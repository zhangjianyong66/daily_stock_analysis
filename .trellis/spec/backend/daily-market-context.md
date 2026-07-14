# 每日大盘上下文契约

## 1. Scope / Trigger

- 适用于修改 `StockAnalysisPipeline` 的目标交易日计算、`DailyMarketContextService` 的缓存/历史复用、`run_market_review()` 的历史持久化或大盘复盘锁时。
- 该链路服务 API 批量分析、单股 Pipeline、CLI 和调度入口；日期身份漂移会导致重复调用行情源、搜索与 LLM。

## 2. Signatures

- `DailyMarketContextService.get_context(..., target_date: Optional[date], current_query_id: Optional[str], require_query_id_match: bool) -> Optional[DailyMarketContext]`
- `run_market_review(..., daily_market_context_target_date: Optional[date] = None) -> Optional[str] | Optional[MarketReviewRunResult]`
- `_persist_market_review_history(..., daily_market_context_target_date: Optional[date] = None) -> int`
- 内部历史快照字段：`context_snapshot.daily_market_context_target_date: "YYYY-MM-DD"`。

## 3. Contracts

- 缓存身份是目标交易日、市场和规范化报告语言；查询隔离开启时还包含 `current_query_id`。
- `daily_market_context_target_date` 记录 Pipeline 计算的有效交易日，仅由每日大盘上下文生成路径传入并写入 `context_snapshot`。
- `market_review_payload.date` 是报告生成日；`generated_at` 与历史 `created_at` 是实际生成时间。它们不得替代目标交易日。
- 公开 API/Web payload、报告 Markdown 和数据库 schema 不包含新增契约；快照键是可选 JSON 字段，不需要迁移。
- `cn/hk/us/jp/kr` 使用同一严格规则；市场或报告语言不匹配时不得复用。
- 旧记录缺少新字段时，按 payload `trade_date/date`，再按 `created_at` 的现有精确规则兼容；不得增加前后一天、周末或时区猜测。
- 历史写入失败保持 fail-open，后续任务允许重新生成，不能以绝对防重牺牲个股分析的大盘风险上下文。

## 4. Validation & Error Matrix

- 显式目标日合法且等于请求目标日 -> 继续校验市场、语言和必要的查询 ID 后复用。
- 显式目标日合法但不同 -> 拒绝该记录，不得回退 payload 日期、`created_at` 或同查询 ID。
- 显式目标日缺失或非法 -> 按旧记录精确日期逻辑兼容。
- 市场或报告语言不同 -> 拒绝复用。
- 首个任务持久化成功 -> 锁等待者必须在再次生成前读到历史并返回。
- 历史读取/写入失败或锁释放后仍无匹配记录 -> 记录告警并保持现有 fail-open 行为。

## 5. Good / Base / Bad Cases

- Good：自然日为 T、目标交易日为 T-1，历史 payload 的报告日为 T，但快照目标日为 T-1；并发等待者复用该记录，`run_market_review` 不再调用。
- Base：报告生成日与目标交易日相同；新旧记录都按精确日期复用，现有用户可见内容不变。
- Bad：把 `market_review_payload.date` 改写为目标交易日，导致报告日期语义漂移。
- Bad：显式目标日不匹配时仍因 query ID、payload 日期或 `created_at` 命中。
- Bad：历史写入失败后把运行时结果当成跨 Pipeline 的持久成功，导致后续分析静默缺少可恢复路径。

## 6. Tests Required

- 持久化测试断言：显式目标日写为 ISO 日期；未传参数时不出现该键；公开 payload 日期不变。
- 历史匹配测试断言：显式字段优先、字段不匹配严格拒绝、非法/缺失字段按旧精确规则回退。
- 并发锁测试断言：自然日 T / 目标日 T-1 的等待者命中首份历史，且不调用第二次 `run_market_review`。
- 故障测试断言：锁释放但历史仍缺失、或持久化失败时允许后续生成。
- 市场/语言测试覆盖 `cn/hk/us/jp/kr`，并证明跨市场、跨语言不复用。
- 入口回归至少覆盖 `tests/test_daily_market_context.py`、`tests/test_market_review.py`、`tests/test_pipeline_daily_market_context.py`、`tests/test_main_schedule_mode.py`。

## 7. Wrong vs Correct

### Wrong

```python
# 报告生成日不是缓存身份。
context_snapshot["market_review_payload"]["date"] = target_date.isoformat()
```

### Correct

```python
# 保留公开报告日期，在内部快照单独记录目标交易日。
context_snapshot["daily_market_context_target_date"] = target_date.isoformat()
```
