#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""断点续爬状态层测试。

覆盖两个实测踩过的坑：
  1. discover() 每次产出全新 pending 列表 → 必须在写盘前合并旧状态，否则进度归零。
  2. 缓存若按章节序号索引，目录增删章节后会串页 → 必须按 cid 索引。
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from noveldown.models import (Chapter, STATUS_BLOCKED, STATUS_EMPTY,  # noqa: E402
                              STATUS_LOCKED, STATUS_OK, STATUS_PENDING)
from noveldown.state import StateStore, slug_of  # noqa: E402
from tests._base import make_book, temp_subdir  # noqa: E402


def ch(index, cid, status=STATUS_OK, text="正文内容" * 10):
    return Chapter(index=index, title=f"第{index}章", url=f"u/{cid}",
                   cid=cid, status=status,
                   paragraphs=[text] if status == STATUS_OK else [])


class TestStateStore(unittest.TestCase):

    def setUp(self):
        # 共享临时目录（本机文件系统慢，见 tests/_base.temp_root 说明）
        self.base = temp_subdir("state")
        self.store = StateStore(self.base, "t.site", "42")

    def test_slug(self):
        self.assertEqual(slug_of("a.b-c", "1/2"), "a.b-c_1_2")

    def test_save_and_load_chapter_by_cid(self):
        self.store.save_chapter(ch(3, "777"))
        got = self.store.load_chapter("777", 3)
        self.assertEqual(got["status"], STATUS_OK)
        self.assertEqual(got["paragraphs"], ["正文内容" * 10])
        self.assertIsNone(self.store.load_chapter("888", 4))

    def test_cache_is_cid_keyed_not_index_keyed(self):
        """目录插入新章导致序号整体后移时，缓存不得错位。"""
        self.store.save_chapter(ch(5, "500", text="A" * 30))
        # 模拟目录变化：同一 cid 的新序号
        got = self.store.load_chapter("500", 9)
        self.assertIsNotNone(got, "应按 cid 命中，与序号无关")
        self.assertEqual(got["paragraphs"], ["A" * 30])

    def test_protected_content_is_not_persisted(self):
        self.store.save_chapter(ch(1, "1", status=STATUS_BLOCKED,
                                   text="VIP 正文不应落盘"))
        got = self.store.load_chapter("1", 1)
        self.assertEqual(got["paragraphs"], [])
        self.assertEqual(got["source_pages"], [])

    def test_merge_prior_status_restores_locked(self):
        book = make_book(n=3)
        book.chapters[1].status = STATUS_LOCKED
        book.chapters[1].note = "目录标记为受保护"
        self.store.save_state(book)

        fresh = make_book(n=3)          # 模拟 discover() 的新结果：全 pending
        merged = self.store.merge_prior_status(fresh)
        self.assertEqual(merged, 1)
        self.assertEqual(fresh.chapters[1].status, STATUS_LOCKED)
        self.assertTrue(fresh.chapters[1].is_protected)

    def test_rehydrate_restores_body(self):
        book = make_book(n=2)
        for c in book.chapters:
            self.store.save_chapter(c)
        self.store.save_state(book)

        fresh = make_book(n=2)
        for c in fresh.chapters:
            c.status = STATUS_PENDING
            c.paragraphs = []
        n = self.store.rehydrate(fresh)
        self.assertEqual(n, 2)
        self.assertTrue(all(c.has_content for c in fresh.chapters))

    def test_done_cids_covers_state_and_orphan_cache(self):
        """状态只每 N 章落一次盘；Ctrl-C 后的那几章靠扫缓存目录补齐。"""
        book = make_book(n=3)
        self.store.save_state(book)                  # state 记 3 章
        self.store.save_chapter(ch(4, "ORPHAN"))     # 第 4 章只落了缓存
        done = self.store.done_cids()
        self.assertIn("1001", done)
        self.assertIn("ORPHAN", done, "state 未记录但缓存已存在的章节必须算完成")

    def test_done_cids_excludes_failed(self):
        book = make_book(n=2)
        book.chapters[1].status = STATUS_EMPTY
        book.chapters[1].paragraphs = []
        self.store.save_state(book)
        done = self.store.done_cids()
        self.assertIn("1001", done)
        self.assertNotIn("1002", done, "empty/failed 必须重试")

    def test_clear(self):
        self.store.save_chapter(ch(1, "1"))
        self.store.save_state(make_book(n=1))
        self.store.clear()
        self.assertIsNone(self.store.load_state())
        self.assertIsNone(self.store.load_chapter("1", 1))

    def test_progress_summary(self):
        book = make_book(n=3)
        book.chapters[2].status = STATUS_BLOCKED
        book.chapters[2].paragraphs = []
        self.store.save_state(book)
        p = self.store.progress()
        self.assertEqual(p["chapters_total"], 3)
        self.assertEqual(p["chapters_ok"], 2)
        self.assertEqual(p["protected"], 1)
        self.assertEqual(p["remaining"], 0)


class TestResumeDecisionLogic(unittest.TestCase):
    """验证 engine 的「真正的完成」判定：状态已完成 **且** 正文在手上。"""

    def test_state_says_ok_but_cache_missing_is_refetched(self):
        store = StateStore(temp_subdir("resume"), "t.site", "1")
        book = make_book(n=2)
        store.save_state(book)                 # 声称 2 章 ok
        raw_done = store.done_cids()

        fresh = make_book(n=2)
        for c in fresh.chapters:
            c.status = STATUS_PENDING
            c.paragraphs = []
        store.rehydrate(fresh)                 # 缓存不存在 → 回填不到正文
        done = {c.cid for c in fresh.chapters
                if c.cid in raw_done and (c.has_content or c.is_protected)}
        self.assertEqual(done, set(),
                         "缓存缺失时必须重抓，否则会导出空章")


if __name__ == "__main__":
    unittest.main()
