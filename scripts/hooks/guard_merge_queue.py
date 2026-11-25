r"""Bash: no agent or session takes a pull request out of a GitHub merge queue, or cancels a workflow run.

A merge queue tests what lands together; an agent that pulls its pull request out, or cancels the run that tests it,
throws away the others' wait too. Closing a PR to take it out of the queue is the same action. Re-runs (`gh run rerun`,
the REST rerun paths, a check suite's rerequest) aren't barred: runbooks direct them.

guard_marketing_tools.py calls queue_reason for every Bash call, the main session's included (with or without an
agent_type): its settings entry runs in every session and fails closed. Refused, with the reason, the bar and what to
do instead:
- `gh run cancel` in any form (`--force`, `-R` before the subcommand), and `gh run` with a subcommand the shell
  fills in;
- `gh pr merge` with `--disable-auto`;
- `gh pr close` when the command's text names a queue anywhere (its `--comment`, a shell comment): with no network
  this hook can't tell whether the PR is queued;
- a GitHub API call (`gh api`; curl, wget, httpie or xh when the command names github or graphql) whose command
  names the mutation dequeuePullRequest or disablePullRequestAutoMerge (what `--disable-auto` sends), that closes a
  PR (closePullRequest, updatePullRequest in a command that names closed, or a REST write whose fields set
  `state` to closed) when the command names a queue, or whose path cancels a run (`actions/runs/<id>/cancel` or
  `force-cancel`);
- a GraphQL call this hook can't read, which it refuses (fail closed): a file it would send (`-F query=@<file>`,
  `--input <file>`, curl's `-d @<file>`, `-T`, `-K`, httpie's `@<file>`) that doesn't exist yet, isn't a regular file,
  is over 5 MB, is relative after a `cd`, or that the command names again (it may write it first); stdin (`--input -`,
  `@-`, `/dev/stdin`, httpie's or xh's body to a graphql URL) from a pipe, a file descriptor, a heredoc or here-string
  the shell fills in, or anything but the call's own heredoc, here-string or `< <file>` on its stdin (a group's or
  subshell's redirect, `exec <`, a pipe into a shell, or a redirect of another file descriptor such as `3<`); a query,
  or curl's or httpie's data, holding a variable, `$(...)` or backtick; an endpoint the shell fills in, with a POST. A
  file it can read is refused if it names one of those mutations or paths. A heredoc or here-string written in the
  command is read as the command's text;
- whatever runs it, a command whose text calls one of those mutations (its name, then `(input`), holds a run's
  cancel path under `repos/<owner>/<repo>/`, or lists gh, run and cancel as quoted strings (a python or node call):
  python's or node's code is read only this way.

What it reads: every simple command, in chains, pipelines, subshells, `$(...)`, backticks, `<(...)` and `${...}`, the
string of `sh -c` (bash, zsh, dash, ksh), `eval`'s words, and a heredoc, here-string or piped text fed to a shell
(`bash`, `bash -s`, `bash /dev/stdin`, `source /dev/stdin`). `$'...'` is decoded for the text checks too. A
`gh` word anywhere in a command counts, so wrappers (`env`, `sudo`, `xargs`, `timeout`, `find -exec`) don't hide it,
and so does a word the shell fills in followed by a barred form (`$(which gh) run cancel`). Quoted text, a quoted
heredoc's body and comments are text, not commands. For the text checks, quotes and backslashes are taken out
(`g""h`, `de\queue`), JSON's `\u` escapes are read, and case doesn't count. A command whose text holds no HINT (gh,
github, graphql, `actions/`, `run cancel` and the rest) and no `$'` isn't parsed; one that is and fails to parse is
refused.

It stops mistakes; it isn't a sandbox.
"""

import os
import re
import stat

MARK = "\x00"  # stands in a word for text the shell fills in: a variable, a `$(...)`, a backtick
DEPTH = 6  # nested substitutions and shell strings read; deeper is refused (a crash, caught below)
MAX_FILE = 5 * 1024 * 1024
SHELLS = {"sh", "bash", "zsh", "dash", "ksh"}
HTTP_CLIENTS = {"curl", "wget", "http", "https", "xh", "xhs"}
MOVES = {"cd", "pushd", "popd"}
STDIN = {"-", "/dev/stdin", "/dev/fd/0"}
ASSIGNMENT = re.compile(r"[A-Za-z_]\w*\+?=", re.S)
NAME = re.compile(r"[A-Za-z_]\w*")
OPERATORS = ["<<<", "<<-", "&>>", "<<", ">>", ">|", "<>", "<&", ">&", "&>", "||", "&&", "|&", ";;", "<", ">", "|",
             "&", ";", "(", ")"]

# The text checks read the command with quotes and backslashes taken out and JSON's \u escapes read, in lower case.
UNICODE = re.compile(r"\\u([0-9a-fA-F]{4})")
ESCAPES = re.compile(r"\\[ntr]")
LITERAL_PARTS = re.compile(r"\\\n|[\\'\"]")
HINT = re.compile(r"(?<![\w.-])gh(?![\w.-])|github|graphql|dequeue|disablepullrequest|disable-auto|actions/|"
                  r"run\s+cancel")
MUTATIONS = re.compile(r"dequeuepullrequest|disablepullrequestautomerge")
CALL = re.compile(r"(?:dequeuepullrequest|disablepullrequestautomerge)[\s,]*(?:#[^\n]*\n[\s,]*)*\([\s,]*input\b")


def run_actions(run_id: str) -> str:
    """A run's cancel path (its rerun paths aren't barred)."""
    return rf"actions/runs/{run_id}/(?:force-cancel|cancel)(?![\w-])"


RUN_ENDPOINT = re.compile(run_actions(r"[^/\s]+"))
RUN_PATH = re.compile(r"repos/[^/\s]+/[^/\s]+/" + run_actions(r"[^/\s<>]+"))
LIST_FORM = re.compile(r"""["']gh["']\s*,\s*\[?\s*["']run["']\s*,\s*["']cancel["']""")
CLOSES = re.compile(r"closepullrequest")
UPDATES = re.compile(r"updatepullrequest")  # a close when the command also names closed (a variable may carry it)
CLOSED_WORD = re.compile(r"(?<![\w-])closed(?![\w-])")
CLOSED_STATE = re.compile(r"state[\s:=]*closed")
GITHUB = re.compile(r"github|graphql")

REPO_FLAGS = {"-R", "--repo"}
API_VALUE_FLAGS = {"-X", "--method", "-H", "--header", "-f", "--raw-field", "-F", "--field", "-q", "--jq", "-t",
                   "--template", "--input", "--hostname", "--cache", "-p", "--preview"}
API_FIELDS = {"-f", "--raw-field", "-F", "--field"}
# curl, wget, httpie and xh: the options whose value is data or a file to send (`man curl`, `wget --help`).
CURL_DATA = {"-d", "--data", "--data-ascii", "--data-binary", "--data-raw", "--data-urlencode", "--json", "-F",
             "--form"}
CURL_FILES = {"-T", "--upload-file", "-K", "--config"}
CURL_VALUE_FLAGS = CURL_DATA | CURL_FILES | {"-H", "--header", "-X", "--request", "-u", "--user", "-o", "--output",
                                             "-A", "--user-agent", "-e", "--referer", "-b", "--cookie", "-c",
                                             "--cookie-jar", "-x", "--proxy", "--url", "-w", "--write-out", "-m",
                                             "--max-time", "--connect-timeout", "-r", "--range", "--retry"}
WGET_DATA = {"--post-data", "--body-data"}
WGET_FILES = {"--post-file", "--body-file", "-i", "--input-file"}
WGET_VALUE_FLAGS = WGET_DATA | WGET_FILES | {"--header", "-O", "--output-document", "--method", "-U", "--user-agent"}
HTTPIE_VALUE_FLAGS = {"--raw", "-a", "--auth", "-A", "--auth-type", "-o", "--output", "--session", "--verify",
                      "--cert", "--cert-key", "--proxy"}

BAR = ("No agent or session takes a pull request out of a merge queue, or cancels a workflow run (docs/guards.md; "
       "scripts/hooks/guard_merge_queue.py).")
INSTEAD = "a queued PR stays in the queue; tell your manager (a NEEDS-CEO-NOW line for a CTO); a refusal is final."


def refused(reason: str) -> str:
    return f"Blocked: {reason}. {BAR} Instead: {INSTEAD}"


def cant(what: str) -> str:
    return (f"Blocked: this hook can't read {what}, so it refuses the call (fail closed). An ordinary GraphQL read "
            "runs with its query in the command's own text (`-f query='...'` in single quotes, values as "
            "`-F name=value`) or in a file that already exists (`-F query=@<file>`, by absolute path after a `cd`): "
            f"run it again that way. {BAR} Instead of a barred action: {INSTEAD}")


def shown(word: str) -> str:
    return word.replace(MARK, "$...")[:80]


def flatten(text: str) -> str:
    """The text as the checks read it: JSON's \\u escapes read, `\\n` a space, quotes and backslashes out, lower case."""
    text = UNICODE.sub(lambda match: chr(int(match.group(1), 16)), text)
    return LITERAL_PARTS.sub("", ESCAPES.sub(" ", text)).lower()


# The shell reading: simple commands with their words and their stdin.

class Command:
    """One simple command: its words (MARK where the shell fills text in), its stdin and the command piped into it."""

    def __init__(self, upstream: "Command | None" = None):
        self.words = []
        self.inputs = []  # ("file", word) for `<`, ("fd", word) for `<&`, ("text", text) for a heredoc or here-string
        self.upstream = upstream


def parse(text: str, depth: int = 0) -> list:
    """Every simple command in text, nested ones included."""
    commands = []
    read(text, 0, depth, commands, closer=False)
    return commands


def read(text: str, i: int, depth: int, out: list, closer: bool) -> int:
    """Read commands from text[i:] into out, up to the end, or with closer up to the `)` that closes a `$(` or `<(`;
    return where it stopped."""
    if depth > DEPTH:
        raise RecursionError("commands nested too deep")
    n, parens, heredocs = len(text), 0, []
    state = {"command": Command(), "word": None, "redirect": None}

    def add(part: str):
        state["word"] = (state["word"] or "") + part

    def end_word():
        word, redirect, command = state["word"], state["redirect"], state["command"]
        if word is None:
            return
        if redirect == "<<<":
            command.inputs.append(("text", word))
        elif redirect in ("<", "<>"):
            command.inputs.append(("file", word))
        elif redirect == "<&":
            command.inputs.append(("fd", word))
        elif redirect is None:
            command.words.append(word)
        state["word"], state["redirect"] = None, None  # an output's target is dropped

    def end_command(piped: bool = False):
        end_word()
        command = state["command"]
        if command.words or command.inputs:
            out.append(command)
        state["command"], state["redirect"] = Command(command if piped else None), None

    while i < n:
        c = text[i]
        if c in " \t":
            end_word()
            i += 1
        elif c == "\n":
            end_word()
            i += 1
            for command, delimiter, strip_tabs, quoted in heredocs:
                body, i = heredoc_body(text, i, delimiter, strip_tabs)
                command.inputs.append(("text", body if quoted else read_double(body, 0, depth, out, "")[1]))
            heredocs = []
            if state["command"].words or state["command"].inputs:  # a `|`, `&&` or `||` before it leaves it open
                end_command()
        elif c == "#" and state["word"] is None:
            end = text.find("\n", i)
            i = n if end < 0 else end
        elif c == "\\":
            if not text.startswith("\\\n", i):
                add(text[i + 1:i + 2])
            i += 2
        elif c == "'":
            end = text.find("'", i + 1)
            end = n if end < 0 else end
            add(text[i + 1:end])
            i = end + 1
        elif c == '"':
            i, part = read_double(text, i + 1, depth, out, '"')
            add(part)
        elif c == "$":
            i, part = read_dollar(text, i, depth, out)
            add(part)
        elif c == "`":
            i, part = read_backtick(text, i, depth, out)
            add(part)
        elif c in "<>" and text.startswith("(", i + 1):  # a process substitution: its commands run, it's a path
            i = read(text, i + 2, depth + 1, out, closer=True)
            add(MARK)
        elif c in "<>&|;()":
            fd = None
            if c in "<>" and state["word"] is not None and state["word"].isdigit():
                fd, state["word"] = state["word"], None  # a file descriptor: the 2 of `2>&1`
            end_word()
            op = next(op for op in OPERATORS if text.startswith(op, i))
            i += len(op)
            other_fd = fd not in (None, "0")  # `3< x` or `3<<EOF` isn't the command's stdin
            if op in ("<<", "<<-"):
                delimiter, quoted, i = heredoc_delimiter(text, i)
                heredocs.append((Command() if other_fd else state["command"], delimiter, op == "<<-", quoted))
            elif op in ("<<<", "<", "<>", "<&"):
                state["redirect"] = ">" if other_fd else op
            elif op in (">", ">>", ">|", ">&", "&>", "&>>"):
                state["redirect"] = ">"
            elif op in ("|", "|&"):
                end_command(piped=True)
            elif op == ")" and closer and parens == 0:
                end_command()
                return i
            else:
                parens = parens + 1 if op == "(" else max(parens - 1, 0) if op == ")" else parens
                end_command()
        else:
            add(c)
            i += 1
    end_command()
    return n


def read_double(text: str, i: int, depth: int, out: list, quote: str) -> tuple:
    """Read a double-quoted string from text[i] to its closing quote (quote '"'), or an unquoted heredoc body to its
    end (quote ''): where it ends, and its text with MARK for what the shell fills in."""
    n, part = len(text), ""
    while i < n and not (quote and text[i] == quote):
        c = text[i]
        if c == "\\":
            follower = text[i + 1:i + 2]
            part += "" if follower == "\n" else follower if follower in "$`\"\\" else c + follower
            i += 2
        elif c == "$":
            i, piece = read_dollar(text, i, depth, out, quoted=True)
            part += piece
        elif c == "`":
            i, piece = read_backtick(text, i, depth, out)
            part += piece
        else:
            part += c
            i += 1
    return min(i + 1, n), part


def read_dollar(text: str, i: int, depth: int, out: list, quoted: bool = False) -> tuple:
    """Read the expansion at text[i] (a `$`): where it ends, and MARK, or the literal text it stands for."""
    after = text[i + 1:i + 2]
    if after == "(":
        return read(text, i + 2, depth + 1, out, closer=True), MARK
    if after == "{":
        end, level = i + 2, 1
        while end < len(text) and level:
            level += {"{": 1, "}": -1}.get(text[end], 0)
            end += 1
        out.extend(parse(text[i + 2:end - 1], depth + 1))  # `${x:-$(...)}` runs its command
        return end, MARK
    if after == "'" and not quoted:  # ANSI-C quoting: its escapes read, so `$'\x67h'` is gh
        end = i + 2
        while end < len(text) and text[end] != "'":
            end += 2 if text[end] == "\\" else 1
        body = re.sub(r"\\x([0-9a-fA-F]{1,2})|\\u([0-9a-fA-F]{4})|\\([0-7]{1,3})|\\(.)",
                      lambda m: chr(int(m.group(1), 16)) if m.group(1) else chr(int(m.group(2), 16)) if m.group(2)
                      else chr(int(m.group(3), 8)) if m.group(3) else m.group(4), text[i + 2:end], flags=re.S)
        return end + 1, body
    if after == '"' and not quoted:
        return read_double(text, i + 2, depth, out, '"')
    name = NAME.match(text, i + 1)
    if name:
        return name.end(), MARK
    if after and after in "0123456789@*#?-$!":
        return i + 2, MARK
    return i + 1, "$"


def read_backtick(text: str, i: int, depth: int, out: list) -> tuple:
    end = i + 1
    while end < len(text) and text[end] != "`":
        end += 2 if text[end] == "\\" else 1
    out.extend(parse(re.sub(r"\\([`$\\])", r"\1", text[i + 1:end]), depth + 1))
    return end + 1, MARK


def heredoc_delimiter(text: str, i: int) -> tuple:
    """The heredoc end word at text[i]: its text, whether any of it is quoted, and where it ends."""
    while i < len(text) and text[i] in " \t":
        i += 1
    word, quoted = "", False
    while i < len(text) and text[i] not in " \t\n;&|<>()":
        if text[i] in "'\"":
            end = text.find(text[i], i + 1)
            end = len(text) if end < 0 else end
            word, quoted, i = word + text[i + 1:end], True, end + 1
        elif text[i] == "\\":
            word, quoted, i = word + text[i + 1:i + 2], True, i + 2
        else:
            word, i = word + text[i], i + 1
    return word, quoted, i


def heredoc_body(text: str, i: int, delimiter: str, strip_tabs: bool) -> tuple:
    """The heredoc body from text[i], and where the line after its end line starts."""
    start = i
    while i < len(text):
        end = text.find("\n", i)
        end = len(text) if end < 0 else end
        if (text[i:end].lstrip("\t") if strip_tabs else text[i:end]) == delimiter:
            return text[start:i], end + 1
        i = end + 1
    return text[start:], len(text)


def program(word: str) -> str:
    return os.path.basename(word.lstrip("="))  # zsh's `=gh` is gh's path


def stdin_texts(command: Command) -> list:
    """The text a command reads on stdin, as far as it's written in the command: a heredoc, a here-string, and the
    words and text of the command piped into it."""
    texts = [value for kind, value in command.inputs if kind == "text"]
    if command.upstream is not None:
        texts += command.upstream.words + [value for kind, value in command.upstream.inputs if kind == "text"]
    return texts


def code_texts(command: Command) -> list:
    """The text this command hands a shell to run: a `sh -c` string, eval's words, a heredoc, here-string or piped
    text fed to a shell (or `source`) that reads stdin."""
    words, texts = command.words, []
    for j, word in enumerate(words):
        name = program(word)
        if name == "eval":
            texts.append(" ".join(words[j + 1:]))
        elif name in ("source", ".") and words[j + 1:j + 2] and words[j + 1] in STDIN:
            texts += stdin_texts(command)
        elif name in SHELLS:
            rest, k = words[j + 1:], 0
            while k < len(rest) and rest[k][:1] in ("-", "+"):
                if rest[k][:1] == "-" and not rest[k].startswith("--") and "c" in rest[k][1:]:
                    texts += rest[k + 1:k + 2]
                    break
                k += 2 if rest[k] in ("-o", "+o", "-O", "+O") else 1
            else:
                if k >= len(rest) or rest[k] in STDIN:  # the shell runs its stdin (a script file isn't read)
                    texts += stdin_texts(command)
    return texts


def all_commands(text: str, depth: int = 0) -> list:
    commands = parse(text, depth)
    for command in list(commands):
        for code in code_texts(command):
            commands += all_commands(code, depth + 1)
    return commands


# The rules.

class Context:
    def __init__(self, command: str, flat: str, cwd: str, commands: list):
        self.flat = flat  # the command's text, for counting the names of files
        self.decoded = ""  # its words with `$'...'` escapes read, for the text checks
        if "$'" in command:
            self.decoded = flatten(" ".join(word for c in commands for word in c.words + stdin_texts(c)))
        self.text = flat + "\n" + self.decoded
        self.cwd = cwd
        self.moves = any(program(first_word(c.words)) in MOVES for c in commands if first_word(c.words))


def first_word(words: list) -> str:
    return next((word for word in words if not ASSIGNMENT.match(word)), "")


def positionals(args: list, value_flags: set) -> list:
    """The indices of args that are operands, not options or an option's value."""
    found, i = [], 0
    while i < len(args):
        if args[i] == "--":
            return found + list(range(i + 1, len(args)))
        if args[i].startswith("-") and args[i] != "-":
            i += 2 if args[i] in value_flags else 1
        else:
            found.append(i)
            i += 1
    return found


def options(args: list, value_flags: set):
    """(flag, value) for each option in args: `--flag=value`, and `--flag value`, `-fvalue` or `-f value` for the flags
    in value_flags; (flag, None) for the rest."""
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--":
            return
        if arg.startswith("--") and "=" in arg:
            yield tuple(arg.split("=", 1))
        elif arg.startswith("-") and (arg.startswith("--") or len(arg) == 2):
            if arg in value_flags and i + 1 < len(args):
                yield arg, args[i + 1]
                i += 1
            else:
                yield arg, None
        elif arg.startswith("-") and len(arg) > 2 and arg[:2] in value_flags:
            yield arg[:2], arg[2:]
        i += 1


def read_file(path: str, ctx: Context) -> "str | None":
    """Why a file the call would send is refused: it can't be read, or it names a barred call."""
    if not path or MARK in path:
        return cant("a file whose name the shell fills in")
    path = os.path.expanduser(path)
    if not os.path.isabs(path) and ctx.moves:
        return cant(f"`{shown(path)}`, a relative path in a command that changes folder (give it by absolute path)")
    base = os.path.basename(path).lower()
    if len(re.findall(rf"(?<![\w.-]){re.escape(base)}(?![\w.-])", ctx.flat)) > 1:
        return cant(f"`{shown(path)}`, a file the command names again (it may write it first)")
    full = os.path.join(ctx.cwd, path)
    try:
        info = os.stat(full)
    except OSError:
        return cant(f"`{shown(path)}`, which doesn't exist yet")
    if not stat.S_ISREG(info.st_mode):
        return cant(f"`{shown(path)}`, which isn't a regular file (a pipe or a device)")
    if info.st_size > MAX_FILE:
        return cant(f"`{shown(path)}`, a file over 5 MB")
    with open(full, "rb") as handle:
        content = flatten(handle.read(MAX_FILE).decode("utf-8", "replace"))
    if MUTATIONS.search(content) or RUN_ENDPOINT.search(content):
        return refused(f"`{shown(path)}` names dequeuePullRequest or disablePullRequestAutoMerge, or a run's cancel "
                       "path")
    return None


def file_reason(path: str, command: Command, ctx: Context) -> "str | None":
    return stdin_reason(command, ctx) if path in STDIN else read_file(path, ctx)


def stdin_reason(command: Command, ctx: Context) -> "str | None":
    """Why the call's stdin is refused: a pipe, a file descriptor, text the shell fills in, or stdin the call doesn't
    carry itself (a group's or subshell's redirect, `exec <`, a pipe into a shell or a group). A file is read; a
    heredoc or here-string written in the command was read in its text."""
    if command.upstream is not None:
        return cant("stdin from a pipe")
    if not command.inputs:
        return cant("stdin the call doesn't carry itself (a group's or subshell's redirect, `exec <`, a pipe into a "
                    "shell or a group): give the call its own heredoc, here-string or `< <file>`, or for httpie "
                    "`--ignore-stdin`")
    for kind, value in command.inputs:
        if kind == "file":
            reason = read_file(value, ctx)
            if reason:
                return reason
        elif kind == "fd":
            return cant("stdin from a file descriptor")
        elif MARK in value:
            return cant("a heredoc or here-string the shell fills in")
    return None


CLOSE_BAR = ("closing a PR to take it out of the queue is the same action; a close for the PR's own reasons isn't "
             "barred")


def mutation_reason(ctx: Context, writes: list) -> "str | None":
    """A call naming a barred mutation; or one that closes a PR (closePullRequest, updatePullRequest in a command that
    names closed, or a REST write whose fields set the state to closed) in a command that names a queue."""
    if MUTATIONS.search(ctx.text):
        return refused("the call names dequeuePullRequest or disablePullRequestAutoMerge, which take a PR out of the "
                       "merge queue")
    closes = (CLOSES.search(ctx.text) or (UPDATES.search(ctx.text) and CLOSED_WORD.search(ctx.text))
              or any(CLOSED_STATE.search(flatten(write)) for write in writes))
    if closes and "queue" in ctx.text:
        return refused(f"the call closes a PR, and the command names a queue: {CLOSE_BAR}")
    return None


def gh_reason(args: list, command: Command, ctx: Context) -> "str | None":
    found = positionals(args, REPO_FLAGS)
    group, sub = ([args[k] for k in found[:2]] + ["", ""])[:2]
    if group == "run" and sub == "cancel":
        return refused("`gh run cancel` cancels a workflow run")
    if group == "run" and MARK in sub:
        return cant(f"`gh run {shown(sub)}`, whose subcommand the shell fills in")
    if group == "pr" and sub == "merge" and any(a == "--disable-auto" or a.startswith("--disable-auto=") for a in args):
        return refused("`gh pr merge --disable-auto` takes a queued PR out of the merge queue")
    if group == "pr" and sub == "close" and "queue" in ctx.text:
        return refused(f"`gh pr close` here says it's to leave the queue: {CLOSE_BAR}")
    if group == "api":
        return api_reason(args[found[0] + 1:], command, ctx)
    return None


def api_reason(args: list, command: Command, ctx: Context) -> "str | None":
    found = positionals(args, API_VALUE_FLAGS)
    endpoint = args[found[0]] if found else ""
    if RUN_ENDPOINT.search(flatten(endpoint)):
        return refused(f"`gh api {shown(endpoint)}` cancels a workflow run")
    pairs = list(options(args, API_VALUE_FLAGS))
    fields = [value or "" for flag, value in pairs if flag in API_FIELDS]
    bodies = [value or "" for flag, value in pairs if flag == "--input"]
    method = next((value or "" for flag, value in reversed(pairs) if flag in ("-X", "--method")), "")
    method = (method or ("POST" if fields or bodies else "GET")).upper()  # gh api posts when given fields
    hidden = endpoint.startswith(MARK) or (MARK in endpoint and "actions/" in endpoint)
    if hidden and method != "GET":
        return cant(f"the API path `{shown(endpoint)}`, which the shell fills in, with a POST")
    graphql = re.split(r"[?#]", endpoint.lower())[0].rstrip("/").endswith("graphql")
    reason = mutation_reason(ctx, fields if method != "GET" and not graphql else [])
    if reason or not (hidden or graphql):
        return reason
    for field in fields:
        key, _, value = field.partition("=")
        if value.startswith("@"):
            reason = file_reason(value[1:], command, ctx)
        elif MARK in key or (key.lower() == "query" and MARK in value):
            reason = cant("a query the shell fills in (a variable, `$(...)` or backtick)")
        if reason:
            return reason
    for body in bodies:
        reason = file_reason(body, command, ctx)
        if reason:
            return reason
    return None


def client_reason(name: str, args: list, command: Command, ctx: Context) -> "str | None":
    """curl, wget, httpie or xh, in a command that names github or graphql, or a run's cancel path."""
    if RUN_ENDPOINT.search(ctx.text):
        return refused(f"`{name}` on a path that cancels a workflow run")
    files, data, writes = [], [], []
    if name == "curl":
        for flag, value in options(args, CURL_VALUE_FLAGS):
            value = value or ""
            if flag in CURL_DATA:
                data.append(value)
                key, eq, rest = value.partition("=")
                if value.startswith("@"):
                    files.append(value[1:])
                elif flag in ("-F", "--form") and eq and rest[:1] in ("@", "<"):
                    files.append(rest[1:].split(";")[0])
                elif flag == "--data-urlencode" and "@" in value and "=" not in value.split("@")[0]:
                    files.append(value.split("@", 1)[1])
            elif flag in CURL_FILES:
                files.append("-" if value == "." else value)
    elif name == "wget":
        for flag, value in options(args, WGET_VALUE_FLAGS):
            if flag in WGET_DATA:
                data.append(value or "")
            elif flag in WGET_FILES:
                files.append(value or "")
    else:  # httpie and xh: `@file` is the body, `key=@file` and `key:=@file` a field from a file
        for flag, value in options(args, HTTPIE_VALUE_FLAGS):
            if flag == "--raw":
                data.append(value or "")
        for k in positionals(args, HTTPIE_VALUE_FLAGS):
            item = args[k]
            first = min((item.find(c) for c in ":=@" if c in item), default=-1)
            if item.startswith("@"):
                files.append(item[1:])
            elif first >= 0 and item[first] == "@":
                files.append(item[first + 1:].split(";")[0])
            elif first >= 0 and (item[first] == "=" or item.startswith(":=", first)):
                value = item[first + (2 if item.startswith(":=", first) else 1):]
                if value.startswith("@"):
                    files.append(value[1:])
                else:
                    data.append(value)
                    writes.append(item)
    reason = mutation_reason(ctx, [] if "graphql" in ctx.text else writes + data)
    if reason:
        return reason
    if any(MARK in value for value in data):
        return cant(f"`{name}`'s data, which the shell fills in (a variable, `$(...)` or backtick)")
    for path in files:
        reason = file_reason(path, command, ctx)
        if reason:
            return reason
    if name not in ("curl", "wget") and "graphql" in ctx.text and "--ignore-stdin" not in args and "-I" not in args:
        return stdin_reason(command, ctx)  # httpie and xh send their stdin as the body
    return None


TEXT_CHECK = ("; this is the check that reads python's and node's code, so it counts quoted text too: if this is "
              "only text, write it with Edit or Write")


def text_reason(text: str) -> "str | None":
    """The whole-text checks, whatever runs the command."""
    if CALL.search(text):
        return refused("the command's text calls dequeuePullRequest or disablePullRequestAutoMerge, which take a PR "
                       "out of the merge queue" + TEXT_CHECK)
    if RUN_PATH.search(text):
        return refused("the command's text holds an API path that cancels a workflow run" + TEXT_CHECK)
    if LIST_FORM.search(text):
        return refused("the command's text runs `gh run cancel` as a list of words" + TEXT_CHECK)
    return None


def command_reason(command: str, flat: str, cwd: str) -> "str | None":
    reason = text_reason(flat) or (LIST_FORM.search(command) and text_reason(command))
    if reason:
        return reason
    commands = all_commands(command)
    ctx = Context(command, flat, cwd, commands)
    reason = ctx.decoded and text_reason(ctx.decoded)
    if reason:
        return reason
    for simple in commands:
        for j, word in enumerate(simple.words):
            name, reason = program(word), None
            if name == "gh" or MARK in word:
                reason = gh_reason(simple.words[j + 1:], simple, ctx)
            elif name in HTTP_CLIENTS and (GITHUB.search(ctx.text) or RUN_ENDPOINT.search(ctx.text)):
                reason = client_reason(name, simple.words[j + 1:], simple, ctx)
            if reason:
                return reason
    return None


def queue_reason(command: str, cwd: str) -> "str | None":
    """Why this Bash command may not run, or None. It reads the command only when its text holds a HINT (gh, github,
    graphql, `actions/`, `run cancel` and the rest) or `$'`; a failure in that reading refuses it (fail closed)."""
    flat = flatten(command)
    if not HINT.search(flat) and "$'" not in command:  # `$'\x67h'` is gh once its escapes are read
        return None
    try:
        return command_reason(command, flat, cwd)
    except Exception as error:  # noqa: BLE001 - a command this hook can't read may be one it bars
        return cant(f"this command ({type(error).__name__})")
