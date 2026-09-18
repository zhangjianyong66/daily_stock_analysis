# 数据库规范

本项目当前使用 SQLite + SQLAlchemy ORM。数据库模型集中在 `src/storage.py`，仓储访问集中在 `src/repositories/`。

## 数据库入口

- `src/storage.py` 定义 `Base`、ORM model、`DatabaseManager`、schema version 和迁移/初始化逻辑。
- 默认数据库路径由配置控制，Docker 默认 `DATABASE_PATH=/app/data/stock_analysis.db`。
- 时间字段大量使用 `DateTime`；`src/storage.py` 提供 `utc_naive_now()`、`to_utc_naive_datetime()` 处理 SQLite UTC-naive 时间。
- 数据表命名使用小写 snake_case，例如 `stock_daily`、`news_intel`、`intelligence_sources`。

## ORM 和表结构

新增持久化表优先在 `src/storage.py` 定义 ORM model，并显式声明：

- `__tablename__`
- 主键
- 必要索引
- 唯一约束
- `created_at` / `updated_at` 等审计字段（如果该业务域已有）
- `to_dict()` 或 service 层序列化方式（按现有域模式选择）

示例模式：

- `StockDaily` 使用 `UniqueConstraint('code', 'date')` 和 `Index('ix_code_date', 'code', 'date')`。
- `NewsIntel` 使用 URL 唯一约束和 `ix_news_code_pub` 组合索引。
- `Portfolio*` 表由 `src/repositories/portfolio_repo.py` 通过仓储管理写入和查询。

## Repository 模式

数据库查询和事务放在 `src/repositories/`，不要放在 API endpoint。

本地模式：

- Repository 构造函数默认使用 `DatabaseManager.get_instance()`。
- 简单读写使用 `with self.db.get_session() as session:`。
- 需要事务锁的写路径封装专用 context manager，例如 `PortfolioRepository.portfolio_write_session()` 使用 `BEGIN IMMEDIATE` 串行化账本写入。
- Repository 可以定义数据库领域异常，例如 `DuplicateTradeUidError`、`PortfolioBusyError`，由 service/API 映射为业务错误。

Service 层负责调用 repository，并把 ORM row 转为 API 友好的 dict。参考 `src/services/portfolio_service.py` 的账户、交易、快照流程。

## 查询和事务

- 使用 SQLAlchemy `select()`、`and_()`、`delete()`、`func()` 等结构化 API。
- 分页接口应返回 `items`、`total`、`page`、`page_size` 这类明确字段，参考 portfolio 列表 schema。
- 唯一冲突、SQLite 锁冲突等应捕获并转换为领域异常，不要直接把底层异常泄漏给 API 用户。
- 多步写入必须放在同一 session/事务内；写入后需要跨 session 返回 row 时，可 `session.expunge(row)` 或在 service 层复制为 dict。

## 迁移和兼容

当前仓库没有独立 Alembic 目录；schema 管理集中在 `src/storage.py` 的初始化/迁移逻辑和 `schema_migrations` 标记。

修改表结构时必须：

- 检查既有数据升级路径，避免只支持空库。
- 增加或调整覆盖旧库场景的测试。
- 检查 Docker volume 持久化路径和 GitHub Actions smoke import。
- 更新 API schema、Web 类型和文档中暴露的数据字段。

## 场景：合并多个启动期 SQLite 迁移

### 1. Scope / Trigger

- Trigger：新增迁移，或合并上游后 `DatabaseManager` 启动序列同时包含多条 `_ensure_*` schema 检查。

### 2. Signatures

- `DatabaseManager.__init__(db_url)` 在 `Base.metadata.create_all()` 后按显式顺序调用迁移。
- 每条迁移使用 `_ensure_<domain>_<schema>() -> None`，检查失败时抛出异常并阻止数据库以未知结构继续启动。

### 3. Contracts

- 迁移顺序是可测试契约，不是可任意重排的实现细节。
- 新增迁移必须保留已有迁移的安全失败入口；依赖特定检查器异常或日志的迁移应排在会使用同一检查器的宽泛兼容迁移之前。
- 幂等迁移在空库、旧库和重复启动时都必须安全；不得因为前置迁移吞掉异常而跳过后续结构校验。

### 4. Validation & Error Matrix

- 列或索引检查失败 -> 记录所属迁移的 `ERROR` 日志并重新抛出，初始化失败。
- 已存在目标列/索引 -> 不重复修改，继续后续迁移。
- 多条迁移共享 `inspect()` 且顺序改变 -> 对每条迁移的失败归因测试必须仍命中对应日志。

### 5. Good/Base/Bad Cases

- Good：`decision_profile` 检查失败时日志明确包含该迁移名称，且数据库初始化抛出原始异常。
- Base：空库完成 `create_all()` 后所有 `_ensure_*` 重复执行无副作用。
- Bad：把另一条使用 `inspect().get_columns()` 的迁移插到安全检查之前，导致异常被错误归因或目标迁移测试不再执行。

### 6. Tests Required

- 旧库升级测试断言目标列、索引和回填结果。
- 检查器故障测试使用 patch 注入异常，并断言对应迁移的日志、异常传播和 `DatabaseManager` 单例清理。
- 调整启动迁移顺序后至少运行 `tests/test_storage.py` 全文件。

### 7. Wrong vs Correct

#### Wrong

```python
Base.metadata.create_all(self._engine)
self._ensure_generic_columns()  # 先消耗/触发共享 inspector 故障
self._ensure_decision_signal_profile_schema()
```

#### Correct

```python
Base.metadata.create_all(self._engine)
self._ensure_decision_signal_profile_schema()  # 保留专属安全失败与日志契约
self._ensure_generic_columns()
```

## 禁止项

- 不在 endpoint 里手写 SQL 或直接管理 session。
- 不绕过 `DatabaseManager` 新建独立 SQLite 连接，除非是明确隔离的数据文件并有文档说明。
- 不依赖 SQLite 隐式并发行为处理关键写路径；需要串行化时像 portfolio 账本一样显式加写事务。
- 不把外部原始 payload 直接长期存储为唯一数据来源，除非同时保存规范化字段和查询索引。

## 场景：`StockDaily.canonical_id` 启动迁移与双写

### 1. Scope / Trigger

- Trigger：日线记录需要跨市场稳定标识，或上游合并引入 canonical target 解析。

### 2. Signatures

- `DatabaseManager._ensure_stock_daily_canonical_id() -> None`
- `DatabaseManager.save_daily_data(df, code, data_source="Unknown", canonical_id=None) -> int`

### 3. Contracts

- 旧库启动时幂等添加 `stock_daily.canonical_id` 和普通索引，并回填可解析记录；无法解析的旧记录保持 `NULL`。
- 显式 `canonical_id` 优先，未提供时使用 `parse_analysis_target(code)` 推导；更新已有日线时不能用 `NULL` 覆盖非空值。
- 检查器、回填或索引验证失败必须记录迁移归因并阻止数据库以未知结构继续启动。

### 4. Validation & Error Matrix

- 空库、旧库、重复启动 -> 结构和索引保持一致，无重复迁移副作用。
- 注册表为空 -> canonical 修复跳过并记录 warning，不改写原始代码。
- 单行解析失败 -> 该行保持可用，继续处理其他行并记录统计。

### 5. Good/Base/Bad Cases

- Good：`save_daily_data(..., canonical_id="sh600519")` 双写并在重复日期更新时保留该值。
- Base：旧库启动完成列、索引和可解析行回填。
- Bad：只修改 ORM 模型而不迁移旧 SQLite 文件，或用空值覆盖已有 canonical ID。

### 6. Tests Required

- `tests/test_storage.py` 覆盖迁移、回填、索引、推导、修复、幂等和显式双写。

### 7. Wrong vs Correct

#### Wrong

```python
existing.canonical_id = record["canonical_id"]  # NULL 会覆盖旧值
```

#### Correct

```python
if record["canonical_id"] is not None:
    existing.canonical_id = record["canonical_id"]
```
