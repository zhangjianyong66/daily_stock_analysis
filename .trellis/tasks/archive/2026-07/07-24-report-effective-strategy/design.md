# 技术设计：报告展示实际执行策略

## 1. 目标与边界

为每次成功生成的股票分析报告保存一份不可反推的策略执行快照，并让 Web 实时/历史报告、Markdown 和通知共用该快照。现有“策略点位”字段保持不变。

本次不改变策略选择算法、不新增 ETF 专用策略、不把 LLM 文本中的策略词语当作事实来源；只补齐策略解析结果、执行状态和报告展示。

## 2. 现有数据流与问题

- 首页在 `apps/dsa-web/src/pages/HomePage.tsx:426-432` 将单选策略转换为 `skills` 请求字段；未选择时省略字段。
- `src/agent/factory.py:104-153` 校验请求/配置 skill，并在没有有效 skill 时回落到默认 skill；当前默认是 `bull_trend`。
- 多 Agent 的 `src/agent/orchestrator.py:763-792` 可能在技术阶段后根据行情路由出最多三个 skill，运行失败的非关键 skill 会降级，不应被伪装为成功切换。
- `AnalysisResult` 当前没有策略执行字段；`to_dict()` 进入历史 `raw_result`，但默认上下文快照只在显式请求时保存 `skills`（`src/core/pipeline.py:2448-2449`）。
- API 的 `ReportMeta`/前端 `ReportMeta` 没有策略身份；`ReportStrategy` 仅代表买点、止损和止盈。
- Markdown/通知从 `AnalysisResult` 或历史 `raw_result` 生成，因此适合复用同一规范化字段。

## 3. 规范化执行快照

在 `src/schemas/` 增加纯数据结构和归一化 helper（不依赖 FastAPI/ORM），建议字段如下：

```json
{
  "schema_version": 1,
  "status": "normal|partial|fallback|degraded|unrecorded",
  "source": "request|default|config|auto|fallback|unknown",
  "requested": [{"id": "box_oscillation", "display_name": "箱体震荡"}],
  "effective": [{"id": "box_oscillation", "display_name": "箱体震荡", "status": "selected|degraded|not_executed"}],
  "rejected": [{"id": "removed_skill", "reason": "unavailable"}],
  "message": "..."
}
```

- `effective` 保存执行时的 ID 与展示名快照，历史上不随 YAML 改名而漂移。
- `requested`/`rejected` 只在有请求或回退时保存；敏感信息不进入该结构。
- `normal` 的默认策略显示“系统默认”，自动路由显示“自动路由”；无效请求全部被过滤时为 `fallback`，部分有效时为 `partial`；策略 Agent 已选中但阶段失败时为 `degraded`。
- 历史数据没有该字段时 API 返回 `null`，Web/Markdown 显示“策略未记录”，不得按当前配置回填。
- 使用现有 `localize_strategy_skill`/报告语言标签本地化内置 skill；自定义策略回退到快照 `display_name`，API 仍保留 ID 供追溯。

## 4. 跨层传播

1. Factory/router 在解析完成和路由完成后构造快照，挂到 `AgentResult` 的可选字段；单 Agent 使用 factory 解析结果，多 Agent 在 router/阶段结束后补充实际 `effective` 与降级状态。
2. `src/core/pipeline.py` 将 `AgentResult` 快照写入 `AnalysisResult.strategy_execution`，并在历史保存前固定快照；非 Agent 传统分析也写入解析后的隐式默认 `bull_trend`（当前默认基线），不依赖日志推断。
3. `AnalysisResult.to_dict()` 持久化 `strategy_execution` 到已有 JSON `raw_result`，无需新增 SQLite 列或迁移；上下文快照可同步保存同一低敏结构，便于诊断，但 API 以 raw result 的规范化字段为主。
4. `api/v1/schemas/analysis.py`、`api/v1/schemas/history.py` 和前端 `apps/dsa-web/src/types/analysis.ts` 增加可选 `strategyExecution`；历史服务和分析 endpoint 从 `raw_result`/旧快照读取并保持旧报告兼容。
5. `ReportOverview` 在顶部股票信息行渲染紧凑策略标签：名称 + 来源；多策略显示首个名称和 `+N`，点击/键盘可展开完整列表和每项状态；回退/降级用非阻断警告样式。
6. `src/services/history_service.py` 的 Markdown 生成与 `src/notification.py` 的通知生成调用同一格式化 helper，避免各自解析 ID 或重复 fallback。

## 5. 重新分析语义

- 历史报告携带 `strategyExecution.effective` 时，Web 的“重新分析”默认把这些 ID 作为请求 skills。
- 首页策略菜单只有在用户明确操作后才覆盖历史策略；需要新增独立的 override/touched 状态，避免当前 `selectedStrategyId === ''` 同时表示“未选择”和“明确选择默认策略”。
- 旧报告没有快照时沿用当前系统默认策略。
- 重新分析提交后仍由后端重新校验并生成新的执行快照；历史策略删除时按既有回退规则处理，并在新报告中明确显示回退。

## 6. 兼容与风险

- 不改 `AnalysisHistory` 表结构，旧数据库与旧历史记录自然返回 `null`。
- 旧客户端忽略新增 API 字段；新客户端对缺失字段显示“策略未记录”。
- 不把 runtime agent 失败变成另一个策略成功；保留 `degraded`，同时沿用现有报告失败/诊断链路。
- 通知渠道失败仍 fail-open；策略元数据生成失败不得阻断主分析，至少输出 `unrecorded`/低敏诊断。
- 用户可见报告结构变化需更新 `docs/CHANGELOG.md` `[Unreleased]`，并补 Web/通知前后截图作为 PR 证据，临时截图不入库。

## 7. 回滚

若跨层字段引发兼容问题，可先停止渲染新增标签，保留 `strategy_execution` JSON 字段；旧报告和旧客户端不受影响。恢复代码后无需数据库回滚。
