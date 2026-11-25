"""Tests for scripts/hooks/guard_critic_bash.py, run as Claude Code runs it:
JSON on stdin, exit 2 plus stderr to block, exit 0 to allow."""

import json
import subprocess
import sys
import unittest
from pathlib import Path

HOOK = Path(__file__).resolve().parents[1] / "hooks" / "guard_critic_bash.py"

SECOND_OPINION = """python3 scripts/second_opinion.py --kind plan --brief "D-20260101-x critic" --file /dev/stdin <<'EOF'
Goal: fewer late orders. The plan: show two dates; $(not run) `not run` > not a file; rm -rf nothing
EOF"""


class GuardCriticBash(unittest.TestCase):
    def run_hook(self, command, agent_type="critic", tool_name="Bash"):
        payload = {"session_id": "test", "cwd": "/tmp", "hook_event_name": "PreToolUse",
                   "tool_name": tool_name, "tool_input": {"command": command}}
        if agent_type:
            payload["agent_type"] = agent_type
        return subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload),
                              capture_output=True, text=True, timeout=30)

    def assertAllowed(self, command):
        result = self.run_hook(command)
        self.assertEqual(result.returncode, 0, f"{command!r}: {result.stderr}")

    def assertBlocked(self, command):
        result = self.run_hook(command)
        self.assertEqual(result.returncode, 2, command)
        self.assertIn("the critic only reads", result.stderr)

    def test_reads_are_allowed(self):
        for command in [
            "cat knowledge/board/directives/D-20260101-x.md",
            "grep -rn 'Gemini' knowledge/board | head -20",
            "grep -n \"foo(\" .claude/agents/executive/ceo.md",
            "find knowledge -name '*.md' -newer CLAUDE.md",
            "ls -la knowledge/research && wc -l knowledge/INDEX.md",
            "git log --oneline -10",
            "git -C workspaces/acme/acme-app show HEAD --stat",
            "git diff main..HEAD -- scripts",
            "gh pr view 12 --json state,url",
            "gh run list --limit 5",
            "tail -5 knowledge/research/README.md 2>/dev/null",
            "cd /repo && git status --short 2>&1",
            "python3 scripts/second_opinion.py --help",
        ]:
            with self.subTest(command=command):
                self.assertAllowed(command)

    def test_second_opinion_packet_on_stdin_is_allowed(self):
        self.assertAllowed(SECOND_OPINION)

    def test_the_gemini_only_form_is_a_flag_and_an_env_prefix_stays_blocked(self):
        flag = SECOND_OPINION.replace("--kind plan", "--only gemini --kind plan")
        self.assertAllowed(flag)
        self.assertAllowed("python3 scripts/second_opinion.py --only gemini --help")
        self.assertBlocked("env -u OPENAI_API_KEY " + SECOND_OPINION)
        self.assertBlocked("env -u OPENAI_API_KEY python3 scripts/second_opinion.py --help")

    def test_writes_are_blocked(self):
        for command in [
            "echo hi > notes.md",
            "cat a >> b",
            "grep x a >| b",
            "cat a 2> err.log",
            "cat a &> out",
            "tee notes.md",
            "cat a | tee notes.md",
            "touch x",
            "rm -rf knowledge",
            "mv a b",
            "cp a b",
            "mkdir out",
            "sed -i s/a/b/ f",
            "printf x > f",
            "cat <<'EOF' > f\nx\nEOF",
            "find . -name x -delete",
            "find . -exec rm {} ;",
            "find . -fprint out",
            "git diff --output=patch.txt",
            "git log --out=x",
            "git grep -O x",
            "git -c core.pager=sh log",
            "git commit -m x",
            "git add .",
            "git checkout main",
            "git push",
            "gh pr merge 12",
            "gh api -X POST repos/x/issues",
            "gh api view -X POST",
            "python3 -c 'open(\"f\", \"w\")'",
            "python3 scripts/kb_lint.py",
        ]:
            with self.subTest(command=command):
                self.assertBlocked(command)

    def test_hidden_commands_are_blocked(self):
        for command in [
            "cat $(rm -rf x)",
            "cat `touch x`",
            "cat a; rm b",
            "cat a && touch b",
            "cat a || touch b",
            "cat a\ntouch b",
            "cat x#; rm y",
            "cat a & touch b",
            "(touch b)",
            "cat <(touch b)",
            "FOO=1 touch b",
            "bash -c 'touch b'",
            "cat 'unbalanced",
        ]:
            with self.subTest(command=command):
                self.assertBlocked(command)

    def test_heredoc_must_end_at_its_last_line(self):
        early_end = SECOND_OPINION.replace("Goal:", "EOF\ntouch b\nGoal:")
        self.assertBlocked(early_end)
        self.assertBlocked(SECOND_OPINION + "\ntouch b")
        self.assertBlocked(SECOND_OPINION.replace("--file /dev/stdin", "--file /dev/stdin; touch b"))
        self.assertBlocked(SECOND_OPINION.replace("<<'EOF'", "<<EOF"))  # unquoted: the shell expands $(...)
        self.assertBlocked(SECOND_OPINION.replace("python3 scripts/second_opinion.py", "python3 other.py"))

    def test_content_reviewer_only_reads_and_may_lint(self):
        for command in ["cat knowledge/marketing/x.md", "python3 tools/marketing/content_lint.py knowledge/marketing/acme",
                        "grep -n Sources knowledge/marketing/acme/content/2026-W05/a.md"]:
            with self.subTest(command=command):
                self.assertEqual(self.run_hook(command, agent_type="content-reviewer").returncode, 0)
        for command in ["echo x > a.md", "python3 tools/marketing/render/png.mjs", "node tools/marketing/render/png.mjs --html a --out b",
                        "python3 scripts/notion_approvals_sync.py --database x --brand acme --week 2026-W05"]:
            with self.subTest(command=command):
                result = self.run_hook(command, agent_type="content-reviewer")
                self.assertEqual(result.returncode, 2)
                self.assertIn("content-reviewer only reads", result.stderr)

    def test_reviewer_reads_what_the_dry_run_needed(self):
        root = str(Path(__file__).resolve().parents[2])
        for command in [f"cd {root}; sed -n 5,120p .claude/skills/content-qa/SKILL.md",
                        "python3 tools/marketing/content_lint.py knowledge/marketing; echo exit $?".replace("$?", "0"),
                        f"python3 {root}/tools/marketing/content_lint.py {root}/knowledge/marketing"]:
            with self.subTest(command=command):
                self.assertEqual(self.run_hook(command, agent_type="content-reviewer").returncode, 0)
        for command in ["sed -i s/a/b/ x.md", "sed -n 'w out.md' x.md", "python3 /tmp/tools/marketing/content_lint.py x"]:
            with self.subTest(command=command):
                self.assertEqual(self.run_hook(command, agent_type="content-reviewer").returncode, 2)

    def test_other_callers_are_not_limited(self):
        for agent_type in [None, "ceo", "analyst", "code-reviewer"]:
            with self.subTest(agent_type=agent_type):
                self.assertEqual(self.run_hook("echo hi > notes.md", agent_type=agent_type).returncode, 0)

    def test_other_tools_are_ignored(self):
        self.assertEqual(self.run_hook("echo hi > notes.md", tool_name="Read").returncode, 0)

    def test_what_it_cant_read_is_refused(self):
        for text in ("not json", "[]", '{"tool_name": "Bash", "agent_type": "critic", "tool_input": [1]}'):
            with self.subTest(text=text):
                result = subprocess.run([sys.executable, str(HOOK)], input=text, capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, 2)
                self.assertIn("couldn't check", result.stderr)


if __name__ == "__main__":
    unittest.main()
