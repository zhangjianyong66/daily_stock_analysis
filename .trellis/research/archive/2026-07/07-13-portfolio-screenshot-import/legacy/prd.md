# 支持持仓与成交截图识别导入

## Goal

让无法从券商手机 App 导出 CSV 的用户，通过 1-5 张持仓或实际成交截图，在人工校对后安全地初始化或增量更新中国市场持仓账本；图片识别复用独立的 `VISION_MODEL`，不要求股票分析模型具备多模态能力。

## Background

- 当前持仓页只支持手工录入和券商 CSV 导入；CSV 解析的是逐笔成交，不能处理当前持仓快照。[PortfolioPage.tsx](/home/zhangjianyong/project/daily_stock_analysis/apps/dsa-web/src/pages/PortfolioPage.tsx:1455) [portfolio_import_service.py](/home/zhangjianyong/project/daily_stock_analysis/src/services/portfolio_import_service.py:143)
- 现有图片能力只提取股票代码、名称和置信度，不能识别持仓数量、成本或成交字段。[image_stock_extractor.py](/home/zhangjianyong/project/daily_stock_analysis/src/services/image_stock_extractor.py:286)
- 设置页已经提供独立的 Vision 模型选择器并保存到 `VISION_MODEL`，本需求不新增同义模型配置。[LLMChannelEditor.tsx](/home/zhangjianyong/project/daily_stock_analysis/apps/dsa-web/src/components/settings/LLMChannelEditor.tsx:2416)
- 持仓快照由 `PortfolioTrade` 等账本事件重放生成，没有直接写入当前持仓的平行数据源。[storage.py](/home/zhangjianyong/project/daily_stock_analysis/src/storage.py:508)
- 华泰“当日成交”列表展示名称、代码、方向、成交时间、均价和数量，但不展示日期、成交编号、手续费或税费；历史成交需 T+1 才可查询。

## Requirements

### R1. Shared Vision Boundary

- 提取共享 Vision 调用层，统一复用 `VISION_MODEL`、API Key 选择、Hermes 禁用规则、超时、重试、图片 MIME/魔数校验和单文件 5MB 限制。
- 原有自选股图片提取接口保持兼容；持仓与成交使用各自独立提示词、结构化解析和业务校验。
- 单次识别支持 1-5 张 JPEG、PNG、WebP 或 GIF 图片。
- 原图、base64 和模型原始响应只在请求期间存在，不入库、不写普通日志。

### R2. Position Screenshot Initialization

- 首版只支持 `cn/CNY` 账户和 6 位中国市场证券代码。
- 目标账户必须没有任何交易流水；不覆盖、补差或同步已有持仓。
- 必填字段为代码、名称、持仓数量和平均成本；市价、市值、可用数量、仓位和盈亏仅用于校验。
- 必须使用“持仓”而不是“可用”作为期初数量。
- 顶部总资产、可用、可取、总市值、总仓位和收益只读展示，不生成现金流水。
- 快照日期默认当天、允许修改、禁止未来日期；该日期表示系统开始跟踪日期，不是原始建仓日期。
- 提交时把每行转换为 `buy` 期初交易：数量为持仓、价格为平均成本、费用和税费为 0。
- 多图按代码合并；相同数据自动去重，数量或成本不一致时必须人工解决。
- 全部期初交易在同一事务中写入；任一失败则全部回滚。

### R3. Executed Trade Screenshot Import

- 只支持“当日成交”“历史成交”或交割单中的实际成交，不导入委托、撤单或未成交记录。
- 允许向已有 `cn/CNY` 账户增量导入。
- 必填字段为成交日期、代码、方向、成交数量和成交价格；成交时间可由截图提取，名称用于校验。
- 当日成交截图无日期时使用批次日期，默认当天、允许修改、禁止未来日期；历史成交优先使用行内日期。
- 账本新增可空 `trade_time`，保存精确到秒的成交时间；旧数据不伪造回填。
- 截图未展示手续费或税费时默认 0，允许用户编辑；禁止按费率猜测。
- 历史回填允许非未来日期，但提交前必须把现有和新增交易按日期、时间及稳定顺序重放，避免新卖出破坏后续账本数量约束。
- 明确重复项跳过；其余新增交易在同一事务中整体写入，任一失败则全部新增交易回滚。

### R4. Deduplication and Ambiguity

- 有成交编号时优先使用成交编号去重。
- 无成交编号时使用日期、时间、代码、方向、数量、价格、手续费和税费生成可见字段指纹。
- 同一图片中完全相同的多行按页面顺序保留为独立分笔。
- 跨图片完全相同的记录标记为疑似重叠，用户必须选择合并一笔或保留多笔。
- 与账户已有成交编号或指纹匹配的记录默认跳过并展示原因。
- 界面明确说明：缺少券商成交编号时只能 best-effort 去重。

### R5. Preview and Confirmation

- 页面提供“持仓初始化”和“成交增量”两个明确模式，不自动猜测图片语义后直接写入。
- 每张图片独立显示识别状态；失败图片必须重试、替换或明确移除后才能提交。
- 预览允许逐行编辑、删除并解决冲突；关键字段未通过格式与业务校验时禁止提交。
- 低置信度只产生提示，不替代字段校验和用户确认。
- 提交接口不信任前端状态，必须重新校验账户、市场、字段、重复、超卖和原子事务条件。

### R6. Compatibility and Documentation

- `trade_time` 同步到 ORM、旧库兼容迁移、Repository、Service、API schema、Web 类型和交易列表。
- 手工录入与 CSV 不含时间时保持兼容；CSV 若以后识别到时间可复用同一字段。
- 更新 `.env.example` 中 Vision 说明、持仓使用文档和 `docs/CHANGELOG.md`；不新增新的模型环境变量。
- 用户提供的真实资产截图不得作为仓库测试 fixture 或文档图片提交。

## Acceptance Criteria

- [x] AC1: 未配置 Vision 时，图片导入提示前往现有 `VISION_MODEL` 设置；配置文本分析模型但未配置视觉模型时不会误调用文本模型。
- [x] AC2: 原有 `/api/v1/stocks/extract-from-image` 行为和测试保持兼容。
- [x] AC3: 用户可上传 1-5 张持仓截图，校对后向空 `cn/CNY` 账户原子写入期初买入；已有交易的账户被拒绝且无数据变化。
- [x] AC4: 持仓截图中“持仓”和“可用”不相等时使用持仓数量；顶部资金数据不写入现金账本。
- [x] AC5: 用户可上传 1-5 张实际成交截图，补齐批次日期、编辑时间/方向/数量/价格/费用后向已有账户增量写入。
- [x] AC6: 委托、撤单、未成交或缺少关键字段的行不能提交。
- [x] AC7: `trade_time` 可空兼容旧库、旧 API 数据、手工录入和 CSV；有值时交易列表按日期和时间展示。
- [x] AC8: 成交编号重复或可见指纹重复会跳过；跨图歧义必须人工解决，合法同秒分笔可保留。
- [x] AC9: 增量批次任一新交易超卖、非法或写入冲突时全部新增交易回滚，已有数据不受影响。
- [x] AC10: 原图、base64、模型原始响应和完整资产明细不进入数据库或普通日志。
- [x] AC11: 后端完整门禁通过（4383 passed、4 deselected、45 warnings、413 subtests passed），Web 目标回归 49 passed，Lint 和构建通过；真实 Vision 在线调用未执行，并在交付中明确说明。

## Out of Scope

- 港股、美股、跨市场或非 `CNY` 账户截图。
- 从委托记录、盈亏、当前持仓差额推测成交。
- 自动导入现金、冻结资金、可取资金、历史已实现盈亏或原始建仓日期。
- OCR 规则引擎、券商页面模板硬编码或持久化识别历史。
- 自动抓取华泰 App 数据或绕过券商导出限制。

## Technical Notes

- 已确认方案：独立持仓截图领域服务 + 共享 Vision 调用层。
- 已确认 UI：选择模式与账户 -> 上传和识别 -> 可编辑预览 -> 原子确认提交。
- 已确认图片失败策略：逐图返回结果，但失败图片未重试、替换或移除前禁止提交。
- 历史会话检索未发现同一需求的既有决策；当前 `trellis mem` 无法读取 OpenCode SQLite 历史。
- 本任务是复杂跨层任务，实施前必须完成 `design.md`、主计划和 milestone 子计划并由用户评审。
