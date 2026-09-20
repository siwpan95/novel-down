#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
预解码器：还原「JS 内联 base64 正文」类反爬。

背景（实测证据，2026-09-20）
---------------------------
多个笔趣阁系站点把每段正文 base64 编码后塞进脚本标签，由 JS 在客户端还原：

    <script>document.writeln(qsbs.bb('PHA+4oCc5ZOS77yM5ZOS77yM5ZOS44CC4oCdPC9wPg=='))</script>
    <script>document.writeln(vmehyrmd.kd('PHA+54KO54KO5aSP5pel...'))</script>

其中命名空间 `qsbs` / `vmehyrmd` 与函数名 `bb` / `kd` **每站/每次渲染随机**，
所以不能用固定的 `qsbs.bb` 去匹配——必须用「任意 ident.ident('base64')」的通配形态。

实测数据（bqgbe.cc /txt/445/54948.html）：33 处 payload → 33 段正文 1099 字。

致命陷阱
--------
`document.writeln(X)` 被替换成 HTML 后，外层 `<script>` 标签仍在：

    <script><p>正文…</p></script>

而 **HTML 解析器把 `<script>` 的内容当作纯文本（CDATA 式），不会解析内部标签**。
因此必须同时把「内容已变成 HTML 的 script 标签」拆掉，否则 bs4 选不到任何 `<p>`。
（本模块实测踩过：字符串里 `count("<p>")==26`，bs4 里却是 0 个元素。）
"""

import base64
import re

# ------------------------------------------------------------
#  document.write / writeln ( NS.FN('b64') )
# ------------------------------------------------------------
_NS_CALL = (
    r"(?:[A-Za-z_$][\w$]*\s*\.\s*)*"          # 可选的多级命名空间 a.b.
    r"[A-Za-z_$][\w$]*\s*\(?\s*"               # 函数名
)
_B64 = r"(?P<payload>[A-Za-z0-9+/=\s]{16,})"

_WRITELN_RE = re.compile(
    r"document\s*\.\s*write(?:ln)?\s*\(\s*"
    + _NS_CALL +
    r"'?\s*" + _B64 + r"\s*'?\s*\)?\s*\)",
    re.S,
)

# 无 document.write 包装的直接调用：NS.FN('b64')
_BARE_CALL_RE = re.compile(
    r"(?<![\w$.])"
    r"(?:[A-Za-z_$][\w$]*\s*\.\s*)+[A-Za-z_$][\w$]*\s*\(\s*'" + _B64 + r"'\s*\)",
    re.S,
)

# atob('b64')
_ATOB_RE = re.compile(r"atob\s*\(\s*'" + _B64 + r"'\s*\)", re.S)

# <script> 内部已是 HTML 标记 → 拆壳
_SCRIPT_HTML_RE = re.compile(
    r"<script\b[^>]*>\s*(?P<inner>(?:\s*<[a-zA-Z][^>]*>.*?</[a-zA-Z][^>]*>\s*|<br\s*/?>\s*)+)\s*;?\s*</script>",
    re.S,
)


def _decode_payload(b64: str):
    """解码单个 base64 payload，失败返回 None。

    校验：必须能 UTF-8 解码，且看起来是文本/HTML（含有可读字符）。
    """
    s = re.sub(r"\s+", "", b64)
    if len(s) < 16:
        return None
    pad = (-len(s)) % 4
    if pad:
        s += "=" * pad
    try:
        raw = base64.b64decode(s, validate=False)
    except Exception:
        return None
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return None
    # 防止误伤：解码结果应含中文或 HTML 标记
    if not any(ch > "\u2e80" for ch in text) and "<" not in text:
        return None
    return text


def predecode(html: str, enabled: bool = True) -> tuple:
    """对 HTML 做预解码，返回 (新 HTML, 统计字典)。

    统计字段：
        payloads  —— 成功还原的 base64 片段数
        unwrapped —— 拆掉的「内容为 HTML」的 script 标签数
        kind      —— 命中的解码形态（writeln / bare / atob）
    """
    stats = {"payloads": 0, "unwrapped": 0, "kind": None}
    if not enabled or not html:
        return html, stats

    def _sub_factory(kind):
        def _sub(m):
            text = _decode_payload(m.group("payload"))
            if text is None:
                return m.group(0)
            stats["payloads"] += 1
            stats["kind"] = kind
            return text
        return _sub

    out = _WRITELN_RE.sub(_sub_factory("writeln"), html)
    if stats["payloads"] == 0:
        out = _BARE_CALL_RE.sub(_sub_factory("bare"), out)
    if stats["payloads"] == 0:
        out = _ATOB_RE.sub(_sub_factory("atob"), out)

    if stats["payloads"]:
        before = out
        out = _SCRIPT_HTML_RE.sub(lambda m: m.group("inner"), out)
        stats["unwrapped"] = len(_SCRIPT_HTML_RE.findall(before))

    return out, stats


def decode_stats_summary(stats: dict) -> str:
    """人类可读的解码摘要。"""
    if not stats.get("payloads"):
        return "无内联编码"
    return (f"还原 {stats['payloads']} 段 base64（形态 {stats['kind']}）"
            f"，拆 script 壳 {stats['unwrapped']} 处")
