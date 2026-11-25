"""Tests for scripts/hooks/cq_write.py: a subagent writes a ceo-questions.md only by Edit, an append (`>>`, `tee -a`)
or `python3 scripts/cq_archive.py`. Every form is checked on command_reason, and
the wiring end to end, as Claude Code runs the hooks: guard_marketing_tools.py for Bash, guard_kb_write.py for Write."""

import json
import os
import random
import re
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from collections import Counter
from pathlib import Path
from unittest import mock

HOOKS = Path(__file__).resolve().parents[1] / "hooks"
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HOOKS))
import cq_write  # noqa: E402

ROOT = "/repo"
# The regex cq_write.heredocs replaced: the oracle its reading is checked against.
HEREDOC = re.compile(r"<<-?[ \t]*(['\"]?)([A-Za-z_][\w.-]*)\1([^\n]*)\n((?:.*?\n)?)[ \t]*\2[ \t]*(?=\n|$)", re.S)
F = "workspaces/acme/content/ceo-questions.md"

REFUSED = {
    # sed and perl in place
    f"sed -i '' 's/a/b/' {F}": "sed",
    f"sed -i.bak -e 's/a/b/' {F}": "sed",
    f"sed -Ei 's/a/b/' {F}": "sed",
    f"sed --in-place 's/a/b/' {F}": "sed",
    f"sed -I '' 's/a/b/' {F}": "sed",
    f"cd workspaces/x/content && sed -i '' 's/a/b/' ceo-questions.md": "sed",
    f"perl -pi -e 's/a/b/' {F}": "perl",
    f"perl -i.bak -ne 'print' {F}": "perl",
    # interpreters other than cq_archive, the path in the command or in a heredoc body
    f"python3 -c \"open('{F}','w').write('x')\"": "python3",
    f"python -c \"print(open('{F}').read())\"": "python",
    f"python3 - <<'EOF'\np = '{F}'\nopen(p, 'w').write('x')\nEOF": "python3",
    f"F={F}; python3 - <<EOF\nopen('$F', 'w')\nEOF": "python3",
    f"node -e 'require(\"fs\").writeFileSync(\"{F}\", \"x\")'": "node",
    f"ruby -e 'File.write(ARGV[0], \"x\")' {F}": "ruby",
    f"bun x.ts {F}": "bun",
    f"nohup python3 x.py {F} &": "python3",
    f"timeout 170 python3 x.py {F}": "python3",
    f"python3 scripts/cq_archive.py {F} --order /9; python3 -c 'x' {F}": "python3",
    f"bash x.sh {F}": "bash",
    f"bash <<'EOF'\nsed -i '' 's/a/b/' {F}\nEOF": "bash",
    # truncating redirections
    f"echo hi > {F}": "`>`",
    f"echo hi >| {F}": "`>|`",
    f"cat a &> {F}": "`&>`",
    f"cat a b>{F}": "`>`",
    f"cat a 2> {F}": "`>`",
    f"cat > {F} <<'EOF'\nit's a line\nEOF": "`>`",
    f"python3 scripts/cq_archive.py {F} --order /9 > {F}": "`>`",
    f"exec 3> {F}": "`>`",
    f"exec 3<> {F}": "`<>`",
    f"(cd a && cat b)>{F}": "`)>`",
    f"echo x > $(echo {F})": "`>`",
    f"F={F}; echo x > $(echo $F)": "`>`",
    f"echo x >! {F}": "`>!`",
    f"echo x >!{F}": "`>!`",
    f"F={F}; awk '{{print}}' $F > $F.new && mv $F.new $F": "mv",
    # tee without -a
    f"printf x | tee {F}": "tee",
    f"printf x | tee -p {F} > /dev/null": "tee",
    f"sort {F} | sponge {F}": "sponge",
    f"printf x | tee -- -a {F}": "tee",
    f"bun /tmp/scripts-x/deploy.ts --ceo-questions {F} {F}": "bun",
    f"bun /tmp/xscripts/deploy.ts --x abc --ceo-questions {F} {F}": "bun",
    f"bun scripts/deploy.ts.bak --ceo-questions {F}": "bun",
    f"bun /tmp/scripts/deploy.ts --ceo-questions {F}": "bun",
    f"python3 scripts/second_opinion.py --kind code --brief x > {F}": "`>`",
    f"python3 /tmp/scripts/second_opinion.py --file {F}": "python3",
    f"uv run python x.py {F}": "uv",
    f"perl -ne 'print if /NEEDS/' {F}": "perl",
    # what a substitution runs, quoted or not
    f"echo \"$(sed -i '' s/a/b/ {F})\"": "sed",
    f"echo `sed -i '' s/a/b/ {F}`": "sed",
    f"echo \"`sed -i '' s/a/b/ {F}`\"": "sed",
    f"out=\"$(python3 -c \"open('{F}','w').write('x')\")\"": "python3",
    f"n=\"$(python3 - <<'EOF'\nopen('{F}', 'w').write('x')\nEOF\n)\"": "python3",
    f"echo \"$(echo \"$(sed -i '' s/a/b/ {F})\")\"": "sed",
    # copies onto it, moves, removes, truncates
    f"cp /tmp/x.md {F}": "cp",
    f"cp -f /tmp/x.md {F}": "cp",
    f"install -m 644 /tmp/x.md {F}": "install",
    f"rsync -a /tmp/x.md {F}": "rsync",
    f"ln -sf /tmp/x.md {F}": "ln",
    "cp /tmp/new/ceo-questions.md workspaces/x/content/": "cp",
    "cp /tmp/new/ceo-questions.md workspaces/x/content": "cp",
    "cp /tmp/new/ceo-questions.md .": "cp",
    "cp /tmp/new/ceo-questions.md $DEST": "cp",
    "cp -t workspaces/x/content /tmp/new/ceo-questions.md": "cp",
    f"cp --target-directory=/tmp /tmp/x.md && cp -t workspaces/x/content/ /tmp/new/ceo-questions.md": "cp",
    f"dd if=/tmp/x of={F}": "dd",
    f"mv /tmp/x.md {F}": "mv",
    f"mv {F} /tmp/x.md": "mv",
    # the copy-out, edit, move-back form
    "mv /tmp/s/ceo-questions.md workspaces/acme/content/": "mv",
    "mv /tmp/s/ceo-questions.md workspaces/acme/content": "mv",
    "mv /tmp/s/ceo-questions.md /repo/workspaces/acme/content/": "mv",
    "cd workspaces/acme/content && mv /tmp/s/ceo-questions.md .": "mv",
    "mv -t workspaces/acme/content /tmp/s/ceo-questions.md": "mv",
    f"rm {F}": "rm",
    f"rm -f $(ls {F})": "rm",
    f"truncate -s 0 {F}": "truncate",
    # awk in place or writing to it, editors
    f"awk -i inplace '{{print}}' {F}": "awk",
    f"gawk -iinplace '{{print}}' {F}": "awk",
    f"awk '{{print > \"{F}\"}}' /tmp/x": "awk",
    f"ed -s {F} <<< $'1d\\nw'": "ed",
    f"vim -c ':wq' {F}": "vim",
    # through a variable, a loop, a substitution, a nested shell
    f"F={F}; sed -i '' 's/a/b/' \"$F\"": "sed",
    f"export F={F} && sed -i '' 's/a/b/' ${{F}}": "sed",
    f"D=workspaces/x/content; F=$D/ceo-questions.md; G=$F; sed -i '' 's/a/b/' $G": "sed",
    f"for f in {F}; do sed -i '' 's/a/b/' \"$f\"; done": "sed",
    "D=/tmp; D=workspaces/x/content; sed -i '' 's/a/b/' \"$D/ceo-questions.md\"": "sed",
    "D=/tmp; D=/repo/workspaces/x/content; sed -i '' 's/a/b/' $D/ceo-questions.md": "sed",
    f"sed -i '' 's/a/b/' $(ls {F})": "sed",
    f"sed -i '' 's/a/b/' `ls {F}`": "sed",
    f"find workspaces -name ceo-questions.md -exec sed -i '' 's/a/b/' {{}} \\;": "sed",
    f"bash -c \"sed -i '' 's/a/b/' {F}\"": "sed",
    f"sh -c 'echo x > {F}'": "`>`",
    f"bash -lc 'F={F}; perl -pi -e s/a/b/ $F'": "perl",
    f"eval \"sed -i '' s/a/b/ {F}\"": "sed",
    f"env LC_ALL=C sed -i '' 's/a/b/' {F}": "sed",
    f"sudo -n sed -i '' 's/a/b/' {F}": "sed",
    # the named exceptions only in their own form
    f"bun scripts/deploy.ts --x abc {F}": "bun",
    f"bun scripts/deploy.ts --lock {F}": "bun",
    f"python3 workspaces/acme/content/watch.py /tmp/d {F}": "python3",
    # a heredoc's text for an editor (its `w`) and behind xargs (stdin becomes operands); process substitutions
    f"ed -s <<'EOF'\nr /tmp/x\nw {F}\nEOF": "ed",
    f"ed -s /tmp/x.md <<'EOF'\na\nx\n.\nw {F}\nEOF": "ed",
    f"xargs rm <<'EOF'\n{F}\nEOF": "rm",
    f"xargs -I@ sed -i '' s/a/b/ @ <<'EOF'\n{F}\nEOF": "sed",
    f"diff <(sed -i '' s/a/b/ {F}) /dev/null": "sed",
    f"cat <(rm {F})": "rm",
    f"python3 /tmp/scripts/cq_archive.py {F} --order /9": "python3",
    f"python3 -c 'x' scripts/cq_archive.py {F}": "python3",
    # a path whose top folder doesn't exist may be the live one
    "python3 -c \"open(ROOT + '/workspaces/x/content/ceo-questions.md', 'w')\"": "python3",
    "cd /tmp/s && sed -i '' 's/a/b/' ceo-questions.md": "sed",
    # can't be read
    f"sed -i 's/a/b {F}": "couldn't be read",
    # what the shell joins or runs later
    f"s\\\ned -i '' 's/a/b/' {F}": "sed",
    f"\"s\\\ned\" -i '' 's/a/b/' {F}": "sed",
    "sed -i '' s/a/b/ workspaces/x/content/ceo-que\\\nstions.md": "sed",
    f"echo a\\\n# x; sed -i '' s/a/b/ {F}": "sed",
    f"X=1s\\\ned -i x {F}": "ed",  # the shell runs no editor (`X=1sed`), but with a space it would
    f"sh -c 'sed -i x \\\n{F}'": "sed",
    f"trap \"sed -i '' s/a/b/ {F}\" EXIT": "sed",
    f"noglob sed -i '' s/a/b/ {F}": "sed",
    f"nocorrect sed -i '' s/a/b/ {F}": "sed",
    f"coproc sed -i '' s/a/b/ {F}": "sed",
    # heredocs the shell reads otherwise than heredocs() (heredoc_doubt)
    f"cat <<EOF\nEOF\nsed -i '' s/a/b/ {F}\nEOF": "an empty heredoc",
    f"echo '<<EOF'\nsed -i '' s/a/b/ {F}\nEOF": "in quotes",
    f"# <<EOF\nsed -i '' s/a/b/ {F}\nEOF": "in quotes",
    f"cat <<<EOF\nsed -i '' s/a/b/ {F}\nEOF": "in quotes",
    f"echo $((1<<EOF))\nsed -i '' s/a/b/ {F}\nEOF": "in quotes",
    f"cat <<EOF\nEO\\\nF\nsed -i '' s/a/b/ {F}\nEOF": "may end it on another line",
    f"cat <<EOF \\\n; sed -i '' s/a/b/ {F}\nx\nEOF": "first line goes on",
    f"cat <<E\\OF\nx\nEOF\nsed -i '' s/a/b/ {F}": "more than a name",
    f"cat <<'E OF'\nx\nE\nsed -i '' s/a/b/ {F}\nE OF": "more than a name",
    f"cat <<EOF\nx\nEOF \nsed -i '' s/a/b/ {F}\nEOF": "more than its end word",
    f"cat <<A <<B\nx\nA\nsed -i '' s/a/b/ {F}\nB": "two heredocs",
    f"cat <<EOF '\nsed -i '' s/a/b/ {F}\nEOF\n'": "a quote or a parenthesis open",
    f"python3 - <<EOF\nprint(1)\n# {F}": "no end line",
    # other contexts the shell reads otherwise, and a split `<<`
    f"echo \"${{x:-\"<<EOF \"}}\"\nsed -i '' s/a/b/ {F}\nEOF": "in quotes",
    f"echo ${{x:-a <<EOF }}\nsed -i '' s/a/b/ {F}\nEOF": "in quotes",
    f"echo ${{x:-{{a}} <<EOF }}\nsed -i '' s/a/b/ {F}\nEOF": "in quotes",  # `${x:-{a}}` is `{a}`: braces count
    f"echo a\\\n#'\ncat <<EOF\n'\nsed -i '' s/a/b/ {F}\nEOF": "in quotes",  # `a#'`: no comment, a quote
    f"echo $[ 1 <<EOF ]\nsed -i '' s/a/b/ {F}\nEOF": "in quotes",
    f"cat <\\\n<A\ncat <<B\nA\nsed -i '' s/a/b/ {F}\nB": "split by a backslash-newline",  # bash's heredoc A
    f"echo \"${{x:-'}}'}}\"\ncat <<EOF\nx\nEOF\nsed -i '' s/a/b/ {F}": "a quote to bash and not to zsh",
    # what runs later, or in a new shell
    f"alias x=\"sed -i '' s/a/b/ {F}\"\nx": "sed",
    f"alias -g X='{F}' x=\"sed -i '' s/a/b/ {F}\"": "sed",
    f"D=/tmp sh -c \"sed -i '' s/a/b/ $D/ceo-questions.md\"": "sed",
    "D=/tmp true; sed -i '' s/a/b/ $D/ceo-questions.md": "sed",
    "false && D=/tmp; sed -i '' s/a/b/ $D/ceo-questions.md": "sed",
    "while false; do D=/tmp; done; sed -i '' s/a/b/ $D/ceo-questions.md": "sed",
    "D=/tmp | true; sed -i '' s/a/b/ $D/ceo-questions.md": "sed",
    "local D=/tmp; sed -i '' s/a/b/ $D/ceo-questions.md": "sed",
    "D=/tmp </nonexistent/x; sed -i '' s/a/b/ $D/ceo-questions.md": "sed",  # zsh skips it
}
# Refused from any cwd (CommandReason.test_the_hidden_program_and_find_forms_from_any_cwd).
REFUSED_PROGRAMS = {
    # an escaped backslash before a newline: the newline ends the line
    f"echo \\\\\nrm {F}": "rm",
    f"\\\\\ntee {F} </dev/null": "tee",
    f"echo a\\\\\nmv /dev/null {F}": "mv",
    f"echo \\\\\\\\\nrm {F}": "rm",
    # a program a `$`, `$(` or backtick names, or an alias or a function defined in the command
    f"X=rm; $X {F}": "a program named by a variable",
    f"${{x:-rm}} {F}": "a program named by a variable",
    f"$(echo rm) {F}": "substitution ($(...))",
    f"`true`python3 -c 'open(\"{F}\",\"w\")'": "a program named by a variable",
    f"$(true)python3 -c 'open(\"{F}\",\"w\")'": "python3",
    f"$'rm' {F}": "a program named by a variable",
    f"\"$X\" {F}": "a program named by a variable",
    f"alias x='sed -i'\nx s/a/b/ {F}": "defines an alias or a function",
    f"alias -s md='sed -i s/a/b/'\n{F}": "defines an alias or a function",
    f"eval \"alias x='sed -i'\"\nx s/a/b/ {F}": "defines an alias or a function",
    f"f() {{ sed -i '' s/a/b/ \"$1\"; }}; f {F}": "defines an alias or a function",
    f"f () {{ sed -i '' s/a/b/ \"$1\"; }}; f {F}": "defines an alias or a function",
    f"function f {{ sed -i '' s/a/b/ \"$1\"; }}; f {F}": "defines an alias or a function",
    f"trap 'f() {{ :; }}' EXIT; f {F}": "defines an alias or a function",
    f"${{x:-\\\ntruncate -s0 {F}\n}}": "truncate",  # bash runs the truncate the default's word holds
    f"${{x:- truncate -s0 {F}}}": "a program named by a variable",
    f"\"${{x:-truncate}}\" -s0 {F}": "a program named by a variable",
    f"${{x:-'\n'truncate -s0 {F}}}": "a program named by a variable",
    f"${{x:-\ntruncate -s0 {F}\n}}": "truncate",
    f"${{x:-a\ntruncate -s0 {F}}}": "truncate",
    f"echo ${{x:-\ntruncate -s0 {F}\n}}": "truncate",
    f"sed -i '' $(true) s/a/b/ {F}": "sed",
    f"sed -i '' `true` s/a/b/ {F}": "sed",
    # a here-string is its program's stdin, and a heredoc may come before the program
    f"python3 <<< \"open('{F}','w')\"": "python3",
    f"bash <<< 'rm {F}'": "bash",
    f"<<'EOF' python3\nopen('{F}','w')\nEOF": "python3",
    # nor does it lift the check of a copy put where the live one is
    f"cp /tmp/scratch/ceo-questions.md workspaces/x/content/ <<< \"{F}\"": "cp puts",
    f"mv /tmp/scratch/ceo-questions.md workspaces/x/content/ <<< {F}": "mv puts",
    f"ln -f /tmp/scratch/ceo-questions.md workspaces/x/content/ <<< {F}": "ln puts",
    "cp /tmp/scratch/ceo-questions.md . <<< ceo-questions.md": "cp puts",
    f"cp /tmp/scratch/ceo-questions.md workspaces/x/content/ <<'EOF'\n{F}\nEOF": "cp puts",
    f"<<'EOF' cp /tmp/scratch/ceo-questions.md workspaces/x/content/\n{F}\nEOF": "cp puts",
    # `D+=` keeps no value, and HOME the command may set makes a `~` path live
    "D=/tmp; D+=/../repo/workspaces/x/content; sed -i '' s/a/b/ $D/ceo-questions.md": "sed",
    "HOME=/repo/workspaces/x/content; sed -i '' s/a/b/ ~/ceo-questions.md": "sed",
    "export HOME=/repo/workspaces/x/content; sed -i '' s/a/b/ ~/ceo-questions.md": "sed",
    "eval \"HO\"\"ME=/repo/workspaces/x/content\"; sed -i '' s/a/b/ ~/ceo-questions.md": "sed",
    "HOME=/repo/workspaces/x/content sh -c \"sed -i '' s/a/b/ ~/ceo-questions.md\"": "sed",
    "read HOME < /tmp/h; sed -i '' s/a/b/ ~/ceo-questions.md": "sed",
    ": ${HOME:=/x}; sed -i '' s/a/b/ ~/ceo-questions.md": "sed",
}
REFUSED.update(REFUSED_PROGRAMS)
# Copies find makes, and a target a `$`, backtick, glob or brace may make any folder; also from any cwd.
REFUSED_FIND = {
    # a copy that find makes: its action read up to its `;` or `{} +`, and `{}` a ceo-questions.md in its folders
    "find /tmp/scratch -name ceo-questions.md -exec cp {} workspaces/x/content/ ';'": "cp puts",
    "find /tmp/scratch -name ceo-questions.md -exec cp {} workspaces/x/content/ \\;": "cp puts",
    "find /tmp/scratch -name ceo-questions.md -exec mv {} workspaces/x/content/ ';'": "mv puts",
    "find /tmp/scratch -name ceo-questions.md -execdir cp {} /repo/workspaces/x/content/ ';' -print": "cp puts",
    "find /tmp/scratch -name ceo-questions.md -exec cp -t workspaces/x/content/ {} +": "cp puts",
    "find /tmp/scratch -name ceo-questions.md -exec echo ';' -exec cp {} . ';'": "cp puts",
    "find /tmp/scratch -name ceo-questions.md -exec cp _ {} workspaces/x/content/ ';'": "cp puts",
    f"find /tmp/scratch -type f -exec cp {{}} {F} ';'": "cp writes over",
    "find workspaces -name ceo-questions.md -exec cp /tmp/new {} ';'": "cp writes over",
    "find workspaces -name ceo-questions.md -exec rm {} ';'": "rm moves, removes",
    "find /repo/workspaces -name ceo-questions.md -delete": "find -delete removes",
    "find -L workspaces -name ceo-questions.md -delete": "find -delete removes",
    # a copier's target with a `$(...)`, a backtick or a `${...}` glued on: it may be any folder, as a variable may
    "cp /tmp/scratch/ceo-questions.md workspaces/x/content/$(true)": "write the target out",
    "cp /tmp/scratch/ceo-questions.md workspaces/x/content/`true`": "write the target out",
    "cp /tmp/scratch/ceo-questions.md \"/repo/workspaces/x/content/$(true)\"": "write the target out",
    "mv /tmp/scratch/ceo-questions.md workspaces/x/content/$(true)": "write the target out",
    "cp /tmp/scratch/ceo-questions.md workspaces/x/content/${x:-}": "write the target out",
    "cp /tmp/scratch/ceo-questions.md $(echo workspaces/x/content/)": "write the target out",
    f"cp {F} /tmp/bak-$(date +%s).md": "write the target out",  # it looks the same
    # a glob or brace in the target, the same kind
    "cp /tmp/scratch/ceo-questions.md workspaces/x/conten[t]/": "write the target out",
    "cp /tmp/scratch/ceo-questions.md workspaces/x/conte?t/": "write the target out",
    "mv /tmp/scratch/ceo-questions.md workspaces/x/{content,content}/": "write the target out",
    "cp /tmp/scratch/ceo-questions.md /repo/workspaces/*/content/": "write the target out",
    # an escaped `\(` or `\)` is a word, not a subshell that splits the command
    f"find /tmp/s \\( -name x \\) -exec cp {{}} {F} ';'": "cp writes over",
    f"find /tmp/s \\( -name x \\) -exec tee {F} ';'": "tee without -a",
    f"find /tmp/s \\( -name x \\) -exec mv {{}} {F} ';'": "mv",
    "find workspaces \\( -name ceo-questions.md \\) -exec sed -i '' s/a/b/ {} +": "sed edits",
    "find /tmp/s \\( -name ceo-questions.md \\) -exec cp {} workspaces/x/content/ ';'": "cp puts",
    f"rm \\( {F}": "rm moves",
    f"sed -i '' s/a/b/ \\( {F}": "sed edits",
    # so is an escaped `\;`, `\|`, `\&` or `\<`, not an operator
    "find workspaces -type f -exec rm {} \\; -name ceo-questions.md": "rm moves",
    f"find /tmp/s -name x -exec cat {{}} \\; -exec cp {{}} {F} \\;": "cp writes over",
    f"rm \\; {F}": "rm moves",
    f"rm \\| {F}": "rm moves",
    f"rm \\& {F}": "rm moves",
    f"rm \\< {F}": "rm moves",
    f"sed -i '' s/a/b/ \\| {F}": "sed edits",
    "find _ /tmp/scratch -name ceo-questions.md -delete": "find -delete removes",  # `_`: a folder
    # an escaped `\>` is a word: `echo x \>> <it>` is `echo x '>' > <it>`, a rewrite, not an append
    f"echo x \\>> {F}": "`>` rewrites",
    f"rm \\>\\> {F}": "rm moves",
}
REFUSED.update(REFUSED_FIND)

ALLOWED = [
    f"cat {F}",
    f"grep -n 'NEEDS-CEO-NOW' {F} | tail -5",
    f"grep -n '>' {F}",
    f"grep -c \">\" {F} > /tmp/count.txt",
    f"sed -n '1,40p' {F}",
    "sed -n '5,$p' workspaces/acme/content/orders/D-20260101-x/2/ceo-questions.md",
    "sed -n '5,$p' /repo/workspaces/x/content/orders/D-20260101-x/2/ceo-questions.md",
    f"sed -n -e '/x/p' {F}",
    f"sed -E -n 's/i/x/p' {F}",
    f"sed -ne 's/i/x/p' {F}",
    f"awk '/NEEDS/' {F}",
    f"head -50 {F}; wc -c {F}",
    f"ls -la {F}; stat {F}",
    f"tail -n 20 {F} > /tmp/tail.txt 2>&1",
    f"echo 'REPORT /1   status: DONE' >> {F}",
    # a refused release's line and the CTO's read before clearing a lock (cto.md, Working rules)
    f"echo 'REFUSED {ROOT}/workspaces/x/.suite-slots/slot-2 09:45Z rm removes a folder that holds a ceo-questions.md; "
    f"it’s final' >> {ROOT}/{F}",
    f"grep -n -i -E 'refus|blocked|denied' {ROOT}/{F} {ROOT}/workspaces/acme/content/"
    f"ceo-questions-archive.md {ROOT}/workspaces/x/content/orders-closed/D-20260101-x/12/ceo-questions.md "
    "| grep -F slot-2",
    f"echo x >> {F}",
    f"date -u >> {F}",
    f"cat a &>> {F}",
    f"cat >> {F} <<'EOF'\nREPORT x: it's done > ok; rm {F}\nEOF",
    f"cat <<'EOF' >> {F}\nline\nEOF",
    f"printf '%s\\n' x | tee -a {F}",
    f"printf x | tee --append {F} > /dev/null",
    f"printf x | tee -ai {F}",
    f"cp {F} /tmp/cq-backup.md",
    f"S=/private/tmp/s; cp {F} $S/cq.md",
    "cp /tmp/ceo-questions.md.bak /tmp/y",
    f"F={F}; cat $F > $F.bak; cp $F ${{F}}.1",
    f"python3 scripts/cq_archive.py {F} --order /12 --dry-run",
    f"cd /repo && python3 scripts/cq_archive.py {F} --order /9",
    f"python3 -I /repo/scripts/cq_archive.py /repo/{F} --order /9",
    f"python3 /repo/scripts/cq_archive.py /repo/{F} --order /9 --add 'REPORT /9.T1   status: DONE   branch a1..b1'",
    f"python3 scripts/cq_archive.py {F} --order /9 && grep -c HANDLED {F}",
    f"cat {F} | python3 -c 'import sys; print(sys.stdin.read().count(\"x\"))'",
    f"python3 x.py < {F}",
    "python3 -c 'print(1)' > /tmp/x",
    # the second opinion only reads
    f"python3 scripts/second_opinion.py --kind code --brief 'a hook on ceo-questions.md' --file {F}",
    f"python3 -I /repo/scripts/second_opinion.py --kind code --brief x --file /repo/{F} > /tmp/so.log 2>&1; echo $? > /tmp/so.rc",
    # find's actions on scratch copies, or reading the live one
    "find /tmp/scratch -name ceo-questions.md -exec rm {} ';'",
    "find /tmp/scratch -name ceo-questions.md -delete",
    "find /tmp/scratch -name ceo-questions.md -exec cp {} /tmp/backup/ ';'",
    "find workspaces -name ceo-questions.md -exec grep -c NEEDS {} ';'",
    "find workspaces -name ceo-questions.md -print -exec wc -l {} +",
    "find workspaces -name ceo-questions.md -exec cp {} /tmp/backup/ ';'",
    "find workspaces \\( -name ceo-questions.md -o -name x \\) -exec grep -c NEEDS {} +",
    "find /tmp/scratch \\( -name ceo-questions.md \\) -exec cp /tmp/new {} ';'",
    "find /tmp/scratch '(' -name ceo-questions.md ')' -delete",
    "find workspaces -name ceo-questions.md -exec grep -c NEEDS {} \\; -exec wc -l {} \\;",
    f"grep -c NEEDS {F} \\| wc; cat {F} \\; echo",
    # reads in a substitution; text naming it in a quoted string or heredoc, for programs that write only operands
    f"echo \"$(cat {F} | wc -l)\"",
    f"x=$(grep -c NEEDS {F})",
    f"tee /tmp/notes.md <<'EOF'\nsee {F}\nEOF",
    f"diff <(sort {F}) /tmp/x",
    f"cat >> {F} <<'EOF'\nREPORT /1: ran `python3 x.py {F}` once\nEOF",
    f"echo 'REPORT /1: ran `sed -i x {F}` once' >> {F}",
    f"echo x >>! {F}",
    f"grep -c x {F} > /tmp/n-`date +%s`.txt",
    f"sed -i '' 's/a/b/' other.md; grep x {F}",
    "sed -i '' s/a/b/ workspaces/x/content/ceo-questions-archive.md",
    "sed -i '' s/a/b/ workspaces/x/content/old-ceo-questions.md.txt",
    "echo hi",
    "rm -rf /tmp/scratch",
    f"diff {F} /tmp/cq-backup.md",
    f"# sed -i '' s/a/b/ {F}\necho done",
    # scratch copies at an absolute path outside the repo's workspaces/ (a test's) are free
    "printf 'x' > /private/tmp/s/kb3/workspaces/demo/content/ceo-questions.md",
    "S=/tmp/s; sed -i '' 's/a/b/' $S/ceo-questions.md",
    "S=/tmp/s; F=$S/ceo-questions.md; python3 - \"$F\" <<'EOF'\nimport sys\nopen(sys.argv[1], 'w')\nEOF",
    "python3 -c \"open('/tmp/x/ceo-questions.md', 'w')\"",
    "rm /tmp/x/ceo-questions.md; cp /tmp/new/ceo-questions.md /tmp/y/",
    "mv /tmp/a/ceo-questions.md /tmp/b/",
    # heredocs the shell reads as heredocs() does
    f"cat >> {F} <<'EOF'\na line that ends in a backslash \\\nEOF",
    f"cat <<-EOF >> {F}\n\tline\n\tEOF",
    f"x=$(cat <<'EOF'\nhi\nEOF\n); echo \"$x\" >> {F}",
    f"echo 'a << b' >> {F}",
    f"cat <<'EOF' >> {F} # a note\nx\nEOF",
    f"cat >> {F} <<EOF\nNEEDS-CEO-NOW: $(date -u) it's \"quoted\" (x)\nEOF",
    f"cat >> {F} <<'EOF'\nREPORT /1\nEOF\ngrep -c REPORT {F}",
    f"echo \"${{x:-a}} $[1<<2]\" >> {F}",
    f"echo \"${{x:-'a'}}\" >> {F}",
    f"cat >> {F} <<EOF\n${{x:-\"a\"}} {{b}}\nEOF",
    # a value from an assignment that surely set it (sure_assignments)
    "D=/tmp; sed -i '' s/a/b/ $D/ceo-questions.md",
    "export D=/tmp && sed -i '' s/a/b/ $D/ceo-questions.md",
    # what passes: a substitution that isn't the program, an array, a here-string
    # for a reader or a writer of operands only, `$HOME`, and a `~` path when nothing may set HOME
    f"cat {F} > /tmp/x-$(date +%s).md",
    f"echo \"$(date -u) a\" >> {F}",
    f"x=(); echo hi >> {F}",
    f"echo \"f() is $HOME\" >> {F}",
    f"echo $() >> {F}",
    f"cat {F} | (wc -l)",
    f"grep -c x <<< \"{F}\"",
    f"tee /tmp/n.md <<< \"see {F}\"",
    f"echo \\\\\necho {F}",
    "sed -i '' s/a/b/ ~/tmp/ceo-questions.md",
    "echo \"$HOME\" > /tmp/h; sed -i '' s/a/b/ ~/tmp/ceo-questions.md",
]


# Each order's own file, content/orders/<directive id>/<n>/. Every refused form above runs on it too (to_order), and
# these: a copy into a folder of the layout other than content/, and a remover of a folder that holds a live file; from
# ROOT unless a cwd is given.
ORDER_FOLDER = "content/orders/D-20260101-x/2"
FOLDERS_REFUSED = {
    ("cp /tmp/s/ceo-questions.md content/orders/D-20260101-x/2", f"{ROOT}/workspaces/x"): "cp puts",
    ("cp /tmp/s/ceo-questions.md workspaces/x/content/orders/D-20260101-x/2/", ROOT): "cp puts",
    ("cd workspaces/x/content/orders/D-20260101-x && cp /tmp/s/ceo-questions.md 2", ROOT): "cp puts",
    ("cd $D && cp /tmp/s/ceo-questions.md 2", ROOT): "a cd this can't follow",
    ("mv /tmp/s/ceo-questions.md workspaces/x/content/orders-closed/D-20260101-x/3", ROOT): "mv puts",
    ("rm -r content/orders/D-20260101-x", f"{ROOT}/workspaces/x"): "rm removes or moves a folder",
    ("rm -rf workspaces/x/content/orders", ROOT): "rm removes or moves a folder",
    ("rm -rf workspaces/x/content/orders/*", ROOT): "rm removes or moves a folder",
    ("rm -rf Workspaces/X/Content", ROOT): "rm removes or moves a folder",
    ("rm -rf workspaces", ROOT): "rm removes or moves a folder",
    ("sudo rm -rf workspaces/x", ROOT): "rm removes or moves a folder",
    ("rm -rf $D/content/orders", ROOT): "rm removes or moves a folder",
    ("cd $D && rm -rf orders", ROOT): "rm removes or moves a folder",
    ("trash workspaces/x/content/orders/D-20260101-x/2", ROOT): "trash removes or moves a folder",
    ("mv workspaces/x/content/orders/D-20260101-x/2 /tmp/", ROOT): "mv removes or moves a folder",
    ("rsync -a --delete /tmp/empty/ workspaces/x/content/orders/", ROOT): "rsync removes or moves a folder",
    ("find workspaces/x/content/orders -delete", ROOT): "find removes or moves a folder",
    ("find workspaces/x/content -type d -exec rm -rf {} +", ROOT): "find removes or moves a folder",
    ("ls workspaces/x/content/orders | xargs rm -rf", ROOT): "rm behind xargs",
    ("bash -c 'rm -rf workspaces/x/content/orders/D-20260101-x'", ROOT): "rm removes or moves a folder",
    ("eval 'rm -rf workspaces/x/content'", ROOT): "rm removes or moves a folder",
    ("trap 'rm -rf workspaces/x/content' EXIT", ROOT): "rm removes or moves a folder",
    ("echo $(rm -rf workspaces/x/content/orders)", ROOT): "rm removes or moves a folder",
    (f"cat {F}; rm -rf workspaces/x/content/orders", ROOT): "rm removes or moves a folder",
    ("rsync -a --remove-source-files workspaces/x/content/orders/ /tmp/b/", ROOT): "rsync removes or moves a folder",
    # a substitution's folder reason is told after the outer one's older one
    (f"echo $(rm -rf workspaces/x/content/orders) > {F}", ROOT): "`>` rewrites a ceo-questions.md whole",
    # so is a shell's `-c`, eval's and a trap's, in a command that names the file
    (f"bash -c 'rm -rf workspaces/x/content/orders; cat {F}'; sed -i '' s/a/b/ {F}", ROOT): "sed edits",
    (f"eval 'rm -rf workspaces/x/content/orders; cat {F}'; sed -i '' s/a/b/ {F}", ROOT): "sed edits",
    (f"trap 'rm -rf workspaces/x/content/orders; cat {F}' EXIT; sed -i '' s/a/b/ {F}", ROOT): "sed edits",
    (f"sh -c 'rm -rf workspaces/x/content/orders; cat {F}'; cat {F}", ROOT): "rm removes or moves a folder",
    # and rsync's old name for --remove-source-files
    ("rsync -a --remove-sent-files workspaces/x/content/orders/ /tmp/b/", ROOT): "rsync removes or moves a folder",
    # an rm that isn't recursive passes a literal path only; these stay held
    ("rm -R workspaces/x/content/orders", ROOT): "rm removes or moves a folder",
    ("rm -fR workspaces/x/content", ROOT): "rm removes or moves a folder",
    ("rm --recursive workspaces/x/content", ROOT): "rm removes or moves a folder",
    ("rm --rec -f workspaces/x/content", ROOT): "rm removes or moves a folder",  # GNU's rm takes a prefix
    ("rm workspaces/x/content -r", ROOT): "rm removes or moves a folder",  # and an option after the folder
    ("srm -r workspaces/x/content/orders", ROOT): "srm removes or moves a folder",
    # an option word the shell expands may become -r
    ("rm -{r,} workspaces/x/content", ROOT): "rm removes or moves a folder",
    ("rm $'-r' workspaces/x/content", ROOT): "rm removes or moves a folder",
    ("X=r; rm -$X workspaces/x/content", ROOT): "rm removes or moves a folder",
    ("rm -`echo r` workspaces/x/content", ROOT): "rm removes or moves a folder",
    ("cd $D/content; rm -r slot-2", ROOT): "rm removes or moves a folder",
    ("rm -f $D/content/owner", ROOT): "rm removes or moves a folder",
    ("rm -f workspaces/x/content/orders/*/owner", ROOT): "rm removes or moves a folder",
    ("rm -d workspaces/x/content/{a,b}", ROOT): "rm removes or moves a folder",
    ("ls workspaces/x/content | xargs rm", ROOT): "rm behind xargs",
    # zsh's glob group glued to a word, which shlex ends at the `(`: the word is read as the glob it
    # starts
    ("rm workspaces/x/content/(c|x)eo-questions.md", ROOT): "rm removes or moves a folder",
    ("rm workspaces/x/content/ceo-questions.(md|)", ROOT): "rm removes or moves a folder",
    # a word the shell expands after `--`, which recursive() doesn't read
    ("ls workspaces/x/content; rm -f -- \"$F\"", ROOT): "rm removes or moves a folder",
    ("rm -f -- workspaces/x/content/*", ROOT): "rm removes or moves a folder",
}
FOLDERS_ALLOWED = [
    ("rm -rf /tmp/scratch/orders", ROOT),
    ("rm -rf workspaces/x/worktrees/y", ROOT),
    ("rm -rf workspaces/system/reviews/x", ROOT),
    ("rm -rf build; cat workspaces/x/content/notes.md", ROOT),
    ("rm -rf content/orders", "/tmp"),  # /tmp's own
    ("mv /tmp/a workspaces/x/content/orders/", ROOT),  # into it: what it holds stays
    ("find /tmp/x -delete; ls workspaces/x/content", ROOT),
    ("git commit -m 'rm the content orders'", ROOT),
    ("echo rm content", ROOT),
    (f"cp {F} {F}.1", ROOT),  # another file's name, as before
    ("cp /tmp/s/ceo-questions.md content/orders/D-20260101-x/2", "/tmp"),
    # a slot's release (a `;` after the cd, or a cut before it, leaves the folder unknown): an rm that isn't recursive
    # takes a file, and rmdir only an empty folder
    (f"cd {ROOT}/workspaces/x && cat .suite-slots/slot-2/owner | cut -c1-120; rm .suite-slots/slot-2/owner; "
     "rmdir .suite-slots/slot-2; ls .suite-slots/ 2>&1 | head; ls .test-locks/acme-pg-ws1t4-sr 2>&1 | head -2",
     ROOT),
    (f"G=/tmp/gate; tail -5 $G/gate-run.log | cut -c1-150; cd {ROOT}/workspaces/x/.suite-slots && cat slot-2/owner && "
     "rm slot-2/owner && rmdir slot-2; ls; date -u", ROOT),
    ("cd $D; rm -f slot-2/owner; rmdir slot-2", ROOT),
    ("rm -- -r workspaces/x/content", ROOT),  # after `--` it is a file's name
    ("rm -df workspaces/x/content/orders/D-20260101-x/2", ROOT),  # -d: only an empty folder
    ("rm /tmp/x/(a|b).log; ls workspaces/x/content", ROOT),  # a glob group far from a live file
    ("find workspaces/x/content \\( -name a \\) -print; rm slot-2/owner", ROOT),  # an escaped `(` is find's
]


def to_order(command):
    """The command with each `content` folder an order's own below it."""
    return re.sub(r"(?<![\w.\[-])content(?![\w.\]-])", ORDER_FOLDER, command)


class CommandReason(unittest.TestCase):
    def test_every_refused_form_on_an_order_s_own_file(self):
        """Each refused form with its `content` folder an order's own."""
        mapped = {to_order(command): word for command, word in REFUSED.items() if to_order(command) != command}
        self.assertGreater(len(mapped), 150)
        self.assertIn(to_order(F), "".join(mapped))
        for command, word in mapped.items():
            with self.subTest(command=command):
                self.assertIn(word, cq_write.command_reason(command, ROOT, ROOT) or "")
        for cwd in (ROOT, "/", f"{ROOT}/workspaces/acme/content", f"{ROOT}/scripts"):
            for command, word in {**REFUSED_PROGRAMS, **REFUSED_FIND}.items():
                with self.subTest(command=to_order(command), cwd=cwd):
                    self.assertIn(word, cq_write.command_reason(to_order(command), cwd, ROOT) or "")

    def test_a_copy_into_and_a_remover_of_a_layout_folder(self):
        for (command, cwd), word in FOLDERS_REFUSED.items():
            with self.subTest(command=command, cwd=cwd):
                self.assertIn(word, cq_write.command_reason(command, cwd, ROOT) or "")
                other = re.sub(r"(?i)workspaces|content|orders", "x", command)  # without the layout, as before
                if other.replace("ceo-questions", "") == other:
                    self.assertIsNone(cq_write.command_reason(other, "/tmp", ROOT))
        for command, cwd in FOLDERS_ALLOWED:
            with self.subTest(command=command, cwd=cwd):
                self.assertIsNone(cq_write.command_reason(command, cwd, ROOT))

    def test_a_remover_is_refused_only_where_a_live_file_is(self):
        """With a real workspaces/: an order's folder holding its file is held; an empty one, another product's folder
        with none, and a glob none of whose matches holds one are free, as is a copy to another file's name."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            content = root / "workspaces" / "x" / "content"
            order = content / "orders" / "D-20260101-x" / "2"
            order.mkdir(parents=True)
            (order / "ceo-questions.md").write_text("# ORDER D-20260101-x/2 (cto, 2026-01-18)\n", encoding="utf-8")
            (content / "orders" / "D-20260101-x" / "3").mkdir()
            (root / "workspaces" / "y" / "notes").mkdir(parents=True)
            (content / "a.log").write_text("x\n", encoding="utf-8")
            other = root / "workspaces" / "z" / "content"  # a product file only: a glob's match is the live file
            other.mkdir(parents=True)
            (other / "ceo-questions.md").write_text("# ceo-questions\n", encoding="utf-8")
            for command in (f"rm -f {order}/*", f"rm -f {other}/*", f"rsync -a --remove-source-files {other}/ /tmp/b/",
                            f"rsync -a --remove-sent-files {other}/ /tmp/b/"):  # its old name
                with self.subTest(command=command):
                    self.assertIn("removes or moves a folder", cq_write.command_reason(command, str(root), str(root)))
            for command in (f"rm -rf {content}/orders/D-20260101-x", f"rm -rf {content}/orders/*", f"rm -rf {root}/workspaces",
                            f"cd {content} && rm -r orders", f"mv {order} /tmp/", f"find {content} -delete",
                            f"cp /tmp/s/ceo-questions.md {order}", f"cp /tmp/s/ceo-questions.md {order.parent}/3"):
                with self.subTest(command=command):
                    self.assertIsNotNone(cq_write.command_reason(command, str(root), str(root)))
            for command in (f"rm -rf {content}/orders/D-20260101-x/3", f"rm -rf {root}/workspaces/y",
                            f"rm -f {content}/*.log", f"rm -rf {root}/workspaces/x/worktrees",
                            f"cp /tmp/s/ceo-questions.md {content}/notes.md"):
                with self.subTest(command=command):
                    self.assertIsNone(cq_write.command_reason(command, str(root), str(root)))

    def test_an_inner_text_s_folder_reason_waits_only_where_a_timeout_refuses(self):
        """A shell's `-c`, eval's and a trap's folder reason goes to the outer
        command's later list only when the outermost command names the file (scope.defer), where a read still going
        at the timer is refused; else it is told at once, so no timeout can let it pass. Both
        ways the command is refused, through the hook's entry too."""
        text = "rm -rf workspaces/x/content/orders"
        for name, args in (("bash", ["-c", text]), ("eval", [text]), ("trap", [text, "EXIT"])):
            for defer, told, kept in ((False, "rm removes or moves a folder", []),
                                      (True, None, ["rm removes or moves a folder that holds a ceo-questions.md"])):
                with self.subTest(name=name, defer=defer):
                    scope, later = cq_write.Scope(ROOT, ROOT), []
                    scope.defer = defer
                    reason = cq_write.program_reason(name, list(args), scope, 0, later)
                    self.assertEqual(reason if reason is None else reason[:len(told)], told)
                    self.assertEqual(later, kept)
        event = {"tool_name": "Bash", "agent_id": "a1"}
        for (command, cwd), word in FOLDERS_REFUSED.items():
            if "sed edits" in word:
                with self.subTest(command=command):
                    self.assertIn(word, cq_write.cq_reason({**event, "cwd": cwd, "tool_input": {"command": command}},
                                                           ROOT))

    def test_each_refused_form(self):
        for command, word in REFUSED.items():
            with self.subTest(command=command):
                reason = cq_write.command_reason(command, ROOT, ROOT)
                self.assertIsNotNone(reason)
                self.assertIn(word, reason)

    def test_each_allowed_form(self):
        for command in ALLOWED:
            with self.subTest(command=command):
                self.assertIsNone(cq_write.command_reason(command, ROOT, ROOT))

    def test_the_hidden_program_and_find_forms_from_any_cwd(self):
        for cwd in (ROOT, "/", "/tmp", f"{ROOT}/workspaces/acme/content", f"{ROOT}/scripts"):
            for command, word in {**REFUSED_PROGRAMS, **REFUSED_FIND}.items():
                with self.subTest(command=command, cwd=cwd):
                    self.assertIn(word, cq_write.command_reason(command, cwd, ROOT) or "")

    def test_a_find_from_a_folder_above_the_live_ones_reaches_them(self):
        """find searches the folders below its start folders. ROOT doesn't
        exist, so every path under it counts as live; this needs a real root. A quoted or escaped `;` or a bare `_`
        before a start folder ends nothing."""
        name = "ceo-questions.md"
        with tempfile.TemporaryDirectory() as tmp:
            root = os.path.join(os.path.realpath(tmp), "repo")
            os.makedirs(os.path.join(root, "workspaces", "x", "content"))
            Path(root, "workspaces", "x", "content", name).write_text("")
            os.makedirs(os.path.join(tmp, "scratch"))
            for start in (root, tmp, f"{tmp}/", f"{root}/workspaces/..", "/", f"{tmp}/*", f"{tmp}/{{repo,x}}",
                          f"{tmp}/scratch _ {root}", f"{tmp}/scratch ';' {root}", f"{tmp}/scratch \\; {root}"):
                for action, word in (("-exec cp /tmp/new {} ';'", "cp writes over"), ("-exec rm {} ';'", "rm moves"),
                                     ("-delete", "find -delete removes"),
                                     ("-exec truncate -s0 {} +", "truncate moves")):
                    with self.subTest(start=start, action=action):
                        self.assertIn(word, cq_write.command_reason(f"find {start} -name {name} {action}", "/", root)
                                      or "")
                for action in ("-exec grep -c NEEDS {} +", "-exec cp {} /tmp/backup/ ';'", "-print"):
                    with self.subTest(start=start, action=action):
                        self.assertIsNone(cq_write.command_reason(f"find {start} -name {name} {action}", "/", root))
            with mock.patch.dict(os.environ, {"HOME": tmp}):
                self.assertIn("find -delete removes",
                              cq_write.command_reason(f"find ~ -name {name} -delete", "/", root))
            self.assertIsNone(cq_write.command_reason(f"find {tmp}/scratch -name {name} -delete", "/", root))

    def test_the_live_files_are_the_main_checkouts_when_root_is_an_agents_worktree(self):
        self.assertEqual(cq_write.live_folders("/x/co/.claude/worktrees/agent-1"),
                         ["/x/co/.claude/worktrees/agent-1/workspaces", "/x/co/workspaces"])

    def test_a_relative_cq_archive_from_another_folder_is_the_repos(self):
        # A Senior's cwd is its product worktree; `scripts/` there isn't this repo's, so the root is tried too.
        self.assertIsNone(cq_write.command_reason(f"python3 scripts/cq_archive.py {F} --order /9", "/w/tree", ROOT))

    def test_a_cq_archive_of_the_cwds_own_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "scripts").mkdir()
            (Path(tmp) / "scripts" / "cq_archive.py").write_text("", encoding="utf-8")
            reason = cq_write.command_reason(f"python3 scripts/cq_archive.py {F} --order /9", tmp, ROOT)
        self.assertIn("python3", reason)

    def test_the_main_checkouts_cq_archive_by_absolute_path_passes_from_any_cwd(self):
        """The hook reads a relative script from the cwd, not from where a `cd` went, so a worktree's own copy is refused;
        the main checkout's script by its absolute path is excepted from every cwd, that worktree's too."""
        with tempfile.TemporaryDirectory() as tmp:
            root = os.path.join(os.path.realpath(tmp), "main")
            tree = os.path.join(root, ".claude", "worktrees", "agent-1")
            product = os.path.join(root, "workspaces", "acme", "acme-app")
            for folder in (root, tree):
                os.makedirs(os.path.join(folder, "scripts"))
                Path(folder, "scripts", "cq_archive.py").write_text("", encoding="utf-8")
            os.makedirs(product)
            live = f"{root}/{F}"
            script = f"{root}/scripts/cq_archive.py"
            for cwd in (root, tree, product, "/tmp", "/"):
                with self.subTest(cwd=cwd):
                    scope = cq_write.Scope(cwd, root)
                    for args in ([script, live, "--order", "D-20260101-acme-launch/4"],
                                 [script, live, "--order", "D-20260101-acme-launch/4", "--dry-run"]):
                        self.assertTrue(cq_write.excepted("python3", args, scope))
                    self.assertIsNone(cq_write.command_reason(
                        f"python3 {script} {live} --order D-20260101-acme-launch/4 --dry-run", cwd, root))
            scope = cq_write.Scope(tree, root)  # the worktree's own copy, by a relative or its absolute path
            self.assertFalse(cq_write.excepted("python3", ["scripts/cq_archive.py", live, "--order", "/4"], scope))
            self.assertFalse(cq_write.excepted("python3", [f"{tree}/scripts/cq_archive.py", live, "--order", "/4"],
                                               scope))
            self.assertIn("python3 runs with a ceo-questions.md", cq_write.command_reason(
                f"cd {root} && python3 scripts/cq_archive.py {F} --order D-20260101-acme-launch/4 --dry-run", tree,
                root))
            self.assertTrue(cq_write.excepted("python3", ["scripts/cq_archive.py", live, "--order", "/4"],
                                              cq_write.Scope(product, root)))  # no copy there: the repo's

    def test_a_command_over_256000_characters_that_names_it_is_refused(self):
        # past this the parse could near the hook's 60 s limit.
        self.assertIn("too long", cq_write.command_reason(f"cat {F} '" + "x" * 256_000 + "'", ROOT, ROOT))
        self.assertIsNone(cq_write.command_reason("cat '" + "x" * 300_000 + "'", ROOT, ROOT))  # names no file
        self.assertIsNone(cq_write.command_reason(f"cat {F} '" + "x" * 20_000 + "'", ROOT, ROOT))

    def test_a_word_with_many_mentions_is_read_fast(self):
        start = time.monotonic()
        cq_write.command_reason("cat /tmp" + "/ceo-questions.md" * 1500, ROOT, ROOT)
        self.assertLess(time.monotonic() - start, 2)

    def test_a_long_word_with_many_slashes_is_read_fast(self):
        start = time.monotonic()
        self.assertIsNone(cq_write.command_reason("cat " + "a/" * 20000 + "x " + F, ROOT, ROOT))
        self.assertLess(time.monotonic() - start, 5)

    def test_heredocs_are_read_as_the_regex_read_them(self):
        pieces = ["<<", "<<-", "<", "-", " ", "\t", "\n", "'", '"', "E", "EO", "EOF", "a", ".", "\r", "é", "_",
                  "EOF\n", " EOF \n", "<<EOF\n", "<<'EOF'\n", "<<-E\n", "\tE\n", "$(", ")"]
        rng = random.Random(39)
        for _ in range(20_000):
            text = "".join(rng.choice(pieces) for _ in range(rng.randint(0, 30)))
            self.assertEqual(cq_write.heredocs(text, lambda quote, rest, body: f"[{quote}|{rest}|{body}]"),
                             HEREDOC.sub(lambda m: f"[{m.group(1)}|{m.group(3)}|{m.group(4)}]", text), repr(text))

    def test_crafted_heredocs_are_read_in_near_linear_time(self):
        # Unterminated `<<EOF`s, one a line or in one line, one 8,000-character name, and k lines of lengths 1..k, then
        # k-character names with no end line (about n^1.5).
        k = 500
        lines = "".join("b" * size + "\n" for size in range(1, k + 1))
        names = ("<<" + "a" * k + "\n") * 250
        for command, refused in [(f"cat {F}\n" + "cat <<EOF\n" * 25_000, True),
                                 (f"cat {F} <<" + "a" * 8_000 + "\n" + "x\n" * 120_000, True),
                                 (f"cat {F}\n" + lines + "cat " + names, True),
                                 (f"cat {F}\n" + lines + "echo '" + names + "'", False)]:
            with self.subTest(command=command[:60]):
                start = time.monotonic()
                cq_write.heredocs(command, lambda quote, rest, body: " ")
                self.assertLess(time.monotonic() - start, 1)
                reason = cq_write.command_reason(command, ROOT, ROOT)
                self.assertEqual(reason is not None, refused, reason)
                self.assertLess(time.monotonic() - start, 8)

    def test_a_command_still_read_after_the_timer_is_refused(self):
        # 4,000 `for x in` words take longer to read than the hook has.
        event = {"tool_name": "Bash", "agent_id": "a1", "tool_input": {"command": f"cat {F}; " + "for x in " * 4000}}
        with mock.patch.object(cq_write, "SECONDS", 1):
            start = time.monotonic()
            reason = cq_write.cq_reason(event, ROOT)
        self.assertLess(time.monotonic() - start, 5)
        self.assertIn("took over 1 s to read", reason)
        self.assertEqual(signal.getitimer(signal.ITIMER_REAL), (0.0, 0.0))
        self.assertIsNone(cq_write.cq_reason({**event, "tool_input": {"command": f"cat {F}"}}, ROOT))

    def test_a_deferred_folder_reason_still_read_at_the_timer_is_refused(self):
        """A `bash -c` rm of the
        orders folder in a command that names the file goes to the later list (scope.defer), and a slow tail read after
        it meets the timer: the command is refused, never passed with the deferred reason untold."""
        first = f"bash -c 'rm -rf workspaces/x/content/orders; cat {F}'"
        event = {"tool_name": "Bash", "agent_id": "a1", "cwd": ROOT}
        quick = cq_write.cq_reason({**event, "tool_input": {"command": f"{first}; cat {F}"}}, ROOT)
        self.assertIn("rm removes or moves a folder that holds a ceo-questions.md", quick)  # told at the end
        told = []

        def folder_reason(*args):
            told.append(original(*args))
            return told[-1]
        original = cq_write.folder_reason
        slow = f"{first}; bash -c 'cat {F}; " + "for x in " * 4000 + "'"  # the inner text read after the deferral
        with mock.patch.object(cq_write, "SECONDS", 1), mock.patch.object(cq_write, "folder_reason", folder_reason):
            start = time.monotonic()
            reason = cq_write.cq_reason({**event, "tool_input": {"command": slow}}, ROOT)
        self.assertLess(time.monotonic() - start, 5)
        self.assertIn("rm removes or moves a folder that holds a ceo-questions.md", told)  # deferred before the timer
        self.assertIn("took over 1 s to read", reason)
        self.assertEqual(signal.getitimer(signal.ITIMER_REAL), (0.0, 0.0))


# Lines that pass for the CEO's (cq_write.ceo_line), and lines that don't. Every
# line capacity_scan.by_ceo counts as the CEO's is in the first list's kind (CeoLines checks it). Made-up lines.
CEO_LINES = [
    "CEO RULING /1/2 12:20Z: yes.",
    "- CEO RULING /1/2: yes.",
    "**CEO RULING** /1/2: yes.",
    "- **CEO** RULING /1/2: yes.",
    "   CEO: on NEEDS-CEO-NOW /1.CTO 11:30Z, yes.",
    "\tCEO yes.",
    "CEOx",
    "HANDLED (CEO, RULING /1/3 (6)) on NEEDS-CEO-NOW /1.CTO 12:30Z.",
    "(CEO) RULING /1/2.",
    "NEEDS-CEO-NOW /1.CTO 2026-01-18T11:30Z: x (CEO's call)",
    "HANDLED /1.CTO 2026-01-16T12:30Z (CEO) done.",
    "HANDLED (x) 2026-01-16T12:30Z (CEO 12:30Z) on NEEDS-CEO-NOW /1.CTO 11:30Z.",
    "HANDLED (x) 12:30Z   (CEO) done.",
]
NOT_CEO_LINES = [
    "REPORT /8 DONE: per CEO RULING /1/3 12:20Z.",
    "HANDLED /1.CTO 12:30Z: done, per CEO RULING /1/3 12:20Z",
    "NEEDS-CEO-NOW /1.CTO 2026-01-18T11:30Z (CTO): x",
    "QUESTION /2.WS-1 -> CEO   2026-01-18T11:20Z (WS-1 Staff). x",
    "HANDLED (x) 12:30Z: see (CEO RULING /1/3).",
    "COORD /1.WS-2 11:20Z -> CEO, CTO: x",
    "1. CEO",
    "ceo-questions.md",
    "Ceo x",
    "",
]
CEO_REFUSED = [  # each with {f}, a live file: `>>`, tee -a and cq_archive's --add, and what they may write
    "echo 'CEO RULING /1/2: yes.' >> {f}",
    "echo 'HANDLED (CEO, RULING /1/3) on NEEDS-CEO-NOW /1.CTO 11:30Z' >> {f}",
    "echo CEO yes >> {f}",
    "echo C\\\nEO yes >> {f}",  # the shell joins the words around a backslash-newline
    "echo -n '- **CEO** RULING x' >> {f}",
    "echo HANDLED /1.CTO 12:30Z '(CEO)' >> {f}",
    "printf '%s\\n' '- **CEO** RULING x' >> {f}",
    "printf 'REPORT x\\nCEO RULING y\\n' >> {f}",
    "printf '%s (%s)\\n' 'HANDLED x' CEO >> {f}",
    "echo -e 'REPORT x\\x0a  CEO y' &>> {f}",
    "echo $'REPORT x\\nCEO y' >> {f}",
    "cat >> {f} <<'EOF'\nREPORT x\nCEO RULING y\nEOF",
    "cat <<EOF >> {f}\n(CEO) yes $(date -u)\nEOF",
    "tee -a {f} <<< 'CEO RULING y' > /dev/null",
    "echo 'CEO y' | tee -a {f} > /dev/null",
    "printf 'CEO y\\n' | sponge -a {f}",
    "python3 scripts/cq_archive.py {f} --order /1 --add 'CEO RULING /1/2: yes.'",
    "python3 scripts/cq_archive.py {f} --order /1 --ad='(CEO) yes'",
    "bash -c \"echo 'CEO y' >> {f}\"",
    "echo \"$(echo 'CEO y')\" >> {f}",
    "echo \"$(printf '%s' 'CEO y')\" | tee -a {f}",
    "L='CEO RULING y'; echo \"$L\" >> {f}",
    "F={f}; echo 'CEO y' >> $F",
    "{{ echo 'REPORT x'; echo 'CEO y'; }} >> {f}",
    "exec 3>>{f}; echo 'CEO y' >&3",
    "eval \"echo 'CEO y' >> {f}\"",
    "echo 'CEO y' > >(cat >> {f})",
    "echo 'CEO y' >> \"$(echo {f})\"",
]
CEO_ALLOWED = [
    "echo 'REPORT /8 DONE: per CEO RULING /1/3 12:20Z.' >> {f}",
    "echo REPORT /86 DONE, for the CEO >> {f}",
    "echo 'NEEDS-CEO-NOW /1.CTO 2026-01-18T11:30Z (CTO): x' >> {f}",
    "printf '%s\\n' 'HANDLED /1.CTO 12:30Z: done, per CEO RULING /1/3 12:20Z' >> {f}",
    "python3 scripts/cq_archive.py {f} --order /1 --add 'HANDLED /1.CTO 12:30Z: per CEO RULING /1/3'",
    "grep -n '^CEO' {f}",
    "grep 'CEO RULING' {f} | head",
    "echo 'CEO lines:'; grep -c '^CEO' {f}",
    "echo 'CEO y' >> /tmp/scratch/ceo-questions.md; cat {f}",
    "echo 'CEO y' >> /tmp/scratch/ceo-questions-archive.md; cat {f}",  # a live archive's: ArchiveLines
    "cat >> {f} <<'EOF'\nREPORT x: the CEO asked\nEOF",
]
# an append whose first line is indented, numbered or starts `(` joins the line above, maybe the CEO's
CONTINUES_REFUSED = [
    "echo '(2) NEEDS-CEO-NOW /2.CTO 11:30Z: approved.' >> {f}",
    "echo '  on NEEDS-CEO-NOW /2.CTO 11:30Z: approved.' >> {f}",
    "printf '1. yes\\n' >> {f}",
    "echo -e '2) yes\\nHANDLED x' | tee -a {f}",
    "cat >> {f} <<'EOF'\n\t(3) yes\nEOF",
    "cat <<-EOF >> {f}\n\t  (3) yes\n\tEOF",  # `<<-` takes the tabs off, not the spaces
    "python3 scripts/cq_archive.py {f} --order /1 --add '(2) on NEEDS-CEO-NOW /2.CTO 11:30Z: approved.'",
    "L='  yes'; echo \"$L\" >> {f}",
    "printf '%s\\n' 'HANDLED x' '  (2) yes' >> {f}",  # over-broad: each printf word's first line counts
]
CONTINUES_ALLOWED = [
    "echo 'HANDLED /1.CTO 12:30Z: (2) done' >> {f}",
    "cat >> {f} <<'EOF'\nHANDLED /1.CTO 12:30Z: done\n  (2) the detail\nEOF",
    "echo -e 'REPORT x\\n  1. y' >> {f}",
    "echo '12 tests pass' >> {f}",
    "echo '' >> {f}",
    "cat <<-EOF >> {f}\n\tHANDLED x\n\t  y\n\tEOF",
]


class CeoLines(unittest.TestCase):
    """A subagent's write that adds a line passing for the CEO's to a live
    ceo-questions.md, a product's or an order's own, is refused by `>>`, tee -a, cq_archive's --add, Edit, MultiEdit and
    Write; the main session (no agent_id) passes; so do an agent's own lines, reads and scratch copies."""

    def test_a_ceo_line_is_every_one_the_scan_counts_as_the_ceo_s(self):
        sys.path.insert(0, str(REPO / "scripts"))
        import capacity_scan
        for line in CEO_LINES + NOT_CEO_LINES:
            with self.subTest(line=line):
                self.assertEqual(cq_write.ceo_line(line), line in CEO_LINES)
                if capacity_scan.by_ceo(line):
                    self.assertTrue(cq_write.ceo_line(line))
        self.assertEqual([line for line in CEO_LINES if capacity_scan.by_ceo(line)], CEO_LINES[:4])

    def test_a_subagents_append_of_a_ceo_line_is_refused_and_the_main_session_s_passes(self):
        event = {"tool_name": "Bash", "cwd": ROOT}
        for f in (F, to_order(F)):
            for form in CEO_REFUSED:
                command = form.format(f=f)
                with self.subTest(command=command):
                    self.assertIsNone(cq_write.command_reason(command, ROOT, ROOT))  # no other reason
                    message = cq_write.cq_reason({**event, "agent_id": "a1", "tool_input": {"command": command}}, ROOT)
                    self.assertIn("a line that passes for the CEO's goes into a ceo-questions.md", message or "")
                    self.assertIn("(cto.md, \"Your question file\")", message)
                    self.assertIsNone(cq_write.cq_reason({**event, "tool_input": {"command": command}}, ROOT))
            for form in CEO_ALLOWED:
                command = form.format(f=f)
                with self.subTest(command=command):
                    self.assertIsNone(cq_write.cq_reason({**event, "agent_id": "a1", "tool_input": {"command": command}},
                                                         ROOT))

    def test_continues_is_the_scans_goes_on(self):
        sys.path.insert(0, str(REPO / "scripts"))
        import capacity_scan
        self.assertEqual(cq_write.CONTINUES.pattern, capacity_scan.GOES_ON.pattern)

    def test_a_subagents_append_of_a_line_that_joins_the_one_above_is_refused(self):
        event = {"tool_name": "Bash", "cwd": ROOT}
        for f in (F, to_order(F)):
            for form in CONTINUES_REFUSED:
                command = form.format(f=f)
                with self.subTest(command=command):
                    self.assertIsNone(cq_write.command_reason(command, ROOT, ROOT))  # no other reason
                    message = cq_write.cq_reason({**event, "agent_id": "a1", "tool_input": {"command": command}}, ROOT)
                    self.assertIn("an appended first line that is indented, numbered or starts `(`", message or "")
                    self.assertIn("(cto.md, \"Your question file\")", message)
                    self.assertIsNone(cq_write.cq_reason({**event, "tool_input": {"command": command}}, ROOT))
            for form in CONTINUES_ALLOWED:
                command = form.format(f=f)
                with self.subTest(command=command):
                    self.assertIsNone(cq_write.cq_reason({**event, "agent_id": "a1", "tool_input": {"command": command}},
                                                         ROOT))

    def test_an_edit_that_puts_a_line_under_a_ceo_line_is_refused(self):
        """An Edit or MultiEdit that leaves an indented, numbered or `(` line under a CEO
        line where it didn't stand (added, changed, or a blank or a line the scan cuts at taken out above it) is
        refused, each one a line the capacity scan then joins to the CEO's reply; one that moves a CEO line out by hand,
        with its lines or from its last line up, or touches only an agent's own lines, passes."""
        sys.path.insert(0, str(REPO / "scripts"))
        import capacity_scan

        def ceo_reply_lines(text):
            return Counter(line for _, reply in capacity_scan.replies(text.split("\n")) if capacity_scan.by_ceo(reply)
                           for line in reply.split("\n"))

        def edit(old, new_text):
            return {"old_string": old, "new_string": new_text}
        text = ("# ORDER D-20260101-x/2 (cto, 2026-01-18)\nNEEDS-CEO-NOW /2.CTO 2026-01-18T11:30Z: x\n"
                "CEO RULING /2/1 11:25Z: yes.\n(1) QUESTION /2.WS-1.q1 11:20Z: yes.\nHOLD /2.CTO 11:35Z\n"
                "CEO RULING /2/2 11:50Z: yes.\n\n  on NEEDS-CEO-NOW /2.CTO 11:30Z: approved.\n"
                "HANDLED /2.CTO 11:40Z: done\n"
                "CEO RULING /2/3 12:20Z: yes.\n  CTO: noted\n  (2) on NEEDS-CEO-NOW /2.CTO 11:30Z: approved too.\n")
        refused = [
            ("Edit", edit("CEO RULING /2/1 11:25Z: yes.",
                          "CEO RULING /2/1 11:25Z: yes.\n(3) on NEEDS-CEO-NOW /2.CTO 11:30Z: approved.")),
            ("Edit", edit("(1) QUESTION /2.WS-1.q1 11:20Z: yes.",
                          "(1) QUESTION /2.WS-1.q1 11:20Z: yes, and NEEDS-CEO-NOW /2.CTO 11:30Z.")),
            ("Edit", edit("11:50Z: yes.\n\n", "11:50Z: yes.\n")),  # the blank under a CEO line taken out
            ("Edit", edit("  CTO: noted\n", "")),  # a line the scan cuts at taken out
            ("Edit", edit("HOLD /2.CTO 11:35Z", "  HOLD /2.CTO 11:35Z")),
            ("MultiEdit", {"edits": [edit("HOLD /2.CTO 11:35Z", "HANDLED x"),
                                     edit("CEO RULING /2/3 12:20Z: yes.", "CEO RULING /2/3 12:20Z: yes.\n  1. ok")]}),
        ]
        allowed = [
            ("Edit", edit("HOLD /2.CTO 11:35Z", "HANDLED /2.CTO 12:20Z: per CEO RULING /2/1")),
            ("Edit", edit("CEO RULING /2/1 11:25Z: yes.\n(1) QUESTION /2.WS-1.q1 11:20Z: yes.\n", "")),
            ("Edit", edit("(1) QUESTION /2.WS-1.q1 11:20Z: yes.\n", "")),  # from its last line up
            ("Edit", edit("CEO RULING /2/1 11:25Z: yes.\n", "")),  # its line now under an agent's
            ("Edit", edit("HANDLED /2.CTO 11:40Z: done", "HANDLED /2.CTO 11:40Z: done\n  the detail")),
            ("MultiEdit", {"edits": [edit("  (2) on NEEDS-CEO-NOW /2.CTO 11:30Z: approved too.\n", ""),
                                     edit("  CTO: noted\n", ""), edit("CEO RULING /2/3 12:20Z: yes.\n", "")]}),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            files = [root / "workspaces" / "x" / "content" / "ceo-questions.md",
                     root / "workspaces" / "x" / "content" / "orders" / "D-20260101-x" / "2" / "ceo-questions.md"]
            for path in files:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text, encoding="utf-8")
                for tool, tool_input in refused + allowed:
                    event = {"tool_name": tool, "tool_input": {"file_path": str(path), **tool_input}}
                    with self.subTest(path=path, tool=tool, tool_input=tool_input):
                        before, after = cq_write.edited(tool, tool_input, path)
                        joins = ceo_reply_lines(after) - ceo_reply_lines(before)
                        message = cq_write.write_reason({**event, "agent_id": "a1"}, str(path), path, str(root))
                        if (tool, tool_input) in refused:
                            self.assertTrue(joins)  # the scan reads a new line as the CEO's
                            self.assertIn(f"{tool} leaves an indented, numbered or `(` line under a CEO line",
                                          message or "")
                            self.assertIn("(cto.md, \"Your question file\")", message)
                        else:
                            self.assertFalse(joins)
                            self.assertIsNone(message)
                        self.assertIsNone(cq_write.write_reason(event, str(path), path, str(root)))  # main session

    def test_a_ceo_line_moved_by_hand_top_down_under_another_is_refused_and_bottom_up_passes(self):
        """A CEO line with a numbered line, right under another CEO reply, taken out first
        leaves its line under the other one, and is refused (the scan reads the same lines as the CEO's, so this one
        is over-broad); taken out from its last line up, each Edit passes (cto.md, "Logs")."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            path = root / "workspaces" / "x" / "content" / "ceo-questions.md"
            path.parent.mkdir(parents=True)
            path.write_text("# ORDER D-20260101-x/2\nCEO RULING /2/1 11:25Z: yes.\n(1) QUESTION /2.WS-1.q1 11:20Z: yes.\n"
                            "CEO RULING /2/2 11:50Z: no.\n(1) QUESTION /2.WS-1.q2 11:40Z: no.\n", encoding="utf-8")

            def reason(old):
                event = {"tool_name": "Edit", "agent_id": "a1",
                         "tool_input": {"file_path": str(path), "old_string": old, "new_string": ""}}
                return cq_write.write_reason(event, str(path), path, str(root))
            message = reason("CEO RULING /2/2 11:50Z: no.\n")
            self.assertIn("Edit leaves an indented, numbered or `(` line under a CEO line", message or "")
            self.assertIn("from its last line up", message)
            for old in ("(1) QUESTION /2.WS-1.q2 11:40Z: no.\n", "CEO RULING /2/2 11:50Z: no.\n"):
                self.assertIsNone(reason(old))
                path.write_text(path.read_text(encoding="utf-8").replace(old, ""), encoding="utf-8")

    def test_a_long_append_is_read_in_time(self):
        """The CEO-line read adds passes over a command that appends (tokens, heredocs): a long one still passes well
        inside the 20 s timer."""
        event = {"tool_name": "Bash", "agent_id": "a1", "cwd": ROOT}
        for command in (f"echo 'REPORT x " + "y " * 100_000 + f"' >> {F}",
                        f"cat >> {F} <<'EOF'\n" + "REPORT a line of text\n" * 10_000 + "EOF"):
            with self.subTest(command=command[:40]):
                start = time.monotonic()
                self.assertIsNone(cq_write.cq_reason({**event, "tool_input": {"command": command}}, ROOT))
                self.assertLess(time.monotonic() - start, 10)

    def test_an_older_reason_is_told_first(self):
        message = cq_write.cq_reason({"tool_name": "Bash", "agent_id": "a1", "cwd": ROOT,
                                      "tool_input": {"command": f"echo 'CEO y' > {F}"}}, ROOT)
        self.assertIn("`>` rewrites a ceo-questions.md whole", message)

    def test_a_ceo_line_read_still_going_at_the_timer_is_refused(self):
        event = {"tool_name": "Bash", "agent_id": "a1", "cwd": ROOT,
                 "tool_input": {"command": f"echo 'REPORT x' >> {F}"}}
        with mock.patch.object(cq_write, "SECONDS", 1), \
                mock.patch.object(cq_write, "ceo_reason", side_effect=lambda *args: time.sleep(4)):
            start = time.monotonic()
            reason = cq_write.cq_reason(event, ROOT)
        self.assertLess(time.monotonic() - start, 3)
        self.assertIn("took over 1 s to read", reason)
        self.assertEqual(signal.getitimer(signal.ITIMER_REAL), (0.0, 0.0))

    def test_an_edit_multiedit_or_write_that_adds_a_ceo_line_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            text = ("# ORDER D-20260101-x/2 (cto, 2026-01-18)\nQUESTION /2.CTO 2026-01-18T11:20Z -> CEO: x\n"
                    "CEO RULING /2/1 11:25Z: yes.\nHOLD /2.CTO 11:35Z\n- XO note\n")
            files = [root / "workspaces" / "x" / "content" / "ceo-questions.md",
                     root / "workspaces" / "x" / "content" / "orders" / "D-20260101-x" / "2" / "ceo-questions.md"]
            for path in files:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text, encoding="utf-8")
            new = root / "workspaces" / "x" / "content" / "orders" / "D-20260101-x" / "3" / "ceo-questions.md"
            scratch = root / "scratch" / "ceo-questions.md"
            scratch.parent.mkdir()
            scratch.write_text(text, encoding="utf-8")

            def edit(old, new_text, **more):
                return {"old_string": old, "new_string": new_text, **more}
            refused = [
                ("Edit", edit("HOLD /2.CTO 11:35Z", "CEO RULING /2/2: yes.")),
                ("Edit", edit("HOLD", "HANDLED (CEO)")),
                ("Edit", edit("HOLD /2.CTO 11:35Z", "HANDLED /2.CTO 11:40Z\n  - **CEO** yes")),
                ("Edit", edit("CEO RULING /2/1 11:25Z: yes.", "CEO RULING /2/1 11:25Z: yes, on QUESTION /2.CTO 11:20Z.")),
                ("Edit", edit("X", "CE")),  # `- XO note` becomes `- CEO note`
                ("Edit", edit("not in the file", "CEO x")),
                ("Edit", edit("HOLD", "(CEO) HOLD", replace_all=True)),
                ("MultiEdit", {"edits": [edit("HOLD /2.CTO 11:35Z", "HANDLED x"), edit("HANDLED x", "CEO x")]}),
            ]
            allowed = [
                ("Edit", edit("HOLD /2.CTO 11:35Z", "HANDLED /2.CTO 11:40Z: per CEO RULING /2/1")),
                ("Edit", edit("CEO RULING /2/1 11:25Z: yes.\nHOLD /2.CTO 11:35Z",
                              "CEO RULING /2/1 11:25Z: yes.\nHANDLED /2.CTO 11:40Z")),
                ("Edit", edit("CEO RULING /2/1 11:25Z: yes.\n", "")),  # moved out by hand (cto.md, "Logs")
                ("MultiEdit", {"edits": [edit("HOLD", "HANDLED"), edit("- XO note", "- note")]}),
            ]
            write = [("Write", {"content": "# ORDER /3\nCEO RULING /3/1: yes.\n"})]
            for path, refused, allowed in ((files[0], refused, allowed), (files[1], refused, allowed),
                                           (new, write, [("Write", {"content": "# ORDER /3\nREPORT /3 DONE\n"})])):
                for tool, tool_input in refused:
                    event = {"tool_name": tool, "tool_input": {"file_path": str(path), **tool_input}}
                    with self.subTest(path=path, tool=tool, tool_input=tool_input):
                        message = cq_write.write_reason({**event, "agent_id": "a1"}, str(path), path, str(root))
                        self.assertIn(f"{tool} adds a line that passes for the CEO's", message or "")
                        self.assertIsNone(cq_write.write_reason(event, str(path), path, str(root)))  # main session
                        self.assertIsNone(cq_write.write_reason({**event, "agent_id": "a1"}, str(scratch), scratch,
                                                                str(root)))
                for tool, tool_input in allowed:
                    event = {"tool_name": tool, "agent_id": "a1", "tool_input": {"file_path": str(path), **tool_input}}
                    with self.subTest(path=path, tool=tool, tool_input=tool_input):
                        self.assertIsNone(cq_write.write_reason(event, str(path), path, str(root)))


# The archive beside a live file. Its ceo-questions.md holds a CEO block (C with
# L1 and L2 under it) and an agent's REPORT with a line under it. Made-up lines.
C, L1, L2 = "CEO RULING /2/1 11:25Z: yes.", "(1) QUESTION /2.WS-1.q1 11:20Z: yes.", "  2. and the detail"
LIVE = f"# ORDER D-20260101-x/2 (cto, 2026-01-18)\nREPORT /2.1 DONE\n  1. the agent detail\n{C}\n{L1}\n{L2}\n"
ARCHIVED = ("# ceo-questions, archive: search it, don't load it\n## ORDER D-20260101-x/1\n"
            "CEO RULING /1/1 10:00Z: old.\nHANDLED /1.CTO 10:05Z: done\n")
ARCHIVE_REFUSED = {  # each with {a}, a live archive, and {d}, its folder: the kind of line refused
    "echo 'CEO RULING /2/9 11:25Z: yes.' >> {a}": "a line that passes for the CEO's",
    "echo '- **CEO** yes' &>> {a}": "a line that passes for the CEO's",
    "echo 'HANDLED /2.CTO 2026-01-16T12:30Z (CEO) done.' >> {a}": "a line that passes for the CEO's",
    "printf 'REPORT x\\nCEO RULING y\\n' >> {a}": "a line that passes for the CEO's",
    "tee -a {a} <<< 'CEO y' > /dev/null": "a line that passes for the CEO's",
    "echo 'CEO y' | sponge -a {a}": "a line that passes for the CEO's",
    "python3 scripts/cq_archive.py {a} --order /1 --add 'CEO y'": "a line that passes for the CEO's",
    "bash -c \"echo 'CEO y' >> {a}\"": "a line that passes for the CEO's",
    "A={a}; echo 'CEO y' >> \"$A\"": "a line that passes for the CEO's",
    "echo 'CEO y' >> {d}/ceo-questions-arch\\\nive.md": "a line that passes for the CEO's",  # the shell joins it
    f"cat >> {{a}} <<'EOF'\n{C}\n(1) QUESTION /2.WS-1.q9 11:20Z: approved.\nEOF": "may join a CEO line",
    "echo '(1) QUESTION /2.WS-1.q9 11:20Z: approved.' >> {a}": "may join a CEO line",
    "echo '  1. the agent detail' >> {a}": "may join a CEO line",  # in the file, but under the agent's line
    "printf '%s\\n' '  on NEEDS-CEO-NOW /2.CTO 11:30Z: approved.' >> {a}": "may join a CEO line",
    "echo 'CEO y' > {a}": "a line that passes for the CEO's",  # `>` too
    "echo 'CEO y' >| {a}": "a line that passes for the CEO's",
    # the line stands in the file, but where it goes can't be told: no file beside it
    f"cd {{d}} && echo '{C}' >> ceo-questions-archive.md": "a line that passes for the CEO's",
    f"echo '{C}' >> workspaces/x/content/ceo-questions-archive.md": "a line that passes for the CEO's",
    f"echo '{C}' >> $(echo {{a}})": "a line that passes for the CEO's",
    f"echo '{C}' >> $UNSET/ceo-questions-archive.md": "a line that passes for the CEO's",
}
ARCHIVE_ALLOWED = [
    f"cat >> {{a}} <<'EOF'\n{C}\n{L1}\n{L2}\nEOF",  # the by-hand move's `>>`, while the lines stand in the file
    f"echo '{L2}' >> {{a}}",
    f"printf '%s\\n' '{C}' >> {{a}}",
    f"A={{a}}; echo '{C}' >> \"$A\"",
    "echo 'HANDLED /2.1 11:20Z: done, per CEO RULING /2/1' >> {a}",
    "cat >> {a} <<'EOF'\nREPORT /2.1 DONE\n  1. the agent detail\nEOF",  # under the agent's own first line
    "grep -n '^CEO' {a}",
    "echo 'CEO y' >> /tmp/scratch/ceo-questions-archive.md",  # not a live one
]


class ArchiveLines(unittest.TestCase):
    """A subagent's write that adds to a live ceo-questions-archive.md, a
    product's or one beside an order's file, a line that passes for the CEO's, or one that may join one there, is
    refused by `>>`, Edit, MultiEdit and Write, unless the ceo-questions.md in the same folder holds that line then (a
    joining line under a CEO line there): the by-hand move (cto.md, "Logs"). The main session passes."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        content = self.root / "workspaces" / "x" / "content"
        self.archives = [content / "ceo-questions-archive.md",
                         content / "orders" / "D-20260101-x" / "2" / "ceo-questions-archive.md"]
        for archive in self.archives:
            archive.parent.mkdir(parents=True, exist_ok=True)
            archive.with_name("ceo-questions.md").write_text(LIVE, encoding="utf-8")
            archive.write_text(ARCHIVED, encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def bash(self, command, agent_id="a1"):
        event = {"tool_name": "Bash", "cwd": str(self.root), "tool_input": {"command": command}}
        return cq_write.cq_reason({**event, "agent_id": agent_id} if agent_id else event, str(self.root))

    def tool(self, path, tool, tool_input, agent_id="a1"):
        event = {"tool_name": tool, "tool_input": {"file_path": str(path), **tool_input}}
        return cq_write.write_reason({**event, "agent_id": agent_id} if agent_id else event, str(path), path,
                                     str(self.root))

    def test_a_subagents_append_of_a_ceo_line_the_file_beside_doesnt_hold_is_refused(self):
        for archive in self.archives:
            for form, kind in ARCHIVE_REFUSED.items():
                command = form.format(a=archive, d=archive.parent)
                with self.subTest(command=command):
                    self.assertIsNone(cq_write.command_reason(command, str(self.root), str(self.root)))
                    self.assertIsNone(cq_write.ceo_reason(command, str(self.root), str(self.root)))
                    message = self.bash(command)
                    self.assertIn(kind, message or "")
                    self.assertIn("goes into a ceo-questions-archive.md, and the ceo-questions.md beside it doesn't "
                                  "hold it", message)
                    self.assertIn("(cto.md, Working rules, \"Logs\")", message)
                    self.assertIn("refusal is final", message)
                    self.assertIsNone(self.bash(command, None))  # the main session
            for form in ARCHIVE_ALLOWED:
                command = form.format(a=archive, d=archive.parent)
                with self.subTest(command=command):
                    self.assertIsNone(self.bash(command))

    def test_a_link_to_an_archive_is_checked_against_the_file_beside_the_archive_it_points_to(self):
        """A link named
        ceo-questions-archive.md outside the live tree, beside a scratch ceo-questions.md that holds the line, points at
        a live archive whose own file beside it doesn't: folder_of reads the real path, as may_be_live does."""
        scratch = self.root / "scratch"
        scratch.mkdir()
        (scratch / "ceo-questions.md").write_text("CEO y\n", encoding="utf-8")  # a file the subagent may write
        for archive in self.archives:
            link = scratch / "ceo-questions-archive.md"
            link.unlink(missing_ok=True)
            link.symlink_to(archive)
            with self.subTest(archive=archive):
                self.assertEqual(cq_write.folder_of(str(link), cq_write.Scope(str(self.root), str(self.root))),
                                 str(archive.parent))
                self.assertIn("a line that passes for the CEO's", self.bash(f"echo 'CEO y' >> {link}") or "")
                self.assertIsNone(self.bash(f"echo '{C}' >> {link}"))  # the file beside the real archive holds it
        self.assertIsNone(self.bash(f"echo 'CEO y' >> {scratch}/ceo-questions-archive.md", None))  # the main session

    def test_a_subagents_edit_multiedit_or_write_of_a_ceo_line_the_file_beside_doesnt_hold_is_refused(self):
        def edit(old, new_text):
            return {"old_string": old, "new_string": new_text}
        last = "HANDLED /1.CTO 10:05Z: done"
        refused = [
            ("Edit", edit(last, f"{last}\nCEO RULING /2/9: yes."), "adds a line that passes for the CEO's"),
            ("Edit", edit(last, f"{last}\n{C}\n(1) QUESTION /2.WS-1.q9 11:20Z: approved."), "leaves an indented"),
            ("Edit", edit("CEO RULING /1/1 10:00Z: old.", "CEO RULING /1/1 10:00Z: old.\n  1. the agent detail"),
             "leaves an indented"),
            ("Edit", edit("not in the file", "(CEO) yes"), "adds a line that passes for the CEO's"),
            ("MultiEdit", {"edits": [edit(last, "HANDLED x"), edit("HANDLED x", "HANDLED (CEO) x")]},
             "adds a line that passes for the CEO's"),
            ("Write", {"content": ARCHIVED + "CEO RULING /2/9: yes.\n"}, "adds a line that passes for the CEO's"),
            ("Write", {"content": ARCHIVED + f"{C}\n  (3) approved.\n"}, "leaves an indented"),
        ]
        allowed = [
            ("Edit", edit(last, f"{last}\n{C}\n{L1}\n{L2}")),  # the by-hand move, by Edit
            ("Edit", edit(last, f"{last}\nHANDLED /2.1 11:20Z: done\n  the detail")),
            ("MultiEdit", {"edits": [edit(last, f"{last}\n{C}"), edit(C, f"{C}\n{L1}")]}),
            ("Write", {"content": ARCHIVED + f"{C}\n{L1}\n{L2}\nREPORT /2.1 DONE\n"}),
        ]
        for archive in self.archives:
            for tool, tool_input, words in refused:
                with self.subTest(archive=archive, tool=tool, tool_input=tool_input):
                    message = self.tool(archive, tool, tool_input)
                    self.assertIn(f"{tool} {words}", message or "")
                    self.assertIn("ceo-questions-archive.md, and the ceo-questions.md beside it doesn't hold it", message)
                    self.assertIn("(cto.md, Working rules, \"Logs\")", message)
                    self.assertIsNone(self.tool(archive, tool, tool_input, None))  # the main session
            for tool, tool_input in allowed:
                with self.subTest(archive=archive, tool=tool, tool_input=tool_input):
                    self.assertIsNone(self.tool(archive, tool, tool_input))
        new = self.root / "workspaces" / "x" / "content" / "orders" / "D-20260101-x" / "3" / "ceo-questions-archive.md"
        new.parent.mkdir()
        new.with_name("ceo-questions.md").write_text(LIVE, encoding="utf-8")
        self.assertIn("Write adds a line that passes for the CEO's",
                      self.tool(new, "Write", {"content": "CEO RULING /3/1: yes.\n"}) or "")
        self.assertIsNone(self.tool(new, "Write", {"content": f"{C}\n{L1}\n"}))
        new.with_name("ceo-questions.md").unlink()  # no file beside it: it holds nothing
        self.assertIn("Write adds a line that passes for the CEO's", self.tool(new, "Write", {"content": f"{C}\n"}) or "")
        scratch = self.root / "scratch" / "ceo-questions-archive.md"
        self.assertIsNone(self.tool(scratch, "Write", {"content": "CEO RULING /3/1: yes.\n"}))  # not a live one

    def test_the_by_hand_move_bottom_up_passes_and_the_same_append_after_it_is_refused(self):
        """cto.md, "Logs", in ARCHIVE_MESSAGE's words: `>>` the CEO line with its lines, in their order, as one heredoc,
        to the archive by its absolute path, then Edit them out of the file from the last line up. Each step passes
        while the lines stand in the file; once they are out of it, the same `>>` is refused."""
        for archive in self.archives:
            live = archive.with_name(cq_write.NAME)
            with self.subTest(archive=archive):
                command = f"cat >> {archive} <<'EOF'\n{C}\n{L1}\n{L2}\nEOF"
                self.assertIsNone(self.bash(command))
                with archive.open("a", encoding="utf-8") as file:
                    file.write(f"{C}\n{L1}\n{L2}\n")
                for line in (L2, L1, C):
                    self.assertIsNone(self.tool(live, "Edit", {"old_string": line + "\n", "new_string": ""}))
                    live.write_text(live.read_text(encoding="utf-8").replace(line + "\n", "", 1), encoding="utf-8")
                self.assertNotIn(C, live.read_text(encoding="utf-8"))
                self.assertIn(C, archive.read_text(encoding="utf-8"))
                self.assertIn("a line that passes for the CEO's", self.bash(f"echo '{C}' >> {archive}") or "")
                self.assertIn("may join a CEO line", self.bash(f"echo '{L2}' >> {archive}") or "")

    def test_cq_archive_s_normal_run_is_untouched_and_keeps_its_ceo_kind_in_the_file(self):
        """Its command doesn't name the archive, and its own writes aren't the hook's to see; a normal run moves the
        HANDLED line and leaves every line starting CEO, with the lines under it, in the file (its module docstring)."""
        sys.path.insert(0, str(REPO / "scripts"))
        import cq_archive
        live = self.archives[0].with_name("ceo-questions.md")
        live.write_text(LIVE + "HANDLED /2.1 11:30Z: done\n", encoding="utf-8")
        for flags in ("", " --dry-run"):
            command = f"python3 {self.root}/scripts/cq_archive.py {live} --order D-20260101-x/2{flags}"  # the root's
            with self.subTest(command=command):
                self.assertIsNone(self.bash(command))
        with mock.patch("sys.stdout"):
            self.assertEqual(cq_archive.run(live, ("D-20260101-x/2",)), 0)
        text, archived = live.read_text(encoding="utf-8"), self.archives[0].read_text(encoding="utf-8")
        self.assertNotIn("HANDLED /2.1 11:30Z: done", text)
        self.assertIn("HANDLED /2.1 11:30Z: done", archived)
        self.assertIn(f"{C}\n{L1}\n{L2}\n", text)
        for counts in (lambda line: cq_archive.kind(line) == "ceo", cq_write.ceo_line):
            self.assertEqual([line for line in archived.split("\n") if counts(line)], ["CEO RULING /1/1 10:00Z: old."])


class ScriptFiles(unittest.TestCase):
    """An interpreter or shell run on a script file whose text names a live ceo-questions.md is refused, the command
    naming it or not (a refused python3 read isn't redone by a scratch script that opens the file); a checkout's own
    scripts, the named exceptions and every allowed form pass."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(os.path.realpath(self.tmp.name))
        self.root, self.scratch = base / "repo", base / "scratch"
        (self.root / ".git").mkdir(parents=True)
        self.live = self.root / F
        self.live.parent.mkdir(parents=True)
        self.live.write_text("# Order /1\n", encoding="utf-8")
        self.scratch.mkdir()
        opens = f"print(open('{self.live}').read())\n"
        for name, text in {"x.py": opens, "x.js": f"require('fs').readFileSync('{self.live}')\n",
                           "x.ts": f"await Bun.file('{self.live}').text()\n", "x.pl": f"open(F, '<', '{self.live}');\n",
                           "x.rb": f"File.read('{self.live}')\n", "x.sh": f"grep x {self.live}\n",
                           "run.py": "#!/usr/bin/env python3\n" + opens,
                           "joined.py": "import os\nprint(os.path.join(ROOT, 'workspaces', 'x', 'ceo-questions.md'))\n",
                           "plain.py": "print(1)\n", "scratch_only.py": f"open('{base}/s/ceo-questions.md', 'w')\n"}.items():
            (self.scratch / name).write_text(text, encoding="utf-8")
        os.mkfifo(self.scratch / "fifo")
        # a checkout's own code: the repo's scripts (kb_lint.py names the file), a worktree's, a product checkout's
        self.tree = self.root / ".claude" / "worktrees" / "agent-1"
        self.product = self.root / "workspaces" / "acme" / "acme-app"
        for folder in (self.root, self.tree, self.product):
            (folder / "scripts").mkdir(parents=True, exist_ok=True)
            (folder / "scripts" / "kb_lint.py").write_text(opens, encoding="utf-8")
        (self.tree / ".git").write_text("gitdir: x\n")
        (self.product / ".git").mkdir()
        # under the live workspaces/, outside a product checkout: gitignored, not the repo's code
        (self.live.parent / "helper.py").write_text(opens, encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def reason(self, command, cwd=None):
        return cq_write.script_reason(command, str(cwd or self.root), str(self.root))

    def test_a_script_that_names_a_live_one_is_refused(self):
        s = self.scratch
        for command, cwd in [
                (f"python3 {s}/x.py", None), (f"python3 -I -u {s}/x.py --flag", None),
                (f"python3 -W ignore {s}/x.py", None), (f"python3 -X dev -B {s}/x.py", None),
                ("python3 x.py", s), (f"cd {s} && python3 x.py", None), (f"cd {s}; python3 x.py", None),
                (f"cd {s}\npython3 x.py", None), (f"S={s}; python3 $S/x.py", None), (f"python3 -- {s}/x.py", None),
                (f"nohup python3 {s}/x.py > /dev/null 2>&1 &", None), (f"timeout 60 python3 {s}/x.py", None),
                (f"env A=1 python3 {s}/x.py", None), (f"/usr/bin/python3 {s}/x.py", None),
                (f"python3 {s}/joined.py", None), (f"python3 {self.live.parent}/helper.py", None),
                (f"node {s}/x.js", None), (f"node --no-warnings {s}/x.js", None), (f"bun {s}/x.ts", None),
                (f"bun run {s}/x.ts", None), (f"deno run --allow-read {s}/x.ts", None), (f"npx tsx {s}/x.ts", None),
                (f"bunx tsx {s}/x.ts", None), (f"uv run python {s}/x.py", None), (f"uv run {s}/x.py", None),
                (f"perl -w {s}/x.pl", None), (f"ruby {s}/x.rb", None),
                (f"bash {s}/x.sh", None), (f"sh {s}/x.sh", None), (f"bash -euo pipefail {s}/x.sh", None),
                (f"zsh +x {s}/x.sh", None), (f"source {s}/x.sh", None), (f". {s}/x.sh", None),
                (f"{s}/run.py", None), (f"cd {s} && ./run.py", None), (f"{s}/x.sh", None),
                (f"echo \"$(python3 {s}/x.py)\"", None), (f"n=`python3 {s}/x.py`", None),
                (f"bash -c 'python3 {s}/x.py'", None), (f"eval python3 {s}/x.py", None),
                (f"cat <(python3 {s}/x.py)", None), (f"true && python3 {s}/x.py | head -5", None)]:
            with self.subTest(command=command):
                self.assertIn("whose text names a ceo-questions.md", self.reason(command, cwd) or "")

    def test_reads_and_runs_of_other_scripts_pass(self):
        s = self.scratch
        for command, cwd in [
                (f"cat {s}/x.py", None), (f"grep -n open {s}/x.py", None), (f"sed -n 1p {s}/x.py", None),
                (f"head -3 {s}/x.sh; wc -l {s}/x.js", None), (f"cp {s}/x.py {s}/y.py", None), (f"ls {s}", None),
                (f"python3 {s}/plain.py", None), (f"python3 {s}/scratch_only.py", None),  # a scratch copy is free
                (f"python3 -c 'print(1)' {s}/x.py", None), (f"python3 -m unittest discover -s {s}", None),
                (f"python3 - {s}/x.py <<'EOF'\nprint(1)\nEOF", None), (f"perl -ne 'print' {s}/x.pl", None),
                (f"node -e '1' {s}/x.js", None), (f"bash -c 'echo hi' {s}/x.sh", None),
                (f"npx eslint {s}/x.js", None), (f"uvx ruff check {s}/x.py", None), (f"bun test {s}", None),
                (f"python3 {s}/fifo", None),  # not a regular file: never opened
                (f"python3 {self.root}/scripts/kb_lint.py", None), ("python3 scripts/kb_lint.py", None),
                (f"cd {self.root} && python3 scripts/kb_lint.py", self.scratch),
                ("python3 scripts/kb_lint.py", self.tree), (f"python3 {self.tree}/scripts/kb_lint.py", None),
                (f"bun {self.product}/scripts/kb_lint.py", None), (f"{self.root}/scripts/kb_lint.py", None)]:
            with self.subTest(command=command):
                self.assertIsNone(self.reason(command, cwd))

    def test_through_cq_reason_every_allowed_form_passes_and_every_refused_one_is_refused(self):
        """The hook's entry runs both checks: the refused forms are refused, the allowed ones pass,
        and the message says a script, a module or any other program that opens the file is the same form."""
        event = {"tool_name": "Bash", "agent_id": "a1"}
        for command in ALLOWED:
            with self.subTest(command=command):
                self.assertIsNone(cq_write.cq_reason({**event, "tool_input": {"command": command}}, ROOT))
        for command, word in REFUSED.items():
            with self.subTest(command=command):
                self.assertIn(word, cq_write.cq_reason({**event, "tool_input": {"command": command}}, ROOT) or "")
        message = cq_write.cq_reason({**event, "cwd": str(self.root),
                                      "tool_input": {"command": f"python3 {self.scratch}/x.py"}}, str(self.root))
        for words in ("python3 runs a script file whose text names a ceo-questions.md",
                      "read it only with cat, grep or `sed -n`", "Edit tool",
                      # an order's line goes by --add, not `>>`
                      f"a line for an older order goes under that order's heading with `python3 {self.root}/scripts/"
                      f"cq_archive.py {self.root}/workspaces/<product>/content/ceo-questions.md --order <id> --add "
                      "'<the line>'`",
                      # `>>` stays the form for a line that is no order's, a new heading with its first line, and an order's own
                      # file
                      "or a one-shot `>>` (or `tee -a`) of whole lines",
                      f"An order with its own file, {self.root}/workspaces/<product>/content/orders/<directive id>/<n>/"
                      "ceo-questions.md (opened by the CEO), takes each of its lines there by `>>`",
                      "a `>>` adds only a line that is no order's (a LANES line) or a new `## ORDER` heading with its "
                      "first line",
                      # `sed -i` is a whole-file rewrite
                      "so a whole rewrite (`sed -i` is one) can drop their lines",
                      "A script file, a module or any other program that opens the file is the same refused form, "
                      "even where the command doesn't name it", "a refusal is final"):
            self.assertIn(words, message)
        self.assertNotIn("appends with", message)
        self.assertIsNone(cq_write.cq_reason({"tool_name": "Bash", "cwd": str(self.root),  # the main session
                                              "tool_input": {"command": f"python3 {self.scratch}/x.py"}},
                                             str(self.root)))

    def test_an_inner_command_keeps_the_outer_ones_folders_and_variables(self):
        """A `$(...)`, backtick, `<(...)`, `sh -c` or eval
        tries a relative script from the outer command's cd folders, and reads the outer command's variables."""
        s, event = self.scratch, {"tool_name": "Bash", "agent_id": "a1", "cwd": str(self.root)}
        for command in (f"cd {s} && echo \"$(python3 x.py)\"", f"cd {s}; bash -c 'python3 x.py'",
                        f"cd {s}; eval python3 x.py", f"cd {s} && n=`python3 x.py`", f"cd {s}; cat <(python3 x.py)",
                        f"cd {s} && bash -c 'echo \"$(python3 x.py)\"'", f"S={s}; bash -c \"python3 $S/x.py\"",
                        f"S={s}; echo \"$(python3 $S/x.py)\"", f"S={s}; eval python3 '$S/x.py'",
                        # the inner command's own folder too
                        f"cd {s.parent} && cd scratch && bash -c 'echo \"$(python3 x.py)\"'",
                        f"cd {s.parent} && cd scratch && bash -c 'make; python3 x.py'",
                        # an inner command's own cds, followed from its cwd
                        f"echo \"$(cd {s.parent} && cd scratch && python3 x.py)\"",
                        f"make; bash -c 'cd {s.parent} && cd scratch && python3 x.py'",
                        f"make; bash -c 'cd {s.parent} && cd scratch && bash -c \"python3 x.py\"'",
                        # its own text, not the outer's `${`, sets how its cds move
                        f"echo ${{X}}; echo \"$(cd {s.parent} && cd scratch && python3 x.py)\"",
                        f"echo ${{X}}; bash -c 'cd {s.parent} && cd scratch && python3 x.py'"):
            with self.subTest(command=command):
                message = cq_write.cq_reason({**event, "tool_input": {"command": command}}, str(self.root))
                self.assertIn("python3 runs a script file whose text names a ceo-questions.md", message or "")
        home = s.parent / "home"  # nor does the outer's HOME skip its `~` script
        (home / "s").mkdir(parents=True)
        (home / "s" / "x.py").write_text((s / "x.py").read_text(encoding="utf-8"), encoding="utf-8")
        with mock.patch.dict(os.environ, {"HOME": str(home)}):
            command = "HOME=$HOME bash -c 'python3 ~/s/x.py'"
            message = cq_write.cq_reason({**event, "tool_input": {"command": command}}, str(self.root))
            self.assertIn("python3 runs a script file whose text names a ceo-questions.md", message or "")
        for command in (f"cd {s} && echo \"$(python3 plain.py)\"", f"cd {s}; bash -c 'cat x.py'",
                        f"cd {s}; eval grep -n open x.py", f"S={s}; bash -c \"python3 $S/plain.py\"",
                        f"cd {self.root} && bash -c 'python3 scripts/kb_lint.py'",
                        f"cd {s}; echo \"$(python3 {self.root}/scripts/kb_lint.py)\""):
            with self.subTest(command=command):
                self.assertIsNone(cq_write.cq_reason({**event, "tool_input": {"command": command}}, str(self.root)))

    def test_an_exception_form_inside_an_inner_command_is_refused(self):
        """An exception passes only as a command of its own; inside a `$(...)`, `<(...)`, `sh -c` or eval it stays
        refused. It shows where the root is no git checkout, so its scripts are no checkout's own."""
        root = self.scratch.parent / "bare"
        script, live = root / "scripts" / "cq_archive.py", root / F
        script.parent.mkdir(parents=True)
        script.write_text(f"# moves the handled lines of {F}\n", encoding="utf-8")
        live.parent.mkdir(parents=True)
        live.write_text("# Order /1\n", encoding="utf-8")
        event = {"tool_name": "Bash", "agent_id": "a1", "cwd": str(root)}
        for command in (f"D=/tmp; bash -c 'python3 {script} $D/x --order /1'", f"bash -c 'python3 {script} /tmp/d'",
                        f"echo \"$(python3 {script} /tmp/d)\"", f"eval python3 {script} /tmp/d",
                        f"cat <(python3 {script} /tmp/d)"):
            with self.subTest(command=command):
                message = cq_write.cq_reason({**event, "tool_input": {"command": command}}, str(root))
                self.assertIn("python3 runs a script file whose text names a ceo-questions.md", message or "")
        for command in (f"python3 {script} {live} --order /1", f"python3 {script} /tmp/d",
                        f"nohup python3 {script} {live} --order /1 --dry-run >/dev/null 2>&1 &"):
            with self.subTest(command=command):
                self.assertIsNone(cq_write.cq_reason({**event, "tool_input": {"command": command}}, str(root)))

    def test_a_scripts_text_is_read_without_the_commands_variables(self):
        """A script sets its own variables, so the command's `D=/tmp` doesn't
        make the script's `$D/ceo-questions.md` a scratch path, at the top or in an inner command."""
        text = f"D={self.live.parent}\nprintf 'x\\n' >> \"$D/{cq_write.NAME}\"\n"
        (self.scratch / "v.sh").write_text(text, encoding="utf-8")
        event = {"tool_name": "Bash", "agent_id": "a1", "cwd": str(self.root)}
        for command in (f"D=/tmp; bash {self.scratch}/v.sh", f"D=/tmp; bash -c 'bash {self.scratch}/v.sh'",
                        f"D=/tmp; echo \"$(bash {self.scratch}/v.sh)\""):
            with self.subTest(command=command):
                message = cq_write.cq_reason({**event, "tool_input": {"command": command}}, str(self.root))
                self.assertIn("bash runs a script file whose text names a ceo-questions.md", message or "")

    def test_an_inner_command_learns_its_names_without_the_outer_values_too(self):
        """A name a read without the outer values makes may-be-live is a name for the script's text."""
        (self.scratch / "w.sh").write_text("printf 'x\\n' >> \"$F\"\n", encoding="utf-8")
        event = {"tool_name": "Bash", "agent_id": "a1", "cwd": str(self.root)}
        for command in (f"S=/tmp; echo \"$(F=$S/{cq_write.NAME}; export F; bash {self.scratch}/w.sh)\"",
                        f"S=/tmp; bash -c 'F=$S/{cq_write.NAME}; export F; bash {self.scratch}/w.sh'"):
            with self.subTest(command=command):
                message = cq_write.cq_reason({**event, "tool_input": {"command": command}}, str(self.root))
                self.assertIn("bash runs a script file whose text names a ceo-questions.md", message or "")
        # those names are the reader's only: a deeper here-string reads by itself
        command = f"S=/tmp; echo \"$(F=$S/{cq_write.NAME}; echo \"$(python3 <<< \"$F\" {self.scratch}/x.py)\")\""
        message = cq_write.cq_reason({**event, "tool_input": {"command": command}}, str(self.root))
        self.assertIn("python3 runs a script file whose text names a ceo-questions.md", message or "")

    def test_many_cds_at_each_level_are_read_fast(self):
        """An inner command is handed a bounded list of folders, so a
        command with many cds at three levels takes time in its length, not in a product of its cds."""
        cds = "".join(f"cd d{i}; " for i in range(1000))
        command = f"{cds}bash -c '{cds}echo \"$({cds}python3 x.py)\"'"
        start = time.monotonic()
        self.assertIsNone(self.reason(command))
        self.assertLess(time.monotonic() - start, 5)

    def test_a_lookalike_deploy_script_is_told_the_form(self):
        """A file of the deploy script's name outside a product checkout whose
        text names the file, run by bun from a command that doesn't name it, gets DEPLOY_HINT."""
        hint = cq_write.DEPLOY_HINT.format(name="deploy.ts")
        lookalike = self.scratch / "scripts" / "deploy.ts"
        lookalike.parent.mkdir()
        named(self.root)
        lookalike.write_text(f"await Bun.file('{self.live}').text()\n", encoding="utf-8")
        event = {"tool_name": "Bash", "agent_id": "a1", "cwd": str(self.root)}
        for command in (f"cd {self.scratch} && bun scripts/deploy.ts --dry-run", f"bun {lookalike}"):
            with self.subTest(command=command):
                message = cq_write.cq_reason({**event, "tool_input": {"command": command}}, str(self.root))
                self.assertIn("bun runs a script file whose text names a ceo-questions.md", message or "")
                self.assertIn(hint, message or "")
        plain = cq_write.cq_reason({**event, "tool_input": {"command": f"bun {self.scratch}/x.ts"}}, str(self.root))
        self.assertNotIn(hint, plain or "")
        self.assertIn("whose text names a ceo-questions.md", plain or "")

    def test_an_unnamed_command_still_read_after_the_timer_passes(self):
        event = {"tool_name": "Bash", "agent_id": "a1", "tool_input": {"command": "for x in " * 4000}}
        with mock.patch.object(cq_write, "SECONDS", 1):
            start = time.monotonic()
            self.assertIsNone(cq_write.cq_reason(event, ROOT))
        self.assertLess(time.monotonic() - start, 5)
        self.assertEqual(signal.getitimer(signal.ITIMER_REAL), (0.0, 0.0))

    def test_a_long_command_is_read_fast(self):
        for command in (f"python3 {self.scratch}/plain.py '" + "x" * 255_000 + "'",
                        f"cat > {self.scratch}/big.md <<'EOF'\n" + "a line of text\n" * 15_000 + "EOF"):
            with self.subTest(command=command[:40]):
                start = time.monotonic()
                self.assertIsNone(self.reason(command))
                self.assertLess(time.monotonic() - start, 5)


def named(root, text=None):
    """root's company.json, which names the deploy script (or holds text)."""
    settings = {"products": {}, "integrations": {"question_files": {"deploy_script": "deploy.ts"}}}
    (root / "company.json").write_text(json.dumps(settings) if text is None else text, encoding="utf-8")


class DeployScript(unittest.TestCase):
    """The bun exception holds only for a product checkout's own deploy script, the file name company.json gives, run as
    `cd <checkout> && bun scripts/<deploy script> --x <sha> --ceo-questions <the live file>`."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(os.path.realpath(self.tmp.name))
        self.root = base / "repo"
        self.checkout = self.root / "workspaces" / "acme" / ".worktrees" / "cto-deploy"
        self.elsewhere = base / "tmp"  # a lookalike outside workspaces/
        self.loose = self.root / "workspaces" / "acme" / "loose"  # under workspaces/, no .git
        for folder in (self.checkout, self.elsewhere, self.loose):
            (folder / "scripts").mkdir(parents=True)
            (folder / "scripts" / "deploy.ts").write_text("// deploy\n")
        for folder in (self.checkout, self.elsewhere):
            (folder / ".git").write_text("gitdir: x\n")
        named(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def reason(self, command, cwd=None):
        return cq_write.command_reason(command, str(cwd or self.root), str(self.root))

    def test_a_deploy_script_company_json_doesnt_name_is_refused(self):
        command = f"bun {self.checkout}/scripts/deploy.ts --x abc --ceo-questions {self.root / F}"
        self.assertIsNone(self.reason(command))
        for text in ("{", "[]", '{"products": {}, "integrations": {}}', '{"products": {}, "integrations": []}',
                     '{"products": {}, "integrations": {"question_files": {}}}',
                     '{"products": {}, "integrations": {"question_files": []}}',
                     '{"products": {}, "integrations": {"question_files": {"deploy_script": ["deploy.ts"]}}}',
                     '{"products": {}, "integrations": {"question_files": {"deploy_script": "other.ts"}}}',
                     '{"products": {}, "integrations": {"question_files": {"deploy_script": "../deploy.ts"}}}'):
            with self.subTest(text=text):
                named(self.root, text)
                self.assertIn("bun", self.reason(command) or "")
        (self.root / "company.json").unlink()
        self.assertIn("bun", self.reason(command) or "")

    def test_the_documented_command_passes(self):
        live = self.root / F
        for command, cwd in [
                (f"cd {self.checkout} && bun scripts/deploy.ts --x abc --ceo-questions {live}", None),
                (f"cd {self.checkout} && ACME_DEPLOY_ORDER=D-1/2 bun scripts/deploy.ts --x abc "
                 f"--ceo-questions {live} > /tmp/d.log 2>&1; echo $? > /tmp/d.rc", None),
                (f"bun scripts/deploy.ts --dry-run --ceo-questions={F}", self.checkout),
                (f"bun {self.checkout}/scripts/deploy.ts --x abc --ceo-questions {F}", None),
                (f"cd {self.checkout.parent} && cd cto-deploy && bun scripts/deploy.ts --ceo-questions {F}",
                 None),
                # a `$(...)` that doesn't name the file (an rc file's) is no hidden path
                (f"bun scripts/deploy.ts --x abc --ceo-questions {live} > /tmp/d.log 2>&1; "
                 f"echo $? > /tmp/d-$(date +%s).rc", self.checkout)]:
            with self.subTest(command=command):
                self.assertIsNone(self.reason(command, cwd))

    def test_the_documented_command_passes_the_hooks_entry(self):
        """It passes cq_reason too, its script naming the file (the checkout's own code, which script_reason doesn't
        read); so does it nested (command_reason follows it)."""
        (self.checkout / "scripts" / "deploy.ts").write_text(f"// --ceo-questions: {F}\n")
        event, live = {"tool_name": "Bash", "agent_id": "a1", "cwd": str(self.root)}, self.root / F
        documented = f"cd {self.checkout} && bun scripts/deploy.ts --x abc --ceo-questions {live}"
        for command in (documented, f"bun {self.checkout}/scripts/deploy.ts --x abc --ceo-questions {F}",
                        f"bash -c '{documented}'"):
            with self.subTest(command=command):
                self.assertIsNone(cq_write.cq_reason({**event, "tool_input": {"command": command}}, str(self.root)))

    def test_a_lookalike_script_is_refused(self):
        for command, cwd in [
                (f"bun {self.elsewhere}/scripts/deploy.ts --ceo-questions {F}", None),
                (f"cd {self.elsewhere} && bun scripts/deploy.ts --ceo-questions {F}", None),
                (f"bun scripts/deploy.ts --ceo-questions {F}", self.elsewhere),
                (f"cd {self.checkout} && cd {self.elsewhere} && bun scripts/deploy.ts --ceo-questions {F}",
                 None),
                (f"bun {self.loose}/scripts/deploy.ts --ceo-questions {F}", None),
                (f"bun scripts/deploy.ts --ceo-questions {F}", None),  # root has no such script
                (f"cd $D && bun scripts/deploy.ts --ceo-questions {F}", self.checkout),
                (f"cd {self.checkout} && cd - && bun scripts/deploy.ts --ceo-questions {F}", None),
                (f"cd {self.checkout} && popd && bun scripts/deploy.ts --ceo-questions {F}", None),
                # the named exception only in its own form
                (f"bun scripts/deploy.ts --x abc {F}", self.checkout),
                (f"bun scripts/deploy.ts --lock {F}", self.checkout)]:
            with self.subTest(command=command):
                self.assertIn("bun", self.reason(command, cwd) or "")

    def test_a_cd_that_moves_nothing_after_it_and_a_link_are_refused(self):
        """A `cd` in a subshell, a pipeline or the background leaves bun
        in the lookalike's folder, and a link to the real script is another name for it."""
        (self.checkout / "scripts" / "lnk.ts").symlink_to(self.checkout / "scripts" / "deploy.ts")
        (self.elsewhere / "link").symlink_to(self.checkout / "scripts")
        run = f"bun scripts/deploy.ts --ceo-questions {F}"
        for command, cwd in [
                (f"(cd {self.checkout}); {run}", self.elsewhere),
                (f"(cd {self.checkout} && true); {run}", self.elsewhere),
                (f"cd {self.checkout} | true; {run}", self.elsewhere),
                (f"true | cd {self.checkout}; {run}", self.elsewhere),
                (f"cd {self.checkout} & {run}", self.elsewhere),
                (f"echo $(cd {self.checkout}); {run}", self.elsewhere),
                (f"case a in a) true;; esac; (cd {self.checkout}); {run}", self.elsewhere),
                (f'cd {self.elsewhere} && bash -c "{run}"', self.checkout),
                (f"bun scripts/lnk.ts --ceo-questions {F}", self.checkout),
                (f"bun {self.elsewhere}/link/deploy.ts --ceo-questions {F}", None)]:
            with self.subTest(command=command):
                self.assertIn("bun", self.reason(command, cwd) or "")
        self.assertIsNone(self.reason(f'cd {self.checkout} && bash -c "{run}"', self.elsewhere))

    def test_a_cd_that_may_not_run_or_move_leaves_the_lookalike_refused(self):
        """From a cwd that holds a lookalike, each cd below may leave
        bun there, so the relative path is refused; and a link's `..` is read as the shell's logical cd reads it."""
        (self.elsewhere / "L").symlink_to(self.checkout / "scripts")
        run = f"bun scripts/deploy.ts --x abc --ceo-questions {self.root / F}"
        for command in [
                f"false && cd {self.checkout}; {run}",
                f"if false; then cd {self.checkout}; fi; {run}",
                f"cd {self.checkout} && true & {run}",  # `&` sends the whole and-or list to the background
                f"(case a in a) true;; esac; cd {self.checkout}); {run}",
                f"cd L/.. && {run}",  # the shell stays in the cwd; the real folder of L/.. is the checkout
                f"cd {self.elsewhere}/L/.. && {run}",
                f"cd {self.checkout} || true; {run}",
                f"true || cd {self.checkout}; {run}",
                f"cd {self.checkout} && cd /nowhere; {run}",
                f"cd {self.checkout} | cat && {run}",
                f"trap 'cd {self.elsewhere}' DEBUG; cd {self.checkout} && {run}",
                f"alias cd=true; cd {self.checkout} && {run}",
                f"pushd {self.elsewhere}; cd {self.checkout}; popd; {run}",
                f"x=$(cd {self.checkout}) && {run}",
                f"cd ~ && cd {self.checkout.relative_to(self.checkout.anchor)} && {run}",
                f"eval cd {self.checkout}; {run}",
                f"while false; do cd {self.checkout}; done; {run}",
                # chdir, a trap that runs later, a variable the shell doesn't have, a cd that may fail before a `;` or a
                # newline, and a value changed after it was set (no variable counts in the cd or the script's path)
                f"D={self.checkout}; cd $D && {run}",
                f"D={self.checkout}; : ${{D::={self.elsewhere}}}; cd $D && {run}",
                f"D={self.checkout}; echo $[D=5]; cd $D && {run}",
                f"D={self.checkout}; bun $D/scripts/deploy.ts --x abc --ceo-questions {self.root / F}",
                f"chdir {self.checkout} && {run}",
                f"chdir {self.checkout}; {run}",
                f"cd {self.checkout} && trap \"{run}\" EXIT; cd {self.elsewhere}",
                f"D={self.checkout} true; cd \"$D\" && {run}",
                f"false && D={self.checkout}; cd \"$D\" && {run}",
                f"D={self.checkout}; sh -c 'cd $D && {run}'",
                f"cd {self.checkout}; {run}",
                f"cd {self.checkout}\n{run}",
                f"bun -e 1; cd {self.checkout}; {run}",
                f"cd {self.checkout} && true; {run}",
                f"true & pushd {self.checkout} && {run}"]:
            with self.subTest(command=command):
                self.assertIn("bun", self.reason(command, self.elsewhere) or "")
        self.assertIn("passes only in the form", self.reason(f"false && cd {self.checkout}; {run}", self.elsewhere))
        # `~` is the shell's HOME, which the command may have changed: not read from the hook's
        with mock.patch.dict(os.environ, {"HOME": str(self.checkout.parent)}):
            self.assertIn("bun", self.reason(f"bun ~/cto-deploy/scripts/deploy.ts --ceo-questions "
                                             f"{self.root / F}", self.elsewhere) or "")
        # A relative cd where CDPATH may send it: bash tries CDPATH's folders first.
        self.assertIsNone(self.reason(f"cd cto-deploy && {run}", self.checkout.parent))
        self.assertIn("bun", self.reason(f"CDPATH={self.elsewhere} cd cto-deploy && {run}", self.checkout.parent) or "")
        # an empty heredoc, from the same folder
        self.assertIn("an empty heredoc", self.reason(f"cat <<EOF\nEOF\nsed -i '' s/a/b/ {self.root / F}\nEOF",
                                                      self.elsewhere))

    def test_the_path_as_written_must_be_scripts_deploy_ts(self):
        (self.checkout / "scripts" / "sub").mkdir()
        scripts = self.checkout / "scripts"
        for command, cwd in [(f"bun deploy.ts --ceo-questions {F}", scripts),
                             (f"bun ./deploy.ts --ceo-questions {F}", scripts),
                             (f"bun ../deploy.ts --ceo-questions {F}", scripts / "sub"),
                             (f"D={scripts}; bun $D/deploy.ts --ceo-questions {F}", None),
                             (f"cd {scripts} && bun deploy.ts --ceo-questions {F}", None)]:
            with self.subTest(command=command):
                self.assertIn("bun", self.reason(command, cwd) or "")

    def test_the_documented_forms_still_pass(self):
        live = self.root / F
        run = f"bun scripts/deploy.ts --x abc --ceo-questions {live}"
        for command, cwd in [
                (f"cd {self.checkout} && {run} > /tmp/d.log 2>&1; echo $? > /tmp/d.rc", None),
                (f"cd {self.checkout} && nohup {run} > /tmp/d.log 2>&1 &", None),
                (f"cd {self.checkout} && {run} 2>&1 | tee /tmp/d.log", None),
                (f"{run} 2>&1 | tee /tmp/d.log", self.checkout),
                (f"cd {self.checkout} &&\n  {run}", None),
                (f"cd {self.checkout} \\\n  && {run}", None),
                (f"cd {self.checkout} && sh -c '{run}'", None),
                (f"cd {self.checkout}/scripts/.. && {run}", None),
                (f"mkdir -p /tmp/d && cd {self.checkout} && git status --short && {run}", None),
                (f"cd {self.elsewhere}; cd {self.checkout} && {run}", None),
                (f"cd {self.checkout} && bun scripts/deploy.ts --dry-run --ceo-questions={F}", None)]:
            with self.subTest(command=command):
                self.assertIsNone(self.reason(command, cwd))


class Wiring(unittest.TestCase):
    """End to end: the Bash check through guard_marketing_tools.py, the Write check through guard_kb_write.py."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.cq = self.root / "workspaces" / "demo" / "content" / "ceo-questions.md"
        self.cq.parent.mkdir(parents=True)
        self.cq.write_text("# Order /1\n", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def run_hook(self, hook, tool_name, tool_input, agent_type=None, agent_id=None):
        payload = {"session_id": "test", "cwd": str(self.root), "hook_event_name": "PreToolUse",
                   "tool_name": tool_name, "tool_input": tool_input}
        if agent_type:
            payload["agent_type"] = agent_type
        if agent_id:
            payload["agent_id"] = agent_id
        return subprocess.run([sys.executable, str(HOOKS / hook)], input=json.dumps(payload), capture_output=True,
                              text=True, env=dict(os.environ, CLAUDE_PROJECT_DIR=str(self.root)), timeout=30)

    def bash(self, command, agent_type="cto", agent_id="a1b2c3d4"):
        return self.run_hook("guard_marketing_tools.py", "Bash", {"command": command}, agent_type, agent_id)

    def write(self, path, tool_name="Write", agent_type="cto", agent_id="a1b2c3d4"):
        tool_input = {"file_path": str(path), "content": "x\n"}
        if tool_name == "Edit":
            tool_input = {"file_path": str(path), "old_string": "# Order /1", "new_string": "# Order /1\nx"}
        if tool_name == "MultiEdit":
            tool_input = {"file_path": str(path), "edits": [{"old_string": "a", "new_string": "b"}]}
        return self.run_hook("guard_kb_write.py", tool_name, tool_input, agent_type, agent_id)

    def test_a_subagents_rewrite_by_bash_is_refused_with_edit_and_append_named(self):
        for agent_type in ("cto", "staff-engineer", "senior-engineer", "platform-engineer", "cmo"):
            with self.subTest(agent_type=agent_type):
                result = self.bash(f"sed -i '' 's/a/b/' {self.cq}", agent_type)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn("Edit tool", result.stderr)
                self.assertIn("`>>`", result.stderr)
                self.assertIn("cq_archive.py", result.stderr)

    def test_a_failing_write_check_fails_closed(self):
        # guard_kb_write.py holds the file by its own except, whatever onFailure says: a copy of the hook with a cq_write.py whose write_reason raises.
        hooks = self.root / "scripts" / "hooks"
        hooks.mkdir(parents=True)
        (hooks / "guard_kb_write.py").write_text((HOOKS / "guard_kb_write.py").read_text(encoding="utf-8"))
        (self.root / "scripts" / "kb_secrets.py").write_text((REPO / "scripts" / "kb_secrets.py").read_text(encoding="utf-8"))
        (hooks / "cq_write.py").write_text("def write_reason(*args):\n    raise RuntimeError('stub')\n")
        payload = {"session_id": "test", "cwd": str(self.root), "hook_event_name": "PreToolUse", "tool_name": "Write",
                   "tool_input": {"file_path": str(self.cq), "content": "x\n"}, "agent_type": "cto", "agent_id": "a1"}
        result = subprocess.run([sys.executable, str(hooks / "guard_kb_write.py")], input=json.dumps(payload),
                                capture_output=True, text=True, env=dict(os.environ, CLAUDE_PROJECT_DIR=str(self.root)),
                                timeout=30)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("check failed (RuntimeError)", result.stderr)

    def test_a_cq_write_that_fails_to_import_holds_a_subagents_archive_write_and_not_the_main_sessions(self):
        """guard_kb_write.py reads agent_id before it imports cq_write for an archive, so the main session still writes
        one; a subagent's write fails closed, and so does any session's write of the file beside it."""
        hooks = self.root / "scripts" / "hooks"
        hooks.mkdir(parents=True)
        (hooks / "guard_kb_write.py").write_text((HOOKS / "guard_kb_write.py").read_text(encoding="utf-8"))
        (self.root / "scripts" / "kb_secrets.py").write_text((REPO / "scripts" / "kb_secrets.py").read_text(encoding="utf-8"))
        (hooks / "cq_write.py").write_text("raise ImportError('stub')\n")
        archive = self.cq.with_name("ceo-questions-archive.md")
        archive.write_text("# ceo-questions, archive\nHANDLED x\n", encoding="utf-8")

        def run(path, agent_id):
            payload = {"session_id": "test", "cwd": str(self.root), "hook_event_name": "PreToolUse",
                       "tool_name": "Edit", "tool_input": {"file_path": str(path), "old_string": "x",
                                                           "new_string": "CEO RULING /1/2: yes."}}
            if agent_id:
                payload.update(agent_type="cto", agent_id=agent_id)
            return subprocess.run([sys.executable, str(hooks / "guard_kb_write.py")], input=json.dumps(payload),
                                  capture_output=True, text=True,
                                  env=dict(os.environ, CLAUDE_PROJECT_DIR=str(self.root)), timeout=30)
        result = run(archive, None)
        self.assertEqual(result.returncode, 0, result.stderr)  # the main session
        for path, agent_id in ((archive, "a1"), (self.cq, "a1"), (self.cq, None)):
            with self.subTest(path=path.name, agent_id=agent_id):
                result = run(path, agent_id)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn("check failed (ImportError)", result.stderr)

    def test_a_scratch_copy_moved_back_into_content_is_refused(self):
        result = self.bash(f"mv /tmp/s/ceo-questions.md {self.cq.parent}/")
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("mv puts a ceo-questions.md into a folder", result.stderr)

    def test_a_subagents_append_passes(self):
        self.assertEqual(self.bash(f"echo 'NEEDS-CEO-NOW x' >> {self.cq}").returncode, 0)
        self.assertEqual(self.bash(f"python3 scripts/cq_archive.py {self.cq} --order /1").returncode, 0)

    def test_a_subagents_scratch_script_that_opens_it_is_refused(self):
        """The command doesn't name the file; the script it runs does."""
        scratch = self.root / "scratch"  # self.root has no .git: no checkout's code
        scratch.mkdir()
        (scratch / "read.py").write_text(f"print(open('{self.cq}').read())\n", encoding="utf-8")
        (scratch / "other.py").write_text("print(1)\n", encoding="utf-8")
        result = self.bash(f"python3 {scratch}/read.py")
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("python3 runs a script file whose text names a ceo-questions.md", result.stderr)
        self.assertIn("A script file, a module or any other program that opens the file is the same refused form",
                      result.stderr)
        self.assertEqual(self.bash(f"python3 {scratch}/other.py").returncode, 0)
        self.assertEqual(self.bash(f"cat {scratch}/read.py").returncode, 0)
        self.assertEqual(self.bash(f"python3 {scratch}/read.py", "ceo", None).returncode, 0)  # the main session

    def test_cq_archive_from_a_worktrees_cwd_passes_only_by_its_absolute_path(self):
        """As Claude Code runs the hook: the project dir is the main checkout, the agent's cwd a worktree of this repo with its own scripts/cq_archive.py."""
        tree = self.root / ".claude" / "worktrees" / "agent-1"
        for folder in (self.root, tree):
            (folder / "scripts").mkdir(parents=True)
            (folder / "scripts" / "cq_archive.py").write_text("", encoding="utf-8")
        payload = {"session_id": "test", "cwd": str(tree), "hook_event_name": "PreToolUse", "tool_name": "Bash",
                   "agent_type": "staff-engineer", "agent_id": "a1"}

        def run(command):
            return subprocess.run([sys.executable, str(HOOKS / "guard_marketing_tools.py")],
                                  input=json.dumps(dict(payload, tool_input={"command": command})), capture_output=True,
                                  text=True, env=dict(os.environ, CLAUDE_PROJECT_DIR=str(self.root)), timeout=30)

        refused = run(f"cd {self.root} && python3 scripts/cq_archive.py {self.cq} --order /1 --dry-run")
        self.assertEqual(refused.returncode, 2, refused.stderr)
        self.assertIn("python3 runs with a ceo-questions.md", refused.stderr)
        allowed = run(f"python3 {self.root}/scripts/cq_archive.py {self.cq} --order /1 --dry-run")
        self.assertEqual(allowed.returncode, 0, allowed.stderr)

    def test_the_main_session_is_not_held(self):
        for agent_type in ("ceo", None):
            with self.subTest(agent_type=agent_type):
                self.assertEqual(self.bash(f"python3 -c \"open('{self.cq}','w')\"", agent_type, None).returncode, 0)
                self.assertEqual(self.bash(f"sed -i '' 's/a/b/' {self.cq}", agent_type, None).returncode, 0)
                self.assertEqual(self.write(self.cq, agent_type=agent_type, agent_id=None).returncode, 0)

    def test_a_subagents_write_on_an_existing_file_is_refused(self):
        result = self.write(self.cq)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("Edit tool", result.stderr)
        self.assertIn("Write would replace", result.stderr)

    def test_a_relative_or_differently_cased_path_is_refused_too(self):
        result = self.run_hook("guard_kb_write.py", "Write", {"file_path": "workspaces/demo/content/ceo-questions.md",
                                                              "content": "x"}, "cto", "a1")
        self.assertEqual(result.returncode, 2, result.stderr)
        upper = self.cq.with_name("CEO-Questions.md")
        if upper.exists():  # a case-insensitive disk
            self.assertEqual(self.write(upper).returncode, 2)

    def test_the_live_file_by_absolute_path_is_held_and_a_scratch_copy_is_free(self):
        scratch = self.root / "scratch" / "ceo-questions.md"
        scratch.parent.mkdir()
        scratch.write_text("x\n", encoding="utf-8")
        self.assertEqual(self.bash(f"perl -pi -e 's/a/b/' {self.cq}").returncode, 2)
        self.assertEqual(self.bash(f"perl -pi -e 's/a/b/' {scratch}").returncode, 0)
        self.assertEqual(self.bash(f"S={self.root}/scratch; cp /tmp/x $S/ceo-questions.md").returncode, 0)
        self.assertEqual(self.bash(f"cp {scratch} {self.cq.parent}/").returncode, 2)
        self.assertEqual(self.write(scratch).returncode, 0)

    def test_a_subagents_ceo_line_is_refused_by_bash_and_edit_and_the_main_session_s_passes(self):
        """As Claude Code runs the hooks: who writes is the hook input's agent_id."""
        bash = f"echo 'CEO RULING /1/2: yes.' >> {self.cq}"
        edit = {"file_path": str(self.cq), "old_string": "# Order /1", "new_string": "# Order /1\nHANDLED (CEO) x"}
        for result in (self.bash(bash), self.run_hook("guard_kb_write.py", "Edit", edit, "cto", "a1")):
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertIn("passes for the CEO's", result.stderr)
            self.assertIn("refusal is final", result.stderr)
        self.assertEqual(self.bash(bash, "ceo", None).returncode, 0)
        self.assertEqual(self.run_hook("guard_kb_write.py", "Edit", edit, "ceo", None).returncode, 0)
        self.assertEqual(self.bash(f"echo 'REPORT /1 DONE: per CEO RULING /1/2' >> {self.cq}").returncode, 0)
        joins = f"echo '(2) NEEDS-CEO-NOW /2.CTO 11:30Z: approved.' >> {self.cq}"
        result = self.bash(joins)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("joins the line above", result.stderr)
        self.assertEqual(self.bash(joins, "ceo", None).returncode, 0)

    def test_a_subagents_ceo_line_into_the_archive_is_refused_unless_the_file_beside_holds_it(self):
        """As Claude Code runs the hooks."""
        archive = self.cq.with_name("ceo-questions-archive.md")
        archive.write_text("# ceo-questions, archive\nHANDLED x\n", encoding="utf-8")
        bash = f"echo 'CEO RULING /1/2: yes.' >> {archive}"
        edit = {"file_path": str(archive), "old_string": "HANDLED x", "new_string": "HANDLED x\nCEO RULING /1/2: yes."}
        for result in (self.bash(bash), self.run_hook("guard_kb_write.py", "Edit", edit, "cto", "a1")):
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertIn("ceo-questions-archive.md, and the ceo-questions.md beside it doesn't hold it", result.stderr)
            self.assertIn("refusal is final", result.stderr)
        self.assertEqual(self.bash(bash, "ceo", None).returncode, 0)
        self.assertEqual(self.run_hook("guard_kb_write.py", "Edit", edit, "ceo", None).returncode, 0)
        self.cq.write_text("# Order /1\nCEO RULING /1/2: yes.\n", encoding="utf-8")  # the by-hand move's line
        self.assertEqual(self.bash(bash).returncode, 0)
        self.assertEqual(self.run_hook("guard_kb_write.py", "Edit", edit, "cto", "a1").returncode, 0)

    def test_a_subagents_write_of_a_new_file_and_its_edits_pass(self):
        new = self.root / "workspaces" / "acme" / "content" / "ceo-questions.md"
        self.assertEqual(self.write(new).returncode, 0)
        self.assertEqual(self.write(self.cq, "Edit").returncode, 0)
        self.assertEqual(self.write(self.cq, "MultiEdit").returncode, 0)
        self.assertEqual(self.write(self.cq.with_name("ceo-questions-archive.md")).returncode, 0)


if __name__ == "__main__":
    unittest.main()
