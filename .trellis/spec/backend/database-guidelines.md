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

## 禁止项

- 不在 endpoint 里手写 SQL 或直接管理 session。
- 不绕过 `DatabaseManager` 新建独立 SQLite 连接，除非是明确隔离的数据文件并有文档说明。
- 不依赖 SQLite 隐式并发行为处理关键写路径；需要串行化时像 portfolio 账本一样显式加写事务。
- 不把外部原始 payload 直接长期存储为唯一数据来源，除非同时保存规范化字段和查询索引。
