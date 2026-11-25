"""The cmo's one capacity_scan form in scripts/hooks/marketing_bash.py: it runs
`python3 scripts/capacity_scan.py --mac`, word for word, for its load hold (cmo.md, "The load hold"), and nothing else
of that script; no other marketing agent runs it."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HOOKS = Path(__file__).resolve().parents[1] / "hooks"
sys.path.insert(0, str(HOOKS))
from marketing_bash import bash_reason  # noqa: E402

SCAN = "python3 scripts/capacity_scan.py --mac"


class CmoScan(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = str(Path(folder.name).resolve())
        (Path(self.root) / "company.json").write_text('{"integrations": {"marketing": {"no_prompts": ["work"]}}}')

    def test_the_cmo_runs_the_mac_line(self):
        self.assertIsNone(bash_reason(SCAN, "cmo", self.root, self.root))
        self.assertIsNone(bash_reason("ls | tail -1", "cmo", self.root, self.root))  # lists stay fine for the rest

    def test_only_as_the_whole_command(self):  # the call's exit code is the scan's
        for command in [f"{SCAN} | tail -1", f"{SCAN} || true", f"{SCAN} && echo ok", f"{SCAN}; ls", f"ls; {SCAN}",
                        f"cd . && {SCAN}", f"{SCAN}\nls", f"python3 {self.root}/scripts/capacity_scan.py --mac | cat"]:
            with self.subTest(command=command):
                self.assertIn("runs only as the whole command", bash_reason(command, "cmo", self.root, self.root))

    def test_only_the_mac_form(self):
        for command in ["python3 scripts/capacity_scan.py", "python3 scripts/capacity_scan.py --stalled",
                        "python3 scripts/capacity_scan.py --mac --stalled", "python3 scripts/capacity_scan.py --mac x",
                        "python3 scripts/capacity_scan.py --mac=1", "python3 scripts/capacity_scan.py -h",
                        "python3 -I scripts/capacity_scan.py --mac", "python3 scripts/capacity_scan.py --mac > x.log",
                        "python3 scripts/capacity_scan.py --mac; echo $?"]:
            with self.subTest(command=command):
                self.assertIsNotNone(bash_reason(command, "cmo", self.root, self.root))

    def test_no_other_marketing_agent_runs_it(self):
        for agent in ["content-producer", "content-reviewer", "performance-analyst", "reel-analyst"]:
            with self.subTest(agent=agent):
                self.assertIsNotNone(bash_reason(SCAN, agent, self.root, self.root))

    def run_guard(self, agent):
        payload = {"session_id": "test", "cwd": self.root, "hook_event_name": "PreToolUse", "tool_name": "Bash",
                   "tool_input": {"command": SCAN}, "agent_type": agent, "agent_id": "a1"}
        env = {k: v for k, v in os.environ.items() if k != "CLAUDE_CONFIG_DIR"}
        env["CLAUDE_PROJECT_DIR"] = self.root
        return subprocess.run([sys.executable, str(HOOKS / "guard_marketing_tools.py")], input=json.dumps(payload),
                              env=env, capture_output=True, text=True, timeout=30)

    def test_through_the_hook_the_cmos_scan_is_approved(self):  # as Claude Code runs it, with no_prompts
        result = self.run_guard("cmo")
        self.assertEqual(result.returncode, 0, result.stderr)
        decision = json.loads(result.stdout)["hookSpecificOutput"]
        self.assertEqual((decision["hookEventName"], decision["permissionDecision"]), ("PreToolUse", "allow"))

    def test_through_the_hook_the_producers_is_refused(self):
        result = self.run_guard("content-producer")
        self.assertEqual(result.returncode, 2)
        self.assertIn("scripts/capacity_scan.py is for the cmo", result.stderr)


if __name__ == "__main__":
    unittest.main()
