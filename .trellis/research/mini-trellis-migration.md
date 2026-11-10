# mini-trellis 迁移与协作规则收敛

## 决定与依据

- 2026-11-09，用户选择“完整收敛”，并明确要求开始执行。
- 基线是迁移后的未提交工作树：原 AGENTS.md 为 422 行，已包含 mini-trellis 托管块；不是从 Git HEAD 重新安装或重建规则。
- 规则真源与技能归属见 [AGENTS.md](../../AGENTS.md) 第 3 节；本页只记录迁移对照与验收，不维护第二份协作规则。
- 主文件精简为 145 行；原有业务限制归入专题。原文过时状态不作为当前能力重新确认。

## 条款去向

| 原 AGENTS.md 内容 | 当前归属 |
| --- | --- |
| 硬规则、PR 标题、贡献质量 | AGENTS.md 第 1、5 节，合并重复条款 |
| AI 资产治理 | AGENTS.md 第 3 节，以及 Copilot 指令、技能 README、治理脚本 |
| 仓库速览 | AGENTS.md 第 2 节；详细分层仍见目录结构规范 |
| 运行命令、Web/Desktop、后端环境隔离、PR/CI 命令 | [运行部署](../spec/backend/runtime-deployment.md) |
| 股票自动补全索引 | 运行部署的既有“股票自动补全索引”章节 |
| 实时行情多源与降级 | [错误处理](../spec/backend/error-handling.md) 的既有超时场景，补充原定向测试命令 |
| ETF 资金流 | [ETF 资金流](../spec/backend/etf-capital-flow.md)，补充流动性风险提示边界 |
| 搜索审计与余额 | [搜索审计](../spec/backend/search-usage-audit.md)，保留网络出口和权限边界 |
| Anspire 综合情报、共享缓存、准入、隔离 | [搜索情报](../spec/backend/search-intelligence.md)，与搜索审计互链 |
| 图片导入 | [图片导入](../spec/backend/portfolio-image-import.md)，补齐单 worker、探针、兼容状态与前端测试入口 |
| Docker 构建代理 | 运行部署的“Docker 构建与运行代理”章节 |
| 本机/ECS2、Key 配置状态、历史隔离批次 | [历史运维线索](./local-ecs2-operations.md)，均标明未重新验证 |
| 默认流程、验证矩阵、CI 覆盖 | AGENTS.md 第 4 节及质量/运行部署专题 |
| 公共稳定性护栏 | AGENTS.md 第 4 节；策略、形态和数据库详细契约继续使用原专题 |
| Issue/PR、review 反馈、发布、交付 | AGENTS.md 第 5、6 节，保留授权与合入阻断条件 |

## 核对中修正的漂移

- 实时行情已有完整归属，因此未保留新建平行规范；搜索分组准入从审计专题移出，审计保留物理计数及其测试场景。
- `src/search_service.py` 的 ETF Anspire 分组失败不扇出；普通股票仅失败组允许既有 fallback。普通股票分析时效按既有 180 天且允许未知日期，ETF 为严格 3/30 天。
- `scripts/docker-up.sh` 的 DEFAULT_DOCKER_BUILD_PROXY 实为 7890；原 AGENTS.md 的 10808 默认值过时。仅修正文档，未修改或验证本机代理服务。
- 当前 ci.yml 由 backend-tests 分片执行检查，backend-gate 汇总；web-gate 还包含 smoke 与 UI fixtures。
- 通用指南中删除旧 Trellis 命令、模板注册/同步要求与重复示例；不修改 archive 内历史命令或工具提供的兼容模块。
- 英文指南和指令保持英文，中文文档保持中文；未修改产品中英双语手册，因本次仅涉及协作治理，无产品能力变化。

## 验收与限制

- 治理脚本、Python 编译、8 个 unittest/定向 pytest、Git 空白检查及本地 Markdown 链接检查通过；mini-trellis 托管块保持原样。
- `mini-trellis doctor` 通过；Codex 启动上下文已在本会话收到，Claude 真实启动尚未验证。
- refresh dry-run 无写入，退出码为 1：本地 .codex/config.toml 差异保留并跳过，AGENTS 托管块显示可更新。未执行实际 refresh，未覆盖用户定制。
- 不依赖本机 hook 或全局 CLI 的治理测试覆盖：正常资产、缺失技能/引用、无 manifest、无本地 hook、损坏 manifest、路径越界及 Copilot 路径覆盖。
- 未运行业务全量门禁、Docker 构建、远程运维或在线第三方测试；本次未修改业务实现。

## 回滚

- 优化前的 AGENTS.md 和本地 Codex 配置快照位于 `/tmp/dsa-mini-trellis-tUxjvukP/`，临时目录可能被系统清理。
- 回滚须仅撤销本轮治理与文档调整；不能使用整仓 reset/checkout，也不能撤销原有 Trellis 卸载、mini-trellis 安装和研究归档迁移。
- 原有未提交安装文件、历史研究及工具脚本保持原状；没有提交、推送或服务重启。
