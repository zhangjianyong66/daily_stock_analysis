# 修复设计

## 边界

本次包含本机 `.env` 的运行时代理移除和 `src/analyzer.py` 的错误传递修复。Docker、FRP、ECS2、Docker 构建代理和模型渠道配置不变。

## 配置恢复

容器的 HTTP/HTTPS/SOCKS 代理变量均指向 `172.17.0.1:10808`，该端口不可达；模型服务主机经直连可在约 0.09 秒获得 HTTP 301。`main.py` 还会在 `USE_PROXY=true` 时按 `PROXY_HOST` 与 `PROXY_PORT` 重写 HTTP/HTTPS 代理。因此设置 `USE_PROXY=false`，并清空本机 `.env` 中大写与小写 `HTTP_PROXY`、`HTTPS_PROXY`、`ALL_PROXY` 运行时代理变量，应用的所有出站请求均使用直连。保留 `NO_PROXY` 和代理地址字段，便于以后显式恢复代理。重建或重启 `stock-server` 后生效。

## 错误传递

`GeminiAnalyzer._call_litellm()` 的流式分支已对 `_LiteLLMStreamError` 保存 `last_error`，但普通 `Exception` 分支仅记录日志后直接跳过该模型。为该分支赋值同样经过 `_sanitize_litellm_exception_text()` 的 `RuntimeError`；不改变 retry、fallback 或流式传输行为。

## 验证

新增单模型流式普通异常回归，断言最终异常包含失败原因且不会改走非流式请求。运行相关测试文件和 Python 编译检查。部署后确认容器不含 HTTP/HTTPS 代理变量，以容器内、无认证的根路径请求验证直连可达，再在页面提交单个低风险分析任务进行端到端确认。

## 回滚

恢复 `.env` 中原有的大写和小写 HTTP/HTTPS/SOCKS 代理变量并重建容器，即可恢复代理行为；代码改动可独立回退。
