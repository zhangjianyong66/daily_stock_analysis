# 实现计划

## 阶段 1：契约与规则

1. [x] 阅读 `trellis-before-dev` 指定的 backend 与 cross-layer 规范，确认实际目录和测试约定。
2. [x] 扩展 `Skill`、YAML 解析、API `SkillInfo` 和前端 `SkillInfo` 类型。
3. [x] 为 15 个内置策略补齐 2～3 个 `usage_scenarios`，与现有策略指南核对。
4. [x] 新建 K 线形态服务，抽取现有识别算法，定义 `kline-pattern-v1` 状态、形态、推荐结构和规则映射。
5. [x] 为形态服务和推荐器补充纯单元测试，覆盖全部映射、去重、最多 3 项和未知/不可调用策略过滤。

## 阶段 2：后端流水线与报告契约

6. [x] 在 `AnalysisResult` 增加 `pattern_report`，接入序列化和历史重建。
7. [x] 在传统 LLM 与 Agent 共用的流水线收尾路径附件形态报告，保证 Agent 提前返回路径也覆盖；失败仅写入不可用状态并继续主分析。
8. [x] 扩展 `ReportDetails`、同步/异步/历史 API 构造逻辑，验证旧报告缺失字段兼容。
9. [x] 更新 Markdown、Jinja 批量模板和通知短摘要，确保中/英/韩文标签和回退路径完整。
10. [x] 运行后端定向测试、`py_compile` 和报告快照/历史兼容测试，修复失败后再进入前端。

## 阶段 3：Web 交互

11. [x] 首页策略菜单展示短场景标签，保持当前单选和默认项行为，覆盖响应式布局和键盘导航。
12. [x] 新增/接入 K 线形态报告组件：摘要默认可见，详细形态与推荐理由可折叠。
13. [x] 推荐按钮通过 HomePage 回调只替换单个 `selectedStrategyId`，不自动提交；历史报告和无回调场景保持安全降级。
14. [x] 增加中文、英文、韩文 UI 文案和前端类型/字段映射。
15. [x] 运行受影响前端测试、`npm run lint`、`npm run build`，检查桌面端未受 API 破坏性变更影响。

## 阶段 4：收敛与验收

16. [x] 执行跨层回归：策略接口、分析 API、历史报告、Markdown/通知、首页和报告组件。
17. [x] 检查未提交的用户改动 `docs/strategy-selection-guide.md` 与 `docs/CHANGELOG.md` 未被覆盖，并按项目规则补充变更日志条目。
18. [x] 运行 `trellis-check` 质量检查，确认 PRD/设计/实现清单与代码一致；已新增 backend 形态报告契约规范。
19. [x] 已获得用户确认并通过 `task.py start` 进入实现阶段。

## 重点验证命令

```bash
python -m py_compile src/agent/skills/base.py src/agent/tools/analysis_tools.py src/services/kline_pattern_service.py src/core/pipeline.py src/analyzer.py api/v1/endpoints/agent.py api/v1/endpoints/analysis.py api/v1/schemas/history.py src/services/history_service.py
python -m pytest tests/test_agent_backend.py tests/test_strategy_execution.py tests/test_analysis_api_contract.py tests/test_analysis_history.py -q
python -m pytest tests/test_kline_pattern_service.py tests/test_strategy_catalog.py -q
cd apps/dsa-web && npm run test -- src/pages/__tests__/HomePage.test.tsx src/components/report/__tests__/KlinePatternReport.test.tsx src/components/report/__tests__/ReportOverview.test.tsx
cd apps/dsa-web && npm run lint && npm run build
```

## 回滚点

- 后端：移除流水线附件步骤，保留可选字段和历史读取兼容。
- 前端：移除形态组件和推荐回调，策略菜单仍可读取新增字段而不影响旧选择。
- 数据：无需数据库迁移；`pattern_report` 随 raw JSON 写入，旧记录不回填、不重算。
