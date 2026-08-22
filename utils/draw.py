"""HTML + pytakumi / Playwright 图片卡片渲染模块

自动加载并注册插件 fonts/ 目录下的专用字体：
- 中文主字体：H7GBKHeavy
- 英数等宽字体：JetBrainsMono
- 补充与兜底：NotoSansJP
- 表情与符号：NotoEmoji

渲染失败时自动将 HTML 保存至 gsuid_core/data/BiliHistoryUID/html 目录，并向用户提示具体路径。
"""

from __future__ import annotations

import asyncio
import functools
import pathlib
import time
from typing import Any, Dict, Optional, Union

from jinja2 import Template

from gsuid_core.data_store import get_res_path
from gsuid_core.logger import logger

_TEMPLATE_PATH = pathlib.Path(__file__).resolve().parent.parent / "templates" / "card_template.html"
_FONTS_DIR = pathlib.Path(__file__).resolve().parent.parent / "fonts"

_renderer_instance: Optional[Any] = None


def _get_renderer():
    global _renderer_instance
    if _renderer_instance is not None:
        return _renderer_instance
    try:
        from pytakumi import Renderer, set_glyph_cache_max_bytes
        try:
            set_glyph_cache_max_bytes(64 * 1024 * 1024)
        except Exception:
            pass
        r = Renderer()

        # 注册插件内置字体
        font_files = [
            ("H7GBKHeavy.TTF", "H7GBKHeavy"),
            ("JetBrainsMono-Medium.ttf", "JetBrainsMono"),
            ("NotoSansJP-Medium.ttf", "NotoSansJP"),
            ("NotoEmoji-Regular.ttf", "NotoEmoji"),
        ]
        for fname, font_name in font_files:
            fpath = _FONTS_DIR / fname
            if fpath.is_file():
                try:
                    r.register_font(fpath.read_bytes(), name=font_name)
                except Exception as e:
                    logger.warning(f"[BiliHistoryUID] 注册字体 {fname} 失败: {e}")

        _renderer_instance = r
        return _renderer_instance
    except Exception as e:
        logger.warning(f"[BiliHistoryUID] 初始化 pytakumi 渲染器失败: {e}")
        return None


def _sync_render_html(rendered_html: str) -> bytes:
    from pytakumi import html_to_pic
    renderer = _get_renderer()
    return html_to_pic(
        rendered_html,
        width=1380,
        height=None,
        format="png",
        renderer=renderer,
        font_families=["JetBrainsMono", "H7GBKHeavy", "NotoSansJP", "NotoEmoji"],
        lang="zh"
    )


async def draw_card(model: Dict[str, Any]) -> Union[bytes, str]:
    uid = model.get("uid", "0")
    summary = model.get("summary")
    analysis = model.get("analysis", {})
    items = model.get("items", [])

    # 读取 HTML 模板
    try:
        template_text = _TEMPLATE_PATH.read_text(encoding="utf-8")
        template = Template(template_text)
        rendered_html = template.render(
            uid=uid,
            summary=summary,
            analysis=analysis,
            items=items,
            generate_time=model.get("generate_time", "")
        )
    except Exception as e:
        logger.exception(f"[BiliHistoryUID] Jinja2 模板渲染失败: {e}")
        return f"⚠️ 模板加载失败: {e}"

    # 尝试 HTML 图片渲染
    try:
        img_bytes = await asyncio.to_thread(_sync_render_html, rendered_html)
        if img_bytes and len(img_bytes) > 0:
            return img_bytes
        else:
            raise RuntimeError("渲染器返回了空字节序列。")

    except Exception as e:
        logger.exception(f"[BiliHistoryUID] HTML 渲染成图片失败: {e}")

        save_dir = get_res_path("BiliHistoryUID") / "html"
        save_dir.mkdir(parents=True, exist_ok=True)
        filename = f"card_{uid}_{int(time.time())}.html"
        file_path = save_dir / filename

        try:
            file_path.write_text(rendered_html, encoding="utf-8")
            path_str = str(file_path.resolve())
            return f"⚠️ 浏览器渲染图片失败（{e}）。\nHTML 已自动保存至：\n{path_str}"
        except Exception as write_err:
            return f"⚠️ 浏览器渲染图片失败: {e} (保存 HTML 同样失败: {write_err})"
