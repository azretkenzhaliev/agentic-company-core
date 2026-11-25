"""Tests for scripts/hooks/bounded_wait.py, through guard_marketing_tools.py as Claude Code runs it (JSON on stdin,
exit 2 plus stderr to block, exit 0 to allow): an engineering subagent's `while` or `until` wait with no $SECONDS
bound is refused, with the bounded form named."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HOOKS = Path(__file__).resolve().parents[1] / "hooks"
HOOK = HOOKS / "guard_marketing_tools.py"
sys.path.insert(0, str(HOOKS))

import bounded_wait  # noqa: E402

ENGINEERING = ["cto", "staff-engineer", "senior-engineer", "code-reviewer", "design-reviewer", "ux-expert"]
OTHERS = ["platform-engineer", "critic", "analyst", "general-purpose"]

REFUSED = [  # each sleeps, and its test never reads SECONDS
    "until [ -e /tmp/x.rc ]; do sleep 5; done; cat /tmp/x.rc",
    "while true; do sleep 30; done",
    "until gh pr checks 18 --repo o/r --required; do sleep 30; done",
    "while ! pg_isready -h localhost -p 5433; do\n  sleep 1\ndone",
    "while sleep 5; do test -e /tmp/x.rc && break; done",  # the sleep in the test
    "cd /w && sh scripts/test-db.sh up x && until docker exec x pg_isready; do sleep 2; done",
    "bash -c 'until [ -e /tmp/x.rc ]; do sleep 5; done'",  # inside quotes as typed
    "if [ -d /w ]; then while [ ! -e /tmp/x ]; do sleep 1; done; fi",
    # an inner loop that never ends holds a bounded outer one
    "while [ $SECONDS -lt 170 ]; do until [ -e /tmp/x ]; do sleep 1; done; done",
    "i=0; while [ $i -lt 30 ]; do i=$((i+1)); sleep 5; done",  # a count isn't a time bound
    "while true; do [ $SECONDS -ge 170 ] && break; sleep 5; done",  # the bound goes in the test
    # the sleep after a nested loop's `done`
    "while true; do for i in 1; do :; done; sleep 5; done",
    "until [ -n x ]; do for n in 1 2; do mkdir d && break; done; sleep 3; done",
    "until [ -e x ]; do while read l; do echo; done < f; sleep 5; done",
    "until [ -e x ]\ndo\n  for i in 1 2\n  do\n    echo $i\n  done\n  sleep 5\ndone",
]
ALLOWED = [
    "until [ -e /tmp/x.rc ] || [ $SECONDS -ge 170 ]; do sleep 5; done; cat /tmp/x.rc 2>/dev/null || echo running",
    "until grep -q '\"name\":\"SubagentHandback\",\"input\"' /tmp/o.output || [ $SECONDS -ge 170 ]; do sleep 5; done",
    "until [ $SECONDS -ge 150 ]; do sleep 5; done",
    "while [ ${SECONDS} -lt 170 ] && ! [ -e /tmp/x ]; do sleep 5; done",
    "while (( SECONDS < 170 )); do sleep 5; done",
    "SECONDS=0; until [ -e /tmp/x ] || [ \"$SECONDS\" -ge 170 ]; do\n  sleep 5\ndone",
    "git log --oneline | while read line; do echo \"$line\"; done",  # no sleep: not a wait
    "for i in 1 2 3; do sleep 1; done",
    "sleep 3",
    "grep -n 'until [ -e' cto.md",
    "echo wait until it is done",
    "rg 'while true; do' scripts/",  # names a loop, no `done`
    "bun test x.test.ts > /tmp/x.log 2>&1; echo $? > /tmp/x.rc",
    "gh pr checks 18 --repo o/r --required --watch",
    "python3 -c 'while True: pass'",
    "git log --until=2026-01-16 --oneline",
    "while read l; do echo do it, then done; done < f; sleep 5",  # words in the body, a sleep after the loop
    "until [ -e x ] || [ $SECONDS -ge 170 ]; do for i in 1; do :; done; sleep 5; done",
]


class Unbounded(unittest.TestCase):
    def test_each_refused_form(self):
        for command in REFUSED:
            with self.subTest(command=command):
                self.assertIn(bounded_wait.unbounded(command), ("while", "until"))

    def test_each_allowed_form(self):
        for command in ALLOWED:
            with self.subTest(command=command):
                self.assertIsNone(bounded_wait.unbounded(command))

    def test_the_message_names_the_loop_and_the_bounded_forms(self):
        reason = bounded_wait.wait_reason({"tool_name": "Bash", "agent_id": "a1", "agent_type": "cto",
                                           "tool_input": {"command": REFUSED[0]}})
        self.assertIn("this `until` loop sleeps, and its test never reads $SECONDS", reason)
        self.assertIn("`until <your test> || [ $SECONDS -ge 170 ]; do sleep 5; done`", reason)
        self.assertIn("`until [ -e <rc> ] || [ $SECONDS -ge 170 ]; do sleep 5; done; cat <rc> 2>/dev/null || echo "
                      "running`", reason)
        self.assertIn("isn't a permission refusal", reason)
        for form in ("until <your test> || [ $SECONDS -ge 170 ]; do sleep 5; done",
                     "until [ -e <rc> ] || [ $SECONDS -ge 170 ]; do sleep 5; done; cat <rc> 2>/dev/null || echo running"):
            self.assertIsNone(bounded_wait.unbounded(form))

    def test_cto_md_s_own_wait_forms_pass(self):
        text = (HOOKS.parents[1] / ".claude" / "agents" / "engineering" / "cto.md").read_text(encoding="utf-8")
        forms = [line.strip().strip("`") for line in text.splitlines() if line.strip().startswith("`until ")]
        self.assertGreaterEqual(len(forms), 2, forms)
        for form in forms:
            with self.subTest(form=form):
                self.assertIsNone(bounded_wait.unbounded(form))


class ThroughTheHook(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()

    def tearDown(self):
        self.tmp.cleanup()

    def run_hook(self, command, agent_type=None, agent_id=None, hook=HOOK):
        payload = {"session_id": "test", "cwd": str(self.root), "hook_event_name": "PreToolUse",
                   "tool_name": "Bash", "tool_input": {"command": command}}
        if agent_type:
            payload["agent_type"] = agent_type
        if agent_id:
            payload["agent_id"] = agent_id
        return subprocess.run([sys.executable, str(hook)], input=json.dumps(payload), capture_output=True, text=True,
                              env=dict(os.environ, CLAUDE_PROJECT_DIR=str(self.root)), timeout=30)

    def test_every_engineering_subagent_is_refused(self):
        for agent_type in ENGINEERING:
            with self.subTest(agent_type=agent_type):
                result = self.run_hook(REFUSED[1], agent_type, "a1b2c3d4e5f6a7b8c")
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn("Blocked: a wait with no time bound (scripts/hooks/bounded_wait.py", result.stderr)

    def test_the_bounded_form_runs_for_every_engineering_subagent(self):
        for agent_type in ENGINEERING:
            with self.subTest(agent_type=agent_type):
                result = self.run_hook(ALLOWED[0], agent_type, "a1b2c3d4e5f6a7b8c")
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_the_main_session_and_other_roles_keep_theirs(self):
        for agent_type, agent_id in [(None, None), ("ceo", None), ("cto", None)] + [(a, "a1") for a in OTHERS]:
            with self.subTest(agent_type=agent_type, agent_id=agent_id):
                result = self.run_hook(REFUSED[1], agent_type, agent_id)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_a_broken_module_fails_closed(self):
        hooks = self.root / "hooks"
        shutil.copytree(HOOKS, hooks, ignore=shutil.ignore_patterns("__pycache__"))
        (hooks / "bounded_wait.py").write_text("raise RuntimeError('broken')\n")
        result = self.run_hook("ls", "senior-engineer", "a1", hook=hooks / "guard_marketing_tools.py")
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("bounded_wait.py", result.stderr)
        self.assertIn("fail closed", result.stderr)


if __name__ == "__main__":
    unittest.main()
