#!/usr/bin/env python3
"""PreToolUse hook for Write, Edit, MultiEdit and NotebookEdit (its path is notebook_path), and for Bash, where it looks
at company.json alone. scripts/tests/test_settings.py pins the matchers in .claude/settings.json.

Blocks (exit 2, reason on stderr) when:
- a write lands in an agent's system worktree (.claude/worktrees/agent-<X>/, after symlinks and
  `..` are resolved) from a session whose folder (the hook input's cwd) isn't inside that same
  worktree, or whose cwd is missing or not absolute: one agent never edits another's draft. The
  folder matches at any depth, not only under this repo's root, so another repo's agent worktree
  is held too;
- a subagent (the hook input has agent_id) writes company.json, the settings the guards read: the
  repo root's, an agent worktree's, or the one beside any scripts/company_config.py. The main
  session's write is answered "ask" instead, so the founder sees it. A Bash command that names a
  file of that name, in any folder (a copy puts it here), or matches it by a glob at a company
  root, counts as a write unless every command in it reads (cat, head, tail, grep, jq, diff,
  git log|show|diff|status, ... with no redirection and no $(...)) or is `git add` or `git commit`;
- the new text for a file under knowledge/ contains a secret;
- the analyst writes anywhere outside knowledge/research/;
- the ux-expert writes anywhere outside knowledge/engineering/ux/ and workspaces/ux/;
- a marketing agent writes outside its own pages: the content-reviewer writes
  nothing; the content-producer only content/ pages and workspaces/marketing/media/;
  the cmo the rest of knowledge/marketing/, media/ and corpus/ (reference
  texts); the trend-researcher only workspaces/marketing/intelligence/; the reel-analyst
  only its reels/ folder;
- any agent writes an approvals/ page under knowledge/marketing/ (the Board's
  decisions; only scripts/notion_approvals_sync.py writes them), anything in
  knowledge/board/answers/ (the Board's answers; only scripts/board_desk.py's reader
  writes them), anything in workspaces/board-desk/ (the desk's state: the Board's id, the Notion
  ids the Notion guard reads; only board_desk.py writes it) or anything in
  workspaces/marketing/inbox/ (the founder's own raw material);
- a subagent Writes an existing ceo-questions.md under the repo's workspaces/, which other
  agents write at the same time: Edit or `>>` only (cq_write.py); or adds a line that passes for
  the CEO's to one, or to the ceo-questions-archive.md beside one unless that file holds the line.
  A check that fails, its module's import too, refuses (fail closed): for a ceo-questions.md in
  any session, for an archive only a subagent's.

Paths compare case-insensitively (a Mac's disk is), and folders are resolved
first, so a media folder linked elsewhere still counts as media.

Everything else is allowed (exit 0); an input it can't read and an error are refused. The project
root is $CLAUDE_PROJECT_DIR, falling back to this script's location. It stops mistakes; it isn't a
sandbox.
"""

import bisect
import fnmatch
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from kb_secrets import find_secrets  # noqa: E402

WRITE_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}


def new_text(tool_name: str, tool_input: dict) -> str:
    if tool_name == "Write":
        return tool_input.get("content", "")
    if tool_name == "Edit":
        return tool_input.get("new_string", "")
    if tool_name == "NotebookEdit":
        return tool_input.get("new_source", "")
    return "\n".join(edit.get("new_string", "") for edit in tool_input.get("edits", []))


def is_under(path: Path, folder: Path) -> bool:
    return path == folder or folder in path.parents


def agent_worktree(path: Path) -> "Path | None":
    """The innermost .claude/worktrees/agent-<X> folder holding path, or None (names compare case-folded)."""
    folded = [part.casefold() for part in path.parts]
    for i in range(len(folded) - 1, 1, -1):
        if folded[i].startswith("agent-") and folded[i - 2:i] == [".claude", "worktrees"]:
            return Path(*path.parts[:i + 1])
    return None


def resolved(path: Path) -> "Path | None":
    try:
        return path.resolve()
    except (OSError, RuntimeError, ValueError):  # a symlink loop before Python 3.13, a NUL in the path
        return None


def worktree_reason(raw_path: str, cwd, root: Path) -> "str | None":
    """Why a write to raw_path from a session in folder cwd may not land, or None.
    Only a path in an agent's system worktree is checked: there the caller's cwd must be in the same one."""
    path = Path(raw_path)
    if not path.is_absolute():
        path = Path(cwd if isinstance(cwd, str) and cwd else root) / path
    real = resolved(path)
    target = agent_worktree(real or Path(os.path.normpath(path)))
    if target is None:
        return None
    if real is None:
        return f"Blocked: {path} is in agent worktree {target} and can't be resolved."
    if not isinstance(cwd, str) or not os.path.isabs(cwd):
        return f"Blocked: {path} is in agent worktree {target}, and the hook input has no absolute cwd to check."
    caller = resolved(Path(cwd))
    if caller is None:
        return f"Blocked: {path} is in agent worktree {target}, and the session's cwd can't be resolved."
    caller = agent_worktree(caller)
    if caller is None or str(caller).casefold() != str(target).casefold():
        return (f"Blocked: {path} is in agent worktree {target}; only the agent working there writes it, and "
                f"this session's cwd is {cwd}. Make the change in your own worktree or put it in your report.")
    return None


def block(reason: str) -> None:
    print(reason, file=sys.stderr)
    sys.exit(2)


def ask(reason: str) -> None:
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "ask",
                                             "permissionDecisionReason": reason}}))


COMPANY_FILE = "company.json"
# The file's name in a command whose quotes and backslashes are gone, and where a word ends there.
COMPANY_NAME = re.compile(r"(?<![\w.-])company\.json(?![\w-]|\.\w)", re.I)
WORD = re.compile(r"[^\s;|&<>()=:]+")
BRACES = re.compile(r"\{[^{}]*\}")
UNKNOWN = re.compile(r"[$`*?\[{]")  # a path with one of these can lead anywhere
MOVES = re.compile(r"(?<![\w./-])(?:cd|pushd)\s+([^\s;|&<>()]+)")
COMPANY_READS = {"jq", "diff", "cmp", "test", "[", "stat"}
COMPANY_WHY = ("company.json holds the company's settings, which the guards read: no subagent writes it. Report the "
               "change you need; the main session makes it, and the founder sees it. To read it, use cat, grep or jq "
               "with no redirection and no $(...); to write text that names it, use the Write or Edit tool.")


def company_root(folder: Path, root: Path) -> bool:
    """Whether company.json in this folder is a company's: the root's, an agent worktree's, or beside its reader."""
    folder = resolved(folder) or folder
    return (str(folder).casefold() == str(root).casefold() or agent_worktree(folder) == folder
            or (folder / "scripts" / "company_config.py").is_file())


def writes_company_file(raw_path: str, cwd, root: Path) -> bool:
    """Whether a write to raw_path lands in a company's company.json, by its own name or through a link to it."""
    path = Path(raw_path)
    if not path.is_absolute():
        path = Path(cwd if isinstance(cwd, str) and cwd else root) / path
    return any(at.name.casefold() == COMPANY_FILE and company_root(at.parent, root)
               for at in (Path(os.path.normpath(path)), resolved(path) or path))


def command_writes_company_file(command: str, cwd, root: Path) -> bool:
    """Whether a Bash command that names a company.json may write a company's (the docstring)."""
    plain = re.sub(r"[\"'\\]", "", command)
    folders, starts = [Path(cwd if isinstance(cwd, str) and cwd else root)], []  # after each cd
    for move in MOVES.finditer(plain):
        folders.append(Path(os.path.normpath(folders[-1] / os.path.expanduser(move[1]))))
        starts.append(move.end())
    # The name counts in any folder: `cp <any folder>/company.json .` writes the one here.
    named = bool(COMPANY_NAME.search(plain))
    for word in () if named else WORD.finditer(plain):
        before, _, name = BRACES.sub("*", word[0]).rpartition("/")
        if (UNKNOWN.search(name) and re.search("[a-z]", name, re.I)
                and fnmatch.fnmatchcase(COMPANY_FILE, name.casefold())):
            folder = folders[bisect.bisect_right(starts, word.start())] / os.path.expanduser(before)
            named = named or company_root(Path(os.path.normpath(folder)), root)
    if not named:
        return False
    import guard_critic_bash as reader  # here, so only a command that names the file loads it

    folder = folders[0]
    if reader.allowed(command, str(folder)):
        return False
    if "$(" in command or "`" in command:
        return True
    commands = reader.simple_commands(command)  # ValueError (a quote left open): main() takes it for a write

    def reads(words: list) -> bool:
        git = words[3:] if words[:2] == ["git", "-C"] else words[1:] if words[0] == "git" else []
        return words[0] in COMPANY_READS or git[:1] in (["add"], ["commit"]) or reader.reads_only(words, str(folder))

    return not commands or not all(reads(words) for words in commands)


PERFORMANCE_PAGES = {"metrics.md", "learnings.md"}


def parts_under(path: Path, folder: Path) -> "tuple | None":
    """path's parts below folder, case-folded, or None if it isn't under it (the disk is case-insensitive)."""
    p, f = str(path).casefold(), str(folder.resolve()).casefold()
    if p == f:
        return ()
    return tuple(Path(p[len(f) + 1:]).parts) if p.startswith(f + "/") else None


def marketing_write_reason(agent_type: str, path: Path, root: Path) -> "str | None":
    """Why a marketing agent may not write path, or None. Other agents get None."""
    parts = parts_under(path, root / "knowledge" / "marketing")
    in_marketing = parts is not None
    parts = parts or ()
    in_media = parts_under(path, root / "workspaces" / "marketing" / "media") is not None
    in_corpus = parts_under(path, root / "workspaces" / "marketing" / "corpus") is not None
    if agent_type == "trend-researcher":
        if parts_under(path, root / "workspaces" / "marketing" / "intelligence") is not None:
            return None
        return "Blocked: the trend-researcher writes only under workspaces/marketing/intelligence/."
    if agent_type == "reel-analyst":
        if parts_under(path, root / "workspaces" / "marketing" / "intelligence" / "reels") is not None:
            return None
        return "Blocked: the reel-analyst writes only under workspaces/marketing/intelligence/reels/."
    if agent_type == "content-reviewer":
        return "Blocked: the content-reviewer is read-only. Put the finding in your VERDICT."
    if agent_type == "content-producer":
        if in_media or "content" in parts[:-1]:
            return None
        return ("Blocked: the content-producer writes only knowledge/marketing/<brand>/content/ pages "
                "and media under workspaces/marketing/media/. Report other changes to the CMO.")
    performance_page = (in_marketing and len(parts) >= 2 and parts[-1] in PERFORMANCE_PAGES
                        and (root / "knowledge" / "marketing" / Path(*parts[:-1]) / "brand-book.md").is_file())
    if agent_type == "performance-analyst":
        if performance_page:
            return None
        return "Blocked: the performance-analyst writes only <brand>/metrics.md and learnings.md under knowledge/marketing/."
    if agent_type == "cmo":
        if in_media or in_corpus or (in_marketing and parts and "content" not in parts[:-1]
                                     and not performance_page):
            return None
        return ("Blocked: the cmo writes knowledge/marketing/ (not the producer's content/ pages or the "
                "performance analyst's metrics.md and learnings.md), workspaces/marketing/media/ and corpus/.")
    return None


def main() -> None:
    try:
        event = json.load(sys.stdin)
    except json.JSONDecodeError:
        block("Blocked: the hook input couldn't be read (guard_kb_write.py), so it refuses (fail closed).")
    tool_name = event.get("tool_name")
    if tool_name == "Bash":
        root = Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path(__file__).resolve().parents[2]).resolve()
        try:
            writes = command_writes_company_file(str((event.get("tool_input") or {}).get("command") or ""),
                                                 event.get("cwd"), root)
        except ValueError:  # it names the file, and its quotes don't close
            writes = True
        if writes and event.get("agent_id"):
            block(f"Blocked: {COMPANY_WHY}")
        if writes:
            ask("This command may write company.json, the company's settings, which the guards read.")
        return
    if tool_name not in WRITE_TOOLS:
        return
    tool_input = event.get("tool_input") or {}

    root = Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path(__file__).resolve().parents[2]).resolve()
    raw_path = tool_input.get("notebook_path" if tool_name == "NotebookEdit" else "file_path", "")
    reason = worktree_reason(raw_path, event.get("cwd"), root)
    if reason:
        block(reason)
    path = Path(raw_path)
    if not path.is_absolute():
        path = Path(event.get("cwd") or root) / path
    path = path.resolve()
    knowledge = root / "knowledge"

    company = writes_company_file(raw_path, event.get("cwd"), root)
    if company and event.get("agent_id"):
        block(f"Blocked: {COMPANY_WHY}")

    agent_type = event.get("agent_type")
    if agent_type == "analyst" and not is_under(path, knowledge / "research"):
        block("Blocked: the analyst may write only under knowledge/research/. Report the finding to the CEO instead.")
    if agent_type == "ux-expert" and parts_under(path, knowledge / "engineering" / "ux") is None \
            and parts_under(path, root / "workspaces" / "ux") is None:
        block("Blocked: the ux-expert writes only under knowledge/engineering/ux/ and workspaces/ux/. "
              "Put other changes in your report.")

    marketing_parts = parts_under(path, knowledge / "marketing")
    if agent_type and marketing_parts and "approvals" in marketing_parts[:-1]:
        block("Blocked: approvals/ pages hold the Board's decisions; only the sync script "
              "(scripts/notion_approvals_sync.py) writes them.")
    if (agent_type or event.get("agent_id")) and parts_under(path, knowledge / "board" / "answers") is not None:
        block("Blocked: knowledge/board/answers/ holds the Board's own answers; only scripts/board_desk.py's reader "
              "writes them. Quote an answer in the directive's status log instead.")
    if (agent_type or event.get("agent_id")) and parts_under(path, root / "workspaces" / "board-desk") is not None:
        block("Blocked: workspaces/board-desk/ is the Board desk's state (the Board's id, its Notion ids); only "
              "scripts/board_desk.py writes it.")
    if agent_type and parts_under(path, root / "workspaces" / "marketing" / "inbox") is not None:
        block("Blocked: workspaces/marketing/inbox/ holds the founder's own raw material; only they put files there.")
    if agent_type:
        reason = marketing_write_reason(agent_type, path, root)
        if reason:
            block(reason)

    names = {Path(raw_path).name.casefold(), path.name.casefold()}
    # The archive's check holds only subagents (agent_id), so a module that fails to import leaves the main session's
    # archive writes; a ceo-questions.md stays fail closed for every session.
    if "ceo-questions.md" in names or ("ceo-questions-archive.md" in names and event.get("agent_id")):
        try:
            from cq_write import write_reason  # here, so a broken module holds only this file
            reason = write_reason(event, raw_path, path, str(root))
        except Exception as error:  # noqa: BLE001 - fail closed, for this file alone
            reason = f"Blocked: the ceo-questions.md check failed ({type(error).__name__}), so it refuses (fail closed)."
        if reason:
            block(reason)

    if is_under(path, knowledge):
        hits = find_secrets(new_text(tool_name, tool_input))
        if hits:
            found = ", ".join(f"{kind} (line {line} of the new text)" for line, kind in hits)
            block(
                f"Blocked: possible secret in a knowledge-base write: {found}. "
                "Never write secrets into the KB; write where the secret lives instead "
                "(e.g. 'env var X in the hosting dashboard')."
            )

    if company:
        ask("This write changes company.json, the company's settings, which the guards read.")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:  # noqa: BLE001 - fail closed
        block(f"Blocked: the write check failed ({type(error).__name__}), so it refuses (fail closed).")
