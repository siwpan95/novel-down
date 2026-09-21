#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""数据模型：Book / Volume / Chapter。"""

from dataclasses import dataclass, field, asdict
from typing import List, Optional


# 章节状态
STATUS_PENDING = "pending"      # 未抓取
STATUS_OK = "ok"                # 抓取成功
STATUS_LOCKED = "locked"        # 目录标记为受保护（VIP/付费）→ 不抓
STATUS_BLOCKED = "blocked"      # 正文命中付费墙特征 → 丢弃
STATUS_EMPTY = "empty"          # 正文过短/空
STATUS_FAILED = "failed"        # 网络/解析失败

# 保护类状态：绝不允许进入导出物
PROTECTED_STATUSES = (STATUS_LOCKED, STATUS_BLOCKED)


@dataclass
class Chapter:
    """章节。index 为按章节号归一化后的阅读顺序（从 1 开始）。"""

    index: int
    title: str
    url: str
    cid: str = ""                       # 站点章节 ID（用于去重/排序/续页判定）
    volume: str = ""                    # 所属卷名（无卷为空）
    api_url: str = ""                   # 逐章正文接口地址（正文不在章节页时才用）
    extra_pages: List[str] = field(default_factory=list)   # 目录层给出的**续页** URL（多页章回）
    status: str = STATUS_PENDING
    paragraphs: List[str] = field(default_factory=list)
    source_pages: List[str] = field(default_factory=list)   # 实际请求过的 URL（含分页）
    note: str = ""                      # 状态说明（拦截原因等）
    ads_removed: int = 0
    decode_note: str = ""

    # ---------------- 派生属性 ----------------
    @property
    def char_count(self) -> int:
        return sum(len(p) for p in self.paragraphs)

    @property
    def text(self) -> str:
        return "\n".join(self.paragraphs)

    @property
    def is_protected(self) -> bool:
        """是否属于受保护内容（绝不可导出）。"""
        return self.status in PROTECTED_STATUSES

    @property
    def has_content(self) -> bool:
        return self.status == STATUS_OK and self.char_count > 0

    def to_dict(self) -> dict:
        d = asdict(self)
        d["char_count"] = self.char_count
        d["is_protected"] = self.is_protected
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Chapter":
        return cls(
            index=d.get("index", 0),
            title=d.get("title", ""),
            url=d.get("url", ""),
            cid=d.get("cid", ""),
            volume=d.get("volume", ""),
            api_url=d.get("api_url", ""),
            extra_pages=list(d.get("extra_pages") or []),
            status=d.get("status", STATUS_PENDING),
            paragraphs=list(d.get("paragraphs") or []),
            source_pages=list(d.get("source_pages") or []),
            note=d.get("note", ""),
            ads_removed=d.get("ads_removed", 0),
            decode_note=d.get("decode_note", ""),
        )


@dataclass
class Book:
    """书籍。"""

    site: str                                   # 站点规则 id
    book_id: str                                # 站点书籍 ID
    url: str                                    # 书籍主页 URL
    title: str = ""
    author: str = ""
    intro: str = ""
    cover: str = ""
    status: str = ""
    volumes: List[str] = field(default_factory=list)
    chapters: List[Chapter] = field(default_factory=list)
    # 目录排序策略：cid_numeric_asc / document_order。
    # 校对时据此决定要不要检查「章节号单调」——document_order 的站点
    # （雪花 ID，如番茄/七猫）本来就不单调，检查它只会产生误报。
    catalog_sort: str = "cid_numeric_asc"

    # ---------------- 派生属性 ----------------
    @property
    def ok_chapters(self) -> List[Chapter]:
        """可导出的章节（明确排除受保护内容）。"""
        return [c for c in self.chapters if c.has_content]

    @property
    def protected_chapters(self) -> List[Chapter]:
        return [c for c in self.chapters if c.is_protected]

    @property
    def failed_chapters(self) -> List[Chapter]:
        from .models import STATUS_PENDING  # noqa
        return [c for c in self.chapters
                if c.status in (STATUS_FAILED, STATUS_EMPTY)]

    @property
    def total_chars(self) -> int:
        return sum(c.char_count for c in self.chapters)

    def stats(self) -> dict:
        by_status = {}
        for c in self.chapters:
            by_status[c.status] = by_status.get(c.status, 0) + 1
        return {
            "site": self.site,
            "book_id": self.book_id,
            "title": self.title,
            "author": self.author,
            "chapters_total": len(self.chapters),
            "by_status": by_status,
            "exportable": len(self.ok_chapters),
            "protected": len(self.protected_chapters),
            "total_chars": self.total_chars,
        }

    def to_dict(self) -> dict:
        return {
            "site": self.site,
            "book_id": self.book_id,
            "url": self.url,
            "title": self.title,
            "author": self.author,
            "intro": self.intro,
            "cover": self.cover,
            "status": self.status,
            "volumes": self.volumes,
            "chapters": [c.to_dict() for c in self.chapters],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Book":
        b = cls(
            site=d.get("site", ""),
            book_id=d.get("book_id", ""),
            url=d.get("url", ""),
            title=d.get("title", ""),
            author=d.get("author", ""),
            intro=d.get("intro", ""),
            cover=d.get("cover", ""),
            status=d.get("status", ""),
            volumes=list(d.get("volumes") or []),
        )
        b.chapters = [Chapter.from_dict(x) for x in (d.get("chapters") or [])]
        return b
