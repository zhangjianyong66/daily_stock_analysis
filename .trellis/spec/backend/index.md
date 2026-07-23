# Daily Stock Analysis 项目规范索引

本目录记录本仓库当前可执行、可验证的基础开发约定。后续 AI 或开发者开始改动前，应先按改动面读取对应文件；若发现规范与实际脚本、CI、代码不一致，以实际可执行内容为准，并同步修正本目录。

## 项目边界

本仓库是 Python 后端为主的单仓库项目，同时包含 Vite Web 前端、Electron 桌面端、Docker 镜像和 GitHub Actions 自动化。

主要入口：

- `main.py`：CLI、定时任务、分析流程和 Web/API 启动入口。
- `server.py` / `api/app.py`：FastAPI 应用入口与应用工厂。
- `src/`：核心业务、服务、仓储、报告、LLM、调度、配置与工具。
- `data_provider/`：行情、基本面、实时数据等数据源适配与 fallback。
- `api/`：FastAPI 路由、中间件、依赖和 Pydantic schema。
- `bot/`：机器人平台接入和命令分发。
- `apps/dsa-web/`：React + Vite Web 工作台。
- `apps/dsa-desktop/`：Electron 桌面端。
- `docker/`、`scripts/`、`.github/workflows/`：部署、构建、CI 和自动化。

## 必读规范

| 改动面 | 读取 |
| --- | --- |
| 新增或移动文件、判断代码放在哪里 | [Directory Structure](./directory-structure.md) |
| 运行、测试、构建、部署、CI 证据 | [Runtime and Deployment](./runtime-deployment.md) |
| Python/TypeScript 风格、测试要求、文档同步 | [Quality Guidelines](./quality-guidelines.md) |
| SQLite / SQLAlchemy / 仓储层改动 | [Database Guidelines](./database-guidelines.md) |
| 搜索供应商调用审计、余额告警、用量 API / Web 联动 | [Search Usage Audit](./search-usage-audit.md) |
| API 错误、异常传播、fallback 语义 | [Error Handling](./error-handling.md) |
| 日志初始化、级别、敏感信息 | [Logging Guidelines](./logging-guidelines.md) |
| 每日大盘上下文日期、历史复用、锁与 fail-open | [Daily Market Context](./daily-market-context.md) |
| 持仓/成交截图、Vision、`trade_time` 跨层改动 | [Portfolio Image Import](./portfolio-image-import.md) |
| A 股场内 ETF 日资金流与盘中主动流 | [ETF Capital Flow](./etf-capital-flow.md) |

## 开发前检查

- 先读 `AGENTS.md`，它是仓库 AI 协作规则的唯一真源。
- 先查现有实现、测试、脚本和文档，再新增实现；不要创建平行模块来绕开现有层次。
- 新配置项必须同步 `.env.example` 和相关文档。
- 用户可见行为、CLI/API、部署、通知、报告结构、Web UI 变化必须同步 `docs/CHANGELOG.md` 的 `[Unreleased]` 扁平条目。
- 修改 AI 协作治理资产时执行 `python scripts/check_ai_assets.py`。
- 未经明确确认，不执行 `git commit`、`git tag`、`git push`。

## 常用验证入口

- 后端完整本地门禁：`./scripts/ci_gate.sh`
- 后端最低语法检查：`python -m py_compile <changed_python_files>`
- 离线测试：`python -m pytest -m "not network"`
- Web：`cd apps/dsa-web && npm ci && npm run lint && npm run build`
- Desktop：先构建 Web 和后端产物，再在 `apps/dsa-desktop` 执行 `npm install && npm run build`

更多命令见 [Runtime and Deployment](./runtime-deployment.md)。
