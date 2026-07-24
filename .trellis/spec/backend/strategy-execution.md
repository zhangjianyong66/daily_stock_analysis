# 策略执行快照规范

## 1. Scope / Trigger

- Trigger：分析策略选择、Agent 路由、历史报告、API、Web、Markdown 或通知读取策略身份时。
- Scope：一次分析最终实际执行的策略，不包含买点、止损、止盈等“策略点位”。

## 2. Signatures

- `src.schemas.strategy_execution.build_strategy_execution_snapshot(...) -> dict[str, Any]`
- `src.schemas.strategy_execution.normalize_strategy_execution(value: Any) -> Optional[dict[str, Any]]`
- `src.schemas.strategy_execution.localize_strategy_execution(value: Any, language: str) -> Optional[dict[str, Any]]`
- API `ReportMeta.strategy_execution: Optional[StrategyExecution]`
- 前端 `ReportMeta.strategyExecution?: StrategyExecution | null`

## 3. Contracts

- 快照保存于分析结果 `raw_result.strategy_execution`，不新增数据库列。
- 必填字段：`schema_version=1`、`status`、`source`、`requested`、`effective`、`rejected`；可选 `message`。
- `status`：`normal`、`partial`、`fallback`、`degraded`、`unrecorded`。
- `source`：`request`、`default`、`config`、`auto`、`fallback`、`unknown`。
- 每个策略项保存稳定 `id`、历史快照名称 `display_name` 和 `status`（`selected`/`degraded`/`not_executed`）。
- 后端生成的快照是唯一事实来源；历史缺少或非法快照时返回空值，展示层显示“策略未记录”，不得根据当前配置推断。
- API endpoint 将 JSON 本地化结果传给 `ReportMeta` 时必须经过 `StrategyExecution.model_validate` 或在模型构造阶段校验，不能在 Pydantic 模型创建后直接赋普通字典。

## 4. Validation & Error Matrix

- 非映射、版本不支持、状态或来源非法 -> 归一化为 `None`，按旧报告处理。
- 请求策略全部不可用 -> `status=fallback`，保留 `requested`/`rejected` 和最终 `effective`。
- 请求策略部分不可用 -> `status=partial`，未执行策略进入 `rejected` 或 `not_executed`。
- 已选策略运行失败或超时 -> `status=degraded`，不得伪装为切换到其他成功策略。
- 正常默认或自动路由未匹配后的默认候选 -> 不产生异常告警。

## 5. Good / Base / Bad Cases

- Good：分析结果写入快照，历史 API、实时 API、Web、Markdown 和通知均从同一字段读取。
- Base：旧历史没有快照，API 返回 `null`，Web 和文本报告显示低强调“策略未记录”。
- Bad：用首页当前配置解释旧报告，或在 endpoint 中把本地化字典直接赋给已构造的 `ReportMeta`，导致类型契约绕过且消费者访问模型属性失败。

## 6. Tests Required

- 快照归一化：默认、固定配置、请求回退、部分执行、执行降级、非法旧数据。
- API：从持久化 `raw_result` 重建报告时断言 `report.meta.strategy_execution.source` 和嵌套策略项属性可用。
- 跨层：历史报告、通知、Markdown、Web 实时/历史展示使用同一名称、来源和状态语义。
- 重新分析：历史有效策略默认复用，首页明确选择覆盖，旧报告走当前默认。

## 7. Wrong vs Correct

### Wrong

```python
meta = ReportMeta(...)
meta.strategy_execution = localize_strategy_execution(raw_value, language)
```

### Correct

```python
localized = localize_strategy_execution(raw_value, language)
if localized is not None:
    meta.strategy_execution = StrategyExecution.model_validate(localized)
```
