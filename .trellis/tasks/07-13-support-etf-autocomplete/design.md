# 支持 ETF 自动补全 - 技术设计

## 边界

本任务只修改自动补全索引生成与前端搜索相关测试，不改变首页组件交互、不改变分析 API、不改变 ETF 分析主流程。

## 数据来源

- 常用 ETF 种子清单：仓库内维护一份小型 CSV，作为离线兜底来源，覆盖常见 A 股 ETF。
- 全量 ETF：在 `scripts/generate_index_from_csv.py` 生成阶段通过 AkShare `fund_etf_spot_em` best-effort 拉取。
- 失败策略：AkShare 缺依赖、网络失败、代理失败、接口返回字段异常时，只打印 warning，不阻断股票索引生成；最终索引至少包含种子 ETF。

## 数据契约

ETF 原始记录统一转换为与股票相同的内部结构：

- `ts_code`: 交易所后缀代码，例如 `510300.SH`、`159915.SZ`
- `symbol`: 展示代码，例如 `510300`
- `name`: 中文名称，例如 `沪深300ETF`
- `market`: `ETF`
- `asset_type`: `etf`
- `aliases`: 可选别名

索引输出继续使用现有 10 字段压缩格式：

1. canonicalCode
2. displayCode
3. nameZh
4. pinyinFull
5. pinyinAbbr
6. aliases
7. market
8. assetType
9. active
10. popularity

## 代码与市场规则

- 沪市 ETF 前缀：`51`、`52`、`56`、`58`，canonical code 使用 `.SH`。
- 深市 ETF 前缀：`15`、`16`、`18`，canonical code 使用 `.SZ`。
- 其他无法识别交易所的 ETF 记录跳过，避免生成不可分析或不可路由代码。
- ETF 在前端 `market` 使用现有 `ETF` 枚举，`assetType` 使用 `etf`。

## 合并与去重

- 股票列表先生成索引，ETF 列表再合入。
- ETF 合入按 `canonicalCode` 去重。
- 若种子清单与全量接口返回同一 ETF，优先保留全量接口名称，合并去重后的 aliases。

## 测试策略

- Python 单测覆盖：
  - ETF 前缀转 canonical code。
  - 种子 ETF 能转换成索引项。
  - mock AkShare 全量返回新 ETF 时能合入。
  - mock AkShare 抛错时生成流程仍保留种子 ETF。
  - 压缩后 `assetType` 为 `etf`。
- 前端单测覆盖：
  - `searchStocks` 能按 ETF 代码、中文名称、别名或拼音命中。

## 回滚

回滚本任务只需撤销：

- ETF 种子 CSV。
- `scripts/generate_index_from_csv.py` 中 ETF 加载、合并、转换逻辑。
- 相关测试与重新生成的 `stocks.index.json`。
