# 实施计划：修复大盘上下文重复生成

## 1. 实现

- [x] 在 `src/core/market_review.py` 为 `run_market_review()` 与 `_persist_market_review_history()` 增加可选目标交易日参数，并只写入历史 `context_snapshot`。
- [x] 在 `src/services/daily_market_context.py` 生成大盘上下文时透传 `target_date`。
- [x] 调整历史匹配：优先严格匹配 `daily_market_context_target_date`，字段缺失时回退旧逻辑。
- [x] 保留历史写入失败后的 fail-open 重试，不增加跨日启发式和进程级全局缓存。

## 2. 回归测试

- [x] 扩展 `tests/test_market_review.py`，覆盖目标日写入与未传参数兼容。
- [x] 扩展 `tests/test_daily_market_context.py`，覆盖自然日 T / 目标交易日 T-1 的复用、显式字段优先级、旧记录兼容、严格不跨日和锁等待去重。
- [x] 现有 `tests/test_pipeline_daily_market_context.py` 与 `tests/test_main_schedule_mode.py` 已覆盖 `effective_daily_bar_date` 透传及各市场目标日路由，无需新增重复用例。
- [x] 保留并运行“锁释放但无历史时重新生成”的现有 fail-open 测试。

## 3. 文档

- [x] 更新 `docs/analysis-context-pack.md`，明确报告生成日与上下文目标交易日分离，以及正常持久化路径的复用语义。
- [x] 在 `docs/CHANGELOG.md` 的 `[Unreleased]` 添加一条扁平 `[修复]` 记录。
- [x] 已将可复用日期、历史复用、锁与 fail-open 契约写入 `.trellis/spec/backend/daily-market-context.md`；无需修改根 `AGENTS.md`。

## 4. 验证

- [x] `.venv/bin/python -m py_compile src/core/market_review.py src/services/daily_market_context.py`
- [x] `.venv/bin/python -m pytest tests/test_daily_market_context.py tests/test_market_review.py tests/test_pipeline_daily_market_context.py tests/test_main_schedule_mode.py -q`（126 passed）。
- [x] 使用隔离环境执行 `./scripts/ci_gate.sh`（4442 passed、413 subtests passed、4 deselected）。
- [x] 检查 `git diff --check` 和最终 diff，确认无 API schema、配置或无关重构。

## 5. 风险与回滚点

- 参数只允许由大盘上下文服务传入，避免手工复盘被错误标记为某个缓存目标日。
- 新字段解析失败必须回退旧精确逻辑，不得异常中断个股分析。
- 若目标测试暴露查询隔离语义冲突，先回到规划修订设计，不用宽松 fallback 绕过。
- 回滚为撤销本任务代码/文档；历史中新增的可选 JSON 键可保留并由旧代码忽略。
