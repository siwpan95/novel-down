#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""`http_client` 的回归测试（审计 #7：此前**零直接测试**）。

覆盖两块：
  1. **纯函数**（不需要网络）：`parse_proxy` / `build_headers` / `auto_referer`；
  2. **重试退避**：用假的 session 注入，验证「哪类响应会重试、哪类不会」——
     这是本模块最容易悄悄退化的地方（比方说把 429 当成功返回，
     表现就是「被限流了还在猛发请求」）。

⚠ 全程不联网：网络层用 monkeypatch 替换掉。
"""

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from noveldown import http_client as hc  # noqa: E402


class _FakeResp:
    def __init__(self, status=200, text="ok", headers=None):
        self.status_code = status
        self.text = text
        self.content = text.encode("utf-8")
        self.headers = headers or {"Content-Type": "text/html; charset=utf-8"}
        self.url = "https://example.com/"
        self.encoding = "utf-8"
        self.apparent_encoding = "utf-8"

    def raise_for_status(self):
        if self.status_code >= 400:
            raise _FakeHTTPError(self.status_code)


# ⚠ 必须**继承 requests 的 HTTPError**：`http_get` 里 `except requests.exceptions.HTTPError`
#   才走「反爬状态码额外等待」那条分支；用普通 Exception 会直接冒出去、绕过重试逻辑
#   （我第一版就是普通 Exception，结果 403/429 用例全挂）。
import requests as _requests  # noqa: E402


class _FakeHTTPError(_requests.exceptions.HTTPError):
    def __init__(self, code):
        super().__init__(f"HTTP {code}")
        self.response = type("R", (), {"status_code": code})()


class TestPureHelpers(unittest.TestCase):

    def test_parse_proxy_empty_returns_none(self):
        # ⚠ 真实实现返回 **None**（不是 {}）—— 我第一版按 {} 写，跑出来才发现
        self.assertIsNone(hc.parse_proxy(""))
        self.assertIsNone(hc.parse_proxy("   "))
        self.assertIsNone(hc.parse_proxy(None))

    def test_parse_proxy_fills_both_schemes(self):
        p = hc.parse_proxy("http://127.0.0.1:7890")
        self.assertEqual(p.get("http"), "http://127.0.0.1:7890")
        self.assertEqual(p.get("https"), "http://127.0.0.1:7890")

    def test_auto_referer_returns_origin(self):
        self.assertEqual(hc.auto_referer("https://a.com/b/c?d=1"), "https://a.com/")
        self.assertTrue(hc.auto_referer("https://a.com/x").endswith("/"))

    def test_build_headers_has_ua(self):
        h = hc.build_headers()
        self.assertTrue(any(k.lower() == "user-agent" for k in h),
                        f"默认请求头里应有 UA：{sorted(h)}")

    def test_build_headers_respects_custom_ua(self):
        h = hc.build_headers(custom_ua="MyAgent/1.0")
        self.assertIn("MyAgent/1.0", str(h.values()))

    def test_build_headers_with_referer(self):
        h = hc.build_headers(referer="https://r.com/p")
        self.assertIn("https://r.com/p", str(h.values()))


class TestRetryBackoff(unittest.TestCase):
    """⚠ 重试语义（按**真实实现**钉住，不是按我以为的逻辑）：

        `http_get` 的循环是 `for attempt in range(retries + 1)`，任何异常都会继续下一轮
        —— 也就是说**包括 404**（由 `raise_for_status` 抛出 HTTPError 后落到 `last_error`）。
        而 403/412/429/503（`ANTICRAWL_STATUS_CODES`）会额外 `sleep(5 * (attempt+1))`。

    ⚠ 因此测试里**必须把 `time.sleep` 打桩**，否则每条反爬用例都要真等 5~15 秒。
    """

    def setUp(self):
        self.codes = []          # 每次 get 见到什么状态码
        self.calls = 0
        self.retry_events = []
        self._saved_sess = hc._thread_session
        self._saved_sleep = hc.time.sleep
        hc.time.sleep = lambda s: self.retry_events.append(("sleep", s))

    def tearDown(self):
        hc._thread_session = self._saved_sess
        hc.time.sleep = self._saved_sleep

    def _install(self, statuses):
        seq = list(statuses)

        class S:
            def __init__(self):
                self.n = 0
                self.cookies = type("C", (), {"clear": lambda _s: None})()

            def get(self, url, **kw):
                outer.calls += 1
                self.n += 1
                code = seq[min(self.n - 1, len(seq) - 1)]
                outer.codes.append(code)
                if code >= 400:
                    raise _FakeHTTPError(code)
                return _FakeResp(status=code)

        # ⚠ 必须**复用同一个实例**：`http_get` 每轮都会调 `_thread_session()`，
        #   若每次返回新对象，计数归零 → 永远只看到第一个状态码
        #   （我第一版写成 `lambda: S()`，于是 429 用例永远拿到 429、重试到上限后抛出）。
        inst = S()
        outer = self
        hc._thread_session = lambda: inst

    def test_success_returns_first_try(self):
        self._install([200])
        r = hc.http_get("https://example.com/x", retries=2, timeout=1)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.calls, 1, "成功不该重试")

    def test_429_triggers_retry_and_anticrawl_wait(self):
        """⚠ 被限流必须重试，且要**额外等待**（而不是立刻再打一下）。"""
        self._install([429, 429, 200])
        r = hc.http_get("https://example.com/x", retries=2, timeout=1,
                        on_retry=lambda a, e, s: self.retry_events.append(("cb", s)))
        self.assertEqual(r.status_code, 200)
        self.assertGreater(self.calls, 1, "429 应该触发重试")
        waits = [s for k, s in self.retry_events if k == "sleep" and s]
        self.assertTrue(waits, "429 走反爬分支时应额外等待")
        self.assertTrue(any(w >= 5 for w in waits), f"反爬等待应 >=5s，实际 {waits}")

    def test_403_triggers_retry(self):
        self._install([403, 200])
        r = hc.http_get("https://example.com/x", retries=2, timeout=1)
        self.assertEqual(r.status_code, 200)
        self.assertGreater(self.calls, 1, "403 应该触发重试")

    def test_404_also_retries_but_without_anticrawl_wait(self):
        """⚠ 如实记录**当前实现**：404 也会重试（它走的是通用异常分支）。

        这不是「期望的行为」，而是**现状**——把现状钉住，将来若有意改成
        「4xx 不重试」，这条测试会失败，提醒改的人一并更新文档。
        关键是：404 **不该**触发反爬的那种 5 秒级等待。
        """
        self._install([404, 404, 404])
        with self.assertRaises(Exception):
            hc.http_get("https://example.com/x", retries=1, timeout=1)
        self.assertEqual(len(self.codes), 2, f"retries=1 → 共 2 次尝试，实际 {len(self.codes)}")
        anticrawl = [s for k, s in self.retry_events if k == "sleep" and s and s >= 5]
        self.assertFalse(anticrawl, f"404 不该走反爬等待，实际 {anticrawl}")

    def test_retries_upper_bound(self):
        """总尝试次数 = retries + 1，不能无限重试。"""
        self._install([500] * 10)
        with self.assertRaises(Exception):
            hc.http_get("https://example.com/x", retries=2, timeout=1)
        self.assertLessEqual(self.calls, 3, f"retries=2 最多 3 次，实际 {self.calls}")


if __name__ == "__main__":
    unittest.main()
