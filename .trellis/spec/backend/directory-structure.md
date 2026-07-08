# 目录结构规范

本仓库按运行面和职责分层。新增文件时优先放入现有目录，不要新增同义平行目录。

## 顶层入口

- `main.py` 是主入口，负责 CLI 参数、`.env` 启动加载、代理开关、日志初始化、分析流程、定时任务和 `--serve/--serve-only` Web/API 启动。
- `server.py` 是 FastAPI 服务入口；应用工厂在 `api/app.py`。
- `webui.py` 是 WebUI 相关兼容入口。
- `requirements.txt` 是 Python 运行依赖真源；CI 额外依赖在 `.github/requirements-ci.txt`。
- `pyproject.toml` 存放 Black、isort、Bandit 等 Python 工具配置。

## 后端目录

- `src/core/`：主流程编排，例如分析 pipeline。
- `src/services/`：业务服务层。服务负责输入归一化、业务校验、跨仓储/数据源编排和 DTO 字典输出。示例：`src/services/portfolio_service.py`、`src/services/system_config_service.py`。
- `src/repositories/`：数据访问层。仓储负责 SQLAlchemy 查询、事务和数据库异常转换。示例：`src/repositories/portfolio_repo.py`、`src/repositories/decision_signal_repo.py`。
- `src/schemas/`：后端内部 schema / 数据结构；API schema 放在 `api/v1/schemas/`。
- `src/reports/`：报告生成、渲染、报告结构相关逻辑。
- `src/llm/`：生成后端、LiteLLM、本地 CLI backend、用量统计和 provider 相关逻辑。
- `src/agent/`：Agent 执行、工具、策略和流式事件。
- `src/data/`：股票索引、静态数据加载和数据文件访问。
- `src/utils/`：跨模块通用工具。新增工具前必须先搜索是否已有等价函数。
- `src/notification_sender/`：通知渠道发送实现。
- `src/patches/`：第三方兼容补丁，需保持作用域清晰并有验证。

## 数据源与机器人

- `data_provider/` 存放多数据源适配器。新增数据源应沿用现有 fetcher 命名和 fallback 语义，例如 `akshare_fetcher.py`、`yfinance_fetcher.py`、`longbridge_fetcher.py`。
- `data_provider/base.py` 存放股票代码规范化等共享数据源契约。
- `bot/commands/` 存放机器人命令；新增命令要接入 `bot/dispatcher.py` 并复用 `bot/commands/base.py` 模式。
- `bot/platforms/` 存放平台适配，例如钉钉、飞书、Discord。

## API 目录

- `api/app.py` 创建 FastAPI app，注册 CORS、认证、错误处理、静态前端资源和生命周期任务。
- `api/v1/router.py` 汇总 v1 路由。
- `api/v1/endpoints/` 存放 endpoint。Endpoint 只做参数接收、调用 service、异常映射和 response model 返回。
- `api/v1/schemas/` 存放 Pydantic 请求/响应模型。字段增删要同步前端类型与文档。
- `api/v1/errors.py` 提供 `api_error()`、`error_body()`、`error_json_response()` 统一错误 helper。
- `api/middlewares/` 存放认证、错误处理中间件。

## Web 和 Desktop

- `apps/dsa-web/` 是 React + Vite 工作台。源码在 `apps/dsa-web/src/`，公共静态资源在 `apps/dsa-web/public/`，构建命令在 `package.json`。
- `apps/dsa-web/src/types/` 存放前端 API 类型。后端 schema 变化时必须检查这些类型。
- `apps/dsa-desktop/` 是 Electron 桌面端，`main.js` 和 `preload.js` 是主入口，`renderer/` 存放桌面加载页，`package.json` 描述 electron-builder 打包资源。

## 脚本、部署和文档

- `scripts/` 是本地构建、测试、检查、索引生成和桌面打包脚本。
- `.github/workflows/` 是 CI、Release、Docker 发布、每日分析等工作流。
- `docker/` 存放 Dockerfile、Compose 和容器 entrypoint。
- `docs/` 存放模块说明、部署说明、配置指南、排障和用户文档。非首页级细节优先写入 `docs/*.md`，不要膨胀 `README.md`。
- `strategies/` 存放内置策略 YAML；修改策略需检查策略 README 和消费方。

## 命名与放置约定

- Python 文件名使用 `snake_case.py`，类名使用 `PascalCase`，常量使用 `UPPER_SNAKE_CASE`。
- API endpoint、schema、service、repository 应按业务域命名并保持同名域聚合，例如 `portfolio.py`、`portfolio_service.py`、`portfolio_repo.py`。
- 新增跨层字段时，至少检查 API schema、service 输出、前端类型、测试和文档。
- 不要把数据库查询写进 API endpoint；不要让 Web/Desktop 直接依赖数据库结构。
