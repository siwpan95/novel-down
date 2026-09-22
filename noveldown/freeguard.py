#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
免费章节硬拦截层（free-only guard）。

设计原则
--------
本项目**只抓取免费章节**，绝不涉及任何 VIP 付费内容。约束是**多层**的，
任何一层命中即拒绝，且没有「跳过开关」：

第 1 层（站点层）——**项目明确声明不支持的域名**
    注意这里**不是**「含 VIP 的站点」黑名单。含 VIP 章节不构成拒绝理由：
    一本小说通常前几十章免费，一律整站拒掉会把可用站点砍到只剩盗版站。
    默认策略为空（POLICY_DENYLIST），只放项目主动声明不支持的域名。
    真正该拦的是「**该章节**需要登录/付费」，那由第 3/4 层在**章节级**处理。

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

from .constants import (POLICY_DENYLIST, PAYWALL_MARKERS,
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
    """第 1 层：项目声明不支持的域名校验（默认空名单）。

    这里**只**查 POLICY_DENYLIST —— 它是「项目主动声明不支持」的政策旋钮，
    不是「含 VIP 内容」的技术判断。含 VIP 的正版站是允许的，
    其 VIP 章节由第 3/4 层在章节级拦下。

    Returns: host
    Raises: FreeGuardError（命中政策名单时）
    """
    host = site_of(url)
    for denied in POLICY_DENYLIST:
        # ⚠⚠ 这里**故意**保留 `startswith`（fail-closed），不是笔误 —— 2026-09-22 记录：
        #
        #   审计报告 #11 曾建议删掉它，理由是「`endswith("."+d)` 已够挡子域，
        #   `startswith` 没有安全增益，反而会误拦 `example-bad.competitor.org`」。
        #   **实测后不采纳这条建议**：政策名单要防的是「**用相似域名绕过**」——
        #   例如名单里写了 `example-bad.com`，而 `example-bad.com.evil.net`
        #   既不等于它、也不以 `.example-bad.com` 结尾（结尾是 `.evil.net`），
        #   删掉 startswith 后就**拦不住了**。tests/test_freeguard.py 里那条用例
        #   正是钉这个行为的（我删掉后它立刻报红）。
        #
        #   语义区别很关键：
        #     · 这里 = **政策名单**（「本项目不做这些站」）→ 宁可误拦，fail-closed；
        #     · `rules.matches()` = **规则匹配**（判断此 URL 属于哪条规则）→ 必须严格，
        #       那里的 host 比对只允许「相等 / 子域」，`example.com.evil.net` 已复现被拒。
        #   两处judgement 不同是**有意的**，不要图省事合并。
        if host == denied or host.endswith("." + denied) or host.startswith(denied):
            raise FreeGuardError(
                f"该域名在项目声明的不支持名单内：{host}（命中 {denied}）。\n"
                f"如需支持，请从 constants.POLICY_DENYLIST 移除并补充站点规则。"
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


def check_content(paragraphs, extra_markers=None) -> tuple:
    """第 4 层：正文付费墙 + 字数校验。

    Args:
        paragraphs: 段落列表
        extra_markers: 站点级补充特征词（规则里的 `chapter.vip_markers`）。
            用于全局表覆盖不到的站点自有信号 —— 例如 17K 用不同的 CSS 文件区分
            免费/付费章（`chapter_free.css` / `chapter_vip.css`），
            把 `chapter_vip` 写进规则即可判定。

    Returns: (是否受保护, 状态, 原因)
    """
    text = "\n".join(paragraphs or [])
    if not text.strip():
        return False, STATUS_EMPTY, "正文为空"
    low = text.lower()
    for m in PAYWALL_MARKERS:
        if m.lower() in low:
            return True, STATUS_BLOCKED, f"正文命中付费墙特征 '{m}'"
    for m in (extra_markers or []):
        if m and m.lower() in low:
            return True, STATUS_BLOCKED, f"正文命中站点级受保护特征 '{m}'"
    if len(text.strip()) < MIN_CHAPTER_CHARS:
        return False, STATUS_EMPTY, f"正文仅 {len(text.strip())} 字，低于阈值 {MIN_CHAPTER_CHARS}"
    return False, None, ""


def check_page_markers(page_html: str, extra_markers=None) -> tuple:
    """在**页面 HTML**（而非正文段落）里找站点级受保护特征。

    有些站点不把付费墙写在正文里，而是换个 CSS / 加个标记类
    （17K：`chapter_free.css` vs `chapter_vip.css`）。
    这类信号要在整页 HTML 上匹配才有效。

    Returns: (是否受保护, 原因)
    """
    if not page_html:
        return False, ""
    low = page_html.lower()
    for m in (extra_markers or []):
        if m and m.lower() in low:
            return True, f"页面命中站点级受保护特征 '{m}'"
    return False, ""


def assert_no_protected(chapters, context: str = "export"):
    """第 5 层：导出前终检 —— 受保护章节**不得携带正文**。

    注意这里检查的是「**泄漏**」，不是「存在」。
    站点目录里标了 VIP 的章节本来就该存在并被跳过：一本 705 章的书有 650 章 VIP
    是**正常状态**，那些章节一直躺在章节表里（状态 locked、正文为空）是对的。
    如果改成「存在受保护章节就拒绝导出」，那么任何含 VIP 的正版站都永远导不出来
    —— 又是把粒度放错了层级。

    真正要防的是：`locked` / `blocked` 的章节**却带着正文**。
    那意味着某层拦截失效（比如目录标记没生效、或付费墙正文没被丢弃），
    此时必须失败而不是静默写进成品。
    """
    leaked = [c for c in chapters if c.is_protected and c.paragraphs]
    if leaked:
        detail = "；".join(
            f"#{c.index} {c.title}({c.status}, {len(c.paragraphs)} 段)"
            for c in leaked[:5])
        more = f" 等 {len(leaked)} 章" if len(leaked) > 5 else ""
        raise FreeGuardError(
            f"[{context}] 检出 {len(leaked)} 个受保护章节**携带正文**，拒绝导出：{detail}{more}\n"
            f"这说明拦截失效（受保护内容泄漏），属实现缺陷，请勿绕过。"
        )


def assert_export_shape(exportable, context: str = "export"):
    """附加检查：传给导出器的集合里不得混入受保护章节。

    这是一道「形状」断言 —— 即使将来有人改了 `filter_exportable` 的过滤条件，
    这里也会拦住，避免受保护章节静默进入产物。
    """
    bad = [c for c in exportable if c.is_protected]
    if bad:
        raise FreeGuardError(
            f"[{context}] 可导出集合里混入了 {len(bad)} 个受保护章节："
            + "；".join(f"#{c.index} {c.title}" for c in bad[:5]))


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
    # 凭据**存储/写入**。排除 `{cookie:NAME}` 占位符 —— 那是浏览器路由里
    # 「从当前页同源 document.cookie 取已存在的 CSRF token 填进 URL」的读取，
    # 不涉及任何用户凭据的保存或外发（见 noveldown/browser.py 的说明）。
    (r"(?<!\{)\bcookies?\s*[:=]", "cookie 变量 / 参数赋值"),
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
                       "fixtures", "_ref", "dist", "build", ".venv", "tests", ".deps"}


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
