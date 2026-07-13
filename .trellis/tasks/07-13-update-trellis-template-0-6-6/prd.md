# 更新 Trellis 模板以适配 0.6.6

## Goal

将当前项目的 Trellis 模板从 0.6.5 安全更新到当前最新稳定版 0.6.6，使项目生成文件与已安装 CLI 保持一致，同时保留项目数据和有价值的本地定制。

## Background

- 本机 `trellis --version` 与 npm `latest` 均为 0.6.6，项目模板版本为 0.6.5。
- `trellis update --dry-run` 确认本次升级会新增 Claude 平台集成文件、自动更新 17 个未被本地修改的受管文件。
- 以下两个受管文件被 CLI 标记为本地修改，但与 0.6.6 上游对比后确认只有空白格式差异，不包含项目语义定制：
  - `.agents/skills/trellis-channel/references/command-reference.md`
  - `.agents/skills/trellis-meta/references/local-architecture/workspace-memory.md`
- `.trellis/workspace/`、`.trellis/tasks/`、`.trellis/spec/` 和 `.trellis/.developer/` 被 CLI 识别为用户数据，升级会保留。

## Requirements

- 使用 Trellis 官方更新机制处理受管模板，不直接修改全局 npm 安装目录或 `node_modules`。
- 采用完整 0.6.6 受管模板面，包括新增的 Claude 平台集成。
- 两个仅含空白格式差异的冲突文件采用 0.6.6 上游版本，避免继续产生无意义冲突。
- 使用官方 `trellis update --force --migrate` 完成升级，并在更新后全量审查 Git diff。
- 不覆盖任务、规范、开发者日志等用户数据。
- 更新后项目版本状态不得继续提示 0.6.5 -> 0.6.6。
- 遵循仓库 AI 协作资产治理约束，不引入与 `AGENTS.md` 冲突的项目规则真源。
- 本次只完成 0.6.6 模板升级，不新增 CI 或脚本形式的版本防漂移机制。
- 目标版本固定为 0.6.6；若执行前 npm 发布更高版本，不在本任务中追随升级。

## Acceptance Criteria

- [x] `trellis update --dry-run` 不再报告项目模板版本落后于 0.6.6。
- [x] 0.6.6 要求的选定平台模板文件均已生成或更新，无未处理的 `.new` 冲突副本。
- [x] 两个本地修改文件已采用 0.6.6 上游版本，且无项目语义内容丢失。
- [x] `.trellis/workspace/`、`.trellis/tasks/`、`.trellis/spec/` 和 `.trellis/.developer/` 内容未被升级流程破坏。
- [x] `python scripts/check_ai_assets.py` 通过。
- [x] Trellis 会话上下文与任务命令能够正常读取当前任务和工作流阶段。

## Out Of Scope

- 升级全局 Trellis CLI；本机已是 0.6.6。
- 修改 Trellis 上游源码或发布 npm 包。
- 借升级之机重构与版本适配无关的项目规范。
- 新增 Trellis 模板版本漂移的 CI 阻断或定时检查。
