# 修复 GPT-5.6 Vision 中转站调用

## Goal

让现有共享 Vision 能力能够通过 OpenAI 兼容中转站稳定调用 `gpt-5.6-sol` 识别图片，同时保持 Gemini、Anthropic、既有 OpenAI Chat Completions 路径和持仓图片导入契约不变。

## Confirmed Facts

- 当前 `.env` 与运行中的 `stock-server` 均已加载 `VISION_MODEL=openai/gpt-5.6-sol` 和 `OPENAI_BASE_URL=https://www.tudoudada.top/v1`。
- 中转站 `/v1/models` 鉴权成功并返回 `gpt-5.6-sol`，因此 Base URL、API Key 和模型可见性正常。
- 现有 `src/services/vision_extraction_service.py` 统一通过 `litellm.completion()` 发起 Vision 请求；默认 SDK 请求头被中转站拦截并返回 `Your request was blocked.`。
- 显式发送普通 `User-Agent` 后，文本 Chat Completions 调用成功；图片 Chat Completions 虽返回 HTTP 200 和 `finish_reason=stop`，但 assistant message 没有 `content`、`refusal` 或其他正文。
- 同一模型、Key、图片和 `User-Agent` 改走 `/v1/responses` 后返回 HTTP 200、`status=completed` 和有效 `output_text=OK`，证明中转站的 GPT-5.6 Vision 能力可通过 Responses API 使用。
- `src/config.py::extra_litellm_params()` 目前没有通用 OpenAI/Vision 自定义请求头配置，仅对 AIHubMix 固定注入 `APP-Code`。
- 当前 LiteLLM Router 原生提供同步 `responses()`，可复用 model list 中同名 deployment 的 Base URL、Key、Extra Headers 和选择策略；共享 Vision 层仍需关闭 Router 内部重试，避免与现有最多两次尝试叠加。
- 使用内存 Router deployment 对当前中转站实测 `Router.responses()` 成功返回 `status=completed` 和 `OK`；LiteLLM 的 `output/content` 项为 Mapping，文本提取必须同时兼容 Mapping 与对象属性形状。
- 持仓/成交截图与自选股图片提取共用 Vision 边界；修复不能只覆盖其中一个入口。

## Requirements

- R1：Vision 复用与 `VISION_MODEL` 精确匹配的现有 LLM Channel deployment，从中解析 wire model、Base URL、API Key 和 `extra_headers`；至少能显式覆盖 `User-Agent`，不新增平行的 `VISION_API_KEY / VISION_API_BASE / VISION_EXTRA_HEADERS`。
- R2：新增全局 `VISION_API_MODE`，允许值为 `chat_completions` 与 `responses`，默认 `chat_completions`；不得按域名/模型自动切换，也不得在两个协议之间回退或重复发送同一图片。
- R3：Responses 结果必须归一化为现有共享 Vision 层返回的纯文本契约，下游持仓 JSON 解析器和自选股提取器不感知协议差异。
- R4：保留现有单次 300 秒上限、瞬时错误最多重试一次、整体 deadline、稳定错误码和取消迟到结果规则。
- R5：配置必须是通用、可验证、可回滚的能力，不在业务代码中写死中转站域名、API Key、模型名或请求头。
- R6：新增配置项时同步 `.env.example`、中英文 LLM 配置文档与 `docs/CHANGELOG.md`。
- R7：`VISION_API_MODE=responses` 时必须存在与 `VISION_MODEL` 精确匹配的非 Hermes LLM Channel deployment；缺失时 fail-fast 为 `vision_not_configured`，不得回退到全局 legacy `OPENAI_*`。
- R8：中转站渠道遵循现有 LLM Channel 语义，不新增 Vision-only 渠道类型；本次保持现有主模型、Agent 模型和 fallback 选择不变，不自动切换到 GPT-5.6。
- R9：本次保持图片 detail 为 provider 默认 `auto`，不新增 `VISION_IMAGE_DETAIL`，不强制 `original`。
- R10：当前部署迁移到 `LLM_TUDOU_*` 后清理重复的 legacy `OPENAI_BASE_URL / OPENAI_API_KEY`，中转渠道作为 Base URL、Key 和 Extra Headers 的唯一真源；保留现有 DeepSeek 主模型不变。
- R11：设置页渠道 Vision 测试必须提交并使用渠道 Extra Headers，并按显式 `VISION_API_MODE` 选择 Chat Completions 或 Responses，测试结果与运行时协议一致。
- R12：通用 Vision 能力探针使用不含业务数据且宽高不小于 32px 的内置图片，避免 1×1 图片触发 provider 最小尺寸限制而误报不支持。
- R13：API Key、Authorization、Extra Header 值、图片、base64、完整 prompt 和 provider body 不得进入普通日志、API 错误或任务快照。
- R14：最终允许使用当前中转站和真实 Key 发起最小在线 smoke；只发送内置 32×32 空白图片和固定短提示，不发送用户截图，不输出模型正文、Key 或 provider body。
- R15：本次不得重建镜像或重启 `stock-server`；交付时必须明确说明代码与配置需要用户自行重建/重启后才会在在线服务生效，并提供验证步骤。

## Acceptance Criteria

- [x] AC1：使用当前中转站、有效 Key、`gpt-5.6-sol`、Responses API 和所需请求头时，共享 Vision 层能返回可解析文本。
- [x] AC2：持仓截图导入和自选股图片提取均复用同一协议选择与请求头实现，不新增平行调用链。
- [x] AC3：未启用新配置时，现有 `litellm.completion()` 行为、provider Key 选择、Base URL 和重试语义保持兼容。
- [x] AC4：空 Responses output、非文本 output、HTTP/鉴权/限流/超时/网络错误映射为现有低敏稳定错误码，不泄露 provider body。
- [x] AC5：测试覆盖请求形状、请求头、Responses 文本提取、兼容路径、重试与隐私边界。
- [x] AC6：文档给出启用、回滚和服务重启要求，不记录真实 Key 或私有响应。
- [x] AC7：渠道中的 `LLM_<CHANNEL>_EXTRA_HEADERS` 能进入 Vision 请求；敏感请求头仍遵守现有配置脱敏和日志边界。
- [x] AC8：Responses 模式缺少匹配渠道时不发起网络请求，并返回可操作的 `vision_not_configured`。
- [x] AC9：当前 `.env` 迁移后只保留一份中转站连接配置，配置解析出的主模型仍为 `deepseek/deepseek-v4-pro`，Vision 为 `openai/gpt-5.6-sol`。
- [x] AC10：设置页测试携带 Extra Headers，Responses 模式能提取 output text；32×32 探针不包含用户图片或业务数据。
- [x] AC11：离线门禁通过后，真实运行时 Vision 与设置页渠道 Vision 测试各完成一次最小在线 smoke，并只记录成功状态、错误码和延迟。
- [x] AC12：交付前不改变当前容器生命周期；交付说明包含用户执行的重建/重启命令、预期短暂中断、健康检查和回滚方式。

## Out of Scope

- 不迁移主分析模型或 Agent 模型到 GPT-5.6。
- 不改变图片持久化、任务槽、草稿 revision 或账本提交语义。
- 不为某一个域名添加硬编码分支。
- 不包含图片 detail/OCR 质量调优；功能恢复后再基于真实截图单独评估 `original` 的识别率、成本和延迟。
