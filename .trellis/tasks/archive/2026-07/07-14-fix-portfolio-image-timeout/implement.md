# 图片识别持仓初始化异步任务实施计划

## 1. 后端任务基础设施

- [x] 在 `src/services/` 新增图片任务状态、DTO、异常和线程安全 `PortfolioImageTaskManager`。
- [x] 实现全局唯一槽位、pending/processing/cancel_requested/cancelled/review_required/committing/failed 状态机。
- [x] 使用单 worker 执行器保存异步任务，确保图片串行且不阻塞 FastAPI 事件循环。
- [x] 确保原始图片 bytes 只由运行 closure 临时持有，任务终态后释放引用。
- [x] 为现有 SSE 广播增加受控的外部事件发布入口，发布 `portfolio_image_task_updated` 轻量摘要。
- [x] 增加任务查询、取消、放弃、草稿 revision 更新和 begin/finish/rollback commit 方法。
- [x] 覆盖全局槽位释放条件、迟到结果隔离和服务重启自然丢失语义。

风险/回滚点：任务状态机和锁是最高风险区域；先以独立 manager 测试锁定，再接 API。

## 2. Vision 与截图解析编排

- [x] 将 Vision 单次 timeout 调整为 300 秒、总尝试次数调整为 2。
- [x] 新增瞬时错误分类，只对 timeout/connection 类错误重试；确定性错误和 rate limit 不重试。
- [x] 为 Vision 调用增加可选 attempt callback 和剩余 deadline，保持其他调用方默认兼容。
- [x] 为 `PortfolioScreenshotImportService` 增加文件级进度/取消/deadline 回调，复用现有行解析与合并逻辑。
- [x] 保持上传顺序串行处理；取消或截止后不启动下一张图片。
- [x] 至少一张成功返回草稿；全部失败映射任务 failed。

验证重点：300 秒参数、最多两次、错误分类、五图串行、取消后的迟到结果、60 分钟截止。

## 3. API 与 Schema

- [x] 在 `api/v1/schemas/portfolio.py` 增加异步任务 accepted/status/current/draft/cancel 响应与请求 schema。
- [x] 在 `api/v1/endpoints/portfolio.py` 增加 positions/trades task submit、current、task detail、draft PATCH、cancel、discard 接口。
- [x] 新异步提交先完成账户/日期/文件数量、大小、MIME/魔数校验，再返回 202。
- [x] 定义 409 active-task、draft conflict、state conflict 和 404 task-not-found 错误。
- [x] 扩展 positions/trades commit schema，支持可选 `task_id/expected_revision`。
- [x] 新 Web 流程 commit 前执行 begin_commit；成功清除任务，失败恢复 review_required。
- [x] 旧 commit 在存在异步待处理任务时禁止绕过 revision；无异步任务时保持兼容。
- [x] 保留旧同步 parse 成功响应，标记 deprecated，并通过线程池和共享 manager 执行。

风险/回滚点：API 响应和 commit 兼容；必须保留旧请求未携带新字段的合法路径。

## 4. Web API、类型与 SSE

- [x] 在 `apps/dsa-web/src/types/portfolio.ts` 定义图片任务状态、摘要、草稿和 revision 类型。
- [x] 在 `apps/dsa-web/src/api/portfolio.ts` 增加任务提交/查询/草稿/取消/放弃方法，新提交使用默认短 HTTP 等待即可。
- [x] 扩展共享 `useTaskStream`，监听 `portfolio_image_task_updated`，使用 portfolio 类型边界统一解析。
- [x] 修正 `apps/dsa-web/src/api/error.ts`：客户端 Axios timeout 与服务端上游 timeout 使用不同标题和操作提示。

## 5. PortfolioPage 与导入抽屉

- [x] `PortfolioPage` 首次加载查询 current task，并订阅图片任务 SSE；SSE 仅触发权威 REST 刷新。
- [x] 增加常驻任务横幅，展示账户、模式、真实文件级进度和继续/取消/放弃操作。
- [x] 已存在任务时，“图片导入”入口打开当前任务，不进入新建流程。
- [x] 重构 `PortfolioImageImportDialog` phase/state，使其可由服务端任务快照初始化和刷新。
- [x] pending/processing 期间允许关闭抽屉，任务继续执行；committing 保持关闭保护。
- [x] 移除同 task_id 原位重试失败图片的行为，改为放弃后重新创建任务。
- [x] review_required 使用服务端草稿；字段修改、删除行和冲突处理后约 500ms 防抖 PATCH。
- [x] 展示草稿保存中/已保存/保存失败状态；revision 409 后停止自动保存并提供重新加载。
- [x] commit 携带 task_id/expected_revision；成功后清除任务横幅并刷新对应账户数据。
- [x] 服务重启/旧 task_id 404 时清理本地引用并提示重新选择图片。

## 6. 后端自动化测试

- [x] 新增 manager 单元测试：全局互斥、状态转移、review 永不过期、取消、deadline、迟到结果、草稿 revision、commit 两阶段和清理。
- [x] 更新 `tests/test_vision_extraction_service.py`：timeout=300、两次尝试、瞬时/确定性错误矩阵、deadline callback。
- [x] 更新 `tests/test_portfolio_screenshot_import_service.py`：文件级进度、串行、部分成功、全部失败、取消与截止。
- [x] 更新 `tests/test_portfolio_api.py`：新 API 契约、202、409 existing_task_id、current/detail、draft revision、cancel/discard、commit revision、旧 API兼容。
- [x] 更新/补充 SSE 契约测试，证明图片事件不会进入股票任务事件回调。

目标命令：

```bash
python3 -m pytest tests/test_vision_extraction_service.py tests/test_portfolio_screenshot_import_service.py tests/test_portfolio_api.py tests/test_analysis_api_contract.py -q
```

## 7. Web 自动化测试

- [x] 更新 `apps/dsa-web/src/api/__tests__/portfolio.test.ts`：异步 API、snake/camel 映射、task/revision commit。
- [x] 更新 `PortfolioImageImportDialog.test.tsx`：提交即返回、进度、关闭后继续、恢复 review、草稿保存、revision 冲突、取消、放弃、commit。
- [x] 更新 `PortfolioPage.test.tsx`：启动时恢复、任务横幅、SSE 后 REST 刷新、跨账户恢复、服务重启提示、防重复入口。
- [x] 增加/更新 `useTaskStream` 测试：图片专用事件与自动重连。

目标命令：

```bash
cd apps/dsa-web
npm run test -- src/api/__tests__/portfolio.test.ts src/components/portfolio/__tests__/PortfolioImageImportDialog.test.tsx src/pages/__tests__/PortfolioPage.test.tsx src/hooks/__tests__/useTaskStream.test.tsx
npm run lint
npm run build
```

## 8. 文档与规范

- [x] 更新 `docs/full-guide.md` 与 `docs/full-guide_EN.md`：新异步 API、状态机、SSE、刷新恢复、旧 API deprecated、重启丢失。
- [x] 更新 `.trellis/spec/backend/portfolio-image-import.md` 的可执行契约和测试矩阵。
- [x] 更新 `docs/CHANGELOG.md` `[Unreleased]` 扁平条目。
- [x] 评估并按实际实现更新根 `AGENTS.md` 中可复用的图片任务运行约定。

## 9. 完整质量门禁

- [x] `python -m py_compile` 覆盖所有变更 Python 文件。
- [x] 执行目标后端测试和目标 Web 测试。
- [x] 执行 `./scripts/ci_gate.sh`（本机需以临时空 `ENV_FILE` + `LITELLM_MODE=PRODUCTION` 隔离真实部署配置）。
- [x] 执行 Web `npm run lint` 与 `npm run build`。
- [ ] 手工验证单图和多图：任务提交快速返回、关闭抽屉、刷新恢复、SSE 完成、校对草稿恢复、确认导入。
- [ ] 手工验证取消、全局防重、全部失败、部分失败、服务重启丢失提示。
- [ ] 修改 UI 后准备桌面与 390px 移动视口截图作为 PR 外部证据，不把临时截图提交仓库。

## 10. 实施顺序与回滚点

1. 先实现 manager + Vision/service 测试，不接 Web。
2. 接新 API 和兼容旧 API，完成后端契约测试。
3. 接 Web API/SSE/页面状态，再重构抽屉。
4. 补文档、规范和全量门禁。
5. 若异步前端无法稳定收敛，可回滚 Web 到旧 parse；后端新增 API保持未使用，不影响数据库。

不得在规划审阅前执行 `task.py start`，不得在未完成 manager 状态机测试前修改 Web 为新 API。
