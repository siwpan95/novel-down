#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从「书源库」拉取**候选站点线索**（只要域名元数据，不要规则体）。

## 为什么只要元数据

社区书源库（shuyuan.yiove.com / Gitee xioo/shuyuan / XIU2/Yuedu）里的书源是
「阅读」APP（Legado）格式的规则 JSON —— 与本项目的规则 schema 没有交集，
**不能直接运行**。它们的价值在于：**每个书源都指向一个真实的站点域名**。
所以本项目只把它当**线索池**：取出「站点名 + 域名 + 热度」，再自己实探。

同理，书源的规则体（`ruleToc` / `ruleContent` 等）**一律不落盘**：
- 书源 JSON 多为社区贡献、无明确许可证；
- 「阅读」APP 已因侵权违法删除其开源源码并公告担责；
- 本项目是 MIT，不把来源不明的规则体随仓分发。
产物写在 `.sources/`（已在 .gitignore 中）。

## 用法

    # 全量（约 316 页 × 100 条 ≈ 3.15 万条），支持断点续跑
    python tools/harvest_book_sources.py

    # 只拉前 20 页试水
    python tools/harvest_book_sources.py --pages 20

    重跑会自动跳过已完成的页（状态记在 .sources/harvest_state.json）。
"""

import argparse
import json
import os
import re
import sys
import time
from urllib.parse import urlparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from noveldown.http_client import http_get  # noqa: E402

API = "https://shuyuan-api.yiove.com/shuyuan/book-sources"
# 该站是 SPA，接口在独立子域，故需带 Origin/Referer 才被接受
HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://shuyuan.yiove.com",
    "Referer": "https://shuyuan.yiove.com/",
}


# ⚠ 书源库的数据是**脏的**：`url` 字段可能是任意字符串。
# 实测踩到 `api.doubi.tk提示：点击登录切换服务器按钮可进行切换(当前书源为融合版)`
# —— 直接喂给 urlparse 会抛 `ValueError: netloc ... contains invalid characters
# under NFKC normalization`（全角括号被 NFKC 归一化后出现非法字符）。
# 所以域名字段一律「先正则校验、再取值」，校验不过就丢掉（当条线索无效）。
_HOST_RE = re.compile(r"^(?=.{1,253}$)(?!-)[A-Za-z0-9-]{1,63}"
                      r"(?:\.[A-Za-z0-9-]{1,63})+$")


def _domain(url: str) -> str:
    """从 URL 里取裸域名；取不到（脏数据/非法主机名）返回空串。"""
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return ""
    if host.startswith("www."):
        host = host[4:]
    # 纯 IP 也保留（有些镜像直接用 IP 提供服务）
    if re.match(r"^\d{1,3}(\.\d{1,3}){3}$", host):
        return host
    return host if _HOST_RE.match(host) else ""


def _apiset(url: str, params: dict):
    """调接口并解 JSON。⚠ 该接口偶发 000/超时（站点抽风），故走 http_get 的退避重试。

    `http_get` 不接受 `params` 参数（调用面刻意保持最小），所以这里自己拼查询串。
    """
    from urllib.parse import urlencode
    full = f"{url}?{urlencode(params)}" if params else url
    resp = http_get(full, headers=HEADERS, timeout=30, retries=3)
    return resp.json()


def load_state(path: str) -> dict:
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"done_pages": [], "total": None}


def save_state(path: str, state: dict):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=os.path.join(".sources", "shuyuan.jsonl"),
                    help="输出 JSONL（默认 .sources/shuyuan.jsonl）")
    ap.add_argument("--pages", type=int, default=0, help="最多抓多少页（0 = 全量）")
    ap.add_argument("--size", type=int, default=100, help="每页条数（接口上限 100）")
    ap.add_argument("--delay", type=float, default=0.25, help="页间隔秒数（礼貌）")
    ap.add_argument("--min-views", type=int, default=0, help="只保留热度 >= 该值的书源")
    args = ap.parse_args()

    out_dir = os.path.dirname(os.path.abspath(args.out))
    os.makedirs(out_dir, exist_ok=True)
    state_path = os.path.join(out_dir, "harvest_state.json")
    state = load_state(state_path)

    first = _apiset(API, {"page": 1, "page_size": args.size})
    total = first.get("total") or 0
    pages = (total + args.size - 1) // args.size
    if args.pages:
        pages = min(pages, args.pages)
    state["total"] = total
    print(f"书源库共 {total} 条 → {pages} 页（每页 {args.size}）")

    done = set(state["done_pages"])
    kept = 0
    skipped = 0
    seen_ids = set()
    # 已写过的 id（续跑时避免重复行）
    if os.path.exists(args.out):
        with open(args.out, encoding="utf-8") as f:
            for line in f:
                try:
                    seen_ids.add(json.loads(line)["id"])
                except Exception:
                    continue

    with open(args.out, "a", encoding="utf-8") as fout:
        for page in range(1, pages + 1):
            if page in done:
                continue
            try:
                data = first if page == 1 else _apiset(
                    API, {"page": page, "page_size": args.size})
            except Exception as e:
                print(f"  第 {page} 页失败（{type(e).__name__}: {e}）—— 记下，下次续跑",
                      file=sys.stderr)
                break
            items = data.get("items") or []
            if not items:
                done.add(page)
                continue
            for it in items:
                iid = it.get("id")
                if iid in seen_ids:
                    continue
                views = int(it.get("view_total") or 0)
                if views < args.min_views:
                    continue
                dom = _domain(it.get("url") or "")
                if not dom:
                    skipped += 1
                    continue
                seen_ids.add(iid)
                fout.write(json.dumps({
                    "id": iid,
                    "name": it.get("name"),
                    "url": it.get("url"),
                    "domain": dom,
                    "is_valid": bool(it.get("is_valid")),
                    "view_total": views,
                    "group": it.get("group"),
                }, ensure_ascii=False) + "\n")
                kept += 1
            fout.flush()
            done.add(page)
            state["done_pages"] = sorted(done)
            save_state(state_path, state)
            if page % 10 == 0 or page == pages:
                print(f"  第 {page}/{pages} 页 · 累计写入 {kept} 条")
            time.sleep(args.delay)

    print(f"\n完成：{args.out}（本次新增 {kept} 条，脏域名丢弃 {skipped} 条，已抓 {len(done)}/{pages} 页）")
    if len(done) < pages:
        print("⚠ 未抓完 —— 直接重跑本命令即可续跑")


if __name__ == "__main__":
    main()
