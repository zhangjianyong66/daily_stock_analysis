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

## 配置错误

- `.env` 读取失败时可以沿用当前环境变量并记录 warning，参考 `main.py::_read_active_env_values()`。
- 配置值无效时应提供可操作提示，避免只有底层 traceback。
- 新配置默认应做到“不配置也可运行，配置后增强能力”。

## 禁止项

- 不向 API 用户返回 Python traceback、密钥、webhook、token 或完整请求体。
- 不用裸 `except Exception: pass`。
- 不把所有错误都降级为 `None`、空列表或默认值。
- 不在多个入口重复实现错误响应格式。
