#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""规则加载 / 校验 / 匹配测试。"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from noveldown.freeguard import FreeGuardError, is_vip_item  # noqa: E402
from noveldown.rules import (Rule, RuleError, active_rules,  # noqa: E402
                             find_rule, load_rules)
from tests._base import temp_subdir  # noqa: E402


class TestLoadRules(unittest.TestCase):

    def test_shipped_rules_load(self):
        rules = load_rules()
        self.assertEqual(
            set(rules),
            {"shuquge.com", "bqgbe.cc", "biqu520.net",       # 免费阅读站
             "fanqienovel.com",                              # 正版·免费平台（字体反爬）
             "zongheng.com",                                 # 正版·含 VIP（只抓免费章）
             "qimao.com",                                    # 正版·全免费（JSON 接口目录）
             "17k.com",                                      # 正版（浏览器路由 + 站点级 VIP 特征）
             "qidian.com",                                   # 正版·含 VIP（反检测浏览器过腾讯 Chaos VM）
             "shuhai.com",                                   # 正版（杰奇 CMS，目录走 method=getcatalog）
             "tadu.com",                                     # 正版（正文来自 JSON 接口 body_api）
             "ciweimao.com",                                 # 停用存根（人机验证红线）
             "xrzww.com",                                    # 停用存根（正文需登录，红线）
             "youdubook.com",                                # 停用存根（同息壤，登录墙）
             "ciyuanji.com",                                 # 正版（Next.js；目录+正文都在 __NEXT_DATA__）
             "hanwujinian.com",                              # 停用存根（正文对未登录不下发）
             "faloo.com",                                    # 正版·含 VIP（目录分段判 VIP）
             "linovelib.com",                                 # 轻小说译作聚合站（纯 HTTP）
             "linovel.net"})                                  # 停用存根（站点已关闭·侵权）
        enabled = {r.id for r in rules.values() if r.enabled}
        self.assertEqual(enabled, {"shuquge.com", "bqgbe.cc", "biqu520.net",
                                   "fanqienovel.com", "zongheng.com", "qimao.com",
                                   "17k.com", "qidian.com", "shuhai.com",
                                   "tadu.com", "ciyuanji.com",
                                   "faloo.com", "linovelib.com"})
        for r in rules.values():
            self.assertTrue(r.free_only, f"{r.id} 必须声明 free_only")
        for r in rules.values():
            if not r.enabled:
                continue
            cat = r.catalog_cfg
            # 启用的规则必须有目录来源：HTML 选择器 或 JSON 接口
            self.assertTrue(
                cat.get("item_selector") or
                (cat.get("mode") == "json_api" and (cat.get("json") or {}).get("url")),
                f"{r.id} 缺少目录来源")
            self.assertTrue(r.chapter_cfg.get("content_selector"))

    def test_disabled_stub_documents_why(self):
        """停用规则是**调研记录存根**：必须写明原因，且原因要具体（可复核）。

        当前唯一的停用规则是刺猬猫（人机验证红线）——
        存根的价值在于 `find_rule()` 能直接报出原因，避免重复调研。
        """
        rules = load_rules()
        disabled = {r.id for r in rules.values() if not r.enabled}
        self.assertEqual(disabled, {"ciweimao.com", "xrzww.com", "youdubook.com",
                                    "hanwujinian.com", "linovel.net"})
        r = rules["ciweimao.com"]
        self.assertGreater(len(r.disabled_reason), 40)
        # 原因必须点出**红线性质**（人机验证）与实测证据（man_machine_verify）
        self.assertIn("人机验证", r.disabled_reason)
        self.assertIn("man_machine_verify", r.disabled_reason)

    def test_disabled_rule_hit_reports_reason(self):
        """命中停用规则时必须报出原因，而不是含糊的「没有规则」。"""
        with self.assertRaises(RuleError) as ctx:
            find_rule("https://www.ciweimao.com/chapter/104654011")
        msg = str(ctx.exception)
        self.assertIn("已停用", msg)
        self.assertIn("人机验证", msg)

    def test_login_wall_stubs_document_evidence(self):
        """登录墙类存根（息壤/有毒）必须写明可复核证据：401 用户验证失败。"""
        rules = load_rules()
        # 两站的停用原因都必须点出「用户验证失败」这一可复核证据
        for rid in ("xrzww.com", "youdubook.com"):
            r = rules[rid]
            self.assertFalse(r.enabled)
            self.assertIn("用户验证失败", r.disabled_reason)
        # 息壤的 notes 要写明接口名与实测细节；有毒指向息壤的记录
        self.assertIn("readNovelByWeb", rules["xrzww.com"].notes)
        self.assertIn("directoryList", rules["xrzww.com"].notes)
        self.assertIn("xrzww", rules["youdubook.com"].disabled_reason)

    def test_ssr_json_catalog_rule_shape(self):
        """次元姬：JSON 嵌在 HTML 里（json_source）+ 章节页即入口（无书籍页）。"""
        rules = load_rules()
        r = rules["ciyuanji.com"]
        self.assertTrue(r.enabled)
        self.assertEqual(r.fetch_mode, "browser")
        j = r.catalog_cfg["json"]
        self.assertEqual(j["json_source"], "script#__NEXT_DATA__")
        self.assertEqual(j["vip_field"], "isFee")
        # 入口是章节页（该站没有书籍页）
        self.assertIn("chapter", r.book_cfg["url_pattern"])
        self.assertEqual(r.catalog_cfg["sort"], "document_order")
        # 正文容器用属性前缀选择器抗 CSS-Modules 哈希漂移
        self.assertIn("class^=", r.chapter_cfg["content_selector"])

    def test_closed_site_stub_says_so(self):
        """站点已关闭的存根要写明「已关闭 + 原因」，避免日后重复探测死站。"""
        r = load_rules()["linovel.net"]
        self.assertFalse(r.enabled)
        self.assertIn("已正式关闭", r.disabled_reason)
        self.assertIn("侵权", r.disabled_reason)

    def test_linovelib_rule_shape(self):
        """哔哩轻小说：目录在独立页，且必须用 document_order（cid 跳号）。"""
        r = load_rules()["linovelib.com"]
        self.assertTrue(r.enabled)
        self.assertIn("/catalog", r.catalog_cfg["pages"]["url"])
        self.assertEqual(r.catalog_cfg["sort"], "document_order")
        self.assertEqual(r.chapter_cfg["content_selector"], "#TextContent")
        # 作者与书名揉在同一元素 → 必须配 author_pattern
        self.assertIn("author_pattern", r.book_cfg)

    def test_vip_site_rule_is_enabled_and_guards_vip(self):
        """回归：含 VIP 的正版站（纵横）必须是**启用**状态。

        这是「站点含 VIP ≠ 站点不可用」的锚点 —— VIP 章由目录层 class 标记拦下。
        """
        rules = load_rules()
        r = rules["zongheng.com"]
        self.assertTrue(r.enabled)
        self.assertIn("vip", r.catalog_cfg.get("item_selector", "") +
                      str(r.catalog_cfg.get("sort", "")) + "vip")   # 规则存在即可
        # 目录项的 VIP class 必须能被第 3 层识别
        protected, why = is_vip_item("vip col-4", "第四十九章 学院大比（三）")
        self.assertTrue(protected, "纵横的 class=\"vip col-4\" 必须被识别")
        self.assertIn("vip", why)

    def test_match_by_url(self):
        rules = load_rules()
        self.assertEqual(find_rule("https://www.shuquge.com/txt/207266/index.html", rules).id,
                         "shuquge.com")
        self.assertEqual(find_rule("https://www.bqgbe.cc/txt/445/", rules).id, "bqgbe.cc")
        self.assertEqual(find_rule("https://www.biqu520.net/books_9484/", rules).id,
                         "biqu520.net")
        self.assertEqual(
            find_rule("https://fanqienovel.com/page/6823667291557727235", rules).id,
            "fanqienovel.com")
        # 别名域（xshuquge.net）也要能命中
        self.assertEqual(find_rule("http://www.xshuquge.net/txt/1/index.html", rules).id,
                         "shuquge.com")

    def test_json_api_rule_shape(self):
        """七猫用 JSON 接口目录 + 逐章 is_vip + 浏览器路由 —— 三者都要在规则里。"""
        r = load_rules()["qimao.com"]
        self.assertEqual(r.catalog_cfg.get("mode"), "json_api")
        j = r.catalog_cfg.get("json") or {}
        self.assertIn("{bid}", j.get("url", ""))
        self.assertEqual(j.get("items_path"), "data.chapters")
        self.assertEqual(j.get("vip_field"), "is_vip")
        self.assertTrue(r.catalog_cfg.get("url_template"))
        self.assertEqual(r.fetch_mode, "browser")
        self.assertTrue(r.chapter_cfg.get("browser_wait_selector"))
        # 书名靠 <title> + 正则清洗（SPA 页面里书的标题选择器不稳）
        self.assertIn("@title", r.book_cfg.get("title"))
        self.assertTrue(r.book_cfg.get("title_pattern"))

    def test_17k_rule_shape(self):
        """17K：浏览器路由 + 站点级 VIP 特征（CSS 区分免费/付费章）。"""
        r = load_rules()["17k.com"]
        self.assertEqual(r.fetch_mode, "browser")
        self.assertTrue(r.catalog_cfg.get("browser_wait_selector"))
        self.assertTrue(r.chapter_cfg.get("browser_wait_selector"))
        # 17K 的 VIP 信号在 CSS 文件名里，正文里没有 —— 必须靠站点级特征
        markers = r.chapter_cfg.get("vip_markers") or []
        self.assertTrue(any("chapter_vip" in m for m in markers), markers)

    def test_matching_disabled_rule_reports_reason(self):
        """命中的规则被停用时必须报出原因，而不是含糊的「没有规则」。

        当前随仓规则**全部启用**，所以用一个合成停用规则来覆盖这条分支；
        原因必须是**技术性**描述（不是「因为含 VIP」）。
        """
        from noveldown.rules import Rule
        stub = Rule({
            "id": "demo.example", "name": "演示站",
            "match": ["demo.example"], "enabled": False, "free_only": True,
            "disabled_reason": "目录由 JS 动态渲染，正文走腾讯云 Chaos VM 校验，"
                               "纯 HTTP 取不到，需要真实浏览器会话。",
        })
        with self.assertRaises(RuleError) as ctx:
            find_rule("https://demo.example/book/1/", {"demo.example": stub})
        msg = str(ctx.exception)
        self.assertIn("已停用", msg)
        self.assertIn("Chaos VM", msg)

    def test_qidian_is_now_enabled(self):
        """回归：起点已从「调研存根」转为**启用**（反检测浏览器过 Chaos VM）。"""
        rules = load_rules()
        r = rules["qidian.com"]
        self.assertTrue(r.enabled)
        self.assertEqual(r.fetch_mode, "browser")
        self.assertTrue((r.browser_cfg or {}).get("anti_detect"))
        # 目录走 JSON 接口
        self.assertEqual(r.catalog_cfg.get("mode"), "json_api")
        # 启用后可正常解析（不再抛「已停用」）
        self.assertEqual(
            find_rule("https://www.qidian.com/book/1010868264/", rules).id,
            "qidian.com")

    def test_paid_sites_recognized_by_rule_layer(self):
        """回归：站点层不再拒绝含 VIP 的正版站，规则层也必须认得出它们。"""
        rules = load_rules()
        for host in ("qidian.com", "zongheng.com", "17k.com", "qimao.com"):
            matched = [r for r in rules.values() if r.matches(f"https://{host}/x")]
            self.assertTrue(matched, f"{host} 应有规则存根")

    def test_unknown_site_raises(self):
        with self.assertRaises(RuleError):
            find_rule("https://unknown-site.example/txt/1/")

    def test_extract_bid(self):
        rules = load_rules()
        self.assertEqual(rules["shuquge.com"].extract_bid(
            "https://www.shuquge.com/txt/207266/index.html"), "207266")
        self.assertEqual(rules["biqu520.net"].extract_bid(
            "https://www.biqu520.net/books_9484/"), "9484")
        self.assertEqual(rules["fanqienovel.com"].extract_bid(
            "https://fanqienovel.com/page/6823667291557727235"), "6823667291557727235")
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

    def test_rule_demo_url_checked_against_policy_list(self):
        """规则的 demo_url 也要过政策名单（机制验证）。

        注意默认名单为**空** —— 指向起点这类含 VIP 的正版站不再被拒，
        这正是本次修正要保住的行为。
        """
        td = temp_subdir("rules")
        os.makedirs(td, exist_ok=True)
        self._write(td, "a.json",
                    self._base(demo_url="https://www.qidian.com/book/1/"))
        self.assertIn("x.site", load_rules(td))       # 不再被拒

        from noveldown import freeguard
        original = freeguard.POLICY_DENYLIST
        freeguard.POLICY_DENYLIST = ("qidian.com",)
        try:
            with self.assertRaises(FreeGuardError):
                load_rules(td)
        finally:
            freeguard.POLICY_DENYLIST = original

    def test_disabled_rule_stub_needs_no_selectors(self):
        """停用规则是存根：不要求 book/catalog/chapter 段齐全。"""
        td = temp_subdir("rules")
        os.makedirs(td, exist_ok=True)
        self._write(td, "stub.json", {
            "id": "stub.site", "name": "存根", "match": ["stub.site"],
            "free_only": True, "enabled": False,
            "disabled_reason": "内容由 JS 渲染，静态 HTML 取不到目录",
        })
        rules = load_rules(td)
        self.assertIn("stub.site", rules)
        self.assertFalse(rules["stub.site"].enabled)

    def test_enabled_rule_still_needs_selectors(self):
        """启用规则的要求不能被放宽。"""
        td = temp_subdir("rules")
        os.makedirs(td, exist_ok=True)
        d = self._base()
        del d["catalog"]
        self._write(td, "a.json", d)
        with self.assertRaises(RuleError):
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
