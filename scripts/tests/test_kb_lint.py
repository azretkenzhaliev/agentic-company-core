"""Tests for scripts/kb_lint.py."""

import contextlib
import io
import os
import re
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

import kb_lint  # noqa: E402
from kb_lint import KB, SWEEP_STAMPS, lint  # noqa: E402

TODAY = date(2026, 10, 12)
EVENING = datetime(2026, 1, 8, 18, 30, tzinfo=timezone.utc).timestamp()  # 00:30 on 2026-01-09 six hours ahead
MIDNIGHT = datetime(2026, 1, 9, 0, 5, tzinfo=timezone.utc).timestamp()


@contextlib.contextmanager
def ahead_of_utc():
    """A machine's zone at UTC+6, so a local date runs ahead of the logs' UTC one from 18:00Z."""
    old = os.environ.get("TZ")
    os.environ["TZ"] = "Asia/Dhaka"
    time.tzset()
    try:
        yield
    finally:
        if old is None:
            del os.environ["TZ"]
        else:
            os.environ["TZ"] = old
        time.tzset()


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
        for i, owner in enumerate(("board", "ceo", "cto", "analyst", "staff-engineer", "cmo", "content-producer", "performance-analyst", "ux-expert")):
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


class WorktreeLinks(KbLintTestCase):
    """workspaces/ is gitignored, so a worktree has none of it: run from one, a link into it is looked up in the main
    checkout."""

    def setUp(self):
        super().setUp()
        self.main = Path(self.tmp.name).resolve() / "main"
        (self.main / ".git" / "worktrees" / "wt").mkdir(parents=True)
        (self.main / ".git" / "worktrees" / "wt" / "commondir").write_text("../..\n")
        self.worktree = self.main / ".claude" / "worktrees" / "wt"
        self.worktree.mkdir(parents=True)
        (self.worktree / ".git").write_text(f"gitdir: {self.main}/.git/worktrees/wt\n")
        (self.main / "workspaces" / "p" / "content").mkdir(parents=True)
        (self.main / "workspaces" / "p" / "content" / "a.md").write_text("x")
        self.root = self.worktree / "knowledge"

    def test_main_checkout(self):
        self.assertEqual(kb_lint.main_checkout(self.worktree), self.main)
        self.assertEqual(kb_lint.main_checkout(self.main), self.main)  # .git is a folder
        self.assertEqual(kb_lint.main_checkout(self.main / "workspaces"), self.main / "workspaces")  # no git at all

    def test_from_a_worktree_a_workspaces_link_is_found_in_the_main_checkout(self):
        body = "[a](../workspaces/p/content/a.md) [b](../workspaces/p/content/b.md)\n"
        self.write("x.md", page(body=body, related="[../workspaces/p/content/a.md]"))
        messages = self.messages()
        self.assertEqual(len(messages), 1, messages)
        self.assertIn("b.md", messages[0])  # missing in the main checkout as well

    def test_from_a_worktree_only_workspaces_links_fall_back(self):
        (self.main / "scripts").mkdir()
        (self.main / "scripts" / "s.py").write_text("x")
        self.write("x.md", page(body="[s](../scripts/s.py) [t](../workspaces/../scripts/s.py)\n"))
        self.assertEqual(len(self.messages()), 2, self.messages())  # each resolves outside the worktree's workspaces/

    def test_from_the_main_checkout_nothing_changes(self):
        self.root = self.main / "knowledge"
        self.write("x.md", page(body="[a](../workspaces/p/content/a.md) [b](../workspaces/p/content/b.md)\n"))
        messages = self.messages()
        self.assertEqual(len(messages), 1, messages)
        self.assertIn("b.md", messages[0])


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


class SystemCheckRows(KbLintTestCase):
    """A System check row the system-check skill's grep misses is an error."""

    LOG = "## Status log\n\n| Date | Who | Event |\n|---|---|---|\n"
    FULL = "| 2026-01-13 | ceo | System check 2026-01-13T20:10:30Z: HEAD 12345678; .git/hooks: none |\n"

    def directive(self, *rows, name="board/directives/D-1.md", **fields):
        path = self.write(name, page(body=self.LOG + "".join(rows), **fields))
        return path.relative_to(self.root.parent).as_posix(), path.read_text().splitlines()

    def test_a_time_only_row_is_an_error_naming_its_file_and_line(self):
        rel, lines = self.directive(self.FULL, "| 2026-01-13 | ceo | System check 17:30:30Z (step 3): HEAD 1 |\n")
        errors = self.findings("error")
        self.assertEqual([(f.path, f.line) for f in errors], [(rel, len(lines))])
        self.assertIn("System check <YYYY-MM-DDTHH:MM[:SS]Z>", errors[0].message)
        self.assertIn(".claude/skills/system-check/SKILL.md", errors[0].message)

    def test_the_full_form_with_or_without_seconds_is_clean(self):
        self.directive(self.FULL, "| 2026-01-14 | ceo | System check 2026-01-14T06:00Z (step 1, before ORDER /5): HEAD 2 |\n")
        self.assertEqual(self.findings(), [])

    def test_a_row_that_mentions_a_system_check_mid_text_is_clean(self):
        self.directive("| 2026-01-13 | ceo | Landed /4; the system check 19:30:00Z found nothing |\n",
                       "| 2026-01-13 | ceo | Decided: run the System check 20:00Z after the report |\n")
        self.assertEqual(self.findings(), [])

    def test_other_forms_the_grep_misses_are_errors_too(self):
        for row in ("| 2026-01-14 | ceo | system check 2026-01-14T06:00Z: HEAD 1 |",  # the grep is case-sensitive
                    "| 2026-01-14 | CEO | System check 2026-01-14T06:00Z: HEAD 1 |",
                    "| 14 Jan 2026 | ceo | System check 2026-01-14T06:00Z: HEAD 1 |",  # not a date the grep reads
                    "  | 2026-01-14 | ceo | System check 2026-01-14T06:00Z: HEAD 1 |",  # indented
                    "| 2026-01-14 | ceo |  System check 2026-01-14T06:00Z: HEAD 1 |",  # two spaces
                    "| 2026-01-14 | ceo | System check 23:00Z logged and committed alone |"):
            with self.subTest(row=row):
                self.directive(row + "\n")
                self.assertEqual(len(self.findings("error")), 1)

    def test_old_rows_have_no_exemption(self):
        old = ["| 2026-01-06 | ceo | System check 14:00Z: HEAD 1111111; sha256 x |\n",
               "| 2026-01-06 | ceo | System check 13:00Z: HEAD 2222222; sha256 x |\n",
               "| 2026-01-12 | ceo | System check 23:00Z logged and committed alone (3333333): nothing differs |\n"]
        rel, lines = self.directive(*old, name="board/directives/D-1-archive-9.md", status="archived")
        first = len(lines) - len(old) + 1
        self.assertEqual([(f.path, f.line) for f in self.findings("error")],
                         [(rel, n) for n in range(first, len(lines) + 1)])

    def test_only_directives_are_checked(self):
        self.write("company/log.md", page(body=self.LOG + "| 2026-01-13 | ceo | System check 17:30:30Z: HEAD 1 |\n"))
        self.assertEqual(self.findings(), [])

    def test_an_archived_directive_is_checked_too(self):
        self.directive("| 2026-01-13 | ceo | System check 17:30:30Z: HEAD 1 |\n",
                       name="board/directives/D-1-archive-1.md", status="archived")
        self.assertEqual(len(self.findings("error")), 1)

    def test_the_regex_is_the_system_check_skill_s_grep(self):
        skill = (SCRIPTS.parent / ".claude" / "skills" / "system-check" / "SKILL.md").read_text(encoding="utf-8")
        greps = re.findall(r'`git grep -hE "([^"]+)" HEAD -- knowledge/board/directives/`', skill)
        self.assertEqual(greps, [kb_lint.SYSTEM_CHECK_GREP.pattern])
        self.assertEqual(kb_lint.SYSTEM_CHECK_DIR, "board/directives/")


class SizeLimits(KbLintTestCase):
    def sized(self, rel, kb, **overrides):
        """A page of exactly `kb` KB, with these front matter fields."""
        head = page("", **overrides)
        return self.write(rel, head + "x" * (kb * 1024 - len(head)))

    def size_errors(self):
        return [f for f in self.findings("error") if "KB limit" in f.message]

    def test_a_current_state_page_over_its_limit_is_an_error(self):
        self.sized("company/a.md", 26)
        errors = self.size_errors()
        self.assertEqual([(f.path, f.line) for f in errors], [("knowledge/company/a.md", 1)])
        self.assertIn("26.0 KB, over the 25 KB limit for a current-state page", errors[0].message)
        self.assertIn("status: archived", errors[0].message)

    def test_a_page_kb_sweep_cant_move_says_to_move_its_history_by_hand(self):
        """The marketing roles' hooks refuse kb_sweep.py. The message only; the limit is the same."""
        hand = ("26.0 KB, over the 25 KB limit for a current-state page; move history by hand, word for word, to a "
                "sibling page with status: archived (kb_sweep.py moves only ceo and cto pages)")
        for owner in ("cmo", "content-producer", "performance-analyst"):
            with self.subTest(owner=owner):
                path = self.sized("marketing/a.md", 26, owner=owner)
                self.assertEqual([f.message for f in self.size_errors()], [hand])
                path.write_text(path.read_text()[:25 * 1024])
                self.assertEqual(self.size_errors(), [])
        for owner in ("ceo", "cto"):
            with self.subTest(owner=owner):
                self.sized("marketing/a.md", 26, owner=owner)
                [error] = self.size_errors()
                self.assertTrue(error.message.endswith("; move history to a sibling page with status: archived"))

    def test_the_limit_itself_is_allowed(self):
        self.sized("company/a.md", 25)
        self.assertEqual(self.size_errors(), [])

    def test_one_byte_over_is_over(self):
        path = self.sized("company/a.md", 25)
        path.write_text(path.read_text() + "x")
        self.assertEqual(len(self.size_errors()), 1)

    def test_each_kind_has_its_limit(self):
        for rel, kb, kind in (("engineering/designs/DD-001-a.md", 60, "a design"),
                              ("engineering/roadmaps/RM-001-a.md", 60, "a roadmap"),
                              ("engineering/runbooks/a.md", 60, "a runbook"),
                              ("engineering/standards/a.md", 30, "a standards page"),
                              ("board/directives/a.md", 100, "a directive"),
                              ("board/attachments/a.md", 100, "an attachment"),
                              ("board/answers/2026-W03.md", 100, "the Board's answers, a week"),
                              ("research/a.md", 100, "a research note")):
            with self.subTest(rel):
                path = self.sized(rel, kb)
                self.assertEqual(self.size_errors(), [])
                self.sized(rel, kb + 1)
                errors = self.size_errors()
                self.assertEqual(len(errors), 1)
                self.assertIn(f"over the {kb} KB limit for {kind}", errors[0].message)
                path.unlink()

    def test_a_folder_only_counts_at_the_kb_root(self):
        self.sized("products/x/research/a.md", 26)
        self.assertEqual(len(self.size_errors()), 1)

    def test_archive_pages_are_exempt(self):
        self.sized("engineering/standards/lessons-learned-archive.md", 200, status="archived")
        self.assertEqual(self.size_errors(), [])

    def test_only_the_archived_status_is_exempt(self):
        self.sized("company/a.md", 26, status="superseded")
        self.assertEqual(len(self.size_errors()), 1)

    def test_a_listed_page_passes_silently(self):
        self.sized("company/a.md", 26)
        self.write("oversize-pages.txt", "# today's pages\n\ncompany/a.md  # a note\n")
        self.assertEqual(self.findings(), [])

    def test_the_list_covers_only_the_pages_it_names(self):
        self.sized("company/a.md", 26)
        self.sized("company/b.md", 26)
        self.write("oversize-pages.txt", "company/a.md\n")
        self.assertEqual([f.path for f in self.size_errors()], ["knowledge/company/b.md"])

    def test_a_listed_page_within_its_limit_warns_so_the_list_empties(self):
        self.sized("company/a.md", 10)
        self.write("oversize-pages.txt", "company/a.md\n")
        self.assertEqual(self.messages("error"), [])
        warnings = self.findings("warning")
        self.assertEqual([f.path for f in warnings], ["knowledge/company/a.md"])
        self.assertIn("remove it from oversize-pages.txt", warnings[0].message)

    def test_a_listed_page_that_was_archived_warns_too(self):
        self.sized("company/a.md", 26, status="archived")
        self.write("oversize-pages.txt", "company/a.md\n")
        self.assertIn("remove it from", self.messages("warning")[0])

    def test_a_line_with_no_page_warns_with_its_line_number(self):
        self.write("oversize-pages.txt", "# a comment\ncompany/gone.md\n")
        warnings = self.findings("warning")
        self.assertEqual([(f.path, f.line) for f in warnings], [("knowledge/oversize-pages.txt", 2)])
        self.assertIn("no page company/gone.md", warnings[0].message)

    def test_templates_have_no_limit(self):
        self.sized("_templates/a.md", 26)
        self.assertEqual(self.size_errors(), [])

    def test_the_board_s_preferences_have_their_own_limit(self):
        """80 KB (that page only), never raised for room: the page is grouped and summarized."""
        self.assertEqual(kb_lint.PAGE_LIMITS["company/board-preferences.md"][1], 80)
        path = self.sized("company/board-preferences.md", 80)
        self.assertEqual(self.size_errors(), [])
        self.sized("company/board-preferences.md", 81)
        [error] = self.size_errors()
        self.assertIn("over the 80 KB limit for the Board's preferences", error.message)
        self.assertIn("group overlapping rules and summarize them, never a higher limit", error.message)
        path.unlink()
        for rel in ("company/board-preferences-archive.md", "products/x/board-preferences.md", "company/a.md"):
            with self.subTest(rel):
                path = self.sized(rel, 26)
                [error] = self.size_errors()
                self.assertIn("over the 25 KB limit for a current-state page", error.message)
                self.assertNotIn("group overlapping rules", error.message)
                path.unlink()

    def test_the_desk_s_q_and_a_and_asks_name_the_sweep_when_over(self):
        """kb_sweep.py moves their oldest entries until they fit; other pages of the folder keep the plain line."""
        for name in ("qa.md", "asks.md", "progress.md"):
            with self.subTest(name):
                path = self.sized(f"company/board-desk/{name}", 26)
                [error] = self.size_errors()
                self.assertIn("over the 25 KB limit for a current-state page", error.message)
                said = "kb_sweep.py --apply --owner ceo moves its oldest entries, word for word, until it fits"
                (self.assertIn if name != "progress.md" else self.assertNotIn)(said, error.message)
                path.unlink()


class WorkLogs(KbLintTestCase):
    """ceo-questions.md and board-steps.md, outside the KB."""

    def log(self, name, size, product="p", folder="content", text="# Order /1\n"):
        path = self.root.parent / "workspaces" / product / folder / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text + "x" * (size - len(text.encode("utf-8"))), encoding="utf-8")
        return path

    def test_each_file_has_its_limit(self):
        for name, kb in [("ceo-questions.md", 30), ("board-steps.md", 20)]:
            with self.subTest(name=name):
                path = self.log(name, int(kb * 1024 * 0.9) - 1)
                self.assertEqual(self.findings(), [])
                self.log(name, kb * 1024)
                self.assertIn("sweep due", self.findings("warning")[0].message)
                self.log(name, kb * 1024 + 1)
                self.assertEqual(self.messages(), [])  # a warning, never an error
                [warning] = self.findings("warning")
                self.assertEqual(warning.path, f"workspaces/p/content/{name}")
                self.assertIn(f"over about {kb} KB", warning.message)
                path.unlink()

    def test_the_warning_names_what_to_archive(self):
        self.log("ceo-questions.md", 31 * 1024, text="# Questions\n# Short\n# Order /2\n" + "y" * 500 + "\n# Order /1\n")
        [warning] = self.findings("warning")
        self.assertIn("answered lines and closed orders", warning.message)
        self.assertIn("ceo-questions-archive.md", warning.message)
        self.assertIn("largest sections: # Order /1 (30.5 KB); # Order /2 (0.5 KB); # Questions (0.0 KB))", warning.message)
        self.assertNotIn("# Short", warning.message)  # three at most
        self.log("board-steps.md", 21 * 1024, text="## Now\n### B-7. A step\n")
        step = [f for f in self.findings("warning") if "board-steps" in f.path][0]
        self.assertIn("done, dropped, waived and obsolete steps", step.message)
        self.assertIn("board-steps-archive.md", step.message)
        self.assertIn("### B-7. A step", step.message)

    def test_a_code_fence_holds_a_ceo_questions_page_and_its_sweep_line_says_so(self):
        hold = "line 3 is a code fence, so no section here moves: move sections by hand or remove the fence"
        path = self.log("ceo-questions.md", 30 * 1024, text="# Order /1\n\n```\n\n")
        self.assertTrue(self.findings("warning")[0].message.endswith(f"a finished order's sections; {hold}"))
        self.log("ceo-questions.md", 30 * 1024)
        self.assertNotIn("code fence", self.findings("warning")[0].message)
        path.unlink()
        self.log("board-steps.md", 20 * 1024, text="## Now\n\n```\n\n")
        self.assertNotIn("code fence", self.findings("warning")[0].message)

    def test_a_ceo_questions_sweep_line_names_cq_archive_and_kb_sweep_keeps_its_pages(self):
        """kb_sweep.py moves only `# ` sections with a CLOSED line, nothing of `## ORDER` ones; cq_archive.py moves
        a ceo-questions.md's handled lines. kb_sweep.py doesn't move board-steps.md either: its line says what to move
        by hand, as its over-limit line does."""
        for product in ("a", "b"):
            self.log("ceo-questions.md", 30 * 1024, product=product, text="## ORDER D-20260112-x/1 (CTO)\n")
        self.log("board-steps.md", 20 * 1024, product="a")
        self.write("board/directives/D-20260101-x.md", page("x" * 95 * KB))
        self.write("engineering/standards/lessons-learned.md", page("x" * 28 * KB, owner="cto"))
        due = {f.path: f.message for f in self.findings("warning")}
        base = self.root.parent.resolve()
        for product in ("a", "b"):
            path = f"workspaces/{product}/content/ceo-questions.md"
            self.assertEqual(due[path], f"sweep due: 30.0 KB, within 10% of its 30 KB limit (owner: cto); "
                                        f"python3 {base}/scripts/cq_archive.py {base}/{path} --dry-run shows what "
                                        "would move; "
                                        "without --dry-run it moves the handled lines, and with --closed <order id> "
                                        "a finished order's sections")
        self.assertEqual(due["workspaces/a/content/board-steps.md"], "sweep due: 20.0 KB, within 10% of its 20 KB "
                         "limit (owner: cto); move done, dropped, waived and obsolete steps, verbatim, to "
                         "board-steps-archive.md")
        for path in ("knowledge/board/directives/D-20260101-x.md", "knowledge/engineering/standards/lessons-learned.md"):
            self.assertRegex(due[path], r"^sweep due: .*; python3 scripts/kb_sweep\.py shows what would move$")

    def test_an_over_limit_ceo_questions_line_names_cq_archive_too(self):
        """The line its owner sees once the file is over; board-steps.md's stays."""
        self.log("ceo-questions.md", 31 * 1024, text="## ORDER D-20260112-x/1 (CTO)\n")
        self.log("board-steps.md", 21 * 1024, text="## Now\n")
        over = {f.path: f.message for f in self.findings("warning")}
        path = "workspaces/p/content/ceo-questions.md"
        base = self.root.parent.resolve()
        self.assertEqual(over[path], "31.0 KB, over about 30 KB; move answered lines and closed orders, verbatim, to "
                                     "ceo-questions-archive.md (largest sections: ## ORDER D-20260112-x/1 (CTO) "
                                     f"(31.0 KB)); python3 {base}/scripts/cq_archive.py {base}/{path} --dry-run shows "
                                     "what would move; without --dry-run it moves the handled lines, and with --closed "
                                     "<order id> a finished order's sections")
        self.assertEqual(over["workspaces/p/content/board-steps.md"], "21.0 KB, over about 20 KB; move done, dropped, "
                         "waived and obsolete steps, verbatim, to board-steps-archive.md (largest sections: ## Now "
                         "(21.0 KB))")

    def test_a_ceo_questions_page_that_cant_be_read_keeps_its_sweep_line(self):
        path = self.log("ceo-questions.md", 30 * 1024)
        path.chmod(0)
        self.assertIn("sweep due", self.findings("warning")[0].message)

    def test_every_product_is_checked(self):
        self.log("ceo-questions.md", 31 * 1024, product="a")
        self.log("ceo-questions.md", 31 * 1024, product="b")
        self.assertEqual([f.path for f in self.findings("warning")],
                         ["workspaces/a/content/ceo-questions.md", "workspaces/b/content/ceo-questions.md"])

    def test_archives_and_other_folders_are_left_alone(self):
        self.log("ceo-questions-archive.md", 400 * 1024)
        self.log("board-steps-archive.md", 80 * 1024)
        self.log("ceo-questions.md", 31 * 1024, folder="reviews")
        self.assertEqual(self.findings(), [])

    def test_no_headings_still_warns(self):
        self.log("board-steps.md", 21 * 1024, text="")
        self.assertIn("largest sections: none", self.findings("warning")[0].message)

    def test_bad_bytes_and_long_headings(self):
        path = self.log("board-steps.md", 21 * 1024, text="### B-1. " + "z" * 200 + "\n")
        path.write_bytes(path.read_bytes() + b"\xff")
        self.assertIn("### B-1. " + "z" * 51 + " (", self.findings("warning")[0].message)


class SweepDue(KbLintTestCase):
    """The trigger for scripts/kb_sweep.py: /report reads these."""

    def sized(self, rel, size, **overrides):
        head = page("", **overrides)
        return self.write(rel, head + "x" * (size - len(head)))

    def due(self):
        return [f for f in self.findings("warning") if f.message.startswith("sweep due")]

    def test_within_10_percent_of_the_limit_is_due_and_says_whose(self):
        self.sized("company/a.md", int(25 * KB * 0.9))
        [finding] = self.due()
        self.assertEqual(finding.path, "knowledge/company/a.md")
        self.assertIn("within 10% of its 25 KB limit (owner: ceo)", finding.message)

    def test_a_page_kb_sweep_cant_move_names_the_move_by_hand_not_kb_sweep(self):
        """The marketing roles' hooks refuse kb_sweep.py."""
        self.sized("marketing/a.md", 25 * KB, owner="cmo")
        [finding] = self.due()
        self.assertEqual(finding.message, "sweep due: 25.0 KB, within 10% of its 25 KB limit (owner: cmo); move history "
                                          "by hand, word for word, to a sibling page with status: archived (kb_sweep.py "
                                          "moves only ceo and cto pages)")
        self.sized("marketing/a.md", 25 * KB, owner="cto")
        [finding] = self.due()
        self.assertTrue(finding.message.endswith("(owner: cto); python3 scripts/kb_sweep.py shows what would move"))

    def test_one_byte_below_the_band_is_quiet(self):
        self.sized("company/a.md", int(25 * KB * 0.9) - 1)
        self.assertEqual(self.findings(), [])

    def test_the_band_follows_each_kind_of_page(self):
        self.sized("board/directives/a.md", 89 * KB)
        self.sized("engineering/designs/b.md", 55 * KB)
        self.assertEqual([f.path for f in self.due()], ["knowledge/engineering/designs/b.md"])

    def test_the_board_s_preferences_are_due_near_their_own_limit_and_say_what_stays(self):
        self.sized("company/board-preferences.md", 72 * KB - 1)
        self.assertEqual(self.due(), [])
        self.sized("company/board-preferences.md", 72 * KB)  # 90% of 80 KB
        [finding] = self.due()
        self.assertIn("within 10% of its 80 KB limit (owner: ceo)", finding.message)
        self.assertIn("group overlapping rules and summarize them, never a higher limit; what to do, numbers "
                      "and scope stay (ceo.md, \"Keep board-preferences.md\")", finding.message)
        self.assertNotIn("only history and repeats", finding.message)

    def test_the_limit_itself_is_due_and_over_it_is_an_error_instead(self):
        path = self.sized("company/a.md", 25 * KB)
        self.assertEqual(len(self.due()), 1)
        path.write_text(path.read_text() + "x")
        self.assertEqual(self.due(), [])
        self.assertEqual(len(self.findings("error")), 1)

    def test_archived_and_listed_pages_are_not_due(self):
        self.sized("company/a.md", 24 * KB, status="archived")
        self.sized("company/b.md", 26 * KB)
        self.write("oversize-pages.txt", "company/b.md\n")
        self.assertEqual(self.due(), [])

    def test_a_work_log_in_the_band_says_the_owner(self):
        log = self.root.parent / "workspaces" / "p" / "content" / "ceo-questions.md"
        log.parent.mkdir(parents=True)
        log.write_text("x" * (28 * KB))
        [finding] = self.due()
        self.assertEqual(finding.path, "workspaces/p/content/ceo-questions.md")
        self.assertIn("(owner: cto)", finding.message)

    def test_no_stamp_file_is_a_bare_kb_and_quiet(self):
        self.assertEqual(self.due(), [])

    def test_an_owner_with_no_line_is_due_at_once(self):
        self.write(SWEEP_STAMPS, "# a comment\nceo 2026-10-12\n")
        [finding] = self.due()
        self.assertEqual(finding.path, f"knowledge/{SWEEP_STAMPS}")
        self.assertIn("cto: none recorded", finding.message)

    def test_14_days_since_the_sweep_is_due_and_13_is_not(self):
        self.write(SWEEP_STAMPS, "ceo 2026-09-29\ncto 2026-09-28\n")  # TODAY is 2026-10-12
        [finding] = self.due()
        self.assertIn("cto: the last was 2026-09-28, 14 days ago", finding.message)

    def test_a_stamp_that_isnt_a_date_counts_as_never(self):
        self.write(SWEEP_STAMPS, "ceo soon\ncto 2026-13-99\n")
        self.assertEqual(len(self.due()), 2)


class TriggersCantRaise(KbLintTestCase):
    """The sweep lines are new: bad input in them must never stop the linter for CI or any role that runs it."""

    def work_log(self, text):
        path = self.root.parent / "workspaces" / "p" / "content" / "ceo-questions.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def test_a_nul_in_a_summarys_link_stays_a_plain_broken_link(self):
        self.write("a.md", page("## Past, in short (to 2026-10-01)\n\n[x](a%00b.md)\n"))
        self.assertIn("broken link -> a%00b.md", self.messages()[0])

    def test_a_very_long_link_in_a_work_logs_summary(self):
        self.work_log(f"# Past, in short\n\n[x]({'a' * 300}.md)\n")
        self.assertEqual(self.findings(), [])

    def test_a_dangling_archive_beside_a_work_log(self):
        log = self.work_log("# Past, in short (to 2026-10-01)\n\nThe past.\n")
        log.with_name("ceo-questions-archive.md").symlink_to(log.with_name("gone.md"))
        self.assertEqual(self.findings(), [])

    def test_a_bad_byte_in_the_stamp_file_counts_as_no_stamp(self):
        (self.root / SWEEP_STAMPS).write_bytes(b"ceo \xff\ncto 2026-10-12\n")
        [finding] = self.findings("warning")
        self.assertIn("ceo: none recorded", finding.message)

    def test_any_error_in_a_trigger_leaves_the_other_checks_running(self):
        self.write("a.md", page("# Page\n\n[gone](gone.md)\n"))
        self.write(SWEEP_STAMPS, "")
        for error in (OSError, ValueError):
            for trigger in ("lint_summary", "read_sweep_stamps"):
                with self.subTest(error=error, trigger=trigger), mock.patch(f"kb_lint.{trigger}", side_effect=error):
                    self.assertEqual(len(self.findings("error")), 1)

    def test_a_secret_on_the_page_stays_an_error_while_a_trigger_raises(self):
        self.write("a.md", page(body=f"token: {'gh' + 'p_' + 'a1B2c3D4e5' * 3 + 'f6G7h8'}\n"))
        with mock.patch("kb_lint.lint_summary", side_effect=ValueError):
            self.assertIn("GitHub token", self.findings("error")[0].message)

    def test_only_a_triggers_expected_errors_are_quiet_and_the_secrets_check_stays_loud(self):
        self.write("a.md", page("# Page\n"))
        for name, error in (("lint_summary", RuntimeError), ("find_secrets", ValueError), ("find_secrets", OSError)):
            with self.subTest(name=name, error=error), mock.patch(f"kb_lint.{name}", side_effect=error):
                with self.assertRaises(error):
                    self.findings()


class SummaryAge(KbLintTestCase):
    """A "Past, in short" older than the cold text it stands for: the tool names it, its owner refreshes it."""

    def hot(self, summary):
        return self.write("engineering/standards/a.md", page(f"# A\n\n{summary}\n\n## Now\n\nLater text from 2027-01-01.\n", owner="cto"))

    def cold(self, updated):
        self.write("engineering/standards/a-archive.md", page("# Cold\n\n[a](a.md)\n", status="archived", updated=updated, owner="cto"))

    def due(self):
        return [f for f in self.findings("warning") if "Past, in short" in f.message]

    def test_older_than_the_cold_text_is_named_with_its_owner_and_line(self):
        self.hot("## Past, in short (to 2026-10-01)\n\nThe past. [cold](a-archive.md)")
        self.cold("2026-10-05")
        [finding] = self.due()
        self.assertEqual((finding.path, finding.line), ("knowledge/engineering/standards/a.md", 11))
        self.assertIn('"Past, in short" (2026-10-01) is older than a-archive.md (2026-10-05)', finding.message)
        self.assertIn("its owner (cto) refreshes it", finding.message)

    def test_as_new_as_the_cold_text_is_quiet(self):
        self.hot("## Past, in short (to 2026-10-05)\n\nThe past. [cold](a-archive.md)")
        self.cold("2026-10-05")
        self.assertEqual(self.due(), [])

    def test_its_date_is_the_newest_in_its_own_section_only(self):
        self.hot("## Past, in short\n\nOn 2026-09-01 and 2026-10-02. [cold](a-archive.md)")
        self.cold("2026-10-05")
        self.assertIn("(2026-10-02)", self.due()[0].message)

    def test_the_date_on_its_heading_wins_over_later_dates_in_its_text(self):
        self.hot("## Past, in short (to 2026-10-01)\n\nA plan for 2027-01-01. [cold](a-archive.md)")
        self.cold("2026-10-05")
        self.assertIn("(2026-10-01)", self.due()[0].message)

    def test_undated_is_named(self):
        self.hot("## Past, in short\n\nThe past. [cold](a-archive.md)")
        self.cold("2026-10-05")
        self.assertIn("(undated)", self.due()[0].message)

    def test_a_sibling_archive_counts_without_a_link(self):
        self.hot("## Past, in short (to 2026-10-01)\n\nThe past.")
        self.cold("2026-10-05")
        self.assertEqual(len(self.due()), 1)

    def test_a_numbered_archive_the_sweep_writes_counts_without_a_link(self):
        self.hot("## Past, in short (to 2026-10-01)\n\nThe past.")
        self.write("engineering/standards/a-archive-2.md", page("# Cold\n\n[a](a.md)\n", status="archived", updated="2026-10-05", owner="cto"))
        self.assertIn("a-archive-2.md", self.due()[0].message)

    def test_a_link_is_opened_only_if_its_a_page_inside_the_repo(self):
        secret = self.root.parent.parent / "archive-outside.md"
        env = self.root.parent / ".env"
        self.addCleanup(secret.unlink, missing_ok=True)
        secret.write_text(page("# Outside\n", status="archived", updated="2026-10-05"))
        env.write_text("A_VALUE=x\n")
        self.hot("## Past, in short (to 2026-10-01)\n\n[out](../../../../archive-outside.md) and [env](../../../.env)")
        opened = []
        real = Path.read_text

        def spy(path, *args, **kwargs):
            opened.append(path.name)
            return real(path, *args, **kwargs)

        with mock.patch.object(Path, "read_text", spy):
            self.assertEqual(self.due(), [])
        self.assertNotIn(".env", opened)
        self.assertNotIn("archive-outside.md", opened)

    def test_a_page_with_no_cold_page_or_no_summary_is_quiet(self):
        self.hot("## Past, in short (to 2026-10-01)\n\nThe past.")
        self.assertEqual(self.due(), [])
        self.hot("## Other\n\n[cold](a-archive.md)")
        self.cold("2026-10-05")
        self.assertEqual(self.due(), [])

    def test_a_link_to_a_hot_page_isnt_cold_text(self):
        self.hot("## Past, in short (to 2026-10-01)\n\n[other](b.md)")
        self.write("engineering/standards/b.md", page("# B\n\n[a](a.md)\n", owner="cto", updated="2026-10-12"))
        self.assertEqual(self.due(), [])

    def test_a_work_log_uses_the_date_of_its_archive_file(self):
        folder = self.root.parent / "workspaces" / "p" / "content"
        folder.mkdir(parents=True)
        (folder / "ceo-questions.md").write_text("# Past, in short (to 2020-01-01)\n\nThe past.\n")
        (folder / "ceo-questions-archive.md").write_text("# Closed\n")
        [finding] = self.due()
        self.assertEqual(finding.path, "workspaces/p/content/ceo-questions.md")
        self.assertIn("older than ceo-questions-archive.md", finding.message)


class UtcDates(KbLintTestCase):
    """Today and a file's date are UTC dates, as the logs write them."""

    def run_main(self, now):
        out = io.StringIO()
        with ahead_of_utc(), mock.patch("time.time", return_value=now), contextlib.redirect_stdout(out):
            kb_lint.main(["--root", str(self.root)])
        return out.getvalue()

    def test_a_timestamp_has_its_utc_date(self):
        with ahead_of_utc():
            self.assertEqual(datetime.fromtimestamp(EVENING).date(), date(2026, 1, 9))  # the old reading
            self.assertEqual(kb_lint.utc_date(EVENING), date(2026, 1, 8))
            self.assertEqual(kb_lint.utc_date(MIDNIGHT), date(2026, 1, 9))

    def test_today_is_the_utc_date(self):
        self.write("a.md", page(updated="2025-10-11"))  # 89 days before 2026-01-08, 90 before 2026-01-09
        self.assertNotIn("not updated for", self.run_main(EVENING))
        self.assertIn("a.md:5: warning: not updated for 90 days", self.run_main(MIDNIGHT))

    def test_a_file_without_updated_has_its_utc_date(self):
        folder = self.root.parent / "workspaces" / "p" / "content"
        folder.mkdir(parents=True)
        (folder / "ceo-questions.md").write_text("# Past, in short (to 2026-01-08)\n\nThe past.\n")
        archive = folder / "ceo-questions-archive.md"
        archive.write_text("# Closed\n")
        os.utime(archive, (EVENING, EVENING))
        with ahead_of_utc():
            self.assertEqual(kb_lint.cold_since(archive), date(2026, 1, 8))
        self.assertNotIn("Past, in short", self.run_main(EVENING))
        os.utime(archive, (MIDNIGHT, MIDNIGHT))
        self.assertIn("is older than ceo-questions-archive.md (2026-01-09)", self.run_main(MIDNIGHT))


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

    def test_exit_0_on_a_work_log_warning(self):
        path = self.root.parent / "workspaces" / "p" / "content" / "board-steps.md"
        path.parent.mkdir(parents=True)
        path.write_text("x" * (21 * 1024))
        result = self.run_cli()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("workspaces/p/content/board-steps.md:1: warning:", result.stdout)

    def test_exit_0_when_a_sweep_is_due(self):
        self.write(SWEEP_STAMPS, "")
        result = self.run_cli()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn(f"knowledge/{SWEEP_STAMPS}:1: warning: sweep due: ceo: none recorded", result.stdout)

    def test_exit_0_on_warnings_only(self):
        self.write("a.md", page(updated="2026-01-01"))
        result = self.run_cli()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("warning", result.stdout)


if __name__ == "__main__":
    unittest.main()
