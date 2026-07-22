# 实施计划：场内 ETF 交易资金流

## 计划步骤

1. **数据适配与路由**
   - 在 `data_provider/fundamental_adapter.py` 增加沪深 ETF 市场路由、日资金流最新/前一日选择、最近与前序 3 日窗口及 5/10 日累计解析。
   - 解析主力、大单、超大单净额及净占比，保留现有 `stock_flow` 兼容字段。
   - 增加盘中成交方向聚合 helper，明确买/卖/中性和“手/金额”单位。
2. **Manager 与状态契约**
   - 在 `data_provider/base.py` 解除 CN ETF 资金流的固定 `not_supported`，保留非 CN 市场和真实失败的降级。
   - 为 ETF 盘中数据设置有限预算和 fail-open，记录 `scope/as_of/source/errors`。
3. **分析与 Prompt**
   - 更新 `src/analyzer.py` 资金流提示，展示场内口径、截止日期、主力/大单/超大单和盘中主动净流入。
   - 为 ETF Prompt 固定 1-5 个交易日短线周期，要求入场触发、失效条件、止损/止盈和复核时间。
   - 注入高抛低吸/超跌反弹约束，避免空头均线机械低分和多头高乖离机械高分。
   - 为超跌反弹增加观察、试仓、确认加仓和失效四阶段约束，禁止仅凭超跌直接买入。
   - 将阶段映射到 20%-30% 试仓、40%-60% 确认仓位、普通 1.5R 止盈一半，以及完整高抛/失效全额退出，禁止满仓买入建议。
   - 增加支撑失效与 3% 硬止损约束，并覆盖止损距离过大和 T+1 跳空语义。
   - 按入场价、有效止损价及费用/滑点计算 1.5R 入场门槛，增加分批止盈、2 日减仓和第 5 日退出/重评规则。
   - 保持持仓信息可选；无持仓数据时仍生成双分支，禁止编造成本、盈亏或持有时间。
   - 空仓按计划触发价计算止损/目标，持仓分支只给结构风控，并注明建议仓位不代表真实账户仓位。
   - 将 ETF `sentiment_score` 限定为 1-5 日短线机会分，记录策略版本/周期并保持非 ETF 语义不变。
   - 增加 ETF 确定性状态后处理，强制 `oversold_watch/starter_entry/add_on_confirmation/strong_entry/take_profit_exit/invalidated` 对应的 score/action/position 区间，保留原始分、调整分和校正原因。
   - 实现/注入超跌 2-of-3 候选规则，并测试单指标不会直接产生试仓动作。
   - 实现/注入高抛 2-of-3 规则，并测试命中后输出全额退出。
   - 实现资金改善/确认状态：拐点允许试仓、3 日累计转正允许加仓、5 日限制仓位、10 日只展示。
   - 使用主力净占比转正/改善 2 个百分点并结合金额收窄判定拐点，计算 3 日正流入天数和 5 日仓位上限。
   - 保持流动性为软风险提示，不作为机会分封顶或禁止交易条件；缺少净值/折溢价时不作保证。
   - 校验资金流 `as_of` 与最新完整日线日期；过期数据只展示，覆盖交易日与盘中日期文案。
   - 仅从逐笔买卖方向估算盘中主动流；汇总量额只展示活跃度，禁止按涨跌猜测方向，并断言盘中值不参与评分。
   - 检查决策护栏在 ETF 日资金流有流入、流出、冲突和缺失时的动作与分数校准，并断言盘中估算值不参与决策。
4. **测试与文档**
   - 新增/更新适配器、manager、决策护栏、Prompt 和 Agent 工具测试，覆盖上海/深圳 ETF、最新行、累计和失败降级。
   - 更新 `docs/CHANGELOG.md` `[Unreleased]`，必要时补充数据源说明。

## 验证命令

```bash
python -m py_compile data_provider/fundamental_adapter.py data_provider/base.py src/analyzer.py
python -m pytest tests/test_fundamental_context.py tests/test_decision_stability.py tests/test_analyzer_news_prompt.py tests/test_data_tools_get_capital_flow.py -q
python -m pytest -m "not network"
./scripts/ci_gate.sh
```

在线验证（非阻断，不能替代离线测试）：

```bash
python -m pytest -m network -k "capital_flow or etf"
```

## 风险检查点

- AkShare `stock_individual_fund_flow` 的列名、日期顺序或资金流单位发生漂移。
- 上海 ETF 被错误按深圳路由，或深圳 ETF 继续走默认上海路由。
- 盘中“买卖盘性质”缺失时被错误当成主动买卖。
- 资金流日期早于当前行情日期，却在报告中显示为“今日资金流”。
- ETF 数据源失败后错误触发 score cap，或新增字段破坏旧普通股票报告。

## 回滚点

- 适配器解析问题：回退到原有股票资金流解析并保留 ETF `not_supported`。
- 盘中接口不稳定：关闭盘中补充调用，只保留日资金流，保持 block 的明确 scope。
- Prompt/评分联动问题：恢复原有 `main_net_inflow/inflow_5d/inflow_10d` 消费，不删除新增持久化字段。
