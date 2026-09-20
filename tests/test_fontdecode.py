#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
字体反爬解码测试（离线，不下载字体）。

真实的字形轮廓匹配需要 17MB 参考字体，不适合放进单测；这里覆盖
「PUA 检测 → 映射替换 → 覆盖率校验 → 缓存读写 → 字体 URL 提取 → 区块优先级」
这些不需要字体的部分。真实的 363/363 命中由端到端探针验证
（见 docs/RULES.md 的番茄小节与 CHANGELOG）。
"""

import gzip
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from noveldown import fontdecode as fd  # noqa: E402
from tests._base import temp_subdir  # noqa: E402


class TestPuaBasics(unittest.TestCase):

    def test_has_pua(self):
        self.assertTrue(fd.has_pua("寒\ue516呼啸"))
        self.assertFalse(fd.has_pua("寒风呼啸"))
        self.assertFalse(fd.has_pua(""))
        self.assertFalse(fd.has_pua(None))

    def test_pua_chars_collects_across_texts(self):
        got = fd.pua_chars(["寒\ue516啸", "漫\ue4eb雪", "\ue516重复"])
        self.assertEqual(got, {0xE516, 0xE4EB})

    def test_decode_text(self):
        m = {0xE516: "风", 0xE4EB: "天"}
        self.assertEqual(fd.decode_text("寒\ue516呼啸，漫\ue4eb飞雪。", m),
                         "寒风呼啸，漫天飞雪。")

    def test_decode_text_keeps_unknown_pua(self):
        """未覆盖的码位原样保留 —— 便于发现映射缺漏，而不是静默丢字。"""
        m = {0xE516: "风"}
        out = fd.decode_text("寒\ue516\ue999", m)
        self.assertEqual(out, "寒风\ue999")

    def test_decode_text_noop_without_map(self):
        s = "寒\ue516"
        self.assertEqual(fd.decode_text(s, {}), s)
        self.assertEqual(fd.decode_text(s, None), s)

    def test_coverage(self):
        texts = ["\ue516\ue4eb", "寒"]
        self.assertEqual(fd.decode_coverage(texts, {0xE516: "风", 0xE4EB: "天"}), 1.0)
        self.assertEqual(fd.decode_coverage(texts, {0xE516: "风"}), 0.5)
        self.assertEqual(fd.decode_coverage(["纯文本"], {}), 1.0)


class TestFontUrlExtraction(unittest.TestCase):

    def test_extracts_woff2_from_font_face(self):
        html = """<style>
        @font-face{font-family:X;src:url(https://a.example/f/a.woff2)format("woff2")}
        @font-face{font-family:X;src:url('//b.example/f/b.woff2')format("woff2"),
                                        url("/local/c.woff2")format("woff2")}
        </style>"""
        urls = fd.font_urls_from_html(html)
        self.assertIn("https://a.example/f/a.woff2", urls)
        self.assertIn("https://b.example/f/b.woff2", urls)   # // 补成 https
        self.assertNotIn("/local/c.woff2", urls)             # 相对路径取不到，跳过

    def test_dedupes_and_handles_empty(self):
        html = ('@font-face{src:url(https://a/f.woff2)}'
                '@font-face{src:url(https://a/f.woff2)}')
        self.assertEqual(fd.font_urls_from_html(html),
                         ["https://a/f.woff2"])
        self.assertEqual(fd.font_urls_from_html(""), [])
        self.assertEqual(fd.font_urls_from_html(None), [])


class TestBlockPriority(unittest.TestCase):
    """同一字形可能对应多个码位（汉字 vs 康熙部首），取号要优先常用区块。

    实测踩过：不做优先级时 U+E516 反查成了 U+2EDB「⻛」而不是 U+98CE「风」。
    """

    def test_ideograph_beats_radical(self):
        self.assertLess(fd._cp_priority(0x98CE), fd._cp_priority(0x2EDB))

    def test_priority_ordering(self):
        p = fd._cp_priority
        self.assertLess(p(0x4E00), p(0x3400))     # 基本区 < 扩展A
        self.assertLess(p(0x3400), p(0x20000))    # 扩展A < 扩展B
        self.assertLess(p(0x3000), p(0x2E80))     # 标点 < 部首
        self.assertLess(p(0xFF00), p(0x2E80))     # 全角 < 部首


class TestReferenceIndexIO(unittest.TestCase):

    def test_save_and_load_roundtrip(self):
        d = temp_subdir("fontidx")
        os.makedirs(d, exist_ok=True)
        path = os.path.join(d, "idx.json.gz")
        idx = {"a" * 40: 0x98CE, "b" * 40: 0x5929}
        size = fd.save_ref_index(idx, path)
        self.assertGreater(size, 0)
        # 确实是 gzip 且能读回
        with gzip.open(path, "rt", encoding="utf-8") as f:
            self.assertEqual(json.load(f), idx)
        self.assertEqual(fd.load_ref_index(path), idx)

    def test_load_missing_raises_with_guidance(self):
        d = temp_subdir("fontidx-miss")
        os.makedirs(d, exist_ok=True)
        with self.assertRaises(fd.FontDecodeError) as ctx:
            fd.load_ref_index(os.path.join(d, "nope.json.gz"))
        self.assertIn("build_fontmap", str(ctx.exception))


class TestFontDecoderCache(unittest.TestCase):
    """map_for_font 的落盘缓存：同字体第二次不必重算。"""

    def test_second_call_hits_cache(self):
        d = temp_subdir("fontcache")
        os.makedirs(d, exist_ok=True)
        dec = fd.FontDecoder(d)
        # 直接塞一份缓存，验证命中路径（避免真去解析字体）
        import hashlib
        fake_font = b"not-a-real-font"
        sig = hashlib.sha1(fake_font).hexdigest()[:16]
        cache_path = os.path.join(d, f"pua-{sig}.json")
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump({"map": {"58886": "风"}}, f)
        m = dec.map_for_font(fake_font)
        self.assertEqual(m, {58886: "风"})

    def test_ref_font_constants_are_sane(self):
        self.assertIn("2.002R", fd.REF_FONT_URL)
        self.assertIn("SourceHanSansSC-Normal", fd.REF_FONT_URL)
        self.assertEqual(len(fd.REF_FONT_SHA256), 16)
        self.assertTrue(fd.REF_INDEX_NAME.endswith(".json.gz"))


class TestDepsCheck(unittest.TestCase):

    def test_deps_available_shape(self):
        ok, why = fd.deps_available()
        self.assertIsInstance(ok, bool)
        self.assertIsInstance(why, str)
        if not ok:
            self.assertIn("pip install", why)


if __name__ == "__main__":
    unittest.main()
