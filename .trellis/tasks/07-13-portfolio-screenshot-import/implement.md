# 持仓与成交截图识别导入 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` in inline mode and execute only the user-approved milestone. Track every step with the checkboxes in the linked milestone file.

**Goal:** 在现有持仓账本上交付空账户持仓截图初始化、已有账户实际成交截图增量导入，以及独立 Vision 模型复用和可空成交时间。

**Architecture:** 共享 Vision client 只负责图片与模型调用；`PortfolioScreenshotImportService` 负责两类图片的领域解析、冲突和提交。提交端在 Repository 单事务中重新校验并原子写入，Web 只提交用户确认后的规范化字段。

**Tech Stack:** Python 3.10+/FastAPI/Pydantic/SQLAlchemy/SQLite/LiteLLM/pytest；React/TypeScript/Vite/Vitest/Tailwind。

---

## Milestones

- [ ] [Milestone 1: 共享 Vision 与成交时间基础](./milestone-1-vision-trade-time.md)
- [ ] [Milestone 2: 截图解析与原子导入后端](./milestone-2-screenshot-import-backend.md)
- [ ] [Milestone 3: Web 工作流、文档与集成验收](./milestone-3-web-docs-integration.md)

## Execution Order

1. Milestone 1 先建立共享 Vision、数据库兼容迁移和 `trade_time` 全链路契约。
2. Milestone 2 在基础契约上实现持仓/成交解析、去重、完整账本重放和四个 API。
3. Milestone 3 接入可编辑工作流，完成文档、截图证据和全量质量门禁。

默认每次只执行用户明确指定的 milestone，不连续扩展到下一 milestone。每个 milestone 完成后先运行其局部门禁并报告，再请求是否继续。

## Global Quality Gates

- [ ] 所有代码步骤遵循 TDD：先写失败测试、确认失败、最小实现、确认通过。
- [ ] 不提交真实资产截图、模型 raw response、base64 或 API Key。
- [ ] API 使用统一错误 envelope；新增字段同步 Python schema、TypeScript 类型和文档。
- [ ] `python -m pytest -m "not network"` 通过。
- [ ] `./scripts/ci_gate.sh` 通过。
- [ ] `cd apps/dsa-web && npm run test -- src/pages/__tests__/PortfolioPage.test.tsx src/components/portfolio/__tests__/PortfolioImageImportDialog.test.tsx` 通过。
- [ ] `cd apps/dsa-web && npm run lint && npm run build` 通过。
- [ ] 使用 Playwright 或浏览器截图验证桌面/移动端弹窗；证据放 PR/外部附件，不写入仓库。
- [ ] 未经用户明确确认不执行 `git commit`、`git push` 或在线 Vision 调用。

## Rollback Points

- Milestone 1：保留 nullable `trade_time` 不影响旧逻辑；共享 Vision 可恢复为 extractor 内部调用。
- Milestone 2：移除新 API/service 即停止图片导入，已提交交易仍是标准账本数据。
- Milestone 3：移除 Web 入口不会影响 API、CSV 或手工交易。
