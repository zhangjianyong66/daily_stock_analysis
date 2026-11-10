# 搜索调用用量记录与余额告警实施计划

## 执行结果（2026-07-16）

- 已完成后端搜索物理请求审计、深度脱敏/截断哈希、三张持久化表、Repository/Service、故障生命周期、24 小时通知冷却和恢复通知。
- 已接入 Anspire、Bocha、MiniMax、Brave、SearXNG、Tavily Session 与 SerpAPI URL transport；Agent、分析、大盘复盘、AlphaSift 和行情增强入口均携带调用来源。
- 已完成 `/api/v1/usage/search/*` 汇总、故障、详情、CSV、单条 JSON API；详情和导出强制要求启用管理员认证且管理员已登录。
- 已完成 Web“LLM 用量 / 搜索调用”双 Tab、时间范围、筛选、分布、分页、故障/审计缺口、详情抽屉、复制/下载和 Shell 全局 60 秒故障提示。
- 已同步 `AGENTS.md`、`.trellis/spec/backend/search-usage-audit.md`、中英文完整指南和 `[Unreleased]` 变更记录。
- 验证通过：后端完整门禁 `4462 passed, 4 deselected`；搜索定向回归 `89 passed, 2 skipped`（后续新增故障冷却/恢复测试后核心测试 `8 passed`）；Web 定向测试 `10 passed, 2 skipped`；Web lint/build；AI 资产检查。
- 未执行真实 Anspire 计费 smoke，避免在余额为 0/额度异常状态下制造额外计费请求。
- UI 截图未写入仓库；创建 PR 时按 `AGENTS.md` 要求将用量页、详情抽屉和全局提示截图放入 PR 描述或附件。

## 1. 数据契约与安全工具

- [ ] 新增 `src/schemas/search_usage.py`，定义审计上下文、物理调用结果和稳定错误类别。
- [ ] 扩展 `src/utils/sanitize.py`：支持 URL 参数、headers、嵌套 JSON、文本值的深度脱敏，以及快照大小/哈希元数据。
- [ ] 增加安全回归测试，覆盖 Authorization、API Key、Cookie、Token、签名、Webhook、嵌套列表和供应商回显凭据。
- [ ] 明确普通日志只输出调用 ID 和安全摘要，不输出完整快照。

## 2. 数据库、Repository 与 Service

- [ ] 在 `src/storage.py` 新增 `search_api_calls`、`search_provider_faults`、`search_audit_gaps` ORM 表和必要索引。
- [ ] 新增 `src/repositories/search_usage_repo.py`，实现同步写入、汇总、breakdown、分页、详情、CSV 流式读取、fault upsert/resolve 和 gap 持久化。
- [ ] 新增 `src/services/search_usage_service.py`，实现日期/筛选归一化、DTO、fault 状态机、供应商总体状态、Key reconciliation 和 audit health。
- [ ] 实现稳定的 Key HMAC/查询 HMAC 本地密钥加载；密钥文件位于数据库持久化目录并避免进入 Git。
- [ ] 增加旧数据库自动建表、分页索引、永久账本汇总、fault 生命周期和 audit gap 测试。

## 3. 物理请求审计接入

- [ ] 新增 `src/services/search_request_audit_service.py`，实现 `audited_request_once` 和 Tavily 可注入 Session。
- [ ] 将 `_get_with_retry` / `_post_with_retry` 的每次 Tenacity attempt 接入审计 transport，确保重试逐次落库。
- [ ] 接入 Anspire、Bocha、MiniMax、Brave、SearXNG；排除文章正文补抓和实例目录刷新。
- [ ] Tavily 使用审计 Session 保留 SDK 行为；SerpAPI 复用 SDK URL/参数构造但由审计 transport 发请求。
- [ ] 在 `SearchService` 各入口建立 business/logical context，覆盖多维搜索、provider fallback、Agent 和行情增强兜底。
- [ ] 确保缓存命中不生成外部调用记录，空结果生成成功调用记录但不生成故障。
- [ ] 增加 Anspire 401 余额不足、三次网络重试、备用 Key、provider fallback、Tavily/SerpAPI 单次请求和 SearXNG 多实例测试。

## 4. 错误分类、故障与通知

- [ ] 实现业务响应语义优先的错误分类器，覆盖 PRD R4 类别。
- [ ] 实现立即故障、10 分钟/3 次瞬时阈值、同 Key 成功恢复和配置移除恢复。
- [ ] 聚合供应商正常/降级/不可用状态。
- [ ] 复用 `NotificationService.send_with_results(route_type="alert")`，实现 24 小时 fault 冷却和一次恢复通知。
- [ ] 通知链路 best-effort，不阻塞搜索；回写安全化通知结果。
- [ ] 增加通知冷却、恢复、无渠道、发送失败和不泄露快照的测试。

## 5. API 与权限

- [ ] 扩展 `api/v1/schemas/usage.py`，增加搜索汇总、breakdown、分页摘要、fault、详情和 audit health schema。
- [ ] 在 `api/v1/endpoints/usage.py` 增加 search dashboard、faults、detail、CSV 和 JSON 端点。
- [ ] 新增可复用的 `require_enabled_admin_session` 依赖；认证未启用返回 403、会话无效返回 401，无桌面例外。
- [ ] CSV 使用 `StreamingResponse`，仅含核账摘要；单条 JSON 包含脱敏快照。
- [ ] 保持现有 LLM usage API 响应兼容。
- [ ] 增加 API 过滤、分页、时区、自定义范围、Content-Disposition、敏感权限和凭据泄漏测试。

## 6. Web 用量分析与全局告警

- [ ] 将 `/usage` 页面升级为 `UsageAnalysisPage` 双 Tab，保留现有 LLM 用量组件与请求竞态保护。
- [ ] 扩展 `apps/dsa-web/src/api/usage.ts` 及共享类型，统一 snake_case → camelCase 转换。
- [ ] 实现 Search Tab：时间范围、筛选、摘要卡、breakdown、分页明细和审计起始/健康状态。
- [ ] 实现详情抽屉、请求/响应 JSON 展示与复制、CSV/JSON blob 下载。
- [ ] 基于 `AuthContext` 禁用未认证敏感操作；服务端仍为最终权限边界。
- [ ] 新增 `SearchProviderFaultBanner` 到 `Shell`，实现启动/焦点/60 秒轮询与 session dismissal。
- [ ] 同步中英文 `uiText`、路由标题和导航说明。
- [ ] 增加 API adapter、页面双 Tab、筛选分页、权限禁用、详情下载、竞态和全局 banner 测试。

## 7. 文档与变更记录

- [ ] 更新 `docs/full-guide.md` 与 `docs/full-guide_EN.md`：新 API、计数口径、明文快照风险、管理员权限、审计起始时间和导出说明。
- [ ] 更新 `docs/CHANGELOG.md` `[Unreleased]`，使用扁平格式。
- [ ] 如新增本地 HMAC 文件约定，更新部署/备份说明并确认路径位于持久化数据目录。
- [ ] PR 描述准备搜索调用 Tab、详情抽屉和全局故障提示截图，不把截图文件提交仓库。

## 8. 验证计划

### 后端定向测试

```bash
python3 -m pytest \
  tests/test_search_usage_storage.py \
  tests/test_search_usage_service.py \
  tests/test_search_usage_api.py \
  tests/test_anspire_search.py \
  tests/test_search_tavily_provider.py \
  tests/test_search_serpapi_provider.py \
  tests/test_search_searxng.py \
  tests/test_search_service_concurrency.py \
  tests/test_notification_diagnostics.py -q
```

### Python 语法与完整门禁

```bash
python3 -m py_compile <changed_python_files>
tmp_env=$(mktemp); trap 'rm -f "$tmp_env"' EXIT; ENV_FILE="$tmp_env" LITELLM_MODE=PRODUCTION PATH="$PWD/.venv/bin:$PATH" ./scripts/ci_gate.sh
```

### Web 定向与完整验证

```bash
cd apps/dsa-web
npm run test -- src/api/__tests__/usage.test.ts src/pages/__tests__/TokenUsagePage.test.tsx src/components/layout/__tests__/SearchProviderFaultBanner.test.tsx
npm run lint
npm run build
```

### 安全验证

- [ ] 使用嵌套测试凭据构造请求/响应，检查数据库、API、CSV、JSON 下载和日志均无原始凭据。
- [ ] 未开启管理员认证、未登录、已登录三种状态分别验证敏感端点 403/401/200。
- [ ] 构造 2 MiB 以上响应，验证截断、大小和 SHA-256，搜索结果仍按原逻辑返回。

### 不执行或独立执行的在线验证

- [ ] 不使用当前余额为 0 的真实 Anspire Key 制造额外计费请求；主要通过确定性 mocked HTTP 响应验证。
- [ ] 如用户后续明确授权并补充可用额度，再单独执行一次 Anspire live smoke，对照本地账本与供应商 Request ID。

## 9. Review Gates

- [ ] 核对每个 provider 的真实网络边界，确认没有只在逻辑返回层记账。
- [ ] 核对 Anspire 余额不足反例、重试三次反例和缓存命中反例。
- [ ] 核对完整出入参只通过强认证详情/导出暴露。
- [ ] 核对 PRD、API schema、Web 类型、文档和测试中的错误枚举及字段名称一致。
- [ ] 核对 UI 统计没有把搜索请求混入 LLM Token 总量。

## 10. 回滚点

- 数据模型完成后：新表为空时可直接回滚代码。
- transport 接入后：若 provider 行为漂移，优先回滚单个 provider 的审计适配，不删除已记录表。
- API/Web 完成后：新端点和 Tab 可独立回滚，现有 LLM `/usage/dashboard` 保持可用。
- 常规回滚不删表，避免丢失核账证据。
