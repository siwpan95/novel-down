#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HTTP 客户端层：请求发送、退避重试、代理、限速。

[复用来源] 本家 webcopier 仓/webcopier/http_client.py
许可证：内部项目（全哥创建）。
抽取范围：parse_proxy / build_headers / auto_referer / http_get + 三个后端实现。
改造点（重要）：
  1. **彻底移除 Cookie / http_post / 登录相关路径**——本项目仅抓取免费章节，
     不存在任何凭据注入或会话提权能力（免费章节硬约束）。
  2. 移除 requests_cache 依赖（章节级缓存由 state.py 自己管理，粒度更合适）。
  3. 移除 _curl_impersonate 透传魔法键，改为显式参数传递。
  4. **新增连接池**（本项目的改进点）：见下方 _thread_session 说明。
"""

import random
import threading
import time
import re
from urllib.parse import urlparse

import requests

from .constants import DEFAULT_HEADERS, ANTICRAWL_STATUS_CODES

try:
    from curl_cffi import requests as curl_requests
    _HAS_CURL_CFFI = True
except ImportError:  # pragma: no cover - 环境相关
    _HAS_CURL_CFFI = False


# ============================================================
#  连接池（相对 webcopier 复用层的**改进点**）
# ============================================================
# webcopier 的 http_get 每次调用 requests.get()，即每次重建 TCP + TLS 连接。
# 实测（2026-09-20，biqu520.net）：单次请求 3.7s，绝大部分是握手开销；
# 抓一本 2653 章的书会因此额外多花数小时。
# 这里改为「每线程一个 Session」复用连接；但**每次请求后清空 cookie jar**，
# 确保不承载任何用户凭据（免费章节硬约束）——连接复用只发生在传输层。
_tls = threading.local()


def _thread_session():
    sess = getattr(_tls, "session", None)
    if sess is None:
        sess = requests.Session()
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=8, pool_maxsize=8, max_retries=0)
        sess.mount("https://", adapter)
        sess.mount("http://", adapter)
        _tls.session = sess
    return sess


def _thread_curl_session():
    sess = getattr(_tls, "curl_session", None)
    if sess is None and _HAS_CURL_CFFI:
        sess = curl_requests.Session()
        _tls.curl_session = sess
    return sess


def close_sessions():
    """关闭当前线程的 Session（进程退出前可调用）。"""
    sess = getattr(_tls, "session", None)
    if sess is not None:
        try:
            sess.close()
        except Exception:
            pass
        _tls.session = None


def parse_proxy(proxy_str):
    """解析代理字符串。

    支持 http://host:port、http://user:pass@host:port、socks5://host:port
    Returns: {"http": ..., "https": ...} 或 None
    """
    if not proxy_str or not proxy_str.strip():
        return None
    return {"http": proxy_str.strip(), "https": proxy_str.strip()}


def build_headers(identity=None, referer=None, custom_ua=None) -> dict:
    """构建请求头。

    注意：**不接受 Cookie 参数**（免费章节硬约束）。

    Args:
        identity: 身份字典（来自 identity_manager）
        referer: 可选 Referer URL
        custom_ua: 可选自定义 UA（优先级高于 identity）

    Returns:
        完整请求头 dict
    """
    headers = dict(DEFAULT_HEADERS)

    if identity and isinstance(identity, dict):
        if identity.get("ua"):
            headers["User-Agent"] = identity["ua"]
        id_headers = identity.get("headers", {})
        if id_headers:
            for key in ("sec-ch-ua", "sec-ch-ua-mobile", "sec-ch-ua-platform"):
                if key in id_headers:
                    headers[key] = id_headers[key]

    if custom_ua:
        headers["User-Agent"] = custom_ua

    if referer:
        headers["Referer"] = referer

    return headers


def auto_referer(url) -> str:
    """根据 URL 自动生成 Referer（取域名根路径）。"""
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}/"


def _fix_encoding(resp):
    """修正编码：requests 对中文站常误判为 ISO-8859-1。"""
    if resp.encoding is None or resp.encoding.lower() == "iso-8859-1":
        resp.encoding = resp.apparent_encoding or "utf-8"
    return resp


# ⚠ 内网地址段（审计 #12 的 SSRF 纵深）。**刻意不含回环 127.0.0.1** ——
#   本地合成站的测试要用它，而且回环并不属于「内网服务」那一类真正的 SSRF 目标。
_PRIVATE_HOST_RE = re.compile(
    r"^(?:"
    r"10\."                       # RFC1918
    r"|192\.168\."
    r"|172\.(?:1[6-9]|2\d|3[01])\."
    r"|169\.254\."               # 链路本地：云元数据服务（169.254.169.254）
    r"|0\.0\.0\.0$"             # 「本机」的另一种写法
    r"|\[?::1\]?$"               # IPv6 回环的显式写法（不含裸 127.*）
    r"|localhost$"
    r")", re.I)

# 提示：这里**故意**不把 127.0.0.1 / ::1 列进去（见上）。若将来要做更严的白名单
# （只允许该规则的域名），注意会误伤「入口域 302 到真实承载域」的跳转型站点 ——
# 本仓有若干条这种规则（见 docs/NEW_SITES_PLAN.md 的「跳转型」小节）。


def _reject_private_host(final_url: str, original: str):
    """响应最终落到了内网地址就报错。

    ⚠ 说明「为什么事后校验也有效」：SSRF 的危害是**借我们的网络位置读到内网服务的响应**。
    这里是**已经跟随完重定向、拿到响应之后**才判——请求确实发出去了，
    但**响应不会被交回给调用方**，攻击者拿不到数据。要完全阻止请求发出，
    就得 `allow_redirects=False` 自己逐跳走，那会改变所有调用方的语义（且要处理
    跳转型站点），收益不成比例。
    """
    from urllib.parse import urlparse
    host = (urlparse(final_url).hostname or "")
    if _PRIVATE_HOST_RE.match(host):
        raise requests.exceptions.ConnectionError(
            f"重定向落到了内网/链路本地地址，已拒绝使用该响应："
            f"{host}（起点 {original}）")


def http_get(url, headers=None, timeout=30, retries=2, proxies=None,
             verify=True, use_curl_cffi=False, impersonate="chrome120",
             on_retry=None):
    """HTTP GET 请求（含自适应退避重试）。

    Args:
        url: 目标 URL
        headers: 请求头（None 则用 DEFAULT_HEADERS）
        timeout: 超时秒数
        retries: 额外重试次数
        proxies: 代理字典
        verify: SSL 验证
        use_curl_cffi: 使用 curl_cffi TLS 指纹伪装
        impersonate: curl_cffi 指纹别名
        on_retry: 可选回调 on_retry(attempt, exc, sleep_secs)
        （重定向的内网防护见 `_reject_private_host`：始终生效，不需要调用方传参。）

    Returns:
        requests.Response
    """
    req_headers = dict(DEFAULT_HEADERS)
    if headers:
        req_headers.update(headers)

    last_error = None
    for attempt in range(retries + 1):
        if attempt > 0:
            backoff = min(2 ** attempt, 60)
            if on_retry:
                on_retry(attempt, last_error, backoff)
            time.sleep(backoff)
        try:
            if use_curl_cffi and _HAS_CURL_CFFI:
                sess = _thread_curl_session()
                resp = sess.get(
                    url, headers=req_headers, timeout=timeout,
                    proxies=proxies, allow_redirects=True, verify=verify,
                    impersonate=impersonate,
                )
                # ⚠ 与 requests 路径保持一致：**不承载任何凭据**，用完即清
                #   （审计 #14：原来只清了 requests 的 cookie jar，curl 这边没清，
                #    与 README / FREE_ONLY 里「无 Cookie」的表述不符）。
                try:
                    sess.cookies.clear()
                except Exception:
                    pass
            else:
                sess = _thread_session()
                resp = sess.get(
                    url, headers=req_headers, timeout=timeout,
                    proxies=proxies, allow_redirects=True, verify=verify,
                )
                # 不承载任何凭据：用完即清，连接复用只在传输层
                try:
                    sess.cookies.clear()
                except Exception:
                    pass
            resp.raise_for_status()
            # ⚠ 审计 #12：命中站点若 302 到内网/云元数据地址，这里拒绝交出响应
            _reject_private_host(getattr(resp, "url", "") or url, url)
            return _fix_encoding(resp)
        except requests.exceptions.HTTPError as e:
            resp = getattr(e, "response", None)
            if resp is not None and resp.status_code in ANTICRAWL_STATUS_CODES:
                # 反爬状态码：额外等待，交由上层轮换身份
                wait = 5 * (attempt + 1)
                if on_retry:
                    on_retry(attempt, e, wait)
                time.sleep(wait)
            last_error = e
        except Exception as e:  # 网络层异常（含 curl_cffi 的异常族）
            last_error = e
    raise last_error


def fetch_text(url, headers=None, timeout=30, retries=2, proxies=None,
               use_curl_cffi=False, impersonate="chrome120", on_retry=None):
    """便捷封装：返回响应文本。"""
    resp = http_get(url, headers=headers, timeout=timeout, retries=retries,
                    proxies=proxies, use_curl_cffi=use_curl_cffi,
                    impersonate=impersonate, on_retry=on_retry)
    return resp.text
