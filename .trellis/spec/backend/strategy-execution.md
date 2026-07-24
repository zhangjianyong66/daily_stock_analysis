# 策略执行快照规范

## 1. Scope / Trigger

- Trigger：分析策略选择、Agent 路由、历史报告、API、Web、Markdown 或通知读取策略身份时。
- Trigger：新增或修改部署级默认策略、`AGENT_SKILLS` 回退、异步任务创建或策略列表接口时。
- Scope：一次分析最终实际执行的策略，不包含买点、止损、止盈等“策略点位”。

## 2. Signatures

- `src.schemas.strategy_execution.build_strategy_execution_snapshot(...) -> dict[str, Any]`
- `src.schemas.strategy_execution.normalize_strategy_execution(value: Any) -> Optional[dict[str, Any]]`
- `src.schemas.strategy_execution.localize_strategy_execution(value: Any, language: str) -> Optional[dict[str, Any]]`
- `src.agent.factory.resolve_default_skill_selection(config, *, skill_catalog=None) -> DefaultSkillResolution`
- `src.agent.factory.resolve_skill_prompt_state(config, skills=None) -> SkillPromptState`
- 环境变量 `DEFAULT_ANALYSIS_SKILL`：单个 `user_invocable=true` 的稳定 skill ID，空值表示跟随系统默认。
- API `GET /api/v1/agent/skills`：`default_skill_id/default_skill_source/saved_default_skill_id/default_skill_warning`。
- API `ReportMeta.strategy_execution: Optional[StrategyExecution]`
- 前端 `ReportMeta.strategyExecution?: StrategyExecution | null`

## 3. Contracts

- 快照保存于分析结果 `raw_result.strategy_execution`，不新增数据库列。
- 必填字段：`schema_version=1`、`status`、`source`、`requested`、`effective`、`rejected`；可选 `message`。
- `status`：`normal`、`partial`、`fallback`、`degraded`、`unrecorded`。
- `source`：`request`、`default`、`config`、`auto`、`fallback`、`unknown`。
- 每个策略项保存稳定 `id`、历史快照名称 `display_name` 和 `status`（`selected`/`degraded`/`not_executed`）。
- 个股分析统一优先级：单次明确 `skills` > 有效 `DEFAULT_ANALYSIS_SKILL` > `AGENT_SKILLS` > 内置 metadata 默认；大盘复盘不读取该配置。
- `DEFAULT_ANALYSIS_SKILL` 是部署级单值覆盖；保存值存在时，多 Agent router 使用冻结后的固定结果，不再被行情自动路由替换。
- 首页和问股可视觉选中 `default_skill_id`，但用户未操作时请求中必须省略 `skills`；用户清空问股策略时保留显式 `skills=[]` 以清理旧上下文。
- 异步分析在入队时解析并深拷贝 `SkillPromptState`；配置热更新只影响之后创建的任务，排队中、执行中任务继续使用冻结状态。
- 策略列表接口中 `default_skill_source` 取 `saved/agent_skills/builtin/fallback`；保存值失效时 `saved_default_skill_id` 保留原值，`default_skill_warning` 给出非敏感提示。
- 后端生成的快照是唯一事实来源；历史缺少或非法快照时返回空值，展示层显示“策略未记录”，不得根据当前配置推断。
- API endpoint 将 JSON 本地化结果传给 `ReportMeta` 时必须经过 `StrategyExecution.model_validate` 或在模型构造阶段校验，不能在 Pydantic 模型创建后直接赋普通字典。

## 4. Validation & Error Matrix

- 非映射、版本不支持、状态或来源非法 -> 归一化为 `None`，按旧报告处理。
- 请求策略全部不可用 -> `status=fallback`，保留 `requested`/`rejected` 和最终 `effective`。
- 请求策略部分不可用 -> `status=partial`，未执行策略进入 `rejected` 或 `not_executed`。
- Web 保存非空 `DEFAULT_ANALYSIS_SKILL` 且 ID 不可调用 -> 拒绝保存，字段错误码 `unavailable_strategy`。
- 已保存默认失效 -> 不中断分析，回退到 `AGENT_SKILLS` / 内置默认；快照使用 `status=fallback/source=fallback`，API 返回 warning。
- 显式请求有效且保存默认失效 -> 显式请求仍优先，快照保持 `source=request`，失效默认不得污染本次请求状态。
- 已选策略运行失败或超时 -> `status=degraded`，不得伪装为切换到其他成功策略。
- 正常默认或自动路由未匹配后的默认候选 -> 不产生异常告警。

## 5. Good / Base / Bad Cases

- Good：分析结果写入快照，历史 API、实时 API、Web、Markdown 和通知均从同一字段读取。
- Good：首页显示保存默认，但用户直接提交时不发送 `skills`；任务入队后修改默认值，原任务仍使用入队时的策略。
- Base：旧历史没有快照，API 返回 `null`，Web 和文本报告显示低强调“策略未记录”。
- Base：`DEFAULT_ANALYSIS_SKILL` 为空时保持原有 `AGENT_SKILLS` / 内置默认行为。
- Bad：用首页当前配置解释旧报告，或在 endpoint 中把本地化字典直接赋给已构造的 `ReportMeta`，导致类型契约绕过且消费者访问模型属性失败。
- Bad：页面初始化后把视觉默认作为显式 `skills` 发送，或 worker 启动时重新读取热更新后的默认值。

## 6. Tests Required

- 快照归一化：默认、固定配置、请求回退、部分执行、执行降级、非法旧数据。
- 默认解析：保存默认优先于 `AGENT_SKILLS`、显式请求优先于保存默认、保存值失效可解释回退。
- 配置/API：动态候选包含跟随系统默认；无效保存返回 `unavailable_strategy`；skills/legacy strategies 接口字段一致。
- 任务/router：队列冻结 prompt state；保存默认优先于自动行情路由。
- Web：首页和问股初始默认不发送 `skills`，用户操作后显式发送；快捷保存、恢复和失败不误更新默认标记。
- API：从持久化 `raw_result` 重建报告时断言 `report.meta.strategy_execution.source` 和嵌套策略项属性可用。
- 跨层：历史报告、通知、Markdown、Web 实时/历史展示使用同一名称、来源和状态语义。
- 重新分析：历史有效策略默认复用，首页明确选择覆盖，旧报告走当前默认。

## 7. Wrong vs Correct

### Wrong

```python
meta = ReportMeta(...)
meta.strategy_execution = localize_strategy_execution(raw_value, language)

# worker 启动时重新读取默认值，导致已排队任务漂移
state = resolve_skill_prompt_state(get_config(), skills=task.skills)
```

### Correct

```python
localized = localize_strategy_execution(raw_value, language)
if localized is not None:
    meta.strategy_execution = StrategyExecution.model_validate(localized)

# 入队时冻结，执行时透传同一状态
task.skill_prompt_state = copy.deepcopy(resolve_skill_prompt_state(get_config(), skills=task.skills))
pipeline = StockAnalysisPipeline(skill_prompt_state=task.skill_prompt_state)
```
