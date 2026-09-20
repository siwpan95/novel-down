#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成 README 用的阅读器演示截图（docs/screenshot.png）。

**为什么用自撰文本**：截图会随仓库公开。若用手头抓来的真实小说截图，
等于把第三方正文发布出去。所以这里用一段明确标注为示例的自撰占位文字。

用法：
    python tools\\make_screenshot.py
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# ---- 自撰示例文本（非任何真实作品）----
PARAS = [
    "这是一段用于演示的占位正文，不摘自任何真实作品。",
    "晨雾还没散，石阶上已经落了一层薄霜。他把手拢在袖中，沿着山道慢慢往下走，"
    "每走十几步就停下来看一眼脚下的路。",
    "“你确定是这条路？”身后的人问。他没有回头，只是把下巴往东南方向抬了抬——"
    "那里有一道极细的炊烟，在灰白的天空里几乎看不见。",
    "两人又走了半个时辰。路旁的石碑断成两截，上面刻的字被风雨磨得只剩三个偏旁。"
    "他伸手摸了一遍，忽然笑了一声。",
    "“笑什么？”",
    "“没什么。”他收回手，“只是想起来，二十年前我在这里迷过路。”",
    "风从峡谷口灌进来，卷着细碎的沙。远处传来一声闷响，像是有什么重物落进了水里。",
    "他停下脚步，侧耳听了很久，才继续往前走。山道在前方拐了个弯，"
    "再往前就看不到任何灯火了。",
]

CHAPTERS = [
    ("第一章 石阶上的霜", "正文卷"),
    ("第二章 断碑", "正文卷"),
    ("第三章 峡谷口的风", "正文卷"),
    ("第四章 一个旧名字", "正文卷"),
    ("第五章 二十年前的岔路", "正文卷"),
    ("第六章 炊烟的方向", "正文卷"),
    ("第七章 雨来之前", "正文卷"),
    ("第八章 山道尽头", "正文卷"),
    ("第九章 第二个人", "第二卷"),
    ("第十章 空屋", "第二卷"),
    ("第十一章 灯", "第二卷"),
    ("第十二章 石阶上的霜（下）", "第二卷"),
]

INTRO = ("示例书籍：本页内容为脚本自撰的占位文字，仅用于演示阅读器界面，"
         "不包含任何第三方作品正文。")


def build_book():
    from noveldown.models import Book, Chapter, STATUS_OK
    book = Book(site="demo", book_id="demo",
                url="https://example.invalid/demo/",
                title="示例书籍 · 阅读器演示", author="novel-down 自撰占位文本",
                intro=INTRO)
    for i, (title, vol) in enumerate(CHAPTERS, 1):
        book.chapters.append(Chapter(
            index=i, title=title, url=f"https://example.invalid/demo/{i}.html",
            cid=str(i), volume=vol, status=STATUS_OK,
            paragraphs=list(PARAS)))
    return book


def main():
    from noveldown.exporters.htmlreader import export as export_html

    shot_dir = os.path.join(ROOT, "docs")
    os.makedirs(shot_dir, exist_ok=True)
    tmp = os.path.join(ROOT, ".screenshot_tmp")
    os.makedirs(tmp, exist_ok=True)

    book = build_book()
    html_path = export_html(book, tmp)
    print(f"演示页已生成：{html_path}")

    from playwright.sync_api import sync_playwright
    url = "file:///" + html_path.replace("\\", "/")
    out = os.path.join(shot_dir, "screenshot.png")

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 820},
                                device_scale_factor=2)   # 2x 便于高 DPI 显示
        page.goto(url, wait_until="load")
        page.wait_for_timeout(400)
        # 跳到第 3 章，内容更饱满
        page.click('#toc a[data-i="2"]')
        page.wait_for_timeout(400)
        page.screenshot(path=out, full_page=False)
        # 顺手出一张移动端
        page.set_viewport_size({"width": 390, "height": 780})
        page.wait_for_timeout(400)
        page.screenshot(path=os.path.join(shot_dir, "screenshot_mobile.png"))
        browser.close()

    import shutil
    shutil.rmtree(tmp, ignore_errors=True)
    print(f"截图已写出：{out}")
    print(f"               {os.path.join(shot_dir, 'screenshot_mobile.png')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
