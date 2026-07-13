# Milestone 1: 共享 Vision 与成交时间基础

目标：在不改变现有图片股票提取行为的前提下，建立可复用 Vision client，并让 `trade_time` 以可空追加字段贯穿存储与后端 API。

## Task 1: 提取共享 Vision Client

**Files:**
- Create: `src/services/vision_extraction_service.py`
- Create: `tests/test_vision_extraction_service.py`
- Modify: `src/services/image_stock_extractor.py`
- Test: `tests/test_image_stock_extractor_litellm.py`

- [x] 写失败测试，固定 `validate_image()` 的 MIME/魔数/5MB 行为，以及 `complete_vision()` 的 `VISION_MODEL`、Hermes guard、API base、timeout 和重试参数。
- [x] 运行 `python -m pytest tests/test_vision_extraction_service.py -q`，预期因模块不存在而失败。
- [x] 实现 `validate_image(image_bytes: bytes, mime_type: str) -> str`、`resolve_vision_model(config: Config | None = None) -> str` 和 `complete_vision(image_bytes: bytes, mime_type: str, prompt: str, *, max_tokens: int = 1024) -> str`。测试中的最小调用形状固定为：

```python
validated_mime = validate_image(png_bytes, "image/png")
assert validated_mime == "image/png"
raw_text = complete_vision(png_bytes, validated_mime, "return []", max_tokens=128)
assert raw_text == "[]"
```

- [x] 修改 `extract_stock_codes_from_image()` 调用共享 client，保留现有 public constants/functions 和返回结构。
- [x] 运行 `python -m pytest tests/test_vision_extraction_service.py tests/test_image_stock_extractor_litellm.py -q`，预期全部通过。
- [ ] 经用户明确确认后提交：`refactor(vision): 提取共享图片模型调用层`。

## Task 2: 增加可空 trade_time 与旧库迁移

**Files:**
- Modify: `src/storage.py`
- Modify: `tests/test_storage.py`

- [x] 写失败测试：新库存在 `portfolio_trades.trade_time`；手工创建的旧表初始化后自动补 `TIME` 列；重复初始化幂等。
- [x] 运行 `python -m pytest tests/test_storage.py -q`，预期缺列断言失败。
- [x] 在 ORM 增加 `trade_time = Column(Time, nullable=True)`，并在数据库初始化中调用：

```python
def _ensure_portfolio_trade_time_column(self) -> None:
    """Idempotently add nullable trade_time to legacy SQLite databases."""
```

- [x] 复用现有 SQLite lock retry、duplicate-column 识别并执行 `ALTER TABLE portfolio_trades ADD COLUMN trade_time TIME`，不重建表、不伪造旧值。
- [x] 运行 `python -m pytest tests/test_storage.py -q`，预期通过。
- [ ] 经用户明确确认后提交：`feat(portfolio): 增加可空成交时间字段`。

## Task 3: trade_time 后端契约贯通

**Files:**
- Modify: `src/repositories/portfolio_repo.py`
- Modify: `src/services/portfolio_service.py`
- Modify: `api/v1/schemas/portfolio.py`
- Modify: `api/v1/schemas/__init__.py`
- Modify: `api/v1/endpoints/portfolio.py`
- Modify: `tests/test_portfolio_service.py`
- Modify: `tests/test_portfolio_api.py`

- [x] 写失败测试：创建交易可传 `datetime.time`/`HH:MM:SS`；不传保持 `None`；列表响应序列化 `trade_time`；非法时间返回 validation error。
- [x] 运行 `python -m pytest tests/test_portfolio_service.py tests/test_portfolio_api.py -q`，预期字段或参数不存在而失败。
- [x] 扩展 `record_trade`，在 `dedup_hash` 前增加 keyword-only `trade_time: time | str | None = None`，并扩展 schema：

```python
class PortfolioTradeCreateRequest(BaseModel):
    trade_time: Optional[time] = None

class PortfolioTradeListItem(BaseModel):
    trade_time: Optional[str] = None
```

- [x] Repository 插入、查询和 service serializer 使用 `HH:MM:SS`；旧数据返回 `null`。
- [x] 运行目标测试，预期通过；再运行 `python -m py_compile src/storage.py src/repositories/portfolio_repo.py src/services/portfolio_service.py api/v1/schemas/portfolio.py api/v1/endpoints/portfolio.py`。
- [ ] 经用户明确确认后提交：`feat(api): 贯通持仓成交时间契约`。

## Task 4: 基础回归门禁

**Files:**
- Modify only if failures reveal a contract regression.

- [x] 运行 `python -m pytest tests/test_image_stock_extractor_litellm.py tests/test_storage.py tests/test_portfolio_service.py tests/test_portfolio_api.py -q`。
- [x] 运行 `./scripts/ci_gate.sh`；若出现与本 milestone 无关的既有失败，记录命令和失败用例，不扩展修复范围。
- [x] 检查 `git diff --check` 和 `git status --short`，确认没有真实截图、临时数据库或密钥文件。
- [x] 更新本文件 Task 1-4 checkbox；停止，不继续 Milestone 2。

## Verification Notes

- 2026-07-13：共享 Vision、存储、Portfolio Service/API 共 134 个目标测试通过；其中覆盖仅配置文本模型/API Key 时不触发 Vision。Web API 测试 2 个通过，lint 与 build 通过。
- 2026-07-14 最终集成复核：修复 Trellis 当前脚本的 `F824`，并让 Flake8 排除 Git 忽略的 `.trellis/.backup-*` 恢复备份后，完整 `./scripts/ci_gate.sh` 通过。
- 各 Task 的提交项保留未勾选，等待用户明确授权；按用户最新要求，本次在 Milestone 1 完成后暂停，不进入 Milestone 2。
