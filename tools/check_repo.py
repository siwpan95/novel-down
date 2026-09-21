#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
仓库卫生门禁 —— 机械验证「本仓不含第三方源码、不含凭据、不含产物」。

为什么需要它
------------
本项目刻意**不把参照的第三方源码放进仓库**（见 docs/REFERENCE.md「为什么不把源码放进仓库」）：
FictionDown 是 GPL-3.0、novel-downloader 是 AGPL-3.0-or-later，本项目是 MIT，
把 GPL/AGPL 源码随 MIT 仓分发会让许可状态含混。
但"不含"如果只写在文档里，迟早会有人手滑 `git add -A` 把它带进去。
所以做成 <1 秒可跑的检查。

九项检查
--------
1. 许可文件唯一且为本项目 LICENSE（不得混入第三方 LICENSE/COPYING）
2. 不跟踪第三方源码目录（_ref/ vendor/ node_modules/ third_party/ …）
3. 不跟踪归档（*.zip / *.tar.gz / *.7z / *.rar）
4. 不跟踪产物与缓存（output/ state/ cache/ dist/ build/）
5. 不跟踪凭据（复用 noveldown.freeguard.selfcheck）
6. 文档一致性：docs/REFERENCE.md 必须为每个第三方来源同时给出**上游 URL**与**许可证**
7. 生产代码（noveldown/ tools/ tests/）不得写死本机绝对路径（解释器安装目录/用户目录/开发盘）
8. 无调试残留 / 草稿文件
9. 镜像族规则 `notes` 里的「域数 N」必须等于 `match` 长度（同一事实写在两处必须相等）

用法：
    python tools\\check_repo.py
    python tools\\check_repo.py --selfcheck   # 注入假违规，证明门禁有效
退出码：0 通过；1 失败
"""

import argparse
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# ------------------------------------------------------------
#  黄金值（改这里 = 改约束）
# ------------------------------------------------------------
ALLOWED_LICENSE_FILES = {"LICENSE"}          # 仓库里**只允许根目录这一个**许可文件
LICENSE_BASENAMES = ("LICENSE", "LICENSE.TXT", "LICENSE.MD", "LICENSE.RST",
                     "COPYING", "COPYING.TXT", "COPYING.MD")
FORBIDDEN_DIR_PARTS = (
    "_ref/", "vendor/", "node_modules/", "third_party/", "third-party/",
    "output/", "state/", "cache/", "dist/", "build/", "release/", ".venv/",
)
FORBIDDEN_ARCHIVE_EXT = (".zip", ".tar.gz", ".tgz", ".7z", ".rar", ".xz", ".bz2")

# 生产代码里不得写死**本机环境路径**（解释器安装目录 / 用户目录 / 本机开发盘）。
# 实测踩过：报错指引里写死 `F://Python314//python.exe`，换盘符/换 Python 就废了。
# 正确做法是自发现：`sys.executable`（解释器）、`os.environ`（系统目录）、`shutil.which`（外部命令）。
# 注意：这里只查**生产代码**（noveldown/ 与 tools/*.py），文档里的来源记账（如 本家 webcopier 仓）
# 属溯源信息，不在本项范围内。
HARDCODED_PATH_RE = re.compile(
    r"[A-Za-z]:[\\/]+(?:Python\d|Users|repos|local|notpython|assets)\b")
SCAN_CODE_DIRS = ("noveldown", "tools", "tests")

# 调试残留 / 草稿文件名特征（实测踩过：调试用的 .tmptest_*.html 被 git add -A 带进仓并推送）
JUNK_NAME_RE = re.compile(r"(?:^|/)(?:\.tmptest|\.pytest_cache|__pycache__)|"
                         r"\.(?:orig|rej|bak|tmp|log|swp)$|(?:^|/)\.DS_Store$", re.I)

# 每个第三方来源：文档里必须同时出现「上游 URL」与「许可证标识」
EXPECTED_THIRD_PARTY = (
    {
        "name": "FictionDown",
        "url": "github.com/ma6254/FictionDown",
        "license": "GPL-3.0",
    },
    {
        "name": "404-novel-downloader",
        "url": "github.com/404-novel-project/novel-downloader",
        "license": "AGPL-3.0-or-later",
    },
    {
        "name": "backupqidian",
        "url": "github.com/zombie110year/backupqidian",
        "license": "未声明",
    },
    {
        "name": "puppeteer-extra-plugin-stealth",
        "url": "github.com/berstend/puppeteer-extra",
        "license": "MIT",
    },
)
REFERENCE_DOC = os.path.join("docs", "REFERENCE.md")


# ------------------------------------------------------------
def tracked_files() -> list:
    """返回 git 已跟踪文件列表（归一化为 / 分隔）。"""
    out = subprocess.run(["git", "-C", ROOT, "ls-files"],
                         capture_output=True, text=True)
    if out.returncode != 0:
        print("!! 不是 git 仓库，或 git 不可用：", out.stderr.strip())
        sys.exit(1)
    return [l.replace("\\", "/") for l in out.stdout.splitlines() if l.strip()]


def read(path: str) -> str:
    with open(os.path.join(ROOT, path), "r", encoding="utf-8") as f:
        return f.read()


def check(root_dir=ROOT, tracked=None) -> list:
    """返回违规列表 [(项, 详情)]。空列表 = 通过。"""
    tracked = tracked if tracked is not None else tracked_files()
    bad = []

    # --- 1. 许可文件唯一性 ---
    # 关键：判「只有根 LICENSE」，而不是「文件名是否眼熟」。
    # 实测踩过：若只判文件名，`_ref/ThirdParty/LICENSE` 会因为 basename 叫 LICENSE 而漏过，
    # 而这恰恰是"第三方源码被误提交"最典型的信号。
    lic = [f for f in tracked
           if os.path.basename(f).upper() in LICENSE_BASENAMES]
    strange = [f for f in lic if f not in ALLOWED_LICENSE_FILES]
    if "LICENSE" not in lic:
        bad.append(("1 许可文件唯一", "仓库根缺少 LICENSE 文件"))
    if strange:
        bad.append(("1 许可文件唯一",
                    f"根目录之外出现许可文件：{strange}"
                    f"（第三方源码被误提交的最典型信号）"))

    # --- 2. 第三方源码目录 ---
    for f in tracked:
        for part in FORBIDDEN_DIR_PARTS:
            if f.startswith(part) or ("/" + part) in f:
                bad.append(("2 无第三方/产物目录", f))
                break

    # --- 3. 归档 ---
    for f in tracked:
        if f.lower().endswith(FORBIDDEN_ARCHIVE_EXT):
            bad.append(("3 无归档文件", f))

    # --- 8. 无调试残留/草稿文件 ---
    for f in tracked:
        if JUNK_NAME_RE.search(f):
            bad.append(("8 无调试残留", f))

    # --- 4. 大文件（> 5 MiB 且非图片）---
    for f in tracked:
        p = os.path.join(root_dir, f)
        if os.path.exists(p):
            size = os.path.getsize(p)
            if size > 5 * 1024 * 1024 and not f.lower().endswith(
                    (".png", ".jpg", ".jpeg", ".gif", ".webp")):
                bad.append(("4 无大文件", f"{f}（{size / 1024 / 1024:.1f} MB）"))

    # --- 5. 凭据（复用项目自身的自检）---
    from noveldown.freeguard import selfcheck as cred_selfcheck
    res = cred_selfcheck(root_dir)
    if not res["ok"]:
        for p, line, what, src in res["violations"]:
            bad.append(("5 无凭据", f"{p}:{line} [{what}] {src[:70]}"))

    # --- 7. 生产代码里不得写死本机绝对路径 ---
    for sub in SCAN_CODE_DIRS:
        d = os.path.join(root_dir, sub)
        if not os.path.isdir(d):
            continue
        for dirpath, dirnames, filenames in os.walk(d):
            dirnames[:] = [x for x in dirnames if x != "__pycache__"]
            for fn in filenames:
                if not fn.endswith(".py"):
                    continue
                fp = os.path.join(dirpath, fn)
                try:
                    with open(fp, "r", encoding="utf-8") as fh:
                        for i, line in enumerate(fh, 1):
                            if line.lstrip().startswith("#"):
                                continue
                            m = HARDCODED_PATH_RE.search(line)
                            if m:
                                bad.append(("7 无硬编码本机路径",
                                            f"{os.path.relpath(fp, root_dir)}:{i} {m.group(0)}"))
                except (OSError, UnicodeDecodeError):
                    continue

    # --- 6. 文档一致性：来源链接 + 许可证 ---
    doc_path = os.path.join(root_dir, REFERENCE_DOC)
    if not os.path.exists(doc_path):
        bad.append(("6 借鉴记账完整", f"缺少 {REFERENCE_DOC}"))
    else:
        doc = read(REFERENCE_DOC)
        for item in EXPECTED_THIRD_PARTY:
            if item["url"] not in doc:
                bad.append(("6 借鉴记账完整",
                            f"{item['name']} 缺少上游链接 {item['url']}"))
            if item["license"] not in doc:
                bad.append(("6 借鉴记账完整",
                            f"{item['name']} 缺少许可证标识 {item['license']}"))
        # 必须明确声明"不入仓"
        if "不入仓" not in doc and "不放进仓库" not in doc:
            bad.append(("6 借鉴记账完整",
                        "未声明第三方源码「不入仓」及理由"))

    # --- 9. 镜像族规则：notes 里的「域数 N」必须等于 match 长度 ---
    # 「同一事实写在两处必须相等」的典型：`notes` 是给人看的散文，
    # `match` 是机器读的真相。手工合并域名时最容易只改一处 ——
    # 实测（v0.8.12 那批）就漏了 3 条，notes 少算、match 已多。
    # 这条约束本来是散文（"记得同步更新"），做成 <1 秒的机械检查最省心。
    mir_dir = os.path.join(root_dir, "noveldown", "rules", "mirrors")
    if os.path.isdir(mir_dir):
        for name in sorted(os.listdir(mir_dir)):
            if not name.endswith(".json"):
                continue
            try:
                with open(os.path.join(mir_dir, name), encoding="utf-8") as f:
                    data = json.load(f)
            except Exception as e:
                bad.append(("9 镜像族域数一致", f"{name}: JSON 解析失败（{e}）"))
                continue
            m = re.search(r"域数 (\d+)", data.get("notes") or "")
            if not m:
                continue
            n = len(data.get("match") or [])
            if int(m.group(1)) != n:
                bad.append(("9 镜像族域数一致",
                            f"{name}: notes 写「域数 {m.group(1)}」，"
                            f"但 match 里有 {n} 个域"))
    return bad


# ------------------------------------------------------------
def _selfcheck() -> int:
    """注入假违规，证明门禁不是死的。"""
    print("=" * 66)
    print("门禁自检：注入假违规，验证门禁必须报红")
    print("=" * 66)
    fake = ["LICENSE", "noveldown/cli.py", "docs/REFERENCE.md",
            "_ref/FictionDown-master/LICENSE",      # 违规 2/1
            "big.zip",                              # 违规 3
            ".tmptest_dump.html",                   # 违规 8
            "output/x.txt"]                         # 违规 2
    bad = check(tracked=fake)
    items = {b[0] for b in bad}
    ok = True
    for expect in ("1 许可文件唯一", "2 无第三方/产物目录", "3 无归档文件", "8 无调试残留"):
        hit = expect in items
        ok = ok and hit
        print(f"  [{ 'PASS' if hit else 'FAIL' }] 检出「{expect}」")
    print()
    print("门禁自检：" + ("有效 ✓" if ok else "失效 ✗（门禁没能抓到假违规）"))
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description="仓库卫生门禁")
    ap.add_argument("--selfcheck", action="store_true",
                    help="注入假违规，验证门禁本身有效")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    if args.selfcheck:
        return _selfcheck()

    print("=" * 66)
    print("仓库卫生门禁 —— 本仓不含第三方源码 / 凭据 / 产物")
    print("=" * 66)
    tracked = tracked_files()
    print(f"已跟踪文件：{len(tracked)} 个")
    if args.verbose:
        for f in tracked:
            print(f"    {f}")
    print()

    bad = check(tracked=tracked)
    if bad:
        print(f"结果：FAIL —— {len(bad)} 项违规")
        cur = None
        for item, detail in bad:
            if item != cur:
                print(f"\n  【{item}】")
                cur = item
            print(f"    · {detail}")
        return 1

    print("结果：PASS")
    print("  1 许可文件唯一且为本项目 LICENSE（MIT）        ✓")
    print("  2 无第三方源码目录 / 产物目录                 ✓")
    print("  3 无归档文件                                  ✓")
    print("  4 无 >5MiB 大文件                             ✓")
    print("  5 无凭据（freeguard.selfcheck）               ✓")
    print(f"  6 借鉴记账完整：{len(EXPECTED_THIRD_PARTY)} 个来源均有上游链接 + 许可证 + 不入仓声明 ✓")
    print()
    print(f"  第三方来源清单见 {REFERENCE_DOC}（只记来源与许可，不含其源码）")
    print("  7 生产代码无硬编码本机路径（解释器 / 用户目录 / 开发盘）  ✓")
    print("  8 无调试残留 / 草稿文件                           ✓")
    print("  9 镜像族规则 notes 的「域数 N」== match 长度       ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main())
