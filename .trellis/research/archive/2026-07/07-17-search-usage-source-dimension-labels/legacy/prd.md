# 搜索调用来源与维度中文化

## Goal

让中文界面的“用量分析 -> 搜索调用”页面以中文展示搜索调用的来源和维度，降低用户理解内部码值的成本。

## Background

- 当前页面在最近搜索调用表格中直接展示 `callSource` 与 `dimension`；当 `dimension` 为空时展示 `operation`。
- 来源筛选器和“调用来源分布”也直接展示 `bySource[].value` 原始码值。
- API 的来源筛选、审计存储、CSV/JSON 导出仍依赖稳定的原始码值，本任务只调整 Web 展示层，不修改数据契约。
- 页面支持中英文界面；本需求明确要求中文界面翻译码值。

## Requirements

- 中文界面为已知的来源、维度和维度为空时的操作码值提供中文标签。
- 来源标签覆盖页面内所有可见位置：来源筛选器、“调用来源分布”和“最近搜索调用”表格。
- 已知码值仅显示中文标签，不在页面并列展示原始码值。
- `dimension` 为空时继续展示 `operation`，并对已知操作码值应用中文标签。
- 用于筛选和接口请求的实际值保持原始码值，不能把中文标签传给后端。
- 未识别的新码值必须回退显示原始值，避免显示空白或错误归类。
- 英文界面的现有原始码值展示保持不变。

## Label Mapping

### 来源

| 码值 | 中文标签 |
| --- | --- |
| `analysis` | 分析流程 |
| `agent` | Agent 工具 |
| `market_review` | 大盘复盘 |
| `alphasift` | AlphaSift |
| `availability_smoke` | 可用性检测 |
| `market_data_fallback` | 行情降级搜索 |
| `direct` | 直接调用 |

### 维度

| 码值 | 中文标签 |
| --- | --- |
| `latest_news` | 最新消息 |
| `market_analysis` | 机构分析 |
| `risk_check` | 风险排查 |
| `announcements` | 公司公告 |
| `earnings` | 业绩预期 |
| `industry` | 行业分析 |
| `fresh_events` | 近期事件 |
| `analysis` | 综合分析 |
| `events` | 事件搜索 |
| `price_attempt_N` | 股价搜索第 N 次尝试 |

### 操作回退

| 码值 | 中文标签 |
| --- | --- |
| `search_stock_news` | 股票新闻搜索 |
| `search_comprehensive_intel` | 综合情报搜索 |
| `search_stock_events` | 股票事件搜索 |
| `search_stock_price_fallback` | 股价降级搜索 |
| `provider_search` | 供应商搜索 |
| `search_stock_news_cache` | 股票新闻缓存 |
| `search_stock_news_cache_retry` | 股票新闻缓存重试 |
| `search_stock_news_cache_wait` | 等待股票新闻缓存 |
| `search_comprehensive_intel_cache` | 综合情报缓存 |

## Acceptance Criteria

- [x] 中文界面的目标位置不再直接显示已知来源和维度码值。
- [x] 来源筛选仍使用原始来源码值请求后端，并能正确筛选。
- [x] `dimension` 为空时，已知 `operation` 码值可显示中文标签。
- [x] `price_attempt_N` 能保留实际尝试序号并显示为中文。
- [x] 未知来源、维度或操作码值原样显示。
- [x] 英文界面仍显示当前英文/原始码值。
- [x] 前端定向测试覆盖翻译、筛选值保持和未知值兜底。

## Out Of Scope

- 修改搜索审计数据库、API Schema 或后端存储码值。
- 修改 CSV/JSON 导出中的原始审计值。
- 翻译供应商名称、Key 指纹、请求/响应快照。

## Notes

- 本任务按轻量前端展示改动处理，规划阶段仅维护 PRD。
- 验证通过：定向 Vitest 6 个用例、`npm run lint`、`npm run build`、`git diff --check`。
