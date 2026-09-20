#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Markdown 导出：保留书名/作者/卷结构/标题层级，便于二次加工或转 EPUB。"""

import os

from ..freeguard import assert_no_protected, filter_exportable
from . import book_slug, ensure_dir, group_by_volume, register


def _yaml_escape(s: str) -> str:
    return (s or "").replace('"', '\\"').replace("\n", " ").strip()


@register("md")
def export(book, out_dir: str) -> str:
    assert_no_protected(book.chapters, context="markdown 导出")
    ensure_dir(out_dir)
    path = os.path.join(out_dir, f"{book_slug(book)}.md")

    chapters = filter_exportable(book.chapters)
    out = [
        "---",
        f'title: "{_yaml_escape(book.title)}"',
        f'author: "{_yaml_escape(book.author)}"',
        f'source: "{_yaml_escape(book.url)}"',
        f'site: "{_yaml_escape(book.site)}"',
        f"chapters: {len(chapters)}",
        "language: zh-CN",
        "---",
        "",
        f"# {book.title}",
        "",
    ]
    if book.author:
        out += [f"> 作者：{book.author}", ""]
    out += [f"> 来源：{book.url}", "",
            "> 仅供个人离线阅读，内容版权归原作者与发布方所有。", ""]
    if book.intro:
        out += ["## 简介", "", book.intro, ""]

    groups = group_by_volume(chapters)
    multi_vol = len(groups) > 1 or (groups and groups[0][0])
    for vi, (vol, chs) in enumerate(groups, 1):
        if multi_vol:
            out += [f"## {vol or f'卷{vi}'}", ""]
        for ch in chs:
            out += [f"### {ch.title}", ""]
            for p in ch.paragraphs:
                out += [p, ""]
            out += ["", ""]

    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(out))
    return path
