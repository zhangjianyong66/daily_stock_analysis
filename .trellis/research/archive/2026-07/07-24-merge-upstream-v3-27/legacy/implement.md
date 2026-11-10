# 实施计划

## 阶段 0：进入实施前的审查门

1. 用户审阅 `prd.md`、`design.md`、`implement.md`，明确批准进入实施；批准不等于批准推送。
2. 确认工作区仅有本任务规划文件等已知未跟踪内容，没有用户代码改动。
3. 校验目标提交：`b36c721415560e48115ad4444d5af2125fc53f5c`，禁止使用上游浮动 `main`。

## 阶段 1：建立可回滚集成点

1. 刷新上游标签引用并核对目标 SHA。
2. 从当前 `main` 创建 `integrate/upstream-v3.27`。
3. 创建本地备份分支指向 `0fa4a41`，记录当前 HEAD、共同祖先和目标 SHA。
4. 执行 `git merge --no-ff --no-commit b36c721`，先停在未提交状态，便于审查合并结果。

## 阶段 2：解决冲突与语义重叠

1. 只对 3 个已知直接冲突执行三方语义合并：`uiText.ts`、`HomePage.tsx`、`system_config_service.py`。
2. 按 `design.md` 的能力清单保留本地有效行为，并接入上游新增契约。
3. 审查 36 个共同修改文件，重点覆盖 API/Schema、Agent、配置、搜索、报告、Web 状态和 Docker 映射。
4. 使用 `git diff --check`，搜索冲突标记，确认所有冲突已暂存且没有意外删除本地能力。

## 阶段 3：定向验证

1. 对本次合并涉及的 Python 文件执行 `python3 -m py_compile`。
2. 运行后端受影响测试，至少覆盖 Agent/多策略、决策信号、市场结构、Futu、配置/系统配置、历史/报告、通知、搜索、数据源和打包相关测试；以仓库实际存在的测试文件为准生成最终命令。
3. 在 `apps/dsa-web` 运行受影响 Vitest 测试、`npm run lint` 和 `npm run build`，覆盖首页、决策信号、系统设置、Agent 状态、报告卡片、API 类型和状态 store。
4. 执行 `docker compose -f docker/docker-compose.yml config --quiet`；不输出包含真实密钥的完整 Compose 渲染结果。
5. 对关键 API Schema、报告 JSON/Markdown、DecisionSignal、首页工作区和本地搜索/实时行情护栏做合并前后差异复核。
6. 记录每项测试命令、通过/失败结果、环境限制和未覆盖风险；不把定向验证描述为全量门禁。

## 阶段 4：形成合并提交并暂停交付

1. 只有冲突解决和定向验证通过后，才提交合并，提交信息使用中文 Conventional Commits 风格，例如 `chore(merge): 合并上游 v3.27.0 并保留本地能力`。
2. 记录合并提交 SHA、父提交、目标上游 SHA、测试证据和回滚点。
3. 在集成分支停止，等待用户审阅；不自动合入 `main`、不执行 `git push`、不部署。
4. 用户另行批准后，再规划将集成分支合入 `main` 及远端 CI 的独立步骤。

## 失败处理与回滚点

- 阶段 1 合并未提交：`git merge --abort`。
- 阶段 2 发现语义无法收敛：保留冲突现场和诊断记录，不强行使用 `ours/theirs`，由用户决定缩小范围或回退。
- 阶段 3 测试失败：不提交合并，修复后重跑失败用例及其上下游回归。
- 合并提交后但尚未进入 `main`：回到 `main`，保留集成分支继续修复或删除；不触碰 `origin/main`。
- 已进入共享分支后的回滚：使用显式 revert，不重写共享历史。

## 实施记录（2026-07-24）

- 已从 `0fa4a415694caabb6eaf6ce4ed32a6148e2ab364` 创建 `integrate/upstream-v3.27`。
- 已创建本地备份分支 `backup/pre-upstream-v3.27-0fa4a41`。
- 已校验并合并上游 `v3.27.0` 的精确提交 `b36c721415560e48115ad4444d5af2125fc53f5c`，未吸收标签后的上游 `main` 提交。
- 3 个直接冲突均按功能并存处理：
  - `uiText.ts` 同时保留本地排序、置顶、删除文案和上游首页工作区文案。
  - `HomePage.tsx` 同时保留本地配置批量分析与上游历史/今日/自选工作区。
  - `system_config_service.py` 同时保留 Vision Responses 能力与 Agent backend 状态检测。
- 语义审查修复两项自动合并问题：合并重复 `orjson` 依赖；恢复 SQLite 决策风格迁移的安全失败顺序。
- 主要验证：Python 语法检查、后端受影响回归 `1889 passed`、实时行情/ETF `213 passed`、搜索 `225 passed / 2 skipped`、Vision/持仓 `194 passed`、Web 定向 `90 passed`、Web lint/build、Compose config、AI 治理校验。
- Web 全量测试为 `1080 passed / 2 skipped / 3 failed`；3 个失败文件相对合并前 HEAD 无差异，属于既有 UI 治理、告警市场选项和选股轮询测试问题，本次不扩大范围修复。
