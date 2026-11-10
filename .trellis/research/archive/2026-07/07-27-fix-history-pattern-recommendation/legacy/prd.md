# 修复历史报告缺少策略推荐

## Goal

让用户从历史记录打开最新个股分析报告时，能够看到分析当时已经保存的“日线形态与后续策略”推荐，避免推荐数据已生成但页面不显示。

## Background

- 最新历史记录已在 `raw_result.pattern_report` 中保存形态与推荐快照，例如报告 `1165 / 518880` 保存了“箱体震荡”形态和“箱体震荡”推荐策略。
- 实时/任务完成报告会把 `pattern_report` 放入 `ReportDetails`，但历史详情接口在 `api/v1/endpoints/history.py:581` 组装 `ReportDetails` 时遗漏该字段。
- Web 在 `apps/dsa-web/src/components/report/ReportSummary.tsx:77` 只从 `details.patternReport` 渲染推荐区域，因此历史详情接口遗漏后整个区域不会显示。

## Requirements

- 历史报告详情接口必须从该报告持久化的 `raw_result.pattern_report` 读取并返回形态推荐快照。
- 只透传分析当时保存的快照，不使用当前行情、当前策略目录或当前配置重新计算历史推荐。
- 缺少 `pattern_report` 的旧报告继续保持字段为空，前端不展示推荐区域，不制造历史推荐。
- 保持实时报告、Markdown、通知、推荐算法和现有 Web 布局不变。
- 增加历史详情接口回归测试，覆盖有快照和旧报告无快照两种情况。

## Acceptance Criteria

- [x] 打开含 `raw_result.pattern_report` 的历史报告时，接口响应包含 `details.pattern_report`，Web 能渲染形态摘要、匹配策略和推荐理由。
- [x] 返回内容与该历史记录保存的快照一致，不按当前配置重新生成。
- [x] 旧报告没有快照时仍正常打开，且不会出现伪造的推荐内容。
- [x] 受影响的 Python 文件通过语法检查，历史详情接口和形态推荐相关定向测试通过。

## Out Of Scope

- 不调整形态识别和策略推荐映射。
- 不修改“本次实际执行策略”标签及默认策略解析。
- 不重新生成已有历史报告，也不修改数据库结构。
- 不改变报告页面现有模块顺序和视觉设计。

## Technical Notes

- 这是单个历史 API 组装遗漏，按轻量任务执行，保留 PRD 单文件规划。
- 修复应复用实时报告已有的 `pattern_report=raw_dict.get("pattern_report")` 透传方式，并保持缺失值为 `None`。
