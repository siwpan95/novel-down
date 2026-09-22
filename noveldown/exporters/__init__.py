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

from ..freeguard import (assert_export_shape, assert_no_protected,
                         filter_exportable)

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


def safe_out_dir(save_dir: str, book) -> str:
    r"""把「保存根目录 + 书名」拼成**保证不越界**的输出目录。

    ⚠⚠ 为什么需要它（2026-09-22 上线前全检的 🔴 发现，CWE-22）：
    `cli.py` 与 `gui.py` 原来都写
    `os.path.join(save_dir, f"{book.title}_{book.site}")` —— 而 `book.title`
    来自**远端页面**：被劫持/恶意的镜像站返回 `..\..\PWNED`（反斜杠形式的上级目录）就能把成品写到
    `--out` **之外**；书名含 Windows 非法字符（`?` `*` `|`）时更是**直接建目录失败**
    （后者不需要任何攻击者就会命中）。
    仓内**早有** `book_slug()`（四个导出器都用它做文件名），**唯独目录名漏用**。

    这里做两件事：
      1. 目录名过 `book_slug()`（净化非法字符，`..` 也会被替换掉）；
      2. 拼完用 `commonpath` **断言仍在 save_dir 之内**，越界直接抛错（fail-closed）——
         「净化」是概率性的，「断言」才是兜底。
    """
    root = os.path.abspath(save_dir)
    # ⚠ 保留 cli.py 原来的语义：**书名空时只用 book_id**
    #   （原来是 `f"{title}_{site}" if title else book_id`）。
    #   我第一版写成 `book_slug(book) or book_id` —— `book_slug` 对空标题返回的是
    #   `"_demo"`（下划线 + 站点），**非空**，于是 `or` 永不触发，语义被悄悄改掉了。
    #   是 tests/test_export_paths.py 里那条用例把它揪出来的。
    title = (getattr(book, "title", "") or "").strip()
    if title:
        slug = book_slug(book)
    else:
        slug = safe_filename(getattr(book, "book_id", "") or "", fallback="book")
    out = os.path.abspath(os.path.join(root, slug))
    if os.path.commonpath([root, out]) != root:
        raise ValueError("输出目录越界，已拒绝：%r 不在 %r 之内" % (out, root))
    return out


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
    # 第 5 层终检：受保护章节不得**携带正文**（存在但为空是正常状态）
    assert_no_protected(book.chapters, context="导出前终检")
    assert_export_shape(filter_exportable(book.chapters), context="导出前终检")
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
