#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""校对报告测试。"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from noveldown.models import (Chapter, STATUS_BLOCKED, STATUS_EMPTY,  # noqa: E402
                              STATUS_LOCKED, STATUS_OK, STATUS_PENDING)
from noveldown.proofread import format_report, proofread  # noqa: E402
from tests._base import make_book  # noqa: E402


class TestProofread(unittest.TestCase):

    def test_clean_book_passes(self):
        rep = proofread(make_book(n=3))
        self.assertEqual(rep["counts"]["verdict"], "PASS")
        self.assertEqual(rep["counts"]["ok"], 3)
        self.assertEqual(rep["counts"]["blocking_issues"], 0)

    def test_pending_is_reported_separately_from_missing(self):
        """限流抓取时未抓章节属预期，不应算「缺失」而判 WARN。"""
        book = make_book(n=3)
        book.chapters[2].status = STATUS_PENDING
        book.chapters[2].paragraphs = []
        rep = proofread(book)
        self.assertEqual(rep["counts"]["not_fetched"], 1)
        self.assertEqual(rep["counts"]["missing"], 0)
        self.assertEqual(rep["counts"]["verdict"], "PASS")

    def test_failed_chapter_is_blocking(self):
        book = make_book(n=3)
        book.chapters[1].status = STATUS_EMPTY
        book.chapters[1].paragraphs = []
        rep = proofread(book)
        self.assertEqual(rep["counts"]["missing"], 1)
        self.assertEqual(rep["counts"]["verdict"], "WARN")

    def test_out_of_order_detected(self):
        book = make_book(n=3)
        book.chapters[0].cid = "9999"     # 人为打乱
        rep = proofread(book)
        self.assertGreater(rep["counts"]["out_of_order"], 0)
        self.assertEqual(rep["counts"]["verdict"], "WARN")

    def test_duplicate_title_and_body_detected(self):
        """同名**且同文** = 真重复（回显块/重复抓取）。"""
        book = make_book(n=3)
        book.chapters[1].title = book.chapters[0].title
        book.chapters[1].paragraphs = list(book.chapters[0].paragraphs)
        rep = proofread(book)
        self.assertEqual(rep["counts"]["duplicate_title"], 1)
        self.assertEqual(rep["counts"]["duplicate_body"], 1)
        self.assertEqual(rep["counts"]["title_clash"], 0)
        self.assertEqual(rep["duplicate_title"][0]["body_same"], True)

    def test_same_title_different_body_is_clash_not_duplicate(self):
        """同名但**不同文** = 站点命名撞车（红袖「番外：归家」实测形态）。

        这类**不是**抓取缺陷，也不能当重复去删 —— 否则会丢掉一章真内容。
        """
        book = make_book(n=3)
        book.chapters[1].title = book.chapters[0].title
        # 正文保持不同（make_book 每章内容各异）
        self.assertNotEqual(book.chapters[0].text, book.chapters[1].text)
        rep = proofread(book)
        self.assertEqual(rep["counts"]["duplicate_title"], 0)
        self.assertEqual(rep["counts"]["title_clash"], 1)
        self.assertEqual(rep["duplicate_title"], [])
        self.assertIs(rep["title_clash"][0]["body_same"], False)
        # 不构成阻断项
        self.assertEqual(rep["counts"]["blocking_issues"], 0)
        self.assertEqual(rep["counts"]["verdict"], "PASS")

    def test_title_clash_with_unfetched_body_is_undetermined(self):
        """--limit 限流时同名两章可能只抓到一章 → 判「未定」，别硬说站点撞车。"""
        book = make_book(n=2)
        book.chapters[1].title = book.chapters[0].title
        book.chapters[1].paragraphs = []
        book.chapters[1].status = STATUS_PENDING
        rep = proofread(book)
        self.assertEqual(rep["counts"]["duplicate_title"], 0)
        self.assertEqual(rep["counts"]["title_clash"], 1)
        self.assertIsNone(rep["title_clash"][0]["body_same"])

    def test_report_text_separates_the_two_cases(self):
        from noveldown.proofread import format_report
        book = make_book(n=3)
        book.chapters[1].title = book.chapters[0].title
        txt = format_report(proofread(book))
        self.assertIn("标题重复", txt)
        self.assertIn("标题同名", txt)
        self.assertIn("站点命名", txt)

    def test_ad_residue_and_mojibake_detected(self):
        book = make_book(n=2)
        book.chapters[0].paragraphs = ["正文" * 60, "最新网址：www.example.com"]
        book.chapters[1].paragraphs = ["a1b2c3d4e5" * 60]     # 汉字占比极低
        rep = proofread(book)
        self.assertEqual(rep["counts"]["ad_residue"], 1)
        self.assertEqual(rep["counts"]["mojibake"], 1)

    def test_short_chapter_detected_against_median(self):
        book = make_book(n=3)
        book.chapters[2].paragraphs = ["太短"]
        rep = proofread(book)
        self.assertEqual(rep["counts"]["short_chapter"], 1)

    def test_protected_listed_but_not_counted_as_missing(self):
        book = make_book(n=2)
        book.chapters.append(Chapter(index=3, title="VIP", url="u",
                                     cid="2003", status=STATUS_LOCKED,
                                     note="目录项 class 命中 'vip'"))
        rep = proofread(book)
        self.assertEqual(rep["counts"]["protected"], 1)
        self.assertEqual(rep["counts"]["missing"], 0)
        self.assertEqual(rep["counts"]["verdict"], "PASS")
        self.assertEqual(rep["protected"][0]["note"], "目录项 class 命中 'vip'")

    def test_format_report_renders(self):
        book = make_book(n=2)
        book.chapters.append(Chapter(index=3, title="VIP", url="u", cid="2003",
                                     status=STATUS_BLOCKED, note="付费墙"))
        text = format_report(proofread(book))
        self.assertIn("校对报告", text)
        self.assertIn("受保护章节", text)
        # 受保护章节属预期拦截，不是阻断性问题
        self.assertIn("结论         : PASS", text)

    def test_format_report_shows_warn_on_real_failure(self):
        book = make_book(n=2)
        book.chapters[0].status = STATUS_EMPTY
        book.chapters[0].paragraphs = []
        text = format_report(proofread(book))
        self.assertIn("WARN", text)
        self.assertIn("缺失 / 失败章节", text)


if __name__ == "__main__":
    unittest.main()
