# 自建 SearXNG 分层搜索降本：技术设计

## 1. 设计目标

本设计解决的核心问题不是“增加一个搜索 Provider”，而是“把 A 股情报搜索的付费调用从固定发生改为仅在免费结果不合格时发生”。最小可行机制由三部分组成：私有 SearXNG、显式市场/成本路由、Anspire 物理请求预算保护。

## 2. 总体架构

```text
A 股搜索入口
  ├─ search_stock_news
  ├─ search_stock_events
  └─ search_comprehensive_intel
          │
          ▼
  SearchRoutingPolicy(searxng_first_cn)
          │
          ├─ 非 A 股 ───────────────► legacy Provider 链
          │
          └─ A 股 / A 股 ETF
                  │
                  ▼
        私有 SearXNG（6 秒/次）
                  │
                  ▼
        现有过滤、排序、准入判断
             │             │
          合格返回       不合格/失败
                             │
                             ▼
               AnspireBudgetGate（30/50）
                             │
                   ┌─────────┴─────────┐
                   │                   │
                允许请求            预算阻断
                   │                   │
                   ▼                   ▼
               Anspire          返回 SearXNG 最佳结果
```

## 3. 部署边界

### 3.1 Compose 服务

- 在现有 `docker/docker-compose.yml` 增加 `searxng` 服务，使用官方镜像的固定版本或 digest。
- 服务只加入 Compose 默认网络，不配置 `ports`；容器内监听 8080，DSA 使用 `http://searxng:8080`。
- 不增加 `depends_on: condition: service_healthy` 作为 server 启动硬依赖。SearXNG 不可用时 DSA 仍可启动并在运行时 fallback。
- 配置只读挂载到 `/etc/searxng/settings.yml`，缓存目录使用命名 volume 或受控宿主目录；最终选型以官方固定镜像验证为准。
- 资源上限为 512 MiB；日志沿用 Compose `json-file` 轮转策略。

### 3.2 SearXNG 配置

- `SEARXNG_SECRET` 从 `.env` 注入，仓库模板仅放空值或生成说明。
- `SEARXNG_LIMITER=false`、`SEARXNG_PUBLIC_INSTANCE=false`，因此首期无需 Valkey/Redis。
- `search.formats` 包含 `json`，默认语言为 `zh-CN`。
- 通过官方默认设置继承/引擎保留语法，仅保留百度、Bing、Bing News、DuckDuckGo；固定镜像后用容器启动校验确认准确 engine identifier。
- 关闭包含 URL query string 的 HTTP access log；保留引擎失败、超时、熔断和耗时日志。
- 健康检查只访问容器本地根路径；实际 `/search?...&format=json` 作为部署 smoke，而不是周期 healthcheck。

## 4. 配置契约

建议新增以下配置：

| 配置 | 默认值 | 语义 |
| --- | --- | --- |
| `SEARCH_ROUTING_MODE` | `legacy` | `legacy` 保持现状；`searxng_first_cn` 仅对 A 股/ETF 启用分层路由 |
| `SEARXNG_REQUEST_TIMEOUT_SECONDS` | `6` | 私有 SearXNG 单次请求硬上限；必须为正数 |
| `SEARCH_INTEL_TOTAL_TIMEOUT_SECONDS` | `30` | 单股低成本情报搜索总预算；`0` 不建议但可表示关闭总预算 |
| `ANSPIRE_DAILY_WARNING_REQUESTS` | `30` | 北京时间每日物理请求预警阈值；`0` 关闭预警 |
| `ANSPIRE_DAILY_HARD_LIMIT_REQUESTS` | `50` | 北京时间每日物理请求硬上限；`0` 关闭硬上限 |
| `SEARXNG_SECRET` | 空 | SearXNG 官方容器 secret，只供容器使用，不回显到 Web 配置详情 |

校验规则：路由模式非法时 warning + `legacy`；数值不得为负；两个 Anspire 阈值均启用时 warning 阈值必须小于硬上限，否则配置校验失败或回退到安全默认值。`SEARXNG_SECRET` 作为敏感字段处理，不进入普通日志、导出或设置页面明文回显。

## 5. 搜索路由设计

### 5.1 单一策略入口

在 `SearchService` 内增加一个私有路由策略/helper，而不是复制三套入口逻辑。构造函数保留现有 `_providers` 供 legacy 使用，同时保存明确的 `SearXNG` 与 `Anspire` 引用供低成本路径调用。

建议职责拆分：

- `_market_for_search(stock_code) -> Optional[str]`：复用现有市场解析函数。
- `_should_use_searxng_first(stock_code) -> bool`：只判断配置模式与市场。
- `_search_cn_dimension_with_fallback(...) -> SearchResponse`：执行 SearXNG、准入、预算、Anspire fallback。
- `_is_searxng_result_acceptable(dimension, response, stats) -> bool`：集中表达关键/分析维度准入标准。

`search_stock_news`、`search_stock_events`、`search_comprehensive_intel` 调用同一 helper。Agent 工具、AlphaSift 和 pipeline 已通过这些公开入口消费结果，因此无需各自增加路由分支。

### 5.2 类别与结果准入

- `latest_news`、`announcements`、`risk_check` 使用 `categories=news`；其合格条件是过滤后至少 1 条 direct result，且发布时间符合各自窗口。
- `market_analysis`、`earnings`、`industry` 使用 `categories=general`；其合格条件是过滤后至少 1 条结果。
- `search_stock_news` 按关键新闻维度处理；`search_stock_events` 按关键事件维度处理。
- 准入必须发生在现有 `_filter_news_response`、`_rank_news_response`、`_filter_ranked_news_for_context` 之后。不得新增另一套相关性算法。
- 若 SearXNG 有部分结果但不满足 direct 标准，保留为 `best_effort_response`；Anspire 失败或预算阻断时返回该结果并通过诊断标注限制。

### 5.3 时间预算

- 私有 SearXNG 在低成本模式中调用单次 transport，不使用当前 `_get_with_retry` 的三次重试；公共实例 legacy 逻辑保持不变。
- 每个维度调用前检查单股 deadline；剩余预算不足时不再启动新请求。
- 调用超时取 `min(SEARXNG_REQUEST_TIMEOUT_SECONDS, remaining_budget)`。
- Anspire fallback 同样受剩余总预算约束；不得在总预算耗尽后继续产生付费调用。
- 当前主流程 `max_searches=5` 执行的五个维度保持串行，保留现有顺序与 0.5 秒节流是否必要应在实现时根据 SearXNG 延迟重新评估，但不得让固定 sleep 导致超过总 deadline；可选的 `industry` 第六维度在调用方提高上限时沿用同一 deadline。

## 6. Anspire 预算控制

### 6.1 控制面与审计真源

`search_api_calls` 继续记录实际已经发出的网络请求。为保证硬上限跨线程、跨进程、跨重启生效，新增轻量控制表（建议名 `search_provider_daily_budgets`）：

- `provider`
- `budget_date`（北京时间日期）
- `reserved_requests`
- `warning_notified_at`
- `hard_limit_notified_at`
- `updated_at`

`(provider, budget_date)` 唯一。该表只用于原子预留预算，不替代真实用量审计。

### 6.2 物理请求预留

- 在每次 Anspire 物理 transport 发送前调用 `SearchPaidBudgetService.reserve(provider="Anspire")`。
- Repository 使用单事务原子插入/递增；只有 `reserved_requests < hard_limit` 时递增成功。
- 每个 Tenacity retry 都会再次经过预留，因此按真实物理尝试消耗预算。
- 预留成功后即计入安全上限，即使连接在服务器接收前失败也不回退计数；这是有意的保守成本保护。
- 预留失败抛出明确的 `SearchBudgetExceeded`，异常不属于 transient retry 类型，因而不会继续重试。
- 预算服务/数据库不可用时，对 Anspire 付费请求 fail-closed；SearXNG 和整体分析继续 fail-open。

### 6.3 告警与诊断

- 第一次达到 warning 阈值发送一次 best-effort 告警；第一次触碰硬上限发送一次告警。
- 告警复用现有通知发送边界，不阻塞搜索，不包含 query、Key 或完整请求体。
- 预算阻断不是外部 HTTP 请求，不写 `search_api_calls`；通过 ProviderRun/运行诊断记录 `budget_blocked`、当前预留数和硬上限。
- 用量页面的 Anspire 真实调用数来自 `search_api_calls`；控制表只用于诊断预算状态，首期不新增独立 Web 页面。

## 7. 审计边界

### 7.1 DSA 层

- 每次 DSA → SearXNG `/search` 调用仍通过 `audited_request_once`，provider 为 `SearXNG`，credential identity 使用内部 base URL 指纹。
- `search_api_calls` 的一行代表一次 DSA 调用自建聚合服务，不代表 SearXNG 内部上游数量。
- Anspire 仍按每个 transport retry 逐次审计。

### 7.2 SearXNG 层

- 百度、Bing、Bing News、DuckDuckGo 的引擎级扇出、超时和失败保留在 SearXNG 容器日志。
- 不把内部引擎日志同步进 DSA 数据库，不维护自定义 SearXNG fork。
- `AGENTS.md`、`.trellis/spec/backend/search-usage-audit.md` 和中英文指南必须说明该基础设施边界，避免后续误把一条 SearXNG 记录解释为一个上游引擎请求。

## 8. 数据流与状态

```text
Config / Web Settings
  → Config dataclass + registry validation
  → SearchService constructor
  → Routing policy
  → SearXNG transport audit
  → filter/rank/admission
  → optional Anspire budget reserve
  → Anspire transport audit
  → SearchResponse / diagnostics / report persistence
```

预算控制表由 SQLAlchemy 启动建表机制创建；不修改已有 `search_api_calls` 数据。旧部署未启用新路由时不会创建额外外部依赖，也不改变历史报告结构。

## 9. 兼容性与迁移

- 默认 `legacy`，因此代码升级不自动改变所有用户的 Provider 成本/质量语义。
- 当前本机部署启用时，在 `.env` 设置低成本模式、私有 URL、30/50 阈值和 SearXNG secret；真实 `.env` 不提交。
- 公共 SearXNG 自动发现继续保留给 legacy 用户；低成本模式要求至少一个显式自建 URL，否则配置校验 warning 并回退 legacy，避免把不稳定公共实例当主源。
- Web/API 报告载荷不新增必需字段；运行诊断可追加低成本路由和预算阻断信息，保持旧消费者兼容。

## 10. 风险与缓解

| 风险 | 缓解 |
| --- | --- |
| SearXNG 上游验证码/限流 | 精简引擎、单次 6 秒、串行维度、Anspire fallback |
| 搜索结果缺少日期 | 关键维度不接受无法证明时效的结果；分析维度允许现有 keep-unknown 语义 |
| 低成本路由误伤其他市场 | 显式 `searxng_first_cn` + 现有市场解析 + 跨市场测试 |
| SearXNG 故障导致付费反弹 | 30 次预警、50 次持久化硬上限 |
| 预算并发竞态 | 数据库原子预留，而不是内存计数或先 count 后 call |
| SearXNG access log 泄漏 query | 关闭含 query 的 access log，只保留低敏引擎状态日志 |
| 审计语义误解 | 更新 AGENTS/spec/docs，明确聚合服务边界 |
| 新容器阻断 DSA 启动 | 不设硬 depends_on，运行时 fallback |

## 11. 回滚

1. 将 `SEARCH_ROUTING_MODE=legacy`，重启 DSA，立即恢复旧 Provider 路由。
2. 停止或移除 Compose 的 SearXNG 服务；历史 `search_api_calls` 与预算控制数据保留。
3. 若预算控制本身异常，可临时把低成本模式切回 legacy；是否关闭硬上限必须由用户明确决定，不能自动绕过成本保护。
4. 数据库新增控制表无需删除，不影响旧版本读取现有表。
