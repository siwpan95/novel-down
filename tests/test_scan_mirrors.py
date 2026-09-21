#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""`tools/scan_mirrors.py` 的过滤判据（不联网，只测纯函数）。

重点锁的是 2026-09-21 补上的**URL（含路径）级非小说判定**：
`classify()` 原本只按「书源名 + 域名 + 页面标题」判，于是 `kaixinman.com`
（域名里没有 `comic`，证据在路径 `/comic/…`）一路通过了探活与深探，
直到人工验证才发现是漫画站。
"""

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

import scan_mirrors as sm  # noqa: E402


class TestClassify(unittest.TestCase):

    def test_domain_level_non_novel(self):
        """域名本身带非小说词（既有能力，防止改坏）。"""
        self.assertIn("非小说", sm.classify("", "bbs.example.com"))
        self.assertIn("非小说", sm.classify("", "dmzj.com"))

    def test_url_path_level_non_novel(self):
        """⭐ 本轮新增：证据在**路径**里（域名不含关键词）。"""
        for u in ("https://kaixinman.com/comic/WGdz9651Q2",
                  "https://x.com/manhua/123/",
                  "https://x.com/manga/456/"):
            self.assertIn("非小说", sm.classify("", "", u), u)

    def test_real_book_urls_not_blocked(self):
        """反过来：真书页不能被误杀（宁可漏，不可错杀）。"""
        for u in ("https://www.doupoall.com/book/124595/",
                  "http://www.tycqzw.info/177_177604/",
                  "http://www.ibiqugu.net/142/142920/",
                  "https://51eshu.com/xs/208137.html"):
            self.assertEqual(sm.classify("", "", u), "", u)

    def test_adult_words(self):
        self.assertIn("成人向", sm.classify("某某成人小说", "x.com"))


if __name__ == "__main__":
    unittest.main()
