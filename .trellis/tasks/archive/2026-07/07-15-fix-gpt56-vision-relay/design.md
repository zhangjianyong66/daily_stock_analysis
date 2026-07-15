# 修复 GPT-5.6 Vision 中转站调用：技术设计

## 1. Problem and Boundaries

当前共享 Vision 层只调用 Chat Completions。当前中转站要求普通 `User-Agent`，且 `gpt-5.6-sol` 图片请求只有 Responses API 返回有效文本。修复必须落在共享 Vision 边界，不能在持仓导入或自选股提取器中增加 provider 特判。

本任务是一个跨配置、后端、API、Web 和文档的单一契约变更，各部分不能独立上线，因此不拆分子任务。

## 2. Configuration Contract

新增：

```env
VISION_API_MODE=chat_completions  # chat_completions | responses
```

- 默认 `chat_completions`，保持现有行为。
- `responses` 必须有与 `VISION_MODEL` 精确匹配的非 legacy、非 Hermes Router deployment。
- Base URL、Key、wire model 和 Extra Headers 只从匹配 deployment 读取。
- 不按域名或模型名自动推断模式，不跨协议 fallback。
- `VISION_IMAGE_DETAIL` 不在本次新增，保持 provider 默认 `auto`。

当前部署迁移为：

```env
LLM_CHANNELS=deepseek,tudou
LLM_TUDOU_PROTOCOL=openai
LLM_TUDOU_BASE_URL=https://www.tudoudada.top/v1
LLM_TUDOU_API_KEY=<现有中转站 Key>
LLM_TUDOU_MODELS=gpt-5.6-sol
LLM_TUDOU_EXTRA_HEADERS={"User-Agent":"Mozilla/5.0"}
VISION_MODEL=openai/gpt-5.6-sol
VISION_API_MODE=responses
```

迁移后清理 `OPENAI_BASE_URL`、`OPENAI_API_KEY` 和空/重复的 `OPENAI_API_KEYS`，保留 `LITELLM_MODEL=deepseek/deepseek-v4-pro`。

## 3. Runtime Data Flow

```text
image bytes
  -> validate MIME / size / magic bytes
  -> resolve VISION_MODEL + VISION_API_MODE
  -> find exact Router deployments
  -> build Router with internal retry/fallback disabled
  -> chat_completions: Router.completion or legacy direct completion
     responses: Router.responses
  -> normalize provider response to text
  -> existing portfolio/watchlist JSON parser
```

### 3.1 Route resolution

- 精确匹配 `model_list[*].model_name == VISION_MODEL`。
- 排除 `__legacy_*`；Hermes 继续由现有 guard 拒绝。
- Chat Completions：有匹配 deployment 时走 Router，以便复用渠道 Extra Headers；没有时保留 legacy provider Key/Base URL 路径。
- Responses：没有匹配 deployment 时在网络调用前抛 `vision_not_configured`。
- 匹配 deployment 中的 API Key 与 Extra Header 值全部加入异常脱敏集合。

### 3.2 Retry ownership

- Router 使用 `num_retries=0`、`max_fallbacks=0` 并禁用 cooldown 对外层语义的干扰。
- 共享 `complete_vision()` 继续拥有 attempt callback、deadline、一次瞬时重试和错误分类。
- 空 output、非文本 output 和格式错误不重试。

### 3.3 Responses request/response

请求：

```json
{
  "model": "<VISION_MODEL>",
  "input": [{
    "role": "user",
    "content": [
      {"type": "input_text", "text": "<prompt>"},
      {"type": "input_image", "image_url": "data:<mime>;base64,..."}
    ]
  }],
  "max_output_tokens": 1024
}
```

不显式发送 `detail`。文本提取遍历 `response.output[*].content[*]`，兼容 Mapping 与对象属性两种形状，只接受非空 `output_text/text`；无文本时抛低敏空响应异常。

## 4. Configuration Validation

- `Config` 增加 `vision_api_mode`，直接 `.env` 非法值记录 warning 并回退默认。
- 配置 registry 将 `VISION_API_MODE` 暴露为二选一模式控件。
- `validate_structured()` 在 Responses 模式下检查精确 Router route、API Key/Base URL 和 Hermes 禁止规则。
- Vision Key 检查同时识别匹配 deployment 凭据，不能因为清理 legacy `OPENAI_API_KEY` 产生误告警。

## 5. Settings Channel Test

后端 `TestLLMChannelRequest` 增加：

- `extra_headers: Dict[str, str]`
- `vision_api_mode: chat_completions | responses`

基础连接、JSON、Tools、Stream 调用均透传 Extra Headers。Vision capability 按显式模式构造请求；Responses 路径复用共享请求构造和文本提取 helper。

探针从 1x1 PNG 改为 32x32 内置 PNG，不包含用户数据。错误结果继续使用现有 capability result 结构，并脱敏 API Key 与 Extra Header 值。

Web 端：

- `ChannelConfig` 保存/回显 `extraHeaders` JSON。
- 渠道连接测试和能力测试都提交解析后的 Extra Headers。
- RuntimeConfig 增加 `visionApiMode`，在 LLM Channel Editor 中提供两段模式控件并随渠道配置保存。
- API snake/camel 映射增加 `extra_headers` 和 `vision_api_mode`。

## 6. Compatibility and Security

- 未配置 `VISION_API_MODE` 时所有现有 provider 保持 Chat Completions。
- 现有 `VISION_MODEL`、deprecated `OPENAI_VISION_MODEL`、timeout、重试和稳定错误码保持兼容。
- 不记录图片、base64、完整 prompt、provider body、Authorization、Key 或 Extra Header 值。
- SystemConfigService 返回的 diagnostic details 只保留错误类别、阶段、重试性和延迟。

## 7. Documentation and Governance

- 更新 `.env.example`、`docs/LLM_CONFIG_GUIDE.md`、英文对应文档、`docs/full-guide.md`、英文对应文档和 `docs/CHANGELOG.md`。
- 更新 `AGENTS.md` 持仓图片导入运行约定，并保留当前未提交的分层测试原则改动。
- 更新 `.trellis/spec/backend/portfolio-image-import.md`，记录 Responses/Channel/Extra Headers 契约。
- 因修改治理资产，运行 `python scripts/check_ai_assets.py`。

## 8. Rollout and Rollback

本轮不重建或重启容器。代码、Web 静态产物和 `.env` 在工作区准备完成后，由用户自行重建/重启 `stock-server`。

回滚：恢复 `VISION_API_MODE=chat_completions` 与迁移前渠道/legacy OpenAI 配置，并使用上一镜像重建容器。任务不涉及数据库迁移或持仓数据写入。
