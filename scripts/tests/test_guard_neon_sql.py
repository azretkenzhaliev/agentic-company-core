"""Tests for scripts/hooks/guard_neon_sql.py, run as Claude Code runs it:
JSON on stdin, exit 2 plus stderr to block, exit 0 to allow."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HOOK = Path(__file__).resolve().parents[1] / "hooks" / "guard_neon_sql.py"
RUN_SQL = "mcp__claude_ai_Neon__run_sql"
RUN_TX = "mcp__claude_ai_Neon__run_sql_transaction"


class GuardNeonSql(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.log = self.root / "workspaces" / "neon-sql-audit.log"

    def tearDown(self):
        self.tmp.cleanup()

    def run_hook(self, tool_input, tool_name=RUN_SQL, agent_type="cto", raw=None):
        payload = {
            "session_id": "test",
            "cwd": str(self.root),
            "hook_event_name": "PreToolUse",
            "tool_name": tool_name,
            "tool_input": tool_input,
            "agent_id": "a1",
            "agent_type": agent_type,
        }
        env = dict(os.environ, CLAUDE_PROJECT_DIR=str(self.root))
        return subprocess.run(
            [sys.executable, str(HOOK)],
            input=raw if raw is not None else json.dumps(payload),
            capture_output=True,
            text=True,
            env=env,
            timeout=30,
        )

    def sql(self, sql, **kw):
        return self.run_hook({"project_id": "p1", "sql": sql}, **kw)

    def log_lines(self):
        return [json.loads(line) for line in self.log.read_text(encoding="utf-8").splitlines()]

    def assertAllowed(self, result):
        self.assertEqual(result.returncode, 0, result.stderr)

    def assertBlocked(self, result, reason):
        self.assertEqual(result.returncode, 2)
        self.assertIn(reason, result.stderr)

    # Allowed: reads, inserts, scoped writes.

    def test_allows_ordinary_statements(self):
        for sql in [
            "SELECT count(*) FROM task",
            "select id, updated_at from task_revision where task_id = $1",
            "INSERT INTO task_provenance (task_id) VALUES (1)",
            "UPDATE task SET level = 2 WHERE id = 7",
            "DELETE FROM content.queue WHERE id = 3",
            "SELECT count(*) FROM test_session",
            "SELECT account_id FROM payment WHERE id = 1",
        ]:
            with self.subTest(sql=sql):
                self.assertAllowed(self.sql(sql))

    # Blocked words and tables.

    def test_blocks_forbidden_words(self):
        for sql, reason in [
            ("DROP TABLE task", "DROP"),
            ("drop index if exists x", "DROP"),
            ("TRUNCATE task", "TRUNCATE"),
            ("ALTER ROLE app_content LOGIN", "ALTER ROLE"),
            ("alter  user x nologin", "ALTER USER"),
            ("CREATE ROLE x PASSWORD 'p'", "PASSWORD"),
            ("SELECT rolname FROM pg_authid", "pg_authid"),
            ("SELECT * FROM pg_shadow", "pg_shadow"),
        ]:
            with self.subTest(sql=sql):
                self.assertBlocked(self.sql(sql), reason)

    def test_blocks_secret_tables(self):
        for sql in ['SELECT count(*) FROM account', 'SELECT 1 FROM public."session"', "SELECT * FROM verification"]:
            with self.subTest(sql=sql):
                self.assertBlocked(self.sql(sql), "account, session or verification")

    def test_blocks_delete_or_update_without_where(self):
        for sql in ["DELETE FROM task", "update task set level = 1", "UPDATE task SET level = 1 WHERE id = 1; DELETE FROM task_revision"]:
            with self.subTest(sql=sql):
                self.assertBlocked(self.sql(sql), "DELETE or UPDATE without WHERE")

    def test_transaction_is_blocked_if_any_statement_is(self):
        result = self.run_hook({"sql_statements": ["SELECT 1", "TRUNCATE task"]}, tool_name=RUN_TX)
        self.assertBlocked(result, "TRUNCATE")

    def test_transaction_of_clean_statements_is_allowed(self):
        self.assertAllowed(self.run_hook({"sql_statements": ["SELECT 1", "INSERT INTO task (id) VALUES (1)"]}, tool_name=RUN_TX))

    def test_missing_or_malformed_sql_is_blocked(self):
        self.assertBlocked(self.run_hook({"project_id": "p1"}), "no SQL")
        self.assertBlocked(self.run_hook({"sql": ["SELECT 1"]}), "no SQL")
        self.assertBlocked(self.run_hook({"sql_statements": []}, tool_name=RUN_TX), "no SQL")
        self.assertBlocked(self.run_hook({}, raw="not json"), "couldn't read")

    def test_other_tools_are_ignored(self):
        self.assertAllowed(self.run_hook({"sql": "DROP TABLE task"}, tool_name="mcp__claude_ai_Neon__list_projects"))
        self.assertFalse(self.log.exists())

    # The audit log.

    def test_every_statement_is_logged_with_agent_and_verdict(self):
        self.sql("SELECT 1")
        self.run_hook({"project_id": "p1", "branch_id": "b1", "sql_statements": ["SELECT 2", "DROP TABLE x"]}, tool_name=RUN_TX, agent_type=None)
        lines = self.log_lines()
        self.assertEqual([line["sql"] for line in lines], ["SELECT 1", "SELECT 2", "DROP TABLE x"])
        self.assertEqual(lines[0]["agent"], "cto")
        self.assertEqual(lines[1]["agent"], "main")
        self.assertEqual(lines[1]["branch_id"], "b1")
        self.assertEqual(lines[0]["blocked"], [])
        self.assertEqual(lines[2]["blocked"], ["DROP"])
        self.assertTrue(lines[0]["time"].endswith("+00:00"))

    def test_passwords_never_reach_the_log(self):
        self.sql("ALTER ROLE x WITH LOGIN PASSWORD 's3cret-value'")
        self.assertNotIn("s3cret-value", self.log.read_text(encoding="utf-8"))

    def test_unwritable_log_blocks_the_call(self):
        self.log.parent.parent.mkdir(parents=True, exist_ok=True)
        self.log.parent.write_text("a file where the folder should be")
        self.assertBlocked(self.sql("SELECT 1"), "can't be written")


if __name__ == "__main__":
    unittest.main()
