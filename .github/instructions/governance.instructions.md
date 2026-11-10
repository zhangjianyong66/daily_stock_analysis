---
applyTo: "README.md,docs/**,AGENTS.md,CLAUDE.md,.github/**,.claude/skills/**,.agents/skills/**,.trellis/spec/**,scripts/**,docker/**"
---

# Governance Instructions

- Keep commands, file paths, workflow names, config keys, release paths, and directory references aligned with the executable repository state.
- `AGENTS.md` is the canonical AI collaboration document; if its meaning changes, sync `CLAUDE.md`, `.github/copilot-instructions.md`, `.github/instructions/*.instructions.md`, and repository skills as needed.
- Root `SKILL.md` and `docs/openclaw-skill-integration.md` describe product or external integration behavior, not repository governance.
- Project-owned skills live in `.claude/skills/`. mini-trellis owns generated platform assets in `.claude/skills/mini-trellis-*/` and `.agents/skills/mini-trellis-*/`; use its manifest and preview refreshes instead of manually syncing copies. Keep local runtime and hooks outside shared governance assets.
- After governance changes, run `python3 scripts/check_ai_assets.py`. It must work without a global mini-trellis installation or local hook configuration.
- Explain which pipeline, release path, deployment path, review automation, or governance asset is affected and what the rollback path is.
- Before creating/updating PRs, PR review, or issue analysis, refresh the latest code baseline with `git fetch --all --prune`; only run `git pull --ff-only` when the worktree is clean and the current branch can fast-forward. If not, keep local state intact and record the fetched remote baseline or branch gap before proceeding.
- Keep `README.md` limited to homepage-level content such as positioning, high-level capabilities, quick start, main entrypoints, and sponsorship/cooperation; put detailed behavior, configuration, troubleshooting, field contracts, and edge cases in `docs/*.md`.
- Avoid widening permissions, secret exposure, or destructive automation without a clearly documented need.
- Preserve the repository's opt-in auto-tag behavior (`#patch`, `#minor`, `#major`) unless the change explicitly updates release policy.
- When creating, reviewing, or suggesting PRs, prefer PR titles in `<type>: <change summary>` form and omit tool/agent source prefixes such as `[codex]`, `codex`, `autocode`, or `copilot`; treat this as non-blocking guidance, not a review hard blocker.
- If only one language version of a document is updated, explain why the counterpart was not synchronized.
