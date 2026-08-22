"""用 Pillow 绘制用户画像卡片.

两种版式：
- AI 总结版（enable_ai_summary=True）
- 直接历史版（enable_ai_summary=False）

字体策略（插件自带 fonts/ 目录，不依赖系统字体）：
- ASCII / 拉丁字母数字 -> JetBrainsMono（等宽）
- 中日韩文字 -> H7GBKHeavy（主），NotoSansJP 兜底
- 表情符号 -> NotoEmoji
按字符类别拆段，每段用对应字体绘制，保证混排正确。
"""

from __future__ import annotations

import io
import pathlib
import re
from datetime import datetime
from typing import Any, Dict, List, Tuple

from PIL import Image, ImageDraw, ImageFont
from PIL.ImageFont import FreeTypeFont

CARD_WIDTH = 800
ACCENT = "#00A1D6"
BG = "#F5F7FA"
CARD = "#FFFFFF"
TEXT_MAIN = "#333333"
TEXT_SUB = "#888888"

_FONTS_DIR = str(pathlib.Path(__file__).resolve().parent.parent / "fonts")


def _path(name: str) -> str:
    return f"{_FONTS_DIR}/{name}"


_CJK_PATHS = ["H7GBKHeavy.TTF", "NotoSansJP-Medium.ttf"]
_LATIN_PATHS = ["JetBrainsMono-Medium.ttf", "H7GBKHeavy.TTF"]
_EMOJI_PATH = "NotoEmoji-Regular.ttf"

_fcache: Dict[Tuple[str, int], FreeTypeFont] = {}


def _load(paths, size: int) -> FreeTypeFont:
    for name in paths:
        key = (name, size)
        f = _fcache.get(key)
        if f is not None:
            return f
        try:
            f = ImageFont.truetype(_path(name), size)
        except Exception:
            continue
        _fcache[key] = f
        return f
    return ImageFont.load_default()


# emoji 常用块
_EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001FAFF"  # 符号/附图
    "\U00002600-\U000027BF"  # 杂项符号/装饰/箭头
    "\U00002B00-\U00002BFF"  # 杂项符号和箭头
    "\U0001F000-\U0001F0FF"  # 扑克
    "]"
)


def _cat(ch: str) -> str:
    if _EMOJI_RE.match(ch):
        return "emoji"
    if ch.isascii():
        return "ascii"
    return "cjk"


def _font_for(cat: str, size: int) -> FreeTypeFont:
    if cat == "ascii":
        return _load(_LATIN_PATHS, size)
    if cat == "emoji":
        return _load([_EMOJI_PATH], size)
    return _load(_CJK_PATHS, size)


def _runs(text: str) -> List[Tuple[str, str]]:
    if not text:
        return []
    out: List[Tuple[str, str]] = []
    cur_cat = _cat(text[0])
    cur = text[0]
    for ch in text[1:]:
        c = _cat(ch)
        if c == cur_cat:
            cur += ch
        else:
            out.append((cur_cat, cur))
            cur_cat = c
            cur = ch
    out.append((cur_cat, cur))
    return out


def _run_width(draw: ImageDraw.Draw, cat: str, chunk: str, size: int) -> int:
    return int(draw.textlength(chunk, font=_font_for(cat, size)))


def _text_width(draw: ImageDraw.Draw, text: str, size: int) -> int:
    return sum(_run_width(draw, cat, chunk, size) for cat, chunk in _runs(text))


def _line_h(size: int) -> int:
    """按主字体实际像素高度估算行距。"""
    asc, desc = _load(_CJK_PATHS, size).getmetrics()
    return asc + desc + 6


def _run_height(font: FreeTypeFont) -> int:
    asc, desc = font.getmetrics()
    return asc + desc


def _draw_runs(
    draw: ImageDraw.Draw,
    pos: Tuple[int, int],
    text: str,
    size: int,
    fill: str,
):
    x, y = pos
    for cat, chunk in _runs(text):
        font = _font_for(cat, size)
        draw.text((x, y), chunk, fill=fill, font=font)
        x += _run_width(draw, cat, chunk, size)
    return x


def _draw_items(draw: ImageDraw.Draw, y: int, items: List[Dict[str, Any]]):
    line_h = _line_h(20)
    pad_y = 8
    for it in items[:12]:
        src = it.get("source_head", "") or ""
        tstr = it.get("readable_time") or "--"
        left_x = 76
        src_x = left_x + _text_width(draw, f"[{src}]", 18)
        time_x = CARD_WIDTH - 76 - _text_width(draw, tstr, 16)
        avail = time_x - src_x - 8

        raw_cont = str(it.get("text") or it.get("content", "")) or ""
        lines = _wrap_text(draw, raw_cont, 20, avail) or [""]
        if len(lines) > 3:
            lines = lines[:3] + [lines[3][:20] + "…"]

        row_h = len(lines) * line_h + pad_y * 2
        fill = ACCENT if it.get("kind") == "danmaku" else "#3E7CB1"
        draw.rounded_rectangle([60, y, CARD_WIDTH - 60, y + row_h - 4], radius=8, fill=CARD)
        _draw_runs(draw, (left_x, y + pad_y), f"[{src}]", 18, fill)
        tx = src_x
        ty = y + pad_y
        for i, line in enumerate(lines):
            _draw_runs(draw, (tx, ty + i * line_h), line, 20, TEXT_MAIN)
        _draw_runs(draw, (time_x, y + pad_y + 2), tstr, 16, TEXT_SUB)
        y += row_h


def _item_row_h(it: Dict[str, Any]) -> int:
    d = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    src = it.get("source_head", "") or ""
    tstr = it.get("readable_time") or "--"
    left_x = 76
    time_x = CARD_WIDTH - 76 - _text_width(d, tstr, 16)
    avail = time_x - (left_x + _text_width(d, f"[{src}]", 18) + 8) - 8
    raw_cont = str(it.get("text") or it.get("content", "")) or ""
    lines = _wrap_text(d, raw_cont, 20, avail) or [""]
    if len(lines) > 3:
        lines = lines[:3] + [lines[3][:20] + "…"]
    return max(len(lines) * _line_h(20) + 16, 36)


def _wrap_text(draw: ImageDraw.Draw, text: str, size: int, width: int) -> List[str]:
    lines: List[str] = []
    cur = ""
    for ch in str(text):
        cur += ch
        if _text_width(draw, cur, size) > width:
            lines.append(cur[:-1])
            cur = ch
    if cur:
        lines.append(cur)
    return lines


def _draw_header(draw: ImageDraw.Draw, uid: str, sources: List[str]):
    draw.rounded_rectangle([40, 40, CARD_WIDTH - 40, 160], radius=16, fill=ACCENT)
    _draw_runs(draw, (70, 70), "用户画像卡片", 34, "#FFFFFF")
    _draw_runs(draw, (70, 122), f"UID: {uid}", 22, "#E6F4FF")
    src_txt = "数据源: " + ("/".join(sources) if sources else "无可用数据源")
    _draw_runs(draw, (CARD_WIDTH - 70 - _text_width(draw, src_txt, 18), 124),
               src_txt, 18, "#FFFFFF")


def _draw_summary(draw: ImageDraw.Draw, y: int, summary: str) -> int:
    lines = _wrap_text(draw, summary, 20, CARD_WIDTH - 220)
    box_h = 60 + len(lines) * _line_h(20)
    draw.rounded_rectangle([40, y, CARD_WIDTH - 40, y + box_h], radius=16, fill="#EAF6FF")
    draw.rectangle([40, y, 56, y + box_h], fill=ACCENT)
    _draw_runs(draw, (72, y + 16), "AI 总结", 26, ACCENT)
    ly = y + 60
    for line in lines:
        _draw_runs(draw, (76, ly), line, 20, TEXT_MAIN)
        ly += _line_h(20)
    return y + box_h + 20


def draw_card(model: Dict[str, Any]) -> bytes:
    items: List[Dict[str, Any]] = model.get("items", []) or []
    enable_ai: bool = model.get("enable_ai_summary", False)
    summary: str = model.get("summary") or ""
    sources: List[str] = model.get("checked_sources") or []
    uid: str = model.get("uid") or "?"

    header_h = 190
    list_h = sum(_item_row_h(it) for it in items[:12]) + 40
    if enable_ai:
        ai_h = 60 + len(_wrap_text(ImageDraw.Draw(Image.new("RGBA", (1, 1))), summary, 20, CARD_WIDTH - 220)) * _line_h(20) + 20
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
        _draw_runs(draw, (60, y), "历史摘录：", 22, TEXT_SUB)
        _draw_items(draw, y + 34, items)
    else:
        _draw_runs(draw, (60, y), "最新历史片段：", 22, TEXT_SUB)
        _draw_items(draw, y + 34, items)

    foot = f"BiliHistoryUID - {model.get('generate_time', '')}"
    fw = _text_width(draw, foot, 18)
    _draw_runs(draw, ((CARD_WIDTH - fw) // 2, height - 40), foot, 18, "#AAAAAA")

    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="PNG", quality=95)
    return buf.getvalue()
