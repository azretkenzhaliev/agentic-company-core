"""Tests for scripts/hooks/guard_kb_write.py, run as Claude Code runs it:
JSON on stdin, exit 2 plus stderr to block, exit 0 to allow."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HOOK = Path(__file__).resolve().parents[1] / "hooks" / "guard_kb_write.py"
FAKE_TOKEN = "gh" + "p_" + "a1B2c3D4e5" * 3 + "f6G7h8"
FAKE_KEY = "-----BEGIN RSA " + "PRIVATE KEY-----\nMIIEow...\n-----END RSA " + "PRIVATE KEY-----"


class GuardKbWrite(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        (self.root / "knowledge" / "research").mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def run_hook(self, tool_name, tool_input, agent_type=None, cwd=None):
        payload = {
            "session_id": "test",
            "cwd": str(cwd or self.root),
            "hook_event_name": "PreToolUse",
            "tool_name": tool_name,
            "tool_input": tool_input,
        }
        if agent_type:
            payload["agent_type"] = agent_type
        env = dict(os.environ, CLAUDE_PROJECT_DIR=str(self.root))
        return subprocess.run(
            [sys.executable, str(HOOK)],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            env=env,
            timeout=30,
        )

    def kb(self, rel):
        return str(self.root / "knowledge" / rel)

    # Secrets in the KB are blocked, whatever the write tool.

    def test_allows_clean_write_in_kb(self):
        result = self.run_hook("Write", {"file_path": self.kb("company/overview.md"), "content": "# Overview\n"})
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_blocks_private_key_written_to_kb(self):
        result = self.run_hook("Write", {"file_path": self.kb("engineering/runbooks/x.md"), "content": FAKE_KEY})
        self.assertEqual(result.returncode, 2)
        self.assertIn("private key", result.stderr)

    def test_blocks_token_in_edit_new_string(self):
        result = self.run_hook(
            "Edit",
            {"file_path": self.kb("products/x/README.md"), "old_string": "TODO", "new_string": f"token {FAKE_TOKEN}", "replace_all": False},
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("GitHub token", result.stderr)

    def test_blocks_token_in_multiedit(self):
        edits = [{"old_string": "a", "new_string": "fine"}, {"old_string": "b", "new_string": FAKE_TOKEN}]
        result = self.run_hook("MultiEdit", {"file_path": self.kb("company/x.md"), "edits": edits})
        self.assertEqual(result.returncode, 2)

    def test_stderr_never_echoes_the_secret(self):
        result = self.run_hook("Write", {"file_path": self.kb("company/x.md"), "content": FAKE_TOKEN})
        self.assertEqual(result.returncode, 2)
        self.assertNotIn(FAKE_TOKEN, result.stderr)

    def test_relative_path_is_resolved_against_cwd(self):
        result = self.run_hook("Write", {"file_path": "knowledge/company/x.md", "content": FAKE_TOKEN})
        self.assertEqual(result.returncode, 2)

    def test_dotdot_back_into_kb_is_still_kb(self):
        path = str(self.root / "scripts" / ".." / "knowledge" / "company" / "x.md")
        result = self.run_hook("Write", {"file_path": path, "content": FAKE_TOKEN})
        self.assertEqual(result.returncode, 2)

    # Outside the KB, secret scanning doesn't apply (other guards cover code).

    def test_allows_secret_like_text_outside_kb(self):
        result = self.run_hook("Write", {"file_path": str(self.root / "scripts" / "tests" / "t.py"), "content": FAKE_TOKEN})
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_dotdot_out_of_kb_is_not_kb(self):
        path = str(self.root / "knowledge" / ".." / "notes.md")
        result = self.run_hook("Write", {"file_path": path, "content": FAKE_TOKEN})
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_ignores_other_tools(self):
        result = self.run_hook("Bash", {"command": f"echo {FAKE_TOKEN}"})
        self.assertEqual(result.returncode, 0, result.stderr)

    # The analyst writes only raw research.

    def test_analyst_may_write_research(self):
        result = self.run_hook("Write", {"file_path": self.kb("research/2026-10-12-x.md"), "content": "# Note\n"}, agent_type="analyst")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_analyst_blocked_from_curated_kb(self):
        result = self.run_hook("Write", {"file_path": self.kb("products/my-product/README.md"), "content": "# x\n"}, agent_type="analyst")
        self.assertEqual(result.returncode, 2)
        self.assertIn("knowledge/research/", result.stderr)

    def test_analyst_blocked_outside_kb(self):
        result = self.run_hook("Write", {"file_path": str(self.root / "CLAUDE.md"), "content": "# x\n"}, agent_type="analyst")
        self.assertEqual(result.returncode, 2)

    def test_analyst_blocked_from_lookalike_folder(self):
        result = self.run_hook("Write", {"file_path": self.kb("research-curated/x.md"), "content": "# x\n"}, agent_type="analyst")
        self.assertEqual(result.returncode, 2)

    def test_analyst_research_secret_still_blocked(self):
        result = self.run_hook("Write", {"file_path": self.kb("research/x.md"), "content": FAKE_TOKEN}, agent_type="analyst")
        self.assertEqual(result.returncode, 2)

    def test_other_agents_may_write_curated_kb(self):
        result = self.run_hook("Write", {"file_path": self.kb("engineering/README.md"), "content": "# x\n"}, agent_type="cto")
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
