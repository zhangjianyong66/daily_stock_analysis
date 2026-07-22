# 技术设计：场内 ETF 交易资金流

## 1. 边界与复用

- 继续使用 `DataFetcherManager.get_fundamental_context()` 的 `capital_flow` 基本面块，不新增平行 service。
- 由 `AkshareFundamentalAdapter` 负责东方财富日资金流与分时成交解析；manager 负责市场/ETF能力路由、预算、重试和统一 block 状态。
- `src/analyzer.py` 继续消费兼容的 `stock_flow.main_net_inflow`、`inflow_5d`、`inflow_10d`，新增字段只作为报告展示和盘中补充过滤。

## 2. 数据流

```text
stock_code
  -> normalize_stock_code / _market_tag
  -> manager: CN stock or CN ETF allowed; HK/US remains not_supported
  -> adapter: daily stock_individual_fund_flow(stock, market)
  -> choose max trade date
  -> aggregate main 1/3/5/10d + previous windows + large/super-large fields
  -> optional intraday trade details with explicit secid market
  -> capital_flow block {status, data, source_chain, errors}
  -> analyzer guardrail + prompt
```

日流字段保留现有兼容结构：

```json
{
  "main_net_inflow": 0,
  "main_net_inflow_pct": 0,
  "previous_main_net_inflow": 0,
  "previous_main_net_inflow_pct": 0,
  "inflow_3d": 0,
  "previous_inflow_3d": 0,
  "positive_days_3d": 0,
  "inflow_5d": 0,
  "inflow_10d": 0,
  "large_net_inflow": 0,
  "large_net_inflow_pct": 0,
  "super_large_net_inflow": 0,
  "super_large_net_inflow_pct": 0,
  "as_of": "YYYY-MM-DD",
  "scope": "daily",
  "source": "akshare.stock_individual_fund_flow"
}
```

盘中字段单独放在 `intraday_flow`，避免把盘中部分数据误写成日主力净额：

```json
{
  "active_buy_amount": 0,
  "active_sell_amount": 0,
  "active_net_inflow": 0,
  "neutral_amount": 0,
  "trade_count": 0,
  "as_of": "ISO timestamp",
  "scope": "intraday",
  "classification": "vendor_classified",
  "is_estimated": true
}
```

## 3. 沪深路由

- 上海 ETF：`51/52/56/58` 前缀，传 `market="sh"` 或 Eastmoney `secid=1.<code>`。
- 深圳 ETF：`15/16/18` 前缀，传 `market="sz"` 或 Eastmoney `secid=0.<code>`。
- 复用现有 `ETF_PREFIXES`，增加一个最小的市场参数 helper，禁止使用“默认 sh”处理所有 ETF。

## 4. 最新日与累计

- 日资金流按日期列解析并选最大有效日期，不能复用对财报“第一行通常最新”的假设。
- 最近 5/10 日累计使用按日期降序后的最近有效行求和；缺失行不补零伪造，至少缺少主力值时该字段为 `None` 并通过 status/limitations 表达。
- `status=ok` 要求主力日值可用；只有大单或超大单部分可用时使用 `partial`。

## 5. 盘中实现与降级

- 盘中成交按供应商返回的买卖盘性质聚合；中性盘仅计入 `neutral_amount`，不参与主动净流入。
- 成交量若以“手”返回，统一乘以 100；若数据源直接返回金额，优先使用金额避免重复换算。
- 盘中抓取设置独立短预算，失败不覆盖成功的日流；最终 block 可为 `partial`，并在 `errors` / `source_chain` 中记录原因。
- 盘中数据不是交易所官方主力定义，必须在 prompt 和 payload 标记供应商分类/估算。

## 6. 评分与报告兼容

- ETF 短线资金状态不要求 1/3/5 日全部转正：最新日较前一日改善，且最新日转正或最近 3 日累计优于前序 3 日窗口时形成 `improving`；最近 3 日累计转正形成 `confirmed_inflow`。5 日累计用于限制仓位上限，10 日只做背景。普通股票原有方向语义保持兼容。
- `intraday_flow.active_net_inflow` 仅用于报告展示，不进入 `_capital_flow_bias_with_status`、评分或动作校准；它不改变已有 unavailable 语义，也不在缺失时用成交额代替。
- Prompt 增加“场内交易资金流”标题、数据范围和截止时间；普通股票可以继续显示板块排行，ETF 没有板块排行时显示 N/A/不适用。
- ETF Prompt 明确目标持有周期为 1-5 个交易日，输出入场触发、失效条件、短线止损/止盈和最迟复核时间；10 日资金流仅作为背景，不得压过 1-5 日量价和资金变化。
- ETF 短线机会采用高抛低吸/均值回归框架：超跌位置必须与支撑、止跌和资金改善共同判断；高位正乖离、压力位和资金走弱共同构成高抛条件。
- 中期均线结构降为背景信息，不能单独覆盖短线反弹机会或追高风险。单一指标不直接触发评分跨档或买卖动作。
- 超跌采用右侧确认状态机：`oversold_watch`（仅超跌）→ `starter_entry`（支撑有效、停止创新低、资金流出收窄或转入）→ `add_on_confirmation`（站回短期均线/突破确认）。任一阶段有效跌破支撑且资金未改善则转为 `invalidated`。
- 状态机对应分批仓位：`starter_entry` 为 20%-30%，`add_on_confirmation` 上限 40%-60%；普通到达第一目标/1.5R 可止盈一半。完整高抛 2-of-3 条件触发 `take_profit_exit` 并全额退出，`invalidated` 同样退出。仓位数字是单只 ETF 的计划上限，不代表组合总仓位。
- `invalidated` 同时受结构与硬止损约束：结构止损取本次反弹支撑失效位，硬止损为试仓成本下方 3%；计划使用更近的风险边界。入场到结构止损超过 3% 时不生成试仓建议。T+1 跳空只描述首次可执行退出，不承诺按止损价成交。
- 入场前计算 `R = entry_price - effective_stop_price`，并将手续费/预估滑点纳入有效风险与收益；第一压力位必须满足 `resistance_price >= entry_price + 1.5 * R`，否则保持观察。到第一压力或 1.5R 减半，剩余仓位按 MA5/前一日低点/资金转弱移动退出；第 2 日无进展触发减仓，第 5 日触发退出或新计划重评。
- 持仓信息是可选上下文，不是前置依赖。未知持仓状态下继续使用现有 `no_position` / `has_position` 双分支：前者以建议触发价作为计划成本，后者只能使用当前结构和关键位，不推断真实成本与持有天数。
- 未知持仓时，3% 硬止损只用于 `no_position` 的模拟计划；`has_position` 仅输出结构风控价格。展示文案明确建议仓位不等于账户真实仓位，持仓读取失败不得改变分析任务终态。
- ETF 继续复用 `sentiment_score`，但 prompt 将其限定为 1-5 日机会分并写入策略版本/周期元数据；现有 canonical 80/60/40/20 分段不变。非 ETF 路径不注入该策略，避免改变普通股票语义。
- `oversold_watch` 使用 2-of-3 规则：`rsi_12 < 35`、`bias_ma5 <= -3%`、`change_3d <= -4%` 且接近支撑。该规则只创建 setup，`starter_entry` 仍要求停止创新低和日资金流改善。
- `take_profit_exit` 使用对称 2-of-3 规则：`rsi_12 > 65`、`bias_ma5 >= 3%`、`change_3d >= 4%` 且接近压力；命中后全额退出，不在同一计划中保留趋势底仓。
- `starter_entry` 接受 `improving` 资金拐点；`add_on_confirmation` 必须是 `confirmed_inflow` 且价格站回 MA5/关键位。流入收窄、转出或 3 日窗口恶化作为高抛/退出的资金确认。盘中估算值不参与这些状态。
- 流动性仅进入执行风险文案，不进入机会分或动作状态机。可用成交额/换手信息提示限价单与滑点；缺少 IOPV/折溢价时明确数据缺失，不推断 ETF 必然贴近净值。
- 决策消费前比较 `stock_flow.as_of` 与 phase context 的 `effective_daily_bar_date`；只接受同一交易日。过期日流保留在 payload/prompt 的历史区，但不进入资金状态机。盘中使用上一完整交易日时必须显示具体截止日期。
- 盘中 `intraday_flow` 只从逐笔 `买盘/卖盘/中性盘` 聚合；汇总 quote 的 volume/amount 只进入活跃度展示。禁止以价格涨跌符号分配买卖方向。盘中 block 始终标记 `estimated/vendor_classified`，不进入机会分。
- 资金状态以比例为主、金额为辅：`latest_pct > 0 >= previous_pct`，或 `latest_pct - previous_pct >= 2pp` 且净流出金额收窄，形成 `improving`；`inflow_3d > 0 && positive_days_3d >= 2` 形成 `confirmed_inflow`。`inflow_5d <= 0` 时仓位上限 30%，转正后上限 60%。
- 增加 ETF 专用确定性后处理状态机，输入技术结果、资金流、价格关键位和风险收益，输出 `strategy_state/score_min/score_max/action/position_cap/reason`。LLM 分数只允许在状态区间内；越界时按边界校正并在 dashboard 记录原始分、调整分、策略版本和原因。非 ETF 路径不调用该状态机。
- 状态区间：`oversold_watch=40-59`、`starter_entry=60-69`、`add_on_confirmation=70-79`、`strong_entry=80-100`；`strong_entry` 只在资金、止跌确认和 >=1.5R 同时高度一致时开放；`take_profit_exit/invalidated=0-19` 并全额退出。

## 7. 风险、回滚与兼容

- 失败回滚点：恢复 manager ETF `not_supported` 分支即可停止新调用；兼容字段不删除，旧报告可继续读取。
- 不新增配置项，不改变 API schema；新增字段放在已有 `fundamental_context.capital_flow.data`。
- 真实网络验证受代理/上游限流影响时，必须使用离线 mock 契约测试覆盖解析和路由，并单独记录在线验证缺口。
