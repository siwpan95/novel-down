#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
站点规则：schema、加载、校验、URL 匹配与构造。

规则是 JSON，一个站点一个文件，放在 noveldown/rules/*.json。
新增站点只需加 JSON，不改代码（见 docs/RULES.md）。

规则字段总览
------------
id / name / match[] / enabled / free_only / predecode
book.url_pattern        书籍 URL 正则（用于从 URL 提取 bid）
book.info_url           {origin} {bid} 占位符
book.title/author/...   候选 CSS 选择器数组，或 meta 属性选择器
catalog.pages.mode      single | select | template
catalog.item_selector   章节项 <a> 的 CSS 选择器
catalog.id_from         href | onclick，以及对应正则
catalog.volume_selector 可选卷标题选择器
chapter.content_selector 正文容器 CSS
chapter.strip_selectors  正文内需剔除的元素
chapter.next_page        分页规则（同一章的多页拼装）
chapter.ad_patterns      广告行特征
"""

import json
import os
import re

from .freeguard import assert_site_allowed, FreeGuardError

RULES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rules")

REQUIRED_FIELDS = ("id", "name", "match", "free_only")


class RuleError(ValueError):
    """规则文件非法。"""


class Rule:
    """一个站点规则。"""

    def __init__(self, raw: dict, path: str = ""):
        self.raw = raw
        self.path = path
        self.id = raw.get("id", "")
        self.name = raw.get("name", self.id)
        self.match = list(raw.get("match") or [])
        self.enabled = bool(raw.get("enabled", True))
        # 池子：把规则按来源性质分类展示（正版 / 免费镜像）。只影响展示与统计，不影响抓取。
        self.pool = raw.get("pool", "")
        self.free_only = bool(raw.get("free_only", False))
        self.predecode = bool(raw.get("predecode", True))
        self.notes = raw.get("notes", "")
        self.disabled_reason = raw.get("disabled_reason", "")
        self.demo_url = raw.get("demo_url", "")
        self.requires_js = bool(raw.get("requires_js", False))
        self.font_decode = raw.get("font_decode") or None
        # 取页路由：http（默认，纯 HTTP）| browser（真实浏览器渲染后再取 DOM）
        self.fetch_mode = raw.get("fetch_mode", "http")
        self.browser_cfg = raw.get("browser") or {}

    # ---------------- 校验 ----------------
    def validate(self):
        for f in REQUIRED_FIELDS:
            if f not in self.raw:
                raise RuleError(f"{self.path or self.id}: 缺少必填字段 '{f}'")
        if not self.free_only:
            raise RuleError(
                f"{self.id}: free_only 必须为 true —— "
                f"本项目仅处理免费章节（见 docs/FREE_ONLY.md）")
        if not self.match:
            raise RuleError(f"{self.id}: match 不能为空")
        # 第 2 层：规则自带 URL 也要过项目声明名单
        if self.demo_url:
            assert_site_allowed(self.demo_url)

        # 停用的规则是「调研记录存根」：只需说明为何做不到，
        # 不要求写全 book/catalog/chapter（避免为一份说明堆几十行无用配置）。
        if not self.enabled:
            return self

        for key in ("book", "catalog", "chapter"):
            if key not in self.raw:
                raise RuleError(f"{self.id}: 缺少 '{key}' 段")
        if not self.raw["catalog"].get("item_selector"):
            cat = self.raw["catalog"]
            if cat.get("mode") != "json_api":
                raise RuleError(f"{self.id}: catalog.item_selector 不能为空"
                                f"（或改用 catalog.mode=json_api 并配 catalog.json）")
            if not (cat.get("json") or {}).get("url"):
                raise RuleError(f"{self.id}: json_api 模式必须提供 catalog.json.url")
        if not self.raw["chapter"].get("content_selector"):
            raise RuleError(f"{self.id}: chapter.content_selector 不能为空")
        if self.fetch_mode not in ("http", "browser"):
            raise RuleError(f"{self.id}: fetch_mode 只能是 http 或 browser，"
                            f"当前为 {self.fetch_mode!r}")
        # 等待条件：字符串（全角色）或对象（逐角色）——错误类型要**加载即报**，
        # 不能等到真正抓取那一刻才炸。
        ws = self.browser_cfg.get("wait_selector")
        if isinstance(ws, dict):
            unknown = [k for k in ws if k not in self.WAIT_ROLES]
            if unknown:
                raise RuleError(
                    f"{self.id}: browser.wait_selector 出现未知角色 {unknown}，"
                    f"只允许 {list(self.WAIT_ROLES)}")
        elif ws is not None and not isinstance(ws, str):
            raise RuleError(f"{self.id}: browser.wait_selector 只能是字符串或对象，"
                            f"当前为 {type(ws).__name__}")
        # 导航重试次数（瞬时网络错误）：抽查站点普遍抽风，允许逐站调大，
        # 但设个上限防止配置事故把单次抓取拖成分钟级。
        nr = self.browser_cfg.get("nav_retries")
        if nr is not None and not (isinstance(nr, int) and 1 <= nr <= 8):
            raise RuleError(f"{self.id}: browser.nav_retries 必须是 1~8 的整数，"
                            f"当前为 {nr!r}")
        return self

    # ---------------- 匹配 ----------------
    def matches(self, url: str) -> bool:
        from urllib.parse import urlparse
        host = (urlparse(url).hostname or "").lower()
        return any(host == d or host.endswith("." + d) for d in self.match)

    # ---------------- 便捷访问 ----------------
    WAIT_ROLES = ("book", "catalog", "chapter")

    def wait_selector_for(self, role: str):
        """按**页面角色**解析浏览器等待选择器，返回 None 表示不等待。

        `browser.wait_selector` 支持两种写法：

        · **字符串**（旧写法，完全等价于历史行为）：所有角色共用。
          历史上它就是这么被用的 —— qidian 填的是**书籍页**的 `#bookName`，
          速读谷/搜书网填的是**章节页**的 `div.con` / `#chaptercontent`。
        · **对象**：`{"book": sel, "catalog": sel, "chapter": sel}`，逐角色指定。
          未出现的角色 = 不等待；值写 `null`/`false`/`""` 亦为不等待。

        为什么需要对象写法（v0.8.1，实测踩到）：字符串写法是**全角色广播**，
        而三处页面的就绪标志天然不同。速读谷把章节容器 `div.con` 写成顶层字符串后，
        **书籍页**也要等 `div.con` → 不存在 → 白等满 30 秒超时才继续（实测目录耗时 37s，
        其中 30s 是纯浪费）。目录页同理。改成对象即可精确到角色。

        优先级：`catalog`/`chapter` 段内的 `browser_wait_selector` > 本方法的角色值。
        """
        raw = self.browser_cfg.get("wait_selector")
        if raw is None:
            return None
        if isinstance(raw, str):
            return raw.strip() or None
        if isinstance(raw, dict):
            val = raw.get(role)
            return val.strip() if isinstance(val, str) and val.strip() else None
        raise RuleError(f"{self.id}: browser.wait_selector 只能是字符串或对象，"
                        f"当前为 {type(raw).__name__}")

    @property
    def book_cfg(self) -> dict:
        return self.raw.get("book", {})

    @property
    def catalog_cfg(self) -> dict:
        return self.raw.get("catalog", {})

    @property
    def chapter_cfg(self) -> dict:
        return self.raw.get("chapter", {})

    def extract_bid(self, url: str):
        """从书籍 URL 提取书籍 ID。"""
        pat = self.book_cfg.get("url_pattern")
        if not pat:
            return None
        m = re.search(pat, url)
        return m.group(1) if m else None

    def book_page_url(self, url: str, bid: str) -> str:
        from urllib.parse import urlparse
        p = urlparse(url)
        origin = f"{p.scheme}://{p.netloc}"
        tpl = self.book_cfg.get("info_url") or "{url}"
        return (tpl.replace("{origin}", origin)
                   .replace("{bid}", bid or "")
                   .replace("{url}", url))

    def __repr__(self):
        return f"<Rule {self.id} enabled={self.enabled}>"


# ============================================================
#  加载
# ============================================================

def load_rules(rules_dir: str = RULES_DIR, strict: bool = True) -> dict:
    """加载全部规则。返回 {id: Rule}。

    strict=True 时非法规则直接抛错；False 时跳过并收集错误。
    """
    rules = {}
    errors = []
    if not os.path.isdir(rules_dir):
        raise RuleError(f"规则目录不存在：{rules_dir}")
    for fn in sorted(os.listdir(rules_dir)):
        if not fn.endswith(".json"):
            continue
        path = os.path.join(rules_dir, fn)
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            rule = Rule(raw, path).validate()
        except (json.JSONDecodeError, RuleError, FreeGuardError) as e:
            errors.append(f"{fn}: {e}")
            if strict:
                raise
            continue
        rules[rule.id] = rule
    load_rules.errors = errors
    return rules


def find_rule(url: str, rules: dict = None) -> Rule:
    """按 URL 找到匹配规则。

    只在**启用**的规则里匹配。若命中的规则被停用，明确说明停用原因 ——
    停用往往是因为「站点技术上做不到」（WAF / 需要浏览器会话 / 目录靠 JS），
    而**不是**因为「站点含 VIP 内容」：含 VIP 的正版站是允许的，
    VIP 章节由章节级的目录标记与正文付费墙拦下。
    """
    assert_site_allowed(url)
    rules = rules if rules is not None else load_rules()

    matched = [r for r in rules.values() if r.matches(url)]
    active = [r for r in matched if r.enabled]
    if active:
        return active[0]

    if matched:
        r = matched[0]
        reason = r.disabled_reason or r.notes or "未说明"
        raise RuleError(
            f"站点 {r.id} 有规则但已停用。\n停用原因：{reason}\n"
            f"若确认可用，把规则文件里的 \"enabled\" 改为 true。")

    raise RuleError(
        f"没有匹配的站点规则：{url}\n"
        f"可用规则：{', '.join(sorted(r.id for r in rules.values() if r.enabled)) or '(空)'}\n"
        f"新增站点请参考 docs/RULES.md")


def active_rules(rules: dict = None) -> dict:
    """仅返回启用的规则。"""
    rules = rules if rules is not None else load_rules()
    return {k: v for k, v in rules.items() if v.enabled}


def site_overview(rules: dict = None) -> list:
    """站点总览（含停用原因），供 CLI `sites` 输出。"""
    rules = rules if rules is not None else load_rules()
    out = []
    for r in sorted(rules.values(), key=lambda x: (not x.enabled, x.id)):
        out.append({
            "id": r.id, "name": r.name, "enabled": r.enabled, "pool": r.pool,
            "requires_js": r.requires_js, "demo_url": r.demo_url,
            "reason": "" if r.enabled else (r.disabled_reason or r.notes or "未说明"),
        })
    return out
