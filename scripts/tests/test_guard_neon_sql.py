"""Tests for scripts/hooks/guard_neon_sql.py, run as Claude Code runs it:
JSON on stdin, exit 2 plus stderr to block, exit 0 to allow."""

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

HOOK = Path(__file__).resolve().parents[1] / "hooks" / "guard_neon_sql.py"
RUN_SQL = "mcp__claude_ai_Neon__run_sql"
RUN_TX = "mcp__claude_ai_Neon__run_sql_transaction"
CREATE_BRANCH = "mcp__claude_ai_Neon__create_branch"
PRODUCTION = "demo-production"
TABLES = "a protected table (account, session, verification)"


class Guard(unittest.TestCase):
    NEON = {}  # company.json's integrations "neon"; None: not there

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.log = self.root / "workspaces" / "neon-sql-audit.log"
        self.company(self.NEON)
        # Claude Code's layout: <projects>/<session>.jsonl, and <projects>/<session>/subagents/agent-<id>.jsonl.
        self.transcript = self.root / "projects" / "s1.jsonl"
        self.subagent_transcript = self.root / "projects" / "s1" / "subagents" / "agent-a1.jsonl"
        self.transcript_path = self.transcript

    def tearDown(self):
        self.tmp.cleanup()

    def company(self, neon, text=None):
        """Writes the company.json the hook reads, with these "neon" settings (None: without any)."""
        (self.root / "company.json").write_text(
            text if text is not None else json.dumps({"integrations": {} if neon is None else {"neon": neon}}), encoding="utf-8")

    def backup(self, minutes_ago=5, project=PRODUCTION, parent=None, error=False, transcript=None):
        """Writes a create_branch call and its result into a transcript, as Claude Code does."""
        path = transcript or self.transcript
        path.parent.mkdir(parents=True, exist_ok=True)
        when = (datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)).isoformat().replace("+00:00", "Z")
        use_id = f"toolu_{uuid.uuid4().hex}"
        given = {"name": "backup-x", "no_compute": True, "project_id": project, **({"parent_id": parent} if parent else {})}
        result = {"type": "tool_result", "tool_use_id": use_id, "content": [{"type": "text", "text": "{}"}]}
        rows = [
            {"type": "assistant", "timestamp": when,
             "message": {"role": "assistant", "content": [{"type": "tool_use", "id": use_id, "name": CREATE_BRANCH, "input": given}]}},
            {"type": "user", "timestamp": when,
             "message": {"role": "user", "content": [dict(result, **({"is_error": True} if error else {}))]}},
        ]
        with path.open("a", encoding="utf-8") as f:
            f.writelines(json.dumps(row) + "\n" for row in rows)

    def prod(self, sql, tool_name=RUN_SQL, **tool_input):
        key = {"sql": sql} if tool_name == RUN_SQL else {"sql_statements": ["SELECT 1", sql]}
        return self.run_hook({"project_id": PRODUCTION, **key, **tool_input}, tool_name=tool_name)

    def payload(self, tool_input, tool_name=RUN_SQL, agent_type="cto"):
        return {
            "session_id": "test",
            "transcript_path": str(self.transcript_path),
            "cwd": str(self.root),
            "hook_event_name": "PreToolUse",
            "tool_name": tool_name,
            "tool_input": tool_input,
            "agent_id": "a1",
            "agent_type": agent_type,
        }

    def run_hook(self, tool_input, tool_name=RUN_SQL, agent_type="cto", raw=None, env=None):
        return subprocess.run(
            [sys.executable, str(HOOK)],
            input=raw if raw is not None else json.dumps(self.payload(tool_input, tool_name, agent_type)),
            capture_output=True,
            text=True,
            errors="surrogateescape",  # so a raw string's "\udcff" reaches stdin as the byte 0xFF
            env=dict(os.environ, CLAUDE_PROJECT_DIR=str(self.root), **(env or {})),
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


class Tightened(Guard):
    """The founder's tightening: bulk_after_backup is false."""

    NEON = {"bulk_after_backup": False}

    def test_allows_ordinary_statements(self):
        for sql in [
            "SELECT count(*) FROM task",
            "select id, updated_at from task_history where task_id = $1",
            "INSERT INTO task_tag (task_id) VALUES (1)",
            "UPDATE task SET level = 2 WHERE id = 7",
            "DELETE FROM content.queue WHERE id = 3",
            "SELECT count(*) FROM test_session",
            "SELECT account_id FROM payment WHERE id = 1",
            "UPDATE task SET level = (SELECT max(level) FROM task_history WHERE task_id = 7) WHERE id = 7",
            "INSERT INTO t (k) SELECT k FROM s ON CONFLICT DO NOTHING",
            "CREATE TABLE t (id int)",
            "ALTER TABLE task ADD COLUMN note text",
        ]:
            with self.subTest(sql=sql):
                self.assertAllowed(self.sql(sql))
                self.assertAllowed(self.run_hook({"project_id": "p1", "sql_statements": ["SELECT 1", sql]}, tool_name=RUN_TX))

    def test_blocks_forbidden_words(self):
        for sql, reason in [
            ("DROP TABLE task", "DROP"),
            ("drop index if exists x", "DROP"),
            ("DROP DATABASE neondb", "DROP"),
            ("DROP/**/SCHEMA public", "DROP"),
            ("ALTER TABLE task DROP COLUMN level", "DROP"),
            ("DROP OWNED BY app_owner", "DROP"),
            ("DO $$ BEGIN EXECUTE 'DROP SCHEMA content CASCADE'; END $$", "DROP"),
            ("DO E'BEGIN \\104ROP TABLE task; END'", "DROP"),
            ("TRUNCATE task", "TRUNCATE"),
            ("DO $$ BEGIN EXECUTE format('TRUNCATE %I', 'task'); END $$", "TRUNCATE"),
            ("ALTER ROLE app_content LOGIN", "ALTER ROLE"),
            ("alter  user x nologin", "ALTER USER"),
            ("CREATE ROLE x PASSWORD 'p'", "PASSWORD"),
            ("SELECT rolname FROM pg_authid", "pg_authid"),
            ("SELECT * FROM pg_shadow", "pg_shadow"),
        ]:
            with self.subTest(sql=sql):
                self.assertBlocked(self.sql(sql), reason)

    def test_blocks_protected_tables_too(self):
        self.assertBlocked(self.sql("SELECT count(*) FROM account"), TABLES)
        self.assertAllowed(self.sql("SELECT count(*) FROM message WHERE subject ILIKE '%verification code%'"))

    def test_blocks_delete_or_update_without_its_own_where(self):
        self.backup(project="p1")  # a backup lifts nothing while bulk_after_backup is off
        for sql in [
            "DELETE FROM task",
            "update task set level = 1",
            "UPDATE task SET level = 1 WHERE id = 1; DELETE FROM task_history",
            "DELETE FROM task -- where id = 7",
            "UPDATE task SET level = 1 /* WHERE id = 7 */",
            "UPDATE task SET level = (SELECT 1 WHERE true)",
            "WITH c AS (SELECT id FROM task_history WHERE level = 1) DELETE FROM task",
            "UPDATE task SET note = 'see where'",
            'DELETE FROM "where"',
            "INSERT INTO t (k) VALUES (1) ON CONFLICT (k) DO UPDATE SET v = 0",
            "DO $$ BEGIN DELETE FROM task; END $$",
        ]:
            with self.subTest(sql=sql):
                self.assertBlocked(self.sql(sql), "DELETE or UPDATE without WHERE")

    def test_transaction_is_blocked_if_any_statement_is(self):
        result = self.run_hook({"sql_statements": ["SELECT 1", "TRUNCATE task"]}, tool_name=RUN_TX)
        self.assertBlocked(result, "TRUNCATE")


class Default(Guard):
    """The default rules: integrations "neon" is {}."""

    def test_bulk_changes_pass_after_a_backup_and_only_then(self):
        for sql in ["DELETE FROM task", "TRUNCATE task", "DROP TABLE task"]:
            self.assertBlocked(self.sql(sql), "no backup branch")
        self.backup(project="p1")
        for sql in ["DELETE FROM task", "TRUNCATE task", "DROP TABLE task"]:
            self.assertAllowed(self.sql(sql))

    def test_blocks_credentials(self):
        for sql, reason in [
            ("ALTER ROLE app_content LOGIN", "ALTER ROLE"),
            ("alter  user x nologin", "ALTER USER"),
            ("CREATE ROLE x PASSWORD 'p'", "PASSWORD"),
            ("DO E'BEGIN ALTER \\122OLE app_content LOGIN; END'", "ALTER ROLE"),
            ("SELECT rolname FROM pg_authid", "pg_authid"),
            ("SELECT * FROM pg_shadow", "pg_shadow"),
        ]:
            with self.subTest(sql=sql):
                self.assertBlocked(self.sql(sql), reason)

    def test_blocks_protected_tables_named_in_code_names_comments_and_strings_read_as_code(self):
        for sql in [
            "SELECT count(*) FROM account",
            'SELECT 1 FROM public."session"',
            "SELECT * FROM verification",
            'SELECT "account".id FROM "account"',
            'SELECT 1 FROM "Session"',
            "SELECT 1 FROM t -- not account",
            "SELECT 1 /* session */ FROM t",
            "SELECT count(*) AS verification FROM t",
            "DO $$ BEGIN PERFORM 1 FROM account; END $$",
            "DO $$ BEGIN EXECUTE 'SELECT 1 FROM session'; END $$",
            "DO $$ BEGIN EXECUTE format('SELECT 1 FROM %I', 'verification'); END $$",
            "DO E'BEGIN PERFORM 1 FROM \\141ccount; END'",
            "CREATE FUNCTION f() RETURNS bigint LANGUAGE sql AS 'SELECT count(*) FROM session'",
            "CREATE FUNCTION f() RETURNS bigint LANGUAGE sql AS E'SELECT count(*) FROM \\163ession'",
            "CREATE FUNCTION f() RETURNS bigint LANGUAGE sql AS $f$ SELECT count(*) FROM account $f$",
            "SELECT cron.schedule('x', '0 3 * * *', 'DELETE FROM verification')",
            "SELECT * FROM dblink('dbname=neondb', E'SELECT id FROM \\x61ccount') AS t(id text)",
            "SELECT query_to_xml('select * from session', true, false, '')",
            "SELECT pg_catalog.table_to_xml('public.account', true, false, '')",
            "SELECT * FROM ts_stat('SELECT to_tsvector(id) FROM verification')",
            "SELECT ts_rewrite(to_tsquery('a'), 'SELECT t, s FROM session')",
            "SELECT * FROM dblink(current_setting('x.conn'), 'SELECT id FROM verification') AS t(id text)",
            "SELECT * FROM crosstab('SELECT a, b, c FROM account') AS ct(a text, b text)",
            "SELECT * FROM connectby('verification', 'id', 'parent', '1', 0) AS t(id text, parent text, level int)",
            # pg_stats' rows hold sampled values of the columns: any string naming the table counts there.
            "SELECT most_common_vals, histogram_bounds FROM pg_stats WHERE tablename = 'session'",
            "SELECT * FROM pg_catalog.pg_stats_ext WHERE tablename = 'account'",
            # `$1$` is no dollar quote (a tag can't start with a digit), so `account` is code.
            "SELECT $1$ FROM account $1$",
            # Where Postgres may pair the quotes otherwise, the rest is read as it stands: with
            # standard_conforming_strings off, 'a\' , ' is one string and `FROM account` is code...
            "SELECT 'a\\' , ' FROM account WHERE '1'='1'",
            # ...and a character past ASCII in code: a dollar tag Postgres takes, a name before E''.
            "SELECT $—$'$—$ FROM account WHERE 'x' = 'x'",
            "SELECT —E'\\' FROM session --'",
        ]:
            with self.subTest(sql=sql):
                self.assertBlocked(self.sql(sql), TABLES)

    def test_every_string_counts_where_a_reader_is_named(self):
        pad = " || ".join(["''"] * 20)
        for sql in [
            "SELECT query_to_xml(('select * from account'), true, false, '')",
            "SELECT \"query_to_xml\"('select * from account', true, false, '')",
            "SELECT pg_catalog.\"query_to_xml\"('select * from session', true, false, '')",
            "SELECT table_to_xml(('account')::regclass, true, false, '')",
            "SELECT table_to_xml(CAST('account' AS regclass), true, false, '')",
            "SELECT query_to_xml(format('select * from %I', 'account'), true, false, '')",
            "SELECT t, query_to_xml(format('select * from %I limit 1', t), true, false, '') "
            "FROM unnest(ARRAY['account', 'session', 'verification']) t",
            "WITH q(s) AS (VALUES ('select * from account')) SELECT query_to_xml(s, true, false, '') FROM q",
            "CREATE FUNCTION dump(t text) RETURNS SETOF json LANGUAGE plpgsql AS $f$ BEGIN RETURN QUERY EXECUTE "
            "format('select row_to_json(x) from %I x', t); END $f$; SELECT * FROM dump('account')",
            "SELECT * FROM dblink('dbname=neondb', format('select id from %I', 'account')) AS t(id text)",
            "SELECT * FROM crosstab(concat('select a, b, c from ', 'session')) AS ct(a text, b text)",
            "SELECT * FROM ts_stat(format('select to_tsvector(id) from %I', 'verification'))",
            f"SELECT query_to_xml({pad} || 'select * from account', true, false, '')",
            "SELECT * FROM xpath_table('id', 'doc', 'account', '/a', 'true') AS t(id text, a text)",
            "COPY (SELECT 1) TO PROGRAM 'psql -c \"select * from account\"'",
            "SELECT cron.schedule('j', '* * * * *', format('delete from %I', 'session'))",
            "SELECT query_to_xml(format('select * from %I', table_name), true, false, '') "
            "FROM information_schema.tables WHERE table_name = 'account'",  # a compared value, but a reader runs it
        ]:
            with self.subTest(sql=sql):
                self.assertBlocked(self.sql(sql), TABLES)

    def test_a_table_word_in_a_string_counts_outside_a_comparison(self):
        # Elsewhere a string may reach a function that reads it as a table's name.
        for sql in [
            "SELECT * FROM dump('account')",  # a function made in an earlier call
            "WITH q(s) AS (VALUES ('account')) SELECT d.* FROM q, dump(q.s) d",
            "SELECT to_regclass('session')",
            "SELECT 'account'::regclass",
            "INSERT INTO note (body) VALUES ('session')",
            "SELECT 1 WHERE s = 'x' AND f('verification')",
            "SELECT 'account'",
            "SELECT 'new-account'",
            "SELECT 1 WHERE s := 'session'",
            "SELECT f(s => 'account')",
            "SELECT doc->>'session' FROM t",
            "SELECT 'x' = 'y', 'account'",  # a comma follows only a list's opener
            "SELECT 1 WHERE s = 'x' OR f(s, 'session')",
        ]:
            with self.subTest(sql=sql):
                self.assertBlocked(self.sql(sql), TABLES)
        result = self.run_hook({"sql_statements": ["SELECT 'session'", "SELECT 1"]}, tool_name=RUN_TX)
        self.assertBlocked(result, TABLES)

    def test_a_table_word_only_in_a_data_string_passes(self):
        for sql in [
            "SELECT table_name FROM information_schema.tables WHERE table_name !~ ALL (ARRAY['^account$', '^session$'])",
            "SELECT count(*) FROM message WHERE subject ILIKE '%verification code%'",
            "SELECT 1 WHERE s ~* E'^session\\\\b' OR s SIMILAR TO U&'%account%' OR s LIKE $$%verification%$$",
            "SELECT 1 WHERE s = 'it''s the account'",
            "SELECT 1 WHERE s ~ '\\maccount\\M' OR s = '\\\\' OR s = 'session'",  # no backslash before a quote
            "SELECT count(*) FROM t WHERE subject ILIKE '%vérifier%' OR subject ILIKE '%verification%'",
            "SELECT 1 FROM t WHERE s <> 'session' AND u != 'verification' AND v >= 'account' AND w < 'session'",
            "SELECT 1 WHERE s NOT ILIKE 'session%' OR s SIMILAR TO '%verification%' OR s !~* 'account'",
            "SELECT 1 WHERE s IN ('account', 'session') OR s NOT IN ('verification')",
            "SELECT 1 WHERE s = ANY (ARRAY['account', 'session']) OR s LIKE SOME (ARRAY['%verification%'])",
            "UPDATE t SET status = 'verification sent' WHERE id = 1",
            "SELECT count(*) FROM test_session",
            "SELECT account_id FROM payment WHERE id = 1",
        ]:
            with self.subTest(sql=sql):
                self.assertAllowed(self.sql(sql))

    def test_the_settings_add_protected_tables_and_take_none_away(self):
        self.assertAllowed(self.sql("SELECT * FROM api_key"))
        self.company({"protected_tables": ["member", "api_key", "account"]})
        label = "a protected table (account, session, verification, member, api_key)"
        self.assertBlocked(self.sql("SELECT * FROM api_key"), label)
        self.assertBlocked(self.sql('SELECT 1 FROM public."MEMBER"'), label)
        self.assertBlocked(self.sql("SELECT count(*) FROM session"), label)
        self.assertAllowed(self.sql("SELECT 1 FROM t WHERE s = 'api_key'"))
        self.company({"protected_tables": []})
        self.assertBlocked(self.sql("SELECT count(*) FROM account"), TABLES)

    def test_transaction_is_blocked_if_any_statement_is(self):
        result = self.run_hook({"sql_statements": ["SELECT 1", "SELECT * FROM pg_shadow"]}, tool_name=RUN_TX)
        self.assertBlocked(result, "pg_shadow")

    def test_without_the_neon_settings_every_call_is_refused(self):
        self.company(None)
        for tool_input, tool_name in [({"project_id": "p1", "sql": "SELECT 1"}, RUN_SQL),
                                      ({"sql_statements": ["SELECT 1"]}, RUN_TX)]:
            with self.subTest(tool_name=tool_name):
                self.assertBlocked(self.run_hook(tool_input, tool_name=tool_name), 'no integrations "neon"')
        (self.root / "company.json").unlink()
        self.assertBlocked(self.sql("SELECT 1"), 'no integrations "neon"')

    def test_a_broken_company_json_blocks_every_call(self):
        for text in ["{", "[]", "null", '{"integrations": []}', '{"integrations": null}', '{"integrations": {"neon": []}}',
                     '{"integrations": {"neon": true}}', '{"integrations": {"neon": {"protected_tables": "account"}}}',
                     '{"integrations": {"neon": {"protected_tables": [""]}}}',
                     '{"integrations": {"neon": {"production_projects": "p1"}}}',
                     '{"integrations": {"neon": {"bulk_after_backup": "yes"}}}']:
            with self.subTest(text=text):
                self.company(None, text)
                self.assertBlocked(self.sql("SELECT 1"), "Blocked: the Neon SQL guard")

    # Fail closed: every failure exits 2.

    def test_an_event_that_isnt_an_object_is_blocked(self):
        for raw in ['["DROP SCHEMA s"]', '"DROP SCHEMA s"', "null", "42"]:
            with self.subTest(raw=raw):
                self.assertBlocked(self.run_hook(None, raw=raw), "Neon SQL guard failed")

    def test_a_tool_input_that_isnt_an_object_is_blocked(self):
        for tool_input in ["DROP SCHEMA s", ["DROP SCHEMA s"], 42]:
            for tool_name in [RUN_SQL, RUN_TX]:
                with self.subTest(tool_input=tool_input, tool_name=tool_name):
                    self.assertBlocked(self.run_hook(tool_input, tool_name=tool_name), "Neon SQL guard failed")

    def test_sql_the_log_cant_encode_is_blocked(self):
        for sql in ["DROP SCHEMA s \udcff", "SELECT 1 \udcff"]:
            with self.subTest(sql=sql, tool="run_sql"):
                self.assertBlocked(self.sql(sql), "Neon SQL guard failed")  # "\udcff" escaped in the JSON
            with self.subTest(sql=sql, tool="run_sql_transaction"):
                result = self.run_hook({"sql_statements": ["SELECT 1", sql]}, tool_name=RUN_TX)
                self.assertBlocked(result, "Neon SQL guard failed")
            # The raw byte 0xFF on stdin, read strictly (a decode error) or with surrogateescape (an encode error at the log).
            raw = json.dumps(self.payload({"sql": sql}), ensure_ascii=False)
            for io in ["utf-8:strict", "utf-8:surrogateescape"]:
                with self.subTest(sql=sql, stdin=io):
                    self.assertBlocked(self.run_hook(None, raw=raw, env={"PYTHONIOENCODING": io}), "Neon SQL guard")

    def test_missing_or_malformed_sql_is_blocked(self):
        self.assertBlocked(self.run_hook({"project_id": "p1"}), "no SQL")
        self.assertBlocked(self.run_hook({"sql": ["SELECT 1"]}), "no SQL")
        self.assertBlocked(self.run_hook({"sql_statements": []}, tool_name=RUN_TX), "no SQL")
        self.assertBlocked(self.run_hook({}, raw="not json"), "couldn't read")

    def test_a_connector_by_another_name_is_held_too(self):
        for tool_name in ("mcp__neon__run_sql", "mcp__Neon_prod__run_sql", "mcp__plugin_neon-db_neon__run_sql"):
            self.assertBlocked(self.run_hook({"sql": "DROP SCHEMA s"}, tool_name=tool_name), "DROP SCHEMA")
        self.assertBlocked(self.run_hook({"sql_statements": ["DROP SCHEMA s"]},
                                         tool_name="mcp__neon__run_sql_transaction"), "DROP SCHEMA")

    def test_other_tools_are_ignored(self):
        self.assertAllowed(self.run_hook({"sql": "DROP DATABASE neondb"}, tool_name="mcp__claude_ai_Neon__list_projects"))
        self.assertFalse(self.log.exists())

    def test_a_check_past_its_deadline_is_blocked(self):
        # Whatever is slow, the hook blocks before Claude Code's timeout.
        load = (f"import importlib.util as u; s = u.spec_from_file_location('g', {str(HOOK)!r}); "
                "g = u.module_from_spec(s); s.loader.exec_module(g); g.DEADLINE = 0.5; g.main()")
        slow = "SELECT " + " ".join(f"$a{i}$" for i in range(40000)) + "; DELETE FROM task"
        began = time.monotonic()
        result = subprocess.run(
            [sys.executable, "-c", load], input=json.dumps(self.payload({"project_id": PRODUCTION, "sql": slow})),
            capture_output=True, text=True, env=dict(os.environ, CLAUDE_PROJECT_DIR=str(self.root)), timeout=30,
        )
        self.assertBlocked(result, "was still checking this tool call after 0.5 seconds")
        self.assertLess(time.monotonic() - began, 5)

    # The audit log.

    def test_every_statement_is_logged_with_agent_and_verdict(self):
        self.sql("SELECT 1")
        self.run_hook({"project_id": "p1", "branch_id": "b1", "sql_statements": ["SELECT 2", "DROP SCHEMA x"]},
                      tool_name=RUN_TX, agent_type=None)
        lines = self.log_lines()
        self.assertEqual([line["sql"] for line in lines], ["SELECT 1", "SELECT 2", "DROP SCHEMA x"])
        self.assertEqual(lines[0]["agent"], "cto")
        self.assertEqual(lines[1]["agent"], "main")
        self.assertEqual(lines[1]["branch_id"], "b1")
        self.assertEqual(lines[0]["blocked"], [])
        self.assertEqual(lines[2]["blocked"], ["DROP DATABASE or DROP SCHEMA"])
        self.assertTrue(lines[0]["time"].endswith("+00:00"))

    def test_passwords_never_reach_the_log(self):
        self.sql("ALTER ROLE x WITH LOGIN PASSWORD 's3cret-value'")
        self.assertNotIn("s3cret-value", self.log.read_text(encoding="utf-8"))

    def test_unwritable_log_blocks_the_call(self):
        self.log.parent.parent.mkdir(parents=True, exist_ok=True)
        self.log.parent.write_text("a file where the folder should be")
        self.assertBlocked(self.sql("SELECT 1"), "can't be written")


class BulkAfterBackup(Guard):
    """The default, with production named."""

    NEON = {"production_projects": [PRODUCTION]}

    def test_data_and_schema_changes_pass_outside_production(self):
        for sql in [
            "DELETE FROM task",
            "update task set level = 1",
            "INSERT INTO t (k) VALUES (1) ON CONFLICT (k) DO UPDATE SET v = 0",
            "TRUNCATE task",
            "DROP TABLE task",
            "ALTER TABLE task DROP COLUMN level",
            "ALTER TABLE task DROP schema_version",  # a column, COLUMN left out
            "drop index if exists x",
            "ALTER TABLE task DROP CONSTRAINT task_pkey",
            "DROP /* database */ TABLE t",  # the word inside a comment, then TABLE
            'ALTER TABLE task DROP "user"',  # a quoted name, not the word USER
            "SELECT 'drop'",
        ]:
            with self.subTest(sql=sql):
                self.assertAllowed(self.sql(sql))
                self.assertEqual(self.log_lines()[-1]["blocked"], [])

    def test_blocks_dropping_a_database_or_schema(self):
        for sql in [
            "DROP DATABASE neondb",
            "DrOp DaTaBaSe neondb",
            "drop schema if exists content cascade",
            "DROP DATABASE neondb WITH (FORCE)",
            "DROP SCHEMA a, b",
            "DROP  \t\n DATABASE neondb",
            "DROP/**/SCHEMA public",
            "DROP /* a /* nested */ b */ SCHEMA public",
            "DROP -- why\nSCHEMA public",
            "DROP --why\rDATABASE neondb",  # Postgres ends a -- comment at \r too
            "SELECT 1; DROP SCHEMA public CASCADE",
            "DO $$ BEGIN EXECUTE 'DROP SCHEMA content CASCADE'; END $$",
            "ALTER TABLE t DROP schema",  # a column named schema: write DROP COLUMN
        ]:
            with self.subTest(sql=sql):
                self.assertBlocked(self.sql(sql), "DROP DATABASE or DROP SCHEMA")
        self.assertBlocked(self.sql("ALTER TABLE t DROP schema"), "write DROP COLUMN")

    def test_blocks_dropping_owned_objects_and_roles(self):
        for sql, reason in [
            ("DROP OWNED BY app_owner", "DROP OWNED"),
            ("DROP /* why */ OWNED BY app_owner CASCADE", "DROP OWNED"),
            ("DO $$ BEGIN EXECUTE 'DROP OWNED BY app_owner CASCADE'; END $$", "DROP OWNED"),
            ("drop role if exists a, b", "DROP ROLE, USER or GROUP"),
            ("DrOp\t/* a /* nested */ b */\nUsEr x", "DROP ROLE, USER or GROUP"),
            ("DROP GROUP editors", "DROP ROLE, USER or GROUP"),
            ("ALTER TABLE t DROP role", "DROP ROLE, USER or GROUP"),  # a column named role: write DROP COLUMN
        ]:
            with self.subTest(sql=sql):
                self.assertBlocked(self.sql(sql), reason)
                self.assertBlocked(self.run_hook({"sql_statements": ["SELECT 1", sql]}, tool_name=RUN_TX), reason)

    def test_the_log_names_each_refused_drop(self):
        self.sql("DROP OWNED BY r CASCADE; DROP ROLE r; DROP SCHEMA s")
        self.assertEqual(
            self.log_lines()[-1]["blocked"],
            ["DROP DATABASE or DROP SCHEMA", "DROP OWNED", "DROP ROLE, USER or GROUP"],
        )

    # Production: a bulk change needs a backup branch from the last 60 minutes.

    BULK = [
        ("DELETE FROM task", "DELETE or UPDATE without WHERE"),
        ("update task set level = 1", "DELETE or UPDATE without WHERE"),
        ("UPDATE task SET level = s.level FROM staging s", "DELETE or UPDATE without WHERE"),
        ("UPDATE task SET level = 1 WHERE id = 1; DELETE FROM task_history", "DELETE or UPDATE without WHERE"),
        ("WITH x AS (DELETE FROM task RETURNING id) INSERT INTO task_log (id) SELECT id FROM x", "DELETE or UPDATE without WHERE"),
        ("TRUNCATE task", "TRUNCATE"),
        ("truncate table task, task_history restart identity cascade", "TRUNCATE"),
        ("DROP TABLE task", "DROP TABLE"),
        ("drop /* why */ table if exists task cascade", "DROP TABLE"),
        ("ALTER TABLE task DROP COLUMN level", "ALTER TABLE ... DROP COLUMN"),
        ("alter table task drop column if exists level cascade", "ALTER TABLE ... DROP COLUMN"),
        ("ALTER TABLE task DROP level", "ALTER TABLE ... DROP COLUMN"),  # COLUMN left out
        ("ALTER TABLE task ADD COLUMN note text, DROP COLUMN level", "ALTER TABLE ... DROP COLUMN"),
        # A data string read as code, and a WHERE in another string than its write's, ask for a backup too.
        ("DO $$ BEGIN RAISE NOTICE 'delete'; END $$", "DELETE or UPDATE without WHERE"),
        ("DO $$ BEGIN EXECUTE 'DELETE FROM task' || ' WHERE id = 7'; END $$", "DELETE or UPDATE without WHERE"),
    ]

    def test_bulk_changes_on_production_without_a_backup_are_refused(self):
        for sql, label in self.BULK:
            for tool_name in [RUN_SQL, RUN_TX]:
                with self.subTest(sql=sql, tool_name=tool_name):
                    result = self.prod(sql, tool_name)
                    self.assertBlocked(result, f"{label} on production with no backup branch from the last 60 minutes")
                    self.assertIn(f"{CREATE_BRANCH} (project_id {PRODUCTION}, no parent_id), then retry", result.stderr)

    def test_comments_and_strings_dont_hide_a_bulk_change(self):
        for sql, label in [
            ("DELETE FROM task -- where id = 7", "DELETE or UPDATE without WHERE"),
            # A dollar tag may start with a letter or a digit past ASCII: its apostrophe is data.
            ("INSERT INTO note (body) VALUES ($\u00e9t\u00e9$ Don't $\u00e9t\u00e9$); DELETE FROM task; SELECT 'done'",
             "DELETE or UPDATE without WHERE"),
            ("SELECT $\u0663$ ' $\u0663$ AS a; DELETE FROM task; SELECT 'x'", "DELETE or UPDATE without WHERE"),
            ("UPDATE task SET level = 1 /* WHERE id = 7 */", "DELETE or UPDATE without WHERE"),
            ("UPDATE task SET level = 1 /* a /* nested */ WHERE id = 7 */", "DELETE or UPDATE without WHERE"),
            ("SELECT 1; -- the old rows, all of them,\nDELETE FROM task", "DELETE or UPDATE without WHERE"),
            ("/* run on */ DELETE FROM task", "DELETE or UPDATE without WHERE"),
            ("-- for\rTRUNCATE task", "TRUNCATE"),
            ("ALTER TABLE task /* v2; */ DROP level", "ALTER TABLE ... DROP COLUMN"),
            ("ALTER TABLE task -- v2;\nDROP COLUMN level", "ALTER TABLE ... DROP COLUMN"),
            ("ALTER TABLE task ALTER COLUMN note SET DEFAULT $$;$$, DROP level", "ALTER TABLE ... DROP COLUMN"),
            ("ALTER TABLE task ALTER COLUMN note SET DEFAULT ';', DROP level", "ALTER TABLE ... DROP COLUMN"),
            ("DO $$ BEGIN DELETE FROM task -- where id = 7\n; END $$", "DELETE or UPDATE without WHERE"),
            ("DO $$ BEGIN EXECUTE 'DELETE FROM task'; END $$", "DELETE or UPDATE without WHERE"),
            ("DO $body$ BEGIN EXECUTE format('TRUNCATE %I', 'task'); END $body$", "TRUNCATE"),
            ("DO LANGUAGE plpgsql $$ BEGIN EXECUTE 'DROP TABLE ' || 'task'; END $$", "DROP TABLE"),
            ("DO 'BEGIN UPDATE task SET level = 1; END'", "DELETE or UPDATE without WHERE"),
            # In a DO statement, and inside a string read as code, every string is code.
            ("DO LANGUAGE 'plpgsql' $$ BEGIN DELETE FROM task; END $$", "DELETE or UPDATE without WHERE"),
            ('DO LANGUAGE "plpgsql" $$ BEGIN DELETE FROM task; END $$', "DELETE or UPDATE without WHERE"),
            ("DO $$ BEGIN EXECUTE ('DELETE FROM task'); END $$", "DELETE or UPDATE without WHERE"),
            ("DO $$ BEGIN EXECUTE format('%s FROM task', 'DELETE'); END $$", "DELETE or UPDATE without WHERE"),
            ("DO $$ BEGIN EXECUTE concat('DELETE FROM ', 'task'); END $$", "DELETE or UPDATE without WHERE"),
            ("DO E'BEGIN EXECUTE \\'DELETE FROM task\\'; END'", "DELETE or UPDATE without WHERE"),
            ("DO U&'BEGIN DELETE FROM task; END'", "DELETE or UPDATE without WHERE"),
            ("DO $$ BEGIN EXECUTE U&'DELETE FROM task'; END $$", "DELETE or UPDATE without WHERE"),
            ("DO $$ BEGIN ALTER TABLE task ALTER COLUMN note SET DEFAULT 'x', DROP level; END $$", "ALTER TABLE ... DROP COLUMN"),
            ("CREATE FUNCTION f() RETURNS void AS 'TRUNCATE task' LANGUAGE sql", "TRUNCATE"),
            # Only a write's own WHERE counts, after it at its own depth of parentheses.
            ("UPDATE task SET level = (SELECT 1 WHERE true)", "DELETE or UPDATE without WHERE"),
            ("UPDATE task SET level = (SELECT max(r.level) FROM task_history r WHERE r.task_id = task.id)",
             "DELETE or UPDATE without WHERE"),
            ("WITH c AS (SELECT id FROM task_history WHERE level = 1) DELETE FROM task", "DELETE or UPDATE without WHERE"),
            ("WITH x AS (DELETE FROM task RETURNING id) SELECT * FROM x WHERE id = 1", "DELETE or UPDATE without WHERE"),
            ("DO $$ BEGIN UPDATE task SET note = 'see where'; END $$", "DELETE or UPDATE without WHERE"),
            # Leading blanks don't hide a DO statement; quoted names aren't SQL; escapes are undone; a rule's DO.
            (" " * 63 + "DO $$ BEGIN DELETE FROM task; END $$", "DELETE or UPDATE without WHERE"),
            ("SELECT 1;\n\n" + " " * 64 + "DO $$ BEGIN DELETE FROM task; END $$", "DELETE or UPDATE without WHERE"),
            ('DELETE FROM "where"', "DELETE or UPDATE without WHERE"),
            ('UPDATE task SET "where" = 1', "DELETE or UPDATE without WHERE"),
            ('ALTER TABLE "t;x" DROP level', "ALTER TABLE ... DROP COLUMN"),
            ("DO E'BEGIN \\104ELETE FROM task; END'", "DELETE or UPDATE without WHERE"),
            ("DO E'BEGIN EXECUTE \\'\\x44ELETE FROM task\\'; END'", "DELETE or UPDATE without WHERE"),
            ("DO U&'BEGIN \\0044ELETE FROM task; END'", "DELETE or UPDATE without WHERE"),
            ("CREATE RULE wipe AS ON INSERT TO task_log DO DELETE FROM task", "DELETE or UPDATE without WHERE"),
            ("CREATE RULE r AS ON INSERT TO task_log DO INSTEAD UPDATE task SET level = 1", "DELETE or UPDATE without WHERE"),
            ("CREATE RULE r AS ON INSERT TO task_log DO UPDATE task SET level = 1", "DELETE or UPDATE without WHERE"),
            ("SELECT cron.schedule('nightly', '0 3 * * *', 'DELETE FROM task')", "DELETE or UPDATE without WHERE"),
            ("SELECT dblink_exec('dbname=neondb', 'TRUNCATE task')", "TRUNCATE"),
        ]:
            for tool_name in [RUN_SQL, RUN_TX]:
                with self.subTest(sql=sql, tool_name=tool_name):
                    self.assertBlocked(self.prod(sql, tool_name), f"{label} on production with no backup")

    def test_bulk_changes_on_production_pass_after_a_fresh_backup(self):
        self.backup(minutes_ago=59)
        for sql, _ in self.BULK:
            for tool_name in [RUN_SQL, RUN_TX]:
                with self.subTest(sql=sql, tool_name=tool_name):
                    self.assertAllowed(self.prod(sql, tool_name))

    def test_a_stale_failed_or_other_backup_doesnt_count(self):
        self.backup(minutes_ago=61)
        self.backup(error=True)
        self.backup(project="p1")
        self.backup(parent="br-other")
        for sql, label in self.BULK:
            for tool_name in [RUN_SQL, RUN_TX]:
                with self.subTest(sql=sql, tool_name=tool_name):
                    self.assertBlocked(self.prod(sql, tool_name), f"{label} on production with no backup")

    def test_the_backup_must_come_from_the_branch_changed(self):
        self.backup(parent="br-main")
        self.assertBlocked(self.prod("DELETE FROM task"), "no backup branch")
        self.assertBlocked(self.prod("DELETE FROM task", branch_id="br-other"), "parent_id br-other), then retry")
        self.assertAllowed(self.prod("DELETE FROM task", branch_id="br-main"))
        self.assertAllowed(self.prod("TRUNCATE task", RUN_TX, branch_id="br-main"))

    def test_a_backup_made_by_another_agent_of_the_session_counts(self):
        self.backup(transcript=self.subagent_transcript)
        self.assertAllowed(self.prod("DELETE FROM task"))
        self.transcript_path = self.subagent_transcript  # in case a subagent's own path is passed
        self.assertAllowed(self.prod("DROP TABLE task", RUN_TX))

    def test_a_transcript_untouched_for_60_minutes_isnt_read(self):
        self.backup()
        old = (datetime.now(timezone.utc) - timedelta(minutes=61)).timestamp()
        os.utime(self.transcript, (old, old))
        self.assertBlocked(self.prod("DELETE FROM task"), "no backup branch")

    def test_the_callers_own_transcript_is_searched_first(self):
        # The search may stop at its time limit, so the file most likely to hold the backup goes first.
        spec = importlib.util.spec_from_file_location("guard_neon_sql", HOOK)
        guard = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(guard)
        self.backup(transcript=self.subagent_transcript)
        self.backup(transcript=self.subagent_transcript.with_name("agent-a0.jsonl"), project="p1")
        now, guard.START = datetime.now(timezone.utc), 0
        for agent_id, found in [("a1", True), (None, False)]:
            with self.subTest(agent_id=agent_id):
                clock = iter([0])  # the first file's check is in time; every later check is past the deadline
                guard.time = type("Clock", (), {"monotonic": staticmethod(lambda: next(clock, 100))})
                event = {"transcript_path": str(self.transcript), "agent_id": agent_id}
                self.assertEqual(guard.backed_up(event, {"project_id": PRODUCTION}, now), found)

    def test_a_missing_or_unreadable_transcript_means_no_backup(self):
        self.transcript_path = ""
        self.assertBlocked(self.prod("DELETE FROM task"), "no backup branch")
        self.transcript.parent.mkdir(parents=True)
        self.transcript.write_text("not json\n" + CREATE_BRANCH + "\n", encoding="utf-8")
        self.transcript_path = self.transcript
        self.assertBlocked(self.prod("DELETE FROM task"), "no backup branch")

    def test_a_search_past_its_time_finds_no_backup(self):
        # A search that runs too long counts as no backup.
        spec = importlib.util.spec_from_file_location("guard_neon_sql", HOOK)
        guard = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(guard)
        self.backup()
        event, now = {"transcript_path": str(self.transcript)}, datetime.now(timezone.utc)
        self.assertTrue(guard.backed_up(event, {"project_id": PRODUCTION}, now))
        guard.SEARCH_SECONDS = -1
        self.assertFalse(guard.backed_up(event, {"project_id": PRODUCTION}, now))

    def test_a_padded_call_is_blocked_in_time(self):
        # A check that reread text per DROP would run past the hook's timeout.
        for sql, reason in [
            ('SELECT 1 AS "' + "drop " * 25000 + '"; DROP SCHEMA public CASCADE', "DROP DATABASE or DROP SCHEMA"),
            ("ALTER TABLE task " + "DROP CONSTRAINT c, " * 30000 + "DROP level", "ALTER TABLE ... DROP COLUMN on production"),
            ("SELECT " + " + ".join(["update"] * 30000), "DELETE or UPDATE without WHERE on production"),
        ]:
            with self.subTest(sql=sql[:40]):
                began = time.monotonic()
                self.assertBlocked(self.prod(sql), reason)
                self.assertLess(time.monotonic() - began, 5)

    def test_other_projects_need_no_backup(self):
        for sql, _ in self.BULK:
            with self.subTest(sql=sql):
                self.assertAllowed(self.run_hook({"project_id": "p1", "sql": sql}))
                self.assertAllowed(self.run_hook({"project_id": "p1", "sql_statements": [sql]}, tool_name=RUN_TX))

    def test_no_project_id_counts_as_production_and_no_backup_lifts_it(self):
        self.backup()
        self.backup(project=None)
        self.assertBlocked(self.run_hook({"sql": "DELETE FROM task"}), "project_id of the call: pass it")
        self.assertBlocked(self.run_hook({"sql_statements": ["TRUNCATE t"]}, tool_name=RUN_TX), "no backup branch")

    def test_with_no_production_project_named_every_project_counts(self):
        self.company({})
        self.assertBlocked(self.sql("DELETE FROM task"), "no backup branch")
        self.backup(project="p2")
        self.assertBlocked(self.sql("DELETE FROM task"), "no backup branch")
        self.backup(project="p1")
        self.assertAllowed(self.sql("DELETE FROM task"))

    def test_other_statements_on_production_need_no_backup(self):
        for sql in [
            "SELECT count(*) FROM task",
            "INSERT INTO task (id) VALUES (1)",
            "UPDATE task SET level = 2 WHERE id = 7",
            "DELETE FROM content.queue WHERE id = 3",
            "INSERT INTO t (k) VALUES (1) ON CONFLICT (k) DO UPDATE SET v = 0",
            "INSERT INTO t (k) SELECT k FROM s ON CONFLICT ON CONSTRAINT t_pkey DO /* x */ UPDATE SET v = excluded.v",
            "SELECT * FROM task WHERE id = 1 FOR UPDATE",
            "SELECT * FROM task FOR NO KEY UPDATE SKIP LOCKED",
            "CREATE TABLE t (id int REFERENCES u ON DELETE CASCADE ON UPDATE SET NULL)",
            "CREATE TRIGGER trg BEFORE UPDATE OR DELETE ON t FOR EACH ROW EXECUTE FUNCTION f()",
            "CREATE TRIGGER trg INSTEAD OF DELETE ON v FOR EACH ROW EXECUTE FUNCTION f()",
            "GRANT SELECT, UPDATE, DELETE ON task TO reader",
            "CREATE POLICY p ON task FOR DELETE USING (true)",
            "DROP INDEX task_level_idx",
            "DROP VIEW v",
            "ALTER TABLE task DROP CONSTRAINT task_pkey",
            "ALTER TABLE task ALTER COLUMN level DROP DEFAULT, ALTER COLUMN note DROP NOT NULL",
            "ALTER TABLE task ALTER COLUMN level DROP IDENTITY IF EXISTS",
            "ALTER TABLE task ADD COLUMN note text; DROP INDEX i",
            # Data strings and quoted names aren't SQL.
            "INSERT INTO task_log (action) VALUES ('delete'), ('update'), ('truncate'), ('drop table')",
            "UPDATE task SET note = '-- not a comment' WHERE id = 7",
            "UPDATE task SET note = 'a /* b' WHERE id = 7",
            "UPDATE task SET note = E'it\\'s -- here' WHERE id = 7",
            "UPDATE task SET note = $$-- x$$ WHERE id = 7",
            'UPDATE "task--x" SET level = 1 WHERE id = 7',
            "COMMENT ON TABLE task IS 'we drop table rows and truncate weekly'",
            "SELECT 'DELETE FROM task'",
            "GRANT TRUNCATE ON task TO app",
            "REVOKE TRUNCATE ON task FROM app",
            "GRANT SELECT, TRUNCATE ON task TO app",
            "CREATE TRIGGER trg BEFORE TRUNCATE ON task FOR EACH STATEMENT EXECUTE FUNCTION f()",
            "DO $$ BEGIN EXECUTE format('UPDATE %I SET level = 1 WHERE id = $1', 'task') USING 7; END $$",
            "SELECT 1; DO $$ BEGIN UPDATE task SET note = 'x' WHERE id = 7; END $$",
            # A write's own WHERE, after it at its own depth of parentheses.
            "UPDATE task SET (level, note) = (1, 'x') WHERE id = 7",
            "UPDATE task SET level = (SELECT max(level) FROM task_history WHERE task_id = 7) WHERE id = 7",
            "UPDATE task SET level = s.level FROM (SELECT 1 AS level) s WHERE task.id = 7",
            "WITH x AS (DELETE FROM task WHERE id = 1 RETURNING id) SELECT * FROM x",
            "DELETE FROM task WHERE id IN (SELECT task_id FROM task_history)",
            "CREATE RULE r AS ON UPDATE TO task DO INSTEAD NOTHING",
            "SELECT cron.schedule('nightly', '0 3 * * *', 'DELETE FROM task_log WHERE created < now()')",
        ]:
            for tool_name in [RUN_SQL, RUN_TX]:
                with self.subTest(sql=sql, tool_name=tool_name):
                    self.assertAllowed(self.prod(sql, tool_name))

    def test_a_backup_doesnt_lift_the_other_refusals(self):
        self.backup()
        for sql, reason in [
            ("DROP SCHEMA public CASCADE", "DROP DATABASE or DROP SCHEMA"),
            ("DROP OWNED BY app_owner", "DROP OWNED"),
            ("DROP ROLE r", "DROP ROLE, USER or GROUP"),
            ("SELECT * FROM account", TABLES),
            ("SELECT to_regclass('session')", TABLES),
            ("ALTER ROLE app_content LOGIN", "ALTER ROLE"),
            ("INSERT INTO t (k) VALUES ('p') ON CONFLICT (k) DO UPDATE SET password = 'p'", "PASSWORD"),
            ("SELECT * FROM pg_shadow", "pg_shadow"),
        ]:
            with self.subTest(sql=sql):
                self.assertBlocked(self.prod(sql), reason)
                self.assertBlocked(self.sql(sql), reason)

    def test_the_log_names_the_bulk_change(self):
        self.prod("TRUNCATE task")
        self.assertEqual(self.log_lines()[-1]["blocked"], ["TRUNCATE on production with no backup branch from the last 60 minutes"])
        self.backup()
        self.prod("TRUNCATE task")
        self.assertEqual(self.log_lines()[-1]["blocked"], [])


if __name__ == "__main__":
    unittest.main()
