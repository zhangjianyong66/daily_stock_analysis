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
- `src.config.Config` 环境变量字段：
  - `ANALYSIS_TASK_TIMEOUT_SECONDS`
  - `DATA_SOURCE_STOCK_NAME_TIMEOUT_SECONDS`
  - `DATA_SOURCE_DAILY_TIMEOUT_SECONDS`
  - `DATA_SOURCE_REALTIME_TIMEOUT_SECONDS`

### 3. Contracts

- 队列级超时：`ANALYSIS_TASK_TIMEOUT_SECONDS` 默认 `1200` 秒，`0` 关闭。超时任务复用 `failed`，不新增 API 状态枚举。
- 超时任务必须写入用户可理解的 `message` 和可排查的 `error`，并释放 `_analyzing_stocks` 中属于该 `task_id` 的去重锁。
- 迟到完成或迟到失败不能覆盖已进入终态的任务，也不能释放同一股票后续新任务的去重锁。
- manager 层 provider 调用预算默认值：股票名称 `8` 秒、日线 `45` 秒、实时行情 `12` 秒；`0` 关闭该层兜底。
- provider 调用超时后记录失败并尝试下一个 provider。provider 内部已有请求级 retry 可保留；manager 层不得立即对同一已悬挂 provider 叠加重复调用。

### 4. Validation & Error Matrix

- `pending` / `processing` / `cancel_requested` 超过队列预算 -> `failed`，广播 `task_failed`，释放精确去重锁。
- 队列超时值非法 -> 记录 warning，保持当前配置。
- provider 调用超过能力预算 -> 抛出 `TimeoutError`，记录 provider/source/capability 后 fallback。
- 实时行情同一请求链路内某 provider 超时 -> 跳过该 provider 的后续实时源别名，继续尝试其他 provider。

### 5. Good/Base/Bad Cases

- Good：旧任务超时失败后，同一股票可重新提交，新任务的去重锁不会被旧任务迟到返回删除。
- Base：正常任务仍走 `completed`、`progress=100`、历史落库和运行流查询。
- Bad：只在查询接口修正状态，但提交重复检测仍被旧 `_analyzing_stocks` 拦截。
- Bad：manager 层 timeout 后马上再次调用同一 provider，导致多个后台线程等待同一个悬挂库调用。

### 6. Tests Required

- 队列测试必须断言：超时状态、`error/message`、去重锁释放、迟到完成不覆盖终态、提交路径触发的超时会广播 `task_failed`。
- 数据源测试必须断言：股票名称、日线、实时行情 provider timeout 后继续 fallback；实时行情同一请求链路内不堆叠同 provider 的后续别名调用。
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

## 配置错误

- `.env` 读取失败时可以沿用当前环境变量并记录 warning，参考 `main.py::_read_active_env_values()`。
- 配置值无效时应提供可操作提示，避免只有底层 traceback。
- 新配置默认应做到“不配置也可运行，配置后增强能力”。

## 禁止项

- 不向 API 用户返回 Python traceback、密钥、webhook、token 或完整请求体。
- 不用裸 `except Exception: pass`。
- 不把所有错误都降级为 `None`、空列表或默认值。
- 不在多个入口重复实现错误响应格式。
