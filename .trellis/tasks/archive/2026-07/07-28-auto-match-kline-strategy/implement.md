# 实现计划

## 阶段 1：规则与数据质量

1. [x] 加载 `trellis-before-dev`，核对 backend、strategy execution、Kline report、cross-layer 和质量规范。
2. [x] 扩展 K 线形态服务的稳定 reason code、完整交易日裁剪/校验和单次构建入口；覆盖空数据、少于 10 根、过期、字段异常、日历不可用和周末/节假日。
3. [x] 修复“一阳夹三阴”错误读取窗口开头数据的问题，并为多 K 线形态补充明确确认位置语义。
4. [x] 从同一映射生成候选和唯一 winner，实现强看跌风险优先、强度/时效/规则优先级排序以及不可调用策略过滤。
5. [x] 扩充 `tests/test_kline_pattern_service.py`（必要时新增聚焦测试文件），覆盖全部映射、冲突、稳定排序、最新窗口和所有 fallback reason。

## 阶段 2：每股策略运行状态

6. [x] 在 factory/service 层新增“从冻结 catalog 构造单个自动策略 prompt state”的 helper，不在执行时重新读取配置或策略目录。
7. [x] 定义每股不可变 `AutoStrategyResolution`，在 `process_single_stock()` 数据准备后生成，并以局部参数传给普通分析和 Agent 分支。
8. [x] 重构 Pipeline/Analyzer 调用，保证自动匹配不修改共享 `self.analysis_skills`、`self.skill_prompt_state` 或共享 Analyzer；添加批量并发两股不同策略不串线回归。
9. [x] 保持分析引擎选择不变：自动匹配不强制 Agent，显式具体策略继续沿用原行为；覆盖普通分析、单/多 Agent 和执行降级。
10. [x] 异步队列继续在入队时冻结 fallback state/catalog；验证入队后修改 `DEFAULT_ANALYSIS_SKILL` 或策略目录不会改变原任务。

## 阶段 3：快照与跨层出口

11. [x] 扩展 `strategy_execution` 的可选 `selection_context` 构建、归一化、本地化和文本格式化，保持 schema v1/旧快照兼容。
12. [x] 让自动匹配成功、未命中、数据失败和候选不可用分别写入一致的 source/status/effective/context；策略运行降级不得丢失自动选择上下文。
13. [x] 让现有形态报告附件复用分析前快照，不重复读取日线；验证 raw_result、历史重建、同步/异步 API、Markdown 和通知往返一致。
14. [x] 更新 API Pydantic schema和 Web TypeScript 类型；所有消费者读取共享字段，不从当前配置或 `pattern_report` 反推历史策略。

## 阶段 4：首页默认行为与文案

15. [x] 首页首项改为“自动匹配（默认）”，初始和清空选择均省略 `skills`；具体策略仍发送单值列表。
16. [x] 重新分析始终按当前菜单选择，移除历史 effective strategy 的隐式复用；覆盖自动匹配和具体策略两条测试。
17. [x] 把 `DEFAULT_ANALYSIS_SKILL` 相关首页快捷操作、设置帮助和提示改为“自动匹配失败后的兜底策略”，问股入口保持原范围。
18. [x] `ReportOverview` 展示自动匹配结果、完整日线截止日、依据和 fallback 原因，补中文/英文 UI 与中/英/韩报告文案及可访问性测试。

## 阶段 5：文档、验证与审查

19. [x] 更新 `docs/CHANGELOG.md`、中英文完整指南、策略选择指南、`.env.example` 注释（如受影响）、`AGENTS.md` 和两份 backend Trellis 规范。
20. [x] 执行改动 Python 文件 `py_compile` 和后端定向回归，至少覆盖 K 线服务、策略快照、任务冻结、Pipeline、API、历史、通知和报告渲染。
21. [ ] 执行受影响 Web 测试、`npm run lint`、`npm run build`；用桌面/移动视口截图检查首页菜单与报告区域，无溢出、重叠或错误默认标记。（测试、lint、build 已通过；截图因临时 API mock 夹具不完整未完成。）
22. [x] 执行 `git diff --check` 和 `trellis-check`；因修改 `AGENTS.md`/spec，执行 `python scripts/check_ai_assets.py`。不自动运行完整 `./scripts/ci_gate.sh`，除非用户另行明确要求。

## 重点验证命令

```bash
.venv/bin/python -m pytest tests/test_kline_pattern_service.py tests/test_strategy_execution.py tests/test_task_queue_config_sync.py tests/test_agent_pipeline.py tests/test_multi_agent.py -q
.venv/bin/python -m pytest tests/test_analysis_api_contract.py tests/test_analysis_history.py tests/test_notification.py tests/test_report_renderer.py -q
python -m py_compile <changed_python_files>
cd apps/dsa-web && npm run test -- src/pages/__tests__/HomePage.test.tsx src/components/report/__tests__/ReportOverview.test.tsx src/components/report/__tests__/KlinePatternReport.test.tsx
cd apps/dsa-web && npm run lint && npm run build
python scripts/check_ai_assets.py
git diff --check
```

## 风险点与回滚

- 并发风险：每股匹配状态必须局部传递；禁止写共享 Pipeline/Analyzer。失败时先回滚局部状态重构，不保留半共享实现。
- 日期风险：自动匹配必须严格依赖可确认的最近完整交易日；无法确认就 fallback，不以自然日猜测。
- 兼容风险：`strategy_execution` 只增加可选字段且保留 schema v1；历史缺失字段正常工作。
- 行为回滚：恢复“无显式策略直接使用冻结默认 state”，保留新增快照字段和报告解析不会阻断旧流程。
- 数据回滚：无数据库迁移；历史 JSON 无需删除或回填。
