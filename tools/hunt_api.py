#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""接口猎手：用真浏览器打开页面，**监听网络请求**，把 JSON 接口挖出来。

## 什么时候用它

站点结构拿不到时，根因常常是「目录/正文由 XHR 异步下发」——纯 HTTP 只有空壳，
渲染后 DOM 里也没有（实测创世：书籍页与 `/book/{id}/catalog` 渲染后都没有章节链接）。
此时正确做法不是继续猜选择器，而是**看它到底请求了哪个接口**（套路见 docs/RULES.md
「SPA 站点怎么找接口」）：监听 `page.on("request"/"response")`，
可选地先点一下「目录/展开」触发懒加载，再打印接口 URL、方法、POST 体与响应片段。

## 用法

    python tools/hunt_api.py --url "https://chuangshi.qq.com/detail/60754862"
    python tools/hunt_api.py --url "..." --click "text=目录" --wait 4000
    python tools/hunt_api.py --url "..." --filter "chapter|content|catalog"

## 依赖

可选依赖 playwright（与浏览器路由同一套）。`--headed` 才用真 Chrome；
默认走无头以免弹窗打扰，但部分站点在无头下会拒服 —— 那时加 `--headed`。
"""

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 只关心这两类响应：JSON 接口，以及路径里带 api/catalog/chapter 等关键词的
KW = re.compile(r"(api|ajax|catalog|chapter|content|toc|list|book|read|novel)",
                re.I)
# 明显是静态资源的，跳过（噪音）
SKIP = re.compile(r"\.(js|css|png|jpe?g|gif|webp|svg|woff2?|ttf|ico|mp4)(\?|$)",
                  re.I)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", required=True)
    ap.add_argument("--click", default=None, help="先点击这个选择器（如 text=目录）")
    ap.add_argument("--wait", type=int, default=3500, help="点完/加载后额外等待毫秒")
    ap.add_argument("--filter", default=None, help="只显示 URL 匹配该正则的请求")
    ap.add_argument("--limit", type=int, default=60, help="最多显示多少条")
    ap.add_argument("--headed", action="store_true", help="用真 Chrome + 有头（过 WAF）")
    ap.add_argument("--snippet", type=int, default=260, help="响应片段最多多少字符")
    ap.add_argument("--ignore-https-errors", action="store_true",
                    help="忽略证书错误（实测得间 idejian.com 的 HTTPS 证书已过期，"
                         "浏览器直接 ERR_CERT_DATE_INVALID，必须开这个才能进）")
    args = ap.parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("缺少 playwright：pip install playwright && python -m playwright install chromium",
              file=sys.stderr)
        return 2

    from noveldown.browser import DEFAULT_LAUNCH_ARGS

    flt = re.compile(args.filter) if args.filter else None
    seen = []
    lock = {"n": 0}

    with sync_playwright() as p:
        kwargs = {}
        if args.headed:
            kwargs = {"channel": "chrome", "headless": False,
                      "args": DEFAULT_LAUNCH_ARGS}
        browser = p.chromium.launch(**kwargs)
        ctx = browser.new_context(locale="zh-CN", timezone_id="Asia/Shanghai",
                                  viewport={"width": 1440, "height": 900},
                                  ignore_https_errors=args.ignore_https_errors)
        page = ctx.new_page()

        def on_response(resp):
            try:
                url = resp.url
                if SKIP.search(url):
                    return
                ctype = (resp.headers or {}).get("content-type", "")
                is_json = "json" in ctype.lower()
                if not (is_json or KW.search(url)):
                    return
                if flt and not flt.search(url):
                    return
                lock["n"] += 1
                rec = {"n": lock["n"], "status": resp.status,
                       "method": resp.request.method, "url": url,
                       "ctype": ctype.split(";")[0], "post": None, "body": None}
                if rec["method"] == "POST":
                    try:
                        rec["post"] = (resp.request.post_data or "")[:200]
                    except Exception:
                        pass
                if is_json:
                    try:
                        rec["body"] = json.dumps(resp.json(), ensure_ascii=False)
                    except Exception:
                        try:
                            rec["body"] = resp.text()
                        except Exception:
                            rec["body"] = None
                seen.append(rec)
            except Exception:
                pass

        page.on("response", on_response)
        page.goto(args.url, wait_until="domcontentloaded",
                  timeout=45000)
        page.wait_for_timeout(args.wait)
        if args.click:
            try:
                page.click(args.click, timeout=8000)
                print(f"[点击] {args.click} 成功，等待 {args.wait}ms")
                page.wait_for_timeout(args.wait)
            except Exception as e:
                print(f"[点击] {args.click} 失败（跳过）：{str(e)[:90]}")
        # 滚到底，触发懒加载
        try:
            page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(1500)
        except Exception:
            pass

        title = page.title()
        browser.close()

    print(f"\n页面标题：{title}")
    print(f"命中接口 {len(seen)} 条（最多显示 {args.limit}）")
    print("=" * 78)
    for r in seen[:args.limit]:
        print(f"\n[{r['n']}] {r['method']} {r['status']} {r['ctype']}")
        print(f"    {r['url'][:190]}")
        if r["post"]:
            print(f"    POST: {r['post']}")
        if r["body"]:
            b = re.sub(r"\s+", " ", r["body"])[:args.snippet]
            print(f"    BODY: {b}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
