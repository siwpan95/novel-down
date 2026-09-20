#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""规则加载 / 校验 / 匹配测试。"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from noveldown.freeguard import FreeGuardError  # noqa: E402
from noveldown.rules import (Rule, RuleError, active_rules,  # noqa: E402
                             find_rule, load_rules)
from tests._base import temp_subdir  # noqa: E402


class TestLoadRules(unittest.TestCase):

    def test_shipped_rules_load(self):
        rules = load_rules()
        self.assertEqual(set(rules), {"shuquge.com", "bqgbe.cc", "biqu520.net"})
        for r in rules.values():
            self.assertTrue(r.free_only)
            self.assertTrue(r.enabled)
            self.assertFalse(r.requires_js)
            self.assertTrue(r.catalog_cfg.get("item_selector"))
            self.assertTrue(r.chapter_cfg.get("content_selector"))

    def test_match_by_url(self):
        rules = load_rules()
        self.assertEqual(find_rule("https://www.shuquge.com/txt/207266/index.html", rules).id,
                         "shuquge.com")
        self.assertEqual(find_rule("https://www.bqgbe.cc/txt/445/", rules).id, "bqgbe.cc")
        self.assertEqual(find_rule("https://www.biqu520.net/books_9484/", rules).id,
                         "biqu520.net")
        # 别名域（xshuquge.net）也要能命中
        self.assertEqual(find_rule("http://www.xshuquge.net/txt/1/index.html", rules).id,
                         "shuquge.com")

    def test_paid_site_rejected_before_matching(self):
        with self.assertRaises(FreeGuardError):
            find_rule("https://www.qidian.com/book/1010868264/")

    def test_unknown_site_raises(self):
        with self.assertRaises(RuleError):
            find_rule("https://unknown-site.example/txt/1/")

    def test_extract_bid(self):
        rules = load_rules()
        self.assertEqual(rules["shuquge.com"].extract_bid(
            "https://www.shuquge.com/txt/207266/index.html"), "207266")
        self.assertEqual(rules["biqu520.net"].extract_bid(
            "https://www.biqu520.net/books_9484/"), "9484")
        self.assertIsNone(rules["bqgbe.cc"].extract_bid("https://www.bqgbe.cc/"))

    def test_book_page_url(self):
        rules = load_rules()
        r = rules["shuquge.com"]
        self.assertEqual(
            r.book_page_url("https://www.shuquge.com/txt/207266/index.html", "207266"),
            "https://www.shuquge.com/txt/207266/index.html")
        r2 = rules["bqgbe.cc"]
        self.assertEqual(
            r2.book_page_url("https://www.bqgbe.cc/txt/445/ml2.html", "445"),
            "https://www.bqgbe.cc/txt/445/")


class TestRuleValidation(unittest.TestCase):

    def _write(self, td, name, obj):
        p = os.path.join(td, name)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False)
        return p

    def _base(self, **over):
        d = {
            "id": "x.site", "name": "X", "match": ["x.site"], "free_only": True,
            "book": {"url_pattern": "/b/(\\d+)/", "info_url": "{origin}/b/{bid}/"},
            "catalog": {"item_selector": "a", "id_from": {"mode": "href", "pattern": "(?P<cid>\\d+)"}},
            "chapter": {"content_selector": "div#c"},
        }
        d.update(over)
        return d

    def test_free_only_false_is_rejected(self):
        td = temp_subdir("rules")
        os.makedirs(td, exist_ok=True)
        self._write(td, "a.json", self._base(free_only=False))
        with self.assertRaises(RuleError):
            load_rules(td)

    def test_missing_required_field(self):
        td = temp_subdir("rules")
        os.makedirs(td, exist_ok=True)
        d = self._base()
        del d["catalog"]
        self._write(td, "a.json", d)
        with self.assertRaises(RuleError):
            load_rules(td)

    def test_empty_item_selector(self):
        td = temp_subdir("rules")
        os.makedirs(td, exist_ok=True)
        d = self._base()
        d["catalog"]["item_selector"] = ""
        self._write(td, "a.json", d)
        with self.assertRaises(RuleError):
            load_rules(td)

    def test_rule_pointing_at_paid_site_is_rejected(self):
        """规则自带 demo_url 也不能指向付费站。"""
        td = temp_subdir("rules")
        os.makedirs(td, exist_ok=True)
        self._write(td, "a.json",
                    self._base(demo_url="https://www.qidian.com/book/1/"))
        with self.assertRaises(FreeGuardError):
            load_rules(td)

    def test_non_strict_collects_errors_and_skips(self):
        td = temp_subdir("rules")
        os.makedirs(td, exist_ok=True)
        self._write(td, "bad.json", self._base(id="bad", free_only=False))
        self._write(td, "good.json", self._base())
        rules = load_rules(td, strict=False)
        self.assertEqual(set(rules), {"x.site"})
        self.assertEqual(len(load_rules.errors), 1)

    def test_valid_rule_loads(self):
        td = temp_subdir("rules")
        os.makedirs(td, exist_ok=True)
        self._write(td, "a.json", self._base())
        rules = load_rules(td)
        self.assertIn("x.site", rules)
        self.assertEqual(active_rules(rules)["x.site"].enabled, True)

    def test_disabled_rule_excluded_from_active(self):
        td = temp_subdir("rules")
        os.makedirs(td, exist_ok=True)
        self._write(td, "a.json", self._base(enabled=False))
        rules = load_rules(td)
        self.assertEqual(active_rules(rules), {})


if __name__ == "__main__":
    unittest.main()
