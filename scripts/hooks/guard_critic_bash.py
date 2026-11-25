#!/usr/bin/env python3
"""PreToolUse hook for Bash: the critic and the content-reviewer only read.

They have no Write or Edit tool, but Bash can write files too, and a
subagent's own permissionMode is ignored when the main session runs in auto,
acceptEdits or bypass mode (Claude Code docs, "Permission modes"). So for them
(`agent_type` "critic" or "content-reviewer") this blocks (exit 2, reason on stderr) every
Bash command except:

- read commands, alone, piped or chained with |, &&, || or ;:
  cat, head, tail, grep, ls, wc, echo, cd; sed -n with a print-only script;
  find without -delete, -exec, -ok or -fprint/-fls;
  git [-C <path>] log|show|diff|grep|status|blame, without --output, --ext-diff
  or -O (they write files or run programs);
  gh <noun> view|list|diff;
  python3 scripts/second_opinion.py or tools/marketing/content_lint.py (it only reads),
  by a path relative to the repo or absolute inside it;
- redirection only to /dev/null, and 2>&1;
- the second-opinion call with its packet in a quoted heredoc on stdin:
  python3 scripts/second_opinion.py ... --file /dev/stdin <<'EOF' ... EOF

No $(...) or backticks anywhere. Other callers aren't limited. An input it
can't read and an error are refused.
"""

import json
import os
import re
import shlex
import sys
from pathlib import Path

READ_ONLY_AGENTS = {"critic", "content-reviewer"}
PYTHON_SCRIPTS = {"scripts/second_opinion.py", "tools/marketing/content_lint.py"}
READERS = {"cat", "head", "tail", "grep", "ls", "wc", "echo", "cd", "find", "sed", "git", "gh", "python3"}
SED_PRINT = re.compile(r"^(\d+|\$)?(,(\d+|\$))?p$")
FIND_WRITES = ("-delete", "-exec", "-ok", "-fprint", "-fls")
GIT_READS = {"log", "show", "diff", "grep", "status", "blame"}
GIT_RISKY = ("--output", "--ext-diff", "--open-files-in-pager")
GH_READS = {"view", "list", "diff"}
SEPARATORS = {"|", "||", "&&", ";"}
HEREDOC = re.compile(r"(python3 scripts/second_opinion\.py [^\n]*?)\s*<<'(\w+)'\n(.*)\n\2", re.S)


def simple_commands(command: str):
    """The words of each simple command, or None if the line has anything else (redirection, subshell, &)."""
    lexer = shlex.shlex(command.replace("\n", " ; "), posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    lexer.commenters = ""  # bash starts a comment only at a word's start; shlex would hide the rest of `x#; rm y`
    words, current = list(lexer), []
    commands, i = [], 0
    while i < len(words):
        word = words[i]
        if word in SEPARATORS:
            commands.append(current)
            current = []
        elif word in {">", ">>"} and words[i + 1:i + 2] == ["/dev/null"]:
            i += 1
        elif word == ">&" and words[i + 1:i + 2] in (["1"], ["2"]):
            i += 1
        elif set(word) <= set("();<>|&"):
            return None
        else:
            current.append(word)
        i += 1
    commands.append(current)
    return [c for c in commands if c]


def _script(arg: str, cwd: str) -> "str | None":
    """The repo-relative path of a python script argument, if it's inside the repo."""
    root = os.path.realpath(os.environ.get("CLAUDE_PROJECT_DIR") or Path(__file__).resolve().parents[2])
    for base in (cwd or root, root):  # relative paths are repo-relative by habit
        path = os.path.realpath(os.path.join(base, arg))
        if path.startswith(root + os.sep):
            return os.path.relpath(path, root)
    return None


def reads_only(words: list, cwd: str = "") -> bool:
    name, args = words[0], words[1:]
    if name not in READERS:
        return False
    if name == "find":
        return not any(arg.startswith(FIND_WRITES) for arg in args)
    if name == "git":
        if args[:1] == ["-C"]:
            args = args[2:]
        if not args or args[0] not in GIT_READS:
            return False
        for arg in args[1:]:
            option = arg.split("=", 1)[0]
            if arg.startswith("-O") or (option.startswith("--") and len(option) > 2
                                        and any(risky.startswith(option) for risky in GIT_RISKY)):
                return False
        return True
    if name == "gh":
        return len(args) >= 2 and args[1] in GH_READS and args[0] != "api"
    if name == "sed":
        ops = [a for a in args if not a.startswith("-")]
        return "-n" in args and bool(ops) and bool(SED_PRINT.match(ops[0])) and all(
            a in ("-n", "-E", "-r") or not a.startswith("-") for a in args)
    if name == "python3":
        return bool(args) and not args[0].startswith("-") and _script(args[0], cwd) in PYTHON_SCRIPTS
    return True


def allowed(command: str, cwd: str = "") -> bool:
    heredoc = HEREDOC.fullmatch(command.strip())
    if heredoc:
        head, delimiter, body = heredoc.groups()
        if delimiter in body.split("\n"):  # the shell would end the heredoc early and run the rest
            return False
        command = head
    if "$(" in command or "`" in command:
        return False
    try:
        commands = simple_commands(command)
    except ValueError:  # unbalanced quotes
        return False
    return bool(commands) and all(reads_only(words, cwd) for words in commands)


def main() -> None:
    try:
        event = json.load(sys.stdin)
        if event.get("tool_name") != "Bash" or event.get("agent_type") not in READ_ONLY_AGENTS:
            return
        command = (event.get("tool_input") or {}).get("command")
        passes = isinstance(command, str) and allowed(command, event.get("cwd") or "")
    except Exception as error:  # fail closed: a crash would exit 1, which doesn't block by itself
        print(f"Blocked: this hook couldn't check the call ({type(error).__name__}), so it refuses.", file=sys.stderr)
        sys.exit(2)
    if not passes:
        print(
            f"Blocked: the {event['agent_type']} only reads. Bash may run cat, head, tail, grep, ls, wc, find, "
            "git log/show/diff/grep/status/blame, gh ... view/list/diff and python3 scripts/second_opinion.py "
            "(packet on stdin) and python3 tools/marketing/content_lint.py, with no redirection to files and no $(...). "
            "Report what you'd write to your manager.",
            file=sys.stderr,
        )
        sys.exit(2)


if __name__ == "__main__":
    main()
