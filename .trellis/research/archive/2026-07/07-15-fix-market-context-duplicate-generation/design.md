# 技术设计：修复大盘上下文重复生成

## 1. 问题模型

当前链路包含两个不同日期概念：

- 报告生成日：`MarketAnalyzer.get_market_overview()` 使用运行时自然日构造 `MarketOverview.date`，并写入 `market_review_payload.date`。
- 上下文目标交易日：`StockAnalysisPipeline` 根据市场阶段计算 `effective_daily_bar_date`，作为 `DailyMarketContextService.get_context(target_date=...)` 的缓存身份。

历史读取却把 `market_review_payload.date` 当作目标交易日。当凌晨、周末、节假日或跨时区运行导致两个日期不一致时，锁等待者无法识别刚保存的记录，随后再次获得锁并重复生成。

## 2. 设计原则

- 不改变公开 `market_review_payload.date`、`generated_at` 或报告正文的既有语义。
- 不通过 `±1 day`、周末或时区猜测放宽历史匹配。
- 不引入数据库迁移、Redis、全局共享服务或新的配置开关。
- 复用现有 `analysis_history.context_snapshot`、大盘复盘锁和历史读取链路。
- 首份记录持久化失败时继续 fail-open，允许后续任务重试。

## 3. 数据契约

在大盘复盘历史的 `context_snapshot` 中增加可选内部字段：

```json
{
  "report_kind": "market_review",
  "market_review_region": "cn",
  "report_language": "zh",
  "daily_market_context_target_date": "2026-07-14"
}
```

字段规则：

- 仅当调用方显式传入目标交易日时写入。
- 值为 ISO `YYYY-MM-DD` 字符串。
- 不写入 `market_review_payload`，不改变 API/Web payload schema。
- 手工 API、Bot、CLI 大盘复盘未传目标日时维持原快照结构。

## 4. 调用链改动

1. `DailyMarketContextService._run_market_review_context()` 已持有规范化后的 `target_date`，调用 `run_market_review()` 时增加可选参数 `daily_market_context_target_date=target_date`。
2. `src.core.market_review.run_market_review()` 只透传该参数到 `_persist_market_review_history()`，不参与报告生成和展示。
3. `_persist_market_review_history()` 将合法日期序列化到 `context_snapshot.daily_market_context_target_date`。
4. `DailyMarketContextService._load_same_day_history()` 读取快照中的显式目标日。
5. `_record_matches_target_date()` 优先使用显式目标日进行严格匹配；字段缺失时才回退现有 payload 日期/创建日期逻辑。

## 5. 匹配优先级

历史记录按以下顺序判断：

1. `report_type`、市场、报告语言必须匹配。
2. 若存在合法 `daily_market_context_target_date`，必须与请求 `target_date` 精确相等。
3. 若新字段缺失或非法，沿用旧记录的 payload `trade_date/date`，再回退 `created_at`。
4. `require_query_id_match=true` 的既有查询隔离语义保留；显式目标日存在时同时要求目标日正确，避免同查询误用其它交易日记录。

## 6. 并发与故障语义

- 正常路径：第一个 Pipeline 获得锁、生成并保存带目标日的历史；等待者轮询历史后命中，返回 `analysis_history` 上下文，不再生成。
- 历史写入失败：等待者仍可能在锁释放后重新生成，保持现有 fail-open 行为。
- 单进程/同宿主机：继续由现有线程锁和文件锁串行化。
- 跨宿主机：本次不新增分布式锁，维持现有部署边界。

## 7. 兼容性

- 新字段为 SQLite JSON 文本中的可选键，无数据库 schema 迁移。
- 旧历史记录继续可读，并按原精确日期逻辑匹配。
- 公开 API、Web 类型、报告 Markdown、通知载荷和配置均不变。
- 已产生的重复历史不自动删除。

## 8. 测试设计

- 持久化测试：显式目标日写入历史快照，未传时不写入。
- 日期优先级测试：新字段与目标日相同，即使 payload 生成日为次日也可复用。
- 严格性测试：新字段不匹配时，不得因 payload 日期或创建日期碰巧匹配而复用。
- 旧记录兼容测试：缺少新字段时仍按旧 payload/创建日期精确匹配，不支持跨日猜测。
- 锁等待回归：等待者在首份带目标日记录出现后返回，不调用第二次 `run_market_review`。
- 故障回归：锁释放后仍无匹配历史时允许再次生成。
- 市场/语言矩阵：`cn/hk/us/jp/kr` 均使用同一字段规则；市场或语言不同不得复用。

## 9. 回滚

回滚代码与文档即可。已写入历史快照的可选字段会被旧版本忽略，无需清理或数据迁移。
