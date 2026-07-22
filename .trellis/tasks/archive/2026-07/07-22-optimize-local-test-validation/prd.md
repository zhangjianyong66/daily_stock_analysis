# 优化本地测试验证策略

## Goal

缩短 Codex 完成后端需求后的本地验证时间，避免每次交付都运行包含数千条离线用例的完整 `scripts/ci_gate.sh`，同时由 GitHub CI 保留全量门禁兜底。

## Background

- `scripts/ci_gate.sh` 当前会执行语法检查、Flake8、两组确定性检查和全部非网络 pytest。
- 当前工作区可收集 4538 条非网络 pytest，完整本地门禁耗时较长。
- `.github/workflows/ci.yml` 已通过 `backend-gate` 执行完整 `scripts/ci_gate.sh`，可继续承担全量回归职责。
- `AGENTS.md` 当前要求后端改动最终交付前默认执行完整门禁，这正是需要调整的行为来源。

## Requirements

- Codex 本地默认不得自动执行完整 `scripts/ci_gate.sh`。
- 后端本地最小验证必须包含改动 Python 文件的 `py_compile`、受影响 pytest，以及直接上下游契约的相关回归。
- 测试范围应依据改动文件、现有测试映射、业务契约和影响面选择，并在交付说明中列出实际执行项。
- GitHub CI 继续执行完整 `scripts/ci_gate.sh`，作为唯一默认全量测试兜底。
- 当改动涉及公共配置、API/Schema、认证、调度、共享基础模块，或无法可靠判断影响范围时，Codex 必须先说明风险并征求用户同意，才能执行本地全量门禁。
- 仅调整 `AGENTS.md` 的协作验证策略，不修改 `scripts/ci_gate.sh` 或 GitHub Actions。
- 保留 Web、Desktop、网络测试和其他改动面的现有专项验证原则，除非为消除与新后端策略的直接矛盾而需要最小措辞调整。

## Acceptance Criteria

- [x] `AGENTS.md` 明确规定后端本地默认只执行受影响验证，不再要求最终交付前自动运行完整 `scripts/ci_gate.sh`。
- [x] `AGENTS.md` 明确列出本地最小验证基线：改动 Python 文件语法检查、受影响测试、直接上下游回归。
- [x] `AGENTS.md` 明确完整 `scripts/ci_gate.sh` 默认由 GitHub CI 兜底。
- [x] `AGENTS.md` 明确高风险或影响范围不明时先征求用户同意，再决定是否本地运行完整门禁。
- [x] `scripts/ci_gate.sh` 与 `.github/workflows/ci.yml` 保持不变。
- [x] `python scripts/check_ai_assets.py` 通过。

## Out Of Scope

- 自动分析 Python 依赖关系或新增“受影响测试”选择脚本。
- 删除、裁剪或加速现有 pytest 用例。
- 改变 GitHub CI 的全量门禁行为。
- 调整 Web、Desktop 或网络 smoke 的既有验证要求。
