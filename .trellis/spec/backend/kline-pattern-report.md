# 日线形态报告契约

## 1. Scope / Trigger

- 个股分析完成后生成最近 60 个交易日的日线形态附件。
- 该附件是 fail-open 的持久化快照，不适用于大盘复盘，也不自动触发二次分析。

## 2. Signatures

- `src.services.kline_pattern_service.build_pattern_report(stock_code, *, language, skill_catalog, df, source, as_of) -> dict`
- `src.services.kline_pattern_service.recommend_pattern_strategies(patterns, skill_catalog, *, language, limit=3) -> list[dict]`
- `AnalysisResult.pattern_report: Optional[Dict[str, Any]]`
- `GET /api/v1/agent/skills` 的 `skills[].usage_scenarios: string[]`

## 3. Contracts

- 报告版本固定为 `schema_version=kline-pattern-v1`，包含 `status`、`period=daily`、`window_days=60`、`source`、`as_of`、`current_price`、`patterns`、`summary` 和 `recommendations`。
- `status` 取 `ok`、`insufficient_data`、`unavailable`、`not_supported`；少于 10 根日线时为 `insufficient_data`，异常为 `unavailable`。
- 每个形态包含 `name/type/strength/day_offset/description`；推荐包含 `skill_id/display_name/matched_patterns/reason/mode`。
- 推荐只保留当时 `user_invocable=true` 的策略，最多 3 项；看跌形态使用 `mode=risk_review`，不得表述为进攻性买入。
- `pattern_report` 随 `raw_result` JSON 保存，历史缺失时保持空值；API、Web、Markdown 和通知读取同一快照。

## 4. Validation & Error Matrix

- 日线为空或识别异常 -> 返回 `unavailable` 最小快照，主分析继续。
- 日线少于 10 根 -> 返回 `insufficient_data`，不生成推荐。
- 未知/不可调用策略 -> 从推荐结果过滤，不阻塞报告。
- 无可靠形态 -> `patterns=[]`、`recommendations=[]`，摘要明确证据不足。

## 5. Good/Base/Bad Cases

- Good：检测器失败只影响形态附件，分析结果、历史保存和通知仍完成。
- Base：旧历史没有 `pattern_report` 时 Web/API 不报错、不重算、不伪造推荐。
- Bad：在历史读取时按当前策略配置重新识别，或把看跌形态映射成买入策略。

## 6. Tests Required

- 推荐规则：映射、去重、最多 3 项、不可调用策略过滤和看跌 `risk_review`。
- 报告状态：数据不足、异常、空形态和完整快照字段。
- 跨层：`AnalysisResult.to_dict()`、历史重建、API `ReportDetails.pattern_report` 和 Web camelCase 映射。

## 7. Wrong vs Correct

### Wrong

```python
history_result.pattern_report = build_pattern_report(code)
```

### Correct

```python
# 运行时只识别一次，结果随 raw_result 保存并由历史/API/Web 复用
result.pattern_report = pipeline._attach_pattern_report(result, code).pattern_report
```
