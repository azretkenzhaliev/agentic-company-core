"""Tests for scripts/agent_index.py. Every repo is made up in a temp folder."""

import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

import agent_index  # noqa: E402

TABLE = """# How engineering works

## What to read

| Role | Always | When the task needs it |
|---|---|---|
| Senior | Its ORDER; standards `coding`; the digest's groups | `staff-engineer.md` §5 |
| Staff | this page; every standard above | Architecture sections |
| Board | `coding` | |
"""
INVENTORY = """# Inventory

#### ceo (main session)

| Opens | Page |
|---:|---|
| 9 | `workspaces/p/content/ceo-questions.md` |
| 8 | `knowledge/company/prefs.md` |
| 7 | `knowledge/research/2026-01-01-note.md` |
| 6 | `knowledge/company/old-archive.md` |
| 5 | `knowledge/company/gone.md` |
| 4 | `knowledge/_templates/directive.md` |

#### senior-engineer

| 4 | `knowledge/engineering/standards/coding.md` |
| 3 | `knowledge/products/p/a.md` |
| 2 | `knowledge/products/p/b.md` |
| 1 | `knowledge/products/p/c.md` |

#### cmo as the headless job (`scripts/x.sh`)

| 9 | `knowledge/company/prefs.md` |
"""


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def page(owner: str, title: str, status: str = "active") -> str:
    return f"---\ntitle: {title}\nowner: {owner}\nstatus: {status}\nupdated: 2026-01-01\nrelated: []\n---\n\nBody.\n"


class AgentIndexTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        r = self.root
        write(r / "knowledge/engineering/README.md", TABLE)
        write(r / "knowledge/engineering/standards/coding.md", page("cto", "Coding standards"))
        write(r / "knowledge/engineering/standards/lessons-learned.md", page("cto", "Lessons learned"))
        write(r / "knowledge/engineering/architecture/overview.md", page("cto", "Architecture overview", "draft"))
        write(r / "knowledge/company/prefs.md", page("ceo", "Board preferences"))
        write(r / "knowledge/company/old-archive.md", page("ceo", "Old"))
        write(r / "knowledge/research/2026-01-01-note.md", page("analyst", "Raw note"))
        write(r / "knowledge/_templates/directive.md", page("ceo", "<Short directive title>"))
        write(r / "knowledge/products/p/a.md", page("ceo", "A"))
        write(r / "knowledge/products/p/b.md", page("ceo", "B", "superseded"))
        write(r / "knowledge/products/p/c.md", page("ceo", "C"))
        write(r / "knowledge/products/p/d.md", page("ceo", "D"))
        for name in ("ceo", "senior-engineer", "staff-engineer", "cmo"):
            write(r / f".claude/agents/{name}.md", f"---\nname: {name}\n---\nBody.\n")
        self.inventory = r / "inventory.md"
        write(self.inventory, INVENTORY)

    def tearDown(self):
        self.tmp.cleanup()

    def build(self):
        return agent_index.build(self.root, agent_index.agent_names(self.root), self.inventory)

    def test_table_rows_ticked_words_and_phrases(self):
        reads = agent_index.table_reads(self.root)
        self.assertEqual(reads["senior-engineer"], ["knowledge/engineering/standards/coding.md",
                                                    "knowledge/engineering/standards/lessons-learned.md"])
        self.assertEqual(reads["staff-engineer"], ["knowledge/engineering/README.md",
                                                   "knowledge/engineering/architecture/overview.md",
                                                   "knowledge/engineering/standards/coding.md"])
        self.assertNotIn("board", reads)  # only the rows of known roles

    def test_inventory_roles_and_a_non_role_heading(self):
        opened = agent_index.opened_reads(self.inventory)
        self.assertEqual(sorted(opened), ["ceo", "senior-engineer"])
        self.assertNotIn("cmo", opened)  # the headless job's heading isn't a role's
        self.assertNotIn("workspaces/p/content/ceo-questions.md", opened["ceo"])

    def test_never_research_templates_cold_superseded_missing_or_live_state(self):
        lines = [line for line in self.build()["ceo"].splitlines() if line.lstrip().startswith("- ")]
        self.assertEqual(lines, ["- knowledge/company/prefs.md: Board preferences"])

    def test_owner_shown_only_when_another_role_and_draft_marked(self):
        staff = self.build()["staff-engineer"]
        self.assertIn("- knowledge/engineering/architecture/overview.md: Architecture overview (cto, draft)", staff)
        ceo = self.build()["ceo"]
        self.assertIn("- knowledge/company/prefs.md: Board preferences\n", ceo)

    def test_a_small_folder_stays_flat(self):
        text = self.build()["senior-engineer"]
        self.assertIn("- knowledge/products/p/a.md: A (ceo)\n- knowledge/products/p/c.md: C (ceo)\n", text)
        self.assertNotIn("b.md", text)  # superseded

    def test_grouping_at_group_at_pages(self):
        write(self.root / "knowledge/products/p/b.md", page("ceo", "B"))
        text = self.build()["senior-engineer"]
        self.assertIn("knowledge/products/p/\n  - a.md: A (ceo)\n  - b.md: B (ceo)\n  - c.md: C (ceo)\n", text)

    def test_header_says_generated_and_names_sources(self):
        text = self.build()["senior-engineer"]
        self.assertTrue(text.startswith("<!-- Generated by scripts/agent_index.py"))
        self.assertIn('its row of "What to read"', text)
        self.assertIn("per inventory.md", text)

    def test_header_names_a_workspaces_inventory_from_its_folder(self):
        moved = self.root / "main/workspaces/system/inventory.md"
        write(moved, INVENTORY)
        text = agent_index.build(self.root, agent_index.agent_names(self.root), moved)["senior-engineer"]
        self.assertIn("per workspaces/system/inventory.md", text)

    def test_without_inventory_only_the_table(self):
        indexes = agent_index.build(self.root, agent_index.agent_names(self.root), None)
        self.assertEqual(sorted(indexes), ["senior-engineer", "staff-engineer"])

    def run_main(self, *argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = agent_index.main(["--root", str(self.root), *argv])
        return code, out.getvalue()

    def test_default_writes_nothing_and_write_writes(self):
        code, out = self.run_main("--opened", str(self.inventory))
        self.assertEqual(code, 0)
        self.assertIn("senior-engineer", out)
        self.assertFalse((self.root / ".claude/agent-index").exists())
        self.run_main("--opened", str(self.inventory), "--write")
        written = sorted(p.name for p in (self.root / ".claude/agent-index").iterdir())
        self.assertEqual(written, ["ceo.md", "senior-engineer.md", "staff-engineer.md"])

    def test_write_removes_a_generated_index_whose_role_has_no_page_and_keeps_other_files(self):
        out = self.root / ".claude/agent-index"
        self.run_main("--opened", str(self.inventory), "--write")
        write(out / "notes.md", "Hand-written.\n")
        code, text = self.run_main("--write")  # no inventory: ceo has no page now
        self.assertEqual(code, 0)
        self.assertIn("removed ceo.md", text)
        self.assertEqual(sorted(p.name for p in out.iterdir()), ["notes.md", "senior-engineer.md", "staff-engineer.md"])

    def test_a_missing_inventory_is_an_error(self):
        self.assertEqual(self.run_main("--opened", str(self.root / "nope.md"))[0], 2)

    def test_the_repos_table_still_parses(self):
        reads = agent_index.table_reads(agent_index.ROOT)
        self.assertEqual(sorted(reads), sorted(agent_index.ROWS.values()))
        self.assertIn("knowledge/engineering/standards/testing.md", reads["code-reviewer"])
        self.assertIn("knowledge/engineering/standards/lessons-learned.md", reads["cto"])


if __name__ == "__main__":
    unittest.main()
