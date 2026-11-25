"""The Neon connector's update_branch: the rules guard_marketing_tools.py holds it to, by calling
branch_reason for that tool name.

Backup branches cost money, so agents may make them expire and clean them up; never the production
(default) branch or a branch with children. So update_branch passes only a call that sets an expiry and
changes nothing else:
- from the cto or a staff-engineer, the two agents that list the tool;
- with exactly project_id, branch_id and expires_at: no name (a rename), no protected, nothing else;
- with expires_at a time with a zone, after now and at most 30 days ahead (Neon's limit), so an
  expiry is never removed;
- with expires_at no earlier than the branch's created_at plus 24 hours (FLOOR), created_at as the
  caller's read (the last item) shows it; a read with no created_at with a zone is refused. So no
  agent expires another session's fresh backup, or one still inside a product's restore window;
- where company.json's integrations "neon" names the default branch of each of the company's Neon projects
  ("default_branches", by id): without that list every call is refused;
- on a br- id that isn't one of them (refused before any transcript is read);
- on a branch that the caller's own latest read of it (a list_branches, get_branch or create_branch
  result in its transcript, at most 30 minutes old, same project) showed named backup-... or
  gate-..., not the default (or primary) branch and not protected, and that no branch the caller
  read names as its parent.
  Only a timestamped read is the latest (a compaction's copy has none); any read's children count.

update_branch takes a branch id, not a name, so the name, the default flag and created_at come
from the caller's own transcript, found the way guard_agent_control.py finds its spawns. Neon's own
refusal is the second line: no expiry on the default branch, a protected one or one with children; the
24-hour floor is this hook's own. A call it can't check (bad input, no transcript, no fresh read of the
caller's own, a company.json that can't be read) is refused. It stops mistakes; it isn't a sandbox.

Every call, passed or not, is appended as one JSON line to the Neon audit log,
workspaces/neon-sql-audit.log (outside git), which guard_neon_sql.py also writes; if the log can't be
written, the call is refused. It approves nothing: a passed call still goes to Claude Code's own
permission check, as the CEO's Gmail send does.
"""

import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

UPDATE_BRANCH = "mcp__claude_ai_Neon__update_branch"
READS = {"mcp__claude_ai_Neon__list_branches", "mcp__claude_ai_Neon__get_branch", "mcp__claude_ai_Neon__create_branch"}
ROLES = {"cto", "staff-engineer"}
KEYS = {"project_id", "branch_id", "expires_at"}
PREFIXES = ("backup-", "gate-")
MAX_AHEAD = timedelta(days=30)
FLOOR = timedelta(hours=24)  # no expiry earlier than this after the branch's created_at
FRESH = timedelta(minutes=30)
AGENT_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
BRANCH_ID = re.compile(r"br-[a-z0-9-]{1,60}")  # an id, never a name such as production or main
AUDIT_LOG = Path("workspaces/neon-sql-audit.log")


def parse_time(value):
    """The time, if it is an ISO 8601 string with a zone; else None."""
    if not isinstance(value, str):
        return None
    try:
        t = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)  # Python 3.9 has no Z
    except ValueError:
        return None
    return t if t.tzinfo else None


def own_transcript(event: dict) -> Path:
    """The caller's own transcript: the main one, or subagents/agent-<id>.jsonl beside it (guard_agent_control.py)."""
    transcript = Path(event["transcript_path"])
    agent_id = event.get("agent_id")
    if not agent_id:
        return transcript
    if not AGENT_ID.match(str(agent_id)):
        raise ValueError("the caller's agent ID is malformed")
    session_dir = transcript.parent.parent if transcript.parent.name == "subagents" else transcript.with_suffix("")
    return session_dir / "subagents" / f"agent-{agent_id}.jsonl"


def branches_in(content):
    """The branch objects in a tool result: its text is a JSON list (list_branches) or one object, either of them plain
    or as the one value of {"data": …}; any other wrapper shows no branch."""
    if isinstance(content, str):
        texts = [content]
    elif isinstance(content, list):
        texts = [c.get("text") for c in content if isinstance(c, dict) and c.get("type") == "text"]
    else:
        texts = []
    for text in texts:
        try:
            data = json.loads(text)
        except (TypeError, json.JSONDecodeError):
            continue
        if isinstance(data, dict) and list(data) == ["data"]:
            data = data["data"]  # the envelope the connector may put a result in
        for branch in data if isinstance(data, list) else [data]:
            if isinstance(branch, dict):
                yield branch


def reads_of(transcript: Path, branch_id: str):
    """(when, branch) for each read of the branch, oldest first, and whether a read branch has it as its parent."""
    calls, seen, has_child = set(), [], False
    with transcript.open(encoding="utf-8", errors="replace") as f:
        for line in f:
            if "claude_ai_Neon__" not in line and branch_id not in line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            message = entry.get("message") if isinstance(entry, dict) else None
            content = message.get("content") if isinstance(message, dict) else None
            for item in content if isinstance(content, list) else []:
                if not isinstance(item, dict):
                    continue
                if item.get("type") == "tool_use" and message.get("role") == "assistant" and item.get("name") in READS:
                    calls.add(item.get("id"))
                elif item.get("type") == "tool_result" and item.get("tool_use_id") in calls and not item.get("is_error"):
                    for branch in branches_in(item.get("content")):
                        if branch.get("id") == branch_id:
                            seen.append((parse_time(entry.get("timestamp")), branch))
                        if branch.get("parent_id") == branch_id:
                            has_child = True
    return seen, has_child


def default_branches(root: Path) -> "list | None":
    """The ids integrations "neon" names, or None where it names none. A value of the wrong kind raises."""
    import company_config  # here, inside branch_reason()'s fail-closed handling

    own = company_config.integration("neon", root)
    ids = None if own is None else own.get("default_branches")
    if ids is not None and not (isinstance(ids, list) and all(isinstance(i, str) and BRANCH_ID.fullmatch(i) for i in ids)):
        raise ValueError("integrations neon: default_branches is a list of br- ids")
    return ids or None


def check(event: dict, root: Path, now: datetime):
    """The reasons to refuse the call (none: let it through), and the branch's name as last read."""
    tool_input = event.get("tool_input")
    if not isinstance(tool_input, dict):
        return ["the tool input isn't an object"], None
    found = []
    if event.get("agent_type") not in ROLES:
        found.append(f"only the cto and staff-engineer set expiries, not {event.get('agent_type') or 'a plain session'}")
    extra = sorted(set(tool_input) - KEYS)
    if extra:
        found.append(f"it changes more than the expiry ({', '.join(extra)}); pass only project_id, branch_id and expires_at")
    expires = parse_time(tool_input.get("expires_at"))
    if expires is None:
        found.append("expires_at must be a time with a zone, such as 2026-01-18T12:00:00Z; an expiry is never removed")
    elif not now < expires <= now + MAX_AHEAD:
        found.append("expires_at must be after now and at most 30 days ahead")
    project_id, branch_id = tool_input.get("project_id"), tool_input.get("branch_id")
    if not (isinstance(project_id, str) and project_id and isinstance(branch_id, str) and branch_id):
        return found + ["give both project_id and branch_id"], None
    defaults = default_branches(root)
    if defaults is None:
        return found + ['company.json\'s integrations "neon" names no default_branches, so no agent sets an expiry '
                        "(docs/guards.md)"], None
    if branch_id in defaults:
        return found + [f"{branch_id} is a default branch of the company's Neon projects, "
                        "which never gets an expiry"], None
    if not BRANCH_ID.fullmatch(branch_id):
        return found + [f"branch_id must be a br- id, not {branch_id!r}"], None

    seen, has_child = reads_of(own_transcript(event), branch_id)
    if not seen:
        return found + [f"no list_branches, get_branch or create_branch result of yours shows {branch_id}; "
                        "read it first, in a call of its own"], None
    dated = [read for read in seen if read[0] is not None]  # a compaction copies a result with no timestamp
    read_at, branch = (dated or seen)[-1]  # none dated: read_at is None, refused below
    name = branch.get("name")
    if read_at is None or not now - FRESH <= read_at <= now:
        found.append(f"your last read of {branch_id} is more than 30 minutes old, or dated after now; read it again")
    created = parse_time(branch.get("created_at"))
    if created is None:
        found.append(f"your last read of {branch_id} shows no created_at with a zone, so the 24-hour floor "
                     "can't be checked; read it again")
    elif expires is not None and expires < created + FLOOR:
        found.append(f"expires_at must be at least 24 hours after {branch_id} was made (created_at "
                     f"{branch.get('created_at')}), so not before {(created + FLOOR).isoformat()}")
    if branch.get("project_id") != project_id:
        found.append(f"{branch_id} was read in project {branch.get('project_id')}, not {project_id}")
    if branch.get("default") is not False or branch.get("primary") is True:
        found.append(f"{branch_id} is, or may be, the default branch, which never gets an expiry")
    if branch.get("protected") not in (False, None):
        found.append(f"{branch_id} is, or may be, protected; a protected branch never gets an expiry")
    if not (isinstance(name, str) and name.startswith(PREFIXES)):
        found.append(f"{branch_id} is named {name!r}; only backup- and gate- branches get an expiry")
    if has_child:
        found.append(f"a branch you read has {branch_id} as its parent; a branch with children never gets an expiry")
    return found, name


def branch_reason(event: dict, root: Path, now=None) -> "str | None":
    """The reason to refuse this update_branch, or None to let it through; either way, the call is logged."""
    now = now or datetime.now(timezone.utc)
    try:
        found, name = check(event, root, now)
    except Exception as error:  # noqa: BLE001 - a call it can't check is refused, and still logged
        found, name = [f"the Neon branch guard couldn't check the call ({type(error).__name__}: {error})"], None
    tool_input = event.get("tool_input")
    given = tool_input if isinstance(tool_input, dict) else {}
    log = root / AUDIT_LOG
    try:
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("a", encoding="utf-8") as f:
            f.write(json.dumps({
                "time": now.isoformat(timespec="seconds"),
                "agent": event.get("agent_type") or "main",
                "agent_id": event.get("agent_id"),
                "tool": UPDATE_BRANCH,
                "project_id": given.get("project_id"),
                "branch_id": given.get("branch_id"),
                "branch_name": name,
                "blocked": found,
                "input": tool_input,
            }, ensure_ascii=False) + "\n")
    except OSError as e:
        return f"the Neon audit log {AUDIT_LOG} can't be written ({e.strerror})"
    if not found:
        return None
    return (f"{'; '.join(found)}. update_branch only sets an expiry, at least 24 hours after the branch was made "
            "and at most 30 days ahead, on a backup- or gate- "
            "branch that isn't the default branch or protected and has no children")
