#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""`cli.main()` 的**异常分支**回归测试。

⚠ 为什么专门为「异常分支」写测试（2026-09-22）：

    这个项目里，**同一个坑我踩了两次**：
      · `engine.discover()` 里 `raise RuleError(...)` —— 忘了 import，跑到才 NameError；
      · `cli.main()` 里 `except BrowserUnavailable` —— **又忘了 import**。
    两次的特征完全一样：**代码逻辑写对了、异常类没引进**，
    而当时所有测试都绿 —— 因为**没有一条用例真正走进那个分支**。

    「测试全绿」不等于「这条路能跑」。所以这里把每条异常分支都**实际触发一次**，
    断言「返回预期的退出码 + 打印了人话」，而不是只测正常路径。

    退出码是 CLI 的对外契约（README 里也写了），所以它值得被钉住。
"""

import io
import os
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from noveldown import cli  # noqa: E402
from noveldown.browser import BrowserUnavailable  # noqa: E402
from noveldown.freeguard import FreeGuardError  # noqa: E402
from noveldown.rules import RuleError  # noqa: E402


class _FakeArgs:
    """顶掉 argparse 的结果，让 main() 直接走到异常分支。"""

    def __init__(self, exc):
        self._exc = exc

    def __getattr__(self, name):
        # main() 只会访问 args.func
        if name == "func":
            def _f(_args):
                raise self._exc
            return _f
        raise AttributeError(name)


class TestMainExceptionBranches(unittest.TestCase):

    def _run(self, exc):
        """跑 main()，返回 (退出码, stderr 文本)。"""
        saved = cli.build_parser
        cli.build_parser = lambda: type("P", (), {
            "parse_args": lambda _s, _a=None: _FakeArgs(exc)})()
        err = io.StringIO()
        try:
            with redirect_stderr(err):
                code = cli.main([])
        finally:
            cli.build_parser = saved
        return code, err.getvalue()

    def test_free_guard_error_returns_2(self):
        code, err = self._run(FreeGuardError("该域名在名单内"))
        self.assertEqual(code, 2, "FreeGuardError 应返回退出码 2")
        self.assertIn("拒绝", err)

    def test_rule_error_returns_4(self):
        code, err = self._run(RuleError("规则写错了"))
        self.assertEqual(code, 4, "RuleError 应返回退出码 4")
        self.assertIn("规则", err)

    def test_file_not_found_returns_5(self):
        code, err = self._run(FileNotFoundError("没这个文件"))
        self.assertEqual(code, 5, "FileNotFoundError 应返回退出码 5")

    def test_browser_unavailable_returns_6_and_is_friendly(self):
        """⚠ 这条正是「忘了 import BrowserUnavailable」时会炸的分支。

        旧代码没捕它 → 用户看到一段原始 traceback；
        现在应返回 6 并给出**可执行的补救指引**。
        """
        code, err = self._run(BrowserUnavailable("该站需要浏览器路由"))
        self.assertEqual(code, 6, "BrowserUnavailable 应返回退出码 6")
        self.assertIn("浏览器路由", err)
        self.assertIn("playwright", err, "应告诉用户装什么")

    def test_exception_classes_are_imported(self):
        """直接钉住「异常类确实被引进来了」——两次事故都是这一条没做到。"""
        for name, mod in (("BrowserUnavailable", "browser"),
                          ("RuleError", "rules"),
                          ("FreeGuardError", "freeguard")):
            self.assertTrue(hasattr(cli, name),
                            f"cli 模块里看不到 {name}（{mod}.py 里的那个）—— "
                            f"main() 里 except 它的时候会 NameError")


if __name__ == "__main__":
    unittest.main()
