#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
免费章节硬拦截层（free-only guard）。

设计原则
--------
本项目**只抓取免费章节**，绝不涉及任何 VIP 付费内容。约束是**多层**的，
任何一层命中即拒绝，且没有「跳过开关」：

第 1 层（站点层）——付费站黑名单
    起点/纵横/17K/晋江/刺猬猫/飞卢等以 VIP 章节为主的站点直接拒绝，
    连规则都不提供。见 constants.PAID_SITE_DENYLIST。

第 2 层（规则层）——规则必须显式声明 free_only
    站点规则 JSON 里 `free_only` 必须为 true 才被加载；
    启动时对规则 url 再做一次域名黑名单校验。

第 3 层（目录层）——章节项 VIP 标记
    目录里的章节名/class 命中 VIP 标记（vip/lock/paid/订阅/付费…）时，
    该章节标记为 locked，**不发起请求**。

第 4 层（正文层）——付费墙特征 + 最小字数
    已抓到的正文若命中 PAYWALL_MARKERS（"本章为VIP章节"/"订阅后可阅读"/
    "余额不足"/"请先登录"…）或字数低于 MIN_CHAPTER_CHARS，
    判定为受保护内容，**正文立即丢弃**，只保留状态与原因。

第 5 层（导出层）——终检
    任何导出器写盘前调用 `assert_no_protected()`，
    只要存在 locked/blocked 章节就抛错，确保拦截失效时是「失败」而非「静默泄漏」。

第 6 层（代码层）——不存在凭据路径
    全项目无 cookie / 登录 / 购买 / token 相关参数与函数（可用
    `python -m noveldown selfcheck` 机械校验）。
"""

from .constants import (PAID_SITE_DENYLIST, PAYWALL_MARKERS,
                        VIP_ITEM_CLASS_MARKERS, VIP_ITEM_TEXT_MARKERS,
                        MIN_CHAPTER_CHARS)
from .models import STATUS_BLOCKED, STATUS_EMPTY


class FreeGuardError(RuntimeError):
    """免费章节约束被违反。"""


def site_of(url: str) -> str:
    """从 URL 提取小写 host（不含 www.）。"""
    from urllib.parse import urlparse
    host = (urlparse(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def assert_site_allowed(url: str):
    """第 1 层：付费站黑名单校验。命中即抛 FreeGuardError。"""
    host = site_of(url)
    for denied in PAID_SITE_DENYLIST:
        if host == denied or host.endswith("." + denied) or host.startswith(denied):
            raise FreeGuardError(
                f"拒绝处理付费站点：{host}（命中黑名单 {denied}）。\n"
                f"本项目仅用于免费章节，不提供 VIP/付费章节的任何抓取能力。"
            )
    return host


def is_vip_item(class_attr: str, text: str) -> tuple:
    """第 3 层：判断目录项是否为受保护章节。

    Returns: (是否受保护, 命中原因)

    · class 判定用宽表（vip / lock / paid…），因为站点加 class 的意图很明确。
    · 标题文本判定用**窄表**（只认徽章形态），因为标题里的普通词
      （如「第3章 付费墙占位」）并不代表该章受保护——
      实测踩过：宽表会让合法免费章节被整批误锁。
    · 大小写不敏感（站点写 "VIP"，标记词是小写）。
    """
    cls = (class_attr or "").lower()
    for m in VIP_ITEM_CLASS_MARKERS:
        if m in cls:
            return True, f"目录项 class 命中 '{m}'"
    low = (text or "").lower()
    for m in VIP_ITEM_TEXT_MARKERS:
        if m.lower() in low:
            return True, f"目录项标题命中徽章 '{m}'"
    return False, ""


def check_content(paragraphs) -> tuple:
    """第 4 层：正文付费墙 + 字数校验。

    Returns: (是否受保护, 状态, 原因)
    """
    text = "\n".join(paragraphs or [])
    if not text.strip():
        return False, STATUS_EMPTY, "正文为空"
    low = text.lower()
    for m in PAYWALL_MARKERS:
        if m.lower() in low:
            return True, STATUS_BLOCKED, f"正文命中付费墙特征 '{m}'"
    if len(text.strip()) < MIN_CHAPTER_CHARS:
        return False, STATUS_EMPTY, f"正文仅 {len(text.strip())} 字，低于阈值 {MIN_CHAPTER_CHARS}"
    return False, None, ""


def assert_no_protected(chapters, context: str = "export"):
    """第 5 层：导出前终检。存在受保护章节即抛错。"""
    bad = [c for c in chapters if c.is_protected]
    if bad:
        detail = "；".join(f"#{c.index} {c.title}({c.status}: {c.note})" for c in bad[:5])
        more = f" 等 {len(bad)} 章" if len(bad) > 5 else ""
        raise FreeGuardError(
            f"[{context}] 检出 {len(bad)} 个受保护章节，拒绝导出：{detail}{more}\n"
            f"这是免费章节约束的终检，属预期行为，非程序错误。"
        )


def filter_exportable(chapters):
    """筛出真正可导出的章节。

    条件 = 有实际正文（status==ok 且字数 > 0）。
    这**同时**排除了两类：受保护章节（locked/blocked），
    以及尚未抓取（pending）/ 抓取失败（failed/empty）的章节。

    坑（实测踩过）：早期版本只判 `not is_protected`，导致限流抓取 30 章时
    EPUB 里被塞进 169 个章节文件（139 个空章）。用 has_content 才是对的。
    """
    return [c for c in chapters if c.has_content]


# ============================================================
#  第 6 层：代码层机械自检
# ============================================================
# 用「代码形态」正则而非裸词匹配——否则文档里描述约束的文字会被误判为违规。
FORBIDDEN_PATTERNS = (
    (r"\bcookies?\s*[:=]", "cookie 变量 / 参数赋值"),
    (r"[\"']Cookie[\"']", "Cookie 请求头字段"),
    (r"\bset_cookie\b|\bcookiejar\b", "Cookie 写入调用"),
    (r"--vip\b", "--vip 开关"),
    (r"\bpassword\b|\bpasswd\b", "口令字段"),
    (r"[\"']token[\"']|\btoken\s*=", "token 字段"),
    (r"/login\b|\blogin_by_\w*\b|\bsign_in\b", "登录路径"),
    (r"\bbuy_chapter\b|\bpurchase\b|\bpaywall_bypass\b", "购买 / 绕过付费墙"),
)

# 自检自身的豁免：这些文件**就是**用来声明约束的，必然含描述性词汇。
SELFCHECK_EXEMPT = {"freeguard.py", "constants.py"}

# 跳过的目录。tests/ 里有**故意构造**的违规样本（用于验证自检有效），
# 属预期内容且不参与运行时分发，故排除。
SELFCHECK_SKIP_DIRS = {"__pycache__", ".git", "output", "cache", "state",
                       "fixtures", "_ref", "dist", "build", ".venv", "tests"}


def selfcheck(root_dir: str) -> dict:
    """扫描源码，确认不存在任何凭据 / 付费相关代码路径。

    跳过：注释行、tests/ 与缓存/产物目录。
    Returns: {"ok": bool, "violations": [(rel_path, line_no, what, line)]}
    """
    import os
    import re as _re

    compiled = [(_re.compile(p), what) for p, what in FORBIDDEN_PATTERNS]
    violations = []

    for dirpath, dirnames, filenames in os.walk(root_dir):
        dirnames[:] = [d for d in dirnames if d not in SELFCHECK_SKIP_DIRS]
        for fn in filenames:
            if not fn.endswith(".py") or fn in SELFCHECK_EXEMPT:
                continue
            path = os.path.join(dirpath, fn)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    for i, line in enumerate(f, 1):
                        stripped = line.strip()
                        if stripped.startswith("#"):
                            continue
                        for rx, what in compiled:
                            if rx.search(line):
                                violations.append(
                                    (os.path.relpath(path, root_dir), i, what,
                                     stripped[:100]))
            except (OSError, UnicodeDecodeError):
                continue
    return {"ok": not violations, "violations": violations}
