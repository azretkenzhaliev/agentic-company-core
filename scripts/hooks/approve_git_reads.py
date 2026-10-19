#!/usr/bin/env python3
"""PreToolUse hook for Bash: approves plain git reads, with or without -C.

Agents inspect repos and worktrees with `git -C <worktree> log|diff|...` and
`git fetch`, and background agents can't answer a permission prompt. Rules
like `Bash(git -C * log *)` or `Bash(git fetch *)` can't express this safely:
their `*` also spans spaces, so they approved options inserted before the
subcommand (`-c core.pager=<cmd>`) and options that run programs or write
files (`--upload-pack=<cmd>`, `--output=<file>`). This hook approves only:

    git [-C <path>] <subcommand> [args...]

- the subcommand is status, log, diff, show, branch, rev-parse or fetch, or
  `worktree list`;
- nothing at all sits between `git` (or the path) and the subcommand;
- the whole command uses only letters, digits, spaces and _ . / @ : = + , % ^ ~ -
  (no quotes, globs, braces, $, ;, &, |, <, > or backslashes, so the shell
  can't change the words or chain another command);
- no argument is --upload-pack (runs a program), --output (writes a file) or
  --ext-diff (runs a program), or an abbreviation git would accept for one;
- no argument contains `::`, which makes fetch run a remote helper program.

Anything else gets no decision (exit 0, no output), so the normal permission
rules apply.
"""

import json
import re
import sys

SUBCOMMANDS = {"status", "log", "diff", "show", "branch", "rev-parse", "fetch"}
SAFE_COMMAND = re.compile(r"[A-Za-z0-9 _./@:=+,%^~-]+")
RISKY_OPTIONS = ("--upload-pack", "--output", "--ext-diff")


def approvable(command: str) -> bool:
    if not SAFE_COMMAND.fullmatch(command):
        return False
    words = command.split()
    if words[:1] != ["git"]:
        return False
    if words[1:2] == ["-C"]:
        if len(words) < 3 or words[2].startswith("-"):
            return False
        words = words[3:]
    else:
        words = words[1:]
    if not words:
        return False
    sub, args = words[0], words[1:]
    if sub == "worktree":
        if not args or args[0] != "list":
            return False
    elif sub not in SUBCOMMANDS:
        return False
    for arg in args:
        name = arg.split("=", 1)[0]
        if name.startswith("--") and len(name) > 2 and any(option.startswith(name) for option in RISKY_OPTIONS):
            return False
        if "::" in arg:
            return False
    return True


def main() -> None:
    try:
        event = json.load(sys.stdin)
    except json.JSONDecodeError:
        return
    if event.get("tool_name") != "Bash":
        return
    command = (event.get("tool_input") or {}).get("command")
    if isinstance(command, str) and approvable(command.strip()):
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
            "permissionDecisionReason": "plain git read (scripts/hooks/approve_git_reads.py)",
        }}))


if __name__ == "__main__":
    main()
