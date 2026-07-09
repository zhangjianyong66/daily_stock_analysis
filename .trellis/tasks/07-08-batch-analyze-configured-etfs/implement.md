# 前端批量分析配置标的实施计划

## 实施步骤

1. 读取前端相关规范
   - 读取 `.trellis/spec/guides/index.md`。
   - 读取与 `apps/dsa-web/` 相关的现有测试、组件和状态管理模式。

2. 增加配置编码整理能力
   - 读取 watchlist 后清理空白编码。
   - 优先复用 `apps/dsa-web/src/utils/stockCode.ts` 的 `includesStockCode` / 等价语义做去重，不能复制规范化规则。
   - 保留用户配置中的代码形态用于提交，避免意外改变 `STOCK_LIST` 表达。

3. 扩展首页状态与交互
   - 在 `HomePage.tsx` 引入 `ConfirmDialog`。
   - 增加批量分析配置按钮，位置在“推送通知”后、“大盘复盘”前。
   - 增加批量准备、确认弹窗、提交中、提示/错误状态。
   - 点击按钮时读取 `systemConfigApi.getWatchlist()`，整理配置编码并打开确认框。
   - 确认后调用 `analysisApi.analyzeAsync({ stockCodes, reportType: "detailed", notify })`。

4. 结果反馈
   - 对 `BatchTaskAcceptedResponse` 展示 accepted / duplicates 摘要。
   - 对 `TaskAccepted` 单项响应保留兼容处理。
   - 对空配置、读取失败、提交失败展示明确提示。

5. 文案与文档
   - 在 `apps/dsa-web/src/i18n/uiText.ts` 增加中英文文案。
   - 在 `docs/CHANGELOG.md` 的 `[Unreleased]` 段新增扁平条目。

6. 测试
   - 更新 `HomePage.test.tsx`。
   - 覆盖成功提交所有配置编码、空配置、部分重复、通知状态传递。
   - 如新增 helper 文件，补充对应单元测试。

## 验证命令

优先执行：

```bash
cd apps/dsa-web && npm run lint && npm run build
```

若测试环境可用，补充执行相关测试：

```bash
cd apps/dsa-web && npm test -- HomePage
```

如实际 package scripts 不支持上述测试命令，改用仓库已有 Vitest 命令并在交付说明记录。

## 风险点

- 首页顶部操作区空间有限，新增按钮需避免移动端挤压和文字溢出。
- 批量提交可能产生大量任务；确认弹窗必须展示数量和代码。
- 任务面板依赖 SSE / refresh 链路，提交成功提示不能替代任务完成状态。

## 回滚点

- 回滚 `HomePage.tsx`、相关 helper、文案和测试即可移除功能。
- 后端和配置没有迁移，回滚不需要数据处理。
