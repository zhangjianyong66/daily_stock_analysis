# 综合搜索、可信准入与缓存契约

修改大盘新闻、ETF/普通股票综合情报、新闻准入、缓存或隔离读取时必读。物理请求计数、账户故障和敏感权限以[搜索审计](./search-usage-audit.md)为准。

## 请求与准入

- 仓库不再内置或自动启动私有 SearXNG：Compose 无 `searxng` 服务，`scripts/docker-up.sh` 不读取搜索路由或附加 profile。通用 SearXNG Provider 兼容入口仍保留，但公共实例默认 `SEARXNG_PUBLIC_INSTANCES_ENABLED=false`。
- 单市场大盘复盘按 `MarketProfile.news_queries` 合并为一次综合搜索，逻辑结果上限 6、Provider 候选上限 12，继续使用 `call_source=market_review`；单次失败或空结果不追加隐式查询。
- ETF 综合情报在 Anspire 可用时按逻辑维度合并为两组物理请求：`fresh_events` 近 3 个自然日、`analysis` 近 30 个自然日，均固定 `top_k=18` 且不启用 transport retry；Pipeline 的 5 维度和 Agent 的 6 维度最多产生 2 次物理请求。
- 非 ETF 标准 Pipeline 在 Anspire 可用时按市场保留既有五维并合并为 `fresh_events` 与 `analysis` 两次物理请求：A 股包含最新消息、风险、公告、机构分析和业绩，海外包含最新消息、风险、机构分析、业绩和行业；均固定 `top_k=18` 且不启用 transport retry。Agent 六维工具链保持逐维请求。Anspire 成功但无可信结果时不扇出，物理失败时仅失败组使用既有非 Anspire Provider 降级并逐次审计。
- ETF profile 使用股票索引中的可信名称/别名和确定性名称规则，覆盖行业/主题、跨境、商品、宽基、策略、债券和 `generic_etf`；无法建立唯一底层映射时关闭 `underlying_driver`。
- 产品公告、申赎、份额、规模、折溢价和跟踪事实必须直接命中 ETF 产品身份；不含产品身份的内容只有命中已验证底层映射时才能进入独立底层驱动通道，并明确声明不代表 ETF 产品事实。
- ETF 未知日期、超出 3/30 天窗口、垃圾页、普通涨跌/成交额复述、泛宏观和歧义映射全部拒绝。所有维度为空时不生成空壳报告、不设置 `news_context`、不写 `news_intel`。
- ETF 与普通股票的可信分组结果使用进程级、跨 `SearchService` 实例共享缓存：事件 TTL 15 分钟、分析 TTL 6 小时；同键冷启动通过 singleflight 只允许一个 owner 发请求，等待者复用深拷贝。失败、空结果、`no_trusted_data` 和原始响应不缓存，缓存/等待命中不新增 `search_api_calls`。
- ETF 的任一 Anspire 分组失败时也不自动扇出其他 Provider；普通股票仅物理失败组允许既有非 Anspire fallback，二者不得混用。
- 普通股票近期组拒绝未知或超窗日期；分析组允许未知日期，拒绝已知的 180 天窗外日期。ETF 的严格 3/30 天窗口不得直接套用于普通股票。
- 同一 URL 在组内和跨组只能进入一个最具体维度。
- ETF 别名只接受股票索引中 `asset_type=etf` 的受控别名或代码白名单认可的无歧义名称词，不能将任意名称去掉 ETF 后缀就作为可信底层；未知名称降为 `generic_etf`。
- 普通股票 Anspire 分组 timeout 为 10 秒，ETF 组同样使用 10 秒上限，不开启 transport retry。

## 缓存键与等待者

- 键区分路径类型、模板版本、股票身份、组、窗口、语言和启用维度。
- singleflight 等待者只读取 owner 写入的可信缓存；owner 失败、空结果或等待超时，本轮返回空且不立即重试，owner 必须在 finally 释放 event。
- 共享状态仅限当前 Python 进程，不持久化、不跨容器。

## 历史污染隔离

- `news_intel` 使用 `quarantined_at/quarantine_reason/quarantine_batch` 隔离，默认读取排除隔离记录。
- `save_news_intel()` 遇到已隔离 URL 不得更新内容、Provider 或解除隔离；只有显式批次 rollback 可恢复。历史批次线索见[运维记录](../../research/local-ecs2-operations.md)。

## 定向回归

- 目标回归：`.venv/bin/python -m pytest tests/test_market_strategy.py tests/test_market_review.py tests/test_etf_search_intelligence.py tests/test_stock_search_intelligence.py tests/test_anspire_search.py tests/test_search_news_freshness.py tests/test_search_service_concurrency.py tests/test_search_tools_persistence.py tests/test_news_intel.py tests/test_search_usage_storage.py tests/test_search_usage_service.py -q`。
