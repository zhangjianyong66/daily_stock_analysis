# 排查服务截图报错

## Goal

定位 `stock.zhangjianyong.top` 截图中大盘复盘失败的直接原因，并给出安全、可执行的恢复建议。

## Confirmed Facts

- 截图时间为 2026-09-04 08:51；批量配置分析已提交 13 个任务。
- 页面提示“系统没有配置可用的 LLM 模型”，详情为：`All LLM models failed (tried 1 model(s)). Last error: None`。
- 截图访问的服务为 `stock.zhangjianyong.top`，项目部署说明表明该域名经 ECS2 的 FRP 转发至本机 Docker 服务。
- 本机 `stock-server` 容器健康且已运行；该问题不是 Web、FRP 或容器存活故障。
- 容器中存在一个有效的主模型配置，且本次只尝试了该模型一次；并非“没有配置模型”。
- 2026-09-04 08:43--08:50 的容器日志反复记录该模型的流式请求发生 `OpenAIException - Connection error`，LiteLLM 已按配置重试两次后失败；所有批量任务因此失败。
- 前端把包含 `All LLM models failed` 和 `Last error: None` 的后端错误归类为“未配置 LLM”。流式请求失败路径未将底层连接错误保留到最终异常，因而页面文案掩盖了真实原因。

## Requirements

- 恢复容器到模型渠道的可用连接；应用运行环境的所有 HTTP/HTTPS 出站请求统一直连，不再使用代理。
- 修复流式模型调用失败时最终错误丢失为 `Last error: None` 的问题。
- 不输出任何 API Key、令牌或其他密钥。
- 不改变“流式失败后不以非流式方式重试同一模型”的既有策略。
- 运行针对性后端测试；连接恢复后执行一次不含敏感信息的容器内连通性验证。
- 设置 `USE_PROXY=false`，并清空本机运行配置中的大写和小写 HTTP/HTTPS/SOCKS 代理变量；不改模型名称、API Key、Base URL 或应用业务逻辑。

## Acceptance Criteria

- [ ] 给出与截图错误对应的直接原因及证据。
- [ ] 给出按优先级排序的恢复步骤和验证方式。
- [ ] 明确本次未执行的修改及其风险。
- [ ] 容器运行时不再注入 HTTP/HTTPS/SOCKS 代理变量，且直连请求可达模型上游。
- [ ] 流式请求在抛出普通异常后，最终失败消息保留已脱敏的异常类型与原因。
- [ ] 现有流式失败回归和新增错误传递回归测试通过。

## Out of Scope

- 更换模型供应商、模型名称、API Key 或模型渠道协议。
- 修改 ECS2、FRP、Docker 构建代理或无关服务。
- 为该模型增加备用渠道。

## Open Questions

无。模型服务已经通过容器内直连实测可达；无需用户提供密钥或选择供应商。
