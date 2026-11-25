"""The marketing agents' Bash allowlist, used by guard_marketing_tools.py.

A blocklist can't hold, so marketing agents' Bash runs only:
- reads: cat, head, tail, ls, wc, grep, sort, uniq, cut, diff, stat, file, echo,
  pwd, true, date, basename, dirname, sleep, jq; find without its write or exec
  actions; `sed -n` with a print-only script. Four readers can also write or run
  code, so they're limited: sort only with -n -r -u -f -b -h -V -k -t (no -o, no
  --compress-program), uniq with at most one file and -c -d -u -i, file without -C,
  date only with +FORMAT or -u;
- the tools: `node` on tools/marketing/{render/png,render/reel,video/subtitles,video/frames,video/cut,video/compile}.mjs,
  with --out/--dir only in media/, and swipe/ingest.mjs for the cmo, with them only in swipe/; `python3 tools/marketing/footage/fetch.py`
  for the cmo and the producer, the one command that may name a URL, as the value of its --url and only http(s)
  (it writes only into workspaces/marketing/sources/); `python3` on tools/marketing/content_lint.py,
  scripts/language_check.py and scripts/kb_lint.py (it only reads), and by role on voice/, gen/, spend.py,
  taste/build.py, taste/analyze.py, publish/post_hashes.py and publish/stage_item.py (never
  scripts/notion_approvals_sync.py: it is a hook, and stdin from an agent could forge the Board's decisions);
- file moves inside workspaces/marketing/media/: mkdir, mv, rm, and cp from
  workspaces/marketing/ or tools/marketing/templates/, each path checked where it leads: media/ may be a link
  out of the repo (a synced folder) and counts; inbox/ and swipe/, when they are links outside it, don't, so cp from
  them is refused. No cp flag but -R -P -p -n -f -v -X (the others
  follow links or make them), a source's glob checked by what it matches;
  a name that isn't ASCII counts as matched by every glob, so a non-ASCII link leading out of a folder makes
  every glob in that folder refused, even one that can't match it (fail-closed);
  for the cmo, also mkdir, mv and rm inside workspaces/marketing/swipe/ (ingest.mjs's frames and
  audio, and a reel the founder saves when a site refuses a download; the audio is deleted after
  transcription, the video kept);
- for the cmo, `pdftotext [-layout] <book>.pdf <out>.txt` and
  `pandoc --wrap=none -t plain <book>.epub -o <out>.txt`, all inside workspaces/marketing/books/
  (a pandoc `-t` naming a .lua file runs Lua, so nothing else passes);
- for the cmo, `python3 scripts/capacity_scan.py --mac`, word for word and as the whole command (no pipe or list, so
  the call's exit code is the scan's): the Mac's disk, memory and load, read on the Mac, nothing
  written or sent, for its load hold before it starts a content-producer or the ux-expert (cmo.md, "The load hold").
  Not the full scan, which reads every agent's session folder.
The reel-analyst gets the reads and `python3 tools/marketing/reels/watch.py`, and nothing else: no other
script, no file moves. watch.py takes no URL or path, only a week from posts.csv.
Both it and the cmo also run `python3 tools/marketing/reels/save.py`, the reel-analyst only as `post` or `covers`: public
posts and reel covers, logged out, from post codes or a week, never a URL or a path.
The cmo and the producer run watch.py only as `measure --file <render in media/>`, word for word and with no glob: local
numbers, nothing paid, nothing written. Not the reel-analyst: it gets no path.
The cmo runs taste/build.py, which holds itself to one page's folder: it reads its rubric and picks from
workspaces/marketing/media/taste/<page>/ and writes only picker.html there (a session's beside its session.json, in
<page>/session-<date>/), local, nothing sent: one picker an account, never two accounts in one.
It also runs taste/analyze.py, held to one session's folder the same way: it rebuilds the design from session.json with
build.py's checks, reads the answers export beside it and writes only the profile there; --recover writes nothing.
Local, nothing sent.
Not bare ffmpeg: its filters and extra outputs can write anywhere; video/cut.mjs does cuts.
Pipes and &&, ||, ; are fine; redirection only to /dev/null and 2>&1 (as in
guard_critic_bash). No `$` and no backticks anywhere. Outside the reads, nothing the
shell (zsh, with `equals`, `autopushd` and `pushdminus` on) would rewrite after this
check: no brace expansion, no `[...]` globs, no word starting with `=`, no `~` except
a leading `~/`, no `^` or `#`, no URLs (fetch.py's --url aside); except in a
script's words other than a node script's --out and --dir, `*` and `?` only in a path's
last part and never there after a leading dot, and no `scheme:` paths; and `cd` only to one plain
path (not `-`, `-1`, `+1` or `~-`). Paths are resolved
(symlinks too) against the session's cwd, following `cd`, and compared
case-insensitively, because the Mac's disk is. Files are written with Write or
Edit, which guard_kb_write.py checks.
"""

import fnmatch
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from guard_critic_bash import simple_commands  # noqa: E402

READERS = {"cat", "head", "tail", "ls", "wc", "grep", "sort", "uniq", "cut", "diff", "stat", "file", "echo",
           "pwd", "true", "date", "basename", "dirname", "sleep", "jq"}
FIND_ACTIONS = ("-delete", "-exec", "-execdir", "-ok", "-okdir", "-fprint", "-fprintf", "-fls")
SORT_FLAGS = {"-n", "-r", "-u", "-f", "-b", "-h", "-V", "-k", "-t", "-nr", "-rn"}
UNIQ_FLAGS = {"-c", "-d", "-u", "-i"}
SED_PRINT = re.compile(r"^(\d+|\$)?(,(\d+|\$))?p$")
NODE_SCRIPTS = {"tools/marketing/render/png.mjs": None, "tools/marketing/render/reel.mjs": None,
                "tools/marketing/video/subtitles.mjs": None, "tools/marketing/video/frames.mjs": None,
                "tools/marketing/video/cut.mjs": None, "tools/marketing/video/compile.mjs": None,
                "tools/marketing/swipe/ingest.mjs": {"cmo"}}  # None: every marketing agent
OUTPUT_FLAGS = ("--out", "--dir")
PYTHON_SCRIPTS = {"tools/marketing/content_lint.py": None, "scripts/language_check.py": None, "scripts/kb_lint.py": None,
                  "tools/marketing/voice/scribe.py": {"cmo", "content-producer"},
                  "tools/marketing/voice/tts.py": {"content-producer"},
                  "tools/marketing/gen/image.py": {"content-producer"},  # SA-005: the producer generates
                  "tools/marketing/gen/video.py": {"content-producer"},
                  "tools/marketing/spend.py": {"cmo"},
                  "tools/marketing/taste/build.py": {"cmo"},  # writes only picker.html, in media/taste/<page>/ or its session-<date>/
                  "tools/marketing/taste/analyze.py": {"cmo"},  # writes only the profile beside its export, in media/taste/<page>/session-<date>/
                  "tools/marketing/publish/post_hashes.py": {"content-producer"},  # writes its own piece page
                  "tools/marketing/publish/stage_item.py": {"cmo"},
                  "tools/marketing/footage/fetch.py": {"cmo", "content-producer"},  # the only script given a URL (--url)
                  "tools/marketing/reels/watch.py": {"reel-analyst"},
                  "tools/marketing/reels/save.py": {"cmo", "reel-analyst"},  # logged out; post codes or a week, no URL
                  "scripts/capacity_scan.py": {"cmo"}}  # only as --mac (SCAN_ARGS)
FETCH = "tools/marketing/footage/fetch.py"
SCAN = "scripts/capacity_scan.py"
SCAN_ARGS = ["--mac"]
WATCH = "tools/marketing/reels/watch.py"
SAVE = "tools/marketing/reels/save.py"
MEASURERS = {"cmo", "content-producer"}  # of WATCH, only its `measure --file`
WEB_URL = re.compile(r"^https?://[^\s]+$")
MEDIA = "workspaces/marketing/media"
SWIPE = "workspaces/marketing/swipe"
INBOX = "workspaces/marketing/inbox"
BOOKS = "workspaces/marketing/books"
UNSAFE_CHARS = set("{}[]^#")
SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
READABLE_SOURCES = ("workspaces/marketing", MEDIA, "tools/marketing/templates")  # MEDIA resolves outside the repo
CP_FLAGS = re.compile(r"^-[RPpnfvX]+$")


def _fold(path: str) -> str:
    return os.path.normcase(path).casefold()


class Paths:
    def __init__(self, root: str, cwd: str):
        self.root = os.path.realpath(root)
        self.cwd = os.path.realpath(cwd or root)

    def resolve(self, arg: str) -> str:
        return os.path.realpath(os.path.join(self.cwd, os.path.expanduser(arg) if arg.startswith("~") else arg))

    def rel(self, arg: str) -> "str | None":
        """The path relative to the repo root, case-folded, or None outside it."""
        path, root = _fold(self.resolve(arg)), _fold(self.root)
        if path == root:
            return ""
        return path[len(root) + 1:] if path.startswith(root + os.sep) else None

    def under(self, arg: str, *bases: str) -> bool:
        """arg is in one of bases (repo-relative), comparing resolved paths: a base linked elsewhere,
        such as a media folder in a synced drive, still counts."""
        path = _fold(self.resolve(arg))
        for base in bases:
            real = _fold(os.path.realpath(os.path.join(self.root, base)))
            if path == real or path.startswith(real + os.sep):
                return True
        return False


def _operands(args: list) -> list:
    """The non-option words; everything after `--` counts."""
    if "--" in args:
        cut = args.index("--")
        return [a for a in args[:cut] if not a.startswith("-")] + args[cut + 1:]
    return [a for a in args if not a.startswith("-")]


def _matches(word: str, paths: Paths) -> list:
    """What the shell could expand word to, so a glob matching a link is checked where the link leads: its last
    part (the only one _unsafe lets hold * or ?) against every name in its folder, dot names included. An ASCII
    name is matched as zsh does (CASE_GLOB): raw, with case. Any other name counts as matched by every glob, since
    zsh on macOS composes it pair by pair before matching, which neither the raw name nor NFC copies (a, U+0302,
    U+0323 is two characters to it); a match is only checked. Casefolding misses "ß", raw names "n" plus U+0303.
    The word itself if it has no glob or nothing matches."""
    head, last = os.path.split(word)
    if not set("*?") & set(last):
        return [word]
    try:
        names = os.listdir(paths.resolve(head or "."))
    except OSError:
        return [word]
    return [os.path.join(head, n) for n in names if not n.isascii() or fnmatch.fnmatchcase(n, last)] or [word]


def _rewritten(word: str) -> "str | None":
    """Why zsh could expand word into something else, or None: `=cmd`, `~-`, `~+`, `~user`, braces, globs."""
    if word.startswith("="):
        return f"no word starting with = ({word})"
    if "~" in word and not (word == "~" or (word.startswith("~/") and "~" not in word[1:])):
        return f"~ only as a leading ~/ ({word})"
    if UNSAFE_CHARS & set(word):
        return f"no brace expansion, [...], ^ or # ({word})"
    if "://" in word:
        return f"no URLs ({word})"
    return None


def _unsafe(word: str) -> "str | None":
    """Why the shell could turn word into a path other than the one checked, or None."""
    reason = _rewritten(word)
    if reason:
        return reason
    if SCHEME.match(word) and not word.startswith("-"):
        return f"no scheme: paths ({word})"
    parts = word.split("/")
    if any(c in part for part in parts[:-1] for c in "*?"):
        return f"* and ? only in a path's last part ({word})"
    if parts[-1].startswith(".") and any(c in parts[-1] for c in "*?"):
        return f"no globs on dot names ({word})"
    return None


def _outputs(args: list) -> list:
    """The values of --out and --dir, in either `--out x` or `--out=x` form."""
    found = []
    for i, word in enumerate(args):
        flag, eq, value = word.partition("=")
        if flag in OUTPUT_FLAGS:
            found.append(value if eq else (args[i + 1] if i + 1 < len(args) else ""))
    return found


def _reader_reason(name: str, args: list) -> "str | None":
    """The readers that can also write files or run code: sort (-o, --compress-program), uniq (its second
    operand is an output file), file (-C writes a compiled magic file), date (sets the clock)."""
    if name == "sort":
        flags = [a for i, a in enumerate(args) if a.startswith("-") and not (i and args[i - 1] in ("-k", "-t"))]
        bad = [a for a in flags if a not in SORT_FLAGS and not a.startswith(("-k", "-t"))]
        return f"sort only with {' '.join(sorted(SORT_FLAGS))} ({bad[0]})" if bad else None
    if name == "uniq":
        if [a for a in args if a.startswith("-") and a not in UNIQ_FLAGS] or len(_operands(args)) > 1:
            return f"uniq only with {' '.join(sorted(UNIQ_FLAGS))} and at most one file (a second one is written)"
        return None
    if name == "file" and any(a in ("-C", "--compile") for a in args):
        return "file -C writes a compiled magic file"
    if name == "date" and any(not (a.startswith("+") or a == "-u") for a in args):
        return "date only with +FORMAT or -u"
    return None


def _book_reason(name: str, args: list, paths: Paths) -> "str | None":
    """pdftotext [-layout] <book>.pdf <out>.txt, or pandoc --wrap=none -t plain <book>.epub -o <out>.txt."""
    usage = (f"{name} only as `pdftotext [-layout] <book>.pdf <out>.txt` or "
             f"`pandoc --wrap=none -t plain <book>.epub -o <out>.txt`, inside {BOOKS}/")
    if name == "pdftotext":
        ops = [a for a in args if a != "-layout"]
        if len(ops) != 2 or any(a.startswith("-") for a in ops):
            return usage
        source, out, kind = ops[0], ops[1], ".pdf"
    else:
        rest, source, out = list(args), None, None
        while rest:
            word = rest.pop(0)
            if word == "--wrap=none":
                continue
            if word == "-t" and rest and rest[0] == "plain":
                rest.pop(0)
            elif word == "-o" and rest and out is None:
                out = rest.pop(0)
            elif not word.startswith("-") and source is None:
                source = word
            else:
                return usage
        if source is None or out is None:
            return usage
        kind = ".epub"
    if not (source.lower().endswith(kind) and out.lower().endswith(".txt")
            and os.path.isfile(paths.resolve(source)) and paths.under(source, BOOKS) and paths.under(out, BOOKS)):
        return usage
    return None


def _measure_reason(args: list, paths: Paths) -> "str | None":
    """`watch.py measure --file <render>`, nothing else: prepare pays Scribe, and label writes posts.csv."""
    if (len(args) == 4 and args[1:3] == ["measure", "--file"] and not _unsafe(args[3]) and not set("*?") & set(args[3])
            and paths.under(args[3], MEDIA)):
        return None
    return f"{WATCH} is for the reel-analyst; you run only `measure --file <a render in {MEDIA}/>`"


def _check(words: list, agent: str, paths: Paths) -> "str | None":
    name, args = words[0], words[1:]
    if name == "cd":
        if len(args) != 1 or args[0][:1] in ("-", "+") or _unsafe(args[0]) or "*" in args[0] or "?" in args[0]:
            return "cd only to one plain path"
        paths.cwd = paths.resolve(args[0])
        return None
    if name in READERS:
        return _reader_reason(name, args)
    if name == "find":
        return "find may not delete or run anything" if any(a.startswith(FIND_ACTIONS) for a in args) else None
    if name == "sed":
        ops = _operands(args)
        if "-n" in args and ops and SED_PRINT.match(ops[0]) and all(a in ("-n", "-E", "-r") or not a.startswith("-") for a in args):
            return None
        return "sed may only print (sed -n 'N,Mp' file)"
    if name in ("node", "python3", "python"):
        scripts = NODE_SCRIPTS if name == "node" else PYTHON_SCRIPTS
        rel = paths.rel(args[0]) if args and not args[0].startswith("-") else None
        script = next((s for s in scripts if rel == _fold(s)), None)
        if script is None:
            return f"{name} runs only the marketing scripts: {', '.join(sorted(scripts))}"
        if agent == "reel-analyst" and not ((script == WATCH and "measure" not in args)
                                            or (script == SAVE and args[1:2] in (["post"], ["covers"]))):
            return f"the reel-analyst runs only {WATCH} on a week, and {SAVE} post or covers"
        if script == WATCH and agent in MEASURERS:
            return _measure_reason(args, paths)
        who = scripts[script]
        if who is not None and agent not in who:
            return f"{script} is for the {' and '.join(sorted(who))}"
        if script == SCAN and args[1:] != SCAN_ARGS:
            return f"{SCAN} runs only as `python3 {SCAN} --mac`, word for word"
        checked = args
        if script == FETCH:  # its --url value may be a web address; nothing else may
            urls = [i + 1 for i, a in enumerate(args) if a == "--url"] + [i for i, a in enumerate(args) if a.startswith("--url=")]
            for i in urls:
                value = "" if i >= len(args) else (args[i].partition("=")[2] if args[i].startswith("--url=") else args[i])
                if not WEB_URL.match(value):
                    return f"{FETCH} --url takes an http(s) address"
            checked = [a for i, a in enumerate(args) if i not in urls]
        rewritten = next(filter(None, map(_rewritten, checked)), None)
        if rewritten:
            return rewritten
        base = SWIPE if script.endswith("ingest.mjs") else MEDIA
        outs = _outputs(args) if name == "node" else []
        if any(_unsafe(o) or not paths.under(o, base) for o in outs):
            return f"{script} writes only into {base}/"
        return None
    if agent == "reel-analyst":
        return f"the reel-analyst's Bash is reads, {WATCH} and {SAVE}, not '{name}'"
    unsafe = next(filter(None, map(_unsafe, args)), None)
    if unsafe:
        return unsafe
    if name in ("mkdir", "mv", "rm"):
        ops = _operands(args)
        bases = (MEDIA, SWIPE) if agent == "cmo" else (MEDIA,)
        return None if ops and all(paths.under(a, *bases) for a in ops) else f"{name} works only inside {' or '.join(bases)}/"
    if name in ("pdftotext", "pandoc") and agent == "cmo":
        return _book_reason(name, args, paths)
    if name == "cp":
        flags = args[:args.index("--")] if "--" in args else args
        if any(f.startswith("-") and f != "--" and not CP_FLAGS.match(f) for f in flags):
            # -r, -H and -L follow links, -s and -l make them; -R copies a link as a link.
            return "cp takes only -R -P -p -n -f -v -X: the others follow links or make them"
        ops = _operands(args)
        if len(ops) < 2 or set("*?") & set(ops[-1]) or any("**" in a for a in ops):
            return f"cp needs a plain destination in {MEDIA}/, and no ** in a source"
        sources = [match for a in ops[:-1] for match in _matches(a, paths)]
        out = next((a for a in sources if not paths.under(a, *READABLE_SOURCES)), None)
        if paths.under(ops[-1], MEDIA) and out is None:
            return None
        if out is not None and paths.under(out, INBOX, SWIPE):
            # It names the source, which may be a link in media/ the command reached by a glob, so repr() escapes a
            # newline or control character in its name.
            folder = INBOX if paths.under(out, INBOX) else SWIPE
            return (f"cp's source {out!r} resolves into {folder}/, and cp doesn't copy from {INBOX}/ or {SWIPE}/: "
                    f"each is a link out of {MEDIA}/, so its files resolve outside every folder cp "
                    "copies from; use them where they are")
        return f"cp copies only from workspaces/marketing/ (media/ included) or tools/marketing/templates/ into {MEDIA}/"
    return f"'{name}' isn't on the marketing agents' list"


def bash_reason(command: str, agent: str, cwd: str, root: str) -> "str | None":
    """Why this Bash command is blocked for a marketing agent, or None to allow it."""
    if "$" in command or "`" in command:
        return "no $ expansions or backticks"
    try:
        commands = simple_commands(command)
    except ValueError:
        return "unbalanced quotes"
    if not commands:
        return "only plain commands: no heredocs, subshells or redirection into files"
    paths = Paths(root, cwd)
    for words in commands:
        reason = _check(words, agent, paths)
        if reason:
            return reason
        if len(commands) > 1 and words[0] in ("python3", "python") and paths.rel(words[1]) == _fold(SCAN):
            return f"{SCAN} runs only as the whole command, so the call's exit code is the scan's"
    return None
