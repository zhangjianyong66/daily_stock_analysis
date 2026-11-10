# 修复 ETF 实时行情多源兜底 - 技术设计

## 1. 设计目标

在不改变外部 API、`REALTIME_SOURCE_PRIORITY` 配置格式和 `DataFetcherManager.get_realtime_quote()` 返回契约的前提下，修复 ETF 路由名与真实物理数据源不一致的问题，并为所有市场实时行情统一增加：

- 有界重试和 20 秒总等待预算。
- 真实跨源 fallback 和物理上游级失败去重。
- 进程内 last-good stale 降级。
- 逐源结构化诊断和可读的分析上下文状态。
- 全量接口缓存刷新 singleflight，避免并发请求风暴。

本任务不新建平行 Router 服务。`DataFetcherManager` 继续是实时行情唯一公共调度入口。

## 2. 现有边界与改动边界

现有调用关系保持不变：

```text
StockAnalysisPipeline / API / Agent
  -> DataFetcherManager.get_realtime_quote()
      -> EfinanceFetcher / AkshareFetcher / TushareFetcher / ...
          -> Tencent / Sina / Eastmoney / 其他上游
```

改动集中在以下边界：

- `data_provider/base.py`
  - 把实时行情的条件分支收敛为内部源计划。
  - 统一执行预算、重试、fallback、结果校验、物理源去重和 last-good 降级。
- `data_provider/akshare_fetcher.py`
  - ETF 必须尊重 `source` 参数。
  - `tencent`、`sina` 使用已有单标的解析路径，`em` 才调用 `fund_etf_spot_em()`。
  - ETF 全量缓存刷新增加进程内 singleflight。
- `data_provider/efinance_fetcher.py`
  - ETF 全量缓存刷新增加进程内 singleflight。
- `data_provider/realtime_types.py`
  - 复用 `UnifiedRealtimeQuote`，只增加 stale/fallback 所需的低敏元数据。
- `src/core/pipeline.py`、`src/services/analysis_context_builder.py`、`src/services/run_diagnostics.py`
  - 把请求级失败轨迹转换为 `fallback / stale / fetch_failed` 上下文和诊断语义。
- Web 状态映射
  - 仅在新增原因码无法由现有映射正确展示时补充文案和测试，不重做报告组件。

## 3. 内部源计划

在 `DataFetcherManager` 内增加不可变的内部源计划，例如：

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

字段语义：

- `route_source`：配置和诊断使用的逻辑名，如 `tencent`、`akshare_sina`。
- `physical_source`：真实上游族，如 `tencent`、`sina`、`eastmoney`，用于避免伪多源。
- `fetcher_name` / `kwargs`：定位现有 fetcher 和调用参数，不引入新的公共 provider 接口。
- `timeout_seconds`：单次等待上限；实际等待值还受总预算约束。
- `max_attempts`：轻量单标的源最多 2 次，慢速全量源为 1 次。
- `lightweight`：仅用于选择重试策略，不改变数据质量判断。

源计划按市场生成：

- A 股和 ETF：遵守 `REALTIME_SOURCE_PRIORITY`。
- 港股、美股、日股、韩股、台股：保持现有候选源和优先关系，但统一经过预算、诊断和 stale 降级。
- 没有第二个已验证源的市场不伪造多源能力。

## 4. ETF 真实路由

`AkshareFetcher.get_realtime_quote(stock_code, source=...)` 对 ETF 的行为调整为：

| source | 实际调用 | 物理上游 |
| --- | --- | --- |
| `tencent` / `akshare_qq` | 腾讯单标的接口与现有腾讯解析器 | `tencent` |
| `sina` / `akshare_sina` | 新浪单标的接口与现有新浪解析器 | `sina` |
| `em` / `akshare_em` | `ak.fund_etf_spot_em()` | `eastmoney` |

efinance ETF 行情继续作为 Eastmoney 的另一客户端实现，`physical_source` 同样标记为 `eastmoney`。

如果 Eastmoney 客户端发生 `timeout`、`connection_error` 或 `rate_limited`，本轮阻断 `physical_source=eastmoney` 的其他计划。若失败属于解析或客户端兼容差异，可在剩余预算内尝试另一 Eastmoney 客户端实现。

## 5. 执行与预算

单只股票实时行情总预算固定为 20 秒。每次调用前计算：

```text
remaining = deadline - monotonic_now
attempt_timeout = min(plan.timeout_seconds, remaining)
```

当 `remaining <= 0` 时停止启动新 provider 调用。

现有 `DATA_SOURCE_REALTIME_TIMEOUT_SECONDS` 继续作为用户配置的额外单次等待上限。有效等待时间按以下方式收敛：

```text
effective_timeout = min(source_policy_timeout, configured_timeout_if_positive, remaining)
```

当现有配置为 `0` 时，表示不施加额外的用户配置上限，但仍受源策略 3/8 秒和总链路 20 秒安全上限约束。该语义需要同步更新 `.env.example` 和数据源稳定性文档。

重试策略：

- 腾讯、新浪等轻量单标的源：单次最多 3 秒；仅对快速返回的瞬时网络错误重试 1 次。
- manager 等待超时意味着底层 daemon 线程可能仍在运行，因此 manager 超时后不重试同一 plan，也不再尝试相同 fetcher / 物理上游。
- Eastmoney 全量接口和 efinance：单次最多 8 秒，每轮只调用 1 次。
- `empty`、`invalid_quote`、`not_supported`：当前 plan 不重试，立即进入下一计划。
- provider 内已有的请求级 retry 必须服从该 provider 的请求 timeout，不能突破 manager 的总预算语义。

总预算限制调用方等待时间，不承诺强杀 Python 后台线程。已有 per-fetcher lock 和“manager 超时后本轮跳过同 provider”护栏继续保留，避免悬挂调用堆叠。

## 6. 主行情与字段补充

第一个 `has_basic_data()` 成功的 quote 立即成为主行情：

- 立即记录成功来源和 last-good 缓存候选。
- 后续源可在剩余预算内补充量比、换手率、估值等缺失字段。
- 补充失败、超时、熔断或预算耗尽不得覆盖或丢弃主行情。
- `fallback_from` 只表示首选源失败后切换成功，不因单纯字段补充而标记 fallback。

## 7. last-good stale 缓存

last-good 缓存为进程级、线程安全内存结构：

- 键：`(market, normalized_stock_code)`。
- 值：成功 quote 的深拷贝、缓存时间、有效交易日和原始来源。
- 只缓存实时源成功返回的有效基本行情；stale 结果不得再次写回并延长寿命。
- 服务重启后缓存为空，不持久化到 SQLite 或文件。

所有实时源失败或总预算耗尽后，缓存必须同时满足：

- 与当前请求属于同一有效交易日。
- `cache_age_seconds <= 1800`。
- quote 仍有有效基本价格。

返回 stale 时使用 quote 深拷贝，并设置：

- `is_stale = True`
- `data_quality = "stale"`
- `cache_age_seconds`
- 原始 `source`
- `fallback_from`
- 低敏 `fallback_reason`

`stale_seconds` 继续表示 provider 时间与获取时间的差值；新增 `cache_age_seconds` 表示 last-good 缓存年龄，避免混淆两个时间概念。

## 8. 全量缓存 singleflight

Akshare 和 efinance 的 ETF 全量缓存当前是模块级共享数据，但刷新过程缺少跨 manager 的全局协调。

为各自 ETF 全量缓存增加模块级 `Condition` / `RLock` 和 `refreshing` 状态：

1. 缓存新鲜时直接读取。
2. 缓存过期且没有刷新者时，当前调用成为刷新者。
3. 已有刷新者时，其他调用在自身剩余预算内等待。
4. 刷新完成后广播等待者；等待者复用成功结果或统一看到失败结果。
5. 等待超时后返回本 plan 失败，不再额外启动并行全量刷新。

网络调用期间不持有互斥锁；锁只保护刷新所有权和缓存状态。

## 9. 失败分类与诊断

稳定失败类别：

- `timeout`
- `connection_error`
- `rate_limited`
- `empty`
- `invalid_quote`
- `not_supported`
- `circuit_open`
- `all_sources_failed`

每次 plan 尝试复用现有 `record_provider_run_started()` / `record_provider_run()`，记录：

- 逻辑路由名和实际 provider。
- 物理上游。
- 尝试序号、耗时、结果类别。
- retry、fallback_to、是否因预算或熔断跳过。

原始异常只进入普通日志；持久化诊断和报告只保留归一化类别与截断、低敏摘要。

不在 `DataFetcherManager` 上保存进程级“最后一次失败”可变字段。所有失败轨迹继续进入现有请求级诊断上下文，避免并发分析串线。

## 10. 分析上下文和用户可见状态

成功 quote：

- 首源成功 -> `available`
- 跨源成功 -> `fallback`
- last-good -> `stale`

无 quote：

- 请求级诊断证明实时源已尝试且全部失败 -> `fetch_failed`
- 没有请求证据，例如功能禁用或旧上下文 -> 保留 `missing`

pipeline 从当前请求诊断快照提取低敏实时行情失败摘要，放入 `PipelineAnalysisArtifacts.metadata`。`AnalysisContextBuilder` 据此区分 `fetch_failed` 和 `realtime_quote_missing`。

stale quote 继续进入增强上下文和 LLM 输入，并显式传递：

- `is_stale`
- `cache_age_seconds`
- 原始来源
- 简洁 fallback 原因

数据质量评分沿用现有 `ContextFieldStatus.STALE` 低于 `AVAILABLE` / `FALLBACK` 的权重，不把 stale 伪装为实时成功。

## 11. 兼容性

- `get_realtime_quote()` 继续返回 `UnifiedRealtimeQuote | None`。
- `REALTIME_SOURCE_PRIORITY` 格式和已有 source token 保持兼容。
- `DATA_SOURCE_REALTIME_TIMEOUT_SECONDS` 继续可收紧单次等待时间，但不能放大源策略和总链路安全上限。
- 数据源正常时，普通 A 股及其他市场的成功路径保持原有来源和主要字段。
- `UnifiedRealtimeQuote.to_dict()` 只追加可选字段，旧消费者可忽略。
- API schema 如需显式声明新增可选字段，只做向后兼容追加。
- 全部实时源失败时仍使用历史数据完成分析，不改变主流程 fail-open 原则。

## 12. 测试设计

离线确定性测试覆盖：

- ETF 腾讯、新浪、Eastmoney 源映射。
- 首源失败、次源成功和 `fallback_from`。
- 轻量源瞬时错误重试、不可重试错误直接切源。
- manager 超时后不重试悬挂 provider。
- 20 秒总预算和剩余预算裁剪。
- 主行情成功后补充失败仍返回主行情。
- Eastmoney 物理源网络失败去重与解析错误替代客户端。
- ETF 全量缓存并发 singleflight。
- last-good 同交易日、30 分钟边界、深拷贝和线程安全。
- stale 不回写延长寿命。
- 各市场现有路由回归。
- 上下文 `available / fallback / stale / fetch_failed / missing`。
- 诊断字段完整且不包含原始堆栈。

验证命令：

```bash
python3 -m pytest <targeted tests>
python3 -m py_compile <changed python files>
./scripts/ci_gate.sh
```

如修改 Web 映射或文案，补充：

```bash
cd apps/dsa-web
npm run test -- <targeted tests>
npm run lint
npm run build
```

在线腾讯 / 新浪 / Eastmoney 请求只作为人工补充证据，不进入确定性 CI。

## 13. 风险与回滚

主要风险：

- manager 超时无法强杀底层 Python 线程；通过不重试超时 plan、跳过相同 fetcher / 物理源和 singleflight 控制线程数量。
- 新物理源去重过严可能少尝试一个客户端；只对网络、限流和 manager timeout 触发物理源阻断，解析类错误仍允许替代实现。
- stale 数据可能影响结论；通过同交易日、30 分钟限制、显式 stale 元数据和数据质量降级控制风险。

回滚方式：

- 回退本任务代码即可恢复现有路由。
- 不涉及数据库迁移或持久化缓存清理。
- 如新增可选配置，默认值必须维持本设计行为，并可通过现有实时行情开关整体关闭实时链路。
