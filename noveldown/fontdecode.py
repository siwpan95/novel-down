#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
字体反爬解码：还原被替换成 PUA 码位的正文。

问题
----
番茄小说把正文里**过半**的汉字替换成私用区码位（U+E000–U+F8FF），再用一份
woff2 子集字体把这些码位渲染成真正的字形。DOM 里是 `'寒\\ue516呼啸'`，
浏览器里显示「寒风呼啸」。实测该书第 1 章 1409 字里有 764 个 PUA（54%）；
连 `<meta description>` 都是混淆过的，页面上没有任何非混淆的正文来源。

为什么不能简单反查
------------------
子集字体里**没有**现成的映射线索：
  · cmap 里 362 个码位**全是 PUA**，零真实码位；
  · glyph 名是 `gid58646` 这类，取自某个来源字体的序号，
    与官方字体的 gid / cid 编号**都不一致**（实测 2.002R 里「风」是 `cid44285`）；
  · charstring 字节日码也被重新打包过，直接比字节对不上。

可行方法：**字形轮廓匹配**
--------------------------
子集字体的 CFF charstring 就是来源字体的字形轮廓（同一份设计数据）。
只要拿到**同版本**的来源字体，把两者每个字形的轮廓点集序列化后取哈希，
即可一一对应——与编号无关，且是精确匹配而非 OCR 近似。

实测（2026-09-20，番茄小说 /reader/6839851004213592580）：
  · 子集字体声明为 `SourceHanSansSC-Normal` **Version 2.002**（OFL-1.1 开源字体）；
  · 用 `adobe-fonts/source-han-sans@2.002R` 的同名 OTF 比对 → **363/363 全部命中**；
  · 换用 @release（2.005）只有 **7/363** —— **版本必须严格对上**。

依赖
----
`fontTools`（+ `brotli` 用于读 woff2）。这两个包**只**服务本功能，
缺失时其它站点照常工作，只是番茄这类站点无法解码并会给出明确提示。

运行时零参考字体依赖
--------------------
途径二所需的「字形轮廓 → 字符」索引**随仓库分发**
（`noveldown/fontmaps/sourcehan-sc-2.002.bin`，gzip 压缩的 JSON，
44 260 条、约 460 KB）——因此运行时**不联网、不下载 17 MB 参考字体**，
`FontDecoder` 也没有任何下载分支。该索引由 `tools/build_fontmap.py` 离线从
OFL-1.1 的 SourceHanSansSC-Normal **2.002** 派生（来源与许可证见
docs/REFERENCE.md 第四节）；**参考字体本体不入仓**，只有维护者重建索引时
才需要按需获取。
"""

import gzip
import hashlib
import json
import os
import re
import sys

# 当前解释器路径（**自发现**，不写死盘符）——报错指引里用它。
PY = sys.executable or "python"

PUA_START, PUA_END = 0xE000, 0xF8FF
FONT_EXT_RE = ("woff2", "woff", "otf", "ttf")

# 参考字体版本（换版本会失配，见模块 docstring）。**运行时不需要字体本体**：
# 所需的字形轮廓索引随仓库分发，见下方 SHIPPED_INDEX。
REF_FONT_VERSION = "2.002"

# 参考索引的缓存文件名（本地/早期版本产物；gzip 压缩的 JSON {轮廓哈希: 码位}）。
REF_INDEX_NAME = "sourcehan-sc-2.002.index.json.gz"

# 随仓分发的**字形轮廓索引**（gzip 压缩的 JSON，44 260 条，约 460 KB）：
# **有它就不需要下载 17 MB 参考字体，也不需要联网** —— 这是唯一运行时路径。
# 生成方式：tools/build_fontmap.py --shipped；来源与许可证见 docs/REFERENCE.md 第四节。
REF_INDEX_BIN = "sourcehan-sc-2.002.bin"
SHIPPED_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fontmaps")
SHIPPED_INDEX = os.path.join(SHIPPED_DIR, REF_INDEX_BIN)
_HASH_LEN = 6


class FontDecodeError(RuntimeError):
    """字体解码不可用（缺依赖 / 缺索引 / 无法建映射）。"""


# ============================================================
#  PUA 检测与替换
# ============================================================

def has_pua(text: str) -> bool:
    return any(PUA_START <= ord(c) <= PUA_END for c in text or "")


def pua_chars(texts) -> set:
    """收集若干文本中出现过的 PUA 码位。"""
    out = set()
    for t in texts:
        for c in t or "":
            if PUA_START <= ord(c) <= PUA_END:
                out.add(ord(c))
    return out


def decode_text(text: str, mapping: dict) -> str:
    """按 {PUA 码位: 真字符} 替换。未覆盖的码位原样保留（便于发现遗漏）。"""
    if not text or not mapping:
        return text
    return "".join(mapping.get(ord(c), c) if PUA_START <= ord(c) <= PUA_END else c
                   for c in text)


def decode_coverage(texts, mapping: dict) -> float:
    """已解码比例，用于校验映射是否够用。"""
    total = miss = 0
    for t in texts:
        for c in t or "":
            if PUA_START <= ord(c) <= PUA_END:
                total += 1
                if ord(c) not in mapping:
                    miss += 1
    return 1.0 if total == 0 else (total - miss) / total


# ============================================================
#  页面里的字体 URL
# ============================================================

def font_urls_from_html(html: str) -> list:
    """从 @font-face 的 src 里取出字体文件 URL（按出现顺序，去重）。"""
    import re
    urls, seen = [], set()
    for m in re.finditer(r"url\(\s*['\"]?([^'\")]+?\.(?:woff2|woff|otf|ttf))['\"]?\s*\)",
                         html or "", re.I):
        u = m.group(1).strip()
        if u.startswith("//"):
            u = "https:" + u
        if u.startswith(("http://", "https://")) and u not in seen:
            seen.add(u)
            urls.append(u)
    return urls


# ============================================================
#  途径一（优先）：按 glyph 名字解码
# ============================================================
# 这是字体反爬里**最常见也最便宜**的做法：子集字体不给 PUA 真实的 cmap，
# 但 glyph 名保留了可读信息。实测两种主流写法：
#
#   ① **英文单词**（起点老版、很多中小站）：
#      glyph 名直接是 `zero` / `one` / … / `nine` / `period`
#      —— 所以数字会显示成乱码但仍是数字。`TTFont.getBestCmap()` 即可还原。
#   ② **uniXXXX / uXXXXX**：名字里带码位十六进制，直接可解。
#
# 能靠名字解就不用下载 17MB 参考字体 —— 先试这条，失败再退回轮廓匹配。

_WORD_TO_CHAR = {
    "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4",
    "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9",
    "period": ".", "comma": ",", "hyphen": "-", "space": " ",
    "colon": ":", "semicolon": ";", "slash": "/", "backslash": "\\",
    "percent": "%", "plus": "+", "asterisk": "*", "underscore": "_",
    "equal": "=", "at": "@", "numbersign": "#", "dollar": "$",
    "ampersand": "&", "parenleft": "(", "parenright": ")",
    "bracketleft": "[", "bracketright": "]", "braceleft": "{",
    "braceright": "}", "quotesingle": "'", "quotedbl": '"',
    "less": "<", "greater": ">", "question": "?", "exclam": "!",
    "bar": "|", "asciitilde": "~", "asciicircum": "^", "degree": "°",
    "hyphenminus": "-", "quotedblleft": "“", "quotedblright": "”",
    "quoteleft": "‘", "quoteright": "’", "ellipsis": "…",
    "periodcentered": "·", "onequote": "'",
}


def char_from_glyph_name(name: str):
    """尽力从 glyph 名推断真实字符；推不出返回 None。

    支持的形态（按可靠性排序）：
      `uni4E00` / `uni4E00.alt`  → 码位十六进制，**精确**
      `u4E00` / `U+4E00`         → 同上
      `CJK UNIFIED IDEOGRAPH-4E00` → 同上
      `zero` / `period` / …      → 英文单词表
      `a` / `A` / `zero.sc`      → 单字符名（去掉 `.后缀` 后）
      `cid12345` / `gid12345`    → **推不出**（那是索引，不是字符）
    """
    if not name or name == ".notdef":
        return None
    n = name.split(".")[0].strip()          # 去掉 .alt / .sc 之类后缀
    low = n.lower()

    # ---- 码位十六进制 ----
    m = re.fullmatch(r"uni([0-9a-fA-F]{4,6})", n)
    if m:
        cp = int(m.group(1), 16)
        return chr(cp) if 0x20 <= cp <= 0x10FFFF else None
    m = re.fullmatch(r"[uU]\+?([0-9a-fA-F]{4,6})", n)
    if m:
        cp = int(m.group(1), 16)
        return chr(cp) if 0x20 <= cp <= 0x10FFFF else None
    m = re.search(r"UNIFIED IDEOGRAPH[- ]([0-9A-Fa-f]{4,6})", n, re.I)
    if m:
        cp = int(m.group(1), 16)
        return chr(cp) if 0x20 <= cp <= 0x10FFFF else None

    # ---- cidNNNNN / gidNNNNN：是索引不是字符，明确放弃 ----
    if re.fullmatch(r"(cid|gid)\d+", low):
        return None

    # ---- 英文单词 ----
    if low in _WORD_TO_CHAR:
        return _WORD_TO_CHAR[low]

    # ---- 单字符名 ----
    if len(n) == 1 and n.isprintable():
        return n
    return None


def map_from_glyph_names(pairs) -> tuple:
    """pairs = [(pua_codepoint, glyph_name)] → (映射, 覆盖率)。

    纯函数、不依赖字体文件 —— 便于单测。
    """
    out, total = {}, 0
    for cp, name in pairs:
        total += 1
        ch = char_from_glyph_name(name)
        if ch is not None:
            out[cp] = ch
    return out, (len(out) / total if total else 0.0)


# ============================================================
#  途径二（兜底）：字形轮廓匹配
# ============================================================

def _cp_priority(cp: int) -> int:
    """同一字形可能对应多个码位（如「风」与康熙部首「⻛」共用字形）。

    取号时要优先常用的那个区块，否则正文会混进部首/兼容字符。
    实测踩过：不做优先级时 U+E516 反查成了 U+2EDB「⻛」而不是 U+98CE「风」。
    """
    if 0x4E00 <= cp <= 0x9FFF:      # CJK 统一表意文字（基本区）
        return 0
    if 0x3400 <= cp <= 0x4DBF:      # 扩展 A
        return 1
    if 0x20000 <= cp <= 0x3FFFF:    # 扩展 B 及以上
        return 2
    if 0x3000 <= cp <= 0x303F:      # CJK 标点
        return 3
    if 0xFF00 <= cp <= 0xFFEF:      # 全角
        return 4
    if 0x2E80 <= cp <= 0x2FDF:      # 部首（最低优先）
        return 8
    if 0xF900 <= cp <= 0xFAFF:      # 兼容汉字
        return 6
    return 5


def _outline_key(glyph_set, name: str) -> str:
    """把一个字形的轮廓点集序列化成哈希（**前 6 字节**，与紧凑索引一致）。

    取 6 字节而非完整 20 字节：实测 44260 条**零碰撞**，索引体积小一个量级。
    """
    from fontTools.pens.recordingPen import RecordingPen
    pen = RecordingPen()
    glyph_set[name].draw(pen)
    parts = [op + "|" + ",".join(f"{x:g}/{y:g}" for x, y in pts)
             for op, pts in pen.value]
    return hashlib.sha1(";".join(parts).encode()).hexdigest()[:_HASH_LEN * 2]


def build_ref_index(font_path: str, log=None) -> dict:
    """从参考字体构建 {轮廓哈希: 字符} 索引。"""
    from fontTools.ttLib import TTFont
    if log:
        log(f"  加载参考字体 {os.path.basename(font_path)}（约 17MB，需十余秒）…")
    font = TTFont(font_path)
    cmap = font.getBestCmap()
    glyph_set = font.getGlyphSet()

    hash2cp = {}
    for cp, name in cmap.items():
        if not (0x20 <= cp <= 0x10FFFF):
            continue
        try:
            h = _outline_key(glyph_set, name)
        except Exception:
            continue
        old = hash2cp.get(h)
        if old is None or _cp_priority(cp) < _cp_priority(old):
            hash2cp[h] = cp
    if log:
        log(f"  索引完成：{len(hash2cp)} 个字形轮廓")
    return hash2cp


def save_ref_index(hash2cp: dict, path: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    payload = json.dumps({h: cp for h, cp in hash2cp.items()},
                         separators=(",", ":")).encode("utf-8")
    with gzip.open(path, "wb", compresslevel=9) as f:
        f.write(payload)
    return os.path.getsize(path)


def load_ref_index(path: str) -> dict:
    if not os.path.exists(path):
        raise FontDecodeError(
            f"缺少字体轮廓索引：{path}\n"
            f"正常安装应随仓自带 noveldown/fontmaps/{REF_INDEX_BIN}。"
            f"若确实缺失，请跑：{PY} tools\\build_fontmap.py --shipped")
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return {h: cp for h, cp in json.load(f).items()}


# ============================================================
#  子集字体 → PUA 映射
# ============================================================

def pua_map_from_font(font_bytes: bytes, ref_index: dict = None,
                     name_threshold: float = 0.6) -> dict:
    """把子集字体解成 {PUA 码位: 真字符}。

    两条途径，**优先用便宜的那条**：
      ① `glyph_name` —— 按 glyph 名解（英文单词 / uniXXXX）；
         能解就不用任何字体重建，秒级完成。
      ② `outline`     —— 字形轮廓匹配；用**随仓**的轮廓索引
         （`noveldown/fontmaps/`，零下载、零参考字体）。

    返回 {"map", "mode", "coverage", "unmatched", "total_pua"}；
    当 mode == "needs_outline" 时表示名字解不出来，需要调用方提供 ref_index 再来一次。
    """
    from fontTools.ttLib import TTFont
    import io
    font = TTFont(io.BytesIO(font_bytes))
    cmap = font.getBestCmap()
    pua_pairs = [(cp, n) for cp, n in cmap.items() if PUA_START <= cp <= PUA_END]
    total = len(pua_pairs)

    # ---- 途径一：glyph 名 ----
    name_map, cov = map_from_glyph_names(pua_pairs)
    if total and cov >= name_threshold:
        return {"map": name_map, "mode": "glyph_name", "coverage": cov,
                "unmatched": [cp for cp, _ in pua_pairs if cp not in name_map],
                "total_pua": total}

    # ---- 途径二：轮廓匹配 ----
    if ref_index is None:
        return {"map": {}, "mode": "needs_outline", "coverage": cov,
                "unmatched": [cp for cp, _ in pua_pairs if cp not in name_map],
                "total_pua": total}

    glyph_set = font.getGlyphSet()
    out, unmatched = dict(name_map), []
    for cp, nm in pua_pairs:
        if cp in out:
            continue
        try:
            h = _outline_key(glyph_set, nm)
        except Exception:
            unmatched.append(cp)
            continue
        real = ref_index.get(h)
        if real is None:
            unmatched.append(cp)
        else:
            out[cp] = chr(real)
    return {"map": out, "mode": "outline",
            "coverage": (len(out) / total if total else 1.0),
            "unmatched": unmatched, "total_pua": total}


# ============================================================
#  对外：一个带缓存的门面
# ============================================================

class FontDecoder:
    """字体反爬解码器（索引与逐字体映射都落盘缓存）。"""

    def __init__(self, cache_dir: str, log=None):
        self.cache_dir = os.path.abspath(cache_dir)
        self.log = log or (lambda m: None)
        self.ref_index_path = os.path.join(self.cache_dir, REF_INDEX_NAME)
        self._ref = None
        self._maps = {}
        self.last_mode = None       # 上次用于解码的途径（glyph_name / outline）
        os.makedirs(self.cache_dir, exist_ok=True)

    # ---------- 参考索引 ----------
    def ref_index(self):
        """取字形轮廓索引（**运行时零下载、零参考字体**）。

        查找顺序：
          1. 随仓索引 `noveldown/fontmaps/sourcehan-sc-2.002.bin`（默认路径）
          2. 缓存目录里的索引（本地重建产物；仅供开发/离线校验）
        两者都没有才报错——错误信息会给出重建指引（需维护者离线重建，
        见 tools/build_fontmap.py）。**本方法不再有任何下载分支。**
        """
        if self._ref is not None:
            return self._ref
        for path in (SHIPPED_INDEX, self.ref_index_path):
            if os.path.exists(path):
                self._ref = load_ref_index(path)
                self.log(f"  字形轮廓索引已加载（{len(self._ref)} 条，"
                         f"{os.path.basename(path)}）")
                return self._ref
        load_ref_index(SHIPPED_INDEX)      # 抛带指引的错误
        return self._ref

    # ---------- 单字体映射 ----------
    def map_for_font(self, font_bytes: bytes) -> dict:
        sig = hashlib.sha1(font_bytes).hexdigest()[:16]
        if sig in self._maps:
            return self._maps[sig]

        cache_path = os.path.join(self.cache_dir, f"pua-{sig}.json")
        if os.path.exists(cache_path):
            try:
                with open(cache_path, "r", encoding="utf-8") as f:
                    d = json.load(f)
                m = {int(k): v for k, v in d["map"].items()}
                self._maps[sig] = m
                self.last_mode = d.get("mode", "?")
                self.log(f"  PUA 映射命中缓存（{len(m)} 个码位，{self.last_mode}，字体 {sig}）")
                return m
            except (OSError, json.JSONDecodeError, KeyError):
                pass

        # 先试「按 glyph 名解」—— 秒级、且不需要任何字体重建
        res = pua_map_from_font(font_bytes, None)
        if res["mode"] == "needs_outline":
            self.log("  按 glyph 名解不出（名字是索引而非字符），"
                     "改用轮廓匹配（随仓同版本轮廓索引）")
            ref = self.ref_index()
            res = pua_map_from_font(font_bytes, ref)
        m = res["map"]
        self.last_mode = res["mode"]
        how = {"glyph_name": "按 glyph 名", "outline": "轮廓匹配"}.get(
            res["mode"], res["mode"])
        self.log(f"  PUA 映射（{how}）：{len(m)}/{res['total_pua']} 个码位已还原"
                 + (f"，{len(res['unmatched'])} 个未匹配" if res["unmatched"] else ""))
        try:
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump({"map": {str(k): v for k, v in m.items()},
                           "mode": res["mode"]}, f, ensure_ascii=False)
        except OSError:
            pass
        self._maps[sig] = m
        return m


# ============================================================
#  依赖检查
# ============================================================

def deps_available() -> tuple:
    """返回 (是否可用, 缺失说明)。

    ⚠ 审计 #8（2026-09-22）：原来对 brotli 的 ImportError 是 **`pass`** 掉的，
    理由是「只在读 woff2 时才需要」——但这与本模块 docstring 里
    「缺失时…会给出明确提示」**自相矛盾**，而且后果不轻：
    只装了 fontTools、没装 brotli 时这里照样返回 True，于是 woff2 站点一路走到
    `TTFont()` 才在**深层**炸掉，被 engine 兜住之后，**含 PUA 占位字符的半乱码正文
    会被当成 status=ok 存下来并导出**。

    两件事分开说清楚：
      · 缺 fontTools → 整个能力不可用（返回 False）；
      · 缺 brotli   → 能力**部分**可用（otf/ttf 能读、woff2 不能），
        所以这里返回「说明」让调用方在真遇到 woff2 时报得明白。
    """
    missing = []
    parts_ok = []
    try:
        import fontTools  # noqa: F401
        parts_ok.append("fontTools")
    except ImportError:
        missing.append("fontTools")
    try:
        import brotli  # noqa: F401
        parts_ok.append("brotli")
    except ImportError:
        missing.append("brotli")

    if "fontTools" in missing:
        return False, ("缺少依赖：" + "、".join(missing)
                       + f"。安装：{PY} -m pip install fontTools brotli")
    if "brotli" in missing:
        # 能跑，但读不了 woff2 —— 明确告知，别等深层报错
        return True, ("缺少 brotli：otf/ttf 字体仍可解码，但 **woff2 读不了**。"
                      f"安装：{PY} -m pip install brotli")
    return True, ""
