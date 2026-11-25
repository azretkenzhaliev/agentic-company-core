"""A subagent writes a ceo-questions.md only by Edit, an append (`>>`, `tee -a`) or the root's `scripts/cq_archive.py`,
by absolute path from any cwd or relative as `_script` reads it.

cto.md, Working rules, "Logs": "Write the file only by Edit, `--add` or a one-shot `>>`, never through a file you hold
open". The refusal names `--add`, which puts an order's line under its heading. Several CTOs, Staff engineers and
Seniors write one workspaces/<product>/content/ceo-questions.md at once, so a whole rewrite can drop another agent's
NEEDS-CEO-NOW line or a CEO ruling; git can't restore it, since workspaces/ is gitignored.

Only subagents are held (the hook input has agent_id); the main session, the CEO, inserts rulings with Python. Only a
live file counts: a path that is, or may be, under the repo's workspaces/ (relative, through a variable the command
doesn't set, or with a top folder that doesn't exist); a scratch copy at an absolute path elsewhere, such as a test's,
is free. A Write on an existing one is refused by guard_kb_write.py. A Bash command is refused here
(guard_marketing_tools.py calls cq_reason for every Bash call, and fails closed) when a simple command in it names one,
by its path, through a variable the same command sets to it, or behind a `$(...)` or backtick whose text names it,
and:
- redirects into it with `>`, `>|`, zsh's `>!`, `&>`, `>&` or `<>` (`>>` and `&>>` pass);
- runs sed in place (`-i`, `-I`, `--in-place`), awk in place (`-i`) or writing to it, or an editor (ed, ex, vi, vim, ...);
- runs an interpreter (python, node, ruby, perl, php, bun, deno, uv, ...) other than the root's cq_archive.py,
  or a shell on a script or heredoc: a heredoc body or any text that names it counts (`python3 - <<'EOF'`,
  `perl -ne 'print if /x/' <it>`); so it does for an editor (ed runs its `w` from stdin) and a command behind xargs
  (stdin becomes its operands); for the rest (tee, cp, ...) a heredoc's text doesn't, as they write only their operands;
- runs tee or sponge without `-a`;
- copies or moves onto it: cp, install, rsync, ditto, ln or mv with it as the last operand (or GNU's `-t`), or with a
  source named ceo-questions.md and, as the last, a `content` folder, `.`, `..` or a folder it can't tell, which any
  `$`, backtick, glob or brace in it makes (the copy-out, edit, move-back form; `<content/>$(true)`, `conten[t]/`);
  dd with `of=` it; and, with such a source, into any other folder that may hold the live one, read from where the
  command runs (places): one written as a folder (a trailing `/`, `-t`, two sources or more), one that exists or one of
  the layout's (LAYOUT; an order's own file is content/orders/<directive id>/<n>/ceo-questions.md), or a relative one
  after a cd it can't follow; a copy to another file's name passes;
- moves, removes or truncates it (mv, rm, unlink, truncate, shred, find's `-delete`);
- and, whether the command names the file or not, removes or moves a folder that holds a live one (holds_live:
  workspaces/ or a folder above it, a product's folder, its content/, orders/ or orders-closed/, a directive's or an
  order's folder; a glob by its matches, the live file itself among them; a path it can't read): rm, srm or trash of it
  (an rm or srm that isn't recursive takes no folder that holds a file, so a path it names with nothing the shell
  expands, LITERAL, passes, whatever the cwd: `rm slot-2/owner; rmdir slot-2`), mv of it (not into it), rsync's
  `--delete` into it or `--remove-source-files` (or its old name `--remove-sent-files`) from it, find's `-delete` or a
  remover in its actions from it, a remover xargs feeds, or one of these in `sh -c`, eval, a trap or a `$(...)`. A
  command that doesn't name the file is read for this only if it names one of those programs and a layout folder
  (FOLDER_WORDS); these are told only when no other reason is found (in a command that names the file, a `sh -c`, eval
  or trap text's too). Its cost: in a command that names a layout folder's word anywhere, any remover xargs feeds and any `rm "$VAR/..."` are refused,
  whatever they remove (write the path out);
- runs a program a `$` or backtick names (`X=rm; $X <it>`, `${x:-rm}`, `$(echo rm)`, `` `true`python3 ``, `$'rm'`),
  which may be any of these;
- or, anywhere in the command, defines an alias or a function (`alias x='sed -i'`, zsh's `alias -s`, `f() { ...; }`,
  `function f`, in eval's or a trap's text too), which may run any of these under another name.
`sh|bash|zsh|dash|ksh -c '<string>'` (without the command's variables: a new shell has only exported ones), `eval`,
`trap`, an `alias`'s text (zsh runs it on a later line) and the commands in `$(...)`, backticks, `<(...)` and `>(...)`
(outside single quotes and quoted heredocs) are read inside, three levels deep; a `$(...)`'s text is also read cut
out of its word, so the shell's program and operands after it count (`$(true)python3`, `sed -i '' $(true) ... <it>`).
A backslash-newline joins the words around it, as in the shell (`s\\<newline>ed` is sed); the command is read again
with it as a space, so nothing refused either way passes, and, if it holds an escaped backslash before a newline
(`echo \\\\<newline>rm <it>`: the newline ends the line), with that newline ending the line. A here-string's text (`bash
<<< 'rm <it>'`) counts as a heredoc's, a heredoc before the program (`<<'EOF' python3`) leaves the program as the first
word, `D+=x` keeps no value for D (so a path built from it may be live), and a `~` path counts as live when the command
may set HOME (`HOME=`, `export HOME=`, `read HOME`).
What find's `-exec`, `-execdir`, `-ok` and `-okdir` run is a program too, read to the end of the command and up to each
`;` or `{} +` that may end it, and where find names a ceo-questions.md, `{}` is one in each folder find starts from
(`find /tmp/s -name <it> -exec cp {} <content/> ';'`), or a live one for a folder that holds a live folder or has a glob
or brace (`find ~ -name <it> -delete`).
A heredoc is read only in a form the shell reads the same way (heredoc_doubt); any other that names the file is refused
as unreadable: a `<<` in quotes (nested in a `${ }` too), a `${ }`, a comment or arithmetic (`$[ ]` too), a `<<<`, a
`<<` split by a backslash-newline, a `'` in a `${ }` in double quotes (a quote to bash, not to zsh), an end word that is
more than a name (`<<E\\OF`), a first line that leaves a quote open or holds a second heredoc, an end line with more than
the word or none, and an empty heredoc whose word comes again later (`cat <<EOF`, `EOF`, `sed -i ... <it>`, `EOF`,
where the shell runs the sed line). Deeper, in a command over 256,000 characters, or still being read after 20 s, it's
refused (fail closed: settings.json gives the hook 60 s). Reads pass (cat, grep, sed -n, awk, head, a cp to a named
file), and so do `>>`, `tee -a` and the cq_archive call.

A script file is the same form. Every subagent Bash command, naming the file or not, is also refused (script_reason) when
an interpreter or shell in it runs a script file (`python3 x.py`, `node x.js`, `bash x.sh`, `npx tsx x.ts`, `source
x.sh`, or `./x.py` run by its path) whose text names a live one, unless the script is a checkout's own code (a `.git`
above it, with no live workspaces/ between: the repo's kb_lint.py and tests name the file) or a named exception below.

Named exceptions:
- `bun scripts/<deploy script> ... --ceo-questions <path>`, a product's deploy script, which only reads it: the file
  name that company.json gives ("integrations": {"question_files": {"deploy_script": "<name>.ts"}}; none named, none
  passes), and only a product checkout's own: a file under the live workspaces/, in `scripts/` beside the checkout's
  `.git`, a relative path read from the folder the command's `cd`s moved to (deploy_script, places: only a `cd` joined to
  it by `&&` counts, past commands that can't move the shell; a `;` or newline after the cd (which may have failed), a
  `( )`, `if`, `case`, pipeline, `||`, background list, trap, alias or eval before it leaves the folder unknown, and the
  path is refused; so does a variable or `~` in the cd or the script's path);
- `python3 scripts/second_opinion.py ...`, which only reads its `--file` and `--brief` and writes only its own call log
  and answers, so a reviewer of a change about this file keeps its call.

A subagent writes no line that passes for the CEO's: the capacity scan counts a NEEDS-CEO-NOW as answered only by a line
that starts `CEO`, and no test on a line's text tells the CEO's from an agent's, but the hook input's agent_id tells who writes. So, for a subagent, a write to a live ceo-questions.md, a
product's or an order's own, that adds a line starting `CEO` (after spaces, `- ` or `**`), or whose first parenthesis, or
the one right after its first time, starts `(CEO` (ceo_line), is refused: an Edit or MultiEdit (the file's lines after it
that it didn't hold before, by count, so one that changes a CEO line is refused too), a Write of a new file, and a Bash
command that names the file and appends to it (`>>` or `&>>` into it, tee or sponge naming it, cq_archive.py's `--add`;
ceo_reason), by what it may write there: what echo, print and printf print (each of printf's words alone), a heredoc's
body, a here-string's text and `--add`'s line, in it and in what it runs inside (`$(...)`, backticks, `<(...)`, a shell's
`-c`, eval's and a trap's text), each split at a newline or an escape that prints one (`\\n`, `\\x0a`, `\\012`). A reply's
indented, numbered or `(` line joins it in the scan (its GOES_ON and goes_on), so such an append is refused too when the
first line of one of those texts is such a line (CONTINUES; agents start each `>>` with their own word: cto.md,
staff-engineer.md), and so is an Edit or MultiEdit that leaves such a line right under a CEO line, or under one that is,
where it didn't stand (under_ceo, by count: one added or changed there, or a line above it taken out, a blank among them);
one that takes a CEO line out with its lines, or from its last line up, passes (the by-hand move, cto.md, "Logs"). It is
told only when no older reason is, and a command that names the file still being read at the timer is refused as above.
The main session (no agent_id) isn't held. Over-broad: in a command that appends to the file, any printer's line counts,
also one that prints to the terminal (`echo 'CEO lines: 3'`), and so does the first line of each printer's text, a second
echo's or a printf word's too (`{ echo HANDLED x; echo '  y'; } >> <the file>`: write it as one heredoc).

The archive beside a live file, ceo-questions-archive.md (a product's, or one beside an order's file), is held the same
way: the scan reads its replies too, and agents move a CEO line there by hand (cto.md, "Logs"). A subagent's `>>`, `>`,
tee, sponge or `--add` into one (archive_reason, by the texts above; ARCHIVE_MENTION names it), and its Edit, MultiEdit or
Write of one (write_reason; guard_kb_write.py calls it for the archive's name too), is refused when it adds a line that
passes for the CEO's, or one that may join one there (an append's first line that CONTINUES matches, and such a line right
under a CEO line or under one of these in the same text: joining; an Edit's line under_ceo newly finds), unless the
ceo-questions.md in the same folder holds that line as it is then: a CEO line anywhere in it, a joining line under a CEO
line there (unheld). That is what the by-hand move does: its `>>` comes before the Edits that take the lines out of the
file, from the last line up. A target it can't place (a variable with no plain value, a `$(...)`, a `~` the command may
move, any relative path, which a cd, `env -C` or find's `-execdir` may move: folder_of) has no file beside it, so such a
line to it is refused: write the archive's path out, absolute. A link with the archive's name is read by its real path,
against the file beside the archive it points to (folder_of, as may_be_live). Over-broad there: a line the file holds with
an escape that prints a newline (`\\n`) is read in pieces, which the file doesn't hold. cq_archive.py's own moves, made
inside its process, aren't held: it never moves a line starting `CEO`, moves a line this counts as the CEO's only with the
lines under it, and puts no line into a CEO line's reply it wasn't in before the run (cq_archive.together, keep_apart,
to_archive).

It stops mistakes; it isn't a sandbox.
"""

import bisect
import copy
import fnmatch
import glob
import os
import re
import shlex
import signal
import sys
from collections import Counter

NAME = "ceo-questions.md"
MENTION = re.compile(r"(?<![\w.-])ceo-questions\.md(?![\w.-])", re.I)
# The archive beside each one, whose replies the capacity scan reads too
ARCHIVE = "ceo-questions-archive.md"
ARCHIVE_MENTION = re.compile(r"(?<![\w.-])ceo-questions-archive\.md(?![\w.-])", re.I)
STOP = set("'\"=:,;()<>|&`")  # what ends a path inside one word or a line of code (`open('<path>')`)
PUNCTUATION = set("();<>|&")
HEREDOC_NAME = re.compile(r"[A-Za-z_][\w.-]*")
# Quoted text is matched only to step over it: a `#` in quotes is no comment, and an apostrophe in a comment no quote;
# nor is a `#` after a backslash-newline, which joins it to the word before (`a\<newline>#b` is `a#b`). SPACED is the
# reading that takes a backslash-newline for a space (tokens).
COMMENT_OR_QUOTED = re.compile(r"""'[^']*'|"(?:\\.|[^"\\])*"|\\.|(?<![^\s;&|()])(?<!\\\n)#[^\n]*""", re.S)
SPACED = re.compile(r"""'[^']*'|"(?:\\.|[^"\\])*"|\\.|(?<![^\s;&|()])#[^\n]*""", re.S)
QUOTED_PUNCTUATION = re.compile(r"""^(['"])[();<>|&]+\1$""")
ESCAPED_PAREN = re.compile(r"\\[()]")  # `\(`: a word to the shell, a bare `(` to shlex (tokens)
ESCAPED_OPERATOR = re.compile(r"\\[;<>|&]")  # `\;`, `\|`: a word to the shell, a bare `;` or `|` to shlex (tokens)
HEREDOC_WORD = "heredoc:ceo-questions.md"
HIDDEN = re.compile(r"\$\(|`|\$$")  # shlex leaves a word ending in `$` before an unquoted `$(`
VARIABLE = re.compile(r"\$(?:\{([A-Za-z_]\w*)\}|([A-Za-z_]\w*))")
ASSIGNMENT = re.compile(r"^([A-Za-z_]\w*)=(.*)$", re.S)
APPEND = re.compile(r"^([A-Za-z_]\w*)\+=")  # `D+=x` adds to D's value
# HOME other than read as `$HOME` or `${HOME}`: the command may set it (`HOME=`, `export HOME=`, `read HOME`,
# `${HOME:=x}`), and the shell expands `~` from it.
HOME = re.compile(r"(?<![\w$])(?<!\$\{)HOME(?!\w)|\$\{HOME(?!\})")
# What may define an alias or a function in eval's or a trap's text, which run in this shell.
DEFINES = re.compile(r"\balias\b|\bfunction\b|\(\s*\)")
FD = re.compile(r"^\d+$")
DECLARERS = {"export", "local", "declare", "readonly", "typeset"}
KEYWORDS = {"if", "then", "elif", "else", "fi", "do", "done", "while", "until", "time", "!", "{", "}", "coproc"}
WRAPPERS = {"nohup", "command", "builtin", "exec", "nice", "env", "timeout", "caffeinate", "stdbuf", "sudo", "xargs",
            "noglob", "nocorrect", "-"}  # the last three: zsh's precommand modifiers
WRAPPER_VALUE = re.compile(r"^(\d+(\.\d+)?[smhd]?|\{\})$")  # nice -n 15, timeout 170, xargs -I {}
INTERPRETER = re.compile(r"^(python[\d.]*|pypy[\d.]*|node(js)?|ruby|perl[\d.]*|php[\d.]*|bunx?|deno|lua(jit)?|"
                         r"osascript|rscript|tclsh|pwsh|npx|tsx|ts-node|swift|java|jshell|groovy|uvx?)$", re.I)
EDITORS = {"ed", "red", "ex", "vi", "vim", "nvim", "view", "nano", "pico", "emacs"}
COPIERS = {"cp", "gcp", "install", "rsync", "ditto", "ln"}
REMOVERS = {"mv", "rm", "unlink", "truncate", "shred", "srm"}
FIND_ACTIONS = {"-exec", "-execdir", "-ok", "-okdir"}
# Where the live files are below a workspaces/ folder, the product's and each order's own, and what removes or moves a
# folder that holds one (holds_live, folder_reason). A command that doesn't name the file is read for this only if it
# names one of FOLDER_PROGRAMS and a folder of the layout.
LAYOUT = ("*/content/" + NAME, "*/content/orders/*/*/" + NAME, "*/content/orders-closed/*/*/" + NAME)
FOLDER_PROGRAMS = {"rm", "srm", "trash", "mv", "rsync", "find", "gfind"}
LITERAL = re.compile(r"[^$`~*?\[{]+")  # a path with nothing the shell expands: no variable, `~`, glob or brace
# A `(` glued to the character before it, not after `$`, `<`, `>`, `=`, a backslash or another `(`: zsh's glob group
# (`content/(c|x)eo-questions.md`), where shlex ends the word at the `(`
GLUED_PAREN = re.compile(r"[^\s;&|()<>$=\\]\(")
FOLDER_WORDS = (re.compile(r"(?<![\w.-])(?:rm|srm|trash|mv|rsync|g?find)(?![\w.-])", re.I),
                re.compile(r"(?<![\w.-])(?:workspaces|content|orders(?:-closed)?)(?![\w.-])", re.I))
FIND_OPTIONS = re.compile(r"^-[HLPEXdsx]+$")  # find's options before the folders it starts from
SHELLS = {"sh", "bash", "zsh", "dash", "ksh"}
SHELL_STRING_FLAG = re.compile(r"^-[A-Za-z]*c[A-Za-z]*$")
SAFE_PYTHON_FLAGS = {"-I", "-B", "-E", "-s", "-S", "-u"}
DEPTH = 3
LONGEST = 256_000  # characters: past this the parse may near the hook's 60 s limit
SECONDS = 20  # one that names the file, still being read after this, is refused (cq_reason); the Bash hook has 60 s
SCRIPT_BYTES = 1_000_000  # how much of a script file's text script_reason reads for a mention
FOLDERS = 64  # the outer command's latest cd folders an inner one also tries a relative script from
SOURCES = {"source", "."}  # they run a script file in this shell
RUNNERS = {"npx", "bunx", "uvx", "uv"}  # their first operand (after uv's `run`) is the program they run
# The folder a deploy script's relative path is read from (places): the commands before it may only move (MOVES) or
# leave the folder as it is (STILL), joined only by LISTS. Anything else (trap, alias, eval, popd, exec, `(`, `if`,
# `case`, ...) may move it, or change where a later cd goes, so no folder is told after it.
MOVES = {"cd", "pushd"}  # not zsh's chdir, which bash lacks: it may move
STILL = {"true", "false", ":", "echo", "pwd", "date", "sleep", "ls", "cat", "grep", "head", "tail", "wc", "test", "[",
         "[[", "git", "gh", "mkdir", "touch", "bun"}
LISTS = {";", "&", "&&", "||", "|", "|&"}
PIPES = {"|", "|&"}
# A relative cd may go where CDPATH says (bash reads it before the folder, zsh after): the command may set it by name,
# or through a `${...}` or `$[...]` that assigns.
CDPATH = re.compile(r"cdpath|\$[{\[]", re.I)
TERMINATOR = set(" \t\n;&|()<>")  # what ends a heredoc's end word for the shell
NOT_SPACE = re.compile(r"\S")
# Each backslash with the character it escapes, left to right: a backslash-newline is removed, as the shell does outside
# single quotes, but `\\` and then a newline ends a line.
CONTINUATION = re.compile(r"\\(.)", re.S)
# What matters next in each context of heredoc_doubt's scan: code (at the top, in `( )`, `$( )`, backticks or `${ }`),
# arithmetic (`(( ))`, `$(( ))`, `$[ ]`), double quotes, single quotes, `$'...'` and a comment.
NEXT = {"code": re.compile(r"[\\'\"$()`#<{}]"), "((": re.compile(r"[\\'\"$()`<]"), "$[": re.compile(r"[\\'\"$`<\[\]]"),
        '"': re.compile(r"[\\\"$`<]"), "'": re.compile(r"['<]"), "$'": re.compile(r"[\\'<]"), "#": re.compile(r"[\n<]")}
BRACES = {"${", '"${'}  # a `${ }`, and one in double quotes, where bash reads `'` as a quote and zsh doesn't
CODE = {"code", "(", "$(", "`"} | BRACES
# A line that passes for the CEO's (ceo_line), a superset of what
# scripts/capacity_scan.py counts as the CEO's (by_ceo): `CEO` first, after spaces, `- ` or `**`; or `(CEO` as its first
# parenthesis, or the one right after its first time (CLOCK).
CEO_FIRST = re.compile(r"(?:[ \t]|- |\*\*)*CEO")
CLOCK = re.compile(r"\d\d:[0-5x]\d(?::[0-5]\d)?(?:\.\d+)?Z")
NEWLINE = re.compile(r"\n|\\(?:n|[xuU]0*[aA]|0*12)")  # a newline, or an escape echo, print or printf may print as one
PRINTERS = {"echo", "print", "printf"}
ADD = re.compile(r"--add?(?:=|$)")  # cq_archive.py's --add (argparse takes `--ad` too), its line next or after `=`
APPENDS = re.compile(r">>|tee|sponge|--ad")  # read with quotes and backslashes out: none, and nothing appends
CONTINUES = re.compile(r"[ \t]|\d+[.)][ \t]|\(")  # the scan's GOES_ON: a line that may join the reply above it

DEPLOY_HINT = (" (the deploy script passes only in the form `cd <checkout> && bun scripts/{name} "
               "... --ceo-questions <path>`, with nothing before the cd but commands that can't move the shell)")
MESSAGE = (
    "Blocked: {how}. A subagent changes a ceo-questions.md only with the Edit tool, the root's cq_archive.py or a "
    "one-shot `>>` (or `tee -a`) of whole lines. An order with its own file, "
    "{root}/workspaces/<product>/content/orders/<directive id>/<n>/ceo-questions.md (opened by the CEO), takes each of "
    "its lines there by `>>`. To the product's file, {root}/workspaces/<product>/content/ceo-questions.md, a `>>` adds "
    "only a line that is no order's (a LANES line) or a new `## ORDER` heading with its first line: a line "
    "for an older order goes under that order's heading with `python3 {root}/scripts/cq_archive.py "
    "{root}/workspaces/<product>/content/ceo-questions.md --order <id> --add '<the line>'` (a `>>` lands it under the "
    "file's last heading, another order's), and handled lines move with `python3 {root}/scripts/cq_archive.py "
    "{root}/workspaces/<product>/content/ceo-questions.md --order <id>`, both paths absolute, no `cd` (cto.md, Working "
    "rules, \"Logs\"; scripts/hooks/cq_write.py). "
    "Other agents write the file at the same time, so a whole rewrite (`sed -i` is one) can drop their "
    "lines. An interpreter or shell whose command names the file at all, even in text or a heredoc, is refused: "
    "read it only with cat, grep or `sed -n`. A script file, a module or any other program that opens the file is "
    "the same refused form, even where the command doesn't name it: running one after this refusal is a variant, "
    "and a refusal is final (CLAUDE.md, b9)."
)
CEO_MESSAGE = (
    "Blocked: {how}. In a ceo-questions.md a line passes for the CEO's when it starts `CEO` (after "
    "spaces, `- ` or `**`) or puts `(CEO` first in its first parenthesis or the one right after its first time, and an "
    "indented, numbered or `(` line under it for part of it, so only the main session, the CEO, writes such lines; a "
    "subagent's is refused by who writes it, the hook input's agent_id (cto.md, \"Your "
    "question file\"). Your line starts with its own word (REPORT, QUESTION, HANDLED, ...), never a space, a "
    "number or `(`, and cites a ruling inside it, never with `(CEO` first in a parenthesis (`HANDLED /1.CTO 12:30Z: "
    "done, per CEO RULING /1/3 12:20Z`); a `>>` of several lines is one heredoc or one echo, its first line yours. An "
    "Edit leaves the CEO's lines, and what stands under them, as they are: a CEO line moved out by hand goes with its "
    "lines in one Edit, or from its last line up. The same text built another way (a variable, printf's format, a "
    "file, a script) is a variant, and a refusal is final (CLAUDE.md, b9)."
)
ARCHIVE_MESSAGE = (
    "Blocked: {how}. The capacity scan reads the replies in a ceo-questions-archive.md as in the ceo-questions.md "
    "beside it: a line that starts `CEO` (after spaces, `- ` or `**`), or puts `(CEO` first in its first parenthesis or "
    "the one right after its first time, passes for the CEO's, and an indented, numbered or `(` line under it for part "
    "of it. So "
    "a subagent adds such a line to an archive only as the by-hand move does, while the same line stands in the "
    "ceo-questions.md in the same folder (an indented, numbered or `(` line: under a CEO line there), by an absolute "
    "path: `>>` the CEO line with its lines, in their order, as one heredoc, then Edit them out of the "
    "ceo-questions.md from the last line up (cto.md, Working rules, \"Logs\"). "
    "Your own lines start with your own word, never a space, a number or `(`. The same text built another way (a "
    "variable, printf's format, a file, a script) is a variant, and a refusal is final (CLAUDE.md, b9)."
)


def live_folders(root: str) -> list:
    """The workspaces/ folders the live files are in: root's, and its main checkout's if root is an agent's worktree."""
    real = os.path.realpath(root)
    cut = real.find("/.claude/worktrees/")
    return [os.path.join(base, "workspaces") for base in ([real, real[:cut]] if cut > 0 else [real])]


def candidates(word: str, mention=MENTION):
    """Each mention with the path before it, back to a space or a STOP character, if a `/` joins them. Walked back
    by hand: a regex for it takes time in the word's length times its slashes."""
    floor = 0  # the last mention's end: no walk goes back past it
    for found in mention.finditer(word):
        start = found.start()
        if start and word[start - 1] == "/":
            while start > floor and not word[start - 1].isspace() and word[start - 1] not in STOP:
                start -= 1
        floor = found.end()
        yield word[start:found.end()]


def expand(word: str, values: dict) -> str:
    return VARIABLE.sub(lambda found: values.get(found.group(1) or found.group(2), found[0]), word)


def operator(token: str) -> bool:
    return bool(token) and set(token) <= PUNCTUATION


class Scope:
    """What one command sets: the variables that name a live ceo-questions.md (names) and the plain values of the
    rest (values). A path is live if it is, or may be, under the repo's workspaces/: a relative one, one with a
    variable the command doesn't set, or one whose top folder doesn't exist (`ROOT + '/workspaces/...'`) may be."""

    def __init__(self, cwd: str, root: str, names: "set | None" = None, values: "dict | None" = None):
        self.cwd, self.root = cwd, root
        self.names, self.values = set(names or ()), dict(values or {})
        self.hidden = False  # whether a `$(...)` or backtick in the command names one
        self.live = [folder.casefold() + "/" for folder in live_folders(root)]
        self.at = cwd  # the folder the command runs in, or None if it can't tell (deploy_script)
        self.unsure = False  # whether a command before it may have changed how the shell moves (places)
        self.relative = True  # whether a relative cd goes where it says: no CDPATH may be set (Scope.cd)
        self.home = False  # whether the command may set HOME, so a `~` path may be live (may_be_live)
        self.defer = False  # whether the outermost command names the file, so a timeout refuses it (program_reason)
        self.glued = False  # whether the command holds a zsh glob group, which shlex splits (GLUED_PAREN)
        self.mention = MENTION  # what names the file: ARCHIVE_MENTION for archive_reason's read

    def cd(self, args: list, here: "str | None") -> "str | None":
        """Where `cd <folder>` (or pushd) goes from here, as the shell's logical cd does (os.path.normpath), or
        None if this can't tell: any other form (`cd`, `cd -`, `cd +1`, an option, `~`, any variable: a later `${D::=x}`
        or `$[D=5]` may have changed it), a relative folder from an unknown one or with CDPATH maybe set, or a `..` whose
        real folder isn't the logical one (`cd <link>/..`) or doesn't exist."""
        folder = args[0] if len(args) == 1 else ""
        if not folder or folder[0] in "-+~=" or "$" in folder or "`" in folder:
            return None
        if not folder.startswith("/") and (here is None or not self.relative):
            return None
        joined = os.path.join(here or "/", folder)
        logical = os.path.normpath(joined)
        if ".." in folder.split("/") and not (os.path.isdir(joined)
                                              and os.path.realpath(joined) == os.path.realpath(logical)):
            return None
        return logical

    def may_be_live(self, path: str) -> bool:
        path = expand(path, self.values)
        if self.home and path.startswith("~"):  # `HOME=<live content dir>; sed -i ... ~/<the file>`
            return True
        path = os.path.expanduser(path)
        if "$" in path or "`" in path or not path.startswith("/"):
            return True
        if not os.path.exists("/" + path.lstrip("/").split("/", 1)[0]):
            return True
        return any(os.path.realpath(path).casefold().startswith(folder) for folder in self.live)

    def mentioned(self, word: str) -> bool:
        """Whether a word names a live ceo-questions.md: by a path, or through a variable the command set to one."""
        if any(self.may_be_live(path) for path in candidates(word, self.mention)):
            return True
        return any((found.group(1) or found.group(2)) in self.names and not re.match(r"[\w.-]", word[found.end():])
                   for found in VARIABLE.finditer(word))  # `$F`, not `$F.new`

    def read(self, words: list) -> None:
        """Learn the command's variables, from `NAME=value` (export and its kin included) and `for NAME in ...`. A
        value is kept only from an assignment that surely sets the shell's variable (sure_assignments), and a name
        assigned twice, or added to (`D+=x`), keeps none, so a path built from it may be live (`D=/tmp; D=<live dir>`,
        `D=/tmp; D+=/../<live dir>`)."""
        counts = {}
        for word in words:
            assigned = ASSIGNMENT.match(word)
            if assigned:
                counts[assigned.group(1)] = counts.get(assigned.group(1), 0) + 1
            elif APPEND.match(word):
                counts[APPEND.match(word).group(1)] = 2  # as if assigned twice: no value is kept
        for name in counts:
            self.values.pop(name, None)  # an outer value it may change (`eval "D=..."`)
        sure = sure_assignments(words)
        for _ in range(3):  # a variable set from another one
            for i, word in enumerate(words):
                assigned = ASSIGNMENT.match(word)
                if assigned:
                    name, value = assigned.groups()
                    if i in sure and "$" not in value and "`" not in value and counts[name] == 1:
                        self.values.setdefault(name, value)
                    if self.mentioned(value):
                        self.names.add(name)
                elif APPEND.match(word) and self.mentioned(word[APPEND.match(word).end():]):
                    self.names.add(APPEND.match(word).group(1))
                elif word == "for" and i + 2 < len(words) and words[i + 2] == "in":
                    loop = words[i + 3:]
                    end = next((j for j, w in enumerate(loop) if operator(w)), len(loop))
                    if any(self.mentioned(w) for w in loop[:end]):
                        self.names.add(words[i + 1])


def sure_assignments(words: list) -> set:
    """The indices of the assignments that surely set the shell's variable when they run: in a command of only
    assignments (or export, declare, typeset or readonly and assignments), first or after `;` or a newline, not piped,
    redirected or sent to the background, and before any keyword, `(` or other operator not in LISTS (code that may
    not run, or runs in a subshell). `D=x true`, `false && D=x`, `while false; do D=x; done` and, in zsh, `D=x </no`
    set nothing. What a later command does to the value isn't followed."""
    sure, start, ops = set(), 0, []  # ops: the operators since the last command
    for end in range(len(words) + 1):
        if end < len(words) and not operator(words[end]):
            continue
        command = words[start:end]
        after = words[end] if end < len(words) else ";"
        if command:
            if command[0] in KEYWORDS or command[0] in ("for", "case", "select", "function", "repeat"):
                break
            first = 1 if command[0] in ("export", "declare", "typeset", "readonly") else 0
            if (all(op == ";" for op in ops) and after in LISTS and after not in PIPES and after != "&"
                    and all(ASSIGNMENT.match(word) for word in command[first:])):
                sure.update(range(start + first, end))
            ops = []
        if after not in LISTS:
            break
        ops.append(after)
        start = end + 1
    return sure


def heredocs(text: str, replace, dashes: "list | None" = None) -> str:
    """The text with each heredoc, from its `<<` to its end line, replaced by replace(quote, rest of its first line,
    body): a heredoc's body is text, not commands, and a redirection may follow on its first line. dashes, a list,
    gets whether each is a `<<-`, whose lines the shell reads without their leading tabs.

    It reads them as the regex
    `<<-?[ \\t]*(['"]?)([A-Za-z_][\\w.-]*)\\1([^\\n]*)\\n((?:.*?\\n)?)[ \\t]*\\2[ \\t]*(?=\\n|$)` (re.S) did with re.sub,
    quirks included (test_cq_write.py checks it against that regex), in near-linear time, at most about n^1.5: the
    regex scanned to the end for each `<<name` with no end line, once per prefix of the name, and this tries each line
    length up to the name's once. So: the end line is the first line after the body's first line that is the name
    (spaces and tabs around it), else that first line itself; an unquoted name with no end line tries its prefixes, longest first; a `<<` with none is left as it is."""
    ends, offset = {}, 0  # each line, stripped of spaces and tabs: the offsets where it starts, in order
    for line in text.split("\n"):
        ends.setdefault(line.strip(" \t"), []).append(offset)
        offset += len(line) + 1
    sizes = sorted({len(line) for line in ends if line})
    out, kept, start = [], 0, text.find("<<")
    while start >= 0:
        found = _heredoc(text, start, ends, sizes)
        if not found:
            start = text.find("<<", start + 1)
            continue
        quote, rest, body, end = found
        if dashes is not None:
            dashes.append(text.startswith("-", start + 2))
        out += [text[kept:start], replace(quote, rest, body)]
        kept, start = end, text.find("<<", end)
    return "".join(out) + text[kept:]


def _heredoc(text: str, start: int, ends: dict, sizes: list) -> "tuple | None":
    """The heredoc whose `<<` is at start: (quote, rest of its first line, body, where its end line ends), or None."""
    i = start + 2 + text.startswith("-", start + 2)
    while text.startswith((" ", "\t"), i):
        i += 1
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
        return quote, text[name.start() + size + len(quote):newline], text[first:last], len(text) if stop < 0 else stop
    return None


def _heredoc_end(text: str, start: int, ends: dict, sizes: list) -> "int | None":
    """Where the heredoc heredocs() reads at start ends (its end line's end), or None."""
    found = _heredoc(text, start, ends, sizes)
    return found[3] if found else None


def heredoc_doubt(text: str, end_of=_heredoc_end, word=HEREDOC_NAME) -> "str | None":
    """Why heredocs() may read the text's heredocs otherwise than the shell, or None. It visits each `<<` heredocs()
    does, in one pass that follows quotes (nested in `${ }` too), comments, arithmetic (`(( ))`, `$(( ))`, `$[ ]`),
    `( )`, `$( )`, `${ }` and backticks. A heredoc is read as the shell reads it only in code outside `${ }`, with a plain end word (`EOF`, `'EOF'`, `"EOF"`), a first line
    that closes what it opens, holds no other heredoc and goes on past no backslash, and an end line that is the word
    alone (after tabs, for `<<-`) and the first such line. A `case` pattern's `)` inside `$( )` closes it early here.
    guard_full_suite.py asks the same of its own reading: end_of(text, start, ends, sizes), where the heredoc it reads
    at start ends, and word, the end words it reads."""
    if "<" not in text:
        return None  # no heredoc to misread
    ends, offset = {}, 0
    for line in text.split("\n"):
        ends.setdefault(line.strip(" \t"), []).append(offset)
        offset += len(line) + 1
    sizes = sorted({len(line) for line in ends if line})
    stack, depth = ["code"], []  # the open contexts; the open parentheses (or brackets) of each arithmetic one
    braces = 0  # how many `${` (and `{` inside one) are open: a `<<` inside one is no heredoc
    # Where the last backslash-newline ends, and the character before it (before a run of them): the shell joins the
    # two, so a `#` there starts a comment only after a space, and `<`, backslash-newline, `<` is a `<<`.
    joined, glue = -1, "\n"
    # On a heredoc's first line: (the newline that ends it, len(stack) at its `<<`, where its end line ends), and the
    # least len(stack) since that `<<`: the line must close what it opens and nothing before.
    pending, floor = None, 0
    i, n = 0, len(text)
    while i < n:
        if pending and len(stack) < floor:
            floor = len(stack)
        top = stack[-1]
        kind = "code" if top in CODE else top
        found = NEXT[kind].search(text, i, pending[0] if pending else n)
        if not found:
            if not pending:
                return None
            if stack[-1] == "#":
                stack.pop()  # the newline ends a comment
            if len(stack) != pending[1] or min(floor, len(stack)) < pending[1]:
                return "a heredoc's first line leaves a quote or a parenthesis open"
            i, pending = pending[2], None
            continue
        i, char = found.start(), found.group()
        if char == "<":
            if not text.startswith("<<", i):
                i += 1
                continue
            run = text.startswith("<", i + 2) or (i > 0 and text[i - 1] == "<")
            if pending:  # heredocs() reads none on a heredoc's first line
                if kind == "code" and not braces and not run and _end_word(text, i) is not None:
                    return "two heredocs on one line"
                i += 1
                continue
            read = end_of(text, i, ends, sizes)
            if kind != "code" or braces or run:
                if read:
                    return "a `<<` in quotes, a `${ }`, a comment, arithmetic or a `<<<`"
                i += 1
                continue
            j = _end_word(text, i)
            newline = text.find("\n", i)
            if j is None or newline < 0:
                i += 1  # no end word (the shell refuses the line), or no line after it: no body to misread
                continue
            quote = text[j] if text[j] in "'\"" else ""
            name = word.match(text, j + len(quote))
            after = name.end() + len(quote) if name else j
            if not name or not text.startswith(quote, name.end()) or (after < n and text[after] not in TERMINATOR):
                return "a heredoc's end word is more than a name"
            if not read:
                if NOT_SPACE.search(text, newline):
                    return "a heredoc with no end line, whose body runs to the end"
                i += 1
                continue
            first, end = newline + 1, read
            last = text.rfind("\n", 0, end) + 1
            dash = text.startswith("-", i + 2)

            def ends_it(line: str) -> bool:
                return (line.lstrip("\t") if dash else line) == name.group()

            if not ends_it(text[last:end]):
                return "a heredoc's end line is more than its end word"
            if last > first and ends_it(text[first:text.find("\n", first)]):
                return "an empty heredoc whose end word comes again later"
            if not quote and text.find("\\\n", first, end) >= 0:
                return "an unquoted heredoc's body goes on past a backslash, which may end it on another line"
            pending, floor, i = (newline, len(stack), end), len(stack), after
            continue
        if char == "\\":
            if pending and i + 1 == pending[0]:
                return "a heredoc's first line goes on past a backslash"
            if text.startswith("<<", i + 1) and not pending and end_of(text, i + 1, ends, sizes):
                return "a `<<` after a backslash"
            if text.startswith("\n", i + 1):
                glue = glue if i == joined else text[i - 1] if i else "\n"
                joined = i + 2
                if kind == "code" and glue == "<" and text.startswith("<", joined):
                    return "a `<<` split by a backslash-newline"
            i += 2
            continue
        i += 1
        if char == "\n":  # in a comment
            stack.pop()
        elif char == "'":
            if kind in ("'", "$'"):
                stack.pop()
            elif top == '"${':
                return "a `'` in a `${ }` in double quotes, a quote to bash and not to zsh"
            else:
                stack.append("'")
        elif char == '"':
            if kind == '"':
                stack.pop()
            else:
                stack.append('"')
        elif char == "`":
            if top == "`":
                stack.pop()
            else:
                stack.append("`")
        elif char == "#":
            before = glue if i - 1 == joined else text[i - 2] if i > 1 else "\n"
            if before in " \t\n;&|()" and top not in BRACES:
                stack.append("#")
        elif char == "$":
            if text.startswith("((", i):
                stack.append("((")
                depth.append(2)
                i += 2
            elif text.startswith("(", i):
                stack.append("$(")
                i += 1
            elif text.startswith("{", i):
                stack.append('"${' if kind == '"' or top == '"${' else "${")
                braces += 1
                i += 1
            elif text.startswith("[", i):
                stack.append("$[")
                depth.append(1)
                i += 1
            elif text.startswith("'", i) and kind != '"' and top != '"${':
                stack.append("$'")
                i += 1
        elif char == "{":
            if top in BRACES:  # the shells count the braces inside one (`${x:-{a}}` is `{a}`)
                stack.append(top)
                braces += 1
        elif char == "}":
            if top in BRACES:
                stack.pop()
                braces -= 1
        elif char in "[]":  # in `$[ ]`
            depth[-1] += 1 if char == "[" else -1
            if not depth[-1]:
                stack.pop()
                depth.pop()
        elif char == "(":
            if kind == "((":
                depth[-1] += 1
            elif text.startswith("(", i):
                stack.append("((")
                depth.append(2)
                i += 1
            else:
                stack.append("(")
        elif char == ")":
            if kind == "((":
                depth[-1] -= 1
                if not depth[-1]:
                    stack.pop()
                    depth.pop()
            elif top in ("(", "$("):
                stack.pop()
    return None


def _end_word(text: str, start: int) -> "int | None":
    """Where the end word of a `<<` at start begins, or None if no word follows it on its line."""
    j = start + 2 + text.startswith("-", start + 2)
    while text.startswith((" ", "\t"), j):
        j += 1
    return None if j >= len(text) or text[j] in "\n;&|()<>" else j


def tokens(command: str, scope: Scope, joined: bool = True, exact: bool = False, escaped: str = "") -> list:
    """The command's shell tokens (quotes removed), without comments; ValueError if unbalanced. A heredoc's body
    becomes one word, HEREDOC_WORD, if it names a live file (`python3 - <<'EOF'` with the path inside), else none; so
    does a here-string's text (`python3 <<< "..."`), after it.
    Joined, a backslash-newline outside single quotes joins the words around it, as in the shell (`s\\<newline>ed` is
    sed); otherwise, and in single quotes, it reads as a space. Each reading
    also takes for a space a newline after an escaped backslash (`echo \\\\<newline>rm ...`), which ends the line; exact
    keeps it a newline, as the shell does. Each character in escaped, escaped (`\\(`, `\\;`, `\\|`), is a word, as a
    quoted `'('` is; shlex otherwise makes it a bare one that splits the command or reads as a redirection (`rm \\|
    <live>`)."""

    def body(quote, rest, text):
        return f" {HEREDOC_WORD if scope.mentioned(text) else ''} {rest}"

    def step(found):
        if found[0].startswith("#"):
            return ""
        text = found[0]
        if joined and not text.startswith("'"):
            text = CONTINUATION.sub(lambda pair: "" if pair[1] == "\n" else pair[0], text)
        if len(text) == 2 and text[0] == "\\" and text[1] in escaped:  # find's `\( -name x \)`, `-exec ... \;`
            return "'_'"
        return "'_'" if QUOTED_PUNCTUATION.match(text) else text  # a quoted `>` is no redirection

    text = (COMMENT_OR_QUOTED if joined else SPACED).sub(step, heredocs(command, body))
    if not exact:  # step() has taken each backslash-newline the shell does; one left follows an escaped backslash
        text = text.replace("\\\n", " ")
    lexer = shlex.shlex(text.replace("\n", " ; "), posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    lexer.commenters = ""
    words = []
    for word in lexer:
        words.append(word)
        if len(words) > 1 and words[-2].endswith("<<<") and scope.mentioned(word):
            words.append(HEREDOC_WORD)  # a here-string's text is its program's stdin, as a heredoc's body is
    return words


def substitutions(command: str, scope: Scope) -> list:
    """The commands inside each `$(...)` and backtick pair the shell runs (a nested one stays inside its outer one):
    not in single quotes or a quoted heredoc's body. A heredoc that names a live file becomes HEREDOC_WORD, as in
    tokens(), so `$(python3 - <<'EOF' ...)` keeps it."""
    bodies = []

    def body(quote, rest, text):
        if not quote:
            bodies.append(text)  # an unquoted heredoc's body runs its substitutions
        return f" {HEREDOC_WORD if scope.mentioned(text) else ''} {rest}"

    text = heredocs(command, body)
    return _substitutions(text, quotes=True) + [s for b in bodies for s in _substitutions(b, quotes=False)]


def _substitutions(text: str, quotes: bool) -> list:
    found, i, double = [], 0, False
    while i < len(text):
        char = text[i]
        if char == "\\":
            i += 2
            continue
        if quotes and char == '"':
            double = not double
        elif quotes and char == "'" and not double:
            end = text.find("'", i + 1)
            i = len(text) if end < 0 else end + 1
            continue
        elif text.startswith("$(", i) or (not double and text.startswith(("<(", ">("), i)):  # and `<(...)`, `>(...)`
            depth, j = 1, i + 2
            while j < len(text) and depth:
                depth += {"(": 1, ")": -1}.get(text[j], 0)
                j += 1
            found.append(text[i + 2:j - 1] if depth == 0 else text[i + 2:])
            i = j
            continue
        elif char == "`":
            end = text.find("`", i + 1)
            end = len(text) if end < 0 else end
            found.append(text[i + 1:end])
            i = end + 1
            continue
        i += 1
    return found


def redirection(token: str) -> bool:
    return operator(token) and ("<" in token or ">" in token)


def truncates(token: str) -> bool:
    """A redirection that may write a file from its start: `>`, `>|`, `&>`, `>&`, `<>`; not `>>`, `&>>` or `<`."""
    return ">" in token and ">>" not in token


def simple_commands(words: list) -> tuple:
    """The words of each simple command, every redirection with its target, in order, and for each command the
    operators before it (since the command before) and the one after it, for places()."""
    commands, current, redirections, joins = [], [], [], []
    before = []

    def close(op):
        nonlocal current, before
        if current:
            commands.append(current)
            joins.append((before, op))
            before = []
        before.append(op)
        current = []

    i = 0
    while i < len(words):
        word = words[i]
        if redirection(word):
            target = words[i + 1] if i + 1 < len(words) else ""
            if word.endswith(">") and target.startswith("!"):  # zsh's `>!` writes past noclobber, as `>|` does
                word, target = word + "!", target[1:]
                if not target:  # `>! F`: the file is the next word
                    i += 1
                    target = words[i + 1] if i + 1 < len(words) else ""
            redirections.append((word, target))
            if current and FD.match(current[-1]):  # the fd of `2>&1`: shlex splits it off as a word
                current.pop()
            plain = word.replace(">|", ">")  # `>|` writes; it isn't a pipe
            if set(plain) & set(";()|") or "&&" in plain:
                close(plain)
            i += 2
            continue
        if operator(word):
            close(word)
        else:
            current.append(word)
        i += 1
    close("")
    return commands, redirections, joins


def spliced(words: list) -> list:
    """The words with each unquoted `$(...)` or `$((...))` cut out but its `$`. shlex splits `$(echo rm) <it>` into
    `$`, `(`, `echo`, `rm`, `)`, `<it>`, and `sed -i '' $(true) s/a/b/ <it>` likewise, where the shell runs one
    command, `$ <it>` or sed's; what the substitution runs is read by
    substitutions()."""
    out, i = [], 0
    while i < len(words):
        out.append(words[i])
        i += 1
        if not (out[-1].endswith("$") and not operator(out[-1]) and i < len(words) and operator(words[i])
                and words[i].startswith("(")):
            continue
        depth = 0
        while i < len(words):
            if operator(words[i]):
                for k, char in enumerate(words[i]):
                    depth += {"(": 1, ")": -1}.get(char, 0)
                    if depth <= 0:
                        if words[i][k + 1:]:
                            out.append(words[i][k + 1:])  # `);` or `)>`: what follows the `)` stays
                        break
            i += 1
            if depth <= 0:
                break
    return out


def defines_function(words: list) -> bool:
    """Whether the words define a shell function, `f()` or `f ( )` (`function f` is a program, function)."""
    return any(operator(word) and (word.startswith("()") or (word == "(" and words[i + 1:i + 2] == [")"]))
               and i and not operator(words[i - 1]) and not words[i - 1].endswith("$")
               for i, word in enumerate(words))


def folder_effect(words: list) -> tuple:
    """What a simple command does to the shell's folder: ('move', its arguments) for cd or pushd, ('still', [])
    for one in STILL or only assignments, else ('unknown', [])."""
    i = 0
    while i < len(words) and ASSIGNMENT.match(words[i]):
        i += 1
    if i == len(words) or words[i] in STILL:
        return "still", []
    return ("move", words[i + 1:]) if words[i] in MOVES else ("unknown", [])


def places(commands: list, joins: list, scope: Scope) -> list:
    """For each simple command, (the folder it runs in, or None if this can't tell; whether a command before it may
    have changed how the shell moves), read from scope.at and scope.unsure. A cd moves only the commands joined to it
    by `&&` in its and-or list, which run only if it went there: past a `;`, a newline or a `&` the shell may be where
    it was, if the cd failed (`cd <checkout>; bun ...` once the checkout has moved, or `false && cd <checkout>; bun
    ...`). A cd in a pipeline, after an `||` or
    right after a `&` moves nothing this can tell. Past an operator not in LISTS (`(`, `)`, `;;`) or a command
    that may move (folder_effect: 'unknown'), nothing is told."""
    out, unsure = [], scope.unsure
    start = chain = after = scope.at  # where this and-or list started, where its next command runs, where it leaves
    moved = either = False  # whether this list has moved, or has an `||`, so far
    for words, (before, op_after) in zip(commands, joins):
        op = before[0] if before else ";"
        if any(o not in LISTS for o in before) or any(o != ";" for o in before[1:]):  # `&&` and a newline: `&&`
            unsure = True
        if op in (";", "&"):
            start = None if op == "&" and moved else (after if op == ";" else start)
            chain, after, moved, either = start, start, False, False
        elif op == "||":  # what runs after it may run where the list started or where a cd before went
            either = True
        here = None if unsure or (moved and either) else chain
        out.append((here, unsure))
        effect, args = folder_effect(words)
        if effect == "unknown":
            unsure = True
        elif effect == "move":
            aside = op in PIPES or op_after in PIPES or (before and before[-1] == "&")
            chain = None if unsure or aside else scope.cd(args, here)
            after, moved = None, True
    return out


def programs(words: list, scope: "Scope | None" = None):
    """Each program a simple command runs, as (the word that names it, as written; its arguments): the first word past
    assignments, keywords, wrappers (nohup, env, timeout, xargs, ...) and a heredoc before it (`<<'EOF' python3`), and,
    given the scope, what find's actions run (find_actions; not inside an action, which keeps the readings few)."""
    i = 0
    while i < len(words):
        word = words[i]
        if ASSIGNMENT.match(word) or word in KEYWORDS or word in DECLARERS or word == HEREDOC_WORD:
            i += 1
        elif os.path.basename(word) in WRAPPERS:
            i += 1
            while i < len(words) and (words[i].startswith("-") or ASSIGNMENT.match(words[i])
                                      or WRAPPER_VALUE.match(words[i])):
                i += 1
        else:
            break
    if i >= len(words):
        return
    yield words[i], words[i + 1:]
    if scope is not None:
        yield from find_actions(words[i:], scope)


def found_files(words: list, scope: Scope) -> list:
    """The ceo-questions.md a find may reach, one in each folder it starts from (`.` if it names none). find searches
    the folders below too, so one that holds a live folder (`find ~ ...`), or a glob or brace may make any folder, may
    reach a live one: `<root>/workspaces/ceo-questions.md`."""
    rest = words[1:]
    while rest and FIND_OPTIONS.match(rest[0]):
        rest = rest[1:]
    folders = []
    for i, word in enumerate(rest):
        if word.startswith(("-", "(", "!")):
            break
        if word == "_" and (i + 1 == len(rest) or rest[i + 1].startswith(("-", "(", "!"))):
            break  # a quoted or escaped `(` (tokens) before find's expression; any other `_` (a `;`) is a folder too,
            # and find walks the ones after it
        folders.append(word)
    found = []
    for folder in folders or ["."]:
        start = os.path.expanduser(expand(folder, scope.values))
        above = os.path.realpath(start).casefold().rstrip("/") + "/"
        if any(c in start for c in "*?[{") or (start.startswith("/") and any(live.startswith(above)
                                                                              for live in scope.live)):
            found.append(os.path.join(live_folders(scope.root)[0], NAME))
        else:
            found.append(folder.rstrip("/") + "/" + NAME)
    return found


def find_actions(words: list, scope: Scope):
    """What each -exec, -execdir, -ok and -okdir in these words runs (find's, or any program's), as programs() yields
    it. When find's words before an action name a ceo-questions.md, its `{}` is each of found_files. An action is read
    to the end of the command, and also up to each word that may end it: `;` (a quoted `';'` reads as `_`) or a `+` after `{}`; so `find /tmp/s -name ceo-questions.md
    -exec cp {} <content/> ';'` puts the copy where the live one is."""
    mentions = False
    for j in range(1, len(words)):
        mentions = mentions or bool(MENTION.search(words[j - 1]))
        if words[j] not in FIND_ACTIONS or j + 1 == len(words):
            continue
        action = words[j + 1:]
        ends = [k for k in range(1, len(action)) if action[k] == "_" or (action[k] == "+" and action[k - 1] == "{}")]
        for path in dict.fromkeys(found_files(words, scope)) if mentions else [None]:
            filled = [word.replace("{}", path) for word in action] if path else action
            for end in ends + [len(filled)]:
                yield from programs(filled[:end])


def sed_in_place(args: list) -> bool:
    if any(arg == "--in-place" or arg.startswith("--in-place=") for arg in args):
        return True
    for arg in args:
        if not arg.startswith("-") or arg.startswith("--"):
            continue
        for letter in arg[1:]:
            if letter in "iI":  # BSD sed's -I edits in place too
                return True
            if letter in "efl":  # the rest of the word is this option's value
                break
    return False


def _script(arg: str, scope: Scope, script: str) -> bool:
    """Whether arg is root's scripts/<script>, relative to cwd or (by habit) to root, or absolute."""
    want = os.path.realpath(os.path.join(scope.root, "scripts", script))
    here = os.path.realpath(os.path.join(scope.cwd or scope.root, arg))
    if here != want and os.path.exists(here):  # the cwd's own script of that name: a product repo's
        return False
    return here == want or os.path.realpath(os.path.join(scope.root, arg)) == want


def excepted(name: str, args: list, scope: Scope) -> bool:
    """The interpreter calls this file allows: cq_archive, and the runbooks' two named exceptions."""
    rest = list(args)
    if name in ("python3", "python"):
        while rest and rest[0] in SAFE_PYTHON_FLAGS:
            rest = rest[1:]
        if rest and _script(rest[0], scope, "cq_archive.py"):
            return True
        # The second opinion only reads its --file and --brief; it writes only its own call log and answers.
        if rest and _script(rest[0], scope, "second_opinion.py"):
            return True
    if name == "bun" and rest and deploy_script(rest[0], scope):
        # The deploy script's `--ceo-questions <path>`, which it only reads.
        return all(not scope.mentioned(arg) or arg.startswith("--ceo-questions=") or rest[i - 1] == "--ceo-questions"
                   for i, arg in enumerate(rest[1:], start=1))
    return False


def deploy_name(root: str) -> "str | None":
    """The deploy script's file name in company.json at root, or None: none named, or a file this can't read."""
    try:
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        import company_config  # here, so only a command that may be a deploy reads it

        settings = company_config.integration("question_files", root)
        name = None if settings is None else settings.get("deploy_script")
    except TooSlow:
        raise
    except Exception:  # noqa: BLE001 - a file it can't read names none
        return None
    return name if isinstance(name, str) and re.fullmatch(r"[\w.-]+\.[a-z]+", name) else None


def deploy_script(arg: str, scope: Scope) -> bool:
    """Whether arg is a product checkout's own scripts/<deploy script>: a file under the live workspaces/ (its real path),
    in a `scripts` folder beside the checkout's `.git`. A relative path is read from the folder the command's `cd` moved
    to (`cd <checkout> && bun scripts/<deploy script> ...`), so one under `/tmp` is refused. The path as written, before
    the folder, must have that name and folder too, so `bun <deploy script>` from scripts/, `../<deploy script>`,
    `$D/<deploy script>` and a link to the script are refused; and it may hold no variable or `~`, whose value a later
    `${D::=x}` or `HOME=x` may have changed."""
    name = deploy_name(scope.root)
    if name is None:
        return False
    shown = os.path.normpath(arg)
    if os.path.basename(shown) != name or os.path.basename(os.path.dirname(shown)) != "scripts":
        return False
    if "$" in arg or "`" in arg or arg.startswith("~") or (scope.at is None and not arg.startswith("/")):
        return False
    written = os.path.normpath(os.path.join(scope.at or "/", arg))
    if os.path.basename(written) != name or os.path.basename(os.path.dirname(written)) != "scripts":
        return False
    path = os.path.realpath(os.path.join(scope.at or "/", arg))
    scripts = os.path.dirname(path)
    return (os.path.basename(path) == name and os.path.basename(scripts) == "scripts"
            and os.path.isfile(path) and os.path.exists(os.path.join(os.path.dirname(scripts), ".git"))
            and any(path.casefold().startswith(folder) for folder in scope.live))


def copy_reason(name: str, args: list, scope: Scope) -> "str | None":
    """cp, mv and their kin: onto a live ceo-questions.md, or a file of that name into a folder that may hold the live
    one."""
    folder = None
    if name.lower() in ("cp", "gcp", "install", "ln", "mv"):  # GNU's `-t <folder>` (Linux sessions); BSD's have none
        for i, arg in enumerate(args):
            if arg in ("-t", "--target-directory") and i + 1 < len(args):
                folder, args = args[i + 1], args[:i] + args[i + 2:]
                break
            if arg.startswith("--target-directory="):
                folder, args = arg.split("=", 1)[1], args[:i] + args[i + 1:]
                break
    operands = [a for a in args if not a.startswith("-") and a != HEREDOC_WORD]
    if folder is not None:
        operands.append(folder.rstrip("/") + "/")
    if not operands:
        return None
    if scope.mentioned(operands[-1]):
        return f"{name} writes over a ceo-questions.md"
    if not any(MENTION.search(a) or scope.mentioned(a) for a in operands[:-1]):
        return None
    target = expand(operands[-1], scope.values)
    if any(c in target for c in "$`*?[{"):  # a variable, `$(...)`, backtick, glob or brace may make it any folder
        return (f"{name} puts a ceo-questions.md into a folder where it may replace the live one (a `$`, backtick, "
                "glob or brace in the target may make it any folder: write the target out)")
    if target.startswith("/") and not scope.may_be_live(target.rstrip("/") + "/" + NAME):
        return None
    if os.path.basename(target.rstrip("/")).lower() in ("content", ".", "..", ""):
        return f"{name} puts a ceo-questions.md into a folder where it may replace the live one"
    # Any other folder that may hold a live one, an order's own (`orders/<directive id>/<n>/`) too, read from where the
    # command runs: one written as a folder (a trailing `/`, `-t`, two
    # sources or more), one that exists or one of LAYOUT's, or a relative one after a cd this can't follow. Another
    # file's name is no folder, nor is a `_`: find's quoted `;`, where its action is read to the end (find_actions).
    if target == "_":
        return None
    place = target if target.startswith(("/", "~")) else os.path.join(scope.at, target) if scope.at else None
    if place is None:
        return (f"{name} puts a ceo-questions.md into a folder where it may replace the live one (a relative target "
                "after a cd this can't follow: write the target out)")
    folder = (target.endswith("/") or len(operands) > 2 or os.path.isdir(os.path.expanduser(place))
              or in_layout(os.path.expanduser(place), scope))
    if folder and scope.may_be_live(place.rstrip("/") + "/" + NAME):
        return f"{name} puts a ceo-questions.md into a folder where it may replace the live one"
    return None


def holds_live(word: str, scope: Scope) -> bool:
    """Whether a path a remover names may hold a live ceo-questions.md: a folder at or above a live workspaces/, or one
    of LAYOUT's folders below it (a product's, its content/, orders/ or orders-closed/, a directive's or an order's)
    that holds one (any such folder when that workspaces/ doesn't exist, as in a test), a glob any of whose matches
    does, or a path this can't read (a `$`, backtick or brace left, `~` when the command may set HOME, a relative one
    after a cd this can't follow)."""
    path = expand(word, scope.values)
    if "$" in path or "`" in path or "{" in path or (scope.home and path.startswith("~")):
        return True
    path = os.path.expanduser(path)
    if not path.startswith("/"):
        if scope.at is None:
            return True
        path = os.path.join(scope.at, path)
    if any(c in path for c in "*?["):
        parts = path.split("/")
        base = "/".join(parts[:next(i for i, part in enumerate(parts) if any(c in part for c in "*?["))]) or "/"
        return held(base, scope) if not os.path.isdir(base) else any(held(found, scope) for found in glob.glob(path))
    return held(path, scope)


def below_live(path: str, scope: Scope):
    """(the path's real form, its parts below a live workspaces/, that folder) for each live one it is below; parts
    None for one it is at or above."""
    real = os.path.realpath(path)
    folded = real.casefold().rstrip("/") + "/"
    for live, folder in zip(scope.live, live_folders(scope.root)):
        if live.startswith(folded):
            yield real, None, folder
        elif folded.startswith(live):
            yield real, real[len(folder) + 1:].rstrip("/").split("/"), folder


def layout_steps(parts: list):
    """Each of LAYOUT's patterns, as its parts, whose first parts the path's match."""
    for steps in (pattern.split("/") for pattern in LAYOUT):
        if len(parts) < len(steps) and all(fnmatch.fnmatchcase(part.casefold(), step)
                                           for part, step in zip(parts, steps)):
            yield steps


def held(path: str, scope: Scope) -> bool:
    """holds_live for a path without a glob; a live file itself, as a glob's match, is held too."""
    for real, parts, folder in below_live(path, scope):
        if parts is None or any(len(parts) == len(steps) and all(fnmatch.fnmatchcase(part.casefold(), step)
                                                                 for part, step in zip(parts, steps))
                                for steps in (pattern.split("/") for pattern in LAYOUT)):
            return True
        for steps in layout_steps(parts):
            if not os.path.isdir(folder) or glob.glob(os.path.join(real, *steps[len(parts):])):
                return True
    return False


def in_layout(path: str, scope: Scope) -> bool:
    """Whether a path is a folder LAYOUT puts a live ceo-questions.md in (a product's content/, an order's own), as
    written: it needn't exist."""
    return any(parts is not None and any(len(steps) == len(parts) + 1 for steps in layout_steps(parts))
               for _, parts, _ in below_live(path, scope))


def recursive(args: list) -> bool:
    """Whether rm's or srm's options, before a `--`, may take a folder with what it holds: -r or -R, alone or in a
    cluster, or --recursive or a prefix of it, as GNU's rm takes one (`--rec`), or any word there the shell expands
    (not LITERAL: `-{r,}`, `-$X`, `$'-r'` may each become -r)."""
    return any(not LITERAL.fullmatch(arg) or re.fullmatch(r"-[A-Za-z]*[rR][A-Za-z]*", arg)
               or len(arg) > 2 and "--recursive".startswith(arg)
               for arg in (args[:args.index("--")] if "--" in args else args))


def folder_reason(name: str, args: list, scope: Scope, depth: int, stdin_runs: bool) -> "str | None":
    """Why this program may remove or move a folder that holds a live ceo-questions.md (holds_live), named in the
    command or not: rm, srm or trash of it, mv of it (not into it), rsync's `--delete` into it, find's `-delete` or a
    remover in its actions from it, a remover xargs feeds, or one of these in a shell's `-c`, eval's or a trap's text
    (`rm -r content/orders/<directive id>` would take every running
    order's file with it). An rm or srm that isn't recursive (recursive) takes no folder that holds a file, so a path
    it names with nothing the shell expands (LITERAL: `rm slot-2/owner`, from a folder this can't place) is none of
    this check's, whatever the cwd; the live file's own name is the name check's.
    In a command with a zsh glob group (GLUED_PAREN) each such path is read as a glob."""
    lowered = name.lower()
    if lowered in SHELLS or lowered in ("eval", "trap"):
        inner = copy.copy(scope)
        if lowered in SHELLS:
            inner.values = {}  # a new shell has only the exported variables, which this doesn't follow
            texts = [args[i + 1] for i, arg in enumerate(args[:-1]) if SHELL_STRING_FLAG.match(arg)][:1]
        else:
            texts = [" ".join(args)] if lowered == "eval" else args
            if lowered == "trap":
                inner.at, inner.unsure = None, True  # a trap's commands run later, wherever the shell is by then
        return next(filter(None, (command_reason(text, scope.cwd, scope.root, depth + 1, inner)
                                  for text in texts)), None)
    if lowered not in FOLDER_PROGRAMS:
        return None
    operands = [a for a in args if not a.startswith("-") and a not in (HEREDOC_WORD, "{}")]  # `{}`: find's, below
    if lowered in ("find", "gfind"):
        removes = "-delete" in args or any(arg in FIND_ACTIONS and i + 1 < len(args)
                                           and os.path.basename(args[i + 1]).lower() in FOLDER_PROGRAMS | REMOVERS
                                           for i, arg in enumerate(args))
        operands = [os.path.dirname(path) or "." for path in found_files([name] + args, scope)] if removes else []
    elif stdin_runs:
        return f"{name} behind xargs may remove a folder that holds a ceo-questions.md (its operands come from stdin)"
    elif lowered == "rsync":  # --delete empties its target; --remove-source-files (or its old name) takes what it sends
        operands = ((operands[:-1] if any(a in ("--remove-source-files", "--remove-sent-files") for a in args) else [])
                    + (operands[-1:] if any(a.startswith("--delete") for a in args) else []))
    elif lowered == "mv" and not any(a in ("-t", "--target-directory") or a.startswith("--target-directory=")
                                     for a in args):
        operands = operands[:-1]  # where it moves them to keeps what it holds
    elif lowered in ("rm", "srm") and not recursive(args):  # it takes no folder that holds a file
        # a word the shell expands stays (recursive reads only the words before `--`: `rm -f -- "$F"`); in a command
        # with a zsh glob group, a LITERAL one too, read as the glob it may start (`content/` of
        # `content/(c|x)eo-questions.md`; GLUED_PAREN)
        operands = [operand + "*" if scope.glued and LITERAL.fullmatch(operand) else operand
                    for operand in operands if scope.glued or not LITERAL.fullmatch(operand)]
    if any(holds_live(operand, scope) for operand in operands):
        return f"{name} removes or moves a folder that holds a ceo-questions.md"
    return None


def program_reason(name: str, args: list, scope: Scope, depth: int, later: "list | None" = None) -> "str | None":
    """Why this program, in a simple command that names a live ceo-questions.md, may not run, or None. A shell's
    `-c`, eval's, a trap's or an alias's text hands its folder_reason to later, as a substitution's does, when the
    outermost command names the file (scope.defer: then a read still going at the timer is refused, cq_reason), so an
    older reason later in the command is told first."""
    lowered = name.lower()
    later = later if scope.defer else None
    if lowered in SHELLS:
        inner = copy.copy(scope)
        inner.values = {}  # a new shell has only the exported variables, which this doesn't follow
        for i, arg in enumerate(args[:-1]):
            if SHELL_STRING_FLAG.match(arg):
                return command_reason(args[i + 1], scope.cwd, scope.root, depth + 1, inner, later)
        return f"{name} runs a script with a ceo-questions.md in its command"
    if lowered == "eval":
        return command_reason(" ".join(args), scope.cwd, scope.root, depth + 1, scope, later)
    if lowered in ("trap", "alias"):
        # A trap's commands run later, in this shell, as eval's do, and zsh runs an alias's on a later line: wherever
        # the shell is by then.
        scope.at, scope.unsure = None, True
        texts = args if lowered == "trap" else [a.split("=", 1)[1] for a in args if "=" in a]
        return next(filter(None, (command_reason(a, scope.cwd, scope.root, depth + 1, scope, later) for a in texts)),
                    None)
    if INTERPRETER.match(lowered):
        if excepted(lowered, args, scope):
            return None
        deploy = deploy_name(scope.root) if lowered == "bun" and args else None
        return f"{name} runs with a ceo-questions.md in its command" + (
            DEPLOY_HINT.format(name=deploy) if deploy and args[0].endswith(deploy) else "")
    if lowered in ("sed", "gsed") and sed_in_place(args):
        return "sed edits a ceo-questions.md in place"
    if lowered in ("awk", "gawk", "mawk", "nawk"):
        if any(a in ("-i", "--include") or a.startswith(("-i", "--include=")) for a in args):
            return "awk edits a ceo-questions.md in place"
        if any(">" in a and scope.mentioned(a) for a in args):
            return "awk writes into a ceo-questions.md"
        return None
    if lowered in EDITORS:
        return f"{name} edits a ceo-questions.md"
    if lowered in ("tee", "sponge"):
        options = args[:args.index("--")] if "--" in args else args  # after `--`, `-a` is a file
        appends = any(a in ("-a", "--append") or (a.startswith("-") and not a.startswith("--") and "a" in a)
                      for a in options)
        return None if appends else f"{name} without -a rewrites a ceo-questions.md"
    if lowered in COPIERS:
        return copy_reason(name, args, scope)
    if lowered == "dd":
        return "dd writes a ceo-questions.md" if any(a.startswith("of=") and scope.mentioned(a) for a in args) else None
    if lowered in REMOVERS and any(scope.mentioned(a) for a in args):
        return f"{name} moves, removes or truncates a ceo-questions.md"
    if lowered in ("find", "gfind") and "-delete" in args and any(scope.mentioned(path)
                                                                  for path in found_files([name] + args, scope)):
        return f"{name} -delete removes a ceo-questions.md"
    if lowered == "mv":
        return copy_reason(name, args, scope)  # a ceo-questions.md moved into a folder that may hold the live one
    return None


def command_reason(command: str, cwd: str, root: str, depth: int = 0, outer: "Scope | None" = None,
                   later: "list | None" = None) -> "str | None":
    """Why this Bash command may not run, as a subagent's write to a live ceo-questions.md, or None. A substitution's
    folder_reason goes to its outer command's later list, told only after that command's older reasons."""
    seen = command.replace("\\\n", "")  # `ceo-que\<newline>stions.md` is the name to the shell
    named = "ceo-questions" in seen.lower() or bool(outer and any(f"${n}" in seen or f"${{{n}}}" in seen
                                                                   for n in outer.names))
    # One that names only a remover and a folder of the layout is read for folder_reason alone: what it can't read
    # passes, and nothing else in it can be refused (it names no file).
    if not named and not all(words.search(seen) for words in FOLDER_WORDS):
        return None
    if depth > DEPTH:
        return "a ceo-questions.md is named in shells nested too deep to read" if named else None
    if len(command) > LONGEST:
        return (f"a command over {LONGEST:,} characters that names a ceo-questions.md is too long to read in time"
                if named else None)
    doubt = heredoc_doubt(command)
    if doubt:
        return (f"a command that names a ceo-questions.md couldn't be read ({doubt}); write a heredoc as `<<'EOF'`, "
                "its lines, then `EOF` alone on its line") if named else None
    # The shell joins the words around a backslash-newline; the readings that take it for a space, and that take the
    # newline after an escaped backslash for one too, are kept as well (tokens): what any of them refuses is refused.
    readings = [(True, True)] if "\\\\\n" in command else []
    readings += [(True, False), (False, False)] if "\\\n" in command else [(True, False)]
    # An escaped `\(`, `\;` or `\|` is a word to the shell (find's grouping, the end of its action), where shlex leaves
    # a bare `(` that splits the command: each reading is made again with the escaped parentheses words, then
    # with every escaped one, and kept as it was too (tokens).
    escapes = [""]
    if ESCAPED_PAREN.search(command):
        escapes.append("()")
    if ESCAPED_OPERATOR.search(command):
        escapes.append("();<>|&")
    # folder_reason's, told only if no reading finds another reason, by the outermost command
    told, later = later is None, [] if later is None else later
    for joined, exact in readings:
        for escaped in escapes:
            reason = _reason(command, cwd, root, depth, outer, joined, exact, escaped, named, later)
            if reason:
                return reason
    return later[0] if later and told else None


def _reason(command: str, cwd: str, root: str, depth: int, outer: "Scope | None", joined: bool,
            exact: bool, escaped: str = "", names_it: bool = True, later: "list | None" = None) -> "str | None":
    """command_reason's reading of the command, with backslash-newlines joined or not, and escaped punctuation words
    or not (tokens)."""
    scope = Scope(cwd, root, outer.names if outer else None, outer.values if outer else None)
    scope.relative = (outer.relative if outer else True) and not CDPATH.search(command)
    scope.home = (outer.home if outer else False) or bool(HOME.search(command))
    scope.glued = (outer.glued if outer else False) or bool(GLUED_PAREN.search(command.replace("\\\n", "")))
    if outer:  # `cd <checkout> && bash -c "bun scripts/..."` runs where the cd went
        scope.at, scope.unsure = outer.at, outer.unsure
    scope.defer = outer.defer if outer else names_it  # the outermost command's: cq_reason's `named` (program_reason)
    try:
        words = tokens(command, scope, joined, exact, escaped)
        scope.home = scope.home or any(HOME.search(word) for word in words)  # `eval "HO""ME=..."`
        scope.read(words)
        words = tokens(command, scope, joined, exact, escaped)  # again, so a heredoc using its variables counts
    except ValueError:
        return "a command that names a ceo-questions.md couldn't be read (unbalanced quotes)" if names_it else None
    inner = substitutions(command, scope)
    start = scope.at, scope.unsure
    scope.at, scope.unsure = None, True  # a substitution may run after a `cd` or a trap this hasn't followed yet
    for text in inner:  # `echo "$(sed -i ... F)"`: what a substitution runs is a command too
        reason = command_reason(text, scope.cwd, scope.root, depth + 1, scope, later)
        if reason:
            return reason
    scope.at, scope.unsure = start
    scope.hidden = hidden = any(scope.mentioned(text) for text in inner)
    # The simple commands as shlex splits them, and as the shell runs them around a `$(...)` (spliced).
    readings = [simple_commands(words)] + ([simple_commands(spliced(words))] if spliced(words) != words else [])
    for _, redirections, _ in readings:
        for op, target in redirections:
            if truncates(op) and (scope.mentioned(target) or (hidden and HIDDEN.search(target))):
                return f"`{op}` rewrites a ceo-questions.md whole"
    live_anywhere, defines = False, defines_function(words)
    for commands, _, joins in readings:
        scope.at, scope.unsure = start
        for words_of_one, place in zip(commands, places(commands, joins, scope)):
            scope.at, scope.unsure = place  # where it runs: a relative deploy script, an inner `bash -c`, eval or trap
            named = any(scope.mentioned(w) or (hidden and HIDDEN.search(w)) for w in words_of_one
                        if w != HEREDOC_WORD)
            live = named or HEREDOC_WORD in words_of_one
            live_anywhere = live_anywhere or live
            stdin_runs = any(os.path.basename(w) == "xargs" for w in words_of_one)  # stdin becomes its operands
            for program, args in programs(words_of_one, scope):
                name = os.path.basename(program)
                lowered = name.lower()
                defines = (defines or lowered == "function" or (lowered == "alias" and any("=" in a for a in args))
                           or (lowered in ("eval", "trap") and bool(DEFINES.search(" ".join(args)))))
                copies = (lowered in COPIERS or lowered == "mv") and any(MENTION.search(a) for a in args)
                if live and ("$" in program or "`" in program):  # `$X <it>`, `$(echo rm) <it>`: any program
                    shown = "$(...)" if program == "$" else program  # shlex splits `$(echo rm)` after its `$`
                    reason = f"a program named by a variable or substitution ({shown}) runs on a ceo-questions.md"
                elif live and not named and not (INTERPRETER.match(lowered) or lowered in SHELLS
                                                 or lowered in EDITORS or stdin_runs):
                    # Only a heredoc's or here-string's text names it: tee, cp and their kin write only their
                    # operands, which may still put a scratch copy where the live one is.
                    reason = copy_reason(name, args, scope) if copies else None
                elif live:
                    if hidden and any(HIDDEN.search(a) for a in args):
                        args = args + [NAME]  # what a substitution hides may be the file
                    reason = program_reason(name, args, scope, depth, later)
                elif copies:
                    reason = copy_reason(name, args, scope)  # a scratch copy put where the live one is
                else:
                    reason = None
                if reason:
                    return reason
                if (later is not None and not later
                        and not (live and (lowered in SHELLS or lowered in ("eval", "trap")))):
                    later.extend(filter(None, [folder_reason(name, args, scope, depth, stdin_runs)]))  # program_reason
                    # read a live shell's, eval's and trap's text inside
    if live_anywhere and defines:  # zsh runs an alias on a later line, and a function runs where it's called
        return "a command that names a ceo-questions.md defines an alias or a function, which may run anything"
    return None


def script_file(name: str, args: list) -> "str | None":
    """The script file an interpreter or shell runs, as written: its first operand past its options and a `run` (bun,
    deno, uv); npx, bunx, uvx and `uv run` may name an interpreter first (`npx tsx x.ts`, `uv run python x.py`). None
    when an option gives code, a module or stdin instead (`-c`, `-e`, `-m`, `-p`, `-r`, a shell's `-s`, `-`,
    `--eval`), or no operand follows. An option's separate value, but -W's and -X's (python) and -o's and -O's
    (shells), reads as the operand."""
    lowered = name.lower()
    shell = lowered in SHELLS
    stops, values = ("cs", "oO") if shell else ("cempr", "WX")
    rest = list(args)
    while rest:
        word = rest.pop(0)
        if word == "--":
            return rest[0] if rest else None
        if word == "-" or word.startswith(("--eval", "--print", "--command", "--module")):
            return None
        if word.startswith("--"):
            continue
        if word.startswith("-") or (shell and word.startswith("+")):
            for i, letter in enumerate(word[1:], start=2):
                if letter in stops:
                    return None
                if letter in values:
                    if i == len(word) and rest:
                        rest.pop(0)  # its value is the next word
                    break
            continue
        if word == "run" and lowered in ("bun", "deno", "uv"):
            continue
        if lowered in RUNNERS:
            program = os.path.basename(word).lower()
            if INTERPRETER.match(program) or program in SHELLS:
                return script_file(program, rest)
            return word if lowered == "uv" else None  # `uv run x.py`; npx's first operand is a package
        return word
    return None


def checked_in(path: str, scope: Scope) -> bool:
    """Whether a script file is a checkout's own code: a folder above it holds a `.git`, and no live workspaces/ folder
    (gitignored) lies between them. The repo's scripts/, a worktree's and a product checkout's are; a scratch file, and
    one in workspaces/ outside a product checkout, aren't."""
    real = os.path.realpath(path)
    folder = os.path.dirname(real)
    while True:
        if os.path.exists(os.path.join(folder, ".git")):
            top = folder.casefold().rstrip("/") + "/"
            return not any(real.casefold().startswith(live) and live.startswith(top) for live in scope.live)
        parent = os.path.dirname(folder)
        if parent == folder:
            return False
        folder = parent


def script_text(path: str) -> "str | None":
    """The first SCRIPT_BYTES of a file's text (a NUL read as a space), or None if it can't be read."""
    try:
        with open(path, "rb") as file:
            return file.read(SCRIPT_BYTES).decode("utf-8", "replace").replace("\0", " ")
    except OSError:
        return None


def script_reason(command: str, cwd: str, root: str, depth: int = 0, outer: "Scope | None" = None,
                  outer_folders: "list | None" = None) -> "str | None":
    """Why this Bash command may not run, as a subagent's script that names a live ceo-questions.md, or None:
    an interpreter or shell run on a script file (`python3 x.py`, `node x.js`, `bash
    x.sh`, `npx tsx x.ts`, `source x.sh`, or `./x.py` run by its path) whose text names one as a heredoc's does
    (Scope.mentioned: a scratch copy at an absolute path elsewhere is free), unless the script is a checkout's own
    (checked_in) or a named exception (excepted; only at depth 0, a command of its own). It reads each
    subagent Bash command, whether it names the file or not, and the commands in its `$(...)`, backticks, `<(...)`,
    `sh -c` and eval; a relative script from the folder a `cd` joined by `&&` moved to (places), else from the cwd and
    from each folder a cd in the command names. An inner command (outer, outer_folders) keeps the outer's variables,
    runs where it does (a `$(...)`: unknown), and tries a relative script from its own folder and the outer one's cwd
    and FOLDERS latest cd folders too (`cd <scratch>; bash -c
    'python3 x.py'`, `S=<scratch>; echo "$(python3 $S/x.py)"`); where that is unknown, its own cds are followed from
    its cwd as well (guessed). The command's variables find the script, never read its text
    (reader). What it can't read (unbalanced quotes, over 256,000 characters, nested over three levels) passes it:
    command_reason has already refused any such command that names the file."""
    if depth > DEPTH or len(command) > LONGEST:
        return None
    scope = Scope(cwd, root, outer.names if outer else None, outer.values if outer else None)
    # A command's own text sets how its cds move and whether its `~` scripts are skipped; an outer
    # HOME only makes more paths live.
    scope.relative = not CDPATH.search(command)
    own_home = bool(HOME.search(command))
    scope.home = (outer.home if outer else False) or own_home
    if outer:
        scope.at, scope.unsure = outer.at, outer.unsure
    try:
        words = tokens(command, scope)
        scope.read(words)
        inner = substitutions(command, scope)
    except ValueError:
        return None
    bare = Scope(cwd, root, scope.names)  # the names a read without the outer values learns too
    bare.home = scope.home  # (`S=/tmp; echo "$(F=$S/<the file>; bash w.sh)"`), for the reader only: a deeper here-string
    bare.read(words)  # reads by itself
    # A script's text is read without the command's values: the script may set its own (`D=/tmp; bash v.sh`, where
    # v.sh sets D to the live folder).
    reader = Scope(cwd, root, scope.names | bare.names)
    reader.home = scope.home
    commands, _, joins = simple_commands(spliced(words))
    folders = [cwd] + list(outer_folders or [])  # where a relative script may be when places() can't tell
    for words_of_one in commands:
        effect, args = folder_effect(words_of_one)
        if effect == "move" and len(args) == 1 and not set("$`~") & set(args[0]):
            folders.append(os.path.normpath(os.path.join(cwd, args[0])))
    folders = list(dict.fromkeys(folders))
    handed = folders[:1] + folders[1:][-FOLDERS:]  # to an inner command: a bounded list, so the work stays linear
    start = scope.at, scope.unsure
    scope.at, scope.unsure = None, True  # a substitution may run after any cd in the command
    for text in inner:
        reason = script_reason(text, cwd, root, depth + 1, scope, handed)
        if reason:
            return reason
    scope.at, scope.unsure = cwd, False  # an inner command's cds followed from its cwd
    guessed = places(commands, joins, scope)
    scope.at, scope.unsure = start
    for words_of_one, place, guess in zip(commands, places(commands, joins, scope), guessed):
        scope.at, scope.unsure = place
        here = place[0]
        for program, args in programs(words_of_one, scope):
            name = os.path.basename(program).lower()
            flag = next((i for i, arg in enumerate(args[:-1]) if SHELL_STRING_FLAG.match(arg)), None)
            text = " ".join(args) if name == "eval" else args[flag + 1] if name in SHELLS and flag is not None else ""
            reason = text and script_reason(text, here or guess[0] or cwd, root, depth + 1, scope, handed)
            if reason:
                return reason
            direct = False  # a file run by its path (`./x.py`): its `#!` line's interpreter, or a shell, runs it
            if name in SOURCES:
                script = args[0] if args else ""
            elif INTERPRETER.match(name) or name in SHELLS:
                script = script_file(name, args) or ""
            elif "/" in program:
                script, direct = program, True
            else:
                continue
            script = expand(script, scope.values)
            if not script or "$" in script or "`" in script or (own_home and script.startswith("~")):
                continue
            script = os.path.expanduser(script)
            bases = [""] if script.startswith("/") else [here] if here else [g for g in guess[:1] if g] + folders
            for path in (os.path.join(base, script) for base in bases):
                if not os.path.isfile(path) or checked_in(path, scope):
                    continue
                found = script_text(path)
                if found is None or not reader.mentioned(found):
                    continue
                # An exception passes only as a command of its own: inside an inner command it is refused. The deploy
                # form never gets here: its script is a checkout's own (checked_in), and command_reason follows a
                # nested one on purpose.
                if depth == 0 and (any(excepted(n, [program] + args, scope) for n in ("python3", "bun")) if direct
                                   else excepted(name, args, scope)):
                    break
                runs = "a script file run directly" if direct else f"{name} runs a script file"
                deploy = deploy_name(root)
                hint = DEPLOY_HINT.format(name=deploy) if deploy and os.path.basename(script) == deploy else ""
                return f"{runs} whose text names a ceo-questions.md ({script})" + hint
    return None


def ceo_line(line: str) -> bool:
    """Whether a line passes for the CEO's in the capacity scan: it starts `CEO` after spaces, `- ` or `**`, or its
    first parenthesis, or the one right after its first time, starts `(CEO`."""
    if CEO_FIRST.match(line):
        return True
    stamp = CLOCK.search(line)
    after = len(line) - len(line[stamp.end():].lstrip(" \t")) if stamp else -1
    return any(k >= 0 and line.startswith("(CEO", k) for k in (line.find("("), after))


def ceo_reason(command: str, cwd: str, root: str) -> "str | None":
    """Why a subagent's Bash command that names a live ceo-questions.md may not run, as one that appends to it a line
    that passes for the CEO's (ceo_line), or None (the module docstring)."""
    if not APPENDS.search(re.sub(r"[\"'\\]", "", command)):
        return None
    appends, texts = _ceo_texts(command, cwd, root, 0, None)
    if not appends:
        return None
    line = next((line for text in texts for line in NEWLINE.split(text) if ceo_line(line)), None)
    if line is not None:
        return f"a line that passes for the CEO's goes into a ceo-questions.md: {line.strip()[:80]}"
    # an append's first line joins the reply above it, maybe the CEO's, if it is indented, numbered or `(`
    line = next((first for first in (NEWLINE.split(text, 1)[0] for text in texts)
                 if first.strip() and CONTINUES.match(first)), None)
    return None if line is None else (f"an appended first line that is indented, numbered or starts `(` goes into a "
                                      f"ceo-questions.md, where it joins the line above, maybe the CEO's: "
                                      f"{line.strip()[:80]}")


def archive_reason(command: str, cwd: str, root: str) -> "str | None":
    """Why a subagent's Bash command may not write to a live ceo-questions-archive.md, or None: it adds a line that
    passes for the CEO's, or one that may join one there (joining), that the ceo-questions.md beside it doesn't hold
    as it is now (unheld; the module docstring)."""
    bare = re.sub(r"[\"'\\]", "", command.replace("\\\n", ""))  # a backslash-newline joins the words around it
    if not (APPENDS.search(bare) or ">" in bare) or not ARCHIVE_MENTION.search(bare):
        return None
    folders, texts = _ceo_texts(command, cwd, root, 0, None, ARCHIVE_MENTION)
    if not folders:
        return None
    ceo, joined = [], []
    for text in texts:
        more = joining(NEWLINE.split(text))
        ceo.extend(more[0])
        joined.extend(more[1])
    found = unheld(ceo, joined, folders)
    if found is None:
        return None
    if found[0] == "ceo":
        return (f"a line that passes for the CEO's goes into a ceo-questions-archive.md, and the ceo-questions.md "
                f"beside it doesn't hold it: {found[1].strip()[:80]}")
    return (f"an indented, numbered or `(` line that may join a CEO line goes into a ceo-questions-archive.md, and the "
            f"ceo-questions.md beside it doesn't hold it under a CEO line: {found[1].strip()[:80]}")


def joining(lines: list) -> tuple:
    """(The lines that pass for the CEO's (ceo_line), the lines that may join one in the file they're appended to:
    the first if it's indented, numbered or `(` (CONTINUES: it joins the file's last line, maybe the CEO's), and each
    such line right under a CEO line or under one of these), of lines appended in this order."""
    ceo, joined, above = [], [], True
    for line in lines:
        if ceo_line(line):
            ceo.append(line)
            above = True
        elif above and line.strip() and CONTINUES.match(line):
            joined.append(line)
        else:
            above = False
    return ceo, joined


def unheld(ceo: list, joined: list, folders: list) -> "tuple | None":
    """('ceo', the first line of ceo that the ceo-questions.md in one of the folders doesn't hold), or ('joins', the
    first of joined that it doesn't hold under a CEO line, under_ceo), or None: the by-hand move's lines stand there
    until its Edits take them out (cto.md, "Logs"). A folder this can't place (None) or a file it can't read holds
    nothing."""
    for folder in dict.fromkeys(folders):
        text = ""
        if folder is not None:
            try:
                with open(os.path.join(folder, NAME), encoding="utf-8", errors="replace") as file:
                    text = file.read()
            except OSError:
                pass
        lines, under = set(text.split("\n")), {line for _, line in under_ceo(text)}
        line = next((line for line in ceo if line not in lines), None)
        if line is not None:
            return "ceo", line
        line = next((line for line in joined if line not in under), None)
        if line is not None:
            return "joins", line
    return None


def _ceo_texts(command: str, cwd: str, root: str, depth: int, outer: "Scope | None", mention=MENTION) -> tuple:
    """(the folder of each live file mention names that the command writes to, by a `>>` or `>` into it, tee, sponge
    or `--add`, None for one it can't place (folder_of); the texts it may write there): what echo and print print
    (their words joined), each of printf's words, heredoc bodies, here-strings' texts and cq_archive.py's `--add` line,
    with the command's plain values filled in too, in it and, three levels deep, in its `$(...)`, backticks, `<(...)`,
    a shell's `-c`, eval's and a trap's text. What it can't read adds nothing: command_reason has refused such a
    command that names a ceo-questions.md (and a `>` into one, before ceo_reason reads it)."""
    if depth > DEPTH:
        return [], []
    scope = Scope(cwd, root, outer.names if outer else None, outer.values if outer else None)
    scope.home = (outer.home if outer else False) or bool(HOME.search(command))
    scope.mention = mention
    texts, inner, appends = [], [], []
    bodies, dashes = [], []
    heredocs(command, lambda quote, rest, body: bodies.append(body) or " ", dashes)
    texts += [re.sub(r"(?m)^\t+", "", body) if dash else body for body, dash in zip(bodies, dashes)]  # `<<-`
    for joined in (True, False) if "\\\n" in command else (True,):  # a backslash-newline joins words, and as a space
        try:
            words = tokens(command, scope, joined)
            scope.read(words)
            words = tokens(command, scope, joined)
            subs = substitutions(command, scope)
        except ValueError:
            continue
        inner += [(text, scope) for text in subs]
        hidden = any(scope.mentioned(text) for text in subs)
        texts += [word for before, word in zip(words, words[1:]) if before.endswith("<<<")]  # here-strings
        for commands, redirections, _ in [simple_commands(words), simple_commands(spliced(words))]:
            appends += [None if hidden and HIDDEN.search(target) else folder_of(target, scope)
                        for op, target in redirections
                        if ">" in op and (scope.mentioned(target) or (hidden and HIDDEN.search(target)))]
            for words_of_one in commands:
                for program, args in programs(words_of_one, scope):
                    name = os.path.basename(program).lower()
                    args = [arg for arg in args if arg != HEREDOC_WORD]
                    named = [folder_of(arg, scope) for arg in args if scope.mentioned(arg)]
                    appends += named if name in ("tee", "sponge") else []
                    for i, arg in enumerate(args):
                        if ADD.match(arg):
                            appends += named
                            texts += [arg.split("=", 1)[1]] if "=" in arg else args[i + 1:i + 2]
                    if name in PRINTERS:
                        k = 0  # past its options (`-n`, `-e`, `--`; not `- CEO ...`, a word to print)
                        while k < len(args) and re.fullmatch(r"-[A-Za-z]+|--", args[k]):
                            k += 2 if name == "printf" and args[k] == "-v" else 1  # printf -v NAME prints nothing
                        texts += args[k:] if name == "printf" else [" ".join(args[k:])]
                    if name in SHELLS:
                        flag = next((j for j, arg in enumerate(args[:-1]) if SHELL_STRING_FLAG.match(arg)), None)
                        if flag is not None:
                            fresh = copy.copy(scope)
                            fresh.values = {}  # a new shell has only the exported variables
                            inner.append((args[flag + 1], fresh))
                    elif name == "eval":
                        inner.append((" ".join(args), scope))
                    elif name == "trap":
                        inner += [(arg, scope) for arg in args]
    for text, holder in inner:
        more, found = _ceo_texts(text, cwd, root, depth + 1, holder, mention)
        appends, texts = appends + more, texts + found
    return appends, texts + [expand(text, scope.values) for text in texts if "$" in text]


def folder_of(word: str, scope: Scope) -> "str | None":
    """The folder of the file a word names, by its real path as may_be_live reads it (a link named
    ceo-questions-archive.md elsewhere is checked against the folder of the archive it points to), or
    None if this can't tell: a variable with no plain value, a `$(...)` or backtick, a `~` the command may move (HOME), or
    a relative path, which a cd, `env -C` or find's `-execdir` may move."""
    path = expand(word, scope.values)
    if scope.home and path.startswith("~"):
        return None
    path = os.path.expanduser(path)
    if "$" in path or "`" in path or not path.startswith("/"):
        return None
    return os.path.dirname(os.path.realpath(path))


def edited(tool: str, tool_input: dict, path) -> tuple:
    """(The file's text, its text after a Write, Edit or MultiEdit): a new file's is empty before; an edit whose old
    text isn't in the file (it fails) adds its new text at the end."""
    try:
        before = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
    except OSError:
        before = ""
    if tool == "Write":
        after = tool_input.get("content")
        after = after if isinstance(after, str) else ""
    else:
        edits = tool_input.get("edits") if tool == "MultiEdit" else [tool_input]
        after = before
        for edit in edits if isinstance(edits, list) else []:
            old, new = (edit.get(key) if isinstance(edit, dict) else None for key in ("old_string", "new_string"))
            old, new = old if isinstance(old, str) else "", new if isinstance(new, str) else ""
            if old and old in after:
                after = after.replace(old, new) if edit.get("replace_all") else after.replace(old, new, 1)
            else:
                after += "\n" + new
    return before, after


def written_lines(before: str, after: str) -> list:
    """The lines after holds that before didn't, by count."""
    kept = Counter(before.split("\n"))
    added = []
    for line in after.split("\n"):
        if kept[line]:
            kept[line] -= 1
        else:
            added.append(line)
    return added


def under_ceo(text: str) -> Counter:
    """(The line above, the line) for each non-blank indented, numbered or `(` line (CONTINUES) right under a line
    ceo_line holds or under another such line, by count: where the capacity scan may join a line to a reply that passes
    for the CEO's (a superset of its replies and goes_on)."""
    pairs, above = Counter(), None
    for line in text.split("\n"):
        if above is not None and line.strip() and CONTINUES.match(line):
            pairs[(above, line)] += 1
            above = line
        else:
            above = line if ceo_line(line) else None
    return pairs


def cq_reason(event: dict, root: str) -> "str | None":
    """The block message for a subagent's Bash command that writes a live ceo-questions.md other than by appending,
    or runs a script file that names one (script_reason), or appends a line that passes for the CEO's to one
    (ceo_reason) or to the archive beside one (archive_reason, told last), or None. The main session (no agent_id) isn't
    held."""
    if event.get("tool_name") != "Bash" or not event.get("agent_id"):
        return None
    command = (event.get("tool_input") or {}).get("command")
    if not isinstance(command, str):
        return None
    seen = command.replace("\\\n", "")
    named = "ceo-questions" in seen.lower()  # else command_reason reads it only for folder_reason
    folders = all(words.search(seen) for words in FOLDER_WORDS)
    cwd = event.get("cwd") or root
    message = MESSAGE
    old = signal.signal(signal.SIGALRM, _too_slow)
    signal.setitimer(signal.ITIMER_REAL, SECONDS)
    try:
        if named:
            how = command_reason(command, cwd, root) or script_reason(command, cwd, root)
            if how is None:  # under the timer too: a CEO-line read still going at it is refused below
                how, message = ceo_reason(command, cwd, root), CEO_MESSAGE
            if how is None:  # the archive beside one
                how, message = archive_reason(command, cwd, root), ARCHIVE_MESSAGE
        else:  # script_reason first: a folder read still going at the timer passes
            how = script_reason(command, cwd, root) or (command_reason(command, cwd, root) if folders else None)
    except TooSlow:  # one that doesn't name the file passes
        how = f"a command that names a ceo-questions.md took over {SECONDS} s to read" if named else None
        message = MESSAGE
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old)
    return None if how is None else message.format(how=how, root=root)


class TooSlow(Exception):
    """Raised by the timer in cq_reason."""


def _too_slow(signum, frame):
    raise TooSlow()


def write_reason(event: dict, raw_path: str, path, root: str) -> "str | None":
    """The block message for a subagent's Write on an existing live ceo-questions.md, or its Write, Edit or MultiEdit
    that adds a line that passes for the CEO's to one (ceo_line, written_lines), or
    to the archive beside one unless that file holds it (unheld) (guard_kb_write.py calls it with the
    path as given and resolved), or None."""
    tool = event.get("tool_name")
    if tool not in ("Write", "Edit", "MultiEdit") or not event.get("agent_id"):
        return None
    names = (os.path.basename(raw_path).casefold(), path.name.casefold())
    if NAME not in names and ARCHIVE not in names:
        return None
    if not Scope(str(path.parent), root).may_be_live(str(path)):
        return None
    if NAME not in names:  # the archive
        before, after = edited(tool, event.get("tool_input") or {}, path)
        found = unheld([line for line in written_lines(before, after) if ceo_line(line)],
                       [line for _, line in under_ceo(after) - under_ceo(before)], [str(path.parent)])
        if found is None:
            return None
        what, held = (("adds a line that passes for the CEO's to", "") if found[0] == "ceo" else
                      ("leaves an indented, numbered or `(` line under a CEO line in", " under a CEO line"))
        return ARCHIVE_MESSAGE.format(how=f"{tool} {what} a ceo-questions-archive.md, and the ceo-questions.md beside "
                                          f"it doesn't hold it{held}: {found[1].strip()[:80]}")
    if tool == "Write" and path.exists():
        return MESSAGE.format(how="Write would replace an existing ceo-questions.md whole", root=root)
    before, after = edited(tool, event.get("tool_input") or {}, path)
    line = next((line for line in written_lines(before, after) if ceo_line(line)), None)
    if line is not None:
        return CEO_MESSAGE.format(how=f"{tool} adds a line that passes for the CEO's to a ceo-questions.md: "
                                      f"{line.strip()[:80]}", root=root)
    joined = next(iter(under_ceo(after) - under_ceo(before)), None)  # one added there, changed, or a line above it taken out
    if joined is None:
        return None
    return CEO_MESSAGE.format(how=f"{tool} leaves an indented, numbered or `(` line under a CEO line in a "
                                  f"ceo-questions.md where it didn't stand, so it joins the CEO's reply: "
                                  f"{joined[1].strip()[:80]}", root=root)
