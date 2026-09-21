#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
校对：对抓取结果做质量体检。

[借鉴来源] ma6254/FictionDown（GPL-3.0）—— 该项目自述解决「章节缺失和章节顺序错乱」，
本项目借鉴其**检查维度**（缺失 / 乱序 / 重复 / 广告残留），检查逻辑为本项目自研。
其「正版与盗版站点互补补齐 VIP 章节」的核心流程已**排除**（违反本项目的免费章节约束）。

检查项
------
missing          抓取失败或正文过短的章节
out_of_order     章节号非单调递增（目录归一化失效的信号）
duplicate_title  标题同名**且正文也相同**（目录页混入回显块 / 重复抓取 —— 真问题）
title_clash      标题同名但**正文不同**（多为站点自身命名撞车，非抓取缺陷，见下）
duplicate_body   正文文本完全重复（重复抓取/串页）
ad_residue       正文中疑似仍残留的站点广告行
short_chapter    字数显著低于全书中位数的章节（常见于站点未同步完的章节）
mojibake         编码异常（替换字符过多或汉字占比过低）
protected        受保护章节（预期被拦截，列出以便核对拦截是否生效）

⚠ 为什么「标题同名」要再判一次正文（v0.8.13，红袖实测）：
  《重生换宗…》里 #313 与 #315 都叫「番外：归家」，但两个 cid 不同、
  正文 169 / 182 字、重合度 **1%** —— 是站点自己有两个番外撞了名。
  若只比标题就报「标题重复」，最坏后果是让人去**去重**，
  从而删掉一章真内容。所以定性必须带上正文：只有"同名 + 同文"才算真重复。
"""

import hashlib
import re
from statistics import median

from .models import STATUS_OK, STATUS_PENDING

# 广告残留特征（比抓取时的 ad_patterns 更保守，只报高置信度词）
AD_HINTS = ("笔趣阁", "最新网址", "请记住本站", "手机版阅读",
            "天才一秒记住", "www.", "http://", "https://",
            "本章未完", "点击下一页", "推荐票", "求收藏", "求订阅")

CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")


def _body_hash(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8", "ignore")).hexdigest()[:16]


def _mojibake_ratio(text: str) -> float:
    """汉字占非空白字符的比例。正常中文小说应 > 0.5。"""
    body = re.sub(r"\s", "", text)
    if not body:
        return 0.0
    return len(CJK_RE.findall(body)) / len(body)


def _same_body(a, b) -> bool:
    """两章正文是否一致；任一侧取不到正文（未抓/受保护/空）时返回 None。

    `None` 不等于「不同」—— `--limit` 限流抓取时同名的两章可能只有一章抓了，
    这时说「站点命名撞车」是无依据的，报告里按「未定」呈现。
    """
    if a is None or b is None:
        return None
    if not (a.paragraphs and b.paragraphs):
        return None
    return _body_hash(a.text) == _body_hash(b.text)


def proofread(book) -> dict:
    """产出校对报告。"""
    ok = [c for c in book.chapters if c.status == STATUS_OK]
    chars = [c.char_count for c in ok if c.char_count > 0]
    med = median(chars) if chars else 0

    missing, out_of_order, dup_title, dup_body = [], [], [], []
    title_clash = []
    ad_residue, short_chapter, mojibake = [], [], []

    # 乱序检查：cid 数值应单调递增。
    # 例外：catalog.sort=document_order 的站点（雪花 ID，如番茄/七猫）
    # 章节 ID 与阅读顺序无关，检查单调性只会误报 —— 直接跳过。
    cid_ordered = getattr(book, "catalog_sort", "cid_numeric_asc") != "document_order"
    nums = []
    for c in book.chapters:
        m = re.search(r"(\d+)", c.cid or "")
        nums.append(int(m.group(1)) if m else None)
    prev = None
    if cid_ordered:
        for c, n in zip(book.chapters, nums):
            if n is None:
                continue
            if prev is not None and n < prev:
                out_of_order.append({"index": c.index, "cid": c.cid,
                                     "title": c.title, "prev_cid": prev})
            prev = n

    # 缺失（抓取失败/正文异常）与「未抓取」必须分开：
    # --limit 限流抓取时，未抓章节是预期状态，不该判为「缺失」。
    missing, pending = [], []
    for c in book.chapters:
        if c.is_protected:
            continue
        if c.status == STATUS_PENDING:
            pending.append({"index": c.index, "title": c.title})
        elif c.status != STATUS_OK:
            missing.append({"index": c.index, "title": c.title,
                            "status": c.status, "note": c.note})

    # 标题同名：**必须再判「正文是否也相同」才能定性**。
    #
    # 实测（红袖《重生换宗…》v0.8.13）：两个不同 cid 的章节都叫「番外：归家」，
    # 但正文 169 / 182 字、重合度只有 1% —— 是**站点自己的命名**（同一本书里
    # 两个番外撞名），不是抓取缺陷。早先只比标题，会把它报成「标题重复」，
    # 让人以为抓错了、甚至去「去重」而**误删一章真内容**。
    #
    # 故按正文再分两类：正文也相同 = 真重复（回显块/重复抓取）；
    # 正文不同 = 站点命名撞车，单列 `title_clash`，不计入阻断项。
    by_index = {c.index: c for c in book.chapters}
    seen_title = {}
    for c in book.chapters:
        key = (c.title or "").strip()
        if not key:
            continue
        if key in seen_title:
            rec = {"index": c.index, "title": key, "same_as": seen_title[key]}
            rec["body_same"] = _same_body(by_index.get(seen_title[key]), c)
            (dup_title if rec["body_same"] is True else title_clash).append(rec)
        else:
            seen_title[key] = c.index

    # 正文重复 + 广告残留 + 乱码 + 过短
    seen_body = {}
    for c in ok:
        if c.paragraphs:
            h = _body_hash(c.text)
            if h in seen_body:
                dup_body.append({"index": c.index, "title": c.title,
                                 "same_as": seen_body[h]})
            else:
                seen_body[h] = c.index

            hits = sorted({kw for kw in AD_HINTS if kw in c.text})
            if hits:
                ad_residue.append({"index": c.index, "title": c.title,
                                   "hits": hits})

            ratio = _mojibake_ratio(c.text)
            if ratio < 0.35:
                mojibake.append({"index": c.index, "title": c.title,
                                 "cjk_ratio": round(ratio, 3)})

        if med and c.char_count < max(50, med * 0.15):
            short_chapter.append({"index": c.index, "title": c.title,
                                  "chars": c.char_count, "median": int(med)})

    protected = [{"index": c.index, "title": c.title, "status": c.status,
                  "note": c.note} for c in book.chapters if c.is_protected]

    counts = {
        "chapters_total": len(book.chapters),
        "ok": len(ok),
        "protected": len(protected),
        "not_fetched": len(pending),
        "missing": len(missing),
        "out_of_order": len(out_of_order),
        "duplicate_title": len(dup_title),
        "title_clash": len(title_clash),
        "duplicate_body": len(dup_body),
        "ad_residue": len(ad_residue),
        "short_chapter": len(short_chapter),
        "mojibake": len(mojibake),
        "total_chars": book.total_chars,
        "median_chars": int(med),
    }
    # 只有「抓取失败/乱序/正文重复」才是阻断性问题；
    # 「未抓取」在限流抓取时属预期，单列不判负。
    blocking = counts["missing"] + counts["out_of_order"] + counts["duplicate_body"]
    counts["blocking_issues"] = blocking
    counts["verdict"] = "PASS" if blocking == 0 else "WARN"

    return {
        "book": {"site": book.site, "book_id": book.book_id,
                 "title": book.title, "author": book.author, "url": book.url},
        "counts": counts,
        "pending": pending,
        "missing": missing,
        "out_of_order": out_of_order,
        "duplicate_title": dup_title,
        "title_clash": title_clash,
        "duplicate_body": dup_body,
        "ad_residue": ad_residue,
        "short_chapter": short_chapter,
        "mojibake": mojibake,
        "protected": protected,
    }


def format_report(report: dict, max_items: int = 8) -> str:
    """把校对报告渲染为可读文本。"""
    c = report["counts"]
    b = report["book"]
    lines = [
        "=" * 62,
        f"校对报告 · {b['title'] or '(无标题)'}  [{b['site']}/{b['book_id']}]",
        "=" * 62,
        f"结论         : {c['verdict']}" +
        ("" if c["verdict"] == "PASS" else
         f"（{c['blocking_issues']} 项需关注）"),
        f"章节总数     : {c['chapters_total']}",
        f"抓取成功     : {c['ok']}",
        f"未抓取       : {c['not_fetched']}（限流抓取时属预期）",
        f"受保护拦截   : {c['protected']}",
        f"缺失/失败    : {c['missing']}",
        f"乱序         : {c['out_of_order']}",
        f"标题重复     : {c['duplicate_title']}（同名**且**正文相同）",
        f"标题同名     : {c['title_clash']}（同名但正文不同 → 多为站点命名，非抓取缺陷）",
        f"正文重复     : {c['duplicate_body']}",
        f"广告残留     : {c['ad_residue']}",
        f"异常短章     : {c['short_chapter']}（中位字数 {c['median_chars']}）",
        f"编码异常     : {c['mojibake']}",
        f"总字数       : {c['total_chars']}",
    ]

    def _section(title, items, fmt):
        if not items:
            return
        lines.append("-" * 62)
        lines.append(f"{title}（{len(items)}）")
        for it in items[:max_items]:
            lines.append("  · " + fmt(it))
        if len(items) > max_items:
            lines.append(f"  … 其余 {len(items) - max_items} 项见报告 JSON")

    _section("受保护章节（预期拦截，不应出现在正文中）", report["protected"],
             lambda x: f"#{x['index']} {x['title']} [{x['status']}] {x['note']}")
    _section("缺失 / 失败章节", report["missing"],
             lambda x: f"#{x['index']} {x['title']} [{x['status']}] {x['note']}")
    _section("乱序", report["out_of_order"],
             lambda x: f"#{x['index']} cid={x['cid']} < 前章 cid={x['prev_cid']}")
    _section("标题重复（同名 + 正文相同 → 需查回显块/重复抓取）",
             report["duplicate_title"],
             lambda x: f"#{x['index']} 「{x['title']}」与 #{x['same_as']} 相同")
    _section("标题同名但正文不同（站点命名，**不是**抓取缺陷，不清除）",
             report["title_clash"],
             lambda x: f"#{x['index']} 「{x['title']}」与 #{x['same_as']} 同名，"
                       + ("正文已确认不同" if x.get("body_same") is False
                          else "正文未取到，无法判定"))
    _section("正文重复", report["duplicate_body"],
             lambda x: f"#{x['index']} 与 #{x['same_as']} 正文完全一致")
    _section("广告残留", report["ad_residue"],
             lambda x: f"#{x['index']} {x['title']} → {x['hits']}")
    _section("异常短章", report["short_chapter"],
             lambda x: f"#{x['index']} {x['title']} {x['chars']}字（中位 {x['median']}）")
    _section("编码异常", report["mojibake"],
             lambda x: f"#{x['index']} {x['title']} 汉字占比 {x['cjk_ratio']}")
    lines.append("=" * 62)
    return "\n".join(lines)
