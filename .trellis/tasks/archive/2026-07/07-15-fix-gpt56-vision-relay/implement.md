# 修复 GPT-5.6 Vision 中转站调用：执行计划

## 1. Shared Vision Runtime

- [x] 在 `src/config.py` 增加 `VISION_API_MODE` 常量、解析、Config 字段和结构化校验。
- [x] 在 `src/services/vision_extraction_service.py` 增加精确 deployment 解析、Router 构造、Responses 请求与 Mapping/对象双形状文本提取。
- [x] 保持 Chat Completions legacy 路径；匹配渠道时改用 Router 复用 Extra Headers。
- [x] 关闭 Router 内部 retry/fallback，由现有最多两次 attempt 和 deadline 统一控制。
- [x] 将 deployment Key 与 Extra Header 值纳入错误脱敏；保持稳定错误码。
- [x] 扩展 `tests/test_vision_extraction_service.py` 和 `tests/test_image_stock_extractor_litellm.py`，覆盖默认兼容、Responses、缺 route fail-fast、空 output、重试和脱敏。

## 2. Config and Diagnostics

- [x] 在 `src/core/config_registry.py` 注册 `VISION_API_MODE`，同步配置帮助和 registry 测试。
- [x] 修正 Vision 配置校验，使渠道凭据满足 Key 检查，Responses 缺 route 产生可操作问题。
- [x] 扩展 `TestLLMChannelRequest`、endpoint 和 `SystemConfigService.test_llm_channel()`，接收 Extra Headers 与 Vision API mode。
- [x] 将所有渠道测试调用透传 Extra Headers；Vision capability 按模式使用 Chat Completions/Responses。
- [x] 把内置 Vision probe 升级为 32x32，并复用共享 Responses 文本提取。
- [x] 扩展 `tests/test_system_config_service.py`、配置校验/registry/API contract 测试。

## 3. Web Settings

- [x] 扩展 Web system-config types/API snake_case 映射，提交 `extra_headers` 与 `vision_api_mode`。
- [x] 让 `LLMChannelEditor` 解析、编辑、保存和回显渠道 Extra Headers。
- [x] 将 `VISION_API_MODE` 加入 RuntimeConfig、草稿变更检测、保存载荷和两段模式控件。
- [x] 连接测试与能力测试均提交 Extra Headers；Vision 能力测试提交当前模式。
- [x] 更新 API 和 `LLMChannelEditor` 定向测试，并完成桌面/390px 视口检查；可视证据不写入仓库。

## 4. Local Configuration Migration

- [x] 使用项目 `ConfigManager` 原子迁移现有中转站 Key/Base URL 到 `LLM_TUDOU_*`，避免在命令或补丁输出中暴露 Key。
- [x] 设置 `LLM_CHANNELS=deepseek,tudou`、Extra Headers、`VISION_API_MODE=responses`，清理重复 legacy `OPENAI_*`。
- [x] 验证配置加载后主模型仍为 DeepSeek、Vision route 精确匹配且 Key 只保留一份。
- [x] 不重建、不重启、不操作当前 `stock-server` 生命周期。

## 5. Docs and Specs

- [x] 更新 `.env.example`、中英文 LLM 配置指南、full guide 与 `[Unreleased]` 扁平 changelog。
- [x] 更新 `AGENTS.md` 与 `.trellis/spec/backend/portfolio-image-import.md`，保留用户现有 AGENTS 改动。
- [x] 运行 `python scripts/check_ai_assets.py`。

## 6. Verification Gates

- [x] 语法：`python -m py_compile` 覆盖所有修改的 Python 文件。
- [x] 后端定向：Vision、图片提取、SystemConfigService、配置 registry/validation、Portfolio 图片导入与 API contract。
- [x] Web 定向：systemConfig API、LLMChannelEditor，以及受影响设置页测试。
- [x] 后端完整门禁：使用隔离部署环境执行 `./scripts/ci_gate.sh`。
- [x] Web 完整门禁：`npm ci`、`npm run lint`、`npm run build`。
- [x] 检查 `git diff --check`、敏感文件/Key/base64/provider body 未进入 diff。
- [x] 在线 smoke：本地 `.venv` 通过共享 Vision runtime 与 SystemConfigService 各发一张 32x32 内置空白图，只记录状态、错误码和延迟。

## 7. Handoff and Rollback

- [x] 明确告知用户必须自行重建/重启 `stock-server` 才会生效，并提供健康检查与功能 smoke 步骤。
- [x] 提供回滚：恢复 `VISION_API_MODE=chat_completions`、迁移前配置和上一镜像；无需数据库回滚。
