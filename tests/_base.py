#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
离线单元测试（不联网，全部基于 fixtures/ 与合成样本）。

运行：
    cd G:\\local\\novel-down
    F:\\Python314\\python.exe -m unittest discover -s tests -v
"""

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

FIX = os.path.join(ROOT, "tests", "fixtures")


def read_fixture(name: str) -> str:
    with open(os.path.join(FIX, name), "r", encoding="utf-8") as f:
        return f.read()


def make_book(title="测试书", author="某作者", n=3):
    from noveldown.models import Book, Chapter, STATUS_OK
    b = Book(site="test.site", book_id="1", url="http://test.site/b/1/",
             title=title, author=author)
    b.chapters = [
        Chapter(index=i, title=f"第{i}章 标题{i}", url=f"http://test.site/c/{i}.html",
                cid=str(1000 + i), status=STATUS_OK,
                paragraphs=[f"这是第{i}章的正文段落。" * 6])
        for i in range(1, n + 1)
    ]
    return b


# ------------------------------------------------------------------
#  共享临时目录
# ------------------------------------------------------------------
# 本机文件系统极慢（实测：创建+写+删一个临时目录 ≈1.5s，项目内 ≈3.1s，
# 疑似杀毒软件实时扫描），若每个测试都 TemporaryDirectory() + cleanup()，
# 单测总耗时会从数秒膨胀到 90s+。
# 因此改为「模块级一个临时根目录 + 每个测试用一个唯一子目录、不做删除」。
import itertools  # noqa: E402
import tempfile as _tempfile  # noqa: E402

_TMP_ROOT = None
_TMP_SEQ = itertools.count()


def temp_root() -> str:
    """返回共享临时根目录（进程内只创建一次，不清理单测子目录）。"""
    global _TMP_ROOT
    if _TMP_ROOT is None:
        _TMP_ROOT = _tempfile.mkdtemp(prefix="noveldown-tests-")
    return _TMP_ROOT


def temp_subdir(tag: str = "t") -> str:
    """在共享根目录下取一个全新的子目录路径（不预创建）。"""
    return os.path.join(temp_root(), f"{tag}-{next(_TMP_SEQ)}")
