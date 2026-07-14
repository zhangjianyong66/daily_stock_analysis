# 错误处理规范

本仓库要求错误在边界处可理解、在日志中可排查、在主流程中尽量局部失败不拖垮整体。

## API 错误响应

API 错误响应统一使用：

```json
{
  "error": "error_code",
  "message": "用户可理解的错误说明",
  "detail": {}
}
```

本地 helper：

- `api/v1/errors.py::error_body()`
- `api/v1/errors.py::api_error()`
- `api/v1/errors.py::error_json_response()`

Endpoint 应优先使用这些 helper。参考 `api/v1/endpoints/portfolio.py`：

- `ValueError` 映射为 `400 validation_error`。
- 找不到资源映射为 `404 not_found`。
- 业务冲突映射为 `409`，例如 `portfolio_busy`、`portfolio_oversell`。
- 未预期异常记录 `exc_info=True` 后映射为 `500 internal_error`。

## FastAPI 全局处理

`api/middlewares/error_handler.py` 注册全局异常处理：

- `HTTPException`：如果 detail 已是 `{error, message}`，直接返回。
- `RequestValidationError`：返回 `422 validation_error`。
- 其他异常：记录路径、方法和堆栈，返回 `500 internal_error`，默认不暴露 detail。

新增 API 时不要自定义另一套错误 envelope。

## Service 和 Repository 异常

- Service 层使用 `ValueError` 表示输入或业务参数无效，但跨多入口复用的业务冲突应定义明确异常类。
- Repository 层可以定义数据库相关领域异常，例如 `PortfolioBusyError`、`DuplicateTradeUidError`。
- Endpoint 负责把领域异常映射到 HTTP 状态码；不要在 service 中依赖 FastAPI 类型。
- 底层第三方异常需要在数据源/服务边界转换为可理解错误或 fallback 结果。

## 主流程和数据源 fallback

`main.py` 的设计目标之一是“单股失败不影响整体”。数据源和通知链路应保持局部失败：

- 单一数据源失败应降级到下一个可用源，除非需求明确要求 fail-fast。
- 单一通知渠道失败不应拖垮整个分析主流程。
- 网络或三方依赖错误要保留 provider/source、股票代码、阶段等上下文日志。
- fallback 不应静默吞掉契约错误；要返回明确状态、limitations、data_quality 或日志说明。

## 场景：分析任务和数据源调用超时

### 1. Scope / Trigger

- Trigger：改动任务队列、数据源 fallback、运行时环境变量或 Web 设置页中的超时配置时。
- Scope：普通分析任务、通用后台任务、股票名称、日线数据、实时行情。

### 2. Signatures

- `src.services.task_queue.AnalysisTaskQueue.sync_task_timeout_seconds(timeout_seconds: int) -> Literal["applied", "unchanged"]`
- `data_provider.base.DataFetcherManager._call_fetcher_method(..., timeout_seconds: Optional[float], capability: str)`
- `data_provider.base.DataFetcherManager.get_realtime_quote(stock_code: str, *, log_final_failure: bool = True) -> UnifiedRealtimeQuote | None`
- `data_provider.base.RealtimeSourcePlan(route_source, physical_source, fetcher_name, request_code, kwargs, timeout_seconds, max_attempts, lightweight)`
- `data_provider.realtime_types.RealtimeFailureType`: `timeout/connection_error/rate_limited/empty/invalid_quote/not_supported/circuit_open/all_sources_failed`
- `src.config.Config` 环境变量字段：
  - `ANALYSIS_TASK_TIMEOUT_SECONDS`
  - `DATA_SOURCE_STOCK_NAME_TIMEOUT_SECONDS`
  - `DATA_SOURCE_DAILY_TIMEOUT_SECONDS`
  - `DATA_SOURCE_REALTIME_TIMEOUT_SECONDS`

### 3. Contracts

- 队列级超时：`ANALYSIS_TASK_TIMEOUT_SECONDS` 默认 `1200` 秒，`0` 关闭。超时任务复用 `failed`，不新增 API 状态枚举。
- 超时任务必须写入用户可理解的 `message` 和可排查的 `error`，并释放 `_analyzing_stocks` 中属于该 `task_id` 的去重锁。
- 迟到完成或迟到失败不能覆盖已进入终态的任务，也不能释放同一股票后续新任务的去重锁。
- manager 层 provider 调用预算默认值：股票名称 `8` 秒、日线 `45` 秒；这两项的 `0` 可关闭 manager 等待上限。
- 实时行情固定安全上限：轻量单标的源单次 `3` 秒、全量源单次 `8` 秒、单只标的整链路 `20` 秒。`DATA_SOURCE_REALTIME_TIMEOUT_SECONDS` 只可进一步收紧单次等待；`0` 表示不额外收紧，不能放大或关闭固定上限。
- 实时轻量源只对 `timeout/connection_error/rate_limited` 的快速失败重试 `1` 次；manager wait timeout 不重试同 plan。`empty/invalid_quote/not_supported/circuit_open` 不重试。
- `route_source` 是配置逻辑名，`physical_source` 是真实上游。`efinance` 与 `akshare_em` 均属于 `eastmoney`；同一物理上游发生网络、超时或限流后，本轮不得通过另一客户端重复请求，解析兼容错误才允许换客户端。
- A 股 ETF 的 `tencent`、`akshare_sina`、`akshare_em` 必须分别调用腾讯单标的、新浪单标的和 AkShare Eastmoney ETF 全量实现，禁止路由名不同但全部折叠到 `fund_etf_spot_em()`。
- 成功实时行情写入进程内线程安全 last-good 缓存；所有实时源失败后，只可读取同一市场交易日且年龄不超过 `1800` 秒的深拷贝，并标记 `is_stale=true`、`data_quality=stale`、`cache_age_seconds` 和低敏失败摘要。stale 结果不得回写续期。
- 无 quote 且请求诊断证明所有源均失败时，AnalysisContextPack 使用 `fetch_failed/realtime_quote_fetch_failed`；没有请求证据或功能关闭时才使用 `missing/realtime_quote_missing`。
- AkShare/efinance ETF 全量缓存 miss 使用进程内 singleflight；刷新者在锁外执行网络调用，等待者在自身预算内复用同一成功或失败结果。

### 4. Validation & Error Matrix

- `pending` / `processing` / `cancel_requested` 超过队列预算 -> `failed`，广播 `task_failed`，释放精确去重锁。
- 队列超时值非法 -> 记录 warning，保持当前配置。
- provider 调用超过能力预算 -> 抛出 `TimeoutError`，记录 provider/source/capability 后 fallback。
- 实时行情轻量源快速网络失败 -> 最多重试一次，然后切换独立物理源。
- 实时行情 manager wait timeout -> 跳过该 fetcher 和相同物理源，不启动重复后台调用。
- Eastmoney 客户端网络失败 -> 本轮其他 Eastmoney 客户端记录 `circuit_open` 并跳过；解析错误 -> 剩余预算内允许替代客户端。
- 全部实时源失败 + 合格 last-good -> 返回显式 `stale` quote；缓存超龄/跨交易日 -> 不使用缓存，返回 `None` 并映射 `fetch_failed`。
- 第一个 quote 已有正价格 + 补充字段失败 -> 保留主行情，不因补充失败返回 `None`。

### 5. Good/Base/Bad Cases

- Good：旧任务超时失败后，同一股票可重新提交，新任务的去重锁不会被旧任务迟到返回删除。
- Good：ETF 腾讯失败后新浪成功，返回实际 `source=akshare_sina`、`fallback_from=tencent`，诊断保留两个逻辑源和物理源。
- Base：首个实时源成功且字段完整，立即返回并写入 last-good；外部调用签名和 `REALTIME_SOURCE_PRIORITY` 格式不变。
- Base：实时源全部失败但同交易日 30 分钟内有 last-good，返回深拷贝 stale 行情并降低数据质量。
- Base：正常任务仍走 `completed`、`progress=100`、历史落库和运行流查询。
- Bad：只在查询接口修正状态，但提交重复检测仍被旧 `_analyzing_stocks` 拦截。
- Bad：manager 层 timeout 后马上再次调用同一 provider，导致多个后台线程等待同一个悬挂库调用。
- Bad：把 `efinance` 和 `akshare_em` 当作两个独立上游，在 Eastmoney 断连后连续轰击同一物理接口。
- Bad：把 stale 写回 last-good 并重置时间，使旧行情永久续期。

### 6. Tests Required

- 队列测试必须断言：超时状态、`error/message`、去重锁释放、迟到完成不覆盖终态、提交路径触发的超时会广播 `task_failed`。
- 数据源测试必须断言：股票名称、日线、实时行情 provider timeout 后继续 fallback；实时行情同一请求链路内不堆叠同 provider 的后续别名调用。
- 实时行情测试必须断言：ETF Tencent/Sina/EM 真路由、轻量源最多两次总尝试、空/无效 quote 不重试、3/8/20 秒上限、同物理上游网络失败去重、解析错误可换客户端、主行情不被补充失败丢弃。
- last-good 测试必须断言：同交易日 1800 秒边界、跨交易日拒绝、深拷贝、线程安全、stale 不回写。
- singleflight 测试必须断言：并发 ETF 全量 cache miss 只调用一次 AkShare/efinance 上游，等待者复用结果或在自身预算内超时。
- 跨层测试必须断言：ProviderRun 的 `route_source/physical_source/attempt/retry/budget_remaining_ms`，以及 quote 的 `available/fallback/stale/fetch_failed/missing` 映射和低敏摘要。
- 配置测试必须断言：新增环境变量默认值、解析、registry help key 和前端 locale help key 一致。

### 7. Wrong vs Correct

#### Wrong

```python
task.status = TaskStatus.COMPLETED
_analyzing_stocks.pop(dedupe_key, None)
```

#### Correct

```python
if task.status in IN_FLIGHT_STATUSES:
    task.status = TaskStatus.COMPLETED
    if _analyzing_stocks.get(dedupe_key) == task.task_id:
        del _analyzing_stocks[dedupe_key]
```

#### Wrong（实时行情）

```python
for source in ("tencent", "akshare_sina", "akshare_em"):
    return ak.fund_etf_spot_em()  # 逻辑多源，物理上游仍是同一个 Eastmoney
```

#### Correct（实时行情）

```python
plan = RealtimeSourcePlan(
    route_source="tencent",
    physical_source="tencent",
    fetcher_name="AkshareFetcher",
    request_code="159869",
    kwargs={"source": "tencent"},
    timeout_seconds=3.0,
    max_attempts=2,
    lightweight=True,
)
```

## 配置错误

- `.env` 读取失败时可以沿用当前环境变量并记录 warning，参考 `main.py::_read_active_env_values()`。
- 配置值无效时应提供可操作提示，避免只有底层 traceback。
- 新配置默认应做到“不配置也可运行，配置后增强能力”。

## 禁止项

- 不向 API 用户返回 Python traceback、密钥、webhook、token 或完整请求体。
- 不用裸 `except Exception: pass`。
- 不把所有错误都降级为 `None`、空列表或默认值。
- 不在多个入口重复实现错误响应格式。
