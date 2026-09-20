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

参考字体**不随仓库分发**：由 `tools/build_fontmap.py` 按需下载并生成索引
（索引缓存在输出目录下），理由见 docs/REFERENCE.md。
"""

import gzip
import hashlib
import json
import os

PUA_START, PUA_END = 0xE000, 0xF8FF
FONT_EXT_RE = ("woff2", "woff", "otf", "ttf")

# 参考字体（唯一已验证可用的版本；换版本会失配，见模块 docstring）
REF_FONT_URL = ("https://cdn.jsdelivr.net/gh/adobe-fonts/source-han-sans"
                "@2.002R/OTF/SimplifiedChinese/SourceHanSansSC-Normal.otf")
REF_FONT_SHA256 = ("69a090057ee75936"  # 前 16 位，完整值见 tools/build_fontmap.py 校验
                   )
REF_FONT_VERSION = "2.002"
REF_INDEX_NAME = "sourcehan-sc-2.002.index.json.gz"


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
#  字形轮廓索引
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
    """把一个字形的轮廓点集序列化成哈希。"""
    from fontTools.pens.recordingPen import RecordingPen
    pen = RecordingPen()
    glyph_set[name].draw(pen)
    parts = [op + "|" + ",".join(f"{x:g}/{y:g}" for x, y in pts)
             for op, pts in pen.value]
    return hashlib.sha1(";".join(parts).encode()).hexdigest()


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
            f"请先运行：F:\\Python314\\python.exe tools\\build_fontmap.py")
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return {h: cp for h, cp in json.load(f).items()}


# ============================================================
#  子集字体 → PUA 映射
# ============================================================

def pua_map_from_font(font_bytes: bytes, ref_index: dict) -> dict:
    """把子集字体解成 {PUA 码位: 真字符}。"""
    from fontTools.ttLib import TTFont
    import io
    font = TTFont(io.BytesIO(font_bytes))
    cmap = font.getBestCmap()
    glyph_set = font.getGlyphSet()

    out, unmatched = {}, []
    for cp, name in cmap.items():
        if not (PUA_START <= cp <= PUA_END):
            continue
        try:
            h = _outline_key(glyph_set, name)
        except Exception:
            unmatched.append(cp)
            continue
        real = ref_index.get(h)
        if real is None:
            unmatched.append(cp)
        else:
            out[cp] = chr(real)
    return {"map": out, "unmatched": unmatched,
            "total_pua": sum(1 for cp in cmap if PUA_START <= cp <= PUA_END)}


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
        os.makedirs(self.cache_dir, exist_ok=True)

    # ---------- 参考索引 ----------
    def ref_index(self, build_if_missing=False, downloader=None):
        if self._ref is None:
            if os.path.exists(self.ref_index_path):
                self._ref = load_ref_index(self.ref_index_path)
                self.log(f"  字体索引已加载（{len(self._ref)} 个轮廓）")
            elif build_if_missing:
                self._ref = self._build_index(downloader)
            else:
                load_ref_index(self.ref_index_path)   # 抛带指引的错误
        return self._ref

    def _build_index(self, downloader):
        """下载参考字体（一次性）并生成索引。"""
        import tempfile
        if downloader is None:
            raise FontDecodeError("需要下载参考字体，但未提供下载函数")
        self.log("  首次使用：下载参考字体 SourceHanSansSC-Normal 2.002（约 17MB，一次性）")
        data = downloader(REF_FONT_URL)
        if not data or len(data) < 1024 * 1024:
            raise FontDecodeError(f"参考字体下载异常（{len(data or b'')} 字节）")
        sha = hashlib.sha256(data).hexdigest()
        self.log(f"  参考字体 sha256={sha[:16]}…")
        if not sha.startswith(REF_FONT_SHA256):
            self.log(f"  ! 警告：参考字体指纹与记录不一致（期望 {REF_FONT_SHA256}…）"
                     f"——版本漂移会导致解码失败，请复核 REF_FONT_URL")
        fd, tmp = tempfile.mkstemp(suffix=".otf")
        os.close(fd)
        try:
            with open(tmp, "wb") as f:
                f.write(data)
            idx = build_ref_index(tmp, self.log)
        finally:
            try:
                os.remove(tmp)
            except OSError:
                pass
        size = save_ref_index(idx, self.ref_index_path)
        self.log(f"  索引已写出：{self.ref_index_path}（{size / 1024:.0f} KB）")
        return idx

    # ---------- 单字体映射 ----------
    def map_for_font(self, font_bytes: bytes, build_if_missing=False,
                     downloader=None) -> dict:
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
                self.log(f"  PUA 映射命中缓存（{len(m)} 个码位，字体 {sig}）")
                return m
            except (OSError, json.JSONDecodeError, KeyError):
                pass

        ref = self.ref_index(build_if_missing=build_if_missing,
                             downloader=downloader)
        res = pua_map_from_font(font_bytes, ref)
        m = res["map"]
        self.log(f"  PUA 映射：{len(m)}/{res['total_pua']} 个码位已还原"
                 + (f"，{len(res['unmatched'])} 个未匹配" if res["unmatched"] else ""))
        try:
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump({"map": {str(k): v for k, v in m.items()}}, f,
                          ensure_ascii=False)
        except OSError:
            pass
        self._maps[sig] = m
        return m


# ============================================================
#  依赖检查
# ============================================================

def deps_available() -> tuple:
    """返回 (是否可用, 缺失说明)。"""
    missing = []
    try:
        import fontTools  # noqa: F401
    except ImportError:
        missing.append("fontTools")
    try:
        import brotli  # noqa: F401
    except ImportError:
        # brotli 只读 woff2 时才需要；otf/ttf 不需要
        pass
    if missing:
        return False, ("缺少依赖：" + "、".join(missing)
                       + "。安装：F:\\Python314\\python.exe -m pip install fontTools brotli")
    return True, ""
