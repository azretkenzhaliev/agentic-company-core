"""Tests for scripts/order_lengths.py. Every folder is made up in a temp dir."""

import contextlib
import io
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

import order_lengths  # noqa: E402

FENCE = "```"
DIRECTIVE = f"""# D-20260110-x: a test directive

## Orders

### ORDER D-20260110-x/1   from: ceo   to: analyst
{FENCE}
ORDER D-20260110-x/1   from: ceo   to: analyst
Objective:        A note.
Context:          knowledge/a.md,
                  knowledge/b.md
Acceptance criteria (1 and 2 are about this):
  1. One note.
Constraints:      S. No web.
Report back with: REPORT
{FENCE}

{FENCE}
ORDER D-20260110-x/2   from: ceo   to: cto (lane A)
Objective:        Fix it.
Tasks:
  1. Do it.
{FENCE}

## Status log

| Date | Who | Event |
|---|---|---|
| 2026-01-10 | ceo | ORDERS /1-/2 logged before sending. |
| 2026-01-12 | ceo | ORDER /3 to the cmo, logged before sending (scratchpad o3.txt). |
| 2026-01-13 | ceo | ORDER sent, text: ORDER D-20260110-x/4   from: ceo   to: platform-engineer<br>Objective: one.<br>Context: abc<br>Constraints: de |
| 2026-01-14 | ceo | NEXT: ORDER /5 sent once the Board answers. |
| 2026-01-14 | cto | REPORT /1 DONE; ORDER D-20251212-y/7 sent by the CTO. |
"""


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class OrderLengthsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.folder = self.root / order_lengths.DIRECTIVES
        write(self.folder / "D-20260110-x.md", DIRECTIVE)

    def tearDown(self):
        self.tmp.cleanup()

    def test_context_plus_constraints_whitespace_collapsed(self):
        text = "Objective: x\nContext:   a  b\n           c\nConstraints: d\nReport back with: REPORT"
        self.assertEqual(order_lengths.length_of(text), len("a b c") + len("d"))

    def test_acceptance_criteria_with_a_note_ends_context(self):
        found = order_lengths.orders_in(DIRECTIVE)
        self.assertEqual(found[("D-20260110-x", 1)], ("analyst", len("knowledge/a.md, knowledge/b.md") + len("S. No web."),
                                                      None))

    def test_an_order_without_either_field_counts_0_and_its_role_drops_the_lane(self):
        self.assertEqual(order_lengths.orders_in(DIRECTIVE)[("D-20260110-x", 2)], ("cto", 0, None))

    def test_a_row_that_holds_an_order_dates_it(self):
        found = order_lengths.orders_in(DIRECTIVE)
        self.assertEqual(found[("D-20260110-x", 4)], ("platform-engineer", len("abc") + len("de"), date(2026, 1, 13)))

    def test_sent_rows_ranges_other_directives_and_not_next(self):
        dates = order_lengths.sent_dates(DIRECTIVE, "D-20260110-x")
        self.assertEqual(dates[("D-20260110-x", 1)], date(2026, 1, 10))
        self.assertEqual(dates[("D-20260110-x", 2)], date(2026, 1, 10))
        self.assertEqual(dates[("D-20260110-x", 3)], date(2026, 1, 12))
        self.assertEqual(dates[("D-20251212-y", 7)], date(2026, 1, 14))
        self.assertNotIn(("D-20260110-x", 5), dates)  # a NEXT row plans, it doesn't send

    def test_an_archive_counts_for_its_directive_and_the_earliest_date_wins(self):
        write(self.folder / "D-20260110-x-archive-1.md",
              "| 2026-01-09 | ceo | ORDER /2 logged before sending. |\n")
        per_role, _, _ = order_lengths.measure(self.folder, date(2026, 1, 9), date(2026, 1, 9))
        self.assertEqual(per_role, {"cto": [0]})

    def test_measure_range_no_text_and_undated(self):
        write(self.folder / "D-20260111-z.md",
              f"{FENCE}\nORDER D-20260111-z/1   from: ceo   to: critic\nContext: x\n{FENCE}\n")
        per_role, no_text, undated = order_lengths.measure(self.folder, date(2026, 1, 10), date(2026, 1, 12))
        self.assertEqual(sorted(per_role), ["analyst", "cto"])
        self.assertEqual(no_text, 1)  # /3, sent from a scratch file
        self.assertEqual(undated, 1)  # z/1 has no row

    def test_main_prints_roles_and_all(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = order_lengths.main(["--root", str(self.root), "--since", "2026-01-10", "--until", "2026-01-16"])
        self.assertEqual(code, 0)
        lines = out.getvalue().splitlines()
        self.assertTrue(any(line.split()[:2] == ["platform-engineer", "1"] for line in lines))
        self.assertTrue(any(line.split()[:2] == ["all", "3"] for line in lines))
        self.assertIn("no text in the KB, dated in the range: at most 2", out.getvalue())  # /3 and y/7


if __name__ == "__main__":
    unittest.main()
