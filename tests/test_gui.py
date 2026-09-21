#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""图形界面的回归测试。

分两层：

1. **不依赖 Tk 的纯逻辑**（`_Args`、下拉标签的解析规则）——任何环境都能跑；
2. **需要 Tk 的部分**（真正建一次窗口做启动自检）——用 `skipUnless` 守着，
   没有 Tk 的环境（如 CI 容器）自动跳过，而不是报错。

⚠ 为什么值得测：GUI 与 CLI **共用同一套引擎**，一旦 GUI 传参方式变了
（比如把 `config` 的键名写错），CLI 的测试**发现不了**，只有这里能拦住。
"""

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from noveldown.cli import _config_from_args  # noqa: E402
from noveldown.gui import _Args  # noqa: E402

try:
    import tkinter  # noqa: F401
    _HAS_TK = True
except Exception:
    _HAS_TK = False


class TestGuiArgs(unittest.TestCase):
    """GUI 控件值 → config 的映射必须与 CLI 等价。"""

    def test_args_feeds_config_correctly(self):
        a = _Args(url="https://x.com/book/1", out="out-x", concurrency=7,
                  delay=0.5, timeout=20, retries=2, proxy="", formats="txt,md")
        cfg = _config_from_args(a)
        self.assertEqual(cfg["concurrency"], 7)
        self.assertAlmostEqual(cfg["delay"], 0.5)
        self.assertEqual(cfg["timeout"], 20)
        self.assertEqual(cfg["retries"], 2)
        # save_dir 会被规范化成绝对路径
        self.assertTrue(os.path.isabs(cfg["save_dir"]))
        self.assertTrue(cfg["save_dir"].endswith("out-x"))

    def test_args_has_fields_cli_finish_needs(self):
        """`_finish` 会读 formats / quiet / max_items / report —— 缺了会 AttributeError。"""
        a = _Args(url="u", out="o", concurrency=4, delay=1.0, timeout=30,
                  retries=3, proxy="")
        for k in ("formats", "quiet", "max_items", "report", "limit", "force"):
            self.assertTrue(hasattr(a, k), f"_Args 缺字段 {k}")


class TestSiteLabelParsing(unittest.TestCase):
    """下拉标签 → 规则 id 的解析规则（GUI 用它填 demo_url）。"""

    def _parse(self, label):
        return label.split("] ", 1)[-1].split(" — ")[0].strip()

    def test_parse_common_labels(self):
        self.assertEqual(self._parse("[正版] 17k.com — 17K小说网（正版）"), "17k.com")
        self.assertEqual(self._parse("[镜像] mirror-body-a-0651ba — 免费镜像 · 目录 body a"),
                         "mirror-body-a-0651ba")

    def test_parse_label_without_pool_prefix(self):
        """万一以后改了标签格式，也不该把整串当 id 用（退化成空串更安全）。"""
        self.assertEqual(self._parse("17k.com — 17K小说网"), "17k.com")


@unittest.skipUnless(_HAS_TK, "当前环境没有 Tk，跳过界面启动自检")
class TestGuiBoot(unittest.TestCase):
    """真正建一次窗口（不 mainloop），确认界面能渲染、规则能加载。"""

    def test_window_boots_and_fills_url(self):
        from noveldown.gui import App
        app = App()
        try:
            app.update()                       # 渲染一次，不进 mainloop
            self.assertIn("novel-down", app.title())
            self.assertGreater(len(app.cmb_site["values"]), 10)   # 站点下拉有内容
            self.assertTrue(app.cmb_site.get())                   # 默认选中一项

            # 选中站点应把 demo_url 填进 URL 框（这是 GUI 最主要的省事设计）
            app.cmb_site.current(0)
            app._on_site_pick()
            app.update()
            self.assertTrue(app.var_url.get().startswith("http"),
                            "选中站点后应自动填入示例地址")
        finally:
            app.destroy()


if __name__ == "__main__":
    unittest.main()
