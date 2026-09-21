#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把新实测通过的域名合并进**已存在**的镜像族规则（或提示需新增）。

为什么要独立成工具：手工改 JSON 时最容易漏两件事 ——
  1. `notes` 里的「域数 N」没跟着 `match` 更新 → 文档与实现不一致（门禁第 9 项会抓）；
  2. 样例行没追加 → 后续无法从 notes 看出这个域是**哪一批、哪次实测**收进来的。

用法：
    python tools/merge_family_domains.py \
        --deep .sources/deep.blocked2.jsonl \
        --dirs noveldown/rules/mirrors \
        --merge mirror-div-layout-a-058805=bookszw.com \
        --merge mirror-ul-a-1def0f=wujixsw.info
"""

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def load_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--deep", required=True, help="深扫结果 jsonl（提供每域的实测样例数据）")
    ap.add_argument("--dirs", default="noveldown/rules/mirrors")
    ap.add_argument("--merge", action="append", default=[],
                    help="规则文件名（不含 .json）=域名，可重复")
    ap.add_argument("--tag", default="", help="注释里标注的来源批次")
    args = ap.parse_args()

    recs = {r["domain"]: r for r in load_jsonl(args.deep) if r.get("alive")}
    groups = {}
    for item in args.merge:
        rid, _, dom = item.partition("=")
        groups.setdefault(rid, []).append(dom.strip())

    for rid, doms in groups.items():
        path = os.path.join(args.dirs, rid + ".json")
        if not os.path.exists(path):
            print(f"✗ {rid}: 规则文件不存在 → 需按新族规则另建（见 draft_rules/）")
            continue
        raw = json.load(open(path, encoding="utf-8"))
        match = list(raw.get("match") or [])
        added, samples = [], []
        for dom in doms:
            rec = recs.get(dom)
            if rec is None:
                print(f"✗ {rid} ← {dom}: has no deep record (refusing to merge)")
                continue
            if rec.get("catalog_selector") != raw["catalog"].get("item_selector") \
                    or rec.get("content_selector") != raw["chapter"].get("content_selector"):
                print(f"✗ {rid} ← {dom}: 签名不一致，拒绝合并"
                      f"（{rec.get('catalog_selector')} + {rec.get('content_selector')}）")
                continue
            if dom in match:
                print(f"· {rid} ← {dom}: 已在 match 中，跳过")
                continue
            match.append(dom)
            added.append(dom)
            samples.append(f"  · {dom} — {rec.get('chapters')} 章 / "
                           f"{rec.get('content_cjk')} 字")
        if not added:
            continue
        raw["match"] = sorted(match)
        notes = raw.get("notes", "")
        # 「域数 N」必须与 match 长度一致（门禁第 9 项会机械核对）
        notes = re.sub(r"域数 \d+", f"域数 {len(raw['match'])}", notes, count=1)
        tag = args.tag or "本轮镜像铺开"
        notes += (f"\n\n【合并】追加域名 {added}（{tag}，同签名逐域实测通过）\n"
                  + "\n".join(samples))
        raw["notes"] = notes
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            json.dump(raw, f, ensure_ascii=False, indent=2)
            f.write("\n")
        print(f"✓ {rid}: +{added} → 域数 {len(raw['match'])}")


if __name__ == "__main__":
    main()
