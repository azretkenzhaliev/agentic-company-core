"""Tests for scripts/build_cores.py.

Each agent's "## Core" section is a generated copy of its owner's KB pages: the CTO's knowledge/engineering/cores/ and
the CMO's knowledge/marketing/cores/. A section that differs from them fails here. A regenerate is a system change:
the platform engineer runs `python3 scripts/build_cores.py` on a sys/ branch and the CEO lands it through the gate;
never edit a section by hand."""

import contextlib
import io
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

import build_cores  # noqa: E402

AGENT = "---\nname: x\ntools: Read\n---\n\nYou are x.\n\nThe constitution binds you.\n\n## Rules\n\n- one\n"
PAGE = "---\ntitle: t\nowner: cto\n---\n\n# Part\n\nLine.\n\n## Topic\n- rule\n"


class RealAgents(unittest.TestCase):
    def test_every_core_section_matches_its_pages(self):
        built = build_cores.build()
        self.assertEqual(len(built), 11)
        for path, (current, expected) in built.items():
            with self.subTest(agent=path.name):
                self.assertTrue(current == expected, f"{path.name}: its Core section differs from the KB pages. A "
                                "regenerate is a system change: the platform engineer runs python3 "
                                "scripts/build_cores.py on a sys/ branch, landed through the CEO's gate")

    def test_each_section_within_its_owners_cap(self):
        for agent, pages in build_cores.CORES.items():
            text = (build_cores.ROOT / agent).read_text(encoding="utf-8")
            found = re.search(r"^## Core\n.*?(?=^## )", text, re.M | re.S)
            with self.subTest(agent=agent):
                self.assertIsNotNone(found)
                self.assertLessEqual(len(found.group(0)), build_cores.CAP)  # the span section() counts
                self.assertEqual(text.count("\n## Core\n"), 1)

    def test_the_cto_loads_no_shared_part(self):
        self.assertEqual(build_cores.CORES[".claude/agents/engineering/cto.md"],
                         ["knowledge/engineering/cores/cto.md"])


class Generator(unittest.TestCase):
    def test_section_strips_front_matter_and_moves_headings_down(self):
        self.assertEqual(build_cores.section([PAGE, PAGE.replace("Part", "Role")]),
                         "## Core\n\n### Part\n\nLine.\n\n#### Topic\n- rule\n\n"
                         "### Role\n\nLine.\n\n#### Topic\n- rule\n\n")

    def test_inserted_after_the_opening_paragraphs(self):
        out = build_cores.with_core(AGENT, "## Core\n\nC.\n\n")
        self.assertEqual(out, AGENT.replace("## Rules", "## Core\n\nC.\n\n## Rules"))

    def test_a_stale_section_is_replaced_and_nothing_else_changes(self):
        stale = build_cores.with_core(AGENT, "## Core\n\n### Old\n\nedited by hand\n\n")
        self.assertEqual(build_cores.with_core(stale, "## Core\n\nC.\n\n"),
                         build_cores.with_core(AGENT, "## Core\n\nC.\n\n"))

    def test_running_twice_changes_nothing(self):
        once = build_cores.with_core(AGENT, build_cores.section([PAGE]))
        self.assertEqual(build_cores.with_core(once, build_cores.section([PAGE])), once)

    def test_over_the_cap_is_refused(self):
        page = "---\ntitle: t\n---\n" + "x" * (build_cores.CAP - len("## Core\n\n\n\n") + 1)
        with self.assertRaises(ValueError):
            build_cores.section([page])
        build_cores.section([page[:-1]])  # exactly at the cap is allowed

    def test_a_code_block_is_refused(self):
        for fence in ("```", "~~~"):
            with self.subTest(fence=fence), self.assertRaises(ValueError):
                build_cores.section([f"---\ntitle: t\n---\n{fence}\n# not a heading\n{fence}\n"])


class Main(unittest.TestCase):
    """`--check` and the write mode, on a copy of the agent files and core pages in a temporary folder."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root)
        for name in set(build_cores.CORES) | {p for pages in build_cores.CORES.values() for p in pages}:
            (self.root / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(build_cores.ROOT / name, self.root / name)

    def run_main(self, *args):
        with contextlib.redirect_stdout(io.StringIO()) as out, contextlib.redirect_stderr(io.StringIO()):
            return build_cores.main(["build_cores.py", *args], self.root), out.getvalue()

    def test_check_passes_clean_fails_on_drift_and_the_write_mode_fixes_it(self):
        self.assertEqual(self.run_main("--check"), (0, ""))
        page = self.root / "knowledge/engineering/cores/design-reviewer.md"
        page.write_text(page.read_text(encoding="utf-8") + "\n- **A new line**\n", encoding="utf-8")
        self.assertEqual(self.run_main("--check"), (1, "differs: .claude/agents/engineering/design-reviewer.md\n"))
        self.assertEqual(self.run_main(), (0, "written: .claude/agents/engineering/design-reviewer.md\n"))
        self.assertEqual(self.run_main("--check"), (0, ""))
        self.assertIn("- **A new line**", (self.root / ".claude/agents/engineering/design-reviewer.md").read_text())

    def test_an_unknown_argument_is_refused(self):
        self.assertEqual(self.run_main("--write")[0], 2)


if __name__ == "__main__":
    unittest.main()
