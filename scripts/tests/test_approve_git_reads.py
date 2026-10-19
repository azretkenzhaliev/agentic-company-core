"""Tests for scripts/hooks/approve_git_reads.py, run as Claude Code runs it:
JSON on stdin; an allow decision on stdout approves, no output leaves the
call to the normal permission rules."""

import json
import subprocess
import sys
import unittest
from pathlib import Path

HOOK = Path(__file__).resolve().parents[1] / "hooks" / "approve_git_reads.py"
WT = "workspaces/my-product/.worktrees/RM-001-WS-1"


class ApproveGitReads(unittest.TestCase):
    def decision(self, command, tool_name="Bash"):
        payload = {
            "session_id": "test",
            "cwd": "/tmp",
            "hook_event_name": "PreToolUse",
            "tool_name": tool_name,
            "tool_input": {"command": command},
        }
        result = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload), capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        if not result.stdout.strip():
            return None
        return json.loads(result.stdout)["hookSpecificOutput"]["permissionDecision"]

    def assertApproved(self, command):
        self.assertEqual(self.decision(command), "allow", command)

    def assertNotApproved(self, command):
        self.assertIsNone(self.decision(command), command)

    # What agents run is approved, with or without -C.

    def test_approves_the_reads_agents_run(self):
        for command in [
            f"git -C {WT} status --porcelain",
            f"git -C {WT} log --oneline abc123..def456",
            f"git -C {WT} diff --stat abc123..def456",
            f"git -C {WT} diff origin/main...HEAD",
            f"git -C {WT} show --stat HEAD~1",
            f"git -C {WT} branch --show-current",
            f"git -C {WT} rev-parse HEAD",
            "git -C workspaces/my-product/my-repo fetch origin",
            "git -C workspaces/my-product/my-repo worktree list",
            "git -C /Users/me/agentic-company/workspaces/other-product/other-repo log -5 --format=%h",
            f"  git -C {WT} status  ",
            "git fetch origin",
            "git fetch origin main:refs/remotes/origin/main --prune",
            "git diff",
            "git diff --stat HEAD~1..HEAD",
            "git diff --name-only origin/main...HEAD -- knowledge/",
            "git status --short",
            "git log --oneline -5",
            "git log --stat origin/main..HEAD -- scripts/",
            "git show --stat HEAD",
            "git show HEAD:README.md",
        ]:
            with self.subTest(command=command):
                self.assertApproved(command)

    # Anything between git (or the path) and the subcommand is not.

    def test_inserted_global_options_are_not_approved(self):
        for command in [
            f"git -C {WT} -c core.pager=cat log --oneline -1",
            f"git -C {WT} -c core.fsmonitor=true status",
            f"git -C {WT} --config-env=core.pager=X log",
            f"git -C {WT} --exec-path=/tmp log",
            f"git -C {WT} --no-pager log",
            f"git -C {WT} -p log",
            f"git -C {WT} -C other status",
            "git -C -c status",
            "git -c core.pager=cat diff",
            "git -c protocol.ext.allow=always fetch origin",
            "git --no-pager diff",
            "git -c core.pager=cat log",
            "git -p show HEAD",
            "git --git-dir=/tmp/x fetch origin",
        ]:
            with self.subTest(command=command):
                self.assertNotApproved(command)

    def test_shell_tricks_are_not_approved(self):
        for command in [
            f'git -C {WT} "-c" core.pager=cat log',
            f"git -C {WT} '-c' core.pager=cat log",
            f"git -C {WT} \\-c core.pager=cat log",
            f"git -C {WT} {{-c,core.pager=cat}} log",
            f"git -C {WT} status; rm -rf /",
            f"git -C {WT} status && touch x",
            f"git -C {WT} log | sh",
            f"git -C {WT} log > out.txt",
            f"git -C {WT} log $(touch x)",
            f"git -C {WT} log `touch x`",
            f"git -C {WT} log\ntouch x",
            f"git -C {WT}\tstatus",
            f"git -C {WT} log -- *",
            "git diff > out.txt",
            "git fetch origin; touch x",
            'git fetch "--upload-pack=touch x" origin',
        ]:
            with self.subTest(command=command):
                self.assertNotApproved(command)

    # Options that run programs or write files are not, even abbreviated.

    def test_command_running_and_file_writing_options_are_not_approved(self):
        for command in [
            "git -C workspaces/x/y fetch --upload-pack=touch origin",
            "git -C workspaces/x/y fetch --upload-pack touch origin",
            "git -C workspaces/x/y fetch --upload-pa=touch origin",
            "git fetch --upload-pack=touch origin",
            "git fetch --upload-p touch origin",
            "git fetch --up=touch origin",
            f"git -C {WT} diff --output=/tmp/x",
            f"git -C {WT} log --outp=/tmp/x",
            "git diff --output=/tmp/x HEAD",
            "git diff --output /tmp/x HEAD",
            "git diff --outpu=/tmp/x",
            f"git -C {WT} diff --ext-diff",
            "git diff --ext-diff",
            "git diff --ext",
            "git log --output=/tmp/x -1",
            "git log --outp=/tmp/x -1",
            "git log --ext-diff -1",
            "git show --output=/tmp/x HEAD",
            "git show --output /tmp/x HEAD",
            "git show --ext-diff HEAD",
            "git show --ext-d HEAD",
        ]:
            with self.subTest(command=command):
                self.assertNotApproved(command)

    def test_remote_helper_urls_are_not_approved(self):
        for command in [
            "git fetch ext::sh",
            "git fetch fd::3",
            "git -C workspaces/x/y fetch evil::/tmp/repo main",
        ]:
            with self.subTest(command=command):
                self.assertNotApproved(command)

    def test_similar_safe_options_still_pass(self):
        self.assertApproved(f"git -C {WT} log --oneline -1")
        self.assertApproved(f"git -C {WT} diff --output-indicator-new=+ HEAD")
        self.assertApproved(f"git -C {WT} log -c -1")
        self.assertApproved("git diff --no-ext-diff HEAD")
        self.assertApproved("git fetch --no-upload-pack origin")

    def test_other_subcommands_and_forms_are_not_approved(self):
        for command in [
            f"git -C {WT} push origin main",
            f"git -C {WT} commit -m x",
            f"git -C {WT} worktree add ../x",
            f"git -C {WT} worktree",
            f"git -C {WT} config core.pager cat",
            f"git -C {WT}",
            "git",
            "git -C",
            "git push origin main",
            "git pull",
            "git clone ext::sh x",
            f"GIT_PAGER=cat git -C {WT} log",
            f"git -C {WT} STATUS",
            "gitx diff",
        ]:
            with self.subTest(command=command):
                self.assertNotApproved(command)

    def test_other_tools_and_bad_input_get_no_decision(self):
        self.assertIsNone(self.decision(f"git -C {WT} status", tool_name="Read"))
        result = subprocess.run([sys.executable, str(HOOK)], input="not json", capture_output=True, text=True, timeout=30)
        self.assertEqual((result.returncode, result.stdout), (0, ""))


if __name__ == "__main__":
    unittest.main()
