# AGENTS.md

本文件用于约束本仓库的默认开发流程，目标是减少重复沟通、减少返工，并让改动和当前项目结构保持一致。

如果本文件与仓库中的脚本、工作流、代码现状不一致，以实际可执行内容为准，并在相关改动中顺手修正文档，避免规则继续漂移。

## 1. 硬规则

- 遵循现有目录边界：
  - 后端逻辑优先放在 `src/`、`data_provider/`、`api/`、`bot/`
  - Web 前端改动在 `apps/dsa-web/`
  - 桌面端改动在 `apps/dsa-desktop/`
  - 部署与流水线改动在 `scripts/`、`.github/workflows/`、`docker/`
- 未经明确确认，不执行 `git commit`、`git tag`、`git push`。
- commit message 使用英文，不添加 `Co-Authored-By`。
- 不写死密钥、账号、路径、模型名、端口或环境差异逻辑。
- 优先复用现有模块、配置入口、脚本和测试，不新增平行实现。
- 默认稳定性优先于“顺手优化”；非当前任务直接需要的重构、抽象和基础设施迁移一律克制。
- 新增配置项时，必须同步更新 `.env.example` 和相关文档。
- 涉及用户可见能力、CLI/API 行为、部署方式、通知方式、报告结构变化时，必须同步更新相关文档与 `docs/CHANGELOG.md`。
- 修改报告格式、报告渲染效果或 Web UI 界面时，PR 描述必须附受影响报告 / 页面截图；涉及前后差异时优先附前后对比，无法截图时说明原因与替代可视证据。
- Issue / PR 过程截图、审查截图、一次性验收截图和临时可视证据不得作为仓库文件合入；应放在 PR 描述、PR 评论、GitHub 附件、Actions artifact 或外部可访问证据链接中。产品长期文档确需保留的示意图除外，但文件名和文档语义必须脱离具体 issue / PR 编号。
- `docs/CHANGELOG.md` 的 `[Unreleased]` 段使用**扁平格式**：每条独立一行，格式为 `- [类型] 描述`，类型取值：`新功能`/`改进`/`修复`/`文档`/`测试`/`chore`；**禁止在 `[Unreleased]` 内新增 `### 类目标题`**，以减少并发 PR 的 merge 冲突。发版时由 maintainer 汇总整理成带标题的正式格式。
- `README.md` 只用于项目定位、核心能力总览、快速开始、主要入口、赞助/合作等首页级信息；非必要不更新 README，避免持续膨胀。
- 更细的模块行为、页面交互、专题配置、排障说明、字段契约、实现语义和边界条件，优先更新对应 `docs/*.md` 或专题文档，不写入 README。
- 变更中英双语文档之一时，需评估另一份是否需要同步；若未同步，交付说明里要写明原因。
- 注释、docstring、日志文案以清晰准确为准，不强制要求英文，但应与文件语境保持一致。

## 1.1 PR 标题规范（非阻断建议）

- 推荐使用 `<类型>: <修改内容>` 作为 PR 标题，例如 `fix: 修复大盘分析历史记录丢失`，优先类型为 `fix`/`feat`/`refactor`/`docs`/`chore`/`test`/`ci`。
- 标题应描述实际变更内容，建议不添加 `[codex]`、`codex`、`autocode`、`copilot` 或其他工具/agent 来源前缀。
- 该规范仅用于协作可读性与一致性提示，不应单独作为 review process blocker。

## 1.2 贡献质量底线

- 本仓库不接受以堆叠代码量、扩大 diff 面、补丁式响应 review 来替代真实设计收敛的 PR。
- 贡献质量以是否解决明确问题、是否最小化影响面、是否保持现有契约一致、是否覆盖真实风险路径为准；不以新增行数、文件数量、功能宣传或“看起来完整”为准。
- 请不要把本仓库当作低成本试验场、简历展示场或 contribution farming 场所。任何 PR 都必须证明作者理解当前系统契约，并完成基本自审、集成和验证。
- 使用 AI 辅助开发本身不是问题；问题是提交 AI 生成后未经人工语义审查、未验证、未收敛的代码。此类 PR 会按低质量提交处理。
- review 反馈后，不接受只在被指出的位置追加局部 patch。作者必须重新检查同一业务语义涉及的所有入口、配置、测试、文档、workflow 和用户可见路径。
- 如果一个 PR 在多轮 review 后仍持续出现同类契约漂移、重复 fallback、测试绕过真实风险层、PR body 与实际 diff 不一致等问题，维护者可以要求关闭重做，而不是继续逐点 review。

## 2. AI 协作资产治理

- `AGENTS.md` 是仓库内 AI 协作规则的唯一真源。
- `CLAUDE.md` 必须是指向 `AGENTS.md` 的软链接，用于兼容 Claude 生态。
- `.github/copilot-instructions.md` 与 `.github/instructions/*.instructions.md` 是 GitHub Copilot / Coding Agent 的镜像或分层补充；若与本文件冲突，以 `AGENTS.md` 为准。
- 仓库协作 skill 存放在 `.claude/skills/`，分析产物存放在 `.claude/reviews/`；前者可以入库，后者默认视为本地产物。
- 根目录 `SKILL.md` 与 `docs/openclaw-skill-integration.md` 属于产品或外部集成说明，不是仓库协作规则真源。
- 若未来新增 `.agents/skills/` 或其他 agent 专用目录，必须先明确单一真源，再通过脚本或镜像同步；禁止手工长期维护多份同义内容。
- 修改 AI 协作治理资产时，执行：

```bash
python scripts/check_ai_assets.py
```

## 3. 仓库速览

- 项目定位：股票智能分析系统，覆盖 A 股、港股、美股。
- 主流程：抓取数据 -> 技术分析/新闻检索 -> LLM 分析 -> 生成报告 -> 通知推送。
- 关键入口：
  - `main.py`：分析任务主入口
  - `server.py`：FastAPI 服务入口
  - `apps/dsa-web/`：Web 前端
  - `apps/dsa-desktop/`：Electron 桌面端
  - `.github/workflows/`：CI、发布、每日任务
- 核心职责：
  - `src/core/`：主流程编排
  - `src/services/`：业务服务层
  - `src/repositories/`：数据访问层
  - `src/reports/`：报告生成
  - `src/schemas/`：Schema / 数据结构
  - `data_provider/`：多数据源适配与 fallback
  - `api/`：FastAPI API
  - `bot/`：机器人接入
  - `scripts/`：本地脚本
  - `.github/scripts/`：GitHub 自动化脚本
  - `tests/`：pytest 测试
  - `docs/`：文档与说明

## 4. 常用命令

### 运行应用

```bash
python main.py
python main.py --debug
python main.py --dry-run
python main.py --stocks 600519,hk00700,AAPL
python main.py --market-review
python main.py --schedule
python main.py --serve
python main.py --serve-only
uvicorn server:app --reload --host 0.0.0.0 --port 8000
```

### 后端验证

```bash
pip install -r requirements.txt
pip install flake8 pytest
./scripts/ci_gate.sh
python -m pytest -m "not network"
python -m py_compile <changed_python_files>
```

- Trellis 升级产生的 `.trellis/.backup-*` 是 Git 忽略的本地恢复备份，Flake8 配置会排除该目录，避免历史模板代码阻断当前工作树的 `./scripts/ci_gate.sh`。
- 本机真实 `.env` 启用管理员认证或配置 LLM 路由时，LiteLLM 导入会自行读取仓库 `.env`，可能让离线 API/配置测试误报 401 或模型契约失败。需要隔离部署配置执行完整门禁时，使用：`tmp_env=$(mktemp); trap 'rm -f "$tmp_env"' EXIT; ENV_FILE="$tmp_env" LITELLM_MODE=PRODUCTION PATH="$PWD/.venv/bin:$PATH" ./scripts/ci_gate.sh`。

### Web / Desktop

```bash
cd apps/dsa-web
npm ci
npm run lint
npm run build

cd ../dsa-desktop
npm install
npm run build
```

### 股票自动补全索引

- `scripts/generate_index_from_csv.py --source tushare` 依赖 `data/stock_list_a.csv`、`data/stock_list_hk.csv`、`data/stock_list_us.csv` 等完整股票列表；本地缺少这些 CSV 时直接写入会只生成种子市场 / ETF 子集，可能覆盖 `apps/dsa-web/public/stocks.index.json` 的完整索引。
- 刷新完整索引前应先确认基础 CSV 可用，或使用 `scripts/refresh_stock_index.py` 先拉取 / 准备数据；只补少量离线 seed 时，应以现有完整 `stocks.index.json` 为基线合入，避免丢失 A 股、港股、美股条目。

### 实时行情多源与降级

- A 股 ETF 的 `tencent`、`akshare_sina`、`akshare_em` 必须分别路由到腾讯单标的、新浪单标的和 AkShare Eastmoney ETF 全量实现；`efinance` 与 `akshare_em` 虽是不同客户端，但同属 Eastmoney 物理上游。
- 实时行情公共安全上限为：腾讯/新浪等轻量源单次 10 秒、Eastmoney 等全量源单次 8 秒、单只标的整链路 20 秒；`DATA_SOURCE_REALTIME_TIMEOUT_SECONDS=0` 只表示不额外收紧，不能取消这些上限。
- 默认优先级中腾讯位于新浪之前时，腾讯等待 5 秒仍未完成会启动新浪并行 hedge；腾讯快速失败、空数据或无有效价格时立即启动新浪。腾讯与新浪的调用锁、遗留线程和限速状态按物理上游隔离，迟到结果不得覆盖 winner 或写入 last-good。
- 轻量源只对瞬时网络错误重试 1 次；空数据、无有效价格和不支持不重试。同一物理上游发生超时、连接失败或限流后，本轮不得通过另一个客户端重复请求。
- 所有实时源失败后，仅同一市场交易日且年龄不超过 30 分钟的进程内 last-good 行情可作为 `stale` 降级；stale 不得回写延长寿命，也不得伪装为实时成功。
- 实时源确已尝试但全部失败且无合格 stale 时，AnalysisContextPack 使用 `fetch_failed`；功能未启用或没有请求证据时才使用 `missing`。
- 实时行情目标回归：`python3 -m pytest tests/test_realtime_types.py tests/test_realtime_quote_fallback_logging.py tests/test_akshare_realtime_quote.py tests/test_etf_realtime_singleflight.py tests/test_fetcher_source_optimization.py tests/test_hk_realtime_routing.py tests/test_tw_market_support.py tests/test_run_diagnostics_p1.py tests/test_analysis_context_builder.py tests/test_pipeline_market_phase_context.py -q`。

### 搜索调用审计与余额告警

- 搜索供应商用量以真实外部 HTTP 请求为计数真源；自动重试、备用 Key、供应商 fallback 和 SearXNG 多实例尝试逐次记账，缓存、本地过滤、正文补抓和公共实例目录刷新不计数。
- 所有搜索 provider 的网络出口必须经过 `src/services/search_request_audit_service.py`；新增或替换 SDK 时必须证明能观察到每次物理请求，不能只在 `SearchResponse` 逻辑返回层补一条记录。
- 搜索审计会把深度脱敏后的完整业务请求/响应以明文 JSON 永久写入 `search_api_calls`；请求上限 256 KiB、响应上限 2 MiB，超限保存预览、原始脱敏大小和 SHA-256。普通日志禁止重复输出完整查询或响应。
- 错误分类以供应商响应语义优先于 HTTP 状态；Anspire 401 正文明示免费额度/充值余额为 0 时必须归类为 `quota_exhausted`，不能显示为 Key 无效。
- 余额、认证、权限和账户停用首次失败立即激活故障；限流、超时、连接失败、5xx 需同供应商/Key 在 10 分钟内连续 3 次。成功请求会清空该 Key 的瞬时计数并恢复故障。
- 搜索汇总沿用现有可选认证边界；完整出入参、复制、CSV 和单条 JSON 下载必须 `ADMIN_AUTH_ENABLED=true` 且管理员已登录，没有桌面端例外。
- 搜索审计目标回归：`python3 -m pytest tests/test_search_usage_storage.py tests/test_search_usage_service.py tests/test_search_usage_api.py tests/test_anspire_search.py tests/test_search_tavily_provider.py tests/test_search_serpapi_provider.py tests/test_search_searxng.py -q`。

### 私有 SearXNG 分层搜索降本

- `docker/docker-compose.yml` 提供可选 `searxng` profile，使用固定官方镜像 tag + digest；服务不发布宿主机端口、不依赖 Valkey/Redis，也不是 `server` / `analyzer` 启动硬依赖。启动示例：`docker compose -f docker/docker-compose.yml --profile searxng up -d server searxng`。
- 私有实例配置位于 `docker/searxng/settings.yml`，只启用百度、Bing、Bing News、DuckDuckGo，开启 JSON，默认中文，关闭 public instance、limiter 与 Granian access log；容器内部地址为 `http://searxng:8080`。
- `SEARCH_ROUTING_MODE=legacy` 保持现有搜索语义；`searxng_first_cn` 只覆盖 A 股与 A 股 ETF，并要求显式 `SEARXNG_BASE_URLS`。公共实例不会成为低成本主路由，其他市场继续 legacy。
- 低成本链路每个维度先查私有 SearXNG；最新消息、公告、风险要求直接且及时结果，机构分析、业绩预期、行业分析有 1 条合格结果即可。单次 SearXNG 默认 6 秒且不在 DSA 侧重试同一实例，单股总预算默认 30 秒。
- Anspire 每日预算只在 `searxng_first_cn` 启用，按北京时间自然日和物理请求持久化预留：默认 30 次预警、50 次硬上限。预算阻断不写伪造 `search_api_calls`；预留失败对付费请求 fail-closed，已有 SearXNG 结果继续 best-effort 返回。
- 审计边界为：DSA → SearXNG 每次请求写一条 `search_api_calls`；SearXNG → 内部四个引擎的扇出由容器日志观察。回滚只需设 `SEARCH_ROUTING_MODE=legacy` 并停止 `searxng` profile，无需删除审计或预算历史。
- 目标回归：`.venv/bin/python -m pytest tests/test_search_paid_budget.py tests/test_search_searxng.py tests/test_search_news_freshness.py tests/test_search_usage_storage.py tests/test_search_usage_service.py tests/test_anspire_search.py -q`。

### 持仓与成交截图导入

- Web 持仓图片导入只支持活跃 `cn/CNY` 账户；持仓初始化要求账户没有任何交易流水，成交增量只接受实际成交记录。
- 图片能力必须显式配置 `VISION_MODEL`，不会使用 `LITELLM_MODEL` 文本主模型兜底；`OPENAI_VISION_MODEL` 仅为废弃兼容别名，Hermes Vision 尚未验证。
- `VISION_API_MODE` 默认为 `chat_completions`；设为 `responses` 时，`VISION_MODEL` 必须精确匹配非 legacy、非 Hermes LLM Channel route，并只复用该 deployment 的 Base URL、API Key 与 Extra Headers，不按域名/模型猜测或跨协议 fallback。
- LiteLLM Responses 路径在干净 Docker 镜像中依赖显式安装的 `orjson`；`requirements.txt` 必须保留该依赖，`docker/Dockerfile` 构建阶段必须执行导入检查，避免 LiteLLM 小版本漂移后直到真实图片调用才暴露缺包。
- 设置页渠道连接、JSON/Tools/Stream/Vision 能力检测均携带渠道 Extra Headers；Vision 探针使用不含业务数据的 32×32 内置空白图。
- 每批支持 1-5 张 JPEG、PNG、WebP 或 GIF，单文件最大 5MB。原图、base64 和模型原始响应不得持久化或写入普通日志。
- 图片识别使用进程内单 worker 和全局唯一槽，持仓/成交及所有账户共享；新 API 快速返回 HTTP 202，`review_required` 在确认导入或放弃前不自动过期，服务重启会丢失任务和草稿。
- Vision 单次上限 300 秒、每图最多 2 次，只对 timeout/connection 瞬时错误重试一次；图片按上传顺序串行，整批 deadline 为 60 分钟。取消是尽力语义，当前阻塞调用返回前继续占槽，迟到结果不得覆盖终态。
- 校对草稿保存在服务端内存并使用 `draft_revision` 乐观锁；Web 保存必须串行，commit 携带 `task_id/expected_revision`，失败文件标记移除后才允许提交。旧同步 parse 标记 deprecated，但与异步 API 共享槽位和识别编排。
- 后端目标回归：`python3 -m pytest tests/test_vision_extraction_service.py tests/test_portfolio_screenshot_import_service.py tests/test_portfolio_image_task_manager.py tests/test_portfolio_api.py tests/test_analysis_api_contract.py -q`。
- 前端目标回归：`cd apps/dsa-web && npm run test -- src/api/__tests__/error.test.ts src/api/__tests__/portfolio.test.ts src/components/portfolio/__tests__/PortfolioImageImportDialog.test.tsx src/pages/__tests__/PortfolioPage.test.tsx src/hooks/__tests__/useTaskStream.test.tsx src/utils/__tests__/portfolioFormat.test.ts`。

### Docker 构建代理

- Docker Compose 的 `server` 端口优先使用 `.env` 中的 `WEBUI_PORT`；旧部署仍可通过 `API_PORT` 兼容覆盖。排查 8000 端口冲突时，先确认 `WEBUI_PORT`、`API_PORT` 与 `docker-compose config` 渲染结果是否一致。
- `scripts/docker-up.sh` 默认设置 `DOCKER_BUILD_NETWORK=host`、`DOCKER_BUILD_HTTPS_PROXY=http://127.0.0.1:10808`、空 `DOCKER_BUILD_HTTP_PROXY` / `DOCKER_BUILD_http_proxy`，并把 Debian apt 源切到清华 HTTPS 镜像，确保构建阶段可通过宿主机 10808 代理访问 npm、PyPI/GitHub 与 apt 源。
- `scripts/docker-up.sh` 仍会补齐宿主机 `HTTP_PROXY` / `HTTPS_PROXY` / `NO_PROXY` 及小写同名变量，构建代理以脚本默认值为准；显式导出的 `DOCKER_BUILD_*`、`DEBIAN_APT_MIRROR`、`DEBIAN_SECURITY_APT_MIRROR` 优先级高于脚本默认值。
- 如需覆盖构建网络，可显式执行：`DOCKER_BUILD_NETWORK=default ./scripts/docker-up.sh restart` 或 `DOCKER_BUILD_NETWORK=host ./scripts/docker-up.sh restart`。
- 运行中的 Docker 容器不会自动继承宿主机系统代理；Linux bridge 网络下访问宿主机本地代理通常使用 `172.17.0.1:<端口>`，例如在 `.env` 中配置 `HTTP_PROXY=http://172.17.0.1:10808` / `HTTPS_PROXY=http://172.17.0.1:10808`，重启容器后生效。

### 本机 / ECS2 当前部署备注

- 本机 Docker 中 `daily-stock-analysis` 的 Web/API 服务通常由 `stock-server` 容器提供，启动命令为 `python main.py --serve-only --host 0.0.0.0 --port ${WEBUI_PORT:-${API_PORT:-8000}}`。
- 当前本机 8000 端口可能被其他项目占用；如 `.env` 中设置 `WEBUI_PORT=8001` / `API_PORT=8001`，`stock-server` 会映射为宿主机 `0.0.0.0:8001->8001/tcp`。
- 本机 frpc 由用户级 systemd 服务 `~/.config/systemd/user/frpc.service` 管理，配置入口为 `~/.frpc/frpc.ini`。该文件包含 frps token，禁止提交仓库。
- 当前本机 frpc 代理包含本机 SSH、其他项目域名以及本项目 `[dsa-stock]`。`[dsa-stock]` 使用 `type = http`、`local_ip = 127.0.0.1`、`local_port = 8001`、`custom_domains = stock.zhangjianyong.top`，通过 ECS2 frps HTTP vhost 暴露 DSA。
- ECS2 的历史/运维记录在 `/home/zhangjianyong/project/server_environment/docs/ecs2-environment.md`；ECS2 nginx 常用配置目录为 `/usr/local/nginx/conf/conf.d/`，frps 配置为 `/etc/frp/frps.ini`。
- ECS2 上 `stock.zhangjianyong.top` 当前由 nginx `/usr/local/nginx/conf/conf.d/stock.conf` 管理，HTTPS 入口反代到 ECS2 frps HTTP vhost `http://127.0.0.1:8080`，再由本机 frpc `[dsa-stock]` 转发到本机 DSA `127.0.0.1:8001`。
- `stock.zhangjianyong.top` 证书使用 Let's Encrypt，nginx 证书路径为 `/usr/local/nginx/conf/cert/stock.zhangjianyong.top.pem` 和 `/usr/local/nginx/conf/cert/stock.zhangjianyong.top.key`；ECS2 `/root/ssl_auto_renew/domains.conf` 已包含该域名映射，root crontab 继续执行 `/root/ssl_auto_renew/ssl_auto_renew.sh apply auto` 与 `check`。

### PR / CI 证据

```bash
gh pr view <pr_number>
gh pr checks <pr_number>
gh run view <run_id> --log-failed
```

## 5. 默认工作流

1. 先判断任务类型：`fix / feat / refactor / docs / chore / test / review`
2. 先读现有实现、配置、测试、脚本、工作流和文档，再动手修改。
3. 识别改动边界：后端 / API / Web / Desktop / Workflow / Docs / AI 协作资产。
4. 先判断是否命中高风险区域：配置语义、API / Schema、数据源 fallback、报告结构、认证、调度、发布流程、桌面端启动链路。
5. 只做和当前任务直接相关的最小改动，不顺手夹带无关重构。
6. 如果发现文档、脚本、工作流描述不一致，优先信任实际代码与工作流，再决定是否顺手修正文档。
7. 改完后按下面的验证矩阵执行检查。
8. 最终交付默认要说明：
   - 改了什么
   - 为什么这么改
   - 验证情况
   - 未验证项
   - 风险点
   - 回滚方式

## 6. 验证矩阵

### 分层测试原则

- 不要求在每次命令执行、每轮修改或每个中间步骤后运行全量测试套件；测试范围应与当前改动阶段和影响面匹配。
- 开发迭代阶段优先运行受影响模块的定向测试，并补充必要的语法检查、类型检查或 lint，以便快速发现局部问题。
- 单个功能或修复完成后，运行覆盖该功能及其直接上下游契约的回归测试；修复失败用例后，先重跑失败用例和相关用例。
- 最终交付、提交或创建 / 更新 PR 前，至少执行一次覆盖实际改动面的完整门禁。完整门禁按后端、Web、Desktop、工作流等改动面选择，不要求为未受影响的技术栈机械执行测试。
- 涉及公共配置、API / Schema、认证、调度、数据源 fallback、报告结构、共享基础模块，或无法可靠判断影响范围时，应扩大回归范围，并执行相关改动面的全量离线测试。
- 网络测试和三方服务 smoke 默认与离线门禁分开，仅在相关改动、发布验证或明确要求时执行；不得用不稳定的在线测试替代确定性离线测试。
- 纯文档改动不强制运行代码测试；AI 协作治理资产仍须执行本节指定的治理校验。

### CI 覆盖原则

当前仓库 CI 主要包含：

| 检查项 | 来源 | 说明 | 是否阻断 |
| --- | --- | --- | --- |
| `ai-governance` | `.github/workflows/ci.yml` | 校验 `AGENTS.md` / `CLAUDE.md` / `.github` 指令 / `.claude/skills` 关系 | 是 |
| `backend-gate` | `.github/workflows/ci.yml` | 执行 `./scripts/ci_gate.sh` | 是 |
| `docker-build` | `.github/workflows/ci.yml` | Docker 构建与关键模块导入 smoke | 是 |
| `web-gate` | `.github/workflows/ci.yml` | 前端改动时执行 `npm run lint` + `npm run build` | 是（触发时） |
| `network-smoke` | `.github/workflows/network-smoke.yml` | `pytest -m network` + `scripts/test.sh quick` | 否，观测项 |
| `pr-review` | `.github/workflows/pr-review.yml` | PR 静态检查 + AI 审查 + 自动标签 | 否，辅助项 |

若 PR 上已有对应 CI 结果，可直接引用 CI 结论；若 CI 未覆盖改动面，或本地与 CI 环境差异较大，需要补充说明本地验证与缺口。

### 按改动面执行

- Python 后端改动：
  - 适用范围：`main.py`、`src/`、`data_provider/`、`api/`、`bot/`、`tests/`
  - 开发迭代：优先运行受影响测试；最终交付前默认执行 `./scripts/ci_gate.sh`
  - 最低要求：`python -m py_compile <changed_python_files>`
  - 若影响 API、任务编排、报告生成、通知发送、数据源 fallback、认证、调度，交付说明中要写明是否覆盖了对应路径。

- Web 前端改动：
  - 适用范围：`apps/dsa-web/`
  - 开发迭代：优先运行受影响测试；最终交付前默认执行 `cd apps/dsa-web && npm ci && npm run lint && npm run build`
  - 若涉及 API 联调、路由、状态管理、Markdown/图表渲染或认证状态，交付说明中要明确说明联动面和未覆盖风险。

- 桌面端改动：
  - 适用范围：`apps/dsa-desktop/`、`scripts/run-desktop.ps1`、`scripts/build-desktop*.ps1`、`scripts/build-*.sh`、`docs/desktop-package.md`
  - 默认执行：先构建 Web，再构建桌面端
  - 如受平台限制未能完整验证，需要明确说明是否验证了 Web 构建产物、Electron 构建以及 Release 工作流影响。

- API / Schema / 认证联动改动：
  - 适用范围：`api/**`、`src/schemas/**`、`src/services/**`、`apps/dsa-web/**`、`apps/dsa-desktop/**`
  - 至少覆盖对应后端验证 + 受影响客户端构建验证。
  - 若涉及登录、Cookie、会话、轮询状态、字段增删或枚举变化，必须明确写出兼容性影响。

- 文档与治理文件改动：
  - 适用范围：`README.md`、`docs/**`、`AGENTS.md`、`.github/copilot-instructions.md`、`.github/instructions/**`、`.claude/skills/**`
  - 不强制代码测试。
  - 需确认命令、配置项、文件名、工作流名称与实际仓库一致。
  - 改动 AI 协作治理资产时，执行 `python scripts/check_ai_assets.py`。

- 工作流 / 脚本 / Docker 改动：
  - 适用范围：`.github/**`、`scripts/**`、`docker/**`
  - 运行最接近改动面的本地验证。
  - 交付时说明影响了哪条流水线、发布路径或部署路径。
  - 若未执行 Docker / GitHub Actions 相关验证，明确说明原因与潜在风险。

- 网络或三方依赖相关改动：
  - 先跑离线或确定性检查。
  - 优先确认 timeout、retry、fallback、异常文案、降级路径是否仍然成立。
  - 若未执行在线验证，必须明确写出原因。

## 7. 稳定性护栏

- 配置与运行入口：
  - 修改 `.env` 语义、默认值、CLI 参数、服务启动方式、调度语义时，要同时评估本地运行、Docker、GitHub Actions、API、Web、Desktop 的影响。
  - 新配置优先做到“不配置也可运行，配置后增强能力”，避免叠加开关和互斥模式。

- 数据源与 fallback：
  - 修改 `data_provider/` 时，要关注数据源优先级、失败降级、字段标准化、缓存与超时策略。
  - 单一数据源失败不应拖垮整个分析流程，除非需求明确要求 fail-fast。

- API / Web / Desktop 兼容：
  - 改 API / Schema / 认证 / 报告载荷时，要同时检查后端、Web、Desktop 的兼容性。
  - 默认优先追加字段、保留旧字段或提供兼容层，避免无提示破坏现有客户端。

- 报告 / Prompt / 通知：
  - 修改报告结构、Prompt、提取器、通知模板、机器人链路时，要检查上游输入与下游消费方是否仍兼容。
  - 单一通知渠道失败不应拖垮整个分析主流程，除非需求明确要求 fail-fast。
  - 修改 `src/services/image_stock_extractor.py` 中 `EXTRACT_PROMPT` 时，要在 PR 描述中附完整最新 prompt。

- 工作流 / 发布 / 打包：
  - 修改自动 tag、Release、Docker 发布、日常分析或桌面端打包流程时，要评估触发条件、产物路径、权限边界和回滚方式。
  - 自动 tag 默认保持 opt-in：只有 commit title 含 `#patch`、`#minor`、`#major` 才触发版本号更新，除非需求明确要求改变发布策略。

## 8. Issue / PR / Skill 工作流

- 仓库内已有以下 skill，可优先复用：
  - `.claude/skills/analyze-issue/SKILL.md`
  - `.claude/skills/analyze-pr/SKILL.md`
  - `.claude/skills/fix-issue/SKILL.md`
- 如果任务明确是 issue 分析、PR 审查、issue 修复，优先按对应 skill 执行，并将产物保存到 `.claude/reviews/`。
- skill 中的命令、模板、验证顺序和交付结构必须与 `AGENTS.md` 保持一致。
- 每次进行 PR 创建 / 更新、PR 审查或 issue 分析前，必须先同步最新代码基线：先检查工作区状态并执行 `git fetch --all --prune`；若工作区干净且当前分支可 fast-forward，则执行 `git pull --ff-only`。如存在本地改动、冲突状态、未跟踪风险文件或无法 fast-forward，不得强行切分支、stash、reset 或覆盖本地状态；PR 审查 / issue 分析可改用已 fetch 的远端 refs/PR head 做分析，并在分析文档中明确记录未更新本地工作树的原因、当前本地 HEAD 与使用的远端基线；PR 创建 / 更新应先说明当前分支与目标基线差异，必要时请求用户确认 rebase、merge 或继续基于当前分支推进。
- skill 默认优先读取 CI / 工作流证据，再决定是否补本地验证。
- 除上述 PR 创建 / 更新、PR 审查 / issue 分析的安全 fast-forward 同步外，skill 不得默认执行 `git pull`、`git push`、`git tag`、`gh pr create` 等会改变远端或当前分支状态的操作；这些操作必须要求用户确认。
- PR 审查默认顺序：
  1. 必要性
  2. 关联性
  3. 标题建议（`<类型>: <修改内容>`，且不含工具/agent 前缀；不作为硬性阻断项）
  4. 描述完整性（对照 `.github/PULL_REQUEST_TEMPLATE.md`）
  5. 验证证据
  6. 实现正确性
  7. 合入判定
- 对 `fix` 类 PR，必须说明：原问题、根因、修复点、回归风险。
- 合入阻断条件：
  - 正确性或安全性问题
  - 阻断型 CI 未通过
  - PR 描述与实际改动内容实质性矛盾
  - 缺少回滚方案
  - 反复出现未收敛的契约漂移、补丁堆叠或验证证据失真

## 8.1 Review 反馈处理与补丁堆叠禁止

当你处理 review 反馈时，禁止只在 reviewer 点名的位置追加局部 patch 后声称“已全部修复”。你必须先重新理解 reviewer 指出的业务契约，再检查同一语义涉及的所有入口、配置、测试、文档、workflow 和用户可见路径。

收到 review 反馈后，必须按以下顺序处理：

1. 逐条列出 reviewer 指出的原问题。
2. 说明根因，不能只描述“改了哪几行”。
3. 找出同一语义影响的所有相关路径，例如 runtime、API/Web、CLI、diagnostics、workflow、docs、tests。
4. 修复完整契约，而不是只修复当前失败测试或当前评论行。
5. 补充能覆盖 reviewer 反例的回归测试、最终入口验证，或明确说明无法验证的原因。
6. 同步更新 PR body，保证 scope、验证结果、兼容性、风险和回滚方案与当前 head 一致。

如果你无法完成上述收敛，不要继续堆叠补丁，不要声称 ready for merge。应主动说明当前 PR 需要拆分、关闭重做，或请求维护者确认新的最小范围。

以下行为会被视为低质量 PR：

- 用 broad fallback、静默降级、`return False/None/[]` 掩盖不清晰的契约。
- 测试 mock 掉真实风险层，只证明局部实现通过。
- CI 通过后声称问题已关闭，但没有覆盖 reviewer 指出的反例。
- PR body 与实际 diff、验证结果或兼容风险不一致。
- review 后继续追加零散 patch，而不是重新收敛完整语义。
- 同一业务语义在 runtime、Web/API、docs、workflow、tests 中表现不一致。

CI 通过只能说明自动检查通过，不能替代人工语义收敛，也不能单独证明 reviewer 指出的反例已经关闭。

## 9. 交付与发布

- 默认交付结构：
  - `改了什么`
  - `为什么这么改`
  - `验证情况`
  - `未验证项`
  - `风险点`
  - `回滚方式`
- 如果是 `docs` 任务，可直接写：`Docs only, tests not run`，但仍需说明是否核对了命令和文件名。
- 自动 tag 默认不触发，只有 commit title 包含 `#patch`、`#minor`、`#major` 才会触发版本号更新。
- 手动打 tag 必须使用 annotated tag。
- 用户可见变更优先通过 PR 合入，并补齐 label 与验证说明。
<!-- TRELLIS:START -->
# Trellis Instructions

These instructions are for AI assistants working in this project.

This project is managed by Trellis. The working knowledge you need lives under `.trellis/`:

- `.trellis/workflow.md` — development phases, when to create tasks, skill routing
- `.trellis/spec/` — package- and layer-scoped coding guidelines (read before writing code in a given layer)
- `.trellis/workspace/` — per-developer journals and session traces
- `.trellis/tasks/` — active and archived tasks (PRDs, research, jsonl context)

If a Trellis command is available on your platform (e.g. `/trellis:finish-work`, `/trellis:continue`), prefer it over manual steps. Not every platform exposes every command.

If you're using Codex or another agent-capable tool, additional project-scoped helpers may live in:
- `.agents/skills/` — reusable Trellis skills
- `.codex/agents/` — optional custom subagents

Managed by Trellis. Edits outside this block are preserved; edits inside may be overwritten by a future `trellis update`.

<!-- TRELLIS:END -->
