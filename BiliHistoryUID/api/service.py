"""聚合各数据源，产出卡片渲染所需的统一结构（并发抓取，各自兜底）。"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional

from ..config import get_config
from .danmakus import api as dm_api
from .aicu import api as aicu_api


def _ai_summary(items: List[Dict[str, Any]], uid: str) -> str:
    danmaku_cnt = sum(1 for i in items if i["kind"] == "danmaku")
    comment_cnt = sum(1 for i in items if i["kind"] == "comment")
    tx = "、".join(str(i.get("content", "")) for i in items[:5] if i.get("content"))
    if not items:
        return "未获取到有效痕迹。"
    return (
        f"该用户近期共 {len(items)} 条痕迹（弹幕 {danmaku_cnt}、评论 {comment_cnt}）。"
        f"片段：{tx}。（AI 总结占位，待接线 LLM）"
    )


_SOURCE_BY_MODE = {
    # 板块 -> 需抓取的数据源
    "card": ["danmakus", "aicu_reply", "aicu_video", "aicu_live"],
    "reply": ["aicu_reply"],
    "video": ["aicu_video"],
    "live": ["danmakus", "aicu_live"],
}

_FETCHERS = {
    "danmakus": dm_api.fetch_history,
    "aicu_reply": aicu_api.fetch_replies,
    "aicu_video": aicu_api.fetch_video_danmaku,
    "aicu_live": aicu_api.fetch_live_danmaku,
}


async def build_card(uid: str, enable_ai: bool, mode: str = "card") -> Dict[str, Any]:
    page_size = get_config().get_config("history_page_size").data
    need = _SOURCE_BY_MODE.get(mode, _SOURCE_BY_MODE["card"])

    tasks = {s: _FETCHERS[s](uid, page_size) for s in need}
    gathered = await asyncio.gather(*tasks.values(), return_exceptions=True)
    src_map = {s: v for s, v in zip(tasks.keys(), gathered)}

    per_src: Dict[str, List[Dict[str, Any]]] = {}
    for src, data in src_map.items():
        if isinstance(data, Exception) or not data:
            continue
        per_src[src] = _parse(src, data)

    # 评论置顶，随后视频、直播，同类内保持原顺序
    priority = {"aicu_reply": 0, "aicu_video": 1, "aicu_live": 2, "danmakus": 2}
    items: List[Dict[str, Any]] = []
    for src in sorted(per_src.keys(), key=lambda s: priority.get(s, 9)):
        items.extend(per_src[src])

    checked = [k for k, v in src_map.items()
               if not isinstance(v, Exception) and v]

    return {
        "uid": uid,
        "enable_ai_summary": enable_ai,
        "summary": _ai_summary(items, uid) if enable_ai else None,
        "items": items,
        "checked_sources": checked,
        "generate_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def _ts(t, ms: bool = True) -> str:
    try:
        t = float(t)
    except Exception:
        return "--"
    if t <= 0:
        return "--"
    if not ms:
        # 部分接口直接给秒级时间戳（如 aicu 评论的 time 字段）
        t = t * 1000
    try:
        return datetime.fromtimestamp(t / 1000).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return "--"


def _push(out, **kw):
    base = {"content": "", "text": "", "time": 0, "readable_time": "--",
            "source_head": "", "kind": "record", "type": -1}
    # source 由调用方在 kw 中给出；kind 也是
    base.update(kw)
    out.append(base)


def _parse(src: str, raw: dict) -> List[Dict[str, Any]]:
    if src == "danmakus":
        return _parse_danmakus(raw)
    if src == "aicu_reply":
        return _parse_aicu_replies(raw)
    if src == "aicu_video":
        return _parse_aicu_video(raw)
    if src == "aicu_live":
        return _parse_aicu_live(raw)
    return []


def _parse_danmakus(raw: dict) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if raw.get("code") != 200:
        return out
    for it in ((raw.get("data") or {}).get("items") or []):
        ch = it.get("channel") or {}
        live = it.get("live") or {}
        head = "·".join(x for x in (ch.get("uName", ""), live.get("title", "")) if x) or "直播间"
        for rec in (it.get("danmakus") or {}).get("records") or []:
            typ = rec.get("type", 0)
            payload = rec.get("payload") or {}
            raw_t = payload.get("rawText", "")
            gift = payload.get("name", "") if payload.get("price") is not None else ""
            text = raw_t or gift or ""
            label = {0: "弹幕", 1: "醒目留言", 2: "礼物", 3: "SC", 4: "进场"}.get(typ, "记录")
            _push(out, content=text or label, text=text, time=rec.get("ts", 0),
                  readable_time=_ts(rec.get("ts", 0)), source_head=head,
                  source="danmakus", kind="danmaku", type=typ)
    return out


def _parse_aicu_replies(raw: dict) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if raw.get("code") != 0:
        return out
    block = raw.get("data", {}) or {}
    if isinstance(block, dict):
        block = block.get("data", block)
    for row in (block.get("replies") or []):
        msg = row.get("message", "")
        _push(out, content=msg, text=msg, time=row.get("time", 0),
              readable_time=_ts(row.get("time", 0), ms=False), source_head="B站评论",
              source="aicu", kind="comment", type=-1)
    return out


def _parse_aicu_video(raw: dict) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if raw.get("code") != 0:
        return out
    data = raw.get("data") or {}
    for dm in (data.get("videodmlist") or []):
        content = dm.get("content", "")
        progress = int((dm.get("progress") or 0) // 1000)
        mm, ss = divmod(progress, 60)
        head = f"视频弹幕 {mm:02d}:{ss:02d}"
        _push(out, content=content, text=content, time=dm.get("ctime", 0),
              readable_time=_ts(dm.get("ctime", 0)), source_head=head,
              source="aicu_video", kind="danmaku", type=0)
    return out


def _parse_aicu_live(raw: dict) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if raw.get("code") != 0:
        return out
    data = raw.get("data") or {}
    for room in (data.get("list") or []):
        ri = room.get("roominfo") or {}
        head = ri.get("roomname") or ri.get("upname") or "直播间"
        for dm in (room.get("danmu") or []):
            text = dm.get("text", "")
            _push(out, content=text, text=text, time=dm.get("ts", 0),
                  readable_time=_ts(dm.get("ts", 0)), source_head=head,
                  source="aicu_live", kind="danmaku", type=0, actor=dm.get("uname", ""))
    return out
