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

import time

DEFAULT_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")


class BrowserUnavailable(RuntimeError):
    """浏览器路由不可用（缺依赖 / 缺浏览器内核）。"""


def deps_available() -> tuple:
    """返回 (是否可用, 缺失说明)。"""
    try:
        import playwright  # noqa: F401
    except ImportError:
        return False, ("缺少 playwright。安装：\n"
                       "  F:\\Python314\\python.exe -m pip install playwright\n"
                       "  F:\\Python314\\python.exe -m playwright install chromium")
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            p.chromium.executable_path
    except Exception as e:
        return False, (f"Chromium 内核不可用：{e}\n"
                       f"  修复：F:\\Python314\\python.exe -m playwright install chromium")
    return True, ""


class BrowserFetcher:
    """一个进程内复用的 Chromium 实例（**只能在创建它的线程里用**）。

    用法：
        with BrowserFetcher(log=print) as bf:
            html = bf.fetch(url, click_selectors=["text=目录"])
    """

    def __init__(self, headless: bool = True, timeout: int = 45000,
                 user_agent: str = DEFAULT_UA, log=None):
        self.headless = headless
        self.timeout = timeout
        self.user_agent = user_agent or DEFAULT_UA
        self.log = log or (lambda m, level="info": None)
        self._pw = None
        self._browser = None
        self._ctx = None
        self._page = None

    # ------------------------------------------------------------
    def start(self):
        ok, why = deps_available()
        if not ok:
            raise BrowserUnavailable(why)
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=self.headless)
        self._ctx = self._browser.new_context(
            user_agent=self.user_agent, locale="zh-CN",
            viewport={"width": 1440, "height": 900})
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
        pg = self._page
        pg.goto(url, wait_until=wait_until, timeout=self.timeout)

        for sel in (click_selectors or []):
            try:
                el = pg.query_selector(sel)
                if el:
                    el.click(timeout=8000)
                    pg.wait_for_timeout(1500)
                    self.log(f"  浏览器路由：已点击「{sel}」", "info")
                else:
                    self.log(f"  浏览器路由：未找到「{sel}」（跳过）", "warn")
            except Exception as e:
                self.log(f"  浏览器路由：点击「{sel}」失败（跳过）：{e}", "warn")

        if wait_selector:
            try:
                pg.wait_for_selector(wait_selector, timeout=min(self.timeout, 30000))
            except Exception as e:
                self.log(f"  浏览器路由：等待「{wait_selector}」超时，按现状取 DOM：{e}", "warn")
        if wait_ms:
            pg.wait_for_timeout(wait_ms)
        if scroll:
            try:
                pg.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
                pg.wait_for_timeout(1200)
            except Exception:
                pass
        return pg.content()

    def fetch_bytes(self, url: str) -> bytes:
        """经由浏览器上下文取二进制（会在页面内 fetch，故带同源会话）。"""
        if self._page is None:
            self.start()
        pg = self._page
        b64 = pg.evaluate(
            """async (u) => {
                 const r = await fetch(u, {credentials:'same-origin'});
                 const b = await r.arrayBuffer();
                 let s = ''; const a = new Uint8Array(b);
                 for (let i = 0; i < a.length; i++) s += String.fromCharCode(a[i]);
                 return btoa(s);
               }""", url)
        import base64
        return base64.b64decode(b64)
