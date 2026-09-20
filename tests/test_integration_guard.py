#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
端到端集成测试：用**真实引擎**跑一个本地合成站点，验证免费章节拦截真的生效。

为什么需要这个测试：
  单元测试只验证了 freeguard 的函数本身。但真正要证明的是——
  「受保护的章节**根本不会发出网络请求**」，以及
  「受保护的正文**不会出现在任何导出物里**」。
  所以这里起一个本地 HTTP 服务，把每一次请求都记下来，用真实 Downloader 跑完整链路。

合成站点（127.0.0.1）：
  /book/1/        目录：3 章，其中第 2 章带 class="vip-lock"
  /chap/1.html    正常免费章节
  /chap/2.html    受保护章节（**不应被请求**）
  /chap/3.html    免费页但正文是付费墙占位（"本章为VIP章节…"）
"""

import json
import os
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from noveldown.engine import Downloader  # noqa: E402
from noveldown.freeguard import FreeGuardError  # noqa: E402
from noveldown.models import STATUS_BLOCKED, STATUS_LOCKED, STATUS_OK  # noqa: E402
from noveldown.rules import Rule  # noqa: E402
from tests._base import temp_subdir  # noqa: E402

CATALOG = """<html><head><meta charset="utf-8">
<meta property="og:novel:book_name" content="合成测试书">
<meta property="og:novel:author" content="测试作者">
</head><body>
<div class="listmain"><dl><dt>正文卷</dt>
  <dd><a href="/chap/1.html">第1章 免费章节</a></dd>
  <dd class="vip-lock"><a href="/chap/2.html">第2章 会员专享</a></dd>
  <dd><a href="/chap/3.html">第3章 付费墙占位</a></dd>
</dl></div>
</body></html>"""
CH1 = """<html><head><meta charset="utf-8"></head><body>
<h1>第1章 免费章节</h1>
<div id="content">
  <div id="center_tip">最新网址：www.example.com</div>
  这是第一章的第一段正文，长度足够通过最小字数校验。<br/>
  这是第一章的第二段正文，同样长度足够。<br/>
  这是第一章的第三段正文，用于凑够字数阈值以便通过校验。<br/>
</div>
<div class="read_btn"><a href="/book/1/">章节目录</a><a href="/chap/2.html">下一章</a></div>
</body></html>""" * 1

CH2 = """<html><head><meta charset="utf-8"></head><body>
<h1>第2章 会员专享</h1>
<div id="content">本章为VIP章节，订阅后可阅读全文。</div>
</body></html>"""

CH3 = """<html><head><meta charset="utf-8"></head><body>
<h1>第3章 付费墙占位</h1>
<div id="content">
  本章为VIP章节，订阅后可阅读。
  余额不足，请先充值后继续阅读。
</div>
</body></html>"""


class Handler(BaseHTTPRequestHandler):
    hits = []          # 所有被请求的路径

    def do_GET(self):
        Handler.hits.append(self.path)
        pages = {
            "/book/1/": CATALOG,
            "/chap/1.html": CH1,
            "/chap/2.html": CH2,
            "/chap/3.html": CH3,
        }
        body = pages.get(self.path)
        if body is None:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"not found")
            return
        raw = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, *a):
        pass


RULE_RAW = {
    "id": "127.0.0.1-test",
    "name": "合成测试站",
    "enabled": True,
    "free_only": True,
    "predecode": False,
    "demo_url": None,
    "match": ["127.0.0.1"],
    "book": {
        "url_pattern": "/book/(\\d+)/",
        "info_url": "{origin}/book/{bid}/",
        "title": ["meta[property='og:novel:book_name']"],
        "author": ["meta[property='og:novel:author']"],
    },
    "catalog": {
        "pages": {"mode": "single", "url": "{origin}/book/{bid}/"},
        "item_selector": "div.listmain dl dd a",
        "id_from": {"mode": "href", "pattern": "/chap/(?P<cid>\\d+)\\.html"},
        "sort": "cid_numeric_asc",
    },
    "chapter": {
        "title_selector": "h1",
        "content_selector": "div#content",
        "strip_selectors": ["div#center_tip"],
        "ad_patterns": ["最新网址", "请记住本站"],
    },
}
RULE_RAW.pop("demo_url")


class TestEndToEndFreeGuard(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        Handler.hits = []
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.port}"
        cls.rule = Rule(RULE_RAW).validate()
        cls.out = temp_subdir("e2e")

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def test_full_pipeline_blocks_protected_chapters(self):
        Handler.hits = []
        url = f"{self.base}/book/1/"
        d = Downloader(url, config={
            "save_dir": self.out, "concurrency": 2, "delay": 0.05,
            "jitter": 0.0, "timeout": 10, "retries": 1,
        }, rules={self.rule.id: self.rule}, log=lambda *a, **k: None)

        book = d.run(limit=0)
        by_index = {c.index: c for c in book.chapters}

        # --- 目录层：VIP 标记的章节必须被标 locked ---
        self.assertEqual(len(book.chapters), 3)
        self.assertEqual(by_index[2].status, STATUS_LOCKED,
                         "目录里 class=vip-lock 的章节必须标 locked")
        self.assertIn("vip", by_index[2].note.lower())

        # --- 最关键的断言：受保护章节**根本没被请求过** ---
        requested = set(Handler.hits)
        self.assertNotIn("/chap/2.html", requested,
                         "locked 章节不得发起任何网络请求")

        # --- 免费章节正常抓取 ---
        self.assertEqual(by_index[1].status, STATUS_OK)
        self.assertGreater(by_index[1].char_count, 50)
        self.assertNotIn("最新网址", by_index[1].text, "水印必须被剔除")

        # --- 正文层：付费墙占位必须被拦下且正文清空 ---
        self.assertEqual(by_index[3].status, STATUS_BLOCKED)
        self.assertEqual(by_index[3].paragraphs, [], "受保护正文必须立即丢弃")
        self.assertTrue(by_index[3].is_protected)

        # --- 导出层：受保护章节**不携带正文**，故应拒绝导出（泄漏检查）---
        #    这里手工塞一段正文进去，模拟"拦截失效"，导出必须失败
        by_index[3].paragraphs = ["这里是本不该存在的付费正文"]
        from noveldown.exporters import export_all
        with self.assertRaises(FreeGuardError):
            export_all(book, os.path.join(self.out, "leak"))

        # --- 恢复正常状态（正文为空）后，导出应成功且不含受保护章节 ---
        by_index[3].paragraphs = []
        res = export_all(book, os.path.join(self.out, "clean"))
        self.assertEqual(set(res), {"txt", "md", "epub", "html"})
        txt = open(res["txt"], encoding="utf-8").read()
        self.assertNotIn("会员专享", txt)
        self.assertIn("第1章 免费章节", txt)

    def test_blocked_body_not_persisted_and_export_excludes_it(self):
        """把受保护章节从结果里剔除后，导出应成功且不含任何付费内容。"""
        Handler.hits = []
        url = f"{self.base}/book/1/"
        d = Downloader(url, config={
            "save_dir": temp_subdir("e2e2"), "concurrency": 1, "delay": 0.05,
            "jitter": 0.0, "timeout": 10, "retries": 1,
        }, rules={self.rule.id: self.rule}, log=lambda *a, **k: None)
        book = d.run(limit=0)

        # 缓存里也不得有受保护正文
        for c in book.chapters:
            if c.is_protected:
                cached = d.store.load_chapter(c.cid, c.index)
                if cached:
                    self.assertEqual(cached["paragraphs"], [],
                                     "受保护正文不得落缓存")

        # 只留免费章节后导出，且成品里不得出现付费墙字样
        book.chapters = [c for c in book.chapters if not c.is_protected]
        from noveldown.exporters import export_all
        out = os.path.join(self.out, "ok")
        res = export_all(book, out)
        self.assertEqual(set(res), {"txt", "md", "epub", "html"})
        for fmt, path in res.items():
            if fmt == "epub":
                import zipfile
                z = zipfile.ZipFile(path)
                blob = "\n".join(z.read(n).decode("utf-8", "ignore")
                                 for n in z.namelist()
                                 if n.endswith((".xhtml", ".opf", ".ncx")))
            else:
                blob = open(path, encoding="utf-8").read()
            for marker in ("本章为VIP章节", "订阅后可阅读", "余额不足", "会员专享"):
                self.assertNotIn(marker, blob, f"{fmt} 产物里出现了受保护内容标记")


if __name__ == "__main__":
    unittest.main()
