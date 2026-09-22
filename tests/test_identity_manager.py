#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""`identity_manager` 的回归测试（审计 #7：此前**零直接测试**）。

它管的是「浏览器身份轮换」—— 每个请求换一套 UA/平台/header 组合。
退化（比如永远返回同一条）不会报错，只会让站点更容易把你认出来，
所以把「确实在轮换」「字段完整」这两条钉住。

不联网：只读随仓的 `identities.json`。
"""

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from noveldown.identity_manager import (BrowserIdentityManager,  # noqa: E402
                                        get_identity_manager)


class TestIdentityManager(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.mgr = BrowserIdentityManager()

    def test_loads_shipped_identities(self):
        # ⚠ `count` 是 **@property**（我第一版按方法写，跑出来才发现的）
        self.assertGreater(self.mgr.count, 100,
                           "随仓 identities.json 应该有一大批身份")

    def test_identity_shape(self):
        """每条身份要有构建请求头所需的字段。"""
        ident = self.mgr.get_identity(0)
        self.assertIsInstance(ident, dict)
        self.assertTrue(self.mgr.get_ua(ident), "UA 不能为空")

    def test_get_identity_is_index_stable(self):
        """按索引取同一条应稳定（否则「复现某次请求」无从谈起）。"""
        a = self.mgr.get_identity(7)
        b = self.mgr.get_identity(7)
        self.assertEqual(self.mgr.get_ua(a), self.mgr.get_ua(b))

    def test_random_identity_actually_varies(self):
        """⚠ 核心断言：随机取要**真的在轮换**。

        单看一次没意义，所以取一批看有多少个不同的 UA ——
        如果实现退化成「永远返回第一条」，这里立刻挂。
        """
        seen = {self.mgr.get_ua(self.mgr.get_random_identity()) for _ in range(60)}
        self.assertGreater(len(seen), 5, f"随机身份几乎没变化（只见到 {len(seen)} 种 UA）")

    def test_random_ua_varies(self):
        seen = {self.mgr.get_random_ua() for _ in range(60)}
        self.assertGreater(len(seen), 5)

    def test_build_headers_contains_ua(self):
        ident = self.mgr.get_random_identity()
        h = self.mgr.build_headers(ident)
        self.assertIsInstance(h, dict)
        self.assertTrue(h, "headers 不能为空")
        # header 键大小写不敏感，这里统一小写比对
        keys = {k.lower() for k in h}
        self.assertTrue(any("user-agent" in k for k in keys),
                        f"headers 里应有 User-Agent，实际键：{sorted(h)}")

    def test_build_headers_with_referer(self):
        ident = self.mgr.get_random_identity()
        h = self.mgr.build_headers(ident, referer="https://example.com/a")
        vals = " ".join(str(v) for v in h.values())
        self.assertIn("example.com", vals, "给了 referer 就该带上")

    def test_curl_impersonate_may_be_empty_but_not_crash(self):
        """`curl_impersonate` 允许为空（不是每条身份都有），但取用不能抛。"""
        ident = self.mgr.get_random_identity()
        v = self.mgr.get_curl_impersonate(ident)
        self.assertIsInstance(v, str)

    def test_singleton_returns_same_manager(self):
        """`get_identity_manager()` 应复用同一个实例（避免反复解析 674KB JSON）。"""
        self.assertIs(get_identity_manager(), get_identity_manager())

    def test_no_credentials_in_identities(self):
        """⚠ 随仓分发的身份数据里**不能有凭据**（这是 public 仓库的底线）。"""
        import json
        p = os.path.join(ROOT, "noveldown", "identities.json")
        raw = open(p, encoding="utf-8").read().lower()
        for bad in ("password", "passwd", "cookie", "authorization",
                    "api_key", "apikey", "secret", "token", "bearer"):
            self.assertNotIn(f'"{bad}"', raw.replace(" ", ""),
                             f"identities.json 里出现了疑似凭据字段 {bad!r}")


if __name__ == "__main__":
    unittest.main()
