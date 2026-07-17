# 实施计划：压缩大盘复盘与分析搜索请求

## 1. 启动前审核

- [x] 用户审核并批准 `prd.md`、`design.md`、`implement.md`。
- [x] 运行 `trellis-before-dev`，读取 backend、搜索审计、质量和每日大盘上下文规范。
- [x] 复核工作区状态，保留与本任务无关的用户改动。
- [x] 运行 `task.py start` 进入 `in_progress`；未启动前不修改产品代码。

## 2. 大盘复盘单查询

- [x] 修改 `MarketAnalyzer.search_market_news()`：按 profile 顺序合并并去重三个主题，只调用一次 `search_stock_news()`。
- [x] 单次逻辑结果上限设为 6，保留 `call_source=market_review`、现有过滤和空结果降级。
- [x] 增加各市场 profile 测试，至少断言 A 股综合查询包含原三个意图、只调用一次、`max_results=6`。
- [x] 增加失败/空响应测试，确认不产生隐式第二次请求且大盘报告链路仍可继续。

## 3. 共享可信缓存与 singleflight

- [x] 将 ETF 分组缓存泛化为类级进程共享缓存，键区分 ETF/普通股票、模板版本、身份、窗口、维度和语言。
- [x] 增加共享 inflight owner/waiter 协议；owner 在所有返回和异常路径释放 event。
- [x] 保持只缓存可信非空结果，读取返回深拷贝，失败/空结果不写缓存。
- [x] 增加测试 reset helper 和自动 fixture，防止测试顺序污染。
- [x] 回归同一实例缓存：15 分钟内 0 次、近期过期/分析有效时 1 次、两组过期时 2 次。
- [x] 新增跨两个 `SearchService` 实例缓存复用测试，锁定今天真实暴露的生命周期问题。
- [x] 新增并发冷启动测试，断言同键每组只有一个 owner 物理请求；owner 失败时等待者不形成请求风暴。

## 4. 非 ETF Anspire 两组搜索

- [x] 新建 `src/services/stock_search_intelligence.py`，定义模板版本、Pipeline 五维分组、CN/foreign 查询构造和确定性分类。
- [x] 保留 `max_searches` 逻辑维度上限；只为含启用维度的组发请求。
- [x] 在 `SearchService` 增加仅限 `call_source=analysis` 的普通股票 Anspire 分组编排，复用共享缓存、审计、timeout 和禁用 retry 规则；Agent 保持 legacy 路径。
- [x] 近期组使用有效新闻窗口并拒绝未知/过期日期；分析组使用现有 180 天窗口并保留未知日期。
- [x] 每条结果只进入一个最具体维度，每维最多 3 条；维度键与 `SearchResponse` 结构保持兼容。
- [x] Anspire 成功但无可信数据时不扇出逐维请求；物理失败时仅对失败组调用既有非 Anspire Provider 降级，逐次审计；未配置 Anspire 和 Agent 的 legacy 路径保持不变。

## 5. 定向测试

- [x] Pipeline 五维：Anspire 冷启动最多两次，审计维度为 `fresh_events` / `analysis`，逻辑结果仍覆盖五个既有维度正例。
- [x] Agent 六维：调用次数、维度顺序和 `industry` 时间语义保持当前行为。
- [x] 单组调用：`max_searches=1` 只请求近期组；只启用分析维度的内部用例只请求分析组。
- [x] Pipeline 分类正例：最新事件、公告、风险、机构分析和业绩分别进入正确维度。
- [x] 分类反例：错股票、泛宏观、垃圾页、无 URL、近期未知日期、超窗日期拒绝；同 URL 不跨维度重复。
- [x] 分析日期兼容：180 天内已知日期和未知日期保留，181 天已知日期拒绝。
- [x] 失败语义：一组失败不污染另一组、不缓存，只对失败组执行 legacy Provider 降级；成功空结果不 fallback。
- [x] 未配置 Anspire：现有 Bocha/Tavily/Brave/SerpAPI/MiniMax/SearXNG legacy 测试行为不变。
- [x] 审计：缓存与 singleflight waiter 不新增 `search_api_calls`；owner、备用 Key 和真实 transport 行为仍逐物理请求计数。

建议定向命令：

```bash
python3 -m pytest \
  tests/test_market_strategy.py \
  tests/test_market_review.py \
  tests/test_etf_search_intelligence.py \
  tests/test_stock_search_intelligence.py \
  tests/test_search_news_freshness.py \
  tests/test_search_service_concurrency.py \
  tests/test_search_usage_storage.py \
  tests/test_search_usage_service.py -q
```

## 6. 文档与项目知识

- [x] 更新 `AGENTS.md` 的大盘复盘、ETF 缓存和非 ETF Anspire 请求上限约定。
- [x] 更新 `.trellis/spec/backend/search-usage-audit.md` 的计数矩阵和缓存/singleflight 契约。
- [x] 更新 `docs/full-guide.md` / `docs/full-guide_EN.md`，同步中英文搜索请求说明。
- [x] 在 `docs/CHANGELOG.md` 的 `[Unreleased]` 增加扁平 `[改进]` 条目。
- [x] 不更新 README；不新增配置项、数据库迁移或 Web 截图。

## 7. 验证门禁

- [x] 对变更 Python 文件执行 `python -m py_compile`。
- [x] 执行上述定向测试，失败后先重跑失败用例和直接相关用例。
- [x] 使用隔离部署配置执行 `./scripts/ci_gate.sh`，避免本机真实 `.env` 干扰离线门禁。
- [x] 若修改 `AGENTS.md` 或 Trellis spec，执行 `python scripts/check_ai_assets.py`。
- [x] 执行 `git diff --check` 并检查 diff 中无密钥、原始请求/响应和无关改动。
- [x] 运行 `trellis-check` 完成跨层、缓存并发和文档一致性复核。

## 8. 在线验收与成本证据

- [ ] 在线 Anspire smoke 需要用户另行确认；未授权时只执行离线 mock/审计测试，不消耗真实额度。
- [ ] 如获授权，只使用公开股票样本，记录脱敏后的物理请求数、逻辑维度覆盖和缓存命中，不把原始响应写入任务文档或普通日志。
- [x] 对照目标矩阵确认：大盘 1 次、ETF 冷启动 2 次/重复 0 或 1 次、非 ETF 健康冷启动 2 次；故障 fallback 单独计数并说明。

## 9. 回滚点

- [ ] 大盘合并异常时单独恢复 `news_queries` 循环。
- [ ] 普通股票分组召回不足时移除非 ETF Anspire 分组路由，恢复 legacy 逐维路径。
- [ ] 共享缓存出现隔离问题时恢复实例级缓存；无数据库或配置回滚要求。
- [ ] 未经用户明确确认，不执行 git commit、tag、push 或创建 PR。
