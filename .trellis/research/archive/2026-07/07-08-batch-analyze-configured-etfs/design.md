# 前端批量分析配置标的设计

## 方案选择

### 推荐方案：前端读取自选队列后提交全部配置编码

首页点击批量分析入口后读取当前自选队列，去除空值并按现有股票代码等价语义去重，弹出确认框，用户确认后调用 `analysisApi.analyzeAsync({ stockCodes, notify, reportType: "detailed" })`。

优点：复用现有 `STOCK_LIST`、`/api/v1/stocks/watchlist` 和批量分析 API，影响面最小，且符合用户“所有编码都支持批量分析”的最新要求。缺点：批量提交数量可能更多，因此确认框必须展示数量和代码。

### 备选方案：新增独立批量配置项

新增独立配置项，只从新的批量分析列表提交。优点是语义显式；缺点是要改 `.env.example`、配置注册、设置页、文档和后端读取，且与现有自选队列产生双配置维护成本。本任务不采用。

### 备选方案：后端新增“分析全部配置标的”接口

后端负责读取配置并提交全部配置标的。优点是前端更薄；缺点是新增 API 合约和测试面。本任务不采用。

## 架构与边界

- 修改范围集中在 `apps/dsa-web/`。
- 首页 `HomePage.tsx` 增加配置标的批量提交流程和确认弹窗。
- 复用 `systemConfigApi.getWatchlist()` 读取配置标的。
- 复用 `apps/dsa-web/src/utils/stockCode.ts` 中已有的等价匹配语义对配置编码去重，不新增平行规范化规则。
- 复用 `analysisApi.analyzeAsync()` 的 `stockCodes` 批量字段提交任务。
- 复用 `ConfirmDialog` 展示二次确认。
- 不修改后端 API、配置项、任务队列协议或股票索引生成逻辑。

## 数据流

1. 用户点击首页顶部操作区批量分析按钮。
2. 前端读取当前自选队列。
3. 前端清理空白编码，并用 `stockCode.ts` 现有 normalize/equivalence 语义去重。
4. 若配置编码列表为空，展示提示，不打开提交确认。
5. 若存在配置编码，打开 `ConfirmDialog`，提示即将提交的数量和代码。
7. 用户确认后调用 `analysisApi.analyzeAsync`：
   - `stockCodes`: 配置编码列表
   - `reportType`: `detailed`
   - `notify`: 首页当前通知开关状态
8. 提交成功后展示 accepted / duplicate 摘要；任务进度继续由现有 SSE / active task 机制展示。

## 交互与状态

- 按钮位置：首页顶部操作区，“推送通知”后、“大盘复盘”前。
- 按钮文案：中文“批量分析配置”或等价短文案，英文“Batch Analyze”或等价短文案。
- 确认弹窗文案展示数量和代码，避免误触批量消耗额度。
- 提交中禁用批量按钮和确认按钮，避免重复提交。

## 错误处理

- 自选队列读取失败：展示 API 错误提示。
- 无配置编码：展示“当前自选队列没有可批量分析的配置标的”。
- 批量提交失败：展示解析后的 API 错误。
- 批量提交部分重复：根据 `BatchTaskAcceptedResponse.duplicates` 展示重复数量，不当作整体失败。
- 单只重复的 409 兼容路径保留在 `analysisApi.analyzeAsync`，批量路径正常接收响应体中的 `duplicates`。

## 兼容性

- 不改变已有单股分析请求。
- 不改变大盘复盘请求。
- 不改变自选队列保存格式。
- 不新增配置项，因此无需更新 `.env.example`。
- 新增用户可见能力，需要更新 `docs/CHANGELOG.md` 的 `[Unreleased]` 段。

## 测试

- `HomePage` 单元测试覆盖：
  - 自选队列中混有普通股票和 ETF 时，全部提交。
  - 空自选队列时提示用户，不调用批量分析 API。
  - 批量返回 accepted + duplicates 时展示摘要。
  - 通知开关状态会传入批量分析请求。
- 如新增去重 helper，应补充纯函数单元测试覆盖等价代码变体。

## 回滚

回滚前端改动即可移除按钮和批量提交入口；后端和配置没有迁移或新增状态。
