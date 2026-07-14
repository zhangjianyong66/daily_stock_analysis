# 修复图片识别持仓初始化超时

## Goal

将持仓/成交截图识别改为可恢复的进程内异步任务，避免 Web 固定 30 秒超时把仍在正常执行的 Vision 任务误判为失败；用户在页面刷新、SSE 断线或切换标签页后仍能获取唯一当前任务、继续校对并显式确认导入。

## Background

- Web Axios 全局超时为 30 秒：`apps/dsa-web/src/api/index.ts:7`。
- 图片 parse 未设置专用超时：`apps/dsa-web/src/api/portfolio.ts:309`、`apps/dsa-web/src/api/portfolio.ts:341`。
- Vision 当前单次 timeout 为 60 秒、最多尝试 3 次：`src/services/vision_extraction_service.py:156`、`src/services/vision_extraction_service.py:200`。
- 图片当前按上传顺序串行识别：`src/services/portfolio_screenshot_import_service.py:181`、`src/services/portfolio_screenshot_import_service.py:237`。
- 2026-07-14 现场请求中，浏览器报 `timeout of 30000ms exceeded`，服务端稍后对 positions parse 返回 HTTP 200，且没有对应 commit 请求；本次失败发生在等待识别结果阶段，没有写入持仓。
- 容器到当前阿里百炼 OpenAI-compatible `/models` 入口检查耗时约 0.265 秒；当前证据不支持代理断网是主因。
- Axios `ECONNABORTED` 当前被统一显示为“服务端访问外部依赖超时”：`apps/dsa-web/src/api/error.ts:466`，与实际客户端等待超时不一致。
- 项目没有 WebSocket，但已有 `/api/v1/analysis/tasks/stream` SSE、共享 `useTaskStream`、线程池后台任务和 AlphaSift 刷新恢复范例，可复用现有基础设施。

## Requirements

### R1. 异步任务与 API 兼容

- 新增 positions/trades 图片异步任务 API。上传请求只完成账户、日期、文件数量、大小、MIME 和魔数校验，快速返回 HTTP 202 与 `task_id`；Vision 不占用原始 HTTP 请求连接。
- Web 图片导入全部切换到新异步 API。
- 现有 `/imports/images/{positions|trades}/parse` 保留原同步成功响应并标记 deprecated；旧接口使用线程池并与新接口共享同一全局槽位和识别编排，不能形成绕过防重、取消、预算和隐私约束的平行实现。
- positions/trades commit 请求兼容新增可选 `task_id`、`expected_revision`；Web 新流程必须携带它们，旧调用在没有异步待处理任务时保持兼容。

### R2. 唯一任务与状态机

- 整个服务全局最多存在一个阻塞新提交的图片任务，持仓和成交、所有账户共享同一槽位。
- 阻塞状态为 `pending`、`processing`、`cancel_requested`、`review_required`、`committing`。
- 新提交遇到阻塞状态时返回稳定 409、`existing_task_id` 和现有状态；前端加载既有任务，不触发第二次 Vision 调用。
- 正常状态流为 `pending -> processing -> review_required -> committing -> committed`；commit 成功后清除结果并释放槽位。
- 至少一张图片成功时进入 `review_required`；全部图片失败时进入 `failed`，不展示空校对表并允许重新提交。
- `review_required` 表示识别完成但尚未写入持仓/成交，必须与“导入完成”明确区分。
- `review_required` 在当前服务进程生命周期内不按时间过期；只有确认导入成功、主动放弃或服务重启才清除并释放。
- 服务重启不恢复任务、草稿或槽位。前端查询旧 task_id 时清理本地引用并提示“任务因服务重启已中断，请重新提交”。

### R3. 取消、截止和迟到结果

- 支持尽力取消：`pending/processing -> cancel_requested -> cancelled`。
- pending 尚未运行时直接取消；processing 中不能保证中断当前阻塞上游调用，当前调用返回后停止后续图片。
- `cancel_requested` 在 worker 真正停止前继续占用槽位；取消后的迟到结果不得进入 `review_required` 或覆盖终态。
- `review_required` 使用“放弃本次识别”操作并立即清除结果；不称为取消。
- 单个任务整体运行上限为 60 分钟。达到上限后不再启动下一张图片，当前调用收敛后进入失败状态并释放槽位。

### R4. Vision 预算和多图执行

- Vision 单次调用 timeout 为 300 秒。
- 单张图片最多尝试 2 次，只对 timeout、连接建立/读取失败等瞬时网络错误重试一次。
- rate limit、鉴权失败、模型不支持图片、无效图片、空响应和格式错误等确定性错误不重试。
- 1-5 张图片按上传顺序串行处理，不做图片级并发。
- 进度只展示真实阶段、当前第 N/M 张、当前尝试、成功/失败计数和取消等待，不伪造模型内部连续百分比。
- 多图部分成功时保留成功结果和失败文件状态；用户可删除失败项继续校对，或放弃整批重新创建任务。
- 本次不支持向既有 task_id 追加图片或原位重试失败图片。

### R5. 校对草稿和并发安全

- `review_required` 的结构化草稿保存在服务端内存，包含文件状态和 positions/trades 校对行；不包含原图、base64 或模型原始响应。
- 前端编辑字段、删除行、移除失败文件和解决冲突后，防抖同步完整草稿；页面刷新后恢复最新已保存版本。
- 草稿使用单调递增的 `draft_revision` 乐观并发控制。更新必须携带 `expected_revision`；版本不一致返回 409，禁止静默最后写入覆盖。
- commit 必须校验当前 task_id、mode、account_id、batch_id 和 expected_revision；旧标签页不得提交过期草稿。
- commit 继续使用用户提交的数据执行现有原子账本校验，内存草稿不能绕过账户为空、重复、顺序、超卖或写锁契约。
- commit 失败时恢复 `review_required` 并保留草稿；成功后删除任务结果。

### R6. 前端恢复与通知

- 复用现有 `/api/v1/analysis/tasks/stream` SSE，不新增 WebSocket。
- SSE 增加图片任务专用事件；事件只携带轻量状态摘要，前端收到后通过 REST 获取权威快照。
- `PortfolioPage` 首次加载查询当前图片任务，并在页面顶部展示常驻任务横幅，不强制自动打开抽屉。
- 横幅展示账户、导入类型、状态、真实文件级进度和继续/取消/放弃操作。
- 点击“图片导入”时若存在当前任务，直接打开既有任务；恢复时账户、类型和日期以任务元数据为准并锁定。
- 抽屉在 pending/processing 阶段允许关闭，任务继续执行；SSE 完成时，抽屉打开则加载结果，抽屉关闭则更新横幅并提示继续校对。
- SSE 断线、自动重连和漏事件不得影响最终状态，REST 查询是恢复兜底。
- 确认导入后刷新并切换到受影响账户的数据。

### R7. 错误、隐私和文档

- 用户必须能区分客户端 Axios 等待超时、服务端 Vision timeout、网络不可达、rate limit、未配置 Vision、模型不支持图片和文件级识别失败。
- 客户端 `ECONNABORTED` 不得继续显示为“服务端访问外部依赖超时”。
- 日志只记录 task_id、mode、account_id、文件序号、尝试次数、状态转移和低敏错误码；不得记录原图、base64、完整 prompt、模型原始响应、Key、Authorization 或完整 provider body。
- parse/识别阶段始终只读；重试、刷新、SSE 迟到事件和任务恢复均不得直接写入持仓或成交。
- 用户可见 API、交互和运行方式变化同步更新 `docs/full-guide.md`、`docs/full-guide_EN.md`、`docs/CHANGELOG.md` 和 `.trellis/spec/backend/portfolio-image-import.md`。

## Acceptance Criteria

- [ ] AC1：图片任务提交快速返回 HTTP 202；正常但耗时超过 30 秒的识别不会被 Web 提前判定失败，普通 API 请求仍可响应。
- [ ] AC2：任意账户/模式已有阻塞状态任务时，重复提交不会产生第二次 Vision 调用，并返回可恢复的 existing_task_id。
- [ ] AC3：页面刷新可恢复 `pending/processing/cancel_requested/review_required/committing/failed` 状态；服务重启后得到明确丢失提示且无残留槽位。
- [ ] AC4：SSE 能通知图片任务变化；SSE 不可用或漏事件时，REST 查询仍能恢复权威状态和结果。
- [ ] AC5：多图按顺序串行处理，展示真实第 N/M 张和尝试次数；部分失败保留成功结果，全部失败不展示空校对表。
- [ ] AC6：单次 Vision timeout=300 秒、瞬时错误最多重试一次、确定性错误不重试、整批 deadline=60 分钟均有确定性测试。
- [ ] AC7：pending 可立即取消；processing 取消后不启动下一张，取消确认前不释放槽位，迟到结果不覆盖终态。
- [ ] AC8：review_required 不自动过期；确认导入或放弃前刷新页面始终能恢复服务端结构化草稿。
- [ ] AC9：两个标签页同时编辑时，旧 revision 的草稿更新和 commit 返回稳定 409，不覆盖或提交另一标签页的新版本。
- [ ] AC10：commit 失败保留草稿并恢复 review_required；commit 成功只写入一次并清除当前任务。
- [ ] AC11：客户端等待超时与服务端上游错误显示准确、可操作且不泄露敏感信息。
- [ ] AC12：旧同步 parse 成功响应保持兼容并标记 deprecated；Web 只使用新异步 API。
- [ ] AC13：后端和 Web 测试覆盖提交、SSE、刷新恢复、防重、部分/全部失败、取消、deadline、草稿 revision、commit 和服务重启丢失路径。

## Out of Scope

- 不持久化任务、草稿、原图或模型原始响应；不支持跨服务重启恢复。
- 不新增 WebSocket、数据库表、迁移或外部任务队列。
- 不改变图片识别字段含义、持仓初始化账本语义或成交去重算法。
- 不更换当前 Vision 模型供应商。
- 不支持在同一任务中追加图片或单图原位重试。
