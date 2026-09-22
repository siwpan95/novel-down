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

# `book.info_api` 片段里允许覆盖的元数据字段（与 parse_book_info 的返回键一一对应）。
INFO_API_FIELDS = ("title", "author", "intro", "cover", "status")


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
            j = cat.get("json") or {}
            # 分页（v0.8.15）：url 里出现 {page} 才会迭代，故 max_pages > 1 才是有效配置
            mp = j.get("max_pages")
            if mp is not None and not (isinstance(mp, int) and 1 <= mp <= 200):
                raise RuleError(f"{self.id}: catalog.json.max_pages 必须是 1~200 的整数，"
                                f"当前为 {mp!r}")
            pf = j.get("page_from")
            if pf is not None and not (isinstance(pf, int) and 0 <= pf <= 100):
                raise RuleError(f"{self.id}: catalog.json.page_from 必须是 0~100 的整数，"
                                f"当前为 {pf!r}")
            if ("{page}" in (j.get("url") or "")) and not (mp and mp > 1):
                raise RuleError(
                    f"{self.id}: catalog.json.url 用了 {{page}} 分页，"
                    f"但 max_pages 未设置或 <= 1 —— 那样只会抓第一页，"
                    f"且**不会报错**（实测仙人掌小说：单页上限 20 章，书有 490 章）")
            auf = j.get("api_url_field")
            if auf is not None and not (isinstance(auf, str) and auf.strip()):
                raise RuleError(f"{self.id}: catalog.json.api_url_field 不能为空串")
        # `chapter.body_api.require`：在数据源上判免费的字段（见 engine._require_violation）
        req = (self.raw["chapter"].get("body_api") or {}).get("require")
        if req is not None:
            if not isinstance(req, dict) or not (req.get("field") or "").strip():
                raise RuleError(f"{self.id}: chapter.body_api.require 必须是含非空 "
                                f"field 的对象，如 {{\"field\": \"data.unlock\"}}")
            tr = req.get("truthy")
            if tr is not None and not (isinstance(tr, list) and tr):
                raise RuleError(f"{self.id}: chapter.body_api.require.truthy 必须是非空数组")
        # `catalog.continuation_title_pattern`（v0.8.16）：多页章回的续页合并依据。
        # 必须是**合法正则**且不能过宽 —— 过宽会把正常章节也并掉（静默少章）。
        ctp = (self.raw["catalog"].get("continuation_title_pattern")
               if isinstance(self.raw.get("catalog"), dict) else None)
        if ctp is not None:
            if not isinstance(ctp, str) or not ctp.strip():
                raise RuleError(f"{self.id}: catalog.continuation_title_pattern 不能为空")
            try:
                rx = re.compile(ctp)
            except re.error as e:
                raise RuleError(f"{self.id}: catalog.continuation_title_pattern "
                                f"不是合法正则（{e}）")
            # 过宽判据：能匹配空串、或能匹配任意常见章节标题（用一组样本试）
            if rx.match(""):
                raise RuleError(f"{self.id}: continuation_title_pattern 能匹配空串 —— "
                                f"会把所有无标题条目都并掉，几乎必然是写错了")
            for sample in ("第一章 起", "第1章", "卷一", "序", "楔子", "[清]曹雪芹"):
                if rx.match(sample):
                    raise RuleError(
                        f"{self.id}: continuation_title_pattern 过宽 —— 它匹配到了正常标题 "
                        f"{sample!r}。该模式只应匹配「纯页码标记」（如 ^[（(]\\d+[）)]$）")
        # `catalog.id_from.pattern` 必须含**命名组 `(?P<cid>…)`**（审计 #4，2026-09-22）：
        # 解析器用 `m.group("cid")` 取章节号，pattern 若写成无名组 `(\d+)` 就抛 IndexError，
        # 而调用处 `except Exception: pass` **把它吞掉** → **目录静默 0 章、不报任何错**，
        # 用户只会看到「怎么一本都没抓到」。
        # 这类配置事故（漏个命名组）完全能在**加载时**拦住，不该留到运行时。
        idf = (self.raw.get("catalog") or {}).get("id_from") or {}
        if isinstance(idf, dict) and idf.get("pattern"):
            try:
                _rx = re.compile(idf["pattern"])
            except re.error as e:
                raise RuleError(f"{self.id}: catalog.id_from.pattern 不是合法正则（{e}）")
            if "cid" not in (_rx.groupindex or {}):
                raise RuleError(
                    f"{self.id}: catalog.id_from.pattern 必须含命名组 `(?P<cid>…)` —— "
                    f"解析器用 m.group(\"cid\") 取章节号；写成无名组会抛 IndexError，"
                    f"而调用处会吞掉异常 → **目录静默 0 章且不报错**。"
                    f"当前 pattern={idf['pattern']!r}")
        if not self.raw["chapter"].get("content_selector"):
            raise RuleError(f"{self.id}: chapter.content_selector 不能为空")
        # `book.info_api`（v0.8.13）：书籍页是 SPA 外壳、简介/封面由 XHR
        # 片段另发时的配置。`url` 必填，字段名必须是我们支持的元数据键 ——
        # 打错字会让「片段里明明有简介」却静默落回主页面，属配置事故。
        iapi = (self.raw.get("book") or {}).get("info_api")
        if iapi is not None:
            if not isinstance(iapi, dict):
                raise RuleError(f"{self.id}: book.info_api 必须是对象")
            if not (iapi.get("url") or "").strip():
                raise RuleError(f"{self.id}: book.info_api.url 不能为空")
            unknown = [k for k in iapi
                       if k not in ("url",) + INFO_API_FIELDS]
            if unknown:
                raise RuleError(f"{self.id}: book.info_api 出现未知字段 {unknown}，"
                                f"只允许 ['url'] + {list(INFO_API_FIELDS)}")
        if self.fetch_mode not in self.FETCH_MODES:
            raise RuleError(f"{self.id}: fetch_mode 只能是 http 或 browser，"
                            f"当前为 {self.fetch_mode!r}")
        # 段内路由覆盖：book / catalog / chapter 各自可以改走另一条路由
        # （书山式「目录要浏览器、正文纯 HTTP」）。非法值**加载即报**。
        for role, key in self.SECTION_BY_ROLE.items():
            sec = self.raw.get(key) or {}
            if not isinstance(sec, dict):
                continue
            mode = sec.get("fetch_mode")
            if mode is None:
                continue
            if not isinstance(mode, str) or mode.strip().lower() not in self.FETCH_MODES:
                raise RuleError(
                    f"{self.id}: {key}.fetch_mode 只能是 http 或 browser，"
                    f"当前为 {mode!r}")
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
    FETCH_MODES = ("http", "browser")
    SECTION_BY_ROLE = {"book": "book", "catalog": "catalog", "chapter": "chapter"}

    def fetch_mode_for(self, role: str) -> str:
        """解析**某个页面角色**的取页路由：段内 `fetch_mode` > 顶层 `fetch_mode`。

        为什么需要它（v0.8.13，实测踩到）：书山（shushan.zhangyue.net）这类站点的
        **目录页**靠 JS 渲染（必须走浏览器），但**章节页**是服务端直出的静态 HTML ——
        纯 HTTP 取一页只要 0.7s，走浏览器要 20s+。顶层只允许一个 `fetch_mode` 时
        只能二选一：要么目录拿不到，要么正文慢 30 倍。

        实测数据（书山 3 章 E2E）：
        · 全浏览器路由 = 82.6s
        · 目录 browser + 正文 http = 见 CHANGELOG 记录（并发还能恢复）

        ⚠ 这条覆盖同时决定**并发是否可用**：只要正文不是浏览器路由，
        `run()` 就不必把并发压成 1（Playwright 同步 API 不能跨线程共享）。
        所以调用方必须用本方法判路由，**不要再直接读 `rule.fetch_mode`**。
        """
        if role not in self.SECTION_BY_ROLE:
            raise RuleError(f"{self.id}: 未知页面角色 {role!r}，"
                            f"只允许 {list(self.WAIT_ROLES)}")
        sec = self.raw.get(self.SECTION_BY_ROLE[role]) or {}
        if isinstance(sec, dict):
            mode = sec.get("fetch_mode")
            if isinstance(mode, str) and mode.strip():
                mode = mode.strip().lower()
                if mode not in self.FETCH_MODES:
                    raise RuleError(f"{self.id}: {role}.fetch_mode 只能是 "
                                    f"http 或 browser，当前为 {mode!r}")
                return mode
        return self.fetch_mode

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

def iter_rule_files(rules_dir: str = RULES_DIR):
    """列出规则文件（**递归**含子目录，顺序确定）。

    规则按池分目录组织（纯组织用途，加载器递归读，不区分层级）：
    - **正版**放 `genuine/`
    - **免费镜像**放 `mirrors/`（批量生成的镜像池，"一个模板一个文件"自动产出，数量到几百条）
    门禁 #12（`tools/check_repo.py`）强制 `pool` 字段与所在文件夹一致，
    从根上杜绝人工拷规则时把镜像误放顶层、导致 `rules/` 散落一地。
    """
    out = []
    for root, dirs, files in os.walk(rules_dir):
        dirs.sort()
        for fn in sorted(files):
            if fn.endswith(".json"):
                out.append(os.path.join(root, fn))
    return out


def load_rules(rules_dir: str = RULES_DIR, strict: bool = True) -> dict:
    """加载全部规则（含子目录）。返回 {id: Rule}。

    strict=True 时非法规则直接抛错；False 时跳过并收集错误。
    """
    rules = {}
    errors = []
    if not os.path.isdir(rules_dir):
        raise RuleError(f"规则目录不存在：{rules_dir}")
    for path in iter_rule_files(rules_dir):
        fn = os.path.relpath(path, rules_dir)
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
