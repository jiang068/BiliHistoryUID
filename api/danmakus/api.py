"""danmakus 系数据源抓取器（独立模块，便于维护）.

直播弹幕历史：
    GET /api/v3/users/{uid}/history?page=1&pageSize=N
已验证返回结构，实际 API 主机可通过配置 danmakus_base 调整（默认 ukamnads.icu）。
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import httpx

from ...config import get_config

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36 Edg/150.0.0.0",
    "accept-language": "zh-CN,zh;q=0.9",
}


async def _get(url: str, params: Optional[Dict] = None) -> Optional[Dict[str, Any]]:
    try:
        async with httpx.AsyncClient(timeout=20, headers=DEFAULT_HEADERS,
                                     follow_redirects=True) as c:
            r = await c.get(url, params=params)
            if r.status_code != 200:
                return None
            return r.json()
    except Exception:
        return None


async def fetch_history(uid: str, page_size: int) -> Optional[Dict[str, Any]]:
    """用户在直播间的弹幕历史（第 1 页）. """
    host = get_config().get_config("danmakus_base").data
    url = f"https://{host}/api/v3/users/{uid}/history"
    return await _get(url, {"page": 1, "pageSize": page_size})
