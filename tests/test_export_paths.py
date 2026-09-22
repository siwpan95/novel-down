#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""导出**路径安全**的回归测试：`safe_filename` / `book_slug` / `safe_out_dir`。

⚠ 为什么必须有这组测试（2026-09-22 上线前全检的 🔴 发现 + 全哥实测的 GUI 导出崩溃）：

1. **路径穿越（CWE-22）**：`cli.py` 与 `gui.py` 原来把**远端返回的书名**直接拼进输出目录
   —— 恶意/被劫持的镜像站返回上级目录形式的名字，就能把成品写到 `--out` 之外。
   仓内早有 `book_slug()`，偏偏**目录名漏用**。
2. **非法字符**：书名含 `?` `*` `|` 时（Windows 非法），连目录都建不出来 ——
   这条**不需要攻击者**就会命中，是纯健壮性问题。
3. 全检时发现 `grep -rn safe_filename tests/` **为空** → 这条路**零回归覆盖**。
"""

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from noveldown.exporters import book_slug, safe_filename, safe_out_dir  # noqa: E402


class _Book:
    def __init__(self, title, site="demo", book_id="1"):
        self.title = title
        self.site = site
        self.book_id = book_id


class TestSafeFilename(unittest.TestCase):

    def test_strips_windows_illegal_chars(self):
        got = safe_filename('斗破苍穹：第一章?*|"<>/\\_demo')
        for ch in '?*|"<>/\\:':
            self.assertNotIn(ch, got, f"{ch!r} 应被净化：{got}")

    def test_empty_falls_back(self):
        self.assertEqual(safe_filename(""), "book")
        self.assertEqual(safe_filename("   "), "book")
        self.assertEqual(safe_filename("..."), "book")   # 全是点也要兜底，别产出 "." 或 ".."

    def test_truncates(self):
        self.assertLessEqual(len(safe_filename("长" * 500)), 80)


class TestBookSlug(unittest.TestCase):

    def test_normal_title_untouched(self):
        self.assertEqual(book_slug(_Book("斗罗大陆")), "斗罗大陆_demo")

    def test_site_included(self):
        self.assertIn("qidian", book_slug(_Book("X", site="qidian")))


class TestSafeOutDir(unittest.TestCase):
    """核心：目录**必须**落在 save_dir 之内，无论书名多离谱。"""

    def setUp(self):
        self.root = os.path.abspath(os.path.join(ROOT, "output-test-safety"))

    def _in_root(self, path):
        return os.path.commonpath([self.root, os.path.abspath(path)]) == self.root

    def test_traversal_is_contained(self):
        """⚠ 这条以前会真的逃出 save_dir（全检独立复现过）。"""
        for evil in ("../../PWNED", "..\\..\\PWNED", "..", "../..",
                     "a/../../b", "....//....//PWNED"):
            out = safe_out_dir(self.root, _Book(evil))
            self.assertTrue(self._in_root(out),
                            f"书名 {evil!r} 竟然逃出了：{out}")

    def test_illegal_chars_do_not_break(self):
        """含 Windows 非法字符的书名不该让建目录直接失败。"""
        out = safe_out_dir(self.root, _Book("斗破苍穹：第一章?_demo"))
        self.assertTrue(self._in_root(out))
        os.makedirs(out, exist_ok=True)      # 真建一次，证明路径可用
        self.assertTrue(os.path.isdir(out))
        os.rmdir(out)

    def test_absolute_title_is_contained(self):
        """书名是绝对路径时也不能把根目录换掉。"""
        out = safe_out_dir(self.root, _Book("C:\\Windows\\Temp\\evil"))
        self.assertTrue(self._in_root(out), out)

    def test_empty_title_falls_back_to_book_id(self):
        out = safe_out_dir(self.root, _Book("", book_id="12345"))
        self.assertTrue(self._in_root(out))
        self.assertIn("12345", os.path.basename(out))

    def test_normal_case_layout(self):
        out = safe_out_dir(self.root, _Book("斗罗大陆", site="biqu520"))
        self.assertEqual(os.path.dirname(out), self.root)
        self.assertEqual(os.path.basename(out), "斗罗大陆_biqu520")


if __name__ == "__main__":
    unittest.main()
