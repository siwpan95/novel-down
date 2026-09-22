#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""付费墙判定的**精准度**回归（审计 #15，2026-09-22）。

原来的问题：`PAYWALL_MARKERS` 里有「打开APP」「下载【」这类**泛词**，
而 `check_content` 对**整章正文**做子串匹配 → 正常免费章节里只要出现这些词，
整章被判 blocked、正文被丢弃。

收紧办法不是删词（会连 APP 墙一起漏掉），而是利用 APP 墙的**结构性特征**：
    · 实测 APP 墙（七猫第 21 章）的正文**就是那段提示本身** —— 2 段 78 字；
    · 正常章节的正文是成百上千字。
所以泛词降为**弱信号，只在正文很短时才采信**（阈值 200 字）。

这个文件就是钉住「两头都不能坏」：
  · 真墙要能拦住（否则用户会把占位文本当正文收藏）；
  · 正常长章不能被误杀（否则整章内容白白丢掉）。
"""

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from noveldown.constants import (PAYWALL_MARKERS,  # noqa: E402
                                 PAYWALL_MARKERS_WEAK,
                                 PAYWALL_WEAK_MAX_CHARS)
from noveldown.freeguard import check_content  # noqa: E402
from noveldown.models import STATUS_BLOCKED  # noqa: E402


class TestWeakMarkersOnlyWhenShort(unittest.TestCase):

    def test_weak_marker_in_short_body_is_blocked(self):
        """真 APP 墙：整章正文就是那句提示（实测 78 字）→ 必须拦住。"""
        body = ["扫码下载】客户端，畅读全本"] * 3
        self.assertLessEqual(len("\n".join(body)), PAYWALL_WEAK_MAX_CHARS)
        blocked, status, why = check_content(body)
        self.assertTrue(blocked, f"短正文里的弱信号应判 blocked（实际 {status!r} {why!r}）")
        self.assertEqual(status, STATUS_BLOCKED)

    def test_weak_marker_in_long_body_is_not_blocked(self):
        """⚠ 核心：正常长章里出现「打开APP」这种词，**不该**整章丢弃。"""
        long_body = ["他掏出手机，打开APP看了一眼时间，又塞回兜里。"]
        long_body += ["这是一段完全正常的正文内容，长度足够。"] * 40
        text = "\n".join(long_body)
        self.assertGreater(len(text), PAYWALL_WEAK_MAX_CHARS)
        blocked, status, why = check_content(long_body)
        self.assertFalse(blocked, f"长正文不该因弱信号被判 blocked（{why!r}）")

    def test_strong_marker_still_blocks_even_in_long_body(self):
        """强信号（站点独有整句）不受字数限制 —— 收紧不能把检出能力削掉。"""
        body = ["上QQ阅读APP看书，第一时间看更新"]
        body += ["正常正文内容，足够长。" * 20] * 5
        self.assertGreater(len("\n".join(body)), PAYWALL_WEAK_MAX_CHARS)
        blocked, status, _why = check_content(body)
        self.assertTrue(blocked, "强信号在任何长度下都应拦住")
        self.assertEqual(status, STATUS_BLOCKED)

    def test_strong_and_weak_tables_do_not_overlap(self):
        """同一句不该同时在两档里（否则档位语义就乱了）。"""
        overlap = set(m.lower() for m in PAYWALL_MARKERS) & \
            set(m.lower() for m in PAYWALL_MARKERS_WEAK)
        self.assertEqual(overlap, set(), f"两档不应重叠：{sorted(overlap)}")

    def test_weak_markers_are_actually_generic(self):
        """弱信号表里的词应该**都是**那种「单独看很泛」的 —— 防止有人把强词挪进来。"""
        for w in PAYWALL_MARKERS_WEAK:
            self.assertLessEqual(len(w), 8, f"{w!r} 看起来更像强信号（整句），不该在弱表里")

    def test_empty_body_is_empty_not_blocked(self):
        """空正文是 empty，不是 blocked —— 两个状态语义不同，别混。"""
        blocked, status, _why = check_content([])
        self.assertFalse(blocked)
        self.assertNotEqual(status, STATUS_BLOCKED)


if __name__ == "__main__":
    unittest.main()
