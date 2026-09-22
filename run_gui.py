#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""文件级图形入口（薄壳）：供宿主以 `python run_gui.py` 拉起本仓 GUI。

为什么需要它
------------
GUI 本体是**包模块** `noveldown/gui.py`（内部用相对导入 `from .cli import ...`），
只支持 `python -m noveldown.gui`；而 crawl-hub 聚合启动器的约定是
`entry` = **工具目录下的一个文件**，启动方式 `python <entry>`（cwd = 工具目录）。
`packaging/entry_gui.py` 不能顶这个位置（它把 sys.path 指向 packaging/ 自身，
缺 `_MEIPASS` 时 `import noveldown` 会失败），故这里给一个仓根薄壳。

本文件**只**做两件事：把仓根塞进 sys.path → 转交 `noveldown.gui.main`。
不复制任何 GUI 逻辑（与 packaging/entry_gui.py 同为薄壳，区别只在用途：
那个是打包专用，这个是宿主文件级入口专用）。

启动：
    python run_gui.py        （等价于 python -m noveldown.gui）
"""

import os
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from noveldown.gui import main  # noqa: E402  （必须先补 sys.path）

if __name__ == "__main__":
    sys.exit(main())
