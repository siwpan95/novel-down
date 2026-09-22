#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""烟雾测试：所有模块**都能导入**。

⚠ 为什么专门写这一条（2026-09-22，同一个坑我踩了三次）：

    1. `engine.discover()` 里 `raise RuleError(...)` —— 忘了 import → 跑到才 NameError；
    2. `cli.main()` 里 `except BrowserUnavailable` —— 又忘了 import；
    3. `http_client` 里新增的正则用了 `re` —— 而那个文件**根本没 import re**
       → 这次更狠：**import 模块就炸**，所有测试一起挂。

    三次都不是逻辑错，而是「用了没引进来的名字」。而当时的测试**全绿** ——
    因为没有任何用例走到那条分支，或者（第 3 次）改动后根本没跑测试就往下做了。

    这条烟雾测试的价值就在于：**它不挑分支**。只要有任何模块在导入期用了未定义的名字，
    `import noveldown.<mod>` 立刻报错。代价是毫秒级。

    经验：**改完任何模块，先 import 一次再往下走** —— 比事后追查快得多。
"""

import importlib
import os
import pkgutil
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import noveldown  # noqa: E402


def _all_modules():
    """枚举 `noveldown` 包下的全部模块名（不含子包的私有测试件）。"""
    names = [noveldown.__name__]
    for m in pkgutil.walk_packages(noveldown.__path__, noveldown.__name__ + "."):
        names.append(m.name)
    return sorted(set(names))


class TestAllModulesImport(unittest.TestCase):

    def test_package_imports(self):
        importlib.import_module("noveldown")

    def test_every_submodule_imports(self):
        """⚠ 逐个导入 —— 任何一个模块在导入期用到未定义的名字都会在这里炸。"""
        failures = []
        for name in _all_modules():
            try:
                importlib.import_module(name)
            except Exception as e:                      # noqa: BLE001
                failures.append(f"{name}: {type(e).__name__}: {e}")
        self.assertEqual(failures, [], "以下模块导入失败：\n  " +
                         "\n  ".join(failures))

    def test_entrypoints_importable(self):
        """CLI / GUI 入口与打包入口都要能导入（打包时才会发现的问题提前暴露）。"""
        for name in ("noveldown.cli", "noveldown.gui", "noveldown.__main__"):
            try:
                importlib.import_module(name)
            except Exception as e:                      # noqa: BLE001
                self.fail(f"{name} 导入失败：{type(e).__name__}: {e}")

    def test_cli_exposes_names_it_catches(self):
        """`main()` 里 except 的异常类必须都在 cli 模块里可见（前两次事故就是这条）。"""
        from noveldown import cli
        for name in ("BrowserUnavailable", "RuleError", "FreeGuardError"):
            self.assertTrue(hasattr(cli, name), f"cli 模块缺 {name}（会在 except 时 NameError）")

    def test_engine_exposes_rule_error(self):
        from noveldown import engine
        self.assertTrue(hasattr(engine, "RuleError"))

    def test_tools_scripts_compile(self):
        """`tools/` 与 `packaging/` 的脚本至少要能**编译**（不要求可导入：它们有副作用）。"""
        import py_compile
        bad = []
        for sub in ("tools", "packaging"):
            d = os.path.join(ROOT, sub)
            for dp, _dn, fns in os.walk(d):
                for fn in fns:
                    if not fn.endswith(".py"):
                        continue
                    fp = os.path.join(dp, fn)
                    try:
                        py_compile.compile(fp, doraise=True)
                    except Exception as e:              # noqa: BLE001
                        bad.append(f"{os.path.relpath(fp, ROOT)}: {e}")
        self.assertEqual(bad, [], "以下脚本编译失败：\n  " + "\n  ".join(bad))


if __name__ == "__main__":
    unittest.main()
