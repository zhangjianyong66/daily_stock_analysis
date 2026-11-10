# 实施计划：恢复 ETF 狙击点位说明

## 计划步骤

1. **建立 ETF 点位格式化入口**
   - 在 `src/analyzer.py` 增加最小的价格格式化 helper，最多保留四位小数并去除尾零。
   - 增加状态化点位说明 helper，集中处理入场、观察、退出和缺失数据文案。
   - 保证每个有效字段只出现一个可解析价格；缺失字段输出明确、无歧义数字的原因。

2. **接入确定性短线状态机**
   - 将 `_apply_etf_short_term_strategy` 中四个纯数值的 `sniper_points.update(...)` 替换为状态化说明结果。
   - 保持风险计划、状态判断、评分、动作、仓位和非 ETF 逻辑不变。
   - `secondary_buy` 明确为 MA5 确认加仓参考位；止损和止盈说明遵循已确认的单一执行价契约。

3. **补充回归测试**
   - 在 `tests/test_decision_stability.py` 覆盖试仓、观望、加仓、止盈退出和缺失点位场景。
   - 断言四字段不再是纯数字，且文案与状态一致。
   - 使用 `parse_sniper_value` 断言格式化后的点位仍还原原始 entry/MA5/stop/target 数值。
   - 覆盖最多四位小数、去除尾零和缺失字段返回 `None`。
   - 复跑决策信号、历史与通知相关测试，确认消费者无需修改。

4. **文档与交付检查**
   - 更新 `docs/CHANGELOG.md` 的 `[Unreleased]` 扁平条目，记录 ETF 报告点位说明恢复。
   - 若实现中形成可复用契约，同步补充 `.trellis/spec/backend/etf-capital-flow-short-swing.md`。
   - 检查 `AGENTS.md` 是否需要记录新的长期运行约定；没有新目录、配置或部署约定时不增加无关内容。

## 验证命令

开发阶段定向验证：

```bash
python -m py_compile src/analyzer.py
python -m pytest tests/test_decision_stability.py tests/test_decision_signal_extractor.py tests/test_analysis_history.py tests/test_notification.py -q
```

最终后端门禁：

```bash
./scripts/ci_gate.sh
python scripts/check_ai_assets.py
git diff --check
```

## 风险检查点

- 点位字符串含有多个数字时，`parse_sniper_value` 是否仍提取到价格而不是仓位、MA5、3% 或 1.5R。
- 观望/退出状态是否仍被固定的“理想买入”“二次买入”标题误导；字段内容必须明确当前不执行。
- 风险收益无效或关键位缺失时，是否错误输出可执行目标。
- ETF 文案修改是否误入普通股票路径，或改变已有决策状态、分数与仓位。

## 回滚点

- 单文件逻辑回滚：恢复 `_apply_etf_short_term_strategy` 对四个纯数值的直接写入。
- 测试与文档随逻辑一并回退；无数据库、配置、API schema 或前端迁移。

## 完成标准

- PRD 的全部验收项有对应实现或测试证据。
- 定向测试和最终后端门禁通过。
- 交付说明包含改动、原因、验证、未验证项、风险和回滚方式。
