# 修复大盘上下文重复生成

## Goal

修复批量个股分析在自然日与有效交易日不一致时连续生成多份大盘复盘的问题，恢复“大盘上下文按目标交易日、市场和报告语言复用”的既有契约，避免重复消耗行情源、搜索服务和 LLM 配额，并避免个股任务因等待大盘复盘锁而显著延迟。

## Background

- 2026-07-15 00:42:55，Web API 通过一次 `POST /api/v1/analysis/analyze` 提交 18 只股票；异步批量入口为每只股票创建独立 Pipeline，任务队列最大并发数为 3。
- `SCHEDULE_ENABLED=false`，重复运行不是定时器触发；日志中的大盘复盘均为 `trigger_source=daily_market_context`。
- 个股 Pipeline 根据市场阶段把大盘上下文目标日解析为有效交易日 `2026-07-14`，代码入口为 `src/core/pipeline.py:402-414`。
- 大盘结构化 payload 使用 `overview.date` 写入 `date`，代码位置为 `src/market_analyzer.py:790-797`。现场记录保存的 payload `date` 为自然日 `2026-07-15`。
- 历史复用按 payload 日期匹配 `target_date`，代码位置为 `src/services/daily_market_context.py:819-844`。因此刚保存的 `2026-07-15` 记录无法满足 `target_date=2026-07-14`。
- 共享大盘复盘锁能够串行化生成，但等待者在锁释放后仍无法命中历史记录，继而获得锁并再次生成，所以表现为一份完成后下一份立刻开始。
- `docs/analysis-context-pack.md` 已规定：优先复用同日同市场历史，没有记录时才生成，并通过 cache 与大盘复盘锁避免重复生成。当前行为违反既有契约。

## Requirements

- R1：同一目标交易日、市场和报告语言的大盘上下文，在首份结果成功持久化的正常路径中最多生成一次；后续任务必须复用已生成结果。
- R2：保留现有 `market_review_payload.date` 的报告生成日语义；新增内部缓存身份字段 `daily_market_context_target_date`，记录 Pipeline 计算出的有效交易日，历史复用不得继续把两个概念混为一谈。
- R3：`market_review_payload.date`、`generated_at` 与历史记录 `created_at` 继续表达报告日期/实际生成时间；内部目标交易日与生成时间必须保持独立，新增字段不得改变 Web/API 既有 payload 契约。
- R4：大盘复盘锁竞争者在首个生成成功后必须能够读到并复用持久化记录，不应等待到上限或串行再次生成。
- R5：保持旧版历史记录可读；不得要求数据库迁移或批量重写已有 `analysis_history`。
- R6：不得放宽到跨市场、跨报告语言或不相关交易日复用。
- R7：保留 `DAILY_MARKET_CONTEXT_ENABLED=false` 与 `MARKET_REVIEW_ENABLED=false` 的现有语义，不新增配置开关作为修复条件。
- R8：修复应覆盖 API 批量任务、普通单股 Pipeline、CLI/调度路径共享的后端 runtime，不改变 Web/API schema 和用户操作流程。
- R9：日期契约与防重行为统一覆盖 `cn/hk/us/jp/kr`，不得为 A 股或本次午夜复现增加特判。
- R10：缺少 `daily_market_context_target_date` 的旧历史记录继续按既有 payload 日期或创建日期精确匹配；禁止增加“前后一天”、周末回退或跨时区猜测等宽松复用规则。
- R11：历史持久化失败时保留现有 fail-open 重试语义，允许后续任务重新生成上下文；不得为追求绝对防重而静默移除个股分析的市场风险护栏。

## Acceptance Criteria

- [x] AC1：在自然日为 T、目标交易日为 T-1 且首份历史成功持久化的批量并发场景中，`run_market_review` 只调用一次，其余任务复用相同市场上下文。
- [x] AC2：大盘上下文历史快照明确携带正确的 `daily_market_context_target_date`；公开 payload 的 `date` 与 `generated_at` 保持既有含义。
- [x] AC3：锁等待者在首个任务保存历史后命中该记录，不触发第二次生成，也不等待到最大重试次数。
- [x] AC4：同市场同交易日但不同报告语言不得互相复用；不同市场不得互相复用。
- [x] AC5：旧记录缺少新日期字段时继续按现有精确兼容规则读取，不破坏历史报告展示；跨日旧记录不得被启发式复用。
- [x] AC6：覆盖盘前、盘中/盘后、周末或节假日回看上一交易日的日期边界测试。
- [x] AC7：`tests/test_daily_market_context.py`、`tests/test_pipeline_daily_market_context.py`、`tests/test_main_schedule_mode.py` 相关回归通过；完整后端质量门禁通过或明确记录环境阻断。
- [x] AC8：`docs/CHANGELOG.md` 与大盘上下文专题文档同步说明修复后的日期契约。
- [x] AC9：历史持久化失败后，后续任务仍可重新生成上下文，现有 fail-open 行为有回归测试保护。

## Out Of Scope

- 新增数据库表、Redis 或分布式任务系统。
- 修改大盘报告正文结构、Web 页面展示或 API schema。
- 自动或手工清理现场已经生成的重复历史记录；如后续需要清理，应另行设计带预览和回滚能力的维护流程。
- 改变报告语言、模型、数据源优先级或通知配置。
