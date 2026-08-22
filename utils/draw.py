"""用 Pillow 绘制用户画像卡片.

两种版式：
- AI 总结版（enable_ai_summary=True）：顶部资料头 + AI 总结区 + 精简历史摘录
- 直接历史版（enable_ai_summary=False）：顶部资料头 + 用户较新/较旧历史片段列表

返回 PNG bytes 供 ``bot.send`` 直接发送。
"""

from __future__ import annotations

import io
from datetime import datetime
from typing import Any, Dict, List

from PIL import Image, ImageDraw, ImageFont

from gsuid_core.data_store import get_res_path

CARD_WIDTH = 800
ACCENT = "#00A1D6"
BG = "#F5F7FA"
CARD = "#FFFFFF"
TEXT_MAIN = "#333333"
TEXT_SUB = "#888888"

# 候选字体路径：插件资源 → Linux 常用 CJK 字体 → Windows 字体，逐个尝试加载
_FONT_PATHS = [
    str(get_res_path("font") / "simhei.ttf"),
    "msyh.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJKsc-Regular.otf",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
    "/usr/share/fonts/adobe-sourcehansans/SourceHanSansSC-Regular.otf",
    "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/noto/NotoSansCJK-Regular.ttc",
    "/usr/local/share/fonts/NotoSansCJK-Regular.ttc",
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/simhei.ttf",
    "C:/Windows/Fonts/msyhbd.ttc",
]


def _font(size: int) -> ImageFont.FreeTypeFont:
    for p in _FONT_PATHS:
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _wrap_text(draw: ImageDraw.Draw, text: str, font, width: int) -> List[str]:
    lines: List[str] = []
    cur = ""
    for ch in str(text):
        cur += ch
        if draw.textbbox((0, 0), cur, font=font)[2] > width:
            lines.append(cur[:-1])
            cur = ch
    if cur:
        lines.append(cur)
    return lines


def _draw_header(draw: ImageDraw.Draw, uid: str, sources: List[str]):
    draw.rounded_rectangle([40, 40, CARD_WIDTH - 40, 160], radius=16, fill=ACCENT)
    draw.text((70, 70), "用户画像卡片", fill="#FFFFFF", font=_font(34))
    draw.text((70, 122), f"UID: {uid}", fill="#E6F4FF", font=_font(22))
    src_txt = "数据源: " + ("/".join(sources) if sources else "无可用数据源")
    draw.text((CARD_WIDTH - 70 - draw.textbbox((0, 0), src_txt, font=_font(18))[2], 124),
              src_txt, fill="#FFFFFF", font=_font(18))


def _draw_summary(draw: ImageDraw.Draw, y: int, summary: str) -> int:
    box_h = 60 + len(_wrap_text(draw, summary, _font(20), CARD_WIDTH - 220)) * 34
    draw.rounded_rectangle([40, y, CARD_WIDTH - 40, y + box_h], radius=16, fill="#EAF6FF")
    draw.rectangle([40, y, 56, y + box_h], fill=ACCENT)
    draw.text((72, y + 16), "AI 总结", fill=ACCENT, font=_font(26))
    ly = y + 60
    for line in _wrap_text(draw, summary, _font(20), CARD_WIDTH - 220):
        draw.text((76, ly), line, fill=TEXT_MAIN, font=_font(20))
        ly += 34
    return y + box_h + 20


def _draw_items(draw: ImageDraw.Draw, y: int, items: List[Dict[str, Any]]):
    line_h = 34
    pad_y = 10
    for it in items[:12]:
        src = it.get("source_head", "") or ""
        kind_font = _font(18)
        tstr = it.get("readable_time") or "--"
        tfont = _font(16)
        left_x = 76
        time_x = CARD_WIDTH - 76 - _text_w(draw, tstr, tfont)
        avail = time_x - (left_x + _text_w(draw, f"[{src}]", kind_font) + 8) - 8

        raw_cont = str(it.get("text") or it.get("content", "")) or ""
        cont_font = _font(20)
        lines = _wrap_text(draw, raw_cont, cont_font, avail) or [""]
        if len(lines) > 3:
            lines = lines[:3] + [lines[3][:20] + "…"]

        row_h = max(len(lines) * line_h + pad_y * 2, 34)
        fill = ACCENT if it.get("kind") == "danmaku" else "#3E7CB1"
        draw.rounded_rectangle([60, y, CARD_WIDTH - 60, y + row_h - 4], radius=8, fill=CARD)
        draw.text((left_x, y + pad_y), f"[{src}]", fill=fill, font=kind_font)
        tx = left_x + _text_w(draw, f"[{src}]", kind_font) + 8
        ty = y + pad_y + (line_h - cont_font.size) // 2 + 2
        for i, line in enumerate(lines):
            draw.text((tx, ty + i * line_h), line, fill=TEXT_MAIN, font=cont_font)
        draw.text((time_x, y + pad_y + 2), tstr, fill=TEXT_SUB, font=tfont)
        y += row_h


def _text_w(draw: ImageDraw.Draw, s: str, font) -> int:
    return draw.textbbox((0, 0), s, font=font)[2]


def _item_row_h(it: Dict[str, Any]) -> int:
    """与 _draw_items 一致的逻辑，计算单个条目所需高度。"""
    d = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    src = it.get("source_head", "") or ""
    tstr = it.get("readable_time") or "--"
    left_x = 76
    time_x = CARD_WIDTH - 76 - _text_w(d, tstr, _font(16))
    avail = time_x - (left_x + _text_w(d, f"[{src}]", _font(18)) + 8) - 8
    raw_cont = str(it.get("text") or it.get("content", "")) or ""
    lines = _wrap_text(d, raw_cont, _font(20), avail) or [""]
    if len(lines) > 3:
        lines = lines[:3] + [lines[3][:20] + "…"]
    return max(len(lines) * 34 + 20, 34)


def draw_card(model: Dict[str, Any]) -> bytes:
    items: List[Dict[str, Any]] = model.get("items", []) or []
    enable_ai: bool = model.get("enable_ai_summary", False)
    summary: str = model.get("summary") or ""
    sources: List[str] = model.get("checked_sources") or []
    uid: str = model.get("uid") or "?"

    header_h = 190
    list_h = sum(_item_row_h(it) for it in items[:12]) + 40
    if enable_ai:
        ai_h = 60 + len(_wrap_text(ImageDraw.Draw(Image.new("RGBA", (1, 1))), summary, _font(20), CARD_WIDTH - 220)) * 34 + 20
        body_h = ai_h + 40 + list_h
    else:
        body_h = 40 + list_h
    height = header_h + body_h + 60
    height = max(height, 400)

    img = Image.new("RGBA", (CARD_WIDTH, height), BG)
    draw = ImageDraw.Draw(img)

    _draw_header(draw, uid, sources)

    y = header_h
    if enable_ai:
        y = _draw_summary(draw, y, summary)
        draw.text((60, y), "历史摘录：", fill=TEXT_SUB, font=_font(22))
        _draw_items(draw, y + 34, items)
    else:
        draw.text((60, y), "最新历史片段：", fill=TEXT_SUB, font=_font(22))
        _draw_items(draw, y + 34, items)

    foot = f"BiliHistoryUID - {model.get('generate_time', '')}"
    fw = draw.textbbox((0, 0), foot, font=_font(18))[2]
    draw.text(((CARD_WIDTH - fw) // 2, height - 40), foot, fill="#AAAAAA", font=_font(18))

    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="PNG", quality=95)
    return buf.getvalue()
