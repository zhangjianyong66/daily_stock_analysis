# 恢复 ETF 狙击点位说明

## Goal

恢复 ETF 分析报告中狙击点位的可读说明，同时保留新短线策略计算出的具体价格，避免前端、通知和历史报告只显示孤立数字。

## Background / Confirmed Facts

- ETF 短线策略在 `src/analyzer.py:_apply_etf_short_term_strategy` 中会写入 `dashboard.battle_plan.sniper_points`。
- 当前实现用 `entry_price`、`ma5`、`effective_stop_price`、`minimum_target_price` 直接覆盖四个点位字段，因此覆盖了模型原先生成的“理想买入点/次优买入点/止损原因/目标位”说明文本。
- Web `apps/dsa-web/src/components/report/ReportStrategy.tsx`、通知和历史报告渲染器都直接展示这些字段；字段类型也是字符串，因此覆盖发生后用户看到的就是单个数字。
- `src/utils/sniper_points.py:parse_sniper_value` 可以从“说明 + 价格”文本中提取价格，决策信号和历史持久化不需要点位字段必须是纯数字。

## Requirements

1. ETF 报告的四个狙击点位继续显示可执行的具体价格。
2. 每个点位恢复简洁的中文说明，至少包含该价格的用途或触发条件：理想入场、确认/次优入场、结构止损、第一目标/1.5R。
3. 说明应由确定性 ETF 策略生成，不能依赖 LLM 是否返回旧格式文本；中英文报告保持现有语言约定。
4. 不破坏现有点位提取、决策信号、历史记录、通知和 Web 展示；数值解析仍应得到同样的价格。
5. 非 ETF 报告行为保持不变。
6. 点位说明必须随 ETF 策略状态变化；观望或卖出状态不得把参考价格表述成可立即执行的买入指令。
7. `secondary_buy` 的说明采用“确认加仓参考位”语义，因为当前确定性策略将其绑定为 MA5，而不是简单的更低补仓价。
8. 止损点位只展示一个最终有效止损价，并在同一段说明中解释“结构失效优先、模拟硬止损不超过 3%”两层规则。
9. `take_profit` 继续以确定性风险计划计算的最低 1.5R 目标价作为唯一数值，不改成第一压力价；说明中补充先止盈一半和剩余仓位移动退出规则。
10. ETF 点位价格最多保留四位小数，并去除无意义的尾零，以兼容场内 ETF 的报价精度。
11. 点位数据缺失时显示明确且不含歧义数字的原因说明，例如“暂无有效止盈位（缺少压力位或风险收益数据）”；不得输出 `None`、伪造价格或只显示破折号。

## Technical Notes

- 入场状态（`starter_entry`、`add_on_confirmation`、`strong_entry`）：理想点位表述为可执行的计划触发价，MA5 表述为确认加仓参考位。
- 观察状态（`oversold_watch`、`neutral_watch`）：价格只作为观察/确认参考，说明必须明确当前不执行买入。
- 退出状态（`take_profit_exit`、`invalidated`）：说明必须明确暂停买入并按当前状态退出，不得把参考价呈现为新的买入指令。
- 点位仍使用现有四字段字符串契约；通过“说明：价格元（条件）”保持 `parse_sniper_value` 的数值提取能力，不新增前端字段或改变布局。

## Acceptance Criteria

- [x] ETF `dashboard.battle_plan.sniper_points` 四个字段不再是孤立数字，而是“说明 + 价格”的可读字符串。
- [x] 说明反映当前策略状态和风险规则：右侧确认/试仓、MA5 或确认加仓、结构/3% 硬止损、第一压力或至少 1.5R 止盈。
- [x] `oversold_watch`、`neutral_watch`、`take_profit_exit` 和 `invalidated` 的点位文案明确标注等待、暂停买入或退出语义。
- [x] `secondary_buy` 显示为确认加仓参考位，并说明站回 MA5、资金确认等条件。
- [x] `stop_loss` 只给出一个可执行的最终止损价，不并列制造两个互相竞争的止损点。
- [x] `take_profit` 的数值解析结果与当前最低 1.5R 目标价保持一致。
- [x] 点位显示不把三位或四位小数的 ETF 价格粗略截成两位，也不显示冗余尾零。
- [x] 任一点位缺少计算依据时显示明确原因，且 `parse_sniper_value` 返回 `None`。
- [x] `parse_sniper_value`、决策信号 payload、历史保存与已有非 ETF 测试继续通过，并新增 ETF 回归断言。
- [x] Web、通知和历史 Markdown 展示中能看到说明文本。

## Out Of Scope

- 不调整 ETF 评分、资金流计算、仓位上限或状态机规则。
- 不修改非 ETF 的点位生成逻辑或前端布局。
