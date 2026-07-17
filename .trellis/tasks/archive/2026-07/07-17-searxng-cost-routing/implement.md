# 自建 SearXNG 分层搜索降本：实施计划

> 2026-07-17 已经用户确认启动，任务状态为 `in_progress`。下方保留原始实施清单作为设计基线，实际交付状态以本节为准。

> 2026-07-17 收尾：本任务的自建 SearXNG 路线已被子任务 `07-17-searxng-contamination-guard` 的停用方案取代。原方案的连续 3 天线上指标和 PR 截图不再适用，保留未勾选状态作为历史记录；本任务按“已被替代”归档，不表示原方案验收通过。

## 当前执行记录

### 2026-07-17 SearXNG 可用性修复

- [x] 修复 SearXNG 容器错误继承宿主机 `127.0.0.1` 代理的问题：运行时优先读取 `SEARXNG_OUTGOING_PROXY`，未设置时继承容器 `.env` 中的 HTTPS/HTTP 代理，并写入 SearXNG `outgoing.proxies`。
- [x] 低成本路由不再向私有 SearXNG 强制发送 `time_range`；时效窗口继续由 DSA 现有过滤链路执行，避免不支持 time range 的 Bing 被排除。
- [x] SearXNG HTTP 200 但空结果时保留 `unresponsive_engines` 低敏摘要，区分百度 CAPTCHA、DuckDuckGo 超时和普通空结果。
- [x] 未配置 `ANSPIRE_API_KEYS` 时不再记录“准备 Anspire fallback”，启动和运行日志明确提示无付费兜底。
- [x] 增加入口脚本、Compose、Provider 参数、空结果诊断和无 Anspire 路径回归测试。
- [x] 重建 SearXNG 并完成在线验证：百度处于 `Suspended: CAPTCHA`、DuckDuckGo 处于 `Suspended: access denied`、Bing News 解析失败时，`general` 与 `news` 查询仍由 Bing 各返回 10 条结果。
- [x] 完整后端门禁通过：`4491 passed` / `4 deselected` / `413 subtests passed`；定向搜索/预算/审计/Docker 回归 `141 passed` / `2 skipped`；Compose、AI 资产、Shell 语法和在线 smoke 通过。

- [x] 完成 A 股/A 股 ETF 的私有 SearXNG → Anspire 分层路由，默认 `legacy` 保持兼容。
- [x] 完成关键新闻/公告/风险与分析维度的差异化准入、6 秒单次超时和 30 秒单股总预算。
- [x] 完成 Anspire 北京时间每日 30/50 预警/硬上限，并覆盖线程、进程与重启后的原子持久化预留。
- [x] 完成物理请求审计边界：预算阻断不伪造 `search_api_calls`，DSA → SearXNG 与 Anspire 真实请求继续逐次记账。
- [x] 完成 Docker SearXNG 可选 profile、固定镜像 digest、内部网络、无宿主端口、资源上限与低敏日志配置。
- [x] 优化 `scripts/docker-up.sh`：低成本路由启用时，默认 `restart` 自动激活 SearXNG profile 并同时启动私有服务，legacy 模式保持原行为。
- [x] 完成配置注册、Web 中英文帮助、Actions、`.env.example`、中英文部署/完整指南、Changelog、`AGENTS.md` 和审计 spec 同步。
- [x] 最终质量检查修复 SearXNG 普通日志输出完整查询的隐私问题，并补齐 A 股 ETF/非 A 股边界、预算阻断保留 best-effort 结果和 deadline 阻断回归。
- [x] 离线质量门禁完成：最终完整后端门禁 `4483 passed` / `4 deselected` / `413 subtests passed`；Web 测试、lint、build；Docker 实测；AI 治理检查均通过。
- [x] 最终修正后复验：搜索审计/预算/供应商回归 `86 passed`，Python syntax、Flake8 critical、AI 治理、Compose config 与 `git diff --check` 通过。
- [ ] 待线上验收：20 只 A 股/ETF 样本连续 3 天观测，确认 SearXNG 准入率、Anspire 次数/只、成本、耗时与重要事件无漏报。
- [ ] 如后续创建 PR，在 PR 描述附设置页受影响字段截图；截图不写入仓库。

## 1. 开发前准备

- [ ] 运行 `trellis-before-dev`，重新读取 backend、搜索审计、错误处理、Docker、配置和文档规范。
- [ ] 检查工作区与当前分支，确认没有覆盖用户改动。
- [ ] 用固定 SearXNG 官方镜像验证 engine identifier、`SEARXNG_SECRET`、JSON formats、access log 开关和健康检查命令；记录最终镜像 tag/digest。
- [ ] 将任务 scope 与实际文件清单复核，保持单任务实现，不拆分无必要的平行模块。

## 2. 配置契约

- [ ] 在 `src/config.py` 增加并校验：`SEARCH_ROUTING_MODE`、`SEARXNG_REQUEST_TIMEOUT_SECONDS`、`SEARCH_INTEL_TOTAL_TIMEOUT_SECONDS`、`ANSPIRE_DAILY_WARNING_REQUESTS`、`ANSPIRE_DAILY_HARD_LIMIT_REQUESTS`。
- [ ] 保持默认 `legacy`，验证非法枚举、负数、warning ≥ hard limit、hard limit=0 等边界。
- [ ] 在 `src/core/config_registry.py`、`.env.example`、Web 中英文字段名/帮助、结构化配置测试中补齐新字段；`SEARXNG_SECRET` 按 secret 处理，不允许明文回显。
- [ ] 评估并补齐 `.github/workflows/00-daily-analysis.yml` 环境变量映射，确保未配置时行为不变。

## 3. 私有 SearXNG Compose 服务

- [ ] 新增 `docker/searxng/settings.yml`，只保留百度、Bing、Bing News、DuckDuckGo，开启 JSON、默认 `zh-CN`，关闭 public instance、limiter 和 query access log。
- [ ] 在 `docker/docker-compose.yml` 增加无宿主端口的 `searxng` 服务、512 MiB 上限、日志轮转、配置/缓存挂载和进程健康检查。
- [ ] 使用官方固定镜像 tag/digest；不引入 Valkey/Redis，不将 SearXNG 设为 server 启动硬依赖。
- [ ] 明确运行时代理变量与 `NO_PROXY=searxng,stock-server,localhost,127.0.0.1`，验证容器内访问国内与海外上游不会把内部服务地址错误发给代理。
- [ ] 通过 `docker compose config` 验证 secret/URL/网络渲染，不输出真实 secret。

## 4. 分层搜索路由

- [ ] 在 `SearchService` 构造中保留 legacy `_providers`，同时建立复用现有 Provider 实例的明确引用，不重复实例化 SearXNG/Anspire。
- [ ] 复用现有市场解析实现 `searxng_first_cn` 判定；覆盖 A 股、A 股 ETF、港股、美股、台股和未知代码测试。
- [ ] 为 SearXNG 增加 `categories` 与按调用传入 timeout 的能力；私有低成本模式关闭 DSA transport retry，legacy 公共实例/多实例行为保持不变。
- [ ] 抽取共享 `_search_cn_dimension_with_fallback` 与准入 helper，接入 `search_stock_news`、`search_stock_events`、`search_comprehensive_intel`。
- [ ] 当前主流程的三个关键维度使用 `news` + direct/时效准入；两个分析维度使用 `general` + 至少一条合格结果准入；可选的 `industry` 第六维度沿用分析维度标准。
- [ ] 保留 SearXNG best-effort response；Anspire 失败、预算阻断或总 deadline 耗尽时按明确限制返回，不静默丢失已有结果。
- [ ] 增加单股 30 秒 deadline，调用 timeout 取剩余预算；检查并调整现有固定 sleep，确保不会越过总预算。

## 5. Anspire 每日预算控制

- [ ] 在 `src/storage.py` 增加控制表模型，在 `src/repositories/` 增加原子预算预留操作，在 `src/services/` 增加独立预算服务与领域异常。
- [ ] 预算日期使用 Asia/Shanghai，自然日切换自动创建新行；控制表不替代 `search_api_calls`。
- [ ] 在 Anspire 每次物理 transport 前预留，确保每个 retry 单独计数；达到硬上限时在网络前抛出非 retryable `SearchBudgetExceeded`。
- [ ] 数据库/预算服务不可用时阻断付费调用但不中断整体分析；验证并发线程、server/analyzer 双进程和重启后的上限语义。
- [ ] 第 30 次与第 50 次分别发送一次低敏 best-effort 通知；无完整 query、Key 或请求体。
- [ ] 预算阻断只写运行诊断 `budget_blocked`，不写伪造的物理调用审计行。

## 6. 审计、诊断和跨层一致性

- [ ] 保证 DSA → SearXNG 仍通过 `audited_request_once`，SearXNG/Anspire 的 `business_search_id`、`logical_request_id`、股票和维度上下文完整。
- [ ] 扩展运行诊断以区分 `searxng_accepted`、`fallback_to_anspire`、`budget_blocked`、`deadline_exhausted`，不改变旧 API 必填字段。
- [ ] 检查 Search Usage 页面无需新 DTO 即可展示 Provider 调用；如追加预算状态 API，则同步 schema、Web 类型和权限测试，禁止只改后端。
- [ ] 更新 `.trellis/spec/backend/search-usage-audit.md` 与 `AGENTS.md`，明确自建聚合服务的双层审计边界。

## 7. 测试

- [ ] 扩展 `tests/test_search_searxng.py`：categories、6 秒 timeout、私有低成本模式不 retry、无效 JSON、空结果、best-effort 保留。
- [ ] 扩展新闻/路由测试：A 股与 ETF 走 SearXNG → Anspire，关键/分析维度准入差异，港股/美股 legacy 不变。
- [ ] 增加预算 Repository/Service/transport 测试：30 次一次预警、50 次后阻断、北京时间换日、并发原子性、重启、retry 逐次预留、DB 故障 fail-closed、阻断不写审计行。
- [ ] 扩展审计测试：一次 DSA → 私有 SearXNG 记一条；cache、过滤、budget block 不计；Anspire retry 仍逐次记录。
- [ ] 扩展配置与 Web i18n 测试，检查新字段 registry/help key/locale 一致。
- [ ] 扩展 run diagnostics 测试，验证 fallback、deadline、budget 状态与低敏摘要。

建议定向命令：

```bash
python3 -m pytest \
  tests/test_search_searxng.py \
  tests/test_search_news_freshness.py \
  tests/test_search_service_concurrency.py \
  tests/test_search_usage_storage.py \
  tests/test_search_usage_service.py \
  tests/test_search_usage_api.py \
  tests/test_anspire_search.py \
  tests/test_run_flow.py \
  tests/test_config_validate_structured.py -q
```

## 8. Docker 与在线 smoke

- [ ] `docker compose -f docker/docker-compose.yml config`
- [ ] 只启动 SearXNG，验证健康状态、无宿主端口、资源上限与日志不含完整 query。
- [ ] 从 `stock-server` 容器访问 `http://searxng:8080/search?q=<测试词>&format=json`，确认 JSON、四个引擎与发布时间字段行为。
- [ ] 模拟 SearXNG 停止、上游超时、空结果，确认 Anspire fallback 与 30/50 预算保护。
- [ ] 在线 smoke 使用非敏感公开股票查询，完整响应仅进入受控审计快照，不进入普通日志。

## 9. 文档与验收

- [ ] 更新中英文完整指南、部署文档、设置帮助和 `[Unreleased]` 扁平 changelog；README 不新增专题内容。
- [ ] 更新 `AGENTS.md`：私有 SearXNG Compose 运行方式、引擎组合、内部网络地址、审计边界、回滚步骤和目标回归命令。
- [ ] 如设置页新增可见字段，在 PR 描述准备截图，不把截图提交仓库。
- [ ] 选择 20 只 A 股/ETF 样本，连续 3 天记录：SearXNG 接受维度占比、Anspire 次数/只、搜索总耗时、关键事件人工核验。
- [ ] 验收阈值：SearXNG ≥70% 维度、Anspire ≤1.5 次/只、成本 ≤0.045 元/只、搜索阶段 ≤30 秒、重要事件无确认漏报。

## 10. 最终质量门禁

- [ ] 对改动 Python 文件执行 `python -m py_compile`。
- [ ] 使用隔离部署配置执行 `./scripts/ci_gate.sh`，避免本机真实 `.env` 干扰离线测试。
- [ ] Web 配置/帮助改动执行 `cd apps/dsa-web && npm ci && npm run lint && npm run build`，并运行受影响 Vitest。
- [ ] Docker 相关改动完成 compose config 与实际容器 smoke；未执行 GitHub Actions 时说明风险。
- [ ] 修改 `AGENTS.md` 后执行 `python scripts/check_ai_assets.py`。
- [ ] 使用 `trellis-check` 做最终 spec、测试、跨层与文档一致性复核。

## 11. 回滚点

- [ ] 路由回滚：`SEARCH_ROUTING_MODE=legacy`。
- [ ] 部署回滚：停止 SearXNG 服务，保留配置和审计数据。
- [ ] 预算回滚：保留控制表；除非用户明确批准，不通过关闭硬上限绕过成本保护。
- [ ] 数据回滚：不删除 `search_api_calls` 与预算历史；新控制表对 legacy 路由无副作用。

## 12. 启动实施前的审核门

- [ ] 用户审核并批准 `prd.md`、`design.md`、`implement.md`。
- [ ] 只有收到明确“开始实现”指令后，才运行 `python3 ./.trellis/scripts/task.py start ...`。
- [ ] 未经明确确认，不执行 git commit、tag、push 或 PR 操作。
