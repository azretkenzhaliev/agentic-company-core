#!/usr/bin/env python3
"""PreToolUse hook for MCP tools and Bash: the marketing department's tool limits.

Blocks (exit 2, reason on stderr):
- any agent writing a Notion property only the Board sets (Approval, AI label,
  Board comment, and the Board desk's Your answer and Your words), or any property outside AGENT_PROPERTIES (so a
  property id or a renamed field doesn't get round it);
- any agent using Notion's structural writes (delete, duplicate, move, schemas,
  views);
- any caller's Notion write that names a page, database or row of the Board desk (the ids in the main checkout's
  workspaces/board-desk/notion.json, hyphens or none; where that file isn't, a cloud session's or a fresh clone's
  checkout, the fixed ones setup copies to the tracked scripts/board_desk/desk_ids.json: the root, the pages, both
  databases and their data sources, no row): those are scripts/board_desk.py's and the Board's (a file that can't be
  read blocks every Notion write, and neither file, before setup, blocks none);
- agents outside marketing using Notion or Canva (the Board's own accounts);
- any caller using a Metricool tool other than a read (`get…`, `list…`), except the cmo's
  createScheduledPost of exactly what tools/marketing/publish/post.py rebuilds from an
  approved piece page, with autoPublish false (the Board publishes it), and
  any agent but the cmo and performance-analyst using Metricool at all;
- any caller using a Gmail tool other than a read (GMAIL_READS), and any agent but
  the analyst using Gmail at all, except the CEO main session's send_message to the
  Board's own address, in the form board_email.py holds;
- any caller using the Neon connector's update_branch for more than the cto's or a staff-engineer's
  expiry on a backup- or gate- branch, as neon_branch.py holds, which also logs every such call;
- any agent but the analyst using the Telegram server, and the analyst using it beyond
  list_messages on a channel named on knowledge/marketing/idea-sources.md;
- any caller using FastDL beyond the content tools scripts/hooks/fastdl.py gives the cmo, trend-researcher and
  reel-analyst, or giving it a login, a URL or host off instagram.com, an email address, a phone-like number or more
  text than its caps, and any caller using FastDL's four people tools under any connector's name;
- marketing agents using any other MCP tool, which covers every publish, DM,
  ad and browser tool, whatever account it comes from;
- the trend-researcher using Bash or any other MCP tool beyond the read-only Chrome steps
  scripts/hooks/trend_reader.py allows, on instagram.com, youtube.com and t.me. It is
  the one marketing role with a browser;
- the reel-analyst using any other MCP tool, or Bash beyond reads, tools/marketing/reels/watch.py and
  tools/marketing/reels/save.py's `post` and `covers` (not its `latest --account`, the cmo's);
- any caller using a Notion template (`template_id`, `apply_template`): a
  template copies its properties, the Board's fields included;
- marketing agents' Bash outside its allowlist (scripts/hooks/marketing_bash.py):
  reads, the marketing tools, and file moves inside workspaces/marketing/media/;
- any subagent's Bash call with run_in_background (background_bash.py), and any subagent's Bash command that
  rewrites a ceo-questions.md instead of appending to it (cq_write.py): every role, not only marketing, since this
  is the Bash hook that runs in every session and fails closed;
- an engineering subagent's Bash wait, a `while` or `until` loop that sleeps, with no $SECONDS bound in its test
  (bounded_wait.py);
- any caller's Bash command, the main session's included, that takes a PR out of a GitHub merge queue or cancels a
  workflow run (guard_merge_queue.py);
- any agent's Bash command (agent_type or agent_id, the CEO's main session included) that writes the Board's answers in
  knowledge/board/answers/ or the desk's state in workspaces/board-desk/, runs board_desk.py's run, hour, day or
  read, or its setup or attribution but in the CEO's main session (agent_type ceo, no agent_id), or reads the desk's
  Notion token (board_desk_bash.py).

All of it holds whatever company.json says. The limits on the marketing roles concern nobody else, so a company that
doesn't use them never meets them. The department's settings, read from company.json only where a rule needs them, can
only be missing one way: no reader profile, no approved Notion database, no post to schedule.

The Board-only fields, the desk's ids, templates and Notion's structural writes are blocked for
every caller, a session without agent_type included: the Board sets its fields
in Notion itself, and a port that doesn't send agent_type is still held. Other
limits apply by agent_type, which a port must supply. Why a hook: a Cursor port
has no per-agent tool lists, and hooks also hold in Claude Code when the main
session runs in auto or bypass mode. Any error, including unreadable input,
blocks the call (fail closed).

The server family comes from the `mcp__<server>__` part, case-insensitively,
because each account names its connectors differently (`mcp__claude_ai_Notion__`,
`mcp__notion__`).

Approves (an allow on stdout), once nothing above blocks it, a marketing role's normal call, so it
doesn't wait on a prompt, only if the founder asked for that: company.json, "integrations"."marketing"."no_prompts", a
list with "work" for the calls below and "fastdl" for FastDL's. Without it nothing is approved. "work" is the Bash marketing_bash.py passes for
the marketing agents and the reel-analyst, when all its paths are in the repo or the marketing folders and
it doesn't run footage/fetch.py, which takes any URL; the Chrome steps trend_reader.py passes; and the reads of
Notion, Canva and Metricool, Canva's export, Notion's file uploads, and a new Notion page in the
Marketing calendar or Swipe database, as each role is allowed them (APPROVED). "fastdl" is a FastDL call fastdl.py passes,
never the analyst's. Never a Metricool write, a Gmail
or Telegram tool, a Canva upload, import or comment, a Notion page update, attachment or comment, a new Notion
page anywhere else, any other tool, or any other call by an agent outside marketing or a session without agent_type:
those still go to Claude Code's own permission check. Another hook's block still
wins, and an allow doesn't get past Claude Code's check on paths outside the working directories: an
approved mkdir, mv or rm through a swipe/ or media/ folder that links out of the repo is still refused, so a linked
folder also needs an additionalDirectories entry in .claude/settings.local.json.
"""

import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(1, str(Path(__file__).resolve().parents[1]))

MARKETING_AGENTS = {"cmo", "content-producer", "content-reviewer", "performance-analyst"}
CANVA_AGENTS = {"cmo", "content-producer"}
NOTION_WRITERS = {"cmo", "content-producer"}
METRICOOL_AGENTS = {"cmo", "performance-analyst"}
GMAIL_AGENTS = {"analyst"}
TELEGRAM_AGENTS = {"analyst"}

# AI label: the Board's choice per post (SA-005). Your answer and Your words: the Board desk's answers.
BOARD_ONLY = {"approval", "ai label", "board comment", "your answer", "your words"}
AGENT_PROPERTIES = {
    "title", "name", "brand", "week", "date", "format", "pillar", "status",
    "kb page", "gemini flags", "preview",
    "reel url", "type", "file", "teardown",  # the Swipe database (the reel library)
}
NOTION_READS = {
    "notion-search", "notion-fetch", "notion-query-data-sources", "notion-query-multiple-data-sources",
    "notion-get-comments", "notion-get-file-download-urls", "notion-get-self", "notion-get-users",
}
NOTION_AGENT_WRITES = {
    "notion-create-pages", "notion-update-page", "notion-create-comment",
    "notion-create-file-upload", "notion-create-attachment",
}
# Canva is for the Board's hand edits: reading, exporting and handing over files. No AI generation
# (that goes through SA-005's capped key and its tracking), and no tool Canva adds later.
CANVA_PREFIXES = ("get-", "list-", "search-")
CANVA_TOOLS = {"read-design", "export-design", "resolve-shortlink", "help", "upload-asset-from-url",
               "create-upload-url", "import-design-from-url", "create-folder", "move-item-to-folder",
               "comment-on-design", "reply-to-comment"}
# Metricool (phase 1.5): reads only. Its writes schedule and publish posts, which only the Board does.
# A read is get/list followed by "_", "-" or a capital: get_brands, getBrandSettings (the claude.ai connector's
# names). Its writes are createScheduledPost, createScheduledPostForReview, updateScheduledPost and
# sendScheduledPostForReview.
METRICOOL_READ = re.compile(r"(get|list)[_\-A-Z]")
# Gmail (the Board's connector): the analyst reads mail when its order says so.
# An exact list, so a tool Gmail adds later stays off. Drafts stay off too: they're the Board's unsent writing.
# The one write: the CEO main session's send_message to the Board (board_email.py).
GMAIL_READS = {"search_threads", "get_thread", "get_message", "list_labels"}
# Telegram (the Board's account, through a local read-only server): each read names its chat, so the
# guard can hold the analyst to the channels on the idea-sources page and keep private chats out of reach. The
# server exposes no write tool (idea-sources.md, "The server"). The Telegram bot plugin is another server.
TELEGRAM = "mcp__telegram__"
IDEA_SOURCES = "knowledge/marketing/idea-sources.md"
TELEGRAM_CHANNEL = re.compile(r"(?<![\w.])@\w+|(?<![\w.-])-100\d+")  # a @handle, not an email's @, or a private id

FAMILIES = ("fastdl", "notion", "canva", "metricool", "gmail")

# What main() approves once decide() passes it (the docstring's "Approves"). Exact lists, as above.
APPROVED_BASH = MARKETING_AGENTS | {"reel-analyst"}  # the roles whose Bash marketing_bash.py holds
# Where an approved command's paths lie: the repo, and the marketing folders, which may link out of it.
APPROVED_BASH_PLACES = ("", "workspaces/marketing/media", "workspaces/marketing/inbox", "workspaces/marketing/swipe")
# A new page only in the two private marketing databases in the Board's workspace, the Marketing calendar and Swipe, by
# the data source ids in company.json ("integrations"."marketing"."notion"; knowledge/marketing/notion.md): with none
# set, no new page is approved. Under any other parent, which could be a publicly shared page, it would be sent outside
# (b1). Not notion-update-page or notion-create-attachment: each names a page id the guard can't tie to those databases.
DATABASES = ("calendar", "swipe")
APPROVED_NOTION = NOTION_READS | {"notion-create-file-upload"}
# The Board desk's Notion ids (board_desk.py setup writes them; gitignored, so read from the main checkout, else from
# setup's tracked copy): no Notion write through Claude's connector may name one.
DESK_IDS = Path("workspaces/board-desk/notion.json")
FIXED_DESK_IDS = Path("scripts/board_desk/desk_ids.json")  # setup's copy of the fixed ones, tracked: in every checkout
DESK_ID_KEYS = ("root", "pages", "databases", "rows")  # not "bot": the connection's user id names no page
NOTION_ID = re.compile(r"[0-9a-f]{32}")
# Canva's reads by name, not prefix, so a tool Canva adds later isn't approved: the connector's get-, list- and
# search- tools, but the job reads and video guide of the generation tools decide() refuses.
APPROVED_CANVA = {"read-design", "export-design", "resolve-shortlink", "help", "search-designs", "search-folders",
                  "search-brand-templates", "list-brand-kits", "list-comments", "list-folder-items", "list-replies",
                  "get-assets", "get-design-dataset", "get-brand-template-dataset", "get-export-formats"}


def split_mcp(tool_name: str):
    """(family, tool) for an MCP tool name, the family one of FAMILIES or 'other'; None if not MCP."""
    if not tool_name.startswith("mcp__") or "__" not in tool_name[5:]:
        return None
    server, tool = tool_name[5:].rsplit("__", 1)
    server = server.lower()
    family = next((f for f in FAMILIES if f in server), "other")
    return family, tool


def _parsed(value):
    if isinstance(value, str) and value.lstrip()[:1] in ("{", "["):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def property_names(value):
    """Every key of every `properties` mapping in value, JSON strings included."""
    value = _parsed(value)
    if isinstance(value, dict):
        for key, inner in value.items():
            props = _parsed(inner) if key == "properties" else None
            if isinstance(props, dict):
                yield from (str(k) for k in props)
            yield from property_names(inner)
    elif isinstance(value, list):
        for inner in value:
            yield from property_names(inner)


def uses_template(value) -> bool:
    """A `template_id` key or an `apply_template` command anywhere in value, JSON strings included."""
    value = _parsed(value)
    if isinstance(value, dict):
        return any(k == "template_id" or v == "apply_template" or uses_template(v) for k, v in value.items())
    if isinstance(value, list):
        return any(uses_template(v) for v in value)
    return False


EXPANDED_KEY = re.compile(r"^(?:date|place):(.+):(?:start|end|is_datetime|name|address|latitude|longitude|google_place_id)$")


def property_name(key: str) -> str:
    """The property a Notion MCP key sets: `date:Date:start` sets Date, `userDefined:URL` sets URL."""
    key = key.strip()
    key = key.removeprefix("userDefined:")
    expanded = EXPANDED_KEY.match(key)
    return (expanded.group(1) if expanded else key).strip().lower()


def marketing() -> dict:
    """company.json's marketing settings, empty when the department isn't set up. A file that can't be parsed raises,
    so main() blocks the call that needed it (fail closed)."""
    from company_config import integration  # here, so a broken module blocks only what needs it

    root = Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path(__file__).resolve().parents[2])
    return integration("marketing", root) or {}


def marketing_data_sources() -> set:
    ids = marketing().get("notion") or {}
    return {str(ids[name]).lower().removeprefix("collection://") for name in DATABASES if ids.get(name)}


def main_checkout(root: Path) -> Path:
    """root, or for a git worktree the main checkout its .git file points to (capacity_scan.main_checkout's way)."""
    try:
        gitdir = root / (root / ".git").read_text().split("gitdir:", 1)[1].strip()
        return (gitdir / (gitdir / "commondir").read_text().strip()).resolve().parent
    except (OSError, IndexError):  # .git is a folder (the main checkout), or isn't there
        return root


def desk_ids() -> set:
    """The Board desk's Notion ids, lower case without hyphens: the main checkout's notion.json's, else (a cloud
    session, a fresh clone) the tracked desk_ids.json's, its rows aside; none before setup. An unreadable file raises,
    so main() blocks the call (fail closed)."""
    root = Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path(__file__).resolve().parents[2])
    path = main_checkout(root) / DESK_IDS
    if not path.exists():
        path = main_checkout(root) / FIXED_DESK_IDS
    if not path.exists():
        return set()
    data = json.loads(path.read_text(encoding="utf-8"))
    found = set()

    def walk(value):
        if isinstance(value, dict):
            for key, item in value.items():
                walk(key)
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)
        elif isinstance(value, str) and NOTION_ID.fullmatch(value.replace("-", "").lower()):
            found.add(value.replace("-", "").lower())

    walk([data[key] for key in DESK_ID_KEYS if key in data])
    return found


def notion_reason(agent: str, tool: str, tool_input) -> "str | None":
    names = [] if tool in NOTION_READS else [property_name(n) for n in property_names(tool_input)]
    if any(n in BOARD_ONLY for n in names):
        return ("Blocked: only the Board sets Approval, AI label, Board comment, Your answer and Your words, in Notion "
                "itself. Leave them for the Board.")
    if tool not in NOTION_READS:
        written = json.dumps(tool_input).replace("-", "").lower()
        if any(identity in written for identity in desk_ids()):
            return ("Blocked: that is the Board desk in Notion. Only scripts/board_desk.py writes it, and the Board; "
                    "put what the Board should read in the desk's KB pages (asks.md for the CEO).")
    if tool not in NOTION_READS and uses_template(tool_input):
        return "Blocked: no Notion templates: a template copies its properties, the Board's fields included."
    if tool not in NOTION_READS | NOTION_AGENT_WRITES:
        return f"Blocked: {tool} changes Notion's structure (delete, duplicate, move, schemas, views); that's the Board's, in Notion."
    if not agent:
        return None
    if agent not in MARKETING_AGENTS:
        return f"Blocked: Notion is for the marketing department only, not the {agent}."
    if tool in NOTION_READS:
        return None
    if agent not in NOTION_WRITERS:
        return f"Blocked: the {agent} may only read Notion, not use {tool}."
    unknown = sorted(set(n for n in names if n not in AGENT_PROPERTIES))
    if unknown:
        return (f"Blocked: agents may set only these Notion properties: {', '.join(sorted(AGENT_PROPERTIES))}. "
                f"Not: {', '.join(unknown)}.")
    return None


def telegram_reason(agent: str, tool: str, tool_input) -> "str | None":
    if agent not in TELEGRAM_AGENTS:
        return f"Blocked: Telegram is for the analyst, not the {agent}."
    if tool != "list_messages":
        return f"Blocked: the analyst reads Telegram with only list_messages, not {tool}."
    root = os.environ.get("CLAUDE_PROJECT_DIR") or str(Path(__file__).resolve().parents[2])
    channels = {channel.lower() for channel in TELEGRAM_CHANNEL.findall((Path(root) / IDEA_SOURCES).read_text())}
    chat = str(tool_input.get("chat_id") or "")
    if chat.lower() not in channels:
        return (f"Blocked: {chat or 'that chat'} isn't on {IDEA_SOURCES}. The analyst reads only the channels "
                "named there, by @handle or id, never a private chat.")
    return None


def decide(event: dict) -> "str | None":
    """The reason to block this tool call, or None to allow it."""
    # Imported here, for every call, so main()'s try holds it: a module that won't import exits 2, not a traceback's 1.
    from marketing_bash import bash_reason

    agent = event.get("agent_type") or ""
    tool_name = event.get("tool_name") or ""
    tool_input = event.get("tool_input") or {}

    if tool_name == "Bash":
        try:
            from guard_merge_queue import queue_reason  # here, so a broken module blocks only Bash
            root = os.environ.get("CLAUDE_PROJECT_DIR") or str(Path(__file__).resolve().parents[2])
            reason = queue_reason(str(tool_input.get("command") or ""), event.get("cwd") or root)
        except Exception as error:  # noqa: BLE001 - fail closed, naming the check that failed
            reason = (f"Blocked: the merge-queue and workflow-run check (guard_merge_queue.py) failed "
                      f"({type(error).__name__}), so it refuses (fail closed).")
        if reason:
            return reason

    if tool_name == "Bash" and (agent or event.get("agent_id")):
        try:
            from board_desk_bash import desk_reason  # here, so a broken module blocks only agents' Bash
            root = os.environ.get("CLAUDE_PROJECT_DIR") or str(Path(__file__).resolve().parents[2])
            reason = desk_reason(str(tool_input.get("command") or ""), event.get("cwd") or root,
                                 agent == "ceo" and not event.get("agent_id"))
        except Exception as error:  # noqa: BLE001 - fail closed, naming the check that failed
            reason = (f"Blocked: the Board desk's check (board_desk_bash.py) failed ({type(error).__name__}), so it "
                      "refuses (fail closed).")
        if reason:
            return reason

    if tool_name == "Bash" and event.get("agent_id"):
        try:
            from background_bash import background_reason  # here, so a broken module blocks only subagents' Bash
            from bounded_wait import wait_reason
            from cq_write import cq_reason
            root = os.environ.get("CLAUDE_PROJECT_DIR") or str(Path(__file__).resolve().parents[2])
            reason = background_reason(event) or wait_reason(event) or cq_reason(event, root)
        except Exception as error:  # noqa: BLE001 - fail closed, naming the check that failed
            reason = (f"Blocked: the run_in_background, bounded-wait and ceo-questions.md checks (background_bash.py, "
                      f"bounded_wait.py, cq_write.py) failed ({type(error).__name__}), so they refuse (fail closed).")
        if reason:
            return reason

    if tool_name.startswith("mcp__") and "instagram" in tool_name.lower():
        from fastdl import people_reason  # here, so a broken module blocks only tools named for Instagram
        reason = people_reason(tool_name)
        if reason:
            return reason

    parsed = split_mcp(tool_name)
    if parsed and parsed[0] == "fastdl":
        from fastdl import fastdl_reason  # here, so a broken module blocks only this connector
        return fastdl_reason(agent, tool_name, tool_input)

    if agent == "trend-researcher" and (tool_name == "Bash" or tool_name.startswith("mcp__")):
        from trend_reader import reader_reason  # here, so a broken module blocks only this role
        return reader_reason(tool_name, tool_input, marketing().get("reader") or {})

    if agent == "reel-analyst" and tool_name.startswith("mcp__"):
        return "Blocked: the reel-analyst has no MCP tools but FastDL's four. It works from files, with tools/marketing/reels/watch.py and save.py."

    if tool_name == "Bash":
        if agent not in MARKETING_AGENTS and agent != "reel-analyst":
            return None
        root = os.environ.get("CLAUDE_PROJECT_DIR") or str(Path(__file__).resolve().parents[2])
        reason = bash_reason(str(tool_input.get("command") or ""), agent, event.get("cwd") or root, root)
        if reason:
            return ("Blocked: marketing agents' Bash runs only reads, the scripts in tools/marketing/, content_lint, "
                    "language_check, and mkdir, cp, mv and rm inside "
                    f"workspaces/marketing/media/. Write files with Write or Edit. Here: {reason}.")
        return None

    if tool_name == "mcp__claude_ai_Neon__update_branch":
        from neon_branch import branch_reason  # here, so a broken module blocks only this tool
        root = os.environ.get("CLAUDE_PROJECT_DIR") or str(Path(__file__).resolve().parents[2])
        reason = branch_reason(event, Path(root))
        return None if reason is None else f"Blocked: {reason}."

    if parsed is None:
        return None
    family, tool = parsed
    if family == "notion":
        return notion_reason(agent, tool, tool_input)
    if family == "canva" and agent:
        if agent not in CANVA_AGENTS:
            who = "the content-reviewer, which only reads" if agent == "content-reviewer" else f"the {agent}"
            return f"Blocked: Canva is for the marketing department's cmo and content-producer, not {who}."
        if not (tool.startswith(CANVA_PREFIXES) or tool in CANVA_TOOLS):
            return (f"Blocked: Canva {tool} isn't on the list. Canva is for the Board's hand edits (read, export, "
                    "hand over files); AI generation goes through SA-005's capped key.")
        return None
    if family == "metricool":
        if tool == "createScheduledPost":
            if agent != "cmo":
                return "Blocked: only the cmo schedules posts, with stage_item.py's output (docs/marketing.md, \"Publishing\")."
            sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools/marketing/publish"))
            from post import schedule_reason  # here, so a broken builder can't block other tools
            reason = schedule_reason(tool_input)
            return None if reason is None else f"Blocked: {reason}."
        if not METRICOOL_READ.match(tool):
            return (f"Blocked: Metricool {tool} isn't a read. Its writes schedule or publish posts, which only the "
                    "Board does, in Metricool itself.")
        if agent and agent not in METRICOOL_AGENTS:
            return f"Blocked: Metricool's reads are for the cmo and performance-analyst, not the {agent}."
        return None
    if family == "gmail":
        if tool_name == "mcp__claude_ai_Gmail__send_message":
            from board_email import email_reason  # here, so a broken module can't block other tools
            root = os.environ.get("CLAUDE_PROJECT_DIR") or str(Path(__file__).resolve().parents[2])
            reason = email_reason(event, Path(root))
            return None if reason is None else f"Blocked: {reason}."
        if tool not in GMAIL_READS:
            return (f"Blocked: Gmail {tool} isn't a read. No agent sends (but the CEO's email to the Board), drafts, labels, trashes or otherwise "
                    "changes mail; the Board does that in Gmail itself.")
        if agent and agent not in GMAIL_AGENTS:
            return f"Blocked: Gmail's reads are for the analyst, not the {agent}."
        return None
    if tool_name.startswith(TELEGRAM) and agent and agent not in MARKETING_AGENTS:
        return telegram_reason(agent, tool, tool_input)
    if agent not in MARKETING_AGENTS:
        return None
    if family == "other":
        return (f"Blocked: marketing agents may use only Notion, Canva, Metricool's reads and FastDL's content tools "
                f"among MCP tools, as their role allows, not {tool_name}. Nothing is published, sent or "
                "advertised by an agent; the Board does that.")
    return None


def _bash_stays_home(command: str, cwd: str, root: str) -> bool:
    """Whether a command bash_reason passed stays in the repo and the marketing folders: every word, and a flag's
    =value, names a place there (a word that isn't a path resolves there too), no other flag holds a path, and
    footage/fetch.py, the one script given any URL, doesn't run. Each word is read as a literal path, so one the
    shell would rewrite doesn't count as staying, and a short option's attached value is checked as a path too."""
    from guard_critic_bash import simple_commands
    from marketing_bash import FETCH, Paths, _rewritten

    paths = Paths(root, cwd)
    if not paths.under(".", *APPROVED_BASH_PLACES):
        return False
    for name, *args in simple_commands(command):
        if name in ("python3", "python") and args and paths.under(args[0], FETCH):
            return False
        for word in args:
            if _rewritten(word) or "*" in word or "?" in word:
                return False
            if word.startswith("-"):
                flag, _, word = word.partition("=")
                if "/" in flag or "~" in flag:
                    return False
                if not flag.startswith("--") and not all(
                        paths.under(flag[i:], *APPROVED_BASH_PLACES) for i in range(2, len(flag))):
                    return False
            if not paths.under(word, *APPROVED_BASH_PLACES):
                return False
        if name == "cd":
            paths.cwd = paths.resolve(args[0])
    return True


def _in_marketing_database(tool_input) -> bool:
    """Whether notion-create-pages puts its pages in the Marketing calendar or Swipe: a data_source_id parent and
    nothing else, the id bare or as its collection:// URL (marketing_data_sources)."""
    parent = tool_input.get("parent") if isinstance(tool_input, dict) else None
    if not isinstance(parent, dict) or set(parent) - {"type", "data_source_id"}:
        return False
    source = parent.get("data_source_id")
    return (parent.get("type", "data_source_id") == "data_source_id" and isinstance(source, str)
            and source.lower().removeprefix("collection://") in marketing_data_sources())


def approves(event: dict) -> bool:
    """Whether to approve a call decide() passed: a marketing role's normal work (the docstring's "Approves"), where
    company.json's no_prompts asks for it."""
    agent = event.get("agent_type") or ""
    tool_name = event.get("tool_name") or ""
    parsed = split_mcp(tool_name)
    if parsed and parsed[0] == "fastdl":
        from fastdl import fastdl_reason  # asked again, so no order of calls approves what decide() refuses
        return (fastdl_reason(agent, tool_name, event.get("tool_input") or {}) is None
                and _no_prompts("fastdl"))
    return _normal_work(event, agent, tool_name, parsed) and _no_prompts("work")


def _no_prompts(calls: str) -> bool:
    """Whether the founder asked for these calls without a prompt. Only a list counts."""
    asked = marketing().get("no_prompts")
    return isinstance(asked, list) and calls in asked


def _normal_work(event: dict, agent: str, tool_name: str, parsed) -> bool:
    if tool_name == "Bash":
        root = os.environ.get("CLAUDE_PROJECT_DIR") or str(Path(__file__).resolve().parents[2])
        command = str((event.get("tool_input") or {}).get("command") or "")
        return agent in APPROVED_BASH and _bash_stays_home(command, event.get("cwd") or root, root)
    if agent == "trend-researcher":
        return tool_name.startswith("mcp__claude-in-chrome__")
    if parsed is None or agent not in MARKETING_AGENTS:
        return False
    family, tool = parsed
    if family == "notion":
        if tool == "notion-create-pages":
            return agent in NOTION_WRITERS and _in_marketing_database(event.get("tool_input"))
        return tool in APPROVED_NOTION
    if family == "canva":
        return tool in APPROVED_CANVA
    if family == "metricool":
        return bool(METRICOOL_READ.match(tool))
    return False


def main() -> None:
    try:
        event = json.load(sys.stdin)
        if not isinstance(event, dict):
            raise ValueError("the input isn't a JSON object")
        reason = decide(event)
        approved = not reason and approves(event)
    except Exception as error:  # noqa: BLE001 - any failure must block, never allow (exit 1 doesn't block)
        print(f"Blocked: the marketing tool guard failed ({type(error).__name__}), so it refuses (fail closed).",
              file=sys.stderr)
        sys.exit(2)
    if reason:
        print(reason, file=sys.stderr)
        sys.exit(2)
    if approved:
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "allow",
                "permissionDecisionReason": "a marketing role's call the guard passes (scripts/hooks/guard_marketing_tools.py)",
            }
        }))


if __name__ == "__main__":
    main()
