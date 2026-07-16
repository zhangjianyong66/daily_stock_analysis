# 搜索供应商调用审计规范

本规范约束搜索 provider 的真实调用计数、脱敏快照、故障生命周期、敏感 API 权限和跨层展示。目标是让本地账本能够独立核查供应商调用次数，同时不改变原有搜索 fallback 和分析结果。

## 1. Scope / Trigger

- 新增、替换或修改 Anspire、Bocha、MiniMax、Brave、SearXNG、Tavily、SerpAPI 等搜索 provider 的网络出口。
- 修改搜索重试、备用 Key、provider fallback、缓存或多实例策略。
- 修改 `search_api_calls`、`search_provider_faults`、`search_audit_gaps` 表及其 Repository / Service。
- 修改 `/api/v1/usage/search/*`、Web“搜索调用”页面、全局故障提示或管理员导出权限。
- 修改搜索错误分类、余额告警阈值、通知冷却或恢复语义。

## 2. Signatures

- 网络审计入口：`src.services.search_request_audit_service.audited_request_once(...) -> requests.Response`
- SDK 适配入口：`src.services.search_request_audit_service.AuditedRequestsSession`
- 业务上下文：`src.schemas.search_usage.SearchAuditContext`
- 仓储：`src.repositories.search_usage_repo.SearchUsageRepository`
- 服务：`src.services.search_usage_service.SearchUsageService`
- 数据表：
  - `search_api_calls`：每次真实外部 HTTP 请求一行。
  - `search_provider_faults`：按 provider、Key 指纹和错误类别保存故障与通知状态。
  - `search_audit_gaps`：保存审计写入失败后可恢复记录的缺口。
- HTTP API：
  - `GET /api/v1/usage/search/dashboard`
  - `GET /api/v1/usage/search/faults`
  - `GET /api/v1/usage/search/calls/{id}`
  - `GET /api/v1/usage/search/export.csv`
  - `GET /api/v1/usage/search/calls/{id}/export.json`

## 3. Contracts

- 计数真源是物理网络请求。自动重试、备用 Key、provider fallback 和 SearXNG 多实例尝试必须逐次记录；缓存、数据库读取、本地过滤、文章正文补抓和公共实例目录刷新不计数。
- 上层业务入口应传播 `business_search_id`、`logical_request_id`、`call_source`、股票和搜索维度；缺少上层上下文的 provider 直接调用使用 `call_source=direct`。
- 物理请求完成后同步写入审计记录，再把供应商结果返回上层。审计写入 fail-open，不得改变搜索成功、失败或 fallback 结果，但必须记录低敏错误并暴露 audit gap。
- 请求/响应先递归脱敏，再以明文 JSON 永久保存。请求上限 256 KiB，响应上限 2 MiB；超限保存预览、完整脱敏字节数和 SHA-256。
- 原始 API Key、Authorization、Cookie、Token、Secret、Signature、Webhook 不得进入数据库快照、普通日志、公开汇总、CSV、JSON 下载或通知。Key 和查询只保存 domain-separated HMAC 指纹。
- 错误分类先看供应商业务正文，再看 HTTP 状态。Anspire HTTP 401 正文明示免费额度或充值余额耗尽时必须是 `quota_exhausted`，不能是 `auth_invalid`。
- `quota_exhausted`、`auth_invalid`、`permission_denied`、`account_disabled` 首次失败立即激活；`rate_limited`、`timeout`、`connection_error`、`provider_5xx` 在 10 分钟内连续 3 次激活。真实成功清理同 Key 瞬时计数并恢复故障。
- 同一 provider、Key 指纹、错误类别的故障通知 24 小时最多一次；恢复后只通知一次。通知链路 best-effort，不阻塞搜索。
- dashboard 和 faults 不返回完整查询或快照，沿用用量页面可选认证。详情、复制、CSV 和单条 JSON 必须同时满足 `ADMIN_AUTH_ENABLED=true` 和有效管理员会话，没有桌面端例外。
- API 负责参数与 HTTP 错误边界，Service 负责筛选、状态机和 DTO，Repository 负责 SQLAlchemy 查询与事务，Web 只消费 API DTO。

## 4. Validation & Error Matrix

| 条件 | 结果 |
| --- | --- |
| 缓存命中或仅执行本地过滤 | 不新增 `search_api_calls` |
| 一次逻辑搜索发生 3 次 transport retry | 新增 3 条物理调用记录 |
| HTTP/API 成功但结果为 0 | 记录成功调用，不激活故障 |
| Anspire 401 且正文余额/额度为 0 | `quota_exhausted`，首次激活故障 |
| HTTP 401 且无额度耗尽语义 | `auth_invalid` |
| 同 Key 10 分钟内第 1/2 次 timeout | 仅累计瞬时计数，不激活故障 |
| 同 Key 10 分钟内第 3 次 timeout | 激活 `timeout` 故障 |
| 同 Key 后续真实请求成功 | 清空瞬时计数，恢复 active faults |
| 审计数据库写入失败 | 搜索结果保持原样，记录低敏 error 和 audit gap |
| `ADMIN_AUTH_ENABLED=false` 请求详情/导出 | HTTP 403 |
| 已启用认证但无有效管理员会话 | HTTP 401 |
| 已启用认证且管理员已登录 | 返回脱敏详情或导出文件 |

## 5. Good / Base / Bad Cases

- Good：同一业务搜索先用主 Key 失败、再用备用 Key 成功，两次请求分别落库，可按 business/logical ID 串联，并在成功后恢复对应瞬时故障。
- Good：超大响应仍按原 provider 解析并返回业务结果，审计详情显示截断、原始脱敏大小和 SHA-256。
- Base：一次 provider 请求成功且结果非空，写一条成功记录，页面统计物理请求数和业务搜索任务数。
- Base：供应商正常返回空结果，写成功记录但不产生余额或可用性告警。
- Bad：只在 `SearchResponse` 返回后记一条，导致 Tenacity retry、备用 Key 和多实例请求漏计。
- Bad：按 HTTP 401 直接显示“API Key 无效”，忽略正文中的额度耗尽业务语义。
- Bad：只在前端禁用详情按钮，服务端在管理员认证关闭时仍允许下载快照。
- Bad：普通日志打印完整 query、请求体或供应商响应，绕开详情 API 权限边界。

## 6. Tests Required

- transport 测试断言：每次 retry、备用 Key、provider fallback、SearXNG 多实例都产生独立记录；缓存和正文补抓不产生记录。
- 分类测试断言：Anspire 401 余额不足为 `quota_exhausted`；普通 401 为 `auth_invalid`；空结果不告警。
- 脱敏测试断言：嵌套对象、列表、URL 参数、请求头、响应头和错误文本均不含测试凭据；当前 API Key 被正文回显时也会替换。
- 截断测试断言：请求 256 KiB、响应 2 MiB 边界，以及 preview、size、SHA-256 字段。
- 持久化测试断言：旧数据库启动自动建表；同步写入发生在业务返回前；写入失败 fail-open 且 audit gap 可见。
- 故障测试断言：立即故障、10 分钟连续 3 次、24 小时通知冷却、成功恢复、配置移除恢复和一次恢复通知。
- API 测试断言：筛选、北京时间范围、分页、CSV 一致性，以及敏感端点 403/401/200。
- Web 测试断言：LLM/Search 双 Tab、详情权限禁用、筛选分页、下载、启动/焦点/60 秒故障轮询和 session dismissal。
- 目标回归至少包含：

```bash
python3 -m pytest \
  tests/test_search_usage_storage.py \
  tests/test_search_usage_service.py \
  tests/test_search_usage_api.py \
  tests/test_anspire_search.py \
  tests/test_search_tavily_provider.py \
  tests/test_search_serpapi_provider.py \
  tests/test_search_searxng.py -q
```

## 7. Wrong vs Correct

### Wrong：在逻辑返回层记一次

```python
response = provider.search(query)
record_search_call(provider=provider.name, success=response.success)
return response
```

这会把多次 retry、备用 Key 和实例 fallback 合并成一条，无法核账。

### Correct：在每次物理 transport 边界审计

```python
response = audited_request_once(
    method="POST",
    url=endpoint,
    api_key=api_key,
    context=current_search_audit_context(),
    request_kwargs=request_kwargs,
)
return parse_provider_response(response)
```

SDK 无法直接暴露每次网络请求时，应注入 `AuditedRequestsSession` 或复用 SDK 参数构造后通过统一审计 transport 发送；不能用逻辑层补记替代物理请求观察。
