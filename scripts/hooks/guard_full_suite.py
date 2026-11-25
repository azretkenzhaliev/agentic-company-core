#!/usr/bin/env python3
"""PreToolUse hook for Bash, opt-in: on this machine no full suite of one product starts, and a heavy run of named files
needs a slot and charge, on a tree that hasn't passed in full.

For a product whose full suite takes the machine for a long time, and whose tests run with `bun test` in Docker database
containers. It's off until company.json names the product ("integrations", "full_suite", below), since "only affected
tests run on this machine" is the founder's choice; a company.json it can't read refuses every command that names `bun`
and `test`. The load limit is the product's runbook's (knowledge/engineering/runbooks/<product>.md, "Machine load: a heavy
run takes a slot"): agents take and release a slot with its `mkdir` call, and this only checks. It writes nothing but its
error log. It doesn't judge whether a heavy run has a good reason: that's the runbook's and the reviewer's.

A run of the product's is `bun test` or `bun run test` with the command naming the database variable, running under the
product's folder or going through `sh scripts/test-db.sh run <container> <port> -- <command>`, which exports that URL;
also inside the string of `sh -c`, `bash -c` or `zsh -c`, or as the <command> of `test-db.sh run`. One that reaches up to
HEAVY_FILES test files gets no decision, at once: the essential tier plus the files a change touches is never refused or
delayed.

A clear full suite is refused, and that's final: more than HEAVY_FILES test files reached through no file at all (bare, a
shard, `--cwd`), through a folder or a glob (`*`, `?`, or a `[` that matches a path but names none), or a run whose files
a `$(...)` or a backtick hides, in its words or in a variable the command sets; a variable the command sets to plain words
is read in its place and split into them, while a literal path stays whole. No run is exempt, not even a production
deploy's. So is a run whose count is still walking after WALK_SECONDS (a command's counts together), or finds them spent.

More than HEAVY_FILES named files (the runbook's "heavy") are blocked (exit 2, one line on stderr saying why and what
to do) if:
- the same tree already passed in full: a green run of the CI workflow on a commit with this tree in which every
  `full-suite tests K/N` leg is `success`. Only a clean checkout under the product's folder is checked, since a copy or a
  dirty tree isn't that tree. A green run isn't enough: a pull request's run may hold only the affected tests;
- or this machine is a Mac on battery under BATTERY_FLOOR% (`pmset -g batt`): a battery death stops every agent;
- or no slot's `owner` names the container on the URL's port (or the command names no port, so no slot can be
  checked), or the <container> of `test-db.sh run`: `run` starts it itself, so it's usually stopped when this reads
  the command and no port would find it. Each such <container> in a command needs a slot that names it. So at most
  len(SLOTS) containers run at once, unless one owner line names two, and there's no timer: a wait never turns into
  "run anyway". `slot-L` counts while `.landing-lock` exists, so a production deploy never queues behind a review
  or a Senior (outside the lock that rests on the runbook's table alone, which keeps slot-L for a landing: this
  can't tell one); and otherwise, for a landing, while this machine's 5-minute load, which this reads itself
  (`os.getloadavg`), is below LOAD_LIMIT. At or above it, a run whose container only slot-L names waits for the load.

The full-suite line is final, and the passed-tree line final for that tree; the slot lines are a wait for a slot, and
the battery line a wait for the charger.

It can't block all engineering. Once its settings are read, an error lets the run go and adds a line to
<product's folder>/.suite-guard-errors.log: the CI check failing skips only that check, the battery check failing skips
only that check, and the container lookup failing skips only the slot check. A load it can't read counts `slot-L` only
under `.landing-lock`. The CTO's off switch, for a fault in this hook alone, is one line, `touch <product's
folder>/.suite-guard-off`; removing the file turns the guard back on.

"Same tree" is approximate for a pull request's run. Its legs test refs/pull/N/merge, the head merged with its base,
and this compares HEAD with headSha^{tree}, so on a branch behind its base the code that passed isn't literally this
checkout. Only a local run is affected: no merge or deploy gate reads this hook.

Heredocs: without_heredocs drops each body, and the command is read again with the rest of each heredoc's first line kept
(`cat <<'EOF' > x; bun test`). Where its reading may differ from the shell's (cq_write.heredoc_doubt), a command that may
start a run (it names `bun` and `test`, and the URL, test-db.sh or the product's folder, or runs under it) is refused,
after the full-suite line; the message says how to write the heredoc.

Settings, company.json:
  "products": {"acme": {"repo": "example-co/acme-app", "workspace": "workspaces/acme/acme-app"}},
  "integrations": {"full_suite": {"product": "acme", "database_env": "ACME_TEST_DATABASE_URL",
                                  "database_name": "acme_test", "container_prefix": "acme-pg", "workflow": "ci"}}
The product's folder is the one its workspace is in (workspaces/acme); slots, the lock, the log and the off switch are
there. It stops mistakes; it isn't a sandbox.
"""

import bisect
import glob
import itertools
import json
import os
import re
import shlex
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path(__file__).resolve().parents[2])
OFF_SWITCH = ".suite-guard-off"
ERROR_LOG = ".suite-guard-errors.log"
SLOT_FOLDER = ".suite-slots"
LANDING_LOCK = ".landing-lock"
LANDING_SLOT = "slot-L"
SLOTS = (LANDING_SLOT, "slot-1", "slot-2")  # the runbook's limit
HEAVY_FILES = 30  # the runbook's "about 30 test files"
# A command's test-file counts together; with the calls' worst sum (below) and 0.5 s for the hook's start, still under
# its timeout of 40 s.
WALK_SECONDS = 0.4
TEST_DB_SCRIPT = "test-db.sh"
GREEN_RUNS = 100  # how far back the CI check looks; an older pass only means one more run, in a slot
PROOFS = 2  # same-tree runs whose jobs it reads; each is a call, and the hook's timeout bounds them
BATTERY_FLOOR = 25  # percent
ON_MACOS = sys.platform == "darwin"  # pmset is macOS's; elsewhere the battery isn't checked
# The 5-minute load at which slot-L stops counting outside .landing-lock: capacity_scan.py's limit, 2.5 a CPU.
LOAD_LIMIT = 2.5 * (os.cpu_count() or 1)
GIT_SECONDS, GH_SECONDS, DOCKER_SECONDS, PMSET_SECONDS = 3, 8, 5, 1  # their worst sum stays under the hook's timeout of 40 s
CI_SECONDS = 3 * GIT_SECONDS + (1 + PROOFS) * GH_SECONDS  # one checkout's CI check at worst: every checkout's, together

FULL_LEG = re.compile(r"full-suite tests (\d+)/(\d+)")  # the jobs that prove a full run
MAYBE_SUITE = re.compile(r"\bbun\b.*\btest\b", re.S)
TEST_FILE = re.compile(r"[._](test|spec)\.[cm]?[jt]sx?$")
CHARGE = re.compile(r"(\d+)%")
NOT_TESTS = {"node_modules", "dist"}
HEREDOC_SPACE, HEREDOC_NAME = re.compile(r"\s*"), re.compile(r"\w+")  # without_heredocs
# Quoted text is matched only to step over it: a `#` in quotes is no comment, and a `;` or an apostrophe in a comment
# is no command or quote.
COMMENT_OR_QUOTED = re.compile(r"""'[^']*'|"(?:\\.|[^"\\])*"|\\.|(?:^|(?<=[\s;&|()]))#[^\n]*""", re.M | re.S)
ASSIGNMENT = re.compile(r"[A-Za-z_]\w*=.*", re.S)
# A substitution: shlex leaves a word ending in `$` before an unquoted `$(`, and keeps a quoted one or a backtick whole.
HIDDEN = re.compile(r"\$\(|`|\$$")
VARIABLE = re.compile(r"\$(?:\{([A-Za-z_]\w*)\}|([A-Za-z_]\w*))")
BRACES = re.compile(r"\{([^{}]*,[^{}]*)\}")
SHELL_MARKS = set("();<>|&")
REDIRECTION = re.compile(r"&?[<>]+[&|]?")
SHELLS = {"sh", "bash", "zsh"}
SHELL_STRING_FLAG = re.compile(r"-[a-z]*c[a-z]*")  # -c, and -lc or -ec
NOT_THIS_MACHINES_SHELL = {"echo", "printf", "docker"}  # they print the words, or run them in CI's image
BEFORE_A_COMMAND = {"if", "elif", "while", "until", "do", "then", "else", "{", "!", "time", "nohup", "command", "exec"}
VALUE_FLAGS = {"--shard", "--timeout", "--rerun-each", "--retry", "--preload", "-r", "--reporter", "--reporter-outfile",
               "--coverage-reporter", "--coverage-dir", "--max-concurrency", "--seed", "--cwd", "--config", "-c",
               "--tsconfig-override", "--path-ignore-patterns"}
NOT_THE_SUITE = {"--help", "-h", "--version", "-t", "--test-name-pattern", "--changed"}  # --changed is bun's affected run


# The product's, from company.json: configure() sets them.
FOLDER = MAIN_CLONE = REPO = DATABASE_NAME = TEST_DB_CONTAINER = WORKFLOW = RUNBOOK = PORT = None


def configure(root: Path) -> bool:
    """Read the product's names from company.json at root; False when no product is set up. A file it can't read, or a
    missing or wrong value, raises: the caller refuses. The workspaces are in the main checkout, not in its worktrees."""
    global FOLDER, MAIN_CLONE, REPO, DATABASE_NAME, TEST_DB_CONTAINER, WORKFLOW, RUNBOOK, PORT
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import company_config

    settings = company_config.integration("full_suite", root)
    if settings is None:
        return False
    product = company_config.load(root)["products"][settings["product"]]
    workspace = Path(str(root).split("/.claude/worktrees/")[0]) / product["workspace"]
    texts = [settings[name] for name in ("database_env", "database_name", "container_prefix", "workflow")]
    if not all(isinstance(text, str) and text for text in [product["workspace"], product["repo"], *texts]):
        raise ValueError("integrations.full_suite and its product need text in every field")
    FOLDER, MAIN_CLONE, REPO = workspace.parent, workspace.name, product["repo"]
    DATABASE_NAME, database, TEST_DB_CONTAINER, WORKFLOW = texts
    RUNBOOK = f"{settings['product']}.md"
    PORT = re.compile(rf"(?:127\.0\.0\.1|localhost):(\d+)/{re.escape(database)}")
    return True


def run(args: list, seconds: int, stdin: "str | None" = None) -> str:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}  # no GIT_DIR pointing elsewhere
    return subprocess.run(args, capture_output=True, text=True, timeout=seconds, check=True, input=stdin,
                          env=env).stdout


def log_error(root: Path, what: str) -> None:
    try:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        with (root / ERROR_LOG).open("a", encoding="utf-8") as log:
            log.write(f"{now} {what}\n")
    except OSError:
        pass


def without_heredocs(text: str, keep_rest: bool = False) -> str:
    """The text without its heredocs, each from its `<<` to the end of its end line (keep_rest: but for the rest of its
    first line, where the shell runs what follows, `cat <<'EOF' > x; bun test`). It reads them as the regex
    `<<-?\\s*(['"]?)(\\w+)\\1[^\\n]*\\n(?:.*?\\n)?[ \\t]*\\2[ \\t]*(?=\\n|$)` (re.S) did with re.sub, quirks included
    (test_guard_full_suite.py checks it against that regex), in near-linear time: the regex scanned to the end for each
    `<<name` with no end line, once per prefix of the name, so a crafted command could outlast the hook's timeout. So: the end line is the first line after the body's first
    line that is the name (spaces and tabs around it), else that first line itself; an unquoted name with no end
    line tries its prefixes, longest first; a `<<` with none is left as it is."""
    ends, offset = {}, 0  # each line, stripped of spaces and tabs: the offsets where it starts, in order
    for line in text.split("\n"):
        ends.setdefault(line.strip(" \t"), []).append(offset)
        offset += len(line) + 1
    sizes = sorted({len(line) for line in ends if line})
    out, kept, start = [], 0, text.find("<<")
    while start >= 0:
        span = _heredoc_span(text, start, ends, sizes)
        if span is None:
            start = text.find("<<", start + 1)
            continue
        rest, newline, end = span
        out += [text[kept:start], " " + text[rest:newline] if keep_rest else ""]
        kept, start = end, text.find("<<", end)
    return "".join(out) + text[kept:]


def _heredoc_end(text: str, start: int, ends: dict, sizes: list) -> "int | None":
    """Where the heredoc whose `<<` is at start ends (its end line's end), or None if the regex matched none there."""
    span = _heredoc_span(text, start, ends, sizes)
    return span[2] if span else None


def _heredoc_span(text: str, start: int, ends: dict, sizes: list) -> "tuple | None":
    """For the heredoc whose `<<` is at start: where the rest of its first line starts, that line's newline, and where
    its end line ends; or None if the regex matched none there."""
    i = HEREDOC_SPACE.match(text, start + 2 + text.startswith("-", start + 2)).end()
    quote = text[i] if text.startswith(("'", '"'), i) else ""
    name = HEREDOC_NAME.match(text, i + len(quote))
    if not name or (quote and not text.startswith(quote, name.end())):
        return None
    newline = text.find("\n", name.end())
    if newline < 0:
        return None
    first = newline + 1
    longest = name.end() - name.start()
    for size in [longest] if quote else reversed(sizes[:bisect.bisect_right(sizes, longest)]):
        starts = ends.get(text[name.start():name.start() + size])
        if not starts:
            continue
        later = bisect.bisect_right(starts, first)
        if later < len(starts):
            last = starts[later]
        elif starts[-1] == first:
            last = first
        else:
            continue
        stop = text.find("\n", last)
        return name.start() + size + len(quote), newline, len(text) if stop < 0 else stop
    return None


def simple_commands(command: str, keep_rest: bool = False) -> list:
    """The words of each simple command, without comments, heredoc bodies or redirections (keep_rest:
    without_heredocs)."""
    text = COMMENT_OR_QUOTED.sub(lambda found: "" if found[0].startswith("#") else found[0],
                                 without_heredocs(command, keep_rest))
    text = text.replace("\\\n", " ").replace("\n", " ; ")
    lexer = shlex.shlex(text, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    lexer.commenters = ""  # they're gone already; shlex would also take the `#` of `x#y` for one
    commands, current, skip_next = [], [], False
    for word in lexer:
        if skip_next:
            skip_next = False
        elif set(word) <= SHELL_MARKS:
            skip_next = "<" in word or ">" in word  # the redirection's target
            if skip_next and current and current[-1].isdigit():
                current.pop()  # the 2 of 2>&1 isn't an argument
            if not REDIRECTION.fullmatch(word):  # paths can follow a redirection
                commands.append(current)
                current = []
        else:
            current.append(word)
    commands.append(current)
    return [words for words in commands if words]


def without_prefixes(words: list) -> list:
    """These words from the command they run on, past assignments, `env`, `timeout` and the like."""
    i = 0
    while i < len(words):
        if ASSIGNMENT.fullmatch(words[i]) or words[i] in BEFORE_A_COMMAND:
            i += 1
        elif words[i] == "env":
            i += 1
            while i < len(words) and words[i].startswith("-"):
                i += 2 if words[i] in ("-u", "--unset") else 1
        elif words[i] == "timeout":
            i += 2
        else:
            break
    return words[i:]


def test_db_run(words: list) -> "tuple | None":
    """The <container> and the <command>'s words of `sh scripts/test-db.sh run <container> <port> -- <command>`."""
    rest = without_prefixes(words)
    if rest and os.path.basename(rest[0]) in SHELLS:
        rest = rest[1:]
        while rest and rest[0].startswith("-") and not SHELL_STRING_FLAG.fullmatch(rest[0]):  # sh -x, bash -eu
            rest = rest[1:]
    if len(rest) > 5 and os.path.basename(rest[0]) == TEST_DB_SCRIPT and rest[1] == "run" and rest[4] == "--":
        return rest[2], rest[5:]
    return None


def commands_in(command: str, container: "str | None" = None, keep_rest: bool = False):
    """Each simple command, with the string of an `sh -c`, `bash -c` or `zsh -c` and the <command> of a `test-db.sh
    run` read as commands in their place, and the <container> of the `test-db.sh run` it's in, if any."""
    for words in simple_commands(command, keep_rest):
        through = test_db_run(words)
        strings = [words[i + 2] for i in range(len(words) - 2)
                   if os.path.basename(words[i]) in SHELLS and SHELL_STRING_FLAG.fullmatch(words[i + 1])]
        if through:
            yield from commands_in(shlex.join(through[1]), through[0], keep_rest)
        elif strings and words[0] not in NOT_THIS_MACHINES_SHELL:
            try:
                yield from commands_in(strings[0], container, keep_rest)
            except ValueError:  # a string it can't read mustn't undo a heavy run found before it
                yield words, container
        else:
            yield words, container


def suite_args(words: list) -> "list | None":
    """The arguments of the `bun test` or `bun run test` these words run, or None if they run something else."""
    rest = without_prefixes(words)
    if rest[:2] == ["bun", "test"]:
        return rest[2:]
    return rest[3:] if rest[:3] == ["bun", "run", "test"] else None


def expand(arg: str) -> list:
    """What the shell's brace expansion makes of a path."""
    match = BRACES.search(arg)
    if not match:
        return [arg]
    return [path for option in match[1].split(",") for path in expand(arg[:match.start()] + option + arg[match.end():])]


def named_paths(args: list) -> "list | None":
    """The paths a run names, [] for none, or None if it doesn't run the tests it reaches (help, a name filter)."""
    paths, skip_next = [], False
    for arg in args:
        if skip_next:
            skip_next = False
        elif arg in NOT_THE_SUITE or arg.startswith(("-t=", "--test-name-pattern=", "--changed=")):
            return None
        elif arg in VALUE_FLAGS:
            skip_next = True
        elif not arg.startswith("-"):
            paths.extend(expand(arg))
    return paths


def is_glob(base: str, path: str) -> bool:
    """Whether the shell expands this path: a `*` or `?`, or a `[` that matches a path but names none (Next.js's `[id]`
    folders are names; a `[` that matches nothing reaches no file, as a name)."""
    full = os.path.join(base, path)
    return "*" in path or "?" in path or ("[" in path and not os.path.exists(full) and bool(glob.glob(full)))


def test_files(base: str, paths: list) -> int:
    """How many test files these paths reach, each once, from base; a variable or a word that's no path counts none."""
    tests = set()
    for path in paths or ["."]:
        full = os.path.join(base, path)
        globbed = is_glob(base, path)
        for found in sorted(glob.glob(full, recursive=True)) if globbed else [full]:
            if globbed and not NOT_TESTS.isdisjoint(os.path.relpath(found, base).split(os.sep)):
                continue  # a ** reaches where a folder's walk doesn't
            if os.path.isfile(found) and (not globbed or TEST_FILE.search(found)):
                tests.add(os.path.normpath(found))
            for folder, subfolders, files in os.walk(found):
                subfolders[:] = [name for name in subfolders if name not in NOT_TESTS and not name.startswith(".")]
                tests.update(os.path.normpath(os.path.join(folder, name)) for name in files if TEST_FILE.search(name))
    return len(tests)


def heavy(base: str, paths: list, budget: list) -> "bool | None":
    """Whether these paths reach more than HEAVY_FILES test files from base, or None if they weren't counted. budget
    holds the seconds the command's counts have left, and this lowers it (WALK_SECONDS); a count still walking when they
    run out, one that finds none left and one no thread starts for aren't counted, and the run is a clear full suite. The
    count runs in a thread this waits for, so no timer goes off around it; a thread left walking ends with the hook."""
    if budget[0] <= 0:
        return None
    found = []

    def count():
        try:
            found.append(test_files(base, paths))
        except Exception as error:  # raised below (an error lets the run go)
            found.append(error)

    start = time.monotonic()
    walker = threading.Thread(target=count, daemon=True)
    try:
        walker.start()
    except Exception:  # no thread to be had, or no memory: not counted, rather than counted with no cap or let go
        return None
    walker.join(budget[0])
    budget[0] -= time.monotonic() - start
    if walker.is_alive() or not found:
        return None
    if isinstance(found[0], Exception):
        raise found[0]
    return found[0] > HEAVY_FILES


def under(path: str, root: Path) -> bool:
    return os.path.realpath(path).startswith(os.path.realpath(root) + os.sep)


def moved_to(folder: str, target: str) -> str:
    """Where a `cd` or `--cwd` to target leads from folder, or "" if a variable hides it."""
    if not target or "$" in target or not (folder or os.path.isabs(target)):
        return ""
    return os.path.normpath(os.path.join(folder, target))


def cwd_value(args: list) -> str:
    for i, arg in enumerate(args):
        if arg.startswith("--cwd="):
            return arg[len("--cwd="):]
        if arg == "--cwd":
            return "".join(args[i + 1:i + 2])
    return ""


def filled(text: str, values: dict) -> "str | None":
    """text with each variable the command set put in its place, or None if a substitution hides any of it."""
    names = [braced or bare for braced, bare in VARIABLE.findall(text)]
    if HIDDEN.search(text) or any(values.get(name, "") is None for name in names):
        return None
    return VARIABLE.sub(lambda found: values.get(found[1] or found[2], found[0]), text)


def full_suites(command: str, cwd: str, root: Path) -> list:
    """Each heavy run of the product's this command starts: where ("" if a variable hides it), the `test-db.sh run` container
    it runs in (None outside one), and whether it's a clear full suite rather than more than HEAVY_FILES named files.
    A command with a heredoc is read twice: without its lines, and with the rest of each heredoc's first line kept,
    where the shell runs what follows (`cat <<'EOF' > x; bun test`). Their counts walk WALK_SECONDS in all, and a run they
    don't count is clear (heavy)."""
    if not MAYBE_SUITE.search(command):
        return []
    budget = [WALK_SECONDS]
    found = _full_suites(command, cwd, root, False, budget)
    if "<<" in command:
        try:
            found += [suite for suite in _full_suites(command, cwd, root, True, budget) if suite not in found]
        except ValueError:  # a first line that leaves a quote open: unreadable() refuses it
            pass
    return found


def unreadable(command: str, cwd: str, root: Path) -> "str | None":
    """Why the heredocs of a command that may start a run may hide it from without_heredocs, or None: cq_write's
    heredoc_doubt, asked of this hook's reading. A command may start one if it names `bun` and `test`, and the URL,
    test-db.sh or the product's folder, or runs under it. An error lets the run go."""
    if "<" not in command or not MAYBE_SUITE.search(command):
        return None
    if not (DATABASE_NAME in command or TEST_DB_SCRIPT in command or root.name in command or (cwd and under(cwd, root))):
        return None
    try:
        from cq_write import heredoc_doubt  # here, so a command with no heredoc doesn't load it
        return heredoc_doubt(command, _heredoc_end, HEREDOC_NAME)
    except Exception as error:  # as any error here: the run goes
        log_error(root, f"heredoc check skipped: {error!r}")
        return None


def _full_suites(command: str, cwd: str, root: Path, keep_rest: bool, budget: list) -> list:
    found, folder, values = [], cwd, {}
    for words, container in commands_in(command, keep_rest=keep_rest):
        if words[0] == "cd":
            folder = moved_to(folder, words[1] if len(words) > 1 else "")
            continue
        setting = words[1:] if words[0] in ("export", "local", "readonly") else words
        assigned = list(itertools.takewhile(ASSIGNMENT.fullmatch, setting))
        for word in assigned:
            name, _, text = word.partition("=")
            value = filled(text, values)  # None: a substitution hides what it holds (SEL=`...` is split, so in a prefix)
            if value is None or len(assigned) == len(setting):  # a prefix's plain value is only its command's
                values[name] = value
        if assigned and len(assigned) == len(setting):
            continue
        args = suite_args(words)
        paths = None if args is None else named_paths(args)
        if paths is None:
            continue
        cwd_flag = cwd_value(args)
        here = moved_to(folder, cwd_flag) if cwd_flag else folder
        through = (container or "").startswith(TEST_DB_CONTAINER)
        if not (through or DATABASE_NAME in command or (here and under(here, root))):
            continue
        texts = [filled(path, values) for path in paths]
        if None in texts:
            found.append((here, container, True))  # files it can't count, so the run counts as all of them
            continue
        paths = [word for path, text in zip(paths, texts) for word in (text.split() if text != path else [path])]
        start = folder if folder and os.path.isdir(folder) else str(root / MAIN_CLONE)
        base = moved_to(start, cwd_flag) or start
        counted = heavy(base, paths, budget)
        if counted is None:  # not counted in the seconds: clear, and no is_glob or isdir walks after it
            found.append((here, container, True))
        elif counted:
            named = paths and not any(is_glob(base, path) or os.path.isdir(os.path.join(base, path)) for path in paths)
            found.append((here, container, not named))
    return found


def every_leg_passed(jobs: list) -> bool:
    legs = {}
    for job in jobs:
        match = FULL_LEG.fullmatch(job.get("name") or "")
        if match:
            legs[int(match[1])] = (int(match[2]), job.get("conclusion"))
    return bool(legs) and set(legs) == set(range(1, len(legs) + 1)) and all(
        total == len(legs) and conclusion == "success" for total, conclusion in legs.values())


def passed_run(folder: str, deadline: "float | None" = None) -> "dict | None":
    """The green CI run that ran the full suite on this checkout's exact tree, if there's one. With a deadline (a
    time.monotonic() value), no call runs past it: TimeoutError instead."""
    def call(args: list, seconds: int, stdin: "str | None" = None) -> str:
        if deadline is not None:
            seconds = min(seconds, deadline - time.monotonic())
            if seconds <= 0:
                raise TimeoutError("no time left for this checkout's CI check")
        return run(args, seconds, stdin)

    git = ["git", "--no-optional-locks", "-C", folder]
    if call([*git, "status", "--porcelain"], GIT_SECONDS).strip():
        return None
    tree = call([*git, "rev-parse", "HEAD^{tree}"], GIT_SECONDS).strip()
    runs = json.loads(call(["gh", "run", "list", "--repo", REPO, "--workflow", WORKFLOW, "--status", "success",
                            "--limit", str(GREEN_RUNS), "--json", "databaseId,headSha"], GH_SECONDS))
    lookups = "".join(f"{green['headSha']}^{{tree}}\n" for green in runs)
    trees = call([*git, "cat-file", "--batch-check"], GIT_SECONDS, lookups).splitlines()
    same_tree = [green for green, line in zip(runs, trees) if line.split()[0] == tree]
    for green in same_tree[:PROOFS]:
        view = call(["gh", "run", "view", str(green["databaseId"]), "--repo", REPO, "--json", "jobs"], GH_SECONDS)
        if every_leg_passed(json.loads(view)["jobs"]):
            return green
    return None


def battery_charge() -> "int | None":
    """The charge while this Mac runs on its battery, or None on the charger (and on any other system)."""
    if not ON_MACOS:
        return None
    output = run(["pmset", "-g", "batt"], PMSET_SECONDS)
    return int(CHARGE.search(output)[1]) if "'Battery Power'" in output else None


def container_on(port: str) -> "str | None":
    for line in run(["docker", "ps", "--format", "{{.Names}}|{{.Ports}}"], DOCKER_SECONDS).splitlines():
        name, _, ports = line.partition("|")
        if f":{port}->" in ports:
            return name
    return None


def owner_names(slot: str, container: str, root: Path) -> bool:
    owner = root / SLOT_FOLDER / slot / "owner"
    named = re.compile(rf"(?<![\w-]){re.escape(container)}(?![\w-])")
    return owner.is_file() and bool(named.search(owner.read_text(encoding="utf-8", errors="replace")))


def holds_a_slot(container: str, root: Path, seen: "list | None" = None) -> bool:
    return any(owner_names(slot, container, root) and (slot != LANDING_SLOT or landing_slot_counts(root, seen))
               for slot in SLOTS)


def landing_slot_counts(root: Path, seen: "list | None" = None) -> bool:
    """slot-L counts under .landing-lock, and otherwise while the 5-minute load is below LOAD_LIMIT; a load
    this can't read counts it only under the lock. The load it reads (None if it can't) goes into seen, so a wait's line
    shows that reading, not a second one."""
    if (root / LANDING_LOCK).exists():
        return True
    try:
        load = five_minute_load()
    except OSError as error:
        log_error(root, f"load check skipped, slot-L only under {LANDING_LOCK}: {error!r}")
        load = None
    if seen is not None:
        seen.append(load)
    return load is not None and load < LOAD_LIMIT


def five_minute_load() -> float:
    return os.getloadavg()[1]


def refusal(event: dict, root: Path) -> "str | None":
    """Why this command can't start, in one line, or None if it can."""
    if event.get("tool_name") != "Bash":
        return None
    command, cwd = str((event.get("tool_input") or {}).get("command") or ""), str(event.get("cwd") or "")
    doubt = unreadable(command, cwd, root)
    try:
        suites = full_suites(command, cwd, root)
    except ValueError:  # a quote left open, maybe by a heredoc read otherwise than the shell reads it
        if not doubt:
            raise
        suites = []
    if not (suites or doubt) or (root / OFF_SWITCH).exists():
        return None
    if doubt and not any(clear for _, _, clear in suites):
        return (f"Not started: this command may start a `bun test` of {root.name}'s that the shell reads outside a heredoc, "
                f"where this hook can't read it ({doubt}). Write each heredoc as `<<'EOF'`, its lines, then `EOF` "
                "alone on its line, with no `<<` in quotes, a comment or a `<<<`, or run the tests in a call of "
                "their own.")
    if any(clear for _, _, clear in suites):  # before any call: this line needs none
        return (f"Not started: this is a full suite (no files, a shard, a folder or glob over {HEAVY_FILES} test "
                f"files, files too many to count in {WALK_SECONDS} s, or files a $(...) or backtick hides), and on this "
                "machine only affected tests run. That's final: no slot or other form of it runs. Run the runbook's "
                f"essential-tier command ({RUNBOOK}, \"Essential tier\") plus the files your change touches, each by "
                f"its path: list them first, then paste them; over {HEAVY_FILES} named files wait for a slot. A "
                "production deploy runs none either.")
    # Every heavy run's checkout, not only the first run's: the first gets one checkout's seconds, and the rest share
    # what's left of them, so the hook's timeout still holds.
    start, deadline = time.monotonic(), None
    for folder in dict.fromkeys(here for here, _, _ in suites if here and under(here, root)):
        try:
            green = passed_run(folder, deadline)
        except Exception as error:  # GitHub or git being down mustn't stop a run, or lift the limit below
            log_error(root, f"CI check skipped: {error!r}")
        else:
            if green:
                return (f"Not started: this tree already passed in full (CI run {green['databaseId']}, commit "
                        f"{green['headSha'][:8]}). That's final for this tree: cite that run, run only the files "
                        "your change touches (they need no slot), and release your slot if you took one.")
        deadline = start + CI_SECONDS
    try:
        charge = battery_charge()
    except Exception as error:  # a Mac that can't say mustn't stop a run, or lift the limit below
        log_error(root, f"battery check skipped: {error!r}")
    else:
        if charge is not None and charge < BATTERY_FLOOR:
            return (f"Not started: this Mac is on battery at {charge}%, under the {BATTERY_FLOOR}% a heavy run needs. "
                    "It's a wait for the charger, and there's no run-anyway; the files your change touches need no "
                    "charge and no slot: run those, say so in your report, and release your slot if you took one.")
    for container in dict.fromkeys(suite[1] for suite in suites):  # each once, so at most one docker call
        reason = no_slot(command, container, root)
        if reason:
            return reason
    return None


def no_slot(command: str, container: "str | None", root: Path) -> "str | None":
    """Why a heavy run in this container (None: on the URL's port) can't start for want of a slot, or None if it can."""
    port = PORT.search(command)
    if not (port or container):
        return (f"Not started: this heavy run names no test database, so its slot can't be checked. Put "
                f"{DATABASE_NAME}=<the runbook's URL> in the command, take a slot with the runbook's call "
                f"({RUNBOOK}, \"Machine load: a heavy run takes a slot\"), then run it. It's a wait "
                "for a slot, and there's no run-anyway.")
    if not container:
        try:
            container = container_on(port[1])
        except Exception as error:
            log_error(root, f"slot check skipped: {error!r}")
            return None
        if container is None:
            log_error(root, f"slot check skipped: no container on port {port[1]}")
            return None
    seen = []  # the load holds_a_slot read for slot-L, if it read one
    if holds_a_slot(container, root, seen):
        return None
    if owner_names(LANDING_SLOT, container, root):
        load = f"is {seen[0]:.2f}" if seen and seen[0] is not None else "can't be read"
        return (f"Not started: {LANDING_SLOT} names {container}, but outside {LANDING_LOCK} it counts only while this "
                f"machine's 5-minute load is below {LOAD_LIMIT:g}, and it {load}. It's a wait for the load, and there's no run-anyway: run this same command again once the load is below it; the "
                "files your change touches need no slot.")
    return (f"Not started: no slot names {container}, and a heavy run needs one. Take a slot with the runbook's "
            f"call ({RUNBOOK}, \"Machine load: a heavy run takes a slot\"), name this container in "
            "its owner line, then run this same command; slot-L counts under .landing-lock, or for a landing while "
            f"the 5-minute load is below {LOAD_LIMIT:g}. It's a wait for a slot, and there's no run-anyway; the files "
            "your change touches need no slot.")


def main() -> None:
    folder = None
    try:
        event = json.load(sys.stdin)
        reason = None
        if event.get("tool_name") == "Bash" and MAYBE_SUITE.search(str((event.get("tool_input") or {}).get("command"))):
            try:
                folder = FOLDER if configure(ROOT) else None
            except Exception as error:  # what it can't read may say that only affected tests run here
                reason = (f"Not started: company.json's products or integrations.full_suite couldn't be read "
                          f"({type(error).__name__}), so this test run wasn't checked. Report it: only the main session "
                          "repairs that file.")
            if folder:
                reason = refusal(event, folder)
    except Exception as error:  # a bug here must never stop engineering
        if folder:
            log_error(folder, f"guard error, run let go: {error!r}")
        return
    if reason:
        print(reason, file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
