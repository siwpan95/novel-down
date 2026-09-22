#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""`ratelimit.RateLimiter` 的回归测试（审计 #7：此前**零直接测试**）。

它是「线程池 + 连接池 + 限速」这条链路上唯一节制请求速率的东西，
自适应降速（遇到 429/403 时 `slowdown`、平稳时 `recover`）一旦退化，
表现为「平时没事、被站点封了才知道」。所以把它的基本不变量钉住。

不联网、不 sleep 太久（用很小的 delay，总耗时 < 1s）。
"""

import os
import sys
import threading
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from noveldown.ratelimit import RateLimiter  # noqa: E402


class TestRateLimiter(unittest.TestCase):

    def test_effective_delay_within_jitter(self):
        """有效延迟必须落在 [delay-jitter, delay+jitter] 内（抖动量不能失控）。"""
        rl = RateLimiter(delay=0.1, jitter=0.05)
        for _ in range(30):
            d = rl._effective_delay()
            self.assertGreaterEqual(d, 0.1 - 0.05 - 1e-9)
            self.assertLessEqual(d, 0.1 + 0.05 + 1e-9)

    def test_zero_jitter_is_deterministic(self):
        rl = RateLimiter(delay=0.05, jitter=0.0)
        self.assertAlmostEqual(rl._effective_delay(), 0.05, places=6)

    def test_delay_never_negative(self):
        """jitter 比 delay 大时也不能出现负延迟（负数会让 time.sleep 抛错）。"""
        rl = RateLimiter(delay=0.01, jitter=5.0)
        for _ in range(20):
            self.assertGreaterEqual(rl._effective_delay(), 0.0)

    def test_slowdown_increases_then_caps(self):
        """⚠ 自适应降速：遇到限流要变慢，且有上限（不能无限涨到把任务卡死）。

        ⚠ `stats` 是 **@property**（不是方法）；并且 `cap` 限的是**倍率**、
        不是「秒数」—— 我第一版按「延迟秒数」写，跑出来才发现接口不是那样。
        """
        rl = RateLimiter(delay=0.05, jitter=0.0)
        first = rl.stats["slowdown"]
        self.assertAlmostEqual(first, 1.0, places=6)
        for _ in range(50):
            rl.slowdown()
        grown = rl.stats["slowdown"]
        self.assertGreater(grown, first, "slowdown 后倍率应变大")
        self.assertLessEqual(grown, 8.0 + 1e-6, "倍率应有上限（默认 cap=8.0）")
        # 倍率确实作用到了有效延迟上
        self.assertGreater(rl.stats["effective_delay"], 0.05)

    def test_recover_returns_to_baseline_not_below(self):
        rl = RateLimiter(delay=0.05, jitter=0.0)
        rl.slowdown()
        rl.slowdown()
        high = rl.stats["slowdown"]
        for _ in range(200):
            rl.recover()
        low = rl.stats["slowdown"]
        self.assertLess(low, high, "recover 后倍率应变小")
        # 下限是 1.0：不该掉到 0 或负数，那样等于「无限速」
        self.assertGreaterEqual(low, 1.0 - 1e-9)
        self.assertAlmostEqual(low, 1.0, places=6)

    def test_stats_shape(self):
        rl = RateLimiter(delay=0.2, jitter=0.1)
        s = rl.stats                     # ← property，不是方法
        self.assertIsInstance(s, dict)
        for k in ("tickets", "total_wait", "slowdown", "effective_delay"):
            self.assertIn(k, s)
            self.assertIsInstance(s[k], (int, float))
        self.assertEqual(s["tickets"], 0)

    def test_wait_is_serialized_across_threads(self):
        """⚠ 核心不变量：`wait()` 必须**串行**放行 —— 并发线程之间也要维持间隔。

        这是模块存在的意义：若它退化成「各线程各睡各的」，限速就形同虚设。
        """
        rl = RateLimiter(delay=0.08, jitter=0.0)
        stamps = []
        lock = threading.Lock()

        def worker():
            rl.wait()
            with lock:
                stamps.append(time.monotonic())

        ths = [threading.Thread(target=worker) for _ in range(4)]
        t0 = time.monotonic()
        for t in ths:
            t.start()
        for t in ths:
            t.join(timeout=10)
        elapsed = time.monotonic() - t0

        self.assertEqual(len(stamps), 4)
        # 4 次 wait、每次至少 0.08s → 总耗时必须明显大于「一次 delay」
        self.assertGreater(elapsed, 0.08 * 2,
                           f"wait() 没有串行放行（总耗时 {elapsed:.3f}s 太短）")


if __name__ == "__main__":
    unittest.main()
