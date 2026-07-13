# 运行、测试与部署规范

本文件记录当前仓库可执行的命令和部署约定。命令与脚本冲突时，以脚本和 workflow 实际内容为准，并同步修正文档。

## 本地运行

安装 Python 依赖：

```bash
pip install -r requirements.txt
```

复制配置模板：

```bash
cp .env.example .env
```

常用 CLI：

```bash
python main.py
python main.py --debug
python main.py --dry-run
python main.py --stocks 600519,hk00700,AAPL
python main.py --market-review
python main.py --no-market-review
python main.py --schedule
python main.py --serve
python main.py --serve-only
python main.py --webui
python main.py --webui-only
python main.py --backtest --backtest-code 600519
```

FastAPI 也可直接启动：

```bash
uvicorn server:app --reload --host 0.0.0.0 --port 8000
```

`main.py` 会加载 `.env`，支持 `ENV_FILE` 指向其他配置文件；本地代理通过 `USE_PROXY=true`、`PROXY_HOST`、`PROXY_PORT` 控制，GitHub Actions 环境会跳过代理注入。

## 后端验证

完整后端门禁：

```bash
./scripts/ci_gate.sh
```

可分阶段执行：

```bash
./scripts/ci_gate.sh syntax
./scripts/ci_gate.sh flake8
./scripts/ci_gate.sh deterministic
./scripts/ci_gate.sh offline-tests
```

CI 中 `backend-gate` 实际执行：

- `./scripts/ci_gate.sh syntax`
- `./scripts/ci_gate.sh flake8`
- `./scripts/ci_gate.sh deterministic`
- `./scripts/ci_gate.sh offline-tests`

最低本地检查：

```bash
python -m py_compile <changed_python_files>
python -m pytest -m "not network"
```

`scripts/test.sh` 还提供场景测试：

```bash
./scripts/test.sh code
./scripts/test.sh yfinance
./scripts/test.sh quick
./scripts/test.sh dry-run
./scripts/test.sh all
```

其中 `quick`、`dry-run`、行情/新闻/LLM 相关场景可能依赖网络和 API 配置；交付时要说明是否执行在线验证。

## Web 验证

Web 工作目录是 `apps/dsa-web/`，要求 Node `>=20.19.0 <27`、npm `>=10`。

```bash
cd apps/dsa-web
npm ci
npm run lint
npm run build
npm run test
```

CI 的 `web-gate` 只在 `apps/dsa-web/**` 变更时触发，并执行 `npm ci`、`npm run lint`、`npm run build`。

## 股票自动补全索引

`apps/dsa-web/public/stocks.index.json` 和后端静态入口共用同一份压缩索引契约，生成时必须保护已有市场覆盖面。

- `scripts/generate_index_from_csv.py --source tushare` 依赖 `data/stock_list_a.csv`、`data/stock_list_hk.csv`、`data/stock_list_us.csv` 等完整股票列表。
- 本地缺少完整 CSV 时直接写入，会只生成种子市场 / ETF 子集，可能覆盖掉 A 股、港股、美股条目。
- 刷新完整索引前先确认基础 CSV 可用，或先运行 `scripts/refresh_stock_index.py` 准备数据。
- 只补少量 seed 时，以现有完整 `stocks.index.json` 为基线合入，再校验总条目数和新增条目数。
- 新增 `market` 或 `assetType` 时，同步更新前端 `apps/dsa-web/src/types/stockIndex.ts`、后端 `src/services/stock_index_remote_service.py` 校验和相关测试。

## Desktop 验证

Desktop 工作目录是 `apps/dsa-desktop/`。

```bash
cd apps/dsa-desktop
npm install
npm run test
npm run build
```

桌面端打包依赖后端构建产物 `dist/backend/stock_analysis` 和 Web 静态资源。桌面相关改动默认应先验证 Web 构建，再验证 Electron 构建；受平台限制无法完整打包时，要说明缺口。

## Docker 部署

Dockerfile 是多阶段构建：

- `node:20-slim` 构建 `apps/dsa-web`。
- `python:3.11-slim-bookworm` 运行后端。
- 容器默认时区 `Asia/Shanghai`。
- 默认命令是 `python main.py --schedule`。
- 服务暴露 `8000`，持久化 `/app/data`、`/app/logs`、`/app/reports`。
- entrypoint 会修复挂载目录权限，然后降权为 `dsa` 用户运行。

Compose 常用命令：

```bash
docker-compose -f ./docker/docker-compose.yml up -d
docker-compose -f ./docker/docker-compose.yml up -d server
docker-compose -f ./docker/docker-compose.yml logs -f
docker-compose -f ./docker/docker-compose.yml down
docker-compose -f ./docker/docker-compose.yml exec -u dsa stock-analyzer bash
docker-compose -f ./docker/docker-compose.yml exec -u dsa stock-analyzer python main.py --no-notify
```

不要把 `../.env` 作为单文件 volume 挂载到 `/app/.env`，否则会破坏配置保存时的原子替换。Compose 使用 `env_file` 加载 `.env`。

## GitHub Actions 与发布

主要 workflow：

- `.github/workflows/ci.yml`：PR 阻断 CI，包含 `ai-governance`、`backend-gate`、`docker-build`、按路径触发的 `web-gate`。
- `.github/workflows/network-smoke.yml`：网络 smoke，非阻断观测项。
- `.github/workflows/docker-publish.yml`、`ghcr-dockerhub.yml`：镜像发布。
- `.github/workflows/desktop-release.yml`：桌面端发布。
- `.github/workflows/00-daily-analysis.yml`：每日分析任务。
- `.github/workflows/auto-tag.yml`、`create-release.yml`：版本和 Release。

自动 tag 默认 opt-in：只有 commit title 含 `#patch`、`#minor`、`#major` 才触发版本号更新。

## 配置约定

- 新增配置项必须同步 `.env.example` 和相关文档。
- `.env.example` 只放示例和空值，不提交真实密钥、token、webhook、账号或本机路径。
- Web 设置页会维护部分配置；修改配置语义时要评估 CLI、API、Web、Desktop、Docker、GitHub Actions。
- 公开绑定 `WEBUI_HOST=0.0.0.0` 且未启用管理认证时，`main.py`/`api.app` 会记录风险告警；不要把未认证服务暴露到不可信网络。
