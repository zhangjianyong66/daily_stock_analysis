"""Offline checks for shared mini-trellis assets, independent of host wiring."""

import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_ai_assets.py"
SPEC = importlib.util.spec_from_file_location("check_ai_assets", SCRIPT)
ai_assets = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ai_assets)


class MiniTrellisAssetsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        root_patch = patch.object(ai_assets, "ROOT", self.root)
        root_patch.start()
        self.addCleanup(root_patch.stop)

    def write(self, relative_path, content):
        path = self.root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def install(self):
        files = {
            ".agents/skills/mini-trellis-remember/SKILL.md": "hash",
            ".claude/skills/mini-trellis-session-insight/references/help.md": "hash",
            ".codex/hooks.json": "hash",
        }
        self.write(".trellis/.mini-trellis-manifest.json", json.dumps({"files": files}))
        for name in files:
            if "/skills/" in name:
                self.write(name, "shared skill")
        self.write(".github/copilot-instructions.md", "Skills: .agents/skills/")
        self.write(
            ".github/instructions/governance.instructions.md",
            '---\napplyTo: ".agents/skills/**"\n---\nManaged skills.\n',
        )

    def assert_failure(self, message):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr), self.assertRaises(SystemExit) as exc:
            ai_assets.ensure_mini_trellis_assets()
        self.assertEqual(exc.exception.code, 1)
        self.assertIn(message, stderr.getvalue())

    def test_without_manifest_keeps_existing_governance_compatible(self):
        ai_assets.ensure_mini_trellis_assets()

    def test_shared_assets_pass_without_local_hooks_or_cli(self):
        self.install()
        ai_assets.ensure_mini_trellis_assets()

    def test_missing_codex_skill_is_reported(self):
        self.install()
        (self.root / ".agents/skills/mini-trellis-remember/SKILL.md").unlink()
        self.assert_failure("missing mini-trellis skill asset: .agents/skills/")

    def test_missing_claude_reference_is_reported(self):
        self.install()
        (self.root / ".claude/skills/mini-trellis-session-insight/references/help.md").unlink()
        self.assert_failure("missing mini-trellis skill asset: .claude/skills/")

    def test_malformed_manifest_is_reported(self):
        self.write(".trellis/.mini-trellis-manifest.json", "invalid json")
        self.assert_failure("cannot read mini-trellis manifest")
        self.write(".trellis/.mini-trellis-manifest.json", '{"files": []}')
        self.assert_failure("must contain a files object")

    def test_skill_path_cannot_escape_shared_directory(self):
        self.install()
        self.write(
            ".trellis/.mini-trellis-manifest.json",
            json.dumps({"files": {".agents/skills/../../outside.md": "hash"}}),
        )
        self.assert_failure("skill path escapes its directory")

    def test_copilot_must_cover_codex_skills(self):
        self.install()
        self.write(".github/copilot-instructions.md", "Only .claude/skills/")
        self.assert_failure("copilot-instructions.md must cover .agents/skills/")

    def test_governance_body_does_not_replace_path_coverage(self):
        self.install()
        self.write(
            ".github/instructions/governance.instructions.md",
            '---\napplyTo: "docs/**"\n---\nSee .agents/skills/**\n',
        )
        self.assert_failure("governance applyTo must cover .agents/skills/**")


if __name__ == "__main__":
    unittest.main()
