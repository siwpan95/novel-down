#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""novel-down 命令行入口（**打包专用**）。

为什么单独建一个入口，而不是直接打 `noveldown/__main__.py`：

1. ⚠ **PYTHONSAFEPATH**：本机 Python 是嵌入式安装（标准库打包成 zip），
   `PYTHONSAFEPATH=1` 时脚本**不会**自动把自身目录加进 `sys.path`
   —— 必须显式插入，否则 `import noveldown` 失败。
2. 打包后 `noveldown` 包位于 `_internal/`，入口需要保证能找到它。
3. 顶层入口让 `PyInstaller` / `cx_Freeze` 的 `scripts` 配置更直观。
"""

import os
import sys

# ⚠⚠ 打包成 exe 后必须做这一步（实测踩到，否则一运行就崩）：
# Windows 控制台的 stdout/stderr 默认是 **GBK(cp936)**，而本项目输出大量
# `⚠` `✓` `★` `·` 等符号 → `UnicodeEncodeError: 'gbk' codec can't encode '\u26a0'`。
# 在**入口最先**把标准流切成 UTF-8（errors="replace" 保证个别字符也不会崩）。
# 未打包时（python -m noveldown）也无害：终端本就是 UTF-8，reconfigure 幂等。
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

# 打包后（onefile/onedir）包在 sys._MEIPASS 或可执行文件旁，显式补上更稳
if getattr(sys, "frozen", False):
    _base = os.path.dirname(sys.executable)
    for p in (getattr(sys, "_MEIPASS", None), _base,
              os.path.join(_base, "_internal")):
        if p and os.path.isdir(p) and p not in sys.path:
            sys.path.insert(0, p)

from noveldown.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
