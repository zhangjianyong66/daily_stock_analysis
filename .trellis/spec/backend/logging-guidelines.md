# 日志规范

本仓库使用 Python 标准 `logging`。模块级 logger 使用：

```python
logger = logging.getLogger(__name__)
```

## 初始化

统一日志配置在 `src/logging_config.py::setup_logging()`：

- 格式：`%(asctime)s | %(levelname)-8s | %(name)s | %(pathname)s:%(lineno)d | %(message)s`
- 日期格式：`%Y-%m-%d %H:%M:%S`
- 控制台输出到 stdout，debug 模式输出 DEBUG，否则 INFO。
- 常规日志文件 INFO，10MB 轮转，保留 5 个备份。
- debug 日志文件 DEBUG，50MB 轮转，保留 3 个备份。
- 默认降低 `urllib3`、`sqlalchemy`、`google`、`httpx` 噪音日志级别。
- LiteLLM 日志级别由 `LITELLM_LOG_LEVEL` 控制，无效值回退为 WARNING 并记录 warning。

`main.py` 启动早期先用 `_setup_bootstrap_logging()` 建立 stderr 日志，加载配置后再调用运行期日志初始化；文件日志初始化失败时降级为控制台并记录 warning。

## 日志级别

- `debug`：调试细节、分支选择、诊断信息。不得包含原始 prompt、密钥、token、webhook、Cookie。
- `info`：启动成功、任务开始/结束、关键配置路径、后台刷新成功等正常事件。
- `warning`：可恢复异常、配置风险、fallback、缓存刷新失败、权限修复失败等。
- `error`：请求或任务失败、前端资源不一致、未处理异常、无法完成的关键操作。
- `critical`：仅用于进程无法继续运行或数据安全高风险事件。

## 应记录的上下文

根据场景记录可排查但不敏感的信息：

- 股票代码、市场、数据源 provider、分析阶段。
- API 请求路径和方法。
- 配置文件路径、日志目录、数据库路径的相对或容器路径。
- Docker 权限修复结果、挂载目录是否可写。
- Web 静态资源一致性检查缺失的 asset 路径。
- fallback 原因和降级后的 source。

`api/middlewares/error_handler.py` 会记录未处理异常的路径、方法和堆栈；endpoint 中捕获未预期异常时使用 `logger.error(..., exc_info=True)`。

## 敏感信息

不要记录：

- API key、token、webhook、Cookie、OAuth 缓存内容。
- 完整 LLM prompt、完整 request body、用户导入的原始隐私数据。
- `.env` 文件完整内容。
- 未脱敏的 provider credential 或 Authorization header。

LLM prompt cache / diagnostics 相关配置在 `.env.example` 中强调只输出脱敏诊断；新增日志必须保持这一约束。

## 前端和桌面

Web/桌面问题应尽量在后端或桌面日志中留下可定位信息。`api/app.py::_check_frontend_assets_consistency()` 会在 `index.html` 引用缺失 asset 时记录 error，避免桌面端只表现为空白页。

Desktop 打包或运行日志不得写入仓库；临时截图和验收证据放 PR 描述、评论、artifact 或外部链接。
