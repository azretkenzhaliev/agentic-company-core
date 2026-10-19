"""Tests for scripts/kb_lint.py."""

import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

from kb_lint import lint  # noqa: E402

TODAY = date(2026, 10, 12)


def page(body="# Page\n", **overrides):
    fields = {
        "title": "A page",
        "owner": "ceo",
        "status": "active",
        "updated": "2026-10-12",
        "related": "[]",
    }
    fields.update(overrides)
    front = "".join(f"{k}: {v}\n" for k, v in fields.items() if v is not None)
    return f"---\n{front}---\n\n{body}"


class KbLintTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "knowledge"
        self.root.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, rel, text):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def findings(self, level=None):
        return [f for f in lint(self.root, TODAY) if level is None or f.level == level]

    def messages(self, level="error"):
        return [f.message for f in self.findings(level)]


class FrontMatter(KbLintTestCase):
    def test_valid_page_is_clean(self):
        self.write("a.md", page())
        self.assertEqual(self.findings(), [])

    def test_missing_front_matter(self):
        self.write("a.md", "# No front matter\n")
        self.assertEqual(len(self.findings("error")), 1)
        self.assertIn("front matter", self.messages()[0])

    def test_each_required_key(self):
        for key in ("title", "owner", "status", "updated", "related"):
            with self.subTest(key=key):
                self.write("a.md", page(**{key: None}))
                self.assertTrue(any(key in m for m in self.messages()), self.messages())

    def test_invalid_owner(self):
        self.write("a.md", page(owner="marketing"))
        self.assertTrue(any("owner" in m and "marketing" in m for m in self.messages()))

    def test_invalid_status(self):
        self.write("a.md", page(status="done"))
        self.assertTrue(any("status" in m for m in self.messages()))

    def test_invalid_date(self):
        self.write("a.md", page(updated="12/10/2026"))
        self.assertTrue(any("updated" in m for m in self.messages()))

    def test_every_owner_value_is_accepted(self):
        for i, owner in enumerate(("board", "ceo", "cto", "analyst", "staff-engineer")):
            self.write(f"p{i}.md", page(owner=owner))
        self.assertEqual(self.findings(), [])

    def test_templates_are_skipped(self):
        self.write("_templates/x.md", "# placeholder <owner>\n")
        self.assertEqual(self.findings(), [])


class Staleness(KbLintTestCase):
    def test_page_90_days_old_warns(self):
        self.write("a.md", page(updated="2026-07-14"))  # 90 days before TODAY
        self.assertEqual(self.findings("error"), [])
        self.assertEqual(len(self.findings("warning")), 1)

    def test_page_89_days_old_is_clean(self):
        self.write("a.md", page(updated="2026-07-15"))
        self.assertEqual(self.findings(), [])


class Links(KbLintTestCase):
    def test_broken_markdown_link_reports_its_line(self):
        self.write("a.md", page(body="# A\n\nSee [b](missing.md).\n"))
        errors = self.findings("error")
        self.assertEqual(len(errors), 1)
        self.assertIn("missing.md", errors[0].message)
        self.assertEqual(errors[0].line, 11)  # 7 front-matter lines, blank, "# A", blank, link

    def test_valid_links_to_file_dir_and_anchor(self):
        self.write("sub/b.md", page())
        self.write("a.md", page(body="[b](sub/b.md) [dir](sub/) [anchor](sub/b.md#part) [self](#top)\n"))
        self.assertEqual(self.findings(), [])

    def test_link_outside_kb_is_resolved(self):
        (self.root.parent / "CLAUDE.md").write_text("x")
        self.write("a.md", page(body="[c](../CLAUDE.md)\n"))
        self.assertEqual(self.findings(), [])

    def test_external_links_are_ignored(self):
        self.write("a.md", page(body="[x](https://example.com/nope) [m](mailto:a@b.c)\n"))
        self.assertEqual(self.findings(), [])

    def test_links_in_code_are_ignored(self):
        body = "```\n[x](nope.md)\n```\n\nUse `[y](nope.md)` like this.\n"
        self.write("a.md", page(body=body))
        self.assertEqual(self.findings(), [])

    def test_broken_related_path(self):
        self.write("a.md", page(related="[nope.md]"))
        self.assertTrue(any("nope.md" in m for m in self.messages()))

    def test_related_block_list(self):
        self.write("b.md", page())
        text = page().replace("related: []\n", "related:\n  - b.md\n  - gone.md\n")
        self.write("a.md", text)
        messages = self.messages()
        self.assertEqual(len(messages), 1, messages)
        self.assertIn("gone.md", messages[0])


class Orphans(KbLintTestCase):
    """With a root INDEX.md, every other page needs at least one inbound link."""

    def orphan_paths(self):
        return [f.path for f in self.findings("warning") if "orphan" in f.message]

    def test_unlinked_page_warns(self):
        self.write("INDEX.md", page(body="[a](a.md)\n"))
        self.write("a.md", page())
        self.write("b.md", page())
        self.assertEqual(self.orphan_paths(), ["knowledge/b.md"])
        self.assertEqual(self.findings("error"), [])

    def test_link_from_related_counts(self):
        self.write("INDEX.md", page(related="[a.md]"))
        self.write("a.md", page())
        self.assertEqual(self.orphan_paths(), [])

    def test_index_itself_is_never_an_orphan(self):
        self.write("INDEX.md", page())
        self.assertEqual(self.orphan_paths(), [])

    def test_self_link_does_not_count(self):
        self.write("INDEX.md", page())
        self.write("a.md", page(body="[me](a.md)\n"))
        self.assertEqual(self.orphan_paths(), ["knowledge/a.md"])

    def test_directory_link_counts_for_its_readme(self):
        self.write("INDEX.md", page(body="[sub](sub/)\n"))
        self.write("sub/README.md", page())
        self.assertEqual(self.orphan_paths(), [])

    def test_no_index_means_no_orphan_check(self):
        self.write("a.md", page())
        self.assertEqual(self.orphan_paths(), [])


class Ids(KbLintTestCase):
    def test_duplicate_roadmap_ids(self):
        self.write("engineering/roadmaps/RM-001-alpha.md", page())
        self.write("engineering/roadmaps/RM-001-beta.md", page())
        self.assertTrue(any("RM-001" in m for m in self.messages()))

    def test_distinct_ids_are_clean(self):
        self.write("engineering/designs/DD-001-a.md", page())
        self.write("engineering/designs/DD-002-b.md", page())
        self.write("engineering/adr/ADR-001-a.md", page())
        self.assertEqual(self.findings(), [])

    def test_duplicate_standing_authorization_headings(self):
        self.write("board/sa.md", page(body="## SA-001: one\n\n## SA-001: again\n"))
        self.assertTrue(any("SA-001" in m for m in self.messages()))


class Secrets(KbLintTestCase):
    def test_secret_is_an_error_without_its_value(self):
        token = "gh" + "p_" + "a1B2c3D4e5" * 3 + "f6G7h8"
        self.write("a.md", page(body=f"token: {token}\n"))
        errors = self.findings("error")
        self.assertEqual(len(errors), 1)
        self.assertIn("GitHub token", errors[0].message)
        self.assertNotIn(token, errors[0].message)


class CommandLine(KbLintTestCase):
    def run_cli(self):
        return subprocess.run(
            [sys.executable, str(SCRIPTS / "kb_lint.py"), "--root", str(self.root), "--today", "2026-10-12"],
            capture_output=True,
            text=True,
            timeout=30,
        )

    def test_exit_1_on_errors(self):
        self.write("a.md", "# No front matter\n")
        result = self.run_cli()
        self.assertEqual(result.returncode, 1)
        self.assertIn("knowledge/a.md", result.stdout)

    def test_exit_0_on_warnings_only(self):
        self.write("a.md", page(updated="2026-01-01"))
        result = self.run_cli()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("warning", result.stdout)


if __name__ == "__main__":
    unittest.main()
