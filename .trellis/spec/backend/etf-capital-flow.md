# A 股场内 ETF 资金流契约

## 1. Scope / Trigger

- Trigger：修改 A 股场内 ETF 识别、东方财富资金流适配、资金流 Prompt、Agent 工具或通用决策后处理时。
- Scope：上海 `51/52/56/58`、深圳 `15/16/18` 前缀的二级市场 ETF/场内基金代码。
- 本契约不包含一级市场申购赎回、Level-2 盘口或成分股资金流推导。

## 2. Signatures

- `src.services.market_symbol_utils.is_cn_etf_symbol(stock_code: str) -> bool`
- `data_provider.fundamental_adapter.AkshareFundamentalAdapter.get_capital_flow(stock_code: str, top_n: int = 5, *, include_intraday: bool = True) -> Dict[str, Any]`
- `data_provider.fundamental_adapter.AkshareFundamentalAdapter.get_intraday_capital_flow(stock_code: str) -> Dict[str, Any]`
- `data_provider.base.DataFetcherManager.get_capital_flow_context(stock_code: str, budget_seconds: Optional[float] = None) -> Dict[str, Any]`

## 3. Contracts

- 日资金流调用 `stock_individual_fund_flow`：上海传 `market="sh"`，深圳传 `market="sz"`；必须按日期倒序解析，不能假设第一行最新。
- `stock_flow` 至少保留兼容字段 `main_net_inflow/inflow_5d/inflow_10d`，并提供最新/前一日主力净额与净占比、最近/前序 3 日、3 日流入天数、大单/超大单、`as_of/scope/source/data_quality`。
- 3/5/10 日累计只在窗口完整且每行主力值有效时计算；缺行返回 `None`，不得补零。
- ETF 日流与盘中流分开调用。日流先执行；盘中只使用总预算的剩余部分且上限为 3 秒。盘中超时、空数据或字段漂移时保留日流，区块使用 `partial` 并写入 `limitations/errors`。
- 日流网络调用已有明确异常且无 payload 时使用 `failed`，不能伪装为 `not_supported`；本轮跳过同属 Eastmoney 的逐笔调用并记录 `intraday_skipped_after_daily_source_failure`。
- 盘中只聚合供应商逐笔的买盘、卖盘和中性盘；手数乘 100，中性和未知方向不进入主动净流入。`intraday_flow` 必须标记 `scope=intraday`、`classification=vendor_classified`、`is_estimated=true`。
- ETF 与其他标的一样进入通用分析和市场环境护栏。资金流可作为 Prompt 和通用稳定性校准的参考，但不得触发 ETF 专用状态机，强制修改评分、买卖动作、仓位、止损止盈或持有期限。
- 不新增环境变量或密钥；资金流和盘中流单源失败保持 fail-open。

## 4. Validation & Error Matrix

- 非 CN 市场 -> `capital_flow.status=not_supported`。
- 日资金流超时/异常且无 payload -> `failed`，分析主流程 fail-open。
- 日流成功、盘中超时/无方向 -> `partial`，保留 `stock_flow`，`intraday_flow={}`，写入 `intraday_trade_direction_unavailable`。
- 只有盘中汇总成交量额、没有买卖性质 -> 不生成主动方向估算。
- `as_of` 缺失或早于完整日线 -> 保留原始日期和限制说明，由通用分析判断数据时效，不生成 ETF 专用动作。

## 5. Good / Base / Bad Cases

- Good：日流 1 秒成功，盘中调用 3 秒超时；报告仍展示最新完整日日流，状态为 `partial`。
- Good：ETF 资金流进入通用 Prompt，但最终评分、动作和市场环境限制仍由通用分析链决定。
- Base：日流和盘中流均可用；报告展示两种时间口径，通用分析可把它们作为参考，但不会生成 ETF 专用动作。
- Bad：把日流和逐笔放入一个超时任务，导致逐笔卡住后已成功日流也丢失。
- Bad：用成交额、涨跌幅或红绿 K 推断盘中主力方向。
- Bad：根据 ETF 资金流写入专用策略字段，或绕过通用大盘环境护栏。

## 6. Tests Required

- `tests/test_etf_capital_flow.py`：沪深参数、最新/前一日、完整窗口、买卖/中性/未知、只有汇总量额、盘中超时仍保留日流。
- `tests/test_fundamental_context.py`：manager 解除 ETF 固定 `not_supported`，其他股票专属能力继续降级。
- `tests/test_data_tools_get_capital_flow.py`：Agent 工具展示 scope/date 和盘中估算语义。
- `tests/test_analyzer_news_prompt.py`：ETF 资金流仍进入 Prompt，且不存在额外的强制交易计划。
- `tests/test_decision_stability.py`、`tests/test_daily_market_context_guardrail.py`：ETF 使用通用稳定性和市场环境护栏，不写入或绕过专用策略。

## 7. Wrong vs Correct

### Wrong

```python
if is_cn_etf_symbol(result.code):
    result.sentiment_score = fixed_etf_score(capital_flow)
    result.operation_advice = fixed_etf_action(capital_flow)
    return
```

这会让同一份资金流绕过通用分析和市场环境护栏，并把参考数据升级成强制交易结论。

### Correct

```python
# ETF 与其他标的一样走通用后处理；资金流只是 fundamental_context 的一部分。
stabilize_decision_with_structure(result, trend_result, fundamental_context)
apply_daily_market_context_guardrail(result, daily_market_context, report_language)
```

资金流数据契约保持稳定，评分、动作和风险限制仍由通用链路统一处理。
