#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""无头自检（不启动 Tk 图形界面）。

只 import 纯逻辑模块（模型 / 规则 / 目录归一化 / 导出器 / 校对 / 免费拦截层），
不 import noveldown.gui，也不联网。验证四件事：

  1. 站点规则能全部加载，且能按 URL 命中启用规则；
  2. 目录归一化（去重 + 升序 + 编号）结果正确；
  3. 导出往返：Book → TXT / EPUB 落盘，内容可被读回校验；
  4. 免费章节终检：存在受保护章节时导出必须 fail-closed。

用法：python selfcheck.py
退出码：0 成功 / 1 失败。
"""

import os
import shutil
import sys
import tempfile
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:  # 统一按 UTF-8 输出，避免 GBK 控制台把中文自检结果打成乱码
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
except Exception:
    pass

from noveldown.freeguard import FreeGuardError  # noqa: E402
from noveldown.models import (STATUS_LOCKED, STATUS_OK, STATUS_PENDING, Book,  # noqa: E402
                              Chapter)
from noveldown.parser import normalize_catalog  # noqa: E402
from noveldown.proofread import proofread  # noqa: E402
from noveldown.rules import active_rules, find_rule, load_rules  # noqa: E402
import noveldown.exporters as exporters  # noqa: E402,F401  注册导出器


def fail(msg):
    print("FAIL: " + msg)
    sys.exit(1)


def check_rules():
    rules = load_rules()
    if not rules:
        fail("规则库为空")
    enabled = active_rules(rules)
    if len(enabled) < 50:
        fail("启用规则太少：%d" % len(enabled))
    rule = find_rule("https://www.shuquge.com/txt/207266/index.html", rules)
    if not rule.enabled:
        fail("find_rule 命中了停用规则：%s" % rule.id)
    if not rule.book_cfg.get("url_pattern"):
        fail("规则缺少 book.url_pattern：%s" % rule.id)
    return len(rules), len(enabled), rule.id


def check_normalize():
    items = [
        {"cid": "305", "title": "第3章", "url": "https://x/305"},
        {"cid": "303", "title": "第1章", "url": "https://x/303"},
        {"cid": "304", "title": "第2章", "url": "https://x/304"},
        {"cid": "303", "title": "第1章", "url": "https://x/303"},  # 最新章节回显
        {"cid": "306", "title": "第4章 VIP", "url": "https://x/306",
         "status": STATUS_LOCKED, "note": "目录标记 VIP"},
    ]
    chs = normalize_catalog(items)
    if [c.cid for c in chs] != ["303", "304", "305", "306"]:
        fail("目录去重/排序不对：%r" % [c.cid for c in chs])
    if [c.index for c in chs] != [1, 2, 3, 4]:
        fail("章节编号不对：%r" % [c.index for c in chs])
    if not chs[-1].is_protected:
        fail("受保护状态在归一化后丢失")
    if len(chs) != 4:
        fail("重复目录项未去重：%d" % len(chs))
    return len(items), len(chs)


def demo_book(with_locked=False):
    paras1 = ["第一段：山雨欲来。", "第二段：他没有回头。"]
    paras2 = ["第一章之外的续篇。", "此处同样只是自检用的占位文本。"]
    book = Book(site="shuquge.com", book_id="207266",
                url="https://www.shuquge.com/txt/207266/index.html",
                title="自检样书", author="无名氏", intro="自检用简介。")
    book.chapters = [
        Chapter(index=1, title="第1章 起", url="https://x/1", cid="1",
                status=STATUS_OK, paragraphs=paras1),
        Chapter(index=2, title="第2章 承", url="https://x/2", cid="2",
                status=STATUS_OK, paragraphs=paras2),
        Chapter(index=3, title="第3章 转", url="https://x/3", cid="3",
                status=STATUS_PENDING),
    ]
    if with_locked:
        book.chapters.append(Chapter(
            index=4, title="第4章 受保护", url="https://x/4", cid="4",
            status=STATUS_LOCKED, note="目录标记 VIP",
            paragraphs=[]))  # 正常状态：占位但不带正文
    return book, paras1 + paras2


def check_export_roundtrip():
    book, para_all = demo_book()
    tmp = tempfile.mkdtemp(prefix="noveldown-selfcheck-")
    try:
        results = exporters.export_all(book, tmp, formats=["txt", "epub"])
        if set(results) != {"txt", "epub"}:
            fail("导出器未全部产出：%r" % sorted(results))

        with open(results["txt"], "r", encoding="utf-8") as f:
            txt = f.read()
        for p in para_all:
            if p not in txt:
                fail("TXT 丢失正文段落：%r" % p)
        for title in ("第1章 起", "第2章 承"):
            if title not in txt:
                fail("TXT 丢失章节标题：%s" % title)
        if "第3章 转" in txt:
            fail("未抓取章节被导出")

        if not zipfile.is_zipfile(results["epub"]):
            fail("EPUB 不是合法 zip 容器")
        with zipfile.ZipFile(results["epub"]) as z:
            names = z.namelist()
            if "mimetype" not in names:
                fail("EPUB 缺少 mimetype")
            if z.read("mimetype").decode("ascii").strip() != "application/epub+zip":
                fail("EPUB mimetype 不正确")
            if not any(n.endswith(".opf") for n in names):
                fail("EPUB 缺少 OPF 包文件")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return sorted(results)


def check_freeguard():
    # (a) 常规状态：目录里有 locked 章节（不带正文）时，导出照常进行，
    #     但产物里绝不能出现该章节。
    book, _ = demo_book(with_locked=True)
    tmp = tempfile.mkdtemp(prefix="noveldown-selfcheck-")
    try:
        res = exporters.export_all(book, tmp, formats=["txt"])
        with open(res["txt"], "r", encoding="utf-8") as f:
            txt = f.read()
        if "受保护" in txt:
            fail("受保护章节标题进入了导出物")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # (b) 泄漏状态：受保护章节竟然带着正文 → 必须 fail-closed，且不落盘。
    book2, _ = demo_book(with_locked=True)
    book2.chapters[-1].paragraphs = ["这段正文本不该被导出。"]
    tmp2 = tempfile.mkdtemp(prefix="noveldown-selfcheck-")
    try:
        try:
            exporters.export_all(book2, tmp2, formats=["txt"])
        except FreeGuardError:
            pass
        else:
            fail("受保护章节携带正文时导出未 fail-closed")
        if os.listdir(tmp2):
            fail("泄漏状态下仍写出了文件：%r" % os.listdir(tmp2))
    finally:
        shutil.rmtree(tmp2, ignore_errors=True)

    # (c) 第 6 层：源码不得存在凭据 / 付费相关代码路径。
    from noveldown import freeguard
    scan = freeguard.selfcheck(os.path.dirname(os.path.abspath(__file__)))
    if not scan["ok"]:
        fail("源码自检发现违规：%r" % scan["violations"][:3])
    return True


def check_proofread():
    book, _ = demo_book()
    report = proofread(book)
    c = report["counts"]
    if c["ok"] != 2:
        fail("校对统计 ok 章节数不对：%d" % c["ok"])
    if c["not_fetched"] != 1:
        fail("校对未把未抓取章节单列：%d" % c["not_fetched"])
    if c["verdict"] != "PASS":
        fail("干净样书被评为 %s" % c["verdict"])
    return c["ok"], c["verdict"]


def main():
    total, enabled, rid = check_rules()
    n_items, n_chs = check_normalize()
    fmts = check_export_roundtrip()
    check_freeguard()
    ok_n, verdict = check_proofread()
    print("selfcheck ok: 规则加载 %d 条(启用 %d，命中 %s) / 目录归一化 %d→%d 去重升序 / "
          "TXT+EPUB 导出往返（%s） / 受保护章节不泄漏且泄漏时 fail-closed / 源码无凭据路径 / "
          "校对 %d 章 %s"
          % (total, enabled, rid, n_items, n_chs, ",".join(fmts), ok_n, verdict))


if __name__ == "__main__":
    main()
