# 支持 ETF 自动补全 - 实施计划

## 任务清单

- [x] 新增常用 ETF 种子 CSV，至少覆盖 `510300`、`159915`、`512880`、`512000`、`512480`、`515030`、`159887`。
- [x] 在 `scripts/generate_index_from_csv.py` 中新增 ETF 代码识别、canonical code 构造、种子 ETF 加载逻辑。
- [x] 在 `scripts/generate_index_from_csv.py` 中新增 AkShare 全量 ETF best-effort 拉取逻辑，失败时 warning 并继续。
- [x] 调整 `build_stock_index` 或周边转换逻辑，使 ETF 输出 `market: ETF`、`assetType: etf`，股票仍保持现有行为。
- [x] 重新生成 `apps/dsa-web/public/stocks.index.json`；如项目需要，同步 `static/stocks.index.json`。
- [x] 补充 `tests/test_generate_index_from_csv.py` 覆盖种子、全量、失败兜底和压缩格式。
- [x] 补充或调整 `apps/dsa-web/src/utils/__tests__/searchStocks.test.ts`，覆盖 ETF 代码和名称联想。
- [x] 运行验证命令并记录结果。

## 验证命令

```bash
python -m pytest tests/test_generate_index_from_csv.py tests/test_stock_index_remote_service.py tests/test_stock_index_loader.py
cd apps/dsa-web && npm run test -- searchStocks
cd apps/dsa-web && npm run lint
```

如前端测试脚本名称不支持定向运行，则改用仓库现有最近似命令。

## 风险点

- AkShare ETF 接口依赖网络和东方财富可用性，必须保持 best-effort。
- 当前本地代理可能导致 AkShare 请求失败，测试不能依赖真实网络。
- 全量 ETF 返回字段可能变动，解析逻辑需要兼容常见中文字段名并对缺失字段 fail-open。
- 重新生成索引会改变较大的 JSON 文件，需确认 diff 主要是 ETF 条目追加。

## 回滚点

- 若全量拉取实现不稳定，保留种子清单能力，移除 AkShare 全量拉取逻辑。
- 若前端搜索出现回归，撤销搜索测试相关改动；核心搜索算法原则上无需改动。
