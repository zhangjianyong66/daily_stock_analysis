# 修复 Vision Responses 缺少 orjson 依赖

## Goal

确保从 `requirements.txt` 构建的干净 Docker 镜像能够执行 LiteLLM Responses Vision 调用，不再因为缺少 `orjson` 导致所有图片在请求上游前失败。

## Confirmed Facts

- 2026-07-15 21:00 的持仓图片任务已正常创建，但 LiteLLM 在第一次 Vision 调用时抛出 `OpenAIException - No module named 'orjson'`。
- 运行时 `VISION_MODEL=openai/gpt-5.6-sol`、`VISION_API_MODE=responses`，精确渠道、API Key 和 `User-Agent` 均已正确加载。
- 当前 Docker 镜像安装 LiteLLM `1.92.0`，未安装 `orjson`；`requirements.txt` 允许 LiteLLM 小版本升级但没有显式声明该运行时依赖。
- 之前成功的在线 smoke 使用本地 `.venv` 中的 LiteLLM `1.91.1`，没有覆盖当前干净 Docker 依赖组合。

## Requirements

- R1：在项目依赖真源中显式声明 `orjson`，使本地、Docker 和 CI 安装结果一致。
- R2：Docker 构建阶段必须验证 `orjson` 可导入，避免仅靠业务运行时才发现缺依赖。
- R3：不修改 Vision 协议、模型、渠道、重试、图片数据或任务状态契约。
- R4：同步更新 `[Unreleased]` changelog，并把 LiteLLM Responses 的 Docker 依赖约定记录到项目 `AGENTS.md`。
- R5：完成依赖解析检查、相关定向测试和 Docker 镜像构建/运行验证；不得把真实图片、Key 或 provider 响应写入测试或日志。

## Acceptance Criteria

- [x] AC1：全新安装 `requirements.txt` 后 `python -c "import orjson"` 成功。
- [x] AC2：`docker/Dockerfile` 在镜像构建阶段验证 `orjson` 导入，缺依赖时构建直接失败。
- [x] AC3：Vision 与持仓图片导入相关离线回归测试通过。
- [x] AC4：重新构建的 `stock-server` 镜像包含 `orjson`，容器内 LiteLLM Responses 路径不再出现 `No module named 'orjson'`。
- [x] AC5：文档记录与实际依赖、构建方式一致。

## Out of Scope

- 不调整或锁死当前 Vision 模型和中转站配置。
- 不更改 LiteLLM Responses 请求结构或错误映射。
- 不提交、不推送代码。
