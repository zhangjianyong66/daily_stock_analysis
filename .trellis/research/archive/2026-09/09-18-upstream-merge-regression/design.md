# 技术设计

## 边界

以当前 `main` 的合并提交 `0838d366` 为基线，先修复导入和跨模块契约，再按后端、Web、数据源与部署分层验证。不得通过整体覆盖 `ours/theirs` 解决后续问题。

## 兼容策略

- 上游核心 API、指数身份、ResearchArtifact、Screening 和安全修复作为主契约。
- 本地 ETF、搜索审计、Vision、策略快照和实时行情隔离逻辑作为必须保留的本地契约。
- 对新增字段优先采用可选字段和旧客户端兼容读取；对删除或重命名模块提供兼容导入或明确迁移。
- 数据库模型与迁移顺序遵循现有 `src/storage.py` 契约，新增表必须有幂等启动路径。

## 验证层次

1. 静态：冲突标记、Python 编译、配置/Schema 导入。
2. 后端：API、存储、数据源 fallback、搜索、ETF、Vision、策略和任务队列定向回归。
3. Web/Desktop：前端 lint/build，必要时桌面端构建。
4. 部署：Dockerfile 导入 smoke、Compose 配置静态检查；在线 Provider 只做明确授权的 smoke。

## 数据流与契约重点

- 分析请求从 API Schema 进入服务层，再进入 Pipeline/市场复盘、任务队列和报告持久化；新增 `asset_type`、`region`、`report_language` 等字段必须在入口、内部请求对象、任务快照和响应读取路径保持可选兼容。
- 指数与数据源链路从注册表/市场代码进入 loader，再被分析上下文和报告消费；指数元数据缺失只能影响对应能力，不得让普通股票分析整体失败。
- 搜索、ETF 资金流、实时行情和 Vision 仍沿用本地 fail-open、审计、singleflight、超时和隔离约束；上游新增能力只能通过既有服务边界接入。
- Web 页面消费 API 字段和状态枚举；后端契约修复完成后必须检查 TypeScript 类型、测试和生产构建，避免只修 Python 测试替身。

## 回滚

若核心契约无法在本任务内稳定收敛，回到 `backup/local-main-before-upstream-20260918`，保留上游远程和集成提交供后续拆分处理。
