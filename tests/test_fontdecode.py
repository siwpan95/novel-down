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

    def test_shipped_index_present_and_loadable(self):
        """运行时零参考字体依赖：随仓轮廓索引必须在，且可读。

        这是「不需要联网、不需要 17MB 参考字体」的唯一凭据 —— 一旦缺失，
        番茄这类站点会直接解码失败，所以用单测看住它。
        """
        self.assertTrue(os.path.exists(fd.SHIPPED_INDEX),
                        f"随仓索引缺失：{fd.SHIPPED_INDEX}")
        idx = fd.load_ref_index(fd.SHIPPED_INDEX)
        # 4.4 万条量级；给个宽松下界，避免误判同时能发现「索引被截断」
        self.assertGreater(len(idx), 40000)
        self.assertTrue(all(len(h) == 12 for h in list(idx)[:50]))  # 6 字节哈希
        self.assertEqual(fd.REF_INDEX_BIN, "sourcehan-sc-2.002.bin")

    def test_no_runtime_reference_font_or_download(self):
        """运行时模块不得残留参考字体 URL / 下载分支。"""
        self.assertFalse(hasattr(fd, "REF_FONT_URL"))
        self.assertFalse(hasattr(fd, "REF_FONT_SHA256"))
        dec = fd.FontDecoder(temp_subdir("nodl"))
        # ref_index 不接受下载参数
        import inspect
        params = inspect.signature(dec.ref_index).parameters
        self.assertNotIn("build_if_missing", params)
        self.assertNotIn("downloader", params)
        params2 = inspect.signature(dec.map_for_font).parameters
        self.assertNotIn("build_if_missing", params2)
        self.assertNotIn("downloader", params2)


class TestDepsCheck(unittest.TestCase):

    def test_deps_available_shape(self):
        ok, why = fd.deps_available()
        self.assertIsInstance(ok, bool)
        self.assertIsInstance(why, str)
        if not ok:
            self.assertIn("pip install", why)


class TestGlyphNameDecoding(unittest.TestCase):
    """途径一：按 glyph 名解码（比轮廓匹配便宜得多，且不需参考字体）。

    实测来源：`_ref/2.txt` 记录起点老版反爬就是这一套 ——
    glyph 名直接是 `zero`/`one`/…/`period`，数字在 HTML 里是乱码但仍可还原。
    """

    def test_english_word_names(self):
        for name, ch in (("zero", "0"), ("nine", "9"), ("period", "."),
                         ("comma", ","), ("hyphen", "-"), ("space", " ")):
            self.assertEqual(fd.char_from_glyph_name(name), ch, name)

    def test_word_names_with_suffix(self):
        self.assertEqual(fd.char_from_glyph_name("zero.sc"), "0")
        self.assertEqual(fd.char_from_glyph_name("one.alt"), "1")

    def test_unicase_names(self):
        self.assertEqual(fd.char_from_glyph_name("uni98CE"), "风")
        self.assertEqual(fd.char_from_glyph_name("uni4E00"), "一")
        self.assertEqual(fd.char_from_glyph_name("uni98CE.alt"), "风")
        self.assertEqual(fd.char_from_glyph_name("u5929"), "天")
        self.assertEqual(fd.char_from_glyph_name("U+98CE"), "风")

    def test_adobe_style_ideograph_names(self):
        self.assertEqual(
            fd.char_from_glyph_name("CJK UNIFIED IDEOGRAPH-98CE"), "风")

    def test_single_char_names(self):
        self.assertEqual(fd.char_from_glyph_name("A"), "A")
        self.assertEqual(fd.char_from_glyph_name("5"), "5")

    def test_index_names_are_rejected(self):
        """cidNNNNN / gidNNNNN 是索引不是字符 —— 必须明确放弃，别瞎猜。

        这正是番茄那种子集字体的形态（gid58646），只能走轮廓匹配。
        """
        self.assertIsNone(fd.char_from_glyph_name("gid58646"))
        self.assertIsNone(fd.char_from_glyph_name("cid44285"))
        self.assertIsNone(fd.char_from_glyph_name(".notdef"))
        self.assertIsNone(fd.char_from_glyph_name(""))

    def test_map_from_glyph_names_coverage(self):
        pairs = [(0xE000, "zero"), (0xE001, "one"), (0xE002, "gid123")]
        m, cov = fd.map_from_glyph_names(pairs)
        self.assertEqual(m, {0xE000: "0", 0xE001: "1"})
        self.assertAlmostEqual(cov, 2 / 3)
        m2, cov2 = fd.map_from_glyph_names([])
        self.assertEqual((m2, cov2), ({}, 0.0))

    def test_threshold_decides_path(self):
        """名字能解出 ≥60% 就走 glyph_name；否则报告需要轮廓匹配。"""
        # 用假的「字体字典」直接测判定逻辑（不构造真字体）
        good = [(0xE000 + i, n) for i, n in enumerate(
            ["zero", "one", "two", "three", "four", "gid9"])]
        m, cov = fd.map_from_glyph_names(good)
        self.assertGreaterEqual(cov, 0.6)
        bad = [(0xE000 + i, f"gid{i}") for i in range(6)]
        m2, cov2 = fd.map_from_glyph_names(bad)
        self.assertEqual(cov2, 0.0)


if __name__ == "__main__":
    unittest.main()
