# 修复实时行情慢响应与超时隔离

## Goal

提高 A 股与 ETF 腾讯/新浪实时行情在正常慢响应场景下的成功率，并保证腾讯超时或卡住时不会阻塞新浪等独立物理上游。分析流程仍须在统一总预算内 fail-open，不因实时行情失败中断报告生成。

## Background

- 2026-07-14 13:58 之后新增的 7 份报告中，有 4 份将行情持久化为 `fetch_failed/realtime_quote_fetch_failed`：`515220`、`513060`、首次分析的 `513360`、`512710`。
- 腾讯请求在 manager 3 秒等待结束后仍正常返回，日志观测到约 `3.50s`、`4.94s`、`5.33s`；新浪也出现约 `4.09s`、`4.51s`、`5.81s` 的正常返回。
- `AkshareFetcher._enforce_rate_limit()` 会在请求前随机等待 2-5 秒，当前腾讯/新浪 HTTP 层又把 timeout 硬限制为 3 秒，导致 manager 的 3 秒策略不足以覆盖正常限速等待和网络请求。
- `DataFetcherManager` 当前按 fetcher 实例记录 manager timeout，并使用实例级调用锁。腾讯和新浪共用同一个 `AkshareFetcher`，腾讯超时后新浪会被静默跳过或被腾讯遗留线程占用的锁阻塞。
- Eastmoney 在同一时段出现 `RemoteDisconnected`、空结果和 300 秒熔断；首次请求没有 last-good 缓存时，错误的新浪跳过会直接放大为 `fetch_failed`。

## Requirements

### R1. 超时预算

- 腾讯和新浪单次硬超时上限从 3 秒调整为 10 秒，manager 与 HTTP 请求层必须使用一致的有效上限。
- `DATA_SOURCE_REALTIME_TIMEOUT_SECONDS` 继续只能收紧单源等待，不能放大 10 秒源策略上限或 20 秒整链路上限。
- Eastmoney 等全量源保持单次 8 秒上限，单只标的实时行情整链路保持 20 秒上限。

### R2. 软超时并行兜底

- 默认优先级下先启动腾讯；腾讯在 5 秒内未产生最终结果时，启动新浪作为独立物理上游的并行兜底。
- 腾讯若在 5 秒前快速失败、返回空数据或无有效价格，应立即进入新浪，不必等待软超时点。
- 腾讯或新浪任一方先返回有效基本行情，即确定为主行情来源；另一方不得覆盖已选主行情。
- 仍在当前调用预算内被收集到的次源结果，只能沿用现有字段补充规则填充主行情缺失字段；调用方已经返回后的迟到结果不得写入 last-good、报告上下文或覆盖主行情。
- 仅在优先级中同时存在腾讯和新浪且腾讯位于新浪之前时启用该 5 秒 hedge；自定义优先级的其他组合继续按配置顺序执行。

### R3. 物理上游隔离

- manager timeout、调用锁和遗留线程隔离必须以物理上游为边界，至少区分 `tencent`、`sina`、`eastmoney`。
- 腾讯遗留线程只能占用腾讯自己的调用锁，不得阻止新浪开始请求。
- 同一物理上游的并发调用仍须有界并串行化，避免同一上游请求堆叠。
- `efinance` 与 `akshare_em` 继续共享 Eastmoney 网络失败阻断和熔断语义，不得伪装为独立上游。

### R4. 限速与线程安全

- 腾讯/新浪并行后，`AkshareFetcher` 的限速时间戳和互斥状态必须按物理上游隔离，不能继续依赖无锁的单一 `_last_request_time`。
- 单次标的最多同时存在腾讯和新浪两个轻量源调用；不得引入无上限线程池、无限重试或跨标的共享结果。
- Python 无法强杀的迟到 daemon 调用必须保持 fail-open、结果隔离和有界启动数量。

### R5. 诊断与用户状态

- provider diagnostics 必须记录实际启动、完成、超时、winner source、fallback/hedge 关系和剩余预算，且不得泄漏 URL 参数、代理、token 或堆栈。
- 被错误跳过的新浪路径必须有回归测试；不能再出现日志声明 `fallback_to=akshare_sina`，实际却没有启动或记录新浪的情况。
- 有效 quote 继续映射为 `available` 或 `fallback`；只有实际尝试后全部失败且无合格 last-good 时才映射为 `fetch_failed`。

### R6. 兼容与文档

- 保持 `DataFetcherManager.get_realtime_quote()`、`UnifiedRealtimeQuote`、`REALTIME_SOURCE_PRIORITY` 和现有 API/报告载荷兼容。
- 同步更新 `AGENTS.md`、`.env.example`、`docs/data-source-stability.md`、中英文完整指南和 `docs/CHANGELOG.md`，删除已失效的 3 秒轻量源契约。
- 不新增数据库表、持久化缓存、用户配置开关或平行实时行情 Router。

## Acceptance Criteria

- [ ] 腾讯在 5-10 秒之间返回有效行情时不再被误判为 `fetch_failed`。
- [ ] 腾讯超过 5 秒未完成时，新浪能够在腾讯仍运行的情况下实际启动，并可先于腾讯成为主行情。
- [ ] 腾讯硬超时或遗留线程持锁时，不影响新浪物理上游；同一腾讯上游的后续调用仍不会无限堆叠。
- [ ] 腾讯/新浪 HTTP 请求层和 manager 层的有效硬上限均为 `min(10s, 用户收紧值, 整链路剩余预算)`。
- [ ] 腾讯与新浪均失败后，Eastmoney 只在剩余 20 秒总预算内执行；整链路调用方等待不突破 20 秒。
- [ ] hedge 竞争中首个有效 quote 的来源、`fallback_from`、字段补充和 last-good 写入语义正确，迟到结果不会覆盖或续命缓存。
- [ ] provider diagnostics 能证明腾讯和新浪是否实际启动、谁成功、谁超时，不产生静默跳过或跨 trace 串线。
- [ ] AnalysisContextPack 的 `available/fallback/stale/fetch_failed/missing` 既有契约保持成立。
- [ ] 新增确定性回归测试覆盖 5 秒软触发、10 秒硬上限、物理源锁隔离、迟到结果、总预算和原 4 笔失败反例。
- [ ] 目标实时行情测试、Python 语法检查和 `./scripts/ci_gate.sh` 通过；如未执行在线 smoke，交付说明明确记录。

## Out Of Scope

- 不追溯修改已经生成的历史报告 192-195。
- 不改变 Eastmoney 8 秒上限、300 秒熔断或 30 分钟 last-good 生命周期。
- 不新增第三方付费行情源，也不调整 Web 报告组件布局。
