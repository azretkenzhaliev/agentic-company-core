"""Tests for scripts/kb_sweep.py.

Every page is built in a temporary folder and every transcript is made up: nothing here reads a real session log."""

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

import capacity_scan  # noqa: E402
import kb_sweep  # noqa: E402
from kb_lint import SWEEP_STAMPS, lint  # noqa: E402
from kb_sweep import AGE_DAYS, HOT_OPENS, apply_move, main, plan  # noqa: E402

TODAY = date(2026, 11, 20)
KB = 1024
DIRECTIVE = "D-20260101-x"
EVENING = datetime(2026, 1, 8, 18, 30, tzinfo=timezone.utc).timestamp()  # 00:30 on 2026-01-09 six hours ahead
MIDNIGHT = datetime(2026, 1, 9, 0, 5, tzinfo=timezone.utc).timestamp()
CLOCK = datetime(TODAY.year, TODAY.month, TODAY.day, 12, tzinfo=timezone.utc).timestamp()  # the clock run_main runs at


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


def ago(days):
    return (TODAY - timedelta(days=days)).isoformat()


def age_file(path, days=0):
    """Give a file a date from TODAY, not the clock's."""
    stamp = datetime(TODAY.year, TODAY.month, TODAY.day, tzinfo=timezone.utc).timestamp() - days * 86400
    os.utime(path, (stamp, stamp))


def front(owner="ceo", status="active", updated="2026-10-01", related="[]", title="A page"):
    return f"---\ntitle: {title}\nowner: {owner}\nstatus: {status}\nupdated: {updated}\nrelated: {related}\n---\n\n"


def status_page(rows, owner="ceo", filler=0):
    return (front(owner) + "# D\n\n## Directive (verbatim)\n\n| 2020-01-01 | board | A quoted table in the Board's words |\n\n"
            "## Status log\n\n| Date | Who | Event |\n|---|---|---|\n" + "".join(rows)
            + "\n## Open questions for the Board\n\n| 2020-01-02 | not | a status row |\n" + "x" * filler + "\n")


def row(days, text="an event", who="ceo"):
    return f"| {ago(days)} | {who} | {text} |\n"


class SweepTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name).resolve()
        self.root = self.base / "knowledge"
        self.root.mkdir()
        self.transcripts = self.base / "no-transcripts"
        self.transcripts.mkdir()
        self.write("INDEX.md", front() + "# Index\n")

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, rel, text):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text if isinstance(text, bytes) else text.encode("utf-8"))
        return path

    def questions(self, text, product="acme"):
        path = self.base / "workspaces" / product / "content" / "ceo-questions.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text if isinstance(text, bytes) else text.encode("utf-8"))
        return path

    def directive(self, rows, cold=True, **kwargs):
        page = self.write(f"board/directives/{DIRECTIVE}.md", status_page(rows, **kwargs))
        if cold:
            self.write(f"board/directives/{DIRECTIVE}-archive-1.md",
                       front(status="archived", related=f"[{DIRECTIVE}.md]")
                       + "# Cold\n\n## Orders\n\n| 2020-01-03 | old | order table |\n\n## Status log\n\n"
                         "| Date | Who | Event |\n|---|---|---|\n" + row(100, "the oldest") + "\n## Other\n\nText.\n")
        return page

    def run_main(self, *args):
        out = io.StringIO()
        argv = ["--root", str(self.root), "--today", TODAY.isoformat(), "--transcripts", str(self.transcripts), *args]
        with mock.patch("time.time", return_value=CLOCK), contextlib.redirect_stdout(out):
            code = main(argv)
        return code, out.getvalue()

    def apply(self, owner="ceo", *args):
        return self.run_main("--apply", "--owner", owner, *args)

    def snapshot(self):
        return {p: p.read_bytes() for p in self.base.rglob("*") if p.is_file()}


class StatusRows(SweepTestCase):
    def test_old_rows_move_word_for_word_after_the_cold_tables_last_row(self):
        old = row(20, "**Decided:** a | piped `row` with \"quotes\"", who="board")
        page = self.directive([old, row(14, "fourteen days stays"), row(1, "new")])
        code, _ = self.apply()
        self.assertEqual(code, 0)
        cold = page.with_name(f"{DIRECTIVE}-archive-1.md").read_text()
        self.assertIn(row(100, "the oldest") + old + "\n## Other", cold)
        self.assertNotIn(old, page.read_text())
        self.assertIn(row(14, "fourteen days stays") + row(1, "new"), page.read_text())

    def test_past_the_age_means_older_than_it(self):
        page = self.directive([row(AGE_DAYS["status"]), row(AGE_DAYS["status"] + 1, "older")])
        self.apply()
        self.assertIn(row(AGE_DAYS["status"]), page.read_text())
        self.assertNotIn("older", page.read_text())

    def test_only_the_status_log_moves(self):
        page = self.directive([row(20)])
        self.apply()
        for text in ("| 2020-01-01 | board | A quoted table in the Board's words |", "| 2020-01-02 | not | a status row |",
                     "## Open questions for the Board"):
            self.assertIn(text, page.read_text())

    def test_a_pointer_is_added_once_and_links_the_cold_page(self):
        page = self.directive([row(20), row(1)])
        self.apply()
        self.assertIn(f"## Status log\n\nRows before {ago(14)} are in [the archive]({DIRECTIVE}-archive-1.md).\n\n| Date", page.read_text())

    def test_an_existing_pointer_moves_forward_and_never_back(self):
        cold = f"{DIRECTIVE}-archive-1.md"
        for pointer_days, expected_days in ((16, 14), (5, 5)):
            with self.subTest(pointer_days):
                page = self.write(f"board/directives/{DIRECTIVE}.md", status_page([row(20)]).replace(
                    "## Status log\n\n", f"## Status log\n\nRows before {ago(pointer_days)} are in [the archive]({cold}).\n\n"))
                self.write(f"board/directives/{cold}", front(status="archived") + "## Status log\n\n| Date | Who | Event |\n|---|---|---|\n")
                self.apply()
                self.assertIn(f"Rows before {ago(expected_days)} are in [the archive]({cold}).", page.read_text())
                self.assertEqual(page.read_text().count("are in [the archive]"), 1)

    def test_updated_changes_on_both_pages(self):
        page = self.directive([row(20)])
        self.apply()
        self.assertIn(f"updated: {TODAY}", page.read_text())
        self.assertIn(f"updated: {TODAY}", page.with_name(f"{DIRECTIVE}-archive-1.md").read_text())

    def test_updated_is_the_runs_own_date_never_the_today_flag(self):
        """--today sets the ages only: `updated:` says the day the run ran."""
        for cold, filler in ((False, 95 * KB), (True, 0)):  # a new archive first, then one that exists
            with self.subTest(cold=cold):
                page = self.directive([row(20)], cold=cold, filler=filler)
                self.assertEqual(page.with_name(f"{DIRECTIVE}-archive-1.md").exists(), cold)
                argv = ["--root", str(self.root), "--today", TODAY.isoformat(), "--transcripts", str(self.transcripts), "--apply", "--owner", "ceo"]
                with mock.patch("time.time", return_value=MIDNIGHT), contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(main(argv), 0)
                for text in (page.read_text(), page.with_name(f"{DIRECTIVE}-archive-1.md").read_text()):
                    self.assertIn("\nupdated: 2026-01-09\n", text)

    def test_an_updated_line_in_the_body_is_left_alone(self):
        page = self.directive([row(20)])
        page.write_text(page.read_text().replace("updated: 2026-10-01\n", "").replace(
            "## Directive (verbatim)\n", "## Directive (verbatim)\n\nupdated: the Board's own words\n"))
        self.apply()
        self.assertIn("updated: the Board's own words", page.read_text())

    def test_a_short_directive_gets_no_archive_twin(self):
        page = self.directive([row(20)], cold=False)
        before = self.snapshot()
        _, out = self.apply()
        self.assertNotIn("Moved", out)
        self.assertFalse(page.with_name(f"{DIRECTIVE}-archive-1.md").exists())
        self.assertEqual({p: b for p, b in self.snapshot().items() if p.name != SWEEP_STAMPS}, before)

    def test_a_directive_near_its_limit_gets_a_cold_page_that_lints_clean(self):
        page = self.directive([row(20), row(1)], cold=False, filler=95 * KB)
        self.write("board/directives/README.md", front() + f"[d]({DIRECTIVE}.md)\n")
        self.write("INDEX.md", front() + "[d](board/directives/README.md)\n")
        self.apply()
        cold = page.with_name(f"{DIRECTIVE}-archive-1.md").read_text()
        self.assertIn(f"owner: ceo\nstatus: archived\nupdated: {TODAY}\nrelated: [{DIRECTIVE}.md]", cold)
        self.assertIn("## Status log\n\n| Date | Who | Event |\n|---|---|---|\n" + row(20), cold)
        self.assertEqual([f for f in lint(self.root, TODAY) if f.level == "error" or "orphan" in f.message], [])

    def test_a_page_on_the_oversize_list_moves(self):
        page = self.directive([row(20)], cold=False, filler=110 * KB)
        self.write("oversize-pages.txt", f"board/directives/{DIRECTIVE}.md\n")
        self.apply()
        self.assertTrue(page.with_name(f"{DIRECTIVE}-archive-1.md").exists())

    def test_an_archived_page_is_never_a_hot_page(self):
        page = self.directive([row(20)])  # it has a cold twin, so only its status can keep it from moving
        page.write_text(page.read_text().replace("status: active", "status: archived"))
        cold = page.with_name(f"{DIRECTIVE}-archive-1.md")
        before = page.read_bytes(), cold.read_bytes()
        self.apply()
        self.assertEqual((page.read_bytes(), cold.read_bytes()), before)

    def test_a_status_row_holding_a_stays_word_stays_and_is_named(self):
        page = self.directive([row(20, "NEEDS-CEO-NOW: which account?"), row(20, "PAUSE /5 until told"), row(20, "an old event")])
        self.assertIn("2 old rows hold a NEEDS-CEO-NOW or PAUSE", plan(self.root, TODAY)[1][0][2])
        self.apply()
        self.assertIn("NEEDS-CEO-NOW: which account?", page.read_text())
        self.assertIn("PAUSE /5 until told", page.read_text())
        self.assertNotIn("an old event", page.read_text())

    def test_the_latest_next_row_stays_whatever_its_age_and_older_ones_move(self):
        """capacity_scan.py reads it: without one the directive would be NO NEXT."""
        latest = row(20, "NEXT: the drift audit; waits: 2026-11-21")
        page = self.directive([row(30, "NEXT: an older step; waits: none"), latest, row(20, "an old event"), row(1, "new")])
        scanned = capacity_scan.next_row(page.read_text())
        self.apply()
        self.assertEqual(capacity_scan.next_row(page.read_text()), scanned)
        self.assertIn(latest + row(1, "new"), page.read_text())
        for moved in ("an older step", "an old event"):
            self.assertNotIn(moved, page.read_text())
        self.assertIn(f"Stays, ceo: knowledge/board/directives/{DIRECTIVE}.md: the latest NEXT row ({ago(20)}) stays: "
                      "capacity_scan.py reads it", self.run_main()[1])

    def test_only_held_rows_means_nothing_moves_and_they_are_named(self):
        page = self.directive([row(20, "PAUSE /5 until told")])
        moves, left = plan(self.root, TODAY)
        self.assertEqual(moves, [])
        self.assertIn("1 old rows hold", left[0][2])
        self.assertTrue(page.exists())

    def test_a_cold_page_with_no_table_or_another_owner_stays_and_is_named(self):
        for cold in (front(status="archived") + "# Cold\n",
                     front(owner="board", status="archived") + "## Status log\n\n| Date | Who | Event |\n|---|---|---|\n"):
            with self.subTest(cold):
                self.directive([row(20)])
                self.write(f"board/directives/{DIRECTIVE}-archive-1.md", cold)
                moves, left = plan(self.root, TODAY)
                self.assertEqual(moves, [])
                self.assertIn("move by hand", left[0][2])

    def test_a_row_with_an_impossible_date_stays(self):
        page = self.directive(["| 2026-13-45 | ceo | a typo |\n", row(20)])
        self.apply()
        self.assertIn("2026-13-45", page.read_text())

    def test_a_level_1_log_ends_at_the_next_heading_of_any_level(self):
        page = self.directive([row(20, "in the log")])
        page.write_text(page.read_text().replace("## Status log", "# Status log").replace(
            "## Open questions for the Board\n\n| 2020-01-02 |", "## Open questions for the Board\n\n" + row(30, "under another heading") + "| 2020-01-02 |"))
        self.apply()
        self.assertIn("under another heading", page.read_text())
        self.assertNotIn("in the log", page.read_text())

    def test_rows_land_in_the_cold_logs_own_table(self):
        page = self.directive([row(20, "moved")])
        cold = page.with_name(f"{DIRECTIVE}-archive-1.md")
        cold.write_text(cold.read_text().replace("\n## Other\n\nText.\n", "\n### Later\n\n| a table | after the log |\n|---|---|\n"))
        self.apply()
        self.assertIn(row(100, "the oldest") + row(20, "moved"), cold.read_text())


class SeveralArchives(SweepTestCase):
    """Rows go to the highest-numbered archive; the header names each archive and its dates, so kb_lint calls none an
    orphan."""
    ONE, TWO = f"{DIRECTIVE}-archive-1.md", f"{DIRECTIVE}-archive-2.md"

    def pages(self, two_log="## Status log\n\n| Date | Who | Event |\n|---|---|---|\n" + row(60, "in two") + row(45, "also in two")):
        page = self.directive([row(30, "to the newest archive"), row(1, "new")])
        page.write_text(page.read_text().replace("## Status log\n\n", (
            f"## Status log\n\nRows before {ago(40)} are in two archives: the rows of {ago(60)} to {ago(45)} are in "
            f"[archive 2]({self.TWO}); the rest are in [archive 1]({self.ONE}).\n\n")))
        two = self.write(f"board/directives/{self.TWO}", front(status="archived", related=f"[{DIRECTIVE}.md]") + "# Part 2\n\n" + two_log)
        self.write("board/directives/README.md", front() + f"[d]({DIRECTIVE}.md)\n")
        self.write("INDEX.md", front() + "[d](board/directives/README.md)\n")
        return page, page.with_name(self.ONE), two

    def test_rows_go_to_the_last_archive_and_the_header_keeps_every_link(self):
        page, one, two = self.pages()
        one_before = one.read_bytes()
        self.assertEqual(self.apply()[0], 0)
        self.assertEqual(one.read_bytes(), one_before)
        self.assertIn(row(45, "also in two") + row(30, "to the newest archive"), two.read_text())
        header = (f"Rows before {ago(14)} are in 2 archives: [archive 1]({self.ONE}), rows of {ago(100)} to {ago(100)}; "
                  f"[archive 2]({self.TWO}), rows of {ago(60)} to {ago(30)}.")
        self.assertIn(f"## Status log\n\n{header}\n\n| Date", page.read_text())
        self.assertEqual([f for f in lint(self.root, TODAY) if f.level == "error" or "orphan" in f.message], [])
        self.apply()
        self.assertEqual(page.read_text().count("Rows before "), 1)
        self.assertIn(header, page.read_text())

    def test_a_header_with_no_date_and_one_link_gets_every_archive(self):
        page, _, _ = self.pages()
        page.write_text(page.read_text().replace(
            next(line for line in page.read_text().split("\n") if line.startswith("Rows before ")),
            f"Rows before the split are in [archive 1]({self.ONE})."))
        self.apply()
        self.assertIn(f"Rows before {ago(14)} are in 2 archives: [archive 1]({self.ONE}), rows of {ago(100)} to {ago(100)}; "
                      f"[archive 2]({self.TWO}), rows of {ago(60)} to {ago(30)}.", page.read_text())

    def test_a_last_archive_with_no_log_table_moves_nothing_and_is_named(self):
        page, one, two = self.pages(two_log="| Date | Who | Event |\n|---|---|---|\n" + row(60, "in two"))
        before = page.read_bytes(), one.read_bytes(), two.read_bytes()
        self.assertIn(f"{self.TWO} has no table for this log", self.run_main()[1])
        self.apply()
        self.assertEqual((page.read_bytes(), one.read_bytes(), two.read_bytes()), before)


class LessonsRows(SweepTestCase):
    def pages(self, rows):
        page = self.write("engineering/standards/lessons-learned.md", front("cto") + (
            "# Lessons learned\n\nRows older than the table below are in [lessons-learned-archive.md](lessons-learned-archive.md).\n\n"
            "## Digest: the rules\n\n- A rule (2026-10-01).\n\n## Recent lessons\n\n| Date | Directive | What |\n|---|---|---|\n" + "".join(rows)))
        cold = self.write("engineering/standards/lessons-learned-archive.md", front("cto", "archived") + (
            "# Lessons learned, archive\n\n| Date | Directive | What |\n|---|---|---|\n" + row(50, "older")))
        return page, cold

    def test_rows_go_to_the_top_of_the_newest_first_table(self):
        page, cold = self.pages([row(1, "new"), row(10, "ten"), row(20, "twenty")])
        self.apply("cto")
        self.assertIn("|---|---|---|\n" + row(10, "ten") + row(20, "twenty") + row(50, "older"), cold.read_text())
        self.assertIn("|---|---|---|\n" + row(1, "new"), page.read_text())

    def test_the_pages_own_pointer_stands_and_the_digest_is_untouched(self):
        page, _ = self.pages([row(10)])
        self.apply("cto")
        self.assertNotIn("Rows before", page.read_text())
        self.assertIn("- A rule (2026-10-01).", page.read_text())

    def test_a_lesson_that_tells_of_a_pause_or_a_next_step_still_moves(self):
        for text in ("The PAUSE reached nobody", "NEXT: a step the scan never reads here"):
            with self.subTest(text):
                page, cold = self.pages([row(10, text)])
                self.apply("cto")
                self.assertNotIn(text, page.read_text())
                self.assertIn(text, cold.read_text())

    def test_age_days_is_for_a_page_still_near_its_limit(self):
        page, _ = self.pages([row(1, "new"), row(3, "three")])
        self.assertEqual(plan(self.root, TODAY)[0], [])
        self.apply("cto", "--age-days", "2")
        self.assertNotIn("three", page.read_text())
        self.assertIn("new", page.read_text())


class ClosedSections(SweepTestCase):
    """Only the owner's CLOSED line moves a section. A status row only names a candidate."""
    OPEN = "# Order /100\n\nA landing line.\n\n"
    HOLD = "line {} is a code fence, so no section here moves: move sections by hand or remove the fence"

    def closed(self, days=5, then="A line.\n", heading="# Order /84"):
        return f"{heading}\n\nCLOSED {ago(days)}: all landed.\n\n{then}"

    def moves(self):
        return plan(self.root, TODAY)[0]

    def left(self):
        return [why for _, _, why in plan(self.root, TODAY)[1]]

    def test_a_closed_section_moves_word_for_word_and_the_rest_stays(self):
        body = self.closed(then=f"RESUME POINT, {ago(12)}: a \"line\" | with\ttabs\n\n**CEO:** ruled.\n\n")
        page = self.questions("# Past, in short\n\nThe past.\n\n" + body + self.OPEN)
        self.assertEqual(self.apply("cto")[0], 0)
        self.assertIn(body.rstrip("\n"), page.with_name("ceo-questions-archive.md").read_text())
        self.assertNotIn("# Order /84", page.read_text())
        self.assertIn(self.OPEN, page.read_text())
        self.assertIn("# Past, in short\n\nThe past.\n", page.read_text())

    def test_any_product_works_the_same(self):
        page = self.questions(self.closed(), product="demo")
        self.apply("cto")
        self.assertNotIn("# Order /84", page.read_text())

    def test_a_pointer_is_left_once_and_is_no_heading(self):
        page = self.questions("Intro.\n\n" + self.closed() + "\n" + self.OPEN)
        self.apply("cto")
        self.assertEqual(page.read_text().count("[ceo-questions-archive.md](ceo-questions-archive.md)"), 1)
        self.assertIn("\nClosed orders' lines are in [", page.read_text())
        page.write_text(page.read_text() + self.closed(heading="# Order /85"))
        self.apply("cto")
        self.assertEqual(page.read_text().count("[ceo-questions-archive.md](ceo-questions-archive.md)"), 1)

    def test_no_closed_line_no_move_whatever_the_status_rows_say(self):
        self.directive([row(10, "**REPORT /84: DONE.** All landed")])
        for section in ("# Order /84\n\nA line.\n", "# Order /84\n\nDONE, and CLOSED.\n", "# Order /84\n\nclosed 2026-01-01\n"):
            with self.subTest(section):
                self.questions(section)
                self.assertEqual(self.moves(), [])

    def test_a_row_saying_done_names_a_candidate_with_what_to_do(self):
        self.directive([row(10, "**REPORT /84: DONE.** All landed")])
        self.questions("# Order /84\n\nA line.\n\n" + self.OPEN)
        [why] = self.left()
        self.assertIn(f"# Order /84: candidate: a row in {DIRECTIVE} says DONE", why)
        self.assertIn("add `CLOSED YYYY-MM-DD` under the heading", why)

    def test_a_candidate_comes_from_an_archive_too_and_names_every_directive(self):
        self.write("board/directives/D-20260102-y.md", status_page([row(10, "REPORT /84: DONE")]))
        self.write(f"board/directives/{DIRECTIVE}-archive-1.md", status_page([row(10, "REPORT /84: DONE")]))
        self.questions("# Order /84\n\nA line.\n")
        self.assertIn(f"{DIRECTIVE}-archive-1, D-20260102-y", self.left()[0])

    def test_no_row_or_another_number_or_no_order_is_quiet(self):
        self.directive([row(10, "REPORT /840: DONE"), row(10, "REPORT /84: PARTIAL"), row(10, "A row: /84 DONE")])
        self.questions("# Order /84\n\nA line.\n\n# Questions\n\nA line.\n")
        self.assertEqual(self.left(), [])

    def test_closed_must_be_the_first_line_under_the_heading(self):
        self.questions(f"# Order /84\n\nA line.\n\nCLOSED {ago(5)}\n")
        self.assertEqual(self.moves(), [])

    def test_a_section_of_only_its_heading_is_open(self):
        self.questions("# Order /84\n")
        self.assertEqual(self.moves(), [])

    def test_lines_the_watcher_or_a_running_agent_looks_for_stay(self):
        for word in ("NEEDS-CEO-NOW: an old question", "PAUSE until told"):
            with self.subTest(word):
                self.questions(self.closed(then=word + "\n"))
                self.assertEqual(self.moves(), [])
                self.assertIn("holds a", self.left()[0])

    def test_a_line_dated_after_the_closed_line_stays(self):
        self.questions(self.closed(then=f"**CEO, {ago(2)}T08:00Z:** reopened.\n"))
        self.assertEqual(self.moves(), [])
        self.assertIn(f"has a line dated {ago(2)}", self.left()[0])

    def test_the_closed_lines_own_text_can_hold_a_later_date(self):
        self.questions(f"# Order /84\n\nCLOSED {ago(5)}: a deadline of {ago(-30)} went with it.\n")
        self.assertEqual(len(self.moves()), 1)

    def test_within_the_age_stays_and_age_days_shortens_it(self):
        self.questions(self.closed(days=AGE_DAYS["closed"]))
        self.assertEqual(self.moves(), [])
        self.assertIn("within its age", self.left()[0])
        self.assertEqual(len(plan(self.root, TODAY, age_days=2)[0]), 1)

    def test_an_impossible_date_stays(self):
        self.questions("# Order /84\n\nCLOSED 2026-13-45\n")
        self.assertEqual(self.moves(), [])

    def test_any_code_fence_holds_the_whole_page(self):
        """A `# ` in a fence can't be told from a heading, so nothing moves: same bytes, no archive, named once."""
        stray = self.closed(then="```\n\n")
        quoted = "```\n# Order /9\nCLOSED 2026-01-01\n```\n\nOpen text.\n\n```sh\nmake deploy\n```\n\nThe last open line.\n"
        for name, text, line in (
                ("a: pairs with a later order's fence", stray + "# Order /101\n\nAn open line.\n\n```sh\nmake deploy\n```\n\nThe last open line.\n", 5),
                ("b: pairs with one round a shell comment", stray + "# Order /101\n\nAn open line.\n\n```\n# a comment\n```\n\nThe last open line.\n", 5),
                ("f: an order quoted in a real fence", stray + f"# Order /101\n\nStill open.\n\n{quoted}", 5),
                ("g: a clean closed order below", stray + "# Order /101\n\nAn open line.\n\n```\n\n" + self.closed(heading="# Order /102"), 5),
                ("same_section: the stray fence is in the open order", f"# Order /101\n\nStill open.\n\n```\n\n{quoted}", 5),
                ("a preamble's fence that never closes", "Intro.\n\n```\nnever closed\n\n" + self.closed(), 3),
                ("a preamble's fence that pairs with an order's", "Intro.\n\n```\n\n# Order /100\n\nAn open line.\n\n```\n\n" + self.closed(), 3),
                ("tilde", self.closed(then="~~~\n\n") + "# Order /101\n\nAn open line.\n", 5),
                ("three spaces in", self.closed(then="   ```\n\n") + "# Order /101\n\nAn open line.\n", 5),
                ("a clean fence in the closed order", self.closed(then="```sh\n# a comment\n```\n"), 5),
                ("a clean fence in an open order", self.closed() + "# Order /101\n\n```sh\nmake deploy\n```\n", 8),
                ("a closed line in a fence", f"# Order /84\n\n```\nCLOSED {ago(5)}\n```\n", 3)):
            with self.subTest(name):
                page = self.questions(text)
                self.assertEqual(self.moves(), [])
                self.assertEqual(self.left(), [self.HOLD.format(line)])
                self.assertEqual(self.run_main()[1].count(f"ceo-questions.md: {self.HOLD.format(line)}"), 1)
                self.assertEqual(self.apply("cto")[0], 0)
                self.assertEqual(page.read_text(), text)
                self.assertFalse(page.with_name("ceo-questions-archive.md").exists())

    def test_without_a_fence_the_closed_order_moves_and_the_open_one_stays(self):
        later = "# Order /101\n\nAn open line.\n\nThe last open line.\n"
        page = self.questions(self.closed() + later)
        self.assertEqual(self.left(), [])
        self.assertEqual(self.apply("cto")[0], 0)
        self.assertEqual(page.read_text().split("\n", 2)[2], later)
        archive = page.with_name("ceo-questions-archive.md").read_text()
        self.assertIn("# Order /84", archive)
        self.assertNotIn("# Order /101", archive)

    def test_a_line_that_opens_no_fence_holds_nothing(self):
        for line in ("```a``` is inline code", "    ```"):
            with self.subTest(line):
                page = self.questions(self.closed(then=f"{line}\n\n") + f"# Order /100\n\nAn open line.\n\n{line}\n")
                self.assertEqual(self.apply("cto")[0], 0)
                self.assertIn("# Order /100", page.read_text())
                self.assertNotIn("# Order /84", page.read_text())

    def test_a_held_page_names_its_fence_and_no_candidate(self):
        self.directive([row(10, "**REPORT /100: DONE.** All landed")])
        self.questions("# Order /100\n\n```\n# quoted\n```\n")
        self.assertEqual(self.left(), [self.HOLD.format(3)])

    def test_a_held_page_moves_once_its_fence_is_gone(self):
        text = self.closed(then="```\n\n") + "# Order /101\n\nAn open line.\n"
        page = self.questions(text)
        self.assertEqual(self.moves(), [])
        page.write_text(text.replace("```\n\n", ""))
        self.assertEqual(self.apply("cto")[0], 0)
        self.assertEqual(page.read_text(), "Closed orders' lines are in [ceo-questions-archive.md](ceo-questions-archive.md): search it, don't load it.\n\n# Order /101\n\nAn open line.\n")

    def test_a_cold_page_with_another_owner_stays_and_is_named(self):
        page = self.questions(self.closed())
        cold = page.with_name("ceo-questions-archive.md")
        cold.write_text(front("ceo", "archived") + "# Cold\n")
        self.assertEqual(self.moves(), [])
        self.assertIn("another owner", self.left()[0])

    def test_the_hot_page_keeps_its_final_newline(self):
        page = self.questions("# Order /100\n\nAn open line.\n" + self.closed())
        self.apply("cto")
        self.assertTrue(page.read_text().endswith("An open line.\n"))

    def test_would_move_and_moved_count_the_ceo_lines(self):
        self.questions(self.closed(then="**CEO:** a ruling.\n\n**CEO, later:** another.\n"))
        self.assertIn("1 closed sections, 2 **CEO lines", self.run_main()[1])
        self.assertIn("1 closed sections, 2 **CEO lines", self.apply("cto")[1])

    def test_bytes_that_arent_utf8_and_odd_line_ends_move_unchanged(self):
        odd = f"# Order /84\n\nCLOSED {ago(5)}\nbad \xff byte\r\nand a   separator \x0c form feed\n".encode("utf-8", "surrogateescape")
        odd = odd.replace("\xff".encode("utf-8"), b"\xff")
        page = self.questions(odd + self.OPEN.encode())
        self.apply("cto")
        self.assertIn(odd.rstrip(b"\n"), page.with_name("ceo-questions-archive.md").read_bytes())
        self.assertEqual(page.read_bytes().count(b"\xff"), 0)

    def test_the_cold_page_keeps_what_it_had(self):
        page = self.questions(self.closed())
        cold = page.with_name("ceo-questions-archive.md")
        cold.write_text("# Older\n\nKept.\n")
        self.apply("cto")
        self.assertTrue(cold.read_text().startswith("# Older\n\nKept.\n"))
        self.assertIn("# Order /84", cold.read_text())


class Owners(SweepTestCase):
    def pages(self):
        self.directive([row(20)])
        self.questions(f"# Order /84\n\nCLOSED {ago(5)}\n")

    def test_apply_needs_an_owner(self):
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()) as err:
            main(["--root", str(self.root), "--apply"])
        self.assertIn("--apply needs --owner", err.getvalue())

    def test_only_the_owners_pages_move_and_the_other_is_named(self):
        self.pages()
        before = self.snapshot()
        code, out = self.apply("cto")
        self.assertEqual(code, 0)
        after = self.snapshot()
        self.assertEqual({p.name for p in after if after[p] != before.get(p)},
                         {"ceo-questions.md", "ceo-questions-archive.md", SWEEP_STAMPS})
        self.assertIn(f"Not yours, ceo: knowledge/board/directives/{DIRECTIVE}.md", out)

    def test_a_page_with_another_owners_front_matter_doesnt_move(self):
        page = self.directive([row(20)], owner="board")
        self.write(f"board/directives/{DIRECTIVE}-archive-1.md", front("board", "archived") + "## Status log\n\n|h|\n|---|\n")
        before = page.read_bytes()
        self.apply("ceo")
        self.assertEqual(page.read_bytes(), before)

    def test_a_sweep_stamps_only_its_owner_and_quiets_only_that_lint_line(self):
        self.write(SWEEP_STAMPS, "# Only the tool writes a line.\n")
        self.apply("ceo")
        self.assertEqual((self.root / SWEEP_STAMPS).read_text(), f"# Only the tool writes a line.\nceo {TODAY}\n")
        due = [f.message for f in lint(self.root, TODAY) if f.message.startswith("sweep due")]
        self.assertEqual(len(due), 1)
        self.assertIn("cto: none recorded", due[0])
        self.apply("cto")
        self.apply("ceo")
        lines = (self.root / SWEEP_STAMPS).read_text().splitlines()
        self.assertEqual(sorted(lines), sorted(["# Only the tool writes a line.", f"ceo {TODAY}", f"cto {TODAY}"]))

    def test_a_sweep_with_nothing_to_move_still_counts(self):
        self.apply("cto")
        self.assertEqual((self.root / SWEEP_STAMPS).read_text(), f"cto {TODAY}\n")


class UtcToday(SweepTestCase):
    """Without --today, ages count from today's UTC date, as the logs write it."""

    def stamp_at(self, now, *args):
        argv = ["--root", str(self.root), "--transcripts", str(self.transcripts), "--apply", "--owner", "ceo", *args]
        with ahead_of_utc(), mock.patch("time.time", return_value=now), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(argv), 0)
        return (self.root / SWEEP_STAMPS).read_text()

    def test_the_evening_is_still_the_utc_day(self):
        self.assertEqual(self.stamp_at(EVENING), "ceo 2026-01-08\n")

    def test_after_midnight_utc_is_the_next_day(self):
        self.assertEqual(self.stamp_at(MIDNIGHT), "ceo 2026-01-09\n")

    def test_the_stamp_is_the_runs_own_date_never_the_today_flag(self):
        """--today sets ages only."""
        for flag in ("2026-01-13", "2026-01-01"):
            with self.subTest(flag):
                self.assertEqual(self.stamp_at(MIDNIGHT, "--today", flag), "ceo 2026-01-09\n")


class Safety(SweepTestCase):
    def pages(self):
        page = self.directive([row(20)])
        return page, page.with_name(f"{DIRECTIVE}-archive-1.md")

    def test_a_dry_run_changes_nothing_and_says_what_would_move(self):
        self.directive([row(20, "**REPORT /84: DONE.**")])
        self.questions("# Order /84\n\nA line.\n")
        before = self.snapshot()
        code, out = self.run_main()
        self.assertEqual(code, 0)
        self.assertEqual(self.snapshot(), before)
        self.assertIn(f"Would move, ceo: knowledge/board/directives/{DIRECTIVE}.md -> {DIRECTIVE}-archive-1.md: 1 rows", out)
        self.assertIn("Stays, cto: workspaces/acme/content/ceo-questions.md: # Order /84: candidate:", out)
        self.assertIn("Dry run: nothing changed.", out)

    def test_a_dry_run_counts_size_in_bytes_as_the_linter_does(self):
        self.directive([row(20, "é" * 2048)])
        _, out = self.run_main()
        self.assertRegex(out, r"\((?:4\.[3-9]) KB -> 0\.\d KB\)")

    def test_a_second_sweep_moves_nothing(self):
        page, cold = self.pages()
        self.apply()
        before = page.read_bytes(), cold.read_bytes()
        self.apply()
        self.assertEqual((page.read_bytes(), cold.read_bytes()), before)

    def test_a_rerun_after_a_stop_adds_nothing_twice(self):
        page, cold = self.pages()
        [move] = plan(self.root, TODAY)[0]
        kb_sweep.write(move.cold, move.cold_text, move.cold_before)  # stopped here: the cold page written, the hot page not
        self.apply()
        self.assertEqual(cold.read_text().count(row(20)), 1)
        self.assertNotIn(row(20), page.read_text())

    def test_a_section_rerun_adds_nothing_twice(self):
        page = self.questions(f"# Order /84\n\nCLOSED {ago(5)}\n")
        [move] = plan(self.root, TODAY)[0]
        kb_sweep.write(move.cold, move.cold_text, move.cold_before)
        self.apply("cto")
        self.assertEqual(page.with_name("ceo-questions-archive.md").read_text().count("# Order /84"), 1)

    def test_two_equal_rows_stay_two_after_a_stop(self):
        page, cold = self.pages()
        page.write_text(page.read_text().replace(row(20), row(20) * 2))
        cold.write_text(cold.read_text().replace(row(100, "the oldest"), row(100, "the oldest") + row(20)))  # a stopped run left one
        self.apply()
        self.assertEqual(cold.read_text().count(row(20)), 2)
        self.assertNotIn(row(20), page.read_text())

    def test_a_hot_page_that_changed_is_left_and_nothing_is_lost(self):
        page, cold = self.pages()
        [move] = plan(self.root, TODAY)[0]
        page.write_text(page.read_text() + "A new line from a running agent.\n")
        self.assertFalse(apply_move(move))
        self.assertIn("A new line from a running agent.", page.read_text())
        self.assertIn(row(20), page.read_text())
        self.assertIn(row(20), cold.read_text())

    def test_a_cold_page_that_changed_since_the_plan_is_kept_whole(self):
        page, cold = self.pages()
        [move] = plan(self.root, TODAY)[0]
        cold.write_text(cold.read_text() + "A line added meanwhile.\n")
        self.assertFalse(apply_move(move))
        self.assertIn("A line added meanwhile.", cold.read_text())
        self.assertIn(row(20), page.read_text())

    def test_a_cold_page_that_appeared_since_the_plan_is_kept_whole(self):
        page = self.questions(f"# Order /84\n\nCLOSED {ago(5)}\n")
        [move] = plan(self.root, TODAY)[0]
        move.cold.write_text("# Someone else's archive\n")
        self.assertFalse(apply_move(move))
        self.assertEqual(move.cold.read_text(), "# Someone else's archive\n")
        self.assertIn("# Order /84", page.read_text())

    def test_a_cold_page_missing_the_text_stops_before_the_hot_page_changes(self):
        page, _ = self.pages()
        before = page.read_bytes()
        [move] = plan(self.root, TODAY)[0]
        move.chunks.append("text that never reached the cold page")
        with self.assertRaises(RuntimeError):
            apply_move(move)
        self.assertEqual(page.read_bytes(), before)

    def test_a_changed_page_stops_the_stamp_and_exits_1(self):
        page, _ = self.pages()

        def changes_first(move):
            page.write_text(page.read_text() + "A new line.\n")
            return apply_move(move)

        with mock.patch.object(kb_sweep, "apply_move", changes_first):
            code, out = self.apply()
        self.assertEqual(code, 1)
        self.assertIn("changed while running", out)
        self.assertFalse((self.root / SWEEP_STAMPS).exists())

    def test_a_changed_stamp_file_exits_1_and_keeps_the_other_line(self):
        stamps, real_write = self.root / SWEEP_STAMPS, kb_sweep.write
        stamps.write_text("cto 2026-11-01\n")

        def changes_first(path, text, before):
            stamps.write_text("cto 2026-11-02\n")
            return real_write(path, text, before)

        with mock.patch.object(kb_sweep, "write", changes_first):
            code, out = self.apply()
        self.assertEqual(code, 1)
        self.assertIn("changed while running", out)
        self.assertNotIn("Recorded the sweep", out)
        self.assertEqual(stamps.read_text(), "cto 2026-11-02\n")

    def test_text_reaches_the_disk_before_the_replace(self):
        path, calls, real_replace = self.root / "a.md", [], os.replace
        with mock.patch.object(kb_sweep, "sync", lambda f: calls.append(("sync", Path(f.name).read_bytes()))), \
                mock.patch.object(kb_sweep.os, "replace", lambda *names: (calls.append(("replace", b"")), real_replace(*names))):
            self.assertTrue(kb_sweep.write(path, "text", None))
        self.assertEqual(calls, [("sync", b"text"), ("replace", b"")])  # flushed before the sync
        self.assertEqual(path.read_text(), "text")

    def test_sync_uses_the_full_sync_where_there_is_one_and_fsync_where_it_fails(self):
        with open(self.root / "a.md", "wb") as f, mock.patch.object(kb_sweep.os, "fsync") as fsync:
            with mock.patch.object(kb_sweep.fcntl, "fcntl", side_effect=OSError("not on this disk")):
                kb_sweep.sync(f)
            fsync.assert_called_once()

    def test_the_compare_comes_after_the_temporary_file(self):
        path = self.write("a.md", "old\n")

        def a_line_arrives(_):
            path.write_text("old\nnew\n")

        with mock.patch.object(kb_sweep, "sync", a_line_arrives):
            self.assertFalse(kb_sweep.write(path, "replacement\n", "old\n"))
        self.assertEqual(path.read_text(), "old\nnew\n")
        self.assertEqual(list(self.base.rglob(".kb_sweep-*")), [])

    def test_age_days_must_be_positive(self):
        for age in ("0", "-1"):
            with self.subTest(age), self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
                self.run_main("--age-days", age)

    def test_a_failed_cold_write_leaves_the_hot_page_and_no_temporary_file(self):
        page, _ = self.pages()
        before = page.read_bytes()
        with mock.patch.object(kb_sweep.os, "replace", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                self.apply()
        self.assertEqual(page.read_bytes(), before)
        self.assertEqual(list(self.base.rglob(".kb_sweep-*")), [])

    def test_a_bad_byte_in_a_heading_prints_and_doesnt_stop_the_sweep(self):
        self.directive([row(10, "REPORT /84: DONE")])
        page = self.questions(b"# Order /84: bad \xff byte\n\nA line.\n\n# Order /85: bad \xff byte\n\nCLOSED " + ago(5).encode() + b"\n")
        base = [sys.executable, str(SCRIPTS / "kb_sweep.py"), "--root", str(self.root), "--today", TODAY.isoformat()]
        dry = subprocess.run([*base, "--transcripts", str(self.transcripts)], capture_output=True, timeout=30)
        self.assertEqual(dry.returncode, 0, dry.stderr)
        self.assertIn(b"\\udcff", dry.stdout)
        moved = subprocess.run([*base, "--apply", "--owner", "cto"], capture_output=True, timeout=30)
        self.assertEqual(moved.returncode, 0, moved.stderr)
        self.assertNotIn(b"# Order /85", page.read_bytes())


class PageUse(SweepTestCase):
    SECRET = "-".join(("marker", "that", "must", "not", "print"))  # built at run time, as a canary is

    def line(self, name, tool_input, days=1):
        return json.dumps({"type": "assistant", "timestamp": f"{ago(days)}T10:00:00.000Z", "message": {"content": [
            {"type": "text", "text": self.SECRET},
            {"type": "tool_use", "name": name, "input": tool_input}]}}) + "\n"

    def transcript(self, *lines, name="session.jsonl"):
        path = self.transcripts / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(lines))
        age_file(path)

    def read_of(self, rel, days=1):
        return self.line("Read", {"file_path": f"/home/x/agentic-company/{rel}"}, days)

    def opens(self):
        return kb_sweep.page_opens([self.transcripts], TODAY - timedelta(days=14))[0]

    def test_read_calls_and_shell_reads_count(self):
        self.transcript(self.read_of("knowledge/a.md"),
                        self.line("Read", {"file_path": "/x/.claude/worktrees/agent-1/knowledge/a.md", "offset": 5}),
                        self.line("Bash", {"command": "sed -n '1,5p' knowledge/a.md"}),
                        self.line("Bash", {"command": "cd /x && cat knowledge/a.md | head -3"}),
                        self.line("Bash", {"command": "tail -5 workspaces/p/content/ceo-questions.md"}))
        self.assertEqual(self.opens(), {"knowledge/a.md": 4, "workspaces/p/content/ceo-questions.md": 1})

    def test_searches_writes_and_other_tools_dont_count(self):
        self.transcript(self.line("Bash", {"command": "grep -n x knowledge/a.md"}),
                        self.line("Bash", {"command": "grep -c x knowledge/a.md | sed s/1/2/"}),
                        self.line("Edit", {"file_path": "/x/knowledge/a.md"}),
                        self.line("Write", {"file_path": "/x/knowledge/a.md"}),
                        self.line("Grep", {"path": "/x/knowledge/a.md"}),
                        self.read_of("scripts/kb_lint.py"))
        self.assertEqual(self.opens(), {})

    def test_shell_writes_and_paths_out_of_the_kb_dont_count(self):
        self.transcript(self.line("Bash", {"command": "cat > knowledge/a.md"}),
                        self.line("Bash", {"command": "sed -i s/a/b/ knowledge/a.md"}),
                        self.line("Bash", {"command": "cat knowledge/../secrets.md"}),
                        self.line("Read", {"file_path": "/x/knowledge/../../etc/x.md"}))
        self.assertEqual(self.opens(), {})

    def test_the_window_is_14_days_and_old_files_are_skipped(self):
        self.transcript(self.read_of("knowledge/new.md", days=14), self.read_of("knowledge/old.md", days=15))
        self.assertEqual(self.opens(), {"knowledge/new.md": 1})
        old = self.transcripts / "old.jsonl"
        old.write_text(self.read_of("knowledge/older.md", days=1))
        age_file(old, days=30)
        self.assertNotIn("knowledge/older.md", self.opens())

    def test_subagents_transcripts_count(self):
        self.transcript(self.read_of("knowledge/a.md"), name="abc/subagents/agent-1.jsonl")
        self.assertEqual(self.opens(), {"knowledge/a.md": 1})

    def test_bad_lines_are_skipped(self):
        self.transcript('{"tool_use" broken\n', '["tool_use"]\n', json.dumps({"tool_use": 1, "message": "x"}) + "\n",
                        json.dumps({"type": "tool_use", "message": {"content": "tool_use"}}) + "\n",
                        self.line("Read", ["not", "a", "dict"]), self.line("Read", None), self.read_of("knowledge/a.md"))
        self.assertEqual(self.opens(), {"knowledge/a.md": 1})

    def test_the_default_folder_is_this_repos_sessions_from_a_worktree_too(self):
        home = self.base / "home"
        projects = home / ".claude" / "projects"
        wanted = {"-repo-my-company-1", "-repo-my-company-1--claude-worktrees-agent-1"}
        for name in (*wanted, "-repo-other"):
            (projects / name).mkdir(parents=True)
        base = Path("/repo/my_company 1/.claude/worktrees/agent-1")
        with mock.patch.object(Path, "home", return_value=home), mock.patch.dict(os.environ):
            os.environ.pop("CLAUDE_CONFIG_DIR", None)
            folders = kb_sweep.transcript_folders(base)
        self.assertEqual({folder.name for folder in folders}, wanted)
        with mock.patch.dict(os.environ, CLAUDE_CONFIG_DIR=str(home / ".claude")):
            self.assertEqual(kb_sweep.transcript_folders(base), folders)

    def test_the_report_shows_paths_and_counts_and_no_transcript_text(self):
        self.write("a.md", front() + "# A\n")
        self.transcript(self.read_of("knowledge/a.md"), self.line("Bash", {"command": f"cat knowledge/a.md # {self.SECRET}"}))
        _, out = self.run_main()
        self.assertIn("2 opens of 1 pages, from 1 transcripts", out)
        self.assertIn("2  knowledge/a.md", out)
        self.assertNotIn(self.SECRET, out)

    def test_a_page_that_no_longer_exists_isnt_reported(self):
        self.transcript(self.read_of("knowledge/gone.md"))
        _, out = self.run_main()
        self.assertNotIn("knowledge/gone.md", out)

    def test_a_cold_page_read_often_is_a_candidate_for_hot(self):
        self.write("a.md", front() + "[cold](a-archive.md)\n")
        self.write("a-archive.md", front("cto", "archived") + "# Cold\n")
        self.write("b-archive.md", front("cto", "archived") + "# Cold\n")
        self.transcript(*[self.read_of("knowledge/a-archive.md")] * HOT_OPENS, *[self.read_of("knowledge/b-archive.md")] * (HOT_OPENS - 1))
        _, out = self.run_main()
        self.assertIn(f"candidate for hot: knowledge/a-archive.md: {HOT_OPENS} opens (owner: cto)", out)
        self.assertNotIn("candidate for hot: knowledge/b-archive.md", out)

    def test_a_work_logs_archive_read_often_is_a_candidate_for_hot(self):
        page = self.questions("# Order /1\n")
        page.with_name("ceo-questions-archive.md").write_text("# Closed\n")
        self.transcript(*[self.read_of("workspaces/acme/content/ceo-questions-archive.md")] * HOT_OPENS)
        _, out = self.run_main()
        self.assertIn(f"candidate for hot: workspaces/acme/content/ceo-questions-archive.md: {HOT_OPENS} opens (owner: cto)", out)

    def test_a_hot_page_nobody_reads_is_a_candidate_for_cold(self):
        self.write("a.md", front() + "[cold](a-archive.md)\n")
        self.write("c.md", front() + "[cold](a-archive.md)\n")
        self.write("a-archive.md", front("cto", "archived") + "# Cold\n")
        self.write("b.md", front() + "# A plain page, not split: it isn't hot, read or not\n")
        self.questions("# Order /1\n")
        self.transcript(self.read_of("knowledge/c.md"))
        _, out = self.run_main()
        self.assertIn("candidate for cold: knowledge/a.md: no opens (owner: ceo)", out)
        self.assertIn("candidate for cold: workspaces/acme/content/ceo-questions.md: no opens (owner: cto)", out)
        for page in ("c.md", "b.md", "a-archive.md"):
            self.assertNotIn(f"candidate for cold: knowledge/{page}", out)

    def test_a_summary_makes_a_page_hot(self):
        self.write("a.md", front() + "## Past, in short\n\nText.\n")
        self.transcript(self.read_of("knowledge/INDEX.md"))
        _, out = self.run_main()
        self.assertIn("candidate for cold: knowledge/a.md", out)

    def test_a_link_to_a_file_outside_the_repo_isnt_followed(self):
        outside = self.base.parent / f"{self.base.name}-archive.md"
        self.addCleanup(outside.unlink, missing_ok=True)
        outside.write_text(front("cto", "archived") + "# Out\n")
        self.write("a.md", front() + f"[out](../../{outside.name})\n")
        self.assertEqual(kb_sweep.hot_pages(self.root), [])

    def test_a_research_note_named_history_is_neither_hot_nor_cold(self):
        note = self.write("research/2026-01-14-acme-history.md", front("analyst") + "# Note\n")
        self.assertFalse(kb_sweep.is_cold(note))

    def test_no_transcripts_means_no_candidates_not_no_use(self):
        self.write("a.md", front() + "[cold](a-archive.md)\n")
        self.write("a-archive.md", front("cto", "archived") + "# Cold\n")
        _, out = self.run_main()
        self.assertIn("no transcripts found", out)
        self.assertNotIn("candidate for", out)


class WhoCanRunIt(unittest.TestCase):
    """--apply writes KB pages from Bash, so guard_kb_write.py can't see it: the agents that hook limits must be stopped
    by their Bash hooks. kb_lint.py is each test's control: the hook judges the script, not everything."""
    COMMANDS = ("python3 scripts/kb_sweep.py --apply --owner ceo", "python3 scripts/kb_sweep.py")

    def test_marketing_agents_cant_run_it_and_keep_the_lint(self):
        sys.path.insert(0, str(SCRIPTS / "hooks"))
        from marketing_bash import bash_reason
        root = str(SCRIPTS.parent)
        for agent in ("cmo", "content-producer", "content-reviewer", "performance-analyst"):
            with self.subTest(agent):
                self.assertIsNone(bash_reason("python3 scripts/kb_lint.py", agent, root, root))
                for command in self.COMMANDS:
                    self.assertIn("python3 runs only the marketing scripts", bash_reason(command, agent, root, root))

    def test_the_read_only_agents_cant_run_it(self):
        for agent in ("critic", "content-reviewer"):
            for command in self.COMMANDS:
                with self.subTest(agent=agent, command=command):
                    payload = {"session_id": "test", "cwd": str(SCRIPTS.parent), "hook_event_name": "PreToolUse",
                               "tool_name": "Bash", "tool_input": {"command": command}, "agent_type": agent}
                    result = subprocess.run([sys.executable, str(SCRIPTS / "hooks" / "guard_critic_bash.py")],
                                            input=json.dumps(payload), capture_output=True, text=True, timeout=30)
                    self.assertEqual(result.returncode, 2)
                    self.assertIn("only reads", result.stderr)


class Desk(SweepTestCase):
    """The Board desk's pages. TODAY is Friday 2026-11-20."""

    OCT31 = "## 2026-10-31, Saturday\n### 00:00-06:00\n- 01:00-02:00 Done: a.\n### 06:00-24:00: Nothing happened.\n"
    NOV19 = "## 2026-11-19, Thursday\n### 18:00-24:00\n- 20:00-21:00\n  - Decided: b.\n  - Done: c.\n"
    A1 = "### A-1 · withdrawn 2026-11-10 · b1 · D-x · asked 2026-11-09 09:00\n\n- **Question:** one?\n- **Outcome:** gone"

    def pages(self, summarised=("2026-11-19", "2026-11-15", "2026-11-14", "2026-10-31")):
        desk = "company/board-desk/"
        self.progress = (front(title="Progress, hour by hour") + "# Progress\n\nAbout.\n\n## Spend\n\nSpend as of x\n- y\n\n"
                         "## 2026-11-20, Friday\n### 06:00-12:00\n- 08:00-09:00 Done: d.\n\n" + self.NOV19 + "\n" + self.OCT31)
        self.write(desk + "progress.md", self.progress)
        days = "".join(f"## {day}, {date.fromisoformat(day):%A}\nWritten then.\n\nThe day {day}.\n\n### Spend (read 10:00)\n\n"
                       f"Spend as of x\n\n" for day in summarised)
        self.write(desk + "summaries.md", front(title="Daily executive summaries") + "# Summaries\n\nAbout.\n\n" + days)
        self.write(desk + "asks.md", front(title="Asks for the Board") + "# Asks\n\nAbout.\n\n## Open\n\n"
                   "### A-3 · open · b9 · D-x · asked 2026-11-01 10:00\n\n- **Question:** three?\n\n## Closed\n\n"
                   "### A-2 · answered 2026-11-18 (in chat) · two-way · D-x · asked 2026-11-17 09:00\n\n- **Question:** two?\n\n"
                   + self.A1 + "\n")

    def desk(self, name):
        return (self.root / "company" / "board-desk" / name).read_text()

    def test_a_dry_run_names_each_page_one_month_at_a_time(self):
        self.pages()
        code, out = self.run_main()
        self.assertEqual(code, 0)
        self.assertIn("Would move, ceo: knowledge/company/board-desk/progress.md -> progress-archive-2026-10.md: 1 days, "
                      "2026-10-31 to 2026-10-31", out)
        self.assertIn("summaries.md -> summaries-archive-2026-10.md: 1 summaries, 2026-10-31", out)
        self.assertIn("asks.md -> asks-archive-2026-11.md: 1 closed asks, 2026-11-10", out)

    def test_a_closed_ask_with_a_part_in_its_id_moves_too(self):
        self.A1 = self.A1.replace("### A-1 ·", "### B-7 B+C ·")
        self.pages()
        self.assertEqual(self.apply()[0], 0)
        self.assertNotIn("B-7 B+C", self.desk("asks.md"))
        self.assertIn(self.A1, self.desk("asks-archive-2026-11.md"))
        self.assertIsNone(kb_sweep.DESK_ASK.match("### B-7 a|b · answered 2026-11-10 · b1"))  # board_desk.py's ASK_ID_TEXT

    def test_apply_moves_text_word_for_word_and_the_pages_still_read(self):
        sys.path.insert(0, str(SCRIPTS))
        import board_desk
        self.pages()
        for _ in range(2):
            self.assertEqual(self.apply()[0], 0)
        progress, archive = self.desk("progress.md"), self.desk("progress-archive-2026-10.md")
        self.assertIn(self.OCT31.rstrip("\n"), archive)
        self.assertIn(self.NOV19.rstrip("\n"), self.desk("progress-archive-2026-11.md"))
        self.assertNotIn("2026-10-31", progress.split("## Spend")[1])
        self.assertIn("## 2026-11-20, Friday", progress)  # the latest day stays
        self.assertIn("[progress-archive-2026-10.md](progress-archive-2026-10.md)", progress)
        self.assertIn("[progress-archive-2026-11.md](progress-archive-2026-11.md)", progress)
        board_desk.parse_progress(progress, strict=True)  # the hourly job still takes the page
        summaries = self.desk("summaries.md")
        self.assertIn("## 2026-11-15, Sunday", summaries)
        self.assertNotIn("## 2026-11-14, Saturday", summaries)
        self.assertIn("## 2026-11-14, Saturday", self.desk("summaries-archive-2026-11.md"))
        asks = self.desk("asks.md")
        self.assertNotIn("A-1 ·", asks)
        self.assertIn("### A-2 · answered", asks)
        self.assertIn("### A-3 · open", asks)
        self.assertIn(self.A1, self.desk("asks-archive-2026-11.md"))
        self.assertIn("status: archived", archive)
        found = [f for f in lint(self.root, TODAY) if "board-desk" in str(f.path) and "archive" in str(f.path)
                 and (f.level == "error" or "orphan" in f.message)]
        self.assertEqual(found, [])
        code, out = self.run_main()
        self.assertIn("Nothing to move", out)

    def test_an_archive_keeps_the_newest_first(self):
        self.pages()
        self.apply()
        self.apply()
        self.write("company/board-desk/progress.md", self.desk("progress.md").replace(
            "## 2026-11-20, Friday", "## 2026-11-21, Saturday\n- 01:00-02:00 Done: e.\n\n## 2026-11-20, Friday"))
        self.write("company/board-desk/summaries.md", self.desk("summaries.md").replace(
            "## 2026-11-19", "## 2026-11-20, Friday\nWritten.\n\n## 2026-11-19"))
        self.apply()
        archive = self.desk("progress-archive-2026-11.md")
        self.assertLess(archive.index("## 2026-11-20, Friday"), archive.index("## 2026-11-19, Thursday"))
        self.assertEqual(archive.count("## 2026-11-19, Thursday"), 1)

    def test_a_rerun_after_a_stop_adds_nothing_twice(self):
        self.pages()
        moves = kb_sweep.plan_desk(self.root, TODAY)
        for move in moves:  # stopped after the archive, before the hot page
            kb_sweep.write(move.cold, move.cold_text, move.cold_before)
        self.apply()
        self.assertEqual(self.desk("progress-archive-2026-10.md").count("## 2026-10-31, Saturday"), 1)
        self.assertEqual(self.desk("asks-archive-2026-11.md").count("### A-1 ·"), 1)
        self.assertNotIn("## 2026-10-31", self.desk("progress.md").split("## Spend")[1])

    def test_an_unsummarised_day_and_the_latest_day_stay(self):
        self.pages(summarised=())
        self.assertEqual([m.page.name for m in kb_sweep.plan_desk(self.root, TODAY)], ["asks.md"])
        self.pages(summarised=("2026-11-20",))
        self.write("company/board-desk/progress.md", self.progress.replace(self.NOV19 + "\n" + self.OCT31, ""))
        self.assertEqual([m.page.name for m in kb_sweep.plan_desk(self.root, TODAY)], ["asks.md"])

    def test_a_day_of_questions_moves_after_three_days_word_for_word(self):
        """Like asks.md's, a day of qa.md (its `## YYYY-MM-DD`) asked longer ago
        than AGE_DAYS["closed"] moves, whatever its entries' status; a later day stays."""
        q1 = ("## 2026-11-16\n\n### Q-1 · changed 2026-11-19, see Q-2 · the desk · asked 14:3x\n\n"
              "- **Your words:** \"Done?\"\n- **Answer:** Yes.")
        q2 = ("## 2026-11-19\n\n### Q-2 · current · the desk · asked 09:00\n\n- **Your words:** \"Still?\"\n"
              "- **Still true from Q-1:** Yes.\n- **Updated:** And more.")
        self.write("company/board-desk/qa.md", front(title="Q&A") + "# Q&A\n\nAbout.\n\n" + q2 + "\n\n" + q1 + "\n")
        [move] = kb_sweep.plan_desk(self.root, TODAY)
        self.assertEqual(move.what, "1 question, 2026-11-16 to 2026-11-16")
        self.apply()
        qa, archive = self.desk("qa.md"), self.desk("qa-archive-2026-11.md")
        self.assertIn(q1, archive)
        self.assertNotIn("Q-1 ·", qa)
        self.assertIn(q2, qa)
        self.assertIn("Days of questions of 2026-11, moved word for word: [qa-archive-2026-11.md](qa-archive-2026-11.md)", qa)
        self.assertIn("status: archived", archive)

    @staticmethod
    def question(n, size=2500, day="11-20"):
        return f"### Q-{n} · current · topic {n} · asked about 10:0x on {day}\n\n- **Your words:** \"Q{n}?\"\n- **Answer:** " + "a" * size

    def qa(self, days, archive=None):
        """qa.md with these days ({date: [question]}, in page order) and, if given, its 2026-11 archive's body."""
        desk = "company/board-desk/"
        body = "".join(f"## {day}\n\n" + "\n\n".join(questions) + "\n\n" for day, questions in days.items())
        self.write(desk + "qa.md", front(title="Q&A", related="[qa-archive-2026-11.md]") + "# Q&A\n\nAbout.\n\n" + body)
        if archive is not None:
            self.write(desk + "qa-archive-2026-11.md", front(status="archived", title="Q&A: archive, 2026-11")
                       + "# Q&A: archive, 2026-11\n\nMoved word for word from [qa.md](qa.md), oldest first.\n\n" + archive)

    def test_a_q_and_a_page_over_its_limit_moves_its_oldest_questions_at_any_age_until_it_fits(self):
        """Today's questions, younger than AGE_DAYS["closed"], go oldest first,
        whole and word for word, to the end of their day in the archive, under the heading a move by hand left
        there; the newest stay. The desk's push (board_desk.qa_entries, which reads the page and its archives) still
        finds every question, the same."""
        sys.path.insert(0, str(SCRIPTS))
        import board_desk
        today = [self.question(n) for n in range(3, 15)]  # 12 questions of about 2.6 KB: about 31 KB
        self.qa({"2026-11-20": today}, archive="## 2026-11-19\n\n" + self.question(1, 100, "11-19") + "\n\n## 2026-11-20\n\n"
                + self.question(2, 100) + "\n")
        pushed = board_desk.qa_entries(self.base)
        [move] = kb_sweep.plan_desk(self.root, TODAY)
        self.assertRegex(move.what, r"^(\d+) questions?, 2026-11-20 to 2026-11-20; \1 of them younger: over its 25 KB limit, "
                                    r"it goes under 22.5 KB$")
        self.assertEqual(self.apply()[0], 0)
        qa, archive = self.desk("qa.md"), self.desk("qa-archive-2026-11.md")
        self.assertLess(len(qa.encode()), 0.9 * 25 * KB)  # out of kb_lint's sweep band, so the next entry fits too
        moved = [q for q in today if q not in qa]
        self.assertGreater(len(moved), 0)
        self.assertEqual(moved, today[:len(moved)])  # the oldest, whole
        self.assertGreaterEqual(len(qa.encode()) + len(today[len(moved) - 1].encode()), 0.9 * 25 * KB)  # no more than that
        self.assertIn("## 2026-11-20\n\n" + today[len(moved)], qa)  # the day keeps its heading for the rest
        self.assertEqual(archive.count("## 2026-11-20"), 1)
        self.assertIn("\n\n".join([self.question(2, 100), *moved]), archive)  # after the day's questions already there
        self.assertLess(archive.index("## 2026-11-19"), archive.index("## 2026-11-20"))
        after = board_desk.qa_entries(self.base)
        self.assertEqual(list(after), [f"Q-{n}" for n in range(1, 15)])
        for qid, entry in pushed.items():
            self.assertEqual((after[qid]["fields"], after[qid]["lines"]), (entry["fields"], entry["lines"]), qid)
            self.assertEqual(after[qid]["page"].endswith("qa-archive-2026-11.md"), qid in ("Q-1", "Q-2") or any(
                q.startswith(f"### {qid} ·") for q in moved), qid)
        self.assertEqual([f for f in lint(self.root, TODAY) if f.path.endswith("board-desk/qa.md") and f.level == "error"], [])
        self.assertIn("Nothing to move", self.run_main()[1])

    def test_a_page_within_its_limit_moves_nothing_young(self):
        self.qa({"2026-11-20": [self.question(n) for n in range(1, 5)]})
        self.assertEqual(kb_sweep.plan_desk(self.root, TODAY), [])

    def test_a_day_the_archive_hasn_t_got_goes_in_date_order_under_its_own_heading(self):
        """The CEO's archive is oldest first: a part of a day, or a whole day by age, goes before the first later day."""
        self.qa({"2026-11-16": [self.question(1, 100, "11-16")], "2026-11-18": [self.question(n, 4000, "11-18") for n in range(3, 11)]},
                archive="## 2026-11-15\n\n" + self.question(0, 100, "11-15") + "\n\n## 2026-11-19\n\n" + self.question(20, 100, "11-19") + "\n")
        [move] = kb_sweep.plan_desk(self.root, TODAY)
        self.assertEqual(move.what, "4 questions, 2026-11-16 to 2026-11-18; 3 of them younger: over its 25 KB limit, "
                                    "it goes under 22.5 KB")
        self.assertEqual(self.apply()[0], 0)
        archive, qa = self.desk("qa-archive-2026-11.md"), self.desk("qa.md")
        days = [line for line in archive.split("\n") if line.startswith("## ")]
        self.assertEqual(days, ["## 2026-11-15", "## 2026-11-16", "## 2026-11-18", "## 2026-11-19"])
        filed = "\n\n".join(["## 2026-11-16", self.question(1, 100, "11-16"), "## 2026-11-18",
                              *[self.question(n, 4000, "11-18") for n in (3, 4, 5)], "## 2026-11-19"])
        self.assertTrue(filed in archive, "the 11-16 day, then 11-18's three oldest, before 11-19")
        self.assertNotIn("## 2026-11-16", qa)
        self.assertTrue(("## 2026-11-18\n\n" + self.question(6, 4000, "11-18")) in qa, "the rest of 11-18 stays")

    def test_a_heading_in_a_code_fence_stays_in_its_question(self):
        """board_desk.qa_entries reads a fenced `# comment` or `## 2026-…` line as the entry's text, and so does the sweep."""
        fenced = self.question(1, 100) + "\n\n```\n# a shell comment\n## 2026-01-01\n### Q-99 · not a heading\n```\n\nAfter the fence."
        self.qa({"2026-11-20": [fenced, *[self.question(n) for n in range(2, 14)]]})
        self.assertEqual(self.apply()[0], 0)
        archive, qa = self.desk("qa-archive-2026-11.md"), self.desk("qa.md")
        self.assertIn("## 2026-11-20\n\n" + fenced, archive)
        self.assertNotIn("a shell comment", qa)
        self.assertIn("oldest first", archive)

    def test_a_fence_in_the_intro_is_text_and_an_empty_day_counts_as_a_day(self):
        """board_desk.qa_entries opens a fence only inside an entry, so a
        stray one in the page's intro holds nothing; a day with no entry moves whole and is counted as a day."""
        desk = "company/board-desk/"
        self.write(desk + "qa.md", front(title="Q&A") + "# Q&A\n\nAbout.\n\n```\nan intro fence, never closed\n\n"
                   "## 2026-11-19\n\n" + self.question(2, 100, "11-19") + "\n\n## 2026-11-16\n\n" + self.question(1, 100, "11-16")
                   + "\n\n## 2026-11-15\n\nNothing asked.\n")
        [move] = kb_sweep.plan_desk(self.root, TODAY)
        self.assertEqual(move.what, "1 question and 1 empty day, 2026-11-15 to 2026-11-16")
        self.assertEqual(self.apply()[0], 0)
        qa, archive = self.desk("qa.md"), self.desk("qa-archive-2026-11.md")
        self.assertIn("## 2026-11-15\n\nNothing asked.", archive)
        self.assertIn("## 2026-11-16\n\n" + self.question(1, 100, "11-16"), archive)
        self.assertIn("an intro fence, never closed", qa)
        self.assertIn("## 2026-11-19\n\n" + self.question(2, 100, "11-19"), qa)

    def test_a_rerun_after_a_stop_files_each_question_once(self):
        self.qa({"2026-11-20": [self.question(n) for n in range(3, 15)]}, archive="## 2026-11-20\n\n" + self.question(2, 100) + "\n")
        [move] = kb_sweep.plan_desk(self.root, TODAY)
        kb_sweep.write(move.cold, move.cold_text, move.cold_before)  # stopped after the archive, before the hot page
        self.write("company/board-desk/qa.md", self.desk("qa.md") + "\n" + self.question(15) + "\n")  # and a new one came
        self.assertEqual(self.apply()[0], 0)
        archive = self.desk("qa-archive-2026-11.md")
        for n in range(2, 16):
            self.assertLessEqual(archive.count(f"### Q-{n} ·"), 1, n)
        self.assertEqual(archive.count("## 2026-11-20"), 1)
        qa = self.desk("qa.md")
        self.assertEqual([n for n in range(2, 16) if f"### Q-{n} ·" in qa and f"### Q-{n} ·" in archive], [])
        self.assertLessEqual(len(qa.encode()), 25 * KB)

    def test_one_month_a_run_and_the_next_run_moves_the_next(self):
        self.qa({"2026-11-30": [self.question(1, 3000, "11-30")], "2026-12-01": [self.question(n, 3000, "12-01") for n in range(2, 12)]})
        left = []
        first = date(2026, 12, 1)
        [move] = kb_sweep.plan_desk(self.root, first, left=left)
        self.assertEqual((move.cold.name, move.what), ("qa-archive-2026-11.md", "1 question, 2026-11-30 to 2026-11-30; 1 of "
                                                                                 "them younger: over its 25 KB limit, it goes under 22.5 KB"))
        self.assertIn("the next run moves the next month's", left[0][2])
        self.assertTrue(apply_move(move))
        [move] = kb_sweep.plan_desk(self.root, first)
        self.assertEqual(move.cold.name, "qa-archive-2026-12.md")
        self.assertTrue(apply_move(move))
        self.assertLessEqual(len(self.desk("qa.md").encode()), 25 * KB)
        self.assertIn("oldest first", self.desk("qa-archive-2026-12.md"))

    def test_asks_over_their_limit_move_closed_asks_at_any_age_never_an_open_one(self):
        """A closed ask goes, oldest closed first, even closed today; an open ask stays, and if the page is
        still over, the dry run says so."""
        def ask(n, status, size):
            return f"### A-{n} · {status} · two-way · D-x · asked 2026-11-19 10:00\n\n- **Question:** {n}?\n- **Outcome:** " + "o" * size
        opened = [ask(n, "open", 3500) for n in (1, 2)]
        closed = [ask(n, f"answered 2026-11-{day}", 3500) for n, day in ((3, 20), (4, 19), (5, 20), (6, 19), (7, 20), (8, 20), (9, 20))]
        self.write("company/board-desk/asks.md", front(title="Asks") + "# Asks\n\nAbout.\n\n## Open\n\n" + "\n\n".join(opened + closed) + "\n")
        [move] = kb_sweep.plan_desk(self.root, TODAY)
        self.assertEqual(self.apply()[0], 0)
        asks, archive = self.desk("asks.md"), self.desk("asks-archive-2026-11.md")
        self.assertLessEqual(len(asks.encode()), 25 * KB)
        self.assertTrue(all(a in asks for a in opened))
        self.assertEqual([a for a in closed if a not in asks], closed[:2] + [closed[3]])  # the two of 11-19, then the first of 11-20
        self.assertTrue(all(a in archive for a in closed[1:4:2]))
        self.write("company/board-desk/asks.md", front(title="Asks") + "# Asks\n\n## Open\n\n"
                   + "\n\n".join([ask(n, "open", 3000) for n in range(1, 10)]) + "\n")
        left = []
        self.assertEqual(kb_sweep.plan_desk(self.root, TODAY, left=left), [])
        self.assertIn("nothing else moves (an open ask stays)", left[0][2])

    def test_an_archive_with_another_owner_stops_its_page(self):
        self.pages()
        self.write("company/board-desk/asks-archive-2026-11.md", front(owner="cto", status="archived") + "# x\n")
        left = []
        self.assertNotIn("asks.md", [m.page.name for m in kb_sweep.plan_desk(self.root, TODAY, left=left)])
        self.assertIn("another owner", left[0][2])


class TheRealRepo(unittest.TestCase):
    def test_the_stamp_file_exists_so_the_14_day_trigger_cant_go_quiet(self):
        self.assertTrue((SCRIPTS.parent / "knowledge" / SWEEP_STAMPS).is_file())

    def test_each_owners_routine_runs_the_sweep_so_nobody_has_to_order_it(self):
        claude = SCRIPTS.parent / ".claude"
        self.assertIn("kb_sweep.py --apply --owner ceo", (claude / "skills" / "report" / "SKILL.md").read_text())
        self.assertIn("kb_sweep.py --apply --owner cto", (claude / "agents" / "engineering" / "cto.md").read_text())

    def test_the_cold_pages_the_tool_writes_to_have_their_tables(self):
        cold = (SCRIPTS.parent / "knowledge" / "engineering" / "standards" / "lessons-learned-archive.md").read_text().split("\n")
        self.assertIsNotNone(kb_sweep.log_span(cold, kb_sweep.LESSONS_LOG[1]))

    def test_a_dry_run_of_the_real_kb_finishes(self):
        result = subprocess.run([sys.executable, str(SCRIPTS / "kb_sweep.py"), "--transcripts", str(SCRIPTS / "tests" / "fixtures")],
                                capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Dry run: nothing changed.", result.stdout)


if __name__ == "__main__":
    unittest.main()
