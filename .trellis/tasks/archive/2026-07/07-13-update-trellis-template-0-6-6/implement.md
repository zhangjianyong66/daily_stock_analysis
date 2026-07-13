# Trellis 0.6.6 模板升级实施计划

> **Codex inline 执行要求：** 实现前必须加载 `trellis-before-dev`，由主会话逐项执行和检查；不得分派实现或检查子代理。

**目标：** 使用官方 Trellis 0.6.6 更新器完整升级项目受管模板，并证明项目数据、项目规则和工作流仍然完整可用。

**架构：** 将官方更新器视为唯一模板写入方，以 dry-run 作为变更清单，以 Git diff 和用户数据 SHA-256 快照作为边界审计。升级后从模板版本、上下文加载、治理检查、Python 语法和文件完整性五个层面验证。

**技术栈：** Trellis CLI 0.6.6、Python 3、Git、SHA-256。

---

### 任务 1：执行前基线与数据快照

**文件：**

- 读取：`.trellis/.template-hashes.json`
- 读取：`.trellis/workspace/`
- 读取：`.trellis/tasks/`
- 读取：`.trellis/spec/`
- 读取：`.trellis/.developer/`

- [x] **步骤 1：加载实现规范**

运行 `trellis-before-dev`，读取本任务的 `prd.md`、`design.md`、`implement.md` 以及适用的项目规范。预期：任务状态为 `in_progress`，没有要求使用子代理。

- [x] **步骤 2：确认固定版本**

运行：

```bash
trellis --version
```

预期：输出 `0.6.6`。若不是 0.6.6，停止执行，不自动升级或降级全局 CLI。

- [x] **步骤 3：复核官方更新清单**

运行：

```bash
trellis update --dry-run
```

预期：显示项目从 0.6.5 升级到 0.6.6；新增 Claude 集成、自动更新受管文件，并仅将已分析的两个文件列为用户修改冲突。若出现新的用户修改冲突，返回规划阶段分析，不使用 `--force`。

- [x] **步骤 4：记录用户数据快照**

在执行工具进程内，对以下路径的全部普通文件按规范化路径排序，并记录路径与 SHA-256：

```text
.trellis/workspace/
.trellis/tasks/
.trellis/spec/
.trellis/.developer/
```

预期：获得可与更新后结果逐项比较的内存快照，不在仓库内创建临时文件。

### 任务 2：应用官方 0.6.6 模板

**文件：**

- 修改：`.trellis/.template-hashes.json`
- 修改：dry-run 列出的 Trellis 受管文件
- 新增：dry-run 列出的 Claude 平台集成文件

- [x] **步骤 1：执行确定性升级**

运行：

```bash
trellis update --force --migrate
```

预期：命令成功，将项目版本从 0.6.5 更新为 0.6.6；迁移步骤只跳过不存在的旧 ZCode 目录，不修改用户数据。

- [x] **步骤 2：立即核对用户数据**

使用与任务 1 步骤 4 完全相同的路径排序和 SHA-256 规则重新计算快照，并逐项比较。

预期：文件集合与全部 SHA-256 完全一致。若不一致，停止并按 `design.md` 的回滚边界处理，不继续验证或提交。

- [x] **步骤 3：审查工作区边界**

运行：

```bash
git status --short
git diff --stat
git diff -- .trellis .agents .codex .claude
rg --files -g '*.new' .trellis .agents .codex .claude
```

预期：除本任务文档外，改动仅包含 dry-run 声明的受管文件；不存在 `.new` 文件。`rg` 在没有匹配时退出码为 1，属于预期结果。

### 任务 3：验证升级后的工作流

**文件：**

- 验证：`.trellis/scripts/`
- 验证：`.codex/hooks/`
- 验证：`.claude/hooks/`
- 验证：`AGENTS.md`、`CLAUDE.md`、`.github/` 与 AI 协作资产

- [x] **步骤 1：确认模板已完全同步**

运行：

```bash
trellis update --dry-run
```

预期：项目版本与 CLI 版本均为 0.6.6，不再出现 0.6.5 -> 0.6.6 升级提示，也没有待应用模板变更。

- [x] **步骤 2：验证 Trellis 上下文读取**

运行：

```bash
python3 ./.trellis/scripts/get_context.py
python3 ./.trellis/scripts/get_context.py --mode phase
python3 ./.trellis/scripts/get_context.py --mode packages
```

预期：三个命令均成功；普通上下文识别当前任务，phase 输出当前工作流阶段，packages 输出当前单仓库与 spec layer 信息。

- [x] **步骤 3：验证 AI 协作资产治理**

运行：

```bash
python3 scripts/check_ai_assets.py
```

预期：退出码为 0，无治理错误。

- [x] **步骤 4：验证更新脚本语法**

运行：

```bash
python3 -m py_compile \
  .trellis/scripts/common/cli_adapter.py \
  .trellis/scripts/common/config.py \
  .trellis/scripts/common/task_store.py \
  .trellis/scripts/common/session_context.py \
  .trellis/scripts/task.py \
  .trellis/scripts/add_session.py \
  .codex/hooks/session-start.py \
  .codex/hooks/inject-workflow-state.py \
  .claude/hooks/inject-subagent-context.py \
  .claude/hooks/inject-workflow-state.py \
  .claude/hooks/session-start.py
```

预期：退出码为 0，无语法错误。

- [x] **步骤 5：执行最终 diff 自审**

运行：

```bash
git diff --check
git status --short
git diff --stat
```

实际结果：完整 `git diff --check` 只报告两类与 0.6.6 上游逐字节一致的 Markdown 模板及其 `.agents` / `.claude` 四个仓库副本存在空白格式；排除这四个已核验副本后退出码为 0。状态与统计只包含 0.6.6 模板升级和本任务文档，`.trellis/.template-hashes.json` 已记录 0.6.6 模板状态，没有项目规则被意外覆盖。详细依据见 `design.md` 的“实施期兼容例外”。

### 任务 4：交付与回滚准备

**文件：**

- 更新：`.trellis/tasks/07-13-update-trellis-template-0-6-6/prd.md`
- 更新：`.trellis/tasks/07-13-update-trellis-template-0-6-6/implement.md`

- [x] **步骤 1：回填验收结果**

逐项勾选 `prd.md` 的验收标准，并在实施计划中记录实际命令结果。任何未通过项必须保留为未完成并说明原因。

实施结果：

- `trellis update --dry-run`：退出码 0，项目、CLI 与 npm latest 均为 0.6.6，输出 `Already up to date!`。
- 用户数据：更新命令前后 61 个文件路径与 SHA-256 完全一致；回填任务文档后再次核对，当前任务之外的 55 个用户数据文件仍完全一致。
- `python3 scripts/check_ai_assets.py`：退出码 0，输出 `[ai-assets] OK`。
- 指定 Trellis/Codex/Claude Python 文件 `py_compile`：退出码 0。
- `./scripts/ci_gate.sh syntax`：本机直接运行因缺少 `python` 命令退出 127；通过临时 `python -> python3` 兼容入口重跑后退出码 0。
- Trellis 上下文、phase、packages 与 Codex inline 2.1 读取：均退出码 0。
- `.new` 搜索：无匹配；退出码 1 为 `rg` 的预期“未找到”结果。
- 完整 `git diff --check`：只报告 `design.md` 已记录的两类上游模板在 `.agents` / `.claude` 中的四个原样副本；排除这四个文件后退出码 0。

Spec 更新判断：本次是官方受管模板的固定版本升级，没有新增项目代码契约；上游 whitespace 与本机 Python 命令入口差异均为任务级证据，不写入长期 `.trellis/spec/`。

- [x] **步骤 2：报告交付状态**

向用户说明改动范围、升级原因、验证结果、未验证项、风险和精确回滚边界。不得自动执行 `git commit`、`git push` 或任务归档。
