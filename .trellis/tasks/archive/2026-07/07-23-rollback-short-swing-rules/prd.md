# 回退短线交易规则

## Goal

撤销 2026-07-22 引入的 ETF `etf_short_swing_v1` 短线交易决策规则，使 ETF 恢复到规则变更前的评分、动作和报告语义，同时保留同一提交中新增的场内 ETF 资金流能力。

## Background / Confirmed Facts

- 工作区当前位于 `main`，干净且与 `origin/main` 同步；未执行任何回退或写入代码操作。
- 主要功能提交为 `71af69060c3e396cadceaaddee77a8850ff4481c`（`feat(etf): 接入场内资金流与短线交易规则`），涉及 31 个文件、约 2135 行新增；其中同时包含场内 ETF 日/盘中资金流、ETF 短线评分/动作护栏、Prompt/报告、文档/spec 和测试。
- 后续提交 `47a642bfbca419bca1653ec93ad3da6a06990102`（`fix(etf): 恢复狙击点位说明`）在 `src/analyzer.py` 与 `tests/test_decision_stability.py` 继续补充了短线规则相关行为，并同步文档/spec。
- 当前短线规则的核心契约标识为 `etf_short_swing_v1`，代码主要位于 `src/analyzer.py` 和 `src/daily_market_context_guardrail.py`；相关测试主要位于 `tests/test_decision_stability.py`、`tests/test_analyzer_news_prompt.py` 与 `tests/test_etf_capital_flow.py`。
- 场内 ETF 资金流能力还被 `data_provider/base.py`、`data_provider/fundamental_adapter.py`、`src/agent/tools/data_tools.py`、报告 Prompt、文档和测试共同消费，不能在未确认范围时粗暴删除。

## Fundamental Truths

- 用户不满意的是新增短线交易规则的实际可用性，而不是已经存在的所有资金流数据能力（两者在同一提交中混合交付）。
- 回退必须恢复可解释、可验证的历史行为，不能留下代码、测试、文档或 spec 对已删除规则的悬挂引用。
- 回退不应影响与本需求无关的 2026-07-22 变更及当前工作区之外的提交。

## Requirements

- R1. 仅删除用户确认不再需要的 2026-07-22 ETF 短线规则及其后续“狙击点位说明”补丁，保留同一提交中的场内 ETF 资金流数据接入。
- R2. 对保留的能力维持既有兼容契约；对删除的能力清理实现、调用链、测试、文档、AGENTS 规则和 Trellis spec，避免继续宣称或执行已删除规则。
- R3. 不覆盖用户已有改动；当前工作区干净，正式修改前仍需再次检查状态和目标提交边界。
- R4. 完成与改动面匹配的离线测试、语法检查，并核对旧行为与回退后行为的关键契约。

## Acceptance Criteria

- [x] 用户确认回退边界：仅删除短线规则及狙击点位补丁，保留 ETF 资金流。
- [x] 回退后不存在不应保留的 `etf_short_swing_v1` 生产调用、规则 Prompt/报告输出、测试断言或文档/spec 残留。
- [x] ETF `capital_flow` 数据获取、Agent 工具和既有资金流过滤语义仍可用；资金流仍可展示和作为通用分析参考，但不再触发 ETF 专用短线状态机。
- [x] 受影响 Python 文件通过 `py_compile`，相关 pytest 用例通过；未执行的在线或完整门禁在交付中明确说明。
- [x] 回退变更可通过目标提交边界审查，且不包含与本次需求无关的修改。

## Technical Notes

- 已确认的实现边界：`src/analyzer.py` 中 ETF 专用确定性策略入口、评分区间、状态机、风险收益计划和状态化狙击点位属于删除范围；通用稳定性校准、ETF `capital_flow` 数据解析/获取、通用历史报告狙击点位解析不属于删除范围。
- 相关文档与测试按保留/删除边界同步调整；`docs/CHANGELOG.md` 的 `[Unreleased]` 删除“狙击点位恢复”条目，ETF 新功能条目改为只描述场内资金流数据接入，正式发布历史不改写。

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
