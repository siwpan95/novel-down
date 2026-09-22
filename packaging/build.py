#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""novel-down 发行版一键构建（便携版 onedir / onefile + MSI 安装版）。

## 用法（在本仓根目录执行）

    <python> packaging/build.py --all
    <python> packaging/build.py --portable          # 只做便携版
    <python> packaging/build.py --msi               # 只做 MSI
    <python> packaging/build.py --portable --zip    # 顺带打 zip

## 为什么把这些固化成脚本

打包命令里有**几个踩过的坑**，靠记忆拼命令必错：

1. `--add-data` 用**相对路径**会被解析成相对 `--specpath` 的目录 →
   实测报 `Unable to find ...\\build\\noveldown\\rules`。**必须用绝对路径**。
2. 本机 `<你的打包环境>` 装了大量无关包，静态分析会把 numpy / PIL / cryptography /
   curl_cffi / gevent / Cython / pygame 一起打进去 → 产物 **110MB**；
   显式排除后 **约 35MB**。**不排除就是 3 倍体积**。
3. 打包后 Windows 控制台 stdout 是 **GBK**，输出 `⚠` 会直接崩
   （`UnicodeEncodeError: 'gbk' codec can't encode '\\u26a0'`）——
   已在 `entry_console.py` 里强制 UTF-8，**换入口时必须保留那段**。
4. 规则（`noveldown/rules/*.json`）与 `identities.json` 是**数据文件**，
   打包器**不会**自动带，必须 `--add-data` / `include_files`。
5. cx_Freeze 的 `build_exe` 目录若被占用会报
   `the build_exe directory cannot be cleaned` → MSI 用**独立** `--build-base`。

退出码：0 全部成功；1 有失败。
"""

import argparse
import os
import shutil
import subprocess
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
VERSION = "0.8.40"

# ⚠ 与 packaging/setup_cx.py 的 EXCLUDES 保持一致。
# 这些都是**可选能力**，排除后只是对应站点不可用（最小发行版）。
EXCLUDES = [
    "numpy", "PIL", "cryptography", "curl_cffi", "gevent", "Cython", "pygame",
    "scipy", "pandas", "matplotlib", "IPython", "torch", "sklearn",
    "playwright", "fontTools", "brotli", "psutil",
    "pytest", "tests",
]

# 数据文件（**绝对路径**，见上面坑 1）
DATA_ARGS = [
    f"--add-data={os.path.join(ROOT, 'noveldown', 'rules')}"
    f"{os.pathsep}noveldown{os.sep}rules",
    f"--add-data={os.path.join(ROOT, 'noveldown', 'identities.json')}"
    f"{os.pathsep}noveldown",
]


def _run(cmd, cwd=ROOT, env=None):
    print("\n$ " + " ".join(cmd[:6]) + (" …" if len(cmd) > 6 else ""))
    return subprocess.run(cmd, cwd=cwd, env=env).returncode == 0


def build_portable(py, onefile, gui=False):
    """打包一个入口。gui=True 时用 entry_gui.py + --windowed（不弹控制台）。

    ⚠ GUI 版**不能**排除 tkinter（CLI 版要排除，能省 ~10MB）。
    """
    if gui:
        entry = "entry_gui.py"
        name = "noveldown-gui" + ("-onefile" if onefile else "")
        mode = "--windowed"
        excludes = [m for m in EXCLUDES if m != "tkinter"]
    else:
        entry = "entry_console.py"
        name = "noveldown-onefile" if onefile else "noveldown"
        mode = "--console"
        excludes = EXCLUDES
    cmd = [py, "-m", "PyInstaller", os.path.join(HERE, entry),
           f"--name={name}",
           "--onefile" if onefile else "--onedir",
           mode, "--noconfirm"]
    cmd += [f"--exclude-module={m}" for m in excludes]
    cmd += DATA_ARGS
    kind = ("gui-" if gui else "") + ("onefile" if onefile else "onedir")
    cmd += [f"--distpath={os.path.join(ROOT, 'dist')}",
            f"--workpath={os.path.join(ROOT, 'build', kind)}",
            f"--specpath={os.path.join(ROOT, 'build')}"]
    ok = _run(cmd)
    print(("✓ " if ok else "✗ ") + name)
    return ok


def build_msi(py, pkgs):
    """MSI。**必须**用独立 --build-base（否则 build_exe 目录清不掉）。"""
    env = dict(os.environ)
    if pkgs and os.path.isdir(pkgs):
        env["PYTHONPATH"] = pkgs + os.pathsep + env.get("PYTHONPATH", "")
    base = os.path.join(ROOT, "build", "cx")
    ok = _run([py, os.path.join(HERE, "setup_cx.py"),
               "bdist_msi", f"--build-base={base}"], env=env)
    print(("✓ " if ok else "✗ ") + "msi")
    return ok


def zip_portable():
    src = os.path.join(ROOT, "dist", "noveldown")
    if not os.path.isdir(src):
        print("✗ 没有 dist/noveldown，先跑 --portable")
        return False
    dst = os.path.join(ROOT, "dist", f"noveldown-{VERSION}-portable-win64.zip")
    if os.path.exists(dst):
        os.remove(dst)
    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as z:
        for dirpath, _dirs, files in os.walk(src):
            for fn in files:
                full = os.path.join(dirpath, fn)
                z.write(full, os.path.relpath(full, os.path.join(ROOT, "dist")))
    print(f"✓ zip → {dst}  ({os.path.getsize(dst) / 1048576:.1f} MB)")
    return True


def main():
    ap = argparse.ArgumentParser(description="novel-down 发行版构建")
    # ⚠ 默认用**当前解释器**，不硬编码本机路径（审计 #6）：
    #   换机/换盘时旧写法必失败，而且它刚好落在门禁「生产代码不得写死本机路径」的射程内。
    #   本机要指名打包用的 Python 时，显式传 --py <python>。
    ap.add_argument("--py", default=sys.executable,
                    help="打包用的 Python（默认=当前解释器；需已装 requests/bs4/lxml/PyInstaller）")
    ap.add_argument("--pkgs-dir", default=os.path.join(ROOT, ".deps", "pkgs"),
                    help="cx_Freeze 所在目录（pip --target 装），用于 MSI")
    ap.add_argument("--portable", action="store_true", help="便携版（onedir + onefile）")
    ap.add_argument("--gui", action="store_true", help="图形界面版（windowed，不弹控制台）")
    ap.add_argument("--msi", action="store_true", help="MSI 安装版")
    ap.add_argument("--zip", action="store_true", help="把 onedir 压成 zip")
    ap.add_argument("--all", action="store_true", help="便携版 + zip + MSI")
    ap.add_argument("--clean", action="store_true", help="构建前清空 dist/ 与 build/")
    args = ap.parse_args()

    if args.all:
        args.portable = args.msi = args.zip = args.gui = True
    if not (args.portable or args.msi or args.zip or args.gui):
        print("请指定 --portable / --gui / --msi / --zip / --all")
        return 1

    if args.clean:
        for d in ("dist", "build"):
            p = os.path.join(ROOT, d)
            if os.path.isdir(p):
                shutil.rmtree(p)
                print("已清空", d)

    ok = True
    if args.portable:
        ok &= build_portable(args.py, onefile=False)
        ok &= build_portable(args.py, onefile=True)
    if args.gui:
        # GUI 只出 onedir：onefile 每次解包 + 杀软扫描要 47 秒，对双击启动的 GUI 不可接受
        ok &= build_portable(args.py, onefile=False, gui=True)
    if args.zip:
        ok &= zip_portable()
    if args.msi:
        ok &= build_msi(args.py, args.pkgs_dir)

    print("\n" + ("全部成功 → dist/" if ok else "有步骤失败，见上方 ✗"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
