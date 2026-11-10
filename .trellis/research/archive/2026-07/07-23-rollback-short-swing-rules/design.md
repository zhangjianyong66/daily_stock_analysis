# 技术设计：回退 ETF 短线交易规则

## 1. 目标与边界

- 目标是把 ETF 分析从 `etf_short_swing_v1` 专用后处理恢复为原有通用分析路径。
- 保留 2026-07-22 同批变更中的 ETF 场内资金流获取、解析、Agent 工具和数据展示；资金流回到普通的参考信息，不再驱动 ETF 专用动作或评分。
- 保留系统原本的通用资金流稳定性校准和历史报告通用狙击点位解析。
- 不执行整提交 `git revert`，因为 `71af690` 同时包含需要保留的资金流能力。

## 2. 运行时改动

1. `src/analyzer.py`
   - 移除 `stabilize_decision_with_structure()` 中针对 ETF 的专用策略分支和提前返回。
   - 删除仅服务于该策略的常量、资金流状态计算、风险收益计算、状态化狙击点位构造、评分夹逼和报告 Prompt 中的强制短线规则段落。
   - 保留通用结构/资金流稳定性函数，以及资金流展示段落；必要时将 ETF 资金流标题恢复为不承诺短线计划的描述。
2. `src/daily_market_context_guardrail.py`
   - 删除识别 `etf_short_swing_v1` 并绕过通用大盘护栏的分支，恢复通用护栏行为。
3. `src/core/pipeline.py`、`src/stock_analyzer.py` 等
   - 只移除为 ETF 专用策略传递上下文或消费策略结果的代码；不触碰资金流上下文传递。

## 3. 测试、文档与协作规范

- 删除或改写只验证短线状态机、固定分数区间、仓位/1.5R/第 2/5 日规则、状态化狙击点位的测试；保留并补充 ETF 资金流路由、解析、失败降级和通用资金流参考测试。
- `AGENTS.md`、`.trellis/spec/backend/etf-capital-flow-short-swing.md`、`docs/full-guide.md`、`docs/full-guide_EN.md`、`docs/market-support.md` 删除短线规则契约，保留资金流契约。
- `docs/CHANGELOG.md` `[Unreleased]` 删除狙击点位恢复条目，将 ETF 新功能条目改为只描述场内资金流接入。
- 不改动历史发布记录、数据库结构、API schema 或前端。

## 4. 兼容与风险

- `capital_flow` payload 结构及其 `main_net_inflow`、`inflow_5d`、`inflow_10d` 兼容字段保持不变。
- 普通股票的买入降级、资金流不可用和稳定性仪表盘行为保持不变。
- ETF 评分/动作恢复为 LLM/通用护栏决定，历史上已落盘的旧报告不迁移；新报告不应再写入 `etf_short_term_strategy`。
- 变更完成后通过 `git diff` 和 `rg` 检查，确保生产代码和当前文档不存在 `etf_short_swing_v1` 残留，但历史归档任务可保留其原始记录。

## 5. 回滚方式

- 本次修改不提交前先保持工作区可审查；如验证不通过，可在用户确认后按文件恢复本任务产生的 diff，或从当前提交重新建立补丁。
