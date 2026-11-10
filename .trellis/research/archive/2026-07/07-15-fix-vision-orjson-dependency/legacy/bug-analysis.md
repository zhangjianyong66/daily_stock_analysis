# Bug Analysis: LiteLLM Responses 在干净 Docker 中缺少 orjson

## 1. Root Cause Category

- **Category**：D - Test Coverage Gap；同时包含 E - Implicit Assumption。
- **Specific Cause**：此前 Responses Vision 在线 smoke 运行在已存在的本地 `.venv` 与 LiteLLM 1.91.1 上，而实际重建镜像解析到 LiteLLM 1.92.0。项目未显式声明 `orjson`，也没有在干净 Docker 构建阶段验证 Responses 运行时依赖，导致真实图片任务成为首次发现缺包的位置。

## 2. Why Fixes Failed

1. 上一次协议修复证明了 Responses 请求、渠道请求头与文本提取正确，但验证环境不是最终部署镜像，遗漏了依赖安装边界。
2. `requirements.txt` 对 LiteLLM 使用宽松的小版本范围，本地 smoke 与 Docker 重建解析到不同版本；验证记录没有把实际解析版本和干净安装纳入验收条件。
3. 单元测试使用替身验证 Router/Responses 契约，无法发现第三方包在真实导入路径中的可选依赖缺失。

## 3. Prevention Mechanisms

| Priority | Mechanism | Specific Action | Status |
| --- | --- | --- | --- |
| P0 | 依赖真源 | 在 `requirements.txt` 显式声明 `orjson>=3.10.0,<4.0.0` | DONE |
| P0 | 构建门禁 | Dockerfile 构建阶段执行 `import orjson` | DONE |
| P0 | 集成验证 | 重建实际镜像并用 32×32 空白图完成共享 Responses Vision smoke | DONE |
| P1 | 文档与规范 | 更新 `AGENTS.md` 和持仓图片导入 code-spec | DONE |
| P1 | 全库门禁 | 执行完整后端门禁和相关 Vision 定向测试 | DONE |

## 4. Systematic Expansion

- **Similar Issues**：所有依赖第三方 SDK 可选 extras、延迟导入或版本相关导入路径的能力，都可能在长期存在的开发环境中通过、在干净镜像中失败。
- **Design Improvement**：运行时关键的延迟导入包应进入项目依赖真源，并由最终镜像构建执行最小导入 smoke。
- **Process Improvement**：涉及依赖或 SDK 新调用面时，验收证据必须包含最终部署镜像中的实际包版本，而不能只引用本地虚拟环境。

## 5. Knowledge Capture

- [x] 更新 `AGENTS.md` 的 Vision/Docker 运行约定。
- [x] 更新 `.trellis/spec/backend/portfolio-image-import.md` 的依赖、错误矩阵、测试与反例契约。
- [x] 使用 Docker 构建导入检查替代仅依赖 mock 的回归证明。
- [ ] Git commit：项目规则要求用户明确确认后才能提交，本任务不自动提交。
