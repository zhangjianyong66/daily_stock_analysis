<!-- TRELLIS:START -->
# mini-trellis

This project uses mini-trellis as a memory layer. Working knowledge lives under `.trellis/`:

- `.trellis/spec/` — durable contracts (short markdown; read `index.md` first)
- `.trellis/research/` — topic inbox (`<topic>.md`; `README.md` is not a topic)
- `.trellis/workspace/` — per-developer journals

Record a session with `/mini-trellis:remember` (Claude/OpenCode), `/mini-trellis-remember` (Pi), `$mini-trellis-remember` (Codex), or the `mini-trellis-remember` skill (Cursor and DeepSeek Harness). When earlier decisions or relevant project rules are needed, use `mini-trellis mem recall "<topic or path>"`; expand evidence with `mini-trellis mem read "<ref>"`. No search is required for unrelated work. Promote lasting boundaries into spec with `mini-trellis-update-spec`.

Record only confirmed decisions, reusable research findings, or the session/compact handoff. Skip ordinary turns and unconfirmed guesses. New installs write notes without an automatic git commit; use `mini-trellis doctor` to check host wiring and `mini-trellis refresh --dry-run` before refreshing assets.

Keep confirmed rules short and faithful. Unconfirmed scope, exceptions, and implementation choices stay open or are labeled as inference, not added to the contract.

For a confirmed update, follow this short order: read the existing topic; edit that file; read it back and check the new rule, limits, and negations; run `python3 ./.trellis/scripts/add_session.py --title "..." --summary "..." --topic <actual-topic-path>`; read the journal and check its topic link. Journal-only success is not topic success; report partial writes accurately. New notes follow the requested or discussion language; updates preserve the document language.

When recall excerpts already answer the question with source and qualifiers, cite them and stop. Expand only missing context; do not repeat a lookup or fall back to dialogue-only `search` merely to reconfirm sufficient evidence.

For an explicit request to organize selected past sessions or supplied Markdown/text exports into project knowledge, use `mini-trellis-session-insight`; update existing documents and preserve sources.

mini-trellis does not create or drive tasks.

Managed by mini-trellis. Edits outside this block are preserved.
<!-- TRELLIS:END -->

# AGENTS.md

本文件是仓库 AI 协作规则的唯一真源。专题文档承载详细契约；按下表读取相关内容，避免每次加载全部知识。
文档与实际代码、脚本或 workflow 不一致时，先核实可执行行为，再修正相关说明。

## 1. 核心约束

- 未经用户明确确认，不执行 `git commit`、`git tag`、`git push`；commit message 使用英文，不添加 `Co-Authored-By`。
- 稳定性优先，仅修改当前任务需要的内容；先读现有实现、配置、测试和文档，复用现有模块，不新增平行实现。
- 不写死密钥、账号、本机路径、模型名、端口或环境差异逻辑；不得在聊天、日志、文档或提交中输出真实凭据。
- 新增配置项必须同步 `.env.example` 和相关文档。新配置优先做到“不配置也可运行，配置后增强能力”，避免叠加互斥开关。
- 用户可见能力、CLI/API、部署、通知、报告结构或 Web UI 变化必须更新相关文档和 `docs/CHANGELOG.md`。
- `[Unreleased]` 使用扁平格式：每条独立一行 `- [类型] 描述`，类型为新功能/改进/修复/文档/测试/chore；禁止新增 `###` 类目标题，正式发版由 maintainer 汇总。
- README 只放定位、核心能力、快速开始、主要入口及赞助/合作；行为细节、字段、配置和排障写入已有专题 docs/spec，不复制维护。
- 修改中英双语文档之一时评估另一份是否同步，未同步须说明原因。注释、docstring、日志与文件语境一致，清晰准确即可。
- 修改报告格式、渲染效果或 Web UI 时，PR 描述必须附受影响页面/报告截图；前后变化优先对比，不能截图须说明原因与替代证据。
- 一次性 Issue/PR/验收截图放 PR、GitHub 附件、Actions artifact 或外部证据链接，不合入仓库；长期产品示意图除外，文件名和语义须脱离具体 Issue/PR 编号。
- AI 生成代码必须完成语义自审、集成和验证；贡献质量取决于问题解决、契约一致和真实风险覆盖，不以行数、文件数或功能宣传衡量。

## 2. 目录与知识入口

股票智能分析流程：抓取数据 -> 技术分析/新闻检索 -> LLM 分析 -> 报告 -> 通知，覆盖 A 股、港股和美股。

| 改动面 | 目录边界 |
| --- | --- |
| 主入口与后端 | `main.py`、`server.py`；`src/`、`data_provider/`、`api/`、`bot/` |
| 后端职责 | `src/core/` 编排、`services/` 业务、`repositories/` 数据访问、`reports/` 报告、`schemas/` 结构 |
| 客户端 | Web：`apps/dsa-web/`；Electron：`apps/dsa-desktop/` |
| 构建与部署 | `scripts/`、`.github/scripts/`、`.github/workflows/`、`docker/` |
| 测试与文档 | `tests/`、`docs/`、`.trellis/spec/` |

开始改动前按触发条件读取下列专题及其中的测试要求；完整目录见 [backend 索引](.trellis/spec/backend/index.md)。

| 触发条件 | 必读契约 |
| --- | --- |
| 文件放置、分层和命名 | [目录结构](.trellis/spec/backend/directory-structure.md) |
| 运行、测试环境隔离、索引刷新、Docker/代理、发布 | [运行部署](.trellis/spec/backend/runtime-deployment.md) |
| 风格、文档同步、测试与质量 | [质量规范](.trellis/spec/backend/quality-guidelines.md) |
| 数据库、启动迁移、锁与事务 | [数据库](.trellis/spec/backend/database-guidelines.md) |
| 数据源 fallback、异常与敏感日志 | [错误处理](.trellis/spec/backend/error-handling.md)、[日志](.trellis/spec/backend/logging-guidelines.md) |
| 实时行情路由、超时、hedge、stale | [数据源超时与降级](.trellis/spec/backend/error-handling.md) |
| ETF 日资金流和盘中流 | [ETF 资金流](.trellis/spec/backend/etf-capital-flow.md) |
| 搜索计数、错误分类、余额、详情/导出认证 | [搜索审计](.trellis/spec/backend/search-usage-audit.md) |
| 综合搜索、可信准入、共享缓存、污染隔离 | [搜索情报](.trellis/spec/backend/search-intelligence.md) |
| Vision、截图任务、草稿、持仓/成交导入 | [图片导入](.trellis/spec/backend/portfolio-image-import.md) |
| 分析策略、日线形态、报告历史快照 | [策略执行](.trellis/spec/backend/strategy-execution.md)、[形态报告](.trellis/spec/backend/kline-pattern-report.md) |
| 每日大盘上下文与决策护栏 | [市场上下文](.trellis/spec/backend/daily-market-context.md) |
| 新 helper、重复逻辑或跨层字段 | [复用与跨层指南](.trellis/spec/guides/index.md) |
| mini-trellis 记忆使用 | [记忆层](.trellis/spec/guides/mini-memory.md) |
| 本机/ECS2 运维排查 | [历史部署线索](.trellis/research/local-ecs2-operations.md)，操作前核实当前状态 |

## 3. AI 协作资产治理

- `CLAUDE.md` 必须保持指向 `AGENTS.md` 的软链接。
- `.github/copilot-instructions.md`、`.github/instructions/*.instructions.md` 是镜像或分层补充，冲突时以本文件为准。
- 项目自有协作技能在 `.claude/skills/`，其规则与本文件保持一致；Issue/PR 分析产物写入本地 `.claude/reviews/`。
- mini-trellis 的 Claude/Codex 技能分别安装于 `.claude/skills/mini-trellis-*/` 和 `.agents/skills/mini-trellis-*/`，由工具及 manifest 管理；使用 `refresh --dry-run` 检查更新，不手工长期维护跨平台副本。
- 顶部 mini-trellis 托管块由工具维护，项目定制写在块外。mini-trellis 只负责记忆，不创建或驱动任务；`session_auto_commit: false` 保持关闭。
- 本地 hook、运行状态、备份和凭据不作为共享规则；保留既有忽略边界，不为安装工具扩大入库范围。
- 新增其他 agent 目录须明确单一真源及生成/同步方式，禁止手工维护多份同义规则。
- 根目录 `SKILL.md`、`docs/openclaw-skill-integration.md` 属于产品或外部集成说明，不是协作规则真源。
- 修改治理资产（含两处技能目录）后执行 `python3 scripts/check_ai_assets.py`；该检查不依赖全局 mini-trellis 或本机 hook。

## 4. 开发与验证

1. 判断任务类型 `fix/feat/refactor/docs/chore/test/review`，识别改动层次及直接上下游。
2. 阅读相关专题、实现和测试；配置、API/Schema、认证、调度、fallback、报告、发布和桌面启动属于高风险面。
3. 实施最小必要改动，检查异常、兼容、文档与工作流路径，按下表验证。
4. 完成后说明实际改动及原因、执行的验证和未覆盖项；不得把推断写成已验证事实。

### 分层验证

- 迭代先跑受影响测试；功能完成后覆盖直接上下游。修复失败后先重跑失败及相关用例，通过后无新改动或疑点不重复扩大检查。
- 最终交付、提交或创建/更新 PR 前，本地默认只做定向验证，全量测试由 GitHub CI 兜底。
- 高风险面应扩大相关回归；仍无法可靠判断影响时，说明风险并征得用户同意后再执行本地完整门禁。
- 除非用户明确要求或同意，不在本地自动执行完整 `./scripts/ci_gate.sh`。CI 未运行、未覆盖或阻断失败，不得宣称完整门禁通过。
- 已有对应 PR CI 可直接引用；环境差异、缺失覆盖或未执行检查必须说明。网络和三方 smoke 单独执行，仅用于相关改动、发布验证或明确要求，不替代确定性离线检查。

| 改动面 | 最低验证与交付要求 |
| --- | --- |
| Python 后端 | `python -m py_compile <changed_python_files>` 和受影响 pytest；说明 API、编排、报告、通知、fallback、认证/调度的实际覆盖 |
| Web | 迭代跑受影响测试；交付前 `cd apps/dsa-web && npm ci && npm run lint && npm run build`；说明路由、状态、API、Markdown/图表及认证联动缺口 |
| Desktop/打包 | 先构建 Web 再构建 Desktop；平台受限时分别说明 Web 产物、Electron 与 Release 验证情况 |
| API/Schema/认证 | 后端回归及受影响客户端构建；说明登录、Cookie、会话、轮询、字段/枚举的兼容影响 |
| 文档与治理 | 核对命令、配置、路径和 workflow；纯文档不强制代码测试，治理改动仍跑专用检查 |
| 脚本/Docker/Workflow | 最接近改动面的验证，说明流水线/部署影响、未执行项与风险 |
| 网络/三方 | 先离线确定性检查，覆盖 timeout、retry、fallback、异常文案与降级；说明未做在线验证的原因 |

CI 当前检查名与职责以 workflow 为准：`ai-governance`；后端 `backend-tests` 分片及汇总 `backend-gate`；`docker-build`；按路径触发的 `web-gate`。网络 smoke 和 PR AI review 为非阻断辅助证据。详见运行部署专题。

### 公共稳定性护栏

- 数据源须保持优先级、标准化、缓存、超时与降级语义；单一数据源或通知渠道失败不拖垮主流程，除非需求明确 fail-fast。
- 配置默认值、CLI、启动或调度变化同时评估本地、Docker、Actions、API、Web、Desktop。
- API/Schema/认证/报告载荷优先追加字段、保留旧字段或提供兼容层；报告/Prompt/提取器/Bot/通知变化检查上游输入与下游消费。
- 数据库启动迁移顺序是可测试契约，改变 `_ensure_*` 顺序须保留失败归因并跑 `tests/test_storage.py`。
- 分析实际策略只读持久化的 `strategy_execution` 快照，旧报告缺失时显示“策略未记录”，禁止从当前配置或 LLM 文本反推。
- ETF 走通用分析和市场环境护栏，不以专用资金流规则强制改写交易结论；详细数据与失败语义见专题。
- 修改 `src/services/image_stock_extractor.py` 的 `EXTRACT_PROMPT` 时，PR 描述附完整最新 prompt。

## 5. Issue / PR 与发布

- Issue 分析、PR 审查、Issue 修复优先使用 `.claude/skills/` 中的 `analyze-issue`、`analyze-pr`、`fix-issue`；命令、验证和交付结构与本文件一致，优先读取 CI 证据。
- PR 创建/更新、PR 审查或 Issue 分析前，先检查工作区并执行 `git fetch --all --prune`；工作区干净且当前分支可 fast-forward 时执行 `git pull --ff-only`。
- 有本地改动、冲突、未跟踪风险文件或无法 fast-forward 时，不强行切分支、stash、reset 或覆盖。审查/分析可用已 fetch 的 refs/PR head，记录未更新原因、本地 HEAD 和远端基线。
- PR 创建/更新须说明当前分支与目标基线差异，必要时请求确认 rebase、merge 或继续。除上述安全同步外，skill 不得默认执行 pull、push、tag 或 `gh pr create`，须有用户确认。
- PR 标题推荐 `<类型>: <修改内容>`，类型为 fix/feat/refactor/docs/chore/test/ci，不加 codex/copilot 等工具来源前缀；仅为建议，不单独阻断。
- 审查顺序：必要性 -> 关联性 -> 标题建议 -> 对照 PR 模板的描述完整性 -> 验证证据 -> 实现正确性 -> 合入判定。
- fix PR 必须说明原问题、根因、修复点与回归风险；描述应与当前实际 diff、兼容性和验证一致。
- 处理 review：逐条列出原问题和根因，检查同一语义的所有入口/配置/测试/文档/workflow，修复完整契约，补 reviewer 反例或明确验证限制，同步 PR body。
- 禁止只追加局部 patch、用 broad fallback 或静默空值掩盖契约、mock 掉风险层、把 CI 通过当作反例已解决。
- 正确性/安全问题、阻断 CI 失败、描述与 diff 实质矛盾、缺少回滚方案、反复未收敛的契约漂移或证据失真，均阻断合入。无法收敛须说明需拆分或关闭重做，不声称 ready for merge。
- 发布/打包变化检查触发条件、产物、权限和回滚。自动 tag 仅在 commit title 含 `#patch/#minor/#major` 时 opt-in；改变政策须有明确需求，手动 tag 使用 annotated tag。
- 用户可见变更优先经 PR 合入，补齐 label 和验证说明。

## 6. 交付

普通任务简洁说明结果和验证；较复杂或高风险任务明确改动原因、未验证项、风险与回滚方式。PR 仍须具备回滚方案。
纯文档可说明“仅文档，未运行业务测试”，并交代命令/文件名核对及治理校验；无需重复空洞栏目。
