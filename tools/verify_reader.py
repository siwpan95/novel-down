#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
用真实浏览器（Playwright + Chromium）验证单文件 HTML 阅读器是否真的可用。

这不是「打开文件看看」——脚本会实际操作 UI 并断言结果：
  目录条数 / 点击跳转 / 键盘翻页 / 搜索过滤 / 滚动 / 进度记忆（reload 后仍在原章）/ 主题切换
最后输出截图，供人眼复核。

用法：
    F:\\Python314\\python.exe tools\\verify_reader.py "output\\某本书\\某本书.html"
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    html_path = os.path.abspath(sys.argv[1])
    if not os.path.exists(html_path):
        print(f"文件不存在：{html_path}")
        return 2

    from playwright.sync_api import sync_playwright

    url = "file:///" + html_path.replace("\\", "/")
    shot_dir = os.path.join(ROOT, "output", "_reader_shots")
    os.makedirs(shot_dir, exist_ok=True)
    ok = True

    def check(name, cond, detail=""):
        nonlocal ok
        mark = "PASS" if cond else "FAIL"
        if not cond:
            ok = False
        print(f"  [{mark}] {name}" + (f"  {detail}" if detail else ""))

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)

        page.goto(url, wait_until="load")
        page.wait_for_timeout(300)

        print("\n=== 1. 基本渲染 ===")
        title = page.title()
        check("页面标题正确", "离线" in title or "阅读" in title, title)
        h1 = page.inner_text("#bk-title").strip()
        check("书名已渲染", len(h1) > 0, h1)
        check("作者栏已渲染", len(page.inner_text("#bk-author")) > 0)

        print("\n=== 2. 目录 ===")
        n_toc = page.eval_on_selector_all("#toc a", "els => els.length")
        n_meta = page.evaluate("JSON.parse(document.getElementById('book').textContent).chapters.length")
        check("目录条数与内嵌章节数一致", n_toc == n_meta, f"toc={n_toc} data={n_meta}")
        check("目录非空", n_toc > 0, str(n_toc))
        check("章节标题已渲染", page.inner_text("#toc a >> nth=0").strip() != "")

        print("\n=== 3. 当前章与正文 ===")
        check("位置指示正确", page.inner_text("#pos").replace(" ", "") == f"1/{n_meta}",
              page.inner_text("#pos"))
        first_body = page.inner_text("#art")
        check("正文有内容", len(first_body) > 200, f"{len(first_body)} 字符")
        check("正文含段首缩进样式段", page.eval_on_selector_all("#art p", "e => e.length") > 3)

        print("\n=== 4. 翻页（按钮 + 键盘）===")
        page.click("#nextTop")
        page.wait_for_timeout(200)
        check("按钮翻页到第 2 章", page.inner_text("#pos").replace(" ", "") == f"2/{n_meta}",
              page.inner_text("#pos"))
        body2 = page.inner_text("#art")
        check("正文已切换", body2 != first_body)
        check("目录高亮同步", page.eval_on_selector_all(
            "#toc a.cur", "e => e.length === 1 && e[0].dataset.i === '1'"))

        page.keyboard.press("ArrowRight")
        page.wait_for_timeout(200)
        check("键盘→翻到第 3 章", page.inner_text("#pos").replace(" ", "") == f"3/{n_meta}",
              page.inner_text("#pos"))
        page.keyboard.press("ArrowLeft")
        page.wait_for_timeout(200)
        check("键盘←回到第 2 章", page.inner_text("#pos").replace(" ", "") == f"2/{n_meta}")

        page.keyboard.press("End")
        page.wait_for_timeout(200)
        check("End 跳末章", page.inner_text("#pos").replace(" ", "") == f"{n_meta}/{n_meta}")
        check("末章时下一章按钮禁用", page.is_disabled("#nextTop"))
        page.keyboard.press("Home")
        page.wait_for_timeout(200)
        check("Home 回首章", page.inner_text("#pos").replace(" ", "") == f"1/{n_meta}")
        check("首章时上一章按钮禁用", page.is_disabled("#prevTop"))

        print("\n=== 5. 目录点击跳转 ===")
        target = min(4, n_meta - 1)
        page.click(f'#toc a[data-i="{target}"]')
        page.wait_for_timeout(250)
        check(f"点击目录跳到第 {target + 1} 章",
              page.inner_text("#pos").replace(" ", "") == f"{target + 1}/{n_meta}",
              page.inner_text("#pos"))

        print("\n=== 6. 章节搜索过滤 ===")
        kw = page.evaluate(
            "JSON.parse(document.getElementById('book').textContent)"
            f".chapters[{min(2, n_meta - 1)}].t.substring(0, 3)")
        page.fill("#q", kw)
        page.wait_for_timeout(250)
        visible = page.eval_on_selector_all(
            "#toc a", "els => els.filter(e => e.style.display !== 'none').length")
        check("搜索后目录被过滤", 0 < visible < n_meta, f"关键词「{kw}」→ {visible}/{n_meta}")
        page.fill("#q", "")
        page.wait_for_timeout(250)
        visible2 = page.eval_on_selector_all(
            "#toc a", "els => els.filter(e => e.style.display !== 'none').length")
        check("清空搜索后恢复", visible2 == n_meta, str(visible2))

        print("\n=== 7. 进度记忆（reload 后仍在原章）===")
        page.click(f'#toc a[data-i="{target}"]')
        page.wait_for_timeout(400)
        before = page.inner_text("#pos")
        page.reload(wait_until="load")
        page.wait_for_timeout(400)
        after = page.inner_text("#pos")
        check("重开后回到上次章节", before == after, f"{before} → {after}")
        ls = page.evaluate("Object.keys(localStorage).filter(k=>k.indexOf('noveldown:')===0).length")
        check("localStorage 已写入进度", ls >= 1, f"{ls} 个键")

        print("\n=== 8. 阅读设置 ===")
        page.click("#cfgBtn")
        page.wait_for_timeout(150)
        check("设置面板打开", page.eval_on_selector("#cfg", "e => e.classList.contains('on')"))
        page.click('#cfg .themes button[data-t="dark"]')
        page.wait_for_timeout(200)
        check("夜间主题生效",
              page.eval_on_selector("html", "e => e.getAttribute('data-theme')") == "dark")
        page.eval_on_selector("#fs", "e => { e.value = 22; e.dispatchEvent(new Event('input')); }")
        page.wait_for_timeout(200)
        fs = page.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--fs')")
        check("字号调节生效", "22" in fs, fs)
        page.screenshot(path=os.path.join(shot_dir, "reader_dark.png"), full_page=False)
        page.click('#cfg .themes button[data-t="light"]')
        page.wait_for_timeout(200)
        page.click("#cfgBtn")
        page.wait_for_timeout(150)

        print("\n=== 9. 侧栏折叠 ===")
        page.click("#toggle")
        page.wait_for_timeout(400)
        hidden = page.eval_on_selector("#side", "e => e.classList.contains('hide')")
        check("目录可折叠", hidden)
        page.click("#toggle")
        page.wait_for_timeout(400)

        print("\n=== 10. 控制台错误 ===")
        real_errors = [e for e in errors if "favicon" not in e.lower()]
        check("无 JS 运行时错误", len(real_errors) == 0, str(real_errors[:3]))

        page.screenshot(path=os.path.join(shot_dir, "reader_light.png"), full_page=False)

        print("\n=== 11. 移动端抽屉 ===")
        page.set_viewport_size({"width": 390, "height": 844})
        page.wait_for_timeout(400)
        check("窄屏默认收起目录",
              page.eval_on_selector("#side", "e => e.classList.contains('hide')"))
        page.click("#toggle")
        page.wait_for_timeout(400)
        check("点 ☰ 展开抽屉",
              not page.eval_on_selector("#side", "e => e.classList.contains('hide')"))
        check("抽屉展开时遮罩出现",
              page.eval_on_selector("#mask", "e => e.classList.contains('on')"))
        page.screenshot(path=os.path.join(shot_dir, "reader_mobile_drawer.png"), full_page=False)
        page.click(f'#toc a[data-i="{min(3, n_meta - 1)}"]')
        page.wait_for_timeout(400)
        check("选章节后抽屉自动收起",
              page.eval_on_selector("#side", "e => e.classList.contains('hide')"))
        check("遮罩同时消失",
              not page.eval_on_selector("#mask", "e => e.classList.contains('on')"))
        page.screenshot(path=os.path.join(shot_dir, "reader_mobile.png"), full_page=False)

        print("\n=== 12. 再次检查控制台 ===")
        real_errors2 = [e for e in errors if "favicon" not in e.lower()]
        check("全程无 JS 运行时错误", len(real_errors2) == 0, str(real_errors2[:3]))

        browser.close()

    print(f"\n截图输出：{shot_dir}")
    print("=" * 62)
    print("阅读器验证：" + ("全部通过 ✅" if ok else "存在失败项 ❌"))
    print("=" * 62)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
