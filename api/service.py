"""聚合各数据源，产出卡片渲染所需的统一结构（并发抓取，各自兜底）。"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional

from ..config import get_config
from .danmakus import api as dm_api
from .aicu import api as aicu_api
from .inspector import (
    fetch_bili_card,
    analyze_content,
    analyze_live,
    novice_probability,
    analyze_activity,
    compute_allegiance,
    cross_check_allegiance,
    analyze_style,
    build_evaluation,
)
from ..material.inspector_data import PIE_COLORS

_SOURCE_BY_MODE = {
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


def _safe_format_ts(ts) -> str:
    try:
        t = float(ts)
        if t <= 0:
            return "近期"
        if t > 1e11:
            t = t / 1000.0
        return datetime.fromtimestamp(t).strftime("%Y/%m/%d")
    except Exception:
        return "近期"


def _ai_summary(items: List[Dict[str, Any]], uid: str, evaluation: str) -> str:
    danmaku_cnt = sum(1 for i in items if i["kind"] == "danmaku")
    comment_cnt = sum(1 for i in items if i["kind"] == "comment")
    return (
        f"该用户近期共 {len(items)} 条痕迹（弹幕 {danmaku_cnt}、评论 {comment_cnt}）。"
        f"画像总结：{evaluation}"
    )


async def build_card(uid: str, enable_ai: bool, mode: str = "card") -> Dict[str, Any]:
    page_size = get_config().get_config("history_page_size").data
    need = _SOURCE_BY_MODE.get(mode, _SOURCE_BY_MODE["card"])

    # 1. 并发抓取：B 站官方卡片 + aicu/danmakus 各源
    tasks = {s: _FETCHERS[s](uid, page_size) for s in need}
    tasks["bili_card"] = fetch_bili_card(uid)

    gathered = await asyncio.gather(*tasks.values(), return_exceptions=True)
    src_map = {s: v for s, v in zip(tasks.keys(), gathered)}

    bili_card_raw = src_map.get("bili_card")
    bili_card = bili_card_raw if isinstance(bili_card_raw, dict) and not isinstance(bili_card_raw, Exception) else {
        "name": f"用户{uid}", "face": "", "sex": "保密", "sign": "", "level": 0, "fans": 0, "following": 0, "official": "", "vip": ""
    }

    per_src: Dict[str, List[Dict[str, Any]]] = {}
    for src, data in src_map.items():
        if src == "bili_card" or isinstance(data, Exception) or not data:
            continue
        per_src[src] = _parse(src, data)

    # 评论置顶，随后视频、直播
    priority = {"aicu_reply": 0, "aicu_video": 1, "aicu_live": 2, "danmakus": 2}
    items: List[Dict[str, Any]] = []
    for src in sorted(per_src.keys(), key=lambda s: priority.get(s, 9)):
        items.extend(per_src[src])

    checked = [k for k, v in src_map.items()
               if k != "bili_card" and not isinstance(v, Exception) and v]

    # 2. 深度运行 Account Inspector 算法
    live_items = [i for i in items if i.get("source") in ("aicu_live", "danmakus")]
    cmt_and_video_items = [i for i in items if i.get("source") in ("aicu_reply", "aicu_video")]

    content = analyze_content(items)
    live_analyzed = analyze_live(live_items)
    novice = novice_probability(bili_card)
    activity = analyze_activity(cmt_and_video_items)
    aleg_raw = compute_allegiance(bili_card, live_analyzed.get("rooms", []), content)
    aleg_check = cross_check_allegiance(aleg_raw, content, live_analyzed.get("liveAttitude", {}))
    style = analyze_style(content, activity, len(items), aleg_check)
    evaluation = build_evaluation(content, style, activity, novice, aleg_check)

    # 3. 构建圆饼图 Conic Gradient CSS
    circle_slices = content.get("circleSlices", [])
    tot_weight = sum(v for _, v in circle_slices) or 1.0
    pie_data = []
    gradient_parts = []
    cur_deg = 0.0

    for idx, (label, val) in enumerate(circle_slices[:8]):
        pct = max(1, int(round(val / tot_weight * 100)))
        color = PIE_COLORS[idx % len(PIE_COLORS)]
        pie_data.append((label, pct, color))
        next_deg = cur_deg + (pct / 100.0) * 360.0
        gradient_parts.append(f"{color} {cur_deg:.1f}deg {next_deg:.1f}deg")
        cur_deg = next_deg

    conic_css = ", ".join(gradient_parts) if gradient_parts else "#4C9AFF 0deg 360deg"

    # 4. 证据发言选择 (优先攻击性发言，补全最新发言至 25 条)
    evidence_items = []
    seen_texts = set()

    for it in items:
        raw_t = str(it.get("text") or it.get("content", ""))
        tone = it.get("tone") or {}
        if raw_t not in seen_texts:
            seen_texts.add(raw_t)
            evidence_items.append(it)
        if len(evidence_items) >= 25:
            break

    # 5. 直播动向格式化
    top_rooms = live_analyzed.get("rooms", [])[:5]

    analysis = {
        "card": bili_card,
        "style_tag": style.get("label", "正常用户 / 玩家"),
        "style_color": style.get("color", "#36B37E"),
        "style_desc": evaluation,
        "style_reason": "；".join(style.get("reasons", ["多圈子均匀分布，发言平和"])),
        "certs": aleg_check.get("checked", []),
        "suspect_warn": aleg_check.get("suspect"),
        "live_dynamics": top_rooms,
        "total_live": live_analyzed.get("total", 0),
        "freshness": _safe_format_ts(live_analyzed.get("latestTs")),
        "top_entities": content.get("topEntities", [])[:6],
        "camp_info": content.get("campInfo", [])[:4],
        "toxic_ratio": content.get("toxicRatio", 0),
        "live_toxic_ratio": content.get("liveToxicRatio", 0),
        "hard_count": content.get("hardCount", 0),
        "meme_count": content.get("memeCount", 0),
        "light_count": content.get("lightCount", 0),
        "top_memes": content.get("topMemes", []),
        "pie_data": pie_data,
        "conic_gradient_css": conic_css,
        "total_comments": len(cmt_and_video_items),
        "total_danmaku": len(live_items),
        "sampled_count": len(items),
        "time_span_hours": activity.get("spanH", 0.0),
        "unique_videos": activity.get("uniqueVideos", 1),
        "burst": activity.get("burst", False),
        "alt_account_prob": novice.get("p", 10),
        "alt_band": novice.get("band", "偏低"),
        "evidence_items": evidence_items,
    }

    summary_text = _ai_summary(items, uid, evaluation) if enable_ai else None

    return {
        "uid": uid,
        "enable_ai_summary": enable_ai,
        "summary": summary_text,
        "items": items,
        "checked_sources": checked,
        "generate_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "analysis": analysis,
    }


def _ts(t, ms: bool = True) -> str:
    try:
        t = float(t)
    except Exception:
        return "--"
    if t <= 0:
        return "--"
    if not ms:
        t = t * 1000
    try:
        return datetime.fromtimestamp(t / 1000).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return "--"


def _push(out, **kw):
    base = {"content": "", "text": "", "time": 0, "readable_time": "--",
            "source_head": "", "kind": "record", "type": -1}
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
              source="aicu_reply", kind="comment", type=-1)
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
              readable_time=_ts(dm.get("ctime", 0), ms=False), source_head=head,
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
              readable_time=_ts(dm.get("ts", 0), ms=False), source_head=head,
              source="aicu_live", kind="danmaku", type=0, actor=dm.get("uname", ""))
    return out
