# 修复 Docker 构建阶段 alphasift 导入失败

## Goal

修复 Docker 后端镜像构建在运行时导入校验阶段失败的问题，使镜像校验与当前仓库内置的选股实现保持一致。

## Background

- `src/services/screening/` 已包含基于 AlphaSift 衍生的本地实现，正常运行不依赖外部 `alphasift` Python 包。
- `requirements.txt` 没有安装 `alphasift`，因此 Dockerfile 中 `import alphasift.dsa_adapter` 在干净镜像内必然失败。
- 现有回归测试要求 Dockerfile 校验 `src.services.screening.pipeline`，并禁止重新依赖外部 AlphaSift 安装包。

## Requirements

1. 将 Docker 构建阶段的选股运行时导入校验改为检查仓库内置模块。
2. 保留对 `orjson` 和 Futu SDK 的构建期导入校验。
3. 不新增外部 AlphaSift 依赖，不改变应用运行时选股逻辑。

## Acceptance Criteria

- [x] `docker/Dockerfile` 不再执行 `import alphasift.dsa_adapter`，而是校验 `src.services.screening.pipeline`。
- [x] 相关内置选股回归测试通过。
- [x] 修改后的 Dockerfile 语法和变更涉及的 Python 模块可通过本地静态验证；完整 Docker 构建因 Debian 依赖下载过慢中止，交付时明确说明。

## Out of Scope

- 不恢复或安装外部 `alphasift` 包。
- 不调整选股 API、策略文件、配置项或前端行为。
