"""Tests for scripts/hooks/background_bash.py, through guard_marketing_tools.py as Claude Code runs it (JSON on stdin,
exit 2 plus stderr to block, exit 0 to allow): a subagent's Bash call with run_in_background is refused; the main
session's isn't."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HOOK = Path(__file__).resolve().parents[1] / "hooks" / "guard_marketing_tools.py"
SUBAGENTS = ["cto", "staff-engineer", "senior-engineer", "code-reviewer", "design-reviewer", "ux-expert",
             "platform-engineer", "cmo", "content-producer", "reel-analyst", "trend-researcher", "general-purpose"]


class BackgroundBash(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()

    def tearDown(self):
        self.tmp.cleanup()

    def run_hook(self, tool_input, agent_type=None, agent_id=None):
        payload = {"session_id": "test", "cwd": str(self.root), "hook_event_name": "PreToolUse",
                   "tool_name": "Bash", "tool_input": tool_input}
        if agent_type:
            payload["agent_type"] = agent_type
        if agent_id:
            payload["agent_id"] = agent_id
        return subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload), capture_output=True, text=True,
                              env=dict(os.environ, CLAUDE_PROJECT_DIR=str(self.root)), timeout=30)

    def test_every_subagent_is_refused_with_the_rule_and_the_foreground_pattern(self):
        for agent_type in SUBAGENTS:
            with self.subTest(agent_type=agent_type):
                result = self.run_hook({"command": "bun test x.test.ts", "run_in_background": True},
                                       agent_type, "a1b2c3d4e5f6a7b8c")
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn("run_in_background", result.stderr)
                self.assertIn('"Wait in the foreground"', result.stderr)
                self.assertIn("<command> > <log> 2>&1; echo $? > <rc>", result.stderr)
                self.assertIn("timeout: 175000", result.stderr)
                self.assertEqual(result.stdout, "")  # no allow, even for a marketing role's normal command

    def test_a_subagent_with_no_agent_type_is_refused(self):
        result = self.run_hook({"command": "sleep 1", "run_in_background": True}, agent_id="a1b2c3")
        self.assertEqual(result.returncode, 2)

    def test_any_value_but_false_is_refused(self):
        for value in ("true", 1, "yes"):
            with self.subTest(value=value):
                result = self.run_hook({"command": "ls", "run_in_background": value}, "senior-engineer", "a1")
                self.assertEqual(result.returncode, 2)

    def test_a_subagents_foreground_call_passes(self):
        for tool_input in ({"command": "ls"}, {"command": "ls", "run_in_background": False},
                           {"command": "ls", "run_in_background": None}, {"command": "ls", "timeout": 175000}):
            with self.subTest(tool_input=tool_input):
                result = self.run_hook(tool_input, "senior-engineer", "a1b2c3")
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_the_forms_its_message_names_pass(self):
        # the refused call, redone once in the form the message spells out
        refused = self.run_hook({"command": "ls", "run_in_background": True}, "senior-engineer", "a1b2c3")
        self.assertEqual(refused.returncode, 2)
        for command in ("ls > /tmp/o/log 2>&1; echo $? > /tmp/o/rc",
                        "until [ -e /tmp/o/rc ] || [ $SECONDS -ge 170 ]; do sleep 5; done; cat /tmp/o/rc 2>/dev/null "
                        "|| echo running"):
            with self.subTest(command=command):
                result = self.run_hook({"command": command, "timeout": 175000}, "senior-engineer", "a1b2c3")
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_the_main_session_keeps_its_background_watchers(self):
        # The CEO (settings' "agent": "ceo"), the CTO's escape hatch (claude --agent cto) and a plain session have no
        # agent_id.
        for agent_type in ("ceo", "cto", None):
            with self.subTest(agent_type=agent_type):
                result = self.run_hook({"command": "until false; do sleep 60; done", "run_in_background": True},
                                       agent_type)
                self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
