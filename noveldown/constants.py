#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
全局常量。

[复用来源] 本家 webcopier 仓/webcopier/constants.py
许可证：内部项目（全哥创建）——本项目为其派生子项目，可自由复用。
抽取范围：DEFAULT_HEADERS / ANTICRAWL_STATUS_CODES / 版本常量。
剔除范围：字体常量（本项目无 GUI）。
"""

VERSION = "0.8.29"
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
# 【设计修正 2026-09-20】这里原本是一份「付费站黑名单」（起点/纵横/17K/晋江/
# 刺猬猫/飞卢…），把「**站点**含 VIP 内容」当成了拒绝理由。那是**粒度放错层级**：
#
#   · 「站点含 VIP 内容」——几乎所有正版站都成立，一本小说通常前几十章免费；
#   · 真正该拦的是「**该章节**需要登录/付费才能读」——这是**章节级**问题。
#
# 把站点整站拒掉，导致可用规则里只剩盗版站。现在改为：
#   **站点层只拦「项目明确声明不支持」的域名（政策旋钮，默认为空）**，
#   拦截职责下沉到目录层（VIP 标记 → 不请求）与正文层（付费墙 → 丢弃）。
# 详见 docs/FREE_ONLY.md 第 1 层。
POLICY_DENYLIST = ()   # 默认空。只放"项目明确不支持"的域名，不含任何技术判断。

# 目录/章节项上的 VIP 标记（按 **class** 匹配）
# 站点在目录里标 VIP/付费章节，最可靠的信号是给该项加 class。
# 2026-09-20 扩充：实测纵横用 `class="pay fr"` / `user_pay` 标注付费章，
# 裸 "paid" 匹配不到，故补入 pay / price / coin / charge / subscribe 等常见写法。
VIP_ITEM_CLASS_MARKERS = (
    "vip", "lock", "paid", "pay", "price", "coin", "charge", "subscribe",
    "vipchapter", "vip-chapter",
)
# 正文付费墙特征词：命中即判定为受保护内容，正文一律丢弃。
PAYWALL_MARKERS = (
    # 订阅 / 购买类
    "本章为VIP章节", "本章为付费章节", "VIP章节", "vip章节",
    "订阅后可阅读", "订阅本章", "购买本章", "付费阅读",
    "余额不足", "书币不足", "点币不足", "月票不足",
    "该章节为付费", "本章尚未购买", "试读结束",
    "本章内容需要购买", "升级为VIP",
    # 登录类
    "请先登录", "登录后可阅读", "请登录后查看",
    # **APP 墙**（2026-09-20 实测补充）
    # 不少中文小说站是「APP 优先」：web 端只放前若干章，其余章在页面上写
    # 「下载【七猫免费小说APP】，继续在APP内免费畅读全本内容」。
    # 这类占位文本本身有 70+ 字，**高于最小字数阈值**——若不显式拦截，
    # 会被当成正常正文保存下来（实测：七猫第21章正文 = 2 段 78 字的 APP 提示）。
    "APP内免费畅读", "APP内阅读", "APP内畅读", "继续在APP内",
    "请在APP", "打开APP", "下载【", "扫码下载", "客户端阅读全文",
    # 阅文系（创世/云起）的 APP 墙文案 —— 全哥实测观察到 VIP 章显示这句
    # 「上QQ阅读APP看书，第一时间看更新」。按整句收，避免「QQ阅读」这种
    # 短词误伤正文（正文里出现平台名是可能的）。
    "上QQ阅读APP看书", "第一时间看更新", "去QQ阅读APP", "QQ阅读APP",
)

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
