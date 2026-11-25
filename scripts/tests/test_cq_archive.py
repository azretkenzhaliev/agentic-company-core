"""Tests for scripts/cq_archive.py.

Every file is built in a temporary folder; the writers that race the script are simulated at the exact moments that
matter: between its read and its compare, between the compare and the swap, and after the swap."""

import contextlib
import io
import os
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

import cq_archive  # noqa: E402
from cq_archive import main, plan, run  # noqa: E402

sys.path.append(str(SCRIPTS / "hooks"))
from cq_write import under_ceo  # noqa: E402

H1 = "## ORDER D-20260111-x/1 (CTO; Seniors write REPORT lines here)"
H2 = "## ORDER D-20260111-x/2 (CTO)"
CEO = "CEO RULING 23:30:30Z (for every running CTO): batch PRs."
T4 = "REPORT D-20260111-x/1.WS1.T4   status: DONE   branch a1..b1 (ready for review)"
T5 = "REPORT D-20260111-x/1.WS1.T5   status: DONE   branch c1..d1 (ready for review)"
HANDLED = "HANDLED (CEO 20:50:30Z: read). Was: NEEDS-CEO-NOW (CTO /1, 2026-01-11 20:10:30Z by date -u): switch-on"
NEEDS = "NEEDS-CEO-NOW (CTO /1, 2026-01-11 21:00:00Z by date -u): a one-way door, b3"
OLD_RP = "RESUME POINT 2026-01-11T20:00:00Z (date -u; CTO /1; overwrite). Old state."
ANSWER = "ANSWER (CTO /1, 2026-01-11 23:40Z by date -u) to the 23:30:30Z ruling: noted"
NEW_RP = "RESUME POINT 2026-01-12T00:05:30Z (date -u; CTO /1; overwrites 20:00:00Z). DONE: T4. ACTED: /1.WS1.T4"
CTO_RP = "RESUME POINT /2 (CTO, 2026-01-11 16:45Z by date -u; overwrite): the CTO's lane"
STAFF_RP = "RESUME POINT /2.WS1 (Staff DD-1, 2026-01-11 16:20Z; overwrite): the Staff's lane"
COORD = "COORDINATION (CTO /1 to the /2 CTO, 2026-01-11 23:50Z): hello"
SAMPLE = "\n".join(["# CTO's questions for the CEO (acme)", "", H1, CEO, T4, T5, HANDLED, NEEDS, OLD_RP, ANSWER, NEW_RP,
                    "", H2, CTO_RP, STAFF_RP, COORD, ""])
MOVED = [T4, HANDLED, OLD_RP]  # what SAMPLE gives up, in file order
OLD_ARCHIVE = "# ceo-questions, archive: search it, don't load it\n\n## ORDER D-20260101-old/9\nREPORT old line\n"


def lines(text):
    return [line for line in text.split("\n") if line.strip()]


class Base(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.dir = Path(folder.name)
        self.src, self.arc = self.dir / "ceo-questions.md", self.dir / "ceo-questions-archive.md"
        grace = mock.patch.object(cq_archive, "GRACE", 0)
        grace.start()
        self.addCleanup(grace.stop)

    def make(self, text=SAMPLE, archive=OLD_ARCHIVE):
        self.src.write_text(text, encoding="utf-8")
        if archive is not None:
            self.arc.write_text(archive, encoding="utf-8")

    def run_it(self, *args, **kwargs):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = run(self.src, *args, **kwargs)
        return code, out.getvalue()

    def texts(self):
        return self.src.read_text(encoding="utf-8"), self.arc.read_text(encoding="utf-8")

    def assert_moved_once(self, moved=MOVED):
        source, archive = self.texts()
        for line in moved:
            self.assertNotIn(line, lines(source))
            self.assertEqual(lines(archive).count(line), 1, line)


class WhatMoves(Base):
    def test_moves_handled_acted_reports_and_superseded_resume_points_under_the_same_heading(self):
        self.make()
        code, out = self.run_it()
        self.assertEqual(code, 0, out)
        source, archive = self.texts()
        self.assertEqual(source, SAMPLE.replace(f"{T4}\n", "").replace(f"{HANDLED}\n", "").replace(f"{OLD_RP}\n", ""))
        self.assertEqual(archive, OLD_ARCHIVE + "\n" + "\n".join([H1, *MOVED]) + "\n")

    def test_an_open_needs_line_never_moves_not_even_in_a_closed_section(self):
        acted_needs = "REPORT D-20260111-x/1.WS1.T6   status: BLOCKED; NEEDS-CEO-NOW written above"
        self.make(SAMPLE.replace(NEW_RP, f"{acted_needs}\n{NEW_RP}, /1.WS1.T6"))
        self.run_it()
        self.assertIn(NEEDS, lines(self.texts()[0]))
        self.assertIn(acted_needs, lines(self.texts()[0]))
        self.make()
        code, _ = self.run_it(closed=["D-20260111-x/1"])
        self.assertEqual(code, 0)
        source, archive = self.texts()
        self.assertEqual(lines(source)[1:4], [H1, CEO, NEEDS])  # its heading stays with them
        self.assertNotIn(NEEDS, archive)
        self.assertNotIn(CEO, archive)

    def test_a_line_it_cant_classify_never_moves(self):
        unknown = ["FYI (Staff DD-2 to the CTO /34): T-3 is live", "SETTING (CTO /34): `page_size` set",
                   "### CEO ruling 2026-01-09 13:25Z", "Some free text a writer added", "- a list item", "**CEO, 2026-01-08** bold ruling",
                   "PAUSE (CTO /1, 2026-01-11 22:00Z): stop T5"]
        self.make(SAMPLE.replace(f"{NEW_RP}\n", "\n".join([*unknown, NEW_RP]) + "\n"))
        self.run_it()
        source, archive = self.texts()
        for line in unknown:
            self.assertIn(line, lines(source))
            self.assertNotIn(line, archive)

    def test_lines_under_no_heading_and_out_of_scope_orders_stay(self):
        """The HANDLED line under /2's heading names /1 first (`CTO
        /1`), so /2's run keeps it, and /1's own run moves it, under /1's heading."""
        self.make(f"{HANDLED}\n" + SAMPLE.replace(COORD, f"{COORD}\n{HANDLED} (2)"))
        code, out = self.run_it(orders=["D-20260111-x/2"])
        source, _ = self.texts()
        self.assertEqual(lines(source)[0], HANDLED)  # above every heading
        for line in (T4, OLD_RP, f"{HANDLED} (2)"):  # /1 isn't the caller's order
            self.assertIn(line, lines(source))
        self.assertIn("1 HANDLED naming another order first", out)
        self.run_it(orders=["D-20260111-x/1"])
        source, archive = self.texts()
        self.assertNotIn(f"{HANDLED} (2)", source)
        self.assertTrue(archive.endswith(f"{HANDLED} (2)\n"))

    def test_a_handled_line_under_another_heading_moves_with_the_order_it_names(self):
        # A `>>` lands a line under the file's last heading.
        stray = "HANDLED (RULING /1/50) /1.CTO 2026-01-12T01:00Z (CTO, by date -u): appended under the last heading"
        full = "HANDLED (CEO 01:10Z) NEEDS-CEO-NOW D-20260111-x/1.WS1 2026-01-12T01:05Z: by its full id"
        own = "HANDLED (CEO 01:20Z) /2.WS1 asked about /1.WS1's lock: it names its own heading's order too"
        other = "HANDLED (CEO 01:30Z) /10.CTO and D-20260111-x/12: other orders"
        still_open = "NEEDS-CEO-NOW /1.CTO 2026-01-12T01:40Z (CTO, by date -u): not handled"
        text = SAMPLE.replace(COORD, "\n".join([COORD, stray, full, own, other, still_open]))
        self.make(text)
        code, out = self.run_it(orders=["D-20260111-x/1"])
        self.assertEqual(code, 0, out)
        source, archive = self.texts()
        self.assertEqual(source, text.replace(f"{T4}\n", "").replace(f"{HANDLED}\n", "").replace(f"{OLD_RP}\n", "")
                         .replace(f"{stray}\n", "").replace(f"{full}\n", ""))
        self.assertEqual(archive, OLD_ARCHIVE + "\n" + "\n".join([H1, *MOVED, stray, full]) + "\n")
        self.assertIn("HANDLED, under another heading", out)
        self.make(text)
        self.run_it()  # every order: each HANDLED line goes under the heading it sits under, as before
        self.assertTrue(self.texts()[1].endswith("\n".join([H2, stray, full, own, other]) + "\n"))

    def test_a_short_id_names_the_last_order_before_the_line_ending_so(self):
        old = "## ORDER D-20260101-old/1 (CTO)"
        stray = "HANDLED (CEO 01:10Z) NEEDS-CEO-NOW /1.CTO 2026-01-12T01:05Z: appended under the last heading"
        self.make(SAMPLE.replace(H1, f"{old}\nHANDLED old\n\n{H1}").replace(COORD, f"{COORD}\n{stray}"))
        self.run_it(orders=["D-20260101-old/1"])
        self.assertIn(stray, lines(self.texts()[0]))
        self.run_it(orders=["D-20260111-x/1"])
        source, archive = self.texts()
        self.assertNotIn(stray, lines(source))
        self.assertTrue(archive.endswith("\n".join([H1, *MOVED, stray]) + "\n"))

    def test_the_first_order_a_handled_line_names_decides_where_it_goes(self):
        """A line naming an order out of scope first and this one second stays; one naming this one first moves."""
        other_first = "HANDLED (CEO 02:00Z) D-20260111-x/5.CTO waits on D-20260111-x/1: about /5"
        this_first = "HANDLED (CEO 02:10Z) D-20260111-x/1.WS1, then D-20260111-x/5: about /1"
        text = SAMPLE.replace(COORD, f"{COORD}\n{other_first}\n{this_first}") + "## ORDER D-20260111-x/5 (CTO)\nFYI\n"
        self.make(text)
        code, out = self.run_it(orders=["D-20260111-x/1"])
        self.assertEqual(code, 0, out)
        source, archive = self.texts()
        self.assertIn(other_first, lines(source))
        self.assertNotIn(other_first, archive)
        self.assertNotIn(this_first, lines(source))
        self.assertTrue(archive.endswith("\n".join([H1, *MOVED, this_first]) + "\n"))

    def test_a_short_id_names_its_own_heading_s_directive_first(self):
        """Under ORDER D-20260112-y/2, a short /1 is y/1 when the file has that heading,
        even when x/1's heading is the last one before the line ending /1."""
        y1, y2 = "## ORDER D-20260112-y/1 (CTO)", "## ORDER D-20260112-y/2 (CTO)"
        stray = "HANDLED (CEO 02:20Z) /1.CTO: written under y/2, about y/1"
        text = SAMPLE.replace(H1, f"{y1}\nFYI y1\n\n{H1}") + f"{y2}\n{stray}\n"
        self.make(text)
        self.run_it(orders=["D-20260111-x/1"])
        self.assertIn(stray, lines(self.texts()[0]))
        self.run_it(orders=["D-20260112-y/1"])
        source, archive = self.texts()
        self.assertNotIn(stray, lines(source))
        self.assertTrue(archive.endswith("\n".join([y1, stray]) + "\n"))

    def test_a_heading_without_an_order_id_is_no_order_s(self):
        """--order and --closed name only ORDER ids."""
        notes = "# Notes about /5"
        self.make(SAMPLE + f"{notes}\nHANDLED a note\n")
        before = self.texts()
        for args in ({"orders": [notes]}, {"closed": [notes]}):
            with self.subTest(args=args):
                code, out = self.run_it(**args)
                self.assertEqual(code, 2, out)
                self.assertEqual(self.texts(), before)

    def test_a_report_moves_only_when_a_later_line_of_its_order_marks_it_acted(self):
        full = "ACTED: D-20260111-x/1.WS1.T5"
        self.make(SAMPLE.replace(NEW_RP, f"{NEW_RP}\n{T4} (again, after the mark)").replace(COORD, f"{COORD} {full}"))
        self.run_it()
        source, _ = self.texts()
        self.assertIn(T5, lines(source))  # marked under another order's heading
        self.assertIn(f"{T4} (again, after the mark)", lines(source))
        self.make(SAMPLE.replace("ACTED: /1.WS1.T4", f"{full}, and /1.WS1.T4"))
        self.run_it()
        self.assert_moved_once([T4, T5])

    def test_a_mark_names_a_task_exactly(self):
        for mark in ("ACTED: /1.WS1", "ACTED: /1.WS1.T45", "ACTED /1.WS1.T4", "acted: /1.WS1.T4"):
            self.make(SAMPLE.replace("ACTED: /1.WS1.T4", mark))
            self.run_it()
            self.assertIn(T4, lines(self.texts()[0]), mark)

    def test_a_newer_resume_point_of_another_lane_supersedes_nothing(self):
        staff = "RESUME POINT /2.WS1 (Staff DD-1, 2026-01-11 17:00Z; overwrite): newer than the CTO's"
        self.make(SAMPLE.replace(STAFF_RP, staff))
        self.run_it(orders=["D-20260111-x/2"])
        self.assertEqual(lines(self.texts()[0])[-3:], [CTO_RP, staff, COORD])

    def test_resume_points_supersede_only_in_their_own_lane_and_by_a_newer_date(self):
        older_cto = "RESUME POINT /2 (CTO, 2026-01-11 15:00Z by date -u): an older CTO line"
        later_but_older = "RESUME POINT 2026-01-11T19:00:00Z (CTO /1): appended after, dated before"
        undated = "RESUME POINT 23:10Z (CTO /1; overwrites 2026-01-11 20:00Z): no date of its own"
        text = SAMPLE.replace(CTO_RP, f"{older_cto}\n{CTO_RP}").replace(f"{NEW_RP}\n", f"{undated}\n{NEW_RP}\n{later_but_older}\n")
        self.make(text)
        self.run_it()
        source, archive = self.texts()
        self.assertIn(older_cto, archive)
        for line in (CTO_RP, STAFF_RP, NEW_RP, later_but_older, undated):
            self.assertIn(line, lines(source), line)
        self.assertEqual(Counter(p.moves[i] for p in [plan(text)] for i in p.moves)["superseded RESUME POINT"], 2)

    def test_a_closed_section_moves_whole_with_its_blank_lines(self):
        self.make()
        code, _ = self.run_it(closed=["D-20260111-x/2"])
        self.assertEqual(code, 0)
        source, archive = self.texts()
        self.assertNotIn(H2, source)
        self.assertTrue(archive.endswith("\n".join([H2, CTO_RP, STAFF_RP, COORD]) + "\n"))
        self.assertTrue(source.endswith(f"{NEW_RP}\n\n"))

    def test_a_ceo_line_and_the_lines_under_it_move_together_or_stay_together(self):
        """A line cq_write.ceo_line counts as the CEO's and the indented, numbered or `(` lines under it are one reply to the capacity scan. A HANDLED (CEO ...) line alone
        moves, as before; with lines under it that stay, it stays with them, under its own heading or as a stray under
        another; a CEO line's lines stay with it in a closed section too, with --all as well."""
        reply = ["HANDLED (CEO 21:05:00Z) /1.CTO 2026-01-11T21:00:00Z: yes, in two steps:", "  1. switch it on",
                 "(2) then tell the Board"]
        lone = "HANDLED (CEO 21:10:00Z) /1.CTO: read"
        stray = ["HANDLED (CEO 01:10Z) NEEDS-CEO-NOW D-20260111-x/1.WS1 2026-01-12T01:05Z: by its full id",
                 "  and the detail under it"]
        ruling = [CEO, "  1. batch by product", "(2) and by lane"]
        text = (SAMPLE.replace(CEO, "\n".join(ruling)).replace(NEEDS, "\n".join([NEEDS, *reply, lone]))
                .replace(COORD, "\n".join([COORD, *stray])))
        self.make(text)
        code, out = self.run_it(orders=["D-20260111-x/1"])
        self.assertEqual(code, 0, out)
        source, archive = self.texts()
        for unit in (reply, stray, ruling):
            self.assertIn("\n".join(unit) + "\n", source)
            for line in unit:
                self.assertNotIn(line, archive)
        self.assertEqual(archive, OLD_ARCHIVE + "\n" + "\n".join([H1, T4, HANDLED, lone, OLD_RP]) + "\n")
        self.assertIn("2 of a CEO line's reply, kept whole", out)  # reply's and stray's HANDLED lines
        self.assertIn("while they stand in the file: >> the CEO line with its lines, in their order, as one heredoc",
                      out)
        held = "  NEEDS-CEO-NOW /1.CTO 2026-01-11T21:20:00Z (CTO): and one more"  # it never moves in a closed section
        text = SAMPLE.replace(CEO, "\n".join(ruling)).replace(NEEDS, "\n".join([NEEDS, reply[0], held, lone]))
        self.make(text)
        code, out = self.run_it(closed=["D-20260111-x/1"])
        self.assertEqual(code, 0, out)
        source, archive = self.texts()
        self.assertEqual(lines(source)[1:9], [H1, *ruling, NEEDS, reply[0], held, H2])  # its heading stays with them
        self.assertIn(lone, archive)
        for line in (*ruling, reply[0], held):
            self.assertNotIn(line, archive)
        p = plan(text, closed=("D-20260111-x/1",), whole=True)  # --all: the CEO's lines stay, with its own
        self.assertEqual([i for i, line in enumerate(p.lines) if line in ruling and i in p.moves], [])
        self.assertIn(p.lines.index(reply[0]), p.moves)  # the whole reply moves: --all moves NEEDS lines too
        self.assertIn(p.lines.index(held), p.moves)

    def test_trim_keeps_a_ceo_line_with_the_lines_under_it(self):
        """--trim moves an old LANES or DEPLOY DONE line, but not apart from a reply it makes with the
        lines under it."""
        old = "DEPLOY DONE D-20260115-c/1.WS-8 2026-01-15T16:30Z (CEO, by date -u). X = 1a2b3c4d."
        text = "\n".join(["# ceo-questions", old, "  1. smoke check passed", old.replace("(CEO", "(Staff WS-8"), ""])
        p = cq_archive.trim_plan(text, 1768910400.0)  # 2026-01-20T12:00Z
        self.assertEqual(sorted(p.moves), [3])
        self.assertEqual(p.kept[cq_archive.KEPT["together"]], 1)

    def assert_no_new_join(self, before, source, added=""):
        """No indented, numbered or `(` line stands under a CEO line, in the file or in what the archive gained, that
        it didn't stand under in the file before (cq_write.under_ceo's pairs, by count)."""
        self.assertEqual(under_ceo(source) - under_ceo(before), Counter())
        self.assertEqual(under_ceo(added) - under_ceo(before), Counter())

    def test_a_move_never_leaves_an_indented_numbered_or_paren_line_under_a_ceo_line(self):
        """A HANDLED line with an indented, numbered or `(` line under it, after a CEO line that ends the file: moved
        alone, it would leave the other under the CEO line, where the scan joins it to the CEO's reply. So the HANDLED
        line stays; so does one under a heading ceo_line counts, a stray, and a closed section's blank line. With no
        CEO line above, it moves."""
        ruling = "CEO RULING 2026-01-12T00:30Z (for the /2 CTO): go on."
        done = "HANDLED /2.CTO 2026-01-12T01:00Z (CTO, by date -u): done, in two steps:"
        stray = "HANDLED /1.CTO 2026-01-12T01:10Z (CTO, by date -u): appended under the last heading:"
        h3, done3 = "## ORDER D-20260111-x/3 (CEO to CTO, 2026-01-12 00:10Z): three", "HANDLED /3.CTO (CTO): done:"
        for form in ("  1. switched it on", "1. switched it on", "(1) switched it on"):
            for text, order, kept in ((SAMPLE + "\n".join([ruling, done, form, ""]), "D-20260111-x/2", done),
                                      (SAMPLE + "\n".join([h3, done3, form, ""]), "D-20260111-x/3", done3),
                                      (SAMPLE + "\n".join([ruling, stray, form, ""]), "D-20260111-x/1", stray)):
                with self.subTest(form=form, order=order):
                    self.make(text)
                    code, out = self.run_it(orders=[order])
                    self.assertEqual(code, 0, out)
                    source, archive = self.texts()
                    self.assertTrue(source.endswith(f"\n{kept}\n{form}\n"), source)
                    self.assertNotIn(kept, archive)
                    self.assertIn(f"1 {cq_archive.KEPT['apart']}", out)
                    self.assertIn(". The 1 kept so no line joins a CEO line's reply stay where they are, also by hand, "
                                  "until the CEO line above them, or the line under them, leaves. Move the rest by hand",
                                  out)
                    self.assert_no_new_join(text, source, archive[len(OLD_ARCHIVE):])
            with self.subTest(form=form, above="no CEO line"):
                text = SAMPLE + "\n".join([done, form, ""])
                self.make(text)
                self.run_it(orders=["D-20260111-x/2"])
                source, archive = self.texts()
                self.assertTrue(source.endswith(f"\n{COORD}\n{form}\n"))
                self.assertTrue(archive.endswith(f"\n{H2}\n{done}\n"))
        held = "  NEEDS-CEO-NOW /2.CTO 2026-01-12T01:20Z (CTO, by date -u): one more"  # never moves in a closed section
        text = SAMPLE + "\n".join([ruling, "", held, ""])
        self.make(text)
        code, out = self.run_it(closed=["D-20260111-x/2"])
        self.assertEqual(code, 0, out)
        source, archive = self.texts()
        self.assertTrue(source.endswith(f"\n{H2}\n{ruling}\n\n{held}\n"), source)  # the blank line between them stays
        self.assertTrue(archive.endswith("\n".join([H2, CTO_RP, STAFF_RP, COORD]) + "\n"))
        self.assert_no_new_join(text, source, archive[len(OLD_ARCHIVE):])
        # A line kept so alone gets no advice to move it by hand.
        text = "\n".join(["## ORDER D-20260111-x/8 (CTO)", ruling, "HANDLED /9.CTO (CTO): done, under /8's heading",
                          "  1. switched it on", "## ORDER D-20260111-x/9 (CTO)", ""])
        self.make(text)
        code, out = self.run_it(orders=["D-20260111-x/9"])
        self.assertEqual((code, self.texts()[0]), (0, text))
        self.assertIn(f"Kept: 1 {cq_archive.KEPT['apart']}. The 1 kept so no line joins a CEO line's reply stay where "
                      "they are, also by hand, until the CEO line above them, or the line under them, leaves.\n", out)
        self.assertNotIn("Move the rest by hand", out)

    def test_trim_never_leaves_an_indented_line_under_a_ceo_line(self):
        """--trim's moves keep the line above too."""
        old = "DEPLOY DONE D-20260115-c/1.WS-8 2026-01-15T16:30Z (Staff WS-8, by date -u). X = 1a2b3c4d."
        text = "\n".join(["# ceo-questions", "CEO RULING 2026-01-15T16:00Z: deploy it.", old, "  1. smoke check passed",
                          old, ""])
        p = cq_archive.trim_plan(text, 1768910400.0)  # 2026-01-20T12:00Z
        self.assertEqual(sorted(p.moves), [4])
        self.assertEqual(p.kept[cq_archive.KEPT["apart"]], 1)

    def test_a_closed_run_never_puts_a_moved_line_under_a_ceo_line_in_the_archive(self):
        """With --closed, an indented, numbered or `(` line under a NEEDS-CEO-NOW line the run keeps, below a HANDLED
        line with `(CEO` as its writer field, would land in the archive right under that HANDLED line, and join its
        reply there. A blank line goes above it, and above one that would land under a heading's copy ceo_line counts,
        and one a copy the archive holds already would have stood between; a reply that moves whole gets none."""
        reply = "HANDLED (CEO 01:30Z) /2.CTO 2026-01-12T01:20Z: yes"
        ask = "NEEDS-CEO-NOW /2.CTO 2026-01-12T01:40Z (CTO, by date -u): one more:"
        h3 = "## ORDER D-20260111-x/3 (CEO to CTO, 2026-01-12 00:10Z): three"
        for form in ("  1. the detail", "1. the detail", "(1) the detail"):
            for text, order, block in ((SAMPLE + "\n".join([reply, ask, form, ""]), "D-20260111-x/2",
                                        [H2, CTO_RP, STAFF_RP, COORD, reply, "", form]),
                                       (SAMPLE + "\n".join([h3, ask, form, ""]), "D-20260111-x/3", [h3, "", form])):
                with self.subTest(form=form, order=order):
                    self.make(text)
                    code, out = self.run_it(closed=[order])
                    self.assertEqual(code, 0, out)
                    source, archive = self.texts()
                    self.assertTrue(source.endswith(f"\n{block[0]}\n{ask}\n"), source)  # the heading stays with it
                    self.assertTrue(archive.endswith("\n" + "\n".join(block) + "\n"), archive)
                    self.assert_no_new_join(text, source, archive[len(OLD_ARCHIVE):])
            with self.subTest(form=form, reply="whole"):
                text = SAMPLE + "\n".join([reply, form, ""])
                self.make(text)
                self.run_it(closed=["D-20260111-x/2"])
                self.assertTrue(self.texts()[1].endswith(f"\n{COORD}\n{reply}\n{form}\n"))
            with self.subTest(form=form, archive="holds the line between"):
                fyi = "FYI (CTO /2): the line between"
                p = plan(SAMPLE + "\n".join([reply, fyi, form, ""]), closed=("D-20260111-x/2",))
                added = cq_archive.to_archive(p, f"{OLD_ARCHIVE}\n{H2}\n{fyi}\n")
                self.assertTrue(added.endswith("\n" + "\n".join([H2, CTO_RP, STAFF_RP, COORD, reply, "", form]) + "\n"))

    def test_a_long_resume_point_is_named(self):
        self.make(SAMPLE.replace("Old state.", "x" * 1600))
        _, out = self.run_it(dry_run=True)
        self.assertNotIn("Over about", out)  # it moves anyway
        self.make(SAMPLE.replace("DONE: T4.", "DONE: " + "y" * 1600))
        _, out = self.run_it(dry_run=True)
        self.assertIn("Over about 1.5 KB: the RESUME POINT at line 11", out)


class Safety(Base):
    def test_line_counts_add_up_and_the_old_files_are_never_truncated(self):
        self.make()
        before_src, before_arc = self.texts()
        with open(self.src, "rb") as old_src, open(self.arc, "rb") as old_arc:
            code, _ = self.run_it()
            self.assertEqual(old_src.read().decode(), before_src)  # the file it read is whole: only swapped away
            self.assertTrue(old_arc.read().decode().startswith(before_arc))  # appended to, never rewritten
        self.assertEqual(code, 0)
        source, archive = self.texts()
        self.assertEqual(len(lines(before_src)) + len(lines(before_arc)) + 1, len(lines(source)) + len(lines(archive)))  # + its heading
        self.assertEqual(Counter(lines(before_src)), Counter(lines(source)) + Counter(MOVED))

    def test_dry_run_changes_nothing_and_prints_the_sizes(self):
        self.make()
        before = self.texts()
        code, out = self.run_it(dry_run=True)
        self.assertEqual((code, self.texts()), (0, before))
        self.assertIn("Would move 3 lines", out)
        self.assertIn("ceo-questions.md: ", out)
        self.assertRegex(out, r"ceo-questions-archive\.md: [\d.]+ KB, 4 lines -> [\d.]+ KB, 9 lines")
        self.assertIn("Dry run: nothing changed.", out)

    def test_a_rerun_adds_nothing_twice(self):
        self.make()
        self.run_it()
        after = self.texts()
        code, out = self.run_it()
        self.assertEqual((code, self.texts()), (0, after))
        self.assertIn("Nothing to move", out)

    def test_identical_lines_each_get_a_copy(self):
        self.make(SAMPLE.replace(HANDLED, f"{HANDLED}\n{HANDLED}"))
        code, out = self.run_it()
        self.assertEqual(code, 0)
        self.assertIn("Moved 4 lines", out)
        source, archive = self.texts()
        self.assertNotIn(HANDLED, source)
        self.assertEqual(lines(archive).count(HANDLED), 2)
        self.assertEqual(self.run_it()[0], 0)
        self.assertEqual(lines(self.texts()[1]).count(HANDLED), 2)

    def test_a_new_archive_gets_kb_sweeps_title(self):
        self.make(archive=None)
        self.run_it()
        self.assertTrue(self.texts()[1].startswith(cq_archive.ARCHIVE_TITLE + "\n" + H1 + "\n"))

    def test_an_append_after_the_run_starts_its_own_line(self):
        self.make(SAMPLE.rstrip("\n") + f"\n{HANDLED} (last)\n")
        self.run_it()
        with open(self.src, "a") as f:
            f.write("REPORT D-20260111-x/2.T1   status: DONE\n")
        self.assertEqual(lines(self.texts()[0])[-1], "REPORT D-20260111-x/2.T1   status: DONE")

    def test_a_code_fence_holds_the_file(self):
        self.make(SAMPLE + "```\n# not a heading\n```\n")
        before = self.texts()
        code, out = self.run_it()
        self.assertEqual((code, self.texts()), (1, before))
        self.assertIn("code fence", out)

    def test_an_unknown_order_changes_nothing(self):
        self.make()
        before = self.texts()
        self.assertEqual(self.run_it(orders=["D-20260111-x/12"])[0], 2)
        self.assertEqual(self.run_it(closed=["D-20260111-x"])[0], 2)
        self.assertEqual(self.texts(), before)

    def test_the_cli_takes_only_a_ceo_questions_file(self):
        self.make()
        other = self.dir / "board-steps.md"
        other.write_text(SAMPLE)
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as stop:
            main([str(other)])
        self.assertEqual(stop.exception.code, 2)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main([str(self.src), "--order", "D-20260111-x/1"]), 0)
        self.assert_moved_once()


class Add(Base):
    """A line appended with `>>` lands under the file's last heading, maybe another order's. --add puts one line under
    its own order's heading."""

    LINE = "REPORT D-20260111-x/1.WS1.T6   status: DONE   branch e1..f1"

    def add(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = main([str(self.src), *args])
        return code, out.getvalue()

    def test_a_line_for_the_earlier_of_two_orders_lands_under_its_heading(self):
        self.make()
        self.assertEqual(self.add("--order", "D-20260111-x/1", "--add", self.LINE)[0], 0)
        got = self.src.read_text(encoding="utf-8").split("\n")
        self.assertEqual(got[got.index(NEW_RP) + 1], self.LINE)  # after /1's last line, before its blank line and H2
        self.assertEqual(got, SAMPLE.split("\n")[:11] + [self.LINE] + SAMPLE.split("\n")[11:])
        self.assertEqual(self.arc.read_text(encoding="utf-8"), OLD_ARCHIVE)  # it moves nothing

    def test_the_last_order_and_its_last_heading(self):
        self.make(SAMPLE + "## ORDER D-20260111-x/1 (resumed)\nCOORDINATION x\n\n\n")
        self.assertEqual(self.add("--order", "D-20260111-x/2", "--add", "x2")[0], 0)
        self.assertEqual(self.add("--order", "D-20260111-x/1", "--add", "x1")[0], 0)
        got = lines(self.src.read_text(encoding="utf-8"))
        self.assertEqual(got[got.index(COORD) + 1], "x2")
        self.assertEqual(got[-2:], ["COORDINATION x", "x1"])  # under /1's last heading, not its first
        self.assertTrue(self.src.read_text(encoding="utf-8").endswith("x1\n\n\n"))

    def test_no_heading_one_line_and_one_order_or_nothing_changes(self):
        self.make()
        before = self.texts()
        code, out = self.add("--order", "D-20260111-x/3", "--add", self.LINE)
        self.assertEqual(code, 2)
        self.assertIn("No section of ceo-questions.md is headed ORDER D-20260111-x/3, or by an id ending so: nothing added", out)
        for args in (["--add", self.LINE], ["--order", "D-20260111-x/1", "--order", "D-20260111-x/2", "--add", "x"],
                     ["--order", "D-20260111-x/1", "--add", "a\nb"], ["--order", "D-20260111-x/1", "--add", " "],
                     ["--order", "D-20260111-x/1", "--closed", "D-20260111-x/2", "--add", "x"]):
            with self.subTest(args=args), self.assertRaises(SystemExit) as stop:
                self.add(*args)
            self.assertEqual(stop.exception.code, 2)
        self.assertEqual(self.add("--order", "D-20260111-x/1", "--add", self.LINE, "--dry-run")[0], 0)
        self.assertEqual(self.texts(), before)

    def test_a_short_or_full_id_names_one_heading_or_nothing_is_added(self):
        """`--order /2` for `ORDER D-20260111-x/2`, and the reverse."""
        self.make(SAMPLE + "# Order /7 (2026-01-18, T-3)\nQUESTION x\n")
        self.assertEqual(self.add("--order", "/2", "--add", "short")[0], 0)
        self.assertEqual(self.add("--order", "D-20260111-x/7", "--add", "full")[0], 0)
        got = lines(self.src.read_text(encoding="utf-8"))
        self.assertEqual(got[got.index(COORD) + 1], "short")
        self.assertEqual(got[-1], "full")
        self.make(SAMPLE + "## ORDER D-20260112-y/2 (another directive)\n")
        before = self.texts()
        code, out = self.add("--order", "/2", "--add", "x")
        self.assertEqual(code, 2)
        self.assertIn("ORDER /2 may be any of D-20260111-x/2, D-20260112-y/2", out)
        self.assertEqual(self.add("--order", "/22", "--add", "x")[0], 2)  # /22 is no end of /2's ids
        self.assertEqual(self.texts(), before)

    def test_only_a_heading_with_an_order_id_takes_the_line(self):
        """`--order /5` doesn't name "# Notes about /5"."""
        self.make(SAMPLE + "# Notes about /5\nFYI\n")
        before = self.texts()
        code, out = self.add("--order", "/5", "--add", self.LINE)
        self.assertEqual(code, 2, out)
        self.assertIn("No section of ceo-questions.md is headed ORDER /5", out)
        self.assertEqual(self.texts(), before)

    def test_text_that_splitlines_splits_is_refused(self):
        """A `\\r` reads as two lines to a splitlines() reader."""
        self.make()
        before = self.texts()
        for text in ("REPORT x\rHANDLED y", "a\r\nb", "a\x0bb", "a\x0cb", "a\x1cb", "a\x85b", "a\u2028b", "a\u2029b",
                     "a\n", "a\r"):
            with self.subTest(text=text), self.assertRaises(SystemExit) as stop:
                self.add("--order", "D-20260111-x/1", "--add", text)
            self.assertEqual(stop.exception.code, 2)
        self.assertEqual(self.texts(), before)

    def drop_after(self, swaps):
        """An Edit from a read taken before the swap lands just after it, `swaps` times: the added line is gone."""
        real, calls = cq_archive.exchange, []

        def exchange(a, b):
            old = Path(b).read_text(encoding="utf-8")
            real(a, b)
            calls.append(1)
            if len(calls) <= swaps:
                (self.dir / "edit.tmp").write_text(old, encoding="utf-8")
                os.replace(self.dir / "edit.tmp", b)
        return mock.patch.object(cq_archive, "exchange", exchange), calls

    def test_a_line_a_whole_file_write_drops_is_added_once_more(self):
        """The file is read back after the grace period."""
        self.make()
        patch, calls = self.drop_after(1)
        with patch:
            code, out = self.add("--order", "D-20260111-x/1", "--add", self.LINE)
        self.assertEqual((code, len(calls)), (0, 2), out)
        self.assertIn("dropped the line just after it was added", out)
        got = self.src.read_text(encoding="utf-8").split("\n")
        self.assertEqual(got, SAMPLE.split("\n")[:11] + [self.LINE] + SAMPLE.split("\n")[11:])

    def test_a_line_dropped_twice_exits_1_and_says_so(self):
        self.make()
        patch, calls = self.drop_after(5)
        with patch:
            code, out = self.add("--order", "D-20260111-x/1", "--add", self.LINE)
        self.assertEqual((code, len(calls)), (1, 2), out)  # one retry, then it stops
        self.assertIn("it isn't in ceo-questions.md. Add it by Edit.", out)
        self.assertNotIn("Added the line under", out)
        self.assertEqual(self.texts()[0], SAMPLE)

    def test_an_append_at_the_end_that_opened_the_file_before_the_swap_keeps_its_line(self):
        """A `>>` at the file's end during --add's swap. One that opened the
        file before the swap and writes in the grace period lands in the old file: it is appended to the new one,
        and the added line is still read back once."""
        self.make()
        late, held, real = "HANDLED (CEO 13:30:30Z) appended with >> during the swap", [], cq_archive.exchange

        def exchange(a, b):
            if not held:
                held.append(open(self.src, "a"))  # opened on the file that is about to be swapped out
            real(a, b)

        def grace(_):
            while held:
                f = held.pop()
                f.write(late + "\n")
                f.close()
        with mock.patch.object(cq_archive, "exchange", exchange), mock.patch.object(cq_archive.time, "sleep", grace):
            code, out = self.add("--order", "D-20260111-x/1", "--add", self.LINE)
        self.assertEqual(code, 0, out)
        self.assertIn("Kept 1 lines a writer added during the swap", out)
        self.assertIn("Added the line under", out)
        got = lines(self.src.read_text(encoding="utf-8"))
        self.assertEqual((got.count(self.LINE), got.count(late)), (1, 1))
        self.assertEqual(got[got.index(NEW_RP) + 1], self.LINE)
        self.assertEqual(got[-1], late)

    def test_a_line_already_in_the_file_still_counts_as_added_only_once_more(self):
        """The read-back counts copies: a REPORT line written twice must show one more copy, not just one."""
        self.make(SAMPLE.replace(NEW_RP, f"{self.LINE}\n{NEW_RP}"))
        patch, calls = self.drop_after(1)
        with patch:
            code, out = self.add("--order", "D-20260111-x/1", "--add", self.LINE)
        self.assertEqual((code, len(calls)), (0, 2), out)
        self.assertEqual(lines(self.texts()[0]).count(self.LINE), 2)

    def test_a_code_fence_holds_the_add(self):
        self.make(SAMPLE + "```\n")
        code, out = self.add("--order", "D-20260111-x/1", "--add", self.LINE)
        self.assertEqual(code, 1)
        self.assertIn("is a code fence. Add the line by Edit.", out)

    def test_a_writer_s_append_during_the_swap_is_kept(self):
        self.make()
        added = "REPORT D-20260111-x/2.T9   status: DONE   (appended with >> mid-run)"
        real, calls = cq_archive.exchange, []

        def exchange(a, b):
            calls.append(1)
            if len(calls) == 1:
                with open(self.src, "a") as f:
                    f.write(added + "\n")
            real(a, b)
        with mock.patch.object(cq_archive, "exchange", exchange):
            self.assertEqual(self.add("--order", "D-20260111-x/1", "--add", self.LINE)[0], 0)
        got = lines(self.src.read_text(encoding="utf-8"))
        self.assertEqual((got.count(self.LINE), got.count(added)), (1, 1))
        self.assertEqual(got[got.index(NEW_RP) + 1], self.LINE)


class QuestionFiles(Base):
    """--add on an order's own file, the old file's drain by --closed --all, the product file's trim, and --add's
    read-back. Made-up lines."""

    OLD = "## ORDER D-20260101-old/3 (CTO, 2026-01-01)"
    NEW = "## ORDER D-20260118-new/1 (CTO, 2026-01-18)"
    DRAINED = [OLD, "CEO RULING D-20260101-old/3/1 (2026-01-01T09:00Z, by date -u): the CEO's.",
               "NEEDS-CEO-NOW /3.CTO 2026-01-01T10:00Z (CTO). x",
               "CEO RULING D-20260101-old/3/2 (2026-01-01T10:05Z, by date -u), on NEEDS-CEO-NOW /3.CTO 10:00Z: yes.",
               "PAUSE /3 2026-01-01T11:00Z (CEO): x", "COORD /4.CTO -> /3.CTO 2026-01-01T11:30Z (CTO): to /3.",
               "RESUME POINT /3 2026-01-01T12:00Z (CTO): its last."]

    def setUp(self):
        super().setUp()
        self.content = self.dir / "workspaces" / "acme" / "content"
        self.content.mkdir(parents=True)
        self.src, self.arc = self.content / "ceo-questions.md", self.content / "ceo-questions-archive.md"
        self.log = self.dir / "knowledge" / "board" / "directives" / "D-20260101-old.md"  # its status log: CLOSED /3
        self.log.parent.mkdir(parents=True)
        self.log.write_text("# D-20260101-old\n\n## Status log\n\n| Date | Who | Event |\n|---|---|---|\n"
                            "| 2026-01-02 | CEO | CLOSED /3: ended. |\n", encoding="utf-8")

    def main_it(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = main([*args])
        return code, out.getvalue()

    def old_file(self, *old_lines):
        return "\n".join(["# ceo-questions", "CEO broadcast 2026-01-18T08:00Z: every lane.", "", *self.DRAINED,
                          *old_lines, "", self.NEW, "QUESTION /1.WS-1 -> /1.CTO 2026-01-18T09:00Z (Staff). open", ""])

    def test_add_lands_at_the_end_of_an_order_s_own_file(self):
        page = self.content / "orders" / "D-20260118-new" / "2" / "ceo-questions.md"
        page.parent.mkdir(parents=True)
        text = ("# ORDER D-20260118-new/2 (cto, 2026-01-18)\nQUESTION /2.WS-1 -> /2.CTO 2026-01-18T09:00Z (Staff). x\n"
                "RESUME POINT /2 2026-01-18T09:10Z (CTO): x\n")
        page.write_text(text, encoding="utf-8")
        for order, line in (("D-20260118-new/2", "REPORT /2.T-1 status: DONE"), ("/2", "HANDLED /2.T-1 (CTO)")):
            self.assertEqual(self.main_it(str(page), "--order", order, "--add", line)[0], 0)
        self.assertEqual(page.read_text(encoding="utf-8"), text + "REPORT /2.T-1 status: DONE\nHANDLED /2.T-1 (CTO)\n")

    def test_closed_all_drains_a_section_whole_and_a_writer_s_append_stays(self):
        text = self.old_file()
        self.make(text, archive=None)
        code, out = self.run_it(closed=["D-20260101-old/3"])  # without --all, the CEO's, NEEDS and PAUSE lines stay
        self.assertEqual(code, 0, out)
        for line in self.DRAINED[1:5]:
            self.assertIn(line, lines(self.texts()[0]))
        self.arc.unlink()
        self.make(text, archive=None)
        added, real = "LANES ASK 2026-01-18T10:00Z to duty from D-20260118-new/1: appended mid-run", cq_archive.exchange

        def exchange(a, b):
            if not added_once:
                added_once.append(1)
                with open(self.src, "a") as f:
                    f.write(added + "\n")
            real(a, b)
        added_once = []
        with mock.patch.object(cq_archive, "exchange", exchange):
            code, out = self.run_it(closed=["D-20260101-old/3"], whole=True)
        self.assertEqual(code, 0, out)
        source, archive = self.texts()
        stay = [self.DRAINED[0], self.DRAINED[1], self.DRAINED[3], self.DRAINED[4]]  # the CEO's and PAUSE lines
        self.assertEqual(lines(source), ["# ceo-questions", "CEO broadcast 2026-01-18T08:00Z: every lane.", *stay,
                                         self.NEW, "QUESTION /1.WS-1 -> /1.CTO 2026-01-18T09:00Z (Staff). open", added])
        self.assertEqual(lines(archive)[1:], [line for line in self.DRAINED if line not in stay[1:]])  # each once

    def test_closed_all_moves_nothing_while_a_line_can_t_leave(self):
        """An unanswered ask; another order's line; a line elsewhere pointing into the section. Each refuses, dry run or
        not, and names the line; once it's gone, the section drains."""
        foreign = "RULING D-20260115-other/1/31 2026-01-16T10:00Z (CEO), on x: still in force."
        pointer = ('CEO RULING D-20260118-new/1/2 (2026-01-18T09:30Z, for every running CTO; full text under "## ORDER '
                   'D-20260101-old/3", point 4): x')
        for extra, after, word in (
                (["NEEDS-CEO-NOW /3.WS-1 2026-01-01T13:00Z (WS-1 Staff). Nobody answered."], [], "unanswered NEEDS"),
                ([foreign], [], "a RULING line of D-20260115-other/1, another order's"),
                ([], [pointer], "it points to the text of ORDER D-20260101-old/3")):
            text = self.old_file(*extra) + "\n".join(after) + ("\n" if after else "")
            for dry in (True, False):
                with self.subTest(word=word, dry=dry):
                    self.make(text, archive=None)
                    code, out = self.run_it(closed=["D-20260101-old/3"], whole=True, dry_run=dry)
                    self.assertEqual(code, 1, out)
                    self.assertIn("Nothing moved: ORDER D-20260101-old/3 holds lines that can't leave yet", out)
                    self.assertIn(word, out)
                    self.assertEqual(self.src.read_text(encoding="utf-8"), text)
                    self.assertFalse(self.arc.exists())
        log = self.log.read_text(encoding="utf-8")
        for row in ("RULING /3/9", "REPORT /3 status: DONE"):  # a CLOSED row only
            with self.subTest(row=row):
                self.log.write_text(log.replace("CLOSED /3: ended.", row), encoding="utf-8")
                self.make(self.old_file(), archive=None)
                code, out = self.run_it(closed=["D-20260101-old/3"], whole=True)
                self.assertEqual(code, 1, out)
                self.assertIn("ORDER D-20260101-old/3 has no CLOSED row in knowledge/board/directives/"
                              "D-20260101-old.md's status log", out)
                self.assertFalse(self.arc.exists())
        self.log.write_text(log, encoding="utf-8")
        self.make(self.old_file(), archive=None)
        self.assertEqual(self.run_it(closed=["D-20260101-old/3"], whole=True)[0], 0)
        for args in (["--all"], ["--all", "--order", "D-20260101-old/3"], ["--trim", "--order", "D-20260118-new/1"],
                     ["--trim", "--closed", "D-20260101-old/3"]):
            with self.subTest(args=args), self.assertRaises(SystemExit) as stop:
                self.main_it(str(self.src), *args)
            self.assertEqual(stop.exception.code, 2)

    def test_a_closed_section_keeps_a_handled_line_another_order_names_first(self):
        """`--order X --closed A` keeps in A's section a HANDLED line that names first an order outside the run, and
        --all moves nothing while one is there."""
        handled = "HANDLED /2.CTO 2026-01-01T10:30Z (CTO): /2's ask, settled."
        text = "\n".join(["# ceo-questions", self.OLD, "PAUSE /3 2026-01-01T11:00Z (CEO): x", handled,
                          "## ORDER D-20260101-old/2 (CTO, 2026-01-01)", "RESUME POINT /2 2026-01-01T12:00Z (CTO): x",
                          self.NEW, "REPORT /1.T-1 status: DONE", ""])
        self.make(text, archive=None)
        code, out = self.run_it(orders=["D-20260118-new/1"], closed=["D-20260101-old/3"])
        self.assertEqual(code, 0, out)
        self.assertIn(handled, lines(self.src.read_text(encoding="utf-8")))
        self.assertIn("1 HANDLED naming another order first", out)
        self.make(text, archive=None)
        code, out = self.run_it(closed=["D-20260101-old/3"], whole=True)
        self.assertEqual(code, 1, out)
        self.assertIn("a HANDLED line naming ORDER D-20260101-old/2 first", out)
        self.assertEqual(self.src.read_text(encoding="utf-8"), text)

    def test_trim_keeps_the_latest_duty_line_and_open_claims(self):
        old = ["LANES DUTY 2026-01-17T14:00:30Z CLAIMED by D-20260117-a/5 CTO; T0.",
               "LANES TOKEN 2026-01-17T02:30:00Z CI CLAIMED by D-20260115-b/4.WS-5.T-3 for PR 3",
               "LANES TOKEN 2026-01-17T05:00:30Z CI RELEASED by D-20260115-b/4.WS-5.T-3 for PR 3 (merged)",
               "DEPLOY DONE D-20260115-c/1.WS-8 2026-01-15T16:30Z (Staff WS-8, by date -u; SA-001). X = 1a2b3c4d."]
        stay = ["LANES DUTY 2026-01-18T00:20:30Z CLAIMED by D-20260115-b/4 CTO; the latest DUTY line.",
                "LANES TOKEN 2026-01-17T02:40:30Z CORE CLAIMED by D-20260115-c/1.WS-0.T-3 for PR 7",
                "DEPLOY DONE x/7.AF 22:40Z (Staff /7.AF): no date.", "LANES EJECT 2026-01-19T07:40Z PR 4: recent.",
                "CEO broadcast 2026-01-10T00:00Z: no LANES line."]
        asked = "LANES ASK 2026-01-16T01:00:30Z to duty from D-20260115-c/1: under an order's heading."
        text = "\n".join(["# ceo-questions", *old[:2], stay[0], stay[1], old[2], old[3], *stay[2:], "", self.NEW, asked,
                          ""])
        self.make(text, archive=None)
        with mock.patch.object(cq_archive.time, "time", return_value=1768910400.0):  # 2026-01-20T12:00Z
            code, out = self.main_it(str(self.src), "--trim")
        self.assertEqual(code, 0, out)
        source, archive = self.texts()
        self.assertEqual(lines(source), ["# ceo-questions", *stay, self.NEW])
        self.assertEqual(lines(archive)[1:], ["# ceo-questions", *old, self.NEW, asked])
        self.assertIn("3 LANES or DEPLOY DONE kept", out)
        page = self.content / "orders" / "D-20260118-new" / "1" / "ceo-questions.md"
        page.parent.mkdir(parents=True)
        page.write_text(f"{self.NEW}\n{old[0]}\n", encoding="utf-8")
        with self.assertRaises(SystemExit) as stop:
            self.main_it(str(page), "--trim")  # an order's own file is never trimmed
        self.assertEqual(stop.exception.code, 2)

    def test_add_leaves_a_line_another_run_moved_to_the_archive_on_purpose(self):
        """In the grace period another cq_archive run moves the added
        HANDLED line to the archive. The read-back sees the archive's new copy and doesn't put the line back."""
        self.make()
        line, real = "HANDLED /1.WS1.T6 2026-01-18T10:00Z (CTO): settled", cq_archive.exchange

        def exchange(a, b):
            real(a, b)
            text = self.src.read_text(encoding="utf-8")
            if line in text and Path(b).name == self.src.name:  # the other run: the line leaves, the archive gains it
                with open(self.arc, "a", encoding="utf-8") as f:
                    f.write(f"{H1}\n{line}\n")
                self.src.write_text(text.replace(f"{line}\n", ""), encoding="utf-8")
        with mock.patch.object(cq_archive, "exchange", exchange):
            code, out = self.main_it(str(self.src), "--order", "D-20260111-x/1", "--add", line)
        self.assertEqual(code, 0, out)
        self.assertIn("moved it to ceo-questions-archive.md on purpose: not added again", out)
        source, archive = self.texts()
        self.assertEqual((lines(source).count(line), lines(archive).count(line)), (0, 1))


class ConcurrentWriters(Base):
    """A writer lands at each moment that matters; no line is lost, and the archive gets each moved line once."""

    def wrap_exchange(self, before_swap):
        real, calls = cq_archive.exchange, []

        def exchange(a, b):
            calls.append(1)
            before_swap(len(calls))
            real(a, b)
        return mock.patch.object(cq_archive, "exchange", exchange)

    def test_an_append_between_the_compare_and_the_swap(self):
        self.make()
        added = "REPORT D-20260111-x/2.T9   status: DONE   (appended with >> mid-run)"

        def writer(call):
            if call == 1:
                with open(self.src, "a") as f:
                    f.write(added + "\n")
        with self.wrap_exchange(writer):
            code, _ = self.run_it()
        self.assertEqual(code, 0)
        self.assertEqual(lines(self.texts()[0])[-1], added)
        self.assert_moved_once()

    def test_an_edit_between_the_read_and_the_compare(self):
        self.make()
        edited, real_append, calls = SAMPLE.replace(ANSWER, ANSWER + " (edited)"), cq_archive.append, []

        def append(path, text):
            real_append(path, text)
            if not calls:  # an Edit tool write: a new file renamed over the old
                calls.append(1)
                (self.dir / "edit.tmp").write_text(edited)
                os.replace(self.dir / "edit.tmp", self.src)
        swaps = mock.Mock(side_effect=cq_archive.exchange)
        with mock.patch.object(cq_archive, "append", append), mock.patch.object(cq_archive, "exchange", swaps):
            code, _ = self.run_it()
        self.assertEqual((code, swaps.call_count), (0, 1))  # the compare caught it: no swap until the second try
        source = self.texts()[0]
        self.assertEqual(lines(source).index(ANSWER + " (edited)"), lines(source).index(NEW_RP) - 1)  # in its place
        self.assert_moved_once()

    def test_an_archive_rewritten_before_the_swap_stops_the_move(self):
        self.make()
        real_append = cq_archive.append

        def append(path, text):
            real_append(path, text)
            path.write_text(OLD_ARCHIVE)  # a writer's Edit, from a read before the append
        with mock.patch.object(cq_archive, "append", append):
            code, out = self.run_it()
        self.assertEqual((code, self.texts()), (1, (SAMPLE, OLD_ARCHIVE)))
        self.assertIn("nothing removed", out)

    def test_an_append_that_opened_the_file_before_the_swap_and_writes_after_it(self):
        self.make()
        late, held = "REPORT D-20260111-x/2.T8   status: DONE   (written to the old file)", []

        def writer(call):
            if call == 1:
                held.append(open(self.src, "a"))

        def grace(_):
            while held:
                f = held.pop()
                f.write(late + "\n")
                f.close()
        with self.wrap_exchange(writer), mock.patch.object(cq_archive.time, "sleep", grace):
            code, out = self.run_it()
        self.assertEqual(code, 0, out)
        self.assertEqual(lines(self.texts()[0])[-1], late)
        self.assert_moved_once()

    def test_writers_on_both_files_during_the_swap_back(self):
        self.make()
        first, second = "COORDINATION one (into the old file)", "COORDINATION two (into the swapped-in file)"

        def writer(call):
            if call in (1, 2):  # the swap, then the swap back
                with open(self.src, "a") as f:
                    f.write((first if call == 1 else second) + "\n")
        with self.wrap_exchange(writer):
            code, _ = self.run_it()
        self.assertEqual(code, 0)
        source = lines(self.texts()[0])
        self.assertEqual(source.count(first), 1)
        self.assertEqual(source.count(second), 1)
        self.assert_moved_once()

    def test_a_file_that_keeps_changing_loses_nothing_and_a_rerun_finishes(self):
        self.make()
        added = []

        def writer(call):
            added.append(f"COORDINATION {call}")
            with open(self.src, "a") as f:
                f.write(added[-1] + "\n")
        with self.wrap_exchange(writer):
            code, out = self.run_it()
        self.assertEqual(code, 1)
        self.assertIn("nothing removed", out)
        source = lines(self.texts()[0])
        self.assertTrue(set(lines(SAMPLE)) | set(added) <= set(source))
        code, _ = self.run_it()
        self.assertEqual(code, 0)
        self.assert_moved_once()

    def test_a_failed_swap_changes_nothing_and_a_rerun_finishes(self):
        self.make()
        before = self.texts()[0]

        def broken(a, b):
            raise OSError(45, "Operation not supported", str(b))
        with mock.patch.object(cq_archive, "exchange", broken):
            code, out = self.run_it()
        self.assertEqual((code, self.texts()[0]), (1, before))
        self.assertEqual(list(self.dir.glob(".ceo-questions.md.cq_archive-*")), [])
        self.run_it()
        self.assert_moved_once()

    def test_an_archive_rewritten_during_the_swap_gets_its_lines_again(self):
        self.make()
        real_swap = cq_archive.swap_in

        def swap_in(*args):
            self.arc.write_text(OLD_ARCHIVE)  # a writer's Edit, from a read before the append
            return real_swap(*args)
        with mock.patch.object(cq_archive, "swap_in", swap_in):
            code, out = self.run_it()
        self.assertEqual(code, 0)
        self.assertIn("appended them again", out)
        self.assert_moved_once()


if __name__ == "__main__":
    unittest.main()
