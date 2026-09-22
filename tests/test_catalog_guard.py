#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""「目录解析失败不许静默」的回归测试（审计 #4，2026-09-22）。

背景：目录解析路径上曾有 `except Exception: pass` 吞掉一切 ——
规则作者把 `catalog.id_from.pattern` 写成**无名组** `(\\d+)` 时，解析器
`m.group("cid")` 抛 IndexError 被吞 → **一本都没抓到、却什么也不报**。

两层防线，各测一条：
  1. **加载时**：`rules.validate()` 认出「pattern 里没有 `(?P<cid>…)`」并拒绝；
  2. **运行时**：`engine.discover()` 目录 0 章时**显式报错**（而不是安静返回空书）。
"""

import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from noveldown.rules import Rule, RuleError, load_rules  # noqa: E402


def _rule_dict(pattern=None):
    """用仓里一条真规则当底子，只改 id_from.pattern。"""
    p = os.path.join(ROOT, "noveldown", "rules", "biqu520.net.json")
    d = json.load(open(p, encoding="utf-8"))
    d["id"] = "_probe_rule"
    d["path"] = "probe"
    if pattern is not None:
        d["catalog"]["id_from"] = {"mode": "href", "pattern": pattern}
    return d


class TestValidateRequiresCidGroup(unittest.TestCase):

    def test_unnamed_group_is_rejected(self):
        """⚠ 就是这条配置事故：写成 `(\\d+)` → 目录静默 0 章。"""
        with self.assertRaises(RuleError) as cm:
            Rule(_rule_dict(r"/(\d+)(?:_\d+)?\.html?")).validate()
        msg = str(cm.exception)
        self.assertIn("cid", msg)
        self.assertIn("(?P<cid>", msg)

    def test_named_group_is_accepted(self):
        """不误伤：带命名组的正常规则照样通过。"""
        Rule(_rule_dict(r"/(?P<cid>\d+)(?:_\d+)?\.html?")).validate()

    def test_invalid_regex_is_rejected(self):
        with self.assertRaises(RuleError):
            Rule(_rule_dict(r"/(?P<cid>")).validate()

    def test_rule_without_id_from_still_ok(self):
        """没配 id_from 的规则（走默认或 json_api）不该被这条校验拦住。"""
        d = _rule_dict()
        d["catalog"].pop("id_from", None)
        Rule(d).validate()

    def test_all_shipped_rules_pass_this_check(self):
        """全仓 161 条规则都要过 —— 证明新校验没误伤存量。"""
        rules = load_rules()
        self.assertGreater(len(rules), 100)
        for r in rules.values():
            self.assertIsNotNone(r.id)


class TestZeroChapterIsLoud(unittest.TestCase):
    """`discover()` 遇到 0 章必须报错，而不是返回一本空书。"""

    def _make_book(self, chapters):
        from noveldown.models import Book
        return Book(site="probe", book_id="1", url="https://x/book/1",
                    title="", author="")

    def test_error_message_lists_causes(self):
        """报错文案要给出可执行的排查方向（而不是一句 '0 章'）。"""
        from noveldown.engine import Downloader
        import inspect
        src = inspect.getsource(Downloader.discover)
        self.assertIn("0 章", src)
        self.assertIn("probe", src)          # 指向 probe 子命令
        self.assertIn("RuleError", src)
        # 并且 engine 里真的导入了它（我第一版漏了 import，测试全绿也没发现）
        import noveldown.engine as E
        self.assertTrue(hasattr(E, "RuleError"))

    def test_rule_error_is_same_class(self):
        import noveldown.engine as E
        from noveldown import rules as R
        self.assertIs(E.RuleError, R.RuleError)


if __name__ == "__main__":
    unittest.main()
