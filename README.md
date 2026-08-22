# BiliHistoryUID

基于 **GsCore** 框架开发的 Bilibili 用户行为画像与成分探查插件。通过聚合 B 站官方资料与第三方历史数据（aicu.cc / danmakus.com），对目标用户的跨视频评论、视频弹幕、直播互动进行全方位分析，并自动生成双栏用户画像卡片。

---

## 🌟 功能特色

1. **真实 B 站官方资料聚合**：
   - 自动获取真实头像、昵称、Lv 等级、关注/粉丝数、投稿量、获赞数、大会员标识及官方认证信息。
2. **多维度成分与阵营分析**：
   - **50+ 实体/阵营词库**：覆盖主流手游（米哈游系、库洛系、鹰角系、腾讯系、网易系等）、竞技网游（LOL、VALORANT、CS2、DOTA2、三角洲、永劫等）、主机 3A、国乙、VTuber 及敏感争议圈子。
   - **关注度 vs 态度交叉矩阵**：区分“在圈内活跃”与“真实立场”，精准推导各圈友善/中性/对线/敌对比例。
3. **情绪与对线黑话检测**：
   - 分级词库识别（人身攻击、阴阳怪气、对线黑话、轻度嘲讽），内置**安全词剥离算法**避免常见中文单字误判。
   - 计算评论区与直播弹幕的加权引战比例。
4. **认证归属与反串侦测**：
   - 结合官方认证、粉丝牌、抽奖记录与实际发言交叉验证，识别“言行相符”、“偏对线”或“疑似反串”。
5. **账号特征与活动节奏**：
   - 多因子启发式测算**疑似小号可能性**。
   - 时间跨度与高密度发言（单小时 ≥10 条）爆发检测。
6. **双栏 HTML/Playwright 渲染引擎**：
   - 现代响应式排版、CSS 动态渐变成分圆饼图与高密度证据发言流卡片。
   - 内置注册 `H7GBKHeavy`（中文主字体）、`JetBrainsMono`（英数等宽）及 `NotoEmoji`（符号表情），跨平台排版不缺字不乱码。
   - 渲染异常时自动将 HTML 保存至 `data/BiliHistoryUID/html/` 并给出物理路径提示。
7. **智能 AI 画像扩展**：
   - 支持按需启用 LLM 深度分析卡片，关闭时自动丢弃不占位。

---

## 📋 命令说明

所有命令均以 `bc` 开头，后接目标纯数字 UID：

| 命令 | 说明 | 示例 |
|---|---|---|
| `bc<uid>` | 综合画像探查（聚合全源数据） | `bc401742377` |
| `bc评论<uid>` | 仅查询评论区历史画像 | `bc评论401742377` |
| `bc弹幕<uid>` / `bc视频弹幕<uid>` | 仅查询视频弹幕历史画像 | `bc弹幕401742377` |
| `bc直播<uid>` / `bc直播弹幕<uid>` | 仅查询直播间弹幕与互动画像 | `bc直播401742377` |

---

## ⚙️ 配置说明

插件配置文件位于 `data/BiliHistoryUID/config.json`，支持通过 Web 控制台或直接修改：

| 配置项 | 默认值 | 说明 |
|---|---|---|
| `enable_ai_summary` | `false` | 是否开启 AI 深度画像总结面板 |
| `danmakus_base` | `ukamnads.icu` | danmakus 反代 API 域名 |
| `history_page_size` | `5` | 抓取历史弹幕/评论的每页条数 |
| `aicu_cookie` | `""` | 可选，aicu.cc 的 Session Cookie（提高抓取成功率） |

---

## 📁 目录结构（单层插件包）

```text
BiliHistoryUID/
├── __init__.py             # 插件命令入口与服务注册
├── api/                    # 数据源聚合与分析引擎
│   ├── service.py          # 聚合调度器
│   ├── inspector.py        # 行为画像与成分研判核心算法
│   ├── aicu/               # aicu.cc 抓取模块
│   └── danmakus/           # danmakus.com 抓取模块
├── config/                 # 插件配置管理
├── fonts/                  # 内置字体（H7GBKHeavy、JetBrainsMono、NotoEmoji 等）
├── material/               # 实体词库与语料定义
│   └── inspector_data.py   # 阵营实体、黑话词库与账号名册
├── templates/              # 卡片渲染模板
│   └── card_template.html  # 双栏响应式 HTML/CSS 模板
├── utils/                  # 工具函数
│   └── draw.py             # 基于 pytakumi 的 HTML 图片渲染器
├── pyproject.toml
├── README.md
└── LICENSE
```

---

## 🙏 致谢与参考

本插件的诞生离不开以下开源项目与技术支持：

- **框架搭建**：由 **DeepSeek V4 Flash** 完成基础架构设计。
- **功能扩充与算法重构**：由 **Gemini 3.7 Flash** 完成实体词库扩充与评判引擎重构。
- **数据抓取逻辑参考**：参考自 [astrbot_plugin_aicu_analysis](https://github.com/1780605301/astrbot_plugin_aicu_analysis) 的 API 调度与指纹抓取实现。
- **评判框架与算法逻辑**：核心判定决策树、安全词防误判、一致性交叉检验及实体词表参考自油猴脚本 [B站查成分 (Account Inspector)](https://greasyfork.org/zh-CN/scripts/586954-b%E7%AB%99%E6%9F%A5%E6%88%90%E5%88%86-account-inspector) 。

---

## ⚠️ 免责声明

本插件所有输出均为基于公开数据与关键词规则推测的**辅助辨识参考讯号，非定论**。立场与风格判断可能因反串、引用、语境发生误判，请结合卡片中的原始发言核实。切勿将分析结果用于对任何个人进行骚扰或攻击。
