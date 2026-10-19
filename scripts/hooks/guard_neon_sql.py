#!/usr/bin/env python3
"""Optional PreToolUse hook for the Neon connector's run_sql and run_sql_transaction.

Off by default; docs/optional-integrations.md says how to enable it. Permission
rules can't look inside SQL, so this does.

Blocks (exit 2, reason on stderr) a call whose SQL:
- contains DROP, TRUNCATE, ALTER ROLE, ALTER USER, PASSWORD, pg_authid or
  pg_shadow (the view of pg_authid's password hashes);
- names a table in PROTECTED_TABLES (by default Better Auth's account, session and
  verification tables, which hold credentials and sessions; edit it for your schema);
- has a DELETE or UPDATE statement without WHERE;
- can't be read from the tool input.

It matches words, case-insensitively, and errs on the side of blocking. It
guards against mistakes; it can't parse Postgres, so it isn't a sandbox.

Every statement, blocked or not, is appended as one JSON line with the time
and the calling agent to workspaces/neon-sql-audit.log
(outside git). If the log can't be written, the call is blocked.
"""

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

SQL_TOOLS = {"mcp__claude_ai_Neon__run_sql", "mcp__claude_ai_Neon__run_sql_transaction"}
AUDIT_LOG = Path("workspaces/neon-sql-audit.log")
PROTECTED_TABLES = ["account", "session", "verification"]

FORBIDDEN = [
    (re.compile(r"\bdrop\b", re.I), "DROP"),
    (re.compile(r"\btruncate\b", re.I), "TRUNCATE"),
    (re.compile(r"\balter\s+role\b", re.I), "ALTER ROLE"),
    (re.compile(r"\balter\s+user\b", re.I), "ALTER USER"),
    (re.compile(r"\bpassword\b", re.I), "PASSWORD"),
    (re.compile(r"\bpg_(?:authid|shadow)\b", re.I), "pg_authid or pg_shadow"),
    (re.compile(r"\b(?:" + "|".join(map(re.escape, PROTECTED_TABLES)) + r")\b", re.I),
     "the " + ", ".join(PROTECTED_TABLES[:-1]) + " or " + PROTECTED_TABLES[-1] + " table"),
]
DELETE_OR_UPDATE = re.compile(r"\b(?:delete|update)\b", re.I)
WHERE = re.compile(r"\bwhere\b", re.I)
STRING_LITERAL = re.compile(r"'(?:[^']|'')*'")


def statements(tool_name: str, tool_input: dict):
    """The SQL strings of the call, or None if they can't be read."""
    if tool_name.endswith("__run_sql"):
        sql = tool_input.get("sql")
        return [sql] if isinstance(sql, str) else None
    sqls = tool_input.get("sql_statements")
    if isinstance(sqls, list) and all(isinstance(s, str) for s in sqls):
        return sqls
    return None


def problems(sql: str) -> list:
    found = [label for pattern, label in FORBIDDEN if pattern.search(sql)]
    # Splitting on every ';' (even inside a string) only adds fragments, so it can block more, never less.
    if any(DELETE_OR_UPDATE.search(part) and not WHERE.search(part) for part in sql.split(";")):
        found.append("DELETE or UPDATE without WHERE")
    return found


def for_log(sql: str) -> str:
    """Keep passwords out of the audit log."""
    return STRING_LITERAL.sub("'<redacted>'", sql) if re.search(r"\bpassword\b", sql, re.I) else sql


def block(reason: str) -> None:
    print(reason, file=sys.stderr)
    sys.exit(2)


def main() -> None:
    try:
        event = json.load(sys.stdin)
    except json.JSONDecodeError:
        block("Blocked: the Neon SQL guard couldn't read the tool call.")
    tool_name = event.get("tool_name")
    if tool_name not in SQL_TOOLS:
        return
    tool_input = event.get("tool_input") or {}
    sqls = statements(tool_name, tool_input)
    if not sqls:
        block("Blocked: the Neon SQL guard found no SQL in the tool input. Pass `sql` (run_sql) or `sql_statements` (run_sql_transaction).")

    found = {sql: problems(sql) for sql in sqls}
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    root = Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path(__file__).resolve().parents[2])
    log = root / AUDIT_LOG
    try:
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("a", encoding="utf-8") as f:
            for sql in sqls:
                f.write(json.dumps({
                    "time": now,
                    "agent": event.get("agent_type") or "main",
                    "agent_id": event.get("agent_id"),
                    "tool": tool_name,
                    "project_id": tool_input.get("project_id"),
                    "branch_id": tool_input.get("branch_id"),
                    "blocked": found[sql],
                    "sql": for_log(sql),
                }, ensure_ascii=False) + "\n")
    except OSError as e:
        block(f"Blocked: the Neon SQL audit log {AUDIT_LOG} can't be written ({e.strerror}).")

    hits = sorted({label for labels in found.values() for label in labels})
    if hits:
        block(
            f"Blocked by the Neon SQL guard: {'; '.join(hits)}. "
            "Schema changes go only through the repo's migrations; never touch the protected tables "
            f"({', '.join(PROTECTED_TABLES)}) or pg_authid, and never set or read a password."
        )


if __name__ == "__main__":
    main()
