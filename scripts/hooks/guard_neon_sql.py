#!/usr/bin/env python3
"""PreToolUse hook for a Neon connector's run_sql and run_sql_transaction, by whatever name the account
gives the connector, if "neon" is in it. Always on: permission rules can't look inside SQL, so this does.
Its settings are company.json's integrations "neon"; without that entry it refuses every call (an empty
one, {}, gives the rules below).

Data and schema changes pass: DELETE and UPDATE with or without WHERE, TRUNCATE, every other DROP; the
bulk ones only after a backup branch (below). It blocks (exit 2, reason on stderr) a call whose SQL:
- drops a database, a schema or all a role owns: the word DROP, then only whitespace or comments (nested
  ones too), then DATABASE, SCHEMA or OWNED. It reads strings too, so `EXECUTE 'DROP SCHEMA x'` is caught,
  and `ALTER TABLE t DROP schema` (a column named schema) is refused: write DROP COLUMN;
- drops a role: DROP, then ROLE, USER or GROUP, found the same way; or contains ALTER ROLE, ALTER USER,
  PASSWORD, pg_authid or pg_shadow (the view of pg_authid's password hashes);
- names a protected table anywhere but in a data string: account, session and verification, which hold
  credentials and sessions in common sign-in libraries, and those "protected_tables" adds. Anywhere: in
  code, a quoted name or a comment, in a string read as code (the bulk check's, below, or one in the
  parentheses of query_to_xml, table_to_xml and their kin, ts_stat, ts_rewrite, crosstab or connectby), and
  in every string of a statement that names a reader (READERS: those calls, cron.*, dblink, xpath_table,
  PROGRAM, EXECUTE, FUNCTION, PROCEDURE or DO, quoted or not) or reads pg_stats, pg_stats_ext or
  pg_statistic, whose rows hold sampled column values. Elsewhere a string is data only right after a
  comparison or pattern operator (=, <>, !=, <, >, <=, >=, LIKE, ILIKE, SIMILAR TO, the ~ family; not =>
  or :=), or in the list of IN, or of ANY, ALL or SOME (ARRAY[...]) after one: a value compared, a LIKE or
  regex pattern. Every other string counts;
- makes a bulk change on a project in "production_projects" (none named: every project), or with no
  project_id, with no backup branch from the last 60 minutes. Bulk: UPDATE or DELETE with no WHERE of its
  own, after it at its own depth of parentheses (a subquery's or a CTE's doesn't count; not an upsert's DO
  UPDATE SET, FOR UPDATE, ON DELETE, a trigger's or a privilege's), TRUNCATE (not a trigger's or a
  privilege's), DROP TABLE, and ALTER TABLE ... DROP [COLUMN]. This check skips comments, data strings and
  quoted names, but reads as code, in parentheses, every string in a DO statement, right after AS (a
  function's body), in a pg_cron or dblink call, or inside a string read as code (EXECUTE's dynamic SQL),
  E'' and U&'' escapes undone. Only a call no other check blocks gets it. The backup: a create_branch on
  that project whose parent_id is the call's branch_id (both left out: the default branch), that succeeded
  in the last 60 minutes in this session's main transcript or a subagent's (the layout
  guard_agent_control.py reads; a search still running 5 seconds after the hook started finds none);
- can't be read from the tool input, makes the guard fail in any way, a company.json that can't be read
  included, or is still being checked 7 seconds after the hook started (then unlogged).

"bulk_after_backup": false tightens it: DROP and TRUNCATE, in code, a comment or a string, and an UPDATE or
DELETE without a WHERE of its own are refused, backup or not; schema changes then go only through the repo's
migrations. Where its two readings of WHERE differ (an upsert's DO UPDATE SET, ON DELETE CASCADE), it blocks.

Where Postgres may pair the quotes otherwise than it does (a plain string with a backslash before a quote,
code with a character past ASCII), the table check reads the rest of the SQL as it stands. It matches
words, case-insensitively, and errs on the side of blocking. It guards against mistakes; it can't parse
Postgres, so it isn't a sandbox: a database role with no rights on a table is what keeps that table out of
reach.

Every statement, blocked or not, is appended as one JSON line with the time and the calling agent to
workspaces/neon-sql-audit.log (outside git). If the log can't be written, the call is blocked.
"""

import json
import os
import re
import signal
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

START = time.monotonic()
SQL_TOOL = re.compile(r"mcp__[^/]*neon[^/]*__run_sql(_transaction)?", re.I)
AUDIT_LOG = Path("workspaces/neon-sql-audit.log")
PROTECTED_TABLES = ["account", "session", "verification"]
CREATE_BRANCH = "mcp__claude_ai_Neon__create_branch"
FRESH = timedelta(minutes=60)
DEADLINE = 7  # seconds from the hook's start: well under its 10-second timeout in settings.json
SEARCH_SECONDS = 5  # from the hook's start; a backup search still running then finds none
NO_BACKUP = " on production with no backup branch from the last 60 minutes"
NO_WHERE = "DELETE or UPDATE without WHERE"

FORBIDDEN = [
    (re.compile(r"\balter\s+role\b", re.I), "ALTER ROLE"),
    (re.compile(r"\balter\s+user\b", re.I), "ALTER USER"),
    (re.compile(r"\bpassword\b", re.I), "PASSWORD"),
    (re.compile(r"\bpg_(?:authid|shadow)\b", re.I), "pg_authid or pg_shadow"),
]
DROP = re.compile(r"\bdrop\b", re.I)
TRUNCATE = re.compile(r"\btruncate\b", re.I)
DELETE_OR_UPDATE = re.compile(r"\b(?:delete|update)\b", re.I)
WHERE = re.compile(r"\bwhere\b", re.I)
# What DROP mustn't be followed by, past whitespace and comments.
DROPPED = [
    (re.compile(r"(?:database|schema)\b", re.I), "DROP DATABASE or DROP SCHEMA"),
    (re.compile(r"owned\b", re.I), "DROP OWNED"),
    (re.compile(r"(?:role|user|group)\b", re.I), "DROP ROLE, USER or GROUP"),
]
# bulk() reads these left to right: parentheses, WHERE and the writes.
EVENT = re.compile(r"[()]|\b(?:where|update|delete|truncate)\b", re.I)
# Before UPDATE, DELETE or TRUNCATE, these make it a clause, not a statement: an upsert's DO UPDATE SET, FOR [NO KEY]
# UPDATE, ON DELETE CASCADE, a trigger's BEFORE, AFTER, OR or INSTEAD OF, a privilege in GRANT, REVOKE or a list.
CLAUSE = re.compile(r"\b(?:do|for|key|on|or|of|before|after|grant|revoke)\b|,", re.I)
SET = re.compile(r"set\b", re.I)
# For bulk(), read left to right: a quoted identifier, a comment's start, a dollar quote, an E'' string (where \' is a
# quote), a U&'' string or a string literal, so a quote inside one can't shift the strings after it.
TOKEN = re.compile(
    r"\"(?:[^\"]|\"\")*\"|--|/\*|(?<![\w$])\$((?:[^\W0-9]\w*)?)\$.*?\$\1\$|(?<![\w$])[eE]'(?:[^'\\]|\\.|'')*'"
    r"|(?<![\w$])[uU]&'(?:[^']|'')*'|'(?:[^']|'')*'",
    re.S,
)
# The escapes of an E'' and a U&'' string, so `\104ELETE` reads as DELETE.
E_ESCAPE = re.compile(r"''|\\(?:(?P<octal>[0-7]{1,3})|(?P<hex>x[0-9a-fA-F]{1,2}|u[0-9a-fA-F]{4}|U[0-9a-fA-F]{8})|(?P<other>.))", re.S)
U_ESCAPE = re.compile(r"''|\\(?:(?P<hex>[0-9a-fA-F]{4}|\+[0-9a-fA-F]{6})|(?P<other>.))", re.S)
DO = re.compile(r"\s*do\b", re.I)  # a DO statement: every string in it is code
# A string right after AS is a function's body; one inside pg_cron's or dblink's call is SQL it runs. Inside: in its
# parentheses, after its other arguments, which may be calls of their own (`dblink(current_setting('c'), '...')`).
INSIDE = r"\s*\((?:[^()]|\([^()]*\))*$"
CODE_BEFORE = re.compile(r"\bas$|\b(?:cron\s*\.\s*(?:schedule\w*|alter_job)|dblink\w*)" + INSIDE, re.I)
# For the table check only, a string one of these runs as a query or reads as a table's name is code too. The bulk
# check leaves them out: the query they run can't write.
QUERY_BEFORE = re.compile(r"\b(?:(?:query|table)_to_xml\w*|ts_stat|ts_rewrite|crosstab\w*|connectby)" + INSIDE, re.I)
# Where Postgres may pair the quotes otherwise, so the table check reads the rest as it stands: a plain string with a
# backslash right before a quote ('a\', read on past that quote with standard_conforming_strings off), and code with a
# character past ASCII (a $—$ dollar tag, or a name ending in one before E'').
BACKSLASH_QUOTE = re.compile(r"(?<!\\)(?:\\\\)*\\'")
NON_ASCII = re.compile(r"[^\x00-\x7f]")
# Their rows hold sampled column values (most_common_vals, histogram_bounds): a table named in any string of a
# statement that reads them counts.
STATS = re.compile(r"\bpg_stat(?:s(?:_ext(?:_exprs)?)?|istic(?:_ext(?:_data)?)?)\b", re.I)
# A statement naming one of these may run a string as SQL or read a table's name from one, so every string in it
# counts too: QUERY_BEFORE's and CODE_BEFORE's calls, xpath_table, COPY's PROGRAM, EXECUTE, a function or procedure
# made, and DO. Quoted names count, as the table check reads them.
READERS = re.compile(r"\b(?:(?:query|table|cursor|schema|database)_to_xml\w*|ts_stat|ts_rewrite|crosstab\w*|connectby|"
                     r"cron\s*\.\s*\w+|dblink\w*|xpath_table|program|execute|function|procedure|do)\b", re.I)
# Elsewhere a string is data only right after a comparison or pattern operator (not => or :=), or in the list of IN
# or of ANY, ALL or SOME (ARRAY[...]) after one: a value compared, a LIKE or regex pattern.
COMPARE = r"(?:(?<![=:<>!])=|<>|!=|<=|>=|(?<![-=>])>|(?<!<)<|\b(?:i?like|similar\s+to)|!?~~?\*?)"
DATA_BEFORE = re.compile(rf"(?:{COMPARE}|(?:{COMPARE}\s*\b(?:any|all|some)\s*\(\s*(?:array\s*\[)?|\bin\s*\()(?:\s*,)*)$", re.I)
ALTER = re.compile(r"\balter\b", re.I)
TABLE = re.compile(r"table\b", re.I)
COLUMN = re.compile(r"column\b", re.I)
NOT_A_COLUMN = re.compile(r"(?:constraint|default|not|expression|identity)\b", re.I)  # ALTER TABLE's other DROPs
STRING_LITERAL = re.compile(r"'(?:[^']|'')*'")


def after_space_and_comments(sql: str, i: int) -> int:
    """Where the next token after position i starts, past whitespace, -- comments and nested /* */ comments."""
    while True:
        while i < len(sql) and sql[i].isspace():
            i += 1
        if sql.startswith("--", i):  # Postgres ends it at \r or \n
            ends = [j for j in (sql.find("\n", i), sql.find("\r", i)) if j >= 0]
            i = min(ends) if ends else len(sql)
        elif sql.startswith("/*", i):
            depth = 0
            while i < len(sql):
                if sql.startswith("/*", i):
                    depth, i = depth + 1, i + 2
                elif sql.startswith("*/", i):
                    depth, i = depth - 1, i + 2
                    if depth == 0:
                        break
                else:
                    i += 1
        else:
            return i


def dropped(sql: str) -> list:
    """The labels of what the SQL drops that it mustn't."""
    starts = [after_space_and_comments(sql, m.end()) for m in DROP.finditer(sql)]
    return [label for pattern, label in DROPPED if any(pattern.match(sql, i) for i in starts)]


def unescaped(m: re.Match) -> str:
    """One escape of an E'' or a U&'' string, as Postgres reads it."""
    if m.group() == "''":
        return "'"
    found = m.groupdict()
    if found.get("octal"):
        return chr(int(found["octal"], 8))
    if found.get("hex"):
        return chr(min(int(found["hex"].lstrip("xuU+"), 16), 0x10FFFF))
    return " " if found["other"] in "bfnrt" else found["other"]  # \b \f \n \r \t are blanks between words


def unquoted(token: str) -> str:
    """A string literal's text: a dollar quote's as it stands, an E'' or U&'' string's with its escapes undone."""
    if token.startswith("$"):
        tag = token[:token.index("$", 1) + 1]
        return token[len(tag):-len(tag)]
    body = token[token.index("'") + 1:-1]
    if token[0] in "eE":
        return E_ESCAPE.sub(unescaped, body)
    if token[0] in "uU":
        return U_ESCAPE.sub(unescaped, body)
    return body.replace("''", "'")


def code_only(sql: str, code: bool = False, names: bool = False) -> str:
    """The SQL as bulk() reads it: each comment and data string made a space, each quoted identifier the name _.
    Every string in a DO statement, right after AS (a function's body), in a pg_cron or dblink call, or inside a
    string read as code (EXECUTE's dynamic SQL) is code: its text stays, read the same way, in parentheses, so a ','
    before it can't make it a privilege list and a WHERE in it isn't the WHERE of a write outside it. code: sql is
    itself such a string. names: as the table check reads it, where comments and quoted identifiers keep their text,
    a string in QUERY_BEFORE's calls is code too, any other string keeps its text unless DATA_BEFORE ends just before
    it, and from where Postgres may pair the quotes otherwise (BACKSLASH_QUOTE, NON_ASCII) the SQL stays as it
    stands."""
    out, before, statement, i = [], "", "", 0
    while m := TOKEN.search(sql, i):
        token, text = m.group(), sql[i:m.start()]
        if names and (NON_ASCII.search(text) or token[0] == "'" and BACKSLASH_QUOTE.search(token, 1)):
            return "".join(out) + sql[i:]
        statement = (statement + text).rsplit(";", 1)[-1].lstrip()[:64]  # the statement's start, outside strings
        before = (before + text).rstrip()[-64:]  # the code just before the token, each string a space
        if token in ("--", "/*"):
            i = after_space_and_comments(sql, m.start())
            text += " " + (sql[m.start():i] if names else "") + " "
        else:
            i = m.end()
            if token.startswith('"'):
                text += f" {token} " if names else " _ "
            elif code or DO.match(statement) or CODE_BEFORE.search(before) or names and QUERY_BEFORE.search(before):
                text += " (" + code_only(unquoted(token), True, names) + ") "
            elif names and not DATA_BEFORE.search(before):
                text += " " + unquoted(token) + " "
            else:
                text += " "
        before += " _ " if token.startswith('"') else " "
        out.append(text)
    return "".join(out) + sql[i:]


def bulk(sql: str) -> list:
    """The bulk changes in the SQL (module docstring), in one pass over each statement: a scan that rereads text
    can outlast the hook's time limit."""
    sql = code_only(sql)
    clauses = {after_space_and_comments(sql, m.end()): m.group().lower() for m in CLAUSE.finditer(sql)}
    found, start = set(), 0
    for part in sql.split(";"):
        depth, waiting = 0, set()  # waiting: the depths of an UPDATE or DELETE still without its own WHERE
        for m in EVENT.finditer(part):
            word, clause = m.group().lower(), clauses.get(start + m.start())
            if word == "(":
                depth += 1
            elif word == ")":
                if depth in waiting:
                    found.add(NO_WHERE)
                waiting.discard(depth)
                depth -= 1
            elif word == "where":
                waiting.discard(depth)
            elif clause and (clause != "do" or word == "update" and SET.match(part, after_space_and_comments(part, m.end()))):
                continue  # a clause; DO makes one only of an upsert's DO UPDATE SET, not of a rule's DO DELETE
            elif word == "truncate":
                found.add("TRUNCATE")
            else:
                waiting.add(depth)
        if waiting:
            found.add(NO_WHERE)
        alter_table = next((a.start() for a in ALTER.finditer(part)
                            if TABLE.match(part, after_space_and_comments(part, a.end()))), len(part))
        for m in DROP.finditer(part):
            i = after_space_and_comments(part, m.end())
            if TABLE.match(part, i):
                found.add("DROP TABLE")
            elif COLUMN.match(part, i) or (alter_table < m.start() and not NOT_A_COLUMN.match(part, i)):
                found.add("ALTER TABLE ... DROP COLUMN")
        start += len(part) + 1
    return sorted(found)


def items(data: bytes, needle: str):
    """Each (row, content item) of the transcript lines that hold needle. A transcript can be 100 MB, so only those."""
    i = data.find(needle.encode())
    while i >= 0:
        end = data.find(b"\n", i)
        end = len(data) if end < 0 else end
        try:
            row = json.loads(data[data.rfind(b"\n", 0, i) + 1:end])
        except ValueError:
            row = None
        content = (row.get("message") or {}).get("content") if isinstance(row, dict) else None
        for item in content if isinstance(content, list) else []:
            if isinstance(item, dict):
                yield row, item
        i = data.find(needle.encode(), end)


def backed_up(event: dict, tool_input: dict, now: datetime) -> bool:
    """True if a create_branch on the call's project, from the branch this call changes, succeeded in the last 60 minutes in
    this session's main transcript or a subagent's, the caller's own first. A search past SEARCH_SECONDS finds none:
    it mustn't outlast the hook's timeout."""
    if not event.get("transcript_path") or not tool_input.get("project_id"):
        return False
    transcript = Path(event["transcript_path"])
    session_dir = transcript.parent.parent if transcript.parent.name == "subagents" else transcript.with_suffix("")
    main = session_dir.parent / f"{session_dir.name}.jsonl"
    own = session_dir / "subagents" / f"agent-{event['agent_id']}.jsonl" if event.get("agent_id") else main
    since, deadline, seen = now - FRESH, START + SEARCH_SECONDS, set()
    for path in [own, main, *(session_dir / "subagents").glob("agent-*.jsonl")]:
        if time.monotonic() > deadline:
            return False
        if path in seen or not path.is_file() or path.stat().st_mtime < since.timestamp():
            continue
        seen.add(path)
        data = path.read_bytes()
        calls = {str(item.get("id")) for _, item in items(data, CREATE_BRANCH)
                 if item.get("type") == "tool_use" and item.get("name") == CREATE_BRANCH
                 and isinstance(item.get("input"), dict) and item["input"].get("project_id") == tool_input["project_id"]
                 and item["input"].get("parent_id") == tool_input.get("branch_id")}
        for call in calls:
            for row, item in items(data, call):
                if (item.get("type") == "tool_result" and item.get("tool_use_id") == call
                        and item.get("is_error") is not True and isinstance(row.get("timestamp"), str)
                        and datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00")) >= since):
                    return True
    return False


def statements(tool_name: str, tool_input: dict):
    """The SQL strings of the call, or None if they can't be read."""
    if tool_name.endswith("__run_sql"):
        sql = tool_input.get("sql")
        return [sql] if isinstance(sql, str) else None
    sqls = tool_input.get("sql_statements")
    if isinstance(sqls, list) and all(isinstance(s, str) for s in sqls):
        return sqls
    return None


def problems(sql: str, protected: list, bulk_after_backup: bool) -> list:
    """What the SQL holds that it mustn't; its words are read as it stands and with the escapes of its strings read as
    code undone."""
    texts = (sql, code_only(sql))
    if bulk_after_backup:
        found = dropped(sql)
    else:
        found = [label for pattern, label in ((DROP, "DROP"), (TRUNCATE, "TRUNCATE")) if any(map(pattern.search, texts))]
    found += [label for pattern, label in FORBIDDEN if any(map(pattern.search, texts))]
    tables = re.compile(r"\b(?:" + "|".join(map(re.escape, protected)) + r")\b", re.I)
    names = code_only(sql, names=True)
    if tables.search(names) or (STATS.search(names) or READERS.search(names)) and tables.search(sql):
        found.append("a protected table (" + ", ".join(protected) + ")")
    # Splitting on every ';' (even inside a string) only adds fragments, so it can block more, never less.
    if not bulk_after_backup and (
            any(DELETE_OR_UPDATE.search(part) and not WHERE.search(part) for part in sql.split(";")) or NO_WHERE in bulk(sql)):
        found.append(NO_WHERE)
    return found


def settings(root: Path) -> "tuple[list, bool, list] | None":
    """(protected tables, bulk_after_backup, production projects), or None where integrations has no "neon". A value of
    the wrong kind raises."""
    import company_config  # here, inside check()'s fail-closed handling

    own = company_config.integration("neon", root)
    if own is None:
        return None
    added, projects = own.get("protected_tables", []), own.get("production_projects", [])
    bulk_after_backup = own.get("bulk_after_backup", True)
    for names in (added, projects):
        if not (isinstance(names, list) and all(isinstance(name, str) and name for name in names)):
            raise ValueError("integrations neon: protected_tables and production_projects are lists of names")
    if not isinstance(bulk_after_backup, bool):
        raise ValueError("integrations neon: bulk_after_backup is true or false")
    return PROTECTED_TABLES + [name for name in added if name not in PROTECTED_TABLES], bulk_after_backup, projects


def for_log(sql: str) -> str:
    """Keep passwords out of the audit log."""
    return STRING_LITERAL.sub("'<redacted>'", sql) if re.search(r"\bpassword\b", sql, re.I) else sql


def block(reason: str) -> None:
    print(reason, file=sys.stderr)
    sys.exit(2)


def too_slow(*_) -> None:
    """Blocks at once, from the alarm: no exception that a handler could turn into exit 1."""
    os.write(2, f"Blocked: the Neon SQL guard was still checking this tool call after {DEADLINE} seconds.".encode())
    os._exit(2)


def main() -> None:
    # Every failure blocks by itself, and so does a check still running DEADLINE seconds after the hook started: the
    # hook entry's onFailure is the second line, and an older Claude Code ignores it.
    signal.signal(signal.SIGALRM, too_slow)
    signal.setitimer(signal.ITIMER_REAL, max(START + DEADLINE - time.monotonic(), 0.001))
    try:
        check(json.load(sys.stdin))
    except json.JSONDecodeError:
        block("Blocked: the Neon SQL guard couldn't read the tool call.")
    except Exception as e:
        block(f"Blocked: the Neon SQL guard failed on this tool call ({type(e).__name__}: {e}).")


def check(event: dict) -> None:
    tool_name = event.get("tool_name")
    if not isinstance(tool_name, str) or not SQL_TOOL.fullmatch(tool_name):
        return
    tool_input = event.get("tool_input") or {}
    sqls = statements(tool_name, tool_input)
    if not sqls:
        block("Blocked: the Neon SQL guard found no SQL in the tool input. Pass `sql` (run_sql) or `sql_statements` (run_sql_transaction).")

    root = Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path(__file__).resolve().parents[2])
    own = settings(root)
    if own is None:
        block('Blocked: company.json has no integrations "neon", so no agent runs SQL on Neon (docs/guards.md).')
    protected, bulk_after_backup, production = own
    found = {sql: problems(sql, protected, bulk_after_backup) for sql in sqls}
    moment = datetime.now(timezone.utc)
    project = tool_input.get("project_id")
    # A call the checks above block is blocked without the bulk check, so their refusals never wait on it.
    if bulk_after_backup and not any(found.values()) and (
            not production or not isinstance(project, str) or project in ("", *production)):  # no project_id: maybe production
        changes = {sql: bulk(sql) for sql in sqls}
        if any(changes.values()) and not backed_up(event, tool_input, moment):
            for sql in sqls:
                found[sql] += [label + NO_BACKUP for label in changes[sql]]
    now = moment.isoformat(timespec="seconds")
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
        parent = f"parent_id {tool_input['branch_id']}" if tool_input.get("branch_id") else "no parent_id"
        block(
            f"Blocked by the Neon SQL guard: {'; '.join(hits)}. "
            + (f"Fix: make a backup first, with {CREATE_BRANCH} (project_id {project or 'of the call: pass it'}, {parent}), "
               "then retry within 60 minutes. " if any(h.endswith(NO_BACKUP) for h in hits) else "")
            + ("Never drop a database, a schema, a role or all a role owns (to drop a column of such a name, write DROP "
               "COLUMN); never " if bulk_after_backup else
               "Schema changes go only through the repo's migrations, and a write has a WHERE of its own; never ")
            + f"touch the protected tables ({', '.join(protected)}) or pg_authid, and never set or read a "
            "password."
        )


if __name__ == "__main__":
    main()
