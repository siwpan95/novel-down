#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
产物终检：机械验证「导出物里没有受保护内容，也没有未还原的乱码」。

为什么要它
----------
免费章节约束里最难验的不是"我拦了没有"，而是"**发出去的东西干不干净**"。
人工翻一遍 TXT/EPUB 既不现实也不可靠，所以把下面这些检查做成 <1 秒可跑的脚本：

  1. **零请求**：受保护章节（locked/blocked）不得留下任何缓存与请求痕迹
  2. **零泄漏**：受保护章节的标题不得出现在产物**正文区**
  3. **零付费墙字样**：产物里不得出现「本章为VIP」「订阅后可阅读」「请先登录」…
  4. **零乱码残留**：字体反爬站点（番茄）的产物里 PUA 码位必须为 0
  5. **章节数自洽**：产物章节数 == state 里 status=ok 的章节数

> 关于"正文区"：书籍简介里可能**合法地**出现受保护章节名
> （实测纵横的 meta description 自带「最新章节：第699章 后会无期」）。
> 所以标题检查只扫「首个可导出章节标题之后」的区域，避免误报。

用法：
    python tools\\verify_artifacts.py "output\\<书名>_<站点>"
    python tools\\verify_artifacts.py "output\\<书名>_<站点>" --state output\\state\\x.json
退出码：0 通过；1 失败
"""

import argparse
import glob
import json
import os
import re
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from noveldown.constants import PAYWALL_MARKERS  # noqa: E402

PUA = re.compile(r"[\ue000-\uf8ff]")

# 「受保护章节标题泄漏」判据的**最小标题长度**。
# 短标题（尤其单字）在正常正文里会自然出现，拿它当判据必然误报 ——
# 实测仙人掌小说第 490 章标题就是一个字「番」。4 是经验下限。
MIN_LEAK_NEEDLE = 4


def pua_count(s: str) -> int:
    return len(PUA.findall(s or ""))


def read_artifact(path: str):
    """返回 (全文, 正文区文本)。

    正文区用于「受保护章节标题泄漏」检查，必须**排除**书籍简介/导航这类元信息区——
    实测踩过：纵横的 meta description 自带「最新章节：第699章 后会无期（大结局）」，
    站点自己的元信息里出现受保护章节名是正常的，不是泄漏。
    """
    if path.lower().endswith(".epub"):
        z = zipfile.ZipFile(path)
        names = z.namelist()
        full = "".join(z.read(n).decode("utf-8", "ignore")
                       for n in names
                       if n.endswith((".xhtml", ".html", ".opf", ".ncx")))
        # 正文区 = 只取章节文件（EPUB 里 intro/nav 的物理顺序在章节之后，
        # 用"锚点之后"的切法会把它们又算进来 —— 实测踩过这个假阳性）
        body = "".join(z.read(n).decode("utf-8", "ignore")
                       for n in names
                       if re.search(r"OEBPS/text/chapter_\d+\.xhtml$", n))
        return full, body
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    return text, None


def find_state(out_dir: str, explicit: str = None) -> str:
    if explicit:
        return explicit
    # out_dir 形如 output/<title>_<site> → state 在 ../state/<site>_<bid>.json
    base = os.path.basename(os.path.normpath(out_dir))
    parent = os.path.dirname(os.path.normpath(out_dir))
    cands = [p for p in glob.glob(os.path.join(parent, "state", "*.json"))
             if os.path.basename(p).startswith(base.split("_")[-1])]
    if len(cands) == 1:
        return cands[0]
    if not cands:
        raise SystemExit(f"找不到 state 文件（{parent}/state/ 下无匹配 {base}）。请用 --state 指定。")
    raise SystemExit(f"state 文件有多个候选，请用 --state 指定：{cands}")


def main():
    ap = argparse.ArgumentParser(description="产物终检")
    ap.add_argument("out_dir", help="导出目录，如 output/<书名>_<站点>")
    ap.add_argument("--state", default=None, help="state JSON（默认自动推断）")
    args = ap.parse_args()

    out_dir = os.path.abspath(args.out_dir)
    if not os.path.isdir(out_dir):
        raise SystemExit(f"目录不存在：{out_dir}")
    state_path = find_state(out_dir, args.state)
    with open(state_path, "r", encoding="utf-8") as f:
        state = json.load(f)

    chapters = state.get("chapters", [])
    ok = [c for c in chapters if c.get("status") == "ok"]
    protected = [c for c in chapters if c.get("status") in ("locked", "blocked")]

    print("=" * 68)
    print(f"产物终检 · {state.get('title','?')}  [{state.get('site')}/{state.get('book_id')}]")
    print("=" * 68)
    print(f"state      : {state_path}")
    print(f"目录       : {out_dir}")
    print(f"章节状态   : ok={len(ok)} protected={len(protected)} 总={len(chapters)}")
    print()

    artifacts = sorted(glob.glob(os.path.join(out_dir, "*")))
    artifacts = [p for p in artifacts
                 if p.lower().endswith((".txt", ".md", ".epub", ".html"))]
    if not artifacts:
        raise SystemExit("目录里没有导出物")

    fails = []

    # ---- 1. 零请求：受保护章节不得有缓存/请求痕迹 ----
    site, bid = state.get("site", ""), state.get("book_id", "")
    # ⚠ 必须**复用引擎的 slug 规则**（`slug_of`），别在这里自己拼 `f"{site}_{bid}"`：
    #   文库型站点的 book_id 是**路径**（虚阁网 `gdwx/hlm`），未 slug 化会带上 `/`
    #   → 拼出 `cache/xuges.com_gdwx/hlm` 这种不存在的路径 → 「缓存 0 个」误报 FAIL。
    #   实测 2026-09-21 就是踩了这个。同一事实只写一处，才不会两边跑偏。
    from noveldown.state import slug_of
    cache_dir = os.path.join(os.path.dirname(os.path.dirname(state_path)), "cache",
                             slug_of(site, bid))
    locked_cids = {c["cid"] for c in protected if c.get("cid")}
    cached = {os.path.splitext(os.path.basename(p))[0]
              for p in glob.glob(os.path.join(cache_dir, "*.json"))}
    hit = cached & locked_cids
    print(f"[1] 零请求  : locked/blocked 章节的缓存痕迹 {len(hit)}（缓存共 {len(cached)} 个）")
    if hit:
        fails.append(f"受保护章节留下了缓存/请求痕迹：{sorted(hit)[:5]}")
    if len(cached) != len(ok):
        fails.append(f"缓存数 {len(cached)} 与 ok 章节数 {len(ok)} 不一致")

    # ---- 正文区锚点 ----
    body_anchor = ok[0]["title"] if ok else None

    for path in artifacts:
        name = os.path.basename(path)
        text, body = read_artifact(path)

        # ---- 4. 零乱码残留 ----
        n_pua = pua_count(text)
        if n_pua:
            fails.append(f"{name}: 残留 {n_pua} 个 PUA 码位（字体反爬未还原）")

        # ---- 3. 零付费墙字样 ----
        hits = sorted({m for m in PAYWALL_MARKERS if m in text})

        # ---- 2. 零泄漏（只扫正文区）----
        if body is None:                      # txt / md：锚点之后的区域
            body = text
            if body_anchor and body_anchor in text:
                body = text[text.find(body_anchor):]
        leaked = [c["title"] for c in protected
                  if c.get("title") and len(c["title"].strip()) >= MIN_LEAK_NEEDLE
                  and c["title"] in body]
        # 同名去重：若该标题同时属于某个 ok 章节，则不算泄漏
        ok_titles = {c["title"] for c in ok}
        leaked = [t for t in leaked if t not in ok_titles]
        # ⚠ 太短的标题**不能当泄漏判据**（v0.8.15，实测仙人掌小说踩到）：
        #   该书第 490 章的标题就是**一个字**「番」，而「番」在正常正文里
        #   到处都可能出现（番外/一番/番茄…）→ 拿它去正文里搜是**必然误报**。
        #   同一条道理此前在校对报告里也踩过：**短串不是可靠判据**。
        #   这里显式**列出被跳过的短标题**，不静默忽略（否则等于悄悄放宽了判据）。
        skipped = [c["title"] for c in protected
                   if c.get("title") and 0 < len(c["title"].strip()) < MIN_LEAK_NEEDLE]

        status = "OK"
        if hits or leaked or n_pua:
            status = "FAIL"
            if hits:
                fails.append(f"{name}: 出现付费墙字样 {hits}")
            if leaked:
                fails.append(f"{name}: 正文区出现受保护章节标题 {leaked[:3]}")
        print(f"[2] {name:44} PUA={n_pua:5d} 付费墙={len(hits)} 泄漏={len(leaked)}  {status}")
        if skipped:
            print(f"    注：{len(skipped)} 个受保护章节标题短于 {MIN_LEAK_NEEDLE} 字，"
                  f"不作泄漏判据（短串必然误报）：{skipped[:5]}")

    # ---- 5. 章节数自洽 ----
    txt = next((p for p in artifacts if p.lower().endswith(".txt")), None)
    if txt:
        head = read_artifact(txt)[0][:400]
        m = re.search(r"章节：(\d+)", head)
        if m and int(m.group(1)) != len(ok):
            fails.append(f"TXT 声明章节数 {m.group(1)} != state 的 ok 章节数 {len(ok)}")

    # EPUB 章节文件数
    epub = next((p for p in artifacts if p.lower().endswith(".epub")), None)
    if epub:
        z = zipfile.ZipFile(epub)
        n_ch = len([n for n in z.namelist()
                    if n.startswith("OEBPS/text/chapter_")])
        print(f"[5] EPUB 章节文件数 {n_ch}（应 = {len(ok)}）")
        if n_ch != len(ok):
            fails.append(f"EPUB 章节文件数 {n_ch} != ok 章节数 {len(ok)}")

    print()
    if fails:
        print(f"结果：FAIL —— {len(fails)} 项")
        for x in fails:
            print(f"  · {x}")
        return 1
    print("结果：PASS —— 受保护内容零请求、零泄漏；产物无付费墙字样、无乱码残留")
    return 0


if __name__ == "__main__":
    sys.exit(main())
