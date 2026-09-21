#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从「中国哲学书电子化计划」离线数据集导入书籍并导出。

## 为什么有这个工具

`ctext.org` 本身抓不了：纯 HTTP 与**无头浏览器都被 Cloudflare Turnstile 拦住**
（见规则存根 `noveldown/rules/ctext.org.json`）。但社区有它的**离线数据集**
（`github.com/Guopop/chinese-philosophy`），因此改为**离线导入**——
本工具只读本地 zip，**零网络请求**。

## 数据集形态（实测）

    { "name": "大学", "author": "战国·佚名", "loadChapterCount": 1,
      "chapters": [ { "name": "大学",
                      "paragraphs": [ {"paragraph": "…", "type": 1|2} ] } ] }

与本仓 `Book` / `Chapter` 模型**一一对应**，所以直接映射后**复用既有导出器**
（txt / md / epub / 单文件 HTML 阅读器）。

## 去重

zip 里同一本书常有**多个版本**（`back/old` 旧版、`back/new` 新版、
`back/traditional` 繁体、以及顶层 `经/史/子/集/佛/道` 的最终整理版）。
按书名去重，**优先级**：顶层分类目录 > `back/new` > `back/simple` > `back/old` > `back/traditional`。

## 用法

    python tools\\import_chinese_philosophy.py --zip <数据集 zip 路径> --list
    python tools\\import_chinese_philosophy.py --zip <zip> --book 大学
    python tools\\import_chinese_philosophy.py --zip <zip> --book 论语 --formats txt,md,epub,html
    python tools\\import_chinese_philosophy.py --zip <zip> --all --formats txt,md   # 全量（谨慎：3797 万字）

退出码：0 成功；1 失败。
"""

import argparse
import json
import os
import re
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from noveldown.exporters import export_all, safe_filename  # noqa: E402
from noveldown.models import Book, Chapter  # noqa: E402

# 去重优先级（数字越小越优先）。顶层分类目录是最终整理版，排最前。
PRIORITY_DIRS = ("经/", "史/", "子/", "集/", "佛/", "道/")
SOURCE_LABEL = "ctext"
CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def _priority(path: str) -> int:
    """给数据集内路径打分，越小越优先。"""
    p = path.split("/", 1)[1] if "/" in path else path
    if p.startswith(PRIORITY_DIRS):
        return 0                      # 顶层最终整理版
    if p.startswith("back/new/"):
        return 1
    if p.startswith("back/simple/"):
        return 2
    if p.startswith("back/old/"):
        return 3
    if p.startswith("back/traditional/"):
        return 4
    if p.startswith("cjk/"):
        return 9                      # 字符集文件，不是书
    return 5


def scan(zip_path: str) -> dict:
    """返回 {书名: [ (优先级, zip 内路径, 原始 dict) ]}（只读元信息，惰性解析正文）。"""
    z = zipfile.ZipFile(zip_path)
    out = {}
    for info in z.infolist():
        n = info.filename
        if not n.endswith(".json") or "/." in n:
            continue
        if _priority(n) >= 9:
            continue
        try:
            d = json.loads(z.read(n).decode("utf-8"))
        except Exception:
            continue
        if not isinstance(d, dict) or "chapters" not in d:
            continue
        name = (d.get("name") or "").strip() or os.path.basename(n)[:-5]
        out.setdefault(name, []).append((_priority(n), n, d))
    for k in out:
        out[k].sort(key=lambda t: (t[0], t[1]))
    return out


def stat_of(d: dict):
    """(章数, 汉字数, 段落数)"""
    ch = d.get("chapters") or []
    chars = 0
    paras = 0
    for c in ch:
        for p in (c.get("paragraphs") or []):
            paras += 1
            chars += len(CJK_RE.findall(p.get("paragraph") or ""))
    return len(ch), chars, paras


def to_book(name: str, d: dict, src_path: str) -> Book:
    """数据集 dict → 本仓 Book（段落直接用 `paragraph`，**保留原文，不做任何改写**）。"""
    book = Book(
        site=SOURCE_LABEL,
        book_id=name,
        url="",                                  # 离线数据，无来源 URL
        title=d.get("name") or name,
        author=(d.get("author") or "").strip(),
        intro="",
        status="",
    )
    chapters = []
    for i, c in enumerate(d.get("chapters") or [], 1):
        paras = []
        for p in (c.get("paragraphs") or []):
            t = (p.get("paragraph") or "").strip()
            if t:
                paras.append(t)
        ch = Chapter(index=i,
                     title=(c.get("name") or "").strip() or f"第 {i} 节",
                     url="",
                     cid=str(i),
                     paragraphs=paras,
                     status="ok",
                     source_pages=[f"{src_path}#{i}"])
        chapters.append(ch)
    book.chapters = chapters
    return book


def main():
    ap = argparse.ArgumentParser(
        description="从「中国哲学书电子化计划」离线数据集导入书籍",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--zip", required=True, help="chinese-philosophy-main.zip 路径")
    ap.add_argument("--list", action="store_true", help="只列出书目，不导出")
    ap.add_argument("--book", help="要导入的书名（精确匹配数据集里的 name）")
    ap.add_argument("--all", action="store_true", help="导入全部（⚠ 3797 万字，耗时长）")
    ap.add_argument("--formats", default="txt,md,epub,html", help="导出格式")
    ap.add_argument("-o", "--out", default="output", help="输出根目录")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    if not os.path.isfile(args.zip):
        print("找不到 zip：%s" % args.zip)
        return 1

    books = scan(args.zip)
    total_ch = sum(stat_of(v[0][2])[0] for v in books.values())
    total_chars = sum(stat_of(v[0][2])[1] for v in books.values())
    print("数据集：%d 本书 · %d 章 · %.1f 万字（已按书名去重，取优先级最高的版本）"
          % (len(books), total_ch, total_chars / 10000))

    if args.list:
        print()
        rows = [(n, stat_of(r[0][2]), r[0][1]) for n, r in books.items()]
        for n, (c, ch_, p), path in sorted(rows, key=lambda x: -x[1][1])[:60]:
            print("   %-26s %4d 章 %9.1f 万字   %s" % (n, c, ch_ / 10000, path.split("/", 1)[1]))
        if len(rows) > 60:
            print("   … 共 %d 本" % len(rows))
        return 0

    targets = []
    if args.all:
        targets = sorted(books)
    elif args.book:
        if args.book not in books:
            print("数据集中没有「%s」。用 --list 看书名。" % args.book)
            cand = [n for n in books if args.book in n][:8]
            if cand:
                print("你是不是要：", "、".join(cand))
            return 1
        targets = [args.book]
    else:
        print("请指定 --book <书名> 或 --all（或 --list 先看看）")
        return 1

    fmts = [f.strip() for f in args.formats.split(",") if f.strip()]
    done = fail = 0
    for name in targets:
        d = books[name][0][2]
        src = books[name][0][1]
        try:
            book = to_book(name, d, src)
            out_dir = os.path.join(args.out, "%s_%s" % (safe_filename(name), SOURCE_LABEL))
            paths = export_all(book, out_dir, formats=fmts,
                               verbose=(lambda m, lv="": print("      " + m))
                               if args.verbose else None)
            done += 1
            nch, nchars, _ = stat_of(d)
            print(" ✓ %-24s %4d 章 %8.1f 万字 → %s"
                  % (name, nch, nchars / 10000, out_dir))
            if args.verbose and isinstance(paths, dict):
                for k, v in paths.items():
                    print("      %-4s %s" % (k, v))
        except Exception as e:                                  # noqa: BLE001
            fail += 1
            print(" ✗ %-24s 失败：%s: %s" % (name, type(e).__name__, e))

    print()
    print("完成：成功 %d · 失败 %d" % (done, fail))
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
