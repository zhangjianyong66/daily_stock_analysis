# 修复 ETF 实时行情多源兜底 - 实施计划

> 本任务由 Codex inline 模式执行。实施阶段必须先加载 `trellis-before-dev`、`superpowers:test-driven-development`，每个行为先补失败测试再写实现；完成前加载 `trellis-check` 与 `superpowers:verification-before-completion`。未经用户明确确认，不执行代码提交、推送或打标签。

## 目标与边界

- 保持 `DataFetcherManager.get_realtime_quote()`、`REALTIME_SOURCE_PRIORITY` 和现有调用方兼容。
- 在 `DataFetcherManager` 内收敛所有市场实时行情的总预算、失败分类、物理上游去重、fallback 诊断和 last-good stale 降级。
- 只为 A 股 ETF 修正腾讯、新浪、Eastmoney 的真实独立路由；其他市场沿用现有 provider 集合。
- 不新增数据库表、文件缓存、平行 Router 服务或未经验证的新供应商。
- 已获得有效主行情后，字段补充失败不得丢弃主行情。

## 文件映射

| 文件 | 职责 | 计划改动 |
| --- | --- | --- |
| `data_provider/realtime_types.py` | 统一实时行情类型与熔断器 | 增加稳定失败枚举、失败归一化 helper、stale/fallback 低敏元数据字段 |
| `data_provider/base.py` | 实时行情公共调度入口 | 增加内部 source plan、20 秒总预算、分层重试、物理源阻断、last-good 缓存、公共市场执行器 |
| `data_provider/akshare_fetcher.py` | AkShare/腾讯/新浪实时行情适配 | ETF 尊重 `source`；轻量请求接受有界 timeout；AkShare EM ETF 全量缓存增加 singleflight |
| `data_provider/efinance_fetcher.py` | efinance Eastmoney 适配 | ETF 全量缓存增加 singleflight，并允许 manager 收紧等待时间 |
| `src/services/run_diagnostics.py` | 请求级 provider 诊断 | ProviderRun 追加逻辑源、物理源、attempt/retry/budget/stale 元数据；保持脱敏 |
| `src/core/pipeline.py` | 分析流程与 artifacts 组装 | 从当前诊断快照提取实时行情低敏失败摘要，传入两条 artifacts 构建路径 |
| `src/services/analysis_context_builder.py` | AnalysisContextPack 映射 | 区分 `available/fallback/stale/fetch_failed/missing`，传递缓存年龄与失败摘要 |
| `tests/test_realtime_types.py` | 统一类型测试 | 覆盖失败分类、序列化和 stale 元数据 |
| `tests/test_realtime_quote_fallback_logging.py` | manager 回归测试 | 覆盖预算、重试、fallback、物理源去重、last-good 和多市场兼容 |
| `tests/test_akshare_realtime_quote.py` | AkShare 路由测试（新建） | 覆盖 ETF 腾讯/新浪/EM 分派、轻量 timeout 和不可重试空数据 |
| `tests/test_etf_realtime_singleflight.py` | 全量缓存并发测试（新建） | 覆盖 AkShare/efinance singleflight 成功、失败与等待超时 |
| `tests/test_run_diagnostics_p1.py` | provider 诊断回归 | 覆盖新增结构化字段和脱敏边界 |
| `tests/test_analysis_context_builder.py` | 上下文状态回归 | 覆盖 stale、fallback、fetch_failed、missing 优先级 |
| `.env.example` | 配置说明 | 明确 `0` 仅关闭用户额外上限，不能突破 3/8/20 秒安全上限；说明 ETF 真源路由 |
| `docs/data-source-stability.md` | 数据源稳定性文档 | 补充 ETF 真实源、总预算、物理源去重、stale 与失败状态 |
| `docs/full-guide.md`、`docs/full-guide_EN.md` | 中英文配置说明 | 同步实时 timeout 与 fallback 契约 |
| `docs/analysis-context-pack.md` | 输入质量契约 | 补充 quote `fetch_failed`、cache age、失败摘要语义 |
| `docs/CHANGELOG.md` | 用户可见变更 | 在 `[Unreleased]` 扁平区新增一条 `[修复]` |

## 阶段 1：统一失败分类与 quote 元数据

- [x] 在 `tests/test_realtime_types.py` 先增加失败测试：
  - `TimeoutError`/requests timeout -> `timeout`。
  - connection reset/remote disconnect -> `connection_error`。
  - HTTP 429 或项目 `RateLimitError` -> `rate_limited`。
  - `None` -> `empty`，无有效价格 -> `invalid_quote`，不支持 -> `not_supported`，熔断 -> `circuit_open`。
  - 原始异常文本只用于日志，稳定分类和低敏摘要不包含 URL、代理、token、堆栈。
- [x] 运行：

  ```bash
  python3 -m pytest tests/test_realtime_types.py -q
  ```

  预期：新增测试先失败，证明现有类型缺少公共失败契约。

- [x] 在 `data_provider/realtime_types.py` 增加：
  - `RealtimeFailureType(str, Enum)`，值固定为 `timeout`、`connection_error`、`rate_limited`、`empty`、`invalid_quote`、`not_supported`、`circuit_open`、`all_sources_failed`。
  - `classify_realtime_failure(...)` 和只返回低敏稳定文本的 summary helper，供 manager、诊断和上下文共同复用。
  - `UnifiedRealtimeQuote.cache_age_seconds`、`fallback_reason`、`failure_summary` 可选字段；`data_quality` 允许 `ok/partial/stale/unavailable`。
  - `to_dict()` 序列化新增字段，`has_basic_data()` 仍只以正价格作为主行情有效条件。
- [x] 重新运行 `tests/test_realtime_types.py`，预期通过。

## 阶段 2：manager 内部源计划、总预算与 last-good

- [x] 在 `tests/test_realtime_quote_fallback_logging.py` 先补以下失败测试：
  - `test_manager_retries_lightweight_connection_error_once_then_falls_back`：轻量源快速抛瞬时网络错误时总尝试 2 次。
  - `test_manager_does_not_retry_empty_or_invalid_quote`：空值/无价格只调用 1 次。
  - `test_manager_caps_lightweight_and_bulk_timeouts`：配置 30 秒时实际轻量等待不超过 3 秒、全量不超过 8 秒。
  - `test_manager_stops_starting_sources_after_total_budget`：fake monotonic 到 20 秒后不启动后续源。
  - `test_manager_timeout_does_not_retry_same_fetcher_or_physical_source`：manager wait timeout 后跳过同 fetcher 和同物理上游。
  - `test_manager_blocks_second_eastmoney_client_after_connection_failure`：efinance 网络失败后本轮不再调用 AkShare EM。
  - `test_manager_allows_second_eastmoney_client_after_parse_failure`：解析/兼容错误允许在剩余预算内尝试另一客户端。
  - `test_manager_keeps_primary_quote_when_supplement_times_out`：有效主行情不因补充失败丢失。
  - `test_manager_returns_same_day_last_good_with_stale_metadata`：所有实时源失败时返回同交易日 30 分钟内深拷贝。
  - `test_manager_rejects_expired_or_previous_day_last_good`：超过 1800 秒或跨交易日返回 `None`。
  - `test_manager_does_not_extend_last_good_age_from_stale_result`：stale 不回写。
  - `test_manager_last_good_cache_is_thread_safe`：并发读写不串标的、不共享可变 quote。
  - 日/韩/台单源以及港/美双源路径也受 20 秒预算和 stale 契约约束，但不生成虚假候选源。
- [x] 运行新增 manager 测试，确认先失败。
- [x] 在 `data_provider/base.py` 增加私有不可变结构：

  ```python
  @dataclass(frozen=True)
  class RealtimeSourcePlan:
      route_source: str
      physical_source: str
      fetcher_name: str
      kwargs: Mapping[str, Any]
      timeout_seconds: float
      max_attempts: int
      lightweight: bool
  ```

- [x] 增加 `_build_realtime_source_plans()`：
  - A 股/ETF 从 `REALTIME_SOURCE_PRIORITY` 生成计划，token 与现有配置兼容。
  - `tencent/akshare_qq -> physical=tencent`，`akshare_sina -> sina`，`efinance/akshare_em -> eastmoney`。
  - 港/美/日/韩/台把现有专用路由转换为相同执行模型，不添加新 provider。
- [x] 增加 `_execute_realtime_plans()`：
  - 使用 `time.monotonic()` 计算固定 20 秒 deadline。
  - 每次调用 timeout 为 `min(源策略上限, 正配置上限, remaining)`；配置 `<=0` 视为无额外用户上限。
  - 轻量源只对公共分类为 `timeout/connection_error/rate_limited` 的快速失败重试 1 次；manager wait timeout 不重试同 plan。
  - `empty/invalid_quote/not_supported/circuit_open` 不重试。
  - 网络/限流失败阻断同 `physical_source`；解析/兼容类失败不阻断替代客户端。
  - 每个 attempt 调用 `record_provider_run_started/record_provider_run`，记录 route/physical/attempt/fallback/budget。
  - 第一份 `has_basic_data()` quote 成为主行情；补充调用只能填 `_SUPPLEMENT_FIELDS`，异常不能覆盖主行情。
- [x] 增加进程级 last-good 存储：
  - key 为 `(market, normalized_code)`；值为 quote 深拷贝、monotonic 缓存时刻、交易日和原始来源。
  - 用 `RLock` 保护；仅实时成功写入；读取返回深拷贝。
  - 所有 plan 失败/预算耗尽后检查同交易日且 `age <= 1800`，设置 `is_stale=True`、`data_quality="stale"`、`cache_age_seconds`、`fallback_reason`、`failure_summary`。
- [x] 保留 `get_realtime_quote()` 的参数和返回类型，删除/收敛现有重复市场循环到公共执行器；`_try_fetcher_quote()`、`_supplement_quote()` 只保留仍有其他调用方需要的兼容职责。
- [x] 运行 manager 定向测试，预期全部通过且原有 fallback 测试不回归。

## 阶段 3：ETF 腾讯/新浪/EM 真路由与请求上限

- [x] 新建 `tests/test_akshare_realtime_quote.py`，先覆盖：
  - ETF `source="tencent"` 只调用腾讯单标的解析路径，source 为 `RealtimeSource.TENCENT`。
  - ETF `source="sina"` 只调用新浪单标的解析路径，source 为 `RealtimeSource.AKSHARE_SINA`。
  - ETF `source="em"` 才调用 ETF Eastmoney 全量接口。
  - 普通 A 股路由保持原行为；港股/美股分支不受影响。
  - `request_timeout_seconds` 能把 requests timeout 收紧到 manager 下发值，不使用固定 10 秒。
- [x] 运行新测试，确认当前 ETF 三个 source 均落到 EM 的测试先失败。
- [x] 修改 `data_provider/akshare_fetcher.py`：
  - `get_realtime_quote()` 的 ETF 分支按 `source` 显式分派到腾讯、新浪、EM。
  - 复用现有 `_get_stock_realtime_quote_tencent/_sina` 解析器，不复制解析代码；仅调整命名/docstring 使其覆盖 A 股股票和 ETF。
  - 为轻量 HTTP 方法增加私有 `request_timeout_seconds` 参数，实际 requests timeout 使用 `min(3, 传入正值)`。
  - Eastmoney ETF 全量方法每轮只调用一次，移除内部 2 次重试和 sleep；重试归 manager 统一控制。
  - 熔断 key 与真实上游对应，不再把所有 ETF source 共用 `akshare_etf`。
- [x] 运行 AkShare 新测试及现有 A 股/港股路由测试。

## 阶段 4：AkShare / efinance ETF 全量缓存 singleflight

- [x] 新建 `tests/test_etf_realtime_singleflight.py`，用线程、Event 和 fake DataFrame 先覆盖：
  - 两个并发 AkShare ETF 缓存 miss 只执行一次 `fund_etf_spot_em()`。
  - 两个并发 efinance ETF 缓存 miss 只执行一次 `get_realtime_quotes(['ETF'])`。
  - 刷新成功后等待者复用结果；刷新失败后等待者一致得到空结果且不二次刷新。
  - 等待者自己的预算到期时返回失败，不阻塞到刷新者完成。
  - 网络调用期间不持有缓存互斥锁，其他线程可读取新鲜缓存。
- [x] 修改两个 fetcher 的模块级 ETF 缓存状态：增加 `Condition(RLock())`、`refreshing` 和最近刷新结果时间；缓存数据结构仍保持进程内，不持久化。
- [x] 抽取每个文件内部的 `_get_or_refresh_etf_realtime_data(wait_timeout_seconds)`：
  - 新鲜缓存直接返回。
  - 首个 miss 成为刷新者，锁外执行网络调用，finally 广播。
  - 等待者按剩余 timeout 等待并复用结果；不得自行并发刷新。
- [x] 运行 singleflight 测试，随后运行 AkShare/efinance 现有测试。

## 阶段 5：诊断、pipeline 与 AnalysisContextPack

- [x] 在 `tests/test_run_diagnostics_p1.py` 先增加诊断测试：ProviderRun 能序列化 `route_source`、`physical_source`、`attempt`、`retry`、`budget_remaining_ms`、`cache_age_seconds`，且 error message 继续脱敏。
- [x] 在 `src/services/run_diagnostics.py` 扩展 `ProviderRun` 和 `record_provider_run()` 可选参数；不改变现有调用方必填参数，不保存原始异常或堆栈。
- [x] 在 `tests/test_analysis_context_builder.py` 先增加：
  - 无 quote 且 metadata 有实时 provider failures -> block/item 为 `FETCH_FAILED`，reason 为 `realtime_quote_fetch_failed`。
  - 无 quote 且无请求证据/功能关闭 -> 仍为 `MISSING/realtime_quote_missing`。
  - last-good quote -> `STALE`，metadata 含 `cache_age_seconds`、原始 source、failure summary。
  - 跨源成功 -> `FALLBACK`；stale 优先级高于 fallback。
  - 用户可见 summary 只含稳定分类和源 token，不含异常原文。
- [x] 在 `src/core/pipeline.py` 增加单一 helper 从 `current_diagnostic_snapshot()["provider_runs"]` 投影当前请求的实时行情摘要：
  - 只选择 `data_type == "realtime_quote"`。
  - 输出 `attempted`、`all_failed`、失败源列表、稳定 error types、最终 fallback/stale 信息。
  - legacy 和 agent 两条 `PipelineAnalysisArtifacts` 构建路径共同复用 helper，禁止各自解析诊断 payload。
- [x] 修改 `src/services/analysis_context_builder.py`：
  - `_build_quote_block()` 在无 quote 时读取统一 metadata 投影决定 `FETCH_FAILED` 或 `MISSING`。
  - `_quote_metadata()` 追加 `cache_age_seconds/failure_summary/fallback_reason` 白名单。
  - stale 行情保留 source 和 fallback 信息，数据质量权重沿用现有 `STALE=50`。
- [x] 运行：

  ```bash
  python3 -m pytest \
    tests/test_run_diagnostics_p1.py \
    tests/test_analysis_context_builder.py \
    tests/test_analysis_context_pack_prompt.py \
    -q
  ```

## 阶段 6：文档、回归与质量门禁

- [x] 更新 `.env.example`：明确 `DATA_SOURCE_REALTIME_TIMEOUT_SECONDS` 是额外单次上限，`0` 不取消 3/8/20 秒安全上限；标注 ETF 的 Tencent/Sina/EM 为真实独立路由，efinance 与 AkShare EM 同属 Eastmoney 物理上游。
- [x] 更新 `docs/data-source-stability.md`：
  - 数据源矩阵新增 A 股 ETF。
  - 图示加入 20 秒总预算、物理上游阻断、30 分钟 same-day last-good。
  - 用户提示区分 fallback、stale、fetch_failed。
- [x] 同步 `docs/full-guide.md` 与 `docs/full-guide_EN.md` 的配置说明；更新 `docs/analysis-context-pack.md` 的 quote 状态契约。
- [x] 在 `docs/CHANGELOG.md` 的 `[Unreleased]` 扁平区增加：

  ```markdown
  - [修复] ETF 实时行情改为腾讯、新浪、Eastmoney 真实多源路由，并统一重试预算、同上游去重、30 分钟 stale 降级和失败诊断。
  ```

- [x] 运行定向测试：

  ```bash
  python3 -m pytest \
    tests/test_realtime_types.py \
    tests/test_realtime_quote_fallback_logging.py \
    tests/test_akshare_realtime_quote.py \
    tests/test_etf_realtime_singleflight.py \
    tests/test_fetcher_source_optimization.py \
    tests/test_hk_realtime_routing.py \
    tests/test_tw_market_support.py \
    tests/test_run_diagnostics_p1.py \
    tests/test_analysis_context_builder.py \
    tests/test_analysis_context_pack_prompt.py \
    -q
  ```

- [x] 对所有变更 Python 文件运行：

  ```bash
  python3 -m py_compile \
    data_provider/realtime_types.py \
    data_provider/base.py \
    data_provider/akshare_fetcher.py \
    data_provider/efinance_fetcher.py \
    src/services/run_diagnostics.py \
    src/core/pipeline.py \
    src/services/analysis_context_builder.py
  ```

- [x] 运行完整后端门禁：

  ```bash
  ./scripts/ci_gate.sh
  ```

- [x] 若实际改动触及 Web 状态映射，再追加对应 Vitest、`npm run lint`、`npm run build`；若后端已有状态可直接展示，则不扩大前端 diff。
- [x] 可选在线补充证据（不作为 CI 成败条件）：在当前容器对 `159869` 分别调用腾讯、新浪、Eastmoney 路由，记录实际 source 与耗时；不得把原始响应、代理配置或敏感网络信息写入仓库。

## 计划自审与回滚点

- R1/R5/R16：阶段 3 覆盖 ETF 真路由及非 ETF 回归。
- R2/R3/R6/R11/R12/R22/R23：阶段 1、2、5 覆盖失败分类、重试和物理源去重。
- R7/R13/R25：阶段 2 覆盖 3/8/20 秒预算与配置上限。
- R10/R14/R15/R17：阶段 2、5 覆盖所有市场公共 last-good 和 LLM 输入语义。
- R20：阶段 2 覆盖主行情不可丢失。
- R21：阶段 4 覆盖 singleflight。
- R8/R18/R24：阶段 5、6 覆盖低敏诊断、`fetch_failed` 和文档。
- 回滚按阶段进行：类型字段为向后兼容可选字段；manager 执行器可整体回退；singleflight 无持久化状态；文档无数据迁移。任何阶段失败都不得用 broad `except: return None` 隐藏契约问题。

## 实施与验证结果

- ETF Tencent/Sina/EM 已按物理上游独立路由；在线 `159869` 探测返回 `tencent` 与 `akshare_sina` 两个实际 source。
- manager 已统一 3/8/20 秒预算、分层重试、物理源去重、主行情保护和 same-day 30 分钟 last-good stale。
- AkShare/efinance ETF 全量缓存已使用共享 singleflight，覆盖并发成功、共享失败和等待者超时。
- ProviderRun、pipeline artifacts 和 AnalysisContextPack 已贯通 route/physical/attempt/budget、fallback/stale/fetch_failed 低敏语义。
- `python scripts/check_ai_assets.py`、`git diff --check`、Python 编译和 critical flake8 通过。
- `./scripts/ci_gate.sh`：`4410 passed, 4 deselected, 45 warnings, 413 subtests passed`。
