# 技术设计

## 1. 边界与总体方案

本任务拆成四个相互衔接的层次，但保持一个统一数据契约：

1. 策略定义层为 `Skill` 增加可选 `usage_scenarios`，内置 YAML 提供短标签，API 原样透传，首页只负责展示。
2. 新增 K 线形态服务，复用现有历史数据加载和形态识别算法，输出稳定版本化的 `pattern_report`，并在同一服务内执行确定性策略推荐。
3. 个股分析流水线在 Agent 和传统 LLM 两条路径汇合后调用形态服务，失败只写入不可用状态，不阻断主分析；结果通过 `AnalysisResult.to_dict()` 随原始 JSON 持久化。
4. API、历史重建、Web、Markdown 和通知全部读取同一 `pattern_report` 快照，避免在不同出口重复识别或重新推断。

大盘复盘不进入该流水线，不增加个股形态字段。

## 2. 策略元数据契约

在 `src/agent/skills/base.py` 的 `Skill` 增加：

```python
usage_scenarios: List[str] = field(default_factory=list)
```

YAML 解析兼容 `usage_scenarios` 缺失、字符串和列表。15 个内置策略在 `strategies/*.yaml` 增加 2～3 个短标签，标签内容以现有 `docs/strategy-selection-guide.md` 和策略 `instructions` 为准。自定义策略缺失时保持空数组，API 仍返回原描述；前端把描述作为兼容说明，不阻塞或改写策略加载。

`api/v1/endpoints/agent.py` 的 `SkillInfo` 增加 `usage_scenarios: List[str]`，`apps/dsa-web/src/api/agent.ts` 同步类型。旧客户端忽略新增字段即可继续工作。

## 3. K 线形态数据契约

新增 `src/services/kline_pattern_service.py`，将 `src/agent/tools/analysis_tools.py` 中现有 `analyze_pattern` 的检测逻辑抽为可复用函数；工具 handler 只负责参数校验和调用，避免维护两份检测实现。服务使用已有 `load_history_df`，固定 `period=daily`、`window_days=60`，遵守当前冻结目标日期。

`pattern_report` 使用普通 JSON 结构，版本固定为 `kline-pattern-v1`：

```json
{
  "schema_version": "kline-pattern-v1",
  "status": "ok|insufficient_data|unavailable|not_supported",
  "period": "daily",
  "window_days": 60,
  "source": "...",
  "as_of": "YYYY-MM-DD|null",
  "current_price": 0.0,
  "patterns": [
    {
      "name": "放量突破20日高点",
      "type": "bullish_breakout",
      "day_offset": 0,
      "strength": "强",
      "description": "收盘突破近20日最高，量能配合"
    }
  ],
  "summary": "放量突破20日高点",
  "recommendations": [
    {
      "skill_id": "volume_breakout",
      "display_name": "放量突破",
      "matched_patterns": ["放量突破20日高点"],
      "reason": "识别到放量突破形态，优先确认突破有效性和阻力位。",
      "mode": "analysis|risk_review"
    }
  ]
}
```

状态语义：`ok` 表示成功识别（包括空形态列表）；`insufficient_data` 表示少于 10 根日线；`unavailable` 表示加载或识别异常；`not_supported` 仅用于明确不支持的市场/入口。`ok` 且无可靠形态时 `patterns=[]`、`recommendations=[]`，摘要显示证据不足，不制造空壳推荐。

推荐器只接受结构化形态名称/类型和分析当时的 skill catalog，过滤 `user_invocable=false` 或不存在的策略，并保留顺序、去重、最多 3 项。看跌映射使用 `mode=risk_review`，前端和通知不得显示为买入建议。推荐理由由规则模板和命中形态组成，不调用 LLM。

## 4. 流水线与持久化

在 `src/core/pipeline.py` 增加一个小的 fail-open 附件步骤，在 Agent 分析返回路径和传统 LLM 分析结果完成后都执行，避免 Agent 分支提前 return 导致数据缺失：

```python
result = self._attach_pattern_report(result, code)
```

该步骤从 `self.skill_prompt_state.skill_manager.list_skills()` 获取当前 catalog，传给形态服务；异常记录 warning 并写入 `status=unavailable` 的最小快照。不会新增 LLM 请求，也不改变原分析结论、策略执行快照或任务状态。

`src/analyzer.py` 的 `AnalysisResult` 增加可选 `pattern_report: Optional[Dict[str, Any]]`，`to_dict()` 持久化该字段；历史 `_rebuild_analysis_result` 读取它，旧 JSON 缺失时保持 `None`。不改已有 `pattern_analysis` 文本字段。

## 5. API 与历史兼容

在 `api/v1/schemas/history.py` 增加可选 `pattern_report: Optional[Dict[str, Any]]`（或等价的轻量 Pydantic 嵌套类型），`ReportDetails` 构造同时从当前结果和 `raw_result` 读取。同步响应、异步完成响应和历史详情均走现有 `AnalysisReport` 构造路径，确保字段位置一致：`report.details.pattern_report`。

保存内容只包含低敏行情派生数据、形态名称和策略 ID/显示名，不保存原始 DataFrame、完整行情响应或密钥。

## 6. Web、Markdown 与通知

- `HomePage.tsx`：`SkillInfo` 的场景标签渲染为可换行短 badge，保留名称、默认标记和原描述；默认项没有标签。
- 新增 `KlinePatternReport` 展示组件或放入现有 report 组件目录，使用 `details.patternReport`。在 `ReportSummary` 中置于 `ReportStrategy` 之后，摘要默认可见，形态明细/推荐理由折叠。
- 推荐按钮只调用 HomePage 传入的回调，将单个 `skill_id` 写入现有 `selectedStrategyId`，关闭菜单或自动分析均不发生；未提供回调时（例如纯历史/嵌入场景）按钮保持展示但不可触发跨页面操作。
- `analysis.ts` 增加 `PatternReport` 类型及 camelCase 映射字段；报告语言工具增加中/英/韩的标题、状态、强度、推荐模式文案，缺失时中文回退。
- `src/services/history_service.py` 的 Markdown 生成在技术面段落增加一行形态摘要和最多 3 项推荐；`src/notification.py` 同步增加短摘要，避免输出全部日线数据。
- Jinja 批量模板只展示每只股票的一行形态摘要/推荐，详细列表留在 Web/API；无 `pattern_report` 的历史结果不输出空标题。

## 7. 风险与回滚

- 风险：历史加载额外耗时、数据源失败、旧报告字段缺失。通过复用 DB/冻结日期、fail-open、可选字段和定向测试控制。
- 风险：内置 YAML 标签与文档漂移。实现前以 YAML/指南交叉核对，测试检查所有 user-invocable 策略至少有标签。
- 回滚：删除流水线附件调用和前端展示即可恢复旧行为；保留 `pattern_report` JSON 不影响旧代码。若需要完全回滚，移除新增 YAML 字段/API 可选字段和报告组件即可，不需要数据库迁移。
