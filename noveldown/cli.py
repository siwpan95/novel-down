#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
命令行接口。

  python -m noveldown sites                     列出可用站点规则
  python -m noveldown rules [--json]            查看规则详情
  python -m noveldown probe <url>               规则自检：抓目录 + 抽 1 章，报告命中情况
  python -m noveldown fetch <url> [选项]        抓取整本（支持断点续爬）并导出
  python -m noveldown export <url> [选项]       仅从已有断点/缓存重新导出
  python -m noveldown report <url>              仅产出校对报告
  python -m noveldown selfcheck                 免费章节约束的代码级机械自检
"""

import argparse
import json
import os
import sys
import time

from .constants import (APP_TITLE, DEFAULT_CONFIG, MIN_CHAPTER_CHARS,
                        POLICY_DENYLIST, VERSION)
from .exporters import EXPORTERS, export_all
from .freeguard import (assert_no_protected, assert_site_allowed, selfcheck,
                        FreeGuardError)
from .models import Book, STATUS_OK
from .proofread import format_report, proofread
from .rules import find_rule, load_rules, site_overview, RuleError
from .state import StateStore, slug_of

LEVEL_ICON = {"info": "·", "ok": "✓", "warn": "!", "error": "✗"}


# ============================================================
#  日志
# ============================================================
def make_logger(quiet: bool = False):
    def _log(msg, level="info"):
        if quiet and level in ("info",):
            return
        print(f" {LEVEL_ICON.get(level, '·')} {msg}", flush=True)
    return _log


def make_progress(quiet: bool = False, width: int = 26):
    def _progress(done, total, msg=""):
        if quiet or not total:
            return
        ratio = done / total
        filled = int(width * ratio)
        bar = "█" * filled + "░" * (width - filled)
        sys.stdout.write(f"\r  [{bar}] {done}/{total} {msg[:18]:<18}")
        sys.stdout.flush()
        if done >= total:
            sys.stdout.write("\n")
    return _progress


# ============================================================
#  从状态重建 Book
# ============================================================
def load_book(config: dict, url: str, rules: dict):
    """从 state + cache 重建 Book（用于 export / report 不重新联网）。"""
    assert_site_allowed(url)
    rule = find_rule(url, rules)
    bid = rule.extract_bid(url)
    if not bid:
        raise RuleError(f"无法从 URL 提取书籍 ID：{url}")
    store = StateStore(config["save_dir"], rule.id, bid)
    st = store.load_state()
    if not st:
        raise FileNotFoundError(
            f"未找到断点记录：{store.state_path}\n"
            f"请先执行 fetch：python -m noveldown fetch \"{url}\"")
    book = Book(site=rule.id, book_id=bid, url=st.get("url") or url,
                title=st.get("title", ""), author=st.get("author", ""))
    # 恢复目录排序策略：否则校对会对 document_order 的站点误报「乱序」
    book.catalog_sort = st.get("catalog_sort", "cid_numeric_asc")
    from .models import Chapter, STATUS_PENDING, STATUS_LOCKED, STATUS_BLOCKED
    chapters = []
    for c in st.get("chapters", []):
        ch = Chapter(index=c["index"], title=c.get("title", ""),
                     url=c.get("url", ""), cid=c.get("cid", ""),
                     volume=c.get("volume", ""),
                     status=c.get("status", STATUS_PENDING),
                     note=c.get("note", ""))
        chapters.append(ch)
    book.chapters = chapters
    book.volumes = sorted({c.volume for c in chapters if c.volume})
    store.rehydrate(book)
    return book, store, rule


# ============================================================
#  子命令
# ============================================================
def cmd_sites(args):
    rules = load_rules()
    print(f"{APP_TITLE}")
    active = [r for r in rules.values() if r.enabled]
    disabled = [r for r in rules.values() if not r.enabled]
    print(f"站点规则共 {len(rules)} 条：启用 {len(active)}，停用 {len(disabled)}\n")

    print(f"  {'规则 ID':<18} {'名称':<20} {'说明'}")
    print("  " + "-" * 86)
    for item in site_overview(rules):
        if item["enabled"]:
            flag = " [需JS]" if item["requires_js"] else ""
            print(f"  {item['id']:<18} {item['name']:<20} 可用{flag}　{item['demo_url']}")
        else:
            print(f"  {item['id']:<18} {item['name']:<20} 停用（{item['reason'][:40]}…）")

    print()
    print("  说明：**含 VIP 章节不构成拒绝理由** —— 一本小说通常前几十章免费。")
    print("        拦截发生在**章节级**：目录标 VIP 的章不请求，正文命中付费墙的丢弃。")
    print("        [需JS] 表示该站需浏览器路由（fetch_mode=browser）渲染。")
    if disabled:
        print("        上表「停用」均为**技术原因**（WAF / 需浏览器会话 / 目录靠 JS），非政策拒绝。")
    if POLICY_DENYLIST:
        print(f"  项目声明不支持的域名：{', '.join(POLICY_DENYLIST)}")
    else:
        print("  项目声明不支持的域名：（空）")
    return 0


def cmd_rules(args):
    rules = load_rules()
    if args.json:
        print(json.dumps({k: v.raw for k, v in rules.items()},
                         ensure_ascii=False, indent=2))
        return 0
    for r in sorted(rules.values(), key=lambda x: x.id):
        print(f"\n=== {r.id} · {r.name} " + ("[启用]" if r.enabled else "[停用]"))
        print(f"  匹配域名   : {', '.join(r.match)}")
        print(f"  免费站声明 : free_only={r.free_only}")
        print(f"  需要 JS    : {r.requires_js}")
        print(f"  预解码     : {r.predecode}")
        print(f"  目录项选择 : {r.catalog_cfg.get('item_selector')}")
        print(f"  正文选择器 : {r.chapter_cfg.get('content_selector')}")
        if r.notes:
            print(f"  备注       : {r.notes}")
    return 0


def cmd_probe(args):
    """规则自检：抓目录 + 抽 1 章，报告各环节命中情况。"""
    from .engine import Downloader
    rules = load_rules()
    log = make_logger(args.quiet)
    cfg = _config_from_args(args)
    try:
        d = Downloader(args.url, config=cfg, rules=rules, log=log)
    except (FreeGuardError, RuleError) as e:
        print(f"\n[拒绝] {e}", file=sys.stderr)
        return 2

    d.log(f"[规则] {d.rule.id} · {d.rule.name}")
    if d.rule.fetch_mode == "browser":
        d.log("[路由] browser —— 用真实 Chromium 渲染后取 DOM（单线程）")
    t0 = time.time()
    try:
        book = d.discover()
    except Exception as e:
        d.close()          # 异常时也要释放浏览器，否则会留下未清理的 Playwright 任务
        print(f"\n[失败] 目录发现出错：{e}", file=sys.stderr)
        return 6
    dt = time.time() - t0
    print()
    print("=" * 62)
    print("目录探测结果")
    print("=" * 62)
    print(f"  书名        : {book.title}")
    print(f"  作者        : {book.author}")
    print(f"  站点状态    : {book.status}")
    print(f"  简介        : {(book.intro or '')[:60]}")
    print(f"  章节总数    : {len(book.chapters)}")
    print(f"  受保护章节  : {len(book.protected_chapters)}")
    print(f"  目录耗时    : {dt:.1f}s")
    print(f"  前 5 章     : {[c.title for c in book.chapters[:5]]}")
    print(f"  后 3 章     : {[c.title for c in book.chapters[-3:]]}")

    # 抽第一章实测正文
    target = next((c for c in book.chapters if not c.is_protected), None)
    if target:
        print("\n" + "=" * 62)
        print(f"正文抽样：#{target.index} {target.title}")
        print("=" * 62)
        d._fetch_one_chapter(target)
        print(f"  状态        : {target.status}")
        print(f"  标题(终)    : {target.title}")
        print(f"  备注        : {target.note or '—'}")
        print(f"  请求页数    : {len(target.source_pages)}")
        print(f"  段落 / 字数 : {len(target.paragraphs)} / {target.char_count}")
        print(f"  预解码      : {target.decode_note or '无内联编码'}")
        print(f"  过滤广告行  : {target.ads_removed}")
        print(f"  首段        : {target.paragraphs[0][:60] if target.paragraphs else '—'}")
        if target.char_count < MIN_CHAPTER_CHARS:
            print(f"  [!] 字数低于阈值 {MIN_CHAPTER_CHARS}，该章会被标为 empty")
    d.close()          # 释放浏览器等资源
    return 0


def cmd_fetch(args):
    from .engine import Downloader
    rules = load_rules()
    log = make_logger(args.quiet)
    prog = make_progress(args.quiet)
    cfg = _config_from_args(args)
    try:
        d = Downloader(args.url, config=cfg, rules=rules, log=log, progress=prog)
    except (FreeGuardError, RuleError) as e:
        print(f"\n[拒绝] {e}", file=sys.stderr)
        return 2

    print(f"{APP_TITLE}")
    print(f"目标：{args.url}")
    print("-" * 62)
    try:
        book = d.run(limit=args.limit, force=args.force)
    except KeyboardInterrupt:
        print("\n[中断] 已保存断点，重新运行同一命令即可续爬。")
        return 130

    return _finish(book, d.store, args, log)


def cmd_export(args):
    cfg = _config_from_args(args)
    rules = load_rules()
    log = make_logger(args.quiet)
    book, store, rule = load_book(cfg, args.url, rules)
    print(f"{APP_TITLE} · 重新导出")
    print(f"目标：{book.title}  [{rule.id}/{book.book_id}]")
    print("-" * 62)
    return _finish(book, store, args, log, skip_fetch=True)


def cmd_report(args):
    cfg = _config_from_args(args)
    rules = load_rules()
    book, store, rule = load_book(cfg, args.url, rules)
    rep = proofread(book)
    print(format_report(rep, max_items=args.max_items))
    if args.json:
        path = os.path.join(cfg["save_dir"], f"{slug_of(book.site, book.book_id)}.report.json")
        os.makedirs(cfg["save_dir"], exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(rep, f, ensure_ascii=False, indent=2)
        print(f"\n报告已写出：{path}")
    return 0 if rep["counts"]["verdict"] == "PASS" else 1


def cmd_selfcheck(args):
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    res = selfcheck(root)
    print(f"{APP_TITLE} · 免费章节约束机械自检")
    print("=" * 62)
    print("检查目标：源码中不存在登录 / Cookie / 购买 / 付费墙绕过等代码路径。")
    print(f"扫描根目录：{root}")
    print("-" * 62)
    if res["ok"]:
        print("结果：PASS —— 未发现任何凭据或付费相关代码路径。")
        return 0
    print(f"结果：FAIL —— 发现 {len(res['violations'])} 处：")
    for path, line, what, src in res["violations"]:
        print(f"  {path}:{line}  [{what}]  {src}")
    return 1


# ============================================================
#  收尾（校对 + 导出）
# ============================================================
def _config_from_args(args) -> dict:
    cfg = dict(DEFAULT_CONFIG)
    for key in ("concurrency", "delay", "timeout", "retries"):
        v = getattr(args, key, None)
        if v is not None:
            cfg[key] = v
    if getattr(args, "out", None):
        cfg["save_dir"] = args.out
    if getattr(args, "proxy", None):
        cfg["proxy"] = args.proxy
    if getattr(args, "curl_cffi", False):
        cfg["use_curl_cffi"] = True
    cfg["save_dir"] = os.path.abspath(cfg["save_dir"])
    return cfg


def _finish(book, store, args, log, skip_fetch=False):
    cfg = _config_from_args(args)
    formats = [f.strip() for f in (args.formats or "txt,md,epub,html").split(",") if f.strip()]

    # 校对
    rep = proofread(book)
    if not args.quiet or args.report:
        print()
        print(format_report(rep, max_items=args.max_items))

    # 免费约束终检（写盘前）
    try:
        assert_no_protected(book.chapters, context="导出前终检")
    except FreeGuardError as e:
        print(f"\n[拦截] {e}", file=sys.stderr)
        return 3

    ok = len(book.ok_chapters)
    if ok == 0:
        print("\n[跳过导出] 没有可导出的章节。", file=sys.stderr)
        return 1

    # 导出
    out_dir = os.path.join(cfg["save_dir"], f"{book.title}_{book.site}" if book.title else book.book_id)
    print("\n导出：")
    results = export_all(book, out_dir, formats=formats, verbose=log)

    # 报告落盘
    rep_path = os.path.join(out_dir, "proofread.json")
    os.makedirs(out_dir, exist_ok=True)
    with open(rep_path, "w", encoding="utf-8") as f:
        json.dump(rep, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 62)
    print(f"完成：{book.title} ｜ 可导出 {ok} 章 ｜ {book.total_chars} 字")
    stats = book.stats()["by_status"]
    print(f"状态分布：{stats}")
    print(f"输出目录：{out_dir}")
    print(f"断点记录：{store.state_path}")
    print(f"校对报告：{rep_path}（结论 {rep['counts']['verdict']}）")
    print("=" * 62)
    return 0 if rep["counts"]["verdict"] == "PASS" else 1


# ============================================================
#  参数解析
# ============================================================
def build_parser():
    p = argparse.ArgumentParser(
        prog="noveldown",
        description=f"{APP_TITLE} —— 规则驱动的网络小说离线阅读工具（仅免费章节）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""示例：
  python -m noveldown sites
  python -m noveldown probe "https://www.shuquge.com/txt/207266/index.html"
  python -m noveldown fetch "https://www.shuquge.com/txt/207266/index.html" --limit 20
  python -m noveldown fetch "https://www.bqgbe.cc/txt/445/" --concurrency 3
  python -m noveldown export "https://www.bqgbe.cc/txt/445/" --formats epub,html
  python -m noveldown report "https://www.bqgbe.cc/txt/445/"
  python -m noveldown selfcheck
""")
    p.add_argument("-V", "--version", action="version", version=f"noveldown {VERSION}")
    sub = p.add_subparsers(dest="cmd", required=True)

    def add_common(sp, with_fetch=True):
        if with_fetch:
            sp.add_argument("--limit", type=int, default=0,
                            help="最多抓取多少章（0=全部，调试用）")
            sp.add_argument("--force", action="store_true",
                            help="忽略断点，清空缓存重新抓取")
        sp.add_argument("-o", "--out", default=None, help="输出根目录（默认 output/）")
        sp.add_argument("--formats", default="txt,md,epub,html",
                        help="导出格式，逗号分隔：" + ",".join(EXPORTERS.keys()))
        sp.add_argument("--concurrency", type=int, default=None, help="并发数（默认 4）")
        sp.add_argument("--delay", type=float, default=None, help="基础请求间隔秒（默认 1.2）")
        sp.add_argument("--timeout", type=int, default=None, help="请求超时秒（默认 30）")
        sp.add_argument("--retries", type=int, default=None, help="重试次数（默认 3）")
        sp.add_argument("--proxy", default=None, help="代理地址，如 http://127.0.0.1:7890")
        sp.add_argument("--curl-cffi", action="store_true",
                        help="启用 curl_cffi TLS 指纹伪装")
        sp.add_argument("-q", "--quiet", action="store_true", help="安静模式")
        sp.add_argument("--max-items", type=int, default=8, help="校对报告每节最多列出条数")
        sp.add_argument("--report", action="store_true", help="安静模式下也打印校对报告")

    sp = sub.add_parser("sites", help="列出可用站点规则")
    sp.set_defaults(func=cmd_sites)

    sp = sub.add_parser("rules", help="查看规则详情")
    sp.add_argument("--json", action="store_true", help="输出原始 JSON")
    sp.set_defaults(func=cmd_rules)

    sp = sub.add_parser("probe", help="规则自检（抓目录 + 抽 1 章）")
    sp.add_argument("url")
    add_common(sp, with_fetch=False)
    sp.set_defaults(func=cmd_probe)

    sp = sub.add_parser("fetch", help="抓取整本并导出")
    sp.add_argument("url")
    add_common(sp, with_fetch=True)
    sp.set_defaults(func=cmd_fetch)

    sp = sub.add_parser("export", help="仅从断点/缓存重新导出")
    sp.add_argument("url")
    add_common(sp, with_fetch=False)
    sp.set_defaults(func=cmd_export)

    sp = sub.add_parser("report", help="仅产出校对报告")
    sp.add_argument("url")
    add_common(sp, with_fetch=False)
    sp.add_argument("--json", action="store_true", help="同时写出 JSON 报告")
    sp.set_defaults(func=cmd_report)

    sp = sub.add_parser("selfcheck", help="免费章节约束机械自检")
    sp.set_defaults(func=cmd_selfcheck)

    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except FreeGuardError as e:
        print(f"\n[拒绝] {e}", file=sys.stderr)
        return 2
    except RuleError as e:
        print(f"\n[规则错误] {e}", file=sys.stderr)
        return 4
    except FileNotFoundError as e:
        print(f"\n[未找到] {e}", file=sys.stderr)
        return 5
    except KeyboardInterrupt:
        print("\n[中断]")
        return 130


if __name__ == "__main__":
    sys.exit(main())
