# 修复搜索用量额度耗尽误判

## Goal

让搜索用量账本和全局故障提示只根据真实供应商错误判定余额、认证、权限、限流等故障，避免正常搜索结果正文中的业务词触发虚假告警。

## Background

- `src/services/search_request_audit_service.py:207-225` 当前把完整响应文本和完整 JSON payload 拼接后扫描错误关键词，扫描范围包含 `results`、`organic`、`web.results` 等正常搜索结果。
- 本地 `data/stock_analysis.db` 中已确认 4 条 Anspire 请求同时满足 HTTP 200、结果非空、`success=false`、`error_category=quota_exhausted`；命中词均位于 `results[].content`，响应顶层没有错误 `message`。
- `tests/test_search_usage_storage.py:41-70` 已约束 Anspire HTTP 401 且顶层消息明确免费额度/充值余额为 0 时必须分类为 `quota_exhausted`，该行为必须保留。
- `.trellis/spec/backend/search-usage-audit.md` 要求 HTTP/API 成功且结果为 0 仍算成功，并要求错误正文语义优先于 HTTP 401 状态，以区分额度耗尽和 Key 无效。

## Requirements

- R1：错误关键词只能从供应商错误语义字段或真实失败响应中识别，不得扫描成功响应的搜索结果数据。
- R2：HTTP 2xx 且供应商成功 payload 中，即使结果标题、正文、摘要或 URL 含“余额不足”“额度耗尽”“quota”“unauthorized”“限流”等词，也必须记录为成功。
- R3：HTTP 401 且错误正文明确余额或额度耗尽时，仍优先分类为 `quota_exhausted`；普通 HTTP 401 仍分类为 `auth_invalid`。
- R4：HTTP 2xx 但供应商通过错误码或顶层错误字段表达业务失败时，仍应按明确错误语义分类；无法识别的业务失败保持 `other`。
- R5：不修改数据库 schema、用量 API DTO、Web 展示映射、物理请求计数、脱敏或故障状态机。
- R6：在 `docs/CHANGELOG.md` 的 `[Unreleased]` 扁平列表记录用户可见修复。

## Acceptance Criteria

- [x] AC1：新增回归测试证明 Anspire HTTP 200、`results` 非空且 `results[].content` 含额度词时，审计记录为 `success=true`、`error_category=None`，结果数量正确。
- [x] AC2：测试覆盖正常结果中的其他错误关键词不会触发认证、权限或限流故障。
- [x] AC3：既有 Anspire HTTP 401 额度耗尽测试继续通过，并补充/保留普通 401 分类行为。
- [x] AC4：测试覆盖 HTTP 2xx 业务错误 payload 的额度分类以及未知业务错误分类。
- [x] AC5：搜索用量目标回归与 Python 语法检查通过；最终门禁按后端改动面执行。

## Out Of Scope

- 不批量改写历史 `search_api_calls` 记录；历史审计是当时分类结果，修复只影响后续请求。
- 不手工清除或迁移现有故障表；同一 Key 的后续真实成功请求将沿用既有状态机自动恢复 active fault。
- 不调整搜索 Provider 的请求、重试、fallback、缓存或计费行为。
