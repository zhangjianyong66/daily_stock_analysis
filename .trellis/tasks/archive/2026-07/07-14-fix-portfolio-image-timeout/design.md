# 图片识别持仓初始化异步任务设计

## 1. 设计目标

将持仓/成交截图识别从长连接同步请求改为可恢复的进程内异步任务，复用现有 SSE 通知通道，并保持“识别只生成校对草稿、用户确认后才写入账本”的边界。

本设计优先保证：

- 浏览器 30 秒超时不再决定 Vision 任务成败。
- 全局只有一个图片识别任务或待校对结果。
- 页面刷新、SSE 断线和跨标签页场景可从服务端内存恢复状态。
- 原图、base64、模型原始响应不持久化、不进入普通日志。
- 旧同步 parse API 暂时兼容，但与新异步 API 共用同一 Vision 编排与全局槽位。

## 2. 架构边界

### 2.1 新增专用任务管理器

在 `src/services/` 新增 `PortfolioImageTaskManager` 单例，专门管理图片识别任务，不把 `review_required`、草稿 revision 和导入消费语义塞入股票分析 `TaskInfo`。

管理器职责：

- 维护唯一当前任务和线程安全状态机。
- 使用单 worker 后台执行器串行执行异步图片任务。
- 为旧同步 parse 提供共享的全局槽位和同一执行核心。
- 保存任务元数据、文件级状态、结构化识别结果、校对草稿和 `draft_revision`。
- 管理取消标记、60 分钟任务截止和迟到结果隔离。
- 通过现有任务 SSE 广播通道发布轻量状态事件。

不负责：

- 持仓/成交数据库写入。
- 原图持久化。
- 绕过 `PortfolioScreenshotImportService` 的识别、归一化或 commit 校验。

### 2.2 复用现有 SSE 通道

`AnalysisTaskQueue` 继续拥有现有 EventSource 订阅者列表，新增一个公开、受控的事件发布入口，供图片任务管理器发布：

```text
event: portfolio_image_task_updated
data: 轻量任务状态摘要
```

事件只通知“状态已变化”，不携带完整校对草稿。前端收到事件后调用图片任务 REST API 获取权威快照，避免 SSE 载荷过大或在多个消费者中重复解析完整结果。

现有 `task_created/task_started/task_progress/task_completed/task_failed` 保持不变，首页股票任务消费者不会把图片任务误认为股票分析任务。

### 2.3 数据流

```text
选择图片
  -> POST 新异步任务 API
  -> 校验账户/日期/数量/类型/大小/魔数
  -> 内存创建 pending 任务并返回 202 + task_id
  -> 单 worker 串行调用 PortfolioScreenshotImportService
  -> SSE 发布文件级状态变化
  -> review_required + 内存草稿
  -> 前端 GET 任务并渲染/编辑
  -> PATCH 草稿（expected_revision）
  -> POST 现有 commit（task_id + expected_revision + 校对数据）
  -> 原子写账本
  -> 消费任务、删除内存结果、释放全局槽位
```

页面刷新和 SSE 漏事件都通过 `GET current` / `GET task` 恢复，不把 localStorage 作为服务端任务是否存在的真源。

## 3. 状态机

### 3.1 状态

- `pending`：任务已创建，尚未进入 worker。
- `processing`：正在识别图片。
- `cancel_requested`：用户请求取消，等待当前阻塞调用返回。
- `cancelled`：worker 已确认停止，槽位已释放。
- `review_required`：至少一张图片识别成功，存在待校对草稿；继续占用槽位。
- `committing`：已通过 task/revision 检查，正在执行账本 commit；继续占用槽位。
- `failed`：全部图片失败、任务超时或内部安全失败；不再占用运行槽位。

`committed` / `discarded` 只作为 SSE 的终止通知使用；通知后当前任务指针和结构化结果被清除。

### 3.2 转移规则

```text
pending -> processing -> review_required -> committing -> committed(清除)
pending -> cancelled
processing -> cancel_requested -> cancelled
pending/processing -> failed
review_required -> discarded(清除)
committing -> review_required        # commit 失败，保留草稿
```

禁止转移：

- `cancel_requested/cancelled/failed` 的迟到结果进入 `review_required`。
- 非当前 task_id 修改草稿、commit、取消或放弃。
- `review_required` 期间创建第二个图片任务。

## 4. 内存模型

任务记录至少包含：

- `task_id`、`trace_id`。
- `mode`: `positions | trades`。
- `account_id`、账户展示名。
- `snapshot_date` 或 `default_trade_date`。
- `status`、安全 `message/error_code`。
- `created_at/started_at/finished_at`。
- 文件元数据：index、filename、status、record_count、error、removed。
- 真实进度：`current_file_index/total_files/current_attempt/max_attempts/success_count/failure_count`。
- `batch_id`。
- 结构化 `positions` 或 `trades` 草稿。
- `draft_revision`。
- 内部取消事件、deadline、Future 引用；这些字段不得序列化给客户端。

原始 `ImageInput.content` 只由提交后的 worker closure 临时持有。任务进入任一终态后必须释放图片 bytes 引用；`review_required` 只保留结构化结果和文件元数据。

当前服务进程内，`review_required` 不设置 TTL。确认导入、主动放弃或服务重启后清除。

## 5. 全局互斥

阻塞新任务的状态为：

- `pending`
- `processing`
- `cancel_requested`
- `review_required`
- `committing`

新异步提交遇到上述状态时返回 HTTP 409：

```json
{
  "error": "portfolio_image_task_active",
  "message": "已有图片识别任务，请继续处理当前任务",
  "existing_task_id": "...",
  "existing_status": "review_required"
}
```

前端收到后加载既有任务，不再次调用 Vision。

旧同步 parse 也必须先取得相同槽位。它在请求线程池中调用同一识别核心，运行期间可被 `current` API 观察；返回旧响应后释放同步兼容任务，不创建长期草稿。新异步 API 是唯一提供刷新恢复和草稿能力的推荐路径。

## 6. API 契约

### 6.1 新异步接口

- `POST /api/v1/portfolio/imports/images/positions/tasks`
  - multipart：`account_id`、`snapshot_date`、重复 `files`。
  - 返回 HTTP 202：`task_id/status/mode/account_id/message`。
- `POST /api/v1/portfolio/imports/images/trades/tasks`
  - multipart：`account_id`、`default_trade_date`、重复 `files`。
- `GET /api/v1/portfolio/imports/images/tasks/current`
  - 返回 `{ "task": null }` 或当前/最近失败任务快照。
- `GET /api/v1/portfolio/imports/images/tasks/{task_id}`
  - 返回权威任务状态；`review_required` 时包含草稿和 revision。
- `PATCH /api/v1/portfolio/imports/images/tasks/{task_id}/draft`
  - 请求：`expected_revision` 和与 mode 匹配的完整结构化草稿。
  - 成功后 revision +1；冲突返回 409。
- `POST /api/v1/portfolio/imports/images/tasks/{task_id}/cancel`
  - 仅用于 `pending/processing`，返回最新状态。
- `DELETE /api/v1/portfolio/imports/images/tasks/{task_id}`
  - `review_required` 表示放弃；`failed/cancelled` 表示清除提示。

### 6.2 commit 兼容扩展

现有 positions/trades commit 请求新增可选：

- `task_id`
- `expected_revision`

Web 新流程必须传这两个字段。服务端在写库前调用 `begin_commit`：

1. task_id 是当前全局任务。
2. 状态为 `review_required`。
3. mode、account_id、batch_id 匹配。
4. expected_revision 等于当前 revision。

校验成功后状态变为 `committing`。数据库 commit 成功后清除任务；失败则恢复 `review_required` 并保留草稿。

未传 task_id 的旧调用在没有异步 `review_required/committing` 任务时继续走原有 commit 逻辑；存在异步任务时拒绝绕过任务/revision 契约。

### 6.3 旧同步 parse

保留原路径和成功响应模型，OpenAPI 标记 deprecated。Endpoint 使用线程池运行，避免同步 Vision 阻塞 FastAPI 事件循环，并获取同一全局槽位。

## 7. Vision 调用与截止预算

- 单次上游调用 timeout：300 秒。
- 每张图片最多 2 次尝试。
- 只对 timeout、连接建立/读取失败等瞬时网络错误重试一次。
- rate limit、鉴权失败、模型不支持图片、无效图片、空响应和格式错误不重试。
- 同一任务图片按上传顺序串行处理。
- 整批 deadline：创建后 60 分钟。
- 每次调用使用 `min(300 秒, 剩余任务预算)`。
- 达到 deadline 后不启动下一张；当前调用返回后任务进入 `failed`，错误码 `portfolio_image_task_timeout`。

`complete_vision` 增加可选 attempt callback/deadline 参数，但默认调用方行为需保持可测试兼容；图片任务通过 callback 发布当前文件和尝试次数。

## 8. 部分失败与草稿

- 每张图片独立生成文件结果。
- 至少一张成功：任务进入 `review_required`，保留成功行和失败文件状态。
- 全部失败：任务进入 `failed`，不生成空校对表，允许新提交。
- 不支持在同一 task_id 中追加图片或重跑失败图片。
- 用户可在草稿中标记失败文件已移除，并编辑/删除识别行。

草稿 PATCH 使用 `draft_revision` 乐观锁。409 时前端停止自动保存，提示重新加载服务端最新草稿。commit 同样检查 revision，避免旧标签页提交过期内容。

## 9. 前端状态所有权

`PortfolioPage` 持有当前图片任务摘要，并负责：

- 首次加载调用 `GET current`。
- 订阅 `portfolio_image_task_updated` SSE。
- 收到事件后按 task_id 获取最新快照。
- 渲染常驻任务横幅。
- 已有任务时把“图片导入”入口路由到当前任务。

`PortfolioImageImportDialog` 负责：

- 新建任务的文件选择和提交。
- 展示 pending/processing/cancel_requested 文件级进度。
- review_required 草稿编辑、500ms 左右防抖保存和保存状态提示。
- revision 冲突后的停止保存/重新加载。
- commit、取消、放弃。

异步任务运行期间允许关闭抽屉，任务继续执行；`committing` 期间保持现有关闭保护。

## 10. 错误与日志

稳定错误码至少包括：

- `portfolio_image_task_active`
- `portfolio_image_task_not_found`
- `portfolio_image_task_state_conflict`
- `portfolio_image_draft_conflict`
- `portfolio_image_task_timeout`
- `vision_timeout`
- `vision_rate_limited`
- `vision_not_configured`
- `vision_unsupported`
- `vision_failed`

日志只记录 task_id、mode、account_id、文件序号、尝试次数、状态转移和低敏错误码；不记录文件内容、base64、完整 prompt、模型原始响应、API Key 或完整 provider body。

前端错误解析需区分 Axios 客户端 `ECONNABORTED` 与服务端上游 timeout，避免继续显示错误归因。

## 11. 兼容性与部署

- 不新增 WebSocket，不需要调整 nginx/frp Upgrade 配置。
- SSE 仍使用现有 HTTP vhost 和 cookie 鉴权。
- 不新增数据库表或迁移。
- 不新增环境配置项；timeout/budget 作为图片能力的代码级安全常量并由测试锁定。
- 服务重启会丢失任务和草稿，前端对旧 task_id 展示明确中断提示。
- 旧同步 API 保留并标记 deprecated；中英文文档同步更新。

## 12. 回滚

回滚时：

1. Web 恢复调用旧同步 parse。
2. 移除新增图片任务 API、管理器和 SSE 图片事件监听。
3. 恢复 Vision 原 timeout/retry 常量。
4. commit 新增字段保持可选即可，不要求数据库回滚。

无数据库结构变更，回滚不涉及数据迁移；已通过 commit 写入的持仓/成交仍按现有删除/修正流程处理。
