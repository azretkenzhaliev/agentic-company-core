#!/usr/bin/env python3
"""Replays the Bash commands the company's agents ran in the last hours through the desk guard and counts its false
refusals. Every desk-guard change runs this over the last 24 hours before its review, and its report names the counts,
with zero false refusals.

It reads the transcripts under the Claude configuration folder's projects/ ($CLAUDE_CONFIG_DIR, or ~/.claude; the
folders of this checkout, its worktrees and scratch clones: a name with the main checkout's folder name), and in them
only the assistant's Bash tool_use inputs: the command and the cwd its line records. A call is replayed when the hook
holds it: a subagent's (its file under subagents/, its type from the meta file beside it) or a main session's started
as an agent (its agent-setting line); a plain session's (the Board's own) is never held, so it is skipped. Each goes
through board_desk_bash.desk_reason as guard_marketing_tools.py calls it (the cwd, and ceo for the CEO's main session);
a check that raises refuses, as the hook fails closed.

A refusal is false (it writes nothing under the held folders) unless its command, at some quote depth, names a held
folder (FOLDER), a word of it resolved against the cwd and its folder moves lies in one, the cwd does, or it names
board_desk.py or the desk's token (witnessed). That reading is strict where it can't see: a write through a folder
holding one (`rm -rf knowledge`) counts as false, for a look. The witnessed refusals are listed too: one that only
reads there is a false refusal as well, judged by hand (the check blocks only commands that write there).

The corpus it builds goes to workspaces/system/guard-corpus/ in this checkout (gitignored; its folder 0700, its file
0600; only the latest run's kept) and nowhere else: never committed, never put in a review or second-opinion packet.
Commands can hold paths, ids or tokens, so none is printed whole: a false or witnessed refusal shows its first 120
characters, after every match of the secrets lint's patterns (kb_secrets.py) is replaced, in the corpus too. Exit 0: no
false refusal; 1: some; 2: an error, or no call read.

    python3 scripts/guard_replay.py [--hours 24] [--projects DIR] [--corpus-dir DIR]
"""

import argparse
import datetime
import importlib.util
import json
import os
import posixpath
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "hooks"))

from kb_secrets import SECRET_PATTERNS  # noqa: E402

desk = None  # the guard under replay: this checkout's board_desk_bash.py, or --guard's file (load)

PROJECTS = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude") / "projects"
NAME = re.sub(r"[^A-Za-z0-9]", "-", Path(str(ROOT).split("/.claude/worktrees/")[0]).name)  # as a projects folder's name holds it
CORPUS = ROOT / "workspaces" / "system" / "guard-corpus"
GUARD = ROOT / "scripts" / "hooks" / "board_desk_bash.py"
MASK = "SECRET_MASKED"
SHOWN = 120


def load(path):
    """The guard module at path, as desk."""
    global desk
    spec = importlib.util.spec_from_file_location("board_desk_bash", path)
    desk = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(desk)
    return desk


def masked(text):
    """(text, count): the text with each match of the secrets lint's patterns replaced by MASK."""
    count = 0
    for _, pattern in SECRET_PATTERNS:
        text, n = pattern.subn(MASK, text)
        count += n
    return text, count


def agent_of(path):
    """(agent type, subagent) for a transcript: a subagent's type from its meta file, or the main session's from its
    agent-setting line ("" for a plain session)."""
    if path.parent.name == "subagents":
        try:
            meta = json.loads(path.with_suffix(".meta.json").read_text())
            return str(meta.get("agentType") or "subagent"), True
        except (OSError, ValueError):
            return "subagent", True
    agent = ""
    with open(path, errors="replace") as lines:
        for line in lines:
            if '"agent-setting"' in line:
                try:
                    agent = str(json.loads(line).get("agentSetting") or agent)
                except ValueError:
                    pass
    return agent, False


def collect(projects, since):
    """([{ts, agent, ceo, cwd, command, id}], plain, masks): the held Bash calls since `since` (an aware datetime),
    each once by its tool_use id, with secrets masked; how many plain sessions' calls were skipped."""
    cutoff = since.strftime("%Y-%m-%dT%H:%M:%S")
    calls, seen, plain, masks = [], set(), 0, 0
    for path in sorted(projects.glob(f"*{NAME}*/**/*.jsonl")):
        if path.stat().st_mtime < since.timestamp():
            continue
        agent, sub = agent_of(path)
        with open(path, errors="replace") as lines:
            for line in lines:
                if '"Bash"' not in line:
                    continue
                try:
                    entry = json.loads(line)
                except ValueError:
                    continue
                if entry.get("type") != "assistant" or str(entry.get("timestamp") or "") < cutoff:
                    continue
                for block in (entry.get("message") or {}).get("content") or []:
                    if not (isinstance(block, dict) and block.get("type") == "tool_use" and block.get("name") == "Bash"):
                        continue
                    key = block.get("id") or f"{path}:{len(seen)}"
                    if key in seen:
                        continue
                    seen.add(key)
                    if not agent:
                        plain += 1
                        continue
                    command, n = masked(str((block.get("input") or {}).get("command") or ""))
                    masks += n
                    calls.append({"ts": entry.get("timestamp"), "agent": agent, "ceo": agent == "ceo" and not sub,
                                  "cwd": str(entry.get("cwd") or ""), "command": command, "id": key})
    return calls, plain, masks


def write_corpus(folder, calls, stamp):
    """The corpus file's path: the calls as JSON lines, in a 0700 folder, the file 0600; the corpus files of earlier
    runs in it removed, so only the latest is kept."""
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(folder, 0o700)  # an existing folder keeps its mode through mkdir
    path = folder / f"corpus-{stamp}.jsonl"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as out:
        for call in calls:
            out.write(json.dumps(call) + "\n")
    os.chmod(path, 0o600)
    for old in folder.glob("corpus-*.jsonl"):
        if old != path:
            old.unlink()
    return path


def inside_held(path) -> bool:
    """Whether an absolute, normalized path lies in a held folder (the guard's HELD_PARTS: knowledge/board/answers,
    workspaces/board-desk, board-desk-seal)."""
    parts = [part.casefold() for part in Path(path).parts]
    return any(tuple(parts[i:i + len(held)]) == held for held in desk.HELD_PARTS for i in range(len(parts)))


def witnessed(command, cwd) -> bool:
    """Whether the command may write a held folder, run board_desk.py or read the desk's token by what it names: its
    text at some quote depth, or its words resolved against the cwd and its folder moves, or the cwd itself."""
    folded = command.casefold()
    if any(word in folded for word in ("board_desk", desk.KEYCHAIN, "keychain_token", "dump-keychain",
                                       "adapter_notion")) or desk.ACCOUNT_TEXT.search(command):
        return True
    bare = folded.replace("\\\n", "")
    if any(desk.FOLDER.search(text) for text in desk.depths(bare) + [bare.replace("'", "").replace('"', "")]):
        return True
    if cwd and inside_held(posixpath.normpath(cwd)):
        return True
    here, stack = cwd, []
    try:
        lines, _ = desk.split(command)
        commands = [simple for line in lines for simple in desk.simple_commands(line)]
    except ValueError:
        return False
    for words, targets in commands:
        if here and any(path and inside_held(path) for path in (desk.resolve(here, word) for word in words + targets)):
            return True
        move = desk.moved(words)
        if move:
            here = desk.moved_to(*move, here, stack)
    return False


def gone(command, cwd) -> bool:
    """Whether the cwd, or a folder the command moves into (cd, pushd, git -C), is gone since: the guard reads the
    disk (a checkout's .git, a held folder beneath a word), so such a call can't be read as it was."""
    if not os.path.isdir(cwd or "/"):
        return True
    here, stack = cwd, []
    try:
        lines, _ = desk.split(command)
        commands = [simple for line in lines for simple in desk.simple_commands(line)]
    except ValueError:
        return False
    for words, _ in commands:
        if desk.program(words) == "git" and here:
            folder = desk.git_folder(words, here)
            if folder and not os.path.isdir(folder):
                return True
        move = desk.moved(words)
        if move:
            here = desk.moved_to(*move, here, stack)
            if here and not os.path.isdir(here):
                return True
    return False


def shown(command):
    """The command's first SHOWN characters on one line (its secrets already masked)."""
    return command[:SHOWN].replace("\n", "\\n")


def replay(calls):
    """(allowed, false, witnessed, lost): the refused calls as (call, reason) lists; lost: refused, naming none, after
    a move into a folder gone since (gone)."""
    allowed, false, seen, lost = 0, [], [], []
    for call in calls:
        try:
            reason = desk.desk_reason(call["command"], call["cwd"] or str(ROOT), call["ceo"])
        except Exception as error:  # noqa: BLE001 - the hook fails closed: a raise is a refusal
            reason = f"the check failed ({type(error).__name__})"
        if reason is None:
            allowed += 1
        elif witnessed(call["command"], call["cwd"]):
            seen.append((call, reason))
        elif gone(call["command"], call["cwd"]):
            lost.append((call, reason))
        else:
            false.append((call, reason))
    return allowed, false, seen, lost


def listing(refused):
    for call, reason in refused:
        why = reason.rsplit("Here: ", 1)[-1].rstrip(".")[:80]
        print(f"  {str(call['ts'])[:16]}Z {call['agent']} [{why}]: {shown(call['command'])}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--hours", type=float, default=24)
    parser.add_argument("--projects", type=Path, default=PROJECTS)
    parser.add_argument("--corpus-dir", type=Path, default=CORPUS)
    parser.add_argument("--guard", type=Path, default=GUARD, help="another board_desk_bash.py to replay (a base's)")
    args = parser.parse_args(argv)
    load(args.guard)
    now = datetime.datetime.now(datetime.timezone.utc)
    since = now - datetime.timedelta(hours=args.hours)
    if not args.projects.is_dir():
        print(f"guard replay: no transcripts folder {args.projects}", file=sys.stderr)
        return 2
    calls, plain, masks = collect(args.projects, since)
    corpus = write_corpus(args.corpus_dir, calls, now.strftime("%Y%m%dT%H%M%SZ"))
    allowed, false, seen, lost = replay(calls)
    print(f"guard replay: {len(calls)} agents' Bash calls from {since:%Y-%m-%dT%H:%MZ} to {now:%Y-%m-%dT%H:%MZ} "
          f"(transcripts in {args.projects}; {plain} plain sessions' calls skipped, never held); guard "
          f"{Path(desk.__file__).resolve()}")
    print(f"allowed: {allowed}")
    print(f"refused: {len(false) + len(seen) + len(lost)}")
    print(f"false refusals (refused, naming no held folder, desk script or token): {len(false)}")
    listing(false)
    print(f"refused naming a held folder, the desk script or the token: {len(seen)} (each judged by hand: one that "
          "only reads there is a false refusal too)")
    listing(seen)
    print(f"refused naming none, after a move into a folder gone since (each judged by hand: the disk isn't as it "
          f"was, so one may be a false refusal): {len(lost)}")
    listing(lost)
    print(f"corpus: {corpus} ({len(calls)} commands, {masks} secrets masked; never committed, sent or printed whole)")
    if not calls:
        print("guard replay: no call read, so this run shows nothing", file=sys.stderr)
        return 2
    return 1 if false else 0


if __name__ == "__main__":
    sys.exit(main())
