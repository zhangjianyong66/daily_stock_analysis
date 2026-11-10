# 修复分析任务长期执行中 - 实施计划

## 1. 测试先行

- 在任务队列测试中新增失败用例：
  - processing 任务超过 `ANALYSIS_TASK_TIMEOUT_SECONDS` 后变为 `failed`。
  - 超时后释放 `_analyzing_stocks`，同一股票可重新提交。
  - 迟到完成的旧任务不会覆盖 `failed` 终态，也不会释放新任务锁。
- 在数据源 manager 测试中新增失败用例：
  - 股票名称 provider 超时后继续尝试下一个 provider。
  - 日线 provider 超时后记录失败并 fallback 到下一个 provider。
  - 实时行情 provider 超时后继续尝试下一个 source。
- 在配置测试中新增失败用例：
  - 新环境变量可解析，默认值符合设计。

## 2. 队列级超时兜底

- 在 `Config` 中新增 `analysis_task_timeout_seconds`。
- `get_task_queue()` 同步 runtime config 时同步任务超时配置。
- `AnalysisTaskQueue` 增加超时配置、同步方法、过期扫描方法。
- 在任务提交、查询、统计、重复检测入口调用过期扫描。
- 抽取安全释放去重锁 helper，所有 completed/failed/timeout 路径都按 `dedupe_key -> task_id` 精确释放。
- 工作线程写终态前检查任务当前状态，忽略迟到结果。

## 3. 数据源调用超时治理

- 在 `Config` 中新增：
  - `data_source_stock_name_timeout_seconds`
  - `data_source_daily_timeout_seconds`
  - `data_source_realtime_timeout_seconds`
- 在 `DataFetcherManager` 增加 manager 层限时调用 helper。`0` 或负数表示关闭该层等待预算。
- 接入股票名称、日线、实时行情三条主路径。
- timeout 归类为 `timeout`，保留现有运行流和 fallback 记录语义。
- 避免 manager 层对同一 provider 立即重试；失败后继续下一个 provider。

## 4. 文档与配置

- 更新 `.env.example`，说明新增超时配置与默认值。
- 更新 `docs/CHANGELOG.md` 的 `[Unreleased]` 扁平条目。
- 若发现配置注册表已有运行时设置分组需要同步，则更新 `src/core/config_registry.py`。

## 5. 验证

优先执行：

```bash
python -m pytest tests/test_task_queue_config_sync.py tests/test_analysis_api_contract.py -q
python -m pytest -m "not network" tests/test_data_fetcher_timeout.py -q
python -m py_compile src/services/task_queue.py data_provider/base.py src/config.py
```

最终按影响面补充：

```bash
./scripts/ci_gate.sh
```

如完整 CI gate 因环境或依赖耗时无法完成，交付时明确说明未验证项。
