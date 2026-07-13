# 持仓与成交截图导入契约

## 1. Scope / Trigger

- 修改持仓截图、成交截图、`trade_time`、Vision 图片调用、四个图片导入 API 或 Web 校对流程时适用。
- 该能力跨越 Vision -> Service -> Repository/DB -> API -> Web，必须同步检查完整数据流。

## 2. Signatures

- `POST /api/v1/portfolio/imports/images/positions/parse`：multipart `account_id`、`snapshot_date`、重复 `files`。
- `POST /api/v1/portfolio/imports/images/positions/commit`：JSON `batch_id/account_id/snapshot_date/positions`。
- `POST /api/v1/portfolio/imports/images/trades/parse`：multipart `account_id`、`default_trade_date`、重复 `files`。
- `POST /api/v1/portfolio/imports/images/trades/commit`：JSON `batch_id/account_id/trades`。
- DB：`PortfolioTrade.trade_time` 为 nullable `TIME`；旧 SQLite 表初始化时幂等补列。

## 3. Contracts

- 只支持活跃 `cn/CNY` 账户、6 位证券代码、每批 1-5 张 JPEG/PNG/WebP/GIF，单文件最大 5MB。
- Vision 只使用显式 `VISION_MODEL`，兼容废弃别名 `OPENAI_VISION_MODEL`；不得使用 `LITELLM_MODEL` 文本主模型顶替。
- 持仓初始化要求账户无任何交易，提交 `symbol/name/quantity/avg_cost`，生成费用和税费为 0 的期初买入；资金汇总不入账。
- 成交提交接受可空 `trade_time`、非负 `fee/tax` 和稳定 `occurrence_index`；前端不得提交或信任客户端生成的 fingerprint/hash。
- 同一指纹的多笔成交必须显式提交不同 `occurrence_index`；批内重复 occurrence 表示重叠冲突未解决，后端必须拒绝，不能自动递增掩盖歧义。
- 成交插入、账本重放、卖出可用量校验和列表查询统一按 `trade_date -> 已知 trade_time -> null time -> stable id/input order` 排序；单笔卖出不得使用同日更晚成交的买入数量。
- parse 只返回校对数据；commit 在单事务中重新校验重复、顺序、超卖和账户条件。原图、base64、raw model response 不持久化、不写普通日志。
- Web 编辑识别错误行后必须按当前字段重算 editable issues/status；`not_executed_trade` 等不可通过字段编辑修复的业务错误继续阻断，跨图 conflict 仍需显式合并或保留。

## 4. Validation & Error Matrix

| 条件 | 结果 |
| --- | --- |
| 未配置 Vision / 缺 provider key | `vision_not_configured` |
| Hermes route 或不支持的图片 | `vision_unsupported` / `unsupported_type` / `invalid_image` |
| 超过 5 张 / 单图超过 5MB | `too_many_files` / `file_too_large` |
| 持仓账户已有交易 | HTTP 409 `account_not_empty`，零写入 |
| 跨图同指纹未决 | Web 禁止提交，用户选择合并或保留 |
| 同指纹批内 occurrence 重复 | HTTP 400 `validation_error`，零写入 |
| 时间线顺序歧义 / 超卖 | HTTP 409 `ambiguous_trade_order` / `portfolio_oversell`，整批回滚 |
| SQLite 写锁冲突 | HTTP 409 `portfolio_busy` |

## 5. Good / Base / Bad Cases

- Good：两张成交图存在同秒合法分笔，用户选择保留多笔后 occurrence 连续编号并原子写入。
- Good：请求中先出现 10:02 卖出、后出现 10:01 买入，提交按成交时间插入，列表倒序展示，快照按 10:01 -> 10:02 重放。
- Base：旧交易 `trade_time=null`，API 返回 `null`，Web 只显示日期，手工录入与 CSV 不受影响。
- Bad：前端把顶部总资产转换成现金流水，提交模型返回的 dedup hash，或让后端把两条 occurrence=1 的相同成交静默改成 1/2。

## 6. Tests Required

- 后端：`tests/test_vision_extraction_service.py`、`tests/test_portfolio_screenshot_import_service.py`、`tests/test_portfolio_api.py`、`tests/test_portfolio_service.py`、`tests/test_storage.py`；必须覆盖重复 occurrence 拒绝、请求顺序与成交时间相反时的真实快照、同日更晚买入不能支持更早卖出。
- Web：API multipart/JSON/snake-case 映射；Dialog 两模式、逐图失败、错误字段编辑后重校验、删除、冲突、未来日期和提交禁用；PortfolioPage 刷新 snapshot/risk/trades 与可空时间显示。
- 可视：桌面/390px 移动视口验证文件列表、错误、review 行和 footer；截图只作 PR/外部证据，不入库。

## 7. Wrong vs Correct

### Wrong

```ts
await apiClient.post('/positions/commit', parsedResponse);
```

这会提交 summary、状态和客户端 hash，并绕过用户校对边界。

### Correct

```ts
await portfolioApi.commitPositionImages({
  batchId,
  accountId,
  snapshotDate,
  positions: reviewedRows.map(({ symbol, name, quantity, avgCost }) => ({
    symbol,
    name,
    quantity,
    avgCost,
  })),
});
```

后端仍必须重新校验并在一个事务中写入。
