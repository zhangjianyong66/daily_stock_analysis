# 技术设计：恢复 ETF 狙击点位说明

## 1. 根因与边界

- 根因位于 `src/analyzer.py:_apply_etf_short_term_strategy`：ETF 确定性状态机在 LLM 结果之后，用四个纯数值覆盖 `dashboard.battle_plan.sniper_points`。
- Web、通知和历史报告均直接渲染这四个字段，因此修复应优先发生在统一的分析结果生成层，而不是分别修改每个消费端。
- 保持现有四字段字符串契约，不新增 API 字段、不改变 Web 布局、不修改非 ETF 分支。

## 2. 输出契约

新增一个 ETF 点位格式化 helper，输入：

```text
strategy_state + language + entry_price + ma5 + effective_stop + minimum_target + support/resistance availability
```

输出：

```json
{
  "ideal_buy": "说明：价格元（触发条件）",
  "secondary_buy": "说明：价格元（确认条件）",
  "stop_loss": "说明：价格元（失效规则）",
  "take_profit": "说明：价格元（止盈规则）"
}
```

每个含价格的字符串必须满足 `parse_sniper_value` 可提取同一个数值。缺失价格时输出不含数字的原因文本，解析结果必须为 `None`。

## 3. 状态文案矩阵

| 状态类别 | `ideal_buy` 语义 | `secondary_buy` 语义 |
| --- | --- | --- |
| `starter_entry` | 计划触发价，右侧确认后只允许试仓 | MA5 确认加仓参考位 |
| `add_on_confirmation` / `strong_entry` | 已确认入场参考价 | MA5 确认加仓参考位，说明资金确认后的仓位上限 |
| `oversold_watch` / `neutral_watch` | 仅为观察触发参考，当前不执行买入 | 等待站回 MA5 与资金改善后再评估 |
| `take_profit_exit` / `invalidated` | 暂停买入，价格仅作当前计划参考 | 不执行加仓，按退出状态处理 |

`stop_loss` 始终只显示最终有效止损价，说明“结构失效优先、模拟硬止损不超过 3%”。

`take_profit` 只显示当前 `minimum_target_price`，说明“至少 1.5R 后先止盈一半，剩余仓位移动退出”。若风险收益计划不能生成最低目标，则显示缺失原因，不得回退为压力位或声称已满足 1.5R。

## 4. 价格格式

- 使用最多四位小数，去除尾零和末尾小数点。
- 不使用科学计数法。
- `None`、非有限数、非正数均视为无有效点位。
- 缺失文案不得包含 `1.5R`、`3%` 等可能被通用数字解析器误认为价格的数字。

## 5. 兼容性

- `AnalysisResult.get_sniper_points()` 继续返回同一字典结构。
- `src/utils/sniper_points.py:parse_sniper_value` 不改变公共解析规则；新增测试证明格式化后的四个字段仍可还原原数值。
- `analysis_service`、`history_service`、通知渲染和 Web 继续原样消费字符串，因此无需分散修改。
- 非 ETF 不调用新 helper，原有 LLM 文案保持不变。
- 中文使用中文说明；英文和现有非中文降级路径保持现有语言行为，不在本任务扩展新的本地化体系。

## 6. 风险与回滚

- 风险：说明中出现多个价格或数字，导致解析器提取错误值。控制方式是每个字段只包含一个价格，其他参数放在括号内，并用定向解析测试锁定。
- 风险：观望/退出状态仍出现“买入”命令。控制方式是按状态类别生成不同文案，并覆盖观察与退出测试。
- 风险：目标价缺失时把压力位误称为 1.5R。控制方式是区分最低目标与压力参考两种文案。
- 回滚：删除格式化 helper，恢复四字段直接写入纯数值；不会涉及数据库迁移或 API schema 回滚。
