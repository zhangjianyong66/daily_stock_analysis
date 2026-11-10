# 持仓与成交截图识别导入设计

## 1. Design Summary

本功能在现有持仓账本上增加两条受控入口：空账户持仓截图初始化、已有账户实际成交截图增量导入。两条流程共享图片安全校验和 `VISION_MODEL` 调用，但使用独立 prompt、schema、合并和提交语义。图片解析与账本提交分离，用户必须在中间校对；提交端重新校验所有约束。

## 2. Component Boundaries

### 2.1 Shared Vision Client

新增 `src/services/vision_extraction_service.py`：

- `validate_image(image_bytes, mime_type)`：MIME、魔数、空文件和 5MB 限制。
- `resolve_vision_model()`：复用现有 `VISION_MODEL`、deprecated alias 和 provider key 解析。
- `complete_vision(image_bytes, mime_type, prompt, max_tokens)`：构造 LiteLLM image request、执行 Hermes guard、超时和重试，只返回文本给调用方。

`src/services/image_stock_extractor.py` 保留既有公开函数与常量，通过共享 client 完成调用；股票代码解析规则不迁移到共享层。

### 2.2 Portfolio Screenshot Domain Service

新增 `src/services/portfolio_screenshot_import_service.py`：

- `parse_position_images`：逐图识别当前持仓、合并代码、生成校验问题。
- `parse_trade_images`：逐图识别实际成交、补齐批次日期、生成去重候选与跨图冲突。
- `commit_initial_positions`：空账户原子初始化。
- `commit_trade_batch`：已有账户重复过滤、完整账本数量重放和原子增量写入。

该服务不得保存图片或 raw response。日志只输出 `batch_id`、图片数、行数、耗时和错误码。

### 2.3 Existing Portfolio Layers

- `src/storage.py`：`PortfolioTrade.trade_time` 增加可空 `Time` 列；初始化时为旧 SQLite 表幂等补列。
- `src/repositories/portfolio_repo.py`：提供 session 内账户/交易查询、重复检查和交易插入方法，不自行打开嵌套事务。
- `src/services/portfolio_service.py`：现有单笔 `record_trade` 复用 session 内 helper；列表序列化包含可空时间。
- `api/v1/endpoints/portfolio.py`：只处理 multipart/JSON 边界、调用 service 和异常映射。

## 3. API Contracts

### 3.1 Position Parse

`POST /api/v1/portfolio/imports/images/positions/parse`

Multipart fields：`account_id`、`snapshot_date`、重复字段 `files`（1-5）。

响应核心结构：

```json
{
  "batch_id": "uuid",
  "account_id": 1,
  "snapshot_date": "2026-07-13",
  "files": [{"index": 0, "status": "success", "record_count": 5, "error": null}],
  "summary": {"total_assets": 12000.00, "available_cash": 2000.00},
  "positions": [{
    "source_refs": [{"file_index": 0, "row_index": 0}],
    "symbol": "600000",
    "name": "示例股份",
    "quantity": 1000,
    "avg_cost": 10.00,
    "current_price": 10.20,
    "market_value": 10200.00,
    "available_quantity": 0,
    "weight_pct": 85.00,
    "confidence": "high",
    "status": "ready",
    "issues": []
  }]
}
```

`summary` 只用于预览，不进入 commit schema。

### 3.2 Position Commit

`POST /api/v1/portfolio/imports/images/positions/commit`

```json
{
  "batch_id": "uuid",
  "account_id": 1,
  "snapshot_date": "2026-07-13",
  "positions": [{"symbol": "600000", "name": "示例股份", "quantity": 1000, "avg_cost": 10.00}]
}
```

后端忽略任何客户端提交的市价、市值、账户空状态或 ready 状态，只使用规范化必填字段重新校验。

### 3.3 Trade Parse

`POST /api/v1/portfolio/imports/images/trades/parse`

Multipart fields：`account_id`、`default_trade_date`、`files`（1-5）。

每行返回：`trade_date`、`trade_time`、`symbol`、`name`、`side`、`quantity`、`price`、`fee`、`tax`、`trade_uid`、`fingerprint`、`occurrence_index`、`status`、`issues`、`source_refs`。没有明确费用时 `fee/tax=0` 并增加 warning。

### 3.4 Trade Commit

`POST /api/v1/portfolio/imports/images/trades/commit`

只接收用户确认后的交易字段及 `occurrence_index`。服务端重新生成 fingerprint 和 dedup hash，不接受客户端提供的 hash。跨图冲突必须已经通过删除/合并/保留形成无歧义行集。

响应统一返回：`record_count`、`inserted_count`、`duplicate_count`、`failed_count`、`errors`；原子失败时 `inserted_count=0`。

## 4. Prompt and Parsing Contracts

持仓 prompt 明确区分：

- `quantity` 来自“持仓”，绝不能来自“可用”。
- `avg_cost` 来自“成本”。
- 顶部汇总与逐行持仓分开输出。
- 不可见字段返回 `null`，不得计算或猜测。

成交 prompt 明确要求：

- 仅输出选中的“当日成交/历史成交”实际成交行。
- “均价/数量”布局分别映射 `price/quantity`。
- 行内只有时间时使用请求中的默认日期。
- 禁止把顶部 tab、列标题、委托数据或右侧箭头识别为成交。

模型响应先用 `json.loads`，失败时可复用 `json_repair`；修复后仍必须通过 Pydantic/领域校验。解析失败按图片返回错误，不回传 raw response。

## 5. Merge and Dedup Algorithm

### 5.1 Position Merge

按规范化 6 位代码分组：

- 数量和成本相同：合并 `source_refs`。
- 任一不同：`status=conflict`，用户编辑或删除后才能提交。
- 名称不同但代码相同：产生名称校验 warning，不自动拆成两只证券。

### 5.2 Trade Fingerprint

基础指纹字段：

```text
trade_date|trade_time|symbol|side|quantity|price|fee|tax
```

数值在 hash 前使用 Decimal 规范化，避免 `1.10` 与 `1.1` 不一致。最终 dedup hash 加入 `occurrence_index`，允许同一图片内完全相同的合法分笔：

```text
sha256("portfolio_image_trade|" + base_fingerprint + "|" + occurrence_index)
```

- 同一图片同指纹按页面顺序编号 1..N。
- 跨图片同指纹默认形成 overlap conflict；用户合并后保留所需数量，服务端再连续编号。
- 有 `trade_uid` 时先按账户内成交编号判重，同时仍保存 dedup hash。

## 6. Atomic Ledger Writes

### 6.1 Position Initialization

在一个 `portfolio_write_session` 中：锁定并验证账户 active、`cn/CNY`；确认不存在任何交易；校验代码唯一、数量/成本为正；生成确定性 `trade_uid/dedup_hash`；批量插入所有 buy 记录。任一步异常回滚。

### 6.2 Incremental Trades

在一个 `portfolio_write_session` 中：

1. 规范化并按日期、时间、稳定输入顺序排序。
2. 在同一 session 内判定已有 `trade_uid/dedup_hash`，明确重复项移出新增集合。
3. 把现有交易与全部新增交易组成候选账本，按时间线重放数量；卖出导致任一时点数量为负则拒绝整个新增集合。
4. 对同日缺失时间且顺序会影响超卖结论的历史数据返回 `ambiguous_trade_order`，不猜测顺序。
5. 插入全部新增记录并提交；SQLite busy 映射 `portfolio_busy`。

企业行动继续由现有快照重放处理；本任务不从截图生成公司行动。数量校验应复用或提取现有持仓重放规则，避免另写不一致算法。

## 7. Web State Machine

新增 `PortfolioImageImportDialog`，状态固定为：

```text
select -> parsing -> review -> committing -> completed
                    \-> select (replace/retry)
```

- 入口使用“图片导入”命令，内部用 segmented control 选择持仓初始化/成交增量。
- review 桌面使用紧凑表格，移动端使用逐行编辑列表；不把表格塞入嵌套卡片。
- 失败文件保留在文件列表并显示重试/移除操作。
- 冲突、错误、warning 分级显示；存在 error/conflict 时禁用提交。
- 完成后刷新 snapshot、trades 和相关 risk 数据。

## 8. Error and Privacy Model

- 文件错误：`unsupported_type`、`file_too_large`、`invalid_image`、`too_many_files`。
- Vision 错误：`vision_not_configured`、`vision_unsupported`、`vision_timeout`、`vision_rate_limited`、`vision_failed`。
- 业务错误：`account_not_empty`、`unsupported_account_market`、`ambiguous_overlap`、`ambiguous_trade_order`、`portfolio_oversell`、`portfolio_busy`。
- API 继续使用 `{error,message,detail}` envelope，不返回 traceback、key、base64 或 raw model text。

## 9. Compatibility, Rollout, and Rollback

- `trade_time` 是 nullable additive migration；旧数据与旧调用方保持有效。
- 现有 CSV 与手工交易默认 `trade_time=None`；接口字段只追加不删除。
- 先交付共享 Vision 与 schema 基础，再交付持仓初始化，再交付成交增量和统一 Web 流程。
- 回滚 UI/API 后可保留 nullable `trade_time`；共享 Vision 层回滚时恢复现有 extractor 内部调用即可，不需要删除用户交易。

## 10. Verification Strategy

- 后端单元测试使用构造 JSON/model response，不提交真实截图。
- API 测试覆盖 multipart 1-5 文件、逐图失败、schema、错误 envelope 和原子写入。
- 旧库测试手工创建无 `trade_time` 的 `portfolio_trades` 后初始化并验证幂等补列。
- Web Vitest 覆盖两模式、日期、文件状态、编辑、冲突处理、禁用提交和完成刷新。
- 执行 `./scripts/ci_gate.sh`、目标 pytest、Web test/lint/build；在线 Vision smoke 仅在有可用配置且明确允许产生费用时执行。
