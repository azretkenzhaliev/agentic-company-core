"""Tests for scripts/spawn_context.py. Every repo is made up in a temp folder."""

import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

import spawn_context  # noqa: E402


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class SpawnContextTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        write(self.root / "CLAUDE.md", "c" * 100)
        write(self.root / ".claude/agents/team/plain.md", "---\nname: plain\ntools: Read\n---\n\n" + "b" * 50 + "\n\n")
        write(self.root / ".claude/agents/loaded.md",
              "---\nname: loaded\nskills:\n  - craft\n  - gone\n---\n" + "b" * 10 + "\n")
        write(self.root / ".claude/skills/craft/SKILL.md", "---\nname: craft\ndescription: x\n---\n\n" + "s" * 30 + "\n")

    def tearDown(self):
        self.tmp.cleanup()

    def run_main(self, *argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = spawn_context.main(["--root", str(self.root), *argv])
        return code, out.getvalue()

    def rows(self):
        return {r[0]: r for r in spawn_context.measure(self.root)[0]}

    def test_counts_body_claude_md_and_preloaded_skills(self):
        rows = self.rows()
        self.assertEqual(rows["plain"][1:5], (50, 100, 0, 150))  # front matter and blank edges aren't loaded
        self.assertEqual(rows["loaded"][1:5], (10, 100, 30, 140))  # the skill's body, without its front matter

    def test_a_missing_skill_is_named_and_not_counted(self):
        notes = spawn_context.measure(self.root)[1]
        self.assertEqual(notes, ["loaded: skill gone not found, not counted"])

    def test_characters_not_bytes_and_tokens_from_bytes(self):
        write(self.root / ".claude/agents/wide.md", "---\nname: wide\n---\n" + "é" * 53)
        row = self.rows()["wide"]
        self.assertEqual(row[1], 53)
        self.assertEqual(row[5], round((53 * 2 + 100) / 2.65))

    def test_exit_1_over_the_cap_and_names_the_agent(self):
        code, out = self.run_main("--cap", "145")
        self.assertEqual(code, 1)
        self.assertIn("OVER plain: 150 characters, cap 145", out)
        self.assertNotIn("OVER loaded", out)

    def test_exit_0_at_the_cap(self):
        self.assertEqual(self.run_main("--cap", "150")[0], 0)

    def test_agent_filter_and_unknown_agent(self):
        code, out = self.run_main("--cap", "145", "--agent", "loaded")
        self.assertEqual(code, 0)
        self.assertNotIn("plain", out)
        self.assertEqual(self.run_main("--cap", "145", "--agent", "nobody")[0], 2)

    def test_also_adds_a_file_to_every_agent(self):
        extra = self.root / "user-claude.md"
        write(extra, "u" * 7)
        rows = {r[0]: r for r in spawn_context.measure(self.root, [str(extra)])[0]}
        self.assertEqual(rows["plain"][2], 107)
        self.assertEqual(rows["loaded"][4], 147)

    def test_the_repos_agents_parse(self):
        rows, notes = spawn_context.measure(spawn_context.ROOT)
        self.assertIn("ux-expert", {r[0] for r in rows})
        self.assertEqual(notes, [])


if __name__ == "__main__":
    unittest.main()
