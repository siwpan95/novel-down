#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
站点结构探针 —— 给「新增一个站点规则」用。

它不依赖任何已有规则，直接抓一本书页/目录页/章节页，把「可能成为规则字段」的
结构特征全部打印出来，便于照着 docs/RULES.md 填 JSON。

用法：
    python tools\\probe_site.py "https://site.com/book/123/"
    python tools\\probe_site.py "https://site.com/123/456.html" --chapter

输出包含：
  · 页面编码 / 大小 / 最终 URL（是否跳转）
  · 所有 <select><option>（常见于分页目录）
  · 章节链接候选（href / onclick 两种形态）与计数
  · 正文容器候选（含 <br> 或 <p> 最多的 div）
  · 是否含 JS 内联 base64 正文（本项目 predecode 可还原）
  · 目录页可能的跳转链接（ml2.html / chapters_N/2 之类）
  · 付费墙/VIP 关键词命中情况（命中即说明该站不适合本项目）
"""

import argparse
import os
import re
import sys
from collections import Counter
from urllib.parse import urljoin, urlparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from noveldown.constants import (PAYWALL_MARKERS,  # noqa: E402
                                 VIP_ITEM_CLASS_MARKERS, VIP_ITEM_TEXT_MARKERS)
from noveldown.http_client import build_headers, http_get  # noqa: E402
from noveldown.identity_manager import get_identity_manager  # noqa: E402
from noveldown.parser import make_soup  # noqa: E402
from noveldown.predecode import predecode  # noqa: E402


def fetch(url):
    idm = get_identity_manager()
    resp = http_get(url, headers=build_headers(idm.get_random_identity(),
                                               referer=f"{urlparse(url).scheme}://{urlparse(url).netloc}/"),
                    timeout=30, retries=2)
    return resp


def hr(title):
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


def probe(url):
    resp = fetch(url)
    html = resp.text
    print(f"最终 URL   : {resp.url}")
    print(f"状态码     : {resp.status_code}")
    print(f"编码       : {resp.encoding}")
    print(f"页面大小   : {len(html)} 字符")

    soup = make_soup(html)

    # ---- 预解码探测 ----
    hr("1. JS 内联 base64 正文探测（本项目 predecode 能力）")
    decoded, stats = predecode(html)
    if stats["payloads"]:
        print(f"  ✓ 命中：还原 {stats['payloads']} 段（形态 {stats['kind']}），"
              f"拆 script 壳 {stats['unwrapped']} 处")
        print(f"  → 规则里应设 \"predecode\": true")
        html_for_parse = decoded
        soup = make_soup(decoded)
    else:
        print("  – 未命中（正文应为普通 HTML）")
        print("  → 规则里可设 \"predecode\": false")

    # ---- select ----
    hr("2. <select> 下拉框（常见于「分页目录」）")
    selects = soup.select("select")
    if not selects:
        print("  – 无 select")
    for i, sel in enumerate(selects):
        opts = sel.select("option")
        print(f"  select[{i}] name={sel.get('name')} id={sel.get('id')} options={len(opts)}")
        for o in opts[:4]:
            print(f"      value={o.get('value')!r}  text={o.get_text(strip=True)[:30]!r}")
        if len(opts) > 4:
            print(f"      … 共 {len(opts)} 项")
        print("  → 可用 catalog.pages.mode=\"auto\"（会自动读 select 的 option）")

    # ---- 章节链接候选 ----
    hr("3. 章节链接候选")
    links = soup.select("a[href]")
    url_counter = Counter()
    for a in links:
        h = a.get("href") or ""
        if h.startswith(("javascript:", "#", "mailto:")):
            continue
        full = urljoin(url, h)
        # 归一化成「路径形状」：数字 → {N}
        # 注：replacement 用 callable，否则 "\d" 会被当作转义模板而报 bad escape
        shape = re.sub(r"\d+", lambda m: "{N}", urlparse(full).path)
        url_counter[shape] += 1
    print("  按 URL 形状统计（出现次数 ≥3 的形状更可能是章节链接）:")
    for shape, n in url_counter.most_common(12):
        mark = "  ← 候选" if n >= 3 else ""
        print(f"      {n:5d} × {shape}{mark}")

    # ---- onclick 形态 ----
    # 只有「FUNC(纯数字…)」这种才像章节项；shuqian(bookId,cid,'url') 之类书签按钮不算。
    onclick_ch = []
    for a in soup.select("a[onclick]"):
        oc = (a.get("onclick") or "").strip()
        if re.match(r"[A-Za-z_$][\w$]*\s*\(\s*\d+\s*\)\s*;?\s*$", oc):
            onclick_ch.append((oc, a))
    if len(onclick_ch) >= 3:
        hr("3b. onclick 形态章节链接（无 href 的站点，如 biqu520）")
        fn = Counter()
        for oc, _ in onclick_ch:
            fn[re.match(r"\s*([A-Za-z_$][\w$]*)", oc).group(1)] += 1
        for name, n in fn.most_common(6):
            print(f"      {n:5d} × {name}(数字)")
        print(f"  样例: onclick=\"{onclick_ch[0][0][:80]}\"")
        print("  → 规则里 id_from.mode 用 \"onclick\"，"
              "pattern 用 \\\"(?P<cid>\\\\d+)\\\"，并配 catalog.url_template")

    # ---- 目录页跳转 ----
    hr("4. 目录页跳转候选（多页目录 / 查看更多章节）")
    cands = set()
    for a in links:
        h = a.get("href") or ""
        if h.startswith("javascript:"):
            continue
        full = urljoin(url, h)
        if re.search(r"ml\d+\.html|chapters?_\d+/\d+|/list/\d+/\d+|index_\d+\.html", full):
            cands.add(full)
    if cands:
        for c in sorted(cands)[:10]:
            print(f"      {c}")
        print("  → 可用 catalog.pages.mode=\"auto\" + link_pattern")
    else:
        print("  – 未发现（目录应为单页）")

    # ---- 正文容器候选 ----
    hr("5. 正文容器候选（按容器内段落标记数量排序）")
    scored = []
    for div in soup.select("div, article, section"):
        seg = str(div)[:4000]
        n_br = seg.count("<br")
        n_p = seg.count("<p")
        if n_br + n_p >= 3:
            # 注意：id / class 可能是 None，直接进元组会让 sort 在并列时
            # 比较 str 与 None → TypeError（实测踩过）。
            scored.append((n_br + n_p, div.get("id") or "",
                           " ".join(div.get("class") or []),
                           n_br, n_p, len(seg)))
    scored.sort(reverse=True)
    if not scored:
        print("  – 未找到（正文可能由 JS 渲染，本项目暂不支持）")
    for score, did, dcls, nbr, np_, size in scored[:8]:
        sel = f"#{did}" if did else (f".{dcls.split()[0]}" if dcls else "(无 id/class)")
        print(f"      {score:4d} 分  {sel:28s} br={nbr:4d} p={np_:4d} len={size}")
    print("  → 取最外层且分数最高的为 chapter.content_selector")

    # ---- 元信息 ----
    hr("6. 书籍元信息（og:novel:* 常用）")
    for prop in ("book_name", "author", "status", "latest_chapter_name",
                 "description", "category"):
        el = soup.select_one(f"meta[property='og:novel:{prop}']")
        if el:
            print(f"      og:novel:{prop} = {el.get('content')[:50]!r}")
    for prop in ("og:title", "og:image", "og:description"):
        el = soup.select_one(f"meta[property='{prop}']")
        if el:
            print(f"      {prop} = {el.get('content')[:50]!r}")

    # ---- 免费约束探测 ----
    hr("7. 免费章节约束探测（本项目只处理免费章节）")
    hits = [m for m in PAYWALL_MARKERS if m.lower() in html.lower()]
    vips = sorted({m for m in list(VIP_ITEM_CLASS_MARKERS) + list(VIP_ITEM_TEXT_MARKERS)
                   if m.lower() in html.lower()})
    if hits:
        print(f"  ⚠ 命中付费墙特征：{hits}")
        print("  ⚠ 该页含受保护内容标记，若整站如此，本项目不予支持。")
    else:
        print("  ✓ 未命中付费墙特征")
    if vips:
        print(f"  · 命中 VIP 标记词：{vips}（目录项命中时会自动标记 locked 并跳过）")

    print()


def main():
    ap = argparse.ArgumentParser(description="站点结构探针（用于编写新的站点规则）")
    ap.add_argument("url")
    ap.add_argument("--chapter", action="store_true",
                    help="把 URL 当作正文页探测（默认也可，脚本会自行判断）")
    args = ap.parse_args()
    probe(args.url)
    return 0


if __name__ == "__main__":
    sys.exit(main())
