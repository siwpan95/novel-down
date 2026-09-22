#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
抓取引擎：目录发现 → 并发抓取 → 免费拦截 → 断点续爬。

[架构借鉴]
  - 生产者-消费者 + 线程池：源自参考文章 CSDN 139809090 的多线程 Queue 思路，
    但**排除**该文「爬取起点 VIP 内容」的全部语义。
  - 章节校对 / 广告过滤 / 断点续爬：源自 ma6254/FictionDown 的特性设计（GPL-3.0），
    仅借鉴设计思路，未复用代码；其「正版+盗版互补补 VIP」流程已排除。
  - 身份轮换 / 限速 / 退避重试：复用自本家 webcopier（内部项目）。

免费章节约束
------------
抓取前：目录项命中 VIP 标记的章节直接标 locked，**不发起任何请求**。
抓取后：正文命中付费墙特征或字数异常 → 标 blocked，正文丢弃。
导出前：终检（见 freeguard.assert_no_protected）。
"""

import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from . import parser
from .browser import DEFAULT_NAV_RETRIES
from .constants import DEFAULT_CONFIG

# 字体反爬的**最低可接受覆盖率**（审计 #8）。低于它就不还原，改为保留原文 + 告警：
# 半还原的正文「一半对一半是占位符」，比不还原更糟 —— 后者至少一眼能看出有问题。
FONT_DECODE_MIN_COVERAGE = 0.90
from .freeguard import (assert_site_allowed, check_content,
                        check_page_markers, FreeGuardError)
from .http_client import build_headers, http_get, parse_proxy
from .identity_manager import get_identity_manager
from .models import (Book, STATUS_BLOCKED, STATUS_EMPTY, STATUS_FAILED,
                     STATUS_LOCKED, STATUS_OK, STATUS_PENDING)
from .parser import (_dig, body_api_fragment, catalog_links_from_page,
                     catalog_page_urls, collect_catalog_items,
                     collect_json_catalog, normalize_catalog, origin_of,
                     parse_book_info, parse_chapter_page)
from .ratelimit import RateLimiter
# ⚠ 必须显式导入：0 章时 `discover()` 要抛 RuleError。我第一版漏了这行，
#   而当时的测试**没有覆盖 0 章路径**，所以 pytest 全绿也没发现 ——
#   「测试全绿」不等于「这条路能跑」，是这个用例补上之后才暴露的。
from .rules import RuleError
from .rules import find_rule, load_rules
from .state import StateStore

MAX_PAGES_PER_CHAPTER = 30       # 单章最大分页数（防死循环）
STATE_SAVE_INTERVAL = 20         # 每抓 N 章落一次状态

# 「未指定」哨兵：区别于显式的 None（= 明确不等待）。
# 因为 `wait_selector or 顶层默认` 这种写法无法表达「本角色就是不要等待」，
# 于是章节/目录的等待条件会漏到书籍页上白等超时（见 Rule.wait_selector_for）。
_UNSET = object()


def _require_violation(raw_text: str, req: dict) -> str:
    """按 `chapter.body_api.require` 判定响应是否**说明该章受保护**。

    返回 `""` = 通过（可继续抽取正文）；非空 = 受保护的原因（调用方据此判 blocked）。

    为什么需要它（v0.8.15，实测仙人掌小说 360）：
    付费章走正文接口**不报错、也不带任何付费提示**，只返回一段**截断的试读片段**
    （实测 642~714 字符，正文里连一个"付费/VIP"字样都没有）。
    第 4 层「正文付费墙特征」对这种响应**完全失效** —— 会静默导出不完整章节。
    而同一个响应里有 `data.unlock: false` 这种**权威状态字段**，直接用它判最可靠：
    `require: {"field": "data.unlock", "truthy": ["1","true","yes"]}`。

    ⚠ 判定语义是「**取到且落在 truthy 里**才算通过」：字段缺失/为 null/为 false
    都判受保护 —— 宁可漏抓一章，也不能把试读片段当正文导出。
    """
    if not req:
        return ""
    field = req.get("field")
    if not field:
        return ""
    try:
        data = json.loads(raw_text)
    except (ValueError, TypeError):
        return ""
    val = _dig(data, field)
    truthy = {str(x).lower() for x in (req.get("truthy") or ["1", "true", "yes"])}
    if val is not None and str(val).lower() in truthy:
        return ""
    return f"{field}={val!r} 未通过免费校验"


class Downloader:
    """一本书的抓取编排器。"""

    def __init__(self, url: str, config: dict = None, rules: dict = None,
                 log=None, progress=None):
        self.url = url
        # 第 1 层拦截：付费站直接拒绝
        assert_site_allowed(url)

        self.config = {**DEFAULT_CONFIG, **(config or {})}
        self.rules = rules if rules is not None else load_rules()
        self.rule = find_rule(url, self.rules)
        self.log = log or (lambda msg, level="info": None)
        self.progress = progress or (lambda done, total, msg="": None)

        self.idm = get_identity_manager()
        self.limiter = RateLimiter(delay=self.config["delay"],
                                   jitter=self.config["jitter"])
        self.proxies = parse_proxy(self.config.get("proxy"))

        # 提前校验书籍 ID 并建立状态仓库——
        # 断点续爬必须在 discover() 之前就能读到上一次的进度
        self.book_id = self.rule.extract_bid(url)
        if not self.book_id:
            raise ValueError(
                f"无法从 URL 提取书籍 ID（规则 {self.rule.id} 的 "
                f"book.url_pattern 不匹配）：{url}")
        self.store = StateStore(self.config["save_dir"], self.rule.id,
                                self.book_id)

        self.book = None
        self._ident = 0
        self._lock = threading.Lock()
        self._done = 0
        self._total = 0
        self._font_decoder = None       # 惰性创建（仅字体反爬站点需要）
        self._browser_fetcher = None    # 惰性创建（仅 fetch_mode=browser 的站点）

    # ========================================================
    #  HTTP
    # ========================================================
    def _fetch(self, url: str, referer=None, wait_selector=_UNSET,
               role: str = "chapter") -> str:
        # 浏览器路由：目录/正文靠 JS 渲染的站点（见 browser.py）
        # ⚠ 判路由必须走 fetch_mode_for(role) —— 站点可以「目录走浏览器、
        #   正文纯 HTTP」（书山/得间），顶层 fetch_mode 只是默认值。
        if self.rule.fetch_mode_for(role) == "browser":
            if wait_selector is _UNSET:
                wait_selector = self.rule.wait_selector_for(role)
            return self._fetch_browser(url, wait_selector)

        with self._lock:
            ident = self.idm.get_identity(self._ident)
            self._ident += 1
        headers = build_headers(identity=ident, referer=referer)
        self.limiter.wait()

        def _on_retry(attempt, exc, sleep_secs):
            self.limiter.slowdown()
            self.log(f"  重试 {url}（第 {attempt} 次，等待 {sleep_secs:.0f}s）：{exc}",
                     "warn")

        resp = http_get(
            url, headers=headers,
            timeout=self.config["timeout"],
            retries=self.config["retries"],
            proxies=self.proxies,
            use_curl_cffi=self.config.get("use_curl_cffi", False),
            impersonate=self.idm.get_curl_impersonate(ident),
            on_retry=_on_retry,
        )
        self.limiter.recover()
        return resp.text

    # --------------------------------------------------------
    #  浏览器路由（可选依赖 playwright）
    # --------------------------------------------------------
    def _fetch_raw(self, url: str, referer=None, role: str = "chapter") -> str:
        """取**原始文本**（JSON 接口用）。

        浏览器路由下不能用 `pg.goto` —— Chrome 会把 JSON 包成
        `<pre>` 的 HTML 文档，破坏解析。改用页面内 `fetch` 取原始响应体，
        同源请求会自动带上 WAF 下发的匿名 cookie。
        """
        if self.rule.fetch_mode_for(role) == "browser":
            self.limiter.wait()
            return self._browser().fetch_text(url, referer=referer)
        return self._fetch(url, referer=referer, role=role)

    def _collect_json_catalog(self, rule, bid, origin, book_url):
        """按 catalog.mode=json_api 从接口取目录。

        **分页**（v0.8.15）：`catalog.json.url` 里出现 `{page}` 即在多页之间迭代
        （`page_from` 默认 1，`max_pages` 默认 1 = 不分页）。为什么必须有它：
        实测仙人掌小说（360）的目录接口**单次最多只给 20 章**
        （`n` 参数超过 20 会被静默降级成 10），而书有 490 章 ——
        不分页就只能拿到 20 章，且**它不会报错**（表现为"这本书只有 20 章"）。

        停止条件：某页返回 `data.res` 为空；或达到 `max_pages`。
        ⚠ 页内序号（`idx`）**不随分页变化**（每页都是 1..20），
        所以规则里要取**全局序号字段**（`op_ext.money_topic.index`）当 cid。
        """
        cfg = rule.catalog_cfg.get("json") or {}
        tpl = cfg.get("url") or ""
        paged = "{page}" in tpl
        page_from = int(cfg.get("page_from", 1)) if paged else 1
        max_pages = int(cfg.get("max_pages", 1)) if paged else 1
        max_pages = max(1, min(max_pages, 200))

        base = tpl.replace("{origin}", origin).replace("{bid}", bid).replace("{url}", book_url)
        all_items, all_locked = [], []
        for page in range(page_from, page_from + max_pages):
            url = base.replace("{page}", str(page)) if paged else base
            if page == page_from or paged:
                self.log(f"[目录] JSON 接口 第 {page - page_from + 1}/{max_pages} 页 {url}")
            text = self._fetch_raw(url, referer=book_url, role="catalog")
            items, locked = collect_json_catalog(rule, text, bid, origin)
            all_items.extend(items)
            all_locked.extend(locked)
            if not paged:
                break
            if not items and not locked:
                self.log(f"[目录] 第 {page - page_from + 1} 页为空，停止分页")
                break
        self.log(f"[目录] 接口返回：章节 {len(all_items)}，受保护 {len(all_locked)}")
        return all_items, all_locked

    def _browser(self):
        """惰性创建并复用唯一的 BrowserFetcher（只在主线程里用）。"""
        if self._browser_fetcher is None:
            from . import browser as br
            ok, why = br.deps_available()
            if not ok:
                raise br.BrowserUnavailable(why)
            bcfg = self.rule.browser_cfg
            self._browser_fetcher = br.BrowserFetcher(
                headless=bcfg.get("headless", self.config.get("browser_headless", True)),
                timeout=max(self.config["timeout"] * 1000, 45000),
                anti_detect=bool(bcfg.get("anti_detect", False)),
                channel=bcfg.get("channel", ""),
                args=bcfg.get("args"),
                stealth_js=bcfg.get("stealth_js"),
                proxy=bcfg.get("proxy", ""),
                log=self.log).start()
            self.log("  浏览器路由已启动")
        return self._browser_fetcher

    def _fetch_browser(self, url: str, wait_selector: str = None) -> str:
        """⚠ `wait_selector=None` 表示**明确不等待**，不要再回退到顶层默认 ——
        角色解析统一在 `_fetch(role=...)` 里完成（见 Rule.wait_selector_for）。"""
        cfg = self.rule.browser_cfg
        self.limiter.wait()
        html = self._browser().fetch(
            url,
            wait_selector=wait_selector,
            wait_ms=int(cfg.get("wait_ms", 0)),
            click_selectors=cfg.get("click_selectors"),
            scroll=bool(cfg.get("scroll", False)),
            retries=int(cfg.get("nav_retries", DEFAULT_NAV_RETRIES)),
        )
        return html

    def _wait_for(self, section_cfg: dict, role: str):
        """解析某段（catalog/chapter）的等待条件：段内显式声明 > 顶层角色值。

        段内写 `"browser_wait_selector": false` / `""` 即**明确不等待**。
        """
        if section_cfg and "browser_wait_selector" in section_cfg:
            val = section_cfg["browser_wait_selector"]
            return val if isinstance(val, str) and val.strip() else None
        return self.rule.wait_selector_for(role)

    def close(self):
        """释放浏览器资源（run() 结束时会自动调用）。"""
        if self._browser_fetcher is not None:
            try:
                self._browser_fetcher.close()
            finally:
                self._browser_fetcher = None

    def _fetch_bytes(self, url: str, referer=None, role: str = "chapter") -> bytes:
        """抓二进制资源（字体文件用）。"""
        if self.rule.fetch_mode_for(role) == "browser":
            self.limiter.wait()
            return self._browser().fetch_bytes(url)
        with self._lock:
            ident = self.idm.get_identity(self._ident)
            self._ident += 1
        headers = build_headers(identity=ident, referer=referer)
        self.limiter.wait()
        resp = http_get(
            url, headers=headers,
            timeout=self.config["timeout"],
            retries=min(2, self.config["retries"]),
            proxies=self.proxies,
            use_curl_cffi=self.config.get("use_curl_cffi", False),
            impersonate=self.idm.get_curl_impersonate(ident),
        )
        self.limiter.recover()
        return resp.content

    # ========================================================
    #  目录发现
    # ========================================================
    def discover(self, save_state: bool = False) -> Book:
        rule = self.rule
        bid = self.book_id
        book_url = rule.book_page_url(self.url, bid)
        origin = origin_of(book_url)

        self.log(f"[发现] 站点={rule.name} 书籍ID={bid}")
        self.log(f"[发现] 书籍页 {book_url}")
        book_html = self._fetch(book_url, role="book")

        info = parse_book_info(rule, book_html, book_url, bid,
                               info_html=self._book_info_fragment(rule, book_url, bid))
        book = Book(site=rule.id, book_id=bid, url=book_url, **info)

        # ---- 目录收集：JSON 接口 或 HTML ----
        all_items, all_locked = [], []
        if rule.catalog_cfg.get("mode") == "json_api":
            all_items, all_locked = self._collect_json_catalog(rule, bid, origin,
                                                               book_url)
        else:
            catalog_pages = self._discover_catalog_pages(rule, book_url, book_html,
                                                         bid, origin)
            self.log(f"[目录] 共 {len(catalog_pages)} 个目录页")
            for i, (pu, html) in enumerate(catalog_pages, 1):
                if html is None:
                    self.log(f"[目录] 第 {i} 页抓取失败（跳过）：{pu}", "error")
                    continue
                items, locked = collect_catalog_items(rule, html, pu, bid)
                self.log(f"[目录] 第 {i}/{len(catalog_pages)} 页："
                         f"章节 {len(items)}，受保护 {len(locked)}")
                all_items.extend(items)
                all_locked.extend(locked)

        for lk in all_locked:
            lk.setdefault("status", STATUS_LOCKED)
            lk.setdefault("note", lk.get("reason", "目录标记为受保护"))

        sort_mode = rule.catalog_cfg.get("sort", "cid_numeric_asc")
        dedupe = rule.catalog_cfg.get("dedupe", "keep_first")
        chapters = normalize_catalog(all_items + all_locked, sort_mode, dedupe,
                                     rule.catalog_cfg.get("continuation_title_pattern"))
        n_cont = sum(len(c.extra_pages) for c in chapters)
        if n_cont:
            self.log(f"[目录] 续页合并：{n_cont} 个续页条目并入前一章"
                     f"（判定 {rule.catalog_cfg.get('continuation_title_pattern')!r}）")

        if not chapters:
            # ⚠⚠ 「目录 0 章」必须是**显式报错**，不能静默通过（审计 #4，2026-09-22）：
            #   目录解析路径上曾有 `except Exception: pass` 吞掉一切 —— 规则作者把
            #   `catalog.id_from.pattern` 写成无名组 `(\d+)` 时，`m.group("cid")` 抛
            #   IndexError 被吞 → **一本都没抓到、却什么也不报**，用户只会一脸懵。
            #   `rules.validate()` 已在加载时拦住命名组问题，但仍有别的成因会走到这里
            #   （选择器失配 / 需 JS 渲染 / WAF 挑战页），所以这里再兜一层并**说清排查方向**。
            raise RuleError(
                "%s: 目录解析出 **0 章**，已中止。常见原因：\n"
                "  ① catalog.item_selector 与当前页面不匹配（站点改版最常见）\n"
                "  ② 目录页需要 JS 渲染 —— 该站可能要配 browser 路由\n"
                "  ③ 页面被 WAF 拦下，返回的是挑战页而非目录页\n"
                "  ④ 该书的目录确实为空\n"
                "  用 `python -m noveldown probe <书籍URL>` 可逐环节定位。"
                % rule.id)

        book.chapters = chapters
        book.catalog_sort = sort_mode
        book.volumes = sorted({c.volume for c in chapters if c.volume})
        self.book = book

        s = book.stats()
        self.log(f"[目录] 归一化后：共 {s['chapters_total']} 章，"
                 f"待抓 {s['chapters_total'] - s['protected']} 章，"
                 f"受保护 {s['protected']} 章")
        if s["protected"]:
            self.log("[拦截] 检出受保护章节，这些章节不会被请求，也不会进入导出物", "warn")

        if save_state:
            self.store.save_state(book)
        return book

    def _book_info_fragment(self, rule, book_url, bid):
        """`book.info_api`：书籍页是 SPA 外壳、简介/封面另由 XHR 片段下发时取该片段。

        书山（shushan.zhangyue.net）实测：纯 HTTP 取书籍页 30627 字节里
        **没有简介**（`class="intro*"` 零命中），`meta[name=description]` 是
        **站点通用文案**（每本书都一样）—— 直接用它当简介等于往 EPUB 里写错数据。
        真简介在 `/book/bookintro?bid=`（19796 字节片段，纯 HTTP 0.5s）。

        与其他片段一致：取不到就返回 None，由调用方回落主页面选择器，
        **不让元数据缺失升级成整本书失败**。
        """
        cfg = rule.book_cfg.get("info_api") or {}
        tpl = cfg.get("url")
        if not tpl:
            return None
        url = (tpl.replace("{origin}", origin_of(book_url))
                  .replace("{bid}", bid).replace("{url}", book_url))
        self.log(f"[发现] 元数据片段 {url}")
        try:
            return self._fetch_raw(url, referer=book_url, role="book")
        except Exception as e:
            self.log(f"[发现] 元数据片段抓取失败（{e}）——改用书籍页取值", "warn")
            return None

    def _discover_catalog_pages(self, rule, book_url, book_html, bid, origin):
        """迭代发现目录页，返回 [(url, html 或 None), ...]。

        为什么需要迭代：bqgbe.cc 的书籍页**没有** <select>，只提供
        「查看更多章节…」链接指向 /txt/445/ml1.html；而真正的分页列表
        （第101-168章）藏在 ml1.html 的 <select> 里。单次解析拿不到全量目录。
        """
        cfg = rule.catalog_cfg.get("pages") or {}
        mode = cfg.get("mode", "single")
        max_pages = int(cfg.get("max_pages", 80))
        max_rounds = int(cfg.get("max_rounds", 4))

        if mode == "single":
            url = (cfg.get("url") or book_url)
            url = url.replace("{origin}", origin).replace("{bid}", bid)
            if url == book_url:
                return [(book_url, book_html)]
            try:
                html = self._fetch(url, referer=book_url,
                                   wait_selector=self._wait_for(rule.catalog_cfg,
                                                                "catalog"))
            except Exception as e:
                self.log(f"[目录] 抓取失败 {url} — {e}", "error")
                html = None
            return [(url, html)]

        if mode == "template":
            urls = catalog_page_urls(rule, book_html, bid, origin, book_url)
            out = []
            for u in urls:
                try:
                    out.append((u, self._fetch(u, referer=book_url,
                                               role="catalog")))
                except Exception as e:
                    self.log(f"[目录] 抓取失败 {u} — {e}", "error")
                    out.append((u, None))
            return out

        known = {book_url: book_html}
        order = [book_url]
        queue = [book_url]
        rounds = 0
        while queue and len(known) < max_pages and rounds < max_rounds:
            rounds += 1
            candidates = []
            for u in queue:
                html = known.get(u)
                if not html:
                    continue
                for nu in catalog_links_from_page(rule, html, u, bid, origin):
                    if nu not in known and nu not in candidates:
                        candidates.append(nu)
            if not candidates:
                break
            queue = []
            cat_wait = self._wait_for(rule.catalog_cfg, "catalog")
            for u in candidates[:max_pages - len(known)]:
                try:
                    known[u] = self._fetch(u, referer=book_url,
                                           wait_selector=cat_wait)
                    self.log(f"[目录] 发现子目录页 {u}")
                except Exception as e:
                    self.log(f"[目录] 子目录页抓取失败 {u} — {e}", "error")
                    known[u] = None
                order.append(u)
                queue.append(u)

        return [(u, known.get(u)) for u in order]

    # ========================================================
    #  字体反爬解码
    # ========================================================
    def _font_decode(self, page_html, paragraphs):
        """把 PUA 码位还原成真字符。返回 (段落列表, 备注)。"""
        from . import fontdecode as fd

        pua = fd.pua_chars(paragraphs)
        if not pua:
            return paragraphs, ""

        cfg = self.rule.font_decode or {}
        if not cfg.get("enable", True):
            return paragraphs, ""

        with self._lock:
            if self._font_decoder is None:
                cache_dir = os.path.join(self.config["save_dir"], "fontcache")
                self._font_decoder = fd.FontDecoder(cache_dir, log=self.log)
            decoder = self._font_decoder

        try:
            mapping = self._lookup_font_map(decoder, page_html, pua)
        except Exception as e:
            self.log(f"  字体解码失败（正文将保留 PUA 占位字符）：{e}", "warn")
            return paragraphs, f"字体解码失败：{e}"

        if not mapping:
            self.log("  字体解码未取得映射（正文将保留 PUA 占位字符）", "warn")
            return paragraphs, "字体解码无映射"

        out = [fd.decode_text(p, mapping) for p in paragraphs]
        cov = fd.decode_coverage(paragraphs, mapping)
        # ⚠ 覆盖率过低就**不要还原**（审计 #8，2026-09-22）：
        #   原来这里算完 cov 只写进备注，正文照还原 —— 于是「覆盖 30%」的结果是
        #   **一部分字还原对了、一部分还是 PUA 占位**，两者混在一起，而该章依然
        #   status=ok 被导出：用户拿到手才发现是半乱码。
        #   宁可**不还原**（保留原始字符）+ **明确告警**，也不要产出看起来正常、
        #   实际半截坏掉的数据 —— 这是本项目一贯的「宁缺勿滥」取向。
        if cov < FONT_DECODE_MIN_COVERAGE:
            self.log(f"  字体解码覆盖率仅 {cov:.1%}"
                     f"（< {FONT_DECODE_MIN_COVERAGE:.0%}）→ 放弃还原，"
                     f"正文保留原始字符并在备注里标出", "warn")
            return paragraphs, (f"字体解码覆盖率过低（{cov:.1%}），"
                                f"未还原以避免产出半乱码正文")
        note = f"字体反爬还原 {len(mapping)} 码位（覆盖 {cov:.1%}）"
        return out, note

    def _lookup_font_map(self, decoder, page_html, pua):
        """按页面上 @font-face 声明的字体逐个尝试，直到覆盖本轮全部 PUA。"""
        from . import fontdecode as fd

        ok, why = fd.deps_available()
        if not ok:
            raise fd.FontDecodeError(why)
        if why:
            # ⚠ ok=True 也可能带说明（如「缺 brotli：woff2 读不了」）——
            #   原来这里只判 `not ok`，把那句说明**直接丢了**，等于白写。
            self.log(f"  {why}", "warn")

        urls = fd.font_urls_from_html(page_html or "")
        if not urls:
            raise fd.FontDecodeError("页面里没有 @font-face 字体 URL")

        best = {}
        for u in urls[:4]:
            try:
                data = self._fetch_bytes(u, referer=self.book.url)
            except Exception as e:
                self.log(f"  字体下载失败 {u}：{e}", "warn")
                continue
            m = decoder.map_for_font(data)
            if not m:
                continue
            # 记录覆盖最全的那份
            if len(m) > len(best):
                best = m
            if pua <= set(m):
                return m
        return best
    # ========================================================
    #  章节抓取
    # ========================================================
    def _on_chapter_done(self, ch, store, book):
        """单章收尾：落缓存、打日志、报进度、定期落状态。"""
        with self._lock:
            self._done += 1
            n = self._done
        store.save_chapter(ch)
        if ch.status == STATUS_OK:
            msg = f"[{n}/{self._total}] #{ch.index} {ch.title[:26]} ({ch.char_count}字)"
        else:
            msg = (f"[{n}/{self._total}] #{ch.index} {ch.title[:26]} "
                   f"→ {ch.status}（{ch.note}）")
        self.log(msg, "info" if ch.status == STATUS_OK else "warn")
        self.progress(n, self._total, ch.title)
        if n % STATE_SAVE_INTERVAL == 0:
            store.save_state(book)

    def _body_api_html(self, ch, page_url: str):
        """按 `chapter.body_api` 取正文片段。返回 `(片段, 受保护原因)`。

        未配置 / 取不到 → `("", "")`；**命中「数据源级免费校验」→ `("", 原因)`**，
        调用方据此把该章判为受保护（blocked）且**不导出**。

        URL 模板支持 `{origin}` / `{bid}` / `{cid}` / `{seq}`（seq = 章节序号，从 1 起），
        以及 **`{api_url}`**：正文地址**逐章不同、且无法由 bid/cid 推导**时，
        用 `catalog.json.api_url_field` 从目录接口把每章自己的地址带下来
        （实测仙人掌小说：每章一个 `http://zm.news.so.com/<hash>`）。

        **`require`（v0.8.15 新增）—— 在数据源上判免费，而不是在正文里找特征词**：
        实测仙人掌小说（360）的付费章**不会报错、也不会给付费提示**，
        而是返回一段**戛然截断的试读片段**（642~714 字符，正文里一个付费字样都没有）。
        靠第 4 层「付费墙特征词」**抓不到**，会静默产出不完整章节。
        但同一个响应里带了 `unlock: false` —— 那就直接拿它判：
        配 `require: {"field": "data.unlock"}`（真值判定，见 `require_truthy`），
        `false` 即判受保护。**零请求、零泄漏、且不依赖正文里有没有标记。**
        """
        cfg = self.rule.chapter_cfg.get("body_api") or {}
        tpl = cfg.get("url")
        if not tpl:
            return "", ""
        if "{api_url}" in tpl and not (ch.api_url or ""):
            return "", ""
        target = (tpl.replace("{origin}", origin_of(page_url))
                     .replace("{bid}", self.book.book_id)
                     .replace("{cid}", ch.cid)
                     .replace("{seq}", str(ch.index))
                     .replace("{api_url}", ch.api_url or ""))
        try:
            raw = self._fetch_raw(target, referer=page_url)
        except Exception as e:
            self.log(f"  正文接口请求失败（{e}）——该章按页面 HTML 抽取", "warn")
            return "", ""
        req = cfg.get("require") or {}
        reason = _require_violation(raw, req)
        if reason:
            self.log(f"  正文接口判定该章受保护：{reason}")
            return "", reason
        frag = body_api_fragment(self.rule, raw, self.book.book_id,
                                 ch.index, ch.cid)
        if not frag:
            self.log("  正文接口返回空（字段名或接口可能已变）", "warn")
            return "", ""
        # 降级响应告警（实测塔读）：站点用 base64(cid) 标记「本次应隐藏」的段落；
        # 正常首次响应只有少量水印段（如 7/77），但**同一章高频重复直连**时站点会把
        # 越来越多段落标记为隐藏 → 抽取结果变短。占比过高时明确提示。
        drop_cfg = cfg.get("drop") or {}
        src = drop_cfg.get("equals_base64_of")
        if src in ("cid", "seq", "bid"):
            import base64 as _b64
            key = {"cid": ch.cid, "seq": ch.index,
                   "bid": self.book.book_id}[src]
            want = _b64.b64encode(str(key).encode()).decode()
            total = raw.count("<p")
            hidden = raw.count(f'data-limit="{want}"')
            if total and hidden / total > 0.4:
                self.log(f"  正文接口隐藏段占比 {hidden}/{total}（偏高，疑站点降级响应）"
                         f"—— 建议稍后重抓该章；勿用 --force 反复请求同一章", "warn")
        return frag, ""

    def _fetch_one_chapter(self, ch) -> None:
        """抓取单章（含分页拼装）+ 免费章节校验。"""
        paragraphs, pages = [], []
        url = ch.url
        seen = set()
        title = ""
        first_html = None
        pending = list(getattr(ch, "extra_pages", None) or [])

        for _ in range(MAX_PAGES_PER_CHAPTER):
            if not url or url in seen:
                break
            seen.add(url)
            try:
                html = self._fetch(url, referer=self.book.url,
                                   wait_selector=self._wait_for(
                                       self.rule.chapter_cfg, "chapter"))
            except Exception as e:
                if pages:
                    break                     # 已有内容，续页失败就收尾
                ch.status = STATUS_FAILED
                ch.note = f"请求失败：{e}"
                return
            # 正文接口：章节页是空壳、正文另由接口下发的站点（塔读），
            # 把接口片段并进 html 再走同一套选择器抽取。
            # ⚠ 必须插到 `</body>` **之前**：解析器优先用 lxml，
            #   而 lxml 会**丢弃 `</html>` 之后的内容**（实测踩过：片段整块消失）。
            api_html, api_protected = self._body_api_html(ch, url)
            if api_protected:
                # 数据源层就判明是受保护内容 → 判 blocked，**绝不导出**
                ch.status = STATUS_BLOCKED
                ch.note = f"正文接口判定受保护（{api_protected}）"
                return
            if api_html:
                if "</body>" in html:
                    html = html.replace("</body>", api_html + "\n</body>", 1)
                else:
                    html = html + "\n" + api_html
            if first_html is None:
                first_html = html
            info = parse_chapter_page(self.rule, html, url, ch.cid,
                                     expect_title=ch.title)
            pages.append(url)
            if not title and info["title"]:
                title = info["title"]
                ch.decode_note = info["decode_note"]
            ch.ads_removed += info["ads_removed"]
            if info.get("extract_note"):
                # 正文抽取走了回退路径（段落选择器未命中）——记进备注，便于发现站点改版
                ch.decode_note = (ch.decode_note + " " + info["extract_note"]).strip()
            paragraphs.extend(info["paragraphs"])
            # 目录层给出的续页（`catalog.continuation_title_pattern`）优先于页内链接：
            # 页尾「下一页」既可能是续页也可能是下一回，靠它判断要猜；
            # 而目录页自己标了 `(2)`/`(3)`，是权威信号。
            if pending:
                url = pending.pop(0)
                continue
            if not info["next_url"]:
                break
            url = info["next_url"]

        # 字体反爬：把 PUA 码位还原成真字符（见 fontdecode.py）
        if self.rule.font_decode and paragraphs:
            paragraphs, note = self._font_decode(first_html, paragraphs)
            if note:
                ch.decode_note = (ch.decode_note + " " + note).strip()

        # 目录标题为准；仅当目录没给标题时才回退用页标题
        # （页标题常带「（第N页）」等分页后缀，且可能被站点改写成广告文案）
        if title and not ch.title:
            ch.title = title
        ch.source_pages = pages

        # 第 4 层：付费墙 + 最小字数（含规则自带的站点级特征）
        extra = self.rule.chapter_cfg.get("vip_markers") or []
        protected, status, reason = check_content(paragraphs, extra_markers=extra)
        if not protected and first_html and extra:
            # 站点级信号也可能写在页面而非正文里（如 17K 的 chapter_vip.css）
            hit, why = check_page_markers(first_html, extra)
            if hit:
                protected, status, reason = True, STATUS_BLOCKED, why
        if protected:
            ch.status = STATUS_BLOCKED
            ch.note = reason
            ch.paragraphs = []          # 正文立即丢弃
            return
        if status == STATUS_EMPTY:
            ch.status = STATUS_EMPTY
            ch.note = reason
            ch.paragraphs = []
            return

        ch.status = STATUS_OK
        ch.note = ""
        ch.paragraphs = paragraphs

    def run(self, limit: int = 0, force: bool = False,
            stop_event: "threading.Event | None" = None) -> Book:
        """抓取待抓章节。

        `stop_event`（可选）：**协作式取消**信号。置位后不再提交/等待新章节，
        但**已在跑的章节会自然收尾并落盘**（断点可续）。

        ⚠ 为什么是「协作式」而不是抛异常：原来 GUI 的「停止」是在进度回调里抛
        `KeyboardInterrupt`，而 `with ThreadPoolExecutor(...)` 的 `__exit__` 会
        `shutdown(wait=True)` —— **异常也拦不住它等完所有已提交的 future**。
        实测（审计 #3）：第 3 章点停止 → **40/40 全抓完**，提示语还写着「会在当前章节结束后停下」。
        正确做法是在 `as_completed` 循环里检查信号并 `cancel_futures`，
        以 `wait=False` 关闭线程池。
        """
        if stop_event is None:
            stop_event = threading.Event()
        if self.book is None:
            self.discover()

        book = self.book
        store = self.store
        if force:
            self.log("[续爬] --force：清空既有断点与缓存")
            store.clear()
            raw_done = set()
        else:
            # 断点续爬：先把上一次的状态/正文合并回来，再决定哪些还要抓。
            # 注意 discover() 每次都会产出全新的「全部 pending」章节表，
            # 必须在写盘前合并，否则会覆盖进度（实测踩坑）。
            restored_protected = store.merge_prior_status(book)
            restored_body = store.rehydrate(book)
            raw_done = store.done_cids()
            if restored_protected or restored_body:
                self.log(f"[续爬] 恢复受保护状态 {restored_protected} 章、"
                         f"正文缓存 {restored_body} 章")

        # 只有「状态已完成 且 正文确实在手上（或本身就是受保护）」才算真的完成；
        # 缓存文件被删时正文缺失，必须重抓，否则会导出空章。
        done = {c.cid for c in book.chapters
                if c.cid in raw_done and (c.has_content or c.is_protected)}

        pending = [c for c in book.chapters
                   if not c.is_protected and c.cid not in done]
        if limit and limit > 0:
            pending = pending[:limit]

        skipped_protected = sum(1 for c in book.chapters if c.is_protected)
        if skipped_protected:
            self.log(f"[拦截] {skipped_protected} 章受保护，不请求 / 不导出", "warn")

        if done:
            self.log(f"[续爬] 已有 {len(done)} 章完成，本次跳过")

        # 立即落一次盘，让状态文件与缓存保持一致
        store.save_state(book)

        if not pending:
            self.log("[抓取] 无待抓章节（全部已完成）")
            store.save_state(book)
            return book

        self._total = len(pending)
        self._done = 0
        concurrency = max(1, int(self.config["concurrency"]))
        # 正文的**实际**路由（可被 chapter.fetch_mode 覆盖）——决定能否并发。
        chapter_mode = self.rule.fetch_mode_for("chapter")
        if chapter_mode == "browser" and concurrency > 1:
            # Playwright 同步 API 不能跨线程共享 → 浏览器路由强制单线程
            self.log(f"[抓取] 正文走浏览器路由，并发强制为 1（配置的 {concurrency} 已忽略）")
            concurrency = 1
        route_note = ""
        if chapter_mode != self.rule.fetch_mode:
            route_note = f"，路由=chapter:{chapter_mode}（顶层 {self.rule.fetch_mode}）"
        elif self.rule.fetch_mode == "browser":
            route_note = "，路由=browser"
        self.log(f"[抓取] 待抓 {self._total} 章，并发 {concurrency}，"
                 f"基础间隔 {self.config['delay']}s±{self.config['jitter']}s"
                 + route_note)

        t0 = time.time()
        try:
            if chapter_mode == "browser":
                # 浏览器路由**完全不进线程池**：Playwright 同步对象绑定创建它的线程，
                # 线程池会新建线程 → 报 "Cannot switch to a different thread"。
                # 主线程里顺序抓，语义也更清晰。
                for ch in pending:
                    try:
                        self._fetch_one_chapter(ch)
                    except Exception as e:
                        ch.status = STATUS_FAILED
                        ch.note = f"未捕获异常：{e}"
                    self._on_chapter_done(ch, store, book)
            else:
                # ⚠ 不用 `with ThreadPoolExecutor(...)`：它的 `__exit__` 会
                #   `shutdown(wait=True)` —— 取消信号也拦不住它，必须显式控制。
                pool = ThreadPoolExecutor(max_workers=concurrency)
                try:
                    futures = {pool.submit(self._fetch_one_chapter, c): c
                               for c in pending}
                    for fut in as_completed(futures):
                        if stop_event.is_set():
                            break
                        ch = futures[fut]
                        try:
                            fut.result()
                        except Exception as e:
                            ch.status = STATUS_FAILED
                            ch.note = f"未捕获异常：{e}"
                        self._on_chapter_done(ch, store, book)
                finally:
                    if stop_event.is_set():
                        # 协作式取消：**不等**在跑的章节，直接取消未开始的。
                        # 已完成的章节在 _on_chapter_done 里已落盘 → 断点可续。
                        pool.shutdown(wait=False, cancel_futures=True)
                        done = self._done
                        self.log(f"[抓取] 已停止：完成 {done}/{self._total} 章"
                                 f"（已落盘，重新运行同一命令即可续爬）", "warn")
                    else:
                        pool.shutdown(wait=True)
        finally:
            self.close()

        elapsed = time.time() - t0
        store.save_state(book)
        st = book.stats()
        self.log(f"[完成] 用时 {elapsed:.1f}s ｜ 可导出 {st['exportable']} 章 ｜ "
                 f"受保护 {st['protected']} 章 ｜ 总字数 {st['total_chars']}")
        self.log(f"[限速] {self.limiter.stats}")
        return book
