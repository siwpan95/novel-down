#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""批量扫候选镜像站：先判存活，再判「能不能抓」。

## 为什么要两段

书源库给出上万个域名，**绝大多数已死**（这类站死亡率极高）。
若对每个域都做完整的「书籍页 + 目录 + 正文」探测，代价是每站 3~4 个请求，
上万个域就是几万请求 —— 又慢又没礼貌。
所以分两段：

  * `--phase live`（便宜，每站 1 个请求）：只判存活，输出 `.sources/live.jsonl`
  * `--phase deep`（贵，每站 ≤4 个请求）：只对存活站做结构探测，输出 `.sources/deep.jsonl`

## deep 段判什么

对每个存活站，尽量**机械化**地拿到「写规则所需的全部事实」，
这样后面生成规则几乎不用再人工看页面：

1. 打开首页 → **找书籍详情页链接**（按常见形态：`/book/123` `/txt/123/` `/123/456/` …）
2. 打开书籍页 → 数**章节链接数**（≥20 视为目录页），并定位**目录容器**（含最多章节链接的那个节点的 id/class）
3. 取第一个章节链接 → 用 `parser.guess_content_container()` 自动识别**正文容器** + 汉字量
4. 记录 → `.sources/deep.jsonl`

⚠ 本工具**不下载任何书源的规则体**，只探测站点自身的 HTML 结构。

## 用法

    python tools/scan_mirrors.py --phase live --limit 0        # 全部存活扫描
    python tools/scan_mirrors.py --phase deep --limit 500      # 只深探前 500 个存活站
"""

import argparse
import json
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin, urlparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from noveldown.http_client import http_get  # noqa: E402
from noveldown.parser import guess_content_container, make_soup  # noqa: E402

# 已知正版站：不纳入镜像候选（正版池另走一路，见 docs/NEW_SITES_PLAN.md）
OFFICIAL = {
    "qidian.com", "17k.com", "qimao.com", "zongheng.com", "fanqienovel.com",
    "shuhai.com", "tadu.com", "ciyuanji.com", "faloo.com", "linovelib.com",
    "ciweimao.com", "xrzww.com", "youdubook.com", "hanwujinian.com",
    "jjwxc.net", "readnovel.com", "hongxiu.com", "motie.com", "ciweimao.cn",
    "zhangyue.com", "ireader.com", "qq.com", "aliyun.com", "baidu.com",
}
# 明显非「小说正文站」的来源（论坛/漫画/有声/聚合），不做正文抓取
NON_NOVEL = ("bbs", "forum", "manhua", "manga", "comic", "dmzj", "acg",
             "audio", "tingshu", "yousheng", "video", "zhihu", "weibo",
             "douban", "search", "nav", "daohang", "app", "api.", "cdn.")
# 内容不宜纳入本项目的站点（成人向）。⚠ 这**只能是启发式的**：
# 判据取自「书源名 + 域名 + 页面标题」，必然有漏网与误伤。
# 所以本工具只把命中的**打标并排除**，同时把命中数报出来（而不是静默丢），
# 让人能看到过滤到底起作用没有、以及有没有误伤。
ADULT_WORDS = ("成人", "情色", "色情", "禁漫", "里番", "工口", "肉文", "高h",
               "18禁", "18+", "激情", "艳情", "情欲", "海棠", "书吧",
               "h动漫", "h漫", "无码", "成人动漫", "a片", "自慰",
               "alicesw", "sis001", "sexinsex", "cool18", "18hdm", "haitang",
               "po18", "popo18", "18av", "missav")

# 章节页形态：`<前缀>/<bookid>/<cid>.html`。
# ⚠ `bookid` **未必是数字**：实测 min-yuan.com 用**字母编码**（`/txt/vpnm/1.html`），
# 只认 `\d+` 会把整站漏掉。所以 bookid 放宽到「字母数字下划线短横」，
# `cid` 仍是数字（章节号）。
CHAPTER_HREF_RE = re.compile(r"^(?P<prefix>.*/)(?P<bid>[A-Za-z0-9_-]{2,})/"
                             r"(?P<cid>\d+)(?:_\d+)?\.html?$", re.I)
BOOK_PATH_RES = [
    re.compile(r"/book/\d+"),
    re.compile(r"/txt/\d+"),
    re.compile(r"/novel/\d+"),
    re.compile(r"/read/\d+"),
    re.compile(r"/info/\d+"),
    re.compile(r"/\d+/\d+/?"),           # 速读谷式 /{bid}/{cid}.html
    re.compile(r"/book/\d+\.html?"),
    re.compile(r"/list/\d+"),
    re.compile(r"/biquge/\d+"),
    re.compile(r"/xs/\d+"),
    re.compile(r"/html/\d+"),
    re.compile(r"/\d+_\d+/?$"),
]
CHAP_RE = re.compile(r"/(?:chapter|read|book|txt)?/?\d+(_\d+)?\.html?$", re.I)

# ---------------------------------------------------------------
#  模板候选选择器
# ---------------------------------------------------------------
# 深探**不猜**：逐个候选实测，命中哪个就记哪个。
# 这些候选来自本项目已接入的 7 条免费镜像规则 + 常见笔趣阁变体。
# 「镜像铺开」的正确做法不是「看到同模板就跳过」，而是
# **逐个域名实测通过后才写进 match** —— 源越多，个体抽风时整体越可用。
CATALOG_CANDIDATES = [
    "div.listmain dl dd a", "ul.section-list li a", "div#list dd a",
    "div#list a[href$='.html']", "div.dir a[href$='.html']",
    "#chapterlist a", ".listmain a", "dl dd a", "div#chapterlist a",
    "ul.chapter-list a", "div.book_list a", "#booktxt a", "#list a",
    "div.chapterlist a", "ul#chapter-list a",
]
CONTENT_CANDIDATES = [
    "div#chaptercontent", "div#content", "#content", ".Readarea",
    "div.content", "div#nr1", "#nr", "#htmlContent", "div.showtxt",
    "div.con", "div.word_read", "#TextContent", "div#booktext",
    "div#booktxt", "div.txtnav + div", "article",
]
MIN_CHAPTERS = 20      # 目录页至少要这么多章节链接，才当"目录可用"
MIN_CJK = 300          # 正文至少这么多汉字，才当"正文可取"

def _is_official(dom: str) -> bool:
    """正版站判定要按**后缀**：`m.qidian.com` / `www.qidian.com` 都属 qidian.com。"""
    return any(dom == o or dom.endswith("." + o) for o in OFFICIAL)


# 「域名活着但站点没了」的典型占位页。别把它们当存活 ——
# 实测这批候选里这类比例不低（nginx 默认页 / 空间商占位 / 域名待售）。
DEAD_TITLE_RE = re.compile(
    r"没有找到站点|站点创建成功|Welcome to nginx|Apache2? (Ubuntu|Debian) Default|"
    r"域名(出售|转让|待售)|for sale|parked|Default Web Site|502 Bad Gateway|"
    r"503 Service|403 Forbidden|Directory listing for", re.I)


def _origin(dom: str) -> str:
    return dom if dom.startswith("http") else "https://" + dom


# 单次尝试的失败率在本机实测约 **45%**（样本：60 个已知可达的镜像站，
# 失败类型 ProxyError / SSLError / ReadTimeout 各占一部分）。
# 所以「一次失败」完全不足以判死 —— 3 次尝试后成功率 ≈ 1-0.45³ ≈ 91%。
# 这个数字决定了 `--retries` 的默认值（写死在这里，避免以后又退回"试一次就下结论"）。
DEFAULT_RETRIES = 2
# 运行期生效的重试次数（由 --retries 覆盖）。用模块级变量而非改函数签名，
# 是为了让 scan_live / scan_deep 内部所有取页都统一生效、不遗漏某一处。
_RETRIES = DEFAULT_RETRIES


def _get(url, timeout):
    r, _ = _get_ex(url, timeout)
    return r


def _get_ex(url, timeout, retries=None):
    """返回 (resp 或 None, 错误简串)。

    ⚠ 一定要把**真实异常**带出来：早期版本只写「首页取不到」，
    结果 161 个域全报同一句，完全看不出是超时、TLS、还是连接被拒。
    """
    if retries is None:
        retries = _RETRIES
    try:
        return http_get(url, timeout=timeout, retries=retries), ""
    except Exception as e:
        # HTTPError 说明**站点/代理有响应**（403 = WAF、404 = 路径不对、5xx = 上游故障），
        # 与「连不上」是完全不同的事实，不能都记成「不可达」。
        resp = getattr(e, "response", None)
        code = getattr(resp, "status_code", None)
        tag = f"HTTP {code}" if code else type(e).__name__
        return None, f"{tag}: {str(e)[:60]}"


def _classes(el) -> str:
    if el is None:
        return ""
    cid = el.get("id") or ""
    cls = el.get("class") or []
    if isinstance(cls, str):
        cls = [cls]
    return ("#" + cid if cid else "") + ("." + ".".join(cls) if cls else "")


def css_of(el) -> str:
    """由元素生成一个**稳**的 CSS 选择器（优先 id，其次 tag+首个 class）。"""
    if el is None:
        return ""
    if el.get("id"):
        return "#" + el["id"]
    cls = el.get("class") or []
    if isinstance(cls, str):
        cls = cls.split()
    if cls:
        return f"{el.name}.{cls[0]}"
    return el.name or ""


def best_catalog_container(soup, page_url: str):
    """自动找出**目录容器**：包含章节式链接最多的那个节点。

    为什么不只用固定候选选择器：实测 `sequge.com` 的目录是
    `ul.dirlist.three.clearfix` —— 不在任何通用候选表里，于是被判「无可用目录」。
    固定表永远追不上站点的类名花样；而「谁的章节链接多」是**结构事实**。
    所以：先按结构自动发现，再把它变成选择器记下来（供生成规则用）。
    """
    from collections import Counter
    cnt, nodes = Counter(), {}
    n_links = 0
    for a in soup.find_all("a", href=True):
        href = (a.get("href") or "").strip()
        if not href:
            continue
        full = urljoin(page_url, href)
        p = urlparse(full).path
        if not re.search(r"\d+(_\d+)?\.html?$", p):
            continue
        n_links += 1
        # 以「链接的父节点」为起点往上找 3 层
        node = a.parent
        for _ in range(4):
            if node is None:
                break
            nodes[id(node)] = node
            cnt[id(node)] += 1
            node = node.parent
    if not cnt:
        return None, 0, []
    key, best_n = cnt.most_common(1)[0]
    el = nodes[key]
    # 容器内的章节链接（用于后续取第一章）
    links = [a for a in el.find_all("a", href=True)
             if re.search(r"\d+(_\d+)?\.html?$",
                          urlparse(urljoin(page_url, a["href"])).path)]
    # ⚠ 必须返回「**链接**的选择器」而不是「容器的选择器」。
    # 引擎的 `item_selector` 若选中一个容器，语义是「把这个容器当**一个**目录项」
    # （href 取内嵌首个 <a>、标题取容器全文）——实测 `dl` 于是只产出 1 章、
    # 标题是整张目录的全文。加上后代选择器 ` a` 才是「每章一项」。
    return f"{css_of(el)} a", best_n, links


def any_internal_candidates(html: str, base: str, limit: int = 8):
    """兜底候选：**任何**内部链接里带数字的页（排除导航/分类/用户中心这类明显非书的）。

    用于「首页既没有最新章节、也匹配不上书籍页形态」的站 ——
    与其判死，不如**真的去试几个**：这些站往往只是把入口换了个位置
    （排行榜 / 分类页 / 最近更新页）。成本有界（≤ limit 个请求）。
    """
    soup = make_soup(html)
    host = urlparse(base).netloc
    skip = re.compile(r"/(user|login|register|top|rank|category|sort|search|tag|"
                      r"about|contact|help|css|js|img|images|assets|static|"
                      r"favicon|sitemap|rss|feed|xuanhuan|wuxia|dushi|lishi|"
                      r"kehuan|youxi|yanqing|wangyou|kehuan|sort|quanben|"
                      r"full|all)(/|$|\.)", re.I)
    seen, out = set(), []
    for a in soup.find_all("a", href=True):
        href = (a.get("href") or "").strip()
        if not href or href.startswith(("#", "javascript:", "mailto:")):
            continue
        full = urljoin(base, href)
        p = urlparse(full)
        if p.netloc != host or not re.search(r"\d", p.path):
            continue
        if skip.search(p.path):
            continue
        if chapter_like(p.path) or p.path in seen:
            continue
        seen.add(p.path)
        out.append(full)
        if len(out) >= limit:
            break
    return out


def derive_book_urls(html: str, base: str):
    """从首页的**最新章节**链接反推书籍页 URL。⭐ 这是本工具最有用的一招。

    笔趣阁系镜像的首页几乎必然列出「最新章节」——那些链接形如
    `/book/12345/678901.html`（书 + 章两级数字）。把**最后一段数字后缀剥掉**，
    就得到书籍页 URL。比起「猜书籍页路径形态」，这招不依赖站点用什么前缀
    （`book` / `txt` / `biquge` / `xs` / 纯数字都有），命中率高得多。

    实测：早先只按固定路径形态匹配，39/64 个站报「首页无书籍页链接」；
    改用本招后大多数能拿到书籍页。
    """
    soup = make_soup(html)
    out, seen = [], set()
    for a in soup.find_all("a", href=True):
        href = (a.get("href") or "").strip()
        if not href or href.startswith(("#", "javascript:", "mailto:")):
            continue
        full = urljoin(base, href)
        if urlparse(full).netloc != urlparse(base).netloc:
            continue
        path = urlparse(full).path
        m = CHAPTER_HREF_RE.match(path)
        if not m or not m.group("bid"):
            continue
        bid = m.group("bid")
        book_path = path[:path.rfind("/" + bid + "/")] + f"/{bid}/"
        if chapter_like(book_path):
            continue
        if book_path in seen:
            continue
        seen.add(book_path)
        out.append(urljoin(base, book_path))
    return out


def chapter_like(path: str) -> bool:
    """路径本身看着就像章节页/分页，不能当书籍页。"""
    tail = path.rstrip("/").split("/")[-1]
    return bool(re.search(r"\d+\.html?$", tail))


def find_book_link(html: str, base: str):
    """在首页里找形似书籍详情页的链接（作为 derive_book_urls 的补充）。"""
    soup = make_soup(html)
    seen = []
    for a in soup.find_all("a", href=True):
        href = (a.get("href") or "").strip()
        if not href or href.startswith(("#", "javascript:", "mailto:")):
            continue
        full = urljoin(base, href)
        path = urlparse(full).path
        if chapter_like(path):
            continue
        for rx in BOOK_PATH_RES:
            if rx.search(path):
                seen.append(full)
                break
    return seen


def _resolves(dom: str) -> bool:
    """DNS 预筛。⚠ 它是**加速手段，不是判死依据**：

    - 这类候选里绝大多数域名根本不存在（NXDOMAIN），先筛掉能省掉
      「https 超时 + http 超时」两次白等（实测单域最坏 ≈14s）；
    - 但 DNS 也可能瞬时抽风，所以**失败重试一次**才判不可达；
    - 真正"站点抽风"（解析正常、HTTP 时好时坏）不会被这一步误杀 ——
      那类站点会进入后面的 HTTP 存活判定，并走重试。
    """
    import socket
    socket.setdefaulttimeout(4)
    for _ in range(2):
        try:
            socket.gethostbyname(dom)
            return True
        except Exception:
            continue
    return False


def scan_live(domain: str, timeout: float):
    """判存活。三态结论，**不把"没连上"等同于"站点已死"**：

    - `alive=True`            ：拿到了 <400 的响应
    - `alive=False, blocked=True`：站点**有响应**但拒绝（403/404/5xx）—— 站点活着，
                              只是这一层进不去（WAF / 路径不对），后续可再探
    - `alive=False, unknown=True`：多次尝试后仍连不上（ProxyError/SSLError/超时）。
                              ⚠ 本机实测单次失败率约 **45%**（含代理与 TLS 因素），
                              故这一类只记「未确认」，**不能当成死站**。
    """
    if not _resolves(domain):
        return {"domain": domain, "alive": False, "note": "DNS 不解析（已重试）"}
    last = ""
    for scheme in ("https", "http"):
        url = f"{scheme}://{domain}/"
        r, err = _get_ex(url, timeout)
        if r is not None and r.status_code < 400:
            title = _page_title(r.text)
            if DEAD_TITLE_RE.search(title or ""):
                return {"domain": domain, "alive": False,
                        "note": f"占位页（{title[:40]}）"}
            rec = {"domain": domain, "alive": True, "base": url,
                   "status": r.status_code, "final": r.url,
                   "len": len(r.content), "title": title}
            # 「返回 200 但等于没有站点」：这类**不是死站，但作为入口不可用**。
            # 实测样本：390B / 278B / 39B 的空壳页，以及域名待售页（4.cn）。
            # 不单独标出来，它们会以「首页无书籍页链接」混进失败统计、掩盖真问题。
            n_a = r.text.count("<a ")
            if len(r.content) < 2000 or n_a == 0:
                rec["placeholder"] = True
                rec["note"] = f"空壳/占位页（{len(r.content)} 字节 / {n_a} 个链接）"
            why = classify("", domain, title)
            if why:
                rec["excluded"] = why
            return rec
        last = err or last
        if err.startswith("HTTP 4"):
            # 站点有响应 → 活着（403 WAF / 404 首页路径特殊）
            return {"domain": domain, "alive": False, "blocked": True,
                    "note": f"站点有响应但拒绝（{err}）"}
    return {"domain": domain, "alive": False, "unknown": True,
            "note": f"多次尝试未连上（{last}）"}


def _page_title(html: str) -> str:
    m = re.search(r"<title[^>]*>(.*?)</title>", html or "", re.S | re.I)
    if not m:
        return ""
    t = re.sub(r"\s+", " ", m.group(1)).strip()
    return t[:80]


def scan_deep(rec: dict, timeout: float):
    """对一个存活站做结构探测：**逐个候选选择器实测**，记录命中项。

    一次探测把「写规则所需的事实」全部取齐：书籍页 URL + 命中的目录选择器 +
    命中的正文选择器 + 章节链接形态。后面生成规则几乎是机械的。
    """
    dom = rec["domain"]
    base = rec.get("base") or _origin(dom)
    out = {"domain": dom, "base": base, "alive": True,
           "title": rec.get("title", ""), "book_url": None,
           "chapters": 0, "catalog_selector": "", "chapter_url": None,
           "content_selector": "", "content_cjk": 0,
           "book_path": "", "chapter_path": "", "verdict": ""}
    try:
        r, err = _get_ex(base, timeout)
        if r is None:
            out["verdict"] = f"首页取不到（{err}）"
            return out
        # 优先用「最新章节链接反推」（命中率高），再补上路径形态匹配
        cands = (derive_book_urls(r.text, base) + find_book_link(r.text, base)
                 + any_internal_candidates(r.text, base))
        # 去重保序
        seen, uniq = set(), []
        for u in cands:
            if u not in seen:
                seen.add(u)
                uniq.append(u)
        cands = uniq
        if not cands:
            out["verdict"] = "首页无书籍页链接"
            return out

        # 依次试书籍页候选，找到能取出目录的那个（最多试 4 个，控制请求数）
        best = None
        for bu in cands[:6]:
            rb = _get(bu, timeout)
            if rb is None:
                continue
            soup = make_soup(rb.text)
            # ① 自动发现目录容器（按章节链接密度）—— 比固定候选表覆盖面大
            sel_auto, n_auto, links_auto = best_catalog_container(soup, bu)
            hit = (sel_auto, n_auto, links_auto) if n_auto >= MIN_CHAPTERS else None
            # ② 固定候选表兜底（自动发现偶尔会选到外层 wrapper）
            if hit is None:
                for sel in CATALOG_CANDIDATES:
                    links = [a for a in soup.select(sel) if a.get("href")]
                    if len(links) >= MIN_CHAPTERS:
                        hit = (sel, len(links), links)
                        break
            if hit:
                best = (bu, hit[0], hit[2], hit[1], soup)
                break
        if not best:
            out["verdict"] = "书籍页没有可用目录（自动发现 + 候选选择器均未命中）"
            return out

        bu, sel, links, n_links, _ = best
        out["book_url"] = bu
        out["book_path"] = urlparse(bu).path
        out["catalog_selector"] = sel
        out["chapters"] = n_links
        # 书号形态：决定生成规则时 `book.url_pattern` 该用 `(\d+)` 还是 `([A-Za-z0-9]+)`
        seg = [p for p in urlparse(bu).path.split("/") if p]
        out["bid_shape"] = ("digits" if seg and seg[-1].isdigit()
                            else ("alnum" if seg else "unknown"))
        out["bid_sample"] = seg[-1] if seg else ""

        # 抽 1 章 → 逐个候选实测正文容器
        cu = urljoin(bu, links[0]["href"])
        out["chapter_url"] = cu
        out["chapter_path"] = urlparse(cu).path
        rc = _get(cu, timeout)
        if rc is None:
            out["verdict"] = f"目录可用（{len(links)} 章），章节页取不到"
            return out
        csoup = make_soup(rc.text)
        for csel in CONTENT_CANDIDATES:
            el = csoup.select_one(csel)
            if el is None:
                continue
            cjk = len(re.findall(r"[\u4e00-\u9fff]", el.get_text()))
            if cjk >= MIN_CJK:
                out["content_selector"] = csel
                out["content_cjk"] = cjk
                break
        if not out["content_selector"]:
            # 候选全未命中 → 退回自动识别，只作参考（不算通过）
            el = guess_content_container(csoup, min_cjk=200)
            if el is not None:
                out["content_hint_auto"] = _classes(el)
                out["content_cjk"] = len(re.findall(r"[\u4e00-\u9fff]", el.get_text()))
            out["verdict"] = (f"目录可用（{len(links)} 章），正文候选未命中"
                              f"（自动识别到 {out.get('content_hint_auto', '?')}，"
                              f"{out['content_cjk']} 字）")
            return out
        out["verdict"] = (f"可做：目录 {len(links)} 章（{sel}），"
                          f"正文 {out['content_cjk']} 字（{out['content_selector']}）")
    except Exception as e:
        out["verdict"] = f"异常 {type(e).__name__}: {str(e)[:80]}"
    return out


def load_jsonl(path):
    """读 JSONL，**容忍坏行**。

    ⚠ 扫描可能正在向同一个文件追加（另开一个进程/后台任务），
    此刻读到的最后一行可能是**写了一半的多字节字符** → `UnicodeDecodeError`。
    所以：`errors="replace"` + 逐行 try，坏行跳过并计数（不静默）。
    """
    if not os.path.exists(path):
        return []
    out = []
    bad = 0
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:
                bad += 1
    if bad:
        print(f"  （{path}: 跳过 {bad} 行坏数据——通常是文件正在被追加）")
    return out


def aggregate(in_path, min_views=0):
    """按 domain 聚合，保留最具代表性的 name 与最大热度；同时剔除明显不适合的站。"""
    agg = {}
    dropped = {}
    total = 0
    with open(in_path, encoding="utf-8") as f:
        for line in f:
            try:
                d = json.loads(line)
            except Exception:
                continue
            total += 1
            dom = (d.get("domain") or "").strip()
            if not dom or _is_official(dom):
                continue
            if d.get("view_total", 0) < min_views:
                continue
            why = classify(d.get("name"), dom)
            if why:
                dropped[why.split("（")[0]] = dropped.get(why.split("（")[0], 0) + 1
                continue
            cur = agg.get(dom)
            if cur is None:
                agg[dom] = {"domain": dom, "name": d.get("name"),
                            "views": d.get("view_total", 0), "hits": 1}
            else:
                cur["hits"] += 1
                cur["views"] = max(cur["views"], d.get("view_total", 0))
    print(f"  线索 {total} 条 → 唯一域 {len(agg)} 个")
    if dropped:
        print(f"  启发式剔除：{dropped}")
    return sorted(agg.values(), key=lambda x: (-x["views"], -x["hits"]))


def classify(name: str, domain: str, title: str = "") -> str:
    """返回排除原因（空串 = 保留）。

    ⚠ 纯启发式：只用于**把明显不适合的剔掉**，不追求完全准确。
    命中情况会被计入报告，以免"静默丢一堆"。
    """
    hay = f"{name or ''} {domain or ''} {title or ''}".lower()
    for w in NON_NOVEL:
        if w in hay:
            return f"非小说站（命中 {w}）"
    for w in ADULT_WORDS:
        if w.lower() in hay:
            return f"成人向（命中 {w}）"
    return ""


def tidy(paths, out: str):
    """去重 + 用**当前**的判定规则重新过一遍历史记录（可合并多个输入）。

    ⚠ 必须能合并多份输入：扫描是分批跑的（首次全量 + 多轮「未确认重扫」），
    结果落在 `live.jsonl` / `live.retry.jsonl` 两个文件里。
    若不合并，第二轮救回的站就白扫了 —— 报告里仍按「不可达」算。

    为什么需要重新判定：扫描是分批跑的，中途改过判据（补了「空壳页」「正版后缀」等），
    早期写下的记录会带着**过时**的结论留在文件里（实测出现过
    `没有找到站点` 的 nginx 默认页被记成 alive）。与其重扫一遍（每个域要发请求），
    不如就地用已存的字段重新判定 —— 判定是纯函数，不需要网络。
    """
    recs = {}
    order = []
    total_lines = 0
    for path in paths:
        for r in load_jsonl(path):
            total_lines += 1
            dom = r.get("domain")
            if not dom:
                continue
            if dom not in recs:
                order.append(dom)
            recs[dom] = r          # 后者覆盖前者（越晚的记录越新）
    kept, dropped = [], []
    for dom in order:
        r = dict(recs[dom])
        if r.get("alive"):
            title = r.get("title") or ""
            if _is_official(dom):
                r["alive"] = False
                r["note"] = "正版站（另走正版池）"
            elif DEAD_TITLE_RE.search(title):
                r["alive"] = False
                r["note"] = f"占位页（{title[:40]}）"
            else:
                why = classify("", dom, title)
                if why:
                    r["excluded"] = why
                else:
                    r.pop("excluded", None)
                # 空壳页判定（对历史记录补算：只依赖已存的 len，不需要网络）
                if (r.get("len") or 0) < 2000 and not r.get("placeholder"):
                    r["placeholder"] = True
                    r["note"] = f"空壳/占位页（{r.get('len')} 字节）"
        elif (r.get("note") or "") == "HTTP 不可达":
            # 历史遗留结论：那时是「单次尝试即判死」，而本机单次失败率约 45%，
            # 所以这些**不算死亡**，只算「未确认」—— 标出来供 --only unknown 重扫。
            r["unknown"] = True
            r["note"] = "未确认（历史单次尝试结论，需重扫）"
        (kept if r.get("alive") else dropped).append(r)
    with open(out, "w", encoding="utf-8") as f:
        for r in kept + dropped:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    usable = [r for r in kept if not r.get("excluded") and not r.get("placeholder")]
    blocked = [r for r in dropped if r.get("blocked")]
    unknown = [r for r in dropped if r.get("unknown")]
    print(f"合并 {len(paths)} 份输入 {total_lines} 行 → 唯一域 {len(order)}")
    ph = [r for r in kept if r.get("placeholder")]
    print(f"可达 {len(kept)} · 其中空壳/占位 {len(ph)} · 可用候选 {len(usable)}")
    print(f"站点有响应但拒绝(WAF/404) {len(blocked)} · "
          f"未确认（连不上，**不等于死站**）{len(unknown)} · "
          f"DNS 不解析 {sum(1 for r in dropped if 'DNS' in (r.get('note') or ''))} · "
          f"占位页 {sum(1 for r in dropped if '占位页' in (r.get('note') or ''))}")
    print(f"  → {out}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--phase", choices=["live", "deep", "stats", "tidy"], required=True)
    ap.add_argument("--in", dest="inp", default=None,
                    help="输入文件（tidy 可给逗号分隔的多个，会按域合并）。"
                         "live 默认 .sources/live.jsonl；"
                         "deep 默认 .sources/live.clean.jsonl（不存在则用 live.jsonl）")
    ap.add_argument("--out", default=None)
    ap.add_argument("--limit", type=int, default=0, help="只扫前 N 个（0 = 全部）")
    ap.add_argument("--concurrency", type=int, default=24)
    ap.add_argument("--timeout", type=float, default=8.0)
    ap.add_argument("--retries", type=int, default=DEFAULT_RETRIES,
                    help="每次请求的额外重试次数（本机单次失败率约 45%%，3 次尝试≈91%% 成功率）")
    ap.add_argument("--min-views", type=int, default=0)
    ap.add_argument("--only", choices=["all", "unknown", "blocked"], default="all",
                    help="live 段重扫范围：重扫「未确认」或「有响应但被拒」的域，"
                         "用于把因环境导致的假死站救回来")
    ap.add_argument("--resume", action="store_true", help="跳过已扫过的域")
    args = ap.parse_args()
    global _RETRIES
    _RETRIES = max(0, args.retries)

    if args.phase == "tidy":
        # 默认合并「首次全量」与「未确认重扫」两份结果 —— 不合并会丢第二轮救回的站
        default_in = ",".join([os.path.join(".sources", "live.jsonl"),
                               os.path.join(".sources", "live.retry.jsonl"),
                               os.path.join(".sources", "live.retry2.jsonl")])
        srcs = [x for x in (args.inp or default_in).split(",") if x.strip()]
        srcs = [x for x in srcs if os.path.exists(x)]
        tidy(srcs, args.out or os.path.join(".sources", "live.clean.jsonl"))
        return

    if args.phase == "stats":
        deep = args.out or os.path.join(".sources", "deep.jsonl")
        recs = load_jsonl(deep)
        ok = [r for r in recs if r.get("content_selector")]
        print(f"deep 记录 {len(recs)} 条 · **通过（目录+正文双命中）** {len(ok)} 条")
        from collections import Counter
        c = Counter(r.get("content_selector") for r in ok)
        print("  正文选择器分布：")
        for k, v in c.most_common(20):
            print(f"    {v:5}  {k}")
        c2 = Counter(r.get("catalog_selector") for r in ok)
        print("  目录选择器分布：")
        for k, v in c2.most_common(20):
            print(f"    {v:5}  {k}")
        c3 = Counter((r.get("catalog_selector"), r.get("content_selector")) for r in ok)
        print("  组合（= 可合并为同一条族规则的签名）Top15：")
        for (a, b), v in c3.most_common(15):
            print(f"    {v:5}  {a}  +  {b}")
        return

    if args.phase == "live" and args.only != "all" and not args.out:
        args.out = os.path.join(".sources", "live.retry.jsonl")
    out_path = args.out or os.path.join(
        ".sources", "live.jsonl" if args.phase == "live" else "deep.jsonl")
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)

    if args.phase == "live":
        if args.only != "all":
            # 重扫：只挑之前「未确认」或「被拒」的域（见 scan_live 的三态语义）
            src = os.path.join(".sources", "live.clean.jsonl")
            prev = {r["domain"]: r for r in load_jsonl(src)}
            flag = "unknown" if args.only == "unknown" else "blocked"
            cand = [{"domain": d, "views": 0, "hits": 0}
                    for d, r in prev.items() if r.get(flag)]
            print(f"重扫「{args.only}」共 {len(cand)} 个域")
        else:
            cand = aggregate(args.inp or os.path.join(".sources", "shuyuan.jsonl"),
                             min_views=args.min_views)
            print(f"聚合后候选域 {len(cand)} 个（已剔除正版/非小说/成人向/低热）")
        if args.limit:
            cand = cand[:args.limit]
        todo = cand
    else:
        src = args.inp
        if not src:
            clean = os.path.join(".sources", "live.clean.jsonl")
            src = clean if os.path.exists(clean) else os.path.join(".sources", "live.jsonl")
        live = [r for r in load_jsonl(src)
                if r.get("alive") and not r.get("excluded")
                and not r.get("placeholder")]
        print(f"存活且非空壳 {len(live)} 个（来自 {src}）")
        if args.limit:
            live = live[:args.limit]
        todo = live

    done = set()
    if args.resume and os.path.exists(out_path):
        done = {r["domain"] for r in load_jsonl(out_path)}
        todo = [t for t in todo if t["domain"] not in done]
        print(f"续跑：已完成 {len(done)}，待扫 {len(todo)}")

    lock = threading.Lock()
    t0 = time.time()
    n_ok = 0
    with open(out_path, "a", encoding="utf-8") as fout, \
            ThreadPoolExecutor(max_workers=args.concurrency) as ex:
        futs = {}
        for item in todo:
            if args.phase == "live":
                futs[ex.submit(scan_live, item["domain"], args.timeout)] = item
            else:
                futs[ex.submit(scan_deep, item, args.timeout)] = item
        for i, fut in enumerate(as_completed(futs), 1):
            try:
                rec = fut.result()
            except Exception as e:
                rec = {"domain": futs[fut]["domain"], "alive": False,
                       "verdict": f"异常 {type(e).__name__}"}
            with lock:
                fout.write(json.dumps(rec, ensure_ascii=False) + "\n")
                fout.flush()
                if rec.get("alive"):
                    n_ok += 1
            if i % 100 == 0 or i == len(futs):
                el = time.time() - t0
                print(f"  {i}/{len(futs)} · 存活/命中 {n_ok} · "
                      f"{el:.0f}s（{i/max(el,0.1):.1f}/s）")

    print(f"\n完成 → {out_path}")


if __name__ == "__main__":
    main()
