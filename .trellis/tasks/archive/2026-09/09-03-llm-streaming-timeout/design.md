# 技术设计

## 边界与数据流

`analyze` -> `_call_litellm` -> generation backend -> `_call_litellm_impl`。分析入口继续请求 stream；`_call_litellm_impl` 对每个 deployment 发起流式请求，由 `_consume_litellm_stream` 聚合为完整文本后交给现有 validator 和解析器。

## 行为调整

- 流式首分片前异常：记录 provider/model 的低敏错误，直接进入下一个 deployment；不对当前 deployment 发起 non-stream retry。
- 流式收到部分文本后中断：当前文本只作为诊断中的 last response，不作为成功结果；进入下一个 deployment，全部失败时沿用既有失败/文本 fallback 行为。
- 非流式调用仅保留给明确不支持流式的路由（例如 Hermes/本地 CLI），不改变其现有协议边界。
- 保留 prompt audit、usage、进度回调、响应 validator 及报告完整性重试。

## 兼容与回滚

不新增环境变量和 API 字段。回滚只需恢复 `_call_litellm_impl` 的异常分支；配置文件和数据库无需迁移。主要风险是某些兼容 endpoint 宣称支持 stream 但实际只支持 non-stream，因此跨 deployment fallback 必须继续可用，并对明确非流式路由保留原路径。
