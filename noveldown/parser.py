#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
解析器：书籍信息 / 目录 / 正文。

设计要点
--------
1. **预解码先行**：解析前先跑 predecode，把 JS 内联 base64 还原成真实 HTML。
2. **目录一律「先收集、再去重、最后按 cid 升序归一化」**——
   这是应对「最新章节倒序回显」「CSS 隐藏列表项」「多页目录」三类反爬的统一解法。
   实测（2026-09-20）：
     shuquge.com 目录页 1594 项含倒序回显 → 归一化后 1441 章
     bqgbe.cc    两页目录共 199 项（含重复与乱序）→ 归一化后 190 章
     biqu520.net 目录用 onclick 无 href，27 页 → 归一化后 2652 章
3. 正文按 strip_selectors 剔除导航/标题/脚本后再取段落，并过滤广告行。
4. 目录项命中 VIP 标记 → 标记为只读「受保护」，由上层跳过请求（免费章节约束）。
"""

import copy
import re
from urllib.parse import urljoin, urlparse

import soupsieve as sv
from bs4 import BeautifulSoup

from .freeguard import is_vip_item
from .models import Chapter, STATUS_LOCKED, STATUS_PENDING
from .predecode import predecode

# ------------------------------------------------------------
#  基础工具
# ------------------------------------------------------------

_AD_LINE_RE = re.compile(
    r"^(?:https?://)?(?:www\.)?[\w.-]+\.(?:com|net|cc|org|info|la|me|top|xyz)(?:/\S*)?$",
    re.I,
)


def origin_of(url: str) -> str:
    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}"


def make_soup(html: str) -> BeautifulSoup:
    """构造 BeautifulSoup；优先 lxml，缺失回退 html.parser。"""
    try:
        return BeautifulSoup(html, "lxml")
    except Exception:
        return BeautifulSoup(html, "html.parser")


def select_first(soup, selectors):
    """按候选选择器数组取第一个命中的元素。"""
    if isinstance(selectors, str):
        selectors = [selectors]
    for sel in selectors or []:
        el = select_one_safe(soup, sel)
        if el is not None:
            return el
    return None


def select_one_safe(soup, sel):
    """容错 select_one：选择器非法/不支持时返回 None 而不抛。"""
    try:
        return soup.select_one(sel)
    except Exception:
        return None


def el_value(el):
    """取元素值：meta 取 content 属性，其余取文本。"""
    if el is None:
        return ""
    val = el.get("content")
    if val:
        return val.strip()
    return el.get_text(strip=True)


def _norm_space(s: str) -> str:
    """把中文全角空格 / NBSP 视作普通空白并压缩。"""
    if not s:
        return ""
    s = s.replace("\u3000", " ").replace("\xa0", " ").replace("\t", " ")
    s = re.sub(r"[ ]{2,}", " ", s)
    return s.strip()


# 分页章节的页标题后缀，如「（第1页）」「(第2页)」「_第3页」
_PAGE_SUFFIX_RE = re.compile(r"[（(]\s*第\s*\d+\s*页\s*[)）]\s*$|\s*_\s*第\s*\d+\s*页\s*$")


def clean_page_title(s: str) -> str:
    """去掉正文页标题里的分页后缀。

    bqgbe / biqu520 把一章拆成多页时，页标题会变成「第一章（第2页）」，
    直接用作章节标题会污染目录，所以统一剥离。
    """
    return _PAGE_SUFFIX_RE.sub("", _norm_space(s)).strip()


# ------------------------------------------------------------
#  书籍信息
# ------------------------------------------------------------

def parse_book_info(rule, html: str, url: str, bid: str) -> dict:
    """解析书籍元信息（标题/作者/简介/封面/状态）。

    选择器特殊值：
      `@title` —— 取文档 `<title>` 的文本。SPA 站点（七猫）的书籍页里书名
      常只出现在 `<title>` 里，配合 `book.title_pattern` 正则清洗即可
      （如 `^(.*?)免费阅读` 去掉站点后缀）。
    """
    soup = make_soup(html)
    cfg = rule.book_cfg

    def _pick(selectors):
        if isinstance(selectors, str):
            selectors = [selectors]
        for sel in selectors or []:
            if sel == "@title":
                if soup.title and soup.title.string:
                    return soup.title.string.strip()
                continue
            el = select_one_safe(soup, sel)
            if el is not None:
                v = el_value(el)
                if v:
                    return v
        return ""

    title = _pick(cfg.get("title"))
    pat = cfg.get("title_pattern")
    if pat and title:
        m = re.search(pat, title, re.S)
        if m:
            title = (m.group(1) if m.groups() else m.group(0)).strip()

    author = _pick(cfg.get("author"))
    # `author_pattern`：作者常与书名挤在同一行（书海 `.book-info-bookname` =
    # 「神农医婿 作者: 方长」），用正则取出作者，避免把书名一起带出来。
    apat = cfg.get("author_pattern")
    if apat and author:
        m = re.search(apat, author, re.S)
        if m:
            author = (m.group(1) if m.groups() else m.group(0)).strip()

    return {
        "title": title,
        "author": author,
        "intro": _pick(cfg.get("intro")),
        "cover": _pick(cfg.get("cover")),
        "status": _pick(cfg.get("status")),
    }


# ------------------------------------------------------------
#  目录：页列表
# ------------------------------------------------------------

def catalog_page_urls(rule, source_html: str, bid: str, origin: str,
                      source_url: str) -> list:
    """根据 catalog.pages 配置返回目录页 URL 列表。"""
    pages_cfg = rule.catalog_cfg.get("pages") or {}
    mode = pages_cfg.get("mode", "single")

    if mode == "single":
        tpl = pages_cfg.get("url") or source_url
        return [tpl.replace("{origin}", origin).replace("{bid}", bid)]

    if mode == "select":
        soup = make_soup(source_html)
        sel = pages_cfg.get("option_selector", "select option")
        attr = pages_cfg.get("value_attribute", "value")
        keep = pages_cfg.get("keep_pattern")
        keep = keep.replace("{bid}", bid) if keep else None
        urls, seen = [], set()
        for opt in soup.select(sel):
            val = (opt.get(attr) or "").strip()
            if not val:
                continue
            if keep and keep not in val:
                continue
            full = urljoin(source_url, val)
            if full not in seen:
                seen.add(full)
                urls.append(full)
        return urls

    if mode == "template":
        tpl = pages_cfg.get("url", "")
        out = []
        for n in range(int(pages_cfg.get("start", 1)),
                       int(pages_cfg.get("end", 1)) + 1):
            out.append(tpl.replace("{origin}", origin)
                          .replace("{bid}", bid)
                          .replace("{page}", str(n)))
        return out

    raise ValueError(f"未知的 catalog.pages.mode: {mode}")


# ------------------------------------------------------------
#  目录：章节项
# ------------------------------------------------------------

def _resolve_link_el(el):
    """章节项可能是**容器**（如书海 `div.chapter-item`），返回真正带链接的元素。

    自身带 href/onclick 就返回自身；否则向下找第一个 `<a>`。
    找不到时返回自身（交给调用方按缺链接处理）。
    """
    if el.get("href") or el.get("onclick"):
        return el
    if getattr(el, "select_one", None):
        inner = el.select_one("a[href], a[onclick]") or el.select_one("a")
        if inner is not None:
            return inner
    return el


def _extract_cid(rule, el, href: str, bid: str, origin: str, page_url: str):
    """从章节项元素中提取 cid 与最终 URL。

    id_from.mode:
        href    —— 从 <a href> 正则提取（可配合 url_template 重建）
        onclick —— 从 onclick 属性正则提取（biqu520 这类无 href 的站）

    url_template 可用 {origin} / {bid} / {cid} 占位符；
    未配置时用 urljoin(page_url, href) 解析相对链接。

    **容器项**：`item_selector` 也可以选中**容器**（如书海
    `<div class="chapter-item"><a href="/read/1/41.html">…</a><span class="vip"></span></div>`）。
    此时 href / onclick 在内嵌 `<a>` 上，且**标题在容器文本里**——
    实测该书 33% 的 `<a>` 文本为空（标记错位），只选 `<a>` 会丢掉三分之一标题。
    """
    id_cfg = rule.catalog_cfg.get("id_from") or {}
    mode = id_cfg.get("mode", "href")
    pattern = id_cfg.get("pattern", "")
    tpl = rule.catalog_cfg.get("url_template")

    # 容器项：自身没有 href/onclick 时，向下找第一个 <a>
    link_el = _resolve_link_el(el)
    if link_el is not el:
        href = link_el.get("href") or href

    if mode == "onclick":
        raw = link_el.get("onclick") or ""
        m = re.search(pattern, raw) if pattern else None
        if not m:
            return None, ""
        cid = m.group("cid")
    else:
        if not href:
            return None, ""
        m = re.search(pattern, href) if pattern else None
        if not m:
            return None, ""
        cid = m.group("cid")

    if tpl:
        url = (tpl.replace("{origin}", origin)
                  .replace("{bid}", bid)
                  .replace("{cid}", cid))
    else:
        url = urljoin(page_url, href) if href else ""
    return cid, url


def collect_catalog_items(rule, html: str, page_url: str, bid: str):
    """从单个目录页收集章节项。

    Returns: (items, locked)
        items  = [{"cid", "title", "url", "volume"}]
        locked = [{"cid", "title", "url", "reason"}]   # 命中 VIP 标记，不抓
    """
    soup = make_soup(html)
    item_sel = rule.catalog_cfg["item_selector"]
    vol_sel = rule.catalog_cfg.get("volume_selector")
    origin = origin_of(page_url)

    items, locked = [], []
    state = {"vol": ""}

    def _handle(el):
        href = el.get("href") or ""
        cid, url = _extract_cid(rule, el, href, bid, origin, page_url)
        if not cid:
            return
        title = _norm_space(el.get_text())
        cls = " ".join(el.get("class") or [])
        parent_cls = ""
        if el.parent is not None and getattr(el.parent, "get", None):
            parent_cls = " ".join(el.parent.get("class") or [])
        protected, reason = is_vip_item(f"{cls} {parent_cls}", title)
        # VIP 标记在目录项的**子元素**上时的显式选择器（书海：
        # <div class="chapter-item"><a …>…</a><span class="vip"></span></div>）。
        # 该 span 既不在项自身 class、也不在父级 class 上，故需单独指定。
        # 检查范围 = 项自身 + **链接元素的父级**（VIP 标记与链接同级）。
        # ⚠ 不能取「项自身的父级」：那是整个目录容器，会匹配到别的条的 vip span，
        #   导致整本书被误锁（实测踩过：645 章全被判 protected）。
        if not protected:
            vc = rule.catalog_cfg.get("vip_child_selector")
            if vc:
                link_el = _resolve_link_el(el)
                for scope in (el, getattr(link_el, "parent", None)):
                    if scope is None or not getattr(scope, "select_one", None):
                        continue
                    try:
                        if sv.match(vc, scope) or scope.select_one(vc) is not None:
                            protected = True
                            reason = f"目录项子元素命中 '{vc}'"
                            break
                    except Exception:
                        continue
        rec = {"cid": cid, "title": title, "url": url, "volume": state["vol"]}
        # 分段名判 VIP：目录按「免费章节 / VIP章节」**分段**标注、逐章无标记的站点
        # （实测塔读：<h2><span>免费章节<i>/2416章</i></span></h2> 下挂全部章节）。
        # 需要配 `volume_selector`（如 "h2"）才能跟踪到当前分段名。
        if not protected:
            vvm = rule.catalog_cfg.get("vip_volume_markers")
            if vvm and state["vol"]:
                for m in vvm:
                    if m and m.lower() in state["vol"].lower():
                        protected = True
                        reason = f"所属分段「{state['vol']}」命中 '{m}'"
                        break
        if protected:
            locked.append({**rec, "reason": reason})
        else:
            items.append(rec)

    if vol_sel:
        # 按文档顺序线性扫描，同时跟踪当前卷名
        for el in soup.descendants:
            if not getattr(el, "name", None):
                continue
            try:
                if sv.match(vol_sel, el):
                    state["vol"] = _norm_space(el.get_text())
                    continue
                if sv.match(item_sel, el):
                    _handle(el)
            except Exception:
                continue
    else:
        try:
            for el in soup.select(item_sel):
                _handle(el)
        except Exception:
            pass

    return items, locked



def catalog_links_from_page(rule, html: str, page_url: str, bid: str,
                            origin: str) -> list:
    """从某个目录页里发现**其他目录页**的 URL。

    两类来源：
      1) <select> 的 option（bqgbe / biqu520 用下拉框给出全部目录分页）
      2) 页面里形如 /txt/{bid}/ml2.html 的「查看更多章节」链接

    由 engine 迭代展开，直到不再出现新的目录页（上限见 pages.max_pages）。
    """
    pages_cfg = rule.catalog_cfg.get("pages") or {}
    mode = pages_cfg.get("mode", "auto")
    soup = make_soup(html)
    found, seen = [], set()

    def _add(u):
        if u and u not in seen:
            seen.add(u)
            found.append(u)

    if mode in ("auto", "select"):
        sel = pages_cfg.get("option_selector", "select option")
        attr = pages_cfg.get("value_attribute", "value")
        keep = pages_cfg.get("keep_pattern")
        keep = keep.replace("{bid}", bid) if keep else None
        try:
            for opt in soup.select(sel):
                val = (opt.get(attr) or "").strip()
                if not val or val.startswith(("javascript:", "#")):
                    continue
                if keep and keep not in val:
                    continue
                _add(urljoin(page_url, val))
        except Exception:
            pass

    if mode in ("auto", "links"):
        lp = pages_cfg.get("link_pattern")
        if lp:
            lp = lp.replace("{bid}", bid)
            for a in soup.select("a[href]"):
                href = (a.get("href") or "").strip()
                # 跳过伪协议——bqgbe 的「加入书架」是
                # javascript:addbookcase('https://.../ml2.html','445')，
                # 其中的 URL 只是当前页书签参数，不是导航目标。
                if not href or href.startswith(("javascript:", "#", "mailto:",
                                                "tel:", "data:")):
                    continue
                if re.search(lp, href):
                    _add(urljoin(page_url, href))

    return found


def normalize_catalog(items, sort_mode: str = "cid_numeric_asc",
                      dedupe: str = "keep_first"):
    """去重 + 排序 + 编号。

    这是核心归一化步骤：无论目录页给的是「倒序最新章节回显」「CSS 隐藏的乱序块」
    还是「多页拼接」，最终都产出唯一的、按阅读顺序排列的章节列表。

    sort_mode
        `cid_numeric_asc`（默认）按 cid 数字升序 —— 适用于章节 ID 即顺序号的站点
        （shuquge / bqgbe / biqu520 都是）。
        `document_order` 保持页面自身的顺序 —— 适用于 ID 是雪花 ID、
        与阅读顺序无稳定关系的站点（如番茄小说）。
        `cid_numeric_desc` 逆序（罕用）。

    dedupe
        `keep_first`（默认）/ `keep_last`。
        番茄小说把「最近更新：第966章」放在**列表头部**（与末尾的正文条目同 cid），
        此时需要 `document_order` + `keep_last`：丢掉头部的回显，保住末尾那条
        条目自己的位置与干净标题。（实测踩过：用 cid 升序排序会把回显的
        脏标题「最近更新：第966章 终章（完）」留到最后一章上。）

    items 元素可带 "status" / "note" 字段（用于把受保护的 VIP 章节一并纳入编号，
    使其在章节序列中占位但永不被抓取）。
    """
    if dedupe == "keep_last":
        by_cid = {}
        for it in items:
            by_cid[it["cid"]] = it          # 后出现者覆盖 → 位置也取后者
        picked = []
        seen = set()
        for it in items:
            cid = it["cid"]
            if by_cid.get(cid) is it:
                picked.append(it)
    else:
        by_cid, picked, seen = {}, [], set()
        for it in items:
            if it["cid"] not in by_cid:
                by_cid[it["cid"]] = it
                picked.append(it)

    def _num(cid):
        m = re.search(r"(\d+)", cid or "")
        return int(m.group(1)) if m else 0

    if sort_mode == "document_order":
        ordered = picked
    elif sort_mode == "cid_numeric_desc":
        ordered = sorted(by_cid.values(), key=lambda x: _num(x["cid"]), reverse=True)
    else:  # cid_numeric_asc（默认）
        ordered = sorted(by_cid.values(), key=lambda x: _num(x["cid"]))

    chapters = []
    for i, it in enumerate(ordered, 1):
        chapters.append(Chapter(
            index=i, title=it["title"], url=it["url"], cid=it["cid"],
            volume=it.get("volume", ""),
            status=it.get("status", STATUS_PENDING),
            note=it.get("note", "")))
    return chapters


# ------------------------------------------------------------
#  目录：JSON 接口形态
# ------------------------------------------------------------

def _dig(obj, path: str):
    """按 `a.b.c` 或 `a.0.b` 取嵌套值，缺失返回 None。"""
    cur = obj
    for part in (path or "").split("."):
        if part == "":
            continue
        if isinstance(cur, list):
            try:
                cur = cur[int(part)]
            except (ValueError, IndexError):
                return None
        elif isinstance(cur, dict):
            if part not in cur:
                return None
            cur = cur[part]
        else:
            return None
    return cur


def collect_json_catalog(rule, text: str, bid: str, origin: str):
    """从 JSON 接口响应里收集章节。

    为什么要支持这种形态：不少站点的目录**只走 JSON 接口**
    （起点 `ajax/book/category`、七猫 `qimaoapi/api/book/chapter-list`…），
    静态 HTML 里根本没有章节链接。参考项目（backupqidian、_qtref 里的 Scrapy 爬虫）
    走的都是这条路。

    **额外好处**：这类接口常带**逐章 VIP 字段**（如七猫的 `is_vip`、起点的 `vip`），
    比 HTML class 标记更可靠 —— 第 3 层据此就能判定，连请求都不发。

    Returns: (items, locked)
    """
    import json as _json

    cfg = rule.catalog_cfg.get("json") or {}
    try:
        data = _json.loads(text)
    except (ValueError, TypeError) as e:
        raise ValueError(f"目录接口返回的不是 JSON：{e}；前 80 字：{(text or '')[:80]!r}")

    items = _dig(data, cfg.get("items_path", "data.chapters"))
    # 嵌套展开：起点把章节放在 data.vs[].cs[]（卷 → 章）里
    ff = cfg.get("flatten_field")
    if ff and isinstance(items, list):
        flat = []
        for grp in items:
            if isinstance(grp, dict):
                subs = grp.get(ff)
                if isinstance(subs, list):
                    flat.extend(subs)
                else:
                    flat.append(grp)
            else:
                flat.append(grp)
        items = flat
    if not isinstance(items, list):
        raise ValueError(
            f"目录接口的 items_path={cfg.get('items_path')!r} 取不到列表；"
            f"顶层键：{list(data.keys()) if isinstance(data, dict) else type(data).__name__}")

    cid_f = cfg.get("cid_field", "id")
    title_f = cfg.get("title_field", "title")
    vip_f = cfg.get("vip_field")
    truthy = {str(x).lower() for x in (cfg.get("vip_truthy") or ["1", "true", "yes"])}
    tpl = rule.catalog_cfg.get("url_template") or ""

    out, locked = [], []
    for it in items:
        if not isinstance(it, dict):
            continue
        cid = str(it.get(cid_f, "")).strip()
        if not cid:
            continue
        title = _norm_space(str(it.get(title_f, "")))
        url = (tpl.replace("{origin}", origin).replace("{bid}", bid).replace("{cid}", cid))
        rec = {"cid": cid, "title": title, "url": url, "volume": ""}
        if vip_f:
            val = it.get(vip_f)
            if val is not None and str(val).lower() in truthy:
                locked.append({**rec, "status": STATUS_LOCKED,
                               "note": f"目录接口字段 {vip_f}={val} 标记为受保护",
                               "reason": f"目录接口字段 {vip_f}={val}"})
                continue
        out.append(rec)
    return out, locked


# ------------------------------------------------------------
#  正文
# ------------------------------------------------------------

def _is_ad_line(line: str, ad_patterns) -> bool:
    for p in ad_patterns or []:
        if p and p in line:
            return True
    if _AD_LINE_RE.match(line):
        return True
    return False


def extract_paragraphs(container, ad_patterns):
    """从正文容器提取段落。

    坑：正文容器常把多个段落用 <br/> 分隔在同一文本流里，
    必须先把 <br> 换成换行再取文本，否则整章会挤成一段。
    """
    for br in container.find_all("br"):
        br.replace_with("\n")
    # 块级元素之间补换行，避免 <p> 段落被粘连
    text = container.get_text("\n")

    paragraphs, ads = [], 0
    for raw in text.split("\n"):
        line = _norm_space(raw)
        if not line:
            continue
        if _is_ad_line(line, ad_patterns):
            ads += 1
            continue
        paragraphs.append(line)
    return paragraphs, ads


def parse_chapter_page(rule, html: str, url: str, current_cid: str):
    """解析单个正文页。

    Returns: {
        "title", "paragraphs", "ads_removed", "decode_note", "extract_note", "next_url"
    }

    `extract_note` 非空表示正文抽取**走了回退路径**（段落选择器未命中）——
    调用方应把它并进章节备注，便于发现站点改版。
    """
    cfg = rule.chapter_cfg
    html2, dstats = predecode(html, enabled=rule.predecode)
    soup = make_soup(html2)

    title = ""
    t_el = select_first(soup, cfg.get("title_selector")) if cfg.get("title_selector") else None
    if t_el is not None:
        title = clean_page_title(t_el.get_text())

    container = select_first(soup, cfg.get("content_selectors") or cfg.get("content_selector"))
    paragraphs, ads, extract_note = [], 0, ""
    if container is not None:
        # 在**深拷贝**上剔除元素。
        # 坑（实测踩过）：直接 decompose 原容器会把 div.read_btn 也删掉，
        # 而续页判定恰恰要读它里面的「下一章」链接，导致分页章节只抓到第 1 页。
        work = copy.copy(container)
        for sel in cfg.get("strip_selectors") or []:
            for el in work.select(sel):
                el.decompose()
        # `paragraph_selector`：按**段落元素**逐个取文本，而不是把容器整块文本按换行切。
        # 用于「正文段是 <span>，而 <p> 里还混着段评数/点赞数等附加节点」的站点
        # （实测起点：<p><span class="content-text">痛！</span><span class="review">…999…</span></p>，
        #  整块取文本会得到「痛！999」）。
        para_sel = cfg.get("paragraph_selector")
        if para_sel:
            paragraphs, ads = [], 0
            for node in work.select(para_sel):
                line = _norm_space(node.get_text(" "))
                if not line:
                    continue
                if _is_ad_line(line, cfg.get("ad_patterns")):
                    ads += 1
                    continue
                paragraphs.append(line)
        # 回退：段落选择器**一个都没命中**（站点改版 / 换了渲染变体）时，
        # 退回「容器整体切分」——否则整章会**静默变空**（比多几个噪声字严重得多）。
        # 回退结果同样干净：strip_selectors 已在上面剔掉段评数等附加节点。
        if not paragraphs:
            paragraphs, ads = extract_paragraphs(work, cfg.get("ad_patterns"))
            if para_sel:
                extract_note = f"段落选择器「{para_sel}」未命中，已回退为容器整体切分"

    # 续页判定
    next_url = None
    np_cfg = cfg.get("next_page") or {}
    if np_cfg:
        origin = origin_of(url)
        for a in soup.select(np_cfg.get("selector", "a")):
            label = _norm_space(a.get_text())
            if np_cfg.get("text_contains") and np_cfg["text_contains"] not in label:
                continue
            href = a.get("href") or ""
            if not href or href.startswith(("javascript:", "#")):
                continue
            full = urljoin(url, href)
            if origin_of(full) != origin:
                continue
            pat = np_cfg.get("href_pattern", "")
            m = re.search(pat, full) if pat else None
            if not m:
                continue
            if np_cfg.get("continue_when") == "same_base_id":
                if m.group("cid") != current_cid:
                    break
            next_url = full
            break

    return {
        "title": title,
        "paragraphs": paragraphs,
        "ads_removed": ads,
        "decode_note": (f"base64×{dstats['payloads']}" if dstats.get("payloads") else ""),
        "extract_note": extract_note,
        "next_url": next_url,
    }


# ------------------------------------------------------------
#  正文接口（chapter.body_api）
# ------------------------------------------------------------

BODY_API_WRAP_CLASS = "nd-api-body"


def _drop_value(drop_cfg, bid, seq, cid):
    """算出「要剔除的元素」其属性应等于的值。

    `equals_base64_of` 支持 `bid` / `seq` / `cid` —— 站点常用 base64(章节id)
    作为水印段的标记（实测塔读：`data-limit="MTAwODEyNTg3"` = base64("100812587")）。
    """
    src = drop_cfg.get("equals_base64_of")
    if not src:
        return drop_cfg.get("equals")
    val = {"bid": bid, "seq": seq, "cid": cid}.get(src)
    if val is None:
        return None
    import base64
    return base64.b64encode(str(val).encode("utf-8")).decode("ascii")


def body_api_fragment(rule, text: str, bid: str, seq, cid: str) -> str:
    """把「正文接口」的响应转成可供后续选择器使用的 HTML 片段。

    有些站点的章节页是**空壳**，正文由 JS 调接口后填入
    （实测塔读：`#artContent` 为空，正文在 `/getPartContentByCodeTable/{bid}/{seq}`
    返回的 `data.content` 里）。

    本函数：
      1. 解析 JSON，按 `content_field` 取出正文 HTML；
      2. 按 `drop` 规则**剔除水印段**（见 `_drop_value`）；
      3. 包一层 `<div class="nd-api-body">`，使 `content_selector` 有容器可选。

    返回 "" 表示取不到（调用方据此跳过，不影响主流程）。
    """
    import json as _json

    cfg = rule.chapter_cfg.get("body_api") or {}
    if not text:
        return ""
    try:
        data = _json.loads(text)
    except (ValueError, TypeError):
        return ""
    frag = _dig(data, cfg.get("content_field", "data.content"))
    if not isinstance(frag, str) or not frag.strip():
        return ""

    soup = BeautifulSoup(f"<div class='{BODY_API_WRAP_CLASS}'>{frag}</div>",
                         "html.parser")
    drop = cfg.get("drop") or {}
    if drop and drop.get("selector"):
        want = _drop_value(drop, bid, seq, cid)
        attr = drop.get("attr")
        for el in soup.select(drop["selector"]):
            # 已被前一次 decompose 连带删掉的元素，attr 会失效（实测踩过
            # AttributeError: 'NoneType' object has no attribute 'get'）→ 跳过。
            if getattr(el, "attrs", None) is None:
                continue
            if want is None or (attr and (el.get(attr) or "") == want):
                el.decompose()
    return str(soup)
