# Repository Instructions

Canonical source: [`AGENTS.md`](../AGENTS.md).

If any instruction in this file conflicts with `AGENTS.md`, follow `AGENTS.md`.

## Core Rules

- Respect directory boundaries:
  - Backend: `src/`, `data_provider/`, `api/`, `bot/`
  - Web: `apps/dsa-web/`
  - Desktop: `apps/dsa-desktop/`
  - Deployment/workflows: `scripts/`, `.github/workflows/`, `docker/`
- Do not run `git commit`, `git tag`, or `git push` without explicit user confirmation.
- Before creating/updating PRs, PR review, or issue analysis, refresh the latest code baseline with `git fetch --all --prune`; if the worktree is clean and the current branch can fast-forward, run `git pull --ff-only`. If local changes, conflicts, missing upstream, or non-fast-forward history make that unsafe, do not stash/reset/overwrite local state; analyze against fetched remote refs or record the baseline gap before proceeding.
- PR titles should use `<type>: <change summary>` such as `fix: 修复大盘分析历史记录丢失`; use `fix`/`feat`/`refactor`/`docs`/`chore`/`test`/`ci` where possible, and avoid `[codex]`, `codex`, `autocode`, `copilot`, or other tool/agent source prefixes. Treat this as process guidance and do not use title format mismatches as a hard review blocker.
- Do not hardcode secrets, accounts, ports, model names, absolute environment-specific paths, or environment-specific branches.
- Reuse existing modules, configuration entrypoints, scripts, and tests instead of adding parallel implementations.
- For user-visible behavior changes, CLI/API changes, deployment changes, notification changes, or report-structure changes, update the relevant docs and `docs/CHANGELOG.md`.
- In `docs/CHANGELOG.md`, the `[Unreleased]` section uses a **flat format**: one line per entry formatted as `- [type] description`, where type is one of `新功能`/`改进`/`修复`/`文档`/`测试`/`chore`. **Do not add `### category headers` inside `[Unreleased]`** to minimize merge conflicts in concurrent PRs. A maintainer will reorganize into the full categorized format at release time.
- Use `README.md` only for project positioning, high-level capabilities, quick start, main entrypoints, and sponsorship/cooperation information; avoid updating README unless the change is homepage-level.
- Put detailed module behavior, page interaction, topic configuration, troubleshooting, field contracts, implementation semantics, and edge cases in the appropriate `docs/*.md` file instead of README.
- When config semantics change, sync `.env.example` and assess impact on local runs, Docker, GitHub Actions, API, Web, and Desktop.

## Validation

- Backend changes: run `python -m py_compile` on changed Python files and targeted deterministic tests covering affected behavior and direct consumers. Full `./scripts/ci_gate.sh` is a CI responsibility by default; local execution requires the user's explicit request or agreement. Expand relevant tests for high-risk contracts; if impact remains unclear, explain the risk and obtain agreement before a local full run. Report actual coverage and gaps.
- Web changes: run `cd apps/dsa-web && npm ci && npm run lint && npm run build`.
- Desktop changes: build web first, then desktop if feasible.
- Review work should prioritize CI evidence (`gh pr checks`, workflow logs) before re-running local validation.
- AI governance changes (including `.agents/skills/`): run `python3 scripts/check_ai_assets.py`.

## AI Asset Governance

- `AGENTS.md` is the single source of truth for repository AI collaboration rules.
- `CLAUDE.md` must remain a symlink to `AGENTS.md`.
- Use `.github/instructions/*.instructions.md` for path-specific guidance.
- Project-owned collaboration skills live in `.claude/skills/`; keep them aligned with `AGENTS.md`.
- mini-trellis installs managed skills under `.claude/skills/mini-trellis-*/` and `.agents/skills/mini-trellis-*/`. The tool and its manifest own generated copies; preview updates with `mini-trellis refresh --dry-run`, rather than maintaining platform copies manually.
- mini-trellis is a memory layer, not a task workflow. Keep `session_auto_commit: false`; local hooks, runtime state and backups remain local artifacts.
