# 首页个股栏置顶技术设计

## Scope

本次只修改 `apps/dsa-web/` 的个股栏展示与浏览器偏好，不改变后端历史接口、数据库、桌面端封装或股票索引。桌面端复用 Web 构建时会自然获得同一浏览器存储行为。

## Existing Flow

1. `HomePage` 将 `/api/v1/history/stocks` 返回的标的与合成的 `MARKET` 项合并。
2. `StockBar` 先按代码/名称过滤，再调用 `sortStockBarItems` 应用用户选择的排序。
3. `StockBarItemComponent` 渲染可点击的历史卡片及删除操作。
4. 排序偏好已通过容错的 `localStorage` helper 保存。

## Storage Contract

- 新增独立版本化键 `dsa.stockBarPins.v1`，值为 JSON 字符串数组；数组顺序没有业务语义。
- 标的身份统一按 `trim().toUpperCase()` 规范化，忽略空字符串与 `MARKET`，并对重复值去重。
- 读取时只接受 JSON 数组中的字符串元素；非法 JSON、非数组或存储读取异常返回空集合。
- 写入时序列化规范化后的代码集合；为稳定测试与可诊断性可按代码排序后写入。
- 写入异常被吞掉，但 React 内存状态仍更新，因此当前页面交互继续有效。
- 不根据当前接口列表裁剪集合，保证暂时离开 90 天窗口的标的再次出现后恢复置顶。

## Components And Data Flow

### Pin helper

新增 `src/utils/stockBarPins.ts`，负责存储访问、代码规范化、读取、写入、命中判断和稳定的置顶优先分组。它不修改已有基础排序语义。

### StockBar

- 组件挂载时从 helper 初始化 `Set<string>`。
- 可见列表处理顺序固定为：搜索过滤 -> `sortStockBarItems` 基础排序 -> 稳定分组为置顶项和未置顶项。
- 稳定分组保留基础排序在两个分组内的相对顺序。
- 切换图钉时基于规范化代码更新新集合并尝试持久化；`MARKET` 始终拒绝进入集合。
- 首页响应式布局会同时挂载桌面侧栏和移动抽屉的 `StockBar` 实例；图钉变更通过同页面自定义事件携带内存集合同步到其他实例，浏览器原生 `storage` 事件负责跨标签页刷新。自定义事件不依赖写入成功，因此存储失败时当前页面和并行实例仍保持交互状态。
- 将 `isPinned` 与 `onTogglePin` 传给真实标的卡片。

### StockBarItem

- 在现有卡片右上角动作区加入 Lucide `Pin` 图标按钮，始终可见。
- 未置顶使用普通轮廓状态，置顶使用主色与填充/强调状态，并通过 `title` 与 `aria-label` 提供“置顶/取消置顶 + 标的名称”。
- 点击时 `stopPropagation()`，避免触发卡片历史详情。
- `MARKET` 不接收置顶回调，因此不渲染图钉；现有删除按钮与情绪/大盘徽标保持兼容。
- 不增加分组标题、提示条或确认弹窗。

## Localization And Documentation

- 在 `uiText.ts` 同步新增中英文置顶、取消置顶文案。
- 在 `docs/CHANGELOG.md` 的 `[Unreleased]` 扁平段增加一条 `[新功能]` 记录；不更新 README。

## Compatibility And Failure Behavior

- 未存在新存储键的用户默认没有置顶项，当前行为除新增图钉外不变。
- 后端返回代码格式变化时按大小写和首尾空白容错，但不尝试推断不同证券代码别名，避免错误合并。
- 本地数据损坏不会阻止列表渲染；保存失败只影响刷新后的恢复，不影响当前页面状态。
- 删除历史记录不删除置顶偏好，因为两者是独立语义。

## Verification Strategy

- helper 单元测试覆盖规范化、去重、非法数据、`MARKET` 排除、存储异常与稳定分组。
- `StockBar` 组件测试覆盖置顶/取消置顶、组内排序、筛选、刷新/重挂载恢复、事件隔离、`MARKET`、中英文无障碍名称及删除兼容。
- 执行 Web 定向测试、lint 和 production build，并在桌面及移动宽度人工检查图标不挤压名称、徽标和删除动作。

## Rollback

回滚时移除 pin helper、组件 props/UI、文案、测试和 changelog 条目即可；遗留的 `dsa.stockBarPins.v1` 不会被旧版本读取，不影响回滚后的运行。
