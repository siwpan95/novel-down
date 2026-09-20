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
        self.free_only = bool(raw.get("free_only", False))
        self.predecode = bool(raw.get("predecode", True))
        self.notes = raw.get("notes", "")
        self.demo_url = raw.get("demo_url", "")
        self.requires_js = bool(raw.get("requires_js", False))

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
        for key in ("book", "catalog", "chapter"):
            if key not in self.raw:
                raise RuleError(f"{self.id}: 缺少 '{key}' 段")
        if not self.raw["catalog"].get("item_selector"):
            raise RuleError(f"{self.id}: catalog.item_selector 不能为空")
        if not self.raw["chapter"].get("content_selector"):
            raise RuleError(f"{self.id}: chapter.content_selector 不能为空")
        # 第 2 层：规则自带 URL 也必须过付费站黑名单
        if self.demo_url:
            assert_site_allowed(self.demo_url)
        return self

    # ---------------- 匹配 ----------------
    def matches(self, url: str) -> bool:
        from urllib.parse import urlparse
        host = (urlparse(url).hostname or "").lower()
        return any(host == d or host.endswith("." + d) for d in self.match)

    # ---------------- 便捷访问 ----------------
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
    """按 URL 找到匹配规则；先做付费站黑名单校验。"""
    assert_site_allowed(url)          # 第 1 层
    rules = rules if rules is not None else load_rules()
    for r in rules.values():
        if r.matches(url):
            return r
    raise RuleError(
        f"没有匹配的站点规则：{url}\n"
        f"可用规则：{', '.join(sorted(rules)) or '(空)'}\n"
        f"新增站点请参考 docs/RULES.md")


def active_rules(rules: dict = None) -> dict:
    """仅返回启用的规则。"""
    rules = rules if rules is not None else load_rules()
    return {k: v for k, v in rules.items() if v.enabled}
