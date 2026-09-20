#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
全局常量。

[复用来源] G:/repos/webcopier/webcopier/constants.py
许可证：内部项目（全哥创建）——本项目为其派生子项目，可自由复用。
抽取范围：DEFAULT_HEADERS / ANTICRAWL_STATUS_CODES / 版本常量。
剔除范围：字体常量（本项目无 GUI）。
"""

VERSION = "0.1.0"
APP_TITLE = f"novel-down 读书爬虫 v{VERSION}"

# ============================================================
#  默认 HTTP 请求头（不含 UA，由 identity_manager 注入）
# ============================================================
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
              "image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,zh-TW;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
}

# 反爬状态码（命中则延长等待并触发身份轮换）
ANTICRAWL_STATUS_CODES = (403, 412, 429, 503)

# ============================================================
#  免费章节硬约束
# ============================================================
# 明确的付费/需登录站点黑名单：命中即拒绝，不提供规则，不尝试解析。
# 本项目仅用于免费章节，绝不涉及 VIP 付费内容。
PAID_SITE_DENYLIST = (
    "qidian.com", "book.qidian.com",          # 起点（VIP 章节）
    "zongheng.com", "book.zongheng.com",      # 纵横（VIP 章节）
    "17k.com",                                # 17K（VIP 章节）
    "jjwxc.net", "jjwxc.com",                 # 晋江（VIP 章节）
    "ciweimao.com",                           # 刺猬猫（VIP 章节）
    "faloo.com",                              # 飞卢（VIP 章节）
    "hongxiu.com", "xxsy.net",                # 红袖（VIP 章节）
    "readnovel.com",                          # 云起书院
    "shuqi.com", "qidian"                     # 书旗 / 起点别名
)

# 正文付费墙特征词：命中即判定为受保护内容，正文一律丢弃。
PAYWALL_MARKERS = (
    "本章为VIP章节", "本章为付费章节", "VIP章节", "vip章节",
    "订阅后可阅读", "订阅本章", "购买本章", "付费阅读",
    "余额不足", "书币不足", "点币不足", "月票不足",
    "请先登录", "登录后可阅读", "请登录后查看",
    "该章节为付费", "本章尚未购买", "试读结束",
    "本章内容需要购买", "升级为VIP",
)

# 目录/章节项上的 VIP 标记（按 **class** 匹配）
# 站点在目录里标 VIP 章节，最可靠的信号是给该项加 class（vip / lock / paid…）。
VIP_ITEM_CLASS_MARKERS = ("vip", "lock", "paid", "vipchapter", "vip-chapter")

# 目录/章节项上的 VIP 标记（按 **标题文本** 匹配）——只收「徽章形态」的写法。
#
# 设计取舍（实测踩过）：早期版本把裸词「付费」「订阅」也纳入文本匹配，
# 结果一个正常章节「第3章 付费墙占位」被误锁成 locked——标题里的普通词
# 会把合法免费章节整批丢掉。因此文本匹配只认「明显是徽章」的形态：
# 括号包裹的 VIP、带「章节」后缀、或语义上不可能是正文标题的词。
VIP_ITEM_TEXT_MARKERS = (
    "（vip）", "(vip)", "【vip】", "[vip]",
    "vip章节", "vip章", "会员章节", "会员专享", "订阅章节",
    "付费章节", "需购买", "尚未购买",
)

# 正文最小字数：低于该值判定为抓取失败或付费墙占位，不计入正文。
MIN_CHAPTER_CHARS = 50

# ============================================================
#  默认运行参数
# ============================================================
DEFAULT_CONFIG = {
    "save_dir": "output",
    "concurrency": 4,
    "delay": 1.2,
    "jitter": 0.8,
    "timeout": 30,
    "retries": 3,
    "use_curl_cffi": False,
    "proxy": "",
    "max_chapters": 0,          # 0 = 不限制
    "formats": ["txt", "md", "epub", "html"],
    "proofread": True,
}
