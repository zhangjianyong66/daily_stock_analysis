# 首页个股栏置顶实施计划

## Implementation Checklist

- [x] 新增 `stockBarPins` helper 及单元测试，定义版本化本地存储、代码规范化、容错读取/写入和稳定置顶分组。
- [x] 在 `StockBar` 中接入置顶集合状态，保持“过滤 -> 基础排序 -> 置顶分组”的处理顺序，并确保刷新数据后重新应用。
- [x] 为 `StockBarItemComponent` 增加始终可见的 Lucide 图钉按钮、置顶视觉状态、事件隔离及中英文无障碍文案；排除 `MARKET`。
- [x] 扩充组件测试，覆盖置顶/取消置顶、四种排序的组内规则、过滤、持久化恢复、损坏/不可用存储、`MARKET` 和既有删除交互。
- [x] 更新 `docs/CHANGELOG.md` 的 `[Unreleased]` 扁平条目；不修改 README，也不扩展 API / Schema。
- [x] 检查实际改动是否产生新的项目级运行约定；未发现需要新增到 `AGENTS.md` 的目录、环境或部署约定。

## Validation

```bash
cd apps/dsa-web
npm run test -- src/utils/__tests__/stockBarPins.test.ts src/components/history/__tests__/StockBar.test.tsx
npm run lint
npm run build
```

- 在桌面与移动宽度检查未置顶/置顶状态、长名称、情绪徽标、删除按钮和批量复选框不重叠。
- 验证点击图钉不会打开详情，切换排序或搜索后置顶边界仍正确。
- UI 可视证据仅用于验收或后续 PR 描述，不作为一次性截图文件提交仓库。

## Risk And Rollback Points

- `StockBarItemComponent` 动作区空间紧张：先保持 24px 图标按钮和现有布局，视觉检查不通过时只调整动作区布局，不扩大业务范围。
- 本地存储解析必须 fail-safe：helper 测试通过前不接入组件。
- 置顶排序必须建立在既有排序结果之上，避免复制四种 comparator 或改变并列/缺失值规则。
- 任一集成回归无法收敛时，可独立移除图钉接入与 helper；后端和已有排序存储不受影响。
