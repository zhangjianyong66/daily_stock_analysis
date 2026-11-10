# 执行计划

1. 调整 `src/analyzer.py` 流式异常分支，移除同模型 non-stream 自动回退，保留跨模型 fallback 和明确非流式路由。
2. 补充/调整 analyzer 流式调用单元测试，覆盖首块失败、部分中断、validator 失败和兼容路径。
3. 运行受影响测试、语法检查，并检查日志文案和文档变更需求。

验证命令：

```bash
python -m py_compile src/analyzer.py
python -m pytest tests/test_llm_response_content.py tests/test_llm_param_recovery.py -q
```

风险点：真实中转站在线行为未在离线测试中覆盖；交付时需说明未执行在线 smoke。
