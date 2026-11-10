# Repository Claude Skills

本目录存放项目自有协作 skills 和 mini-trellis 生成的 Claude 平台技能，属于版本库资产。

- 规则真源：仓库根目录 `AGENTS.md`
- 兼容入口：根目录 `CLAUDE.md`（应为指向 `AGENTS.md` 的软链接）
- 本目录中的 skill 需要与 `AGENTS.md` 保持一致
- `.claude/reviews/` 属于本地分析产物，不作为规则真源

项目自有技能（analyze-issue、analyze-pr、fix-issue）由仓库维护。mini-trellis 技能由工具及 `.trellis/.mini-trellis-manifest.json` 管理，Claude 和 Codex 分别使用本目录及 `.agents/skills/` 中的生成入口；先运行 `mini-trellis refresh --dry-run` 检查更新，不手工长期维护平台副本。

其他新增 agent 目录仍须明确单一真源及生成/同步方式。修改共享技能后执行 `python3 scripts/check_ai_assets.py`；不要将本地 hooks、评审产物或运行状态加入共享技能目录。
