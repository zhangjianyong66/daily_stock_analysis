# 日线形态报告契约

## 1. Scope / Trigger

- 个股数据准备完成后、模型分析开始前生成最近 60 个交易日的日线形态快照；报告附件和自动策略选择复用同一次识别。
- 该能力是 fail-open 的持久化快照，不适用于问股或大盘复盘，也不自动触发二次分析。

## 2. Signatures

- `src.services.kline_pattern_service.build_pattern_report(stock_code, *, language, skill_catalog, df, source, as_of) -> dict`
- `src.services.kline_pattern_service.recommend_pattern_strategies(patterns, skill_catalog, *, language, limit=3) -> list[dict]`
- `src.services.kline_pattern_service.build_runtime_pattern_match(stock_code, *, target_date, language, skill_catalog, df, source) -> PatternMatchResolution`
- `AnalysisResult.pattern_report: Optional[Dict[str, Any]]`
- `GET /api/v1/agent/skills` 的 `skills[].usage_scenarios: string[]`

## 3. Contracts

- 报告版本固定为 `schema_version=kline-pattern-v1`，包含 `status`、`period=daily`、`window_days=60`、`source`、`as_of`、`current_price`、`patterns`、`summary` 和 `recommendations`。
- `status` 取 `ok`、`insufficient_data`、`unavailable`、`not_supported`；少于 10 根日线时为 `insufficient_data`，异常为 `unavailable`。
- 每个形态包含 `name/type/strength/day_offset/description`；推荐包含 `skill_id/display_name/matched_patterns/reason/mode`。
- 推荐只保留当时 `user_invocable=true` 的策略，最多 3 项；看跌形态使用 `mode=risk_review`，不得表述为进攻性买入。
- 自动匹配只接受最近已完成交易日、至少 10 根、OHLC 有限且高低价关系有效的日线；先裁剪 `bar_date <= target_date`，最后一根必须等于 target date。日历不可用时不得按自然日猜测。
- 报告推荐与自动 winner 共用 `_RECOMMENDATION_RULES`：突破/大阳线 -> `volume_breakout`；一阳夹三阴 -> `one_yang_three_yin`；缩量回踩 -> `shrink_pullback`；底部反转组 -> `bottom_volume`；箱体 -> `box_oscillation`；看跌组 -> `emotion_cycle/risk_review`。十字星、倒锤子和方向不明形态不映射。
- 最新完整日线确认的强看跌候选风险优先；其他候选按规则优先级、强度、确认位置和 skill ID 稳定排序，只执行首项。同名形态在窗口内多次出现时保留最新确认，同一确认位置再保留更强信号，避免较早记录遮蔽最新风险。多 K 线形态 `day_offset` 表示确认位置；最近窗口规则必须读取尾部 K 线。
- 稳定失败码：`calendar_unavailable/history_unavailable/insufficient_data/invalid_daily_bars/stale_daily_bars/pattern_detection_failed/no_reliable_pattern/candidate_unavailable`。
- `pattern_report` 随 `raw_result` JSON 保存，历史缺失时保持空值；API、Web、Markdown 和通知读取同一快照。

## 4. Validation & Error Matrix

- 日线为空或识别异常 -> 返回 `unavailable` 最小快照，主分析继续。
- 日线少于 10 根 -> 返回 `insufficient_data`，不生成推荐。
- 最后一根早于 target date -> `stale_daily_bars`；字段或数值非法 -> `invalid_daily_bars`；交易日不能可靠确定 -> `calendar_unavailable`。
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
- 运行时：全部映射、强看跌冲突、稳定排序、候选不可用、周末/节假日 target date、最新窗口和每个 fallback reason。
- 并发：两只股票使用不同 winner 时 prompt state、Analyzer 和报告互不串线；形态检测对每股只执行一次。

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
