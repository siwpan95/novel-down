#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
构建「字体反爬」解码所需的字形轮廓索引。

背景与方法见 noveldown/fontdecode.py 的模块 docstring（简述：番茄小说把正文
过半汉字替换成 PUA 码位，靠自定义字体渲染；子集字体里没有任何可直接反查的线索，
只能用**同版本**参考字体的字形轮廓做精确匹配。实测 363/363 命中。）

产出物
------
一份 `{字形轮廓哈希: 字符}` 索引（gzip 压缩的 JSON，44 260 条、约 460 KB）。
**它随仓库分发**（`noveldown/fontmaps/sourcehan-sc-2.002.bin`），
因此终端用户**运行时零下载、零参考字体**。**参考字体本体（约 17 MB）不入仓**，
只有维护者在本脚本里重建索引时才按需下载。

用法
----
    # 维护者：重建「随仓索引」（需联网下载 17MB 参考字体，一次性）
    python tools\\build_fontmap.py --shipped --force

    # 开发：只在本地缓存目录生成一份（不覆盖随仓索引）
    python tools\\build_fontmap.py --out output

    # 校验随仓索引可读、条目数正常
    python tools\\build_fontmap.py --verify

依赖：fontTools（+ brotli，读 woff2 时需要；建索引读 otf 不需要）
来源与许可证见 docs/REFERENCE.md 第四节（OFL-1.1）。
"""

import argparse
import hashlib
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from noveldown import fontdecode as fd  # noqa: E402

# ---- 参考字体（唯一已验证可用的版本；换版本会失配，见 fontdecode 模块 docstring）----
# 这些常量**只**服务于「重建索引」这一维护者动作，运行时模块不再持有它们。
REF_FONT_URL = ("https://cdn.jsdelivr.net/gh/adobe-fonts/source-han-sans"
                "@2.002R/OTF/SimplifiedChinese/SourceHanSansSC-Normal.otf")
# 前 16 位（完整 sha256 由下载后打印）
REF_FONT_SHA256 = "69a090057ee75936"

DEFAULT_SHIPPED = os.path.join(ROOT, "noveldown", "fontmaps", fd.REF_INDEX_BIN)


def _fmt(n):
    return f"{n / 1024:.0f} KB" if n < 1024 * 1024 else f"{n / 1024 / 1024:.1f} MB"


def _verify(path):
    idx = fd.load_ref_index(path)
    print(f"[3] 校验：加载 {len(idx)} 个轮廓条目 ✓")
    return 0


def main():
    ap = argparse.ArgumentParser(description="构建字体反爬解码索引")
    ap.add_argument("--out", default="output",
                    help="缓存根目录（默认 output，仅非 --shipped 时使用）")
    ap.add_argument("--shipped", action="store_true",
                    help="写入随仓索引 noveldown/fontmaps/<bin>（维护者用）")
    ap.add_argument("--verify", action="store_true", help="只校验已有索引，不重新构建")
    ap.add_argument("--force", action="store_true", help="已存在也重建")
    args = ap.parse_args()

    if args.shipped:
        idx_path = DEFAULT_SHIPPED
        dist = "随仓（noveldown/fontmaps/）"
    else:
        cache_dir = os.path.join(os.path.abspath(args.out), "fontcache")
        cache_path = os.path.join(cache_dir, fd.REF_INDEX_NAME)
        # --verify 默认看住**随仓**索引（那才是分发物）；不在才退回本地缓存
        if args.verify and os.path.exists(DEFAULT_SHIPPED):
            idx_path, dist = DEFAULT_SHIPPED, "随仓（noveldown/fontmaps/）"
        else:
            idx_path, dist = cache_path, "本地缓存（不入仓）"

    print("=" * 68)
    print("字体反爬解码索引构建")
    print("=" * 68)
    print(f"索引文件：{idx_path}")
    print(f"分发方式：{dist}")
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

    exists = os.path.exists(idx_path)
    if exists and not args.force:
        print(f"[2] 索引已存在：{_fmt(os.path.getsize(idx_path))}（--force 可重建）")
        if args.verify:
            return _verify(idx_path)
    if args.verify:
        print(f"[2] 索引不存在：{idx_path}\n    请去掉 --verify 直接构建。")
        return 1

    # ---- 下载参考字体（仅维护者重建时需要）----
    print("[2] 下载参考字体（维护者重建专用，约 17MB，一次性）")
    print(f"    来源：{REF_FONT_URL}")
    import urllib.request
    data = None
    for attempt in (1, 2):
        try:
            req = urllib.request.Request(REF_FONT_URL, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                              "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"})
            with urllib.request.urlopen(req, timeout=300) as r:
                data = r.read()
            break
        except Exception as e:
            print(f"    第 {attempt} 次下载失败：{e}")
    if not data:
        print("    ✗ 下载失败。可改用镜像；或手动下载后参照本脚本直接用 "
              "fontdecode.build_ref_index(<本地otf>) 生成。")
        return 1

    sha = hashlib.sha256(data).hexdigest()
    print(f"    下载完成：{_fmt(len(data))}  sha256={sha}")
    if not sha.startswith(REF_FONT_SHA256):
        print(f"    ! 指纹与记录不符（期望前缀 {REF_FONT_SHA256}）。")
        print("      参考字体**版本漂移会导致解码全部失配**（实测 2.005 只有 7/363 命中）。")
        print("      如确认是上游更新，请同步更新 fontdecode 模块 docstring 的版本说明后重试。")
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
    if args.shipped:
        print("完成。随仓索引已更新——记得 git add noveldown/fontmaps/ 并提交。")
    else:
        print("完成。本地索引已生成（用于开发/离线校验）。")
    print("  验证：python -m noveldown probe \"https://fanqienovel.com/page/<bookId>\"")
    print("=" * 68)
    return 0


if __name__ == "__main__":
    sys.exit(main())
