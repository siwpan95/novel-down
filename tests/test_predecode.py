#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""预解码器测试：JS 内联 base64 正文的还原。"""

import base64
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from noveldown.predecode import predecode, _decode_payload  # noqa: E402
from tests._base import read_fixture  # noqa: E402


def b64(s: str) -> str:
    return base64.b64encode(s.encode("utf-8")).decode()


class TestPredecode(unittest.TestCase):

    def test_document_writeln_with_random_namespace(self):
        """命名空间/函数名每站随机，必须用通配形态匹配。"""
        html = ("<div class='word_read'>"
                "<script>document.writeln(qsbs.bb('%s'));</script>"
                "<script>document.writeln(vmehyrmd.kd('%s'));</script>"
                "</div>") % (b64("<p>第一段</p>"), b64("<p>第二段</p>"))
        out, stats = predecode(html)
        self.assertEqual(stats["payloads"], 2)
        self.assertEqual(stats["kind"], "writeln")
        self.assertIn("<p>第一段</p>", out)
        self.assertIn("<p>第二段</p>", out)

    def test_script_shell_is_unwrapped(self):
        """关键坑：还原出的 HTML 若仍被 <script> 包着，HTML 解析器不认内部标签。"""
        html = "<div><script>document.writeln(ns.fn('%s'));</script></div>" % b64("<p>正文</p>")
        out, stats = predecode(html)
        self.assertEqual(stats["unwrapped"], 1)
        self.assertNotIn("<script>", out)
        from bs4 import BeautifulSoup
        self.assertEqual(len(BeautifulSoup(out, "lxml").select("p")), 1)

    def test_bare_call_and_atob(self):
        html = ("<div>" + "ns.zz('%s')" % b64("<p>裸调用</p>")
                + "atob('%s')" % b64("<p>atob形态</p>") + "</div>")
        out, stats = predecode(html)
        self.assertGreaterEqual(stats["payloads"], 1)
        self.assertTrue("<p>裸调用</p>" in out or "<p>atob形态</p>" in out)

    def test_noop_on_plain_html(self):
        html = "<div><p>普通正文</p></div>"
        out, stats = predecode(html)
        self.assertEqual(out, html)
        self.assertEqual(stats["payloads"], 0)

    def test_disabled(self):
        html = "document.writeln(a.b('%s'))" % b64("<p>x</p>")
        out, stats = predecode(html, enabled=False)
        self.assertEqual(stats["payloads"], 0)

    def test_rejects_non_text_payload(self):
        """解码结果不像文本时不应替换（防误伤）。"""
        self.assertIsNone(_decode_payload(base64.b64encode(b"\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09\x0a\x0b\x0c").decode()))

    def test_real_fixture_bqgbe_chapter(self):
        """真实页面回归：bqgbe 章节页应还原出成段正文。"""
        html = read_fixture("bqgbe_chapter.html")
        out, stats = predecode(html)
        self.assertGreater(stats["payloads"], 20, "真实页应有 20+ 段 base64")
        from bs4 import BeautifulSoup
        ps = BeautifulSoup(out, "lxml").select("div.word_read p")
        self.assertGreater(len(ps), 20)
        text = "".join(p.get_text() for p in ps)
        cjk = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
        self.assertGreater(cjk, 500, "还原正文应以中文为主")


if __name__ == "__main__":
    unittest.main()
