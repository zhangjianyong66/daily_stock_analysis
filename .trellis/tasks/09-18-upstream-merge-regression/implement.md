# 执行计划

1. [x] 盘点当前合并后的导入错误、失败测试和受影响文件，按模块建立修复清单。
2. [x] 修复后端基础契约：配置、存储模型、指数注册表、任务队列、API Schema 和服务导入。
3. [x] 修复核心分析、搜索、数据源、ETF、Vision、策略与调度链路的兼容问题。
4. [x] 运行后端定向回归；失败用例按根因修复并重跑，不扩大无关重构。
5. [x] 运行 Web lint/build；Desktop 未执行，Docker 仅完成 Compose 静态配置检查。
6. [x] 检查文档、`.env.example`、CHANGELOG、OpenAPI 和实际配置是否一致；本轮未新增配置项。
7. [x] 进行最终 Trellis quality check，记录测试缺口、风险和回滚方式。

## 执行门槛与回滚点

- 启动前必须保留任务目录中的本计划、真实 `implement.jsonl` / `check.jsonl` 和当前备份分支信息。
- 每轮修复先运行失败用例，再扩大到同一契约的直接上下游测试；不得通过删除断言、扩大 skip 或整体选择一侧实现来消除失败。
- 若分析 API、存储或数据源公共契约无法稳定兼容，停止扩大范围，记录根因并使用 `backup/local-main-before-upstream-20260918` 回滚评估。
- 交付前确认 `git diff --check`、冲突标记扫描、未推送状态和回滚命令均有结果记录。

## 主要验证命令

```bash
.venv/bin/python -m py_compile <changed_python_files>
.venv/bin/python -m pytest tests/test_analysis_api_contract.py tests/test_system_config_api.py tests/test_storage.py -q
.venv/bin/python -m pytest tests/test_etf_capital_flow.py tests/test_search_usage_service.py tests/test_portfolio_image_task_manager.py tests/test_auto_strategy_resolution.py -q
cd apps/dsa-web && npm run lint && npm run build
```
