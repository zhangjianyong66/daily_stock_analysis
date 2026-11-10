# 支持 ETF 自动补全

## Goal

首页股票代码输入框在输入 ETF 代码或 ETF 名称时，也能像股票一样展示联想下拉选项，并允许用户选择对应 ETF 发起分析。

用户价值：减少手动输入 ETF 代码的出错概率，让 ETF 与股票在首页分析入口保持一致的选择体验。

## Confirmed Facts

- 首页输入框使用 `apps/dsa-web/src/components/StockAutocomplete/StockAutocomplete.tsx`。
- 首页调用位置在 `apps/dsa-web/src/pages/HomePage.tsx`，没有针对 ETF 的额外屏蔽逻辑。
- 前端索引类型 `apps/dsa-web/src/types/stockIndex.ts` 已支持 `AssetType = 'stock' | 'index' | 'etf'`。
- 前端搜索逻辑 `apps/dsa-web/src/utils/searchStocks.ts` 只按 `active` 过滤，不按 `assetType` 排除 ETF。
- 后端静态入口 `api/app.py` 负责托管最新可用的 `stocks.index.json`。
- 当前 `apps/dsa-web/public/stocks.index.json` 中 ETF 条目数为 0，`510300`、`159915`、`512880`、`512000`、`515030`、`159887` 均未命中。
- `scripts/generate_index_from_csv.py` 当前生成索引时固定写入 `"assetType": "stock"`，未把 ETF 作为独立资产类型写入。
- `requirements.txt` 已声明 `akshare>=1.12.0` 和 `efinance>=0.5.5`。
- 本地环境可导入 `akshare`，且 AkShare 暴露 `fund_etf_spot_em` ETF 接口；实际调用受当前代理影响失败，因此全量 ETF 拉取必须允许失败兜底。
- 本地环境当前不能导入 `efinance`，不适合作为本次索引生成的唯一全量来源。

## Requirements

- R1: 首页自动补全索引必须包含常用 ETF 种子清单条目。
- R2: ETF 条目必须可通过代码、中文名称、拼音缩写或别名命中联想下拉。
- R3: 选择 ETF 联想项后，应沿用现有 `autocomplete` 提交流程，不破坏股票、港股、美股、北交所等现有自动补全行为。
- R4: ETF 条目的 canonical code 必须与现有分析入口兼容，避免选择后提交无法识别的代码。
- R5: 索引生成流程应 best-effort 拉取全量 A 股 ETF，并从返回数据中提取 ETF 代码和名称。
- R6: 当全量 ETF 拉取因网络、代理、依赖或接口异常失败时，索引生成不能整体失败，必须至少保留常用 ETF 种子清单。
- R7: 变更应覆盖索引生成和前端搜索/加载测试，防止后续重新生成索引时 ETF 丢失。

## Acceptance Criteria

- [x] 在首页输入典型 ETF 代码（如 `510300`、`159915`、`512880`）时能出现对应联想选项。
- [x] 在首页输入典型 ETF 名称或简称（如 `沪深300ETF`、`创业板ETF`、`证券ETF`）时能出现对应联想选项。
- [x] 生成脚本在 AkShare 全量 ETF 接口返回新 ETF 时，能把该 ETF 写入索引并保留代码、名称和 `assetType: 'etf'`。
- [x] 生成脚本在 AkShare 全量 ETF 接口失败时，仍能生成包含常用 ETF 种子清单的索引。
- [x] 选择 ETF 联想项后提交来源仍为 `autocomplete`。
- [x] 现有股票自动补全测试继续通过。
- [x] 索引生成或加载相关测试覆盖 ETF 条目，验证 `assetType: 'etf'` 不被丢失。

## Out of Scope

- 本任务不扩展 ETF 分析主流程能力，只补齐首页自动补全入口。
- 本任务不在用户输入时调用在线实时 ETF 搜索服务；全量 ETF 只在索引生成阶段 best-effort 获取。
- 本任务不调整报告内容、分析 Prompt 或数据源 fallback 策略。
