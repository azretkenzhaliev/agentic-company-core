"""An agent's Bash never writes the Board's answers or the desk's state, runs the desk's writing commands or reads its
Notion token (docs/board-desk.md, "Protection").

knowledge/board/answers/ holds the Board's own answers, written only by scripts/board_desk.py's reader; the CEO acts on
each row as the Board's word. workspaces/board-desk/ holds the desk's state: the Board's medium id the reader trusts,
the desk's Notion ids. board_desk.py's run, hour, day and read write the desk pages and the answers, and are its launchd
jobs' (or the Board's own). guard_kb_write.py holds Write and Edit there; this holds Bash.

guard_marketing_tools.py calls desk_reason for every Bash call of an agent (a hook input with agent_type, the CEO's
main session included, or with agent_id), with the call's cwd: its settings entry runs in every session and fails
closed. A plain session (the Board's own) is never held here. Refused, with the reason:
- a command that names either folder, unless each of its simple commands is a read (READS, git's GIT_KEEPS without a
  prefix of --output, --open-files-in-pager, --receive-pack, --upload-pack or --exec, grep's -O, a git option of its own
  but -C, a -c that runs nothing and those GIT_OWN lists (git_runs), find without an action, sed -n with a script that
  only prints (SED_PRINT), sort without -o, -T, --compress-program or TMPDIR, a plain assignment, or a for or while
  loop's own words: `for NAME [in WORDS]`, do, while, done) with no output redirection but to /dev/null or another
  descriptor and no variable set for it alone but a locale (`LC_ALL=C`), and the command holds no `$(`, backquote or
  process substitution (HIDDEN) and no code of a zsh glob qualifier (qualifier_codes); if, then, until and the other
  keywords (PREFIXES) aren't reads. A `$` the shell may expand (EXPANDS: a loop's or read's variable) stands in find and
  sort nowhere, in git and sed only after a literal `--` and never in sed's script; and no simple command sets a
  variable the shell reads (SPECIAL: PATH, IFS, TMPDIR, zsh's `path`, `commands`, `functions`, ...) or one the
  environment exports, for the commands after it (environ_set; not one for being upper-case). It names one when its text
  holds `board/answers` or `workspaces/board-desk` (FOLDER), when a word or redirection target, resolved against the cwd
  and each folder move before it (cd, chdir, pushd, popd, after builtin, command, noglob or nocorrect too: moved), lies
  in a knowledge/board/answers or workspaces/board-desk folder or is a folder holding one (knowledge, knowledge/board or
  workspaces, with the rest beneath it on disk) (in_answers), or after a move the check can't follow (`cd -`, `~`, a
  variable), eval or a zsh NAME[key]=value may be one or hold one, whatever folder it is read from (holds_name), or when
  the cwd does; when a word of shell code it gives as words (a shell's -c string, eval's, a NAME[key]=value, git's:
  shell_code) or of a heredoc a shell reads may be one, read so from any folder too, at each quote depth; when a word
  the quotes split (`kno''wledge`) is one after quote removal; and when a git command may throw away the uncommitted
  changes of a checkout holding one (discards: stash but list and show, clean but -n, reset --hard, --merge or --keep
  but one in a linked worktree that changes no file there, beside only reads that move no ref and stage nothing
  (reset_keeps, same_files), checkout, restore or switch forced, checkout or restore given the checkout's top folder). A
  command with code of a zsh glob qualifier (after a space, `=` or a glob group) or a `${(e)...}` that names a held
  folder by any word, read from any folder, is refused whole, whatever else it is; so is one whose shell heredoc does. A
  refusal whose call's first simple command is a git reset that passes alone names that reset, the one retry a blocked
  agent is allowed (reset_hint). A heredoc's body (opened by a `<<` outside quotes, a comment, `((...))`, `${...}` and
  `$[...]`, and closed by its word after the shell's quote removal) counts for the text, never as a command; after a
  word with a backquote, `$(`, `${`, `$'` or `$"`, each line counts as both;
- a run of board_desk.py whose command isn't wait, install, uninstall or --help (DESK_COMMANDS), or setup or
  attribution too for the CEO's main session (CEO_COMMANDS: agent_type ceo and no agent_id; on the Board's steps, and
  only in the main checkout). `read` writes the answers, so it is the 2-minute job's alone. The file as the
  program, or as an operand of python or a wrapper (nohup, env, timeout, ...), or `-m <...>board_desk`; or such a run
  in the code a shell or an interpreter is given (a `-c` or `-e` string, eval's or source's operands, a heredoc's
  body it reads), or a run of it (RUN_FORM) in a `$(` or backquote substitution. A command that won't split is
  refused when it names the folder, or holds a run (RUN_FORM); one whose lines split once their comments are cut
  (uncommented) is then checked as any other;
- a read or change of the desk's Notion token, which scripts/board_desk/adapter_notion.py alone reads: `security` (as
  the program, or after a wrapper) naming its Keychain service (KEYCHAIN) or account (ACCOUNT), or dump-keychain, which
  prints every item; or code a shell or an interpreter is given (a `-c` or `-e` string, eval's or source's operands, a
  heredoc's body it reads) that calls keychain_token, names the service, the account (`-a notion`) or dump-keychain
  beside `security`, or makes adapter_notion's Notion or Desk (each reads the token). A command that won't split is
  refused when it holds `keychain_token(`, `security dump-keychain`, the service or the account beside
  `generic-password`, or adapter_notion with its Notion or Desk made. Reading the adapter's code is no read of
  the token; other Keychain items are CLAUDE.md's ("Secrets").

Every check reads a simple command's program past the shell keywords it follows (`do`, `then`, `!`, ...), so a run
or a git discard inside a loop or an if is the one outside it.

A line that ends inside a quote is one line with the lines after it, up to the one that closes the quote, as the shell
reads it (split). Where `$(`, a backquote, `<(`, `>(`, `${`, `$[` or `((` stands (NESTS), the
shell's quotes nest and this reading's don't, so such lines are read one by one, as before. A backslash-newline is
read as the shell reads it, in a heredoc's body too, and `$'...'` as the word it makes (split, ansi_c).

A command whose only mention of a held folder is text it prints or writes elsewhere (echo's or printf's operands, a
commit message, a quoted heredoc's body given to cat or tee) isn't one that names it, when each of its other simple
commands is a read, a plain assignment or `date`, and nothing can run that text or take paths from it (text_only), nor
scripts/second_opinion.py's --brief text when that run is the call's only simple command (brief_words). Nor is one whose
text holds no held folder's path (FOLDER) and whose simple commands are reads (which may name a folder holding one:
knowledge, knowledge/board, workspaces) and python runs of script files whose words can't reach one (parents_only,
script_run).

It reads only the command's text, so it stops an agent's mistake; it isn't a sandbox. The answers pages are tracked by
git and sealed (answers_seal.py), so a change of them shows. It is always on, with a desk configured or not, and reads
no setting (company.json), so a broken one can't open it.
"""

import fnmatch
import hashlib
import os
import posixpath
import re
import shlex
import stat
import subprocess
from pathlib import PurePosixPath

FOLDER = re.compile(r"board/+answers\b|workspaces/+board-desk\b|board-desk-seal\b", re.I)
# and the answers' seal (scripts/board_desk/answers_seal.py's SEAL_DIR, outside the repo), by its own name
HELD_PARTS = (("knowledge", "board", "answers"), ("workspaces", "board-desk"), ("board-desk-seal",))
HELD_PART = {part for held in HELD_PARTS for part in held}
HIDDEN = ("$(", "`", "<(", ">(")
NESTS = HIDDEN + ("${", "$[", "((")  # where the shell's quotes nest inside other quotes and scan's don't
READS = {"cat", "head", "tail", "grep", "egrep", "fgrep", "wc", "ls", "stat", "diff", "cmp", "cd", "pwd", "echo",
         "test", "[", "true", "false", "basename", "dirname", "realpath", "readlink", "find", "git",
         "printf", "read",  # a loop's (`while read -r f`)
         "sort", "cut",  # what read-only git is piped into; sort without -o, -T (sort_reason)
         "tr"}  # it reads only its input
GIT_KEEPS = {"status", "diff", "log", "show", "add", "commit", "push", "blame", "ls-files", "grep", "rev-parse",
             "cat-file"}  # git subcommands that leave the working files as they are
TEXT = {"echo", "printf"}  # whose operands are text they print (text_only)
WRITERS = {"cat", "tee"}  # and those whose heredoc's body is text they print or write
# variables the shell itself reads (command lookup, cd, `~`, a bare redirection's program, word splitting), zsh's tied
# arrays among them; text_only refuses an assignment to one, or to any variable the environment already exports, and
# so do read_reason and environ_set. zsh's own tables of what a name runs are among them (checked on the Mac, zsh 5.9:
# `commands=(ls /bin/echo)`, `functions=(ls 'print x')`, `read -A commands` and `for path in /x` each change what a
# later `ls` runs, in the same command). Only these and the names the environment exports refuse, not any upper-case one
# (`S=/x; ls $S`): bash(1) and zshparam(1) name ZDOTDIR, PWD and OLDPWD (cd, `~-`), TMPDIR (bash's heredoc files) and
# TMPPREFIX (zsh's), EXECIGNORE (bash's command lookup), GLOBIGNORE, SHELLOPTS, BASHOPTS and POSIXLY_CORRECT (the
# shell's own options), BASH_XTRACEFD (where `set -x` writes) and BASH_LOADABLES_PATH (`enable -f`), BASH_CMDS and
# BASH_ALIASES (bash's command hash and aliases), zsh's MODULE_PATH and PROMPT4, tied to module_path and PS4, and
# HISTFILE (where both write the history)
SPECIAL = {"PATH", "HOME", "IFS", "CDPATH", "FPATH", "ENV", "BASH_ENV", "NULLCMD", "READNULLCMD", "PS4",
           "PROMPT_COMMAND", "ZDOTDIR", "PWD", "OLDPWD", "TMPDIR", "TMPPREFIX", "EXECIGNORE", "GLOBIGNORE",
           "SHELLOPTS", "BASHOPTS", "POSIXLY_CORRECT", "BASH_XTRACEFD", "BASH_LOADABLES_PATH", "BASH_CMDS",
           "BASH_ALIASES", "MODULE_PATH", "PROMPT4", "HISTFILE",
           "path", "cdpath", "fpath", "module_path",
           "commands", "functions", "aliases", "galiases", "saliases", "options", "nameddirs", "mapfile",
           "dis_aliases", "dis_functions", "dis_galiases", "dis_saliases", "dis_builtins", "dis_reswords",
           "chpwd_functions", "precmd_functions", "preexec_functions", "periodic_functions", "zshexit_functions",
           "zshaddhistory_functions"}
# git's long options that write a file or run a program: push's --receive-pack and --exec, and --upload-pack, name a
# program git runs
GIT_RUNS = ("output", "open-files-in-pager", "receive-pack", "upload-pack", "exec")
# git's own options a read may take, beside -C and a SAFE_CONFIG -c: each names no program, file or config
GIT_OWN = {"--no-pager", "-P", "--no-optional-locks", "--literal-pathspecs", "--glob-pathspecs", "--noglob-pathspecs",
           "--icase-pathspecs", "--no-replace-objects", "--no-lazy-fetch", "--no-advice"}
SAFE_CONFIG = re.compile(r"^(?:core\.quotepath|user\.name|user\.email|color\.[\w.-]+|advice\.[\w-]+)(?:=|$)", re.I)
LOCALE = re.compile(r"^(?:LC_\w+|LANG|LANGUAGE|TZ)$")  # variables a read may be given for itself (`LC_ALL=C sort`)
PAIRS = {"[": "]", "{": "}", "<": ">", "(": ")"}  # a zsh glob qualifier's `e` string, so delimited, ends at its pair
HELD_NAME = re.compile(r"knowledge|workspaces|board|answers", re.I)  # a held path's parts, in any word (parents_only)
INTERPRETER_FLAGS = re.compile(r"^-[IuBEsSOqb]+$")  # python's options that take no value and name no code
FIND_ACTIONS = {"-delete", "-exec", "-execdir", "-ok", "-okdir", "-fprint", "-fprint0", "-fprintf", "-fls"}
PREFIXES = {"do", "then", "else", "elif", "if", "while", "until", "!", "{"}  # shell keywords a command may follow
LOOP = {"do", "while"}  # those a read may follow: a for or while loop's
NAME = re.compile(r"^[A-Za-z_]\w*$")  # `for NAME`'s
SED_ADDRESS = r"(?:\d+|\$|/(?:[^/\\]|\\.)*/I?)"  # a line, the last, or /regex/
SED_ONE = rf"(?:{SED_ADDRESS}(?:,(?:{SED_ADDRESS}|\+\d+))?(?:\s*!)?\s*)?[p=]"  # an address or range, then p or =
SED_PRINT = re.compile(rf"^\s*{SED_ONE}(?:\s*;\s*{SED_ONE})*(?:\s*;)?\s*$")  # a script that only prints: `1,20p`
# a `$` bash or zsh (the Bash tool's shell) may expand: `$x`, `${`, `$'`, zsh's `$=x`, `$=~x` or `$==x`; not `/x$/`
# or sed's own `$=` (before `;`, a space, `}` or the end)
EXPANDS = re.compile(r"\$(?![/;,\s]|$|=(?:[;\s}]|$))")
# an environment variable's name: TMPDIR, PATH, HOME, any upper-case one; a program given one for itself alone
# (`GIT_TRACE=<file> git status`) may read it (read_reason)
ENVIRON = re.compile(r"^_*[A-Z][A-Z0-9_]*$")
# a name a read program takes from the environment to run a program or read a config that does (git(1): GIT_EDITOR,
# GIT_PAGER, GIT_EXTERNAL_DIFF, GIT_CONFIG_*, ...; git-config(1): XDG_CONFIG_HOME; PAGER, EDITOR, VISUAL; less(1):
# LESSOPEN, LESSCLOSE; man(1): MANPAGER), refused for the commands after it as the Bash tool's shell may export it
# though the hook's environment doesn't
EXPORTED_RUNS = re.compile(r"^(GIT_\w+|XDG_CONFIG_HOME|PAGER|EDITOR|VISUAL|LESSOPEN|LESSCLOSE|MANPAGER)$")
KEYCHAIN = "board-desk-notion"  # adapter_notion.KEYCHAIN's service: the desk's Notion token
ACCOUNT = "notion"  # and its account
ACCOUNT_TEXT = re.compile(r"-[a-z]*a\W{0,4}notion\b", re.I)  # `-a notion`, or `"-a", "notion"` in code
NOTION_MADE = re.compile(r"\b(?:Notion|Desk)\s*\(")  # adapter_notion's client or desk made: each reads the token
DESK = "board_desk.py"
DESK_COMMANDS = {"wait", "install", "uninstall", "-h", "--help", None}  # any agent's
# the CEO's main session's too: setup and attribution
CEO_COMMANDS = DESK_COMMANDS | {"setup", "attribution"}


def run_patterns(commands):
    """(DESK_TEXT, RUN_FORM) for these commands: board_desk.py given any other, in text (code given to a shell or an
    interpreter), or in a command that won't split (python's or a path's board_desk.py, or `-m ...board_desk`)."""
    allowed = r"(?!(?:" + "|".join(sorted(re.escape(c) for c in commands if c)) + r")(?![\w-]))[\w-]"
    text = re.compile(r"(?<!\w)board_desk(?:\.py)?['\"]?\s+" + allowed, re.I)
    form = re.compile(r"(?:(?:^|[\s;&|(`])(?:python[\d.]*|pypy[\d.]*)(?:\s+-\S+)*\s+['\"]?\S*board_desk\.py"
                      r"|(?:^|[\s;&|(`])['\"]?\S*/board_desk\.py|-m\s*['\"]?[\w.]*board_desk)['\"]?\s+" + allowed,
                      re.I | re.M)
    return text, form


PATTERNS = {False: run_patterns(DESK_COMMANDS), True: run_patterns(CEO_COMMANDS)}  # by: the CEO's main session
PYTHON = re.compile(r"^(python[\d.]*|pypy[\d.]*)$")
CODE = re.compile(r"^(python[\d.]*|pypy[\d.]*|node(js)?|ruby|perl[\d.]*|php[\d.]*|bunx?|deno|osascript|eval|source|\.)$")
CODE_FLAG = re.compile(r"^(?:-[A-Za-z]*[ce]|--eval|--command)$")  # the next word is code: -c, -e, bash -ec, --eval
SHELLS = {"sh", "bash", "zsh", "dash", "ksh", "fish"}
WRAPPERS = {"env", "nohup", "timeout", "caffeinate", "nice", "command", "exec", "time", "sudo", "xargs", "stdbuf",
            "uv", "uvx"}
HEREDOC = re.compile(r"(?<!<)<<-?(?!<)\s*")  # a heredoc's `<<` or `<<-`, matched by scan() outside quotes
OPENERS = {"((": "))", "${": "}", "$[": "]"}  # arithmetic and parameter expansions: a `<<` there opens no heredoc
ASSIGNMENT = re.compile(r"^[A-Za-z_]\w*=")
OPERATOR = set("();<>|&")
# what moves the shell's folder, the precommand modifiers it may follow, and code the check reads only as text: zsh's
# NAME[key]=value (`functions[ls]=...`, `aliases[x]=...`) and its ${(e)...}, which runs the $(...) in a value
MOVES = {"cd", "chdir", "pushd", "popd"}
MODIFIERS = {"builtin", "command", "noglob", "nocorrect", "-"}  # zsh's `-` too
INDEXED = re.compile(r"^[A-Za-z_]\w*\[(.*?)\]\+?=(.*)$", re.S)
EVAL_FLAG = re.compile(r"\$\{\([^)]*e")
CODE_SPLIT = re.compile(r"[\s'\"`;|&()<>!\\=:,{}$]+")  # where a word of code ends, read as paths (code_words)
CODE_PIECES = re.compile(f"({CODE_SPLIT.pattern})")  # and with what lies between them kept (built_words)
GLOB = re.compile(r"[*?[]")  # a word's part the shell or a glob call may expand (fits)
RUN_SPLIT = re.compile(r"[\s;|&()<>]+")  # where a word of shell code ends, its `$`, quotes and braces kept (cut_words)
LONE = re.compile(r"\$\{?\w+\}?|\$[@*#?]")  # a word that is only a variable, read whole elsewhere (cut_words)
POSITIONAL = re.compile(r"\$\{?[0-9@*#]")  # an operand the code is given, by its number or all of them (loose_names)
# a folder move in code, and its operand up to the next command (loose_names): one the shell builds (`cd "${PWD%/*}"`,
# `cd "$(dirname "$PWD")"`, a backquote, zsh's `cd $PWD:h`, `cd ~-/..`, a glob qualifier) may climb, as `..` does
MOVE = re.compile(r"(?:^|[\s;&|(){}!])(?:cd|pushd|chdir)\s+([^;&|\n]*)")
BUILT_MOVE = re.compile(r"[$`~(:]")
# what makes code (a shell's -c, -s or heredoc code, eval's, an interpreter's) keep the broad held-part rule (risky): a
# `$`, a backquote or a glob character; a folder move (cd, pushd, popd, chdir: `cd -`, zsh's two-operand cd, os.chdir);
# a name the moves read (PWD, OLDPWD, CDPATH, dirstack); and in shell code a command word the shell builds (a quote,
# backslash or brace in it: `{c,}d`)
RISK = re.compile(r"[$`*?[]")
FOLDER_MOVE = re.compile(r"(?<![\w-])(?:cd|pushd|popd|chdir)(?![\w-])")
MOVE_NAMES = re.compile(r"(?<![\w$])(?:PWD|OLDPWD|CDPATH|dirstack)(?!\w)")
BUILT_COMMAND = re.compile(r"(?:^|[;&|(\n])\s*(?:\w+=\S*\s+)*(?![{}]\s)[^\s;&|()<>]*[{}\\'\"]")
PLAIN_OPERAND = re.compile(r"[\w./+-]+")  # a file the row helper is given, which nothing expands (status_log_run)
OPINION = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "second_opinion.py")  # brief_words
STATUS_LOG = os.path.join(os.path.dirname(OPINION), "status_log.py")  # status_log_run: the CEO's row helper
# `$(date -u +%Y-%m-%dT%H:%M:%SZ)`, a substitution of date given only options
# and a +format with no quote, `$`, backquote, parenthesis, operator or backslash (text_only reads it as a word)
DATE_RUN = re.compile(r"\$\(\s*date(?:\s+[-+][^\s$`()<>;|&\\'\"]*)*\s*\)")
GH_TEXT = {("pr", "create"), ("pr", "comment"), ("pr", "edit"), ("pr", "review"), ("issue", "create"),
           ("issue", "comment"), ("issue", "edit")}  # gh_text: the gh commands whose --title and --body are text

ANSWERS_MESSAGE = ("Blocked: knowledge/board/answers/ holds the Board's own answers, and workspaces/board-desk/ the "
                   "desk's state; only scripts/board_desk.py writes them. An "
                   "agent's Bash only reads there; the CEO's main session also stages and commits the answers. "
                   "Here: {}.")
TOKEN_MESSAGE = ("Blocked: the Board desk's Notion token (Keychain service board-desk-notion) is read only by "
                 "scripts/board_desk/adapter_notion.py, in the desk's own runs; no agent reads, prints or changes it. "
                 "Here: {}.")
DESK_MESSAGE = ("Blocked: board_desk.py's run, hour, day and read write the desk pages and the Board's answers; they "
                "are its launchd jobs', or the Board's own. An agent runs only "
                "`python3 scripts/board_desk.py wait`, install, uninstall or --help, and the CEO's main session setup "
                "and attribution too. Here: {}.")


def odd(line) -> bool:
    """Whether the line ends in an odd number of backslashes: the last one escapes the newline after it."""
    return (len(line) - len(line.rstrip("\\"))) % 2 == 1


def continues(line) -> bool:
    """Whether the shell joins the next line to this one, removing the backslash and the newline: the line ends in an
    odd number of backslashes (an escaped backslash, `\\\\`, ends the line) outside a comment and outside single
    quotes and `$'...'` (whose newline stays in the word: bash keeps that backslash, zsh drops it). In a line that
    holds a NESTS form, where the shell's quotes nest and scan's don't, the quote scan reads isn't trusted and an odd
    count joins."""
    if not odd(line):
        return False
    _, cut, quote = scan(line)
    return cut == len(line) and (quote not in ("'", "$'") or any(nest in line for nest in NESTS))


def split(command):
    """(lines, bodies): the command's lines with each heredoc's body taken out (a body is data here), and the bodies'
    lines, each as (the index of the line that opened it, the line, whether its word was quoted), read in order, as
    the shell reads them:
    - a line that continues (an odd backslash at its end, outside a comment and single quotes) takes the next one,
      with the backslash and the newline removed, as the shell does: `rm -rf knowledge/bo\\` and `ard/answers` are
      one word; after an escaped backslash (`\\\\`) the next line is a command of its own;
    - a newline inside quotes is the shell's word, not a line's end (a commit message's), so a line whose
      quote is still open (scan) takes the next one, unless the text holds a `$(`, backquote, process substitution,
      `${`, `$[` or `((`, where the shell's quotes nest and scan's don't (NESTS): then the line is left open and won't
      split;
    - a heredoc's body ends at its word's line; in a body whose word wasn't quoted a line ending in an odd backslash
      takes the next one first, as the shell does (`a\\` and `EOF` are `aEOF`, no end), and in a quoted one it
      doesn't (a body line `a\\` above `EOF` ends there);
    - after a heredoc word the check can't read, each line is both a line and the body of each such heredoc, so it is
      checked as a command and as the code it may be; no line is quote-joined (that body may end anywhere), and no later
      heredoc's body is taken out."""
    lines, bodies, ends, unread = [], [], [], []
    pieces, k = command.split("\n"), 0
    while k < len(pieces):
        line, k = pieces[k], k + 1
        if ends:  # a heredoc's body line
            end, dash, quoted = ends[0]
            while not quoted and odd(line) and k < len(pieces):
                line, k = line[:-1] + pieces[k], k + 1
            if (line.lstrip("\t") if dash else line) == end:
                ends.pop(0)
            else:
                bodies.append((len(lines) - 1, line, quoted))
            continue
        while k < len(pieces):
            if continues(line):
                line, k = line[:-1] + pieces[k], k + 1
                continue
            found, _, quote = scan(line)
            if (quote and not unread and all(word is not None for word, _, _ in found)
                    and not any(nest in line + "\n" + pieces[k] for nest in NESTS)):
                line, k = line + "\n" + pieces[k], k + 1
                continue
            break
        found = scan(line)[0]
        bodies.extend((at, line, False) for at in unread)
        lines.append(line)
        if not unread:
            ends.extend(heredoc for heredoc in found if heredoc[0])
        if any(word is None for word, _, _ in found):
            unread.append(len(lines) - 1)
    return lines, bodies


def heredocs(line):
    """[(word, dash)]: the heredocs a line opens (scan)."""
    return [(word, dash) for word, dash, _ in scan(line)[0]]


def uncommented(line):
    """The line without its comment, for one that won't split whole (`rm -rf knowledge/board # don't`), or None: it has
    no comment, or a `$(`, backquote or process substitution (HIDDEN) its `#` may lie in."""
    cut = scan(line)[1]
    return None if cut == len(line) or any(hidden in line for hidden in HIDDEN) else line[:cut]


def heredoc_word(line, i):
    """(delimiter, end, quoted) for the word at i after a heredoc's `<<`: the word after the shell's quote removal,
    as bash and zsh end the body (`E"O"F` at EOF, `EOF$x` at EOF$x: nothing is expanded there), where it ends, and
    whether any of it was quoted (a quote or a backslash: then the shell expands nothing in the body and joins no line
    there; split); None for the delimiter when the word is empty or reaches a backquote, `$(`, `${`, `$'` or `$"`:
    then each line after it is checked as a command and as its body (split)."""
    word, quote, quoted = "", "", False
    while i < len(line):
        c = line[i]
        if c == "`" or c == "$" and line[i + 1:i + 2] in ("(", "{", "'", '"'):
            return None, i, quoted
        if quote == "'":
            quote, word = ("", word) if c == "'" else (quote, word + c)
        elif quote:  # in double quotes a backslash escapes only $, `, " and itself
            if c == "\\" and line[i + 1:i + 2] in ("$", "`", '"', "\\"):
                word, i = word + line[i + 1], i + 1
            elif c == '"':
                quote = ""
            else:
                word += c
        elif c == "\\":
            word, i, quoted = word + line[i + 1:i + 2], i + 1, True
        elif c in "'\"":
            quote, quoted = c, True
        elif c.isspace() or c in ";&|()<>":
            break
        else:
            word += c
        i += 1
    return (word if word and not quote else None), i, quoted


def scan(line):
    """([(word, dash, quoted)], comment, quote): the heredocs a line opens, each a `<<` or `<<-` outside quotes, a
    comment, `((...))`, `${...}` and `$[...]`, so a quoted `'<<EOF'` hides no line after it from the check, each with
    its word as the shell reads it (heredoc_word; None if the check can't read it) and whether it was quoted; where the
    line's comment starts (its length if it has none, or if the `#` lies in one of those: `${a:- #}`); and the quote
    still open at its end ("" if none), which split reads on into the next line."""
    found, quote, inside, i = [], "", [], 0  # inside: the closers of the `((`, `${` and `$[` the scan is in
    while i < len(line):
        c = line[i]
        if quote == "'":
            quote = "" if c == "'" else quote
        elif c == "\\":  # outside single quotes, a backslash escapes the next character, in $'...' too
            i += 1
        elif quote:
            quote = "" if c == quote[-1] else quote
        elif c in "'\"":
            quote = c
        elif line.startswith("$'", i):
            quote, i = "$'", i + 1
        elif c == "#" and (i == 0 or line[i - 1] in " \t;&|()<>"):
            return found, (len(line) if inside else i), ""
        elif line[i:i + 2] in OPENERS:
            inside, i = inside + [OPENERS[line[i:i + 2]]], i + 1
        elif inside and line.startswith(inside[-1], i):
            i += len(inside.pop()) - 1
        elif not inside and HEREDOC.match(line, i):
            match = HEREDOC.match(line, i)
            word, i, quoted = heredoc_word(line, match.end())
            found.append((word, match.group(0).startswith("<<-"), quoted))
            continue
        i += 1
    return found, len(line), quote


ESCAPES = {"a": "\a", "b": "\b", "e": "\x1b", "E": "\x1b", "f": "\f", "n": "\n", "r": "\r", "t": "\t", "v": "\v"}
ESCAPE = re.compile(r"\\(?:([0-7]{1,3})|x([0-9A-Fa-f]{1,2})|u([0-9A-Fa-f]{1,4})|U([0-9A-Fa-f]{1,8})|c(.)|(.))", re.S)
QUOTED_C = re.compile(r"\$'((?:[^'\\]|\\.)*)'", re.S)  # each `$'...'`, wherever it stands (nul_readings)


def decoded(match) -> str:
    """One `$'...'` escape as bash and zsh read it: octal, \\xHH, \\uHHHH, \\UHHHHHHHH, \\cX, \\n and the others
    (ESCAPES), or the character itself (\\', \\\\, \\")."""
    octal, hex2, hex4, hex8, control, other = match.groups()
    if control is not None:
        return chr(ord(control.upper()) ^ 0x40)
    digits = octal or hex2 or hex4 or hex8
    if digits:
        return chr(min(int(digits, 8 if octal else 16), 0x10FFFF))
    return ESCAPES.get(other, other)


def ansi_c(line):
    """The line with each `$'...'` outside quotes written as the single-quoted word the shell makes of it, since
    shlex has no such quotes: `echo $'it\\'s'; rm -rf knowledge` split as `echo 'it'"'"'s'` and an rm the checks
    read. One left open is left as it is: shlex won't split it. A NUL stays in the word (nul_readings)."""
    out, quote, i = [], "", 0
    while i < len(line):
        c = line[i]
        if quote == "'":
            quote = "" if c == "'" else quote
        elif c == "\\":
            out.append(line[i:i + 2])
            i += 2
            continue
        elif quote:
            quote = "" if c == '"' else quote
        elif c in "'\"":
            quote = c
        elif line.startswith("$'", i):
            j = i + 2
            while j < len(line) and line[j] != "'":
                j += 2 if line[j] == "\\" else 1
            if j >= len(line):
                return "".join(out) + line[i:]
            out.append(shlex.quote(ESCAPE.sub(decoded, line[i + 2:j])))
            i = j + 1
            continue
        out.append(c)
        i += 1
    return "".join(out)


def parts(line):
    """[(words, output redirection targets, input sources, piped)] for each simple command of one line (`$'...'`
    read as the shell reads it: ansi_c): a source is a `<` file, a heredoc's word or a `<<<` string; piped when its
    output goes into a pipe (`|` or `|&`, at the line's end too); shlex's ValueError if it won't split."""
    lex = shlex.shlex(ansi_c(line), posix=True, punctuation_chars=True)
    lex.whitespace_split = True
    lex.commenters = ""  # a `#` inside a word isn't a comment to the shell; reading on only refuses more
    commands, words, targets, sources, tokens = [], [], [], [], list(lex)
    i = 0
    while i < len(tokens):
        token = tokens[i]
        if token and set(token) <= OPERATOR:
            if ">" in token or token.startswith("<"):  # a redirection: the next token is its target or source
                (targets if ">" in token else sources).append(tokens[i + 1] if i + 1 < len(tokens) else "")
                i += 2
                continue
            if words or targets or sources:
                commands.append((words, targets, sources, token in ("|", "|&")))
            words, targets, sources = [], [], []
        else:
            words.append(token)
        i += 1
    if words or targets or sources:
        commands.append((words, targets, sources, False))
    return commands


def simple_commands(line):
    """[(words, output redirection targets)] for each simple command of one line (parts; one with neither left out);
    shlex's ValueError if it won't split."""
    return [(words, targets) for words, targets, _, _ in parts(line) if words or targets]


def dequoted(text):
    """The text after the shell's quote removal, as one word: quotes and backslashes dropped, `$'...'` decoded,
    spaces kept; the text as it is if it won't split."""
    lex = shlex.shlex(ansi_c(text), posix=True)
    lex.whitespace, lex.whitespace_split, lex.commenters = "", True, ""
    try:
        return "".join(lex)
    except ValueError:
        return text


def depths(text):
    """The text, then it after the shell's quote removal (dequoted), again until it stays as it is: a word the quotes
    split (`kno''wledge`, `bash -c "rm -rf kno\\"\\"wledge"`) reads whole at some depth."""
    found = [text]
    for _ in range(8):
        plain = dequoted(found[-1])
        if plain == found[-1]:
            break
        found.append(plain)
    return found


def code_words(code):
    """The words of code, at each quote depth (depths), cut at the shell's separators (CODE_SPLIT), read as paths."""
    return [word for text in depths(code) for word in CODE_SPLIT.split(text) if word]


def built_words(code):
    """The paths code may build of its words (code_words), each of which may lie under any folder: a word that goes on
    from the one before it past a `$`, quote, brace or parenthesis, with no space between (`"$x"/board`,
    `${PWD%/*}/board`, `$(dirname "$PWD")/board`), without its leading `/`; and a word after a `$`, without its first
    part, the variable's name (`$PWD/board`)."""
    found = []
    for text in depths(code):
        pieces = CODE_PIECES.split(text)  # word, what lies between, word, ...
        for n in range(2, len(pieces), 2):
            word, gap = pieces[n], pieces[n - 1]
            if word.startswith("/") and pieces[n - 2] and not re.search(r"\s", gap):
                found.append(word.lstrip("/"))
            if gap.endswith("$") and "/" in word:
                found.append(word.split("/", 1)[1])
    return [word for word in found if word]


def cut_words(text):
    """The words of shell code (cut at blanks and the shell's operators, at each quote depth) that a `$`, backquote
    or brace joins to more text (`knowledge/boa${x}rd`, `{know,x}ledge/board`, `"$1"ard`, `knowledge/boar$(printf
    d)`), but a word that is only a variable (LONE): the shell builds the path there, so no piece of it is read
    alone."""
    return [run for depth in depths(text) for run in RUN_SPLIT.split(depth)
            if re.search(r"[$`{}]", run) and not LONE.fullmatch(run.strip("'\""))]


def held_part(word) -> bool:
    """Whether a word has a held path's part (knowledge, board, answers, workspaces, board-desk; any case) as one of
    its own."""
    return any(part.casefold() in HELD_PART for part in PurePosixPath(word).parts)


def fits(parts, held) -> bool:
    """Whether these parts are a held path's (held), part by part: the same, or a glob (`*`, `?`, `[...]`) that
    matches it, a glob only beside another part (`knowledge/boar[d]`, `*/answers`)."""
    return all(fnmatch.fnmatchcase(h, p) if GLOB.search(p) else p == h for p, h in zip(parts, held)) and (
        len(parts) > 1 or not GLOB.search(parts[0]))


def could_name(word, cwd) -> bool:
    """Whether a word may be a held folder, a folder holding one or a path in one: read from the cwd (in_answers), as
    an absolute path, or, relative, from any folder, its leading climbs (`..`) dropped: the rest holds a held path,
    or starts with the parts of one from any of them on (`board/answers/x`, `board-desk`, `answers`), or, from its
    second part on, with a held path's first parts (`x/knowledge`, `wt/workspaces/board-desk`), a glob part matching
    (fits). So `../board`, `knowledge` and `knowledge/b*` may, and `knowledge/company`, `workspaces/system/x` or
    `apps/board` may not."""
    word = re.sub(r"^--?[\w-]+=", "", word)
    if not word:
        return False
    if in_answers(resolve(cwd, word) or "/"):
        return True
    if word.startswith("/") and not GLOB.search(word):  # an absolute glob is read as a relative one is
        return False
    parts = [part.casefold() for part in PurePosixPath(posixpath.normpath(word)).parts if part != "/"]
    while parts and parts[0] == "..":
        parts.pop(0)
    return any(fits(parts[i:i + len(held) - o], held[o:o + len(parts) - i])
               for held in HELD_PARTS for i in range(len(parts)) for o in (range(len(held)) if i == 0 else (0,)))


def climbs(word) -> bool:
    """Whether a relative word, normalized, climbs above the folder it is read from (`..`, `../x`)."""
    word = re.sub(r"^--?[\w-]+=", "", word)
    return not word.startswith("/") and PurePosixPath(posixpath.normpath(word or ".")).parts[:1] == ("..",)


def risky(code, shell=True) -> bool:
    """Whether code, at any quote depth, holds what keeps the broad held-part rule (RISK, FOLDER_MOVE, MOVE_NAMES, and
    in shell code BUILT_COMMAND)."""
    return any(RISK.search(depth) or FOLDER_MOVE.search(depth) or MOVE_NAMES.search(depth)
               or shell and BUILT_COMMAND.search(depth) for depth in depths(code))


def loose_names(texts, cwd, codes=(), shells=None) -> bool:
    """Whether code that may move the folder first, or the words that feed it, may name a held folder, a folder holding
    one or a path in one: a word of these texts (code_words: shell code, its operands, the values set before it), or a
    word of an interpreter's code (codes: python's -c string, a heredoc python reads) with a `/` in it or `..` (its
    names and other text aren't paths: `answers = 1`), that could_name takes; or, beside a climb (`..`, `../x`) among
    them, any word with a held path's part (knowledge, board, answers, workspaces, board-desk; any case) as one of its
    own, absolute ones too (`sh -c 'cd "$1"; rm -rf ..' _ knowledge/company`). A word with such a part alone, as
    `cd <the main checkout>/workspaces/<product> && sh scripts/x.sh` has, names none; a path code builds in its
    own text (built_words: `"$(dirname "$PWD")/board"`) is read as a word. And a word the shell builds in these texts
    (cut_words: `knowledge/boa${x}rd`) names one by a held part, and so does the value the texts set to a variable shell
    code joins to more text (`a=knowledge/boar; rm -rf ${a}d`); if one joins an operand (`"$1"ard`, `"$1$2"`), so does
    every word. A folder move whose operand the shell builds (MOVE: `cd "${PWD%/*}"`, `cd "$(dirname "$PWD")"`), in
    shell code or an interpreter's, is a climb too. And code that is risky (shells: the shell code among the texts, all
    of them by default; codes) keeps the broad rule: any word with a held part names one; only code with none of it is
    read by the narrowed words above. And any interpreter's code (codes) keeps the broad rule whole for the words of the
    texts, which it may climb from by a call (dirname, .parent, a shell call)."""
    words = [word for text in texts for word in code_words(text) + built_words(text)]
    words += [word for code in codes for word in code_words(code) if "/" in word or word == ".."]
    words += [word for code in codes for word in built_words(code)]
    if any(could_name(word, cwd) for word in words):
        return True
    if (any(risky(text) for text in (texts if shells is None else shells)) or any(risky(code, False) for code in codes)
            ) and any(held_part(word) for word in words):
        return True
    if codes and any(held_part(word) for text in texts for word in code_words(text)):
        return True
    cuts = [run for text in texts for run in cut_words(text)]
    if any(held_part(word) for run in cuts for word in code_words(run)):
        return True
    # a variable that shell code joins: not the command's own words' (`M=<path>; python3 - "$M/x.csv"`)
    joined = {name for text in texts if len(RUN_SPLIT.split(text.strip())) > 1
              for run in cut_words(text) for name in re.findall(r"\$\{?(\w+)", run)}
    if any(held_part(word) for text in texts for depth in depths(text) for run in RUN_SPLIT.split(depth)
           if run.split("=", 1)[0] in joined and "=" in run for word in code_words(run.split("=", 1)[1])):
        return True
    if any(POSITIONAL.search(run) for run in cuts) and any(held_part(word) for word in words):
        return True
    built_move = any(BUILT_MOVE.search(move) for text in list(texts) + list(codes) for depth in depths(text)
                     for move in MOVE.findall(depth))
    return (built_move or any(climbs(word) for word in words)) and any(held_part(word) for word in words)


def qualifier_codes(line):
    """The shell code each zsh glob qualifier in the line runs. zsh, the Bash tool's shell, reads a `(...)` glued to a
    word outside quotes as that word's glob qualifiers, even with no `*` (checked on the Mac, zsh 5.9:
    `echo .(e:'print x':)`, `"."(e:...:)`, `.(e,...,)`, `.(+f)` and, with extendedglob, `.(#qe:...:)` each ran their
    code), and runs each `e` string (any delimiter; `[`, `{`, `<` and `(` close at their pair) and each `+` name for
    every file the glob matches. A `(` after a space, an operator, `$`, `<` or `>` (a subshell, `$(`, `<(`, `>(`) and a
    function's `()` aren't qualifiers, but one after an escaped character (`x\\ (e:...:)`) or a numeric glob's `>`
    (`<->(e:...:)`, `x<1-5>(+f)`) is (read so, unchecked on zsh), and so is one after `=`: in an
    argument zsh reads `a=(e:...:)` and `--x=(e:...:)` as qualifiers, and an array's `NAME=(...)` or zsh's `=(...)` is
    read so too, whatever words or glob groups stand before it. Any `e` or `+` in one counts: more code read, never
    less."""
    codes, quote, i, escaped = [], "", 0, -1
    while i < len(line):
        c = line[i]
        if quote in ("'", "$'"):
            if quote == "$'" and c == "\\":
                i += 1
            elif c == "'":
                quote = ""
        elif c == "\\":
            i += 1
            escaped = i
        elif quote:
            quote = "" if c == '"' else quote
        elif c == "'" or c == '"':
            quote = c
        elif line.startswith("$'", i):
            quote, i = "$'", i + 1
        elif (c == "(" and i and line[i + 1:i + 2] != ")"
              and (i - 1 == escaped or not line[i - 1].isspace() and line[i - 1] not in ";&|(<>$"
                   or re.search(r"<\d*-\d*>$", line[:i]))):
            end, depth, inner = i + 1, 1, ""
            while end < len(line) and depth:  # its `)`, past nested pairs and quotes
                d = line[end]
                if d in "'\"":
                    close = line.find(d, end + 1)
                    end = len(line) if close < 0 else close
                elif d == "\\":
                    end += 1
                else:
                    depth += {"(": 1, ")": -1}.get(d, 0)
                end += 1
            inner = dequoted(line[i + 1:end - 1 if not depth else end])
            k = 0
            while k < len(inner):
                if inner[k] in "e+" and k + 1 < len(inner):
                    named = re.match(r"\w+", inner[k + 1:]) if inner[k] == "+" else None
                    if named:
                        codes.append(named[0])
                        k += 1 + len(named[0])
                        continue
                    close = inner.find(PAIRS.get(inner[k + 1], inner[k + 1]), k + 2)
                    close = len(inner) if close < 0 else close
                    codes.append(inner[k + 2:close])
                    k = close + 1
                    continue
                k += 1
            i = end
            continue
        i += 1
    return [code for code in codes if code.strip()]


def qualified(line):
    """The simple commands of the code the line's zsh glob qualifiers run (qualifier_codes), theirs too; one that
    won't split is read as `eval` with its words, which no check passes as a read."""
    commands = []
    for code in qualifier_codes(line):
        for piece in code.split("\n"):
            try:
                commands += simple_commands(piece)
            except ValueError:
                commands.append((["eval", *piece.split()], []))
            commands += qualified(piece)
    return commands


def first(words):
    """The index of the simple command's program, past any VAR=value words and the shell keywords it follows
    (PREFIXES: `do`, `then`, `!`, ...), or None."""
    return next((i for i, word in enumerate(words) if not ASSIGNMENT.match(word) and word not in PREFIXES), None)


def program(words):
    """The simple command's program, its path and case dropped; "" if none."""
    at = first(words)
    return "" if at is None else PurePosixPath(words[at]).name.casefold()


def in_answers(path) -> bool:
    """Whether a path (absolute, normalized) lies in a knowledge/board/answers, workspaces/board-desk or
    board-desk-seal folder, any case, or is a folder holding one: knowledge, knowledge/board or workspaces, with the
    rest of it beneath on disk (`rm -r knowledge/board`), or one with a
    board-desk-seal folder in it (the seal's, answers_seal.SEAL_DIR)."""
    parts = [part.casefold() for part in PurePosixPath(path).parts]
    if any(tuple(parts[i:i + len(held)]) == held for held in HELD_PARTS for i in range(len(parts))):
        return True
    if os.path.isdir(os.path.join(path, *HELD_PARTS[-1])):  # the seal's parent folder
        return True
    return any(tuple(parts[-k:]) == held[:k] and os.path.isdir(os.path.join(path, *held[k:]))
               for held in HELD_PARTS for k in range(1, len(held)))


def holds(folder) -> bool:
    """Whether a held folder lies right beneath this one (a checkout's top)."""
    return any(os.path.isdir(os.path.join(folder, *held)) for held in HELD_PARTS)


def checkout_holds(folder) -> bool:
    """Whether the checkout around folder (the nearest folder up with a .git) holds a held folder; an unknown folder
    (a `cd` to a variable) does."""
    while folder:
        if os.path.lexists(os.path.join(folder, ".git")):
            return holds(folder)
        parent = posixpath.dirname(folder)
        if parent == folder:
            return False
        folder = parent
    return True


def git_folder(words, cwd):
    """The folder a git command runs in: the cwd, moved by each -C."""
    folder, i = cwd, first(words) + 1
    while i < len(words) and words[i].startswith("-"):
        if words[i] == "-C" and i + 1 < len(words):
            folder = resolve(folder, words[i + 1])
        i += 2 if words[i] in ("-C", "-c") else 1
    return folder


def discards(words, cwd, alone=False) -> bool:
    """Whether a git command may throw away uncommitted changes across a checkout that holds a held folder, where
    the reader's rows wait for the CEO's commit (`git stash -u`): stash but
    list and show, clean but -n, reset --hard, --merge or --keep (but one in a linked worktree that changes no file
    under a held folder, when every other simple command of the call is a read that moves no ref and stages nothing:
    alone, and reset_keeps), checkout, restore or switch forced, or checkout or restore (of the working files) given
    the checkout's top folder. A path inside is names_answers' own check."""
    sub = git_subcommand(words)
    folded = [word.casefold() for word in words]
    raw = words[folded.index(sub) + 1:] if sub in folded else []  # restore's -S (staged) isn't -s (source)
    after = [word.casefold() for word in raw]
    folder = git_folder(words, cwd)
    if sub == "stash":
        hit = not after or after[0] not in ("list", "show")
    elif sub == "clean":
        hit = not any(word == "--dry-run" or re.fullmatch(r"-[a-z]*n[a-z]*", word) for word in after)
    elif sub == "reset":
        hit = any(word in ("--hard", "--merge", "--keep") for word in after) and not (alone and reset_keeps(words, cwd))
    elif sub in ("checkout", "restore", "switch"):
        index_only = sub == "restore" and any(w in ("--staged", "-S") for w in raw) and not any(
            w in ("--worktree", "-W") for w in raw)
        hit = any(word in ("-f", "--force", "--discard-changes") for word in after) or not index_only and any(
            word == ":/" or (path and holds(path)) for word, path in ((w, resolve(folder, w)) for w in after
                                                                      if not w.startswith("-")))
    else:
        return False
    return hit and checkout_holds(folder)


def linked_top(folder):
    """The top of the checkout around folder when it is a linked worktree (its .git a file, not a folder: a
    `git worktree add`'s), else None."""
    while folder:
        dot_git = os.path.join(folder, ".git")
        if os.path.lexists(dot_git):
            return folder if os.path.isfile(dot_git) and not os.path.islink(dot_git) else None
        parent = posixpath.dirname(folder)
        if parent == folder:
            return None
        folder = parent
    return None


def reset_keeps(words, cwd) -> bool:
    """Whether a git reset --hard, --merge or --keep leaves every file under a held folder as it is, so it writes
    nothing there: it runs in a linked worktree (linked_top; the main checkout's answers wait there for
    the CEO's commit, so a reset there stays refused), git's own options are only -C, its own only --hard, --merge,
    --keep and -q, it names at most one commit, with no `$`, backquote or glob the shell may change, and the commit's
    files under knowledge/board/answers and workspaces/board-desk are the working files there (same_files). Its
    caller passes it only when every other simple command of the call is a read that moves no ref and stages nothing
    (discards' alone: `git fetch o && git reset --hard o/x` and `git commit ... && git reset --hard HEAD~1` reset to a
    commit this check can't see, and `git add -A && git reset --hard` deletes a file this check saw untracked)."""
    i = first(words) + 1
    while i < len(words) and words[i].startswith("-"):
        if words[i] != "-C" or i + 1 >= len(words):
            return False
        i += 2
    if i >= len(words) or words[i].casefold() != "reset":
        return False
    options = [word for word in words[i + 1:] if word.startswith("-")]
    commits = [word for word in words[i + 1:] if not word.startswith("-")]
    if (any(word not in ("--hard", "--merge", "--keep", "-q", "--quiet") for word in options) or len(commits) > 1
            or any(c in word for word in commits for c in "$`*?[")):
        return False
    top = linked_top(git_folder(words[:i], cwd))
    return bool(top) and same_files(top, commits[0] if commits else "HEAD")


def listed(top, *args):
    """{path: (mode, object id)} from `git ls-tree -r -z` or `git ls-files -s -z` under the held folders in top. Each
    reads only git's objects and index, so no clean filter, textconv, external diff or fsmonitor runs; no lazy fetch, no
    optional lock. OSError or SubprocessError on a git error or no answer in 2 seconds."""
    result = subprocess.run(["git", "--no-optional-locks", "-C", top, "-c", "core.fsmonitor=false", *args, "--",
                             *("/".join(held) for held in HELD_PARTS)], capture_output=True, timeout=2, check=True,
                            env={**os.environ, "GIT_NO_LAZY_FETCH": "1"})
    found = {}
    for entry in filter(None, result.stdout.split(b"\0")):
        meta, path = entry.split(b"\t", 1)
        fields = meta.split()
        found[path] = (fields[0].decode(), fields[2 if args[0] == "ls-tree" else 1].decode())
    return found


def blob(path):
    """(mode, bytes) git would store for the working file at path, read here, never by git (no filter runs): a
    symlink's target or a regular file's bytes; None for anything else (same_files hashes them as the commit's ids
    are: sha1, 40 hex digits; sha256, 64)."""
    info = os.lstat(path)
    if stat.S_ISLNK(info.st_mode):
        mode, data = "120000", os.readlink(os.fsencode(path))
    elif stat.S_ISREG(info.st_mode):
        mode = "100755" if info.st_mode & stat.S_IXUSR else "100644"
        with open(path, "rb") as f:
            data = f.read()
    else:
        return None
    return mode, data


def same_files(top, commit) -> bool:
    """Whether a reset of the linked worktree at top to commit writes no file under a held folder: each path the
    commit or the index has there is the commit's file in the working tree, in bytes and mode, or is gone from both
    the commit and the working tree (an untracked file the reset leaves is no change). The working files are read
    here, never through a symlinked folder; a git error, no answer in 2 seconds, or any doubt counts as a change."""
    try:
        tree = listed(top, "ls-tree", "-r", "-z", "--end-of-options", commit)
        index = listed(top, "ls-files", "-s", "-z")
        for path in set(tree) | set(index):
            parts = os.fsdecode(path).split("/")
            if any(os.path.islink(os.path.join(top, *parts[:k])) for k in range(1, len(parts))):
                return False
            full = os.path.join(top, *parts)
            if path not in tree:
                if os.path.lexists(full):
                    return False
                continue
            mode, oid = tree[path]
            have = blob(full) if os.path.lexists(full) else None
            if have is None or have[0] != mode:
                return False
            digest = hashlib.sha256 if len(oid) == 64 else hashlib.sha1
            if digest(b"blob %d\0" % len(have[1]) + have[1]).hexdigest() != oid:
                return False
    except (OSError, ValueError, IndexError, subprocess.SubprocessError):
        return False
    return True


def resolve(cwd, word):
    """The word as a normalized path against cwd (an option's `--x=` dropped), or None when there is no cwd to resolve
    a relative one against."""
    word = re.sub(r"^--?[\w-]+=", "", word)
    if word.startswith("/"):
        return posixpath.normpath(word)
    return posixpath.normpath(posixpath.join(cwd, word)) if cwd else None


def holds_name(word) -> bool:
    """Whether a relative word (an option's `--x=` dropped), read from a folder the check doesn't know, may be a held
    folder, a folder holding one or a path in one: a held path's part, then that path's next parts or fewer
    (`knowledge`, `x/board`, `board-desk/notion.json`; not `workspaces/system`)."""
    word = re.sub(r"^--?[\w-]+=", "", word)
    if word.startswith("/"):
        return False
    parts = [part.casefold() for part in PurePosixPath(word).parts]
    return any(part == name and (tuple(parts[i + 1:i + len(held) - j]) == held[j + 1:]
                                 or tuple(parts[i + 1:]) == held[j + 1:j + len(parts) - i])
               for held in HELD_PARTS for j, name in enumerate(held) for i, part in enumerate(parts))


def moved(words):
    """(name, operands) when this simple command moves the shell's folder: cd, chdir (zsh's), pushd or popd, also
    after builtin, command, noglob or nocorrect; operands None when the check can't read them
    (a modifier's option, `command -v cd`; a program by its path, `/usr/bin/cd`, which moves nothing). None for any
    other command."""
    at = first(words)
    if at is None:
        return None
    rest, unread = words[at:], False
    while rest and rest[0] in MODIFIERS:
        rest = rest[1:]
        while rest and rest[0].startswith("-"):
            rest, unread = rest[1:], True
    name = PurePosixPath(rest[0]).name.casefold() if rest else ""
    if name not in MOVES:
        return None
    return name, (None if unread or "/" in rest[0] else rest[1:])


def searched(word_lists) -> bool:
    """Whether a cd may search CDPATH (zsh's cdpath) or take a variable's value (CDABLE_VARS): the environment sets
    CDPATH, a word of the command (its simple commands' words) names either
    (`CDPATH=knowledge; cd board; rm -rf answers`; zsh reads an option's name in any case and with any `_`), or a set,
    setopt or shopt may set an option (zsh's `set -T` is CDABLE_VARS)."""
    return bool(os.environ.get("CDPATH")) or any(
        "cdpath" in word.casefold() or "cdablevars" in word.casefold().replace("_", "")
        or word.casefold() in ("set", "setopt", "shopt") for words in word_lists for word in words)


def moved_to(name, operands, cwd, stack, search=False):
    """The folder a move (moved) leaves the shell in, or None when the check can't know it: popd's is the folder the
    last pushd left (stack, changed here), a bare pushd's the one it swaps with; a cd's, chdir's or pushd's one
    operand resolved against the cwd, but none, several (zsh's `cd old new`), or one with a `$`, a backquote, a glob or
    brace character, or a leading `~`, `-` (`cd -`, `cd -P x`), `+` or `=` leave it unknown, and so does a relative
    one CDPATH may take (search: searched), all but `.`, `..` and those that start `./` or `../`."""
    if operands is None or name == "popd" and operands:
        return None
    if name == "popd":
        return stack.pop() if stack else None
    if name == "pushd" and not operands:
        if not stack:
            return None
        stack[-1], cwd = cwd, stack[-1]
        return cwd
    if name == "pushd":
        stack.append(cwd)
    target = operands[0] if len(operands) == 1 else ""
    if not target or target[0] in "~-+=" or re.search(r"[$`*?\[\]{}]", target):
        return None
    if search and target not in (".", "..") and not target.startswith(("/", "./", "../")):
        return None
    return resolve(cwd, target)


def interpreted(words):
    """The indexes of this simple command's words that are code an interpreter (CODE: python, perl, node, ruby, ...;
    after a wrapper too) is given: the word after its -c, -e, perl's -E or --eval, and a `-` (code read from its
    input); none for eval, source or `.`, whose code is shell code."""
    at, name = first(words), run_name(words)
    if at is None or not CODE.match(name) or name in ("eval", "source", "."):
        return set()
    flags = [i for i in range(at + 1, len(words)) if CODE_FLAG.match(words[i])
             or name.startswith("perl") and re.match(r"^-[A-Za-z]*E$", words[i])]
    return {i + 1 for i in flags} | {i for i in range(at + 1, len(words)) if words[i] == "-"}


def feeds(words) -> bool:
    """Whether this simple command runs code that may take the command's other words, or a value set before it, as
    its own: a shell (`sh -c`, `bash x.sh`), eval, source or `.` (also after builtin, command, noglob or nocorrect), a
    zsh NAME[key]=value, or an interpreter given code (interpreted: python's -c, perl's -e or -E, node's -e or --eval,
    ruby's -e; it reads sys.argv, @ARGV, process.argv)."""
    if any(INDEXED.match(word) for word in words):
        return True
    at, name = first(words), run_name(words)
    rest = [] if at is None else words[at:]
    while rest and rest[0] in MODIFIERS:
        rest = rest[1:]
        while rest and rest[0].startswith("-"):
            rest = rest[1:]
    return name in SHELLS | {"eval"} or bool(rest) and rest[0] in ("eval", "source", ".") or bool(interpreted(words))


def names_answers(commands, cwd) -> bool:
    """Whether the cwd, or any word or redirection target of these commands resolved against the cwd and the folder
    moves before it (moved: cd, chdir, pushd, popd), lies in a knowledge/board/answers folder. A move the check can't
    follow (moved_to: to a variable, `~` or `-`) leaves the cwd unknown, and so does eval or a zsh NAME[key]=value
    (its code, or a function or alias it defines, may move it); then a relative word with a held folder's part in it
    (knowledge, board, answers, workspaces, board-desk) names one. Shell code a
    command gives as words (shell_code: a shell's -c string, eval's, a NAME[key]= value, git's) names one so read from
    any folder too."""
    if cwd and in_answers(posixpath.normpath(cwd)):
        return True
    # a reset may pass only when every other simple command is a read that moves no ref and stages nothing (reset_keeps)
    moving = sum(1 for words, targets in commands if read_reason(words, targets) is not None
                 or program(words) == "git" and git_subcommand(words) in ("add", "commit", "push"))
    # code a command runs may take any word of the command as its own (`sh -c 'cd "$1"; rm -rf ..' _
    # knowledge/company`, `x=knowledge/company; eval 'cd $x; rm -rf ..'`, python's sys.argv): then a word or value
    # that may name one, read from any folder, names one (feeds, loose_names),
    # and so does a path in an interpreter's own code, whose other words aren't paths (`python3 -c 'answers = 1'`)
    if any(feeds(words) for words, _ in commands) and loose_names(
            [word for words, targets in commands for code in [interpreted(words)]
             for i, word in enumerate(words + targets) if i not in code], cwd,
            [words[i] for words, _ in commands for i in interpreted(words) if i < len(words)],
            [text for words, _ in commands for text in shell_code(words)]):
        return True
    stack, search = [], searched(words for words, _ in commands)  # the folders pushd left, for popd; CDPATH
    for words, targets in commands:
        at = first(words)
        operands = [] if at is None else words[at + 1:]
        code = shell_code(words)
        if any(path and in_answers(path) for path in (resolve(cwd, word) for word in operands + targets)):
            return True
        if not cwd and any(holds_name(word) for word in operands + targets) or loose_names(code, cwd):
            return True
        if program(words) == "git" and discards(words, cwd, moving <= 1):
            return True
        move = moved(words)
        if move:
            cwd = moved_to(*move, cwd, stack, search)
            if cwd and in_answers(cwd):
                return True
        elif program(words) == "eval" or any(INDEXED.match(word) for word in words):
            cwd = None
    return False


def git_subcommand(words):
    skip = False
    for word in words[first(words) + 1:]:
        if skip:
            skip = False
        elif word in ("-C", "-c"):
            skip = True
        elif not word.startswith("-"):
            return word.casefold()
    return ""


def sed_reason(words):
    """Why this sed isn't a read: -n (or --quiet, --silent), each script SED_PRINT's with no `$` the shell may expand
    (EXPANDS), no option but -E, -r and -e (so no -i, -I or -f), and a `$` word only after a literal `--`, or None.
    BSD sed (the Mac's) takes a `$f` set to -i as an option right after `-e SCRIPT`, and GNU sed anywhere before
    `--`: `sed -n -e 1p -- "$f"` reads."""
    quiet, scripts, operands, script_next, rest = False, [], [], False, words[first(words) + 1:]
    files = len(rest)  # where the words after a literal `--` start: files (or the script, with no -e)
    for n, word in enumerate(rest):
        if script_next:
            scripts.append(word)
            script_next = False
        elif word == "--" and files == len(rest):
            files = n + 1
        elif n >= files:
            operands.append(word)
        elif word in ("--quiet", "--silent", "--regexp-extended"):
            quiet = quiet or word != "--regexp-extended"
        elif word == "--expression" or re.fullmatch(r"-[nEr]*e?", word) and word != "-":
            quiet = quiet or "n" in word and word != "--expression"
            script_next = word.endswith("e") or word == "--expression"
        elif word.startswith("--expression="):
            scripts.append(word.split("=", 1)[1])
        elif word.startswith("-") and word != "-":
            return "`sed` with an option but -n, -E, -r or -e"
        else:
            operands.append(word)
    scripts = scripts or operands[:1]
    if not quiet or not scripts or script_next or not all(SED_PRINT.match(script) for script in scripts):
        return "`sed` but -n with a script that only prints (p or =)"
    if any(EXPANDS.search(script) for script in scripts):  # `sed -n "$p"`, with p set to `w x`
        return "`sed` with a `$` the shell may expand in its script (the last line: `tail -n 1`)"
    if any(EXPANDS.search(word) for word in rest[:files]):  # `sed -n -e 1p $f x`, with f set to -i
        return "`sed` with a `$` the shell may expand before `--` (a file after it: `sed -n -e 1p -- \"$f\"`)"
    return None


def sort_reason(words):
    """Why this sort may write a file or run a program, or None: -o or -T (an output file, a temp folder), a long
    option one may shorten to --output, --temporary-directory or --compress-program, or TMPDIR set
    before it."""
    if any(word.startswith("TMPDIR=") for word in words[:first(words)]):
        return "`sort` with an output file, a temp folder or a compress program"
    for word in words[first(words) + 1:]:
        if word == "--":
            break
        if word.startswith("--"):
            option = word[2:].split("=", 1)[0]
            if option and any(name.startswith(option) for name in ("output", "temporary-directory",
                                                                    "compress-program")):
                return "`sort` with an output file, a temp folder or a compress program"
        elif word.startswith("-"):
            for c in word[1:]:
                if c in "oT":
                    return "`sort` with an output file, a temp folder or a compress program"
                if c in "tkS":  # the rest of the word is its value: `-t:`, `-k2,2`
                    break
    return None


def environ_set(words):
    """The name of a variable the shell reads (SPECIAL: PATH, IFS, TMPDIR, zsh's `path`, `commands`, `functions`, ...)
    or the environment exports (a later program reads its new value) this simple command sets for the commands after it,
    or None: a for loop's variable, a read's (`-aNAME`, zsh's `-ANAME` and `NAME?prompt` too), a printf -v's, an
    assignment with no program (`do TMPDIR=x`), or a `${NAME=x}`, `${NAME:=x}` or zsh's `${NAME::=x}`, or one a read
    program takes from the environment to run one (EXPORTED_RUNS). Not a name for being upper-case (`S=/x; ls $S`)."""
    at = first(words)
    rest = [] if at is None else words[at + 1:]
    if at is None:
        names = [word.split("=", 1)[0] for word in words if ASSIGNMENT.match(word)]
    elif words[at] == "for":
        names = rest[:1]
    elif program(words) == "read":
        names = [re.sub(r"^-[A-Za-z]*?[aA]", "", word).split("?", 1)[0] for word in rest]  # zsh's -A too
    elif program(words) == "printf":
        names = [rest[n + 1] if word == "-v" else word[2:] for n, word in enumerate(rest)
                 if word.startswith("-v") and (word != "-v" or n + 1 < len(rest))]
    else:
        names = []
    names += re.findall(r"\$\{(?:\([^)]*\))?[=~^#]*(\w+):{0,2}=", " ".join(words))
    return next((name for name in names if name in SPECIAL or name in os.environ or EXPORTED_RUNS.match(name)), None)


def git_runs(words) -> bool:
    """Whether a git command names an option that writes a file or runs a program: one of git's own but -C, a -c
    whose key runs nothing (SAFE_CONFIG: core.quotepath, user.name, user.email, color.*, advice.*) and GIT_OWN's (a -c
    may name a program git runs, core.editor, core.pager, core.fsmonitor, alias.*, diff.external, or a config file
    that does, include.path; --config-env, --exec-path, --git-dir and --work-tree such a config or program); or, before
    its `--`, --output, --open-files-in-pager, --receive-pack, --upload-pack or --exec, or a prefix of one (git takes a
    long option's unique prefix; `--o` too), or grep's -O, alone or in a cluster (`-iOrm`: rm on every file it
    matches)."""
    i = first(words) + 1
    while i < len(words) and words[i].startswith("-"):  # git's own options, to the subcommand
        if words[i] == "-C" or words[i] == "-c" and i + 1 < len(words) and SAFE_CONFIG.match(words[i + 1]):
            i += 2
        elif words[i] in GIT_OWN:
            i += 1
        else:
            return True
    rest = words[i:]
    rest = rest[:rest.index("--")] if "--" in rest else rest
    grep = git_subcommand(words) == "grep"
    for word in rest:
        option = word[2:].split("=", 1)[0]
        if word.startswith("--") and option and any(name.startswith(option) for name in GIT_RUNS):
            return True
        if grep and re.match(r"-[^-]", word):
            for c in word[1:]:
                if c == "O":
                    return True
                if c in "efABCm":  # the rest of the word is its value: `-e-O`, `-m2`
                    break
    return False


def git_code(words):
    """The code a git command may run from its own words: each value set
    before it (`GIT_EXTERNAL_DIFF=CMD git diff`), each of its own -c's value (`core.pager=CMD`, `alias.x=!CMD`), and,
    before its `--`, --receive-pack's, --upload-pack's and --exec's (or a prefix's); [] for any other command. Its
    words are read as paths (names_answers) and as code (code_strings: a run of board_desk.py, a read of the token)."""
    at = first(words)
    if at is None or program(words) != "git":
        return []
    found = [word.split("=", 1)[1] for word in words[:at] if ASSIGNMENT.match(word)]
    own = True  # still among git's own options, before the subcommand
    for n, word in enumerate(words[at + 1:], at + 1):
        if word == "--":
            break
        option = word[2:].split("=", 1)[0] if word.startswith("--") else ""
        if own and word == "-c" and n + 1 < len(words):
            found.append(words[n + 1].split("=", 1)[-1])
        elif option and any(name.startswith(option) for name in ("receive-pack", "upload-pack", "exec")):
            found.append(word.split("=", 1)[1] if "=" in word else words[n + 1] if n + 1 < len(words) else "")
        own = own and (word.startswith("-") or words[n - 1] in ("-C", "-c"))
    return found


def read_reason(words, targets):
    """Why this simple command isn't a read that leaves the answers folder as it is, or None. A for or while loop's
    own words are reads (`for NAME [in WORDS]`, do, while, done), so a loop of
    reads is one; if, then, until and the other keywords (PREFIXES) aren't."""
    at = first(words)
    keyword = next((word for word in (words if at is None else words[:at]) if word in PREFIXES - LOOP), None)
    if keyword:
        return f"`{keyword}` isn't a read"
    environ = environ_set(words)
    if environ:
        return f"`{environ}` set for the commands after it (the shell reads it or the environment exports it)"
    name, rest = program(words), ([] if at is None else words[at + 1:])
    loop = (at is None and any(word in LOOP for word in words)
            or at is not None and words[at] == "done" and all(word.isdigit() for word in rest)  # `done 2>/dev/null`
            or at is not None and words[at] == "for" and bool(rest) and bool(NAME.match(rest[0]))
            and (len(rest) == 1 or rest[1] == "in"))
    # a plain assignment (`t=<path>`) to a variable neither the shell reads nor the environment exports (both above)
    # changes nothing a read does
    plain = at is None and bool(words) and all(ASSIGNMENT.match(word) for word in words)
    if not loop and name in ("sed", "sort"):
        reason = sed_reason(words) if name == "sed" else sort_reason(words)
        if reason:
            return reason
    elif not loop and not plain and name not in READS:
        return f"`{name}` isn't a read" if name else "a bare redirection"
    if any(target != "/dev/null" and not target.isdigit() and target != "-" for target in targets):
        return "an output redirection"
    # a variable set for this read alone that a program reads may make it run another or write a file
    # (GIT_EXTERNAL_DIFF, GIT_CONFIG_*, GIT_TRACE=<file>, PATH, HOME); not a
    # locale, IFS for read, or a pager that is cat
    for var, value in (word.split("=", 1) for word in words[:at or 0] if ASSIGNMENT.match(word)):
        if ((ENVIRON.match(var) or var in SPECIAL) and not LOCALE.match(var) and not (var == "IFS" and name == "read")
                and not (var in ("PAGER", "GIT_PAGER") and value == "cat")):
            return f"`{var}` set for `{name}` (a variable a program reads; a locale passes)"
    # a loop's or read's variable may expand to an action, an option or an output file
    if name in ("find", "sort") and any(EXPANDS.search(word) for word in rest):
        return f"`{name}` with a `$` the shell may expand (to an action or an output file)"
    if name == "git" and any(EXPANDS.search(word) for word in (rest[:rest.index("--")] if "--" in rest else rest)):
        return "`git` with a `$` the shell may expand before `--`"
    if name == "find" and any(word.casefold() in FIND_ACTIONS for word in words):
        return "find with an action"
    if name == "git" and (git_subcommand(words) not in GIT_KEEPS or any(w.startswith("--output") for w in words)):
        return f"`git {git_subcommand(words)}` changes the working files or writes a file"
    if name == "git" and git_runs(words):
        return (f"`git {git_subcommand(words)}` with a file it writes or a program it runs (--output, -O, -c, "
                "--receive-pack, --exec, --git-dir)")
    return None


def desk_command(words):
    """The command a run of board_desk.py in these words is given (None if none), or False if they hold no run."""
    name = program(words)
    if name != DESK and not PYTHON.match(name) and name not in WRAPPERS:
        return False
    folded = [word.casefold() for word in words]
    for i, word in enumerate(folded):
        if PurePosixPath(word).name == DESK:
            return folded[i + 1] if i + 1 < len(folded) else None
        if word == "-m":
            module, at = (folded[i + 1] if i + 1 < len(folded) else ""), i + 2
        else:
            module, at = (word[2:] if word.startswith("-m") else ""), i + 1
        if re.search(r"(?:^|\.)board_desk$", module):
            return folded[at] if at < len(folded) else None
    return False


def runs_code(words):
    """Whether this simple command's program is a shell, an interpreter or a wrapper (which may run one)."""
    name = program(words)
    return name in SHELLS or name in WRAPPERS or bool(CODE.match(name))


def code_strings(words):
    """The code this simple command hands to a shell or an interpreter as words: each `-c` or `-e` string, and
    eval's or source's operands; for git, the code its own words may run (git_code)."""
    if program(words) == "git":
        return git_code(words)
    if not runs_code(words):
        return []
    at = first(words)
    if program(words) in ("eval", "source", "."):
        return [" ".join(words[at + 1:])]
    return [words[i + 1] for i in range(at, len(words) - 1) if CODE_FLAG.match(words[i])]


def shell_code(words):
    """The shell code this simple command gives as words: a shell's -c string
    (sh, bash, zsh, ..., after a wrapper too: `timeout 5 bash -c ...`), eval's operands, each zsh NAME[key]=value's key
    and value (`functions[ls]='rm -rf ...'` makes ls run it, `aliases[x]=...` an alias), and git's (git_code); not an
    interpreter's (python's `-c` code, whose words aren't paths). names_answers reads its words as paths."""
    found = [part for word in words for match in [INDEXED.match(word)] if match for part in match.groups()]
    if run_name(words) in SHELLS | {"eval", "git"}:
        found += code_strings(words)
    return found


def run_name(words):
    """The program this simple command runs: its own, or after a wrapper (and the wrapper's own words: `timeout 5`,
    `nice -n 5`, `sudo -u x`; find, whose -exec runs one, and script too) the first word that names a shell or an
    interpreter (SHELLS, CODE); "" if none."""
    at, name = first(words), program(words)
    if name in WRAPPERS or name in ("find", "script"):
        names = (PurePosixPath(word).name.casefold() for word in words[at + 1:])
        name = next((name for name in names if name in SHELLS or CODE.match(name)), "")
    return name


def reads_token(code: str) -> bool:
    """Whether code a shell or an interpreter is given reads the desk's token: keychain_token; the service's name,
    the account's (`-a notion`) or dump-keychain beside `security`; or adapter_notion with its Notion or Desk made."""
    folded = code.casefold()
    return ("keychain_token" in folded
            or "security" in folded and (KEYCHAIN in folded or "dump-keychain" in folded
                                         or bool(ACCOUNT_TEXT.search(code)))
            or "adapter_notion" in folded and bool(NOTION_MADE.search(code)))


def token_reason(words) -> "str | None":
    """Why this simple command reads or changes the desk's token, or None."""
    at = first(words)
    if at is None:
        return None
    name = program(words)
    if name in WRAPPERS:  # the program it runs: the first word past the wrapper's own options and settings
        name = next((PurePosixPath(word).name.casefold() for word in words[at + 1:]
                     if not word.startswith("-") and not ASSIGNMENT.match(word)), "")
    if name == "security":
        folded = [word.casefold() for word in words]
        if any(KEYCHAIN in word for word in folded):
            return "`security` on its Keychain item"
        if "dump-keychain" in folded:
            return "`security dump-keychain`, which prints every item"
        if any(word == ACCOUNT or re.fullmatch(r"-[a-z]*a" + ACCOUNT, word) for word in folded):
            return "`security` on its Keychain account"
    if any(reads_token(code) for code in code_strings(words) + shell_code(words)):
        return "a read of it in the code this command runs"
    return None


def unquoted(line):
    """The line's text outside single quotes and `$'...'`, where the shell expands nothing."""
    out, quote, i = [], "", 0
    while i < len(line):
        c = line[i]
        if quote in ("'", "$'"):
            if quote == "$'" and c == "\\":
                i += 1
            elif c == "'":
                quote = ""
            i += 1
            continue
        if c == "\\":
            out.append(line[i:i + 2])
            i += 2
            continue
        if quote:  # in double quotes
            quote = "" if c == '"' else quote
        elif c == "'" or line.startswith("$'", i):
            quote, i = ("'", i + 1) if c == "'" else ("$'", i + 2)
            continue
        elif c == '"':
            quote = c
        out.append(c)
        i += 1
    return "".join(out)


def substitutions(line):
    """The text inside each `$(...)` and backquote pair of the line outside single quotes and `$'...'`, where the
    shell runs it (nested ones within it; to the line's end for one left open)."""
    found, quote, i = [], "", 0
    while i < len(line):
        c = line[i]
        if quote in ("'", "$'"):
            if quote == "$'" and c == "\\":
                i += 1
            elif c == "'":
                quote = ""
        elif c == "\\":
            i += 1
        elif not quote and c == "'":
            quote = "'"
        elif not quote and line.startswith("$'", i):
            quote, i = "$'", i + 1
        elif c == '"':
            quote = "" if quote else '"'
        elif line.startswith("$(", i):
            depth, j = 1, i + 2
            while j < len(line) and depth:
                depth += {"(": 1, ")": -1}.get(line[j], 0)
                j += 1
            found.append(line[i + 2:j - 1 if not depth else j])
            i = j
            continue
        elif c == "`":
            j = line.find("`", i + 1)
            j = len(line) if j < 0 else j
            found.append(line[i + 1:j])
            i = j + 1
            continue
        i += 1
    return found


def commit_message(words):
    """The indexes of a git commit's message words: each -m's or --message's value (`-am` too), and -mX and
    --message=X."""
    if program(words) != "git" or git_subcommand(words) != "commit":
        return set()
    i, skip = first(words) + 1, False
    while i < len(words) and (skip or words[i].startswith("-")):  # git's own options, to the subcommand
        skip, i = not skip and words[i] in ("-C", "-c"), i + 1
    found, i = set(), i + 1
    while i < len(words) and words[i] != "--":
        word = words[i]
        if word == "--message" or re.fullmatch(r"-[A-Za-z]*m", word):
            found.add(i + 1)
            i += 1
        elif word.startswith("--message=") or re.fullmatch(r"-m.+", word, re.S):
            found.add(i)
        i += 1
    return found


def text_only(lines, bodies, cwd) -> bool:
    """Whether the command names a held folder only in text it prints or writes elsewhere, so it writes nothing there
    (`printf '...' > $S/x` of a row quoting knowledge/board/answers/<week>.md). The text is the operands of echo or
    printf (no -v) whose output goes into no pipe, a git commit's message (commit_message), and the body of a heredoc on
    a line of cat, tee and plain assignments only, with no pipe, whose word was quoted or whose body holds no `$` or
    backquote. Everything else, the words, targets and sources, other bodies and each assignment's value, is read as
    before: it may name no held folder (FOLDER, names_answers), and each simple command must be such a text command, a
    read (read_reason), a plain assignment to a variable neither the shell reads (SPECIAL: PATH, IFS, CDPATH, ...) nor
    the environment exports, or `date` given only options and a +format. So nothing but a read can take the text, and
    nothing can change what echo, printf, cat or tee are: no shell or interpreter by any path (python, node, ruby, perl,
    sh, bash, zsh: none is a read, so a command with one keeps the full check: a script may run a file it is given, or
    code a pipe hands it), eval, source, xargs, read, alias, function definition (`()`) or `X=y cmd`, and no `$(`,
    backquote, process substitution, `${`, `$[` or `((` outside single quotes (NESTS), and no code a zsh glob qualifier
    runs (qualifier_codes). A read that runs a program (git push's --receive-pack or --exec, git -c core.editor or
    core.fsmonitor) isn't one (git_runs). A heredoc word the check can't read, or a line that split only without its
    comment (desk_reason), keeps the old check, and so does a command with any other program
    (`echo <folder>; rm -rf /tmp/x`), but one: scripts/second_opinion.py's --brief text is text when that run is the
    call's only simple command and goes into no pipe (brief_words). So text written to a scratch file passes only beside
    reads, by design: another program in the call may run or read that file.

    A `$(date ...)` given only
    options and a +format (DATE_RUN) is read as a word of text, wherever it stands; a gh pr or issue create, comment,
    edit or review (no -e or --editor, which runs gh's editor) is a text command, its --title, --body, -t and -b values
    its text (gh_text); and so is a run of this checkout's own scripts/status_log.py (status_log_run), the body of a
    heredoc on its line its text, its words read as paths."""
    lines = [DATE_RUN.sub("DATE", line) for line in lines]
    bodies = [(at, text if quoted else DATE_RUN.sub("DATE", text), quoted) for at, text, quoted in bodies]
    if any(word is None for line in lines for word, _, _ in scan(line)[0]):
        return False
    if any(nest in unquoted(line) for line in lines for nest in NESTS + ("()",)):
        return False
    if any(qualifier_codes(line) for line in lines):  # code a zsh glob qualifier runs
        return False
    if any(not quoted and ("$" in text or "`" in text) for _, text, quoted in bodies):
        return False
    residue, rest, alone = [], [], sum(len(parts(line)) for line in lines) == 1
    for n, line in enumerate(lines):
        simple = parts(line)
        text_body = any(at == n for at, _, _ in bodies) and not any(piped for *_, piped in simple) and all(
            program(words) in WRITERS or words and first(words) is None or status_log_run(words, cwd)
            for words, *_ in simple)
        residue += [] if text_body else [text for at, text, _ in bodies if at == n]
        for words, targets, sources, piped in simple:
            at, name = first(words), program(words)
            if at is not None and any(ASSIGNMENT.match(word) for word in words[:at]):
                return False  # `X=y cmd`, which may change what cmd is (PATH) or what it reads
            kept = words
            if at is None:  # plain assignments: none to a variable the shell or a later command reads (SPECIAL)
                assigned = [word.split("=", 1) for word in words if ASSIGNMENT.match(word)]
                if not words or any(var in SPECIAL or var in os.environ or holds_name(value)
                                    for var, value in assigned):
                    return False  # holds_name: a value such as `$PWD/knowledge/board`, which resolve can't read
                kept = [":"] + [value for _, value in assigned]  # each value read as a path (names_answers)
            elif name in TEXT and not piped and not (name == "printf"
                                                     and any(word.startswith("-v") for word in words[at + 1:])):
                kept = words[:at + 1]
            elif name in WRITERS and text_body:
                pass
            elif name == "date" and all(word[:1] in "-+" for word in words[at + 1:]):
                pass
            elif not piped and (status_log_run(words, cwd) or gh_text(words) is not None):
                # the row helper's `-` is its rows' file, not code an interpreter reads
                kept = [word for i, word in enumerate(words) if i not in (gh_text(words) or interpreted(words))]
            elif name != "read" and read_reason(words, targets) is None:
                message = commit_message(words)
                kept = [word for i, word in enumerate(words) if i not in message]
            elif alone and not piped and (brief := brief_words(words, cwd)):  # a review brief's text
                kept = [word for i, word in enumerate(words) if i not in brief]
            else:
                return False
            rest.append((kept + sources, targets))
            residue += kept + targets + sources
    return not FOLDER.search("\n".join(residue)) and not names_answers(rest, cwd)


def opinion_script(path, own=None) -> bool:
    """Whether the file at path is this checkout's scripts/second_opinion.py (OPINION; the hook runs from the main
    checkout), or own (status_log_run's STATUS_LOG), or, with the same bytes, a linked worktree's of it (its .git file
    names a folder in this checkout's .git/worktrees/ whose gitdir file names that .git back, as `git worktree add`
    writes them): no other script of that name, whose folder, first on its sys.path, may hold another kb_secrets.py."""
    own = own or OPINION
    own_scripts = os.path.dirname(os.path.realpath(own))
    folder = os.path.dirname(os.path.realpath(path))
    top, main = os.path.dirname(folder), os.path.dirname(own_scripts)
    try:
        if folder != own_scripts:
            with open(os.path.join(top, ".git")) as dot_git:
                named = dot_git.read().strip().removeprefix("gitdir: ")
            if posixpath.dirname(posixpath.normpath(named)) != f"{main}/.git/worktrees":
                return False
            with open(os.path.join(named, "gitdir")) as back:
                if os.path.realpath(back.read().strip()) != os.path.join(top, ".git"):
                    return False
        with open(path, "rb") as given, open(own, "rb") as ours:
            return given.read() == ours.read()
    except (OSError, UnicodeDecodeError):
        return False


def brief_words(words, cwd):
    """The indexes of the words that are scripts/second_opinion.py's --brief text: each exact `--brief`'s next word
    and each `--brief=...` word, before any `--`, in a python run (after options that take no value: INTERPRETER_FLAGS)
    of a file of that name in a scripts folder, resolved against the cwd, that is this checkout's own (opinion_script;
    its other words are read as paths)."""
    at = first(words)
    if at is None or not cwd or not PYTHON.match(program(words)):
        return set()
    i = at + 1
    while i < len(words) and INTERPRETER_FLAGS.match(words[i]):
        i += 1
    script = PurePosixPath(resolve(cwd, words[i])) if i < len(words) else None
    if (not script or script.name != "second_opinion.py" or script.parent.name != "scripts"
            or not os.path.isfile(script) or not opinion_script(script)):
        return set()
    found = set()
    for j in range(i + 1, len(words)):
        if words[j] == "--":
            break
        if words[j] == "--brief" and j + 1 < len(words):
            found.add(j + 1)
        elif words[j].startswith("--brief="):
            found.add(j)
    return found


def status_log_run(words, cwd) -> bool:
    """Whether this simple command is python (with no variable set for it, after options that take no value) given a
    file named status_log.py in a scripts folder, resolved against the cwd, that is this checkout's own
    scripts/status_log.py (opinion_script, STATUS_LOG): the CEO's row helper, which only adds the rows it reads to the
    status log of the file it is given, given just its two files, each plain (PLAIN_OPERAND: no glob, `$`, brace or `~`
    the shell expands past the check), or `-`. text_only reads its words as paths and a quoted heredoc on its line as
    text."""
    if first(words) != 0 or not cwd or not PYTHON.match(program(words)):
        return False
    i = 1
    while i < len(words) and INTERPRETER_FLAGS.match(words[i]):
        i += 1
    script = PurePosixPath(resolve(cwd, words[i])) if i < len(words) else None
    return bool(script and script.name == "status_log.py" and script.parent.name == "scripts"
                and len(words) == i + 3 and all(PLAIN_OPERAND.fullmatch(word) for word in words[i + 1:])
                and os.path.isfile(script) and opinion_script(script, STATUS_LOG))


def gh_text(words):
    """The indexes of a gh pr or issue create, comment, edit or review's text (GH_TEXT): each --title, --body, -t and
    -b's next word, and --title=..., --body=..., -tX and -bX, before any `--`; None for any other command, a gh with a
    variable set for it, or one given -e or --editor, which runs gh's editor, or a cluster of short options. text_only
    reads its other words as paths."""
    if first(words) != 0 or program(words) != "gh" or len(words) < 3 or (words[1], words[2]) not in GH_TEXT:
        return None
    found, j = set(), 3
    while j < len(words) and words[j] != "--":
        word = words[j]
        if word in ("--title", "-t", "--body", "-b"):
            found.add(j + 1)
            j += 2
            continue
        if word.startswith(("--title=", "--body=")) or re.fullmatch(r"-[tb].+", word, re.S):
            found.add(j)
        elif word == "--editor" or word.startswith("--editor=") or re.fullmatch(r"-[^-].+", word, re.S):
            return None
        elif word == "-e":
            return None
        j += 1
    return found


def script_run(words, targets, sources, fed, cwd) -> bool:
    """Whether this simple command is python given a script file that exists (after options that take no value and
    name no code: no -c, -m or -), whose words, redirections and here-strings can't name or reach a held folder: none
    holds knowledge, workspaces, board or answers (HELD_NAME, any case), a `$`, a backquote, a glob or brace
    character, or a leading `~` or `=`, and none resolves to the cwd, a folder above it, a folder holding a held
    folder or a path in one; no pipe feeds it (fed) and no shell keyword stands before it."""
    at = first(words)
    if at is None or fed or not PYTHON.match(program(words)) or any(word in PREFIXES for word in words[:at]):
        return False
    i = at + 1
    while i < len(words) and INTERPRETER_FLAGS.match(words[i]):
        i += 1
    script = resolve(cwd, words[i]) if i < len(words) and not words[i].startswith("-") else None
    if not script or not os.path.isfile(script):
        return False
    for word in words + targets + sources:
        if HELD_NAME.search(word) or re.search(r"[$`*?\[\]{}]", word) or word.startswith(("~", "=")):
            return False
        path = resolve(cwd, word)
        if path and (path == cwd or cwd.startswith(path.rstrip("/") + "/") or holds(path) or in_answers(path)):
            return False
    return True


def parents_only(command, lines, bodies, cwd) -> bool:
    """Whether each simple command of the command is a read, which may name a folder holding a held folder
    (knowledge, knowledge/board, workspaces) or a held folder in a form FOLDER doesn't take
    (`knowledge/board/./answers`), or a run of a python script file that can't reach one (script_run), so nothing it
    names is written (`python3 scripts/kb_lint.py 2>&1 | grep ...; git status --short knowledge/ | head -6`). Every
    other simple command is a read (read_reason) but cd and read, which may move the runs' folder or feed them; the text
    holds no held folder's path (FOLDER), no `$(`, backquote, `<(`, `>(`, `${`, `$[` or `((` outside single quotes
    (NESTS), no function definition, no code of a zsh glob qualifier, no heredoc word the check can't read and no
    heredoc body with a held path's part; the cwd is known; and at least one such run is there. Narrow, by
    design: any other program keeps the full check, since a shell builtin (`hash ls=/bin/rm`) or a
    git command (`git config diff.external /bin/rm`) may change what a later read in the same command does."""
    if not cwd or FOLDER.search(command):
        return False
    if any(word is None for line in lines for word, _, _ in scan(line)[0]):
        return False
    if any(nest in unquoted(line) for line in lines for nest in NESTS + ("()",)):
        return False
    if any(qualifier_codes(line) for line in lines) or any(HELD_NAME.search(text) for _, text, _ in bodies):
        return False
    cwd, ran = posixpath.normpath(cwd), False
    for line in lines:
        fed = False
        for words, targets, sources, piped in parts(line):
            if script_run(words, targets, sources, fed, cwd):
                ran = True
            elif read_reason(words, targets) is not None or program(words) in ("cd", "read"):
                return False
            fed = piped
    return ran


def reset_hint(parsed, lines, cwd, ceo) -> str:
    """For a refused call of several simple commands whose first is a git reset --hard, --merge or --keep (no word
    before git, no redirection, no zsh glob qualifier on its line) that passes in its own call: the text naming that
    form, the one retry a blocked agent is allowed (once, in exactly the form the block message names); "" otherwise.
    Only the first: a command before the reset (a commit, a reset --soft, a fetch, a checkout -b, a pushd) may move the
    ref, the branch or the folder it resets, so alone it would reset another commit or checkout."""
    if sum(len(line) for line in parsed) < 2 or not parsed[0]:
        return ""
    words, targets = parsed[0][0]
    if (program(words) != "git" or first(words) != 0 or targets or git_subcommand(words) != "reset"
            or not any(word in ("--hard", "--merge", "--keep") for word in words) or qualifier_codes(lines[0])):
        return ""
    form = shlex.join(words)
    return f"; run the reset in its own call: `{form}`" if one_reason(form, cwd, ceo) is None else ""


def unsplit_reason(command, inside, run_form) -> "str | None":
    """Why a command with a line that won't split may not run, or None: it holds a read of the token, names the
    folder (or runs inside it), or holds a run (RUN_FORM)."""
    folded = command.casefold()
    if ("keychain_token(" in folded or re.search(r"security\s+dump-keychain", folded)
            or "generic-password" in folded and (KEYCHAIN in folded or ACCOUNT_TEXT.search(command))
            or "adapter_notion" in folded and NOTION_MADE.search(command)):
        return TOKEN_MESSAGE.format("a command the check can't split")
    if inside or FOLDER.search(command):
        return ANSWERS_MESSAGE.format("a command the check can't split")
    return DESK_MESSAGE.format("a command the check can't split") if run_form.search(command) else None


def nul_readings(command):
    """The command as bash and as zsh read each `$'...'` that holds a NUL (`\\0`, `\\x0`, `\\c@`): bash ends the
    quote's text there and zsh the whole argument (here: a space after it), or [] if none does. Each is checked whole,
    beside the command as written (desk_reason)."""
    def cut(match, end):
        nul = next((m.start() for m in ESCAPE.finditer(match[1]) if decoded(m) == "\0"), None)
        return match[0] if nul is None else "$'" + match[1][:nul] + "'" + end
    readings = [QUOTED_C.sub(lambda match, end=end: cut(match, end), command) for end in ("", " ")]
    return [] if readings[0] == command else readings


def desk_reason(command: str, cwd: str = "", ceo: bool = False) -> "str | None":
    """Why this agent's Bash command, run in cwd (absolute), may not run, or None. ceo: the CEO's main session's
    (agent_type ceo, no agent_id), which may also run setup and attribution. The command as written is checked, and
    each of its NUL readings (nul_readings): one refused is enough."""
    return next(filter(None, (one_reason(text, cwd, ceo) for text in [command] + nul_readings(command))), None)


def one_reason(command: str, cwd: str, ceo: bool) -> "str | None":
    """desk_reason for one reading of the command."""
    folded = command.casefold()
    commands_allowed, (desk_text, run_form) = CEO_COMMANDS if ceo else DESK_COMMANDS, PATTERNS[bool(ceo)]
    inside = bool(cwd) and in_answers(posixpath.normpath(cwd))
    # the text with every quote, backslash and joined line's newline dropped, which holds each word at each quote depth
    # (`rm -rf kno''wledge`), read in one pass before split; a `$'...'` may spell one in escapes, so a command with one
    # is read whole
    bare = re.sub(r"[\\'\"]", "", folded.replace("\\\n", ""))
    if not inside and "$'" not in command and not any(word in bare for word in (
            "answers", "board", "keychain_token", "notion", "dump-keychain", "knowledge", "workspaces", "git",
            "application support", "local/state")):  # the seal's parent folder (in_answers)
        if not qualifier_codes(command):  # whose code, its own quotes removed, may name one
            return None
    lines, bodies = split(command)
    unsplit = unsplit_reason(command, inside, run_form)
    parsed, whole = [], True
    try:
        for line in lines:
            try:  # with the code its zsh glob qualifiers run, read as commands
                parsed.append(simple_commands(line) + qualified(line))
            except ValueError:  # one that splits only without its comment: unsplit's refusals, then the checks below
                short = uncommented(line)
                if short is None or unsplit:
                    raise
                parsed.append(simple_commands(short) + qualified(short))
                whole = False
    except ValueError:
        return unsplit
    commands = [simple for line in parsed for simple in line]
    qualifier = any(qualifier_codes(line) for line in lines)
    expands = any(EVAL_FLAG.search(unquoted(line)) for line in lines)
    # a heredoc's body a shell reads is shell code, and one an interpreter
    # reads (`python3 - <<'EOF'`) its code; each is read with the words that may feed it
    shell_bodies = [text for at, text, _ in bodies if any(run_name(words) in SHELLS for words, _ in parsed[at])]
    # the row helper's rows in a quoted heredoc are text; an unquoted one's `$(` runs
    code_bodies = [text for at, text, quoted in bodies if any(
        CODE.match(run_name(words)) and run_name(words) not in ("eval", "source", ".")
        and not (quoted and status_log_run(words, cwd)) for words, _ in parsed[at])]
    fed = [word for words, targets in commands for code in [interpreted(words)]
           for i, word in enumerate(words + targets) if i not in code]
    codes = [words[i] for words, _ in commands for i in interpreted(words) if i < len(words)]
    # code the check reads only as text, which may move the folder first, names one by any word that may name one
    # (loose_names): never text_only's or parents_only's
    hidden_code = ((shell_bodies or code_bodies) and loose_names(shell_bodies + fed, cwd, code_bodies + codes,
                                                                 shell_bodies)
                   or (qualifier or expands)
                   and (loose_names(lines + [text for _, text, _ in bodies], cwd) or names_answers(commands, None)))
    if hidden_code or ((inside or FOLDER.search(command) or names_answers(commands, cwd))
                       and not (whole and not inside and (text_only(lines, bodies, cwd)
                                                          or parents_only(command, lines, bodies, cwd)))):
        hidden = next((h for h in HIDDEN if h in command), None)
        if hidden:
            return ANSWERS_MESSAGE.format(f"`{hidden}` hides what runs")
        if qualifier:
            return ANSWERS_MESSAGE.format("a zsh glob qualifier that runs code (`*(e:...:)`, `*(+name)`)")
        if expands:
            return ANSWERS_MESSAGE.format("a zsh `${(e)...}`, which runs the code in a value")
        for words, targets in commands:
            reason = read_reason(words, targets)
            if reason:
                return ANSWERS_MESSAGE.format(reason + reset_hint(parsed, lines, cwd, ceo))
        if hidden_code:
            return ANSWERS_MESSAGE.format("a heredoc a shell runs, whose code names a held folder")
    for n, line in enumerate(parsed):
        for words, _ in line:
            reason = token_reason(words)
            if reason:
                return TOKEN_MESSAGE.format(reason)
            given = desk_command(words)
            if given is not False and given not in commands_allowed:
                return DESK_MESSAGE.format(f"`board_desk.py {given}`")
            if any(desk_text.search(code) for code in code_strings(words) + shell_code(words)):
                return DESK_MESSAGE.format("a run of it in the code this command runs")
        # what a `$(` or backquote runs, not quoted text that holds one (an
        # echo'd line quoting a block message that names scripts/board_desk.py in single quotes), in an unquoted
        # heredoc's body too; and, as a substitution's end may lie past a quoted `)` or a case pattern's, a run anywhere
        # outside single quotes in a line, or in an unquoted body, with a `$(` or backquote that isn't `$(date ...)`
        # (DATE_RUN)
        open_bodies = [body for at, body, quoted in bodies if at == n and not quoted]
        if any(run_form.search(text) for text in substitutions(lines[n]) + [
                inner for body in open_bodies for inner in substitutions(body)]) or any(
                ("$(" in DATE_RUN.sub("", text) or "`" in text) and run_form.search(text)
                for text in [unquoted(lines[n])] + open_bodies):
            return DESK_MESSAGE.format("a run of it in a substitution")
        body = "\n".join(text for at, text, _ in bodies if at == n)
        rows = all(quoted for at, _, quoted in bodies if at == n)  # the row helper's quoted rows
        coded = any(runs_code(words) and not (rows and status_log_run(words, cwd)) for words, _ in line)
        if body and coded and reads_token(body):
            return TOKEN_MESSAGE.format("a read of it in a heredoc")
        if body and coded and desk_text.search(body):
            return DESK_MESSAGE.format("a run of it in a heredoc")
    return None
