#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""`tools/gen_family_rule.py` 的两个「防手滑」判据：demo 是不是书页 + id 冲突检查。

两个都是 2026-09-21 实测踩出来的，必须有测试锁住，否则改着改着就退回去了。
不联网、不依赖扫描结果。
"""

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

import gen_family_rule as g  # noqa: E402


class TestDemoIsBookPage(unittest.TestCase):
    """demo_url 必须是**书页**，不能是分类页 / 榜单页 / 漫画页。

    ⚠ 踩过的坑：原来只校验「主机名在 match 内」，于是把
    `/top_0.html`（榜单页）、`/cate1/`（分类页）、`/comic/…`（漫画站）
    都当成了书页 → 生成的草稿 probe 必然 0 章。
    """

    def test_real_book_pages_pass(self):
        for u in ("https://www.doupoall.com/book/124595/",
                  "http://www.tycqzw.info/177_177604/",
                  "http://www.ibiqugu.net/142/142920/",
                  "https://51eshu.com/xs/208137.html"):
            self.assertIsNone(g._DEMO_DENY_PATH.search(u), u)

    def test_non_book_pages_blocked(self):
        cases = {
            "https://m.sewenxue.com/top_0.html": "榜单页",
            "https://m.jdzfx.com/cate1/": "分类页",
            "https://kaixinman.com/comic/WGdz9651Q2": "漫画站（comic 在倒数第二段）",
            "https://x.com/rank/1.html": "排行榜",
            "https://x.com/manga/123/": "漫画（manga）",
        }
        for u, why in cases.items():
            self.assertIsNotNone(g._DEMO_DENY_PATH.search(u), f"{u} 应被拦（{why}）")

    def test_deny_matches_any_path_segment(self):
        """⚠ 不能锚到行尾：`/comic/XXXX` 的 `comic` 在倒数第二段。"""
        self.assertIsNotNone(g._DEMO_DENY_PATH.search("https://a.com/comic/abc123"))
        # 反例（防过度拦截）：真书页里带这些词的**前缀**不该命中
        self.assertIsNone(g._DEMO_DENY_PATH.search("https://a.com/book/124595/"))


class TestFindExisting(unittest.TestCase):
    """id 冲突检查：同签名的批次会生成同名 id，必须能查出来（含 mirrors/ 子目录）。"""

    def test_finds_top_level_rule(self):
        self.assertTrue(g._find_existing("qidian.com"))

    def test_returns_none_for_unknown(self):
        self.assertIsNone(g._find_existing("definitely-not-a-rule-xyz"))


if __name__ == "__main__":
    unittest.main()
