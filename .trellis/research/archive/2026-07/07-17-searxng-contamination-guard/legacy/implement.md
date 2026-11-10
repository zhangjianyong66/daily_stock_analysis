# 实施计划：停用私有 SearXNG 与 Anspire 双查询

## 1. 启动前审核

- [x] 用户确认实际 `.env` / 现有设置管理入口为 Anspire Key 配置真源；不在任务文档、日志或提交中保存真实 Key。
- [x] 运行 `trellis-before-dev`，读取 backend、配置、搜索审计、错误处理、Docker 和文档规范。
- [x] 复核当前脏工作区，逐文件保留与本任务无关的用户改动。

## 2. 停用 SearXNG

- [x] 修改实际 `.env`：删除私有路由/URL/secret/proxy/timeout/deadline/预算值，关闭公共实例；输出只显示配置状态，不显示密钥。
- [x] 删除 `scripts/docker-up.sh` 的 `read_env_value`、`configure_optional_services`、profile 参数和自动启动说明；补脚本回归与 `bash -n`。
- [x] 删除 Compose 私有服务、`docker/searxng/`、`searxng_first_cn` 专用配置、预算服务/测试和文档。
- [x] 保留通用 SearXNG Provider，逐项验证配置注册、设置页、Actions 和搜索用量页面没有悬空引用；实际部署保持关闭。

## 3. Anspire 合并查询

- [x] 抽取市场对应的逻辑维度定义，保持现有顺序和 `max_searches` 截取语义。
- [x] 增加 ETF profile：行业/主题、跨境、商品、宽基、策略、债券和保守通用类型；优先复用现有标准名称/别名/基金元数据。
- [x] profile 规则不依赖当前 `STOCK_LIST`；新增测试标的验证无需新增代码分支即可分类，标的特例集中存放在受控元数据/别名入口。
- [x] 构造 ETF 产品简称与底层主题别名，去除基金管理人后缀但保留代码和全称用于直接相关性验证。
- [x] 建立 fail-closed 的 ETF → 底层身份映射；映射缺失或歧义时禁用 `underlying_driver`，不得根据搜索结果反推 ETF 类型。
- [x] 增加 `fresh_events` / `analysis` 查询组构造器，组内只包含已启用维度关键词。
- [x] ETF 短线模式使用固定 3 天/30 天查询与本地日期准入，不复用现有 180 天分析窗口。
- [x] 综合搜索检测到 Anspire 可用时按组调用，最多两次；单查询搜索接口保持原行为。
- [x] Anspire 组失败后不自动 fallback；未配置 Anspire 时保留其他非 SearXNG Provider 的 legacy 兼容路径，并验证不会恢复 SearXNG。
- [x] 为物理请求审计补充分组和逻辑维度上下文，确认真实 HTTP 请求数可准确统计。
- [x] 取消综合搜索逐维度 `sleep(0.5)`，只在确有供应商限速要求时保留组间最小延迟。
- [x] 增加进程内分组缓存：事件 15 分钟、分析 6 小时；缓存键包含 profile/模板版本/窗口/维度，读取返回不可变副本。

## 4. 分流与准入

- [x] 实现确定性的 ETF 结果分类器，覆盖产品公告、份额/规模、风险事件、底层催化、底层展望、核心成分影响和结构/估值。
- [x] 为 `underlying_driver` 建立独立证据和提示词标签，禁止其进入产品公告、份额、折溢价和跟踪事实字段。
- [x] 为旧维度键增加明确兼容映射，报告标签使用 ETF 交易语义，禁止把普通涨跌归为风险、份额变化归为业绩、行情页归为公告。
- [x] 实现 ETF 短线排序：官方产品风险覆盖 > 底层驱动 > 核心成分影响 > 份额/规模/资金流确认 > 普通行情复述。
- [x] 修复全零相关度仍保留候选的问题；未直接命中标的的结果全部拒绝。
- [x] 新鲜组与分析组都要求可解析日期并按各自窗口过滤。
- [x] 分流后执行 URL 去重、排序和每维度条数限制；未命中任何维度的结果丢弃。
- [x] 搜索结果不得生成实时折溢价、盘中价格、成交额或换手率；这些字段只接受结构化行情来源。
- [x] 确认缓存只保存最终可信结果；如不复用现有缓存，则不为本任务新增复杂持久化缓存。
- [x] 失败、空结果、`no_trusted_data` 和原始 Provider 响应不缓存；缓存命中不新增物理请求审计行。

## 5. 空结果与消费路径

- [x] `format_intel_report` 在无可信结果时不生成标题/“未找到”空壳文本。
- [x] Pipeline 仅在存在可信结果时设置 `news_context` 和 `search_performed`，并仅持久化可信维度。
- [x] Agent 工具无可信结果时返回结构化诊断，不返回可被当作事实的报告文本，也不写 `news_intel`。
- [x] 检查 AlphaSift、market review 和其他复用 `SearchService` 的入口，保证同一可信契约。

## 6. 历史污染隔离

- [x] 为 `news_intel` 增加 `quarantined_at`、`quarantine_reason`、`quarantine_batch` 并实现幂等 SQLite 迁移。
- [x] 编写一次性、可重复执行的隔离操作，按 Provider 和上线时间边界锁定最终 206 条 SearXNG 记录。
- [x] 所有 `news_intel` 查询和历史消费路径默认排除隔离记录。
- [x] 增加 dry-run、执行后数量校验和按批次回滚命令；永久保留 `search_api_calls`。

## 7. 配置、文档与项目知识

- [x] 更新 `.env.example`、`src/config.py`、`src/core/config_registry.py` 和结构化配置测试。
- [x] 更新 `docs/full-guide.md` / `docs/full-guide_EN.md`、`docs/DEPLOY.md` / `docs/DEPLOY_EN.md`、`docs/settings-help.md`。
- [x] 更新 `docs/CHANGELOG.md` 的 `[Unreleased]` 扁平条目。
- [x] 更新 `AGENTS.md` 和 `.trellis/spec/backend/runtime-deployment.md` / 搜索审计规范，删除私有 SearXNG 自动启动约定，记录 Anspire 最多两次综合搜索契约。

## 8. 定向测试

- [x] Anspire Provider：单次 top_k、日期解析、错误/额度耗尽、审计逐物理请求计数。
- [x] 综合搜索：Pipeline 5 维度最多 2 次、Agent 6 维度最多 2 次、单组维度只调用 1 次。
- [x] 缓存：15 分钟内重复调用为 0 次；15 分钟后、6 小时内最多 1 次；模板/profile/窗口变化失效；失败与空结果不命中缓存。
- [x] ETF profile：当前 18 个 ETF 正确覆盖行业/主题、跨境和商品；宽基/策略/债券/未知 ETF 使用确定性或保守模板。
- [x] 通用性：新增非当前清单 ETF 可由元数据/名称规则分类；无歧义证据不足时降为 `generic_etf`，不开放底层驱动。
- [x] 分流反例：普通涨跌不是风险、份额变化不是业绩、行情页不是公告；零相关、错题、垃圾页、未知日期、过期日期、无法分类全部拒绝。
- [x] 正例：行业主题政策/景气、跨境指数/汇率/QDII、黄金价格/美元/实际利率、产品公告/申赎/份额规模正确分流且不重复。
- [x] 底层映射：不含 ETF 代码的真实底层驱动可进入独立通道；未知/歧义 ETF、泛宏观内容和错误主题全部拒绝。
- [x] 排序正反例：底层驱动压过普通资金流；官方溢价/暂停申赎风险压过看多催化；只有份额净流入时不得生成方向性事实。
- [x] 时间边界：3 天事件、30 天分析的临界值通过；31 天分析、4 天事件、未知日期全部拒绝。
- [x] 空结果：`news_context=None`、无空壳文本、无 `news_intel` 写入。
- [x] 隔离：最终 206 条目标记录不可见、其他 Provider 不受影响、审计保留、回滚恢复可见。
- [x] 脚本/Compose：不再隐式启动 SearXNG，目标服务启停不变。

建议定向命令：

```bash
python3 -m pytest \
  tests/test_anspire_search.py \
  tests/test_search_news_freshness.py \
  tests/test_search_tools_persistence.py \
  tests/test_search_usage_storage.py \
  tests/test_search_usage_service.py \
  tests/test_analysis_api_contract.py -q
bash -n scripts/docker-up.sh
docker compose -f docker/docker-compose.yml config --quiet
```

## 9. 最终门禁

- [x] 对变更 Python 文件执行 `python -m py_compile`。
- [x] 使用隔离部署配置执行 `./scripts/ci_gate.sh`。
- [x] 如设置页/配置 registry 影响 Web，执行受影响 Vitest、`npm run lint` 和 `npm run build`。
- [x] 执行 `python scripts/check_ai_assets.py`。
- [x] 执行 `git diff --check`，确认无密钥、无误删用户改动。
- [x] 使用 `trellis-check` 完成跨层、测试和文档一致性复核。

## 10. 在线验收

- [x] 用户已确认使用公开股票样本完成在线验证，每只最多两次物理请求。
- [x] 用户已确认真实 Anspire 响应的召回和分流验证通过；无法确认的结果保持为空，不放宽准入。
- [x] 在线响应只进入脱敏审计，不进入普通日志或任务文档。

## 11. 启动实施门

- [x] 用户审核并批准 `prd.md`、`design.md`、`implement.md`。
- [x] 收到明确“开始实现”后运行 `python3 ./.trellis/scripts/task.py start 07-17-searxng-contamination-guard`。
- [x] 未经明确确认，不执行 git commit、tag、push 或创建 PR。
