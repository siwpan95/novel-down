#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""「作家入口」机械校验：用**有没有创作/投稿入口**来交叉验证站点归类。

## 判据来源

全哥提出：**正版站才提供创作渠道（作家专区 / 投稿 / 签约），盗版站只负责推小说**。

这条比"看起来像不像正版"可靠得多 —— 它是个**可机械检测的事实**：
去站点首页找 `创作`/`投稿`/`作家专区`/`成为作者`/`我要写书` 这类入口链接。

## 它做什么 / 不做什么

- **做**：对规则里 `pool=正版`（或 `--pool` 指定）的站点逐个抓首页，
  统计命中哪些关键词，输出一张对照表。
- **不做**：**不当硬门禁**。因为
  · 有些**正版免费站**本身不提供创作入口（纯阅读/聚合，如部分授权阅读平台）；
  · 有些站把入口放在更深的页面（首页抓不到）——实测未命中的 4 条都属于这类：
    晋江作者专区在 `my.jjwxc.net`、起点在作家助手/`write.*`、七猫在 `author.qimao.com`、
    掌阅移动站不展示创作入口。
  → 所以它是**审计提示**（`--strict` 才非零退出），而不是"命不中就删规则"。

## 用法

    python tools/check_official.py                    # 校验正版池
    python tools/check_official.py --pool 免费镜像     # 反向对照（应几乎不命中）
    python tools/check_official.py --browser          # JS 站点也用真 Chrome 渲染
"""

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from noveldown.parser import make_soup          # noqa: E402
from noveldown.rules import RULES_DIR, load_rules  # noqa: E402

# 创作/投稿入口的关键词（宽一点没关系，只是提示强度不同）
KW = {
    "创作": ("创作", "我要创作", "开始创作"),
    "投稿": ("投稿", "我要投稿", "作者投稿"),
    "作家": ("作家专区", "作家助手", "成为作家", "作家中心", "作家福利"),
    "作者": ("成为作者", "作者专区", "作者中心", "作者福利", "作者后台", "我的作品"),
    "写书": ("写书", "我要写书", "写小说", "开新书", "新建作品"),
    "签约": ("签约", "签约作者", "申请签约"),
    "原创文学": ("原创文学", "原创小说平台", "文学创作"),
}


def _fetch(url, timeout, browser):
    if not browser:
        from noveldown.http_client import http_get
        try:
            return http_get(url, timeout=timeout, retries=1).text, ""
        except Exception as e:
            return None, f"{type(e).__name__}: {str(e)[:50]}"
    try:
        from noveldown.browser import BrowserFetcher
        f = BrowserFetcher(anti_detect=True, log=lambda m, l="info": None).start()
        try:
            return f.fetch(url, wait_ms=2500), ""
        finally:
            f.close()
    except Exception as e:
        return None, f"{type(e).__name__}: {str(e)[:50]}"


def check_one(rule, timeout, browser):
    """返回 (命中关键词集合, 错误串)。"""
    url = rule.raw.get("demo_url")
    if not url:
        return set(), "规则无 demo_url"
    # 取首页（站点根），创作入口一般在导航里
    from urllib.parse import urlparse
    p = urlparse(url)
    home = f"{p.scheme}://{p.netloc}/"
    html, err = _fetch(home, timeout, browser)
    if html is None:
        return set(), err
    soup = make_soup(html)
    nav = " ".join((a.get_text() or "") + " " + (a.get("href") or "")
                   for a in soup.find_all("a", href=True))
    hits = set()
    for label, words in KW.items():
        if any(w in nav for w in words):
            hits.add(label)
    return hits, ""


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pool", default="正版", help="要校验的池（默认 正版）")
    ap.add_argument("--timeout", type=float, default=20)
    ap.add_argument("--browser", action="store_true",
                    help="用真 Chrome 渲染后再查（JS 站点需要）")
    ap.add_argument("--strict", action="store_true",
                    help="有站点未命中创作入口时以非零码退出（默认只提示）")
    ap.add_argument("--all", action="store_true", help="含停用规则（默认只看启用）")
    ap.add_argument("--limit", type=int, default=0, help="只查前 N 条（抽样，0=全部）")
    args = ap.parse_args()

    rules = load_rules()
    pool = [r for r in rules.values() if r.pool == args.pool]
    if not args.all:
        pool = [r for r in pool if r.enabled]
    pool.sort(key=lambda r: r.id)
    if args.limit:
        pool = pool[:args.limit]
    print(f"校验「{args.pool}」池 {len(pool)} 条"
          f"（{'含停用' if args.all else '仅启用'}）"
          f"｜{'浏览器渲染' if args.browser else '纯 HTTP'}")
    print("=" * 78)

    miss = []
    for r in pool:
        hits, err = check_one(r, args.timeout, args.browser)
        if err:
            print(f"  ?  {r.id:22} 取页失败：{err}")
            miss.append(r.id)
            continue
        if hits:
            print(f"  ✓  {r.id:22} 命中创作入口：{'、'.join(sorted(hits))}")
        else:
            print(f"  ✗  {r.id:22} **未发现**创作/投稿入口")
            miss.append(r.id)

    print("=" * 78)
    ok = len(pool) - len(miss)
    print(f"命中 {ok}/{len(pool)}"
          f"（{100 * ok / max(len(pool), 1):.0f}%）")
    if miss:
        print("⚠ 未命中（**不等于「不是正版」**）—— 可能是纯阅读站、或入口在更深页面：")
        for m in miss:
            print(f"    · {m}")
        print("  → 建议人工复核这几条；**不要**仅凭此判据删规则。")
    if args.strict and miss:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
