#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
浏览器路由：用真实浏览器渲染后再取 DOM。

为什么需要它
------------
纯 HTTP 路由只能拿到服务端首屏 HTML。以下两类站点因此抓不到：

1. **目录靠 JS 异步加载**（纵横、17K、七猫）——静态 HTML 里只有导航项，
   章节列表要等 XHR 回来才渲染；
2. **必须执行 JS 才能过反爬探针**的站点。

参考项目里这是标配：FictionDown 用 Chromedp / PhantomJS 处理这类页面
（`--driver chromedp`）。本项目此前只有 HTTP 路由，属于能力缺口。

设计取舍
--------
- **不用它做任何凭据相关的事**：不注入 Cookie、不登录、不接管你的浏览器会话。
  它只是"把页面渲染出来"，因此不构成 VIP 章节的获取路径。
- **人机验证不绕**：若站点要求完成 captcha（如起点的 WAF），本路由同样会失败——
  那是需要人参与的环节，不在无人值守爬虫的范围内，代码里也不做任何绕过。
- **单线程**：Playwright 的同步 API 不能在多线程里共享，
  故 `fetch_mode=browser` 时强制并发 1（引擎会打印说明），避免隐蔽的错乱。

依赖：`playwright` + 已安装的 Chromium。**可选依赖**——不装只影响 browser 模式的站点。
"""

import os
import sys
import time

# 当前解释器路径（**自发现**，不写死任何盘符/目录）——报错指引里用它。
PY = sys.executable or "python"

DEFAULT_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

# ============================================================
#  反检测（anti-detect）
# ============================================================
# [复用来源] 本家 webcopier 仓/webcopier/playwright_utils.py（AntiDetectBrowser）
# 许可证：内部项目（全哥创建，本家复用，见 docs/REFERENCE.md 第一节）。
# 抽取范围：DEFAULT_LAUNCH_ARGS + channel=chrome/headed 的本地 Chrome 用法。
# 改造点：接入本项目的规则体系（规则里用 browser.anti_detect 开关），
#         去掉 cookie 存取，去掉随仓第三方 stealth.min.js（见下）。
#
# 为什么需要它（实测 2026-09-20，起点）：
#   · 捆绑 Chromium + headless 时，请求头 `sec-ch-ua` 里赫然写着 **HeadlessChrome**，
#     `navigator.webdriver = true`，起点 Chaos VM 直接挡死（202 挑战页 42s 不放行）。
#   · 换成 **本机真 Chrome（channel="chrome"）+ headed + 关 AutomationControlled** 后：
#     202 状态数秒内正常渲染出 67~70 万字节书页，#bookName/.chapter-name 全部命中，
#     navigator.webdriver=False、plugins=5、UA 不含 HeadlessChrome。→ 起点可抓。
#
# 可选的 stealth 脚本（**不入仓**，需用户自备 —— 见 docs/REFERENCE.md 第六节）：
#   上面那组「真 Chrome + headed + 关 AutomationControlled + 语言自洽」经**实测已足够**
#   通过起点 Chaos VM（分两组对照：带/不带 stealth.min.js 结果一致），
#   因此本仓**不随仓分发任何第三方 stealth 源码**（本仓铁律：第三方源码不入仓）。
#   若某站点还需更强伪装，可自取 puppeteer-extra-plugin-stealth（MIT）的
#   `stealth.min.js`，用环境变量 NOVELDOWN_STEALTH_JS 或规则里的
#   `browser.stealth_js` 指定其路径，即会在页面脚本前自动注入。
STEALTH_ENV_VAR = "NOVELDOWN_STEALTH_JS"

# 语言一致性脚本。context 里声明了 locale="zh-CN"，但 `navigator.languages`
# 默认仍取浏览器 UI 语言（实测 "en-US,en"）—— 真人中文 Chrome 不会这么自相矛盾，
# 而反爬常查 navigator.language / languages / Accept-Language 三者是否自洽。
# 与 stealth 同批注入（在**页面脚本之前**执行，故用 init script）。
CONSISTENCY_JS = """
(() => {
  try {
    Object.defineProperty(navigator, 'languages', {get: () => ['zh-CN', 'zh']});
  } catch (e) {}
})();
"""

DEFAULT_LAUNCH_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--disable-features=IsolateOrigins,site-per-process",
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-infobars",
    "--disable-dev-shm-usage",
    "--disable-browser-side-navigation",
    "--disable-gpu",
    "--disable-extensions",
    "--disable-background-networking",
    "--disable-sync",
    "--disable-default-apps",
    "--hide-scrollbars",
    "--metrics-recording-only",
    "--mute-audio",
    "--no-first-run",
    "--safebrowsing-disable-auto-update",
]


def anti_detect_available() -> tuple:
    """检查本机是否有可用于反检测的真 Chrome。

    只有用**本机真 Chrome**（`channel="chrome"`）才可靠：playwright 捆绑的
    Chromium 在 headless 下会把 `HeadlessChrome` 写进 `sec-ch-ua`。
    """
    cands = [
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"),
                     r"Google\Chrome\Application\chrome.exe"),
        os.path.join(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
                     r"Google\Chrome\Application\chrome.exe"),
    ]
    for c in cands:
        if os.path.isfile(c):
            return True, c
    return False, "未找到系统 Google Chrome（channel=\"chrome\" 需要它）"


class BrowserUnavailable(RuntimeError):
    """浏览器路由不可用（缺依赖 / 缺浏览器内核）。"""


def deps_available() -> tuple:
    """返回 (是否可用, 缺失说明)。"""
    try:
        import playwright  # noqa: F401
    except ImportError:
        return False, ("缺少 playwright。安装：\n"
                       f"  {PY} -m pip install playwright\n"
                       f"  {PY} -m playwright install chromium")
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            p.chromium.executable_path
    except Exception as e:
        return False, (f"Chromium 内核不可用：{e}\n"
                       f"  修复：{PY} -m playwright install chromium")
    return True, ""


class BrowserFetcher:
    """一个进程内复用的 Chromium 实例（**只能在创建它的线程里用**）。

    用法：
        with BrowserFetcher(log=print) as bf:
            html = bf.fetch(url, click_selectors=["text=目录"])
    """

    def __init__(self, headless: bool = True, timeout: int = 45000,
                 user_agent: str = DEFAULT_UA, log=None,
                 anti_detect: bool = False, channel: str = "", args=None,
                 stealth_js: str = None, proxy: str = ""):
        self.headless = headless
        self.timeout = timeout
        self.user_agent = user_agent or DEFAULT_UA
        self.log = log or (lambda m, level="info": None)
        self.anti_detect = anti_detect
        self.channel = channel
        self.extra_args = list(args or [])
        # 可选 stealth 脚本：显式传入 > 环境变量 > 无（详见模块常量处说明）
        self.stealth_js = (stealth_js if stealth_js is not None
                           else os.environ.get(STEALTH_ENV_VAR, ""))
        # 代理：Chromium **不读** HTTP_PROXY/HTTPS_PROXY 环境变量（requests 会读），
        # 所以「只在代理下可达」的站点必须显式把代理交给浏览器，否则报 ERR_TIMED_OUT。
        # 传 "env" 表示沿用环境变量里的代理。
        self.proxy = self._resolve_proxy(proxy)
        self._pw = None
        self._browser = None
        self._ctx = None
        self._page = None

    # ------------------------------------------------------------
    @staticmethod
    def _resolve_proxy(proxy) -> str:
        """把规则里的 proxy 配置解析成 playwright 需要的 URL（空串 = 不用代理）。

        · `""` / `False` / None → 不用代理
        · `"env"` / True         → 取环境变量 HTTPS_PROXY / HTTP_PROXY
        · 其它字符串             → 当作代理 URL 直接用
        """
        if not proxy:
            return ""
        if proxy is True or str(proxy).lower() == "env":
            for k in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy",
                      "ALL_PROXY", "all_proxy"):
                v = os.environ.get(k)
                if v:
                    return v
            return ""
        return str(proxy)

    def launch_kwargs(self) -> dict:
        """构造 playwright `launch()` 的参数（**不启动浏览器**，便于单测）。

        反检测模式的关键三点（缺一不可）：
          · `channel="chrome"` —— 用本机**真** Chrome，而非捆绑 Chromium；
          · `headless=False`   —— 捆绑 Chromium + headless 会在 `sec-ch-ua`
            里明写 `HeadlessChrome`，直接暴露；
          · `args=DEFAULT_LAUNCH_ARGS + …` —— 关掉自动化特征（见常量处注释）。
        另外 `start()` 里还会注入 `CONSISTENCY_JS`（语言自洽），以及可选的
        用户自备 stealth 脚本（若已配置）。
        """
        kwargs = {}
        if self.proxy:
            kwargs["proxy"] = {"server": self.proxy}
        if self.anti_detect:
            kwargs["channel"] = self.channel or "chrome"
            kwargs["headless"] = False
            kwargs["args"] = DEFAULT_LAUNCH_ARGS + self.extra_args
        else:
            kwargs["headless"] = self.headless
            if self.channel:
                kwargs["channel"] = self.channel
            if self.extra_args:
                kwargs["args"] = self.extra_args
        return kwargs

    def start(self):
        ok, why = deps_available()
        if not ok:
            raise BrowserUnavailable(why)
        # playwright 的 sync API 在进程退出时会因内部连接任务被取消，经 asyncio
        # logger 打出一堆 "Task was destroyed but it is pending!" /
        # TargetClosedError —— 与抓取结果无关（实测在 close() 之后才出现），
        # 抬高该 logger 级别以免污染终端输出。只影响 asyncio 自身的拆除日志。
        import logging
        logging.getLogger("asyncio").setLevel(logging.CRITICAL)

        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()

        if self.anti_detect:
            ok, why = anti_detect_available()
            if not ok:
                raise BrowserUnavailable(
                    f"反检测模式需要系统 Chrome：{why}\n"
                    f"  安装 Chrome 后可重试；或把规则的 browser.anti_detect 关掉。")
            self.log("  反检测模式：真 Chrome + headed + 关 AutomationControlled")

        self._browser = self._pw.chromium.launch(**self.launch_kwargs())
        self._ctx = self._browser.new_context(
            user_agent=self.user_agent, locale="zh-CN",
            timezone_id="Asia/Shanghai",
            viewport={"width": 1440, "height": 900})
        if self.anti_detect:
            self._ctx.add_init_script(CONSISTENCY_JS)
            p = self.stealth_js
            if p and os.path.isfile(p):
                self._ctx.add_init_script(path=p)
                self.log(f"  已注入自定义 stealth 脚本（{os.path.getsize(p) // 1024} KB）")
        self._page = self._ctx.new_page()
        return self

    def close(self):
        for obj, meth in ((self._ctx, "close"), (self._browser, "close")):
            try:
                if obj:
                    getattr(obj, meth)()
            except Exception:
                pass
        try:
            if self._pw:
                self._pw.stop()
        except Exception:
            pass
        self._pw = self._browser = self._ctx = self._page = None

    def __enter__(self):
        return self.start()

    def __exit__(self, *exc):
        self.close()

    # ------------------------------------------------------------
    def fetch(self, url: str, wait_selector: str = None, wait_ms: int = 0,
              click_selectors=None, scroll: bool = False,
              wait_until: str = "domcontentloaded") -> str:
        """渲染并返回页面 HTML。

        Args:
            url: 目标地址
            wait_selector: 等待该 CSS 选择器出现（目录类页面建议填 item_selector）
            wait_ms: 额外固定等待毫秒（给 XHR 留时间，兜底用）
            click_selectors: 需要先点的元素（如「目录」标签页），按顺序点，点不到则跳过
            scroll: 是否滚到底（触发懒加载）
            wait_until: goto 的等待条件
        """
        if self._page is None:
            self.start()
        ctx = self._ctx
        # 每次导航用**独立页面**。
        # 实测踩过（七猫，Nuxt SPA）：复用同一个 page 连续 goto 时，
        # 上一次的客户端路由会把新的文档级导航中断掉 → net::ERR_ABORTED，
        # 而且内容是空的（20 章全 failed）。独立页面彻底规避这类状态串扰；
        # context 复用 → WAF 下发的匿名 cookie 仍然带着，不重复过墙。
        page = ctx.new_page()
        try:
            try:
                page.goto(url, wait_until=wait_until, timeout=self.timeout)
            except Exception as e:
                msg = str(e)
                if ("ERR_ABORTED" in msg or "interrupted" in msg
                        or "frame was detached" in msg):
                    self.log("  浏览器路由：导航被 SPA 客户端路由中断，继续等目标元素", "warn")
                else:
                    raise

            for sel in (click_selectors or []):
                try:
                    el = page.query_selector(sel)
                    if el:
                        el.click(timeout=8000)
                        page.wait_for_timeout(1500)
                        self.log(f"  浏览器路由：已点击「{sel}」", "info")
                    else:
                        self.log(f"  浏览器路由：未找到「{sel}」（跳过）", "warn")
                except Exception as e:
                    self.log(f"  浏览器路由：点击「{sel}」失败（跳过）：{e}", "warn")

            if wait_selector:
                try:
                    page.wait_for_selector(wait_selector,
                                           timeout=min(self.timeout, 30000))
                except Exception as e:
                    self.log(f"  浏览器路由：等待「{wait_selector}」超时，按现状取 DOM：{e}",
                             "warn")
            if wait_ms:
                page.wait_for_timeout(wait_ms)
            if scroll:
                try:
                    page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
                    page.wait_for_timeout(1200)
                except Exception:
                    pass
            # 取 DOM。⚠ 有些站点会做**多跳 JS 跳转**（实测搜书网：章节页是「加载中」中转页
            # → /userverify → 跳去 bqg142.cc 的 hash 路由），此刻 `page.content()` 会抛
            # `Unable to retrieve content because the page is navigating and changing the content`。
            # 这属于「还在导航」，等一下重试即可 —— 不要把它当成失败。
            last = None
            for _ in range(4):
                try:
                    return page.content()
                except Exception as e:
                    last = e
                    if ("navigating" not in str(e)
                            and "changing the content" not in str(e)):
                        raise
                    try:
                        page.wait_for_load_state("domcontentloaded", timeout=8000)
                    except Exception:
                        pass
                    page.wait_for_timeout(1000)
            raise last
        finally:
            try:
                page.close()
            except Exception:
                pass

    def fetch_bytes(self, url: str) -> bytes:
        """经由浏览器上下文取二进制（会在页面内 fetch，故带同源会话）。"""
        import base64
        b64 = self._in_page_fetch(url, binary=True)
        return base64.b64decode(b64)

    def fetch_text(self, url: str, referer: str = None) -> str:
        """经由浏览器上下文取**原始文本**（JSON 接口用）。

        关键：不能用 `page.goto()` —— Chrome 会把 JSON 响应包成一个 `<pre>`
        的 HTML 文档，`page.content()` 拿到的就不是原始 JSON 了。
        页面内 `fetch()` 返回的是原始响应体，且同源请求会自动带上
        站点下发的匿名反爬 cookie（如阿里云 WAF 的 `acw_sc__v2`）——
        这正是纯 HTTP 路由拿不到的东西。
        """
        return self._in_page_fetch(url, binary=False, referer=referer)

    def _in_page_fetch(self, url: str, binary: bool, referer: str = None):
        """在页面内发起 fetch。

        每次用独立页面：同 context → WAF cookie 已在，不必重复过墙；
        独立页面 → 不受上一次导航残留状态影响。

        **落地页要用 referer，不能用站点根**（实测踩过）：起点的
        `ajax/book/category` 会校验来源，从 `https://www.qidian.com/` 根路径发起
        会被回 `{"code":1,"msg":"失败"}`；从书籍页发起才返回数据。
        """
        if self._page is None:
            self.start()
        from urllib.parse import urlparse
        p = urlparse(url)
        origin = f"{p.scheme}://{p.netloc}/"
        landing = referer or origin
        page = self._ctx.new_page()
        try:
            try:
                page.goto(landing, wait_until="domcontentloaded", timeout=self.timeout)
            except Exception as e:
                if "ERR_ABORTED" not in str(e):
                    raise
            return page.evaluate(
                """async ([u, bin]) => {
                     // {cookie:NAME} 占位符：从 document.cookie 取值填入 URL。
                     // 不少站点的 ajax 接口要求把 CSRF token 作为**查询参数**
                     // （起点 ajax/book/category 就是这样，光有 cookie 会被回「失败」）。
                     u = u.replace(/\\{cookie:([^}]+)\\}/g, (m, name) => {
                       const mm = document.cookie.match(
                         new RegExp('(?:^|; )' + name + '=([^;]*)'));
                       return mm ? decodeURIComponent(mm[1]) : '';
                     });
                     const r = await fetch(u, {credentials:'same-origin',
                                               headers:{'Accept':'application/json, text/plain, */*',
                                                        'X-Requested-With':'XMLHttpRequest'}});
                     if (bin) {
                       const b = await r.arrayBuffer(); const a = new Uint8Array(b);
                       let s = ''; for (let i = 0; i < a.length; i++) s += String.fromCharCode(a[i]);
                       return btoa(s);
                     }
                     return await r.text();
                   }""", [url, binary])
        finally:
            try:
                page.close()
            except Exception:
                pass
