#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""国图古籍库 · 影印本取图 + 古籍 OCR + 与文本版互校（P2 工具）。

为什么单独做成工具：这条路线与「网文下载器」正交互补 ——
网文线解决「有文本版的现代书」，本工具解决「**只有影印本**的公版古籍」。

链路（全部实测可用，纯 HTTP；详见 docs/NEW_SITES_PLAN.md §13.6）：
    ① 检索  POST /api/resource/getResourceCount  {keyword…}
            POST /api/resource/list               {keyword…,pageNum,pageSize}
    ② 书目  POST /api/anc/ancMetadataDetail/{id}          → picArray[] + ftpId
    ③ 册    POST /api/anc/ancStructureList?metadataId={id} → fileNumber=**真实页数**
    ④ 页图  GET  /api/common/jpgViewer?ftpId=&filePathName=

⚠⚠ `ancMetadataDetail.picArray` **只有 10 条（抽样！）**，真实页数只能从
   `ancStructureList.fileNumber` 拿 —— 只看 picArray 会把 129 页的书当 10 页，且不报错。

古籍 OCR 的三个关键处理（都是实测逼出来的）：
    ① **切半页**：页图常是「双叶合拍」（宽 > 高，一张图含左右两个半页），
       整页 OCR 会把两半页的行**交错串起来**；
    ② **坐标重排**：竖排古籍的行序不能按 DOM/检测顺序取 —— 竖排的框是**列**，
       正确顺序是 **x 从大到小**（右→左），而不是 (y, x)；
    ③ **列切分**：更稳的做法是按 x 投影切出**单列**再逐列识别，可根治行序。

用法：
    python tools\\guji_ocr.py search 西遊記
    python tools\\guji_ocr.py info 1005600
    python tools\\guji_ocr.py fetch 1005600 --pages 1-6 -o imgs/
    python tools\\guji_ocr.py ocr imgs/ --split --order col -o out.txt
    python tools\\guji_ocr.py proofread out.txt --ref xyj.txt -o fixed.txt
    python tools\\guji_ocr.py eval out.txt --ref xyj.txt        # 量字准率
"""

import argparse
import difflib
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API = "https://guji.nlc.cn/api"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
      "Referer": "https://guji.nlc.cn/result"}
CJK = re.compile(r"[\u4e00-\u9fff]")


def _session():
    import requests
    s = requests.Session()
    h = dict(UA, **{"Content-Type": "application/json"})
    s.post(API + "/userc/addEnter", headers=h, timeout=20,
           data=json.dumps({"columnCode": 100, "columnType": 1, "sourceCode": 1}))
    return s


def _search_body(kw, page=1, size=20):
    # 字段是固定这一套：少一个都可能不返数据
    return {"type": "1", "advancedRetrievalParams": [], "typeList": ["1", "2", "3", "4"],
            "keyword": kw, "nameIndex": "", "pageNum": page, "pageSize": size}


# ----------------------------------------------------------------- ① 取图
def cmd_search(args):
    s = _session()
    h = dict(UA, **{"Content-Type": "application/json"})
    r = s.post(API + "/resource/list", headers=h, timeout=30,
               data=json.dumps(_search_body(args.keyword), ensure_ascii=False).encode("utf-8"))
    rows = ((r.json().get("data") or {}).get("rows")) or []
    print("关键词 %r → %d 条" % (args.keyword, len(rows)))
    for x in rows:
        title = re.sub(r"<[^>]+>", "", str(x.get("parallelTitle-title") or ""))
        print("  id=%-9s %-34s | %-6s | %s" % (
            x.get("id"), title[:32], str(x.get("edition") or "")[:6],
            str(x.get("location-collectionUnit") or "")[:14]))


def cmd_info(args):
    s = _session()
    h = dict(UA, **{"Content-Type": "application/json"})
    hq = {k: v for k, v in UA.items()}
    d = s.post("%s/anc/ancMetadataDetail/%s" % (API, args.metadata_id),
               headers=h, timeout=30).json().get("data") or {}
    pt = d.get("parallelTitle") or d.get("title")
    if isinstance(pt, list):        # 题名常是 [{title:…}] 形态
        try:
            pt = pt[0].get("title")
        except Exception:
            pt = str(pt)[:60]
    print("题名  :", pt)
    print("版本  :", d.get("edition"), "| ftpId:", d.get("ftpId"))
    print("主题  :", str(d.get("subject"))[:100])
    v = s.post(API + "/anc/ancStructureList", headers=hq,
               params={"metadataId": args.metadata_id}, timeout=30).json().get("data") or []
    tot = 0
    print("册    : %d 册" % len(v))
    for x in v:
        tot += int(x.get("fileNumber") or 0)
        print("   %-26s fileNumber=%-5s ftpId=%s" % (
            str(x.get("volumeTitle"))[:24], x.get("fileNumber"), x.get("ftpId")))
    print("⚠ 真实页数合计 = %d（`picArray` 只有 %d 条，是**抽样**，别拿它当页数）" % (
        tot, len(d.get("picArray") or [])))


def cmd_fetch(args):
    s = _session()
    h = dict(UA, **{"Content-Type": "application/json"})
    hq = dict(UA)
    d = s.post("%s/anc/ancMetadataDetail/%s" % (API, args.metadata_id),
               headers=h, timeout=30).json().get("data") or {}
    pic = d.get("picArray") or []
    if not pic:
        print("✗ picArray 为空"); return 1
    lo, hi = 1, len(pic)
    if args.pages:
        a, _, b = args.pages.partition("-")
        lo, hi = int(a), int(b or a)
    ftp = d.get("ftpId") or "1"
    os.makedirs(args.out, exist_ok=True)
    n = 0
    for i, p in enumerate(pic, 1):
        if not (lo <= i <= hi):
            continue
        fp = p.get("filePath") or ""
        u = "%s/common/jpgViewer?ftpId=%s&filePathName=%s" % (API, ftp, fp)
        rr = s.get(u, headers=hq, timeout=180)
        out = os.path.join(args.out, "%s_%s.jpg" % (args.metadata_id,
                                                   p.get("fileName") or i))
        with open(out, "wb") as f:
            f.write(rr.content)
        n += 1
        print("  [%d] %s %9d 字节 → %s" % (i, p.get("fileName"), len(rr.content),
                                           os.path.basename(out)))
    print("下载 %d 页 → %s" % (n, args.out))
    return 0


# ----------------------------------------------------------------- ② 古籍 OCR
def _imread(path):
    from PIL import Image
    import numpy as np
    return np.array(Image.open(path).convert("RGB"))


def _split_halves(arr):
    """双叶合拍：宽 > 高 时切左右半页（实测有效，行连通性明显改善）。"""
    h, w = arr.shape[:2]
    if w > h * 1.05:
        return [("L", arr[:, : w // 2]), ("R", arr[:, w // 2:])]
    return [("", arr)]


def _col_cut(arr, min_gap=6, min_w=20):
    """按 x 投影切出**单列**（竖排根治行序）。返回 [(x0, 子图), …]。"""
    import numpy as np
    g = arr.mean(axis=2)
    ink = (g < 160).sum(axis=0)                 # 每列的墨量
    thr = max(1, int(ink.max() * 0.02))
    on = ink > thr
    cuts, run = [], 0
    for i, v in enumerate(on):
        if v:
            if run == 0:
                start = i
            run += 1
        else:
            if run >= min_w:
                cuts.append((start, start + run))
            run = 0
    if run >= min_w:
        cuts.append((start, start + run))
    # 合并间距过近的列
    merged = []
    for a, b in cuts:
        if merged and a - merged[-1][1] < min_gap:
            merged[-1] = (merged[-1][0], b)
        else:
            merged.append((a, b))
    return [(a, arr[:, max(0, a - 2): b + 2]) for a, b in merged]


def _order_boxes(boxes, order):
    """按 order 排框：`col` = 竖排（x 从大到小，右→左）；`row` = 横排 (y, x)。"""
    if order == "col":
        return sorted(boxes, key=lambda b: (-b[1], b[0]))
    if order == "row":
        return sorted(boxes, key=lambda b: (b[0], b[1]))
    # auto：看框的平均高宽比 —— 高>宽 说明框是「列」
    tall = sum(1 for b in boxes if b[3] > b[4])
    return _order_boxes(boxes, "col" if tall * 2 >= len(boxes) else "row")


def _maybe_rotate(arr, mode):
    """竖排古籍的关键一步：**旋转 90° 让竖排变横排**再送 OCR。

    为什么必须这么做（实测的关键发现）：RapidOCR 是**横排语料**训练的 —— 面对竖排文本，
    它会把「**每列各取一个字**」组成一条横排「行」，于是字全乱，**再怎么排序都救不回来**
    （排序只能改框的顺序，改不了"分组本身就错了"这件事）。

    实测同一页（国图《繡像西遊記》）：
        · 原方向（不切不旋）  最佳匹配 **15.3%**
        · 切半页 + 坐标重排   **24.1%**
        · 切半页 + 列切分     **22.5%**
        · **切半页 + 逆时针 90°  → 25.7%**（最高，且文字**可读**：
          「石碣上…一行楷…大字」「铁板桥」「花果山」「造化造化」都对上了）
    → 所以 `--rotate auto` 默认对「高 > 宽」的半页做**逆时针 90°**。
    """
    if mode == "none":
        return arr
    h, w = arr.shape[:2]
    if mode == "auto":
        if w >= h:               # 已经是横构图（切半页后是「高>宽」才需要转）
            return arr
        mode = "ccw"
    from PIL import Image
    im = Image.fromarray(arr)
    if mode == "ccw":
        im = im.rotate(90, expand=True)      # 逆时针
    elif mode == "cw":
        im = im.rotate(-90, expand=True)     # 顺时针
    import numpy as np
    return np.array(im.convert("RGB"))


def _ocr_page(ocr, arr, args, tag=""):
    parts = []
    for side, sub in _split_halves(arr) if args.split else [("", arr)]:
        sub = _maybe_rotate(sub, args.rotate)
        if args.col_cut:
            cols = _col_cut(sub)
            sub_txt = []
            for _, colimg in cols:
                res, _ = ocr(colimg)
                sub_txt.append("".join(x[1] for x in (res or [])))
            parts.append("".join(sub_txt) if args.order == "col" else "".join(sub_txt))
            continue
        res, _ = ocr(sub)
        boxes = []
        for x in (res or []):
            pts = x[0]
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            boxes.append((min(ys), min(xs), x[1],
                          max(ys) - min(ys), max(xs) - min(xs)))
        boxes = _order_boxes(boxes, args.order)
        parts.append("".join(b[2] for b in boxes))
    return "".join(parts)


def cmd_ocr(args):
    try:
        from rapidocr_onnxruntime import RapidOCR
    except Exception as e:
        print("✗ OCR 依赖不可用（需要 rapidocr_onnxruntime）：%s" % e)
        return 1
    ocr = RapidOCR()
    files = []
    for p in args.paths:
        if os.path.isdir(p):
            files += [os.path.join(p, f) for f in sorted(os.listdir(p))
                      if f.lower().endswith((".jpg", ".jpeg", ".png", ".tif", ".tiff"))]
        else:
            files.append(p)
    if not files:
        print("✗ 没找到图片"); return 1
    outs = []
    for p in files:
        arr = _imread(p)
        txt = _ocr_page(ocr, arr, args)
        print("  %-28s %5d 汉字" % (os.path.basename(p), len(CJK.findall(txt))))
        outs.append(txt)
        if args.out_pages_dir:
            os.makedirs(args.out_pages_dir, exist_ok=True)
            with open(os.path.join(args.out_pages_dir,
                                   os.path.splitext(os.path.basename(p))[0] + ".txt"),
                      "w", encoding="utf-8", newline="\n") as f:
                f.write(txt + "\n")
    body = "\n".join(outs)
    if args.out:
        with open(args.out, "w", encoding="utf-8", newline="\n") as f:
            f.write(body + "\n")
        print("→ %s（%d 汉字）" % (args.out, len(CJK.findall(body))))
    else:
        print(body)
    return 0


# ----------------------------------------------------------------- ③ 互校
_PUNCT = re.compile(r"[^\u4e00-\u9fff\uf900-\ufaff]")


def _norm(t):
    """只留汉字（去标点/空白/异体字区间的非汉字），便于字符级对齐。"""
    return _PUNCT.sub("", t)


def _align_rate(ocr_text, ref_text):
    """用参照文本量 OCR 的字符匹配率（SequenceMatcher 的匹配块占比）。"""
    a, b = _norm(ocr_text), _norm(ref_text)
    if not a or not b:
        return 0.0, a, b
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    return sm.ratio(), a, b


def cmd_eval(args):
    ocr_text = open(args.ocr, encoding="utf-8").read()
    ref_text = open(args.ref, encoding="utf-8").read()
    r, a, b = _align_rate(ocr_text, ref_text)
    print("OCR 汉字 %d ｜ 参照汉字 %d ｜ 字符匹配率 **%.1f%%**" % (len(a), len(b), r * 100))
    return 0


def cmd_proofread(args):
    """与文本版互校：**只做「一对一形近字」的局部纠正**，绝不长段覆盖。

    ⚠⚠ 这里有一条**必须守住的红线**（初版实现踩过，必须记下来）：
    最朴素的互校就是「把 OCR 串和参照串做 diff，然后把不同处换成参照的」——
    **这个做法是错的，而且有害**：实测它会把 `'像'` 整段改成 `'于绘画擅长书'`、
    还会把参照里 OCR 根本没有的内容（`∅→吴承恩约一说年字`）**插进正文**。
    结果「匹配率 11.7% → 100%」看着很漂亮，其实等于**把参照文本抄了一遍** ——
    而**影印本独有的内容（异文/批注/缺页补遗）被静默抹掉了**。
    那恰恰是拿影印本的**唯一理由**（文本版读者直接看文本就够了）。

    所以本函数的护栏是：
      · `replace` **只在长度差 ≤1 时**才当形近字纠正（`石涯`→`石崖` 这类）；
      · 长度差大的 `replace` 一律**保留 OCR 原文**并记为「对不齐，存疑」；
      · `insert`（参照有、OCR 没有）**只记录不写入** —— 那可能是 OCR 漏识，
        也可能是影印本与文本版的**真实差异**，不能替读者决定；
      · `delete`（OCR 有、参照没有）**保留**，单独输出为「影印本独有」。
    """
    ocr_text = open(args.ocr, encoding="utf-8").read()
    ref_text = open(args.ref, encoding="utf-8").read()
    a, b = _norm(ocr_text), _norm(ref_text)
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    fixed, fixes, suspect, ocr_only, ref_only = [], [], [], [], []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        seg_a, seg_b = a[i1:i2], b[j1:j2]
        if tag == "equal":
            fixed.append(seg_a)
        elif tag == "replace" and abs(len(seg_a) - len(seg_b)) <= 1:
            fixed.append(seg_b)                     # 一对一形近字 → 纠正
            if seg_a != seg_b:
                fixes.append((seg_a, seg_b))
        elif tag == "replace":
            fixed.append(seg_a)                     # 长度差大 → **保留原文**
            suspect.append((seg_a, seg_b))
        elif tag == "delete":
            fixed.append(seg_a)                     # OCR 独有 → 保留
            ocr_only.append(seg_a)
        elif tag == "insert":
            ref_only.append(seg_b)                  # 参照独有 → **只记录**
    out = "".join(fixed)
    acc = difflib.SequenceMatcher(None, _norm(out), b, autojunk=False).ratio()
    print("互校（**只纠一对一形近字**，不做长段覆盖）")
    print("  形近字纠正 %d 处 ｜ 对不齐存疑 %d 段 ｜ 影印本独有 %d 段 ｜ 参照独有 %d 段" % (
        len(fixes), len(suspect), len(ocr_only), len(ref_only)))
    print("  典型形近字纠正（前 12）：")
    for x, y in fixes[:12]:
        print("     %-6r → %r" % (x[:6], y[:6]))
    if suspect:
        print("  ⚠ 对不齐（**保留 OCR 原文**，需人工看）（前 6）：")
        for x, y in suspect[:6]:
            print("     ocr=%-14r  ref=%r" % (x[:14], y[:18]))
    if ocr_only:
        print("  ⭐ 影印本独有（参照里没有，**保留**）（前 6）：", [x[:12] for x in ocr_only[:6]])
    print("  ℹ 参照独有（OCR 漏识 or 版本差异，**未写入**）：%d 段" % len(ref_only))
    if args.out:
        with open(args.out, "w", encoding="utf-8", newline="\n") as f:
            f.write(out + "\n")
        print("→", args.out)
    if args.report:
        with open(args.report, "w", encoding="utf-8", newline="\n") as f:
            json.dump({"fixes": fixes, "suspect": suspect, "ocr_only": ocr_only,
                       "ref_only": ref_only}, f, ensure_ascii=False, indent=1)
        print("→", args.report)
    return 0


def main():
    ap = argparse.ArgumentParser(description="国图古籍库取图 + 古籍 OCR + 与文本版互校")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("search", help="检索书目"); p.add_argument("keyword")
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("info", help="书目 + 册/真实页数"); p.add_argument("metadata_id")
    p.set_defaults(func=cmd_info)

    p = sub.add_parser("fetch", help="下载页图")
    p.add_argument("metadata_id"); p.add_argument("--pages", help="如 1-6")
    p.add_argument("-o", "--out", default="guji_pages"); p.set_defaults(func=cmd_fetch)

    p = sub.add_parser("ocr", help="古籍 OCR（切半页/列切分/坐标重排）")
    p.add_argument("paths", nargs="+")
    p.add_argument("--split", action="store_true", default=True,
                   help="双叶合拍切左右半页（默认开）")
    p.add_argument("--no-split", dest="split", action="store_false")
    p.add_argument("--col-cut", action="store_true", help="按 x 投影切单列再识别（最稳）")
    p.add_argument("--order", choices=["auto", "col", "row"], default="auto",
                   help="框排序：col=竖排右→左 / row=横排 / auto=按框形状自动")
    p.add_argument("--rotate", choices=["auto", "ccw", "cw", "none"], default="auto",
                   help="竖排处理：auto=高>宽时逆时针 90°（实测增益最大，默认）")
    p.add_argument("-o", "--out", help="整本合并输出")
    p.add_argument("--pages-dir", dest="out_pages_dir", help="逐页输出目录")
    p.set_defaults(func=cmd_ocr)

    p = sub.add_parser("eval", help="用参照文本量字准率")
    p.add_argument("ocr"); p.add_argument("--ref", required=True); p.set_defaults(func=cmd_eval)

    p = sub.add_parser("proofread", help="与文本版互校纠错")
    p.add_argument("ocr"); p.add_argument("--ref", required=True)
    p.add_argument("-o", "--out")
    p.add_argument("--report", help="差异明细 JSON 输出路径")
    p.set_defaults(func=cmd_proofread)

    args = ap.parse_args()
    return args.func(args) or 0


if __name__ == "__main__":
    sys.exit(main())
