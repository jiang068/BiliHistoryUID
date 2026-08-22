"""B站查成分 (Account Inspector) 核心分析引擎 Python 实现

100% 忠实对齐原版 JS 脚本的所有算法与规则：
- 真实 B 站官方 Card 资料抓取
- 实体与阵营识别 (ENTITIES)
- 语气、辱骂、阴阳怪气、两义梗与单字防误判检测 (tone_of)
- 关注度与阵营态度交叉矩阵 (analyze_content)
- 直播动向分析与直播间态度 (analyze_live)
- 认证归属与一致性检验 (compute_allegiance, cross_check_allegiance)
- 风格研判决策树 (analyze_style)
- 客观自然语言摘要 (build_evaluation)
- 疑似小号启发式测算 (novice_probability)
- 爆发与活动轨迹 (analyze_activity)
"""

from __future__ import annotations

import math
import re
from typing import Any, Dict, List, Optional, Set, Tuple

import httpx

from ..material.inspector_data import (
    ENTITIES,
    HARD_ATTACK,
    MEME_WARFARE,
    MEME_LIGHT,
    MEME_AMBIGUOUS,
    HARD_AMBIGUOUS,
    KNOWN_ACCOUNTS,
    PIE_COLORS,
)

_RE_CACHE: Dict[str, re.Pattern] = {}


def _kw_hit(text: str, kw: str) -> bool:
    if re.match(r"^[a-zA-Z0-9+]+$", kw):
        if kw not in _RE_CACHE:
            try:
                _RE_CACHE[kw] = re.compile(r"(?<![a-zA-Z0-9])" + re.escape(kw) + r"(?![a-zA-Z0-9])", re.IGNORECASE)
            except Exception:
                _RE_CACHE[kw] = None
        pattern = _RE_CACHE[kw]
        return bool(pattern.search(text)) if pattern else (kw.lower() in text.lower())
    return kw.lower() in text.lower()


def _detect_ambig(text: str, safe_map: Dict[str, List[str]]) -> List[str]:
    hits = []
    for term, safe_list in safe_map.items():
        c = text
        for safe in safe_list:
            c = c.replace(safe, "")
        if term in c:
            hits.append(term)
    return hits


def tone_of(raw: str) -> Dict[str, Any]:
    t = (raw or "").lower()
    if not t:
        return {"hard": False, "memes": [], "light": []}
    hard = any(_kw_hit(t, w) for w in HARD_ATTACK) or len(_detect_ambig(t, HARD_AMBIGUOUS)) > 0
    memes = [w for w in MEME_WARFARE if _kw_hit(t, w)] + _detect_ambig(t, MEME_AMBIGUOUS)
    light = [w for w in MEME_LIGHT if _kw_hit(t, w)]
    return {"hard": hard, "memes": memes, "light": light}


def match_entities(text: str) -> List[Dict[str, Any]]:
    t = (text or "").lower()
    hits = []
    if not t:
        return hits
    for e in ENTITIES:
        if any(_kw_hit(t, k.lower()) for k in e["kw"]):
            hits.append(e)
    return hits


async def fetch_bili_card(mid: str) -> Dict[str, Any]:
    url = f"https://api.bilibili.com/x/web-interface/card?mid={mid}&photo=false"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://www.bilibili.com/",
    }
    face_b64 = ""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code == 200:
                j = resp.json()
                if j.get("code") == 0:
                    c = j.get("data", {}).get("card", {})
                    level_info = c.get("level_info") or {}
                    official_verify = c.get("official_verify") or {}
                    vip = c.get("vip") or {}
                    vip_label = (vip.get("label") or {}).get("text", "") if isinstance(vip, dict) else ""
                    official_desc = official_verify.get("desc", "") if official_verify.get("type") == 0 else (c.get("Official") or {}).get("title", "")
                    raw_face = c.get("face", "")

                    if raw_face:
                        try:
                            face_resp = await client.get(raw_face, headers={"Referer": "https://www.bilibili.com/"}, timeout=5.0)
                            if face_resp.status_code == 200:
                                import base64
                                face_b64 = f"data:image/jpeg;base64,{base64.b64encode(face_resp.content).decode('utf-8')}"
                        except Exception:
                            pass

                    return {
                        "name": c.get("name", ""),
                        "face": face_b64 or raw_face or "",
                        "sex": c.get("sex", ""),
                        "sign": c.get("sign", ""),
                        "level": level_info.get("current_level", 0),
                        "fans": c.get("fans", 0),
                        "following": c.get("attention") or c.get("friend") or 0,
                        "official": official_desc or "",
                        "vip": vip_label or "",
                        "archiveCount": j.get("data", {}).get("archive_count", 0),
                        "likeNum": j.get("data", {}).get("like_num", 0),
                    }
    except Exception:
        pass
    return {
        "name": f"用户{mid}",
        "face": "",
        "sex": "保密",
        "sign": "",
        "level": 0,
        "fans": 0,
        "following": 0,
        "official": "",
        "vip": "",
        "archiveCount": 0,
        "likeNum": 0,
    }


def novice_probability(card: Dict[str, Any]) -> Dict[str, Any]:
    p = 0
    lvl = card.get("level", 0)
    if lvl <= 0:
        p += 35
    elif lvl == 1:
        p += 30
    elif lvl == 2:
        p += 22
    elif lvl == 3:
        p += 12
    elif lvl == 4:
        p += 4

    fans = card.get("fans", 0)
    if fans < 5:
        p += 20
    elif fans < 50:
        p += 12
    elif fans < 500:
        p += 4

    if card.get("archiveCount", 0) == 0:
        p += 12
    if not card.get("sign"):
        p += 6

    following = card.get("following", 0)
    if fans < 50 and following > fans * 3 and following > 30:
        p += 8

    if card.get("official"):
        p -= 30
    if card.get("vip"):
        p -= 5

    p = max(0, min(100, p))
    band = "偏高" if p >= 60 else ("中等" if p >= 30 else "偏低")
    return {"p": p, "band": band}


def analyze_activity(items: List[Dict[str, Any]]) -> Dict[str, Any]:
    times = [i["time"] for i in items if i.get("time") and i["time"] > 0]
    times.sort(reverse=True)
    if len(times) < 2:
        return {"note": "样本过少", "burst": False, "spanH": 0.0, "sample": len(times)}
    span_h = (times[0] - times[-1]) / 3600.0
    recent = times[:20]
    burst = False
    for i in range(len(recent)):
        cnt = 0
        for j in range(i, len(recent)):
            if recent[i] - recent[j] <= 3600:
                cnt += 1
        if cnt >= 10:
            burst = True
            break
    return {
        "spanH": round(span_h, 1),
        "sample": len(times),
        "burst": burst,
        "uniqueVideos": len(set(i.get("source_head", "") for i in items if i.get("source_head"))),
    }


def analyze_content(items: List[Dict[str, Any]]) -> Dict[str, Any]:
    entity_counts: Dict[str, float] = {}
    entity_meta: Dict[str, Dict[str, str]] = {}
    camp_counts: Dict[str, float] = {}
    domain_counts: Dict[str, float] = {}
    circle_counts: Dict[str, float] = {}

    hard_count = 0
    meme_count = 0
    light_count = 0
    off_cmt = 0.0
    n_cmt = 0
    off_live = 0.0
    n_live = 0
    matched_memes: Dict[str, int] = {}
    evidence: List[str] = []

    camp_stat: Dict[str, Dict[str, int]] = {}
    camp_evidence: Dict[str, List[str]] = {}

    for it in items:
        raw = str(it.get("text") or it.get("content", ""))
        src_head = str(it.get("source_head") or "")
        combined = f"{src_head} {raw}"

        tone = tone_of(raw)
        heavy = tone["hard"] or len(tone["memes"]) > 0
        light_only = not heavy and len(tone["light"]) > 0
        toxic = heavy

        if tone["hard"]:
            hard_count += 1
        if tone["memes"]:
            meme_count += 1
            for w in tone["memes"]:
                matched_memes[w] = matched_memes.get(w, 0) + 1
        if tone["light"]:
            if light_only:
                light_count += 1
            for w in tone["light"]:
                matched_memes[w] = matched_memes.get(w, 0) + 1

        w2 = 1.0 if heavy else (0.5 if light_only else 0.0)
        is_live = it.get("source") in ("aicu_live", "danmakus")

        if len(raw.strip()) >= 1:
            if is_live:
                n_live += 1
                off_live += w2
            else:
                n_cmt += 1
                off_cmt += w2

        if (heavy or light_only) and len(raw.strip()) >= 2 and len(evidence) < 15:
            evidence.append(raw.strip()[:80])

        hits = match_entities(combined)
        camps: Set[str] = set()
        names: Set[str] = set()
        for e in hits:
            name = e["name"]
            domain = e["domain"]
            camp = e["camp"]
            entity_counts[name] = entity_counts.get(name, 0.0) + 1.0
            entity_meta[name] = {"domain": domain, "camp": camp}
            domain_counts[domain] = domain_counts.get(domain, 0.0) + 1.0
            camps.add(camp)
            names.add(name)

        for c in camps:
            camp_counts[c] = camp_counts.get(c, 0.0) + 1.0
            if c not in camp_stat:
                camp_stat[c] = {"total": 0, "toxic": 0}
            camp_stat[c]["total"] += 1
            if toxic:
                camp_stat[c]["toxic"] += 1
                if c not in camp_evidence:
                    camp_evidence[c] = []
                if len(camp_evidence[c]) < 3 and len(raw.strip()) >= 2:
                    camp_evidence[c].append(raw.strip()[:60])

        if names:
            per_w = 1.0 / len(names)
            for nm in names:
                circle_counts[nm] = circle_counts.get(nm, 0.0) + per_w
        else:
            circle_counts["其他"] = circle_counts.get("其他", 0.0) + 1.0
            domain_counts["其他"] = domain_counts.get("其他", 0.0) + 1.0

    def attitude_of(camp: str) -> Dict[str, Any]:
        s = camp_stat.get(camp)
        if not s or s["total"] < 2:
            return {"label": "样本少", "hostile": False, "ratio": None, "total": s["total"] if s else 0}
        r = int(round(s["toxic"] / s["total"] * 100))
        if r >= 40:
            return {"label": "多为敌对/对线", "hostile": True, "ratio": r, "total": s["total"]}
        if r >= 18:
            return {"label": "偶有对线", "hostile": False, "mixed": True, "ratio": r, "total": s["total"]}
        return {"label": "大致友善/中性", "hostile": False, "ratio": r, "total": s["total"]}

    circle_slices = sorted(
        [(k, round(v, 1)) for k, v in circle_counts.items() if v > 0],
        key=lambda x: x[1],
        reverse=True
    )
    domain_slices = sorted(
        [(k, int(round(v))) for k, v in domain_counts.items() if v > 0],
        key=lambda x: x[1],
        reverse=True
    )
    top_entities = sorted(
        [
            {"name": name, "count": int(round(count)), "camp": entity_meta[name]["camp"], "domain": entity_meta[name]["domain"]}
            for name, count in entity_counts.items() if count > 0
        ],
        key=lambda x: x["count"],
        reverse=True
    )

    top_camps = sorted(camp_counts.items(), key=lambda x: x[1], reverse=True)
    camp_total = sum(v for _, v in top_camps) or 1.0
    camp_info = [
        {
            "camp": camp,
            "weight": int(round(w)),
            "share": max(1, int(round(w / camp_total * 100))),
            "attitude": attitude_of(camp),
            "evidence": camp_evidence.get(camp, []),
        }
        for camp, w in top_camps
    ]

    hostile_camps = [c for c in camp_info if c["attitude"].get("hostile")]
    toxic_ratio = int(round((off_cmt / n_cmt) * 100)) if n_cmt else 0
    live_toxic_ratio = int(round((off_live / n_live) * 100)) if n_live else 0
    top_memes = sorted(matched_memes.items(), key=lambda x: x[1], reverse=True)[:8]

    return {
        "domainSlices": domain_slices,
        "circleSlices": circle_slices,
        "topEntities": top_entities,
        "campInfo": camp_info,
        "dominantCamp": camp_info[0]["camp"] if camp_info else None,
        "dominantShare": camp_info[0]["share"] if camp_info else 0,
        "hostileCamps": hostile_camps,
        "hardCount": hard_count,
        "memeCount": meme_count,
        "lightCount": light_count,
        "toxicRatio": toxic_ratio,
        "liveToxicRatio": live_toxic_ratio,
        "cmtSampleN": n_cmt,
        "liveSampleN": n_live,
        "topMemes": top_memes,
        "evidence": evidence,
        "distinctCamps": len(top_camps),
        "distinctEntities": len(top_entities),
        "totalTexts": n_cmt + n_live,
    }


def analyze_live(live_items: List[Dict[str, Any]]) -> Dict[str, Any]:
    rooms: Dict[str, Dict[str, Any]] = {}
    total = len(live_items)
    latest_ts = 0

    for dm in live_items:
        head = dm.get("source_head") or "直播间"
        uname = dm.get("actor") or head
        key = head
        if key not in rooms:
            rooms[key] = {"upname": uname, "texts": [], "count": 0, "roomname": head}
        raw_t = str(dm.get("text") or dm.get("content", ""))
        rooms[key]["texts"].append(raw_t)
        rooms[key]["count"] += 1
        ts = dm.get("time", 0)
        if ts > latest_ts:
            latest_ts = ts

    room_list = []
    agg: Dict[str, Dict[str, int]] = {}

    for r in sorted(rooms.values(), key=lambda x: x["count"], reverse=True):
        hostile = 0
        for t in r["texts"]:
            tn = tone_of(t)
            if tn["hard"] or len(tn["memes"]) > 0:
                hostile += 1
        ratio = int(round(hostile / len(r["texts"]) * 100)) if r["texts"] else 0

        # 检测主播阵营
        camp = None
        for a in KNOWN_ACCOUNTS:
            if any(k in r["upname"] for k in [a["name"], a["camp"]]):
                camp = a["camp"]
                break

        r_data = {
            "upname": r["upname"],
            "count": r["count"],
            "hostileRatio": ratio,
            "camp": camp,
            "friendly": f"{max(0, 100 - ratio)}%",
        }
        room_list.append(r_data)

        if camp:
            if camp not in agg:
                agg[camp] = {"total": 0, "hostile": 0}
            agg[camp]["total"] += len(r["texts"])
            agg[camp]["hostile"] += hostile

    live_attitude = {}
    for c, s in agg.items():
        ratio = int(round(s["hostile"] / s["total"] * 100)) if s["total"] else 0
        live_attitude[c] = {
            "ratio": ratio,
            "hostile": ratio >= 40,
            "mixed": 18 <= ratio < 40,
            "total": s["total"],
        }

    return {"rooms": room_list, "liveAttitude": live_attitude, "total": total, "latestTs": latest_ts}


def compute_allegiance(card: Dict[str, Any], live_rooms: List[Dict[str, Any]], content: Dict[str, Any]) -> List[Dict[str, Any]]:
    out = []
    top_camps = set(c["camp"] for c in content.get("campInfo", [])[:3])
    live_camps = set(r["camp"] for r in live_rooms if r.get("camp"))

    # 根据活跃与发言自动匹配已知阵营
    for a in KNOWN_ACCOUNTS:
        signals = []
        if a["camp"] in live_camps:
            signals.append("直播互动(新)")
        if a["camp"] in top_camps:
            signals.append("发言高度相关")
        if signals:
            out.append({"camp": a["camp"], "name": a["name"], "signals": signals})

    if not out:
        if content.get("dominantCamp"):
            out.append({
                "camp": content["dominantCamp"],
                "name": content["dominantCamp"],
                "signals": ["发言高度相关"]
            })

    # 同 camp 合并
    by_camp: Dict[str, Dict[str, Any]] = {}
    for o in out:
        c = o["camp"]
        if c not in by_camp:
            by_camp[c] = {"camp": c, "names": [], "signals": set()}
        by_camp[c]["names"].append(o["name"])
        for s in o["signals"]:
            by_camp[c]["signals"].add(s)

    return [{"camp": c["camp"], "names": c["names"], "signals": list(c["signals"])} for c in by_camp.values()]


def cross_check_allegiance(allegiance: List[Dict[str, Any]], content: Dict[str, Any], live_attitude: Dict[str, Any]) -> Dict[str, Any]:
    by_camp = {ci["camp"]: ci for ci in content.get("campInfo", [])}
    checked = []

    for a in allegiance:
        camp = a["camp"]
        att = None
        src = ""
        if camp in live_attitude and live_attitude[camp]["total"] >= 3:
            att = live_attitude[camp]
            src = "直播"
        elif camp in by_camp and by_camp[camp].get("attitude") and by_camp[camp]["attitude"]["total"] >= 2:
            att = by_camp[camp]["attitude"]
            src = "留言"

        if not att or att.get("ratio") is None:
            checked.append({**a, "consistency": "unknown", "color": "#8993a4", "match": "? 发言未涉及", "note": "发言中几乎未涉及此圈"})
        elif att.get("hostile"):
            checked.append({**a, "consistency": "conflict", "color": "#8E1B1B", "match": f"⚠ 矛盾·疑反串 {att['ratio']}%", "ratio": att["ratio"], "src": src})
        elif att.get("mixed"):
            checked.append({**a, "consistency": "weak", "color": "#b7791f", "match": f"～ 偏对线 {att['ratio']}%", "ratio": att["ratio"], "src": src})
        else:
            checked.append({**a, "consistency": "consistent", "color": "#1a7f4b", "match": f"✔ 言行相符 {100 - (att.get('ratio') or 0)}%", "ratio": att.get("ratio", 0), "src": src})

    conflict = [c for c in checked if c["consistency"] == "conflict"]
    suspect = None
    if conflict:
        suspect = {"level": "high", "camps": [c["camp"] for c in conflict]}
    elif checked and all(c["consistency"] == "unknown" for c in checked):
        suspect = {"level": "low"}

    return {"checked": checked, "suspect": suspect}


def analyze_style(content: Dict[str, Any], activity: Dict[str, Any], total_activity: int, aleg_check: Dict[str, Any]) -> Dict[str, Any]:
    toxic_ratio = content.get("toxicRatio", 0)
    meme_count = content.get("memeCount", 0)
    hostile_camps = content.get("hostileCamps", [])
    camp_info = content.get("campInfo", [])
    checked = aleg_check.get("checked", [])
    suspect = aleg_check.get("suspect")
    alleg_set = set(a["camp"] for a in checked)

    reasons = []

    if total_activity < 5 and toxic_ratio < 15:
        return {"label": "潜水 / 低活跃用户", "color": "#8993A4", "reasons": ["公开发言很少，样本不足以判断倾向"]}

    high_toxic = toxic_ratio >= 30
    mid_toxic = toxic_ratio >= 15
    hostile_many = len(hostile_camps) >= 2 or (high_toxic and content.get("distinctCamps", 0) >= 4)
    hostile_one = len(hostile_camps) == 1
    main = camp_info[0] if camp_info else None

    # ① 反串侦测优先
    if suspect and suspect.get("level") == "high":
        reasons.append(f"表面「认证支持」{'、'.join(suspect['camps'])}")
        reasons.append("但在同一圈子的发言却多为攻击性，身分与言行矛盾")
        reasons.append("→ 高机率反串黑（伪装成粉再抹黑），或脱粉回踩/买号盗号")
        return {"label": "⚠️ 疑似反串：认证与发言矛盾", "color": "#8E1B1B", "reasons": reasons}

    # ② 对某圈敌对、认证支持对家
    if high_toxic and hostile_one and (hostile_camps[0]["camp"] not in alleg_set) and checked:
        hc = hostile_camps[0]
        reasons.append(f"火力集中对「{hc['camp']}」（该圈发言 {hc['attitude']['ratio']}% 带攻击性）")
        reasons.append(f"本人认证支持 {'、'.join(a['camp'] for a in checked)}，并非「{hc['camp']}」")
        reasons.append("→ 高信心：疑似对家/黑")
        return {"label": f"对家打手：疑似「{hc['camp']}」的反方", "color": "#C0392B", "reasons": reasons}

    # ③ 激进粉
    if high_toxic and hostile_one and (hostile_camps[0]["camp"] in alleg_set):
        hc = hostile_camps[0]
        reasons.append(f"认证支持「{hc['camp']}」，发言也偏该圈")
        reasons.append(f"但攻击性偏高（{hc['attitude']['ratio']}%）→ 疑似激进护粉/对线护镖")
        return {"label": f"激进粉：「{hc['camp']}」护镖型", "color": "#C0392B", "reasons": reasons}

    if high_toxic and hostile_many:
        reasons.append(f"引战/黑话比例高（约 {toxic_ratio}%）")
        reasons.append(f"对多个圈子持敌对态度（{'、'.join(c['camp'] for c in hostile_camps[:3])}）")
        reasons.append("不专属某一方，偏好到处对线/看热闹")
        return {"label": "乐子人（到处引战・看热闹）", "color": "#E8850C", "reasons": reasons}

    if high_toxic and hostile_one:
        hc = hostile_camps[0]
        reasons.append(f"火力集中对「{hc['camp']}」（该圈发言 {hc['attitude']['ratio']}% 带攻击性）")
        reasons.append("高度活跃于该圈却多为敌对 → 疑似该圈的反方/黑，而非支持者")
        return {"label": f"对线型：疑似「{hc['camp']}」的反方/黑", "color": "#C0392B", "reasons": reasons}

    if high_toxic:
        reasons.append(f"引战/攻击词比例偏高（约 {toxic_ratio}%）")
        if meme_count:
            reasons.append("常用阴阳怪气/对线黑话")
        return {"label": "偏激型（时常引战）", "color": "#E8850C", "reasons": reasons}

    if mid_toxic:
        reasons.append(f"偶有攻击性/对线发言（约 {toxic_ratio}%）")
        return {"label": "偶尔对线", "color": "#F0B429", "reasons": reasons}

    # 低攻击
    if main and main["attitude"]["label"] == "大致友善/中性" and main["attitude"]["total"] >= 2:
        reasons.append(f"主要活跃于「{main['camp']}」且发言平和 → 疑似该圈爱好者/支持者")
        return {"label": f"「{main['camp']}」圈普通用户", "color": "#36B37E", "reasons": reasons}

    reasons.append(f"攻击性发言很少（约 {toxic_ratio}%）")
    return {"label": "正常用户 / 玩家", "color": "#36B37E", "reasons": reasons}


def build_evaluation(content: Dict[str, Any], style: Dict[str, Any], activity: Dict[str, Any], novice: Dict[str, Any], aleg_check: Dict[str, Any]) -> str:
    parts = []
    main = content.get("campInfo", [{}])[0] if content.get("campInfo") else None
    checked = aleg_check.get("checked", [])

    if checked:
        consistent = [a["camp"] for a in checked if a["consistency"] == "consistent"]
        conflict = [a["camp"] for a in checked if a["consistency"] == "conflict"]
        if consistent:
            parts.append(f"认证且发言相符的支持圈：【{'、'.join(consistent)}】（可信度高）")
        if conflict:
            parts.append(f"⚠️ 认证支持【{'、'.join(conflict)}】却在该圈发言充满攻击，身份矛盾，此认证恐为反串伪装")

    if content.get("topEntities"):
        top = "、".join(e["name"] for e in content["topEntities"][:3])
        domain = content["domainSlices"][0][0] if content.get("domainSlices") else "综合"
        parts.append(f"主要活跃于【{domain}】，常出没于【{top}】相关内容")
    else:
        parts.append("公开发言中未侦测到明确的圈子关键词")

    if main and main.get("attitude") and main["attitude"].get("ratio") is not None:
        att = main["attitude"]
        if att.get("hostile"):
            parts.append(f"但在「{main['camp']}」圈的发言 {att['ratio']}% 带攻击性，较像反方/对家而非支持者")
        elif att["label"] == "大致友善/中性":
            parts.append(f"在「{main['camp']}」圈发言平和，较像该圈爱好者")
        else:
            parts.append(f"在「{main['camp']}」圈态度中性偏对线（{att['ratio']}%）")

    if len(content.get("hostileCamps", [])) >= 2:
        parts.append(f"对多个圈子（{'、'.join(c['camp'] for c in content['hostileCamps'][:3])}）持敌对态度")

    if activity.get("burst"):
        parts.append("近期发言时间高度集中")
    if novice and novice.get("p", 0) >= 60:
        parts.append(f"账号本身疑似小号（{novice['p']}%）")

    parts.append(f"综合特征接近『{style['label']}』")
    return "；".join(parts) + "。"
