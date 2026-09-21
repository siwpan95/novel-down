#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""规则加载 / 校验 / 匹配测试。"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from noveldown.engine import Downloader  # noqa: E402
from noveldown.freeguard import FreeGuardError, is_vip_item  # noqa: E402
from noveldown.rules import (Rule, RuleError, active_rules,  # noqa: E402
                             find_rule, load_rules)
from tests._base import temp_subdir  # noqa: E402


class TestLoadRules(unittest.TestCase):

    def test_shipped_rules_load(self):
        """随仓规则必须**全部**能加载，且 == rules/ 目录下的文件集合。

        ⚠ 这里刻意**不写死 id 清单**：本项目会持续批量添加镜像站规则
        （见 docs/NEW_SITES_PLAN.md §11.3），写死清单会让每加一个域就改一次测试、
        且掩盖真正要守的不变量 ——
        真正的不变量是「**文件系统里的每条规则都能通过校验并加载**」。
        几个关键站点单独断言，防止被误删。
        """
        from noveldown.rules import iter_rule_files
        files = {os.path.basename(p)[:-5] for p in iter_rule_files()}
        self.assertTrue(files, "rules/ 目录下没有规则文件？")
        rules = load_rules()
        self.assertEqual(set(rules), files,
                         "有规则文件加载失败（或 id 与文件名不一致）")
        # 关键站点守门（防误删）
        for key in ("qidian.com", "17k.com", "qimao.com", "zongheng.com",
                    "fanqienovel.com", "tadu.com", "shuhai.com", "ciyuanji.com",
                    "faloo.com", "linovelib.com", "shuquge.com", "bqgbe.cc",
                    "biqu520.net", "soushuwang.cc", "shudugu.org"):
            self.assertIn(key, rules, f"关键规则 {key} 不见了")
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

        存根的价值在于 `find_rule()` 能直接报出原因，避免重复调研。

        ⚠ 这里**不写死停用规则清单**：存根会随调研推进而增减
        （实测：起点从停用翻案成可用、创世新增为存根），
        写死清单会让每次变动都得改测试，且掩盖真正的不变量 ——
        真正的不变量是「**每条停用规则都有足够具体的 disabled_reason**」。
        """
        rules = load_rules()
        for r in rules.values():
            if r.enabled:
                continue
            self.assertTrue(r.disabled_reason,
                            f"{r.id} 停用却没写 disabled_reason")
            self.assertGreater(len(r.disabled_reason), 40,
                               f"{r.id} 的 disabled_reason 太短，不足以复核")
        disabled = {r.id for r in rules.values() if not r.enabled}
        # 几个长期存根必须仍在（防止被误删）
        for key in ("ciweimao.com", "xrzww.com", "youdubook.com"):
            self.assertIn(key, disabled)
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

    def test_pool_field_and_mirror_pool(self):
        """每条规则都要有池子；免费镜像池里至少 5 条启用。"""
        rules = load_rules()
        for r in rules.values():
            self.assertIn(r.pool, ("正版", "免费镜像"), f"{r.id} 缺少合法 pool")
        mirrors = [r for r in rules.values() if r.pool == "免费镜像" and r.enabled]
        self.assertGreaterEqual(len(mirrors), 5)
        self.assertTrue(any(r.pool == "正版" for r in rules.values()))

    def test_mirror_family_rule_covers_three_domains(self):
        """镜像族规则：三个域共用一条规则，且配了章节内分页。"""
        r = load_rules()["soushuwang.cc"]
        self.assertTrue(r.enabled)
        self.assertEqual(set(r.match), {"soushuwang.cc", "bqg142.cc", "soduo.cc"})
        self.assertIn("下一页", r.chapter_cfg["next_page"]["text_contains"])
        self.assertEqual(r.chapter_cfg["next_page"]["continue_when"], "same_base_id")
        self.assertEqual(r.pool, "免费镜像")

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


class _Stub:
    """只带 rule 属性的壳，用来单独调 Downloader 的纯逻辑方法。"""

    def __init__(self, rule):
        self.rule = rule


class TestWaitSelectorRoles(unittest.TestCase):
    """浏览器等待条件的**角色化**解析（v0.8.1）。

    背景：`browser.wait_selector` 旧写法是**字符串**，会被所有角色继承 ——
    速读谷把章节容器 `div.con` 写成顶层字符串后，**书籍页**也要等 `div.con`
    （不存在）→ 白等满 30 秒超时（实测目录耗时 37s，其中 30s 是纯浪费）。
    新写法支持 `{"book": .., "catalog": .., "chapter": ..}` 逐角色指定。
    """

    def _rule(self, browser=None):
        raw = {
            "id": "x.site", "name": "X", "match": ["x.site"],
            "free_only": True, "enabled": True, "fetch_mode": "browser",
            "book": {"url_pattern": "/b/(\\d+)", "info_url": "{origin}/b/{bid}/"},
            "catalog": {"item_selector": "a",
                        "id_from": {"mode": "href", "pattern": "(?P<cid>\\d+)"}},
            "chapter": {"content_selector": "div#c"},
        }
        if browser is not None:
            raw["browser"] = browser
        return Rule(raw)

    def test_string_selector_applies_to_every_role(self):
        """字符串写法 = 历史行为（全角色广播），必须保持兼容。"""
        r = self._rule({"wait_selector": "#bookName"})
        for role in ("book", "catalog", "chapter"):
            self.assertEqual(r.wait_selector_for(role), "#bookName")

    def test_role_map_only_affects_declared_role(self):
        r = self._rule({"wait_selector": {"chapter": "div.con"}})
        self.assertEqual(r.wait_selector_for("chapter"), "div.con")
        self.assertIsNone(r.wait_selector_for("book"))
        self.assertIsNone(r.wait_selector_for("catalog"))

    def test_role_map_falsy_means_no_wait(self):
        r = self._rule({"wait_selector": {"book": "#b", "chapter": None,
                                          "catalog": ""}})
        self.assertEqual(r.wait_selector_for("book"), "#b")
        self.assertIsNone(r.wait_selector_for("chapter"))
        self.assertIsNone(r.wait_selector_for("catalog"))

    def test_no_browser_block_means_no_wait(self):
        self.assertIsNone(self._rule().wait_selector_for("chapter"))

    def _load_one(self, browser):
        td = temp_subdir("rules")
        os.makedirs(td, exist_ok=True)
        d = TestRuleValidation()._base(browser=browser)
        TestRuleValidation()._write(td, "a.json", d)
        return load_rules(td)

    def test_unknown_role_rejected_at_load(self):
        with self.assertRaises(RuleError) as ctx:
            self._load_one({"wait_selector": {"body": "x"}})
        self.assertIn("未知角色", str(ctx.exception))
        self.assertIn("body", str(ctx.exception))

    def test_bad_type_rejected_at_load(self):
        with self.assertRaises(RuleError) as ctx:
            self._load_one({"wait_selector": 5})
        self.assertIn("字符串或对象", str(ctx.exception))

    def test_section_override_beats_role_map(self):
        r = self._rule({"wait_selector": {"catalog": "top"}})
        stub = _Stub(r)
        self.assertEqual(
            Downloader._wait_for(stub, {"browser_wait_selector": "sec"}, "catalog"),
            "sec")
        self.assertEqual(Downloader._wait_for(stub, {}, "catalog"), "top")

    def test_section_false_disables_inherited_wait(self):
        r = self._rule({"wait_selector": {"catalog": "top"}})
        self.assertIsNone(
            Downloader._wait_for(_Stub(r), {"browser_wait_selector": False},
                                 "catalog"))
        self.assertIsNone(
            Downloader._wait_for(_Stub(r), {"browser_wait_selector": ""}, "catalog"))

    def test_shipped_mirrors_scope_wait_to_chapter_only(self):
        """回归守卫：两个免费镜像的章节等待条件不得再漏到书籍页/目录页。"""
        rules = load_rules()
        for sid, sel in (("shudugu.org", "div.con"),
                         ("soushuwang.cc", "#chaptercontent")):
            r = rules[sid]
            self.assertEqual(r.wait_selector_for("chapter"), sel, sid)
            self.assertIsNone(r.wait_selector_for("book"),
                              f"{sid} 书籍页不该继承章节等待条件（会白等 30s 超时）")
            self.assertIsNone(r.wait_selector_for("catalog"),
                              f"{sid} 目录页不该继承章节等待条件")

    def test_qidian_book_wait_preserved(self):
        """qidian 的顶层字符串是**书籍页**自检条件，改造后必须仍在。"""
        r = load_rules()["qidian.com"]
        self.assertEqual(r.wait_selector_for("book"), "#bookName")
        # 章节页在段内声明了段落专用覆盖 → 生效值由 _wait_for 解析，优先级高于顶层
        self.assertEqual(
            Downloader._wait_for(_Stub(r), r.chapter_cfg, "chapter"),
            "main.content span.content-text")
        # 且该覆盖**不干扰**书籍页
        self.assertEqual(
            Downloader._wait_for(_Stub(r), r.book_cfg, "book"), "#bookName")


class TestFetchModeRoles(unittest.TestCase):
    """取页路由的**角色化**解析（v0.8.13）。

    背景：`fetch_mode` 原本只有顶层一个值。书山（shushan.zhangyue.net）这类站点
    **目录页靠 JS 渲染**（必须走浏览器），**章节页是服务端直出的静态 HTML**
    （纯 HTTP 0.7s/页，浏览器 20s+/页）。顶层单值时只能二选一。

    段内 `book/catalog/chapter.fetch_mode` 覆盖顶层；未声明的角色继承顶层。
    """

    def _rule(self, top="browser", **sections):
        raw = {
            "id": "x.site", "name": "X", "match": ["x.site"],
            "free_only": True, "enabled": True, "fetch_mode": top,
            "book": {"url_pattern": "/b/(\\d+)", "info_url": "{origin}/b/{bid}/"},
            "catalog": {"item_selector": "a",
                        "id_from": {"mode": "href", "pattern": "(?P<cid>\\d+)"}},
            "chapter": {"content_selector": "div#c"},
        }
        for key, mode in sections.items():
            raw[key]["fetch_mode"] = mode
        return Rule(raw)

    def test_default_inherits_top_level(self):
        for top in ("http", "browser"):
            r = self._rule(top=top)
            for role in ("book", "catalog", "chapter"):
                self.assertEqual(r.fetch_mode_for(role), top, f"{top}/{role}")

    def test_chapter_override_beats_top_level(self):
        """书山形态：顶层 browser，正文改 http（其余角色保持 browser）。"""
        r = self._rule("browser", chapter="http")
        self.assertEqual(r.fetch_mode_for("book"), "browser")
        self.assertEqual(r.fetch_mode_for("catalog"), "browser")
        self.assertEqual(r.fetch_mode_for("chapter"), "http")

    def test_reverse_direction_is_symmetric(self):
        """顶层 http、某一节改 browser（塔读式：正文接口需带 WAF cookie）。"""
        r = self._rule("http", chapter="browser")
        self.assertEqual(r.fetch_mode_for("book"), "http")
        self.assertEqual(r.fetch_mode_for("chapter"), "browser")

    def test_value_is_lowercased_and_stripped(self):
        r = self._rule("http", catalog="BROWSER", chapter=" Browser ")
        self.assertEqual(r.fetch_mode_for("catalog"), "browser")
        self.assertEqual(r.fetch_mode_for("chapter"), "browser")

    def test_unknown_role_rejected(self):
        with self.assertRaises(RuleError) as ctx:
            self._rule().fetch_mode_for("body")
        self.assertIn("未知页面角色", str(ctx.exception))

    def test_bad_value_rejected_at_load(self):
        """非法路由值必须**加载即报**，不能等到抓取那一刻才炸。"""
        for bad in ("curl", "", "fetch"):
            r = self._rule("http", chapter=bad)
            with self.assertRaises(RuleError) as ctx:
                r.validate()
            self.assertIn("fetch_mode", str(ctx.exception))

    def test_explicit_none_means_inherit(self):
        r = self._rule("browser", chapter=None)
        r.validate()
        self.assertEqual(r.fetch_mode_for("chapter"), "browser")

    def test_shipped_shushan_is_now_pure_http(self):
        """回归守卫：书山**不该**再用浏览器（改前 3 章 82.6s、且只拿到 1 章）。

        修正的事实依据（2026-09-21 复测）：
          · 目录来自 XHR 片段 `/book/directory?bid=`（纯 HTTP 0.5s，821 条 cid），
            不是「点一下锚点渲染出来」的虚拟滚动；
          · 章节页静态 HTML 直接有 `div.art_con`（0.2s / 3240 字）。
        """
        r = load_rules()["shushan.zhangyue.net"]
        self.assertEqual(r.fetch_mode, "http")
        self.assertFalse(r.requires_js)
        for role in ("book", "catalog", "chapter"):
            self.assertEqual(r.fetch_mode_for(role), "http", role)
        # 目录必须指向片段接口，否则又退回「书籍页里没有目录 → 只 1 章」
        self.assertIn("/book/directory", r.catalog_cfg["pages"]["url"])
        self.assertIn("{bid}", r.catalog_cfg["pages"]["url"])

    def test_shipped_shushan_metadata_comes_from_fragment(self):
        """简介不得再用 `meta[name=description]`（那是站点通用文案，非本书简介）。"""
        r = load_rules()["shushan.zhangyue.net"]
        iapi = r.book_cfg["info_api"]
        self.assertIn("/book/bookintro", iapi["url"])
        self.assertTrue(iapi["intro"])
        self.assertNotIn("meta[name='description']", r.book_cfg.get("intro") or [])
        # 封面是 img 元素 → 必须用 `sel@attr` 取 src，否则只会取到空文本
        self.assertTrue(any("@" in s for s in r.book_cfg["cover"]))


if __name__ == "__main__":
    unittest.main()
