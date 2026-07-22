# A 股场内 ETF 资金流与 1-5 日短线契约

## 1. Scope / Trigger

- Trigger：修改 A 股场内 ETF 识别、东方财富资金流适配、技术指标、报告 Prompt、决策后处理或通用决策护栏时。
- Scope：上海 `51/52/56/58`、深圳 `15/16/18` 前缀的二级市场 ETF/场内基金代码。
- 本契约不包含一级市场申购赎回、Level-2 盘口或成分股资金流推导。

## 2. Signatures

- `src.services.market_symbol_utils.is_cn_etf_symbol(stock_code: str) -> bool`
- `data_provider.fundamental_adapter.AkshareFundamentalAdapter.get_capital_flow(stock_code: str, top_n: int = 5, *, include_intraday: bool = True) -> Dict[str, Any]`
- `data_provider.fundamental_adapter.AkshareFundamentalAdapter.get_intraday_capital_flow(stock_code: str) -> Dict[str, Any]`
- `data_provider.base.DataFetcherManager.get_capital_flow_context(stock_code: str, budget_seconds: Optional[float] = None) -> Dict[str, Any]`
- `src.analyzer.stabilize_decision_with_structure(result, trend_result=None, fundamental_context=None, market_phase_summary=None) -> None`

## 3. Contracts

- 日资金流调用 `stock_individual_fund_flow`：上海传 `market="sh"`，深圳传 `market="sz"`；必须按日期倒序解析，不能假设第一行最新。
- `stock_flow` 至少保留兼容字段 `main_net_inflow/inflow_5d/inflow_10d`，并提供最新/前一日主力净额与净占比、最近/前序 3 日、3 日流入天数、大单/超大单、`as_of/scope/source/data_quality`。
- 3/5/10 日累计只在窗口完整且每行主力值有效时计算；缺行返回 `None`，不得补零。
- ETF 日流与盘中流分开调用。日流先执行；盘中只使用总预算的剩余部分且上限为 3 秒。盘中超时、空数据或字段漂移时保留日流，区块使用 `partial` 并写入 `limitations/errors`。
- 日流网络调用已有明确异常且无 payload 时使用 `failed`，不能伪装为 `not_supported`；本轮跳过同属 Eastmoney 的逐笔调用并记录 `intraday_skipped_after_daily_source_failure`。
- 盘中只聚合供应商逐笔的买盘、卖盘和中性盘；手数乘 100，中性和未知方向不进入主动净流入。`intraday_flow` 必须标记 `scope=intraday`、`classification=vendor_classified`、`is_estimated=true`，只展示、不评分。
- ETF 日流只有 `stock_flow.as_of == effective_daily_bar_date` 时可进入决策。资金改善是净占比由负转正，或改善至少 2 个百分点且负净额同步收窄；3 日累计大于 0 且至少 2 日流入才是确认。
- `etf_short_swing_v1` 使用超跌/高抛 2-of-3、右侧止跌、MA5、5 日资金和至少 1.5R 生成确定性状态。状态区间为：`take_profit_exit/invalidated=0-19`、`oversold_watch/neutral_watch=40-59`、`starter_entry=60-69`、`add_on_confirmation=70-79`、`strong_entry=80-100`。
- 结构止损与计划价下方 3% 取更近边界；结构止损距离超过 3% 或第一压力不足含 0.1% 费用/滑点后的 1.5R 时不得入场。
- 状态机生成后，`daily_market_context_guardrail` 不得再改写其动作或分数，否则 dashboard 状态与最终结论会矛盾。市场阶段护栏仍可限制“立即盘中执行”的表述。
- ETF `dashboard.battle_plan.sniper_points` 保持四字段字符串契约，但必须由状态机输出“说明 + 唯一价格”：入场、观察和退出状态使用不同语义，MA5 表述为确认加仓参考位，止损只显示最终有效止损，止盈只显示最低 1.5R 目标。有效字段必须可由 `parse_sniper_value` 还原同一价格；缺失字段显示不含歧义数字的原因，不得回退为孤立数字或伪造点位。
- 不新增环境变量或密钥；ETF 流动性只产生限价单、滑点和折溢价提示，不作为禁入或分数封顶条件。

## 4. Validation & Error Matrix

- 非 CN 市场 -> `capital_flow.status=not_supported`。
- 日资金流超时/异常且无 payload -> `failed`，分析主流程 fail-open。
- 日流成功、盘中超时/无方向 -> `partial`，保留 `stock_flow`，`intraday_flow={}`，写入 `intraday_trade_direction_unavailable`。
- 只有盘中汇总成交量额、没有买卖性质 -> 不生成主动方向估算。
- `as_of` 缺失或早于完整日线 -> `stale_or_unverified`，不得进入试仓/加仓。
- 超跌不足 2 项 -> `neutral_watch`；超跌满足但创新低确认字段缺失、明确创新低、破支撑、资金未改善或不足 1.5R -> `oversold_watch`。缺失值不得当作“未创新低”。
- 支撑有效、停止创新低、资金改善且风险收益有效 -> `starter_entry`，上限 30%；MA5、3 日确认和 5 日转正 -> `add_on_confirmation/strong_entry`，上限 60%。
- 高抛 2-of-3 或结构失效 -> 分别 `take_profit_exit/invalidated`，全额退出。

## 5. Good/Base/Bad Cases

- Good：日流 1 秒成功，盘中调用 3 秒超时；报告仍展示最新完整日日流，状态为 `partial`，评分不读取盘中值。
- Good：超跌 2-of-3、支撑止跌、日流改善、第一压力大于 1.5R；只给 20%-30% 试仓，不因空头均线机械低分。
- Base：资金流日期与日线同日但仍净流出、价格继续创新低；保持观察，不猜底。
- Base：RSI 与 MA5 正乖离满足高抛 2-of-3；全额退出，不保留底仓。
- Bad：把日流和逐笔放入一个超时任务，导致逐笔卡住后已成功日流也丢失。
- Bad：用成交额、涨跌幅或红绿 K 推断盘中主力方向。
- Bad：状态机写入 `starter_entry=65` 后又被通用大盘护栏改成 `hold=52`，但 dashboard 仍保留 starter 状态。

## 6. Tests Required

- `tests/test_etf_capital_flow.py`：沪深参数、最新/前一日、完整窗口、买卖/中性/未知、只有汇总量额、盘中超时仍保留日流。
- `tests/test_fundamental_context.py`：manager 解除 ETF 固定 `not_supported`，其他股票专属能力继续降级。
- `tests/test_decision_stability.py`：超跌单指标不越权、继续创新低保持观察、资金改善试仓、MA5+3/5 日确认加仓、过期日流、盘中值不评分、高抛全退、3% 和 1.5R 边界。
- `tests/test_daily_market_context_guardrail.py`：通用大盘护栏不改写已有 `etf_short_swing_v1` 状态。
- `tests/test_analyzer_news_prompt.py`、`tests/test_data_tools_get_capital_flow.py`：Prompt 与 Agent 工具展示 scope/date/盘中只读语义。
- 最终执行 `./scripts/ci_gate.sh`，在线 smoke 只能补充验证，不能替代离线契约测试。

## 7. Wrong vs Correct

### Wrong

```python
payload = run_with_timeout(lambda: adapter.get_capital_flow_with_intraday(code), timeout)
if payload is None:
    return failed_block()  # 盘中卡住会丢掉已成功日流
```

### Correct

```python
daily = run_with_timeout(lambda: adapter.get_capital_flow(code, include_intraday=False), timeout)
intraday = run_with_timeout(
    lambda: adapter.get_intraday_capital_flow(code),
    min(3.0, remaining_seconds),
)
return merge_daily_with_optional_intraday(daily, intraday)
```

### Wrong

```python
intraday_net = amount if change_pct > 0 else -amount
```

### Correct

```python
intraday_net = vendor_buy_amount - vendor_sell_amount
# neutral/unclassified trades stay outside directional flow
```
