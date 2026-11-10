# 自建 SearXNG 分层搜索降本

## Goal

在不明显降低 A 股新闻、公告和风险情报质量的前提下，将 A 股及 A 股 ETF 的搜索链路改为“自建 SearXNG 优先、Anspire 付费兜底”，把正常单股分析的付费搜索成本从约 0.15 元降低至少 70%，同时用明确的延迟预算、每日付费上限和可回滚配置控制稳定性风险。

## Background

- 当前普通分析通过 `SearchService.search_comprehensive_intel(..., max_searches=5)` 发起最多 5 个情报维度搜索，入口位于 `src/core/pipeline.py:562`；本机 2026-07-16 审计数据为 90 次 Anspire 物理请求 / 18 次业务搜索，平均每次业务搜索 5 次。按每次 0.03 元计算，基线约为 0.15 元/只股票。
- 当前 Provider 顺序把 Anspire 固定插到首位（`src/search_service.py:2439`），多维情报搜索按 Provider 轮转而不是按成本分层（`src/search_service.py:4241`）。仅增加一个 SearXNG 容器不能完整实现“免费源优先、付费源兜底”。
- 项目已经具备自建与公共 SearXNG Provider、JSON 解析、多实例 fallback、新闻过滤、相关性排序、缓存和调用审计（`src/search_service.py:1771`、`src/search_service.py:1960`、`src/search_service.py:3704`）。本任务应复用这些能力，不新增平行搜索模块。
- `SEARXNG_BASE_URLS` 与 `SEARXNG_PUBLIC_INSTANCES_ENABLED` 已进入配置、Web 设置帮助和 GitHub Actions（`src/config.py:1571`、`src/core/config_registry.py:1227`）。新增路由与预算配置必须沿用同一配置链路。
- 当前搜索审计契约以 DSA 进程发出的物理 HTTP 请求为计数真源（`.trellis/spec/backend/search-usage-audit.md`、`src/storage.py:815`）。本任务确认采用双层边界：DSA 审计 DSA → 私有 SearXNG 的调用；SearXNG → 上游引擎的扇出由 SearXNG 自身日志监控，并同步修订项目文档与规范。

## Requirements

### R1. 可选启用与兼容性

- 新增显式搜索路由模式，默认保持现有行为；只有配置低成本模式后，才启用 A 股分层路由。
- 推荐配置契约为 `SEARCH_ROUTING_MODE=legacy|searxng_first_cn`，默认 `legacy`。非法值记录可操作 warning 并回退 `legacy`。
- 港股、美股、日股、韩股、台股及无法识别市场的标的首期继续走原有 Provider 语义，不受低成本路由影响。
- A 股市场识别必须复用现有市场解析能力，不能用新的代码前缀副本；A 股 ETF 继续复用 `SearchService.is_index_or_etf()`（`src/search_service.py:2580`）。

### R2. 私有 SearXNG 部署

- 在 `docker/docker-compose.yml` 增加官方 SearXNG 服务，加入现有 `daily-stock-analysis_default` 网络，不发布宿主机端口，不经 nginx/frp 暴露公网。
- 使用固定版本标签或 digest，不使用不可复现的浮动 `latest` 作为最终提交值。
- SearXNG 使用独立资源限制，首期内存上限 512 MiB；当前仅 DSA 私有调用，关闭 public instance 与 limiter，不引入 Valkey/Redis。
- SearXNG 配置启用 JSON 输出、默认中文语言，并仅启用百度、Bing、Bing News、DuckDuckGo；暂不启用 Google。
- 通过官方 `SEARXNG_SECRET` 环境变量注入密钥，仓库不保存真实 secret。禁用会输出完整查询字符串的 HTTP access log；普通日志只保留引擎、状态、耗时和低敏错误。
- 容器健康检查只验证本地 Web 进程，不通过持续真实搜索制造上游请求；另提供一次性 JSON 搜索 smoke 验证上游可用性。
- `stock-server` 使用 `SEARXNG_BASE_URLS=http://searxng:8080`，并关闭公共实例自动发现。SearXNG 不健康不得阻止 DSA 启动，运行时由 Anspire fallback 兜底。

### R3. A 股低成本路由

- `search_stock_news`、`search_stock_events`、`search_comprehensive_intel` 及其 Agent/AlphaSift 间接入口，对 A 股和 A 股 ETF 使用同一分层路由 helper，禁止各入口各写一套 fallback。
- 每个搜索维度先调用私有 SearXNG；不再在 SearXNG 与 Anspire 之间轮流分配维度。
- 最新消息、公司公告、风险排查向 SearXNG 发送 `news` 类别；机构分析、业绩预期、行业分析发送 `general` 类别。
- 当前主流程 `max_searches=5` 实际执行的五个维度保持串行，避免短时间并发扇出导致上游封禁；若其他调用方提高上限而执行 `industry`，该维度同样走统一分层路由与总预算。

### R4. 结果准入与付费 fallback

- 复用现有时效过滤、语言优先、相关性排序和低质量准入逻辑（`src/search_service.py:3704` 之后的新闻处理链路），不得用“HTTP 200”直接判定 SearXNG 已满足需求。
- 最新消息、公司公告、风险排查至少需要 1 条与目标股票直接相关且符合时间窗口的结果；否则调用 Anspire。
- 机构分析、业绩预期、行业分析至少需要 1 条通过现有相关性和低质量过滤的结果；不因未达到 3 条而调用 Anspire。
- SearXNG 超时、连接失败、非 2xx、无效 JSON、空结果或所有结果被过滤时，调用 Anspire。
- 保留 SearXNG 最佳可用结果；Anspire 因预算被阻断或自身失败时，不得丢弃已有 SearXNG 结果，也不得伪装为付费搜索成功。

### R5. 时间预算

- 单次私有 SearXNG 请求默认硬上限 6 秒，不在 DSA 侧自动重试同一私有实例；上游引擎容错由 SearXNG 内部完成。
- 单只股票的低成本情报搜索总预算默认 30 秒；超过预算后停止继续发起新搜索，并按已有结果完成或降级。
- 目标体验为正常单股搜索阶段相对当前增加不超过约 15 秒；超时、预算耗尽和 fallback 原因必须进入运行诊断与低敏日志。

### R6. Anspire 每日预算保护

- 对 Anspire 的真实物理 HTTP 请求执行北京时间自然日预算：30 次预警、50 次硬上限；两个阈值均可配置，`0` 表示关闭对应阈值。
- 预算按物理请求计数，包括 transport retry；不能只按逻辑搜索或 Provider 返回计数。
- 硬上限必须跨线程、跨服务进程和重启保持有效。使用持久化、原子递增的“预算预留计数”作为控制面；`search_api_calls` 仍是真实已执行网络请求的审计真源。
- 达到硬上限后必须在网络调用前阻断，不新增伪造的 `search_api_calls` 记录；运行诊断应明确记录 `budget_blocked`，并发送一次 best-effort 告警。
- 预算控制故障应采用保守策略：无法可靠预留预算时不继续付费请求，但不能拖垮整个股票分析流程。

### R7. 审计与可观测性

- DSA → 私有 SearXNG 每个真实请求仍通过 `audited_request_once()`，在 `search_api_calls` 中记一条；缓存、本地过滤和预算阻断不记物理调用。
- SearXNG 内部对百度、Bing、Bing News、DuckDuckGo 的扇出不写入 DSA 的 `search_api_calls`，由 SearXNG 容器日志记录引擎级状态。必须更新 `AGENTS.md`、搜索审计 spec 和中英文指南，明确该基础设施边界。
- 现有用量页面应能按 Provider 观察 SearXNG/Anspire 请求数、成功率、耗时和 fallback 结果；不为首期新增独立 Web 仪表盘。
- 日志与审计快照不得包含 SearXNG secret、Anspire Key、Authorization 或未脱敏完整查询。

### R8. 配置、文档与发布说明

- 新配置必须同步 `src/config.py`、`src/core/config_registry.py`、`.env.example`、Web 设置页中英文帮助、结构化配置校验和 `.github/workflows/00-daily-analysis.yml` 的环境变量映射。
- 更新 `docs/full-guide.md` / `docs/full-guide_EN.md`、`docs/DEPLOY.md` / `docs/DEPLOY_EN.md`、`docs/settings-help.md` 与 `docs/CHANGELOG.md`；README 不扩充专题细节。
- 因部署方式与审计边界属于可复用项目知识，实施时同步更新根目录 `AGENTS.md`，并执行 AI 治理资产检查。
- 若 Web 设置页因新增字段发生可见变化，PR 描述附设置页截图，截图不写入仓库。

## Acceptance Criteria

- [ ] 未配置低成本模式时，现有 Provider 顺序、港股/美股搜索结果和 API/Agent 行为保持兼容。
- [ ] 配置 `searxng_first_cn` 时，A 股及 A 股 ETF 的每个搜索维度先调用私有 SearXNG；港股、美股仍走 legacy 路由。
- [ ] 当前主流程的三个关键新闻维度只有在缺少直接、及时结果时才调用 Anspire；两个分析维度只要求至少 1 条合格结果，不为补数量付费。若调用方额外执行 `industry`，沿用分析维度准入标准。
- [ ] 私有 SearXNG 单次请求 6 秒、单股搜索总预算 30 秒生效；超时不会导致同一私有实例在 DSA 侧重试堆叠。
- [ ] Anspire 第 30 个物理请求触发一次预警，第 50 个请求后阻断后续真实网络调用；并发和进程重启后仍不突破持久化硬上限。
- [ ] 预算阻断不写伪造的 `search_api_calls`；真实 SearXNG/Anspire 调用仍逐次落库，审计写入失败继续 fail-open，预算预留失败则 fail-closed 于付费请求。
- [ ] `docker compose -f docker/docker-compose.yml config` 通过；SearXNG 无宿主端口、无 Valkey/Redis 依赖、健康检查通过，`stock-server` 能通过容器 DNS 获得 JSON 结果。
- [ ] SearXNG 配置只启用百度、Bing、Bing News、DuckDuckGo，JSON 输出开启，secret 不入库，普通日志不打印完整查询或凭据。
- [ ] 20 只 A 股/ETF 样本覆盖热门、冷门、低新闻量与宽基 ETF；连续 3 天观测中，SearXNG 独立满足至少 70% 搜索维度，Anspire 平均不超过 1.5 次/只，付费成本不高于约 0.045 元/只。
- [ ] 样本中的最新消息、公司公告和风险排查未遗漏人工可确认的重要事件，单只股票搜索阶段不超过 30 秒。
- [ ] 定向后端测试、Docker smoke、Web lint/build、完整后端门禁和 AI 资产治理检查均通过；未执行的在线测试在交付说明中明确。
- [ ] 回滚只需把 `SEARCH_ROUTING_MODE` 改回 `legacy` 并停止 SearXNG 服务，不需要迁移或删除历史搜索审计数据。

## Out of Scope

- 接入百度付费搜索 API 或阿里 IQS。
- 首期修改港股、美股及其他市场的 Provider 优先级。
- 对外公开 SearXNG、配置域名/TLS/frp/nginx，或提供公共搜索页面。
- 维护 SearXNG fork，或把 SearXNG 内部每个上游引擎请求逐条导入 DSA 的 `search_api_calls`。
- 并行执行五个搜索维度、引入复杂智能路由模型，或新建独立搜索成本 Web 仪表盘。
- 在本任务中自动执行 git commit、tag、push 或创建 PR。
