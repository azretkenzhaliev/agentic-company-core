"""The form scripts/hooks/cq_write.py's refusal and scripts/kb_lint.py's sweep line give for scripts/cq_archive.py: the
main checkout's script and the file, both by absolute path, with no `cd`, which the hook allows from any cwd. A relative
path is refused in a worktree of this repo, which has its own copy."""

import re
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS / "hooks"))
sys.path.insert(0, str(SCRIPTS))
import cq_write  # noqa: E402
import kb_lint  # noqa: E402

F = "workspaces/demo/content/ceo-questions.md"
LINT_FORM = re.compile(r"python3 (\S+) (\S+) --dry-run shows what would move")


class AbsoluteForm(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.main = Path(self.tmp.name).resolve() / "main"
        (self.main / ".git" / "worktrees" / "wt").mkdir(parents=True)
        (self.main / ".git" / "worktrees" / "wt" / "commondir").write_text("../..\n", encoding="utf-8")
        (self.main / "knowledge").mkdir()
        self.worktree = self.main / ".claude" / "worktrees" / "wt"  # an agent's cwd, with its own copy of the script
        (self.worktree / "scripts").mkdir(parents=True)
        (self.worktree / "scripts" / "cq_archive.py").write_text("", encoding="utf-8")
        (self.worktree / ".git").write_text(f"gitdir: {self.main}/.git/worktrees/wt\n", encoding="utf-8")
        (self.worktree / "knowledge").mkdir()
        self.cq = self.main / F
        self.log(self.cq)

    def tearDown(self):
        self.tmp.cleanup()

    @staticmethod
    def log(path):
        """A ceo-questions.md over its 30 KB limit, so kb_lint names the tool."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("## ORDER D-20260101-x/1 (CTO)\n" + "x" * 31 * 1024, encoding="utf-8")

    def passes(self, command):
        return cq_write.command_reason(command, str(self.worktree), str(self.main)) is None

    def test_the_hooks_message_names_the_absolute_form_and_it_passes_from_a_worktree(self):
        form = (f"python3 {self.main}/scripts/cq_archive.py {self.main}/workspaces/<product>/content/ceo-questions.md "
                "--order <id>")
        bash = {"tool_name": "Bash", "agent_id": "a1", "cwd": str(self.worktree),
                "tool_input": {"command": f"sed -i '' 's/a/b/' {self.cq}"}}
        messages = [cq_write.cq_reason(bash, str(self.main)),
                    cq_write.write_reason({"tool_name": "Write", "agent_id": "a1"}, str(self.cq), self.cq,
                                          str(self.main))]
        for message in messages:
            self.assertIn(f"`{form}`, both paths absolute, no `cd`", message)
            self.assertNotIn("python3 scripts/cq_archive.py", message)
        self.assertTrue(self.passes(form.replace("<product>", "demo").replace("<id>", "/9")))
        self.assertFalse(self.passes(f"python3 scripts/cq_archive.py {F} --order /9"))  # the worktree's own copy

    def test_kb_lints_line_names_the_main_checkouts_script_and_it_passes_from_a_worktree(self):
        self.log(self.worktree / F)  # a worktree has no workspaces/ as a rule; one here shows whose script is named
        for base, page in ((self.main, self.cq), (self.worktree, self.worktree / F)):
            with self.subTest(base=base):
                lines = [f.message for f in kb_lint.lint(base / "knowledge", date(2026, 1, 15)) if f.path == F]
                self.assertEqual(len(lines), 1, lines)
                script, file = LINT_FORM.search(lines[0]).groups()
                self.assertEqual((script, file), (f"{self.main}/scripts/cq_archive.py", str(page)))
                self.assertTrue(self.passes(f"python3 {script} {file} --dry-run"))


if __name__ == "__main__":
    unittest.main()
