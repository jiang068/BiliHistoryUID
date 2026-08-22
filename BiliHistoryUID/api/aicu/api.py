"""aicu.cc 数据源抓取器（独立模块，便于维护；逻辑移植自 astrbot_plugin_aicu_analysis）.

- 查评论：GET api.aicu.cc/api/v3/search/getreply（httpx 即可，无需排队）
- 查视频弹幕 / 直播弹幕：AICU v4 需要 queue 排队获取一次性 ticket，
  且必须用 curl_cffi 的 Chrome TLS 指纹(impersonate="chrome")，否则被 Cloudflare 拦截。
  注意：弹幕接口 ps 不能为 50，否则返回 403。
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional

import httpx

from ...config import get_config

try:
    from curl_cffi.requests import AsyncSession as CurlAsyncSession
    _HAS_CURL = True
except Exception:
    _HAS_CURL = False

# AICU 接口
AICU_REPLY = "https://api.aicu.cc/api/v3/search/getreply"
AICU_QUEUE = "https://api.aicu.cc/api/v4/queue/enqueue"
AICU_VIDEO_DM = "https://api.aicu.cc/api/v4/search/getvideodm"
AICU_LIVE_DM = "https://api.aicu.cc/api/v4/search/getlivedm"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
    "accept-language": "zh-CN,zh;q=0.9",
    "origin": "https://www.aicu.cc",
    "referer": "https://www.aicu.cc/",
}


def _cookie() -> str:
    return get_config().get_config("aicu_cookie").data


async def fetch_replies(uid: str, page_size: int = 30) -> Optional[Dict[str, Any]]:
    """查评论（httpx，无需排队）."""
    headers = HEADERS.copy()
    if _cookie():
        headers["cookie"] = _cookie()
    try:
        async with httpx.AsyncClient(timeout=20, headers=headers,
                                     follow_redirects=True) as c:
            r = await c.get(AICU_REPLY, params={
                "uid": uid, "pn": "1", "ps": str(page_size), "mode": "0", "keyword": "",
            })
            if r.status_code != 200:
                return None
            return r.json()
    except Exception:
        return None


async def _fetch_danmaku(endpoint: str, uid: str, page_size: int) -> Optional[Dict[str, Any]]:
    """弹幕接口整体流程：翻单幕 queue → 拿到 ticket → 同一连接请求弹幕. 照抄插件逻辑."""
    if not _HAS_CURL:
        return None
    headers = HEADERS.copy()
    if _cookie():
        headers["cookie"] = _cookie()
    # 避开 ps=50：AICU/Cloudflare WAF 会对该值返回 403
    if page_size == 50:
        page_size = 30
    try:
        async with CurlAsyncSession(impersonate="chrome") as session:
            # 1. queue 排队获取一次性 ticket（POST）
            resp = await session.post(AICU_QUEUE, headers=headers, timeout=20)
            if resp.status_code != 200:
                return None
            ticket = (resp.json().get("data") or {}).get("ticket")
            if not ticket:
                return None

            # 2. 同一连接请求弹幕（GET，需带票）
            resp2 = await session.get(endpoint, params={
                "uid": uid, "pn": "1", "ps": str(page_size), "mode": "0",
                "keyword": "", "need_count": "true", "ticket": ticket,
            }, headers=headers, timeout=30)
            if resp2.status_code != 200:
                return None
            return resp2.json()
    except Exception:
        return None


async def fetch_video_danmaku(uid: str, page_size: int = 30) -> Optional[Dict[str, Any]]:
    """查视频弹幕."""
    return await _fetch_danmaku(AICU_VIDEO_DM, uid, page_size)


async def fetch_live_danmaku(uid: str, page_size: int = 30) -> Optional[Dict[str, Any]]:
    """查直播弹幕."""
    return await _fetch_danmaku(AICU_LIVE_DM, uid, page_size)
