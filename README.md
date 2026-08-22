# BiliHistoryUID

GsCore 插件：从第三方反代（danmakus.com / aicu.cc）查询 B 站用户的评论、视频弹幕、直播弹幕历史，并聚合绘制成画像卡片。若配置了 AI 总结，卡片采用带 AI 总结的样式。

## 命令家族（均以 `bc` 开头，后接纯数字 UID）

- `bc<uid>` — 查评论区历史（聚合全部数据源）
- `bc评论<uid>` — 查评论区历史
- `bc弹幕<uid>` / `bc视频弹幕<uid>` — 查视频弹幕
- `bc直播<uid>` / `bc直播弹幕<uid>` — 查直播弹幕

## 目录结构（单层入口）

```
BiliHistoryUID/
├── __init__.py             命令入口（插件包）
├── api/                    数据源聚合
│   ├── service.py          聚合调度
│   ├── aicu/               aicu.cc 抓取器
│   └── danmakus/           danmakus 抓取器
├── config/                 插件配置
├── utils/draw.py           Pillow 绘图
├── pyproject.toml
├── README.md
└── LICENSE
```

## 配置说明

配置存放于 `data/plugins_configs/BiliHistoryUID.json`，可在 gs 控制台/管理界面修改，或在代码中 `get_config()` 读取。

| 配置项 | 默认 | 说明 |
|---|---|---|
| `enable_ai_summary` | `false` | 开启 AI 总结卡片样式 |
| `danmakus_base` | `ukamnads.icu` | danmakus 系 API 实际 host |
| `history_page_size` | `10` | danmakus 每页条数 |
| `aicu_cookie` | 空 | 可选，aicu.cc 登录后的 Cookie 以提高成功率 |
