# 技术设计：根据完整日 K 线自动匹配分析策略

## 1. 设计目标与边界

把现有“分析完成后生成形态推荐”前移为“数据准备完成后、模型分析开始前生成一次形态快照并选择策略”，同时让分析完成后的报告附件复用同一快照。自动匹配是个股分析默认选择，但不替代用户本次明确指定的具体策略，也不改变分析引擎。

问股聊天和大盘复盘继续走现有策略解析。数据库不新增列，新增上下文仍随 `raw_result` JSON 持久化。

## 2. 最终数据流

```text
请求/CLI/定时任务
  -> 有本次具体 skills? -> 冻结并执行现有具体策略路径
  -> 无具体 skills
       -> 冻结原默认解析结果（仅作 fallback）与可调用 catalog
       -> 获取并保存行情
       -> 计算最近已完成交易日
       -> 读取、裁剪、校验完整日线
       -> 单次形态识别 + 候选排序
       -> 命中：构造本股票专属 prompt state
       -> 未命中：复用冻结 fallback prompt state
       -> 使用现有 Agent 或普通分析引擎
       -> 将同一 pattern_report + strategy_execution 写入结果
       -> 历史/API/Web/Markdown/通知只读快照
```

异步队列继续在入队时深拷贝 `SkillPromptState`。该状态的默认解析结果改为自动匹配的 fallback，而不是直接执行结果。配置热更新只影响之后创建的任务。

## 3. 每股不可变运行对象

新增轻量 DTO（建议放在 `src/services/kline_pattern_service.py` 或紧邻策略解析所有者的 service 模块），表达一次股票任务的结果：

```python
@dataclass(frozen=True)
class AutoStrategyResolution:
    mode: Literal["matched", "fallback", "explicit"]
    skills: tuple[str, ...]
    prompt_state: SkillPromptState
    pattern_report: dict[str, Any] | None
    selection_context: dict[str, Any] | None
```

该对象作为局部参数从 `process_single_stock()` 传入 `analyze_stock()`、普通 Analyzer/Agent helper、上下文快照和报告附件步骤。禁止把匹配后的 `analysis_skills`、`skill_prompt_state` 或 Analyzer 写回共享 `StockAnalysisPipeline` 字段，因为 CLI/定时批量分析会在同一 Pipeline 上并发处理多只股票。

普通分析需要按本次 `prompt_state` 构造局部 Analyzer，Agent executor 也显式接收本次 `prompt_state`。自动命中不参与现有“显式请求强制 Agent”判断；分析引擎仍由当前配置决定。

## 4. 完整日线与时效校验

复用 `src.core.trading_calendar.get_effective_trading_date()` 和冻结 target date。自动匹配路径要求交易日可可靠判断；出现 `calendar_unavailable`、未知市场或计算异常时返回 fallback 原因，不把自然日猜测当作完整交易日。

在 `KlinePatternService` 增加面向运行时的构建入口，接收明确 `target_date` 和冻结 catalog：

1. 调用现有 DB-first `load_history_df()`。
2. 统一解析日期列/索引，过滤 `bar_date <= target_date`，排除未来或盘中覆盖数据。
3. 校验 OHLC 必需字段、有限数值和 `latest_bar_date == target_date`。
4. 少于 10 根返回 `insufficient_data`；过期使用 `status=unavailable` + 稳定 `reason_code=stale_daily_bars`；日历不可用、字段非法和加载异常分别使用稳定 reason code。
5. 只把校验后的 DataFrame 传给检测器。

周末和节假日的 `target_date` 本身就是上一交易日，因此不会被误判为 stale。所有市场和 ETF 共用标准化 OHLCV 契约，不增加资产类型分支。

## 5. 单一形态映射与选择器

保留 `_RECOMMENDATION_RULES` 为唯一映射源，将“生成最多三个展示候选”和“选出唯一执行策略”建立在同一候选结构上。候选至少保留：`skill_id`、匹配形态、模式、强度、确认位置、规则优先级。

排序规则：

1. 最新完整日线确认的强看跌反转优先，执行 `emotion_cycle/risk_review`。
2. 其余候选按映射优先级、强度、确认时效稳定排序。
3. 过滤 `user_invocable=false`、catalog 不存在的策略；过滤后无候选则 fallback。
4. 只取第一项作为实际策略，其余候选只进入解释快照。

检测器需要修复“一阳夹三阴”读取窗口开头五根的问题，改为最近五根。对多 K 线形态增加清晰的确认位置语义，避免把形态起点误当成最新确认时间。映射和排序使用稳定代码/枚举，不解析本地化展示文字。

## 6. 从冻结 catalog 构造本次 prompt state

在 `src.agent.factory` 提取一个基于已有 `SkillPromptState`/冻结 `SkillManager` 构造单策略状态的 helper，避免执行时重新调用 `get_config()` 或重新加载策略目录。helper 负责：

- 深拷贝冻结 manager 并只激活选中策略。
- 重建 skill instructions、默认/技术策略 policy 和 legacy prompt 标记。
- 生成 `source=auto/status=normal` 的执行快照。
- 未命中时直接深拷贝冻结 fallback state，并将执行快照改成可解释的 fallback，同时保留原 fallback 的 effective/rejected 信息。

显式具体策略完全走现有 `resolve_skill_prompt_state(config, skills=...)`，不执行 K 线匹配。

## 7. 快照契约

保持 `strategy_execution.schema_version=1` 和现有字段，新增可选的规范化 `selection_context`：

```json
{
  "mode": "auto_match",
  "status": "matched|fallback",
  "as_of": "2026-07-27",
  "matched_patterns": ["缩量回踩"],
  "candidates": [
    {"skill_id": "shrink_pullback", "mode": "analysis", "matched_patterns": ["缩量回踩"]}
  ],
  "fallback_reason": null
}
```

`normalize_strategy_execution()` 必须校验并保留该可选块；缺失时维持旧快照行为。API Pydantic schema、前端 TypeScript 类型、Web 展示和文本格式化均读取同一规范化字段，不自行解析 `pattern_report` 猜策略。

匹配成功：`source=auto/status=normal/effective=[winner]`。未命中：`source=fallback/status=fallback/effective=[冻结默认]`，`selection_context.fallback_reason` 使用稳定 reason code，展示层本地化。策略执行阶段失败仍使用现有 `degraded`，但不得丢失 `selection_context`。

`pattern_report` 继续保存完整形态和最多三个推荐；自动路径把分析前生成的报告保存在 `AutoStrategyResolution`，现有 `_attach_pattern_report()` 优先附加这份快照，不再重新加载日线。

## 8. Web 与默认配置语义

首页 `selectedStrategyId=""` 继续表示没有具体 skill 覆盖，但首项名称和说明改为“自动匹配（默认）”。按钮显示应从完整 `strategyOptions` 找当前项，不能因空 ID 回退为泛化“策略”文本。

重新分析删除“未触碰时复用历史 effective IDs”的分支，始终发送当前菜单选择：自动匹配时省略 `skills`，具体策略时发送单值列表。

现有 `DEFAULT_ANALYSIS_SKILL` 字段和 API 字段名保持兼容，但用户可见名称、帮助、首页星标和提示统一改成“兜底策略”。保存空值表示跟随 `AGENT_SKILLS/内置兜底`；保存具体值只影响自动匹配失败后的任务。问股页面仍按旧策略默认逻辑，不接入自动 K 线匹配。

`ReportOverview` 在已有策略区域增加自动匹配依据和截止日；fallback 使用非阻断警告。报告推荐组件仍展示候选，不触发第二次分析。

## 9. 兼容、失败与回滚

- API 请求不新增必填字段；缺少 `skills` 的个股分析行为按需求变为自动匹配，旧客户端可直接获得新默认能力。
- 旧 `strategy_execution` 和旧 `pattern_report` 继续解析；新可选字段可被旧客户端忽略。
- 形态识别、日历、日线或策略构造失败均只触发冻结 fallback，不让主分析失败。
- 无数据库迁移。回滚时可关闭分析前自动解析并恢复直接使用冻结默认 state；新增 JSON 可选字段不会影响旧代码。
- 用户可见报告和 Web 改动需要 PR 截图；临时截图只放 PR/临时目录，不入库。

## 10. 文档更新

- 更新 `.trellis/spec/backend/strategy-execution.md` 和 `kline-pattern-report.md`。
- 更新 `AGENTS.md` 中个股默认策略解析规则，将现有默认顺序说明改成自动匹配后的 fallback 顺序。
- 更新 `docs/full-guide.md`、`docs/full-guide_EN.md`、`docs/strategy-selection-guide.md` 和 `docs/CHANGELOG.md` `[Unreleased]` 扁平条目。
- 不新增环境变量，因此 `.env.example` 只需在现有 `DEFAULT_ANALYSIS_SKILL` 注释语义需要同步时修改。
