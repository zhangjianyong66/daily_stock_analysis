# 规划合并上游 v3.27.0

## Goal

制定一套可执行、可验证、可回滚的集成方案，将原始上游 `ZhuLinsen/daily_stock_analysis` 的目标版本合入当前定制分叉，同时保留经确认仍需要的本地能力。

本阶段只做需求澄清和方案设计，不执行合并、切换分支、提交或推送。

## Background

- 当前本地 `main` 与个人远端 `origin/main` 均位于 `0fa4a41`，检查时工作区干净。
- 原始上游为 `ZhuLinsen/daily_stock_analysis`。
- 双方共同基线为 `bfdee032`（2026-07-07）。
- 相对共同基线，本地独有 102 个提交；上游正式 `v3.27.0` 独有 24 个提交。
- 正式 `v3.27.0` 标签指向 `b36c721`（2026-07-19）。上游 `main` 当前位于 `aa68d45`，比正式标签多 11 个尚未进入新正式版本的提交。
- 只读模拟将正式 `v3.27.0` 合入当前本地 HEAD 时，发现 36 个双方共同修改的文件，以及 3 个直接内容冲突：
  - `apps/dsa-web/src/i18n/uiText.ts`
  - `apps/dsa-web/src/pages/HomePage.tsx`
  - `src/services/system_config_service.py`
- 若集成上游当前 `main`，还会增加 `docker/Dockerfile` 冲突，直接冲突合计 4 个。

## Requirements

- 目标固定为正式 `v3.27.0` 标签解引用后的提交 `b36c721`；不包含该标签之后的 11 个上游 `main` 提交。
- 必须逐项判定本地定制能力的保留、替换、重做或放弃策略，不能仅按文本冲突数量决定结果。
- 默认保留当前本地所有仍有效的用户可见能力、稳定性修复和部署约定；只有上游完整替代同一问题、本地实现已明确废弃，或两者无法共存且上游方案验证更充分时，才允许替换。
- 使用独立集成分支承载一次 `--no-ff` 合并提交，不重写当前 `main` 的 102 个本地提交。
- 3 个已知冲突文件采用三方语义合并，逐项保留两侧仍有效的行为：`apps/dsa-web/src/i18n/uiText.ts`、`apps/dsa-web/src/pages/HomePage.tsx`、`src/services/system_config_service.py`。
- 必须在独立集成分支完成工作，不直接修改当前 `main`。
- 必须保留可追溯的合并基线、冲突决策、验证证据和回滚点。
- 本地验证采用受影响范围的完整回归，GitHub CI 再执行全量门禁；不把本机一次完整 `ci_gate.sh` 作为合并前置条件。
- 合并和验证完成后先停在集成分支，不自动推进当前 `main`，不自动推送 `origin/main`。
- 未经用户明确确认，不执行真实合并、提交或推送。

## Acceptance Criteria

- [x] 目标上游提交已精确锁定为 `b36c721`，不使用会继续漂移的模糊引用。
- [x] 所有本地独有能力都有明确处置结论，并遵循“有效能力默认保留”原则。
- [x] 直接冲突与无文本冲突但存在语义重叠的区域均有处理方案，并完成对应回归。
- [x] 形成分阶段执行顺序、定向验证矩阵、完整回滚方案。
- [x] 已确定使用集成分支承载结果；验证通过后暂停，等待用户另行批准合入 `main` 或推送。
- [x] 用户审阅并明确批准最终规划后，才允许进入实施阶段。

## Out of Scope

- 规划阶段不执行真实 merge、rebase、cherry-pick、commit、push 或部署。
- 不吸收 `b36c721` 之后的新功能或修复；如未来需要，另行规划增量升级。

## Open Questions

- 无。目标、保留原则、历史整合、冲突处理、验证门槛和交付边界均已确认。

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
