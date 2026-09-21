#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""目录归一化 / 目录页发现 / 正文提取测试。"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from noveldown.parser import (body_api_fragment, catalog_links_from_page,  # noqa: E402
                              clean_page_title, collect_catalog_items,
                              collect_json_catalog,
                              extract_paragraphs, make_soup,
                              normalize_catalog, parse_book_info,
                              parse_chapter_page)
from noveldown.rules import RuleError, load_rules  # noqa: E402
from tests._base import read_fixture  # noqa: E402

RULES = load_rules()


class TestCatalogNormalize(unittest.TestCase):
    """核心归一化：去重 + 升序 + 编号。"""

    def test_dedupes_latest_echo_and_sorts(self):
        """「最新章节倒序回显」必须被去掉，且顺序按章节号升序。"""
        items = [
            {"cid": "305", "title": "第3章", "url": "u305"},
            {"cid": "304", "title": "第2章", "url": "u304"},
            {"cid": "303", "title": "第1章", "url": "u303"},
            {"cid": "303", "title": "第1章", "url": "u303"},
            {"cid": "304", "title": "第2章", "url": "u304"},
            {"cid": "305", "title": "第3章", "url": "u305"},
        ]
        chs = normalize_catalog(items)
        self.assertEqual([c.cid for c in chs], ["303", "304", "305"])
        self.assertEqual([c.index for c in chs], [1, 2, 3])

    def test_merges_multiple_catalog_pages(self):
        """多页目录拼接后仍是唯一且有序的。"""
        p1 = [{"cid": str(1000 + i), "title": f"c{i}", "url": "u"} for i in range(1, 11)]
        p2 = [{"cid": str(1000 + i), "title": f"c{i}", "url": "u"} for i in range(8, 21)]
        chs = normalize_catalog(p1 + p2)
        self.assertEqual(len(chs), 20)
        self.assertEqual([int(c.cid) for c in chs], list(range(1001, 1021)))

    def test_desc_sort_option(self):
        items = [{"cid": "1", "title": "a", "url": "u"},
                 {"cid": "3", "title": "c", "url": "u"},
                 {"cid": "2", "title": "b", "url": "u"}]
        chs = normalize_catalog(items, "cid_numeric_desc")
        self.assertEqual([c.cid for c in chs], ["3", "2", "1"])

    def test_document_order_keep_last_drops_head_echo(self):
        """番茄小说的形态：头部有「最近更新：第N章」回显，与末尾正文条目同 cid。

        章节 ID 是雪花 ID；用 cid 升序会把回显的脏标题排到最后 → 必须
        document_order + keep_last：丢掉头部回显，保住末尾那条干净标题。
        """
        items = [
            {"cid": "700", "title": "最近更新：第3章 终章（完）", "url": "u700"},
            {"cid": "100", "title": "第1章 起", "url": "u100"},
            {"cid": "200", "title": "第2章 承", "url": "u200"},
            {"cid": "700", "title": "第3章 终章（完）", "url": "u700"},
        ]
        chs = normalize_catalog(items, "document_order", "keep_last")
        self.assertEqual([c.title for c in chs],
                         ["第1章 起", "第2章 承", "第3章 终章（完）"])
        self.assertNotIn("最近更新", "".join(c.title for c in chs))

    def test_document_order_keep_first_is_still_available(self):
        """keep_first 仍是默认 —— 回显在尾部时该策略才对。"""
        items = [{"cid": "1", "title": "第1章", "url": "u1"},
                 {"cid": "1", "title": "回显：第1章", "url": "u1"}]
        chs = normalize_catalog(items, "document_order", "keep_first")
        self.assertEqual([c.title for c in chs], ["第1章"])

    def test_default_sort_and_dedupe_unchanged(self):
        """默认参数不得被改动 —— 三个既有站点规则依赖它。"""
        items = [{"cid": "3", "title": "c", "url": "u"},
                 {"cid": "1", "title": "a", "url": "u"},
                 {"cid": "3", "title": "c2", "url": "u"}]
        chs = normalize_catalog(items)
        self.assertEqual([c.cid for c in chs], ["1", "3"])
        self.assertEqual(chs[1].title, "c")     # keep_first

    def test_locked_status_is_carried(self):
        """受保护章节要保留在编号序列里（占位），但状态为 locked。"""
        items = [
            {"cid": "1", "title": "免费章", "url": "u1"},
            {"cid": "2", "title": "VIP章", "url": "u2", "status": "locked", "note": "VIP"},
        ]
        chs = normalize_catalog(items)
        self.assertEqual(chs[1].status, "locked")
        self.assertTrue(chs[1].is_protected)

    def test_clean_page_title(self):
        self.assertEqual(clean_page_title("第一章（第2页）"), "第一章")
        self.assertEqual(clean_page_title("第一章 (第10页)"), "第一章")
        self.assertEqual(clean_page_title("普通标题"), "普通标题")


class TestCatalogFromFixtures(unittest.TestCase):

    def test_shuquge_catalog(self):
        """真实 shuquge 目录：两个 <dt> 分组（含最新章节回显）都要能收集。"""
        html = read_fixture("shuquge_catalog.html")
        rule = RULES["shuquge.com"]
        items, locked = collect_catalog_items(
            rule, html, "https://www.shuquge.com/txt/207266/index.html", "207266")
        self.assertGreater(len(items), 30)
        self.assertEqual(locked, [])
        chs = normalize_catalog(items)
        cids = [int(c.cid) for c in chs]
        self.assertEqual(cids, sorted(cids), "必须升序")
        self.assertEqual(len(cids), len(set(cids)), "必须去重")
        self.assertTrue(all(c.url.startswith("https://") for c in chs))

    def test_biqu520_catalog_uses_onclick(self):
        """biqu520 目录项没有 href，只有 onclick=\"随机函数(id)\"。"""
        html = read_fixture("biqu520_catalog.html")
        rule = RULES["biqu520.net"]
        items, locked = collect_catalog_items(
            rule, html, "https://www.biqu520.net/chapters_9484/1", "9484")
        self.assertEqual(len(items), 40)
        self.assertEqual(locked, [])
        first = items[0]
        self.assertEqual(first["cid"], "7564755")
        self.assertEqual(first["url"],
                         "https://www.biqu520.net/books_9484/7564755.html")
        self.assertIn("第1章", first["title"])

    def test_biqu520_page_discovery_from_select(self):
        html = read_fixture("biqu520_catalog.html")
        rule = RULES["biqu520.net"]
        urls = catalog_links_from_page(
            rule, html, "https://www.biqu520.net/chapters_9484/1", "9484",
            "https://www.biqu520.net")
        self.assertIn("https://www.biqu520.net/chapters_9484/27", urls)
        self.assertFalse(any(u.startswith("javascript:") for u in urls),
                         "伪协议链接必须被过滤")

    def test_biqu520_book_info(self):
        html = read_fixture("biqu520_catalog.html")
        rule = RULES["biqu520.net"]
        info = parse_book_info(rule, html, "https://www.biqu520.net/books_9484/", "9484")
        self.assertIsInstance(info, dict)
        self.assertIn("title", info)


class TestXugesFixtures(unittest.TestCase):
    """虚阁网（v0.8.16 接入）：本仓第一个「文库型」站点。

    三个形状结论被 fixture 钉住：
      · 书 ID 是**路径**（`gdwx/hlm`），books 页与目录页是**同一个 index.htm**；
      · 正文 = `td:not([class])` 的第一个命中（表格布局，锚点 `td.t50` 与正文不同行）；
      · **多页章回**：目录里续页标题只有 `(2)`/`(3)`，须合并进前一章。
    """

    IDX = "https://www.xuges.com/gdwx/hlm/index.htm"

    def test_book_info_from_title_tag(self):
        from noveldown.parser import parse_book_info
        html = read_fixture("xuges_hlm_index.html")
        info = parse_book_info(RULES["xuges.com"], html, self.IDX, "gdwx/hlm")
        self.assertEqual(info["title"], "红楼梦")
        self.assertEqual(info["author"], "曹雪芹")

    def test_title_author_patterns_cover_all_five_shapes(self):
        """`<title>` 有五种实测形态，规则的正则必须都吃对。

        ⚠ 关键是最后两种（**没有作者**）：不设 `author_pattern_strict` 的话，
        `author` 会保留整条 title 当作者名。
        """
        import re
        r = RULES["xuges.com"]
        tpat = r.book_cfg["title_pattern"]
        apat = r.book_cfg["author_pattern"]
        cases = [("红楼梦|曹雪芹_虚阁网", "红楼梦", "曹雪芹"),
                 ("三国演义・三国志通俗演义|罗贯中_虚阁网", "三国演义・三国志通俗演义", "罗贯中"),
                 ("水浒传|水浒全传|施耐庵_虚阁网", "水浒传", "施耐庵"),
                 ("胡适日记胡适日记_虚阁网_虚阁网", "胡适日记胡适日记", ""),
                 ("外国畅销书_虚阁网", "外国畅销书", "")]
        for raw, want_t, want_a in cases:
            m = re.search(tpat, raw)
            self.assertIsNotNone(m, raw)
            got_t = (m.group(1) if m.groups() else m.group(0)).strip()
            self.assertEqual(got_t, want_t, f"title 清洗错：{raw!r}")
            m2 = re.search(apat, raw)
            got_a = (m2.group(1) if m2 else "").strip() if m2 else ""
            self.assertEqual(got_a, want_a, f"author 抽取错：{raw!r}")

    def test_catalog_merges_continuation_pages(self):
        """277 项 → **121 章** = 作者简介 1 + 正文 120 回（红楼梦真实回数）。"""
        html = read_fixture("xuges_hlm_index.html")
        rule = RULES["xuges.com"]
        items, locked = collect_catalog_items(rule, html, self.IDX, "gdwx/hlm")
        self.assertEqual(locked, [])
        self.assertEqual(len(items), 279, "目录原文的编号链接数")
        raw = normalize_catalog(items, rule.catalog_cfg["sort"],
                                rule.catalog_cfg["dedupe"])
        self.assertEqual(len(raw), 277, "不合并时续页会变成假章")
        merged = normalize_catalog(items, rule.catalog_cfg["sort"],
                                   rule.catalog_cfg["dedupe"],
                                   rule.catalog_cfg["continuation_title_pattern"])
        self.assertEqual(len(merged), 121)
        # 续页不再作为独立章出现、标题也不再是纯页码
        import re as _re
        for c in merged:
            self.assertIsNone(_re.match(r"^[（(]\d+[）)]$", c.title),
                              f"仍有纯页码标题的假章：{c.title!r}")
        # 第一回拿到 002/003 两个续页
        c1 = merged[1]
        self.assertEqual(c1.title, "・第一回 甄士隐梦幻识通灵 贾雨村风尘怀闺秀")
        self.assertEqual([u.rsplit("/", 1)[-1] for u in c1.extra_pages],
                         ["002.htm", "003.htm"])
        self.assertEqual(sum(len(c.extra_pages) for c in merged), 156)
        # ⚠ 末章标题里的「○」在**站点数据**里就是替换符（GB2312 装不下生僻字），
        #   所以只能断言可核对的片段 —— 这是站点侧的数据损失，不是我们的 bug
        self.assertTrue(merged[-1].title.startswith("・第一二"))
        self.assertIn("甄士隐详说太虚情", merged[-1].title)

    def test_chapter_content_via_css_only(self):
        """正文用 `td:not([class])` 的第一个命中；且 <br> 分段已被原生支持。"""
        html = read_fixture("xuges_hlm_chapter.html")
        info = parse_chapter_page(RULES["xuges.com"], html,
                                  "https://www.xuges.com/gdwx/hlm/001.htm", "001", "")
        ps = info["paragraphs"]
        self.assertGreater(len(ps), 10, "应被 <br> 切分成多段")
        self.assertTrue(ps[0].startswith("此开卷第一回也"))
        # 导航/页脚不得混进正文
        for nav in ("虚阁网", "上一页", "下一页", "回目录"):
            self.assertNotIn(nav, "\n".join(ps))

    def test_utf8_page_fixture_decodes_cleanly(self):
        """同站 utf-8 页的 fixture：锁住「编码逐页不同，必须按响应头解」。"""
        html = read_fixture("xuges_wgwx_index.html")
        self.assertIn("虚阁网", html)
        self.assertNotIn("澶栧浗鏂囧", html, "utf-8 页被按 gbk 解的乱码指纹")
        self.assertNotIn("\ufffd", html)


class TestContinuationPatternValidation(unittest.TestCase):
    """`catalog.continuation_title_pattern` 的校验（过宽会**静默少章**）。"""

    def _load(self, ctp):
        import json as _json
        import os as _os
        from tests._base import temp_subdir
        td = temp_subdir("rules")
        _os.makedirs(td, exist_ok=True)
        raw = {"id": "x.site", "name": "X", "match": ["x.site"], "free_only": True,
               "book": {"url_pattern": "(\\d+)", "info_url": "{origin}"},
               "catalog": {"item_selector": "a",
                           "id_from": {"mode": "href", "pattern": "(?P<cid>\\d+)"}},
               "chapter": {"content_selector": "div#c"}}
        if ctp is not None:
            raw["catalog"]["continuation_title_pattern"] = ctp
        with open(_os.path.join(td, "a.json"), "w", encoding="utf-8") as f:
            _json.dump(raw, f, ensure_ascii=False)
        return load_rules(td)

    def test_too_broad_pattern_rejected(self):
        """校验保证的三类必须拦下：空模式 / 匹配空串 / 匹配常见标题样本。

        ⚠ 这不是「万能的过宽检测」—— 只覆盖这三类**可机械判定**的情形
        （例如 `^[（(]\d*[）)]$` 允许 `()` 这种懒写法，机械判定抓不到，靠人写规则时自觉）。
        """
        for bad in (".*", "", ".*$", "^$", "第.*章", "序"):
            with self.assertRaises(RuleError) as ctx:
                self._load(bad)
            self.assertIn("continuation_title_pattern", str(ctx.exception))

    def test_bad_regex_rejected(self):
        with self.assertRaises(RuleError):
            self._load("^[（(]\\d+[）)]$(")

    def test_shipped_xuges_pattern_is_valid(self):
        r = load_rules()["xuges.com"]
        self.assertEqual(r.catalog_cfg["continuation_title_pattern"],
                         "^[（(]\\d+[）)]$")

    def test_valid_narrow_pattern_loads(self):
        self.assertIn("x.site", self._load("^[（(]\\d+[）)]$"))
        self.assertIn("x.site", self._load("^\\s*（续）\\s*$"))


class TestNestedJsonFields(unittest.TestCase):
    """`_dig` 穿透**字符串化的 JSON** + `@json:` 路径支持 `{bid}`（v0.8.15）。

    背景：360 系接口不嵌套对象，而是把子对象**序列化成字符串**塞进字段 ——
    仙人掌小说的 `op_ext` 就是 `'{"money_topic":{...}}'`（一个 str），
    而章节标题 / 付费标记 / 全局序号**全在里面**。不穿透就一个都取不到。
    """

    def test_dig_penetrates_json_string(self):
        from noveldown.parser import _dig
        item = {"op_ext": '{"money_topic": {"index": "11", "title": "第十一章", "paid": "2"}}'}
        self.assertEqual(_dig(item, "op_ext.money_topic.index"), "11")
        self.assertEqual(_dig(item, "op_ext.money_topic.title"), "第十一章")
        self.assertEqual(_dig(item, "op_ext.money_topic.paid"), "2")

    def test_dig_plain_string_is_not_parsed(self):
        """普通字符串**不能**当对象继续走 —— 否则等于把无意义的值当数据。"""
        from noveldown.parser import _dig
        self.assertIsNone(_dig({"a": "hello"}, "a.b"))
        self.assertIsNone(_dig({"a": "{坏 JSON"}, "a.b"))
        self.assertIsNone(_dig({"a": "[1,2"}, "a.b"))

    def test_dig_still_handles_index_and_missing(self):
        from noveldown.parser import _dig
        self.assertEqual(_dig({"a": [{"b": 1}]}, "a.0.b"), 1)
        self.assertIsNone(_dig({}, "x.y"))
        self.assertIsNone(_dig({"a": 1}, "a.b"))

    def test_parse_jsonish_accepts_jsonp_and_plain(self):
        from noveldown.parser import _parse_jsonish
        self.assertEqual(_parse_jsonish('{"a":1}'), {"a": 1})
        self.assertEqual(_parse_jsonish('cb({"a":1})'), {"a": 1})
        self.assertEqual(_parse_jsonish('cb({"a":1});'), {"a": 1})
        self.assertIsNone(_parse_jsonish("<html>"))
        self.assertIsNone(_parse_jsonish(""))
        self.assertIsNone(_parse_jsonish("123"))       # 标量不算

    def test_book_info_from_json_api_with_bid_placeholder(self):
        """`book.info_api` 回 JSONP 时用 `@json:data.{bid}.xxx` 取值（仙人掌形态）。"""
        from noveldown.rules import Rule
        rule = Rule({
            "id": "t.x", "name": "T", "match": ["x.com"], "free_only": True,
            "book": {"url_pattern": "c=(\\w+)", "info_url": "{origin}/r?c={bid}",
                     "info_api": {"url": "{origin}/info?c={bid}",
                                  "title": ["@json:data.{bid}.name"],
                                  "author": ["@json:data.{bid}.source"],
                                  "intro": ["@json:data.{bid}.data_describe"],
                                  "status": ["@json:data.{bid}.status_name"]}},
            "catalog": {"mode": "json_api", "json": {"url": "{origin}/l?c={bid}"}},
            "chapter": {"content_selector": "div.c"},
        }).validate()
        frag = ('cb({"errno":0,"data":{"CH1":{"name":"书名X","source":"作者Y",'
                '"data_describe":"简介Z","status_name":"已完结"}}})')
        info = parse_book_info(rule, "<html></html>", "https://x.com/r?c=CH1", "CH1",
                               info_html=frag)
        self.assertEqual(info["title"], "书名X")
        self.assertEqual(info["author"], "作者Y")
        self.assertEqual(info["intro"], "简介Z")
        self.assertEqual(info["status"], "已完结")


class TestJsonCatalogNestedAndApiUrl(unittest.TestCase):
    """JSON 目录：字段走**嵌套路径**、逐章正文地址带在条目上、VIP 字段分栏。"""

    def _rule(self):
        from noveldown.rules import Rule
        return Rule({
            "id": "t.x", "name": "T", "match": ["x.com"], "free_only": True,
            "book": {"url_pattern": "c=(\\w+)", "info_url": "{origin}/r?c={bid}"},
            "catalog": {
                "mode": "json_api",
                "json": {"url": "{origin}/mlist?c={bid}&page={page}",
                         "items_path": "data.res",
                         "max_pages": 9,
                         "cid_field": "op_ext.money_topic.index",
                         "title_field": "op_ext.money_topic.title",
                         "vip_field": "op_ext.money_topic.paid",
                         "vip_truthy": ["1", "2"],
                         "api_url_field": "rawurl"},
                "url_template": "{origin}/read?c={bid}&u={api_url}"},
            "chapter": {"content_selector": "div.c"},
        }).validate()

    def test_catalog_from_fixture(self):
        html = read_fixture("xrz_catalog_p1.json")
        items, locked = collect_json_catalog(self._rule(), html, "ch1", "https://x.com")
        # 前 10 章免费、后 10 章付费
        self.assertEqual(len(items), 10)
        self.assertEqual(len(locked), 10)
        self.assertEqual(items[0]["cid"], "1")
        self.assertEqual(items[0]["title"], "第一章、要不我们凑一下")
        self.assertEqual(locked[0]["cid"], "11")
        self.assertIn("paid=2", locked[0]["reason"])
        # 逐章正文地址被带下来
        self.assertTrue(items[0]["api_url"].startswith("http://zm.news.so.com/"))
        # url_template 里的 {api_url} 生效
        self.assertIn("zm.news.so.com", items[0]["url"])
        chs = normalize_catalog(items)
        self.assertEqual([c.index for c in chs], list(range(1, 11)))
        self.assertTrue(chs[0].api_url)

    def test_cid_must_be_global_index_not_page_local_idx(self):
        """反面锚点：`idx` 是**页内序号**，用它当 cid 会让第 2 页起全被去重掉。"""
        from noveldown.rules import Rule
        rule = Rule({
            "id": "t.y", "name": "T", "match": ["y.com"], "free_only": True,
            "book": {"url_pattern": "c=(\\w+)", "info_url": "{origin}/r?c={bid}"},
            "catalog": {"mode": "json_api",
                        "json": {"url": "{origin}/l?c={bid}", "items_path": "data.res",
                                 "cid_field": "idx", "title_field": "op_ext.money_topic.title"}},
            "chapter": {"content_selector": "div.c"},
        }).validate()
        html = read_fixture("xrz_catalog_p1.json")
        items, _ = collect_json_catalog(rule, html, "ch1", "https://y.com")
        # 用 idx 当 cid → 只剩 20 个唯一值里的 1..20，但**全是页内序号**
        self.assertEqual(items[0]["cid"], "1")
        self.assertEqual(items[-1]["cid"], "20")    # 而真实全局序号应是 1..20 之外的第 20 页
        # 换言之：这样的配置在第 2 页会产出与第 1 页重复的 cid → 被去重掉
        self.assertEqual(len({i["cid"] for i in items}), 20)


class TestBodyApiFreeGuard(unittest.TestCase):
    """`chapter.body_api.require` —— 在**数据源**上判免费（v0.8.15）。

    为什么必须有这道防线（实测仙人掌小说 / 360）：
    付费章走正文接口**既不报错、也不带任何付费提示**，只返回一段**戛然截断的
    试读片段**（实测第 11 章 642 字符 / 434 汉字；第 1 章完整是 2392 字符）。
    正文里连一个「付费/VIP」字样都没有 → **第 4 层「付费墙特征词」完全失效**，
    只靠它会把试读片段当正文**静默导出**。
    而同一个响应里有 `data.unlock: false` 这种**权威状态字段**，直接拿它判。
    """

    def _dl(self, rule):
        from noveldown.engine import Downloader
        d = Downloader.__new__(Downloader)
        d.rule = rule
        d.book = type("B", (), {"book_id": "ch1", "url": "https://x.com/r?c=ch1"})()
        d.log = lambda *a, **k: None
        return d

    def _rule(self, require=None):
        from noveldown.rules import Rule
        ba = {"url": "https://api.x.com/d?u={api_url}&c={bid}",
              "content_field": "data.content"}
        if require is not None:
            ba["require"] = require
        return Rule({
            "id": "t.x", "name": "T", "match": ["x.com"], "free_only": True,
            "book": {"url_pattern": "c=(\\w+)", "info_url": "{origin}/r?c={bid}"},
            "catalog": {"mode": "json_api", "json": {"url": "{origin}/l?c={bid}"}},
            "chapter": {"content_selector": "div.nd-api-body", "body_api": ba},
        }).validate()

    def _ch(self, api_url="http://zm.news.so.com/aaa"):
        return type("C", (), {"cid": "11", "index": 11, "api_url": api_url})()

    def test_paid_chapter_is_judged_protected(self):
        """付费章响应（fixture 实录）→ 判受保护，且**不产出任何片段**。"""
        d = self._dl(self._rule({"field": "data.unlock"}))
        raw = read_fixture("xrz_detail_paid.json")
        d._fetch_raw = lambda *a, **k: raw
        frag, reason = d._body_api_html(self._ch(), "https://x.com/r?c=ch1")
        self.assertEqual(frag, "", "受保护章绝不能给出正文片段")
        self.assertIn("data.unlock", reason)
        self.assertIn("False", reason)

    def test_free_chapter_passes_and_yields_fragment(self):
        d = self._dl(self._rule({"field": "data.unlock"}))
        raw = read_fixture("xrz_detail_free.json")
        d._fetch_raw = lambda *a, **k: raw
        frag, reason = d._body_api_html(self._ch(), "https://x.com/r?c=ch1")
        self.assertEqual(reason, "")
        self.assertIn("nd-api-body", frag)
        self.assertIn("谁经历过", frag)

    def test_missing_or_null_field_is_protected(self):
        """JSON 里**字段缺失 / 为 null / 为假值**一律判受保护。

        宁可漏抓一章（可重试、可见），也不能把试读片段当正文**静默**导出。
        """
        from noveldown.engine import _require_violation
        req = {"field": "data.unlock"}
        for bad in ('{"data":{}}', '{"data":{"unlock":null}}',
                    '{"data":{"unlock":0}}', '{"data":{"unlock":"false"}}'):
            self.assertTrue(_require_violation(bad, req), bad)

    def test_unparseable_response_is_not_judged(self):
        """**完全不是 JSON** 时不判受保护 —— 交给下游兜底。

        理由：这类响应 `body_api_fragment` 也取不到 → 该章回落到页面 HTML，
        而仙人掌的阅读页纯 HTTP 只是个空壳 → 该章会以「空/过短」暴露出来
        （校对报告 + 产物终检都会报），**不是静默错**。
        若在这里武断判受保护，反而会把**免费章误标成 locked**（丢内容）。
        """
        from noveldown.engine import _require_violation
        for other in ("not json at all", "<html>机器人验证</html>", ""):
            self.assertEqual(_require_violation(other, {"field": "data.unlock"}), "")

    def test_truthy_field_passes(self):
        from noveldown.engine import _require_violation
        req = {"field": "data.unlock"}
        for good in ('{"data":{"unlock":true}}', '{"data":{"unlock":"1"}}',
                     '{"data":{"unlock":"True"}}'):
            self.assertEqual(_require_violation(good, req), "")

    def test_no_require_configured_is_noop(self):
        """不配 `require` 时行为与历史一致（不得凭空拦截）。"""
        from noveldown.engine import _require_violation
        self.assertEqual(_require_violation('{"data":{"unlock":false}}', {}), "")
        self.assertEqual(_require_violation("raw text", {"field": ""}), "")

    def test_nested_require_path(self):
        """`require.field` 也支持嵌套路径，且能穿透**字符串化 JSON**。"""
        from noveldown.engine import _require_violation
        raw = '{"data":{"op_ext":"{\\"paid\\":\\"2\\"}"}}'
        # paid=2 落在 truthy 里 → 通过（证明路径穿透到了字符串化 JSON 内部）
        self.assertEqual(_require_violation(raw, {"field": "data.op_ext.paid",
                                                 "truthy": ["2"]}), "")
        # 同一字段不在 truthy 里 → 判受保护
        self.assertTrue(_require_violation(raw, {"field": "data.op_ext.paid",
                                                 "truthy": ["0"]}))

    def test_missing_api_url_skips_call(self):
        """`{api_url}` 占位但条目没带地址 → 直接返回，不发出请求。"""
        d = self._dl(self._rule({"field": "data.unlock"}))
        called = []
        d._fetch_raw = lambda *a, **k: called.append(1) or "{}"
        frag, reason = d._body_api_html(self._ch(api_url=""), "https://x.com/r?c=ch1")
        self.assertEqual((frag, reason), ("", ""))
        self.assertEqual(called, [], "缺 api_url 时不该发请求")


class TestXxsyFixtures(unittest.TestCase):
    """潇湘书院（v0.8.14 接入）：书籍页不给目录，目录在独立页；正文要**逐段**取。

    这一站的意义在于两条「形状」结论被 fixture 钉住：
      · 书籍页只有「最新公共章节」+「开始阅读」，目录必须去 `/chapterlist/{bid}`；
      · `div#reader-content` 里混着登录条 / 底部菜单 / 面包屑 →
        必须用 `paragraph_selector` 逐段取，否则首段会变成导航文字。
    """

    BOOK = "https://www.xxsy.net/book/36931095804318409"
    LIST = "https://www.xxsy.net/chapterlist/36931095804318409"

    def test_book_info(self):
        html = read_fixture("xxsy_book.html")
        info = parse_book_info(RULES["xxsy.net"], html, self.BOOK, "36931095804318409")
        self.assertEqual(info["title"], "禁欲霸总白天冷冰冰，夜里他超爱")
        self.assertEqual(info["author"], "林舒浅", "作者取 dl.bookprofile .title span")
        self.assertTrue(info["intro"].startswith("【先虐女后虐男"),
                        f"简介必须来自 div#book_intro，实际 {info['intro'][:40]!r}")
        self.assertTrue(info["cover"].startswith("//bookcover.yuewen.com"),
                        "封面用 sel@attr 取 img@src")

    def test_book_page_has_no_catalog(self):
        """反面锚点：书籍页的章节链接**只有 1 条**（最新公共章节），不能当目录用。"""
        html = read_fixture("xxsy_book.html")
        items, _ = collect_catalog_items(RULES["xxsy.net"], html, self.BOOK,
                                        "36931095804318409")
        self.assertLessEqual(len(items), 2,
                             "书籍页若被当成目录页，只会拿到 1~2 章（这正是必须走 "
                             "/chapterlist/ 的原因）")

    def test_catalog(self):
        html = read_fixture("xxsy_catalog.html")
        rule = RULES["xxsy.net"]
        items, locked = collect_catalog_items(rule, html, self.LIST,
                                              "36931095804318409")
        self.assertEqual(locked, [], "该站目录无 VIP 标记")
        self.assertEqual(len(items), 22)
        self.assertEqual(items[0]["cid"], "99142876033772511")
        self.assertEqual(items[0]["title"], "第1章 ：浅浅，这三年，你幸福吗？")
        self.assertEqual(items[0]["url"],
                         "https://www.xxsy.net/chapter/36931095804318409/99142876033772511")
        self.assertEqual(items[0]["volume"], "第一卷", "卷标记是非锚点 li 的文本")
        chs = normalize_catalog(items)
        self.assertEqual([c.index for c in chs][:3], [1, 2, 3])
        self.assertIn("第22章", chs[-1].title)

    def test_chapter_paragraphs_exclude_nav(self):
        html = read_fixture("xxsy_chapter.html")
        info = parse_chapter_page(RULES["xxsy.net"], html,
                                  "https://www.xxsy.net/chapter/36931095804318409/99142876033772511",
                                  "99142876033772511", "第1章 ：浅浅，这三年，你幸福吗？")
        text = "\n".join(info["paragraphs"])
        self.assertGreater(len(text), 1500)
        self.assertTrue(text.startswith("盛夏七月，夜间的风裹挟着燥热。"),
                        f"首段必须是正文（实际 {text[:40]!r}）")
        for nav in ("登录", "首页", "夜间模式", "目录书详情"):
            self.assertNotIn(nav, text[:200],
                             f"导航文字 {nav!r} 不得混进正文（须用 paragraph_selector）")


class TestZhulangFixtures(unittest.TestCase):
    """逐浪网（v0.8.14 接入）：书籍页与目录**在两个子域**，正文头部要剃掉。

    钉住的三条：
      · 目录在阅读域 `book.zhulang.com/{bid}/`（跨子域绝对 URL）；
      · 两处 `h1` 都是**站头**「逐浪小说」，章名在 `div#read-content h2`；
      · `div#read-content` 里挂着 `div.textinfo`（小说/作者/更新时间/字数）→
        用 `paragraph_selector` 逐段取可自然排除。
    """

    BOOK = "https://www.zhulang.com/780254/"
    CAT = "https://book.zhulang.com/780254/"

    def test_book_info_from_title(self):
        html = read_fixture("zhulang_book.html")
        info = parse_book_info(RULES["zhulang.com"], html, self.BOOK, "780254")
        self.assertEqual(info["title"], "我的西海雄鹰翱翔")
        self.assertEqual(info["author"], "懿小茹")
        self.assertIn("原子弹", info["intro"])

    def test_catalog_is_cross_subdomain(self):
        html = read_fixture("zhulang_catalog.html")
        rule = RULES["zhulang.com"]
        items, locked = collect_catalog_items(rule, html, self.CAT, "780254")
        self.assertEqual(locked, [])
        self.assertEqual(len(items), 129, "与站点自述「更新至129」一致")
        self.assertEqual(items[0]["cid"], "319")
        self.assertEqual(items[0]["title"], "001 秘密一世")
        self.assertEqual(items[0]["url"], "https://book.zhulang.com/780254/319.html")
        self.assertNotIn("h1", " ".join(str(item) for item in items[:1]),
                        "站头 h1 不得混进目录项")
        chs = normalize_catalog(items)
        self.assertEqual(chs[-1].title, "129 盛世如愿")
        cids = [int(c.cid) for c in chs]
        self.assertEqual(cids, sorted(cids), "cid 升序即阅读顺序")

    def test_chapter_strips_textinfo_header_and_anti_piracy_line(self):
        html = read_fixture("zhulang_chapter.html")
        info = parse_chapter_page(RULES["zhulang.com"], html,
                                  "https://book.zhulang.com/780254/319.html",
                                  "319", "001 秘密一世")
        text = "\n".join(info["paragraphs"])
        self.assertGreater(len(text), 1500)
        self.assertNotIn("字数：", text[:300], "div.textinfo 头部不得进正文")
        self.assertNotIn("打击盗版", text, "站尾反盗版行必须被 ad_patterns 过滤")
        self.assertNotIn("小说：我的西海雄鹰翱翔", text[:300])


class TestChapterExtract(unittest.TestCase):

    def test_shuquge_marker_div_is_stripped(self):
        """坑：div#content 首位有 <div id=center_tip> 水印，
        不剔除会因为 </div> 提前闭合而只抓到水印本身。"""
        html = read_fixture("shuquge_chapter.html")
        rule = RULES["shuquge.com"]
        res = parse_chapter_page(rule, html, 
                                 "https://www.shuquge.com/txt/207266/63891607.html",
                                 "63891607")
        self.assertGreater(len(res["paragraphs"]), 0, "必须抓到正文")
        joined = "\n".join(res["paragraphs"])
        self.assertNotIn("最新网址", joined, "水印必须被剔除")
        self.assertNotIn("推荐阅读", joined, "站外推荐块不得混入")

    def test_bqgbe_base64_chapter(self):
        html = read_fixture("bqgbe_chapter.html")
        rule = RULES["bqgbe.cc"]
        res = parse_chapter_page(rule, html,
                                 "https://www.bqgbe.cc/txt/445/54948.html", "54948")
        self.assertIn("base64", res["decode_note"])
        self.assertGreater(len(res["paragraphs"]), 20)
        self.assertNotIn("笔趣阁", "\n".join(res["paragraphs"]))
        # 续页判定：54948.html 的「下一章」指向 54948_1.html（同一章第 2 页）
        self.assertTrue(res["next_url"] and res["next_url"].endswith("54948_1.html"))

    def test_paragraph_ads_are_filtered(self):
        soup = make_soup(
            "<div id='c'>正文第一段<br/>"
            "最新网址：www.example.com<br/>"
            "http://www.example.com/txt/1/2.html<br/>"
            "正文第二段</div>")
        ps, ads = extract_paragraphs(soup.select_one("#c"), ["最新网址"])
        self.assertEqual(ps, ["正文第一段", "正文第二段"])
        self.assertEqual(ads, 2)

    def test_nbsp_indent_normalized(self):
        soup = make_soup("<div id='c'>&nbsp;&nbsp;&nbsp;&nbsp;缩进正文</div>")
        ps, _ = extract_paragraphs(soup.select_one("#c"), [])
        self.assertEqual(ps, ["缩进正文"])

    def test_paragraph_selector_falls_back_when_missing(self):
        """站点改版 / 换渲染变体：段落选择器一个都没命中时，必须回退整体切分。

        否则整章会**静默变空**（比多几个噪声字严重得多）。回退要留痕（extract_note）。
        """
        from noveldown.rules import Rule
        rule = Rule({
            "id": "t.fb", "name": "T", "match": ["x.com"], "free_only": True,
            "book": {"url_pattern": "/c/(\\d+)"},
            "catalog": {"item_selector": "a"},
            "chapter": {"content_selector": "main.content",
                        "paragraph_selector": "span.content-text",   # 故意不存在的标记
                        "strip_selectors": ["span.review", ".review-count"]},
        })
        html = '<main class="content"><p>第一段</p><p>第二段</p></main>'
        res = parse_chapter_page(rule, html, "https://x/c/1/", "1")
        self.assertEqual(res["paragraphs"], ["第一段", "第二段"])
        self.assertIn("回退", res["extract_note"])
        self.assertIn("span.content-text", res["extract_note"])

    def test_fallback_result_is_clean_after_strip(self):
        """回退路径同样干净：strip_selectors 已先剔掉段评数节点。

        实测起点形态：<p><span class="content-text">痛！</span>
        <span class="review">999</span></p> —— 若 strip 生效，回退也不会得到「痛！999」。
        """
        from noveldown.rules import Rule
        rule = Rule({
            "id": "t.fb2", "name": "T", "match": ["x.com"], "free_only": True,
            "book": {"url_pattern": "/c/(\\d+)"},
            "catalog": {"item_selector": "a"},
            "chapter": {"content_selector": "main.content",
                        "paragraph_selector": "span.nonexistent",
                        "strip_selectors": ["span.review", ".review-icon", ".review-count"]},
        })
        html = ('<main class="content"><p><span class="content-text">痛！</span>'
                '<span class="review"><span class="review-icon"></span>'
                '<span class="review-count">999</span></span></p></main>')
        res = parse_chapter_page(rule, html, "https://x/c/1/", "1")
        self.assertEqual(res["paragraphs"], ["痛！"])
        self.assertNotIn("999", "\n".join(res["paragraphs"]))

    def test_no_fallback_note_when_selector_hits(self):
        """走主路径时不得留下回退痕迹（否则没法靠备注发现站点改版）。"""
        from noveldown.rules import Rule
        rule = Rule({
            "id": "t.hit", "name": "T", "match": ["x.com"], "free_only": True,
            "book": {"url_pattern": "/c/(\\d+)"},
            "catalog": {"item_selector": "a"},
            "chapter": {"content_selector": "main.content",
                        "paragraph_selector": "span.content-text"},
        })
        html = '<main class="content"><p><span class="content-text">痛！</span></p></main>'
        res = parse_chapter_page(rule, html, "https://x/c/1/", "1")
        self.assertEqual(res["paragraphs"], ["痛！"])
        self.assertEqual(res["extract_note"], "")

    def test_no_content_container_still_returns_extract_note_key(self):
        """容器都选不到时也不能 NameError（回归：extract_note 必须在 if 外初始化）。"""
        from noveldown.rules import Rule
        rule = Rule({
            "id": "t.noc", "name": "T", "match": ["x.com"], "free_only": True,
            "book": {"url_pattern": "/c/(\\d+)"},
            "catalog": {"item_selector": "a"},
            "chapter": {"content_selector": "main.nope",
                        "paragraph_selector": "span.content-text"},
        })
        res = parse_chapter_page(rule, "<html><body>空</body></html>",
                                 "https://x/c/1/", "1")
        self.assertEqual(res["paragraphs"], [])
        self.assertEqual(res["extract_note"], "")

    def test_paragraph_selector_ignores_extra_nodes(self):
        """段落级选择器：正文段是 <span>，同 `<p>` 里还混着段评数/点赞数节点。

        实测起点：`<p><span class="content-text">痛！</span>
        <span class="review">999</span></p>` —— 整块取文本会得到「痛！999」，
        按段落元素取则只拿 content-text。
        """
        from noveldown.rules import Rule
        rule = Rule({
            "id": "t.qd", "name": "T", "match": ["qidian.com"], "free_only": True,
            "book": {"url_pattern": "/book/(\\d+)"},
            "catalog": {"item_selector": "a"},
            "chapter": {"content_selector": "main.content",
                        "paragraph_selector": "span.content-text"},
        })
        html = ('<html><body><main class="content">'
                '<p><span class="content-text">痛！</span>'
                '<span class="review">999</span></p>'
                '<p><span class="content-text">太痛了！</span>'
                '<span class="review">12</span></p>'
                '</main></body></html>')
        res = parse_chapter_page(rule, html,
                                 "https://www.qidian.com/chapter/1/2/", "2")
        self.assertEqual(res["paragraphs"], ["痛！", "太痛了！"])
        self.assertNotIn("999", "\n".join(res["paragraphs"]))


class TestJsonApiCatalog(unittest.TestCase):
    """JSON 接口目录（七猫形态）：比 HTML 更强的 VIP 判定来源。"""

    def _rule(self, **json_over):
        from noveldown.rules import Rule
        cfg = {
            "url": "{origin}/qimaoapi/api/book/chapter-list?book_id={bid}",
            "items_path": "data.chapters",
            "cid_field": "id", "title_field": "title",
            "vip_field": "is_vip", "vip_truthy": ["1", "true"],
        }
        cfg.update(json_over)
        return Rule({
            "id": "t.qimao", "name": "T", "match": ["qimao.com"], "free_only": True,
            "book": {"url_pattern": "/shuku/(\\d+)"},
            "catalog": {"mode": "json_api", "json": cfg,
                        "url_template": "{origin}/shuku/{bid}-{cid}/"},
            "chapter": {"content_selector": "div.c"},
        }).validate()

    SAMPLE = ('{"data":{"chapters":['
              '{"id":"1001","title":"第1章  起","is_vip":"0","index":"1"},'
              '{"id":"1002","title":"第2章  承","is_vip":"1","index":"2"},'
              '{"id":"1003","title":"第3章  转","is_vip":"0","index":"3"}]}}')

    def test_parses_and_splits_vip(self):
        from noveldown.parser import collect_json_catalog
        items, locked = collect_json_catalog(self._rule(), self.SAMPLE, "999",
                                            "https://www.qimao.com")
        self.assertEqual([i["cid"] for i in items], ["1001", "1003"])
        self.assertEqual([i["cid"] for i in locked], ["1002"])
        self.assertEqual(items[0]["url"], "https://www.qimao.com/shuku/999-1001/")
        self.assertEqual(items[0]["title"], "第1章 起")
        self.assertIn("is_vip", locked[0]["note"])

    def test_no_vip_field_keeps_all(self):
        from noveldown.parser import collect_json_catalog
        items, locked = collect_json_catalog(self._rule(vip_field=None),
                                            self.SAMPLE, "999", "https://x")
        self.assertEqual(len(items), 3)
        self.assertEqual(locked, [])

    def test_bad_json_raises_with_hint(self):
        from noveldown.parser import collect_json_catalog
        with self.assertRaises(ValueError) as ctx:
            collect_json_catalog(self._rule(), "<html>SPA 外壳</html>", "9", "https://x")
        self.assertIn("不是 JSON", str(ctx.exception))

    def test_wrong_items_path_raises_with_keys(self):
        from noveldown.parser import collect_json_catalog
        with self.assertRaises(ValueError) as ctx:
            collect_json_catalog(self._rule(items_path="data.nope"),
                                 self.SAMPLE, "9", "https://x")
        self.assertIn("取不到列表", str(ctx.exception))

    # 起点形态：卷 → 章 两层嵌套 data.vs[].cs[]，且 sS 是**反直觉**的 VIP 标记
    QIDIAN_STYLE = ('{"data":{"vs":['
                    '{"cs":[{"id":"100","cN":"第一章","sS":"1"},'
                    '{"id":"101","cN":"第二章","sS":"0"}]},'
                    '{"cs":[{"id":"102","cN":"第三章","sS":"1"}]}]}}')

    def test_flatten_field_unrolls_volumes(self):
        """层叠目录：flatten_field 把 data.vs[].cs[] 展平成章节列表。

        起点 `sS` 反直觉：**1 = 免费，0 = VIP**（实测）。规则用 vip_truthy=["0"]
        把 0 判为受保护，这里一并回归。
        """
        from noveldown.parser import collect_json_catalog
        rule = self._rule(items_path="data.vs", flatten_field="cs",
                          cid_field="id", title_field="cN",
                          vip_field="sS", vip_truthy=["0"])
        items, locked = collect_json_catalog(
            rule, self.QIDIAN_STYLE, "999", "https://www.qidian.com")
        self.assertEqual([i["cid"] for i in items], ["100", "102"])
        self.assertEqual([i["cid"] for i in locked], ["101"])
        self.assertEqual(items[0]["title"], "第一章")

    def test_flatten_field_tolerates_non_group_items(self):
        """展平时遇到没有子列表的条目：原样保留，不能丢章。"""
        from noveldown.parser import collect_json_catalog
        rule = self._rule(items_path="data.vs", flatten_field="cs")
        sample = ('{"data":{"vs":[{"cs":[{"id":"1","title":"甲","is_vip":"0"}]},'
                  '{"id":"2","title":"乙","is_vip":"0"}]}}')
        items, _ = collect_json_catalog(rule, sample, "9", "https://x")
        self.assertEqual([i["cid"] for i in items], ["1", "2"])


class TestTitlePattern(unittest.TestCase):
    """书名清洗：SPA 站点书名只在 <title> 里，且带站点后缀。"""

    def _rule(self, **over):
        from noveldown.rules import Rule
        book = {"url_pattern": "/s/(\\d+)",
                "title": ["@title", ".title"],
                "author": [".author"],
                "title_pattern": "^(.*?)(?:免费阅读|最新章节)"}
        book.update(over)
        return Rule({"id": "t.x", "name": "T", "match": ["x.com"], "free_only": True,
                     "book": book,
                     "catalog": {"item_selector": "a",
                                 "id_from": {"mode": "href", "pattern": "(?P<cid>\\d+)"}},
                     "chapter": {"content_selector": "div.c"}}).validate()

    def test_title_from_page_title_with_pattern(self):
        from noveldown.parser import parse_book_info
        html = ("<html><head><title>封总，太太想跟你离婚很久了免费阅读-七猫中文网</title>"
                "</head><body><div class='title'>封总，太太想跟你离婚很久了 9.2分</div>"
                "<div class='author'>云中觅</div></body></html>")
        info = parse_book_info(self._rule(), html, "https://x/s/1/", "1")
        self.assertEqual(info["title"], "封总，太太想跟你离婚很久了")
        self.assertEqual(info["author"], "云中觅")

    def test_falls_back_to_selector_when_no_page_title(self):
        from noveldown.parser import parse_book_info
        html = "<html><head></head><body><div class='title'>备用书名</div></body></html>"
        info = parse_book_info(self._rule(), html, "https://x/s/1/", "1")
        self.assertEqual(info["title"], "备用书名")


class TestBookInfoFragment(unittest.TestCase):
    """`book.info_api` + `sel@attr`（v0.8.13，书山形态）。

    背景：书籍页是 SPA 外壳 —— 静态 HTML 里**没有简介**，而
    `meta[name=description]` 是**站点通用文案**（每本书一模一样）。
    真简介在 XHR 片段 `/book/bookintro?bid=` 里。
    直接把通用文案当简介 = 往导出的 EPUB 里写错数据。

    封面同理：`<img src>` 的文本为空，必须用 `sel@attr` 取 `src`。
    """

    def _rule(self, **book_over):
        from noveldown.rules import Rule
        book = {
            "url_pattern": "/book/(\\d+)/",
            "title": ["@title"],
            "title_pattern": "^([^,，]+)",
            "author": ["@title"],
            "author_pattern": "[,，]\\s*([^,，]+?)作品",
            "cover": ["a.book-face img@src"],
            "info_api": {"url": "{origin}/book/bookintro?bid={bid}",
                         "intro": ["pre.intro-bookinfo", "div.intro-content"]},
        }
        book.update(book_over)
        return Rule({"id": "t.x", "name": "T", "match": ["x.com"], "free_only": True,
                     "book": book,
                     "catalog": {"item_selector": "a",
                                 "id_from": {"mode": "href",
                                             "pattern": "(?P<cid>\\d+)"}},
                     "chapter": {"content_selector": "div.c"}}).validate()

    MAIN = ("<html><head><title>无暗英雄,洛城东作品-书山中文网</title>"
            "<meta name=\"description\" content=\"本站最新最热小说网\"></head>"
            "<body><a class='book-face'><img src='//img.x/bookCover/11/112812_large.jpg'>"
            "</a></body></html>")
    FRAG = ("<div class='introduction'><div class='intro-content'>"
            "<pre class='intro-bookinfo'>真简介：神罚大陆的天空永远都是暗淡昏黄。</pre>"
            "</div></div>")

    def test_fragment_intro_wins_over_generic_meta(self):
        info = parse_book_info(self._rule(), self.MAIN, "https://x/book/1/", "1",
                               info_html=self.FRAG)
        self.assertIn("真简介", info["intro"])
        self.assertNotIn("最新最热", info["intro"])
        self.assertEqual(info["title"], "无暗英雄")
        self.assertEqual(info["author"], "洛城东")

    def test_cover_uses_attr_syntax(self):
        info = parse_book_info(self._rule(), self.MAIN, "https://x/book/1/", "1")
        self.assertEqual(info["cover"], "//img.x/bookCover/11/112812_large.jpg")

    def test_missing_fragment_falls_back_to_main_page(self):
        """片段取不到时不能报错、也不能丢元数据 —— 落回主页面选择器。"""
        for frag in (None, "", "<div>空片段</div>"):
            info = parse_book_info(self._rule(), self.MAIN, "https://x/book/1/", "1",
                                   info_html=frag)
            self.assertEqual(info["title"], "无暗英雄")
            self.assertEqual(info["cover"], "//img.x/bookCover/11/112812_large.jpg")

    def test_meta_still_takes_content_without_attr(self):
        """历史行为：`meta[...]` 不带 `@` 时取 `content`（不能被 @ 语法破坏）。"""
        from noveldown.parser import parse_book_info
        r = self._rule(intro=["meta[name='description']"], info_api=None)
        info = parse_book_info(r, self.MAIN, "https://x/book/1/", "1")
        self.assertEqual(info["intro"], "本站最新最热小说网")

    def test_at_in_attribute_selector_is_not_split(self):
        """`a[href*='@']` 这类属性选择器里的 `@` 不能被当成取值语法。"""
        from noveldown.parser import parse_book_info
        html = "<html><body><a href='mailto:x@y.com'>联系</a></body></html>"
        r = self._rule(cover=["a[href*='@']"], info_api=None)
        info = parse_book_info(r, html, "https://x/book/1/", "1")
        self.assertEqual(info["cover"], "联系")


class TestBookInfoApiValidation(unittest.TestCase):
    """`book.info_api` 的配置事故要**加载即报**（字段打错会静默落回主页面）。"""

    def _load(self, iapi):
        import json
        import os
        from noveldown.rules import load_rules
        from tests._base import temp_subdir
        td = temp_subdir("rules")
        os.makedirs(td, exist_ok=True)
        raw = {
            "id": "x.site", "name": "X", "match": ["x.site"], "free_only": True,
            "book": {"url_pattern": "/b/(\\d+)", "info_url": "{origin}/b/{bid}/",
                     "info_api": iapi},
            "catalog": {"item_selector": "a",
                        "id_from": {"mode": "href", "pattern": "(?P<cid>\\d+)"}},
            "chapter": {"content_selector": "div#c"},
        }
        with open(os.path.join(td, "a.json"), "w", encoding="utf-8") as f:
            json.dump(raw, f, ensure_ascii=False)
        return load_rules(td)

    def test_unknown_field_rejected(self):
        from noveldown.rules import RuleError
        with self.assertRaises(RuleError) as ctx:
            self._load({"url": "{origin}/i?bid={bid}", "Introduction": ["p"]})
        self.assertIn("未知字段", str(ctx.exception))

    def test_missing_url_rejected(self):
        from noveldown.rules import RuleError
        with self.assertRaises(RuleError) as ctx:
            self._load({"intro": ["p"]})
        self.assertIn("url 不能为空", str(ctx.exception))

    def test_valid_config_loads(self):
        rules = self._load({"url": "{origin}/i?bid={bid}", "intro": ["p"]})
        self.assertIn("x.site", rules)


class TestContainerItemAndVipChild(unittest.TestCase):
    """目录项是**容器**时的抽取与 VIP 判定（书海形态）。

    实测书海：`<div class="chapter-item"><a href="/read/1/41.html">第41章 …</a>
    <span class="vip"></span></div>` —— VIP 标记是同级的 span，
    且 **33% 的 `<a>` 文本为空**（站点标记错位，标题落在 `</a>` 之后）。
    """

    def _rule(self, **cat_over):
        from noveldown.rules import Rule
        cat = {
            "item_selector": "div.chapter-item",
            "vip_child_selector": "span.vip",
            "id_from": {"mode": "href",
                        "pattern": "/read/(?P<b>\\d+)/(?P<cid>\\d+)\\.html"},
            "url_template": "{origin}/read/{bid}/{cid}.html",
            "sort": "cid_numeric_asc",
        }
        cat.update(cat_over)
        return Rule({
            "id": "t.sh", "name": "T", "match": ["x.com"], "free_only": True,
            "book": {"url_pattern": "/book/(\\d+)"},
            "catalog": cat,
            "chapter": {"content_selector": "div.c"},
        }).validate()

    HTML = ('<div class="chapter-item"><a href="/read/1/2.html">第2章 乙</a></div>'
            '<div class="chapter-item"><a href="/read/1/1.html"></a>第1章 甲</div>'
            '<div class="chapter-item"><a href="/read/1/3.html">第3章 丙</a>'
            '<span class="vip"></span></div>')

    def test_container_item_title_from_container(self):
        """`<a>` 文本为空时，标题必须从**容器**取（否则丢三分之一标题）。

        注意 `collect_catalog_items` 保持**文档顺序**，排序是归一化阶段的事。
        """
        items, locked = collect_catalog_items(
            self._rule(), self.HTML, "https://x.com/book/1.htm", "1")
        self.assertEqual([i["cid"] for i in items], ["2", "1"])
        self.assertEqual([i["title"] for i in items], ["第2章 乙", "第1章 甲"])
        self.assertEqual([i["url"] for i in items],
                         ["https://x.com/read/1/2.html",
                          "https://x.com/read/1/1.html"])
        self.assertEqual([l["cid"] for l in locked], ["3"])
        self.assertIn("span.vip", locked[0]["reason"])

    def test_vip_child_only_affects_its_own_item(self):
        """回归：不能把「父级的全部后代」当判定范围（否则整本被误锁）。"""
        items, locked = collect_catalog_items(
            self._rule(), self.HTML, "https://x.com/book/1.htm", "1")
        self.assertEqual(len(locked), 1, "只有带 span.vip 的那一条应被锁")
        self.assertEqual(len(items), 2)


class TestCatalogItemDenyText(unittest.TestCase):
    """`catalog.item_deny_text`：丢掉站点导航类的**伪目录项**（v0.8.2）。

    实测：镜像站目录里混着「开始阅读」「在线书库」「TXT下载」，它们和真章节
    一样带数字 href（`/book/21/1.html`），cid 甚至与第 1 章**相同** ——
    于是 `dedupe=keep_first` 会把真标题挤掉，导出里第 1 章叫「开始阅读」。
    """

    def _items(self, deny):
        from noveldown.parser import collect_catalog_items
        from noveldown.rules import Rule
        cat = {
            "item_selector": "ul.dirlist a",
            "id_from": {"mode": "href", "pattern": "/(?P<cid>\\d+)\\.html"},
            "sort": "cid_numeric_asc", "dedupe": "keep_first",
        }
        if deny is not None:
            cat["item_deny_text"] = deny
        rule = Rule({
            "id": "t.m", "name": "T", "match": ["x.com"], "free_only": True,
            "book": {"url_pattern": "/(\\d+)/"},
            "catalog": cat,
            "chapter": {"content_selector": "div#c"},
        }).validate()
        html = ('<ul class="dirlist">'
                '<li><a href="/book/21/1.html">开始阅读</a></li>'
                '<li><a href="/book/21/1.html">第1章 甲</a></li>'
                '<li><a href="/book/21/2.html">第2章 乙</a></li>'
                '<li><a href="/book/21/3.html">TXT下载</a></li>'
                '</ul>')
        items, _locked = collect_catalog_items(rule, html,
                                              "https://x.com/book/21/", "21")
        return items

    def test_without_deny_nav_item_wins_first(self):
        items = self._items(None)
        titles = [i["title"] for i in items]
        self.assertIn("开始阅读", titles, "不配 deny 时应能看到噪声项")

    def test_deny_text_drops_nav_items(self):
        items = self._items(["开始阅读", "TXT下载"])
        titles = [i["title"] for i in items]
        self.assertEqual(titles, ["第1章 甲", "第2章 乙"])


class TestVipVolumeMarkers(unittest.TestCase):
    """目录按**分段**标注免费/VIP（塔读：`<h2><span>免费章节<i>/N章</i></span></h2>`）。"""

    def _rule(self):
        from noveldown.rules import Rule
        return Rule({
            "id": "t.td", "name": "T", "match": ["x.com"], "free_only": True,
            "book": {"url_pattern": "/book/(\\d+)"},
            "catalog": {
                "item_selector": "div.chapter-item",
                "id_from": {"mode": "href",
                            "pattern": "/book/(?P<b>\\d+)/(?P<cid>\\d+)/"},
                "url_template": "{origin}/book/{bid}/{cid}/",
                "sort": "document_order",
                "volume_selector": "h2",
                "vip_volume_markers": ["VIP"],
            },
            "chapter": {"content_selector": "div.c"},
        }).validate()

    def test_items_under_vip_section_are_locked(self):
        html = ('<h2>免费章节 /2章</h2>'
                '<div class="chapter-item"><a href="/book/1/101/">第1章</a></div>'
                '<div class="chapter-item"><a href="/book/1/102/">第2章</a></div>'
                '<h2>VIP章节</h2>'
                '<div class="chapter-item"><a href="/book/1/201/">第3章</a></div>')
        items, locked = collect_catalog_items(html=html, rule=self._rule(),
                                              page_url="https://x.com/book/1",
                                              bid="1")
        self.assertEqual([i["cid"] for i in items], ["101", "102"])
        self.assertEqual([l["cid"] for l in locked], ["201"])
        self.assertIn("VIP", locked[0]["reason"])
        self.assertEqual(items[0]["volume"], "免费章节 /2章")


class TestBodyApi(unittest.TestCase):
    """正文来自 JSON 接口（塔读）+ 按 base64(章节id) 剔除站点水印段。"""

    def _rule(self, **api_over):
        from noveldown.rules import Rule
        api = {
            "url": "{origin}/getPartContentByCodeTable/{bid}/{seq}",
            "content_field": "data.content",
            "drop": {"selector": "p[data-limit]", "attr": "data-limit",
                     "equals_base64_of": "cid"},
        }
        api.update(api_over)
        return Rule({
            "id": "t.tadu", "name": "T", "match": ["tadu.com"],
            "free_only": True,
            "book": {"url_pattern": "/book/(\\d+)"},
            "catalog": {"item_selector": "a"},
            "chapter": {"content_selector": "div.nd-api-body",
                        "paragraph_selector": "p",
                        "body_api": api},
        }).validate()

    def _payload(self, content):
        import json
        return json.dumps({"status": 200, "data": {"content": content}},
                          ensure_ascii=False)

    def test_extracts_and_drops_watermark_by_base64_cid(self):
        import base64
        key = base64.b64encode(b"100812587").decode()      # MTAwODEyNTg3
        content = (f'<p data-limit="{key}">站点水印段</p>'
                   '<p data-limit="MTAwODEyNTg1">正文本段</p>')
        frag = body_api_fragment(self._rule(), self._payload(content),
                                 "1001396", 1, "100812587")
        self.assertIn("nd-api-body", frag)
        self.assertNotIn("站点水印段", frag)
        self.assertIn("正文本段", frag)

    def test_keeps_other_data_limit_paragraphs(self):
        """只有等于 base64(当前 cid) 的那些才是水印，别的一律保留。"""
        frag = body_api_fragment(
            self._rule(),
            self._payload('<p data-limit="MTAwODEyNTg1">正文</p>'),
            "1001396", 1, "100812587")
        self.assertIn("正文", frag)

    def test_bad_json_returns_empty(self):
        self.assertEqual(body_api_fragment(self._rule(), "<html>nope</html>",
                                           "1", 1, "2"), "")
        self.assertEqual(body_api_fragment(self._rule(), "", "1", 1, "2"), "")

    def test_missing_content_field_returns_empty(self):
        import json
        raw = json.dumps({"status": 200, "data": {}})
        self.assertEqual(body_api_fragment(self._rule(), raw, "1", 1, "2"), "")


class TestAuthorPattern(unittest.TestCase):
    """作者与书名挤在同一行时按正则取作者（书海 `.book-info-bookname`）。"""

    def test_author_pattern_extracts_name(self):
        from noveldown.rules import Rule
        rule = Rule({
            "id": "t.ap", "name": "T", "match": ["x.com"], "free_only": True,
            "book": {"url_pattern": "/book/(\\d+)",
                     "title": ["@title"],
                     "title_pattern": "^\\s*([^-]+?)\\s*-",
                     "author": [".book-info-bookname"],
                     "author_pattern": "作者[:：]\\s*(.+?)\\s*$"},
            "catalog": {"item_selector": "a"},
            "chapter": {"content_selector": "div.c"},
        }).validate()
        html = ("<html><head><title>神农医婿 - 方长 - 都市 - 书海小说网</title></head>"
                "<body><div class='book-info-bookname'>神农医婿 作者: 方长</div>"
                "</body></html>")
        info = parse_book_info(rule, html, "https://x.com/book/1.htm", "1")
        self.assertEqual(info["title"], "神农医婿")
        self.assertEqual(info["author"], "方长")

class TestSsrJsonSources(unittest.TestCase):
    """JSON 嵌在 HTML 里的两类通用能力（Next.js / Nuxt 站）。

    实测来源：次元姬 `ciyuanji.com` —— 目录在
    `<script id="__NEXT_DATA__">` 的 `props.pageProps.bookChapter.chapterList`，
    作者在同一数据块的 `...bookChapter.authorName`。
    """

    def _rule(self, **book_over):
        from noveldown.rules import Rule
        book = {"url_pattern": "/chapter/(\\d+)_\\d+", "info_url": "{url}"}
        book.update(book_over)
        return Rule({
            "id": "t.cyj", "name": "T", "match": ["ciyuanji.com"],
            "free_only": True,
            "book": book,
            "catalog": {"mode": "json_api", "json": {
                "url": "{url}",
                "json_source": "script#__NEXT_DATA__",
                "items_path": "props.pageProps.bookChapter.chapterList",
                "cid_field": "chapterId", "title_field": "chapterName",
                "vip_field": "isFee", "vip_truthy": ["1"],
            }, "url_template": "{origin}/chapter/{bid}_{cid}.html",
                "sort": "document_order"},
            "chapter": {"content_selector": "div.c"},
        }).validate()

    HTML = ('<html><head><title>大唐：我真没想当神仙-第十四章 送礼-免费小说阅读-次元姬小说</title>'
            '</head><body><script id="__NEXT_DATA__">'
            '{"props":{"pageProps":{"bookChapter":{"bookName":"大唐：我真没想当神仙",'
            '"authorName":"蓝白","chapterList":['
            '{"chapterId":435750,"chapterName":"第一章 起","isFee":"0"},'
            '{"chapterId":435751,"chapterName":"第二章 承","isFee":"1"}]}}}}'
            '</script></body></html>')

    def test_json_source_extracts_catalog_from_html(self):
        from noveldown.parser import collect_json_catalog
        items, locked = collect_json_catalog(
            self._rule(), self.HTML, "1288", "https://www.ciyuanji.com")
        self.assertEqual([i["cid"] for i in items], ["435750"])
        self.assertEqual([l["cid"] for l in locked], ["435751"])
        self.assertEqual(items[0]["title"], "第一章 起")
        self.assertEqual(items[0]["url"],
                         "https://www.ciyuanji.com/chapter/1288_435750.html")

    def test_json_source_missing_block_raises_with_hint(self):
        from noveldown.parser import collect_json_catalog
        with self.assertRaises(ValueError) as ctx:
            collect_json_catalog(self._rule(), "<html>无数据块</html>",
                                 "1288", "https://x")
        self.assertIn("json_source", str(ctx.exception))

    def test_book_author_from_ssr_json_block(self):
        """`book.author` 支持 `@json:<path>` —— 作者只在数据块里时用。"""
        rule = self._rule(**{
            "title": ["@title"],
            "title_pattern": "^\\s*([^-]+)",
            "author": ["@json:props.pageProps.bookChapter.authorName"],
        })
        info = parse_book_info(rule, self.HTML,
                               "https://www.ciyuanji.com/chapter/1288_1.html", "1288")
        self.assertEqual(info["title"], "大唐：我真没想当神仙")
        self.assertEqual(info["author"], "蓝白")

    def test_book_json_path_missing_falls_back(self):
        rule = self._rule(**{
            "author": ["@json:props.pageProps.nope.nope", ".author-el"],
        })
        html = self.HTML.replace("</body>", '<div class="author-el">备用作者</div></body>')
        info = parse_book_info(rule, html,
                               "https://www.ciyuanji.com/chapter/1288_1.html", "1288")
        self.assertEqual(info["author"], "备用作者")


class TestLxmlCompletenessGuard(unittest.TestCase):
    """lxml 在畸形 HTML 上会**静默丢内容**，必须有完整性守卫。

    实测（飞卢书籍页 2 MB）：原文 `<a>` 12356 个，lxml 只解析出 3128 个，
    章节数从 12188 缩水到 3058，且不报错。
    """

    def test_detects_truncated_parse(self):
        from noveldown.parser import _parse_looks_complete
        raw = "<div class='x'><a href='/1'>t</a></div>" * 100
        tiny = make_soup("<a href='/1'>t</a>")
        self.assertFalse(_parse_looks_complete(raw, tiny))

    def test_accepts_faithful_parse(self):
        from noveldown.parser import _parse_looks_complete
        raw = "<div class='x'><a href='/1'>t</a></div>" * 100
        self.assertTrue(_parse_looks_complete(raw, make_soup(raw)))

    def test_small_pages_not_flagged(self):
        """小页面不做这个校验（阈值以下一律放行），避免误伤。"""
        from noveldown.parser import _parse_looks_complete
        raw = "<a href='/1'>t</a><a href='/2'>u</a>"
        self.assertTrue(_parse_looks_complete(raw, make_soup(raw)))


class TestDropLeadingTitleParagraph(unittest.TestCase):
    """首段即标题（无 class 可剔）时按目录标题精确删除；不匹配就不删。"""

    def _rule(self, **ch_over):
        from noveldown.rules import Rule
        ch = {"content_selector": "div.c"}
        ch.update(ch_over)
        return Rule({
            "id": "t.dt", "name": "T", "match": ["x.com"], "free_only": True,
            "book": {"url_pattern": "/x/(\\d+)"},
            "catalog": {"item_selector": "a"},
            "chapter": ch,
        }).validate()

    HTML = "<html><body><div class='c'><p>第1章 起</p><p>正文一</p><p>正文二</p></div></body></html>"

    def test_drops_when_matches(self):
        res = parse_chapter_page(self._rule(drop_leading_title_paragraph=True),
                                 self.HTML, "https://x.com/x/1", "1",
                                 expect_title="第1章 起")
        self.assertEqual(res["paragraphs"], ["正文一", "正文二"])

    def test_keeps_when_not_matching(self):
        res = parse_chapter_page(self._rule(drop_leading_title_paragraph=True),
                                 self.HTML, "https://x.com/x/1", "1",
                                 expect_title="第1章 别的标题")
        self.assertEqual(res["paragraphs"], ["第1章 起", "正文一", "正文二"])

    def test_off_by_default(self):
        res = parse_chapter_page(self._rule(), self.HTML, "https://x.com/x/1", "1",
                                 expect_title="第1章 起")
        self.assertEqual(res["paragraphs"][0], "第1章 起")


class TestDropLeadingSymbolParagraphs(unittest.TestCase):
    """`chapter.drop_leading_symbol_paragraphs`：丢掉正文头部的**纯符号噪声行**（v0.8.5）。

    实测晋江：正文容器 `div.noveltext` 顶部有一坨无 id/class 的工具栏，
    剔完能命名的元素后仍残留独立的 `[` 与 `]` 两行 —— **没有可用的选择器**，
    但它们只由标点组成，故按「字符全在标点集合内」识别。
    只在**头部**丢：正文中间出现的单独「……」是合理的文学用法。
    """

    def _parse(self, html, **ch_over):
        from noveldown.parser import parse_chapter_page
        from noveldown.rules import Rule
        ch = {"content_selector": "div#c"}
        ch.update(ch_over)
        rule = Rule({
            "id": "t.sym", "name": "T", "match": ["x.com"], "free_only": True,
            "book": {"url_pattern": "/(\\d+)"},
            "catalog": {"item_selector": "a",
                        "id_from": {"mode": "href", "pattern": "(?P<cid>\\d+)"}},
            "chapter": ch,
        }).validate()
        return parse_chapter_page(rule, html, "https://x.com/1/1.html", "1")

    HTML = ('<div id="c">'
            '<div>[</div><div>]</div>'
            '<p>北城的盛夏向来燥热。</p>'
            '<p>……</p>'
            '<p>他说：“后来呢。”</p>'
            '</div>')

    def test_off_by_default(self):
        res = self._parse(self.HTML)
        ps = res["paragraphs"] if isinstance(res, dict) else res
        self.assertEqual(ps[0], "[")

    def test_drops_leading_symbol_lines_only(self):
        res = self._parse(self.HTML, drop_leading_symbol_paragraphs=True)
        ps = res["paragraphs"] if isinstance(res, dict) else res
        self.assertEqual(ps[0], "北城的盛夏向来燥热。")
        # ⚠ 正文**中间**的纯符号行必须保留
        self.assertIn("……", ps)
        self.assertEqual(len(ps), 3)


class TestGuessContentContainer(unittest.TestCase):
    """自动识别正文容器：选择器全失配时的兜底（站点轻微改版可自愈）。

    思路来自 pingcode 那篇方法论文章：正文的特征是「汉字多 + 标点密度高 +
    有段落块 + 链接文字占比低」。
    """

    PROSE = "这是一段用于测试的正文内容，句子里必须有汉字和标点符号。" * 12  # > 200 汉字

    def _page(self, selector="div.nope"):
        from noveldown.rules import Rule
        body = "".join(f"<p>{self.PROSE}</p>" for _ in range(3))
        html = (
            "<html><body>"
            "<div class='nav'>" + "".join(f"<a href='/n{i}'>导航链接{i}</a>" for i in range(20)) + "</div>"
            "<div class='wrap'><article class='prose'>" + body + "</article></div>"
            "<div class='rec'>" + "".join(f"<a href='/r{i}'>推荐位书名{i}</a>" for i in range(20)) + "</div>"
            "</body></html>")
        rule = Rule({
            "id": "t.gc", "name": "T", "match": ["x.com"], "free_only": True,
            "book": {"url_pattern": "/x/(\\d+)"},
            "catalog": {"item_selector": "a"},
            "chapter": {"content_selector": selector},
        }).validate()
        return rule, html

    def test_picks_deepest_body_not_nav(self):
        from noveldown.parser import guess_content_container, make_soup
        _, html = self._page()
        el = guess_content_container(make_soup(html))
        self.assertIsNotNone(el)
        # 应选到最贴身的正文容器，而不是含导航/推荐位的外层
        self.assertEqual(el.get("class"), ["prose"])

    def test_returns_none_without_prose(self):
        from noveldown.parser import guess_content_container, make_soup
        html = ("<html><body><div>" + "".join(
            f"<a href='/n{i}'>短链接{i}</a>" for i in range(50)) + "</div></body></html>")
        self.assertIsNone(guess_content_container(make_soup(html)))

    def test_integration_selector_miss_uses_auto(self):
        """content_selector 写错时，自动识别兜底并留痕。"""
        rule, html = self._page("div.never-matches")
        res = parse_chapter_page(rule, html, "https://x.com/x/1", "1")
        self.assertGreater(len(res["paragraphs"]), 2)
        self.assertIn("自动识别", res["extract_note"])

    def test_auto_content_can_be_disabled(self):
        rule, html = self._page("div.never-matches")
        rule.chapter_cfg["auto_content"] = False
        res = parse_chapter_page(rule, html, "https://x.com/x/1", "1")
        self.assertEqual(res["paragraphs"], [])
        self.assertEqual(res["extract_note"], "")

    def test_configured_selector_still_wins(self):
        """能命中配置选择器时不要走自动识别（否则会破坏既有规则）。"""
        rule, html = self._page("article.prose")
        res = parse_chapter_page(rule, html, "https://x.com/x/1", "1")
        self.assertGreater(len(res["paragraphs"]), 2)
        self.assertNotIn("自动识别", res["extract_note"])



if __name__ == "__main__":
    unittest.main()
