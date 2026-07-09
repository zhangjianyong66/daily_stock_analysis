# 前端批量分析配置标的

## Goal

在 Web 首页增加一个批量分析入口，一键提交 `STOCK_LIST` / 自选队列中所有已配置编码的异步分析任务，减少用户逐只输入股票或 ETF 代码的重复操作。

## Confirmed Facts

- 当前 Web 首页只有单只股票分析按钮，点击后调用 `handleSubmitAnalysis()`，最终只向 `analysisApi.analyzeAsync` 传入 `stockCode`。
- 前端 API 层已支持批量字段：`AnalysisRequest.stockCodes` 会映射为后端请求体 `stock_codes`。
- 后端 `/api/v1/analysis/analyze` 已支持 `stock_codes` + `async_mode=true` 的批量异步分析，返回 `BatchTaskAcceptedResponse`。
- 当前配置化自选队列来自 `STOCK_LIST`，前端可通过 `systemConfigApi.getWatchlist()` 调用 `/api/v1/stocks/watchlist` 读取。
- 用户已调整范围：批量入口应提交当前 `STOCK_LIST` / 自选队列中的所有编码，不再限制为 ETF。
- 点击后需要轻量二次确认，确认内容应展示即将提交的编码数量和代码。
- 前端已有通用 `ConfirmDialog`，批量分析确认交互应优先复用该组件。
- 批量分析应跟随首页现有 `notify` 勾选状态，保持和单股分析 / 大盘复盘一致的通知语义。
- 按钮放在首页顶部操作区，位于“推送通知”后、“大盘复盘”前。
- 当前单股分析提交后主要依赖 SSE / active task 刷新链路展示任务进度，批量分析也应复用该任务展示链路。

## Requirements

- 在首页提供用户可见的配置标的批量分析入口。
- 点击后应读取当前自选队列 / `STOCK_LIST` 中配置的标的。
- 提交所有非空配置编码，不按 ETF / 普通股票过滤。
- 标的来源固定为当前自选队列，不新增 `ETF_LIST` 或其他独立配置项。
- 点击批量分析后必须先打开确认对话框；用户确认后才提交批量异步分析任务。
- 批量请求中的 `notify` 字段应使用首页当前通知复选框状态。
- 批量分析按钮放在首页顶部操作区“推送通知”后、“大盘复盘”前。
- 批量提交应复用现有 `analysisApi.analyzeAsync` 的 `stockCodes` 能力，保持异步队列与任务面板的现有行为。
- 空配置列表、读取失败、全部重复任务等情况需要有明确的用户反馈。

## Out of Scope

- 不新增 `ETF_LIST`、数据库表或后端配置语义。
- 不新增新的任务队列协议；复用现有批量异步分析 API。
- 不改变单股分析、大盘复盘或自选队列增删行为。
- 不在本任务内重做股票索引生成逻辑；批量提交不依赖股票索引识别资产类型。

## Open Questions

- 无阻塞开放问题。

## Acceptance Criteria

- [ ] 首页能看到配置标的批量分析按钮或等价入口。
- [ ] 点击入口后，会批量提交 `STOCK_LIST` / 自选队列中所有非空编码的异步分析任务。
- [ ] 普通股票和 ETF 都会被纳入批量提交。
- [ ] 当没有配置编码时，页面提示用户当前没有可批量分析的配置标的。
- [ ] 当部分编码已有进行中任务时，页面能体现 accepted / duplicate 的结果，不误报为全部失败。
- [ ] 相关前端单元测试覆盖成功提交、空配置、重复任务响应至少三个路径。

## Notes

- 本任务涉及前端交互、现有自选队列 API 和批量分析 API 调用，属于小型功能但需要 `design.md` / `implement.md` 明确边界后再实现。
