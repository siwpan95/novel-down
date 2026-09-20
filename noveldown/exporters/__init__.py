#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
导出器集合。

每个导出器签名统一为 export(book, out_dir, **opts) -> 输出文件路径。
所有导出器在写盘前都会调用 freeguard.assert_no_protected() 做**第 5 层终检**，
确保受保护章节绝不会进入导出物。
"""

import os
import re

from ..freeguard import assert_no_protected, filter_exportable

EXPORTERS = {}


def register(name):
    def deco(fn):
        EXPORTERS[name] = fn
        return fn
    return deco


def safe_filename(name: str, fallback: str = "book", maxlen: int = 80) -> str:
    """把书名转成安全的文件名。"""
    s = (name or "").strip() or fallback
    s = re.sub(r'[\\/:*?"<>|\r\n\t]', "_", s)
    s = re.sub(r"\s+", " ", s).strip(" .")
    return s[:maxlen] or fallback


def book_slug(book) -> str:
    """书名 + 站点标识，用于输出目录/文件名。"""
    return safe_filename(f"{book.title}_{book.site}")


def group_by_volume(chapters):
    """按卷分组，保持原有顺序。

    Returns: [(卷名 or "", [chapter, ...]), ...]
    """
    groups = []
    cur_name = None
    for ch in chapters:
        name = ch.volume or ""
        if not groups or name != cur_name:
            groups.append((name, []))
            cur_name = name
        groups[-1][1].append(ch)
    return groups


def ensure_dir(path: str) -> str:
    os.makedirs(path, exist_ok=True)
    return path


def export_all(book, out_dir: str, formats=None, verbose=None):
    """按 formats 依次导出。返回 {fmt: path}。"""
    formats = formats or list(EXPORTERS.keys())
    assert_no_protected(book.chapters, context="导出前终检")
    ensure_dir(out_dir)
    results = {}
    for fmt in formats:
        fn = EXPORTERS.get(fmt)
        if fn is None:
            if verbose:
                verbose(f"未知导出格式：{fmt}", "warn")
            continue
        try:
            path = fn(book, out_dir)
            results[fmt] = path
            if verbose:
                size = os.path.getsize(path) if os.path.exists(path) else 0
                verbose(f"  导出 {fmt.upper():5s} → {path}  ({size / 1024:.1f} KB)", "ok")
        except Exception as e:
            if verbose:
                verbose(f"  导出 {fmt.upper()} 失败：{e}", "error")
    return results


from . import txt, md, epub, htmlreader  # noqa: E402,F401  注册导出器
