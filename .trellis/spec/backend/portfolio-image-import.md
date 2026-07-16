# 持仓与成交截图导入契约

## 1. Scope / Trigger

- 修改持仓截图、成交截图、Vision 图片调用、图片任务状态、草稿 revision、图片导入 API 或 Web 校对流程时适用。
- 该能力跨越 Vision -> Service -> 进程内任务 -> Repository/DB -> API/SSE -> Web，必须检查完整数据流。

## 2. Signatures

- 创建任务：
  - `POST /api/v1/portfolio/imports/images/positions/tasks`
  - `POST /api/v1/portfolio/imports/images/trades/tasks`
- 查询与控制：
  - `GET /api/v1/portfolio/imports/images/tasks/current`
  - `GET /api/v1/portfolio/imports/images/tasks/{task_id}`
  - `PATCH /api/v1/portfolio/imports/images/tasks/{task_id}/draft`
  - `POST /api/v1/portfolio/imports/images/tasks/{task_id}/cancel`
  - `DELETE /api/v1/portfolio/imports/images/tasks/{task_id}`
- 提交：
  - `POST /api/v1/portfolio/imports/images/positions/commit`
  - `POST /api/v1/portfolio/imports/images/trades/commit`
  - 异步 Web 调用必须携带 `task_id/expected_revision`；旧调用字段可省略。
- 兼容接口：`positions/parse`、`trades/parse` 保留并标记 deprecated，在线程池执行且共享全局任务槽和识别核心。
- SSE：复用 `/api/v1/analysis/tasks/stream`，事件类型 `portfolio_image_task_updated`，载荷只含轻量摘要。
- DB：`PortfolioTrade.trade_time` 为 nullable `TIME`；图片任务和草稿不新增数据库表。
- 共享 Vision：`complete_vision(image_bytes, mime_type, prompt, *, max_tokens=1024, attempt_callback=None, deadline_monotonic=None) -> str`；持仓导入与自选股提取必须共用该入口。
- 设置页渠道测试：`POST /api/v1/system/config/llm/channels/test` 的 `TestLLMChannelRequest` 包含 `extra_headers: Dict[str, str]` 与 `vision_api_mode: chat_completions | responses`，默认模式为 `chat_completions`。

## 3. Contracts

### 3.1 上传、任务与恢复

- 只支持活跃 `cn/CNY` 账户、6 位证券代码、每批 1-5 张 JPEG/PNG/WebP/GIF，单文件最大 5MB。
- 新任务上传只完成账户、日期、数量、MIME、大小和魔数校验，快速返回 HTTP 202；Vision 不占用原始 HTTP 请求。
- 全服务全局只有一个阻塞槽，持仓/成交和所有账户共享。阻塞状态：`pending/processing/cancel_requested/review_required/committing`。
- 重复提交返回 HTTP 409 `portfolio_image_task_active`、`existing_task_id/existing_status`，不得启动第二次 Vision。
- 正常状态：`pending -> processing -> review_required -> committing -> committed(清除)`；全部文件失败进入 `failed`。
- `review_required` 表示识别完成但未写账本，不按时间过期。确认导入或放弃后清除；服务重启自然丢失任务、草稿和槽位。
- Web 首屏查询 current task，并用本地 task ID 识别服务重启后的 404；SSE 只触发 REST 刷新，不能作为权威状态真源。

### 3.2 Vision 预算、顺序与取消

- Vision 只使用显式 `VISION_MODEL`，兼容废弃别名 `OPENAI_VISION_MODEL`；不得使用 `LITELLM_MODEL` 文本主模型顶替。
- `VISION_API_MODE` 只允许 `chat_completions`（默认）或 `responses`。不得按域名/模型推断模式，不得跨协议 fallback 或重复发送同一图片。
- LiteLLM Responses 的干净安装依赖 `requirements.txt` 显式声明 `orjson`；不得假设开发机虚拟环境或 LiteLLM 的非必选 extras 已经间接安装。`docker/Dockerfile` 必须在构建阶段执行 `import orjson`，让依赖漂移在镜像构建时失败，而不是在真实图片任务中失败。
- Responses deployment 由 `LLM_CHANNELS` 与 `LLM_<CHANNEL>_{PROTOCOL,BASE_URL,API_KEY,MODELS,ENABLED,EXTRA_HEADERS}` 定义；每日分析 workflow 还必须把全局 `VISION_API_MODE` 从同名 Actions Variable/Secret 映射到进程环境。私有自定义渠道名仍由部署者自行映射，不写入通用 workflow。
- Chat Completions 精确匹配非 Hermes LLM Channel route 时通过 LiteLLM Router 复用 deployment；无匹配 route 时保留 legacy provider Key/Base URL 路径。Responses 必须精确匹配非 legacy、非 Hermes route，并复用其 wire model、Base URL、API Key 与 Extra Headers；缺 route 在发网前返回 `vision_not_configured`。
- Router 内部 retry/fallback 必须关闭，外层仍统一拥有 300 秒单次上限、最多两次 attempt、整体 deadline 与取消迟到结果规则。Responses output 需兼容 Mapping/对象形状并归一化为纯文本，下游不得感知协议差异。
- 单次调用 timeout 为 300 秒；每张最多 2 次，只对 timeout/connection 类瞬时错误重试一次。
- rate limit、鉴权失败、模型不支持图片、无效图片、空响应和格式错误不重试，并使用低敏稳定错误码。
- 1-5 张图片按上传顺序串行；整批 deadline 为 60 分钟，达到上限后不启动下一张，当前调用收敛后任务失败。
- `pending/processing -> cancel_requested -> cancelled`。阻塞上游调用不保证强杀；取消确认前继续占槽，迟到结果不得进入 review。
- `review_required` 使用 discard，不称为取消；失败图片不能在原 task 原位重试。

### 3.3 草稿与提交

- 至少一张成功才进入 `review_required`；部分失败保留成功行和失败文件，失败文件必须标记 removed 后才能 commit。
- 服务端草稿只保存结构化 files/positions/trades，不保存原图、base64 或模型原始响应。
- 草稿使用单调递增 `draft_revision`。PATCH 和 commit 都必须携带 `expected_revision`；不一致返回 409 `portfolio_image_draft_conflict`。
- 草稿自动保存必须串行；保存进行中产生的新编辑不能被旧保存结果标记为已保存或覆盖。
- commit 校验当前 task、mode、account_id、batch_id、日期和 revision；旧标签页不得提交新版本草稿。
- commit 失败恢复 `review_required` 并保留草稿；成功后只写一次并清除任务。
- 内存草稿不绕过现有账本事务：持仓初始化要求账户无交易；成交仍重新校验重复 occurrence、顺序、超卖和写锁。

### 3.4 数据与隐私

- 持仓初始化只提交 `symbol/name/quantity/avg_cost`，生成 fee/tax=0 的期初买入；资金汇总不入账。
- 成交提交接受可空 `trade_time`、非负 `fee/tax` 和稳定 `occurrence_index`；客户端 fingerprint/hash 不可信。
- 成交插入、账本重放、超卖校验和列表查询统一按 `trade_date -> known trade_time -> null -> stable order`。
- 日志只记录 task_id、mode、account_id、文件序号、尝试、状态和低敏错误码；不得记录原图、base64、完整 prompt、模型响应、Key、Authorization 或 provider body。
- deployment API Key 与 Extra Header 值必须进入异常脱敏集合；设置页 Vision 探针只使用不含业务数据、宽高至少 32px 的内置图片。
- 客户端 Axios `ECONNABORTED` 必须与服务端 Vision timeout 分开提示。

## 4. Validation & Error Matrix

| 条件 | 结果 |
| --- | --- |
| 已有阻塞图片任务 | 409 `portfolio_image_task_active` + existing task |
| task 不存在/服务重启 | 404 `portfolio_image_task_not_found` |
| 草稿或 commit revision 过期 | 409 `portfolio_image_draft_conflict` |
| 状态/mode/account/batch/date 不匹配 | 409 `portfolio_image_task_state_conflict` |
| 整批超过 60 分钟 | `failed/portfolio_image_task_timeout` |
| 未配置 Vision / 缺 provider key | `vision_not_configured` |
| `VISION_API_MODE` 非法 | 配置归一化为默认 `chat_completions` 并产生结构化 warning |
| 干净 Docker 镜像缺少 `orjson` | 镜像构建在运行时依赖导入检查处失败，不得发布或等到 Vision 任务才暴露 `ModuleNotFoundError` |
| Responses 缺精确非 legacy、非 Hermes route | 发网前 `vision_not_configured`，不得尝试 legacy Key/Base URL |
| Responses output 为空或只有非文本 item | 低敏空响应错误，不重试、不返回 provider body |
| 上游 timeout / 网络 / 限流 / 鉴权 | `vision_timeout` / `vision_network_error` / `vision_rate_limited` / `vision_auth_failed` |
| 模型不支持图片 / 非法文件 | `vision_unsupported` / `unsupported_type` / `invalid_image` |
| 持仓账户已有交易 | HTTP 409 `account_not_empty`，草稿保留、零写入 |
| 时间线歧义 / 超卖 / 写锁 | 409 `ambiguous_trade_order` / `portfolio_oversell` / `portfolio_busy`，草稿保留 |

## 5. Good / Base / Bad Cases

- Good：Vision 运行超过浏览器原 30 秒阈值，Web 仍可关闭抽屉并从横幅/刷新恢复同一任务。
- Good：两个标签页同时编辑，旧 revision 保存/提交得到 409，不覆盖新草稿。
- Good：取消发生在第 1 张上游调用中；调用返回后不启动第 2 张，迟到结果不进入 review。
- Good：Responses route 精确匹配并携带渠道 Extra Headers，Mapping/对象形状的 `output_text` 均归一化为纯文本。
- Good：从空缓存构建 Docker 镜像时，`requirements.txt` 安装 `orjson`，Dockerfile 导入检查通过，内置 32×32 探针可完成一次真实 Responses smoke。
- Base：单图成功进入 review，确认提交后原子写入并清除 current task。
- Base：未配置 `VISION_API_MODE` 时继续走 Chat Completions；没有匹配 route 时仍可使用既有 provider Key/Base URL。
- Base：旧同步 parse 保持成功响应，但运行期间占用同一全局槽。
- Bad：Web 仍调用同步 parse 或为图片请求单纯放大 Axios timeout。
- Bad：失败/取消后迟到 worker 覆盖终态，或 `review_required` 自动 TTL 清理。
- Bad：草稿保存并发发送相同 revision，旧响应把后续编辑误标为已保存。
- Bad：通过不带 task_id 的旧 commit 绕过正在等待校对的异步任务。
- Bad：根据中转站域名或模型名自动改走 Responses，或者 Chat/Responses 失败后跨协议重发同一图片。
- Bad：只在已有开发虚拟环境执行在线 smoke，却没有用干净 Docker 镜像验证依赖安装与导入。

## 6. Tests Required

- 后端：
  - `tests/test_vision_extraction_service.py`
  - `tests/test_portfolio_screenshot_import_service.py`
  - `tests/test_portfolio_image_task_manager.py`
  - `tests/test_portfolio_api.py`
  - `tests/test_analysis_api_contract.py`
- 必须覆盖：202、全局防重、状态转移、部分/全部失败、300 秒/两次尝试、错误重试矩阵、60 分钟 deadline、取消迟到结果、draft revision、两阶段 commit、旧 API 兼容、SSE 事件隔离。
- Vision 协议测试必须断言：默认 Chat 兼容、精确 route、Router 内部 retry/fallback 关闭、Responses 请求形状、Mapping/对象文本提取、缺 route 零网络调用、空 output 不重试，以及 Key/Extra Header/provider body 脱敏。
- 配置与部署测试必须断言：registry/API/Web snake-camel 往返、设置页所有能力测试透传 Extra Headers、32×32 低敏探针、`requirements.txt` 显式安装 `orjson`、Dockerfile 构建阶段可导入 `orjson`，以及 `.github/workflows/00-daily-analysis.yml` 同时引用 `vars.VISION_API_MODE` 和 `secrets.VISION_API_MODE`。
- Web：API snake/camel 映射、任务恢复横幅、SSE 后 REST 刷新、关闭抽屉继续执行、草稿串行防抖保存、revision 冲突、取消/放弃/commit、服务重启提示。
- 可视：桌面和 390px 移动视口验证任务横幅、文件进度、review 行和 footer；截图只作 PR 外部证据，不入库。

## 7. Wrong vs Correct

### Wrong：用同步请求或单纯放大 Axios timeout 等待 Vision

```typescript
const parsed = await parsePositionImages(formData, { timeout: 300_000 })
setDraft(parsed)
```

长请求仍会被浏览器、反向代理或网络切换中断，刷新后也没有可恢复的服务端任务。

### Correct：快速创建任务，SSE 只通知，REST 恢复权威快照

```typescript
const accepted = await createPositionImageTask(formData)
rememberTaskId(accepted.taskId)

// portfolio_image_task_updated 只触发刷新；完整状态始终来自 REST。
const task = await getPortfolioImageTask(accepted.taskId)
```

### Wrong：多个防抖 PATCH 并发复用同一 revision

```typescript
void saveDraft({ expectedRevision: revision, draft: firstEdit })
void saveDraft({ expectedRevision: revision, draft: secondEdit })
```

旧响应可能覆盖或误标后续编辑；两个标签页也无法可靠识别过期版本。

### Correct：完整草稿严格串行保存，并用服务端新 revision 推进

```typescript
await saveDraft({ expectedRevision: revision, draft: latestDraft })
revision = response.draftRevision

if (editedWhileSaving) {
  await saveLatestDraftSerially()
}
```

收到 `portfolio_image_draft_conflict` 后必须停止自动保存并重新加载权威草稿，不能静默重试覆盖。

### Wrong：为 Responses 增加平行 Vision-only 连接配置或协议 fallback

```env
VISION_API_BASE=https://relay.example.com/v1
VISION_API_KEY=xxx
VISION_API_MODE=auto
```

这会复制 LLM Channel 的连接真源，并可能在失败后重复发送用户图片。

### Correct：显式选择协议并精确复用渠道 deployment

```env
LLM_CHANNELS=primary,vision_relay
LLM_VISION_RELAY_PROTOCOL=openai
LLM_VISION_RELAY_BASE_URL=https://relay.example.com/v1
LLM_VISION_RELAY_API_KEY=xxx
LLM_VISION_RELAY_MODELS=gpt-vision
LLM_VISION_RELAY_EXTRA_HEADERS={"User-Agent":"Mozilla/5.0"}
VISION_MODEL=openai/gpt-vision
VISION_API_MODE=responses
```

Responses 缺少该精确 route 时必须返回 `vision_not_configured`，不得回退到 legacy `OPENAI_*` 或 Chat Completions。

### Wrong：依赖本地环境偶然存在的 Responses 运行时包

```text
litellm>=1.80.10,<2.0.0
# 本地 smoke 通过，因此假设 Docker 也可用
```

LiteLLM 小版本和安装 extras 可能改变导入路径；本地已有环境不能证明干净镜像具备相同依赖。

### Correct：依赖真源显式声明并在镜像构建时导入

```text
litellm>=1.80.10,<2.0.0
orjson>=3.10.0,<4.0.0
```

```dockerfile
RUN python -c "import orjson"
```

依赖缺失会直接阻断镜像构建，不会让用户图片任务成为首次发现点。
