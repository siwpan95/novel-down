#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TXT 导出：单文件纯文本，最大兼容性。"""

import os

from ..freeguard import assert_no_protected, filter_exportable
from . import book_slug, ensure_dir, group_by_volume, register

SEP = "=" * 40


@register("txt")
def export(book, out_dir: str) -> str:
    assert_no_protected(book.chapters, context="txt 导出")
    ensure_dir(out_dir)
    path = os.path.join(out_dir, f"{book_slug(book)}.txt")

    chapters = filter_exportable(book.chapters)
    lines = [
        SEP,
        f"书名：{book.title}",
        f"作者：{book.author}",
        f"来源：{book.url}",
        f"站点：{book.site}",
        f"章节：{len(chapters)}",
        "说明：仅供个人离线阅读，内容版权归原作者与发布方所有。",
        SEP,
        "",
    ]
    if book.intro:
        lines += ["【简介】", book.intro, ""]

    groups = group_by_volume(chapters)
    multi_vol = len(groups) > 1 or (groups and groups[0][0])
    for vi, (vol, chs) in enumerate(groups, 1):
        if multi_vol:
            title = vol or f"卷{vi}"
            lines += ["", SEP, f"【{title}】", SEP, ""]
        for ch in chs:
            lines += [ch.title, ""]
            lines += ch.paragraphs
            lines += ["", ""]

    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines))
    return path
