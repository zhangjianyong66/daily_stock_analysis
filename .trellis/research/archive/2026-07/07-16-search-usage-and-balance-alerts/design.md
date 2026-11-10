# 搜索调用用量记录与余额告警设计

## 1. 设计目标与边界

本设计在不改变搜索 fallback 和分析主流程结果的前提下，为每次真实搜索供应商请求建立本地审计账本，并将故障状态贯通到 API、Web 全局提示和现有通知渠道。

核心原则：

1. **物理请求是真源**：记录点必须位于真实网络请求边界，而不是只在 `SearchService` 业务方法返回后记一条逻辑调用。
2. **规范化字段与原始快照并存**：汇总和筛选依赖结构化列，核账详情使用脱敏请求/响应快照。
3. **同步审计、业务 fail-open**：正常情况下先完成审计写入再返回搜索结果；审计失败不改变供应商结果，但缺口必须可见。
4. **供应商语义优先分类**：先解析响应正文中的额度、认证和权限语义，再使用 HTTP 状态兜底。
5. **敏感详情强鉴权**：汇总保持现有兼容，完整出入参和导出必须启用管理员认证且已登录。

## 2. 当前实现证据

- `src/search_service.py:60-78` 的 `_post_with_retry` / `_get_with_retry` 使用 Tenacity，单次业务调用最多产生 3 次真实 HTTP 请求；仅在 provider 返回后埋点会漏计重试。
- `src/search_service.py:157-272` 的 `BaseSearchProvider` 负责 Key 轮询和逻辑调用耗时，但不知道底层每次重试的完整响应。
- `src/search_service.py:1073-1242` 的 Anspire 先按 HTTP 401 拼接“API KEY 无效”，再返回业务错误，导致余额不足语义被错误分类。
- Tavily SDK 支持注入 `requests.Session`，可通过审计 Session 捕获一次真实请求；SerpAPI SDK 的 `construct_url()` 可复用参数构造，再由统一审计传输发送请求。
- `src/storage.py:742` 已有 `llm_usage`，但其字段和 Token 语义不适合承载搜索响应快照；搜索审计应使用独立领域表。
- `api/v1/endpoints/usage.py` 和 `apps/dsa-web/src/pages/TokenUsagePage.tsx` 提供现有 LLM 用量 API 与页面入口，应扩展为双 Tab 而不是改变 LLM 汇总契约。
- `api/middlewares/auth.py` 只在 `ADMIN_AUTH_ENABLED=true` 时保护 `/api/v1/*`；敏感详情端点需要额外依赖，在认证未启用时主动返回 403。
- `src/notification.py::NotificationService.send_with_results()` 已支持 `route_type="alert"`、dedup/cooldown key 和结构化发送结果，可复用现有通知渠道。
- `apps/dsa-web/src/components/layout/Shell.tsx` 是全局故障提示的稳定挂载点；`InlineAlert`、`Drawer` 可复用。

## 3. 数据流

```text
业务入口
  └─ SearchService 创建 business_search_id / logical_request_id / 调用上下文
       └─ Provider 选择 Key 与 endpoint
            └─ Audited HTTP transport（每次真实请求，包括 retry）
                 ├─ 捕获并脱敏 request snapshot
                 ├─ 发出 HTTP 请求
                 ├─ 捕获并脱敏 response / exception snapshot
                 ├─ 分类 provider error
                 ├─ 同步写 search_api_calls
                 └─ 更新 search_provider_faults / audit health
                      └─ best-effort 调度外部故障或恢复通知

API
  ├─ 汇总/分页/故障状态（兼容现有可选认证）
  └─ 详情/CSV/JSON（强制管理员认证）

Web
  ├─ Usage Analysis: LLM Tab + Search Tab
  └─ Shell 轮询 active faults → 全局 InlineAlert
```

## 4. 后端领域结构

### 4.1 Schema 与上下文

新增 `src/schemas/search_usage.py`：

- `SearchAuditContext`
  - `business_search_id`
  - `logical_request_id`
  - `call_source`
  - `operation`
  - `stock_code` / `stock_name`
  - `dimension` / `lookback_days`
  - `provider_attempt`
- `SearchPhysicalRequestResult`
  - 网络边界捕获的规范化结果
- `SearchErrorCategory`
  - PRD R4 的稳定枚举

使用 `contextvars.ContextVar` 传播审计上下文：

- `search_comprehensive_intel()` 为整次调用创建一个 `business_search_id`，每个维度创建独立 `logical_request_id`。
- `search_stock_news()` 的 provider fallback 共享一个 `logical_request_id`，不同 provider 使用不同 `provider_attempt`。
- 直接调用 provider 且没有上层上下文时，由 provider 边界生成 `call_source=direct` 的默认 ID，避免漏记。
- 物理请求序号由当前逻辑请求上下文中的线程安全计数器生成；Tenacity 每次实际执行 transport 都获取新序号。

### 4.2 统一审计传输

新增 `src/services/search_request_audit_service.py`，提供：

- `audited_request_once(...) -> requests.Response`
- `AuditedRequestsSession(requests.Session)`，供 Tavily SDK 注入
- 请求/响应快照构建、脱敏、大小限制、哈希和 Request ID 提取
- Key HMAC 指纹和 query HMAC
- 错误分类与同步持久化

集成方式：

- `_get_with_retry` / `_post_with_retry` 的每次 Tenacity attempt 调用 `audited_request_once`，Anspire、Bocha、MiniMax 和带 retry 的 SearXNG 因此逐次记账。
- Brave 和 SearXNG 非 retry 请求直接使用 `audited_request_once`。
- Tavily 创建 `AuditedRequestsSession` 并注入 `TavilyClient(session=...)`，保持 SDK 请求/响应解析行为。
- SerpAPI 继续复用 `GoogleSearch(params).construct_url()`，但通过审计 transport 发送 GET 并解析 JSON，避免 SDK 内部请求绕过审计。
- `fetch_url_content()`、SearXNG 公共实例列表刷新继续使用普通网络调用，不计入搜索供应商账本。

### 4.3 脱敏与快照契约

扩展 `src/utils/sanitize.py`，新增专用于外部调用快照的结构化 sanitizer，复用现有敏感键和 token 模式：

- 映射键命中 Authorization/API Key/Cookie/Token/Secret/Signature/Webhook 等时替换为 `[REDACTED]`。
- URL 保留 scheme/host/path 和非敏感查询参数；敏感查询参数仅替换值，不把整条 URL 删除。
- 字符串值再次扫描 Bearer、常见 token 和敏感赋值模式。
- 请求头和响应头使用 allowlist；Request ID、Trace ID、Content-Type、RateLimit/Usage 类头可以保留，Set-Cookie 等永不保留。
- JSON 可解析时保存结构化对象；不可解析时保存脱敏文本与 content type。
- 先构造完整脱敏 JSON，再计算 UTF-8 字节数和 SHA-256，最后按请求 256 KiB、响应 2 MiB 限制截断。

普通日志仍只写调用 ID、供应商、状态和安全化摘要，不输出完整快照，保持 `.trellis/spec/backend/logging-guidelines.md` 契约。

### 4.4 持久化模型

在 `src/storage.py` 新增 ORM 表，数据库访问放入 `src/repositories/search_usage_repo.py`。

#### `search_api_calls`

每次真实外部搜索请求一行，主要字段：

- 身份关联：`id`、`business_search_id`、`logical_request_id`、`trace_id`
- 调用上下文：`provider`、`endpoint`、`http_method`、`call_source`、`operation`、`stock_code`、`stock_name`、`dimension`、`lookback_days`
- 尝试信息：`provider_attempt`、`physical_attempt`、`key_fingerprint`、`query_hmac`
- 结果：`success`、`http_status`、`provider_code`、`provider_request_id`、`duration_ms`、`result_count`、`error_category`、`error_summary`
- 请求快照：`request_snapshot_json`、`request_size_bytes`、`request_truncated`、`request_sha256`
- 响应快照：`response_snapshot_json`、`response_size_bytes`、`response_truncated`、`response_sha256`
- 时间：`requested_at`、`completed_at`

索引以真实查询路径为准：

- `requested_at`
- `(provider, requested_at)`
- `(key_fingerprint, requested_at)`
- `(call_source, requested_at)`
- `(success, requested_at)`
- `business_search_id`、`logical_request_id`

#### `search_provider_faults`

保存当前故障与通知冷却：

- 唯一键：`provider + key_fingerprint + error_category`
- `active`、`severity`、`first_seen_at`、`last_seen_at`、`resolved_at`
- 瞬时错误窗口和连续计数
- `last_notified_at`、`last_notification_status`、`recovery_notified_at`
- 最近安全化摘要和关联调用 ID

#### `search_audit_gaps`

当审计写入失败时，进程内健康监控累计缺口；数据库恢复后的首次成功写入补记：

- `lost_count`
- `first_failed_at` / `last_failed_at` / `recorded_at`
- 安全化失败原因

若进程在数据库恢复前直接退出，无法把缺口写入同一数据库，普通 error 日志是最后兜底；UI 同时展示当前进程内未落库计数。

新表由现有 `Base.metadata.create_all()` 自动创建；旧版本回滚后会忽略这些表，不需要破坏性迁移。

### 4.5 Repository 与 Service

`SearchUsageRepository` 负责：

- 单条调用同步写入
- 汇总、breakdown、分页筛选
- CSV 流式查询
- 单条详情读取
- fault upsert / resolve / notification cooldown
- audit gap 写入

`SearchUsageService` 负责：

- 日期、筛选和分页归一化
- 错误分类结果到 fault 状态机的转换
- 供应商总体状态聚合
- 当前配置 Key 指纹 reconciliation
- DTO 序列化和敏感详情授权后的导出
- 通知文案与 best-effort 调度

### 4.6 故障状态机

#### 立即故障

`quota_exhausted`、`auth_invalid`、`permission_denied`、`account_disabled`：第一次失败即 upsert active fault。

#### 阈值故障

`rate_limited`、`timeout`、`connection_error`、`provider_5xx`：同 provider/key 在滚动 10 分钟窗口内连续 3 次失败后 active。一次成功清空对应瞬时计数并 resolve。

#### 不告警

- HTTP/API 成功但结果数组为空
- 供应商返回结果后被本地过滤为空
- 缓存命中

#### 恢复

- 同 provider/key 真实请求成功：resolve 该 Key 的 active faults。
- 配置保存或 SearchService 重建时调用 reconciliation；已移除 Key 的 faults resolve。
- 恢复后仅发送一次 recovery notification。

供应商总体状态由当前已配置 Key 和 active faults 动态聚合，不单独保存第二份真源。

### 4.7 通知

复用 `NotificationService.send_with_results(..., route_type="alert")`：

- fault 表先执行固定 24 小时冷却判断，避免依赖全局静态通知冷却值。
- `dedup_key` / `cooldown_key` 使用 provider、Key 指纹、错误类别和 fault 状态。
- 通知调度在审计事务完成后 best-effort 执行，不让通知渠道延迟阻塞搜索响应。
- 发送结果回写 fault 表；失败只记录，不影响搜索。

## 5. API 设计

在现有 `/api/v1/usage` 下扩展，保留 LLM 端点不变。

### 5.1 非敏感汇总端点

- `GET /api/v1/usage/search/dashboard`
  - 参数：预设 period 或 `from/to`、provider、source、success、error_category、key_fingerprint、page、page_size
  - 返回：审计起始时间、汇总、breakdowns、分页摘要、active faults、audit health
- `GET /api/v1/usage/search/faults`
  - 返回当前 active faults、供应商总体状态和 audit health，供 Shell 60 秒轮询

这些端点不返回完整查询词、请求/响应快照或可逆 Key 信息，沿用当前可选认证行为。

### 5.2 强认证敏感端点

- `GET /api/v1/usage/search/calls/{id}`：完整脱敏详情
- `GET /api/v1/usage/search/calls/{id}/export.json`：单条 JSON 下载
- `GET /api/v1/usage/search/export.csv`：按筛选条件流式导出摘要

新增共享依赖 `require_enabled_admin_session(request)`：

- `ADMIN_AUTH_ENABLED=false` → 403
- 已启用但 Cookie 无效/缺失 → 401
- 有效管理员会话 → 放行
- 不提供桌面模式例外

Endpoint 只做参数接收、依赖校验、service 调用和错误映射；CSV 使用 `StreamingResponse`，不一次性加载全部永久账本。

## 6. Web 设计

### 6.1 用量分析页面

- 将 `TokenUsagePage` 重构/重命名为 `UsageAnalysisPage`，路由 `/usage` 不变。
- 顶部保留统一时间范围控件；LLM Tab 沿用现有 `/usage/dashboard`。
- Search Tab 使用新的 search dashboard API。
- 搜索摘要卡、供应商/Key/来源 breakdown、服务端分页表格和筛选器均使用后端规范化字段。
- 详情抽屉按需请求敏感详情；未满足管理员权限时不请求，并显示开启认证提示。
- CSV/JSON 下载走 blob download；服务端 Content-Disposition 决定文件名。
- 现有 `toCamelCase` 继续作为 API 边界唯一字段转换点，组件不自行解析 snake_case。

### 6.2 全局故障提示

新增 `SearchProviderFaultBanner` 挂载在 `Shell` 主内容顶部：

- 首次渲染请求 faults。
- `window.focus` 时刷新。
- 可见期间每 60 秒轮询；卸载时清理定时器。
- 使用 `sessionStorage` 记录当前会话已关闭 fault；severity 升级或 fault identity 改变时重新显示。
- 只展示安全摘要和“查看搜索调用”入口，不展示原始查询/响应。

## 7. 兼容性与迁移

- 现有 `/api/v1/usage/summary`、`/dashboard` 响应保持兼容，避免破坏已有客户端。
- 新搜索端点独立增加，不向 LLM Token 总量混入搜索调用数。
- 新表自动创建；无历史回填，`audit_started_at` 取首条记录时间。
- 新审计 transport 必须保持各 provider 的超时、重试、fallback、结果解析和缓存语义。
- 回滚旧代码时新表保留但无人读取，不影响旧版本运行；重新升级后继续使用已有账本。

## 8. 风险与缓解

| 风险 | 缓解 |
| --- | --- |
| SQLite 同步写增加请求延迟或锁竞争 | 单条短事务、WAL、现有 busy timeout/retry；快照序列化在事务外完成 |
| 完整明文快照带来隐私风险 | 深度脱敏、强认证详情、大小上限、文档警告；普通日志不输出快照 |
| 底层 retry 漏记 | 将埋点放进每次 transport attempt，并用三次连接失败测试断言三条记录 |
| 余额不足仍被 401 误分类 | 分类器业务语义优先，增加 Anspire 原始反例回归 |
| 通知风暴 | fault 表固定 24 小时冷却 + 现有通知 noise control |
| 审计写失败导致账本不完整 | fail-open 但记录 audit health/gap，UI 显示缺口 |
| CSV 永久账本过大 | 服务端流式导出，快照不进入 CSV |
| 配置移除 Key 后故障不恢复 | 配置保存、SearchService 初始化和故障查询前执行 Key reconciliation |

## 9. 回滚方案

1. 回滚搜索审计 transport、API 和 Web 代码。
2. 保留 `search_api_calls`、`search_provider_faults`、`search_audit_gaps` 表，不执行自动删表，避免丢失已记录核账证据。
3. 旧代码忽略新增表，搜索流程恢复原行为。
4. 如需彻底清理，维护者可在确认备份后手工删除新表；不把删表作为常规回滚步骤。
