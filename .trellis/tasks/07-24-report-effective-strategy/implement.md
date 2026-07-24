# 实施计划：报告展示实际执行策略

## 阶段一：策略快照与后端传播

1. 新增策略执行快照的类型、状态枚举、来源枚举、归一化和本地化辅助函数；覆盖默认、配置、请求、自动路由、回退、部分执行、执行降级、未记录。
2. 扩展 factory/router/AgentResult 的传播契约，在策略解析后保留 requested/effective/rejected 与失败原因；不改变现有策略选择顺序和上限。
3. 扩展 `AnalysisResult` 与 `to_dict()`，由 Pipeline 在 Agent、传统默认和降级路径统一写入最终快照；确认 LLM 原始 dashboard 不可覆盖该字段。
4. 将快照写入已有 `raw_result`，必要时同步到上下文快照；历史读取对缺失/非法结构 fail-open 为 `None`，不根据当前配置回填。

## 阶段二：API、历史、通知与 Web

5. 更新分析/历史 API schema、service 组装和前端类型，统一输出 `strategyExecution`；增加中英文/韩文标签及回退/降级文案。
6. 在 `ReportOverview` 顶部概览信息行加入响应式紧凑策略标签；实现多策略 `+N` 展开、键盘可访问、移动端不溢出；旧报告显示“策略未记录”。
7. 更新 Markdown 与通知渲染，复用同一策略格式化 helper；策略身份和来源在所有用户可见报告入口一致，详细失败原因只显示低敏文本。
8. 修改 HomePage 重新分析：历史报告有实际策略时默认复用；新增 override/touched 状态，用户明确选择后覆盖；旧报告按当前默认策略提交。

## 阶段三：测试与文档

9. 后端补 factory/router/AgentResult/Pipeline/历史兼容/Markdown/通知测试：全无效、部分无效、默认、自动未匹配、Agent 降级、旧 JSON、重建报告。
10. Web 补 ReportOverview、ReportSummary、HomePage 重新分析和多语言/响应式交互测试；验证 `+N`、展开、键盘和“策略未记录”。
11. 更新 `docs/CHANGELOG.md` `[Unreleased]` 扁平条目；按项目要求准备 Web/通知前后截图作为 PR 证据，不把截图提交到仓库。

## 验证命令

- `python -m py_compile src/agent/factory.py src/agent/orchestrator.py src/agent/executor.py src/analyzer.py src/core/pipeline.py src/services/history_service.py src/notification.py api/v1/endpoints/analysis.py api/v1/endpoints/history.py`
- `python -m pytest tests/test_agent_pipeline.py tests/test_multi_agent.py tests/test_analysis_history.py tests/test_notification.py tests/test_report_renderer.py -q`
- `cd apps/dsa-web && npm run test -- src/pages/__tests__/HomePage.test.tsx src/components/report/__tests__/AnalysisContextSummary.test.tsx`
- `cd apps/dsa-web && npm run lint && npm run build`

## 风险与回滚点

- 风险：多 Agent 的实际路由发生在技术阶段后；必须以 router 完成后的 effective 列表为准，不能只读 factory 默认值。
- 风险：历史 Markdown 从 raw_result 重建；新增字段必须进入 `AnalysisResult.to_dict()` 并在重建时保留。
- 风险：`selectedStrategyId === ''` 的默认值与“明确选择默认”语义冲突；必须增加 touched/override 状态并补回归测试。
- 回滚点：先回滚 Web/通知渲染，再保留后端可选字段；不改数据库结构，不需要数据回滚。

## 开始实施前检查

- [ ] PRD 已完成收敛，产品决策无阻断问题。
- [ ] 设计已获用户确认。
- [ ] 按 `trellis-before-dev` 读取实现前规范后再修改代码。
