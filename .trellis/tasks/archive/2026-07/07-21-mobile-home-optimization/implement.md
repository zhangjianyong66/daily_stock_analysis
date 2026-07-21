# 实施计划：移动端首页 UI 与交互优化

## 顺序清单

1. [x] 读取 `trellis-before-dev` 指南和 Web 相关项目规范，确认现有组件/样式约定。
2. [x] 在 `HomePage` 拆分移动头部主操作与“更多操作”抽屉，保留桌面端原布局和回调。
3. [x] 将移动个股历史/自选入口改为横向滚动紧凑条，处理空态、加载态、选中态和触控尺寸。
4. [x] 将报告摘要操作在移动端改为紧凑摘要 + 底部粘性操作栏，增加安全区和内容底部间距；全文/运行流抽屉保持可用。
5. [x] 统一移动抽屉、遮罩、焦点、返回和状态清理，避免与 `Shell` 全局导航冲突。
6. [x] 补充/调整 HomePage、StockBar、ReportSummary 的移动视口交互测试和可访问性断言。
7. [x] 运行定向 Vitest、`npm run lint`、`npm run build`，并用 Playwright 在 320/375/390 宽度截图检查溢出和遮挡。
8. [x] 执行 `trellis-check` 质量门禁，完成 PRD 收敛、文档/变更记录评估和回滚检查；按用户要求暂不提交。

## 验证命令

```bash
cd apps/dsa-web
npm run test -- src/pages/__tests__/HomePage.test.tsx src/components/history/__tests__/StockBar.test.tsx src/components/report/__tests__/ReportSummary.test.tsx
npm run lint
npm run build
```

## 风险点与回滚点

- 风险点：移动抽屉状态与全局导航状态互相遮挡；报告底部操作栏覆盖最后内容；桌面断点 class 误伤；中英文按钮文本在窄屏溢出。
- 每完成头部、个股条、报告操作栏三个阶段分别运行相关测试；任一阶段回归失败时回滚该阶段的局部组件改动，不触碰 API 和 store。
- 若 Playwright 环境不可用，至少执行 DOM/样式断言和构建，并在交付中明确说明未完成真实截图验证。

## 开始前复核

- [x] PRD 已包含产品目标、验收标准和非目标。
- [x] design.md 已说明数据流、桌面兼容和回滚策略。
- [x] 用户已确认进入实现，任务已通过 `task.py start` 进入 `in_progress`。

## 验证结果

- 定向回归：`HomePage.test.tsx` 与 `Drawer.test.tsx` 共 34 项通过；此前覆盖首页、个股栏和报告摘要的 73 项定向测试通过。
- Web 门禁：`npm run lint`、`npm run build` 通过，`git diff --check` 通过。
- 全量 Web 测试：996 项通过、2 项跳过、3 项失败。失败稳定定位到未修改的 `SearchUsagePanel.tsx` 原生 `title`、`AlertRuleForm` 缺少 JP/KR 选项、`StockScreeningPage` 超时文案契约，未出现本任务相关新增失败。
- Playwright：320×720、375×812、390×844、1280×900 均无页面级横向溢出；移动抽屉可打开、Escape 可关闭并恢复焦点，桌面不显示移动专用控件。
- 环境说明：`npm ci` 已成功；本机 npm 9.2 低于项目声明的 npm 10，安装阶段有 engine 警告，但不影响本次 lint、测试和构建结果。
