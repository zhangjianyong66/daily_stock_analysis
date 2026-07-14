# 修复实时行情慢响应与超时隔离 - 技术设计

## 1. 设计目标

在不改变公共返回类型和配置格式的前提下，将腾讯/新浪的轻量源硬上限提高到 10 秒，并在腾讯等待 5 秒后对新浪发起有界 hedge。隔离边界从 fetcher 实例下沉到物理上游，使同一个 `AkshareFetcher` 可以安全承载相互独立的腾讯与新浪请求。

## 2. 根因链

```text
AkshareFetcher 请求前随机等待 2-5 秒
  -> manager 3 秒先超时
  -> timed_out_fetcher_ids 标记整个 AkshareFetcher
  -> akshare_sina 因共用实例被跳过
  -> efinance / akshare_em 同属 Eastmoney 且断连或熔断
  -> 首次请求无 last-good
  -> realtime_quote_fetch_failed
```

现有实例级锁还有第二层问题：即使删除 `timed_out_fetcher_ids`，新浪 worker 仍会等待腾讯遗留线程释放同一个 fetcher lock，无法形成真实物理源 fallback。

## 3. 源计划契约

扩展内部 `RealtimeSourcePlan`，使源策略显式携带：

- `timeout_seconds`：硬上限。腾讯/新浪 10 秒，Eastmoney 8 秒。
- `physical_source`：并发锁、隔离和网络失败阻断边界。
- `hedge_after_seconds`：仅默认腾讯计划为 5 秒，其他源为空。
- `hedge_target` 或由相邻计划解析出的新浪目标：只允许 `{tencent -> akshare_sina}`。

有效硬等待仍统一计算：

```text
min(plan timeout, positive configured timeout, total remaining budget)
```

不新增环境变量；10/5/20 是代码级公共安全策略，文档同步更新。

## 4. 调用锁与限速隔离

`DataFetcherManager` 的调用锁键从单一 `id(fetcher)` 扩展为：

```text
(id(fetcher), call_scope)
```

- 普通历史数据、基本面等旧调用不传 scope，继续使用实例级锁，保持兼容。
- 实时行情传 `physical_source` 作为 scope；腾讯、Sina、Eastmoney 各自串行，但可相互并行。
- 同一物理上游的遗留线程继续占用自己的 scope lock，避免同源请求风暴。

`AkshareFetcher` 的实时轻量限速状态改为按 source key 保存，并由各 source 自己的锁保护。腾讯和新浪继续执行现有限速策略，但不再读写同一个无锁 `_last_request_time`。其他 AkShare 抓取路径保持原限速入口，避免扩大改动面。

## 5. Hedge 执行状态机

仅当解析后的计划中存在按顺序排列的 `tencent` 和 `akshare_sina` 时启用：

```text
t=0    启动腾讯，硬截止=min(10s, 配置, 总剩余预算)
  |-- 腾讯快速失败/空/无效 -> 立即启动新浪
  |-- 腾讯返回有效 quote -> 选腾讯为主行情
t=5    腾讯仍未完成 -> 启动新浪，独立硬截止
  |-- 新浪先返回有效 quote -> 选新浪为主行情
  |-- 腾讯随后返回 -> 不覆盖新浪，仅可在当前调用仍收集时补缺失字段
t<=20  所有已启动轻量源失败 -> 在剩余预算内继续后续计划
```

实现使用有界的 per-attempt daemon handle 和完成事件，不使用无界 executor。controller 线程负责：

- 计算 soft/hard/total deadline。
- 启动次数和物理源去重。
- 收集结果并记录 diagnostics。
- 选择 winner、归一化失败、写 last-good。

provider worker 只执行 fetcher 方法并把结果/异常写入私有结果盒，不直接修改 manager 主行情、last-good 或请求级 diagnostics。这样迟到 worker 即使完成，也不能覆盖已返回结果或向已持久化 trace 追加记录。

## 6. Winner、字段补充与迟到结果

- 第一个 `has_basic_data()` 的 quote 成为 `primary_quote`。
- winner 来源若不是最高优先级源，`fallback_from` 仍记录首个已确认失败或软超时后被 hedge 的优先源。
- controller 在返回前已经收集到的其他有效 quote 可以调用现有 `_merge_quote_fields()`，只填 `None`/缺失字段，不覆盖 winner 的基本价格和来源。
- controller 已经返回、总预算已耗尽或 handle 被逻辑放弃后，worker 结果不得进入 `_finalize_realtime_quote()`，因此不会写 last-good。
- last-good 只写 winner 最终结果一次；stale 不回写的既有契约不变。

## 7. 重试与失败阻断

- 腾讯/新浪快速返回 `connection_error/timeout/rate_limited` 时仍最多重试 1 次；manager 自身 hard timeout 不重试同一 plan。
- hedge 启动不算 retry；每个 plan 的 attempt 独立记录。
- 网络类失败只阻断对应 `physical_source`。腾讯失败不阻断新浪。
- Eastmoney 网络失败继续同时阻断 `efinance` 与 `akshare_em`。
- 空数据、无效 quote、不支持不重试，立即推进下一源。

## 8. 诊断语义

所有 diagnostics 由 controller 串行写入当前 `RunDiagnosticContext`，避免 `ContextVar` 在线程中丢失以及共享 list 并发写入：

- 每个实际启动的 route 都有 started 和最终结果记录。
- 记录 `route_source`、`physical_source`、attempt、latency、budget、fallback_to。
- winner 使用 success 记录；已观测到的 loser 使用真实成功/失败结果记录。
- 调用返回后才完成的 loser 不追加持久化 provider run，也不参与 failure summary。
- 日志可记录低敏的 hedge 启动和 winner，不记录原始 URL 查询、代理或敏感配置。

## 9. 兼容性与文档

- 公共方法仍返回 `UnifiedRealtimeQuote | None`。
- 自定义 `REALTIME_SOURCE_PRIORITY` 保持顺序语义；不满足腾讯在新浪之前时不自动重排。
- `DATA_SOURCE_REALTIME_TIMEOUT_SECONDS` 仍可设置小于 10 秒用于主动收紧；`0` 仍表示不额外收紧。
- 更新 `AGENTS.md` 与数据源文档中的 3/8/20 契约为：腾讯/新浪 10 秒硬上限、腾讯 5 秒 hedge、Eastmoney 8 秒、总链 20 秒。
- 在 `docs/CHANGELOG.md` 的 `[Unreleased]` 扁平区新增一条 `[修复]`。

## 10. 回滚

代码回滚可恢复为顺序执行和实例级锁；文档必须同步回滚到实际行为。无需数据库迁移或清理缓存，重启进程即可清空内存中的调用锁与 last-good。
