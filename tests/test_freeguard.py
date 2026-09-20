#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
免费章节硬拦截层测试。

这是本项目最关键的约束：**只抓免费章节，绝不涉及 VIP 付费内容**。
测试从「付费站拒绝 → 规则声明 → 目录标记 → 正文付费墙 → 导出终检 → 代码自检」
六层逐层验证，任何一层失效都应测试失败。
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from noveldown import freeguard  # noqa: E402
from noveldown.constants import MIN_CHAPTER_CHARS  # noqa: E402
from noveldown.freeguard import (FreeGuardError, assert_no_protected,  # noqa: E402
                                 assert_site_allowed, check_content,
                                 filter_exportable, is_vip_item, selfcheck)
from noveldown.models import (Chapter, STATUS_BLOCKED, STATUS_EMPTY,  # noqa: E402
                              STATUS_LOCKED, STATUS_OK, STATUS_PENDING)
from tests._base import make_book, temp_subdir  # noqa: E402


class TestLayer1PaidSiteDenylist(unittest.TestCase):

    def test_paid_sites_are_rejected(self):
        for url in ("https://www.qidian.com/book/1010868264/",
                    "https://book.qidian.com/info/1010868264",
                    "https://www.zongheng.com/book/1.html",
                    "https://www.17k.com/book/1.html",
                    "https://www.jjwxc.net/onebook.php?novelid=1",
                    "https://www.ciweimao.com/book/1",
                    "https://www.faloo.com/book/1.html"):
            with self.assertRaises(FreeGuardError, msg=f"应拒绝 {url}"):
                assert_site_allowed(url)

    def test_lookalike_host_is_not_matched(self):
        """相似域名不得被误伤，也不得被绕过（如 qidian.com.evil.com）。"""
        assert_site_allowed("https://www.shuquge.com/txt/1/")
        with self.assertRaises(FreeGuardError):
            assert_site_allowed("https://www.qidian.com.evil.com/x")
        with self.assertRaises(FreeGuardError):
            assert_site_allowed("https://book.qidian.com.attacker.net/x")


class TestLayer3VipCatalogItem(unittest.TestCase):

    def test_class_marker(self):
        protected, why = is_vip_item("chapter-item vip-lock", "第一章")
        self.assertTrue(protected)
        self.assertIn("class", why)

    def test_uppercase_vip_in_class_is_matched(self):
        """站点常写 VIP（大写），标记词是小写——必须大小写不敏感。"""
        protected, _ = is_vip_item("item VIP", "第一章")
        self.assertTrue(protected)

    def test_badge_shaped_text_marker(self):
        for title in ("第100章（VIP）", "第101章 【VIP】", "第102章 VIP章节",
                      "第103章 会员专享"):
            protected, _ = is_vip_item("", title)
            self.assertTrue(protected, f"徽章形态应命中：{title}")

    def test_plain_words_in_title_are_not_matched(self):
        """重要：标题里的普通词不代表该章受保护，否则会误锁合法免费章节。

        （实测踩过：把裸词「付费」「订阅」纳入文本匹配后，
        一个正常章节「第3章 付费墙占位」被整批误锁。）
        """
        for title in ("第3章 付费墙占位", "第4章 订阅号运营", "第5章 付费方式",
                      "第6章 VIP客户的烦恼"):
            protected, _ = is_vip_item("", title)
            self.assertFalse(protected, f"不该命中：{title}")

    def test_normal_item_passes(self):
        protected, _ = is_vip_item("chapter-item", "第1章 开始")
        self.assertFalse(protected)


class TestLayer4PaywallAndLength(unittest.TestCase):

    def test_paywall_markers_blocked(self):
        for marker in ("本章为VIP章节", "订阅后可阅读", "余额不足",
                       "请先登录", "试读结束"):
            protected, status, why = check_content(["正文" * 100, marker])
            self.assertTrue(protected, f"应拦截 {marker}")
            self.assertEqual(status, STATUS_BLOCKED)

    def test_short_content_is_empty_not_protected(self):
        protected, status, why = check_content(["太短了"])
        self.assertFalse(protected)
        self.assertEqual(status, STATUS_EMPTY)

    def test_blank_is_empty(self):
        _, status, _ = check_content([])
        self.assertEqual(status, STATUS_EMPTY)
        _, status2, _ = check_content(["   ", ""])
        self.assertEqual(status2, STATUS_EMPTY)

    def test_normal_content_passes(self):
        protected, status, why = check_content(["正常正文。" * 40])
        self.assertFalse(protected)
        self.assertIsNone(status)

    def test_threshold_boundary(self):
        """恰好达标/不达标的分界。"""
        not_enough = ["字" * (MIN_CHAPTER_CHARS - 1)]
        enough = ["字" * (MIN_CHAPTER_CHARS + 1)]
        self.assertEqual(check_content(not_enough)[1], STATUS_EMPTY)
        self.assertIsNone(check_content(enough)[1])


class TestLayer5ExportGate(unittest.TestCase):

    def test_assert_no_protected_raises(self):
        chs = [Chapter(index=1, title="ok", url="u", status=STATUS_OK,
                       paragraphs=["正文" * 40]),
               Chapter(index=2, title="vip", url="u2", status=STATUS_BLOCKED,
                       note="正文命中付费墙特征")]
        with self.assertRaises(FreeGuardError):
            assert_no_protected(chs, context="单元测试")

    def test_filter_exportable_excludes_protected_and_pending(self):
        chs = [
            Chapter(index=1, title="ok", url="u", status=STATUS_OK,
                    paragraphs=["正文" * 40]),
            Chapter(index=2, title="locked", url="u", status=STATUS_LOCKED),
            Chapter(index=3, title="blocked", url="u", status=STATUS_BLOCKED),
            Chapter(index=4, title="pending", url="u", status=STATUS_PENDING),
            Chapter(index=5, title="ok-but-empty", url="u", status=STATUS_OK),
        ]
        out = filter_exportable(chs)
        self.assertEqual([c.index for c in out], [1],
                         "只有「有正文且未被拦截」的章节可导出")

    def test_protected_body_is_never_cached(self):
        """受保护章节的正文不得落盘（防止绕过导出层的泄漏）。"""
        from noveldown.state import StateStore
        st = StateStore(temp_subdir("fg"), "t.site", "1")
        ch = Chapter(index=7, title="vip", url="u", cid="777",
                     status=STATUS_BLOCKED,
                     paragraphs=["这段付费正文绝不能落盘"])
        st.save_chapter(ch)
        saved = st.load_chapter("777", 7)
        self.assertEqual(saved["paragraphs"], [])
        self.assertEqual(saved["status"], STATUS_BLOCKED)


class TestLayer6CodeSelfcheck(unittest.TestCase):

    def test_project_has_no_credential_code_paths(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        res = selfcheck(root)
        self.assertTrue(res["ok"],
                        "发现凭据/付费相关代码路径：\n" +
                        "\n".join(f"{p}:{l} [{w}] {s}" for p, l, w, s in res["violations"]))

    def test_selfcheck_detects_violation(self):
        """自检本身必须有效——构造一个违规文件，确认能被抓出来。"""
        td = temp_subdir("sc-bad")
        os.makedirs(td, exist_ok=True)
        with open(os.path.join(td, "bad.py"), "w", encoding="utf-8") as f:
            f.write("def x():\n"
                    "    headers = {'Cookie': 'token=abc'}\n"
                    "    return headers\n")
        res = selfcheck(td)
        self.assertFalse(res["ok"])
        whats = {w for _, _, w, _ in res["violations"]}
        self.assertIn("Cookie 请求头字段", whats)

    def test_selfcheck_ignores_comments(self):
        td = temp_subdir("sc-ok")
        os.makedirs(td, exist_ok=True)
        with open(os.path.join(td, "ok.py"), "w", encoding="utf-8") as f:
            f.write("# 本项目不含 Cookie 与 token 相关逻辑\n"
                    "X = 1\n")
        self.assertTrue(selfcheck(td)["ok"])


if __name__ == "__main__":
    unittest.main()
