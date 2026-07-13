# Milestone 3: Web 工作流、文档与集成验收

前置：Milestone 2 API 已通过。目标：交付移动端友好的校对流程，展示成交时间，补齐文档和全量验证。

## Task 1: TypeScript 契约与 API Client

**Files:**
- Modify: `apps/dsa-web/src/types/portfolio.ts`
- Modify: `apps/dsa-web/src/api/portfolio.ts`
- Create: `apps/dsa-web/src/api/__tests__/portfolio.test.ts`

- [x] 写失败测试：multipart 重复 `files` 字段、position/trade parse 路径、JSON commit、snake_case 到 camelCase、可空 `tradeTime`。
- [x] 运行 `cd apps/dsa-web && npm run test -- src/api/__tests__/portfolio.test.ts`，预期函数不存在而失败。
- [x] 增加明确类型和方法：

```ts
parsePositionImages(accountId: number, snapshotDate: string, files: File[]): Promise<PositionImageParseResponse>
commitPositionImages(request: PositionImageCommitRequest): Promise<ImageImportCommitResponse>
parseTradeImages(accountId: number, defaultTradeDate: string, files: File[]): Promise<TradeImageParseResponse>
commitTradeImages(request: TradeImageCommitRequest): Promise<ImageImportCommitResponse>
```

- [x] 更新交易 DTO 的 `tradeTime?: string | null`，保持旧响应兼容。
- [x] 运行目标测试和 `cd apps/dsa-web && npm run lint`，预期通过。
- [ ] 经用户明确确认后提交：`feat(web): 增加截图导入前端契约`。

## Task 2: 可编辑图片导入工作流

**Files:**
- Create: `apps/dsa-web/src/components/portfolio/PortfolioImageImportDialog.tsx`
- Create: `apps/dsa-web/src/components/portfolio/__tests__/PortfolioImageImportDialog.test.tsx`
- Reuse: `apps/dsa-web/src/components/common/Drawer.tsx`、现有 `Select`、`InlineAlert` 和 Lucide icons。

- [x] 写失败组件测试：模式切换、账户/日期、最多 5 图、逐图失败、position/trade 表格、字段编辑、删除、冲突合并/保留、错误时禁用提交。
- [x] 运行目标 Vitest，预期组件不存在而失败。
- [x] 实现状态机 `select -> parsing -> review -> committing -> completed`；日期默认本地当天且禁止未来日期。
- [x] 桌面使用稳定列宽的紧凑表格；移动端使用逐行编辑布局，按钮使用图标和 tooltip，不创建嵌套卡片。
- [x] 明确展示：资金不导入、费用默认 0、缺成交编号为 best-effort、失败图片必须重试/移除。
- [x] 运行目标测试，预期通过。
- [ ] 经用户明确确认后提交：`feat(web): 增加持仓图片导入校对流程`。

## Task 3: 持仓页接入与成交时间展示

**Files:**
- Modify: `apps/dsa-web/src/pages/PortfolioPage.tsx`
- Modify: `apps/dsa-web/src/pages/__tests__/PortfolioPage.test.tsx`
- Modify: `apps/dsa-web/src/utils/portfolioFormat.ts`
- Modify: `apps/dsa-web/src/utils/__tests__/portfolioFormat.test.ts`

- [x] 写失败测试：“图片导入”入口只对具体账户可写；成功后刷新 snapshot/risk/trades；CSV 功能仍存在；交易列表显示 `日期 时间`，null time 只显示日期。
- [x] 运行 `cd apps/dsa-web && npm run test -- src/pages/__tests__/PortfolioPage.test.tsx src/utils/__tests__/portfolioFormat.test.ts`，预期失败。
- [x] 接入 dialog；完成回调复用现有 refresh 方法，不复制 API 刷新逻辑。
- [x] 增加 `formatTradeDateTime(tradeDate, tradeTime)` 并用于交易列表；保证移动端文本换行、不溢出。
- [x] 运行相关 Vitest、`npm run lint` 和 `npm run build`，预期通过。
- [ ] 经用户明确确认后提交：`feat(web): 接入持仓与成交截图导入`。

## Task 4: 文档、可视证据与全量门禁

**Files:**
- Modify: `.env.example`
- Modify: `docs/full-guide.md`
- Modify: `docs/LLM_CONFIG_GUIDE.md`（仅补充现有 Vision 用途，不新增变量）
- Modify: `docs/CHANGELOG.md`

- [x] 更新文档：两种模式、`cn/CNY` 范围、日期/时间、费用默认、去重边界、隐私、不导入资金、四个 API 和 `VISION_MODEL` 配置入口。
- [x] 在 `[Unreleased]` 添加扁平条目，不新增类目标题；不更新 README，除非最终 diff 证明首页级能力必须同步。
- [x] 运行后端目标测试、`python -m pytest -m "not network"`、`./scripts/ci_gate.sh`。
- [x] 运行 `cd apps/dsa-web && npm run test -- src/components/portfolio/__tests__/PortfolioImageImportDialog.test.tsx src/pages/__tests__/PortfolioPage.test.tsx && npm run lint && npm run build`。
- [x] 启动 Web 服务，使用桌面和移动视口验证：文件列表、长表格、冲突操作、错误提示、完成状态无重叠；截图放 PR 描述或外部附件，不加入仓库。
- [x] 检查 `git diff --check`、`git status --short` 和敏感文件；在线 Vision 未运行时记录原因和剩余风险。
- [x] 完成 PRD AC1-AC11 对照检查；更新三个 milestone 与主计划 checkbox。
- [ ] 经用户明确确认后提交：`docs(portfolio): 补充截图导入说明与验收证据`。

## Verification Notes

- Web 最终目标回归 49 passed；`npm run lint` 与 `npm run build` 均以 exit 0 通过。
- 后端目标回归覆盖 Vision、旧图片提取、截图 service、Portfolio Service/API、Storage 和兼容契约，共 168 项；变更文件关键 flake8 为 0，deterministic code/yfinance 检查通过。
- 2026-07-14 最终离线全量结果：4383 passed、4 deselected、45 warnings、413 subtests passed；`./scripts/ci_gate.sh` 的 syntax、flake8、deterministic 和 offline-tests 全部通过。
- 全量顺序测试发现 intelligence 请求复用了会被 Requests 原地扩展的代理字典；改为逐请求复制并增加回归测试后，原始顺序触发用例和全量套件均通过。
- Playwright 使用合成 API/图片数据完成 1440x1000 和 390x844 验收：document/body 宽度均等于视口，dialog 宽度分别为 1152/390，实际可见按钮重叠 0，console error 0。截图位于 `/tmp`，未加入仓库。
- 未执行在线 Vision 调用，避免产生费用和上传真实资产图片；剩余风险是未使用真实券商截图验证模型识别质量。
- 未执行 `git commit`、`git push`。
