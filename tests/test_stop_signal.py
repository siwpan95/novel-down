#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""`engine.run(stop_event=...)` 的**协作式取消**回归测试（审计 #3，2026-09-22）。

为什么必须测：
    原来 GUI 的「停止」是在进度回调里抛 `KeyboardInterrupt`，而
    `with ThreadPoolExecutor(...)` 的 `__exit__` 会 `shutdown(wait=True)` ——
    **异常也拦不住它等完所有已提交的 future**。审计用真实引擎实测：
    「第 3 章点停止 → **40/40 全抓完**」，而界面还提示「会在当前章节结束后停下」。

    这个测试就是那个场景的固化：起一个本地合成站（20 章），抓起来之后置位 stop，
    **断言实际请求的章节数远小于总数** —— 证明取消真的生效，而不是「等它跑完」。

⚠ 不能只断言「函数返回了」：旧实现也会正常返回（只是返回时已经全抓完）。
   判据必须是**可观测的请求数**。
"""

import os
import sys
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from noveldown.engine import Downloader  # noqa: E402
from noveldown.rules import Rule  # noqa: E402
from tests._base import temp_subdir  # noqa: E402

N_CH = 20          # 目录里放多少章
CHAP_DELAY = 0.05  # 每章响应故意慢一点，好让「取消」有发挥空间


def _catalog_html():
    items = "\n".join(
        f'  <dd><a href="/chap/{i}.html">第{i}章 测试章节</a></dd>'
        for i in range(1, N_CH + 1))
    return f"""<html><head><meta charset="utf-8">
<meta property="og:novel:book_name" content="停止测试书">
<meta property="og:novel:author" content="测试作者">
</head><body>
<div class="listmain"><dl><dt>正文卷</dt>
{items}
</dl></div>
</body></html>"""


def _chap_html(i):
    return f"""<html><head><meta charset="utf-8"></head><body>
<h1>第{i}章 测试章节</h1>
<div id="content">
  这是第 {i} 章的第一段正文，长度足够通过最小字数校验。<br/>
  这是第 {i} 章的第二段正文，同样长度足够通过校验阈值。<br/>
  这是第 {i} 章的第三段正文，用于凑够字数以便正常落盘。<br/>
</div>
</body></html>"""


class Handler(BaseHTTPRequestHandler):
    chapter_hits = []

    def do_GET(self):  # noqa: N802
        if self.path.startswith("/book/"):
            body = _catalog_html()
        elif self.path.startswith("/chap/"):
            Handler.chapter_hits.append(self.path)
            time.sleep(CHAP_DELAY)          # 让并发真的在跑
            try:
                i = int(self.path.split("/")[2].split(".")[0])
            except Exception:               # noqa: BLE001
                i = 1
            body = _chap_html(i)
        else:
            self.send_response(404)
            self.end_headers()
            return
        data = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):              # 静音
        pass


def _rule(base):
    return Rule({
        "id": "stop-probe", "name": "停止测试站", "pool": "免费镜像",
        "enabled": True, "free_only": True, "fetch_mode": "http",
        "match": ["127.0.0.1"], "demo_url": base + "/book/1/",
        "book": {"url_pattern": r"^.*/book/(?P<bid>\d+)/?$", "info_url": "{url}"},
        "catalog": {
            "pages": {"mode": "single"},
            "item_selector": ".listmain a",
            "id_from": {"mode": "href", "pattern": r"/chap/(?P<cid>\d+)\.html"},
            "sort": "cid_numeric_asc", "dedupe": "keep_first",
        },
        "chapter": {"content_selector": "#content"},
    })


class TestCooperativeStop(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.base = "http://127.0.0.1:%d" % cls.httpd.server_address[1]
        cls.th = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.th.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def _run_with_stop_after(self, n_before_stop, concurrency=2):
        Handler.chapter_hits = []
        rule = _rule(self.base)
        d = Downloader(f"{self.base}/book/1/", config={
            "save_dir": temp_subdir("stop"), "concurrency": concurrency,
            "delay": 0.0, "jitter": 0.0, "timeout": 10, "retries": 1,
        }, rules={rule.id: rule}, log=lambda *a, **k: None)

        ev = threading.Event()
        box = {}

        def worker():
            try:
                box["book"] = d.run(stop_event=ev)
            except Exception as e:              # noqa: BLE001
                box["err"] = e

        t = threading.Thread(target=worker, daemon=True)
        t.start()

        # 等它抓够 n_before_stop 章，再请求停止
        deadline = time.time() + 10
        while len(Handler.chapter_hits) < n_before_stop and time.time() < deadline:
            time.sleep(0.01)
        ev.set()
        t.join(timeout=15)
        self.assertFalse(t.is_alive(), "置位 stop_event 后 run() 应尽快返回")
        return box, len(Handler.chapter_hits)

    def test_stop_actually_cancels_remaining(self):
        """⚠ 核心断言：实际请求的章节数要**远小于**总数。

        旧实现（抛 KeyboardInterrupt）在这里会拿到 N_CH —— 一条都不少。
        """
        box, hits = self._run_with_stop_after(3)
        self.assertNotIn("err", box, f"run() 抛了异常：{box.get('err')}")
        self.assertLess(
            hits, N_CH,
            f"停止没生效：请求了 {hits}/{N_CH} 章（旧实现在这里是全部抓完）")
        # 并发会「提前提交」少量章节，放宽但仍要明显低于总数
        self.assertLessEqual(hits, N_CH // 2, f"取消得太迟：{hits}/{N_CH}")

    def test_stopped_chapters_are_persisted(self):
        """停止后已完成的章节要**已落盘**（断点可续），而不是丢掉。"""
        box, hits = self._run_with_stop_after(3)
        book = box.get("book")
        self.assertIsNotNone(book)
        done = [c for c in book.chapters if c.status == "ok"]
        self.assertGreater(len(done), 0, "已抓到的章节不该为空")
        self.assertLess(len(done), N_CH)

    def test_without_stop_runs_to_completion(self):
        """对照：不置位时应该正常抓完（别把取消写成了「总是提前停」）。"""
        Handler.chapter_hits = []
        rule = _rule(self.base)
        d = Downloader(f"{self.base}/book/1/", config={
            "save_dir": temp_subdir("nostop"), "concurrency": 4,
            "delay": 0.0, "jitter": 0.0, "timeout": 10, "retries": 1,
        }, rules={rule.id: rule}, log=lambda *a, **k: None)
        book = d.run()
        self.assertEqual(len(book.chapters), N_CH)
        done = [c for c in book.chapters if c.status == "ok"]
        self.assertEqual(len(done), N_CH, "不取消时应全部抓完")


if __name__ == "__main__":
    unittest.main()
