"""The repo's own .claude/settings.json: which hook runs on which tool, that a guard that fails blocks, what no agent may
do, and what runs without asking. A guard that isn't wired here holds nothing."""

import json
import os
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SETTINGS = ROOT / ".claude" / "settings.json"
PREFIX = "${CLAUDE_PROJECT_DIR}/"
# Each guard with the tools it must run on, and tools it needn't.
GUARDS = {
    "guard_kb_write.py": (["Write", "Edit", "MultiEdit", "NotebookEdit", "Bash"], ["Read"]),
    "guard_agent_spawn.py": (["Agent", "Task"], ["Bash"]),
    "guard_agent_control.py": (["SendMessage", "TaskStop"], ["Agent"]),
    "guard_marketing_tools.py": (["Bash", "mcp__claude_ai_Gmail__send_message", "mcp__claude_ai_Neon__update_branch",
                                  "mcp__metricool__createScheduledPost", "mcp__telegram__list_messages"], ["Read"]),
    "guard_neon_sql.py": (["mcp__claude_ai_Neon__run_sql", "mcp__claude_ai_Neon__run_sql_transaction",
                           "mcp__neon__run_sql", "mcp__NEON__run_sql"], ["mcp__claude_ai_Neon__list_projects"]),
    "guard_vercel_cli.py": (["Bash"], []),
    "guard_critic_bash.py": (["Bash"], []),
    "guard_full_suite.py": (["Bash"], []),
}
# They only approve a command, or write a file after a read: failing, they leave the call to the rules.
OTHERS = {"approve_git_reads.py": ["Bash"], "approve_worktree_merge.py": ["Bash"], "approve_pr_ready.py": ["Bash"],
          "notion_approvals_sync.py": ["mcp__claude_ai_Notion__notion-query-data-sources"]}
DENY = {
    "Bash(git push *--force*)", "Bash(git push -f*)", "Bash(git push * -f*)", "Bash(git push * +*)",
    "Bash(git -C * push *--force*)", "Bash(git -C * push -f*)", "Bash(git -C * push * -f*)", "Bash(git -C * push * +*)",
    "Bash(gh pr merge *--admin*)", "Bash(gh pr merge *--auto*)", "Bash(gemini *)",
} | {"mcp__claude_ai_Neon__" + tool for tool in """
    delete_project delete_branch reset_from_parent restore_snapshot finalize_branch_restore delete_snapshot
    set_snapshot_schedule delete_postgres_database delete_postgres_endpoint delete_postgres_role
""".split()}
# Every command and connector tool that runs without asking. A new one is the founder's decision: add it here and in the
# settings, together.
ALLOW = {f"Bash({command} *)" for command in """
    python3 scripts/kb_lint.py, python3 scripts/second_opinion.py, python3 -m unittest, python3 -m pytest, pytest,
    git status, git branch, git rev-parse, git worktree list,
    gh pr view, gh pr list, gh pr diff, gh pr checks, gh pr create, gh pr merge, gh repo view, gh run list, gh run view,
    npm test, npm run test, npm run lint, npm run typecheck, npm run check, npx eslint, npx tsc --noEmit,
    pnpm test, pnpm run test, yarn test, bun run test, bun run lint, bun run e2e, bunx tsc --noEmit
""".replace("\n", " ").split(",") for command in [" ".join(command.split())]} | {"mcp__claude_ai_Neon__" + tool for tool in """
    list_projects describe_project list_branches get_branch get_default_branch describe_branch list_postgres_databases
    get_database_tables describe_table_schema compare_database_schema list_organizations list_postgres_roles list_snapshots
    get_snapshot_schedule list_operations get_operation inspect_database list_docs_resources get_doc_resource
    create_branch run_sql run_sql_transaction
""".split()}
ENV = {"CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS", "SECOND_OPINION_OPENAI_TIER"}



def runs_on(matcher, tool):
    """Whether a hook's matcher takes this tool, as Claude Code reads one: names joined by `|`, else a regex."""
    if re.fullmatch(r"[\w|]+", matcher):
        return tool in matcher.split("|")
    return re.fullmatch(matcher, tool) is not None


class Settings(unittest.TestCase):
    def setUp(self):
        self.text = SETTINGS.read_text(encoding="utf-8")
        self.settings = json.loads(self.text)
        self.entries = [(event, group.get("matcher", ""), hook) for event, groups in self.settings["hooks"].items()
                        for group in groups for hook in group["hooks"]]

    def named(self, name):
        return [(event, matcher, hook) for event, matcher, hook in self.entries if hook["command"].endswith("/" + name)]

    def test_every_hook_is_an_executable_file_of_this_repo_run_without_a_shell(self):
        for _, _, hook in self.entries:
            with self.subTest(command=hook["command"]):
                self.assertEqual(hook["type"], "command")
                self.assertTrue(hook["command"].startswith(PREFIX))
                path = ROOT / hook["command"][len(PREFIX):]
                self.assertTrue(path.is_file(), path)
                self.assertTrue(os.access(path, os.X_OK), path)
                self.assertTrue(path.read_text(encoding="utf-8").startswith("#!/usr/bin/env python3\n"), path)
                self.assertEqual(hook["args"], [])  # run as it is, no shell between
                self.assertGreater(hook["timeout"], 0)
                self.assertIn(path.name, {**GUARDS, **OTHERS})

    def test_each_guard_runs_on_its_tools_and_blocks_when_it_fails(self):
        for name, (tools, others) in GUARDS.items():
            entries = self.named(name)
            for tool in tools:
                with self.subTest(name=name, tool=tool):
                    found = [hook for event, matcher, hook in entries if event == "PreToolUse" and runs_on(matcher, tool)]
                    self.assertEqual(len(found), 1)
                    self.assertEqual(found[0].get("onFailure"), "block")
            for tool in others:
                with self.subTest(name=name, tool=tool):
                    self.assertFalse([hook for _, matcher, hook in entries if runs_on(matcher, tool)])

    def test_the_approvers_and_the_sync_run_on_their_tools(self):
        for name, tools in OTHERS.items():
            for tool in tools:
                with self.subTest(name=name):
                    self.assertEqual(sum(runs_on(matcher, tool) for _, matcher, _ in self.named(name)), 1)

    def test_what_no_agent_may_do_is_denied(self):
        self.assertEqual(DENY - set(self.settings["permissions"]["deny"]), set())

    def test_only_the_listed_commands_and_tools_run_without_asking(self):
        self.assertEqual(set(self.settings["permissions"]["allow"]) - ALLOW, set())

    def test_nothing_else_is_set(self):
        self.assertEqual(set(self.settings) - {"$schema", "agent", "env", "permissions", "hooks"}, set())
        self.assertEqual(set(self.settings["permissions"]), {"allow", "deny"})
        self.assertEqual(set(self.settings.get("env", {})) - ENV, set())

    def test_it_holds_nothing_of_one_machine_or_one_product(self):
        for word in ("/Users/", "/home/", "/private/", "workspaces/", "bypassPermissions"):
            self.assertNotIn(word, self.text)
        for rule in self.settings["permissions"]["allow"] + self.settings["permissions"]["deny"]:
            with self.subTest(rule=rule):
                self.assertNotRegex(rule, r"[( ]/")
        self.assertEqual(self.settings["agent"], "ceo")


if __name__ == "__main__":
    unittest.main()
