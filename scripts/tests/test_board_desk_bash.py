"""Tests for scripts/hooks/board_desk_bash.py: an agent's Bash never writes knowledge/board/answers/ or runs
board_desk.py's writing commands. Through guard_marketing_tools.py in
test_guard_marketing_tools.py's BoardDesk class."""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "hooks"))

import board_desk_bash as desk  # noqa: E402

PAGE = "knowledge/board/answers/2026-W02.md"
CWD = "/repo"  # the hook's cwd: the event's, else the project's


def reason(command, cwd=CWD, ceo=False):
    return desk.desk_reason(command, cwd, ceo)


class Answers(unittest.TestCase):
    def assertRefused(self, command, why=""):
        found = reason(command)
        self.assertIsNotNone(found, command)
        self.assertIn("the Board's own answers", found)
        self.assertIn(why, found)

    def test_reads_and_git_pass(self):
        for command in (f"cat {PAGE}", f"grep -n 'R-1' {PAGE} 2>/dev/null | head -5", "ls knowledge/board/answers/",
                        f"git add {PAGE} && git commit -m 'kb: the answers' && git push",
                        f"git -C /repo diff -- {PAGE}", "cd knowledge/board/answers && ls -la && wc -l *.md",
                        f"grep -c x {PAGE} >&2; echo done", "find knowledge/board/answers -name '*.md'",
                        f"head -3 {PAGE} 2>&1 | tail -1", "ls knowledge/board && cd answers; pwd"):
            with self.subTest(command=command):
                self.assertIsNone(reason(command))

    def test_writes_there_are_refused(self):
        cases = {f"echo '| R-1 | A-1 | Yes |' >> {PAGE}": "an output redirection",
                 f"printf x > {PAGE}": "an output redirection", f"tee -a {PAGE} < x": "`tee` isn't a read",
                 f"cp /tmp/x {PAGE}": "`cp` isn't a read", f"sed -i '' s/Yes/No/ {PAGE}": "`sed` with an option",
                 f"rm -f {PAGE}": "`rm` isn't a read", f"python3 -c \"open('{PAGE}','a').write('x')\"": "`python3`",
                 f"bash -c 'echo x > {PAGE}'": "`bash` isn't a read", "cd knowledge/board; rm -rf answers": "`rm`",
                 "cd knowledge/board && echo x > answers/2026-W02.md": "an output redirection",
                 f"cat {PAGE} > /tmp/copy": "an output redirection", f"ls {PAGE} | xargs rm": "`xargs`",
                 f"find knowledge/board/answers -name '*.md' -delete": "find with an action",
                 f"git checkout -- {PAGE}": "`git checkout`", f"git diff --output={PAGE}": "`git diff`",
                 f"cat $(rm {PAGE})": "`$(` hides", f"cat `rm {PAGE}`": "hides", f"diff <(rm {PAGE}) x": "hides",
                 f"python3 - <<'EOF'\nopen('{PAGE}', 'w')\nEOF": "`python3`", f"X=1 {PAGE}": "isn't a read",
                 f"> {PAGE}": "a bare redirection", f"echo 'x > {PAGE}": "can't split",
                 f"cat {PAGE}\nrm {PAGE}": "`rm`", f"cat {PAGE} \\\n; rm x": "`rm`",
                 f"cat <<< x\nrm {PAGE}": "`rm`", f"cat Knowledge/Board/Answers/2026-W02.md | sh": "`sh`",
                 "cd /repo/knowledge && cd board/../board && touch answers/x.md": "`touch`",
                 "rm -f /repo/knowledge/board/answers/2026-W02.md": "`rm`",
                 "git -C /repo checkout -- knowledge/board/answers": "`git checkout`"}
        for command, why in cases.items():
            with self.subTest(command=command):
                self.assertRefused(command, why)

    def test_other_answers_and_plain_words_pass(self):
        for command in ("python3 scripts/second_opinion.py --out workspaces/x/content/sa003-answers/a.txt",
                        "echo 'the Board answers in Notion' > /tmp/x", "python3 scripts/capacity_scan.py",
                        "cat > /tmp/x <<'EOF'\nthe answers come later\nEOF",
                        "npx vitest run src/app/api/answers/route.test.ts", "mkdir -p src/app/answers/",
                        "python3 scripts/kb_lint.py > x.log; grep answers x.log", "rm -rf answers",
                        "cd /tmp && rm -rf knowledge/board/../answers"):
            with self.subTest(command=command):
                self.assertIsNone(reason(command))

    def test_the_desk_state_is_held_as_the_answers_are(self):
        """Workspaces/board-desk/ holds the Board's medium id the reader trusts and the desk's Notion ids."""
        for command, why in {"rm -rf workspaces/board-desk": "`rm`",
                             "echo '{}' > workspaces/board-desk/reader.json": "an output redirection",
                             "cd workspaces && sed -i '' s/a/b/ board-desk/notion.json": "`sed`",
                             "cp /tmp/x.json /repo/Workspaces/Board-Desk/notion.json": "`cp`"}.items():
            with self.subTest(command=command):
                self.assertIn(why, reason(command))
        self.assertIn("`python3` isn't a read",
                      reason("python3 -c 'print(1)' > x", "/repo/workspaces/board-desk"))
        for command in ("cat workspaces/board-desk/reader-log.jsonl", "ls workspaces/board-desk",
                        "tail -5 workspaces/board-desk/attribution.jsonl", "mkdir -p workspaces/board-desking"):
            with self.subTest(command=command):
                self.assertIsNone(reason(command))

    def test_a_folder_holding_one_and_a_git_command_that_drops_the_checkout_s_changes_name_it(self):
        """The reader's rows wait uncommitted in the main checkout, and
        workspaces/board-desk/ is never committed; a write to a folder holding them, or a git command that throws
        away a checkout's uncommitted changes, loses them."""
        repo = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, repo, ignore_errors=True)
        for rel in (".git", "knowledge/board/answers", "knowledge/company", "workspaces/board-desk", "scripts"):
            (repo / rel).mkdir(parents=True)
        cases = {"rm -r knowledge/board": "`rm`", "rm -rf knowledge": "`rm`", "rm -rf workspaces/": "`rm`",
                 "mv knowledge/board /tmp/x": "`mv`",
                 "cd knowledge && rm -rf board": "`rm`", "git checkout -- knowledge/board": "`git checkout`",
                 "git stash -u": "`git stash`", "git stash": "`git stash`", "git stash push -m wip": "`git stash`",
                 "cd scripts && git stash -u": "`git stash`", f"cd /tmp && git -C {repo} stash -u": "`git stash`",
                 "git clean -fdx": "`git clean`", "git reset --hard HEAD": "`git reset`",
                 "git checkout -f main": "`git checkout`", "git checkout -- .": "`git checkout`",
                 "git restore .": "`git restore`", "git restore -s HEAD~1 .": "`git restore`",
                 "git switch --discard-changes main": "`git switch`"}
        if (repo / "Knowledge").exists():  # a case-insensitive disk; on another it is another folder
            cases[f"rm -rf {repo}/Knowledge/Board"] = "`rm`"
        for command, why in cases.items():
            with self.subTest(command=command):
                found = reason(command, str(repo))
                self.assertIsNotNone(found, command)
                self.assertIn("the Board's own answers", found)
                self.assertIn(why, found)
        for command in ("git stash list", "git stash show -p", "git clean -n", "git clean -nfd", "git reset HEAD~1",
                        "git restore --staged .", "git restore -S .", "git checkout -b sys/x main",
                        "git switch -c x main", "git restore -s HEAD~1 -- scripts/x.py",
                        "git checkout main", "rm -r knowledge/company", "ls knowledge/board", "git status",
                        "cp /tmp/x.md knowledge/company/y.md", "python3 scripts/kb_lint.py",
                        "cd knowledge/company && sed -i '' s/a/b/ x.md"):
            with self.subTest(command=command):
                self.assertIsNone(reason(command, str(repo)))
        product = Path(tempfile.mkdtemp()).resolve()  # another repo: no answers there, its git and folders its own
        self.addCleanup(shutil.rmtree, product, ignore_errors=True)
        for rel in (".git", "knowledge", "workspaces"):
            (product / rel).mkdir()
        for command in ("git stash -u && git stash pop", "git reset --hard", "rm -rf knowledge workspaces"):
            with self.subTest(command=command):
                self.assertIsNone(reason(command, str(product)))

    def test_a_cwd_inside_the_folder_names_it(self):
        """The CEO's main session keeps its cwd between calls."""
        inside = "/repo/knowledge/board/answers"
        self.assertIn("`sed` with an option", reason("sed -i '' s/Yes/No/ 2026-W02.md", inside))
        self.assertIn("an output redirection", reason("echo x >> 2026-W02.md", inside))
        self.assertIsNone(reason("cat 2026-W02.md && git diff -- .", inside))
        self.assertIn("`rm`", reason("rm 2026-W02.md", "/repo/knowledge/board/answers/"))


class Loops(unittest.TestCase):
    """A for or while loop of reads over knowledge/ or workspaces/
    is a read, for any agent; a write inside one is refused as it is outside one, and so is a run or a token read
    behind any keyword."""

    def setUp(self):
        self.repo = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, self.repo, ignore_errors=True)
        for rel in (".git", "knowledge/board/answers", "knowledge/company", "workspaces/board-desk", "scripts"):
            (self.repo / rel).mkdir(parents=True)

    def test_a_loop_of_reads_passes(self):
        for command in (
                'for w in alpha beta; do printf "%s: " $w; grep -rlwE "$w" knowledge scripts/board_desk* | head -3; '
                'echo; done',
                'for f in knowledge/board/answers/*.md; do head -3 "$f"; wc -l "$f"; done',
                "grep -rl x knowledge | while read -r f; do sed -n -e '1,5p' -- \"$f\"; done",
                'ls workspaces | while read d; do echo "$d"; cat "workspaces/$d/x" 2>/dev/null; done',
                "for a in x y; do for b in 1 2; do ls knowledge/$a/$b; done; done",
                'for w in a b\ndo\n  grep -rl "$w" knowledge\ndone',
                'while read -r f; do cat "$f"; done < knowledge/board/answers/list.txt',
                "sed -n 64p knowledge/board/answers/README.md", "sed -n '/^## /p;$=' workspaces/board-desk/x",
                "sed -nE -e '1,3p' -e '$=' knowledge/company/x.md knowledge/board/answers/y.md",
                "sed -n '/^## x$/p' knowledge/board/answers/y.md",  # a `$` the shell leaves as it is
                'for f in knowledge/board/answers/*.md; do sed -n -e 1p -- "$f"; done',  # a `$` file after `--`
                "for d in board company; do git log --oneline -3 -- knowledge/$d; done",  # a `$` after git's `--`
                "grep -c x knowledge/board/answers/y.md; cat <<'EOF'\nrm -rf knowledge\nEOF",  # a heredoc's body
                "sed --quiet '/a\\/b/p' knowledge/board/answers/y.md",
                "for x in 1; do python3 scripts/board_desk.py wait; done",
                "for f in knowledge/board/answers/*; do grep -c Yes \"$f\"; done 2>/dev/null",
                "sed -n '1,2p; $ =;' knowledge/board/answers/y.md", "sed -n '/x/ !p' knowledge/board/answers/y.md"):
            with self.subTest(command=command):
                self.assertIsNone(reason(command, str(self.repo)))

    def test_a_write_in_a_loop_is_refused_as_outside_one(self):
        cases = {'for f in knowledge/board/answers/*; do rm "$f"; done': "`rm` isn't a read",
                 'for f in knowledge/board/answers/*; do mv "$f" /tmp/; done': "`mv` isn't a read",
                 "for f in knowledge/board/answers/*; do sed -i '' s/a/b/ \"$f\"; done": "`sed` with an option",
                 "for f in knowledge/board/answers/*; do sed -n 'w /tmp/x' \"$f\"; done": "`sed` but -n",
                 "sed -n '1p;w /tmp/x' knowledge/board/answers/y.md": "`sed` but -n",
                 "sed -n 's/a/b/w /tmp/x' knowledge/board/answers/y.md": "`sed` but -n",
                 "sed -n -f s.sed knowledge/board/answers/y.md": "`sed` with an option",
                 "sed 1p knowledge/board/answers/y.md": "`sed` but -n",
                 "sed -n -e": None, "sed -n -e workspaces/board-desk/x": "`sed` but -n",
                 'for f in a; do echo x > knowledge/board/answers/y; done': "an output redirection",
                 'for f in a; do cat "$f"; done > knowledge/board/answers/all.md': "an output redirection",
                 "for f in a; do echo x | tee -a knowledge/board/answers/y; done": "`tee` isn't a read",
                 "for x in 1; do git stash -u; done": "`git stash`",
                 "cd knowledge && for x in 1; do git reset --hard; done": "`git reset`",
                 "if grep -q x knowledge; then echo y; fi": "`if` isn't a read",
                 "until false; do ls knowledge; done": "`until` isn't a read", "{ ls knowledge; }": "`{` isn't a read",
                 "for f in $(ls knowledge); do cat $f; done": "`$(` hides what runs",
                 "for ((i=0;i<2;i++)); do ls knowledge; done": "`for` isn't a read",
                 "for f in knowledge; do /tmp/done; done": "`done` isn't a read",
                 "for f in knowledge; do cat $f; done 2>knowledge/board/answers/err": "an output redirection",
                 "sed -n '1p' -i knowledge/board/answers/y.md": "`sed` with an option",
                 "sed -n '1 w x' knowledge/board/answers/y.md": "`sed` but -n"}
        for command, why in cases.items():
            with self.subTest(command=command):
                found = reason(command, str(self.repo))
                if why is None:
                    self.assertIsNone(found)
                else:
                    self.assertIn("the Board's own answers", found or "")
                    self.assertIn(why, found)

    def assertHeld(self, cases, cwd=None):
        for command, why in cases.items():
            with self.subTest(command=command):
                found = reason(command, cwd or str(self.repo))
                self.assertIn("the Board's own answers", found or "")
                self.assertIn(why, found)

    def test_a_quoted_or_commented_heredoc_opener_hides_no_line(self):
        """A `<<EOF` in quotes, a comment or `((...))` opens no heredoc, so the lines
        after it are commands; bash runs them."""
        self.assertHeld({"for f in knowledge; do grep -r '<<EOF' $f\nrm -rf $f\ndone": "`rm` isn't a read",
                         "sed -n '/<<EOF/p' knowledge\nrm -rf knowledge": "`rm` isn't a read",
                         "grep -c '<<EOF' knowledge/board/answers/y.md\nrm -rf knowledge": "`rm` isn't a read",
                         'grep -c "<<EOF" knowledge\nrm -rf knowledge': "`rm` isn't a read",
                         "ls knowledge # <<EOF\nrm -rf knowledge": "`rm` isn't a read",
                         'grep -c "a\\"<<EOF" knowledge\nrm -rf knowledge': "`rm` isn't a read"})
        for command in ("echo '<<EOF'\npython3 scripts/board_desk.py read", "echo $((1<<n))\npython3 "
                        "scripts/board_desk.py read", "echo x # <<EOF\npython3 scripts/board_desk.py read",
                        "echo ${x:-<<EOF}\npython3 scripts/board_desk.py read"):  # ${...}
            with self.subTest(command=command):
                self.assertIn("`board_desk.py read`", reason(command) or "")
        for command in ("git add knowledge/company/x.md && git commit -m \"$(cat <<'EOF'\nkb: rm -rf knowledge\nEOF\n"
                        ")\"", "cat <<'PY'\nrm -rf knowledge\nPY\ngrep -c x knowledge/board/answers/y.md"):
            with self.subTest(command=command):  # a heredoc's body is still data, as before
                self.assertIsNone(reason(command, str(self.repo)))
        for line, opens in {"cat <<'EOF'": [("EOF", False)], "cat <<-EOF x": [("EOF", True)],
                            'python3 - <<"PY" && cat <<EOF2': [("PY", False), ("EOF2", False)],
                            "grep '<<EOF' x": [], "cat <<<x": [], "echo \\<<EOF": [], "a # <<EOF": [],
                            "echo a#<<EOF": [("EOF", False)], "x=$((1<<y)); cat <<EOF": [("EOF", False)],
                            "echo $'a\\'<<EOF'": [], 'echo "a\\"<<EOF"': [], "echo ${x:-<<EOF}": [],
                            "echo $[1<<x]": [], "cat <<EOF ${x}": [("EOF", False)],
                            "echo ${x:-'}'} <<EOF": [("EOF", False)]}.items():
            with self.subTest(line=line):
                self.assertEqual(desk.heredocs(line), opens)

    def test_a_dollar_that_may_turn_a_read_into_a_write_is_refused(self):
        """A loop's or read's variable may expand to find's action, git's or sort's
        output file, or a sed script that writes."""
        answers = str(self.repo / "knowledge" / "board" / "answers")
        self.assertHeld({"for a in -delete; do find knowledge $a; done": "`find` with a `$`",
                         "for o in --output=x.md; do git diff $o -- knowledge; done": "`git` with a `$`",
                         'for x in "a/w ."; do sed -n "/$x/p" knowledge/board/answers/y.md; done':
                             "`sed` with a `$` the shell may expand in its script",
                         "sed -n '5,$p' knowledge/board/answers/y.md": "(the last line: `tail -n 1`)",
                         "sed $o -n -e 1p knowledge/board/answers/y.md": "before `--`",
                         'for f in knowledge/board/answers/*; do sort "$f"; done': "`sort` with a `$`"})
        self.assertHeld({'read -r p <<< "w ./x.md"; sed -n "$p" y.md': "`sed` with a `$`",
                         # read as the shell reads `$'\x2f'`: a `w` command, not a print
                         "sed -n '/a'$'\\x2f''w ./,$p' y.md": "`sed` but -n with a script that only prints",
                         'sed -n "/$=x/p" y.md': "`sed` with a `$`"}, answers)
        # zsh, a shell of the Bash tool, expands and splits `$=name`, even in double quotes
        self.assertHeld({"for a in -delete; do find knowledge $=a; done": "`find` with a `$`",
                         "for o in --output=x.md; do git diff $=o -- knowledge; done": "`git` with a `$`",
                         "for o in -oknowledge/board/answers/x; do sort $=o knowledge/company/y.md; done":
                             "`sort` with a `$`",
                         "TMPDIR=knowledge/board/answers sort knowledge/company/y.md": "`sort` with an output file"})
        for command in ("sed -n '$=;1p' knowledge/board/answers/y.md", "sed -n '$=' knowledge/board/answers/y.md"):
            with self.subTest(command=command):
                self.assertIsNone(reason(command, str(self.repo)))

    def test_a_cd_the_check_cannot_follow_leaves_held_words_held(self):
        """After a `cd` to a variable, `~` or `-`, a relative word with a held folder's
        part in it names the folder."""
        self.assertHeld({"if cd ~/x; then rm -rf knowledge; fi": "`if` isn't a read",
                         "for d in a; do cd $d; done; rm -rf knowledge": "`rm` isn't a read",
                         "cd ~/agentic-company/knowledge && rm -rf board": "`rm` isn't a read",
                         "cd - && mv ../workspaces /tmp/x": "`mv` isn't a read",
                         "cd $X && rm -rf x/board": "`rm` isn't a read",
                         "cd - && rm board-desk/notion.json": "`rm` isn't a read"})
        for command in ("cd $HOME/x && rm -rf build", "cd - && ls knowledge", "cd ~/x && rm -rf /tmp/build",
                        "cd ~/x && mkdir -p workspaces/system/reviews",  # no held folder in reach
                        "cd ~/x && python3 scripts/kb_lint.py workspaces/acme/content/x.md",
                        "cd $X && rm -rf knowledge/company/x board/x"):
            with self.subTest(command=command):
                self.assertIsNone(reason(command, str(self.repo)))

    def test_read_only_git_piped_into_reads_passes(self):
        """Read-only git over knowledge/ or its parents, alone or piped into
        cut, head, grep, wc or sort, passes; sort's output file, temp folder and compress program, and git's
        discards, stay refused."""
        for command in ("git status --porcelain -- knowledge/ workspaces/acme/content/ | "
                        "cut -c1-140",
                        "git log --oneline -- knowledge/ | head -5", "git diff --stat -- knowledge | sort | cut -c1-80",
                        "git ls-files knowledge | grep -c md", "git grep -n x -- knowledge | cut -d: -f1 | sort -u",
                        "git show --stat HEAD -- knowledge/board/answers | wc -l",
                        "sort -t: -k2,2 -rn knowledge/board/answers/y.md", "sort -to knowledge/board/answers/y.md",
                        "sort -u -- knowledge/board/answers/y.md -o"):
            with self.subTest(command=command):
                self.assertIsNone(reason(command, str(self.repo)))
        why = "`sort` with an output file, a temp folder or a compress program"
        self.assertHeld({"git status --porcelain -- knowledge | sort -o knowledge/board/answers/x": why,
                         "sort --output=knowledge/board/answers/x knowledge/company/y": why,
                         "sort --out=x knowledge/board/answers/y.md": why, "sort -nro x knowledge/board/answers/y": why,
                         "sort -T knowledge/board/answers knowledge/company/y": why,
                         "sort --compress-program=gzip -S1 knowledge/board/answers/y.md": why,
                         "git stash -u": "`git stash`", "git checkout -- knowledge/": "`git checkout`",
                         "git clean -fd knowledge/": "`git clean`", "git restore knowledge/": "`git restore`",
                         "git diff -- knowledge | uniq - knowledge/board/answers/x": "`uniq` isn't a read"})

    def test_a_run_or_a_token_read_behind_a_keyword_is_the_one_outside(self):
        cases = {"for x in 1; do python3 scripts/board_desk.py read; done": "`board_desk.py read`",
                 "if true; then python3 scripts/board_desk.py hour; fi": "`board_desk.py hour`",
                 "for x in 1; do bash -c 'python3 scripts/board_desk.py run'; done": "in the code this command runs",
                 "while true; do security find-generic-password -s board-desk-notion -w; done":
                     "`security` on its Keychain item",
                 "! security dump-keychain": "dump-keychain"}
        for command, why in cases.items():
            with self.subTest(command=command):
                self.assertIn(why, reason(command) or "")


class MoreShellForms(unittest.TestCase):
    """Shell forms that only refuse more."""

    setUp, assertHeld = Loops.setUp, Loops.assertHeld

    def test_zsh_s_stacked_dollar_equals_is_an_expansion_and_sed_s_own_is_not(self):
        """Zsh expands `$=~a`, `$=^a`, `$==a` and `$=+a` as it does `$=a`."""
        cases = {}
        for flag in ("=~", "=^", "==", "=+"):
            cases[f"for a in -delete; do find knowledge ${flag}a; done"] = "`find` with a `$`"
            cases[f"for o in --output=x.md; do git diff ${flag}o -- knowledge; done"] = "`git` with a `$`"
            cases[f"for o in -oknowledge/board/answers/x; do sort ${flag}o knowledge/company/y.md; done"] = (
                "`sort` with a `$`")
        self.assertHeld(cases)
        for text, expands in {"$=~a": True, "$=^a": True, "$==a": True, "$=+a": True, "$=a": True, "$=/": True,
                              "$=": False, "$=;1p": False, "1p;$= ": False, "{$=}": False, "/x$/p": False}.items():
            with self.subTest(text=text):
                self.assertEqual(bool(desk.EXPANDS.search(text)), expands)
        for command in ("sed -n '$=;1p' knowledge/board/answers/y.md", "sed -n '1p; $= ' knowledge/board/answers/y.md"):
            with self.subTest(command=command):
                self.assertIsNone(reason(command, str(self.repo)))

    def test_a_dollar_word_in_sed_stands_only_after_a_literal_double_dash(self):
        """BSD sed (macOS's) takes a `$f` set to -i as an option right after `-e SCRIPT`, and edited a
        file in place so; GNU sed takes one anywhere before `--`."""
        why = "`sed` with a `$` the shell may expand before `--`"
        self.assertHeld({"for f in -i; do sed -n -e 1p $f '' knowledge/board/answers/y.md; done": why,
                         "sed -n -e 1p ${f} knowledge/board/answers/y.md": why,
                         'sed -n -E -e 1p $f "" knowledge/board/answers/y.md': why,
                         "sed -n --expression=1p $f knowledge/board/answers/y.md": why,
                         'for f in knowledge/board/answers/*.md; do sed -n 1p "$f"; done': why,
                         "sed -n 1p $=f -- knowledge/board/answers/y.md": why,
                         "sed -n -e -- $f knowledge/board/answers/y.md": "`sed` but -n"})
        for command in ('for f in knowledge/board/answers/*.md; do sed -n -e 1p -- "$f"; done',
                        'for f in knowledge/board/answers/*.md; do sed -n -- 1p "$f" "$f"; done',
                        "sed -n -e 1p -- -i knowledge/board/answers/y.md"):  # a file named -i after `--`
            with self.subTest(command=command):
                self.assertIsNone(reason(command, str(self.repo)))

    def test_an_environment_name_set_for_the_commands_after_it_is_refused(self):
        """A TMPDIR set by a loop, a read, printf -v or an assignment with no program sends a later sort's
        temporary files into a held folder; a PATH or HOME so set changes the reads after it."""
        sort = "sort -S 1K knowledge/company/y.md"
        self.assertHeld({f"for TMPDIR in knowledge/board/answers; do {sort}; done": "`TMPDIR` set",
                         f"read -r TMPDIR <<< knowledge/board/answers; {sort}": "`TMPDIR` set",
                         f"printf -v TMPDIR %s knowledge/board/answers; {sort}": "`TMPDIR` set",
                         f"printf -vTMPDIR %s knowledge/board/answers; {sort}": "`TMPDIR` set",
                         f"while read -r TMPDIR; do {sort}; done <<< knowledge/board/answers": "`TMPDIR` set",
                         f"for i in 1; do TMPDIR=knowledge/board/answers; {sort}; done": "`TMPDIR` set",
                         f"read -raTMPDIR <<< knowledge/board/answers; {sort}": "`TMPDIR` set",
                         f"read -r 'TMPDIR?x' <<< knowledge/board/answers; {sort}": "`TMPDIR` set",
                         f"echo ${{TMPDIR::=knowledge/board/answers}}; {sort}": "`TMPDIR` set",
                         "for PATH in /tmp; do cat knowledge/board/answers/y.md; done": "`PATH` set",
                         "for i in 1; do HOME=/tmp; ls knowledge; done": "`HOME` set"})
        for command in (f"for tmp in knowledge/board/answers; do {sort}; done",
                        'while read -r f; do cat "$f"; done < knowledge/board/answers/list.txt',
                        "printf -v line %s x; cat knowledge/board/answers/y.md",
                        "LC_ALL=C sort knowledge/board/answers/y.md"):  # set for that one read only
            with self.subTest(command=command):
                self.assertIsNone(reason(command, str(self.repo)))

    def test_git_grep_s_pager_and_a_prefix_of_git_s_output_are_refused(self):
        """Git grep's -O runs a program on every file it matches; git takes a long option's
        prefix, so --op and --outp are --open-files-in-pager and --output."""
        why = "with a file it writes or a program it runs"
        self.assertHeld({"git grep -Orm -e . -- knowledge/board/answers": why,
                         "git grep -iOrm -e . -- knowledge": why, "git grep -O -e x -- knowledge": why,
                         "git grep --open-files-in-pager=rm -e x knowledge": why,
                         "git grep --op=rm -e x -- knowledge": why, "git grep --o=rm -e x -- knowledge": why,
                         "git diff --outp=knowledge/board/answers/x.md": why,
                         "git log --ou=x -- knowledge": why})
        for command in ("git grep -o -e x -- knowledge/board/answers", "git grep -e-O -- knowledge",
                        "git grep -C2 -m1 x -- knowledge", "git grep --or -e a -e b -- knowledge",
                        "git grep -n x -- -Orm knowledge", "git log --oneline -SFOO -- knowledge"):
            with self.subTest(command=command):
                self.assertIsNone(reason(command, str(self.repo)))

    def test_a_heredoc_s_word_is_read_as_the_shell_reads_it(self):
        """Bash and zsh end `<<E"O"F` at EOF and `<<EOF$x` at EOF$x (checked on macOS,
        zsh 5.9 and /bin/bash); after a word the check can't read, each line is checked as a command and as the
        heredoc's body."""
        self.assertHeld({'cat <<E"O"F\nx\nEOF\nrm -rf knowledge': "`rm` isn't a read",
                         "cat <<EOF$x\nx\nEOF$x\nrm -rf knowledge": "`rm` isn't a read",
                         "cat <<\\EOF\nx\nEOF\nrm -rf knowledge": "`rm` isn't a read",
                         "cat <<$'EOF'\nEOF\nrm -rf knowledge": "isn't a read"})
        self.assertIn("a run of it in a heredoc", reason("python3 - <<E${x}\nimport os; os.system('python3 "
                                                         "scripts/board_desk.py read')\nE${x}") or "")
        for command in ("cat <<EOF$x\nEOF\nrm -rf knowledge\nEOF$x\nls knowledge",  # the body, as the shell's
                        'cat <<E"O"F\nE\nrm -rf knowledge\nEOF\nls knowledge'):
            with self.subTest(command=command):
                self.assertIsNone(reason(command, str(self.repo)))
        for line, opens in {'cat <<E"O"F': [("EOF", False)], "cat <<EOF$x": [("EOF$x", False)],
                            "cat <<\\EOF": [("EOF", False)], "cat <<'E F'": [("E F", False)],
                            "cat <<-'EOF'|x": [("EOF", True)], "cat <<EOF;": [("EOF", False)],
                            "cat <<$'EOF'": [(None, False)], "cat <<`x`": [(None, False)],
                            'cat <<"E${x}"': [(None, False)], "cat <<''": [(None, False)],
                            "cat <<-": [(None, True)]}.items():
            with self.subTest(line=line):
                self.assertEqual(desk.heredocs(line), opens)

    def test_a_line_that_splits_without_its_comment_is_checked(self):
        """A line that won't split whole, because of a quote in its comment, is
        refused as one that won't split when it names the folder, else checked without its comment."""
        self.assertHeld({"rm -rf knowledge/board # don't": "`rm` isn't a read",
                         "ls knowledge\nrm -rf knowledge # it's gone": "`rm` isn't a read",
                         "cat knowledge/board/answers/y.md # it's": "can't split"})
        self.assertIsNone(reason("ls knowledge # it's a read", str(self.repo)))
        for line, cut in {"rm -rf x # don't": "rm -rf x ", "# it's": "", "echo '#' don't": None,
                          "echo ${a:- #} it's": None, "echo $(x) # it's": None, "echo a#b it's": None}.items():
            with self.subTest(line=line):
                self.assertEqual(desk.uncommented(line), cut)


class Desk(unittest.TestCase):
    def assertRefused(self, command, why=""):
        found = reason(command)
        self.assertIsNotNone(found, command)
        self.assertIn("board_desk.py's run, hour, day and read", found)
        self.assertIn(why, found)

    def test_its_reading_commands_pass(self):
        for command in ("python3 scripts/board_desk.py wait", "python3 scripts/board_desk.py install",
                        "/usr/bin/python3 /repo/scripts/board_desk.py uninstall", "python3 scripts/board_desk.py --help",
                        "python3 scripts/board_desk.py", "nohup python3 scripts/board_desk.py wait --root /tmp/x",
                        "python3 -m scripts.board_desk -h"):
            with self.subTest(command=command):
                self.assertIsNone(reason(command))

    def test_setup_and_attribution_are_the_ceo_main_session_s_alone(self):
        """They put a test row in the Board's Notion and write the desk's
        ids and the Board's id."""
        for command in ("python3 scripts/board_desk.py setup", "python3 scripts/board_desk.py attribution --board 1f2e",
                        "bash -c 'python3 scripts/board_desk.py setup'",
                        "zsh <<'EOF'\npython3 scripts/board_desk.py attribution --board 1f2e\nEOF"):
            with self.subTest(command=command):
                self.assertIsNone(reason(command, ceo=True))
                self.assertIn("board_desk.py's run, hour, day and read", reason(command) or "")
        self.assertIn("can't split", reason("python3 'scripts/board_desk.py setup") or "")
        self.assertIn("`board_desk.py read`", reason("python3 scripts/board_desk.py read", ceo=True) or "")

    def test_its_writing_commands_are_refused(self):
        cases = {"python3 scripts/board_desk.py hour": "`board_desk.py hour`",
                 "python3 scripts/board_desk.py run": "`board_desk.py run`",
                 "python3 -u scripts/Board_Desk.py day --root .": "`board_desk.py day`",
                 "./scripts/board_desk.py hour": "hour", "python3 scripts/board_desk.py --root /x hour": "--root",
                 "cd scripts && python3 -m board_desk day": "day", "python3 -mscripts.board_desk hour": "hour",
                 "timeout 600 python3 scripts/board_desk.py run": "run", "env X=1 python3 scripts/board_desk.py hour": "",
                 "bash -c 'python3 scripts/board_desk.py hour'": "the code this command runs",
                 "zsh <<'EOF'\npython3 scripts/board_desk.py day\nEOF": "a heredoc",
                 "python3 'scripts/board_desk.py hour": "can't split",
                 "node -e 'require(\"child_process\").execSync(\"python3 scripts/board_desk.py hour\")'": "the code",
                 "eval python3 scripts/board_desk.py run": "", "sh -ec 'scripts/board_desk.py day'": "the code",
                 "echo \"$(python3 scripts/board_desk.py hour)\"": "a substitution",
                 "x=`scripts/board_desk.py day`": "a substitution",
                 "python3 scripts/board_desk.py read": "`board_desk.py read`"}
        for command, why in cases.items():
            with self.subTest(command=command):
                self.assertRefused(command, why)

    def test_reading_editing_and_testing_it_pass(self):
        for command in ("grep -n 'def hour' scripts/board_desk.py", "git diff main -- scripts/board_desk.py",
                        "python3 -m unittest scripts.tests.test_board_desk scripts.tests.test_kb_sweep",
                        "python3 -m unittest scripts/tests/test_board_desk.py", "cp scripts/board_desk.py /tmp/x.py",
                        "git commit -m 'board_desk.py hour: date fix'", "sed -i '' 's/a/b/' scripts/board_desk.py",
                        "python3 - <<'EOF'\np = 'scripts/board_desk.py'\nEOF",
                        "cat > /tmp/notes <<'EOF'\npython3 scripts/board_desk.py hour\nEOF",
                        "python3 -m unittest discover -s scripts/tests -k board_desk -v",
                        "python3 -m pytest -k board_desk scripts/tests",
                        "python3 scripts/second_opinion.py --kind code --brief \"T5: board_desk record() writes R-rows\"",
                        "git commit -m \"$(cat <<'EOF'\nsys: board_desk wait restarted; board_desk hour at :00\nEOF\n)\""):
            with self.subTest(command=command):
                self.assertIsNone(reason(command))


class Token(unittest.TestCase):
    """The desk's Notion token is read only by adapter_notion.py."""

    def test_reads_and_changes_of_the_token_are_refused(self):
        cases = {"security find-generic-password -s board-desk-notion -a notion -w": "`security` on its Keychain item",
                 "security find-generic-password -a notion -sboard-desk-notion -g": "`security`",
                 "/usr/bin/security delete-generic-password -s board-desk-notion": "`security`",
                 "env -i security find-generic-password -s board-desk-notion -w | pbcopy": "`security`",
                 "sh -c 'security find-generic-password -s board-desk-notion -w'": "in the code",
                 "python3 -c \"import sys; sys.path.insert(0, 'scripts/board_desk'); import adapter_notion as a; "
                 "print(a.keychain_token())\"": "in the code",
                 "python3 - <<'EOF'\nfrom adapter_notion import keychain_token\nprint(keychain_token())\nEOF":
                     "in a heredoc",
                 "python3 -c 'import subprocess; subprocess.run([\"security\", \"find-generic-password\", \"-s\", "
                 "\"board-desk-notion\", \"-w\"])'": "in the code",
                 "python3 -c \"from adapter_notion import keychain_token; print(keychain_token())": "can't split",
                 # the account, dump-keychain and the adapter's own client
                 "security find-generic-password -a notion -w": "`security` on its Keychain account",
                 "security find-generic-password -wanotion": "account", "security dump-keychain -d": "dump-keychain",
                 "/usr/bin/security dump-keychain": "dump-keychain", "sh -c 'security dump-keychain -d'": "in the code",
                 "python3 -c 'import subprocess; subprocess.run([\"security\", \"find-generic-password\", \"-a\", "
                 "\"notion\", \"-w\"])'": "in the code",
                 "python3 -c \"import sys; sys.path.insert(0, 'scripts/board_desk'); import adapter_notion as a; "
                 "print(a.Notion().call('GET', '/users/me'))\"": "in the code",
                 "python3 - <<'EOF'\nfrom adapter_notion import Desk\nDesk(root, None, print).poll(None)\nEOF":
                     "in a heredoc",
                 "python3 -c \"import adapter_notion as a; a.Notion().call('GET', '/users/me')": "can't split"}
        for command, why in cases.items():
            with self.subTest(command=command):
                found = reason(command)
                self.assertIsNotNone(found, command)
                self.assertIn("the Board desk's Notion token", found)
                self.assertIn(why, found)

    def test_reading_the_code_and_other_keychain_items_pass(self):
        for command in ("grep -n keychain_token scripts/board_desk/adapter_notion.py",
                        "grep -rn board-desk-notion scripts/", "security find-generic-password -s other-key -w",
                        "security find-generic-password -s other-key -a someone -w", "grep -n 'Notion(' x.py",
                        "python3 -c 'import adapter_notion as a; print(a.notion_text(open(\"x.md\").read()))'",
                        "git commit -m 'sys: refuse security dump-keychain and adapter_notion Notion() for agents'",
                        "python3 -m unittest scripts.tests.test_adapter_notion",
                        "git -C .claude/worktrees/board-desk-notion log --oneline -3",
                        "git commit -m \"$(cat <<'EOF'\nsys: keychain_token reads board-desk-notion via security\nEOF\n)\""):
            with self.subTest(command=command):
                self.assertIsNone(reason(command))


class Narrowed(unittest.TestCase):
    """The check blocks only commands that write there, not ones that merely name the desk's script or a questions
    folder. Each write form stays refused (Answers.test_writes_there_are_refused and these)."""

    # a commit with a newline inside its quoted message
    CASE_1 = ("git add scripts/board_desk.py scripts/board_desk/adapter_notion.py scripts/tests/test_board_desk.py "
              "scripts/tests/test_adapter_notion.py && git commit -q -m \"sys: a "
              "database read whole is marked polled, and notion.json saved, only after record() wrote the ledger\n\n"
              "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\" && git log --oneline -1")

    def test_a_newline_inside_quotes_is_the_word_s_as_the_shell_reads_it(self):
        for command in (self.CASE_1, "git commit -m 'kb: one\n\ntwo' && git log -1",
                        "git commit -m \"a\nit's\" && git status", f"git commit -m 'kb: {PAGE}\nmore' && git log -1",
                        "git commit -m \"board_desk.py hour:\nthe date fix\""):
            with self.subTest(command=command):
                self.assertIsNone(reason(command))
                self.assertIsNone(reason(command, ceo=True))

    def test_a_write_or_a_run_after_a_quoted_newline_is_still_refused(self):
        cases = {f"git commit -m 'a\nb' && rm {PAGE}": "`rm` isn't a read",
                 f"git commit -m \"a\nb\"; echo x >> {PAGE}": "an output redirection",
                 "git commit -m 'a\nb' && python3 scripts/board_desk.py read": "`board_desk.py read`",
                 f"echo 'x > {PAGE}": "can't split", f"echo 'a\nb\nrm {PAGE}": "can't split",
                 # where the shell's quotes nest inside others and the check's don't, no line is joined (NESTS)
                 f"echo \"${{x:-\"it's\"}}\"\nrm {PAGE}\necho \"it's\"": "the Board's own answers",
                 f"echo \"$(echo \"it's\")\"\nrm {PAGE}\necho \"it's\"": "the Board's own answers",
                 f"echo \"`echo \"it's\"`\"\nrm {PAGE}\necho \"it's\"": "the Board's own answers",
                 # after a heredoc word the check can't read, whose body may end at any line, nothing is joined (bash
                 # and zsh end this body at the blank line and run the rm)
                 "cat <<\"\"\necho '\n\nrm -rf knowledge/board/answers # '": "the Board's own answers",
                 "cat <<$'E'\necho '\nE\nrm -rf knowledge/board/answers # '": "the Board's own answers",
                 # after an escaped backslash bash and zsh run the next line, which is checked as a command
                 "echo \\\\\nrm -rf knowledge/board/answers '\n'": "`rm` isn't a read",
                 "echo \\\\\npython3 scripts/board_desk.py read '\n'": "`board_desk.py read`",
                 "echo \"a\nb\" \\\\\nrm -rf knowledge/board/answers": "`rm` isn't a read"}
        for command, why in cases.items():
            with self.subTest(command=command):
                self.assertIn(why, reason(command) or "")

    def test_a_backslash_newline_is_read_as_the_shell_reads_it(self):
        """Bash and zsh
        remove a backslash-newline outside single quotes and comments, end a line at an escaped backslash, join no line
        in a quoted heredoc's body, and do in an unquoted one (checked on macOS, /bin/bash and zsh 5.9)."""
        cases = {
            # an escaped backslash at an echo's end; the next line runs
            "echo a\\\\\nrm -rf knowledge/board/answers": "`rm` isn't a read",
            # a quoted heredoc's body line ending in a backslash above its word: the body ends there
            "cat <<'EOF'\nx\\\nEOF\nrm -rf knowledge/board/answers": "`rm` isn't a read",
            "cat <<\\EOF\nx\\\nEOF\npython3 scripts/board_desk.py read": "`board_desk.py read`",
            # the shell removes the backslash and the newline: one word, not two
            "rm -rf knowledge/bo\\\nard/answers": "`rm` isn't a read",
            "python3 scripts/board_\\\ndesk.py read": "`board_desk.py read`",
            # after a word the check can't read, a later heredoc's body is still read as commands
            "cat <<''\ncat <<EOF\n\nrm -rf knowledge/board/answers\nEOF": "`rm` isn't a read",
            # a comment's backslash joins nothing: the next line runs (shlex won't split the first line whole)
            "ls x # a comment \\\nrm -rf knowledge/board/answers": "the Board's own answers",
        }
        for command, why in cases.items():
            with self.subTest(command=command):
                self.assertIn(why, reason(command) or "")
        for command in (  # the shell's reading, which the check now shares, passes these
                "cat <<EOF\nx\\\nEOF\nrm -rf knowledge/board/answers\nEOF",  # unquoted: `x\` and `EOF` are `xEOF`
                "echo 'a\\\nrm -rf knowledge/board/answers'"):  # in single quotes a backslash is a backslash
            with self.subTest(command=command):
                self.assertIsNone(reason(command))
        for line, joins in {"a\\": True, "a\\\\": False, "a\\\\\\": True, "'a\\": False, "$'a\\": False,
                            "\"a\\": True, "a # b\\": False, "a $(b) 'c\\": True}.items():
            with self.subTest(line=line):
                self.assertEqual(desk.continues(line), joins)

    def test_each_write_form_stays_refused_in_both_folders(self):
        # a redirect, cp, mv, rm, tee, sed -i, and git commands that change the files (Write and
        # Edit: test_guard_kb_write.py), for the CEO's main session too
        for path in (PAGE, "workspaces/board-desk/notion.json"):
            for command in (f"echo x > {path}", f"echo x >> {path}", f"cp /tmp/x {path}", f"mv {path} /tmp/x",
                            f"rm {path}", f"echo x | tee {path}", f"sed -i '' s/a/b/ {path}", f"git checkout -- {path}",
                            f"git restore {path}", f"git rm -q {path}", f"git mv {path} /tmp/x",
                            f"git commit -m 'x\ny' && rm {path}"):
                with self.subTest(command=command):
                    self.assertIsNotNone(reason(command))
                    self.assertIsNotNone(reason(command, ceo=True))


class TextOnly(unittest.TestCase):
    """A command whose only
    mention of a held folder is text it prints or writes elsewhere passes (text_only); one that may run that text,
    take paths from it or change what prints it is checked as before."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, self.root)
        for folder in (".git", "knowledge/board/answers", "workspaces/board-desk", "scratch"):
            (self.root / folder).mkdir(parents=True)
        self.script = self.root / "scratch" / "log.py"
        self.script.write_text("pass\n")
        self.cwd = str(self.root)

    def test_the_ceo_s_text_passes(self):
        s = self.root / "scratch"
        commands = [
            # a status-log row quoting the ledger, in two commands: the file written, then a script run on it, which
            # names no held folder; in one command it stays refused (below)
            f"date -u +%H:%M:%SZ; S={s}; printf '%s\\n' '| 2026-01-05 | board | R-1 Note (a row on the desk, "
            f"knowledge/board/answers/2026-W02.md:9, word for word): \"| R-1 | Note |\". |' > $S/r-r1.txt",
            f"S={s}; python3 {self.script} knowledge/board/directives/D-20260101-demo.md $S/r-r1.txt && "
            "git add knowledge/board/directives/D-20260101-demo.md && git commit -q -m "
            "\"kb(D-20260101-demo): R-1, a note on the desk\n\n"
            "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\" && git log -1 --format=%h",
            # an order's text into a scratch file
            f"S={s}; cat > $S/o-9.md <<'EOF'\nORDER D-20260101-demo-9\nWhy: `guard_marketing_tools.py` "
            "blocks only commands that write to knowledge/board/answers/ and workspaces/board-desk/; run "
            "`python3 -m unittest discover -s scripts/tests` $(not run)\nEOF\necho ok",
            # the CEO main session's commit of the ledger
            f"git add {PAGE} && git commit -q -m \"kb: the Board's answers ledger, week 2026-W02 (R-1 to R-3)\n\n"
            "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\" && git log --oneline -1 | cut -c1-90",
            "printf '%s\\n' 'workspaces/board-desk/notion.json' > /tmp/note.txt",
            "tee /tmp/a.md /tmp/b.md <<'EOF' >/dev/null\nrm -rf knowledge/board/answers\nEOF",
            "echo knowledge/board/answers >&2; echo $'knowledge/board/answers' > /tmp/x",
            "git commit -q -am 'rm -rf knowledge/board/answers' && git log -1",
        ]
        for command in commands:
            for ceo in (False, True):
                with self.subTest(command=command, ceo=ceo):
                    self.assertIsNone(reason(command, self.cwd, ceo))

    def test_text_that_may_run_or_be_read_as_paths_is_checked_as_before(self):
        p = "knowledge/board/answers"
        cases = {
            f"echo {p}/x | xargs rm": "`xargs` isn't a read",
            f"echo 'rm -rf {p}' > /tmp/x.sh; sh /tmp/x.sh": "the Board's own answers",
            f"printf '{p}/x' > /tmp/l; xargs rm < /tmp/l": "the Board's own answers",
            f"printf '{p}/x\\n' > /tmp/l; while read -r f; do rm \"$f\"; done < /tmp/l": "the Board's own answers",
            f"printf '%s' \"$(rm -rf {p})\"": "hides what runs",
            f"cat > /tmp/x <<EOF\n$(rm -rf {p})\nEOF": "hides what runs",
            f"python3 - <<'EOF'\nimport shutil; shutil.rmtree('{p}')\nEOF": "`python3` isn't a read",
            # a script this command writes, by its basename (the stand-in exists, so only that catches it)
            f"cat > {self.script} <<'EOF'\nimport shutil; shutil.rmtree('{p}')\nEOF\npython3 {self.script}":
                "an output redirection",
            f"printf 'diff --git a/{p}/x b/{p}/x' > /tmp/p; git apply /tmp/p": "the Board's own answers",
            f"printf -v a '{p}'; rm -rf $a": "`rm` isn't a read",
            f"cat <<'EOF' | sh\nrm -rf {p}\nEOF": "`sh` isn't a read",
            f"printf() {{ rm -rf \"$@\"; }}; printf {p}": "isn't a read",
            f"alias echo='rm -rf'\necho {p}": "`alias` isn't a read",
            f"PATH=/tmp/evil:$PATH; cat > /tmp/a <<'EOF'\n{p}\nEOF": "`PATH` set",
            # its value names a holder; the plain assignment is a read, the printf's `>` isn't
            f"s=knowledge/board; printf '{p}' > $s/answers/f": "an output redirection",
            f"s=$PWD/knowledge/board; printf '{p}' > $s/answers/f": "an output redirection",
            f"echo {p} > {p}/x": "an output redirection",
            f"cd {p} && printf x > f": "an output redirection",
            f"X=1 printf '{p}' > /tmp/x": "an output redirection",
            f"date -s 1200; printf '{p}'": "`date` isn't a read",
            f"cat > /tmp/x <<EOF\n$HOME {p}\nEOF": "an output redirection",  # an unquoted body with a `$`
            # a program none of the rules knows still gets the full check
            f"echo {p}; rm -rf /tmp/x": "`rm` isn't a read",
            # python with a file the same command wrote, which its script may run (the stand-in script exists)
            f"printf 'import shutil; shutil.rmtree(\"{p}\")' > /tmp/z.py; python3 {self.script} /tmp/z.py":
                "the Board's own answers",
            f"printf 'import shutil; shutil.rmtree(\"{p}\")' > /tmp/z; python3 {self.script} < /tmp/z":
                "the Board's own answers",
            f"F=/tmp/z.py; printf 'import shutil; shutil.rmtree(\"{p}\")' > $F && python3 {self.script} -x $F":
                "the Board's own answers",
            f"cat > /tmp/z.py <<'EOF'\nimport shutil; shutil.rmtree('{p}')\nEOF\npython3 {self.script} /tmp/z.py":
                "the Board's own answers",
            f"printf '%s\\n' '| R-1 | {p}/2026-W02.md |' > /tmp/r.txt && python3 {self.script} log.md /tmp/r.txt":
                "the Board's own answers",  # in one command: two commands pass (above)
        }
        # a commit message, which text_only drops, piped into an interpreter (code.py runs what it reads): no command
        # with one passes, by any path
        for interpreter in ("python3", "/usr/bin/python3", "node", "ruby", "perl", "/bin/bash", "sh", "zsh"):
            cases[f"git commit -q --allow-empty -m 'import shutil; shutil.rmtree(\"{p}\")' && git log -1 --format=%B "
                  f"| {interpreter} {self.script}"] = "the Board's own answers"
        for command, why in cases.items():
            with self.subTest(command=command):
                self.assertIn(why, reason(command, self.cwd) or "")

    def test_ansi_c_quotes_are_read_as_the_shell_reads_them(self):
        """`echo $'it\\'s'; rm -rf knowledge` splits as the shell does (shlex
        has no `$'...'`)."""
        for command in ("echo $'it\\'s'; rm -rf knowledge", "rm -rf $'knowledge'", "rm -rf $'knowledge/board'"):
            with self.subTest(command=command):
                self.assertIn("`rm` isn't a read", reason(command, self.cwd) or "")
        self.assertEqual(desk.ansi_c("a $'it\\'s\\n\\101\\x41\\u00e9\\cA' \"$'x'\" '$'"),
                         "a 'it'\"'\"'s\nAAé\x01' \"$'x'\" '$'")
        self.assertIsNone(reason("git commit -m \"$(cat <<'EOF'\nkb: the knowledge base's page\nEOF\n)\"", self.cwd))

    def test_a_nul_in_ansi_c_quotes_is_read_as_bash_and_zsh_end_the_word(self):
        """A program's argument ends at a NUL; a command with one keeps every check as written (nul_readings)."""
        for command in ("rm -rf $'knowledge/board/answer\\x73\\0x'", "rm -rf $'knowledge/board/answers\\0'x",
                        "rm -rf knowledge/board/$'ans\\0zz'wers", "rm -rf $'knowledge/board/answers\\c@'",
                        "rm -rf $'knowledge/board/answers\\u0000/x'", "rm -rf $'knowledge/board/answers\\x00'y",
                        # refused as written
                        "find knowledge/board -mindepth 1 -print0 | while IFS= read -r -d $'\\0' f; do rm -rf \"$f\"; "
                        "done", "cd knowledge/board; rm -rf answers $'\\0'", "rm -r knowledge/board $'\\0'"):
            with self.subTest(command=command):
                self.assertIn("the Board's own answers", reason(command, self.cwd) or "")
        self.assertEqual(desk.nul_readings("rm $'a\\x0b' $'k\\0z'w"), ["rm $'a\\x0b' $'k'w", "rm $'a\\x0b' $'k' w"])
        self.assertEqual(desk.nul_readings("rm $'a\\x0b' $'\\\\0'"), [])  # an escaped backslash, then 0: no NUL
        self.assertIsNone(reason("git ls-files -z | while IFS= read -r -d $'\\0' f; do echo \"$f\"; done", self.cwd))


class RunsAndQualifiers(unittest.TestCase):
    """Options that run a program, zsh glob qualifiers, and plain reads beside python runs."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, self.root)
        for folder in (".git", "knowledge/board/answers", "knowledge/company", "workspaces/board-desk", "scripts"):
            (self.root / folder).mkdir(parents=True)
        for script in ("kb_sweep.py", "kb_lint.py", "board_desk.py"):
            (self.root / "scripts" / script).write_text("pass\n")
        self.cwd = str(self.root)

    def assertHeld(self, cases, message="the Board's own answers"):
        for command, why in cases.items():
            with self.subTest(command=command):
                found = reason(command, self.cwd) or ""
                self.assertIn(message, found)
                self.assertIn(why, found)

    def assertPass(self, commands, ceo=False):
        for command in commands:
            with self.subTest(command=command):
                self.assertIsNone(reason(command, self.cwd, ceo))

    def test_a_git_option_that_runs_a_program_is_not_a_read(self):
        """Git's -c (core.editor, core.pager, alias.*, any key that may run a program), --receive-pack,
        --upload-pack and --exec, its own options that name a program or a config, and a variable set for it, are
        read as a run."""
        runs = "a program it runs"
        self.assertHeld({
            "git -c core.pager='rm -rf knowledge/board/answers' log": runs,
            "git -c core.editor=/tmp/x.sh commit -- knowledge/board/answers": runs,
            "git -c alias.x='!rm -rf knowledge' log": runs,  # its value names a holder: read as paths too
            "git -c alias.x='!rm -rf knowledge' x": "`git x`",  # an alias isn't a subcommand that keeps files
            "git -c alias.st='!sh -c \"rm -rf knowledge/board/answers\"' st": "`git st`",
            "git -c core.fsmonitor=/tmp/x.sh status -- knowledge": runs,
            "git -c core.fsmonitor=true status -- knowledge": runs,
            "git -c diff.external=/bin/rm diff -- knowledge": runs,
            "git -c include.path=/tmp/x.cfg diff -- knowledge": runs,
            "git -c Core.Pager=x log -- knowledge": runs, "git -c core.quotepath=off -c x.y=z log -- knowledge": runs,
            "git push --receive-pack='rm -rf knowledge' . HEAD": runs,
            "git push --rec='rm -rf knowledge/board/answers' . HEAD": runs,  # a prefix git takes
            "git push --exec='rm -rf knowledge' . HEAD": runs,
            "git push --receive-pack sh . HEAD -- knowledge": runs,
            "git --exec-path=/tmp/x status -- knowledge": runs, "git --git-dir=/tmp/x status -- knowledge": runs,
            "git --work-tree=/tmp status -- knowledge": runs, "git --config-env=core.pager=X log -- knowledge": runs,
            "git -p log -- knowledge": runs, "git --paginate log -- knowledge": runs,
            "GIT_EXTERNAL_DIFF=/bin/rm git diff -- knowledge": "`GIT_EXTERNAL_DIFF` set for `git`",
            "GIT_TRACE=knowledge/board/answers/x git status": "`GIT_TRACE` set for `git`",
            "GIT_PAGER='rm -rf knowledge' git log": "`GIT_PAGER` set for `git`",
            "GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=core.pager GIT_CONFIG_VALUE_0=x git log -- knowledge": "set for",
            "PATH=/tmp/x cat knowledge/board/answers/y.md": "`PATH` set for `cat`",
            "path=/tmp/x cat knowledge/board/answers/y.md": "`path` set for `cat`"})
        # upload-pack's commands (fetch, ls-remote, clone) aren't reads at all
        self.assertHeld({"git fetch --upload-pack='rm -rf knowledge' .": "",
                         "git ls-remote --upload-pack='rm -rf knowledge' .": ""})
        # the code it runs is checked as any code: a desk run, a read of the token
        for command, message in {
                "git -c core.pager='python3 scripts/board_desk.py run' log": "a run of it in the code",
                "GIT_PAGER='python3 scripts/board_desk.py read' git log": "a run of it in the code",
                "git push --receive-pack='python3 scripts/board_desk.py hour' . HEAD": "a run of it in the code",
                "git -c alias.t='!security find-generic-password -s board-desk-notion -w' t": "Notion token"}.items():
            with self.subTest(command=command):
                self.assertIn(message, reason(command, self.cwd) or "")
        self.assertPass([
            "git log --oneline -3 -- knowledge/board/answers", f"git -C {self.root} status --short -- knowledge",
            "git -c core.quotepath=off status --short -- knowledge", "git -c color.ui=never diff --stat -- knowledge",
            "git -c core.quotepath log -1 -- knowledge",
            "git -c user.name=x -c advice.statusHints=false status -- knowledge",
            "git --no-pager log -1 -- knowledge", "git -P show --stat HEAD -- knowledge/board/answers",
            "git --no-optional-locks status -- knowledge", "GIT_PAGER=cat git log -1 -- knowledge",
            "LC_ALL=C git log -1 -- knowledge", "git grep -c x -- knowledge",
            "git diff --exit-code --stat -- knowledge", "git status --untracked-files=no -- knowledge",
            "git diff --unified=0 -- knowledge", "git log --format=%H -1 -- knowledge | cut -c1-8",
            f"git add {PAGE} && git commit -q -m 'kb: answers' && git push", "LANG=C sort knowledge/company/x.md"])

    def test_a_zsh_glob_qualifier_is_read_as_the_code_it_runs(self):
        """Zsh runs a qualifier's `e` string and `+` name for each file the glob matches, even with no `*` (checked on
        macOS, zsh 5.9, with prints only)."""
        qualifier = "a zsh glob qualifier that runs code"
        self.assertHeld({
            "ls x*(e:'rm -rf knowledge':)": qualifier,  # its code names a holder: the command names one
            "ls .(e:'rm -rf knowledge/board/answers':)": qualifier,
            "ls x*(e:rm\\ -rf\\ knowledge:)": qualifier, "ls \".\"(e,'rm -rf knowledge',)": qualifier,
            "ls x(#qe:'rm -rf knowledge':)": qualifier, "ls x(Ne{rm -rf knowledge})": qualifier,
            "ls x*(e:'rm -rf kn\"o\"wledge':)": qualifier,  # the code's own quotes, removed when it runs
            "ls x*(e,'ls y*(e:\"rm -rf knowledge\":)',)": qualifier,  # one in its code
            "ls knowledge/board/answers/*(e:'true':)": qualifier, "ls knowledge/board/answers/*(+f)": qualifier,
            "cat knowledge/company/x(e:'cd knowledge':)": qualifier,
            "echo knowledge/board/answers x(e:'rm -rf knowledge':)": qualifier,  # text_only doesn't take it
            # after a numeric glob's `>` (its `>(` refused first) or an escaped character
            "ls /dev/fd/<->(e:'rm -rf knowledge':)": "`>(` hides what runs",
            "ls x<1-5>(e:'rm -rf knowledge':)": "`>(` hides what runs", "ls x\\ (e:'rm -rf knowledge':)": qualifier})
        self.assertIn("`board_desk.py run`", reason("echo x(e:'python3 scripts/board_desk.py run':)", self.cwd) or "")
        self.assertPass(["ls -d knowledge/board/answers/*", "grep -E 'a(e:b:)' knowledge/board/answers/y.md",
                         "grep -c 'x(e:rm -rf knowledge:)' knowledge/company/x.md", "echo x(e:'print hi':)",
                         "for f in knowledge/board/answers/*; do wc -l \"$f\"; done"])
        line = ("ls x*(e:'rm -rf k':) y(+f) \"z(e:q:)\" 'w(e:q:)' $(a) f() { :; } a=(b) c <(d) ${(e)v} "
                "\\(e:q:) x(e::) x(L+3)")
        self.assertEqual(desk.qualifier_codes(line), ["rm -rf k", "f", "3"])
        self.assertEqual(desk.qualifier_codes("ls <->(e:'a':) x<1->(+g) x\\ (e:b:) <(c) >(d) 2>(e:f:)"),
                         ["a", "g", "b"])
        self.assertEqual(desk.dequoted("e:'a b':\"c\"\\ d"), "e:a b:c d")

    def test_a_read_only_grep_by_a_plain_variable_passes_and_a_shell_variable_stays_refused(self):
        """A read-only grep over a plain variable's path; `tr` reads only its input. A variable the shell reads, by any
        form, stays refused (checked on macOS, zsh 5.9: each changed what a later `ls` ran). An upper-case name isn't
        one the shell reads for being upper-case."""
        grep = ('{v}=/tmp/stand-in/agent-x.jsonl; grep -n "Blocked: knowledge/board/answers/ holds" ${v} | '
                'cut -d: -f1 | head; grep -n "cases2.py\\|cases.py /" ${v} | cut -d: -f1 | tr \'\\n\' \' \'')
        self.assertPass([grep.format(v="t"), "s=knowledge/board; cat $s/answers/y.md", "x=1 y=2; ls knowledge",
                         grep.format(v="T")])
        self.assertHeld({
            "path=/tmp/x; ls knowledge": "`path` set", "for path in /tmp/x; do ls knowledge; done": "`path` set",
            "commands=(ls /bin/rm); ls -rf knowledge": "`commands` set",
            "functions=(ls 'rm -rf \"$@\"'); ls knowledge": "`functions` set",
            "read -A commands <<< 'ls /bin/rm'; ls -rf knowledge": "`commands` set",
            "read -Acommands <<< 'ls /bin/rm'; ls -rf knowledge": "`commands` set",
            "printf -v path %s /tmp/x; ls knowledge": "`path` set",
            "echo ${path::=/tmp/x}; ls knowledge": "`path` set",
            # text_only too: the assignment's name, not its value; a `(` after `=` with an `e` in it reads as a glob
            # qualifier's code first (zsh reads `a=(e:...:)` in an argument so), and refuses the command whole
            "commands=(echo /bin/rm)\necho knowledge/board/answers": "a zsh glob qualifier",
            "functions=(echo 'rm -rf \"$@\"')\necho knowledge/board/answers": "a zsh glob qualifier",
            "s=x; rm -rf knowledge/board/answers": "`rm` isn't a read",
            "s=x > knowledge/board/answers/x": "an output redirection",
            "> knowledge/board/answers/x": "a bare redirection"})
        with mock.patch.dict(os.environ, {"lower_exported": "1"}):
            self.assertHeld({"lower_exported=x; ls knowledge": "the environment exports it"})

    CEO = ("python3 scripts/kb_sweep.py --apply --owner ceo 2>&1 | tail -2; python3 scripts/kb_lint.py 2>&1 | "
           "grep -E \": error|^kb_lint\"; git status --short knowledge/ | grep -v \"^??\" | head -6")

    def test_the_ceo_s_sweep_with_a_read_of_knowledge_passes(self):
        """The CEO's command names a held folder only by its parent, knowledge/, in git status's words."""
        for ceo in (False, True):
            self.assertPass([self.CEO, "python3 scripts/kb_lint.py && git log --oneline -3 -- knowledge",
                             "ls knowledge/board; python3 -I scripts/kb_lint.py --x 2>&1 | tail -2",
                             f"python3 {self.root}/scripts/kb_lint.py > /tmp/out.txt; grep -c x knowledge/company/y",
                             "t=1; python3 scripts/kb_lint.py; ls workspaces"], ceo)

    def test_every_write_form_stays_refused_beside_a_sweep(self):
        """Only python given an existing script file, whose words can't name or reach a held folder, may stand
        beside a read naming a parent; anything else keeps the full check."""
        read = "git status --short knowledge/"
        self.assertHeld({
            f"python3 scripts/kb_lint.py knowledge/board; {read}": "`python3` isn't a read",
            f"python3 scripts/kb_lint.py --dir=Knowledge; {read}": "`python3` isn't a read",
            f"python3 scripts/kb_lint.py ../board; {read}": "`python3` isn't a read",
            f"ls knowledge | python3 scripts/kb_lint.py": "`python3` isn't a read",
            f"{read} | python3 scripts/kb_lint.py": "`python3` isn't a read",
            "cd knowledge && python3 ../scripts/kb_lint.py": "`python3` isn't a read",
            f"python3 -c 'import shutil; shutil.rmtree(\"x\")'; {read}": "`python3` isn't a read",
            f"python3 -m kb_lint; {read}": "`python3` isn't a read",
            f"python3 - <<'EOF'\nimport os\nEOF\n{read}": "`python3` isn't a read",
            f"python3 scripts/kb_lint.py <<'EOF'\nknowledge/board\nEOF\n{read}": "`python3` isn't a read",
            f"python3 scripts/kb_lint.py <<< knowledge; {read}": "`python3` isn't a read",
            f"python3 scripts/kb_lint.py $x; {read}": "`python3` isn't a read",
            f"python3 scripts/kb_lint.py $_; {read}": "`python3` isn't a read",
            f"python3 scripts/kb_lint.py *; {read}": "`python3` isn't a read",
            f"python3 scripts/kb_lint.py {{a,b}}; {read}": "`python3` isn't a read",
            f"python3 scripts/kb_lint.py ~/x; {read}": "`python3` isn't a read",
            f"python3 scripts/kb_lint.py .; {read}": "`python3` isn't a read",
            f"python3 scripts/kb_lint.py {self.root}; {read}": "`python3` isn't a read",
            f"python3 scripts/kb_lint.py /; {read}": "`python3` isn't a read",
            f"python3 scripts/kb_lint.py > workspaces/x; {read}": "`python3` isn't a read",
            f"python3 scripts/nosuch.py; {read}": "`python3` isn't a read",
            f"python3 scripts/board_desk.py wait; {read}": "`python3` isn't a read",
            f"if {read}; then python3 scripts/kb_lint.py; fi": "`if` isn't a read",
            f"for f in x; do python3 scripts/kb_lint.py; done; {read}": "`python3` isn't a read",
            f"{read}; rm -rf /tmp/x": "`rm` isn't a read",
            f"{read}; hash ls=/bin/rm; ls -rf knowledge": "`hash` isn't a read",
            f"git config diff.external /bin/rm; python3 scripts/kb_lint.py; {read}": "`git config`",
            f"{read}; git reset --hard; python3 scripts/kb_lint.py": "`git reset`",
            f"ls knowledge/board/answers; python3 scripts/kb_lint.py": "`python3` isn't a read",  # the folder itself
            f"ls knowledge x(e:'true':); python3 scripts/kb_lint.py": "a zsh glob qualifier",
            f"f() {{ ls; }}; python3 scripts/kb_lint.py; {read}": "isn't a read",
            f"python3 scripts/kb_lint.py \"$(ls)\"; {read}": "hides what runs",
            f"python3 scripts/kb_lint.py; read -r f < /tmp/l; {read}": "`python3` isn't a read",
            f"PATH=x; python3 scripts/kb_lint.py; {read}": "`PATH` set",
            f"python3 scripts/board_desk.py read; {read}": "`python3` isn't a read"})
        self.assertIn("`board_desk.py read`", reason("python3 scripts/board_desk.py read; ls x", self.cwd) or "")


class CodeAndMoves(unittest.TestCase):
    """Zsh and shell forms that run code or move the folder, and text that only names a held folder."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, self.root)
        self.scr = Path(tempfile.mkdtemp()).resolve()  # a scratch folder outside the cwd, as an agent's scratchpad
        self.addCleanup(shutil.rmtree, self.scr)
        for folder in (".git", "knowledge/board/answers", "knowledge/company", "workspaces/board-desk", "scripts"):
            (self.root / folder).mkdir(parents=True)
        for script in ("kb_lint.py", "second_opinion.py", "other.py"):
            (self.root / "scripts" / script).write_text("pass\n")
        # this checkout's own copy
        own = self.root / "scripts" / "second_opinion.py"
        own.write_bytes(Path(desk.OPINION).read_bytes())
        patcher = mock.patch.object(desk, "OPINION", str(own))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.cwd = str(self.root)

    def assertHeld(self, cases, message="the Board's own answers"):
        for command, why in cases.items():
            with self.subTest(command=command):
                found = reason(command, self.cwd) or ""
                self.assertIn(message, found)
                self.assertIn(why, found)

    def assertPass(self, commands):
        for command in commands:
            for ceo in (False, True):
                with self.subTest(command=command, ceo=ceo):
                    self.assertIsNone(reason(command, self.cwd, ceo))

    def names(self, command, cwd=None):
        return desk.names_answers(desk.simple_commands(command), cwd or self.cwd)

    def test_a_glob_qualifier_after_an_equals_or_a_group_is_refused_whole(self):
        """Zsh reads `a=(e:...:)` and `--x=(e:...:)` in an argument as a qualifier, and after a glob group too; with a
        held folder named anywhere, the command is refused whole, with no second parse."""
        qualifier = "a zsh glob qualifier"
        self.assertHeld({
            "ls a=(e:'rm -rf knowledge':)": qualifier, "grep foo a=(e:'rm -rf knowledge':)": qualifier,
            "ls a=(+rmall) knowledge": qualifier, "ls --x=(e:'rm -rf knowledge':)": qualifier,
            "ls x(+f) knowledge": qualifier, "ls (foo|bar) a=(e:'rm -rf knowledge':)": qualifier,
            "ls (foo|bar) a=(e:x:) knowledge": qualifier, "ls x (foo|bar) a=(+f) knowledge": qualifier,
            "ls x (foo|bar) a=(+f) && cd knowledge": qualifier,
            "cd knowledge/company; ls .(e:true:)\nrm -rf ../board": qualifier,
            "cd knowledge/company; ls .(e:'rm -rf ../bo''ard':)": qualifier})
        self.assertEqual(desk.qualifier_codes("ls (foo|bar) a=(e:x:)"), ["x"])
        self.assertEqual(desk.qualifier_codes("ls x (foo|bar) a=(+f)"), ["f"])
        self.assertEqual(desk.qualifier_codes("ls --x=(e:y:)"), ["y"])
        self.assertEqual(desk.qualifier_codes("x=$(echo e) y=<(e) z=>(e)"), [])  # `$(`, `<(` and `>(` aren't qualifiers
        self.assertPass(["ls x(N) knowledge", "ls -d knowledge/board/answers/*", "git log --oneline -3 -- knowledge",
                         "ls (foo|bar) knowledge"])

    def test_a_folder_move_is_followed_or_refused(self):
        """Pushd, popd, zsh's chdir, and cd after builtin, command, noglob or nocorrect move the folder as cd does;
        `cd -`, `cd ~`, a variable or a modifier's option leaves it unknown."""
        for move in ("pushd", "chdir", "builtin cd", "command cd", "noglob cd", "nocorrect cd", "builtin pushd"):
            with self.subTest(move=move):
                self.assertTrue(self.names(f"{move} knowledge/company && rm -rf ../board"))
                self.assertIn("isn't a read", reason(f"{move} knowledge/company && rm -rf ../board", self.cwd) or "")
        self.assertTrue(self.names("pushd knowledge/company; pushd /tmp; popd; ls ../board"))
        self.assertFalse(self.names("pushd knowledge/company; popd; ls board"))  # back where it was
        self.assertFalse(self.names("pushd knowledge/company; pushd; ls ../board"))  # the two swapped
        for command in ("cd knowledge/company; cd -; ls board", "cd knowledge/company; cd ~; ls board",
                        "cd knowledge/company; popd; ls board", "cd knowledge/company; cd $D; ls board",
                        "cd knowledge/company; command -p cd x; ls board", "cd knowledge/company; cd a b; ls board",
                        "cd knowledge/company; cd +1; ls board", "cd knowledge/company; cd x*; ls board"):
            with self.subTest(command=command):
                self.assertTrue(self.names(command))  # unknown: `board` may be the held one
        self.assertHeld({"cd knowledge/company; cd -; rm -rf board": "`rm` isn't a read",
                         "pushd knowledge/company; popd; rm -rf knowledge": "`pushd` isn't a read"})
        for move in ("pushd", "chdir", "builtin cd", "command cd"):  # from a product repo, the main checkout
            with self.subTest(move=move):
                self.assertIn("the Board's own answers", reason(f"{move} {self.root} && git stash -u", str(self.scr)))
        self.assertPass(["cd knowledge/company && ls ../board/answers", "cd knowledge; ls board/answers"])

    def test_code_in_strings_is_read_as_code(self):
        """A shell's -c string, eval's, a zsh NAME[key]=value and ${(e)...} run code the check reads as text: its
        words name a held folder read from any folder; and a word the quotes split reads whole."""
        self.assertHeld({
            "bash -c 'rm -rf knowledge'": "`bash` isn't a read",
            "sh -c 'cd knowledge/company && rm -rf ../board'": "`sh` isn't a read",
            "zsh -c 'rm -rf know\"\"ledge'": "`zsh` isn't a read",
            "timeout 5 bash -c 'cd knowledge/company; rm -rf ../board'": "`timeout` isn't a read",
            "eval 'rm -rf knowledge'": "`eval` isn't a read",
            "eval 'cd knowledge/company'; rm -rf ../board": "`eval` isn't a read",
            "functions[ls]='rm -rf knowledge'; ls": "isn't a read",
            "aliases[x]='cd knowledge/company'\nx; rm -rf ../board": "isn't a read",
            "x='rm -rf knowledge'; echo ${(e)x}": "${(e)...}",
            "x='$(rm -rf knowledge)'; echo ${(e)x}": "hides what runs",
            "bash <<'EOF'\ncd knowledge/company; rm -rf ../board\nEOF": "`bash` isn't a read",
            "rm -rf kno''wledge": "`rm` isn't a read", "rm -rf know\\ledge": "`rm` isn't a read",
            "rm -rf \"knowledg\"e": "`rm` isn't a read"})
        self.assertTrue(self.names("eval 'cd knowledge/company'; ls ../board"))  # eval leaves the folder unknown
        self.assertPass(["bash -c 'echo hi'", "python3 -c 'print(1)'", "x='rm -rf /tmp/y'; echo ${(e)x}",
                         "python3 -c 'answers = 1; print(answers)'"])

    def test_text_written_to_a_scratch_file_passes_only_in_a_call_of_text_alone(self):
        """A `cat > <scratch>/cmds.txt <<'TXTEOF'` of `rm -rf ../board/answers`, and a printf of such text, pass in a
        call of printf, echo, cat or tee writing only outside the held folders; with another program in the call it
        gets the full check."""
        s, p, root, name = self.scr, "knowledge/board/answers", self.root, self.scr.name
        cmds4 = f"cat > {s}/cmds4.txt <<'TXTEOF'\nrm -rf ../board/answers\nTXTEOF"
        self.assertPass([cmds4, f"printf '%s\\n' 'rm -rf {p}' > {s}/a.txt",
                         f"echo '{p}' >> {s}/a.txt; printf x > /dev/null\ntee {s}/b.txt <<'EOF' >/dev/null\n{p}\nEOF"])
        self.assertHeld({cmds4 + "\npython3 scripts/kb_lint.py": "an output redirection"})
        make = f"printf 'all:\\n\\trm -rf {root}/{p}\\n' > {s}/Makefile; "
        make_cat = f"cat > {s}/Makefile <<'EOF'\nall:\n\trm -rf {root}/{p}\nEOF\n"
        run = f"printf 'rm -rf {root}/{p}' > {s}/a.sh; "
        run_cat = f"cat > {s}/a.sh <<'EOF'\nrm -rf {root}/{p}\nEOF\n"
        found = f"-maxdepth 9 -regex '.+/{name}/a.s.' | xargs sh"
        self.assertHeld({command: "an output redirection" for command in (
            make + f"make -C /Users -C ..{s}", make_cat + f"make -C /Users -C ..{s}",
            make + f"make -C /System/Volumes/Data -C {str(s)[1:]}",
            run + f"find -E /System/Volumes/Data {found}", run_cat + f"find -E /System {found}",
            run + f"cd /System/Volumes/Data && find -E . {found}",
            run_cat + f"cd /System/Volumes/Data && find -E . {found}",
            make + f"find -E /System/Volumes/Data -maxdepth 9 -regex '.+/{name}/Makefil.' -execdir make ';'",
            run + "grep -rl 'rm -rf' /System/Volumes | xargs sh", run_cat + "grep -rl 'rm -rf' /System/Volumes | xargs sh")})
        self.assertHeld({  # each keeps the full check
            f"python3 scripts/kb_lint.py; printf 'rm -rf {p}' > {s}/r.sh": "`python3` isn't a read",
            f"printf 'rm -rf {p}' > {s}/r.sh && sh {s}/r.sh": "an output redirection",
            f"printf 'rm -rf {p}' > {s}/r.sh | cat": "an output redirection",
            f"git commit -q --allow-empty -m 'rm -rf {p}' && git log -1 --format=%B | sh": "`sh` isn't a read"})

    def test_every_write_form_beside_held_text_is_refused(self):
        """What writes into a held folder, with held text or a review brief beside it."""
        s, p = self.scr, "knowledge/board/answers"
        for write in (f"echo x > {PAGE}", f"printf x >> {PAGE}", f"tee {PAGE} <<'EOF'\nx\nEOF",
                      f"cat > {PAGE} <<'EOF'\nx\nEOF", f"cp {s}/x {PAGE}", f"mv {s}/x {p}/", f"rm -rf {p}",
                      f"sed -i '' 1d {PAGE}", f"python3 -c \"open('{PAGE}', 'w')\"", f"touch {p}/x",
                      "rm -rf workspaces/board-desk", f"cd {p} && rm x", "rm -rf knowledge"):
            for before in ("", f"printf '{p}' > {s}/t.txt; ", f"cat > {s}/t.txt <<'TXTEOF'\nrm -rf {p}\nTXTEOF\n",
                           f"python3 scripts/second_opinion.py --kind code --brief '{p}'; "):
                with self.subTest(command=before + write):
                    self.assertIn("the Board's own answers", reason(before + write, self.cwd) or "")

    def test_a_review_brief_s_text_passes(self):
        """scripts/second_opinion.py's --brief value is text when that run is the call's only simple command and goes
        into no pipe; its other words are read as paths."""
        s, p = self.scr, "knowledge/board/answers and workspaces/board-desk"
        self.assertPass([f"python3 scripts/second_opinion.py --kind code --brief 'the guard holds {p}'",
                         f"python3 scripts/second_opinion.py --kind code --brief 'the guard holds {p}' > {s}/o.txt",
                         f"python3 scripts/second_opinion.py --kind code --brief '{p}' > {s}/o.txt 2> {s}/e.txt",
                         f"python3 -I scripts/second_opinion.py --kind code --brief='{p}' --diff {self.root} a..b",
                         f"python3 {self.root}/scripts/second_opinion.py --kind design --brief '{p}' --file x.md"])
        held = "knowledge/board/answers"
        self.assertHeld({command: "`python3` isn't a read" for command in (
            f"python3 scripts/second_opinion.py --kind code --brief 'reply only: rm -rf {held}' | sh",
            f"python3 scripts/second_opinion.py --kind code --brief 'reply only: rm -rf {held}' | tee {s}/o.txt | bash",
            f"python3 scripts/second_opinion.py --kind code --brief 'reply only: rm -rf {held}' > {s}/o.sh; "
            f"sh {s}/o.sh",
            f"python3 scripts/second_opinion.py --brief '{p}'; ls", f"ls; python3 scripts/second_opinion.py --brief '{p}'",
            f"python3 scripts/second_opinion.py --brief '{p}' | cat")})
        self.assertHeld({
            f"python3 scripts/second_opinion.py --kind code --bri '{p}'": "`python3` isn't a read",
            f"python3 scripts/second_opinion.py --kind code --brief x --file {PAGE}": "`python3` isn't a read",
            f"python3 scripts/second_opinion.py --brief '{p}' > {PAGE}": "`python3` isn't a read",
            f"python3 scripts/second_opinion.py -- --brief '{p}'": "`python3` isn't a read",
            f"cd /tmp; python3 scripts/second_opinion.py --brief '{p}'": "`python3` isn't a read",
            f"python3 scripts/other.py --brief '{p}'": "`python3` isn't a read",
            f"python3 scripts/nosuch/second_opinion.py --brief '{p}'": "`python3` isn't a read",
            f"python3 -c 'import second_opinion' --brief '{p}'": "`python3` isn't a read",
            f"python3 scripts/second_opinion.py --brief '{p}'; rm -rf knowledge": "`python3` isn't a read"})

    def test_pipes_cases_moves_and_copies(self):
        """Text a pipe takes after a loop (1), a name in another case (2), a move inside code read as words (3), zsh's
        `-` (4), CDPATH (5), another second_opinion.py (6), and joined lines and `$'...'` (7)."""
        s, p, big = self.scr, "knowledge/board/answers", str(self.scr).upper()
        self.assertHeld({command: "" for command in (
            f"while printf 'rm -rf {p}' > /dev/stdout > {s}/a.txt; do break; done | bash",  # 1: MULTIOS
            f"while printf 'rm -rf {p}' > {s}/a.txt >&2; do break; done 2>&1 | bash",
            f"if printf 'rm -rf {p}' > {s}/a.txt >&2; then :; fi 2>&1 | zsh",
            f"for i in 1; do printf 'rm -rf {p}' > {s}/a.txt >&2; done 2>&1 | sh",
            f"while printf 'rm -rf {p}' 3>{s}/a.txt; do break; done | bash",
            f"while printf 'rm -rf {p}' <>{s}/a.txt; do break; done | bash",
            f"while printf 'rm -rf {p}' {{fd}}>{s}/a.txt; do break; done | bash",
            f"{{ tee {s}/a.txt <<'EOF'\nrm -rf {p}\nEOF\n}} | bash",
            f"printf '{p}/w.md' > {s}/list; xargs rm < {big}/LIST",  # 2: macOS's disk reads any case
            f"printf 'rm -rf {p}' > {s}/x.sh; bash {s}/X.SH",
            f"cat > {s}/y.sh <<'EOF'\nrm -rf {p}\nEOF\nzsh {big}/Y.SH",
            f"printf 'all:\\n\\trm -rf {p}\\n' > {s}/Makefile; cd {big}; make",
            "bash -c 'cd knowledge/company && rm -rf ..'",  # 3: a move inside code read as words
            "eval 'cd knowledge/company; rm -rf ..'", "bash <<'EOF'\ncd knowledge/company\nrm -rf ..\nEOF",
            "timeout 5 sh -c 'cd knowledge/company; rm -rf ..'", "ls .(e:'cd knowledge/company':); rm -rf ..",
            f"bash -c 'cd {self.root}/knowledge/company && rm -rf ..'",
            "- cd knowledge/company; rm -rf ../board",  # 4
            "CDPATH=knowledge; cd board; rm -rf answers", "export CDPATH=knowledge; cd board; rm -rf answers")})  # 5
        self.assertTrue(self.names("- cd knowledge/company; ls ../board"))
        self.assertFalse(self.names("cd knowledge/company; cd ./x; ls board"))
        with mock.patch.dict(os.environ, {"CDPATH": str(self.root / "knowledge")}):
            self.assertTrue(self.names("cd board; ls answers"))
            self.assertFalse(self.names("cd ./scripts; ls answers"))
        (self.scr / "scripts").mkdir()  # 6: a second_opinion.py of other bytes isn't the checkout's
        (self.scr / "scripts" / "second_opinion.py").write_text("import sys; print(sys.argv)\n")
        self.assertHeld({f"python3 {s}/scripts/second_opinion.py --brief '{p}'": "`python3` isn't a read"})
        (self.scr / "wt" / "scripts").mkdir(parents=True)  # a linked worktree's copy of the same bytes is
        (self.scr / "wt" / "scripts" / "second_opinion.py").write_bytes(Path(desk.OPINION).read_bytes())
        (self.root / ".git" / "worktrees" / "wt").mkdir(parents=True)
        (self.root / ".git" / "worktrees" / "wt" / "gitdir").write_text(f"{s}/wt/.git\n")
        (self.scr / "wt" / ".git").write_text(f"gitdir: {self.root}/.git/worktrees/wt\n")
        self.assertPass([f"python3 {s}/wt/scripts/second_opinion.py --brief '{p}'",
                         f"printf '%s\\n' 'rm -rf {p}' > {s}/a.txt 2>/dev/null",
                         f"tee {s}/b.txt > /dev/null <<'EOF'\n{p}\nEOF"])
        self.assertHeld({"rm -rf kno\\\nwledge": "`rm` isn't a read",  # 7: the pre-check reads joined lines
                         "rm -rf $'\\x6bnowledge'": "`rm` isn't a read"})  # and a `$'...'` whole

    def test_other_spellings_operands_and_links(self):
        """The same scratch file or folder by another spelling or on disk, the words that feed shell code (2), a
        second_opinion.py beside other code (3) and CDABLE_VARS (4)."""
        s, p = self.scr, "knowledge/board/answers"
        make = f"printf 'all:\\n\\trm -rf {self.root}/{p}\\n' > {s}/Makefile; "
        nfc, nfd = "café", "café"
        (self.scr / nfc).mkdir()
        (self.scr / "x.sh").write_text("")  # a hard link made in an earlier call
        os.link(self.scr / "x.sh", self.scr / "h")
        cases = [f"printf 'rm -rf {p}' > {s}/{nfc}.sh; bash {s}/{nfd}.sh",
                 f"printf 'all:\\n\\trm -rf {p}\\n' > {s}/{nfc}/Makefile; cd {s}/{nfd}; make",
                 f"printf 'rm -rf {p}' > {s}/x.sh; bash {s}/h"]
        data = Path("/System/Volumes/Data" + str(self.scr))
        if data.is_dir() and os.path.samefile(data, self.scr):  # macOS's firmlink to the same folder
            cases += [make + f"cd {data}; make", make + f"make -C {data}"]
        self.assertHeld({command: "" for command in cases + [
            "sh -c 'cd \"$1\"; rm -rf ..' _ knowledge/company",  # 2: the words that feed the code
            "bash -c 'cd \"$@\" && rm -rf ..' x knowledge/company",
            "bash -s knowledge/company <<'EOF'\ncd \"$1\"; rm -rf ..\nEOF",
            "x=knowledge/company; eval 'cd $x; rm -rf ..'",
            "export X=knowledge/company; bash -c 'cd $X; rm -rf ..'",
            "find . -maxdepth 0 -exec sh -c 'cd knowledge/company; rm -rf ..' \\;",
            "script -q /dev/null sh -c 'cd knowledge/company; rm -rf ..'",
            "setopt cdablevars; x=knowledge/board; cd x; rm -rf answers",  # 4, in zsh's spellings
            "setopt CD_ABLE_VARS; x=knowledge/board; cd x; rm -rf answers",
            "set -T; x=knowledge/board; cd x; rm -rf answers"]})
        for at, link in (("x", None), ("fake", f"gitdir: {self.root}/.git/worktrees/fake\n")):  # 3
            (self.scr / at / "scripts").mkdir(parents=True)
            (self.scr / at / "scripts" / "second_opinion.py").write_bytes(Path(desk.OPINION).read_bytes())
            if link:  # a .git file with no gitdir back-link in this checkout's .git/worktrees/
                (self.scr / at / ".git").write_text(link)
            self.assertHeld({f"python3 {s}/{at}/scripts/second_opinion.py --brief '{p}'": "`python3` isn't a read"})
        self.assertPass([f"printf '%s\\n' 'rm -rf {p}' > {s}/{nfc}.txt", "bash -c 'echo hi'", "cd scripts; ls"])

    def test_the_words_that_feed_an_interpreter_s_code_or_a_sourced_file(self):
        """Python's -c code, perl's -e or -E, node's -e or
        --eval and ruby's -e take the command's other words (sys.argv, @ARGV, process.argv, ARGV), and so do a file
        source or `.` runs, and code an interpreter reads as `-`; a word with a held folder's part then names one.
        A word that may name one does (`../board` in the code); an interpreter's code given a word with a held part does
        too."""
        rm = "os.chdir(sys.argv[1]); shutil.rmtree(\"../board\")"
        self.assertHeld({command: "isn't a read" for command in (
            f"python3 -c 'import os,sys,shutil; {rm}' knowledge/company",
            "perl -e 'chdir $ARGV[0]; system(\"rm\", \"-rf\", \"../board\")' knowledge/company",
            "node -e 'process.chdir(process.argv[1]); require(\"fs\").rmSync(\"../board\", {recursive: true})' "
            "knowledge/company",
            "perl -E 'chdir $ARGV[0]; system(\"rm -rf ../board\")' knowledge/company",
            "perl -lE 'chdir $ARGV[0]; system(\"rm -rf ../board\")' knowledge/company",
            "ruby -e 'Dir.chdir(ARGV[0]); system(\"rm -rf ../board\")' knowledge/company",
            f"x=knowledge/company; python3 -c 'import os,sys,shutil; {rm}' $x",
            "timeout 5 python3 -c 'import os,sys,shutil; os.chdir(sys.argv[1]); shutil.rmtree(\"..\")' "
            "knowledge/company",
            "python3 - knowledge/company <<'EOF'\nimport os,sys,shutil; os.chdir(sys.argv[1]); shutil.rmtree('..')\n"
            "EOF", "python3 - <<'EOF'\nimport shutil; shutil.rmtree('knowledge/board')\nEOF")})
        self.assertHeld({command: "" for command in (
            f"source {self.scr}/x.sh knowledge/board", f". {self.scr}/x.sh ../board",
            "x=knowledge/company; builtin eval 'cd $x; rm -rf ..'",
            "x=knowledge/company; builtin eval 'cd $x'",  # a cd the shell builds
            "node --eval 'process.chdir(process.argv[1])' knowledge/company",  # a folder move
            "timeout 5 python3 -c 'import os,sys; os.chdir(sys.argv[1])' knowledge/company",
            "python3 - knowledge/company <<'EOF'\nimport os,sys,shutil; os.chdir(sys.argv[1])\nEOF")})
        self.assertPass(["python3 -c 'print(1)'", "python3 -c 'import sys; print(sys.argv)' scripts/x.py",
                         "python3 -c 'answers = 1; board = 2' scripts/x.py", "node -e 'const board = 1'",
                         "perl -e 'print 1'", f"source {self.scr}/x.sh", "python3 scripts/kb_lint.py knowledge/company",
                         "python3 -E scripts/kb_lint.py knowledge/company",
                         f"source {self.scr}/x.sh knowledge/company", f". {self.scr}/x.sh knowledge/company",
                         f"builtin source {self.scr}/x.sh knowledge/company"])


class NamesNearby(unittest.TestCase):
    """Commands that only name a folder near a held one, or name one in text, pass; the write forms stay refused."""

    setUp, assertHeld = CodeAndMoves.setUp, CodeAndMoves.assertHeld

    def assertPass(self, commands, cwd=None):
        for command in commands:
            for ceo in (False, True):
                with self.subTest(command=command, ceo=ceo):
                    self.assertIsNone(reason(command, cwd or self.cwd, ceo))

    def product(self):
        wt = self.root / "workspaces" / "acme" / ".worktrees" / "wt"
        (wt / "scripts").mkdir(parents=True)
        return wt

    def test_plain_work_near_the_folders_passes(self):
        """Test runs, notes and messages in a product worktree under workspaces/."""
        wt, s, held = self.product(), self.scr, "knowledge/board/answers/ and workspaces/board-desk/"
        block = f"Blocked: {held} hold the Board’s answers; only scripts/board_desk.py writes them. Here: `python3`."
        tests = "apps/web/test/a.test.ts apps/web/test/b.test.ts"
        run = (f"ACME_TEST_DATABASE_URL=postgres://localhost:5432/acme_test "
               f"ACME_TEST_RUN_OWNER=\"senior T-3\" timeout 170 sh scripts/run-db.sh run pg 5432 -- bun "
               f"test --timeout 30000 {tests}")
        cq = f"{self.root}/workspaces/acme/content/orders/D-x/2/ceo-questions.md"
        self.assertPass([
            f"cd {wt} && S={s}/s-t3; {run} > $S/run-1.log 2>&1; echo $? > $S/run-1.rc; tail -30 $S/run-1.log | cut "
            "-c1-220",
            f"cd {wt} && sp={s}/s-t3; {run.replace('timeout 170 ', '')} > $sp/run-1.log 2>&1",
            f"cd {wt} && sh scripts/run-db.sh run pg 5432 -- bun test packages/db/test/a.test.ts",
            f"echo 'BLOCKED: the hook said \"{block}\"' >> {cq}; echo rc=$?; date -u",
            f"echo \"NEEDS-CEO-NOW $(date -u +%Y-%m-%dT%H:%M:%SZ): {block.replace('`', '')}\" >> {cq}; wc -l {cq}",
            f"printf '%s\\n' \"| $(date -u +%H:%MZ) | the Board's word, {held} |\" > {s}/rows.txt",
            f"cat > {self.root}/workspaces/acme/content/reviews/ux.md <<'EOF'\n{held}\nEOF",
            f"S={s}/s-t3; rm \"$S/notes.md\"", f"cd {wt} && sh scripts/run-db.sh down pg", "S=/x; ls $S"])
        # an interpreter's code keeps the broad held-part rule
        self.assertHeld({command: "`python3` isn't a read" for command in (
            f"cd {self.root}/workspaces/acme && python3 -I -c '\nimport subprocess\n"
            "req = \"https://api.github.com/repos/o/r/actions/jobs/1/logs\"\nprint(\"mode=\", \"cause:\")\n'",
            f"M={self.root}/workspaces/acme/content/orders/D-x/2/measure; python3 -I - "
            "\"$M/today.csv\" <<'EOF'\nimport csv, sys\nprint(len(list(csv.reader(open(sys.argv[1])))))\nEOF",
            f"python3 - knowledge/company/board-desk/asks.md {s}/asks.txt <<'EOF'\nimport sys\np = sys.argv[1]\n"
            "open(p, 'a').write(open(sys.argv[2]).read())\nEOF\npython3 scripts/kb_lint.py 2>&1 | tail -3",
            "python3 - knowledge/finance/spend.md <<'EOF'\nimport sys\np = sys.argv[1]\nt = open(p).read()\n"
            "open(p, 'w').write(t.replace('| a |', '| b |'))\nEOF")})
        self.assertPass([f"gh pr create --base main --title 'T-3+T-4' --body 'The guard: {block}'",
                         f"gh pr create -t \"T-3\" -b \"{block.replace('`', '')}\" --draft",
                         f"gh pr comment 12 --body='{block}'", f"gh issue create --title x --body '{held}'"], str(wt))

    def test_a_variable_is_refused_only_when_the_shell_or_a_later_program_reads_it(self):
        """Not for being upper-case. The shell's own (SPECIAL: bash(1), zshparam(1)) and an exported one stay
        refused, beside a held folder."""
        self.assertPass(["S=/x; ls $S", "S=knowledge/company; ls $S knowledge", "for M in a b; do ls knowledge; done",
                         "read -r S <<< x; ls knowledge", "printf -v S %s x; ls knowledge"])
        self.assertHeld({f"{name}=/tmp/x; ls knowledge": f"`{name}` set for the commands after it" for name in (
            "PATH", "IFS", "CDPATH", "HOME", "ENV", "BASH_ENV", "ZDOTDIR", "PWD", "OLDPWD", "TMPDIR", "TMPPREFIX",
            "EXECIGNORE", "GLOBIGNORE", "SHELLOPTS", "POSIXLY_CORRECT", "path", "commands")})
        self.assertHeld({"for TMPPREFIX in knowledge/board/answers/x; do cat <<EOF\nx\nEOF\ndone": "`TMPPREFIX` set",
                         "S=/x; rm -rf knowledge/board/answers": "`rm` isn't a read",
                         "GIT_TRACE=knowledge/board/answers/x git status": "`GIT_TRACE` set for `git`"})
        with mock.patch.dict(os.environ, {"EXPORTED_X": "1"}):
            self.assertHeld({"for EXPORTED_X in a; do ls knowledge; done": "`EXPORTED_X` set",
                             "EXPORTED_X=a; ls knowledge": "the environment exports it"})

    def test_code_and_its_words_name_a_held_folder_only_by_a_word_that_may_name_one(self):
        """A word with a held part in some other path (`workspaces/<product>`, `knowledge/company`) doesn't
        refuse shell code or its runner (an interpreter's code it does); a word that may
        name one, read from any folder, does, and so does such a word beside a climb (`..`)."""
        wt = self.product()
        self.assertPass([f"cd {wt} && bash -c 'bun test apps/web'", f"cd {wt} && sh scripts/x.sh knowledge/company",
                         "bash -c 'cat knowledge/company/x.md'",
                         "bash <<'EOF'\nls workspaces/system\nEOF", "eval 'ls knowledge/company'",
                         "python3 - <<'EOF'\np = 'knowledge/company/board-desk/asks.md'\nEOF",
                         "node -e 'require(\"fs\").rmSync(\"apps/board\", {recursive: true})'"])
        self.assertHeld({command: "isn't a read" for command in (
            # a worktree a `cd` moves into, beside code that names no held part
            f"cd {wt} && python3 -c 'import shutil; shutil.rmtree(\"/tmp/x\")'",
            "bash -c 'rm -rf knowledge'", "sh -c 'rm -rf board/answers'", "sh -c 'rm -rf ../board-desk'",
            "bash -c 'rm -rf x/knowledge/board'", f"bash -c 'rm -rf {self.root}/knowledge/board'",
            "sh -c 'cd \"$1\"; rm -rf ..' _ knowledge/company", f"cd {wt} && sh -c 'rm -rf ../../..'",
            f"bash -c 'cd {self.root}/workspaces/acme && rm -rf ..'",
            "python3 -c 'import shutil; shutil.rmtree(\"knowledge/board\")'",
            "node -e 'require(\"fs\").rmSync(\"workspaces/board-desk\", {recursive: true})'",
            "bash -s knowledge/company <<'EOF'\ncd \"$1\"; rm -rf ..\nEOF", "sh -c 'ls \"$1\"' _ workspaces/system",
            "python3 - <<'EOF'\nimport shutil; shutil.rmtree('../board/answers')\nEOF")})

    def test_text_is_text_and_a_substitution_is_what_runs(self):
        """A PR body, an echo'd line and a `$(date ...)` beside held words pass; a substitution that runs
        board_desk.py, by any quote, stays refused, in an unquoted heredoc's body too."""
        s, held = self.scr, "knowledge/board/answers"
        self.assertPass([f"echo 'scripts/board_desk.py writes them; `python3` here' >> {s}/q.md",
                         f"echo \"$(date -u +%F) {held}\" >> {s}/q.md", f"printf '%s' \"$( date )\" '{held}' > {s}/q",
                         f"git commit -m \"$(date -u +%F): {held}\"",
                         f"cat > {s}/q <<EOF\n$(date -u) {held}\nEOF"])
        self.assertHeld({  # a substitution of anything else, or a date given another word
            f"echo \"$(date -r {held}/x)\" > {s}/q": "hides what runs",
            f"echo \"$(date; rm -rf {held})\" > {s}/q": "hides what runs",
            f"echo \"$(date -u)\" > {held}/x.md": "`$(` hides what runs",
            f"echo \"$(date -u)\" | tee {held}/x.md": "`$(` hides what runs"})
        self.assertHeld({command: "a run of it in a substitution" for command in (
            "echo \"$(python3 scripts/board_desk.py hour)\"", "echo 'x' \"`python3 scripts/board_desk.py day`\"",
            f"cat > {s}/q <<EOF\n$(python3 scripts/board_desk.py read)\nEOF")}, "board_desk.py's run, hour, day and read")
        self.assertHeld({"echo $(echo $(python3 scripts/board_desk.py run))": "`board_desk.py run`"}, "board_desk.py's run, hour, day and read")
        self.assertPass(["echo '$(python3 scripts/board_desk.py hour)'",
                         f"cat > {s}/q <<'EOF'\n$(python3 scripts/board_desk.py read)\nEOF"])
        wt = str(self.product())
        for command, why in {f"gh pr create -e --body '{held}'": "`gh` isn't a read",
                             f"gh pr create --body '{held}' | sh": "`gh` isn't a read",
                             f"gh pr create --body '{held}'; rm -rf /tmp/x": "`gh` isn't a read",
                             f"gh pr create -db '{held}'": "`gh` isn't a read",
                             f"gh pr create --body x --body-file {self.root}/{held}/x.md": "`gh` isn't a read",
                             f"gh pr create --body x > {self.root}/{held}/x.md": "`gh` isn't a read",
                             f"gh pr checkout 1 --body '{held}'": "`gh` isn't a read",
                             f"GH_EDITOR=x gh pr create --body '{held}'": "isn't a read"}.items():
            with self.subTest(command=command):
                self.assertIn(why, reason(command, wt) or "")

    def test_the_ceo_s_row_helper_passes_whatever_its_rows_say(self):
        """scripts/status_log.py, this checkout's own copy, given rows on standard input or in a file; its words
        are read as paths, so a held page given to it stays refused."""
        own = self.root / "scripts" / "status_log.py"
        own.write_bytes(Path(desk.STATUS_LOG).read_bytes())
        patcher = mock.patch.object(desk, "STATUS_LOG", str(own))
        patcher.start()
        self.addCleanup(patcher.stop)
        s, held, page = self.scr, "knowledge/board/answers", "knowledge/board/directives/D-x.md"
        rows = f"| 22:58Z | the Board's yes, {held}/2026-W02.md; `$(date)`, board_desk.py hour, keychain_token() |"
        self.assertPass([f"python3 scripts/status_log.py {page} - <<'EOF'\n{rows}\nEOF",
                         f"python3 -I scripts/status_log.py {page} {s}/rows.txt",
                         f"cat > {s}/rows.txt <<'EOF'\n{rows}\nEOF\npython3 scripts/status_log.py {page} {s}/rows.txt",
                         f"python3 workspaces/system/log.py {page} {s}/rows.txt"])
        self.assertHeld({command: "`$(` hides what runs" for command in (
            f"python3 scripts/status_log.py {held}/2026-W02.md - <<'EOF'\n{rows}\nEOF",
            f"python3 scripts/status_log.py {page} - <<'EOF'\n{rows}\nEOF\nrm -rf /tmp/x",
            f"python3 scripts/status_log.py {page} - <<'EOF' | sh\n{rows}\nEOF",
            f"python3 scripts/other.py {page} - <<'EOF'\n{rows}\nEOF")})
        (self.scr / "scripts").mkdir()  # a status_log.py of other bytes isn't the checkout's
        (self.scr / "scripts" / "status_log.py").write_text("import sys; print(sys.argv)\n")
        self.assertHeld({f"python3 {s}/scripts/status_log.py {page} - <<'EOF'\n{rows}\nEOF": "`$(` hides what runs"})

    def test_the_row_helper_s_unquoted_heredoc_is_still_code(self):
        """Only a quoted heredoc's rows are text; an unquoted one's `$(` runs, so a word in it that may name a held
        folder still refuses."""
        own = self.root / "scripts" / "status_log.py"
        own.write_bytes(Path(desk.STATUS_LOG).read_bytes())
        patcher = mock.patch.object(desk, "STATUS_LOG", str(own))
        patcher.start()
        self.addCleanup(patcher.stop)
        page = "knowledge/board/directives/D-x.md"
        for command in (f"python3 scripts/status_log.py {page} - <<EOF\n$(cd knowledge/board; rm -rf answers)\nEOF",
                        f"python3 scripts/status_log.py {page} - <<EOF\n`cd knowledge/board; rm -rf answers`\nEOF"):
            with self.subTest(command=command):
                self.assertIn("the Board's own answers", reason(command, self.cwd, True) or "")
        self.assertIsNone(reason(f"python3 scripts/status_log.py {page} - <<'EOF'\n$(cd knowledge/board)\nEOF",
                                 self.cwd, True))

    def test_globs_built_paths_names_and_substitutions(self):
        """A glob or a path the code builds in its text names a held folder,
        the row helper takes only plain files (3), the names the shell reads or a read program runs by (4, 6), and a
        run past a substitution's quoted `)` or case pattern (5); what only names one still passes."""
        own = self.root / "scripts" / "status_log.py"
        own.write_bytes(Path(desk.STATUS_LOG).read_bytes())
        patcher = mock.patch.object(desk, "STATUS_LOG", str(own))
        patcher.start()
        self.addCleanup(patcher.stop)
        run, rows = "python3 scripts/board_desk.py run", "- <<'EOF'\n| x |\nEOF"
        self.assertHeld({command: "isn't a read" for command in (
            "bash -c 'rm -rf knowledge/boar[d]'", "bash -c 'rm -rf knowledge/b*'", "sh -c 'rm -rf */answers'",
            "bash -c 'cd knowledge/company && rm -rf \"${PWD%/*}/board\"'", "bash -c 'rm -rf \"$PWD\"/board'",
            "bash -c 'rm -rf $PWD/board-desk'", f"python3 scripts/status_log.py knowledge/board/answer?/x.md {rows}",
            f"python3 scripts/status_log.py knowledge/board/{{answers,x}}/x.md {rows}")})
        self.assertHeld({"sh -c 'cd knowledge/company; rm -rf \"$(dirname \"$PWD\")/board\"'": ""})
        self.assertHeld({f"{name}=/tmp/x; ls knowledge": f"`{name}` set" for name in (
            "MODULE_PATH", "PROMPT4", "BASH_CMDS", "BASH_ALIASES", "HISTFILE", "GIT_EDITOR", "GIT_DIR", "PAGER",
            "XDG_CONFIG_HOME", "LESSOPEN")})
        self.assertHeld({command: "a run of it in a substitution" for command in (
            f"echo \"$(echo \")\"; {run})\"", f"echo \"$(case x in x) {run};; esac)\"",
            f"cat > {self.scr}/q <<EOF\n'$({run})'\nEOF")}, "board_desk.py's run, hour, day and read")
        self.assertHeld({"bash -c 'cat knowledge/company/*.md'": "isn't a read"})  # a glob in code
        self.assertPass(["bash -c 'ls apps/*'", "sh -c 'rm -f \"$S\"/*.log' _",
                         "bash -c 'cd \"$1\" && bun test' _ apps/web", "bash -c 'rm -rf \"$PWD\"/dist'",
                         f"echo \"only scripts/board_desk.py writes them, $(date -u +%F)\" >> {self.scr}/q.md",
                         f"python3 scripts/status_log.py knowledge/board/directives/D-x.md {rows}"])

    def test_a_word_the_shell_builds_in_code_names_a_held_folder_by_a_part(self):
        """A word that a `$`, backquote or brace joins to more text in shell
        code, the value set to a variable it joins, and, when it joins an operand, every word, name one by a held
        part; the command's own words don't, but given to an interpreter's code they do (`M=<path>;
        python3 - "$M/x.csv"`)."""
        self.assertHeld({command: "" for command in (
            "bash -c 'rm -rf knowledge/boa${x}rd'", "bash -c 'rm -rf {know,x}ledge/board'",
            "bash -c 'x=oard; rm -rf knowledge/b$x'", "sh -c 'rm -rf \"$1\"ard' _ knowledge/bo",
            "bash -c 'rm -rf knowledge/boar${y:-d}'", "bash -c 'a=knowledge/boar; rm -rf ${a}d'",
            "sh -c 'rm -rf \"$1$2\"' _ knowledge/bo ard", "bash -c 'rm -rf knowledge/boar$(printf d)'",
            "a=knowledge/boar bash -c 'rm -rf ${a}d'")})
        m = f"{self.root}/workspaces/acme/content/orders/D-x/2/measure"
        self.assertHeld({f"M={m}; python3 -I - \"$M/today.csv\" <<'EOF'\nprint(1)\nEOF": ""})
        self.assertPass(["bash -c 'rm -rf \"$TMPDIR\"/x'", "sh -c 'cd \"$1\" && rm -rf node_modules/*' _ apps/web",
                         "bash -c 'rm -rf \"$1\"/*.log' _ /tmp/x", "bash -c 'rm -rf apps/*/dist'"])

    def test_a_folder_move_the_shell_builds_is_a_climb(self):
        """A cd or pushd whose operand the shell builds (a `$`, a
        substitution, a backquote, `~`, zsh's `:h` or a glob qualifier) may climb, as `..` does, so a word with a held
        part beside it refuses; a held page given plain rows is refused at the page."""
        up, dn = "\"${PWD%/*}\"", "\"$(dirname \"$PWD\")\""
        self.assertHeld({command: "" for command in (
            f"bash -c 'cd knowledge/company && cd {up} && rm -rf b*'",
            f"bash -c 'cd knowledge/company && cd {dn} && rm -rf b*'",
            f"eval 'cd knowledge/company && cd {up} && rm -rf b*'",
            f"bash <<EOF\ncd knowledge/company && cd {up} && rm -rf b*\nEOF",
            f"bash <<'EOF'\ncd knowledge/company && cd {up} && rm -rf b*\nEOF",
            "zsh -c 'cd knowledge/company && cd $PWD:h && rm -rf b*'",
            "zsh -c 'cd knowledge/company && cd .(:h) && rm -rf b*'",
            f"bash -c 'cd knowledge/company && cd {up} && rm -rf boar[d]'",
            f"bash -c 'cd workspaces/system && cd {up} && rm -rf board-d*'",
            "bash -c 'cd knowledge/company && cd `dirname $PWD` && rm -rf b*'",
            f"sh -c 'cd \"$1\" && cd {up} && rm -rf b*' _ knowledge/company",
            f"bash -c 'pushd knowledge/company && pushd {up} && rm -rf b*'",
            "bash -c 'cd knowledge/company && cd /tmp && cd ~-/.. && rm -rf b*'",
            f"bash -c 'cd {self.root}/knowledge/company && cd {up} && rm -rf b*'")})
        self.assertPass(["sh -c 'cd \"$1\" && rm -rf node_modules/*' _ apps/web",
                         "bash -c 'cd \"$(git rev-parse --show-toplevel)\" && bun test apps/web'",
                         "bash -c 'cd ~/tools && ls'", "sh -c 'cd \"${TMPDIR:-/tmp}\" && rm -f x.log'"])
        own = self.root / "scripts" / "status_log.py"
        own.write_bytes(Path(desk.STATUS_LOG).read_bytes())
        patcher = mock.patch.object(desk, "STATUS_LOG", str(own))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.assertHeld({command: "`python3` isn't a read" for command in (
            "python3 scripts/status_log.py knowledge/board/answers/2026-W02.md - <<'EOF'\n| 22:58Z | a row |\nEOF",
            f"python3 scripts/status_log.py knowledge/board/answers/2026-W02.md {self.scr}/rows.txt",
            "python3 scripts/status_log.py workspaces/board-desk/state.md - <<'EOF'\n| 22:58Z | a row |\nEOF")})

    def test_risky_code_keeps_the_broad_held_part_rule(self):
        """Code with a `$`, a backquote, a glob, a folder move (`cd -`, zsh's two-operand
        cd, one run by a variable), a name the moves read or a command word the shell builds refuses beside any word
        with a held part; an absolute word with a glob is matched as a relative one."""
        up = "\"${PWD%/*}\""
        self.assertHeld({command: "" for command in (
            f"bash -c 'cd knowledge/company && OLDPWD={up} && cd - && rm -rf b*'",
            f"bash -c 'c=cd; cd knowledge/company && $c {up} && rm -rf b*'",
            "zsh -c 'cd knowledge/company && cd /company \"\" && rm -rf b*'",
            f"bash -c 'rm -rf {self.root}/knowledge/boar[d]'", f"bash -c 'rm -rf {self.root}/knowledge/b*'",
            f"bash -c 'ls knowledge/company; cd {self.root}/kn*; rm -rf b*'",
            f"bash -c 'cd knowledge/company && x=cd && $x {up} && rm -rf b*'",
            "bash -c 'cd knowledge/company && {c,}d .. && rm -rf b*'", "bash -c 'cd workspaces/system && ls'")})
        self.assertPass(["bash -c 'cd /tmp && cd \"${PWD%/*}\" && ls'", "bash -c 'cat knowledge/company/x.md'",
                         "sh -c 'rm -f \"$S\"/*.log' _", f"bash -c 'rm -rf {self.scr}/x/*.log'"])

    def test_every_write_form_stays_refused(self):
        """Writes, deletes and moves under the two folders, by plain commands, code, runners and text beside
        them, and reads of the token."""
        wt, s, p = self.product(), self.scr, "knowledge/board/answers"
        for command in (
                f"rm -rf {p}", "rm -f workspaces/board-desk/notion.json", f"echo x >> {p}/x.md", f"printf x > {p}/x",
                f"tee -a {p}/x < /tmp/x", f"cp /tmp/x {p}/x", f"mv {p}/x /tmp/x", f"sed -i '' s/a/b/ {p}/x",
                f"touch {p}/x", f"python3 -c \"open('{p}/x','a')\"", "bash -c 'rm -rf knowledge'",
                "sh -c 'cd knowledge/company && rm -rf ..'", "x=knowledge/company; eval 'cd $x; rm -rf ..'",
                "cd knowledge/board && rm -rf answers", "cd knowledge/company; rm -rf ../board",
                f"cd {wt} && rm -rf ../../../board-desk", "git stash -u", "git clean -fdx", f"git checkout -- {p}",
                f"find {p} -delete", f"ls {p}/x | xargs rm", f"cat $(rm {p}/x)", f"S={s}; rm -rf {p}",
                f"for TMPDIR in {p}; do sort -S 1K knowledge/company/y.md; done", f"echo \"$(date)\" > {p}/x",
                f"cd {wt} && timeout 170 sh -c 'rm -rf {self.root}/{p}'",
                f"sp={s}; cd knowledge/board && rm -rf answers",
                "python3 - <<'EOF'\nimport shutil\nshutil.rmtree('workspaces/board-desk')\nEOF",
                f"cd {self.root}/knowledge/company && python3 -c 'import shutil; shutil.rmtree(\"..\")'",
                f"gh pr create --body '{p}' && rm -rf {p}", f"printf '{p}' > {s}/a.sh; sh {s}/a.sh"):
            with self.subTest(command=command):
                self.assertIn("the Board's own answers", reason(command, self.cwd) or "")
        for command in ("security find-generic-password -s board-desk-notion -w", "python3 scripts/board_desk.py read",
                        "python3 -c 'from adapter_notion import keychain_token; keychain_token()'"):
            with self.subTest(command=command):
                self.assertIsNotNone(reason(command, self.cwd))

    def test_an_interpreter_s_code_keeps_the_broad_held_part_rule(self):
        """An interpreter's code (python, node, perl, ruby; -c, -e, a heredoc) refuses
        beside any word it is given with a held part, whatever it does with the word (dirname, .parent, pardir, split, a
        glob, os.environ, a shell call)."""
        self.assertHeld({command: "" for command in (
            "python3 - knowledge/company <<'EOF'\nimport sys, os, shutil\n"
            "shutil.rmtree(os.path.join(os.path.dirname(sys.argv[1]), 'board'))\nEOF",
            r"""python3 -c 'import sys,os,shutil; shutil.rmtree(os.path.dirname(sys.argv[1]) + "/board")'"""
            " knowledge/company",
            r"""python3 -c 'import sys,shutil; from pathlib import Path;"""
            r""" shutil.rmtree(Path(sys.argv[1]).parent / "board")' knowledge/company""",
            r"""python3 -c 'import sys,shutil,glob,os;"""
            r""" [shutil.rmtree(p) for p in glob.glob(os.path.dirname(sys.argv[1]) + "/b*")]' knowledge/company""",
            r"""K=knowledge/company python3 -c 'import os,shutil;"""
            r""" shutil.rmtree(os.path.dirname(os.environ["K"]) + "/board")'""",
            r"""K=knowledge/company python3 -c 'import os; os.system("rm -rf \"$(dirname \"$K\")\"/b*")'""",
            r"""node -e 'const fs=require("fs"),p=require("path");"""
            r""" fs.rmSync(p.join(p.dirname(process.argv[1]), "board"), {recursive: true})' knowledge/company""",
            r"""perl -MFile::Path=rmtree -MFile::Basename -e 'rmtree(dirname($ARGV[0]) . "/board")'"""
            " knowledge/company",
            "python3 - workspaces/system <<'EOF'\nimport sys, os, shutil\n"
            "shutil.rmtree(os.path.join(os.path.dirname(sys.argv[1]), 'board-desk'))\nEOF",
            r"""python3 -c 'import sys,os; open(os.path.join(os.path.dirname(sys.argv[1]), "board", "answers","""
            r""" "x.md"), "w").write("x")' knowledge/company""",
            r"""python3 -c 'import sys,os,shutil; shutil.move(os.path.dirname(sys.argv[1]) + "/board", "/tmp/x")'"""
            " knowledge/company",
            "M=knowledge/company; python3 - \"$M\" <<'EOF'\nimport sys, os, shutil\n"
            "shutil.rmtree(os.path.normpath(sys.argv[1] + '/../board'))\nEOF",
            r"""python3 -c 'import os,sys,shutil; os.chdir(sys.argv[1]);"""
            r""" shutil.rmtree(os.path.dirname(os.getcwd()) + "/board")' knowledge/company""",
            r"""K=knowledge/company node -e 'require("child_process")"""
            r""".execSync("rm -rf \"$(dirname \"$K\")\"/b*")'""",
            r"""python3 -c 'import sys,shutil,os.path as P; shutil.rmtree(P.join(P.split(sys.argv[1])[0], "board"))'"""
            " knowledge/company",
            r"""ruby -e 'require "fileutils"; FileUtils.rm_rf(File.join(File.dirname(ARGV[0]), "board"))'"""
            " knowledge/company",
            r"""python3 -c 'import sys,os,shutil; shutil.rmtree(os.path.join(sys.argv[1], os.pardir, "board"))'"""
            " knowledge/company",
            r"""python3 -c 'import sys,glob,shutil; [shutil.rmtree(p) for p in glob.glob(sys.argv[1] + "/../b*")]'"""
            " knowledge/company",
            r"""python3 -c 'import sys,shutil; shutil.rmtree("%s/../board" % sys.argv[1])' knowledge/company""",
            r"""python3 -c 'import sys,shutil; shutil.rmtree(f"{sys.argv[1]}/../board")' knowledge/company""",
            r"""python3 -c 'import sys,shutil; from pathlib import Path;"""
            r""" [shutil.rmtree(p) for p in Path(sys.argv[1]).parent.glob("b*")]' knowledge/company""",
            "K=knowledge/company python3 -c 'import os,shutil; shutil.rmtree(os.path.dirname(os.getenv(\"K\")) + "
            "\"/board\")'",  # with no risky part
            "python3 -c 'import sys,os,shutil; shutil.rmtree(os.path.join(os.path.dirname(sys.argv.pop()), "
            "\"board\"))' knowledge/company",
            "node -e 'const p=require(\"path\"); require(\"fs\").rmSync(p.join(p.dirname(process.argv.at(-1)), "
            "\"board\"), {recursive: true})' knowledge/company",
            "ruby -e 'require \"fileutils\"; FileUtils.rm_rf(File.join(File.dirname(ARGV.first), \"board\"))' "
            "knowledge/company",
            "python3 - knowledge/company <<'EOF'\nimport sys,os,shutil\n"
            "shutil.rmtree(os.path.dirname(sys.argv.pop()) + '/board')\nEOF")})


class RealCommands(unittest.TestCase):
    """Engineers' everyday commands in a product worktree pass; code that may climb or write from there is held; and
    the seal folder is held."""

    setUp, assertHeld = CodeAndMoves.setUp, CodeAndMoves.assertHeld
    assertPass, product = NamesNearby.assertPass, NamesNearby.product
    SCRIPT = '''\
sort_names() {
  tab=$(printf '\\t'); pages=0; folders=0; odd=
  while [ $# -gt 0 ]; do
    word=$1; shift
    case "$word" in
      ""|*"?"*|*"["*|*"$tab"*) odd="$odd $word" ;;
      ..|*/..) echo "a parent folder" >&2; return 2 ;;
      *.md) pages=$((pages + 1)) ;;
      */) folders=$((folders + 1)) ;;
    esac
  done
  awk -v n="$pages" 'BEGIN { if (n < 1) exit 1; print n }'
}
if [ ! -f "$list" ]; then echo "no list"; exit 1; fi
'''

    def worktree(self):
        """A product's worktree under the checkout's workspaces/, with a script and a package.json."""
        wt = self.product()
        (wt / "scripts" / "run-db.sh").write_text(self.SCRIPT)
        (wt / "package.json").write_text('{"name": "acme", "scripts": {"typecheck": "tsc", "lint": "eslint ."}}\n')
        return wt

    def test_a_script_s_lines_and_runs_pass(self):
        """A shell script's lines (its `case "$word" in`) as the command and as a script the command runs; package
        scripts beside git status."""
        wt = self.worktree()
        lines = self.SCRIPT.splitlines()
        self.assertPass(["\n".join(lines[:-1]), lines[-1]], str(wt))
        self.assertPass([f"cd {wt} && sh scripts/run-db.sh down pg-t3", "sh scripts/run-db.sh down pg-t3",
                         "bun run typecheck && bun run lint && git status",
                         "sh scripts/run-db.sh run pg 5432 -- bun test apps/web/test/a.test.ts"], str(wt))
        self.assertPass([f"cd {wt} && bun run typecheck && bun run lint && git status",
                         f"cd {wt} && sh scripts/run-db.sh down pg-t3"])

    def test_a_commit_with_a_quoted_heredoc_message_passes(self):
        wt = self.worktree()
        message = "T-3: a label\n\nThe guard's words: knowledge/board/answers stays the Board's.\n\nCo-Authored-By: x"
        plain = "T-3: a label\n\nCo-Authored-By: x"  # a `$(` heredoc naming a held folder: the check can't split it
        self.assertPass([f"git add apps/web/a.ts apps/web/test/a.test.ts && git commit -q -F - <<'EOF'\n{message}\nEOF",
                         f"git add -A && git commit -m \"$(cat <<'EOF'\n{plain}\nEOF\n)\"",
                         f"git commit -q -F- <<'MSG'\n{message}\nMSG\ngit log --oneline -1"], str(wt))
        self.assertPass([f"cd {wt} && git add apps/web/a.ts && git commit -q -F - <<'EOF'\n{message}\nEOF"])

    def test_lists_and_their_compare_stay_refused(self):
        """`cd <worktree> && bun scripts/pick-tests.ts ... > <scratch>/list2.txt; ...; python3 -I -c "<compare>"`, and
        others of its kind (a heredoc python reads, a folder two below workspaces/, a climb that doesn't reach a held
        part). Fail-closed: held though they write nothing there."""
        wt, s = self.worktree(), self.scr
        compare = ("import sys; a = set(open(sys.argv[1]).read().split()); b = set(open(sys.argv[2]).read().split()); "
                   "print(len(a), len(b), sorted(a ^ b)[:20])")
        self.assertHeld({command: "" for command in (
            f"cd {wt} && bun scripts/pick-tests.ts --base origin/main --list > {s}/list2.txt 2> {s}/list2.err; "
            f"echo rc=$?; wc -l {s}/list2.txt; python3 -I -c \"{compare}\" {s}/list1.txt {s}/list2.txt",
            # with `$S` filled in the double-quoted code
            f"W={wt}; S={s}; cd $W && bun scripts/pick-tests.ts --base origin/main --list > $S/list2.txt 2> "
            "$S/list2.err; echo $? > $S/list2.rc; cat $S/list2.rc; wc -l < $S/list2.txt; cut -c1-300 $S/list2.err | "
            "head; python3 -I -c \"\na=set(open('$S/list.txt').read().split()); b=set(open('$S/list2.txt').read()"
            ".split())\nprint('added', sorted(b-a)); print('removed', sorted(a-b))\n\"",
            f"cd {wt} && python3 - <<'EOF'\nimport json\nprint(sorted(json.load(open('package.json'))['scripts']))\nEOF",
            f"cd {self.root}/workspaces/acme/acme-web 2>/dev/null; python3 -c 'print(1)'",
            f"cd {wt}; sh scripts/run-db.sh run pg 5432 -- bun test apps/web/test/a.test.ts; "
            "ls ../../.test-locks | grep pg")})

    def test_code_given_a_held_part_or_a_shallow_word_stays_refused(self):
        """The interpreter's rules keep the broad rule for a word less than two folders below its held part,
        one less than three given to the code (its arguments, an exported value), a `$` the shell may fill with one,
        and code that names a held part or climbs; and every climb that reaches its held part (`../../..` from a
        worktree). A word three below given to it stays held too."""
        wt, product = self.worktree(), f"{self.root}/workspaces/acme/acme-web"
        read = "import sys; print([len(open(p).read()) for p in sys.argv[1:]])"
        self.assertHeld({f"python3 -I -c '{read}' {wt}/package.json {wt}/scripts/run-db.sh": ""})
        self.assertHeld({command: "isn't a read" for command in (
            f"python3 -I -c '{read}' {product}", "python3 - knowledge/finance/spend.md <<'EOF'\nprint(1)\nEOF",
            f"W={wt}; python3 -c \"import shutil, os; shutil.rmtree(os.path.dirname(os.path.dirname('$W')))\"",
            f"cd {wt} && python3 -c \"print('$1')\"",
            f"export W={product}; cd {wt} && python3 -c 'import os; print(os.environ[\"W\"])'",
            f"cd {self.root}/workspaces/acme && python3 -c 'import shutil; shutil.rmtree(\"/tmp/x\")'",
            f"cd {wt} && python3 -c 'import shutil; shutil.rmtree(\"../../..\")'",
            f"cd {wt} && python3 -c 'import shutil; shutil.rmtree(\"/x/workspaces\")'",
            f"cd {wt} && sh -c 'rm -rf ../../..'", f"cd {wt}; bash -c 'cd ../..; rm -rf ..'",
            f"cd {wt}; bash -c 'rm -rf ../../*'")})
        self.assertHeld({f"cd {wt} && python3 -c \"print('$(date)')\"": "hides what runs"})

    def test_a_climb_by_a_call_from_a_deep_word_stays_refused(self):
        """Code that climbs by a call, or reads the cwd, the environment, its
        input or a shell, from a deep `cd`, pushd or given word, keeps the broad rule."""
        wt, clone = self.worktree(), f"{self.root}/workspaces/acme/acme-web"
        up = "os.path.dirname(os.path.dirname(os.path.dirname({})))"
        cwd_codes = [f"import os, shutil; shutil.rmtree({up.format('os.getcwd()')})",
                     "import os, shutil; shutil.rmtree(os.path.join(os.pardir, os.pardir, os.pardir))",
                     "import shutil; from pathlib import Path; shutil.rmtree(Path.cwd().parents[2])",
                     "import os; [os.chdir(os.pardir) for _ in range(3)]; os.system(\"rm -rf b*\")",
                     f"import os; os.system(\"rm -rf \" + {up.format('os.getcwd()')})",
                     "import os, shutil; p = os.path.abspath('x'); shutil.rmtree(p[:p.rfind('/x')])"]
        held = []
        for folder in (wt, clone):
            held += [f"cd {folder} && python3 -c '{code}'" for code in cwd_codes]
            held += [f"pushd {folder} && python3 -c '{cwd_codes[0]}'", f"cd $'{folder}' && python3 -c '{cwd_codes[1]}'"]
        environ, oldpwd = ("import os, shutil; shutil.rmtree(" + up.format(f'os.environ["{name}"]') + ")"
                           for name in ("W", "OLDPWD"))
        held += [
            f"python3 -c 'import os, sys, shutil; shutil.rmtree({up.format('sys.argv[1]')})' {wt}",
            f"W={wt} python3 -c '{environ}'", f"export W={wt}; python3 -c '{environ}'",
            f"set -a; W={clone}; python3 -c 'import os; print(os.environ[\"W\"])'",
            f"W={clone}; export W; python3 -c 'import os; print(os.environ[\"W\"])'",
            f"echo {clone} | python3 -c 'import os, sys, shutil; shutil.rmtree(os.path.dirname(os.path.dirname("
            "sys.stdin.read().strip())))'",
            f"cd {wt} && cd /tmp && python3 -c '{oldpwd}'",
            f"cd {wt} && node -e 'require(\"fs\").rmSync(require(\"path\").resolve(\"x\").split(\"/\").slice(0, -4)"
            ".join(\"/\"), {recursive: true})'",
            f"cd {wt} && python3 -c 'import glob, shutil; shutil.rmtree(glob.glob(\"/*/*/w*\")[0])'",
            f"cd {wt} && python3 -c 'import shutil; p = open(\"p\").read(); shutil.rmtree(\"/\".join(p.split(\"/\")[:-3]))'",
            f"cd {wt} && ruby -e 'require \"fileutils\"; FileUtils.rm_rf(Dir[\"/*/*/w*\"])'"]
        self.assertHeld({command: "" for command in held})
        self.assertHeld({command: "" for command in (  # reads, held too
            f"cd {wt} && python3 -c 'import sys; print(open(sys.argv[1]).read().split(\"\\n\")[:3])' {self.scr}/l.txt",
            f"cd {wt} && python3 -c 'import re; print(re.findall(r\"apps/[a-z]+/x.*\", open(\"package.json\").read()))'")})

    def test_code_that_may_write_from_a_deep_word_stays_refused(self):
        """Beside a deep `cd`, given or piped word only python's code that only
        reads (read_only) is plain; code that builds `..` from pieces, climbs by a call the climb list lacks, or may
        write, code a `$` may change, a python the command may find elsewhere (own_python), and every other
        interpreter's code, keep the broad rule. A built path that is only read passes."""
        wt, clone = self.worktree(), f"{self.root}/workspaces/acme/acme-web"
        up3, up2 = '"." + "./" + "." + "./" + "." + "."', '"." + "./" + "." + "."'
        held = [f"cd {wt} && python3 -c '{code}'" for code in (
            f"import shutil; shutil.rmtree({up3})", 'import shutil; shutil.rmtree("/".join(["."*2]*3))',
            'import shutil; shutil.rmtree(chr(46)*2 + "/" + chr(46)*2 + "/" + chr(46)*2)',
            'import os, shutil; shutil.rmtree(os.curdir*2 + "/" + os.curdir*2 + "/" + os.curdir*2)',
            'import shutil; shutil.rmtree("." "./" "." "./" "." ".")',
            'open("." + "./" + "." + "./" + "." + "./bo" + "ard-desk/state", "w").write("1")',
            f'import shutil; getattr(shutil, "rmtree")({up3})', f'__import__("shutil").rmtree({up3})',
            f'm = "w"; open({up3} + "/x", m).write("1")', f'open({up3} + "/x", mode="a").write("1")')]
        held += [
            f"cd {wt} && node -e 'require(\"fs\").rmSync([\".\"+\".\", \".\"+\".\", \".\"+\".\"].join(\"/\"), "
            "{recursive: true})'",
            f"cd {wt} && perl -MFile::Path -e 'File::Path::rmtree(\".\" . \"./\" . \".\" . \"./\" . \".\" . \".\")'",
            f"cd {wt} && perl -MFile::Spec -MFile::Path -e 'File::Path::rmtree(File::Spec->catdir(File::Spec->updir, "
            "File::Spec->updir, File::Spec->updir))'",
            f"cd {wt} && ruby -rfileutils -e 'FileUtils.rm_rf({up3})'",
            f"cd {wt} && perl -MCwd=abs_path -MFile::Path=rmtree -e 'rmtree(join(\"/\", (split m{{/}}, "
            "abs_path(\".\"))[0..4]))'",
            f"python3 -c 'import sys, shutil; shutil.rmtree(sys.argv[1] + \"/\" + {up3})' {wt}",
            f"cd {clone} && python3 -c 'import shutil; shutil.rmtree({up2})'",
            f"python3 -c 'import sys, os, shutil; p = sys.argv[1]; p = os.path.split(os.path.split(os.path.split(p)"
            f"[0])[0])[0]; shutil.rmtree(p)' {wt}",
            f"python3 -c 'import sys, shutil; from pathlib import Path; shutil.rmtree(Path(*Path(sys.argv[1]).parts"
            f"[:-3]))' {wt}",
            f"node -e 'let p = process.argv[1]; for (let i = 0; i < 3; i++) p = p.slice(0, p.lastIndexOf(\"/\")); "
            f"require(\"fs\").rmSync(p, {{recursive: true}})' {wt}",
            f"python3 -c 'import sys, re, shutil; shutil.rmtree(re.sub(r\"(/[^/]+){{3}}\\Z\", \"\", sys.argv[1]))' {wt}",
            f"echo {clone} | python3 -c 'import os, shutil; from pathlib import Path; shutil.rmtree(Path(*Path(os.read("
            "0, 999).decode().strip()).parts[:-2]))'",
            f"python3 -c 'import sys; from pathlib import Path; p = Path(*Path(sys.argv[1]).parts[:-3]) / (\"bo\" + "
            f"\"ard-desk\") / \"state\"; p.write_text(\"1\")' {wt}",
            # python's code from a pipe or a here-string, another interpreter's heredoc, a value the shell fills in
            f"cd {wt} && printf 'import shutil\\nshutil.rmtree({up3})' | python3 -",
            f"cd {wt} && python3 - <<< 'import shutil; shutil.rmtree({up3})'",
            f"cd {wt} && ruby <<'EOF'\nopen(\"|rm -rf \" + {up3})\nEOF",
            f"cd {wt} && python3 - <<'EOF'\nopen({up3} + \"/bo\" + \"ard-desk/x\", \"w\").write(\"1\")\nEOF",
            f"X='\"); import shutil; shutil.rmtree({up3}); print(\"'; cd {wt} && python3 -c \"print(\\\"$X\\\")\"",
            f"S={self.scr}; cd {wt}; read S < x; python3 -c \"print(open('$S').read())\"",
            f"S={self.scr}; cd {wt}; for S in a b; do :; done; python3 -c \"print(open('$S').read())\"",
            f"cd {wt}; python3 -c \"print(open('$HOME/x').read())\"", f"cd {wt}; python3 -c \"print('$1')\"",
            # a value that is a reference, holds a `$` or a quote, or a `$` form the shell fills from elsewhere
            f"X='\"); import shutil; shutil.rmtree({up3}); print(\"'; declare -n S=X; cd {wt} && python3 -c "
            "\"print(\\\"$S\\\")\"",
            f"X='\"); import shutil; shutil.rmtree({up3}); print(\"'; S=$X; cd {wt} && python3 -c \"print(\\\"$S\\\")\"",
            f"S='a\" + open(\"x\", \"w\").write(\"1\") + \"'; cd {wt} && python3 -c \"print(\\\"$S\\\")\"",
            f"set -- '\"); import shutil; shutil.rmtree({up3}); print(\"'; cd {wt} && python3 -c \"print(\\\"$*\\\")\"",
            f"X='\"); import shutil; shutil.rmtree({up3}); print(\"'; cd {wt} && python3 -c \"print(\\\"$=X\\\")\"",
            f"S={self.scr}; cd {wt} && python3 -c \"print(open('$S[1]').read())\"",
            f"S={self.scr}; cd {wt} && python3 -c \"print(open('$S:h').read())\"",
            f"cd {wt} && python3 -c \"print('$_')\"",
            f"cd {wt} && python3 - <<'EOF'\n# -*- coding: utf-7 -*-\nprint(1)\nEOF",
            # a python3 the command defines or finds elsewhere
            f"python3() {{ rm -rf {up3.replace(chr(34), '').replace(' + ', '')}; }}; cd {wt} && python3 -c 'print(1)'",
            f"function python3 {{ rm -rf ../../..; }}; cd {wt} && python3 -c 'print(1)'",
            f"alias python3='rm -rf ../../..'; cd {wt} && python3 -c 'print(1)'",
            f"cd {wt} && PATH=. python3 -c 'print(1)'", f"cd {wt} && ./python3 -c 'print(1)'",
            f"cd {wt} && hash -p ./x python3; python3 -c 'print(1)'", f"export PATH=.; cd {wt} && python3 -c 'print(1)'",
            f"cd {wt} && python3() {{ command python3 -c 'import shutil; shutil.rmtree({up3})'; }}; python3 -c 'print(1)'",
            f"cd {wt} && bun -e 'console.log(require(\"./package.json\").scripts.typecheck)'"]
        self.assertHeld({command: "" for command in held})
        self.assertHeld({command: "" for command in (  # reads, held too
            f"cd {wt} && python3 -c 'print(open(\".\" + \"./\" + \"package.json\").read()[:9])'",
            f"cd {wt}; wc -c package.json; python3 - <<'EOF'\nimport json\nt=json.load(open('package.json'"
            "))\nprint(list(t.keys()))\nprint([k for k in t['scripts']][:30])\nprint(any(ord(c)>127 for c in"
            " open('package.json',encoding='utf8').read()))\nEOF",
            f"cd {wt} && python3 -c 'import json, collections; print(collections.Counter(json.load("
            "open(\"package.json\"))[\"scripts\"]).most_common(3))'")})

    def test_a_builtin_the_code_binds_stays_barred(self):
        """A name python_reads counts as the code's own may be a builtin's
        (getattr, __import__, eval, open) bound where it never runs (a lambda's parameter, a comprehension's target,
        `if 0:`, a for over (), del), and python still calls the builtin; from a deep cd, a given word or a heredoc."""
        wt, up3 = self.worktree(), '"." + "./" + "." + "./" + "." + "."'
        climb = 'getattr(__import__("shu" + "til"), "rm" + "tree")'
        self.assertHeld({command: "" for command in (
            f"cd {wt} && python3 -c 'f = lambda getattr, __import__: 0; {climb}({up3})'",
            f"cd {wt} && python3 -c 'g = [0 for eval in ()]; eval(chr(95) * 2 + \"import__(chr(115) + chr(104) + "
            "chr(117) + chr(116) + chr(105) + chr(108)).rmtree(chr(47).join([chr(46) * 2] * 3))\")'",
            f"cd {wt} && python3 -c 'if 0: getattr = __import__ = 0\n{climb}({up3})'",
            f"cd {wt} && python3 -c 'for getattr, __import__ in (): pass\n{climb}({up3})'",
            f"cd {wt} && python3 -c 'if 0:\n    del getattr, __import__\n{climb}({up3})'",
            f"python3 -c 'import sys; f = lambda getattr, __import__: 0; {climb}(sys.argv[1] + \"/.\" + \"./.\" + "
            f"\"./.\" + \".\")' {wt}",
            f"cd {wt} && python3 - <<'EOF'\nf = lambda getattr, __import__: 0\n{climb}({up3})\nEOF",
            f"cd {wt} && python3 -c 'f = lambda getattr, __builtins__: 0; getattr(getattr(__builtins__, \"op\" + "
            f"\"en\")({up3} + \"/bo\" + \"ard-desk/x\", \"w\"), \"wr\" + \"ite\")(\"x\")'")})

    def test_python_that_runs_its_input_after_its_code_stays_refused(self):
        """-i (alone or in a cluster) and PYTHONINSPECT make python run what
        its input gives (a pipe, a here-string, a `<` file) after its -c code, which is all the check reads."""
        wt, s, up3 = self.worktree(), self.scr, '"." + "./" + "." + "./" + "." + "."'
        self.assertHeld({command: "" for command in (
            f"cd {wt} && python3 -i -c 'print(1)' <<< 'import shutil; shutil.rmtree({up3})'",
            f"cd {wt} && printf 'import shutil\\nshutil.rmtree({up3})\\n' | python3 -i -c 'print(1)'",
            f"cd {wt} && python3 -ic 'print(1)' < {s}/p.py", f"cd {wt} && python3 -Iic 'print(1)' < {s}/p.py",
            f"cd {wt} && PYTHONINSPECT=1 python3 -c 'print(1)' < {s}/p.py",
            f"cd {wt} && PYTHONINSPECT=1 python3 -c 'print(1)' <<< 'import shutil; shutil.rmtree({up3})'",
            f"cd {wt} && env PYTHONINSPECT=1 python3 -c 'print(1)' < {s}/p.py",
            f"export PYTHONINSPECT=1; cd {wt} && python3 -c 'print(1)' < {s}/p.py",
            f"declare -x PYTHONINSPECT=1; cd {wt} && python3 -c 'print(1)' < {s}/p.py",
            # a name the shell builds
            f"x=; cd {wt} && env PY${{x}}THONINSPECT=1 python3 -c 'print(1)' <<< 'import shutil; shutil.rmtree({up3})'",
            f"x=; export PY${{x}}THONINSPECT=1; cd {wt} && python3 -c 'print(1)' <<< 'import shutil; "
            f"shutil.rmtree({up3})'",
            f"x=; declare -x PY$x\"THONINSPECT\"=1; cd {wt} && python3 -c 'print(1)' < {s}/p.py",
            f"cd {wt} && env PY{{THON,}}INSPECT=1 python3 -c 'print(1)' < {s}/p.py",
            f"cd {wt} && env PY''THONINSPECT=1 python3 -c 'print(1)' < {s}/p.py",
            f"cd {wt} && env PY\\THONINSPECT=1 python3 -c 'print(1)' < {s}/p.py",
            f"cd {wt} && xargs -a {s}/args -I@ env @ python3 -c 'print(1)' < {s}/p.py",
            f"x=; cd {wt} && sudo -n PY${{x}}THONINSPECT=1 python3 -c 'print(1)' < {s}/p.py",
            f"cd {wt} && uv run --env-file {s}/e python3 -c 'print(1)' < {s}/p.py")})
        self.assertHeld({f"cd {wt}; grep -rn '^<<<<<<<\\|^=======\\|^>>>>>>>' --include=*.ts . | head; "
                         "python3 -c 'print(1)'": ""})
        # a built name as a prefix is no assignment (the shells find those before they expand), so it runs a command
        # named `PYTHONINSPECT=1`, not python
        self.assertPass([f"x=; cd {wt} && PY${{x}}THONINSPECT=1 python3 -c 'print(1)' <<< 'import shutil; "
                         f"shutil.rmtree({up3})'"])

    def test_a_name_the_shell_sets_unseen_stays_refused(self):
        """Read with no name and select set REPLY, getopts OPTARG, mapfile
        MAPFILE, a =~ match MATCH or BASH_REMATCH, with no word naming it, so the one NAME=value word isn't its value;
        and `${S::=x}` sets S unseen by a bare mention."""
        wt, s = self.worktree(), self.scr
        self.assertHeld({command: "" for command in (
            f"REPLY=1; read -r < {s}/p.txt; cd {wt} && python3 -c \"x = '$REPLY'\"",
            f"REPLY=1; select x in a; do break; done < {s}/p.txt; cd {wt} && python3 -c \"x = '$REPLY'\"",
            f"OPTARG=1; getopts a: o -a x; cd {wt} && python3 -c \"x = '$OPTARG'\"",
            f"MAPFILE=1; mapfile < {s}/p.txt; cd {wt} && python3 -c \"x = '$MAPFILE'\"",
            f"MATCH=1; [[ abc =~ b ]]; cd {wt} && python3 -c \"x = '$MATCH'\"",
            f"BASH_REMATCH=1; [[ abc =~ b ]]; cd {wt} && python3 -c \"x = '$BASH_REMATCH'\"",
            f"S={s}; : ${{S::=x}}; cd {wt} && python3 -c \"print(open('$S').read())\"",
            # a name a shell keeps for its own
            f"(ZSH_EXECUTION_STRING=1); cd {wt} && python3 -c \"x = '$ZSH_EXECUTION_STRING'\"",
            f"(BASH_EXECUTION_STRING=1); cd {wt} && python3 -c \"x = '$BASH_EXECUTION_STRING'\"",
            f"ZSH_ARGZERO=1; cd {wt} && python3 -c \"x = '$ZSH_ARGZERO'\"",
            f"BASH_SOURCE=1; cd {wt} && python3 -c \"x = '$BASH_SOURCE'\"",
            f"ZSH_SOMETHING_NEW=1; cd {wt} && python3 -c \"x = '$ZSH_SOMETHING_NEW'\"",
            f"aliases=1; cd {wt} && python3 -c \"x = '$aliases'\"",
            f"status=1; cd {wt} && python3 -c \"x = '$status'\"")})

    def test_a_find_with_quoted_or_escaped_parentheses(self):
        """Quoted, escaped or not, a find that deletes or runs stays refused; one that only lists passes."""
        r = self.root
        self.assertPass([
            f"find {r}/workspaces/acme {r}/knowledge/company \\( -name '*.md' -o -name '*.ts' \\) "
            "-not -path '*/node_modules/*' | head -20",
            f"find {r}/knowledge/company '(' -name a -o -name b ')' -print", "grep -c ';' knowledge/company/x.md"])
        self.assertHeld({"find knowledge/board/answers -name '*.md' -exec rm {} \\;": "find with an action",
                         "find knowledge/board/answers \\( -name a -o -name b \\) -delete": "",
                         "find knowledge/board '(' -name answers ')' -exec rm -rf {} +": ""})

    def test_the_seal_folder_is_held(self):
        """The answers' seal (answers_seal.SEAL_DIR, in Application Support on macOS and .local/state elsewhere), by its
        name and as the folder holding it; reads there pass."""
        for parent in ("Application Support", ".local/state"):
            app = self.scr / parent / "agentic-company"
            (app / "board-desk-seal").mkdir(parents=True)
            self.assertHeld({command: why for command, why in (
                (f"rm -rf '{app}/board-desk-seal'", "isn't a read"), (f"rm -rf '{app}'", "isn't a read"),
                (f"echo x > '{app}/board-desk-seal/a.json'", "output"),
                ("cd ~/x && rm -rf board-desk-seal", "isn't a read"))})
            self.assertPass([f"ls '{app}/board-desk-seal'", f"cat '{app}/board-desk-seal/a.json' | head -3"])

    def test_it_holds_with_no_desk_and_a_broken_company_json(self):
        """Always on, whatever is configured: it reads no setting, so a broken company.json can't open it."""
        self.assertNotIn("company_config", Path(desk.__file__).read_text(encoding="utf-8"))
        for settings in ("{}", "{not json"):
            (self.root / "company.json").write_text(settings)
            self.assertHeld({"rm -rf knowledge/board/answers": "`rm` isn't a read"})
            self.assertHeld({"security find-generic-password -s board-desk-notion -w": ""}, "Notion token")
            self.assertHeld({"python3 scripts/board_desk.py read": ""}, "its launchd jobs'")


class WorktreeReset(unittest.TestCase):
    """An agent's `git reset --hard <commit>` in its own linked worktree passes when it
    changes no file under knowledge/board/answers or workspaces/board-desk; in the main checkout it stays refused."""

    def git(self, *args, cwd=None):
        return subprocess.run(["git", "-C", str(cwd or self.main), *args], capture_output=True, text=True,
                              check=True).stdout.strip()

    def commit(self, path, text):
        (self.main / path).write_text(text)
        self.git("add", path)
        self.git("commit", "-q", "-m", path)
        return self.git("rev-parse", "HEAD")

    def setUp(self):
        self.root = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, self.root)
        self.main, self.tree = self.root / "main", self.root / "tree"
        (self.main / "knowledge" / "board" / "answers").mkdir(parents=True)
        self.git("init", "-q")
        self.git("config", "user.email", "t@example.com")
        self.git("config", "user.name", "t")
        self.c1 = self.commit("knowledge/board/answers/a.md", "1\n")
        self.c2 = self.commit("other.txt", "2\n")
        self.c3 = self.commit("knowledge/board/answers/a.md", "2\n")
        self.git("worktree", "add", "-q", "--detach", str(self.tree), self.c2)

    def test_a_reset_that_leaves_the_answers_as_they_are_passes_in_a_linked_worktree(self):
        cwd = str(self.tree)
        for command in ("git reset --hard", f"git reset --hard {self.c1}", f"git reset -q --keep {self.c1}",
                        "git reset --merge HEAD~1", f"cd {self.tree} && git reset --hard {self.c1[:8]}"):
            with self.subTest(command=command):
                self.assertIsNone(reason(command, cwd))
        self.assertIsNone(reason(f"git -C {self.tree} reset --hard {self.c1}", str(self.main)))

    def test_a_reset_that_changes_them_or_runs_elsewhere_is_refused(self):
        cwd = str(self.tree)
        cases = [(f"git reset --hard {self.c3}", cwd), ("git reset --hard", str(self.main)),
                 (f"git -C {self.main} reset --hard {self.c3}", cwd), ("git reset --hard $x", cwd),
                 (f"git reset --hard {self.c1} {self.c2}", cwd), ("git -c core.x=y reset --hard", cwd),
                 ("git reset --hard --recurse-submodules", cwd), (f"git reset --hard {self.c1} -- other.txt", cwd),
                 ("git reset --hard nosuchcommit", cwd), ("git reset --hard", "")]
        for command, where in cases:
            with self.subTest(command=command, cwd=where):
                self.assertIn("the Board's own answers", reason(command, where) or "")
        (self.tree / "knowledge" / "board" / "answers" / "a.md").write_text("changed\n")
        self.assertIn("`git reset`", reason("git reset --hard", cwd) or "")

    def test_a_ref_moved_in_the_same_command_leaves_the_reset_refused(self):
        """The check compares the
        commit as it is before the command runs, so a reset passes only beside reads that move no ref."""
        cwd = str(self.tree)
        for command in (f"git commit -q --allow-empty -m x && git reset --hard {self.c1}",
                        f"git fetch -q origin && git reset --hard {self.c1}",
                        f"git update-ref refs/heads/x {self.c3} && git reset --hard {self.c1}",
                        f"git reset --soft {self.c3} && git reset --hard", "git reset --hard; git reset --hard",
                        f"git push -q . {self.c3}:refs/heads/y && git reset --hard {self.c1}",
                        f"git reset --hard {self.c1} && rm -f /tmp/x", f"git stash; git reset --hard {self.c1}",
                        f"git add -A && git reset --hard {self.c1}"):  
            with self.subTest(command=command):
                self.assertIn("the Board's own answers", reason(command, cwd) or "")
        for command in (f"git log -1 && git reset --hard {self.c1}", f"git reset --hard {self.c1} && git status",
                        f"cd {self.tree} && git reset --hard {self.c1} && git log --oneline -1 | cut -c1-8"):
            with self.subTest(command=command):
                self.assertIsNone(reason(command, cwd))

    def test_a_git_add_beside_the_reset_leaves_it_refused(self):
        """The check reads the index before the command runs, so `git add -A`
        beside the reset would stage an untracked answer the reset then deletes."""
        cwd = str(self.tree)
        (self.tree / "knowledge" / "board" / "answers" / "untracked.md").write_text("x\n")
        self.assertIsNone(reason(f"git reset --hard {self.c1}", cwd))  # alone, it leaves the untracked file
        for command in (f"git add -A && git reset --hard {self.c1}", f"git add . ; git reset --hard {self.c1}"):
            with self.subTest(command=command):
                self.assertIn("the Board's own answers", reason(command, cwd) or "")

    def test_the_check_runs_no_filter_and_reads_the_files_itself(self):
        """A `git diff` would run the clean filter of a config the agent may write, so git only lists the commit's and
        the index's entries, and the working files are hashed here."""
        marker = self.root / "filter-ran"
        self.git("config", "filter.x.clean", f"touch {marker}; cat")
        (self.tree / ".gitattributes").write_text("* filter=x\n")
        answer = self.tree / "knowledge" / "board" / "answers" / "a.md"
        answer.write_text(answer.read_text())  # the same bytes, a new mtime: git diff would clean it again
        self.assertIsNone(reason(f"git reset --hard {self.c1}", str(self.tree)))
        self.assertFalse(marker.exists())
        self.assertTrue(desk.same_files(str(self.tree), self.c1))
        self.assertFalse(desk.same_files(str(self.tree), self.c3))
        self.assertFalse(desk.same_files(str(self.tree), "nosuchcommit"))

    def test_an_index_entry_a_mode_or_a_symlinked_folder_is_a_change(self):
        answers = self.tree / "knowledge" / "board" / "answers"
        (answers / "untracked.md").write_text("x\n")  # a reset leaves an untracked file
        self.assertTrue(desk.same_files(str(self.tree), self.c1))
        self.git("add", "knowledge/board/answers/untracked.md", cwd=self.tree)  # a reset removes a staged one
        self.assertFalse(desk.same_files(str(self.tree), self.c1))
        self.git("rm", "-q", "--cached", "knowledge/board/answers/untracked.md", cwd=self.tree)
        (answers / "untracked.md").unlink()
        self.assertTrue(desk.same_files(str(self.tree), self.c1))
        (answers / "a.md").chmod(0o755)
        self.assertFalse(desk.same_files(str(self.tree), self.c1))
        (answers / "a.md").chmod(0o644)
        board = self.tree / "knowledge" / "board"
        shutil.move(str(board), str(self.root / "elsewhere"))
        board.symlink_to(self.root / "elsewhere")
        self.assertFalse(desk.same_files(str(self.tree), self.c1))

    def test_the_hint_names_the_reset_only_when_it_runs_first(self):
        """A refused call whose first
        simple command is a reset that passes alone names it, the one retry a blocked agent is allowed (once, in exactly
        the form the block message names); a command before
        it may move the ref, the branch or the folder, so then no form is named."""
        cwd, hint = str(self.tree), "run the reset in its own call"
        for command in (f"git reset --hard {self.c1} && rm -f /tmp/x", f"git reset --hard {self.c1}; git add -A"):
            with self.subTest(command=command):
                found = reason(command, cwd) or ""
                self.assertIn(f"{hint}: `git reset --hard {self.c1}`", found)
                self.assertIsNone(reason(f"git reset --hard {self.c1}", cwd))  # the named form passes
        reset = f"git reset --hard {self.c1}"
        for command in (f"git commit -q --allow-empty -m x && {reset}", f"git reset --soft {self.c3} && git reset --hard",
                        f"git fetch -q origin && {reset}", f"git checkout -q -b t && {reset}",
                        f"pushd {self.tree} && {reset}", f"chdir {self.tree} && {reset}",
                        f"builtin cd {self.tree}; {reset}", f"command cd {self.tree}; {reset}", f"popd; {reset}",
                        f"git reset --hard {self.c3} && rm -f /tmp/x",  # alone it is refused too
                        f"{reset} > /tmp/x; rm -f /tmp/y", f"! {reset}; rm -f /tmp/y", f"{reset} x(e:true:); rm -f /tmp/y"):
            with self.subTest(command=command):
                found = reason(command, cwd) or ""
                self.assertIn("the Board's own answers", found)
                self.assertNotIn(hint, found)


if __name__ == "__main__":
    unittest.main()
