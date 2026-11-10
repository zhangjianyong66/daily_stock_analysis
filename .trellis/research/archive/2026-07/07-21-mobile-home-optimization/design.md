# 技术设计：移动端首页 UI 与交互优化

## 1. 边界与组件职责

- `HomePage.tsx` 继续作为首页状态编排入口，新增移动端展示状态（更多操作是否打开、移动报告操作是否展开）并复用现有回调。
- 首页头部在 `md` 以下采用移动专用布局：搜索框和主分析按钮为主操作；策略/通知/批量/市场复盘移动到 `Drawer` 或底部菜单。`md` 以上保留现有 DOM 结构和 class 分支。
- 现有 `sidebarContent` 在移动端改为横向滚动的个股条/紧凑列表容器，桌面仍使用 `StockBar` 侧栏；不得复制数据请求逻辑。
- 报告操作区在移动端改为 `position: sticky` 的底部操作容器，使用安全区 padding；桌面继续使用现有顶部按钮组。
- 需要时为移动操作抽屉增加小型局部组件，优先放在 `pages` 或 `components/home`，不新增平行 API 层。

## 2. 数据流与兼容性

- 继续消费 `useHomeDashboardState`、`useWatchlist`、`analysisSkills`、`notify` 和现有分析/复盘回调。
- 不改变 `StockBarItem`、`ReportSummary`、分析任务和报告 API 契约；仅改变同一数据在窄屏的呈现和触达路径。
- 抽屉关闭、路由切换和报告切换时清理移动局部状态，避免滚动锁定或底部操作栏残留。
- 所有新按钮继续使用 `useUiLanguage` 文案键，并提供 `aria-label`、`aria-expanded`、`aria-controls`。

## 3. 视觉与响应式策略

- 沿用现有 design token、`home-*` 样式、浅色/深色主题，不引入新主色或渐变背景。
- 以 CSS 响应式断点控制展示，不通过 JS 读取 viewport 决定业务分支；使用 `md` 作为桌面布局切换点。
- 移动底部操作栏使用不超过一层的固定/粘性容器，内容区增加等高底部 padding，适配 `env(safe-area-inset-bottom)`。
- 横向个股条使用稳定宽度、`overflow-x-auto`、`snap` 和 44px 触控高度；文本截断不能撑破布局。

## 4. 风险、回滚与验证

- 主要风险是移动抽屉与全局导航/首页历史抽屉同时存在、底部操作栏遮挡滚动内容、桌面 class 分支回归。
- 保持改动集中于 Web 首页、报告展示和必要样式；回滚时可整体撤销新增移动分支和 CSS，不涉及数据迁移。
- 通过 HomePage、StockBar、ReportSummary 现有测试补充移动行为断言，并运行 Web lint/build 与目标 Vitest。
