# 修复实时行情慢响应与超时隔离 - 实施计划

> Codex inline 模式执行。实现前加载 `trellis-before-dev`，实现后加载 `trellis-check`。未经用户明确确认，不执行 git commit、tag 或 push。

## 改动边界

| 文件 | 计划改动 |
| --- | --- |
| `data_provider/base.py` | 源计划增加 10 秒硬上限/5 秒 hedge；调用锁按物理源 scope；增加有界 attempt handle 与 winner controller；删除实例级超时误伤 |
| `data_provider/akshare_fetcher.py` | 腾讯/新浪请求层允许 10 秒上限；轻量实时限速状态按 source 隔离 |
| `tests/test_realtime_quote_fallback_logging.py` | 覆盖 hedge、物理锁、迟到结果、总预算、diagnostics 和 fallback 语义 |
| `tests/test_akshare_realtime_quote.py` | 覆盖 HTTP timeout 上限和腾讯/新浪限速隔离 |
| `tests/test_run_diagnostics_p1.py` | 如诊断字段或顺序契约变化，补充结构化回归 |
| `AGENTS.md`、`.env.example`、`docs/*.md` | 同步 10/5/8/20 契约与用户可见变更 |

## 阶段 1：先补失败测试

- [x] 增加腾讯 5-10 秒内成功仍返回 quote 的确定性测试。
- [x] 增加腾讯超过 5 秒时新浪实际并行启动并先成功的测试。
- [x] 增加腾讯 hard timeout 后遗留线程不阻塞新浪 physical scope 的测试。
- [x] 增加同一腾讯 physical scope 不会并行堆叠的测试。
- [x] 增加快速失败立即启动新浪、无需等待 5 秒的测试。
- [x] 增加总等待不超过 20 秒、后续 Eastmoney 只使用剩余预算的测试。
- [x] 增加迟到腾讯结果不覆盖新浪 winner、不写 last-good 的测试。
- [x] 将腾讯/新浪 HTTP timeout 断言从 3 秒更新为 10 秒，并验证用户配置可收紧。
- [x] 增加腾讯/新浪限速状态分别维护、并行不竞争单一时间戳的测试。

先运行并确认新增测试在旧实现上失败：

```bash
python3 -m pytest tests/test_realtime_quote_fallback_logging.py tests/test_akshare_realtime_quote.py -q
```

## 阶段 2：实现物理源调用隔离

- [x] 将 fetcher call lock 扩展为可选 scope key，旧调用默认行为不变。
- [x] 实时 plan 使用 `physical_source` scope。
- [x] 删除或替换 `timed_out_fetcher_ids`；跳过判定不得再按整个 fetcher 实例传播。
- [x] 保证同一 physical scope 的遗留调用继续阻止同源重复堆叠。

## 阶段 3：实现 10 秒硬上限与 5 秒 hedge

- [x] 为腾讯/新浪 source plan 设置 10 秒硬上限，为腾讯设置 5 秒 hedge。
- [x] 实现有界 attempt handle，worker 只写私有结果盒。
- [x] controller 串行处理 soft deadline、hard deadline、winner、失败分类与 diagnostics。
- [x] 快速失败立即启动新浪；未完成才等待到 5 秒 soft deadline。
- [x] winner 产生后保持来源和基本价格，已收集次源只能补缺失字段。
- [x] 调用返回后的迟到结果不进入 finalization、last-good 或 request diagnostics。
- [x] 继续遵守 20 秒总预算和 Eastmoney 物理失败去重。

## 阶段 4：请求层与限速线程安全

- [x] 腾讯/新浪 `requests.get(timeout=...)` 的源策略上限改为 10 秒，并继续接受 manager/配置收紧值。
- [x] 为轻量实时源建立 source-keyed 限速时间戳和锁，避免腾讯/新浪共享无锁 `_last_request_time`。
- [x] 保持历史数据和 Eastmoney 路径原有 `_enforce_rate_limit()` 行为，避免无关改动。

## 阶段 5：完整契约回归

- [x] 验证首源成功、跨源 fallback、字段补充、last-good stale、全部失败等已有测试。
- [x] 验证 diagnostics 中实际启动的新浪不再静默缺失。
- [x] 验证 AnalysisContextPack 状态不因 hedge 引入新的错误分类。
- [x] 检查美股、港股、台股等非 A 股路由未进入腾讯/新浪 hedge。

目标测试：

```bash
python3 -m pytest \
  tests/test_realtime_types.py \
  tests/test_realtime_quote_fallback_logging.py \
  tests/test_akshare_realtime_quote.py \
  tests/test_etf_realtime_singleflight.py \
  tests/test_fetcher_source_optimization.py \
  tests/test_hk_realtime_routing.py \
  tests/test_tw_market_support.py \
  tests/test_run_diagnostics_p1.py \
  tests/test_analysis_context_builder.py \
  tests/test_pipeline_market_phase_context.py -q
```

## 阶段 6：文档与质量门禁

- [x] 更新 `AGENTS.md` 可复用运行约定。
- [x] 更新 `.env.example`、`docs/data-source-stability.md`、`docs/full-guide.md`、`docs/full-guide_EN.md`。
- [x] 在 `docs/CHANGELOG.md` `[Unreleased]` 添加扁平 `[修复]` 条目。
- [ ] 执行：

```bash
python3 -m py_compile data_provider/base.py data_provider/akshare_fetcher.py
./scripts/ci_gate.sh
```

- [ ] 可选在线 smoke：在非高并发条件下请求一个 ETF，记录腾讯/新浪实际耗时、hedge 是否触发以及最终 source；在线结果不作为确定性 CI 的替代。

## 验证记录

- 实时行情目标矩阵：`125 passed`。
- Python 语法检查、Flake8 critical checks、`git diff --check`：通过。
- `./scripts/ci_gate.sh`：语法、Flake8、deterministic checks 通过；离线全集 `4388 passed, 30 failed, 4 deselected`。失败集中在未改动的 Intelligence/System Config/Usage API，本机认证与持久化模型环境会污染测试；隔离环境重跑后 Intelligence/Usage 恢复通过，System Config 仍因导入期注入本机 `deepseek/deepseek-v4-pro` 保留 19 个基线失败。
- 在线 ETF smoke 未执行，避免把实时第三方网络结果当作确定性验收证据。

## 风险与回滚点

- hedge 会增加少量重复请求，只允许腾讯和新浪各一个 in-flight，并由 20 秒总预算限制。
- Python 线程无法强杀；物理 scope 锁和迟到结果隔离是防止堆叠与覆盖的关键，相关测试必须先通过。
- 限速状态改为 source-keyed 后需确认不会提高同一上游并发；同源锁必须保留。
- 如出现线程或诊断回归，可整体回滚 hedge controller、scope lock 和文档变更；无数据库迁移。
