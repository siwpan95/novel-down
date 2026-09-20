#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""抽样验证批量生成的镜像族规则（用**真实引擎**跑，不看"像不像"）。

## 为什么必须有这一步

`scan_mirrors.py --phase deep` 用的是工具自己的探测逻辑；
而真正抓取走的是引擎（`noveldown.engine`）的规则解释器。
两者**不是同一套代码**，实测出现过：探测工具认为「可做」，但生成的规则在引擎里
只抓到 1 章、或 `url_pattern` 把 `https` 当成了书籍 ID。
所以每条落地的族规则都要**用引擎实测一遍**，不能靠"看起来对"。

## 判据

对每条规则的 `demo_url` 跑一次「抓目录 + 抽 1 章」，通过条件：
  · 章节数 ≥ 20
  · 正文汉字 ≥ 300
  · 首章标题与正文标题一致（防「抓到目录当正文」这类静默错位）

用法：
    python tools/verify_mirror_rules.py                # 全部 mirror-* 规则
    python tools/verify_mirror_rules.py --limit 10     # 只验前 10 条
    python tools/verify_mirror_rules.py --prefix mirror-dl-a
"""

import argparse
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from noveldown.engine import Downloader            # noqa: E402
from noveldown.models import STATUS_OK                    # noqa: E402
from noveldown.rules import RULES_DIR, load_rules  # noqa: E402


def verify_one(rule):
    """返回 (ok, 摘要字符串)。走 `Downloader.run(limit=1)` —— 即**生产路径**本身。"""
    url = rule.raw.get("demo_url")
    if not url:
        return False, "规则没有 demo_url，无法验证"
    dl = None
    try:
        dl = Downloader(url, config={"delay": 0.4}, rules={rule.id: rule},
                        log=lambda m, level="info": None)
        book = dl.run(limit=1)
        total = len(book.chapters)
        if total < 20:
            return False, f"目录只 {total} 章"
        done = [c for c in book.chapters if c.status == STATUS_OK]
        if not done:
            bad = next((c for c in book.chapters if not c.is_protected), None)
            return False, (f"首章未抓成（{getattr(bad, 'status', '?')}）"
                           f"｜{getattr(bad, 'note', '') or ''}"[:70])
        ch = done[0]
        text = ch.text or ""
        cjk = len(re.findall(r"[\u4e00-\u9fff]", text))
        if cjk < 300:
            return False, f"正文仅 {cjk} 字"
        # ⚠ 判「是不是把目录当正文抓了」要用**结构特征**，不能用"标题在不在正文里"：
        # 很多站点的正文里**本来就不重复章节标题**（标题在 h1 里），
        # 用后者会把好规则误判成失败（实测 6 条假失败）。
        # 真信号是：正文里出现**大量**章号 —— 那是目录列表，不是散文。
        list_hits = len(re.findall(
            r"第[0-9０-９一二三四五六七八九十百千零两]{1,6}[章节回卷]", text))
        if list_hits >= 8:
            return False, f"正文疑似目录（命中 {list_hits} 个章号 / {cjk} 字）"
        return True, f"{total} 章 / 首章 {cjk} 字"
    except Exception as e:
        return False, f"{type(e).__name__}: {str(e)[:70]}"
    finally:
        try:
            if dl is not None:
                dl.close()
        except Exception:
            pass


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--prefix", default="mirror-", help="只验 id 以该前缀开头的规则")
    ap.add_argument("--from", dest="fromfile",
                    default=os.path.join(".sources", "verify_rules.jsonl"),
                    help="--only-failed 时读取上次结果的路径")
    ap.add_argument("--only-failed", action="store_true",
                    help="只复验上次未通过的（读上一次的 --out 结果）。"
                         "⚠ 本机单次请求失败率约 45%%，一次 404/SSLError **不足以判死**，"
                         "先复验再决定是否剔除")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--out", default=os.path.join(".sources", "verify_rules.jsonl"))
    args = ap.parse_args()

    ids = sorted(os.path.basename(p)[:-5]
                 for p in glob.glob(os.path.join(RULES_DIR, "*.json")))
    rules = load_rules()
    ids = [i for i in ids if i.startswith(args.prefix) and i in rules]
    if args.only_failed and os.path.exists(args.fromfile):
        prev = {}
        with open(args.fromfile, encoding="utf-8", errors="replace") as f:
            for line in f:
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                prev[d["id"]] = d
        failed = {k for k, v in prev.items() if not v.get("ok")}
        ids = [i for i in ids if i in failed]
        print(f"只复验上次未通过的 {len(ids)} 条")
    if args.limit:
        ids = ids[:args.limit]
    print(f"待验证 {len(ids)} 条规则（前缀 {args.prefix}）")

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    ok_n = 0
    with open(args.out, "w", encoding="utf-8") as f:
        for i, rid in enumerate(ids, 1):
            ok, msg = verify_one(rules[rid])
            ok_n += ok
            flag = "✓" if ok else "✗"
            print(f"  {flag} [{i}/{len(ids)}] {rid:26} {msg}")
            f.write(json.dumps({"id": rid, "ok": ok, "msg": msg},
                               ensure_ascii=False) + "\n")
            f.flush()
    print(f"\n通过 {ok_n}/{len(ids)}（{100*ok_n/max(len(ids),1):.0f}%）→ {args.out}")


if __name__ == "__main__":
    main()
