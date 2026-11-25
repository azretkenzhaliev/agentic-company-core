"""The CEO's email to the Board: the rules for the one Gmail write guard_marketing_tools.py is to let
through, by calling email_reason for that tool name; every other Gmail write stays refused there.

The claude.ai connector's send_message passes only:
- from the main session as the CEO: agent_type ceo and no agent_id (a subagent's hook input carries
  its agent_id, as guard_agent_control.py relies on);
- with only the keys to, subject and body: no cc, bcc, attachments, HTML body, draft or thread;
- to exactly the Board's own address, company.json's `board_email`; while that is empty, every email is
  refused;
- with a subject of at most 200 characters starting "[CEO]", with no control or line-separator
  character, a plain body of at most 4,000 characters, and no secret (scripts/kb_secrets.py) in either;
- with no daily cap, unless company.json's integrations "email" sets one: {"per_day": 6} lets through at
  most 6 a UTC day across this clone and its worktrees.

Each email let through is logged, its time and subject, never the body, in the main checkout's
workspaces/system/notify-log.jsonl (gitignored; a worktree finds it through its .git file). It logs when
the guard lets the call through, so one that Claude Code's permission check then refuses, or that fails,
counts too: the error is towards fewer emails.

Any error here (a company.json that can't be read, a log line a cap can't count) is raised, and
guard_marketing_tools.py refuses the call. It stops mistakes; it isn't a sandbox.
"""

import fcntl
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import company_config  # noqa: E402
from kb_secrets import find_secrets  # noqa: E402

SEND = "mcp__claude_ai_Gmail__send_message"
PREFIX = "[CEO]"
MAX_SUBJECT = 200
MAX_BODY = 4000
LINE_SEPARATORS = "\u2028\u2029"
LOG = Path("workspaces") / "system" / "notify-log.jsonl"
KEYS = {"to", "subject", "body"}
GITDIR = "gitdir: "  # how a worktree's .git file starts


def form_reason(event: dict, root: Path) -> "str | None":
    """Why this send_message isn't the CEO's email to the Board, or None if it is."""
    if event.get("tool_name") != SEND:
        return f"only {SEND} sends the CEO's email to the Board"
    agent = event.get("agent_type") or ""
    if agent != "ceo" or event.get("agent_id"):
        who = f"the {agent}" if agent else "a session without a company role"
        return f"only the CEO's main session emails the Board, not {who}{' subagent' if event.get('agent_id') else ''}"
    tool_input = event.get("tool_input")
    if not isinstance(tool_input, dict):
        return "the input isn't an object"
    extra = sorted(set(tool_input) - KEYS)
    if extra:
        return (f"an email to the Board has only to, subject and body, not {', '.join(extra)} "
                "(no cc, bcc, attachments, HTML, drafts or threads)")
    board = company_config.load(root)["board_email"]
    if not isinstance(board, str) or not board:
        return "company.json names no board_email, so the CEO emails nobody (/onboard-company sets it)"
    if tool_input.get("to") != [board]:
        return f'"to" must be exactly ["{board}"], the Board\'s own address, and no one else'
    subject = tool_input.get("subject")
    if (not isinstance(subject, str) or not subject.startswith(PREFIX) or len(subject) > MAX_SUBJECT
            or any(ord(c) < 0x20 or 0x7f <= ord(c) <= 0x9f or c in LINE_SEPARATORS for c in subject)):
        return f'the subject must be one line of at most {MAX_SUBJECT} characters starting "{PREFIX}"'
    body = tool_input.get("body", "")
    if not isinstance(body, str) or len(body) > MAX_BODY:
        return f"the body must be plain text of at most {MAX_BODY:,} characters"
    if find_secrets(subject + "\n" + body):
        return "the email holds a secret; name where a secret lives, never its value"
    return None


def main_checkout(root: Path) -> Path:
    """The repo's main checkout: root itself, or for a worktree the folder that holds git's common dir."""
    dot_git = root / ".git"
    if dot_git.is_dir():
        return root
    pointer = dot_git.read_text(encoding="utf-8").strip()
    if not pointer.startswith(GITDIR):
        raise ValueError(f'{dot_git} doesn\'t start "{GITDIR}"')
    gitdir = Path(pointer.removeprefix(GITDIR))
    gitdir = gitdir if gitdir.is_absolute() else root / gitdir
    commondir = (gitdir / "commondir").read_text(encoding="utf-8").strip()
    if not commondir:
        raise ValueError(f"{gitdir / 'commondir'} is empty")
    return (gitdir / commondir).resolve().parent


def count_reason(root: Path, subject: str) -> "str | None":
    """Refuse past the founder's daily cap, if one is set; otherwise log this email (time and subject) and return None."""
    settings = company_config.integration("email", root)
    per_day = None if settings is None else settings.get("per_day")
    if per_day is not None and type(per_day) is not int:
        return 'company.json\'s integrations "email" "per_day" must be a whole number, or null for no cap'
    log = main_checkout(root) / LOG
    log.parent.mkdir(parents=True, exist_ok=True)
    with open(log, "a+", encoding="utf-8") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)  # two sends at once can't both take the last place
        now = datetime.now(timezone.utc)  # after the lock, so a wait across midnight counts the new day
        if per_day is not None:
            today = now.strftime("%Y-%m-%d")
            handle.seek(0)
            sent = sum(1 for line in handle if line.strip() and json.loads(line)["time"].startswith(today))
            if sent >= per_day:
                return (f"{per_day} emails to the Board already today (UTC, {LOG}). The rest waits for the next "
                        "report or tomorrow, never another route")
        handle.write(json.dumps({"time": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "subject": subject}) + "\n")
    return None


def email_reason(event: dict, root: Path) -> "str | None":
    """The reason to refuse this send_message, or None to let it through (and log it)."""
    return form_reason(event, root) or count_reason(root, event["tool_input"]["subject"])
