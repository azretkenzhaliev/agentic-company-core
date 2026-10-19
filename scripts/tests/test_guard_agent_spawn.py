"""Tests for scripts/hooks/guard_agent_spawn.py, run as Claude Code runs it:
JSON on stdin, exit 2 plus stderr to block, exit 0 to allow."""

import json
import subprocess
import sys
import unittest
from pathlib import Path

HOOK = Path(__file__).resolve().parents[1] / "hooks" / "guard_agent_spawn.py"


class GuardAgentSpawn(unittest.TestCase):
    def run_hook(self, subagent_type, agent_type=None, tool_name="Agent"):
        tool_input = {"description": "x", "prompt": "y"}
        if subagent_type is not None:
            tool_input["subagent_type"] = subagent_type
        payload = {
            "session_id": "test",
            "cwd": "/tmp",
            "hook_event_name": "PreToolUse",
            "tool_name": tool_name,
            "tool_input": tool_input,
        }
        if agent_type:
            payload["agent_type"] = agent_type
        return subprocess.run(
            [sys.executable, str(HOOK)],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            timeout=30,
        )

    def assertAllowed(self, result):
        self.assertEqual(result.returncode, 0, result.stderr)

    def assertBlocked(self, result):
        self.assertEqual(result.returncode, 2)
        self.assertIn("Blocked", result.stderr)

    # The CEO spawns only the CTO and the analyst.

    def test_ceo_may_spawn_cto_and_analyst(self):
        self.assertAllowed(self.run_hook("cto", "ceo"))
        self.assertAllowed(self.run_hook("analyst", "ceo"))

    def test_ceo_may_not_skip_the_cto(self):
        for target in ["staff-engineer", "senior-engineer", "code-reviewer", "design-reviewer", "general-purpose"]:
            with self.subTest(target=target):
                self.assertBlocked(self.run_hook(target, "ceo"))

    def test_ceo_may_not_spawn_the_default_agent(self):
        result = self.run_hook(None, "ceo")
        self.assertBlocked(result)
        self.assertIn("cto, analyst", result.stderr)

    def test_old_tool_name_task_is_guarded_too(self):
        self.assertBlocked(self.run_hook("staff-engineer", "ceo", tool_name="Task"))

    def test_case_and_spaces_are_ignored(self):
        self.assertAllowed(self.run_hook(" CTO ", "ceo"))

    # The CTO and Staff spawn their own reports, whoever started the session.

    def test_cto_may_spawn_its_reports(self):
        for target in ["staff-engineer", "senior-engineer", "code-reviewer"]:
            with self.subTest(target=target):
                self.assertAllowed(self.run_hook(target, "cto"))

    def test_cto_may_not_spawn_outside_its_reports(self):
        for target in ["design-reviewer", "cto", "analyst", "general-purpose", "fork"]:
            with self.subTest(target=target):
                self.assertBlocked(self.run_hook(target, "cto"))

    def test_staff_may_spawn_its_reports(self):
        for target in ["design-reviewer", "senior-engineer", "code-reviewer"]:
            with self.subTest(target=target):
                self.assertAllowed(self.run_hook(target, "staff-engineer"))

    def test_staff_may_not_spawn_another_staff_or_upward(self):
        for target in ["staff-engineer", "cto", "general-purpose"]:
            with self.subTest(target=target):
                self.assertBlocked(self.run_hook(target, "staff-engineer"))

    # Everyone else is not limited by this hook.

    def test_plain_session_is_not_limited(self):
        self.assertAllowed(self.run_hook("staff-engineer"))
        self.assertAllowed(self.run_hook("general-purpose"))

    def test_other_tools_are_ignored(self):
        self.assertAllowed(self.run_hook("staff-engineer", "ceo", tool_name="Read"))

    def test_bad_json_is_allowed(self):
        result = subprocess.run([sys.executable, str(HOOK)], input="not json", capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
