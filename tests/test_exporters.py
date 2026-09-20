#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""导出器测试：TXT / Markdown / EPUB3 / 单文件 HTML 阅读器。"""

import json
import os
import re
import sys
import unittest
import zipfile
from xml.etree import ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from noveldown.exporters import EXPORTERS, export_all  # noqa: E402
from noveldown.models import Chapter, STATUS_BLOCKED, STATUS_OK  # noqa: E402
from tests._base import make_book, temp_subdir  # noqa: E402


class TestExporters(unittest.TestCase):

    def setUp(self):
        self.book = make_book(n=3)
        # 共享临时目录：本机文件系统慢（见 tests/_base.temp_root 说明），
        # 每个用例只新建一个子目录、不做删除。
        self.out = temp_subdir("exp")

    def test_all_four_formats_registered(self):
        self.assertEqual(set(EXPORTERS), {"txt", "md", "epub", "html"})

    def test_export_all_produces_files(self):
        res = export_all(self.book, self.out)
        self.assertEqual(set(res), {"txt", "md", "epub", "html"})
        for fmt, path in res.items():
            self.assertTrue(os.path.exists(path), f"{fmt} 未生成")
            self.assertGreater(os.path.getsize(path), 200, f"{fmt} 内容过小")

    def test_txt_contains_all_chapters(self):
        p = EXPORTERS["txt"](self.book, self.out)
        text = open(p, encoding="utf-8").read()
        self.assertIn(self.book.title, text)
        for ch in self.book.chapters:
            self.assertIn(ch.title, text)
        self.assertIn("章节：3", text)

    def test_md_has_front_matter_and_headings(self):
        p = EXPORTERS["md"](self.book, self.out)
        text = open(p, encoding="utf-8").read()
        self.assertTrue(text.startswith("---\n"))
        self.assertIn(f'title: "{self.book.title}"', text)
        self.assertIn("# " + self.book.title, text)
        self.assertIn("### " + self.book.chapters[0].title, text)

    # ---------------- EPUB 结构 ----------------
    def test_epub_is_valid_epub3_container(self):
        p = EXPORTERS["epub"](self.book, self.out)
        z = zipfile.ZipFile(p)
        self.assertIsNone(z.testzip(), "ZIP 应完整")
        names = z.namelist()

        # mimetype 必须是第一个条目且不压缩
        self.assertEqual(names[0], "mimetype")
        self.assertEqual(z.getinfo("mimetype").compress_type, zipfile.ZIP_STORED)
        self.assertEqual(z.read("mimetype").decode(), "application/epub+zip")

        # 必备文件齐备且 XML 合法
        for req in ("META-INF/container.xml", "OEBPS/content.opf",
                    "OEBPS/nav.xhtml", "OEBPS/toc.ncx", "OEBPS/style.css"):
            self.assertIn(req, names)
            if req.endswith((".xml", ".opf", ".xhtml", ".ncx")):
                ET.fromstring(z.read(req))

        # OPF 自洽：manifest / spine 数量一致
        root = ET.fromstring(z.read("OEBPS/content.opf"))
        ns = {"opf": "http://www.idpf.org/2007/opf"}
        items = root.findall(".//opf:item", ns)
        refs = root.findall(".//opf:itemref", ns)
        self.assertEqual(root.get("version"), "3.0")
        self.assertEqual(len(refs), len(self.book.chapters))
        ids = {i.get("id") for i in items}
        for r in refs:
            self.assertIn(r.get("idref"), ids, "spine 引用的 id 必须在 manifest 中")

        # nav 里的 toc 链接必须指向真实存在的章节文件
        nav = z.read("OEBPS/nav.xhtml").decode()
        toc_nav = re.search(r'<nav epub:type="toc".*?</nav>', nav, re.S)
        self.assertIsNotNone(toc_nav, "必须有 epub:type=toc 的导航")
        hrefs = re.findall(r'href="(text/[^"]+)"', toc_nav.group(0))
        self.assertEqual(len(hrefs), len(self.book.chapters))
        for h in hrefs:
            self.assertIn("OEBPS/" + h, names)

    def test_epub_chapter_body_matches_source(self):
        p = EXPORTERS["epub"](self.book, self.out)
        z = zipfile.ZipFile(p)
        xhtml = z.read("OEBPS/text/chapter_0001.xhtml").decode()
        for para in self.book.chapters[0].paragraphs:
            self.assertIn(para, xhtml)
        # 必须有 XML 声明与命名空间（阅读器严格校验）
        self.assertTrue(xhtml.startswith("<?xml"))
        self.assertIn('xmlns="http://www.w3.org/1999/xhtml"', xhtml)

    def test_epub_escapes_special_chars(self):
        book = make_book(n=1)
        book.chapters[0].paragraphs = ['含 <标签> 与 & 与 "引号" 的正文' * 5]
        p = EXPORTERS["epub"](book, self.out)
        z = zipfile.ZipFile(p)
        xhtml = z.read("OEBPS/text/chapter_0001.xhtml").decode()
        ET.fromstring(xhtml)          # 必须仍是合法 XML
        self.assertIn("&lt;标签&gt;", xhtml)

    # ---------------- HTML 阅读器 ----------------
    def test_html_reader_embeds_data_and_ui(self):
        p = EXPORTERS["html"](self.book, self.out)
        html = open(p, encoding="utf-8").read()
        m = re.search(r'<script id="book" type="application/json">(.*?)</script>',
                      html, re.S)
        self.assertIsNotNone(m, "阅读器必须内嵌 JSON 数据")
        raw = (m.group(1).replace("\\u003c", "<")
                          .replace("\\u003e", ">")
                          .replace("\\u0026", "&"))
        data = json.loads(raw)
        self.assertEqual(len(data["chapters"]), 3)
        self.assertEqual(data["chapters"][0]["p"], self.book.chapters[0].paragraphs)
        # UI 关键部件
        for token in ('id="toc"', 'id="q"', 'data-theme', "localStorage",
                      "ArrowRight", 'id="cfgBtn"'):
            self.assertIn(token, html)
        self.assertNotIn("__BOOK_JSON__", html, "占位符必须被替换")

    def test_html_reader_escapes_script_close_tag(self):
        """正文含 </script> 时不得提前闭合内嵌 JSON 脚本。"""
        book = make_book(n=1)
        book.chapters[0].paragraphs = ["危险内容 </script><script>alert(1)</script>" * 3]
        p = EXPORTERS["html"](book, self.out)
        html = open(p, encoding="utf-8").read()
        m = re.search(r'<script id="book" type="application/json">(.*?)</script>',
                      html, re.S)
        self.assertIsNotNone(m)
        self.assertNotIn("</script>", m.group(1))
        self.assertIn("\\u003c", m.group(1))

    # ---------------- 拦截 ----------------
    def test_export_refuses_on_leaked_content(self):
        """受保护章节**携带正文**时必须拒绝导出（拦截失效的信号）。"""
        from noveldown.freeguard import FreeGuardError
        self.book.chapters.append(
            Chapter(index=99, title="VIP章", url="u", cid="9999",
                    status=STATUS_BLOCKED,
                    paragraphs=["这段付费正文不该存在"]))
        with self.assertRaises(FreeGuardError):
            export_all(self.book, self.out)

    def test_export_succeeds_when_protected_are_empty(self):
        """存在受保护章节但正文为空 —— 正常状态，应正常导出且不含它们。

        （含 VIP 的正版站就是这样：一本书 700 章里 650 章是 VIP。）
        """
        from noveldown.freeguard import assert_no_protected
        from noveldown.models import STATUS_LOCKED
        for i in range(90, 95):
            self.book.chapters.append(
                Chapter(index=i, title=f"VIP{i}", url="u", cid=str(9000 + i),
                        status=STATUS_LOCKED, note="目录项 class 命中 'vip'"))
        assert_no_protected(self.book.chapters, context="测试")   # 不得抛错
        res = export_all(self.book, self.out)
        self.assertEqual(set(res), {"txt", "md", "epub", "html"})
        import zipfile
        z = zipfile.ZipFile(res["epub"])
        chs = [n for n in z.namelist() if n.startswith("OEBPS/text/chapter_")]
        self.assertEqual(len(chs), 3, "受保护章节不得进入 EPUB")
        txt = open(res["txt"], encoding="utf-8").read()
        for i in range(90, 95):
            self.assertNotIn(f"VIP{i}", txt)

    def test_export_skips_unfetched_chapters(self):
        from noveldown.models import STATUS_PENDING
        self.book.chapters.append(
            Chapter(index=99, title="未抓章", url="u", status=STATUS_PENDING))
        p = EXPORTERS["epub"](self.book, self.out)
        z = zipfile.ZipFile(p)
        chs = [n for n in z.namelist() if n.startswith("OEBPS/text/chapter_")]
        self.assertEqual(len(chs), 3, "未抓取的章节不得进入 EPUB")


if __name__ == "__main__":
    unittest.main()
