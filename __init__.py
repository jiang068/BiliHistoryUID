"""BiliHistoryUID - 从 danmakus / aicu.cc 查询用户评论与弹幕历史并绘制画像卡片.

命令家族（均以 bc 开头，后面接 uid）：
  bc<uid>                 查评论区历史（聚合）
  bc评论<uid>            查评论区历史（等价 bc<uid>）
  bc弹幕<uid>           查视频弹幕
  bc视频弹幕<uid>       查视频弹幕
  bc直播<uid>           查直播弹幕（你发过的）
  bc直播弹幕<uid>       查直播弹幕
"""

import time

from gsuid_core.sv import SL, SV, Plugins
from gsuid_core.bot import Bot
from gsuid_core.models import Event
from gsuid_core.logger import logger

from .config import get_config
from .api.service import build_card
from .utils.draw import draw_card

if "BiliHistoryUID" not in SL.plugins:
    Plugins(
        name="BiliHistoryUID",
        allow_empty_prefix=True,
    )

sv_query = SV("B站历史查询")


class _Mode:
    card = "card"
    reply = "reply"
    video = "video"
    live = "live"


def _use_ai() -> bool:
    try:
        return get_config().get_config("enable_ai_summary").data
    except Exception:
        return False


def _make(mode: str):
    async def handler(bot: Bot, ev: Event):
        uid = ev.text.strip()
        if not uid or not uid.isdigit():
            return await bot.send(
                "请输入纯数字 UID，例如：bc12345678 / bc弹幕12345678 / bc直播12345678"
            )
        start = time.time()
        try:
            model = await build_card(uid, _use_ai(), mode=mode)
        except Exception as e:
            logger.exception(e)
            return await bot.send("查询失败，请查看后台日志。")
        if not model.get("items"):
            return await bot.send(f"该板块未获取到用户 {uid} 的数据。")
        try:
            img = await draw_card(model)
        except Exception as e:
            logger.exception(e)
            return await bot.send(f"画像绘制失败，请查看后台日志：{e}")
        await bot.send(img)
        logger.info(f"[BiliHistoryUID] 板块={mode} 查询 {uid} 耗时 {time.time() - start:.1f}s")
    return handler


# bc<uid> / bc评论<uid>  -> 评论
sv_query.on_prefix("bc")(_make(_Mode.card))
sv_query.on_prefix("bc评论")(_make(_Mode.reply))

# bc弹幕<uid> / bc视频弹幕<uid> -> 视频弹幕
sv_query.on_prefix("bc弹幕")(_make(_Mode.video))
sv_query.on_prefix("bc视频弹幕")(_make(_Mode.video))

# bc直播<uid> / bc直播弹幕<uid> -> 直播弹幕
sv_query.on_prefix("bc直播弹幕")(_make(_Mode.live))
sv_query.on_prefix("bc直播")(_make(_Mode.live))
