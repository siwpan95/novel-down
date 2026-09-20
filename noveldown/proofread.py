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
duplicate_title  标题重复（目录页混入回显块的信号）
duplicate_body   正文文本完全重复（重复抓取/串页）
ad_residue       正文中疑似仍残留的站点广告行
short_chapter    字数显著低于全书中位数的章节（常见于站点未同步完的章节）
mojibake         编码异常（替换字符过多或汉字占比过低）
protected        受保护章节（预期被拦截，列出以便核对拦截是否生效）
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


def proofread(book) -> dict:
    """产出校对报告。"""
    ok = [c for c in book.chapters if c.status == STATUS_OK]
    chars = [c.char_count for c in ok if c.char_count > 0]
    med = median(chars) if chars else 0

    missing, out_of_order, dup_title, dup_body = [], [], [], []
    ad_residue, short_chapter, mojibake = [], [], []

    # 乱序检查：cid 数值应单调递增
    nums = []
    for c in book.chapters:
        m = re.search(r"(\d+)", c.cid or "")
        nums.append(int(m.group(1)) if m else None)
    prev = None
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

    # 标题重复
    seen_title = {}
    for c in book.chapters:
        key = (c.title or "").strip()
        if not key:
            continue
        if key in seen_title:
            dup_title.append({"index": c.index, "title": key,
                              "same_as": seen_title[key]})
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
        f"标题重复     : {c['duplicate_title']}",
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
    _section("标题重复", report["duplicate_title"],
             lambda x: f"#{x['index']} 「{x['title']}」与 #{x['same_as']} 相同")
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
