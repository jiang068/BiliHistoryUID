"""BiliHistoryUID 插件配置.

基于 gsuid_core 的 StringConfig 机制，配置 JSON 存放于
``data/plugins_configs/BiliHistoryUID.json``（PLUGINS_CONFIGS_PATH）。
"""

from __future__ import annotations

from gsuid_core.data_store import PLUGINS_CONFIGS_PATH
from gsuid_core.utils.plugins_config.gs_config import StringConfig
from gsuid_core.utils.plugins_config.models import (
    GsBoolConfig,
    GsIntConfig,
    GsStrConfig,
)

CONF_PATH = PLUGINS_CONFIGS_PATH / "BiliHistoryUID.json"

CONFIG_DEFAULT = {
    "enable_ai_summary": GsBoolConfig(
        title="启用 AI 总结",
        desc="开启后渲染带 AI 总结的卡片；关闭则直接输出用户历史片段。",
        data=False,
    ),
    "danmakus_base": GsStrConfig(
        title="danmakus 系 API 主机",
        desc="在浏览器抓包得到 /api/v3/users/../history 的实际 host（如 ukamnads.icu）。",
        data="ukamnads.icu",
    ),
    "history_page_size": GsIntConfig(
        title="danmakus 每页条数",
        desc="历史接口 pageSize，一次命令抓取的弹幕量上限。",
        data=10,
    ),
    "aicu_cookie": GsStrConfig(
        title="AICU Cookie",
        desc="可选，登录 aicu.cc 后抓取的 ASession=... 用于提高成功率。",
        data="",
    ),
}

_CONF = StringConfig("BiliHistoryUID", CONF_PATH, CONFIG_DEFAULT)


def get_config() -> StringConfig:
    return _CONF
