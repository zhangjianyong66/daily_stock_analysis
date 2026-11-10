# 技术设计：压缩大盘复盘与分析搜索请求

## 1. 设计边界

本任务包含三个共享同一搜索审计契约、需要一起验收的改动：

1. 大盘复盘：单市场三个主题查询合并为一个综合查询。
2. ETF 分析：保留 `fresh_events` / `analysis` 双窗口，通过进程级可信缓存和 singleflight 消除跨任务重复。
3. 非 ETF 标准分析：Anspire 可用时把 Pipeline 的五个逐维度请求按时效语义合并为两个物理请求，再在本地恢复既有逻辑维度。

三部分均修改 `src/search_service.py`、共享审计字段和搜索测试。拆成多个子任务会产生同文件、同契约的交叉修改，因此保持一个集成任务；验收仍按三条链路分别给出请求上限。

## 2. 基线与目标矩阵

| 场景 | 当前冷启动 | 目标冷启动 | 短期重复目标 | 备注 |
| --- | ---: | ---: | ---: | --- |
| 单市场大盘复盘新闻 | 3 | 1 | 由现有通用缓存决定 | 一次综合查询覆盖复盘、行情分析、热点板块 |
| ETF 综合情报 | 2 | 2 | 两组均有效时 0；仅近期组过期时 1 | 保留 3 天与 30 天双窗口 |
| 非 ETF Pipeline（`call_source=analysis`、`max_searches=5`） | 5 | 健康路径 2 | 两组均有效时 0 | 近期组 + 分析组；Provider 失败降级另计 |
| 非 ETF Agent（`call_source=agent`） | 现有上限 | 不变 | 不变 | 第六维时间语义不同，本任务不改 |
| 未配置 Anspire | 既有 Provider 逐维度路径 | 不变 | 不变 | 不新增隐式 Anspire 或 SearXNG fallback |

请求数以 `search_api_calls` 中真实外部 HTTP 请求为准。缓存、本地分类、格式化和数据库读取不产生物理调用记录。

## 3. 大盘复盘单查询

### 3.1 查询构造

保留 `MarketProfile.news_queries` 作为各市场意图定义，`MarketAnalyzer.search_market_news()` 不再逐项调用，而是按配置顺序去重后合并为一个关键词查询。这样 A 股、港股、美股、日本和韩国继续由各自 profile 决定语种与市场身份，不新增分支或配置项。

单次调用继续使用 `search_stock_news(..., call_source="market_review")`，逻辑最大结果数由 3 提高到 6。现有 oversample 规则会让 Provider 请求 `top_k=12`，低于当前三次 `top_k=6` 合计的 18 条原始候选，同时最终上下文最多保留 6 条，与 2026-07-17 实际三次准入合计数量一致。

### 3.2 失败与兼容

- 单次查询失败时返回空新闻，保持大盘报告模板/LLM 的既有降级行为，不追加第二个隐式查询。
- 不改变 `MarketProfile` 公共字段、报告结构、通知、历史持久化或 `daily_market_context` 锁。
- 审计仍记录 `call_source=market_review`、`operation=search_stock_news`；一次成功只产生一行。

## 4. 进程级可信缓存与 singleflight

### 4.1 共享范围

把当前单个 `SearchService` 实例持有的 ETF 分组缓存提升为 `SearchService` 类级共享缓存，并泛化为 Anspire 综合情报分组缓存。共享范围仅限当前 Python 进程，不跨进程、不落 SQLite、不跨容器重启，继续满足“可信结果仅使用进程内缓存”的现有约束。

Pipeline 每次构造新的 `SearchService`，因此实例级缓存无法覆盖不同分析任务；类级缓存可以消除同一 server/analyzer 进程内的重复请求。

### 4.2 缓存内容与键

缓存只保存本地分类、时效过滤、身份验证和可信准入完成后的 `Dict[str, SearchResponse]` 深拷贝。失败、空结果、`no_trusted_data` 和 Provider 原始响应不缓存。

缓存键至少包含：

- 路径类型：`etf-intel` / `stock-intel`
- 查询模板版本
- 规范化股票代码与名称/profile 指纹
- 查询组 `fresh_events` / `analysis`
- 请求时间窗口
- 启用逻辑维度及顺序
- 市场/语言

TTL 保持：近期组 15 分钟、分析组 6 小时。读取返回深拷贝，避免 Pipeline/Agent 后续裁剪污染共享对象。缓存上限保持 500 组，写入前优先清理过期项，再淘汰最早到期项。

### 4.3 singleflight

共享状态增加 `inflight[key] -> threading.Event`：

1. 首个 miss 成为 owner 并执行唯一物理请求。
2. 同键并发调用等待 owner，owner 成功后读取可信缓存。
3. owner 失败、空结果或等待超时，等待者本轮返回该组为空，不在同一并发波次立即重试，避免失败时请求风暴；后续独立调用仍可成为新 owner。
4. owner 在 `finally` 中释放 event，任何异常都不得永久占用 inflight。

增加测试专用 reset helper，隔离类级缓存，生产代码不在普通请求中主动清空共享缓存。

## 5. 非 ETF Anspire 两组搜索

### 5.1 路由边界

`search_comprehensive_intel()` 只在目标不是 ETF、`call_source=analysis` 且 Anspire 可用时进入新的股票分组路径；ETF 继续走现有 ETF profile 和 fail-closed 分类器；Agent 以及未配置 Anspire 的场景继续使用既有 Provider 逐维度兼容路径。

Anspire 返回成功但本地无可信数据时不追加请求。只有网络、认证、额度、限流或 Provider 5xx 等物理失败，才对失败组的启用维度使用既有 Provider 路径降级，并排除已经失败的 Anspire；每次 fallback 继续独立审计。未显式配置 SearXNG 时不会引入 SearXNG，显式配置时沿用既有 Provider 可用性语义。

### 5.2 逻辑维度与时间窗口

先按现有 CN/foreign 维度顺序和 `max_searches` 截取启用维度，再分组：

| 查询组 | 逻辑维度 | 窗口 | 日期契约 |
| --- | --- | ---: | --- |
| `fresh_events` | `latest_news`、`risk_check`、`announcements` | 当前 `_effective_news_window_days()`，通常 3 天 | 未知日期拒绝，严格裁剪 |
| `analysis` | `market_analysis`、`earnings`；海外 Pipeline 还包含既有 `industry` | 现有 `ANALYTICAL_INTEL_LOOKBACK_DAYS=180` | 已知日期超窗拒绝，未知日期继续允许 |

只有组内至少存在一个启用维度时才请求。Pipeline 的五维健康路径产生两次；调用方只启用同一组时仅产生一次。Agent 六维继续走当前逐维路径。

每组使用固定 `top_k=18`、10 秒 timeout 且关闭 transport retry，与 ETF Anspire 分组的成本与超时护栏一致。`provider_attempt` 表示本业务搜索中的组顺序，审计 `dimension` 明确记录 `fresh_events` / `analysis`，不伪装成逐维度物理请求。

### 5.3 查询与本地分类

查询必须包含规范化股票代码、股票名称以及该组已启用维度的意图词。中文与海外市场分别沿用现有维度关键词，避免把公司公告、诉讼风险、业绩和行业分析翻译为 ETF 产品语义。

Provider 返回后按以下顺序处理：

1. 规范化 URL、日期、标题和摘要，拒绝垃圾页、成人/博彩和无有效 URL 内容。
2. 使用现有代码/名称身份和相关性排序，拒绝零相关结果。
3. 应用组级日期契约。
4. 每条结果只分配到一个最具体的启用维度，避免同一 URL 在报告中重复：
   - 近期组：公司公告 > 明确风险/处罚/诉讼 > 其他直接公司事件。
   - 分析组：业绩/财报/预告 > 海外行业/竞争格局 > 机构观点/评级/目标价等综合分析。
5. 每维度最多 3 条，构造兼容的 `SearchResponse`；维度键、报告展示和 `news_intel` 持久化入口不变。

分类规则放入独立的 `src/services/stock_search_intelligence.py`，与 ETF 专用规则并列，避免继续扩大 `src/search_service.py` 中的关键词和 profile 逻辑。该模块只负责确定性 query/classification，不发网络请求、不写数据库。

## 6. 审计、诊断与缓存语义

- 物理请求继续统一经过 `_call_provider_with_audit()` 和 `audited_request_once()`；禁止在逻辑分组层补记合成调用。
- 大盘单查询产生一个独立 `business_search_id`；普通股票两组共享同一个 `business_search_id`，各自拥有独立 `logical_request_id`。
- 组缓存命中只写现有低敏运行诊断 `cache_hit=True`，不新增 `search_api_calls`。
- singleflight 等待命中同样不产生物理调用记录；owner 的真实请求保留完整脱敏审计。
- 不隐藏备用 Key、transport retry 或 Provider fallback。Anspire 分组显式关闭 retry；物理失败后的逐维降级以及未配置 Anspire 的 legacy 路径保持真实审计行为。

## 7. 兼容性与文档

- `search_comprehensive_intel()` 签名、返回类型、逻辑维度键和 `format_intel_report()` 消费契约保持不变。
- 不新增配置项、数据库字段或 API/Web schema。
- 用户可见报告仍按原维度展示；变化仅是候选来源由逐维度查询改为组查询后本地分流。
- 更新 `AGENTS.md`、`.trellis/spec/backend/search-usage-audit.md`、`docs/full-guide.md` / `docs/full-guide_EN.md` 和 `docs/CHANGELOG.md`。
- 不修改 README；本任务没有 Web UI 改动，不需要页面截图。

## 8. 风险与回滚

### 风险

- 综合查询可能被某一主题占据，导致稀有维度为空。通过 `top_k=18`、确定性意图词、每结果单维分流和在线 smoke（另行授权）观察。
- 类级缓存可能污染测试或跨配置复用。通过完整键、深拷贝、reset helper 和测试 fixture 隔离。
- owner 失败时等待者本轮返回空，短时降低新闻覆盖，但可以避免并发失败风暴；后续独立调用仍会重试。

### 回滚

- 大盘复盘：恢复 `news_queries` 循环即可回到三次请求。
- 非 ETF：移除 `call_source=analysis` 的 Anspire 分组路由即可恢复逐维度 legacy 路径。
- 缓存：把共享状态恢复为实例字段即可；无需数据迁移或清理数据库。
- 所有改动均可通过代码回滚完成，不涉及持久化 schema 回滚。
