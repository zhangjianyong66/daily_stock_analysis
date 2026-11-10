# 执行计划：回退 ETF 短线交易规则

## 实施步骤

1. 重新检查工作区状态，建立 `71af690`、`47a642b` 与当前 HEAD 的目标 diff 清单。
2. 按设计从 `src/analyzer.py` 移除 ETF 专用短线后处理和强制 Prompt，保留资金流获取/展示与通用稳定性校准。
3. 移除 `src/daily_market_context_guardrail.py` 的 ETF 专用绕过逻辑，检查 pipeline/stock analyzer 是否仍有仅供该策略使用的上下文传递。
4. 清理短线专用测试断言，保留资金流测试并补充“ETF 不再写入专用策略结果、资金流仍可用”的回归断言。
5. 同步清理 AGENTS、backend spec、中文/英文指南、市场边界说明和 `[Unreleased]` 变更记录。
6. 执行静态搜索，确认生产代码、当前文档和测试不再引用 `etf_short_swing_v1` 或已删除的强制短线规则；历史归档任务不纳入清理范围。

## 验证命令

```bash
python -m py_compile src/analyzer.py src/daily_market_context_guardrail.py src/core/pipeline.py src/stock_analyzer.py data_provider/base.py data_provider/fundamental_adapter.py
python -m pytest tests/test_etf_capital_flow.py tests/test_fundamental_context.py tests/test_data_tools_get_capital_flow.py tests/test_decision_stability.py tests/test_analyzer_news_prompt.py tests/test_daily_market_context_guardrail.py -q
rg -n "etf_short_swing_v1|A股场内 ETF 1-5 日短线计划|ETF 短线计划|结构止损.*1\.5R|第.?5.?日.*退出" src data_provider api tests docs AGENTS.md .trellis/spec/backend
git diff --check
```

## 风险点与检查门

- `src/analyzer.py` 改动最大，必须确认通用个股资金流稳定性函数和非 ETF 行为没有被误删。
- `tests/test_decision_stability.py` 同时覆盖通用逻辑和 ETF 专用逻辑，不能整文件删除；应逐条按契约重写或移除。
- 文档中“ETF 资金流”与“ETF 短线计划”经常同段出现，需人工复读，避免删除资金流说明。
- 本地不默认执行完整 `./scripts/ci_gate.sh`；交付时明确说明定向验证范围及未覆盖的 CI/Docker/在线 smoke。
