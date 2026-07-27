# 升级 Trellis 至 0.6.9 并提交

## Goal

将仓库内 Trellis 管理资产从 0.6.6 升级到当前最新版本 0.6.9，确认升级结果可用，并形成一笔边界清晰、可回滚的中文 Git 提交。

## Background

- 本机 Trellis CLI 版本和 npm 最新版本均为 0.6.9。
- 当前工作树已有一组尚未提交的 Trellis 升级改动，`.trellis/.version` 已更新为 0.6.9。
- `trellis update --dry-run` 仅将 `.trellis/scripts/common/__init__.py` 标记为本地修改；该文件不是当前 Git diff 的一部分，升级时不得强制覆盖其项目定制。
- 仓库当前还有两个既有业务任务处于 `in_progress`，本次升级不得修改或归档它们。

## Requirements

- 保留 `.trellis/tasks/`、`.trellis/workspace/`、`.trellis/spec/` 和已有本地定制，不使用 `trellis update --force` 覆盖冲突文件。
- 升级提交只包含 Trellis 0.6.9 管理资产、本任务记录及升级直接要求的治理文件。
- 执行 Trellis 自检和仓库 AI 协作资产校验，失败时先修正升级问题再提交。
- 提交信息使用 Conventional Commits 格式和中文描述，不添加 `Co-Authored-By`。
- 不执行 `git push`。

## Acceptance Criteria

- [ ] `.trellis/.version` 为 `0.6.9`，且 `trellis update --dry-run` 显示项目版本、CLI 版本和 npm 最新版本一致。
- [ ] 升级过程中没有强制覆盖本地修改；没有产生未处理的 `.new` 文件或迁移残留。
- [ ] `python scripts/check_ai_assets.py` 通过。
- [ ] Trellis 任务脚本和上下文脚本的定向检查通过。
- [ ] Git 提交只包含本次 Trellis 升级相关内容，提交信息为中文。
- [ ] 提交完成后工作树无本次升级遗留；不推送远端。

## Out of Scope

- 不处理或归档 `07-23-rollback-short-swing-rules`、`07-24-report-effective-strategy` 两个既有业务任务。
- 不修改产品功能、业务代码、部署配置或用户数据。
- 不升级到 0.6.9 之后的预发布或未发布版本。
- 不执行远端推送。
