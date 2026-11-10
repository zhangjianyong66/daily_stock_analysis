# 修复分析任务长期执行中 - 技术设计

## 架构边界

本任务分两层修复。

第一层是 `src/services/task_queue.py` 的任务生命周期兜底。它不试图强杀 Python 工作线程，而是在任务超过最大运行时长后，把进程内任务状态置为 `failed`，写入明确超时原因，释放对应股票去重锁，并广播失败事件。底层线程如果之后迟到返回，不能覆盖这个终态，也不能释放同一股票的新任务锁。

第二层是 `data_provider/base.py` 的数据源调用治理。`DataFetcherManager` 统一负责 provider 路由、fallback、运行流记录和熔断，因此 manager 层应给关键能力调用增加能力维度的等待预算。provider 内已有 requests timeout、tenacity retry、AkShare 子进程超时、efinance 线程等待超时的逻辑继续保留；manager 层只负责“单个 provider 调用不能无限阻塞整个路由”。

## 配置

新增配置建议：

- `ANALYSIS_TASK_TIMEOUT_SECONDS`：普通分析任务和通用后台任务最大运行时长，默认 `1200` 秒。`0` 表示关闭队列级超时兜底。
- `DATA_SOURCE_STOCK_NAME_TIMEOUT_SECONDS`：股票名称 provider 调用等待预算，默认 `8` 秒。
- `DATA_SOURCE_DAILY_TIMEOUT_SECONDS`：日线 provider 调用等待预算，默认 `45` 秒。
- `DATA_SOURCE_REALTIME_TIMEOUT_SECONDS`：实时行情 provider 调用等待预算，默认 `12` 秒。

这些值进入 `Config`，通过 `parse_env_int` / `parse_env_float` 解析，并同步 `.env.example` 与 `docs/CHANGELOG.md`。

## 任务队列数据流

任务提交后仍保持原有 `pending -> processing -> completed/failed` 模型，不新增 API 枚举。

队列在以下入口触发过期检查：

- `submit_tasks_batch(...)` 进入重复检查前。
- `get_task(...)` / `list_pending_tasks(...)` / `list_all_tasks(...)` / `get_task_stats(...)`。
- `is_analyzing(...)` / `get_analyzing_task_id(...)`。

过期检查只处理 `pending` / `processing` / `cancel_requested`。超时任务更新为：

- `status = failed`
- `completed_at = now`
- `error = "任务执行超过 <N>s，已标记失败"`
- `message = "分析任务执行超时，请稍后重试"`

并且只在 `_analyzing_stocks[dedupe_key] == task_id` 时释放锁，避免旧任务迟到返回时误删新任务锁。

工作线程完成时，终态写入必须先检查当前任务仍是非终态。如果任务已被超时标记为 `failed`，迟到结果只记录日志并忽略。

## 数据源调用数据流

`DataFetcherManager._call_fetcher_method(...)` 增加可选 `timeout_seconds` 和 `capability` 参数。调用内部仍用现有 per-fetcher lock 串行保护 provider 共享状态，但外层调用方只等待指定预算。超时后抛出 `TimeoutError`，由原有 daily/realtime/name 路由 catch 分支记录失败并继续 fallback。

按能力接入：

- 股票名称：`get_stock_name(..., allow_realtime=False)` 的 provider 名称查询使用 `DATA_SOURCE_STOCK_NAME_TIMEOUT_SECONDS`。
- 日线数据：`get_daily_data(...)` 的普通顺序路由和显式 source 路由使用 `DATA_SOURCE_DAILY_TIMEOUT_SECONDS`。
- 实时行情：`get_realtime_quote(...)` 以及 `_try_fetcher_quote(...)` 使用 `DATA_SOURCE_REALTIME_TIMEOUT_SECONDS`。

manager 层 timeout 后，不立即对同一个 provider 再调用一次；这会在 Python 无法强杀悬挂线程时扩大线程泄漏风险。重试保留在 provider 内部已有请求级逻辑里；manager 层负责标记本 provider 本轮失败并切换下一个 provider。

## 兼容性

- API 状态枚举不变，超时复用 `failed`。
- 成功任务落库和历史查询不变。
- `analysis_history` 仍只记录成功生成的历史报告；超时任务只保存在进程内任务状态里。
- 默认超时值足够长，不影响正常 2-5 分钟内完成的分析；可通过环境变量调整。

## 风险与回滚

Python 线程无法被强制杀死。manager 级超时能让调用链继续 fallback，但被放弃等待的底层线程可能短期留在后台直到库调用自行返回。为降低风险，本设计不对同一 provider 做 manager 层立即重试，并通过 provider 熔断/失败记录减少后续重复进入。

最小回滚方式：

- 将 `ANALYSIS_TASK_TIMEOUT_SECONDS=0` 关闭队列级超时。
- 将对应 `DATA_SOURCE_*_TIMEOUT_SECONDS=0` 关闭 manager 层 provider 调用等待预算。
- 或回退本任务代码改动。
