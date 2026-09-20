#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
浏览器路由的**可单测部分**：反检测启动参数与语言自洽脚本。

真正的启动需要本机 Chrome（而且必须 headed），不适合放进单测；这里只锁住
「配置对不对」—— 恰恰是反检测能否生效的关键三件套：

  · `channel="chrome"` 用**真** Chrome，而非 playwright 捆绑 Chromium；
  · `headless=False`   —— 捆绑 Chromium + headless 会在 `sec-ch-ua` 里
    明写 `HeadlessChrome`，一行就被识破；
  · `--disable-blink-features=AutomationControlled` 关掉「受自动化控制」特征。

另：本仓**不随仓分发任何第三方 stealth 源码**（可选外挂，用户自备）。
实测结论见 docs/RULES.md 的起点小节与 CHANGELOG。
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from noveldown import browser as br  # noqa: E402


class TestAntiDetectLaunch(unittest.TestCase):

    def test_antidetect_uses_real_chrome_headed_with_args(self):
        kw = br.BrowserFetcher(anti_detect=True).launch_kwargs()
        self.assertEqual(kw["channel"], "chrome")      # 真 Chrome，非捆绑 Chromium
        self.assertFalse(kw["headless"])               # headless 会暴露 HeadlessChrome
        self.assertEqual(kw["args"], br.DEFAULT_LAUNCH_ARGS)

    def test_antidetect_channel_override_and_extra_args(self):
        kw = br.BrowserFetcher(anti_detect=True, channel="chrome-beta",
                               args=["--foo"]).launch_kwargs()
        self.assertEqual(kw["channel"], "chrome-beta")
        self.assertEqual(kw["args"], br.DEFAULT_LAUNCH_ARGS + ["--foo"])

    def test_plain_mode_honours_headless(self):
        self.assertEqual(br.BrowserFetcher(headless=True).launch_kwargs(),
                         {"headless": True})
        self.assertEqual(
            br.BrowserFetcher(headless=False, channel="msedge",
                              args=["--a"]).launch_kwargs(),
            {"headless": False, "channel": "msedge", "args": ["--a"]})

    def test_default_launch_args_disable_automation_flag(self):
        joined = " ".join(br.DEFAULT_LAUNCH_ARGS)
        self.assertIn("AutomationControlled", joined)   # 最关键的暴露项
        self.assertTrue(all(a.startswith("--") for a in br.DEFAULT_LAUNCH_ARGS))

    def test_no_third_party_stealth_is_shipped(self):
        """本仓**不带任何第三方 stealth 源码**（铁律：第三方源码不入仓）。

        实测「真 Chrome + headed + 关 AutomationControlled + 语言自洽」已足够，
        故 stealth 只作为可选的**用户自备外挂**存在，默认未配置。
        """
        pkg = os.path.dirname(os.path.dirname(br.__file__))
        self.assertFalse(os.path.exists(os.path.join(pkg, "noveldown", "vendor")),
                         "不得存在 noveldown/vendor/ 目录")
        self.assertEqual(br.BrowserFetcher(anti_detect=True).stealth_js, "",
                         "默认不得引用任何 stealth 脚本")

    def test_stealth_hook_is_opt_in(self):
        """可选外挂：显式给路径才启用；给不存在的路径时自动跳过。"""
        bf = br.BrowserFetcher(anti_detect=True, stealth_js=r"Z:\no\stealth.js")
        self.assertEqual(bf.stealth_js, r"Z:\no\stealth.js")

    def test_consistency_js_aligns_language(self):
        """语言自洽脚本：navigator.languages 必须被对齐到中文。"""
        self.assertIn("navigator", br.CONSISTENCY_JS)
        self.assertIn("languages", br.CONSISTENCY_JS)
        self.assertIn("zh-CN", br.CONSISTENCY_JS)


class TestAntiDetectAvailability(unittest.TestCase):

    def test_availability_shape(self):
        ok, why = br.anti_detect_available()
        self.assertIsInstance(ok, bool)
        self.assertIsInstance(why, str)
        if not ok:
            self.assertIn("Chrome", why)


if __name__ == "__main__":
    unittest.main()
