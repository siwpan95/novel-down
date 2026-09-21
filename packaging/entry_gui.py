#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""novel-down 图形入口（**打包专用**，与 entry_console.py 对称）。

打包成 `noveldown-gui.exe`：双击即开窗口，不弹控制台。
若目标机器没有可用的 Tk，会**明确提示**并建议改用命令行，而不是静默失败。

⚠ 与 entry_console.py 一样，顶部必须强制 UTF-8：
   打包后 Windows 控制台的 stdout 是 GBK，本项目输出含 `⚠` `✓` 等符号，
   不处理会 `UnicodeEncodeError: 'gbk' codec can't encode '\u26a0'`。
"""

import os
import sys

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

if getattr(sys, "frozen", False):
    _base = os.path.dirname(sys.executable)
    for p in (getattr(sys, "_MEIPASS", None), _base,
              os.path.join(_base, "_internal")):
        if p and os.path.isdir(p) and p not in sys.path:
            sys.path.insert(0, p)

from noveldown.gui import main as gui_main  # noqa: E402

if __name__ == "__main__":
    sys.exit(gui_main())
