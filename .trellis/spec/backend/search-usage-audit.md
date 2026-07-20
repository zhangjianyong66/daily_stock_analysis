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
- 大盘新闻入口：`src.market_analyzer.MarketAnalyzer.search_market_news() -> list[dict]`
- 综合情报入口：`src.search_service.SearchService.search_comprehensive_intel(stock_code, stock_name, max_searches=3, *, call_source="analysis") -> dict[str, SearchResponse]`
- 普通股票分组规则：`src.services.stock_search_intelligence.enabled_stock_dimensions(...)`、`build_stock_group_query(...)`、`classify_stock_evidence(...)`
- 共享状态：`SearchService._intel_group_cache` 与 `SearchService._intel_group_inflight`，仅限当前 Python 进程，不持久化、不跨容器。
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
- 显式配置的 SearXNG 是独立审计边界：DSA → SearXNG 的一次 `/search` 记一条 `search_api_calls`；SearXNG 内部引擎扇出不逐条导入 DSA 数据库。仓库不内置或自动启动私有 SearXNG。
- 单市场大盘复盘必须按 profile 顺序去重并合并三个主题，只执行一次 `search_stock_news(call_source="market_review", max_results=6)`；Provider 候选上限为 12。失败或成功空结果都不得追加隐式查询。
- ETF 综合情报在 Anspire 可用时按 `fresh_events` / `analysis` 两个逻辑组调用，冷启动最多两次物理请求且禁用 transport retry；缓存命中、本地分流和可信准入不计数。任一组失败不得自动调用 SearXNG 或其他 Provider。
- 非 ETF、`call_source=analysis` 的标准 Pipeline 在 Anspire 可用时按市场保留既有五维：A 股近期组为最新消息/风险/公告、分析组为机构分析/业绩；海外近期组为最新消息/风险、分析组为机构分析/业绩/行业。健康冷启动最多两次物理请求，固定 `top_k=18`、10 秒 timeout、禁用 transport retry。Anspire 成功但无可信数据不 fallback；只有物理失败的组按既有逻辑维度调用非 Anspire Provider，每次 fallback 继续逐次审计。`call_source=agent` 保持逐维请求。
- ETF 与普通股票的已准入非空分组结果使用进程级共享缓存：近期 TTL 15 分钟、分析 TTL 6 小时。键必须区分路径类型、模板版本、股票身份、组、窗口、语言和启用维度；读取返回深拷贝。失败、空结果、`no_trusted_data` 和 Provider 原始响应不缓存。
- 同键并发 miss 使用 singleflight：一个 owner 发出物理请求，等待者只读取 owner 写入的可信缓存；owner 失败、空结果或等待超时时，等待者本轮返回空且不立即重试。owner 必须在 `finally` 释放 event。缓存命中和 waiter 均不得新增 `search_api_calls`。
- 同一 URL 在组内和跨组只能进入一个最具体维度；近期结果拒绝未知或超窗日期，分析结果保留未知日期但拒绝已知的 180 天窗外日期。
- ETF 底层映射只接受股票索引中 `asset_type=etf` 的受控别名，或代码内白名单认可的无歧义名称词；不能把任意 `xxxETF` 去掉 `ETF` 后的 `xxx` 自动视为可信底层。未知名称必须降为 `generic_etf` 并关闭 `underlying_driver`。
- `news_intel` 隔离是显式证据决策：`save_news_intel()` 遇到已隔离 URL 时不得更新内容、Provider 或解除隔离。只有 `rollback_news_intel_quarantine(batch=...)` 可以恢复该批次，避免其他 Provider 的 URL 碰撞复活旧污染标题。
- 上层业务入口应传播 `business_search_id`、`logical_request_id`、`call_source`、股票和搜索维度；缺少上层上下文的 provider 直接调用使用 `call_source=direct`。
- 物理请求完成后同步写入审计记录，再把供应商结果返回上层。审计写入 fail-open，不得改变搜索成功、失败或 fallback 结果，但必须记录低敏错误并暴露 audit gap。
- 请求/响应先递归脱敏，再以明文 JSON 永久保存。请求上限 256 KiB，响应上限 2 MiB；超限保存预览、完整脱敏字节数和 SHA-256。
- 原始 API Key、Authorization、Cookie、Token、Secret、Signature、Webhook 不得进入数据库快照、普通日志、公开汇总、CSV、JSON 下载或通知。Key 和查询只保存 domain-separated HMAC 指纹。
- 错误分类先看供应商错误语义，再看 HTTP 状态。HTTP 非 2xx 可检查完整错误正文；HTTP 2xx 只能检查顶层 `message/msg/error/errors/error_message/error_description/detail/reason` 和 `base_resp` 错误字段，不得扫描 `results`、`organic`、`web.results`、`data.webPages.value` 等结果集合或完整响应文本。Anspire HTTP 401 正文明示免费额度或充值余额耗尽时必须是 `quota_exhausted`，不能是 `auth_invalid`。
- `quota_exhausted`、`auth_invalid`、`permission_denied`、`account_disabled` 首次失败立即激活；`rate_limited`、`timeout`、`connection_error`、`provider_5xx` 在 10 分钟内连续 3 次激活。真实成功清理同 Key 瞬时计数并恢复故障。
- 同一 provider、Key 指纹、错误类别的故障通知 24 小时最多一次；恢复后只通知一次。通知链路 best-effort，不阻塞搜索。
- dashboard 和 faults 不返回完整查询或快照，沿用用量页面可选认证。详情、复制、CSV 和单条 JSON 必须同时满足 `ADMIN_AUTH_ENABLED=true` 和有效管理员会话，没有桌面端例外。
- API 负责参数与 HTTP 错误边界，Service 负责筛选、状态机和 DTO，Repository 负责 SQLAlchemy 查询与事务，Web 只消费 API DTO。

## 4. Validation & Error Matrix

| 条件 | 结果 |
| --- | --- |
| 缓存命中或仅执行本地过滤 | 不新增 `search_api_calls` |
| 单市场大盘复盘新闻搜索 | 健康路径新增 1 条，`call_source=market_review`，Provider `top_k=12` |
| ETF Anspire 冷启动综合搜索 | 最多新增 2 条调用记录，维度为 `fresh_events` / `analysis` |
| ETF/普通股票两组可信缓存均命中 | 不新增 `search_api_calls` |
| 仅近期组 TTL 过期 | 只刷新 `fresh_events`，新增 1 条物理调用记录 |
| 同键并发冷启动 | 每个启用组只有 owner 新增 1 条；waiter 为 0 条 |
| 非 ETF 标准 Pipeline Anspire 健康冷启动 | 最多新增 2 条，维度为 `fresh_events` / `analysis` |
| 非 ETF Anspire 组成功但无可信结果 | 记录该次成功物理调用，不追加逐维 fallback |
| 非 ETF Anspire 某组物理失败 | 仅该组的启用维度走非 Anspire fallback，真实请求逐次记录 |
| Agent 六维综合搜索 | 保持既有逐维请求和 `call_source=agent` 语义 |
| 无索引元数据的 `未知ETF` / 非白名单名称 | `generic_etf`，不开放底层驱动 |
| 新 Provider 结果与已隔离 URL 相同 | 保持原记录隔离且内容不变，不自动恢复 |
| 一次 DSA → 显式 SearXNG 聚合请求 | 新增 1 条 `SearXNG` 调用记录；内部引擎扇出不进入 DSA 表 |
| 一次逻辑搜索发生 3 次 transport retry | 新增 3 条物理调用记录 |
| HTTP/API 成功但结果为 0 | 记录成功调用，不激活故障 |
| HTTP 2xx 且结果正文含余额、认证、权限或限流词 | 记录成功调用；结果内容不得参与错误分类 |
| HTTP 2xx 且顶层错误字段含额度语义 | 按 `quota_exhausted` 记录失败 |
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
- Good：两个独立 `SearchService` 同时分析同一 ETF，首个实例成为 owner，每组只发一次 Anspire 请求；第二个实例等待并读取深拷贝，不产生调用审计行。
- Good：普通股票近期组物理失败、分析组成功时，只对最新消息/风险/公告执行 Provider fallback，机构分析/业绩不重复请求。
- Good：超大响应仍按原 provider 解析并返回业务结果，审计详情显示截断、原始脱敏大小和 SHA-256。
- Good：搜索结果正文讨论“余额不足”或 `quota exhausted` 时仍记录为成功，只有顶层错误元数据或失败 HTTP 正文参与错误分类。
- Good：宽基、策略或商品 ETF 没有索引元数据，但名称命中受控词时建立保守底层映射；`未知ETF` 保持 `generic_etf`。
- Base：一次 provider 请求成功且结果非空，写一条成功记录，页面统计物理请求数和业务搜索任务数。
- Base：供应商正常返回空结果，写成功记录但不产生余额或可用性告警。
- Base：单市场大盘三个主题合并为一个查询，最终最多 6 条，供应商请求最多 12 个候选。
- Bad：只在 `SearchResponse` 返回后记一条，导致 Tenacity retry、备用 Key 和多实例请求漏计。
- Bad：按 HTTP 401 直接显示“API Key 无效”，忽略正文中的额度耗尽业务语义。
- Bad：把完整成功响应序列化后扫描错误关键词，导致财经公告或技术文章中的“余额 0”“额度不足”“unauthorized”等内容激活供应商故障。
- Bad：只在前端禁用详情按钮，服务端在管理员认证关闭时仍允许下载快照。
- Bad：普通日志打印完整 query、请求体或供应商响应，绕开详情 API 权限边界。
- Bad：把缓存放回 `SearchService` 实例字段，导致 Pipeline 每次新建 service 后短期重复分析仍完整扣费。
- Bad：singleflight owner 失败后 waiter 立即成为新 owner，形成同一并发波次的请求风暴。
- Bad：对所有 ETF 直接执行 `name.removesuffix("ETF")` 并开启底层驱动，或用后续 URL 碰撞自动清除历史隔离标记。

## 6. Tests Required

- transport 测试断言：每次 retry、备用 Key、provider fallback、SearXNG 多实例都产生独立记录；缓存和正文补抓不产生记录。
- 分类测试断言：Anspire 401 余额不足为 `quota_exhausted`；普通 401 为 `auth_invalid`；空结果不告警；HTTP 2xx 搜索结果正文包含各类错误关键词仍成功；HTTP 2xx 顶层业务错误仍按语义分类。
- 脱敏测试断言：嵌套对象、列表、URL 参数、请求头、响应头和错误文本均不含测试凭据；当前 API Key 被正文回显时也会替换。
- 截断测试断言：请求 256 KiB、响应 2 MiB 边界，以及 preview、size、SHA-256 字段。
- 持久化测试断言：旧数据库启动自动建表；同步写入发生在业务返回前；写入失败 fail-open 且 audit gap 可见。
- ETF 准入测试断言：索引别名和受控名称规则可建立映射；任意/未知名称降为 `generic_etf`；普通价格涨跌复述和仅 URL 命中产品代码的内容拒绝。
- 请求压缩测试断言：大盘只调用一次且 `max_results=6/top_k=12`；ETF 跨实例命中为 0 次、仅近期过期为 1 次；非 ETF Pipeline 五维健康路径为 2 次、成功空结果不 fallback、物理失败仅降级失败组；Agent 路径保持逐维调用。
- singleflight 测试断言：跨两个 `SearchService` 的同键并发冷启动每组只有一个 owner；成功 waiter 复用深拷贝，owner 失败时 waiter 不形成请求风暴，所有异常路径释放 inflight event。
- 隔离测试断言：默认读取排除隔离记录；同 URL 的其他 Provider 写入不能修改或恢复隔离记录；只有显式批次 rollback 恢复可见。
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
  tests/test_search_searxng.py \
  tests/test_market_strategy.py \
  tests/test_etf_search_intelligence.py \
  tests/test_stock_search_intelligence.py \
  tests/test_search_service_concurrency.py -q
```

## 7. Wrong vs Correct

### Wrong：扫描完整成功响应识别供应商错误

```python
semantic_text = json.dumps(payload, ensure_ascii=False).lower()
if "余额不足" in semantic_text:
    return False, "quota_exhausted"
```

搜索结果本身是非可信业务数据，正文可能正常讨论余额、额度、认证或限流，不能作为供应商账户状态证据。

### Correct：按传输状态隔离错误元数据和结果数据

```python
if status is not None and 200 <= status < 300:
    semantic_payload = {key: payload.get(key) for key in ERROR_FIELDS if key in payload}
else:
    semantic_payload = payload  # 失败响应正文可用于区分额度、认证等语义
```

HTTP 2xx 业务错误通过顶层错误字段和错误码识别，正常结果集合永远不进入关键词扫描。

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

### Wrong：实例缓存或 waiter 失败后立即重试

```python
self._intel_cache = {}
if not event.wait(timeout=30):
    return provider.search(query)
```

这会让不同 Pipeline 实例无法复用，并在上游故障时放大并发请求。

### Correct：进程共享可信缓存与 owner/waiter

```python
cached, owner, event = SearchService._reserve_intel_group_fill(cache_key)
if cached is not None:
    return deepcopy(cached)
if not owner:
    return SearchService._wait_for_intel_group(cache_key, event) or {}
try:
    admitted = search_and_admit_once()
    SearchService._put_intel_group_cache(cache_key, admitted, ttl_seconds=ttl)
    return admitted
finally:
    SearchService._release_intel_group_fill(cache_key, event)
```

### Wrong：从任意 ETF 名称猜底层并自动恢复隔离

```python
underlying_terms = (stock_name.removesuffix("ETF"),)
existing.quarantined_at = None  # 仅因另一个 Provider 返回相同 URL
```

### Correct：受控映射与显式恢复

```python
underlying_terms = trusted_index_aliases or controlled_name_rule_terms(stock_name)
if not underlying_terms:
    profile = "generic_etf"

if existing.quarantined_at is not None:
    return  # 仅 rollback_news_intel_quarantine(batch=...) 可以恢复
```
