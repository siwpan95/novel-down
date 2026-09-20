#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
novel-down · 读书爬虫（仅免费章节）

一个规则驱动的网络小说离线阅读工具：
  目录发现 → 并发抓取 → 免费章节硬拦截 → 校对 → TXT/Markdown/EPUB/单文件HTML 导出

硬约束：本项目**只处理免费章节**，不含任何登录、Cookie、购买或付费墙绕过能力。
详见 docs/FREE_ONLY.md。
"""

from .constants import VERSION, APP_TITLE  # noqa: F401
from .engine import Downloader              # noqa: F401
from .models import Book, Chapter           # noqa: F401
from .rules import load_rules, find_rule    # noqa: F401

__version__ = VERSION
__all__ = ["Downloader", "Book", "Chapter", "load_rules", "find_rule", "VERSION"]
