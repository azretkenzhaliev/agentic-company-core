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
        return self.run_payload(payload)

    def run_payload(self, payload):
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
        result = self.run_hook("Write", {"file_path": self.kb("research/2026-01-12-x.md"), "content": "# Note\n"}, agent_type="analyst")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_analyst_blocked_from_curated_kb(self):
        result = self.run_hook("Write", {"file_path": self.kb("products/acme/README.md"), "content": "# x\n"}, agent_type="analyst")
        self.assertEqual(result.returncode, 2)
        self.assertIn("knowledge/research/", result.stderr)

    def test_analyst_blocked_outside_kb(self):
        result = self.run_hook("Write", {"file_path": str(self.root / "CLAUDE.md"), "content": "# x\n"}, agent_type="analyst")
        self.assertEqual(result.returncode, 2)

    def test_analyst_blocked_from_lookalike_folder(self):
        result = self.run_hook("Write", {"file_path": self.kb("research-curated/x.md"), "content": "# x\n"}, agent_type="analyst")
        self.assertEqual(result.returncode, 2)

    def test_analyst_may_edit_the_research_index(self):
        edit = {"file_path": self.kb("research/README.md"), "old_string": "| last |\n", "new_string": "| last |\n| new |\n"}
        result = self.run_hook("Edit", edit, agent_type="analyst")
        self.assertEqual(result.returncode, 0, result.stderr)

    # The ux-expert writes only its KB folder and its screenshot folder.

    def test_ux_expert_may_write_its_two_folders(self):
        for path in [self.kb("engineering/ux/README.md"), self.kb("engineering/ux/audits/demo-2026-01-06-x.md"),
                     str(self.root / "workspaces" / "ux" / "demo" / "2026-01-06-x" / "steps.mjs"),
                     self.kb("Engineering/UX/specs/x.md")]:
            with self.subTest(path=path):
                result = self.run_hook("Write", {"file_path": path, "content": "# x\n"}, agent_type="ux-expert")
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_ux_expert_blocked_everywhere_else(self):
        for path in [self.kb("engineering/README.md"), self.kb("engineering/designs/DD-001-x.md"),
                     self.kb("engineering/ux-2/x.md"), self.kb("marketing/x.md"),
                     str(self.root / "workspaces" / "demo" / "x.md"), str(self.root / "workspaces" / "ux-old" / "x"),
                     str(self.root / ".claude" / "settings.json"), str(self.root / ".claude" / "skills" / "ux-checklist" / "SKILL.md"),
                     str(self.root / "CLAUDE.md"), str(self.root / "tools" / "ux" / "calibration" / "answer-key.json"),
                     "/tmp/ux-expert-x.md"]:
            with self.subTest(path=path):
                result = self.run_hook("Write", {"file_path": path, "content": "# x\n"}, agent_type="ux-expert")
                self.assertEqual(result.returncode, 2)
                self.assertIn("knowledge/engineering/ux/", result.stderr)

    def test_ux_expert_edit_and_relative_paths_are_held_too(self):
        edit = {"file_path": "../README.md", "old_string": "a", "new_string": "b"}
        result = self.run_hook("Edit", edit, agent_type="ux-expert", cwd=self.root / "knowledge" / "engineering")
        self.assertEqual(result.returncode, 2)
        edit = {"file_path": "ux/../ux/README.md", "old_string": "a", "new_string": "b"}
        result = self.run_hook("Edit", edit, agent_type="ux-expert", cwd=self.root / "knowledge" / "engineering")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_ux_expert_still_gets_the_secrets_check(self):
        result = self.run_hook("Write", {"file_path": self.kb("engineering/ux/README.md"), "content": FAKE_TOKEN}, agent_type="ux-expert")
        self.assertEqual(result.returncode, 2)

    def test_analyst_edit_blocked_from_curated_kb(self):
        edit = {"file_path": self.kb("products/acme/README.md"), "old_string": "a", "new_string": "b"}
        result = self.run_hook("Edit", edit, agent_type="analyst")
        self.assertEqual(result.returncode, 2)
        self.assertIn("knowledge/research/", result.stderr)

    def test_analyst_research_secret_still_blocked(self):
        result = self.run_hook("Write", {"file_path": self.kb("research/x.md"), "content": FAKE_TOKEN}, agent_type="analyst")
        self.assertEqual(result.returncode, 2)

    def test_other_agents_may_write_curated_kb(self):
        result = self.run_hook("Write", {"file_path": self.kb("engineering/README.md"), "content": "# x\n"}, agent_type="cto")
        self.assertEqual(result.returncode, 0, result.stderr)

    # Marketing agents write only their own pages; nobody but the sync script writes approvals.

    def write_as(self, agent_type, path):
        return self.run_hook("Write", {"file_path": path, "content": "# x\n"}, agent_type=agent_type)

    def test_reviewer_writes_nothing(self):
        for path in [self.kb("marketing/founder/one/content/2026-W05/x.md"), str(self.root / "workspaces/marketing/x.png"),
                     str(self.root / "notes.md")]:
            with self.subTest(path=path):
                result = self.write_as("content-reviewer", path)
                self.assertEqual(result.returncode, 2)
                self.assertIn("read-only", result.stderr)

    def test_producer_writes_content_pages_and_media(self):
        for path in [self.kb("marketing/founder/one/content/2026-W05/x.md"),
                     self.kb("marketing/demo/content/2027-W05/y.md"),
                     str(self.root / "workspaces/marketing/media/founder/one/2026-W05/slide-1.html")]:
            with self.subTest(path=path):
                self.assertEqual(self.write_as("content-producer", path).returncode, 0)

    def test_producer_blocked_outside_content(self):
        for path in [self.kb("marketing/founder/one/brand-book.md"),
                     self.kb("marketing/founder/one/calendar/2026-W05.md"),
                     self.kb("marketing/content-ideas.md"),
                     str(self.root / "CLAUDE.md"),
                     str(self.root / "workspaces/acme/x.md")]:
            with self.subTest(path=path):
                result = self.write_as("content-producer", path)
                self.assertEqual(result.returncode, 2)
                self.assertIn("content/", result.stderr)

    def test_trend_researcher_writes_only_the_intelligence_folder(self):
        for path in [str(self.root / "workspaces/marketing/intelligence/2026-W06.md"),
                     str(self.root / "workspaces/marketing/intelligence/posts.csv")]:
            with self.subTest(path=path):
                self.assertEqual(self.write_as("trend-researcher", path).returncode, 0)
        for path in [str(self.root / "workspaces/marketing/media/x.png"),
                     str(self.root / "workspaces/marketing/intelligence-2/x.md"),
                     self.kb("marketing/content-ideas.md"),
                     self.kb("research/x.md"),
                     str(self.root / ".claude/settings.json"),
                     str(self.root / "scripts/hooks/trend_reader.py"),
                     str(self.root / "notes.md"),
                     "/tmp/x.md"]:
            with self.subTest(path=path):
                result = self.write_as("trend-researcher", path)
                self.assertEqual(result.returncode, 2)
                self.assertIn("intelligence", result.stderr)

    def test_reel_analyst_writes_only_the_reels_folder(self):
        for path in [str(self.root / "workspaces/marketing/intelligence/reels/AbCdEfGhIjK/breakdown.md"),
                     str(self.root / "workspaces/marketing/intelligence/reels/2026-W05-formats.md")]:
            with self.subTest(path=path):
                self.assertEqual(self.write_as("reel-analyst", path).returncode, 0)
        for path in [str(self.root / "workspaces/marketing/intelligence/posts.csv"),
                     str(self.root / "workspaces/marketing/intelligence/2026-W05.md"),
                     str(self.root / "workspaces/marketing/media/x.png"),
                     self.kb("marketing/content-ideas.md"),
                     str(self.root / ".claude/settings.json"),
                     str(self.root / "tools/marketing/reels/watch.py"),
                     "/tmp/x.md"]:
            with self.subTest(path=path):
                result = self.write_as("reel-analyst", path)
                self.assertEqual(result.returncode, 2)
                self.assertIn("reels/", result.stderr)

    def test_cmo_writes_marketing_pages(self):
        for path in [self.kb("marketing/founder/one/calendar/2026-W05.md"),
                     self.kb("marketing/founder/two/brand-book.md"),
                     self.kb("marketing/voice/hooks.md"),
                     str(self.root / "workspaces/marketing/media/x.png")]:
            with self.subTest(path=path):
                self.assertEqual(self.write_as("cmo", path).returncode, 0)

    def test_cmo_blocked_from_other_owners_pages(self):
        Path(self.kb("marketing/founder/one/brand-book.md")).parent.mkdir(parents=True, exist_ok=True)
        Path(self.kb("marketing/founder/one/brand-book.md")).write_text("x")
        for path in [self.kb("marketing/founder/one/content/2026-W05/x.md"),
                     self.kb("marketing/founder/one/metrics.md"),
                     self.kb("marketing/founder/one/learnings.md"),
                     self.kb("company/org-chart.md"),
                     str(self.root / "CLAUDE.md")]:
            with self.subTest(path=path):
                self.assertEqual(self.write_as("cmo", path).returncode, 2)

    def test_performance_analyst_writes_only_metrics_and_learnings(self):
        for brand in ("founder/one", "founder/two"):
            Path(self.kb(f"marketing/{brand}/brand-book.md")).parent.mkdir(parents=True, exist_ok=True)
            Path(self.kb(f"marketing/{brand}/brand-book.md")).write_text("x")
        for path in [self.kb("marketing/metrics.md"), self.kb("marketing/voice/learnings.md"),
                     self.kb("marketing/founder/one/calendar/metrics.md")]:
            with self.subTest(path=path):
                self.assertEqual(self.write_as("performance-analyst", path).returncode, 2)
        self.assertEqual(self.write_as("cmo", self.kb("marketing/voice/learnings.md")).returncode, 0)
        for path in [self.kb("marketing/founder/one/metrics.md"), self.kb("marketing/founder/two/learnings.md")]:
            with self.subTest(path=path):
                self.assertEqual(self.write_as("performance-analyst", path).returncode, 0)
        for path in [self.kb("marketing/founder/one/brand-book.md"),
                     self.kb("marketing/founder/one/content/2026-W05/metrics.md"),
                     self.kb("marketing/founder/one/approvals/2026-W05.md"),
                     str(self.root / "workspaces/marketing/media/x.png"), self.kb("research/x.md")]:
            with self.subTest(path=path):
                self.assertEqual(self.write_as("performance-analyst", path).returncode, 2)

    def test_no_agent_writes_approvals(self):
        path = self.kb("marketing/founder/one/approvals/2026-W05.md")
        for agent_type in ["ceo", "cmo", "content-producer", "cto"]:
            with self.subTest(agent_type=agent_type):
                result = self.write_as(agent_type, path)
                self.assertEqual(result.returncode, 2)
                self.assertIn("sync script", result.stderr)

    def test_no_agent_writes_the_board_s_answers(self):
        """Only board_desk.py's reader writes knowledge/board/answers/."""
        for agent_type, rel in [("ceo", "board/answers/2026-W07.md"), ("cto", "board/answers/2026-W07.md"),
                                ("platform-engineer", "board/answers/README.md"), ("cmo", "Board/Answers/2026-W07.md"),
                                ("senior-engineer", "board/answers/x/y.md")]:
            with self.subTest(agent_type=agent_type, rel=rel):
                result = self.write_as(agent_type, self.kb(rel))
                self.assertEqual(result.returncode, 2)
                self.assertIn("the Board's own answers", result.stderr)
        payload = {"session_id": "test", "cwd": str(self.root), "hook_event_name": "PreToolUse", "tool_name": "Edit",
                   "agent_id": "a1", "tool_input": {"file_path": self.kb("board/answers/2026-W07.md"), "old_string": "a",
                                                    "new_string": "b"}}
        self.assertEqual(self.run_payload(payload).returncode, 2, "a subagent without agent_type is held too")
        for rel in ["board/answers/2026-W07.md", "board/answers.md", "board/directives/D-20260101-x.md"]:
            with self.subTest(rel=rel):
                self.assertEqual(self.run_hook("Write", {"file_path": self.kb(rel), "content": "# x\n"}).returncode, 0)
        self.assertEqual(self.write_as("ceo", self.kb("board/directives/D-20260101-x.md")).returncode, 0)

    def test_no_agent_writes_the_desk_s_state(self):
        """workspaces/board-desk/ holds the Board's id the reader trusts and the
        desk's Notion ids the Notion guard reads; only board_desk.py writes it."""
        for agent_type, rel in [("ceo", "workspaces/board-desk/reader.json"), ("cmo", "workspaces/board-desk/notion.json"),
                                ("platform-engineer", "Workspaces/Board-Desk/x.json")]:
            with self.subTest(agent_type=agent_type, rel=rel):
                result = self.write_as(agent_type, str(self.root / rel))
                self.assertEqual(result.returncode, 2)
                self.assertIn("the Board desk's state", result.stderr)
        self.assertEqual(self.run_hook("Write", {"file_path": str(self.root / "workspaces/board-desk/notion.json"),
                                                 "content": "{}\n"}).returncode, 0)
        self.assertEqual(self.write_as("ceo", str(self.root / "workspaces/board-desking/x.json")).returncode, 0)

    def test_producer_media_only_not_inbox_or_corpus(self):
        self.assertEqual(self.write_as("content-producer", str(self.root / "workspaces/marketing/media/a/s.html")).returncode, 0)
        for rel in ["workspaces/marketing/inbox/founder/one/2026-W05/voice-note.txt",
                    "workspaces/marketing/corpus/library/text.txt", "workspaces/marketing/spend.jsonl"]:
            with self.subTest(rel=rel):
                self.assertEqual(self.write_as("content-producer", str(self.root / rel)).returncode, 2)

    def test_inbox_is_the_boards_and_corpus_the_cmos(self):
        inbox = str(self.root / "workspaces/marketing/inbox/x.txt")
        for agent_type in ["cmo", "ceo", "content-producer"]:
            with self.subTest(agent_type=agent_type):
                result = self.write_as(agent_type, inbox)
                self.assertEqual(result.returncode, 2)
                self.assertIn("inbox", result.stderr)
        self.assertEqual(self.write_as("cmo", str(self.root / "workspaces/marketing/corpus/library/a.txt")).returncode, 0)

    def test_case_doesnt_get_round_the_rules(self):
        for agent_type, rel in [("cmo", "knowledge/marketing/founder/one/Approvals/2026-W05.md"),
                                ("ceo", "Knowledge/Marketing/founder/one/approvals/2026-W05.md"),
                                ("cmo", "knowledge/marketing/founder/one/Content/2026-W05/x.md"),
                                ("content-producer", "knowledge/marketing/founder/one/Brand-Book.md")]:
            with self.subTest(agent_type=agent_type, rel=rel):
                self.assertEqual(self.write_as(agent_type, str(self.root / rel)).returncode, 2)

    def test_a_media_folder_linked_into_elsewhere_is_still_media(self):
        elsewhere = self.root.parent / (self.root.name + "-elsewhere")
        elsewhere.mkdir()
        try:
            (self.root / "workspaces/marketing").mkdir(parents=True)
            (self.root / "workspaces/marketing/media").symlink_to(elsewhere)
            self.assertEqual(self.write_as("content-producer", str(self.root / "workspaces/marketing/media/a/s.html")).returncode, 0)
        finally:
            (self.root / "workspaces/marketing/media").unlink()
            elsewhere.rmdir()

    def test_plain_session_may_write_approvals(self):
        result = self.run_hook("Write", {"file_path": self.kb("marketing/founder/one/approvals/2026-W05.md"), "content": "# x\n"})
        self.assertEqual(result.returncode, 0, result.stderr)

    # An agent writes only inside its own system worktree.

    def worktree(self, name):
        folder = self.root / ".claude" / "worktrees" / name
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    @staticmethod
    def write_input(tool_name, path):
        return {"Write": {"file_path": path, "content": "x\n"},
                "Edit": {"file_path": path, "old_string": "a", "new_string": "b"},
                "MultiEdit": {"file_path": path, "edits": [{"old_string": "a", "new_string": "b"}]},
                "NotebookEdit": {"notebook_path": path, "new_source": "x = 1"}}[tool_name]

    def test_another_agents_worktree_is_refused(self):
        a, b = self.worktree("agent-a1"), self.worktree("agent-b2")
        for tool_name in ["Write", "Edit", "MultiEdit", "NotebookEdit"]:
            for cwd in [b, b / "scripts", self.root]:
                for path in [str(a / "scripts" / "x.py"), str(a), str(a) + "/"]:  # a file in it, or its root itself
                    with self.subTest(tool_name=tool_name, cwd=cwd, path=path):
                        result = self.run_hook(tool_name, self.write_input(tool_name, path), cwd=cwd)
                        self.assertEqual(result.returncode, 2)
                        self.assertIn("agent-a1", result.stderr)

    def test_own_worktree_passes(self):
        a = self.worktree("agent-a1")
        for tool_name in ["Write", "Edit", "MultiEdit", "NotebookEdit"]:
            for cwd in [a, a / "scripts"]:
                with self.subTest(tool_name=tool_name, cwd=cwd):
                    result = self.run_hook(tool_name, self.write_input(tool_name, str(a / "scripts" / "x.py")), cwd=cwd)
                    self.assertEqual(result.returncode, 0, result.stderr)
        result = self.run_hook("Write", {"file_path": "scripts/x.py", "content": "x\n"}, cwd=a)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_paths_outside_agent_worktrees_are_unaffected(self):
        b = self.worktree("agent-b2")
        for path in [self.root / "scripts" / "x.py", self.root / ".claude" / "worktrees" / "notes.md",
                     self.root / ".claude" / "worktrees-old" / "agent-a1" / "x.py", Path("/tmp/x.md")]:
            for cwd in [b, self.root]:
                with self.subTest(path=path, cwd=cwd):
                    result = self.run_hook("Write", {"file_path": str(path), "content": "x\n"}, cwd=cwd)
                    self.assertEqual(result.returncode, 0, result.stderr)

    def test_dotdot_and_symlinks_into_another_worktree_are_refused(self):
        a, b = self.worktree("agent-a1"), self.worktree("agent-b2")
        (b / "link-to-a").symlink_to(a)
        (self.root / "link-to-a").symlink_to(a)
        (b / "link-to-new").symlink_to(a / "new.py")  # dangling: a file not yet made in a
        (self.root / "link-to-new").symlink_to(a / "new.py")
        for path, cwd in [(str(b / ".." / "agent-a1" / "x.py"), b), ("../agent-a1/x.py", b),
                          (str(b / "link-to-a" / "x.py"), b), (str(self.root / "link-to-a" / "x.py"), b),
                          (str(self.root / "link-to-a" / "x.py"), self.root),
                          (str(b / "link-to-new"), b), ("link-to-new", b), (str(self.root / "link-to-new"), self.root)]:
            with self.subTest(path=path, cwd=cwd):
                result = self.run_hook("Write", {"file_path": path, "content": "x\n"}, cwd=cwd)
                self.assertEqual(result.returncode, 2)
                self.assertIn("agent-a1", result.stderr)
        (self.root / "cwd-link").symlink_to(a)
        result = self.run_hook("Write", {"file_path": str(a / "x.py"), "content": "x\n"}, cwd=self.root / "cwd-link")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_case_doesnt_get_round_the_worktree_rule(self):
        a, b = self.worktree("agent-a1"), self.worktree("agent-b2")
        path = str(self.root / ".Claude" / "Worktrees" / "Agent-A1" / "x.py")
        self.assertEqual(self.run_hook("Write", {"file_path": path, "content": "x\n"}, cwd=b).returncode, 2)
        result = self.run_hook("Write", {"file_path": path, "content": "x\n"}, cwd=a)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_worktree_writes_fail_closed_without_a_usable_cwd(self):
        a = self.worktree("agent-a1")
        base = {"session_id": "test", "hook_event_name": "PreToolUse", "tool_name": "Write",
                "tool_input": {"file_path": str(a / "x.py"), "content": "x\n"}}
        for cwd in [None, "", "agent-a1", 7, str(a) + "\x00"]:  # missing, empty, relative, not a string, unresolvable
            with self.subTest(cwd=cwd):
                result = self.run_payload(base if cwd is None else dict(base, cwd=cwd))
                self.assertEqual(result.returncode, 2)
                self.assertIn("cwd", result.stderr)
        result = self.run_payload(dict(base, cwd=str(a), tool_input={"file_path": str(a / "x\x00.py"), "content": "x\n"}))
        self.assertEqual(result.returncode, 2)
        self.assertIn("can't be resolved", result.stderr)
        result = self.run_payload(dict(base, tool_input={"file_path": str(self.root / "notes.md"), "content": "x\n"}))
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_notebook_edit_gets_the_other_checks_too(self):
        result = self.run_hook("NotebookEdit", {"notebook_path": self.kb("company/x.ipynb"), "new_source": FAKE_TOKEN})
        self.assertEqual(result.returncode, 2)
        result = self.run_hook("NotebookEdit", {"notebook_path": self.kb("products/x.ipynb"), "new_source": "x"},
                               agent_type="analyst")
        self.assertEqual(result.returncode, 2)


    # company.json is a guardrail file: no subagent writes it, and the main session's write is put to the founder.

    def company_write(self, tool_name, tool_input, agent_id=None, agent_type=None, cwd=None):
        payload = {"session_id": "test", "cwd": str(cwd or self.root), "hook_event_name": "PreToolUse",
                   "tool_name": tool_name, "tool_input": tool_input}
        payload.update({k: v for k, v in (("agent_id", agent_id), ("agent_type", agent_type)) if v})
        return self.run_payload(payload)

    def assert_asks(self, result):
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["hookSpecificOutput"]["permissionDecision"], "ask")

    def assert_refused(self, result):
        self.assertEqual(result.returncode, 2)
        self.assertIn("no subagent writes it", result.stderr)

    def assert_no_decision(self, result):
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, "", ""))

    def test_company_json_writes(self):
        worktree = self.worktree("agent-a1")
        clone = self.root / "workspaces" / "a-clone"
        (clone / "scripts").mkdir(parents=True)
        (clone / "scripts" / "company_config.py").write_text("")
        (self.root / "link.json").symlink_to(self.root / "company.json")
        for path, cwd in [(self.root / "company.json", self.root), ("company.json", self.root),
                          ("../company.json", self.root / "knowledge"), (self.root / "Company.JSON", self.root),
                          (self.root / "knowledge" / ".." / "company.json", self.root), (self.root / "link.json", self.root),
                          (clone / "company.json", self.root), (worktree / "company.json", worktree)]:
            for tool_name in ["Write", "Edit", "MultiEdit", "NotebookEdit"]:
                with self.subTest(path=path, tool_name=tool_name):
                    tool_input = self.write_input(tool_name, str(path))
                    for agent_type in (None, "cto", "platform-engineer"):
                        self.assert_refused(self.company_write(tool_name, tool_input, "a1", agent_type, cwd))
                    self.assert_asks(self.company_write(tool_name, tool_input, None, None, cwd))
                    self.assert_asks(self.company_write(tool_name, tool_input, None, "ceo", cwd))
        for path in ["workspaces/acme/app/company.json", "company.json.md", "my-company.json", "knowledge/company.json"]:
            with self.subTest(path=path):
                for agent_id in (None, "a1"):
                    self.assert_no_decision(self.company_write("Write", {"file_path": path, "content": "x\n"}, agent_id))

    def test_a_link_at_company_json_is_company_json(self):
        (self.root / "elsewhere.json").write_text("{}")
        (self.root / "company.json").symlink_to(self.root / "elsewhere.json")
        edit = {"file_path": str(self.root / "company.json"), "old_string": "a", "new_string": "b"}
        self.assert_refused(self.company_write("Edit", edit, "a1"))
        self.assert_asks(self.company_write("Edit", edit))

    BASH_WRITES = [
        "echo '{}' > company.json", "echo '{}' >> company.json", "echo x | tee company.json", "cat > company.json <<'EOF'\n{}\nEOF",
        "sed -i '' 's/a/b/' company.json", "sed -i s/a/b/ ./company.json", "cp /tmp/x company.json", "mv /tmp/x {root}/company.json",
        "rm company.json", "rm -f comp*.json", "rm *.json", "ln -sf /tmp/x company.json", "truncate -s 0 company.json",
        "python3 -c \"open('company.json','w').write('{}')\"", "python3 - <<'EOF'\nopen('company.json', 'w')\nEOF",
        "jq .x company.json > company.json.new && mv company.json.new company.json", "perl -pi -e s/a/b/ company.json",
        "git checkout other -- company.json", "git restore company.json", "chmod 777 company.json", "dd of=company.json if=/tmp/x",
        "cat company.json; echo x > 'company'.json", "bash -c 'echo > company.json'", "cp /tmp/x \"$ROOT/company.json\"",
        "cd knowledge && echo > ../company.json", "cd $X && echo > company.json", "cp /tmp/{company.json,x} {root}/company.json",
        "cp /tmp/company.json .; cat company.json", "echo x > COMPANY.json", "echo $(echo > company.json)",
        "git -C {root} checkout company.json", "echo 'x > company.json", "find . -name '*.json' -delete",
    ]
    # A copy into a folder, whatever folder its source is in, and from any cwd.
    BASH_COPIES = [
        "cp /tmp/x/company.json .", "cp /tmp/x/company.json {root}/", "cp -R /tmp/x/company.json {root}", "mv /tmp/x/company.json .",
        "install -m 644 /tmp/x/company.json {root}", "rsync /tmp/x/company.json {root}/", "ln -s /tmp/x/company.json {root}/",
        "cp /tmp/x/company.json \"$ROOT\"", "git -C {root} checkout other -- company.json", "tar -xf x.tar -C {root} company.json",
        "cd /tmp/x && cp company.json {root}/", "echo x > workspaces/acme/app/company.json",
    ]
    BASH_READS = [
        "cat company.json", "cat {root}/company.json | head -5", "grep -n products company.json", "jq .products company.json",
        "jq .x company.json 2>/dev/null", "git diff company.json", "git log --oneline -- company.json", "ls company.json",
        "git add company.json", "git add company.json && git commit -m 'company.json: the timezone'", "git show HEAD:company.json",
        "diff company.json company.json.example", "test -f company.json && echo yes", "stat company.json", "ls *.json",
        "sed -n 1,5p company.json", "wc -l c*.json",
    ]
    BASH_OTHER = [
        "echo x > my-company.json", "python3 -c 'import company_config'",
        "cp x /tmp/company.json.bak", "echo x > company.jsonl", "python3 -m unittest discover -s scripts/tests", "ls -la",
        "rm workspaces/acme/*.json", "cat > notes.md <<'EOF'\n* a point\nEOF", "cd workspaces/acme && rm *.json",
        "psql -c 'select * from x'", "for f in knowledge/*.md; do wc $f; done",
    ]

    def test_a_bash_command_that_may_write_company_json(self):
        for command, cwd in [(command, self.root) for command in self.BASH_WRITES + self.BASH_COPIES] + \
                [(command, "/tmp") for command in self.BASH_COPIES]:
            command = command.replace("{root}", str(self.root))
            with self.subTest(command=command, cwd=cwd):
                self.assert_refused(self.company_write("Bash", {"command": command}, "a1", "cto", cwd))
                self.assert_refused(self.company_write("Bash", {"command": command}, "a1", None, cwd))
                self.assert_asks(self.company_write("Bash", {"command": command}, None, "ceo", cwd))

    def test_reading_company_json_and_other_files_gets_no_decision(self):
        for command in self.BASH_READS + self.BASH_OTHER:
            command = command.replace("{root}", str(self.root))
            for agent_id in (None, "a1"):
                with self.subTest(command=command, agent_id=agent_id):
                    self.assert_no_decision(self.company_write("Bash", {"command": command}, agent_id))

    def test_a_review_packet_that_names_the_file_gets_no_decision(self):
        command = "python3 scripts/second_opinion.py --file /dev/stdin <<'EOF'\ncompany.json changes\nEOF"
        self.assert_no_decision(self.company_write("Bash", {"command": command}, "a1", "code-reviewer"))

    def test_a_long_command_is_read_in_time(self):
        for command in ["x" * 400_000 + " > company.json", "company.json " * 20_000, "./" * 200_000 + "company.json",
                        "{" * 100_000 + " > company.json", "*" * 2_000 + "a company.json"]:
            with self.subTest(size=len(command)):
                self.assert_refused(self.company_write("Bash", {"command": command}, "a1"))

    def test_what_it_cant_read_is_refused(self):
        env = dict(os.environ, CLAUDE_PROJECT_DIR=str(self.root))
        for text in ("not json", "[]", '{"tool_name": "Write", "tool_input": [1]}', '{"tool_name": "Bash", "tool_input": [1]}'):
            with self.subTest(text=text):
                result = subprocess.run([sys.executable, str(HOOK)], input=text, capture_output=True, text=True, env=env,
                                        timeout=30)
                self.assertEqual(result.returncode, 2)
                self.assertIn("fail closed", result.stderr)

    def test_a_broken_company_json_changes_nothing_here(self):
        (self.root / "company.json").write_text("{")
        self.assert_refused(self.company_write("Write", {"file_path": "company.json", "content": "{}"}, "a1"))
        self.assert_asks(self.company_write("Write", {"file_path": "company.json", "content": "{}"}))
        self.assert_no_decision(self.company_write("Write", {"file_path": "notes.md", "content": "x"}, "a1"))


if __name__ == "__main__":
    unittest.main()
