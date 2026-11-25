#!/usr/bin/env python3
"""PreToolUse hook for Bash: agents never deploy with the Vercel CLI. Always on.

Products deploy through Git (a push or merge that Vercel builds), never from the
CLI. A `vercel deploy` without --prod still goes to production when it is a
project's first deployment, so even "just a test build" from the CLI is refused.

In agent sessions (the hook input names an `agent_type`: a subagent, or the
--agent type on the main thread), this blocks (exit 2, reason on stderr) any
`vercel` or `vc` call that:
- deploys: `vercel deploy`, or `vercel` with no command, with a path or with
  anything that isn't one of its commands (`vercel --prod`, `vercel .`);
- runs `redeploy`, or `link` (it writes a Vercel OIDC token to `.env.local`);
- runs `promote`, except with a `--scope` in company.json's integrations "vercel",
  "promote_scopes": the teams whose runbook rolls back with Instant Rollback and
  then promotes;
- runs `rollback` (other than `rollback status`), an alias write (anything but
  `alias ls`) or `rolling-release` with no `--scope`, or with one in
  "git_only_scopes", the teams whose production and aliases change only through
  Git. Without a "vercel" in company.json's integrations, every one is refused;
- could show production's values of environment variables. Agents write all
  variables and read the non-production ones: `env add`, `rm`, `remove` and
  `update` run, and `pull`, `env pull` and `env run` run only when the whole
  command's raw text has no `prod` as a word start, quotes and backslashes taken
  out (`pro""d` counts), and no `$`, backtick, glob (zsh's `(` too) or brace,
  which fill a word in later. They default to development. Text, not parsing, on
  purpose: it can't be misread. `--id` is refused too (a deployment may be
  production's), and `env run` when the text names `vercel` or `vc` more than
  once: its command can't run them, however a shell is fed. So are `env ls` with
  `--json` or `--format` (it prints Config values; the table runs), and `vercel
  api` on a path with `/env` or `decrypt`. Without a "vercel" in company.json's
  integrations, `pull`, `env pull` and `env run` are refused; an empty one, {},
  turns them on, and the founder's "value_scopes" there limits them to calls
  with a `--scope` in that list ([]: none). Production's values stay unreadable
  for agents, whatever is configured.

It checks every command in a chain, subshell, `sh -c` string or `eval`,
through variable assignments and launchers such as `npx`, `bunx`, `pnpm dlx`,
`env` and `sudo`. Comments are never run, so they aren't checked. Nor is the
body of a quoted heredoc (`<<'EOF'`), which is text, unless a shell runs it: fed
to bash, sh, zsh, dash or ksh (`bash <<'EOF'`, `sudo bash -s`, `cat <<'EOF' |
bash`), read by `eval`, `source` or `.`, or inside a substitution that such a
command runs (`bash -c "$(cat <<'EOF' …)"`). An unquoted heredoc's body is
always checked, since the shell runs its `$(...)` and backticks, and so are
the `$(...)` and backticks in double quotes. A redirection's file descriptor
(the 2 of `2>&1`) isn't taken for an argument. A plain `claude` session isn't
limited. Any failure in this check refuses the command, and so does a
company.json that can't be read when the command calls vercel.

It stops mistakes; it isn't a sandbox.
"""

import json
import os
import re
import shlex
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

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
ENV_VALUE_OPTIONS = {"--environment", "--git-branch", "--id", "--project", "--type", "--value"}  # `vercel env * --help`
LITERAL_PARTS = re.compile(r"\\\n|[\\'\"]")  # what the shell removes from a word: quotes, escapes, line continuations
NAMES_PRODUCTION = re.compile(r"(?:\b|-e)prod", re.I)  # `-e` glued on: `vercel env run -eproduction`
FILLED_IN_LATER = re.compile(r"[$`*?\[{(]")
RUNS_VERCEL = re.compile(r"\b(?:vercel|vc)\b", re.I)
VALUE_FORMATS = {"--json", "--format", "-F"}  # `vercel env ls` prints Config values with these
ENV_API = re.compile(r"/env(?![a-z-])|decrypt", re.I)  # `vercel api`'s ways to values: /v10/projects/<id>/env, /v3/env
LAUNCHERS = {"npx", "bunx", "pnpx", "env", "command", "exec", "time", "nohup", "sudo"}
LAUNCHER_VALUE_OPTIONS = {
    "sudo": {"-u", "-g", "-C", "-D", "-h", "-p", "-r", "-t", "-T", "-U"},
    "env": {"-u", "-C", "-P"},
}
TWO_WORD_LAUNCHERS = {("pnpm", "dlx"), ("pnpm", "exec"), ("yarn", "dlx"), ("npm", "exec"), ("bun", "x")}
SHELLS = {"sh", "bash", "zsh", "dash", "ksh"}
RUNNERS = SHELLS | {"eval", "source", "."}  # they run as commands the text they read or are given
ASSIGNMENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=.*", re.S)
FD_REDIRECT = re.compile(r"\d+(?=[<>])")
OPERATOR = re.compile(r"[();<>|&]+")


def starts_word(text: str, i: int) -> bool:
    return i == 0 or text[i - 1] in " \t\n;&|()<>"


def quote_end(text: str, i: int) -> int:
    """Where the quoted string opening at text[i] ends: just past its closing quote, or the end of the text."""
    end = text.find("'", i + 1) if text[i] == "'" else expand(text, i + 1, '"')[0]
    return len(text) if end < 0 or end >= len(text) else end + 1


def substitution(text: str, i: int) -> tuple:
    """The code of the command substitution opening at text[i] (`$(` or a backtick), and where it ends."""
    if text[i] == "`":
        j = i + 1
        while j < len(text) and text[j] != "`":
            j += 2 if text[j] == "\\" else 1
        return text[i + 1:j], j + 1
    depth, j = 1, i + 2
    while j < len(text):
        if text[j] in "'\"":
            j = quote_end(text, j)
            continue
        if text[j] == "\\":
            j += 2
            continue
        depth += {"(": 1, ")": -1}.get(text[j], 0)
        if depth == 0:
            return text[i + 2:j], j + 1
        j += 1
    return text[i + 2:], len(text)


def expand(text: str, i: int, quote: str) -> tuple:
    """Read text from i as the shell expands a double-quoted string (quote '"') or an unquoted heredoc body (quote
    ''): the index of the closing quote (or the end of the text), the text with each command substitution replaced
    by `_`, and the substitutions' code, which the shell runs."""
    literal, code = "", []
    while i < len(text) and not (quote and text[i] == quote):
        if text.startswith("$(", i) or text[i] == "`":
            inner, i = substitution(text, i)
            literal, code = literal + "_", code + [inner]
        else:
            step = 2 if text[i] == "\\" else 1
            literal, i = literal + text[i:i + step], i + step
    return min(i, len(text)), literal, code


def heredoc_delimiter(text: str, i: int) -> tuple:
    """The heredoc delimiter word at text[i]: its text, whether any of it is quoted, and where it ends."""
    while i < len(text) and text[i] in " \t":
        i += 1
    word, quoted = "", False
    while i < len(text) and text[i] not in " \t\n;&|<>()":
        if text[i] in "'\"":
            end = quote_end(text, i)
            word, quoted, i = word + text[i + 1:end - 1], True, end
        elif text[i] == "\\":
            word, quoted, i = word + text[i + 1:i + 2], True, i + 2
        else:
            word, i = word + text[i], i + 1
    return word, quoted, i


def heredoc_body(text: str, i: int, delimiter: str, strip_tabs: bool) -> tuple:
    """The heredoc body starting at text[i], and where the line after its delimiter line starts."""
    start = i
    while i < len(text):
        end = text.find("\n", i)
        end = len(text) if end < 0 else end
        if (text[i:end].lstrip("\t") if strip_tabs else text[i:end]) == delimiter:
            return text[start:i], end + 1
        i = end + 1
    return text[start:], len(text)


def last_char(out: list) -> str:
    for piece in reversed(out):
        if piece.strip():
            return piece.strip()[-1]
    return ""


def ends_pipeline(command: str, i: int) -> bool:
    """Whether command[i] ends a pipeline: `;`, `&`, `&&` or `||` (a newline is handled where it's read)."""
    c, before, after = command[i], command[i - 1:i], command[i + 1:i + 2]
    if c == "&":
        return before not in ("<", ">", "|") and after != ">"  # not >&, <&, &> or |&
    return c == ";" or c == "|" and "|" in (before, after)


def shell_code(command: str, runs: bool = False) -> str:
    """The command line as the shell runs it. The text it never runs goes: comments, the file descriptor of a
    redirection (the 2 of `2>&1`), and a quoted heredoc's body unless a shell runs it, which one does when the
    heredoc's pipeline has a shell, `eval`, `source` or `.` in it, or when `runs` says this code's output is run (a
    substitution in such a pipeline). The command substitutions in double quotes and heredocs, and the heredoc bodies
    a shell runs, become commands of their own at the end of their pipeline."""
    out, pending, bodies, substitutions, depth, start, i = [], [], [], [], 0, 0, 0
    texts = set()  # where in out the unquoted heredoc bodies are: checked for vercel, but not commands of the pipeline

    def end_pipeline():
        nonlocal bodies, substitutions, start
        if bodies or substitutions:
            code = "".join(piece for k, piece in enumerate(out) if k >= start and k not in texts)
            shell = runs or any(runs_shell(words) for words in split(code))
            out.extend(f" ; {shell_code(body)} ; " for body in bodies if shell)
            out.extend(f" ; {shell_code(code, shell)} ; " for code in substitutions)
            bodies, substitutions = [], []
        start = len(out)

    while i < len(command):
        c = command[i]
        if depth == 0 and ends_pipeline(command, i):
            end_pipeline()
        if c == "'":
            end = quote_end(command, i)
        elif c == '"':
            end, literal, code = expand(command, i + 1, '"')
            out.append('"' + literal + ('"' if end < len(command) else ""))
            substitutions += code
            i = end + 1
            continue
        elif c == "\\":
            end = i + 2
        elif c == "#" and starts_word(command, i):
            end = command.find("\n", i)
            i = len(command) if end < 0 else end
            continue
        elif c.isdigit() and starts_word(command, i) and FD_REDIRECT.match(command, i):
            i = FD_REDIRECT.match(command, i).end()
            continue
        elif command.startswith("<<<", i):
            end = i + 3
        elif command.startswith("<<", i):
            strip_tabs = command.startswith("<<-", i)
            delimiter, quoted, i = heredoc_delimiter(command, i + 2 + strip_tabs)
            if delimiter:
                pending.append((delimiter, strip_tabs, quoted))
            out.append(" << ")
            continue
        elif c == "\n":
            continues = last_char(out) == "|"  # the pipeline goes on after the heredoc bodies
            i += 1
            for delimiter, strip_tabs, quoted in pending:
                body, i = heredoc_body(command, i, delimiter, strip_tabs)
                if quoted:
                    bodies.append(body)
                else:  # the shell runs its $(...) and backticks, quoted or not
                    texts.add(len(out))
                    out.append("\n" + body)
                    substitutions += expand(body, 0, "")[2]
            pending = []
            if depth == 0 and not continues:
                end_pipeline()
            out.append("\n")
            continue
        else:
            end = i + 1
            depth = depth + 1 if c == "(" else max(depth - 1, 0) if c == ")" else depth
        out.append(command[i:end])
        i = end
    end_pipeline()
    return "".join(out)


def segments(command: str) -> list:
    """The simple commands in a command line, each as its list of words."""
    return split(shell_code(command))


def split(code: str) -> list:
    """The simple commands in code from shell_code, each as its list of words."""
    text = code.replace("`", " ; ").replace("\n", " ; ")
    try:
        lexer = shlex.shlex(text, posix=True, punctuation_chars=True)
        lexer.whitespace_split = True
        lexer.commenters = ""  # shell_code dropped the comments; a `#` inside a word, as in `${#x}`, isn't one
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


def command_start(words: list) -> int:
    """Where the command word of a simple command is: past variable assignments, and launchers and their options."""
    i = 0
    while i < len(words):
        name = os.path.basename(words[i])
        if ASSIGNMENT.fullmatch(words[i]):
            i += 1
        elif name in LAUNCHERS or tuple(words[i:i + 2]) in TWO_WORD_LAUNCHERS:
            i += 1 if name in LAUNCHERS else 2
            while i < len(words) and words[i].startswith("-"):
                i += 2 if words[i] in LAUNCHER_VALUE_OPTIONS.get(name, ()) else 1
        else:
            break
    return i


def command_name(words: list) -> str:
    i = command_start(words)
    return os.path.basename(words[i]) if i < len(words) else ""


def vercel_args(words: list) -> "list | None":
    """The arguments of a vercel call in command position, or None if this isn't one."""
    name = command_name(words)
    return words[command_start(words) + 1:] if name in ("vercel", "vc") or name.startswith("vercel@") else None


def runs_shell(words: list) -> bool:
    """Whether this simple command runs, as commands, the text it reads or is given."""
    return command_name(words) in RUNNERS


def settings() -> "dict | None":
    """company.json's integrations "vercel", or None where it isn't there. A company.json that can't be read raises."""
    import company_config  # here, inside main()'s fail-closed handling

    return company_config.integration("vercel", Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path(__file__).resolve().parents[2]))


def scopes(own: "dict | None", name: str) -> "set | None":
    """The team slugs these settings list under name, in lower case; None when it isn't there. A value of the wrong kind
    raises."""
    if own is None or name not in own.keys():
        return None
    if not (isinstance(own[name], list) and all(isinstance(slug, str) and slug for slug in own[name])):
        raise ValueError(f"company.json: integrations vercel: {name} is a list of team slugs")
    return {slug.lower() for slug in own[name]}


def judge(args: list, raw: str) -> "str | None":
    """Why this vercel call, part of the command line `raw`, is refused, or None."""
    own = settings()
    promote_scopes, git_only = scopes(own, "promote_scopes") or set(), scopes(own, "git_only_scopes") or set()
    value_scopes = scopes(own, "value_scopes")
    positionals, scope, flags = [], None, []
    i = 0
    while i < len(args):
        arg = args[i]
        if arg.startswith("-"):
            name, has_value, value = arg.partition("=")
            takes_value = name in VALUE_OPTIONS or (positionals[:1] == ["env"] and name in ENV_VALUE_OPTIONS)
            if takes_value and not has_value:
                value = args[i + 1] if i + 1 < len(args) else ""
                i += 1
            if name in ("-S", "--scope"):
                scope = value.lower()
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
    if command == "promote" and scope not in promote_scopes:
        allowed = ", ".join(sorted(promote_scopes)) or "none configured"
        return f"{shown} changes production and is allowed only as a runbook's rollback, with --scope in: {allowed}"
    if command in GIT_ONLY_COMMANDS and (own is None or not scope or scope in git_only):
        reads = (command == "rollback" and sub == "status") or (command in ("alias", "ln") and sub in ("ls", "list"))
        if not reads and own is None:
            return (f"{shown} changes production or its aliases; it is off until company.json's integrations has a "
                    '"vercel" (docs/guards.md)')
        if not reads:
            return (f"{shown} targets a product whose production and aliases change only through Git (its runbook), or "
                    'names no --scope; company.json\'s integrations "vercel" lists those teams in "git_only_scopes"')
    exposes = "pull" if command == "pull" else f"env {sub}" if command == "env" and sub in ("pull", "run") else None
    if exposes:
        text = LITERAL_PARTS.sub("", raw)
        if own is None:
            return (f"`vercel {exposes}` hands a project's variables, secrets included, to a file or a command; it is off "
                    'until company.json\'s integrations has a "vercel" (docs/guards.md)')
        if value_scopes is not None and scope not in value_scopes:
            allowed = ", ".join(sorted(value_scopes)) or "none configured"
            return (f"`vercel {exposes}` hands a project's variables, secrets included, to a file or a command; it runs "
                    f"only with --scope in: {allowed}")
        if "--id" in flags or NAMES_PRODUCTION.search(text) or FILLED_IN_LATER.search(raw):
            return (f"`vercel {exposes}` hands a project's variables, secrets included, to a file or a command, and "
                    "production's stay unreadable; it runs only with no `--id`, and a command text with no `prod`, "
                    "`$`, backtick, glob, `(` or brace")
        if exposes == "env run" and len(RUNS_VERCEL.findall(text)) > 1:  # the text: a heredoc or pipe can feed a shell
            return "`vercel env run` can't run vercel: the command's text may name it only once"
    lists = command == "env" and sub not in ("add", "rm", "remove", "update", "pull", "run")
    if lists and VALUE_FORMATS & set(flags):
        return f"`vercel env {sub}` with `--json` or `--format` prints values; agents read the table"
    if command == "api" and ENV_API.search(" ".join(args)):
        return "`vercel api` on an env path reads values; agents read names with `vercel env ls`"
    return None


def refusal(command: str, depth: int = 0, raw: str = "") -> "str | None":
    raw = raw or command
    for words in segments(command):
        name, k = command_name(words), command_start(words)
        if name == "eval" and depth < 3:  # eval runs its arguments, joined, as a command line
            reason = refusal(" ".join(words[k + 1:]), depth + 1, raw)
            if reason:
                return reason
            continue
        if name in SHELLS:
            for j in range(k + 1, len(words) - 1):
                flag = words[j]
                if flag.startswith("-") and not flag.startswith("--") and "c" in flag and depth < 3:
                    reason = refusal(words[j + 1], depth + 1, raw)
                    if reason:
                        return reason
                    break
            continue
        args = vercel_args(words)
        if args is not None:
            reason = judge(args, raw)
            if reason:
                return reason
    return None


def main() -> None:
    try:
        event = json.load(sys.stdin)
        if event.get("tool_name") != "Bash" or not event.get("agent_type"):
            return
        command = (event.get("tool_input") or {}).get("command")
        reason = refusal(command) if isinstance(command, str) else None
    except Exception as error:  # a crash would exit 1, which doesn't block by itself
        reason = f"this hook couldn't check the command ({type(error).__name__}: {str(error)[:200]})"
    if reason:
        print(
            f"Blocked: agents don't deploy with the Vercel CLI; {reason}. Products deploy through Git, as each "
            "product's runbook says. Don't try another form of the command; report the need up the chain.",
            file=sys.stderr,
        )
        sys.exit(2)


if __name__ == "__main__":
    main()
