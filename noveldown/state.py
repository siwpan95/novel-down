#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
断点续爬状态层。

[借鉴来源] ma6254/FictionDown（GPL-3.0）的「断点续爬」特性。
借鉴范围：仅「章节级状态持久化 + 重启后跳过已完成章节」的设计思路，
          未复用任何代码（FictionDown 为 Go 实现，且其正版/盗版互补流程含 VIP 语义，已排除）。

结构
----
state/<site>_<bid>.json
    书籍元信息 + 章节状态表（轻量，便于随时查看进度）
cache/<site>_<bid>/<cid>.json
    单章正文缓存（重跑不重复请求）

**缓存按 cid 索引而非章节序号**（实测踩坑）：站点目录一旦增删章节，
序号会整体错位，按序号缓存会把 A 章的正文当成 B 章。cid 是站点稳定的章节标识。

受保护章节（locked/blocked）的正文一律不落缓存——免费章节硬约束。
"""

import json
import os
import re
import time

from .models import (Book, PROTECTED_STATUSES, STATUS_OK, STATUS_PENDING)


def slug_of(site: str, book_id: str) -> str:
    s = f"{site}_{book_id}"
    return re.sub(r"[^\w.-]", "_", s)


def _safe_cid(cid: str, index: int) -> str:
    cid = (cid or "").strip()
    if cid:
        return re.sub(r"[^\w.-]", "_", cid)
    return f"idx{index:05d}"


class StateStore:
    """书籍级状态与章节缓存的读写。"""

    def __init__(self, base_dir: str, site: str, book_id: str):
        self.slug = slug_of(site, book_id)
        self.base_dir = os.path.abspath(base_dir)
        self.state_path = os.path.join(self.base_dir, "state", f"{self.slug}.json")
        self.cache_dir = os.path.join(self.base_dir, "cache", self.slug)
        os.makedirs(os.path.dirname(self.state_path), exist_ok=True)
        os.makedirs(self.cache_dir, exist_ok=True)

    # ---------------- 章节缓存 ----------------
    def _chapter_path(self, ch) -> str:
        return os.path.join(self.cache_dir, f"{_safe_cid(ch.cid, ch.index)}.json")

    def save_chapter(self, ch):
        """写单章正文缓存。受保护章节只记状态，不保存正文。"""
        payload = {
            "index": ch.index, "title": ch.title, "url": ch.url, "cid": ch.cid,
            "status": ch.status, "note": ch.note,
            "paragraphs": [] if ch.is_protected else ch.paragraphs,
            "source_pages": [] if ch.is_protected else ch.source_pages,
            "ads_removed": ch.ads_removed,
            "decode_note": ch.decode_note,
        }
        path = self._chapter_path(ch)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
        os.replace(tmp, path)

    def load_chapter(self, cid: str, index: int):
        path = os.path.join(self.cache_dir, f"{_safe_cid(cid, index)}.json")
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return None

    # ---------------- 书籍状态 ----------------
    def save_state(self, book: Book, extra: dict = None):
        payload = {
            "saved_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "site": book.site,
            "book_id": book.book_id,
            "url": book.url,
            "title": book.title,
            "author": book.author,
            "stats": book.stats(),
            "chapters": [
                {"index": c.index, "title": c.title, "url": c.url, "cid": c.cid,
                 "volume": c.volume, "status": c.status, "note": c.note,
                 "chars": c.char_count}
                for c in book.chapters
            ],
        }
        if extra:
            payload["extra"] = extra
        tmp = self.state_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.state_path)
        return self.state_path

    def load_state(self):
        if not os.path.exists(self.state_path):
            return None
        try:
            with open(self.state_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return None

    # ---------------- 断点续爬 ----------------
    def done_cids(self) -> set:
        """已完成的章节 cid 集合。

        完成 = ok（有正文）/ locked / blocked（后两者无需重试）。
        failed / empty / pending 会重新入队。

        真相来源有两处：
          1. state.json 的章节表（快速路径，主用）
          2. cache 目录（补齐 state 尚未落盘的章节）——
             状态每 20 章才落一次盘，若用户 Ctrl-C 在两次落盘之间，
             仅靠 state.json 会丢掉这期间的成果。
        """
        st = self.load_state()
        done, known = set(), set()
        if st:
            for c in st.get("chapters", []):
                cid = c.get("cid")
                if not cid:
                    continue
                known.add(cid)
                if c.get("status") == STATUS_OK or c.get("status") in PROTECTED_STATUSES:
                    done.add(cid)

        # 补齐：缓存里已存在但 state.json 还没记上的章节
        try:
            for fn in os.listdir(self.cache_dir):
                if not fn.endswith(".json"):
                    continue
                stem = fn[:-5]
                if stem in known:
                    continue
                try:
                    with open(os.path.join(self.cache_dir, fn), "r",
                              encoding="utf-8") as f:
                        d = json.load(f)
                except (OSError, json.JSONDecodeError):
                    continue
                if d.get("status") == STATUS_OK or d.get("status") in PROTECTED_STATUSES:
                    done.add(d.get("cid") or stem)
        except OSError:
            pass
        return done

    def merge_prior_status(self, book: Book) -> int:
        """把上一次运行的状态合并回新发现的章节表（按 cid 匹配）。

        这是断点续爬的关键：discover() 每次都会产出全新的、全部 pending 的章节表，
        若不合并就会把进度覆盖掉（实测踩坑：限流抓 30 章后重跑，进度归零重抓第 1 章）。

        Returns: 合并（恢复）的章节数
        """
        st = self.load_state()
        if not st:
            return 0
        prior = {c.get("cid"): c for c in st.get("chapters", []) if c.get("cid")}
        merged = 0
        for ch in book.chapters:
            p = prior.get(ch.cid)
            if not p:
                continue
            status = p.get("status")
            if status in PROTECTED_STATUSES:
                ch.status = status
                ch.note = p.get("note", "")
                merged += 1
        return merged

    def rehydrate(self, book: Book) -> int:
        """把缓存里的正文回填到 Book。Returns: 回填章节数。"""
        n = 0
        for ch in book.chapters:
            if ch.is_protected or ch.has_content:
                continue
            cached = self.load_chapter(ch.cid, ch.index)
            if not cached:
                continue
            status = cached.get("status")
            if status in PROTECTED_STATUSES:
                ch.status = status
                ch.note = cached.get("note", "")
                n += 1
            elif status == STATUS_OK:
                ch.status = STATUS_OK
                ch.paragraphs = list(cached.get("paragraphs") or [])
                ch.source_pages = list(cached.get("source_pages") or [])
                ch.ads_removed = cached.get("ads_removed", 0)
                ch.decode_note = cached.get("decode_note", "")
                n += 1
        return n

    def clear(self):
        """清空本书记录（--force 时调用）。"""
        import shutil
        if os.path.exists(self.cache_dir):
            shutil.rmtree(self.cache_dir, ignore_errors=True)
        if os.path.exists(self.state_path):
            try:
                os.remove(self.state_path)
            except OSError:
                pass
        os.makedirs(self.cache_dir, exist_ok=True)

    def progress(self) -> dict:
        """当前进度摘要（供 CLI 显示）。"""
        st = self.load_state()
        if not st:
            return {"exists": False}
        chs = st.get("chapters", [])
        ok = sum(1 for c in chs if c.get("status") == STATUS_OK)
        prot = sum(1 for c in chs if c.get("status") in PROTECTED_STATUSES)
        return {
            "exists": True,
            "saved_at": st.get("saved_at"),
            "title": st.get("title"),
            "chapters_total": len(chs),
            "chapters_ok": ok,
            "protected": prot,
            "remaining": len(chs) - ok - prot,
        }
