"""Tests for scripts/hooks/guard_vercel_cli.py.

Most run the hook as Claude Code runs it (JSON on stdin, exit 2 plus stderr to
block, exit 0 to allow), with its default configuration: no team may promote,
and no product is marked Git-only. The scope and folder rules are tested by
calling refusal() with the configuration patched, as a product would set it."""

import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

HOOKS = Path(__file__).resolve().parents[1] / "hooks"
HOOK = HOOKS / "guard_vercel_cli.py"
sys.path.insert(0, str(HOOKS))

import guard_vercel_cli as guard  # noqa: E402

COMPANY = "/Users/me/agentic-company"
GIT_ONLY_CLONE = f"{COMPANY}/workspaces/git-product/repo"
GIT_ONLY_WORKTREE = f"{COMPANY}/workspaces/git-product/.worktrees/RM-002-WS-1"
OTHER_CLONE = f"{COMPANY}/workspaces/other-product/repo"
ROLLBACK = "--scope rollback-team"


class GuardVercelCli(unittest.TestCase):
    def run_hook(self, command, agent_type="cto", tool_name="Bash", cwd="/tmp"):
        payload = {
            "session_id": "test",
            "cwd": cwd,
            "hook_event_name": "PreToolUse",
            "tool_name": tool_name,
            "tool_input": {"command": command},
        }
        if agent_type:
            payload["agent_type"] = agent_type
        return subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload), capture_output=True, text=True,
                              timeout=30)

    def assertAllowed(self, command, **kwargs):
        result = self.run_hook(command, **kwargs)
        self.assertEqual(result.returncode, 0, f"{command}: {result.stderr}")

    def assertBlocked(self, command, **kwargs):
        result = self.run_hook(command, **kwargs)
        self.assertEqual(result.returncode, 2, command)
        self.assertIn("Blocked", result.stderr)

    # Deploys from the CLI are refused for every agent: products deploy through Git.

    def test_deploys_are_refused(self):
        for command in [
            "vercel deploy",
            "vercel",
            "vercel --prod",
            "vercel --yes",
            "vercel deploy --prod --scope my-team",
            "vercel deploy --cwd /tmp/export --scope my-team",
            "vercel --scope my-team deploy",
            "vercel -S my-team --prod",
            "vercel -e NODE_ENV=production",
            "vercel .",
            "vercel ./apps/web",
        ]:
            with self.subTest(command=command):
                self.assertBlocked(command)

    def test_redeploy_and_link_are_refused(self):
        for command in [
            "vercel redeploy https://app-abc.vercel.app --scope my-team",
            "vercel link --yes --project app --scope my-team",
            "vercel --scope=my-team link",
        ]:
            with self.subTest(command=command):
                self.assertBlocked(command)

    def test_promote_is_refused_by_default(self):
        for command in ["vercel promote dpl_123", "vercel promote dpl_123 --scope my-team"]:
            with self.subTest(command=command):
                self.assertBlocked(command)

    # However vercel is started.

    def test_wrappers_and_chains_are_seen_through(self):
        for command in [
            "npx vercel deploy",
            "npx --yes vercel@62.1.0 --prod",
            "bunx vercel deploy",
            "pnpm dlx vercel deploy",
            "vc deploy",
            "/Users/me/.bun/bin/vercel deploy",
            "VERCEL_ORG_ID=x VERCEL_PROJECT_ID=y vercel deploy",
            "env FOO=1 vercel --prod",
            "cd apps/web && vercel deploy",
            "vercel ls --scope my-team; vercel --prod",
            "git status\nvercel deploy",
            "bash -c 'vercel deploy --prod'",
            "echo $(vercel deploy)",
            "time vercel deploy",
        ]:
            with self.subTest(command=command):
                self.assertBlocked(command)

    # Reads and runbook steps still run.

    def test_reads_are_allowed(self):
        for command in [
            "vercel ls app --scope my-team",
            "vercel ls app --scope my-team | head -8",
            "vercel inspect https://app-abc.vercel.app --scope my-team",
            "vercel env ls --scope my-team",
            "vercel env add CRON_SECRET preview --git-branch main --sensitive --project app --scope my-team --yes",
            "vercel api /v9/projects/app --scope my-team",
            "vercel project ls --scope my-team",
            "vercel rollback status app --scope my-team",
            "vercel alias ls --scope my-team",
            "vercel build --prod",
            "vercel --version",
            "vercel whoami",
        ]:
            with self.subTest(command=command):
                self.assertAllowed(command)

    def test_mentions_that_dont_run_vercel_are_allowed(self):
        for command in [
            'grep -rn "vercel deploy" knowledge/',
            "rg vercel apps/web",
            'git commit -m "no vercel deploy"',
            "echo vercel deploy",
            "cat vercel.json",
        ]:
            with self.subTest(command=command):
                self.assertAllowed(command)

    # Only agent sessions are limited.

    def test_every_agent_is_limited(self):
        for agent in ["ceo", "cto", "staff-engineer", "senior-engineer", "general-purpose"]:
            with self.subTest(agent=agent):
                self.assertBlocked("vercel deploy --prod", agent_type=agent)

    def test_plain_session_is_not_limited(self):
        self.assertAllowed("vercel deploy --prod", agent_type=None)

    def test_other_tools_are_ignored(self):
        self.assertAllowed("vercel deploy", tool_name="Read")

    def test_bad_json_is_allowed(self):
        result = subprocess.run([sys.executable, str(HOOK)], input="not json", capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0)


class ConfiguredScopes(unittest.TestCase):
    """One team rolls back with `vercel promote`; another product changes production only through Git."""

    def setUp(self):
        for name, value in [("PROMOTE_SCOPES", {"rollback-team"}), ("GIT_ONLY_SCOPES", {"git-team"}),
                            ("GIT_ONLY_DIRS", {"git-product"})]:
            patcher = mock.patch.object(guard, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def assertRefused(self, command, cwd="/tmp"):
        self.assertIsNotNone(guard.refusal(command, cwd), f"{command} in {cwd}")

    def assertNotRefused(self, command, cwd="/tmp"):
        self.assertIsNone(guard.refusal(command, cwd), f"{command} in {cwd}")

    def test_promote_runs_only_with_a_configured_scope(self):
        for command in [f"vercel promote dpl_123 {ROLLBACK} --yes", "vercel promote dpl_123 --scope=rollback-team",
                        "vercel -S rollback-team promote dpl_123"]:
            with self.subTest(command=command):
                self.assertNotRefused(command)
        for command in ["vercel promote dpl_123", "vercel promote dpl_123 --scope git-team",
                        "vercel promote dpl_123 --scope=other-team"]:
            with self.subTest(command=command):
                self.assertRefused(command)

    def test_git_only_scope_refuses_rollback_alias_writes_and_rolling_release(self):
        for command in [
            "vercel rollback dpl_123 --scope git-team --yes",
            "vercel rollback --scope=git-team",
            "vercel -S GIT-TEAM rollback dpl_123",
            "vercel alias set https://app-abc.vercel.app staging.example.com --scope git-team",
            "vercel alias rm staging.example.com --scope git-team --yes",
            "vercel alias https://app-abc.vercel.app staging.example.com --scope git-team",
            "vercel ln set https://app-abc.vercel.app staging.example.com --scope git-team",
            "vercel rolling-release start --dpl dpl_123 --scope git-team",
            "vercel rr configure --scope git-team",
        ]:
            with self.subTest(command=command):
                self.assertRefused(command)

    def test_no_scope_from_a_git_only_folder_targets_it(self):
        for cwd in [GIT_ONLY_CLONE, GIT_ONLY_WORKTREE, f"{GIT_ONLY_CLONE}/apps/web"]:
            for command in ["vercel rollback dpl_123", "vercel alias set a.vercel.app b.example.com", "vercel rr start"]:
                with self.subTest(cwd=cwd, command=command):
                    self.assertRefused(command, cwd)
        for command in [
            "cd workspaces/git-product/repo && vercel rollback dpl_123",
            "vercel rollback dpl_123 --cwd workspaces/git-product/repo",
            "vercel --cwd=workspaces/git-product/.worktrees/RM-002-WS-1 alias set a b",
        ]:
            with self.subTest(command=command):
                self.assertRefused(command, COMPANY)

    def test_other_products_rollback_and_reads_still_run(self):
        for cwd in ["/tmp", COMPANY, OTHER_CLONE, GIT_ONLY_CLONE]:
            for command in [
                f"vercel rollback dpl_123 {ROLLBACK} --yes",
                f"vercel rollback status app {ROLLBACK}",
                f"vercel promote dpl_123 {ROLLBACK} --yes",
                "vercel alias ls --scope git-team",
                "vercel rollback status app --scope git-team",
            ]:
                with self.subTest(cwd=cwd, command=command):
                    self.assertNotRefused(command, cwd)
        for command in ["vercel rollback dpl_123", "vercel alias set a.vercel.app b.example.com", "vercel rr start"]:
            with self.subTest(command=command):
                self.assertNotRefused(command, OTHER_CLONE)


if __name__ == "__main__":
    unittest.main()
