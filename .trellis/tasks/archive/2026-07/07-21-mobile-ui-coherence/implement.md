# 实施计划：恢复移动端首页原版 UI

## 顺序清单

1. [x] 加载 `trellis-before-dev` 和 Web 质量规范，确认当前工作区与恢复基线。
2. [x] 选择性恢复 `HomePage` 原版结构，移除快速访问带、更多操作底部 Drawer、固定底部图标栏，并加入窄屏换行/尺寸微调。
3. [x] 恢复 `ReportSummary` 连续内容流；保留 `ReportOverview` 的响应式微调。
4. [x] 删除 `MobileStockStrip` 及 `StockBarItem` compact 变体，清理导出和移动专用文案。
5. [x] 精简 `Drawer` 的底部专用接口与样式，保留并测试焦点管理、Escape、焦点恢复和 `dialogId` 关联。
6. [x] 更新 HomePage、ReportSummary、StockBar、Drawer 相关测试与 `docs/CHANGELOG.md`。
7. [x] 运行定向 Vitest、Web lint/build 和 `git diff --check`。
8. [x] 在 320×720、375×812、390×844 和桌面视口检查截图、横向溢出、文字可见性和叠层行为。
9. [x] 执行 `trellis-check`，核对 PRD、实现、测试和可视证据后交付。

## 验证命令

```bash
cd apps/dsa-web
npm run test -- src/pages/__tests__/HomePage.test.tsx src/components/history/__tests__/StockBar.test.tsx src/components/report/__tests__/ReportSummary.test.tsx src/components/common/__tests__/Drawer.test.tsx
npm run lint
npm run build
```

## 审查门禁

- 页面结构应与 `2cd093e^` 的原版一致，任何保留差异必须能归类为尺寸、间距、换行、触控或已确认的 Drawer 可访问性。
- 不得残留快速访问带、移动分析选项 Drawer、报告总折叠或固定底部操作栏。
- 320px 下所有操作按钮保留文字且无页面级横向溢出。
- 用户审核本规划后，才执行 `task.py start` 并进入实现。

## 验证结果

- `npm ci` 完成；本机 Node 22.22.1 符合要求，npm 9.2.0 低于项目声明的 npm 10，安装仅产生 engine 警告。
- 定向 Vitest：3 个测试文件、47 项全部通过。
- Web 门禁：`npm run lint` 与 `npm run build` 通过，`git diff --check` 通过。
- 全量 Vitest：995 项通过、2 项跳过、3 项失败；失败仍为未修改的 `SearchUsagePanel.tsx` 原生 `title`、`AlertRuleForm` 缺少 JP/KR 选项、`StockScreeningPage` 超时文案契约，与上一移动任务记录一致，未出现本任务相关新增失败。
- Playwright 使用系统 Chrome 与确定性 API fixture 检查 320×720、375×812、390×844、1280×900：页面和各容器无横向溢出，报告按钮无重叠且移动端高度为 44px，操作栏为普通文档流，移动专用快捷栏/底部抽屉/总折叠均不存在。
- 临时截图保存在 `/tmp` 仅用于本地验收，未加入仓库。
