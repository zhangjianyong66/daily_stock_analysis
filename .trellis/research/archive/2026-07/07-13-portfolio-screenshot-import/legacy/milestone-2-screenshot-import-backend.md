# Milestone 2: 截图解析与原子导入后端

前置：Milestone 1 已通过局部门禁。目标：实现两类 prompt/解析、多图冲突、best-effort 去重、完整账本重放和四个 API。

## Task 1: 持仓截图解析与多图合并

**Files:**
- Create: `src/services/portfolio_screenshot_import_service.py`
- Create: `tests/test_portfolio_screenshot_import_service.py`

- [x] 写失败测试，使用人工构造 model response：`持仓=1000`、`可用=0`、`成本=10.00`、`市价=10.20`、`市值=10200`；断言 quantity 使用持仓而非可用。
- [x] 增加测试：同代码相同数量/成本合并；不同数量或成本返回 conflict；名称差异只 warning；顶部资金只进入 summary。
- [x] 运行 `python -m pytest tests/test_portfolio_screenshot_import_service.py -q`，预期服务不存在而失败。
- [x] 实现持仓 prompt、Pydantic 内部 DTO，以及 `parse_position_images(*, account_id: int, snapshot_date: date, images: list[ImageInput]) -> dict[str, Any]`；最小结果断言为：

```python
result = service.parse_position_images(account_id=account_id, snapshot_date=snapshot_date, images=images)
assert result["positions"][0]["quantity"] == 1000
assert result["positions"][0]["avg_cost"] == 10.00
```

- [x] 校验 1-5 图片、`cn/CNY` 账户、6 位代码、正数量/成本；逐图错误保留，禁止记录 raw response。
- [x] 运行目标测试，预期通过。
- [ ] 经用户明确确认后提交：`feat(portfolio): 实现持仓截图结构化解析`。

## Task 2: 成交截图解析、指纹与歧义

**Files:**
- Modify: `src/services/portfolio_screenshot_import_service.py`
- Modify: `tests/test_portfolio_screenshot_import_service.py`

- [x] 写失败测试，使用人工构造“当日成交”响应：批次日期补齐、`10:01:02`、买入、价格 `10.20`、同秒数量 `300/200`，费用默认 0 且 warning。
- [x] 增加测试：委托/撤单拒绝；历史行内日期优先；未来日期拒绝；Decimal 规范化；同图同秒合法分笔保留；跨图同指纹 conflict。
- [x] 运行目标测试，预期成交函数不存在或断言失败。
- [x] 实现 `parse_trade_images(*, account_id: int, default_trade_date: date, images: list[ImageInput]) -> dict[str, Any]`、`build_trade_fingerprint(record: Mapping[str, Any]) -> str` 和 `build_trade_dedup_hash(record: Mapping[str, Any], occurrence_index: int) -> str`；固定以下结果：

```python
result = service.parse_trade_images(account_id=account_id, default_trade_date=trade_date, images=images)
assert result["trades"][0]["trade_time"] == "10:01:02"
assert result["trades"][0]["quantity"] == 300
assert result["trades"][0]["fee"] == 0
```

- [x] 有成交编号时保留 `trade_uid`；无编号时按可见字段+连续 occurrence 生成 hash；跨图冲突不自行决策。
- [x] 运行目标测试，预期通过。
- [ ] 经用户明确确认后提交：`feat(portfolio): 实现成交截图解析与去重`。

## Task 3: 原子初始化与增量账本重放

**Files:**
- Modify: `src/repositories/portfolio_repo.py`
- Modify: `src/services/portfolio_service.py`
- Modify: `src/services/portfolio_screenshot_import_service.py`
- Modify: `tests/test_portfolio_screenshot_import_service.py`
- Modify: `tests/test_portfolio_service.py`

- [x] 写失败测试：空账户持仓整批成功；已有交易拒绝；第二行失败时零插入；busy 转领域错误。
- [x] 写失败测试：已有重复项跳过；新买卖按时间重放；超卖整批回滚；回填历史卖出导致后续数量为负时拒绝；同日 null-time 顺序敏感返回 `ambiguous_trade_order`。
- [x] 运行目标测试，预期批量方法不存在而失败。
- [x] 增加 session 内 repository 方法，以及 `commit_initial_positions` / `commit_trade_batch` service 边界；固定原子结果形状：

```python
result = service.commit_trade_batch(account_id=account_id, batch_id=batch_id, trades=trades)
assert result == {
    "record_count": len(trades),
    "inserted_count": len(trades),
    "duplicate_count": 0,
    "failed_count": 0,
    "errors": [],
}
```

- [x] 单笔 `record_trade` 与批量提交复用同一个规范化/插入 helper；批量方法只打开一次 `portfolio_write_session`。
- [x] 候选账本合并现有与新增交易后执行完整数量时间线校验；不要用逐行外层事务拼接原子性。
- [x] 运行目标测试，预期通过。
- [ ] 经用户明确确认后提交：`feat(portfolio): 支持截图交易原子写入`。

## Task 4: 四个 API 与契约测试

**Files:**
- Modify: `api/v1/schemas/portfolio.py`
- Modify: `api/v1/schemas/__init__.py`
- Modify: `api/v1/endpoints/portfolio.py`
- Modify: `tests/test_portfolio_api.py`

- [x] 写失败 API 测试：1-5 multipart files、超过 5 张、单图超限、逐图失败响应、position/trade commit、统一错误 envelope、原子回滚。
- [x] 运行 `python -m pytest tests/test_portfolio_api.py -q`，预期新路由 404。
- [x] 定义 parse/commit request/response models，endpoint 只读取受限文件、调用 service、映射 `validation_error/account_not_empty/portfolio_oversell/portfolio_busy`。
- [x] 确认 parse response 不含 raw model text；commit endpoint 重新生成 fingerprint/hash，不接受客户端 hash。
- [x] 运行 `python -m pytest tests/test_portfolio_screenshot_import_service.py tests/test_portfolio_service.py tests/test_portfolio_api.py -q`，预期通过。
- [x] 运行 `./scripts/ci_gate.sh`、`git diff --check`；更新 checkbox 后停止，不继续 Milestone 3。
- [ ] 经用户明确确认后提交：`feat(api): 增加持仓与成交截图导入接口`。

## Verification Notes

- 2026-07-13：共享 Vision、原图片提取、截图导入服务、Portfolio Service/API 共 143 个目标测试通过；Python 编译与变更文件关键 flake8 通过。
- 2026-07-14 最终集成复核：完整 `./scripts/ci_gate.sh` 通过，截图导入 service/API 的原子写入、合法相同分笔保留和超卖回滚均包含在全量离线回归中。
- 未执行在线 Vision 调用；测试只使用人工构造响应和合成魔数图片。提交项保留未勾选，等待用户明确授权。
