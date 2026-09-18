# 上游合并后回归修复与验收

## Goal

在保留本地 ETF、搜索审计、Vision、策略和部署定制的前提下，完成 `upstream/main` 合并后的回归修复与验收，使本地 `main` 达到可继续开发、可验证回滚的状态。

## Requirements

- 修复合并后后端模块的导入、API Schema、任务队列、指数注册表和配置契约不一致。
- 保留本地既有功能：ETF 资金流与实时行情 fallback、搜索审计与额度告警、Vision 截图导入、策略执行快照和自动匹配。
- 接入并验证上游新增能力：指数入口、Futu OpenD、数据能力 API、ResearchArtifact、Screening、分享图和调度超时部分通知。
- 修复或明确测试替身与新增 API 字段（如资产类型、市场区域、报告语言）之间的兼容边界。
- 完成受影响后端测试、前端 lint/build，并记录未覆盖的网络、Docker 和外部服务风险。
- 保留 `backup/local-main-before-upstream-20260918` 作为回滚点；不自动推送远程。

## Confirmed Baseline

- `main` 已包含合并提交 `0838d366`，该提交同时有本地历史和 `upstream/main` 父线；当前 `main` 与 `upstream/main` 无差异。
- 当前工作区没有冲突标记，唯一未跟踪内容是本任务目录；当前分支相对 `origin/main` 尚未推送。
- 合并期间已经补回配置、存储、指数加载、分析服务、策略 ID 和 Screening 等基础兼容层；剩余风险集中在分析 API 测试替身/新增字段、跨层契约和未执行的前端/部署验证。
- 现有分析 API 定向测试仍有失败，已知类别包括旧测试替身缺少 `region` / `report_language`、市场复盘与任务队列 patch 入口变化；这些失败必须逐项归因，不能以跳过测试代替修复。

## Acceptance Criteria

- [x] 工作区无 Git 冲突标记，合并提交可追溯到本地父提交和 `upstream/main`。
- [x] 关键 Python 模块可导入并通过语法检查。
- [x] 分析 API、系统配置、存储、数据源、搜索、ETF、Vision 和策略相关定向测试通过；指数路由沿用合并后的导入/契约检查。
- [x] Web 前端 `npm run lint` 与 `npm run build` 已完成；lint 保留 2 个既有 Hook warning。
- [x] 合并后的新增 API/配置/依赖契约已通过代码导入和定向测试核对；未新增配置项。
- [x] 回滚命令和当前未推送状态在任务记录中明确。

## Verification Record

- 后端定向回归：337 passed（分析 API、系统配置、存储、基本面、ETF 资金流/搜索、搜索并发与新鲜度、Vision 任务、策略自动匹配）。
- Python 编译和 `git diff --check`：通过。
- Web `npm run lint`：通过，存在 2 个 `react-hooks/exhaustive-deps` warning，无 error。
- Web `npm run build`：通过。补齐新增中英文 i18n 键、`LLMChannelEditor` 的可选 `modelProviderPrefixes` 和 `MarketReviewAccepted.region` 的旧客户端兼容。
- Docker Compose `config --quiet`：通过；未执行镜像构建、在线搜索供应商、网络 smoke 和 Desktop 构建，保留为外部环境风险。
- Trellis quality check：通过；清理了本轮明确未使用导入。Flake8 仍受仓库既有格式噪声（W293、历史缩进等）影响，本轮未进行大面积格式化。

## Out Of Scope

- 不重新设计上游功能，不回滚或重写本地 ETF、搜索审计、Vision、策略和 Docker 定制。
- 不执行 `git push`、`git tag` 或需要管理员权限的部署操作。
- 不以不稳定的在线供应商调用替代离线契约测试；网络、Docker daemon、外部 API 不可用时记录风险和替代证据。

## Decision Status

- 用户目标、保留范围、合并策略和不推送约束已确认。
- 剩余执行决策采用保守兼容策略：上游新增字段优先可选读取；失败测试按真实根因修复；无法在本任务内稳定收敛的模块保留明确回滚点和后续记录。
- 当前实现与质量检查已完成；未执行提交、推送或标签，代码提交仍需用户明确授权。

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
