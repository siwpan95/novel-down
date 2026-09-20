#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
EPUB3 导出：**纯标准库 zipfile 手写**，不依赖 pandoc / ebooklib。

结构
----
mimetype                 （必须第一个写入且不压缩，否则阅读器拒收）
META-INF/container.xml
OEBPS/content.opf        包文档（manifest + spine）
OEBPS/nav.xhtml          EPUB3 导航（properties="nav"）
OEBPS/toc.ncx            EPUB2 兼容目录（老阅读器需要）
OEBPS/style.css
OEBPS/text/chapter_NNNN.xhtml
"""

import html as html_mod
import os
import uuid
import zipfile
from datetime import datetime, timezone

from ..freeguard import assert_no_protected, filter_exportable
from . import book_slug, ensure_dir, group_by_volume, register

CONTAINER_XML = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""

STYLE_CSS = """html { font-size: 100%; }
body { font-family: serif; line-height: 1.75; margin: 5% 6%; }
h1 { font-size: 1.5em; text-align: center; margin: 0 0 1.4em; }
h2 { font-size: 1.25em; margin: 1.6em 0 1em; border-bottom: 1px solid #ccc; padding-bottom: .3em; }
p { text-indent: 2em; margin: 0 0 .55em; }
.intro { color: #555; }
.vol { text-align: center; font-size: 1.2em; margin: 2em 0; }
"""

XHTML_TPL = """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="zh-CN" lang="zh-CN">
<head>
  <meta charset="utf-8"/>
  <title>{title}</title>
  <link rel="stylesheet" type="text/css" href="../style.css"/>
</head>
<body>
{body}
</body>
</html>
"""


def _x(s: str) -> str:
    return html_mod.escape(s or "", quote=False)


def _chapter_xhtml(ch, show_volume: bool) -> str:
    parts = []
    if show_volume and ch.volume:
        parts.append(f'<p class="vol">{_x(ch.volume)}</p>')
    parts.append(f"<h1>{_x(ch.title)}</h1>")
    parts += [f"<p>{_x(p)}</p>" for p in ch.paragraphs]
    return XHTML_TPL.format(title=_x(ch.title), body="\n".join(parts))


@register("epub")
def export(book, out_dir: str) -> str:
    assert_no_protected(book.chapters, context="epub 导出")
    ensure_dir(out_dir)
    path = os.path.join(out_dir, f"{book_slug(book)}.epub")

    chapters = filter_exportable(book.chapters)
    uid = f"urn:uuid:{uuid.uuid4()}"
    modified = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # ---- 章节文件 ----
    files = {}                      # href -> 内容
    manifest_items = []
    spine_refs = []
    nav_points = []
    prev_vol = None
    for i, ch in enumerate(chapters, 1):
        href = f"text/chapter_{i:04d}.xhtml"
        files[href] = _chapter_xhtml(ch, show_volume=(ch.volume != prev_vol))
        prev_vol = ch.volume
        manifest_items.append(
            f'<item id="c{i}" href="{href}" media-type="application/xhtml+xml"/>')
        spine_refs.append(f'<itemref idref="c{i}"/>')
        nav_points.append((i, ch.volume, ch.title, href))

    # ---- 简介页（可选）----
    if book.intro:
        files["text/intro.xhtml"] = XHTML_TPL.format(
            title="简介",
            body=(f"<h1>{_x(book.title)}</h1>"
                  f'<p class="intro">{_x(book.intro)}</p>'))
        manifest_items.insert(
            0, '<item id="intro" href="text/intro.xhtml" media-type="application/xhtml+xml"/>')
        spine_refs.insert(0, '<itemref idref="intro"/>')

    # ---- nav.xhtml ----
    # 采用平铺目录（不嵌套卷），兼容性最好：所有阅读器都能正确展开。
    nav_flat = "".join(
        f'<li><a href="{href}">{_x(title)}</a></li>'
        for _, _, title, href in nav_points)
    nav_xhtml = f"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="zh-CN" lang="zh-CN">
<head><meta charset="utf-8"/><title>目录</title></head>
<body>
<nav epub:type="toc" id="toc">
  <h1>目录</h1>
  <ol>{nav_flat}</ol>
</nav>
<nav epub:type="landmarks" id="landmarks" hidden="hidden">
  <ol><li><a epub:type="bodymatter" href="{nav_points[0][3] if nav_points else 'text/intro.xhtml'}">正文</a></li></ol>
</nav>
</body>
</html>
"""
    files["nav.xhtml"] = nav_xhtml

    # ---- toc.ncx（EPUB2 兼容）----
    ncx_points = "".join(
        f'<navPoint id="np{i}" playOrder="{i}">'
        f'<navLabel><text>{_x(title)}</text></navLabel>'
        f'<content src="{href}"/></navPoint>'
        for i, _, title, href in nav_points)
    files["toc.ncx"] = f"""<?xml version="1.0" encoding="utf-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
  <head>
    <meta name="dtb:uid" content="{uid}"/>
    <meta name="dtb:depth" content="1"/>
  </head>
  <docTitle><text>{_x(book.title)}</text></docTitle>
  <navMap>{ncx_points}</navMap>
</ncx>
"""
    files["style.css"] = STYLE_CSS

    # ---- content.opf ----
    opf = f"""<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid" xml:lang="zh-CN">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="bookid">{uid}</dc:identifier>
    <dc:title>{_x(book.title)}</dc:title>
    <dc:language>zh-CN</dc:language>
    <dc:creator>{_x(book.author or '佚名')}</dc:creator>
    <dc:source>{_x(book.url)}</dc:source>
    <dc:description>{_x(book.intro)}</dc:description>
    <meta property="dcterms:modified">{modified}</meta>
    <meta name="generator" content="novel-down"/>
  </metadata>
  <manifest>
    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
    <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>
    <item id="css" href="style.css" media-type="text/css"/>
    {"".join(manifest_items)}
  </manifest>
  <spine toc="ncx">
    {"".join(spine_refs)}
  </spine>
</package>
"""
    files["content.opf"] = opf

    # ---- 写盘 ----
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        # mimetype 必须第一个且不压缩
        zi = zipfile.ZipInfo("mimetype")
        zi.compress_type = zipfile.ZIP_STORED
        z.writestr(zi, "application/epub+zip")
        z.writestr("META-INF/container.xml", CONTAINER_XML)
        for name, content in files.items():
            z.writestr(f"OEBPS/{name}", content)
    return path
