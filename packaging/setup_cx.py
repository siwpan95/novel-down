#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cx_Freeze 构建脚本 —— 生成 **MSI 安装版**。

用法（在本仓根目录执行）：

    # cx_Freeze 装在 .deps/pkgs（不污染系统环境）
    PYTHONPATH=.deps/pkgs F:/Python314/python.exe packaging/setup_cx.py build
    PYTHONPATH=.deps/pkgs F:/Python314/python.exe packaging/setup_cx.py bdist_msi

产物：`dist/novel-down-0.8.37-win64.msi`

⚠ 为什么排除这么多模块：本机 `F:\\Python314` 装了大量与本项目无关的包
（numpy / PIL / cryptography / curl_cffi / gevent / Cython / pygame …），
cx_Freeze 的静态分析会把它们一起打进去 —— 实测不排除时产物 **110MB**，
排除后 **约 35MB**。本项目运行期其实只要 `requests` + `bs4`（+ 可选的 `lxml`）。
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# 与 PyInstaller 版保持一致：**最小依赖**。
# 被排除的都是**可选能力**，缺了只会让对应站点不可用（见 requirements.txt 说明）。
EXCLUDES = [
    # 误打进来的大块（与本项目无关）
    "numpy", "PIL", "cryptography", "curl_cffi", "gevent", "Cython", "pygame",
    "scipy", "pandas", "matplotlib", "IPython", "torch", "sklearn",
    # 本项目的**可选**依赖（最小版不含）
    "playwright", "fontTools", "brotli", "psutil",
    # 开发/测试
    "pytest", "tests",
]

INCLUDE_FILES = [
    (os.path.join(ROOT, "noveldown", "rules"), os.path.join("noveldown", "rules")),
    (os.path.join(ROOT, "noveldown", "identities.json"),
     os.path.join("noveldown", "identities.json")),
    (os.path.join(ROOT, "README.md"), "README.md"),
    (os.path.join(ROOT, "LICENSE"), "LICENSE.txt"),
]

from cx_Freeze import Executable, setup  # noqa: E402

# MSI 的升级码必须**固定**，否则每次构建都会被视为新产品（装出多个并存的条目）。
UPGRADE_CODE = "{8F1B2C3D-4E5A-6B7C-8D9E-0F1A2B3C4D5E}"

setup(
    name="novel-down",
    version="0.8.39",
    description="规则驱动的网络小说离线阅读工具（仅免费章节）",
    options={
        "build_exe": {
            # ⚠ 必须显式指定目录：cx_Freeze 在构建前会**清理**已存在的 build_exe 目录，
            #    若目录已存在且删不掉就报 `the build_exe directory cannot be cleaned`
            #    （实测踩到）。指定到独立路径，并在构建前由 build.py 清掉。
            "build_exe": os.path.join(ROOT, "build", "cx-exe"),
            "packages": ["noveldown"],
            "excludes": EXCLUDES,
            "include_files": INCLUDE_FILES,
            # ⚠ 必须 False：cx_Freeze 会去 %APPDATA%\cxfreeze\vc_redist 下载/加锁 VC 运行库，
            #    本机实测报 `[WinError 5] 拒绝访问 ... vc_redist.x64.lock`（沙箱不允许写）。
            #    现代 Windows 10/11 一般已自带 VC 运行库；若目标机器确实缺，
            #    请在**有权限的环境**下改回 True 重新构建。
            "include_msvcr": False,
            "optimize": 2,
        },
        "bdist_msi": {
            "upgrade_code": UPGRADE_CODE,
            "add_to_path": True,            # 装完即可在命令行直接用 noveldown
            "install_icon": None,
            "summary_data": {
                "author": "siwpan",
                "comments": "仅用于抓取各站点的**免费章节**，请遵守各站点的使用条款。",
                "keywords": "小说;离线阅读;epub;爬虫",
            },
        },
    },
    executables=[
        Executable(
            os.path.join(HERE, "entry_console.py"),
            target_name="noveldown.exe",
            base=None,                      # None = 控制台程序（本项目是 CLI）
            copyright="Copyright (c) 2026 siwpan",
        )
    ],
)
