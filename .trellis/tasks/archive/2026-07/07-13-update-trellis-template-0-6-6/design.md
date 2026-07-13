# Trellis 0.6.6 模板升级设计

## 背景与目标

项目模板当前为 0.6.5，本机 Trellis CLI 与规划时 npm `latest` 均为 0.6.6。本次将项目受管模板完整升级到 0.6.6，消除版本提示并保持项目数据、项目规则和既有本地工作不受影响。

目标版本固定为 0.6.6。若执行前 npm 发布更高版本，本任务仍只处理 0.6.6，更高版本另行规划。

## 变更边界

升级通过项目外已安装的 0.6.6 CLI 驱动，但只修改当前仓库内的 Trellis 受管文件：

- 新增 0.6.6 完整模板要求的 Claude 平台集成文件。
- 自动更新 dry-run 识别出的 17 个未被本地修改的受管文件。
- 将两个仅存在空白格式差异的冲突文件替换为 0.6.6 上游版本：
  - `.agents/skills/trellis-channel/references/command-reference.md`
  - `.agents/skills/trellis-meta/references/local-architecture/workspace-memory.md`
- 应用 0.6.6 声明的文件迁移；当前 dry-run 仅发现一个不存在的旧 ZCode 目录，因此预期不会删除现有文件。

以下目录和文件属于用户数据，不是升级目标：

- `.trellis/workspace/`
- `.trellis/tasks/`
- `.trellis/spec/`
- `.trellis/.developer/`

本次不升级全局 CLI、不修改 Trellis 上游源码、不新增版本防漂移 CI，也不重构项目规范。

## 执行流程

1. 确认 CLI 版本仍为 0.6.6，并再次运行 dry-run 固化更新清单。
2. 在进程内记录用户数据文件的路径和 SHA-256 校验值。
3. 执行 `trellis update --force --migrate`。
4. 立即重新计算用户数据校验值并与升级前结果比较。
5. 检查 Git 状态、完整 diff 和 `.new` 残留，确认改动只来自官方模板更新和本任务规划文件。
6. 执行 Trellis 上下文、AI 资产治理、Python 语法和 diff 格式验证。

`--force` 在本设计中的适用前提是两个冲突已经逐文件与已安装的 0.6.6 模板对比，确认不存在语义差异。它不是对未知项目定制的通用覆盖策略。

## 验证契约

升级成功必须同时满足：

- `trellis update --dry-run` 显示项目已是 0.6.6，且没有待应用模板变更。
- `get_context.py` 能读取当前任务，phase 模式能读取工作流阶段。
- `python scripts/check_ai_assets.py` 通过。
- 更新涉及的 Python 脚本与 hooks 能通过 `py_compile`。
- 仓库内不存在 `.new` 残留；除两类与 0.6.6 上游逐字节一致的 Markdown 模板及其 `.agents` / `.claude` 四个仓库副本外，其余改动通过 `git diff --check`。
- 用户数据路径和 SHA-256 校验值在更新命令前后完全一致。
- Git diff 中没有与本次升级无关的文件改动。

## 回滚

若官方更新命令或任一验证失败，停止后续提交操作。根据更新前 dry-run 与更新后 Git diff，只恢复本次更新器修改的受管文件并删除本次新增的模板文件；保留当前任务文档及所有用户数据。回滚后重新运行用户数据校验与 `trellis update --dry-run`，确认项目回到可解释的 0.6.5 状态。

仓库规则要求未经明确确认不得提交或推送，因此本任务完成实现与验证后只报告工作区改动，不自动执行 Git commit 或 push。

## 实施期兼容例外

完整 `git diff --check` 会对两类上游模板的 `.agents` / `.claude` 四个仓库副本报告 whitespace warning：`command-reference.md` 的末尾空行，以及 `workspace-memory.md` 用于 Markdown 强制换行的两个尾随空格。对应内容与已安装 0.6.6 模板逐字节一致，SHA-256 分别为 `c4df3d940b...` 和 `e6427b46ab...`；本地移除这些空白会再次造成模板漂移。

因此保留上游原样内容，并使用排除这四个已证明为上游原样副本的 `git diff --check` 作为其余改动的格式门禁。排除检查退出码为 0。该例外只适用于本次固定版本升级，不扩展为仓库通用 whitespace 豁免。
