# 停用私有 SearXNG 并优化 ETF Anspire 搜索

## Goal

停止当前私有 SearXNG 低成本路由，恢复以 Anspire 为主的搜索链路；针对 1-10 个交易日的 ETF 短线波段，把单只标的综合情报从 5/6 次物理搜索压缩为冷启动最多 2 次、缓存命中时 0-1 次。任何无法证明可信、无法验证日期或无法正确映射到 ETF 产品/底层资产的信息必须 fail-closed，禁止污染 LLM 上下文、缓存、`news_intel` 和报告。

## Background

- 当前实际 `.env` 启用了 `SEARCH_ROUTING_MODE=searxng_first_cn`、私有 `SEARXNG_BASE_URLS` 和 SearXNG secret；`scripts/docker-up.sh:171-190` 会自动启用 profile 并同时启动 `searxng`。
- 用户已确认彻底撤销私有 SearXNG Compose、`docker/searxng/`、`searxng_first_cn` 专用路由/超时/预算和启动联动，仅保留项目原有通用 SearXNG Provider 兼容能力。
- 当前实际 `.env` 与运行中的 `stock-server` 都未配置 `ANSPIRE_API_KEYS`。用户确认实际 `.env` 是 Anspire Key 配置真源，并由用户自行补齐；聊天、日志、任务文档和提交均不得出现真实 Key。
- `src/core/pipeline.py:568-573` 固定以 `max_searches=5` 调用综合情报搜索；Agent 入口 `src/agent/tools/search_tools.py:150-155` 使用 6 个逻辑维度。
- `src/search_service.py:4560-4663` 当前为每个维度构造独立查询；`src/search_service.py:1169-1175` 表明 Anspire 单次最多返回 50 条，但一次请求只有一个时间窗口。
- 当前实际 `STOCK_LIST` 的 18 个标的全部是 ETF：14 个 A 股行业/主题 ETF、3 个港股/纳指/中概跨境 ETF、1 个黄金商品 ETF。
- `src/search_service.py:4624-4657` 对所有 ETF 复用统一关键词，并沿用 `market_analysis`、`earnings`、`industry` 等个股式语义。历史 Anspire 样本中，`risk_check` 大量接收普通涨跌/成交额，`earnings` 大量接收涨幅或份额变化，`announcements` 混入普通行情页。
- 用户确认交易周期为 1-10 个交易日；底层主题/资产驱动优先，ETF 份额、规模和资金流仅作为确认信号。
- 用户确认允许经过确定性映射的行业/指数/商品内容进入独立 `underlying_driver` 通道，但不得冒充 ETF 产品事实。
- 规划时已有 115 条 SearXNG `news_intel` 业务记录；停服前旧容器仍持续写入，最终同批次共隔离 206 条。`search_api_calls` 原始物理请求审计永久保留。

## Requirements

- R1. 实际 `.env` 删除私有 SearXNG 路由、URL、secret、proxy、timeout/deadline 和专用预算值，并设置 `SEARXNG_PUBLIC_INSTANCES_ENABLED=false`；不得输出真实密钥。
- R2. `scripts/docker-up.sh` 不再读取搜索路由、不再附加 `searxng` profile、不再隐式启动 SearXNG；`server` / `analyzer` 启停语义保持不变。
- R3. 删除私有 Compose `searxng` 服务、`docker/searxng/`、`searxng_first_cn` 专用代码、Anspire 专用日预算及相关测试文档；通用 SearXNG Provider 仍可通过原有 Provider 机制显式配置。
- R4. `ANSPIRE_API_KEYS` 仅从实际 `.env` / 现有设置管理入口读取。Anspire 可用时 ETF 综合搜索固定走双查询且不自动 fallback；未配置或调用失败时该路径返回无可信数据，不得恢复 SearXNG 或放宽准入。项目中显式配置的其他非 SearXNG Provider 保留原有 legacy 兼容路径。
- R5. ETF 使用通用 profile 机制，至少覆盖行业/主题、跨境、商品、宽基、策略、债券和 `generic_etf`；当前 18 个标的只是验收样本，禁止把代码清单写死为唯一支持范围。
- R6. profile 优先使用可信基金元数据和受控别名，其次使用无歧义名称规则；无法建立唯一底层映射时使用 `generic_etf` 并禁用 `underlying_driver`，不得根据搜索结果反推 ETF 类型。
- R7. 查询同时包含 ETF 代码、基金全称、去除管理人后缀的产品简称和已验证底层主题/指数/商品别名；产品身份和底层身份必须分开使用。
- R8. 综合情报最多执行两个 Anspire 物理请求，每组固定 `top_k=18`：
  - `fresh_events`：近 3 个自然日的产品公告/申赎、份额规模变化、底层催化和明确风险。
  - `analysis`：近 30 个自然日的底层趋势驱动、核心成分影响、估值/景气和近期机构观点。
- R9. `max_searches` 继续表示启用的逻辑维度上限，不再等同于物理 API 次数；Pipeline 5 维度、Agent 6 维度及现有返回结构保持兼容。
- R10. ETF 内部分流使用交易语义：`product_notice`、`flow_scale`、`risk_event`、`underlying_driver`、`constituent_impact`、`structure_valuation`。旧键仅由适配层映射，报告不得把普通涨跌称为风险、把份额变化称为业绩或把行情页称为公告。
- R11. 产品公告、申赎、份额、规模、折溢价和跟踪事实必须直接命中 ETF 代码/名称或可信官方主体。
- R12. 不直接出现 ETF 产品身份的内容只有在命中已验证底层映射时才可进入 `underlying_driver`；必须明确声明为底层资产/主题驱动，映射缺失、歧义或仅泛行业/宏观相关时拒绝。
- R13. 短线排序采用：可信官方产品风险/交易限制优先覆盖；正常情况下底层主题/资产驱动 > 核心成分影响 > ETF 份额/规模/资金流确认 > 普通行情复述。资金流不得单独形成方向性交易事实。
- R14. 所有结果必须经过低质量/垃圾页过滤、产品或底层相关性验证、日期准入、确定性分流、URL 去重和每维度条数限制；3 天事件、30 天分析之外以及未知日期内容全部拒绝。
- R15. 搜索不得替代结构化实时行情；盘中价格、成交额、换手率和实时折溢价不得从新闻标题或摘要推断，没有结构化数据时明确标记不可用。
- R16. 两个查询组独立失败：超时、额度耗尽、请求失败或无可信结果只影响本组，不复用另一组内容填充，也不调用 SearXNG fallback。
- R17. 只缓存最终通过准入的不可变维度结果：`fresh_events` 进程内 TTL 15 分钟、`analysis` TTL 6 小时。缓存键包含标的、profile、模板版本、窗口、市场/语言和启用维度；失败、空结果、`no_trusted_data` 和原始响应不缓存。
- R18. 所有维度为空时 `format_intel_report` 不生成标题或“未找到”空壳文本；Pipeline/Agent 的 `news_context` 保持 `None`，不写 `news_intel`，仅记录低敏 `no_trusted_data` 诊断。
- R19. `news_intel` 增加可回滚隔离字段；按 `provider='SearXNG'` 和上线前时间边界隔离现有 115 条记录。所有读取路径默认排除隔离记录，其他 Provider 不受影响，`search_api_calls` 不删除不改写。
- R20. 同步更新配置注册、`.env.example`、中英文指南/部署文档、设置帮助、`docs/CHANGELOG.md`、`AGENTS.md` 和 Trellis spec，删除失效的私有 SearXNG说明并记录 ETF 双查询与可信准入契约。

## Acceptance Criteria

- [ ] 实际 `.env` 不再包含私有 SearXNG 运行值，公共实例关闭，真实 Key 不出现在输出或 Git diff 中。
- [ ] Docker/启动脚本不再包含或隐式启动私有 SearXNG；通用 Provider 的显式配置兼容性测试通过。
- [ ] 未配置 Anspire Key 时主分析继续执行但 `news_context=None`；配置后 Pipeline/Agent 冷启动每只 ETF 最多 2 次物理请求。
- [ ] Anspire 双查询失败不会自动追加其他 Provider 请求；未配置 Anspire 时，已有非 SearXNG Provider 的 legacy 兼容路径不被意外删除。
- [ ] 当前 18 个 ETF 正确分类为行业/主题、跨境、商品；额外宽基/策略/债券 ETF 可通用分类，未知/歧义 ETF 降为 `generic_etf`。
- [ ] 查询同时包含产品身份和底层身份，基金管理人后缀不挤占关键词，底层主题不脱离目标 ETF 无限制扩散。
- [ ] `fresh_events` 仅接受近 3 天，`analysis` 仅接受近 30 天；未知日期、4 天事件和 31 天分析均拒绝。
- [ ] 产品事实必须直接命中产品身份；不含 ETF 代码但命中确定性底层映射的内容只进入 `underlying_driver`，且不会进入产品事实字段。
- [ ] 行业/主题政策与景气、跨境指数/汇率/QDII、黄金价格/美元/实际利率能正确分流；普通涨跌、营销稿、泛宏观和错题内容被拒绝。
- [ ] 官方溢价/暂停申赎等风险覆盖看多催化；底层驱动优先于普通资金流；只有份额净流入时不得形成方向性事实。
- [ ] 新闻搜索不会生成实时折溢价、盘中价格、成交额或换手率。
- [ ] 同进程 15 分钟内重复分析为 0 次物理请求；15 分钟后、6 小时内最多刷新 1 次；模板/profile/窗口变化自动失效。
- [ ] 任一组失败不污染另一组；两组均无可信数据时无可注入文本、`news_context=None`、无 `news_intel` 写入。
- [ ] 206 条 SearXNG `news_intel` 被隔离并从全部消费路径消失，其他 Provider 不受影响；隔离可按批次回滚，原始审计仍可查询。
- [ ] 定向搜索/缓存/Pipeline/Agent/持久化/隔离测试、完整后端门禁、Docker Compose 校验、相关 Web 验证和 AI 治理检查通过。

## Out of Scope

- 不保证搜索一定有结果；无可信数据是合法结果。
- 不使用 LLM 对搜索结果进行二次分类或可信判定。
- 不在本任务接入实时 ETF IOPV/折溢价新数据源；只禁止用搜索结果伪造这些字段。
- 不增加跨进程或重启持久化搜索缓存。
- 不删除或改写 `search_api_calls` 原始审计。
- 不新增搜索供应商、自动购买/充值 Anspire 额度或在仓库保存真实 Key。
- 未经明确确认，不执行 git commit、tag、push 或创建 PR。
