#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
构建「字体反爬」解码所需的字形轮廓索引。

背景与方法见 noveldown/fontdecode.py 的模块 docstring（简述：番茄小说把正文
过半汉字替换成 PUA 码位，靠自定义字体渲染；子集字体里没有任何可直接反查的线索，
只能用**同版本**参考字体的字形轮廓做精确匹配。实测 363/363 命中。）

本脚本做两件事：
  1. 下载参考字体 SourceHanSansSC-Normal **2.002**（OFL-1.1，约 17MB，一次性）
  2. 生成 {字形轮廓哈希: 字符} 索引，压缩缓存到输出目录

索引**不随仓库分发**（约 300KB 的派生数据，且可从公开字体重建），
但**字体本身也不入仓**：它由本脚本按需下载。理由见 docs/REFERENCE.md。

用法：
    F:\\Python314\\python.exe tools\\build_fontmap.py
    F:\\Python314\\python.exe tools\\build_fontmap.py --out output   # 指定缓存目录
    F:\\Python314\\python.exe tools\\build_fontmap.py --verify       # 只校验已存在的索引

依赖：fontTools（+ brotli，读 woff2 时需要；建索引读 otf 不需要）
"""

import argparse
import hashlib
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from noveldown import fontdecode as fd  # noqa: E402


def _fmt(n):
    return f"{n / 1024:.0f} KB" if n < 1024 * 1024 else f"{n / 1024 / 1024:.1f} MB"


def main():
    ap = argparse.ArgumentParser(description="构建字体反爬解码索引")
    ap.add_argument("--out", default="output", help="缓存根目录（默认 output）")
    ap.add_argument("--verify", action="store_true", help="只校验已有索引，不重新构建")
    ap.add_argument("--force", action="store_true", help="已存在也重建")
    args = ap.parse_args()

    cache_dir = os.path.join(os.path.abspath(args.out), "fontcache")
    idx_path = os.path.join(cache_dir, fd.REF_INDEX_NAME)

    print("=" * 68)
    print("字体反爬解码索引构建")
    print("=" * 68)
    print(f"缓存目录：{cache_dir}")
    print(f"索引文件：{os.path.basename(idx_path)}")
    print()

    ok, why = fd.deps_available()
    print(f"[1] 依赖检查：{'可用 ✓' if ok else '不可用 ✗'}")
    if not ok:
        print(f"    {why}")
        return 2
    try:
        import fontTools
        print(f"    fontTools {getattr(fontTools, 'version', '?')}")
    except Exception:
        pass

    if os.path.exists(idx_path) and not args.force:
        size = os.path.getsize(idx_path)
        print(f"[2] 索引已存在：{_fmt(size)}（--force 可重建）")
        if args.verify:
            idx = fd.load_ref_index(idx_path)
            print(f"[3] 校验：加载 {len(idx)} 个轮廓条目 ✓")
            return 0

    if args.verify and not os.path.exists(idx_path):
        print("[2] 索引不存在，无法校验。请去掉 --verify 直接构建。")
        return 1

    # ---- 下载参考字体 ----
    print(f"[2] 下载参考字体（一次性，约 17MB）")
    print(f"    来源：{fd.REF_FONT_URL}")
    import urllib.request
    data = None
    for attempt in (1, 2):
        try:
            req = urllib.request.Request(fd.REF_FONT_URL, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                              "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"})
            with urllib.request.urlopen(req, timeout=300) as r:
                data = r.read()
            break
        except Exception as e:
            print(f"    第 {attempt} 次下载失败：{e}")
    if not data:
        print("    ✗ 下载失败。可改用镜像，或手动下载后放到缓存目录并命名为 "
              "SourceHanSansSC-Normal.otf 再跑本脚本。")
        return 1

    sha = hashlib.sha256(data).hexdigest()
    print(f"    下载完成：{_fmt(len(data))}  sha256={sha[:16]}…")
    if not sha.startswith(fd.REF_FONT_SHA256):
        print(f"    ! 指纹与记录不符（期望 {fd.REF_FONT_SHA256}…）。")
        print("      参考字体**版本漂移会导致解码全部失配**（实测 2.005 只有 7/363 命中）。")
        print("      如确认是上游更新，请同步更新 fontdecode.REF_FONT_SHA256 后重试。")
        return 1
    print("    指纹校验通过 ✓（与已验证版本 2.002 一致）")

    # ---- 构建索引 ----
    print("[3] 构建字形轮廓索引（约 4.5 万字形，需十余秒）")
    import tempfile
    fd_, tmp = tempfile.mkstemp(suffix=".otf")
    os.close(fd_)
    try:
        with open(tmp, "wb") as f:
            f.write(data)
        idx = fd.build_ref_index(tmp, log=lambda m: print(f"    {m.strip()}"))
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass

    size = fd.save_ref_index(idx, idx_path)
    print(f"[4] 索引已写出：{idx_path}")
    print(f"    条目 {len(idx)}，压缩后 {_fmt(size)}")
    print()
    print("=" * 68)
    print("完成。番茄小说等字体反爬站点现在可以解码了。")
    print("  python -m noveldown probe \"https://fanqienovel.com/page/<bookId>\"")
    print("=" * 68)
    return 0


if __name__ == "__main__":
    sys.exit(main())
