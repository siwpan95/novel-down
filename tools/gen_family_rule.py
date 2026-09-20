#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把结构扫描结果（`.sources/deep.jsonl`）聚成**族规则草稿**。

## 为什么按「命中的选择器组合」聚类

族规则（一条规则 `match` 多个域）能成立的前提是：**组内所有域的目录/正文结构一致**。
深探阶段已经对每个域**逐个候选选择器实测**过，所以「命中的目录选择器 + 命中的正文选择器」
就是天然的聚类签名 —— 同签名的域可以共用一条规则。

这与「看到同模板就跳过」是相反的做法：**每个域都实测通过才写进 `match`**。
源越多越抗单站抽风，所以不因"重复"而跳过，但也绝不未验证就收录。

## 输出

草稿写到 `.sources/draft_rules/`（不入仓，需人工复核 + 抽样验证后才移入
`noveldown/rules/`）。同时打印聚类报告。
"""

import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def load(path):
    """读深探结果，**按域去重**。

    ⚠ 为什么必须去重：深探是分批跑的（首轮 + 多轮「未确认重扫」救回后再深探），
    同一个域会有**多条**记录 —— 早先失败、后来通过（判据改进了），或反过来。
    若不去重，`match` 里会出现重复域名、且可能用**过时的那条**下结论。
    规则：**只要有一条通过就用它**；都没通过就留最新一条。
    """
    if not os.path.exists(path):
        return []
    best = {}
    for r in load_raw(path):
        dom = r.get("domain")
        if not dom:
            continue
        cur = best.get(dom)
        if cur is None:
            best[dom] = r
        elif passed(r) and not passed(cur):
            best[dom] = r            # 后来通过了 → 覆盖
        elif passed(r) == passed(cur):
            best[dom] = r            # 同状态 → 取更新的
    return list(best.values())


def load_raw(path):
    out = []
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:
                continue                     # 容忍坏行（并发写入可能留半行）
    return out


def passed(rec) -> bool:
    return bool(rec.get("catalog_selector") and rec.get("content_selector"))


def group_key(rec):
    return (rec["catalog_selector"], rec["content_selector"])


def url_shape(path: str) -> str:
    """把具体 URL 路径压成形状：数字段 → N，用于看同组 URL 形态是否一致。"""
    if not path:
        return ""
    return re.sub(r"\d+", "N", path)


def build_rule(domains, cat_sel, con_sel, samples):
    """生成一条族规则草稿。

    URL 策略刻意**保守**：
    - `info_url` 用 `{url}`（用户给什么书页就用什么）—— 因为族内各域的书籍页路径
      形态不一（`/book/N/`、`/txt/N/`、`/N/`），写死一个模板必然有域不匹配；
    - `url_template` **不写**，交给 `urljoin(书籍页URL, href)` —— 只要章节链接是
      相对路径（mirror 模板都是），这比合成模板更稳；
    - `url_pattern` 按**实测到的 bid 形态**选：数字书号用 `(\\d+)`，
      字母数字混用（实测 min-yuan.com 是 `/txt/vpnm/1.html`）用 `([A-Za-z0-9_-]+)`。
    """
    cat_sels = [s.strip() for s in cat_sel.split(",")] if "," in cat_sel else [cat_sel]
    con_sels = [s.strip() for s in con_sel.split(",")] if "," in con_sel else [con_sel]
    shapes = {s.get("bid_shape") for s in samples}
    # ⚠ 书号必须从**URL 的最后一个路径段**里取。
    # 早期用 `([A-Za-z0-9_-]+)`（不带锚点）→ `re.search` 从左往右第一个匹配，
    # 在 `https://xiaoxiaoshuo8.com/0_8/` 上抓到的是 **`https`**（实测 书籍ID=https）。
    # 所以锚定到路径末尾（`^.*/` 贪婪保证是最后一段）：
    #   `/book/12345/` → 12345 ｜ `/txt/vpnm/` → vpnm ｜ `/book/21.html` → 21
    if shapes == {"digits"}:
        bid_pat = r"^.*/(\d+)(?:/|\.html?)?$"
    else:
        bid_pat = r"^.*/([A-Za-z0-9_-]+)(?:/|\.html?)?$"
    # ⚠ slug 必须**唯一**：不同选择器可能压成同一个 slug
    # （实测 `#list a` 与 `list a` 都 → `list-a`，39 组只落成 30 个文件）。
    # 所以附上签名的短哈希。
    import hashlib
    sig_hash = hashlib.sha1(f"{cat_sel}|{con_sel}".encode("utf-8")).hexdigest()[:6]
    slug = re.sub(r"[^0-9a-zA-Z]+", "-", cat_sel).strip("-").lower()[:22] or "generic"
    # ⚠ `demo_url` 必须落在本规则 `match` 覆盖的域名上，否则**引擎会报
    # 「没有匹配的站点规则」**（实测踩到 2 条：深探时站点跳转到了另一个域名，
    # 于是 book_url 的主机名不在 match 里）。
    # 这里挑一个主机名在 match 内的样本做 demo；都没有就退回域根。
    from urllib.parse import urlparse
    def _host_ok(u):
        h = (urlparse(u or "").hostname or "").lower()
        return any(h == d or h.endswith("." + d) for d in domains)
    demo = next((s.get("book_url") for s in samples if _host_ok(s.get("book_url"))), None)
    if not demo:
        # ⚠ 没有**可验证**的 demo 就不生成这条规则。
        # 实测这种组的成因：站点把书页**跳转到另一个域名**，于是深探记下的
        # book_url 主机名不在本组域名里 —— 生成的规则既报「没有匹配的站点规则」，
        # 回退到域根又因 `url_pattern` 匹配不上而报「无法提取书籍 ID」。
        # 与其产出一条注定验证不过的规则，不如**不产出**（留给下轮改进深探来覆盖）。
        return None
    return {
        "id": f"mirror-{slug}-{sig_hash}",
        "name": (f"免费镜像族 · 目录 {cat_sel}"
                 if len(domains) > 1 else f"免费镜像 · 目录 {cat_sel}"),
        "pool": "免费镜像",
        "enabled": True,
        "free_only": True,
        "predecode": False,
        "requires_js": False,
        "fetch_mode": "http",
        "demo_url": demo,
        "notes": (
            "★ 批量铺开镜像池 · 自动聚类（详见 docs/NEW_SITES_PLAN.md §11.3）\n"
            f"签名：目录 `{cat_sel}` + 正文 `{con_sel}`；域数 {len(domains)}；"
            f"书号形态 {sorted(x for x in shapes if x) or ['unknown']} → url_pattern={bid_pat}\n"
            "收录理由：盗版站抽风是通病，**源越多越抗抽风**——同一份内容有多个可替换的域名才算可用。\n"
            "验证方式：每域均由 `tools/scan_mirrors.py --phase deep` 逐候选实测通过"
            "（目录 ≥20 章、正文 ≥300 汉字），**非按模板猜测**。样例：\n"
            + "\n".join(
                f"  · {s['domain']} — {s.get('chapters')} 章 / {s.get('content_cjk')} 字"
                for s in samples[:4])
            + "\n⚠ 法律：内容来源未授权，规则仅供**个人离线阅读**，勿再分发或商用。"
        ),
        "match": sorted(domains),
        "book": {"url_pattern": bid_pat, "info_url": "{url}"},
        "catalog": {
            "pages": {"mode": "single"},
            "item_selector": ", ".join(cat_sels),
            # ⚠ 模式要**宽松**：末段章号后面 `.html` 是**可有可无**的。
            # 实测踩到：扫描器靠「链接文字像章标题」认出了章链接（如 `/book/21/451`），
            # 但这里只写 `\.html` → 引擎一个 cid 都提取不到 →
            # 规则报「目录只 0 章」（占失败项的 1/3）。
            "id_from": {"mode": "href",
                        "pattern": "/(?P<cid>\\d+)(?:_\\d+)?(?:\\.html?)?$"},
            "sort": "cid_numeric_asc",
            "dedupe": "keep_first",
            # 剔除「站点导航类」伪目录项：它们和真章节一样带数字 href，
            # cid 甚至与第 1 章相同 → keep_first 会把真标题挤掉（实测「开始阅读」）。
            "item_deny_text": ["开始阅读", "在线书库", "TXT下载", "txt下载",
                               "最新章节", "加入书架", "推荐本书", "查看全部",
                               "更多章节", "返回目录", "手机阅读", "返回书页"],
        },
        "chapter": {
            "content_selector": con_sels[0],
            "content_selectors": con_sels,
            "strip_selectors": ["script", "style", ".bottem", ".bottem1",
                                ".bottem2", "#center_tip"],
            "ad_patterns": ["请记住本站", "手机版阅读", "最新网址", "笔趣阁",
                            "一秒记住", "本章未完", "点击下一页继续阅读",
                            # 镜像站正文里常见的**站点导航串**（实测 xcsm.net 首段就是这句）
                            "将本站设为首页", "把本站", "加入书架", "推荐本书",
                            "返回目录", "上一章", "下一章", "章节错误",
                            "求收藏", "求推荐", "内容加载失败", "请稍后重试",
                            # ⚠ 只用「整句形态」的串：ad_patterns 是**子串匹配**，
                            # 写「收藏」两个字会把正文里正常的「收藏」也删掉。
                            "收藏本站", "收藏本书", "收藏本页", "加入收藏"],
        },
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--in", dest="inp", default=os.path.join(".sources", "deep.jsonl"))
    ap.add_argument("--out-dir", default=os.path.join(".sources", "draft_rules"))
    ap.add_argument("--min-domains", type=int, default=1,
                    help="组内至少这么多域才生成规则草稿")
    ap.add_argument("--report", default=os.path.join(".sources", "families.md"))
    args = ap.parse_args()

    recs = load(args.inp)
    ok = [r for r in recs if passed(r)]
    print(f"deep 记录 {len(recs)} · 通过 {len(ok)}")
    if not ok:
        print("没有通过的记录，先跑 --phase deep")
        return

    groups = defaultdict(list)
    for r in ok:
        groups[group_key(r)].append(r)

    lines = ["# 镜像族聚类报告（自动生成，勿手改）", "",
             f"输入：`{args.inp}`（{len(recs)} 条）· 通过 **{len(ok)}** 条", "",
             "| 域数 | 目录选择器 | 正文选择器 | 书籍页形态 | 章节页形态 | 示例域 |",
             "|---:|---|---|---|---|---|"]
    ordered = sorted(groups.items(), key=lambda kv: -len(kv[1]))
    os.makedirs(args.out_dir, exist_ok=True)
    made = 0
    skipped = []
    for (cat, con), rs in ordered:
        doms = [r["domain"] for r in rs]
        bshapes = Counter(url_shape(r.get("book_path")) for r in rs)
        cshapes = Counter(url_shape(r.get("chapter_path")) for r in rs)
        lines.append(
            f"| {len(rs)} | `{cat}` | `{con}` | "
            f"{', '.join(f'{k}×{v}' for k, v in bshapes.most_common(2))} | "
            f"{', '.join(f'{k}×{v}' for k, v in cshapes.most_common(2))} | "
            f"{', '.join(doms[:4])} |")
        if len(rs) >= args.min_domains:
            rule = build_rule(doms, cat, con, rs)
            if rule is None:
                skipped.append(f"{cat} + {con}")
                continue
            p = os.path.join(args.out_dir, rule["id"] + ".json")
            with open(p, "w", encoding="utf-8") as f:
                json.dump(rule, f, ensure_ascii=False, indent=2)
            made += 1
    with open(args.report, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    if skipped:
        print(f"⚠ 跳过 {len(skipped)} 组（无可验证 demo：书页跳到了本组域名之外）：")
        for x in skipped:
            print(f"    {x}")
    print(f"\n聚类 {len(groups)} 组 · 生成 {made} 条规则草稿 → {args.out_dir}")
    print(f"报告 → {args.report}")
    print("\n最大 8 组：")
    for (cat, con), rs in ordered[:8]:
        print(f"  {len(rs):4}  {cat}  +  {con}")


if __name__ == "__main__":
    main()
