#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""`tools/import_chinese_philosophy.py` 的回归：数据集 → Book 映射 + 去重优先级。

用**内存临时 zip** 造数据，不需要 fixture 文件，也不联网、不依赖外部数据集。
"""

import json
import os
import sys
import tempfile
import unittest
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

import import_chinese_philosophy as icp  # noqa: E402


def _book(name, author="佚名", chapters=None):
    return {"name": name, "author": author,
            "chapters": chapters if chapters is not None else [
                {"name": name,
                 "paragraphs": [{"paragraph": "正文甲。", "type": 1}]}]}


def _make_zip(entries):
    """entries: [(zip 内路径, dict)] → 临时 zip 路径（调用方负责删除）。"""
    fd, path = tempfile.mkstemp(suffix=".zip")
    os.close(fd)
    with zipfile.ZipFile(path, "w") as z:
        for p, d in entries:
            z.writestr(p, json.dumps(d, ensure_ascii=False))
    return path


class TestImportCtext(unittest.TestCase):

    def test_priority_order(self):
        """顶层分类目录 < back/new < back/simple < back/old < back/traditional。"""
        ps = [icp._priority(p) for p in (
            "chinese-philosophy-main/经/四书类/论语.json",
            "chinese-philosophy-main/back/new/儒家/论语.json",
            "chinese-philosophy-main/back/simple/经/书类/论语.json",
            "chinese-philosophy-main/back/old/儒家/论语.json",
            "chinese-philosophy-main/back/traditional/子/儒家类/論語.json",
        )]
        self.assertTrue(all(ps[i] < ps[i + 1] for i in range(len(ps) - 1)), ps)
        # cjk/ 是字符集，不该当书（被 scan 排除）
        self.assertGreaterEqual(icp._priority("chinese-philosophy-main/cjk/cjk.txt"), 9)

    def test_scan_dedupes_by_name_keeping_best(self):
        z = _make_zip([
            ("chinese-philosophy-main/子/儒家类/大学.json", _book("大学", "曾子")),
            ("chinese-philosophy-main/back/old/儒家/大学.json", _book("大学", "旧版")),
        ])
        try:
            books = icp.scan(z)
            self.assertEqual(list(books), ["大学"])
            self.assertEqual(len(books["大学"]), 2)      # 两个版本都留在候选里
            best = books["大学"][0]
            self.assertIn("子/儒家类", best[1])           # 但榜首是顶层版
            self.assertEqual(best[2]["author"], "曾子")
        finally:
            os.unlink(z)

    def test_scan_skips_non_book_json(self):
        """没有 chapters 的 JSON（如索引/配置）不该被当成书。"""
        z = _make_zip([
            ("chinese-philosophy-main/子/儒家类/真书.json", _book("真书")),
            ("chinese-philosophy-main/子/儒家类/假的.json", {"note": "不是书"}),
        ])
        try:
            books = icp.scan(z)
            self.assertEqual(list(books), ["真书"])
        finally:
            os.unlink(z)

    def test_to_book_maps_model(self):
        d = _book("大学", "战国·佚名", chapters=[
            {"name": "第一节", "paragraphs": [
                {"paragraph": " 甲 ", "type": 1},
                {"paragraph": "", "type": 1},          # 空段应丢弃
                {"paragraph": "乙", "type": 2}]}])
        b = icp.to_book("大学", d, "x/大学.json")
        self.assertEqual(b.site, "ctext")
        self.assertEqual(b.title, "大学")
        self.assertEqual(b.author, "战国·佚名")
        self.assertEqual(len(b.chapters), 1)
        ch = b.chapters[0]
        self.assertEqual(ch.title, "第一节")
        self.assertEqual(ch.paragraphs, ["甲", "乙"])   # 空段丢、首尾空白 strip
        self.assertEqual(ch.status, "ok")
        self.assertEqual(ch.source_pages, ["x/大学.json#1"])

    def test_to_book_falls_back_title_when_chapter_name_empty(self):
        d = _book("无名", chapters=[{"name": "", "paragraphs": [
            {"paragraph": "内容", "type": 1}]}])
        b = icp.to_book("无名", d, "x/无名.json")
        self.assertEqual(b.chapters[0].title, "第 1 节")   # 有兜底，不留空标题

    def test_to_book_handles_empty_chapters(self):
        b = icp.to_book("空书", {"name": "空书", "chapters": []}, "x/空书.json")
        self.assertEqual(b.chapters, [])
        self.assertEqual(b.title, "空书")

    def test_stat_of_counts_cjk_only(self):
        d = _book("X", chapters=[{"name": "c", "paragraphs": [
            {"paragraph": "汉字ABC123", "type": 1}]}])
        self.assertEqual(icp.stat_of(d), (1, 2, 1))       # 章数 / 汉字数 / 段落数


if __name__ == "__main__":
    unittest.main()
