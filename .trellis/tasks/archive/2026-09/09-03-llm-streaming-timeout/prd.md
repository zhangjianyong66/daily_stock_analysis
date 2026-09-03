# 将 LLM 调用改为流式输出以避免中转站非流式超时

## Goal

降低中转站非流式请求在 120 秒响应超时导致批量分析失败的概率。分析请求应优先使用流式传输，以便服务端尽早收到首个响应分片；流式失败时仍允许切换到其他已配置模型，但不应对同一故障模型再次发起可能长时间阻塞的非流式请求。

## Confirmed Facts

- `src/analyzer.py::_call_litellm_impl` 已支持 `stream=True`，并通过 `_consume_litellm_stream` 拼接完整文本、累计 usage 和上报进度。
- `analyze` 已以 `stream=True` 调用，并在返回文本后继续执行 JSON 校验、完整性重试和历史落库。
- 当前流式调用发生 `_LiteLLMStreamError` 后会回退同一模型的非流式调用；日志已出现 `stream unavailable before first chunk, falling back to non-stream`，这会重新触发中转站非流式超时风险。
- 所有模型均失败或 JSON 不可解析时，任务按现有契约失败且不写入 `analysis_history`。

## Requirements

- 保持分析请求默认流式；流式响应仍必须完整拼接后再进行现有 JSON/内容完整性校验。
- 流式请求在首个分片前失败或超时，不得对同一模型自动发起非流式重试；应继续尝试下一个已配置模型。
- 已收到部分分片后中断时，不得把不完整文本当作报告落库；应记录低敏失败原因并按既有模型 fallback 语义处理。
- 保留现有兼容能力：不支持流式的本地/Hermes 路由可继续使用其明确的非流式路径；其他模型的 fallback、审计、usage、进度和 JSON 错误语义不得改变。
- 如新增配置项，必须同步 `.env.example`、LLM 配置文档和 `docs/CHANGELOG.md`；优先不新增配置项。

## Acceptance Criteria

- [ ] 正常兼容中转站的分析请求以 `stream=True` 发出，并能将多个分片拼接为原有完整报告文本。
- [ ] 流式首块超时/空响应时，日志显示切换到下一个模型或最终失败，不再出现同一模型的非流式重试。
- [ ] 流式返回非法 JSON 时仍按现有契约拒绝落库；合法 JSON 仍正常完成任务并写入历史。
- [ ] 现有相关单元测试通过，并新增测试覆盖首块失败、部分输出中断、跨模型 fallback 和非流式兼容路径。
- [ ] 变更文件通过 `python -m py_compile`，不泄露 API Key、完整 prompt 或响应到新增日志。

## Out of Scope

- 不改变模型供应商地址、API Key、模型选择顺序或报告 JSON schema。
- 不把流式分片直接暴露给 Web/桌面端；本次只调整后端 LLM 传输和任务稳定性。
- 不通过提高任务总超时或关闭 JSON 校验来规避问题。

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
