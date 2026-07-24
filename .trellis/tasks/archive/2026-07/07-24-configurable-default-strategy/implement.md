# 实施计划：可配置默认分析策略

## 1. 后端配置与统一解析

- [x] 在 `src/config.py` 增加 `default_analysis_skill`，读取 `DEFAULT_ANALYSIS_SKILL`。
- [x] 在 `src/core/config_registry.py` 注册 Agent 分类单值配置，并在 `.env.example` 添加说明和优先级示例。
- [x] 在策略解析层实现“请求 > 保存默认 > AGENT_SKILLS > 内置默认”的单一 resolver，复用到 factory、技能列表 API、pipeline 与 router。
- [x] 保持 `strategy_execution` 的 `config/default/fallback` 来源与 invalid/partial 状态准确，不扩展历史 schema。
- [x] 在系统配置校验中拒绝不可调用的非空默认 ID，并动态提供当前策略下拉选项。
- [x] 确认配置热重载会刷新 SkillManager 相关缓存。

## 2. 分析入口与 API

- [x] 调整 `src/core/pipeline.py`：固定默认可触发 Agent，但不得伪装成请求参数；任务启动后锁定解析结果。
- [x] 调整多 Agent `SkillRouter`：有效保存默认优先于自动行情路由，清除覆盖后保持旧行为。
- [x] 扩展 `/api/v1/agent/skills` 及 legacy `/strategies` 的默认值、来源、保存值和警告字段。
- [x] 覆盖明确请求、显式空列表、有效/无效保存值、`AGENT_SKILLS`、内置默认和 `all` 的兼容测试。

## 3. Web 设置页与首页

- [x] 扩展前端 `SkillsResponse` 类型和策略 API，复用系统配置版本化保存默认值。
- [x] 设置页渲染动态单选策略及“跟随系统默认”，继续走现有草稿/保存/冲突流程。
- [x] 首页加载有效默认并显示默认标记；普通选择与“设为默认”保持独立。
- [x] 首页保存成功后以后端响应刷新状态；处理保存中、400 校验、409 冲突和普通网络错误。
- [x] 调整首页请求参数：仅用户明确操作时发送 `skills`，保留历史重新分析覆盖语义。
- [x] 调整 Chat 默认选择语义：页面初始化不伪造显式请求，用户操作和快捷问题仍显式发送。
- [x] 补齐中英用户可见文案、tooltip 和移动端布局（当前 Web UI 仅支持 `zh/en`）。

## 4. 文档与变更记录

- [x] 更新 Agent/策略配置专题文档，说明配置入口、优先级、失效回退和恢复方式。
- [x] 更新 `docs/CHANGELOG.md` 的 `[Unreleased]` 扁平条目。
- [x] 同步更新中英文完整指南。
- [x] 已完成首页桌面/移动端与设置页本地截图验收；PR 阶段仍需把截图放在 PR 描述中，不提交临时图片。

## 5. 验证

- [x] Python 语法检查：`python -m py_compile` 覆盖所有改动 Python 文件。
- [x] 后端定向测试：`tests/test_agent_pipeline.py`、`tests/test_strategy_execution.py`、`tests/test_agent_models_api.py`、系统配置相关测试、pipeline 定向用例。
- [x] 前端定向测试：HomePage、ChatPage、SettingsPage、agent/systemConfig API 测试。
- [x] 前端最终检查：`cd apps/dsa-web && npm run lint && npm run build`。
- [x] 手工和组件级验证移动端/桌面端菜单无重叠，默认标记、保存反馈和恢复入口可见且可操作。
- [x] 未执行完整 `./scripts/ci_gate.sh`；交付时列出 GitHub CI 仍需覆盖的完整门禁风险。

## 6. 回滚点

- [x] 若统一 resolver 引发回归，先恢复原 factory/pipeline/router 读取顺序，保留无效的可选配置键不会影响旧版本。
- [x] 若首页快捷保存不稳定，可先隐藏快捷入口，设置页配置与后端解析可独立保留。
- [x] 无数据库迁移；回滚时删除或清空 `.env` 中 `DEFAULT_ANALYSIS_SKILL` 即可恢复旧行为。
