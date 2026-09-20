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

import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from . import parser
from .constants import DEFAULT_CONFIG
from .freeguard import (assert_site_allowed, check_content, FreeGuardError)
from .http_client import build_headers, http_get, parse_proxy
from .identity_manager import get_identity_manager
from .models import (Book, STATUS_BLOCKED, STATUS_EMPTY, STATUS_FAILED,
                     STATUS_LOCKED, STATUS_OK, STATUS_PENDING)
from .parser import (catalog_links_from_page, catalog_page_urls,
                     collect_catalog_items, normalize_catalog, origin_of,
                     parse_book_info, parse_chapter_page)
from .ratelimit import RateLimiter
from .rules import find_rule, load_rules
from .state import StateStore

MAX_PAGES_PER_CHAPTER = 30       # 单章最大分页数（防死循环）
STATE_SAVE_INTERVAL = 20         # 每抓 N 章落一次状态


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

    # ========================================================
    #  HTTP
    # ========================================================
    def _fetch(self, url: str, referer=None) -> str:
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

    def _fetch_bytes(self, url: str, referer=None) -> bytes:
        """抓二进制资源（字体文件用）。"""
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
        book_html = self._fetch(book_url)

        info = parse_book_info(rule, book_html, book_url, bid)
        book = Book(site=rule.id, book_id=bid, url=book_url, **info)

        # ---- 目录页发现（迭代展开）----
        catalog_pages = self._discover_catalog_pages(rule, book_url, book_html,
                                                     bid, origin)
        self.log(f"[目录] 共 {len(catalog_pages)} 个目录页")

        all_items, all_locked = [], []
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
            lk["status"] = STATUS_LOCKED
            lk["note"] = lk.get("reason", "目录标记为受保护")

        sort_mode = rule.catalog_cfg.get("sort", "cid_numeric_asc")
        dedupe = rule.catalog_cfg.get("dedupe", "keep_first")
        chapters = normalize_catalog(all_items + all_locked, sort_mode, dedupe)

        book.chapters = chapters
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
            return [(book_url, book_html)]

        if mode == "template":
            urls = catalog_page_urls(rule, book_html, bid, origin, book_url)
            out = []
            for u in urls:
                try:
                    out.append((u, self._fetch(u, referer=book_url)))
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
            for u in candidates[:max_pages - len(known)]:
                try:
                    known[u] = self._fetch(u, referer=book_url)
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
        with self._lock:
            if self._font_decoder is None:
                cache_dir = os.path.join(self.config["save_dir"], "fontcache")
                self._font_decoder = fd.FontDecoder(cache_dir, log=self.log)
            decoder = self._font_decoder

        try:
            mapping = self._lookup_font_map(decoder, cfg, page_html, pua)
        except Exception as e:
            self.log(f"  字体解码失败（正文将保留 PUA 占位字符）：{e}", "warn")
            return paragraphs, f"字体解码失败：{e}"

        if not mapping:
            self.log("  字体解码未取得映射（正文将保留 PUA 占位字符）", "warn")
            return paragraphs, "字体解码无映射"

        out = [fd.decode_text(p, mapping) for p in paragraphs]
        cov = fd.decode_coverage(paragraphs, mapping)
        note = f"字体反爬还原 {len(mapping)} 码位（覆盖 {cov:.1%}）"
        return out, note

    def _lookup_font_map(self, decoder, cfg, page_html, pua):
        """按页面上 @font-face 声明的字体逐个尝试，直到覆盖本轮全部 PUA。"""
        from . import fontdecode as fd

        ok, why = fd.deps_available()
        if not ok:
            raise fd.FontDecodeError(why)

        urls = fd.font_urls_from_html(page_html or "")
        if not urls:
            raise fd.FontDecodeError("页面里没有 @font-face 字体 URL")

        auto_build = bool(cfg.get("auto_build", True))
        best = {}
        for u in urls[:4]:
            try:
                data = self._fetch_bytes(u, referer=self.book.url)
            except Exception as e:
                self.log(f"  字体下载失败 {u}：{e}", "warn")
                continue
            m = decoder.map_for_font(data, build_if_missing=auto_build,
                                     downloader=lambda url: self._fetch_bytes(url))
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
    def _fetch_one_chapter(self, ch) -> None:
        """抓取单章（含分页拼装）+ 免费章节校验。"""
        paragraphs, pages = [], []
        url = ch.url
        seen = set()
        title = ""
        first_html = None

        for _ in range(MAX_PAGES_PER_CHAPTER):
            if not url or url in seen:
                break
            seen.add(url)
            try:
                html = self._fetch(url, referer=self.book.url)
            except Exception as e:
                if pages:
                    break                     # 已有内容，续页失败就收尾
                ch.status = STATUS_FAILED
                ch.note = f"请求失败：{e}"
                return
            if first_html is None:
                first_html = html
            info = parse_chapter_page(self.rule, html, url, ch.cid)
            pages.append(url)
            if not title and info["title"]:
                title = info["title"]
                ch.decode_note = info["decode_note"]
            ch.ads_removed += info["ads_removed"]
            paragraphs.extend(info["paragraphs"])
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

        # 第 4 层：付费墙 + 最小字数
        protected, status, reason = check_content(paragraphs)
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

    def run(self, limit: int = 0, force: bool = False) -> Book:
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
        self.log(f"[抓取] 待抓 {self._total} 章，并发 {concurrency}，"
                 f"基础间隔 {self.config['delay']}s±{self.config['jitter']}s")

        t0 = time.time()
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            futures = {pool.submit(self._fetch_one_chapter, c): c for c in pending}
            for fut in as_completed(futures):
                ch = futures[fut]
                try:
                    fut.result()
                except Exception as e:
                    ch.status = STATUS_FAILED
                    ch.note = f"未捕获异常：{e}"
                with self._lock:
                    self._done += 1
                    n = self._done
                store.save_chapter(ch)
                if ch.status == STATUS_OK:
                    msg = f"[{n}/{self._total}] #{ch.index} {ch.title[:26]} ({ch.char_count}字)"
                else:
                    msg = f"[{n}/{self._total}] #{ch.index} {ch.title[:26]} → {ch.status}（{ch.note}）"
                self.log(msg, "info" if ch.status == STATUS_OK else "warn")
                self.progress(n, self._total, ch.title)
                if n % STATE_SAVE_INTERVAL == 0:
                    store.save_state(book)

        elapsed = time.time() - t0
        store.save_state(book)
        st = book.stats()
        self.log(f"[完成] 用时 {elapsed:.1f}s ｜ 可导出 {st['exportable']} 章 ｜ "
                 f"受保护 {st['protected']} 章 ｜ 总字数 {st['total_chars']}")
        self.log(f"[限速] {self.limiter.stats}")
        return book
