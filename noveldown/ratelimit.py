#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
限速器：全局限速 + 抖动。

[复用来源] 本家 webcopier 仓/webcopier/engine.py 的 RateLimiter 类
许可证：内部项目（全哥创建）。
抽取范围：delay / jitter / wait 的限速语义与线程锁实现。
改造点：拆为独立模块；新增 min_interval 自适应（命中反爬后全局降速）。
"""

import random
import threading
import time


class RateLimiter:
    """线程安全的全局限速器。

    语义：任意两次「取票」之间至少间隔 delay ± jitter 秒，
    与并发数解耦（并发只影响同时等待的线程数，不影响请求速率上限）。
    """

    def __init__(self, delay: float = 1.2, jitter: float = 0.8,
                 min_interval: float = 0.0):
        self.delay = max(0.0, float(delay))
        self.jitter = max(0.0, float(jitter))
        self.min_interval = max(0.0, float(min_interval))
        self._lock = threading.Lock()
        self._next_at = 0.0
        self._slowdown = 1.0          # 全局降速倍率（命中反爬后上调）
        self._total_wait = 0.0
        self._tickets = 0

    # --------------------------------------------------------
    #  内部
    # --------------------------------------------------------
    def _effective_delay(self) -> float:
        base = max(self.delay, self.min_interval) * self._slowdown
        if self.jitter > 0:
            base += random.uniform(0.0, self.jitter)
        return base

    # --------------------------------------------------------
    #  对外
    # --------------------------------------------------------
    def wait(self):
        """阻塞直到获得下一次请求许可。"""
        with self._lock:
            now = time.monotonic()
            if now < self._next_at:
                sleep_for = self._next_at - now
            else:
                sleep_for = 0.0
            self._next_at = max(now, self._next_at) + self._effective_delay()
            self._tickets += 1
            self._total_wait += sleep_for
        if sleep_for > 0:
            time.sleep(sleep_for)

    def slowdown(self, factor: float = 1.5, cap: float = 8.0):
        """命中反爬后全局降速。"""
        with self._lock:
            self._slowdown = min(self._slowdown * factor, cap)

    def recover(self, factor: float = 0.95):
        """连续成功后缓慢恢复速率。"""
        with self._lock:
            self._slowdown = max(1.0, self._slowdown * factor)

    @property
    def stats(self) -> dict:
        with self._lock:
            return {
                "tickets": self._tickets,
                "total_wait": round(self._total_wait, 2),
                "slowdown": round(self._slowdown, 2),
                "effective_delay": round(self._effective_delay(), 3),
            }
