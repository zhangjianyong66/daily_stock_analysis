# v3.33.0 合并验收记录

## 结果与状态

目标：ZhuLinsen/daily_stock_analysis 的正式 Release v3.33.0，发布于 2026-10-15。标签指向 bba8bf51bdbd3badc75a832c52ede058ef5ab871。
合并前 HEAD：89b54f0f；备份分支：backup/upstream-v3.33.0-before-merge。
真实三方合并的 18 个冲突文件均已解决，索引无 unmerged entries。代码处于 main 的未提交合并状态；未执行 commit、push、部署或服务重启。

## 主要整合

- 保留本地实时行情预算、hedge、stale 和物理上游隔离；接入上游冻结身份、指数及可选 Futu/妙想能力。
- 保留 ETF 完整资金流窗口、日流/盘中流拆分及搜索审计/可信缓存；兼容上游供应商真实字段、北京市场和大小写代码。
- Web 保留图片异步任务、Vision/Extra Headers 和策略快照；整合会话讨论对象、数据中心、持仓风险和渠道 API_SURFACE。
- 合并配置协议校验与 Router wire model，保证图片 Responses 与渠道 Responses 组合不会重复编码。
- 保留本地顺序、最多 3 个 specialist，补齐诊断保留与清空问股技能的内建默认语义；同步多策略专题文档。
- 安装 requirements.txt 固定 wheel/hash 的 fxmacrodata-public-client 到现有 .venv。

## 实际验证

- 后端配置、存储、数据源、ETF资金流、港股、妙想、英文 Prompt、调度及打包脚本等定向回归：703 passed（/tmp/dsa-merge-final-backend.log）。
- Agent 编排、技能 API 与 FXMacroData 最终回归：309 passed（/tmp/dsa-merge-agent-final.log）。
- 策略快照及自动策略选择：18 passed（/tmp/dsa-merge-strategy-final.log）。
- 实际问股 HTTP/SSE 显式空技能失败项复验通过；此前问股/意图/API 大组为 1016 passed、9 failed，9 项随后均已修复或按本地顺序契约修订并复验，未重复执行整个大组（/tmp/dsa-merge-agent-failures-final.log、/tmp/dsa-merge-review-focus.log）。
- 搜索审计、可信资讯、上下文、Vision、图片任务及持仓 API 首轮 177 passed、18 failed；18 项在独立合并前 worktree 可复现，见下方基线。
- Web 已执行 npm ci；最终 lint 0 errors，1 个上游既有 warning；最终 TypeScript/Vite build 通过（/tmp/dsa-merge-web-build-final.log）。
- Web 冲突页面和状态管理等复验 451 passed、2 failed，其中选股 timeout 恢复已修复，后续选股/API 专项 54 passed；另外 1 项为合并前既有 StockBar 滚动契约失败（/tmp/dsa-merge-web-final.log、/tmp/dsa-merge-web-screening.log）。
- 桌面 Node 测试：51 passed（/tmp/dsa-merge-desktop-tests.log）。
- 所有变更 Python 编译、阻断级 Flake8、git diff --check、AI资产治理、shell语法及 Compose config --quiet 已检查。

## 基线问题与验证缺口

- 独立 worktree /tmp/dsa-merge-baseline 在合并前 HEAD 复现 Pipeline 16 项失败（__new__ 测试对象未初始化 skill_prompt_state）和搜索 2 项失败（断言漏掉现有 call_source=agent）。它们不是新增回归；没有为过期 fixture 修改业务流程。
- HomeStockWorkspace 的 StockBar 滚动测试在同一合并前 worktree 也失败；实际 StockBar 源文件未被此次上游修改。日志 /tmp/dsa-merge-web-baseline.log。
- 扩展审查另发现 test_agent_pipeline 的历史诊断 fixture 进入真实资讯/行情路径，未将该结果算作离线通过。
- 未执行完整 ci_gate.sh、GitHub Actions、在线供应商 smoke、Docker 镜像构建或 Electron 完整安装包构建；未创建 PR，因此未上传 PR 页面截图。现有服务和数据库未进行升级验证。

## 回滚

在没有后续工作且仍处于当前未提交合并状态时执行 git merge --abort，可恢复合并前受版本控制的代码。任务记录等新建未跟踪文件和 .venv 新依赖不受该命令影响。
备份分支仍固定指向合并前 HEAD。真实 .env 和业务数据库未修改。

中文本地多策略文档和 Trellis 内部规范没有对应英文镜像；上游已有中英配置文档变更均已保留。
