#!/usr/bin/env python3
"""Optional PreToolUse hook for Bash: agents never deploy with the Vercel CLI.

Off by default; docs/optional-integrations.md says how to enable it. Products
deploy through Git (a push or merge that Vercel builds), never from the CLI. A
`vercel deploy` without --prod still goes to production when it is a project's
first deployment, so even "just a test build" from the CLI is refused.

In agent sessions (the hook input names an `agent_type`: a subagent, or the
--agent type on the main thread), this blocks (exit 2, reason on stderr) any
`vercel` or `vc` call that:
- deploys: `vercel deploy`, or `vercel` with no command, with a path or with
  anything that isn't one of its commands (`vercel --prod`, `vercel .`);
- runs `redeploy`, or `link` (it writes a Vercel OIDC token to `.env.local`);
- runs `promote`, except with a `--scope` listed in PROMOTE_SCOPES (a team
  whose runbook rolls back with Instant Rollback and then promotes);
- targets a Git-only product and runs `rollback` (other than `rollback
  status`), an alias write (anything but `alias ls`) or `rolling-release`. A
  call targets one with a `--scope` in GIT_ONLY_SCOPES, or with no scope when
  it runs in a folder named in GIT_ONLY_DIRS (from the session's folder, a
  `cd` earlier in the command, or `--cwd`). An explicit scope in
  PROMOTE_SCOPES runs from any folder.

It checks every command in a chain, subshell or `sh -c` string, through
variable assignments and launchers such as `npx`, `bunx` and `pnpm dlx`. It
doesn't see vercel started from a script file or a package.json script, or a
default team set with `vercel switch`. A plain `claude` session isn't limited.
"""

import json
import os
import re
import shlex
import sys
from pathlib import PurePosixPath

# Edit these for your products (lower-case team slugs and folder names).
PROMOTE_SCOPES: set = set()   # teams whose runbook rolls back with `vercel promote`, e.g. {"my-team"}
GIT_ONLY_SCOPES: set = set()  # teams whose production and aliases change only through Git
GIT_ONLY_DIRS: set = set()    # folder names of those products, e.g. {"my-product"} for workspaces/my-product/
GIT_ONLY_COMMANDS = {"rollback", "alias", "ln", "rolling-release", "rr"}
# `vercel --help`, CLI 62.1.0. Anything else in the command's place is a path to deploy.
COMMANDS = {
    "deploy", "build", "cache", "dev", "env", "git", "help", "init", "inspect", "i", "install", "integration", "ir",
    "integration-resource", "link", "ls", "list", "login", "logout", "open", "promote", "pull", "redeploy",
    "rollback", "signup", "switch", "activity", "agent", "agent-runs", "ai-gateway", "alerts", "ln", "alias", "api",
    "bisect", "blob", "budgets", "buy", "certs", "changelog", "ci", "comments", "connect", "contract", "crons",
    "curl", "deploy-hooks", "dns", "domains", "firewall", "flags", "global-config", "httpstat", "kms", "log", "logs",
    "mcp", "metrics", "mf", "microfrontends", "project", "redirects", "rm", "remove", "rr", "rolling-release",
    "routes", "sandbox", "schedules", "security", "setup", "skills", "storage", "target", "teams", "telemetry",
    "tokens", "traces", "upgrade", "usage", "vcr", "version", "webhooks", "whoami",
}
INFO_FLAGS = {"-h", "--help", "-v", "--version", "--changelog"}
VALUE_OPTIONS = {"--cwd", "-A", "--local-config", "-Q", "--global-config", "-S", "--scope", "-t", "--token"}
LAUNCHERS = {"npx", "bunx", "pnpx", "env", "command", "exec", "time", "nohup"}
TWO_WORD_LAUNCHERS = {("pnpm", "dlx"), ("pnpm", "exec"), ("yarn", "dlx"), ("npm", "exec"), ("bun", "x")}
SHELLS = {"sh", "bash", "zsh"}
ASSIGNMENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=.*", re.S)
OPERATOR = re.compile(r"[();<>|&]+")


def segments(command: str) -> list:
    """The simple commands in a command line, each as its list of words."""
    text = command.replace("`", " ; ").replace("\n", " ; ")
    try:
        lexer = shlex.shlex(text, posix=True, punctuation_chars=True)
        lexer.whitespace_split = True
        words = list(lexer)
    except ValueError:  # unbalanced quotes: split roughly, and still look
        words = OPERATOR.sub(" ; ", text).split()
    found, current = [], []
    for word in words + [";"]:
        if not OPERATOR.fullmatch(word):
            current.append(word)
        elif current:
            found.append(current)
            current = []
    return found


def vercel_args(words: list) -> "list | None":
    """The arguments of a vercel call in command position, or None if this isn't one."""
    i = 0
    while i < len(words):
        name = os.path.basename(words[i])
        if ASSIGNMENT.fullmatch(words[i]):
            i += 1
        elif name in LAUNCHERS or tuple(words[i:i + 2]) in TWO_WORD_LAUNCHERS:
            i += 1 if name in LAUNCHERS else 2
            while i < len(words) and words[i].startswith("-"):
                i += 1
        elif name in ("vercel", "vc") or name.startswith("vercel@"):
            return words[i + 1:]
        else:
            return None
    return None


def targets_git_only(scope: "str | None", folder: str) -> bool:
    if scope is not None:
        return scope in GIT_ONLY_SCOPES
    return bool(GIT_ONLY_DIRS & set(PurePosixPath(folder).parts))


def judge(args: list, cwd: str) -> "str | None":
    """Why this vercel call, run in folder `cwd`, is refused, or None."""
    positionals, scope, cwd_option, flags = [], None, "", []
    i = 0
    while i < len(args):
        arg = args[i]
        if arg.startswith("-"):
            name, has_value, value = arg.partition("=")
            if name in VALUE_OPTIONS and not has_value:
                value = args[i + 1] if i + 1 < len(args) else ""
                i += 1
            if name in ("-S", "--scope"):
                scope = value.lower()
            elif name == "--cwd":
                cwd_option = value
            flags.append(name)
        else:
            positionals.append(arg)
        i += 1
    if not positionals:
        if flags and all(flag in INFO_FLAGS for flag in flags):
            return None
        return "`vercel` with no command deploys"
    command, sub = positionals[0], (positionals[1:] or [None])[0]
    shown = f"`vercel {command[:60]}`"
    if command == "deploy" or command not in COMMANDS:
        return f"{shown} deploys"
    if command in ("redeploy", "link"):
        return f"{shown} is never run by agents"
    if command == "promote" and scope not in PROMOTE_SCOPES:
        allowed = ", ".join(sorted(PROMOTE_SCOPES)) or "none configured"
        return f"{shown} changes production and is allowed only as a runbook's rollback, with --scope in: {allowed}"
    if command in GIT_ONLY_COMMANDS and targets_git_only(scope, os.path.join(cwd, cwd_option)):
        reads = (command == "rollback" and sub == "status") or (command in ("alias", "ln") and sub in ("ls", "list"))
        if not reads:
            return f"{shown} targets a product whose production and aliases change only through Git (its runbook)"
    return None


def refusal(command: str, cwd: str, depth: int = 0) -> "str | None":
    for words in segments(command):
        start = 0
        while start < len(words) and ASSIGNMENT.fullmatch(words[start]):
            start += 1
        words = words[start:]
        if words and words[0] == "cd":
            cwd = os.path.join(cwd, words[1]) if len(words) > 1 else os.path.expanduser("~")
            continue
        if words and os.path.basename(words[0]) in SHELLS:
            for j in range(1, len(words) - 1):
                flag = words[j]
                if flag.startswith("-") and not flag.startswith("--") and "c" in flag and depth < 3:
                    reason = refusal(words[j + 1], cwd, depth + 1)
                    if reason:
                        return reason
                    break
            continue
        args = vercel_args(words)
        if args is not None:
            reason = judge(args, cwd)
            if reason:
                return reason
    return None


def main() -> None:
    try:
        event = json.load(sys.stdin)
    except json.JSONDecodeError:
        return
    if event.get("tool_name") != "Bash" or not event.get("agent_type"):
        return
    command = (event.get("tool_input") or {}).get("command")
    reason = refusal(command, str(event.get("cwd") or "")) if isinstance(command, str) else None
    if reason:
        print(
            f"Blocked: agents don't deploy with the Vercel CLI; {reason}. Products deploy through Git, as each "
            "product's runbook says. Don't try another form of the command; report the need up the chain.",
            file=sys.stderr,
        )
        sys.exit(2)


if __name__ == "__main__":
    main()
