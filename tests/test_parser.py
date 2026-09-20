#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""目录归一化 / 目录页发现 / 正文提取测试。"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from noveldown.parser import (catalog_links_from_page, clean_page_title,  # noqa: E402
                              collect_catalog_items, extract_paragraphs,
                              make_soup, normalize_catalog, parse_book_info,
                              parse_chapter_page)
from noveldown.rules import load_rules  # noqa: E402
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


if __name__ == "__main__":
    unittest.main()


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
