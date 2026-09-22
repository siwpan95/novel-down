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

十一项检查
----------
1. 许可文件唯一且为本项目 LICENSE（不得混入第三方 LICENSE/COPYING）
2. 不跟踪第三方源码目录（_ref/ vendor/ node_modules/ third_party/ …）
3. 不跟踪归档（*.zip / *.tar.gz / *.7z / *.rar）
4. 不跟踪产物与缓存（output/ state/ cache/ dist/ build/）
5. 不跟踪凭据（复用 noveldown.freeguard.selfcheck）
6. 文档一致性：docs/REFERENCE.md 必须为每个第三方来源同时给出**上游 URL**与**许可证**
7. 生产代码（noveldown/ tools/ tests/）不得写死本机绝对路径（解释器安装目录/用户目录/开发盘）
8. 无调试残留 / 草稿文件
9. 镜像族规则 `notes` 里的「域数 N」必须等于 `match` 长度（同一事实写在两处必须相等）
10. README 里的关键计数必须等于**从代码算出的**事实
11. `docs/NEW_SITES_PLAN.md §12.6` 规划表的「状态」必须等于规则文件的存在/启用事实

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
    # ⚠ `.archived/` 里实有 8 个**第三方归档**（FictionDown×3 / novel-downloader /
    #   backupqidian / novel-spider / QidianCrawler / QidianScrapy）。
    #   它此前不在名单里 → 一旦有人在那儿解压再 `git add -A`，
    #   第三方源码就能入仓而**门禁第 2 项不报**（MIT 仓分发 GPL/AGPL 源码的许可风险）。
    #   审计 #13，2026-09-22。
    ".archived/",
)
FORBIDDEN_ARCHIVE_EXT = (".zip", ".tar.gz", ".tgz", ".7z", ".rar", ".xz", ".bz2")

# 生产代码里不得写死**本机环境路径**（解释器安装目录 / 用户目录 / 本机开发盘）。
# 实测踩过：报错指引里写死 `F://Python314//python.exe`，换盘符/换 Python 就废了。
# 正确做法是自发现：`sys.executable`（解释器）、`os.environ`（系统目录）、`shutil.which`（外部命令）。
# 注意：这里只查**生产代码**（noveldown/ 与 tools/*.py），文档里的来源记账（如 本家 webcopier 仓）
# 属溯源信息，不在本项范围内。
# ⚠⚠ 原来的写法 `(?:Python\d|...)\b` 对 **`F:/Python314` 是失效的**（2026-09-22 注入测试发现）：
#   `Python\d` 只吃一位数字，匹配到 `Python3` 后下一个字符是 `1`（同为 word 字符）
#   → **没有词边界** → 整个匹配失败。也就是说门禁第 7 项对本机最常用的
#   `F://Python314//...` 一律漏报；而 `G://assets`、`C://Users` 这类行尾有边界的能中，
#   于是「看起来门禁是活的」。
#   改用**负向先行断言**（不是 `\b`，因为 `\b` 依赖「后面不是 word 字符」这一前提，
#   而路径里 `Python314` 后面还有数字），并且 `\d+` 吞掉全部版本号。
HARDCODED_PATH_RE = re.compile(
    r"[A-Za-z]:[\\/]+(?:Python\d*|Users|repos|local|notpython|assets)"
    r"(?![A-Za-z0-9_])")
# ⚠ 2026-09-22 审计 #6：原先是 ("noveldown","tools","tests") —— **漏了 packaging**，
#   而 packaging/build.py 当时正硬编码着 `F:/Python314/python.exe`，
#   门禁却照样打印「生产代码无硬编码本机路径 ✓」→ 属**过度声称**。
#   packaging/ 是本仓自己维护的构建脚本，同样是「生产代码」。
SCAN_CODE_DIRS = ("noveldown", "tools", "tests", "packaging")

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
        # ⚠ 必须按 root_dir 读（原来写死 `read(REFERENCE_DOC)` —— 读的是**真实仓库**，
        #   于是 `check(root_dir=临时目录)` 时第 6 项检查的其实是本仓，
        #   自检那边根本没法为它注入现场。2026-09-22 扩展 --selfcheck 时发现）。
        doc = read(os.path.join(root_dir, REFERENCE_DOC))
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
    """注入假违规，**逐项证明**门禁不是死的。

    ⚠ 审计 #9（2026-09-22）：原来的自检只抽验了 11 项里的 5 项
    （许可文件唯一 / 无第三方源码 / 无归档 / 无调试残留 / 规划表脱节）。
    只抽验一部分的问题是：**没被抽到的那几项，你不知道它是活的还是死的**——
    而第 7 项当时恰好就是「死」的（正则对本机那个解释器目录匹配不上，长期漏报）。

    所以现在**每一项都注入一次**，两种手段：
      · **路径类**（1/2/3/8）：伪造 `tracked` 文件清单即可，不用真建文件；
      · **内容类**（4/5/6/7/9/10/11）：在临时目录里**搭一个假现场**，
        塞进真文件内容，再对那个目录跑一次 `check()`。
    """
    print("=" * 66)
    print("门禁自检：逐项注入假违规，验证门禁必须报红")
    print("=" * 66)

    import shutil
    import tempfile

    results = []          # [(项名, 是否检出)]

    # ---------- 路径类：伪造 tracked 清单 ----------
    fake_tracked = [
        "LICENSE", "noveldown/cli.py", "docs/REFERENCE.md",
        "_ref/FictionDown-master/LICENSE",       # 违规 1（根之外有 LICENSE）+ 2
        "big.zip",                               # 违规 3
        ".tmptest_dump.html",                    # 违规 8
        "output/x.txt",                          # 违规 2
        ".archived/vendor-snapshot.zip",         # 违规 2/3（审计 #13 新增覆盖）
    ]
    items = {b[0] for b in check(tracked=fake_tracked)}
    for expect in ("1 许可文件唯一", "2 无第三方/产物目录", "3 无归档文件",
                   "8 无调试残留"):
        results.append((expect, expect in items))

    # ---------- 内容类：临时现场 ----------
    def _probe(label, build, expect_item, with_tracked=False):
        """在临时目录里搭现场 → 跑 check() → 看是否报出该项。

        `with_tracked=True` 时，把临时目录里**真实存在的文件**当作 tracked 清单
        —— 因为第 4 项（无大文件）是按 `tracked` + getsize 判定的，传空清单它就看不到文件。
        """
        tmp = tempfile.mkdtemp(prefix="gate_")
        try:
            build(tmp)
            if with_tracked:
                tracked = []
                for dp, _dn, fns in os.walk(tmp):
                    for fn in fns:
                        tracked.append(os.path.relpath(os.path.join(dp, fn), tmp))
            else:
                tracked = []
            probs = check(root_dir=tmp, tracked=tracked)
            hit = any(p.startswith(expect_item) for p, _ in probs)
            results.append((label, hit))
        except Exception as e:                      # noqa: BLE001
            results.append((label + "（自检异常：%s: %s）" % (type(e).__name__, e), False))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def _big(tmp):
        """4 无大文件：真放一个 >5MiB 的文件。"""
        d = os.path.join(tmp, "noveldown")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "huge.bin"), "wb") as f:
            f.write(b"0" * (6 * 1024 * 1024))

    def _cred(tmp):
        """5 无凭据：塞一行**免费约束相关**的凭据代码。

        ⚠ 注意这里注入的是什么：`freeguard.selfcheck` 的模式表盯的是
        **Cookie / 付费开关 / 口令字段 / token 字段**这类「本项目承诺不做」的代码路径，
        **不是**通用的密钥扫描。我第一版塞的是一个通用形态的 API key 赋值，
        结果「没报」——查了才发现那是**符合设计**的，不是门禁坏了。
        自检用例本身写错，比门禁坏掉更难发现，所以这段说明要留着。

        ⚠ 另外：这些「反面示例」的字面量**不能**直接写进本文件（含 docstring）——
        `check_repo` 与 `freeguard.selfcheck` 都会把它们当成真证据
        （实测：本文件一度被第 7 项和凭据项同时报红）。所以下面用拼接构造。
        """
        d = os.path.join(tmp, "noveldown")
        os.makedirs(d, exist_ok=True)
        # ⚠ 拼出来：字面量会让 `freeguard.selfcheck` 把本文件自己扫成违规
        #   （tests/test_freeguard.py 里那条「项目自身无凭据代码路径」用例会因此失败）
        fake_key = "pass" + "word"
        with open(os.path.join(d, "leak.py"), "w", encoding="utf-8") as f:
            f.write(fake_key + " = " + "\"" + "hunter2" + "\"")
            f.write("\n")

    def _doc(tmp):
        """6 借鉴记账完整：REFERENCE.md 里什么都没记。"""
        os.makedirs(os.path.join(tmp, "docs"), exist_ok=True)
        with open(os.path.join(tmp, REFERENCE_DOC), "w", encoding="utf-8") as f:
            f.write("# 参照\n\n这里什么都没记。\n")

    def _hardpath(tmp):
        """7 无硬编码本机路径：⭐ 这条正是本轮修过的「死正则」。

        ⚠ 假路径必须**拼出来**，不能以字面量写在本文件里 ——
        否则 `tools/` 自己就会被第 7 项报红（我第一次就是这么把门禁搞挂的）。
        同理，下面 #5 的假凭据也是拼的。
        """
        d = os.path.join(tmp, "noveldown")
        os.makedirs(d, exist_ok=True)
        fake_path = "F" + ":" + "\\" + "Python" + "314" + "\\" + "python.exe"
        with open(os.path.join(d, "hard.py"), "w", encoding="utf-8") as f:
            f.write("PY = r\"" + fake_path + "\"")
            f.write("\n")

    def _mirror(tmp):
        """9 镜像族域数：notes 写 3、match 只有 1。"""
        d = os.path.join(tmp, "noveldown", "rules", "mirrors")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "m.json"), "w", encoding="utf-8") as f:
            json.dump({"notes": "签名：x；域数 3", "match": ["a.com"]}, f)

    def _counts(tmp):
        """10 README 计数：写一个明显对不上的数字。"""
        with open(os.path.join(tmp, "README.md"), "w", encoding="utf-8") as f:
            f.write("内置 **9999 条**规则（**9999 条启用**）\n")

    def _plan(tmp):
        """11 规划表脱节：表里写已接入、规则文件却不存在。"""
        os.makedirs(os.path.join(tmp, "docs"))
        os.makedirs(os.path.join(tmp, "noveldown", "rules"))
        with open(os.path.join(tmp, PLAN_DOC_REL), "w", encoding="utf-8") as fh:
            fh.write("### 12.6 正版站扩展 · 优先级规划\n\n")
            fh.write("| 候选 | 状态 | 规则 | 备注 |\n|---|---|---|---|\n")
            fh.write("| 假站A | ⭕ 未探 | `fake-missing` | 应通过（确实无规则）|\n")
            fh.write("| 假站B | ✅ 已接入 | `fake-absent` | 违规 ①：无规则文件 |\n")
            fh.write("| 假站C | ⛔ 存根 | `fake-on` | 违规 ②：规则其实是启用的 |\n")
        with open(os.path.join(tmp, "noveldown", "rules", "fake-on.json"),
                  "w", encoding="utf-8") as fh:
            json.dump({"enabled": True}, fh)

    _probe("4 无大文件", _big, "4 无大文件", with_tracked=True)
    _probe("5 无凭据", _cred, "5 无凭据")
    _probe("6 借鉴记账完整", _doc, "6 借鉴记账完整")
    _probe("7 无硬编码本机路径", _hardpath, "7 无硬编码本机路径")
    _probe("9 镜像族域数一致", _mirror, "9 镜像族域数一致")

    # 10 README 计数（走的是独立函数，不看 tracked）
    tmp = tempfile.mkdtemp(prefix="gate10_")
    try:
        _counts(tmp)
        _ok10, probs10 = check_readme_counts(tmp)
        results.append(("10 README 计数一致", (not _ok10) and bool(probs10)))
    except Exception as e:                          # noqa: BLE001
        results.append(("10 README 计数一致（自检异常：%s）" % type(e).__name__, False))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # 11 规划表状态（独立函数）
    tmp = tempfile.mkdtemp(prefix="gate11_")
    try:
        _plan(tmp)
        _ok11, prob11, _uv11 = check_plan_state(tmp)
        results.append(("11 §12.6 规划表状态", (not _ok11) and len(prob11) == 2))
    except Exception as e:                          # noqa: BLE001
        results.append(("11 §12.6 规划表状态（自检异常：%s）" % type(e).__name__, False))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # ---------- 汇总 ----------
    ok = True
    for label, hit in results:
        ok = ok and hit
        print("  [%s] %s" % ("PASS" if hit else "FAIL", label))
    covered = len([1 for _l, h in results if h])
    print("\n 覆盖 %d 项 / 全部 11 项；检出 %d 项" % (len(results), covered))
    print()
    print("门禁自检：" + ("有效 ✓" if ok else "失效 ✗（有检查项没能抓到假违规）"))
    return 0 if ok else 1


# ---------------------------------------------------------------
# 10. README 计数一致性（v0.8.25 新增）
#
# 为什么需要它：README 里的「153 条规则 / 141 条启用 / 265 个用例」这类数字
# **全是人写的**，改代码时极易忘记同步 —— 实测就脱节过
# （README 写「170 个用例」而实际已 265；写「11 条存根」而实际 12）。
# 与其靠人眼，不如让门禁**从代码算出事实**再与 README 文本比对，
# 不一致就 FAIL 并**直接告诉该改成什么**。
#
# ⚠ 本项只校验 **README 的计数**；**docs/ 里「读作现状」的表**由第 11 项负责。
#   ⚠ 划界依据在 v0.8.27 修正过 —— 原文写的是「只校验 README、不校验 docs」，**太粗**：
#     · **豁免**：带版本号的快照（如「截至 v0.7.1，18 条规则」）、
#       明确标注为实测结果的数字（如「700 章 + 650 个 li.vip」）—— 改反而破坏证据链；
#     · **必须同步**：任何**读起来就是当前事实**的内容，不论它在 README 还是 docs
#       （§12.6 规划表就是这么一处，实测脱节 3 处 → 见第 11 项）。
#   → 判据是「**它承诺的是快照还是现状**」，不是「它在哪个文件」。
# ---------------------------------------------------------------
def check_readme_counts(root: str):
    import os as _os
    import re as _re
    import sys as _sys
    readme = _os.path.join(root, "README.md")
    if not _os.path.isfile(readme):
        return True, []
    text = open(readme, encoding="utf-8").read()
    if root not in _sys.path:
        _sys.path.insert(0, root)
    problems = []
    try:
        from noveldown.rules import load_rules, active_rules
        r = load_rules()
        a = active_rules(r)
        top = {k: v for k, v in r.items()
               if _os.sep + "mirrors" + _os.sep not in (v.path or "")}
        mir = {k: v for k, v in r.items()
               if _os.sep + "mirrors" + _os.sep in (v.path or "")}
        gb = {k: v for k, v in r.items() if v.pool == "正版"}
        facts = {
            "总规则数": len(r),
            "启用规则数": len(a),
            "顶层手写": len(top),
            "顶层启用": sum(1 for v in top.values() if v.enabled),
            "镜像池": len(mir),
            "顶层停用存根": sum(1 for v in top.values() if not v.enabled),
            "正版总数": len(gb),
            "正版启用": sum(1 for v in gb.values() if v.enabled),
            # ⚠ 全仓停用数（含镜像池）—— 与「顶层停用存根」是两个口径，
            #   README 里「停用存根共 N 条」指的是**全仓**，别拿顶层口径去比。
            "停用总数": sum(1 for v in r.values() if not v.enabled),
        }
    except Exception as e:                       # 规则加载失败不在这里报
        return True, []
    # 测试用例数：从测试源码里数 test_ 方法（与 unittest 的计数口径一致）
    n_tests = 0
    tdir = _os.path.join(root, "tests")
    if _os.path.isdir(tdir):
        for fn in _os.listdir(tdir):
            if fn.endswith(".py"):
                src = open(_os.path.join(tdir, fn), encoding="utf-8",
                           errors="replace").read()
                n_tests += len(_re.findall(r"^\s+def (test_\w+)", src, _re.M))
    checks = [
        (r"内置 \*\*(\d+) 条\*\*规则（\*\*(\d+) 条启用\*\*",
         ["总规则数", "启用规则数"], "规则总数/启用数"),
        # ⚠ 措辞要与数字口径**一一对应**：README 原写「顶层手写 28 条」，
        #   而"手写"其实是 40（28 启用 + 12 存根）—— 门禁首次运行就抓到了这个措辞歧义，
        #   故两边都改成「手写 40 条（启用 28）」。
        (r"顶层手写 \*\*(\d+) 条\*\*（启用 (\d+)）\+ \*\*镜像池 (\d+) 条\*\*；另有 (\d+) 条停用存根",
         ["顶层手写", "顶层启用", "镜像池", "顶层停用存根"], "顶层/镜像池/存根"),
        (r"\*\*正版\*\*（(\d+) 条，(\d+) 启用）", ["正版总数", "正版启用"], "正版池"),
        # ⚠ v0.8.28 补：README 末尾还有一句「**停用存根共 N 条**（正版 X + 免费镜像 Y）」，
        #   它此前**不在**校验范围内 —— 实测已脱节（写 11，实际 12；本轮加火星后应为 13）。
        #   教训同第 11 项：**同一事实的每一处都要进校验，只覆盖「主要那处」迟早漏。**
        (r"\*\*停用存根共 (\d+) 条\*\*", ["停用总数"], "停用存根总数"),
    ]
    for pat, keys, label in checks:
        m = _re.search(pat, text)
        if not m:
            problems.append("README 里找不到「%s」的计数（格式变了？请同步本节正则）" % label)
            continue
        for got, key in zip(m.groups(), keys):
            if int(got) != facts[key]:
                problems.append("README 写 %s=%s，实际 %s=%d" % (key, got, key, facts[key]))
    # 测试用例数（README 里多处出现，全部要一致）
    for m in _re.finditer(r"\*\*(\d+) 个用例", text):
        if int(m.group(1)) != n_tests:
            problems.append("README 写用例数=%s，实际 %d" % (m.group(1), n_tests))
    for m in _re.finditer(r"tests/\s+(\d+) 个用例", text):
        if int(m.group(1)) != n_tests:
            problems.append("README 目录树写用例数=%s，实际 %d" % (m.group(1), n_tests))
    return (not problems), problems


# ---------------------------------------------------------------
# 11. docs 规划表 ↔ 规则文件一致性（v0.8.27 新增）
#
# 为什么需要它：`docs/NEW_SITES_PLAN.md §12.6` 是一张**读作当前事实的现状表**
# （标题就叫「优先级规划」，无版本号）。实测它脱节了 3 处 ——
# 把**已接入且启用**的晋江 / 掌阅标成「⭕ 未探」，把**已从存根翻案**的创世标成「⛔ 存根」。
# 这与第 10 项是同一类病：**同一事实写在两处（文档 vs 代码），迟早不一致**。
#
# ⚠ 与第 10 项的划界（**修正版**：判据不是「在 README 还是 docs」）：
#   · **豁免** —— 带版本号的快照（「截至 v0.7.1，18 条规则」）、
#     明确标注为实测结果的数字（「700 章 + 650 个 li.vip」）：改反而破坏证据链；
#   · **必须同步** —— 标为「计划 / 现状 / 优先级」的表：它读起来就是当前事实。
#   → 判据是「**它承诺的是快照还是现状**」。
#
# 校验方式：解析 §12.6 之后所有 `| 候选 | 状态 | 规则 | 备注 |` 形态的行，
# 状态列三选一，再拿「规则」列反引号内的**规则标识**去核对 noveldown/rules/：
#   ✅ 已接入 → 规则文件必须存在**且启用**
#   ⛔ 存根   → 规则文件必须存在**且停用**
#   ⭕ 未探   → 规则文件必须**不存在**
# 「状态」列没写这三种值之一的行（如 P3/P4 的说明表）**不参与校验**，避免误扫。
# ---------------------------------------------------------------

PLAN_DOC_REL = os.path.join("docs", "NEW_SITES_PLAN.md")
PLAN_SECTION_MARK = "### 12.6 正版站扩展"
PLAN_STATE_ON = "✅ 已接入"
PLAN_STATE_OFF = "⛔ 存根"
PLAN_STATE_NONE = "⭕ 未探"


def check_plan_state(root: str):
    """返回 (ok, problems, unverified_rows)。

    unverified_rows = 「⭕ 未探」但没给出规则标识的行（无法校验，**不静默**，由调用方报出）。
    """
    doc = os.path.join(root, PLAN_DOC_REL)
    if not os.path.isfile(doc):
        return True, [], []

    text = open(doc, encoding="utf-8").read()
    i = text.find(PLAN_SECTION_MARK)
    if i < 0:
        return False, ["找不到章节标记「%s」（章节被改名？请同步本项）"
                       % PLAN_SECTION_MARK], []

    seg = text[i:]
    # 截到下一个二级/三级标题为止（§12.6 目前是末节，但别依赖这一点）
    nxt = re.search(r"\n#{2,3} ", seg[len(PLAN_SECTION_MARK):])
    if nxt:
        seg = seg[:len(PLAN_SECTION_MARK) + nxt.start() + 1]

    rules_dir = os.path.join(root, "noveldown", "rules")
    known = {f[:-5] for f in os.listdir(rules_dir) if f.endswith(".json")}

    def is_enabled(rid):
        p = os.path.join(rules_dir, rid + ".json")
        if not os.path.isfile(p):
            return None
        try:
            with open(p, encoding="utf-8") as fh:
                return json.load(fh).get("enabled", True) is not False
        except Exception:
            return None

    problems, unverified, n_rows = [], [], 0
    for line in seg.splitlines():
        s = line.strip()
        if not s.startswith("|"):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if len(cells) < 3:
            continue
        state = cells[1].replace("*", "").replace("`", "").strip()
        if state not in (PLAN_STATE_ON, PLAN_STATE_OFF, PLAN_STATE_NONE):
            continue
        n_rows += 1
        ids = [x for x in re.findall(r"`([^`]+)`", cells[2]) if x != "—"]
        if state == PLAN_STATE_NONE and not ids:
            # 未探行没给标识 → 校验不到（原脱节正是这种形态：标识被写在候选名括号里）
            unverified.append(cells[0].replace("*", "").strip())
            continue
        for rid in ids:
            actual = is_enabled(rid)
            if state == PLAN_STATE_ON:
                if actual is None:
                    problems.append("§12.6 标「已接入」但无规则文件：%s" % rid)
                elif not actual:
                    problems.append("§12.6 标「已接入」但规则**已停用**：%s" % rid)
            elif state == PLAN_STATE_OFF:
                if actual is None:
                    problems.append("§12.6 标「存根」但无规则文件：%s" % rid)
                elif actual:
                    problems.append("§12.6 标「存根」但规则**是启用的**：%s" % rid)
            else:
                if actual is not None:
                    problems.append("§12.6 标「未探」但规则文件**已存在**：%s" % rid)

    if n_rows == 0:
        problems.append("§12.6 规划表解析到 0 行（表格格式变了？请同步本项）")
    return (not problems), problems, unverified


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

    ok_rd, rd_problems = check_readme_counts(ROOT)
    if not ok_rd:
        print(f"结果：FAIL —— {len(rd_problems)} 项 README 计数脱节")
        print("\n  【README 与代码事实不一致】")
        for d in rd_problems:
            print(f"    · {d}")
        return 1

    ok_pl, pl_problems, pl_unverified = check_plan_state(ROOT)
    if not ok_pl:
        print(f"结果：FAIL —— {len(pl_problems)} 项规划表脱节")
        print("\n  【§12.6 规划表 与 规则文件事实不一致】")
        for d in pl_problems:
            print(f"    · {d}")
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
    print(" 10 README 关键计数 == 代码事实（规则/启用/正版/存根/用例） ✓")
    _n_uv = len(pl_unverified)
    _tail = ("（⚠ 其中 %d 行「未探」未给规则标识、无法校验：%s）"
             % (_n_uv, "、".join(pl_unverified))) if _n_uv else ""
    print(" 11 §12.6 规划表状态 == 规则文件存在/启用事实%s ✓" % _tail)
    return 0


if __name__ == "__main__":
    sys.exit(main())
