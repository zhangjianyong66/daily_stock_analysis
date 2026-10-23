# 合并前基线验证

在独立 detached worktree `/tmp/dsa-merge-baseline` 对合并前 HEAD 89b54f0f 使用同一虚拟环境和隔离 ENV_FILE 执行：
`pytest tests/test_pipeline_market_phase_context.py tests/test_llm_channel_config.py tests/test_search_tools_persistence.py -q --tb=short`
结果：29 failed, 79 passed。原始输出 `/tmp/dsa-merge-baseline-tests.log`。

其中 Pipeline 16 项失败来自测试通过 __new__ 构建对象却没有初始化 skill_prompt_state；搜索索引两项失败来自断言遗漏现有 call_source=agent；渠道 11 项失败来自 Responses 解析未接入。以上均为合并前缺陷，不能当作新增回归；本次涉及渠道新旧协议整合，渠道缺陷在本次修复范围，另外两类不改业务实现以迎合过期测试。

上游新增 fxmacrodata-public-client 已按 requirements.txt 固定 wheel/hash 安装到本地 .venv，首次 Agent 大批失败由缺少依赖造成，需重跑。
