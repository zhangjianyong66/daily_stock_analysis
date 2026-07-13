# 质量规范

本仓库稳定性优先。改动应最小化影响面，优先复用现有层次、helper、脚本和测试。

## 代码风格

Python：

- 支持 Python 3.10+；CI 使用 Python 3.11。
- `pyproject.toml` 配置 Black 和 isort，行宽为 120。
- isort 使用 `profile = "black"`。
- Flake8 在 CI 中只阻断严重错误：`E9,F63,F7,F82`。
- `.trellis/.backup-*` 是 Trellis 升级生成且被 Git 忽略的恢复备份，不属于当前代码基线，Flake8 必须排除该目录。
- 文件语境中大量中文注释和日志是可接受的；新增注释要解释非显然约束，不写空泛描述。

TypeScript / Web：

- `apps/dsa-web/package.json` 要求 Node `>=20.19.0 <27`、npm `>=10`。
- Web 使用 React、Vite、TypeScript、ESLint、Vitest。
- 前端类型放在 `apps/dsa-web/src/types/`；后端 API schema 改动时必须同步检查。

## 分层规则

- Endpoint 只负责 HTTP 边界：参数、response model、调用 service、异常映射。参考 `api/v1/endpoints/portfolio.py`。
- Service 负责业务语义：归一化、校验、编排、跨数据源处理和 DTO 输出。参考 `src/services/portfolio_service.py`。
- Repository 负责数据库：SQLAlchemy 查询、事务、锁冲突和持久化异常。参考 `src/repositories/portfolio_repo.py`。
- 数据源适配放在 `data_provider/`，不要把第三方 API 调用塞进 API endpoint。
- CLI/Web/API/Bot 共享业务逻辑时，应沉到 `src/services/` 或 `src/core/`，避免多入口重复实现。

## 配置和文档同步

- 新增配置项必须同步 `.env.example`，并更新相关文档。
- 用户可见能力、CLI/API 行为、部署方式、通知方式、报告结构或 Web UI 变化，必须同步 `docs/CHANGELOG.md` 的 `[Unreleased]` 段。
- `[Unreleased]` 使用扁平格式：`- [类型] 描述`，类型为 `新功能`、`改进`、`修复`、`文档`、`测试`、`chore`。
- README 只放项目定位、核心能力、快速开始、主要入口、赞助/合作等首页级内容；细节优先写入 `docs/*.md`。
- 修改中英双语文档之一时，要评估另一份是否同步；未同步要在交付说明中说明原因。
- 修改 AI 协作治理资产时执行 `python scripts/check_ai_assets.py`。

## 测试要求

按改动面选择最接近的验证：

- Python 后端：优先 `./scripts/ci_gate.sh`；最低 `python -m py_compile <changed_python_files>`。
- 离线测试：`python -m pytest -m "not network"`。
- 数据源、网络、LLM、通知相关：先跑离线确定性检查；未执行在线验证时说明原因。
- Web：`cd apps/dsa-web && npm ci && npm run lint && npm run build`。
- Desktop：先构建 Web，再构建桌面；平台受限时说明未覆盖内容。
- Docker/Workflow：运行最接近改动面的本地验证；不能跑 Actions 或 Docker 时说明风险。

不要用 mock 绕开真实风险层来制造通过结果。测试应覆盖用户路径、数据契约和 reviewer 指出的反例。

## 常见禁止项

- 不写死密钥、账号、本机绝对路径、模型名、端口或环境差异逻辑。
- 不新增与现有 `src/services`、`src/repositories`、`api/v1/schemas` 平行的重复实现。
- 不用 broad fallback、静默 `return None/[]/False` 掩盖不清晰契约。
- 不在 API/Web/Desktop 各自重复解析同一个 payload 字段；需要共享 schema、type guard、normalizer 或 service 输出。
- 不把临时验收截图、PR 过程截图、一次性证据作为仓库文件合入。
- 未经明确确认，不执行 `git commit`、`git tag`、`git push`。

## Review 自检

交付前至少确认：

- 改动是否只覆盖当前任务必要范围。
- 相关入口是否一起检查：runtime、API/Web、CLI、workflow、docs、tests。
- 新字段或配置是否同步到 schema、前端类型、`.env.example`、文档。
- 错误路径是否有明确日志和用户可理解的错误响应。
- 已执行的验证能否覆盖主要风险；未验证项是否明确说明。
