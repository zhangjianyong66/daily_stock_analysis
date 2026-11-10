# 技术设计：可配置默认分析策略

## 1. 设计目标

新增 `DEFAULT_ANALYSIS_SKILL` 单值配置，并把“默认策略解析”收敛为一个后端事实源。页面只展示和修改该事实，不在浏览器本地保存默认值，也不自行推断回退结果。

核心约束：

- 单次显式请求永远优先。
- 保存覆盖失效时 fail-open，继续使用下一级默认并暴露警告。
- 默认值只在任务创建/执行上下文建立时解析一次，执行中不随配置热更新漂移。
- `strategy_execution` 继续是历史和报告的唯一事实源。

## 2. 配置与解析模型

### 2.1 配置字段

- `Config.default_analysis_skill: str = ""`
- 环境变量：`DEFAULT_ANALYSIS_SKILL`
- 空值表示“跟随系统默认”，不保存特殊哨兵字符串。
- `src/core/config_registry.py` 将其注册到 `agent` 分类，单值、可编辑、非敏感。

系统配置服务在返回 Web schema 时，用当前 `SkillManager` 动态补充下拉选项：第一项为空值“跟随系统默认”，其余为当前 `user_invocable=true` 的内置及自定义策略。注册表本身不静态复制策略目录，避免策略列表漂移。

### 2.2 统一解析结果

在 `src/agent/factory.py`（或相邻的策略解析模块）增加可复用解析结构，输入为：

- 单次 `requested_skills`（`None` 与显式空列表保持现有区别）；
- `config.default_analysis_skill`；
- `config.agent_skills`；
- 当前可调用策略目录与内置默认策略。

输出至少包含：

- `effective_ids`：本次最终候选；
- `source`：`request` / `config` / `default` / `fallback`；
- `explicit_request`：用户是否提供了有效的单次选择；
- `configured_override`：保存的单值覆盖；
- `rejected_ids` 与失效原因；
- `status` / `message`：用于构造 `strategy_execution`。

解析顺序：

1. 单次请求包含有效策略：使用有效请求项；混有无效项时记录 `partial`。
2. 单次请求为空或全部无效：尝试有效的 `DEFAULT_ANALYSIS_SKILL`。
3. 保存覆盖为空或失效：尝试 `AGENT_SKILLS` 的现有有效配置。
4. 仍无有效项：使用策略元数据主默认。

无效高优先级值必须进入 `rejected`，最终快照使用 `fallback`，但不得把配置回退伪装成用户请求。有效保存覆盖和有效 `AGENT_SKILLS` 均使用 `source=config`；纯内置回退使用 `source=default`。

## 3. 运行入口

### 3.1 普通分析与定时任务

`src/core/pipeline.py` 不再自行把 `config.agent_skills` 塞成“请求策略”，而是：

- 只有 API/调用方明确传入时才设置 `analysis_skills` 和上下文 `skills`；
- 使用统一解析结果判断是否因固定配置自动启用 Agent pipeline；
- Executor/Analyzer 在任务上下文建立时解析并保存快照，后续配置热更新不改写该任务。

保存了 `DEFAULT_ANALYSIS_SKILL` 时，其行为与当前固定 `AGENT_SKILLS` 一致：非 `all` 策略可触发 Agent pipeline。未保存覆盖时保持现有 Agent 自动启用条件。

### 3.2 多 Agent 路由

`SkillRouter` 的顺序调整为：用户请求 > 有效保存默认覆盖 > 现有 manual/auto 路由。这样保存默认存在时是固定策略，不会被行情识别替换；清除覆盖后自动路由恢复原行为。

Router 使用统一解析 helper 或由 factory 注入的已解析配置，禁止再单独实现一套 ID 校验与回退逻辑。

### 3.3 Agent 问股

Chat 页面可以视觉选中有效默认策略，但需要维护“用户是否操作过策略”的状态：

- 未操作时省略 `skills`，由后端使用配置默认；
- 用户勾选、清空或快捷问题指定策略时，按现有显式请求发送；
- 因页面初始化自动选中的默认策略不记录为 `source=request`。

## 4. API 契约

扩展 `/api/v1/agent/skills`，保留现有字段并追加：

```json
{
  "skills": [],
  "default_skill_id": "chan_theory",
  "default_skill_source": "saved|agent_skills|builtin|fallback",
  "saved_default_skill_id": "chan_theory",
  "default_skill_warning": null
}
```

- `default_skill_id` 改为当前有效单一默认 ID；旧客户端继续读取该字段。
- `saved_default_skill_id` 为空表示跟随系统默认；若保存值已失效，保留原值供设置页解释。
- `default_skill_warning` 仅在保存值失效或回退时返回，不包含敏感配置。
- legacy `/agent/strategies` 继续返回旧字段，并可追加等价兼容元数据，不删除现有 payload。

首页快捷保存复用现有系统配置 API：先读取 `config_version`，再更新单个 `DEFAULT_ANALYSIS_SKILL`，沿用 400 校验和 409 版本冲突。成功后重新读取策略列表，不做只改本地状态的乐观伪成功。

## 5. 设置页与首页交互

### 5.1 设置页

- `SystemConfigService.get_config()` 对 `DEFAULT_ANALYSIS_SKILL` schema 动态注入策略选项，现有 `SettingsField` select 直接渲染。
- 服务端在 `_collect_issues()` 的跨字段校验中加载候选 `AGENT_SKILL_DIR` 对应目录，非空值不在可调用列表时返回字段级 error。
- 配置保存后沿用 `Config.reset_instance()` 和 runtime singleton reload；同时清理/刷新 SkillManager prototype，保证自定义目录或默认策略即时生效。

### 5.2 首页菜单

- `selectedStrategyId` 负责当前视觉/单次选择；另存有效默认 ID、保存覆盖和保存状态。
- 初始化用 API 有效默认值设置视觉选择，但保持 `strategySelectionTouched=false`。
- 计算请求参数时仅在 `strategySelectionTouched=true` 时发送 `skills`。
- 每个策略项提供 Star 类图标按钮和 tooltip；当前默认显示非交互“默认”状态，避免文字按钮挤压移动端菜单。
- “跟随系统默认”用于写入空值；普通点击该行只切换本次分析到隐式默认，不直接保存。
- 保存中禁用重复操作；成功后重新拉取后端状态并显示 toast，失败时显示解析后的 API 错误。

## 6. 兼容与迁移

- 新配置默认空值，因此升级后行为不变。
- `AGENT_SKILLS` 继续支持多值及 `all`；它只在没有有效保存覆盖时参与默认解析。
- API 只追加字段，旧 Web/Desktop 客户端可忽略。
- `strategy_execution` schema 不新增枚举；保存默认和 `AGENT_SKILLS` 都复用 `source=config`，失效回退复用 `source=fallback`。
- 历史报告只读其持久化快照；重新分析仍按“历史有效策略优先，首页明确操作可覆盖”的现有规则。
- 大盘复盘请求和 `src/core/market_strategy.py` 不接入新配置。

## 7. 风险与回滚

- 风险：多处入口自行读取配置导致优先级漂移。控制方式是公共解析 helper + 入口契约测试。
- 风险：运行时保存后 SkillManager 缓存未失效。配置 reload 必须覆盖策略目录和默认解析测试。
- 风险：页面自动选中默认后误发显式请求。前端测试断言未操作时 payload 不含 `skills`。
- 风险：`AGENT_SKILLS=all` 与单一默认语义冲突。保存覆盖优先；清除覆盖后完全恢复旧行为。
- 回滚时可移除 Web 入口和新配置读取；由于配置是可选 `.env` 键且 API 只追加字段，无数据库迁移，旧版本会忽略该键。
