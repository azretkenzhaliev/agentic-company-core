"""Tests for scripts/capacity_scan.py.

Every directive and transcript is made up in a temporary folder, and the Mac's readings are faked: nothing here reads
a real session log, and no test prints a transcript's text."""

import contextlib
import importlib.util
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import unittest
from collections import namedtuple
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

import capacity_scan as scan  # noqa: E402
import company_config  # noqa: E402

DESK_NAMES = (scan.DESK_LOG, scan.DESK_JOB)  # before setUpModule patches the log away
DESK_JOB_LOADED = scan.desk_job_loaded  # and the read job

TODAY = date(2026, 1, 7)
NOW = 1_800_000_000.0
NOON = datetime(2026, 1, 7, 12, 0, tzinfo=timezone.utc).timestamp()  # TODAY's noon, UTC (the Reopened tests)
CANARY = "CANARY-the-text-of-an-order"
README = """# Directives

| Id | Title | Status | Received |
|---|---|---|---|
| [D-20251212-system](D-20251212-system.md) | Build it | in-progress | 2025-12-12 |
| [D-20251216-old](D-20251216-old.md) | Old | done (2025-12-16) | 2025-12-16 |
| [D-20251217-gone](D-20251217-gone.md) | Gone | cancelled | 2025-12-17 |
| [D-20251218-held](D-20251218-held.md) | Held | blocked (on the Board) | 2025-12-18 |
| [D-20251219-new](D-20251219-new.md) | A | b | open | 2025-12-19 |
"""
Usage = namedtuple("Usage", "total used free")
EVENING = datetime(2026, 1, 8, 18, 30, tzinfo=timezone.utc).timestamp()  # 00:30 on 2026-01-09 in Dhaka
MIDNIGHT = datetime(2026, 1, 9, 0, 5, tzinfo=timezone.utc).timestamp()


@contextlib.contextmanager
def ahead_of_utc():
    """The Mac's zone, UTC+6, so a local date runs ahead of the logs' UTC one from 18:00Z."""
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


def status_log(*events):
    rows = "".join(f"| 2026-01-0{n + 1} | ceo | {event} |\n" for n, event in enumerate(events))
    return f"## Status log\n\n| Date | Who | Event |\n|---|---|---|\n{rows}\n## Open questions for the Board\n"


def started(out):
    """The full scan's exit code for what it printed to out: 1 when "Start now" lists anything, else 0. Read after scan.main returns, as assertEqual's second argument."""
    return 0 if 'Start now (ceo.md, "Capacity"): none\n' in out.getvalue() else 1


def setUpModule():
    """No test reads this machine's company.json, the live KB's backlog pages, the live products' questions or the
    desk's live log, or asks launchd: the Board's time is six hours ahead of UTC, the board desk and its emails are on,
    scan.KNOWLEDGE and scan.WORKSPACES are empty folders, scan.DESK_LOG a missing file and the desk's read job unloaded,
    unless a test sets its own."""
    config = {**company_config.DEFAULTS, "integrations": {"board_desk": {}}}
    patch = mock.patch.object(company_config, "load", return_value=config)
    patch.start()
    unittest.addModuleCleanup(patch.stop)
    empty = tempfile.TemporaryDirectory()
    unittest.addModuleCleanup(empty.cleanup)
    for name, value in (("KNOWLEDGE", Path(empty.name) / "knowledge"), ("WORKSPACES", Path(empty.name) / "workspaces"),
                        ("DESK_LOG", Path(empty.name) / "board-desk.log"), ("desk_job_loaded", lambda: False),
                        ("BOARD_TZ", timezone(timedelta(hours=6), "Dhaka")), ("EMAIL_FROM", utc("2026-01-19T17:00Z")),
                        ("BOARD_DESK", {}), ("CONFIG_FAULT", "")):
        patch = mock.patch.object(scan, name, value)
        patch.start()
        unittest.addModuleCleanup(patch.stop)


BACKLOG_PAGE = """---
title: "Acme backlog"
owner: cto
status: {status}
updated: 2026-01-14
related: [../../company/wall-map.md]
backlog: {flag}
---

# The backlog

| Lane | Item | Status | Waits | Order |
|---|---|---|---|---|
| A | Another table's row | not started | none | – |

{header}
|---|---|---|---|---|---|---|
| 17 | The nightly import | done (PR 7) | M | two-way | none | – |
| 18 | **Attachments** ([DD-914](../dd/DD-914.md)), with a \\| pipe | not started | M | two-way | none | – |
| 19 | A shorter delete prompt | partly built | S | b3 | b3, the Board's yes on lowering protection | – |
| 20 | Color picker | in progress | S | two-way | 2026-01-01, the replay's end | D-20251219-new/4 |
| 21 | The read-back | not started | S | two-way | 2026-01-09, after the deploy | – |
| 22 | Site search | in progress | M | two-way | none | D-20251219-new/3 |
"""
HEADER = "| # | Item | Status | Size | Door | Waits | Order |"
RM_911 = "knowledge/engineering/roadmaps/RM-911-acme-backlog.md"


class Directives(unittest.TestCase):
    def test_open_rows_only(self):
        self.assertEqual(scan.open_directives(README),
                         ["D-20251212-system", "D-20251218-held", "D-20251219-new"])

    def test_latest_next_row_wins(self):
        text = status_log("Filed", "NEXT: write the design; waits: b4 the OAuth scope", "Ordered /2",
                          "NEXT: land PR 2; waits: D-20251212-system/2")
        self.assertEqual(scan.next_row(text), ("2026-01-04", "land PR 2", "D-20251212-system/2"))

    def test_no_next_row(self):
        self.assertIsNone(scan.next_row(status_log("Filed", "Ordered /1: NEXT: is in the text, not the start")))

    def test_row_without_waits(self):
        self.assertEqual(scan.next_row(status_log("NEXT: curate the note")), ("2026-01-01", "curate the note", ""))


class Classify(unittest.TestCase):
    D = "D-20251212-system"

    def state(self, waits, running=frozenset(), open_ids=()):
        return scan.classify(self.D, ("2026-01-07", "step", waits), set(running), TODAY, open_ids)

    def test_running_only_without_a_next_row(self):
        self.assertEqual(scan.classify(self.D, None, {(self.D, "3")}, TODAY), "RUNNING")
        self.assertEqual(self.state("b1 the post", {(self.D, "3")}), "BOARD")

    def test_a_running_order_hides_no_idle_step(self):
        self.assertEqual(self.state("none", {(self.D, "3")}), "IDLE")
        self.assertEqual(self.state("/3 (the CTO's report)", {(self.D, "3")}), "WAITS")
        self.assertEqual(self.state("/4", {(self.D, "3")}), "IDLE")

    def test_no_next(self):
        self.assertEqual(scan.classify(self.D, None, {("D-20251219-new", "1")}, TODAY), "NO NEXT")

    def test_board(self):
        self.assertEqual(self.state("b4 the OAuth scope"), "BOARD")
        self.assertEqual(self.state("b1, b9: the post and the hook"), "BOARD")

    def test_marketing_waits_on_the_board_s_order(self):
        """`board-order`: work that starts only on the Board's order."""
        for waits in ("board-order, the Board's order for W04", "board-order", "b7, the Board's word (board-order)",
                      "/7 (W03's batch), then board-order", "D-20251219-new/7; board-order the next week"):
            self.assertEqual(self.state(waits), "BOARD", waits)
            self.assertIsNone(scan.ignored_door("BOARD", ("2026-01-07", "step", waits)), waits)
        self.assertEqual(self.state("/7, then board-order", {(self.D, "7")}), "WAITS")
        self.assertEqual(self.state("the Board's order (board-order)"), "WAITS")  # a reason: still not flagged
        self.assertEqual(self.state("board-orders"), "WAITS")
        for waits in ("none (board-order doesn't hold: the Board ordered W04)", "/7 and board-order"):
            state = self.state(waits)
            self.assertEqual(state, "IDLE", waits)
            self.assertEqual(scan.ignored_door(state, ("2026-01-07", "step", waits)),
                             None if waits.startswith("none") else "board-order", waits)

    def test_a_door_counts_only_where_the_wait_starts(self):
        self.assertEqual(self.state("none (see b2)"), "IDLE")
        self.assertEqual(self.state("None: the b9 yes came 2026-01-07"), "IDLE")
        self.assertEqual(self.state("the Board's b9 yes"), "WAITS")  # a reason, not a door
        self.assertEqual(self.state("b10 isn't a door"), "WAITS")

    def test_idle(self):
        for waits in ("none", "None: start it", ""):
            self.assertEqual(self.state(waits), "IDLE", waits)

    def test_waits_on_an_order(self):
        other = ("D-20251219-new", "4")
        self.assertEqual(self.state("D-20251219-new/4", {other}), "WAITS")
        self.assertEqual(self.state("D-20251219-new/4"), "IDLE")  # its report is back: the step is free
        self.assertEqual(self.state("/2 (the CTO's report)"), "IDLE")

    def test_short_order_id_is_this_directives(self):
        self.assertEqual(scan.classify(self.D, ("x", "y", "/2 to report"), {("D-20251219-new", "2")}, TODAY), "IDLE")

    def test_a_short_order_id_counts_only_at_the_start(self):
        self.assertEqual(self.state("the CTO's /3 report", {(self.D, "3")}), "WAITS")  # a reason
        self.assertEqual(self.state("the CTO's /3 report"), "WAITS")

    def test_a_door_after_an_order_counts_once_the_order_is_done(self):
        other = ("D-20251219-new", "4")
        self.assertEqual(self.state("D-20251219-new/4, then b2", {other}), "WAITS")
        self.assertEqual(self.state("D-20251219-new/4, then b2"), "BOARD")
        self.assertEqual(self.state("/4, then b2"), "BOARD")
        self.assertEqual(self.state("D-20260101-b2-storage/4"), "IDLE")  # b2 in an id is no door

    def test_a_door_after_an_order_counts_only_after_a_separator(self):
        """`, `, `; ` or `then ` before it: prose naming bucket b2 is no door."""
        for waits in ("/2 then b2 the bucket", "D-20251219-new/2 then b2 the bucket", "/2; b9 the hook", "/2, b4 the scope"):
            self.assertEqual(self.state(waits), "BOARD", waits)
        for waits in ("/2, see bucket b2 for the bucket", "D-20251219-new/2, see bucket b2 for the bucket",
                      "/2 to strengthen b2"):  # then inside a word
            self.assertEqual(self.state(waits), "IDLE", waits)
        self.assertEqual(self.state("/2 then b2 the bucket", {(self.D, "2")}), "WAITS")

    def test_a_door_the_scan_does_not_count_gets_a_warning(self):
        """Each of these forms still reads IDLE once /2 is done, and names its door, so the scan prints a warning under
        the row."""
        for waits in ("/2 and b2", "/2 (b2)", "/2: b2", "/2 -> b2", "/2 + b2", "/2, then the Board's b2",
                      "D-20251219-new/2 and b2 the bucket", "/2, see bucket b2 for the bucket", "/2 to strengthen b2.",
                      "2026-01-01 and b2", "D-20251216-old (its report), then b2"):
            state = self.state(waits)
            self.assertEqual(state, "IDLE", waits)
            self.assertEqual(scan.ignored_door(state, ("2026-01-07", "step", waits)), "b2", waits)
        for waits, running, state in (("/2 and b2", {(self.D, "2")}, "WAITS"), ("/2, then b2", set(), "BOARD"),
                                      ("b2 the bucket", set(), "BOARD"), ("the Board's b9 yes", set(), "WAITS"),
                                      ("none (see b2)", set(), "IDLE"), ("None: the b9 yes came 2026-01-07", set(), "IDLE"),
                                      ("D-20260101-b2-storage/4", set(), "IDLE"), ("/2 (b10, web2, b2b)", set(), "IDLE"),
                                      ("/2", set(), "IDLE"), ("", set(), "IDLE")):
            self.assertEqual(self.state(waits, running), state, waits)
            self.assertIsNone(scan.ignored_door(state, ("2026-01-07", "step", waits)), waits)

    def test_the_ux_expert_row_waits_on_the_cto_then_the_board(self):
        """The bare /5 is part of a reason, the wait is the CTO's /117, and b6 after it."""
        row = scan.next_row("| 2026-01-07 | ceo | NEXT: the Board picks the look; waits: the ux-expert's "
                            "/5 re-check of C, D and E in D-20251215-first-launch/117, then b6 |")
        ux, cto = "D-20260106-round-tables", ("D-20251215-first-launch", "117")
        self.assertEqual(scan.classify(ux, row, {cto}, TODAY), "WAITS")
        self.assertEqual(scan.classify(ux, row, {(ux, "5")}, TODAY), "BOARD")
        self.assertEqual(scan.classify(ux, row, set(), TODAY), "BOARD")

    def test_waits_on_a_date(self):
        self.assertEqual(self.state("2026-01-09, the reel's 48 hours"), "WAITS")
        self.assertEqual(self.state("2026-01-07"), "IDLE")
        self.assertEqual(self.state("2026-01-01"), "IDLE")
        self.assertEqual(self.state("2026-01-12 (after /2 reports)"), "WAITS")  # the date is the wait
        self.assertEqual(self.state("2026-01-07 (after /2 reports)", {(self.D, "2")}), "IDLE")  # the date has come: /2 in its reason waits no more
        self.assertEqual(self.state("2026-02-31"), "WAITS")  # no such day: a reason, and the scan doesn't crash

    def test_a_date_with_a_time_is_compared_to_the_minute_in_utc(self):
        """`waits: 2026-01-07 01:40Z` hasn't come at 00:05Z that day."""
        before, after = (datetime(2026, 1, 7, 1, 39, 59, tzinfo=timezone.utc).timestamp(),
                         datetime(2026, 1, 7, 1, 40, tzinfo=timezone.utc).timestamp())

        def state(waits, now):
            return scan.classify(self.D, ("2026-01-07", "step", waits), set(), TODAY, (), now)

        for waits in ("2026-01-07 01:40Z, the replay's end", "2026-01-07 01:40:45Z"):
            self.assertEqual(state(waits, before), "WAITS", waits)
            self.assertEqual(state(waits, after), "IDLE", waits)
        self.assertEqual(state("2026-01-07 01:40Z, then b2", before), "WAITS")
        self.assertEqual(state("2026-01-07 01:40Z, then b2", after), "BOARD")
        self.assertEqual(state("2026-01-08 00:00Z", after), "WAITS")  # another day: by the date, as before
        self.assertEqual(state("2026-01-06 23:59Z", before), "IDLE")
        self.assertEqual(state("2026-01-07", before), "IDLE")  # a bare date keeps today's rule
        self.assertEqual(state("2026-01-07 01:40 (Dhaka)", before), "IDLE")  # no Z: no UTC time, so a bare date
        self.assertEqual(state("2026-01-07 99:99Z", before), "IDLE")  # no such time: a bare date
        self.assertEqual(self.state("2026-01-07 23:59Z"), "IDLE")  # no time given to classify: the day only

    def test_an_iso_time_reads_as_the_spaced_one(self):
        """`waits: 2026-01-15T06:30Z (...)` is a date, not a reason."""
        before, after = (datetime(2026, 1, 7, 1, 39, 59, tzinfo=timezone.utc).timestamp(),
                         datetime(2026, 1, 7, 1, 40, tzinfo=timezone.utc).timestamp())

        def state(waits, now):
            return scan.classify(self.D, ("2026-01-07", "step", waits), set(), TODAY, (), now)

        for tail in ("01:40Z (round 1's data)", "01:40:45Z", "01:40Z, then b2", "01:40 (Dhaka)", "99:99Z"):
            spaced, iso = f"2026-01-07 {tail}", f"2026-01-07T{tail}"
            for now in (before, after):
                self.assertEqual(state(iso, now), state(spaced, now), (iso, now))
            for when in ("2026-01-09", "2026-01-01"):  # another day: by the date
                self.assertEqual(state(iso.replace("2026-01-07", when), before),
                                 state(spaced.replace("2026-01-07", when), before), (iso, when))
        self.assertEqual(state("2026-01-07T01:40Z (round 1's data)", before), "WAITS")
        self.assertEqual(state("2026-01-07T01:40Z (round 1's data)", after), "IDLE")
        self.assertEqual(state("2026-01-07T01:40Z, then b2", after), "BOARD")  # a door after it still counts
        for waits in ("2026-01-07T01:40Z (round 1's data)", "2026-01-07 01:40Z (round 1's data)"):
            self.assertIsNone(scan.data_wait("WAITS", ("2026-01-07", "step", waits)), waits)  # a date first
            self.assertEqual(scan.classify(None, ("", "item", waits), set(), TODAY, (), before), "WAITS")  # backlog's
        self.assertEqual(scan.data_wait("WAITS", ("2026-01-07", "step", "round 1's data, 2026-01-07T01:40Z")), "data")
        self.assertEqual(self.state("the replay (ends 2026-01-07T01:40Z)"), "WAITS")  # a date in a reason

    def test_a_door_after_a_date_counts_once_the_date_has_come(self):
        """A week boundary with no Board order starts nothing."""
        for waits in ("2026-01-01, then b2", "2026-01-07; b9 the hook", "2026-01-02, then board-order (W01's plan)"):
            self.assertEqual(self.state(waits), "BOARD", waits)
            self.assertIsNone(scan.ignored_door("BOARD", ("2026-01-07", "step", waits)), waits)
        self.assertEqual(self.state("2026-01-09, then board-order"), "WAITS")  # the date still to come
        self.assertEqual(self.state("2026-01-01, see bucket b2"), "IDLE")  # prose, as after an order

    def test_a_date_in_a_reason_is_only_a_reason(self):
        self.assertEqual(self.state("the Board's restart (asked 2026-01-01)"), "WAITS")
        self.assertEqual(self.state("the reel's numbers, \"posted 2026-01-01\""), "WAITS")

    def test_waits_on_another_directive_while_it_is_open(self):
        other = "D-20260106-page-colors"
        self.assertEqual(self.state(f"{other} (its trial page)", open_ids=[self.D, other]), "WAITS")
        self.assertEqual(self.state(other, open_ids=[self.D, other]), "WAITS")
        self.assertEqual(self.state(f"{other} (its trial page)", open_ids=[self.D]), "IDLE")  # done: the step is free
        self.assertEqual(self.state(f"{other}/3", {(other, "3")}, open_ids=[self.D, other]), "WAITS")  # an order
        self.assertEqual(self.state(f"{other}/3", open_ids=[self.D, other]), "IDLE")
        self.assertEqual(self.state(f"the trial page ({other})", open_ids=[self.D]), "WAITS")  # a reason

    def test_other_reasons_wait(self):
        self.assertEqual(self.state("the landing lock (PR 4 lands first)"), "WAITS")

    def test_a_running_critic_counts_for_any_order_of_its_directive(self):
        """A critic's prompt is the directive's path, so it has no order number."""
        critic = {(self.D, None)}
        for waits in ("/4", f"{self.D}/1, {self.D}/4", "/5 (the critic's verdict)"):
            self.assertEqual(self.state(waits, critic), "WAITS", waits)
            self.assertEqual(self.state(waits), "IDLE", waits)
        self.assertEqual(self.state("/4, then b1", critic), "WAITS")
        self.assertEqual(self.state("/4, then b1"), "BOARD")
        self.assertEqual(self.state("none", critic), "IDLE")  # the row is judged on its own
        self.assertEqual(self.state("/4", {("D-20251219-new", None)}), "IDLE")  # a critic on another directive
        self.assertEqual(scan.classify(self.D, None, critic, TODAY), "RUNNING")
        self.assertEqual(scan.format_row(self.D, "WAITS", [(None, "critic", 1), ("12", "cto", 1), ("3", "cmo", 1)], None),
                         f"{self.D}  WAITS | agents: /3 cmo, /12 cto, critic (path)")

    def test_a_wait_on_data_with_nothing_first_is_flagged(self):
        """Nothing wakes such a row."""
        for waits, word in (("data that doesn't exist yet (round 1's main run, D-20251215-first-launch; the replay "
                             "ends about 2026-01-10 08:30Z)", "data"), ("results", "results"), ("the run", "run"),
                            ("the reel's numbers, \"posted 2026-01-01\"", "numbers"), ("round 1's result", "result"),
                            ("data that doesn't exist yet (a day with merges)", "data")):
            state = self.state(waits)
            self.assertEqual(state, "WAITS", waits)
            self.assertEqual(scan.data_wait(state, ("2026-01-07", "step", waits)), word, waits)
        for waits, running in (("2026-01-12, the run's data", set()), ("2026-01-10 08:30Z, round 1's data", set()),
                               ("/3 (its results)", {(self.D, "3")}), ("D-20251219-new/3's data", {("D-20251219-new", "3")}),
                               ("the landing lock (PR 4 lands first)", set()), ("the first Short (planned W03)", set()),
                               ("b1, the run's go", set()), ("none (the data is in)", set()), ("the runner's rerun", set())):
            state = self.state(waits, running, open_ids=[self.D])
            self.assertIsNone(scan.data_wait(state, ("2026-01-07", "step", waits)), (waits, state))
        waits = "D-20260106-page-colors (its data)"
        state = self.state(waits, open_ids=[self.D, "D-20260106-page-colors"])
        self.assertEqual(state, "WAITS")
        self.assertIsNone(scan.data_wait(state, ("2026-01-07", "step", waits)))


class StrayNext(unittest.TestCase):
    """A row below the latest NEXT row that holds `NEXT:` mid-row: the row it left
    behind is stale."""

    def test_a_mid_row_next_below_the_latest_is_found(self):
        text = status_log("NEXT: round 1's start; waits: b1, the Board's top-ups", "Filed",
                          "Round 1 ordered now. NEXT: round 1's results; waits: the main run")
        self.assertEqual(scan.next_row(text)[0], "2026-01-01")  # the scan still reads the old row
        self.assertEqual(scan.stray_next(text), "2026-01-03")

    def test_one_above_the_latest_next_row_is_not(self):
        self.assertIsNone(scan.stray_next(status_log("Decided: x. NEXT: a; waits: none", "NEXT: b; waits: none")))

    def test_mentions_in_quotes_or_backticks_are_not(self):
        text = status_log("NEXT: a; waits: none", "Fix: the scan warns on a row holding \"NEXT:\" mid-row",
                          "The latest `NEXT:` row decides; 'NEXT:' too", "A word: SUBNEXT: no")
        self.assertIsNone(scan.stray_next(text))

    def test_with_no_next_row_any_mid_row_next_counts(self):
        self.assertEqual(scan.stray_next(status_log("Filed", "Ordered /1. NEXT: land it; waits: /1")), "2026-01-02")
        self.assertIsNone(scan.stray_next(status_log("Filed", "Ordered /1")))

    def test_a_mention_inside_a_quoted_span_is_not(self):
        """A quote or backtick a few words away, not only next to it."""
        text = status_log("NEXT: a; waits: none", 'The Board: "the old NEXT: step stays" (2026-01-01)',
                          "Fixed `scan --next NEXT: x` and “NEXT: y, it said”")
        self.assertIsNone(scan.stray_next(text))
        self.assertEqual(scan.stray_next(text + '| 2026-01-09 | ceo | "Quoted" then NEXT: b; waits: none "too" |\n'),
                         "2026-01-09")

    def test_only_a_dated_row_counts(self):
        """Prose outside the status log's rows is the directive's text, not a step."""
        self.assertIsNone(scan.stray_next("# D\n\nThe plan: build it. NEXT: ship it.\n\n" + status_log("Filed")))
        self.assertEqual(scan.stray_next("Intro. NEXT: x\n" + status_log("Filed", "Did y. NEXT: z")), "2026-01-02")


class OrderHeader(unittest.TestCase):
    def parse(self, text):
        found = scan.ORDER.search(text)
        return found.groups() if found else None

    def test_plain(self):
        self.assertEqual(self.parse(f"ORDER D-20251215-first-launch/113   from: ceo   to: cto\n{CANARY}"),
                         ("D-20251215-first-launch", "113", "ceo", "cto"))

    def test_a_note_after_the_number(self):
        for note in ("(resumed)", "(continued)", "(resumed 2)", "(resumed, with one more item)",
                     "(RESTARTED 2026-01-11 after the Board's session restart)"):
            self.assertEqual(self.parse(f"ORDER D-20260103-quiz-lists/10 {note}   from: ceo   to: cto"),
                             ("D-20260103-quiz-lists", "10", "ceo", "cto"), note)

    def test_a_sub_id_counts_as_its_order(self):
        for header in ("ORDER D-20251215-first-launch/151.D2.T3 (restart)   from: staff-engineer   to: senior-engineer",
                       "ORDER D-20251215-first-launch/151.UX-C   from: staff-engineer   to: senior-engineer",
                       "ORDER D-20251215-first-launch/151-T4   from: staff-engineer   to: senior-engineer",
                       "ORDER D-20251215-first-launch/151/p1b   from: staff-engineer   to: senior-engineer",
                       "ORDER D-20251215-first-launch/151.T2   from: staff-engineer (DD-915 lane)   to: senior-engineer"):
            self.assertEqual(self.parse(header), ("D-20251215-first-launch", "151", "staff-engineer", "senior-engineer"),
                             header)

    def test_a_hyphen_digit_sub_id_counts_as_the_first_number(self):
        """"/15-16" is /15, never /16."""
        self.assertEqual(self.parse("ORDER D-20251212-system/15-16   from: ceo   to: platform-engineer"),
                         ("D-20251212-system", "15", "ceo", "platform-engineer"))

    def test_prose_and_other_forms_do_not_match(self):
        for text in ("ORDER D-20260103-quiz-lists/10 is in this file; read it first",
                     "ORDER D-20260103-quiz-lists/10 (resumed): see the directive",
                     "ORDER D-20251215-first-launch/4-land from cto to senior-engineer. This IS your manager's word",
                     "ORDER D-20251215-first-launch/4 from: cto, to the Senior",
                     f"ORDER D-20260103-quiz-lists/10 ({'x' * 81})   from: ceo   to: cto",
                     "ORDER D-20251219-new/2   from: maintenance session   to: cmo"):
            self.assertIsNone(self.parse(text), text)


class OrderList(unittest.TestCase):
    RESUME = ("RESUME of ORDER D-20251215-first-launch/152, ORDER D-20260111-cold-fresh-air/2, "
              "ORDER D-20260111-cold-fresh-air/5 and ORDER D-20260112-green-paper/3")

    def pairs(self, prompt):
        return sorted(order[:2] for order in scan.first_orders(prompt))

    def test_a_resume_of_four_orders_counts_all_four(self):
        four = [("D-20251215-first-launch", "152"), ("D-20260111-cold-fresh-air", "2"),
                ("D-20260111-cold-fresh-air", "5"), ("D-20260112-green-paper", "3")]
        for tail in ("   from: ceo   to: cto   (2026-01-12, after the Board's session restart)", ""):
            self.assertEqual(self.pairs(f"{self.RESUME}{tail}\n\nYou are a fresh CTO. {CANARY}"), four, tail)
            self.assertEqual(self.pairs(f"Read the log first.\n{self.RESUME}{tail}\n{CANARY}"), four, tail)

    def test_a_header_listing_several(self):
        for header in ("ORDER D-20251219-new/1, ORDER D-20251219-new/2 and ORDER D-20251218-held/3   from: ceo   to: cto",
                       "ORDER D-20251219-new/1, ORDER D-20251219-new/2, and ORDER D-20251218-held/3 (resumed)   from: ceo"
                       "   to: cto",
                       "  ORDER D-20251219-new/1.T2 and ORDER D-20251219-new/2-land, ORDER D-20251218-held/3   from: cto"
                       "   to: senior-engineer"):
            self.assertEqual(self.pairs(f"{header}\n{CANARY}"), [("D-20251218-held", "3"), ("D-20251219-new", "1"),
                                                                ("D-20251219-new", "2")], header)

    def test_a_single_order_prompt_reads_as_before(self):
        for prompt in ("ORDER D-20251219-new/1   from: ceo   to: cto\nRESUME of ORDER D-20251219-new/2 and "
                       "ORDER D-20251219-new/3",  # the list isn't the first such line
                       "RESUME of ORDER D-20251219-new/1   from: ceo   to: cto",
                       "RESUME of ORDER D-20251219-new/1",
                       "ORDER D-20251219-new/1 and ORDER D-20251219-new/2 are in this file; read them",  # no header
                       # a RESUME list followed by prose
                       "RESUME of ORDER D-20251219-new/1 and ORDER D-20251219-new/2 is done; your task is T4",
                       "The RESUME of ORDER D-20251219-new/1 and ORDER D-20251219-new/2, below",  # not a line's start
                       "ORDER D-20251219-new/1 (resumed)   from: ceo   to: cto"):
            header = scan.ORDER.search(prompt)
            self.assertEqual(scan.first_orders(prompt), [header.groups()] if header else [], prompt)


class Transcripts(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.folder = self.root / "session-1" / "subagents"
        self.folder.mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def agent(self, agent_id, role, prompt, *, parent=None, finished=False, age=60, folder=None, records=(),
              stopped=False):
        folder = folder or self.folder
        meta = {"agentType": role, "description": "x"}
        if parent:
            meta["parentAgentId"] = parent
        if finished:
            meta["finished"] = True
        if stopped:
            meta["stoppedByUser"] = True
        (folder / f"agent-{agent_id}.meta.json").write_text(json.dumps(meta))
        log = folder / f"agent-{agent_id}.jsonl"
        lines = [{"type": "attachment"}, {"type": "user", "message": {"role": "user", "content": prompt}}, *records]
        log.write_text("".join(json.dumps(line) + "\n" for line in lines))
        os.utime(log, (NOW - age, NOW - age))

    @staticmethod
    def background(task_id):
        """The tool result of a command started in the background, as Claude Code records it."""
        return {"type": "user", "message": {"role": "user", "content": [
                    {"type": "tool_result", "tool_use_id": "toolu_1", "content": f"Command running in background with ID: {task_id}"}]},
                "toolUseResult": {"stdout": "", "stderr": "", "interrupted": False, "backgroundTaskId": task_id}}

    @staticmethod
    def notified(task_id, as_attachment=False):
        """A task notification: a user prompt, or a queued_command attachment."""
        text = f"<task-notification>\n<task-id>{task_id}</task-id>\n<status>completed</status>\n</task-notification>"
        if as_attachment:
            return {"type": "attachment", "attachment": {"type": "queued_command", "prompt": text}}
        return {"type": "user", "message": {"role": "user", "content": text}}

    def test_running_agents_and_their_orders(self):
        self.agent("c1", "cto", f"ORDER D-20251215-first-launch/113   from: ceo   to: cto\n{CANARY}")
        self.agent("s1", "senior-engineer", f"Task T4 in a worktree. {CANARY}", parent="c1")
        self.agent("r1", "code-reviewer", [{"type": "text", "text": f"Review {CANARY}"}], parent="s1", age=45 * 60)
        self.agent("p1", "platform-engineer",
                   [{"type": "text", "text": "ORDER D-20260107-bus-stops/1   from: ceo   to: platform-engineer"}])
        self.agent("f1", "analyst", "ORDER D-20251219-new/2   from: ceo   to: analyst", finished=True)
        self.agent("o1", "analyst", "ORDER D-20251219-new/3   from: ceo   to: analyst", age=3 * 3600)
        self.agent("n1", "ux-expert", "An audit with no order", age=-5)  # written a moment "after" now: 0 minutes
        found = sorted(scan.agents(self.root, NOW), key=lambda a: a[2])
        self.assertEqual(found, [
            ("D-20251215-first-launch", "113", "code-reviewer", 45),
            ("D-20251215-first-launch", "113", "cto", 1),
            ("D-20260107-bus-stops", "1", "platform-engineer", 1),
            ("D-20251215-first-launch", "113", "senior-engineer", 1),
            (None, None, "ux-expert", 0),
        ])

    def test_a_child_outlives_its_parent(self):
        self.agent("c1", "cto", "ORDER D-20251215-first-launch/113   from: ceo   to: cto", finished=True, age=9 * 3600)
        self.agent("s1", "senior-engineer", "Task T4", parent="c1")
        self.assertEqual(scan.agents(self.root, NOW), [("D-20251215-first-launch", "113", "senior-engineer", 1)])

    def test_a_critic_takes_the_directive_whose_path_its_prompt_holds(self):
        self.agent("k1", "critic", f"knowledge/board/directives/D-20251219-new.md {CANARY}")
        self.agent("k2", "critic", [{"type": "text", "text": "Check knowledge/board/directives/D-20251212-system.md"}])
        self.agent("k3", "critic", "A design gist with no directive path")
        self.agent("k4", "critic", "ORDER D-20251218-held/9   from: ceo   to: critic (the drift audit; "
                                   "knowledge/board/directives/D-20251219-new.md)")
        self.agent("k5", "analyst", "Read knowledge/board/directives/D-20251219-new.md")  # only a critic's prompt is a path
        self.agent("k6", "critic", "knowledge/board/directives/D-20251219-new.md", finished=True)
        self.assertEqual(sorted(scan.agents(self.root, NOW), key=str), sorted([
            ("D-20251219-new", None, "critic", 1), ("D-20251212-system", None, "critic", 1),
            (None, None, "critic", 1), ("D-20251218-held", "9", "critic", 1), (None, None, "analyst", 1)], key=str))

    GATE = 'CEO gate review (ceo.md "System changes", step 4) of a system diff.'

    def test_a_ceo_gate_review_runs_the_one_order_its_body_names(self):
        """The CEO's gate reviewer, its prompt naming the order only in its body."""
        head = self.GATE
        self.agent("g1", "code-reviewer", f"{head} {CANARY}\nThe order (ORDER D-20251212-system/46, in the "
                                          f"directive's status log): {CANARY}")
        self.agent("g2", "code-reviewer", [{"type": "text", "text": "\nCEO gate review (ceo.md, \"System changes\", "
                                                                     "step 4) of ORDER D-20251219-new/6.T2."}])
        self.agent("g3", "code-reviewer", f"{head}\nThe order: ORDER D-20251219-new/7; ORDER D-20251219-new/7.T2 is its "
                                          "task.")  # one order, named twice
        self.agent("g4", "code-reviewer", f"{head} Unlike \"ORDER D-20251218-held/3\" and `ORDER D-20251218-held/4`, "
                                          "the order is ORDER D-20251219-new/8.")
        # never one: two orders named (the first could be the one in passing), an order only
        # quoted or backticked, in lower case or bare, a prompt that doesn't start so
        self.agent("n8", "code-reviewer", f"{head}\nThe order: ORDER D-20251219-new/12, as ORDER D-20251218-held/2 was.")
        self.agent("n9", "code-reviewer", f"{head} Like ORDER D-20251218-held/13 before it, the order is "
                                          "ORDER D-20251219-new/14.")
        self.agent("n1", "code-reviewer", f"{head} Round 2: the order's text is the row starting "
                                          "\"ORDER D-20251218-held/44\".")
        self.agent("n2", "code-reviewer", f"{head} The order is “ORDER D-20251218-held/45” or `ORDER D-20251218-held/46`.")
        self.agent("n3", "code-reviewer", f"{head} Of order D-20251218-held/39; read the file for its ORDER /43 text.")
        self.agent("n4", "code-reviewer", "Gate review for the CEO (ceo.md, step 4) of ORDER D-20251218-held/38.")
        self.agent("n5", "code-reviewer", "Read this first. CEO gate review of ORDER D-20251218-held/5.")
        self.agent("n6", "senior-engineer", "Task T4; see ORDER D-20251218-held/6 for context.")
        self.agent("n7", "code-reviewer", f"{head} REORDER D-20251218-held/10 and SUBORDER D-20251218-held/11.")
        # not the main session's: its parent's order; a header the scan reads still wins
        self.agent("p1", "platform-engineer", "ORDER D-20251219-new/3   from: CEO   to: platform-engineer")
        self.agent("r1", "code-reviewer", f"{head} ORDER D-20251218-held/7", parent="p1")
        self.agent("h1", "code-reviewer", "CEO gate review of ORDER D-20251218-held/8.\n"
                                          "ORDER D-20251219-new/2 (gate review)   from: ceo   to: code-reviewer")
        self.agent("f1", "code-reviewer", f"{head} ORDER D-20251219-new/9", finished=True)
        unread = []
        self.assertEqual(sorted(((d, n, role) for d, n, role, _ in scan.agents(self.root, NOW, unread)), key=str),
                         sorted([("D-20251212-system", "46", "code-reviewer"),
                                 ("D-20251219-new", "6", "code-reviewer"), ("D-20251219-new", "7", "code-reviewer"),
                                 ("D-20251219-new", "8", "code-reviewer"), *[(None, None, "code-reviewer")] * 8,
                                 (None, None, "senior-engineer"), ("D-20251219-new", "3", "platform-engineer"),
                                 ("D-20251219-new", "3", "code-reviewer"), ("D-20251219-new", "2", "code-reviewer")],
                                key=str))
        self.assertEqual(unread, [])
        self.assertEqual(scan.gate_order(f"{head} ORDER D-20251219-new/9"), [("D-20251219-new", "9", None, None)])
        self.assertEqual(scan.gate_order(f"{head} ORDER D-20251219-new/9 and ORDER D-20251219-new/10"), [])
        # the docstrings' quoting rule: only double quotes and
        # backticks on one line hide an order; single quotes, a fenced block and a quote across lines don't
        for named in ("'ORDER D-20251219-new/9'", "```\nORDER D-20251219-new/9\n```", '"ORDER D-20251219-new/9\nso"'):
            self.assertEqual(scan.gate_order(f"{head} {named}"), [("D-20251219-new", "9", None, None)])

    def test_a_directive_with_only_a_gate_reviewer_running_waits(self):
        """WAITS, not IDLE, and the row lists the reviewer."""
        directives = self.root / "directives"
        directives.mkdir()
        (directives / "README.md").write_text(README)
        (directives / "D-20251212-system.md").write_text(status_log("NEXT: land /46; waits: /46 (gate review)"))
        (directives / "D-20251218-held.md").write_text(status_log("NEXT: land /44; waits: /44 (gate review)"))
        (directives / "D-20251219-new.md").write_text(status_log("NEXT: curate it; waits: none"))
        self.agent("g1", "code-reviewer", f"{self.GATE} {CANARY}\nThe order (ORDER D-20251212-system/46, in "
                                          f"the directive's status log): {CANARY}")
        self.agent("n1", "code-reviewer", f"{self.GATE} The order's text is the row starting \"ORDER D-20251218-held/44\".")
        self.agent("n2", "code-reviewer", f"{self.GATE} Of ORDER D-20251219-new/3.")  # the row waits on none: IDLE
        out = io.StringIO()
        with mock.patch.object(scan, "DIRECTIVES", directives), \
                mock.patch.object(scan, "projects_root", return_value=self.root), \
                mock.patch.object(scan, "mac_room", return_value=(True, "Mac: room: yes")), \
                mock.patch.object(scan.time, "time", return_value=NOW), contextlib.redirect_stdout(out):
            self.assertEqual(scan.main([]), started(out))
        text = out.getvalue()
        self.assertEqual([line for line in text.splitlines() if line.startswith("D-")], [
            "D-20251212-system  WAITS | agents: /46 code-reviewer | NEXT (2026-01-01): land /46; "
            "waits: /46 (gate review)",
            "D-20251218-held  IDLE | NEXT (2026-01-01): land /44; waits: /44 (gate review)",
            "D-20251219-new  IDLE | agents: /3 code-reviewer | NEXT (2026-01-01): curate it; waits: none"])
        self.assertIn('Start now (ceo.md, "Capacity"): D-20251218-held, D-20251219-new\n', text)
        self.assertIn("Running with no ORDER id: 1 (code-reviewer)\n", text)
        self.assertNotIn("CANARY", text)
        self.assertNotIn("Warning:", text)

    def test_ceo_md_step_4_headers_list_the_gate_review_and_its_re_check(self):
        """ceo.md's step 4 starts the CEO's reviewer and each re-check with a header; read here from ceo.md, so a
        wording the scan can't read fails."""
        text = (SCRIPTS.parent / ".claude" / "agents" / "executive" / "ceo.md").read_text(encoding="utf-8")
        section = text.split("## System changes", 1)[1].split("\n## ", 1)[0]
        header = re.search(r"`(ORDER <directive>/<n> \(gate review\)[^`]*)`", section).group(1)
        note = re.search(r"a re-check: `(\([^`]*\))`", section).group(1)
        directives = self.root / "directives"
        directives.mkdir()
        (directives / "README.md").write_text(README)
        (directives / "D-20251212-system.md").write_text(status_log("NEXT: land /4; waits: /4 (gate review)"))
        (directives / "D-20251218-held.md").write_text(status_log("NEXT: land /5; waits: /5 (gate re-check)"))
        (directives / "D-20251219-new.md").write_text(status_log("NEXT: curate it; waits: none"))
        review = header.replace("<directive>/<n>", "D-20251212-system/4")
        self.agent("g1", "code-reviewer", f"{review}\n{CANARY}")
        recheck = header.replace("<directive>/<n>", "D-20251218-held/5").replace("(gate review)", note)
        self.agent("g2", "code-reviewer", f"{recheck}\nRe-check for the CEO of finding 1. {CANARY}")
        out = io.StringIO()
        with mock.patch.object(scan, "DIRECTIVES", directives), \
                mock.patch.object(scan, "projects_root", return_value=self.root), \
                mock.patch.object(scan, "mac_room", return_value=(True, "Mac: room: yes")), \
                mock.patch.object(scan.time, "time", return_value=NOW), contextlib.redirect_stdout(out):
            self.assertEqual(scan.main([]), started(out))
        text = out.getvalue()
        self.assertEqual([line for line in text.splitlines() if line.startswith("D-")], [
            "D-20251212-system  WAITS | agents: /4 code-reviewer | NEXT (2026-01-01): land /4; "
            "waits: /4 (gate review)",
            "D-20251218-held  WAITS | agents: /5 code-reviewer | NEXT (2026-01-01): land /5; waits: /5 (gate re-check)",
            "D-20251219-new  IDLE | NEXT (2026-01-01): curate it; waits: none"])
        self.assertTrue(recheck.startswith("ORDER D-20251218-held/5 (gate re-check)   from: ceo   to: code-reviewer"))
        self.assertNotIn("no ORDER id", text)
        self.assertNotIn("CANARY", text)

    def test_an_agent_waiting_on_its_own_background_work_runs(self):
        """Its meta says finished while its render runs."""
        order = "ORDER D-20260104-office-plants/3   from: ceo   to: cmo"
        bg, note = self.background, self.notified
        self.agent("w1", "cmo", order, finished=True, records=[bg("b1")])
        self.agent("w2", "cmo", order, finished=True, records=[bg("b1"), note("b1"), bg("b2")], age=50 * 60)
        self.agent("d1", "cmo", order, finished=True, records=[bg("b1"), note("b1")])
        self.agent("d2", "cmo", order, finished=True, records=[bg("b1"), bg("b2"), note("b2", True), note("b1", True)])
        self.agent("d3", "cmo", order, finished=True)
        self.agent("d4", "cmo", order, finished=True, records=[bg("b1")], stopped=True)
        self.agent("d5", "cmo", order, finished=True, records=[bg("b1")], age=3 * 3600)
        quoted = {"type": "assistant", "message": {"role": "assistant", "content": [
            {"type": "text", "text": "<task-notification><task-id>b1</task-id></task-notification>"}]}}
        self.agent("w3", "cmo", order, finished=True, records=[bg("b1"), quoted])  # its own words notify nothing
        self.assertEqual(sorted(scan.agents(self.root, NOW)), [
            ("D-20260104-office-plants", "3", "cmo", 1), ("D-20260104-office-plants", "3", "cmo", 1),
            ("D-20260104-office-plants", "3", "cmo", 50)])
        for agent_id, waiting in (("w1", True), ("w2", True), ("w3", True), ("d1", False), ("d2", False), ("d3", False)):
            self.assertEqual(scan.waiting_on_background(self.folder / f"agent-{agent_id}.jsonl"), waiting, agent_id)
        self.assertFalse(scan.waiting_on_background(self.folder / "agent-missing.jsonl"))

    def test_unreadable_files_are_skipped(self):
        (self.folder / "agent-x1.meta.json").write_text("{not json")
        (self.folder / "agent-x1.jsonl").write_text("garbage\n")
        os.utime(self.folder / "agent-x1.jsonl", (NOW, NOW))
        (self.folder / "agent-x2.meta.json").write_text("{}")  # no transcript at all
        self.agent("x3", "cto", "no order", parent="missing")
        self.assertEqual(scan.agents(self.root, NOW), [(None, None, "cto", 1)])

    def test_scan_and_print(self):
        directives = self.root / "directives"
        directives.mkdir()
        (directives / "README.md").write_text(README)
        (directives / "D-20251212-system.md").write_text(status_log("NEXT: curate it; waits: none"))
        (directives / "D-20251218-held.md").write_text(status_log("NEXT: ship it; waits: b1 the post"))
        # D-20251219-new has no file at all: NO NEXT
        self.agent("a1", "cto", f"ORDER D-20251219-new/1   from: ceo   to: cto {CANARY}")
        self.agent("a2", "analyst", "ORDER D-20251212-system/2   from: ceo   to: analyst")  # another lane
        rows = scan.scan(directives, scan.agents(self.root, NOW), TODAY)
        self.assertEqual([(d, s) for d, s, _, _ in rows], [
            ("D-20251212-system", "IDLE"), ("D-20251218-held", "BOARD"), ("D-20251219-new", "RUNNING")])
        out = io.StringIO()
        with mock.patch.object(scan, "DIRECTIVES", directives), \
                mock.patch.object(scan, "projects_root", return_value=self.root), \
                mock.patch.object(scan, "mac_room", return_value=(True, "Mac: room: yes")), \
                mock.patch.object(scan.time, "time", return_value=NOW), contextlib.redirect_stdout(out):
            self.assertEqual(scan.main([]), started(out))
        text = out.getvalue()
        self.assertIn("D-20251212-system  IDLE | agents: /2 analyst | NEXT (2026-01-01): curate it; waits: none",
                      text)
        self.assertIn("D-20251219-new  RUNNING | agents: /1 cto", text)
        self.assertIn('Start now (ceo.md, "Capacity"): D-20251212-system\n', text)
        self.assertNotIn("CANARY", text)
        self.assertNotIn("can't see them", text)
        self.assertNotIn("Warning:", text)

    def test_the_scan_warns_under_an_idle_row_that_names_a_door(self):
        directives = self.root / "directives"
        directives.mkdir()
        (directives / "README.md").write_text(README)
        (directives / "D-20251212-system.md").write_text(status_log("NEXT: land it; waits: /2 and b2"))
        (directives / "D-20251218-held.md").write_text(status_log("NEXT: ship it; waits: /3, then b1"))
        (directives / "D-20251219-new.md").write_text(status_log("NEXT: curate it; waits: none (see b2)"))
        out = io.StringIO()
        with mock.patch.object(scan, "DIRECTIVES", directives), \
                mock.patch.object(scan, "projects_root", return_value=self.root), \
                mock.patch.object(scan, "mac_room", return_value=(True, "Mac: room: yes")), \
                mock.patch.object(scan.time, "time", return_value=NOW), contextlib.redirect_stdout(out):
            self.assertEqual(scan.main([]), started(out))
        lines = out.getvalue().splitlines()
        row = lines.index("D-20251212-system  IDLE | NEXT (2026-01-01): land it; waits: /2 and b2")
        self.assertTrue(lines[row + 1].startswith(
            "Warning: D-20251212-system's NEXT row (2026-01-01) reads IDLE but names b2, "), lines[row + 1])
        self.assertEqual([line for line in lines if line.startswith("Warning:")], [lines[row + 1]])  # BOARD, none: no
        self.assertIn('Start now (ceo.md, "Capacity"): D-20251212-system, D-20251219-new', lines)

    def test_the_scan_warns_on_a_data_wait_and_a_stray_next_and_counts_a_critic(self):
        directives = self.root / "directives"
        directives.mkdir()
        (directives / "README.md").write_text(README)
        (directives / "D-20251212-system.md").write_text(status_log("NEXT: curate it; waits: results of the replay"))
        (directives / "D-20251218-held.md").write_text(status_log("NEXT: ship it; waits: b1 the post",
                                                                  "Posted it. NEXT: the next one"))
        (directives / "D-20251219-new.md").write_text(status_log("Found it; NEXT: write it up"))
        self.agent("k1", "critic", f"Check knowledge/board/directives/D-20251219-new.md {CANARY}")
        out = io.StringIO()
        with mock.patch.object(scan, "DIRECTIVES", directives), \
                mock.patch.object(scan, "projects_root", return_value=self.root), \
                mock.patch.object(scan, "mac_room", return_value=(True, "Mac: room: yes")), \
                mock.patch.object(scan.time, "time", return_value=NOW), contextlib.redirect_stdout(out):
            self.assertEqual(scan.main([]), started(out))
        text = out.getvalue()
        lines = text.splitlines()
        self.assertEqual(lines[:6], [
            "D-20251212-system  WAITS | NEXT (2026-01-01): curate it; waits: results of the replay",
            "Warning: D-20251212-system's NEXT row (2026-01-01) waits on results with no date first, so "
            "nothing wakes it: write the date it's due first (\"waits: 2026-01-10 08:30Z, ...\"), or the order that "
            "brings it (\"waits: /3, ...\")",
            "D-20251218-held  BOARD | NEXT (2026-01-01): ship it; waits: b1 the post",
            "Warning: D-20251218-held's row of 2026-01-02 holds \"NEXT:\" mid-row, below its latest NEXT row "
            "(2026-01-01): the scan reads only a row that starts with NEXT:, so if that step is current, give it its "
            "own row",
            "D-20251219-new  RUNNING | agents: critic (path)",
            "Warning: D-20251219-new's row of 2026-01-01 holds \"NEXT:\" mid-row, and it has no NEXT row: the scan "
            "reads only a row that starts with NEXT:, so if that step is current, give it its own row",
        ])
        self.assertIn('Start now (ceo.md, "Capacity"): none', lines)
        self.assertNotIn("Running with no ORDER id", text)
        self.assertNotIn("CANARY", text)

    def test_an_order_header_the_scan_cannot_read_is_named(self):
        directives = self.root / "directives"
        directives.mkdir()
        (directives / "README.md").write_text(README)
        (directives / "D-20251219-new.md").write_text(status_log("NEXT: ship it; waits: /10"))
        self.agent("c1", "cto", f"ORDER D-20251219-new/10 (resumed)   from: ceo   to: cto\n{CANARY}")
        self.agent("s1", "senior-engineer", "ORDER D-20251219-new/10.T2   from: cto   to: senior-engineer", parent="c1")
        self.agent("s2", "senior-engineer", f"ORDER D-20251219-new/10-land from cto to senior-engineer {CANARY}",
                   parent="c1")
        self.agent("c2", "cto", f"  ORDER D-20251219-new/11 (CTO to Senior; the CEO's order below) {CANARY}")
        self.agent("k1", "critic", "ORDER is the file knowledge/board/directives/D-20251219-new.md")
        self.agent("a1", "analyst", "Your ORDER is in this file")  # doesn't start with it: no warning
        self.agent("a2", "analyst", "ORDER D-20251219-new/11 (resumed)   from: ceo   to: analyst", finished=True)
        self.agent("a3", "analyst", "ORDER D-20251219-new/12 from ceo to analyst", finished=True)  # not running: no warning
        out = io.StringIO()
        with mock.patch.object(scan, "DIRECTIVES", directives), \
                mock.patch.object(scan, "projects_root", return_value=self.root), \
                mock.patch.object(scan, "mac_room", return_value=(True, "Mac: room: yes")), \
                mock.patch.object(scan.time, "time", return_value=NOW), contextlib.redirect_stdout(out):
            self.assertEqual(scan.main([]), started(out))
        text = out.getvalue()
        row = next(line for line in text.splitlines() if line.startswith("D-20251219-new  "))
        state, mine, nxt = row.split(" | ")
        self.assertEqual((state, nxt), ("D-20251219-new  WAITS", "NEXT (2026-01-01): ship it; waits: /10"))
        self.assertEqual(sorted(mine[len("agents: "):].split(", ")),
                         ["/10 cto", "/10 senior-engineer", "/10 senior-engineer", "critic (path)"])
        form = "write it \"ORDER <id>/<n> (note)   from: <role>   to: <role>\" (CLAUDE.md, \"Message formats\")"
        self.assertEqual([line for line in text.splitlines() if line.startswith("Warning:")], [
            f"Warning: agent k1 (critic) has an ORDER header the scan can't read, so it counts under D-20251219-new "
            f"(path): {form}",
            f"Warning: agent c2 (cto) has an ORDER header the scan can't read, so it counts with no ORDER id: {form}",
            f"Warning: agent s2 (senior-engineer) has an ORDER header the scan can't read, so it counts under "
            f"D-20251219-new/10: {form}",
        ])
        self.assertIn("Running with no ORDER id: 2 (analyst, cto)\n", text)
        self.assertNotIn("CANARY", text)

    def test_an_unreadable_header_after_a_preamble_is_named(self):
        """A header line warns wherever it sits in the prompt."""
        self.agent("c1", "cto", f"Re-check the log first.\nORDER D-20251219-new/16 (resumed) from ceo to cto\n{CANARY}")
        self.agent("c2", "cto", f"Re-check the log first.\n\nORDER D-20251219-new/17   from: ceo   to: cto\n{CANARY}")
        self.agent("c3", "cto", f"Re-check the log first: the ORDER D-20251219-new/18 from ceo, below.\n{CANARY}")
        # its own header unreadable, its parent's quoted after it read
        self.agent("c4", "cto", f"Re-check the log first.\nORDER D-20251219-new/19 ({'x' * 81})   from: ceo   to: cto\n"
                                f"It continues:\nORDER D-20251219-new/9   from: ceo   to: cto\n{CANARY}")
        unread = []
        scan.agents(self.root, NOW, unread)
        self.assertEqual(sorted(unread, key=lambda a: a[0]),
                         [("c1", "cto", None), ("c4", "cto", ("D-20251219-new", "9", "ceo", "cto"))])

    def test_an_agent_resuming_several_orders_runs_each(self):
        """Each directive lists the agent, a wait on any of its orders reads
        WAITS, and the list warns of no unreadable header."""
        directives = self.root / "directives"
        directives.mkdir()
        (directives / "README.md").write_text(README)
        (directives / "D-20251212-system.md").write_text(status_log("NEXT: land it; waits: /7"))
        (directives / "D-20251218-held.md").write_text(status_log("NEXT: ship it; waits: /3, then b1"))
        (directives / "D-20251219-new.md").write_text(status_log("NEXT: curate it; waits: /5"))
        self.agent("c1", "cto", "RESUME of ORDER D-20251212-system/7, ORDER D-20251219-new/2, "
                                "ORDER D-20251219-new/5 and ORDER D-20251218-held/3   from: ceo   to: cto   (restart)\n"
                                f"{CANARY}")
        self.agent("s1", "senior-engineer", f"Task T4 in a worktree. {CANARY}", parent="c1")
        self.agent("a1", "analyst", f"ORDER D-20251219-new/8 and ORDER D-20251219-new/9   from: ceo   to: analyst\n{CANARY}")
        out = io.StringIO()
        with mock.patch.object(scan, "DIRECTIVES", directives), \
                mock.patch.object(scan, "projects_root", return_value=self.root), \
                mock.patch.object(scan, "mac_room", return_value=(True, "Mac: room: yes")), \
                mock.patch.object(scan.time, "time", return_value=NOW), contextlib.redirect_stdout(out):
            self.assertEqual(scan.main([]), started(out))
        text = out.getvalue()
        rows = {line.split("  ")[0]: line.split(" | ") for line in text.splitlines() if line.startswith("D-")}
        self.assertEqual({d: (row[0], sorted(row[1][len("agents: "):].split(", "))) for d, row in rows.items()}, {
            "D-20251212-system": ("D-20251212-system  WAITS", ["/7 cto", "/7 senior-engineer"]),
            "D-20251218-held": ("D-20251218-held  WAITS", ["/3 cto", "/3 senior-engineer"]),
            "D-20251219-new": ("D-20251219-new  WAITS", ["/2 cto", "/2 senior-engineer", "/5 cto", "/5 senior-engineer",
                                                         "/8 analyst", "/9 analyst"])})
        self.assertIn('Start now (ceo.md, "Capacity"): none\n', text)
        self.assertNotIn("Warning:", text)
        self.assertNotIn("Running with no ORDER id", text)
        self.assertNotIn("CANARY", text)

    @staticmethod
    def sent(text, woke=False, kind="coordinator"):
        """A message from the agent's manager by SendMessage, as Claude Code writes it: a
        queued_command attachment while the agent ran, or a user record when it woke a finished one."""
        if woke:
            return {"type": "user", "isMeta": True, "origin": {"kind": kind}, "message": {
                "role": "user", "content": f"The coordinator sent a message while you were working:\n{text}"}}
        return {"type": "attachment", "attachment": {"type": "queued_command", "prompt": text, "origin": {"kind": kind},
                                                     "isMeta": True}}

    def test_an_order_sent_later_by_sendmessage_runs_too(self):
        """Its CTO runs /6, which reached it by SendMessage after an earlier order."""
        directives = self.root / "directives"
        directives.mkdir()
        (directives / "README.md").write_text(README + "".join(
            f"| [{d}]({d}.md) | x | in-progress | 2026-01-11 |\n" for d in (
                "D-20260111-cold-fresh-air", "D-20260110-wall-map", "D-20251220-desk-lamps")))
        (directives / "D-20260111-cold-fresh-air.md").write_text(status_log("NEXT: explain it; waits: /6"))
        (directives / "D-20251212-system.md").write_text(status_log("NEXT: land it; waits: /42"))
        sent = self.sent
        self.agent("c1", "cto", f"ORDER D-20251219-new/1   from: ceo   to: cto\n{CANARY}", records=[
            sent(f"ORDER D-20251212-system/42   from: ceo   to: cto\n{CANARY}", woke=True)])
        self.agent("s1", "senior-engineer", f"Task T4 in a worktree. {CANARY}", parent="c1")
        self.agent("c2", "cto", f"ORDER D-20260111-cold-fresh-air/5   from: ceo   to: cto\n{CANARY}", records=[
            sent(f"ORDER D-20260111-cold-fresh-air/6   from: ceo   to: cto\n{CANARY}", woke=True),
            sent(f"RULING cfa/6 2026-01-13T11:00:30Z (CEO, date -u): {CANARY}"),
            sent(f"RULING cfa/7 2026-01-13T11:10Z: {CANARY}"),
            sent(f"RULING D-20251218-held/3 (CEO): {CANARY}")])
        self.agent("c3", "cto", "ORDER D-20251219-new/4   from: ceo   to: cto", finished=True, records=[
            sent("ORDER D-20251212-system/43   from: ceo   to: cto", woke=True)])
        quoted = {"type": "assistant", "message": {"role": "assistant", "content": [
            {"type": "text", "text": '{"kind": "coordinator"}\nORDER D-20251218-held/9   from: ceo   to: cto'}]}}
        self.agent("n1", "cto", "ORDER D-20251219-new/2   from: ceo   to: cto", records=[
            sent("CEO RULING 2026-01-12T06:30:30Z: ORDER D-20251218-held/4   from: ceo   to: cto"),  # not first
            sent("A note first.\nORDER D-20251218-held/5   from: ceo   to: cto", woke=True),  # not the first line
            sent("ORDER D-20251218-held/6   from: cto   to: senior-engineer", kind="peer"),  # not its manager's
            {"type": "attachment", "attachment": {"type": "queued_command", "prompt": "ORDER D-20251218-held/7"}},
            sent("RULING mp/3 (two open directives have mp)"), sent("RULING zz/1 (none has zz)"),
            sent("RULING o/1 (D-20251216-old has o, but it's done)"), sent("RULING D-20251218-held: no number"),
            quoted])  # its own words send nothing
        with mock.patch.object(scan, "DIRECTIVES", directives):  # where a short id is looked up
            self.assertEqual(sorted((d, n, role) for d, n, role, _ in scan.agents(self.root, NOW)), sorted([
                ("D-20251219-new", "1", "cto"), ("D-20251212-system", "42", "cto"),
                ("D-20251219-new", "1", "senior-engineer"), ("D-20251212-system", "42", "senior-engineer"),
                ("D-20260111-cold-fresh-air", "5", "cto"), ("D-20260111-cold-fresh-air", "6", "cto"),
                ("D-20260111-cold-fresh-air", "7", "cto"), ("D-20251218-held", "3", "cto"),
                ("D-20251219-new", "2", "cto")]))
            out = io.StringIO()
            with mock.patch.object(scan, "projects_root", return_value=self.root), \
                    mock.patch.object(scan, "mac_room", return_value=(True, "Mac: room: yes")), \
                    mock.patch.object(scan.time, "time", return_value=NOW), contextlib.redirect_stdout(out):
                self.assertEqual(scan.main([]), started(out))
        text = out.getvalue()
        self.assertIn("D-20260111-cold-fresh-air  WAITS | agents: /5 cto, /6 cto, /7 cto | NEXT (2026-01-01): "
                      "explain it; waits: /6\n", text)
        self.assertIn("D-20251212-system  WAITS | agents: /42 cto, /42 senior-engineer | NEXT", text)
        self.assertNotIn("/43", text)
        self.assertNotIn("CANARY", text)
        self.assertNotIn("Warning:", text)

    def test_a_header_s_roles_may_be_in_any_case(self):
        self.assertEqual(scan.first_orders(f"ORDER D-20251219-new/3   from: CEO   to: platform-engineer\n{CANARY}"),
                         [("D-20251219-new", "3", "ceo", "platform-engineer")])
        self.assertEqual(scan.first_orders("ORDER D-20251219-new/9 (resumed)   from: CEO (main)   to: CTO"),
                         [("D-20251219-new", "9", "ceo", "cto")])
        self.agent("p1", "platform-engineer", f"ORDER D-20251219-new/3   from: CEO   to: platform-engineer\n{CANARY}")
        self.agent("c1", "cto", f"RESUME of ORDER D-20251219-new/4 and ORDER D-20251219-new/5   from: CEO   to: CTO\n"
                                f"{CANARY}")
        unread = []
        self.assertEqual(sorted((d, n, role) for d, n, role, _ in scan.agents(self.root, NOW, unread)), [
            ("D-20251219-new", "3", "platform-engineer"), ("D-20251219-new", "4", "cto"), ("D-20251219-new", "5", "cto")])
        self.assertEqual(unread, [])

    def test_a_sent_order_is_one_alone_or_with_a_header_s_tail_after_at_most_a_sender_s_role(self):
        directives = self.root / "directives"
        directives.mkdir()
        (directives / "README.md").write_text(README + "| [D-20260111-cold-fresh-air](D-20260111-cold-fresh-"
                                              "air.md) | x | in-progress | 2026-01-11 |\n")
        sent = self.sent
        self.agent("c1", "cto", "ORDER D-20251219-new/1   from: ceo   to: cto", records=[
            sent(f"CEO RULING cfa/6 2026-01-13T11:00Z: {CANARY}"),
            sent(f"CTO ORDER D-20251218-held/3   from: CTO   to: staff-engineer\n{CANARY}"),
            sent(f"staff RULING D-20251218-held/4: {CANARY}"), sent("Cmo ORDER D-20251218-held/5", woke=True),
            sent(f"ORDER D-20251218-held/6\n{CANARY}"), sent("ORDER D-20251218-held/7.T2 (resumed)  "),
            sent("ORDER D-20251218-held/8   from: CEO   to: CTO")])
        self.agent("n1", "cto", "ORDER D-20251219-new/2   from: ceo   to: cto", records=[
            sent("ORDER D-20251218-held/10 is cancelled"), sent("ORDER D-20251218-held/11: read it first"),
            sent("CEO CTO RULING D-20251218-held/12"), sent("The CEO RULING D-20251218-held/13"),
            sent("CFO RULING D-20251218-held/14"), sent("CEO: RULING D-20251218-held/15"),
            sent("CEOs ORDER D-20251218-held/16"), sent("CEO RULING on D-20251218-held/17"),
            sent("CEO RULING 2026-01-12T06:30:30Z: ORDER D-20251218-held/18   from: ceo   to: cto"),
            # a peer's message that holds "coordinator" in another field
            {"type": "attachment", "attachment": {"type": "queued_command", "prompt": "ORDER D-20251218-held/19",
                                                  "origin": {"kind": "peer", "name": "coordinator"}}},
            {"type": "user", "origin": {"kind": "peer"}, "sender": "coordinator", "message": {
                "role": "user", "content": "ORDER D-20251218-held/20"}}])
        with mock.patch.object(scan, "DIRECTIVES", directives):
            self.assertEqual(sorted((d, n, role) for d, n, role, _ in scan.agents(self.root, NOW)), sorted([
                ("D-20251219-new", "1", "cto"), ("D-20260111-cold-fresh-air", "6", "cto"),
                *(("D-20251218-held", n, "cto") for n in "345678"), ("D-20251219-new", "2", "cto")]))

    def test_a_sent_list_without_resume_of_counts_each_order(self):
        """A list ending its line, as a queued_command attachment, counts as a header does."""
        sent = self.sent
        listed = ("ORDER D-20260118-new-tabs/13, ORDER D-20260104-wide-tables/5 and "
                  "ORDER D-20260109-round-icons/7")
        self.agent("c1", "cto", f"ORDER D-20260118-new-tabs/13   from: ceo   to: cto\n{CANARY}", records=[
            sent(f"{listed}\nCEO note, no change to the orders. {CANARY}"),
            sent(f"ORDER D-20260118-new-tabs/14   from: ceo   to: cto\n{CANARY}"),
            sent("ORDER D-20251219-new/1 and ORDER D-20251219-new/2 are done; read them"),  # prose: no list
            sent("ORDER D-20251219-new/3, ORDER D-20251219-new/4 (resumed)", woke=True)])
        self.agent("s1", "senior-engineer", f"Task T1. {CANARY}", parent="c1")
        unread = []
        self.assertEqual(sorted((d, n, role) for d, n, role, _ in scan.agents(self.root, NOW, unread)), sorted(
            (d, n, role) for role in ("cto", "senior-engineer") for d, n in (
                ("D-20260118-new-tabs", "13"), ("D-20260104-wide-tables", "5"),
                ("D-20260109-round-icons", "7"), ("D-20260118-new-tabs", "14"), ("D-20251219-new", "3"),
                ("D-20251219-new", "4"))))
        self.assertEqual(unread, [])
        self.assertEqual(sorted(o[:2] for o in scan.first_orders(f"{listed}\n{CANARY}")), [
            ("D-20260104-wide-tables", "5"), ("D-20260109-round-icons", "7"),
            ("D-20260118-new-tabs", "13")])  # a first prompt's list ending its line reads so too

    def test_a_short_id_is_the_first_letter_of_each_word_of_the_slug(self):
        self.assertEqual(scan.short_id("D-20260111-cold-fresh-air"), "cfa")
        self.assertEqual(scan.short_id("D-20251215-first-launch"), "fl")
        self.assertEqual(scan.short_id("D-20260112-refresh"), "r")

    def test_the_scan_reads_which_directives_are_open(self):
        directives = self.root / "directives"
        directives.mkdir()
        (directives / "README.md").write_text(README)
        (directives / "D-20251212-system.md").write_text(status_log("NEXT: a; waits: D-20251218-held"))
        (directives / "D-20251219-new.md").write_text(status_log("NEXT: b; waits: D-20251216-old (its report)"))
        rows = scan.scan(directives, [], TODAY)
        self.assertEqual([(d, s) for d, s, _, _ in rows], [
            ("D-20251212-system", "WAITS"), ("D-20251218-held", "NO NEXT"), ("D-20251219-new", "IDLE")])


class Backlog(unittest.TestCase):
    """A backlog page's row that isn't done, waits on nothing hard and has no
    running order is IDLE, under "Start now"."""

    AT = datetime(2026, 1, 7, 12, 0, tzinfo=timezone.utc).timestamp()  # TODAY, at noon UTC
    RUNNING = [("D-20251219-new", "3", "cto", 1)]

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.knowledge = self.root / "knowledge"

    def tearDown(self):
        self.tmp.cleanup()

    def page(self, path=RM_911, *, status="active", flag="true", header=HEADER, extra=""):
        page = self.root / path
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text(BACKLOG_PAGE.format(status=status, flag=flag, header=header) + extra)
        return page

    def states(self, running=RUNNING):
        return [(ref, state) for ref, state, *_ in scan.backlog(self.knowledge, running, TODAY, ["D-20251219-new"],
                                                                self.AT)]

    def test_one_row_of_each_kind(self):
        """Done, idle, a hard wait (b3), a date that has come, one still to come, a running order."""
        self.page()
        self.assertEqual(self.states(), [(f"{RM_911}#18", "IDLE"), (f"{RM_911}#19", "WAITS"), (f"{RM_911}#20", "IDLE"),
                                         (f"{RM_911}#21", "WAITS"), (f"{RM_911}#22", "RUNNING")])
        # no agent runs /3 any more: #22 waits on nothing, so it is idle work
        self.assertEqual(self.states([])[-1], (f"{RM_911}#22", "IDLE"))
        row = scan.backlog(self.knowledge, self.RUNNING, TODAY)[0]
        self.assertEqual(row, (f"{RM_911}#18", "IDLE", "**Attachments** ([DD-914](../dd/DD-914.md)), with a \\| pipe",
                               "–", "none"))

    def test_waits_reads_as_a_next_row_s(self):
        """The scan's own rules, unchanged."""
        rows = "".join(f"| {n} | Item {n} | not started | S | two-way | {waits} | – |\n" for n, waits in enumerate((
            "–", "", "board-order, the Board's order", "2026-01-07 13:00Z", "2026-01-07 11:00Z, then b1",
            "D-20251219-new/3 (its report)", "D-20251219-new/5", "D-20251219-new", "D-20251216-old",
            "the CTO's design", "none (see b2)", "D-20251219-new/5 and b2",
            "/3 (its report)"), 30))  # a bare /n names no directive here, though D-20251219-new/3 runs
        self.page(extra=f"\n{HEADER}\n|---|---|---|---|---|---|---|\n{rows}")
        found = dict(self.states())
        self.assertEqual([found[f"{RM_911}#{n}"] for n in range(30, 43)], [
            "IDLE", "IDLE", "WAITS", "WAITS", "WAITS", "WAITS", "IDLE", "WAITS", "IDLE", "WAITS", "IDLE", "IDLE",
            "IDLE"])

    def test_a_hard_wait_prints_waits_whoever_runs_its_order(self):
        """A row with a hard wait prints as WAITS."""
        self.page(extra=f"\n{HEADER}\n|---|---|---|---|---|---|---|\n"
                        "| 50 | Running, on b3 | in progress | S | b3 | b3, the yes | D-20251219-new/3 |\n"
                        "| 51 | Running, a date to come | in progress | S | two-way | 2026-01-09 | D-20251219-new/3 |\n"
                        "| 52 | Running, a date come | in progress | S | two-way | 2026-01-01 | D-20251219-new/3 |\n")
        found = dict(self.states())
        self.assertEqual([found[f"{RM_911}#{n}"] for n in (50, 51, 52)], ["WAITS", "WAITS", "RUNNING"])

    def test_paused_by_the_board_is_a_hard_wait(self):
        """A Waits that starts "paused by the Board" is the Board's hold, as a b7
        first word is, even after an order no agent runs any more (which alone reads IDLE)."""
        self.page(extra=f"\n{HEADER}\n|---|---|---|---|---|---|---|\n"
                        "| 60 | Paused | not started | S | two-way | paused by the Board, after D-20251219-new/5 | – |\n"
                        # the bold form after a stopped order: without the hold, IDLE, then RUNNING by its Order
                        "| 61 | Paused, bold | in progress | S | two-way | **Paused by the Board** 2026-01-18, after "
                        "D-20251219-new/5 | D-20251219-new/3 |\n"
                        "| 62 | The b7 form | not started | S | two-way | b7, the Board's pause | – |\n"
                        "| 63 | Not a pause | not started | S | two-way | D-20251219-new/5, paused by the Board before | – |\n")
        found = dict(self.states())
        self.assertEqual([found[f"{RM_911}#{n}"] for n in (60, 61, 62, 63)], ["WAITS", "WAITS", "WAITS", "IDLE"])

    def test_pages_that_are_not_backlog_pages(self):
        self.page("knowledge/engineering/roadmaps/RM-901-x.md", flag="false")
        self.page("knowledge/research/2026-01-14-note.md")  # raw web notes, never instructions
        self.page("knowledge/_templates/backlog.md")
        self.page("knowledge/engineering/roadmaps/RM-902-old.md", status="archived")
        self.page("knowledge/engineering/roadmaps/RM-903-old.md", status="superseded")
        no_front = self.knowledge / "company" / "plan.md"
        no_front.parent.mkdir(parents=True)
        no_front.write_text(BACKLOG_PAGE.format(status="active", flag="true", header=HEADER).split("---\n", 2)[2])
        self.assertEqual(self.states(), [])
        self.page("knowledge/products/x/backlog.md", status="draft", flag='"True"')
        self.assertEqual(len(self.states()), 5)
        self.assertTrue(all(ref.startswith("knowledge/products/x/backlog.md#") for ref, _ in self.states()))

    def test_only_a_table_with_the_columns_is_read(self):
        self.page(header="| # | Item | State | Size | Door | Waits | Order |")
        self.assertEqual(self.states(), [])
        text = ("| Order | Waits | # | Status | Item |\n|---|---|---|---|---|\n"
                "| – | none | 7 | not started | Seven |\n| 8 |\n")  # columns by name; a short row is skipped
        self.assertEqual(scan.backlog_rows(text), [(3, "7", "Seven", "not started", "none", "–")])

    def test_a_row_with_no_id_is_named_by_its_line(self):
        self.page(extra=f"\n{HEADER}\n|---|---|---|---|---|---|---|\n"
                        "|  | No id | not started | S | two-way | none | – |\n")
        self.assertEqual(self.states()[-1], (f"{RM_911}#L27", "IDLE"))

    def run_main(self, running=()):
        directives = self.root / "directives"
        directives.mkdir(exist_ok=True)
        (directives / "README.md").write_text(README)
        for held in ("D-20251212-system", "D-20251218-held", "D-20251219-new"):
            (directives / f"{held}.md").write_text(status_log("NEXT: ship it; waits: b1 the post"))
        folder = self.root / "projects" / "session-1" / "subagents"
        folder.mkdir(parents=True, exist_ok=True)
        for agent_id, prompt in running:
            (folder / f"agent-{agent_id}.meta.json").write_text(json.dumps({"agentType": "cto"}))
            log = folder / f"agent-{agent_id}.jsonl"
            log.write_text(json.dumps({"type": "user", "message": {"role": "user", "content": prompt}}) + "\n")
            os.utime(log, (self.AT - 60, self.AT - 60))
        out = io.StringIO()
        with mock.patch.object(scan, "DIRECTIVES", directives), mock.patch.object(scan, "KNOWLEDGE", self.knowledge), \
                mock.patch.object(scan, "projects_root", return_value=self.root / "projects"), \
                mock.patch.object(scan, "mac_room", return_value=(True, "Mac: room: yes")), \
                mock.patch.object(scan.time, "time", return_value=self.AT), contextlib.redirect_stdout(out):
            self.assertEqual(scan.main([]), started(out))
        return out.getvalue()

    def test_the_scan_prints_each_row_and_starts_the_idle_ones(self):
        self.page(extra=f"\n{HEADER}\n|---|---|---|---|---|---|---|\n"
                        "| 40 | A wait it doesn't count | not started | S | two-way | D-20251219-new/5 and b2 | – |\n")
        text = self.run_main([("c1", f"ORDER D-20251219-new/3   from: ceo   to: cto\n{CANARY}")])
        self.assertEqual([line for line in text.splitlines() if line.startswith(("BACKLOG", "Warning"))], [
            f"BACKLOG {RM_911}#18  IDLE | Attachments (DD-914), with a \\| pipe | waits: none",
            f"BACKLOG {RM_911}#19  WAITS | A shorter delete prompt | waits: b3, the Board's yes on lowering protection",
            f"BACKLOG {RM_911}#20  IDLE | Color picker | order: D-20251219-new/4 | waits: 2026-01-01, the replay's end",
            f"BACKLOG {RM_911}#21  WAITS | The read-back | waits: 2026-01-09, after the deploy",
            f"BACKLOG {RM_911}#22  RUNNING | Site search | order: D-20251219-new/3 | waits: none",
            f"BACKLOG {RM_911}#40  IDLE | A wait it doesn't count | waits: D-20251219-new/5 and b2",
            f"Warning: {RM_911}#40 reads IDLE but its Waits names b2, which the scan doesn't count as a door there: "
            "read it, and if it waits on the Board, have its page's owner write b2 first or after \", then\" "
            "(\"D-<id>/<n>, then b2\")"])
        self.assertIn(f'Start now (ceo.md, "Capacity"): {RM_911}#18, {RM_911}#20, {RM_911}#40\n', text)
        self.assertNotIn("CANARY", text)

    def test_a_backlog_page_with_no_row_the_scan_can_read_is_named(self):
        """A header missing a column."""
        self.page(header="| # | Item | Status | Size | Door | Wait | Order |")
        done = self.page("knowledge/engineering/roadmaps/RM-912-done.md")
        done.write_text(done.read_text().replace("not started", "done").replace("partly built", "done")
                        .replace("in progress", "done"))
        unread = []
        self.assertEqual(scan.backlog(self.knowledge, [], TODAY, unread=unread), [])
        self.assertEqual(unread, [RM_911])  # a page whose rows are all done is read, and quiet
        text = self.run_main()
        self.assertIn(f"Warning: {RM_911} has `backlog: true` but no row the scan can read: its table's header needs "
                      "the columns \"| # | Item | Status | Size | Door | Waits | Order |\" (ceo.md, \"Capacity\")\n", text)
        self.assertEqual(text.count("Warning:"), 1)

    def test_with_no_backlog_page_nothing_changes(self):
        text = self.run_main()
        self.assertNotIn("BACKLOG", text)
        self.assertIn('Start now (ceo.md, "Capacity"): none\n', text)

    def test_a_long_item_is_cut(self):
        line = scan.format_backlog("p#1", "IDLE", "x" * 81, "–", "")
        self.assertEqual(line, f"BACKLOG p#1  IDLE | {'x' * 77}... | waits: none")

    def test_ceo_md_documents_the_key_and_the_columns_the_scan_reads(self):
        """ceo.md's "Capacity" names the key and the table, read here so a wording the scan can't read
        fails."""
        text = (SCRIPTS.parent / ".claude" / "agents" / "executive" / "ceo.md").read_text(encoding="utf-8")
        section = text.split("## Capacity", 1)[1].split("\n## ", 1)[0]
        self.assertIn("`backlog: true`", section)
        header = re.search(r"`(\| # \|[^`]*)`", section).group(1)
        self.assertEqual(header, HEADER)
        self.page(header=header)
        self.assertEqual(len(self.states()), 5)


DESIGN = """---
title: {title}
owner: staff-engineer
status: draft
updated: 2026-01-15
related: []
---

# The design

**Order:** D-20260115-blue-site/1.WS-1   **Design status:** {status}

## Context

Body text.
"""


class Signoffs(unittest.TestCase):
    """A design that waits for the CEO's yes is something to start."""

    AT = Backlog.AT
    page = Backlog.page
    run_main = Backlog.run_main

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.knowledge = self.root / "knowledge"
        self.designs = self.knowledge / "engineering" / "designs"
        self.designs.mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def design(self, name, status, title="A design", text=DESIGN):
        page = self.designs / name
        page.write_text(text.format(title=title, status=status))
        return page

    def others(self):
        """DDs that wait for no sign-off by the CEO, and files the scan can't read or doesn't read."""
        self.design("DD-901-deployed.md", "deployed (2025-12-16)")
        self.design("DD-902-implementing.md", "`implementing` (CEO approved 2026-01-06, two-way; awaiting-ceo before)")
        self.design("DD-903-board.md", "awaiting-board (one-way, b4)")
        self.design("DD-904-later.md", "deployed. Log: \n\n**Design status:** awaiting-ceo (an old row)")  # the first
        self.design("DD-905-no-status.md", "", text=DESIGN.replace("**Design status:** {status}", "{status}"))
        (self.designs / "DD-906-a-folder.md").mkdir()  # can't be read
        self.design("README.md", "awaiting-ceo (not a DD file)")
        self.design("dd-907-lower.md", "awaiting-ceo (not a DD file name)")

    def test_awaiting_ceo_is_found_in_any_case_after_backticks_or_bold(self):
        self.design("DD-912-tables.md", "awaiting-ceo (round 1 done, its 3 majors fixed).",
                    title="DD-912 Acme - a wide table view (RM-912 WS-1)")
        self.design("DD-913-lists.md", "**Awaiting-CEO** (2026-01-15: design round 1 CHANGES_REQUESTED)",
                    title='"DD-913: Acme /lists split in two"')
        self.design("DD-911-notes.md", "`AWAITING-ceo` (approved by the fix rule)", title="Empty-list notes (#4)")
        self.others()
        self.assertEqual(scan.signoffs(self.designs), [
            ("DD-911", "Empty-list notes (#4)", "`AWAITING-ceo` (approved by the fix rule)"),
            ("DD-912", "Acme - a wide table view (RM-912 WS-1)", "awaiting-ceo (round 1 done, its 3 majors fixed)."),
            ("DD-913", "Acme /lists split in two", "**Awaiting-CEO** (2026-01-15: design round 1 CHANGES_REQUESTED)")])

    def test_another_status_a_missing_line_or_an_unreadable_file_is_ignored(self):
        self.others()
        locked = self.design("DD-908-locked.md", "awaiting-ceo (unreadable)")
        locked.chmod(0)
        if os.access(locked, os.R_OK):  # root reads it anyway
            locked.unlink()
        (self.designs / "DD-909-bytes.md").write_bytes(b"\xff\xfe**Design status:** implementing\n")
        self.assertEqual(scan.signoffs(self.designs), [])
        self.assertEqual(scan.signoffs(self.root / "no-such-folder"), [])

    def test_a_title_is_cut_to_60_and_a_status_to_80(self):
        self.assertEqual(scan.format_signoff("DD-912", "x" * 60, "y" * 80), f"SIGNOFF DD-912 {'x' * 60}: {'y' * 80}")
        self.assertEqual(scan.format_signoff("DD-912", "x" * 61, "y" * 81),
                         f"SIGNOFF DD-912 {'x' * 57}...: {'y' * 77}...")
        self.assertEqual(scan.format_signoff("DD-912", "**A** [link](../x.md)", "awaiting-ceo ([RM-912](../rm.md))"),
                         "SIGNOFF DD-912 A link: awaiting-ceo (RM-912)")
        self.design("DD-970-no-title.md", "awaiting-ceo", text=DESIGN.replace("title: {title}\n", ""))
        self.design("DD-971-only-the-id.md", "awaiting-ceo", title='"DD-971:"')
        self.assertEqual(scan.signoffs(self.designs), [("DD-970", "no-title", "awaiting-ceo"),
                                                       ("DD-971", "only-the-id", "awaiting-ceo")])

    def test_the_scan_prints_them_after_the_backlog_rows_and_starts_them(self):
        self.page()
        self.others()
        self.design("DD-912-tables.md", "awaiting-ceo (round 1 done)", title="DD-912 Acme - a wide table view")
        lines = self.run_main().splitlines()
        signoff = lines.index("SIGNOFF DD-912 Acme - a wide table view: awaiting-ceo (round 1 done)")
        self.assertEqual([line for line in lines if line.startswith("SIGNOFF")], [lines[signoff]])
        self.assertEqual(lines[signoff - 1], f"BACKLOG {RM_911}#22  IDLE | Site search | order: "
                                             "D-20251219-new/3 | waits: none")  # the last backlog row
        self.assertEqual(lines[signoff + 1:], [
            "Mac: room: yes", f'Start now (ceo.md, "Capacity"): {RM_911}#18, {RM_911}#20, {RM_911}#22, DD-912'])

    def test_with_no_design_awaiting_ceo_the_output_is_unchanged_byte_for_byte(self):
        self.page()
        before = self.run_main()
        self.others()
        self.assertEqual(self.run_main(), before)
        self.assertEqual(before, (
            "D-20251212-system  BOARD | NEXT (2026-01-01): ship it; waits: b1 the post\n"
            "D-20251218-held  BOARD | NEXT (2026-01-01): ship it; waits: b1 the post\n"
            "D-20251219-new  BOARD | NEXT (2026-01-01): ship it; waits: b1 the post\n"
            f"BACKLOG {RM_911}#18  IDLE | Attachments (DD-914), with a \\| pipe | waits: none\n"
            f"BACKLOG {RM_911}#19  WAITS | A shorter delete prompt | waits: b3, the Board's yes on lowering "
            "protection\n"
            f"BACKLOG {RM_911}#20  IDLE | Color picker | order: D-20251219-new/4 | waits: 2026-01-01, the replay's end\n"
            f"BACKLOG {RM_911}#21  WAITS | The read-back | waits: 2026-01-09, after the deploy\n"
            f"BACKLOG {RM_911}#22  IDLE | Site search | order: D-20251219-new/3 | waits: none\n"
            "Mac: room: yes\n"
            f'Start now (ceo.md, "Capacity"): {RM_911}#18, {RM_911}#20, {RM_911}#22\n'))


class ExitCode(unittest.TestCase):
    """The full scan exits 1 when "Start now" lists anything, else 0, so a
    caller can gate on it; --mac keeps its own code."""

    AT = Backlog.AT
    page = Backlog.page
    design = Signoffs.design

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.knowledge = self.root / "knowledge"
        self.designs = self.knowledge / "engineering" / "designs"
        self.designs.mkdir(parents=True)
        self.directives = self.root / "directives"
        self.directives.mkdir()
        (self.directives / "README.md").write_text(README)
        for held in ("D-20251212-system", "D-20251218-held", "D-20251219-new"):
            self.directive(held, "NEXT: ship it; waits: b1 the post")

    def tearDown(self):
        self.tmp.cleanup()

    def directive(self, name, *events):
        (self.directives / f"{name}.md").write_text(status_log(*events))

    def run_main(self, args=(), room=True):
        out = io.StringIO()
        with mock.patch.object(scan, "DIRECTIVES", self.directives), mock.patch.object(scan, "KNOWLEDGE", self.knowledge), \
                mock.patch.object(scan, "projects_root", return_value=self.root / "projects"), \
                mock.patch.object(scan, "mac_room", return_value=(room, f"Mac: room: {'yes' if room else 'no'}")), \
                mock.patch.object(scan.time, "time", return_value=self.AT), contextlib.redirect_stdout(out):
            code = scan.main(list(args))
        return code, out.getvalue().splitlines()[-1]

    def test_nothing_to_start_exits_0(self):
        self.assertEqual(self.run_main(), (0, 'Start now (ceo.md, "Capacity"): none'))

    def test_each_kind_of_line_to_start_exits_1(self):
        kinds = (
            ("an IDLE directive", lambda: self.directive("D-20251219-new", "NEXT: curate it; waits: none"),
             "D-20251219-new"),
            ("a NO NEXT directive", lambda: self.directive("D-20251219-new", "opened"), "D-20251219-new"),
            ("an IDLE backlog row", lambda: self.page(), f"{RM_911}#18, {RM_911}#20, {RM_911}#22"),
            ("a SIGNOFF design", lambda: self.design("DD-912-tables.md", "awaiting-ceo"), "DD-912"))
        for name, make, ids in kinds:
            with self.subTest(name):
                self.tearDown()
                self.setUp()
                make()
                self.assertEqual(self.run_main(), (1, f'Start now (ceo.md, "Capacity"): {ids}'))

    def test_mac_keeps_its_own_code(self):
        self.directive("D-20251219-new", "NEXT: curate it; waits: none")
        self.assertEqual(self.run_main(["--mac"]), (0, "Mac: room: yes"))
        self.assertEqual(self.run_main(["--mac"], room=False), (1, "Mac: room: no"))


ANSWERS_PAGE = """---
title: The Board's answers, 2026-W03
owner: board
---

| R-id | Ask | Field | Edited (Dhaka) | Recorded (Dhaka) | Medium id | The Board's words |
|---|---|---|---|---|---|---|
| R-30 | A-11 | Your answer | 2026-01-16 19:30 | 2026-01-16 19:31 | page-11 | Yes |
| R-31 | A-12 | Your words | 2026-01-16 19:45 | 2026-01-16 19:46 | page-12 | Not R-30, \\| a pipe |
"""


class Answers(unittest.TestCase):
    """Each answer of the Board's no status-log row names prints as `ANSWER R-<n> <ask id>` and goes under "Start now", the backstop of the CEO's
    watcher."""

    AT = Backlog.AT
    run_main = ExitCode.run_main

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.knowledge = self.root / "knowledge"
        self.answers = self.knowledge / "board" / "answers"
        self.answers.mkdir(parents=True)
        self.directives = self.root / "directives"
        self.directives.mkdir()
        (self.directives / "README.md").write_text(README)
        for held in ("D-20251212-system", "D-20251218-held", "D-20251219-new"):
            (self.directives / f"{held}.md").write_text(status_log("NEXT: ship it; waits: b1 the post"))
        (self.answers / "2026-W03.md").write_text(ANSWERS_PAGE)
        (self.answers / "README.md").write_text("| R-id | Ask |\n|---|---|\n| R-99 | A-99 | not a week's page |\n")

    def tearDown(self):
        self.tmp.cleanup()

    def found(self):
        return scan.unhandled_answers(self.answers, self.directives)

    def test_an_answer_no_status_log_row_names_is_listed(self):
        self.assertEqual(self.found(), [("R-30", "A-11"), ("R-31", "A-12")])

    def test_a_row_naming_its_r_id_handles_it_in_any_directive_or_archive(self):
        (self.directives / "D-20260116-short-notes.md").write_text(
            status_log("ASK 1 b9 A-12 R-31: taken"))
        self.assertEqual(self.found(), [("R-30", "A-11")])
        (self.directives / "D-20251212-system-archive-1.md").write_text(
            "# An archive\n\n## Status log rows of 2026-01-16 (moved)\n\n| 2026-01-16 | ceo | R-30 A-11 quoted |\n")
        self.assertEqual(self.found(), [])

    def test_an_r_id_with_another_ask_or_none_doesn_t_handle_it(self):
        """The logs name other R-ids (a design's risks), so a row handles an answer only when it names its R-id and its ask id together."""
        (self.directives / "D-20260103-quiz-lists-archive-1.md").write_text(
            "# An archive\n\n## Status log\n\n| 2026-01-03 | cto | DD-916's R-1 and R-30: the risks, fixed |\n"
            "| 2026-01-04 | ceo | R-31 is A-99's, not this one |\n")
        self.assertEqual(self.found(), [("R-30", "A-11"), ("R-31", "A-12")])

    def test_a_note_s_answer_is_handled_by_its_r_id_beside_note(self):
        """A row of Notion's "Notes to the CEO" has the ask id "Note", which no ask id
        matches, so a row names it as `R-32 Note`; the word elsewhere in a row naming R-32 doesn't."""
        (self.answers / "2026-W04.md").write_text(ANSWERS_PAGE.replace("| R-30 | A-11 |", "| R-32 | Note |")
                                                  .replace("| R-31 | A-12 |", "| R-33 | Note |"))
        self.assertEqual(self.found(), [("R-30", "A-11"), ("R-31", "A-12"), ("R-32", "Note"), ("R-33", "Note")])
        (self.directives / "D-20260116-short-notes.md").write_text(status_log(
            "R-32 Note: \"call me\", done; A-12 R-31: taken", "Note: R-33 is a later step, not its answer"))
        self.assertEqual(self.found(), [("R-30", "A-11"), ("R-33", "Note")])
        (self.directives / "D-20260117-x.md").write_text(status_log("Quoted: | R-33 | Note | Your words |"))
        self.assertEqual(self.found(), [("R-30", "A-11")])

    def test_a_row_the_board_added_to_q_and_a_is_handled_by_its_r_id_beside_q_and_a(self):
        """A row the Board added to the Q&A table has the ask id "Q&A", so a
        row names it as `R-34 Q&A`; "Q&A" elsewhere in a row naming R-35, or "Q&As", doesn't."""
        (self.answers / "2026-W04.md").write_text(ANSWERS_PAGE.replace("| R-30 | A-11 |", "| R-34 | Q&A |")
                                                  .replace("| R-31 | A-12 |", "| R-35 | Q&A |"))
        self.assertEqual(self.found(), [("R-30", "A-11"), ("R-31", "A-12"), ("R-34", "Q&A"), ("R-35", "Q&A")])
        (self.directives / "D-20260116-short-notes.md").write_text(status_log(
            "R-34 Q&A: \"when do we ship?\", answered in Q-7", "R-35 Q&As are next; the Q&A table"))
        self.assertEqual(self.found(), [("R-30", "A-11"), ("R-31", "A-12"), ("R-35", "Q&A")])
        (self.directives / "D-20260119-x.md").write_text(status_log("Quoted: | R-35 | Q&A | Question |"))
        self.assertEqual(self.found(), [("R-30", "A-11"), ("R-31", "A-12")])

    def test_only_a_status_log_row_names_it(self):
        (self.directives / "D-20260116-short-notes.md").write_text(
            "## CEO analysis\n\n| R-30 | in a table outside the log |\nR-31 in a line\n\n"
            + status_log("R-310 and SR-31 and R-3 aren't these ids", "opened")
            + "\n| 2026-01-16 | ceo | R-31, under the next heading |\n")
        self.assertEqual(self.found(), [("R-30", "A-11"), ("R-31", "A-12")])

    def test_by_number_across_weeks(self):
        (self.answers / "2026-W04.md").write_text(ANSWERS_PAGE.replace("R-30 ", "R-9 ").replace("R-31 ", "R-100 "))
        self.assertEqual([r_id for r_id, _ in self.found()], ["R-9", "R-30", "R-31", "R-100"])

    def test_no_answers_folder(self):
        self.assertEqual(scan.unhandled_answers(self.root / "nowhere", self.directives), [])

    def test_the_scan_prints_them_before_the_mac_and_starts_them(self):
        out = io.StringIO()
        with mock.patch.object(scan, "DIRECTIVES", self.directives), mock.patch.object(scan, "KNOWLEDGE", self.knowledge), \
                mock.patch.object(scan, "projects_root", return_value=self.root / "projects"), \
                mock.patch.object(scan, "mac_room", return_value=(True, "Mac: room: yes")), \
                mock.patch.object(scan.time, "time", return_value=self.AT), contextlib.redirect_stdout(out):
            code = scan.main([])
        self.assertEqual(code, 1)
        self.assertEqual(out.getvalue().splitlines()[-4:], [
            "ANSWER R-30 A-11", "ANSWER R-31 A-12", "Mac: room: yes",
            'Start now (ceo.md, "Capacity"): ANSWER R-30 A-11, ANSWER R-31 A-12'])
        for page in self.answers.glob("*.md"):
            page.unlink()
        self.assertEqual(self.run_main(), (0, 'Start now (ceo.md, "Capacity"): none'))

    def test_start_now_lists_them_last(self):
        self.assertEqual(scan.start_now([("D-1", "IDLE", None, None)], [], [("DD-912", "t", "s")], [("R-31", "A-12")]),
                         ["D-1", "DD-912", "ANSWER R-31 A-12"])
        self.assertEqual(scan.start_now([], []), [])

    def test_a_tampered_row_is_an_alarm_under_start_now_and_never_an_answer(self):
        """A row changed outside the reader, by a plain write after
        the seal (scripts/board_desk/answers_seal.py, in a temporary folder here), prints as its ANSWERS TAMPERED line
        and goes under "Start now", and is no ANSWER line; a failed check against Notion prints its NOT CHECKED line,
        which doesn't."""
        with mock.patch.object(scan.answers_seal, "SEAL_DIR", self.root / "seal"):
            scan.answers_seal.reseal(self.root)
            page = self.answers / "2026-W03.md"
            page.write_text(page.read_text().replace("| Yes |", "| No |"))
            self.assertEqual(self.found(), [("R-31", "A-12")])
            self.assertEqual(scan.unhandled_answers(self.answers, self.directives, keep_flagged=True),
                             [("R-30", "A-11"), ("R-31", "A-12")])
            scan.answers_seal.audited(self.root, datetime(2026, 1, 16, 16, 10, tzinfo=timezone.utc),
                                      error="Notion 503: service_unavailable")
            out = io.StringIO()
            with mock.patch.object(scan, "DIRECTIVES", self.directives), \
                    mock.patch.object(scan, "KNOWLEDGE", self.knowledge), \
                    mock.patch.object(scan, "projects_root", return_value=self.root / "projects"), \
                    mock.patch.object(scan, "mac_room", return_value=(True, "Mac: room: yes")), \
                    mock.patch.object(scan.time, "time", return_value=self.AT), contextlib.redirect_stdout(out):
                self.assertEqual(scan.main([]), 1)
        lines = out.getvalue().splitlines()[-5:]
        self.assertRegex(lines.pop(2), r"\AANSWERS NOT CHECKED at 2026-01-16 [^:]+:10 \S+: Notion's read failed \(Notion "
                                       r"503: service_unavailable\); last checked never\Z")  # the time as the seal says it
        self.assertEqual(lines, [
            "ANSWER R-31 A-12", "ANSWERS TAMPERED R-30: its words or other cells changed", "Mac: room: yes",
            'Start now (ceo.md, "Capacity"): ANSWER R-31 A-12, ANSWERS TAMPERED R-30'])


class UtcDate(unittest.TestCase):
    """A `waits:` date is compared with today's UTC date, as the logs write it."""

    def run_scan(self, now, waits="2026-01-09, 48 hours"):
        with tempfile.TemporaryDirectory() as tmp:
            directives = Path(tmp)
            (directives / "README.md").write_text(README)
            (directives / "D-20251212-system.md").write_text(status_log(f"NEXT: read it; waits: {waits}"))
            for held in ("D-20251218-held", "D-20251219-new"):
                (directives / f"{held}.md").write_text(status_log("NEXT: ship it; waits: b1 the post"))
            out = io.StringIO()
            with ahead_of_utc(), mock.patch.object(scan, "DIRECTIVES", directives), \
                    mock.patch.object(scan, "projects_root", return_value=directives / "none"), \
                    mock.patch.object(scan, "mac_room", return_value=(True, "Mac: room: yes")), \
                    mock.patch.object(scan.time, "time", return_value=now), contextlib.redirect_stdout(out):
                self.assertEqual(scan.main([]), started(out))
            return out.getvalue()

    def test_the_date_is_utc_where_the_mac_s_has_turned(self):
        with ahead_of_utc():
            self.assertEqual(datetime.fromtimestamp(EVENING).date(), date(2026, 1, 9))  # the local day: come
            self.assertEqual(scan.utc_today(EVENING), date(2026, 1, 8))
            self.assertEqual(scan.utc_today(MIDNIGHT), date(2026, 1, 9))

    def test_at_18_30z_on_the_8th_the_9th_has_not_come(self):
        text = self.run_scan(EVENING)
        self.assertIn("D-20251212-system  WAITS | NEXT (2026-01-01): read it; waits: 2026-01-09, 48 hours", text)
        self.assertIn('Start now (ceo.md, "Capacity"): none\n', text)

    def test_a_wait_at_01_40z_has_not_come_at_00_05z(self):
        self.assertIn("D-20251212-system  WAITS", self.run_scan(MIDNIGHT, "2026-01-09 01:40Z, the replay"))
        self.assertIn("D-20251212-system  IDLE", self.run_scan(MIDNIGHT, "2026-01-09 00:05Z, the replay"))

    def test_at_00_05z_on_the_9th_it_has(self):
        text = self.run_scan(MIDNIGHT)
        self.assertIn("D-20251212-system  IDLE | NEXT (2026-01-01): read it; waits: 2026-01-09, 48 hours", text)
        self.assertIn('Start now (ceo.md, "Capacity"): D-20251212-system\n', text)


class Worktree(unittest.TestCase):
    """Run from a worktree, the scan reads the main checkout's session folder: where the heartbeat's transcript is."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.main = self.root / "agentic company"  # a space, as a home folder may have
        (self.main / ".git" / "worktrees" / "wt").mkdir(parents=True)
        (self.main / ".git" / "worktrees" / "wt" / "commondir").write_text("../..\n")
        self.worktree = self.main / ".claude" / "worktrees" / "wt"
        self.worktree.mkdir(parents=True)
        (self.worktree / ".git").write_text(f"gitdir: {self.main}/.git/worktrees/wt\n")

    def tearDown(self):
        self.tmp.cleanup()

    def test_main_checkout(self):
        self.assertEqual(scan.main_checkout(self.worktree), self.main)
        self.assertEqual(scan.main_checkout(self.main), self.main)  # .git is a folder
        self.assertEqual(scan.main_checkout(self.root), self.root)  # no git at all
        (self.worktree / ".git").write_text("gitdir: ../../../.git/worktrees/wt\n")
        self.assertEqual(scan.main_checkout(self.worktree), self.main)

    def run_main(self, config):
        directives = self.root / "directives"
        directives.mkdir(exist_ok=True)
        (directives / "README.md").write_text(README)
        out = io.StringIO()
        with mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": str(config)}), \
                mock.patch.object(scan, "REPO_ROOT", self.worktree), mock.patch.object(scan, "DIRECTIVES", directives), \
                mock.patch.object(scan, "mac_room", return_value=(True, "Mac: room: yes")), \
                mock.patch.object(scan.time, "time", return_value=NOW), contextlib.redirect_stdout(out):
            self.assertEqual(scan.main([]), started(out))
        return out.getvalue()

    def test_a_run_from_a_worktree_counts_the_main_session_s_agents(self):
        config = self.root / "config"
        main_session = config / "projects" / re.sub(r"[^A-Za-z0-9]", "-", str(self.main)) / "session-1" / "subagents"
        main_session.mkdir(parents=True)
        Transcripts.agent(self, "a1", "cto", "ORDER D-20251219-new/1   from: ceo   to: cto", folder=main_session)
        text = self.run_main(config)
        self.assertIn("D-20251219-new  RUNNING | agents: /1 cto", text)
        self.assertNotIn("can't see them", text)

    def test_without_the_folder_it_says_so(self):
        text = self.run_main(self.root / "no-config")
        folder = self.root / "no-config" / "projects" / re.sub(r"[^A-Za-z0-9]", "-", str(self.main))
        self.assertIn(f"Agents: can't see them, no session folder at {folder}: the states below count no running "
                      "agent\n", text)
        self.assertIn("D-20251219-new  NO NEXT", text)


class Mac(unittest.TestCase):
    def room(self, *, free_gb=100, level="1\n", free_pct="48", load=(10.0, 12.0, 30.0), cpus=10, platform="darwin"):
        def run(command, **_):
            # sysctl gives the pressure level, `memory_pressure -Q` the free percentage; an exception is unreadable
            out = level if command[0] == "sysctl" else free_pct
            if isinstance(out, Exception):
                raise out
            if command[0] == "sysctl" or not out:
                return mock.Mock(stdout=out)
            return mock.Mock(stdout="The system has 17179869184 (1048576 pages with a page size of 16384).\n"
                                    f"System-wide memory free percentage: {out}%\n")
        with mock.patch.object(scan.shutil, "disk_usage", return_value=Usage(500e9, 0, free_gb * 1e9)), \
                mock.patch.object(scan.subprocess, "run", side_effect=run), \
                mock.patch.object(scan.os, "getloadavg", **({"side_effect": load} if isinstance(load, Exception)
                                                            else {"return_value": load})), \
                mock.patch.object(scan.os, "cpu_count", return_value=cpus), \
                mock.patch.object(scan.sys, "platform", platform):
            return scan.mac_room()

    def test_room(self):
        room, line = self.room()
        self.assertTrue(room)
        self.assertEqual(line, "Mac: 100 GB free; memory pressure normal, 48% free; load 10.00, 12.00, 30.00 "
                               "(1, 5, 15 min) on 10 CPUs; room: yes")

    def test_anywhere_but_macos_memory_is_not_checked(self):
        # no macOS program is run: critical pressure, little free memory and unreadable readings hold nothing
        for platform in ("linux", "win32"):
            for kwargs in ({}, {"level": "4", "free_pct": "1"},
                           {"level": OSError("no sysctl"), "free_pct": OSError("no memory_pressure")}):
                with self.subTest(platform=platform, **kwargs), \
                        mock.patch.object(scan, "mac_memory", side_effect=AssertionError("read off macOS")):
                    room, line = self.room(platform=platform, **kwargs)
                    self.assertTrue(room, line)
                    self.assertEqual(line, "Mac: 100 GB free; memory not checked (not macOS); load 10.00, 12.00, 30.00 "
                                           "(1, 5, 15 min) on 10 CPUs; room: yes")

    def test_anywhere_but_macos_disk_and_load_hold_the_same(self):
        for kwargs, why in (({"free_gb": 14}, "under 15 GB free"), ({"free_gb": 15}, None),
                            ({"load": (1.0, 24.9, 40.0)}, None),
                            ({"load": (1.0, 25.0, 1.0)}, "5-minute load 25 or more, 2.5 per CPU"),
                            ({"load": (1.0, 10.0, 1.0), "cpus": 4}, "5-minute load 10 or more, 2.5 per CPU"),
                            ({"load": OSError("no load")}, "load unknown"),
                            ({"free_gb": 14, "load": (1.0, 25.0, 1.0)},
                             "under 15 GB free; 5-minute load 25 or more, 2.5 per CPU")):
            with self.subTest(**kwargs):
                room, line = self.room(platform="linux", **kwargs)
                self.assertEqual(room, why is None, line)
                self.assertIn(" GB free; memory not checked (not macOS); ", line)  # no "cleanup due", which macOS has
                self.assertTrue(line.endswith("room: yes" if why is None else f"room: no ({why})"), line)

    def test_a_system_without_getloadavg_has_no_room(self):
        # Windows: os has no getloadavg, so the load is unknown and holds
        room, line = self.room(platform="win32", load=AttributeError("module 'os' has no attribute 'getloadavg'"))
        self.assertFalse(room)
        self.assertEqual(line, "Mac: 100 GB free; memory not checked (not macOS); load unknown on 10 CPUs; "
                               "room: no (load unknown)")
        with mock.patch.object(scan.sys, "platform", "win32"), mock.patch.object(
                scan.shutil, "disk_usage", return_value=Usage(500e9, 0, 100e9)), mock.patch.object(scan, "os") as bare:
            del bare.getloadavg
            bare.cpu_count.return_value = 10
            self.assertEqual(scan.mac_room(), (False, line))

    def test_memory_blocks_only_when_critical_or_under_5_percent_free(self):
        for kwargs, shown, why in (
                ({}, "memory pressure normal, 48% free", None),
                ({"level": "2\n", "free_pct": "52"}, "memory pressure warn, 52% free", None),
                ({"level": "4"}, "memory pressure critical, 48% free", "memory pressure critical"),
                ({"free_pct": "4"}, "memory pressure normal, 4% free", "under 5% of memory free"),
                ({"free_pct": "5"}, "memory pressure normal, 5% free", None),
                ({"free_pct": "6"}, "memory pressure normal, 6% free", None),
                ({"level": "2", "free_pct": "4"}, "memory pressure warn, 4% free", "under 5% of memory free"),
                ({"level": "4", "free_pct": "3"}, "memory pressure critical, 3% free",
                 "memory pressure critical; under 5% of memory free")):
            with self.subTest(**kwargs):
                room, line = self.room(**kwargs)
                self.assertIn(f"; {shown};", line)
                self.assertEqual(room, why is None)
                self.assertTrue(line.endswith("room: yes" if why is None else f"room: no ({why})"), line)

    def test_no_room(self):
        for kwargs, why in (({"free_gb": 14}, "under 15 GB free"),
                            ({"load": (200.0, 180.0, 150.0)}, "5-minute load 25 or more, 2.5 per CPU")):
            room, line = self.room(**kwargs)
            self.assertFalse(room, kwargs)
            self.assertTrue(line.endswith(f"room: no ({why})"), line)

    def test_load_holds_at_2_5_per_cpu_over_5_minutes(self):
        # Only the 5-minute load counts: a high 1- or 15-minute load holds nothing, and the line shows all three.
        for load, cpus, why in (((40.0, 24.9, 40.0), 10, None),
                                ((1.0, 25.0, 1.0), 10, "5-minute load 25 or more, 2.5 per CPU"),
                                ((20.0, 30.0, 35.0), 10, "5-minute load 25 or more, 2.5 per CPU"),
                                ((1.0, 29.9, 1.0), 12, None),
                                ((1.0, 30.0, 1.0), 12, "5-minute load 30 or more, 2.5 per CPU"),
                                ((1.0, 2.5, 1.0), 1, "5-minute load 2.5 or more, 2.5 per CPU")):
            with self.subTest(load=load, cpus=cpus):
                room, line = self.room(load=load, cpus=cpus)
                self.assertEqual(room, why is None, line)
                shown = ", ".join(f"{n:.2f}" for n in load)
                self.assertIn(f"; load {shown} (1, 5, 15 min) on {cpus} CPUs; ", line)
                self.assertTrue(line.endswith("room: yes" if why is None else f"room: no ({why})"), line)

    def test_load_unreadable_means_no_room(self):
        # fail-closed, as unreadable memory is: os.getloadavg raises OSError when it can't read the load
        room, line = self.room(load=OSError("no load"))
        self.assertFalse(room)
        self.assertEqual(line, "Mac: 100 GB free; memory pressure normal, 48% free; load unknown on 10 CPUs; "
                               "room: no (load unknown)")

    def test_cleanup_due_under_60_gb_holds_nothing(self):
        # a warning, never a hold; the 15 GB hold stays
        due = " (cleanup due: remove finished worktrees);"
        for free_gb, shown, room in ((100, False, True), (60, False, True), (59, True, True), (16, True, True),
                                     (14, True, False)):
            with self.subTest(free_gb=free_gb):
                got, line = self.room(free_gb=free_gb)
                self.assertEqual(got, room, line)
                self.assertEqual(f"Mac: {free_gb} GB free{due}" in line, shown, line)
                self.assertNotIn("cleanup due", "" if shown else line)
                self.assertTrue(line.endswith("room: yes" if room else "room: no (under 15 GB free)"), line)

    def test_memory_unreadable_means_no_room(self):
        # fail-closed: a level the scan doesn't know, or no free percentage, blocks as before
        for level, shown in ((OSError("no sysctl"), "unknown"), ("", "unknown"), ("3", "3")):
            with self.subTest(level=level):
                room, line = self.room(level=level)
                self.assertFalse(room)
                self.assertIn(f"; memory pressure {shown}, 48% free;", line)
                self.assertTrue(line.endswith("room: no (memory pressure unknown)"), line)
        for free_pct in (OSError("no memory_pressure"), scan.subprocess.TimeoutExpired("memory_pressure", 5), ""):
            with self.subTest(free_pct=free_pct):
                room, line = self.room(free_pct=free_pct)
                self.assertFalse(room)
                self.assertIn("; memory pressure normal, unknown free;", line)
                self.assertTrue(line.endswith("room: no (memory free unknown)"), line)

    def test_mac_flag_exit_codes(self):
        for room, code in ((True, 0), (False, 1)):
            out = io.StringIO()
            with mock.patch.object(scan, "mac_room", return_value=(room, "Mac: line")), contextlib.redirect_stdout(out):
                self.assertEqual(scan.main(["--mac"]), code)
            self.assertEqual(out.getvalue(), "Mac: line\n")


def utc(text):
    """The epoch time of a UTC time written `2026-01-16T17:30Z`."""
    return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()


def compact(record):
    """One transcript line as Claude Code writes it, with no spaces, so the scan's byte patterns match it."""
    return json.dumps(record, separators=(",", ":"))


def log_rows(*rows):
    """A status log of (date, who, event) rows."""
    return "## Status log\n\n| Date | Who | Event |\n|---|---|---|\n" + "".join(f"| {r[0]} | {r[1]} | {r[2]} |\n"
                                                                            for r in rows)


HANDBACK = {"type": "assistant", "message": {"role": "assistant", "content": [
    {"type": "tool_use", "id": "toolu_1", "name": "SubagentHandback", "input": {"message": "REPORT /1 PARTIAL"}}]}}
LISTING = {"type": "attachment", "attachment": {"type": "deferred_tools_record", "tools": [
    {"name": "SubagentHandback", "description": "x"}]}}  # the tool's listing: no hand-back


def woken(kind):
    """A message that reached an agent: its manager's ("coordinator"), a child's ("peer") or a background task's."""
    return {"type": "user", "origin": {"kind": kind}, "message": {"role": "user", "content": "x"}}


LONG_ID = "D-20251229-table-export"
# an order's block and rows, cut to the lines the scan reads
LONG = f"""# {LONG_ID}: export a table as a file

## Orders

### ORDER {LONG_ID}/2   from: ceo   to: cto

```
ORDER {LONG_ID}/2   from: ceo   to: cto
Objective:        Every table in Demo has an export button.
Acceptance criteria:
  2. The button's words are one setting. The CMO's copy (order D-20260115-new-words/3, due about 15:30Z) lands after this as its own change.
Constraints:      Size: yours. Today: ready estimate 2026-01-16T16:30Z (22:30 Dhaka), my pick, no data.
Report back with: REPORT format
```

{log_rows(
    ("2026-01-16", "ceo", "ORDER /2 to a CTO, logged before sending: the button today."),
    ("2026-01-16", "ceo", "NEXT: the CTO's list of tables; waits: D-20251229-table-export/2"),
    ("2026-01-16", "ceo", "RULING /2/1: CSV only (two-way)."),
    ("2026-01-16", "ceo", "RULING /2/7: PR 8 lands first, once its review passes."),
    ("2026-01-16", "ceo", "NEXT: the long tables, then the short ones on the CTO's word; waits: "
                          "D-20251229-table-export/2 (the first table)"))}"""


class Stalls(unittest.TestCase):
    """LATE, NO MANAGER and ENDED OPEN. Every directive and transcript is made
    up; transcript lines are written compact, as Claude Code writes them."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.projects = self.root / "projects"
        self.folder = self.projects / "session-1" / "subagents"
        self.folder.mkdir(parents=True)
        self.directives = self.root / "directives"
        self.directives.mkdir()
        (self.directives / "README.md").write_text(README)

    def agent(self, agent_id, role, prompt, written, *, parent=None, finished=True, stopped=False, records=()):
        meta = {"agentType": role, "description": "x"}
        if parent:
            meta["parentAgentId"] = parent
        if finished:
            meta["finished"] = True
        if stopped:
            meta["stoppedByUser"] = True
        (self.folder / f"agent-{agent_id}.meta.json").write_text(json.dumps(meta))
        log = self.folder / f"agent-{agent_id}.jsonl"
        lines = [{"type": "user", "message": {"role": "user", "content": prompt}}, *records]
        log.write_text("".join(compact(line) + "\n" for line in lines))
        os.utime(log, (written, written))

    def stalls(self, now, open_ids=("D-20251212-system", "D-20251218-held", "D-20251219-new")):
        return [(kind, d, n, since) for kind, d, n, since, _ in
                scan.stalled(self.directives, self.projects, now, list(open_ids))]

    def test_late_reads_the_latest_due_time_its_order_s_text_and_rows_log(self):
        """A deadline, target or ready estimate with a UTC time, in the order's block (with its date) or
        in a status-log row that names the order (a bare time is the row's day); a REPORT ... DONE or a CLOSED row
        ends it, a PARTIAL doesn't."""
        new = "D-20251219-new"
        block = (f"## Orders\n\n### ORDER {new}/1   from: ceo   to: cto\n\n```\nORDER {new}/1   from: ceo   to: cto\n"
                 "Objective:        x, after the CMO's copy (order D-20251218-held/3, due about 06:00Z)\n"
                 "Constraints:      M; deadline 2026-01-08T12:00Z.\n```\n\n"
                 f"### ORDER {new}/8.T2   from: ceo   to: cto\n\n```\nORDER {new}/8.T2   from: ceo   to: cto\n"
                 "Constraints:      deadline 2026-01-08 09:00Z.\n```\n\n")
        (self.directives / f"{new}.md").write_text(block + log_rows(
            ("2026-01-07", "ceo", "ORDERS /3 (Blue, A)-/5 to three ux-experts, logged before sending (base.txt). "
                                  "Ready estimate 10:00Z (16:00 Dhaka)."),
            ("2026-01-07", "ux-expert", "REPORT /4 Green DONE (100,000 tokens)"),
            ("2026-01-07", "ceo", "Noted: CLOSED /3 once its report is in."),  # mid-row: closes nothing
            ("2026-01-07", "ceo", "CLOSED /5: superseded by /6."),
            ("2026-01-08", "ceo", "ORDER /2 to the analyst, logged before sending: one note. About 1 hour; deadline "
                                  "13:30Z (19:30 Dhaka)."),
            ("2026-01-08", "ceo", f"Sent ORDER {new}/6   from: ceo   to: cto Objective: x Constraints: target "
                                  "2026-01-08 09:00Z. Report back with: REPORT format"),
            ("2026-01-08", "ceo", "RULING /6/1: the new deadline is 2026-01-08 15:00Z."),  # moves it on
            ("2026-01-08", "ceo", "ORDER /7 to a CTO: the read. Deadline 2026-01-08 11:00Z."),
            ("2026-01-08", "ceo", "To the Board: done soon (RULING /7/2, ceo-questions.md); its ready estimate 14:00Z."),
            ("2026-01-08", "ceo", "Quoted, not logged: \"ORDER /8 to a CTO, deadline 09:00Z\" and `ORDER /8, deadline "
                                  "09:00Z`."),
            ("2026-01-08", "ceo", "ORDER /9 to a CTO; deadline 08:00Z. ORDER D-20251218-held/3 to the cmo; deadline "
                                  "06:00Z."),
            ("2026-01-08", "cto", "REPORT /9 PARTIAL: most of it; the rest is DONE tomorrow."),
            ("2026-01-08", "ceo", "ORDER /10 to a CTO; deadline 07:00Z."),
            ("2026-01-08", "cto", "REPORT n/10 DONE (its short id)."),
            ("2026-01-08", "ceo", "ORDER /13 to a CTO; deadline 07:00Z.")))
        (self.directives / f"{new}-archive-1.md").write_text(
            f"# {new}: archive, part 1\n\n| Date | Who | Event |\n|---|---|---|\n"
            "| 2026-01-06 | ceo | ORDER /12 to a CTO; deadline 2026-01-06 10:00Z. |\n"
            "| 2026-01-06 | cto | REPORT /13 DONE, a day early. |\n")
        now = utc("2026-01-08T12:30Z")
        self.assertEqual(self.stalls(now), [
            ("LATE", new, "1", utc("2026-01-08T12:00Z")), ("LATE", new, "3", utc("2026-01-07T10:00Z")),
            ("LATE", new, "7", utc("2026-01-08T11:00Z")), ("LATE", new, "9", utc("2026-01-08T08:00Z")),
            ("LATE", new, "12", utc("2026-01-06T10:00Z"))])
        self.assertEqual(self.stalls(utc("2026-01-08T15:00Z"))[-2:], [  # 15:00Z has come: /2 and /6 too
            ("LATE", new, "9", utc("2026-01-08T08:00Z")), ("LATE", new, "12", utc("2026-01-06T10:00Z"))])
        self.assertIn(("LATE", new, "6", utc("2026-01-08T15:00Z")), self.stalls(utc("2026-01-08T15:00Z")))
        self.assertIn(("LATE", new, "2", utc("2026-01-08T13:30Z")), self.stalls(utc("2026-01-08T15:00Z")))
        self.assertEqual(self.stalls(utc("2026-01-06T09:59Z")), [])
        self.assertEqual(scan.format_stall(*scan.stalled(self.directives, self.projects, now, [new])[0]),
                         f"LATE {new}/1 since 2026-01-08 18:00 Dhaka: its deadline passed with no REPORT DONE logged")

    def test_a_row_may_name_its_order_by_the_slug_s_tail(self):
        """In its own log, a row may name an order by the slug's tail (`REPORT map-view/6 DONE`); another slug's tail
        names nothing there."""
        link = "D-20260113-demo-map-view"
        (self.directives / f"{link}.md").write_text(log_rows(
            ("2026-01-17", "ceo", f"ORDER {link}/6 to a CTO (S, read-only); deadline 01:00Z."),
            ("2026-01-17", "ceo", "ORDER /7 to a CTO; deadline 01:00Z."),
            ("2026-01-17", "ceo", "ORDER /8 to a CTO; deadline 01:00Z."),
            ("2026-01-17", "cto", "REPORT map-view/6 DONE (100,000 tokens), 00:30Z."),
            ("2026-01-17", "cto", "REPORT demo-map-view/7 DONE."),
            ("2026-01-17", "cto", "REPORT other-check/8 DONE (another directive's tail).")))
        self.assertEqual(self.stalls(utc("2026-01-17T02:00Z"), [link]),
                         [("LATE", link, "8", utc("2026-01-17T01:00Z"))])

    def test_an_order_whose_seniors_still_run_reads_late_once_its_ready_estimate_passes(self):
        """The ready estimate, 2026-01-16T16:30Z, passes while the order's CTO and Staff wait on their children, two
        Seniors run and T-5's Senior and reviewer have handed back."""
        readme = README + f"| [{LONG_ID}]({LONG_ID}.md) | Export | in-progress | 2025-12-29 |\n"
        (self.directives / "README.md").write_text(readme)
        (self.directives / f"{LONG_ID}.md").write_text(LONG)
        order = f"ORDER {LONG_ID}/2   from: ceo   to: cto\n{CANARY}"
        self.agent("c1", "cto", order, utc("2026-01-16T14:30:00Z"), records=[woken("coordinator")])
        self.agent("s1", "staff-engineer", f"Workstream WS-1 of RM-913. {CANARY}", utc("2026-01-16T17:25:00Z"),
                   parent="c1", records=[LISTING, woken("peer"), woken("task-notification"), woken("peer")])
        self.agent("e1", "senior-engineer", "Task T-1", utc("2026-01-16T17:50:00Z"), parent="s1", finished=False)
        self.agent("e4", "senior-engineer", "Task T-4", utc("2026-01-16T17:55:00Z"), parent="s1", finished=False)
        self.agent("e5", "senior-engineer", "Task T-5", utc("2026-01-16T17:15:00Z"), parent="s1", records=[HANDBACK])
        self.agent("r5", "code-reviewer", "Review T-5", utc("2026-01-16T17:20:00Z"), parent="s1", records=[HANDBACK])
        late = ("LATE", LONG_ID, "2", utc("2026-01-16T16:30Z"))
        for now, found in (("2026-01-16T16:29Z", []), ("2026-01-16T17:30Z", [late]), ("2026-01-16T18:00Z", [late])):
            self.assertEqual(self.stalls(utc(now), [LONG_ID]), found, now)
        # only Seniors run /2; its managers wait on them, so it isn't NO MANAGER
        self.assertEqual({role for d, n, role, _ in scan.agents(self.projects, utc("2026-01-16T18:00Z"))
                          if (d, n) == (LONG_ID, "2")}, {"senior-engineer"})
        for args, text in ((["--stalled"], f"LATE {LONG_ID}/2 since 2026-01-16 22:30 Dhaka: its ready estimate "
                                           "passed with no REPORT DONE logged\n"), ([], None)):
            out = io.StringIO()
            with mock.patch.object(scan, "DIRECTIVES", self.directives), \
                    mock.patch.object(scan, "projects_root", return_value=self.projects), \
                    mock.patch.object(scan, "mac_room", return_value=(True, "Mac: room: yes")), \
                    mock.patch.object(scan.time, "time", return_value=utc("2026-01-16T17:30Z")), \
                    contextlib.redirect_stdout(out):
                self.assertEqual(scan.main(args), 1)
            if text:
                self.assertEqual(out.getvalue(), text)
            else:
                self.assertIn(f"{LONG_ID}  WAITS | agents: /2 senior-engineer, /2 senior-engineer | ", out.getvalue())
                self.assertIn(f"\nLATE {LONG_ID}/2 since 2026-01-16 22:30 Dhaka: ", out.getvalue())
                self.assertIn(f", LATE {LONG_ID}/2\n", out.getvalue())  # last in "Start now"
            self.assertNotIn("CANARY", out.getvalue())

    def test_no_manager_when_the_manager_that_started_the_workers_is_gone(self):
        """A running Senior, reviewer or ux-expert whose manager handed back after it was last woken, or
        was stopped, with no manager on the order; a manager that ended its turn waiting on them still runs it."""
        new, now = "D-20251219-new", NOW
        lane = lambda n, role="cto": f"ORDER {new}/{n}   from: ceo   to: {role}"  # noqa: E731
        self.agent("c1", "cto", lane(1), now - 1800, records=[woken("coordinator"), HANDBACK])
        self.agent("e1", "senior-engineer", "Task T-1", now - 60, parent="c1", finished=False)
        self.agent("s2", "staff-engineer", lane(2, "staff-engineer"), now - 600, records=[LISTING, woken("peer")])
        self.agent("e2", "senior-engineer", "Task T-2", now - 60, parent="s2", finished=False)  # its manager waits
        self.agent("s3", "staff-engineer", lane(3, "staff-engineer"), now - 900, stopped=True)
        self.agent("r3", "code-reviewer", "Review T-3", now - 60, parent="s3", finished=False)
        self.agent("u4", "ux-expert", lane(4, "ux-expert"), now - 60, finished=False)  # the CEO's own
        self.agent("c5", "cto", lane(5), now - 1800, records=[HANDBACK])
        self.agent("e5", "senior-engineer", "Task T-5", now - 60, parent="c5", finished=False)
        self.agent("c5b", "cto", f"ORDER {new}/5 (resumed)   from: ceo   to: cto", now - 60, finished=False)
        self.agent("m6", "cmo", lane(6, "cmo"), now - 60, finished=False)
        self.agent("u6", "ux-expert", "Audit", now - 60, parent="m6", finished=False)
        self.agent("c7", "cto", lane(7), now - 300, records=[HANDBACK, woken("peer")])  # woken after it handed back
        self.agent("e7", "senior-engineer", "Task T-7", now - 60, parent="c7", finished=False)
        self.agent("c8", "cto", "ORDER D-20251216-old/1   from: ceo   to: cto", now - 300, records=[HANDBACK])
        self.agent("e8", "senior-engineer", "Task", now - 60, parent="c8", finished=False)  # a closed directive's
        self.assertEqual(self.stalls(now), [("NO MANAGER", new, "1", now - 1800), ("NO MANAGER", new, "3", now - 900)])
        self.assertTrue(scan.format_stall(*scan.stalled(self.directives, self.projects, now, [new])[0]).endswith(
            ": only senior-engineer run it, and the manager that started them has handed back or was stopped"))

    def test_ended_open_when_a_manager_ended_and_nobody_runs_its_open_order(self):
        """A cto or staff-engineer that handed back since it was last woken, was
        stopped, or went quiet with every agent under it for ALIVE_FOR, in the last ENDED_FOR, while its order has no
        DONE report or CLOSED row and no live agent runs it. One that ended its turn to wait on its children, or ended
        it under ALIVE_FOR ago, is parked: alive."""
        new, now = "D-20251219-new", NOW
        lane = lambda n, role="cto": f"ORDER {new}/{n}   from: ceo   to: {role}"  # noqa: E731
        (self.directives / f"{new}.md").write_text(log_rows(("2026-01-07", "cto", "REPORT /2 DONE"),
                                                            ("2026-01-07", "ceo", "CLOSED /9: folded into /1.")))
        self.agent("c1", "cto", lane(1), now - 1200, records=[woken("peer"), HANDBACK])
        self.agent("s2", "staff-engineer", lane(2, "staff-engineer"), now - 600, records=[HANDBACK])  # DONE logged
        self.agent("c3", "cto", lane(3), now - scan.ENDED_FOR - 60, records=[HANDBACK])  # before the window
        self.agent("c4", "cto", lane(4), now - 600, records=[HANDBACK, woken("peer")])
        self.agent("e4", "senior-engineer", "Task T-4", now - 60, parent="c4", finished=False)  # c4 waits on it
        self.agent("c5", "cto", lane(5), now - 600, records=[HANDBACK])
        self.agent("a5", "analyst", lane(5, "analyst"), now - 60, finished=False)  # another agent runs /5
        self.agent("c6", "cto", lane(6), now - 300, stopped=True)
        bg = Transcripts.background("b1")
        self.agent("c7", "cto", lane(7), now - 300, records=[bg, HANDBACK])  # still waits on its own background work
        self.agent("c8", "cto", lane(8), now - 60, finished=False)
        self.agent("s8", "staff-engineer", "Workstream WS-1", now - 300, parent="c8", records=[HANDBACK])
        self.agent("c9", "cto", lane(9), now - 300, records=[HANDBACK])  # its order is CLOSED
        self.agent("c10", "cto", lane(10), now - 3 * 3600)  # quiet, and so is all under it, past ALIVE_FOR
        self.agent("e10", "senior-engineer", "Task T-10", now - scan.ALIVE_FOR - 600, parent="c10")
        self.agent("c11", "cto", lane(11), now - 3 * 3600)  # parked: its Staff wrote 30 minutes ago
        self.agent("s11", "staff-engineer", "Workstream WS-1", now - 1800, parent="c11", records=[woken("peer")])
        self.agent("c12", "cto", lane(12), now - 600, records=[woken("coordinator")])  # ended its turn 10 minutes ago
        self.assertEqual(self.stalls(now), [("ENDED OPEN", new, "1", now - 1200), ("ENDED OPEN", new, "6", now - 300),
                                            ("ENDED OPEN", new, "10", now - scan.ALIVE_FOR - 600)])
        self.assertTrue(scan.format_stall(*scan.stalled(self.directives, self.projects, now, [new])[0]).endswith(
            ": its cto handed back, was stopped or went quiet with its agents for 2 hours, with no REPORT DONE "
            "logged, and no agent runs it"))

    def test_unanswered_asks_in_a_product_s_questions(self):
        """A NEEDS-CEO-NOW (10 minutes), NEEDS-CTO or QUESTION line, or a COORD line to the CEO (15
        minutes), that no RULING, HANDLED, ANSWER or ACTED line cites: by its ref (or word) and time, by an ask's own
        id, or by place ("on the line below"), in its page or the archive beside it. Made-up lines."""
        content = self.root / "workspaces" / "acme" / "content"
        content.mkdir(parents=True)
        (content / "ceo-questions.md").write_text("\n".join((
            "# ceo-questions", "", "## ORDER D-20251219-new/2   from: ceo   to: cto", "",
            "NEEDS-CEO-NOW /2.WS-1 -> the CEO, for a CTO   2026-01-16T18:40Z (WS-1 Staff, by date -u). x",
            "COORD /2.WS-1 -> /11.CTO, /11.WS-1   2026-01-16T18:40Z (WS-1 Staff; two-way). x",  # not to the CEO
            "NEEDS-CTO /2.WS-1 -> /2.CTO   2026-01-16T14:50Z (WS-1 Staff). x",
            "ANSWER /2.CTO 2026-01-16T15:30Z (CTO) to NEEDS-CTO /2.WS-1 14:50Z: x",
            "QUESTION /2.WS-1 -> /2.CTO   2026-01-16T13:10Z (WS-1 Staff). x",
            "COORD /2.CTO -> /2.WS-1   2026-01-16T13:20Z (CTO; answers QUESTION /2.WS-1 13:10Z, but a COORD isn't an "
            "answer). x",
            "COORD /2.CTO -> CEO, every Acme lane   2026-01-17T09:10Z (CTO). x",
            "QUESTION /3.CTO 2026-01-16T11:00Z (CTO). x",
            "RESUME POINT /3.CTO 2026-01-16T12:00Z (CTO). ACTED: /3.T1; QUESTION /3.CTO 11:00Z settled. x",
            "QUESTION D-20251219-new/1.CTO.q1   2026-01-15T09:05:00Z (CTO). x",
            "RULING D-20251219-new/1/6 2026-01-15T09:20Z (CEO), on q1 and q2:",
            "(1) QUESTION /1.CTO.q1: yes.",
            "RULING D-20251219-new/1/7 2026-01-15T09:30Z (CEO), on the line below: yes.",
            "QUESTION D-20251219-new/1.CTO.q2   2026-01-15T09:10:00Z (CTO). x",
            "NEEDS-CEO-NOW /4.WS-3 2026-01-14T22:1xZ (CTO). x",
            "CEO RULING D-20251219-new/4.WS-3/1 2026-01-14T22:2xZ, on NEEDS-CEO-NOW /4.WS-3 22:1xZ: approved.",
            "- **COORDINATION** (Staff to the CEO, 2026-01-11 22:00Z): x",
            "NEEDS-CEO-NOW /5.CTO 2026-01-16T10:00Z (CTO). x",
            "HANDLED (RULING /2/3) NEEDS-CEO-NOW /2.CTO 2026-01-16T09:00Z (CTO). x",
            "NEEDS-CEO-NOW /6.CTO 2026-01-17T09:55Z (CTO). x",
            "QUESTION /7.CTO 2026-01-17T09:50Z (CTO). x",
            "NEEDS-CEO-NOW /8.CTO with no time. x", "")))
        (content / "ceo-questions-archive.md").write_text(
            "## ORDER D-20251219-new/5\n\nCEO RULING /5/1 2026-01-16T10:05Z, on NEEDS-CEO-NOW /5.CTO 10:00Z: x\n")
        other = self.root / "workspaces" / "demo" / "content"
        other.mkdir(parents=True)
        (other / "ceo-questions.md").write_text("QUESTION /9.CTO 2026-01-17T08:00Z (CTO). x\n")
        pages = scan.question_pages(self.root / "workspaces")
        self.assertEqual([product for product, _ in pages], ["acme", "demo"])
        ten = utc("2026-01-17T10:00Z")
        self.assertEqual([ask[:5] for ask in scan.unanswered(pages, ten)], [
            ("acme", "NEEDS-CEO-NOW", "/2.WS-1", "2026-01-16T18:40Z", 5),
            ("acme", "QUESTION", "/2.WS-1", "2026-01-16T13:10Z", 9),
            ("acme", "COORD", "/2.CTO", "2026-01-17T09:10Z", 11),
            ("acme", "COORD", None, "2026-01-11T22:00Z", 21),
            ("demo", "QUESTION", "/9.CTO", "2026-01-17T08:00Z", 1)])
        later = [ask[4] for ask in scan.unanswered(pages, utc("2026-01-17T10:05Z"))]
        self.assertEqual(later, [5, 9, 11, 21, 24, 25, 1])  # /6's 10 minutes and /7's 15 have passed
        for now, found in (("2026-01-16T18:49:59Z", False), ("2026-01-16T18:50Z", True)):
            self.assertEqual(any(ask[4] == 5 for ask in scan.unanswered(pages, utc(now))), found, now)
        since = scan.unanswered(pages, ten)[0][5]
        self.assertEqual(since, utc("2026-01-16T18:50Z"))
        self.assertEqual(scan.format_unanswered(*scan.unanswered(pages, ten)[0]),
                         "UNANSWERED acme NEEDS-CEO-NOW /2.WS-1 2026-01-16T18:40Z since 2026-01-17 00:50 Dhaka: no "
                         "RULING, HANDLED, ANSWER or ACTED line cites it (ceo-questions.md:5)")
        (self.directives / "README.md").write_text("# Directives\n")
        for args, shown in (([], True), (["--stalled"], False)):
            out = io.StringIO()
            with mock.patch.object(scan, "DIRECTIVES", self.directives), \
                    mock.patch.object(scan, "WORKSPACES", self.root / "workspaces"), \
                    mock.patch.object(scan, "projects_root", return_value=self.projects), \
                    mock.patch.object(scan, "mac_room", return_value=(True, "Mac: room: yes")), \
                    mock.patch.object(scan.time, "time", return_value=ten), contextlib.redirect_stdout(out):
                self.assertEqual(scan.main(args), 1 if shown else 0)
            self.assertEqual("UNANSWERED acme COORD 2026-01-11T22:00Z since " in out.getvalue(), shown)
            if shown:
                self.assertIn("Start now (ceo.md, \"Capacity\"): UNANSWERED acme NEEDS-CEO-NOW /2.WS-1 "
                              "2026-01-16T18:40Z, UNANSWERED acme QUESTION /2.WS-1 2026-01-16T13:10Z, ",
                              out.getvalue())

    def test_only_a_reply_after_an_ask_that_names_it_answers_it(self):
        """A reply cites an ask by its ref and time, or its time to the
        second, or its ref, date and time, and only one written after it counts (by the reply's own dated time, else
        below it); the reply's own time cites nothing. An older ruling, or one on another ask at the same minute, or
        another day's, hides nothing, and nor does the ask's own line marking ACTED. Made-up lines."""
        content = self.root / "workspaces" / "acme" / "content"
        content.mkdir(parents=True)
        (content / "ceo-questions.md").write_text("\n".join((
            "## ORDER D-20251219-new/2   from: ceo   to: cto", "",
            "CEO RULING /9/1 2026-01-10T18:50Z, on NEEDS-CEO-NOW /2.WS-1 18:40Z: older, above it.",
            "NEEDS-CEO-NOW /2.WS-1 -> CEO   2026-01-16T18:40Z (WS-1 Staff, by date -u). x",
            "CEO RULING /9/2 18:40Z, on NEEDS-CEO-NOW /9.CTO 18:40Z: another ask at the same minute.",
            "HANDLED /2.WS-1 2026-01-16T18:40Z (WS-1 Staff): its own time, at the same minute.",
            "CEO RULING /9/3 2026-01-10T19:00Z, on NEEDS-CEO-NOW /2.WS-1 18:40Z: older, below it.",
            "CEO RULING /9/4 19:00Z, on NEEDS-CEO-NOW /2.WS-1 2026-01-10T18:40Z: another day's.",
            "QUESTION /4/2 2026-01-15T15:20:00Z (CTO, by date -u). x",
            "RULING D-20251219-new/4/3 2026-01-15T16:30Z (CEO), on QUESTION /4/2 15:20:00Z: yes.",
            "NEEDS-CEO-NOW /1.CTO -> CEO   2026-01-17T09:30:30Z (CTO, by date -u). x",
            "NEEDS-CEO-NOW /1.CTO -> CEO   2026-01-17T09:40:30Z (CTO, by date -u; replaces 09:30:30Z's). x",
            "CEO RULING /1/6 09:50:30Z, on NEEDS-CEO-NOW /1.CTO 09:40:30Z: yes (not 09:30:30Z's).",
            "ANSWER /11.CTO -> /11.WS-2   2026-01-16T16:00Z (CTO, by date -u). My answer to QUESTION /11.WS-2 of "
            "14:10:30Z (below) is yes.",
            "QUESTION /11.WS-2 -> /11.CTO   2026-01-16T14:10:30Z (WS-2 Staff, by date -u). x",
            "NEEDS-CEO-NOW /3.CTO 2026-01-16T20:00Z (CTO). x",
            "NEEDS-CEO-NOW /1.CTO.r26 -> CEO   2026-01-16T21:00Z (CTO, by date -u). x ACTED: /1.CTO.r25",  # itself
            "")))
        (content / "ceo-questions-archive.md").write_text(
            "## ORDER D-20251219-new/2\n\n"
            "CEO RULING /2/2 2026-01-10T18:50Z, on NEEDS-CEO-NOW /2.WS-1 18:40Z: older, in the archive.\n"
            "CEO HANDLED (20:05Z; RULING /3/1) NEEDS-CEO-NOW /3.CTO 2026-01-16T20:00Z: moved here by cq_archive.py.\n")
        pages = scan.question_pages(self.root / "workspaces")

        def asks():
            return [(kind, ref, line) for _, kind, ref, _, line, *_ in scan.unanswered(pages, utc("2026-01-17T10:00Z"))]
        self.assertEqual(asks(), [("NEEDS-CEO-NOW", "/2.WS-1", 4), ("NEEDS-CEO-NOW", "/1.CTO.r26", 17)])
        self.assertEqual(scan.cited("RULING /1/517:50Z (CEO), on NEEDS-CEO-NOW /1.CTO 17:50Z"),
                         ("RULING /1/5       (CEO), on NEEDS-CEO-NOW /1.CTO 17:50Z", None))
        self.assertIsNone(scan.cited("HANDLED (RULING /1/6 09:50:30Z) NEEDS-CEO-NOW /2.WS-1 2026-01-16T18:40Z")[1])
        self.assertEqual(scan.cited("ANSWER /2.CTO 2026-01-16T15:30Z (CTO)")[1], utc("2026-01-16T15:30Z"))
        self.assertEqual(scan.cited("RULING cfa/7/6 2026-01-15T08:0xZ (CEO)")[1], None)  # can't be ordered

    def test_an_unreadable_byte_or_impossible_date_is_skipped(self):
        """A page or log with a byte that isn't UTF-8, or a line dated 2026-02-31, never ends the scan."""
        content = self.root / "workspaces" / "acme" / "content"
        content.mkdir(parents=True)
        (content / "ceo-questions.md").write_bytes(
            b"NEEDS-CEO-NOW /1.CTO 2026-02-31T10:00Z (CTO). \xff x\n"
            b"RULING /1/1 2026-02-31T10:05Z (CEO), on NEEDS-CEO-NOW /1.CTO 10:00Z: x\n"
            b"NEEDS-CEO-NOW /2.CTO 2026-01-16T10:00Z (CTO). x\n")
        (content / "ceo-questions-archive.md").write_bytes(b"HANDLED \xfe\n")
        pages = scan.question_pages(self.root / "workspaces")
        self.assertEqual([ask[4] for ask in scan.unanswered(pages, utc("2026-01-17T10:00Z"))], [3])
        log = self.root / "board-desk.log"
        log.write_bytes(b"2026-01-17T10:00Z board desk: pushed: A-2: \xff\n"
                        b"2026-02-31T10:00Z board desk: pushed: A-1: updated\n")
        self.assertEqual(scan.desk(log, utc("2026-01-17T10:11Z"), True), [("DESK STALE", utc("2026-01-17T10:00Z"))])

    def test_only_the_ceo_answers_an_ask_to_the_ceo(self):
        """A NEEDS-CEO-NOW, or a QUESTION to the CEO, is answered only by a line the CEO wrote, and other asks by any
        reply: the CTO's own lines naming it answer nothing."""
        content = self.root / "workspaces" / "acme" / "content"
        content.mkdir(parents=True)
        ask = ("NEEDS-CEO-NOW COPY-CHECK D-20260118-two-lanes/1.WS-1+WS-2 workspaces/acme/content/"
               "draft-2.md  2026-01-18T07:10:30Z (CTO, by date -u; not urgent; RULING /1/2 (1) and (3)). A: x")
        theirs = [
            "- HANDLED (CEO RULING /1/2 (3); COPY-CHECK 07:10:30Z) Q /1.CTO 2026-01-18T01:40:30Z (CTO, by date -u; not "
            "urgent; adds to Q 00:50:30Z). x",
            "HANDLED (RULING /1/2 (3)) NEEDS-CEO-NOW COPY-CHECK 2026-01-18T07:10:30Z (CTO, by date -u): covered.",
            "ANSWER /1.WS-1 2026-01-18T07:30Z (WS-1 Staff, by date -u), on NEEDS-CEO-NOW COPY-CHECK 07:10:30Z: x",
            "QUESTION /1.CTO -> CEO   2026-01-18T09:00Z (CTO, by date -u). x",
            "ANSWER /1.CTO 2026-01-18T09:05Z (CTO), on QUESTION /1.CTO 09:00Z: settled myself.",
            "QUESTION /1.WS-1 -> /1.CTO   2026-01-18T09:10Z (WS-1 Staff). x",
            "ANSWER /1.CTO 2026-01-18T09:15Z (CTO), on QUESTION /1.WS-1 09:10Z: yes.",
            "NEEDS-CEO-NOW /1.WS-2 2026-01-18T10:00Z (WS-2 Staff). x",
            "RULING /1/9 (CTO), on the line above: the CTO's, by place."]
        page = content / "ceo-questions.md"
        page.write_text("\n".join(["## ORDER D-20260118-two-lanes/1   from: ceo   to: cto", ask] + theirs) + "\n")
        pages = scan.question_pages(self.root / "workspaces")
        late = utc("2026-01-18T14:05Z")
        self.assertEqual([ask[1:5] for ask in scan.unanswered(pages, late)], [
            ("NEEDS-CEO-NOW", None, "2026-01-18T07:10Z", 2), ("QUESTION", "/1.CTO", "2026-01-18T09:00Z", 6),
            ("NEEDS-CEO-NOW", "/1.WS-2", "2026-01-18T10:00Z", 10)])
        with mock.patch.object(scan, "by_ceo", return_value=True):  # before: every reply counted
            self.assertEqual(scan.unanswered(pages, late), [])
        with page.open("a") as out:
            out.write("HANDLED 2026-01-18T14:05:30Z (CEO, by date -u) NEEDS-CEO-NOW COPY-CHECK 2026-01-18T07:10Z.\n"
                      "RULING D-20260118-two-lanes/1/10 14:06Z (CEO), on QUESTION /1.CTO 09:00Z: yes.\n"
                      "CEO RULING D-20260118-two-lanes/1/11 (14:08:00Z, by date -u), on NEEDS-CEO-NOW /1.WS-2 10:00Z: "
                      "yes.\n")
        # the first two don't start with CEO, so they answer nothing
        self.assertEqual([ask[1:5] for ask in scan.unanswered(pages, utc("2026-01-18T14:10Z"))], [
            ("NEEDS-CEO-NOW", None, "2026-01-18T07:10Z", 2), ("QUESTION", "/1.CTO", "2026-01-18T09:00Z", 6)])
        with page.open("a") as out:
            out.write("CEO HANDLED (14:05:30Z, by date -u) NEEDS-CEO-NOW COPY-CHECK 2026-01-18T07:10Z.\n"
                      "CEO RULING D-20260118-two-lanes/1/10 (14:06:00Z, by date -u), on QUESTION /1.CTO 09:00Z: yes.\n")
        self.assertEqual(scan.unanswered(pages, utc("2026-01-18T14:10Z")), [])
        for line, mine in (("CEO RULING /1/2 (07:12:00Z, by date -u), on x", True),
                           ("RULING /7/2 11:30:30Z (CEO), on x", False),
                           ("HANDLED (CEO 17:20Z: x) NEEDS-CEO-NOW", False),
                           ("HANDLED (RULING /3/1) NEEDS-CEO-NOW /3.CTO 2026-01-16T20:00Z (CEO): x", False),
                           (theirs[0], False), (theirs[1], False), ("HANDLED (CEO RULING /1/2) x 00:40:30Z (CTO)", False),
                           ("RULING /3/1 (CEOs' x)", False), ("ANSWER /2.CTO 2026-01-16T15:30Z (CTO) to x", False)):
            self.assertEqual(scan.by_ceo(line), mine, line)
        # an agent's line with `(CEO` first in a parenthesis is never the CEO's, in an order's file or the product's
        agents = ("HANDLED (CEO 07:20Z RULING /1/2 (3)) COPY-CHECK 07:10:30Z Q /1.CTO (CTO, 07:25Z)",
                  "HANDLED (CEO, RULING /1/2 (3)) COPY-CHECK 07:10:30Z Q /1.CTO (CTO, 07:25Z)",
                  "HANDLED (CEO: see RULING /1/2) NEEDS-CEO-NOW /1.CTO 2026-01-18T07:10:30Z (CTO 07:25Z)")
        for line in agents:
            self.assertFalse(scan.by_ceo(line), line)
        order = content / "orders" / "D-20260118-two-lanes" / "2" / "ceo-questions.md"
        order.parent.mkdir(parents=True)
        ask = "NEEDS-CEO-NOW /2.CTO 2026-01-18T07:10:30Z (CTO). COPY-CHECK: x"
        for reply in agents:
            for where in (order, page):  # the agent's line in the order's file, or in the product's
                with self.subTest(reply=reply, where=where.name):
                    page.write_text("## ORDER D-20260118-two-lanes/1   from: ceo   to: cto\n"
                                    + (reply.replace("/1.CTO", "/2.CTO") + "\n" if where == page else ""))
                    order.write_text("# ORDER D-20260118-two-lanes/2 (cto, 2026-01-18)\n" + ask + "\n"
                                     + (reply.replace("/1.CTO", "/2.CTO") + "\n" if where == order else ""))
                    self.assertEqual([a[1:4] for a in scan.unanswered(scan.question_pages(self.root / "workspaces"),
                                                                       utc("2026-01-18T14:10Z"))],
                                     [("NEEDS-CEO-NOW", "/2.CTO", "2026-01-18T07:10Z")])
        with order.open("a") as out:
            out.write("CEO RULING D-20260118-two-lanes/2/1 (14:08:00Z, by date -u), "
                      "on NEEDS-CEO-NOW /2.CTO 07:10:30Z: x\n")
        self.assertEqual(scan.unanswered(scan.question_pages(self.root / "workspaces"), utc("2026-01-18T14:10Z")), [])

    def test_an_agent_line_glued_under_the_ceo_s_does_not_join_it(self):
        """A reply
        ends at the first line below it with a writer field of its own or a role word first, so an agent's line
        starting `(` or `1.`, appended right after a CEO ruling, doesn't join it; the CEO's own numbered line still
        does. Made-up lines."""
        order = self.root / "workspaces" / "acme" / "content" / "orders" / "D-20260118-glue" / "2"
        order.mkdir(parents=True)
        page = order / "ceo-questions.md"
        head = ("# ORDER D-20260118-glue/2 (cto, 2026-01-18)\n"
                "QUESTION /2.WS-1 -> CEO   2026-01-18T11:20Z (WS-1 Staff). x\n"
                "NEEDS-CEO-NOW /2.CTO 2026-01-18T11:30Z (CTO). x\n"
                "CEO RULING D-20260118-glue/2/1 (11:40:00Z, by date -u), on QUESTION /2.WS-1 11:20Z:\n"
                "(1) yes.\n")
        late = utc("2026-01-18T12:20Z")

        def asks():
            return [a[1:4] for a in scan.unanswered(scan.question_pages(self.root / "workspaces"), late)]
        for glued in ("(CTO, 11:45Z) on NEEDS-CEO-NOW /2.CTO 2026-01-18T11:30Z: covered.",
                      "1. on NEEDS-CEO-NOW /2.CTO 2026-01-18T11:30Z: covered (WS-1 Staff, by date -u).",
                      "(CEO RULING /2/1 (1)) NEEDS-CEO-NOW /2.CTO 2026-01-18T11:30Z: covered.",
                      "  CTO: on NEEDS-CEO-NOW /2.CTO 2026-01-18T11:30Z, done.",
                      "1. Staff: on NEEDS-CEO-NOW /2.CTO 2026-01-18T11:30Z, done.",
                      "(2) on NEEDS-CEO-NOW /2.CTO 2026-01-18T11:30Z: covered (CTO 11:45Z).",
                      # any case, a role and a word, any agent's id
                      "(cto, 11:45Z) on NEEDS-CEO-NOW /2.CTO 2026-01-18T11:30Z: covered.",
                      "1. on NEEDS-CEO-NOW /2.CTO 2026-01-18T11:30Z: covered (Senior engineer, 11:45Z).",
                      "(platform-engineer, 11:45Z) on NEEDS-CEO-NOW /2.CTO 2026-01-18T11:30Z: covered.",
                      "  cto: on NEEDS-CEO-NOW /2.CTO 2026-01-18T11:30Z, done.",
                      "(2) on NEEDS-CEO-NOW /2.CTO 2026-01-18T11:30Z: covered (ws-2 staff engineer).",
                      # a role word next to a comma or a
                      # time anywhere in a parenthesis, after a dash, or `The <role>:` first
                      "1. on NEEDS-CEO-NOW /2.CTO 2026-01-18T11:30Z: covered (by the CTO, 11:45Z).",
                      "1. on NEEDS-CEO-NOW /2.CTO 2026-01-18T11:30Z: covered (Staff engineer WS-1, 11:45Z).",
                      "1. on NEEDS-CEO-NOW /2.CTO 2026-01-18T11:30Z: covered (11:45Z, CTO).",
                      "1. on NEEDS-CEO-NOW /2.CTO 2026-01-18T11:30Z: covered - CTO 11:45Z.",
                      "  The CTO: on NEEDS-CEO-NOW /2.CTO 2026-01-18T11:30Z, done."):
            with self.subTest(glued=glued):
                page.write_text(head + glued + "\n")
                self.assertEqual(asks(), [("NEEDS-CEO-NOW", "/2.CTO", "2026-01-18T11:30Z")])
                with mock.patch.object(scan, "goes_on", lambda line: bool(scan.GOES_ON.match(line))):
                    self.assertEqual(asks(), [])  # by GOES_ON alone it would join the CEO's ruling
        page.write_text(head + "(2) NEEDS-CEO-NOW /2.CTO 11:30Z: approved.\n")  # the CEO's own numbered line
        self.assertEqual(asks(), [])

    def test_an_order_file_s_reply_answers_only_there_and_in_the_product_file(self):
        """Two
        directives' /1 asks with the same ref and minute; the CEO's reply in one's file answers that one only. A reply
        in an order's file still answers an ask in the product's own file, and one there still answers an order
        file's. Made-up lines."""
        content = self.root / "workspaces" / "acme" / "content"
        aaa, bbb = (content / "orders" / f"D-20260118-{d}" / "1" for d in ("aaa", "bbb"))
        for folder in (aaa, bbb):
            folder.mkdir(parents=True)
        (content / "ceo-questions.md").write_text(
            "## ORDER D-20260101-old/1   from: ceo   to: cto\n"
            "NEEDS-CTO /1.WS-1 -> /1.CTO   2026-01-18T11:20Z (WS-1 Staff). Answered from aaa's file.\n"
            "ANSWER /1.CTO 2026-01-18T11:45Z (CTO), on QUESTION /1.WS-2 11:40Z: yes, from the product file.\n")
        (aaa / "ceo-questions.md").write_text(
            "# ORDER D-20260118-aaa/1 (cto, 2026-01-18)\n"
            "NEEDS-CEO-NOW /1.CTO 2026-01-18T11:30Z (CTO). x\n"
            "CEO RULING D-20260118-aaa/1/1 (11:35:00Z, by date -u), on NEEDS-CEO-NOW /1.CTO 2026-01-18T11:30Z: yes.\n"
            "ANSWER /1.CTO 2026-01-18T11:25Z (CTO), on NEEDS-CTO /1.WS-1 2026-01-18T11:20Z: yes.\n")
        (bbb / "ceo-questions.md").write_text(
            "# ORDER D-20260118-bbb/1 (cto, 2026-01-18)\n"
            "NEEDS-CEO-NOW /1.CTO 2026-01-18T11:30Z (CTO). y\n"
            "QUESTION /1.WS-2 -> /1.CTO   2026-01-18T11:40Z (WS-2 Staff). Answered from the product file.\n")
        pages = scan.question_pages(self.root / "workspaces")
        late = utc("2026-01-18T12:20Z")
        self.assertEqual([(a[1], a[2], a[3], a[6]) for a in scan.unanswered(pages, late)],
                         [("NEEDS-CEO-NOW", "/1.CTO", "2026-01-18T11:30Z", "orders/D-20260118-bbb/1/ceo-questions.md")])
        with mock.patch.object(scan, "page_group", return_value=None):  # pooled
            self.assertEqual(scan.unanswered(pages, late), [])
        self.assertEqual([scan.page_group(page) for _, page in pages],
                         [None, "D-20260118-aaa/1", "D-20260118-bbb/1"])
        self.assertEqual(scan.page_group(aaa / "ceo-questions-archive.md"), "D-20260118-aaa/1")

    def test_order_files_are_read_pooled_and_placed(self):
        """The product's file plus two order files, one closed. Each
        uncited ask prints once, with its file's path; an ask cited in its own file (below it, or by place), or from
        another of the product's files or an archive by a dated time, doesn't; an undated reply in another file cites
        nothing; the product comes from the path. Made-up lines."""
        content = self.root / "workspaces" / "acme" / "content"
        (content / "orders" / "D-20260118-new" / "2").mkdir(parents=True)
        (content / "orders-closed" / "D-20260118-new" / "3").mkdir(parents=True)
        (content / "ceo-questions.md").write_text("\n".join((
            "## ORDER D-20260118-new/1   from: ceo   to: cto", "",
            "NEEDS-CEO-NOW /1.CTO 2026-01-18T08:00Z (CTO). Cited from /2's file, dated.",
            "NEEDS-CTO /1.WS-1 -> /1.CTO 2026-01-18T08:10Z (WS-1 Staff). Cited from /2's file, undated.",
            "CEO broadcast 2026-01-18T08:20Z: every lane, x.", "")))
        two = content / "orders" / "D-20260118-new" / "2" / "ceo-questions.md"
        two.write_text("\n".join((
            "# ORDER D-20260118-new/2 (cto, 2026-01-18)",
            "CEO RULING D-20260118-new/1/4 2026-01-18T08:05Z, on NEEDS-CEO-NOW /1.CTO 08:00Z: yes.",
            "ANSWER /1.CTO (CTO), on NEEDS-CTO /1.WS-1 08:10Z: undated, in another file.",
            "QUESTION /2.WS-1 -> /2.CTO   2026-01-18T09:00Z (WS-1 Staff). x",
            "ANSWER /2.CTO (CTO), on QUESTION /2.WS-1 09:00Z: below it, undated.",
            "NEEDS-CTO /2.WS-1 -> /2.CTO   2026-01-18T09:10Z (WS-1 Staff). Nobody cites it.",
            "CEO RULING D-20260118-new/2/1, on the line below: yes.",
            "NEEDS-CEO-NOW /2.CTO 2026-01-18T09:20Z (CTO). x", "")))
        three = content / "orders-closed" / "D-20260118-new" / "3" / "ceo-questions.md"
        three.write_text("\n".join((
            "# ORDER D-20260118-new/3 (cto, 2026-01-18)",
            "QUESTION /3.WS-1 -> /3.CTO   2026-01-18T09:30Z (WS-1 Staff). Answered in the old archive.",
            "NEEDS-CTO /3.WS-2 -> /3.CTO   2026-01-18T09:40Z (WS-2 Staff). Nobody cites it.", "")))
        (content / "ceo-questions-archive.md").write_text(
            "ANSWER /3.CTO 2026-01-18T09:35Z (CTO), on QUESTION /3.WS-1 09:30Z: yes.\n")
        (content / "orders" / "D-20260118-new" / "2" / "notes.md").write_text("NEEDS-CTO /2.x 2026-01-18T09:00Z. x\n")
        pages = scan.question_pages(self.root / "workspaces")
        self.assertEqual(pages, [("acme", content / "ceo-questions.md"), ("acme", two), ("acme", three)])
        now = utc("2026-01-18T12:00Z")
        self.assertEqual([(ask[0], ask[1], ask[2], ask[4], ask[6]) for ask in scan.unanswered(pages, now)], [
            ("acme", "NEEDS-CTO", "/1.WS-1", 4, "ceo-questions.md"),
            ("acme", "NEEDS-CTO", "/2.WS-1", 6, "orders/D-20260118-new/2/ceo-questions.md"),
            ("acme", "NEEDS-CTO", "/3.WS-2", 3, "orders-closed/D-20260118-new/3/ceo-questions.md")])
        self.assertTrue(scan.format_unanswered(*scan.unanswered(pages, now)[1]).endswith(
            "line cites it (orders/D-20260118-new/2/ceo-questions.md:6)"))
        self.assertEqual([scan.page_order(page) for _, page in pages], [None, "D-20260118-new/2", "D-20260118-new/3"])

    def test_misfiled_and_stray_fire_only_on_their_cases(self):
        """MISFILED is a line in an order's file whose word is
        followed by another order's ref (COORD, ANSWER and LANES lines go elsewhere on purpose; a short id like `cfa/7`
        can't be tied); STRAY is a ceo-questions.md outside the layout. Both print as warnings and start nothing.
        Made-up lines."""
        ws = self.root / "workspaces"
        content = ws / "acme" / "content"
        mine = content / "orders" / "D-20260118-new" / "2"
        mine.mkdir(parents=True)
        (content / "ceo-questions.md").write_text("\n".join((
            "## ORDER D-20260118-new/1   from: ceo   to: cto",
            "RULING D-20260118-new/2/1 2026-01-18T08:00Z (CEO): under /1's heading.",
            "RULING /1/2 2026-01-18T08:01Z (CEO): its own.", "")))
        (mine / "ceo-questions.md").write_text("\n".join((
            "# ORDER D-20260118-new/2 (cto, 2026-01-18)",
            "RULING D-20260118-new/2/1 2026-01-18T08:00Z (CEO): its own, by its full id.",
            "REPORT /2.WS-1.T-1 status: DONE: its own, by a short ref.",
            "RULING D-20260118-other/2/1 2026-01-18T08:02Z (CEO): another directive's /2.",
            "NEEDS-CEO-NOW /3.CTO 2026-01-18T08:03Z (CTO): another order of this directive.",
            "- **RESUME POINT /1.WS-1 2026-01-18T08:04Z (WS-1 Staff): a list item.",
            "COORD /2.CTO -> /3.CTO 2026-01-18T08:05Z (CTO): its own, to /3.",
            "COORD /3.CTO -> /2.CTO 2026-01-18T08:06Z (CTO): /3's, to the recipient's file.",
            "ANSWER /3.CTO 2026-01-18T08:07Z (CTO), on QUESTION /2.WS-1 08:00Z: in the asker's file.",
            "LANES /3 DEPLOY 2026-01-18T08:08Z: x",
            "RULING cfa/7/6 2026-01-18T08:09Z (CEO): a short id.", "")))
        pages = scan.question_pages(ws)
        self.assertEqual(scan.misfiled([page for page in pages if scan.page_order(page[1])]), [
            ("acme", "orders/D-20260118-new/2/ceo-questions.md", 4, "RULING", "D-20260118-other/2",
             "D-20260118-new/2"),
            ("acme", "orders/D-20260118-new/2/ceo-questions.md", 5, "NEEDS-CEO-NOW", "/3", "D-20260118-new/2"),
            ("acme", "orders/D-20260118-new/2/ceo-questions.md", 6, "RESUME POINT", "/1", "D-20260118-new/2")])
        self.assertEqual([line[2] for line in scan.misfiled(pages, every=True)], [2, 4, 5, 6, 8, 9])
        self.assertEqual(scan.stray_pages(ws), [])
        for place in ("acme/ceo-questions.md", "acme/content/x/ceo-questions.md",
                      "acme/content/orders/D-20260118-new/ceo-questions.md",
                      "acme/content/orders/D-20260118-new/2/T-1/ceo-questions.md",
                      "acme/content/orders-closed/D-20260118-new/2/x/ceo-questions.md",
                      "acme/content/orders/new/2/ceo-questions.md",
                      "acme/content/orders/D-20260118-new/two/ceo-questions.md"):
            (ws / place).parent.mkdir(parents=True, exist_ok=True)
            (ws / place).write_text("QUESTION /2.x 2026-01-18T08:00Z. x\n")
        (ws / "acme" / "content" / "orders" / "D-20260118-new" / "2" / "ceo-questions-archive.md").write_text("x\n")
        self.assertEqual(scan.stray_pages(ws), sorted([
            "acme/ceo-questions.md", "acme/content/x/ceo-questions.md",
            "acme/content/orders/D-20260118-new/ceo-questions.md",
            "acme/content/orders/D-20260118-new/2/T-1/ceo-questions.md",
            "acme/content/orders-closed/D-20260118-new/2/x/ceo-questions.md",
            "acme/content/orders/new/2/ceo-questions.md",
            "acme/content/orders/D-20260118-new/two/ceo-questions.md"]))
        (self.directives / "README.md").write_text("# Directives\n")
        out = io.StringIO()
        with mock.patch.object(scan, "DIRECTIVES", self.directives), mock.patch.object(scan, "WORKSPACES", ws), \
                mock.patch.object(scan, "projects_root", return_value=self.projects), \
                mock.patch.object(scan, "mac_room", return_value=(True, "Mac: room: yes")), \
                mock.patch.object(scan.time, "time", return_value=utc("2026-01-18T08:10Z")), \
                contextlib.redirect_stdout(out):
            self.assertEqual(scan.main([]), 0)
        self.assertIn("Warning: MISFILED acme orders/D-20260118-new/2/ceo-questions.md:5: a NEEDS-CEO-NOW line of /3, "
                      "in D-20260118-new/2's file", out.getvalue())
        self.assertIn("Warning: STRAY workspaces/acme/content/orders/new/2/ceo-questions.md: ", out.getvalue())
        self.assertEqual(out.getvalue().count("Warning: MISFILED"), 3)
        self.assertEqual(out.getvalue().count("Warning: STRAY"), 7)

    def test_no_manager_and_late_skip_a_finished_order_and_a_row_beats_the_block(self):
        """A stray Senior on an order with a DONE report or a CLOSED
        row isn't NO MANAGER (the heartbeat tells the CEO to log one); a ruling's new deadline, moved to an archive by
        a sweep, still beats the order block's first one."""
        new, now = "D-20251219-new", utc("2026-01-08T12:30Z")
        (self.directives / f"{new}.md").write_text(
            f"## Orders\n\n### ORDER {new}/14   from: ceo   to: cto\n\n```\nORDER {new}/14   from: ceo   to: cto\n"
            f"Constraints:      M; deadline 2026-01-08T10:00Z.\n```\n\n" + log_rows(
                ("2026-01-07", "cto", "REPORT /1 DONE"), ("2026-01-07", "ceo", "CLOSED /2: folded into /1.")))
        (self.directives / f"{new}-archive-1.md").write_text(
            f"# {new}: archive, part 1\n\n| Date | Who | Event |\n|---|---|---|\n"
            "| 2026-01-08 | ceo | RULING /14/1: the new deadline is 2026-01-08 16:00Z. |\n")
        for n in ("1", "2", "3"):  # /3 has no DONE or CLOSED row
            self.agent(f"c{n}", "cto", f"ORDER {new}/{n}   from: ceo   to: cto", now - 1800, records=[HANDBACK])
            self.agent(f"e{n}", "senior-engineer", f"Task T-{n}", now - 60, parent=f"c{n}", finished=False)
        self.assertEqual(self.stalls(now, [new]), [("NO MANAGER", new, "3", now - 1800)])
        self.assertIn(("LATE", new, "14", utc("2026-01-08T16:00Z")), self.stalls(utc("2026-01-08T16:00Z"), [new]))

    def test_nothing_stalled_prints_nothing(self):
        out = io.StringIO()
        with mock.patch.object(scan, "DIRECTIVES", self.directives), \
                mock.patch.object(scan, "projects_root", return_value=self.projects), \
                mock.patch.object(scan.time, "time", return_value=NOW), contextlib.redirect_stdout(out):
            self.assertEqual(scan.main(["--stalled"]), 0)
        self.assertEqual(out.getvalue(), "")


READ_LINE = "board desk: read: 0 answers kept (none), 0 changes not tied to the Board"
TODAY_LOG = [  # board-desk.log's lines in the desk's forms, each push's outcomes cut short
    "2026-01-17T08:55Z board desk: pushed: A-1: updated; Progress: pushed; Daily summaries: pushed",
    "2026-01-17T08:55Z board desk: read: 0 answers kept (none), 1 changes not tied to the Board",
    "2026-01-17T09:00Z board desk: hour 14:00-15:00, try 1: claude-sonnet-5-5, input 2, cache write 2,000, cache "
    "read 0, output 900; passed",
    "2026-01-17T09:00Z board desk: hour 14:00-15:00 Dhaka written: 10 items; spend read",
    "2026-01-17T09:05Z board desk: pushed: Progress: updated",
    f"2026-01-17T09:05Z {READ_LINE}",
    f"2026-01-17T09:25Z {READ_LINE}",
    "2026-01-17T10:10Z board desk: read failed: Notion 0: URLError",
    "2026-01-17T10:20Z board desk: pushed: A-3: updated",
    f"2026-01-17T10:20Z {READ_LINE}",
    "2026-01-17T10:30Z board desk: pushed: Progress: waits one read: edited in Notion",
]


class Reopened(unittest.TestCase):
    """An order reopened after its DONE row runs, so a NEXT row waiting on it reads WAITS."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.folder = self.root / "projects" / "session-1" / "subagents"
        self.folder.mkdir(parents=True)
        self.directives = self.root / "directives"
        self.directives.mkdir()
        (self.directives / "README.md").write_text(README)

    def state(self, *rows, running=(), now=None):
        """D-20251219-new's state at now (2026-01-07T12:00Z by default), its log the rows ((date, event)), with its
        NEXT row last, waiting on /5."""
        (self.directives / "D-20251219-new.md").write_text(log_rows(
            ("2026-01-05", "ceo", "ORDER /5 to a platform engineer"), *((day, "ceo", event) for day, event in rows),
            ("2026-01-07", "ceo", "NEXT: land /5; waits: /5, its fix round")))
        return dict((d, s) for d, s, _, _ in scan.scan(self.directives, list(running), TODAY, now or NOON))[
            "D-20251219-new"]

    def test_a_ruling_for_a_fix_round_after_done_reopens_the_order(self):
        done = ("2026-01-06", "REPORT /5 DONE: the branch at abc1234")
        for rows, state in (
                ((done, ("2026-01-07", "RULING /5 fix round 11:30Z: finding 1 first")), "WAITS"),
                ((done, ("2026-01-07", "CEO RULING /5/2 2026-01-07T10:05:00Z (fix round): finding 1")), "WAITS"),
                # no agent and over 2 hours old, so IDLE again
                ((done, ("2026-01-07", "RULING /5 fix round 09:59Z")), "IDLE"),
                ((done, ("2026-01-06", "RULING /5 fix round, sent at 23:50Z")), "IDLE"),  # yesterday's
                ((done, ("2026-01-07", "RULING /5 fix round")), "IDLE"),  # no time: a row this can't place
                ((done, ("2026-01-07", "RULING /5 fix round 13:00Z")), "IDLE"),  # a time after now
                ((done, ("2026-01-05", "RULING /5 fix round 11:30Z")), "IDLE"),  # two days ago
                ((done, ("2026-01-07", "RULING /5 fix round 11:30Z"),
                  ("2026-01-07", "REPORT /5 fix round DONE: def5678")), "IDLE"),
                ((done, ("2026-01-07", "RULING /5 fix round 11:30Z"), ("2026-01-07", "CLOSED /5: landed as is")),
                 "IDLE"),
                ((done, ("2026-01-07", "RULING /5 11:30Z: land it as it is")), "IDLE"),  # no fix round
                ((done, ("2026-01-07", 'RULING /5 11:30Z: "fix round" is a word I won\'t use')), "IDLE"),  # quoted
                # not the row's start
                ((done, ("2026-01-07", "Decided: RULING /5 fix round 11:30Z, to its engineer")), "IDLE"),
                # not done yet: nothing to reopen, no agent runs it
                ((("2026-01-07", "RULING /5 fix round 11:30Z"),), "IDLE"),
                ((done, ("2026-01-07", "RULING /4 fix round 11:30Z")), "IDLE"),  # another order
                ((("2026-01-06", "REPORT /5 PARTIAL: half"), ("2026-01-07", "RULING /5 fix round 11:30Z")), "IDLE")):
            with self.subTest(rows=rows):
                self.assertEqual(self.state(*rows), state)
        # the 2 hours run over midnight: sent 23:50Z the day before, read at 01:00Z
        late = ("2026-01-06", "RULING /5 fix round, sent at 23:50Z")
        self.assertEqual(self.state(done, late, now=datetime(2026, 1, 7, 1, 0, tzinfo=timezone.utc).timestamp()),
                         "WAITS")
        # an archive's DONE row counts first, and a reopened order runs for its directive's RUNNING too
        (self.directives / "D-20251219-new-archive-1.md").write_text(
            "# Archive\n" + log_rows(("2026-01-06", "ceo", "REPORT /5 DONE")).partition("\n\n")[2])
        (self.directives / "D-20251219-new.md").write_text(
            log_rows(("2026-01-07", "ceo", "RULING /5 fix round 11:30Z")))
        rows = dict((d, s) for d, s, _, _ in scan.scan(self.directives, [], TODAY, NOON))
        self.assertEqual(rows["D-20251219-new"], "RUNNING")

    def agent(self, agent_id, records, *, written=NOW - 60, stopped=False):
        meta = {"agentType": "platform-engineer", "description": "x", "finished": True}
        if stopped:
            meta["stoppedByUser"] = True
        (self.folder / f"agent-{agent_id}.meta.json").write_text(json.dumps(meta))
        log = self.folder / f"agent-{agent_id}.jsonl"
        prompt = {"type": "user", "message": {"role": "user", "content":
                                              f"ORDER D-20251219-new/5   from: ceo   to: platform-engineer\n{CANARY}"}}
        log.write_text("".join(compact(line) + "\n" for line in [prompt, *records]))
        os.utime(log, (written, written))
        return log

    def test_an_agent_its_manager_woke_after_its_hand_back_runs(self):
        """Its meta may still say finished; an api-request-blob record repeats the old hand-back call, which counts
        for nothing."""
        blob = {"type": "api-request-blob", "body": {"messages": [HANDBACK["message"]]}}
        agents = {
            "w1": ([HANDBACK, woken("coordinator")], {}, True),
            "w2": ([HANDBACK, woken("coordinator"), blob, blob], {}, True),
            "d1": ([HANDBACK, woken("coordinator"), blob, HANDBACK], {}, False),  # it handed back again
            "d2": ([woken("coordinator"), HANDBACK], {}, False),  # a message before its hand-back
            "d3": ([woken("coordinator")], {}, False),  # no hand-back before it: an end this can't place
            "d4": ([HANDBACK, woken("peer")], {}, False),  # a child's message isn't its manager's
            "d5": ([HANDBACK, LISTING, woken("coordinator")], {"stopped": True}, False),
            "d6": ([HANDBACK, woken("coordinator")], {"written": NOW - 3 * 3600}, False),  # quiet for 3 hours
            "d7": ([LISTING, woken("coordinator")], {}, False),  # the tool's listing is no hand-back
        }
        for agent_id, (records, extra, runs) in agents.items():
            log = self.agent(agent_id, records, **extra)
            with self.subTest(agent=agent_id):
                self.assertEqual(scan.resumed(log), agent_id in ("w1", "w2", "d5", "d6"))
        found = sorted(scan.agents(self.root / "projects", NOW))
        self.assertEqual(found, [("D-20251219-new", "5", "platform-engineer", 1)] * 2)
        (self.directives / "D-20251219-new.md").write_text(log_rows(
            ("2026-01-06", "ceo", "REPORT /5 DONE"), ("2026-01-07", "ceo", "NEXT: land /5; waits: /5")))
        self.assertEqual(scan.scan(self.directives, found, TODAY)[-1][:2], ("D-20251219-new", "WAITS"))
        self.assertEqual(scan.scan(self.directives, [], TODAY)[-1][:2], ("D-20251219-new", "IDLE"))
        self.assertFalse(scan.resumed(self.folder / "agent-missing.jsonl"))


class Desk(unittest.TestCase):
    """DESK STALE, read from the Board's desk's log: a push's outcomes never print."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.log = self.root / "board-desk.log"
        self.log.write_text("\n".join(TODAY_LOG) + "\n")

    def add(self, *lines):
        self.log.write_text(self.log.read_text() + "".join(line + "\n" for line in lines))

    def test_the_desk_s_own_log_and_read_job(self):
        import board_desk
        self.assertEqual(DESK_NAMES, (board_desk.LOG, board_desk.READ_LABEL))

    def test_a_desk_that_reads_prints_nothing(self):
        self.assertEqual(scan.desk(self.log, utc("2026-01-17T10:31Z"), True), [])  # a page that waits isn't held
        self.add(f"2026-01-17T10:40Z {READ_LINE}", f"2026-01-17T10:42Z {READ_LINE}", f"2026-01-17T10:44Z {READ_LINE}")
        self.assertEqual(scan.desk(self.log, utc("2026-01-17T10:50Z"), True), [])  # no push line since 10:30: all same
        self.assertEqual(scan.desk(self.log, utc("2026-01-18T10:31Z"), False), [])  # the desk is off

    def test_a_company_with_no_board_desk_is_never_stale(self):
        for desk, loaded in (({}, True), (None, False)):
            with mock.patch.object(scan, "BOARD_DESK", desk), \
                    mock.patch.object(scan.subprocess, "run", return_value=mock.Mock(returncode=0)):
                self.assertIs(DESK_JOB_LOADED(), loaded)

    def test_stale_ten_minutes_after_the_last_read_or_push_line(self):
        last = utc("2026-01-17T10:30Z")
        self.assertEqual(scan.desk(self.log, last + scan.DESK_QUIET, True), [])
        self.assertEqual(scan.desk(self.log, last + scan.DESK_QUIET + 1, True), [("DESK STALE", last)])
        self.add("2026-01-17T10:32Z board desk: read failed: Notion 0: URLError",
                 "2026-01-17T11:00Z board desk: hour 16:00-17:00 Dhaka written: 40 items")  # neither counts
        stale = scan.desk(self.log, utc("2026-01-17T11:01Z"), True)
        self.assertEqual(stale, [("DESK STALE", last)])
        self.assertEqual(scan.format_desk(*stale[0]), "DESK STALE since 2026-01-17 16:30 Dhaka: com.agentic-company."
                                                      "board-desk-read is loaded, but board-desk.log has no read or "
                                                      "push line in the last 10 minutes")
        missing = scan.desk(self.root / "none.log", last, True)
        self.assertEqual(missing, [("DESK STALE", None)])
        self.assertTrue(scan.format_desk(*missing[0]).startswith("DESK STALE: com.agentic-company.board-desk-read is "))
        self.assertEqual(scan.start_now([], [], desk_lines=missing), ["DESK STALE"])

    def test_only_the_log_s_end_is_read(self):
        hour = "2026-01-17T10:35Z board desk: hour 16:00-17:00 Dhaka written: 40 items"
        self.add(hour)
        with mock.patch.object(scan, "DESK_TAIL", len(hour) + 1):  # the 10:30 push line is above the tail
            self.assertEqual(scan.desk(self.log, utc("2026-01-17T10:36Z"), True), [("DESK STALE", None)])
        self.assertEqual(scan.desk(self.log, utc("2026-01-17T10:36Z"), True), [])

    def test_the_full_scan_prints_and_starts_it_and_stalled_doesn_t(self):
        directives = self.root / "directives"
        directives.mkdir()
        (directives / "README.md").write_text("# Directives\n")
        for args, code in (([], 1), (["--stalled"], 0)):
            out = io.StringIO()
            with mock.patch.object(scan, "DIRECTIVES", directives), mock.patch.object(scan, "DESK_LOG", self.log), \
                    mock.patch.object(scan, "desk_job_loaded", return_value=True), \
                    mock.patch.object(scan, "projects_root", return_value=self.root / "projects"), \
                    mock.patch.object(scan, "mac_room", return_value=(True, "Mac: room: yes")), \
                    mock.patch.object(scan.time, "time", return_value=utc("2026-01-17T10:41Z")), \
                    contextlib.redirect_stdout(out):
                self.assertEqual(scan.main(args), code)
            if args:
                self.assertEqual(out.getvalue(), "")
                continue
            lines = out.getvalue().splitlines()
            desk = [line for line in lines if line.startswith("DESK ")]
            self.assertEqual(desk, ["DESK STALE since 2026-01-17 16:30 Dhaka: com.agentic-company.board-desk-read is "
                                    "loaded, but board-desk.log has no read or push line in the last 10 minutes"])
            self.assertEqual(lines.index(desk[0]) + 1, lines.index("Mac: room: yes"))
            self.assertEqual(lines[-1], "Start now (ceo.md, \"Capacity\"): DESK STALE")


class BrokenSettings(unittest.TestCase):
    """A company.json that can't be read or used: the scan says so and goes on with the defaults."""

    OWN = {**company_config.DEFAULTS, "timezone": "Asia/Dhaka", "integrations": {
        "board_desk": {}, "board_email_events": {"from": "2026-01-19T17:00:00Z"}}}

    def broken(self):
        """(how company_config.load answers, what the fault says) for each way the file can be broken."""
        events = lambda value: {"return_value": {**self.OWN, "integrations": {"board_email_events": value}}}  # noqa: E731
        return (({"side_effect": json.JSONDecodeError("Expecting value", "{", 1)}, "JSONDecodeError: Expecting value"),
                ({"side_effect": PermissionError("no access")}, "PermissionError: no access"),
                ({"side_effect": TypeError("a list, no object")}, "TypeError: a list"),
                ({"return_value": {**self.OWN, "timezone": "Nowhere/None"}}, "ZoneInfoNotFoundError: "),
                ({"return_value": {**self.OWN, "timezone": 6}}, "TypeError: "),
                ({"return_value": {**self.OWN, "integrations": []}}, "AttributeError: "),
                (events(True), "TypeError: "), (events({}), "KeyError: 'from'"), (events({"from": "soon"}), "ValueError: "),
                (events({"from": None}), "AttributeError: "))

    def settings(self, load):
        with mock.patch.object(company_config, "load", **load):
            return scan.settings()

    def test_settings_that_can_be_read(self):
        zone, desk, start, fault = self.settings({"return_value": self.OWN})
        self.assertEqual((str(zone), desk, start, fault), ("Asia/Dhaka", {}, utc("2026-01-19T17:00Z"), ""))
        zone, desk, start, fault = self.settings({"return_value": company_config.DEFAULTS})
        self.assertEqual((str(zone), desk, start, fault), ("UTC", None, None, ""))

    def test_settings_that_can_t_be_read_are_the_defaults_and_why(self):
        for load, why in self.broken():
            with self.subTest(why=why, load=load):
                *defaults, fault = self.settings(load)
                self.assertEqual(defaults, [timezone.utc, None, None])
                self.assertTrue(fault.startswith(why), fault)

    def test_a_broken_file_doesn_t_stop_the_import(self):
        spec = importlib.util.spec_from_file_location("capacity_scan_again", scan.__file__)
        again = importlib.util.module_from_spec(spec)
        with mock.patch.object(company_config, "load", side_effect=json.JSONDecodeError("Expecting value", "{", 1)):
            spec.loader.exec_module(again)
        self.assertEqual((again.BOARD_TZ, again.BOARD_DESK, again.EMAIL_FROM), (timezone.utc, None, None))
        self.assertTrue(again.CONFIG_FAULT.startswith("JSONDecodeError: "), again.CONFIG_FAULT)

    def test_each_mode_goes_on_and_the_reports_say_so(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        (root / "README.md").write_text("# Directives\n")
        warning = "Warning: company.json can't be read or used (ValueError: x): times are UTC"
        for args, shown, told in (([], [f"{warning}, and the desk and email checks are off"], []),
                                  (["--stalled"], [], [warning]), (["--mac"], [], [])):
            out, err = io.StringIO(), io.StringIO()
            with mock.patch.object(scan, "CONFIG_FAULT", "ValueError: x"), mock.patch.object(scan, "BOARD_DESK", None), \
                    mock.patch.object(scan, "BOARD_TZ", timezone.utc), mock.patch.object(scan, "EMAIL_FROM", None), \
                    mock.patch.object(scan, "DIRECTIVES", root), \
                    mock.patch.object(scan, "projects_root", return_value=root), \
                    mock.patch.object(scan, "mac_room", return_value=(True, "Mac: room: yes")), \
                    mock.patch.object(scan.time, "time", return_value=utc("2026-01-17T10:41Z")), \
                    contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                self.assertEqual(scan.main(args), 0)
            for text, lines in ((out, shown), (err, told)):
                self.assertEqual([line for line in text.getvalue().splitlines() if "company.json" in line], lines, args)


GIT_ENV = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}


def commit(repo, when):
    """Commits everything in repo at the UTC time when (`2026-01-19T16:00:00Z`) and returns the commit."""
    env = {**GIT_ENV, "GIT_AUTHOR_DATE": when, "GIT_COMMITTER_DATE": when}
    config = ["-c", "user.name=t", "-c", "user.email=t@example.invalid", "-c", "commit.gpgsign=false"]
    for args in (["init", "-q"], ["add", "-A"], ["commit", "-q", "--allow-empty", "-m", f"at {when}"]):
        subprocess.run(["git", *config, "-C", str(repo), *args], check=True, capture_output=True, env=env, timeout=30)
    return subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], check=True, capture_output=True, text=True,
                          env=GIT_ENV, timeout=30).stdout.strip()


def big_picture(checked, product=None, flag="true", status="active"):
    return (f"---\ntitle: How it works\nowner: ceo\nstatus: {status}\nupdated: 2026-01-19\nrelated: []\n"
            f"big_picture: {flag}\n" + (f"product: {product}\n" if product else "") + "---\n\n# How it works\n\n"
            + (f"**Last checked:** {checked}\n\n" if checked is not None else "") + "## Live, off, being built\n")


class BigPicturePages(unittest.TestCase):
    """STALE PAGE: a `big_picture: true` page more than 7 days old, older than
    its product's newest DEPLOY DONE line or the newest system commit, or with no "Last checked" the scan can read."""

    TODAY = date(2026, 1, 19)

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.repo = Path(os.path.realpath(tmp.name))
        self.knowledge = self.repo / "knowledge"
        self.workspaces = self.repo / "workspaces"
        (self.knowledge / "company").mkdir(parents=True)
        self.content = self.workspaces / "acme" / "content"
        self.content.mkdir(parents=True)

    def page(self, text, rel="company/how-it-works.md"):
        (self.knowledge / rel).parent.mkdir(parents=True, exist_ok=True)
        (self.knowledge / rel).write_text(text)

    def stale(self):
        return scan.stale_pages(self.knowledge, self.workspaces, self.repo, self.TODAY)

    def test_more_than_7_days_old(self):
        self.page(big_picture("2026-01-11, against production `1a2b3c4d`", product="acme"))
        self.assertEqual(self.stale(), [("knowledge/company/how-it-works.md", "2026-01-11", ["more than 7 days old"])])
        self.page(big_picture("2026-01-12, 09:00 Dhaka", product="acme"))
        self.assertEqual(self.stale(), [])  # 7 days: not yet

    def test_a_product_page_older_than_its_newest_deploy(self):
        page = "engineering/architecture/acme-how-it-works.md"
        self.page(big_picture("2026-01-17, 16:00 Dhaka, against production `1a2b3c4d`",
                              product="acme"), page)
        (self.content / "ceo-questions.md").write_text(
            "DEPLOY DONE /12.CTO 2026-01-19T14:30:00Z (duty CTO, by date -u): X 2b3c4d5 in production\n"
            "COORD /5 2026-01-19T18:30Z: see DEPLOY DONE /12.CTO 2026-01-19T18:30:00Z\n"  # mid-line: not a deploy
            "DEPLOY DONE /12.CTO 2026-01-19T16:10:30Z (duty CTO, by date -u): X 3c4d5e6 in production\n")
        (self.content / "ceo-questions-archive.md").write_text(
            "DEPLOY DONE /1 2026-01-14T13:30:00Z (CTO, by date -u): X 5e6f7081\n")
        self.assertEqual(self.stale(), [(f"knowledge/{page}", "2026-01-17 16:00 Dhaka", [
            "acme's production deploy of 2026-01-19T16:10:30Z (DEPLOY DONE, ceo-questions.md:3) "
            "came after it"])])
        self.page(big_picture("2026-01-19, 22:11 Dhaka", product="acme"), page)  # 16:11Z
        self.assertEqual(self.stale(), [])
        self.page(big_picture("2026-01-19T16:10Z", product="acme"), page)  # its minute: to 16:10:59Z
        self.assertEqual(self.stale(), [])
        self.page(big_picture("2026-01-19T16:09Z", product="acme"), page)  # UTC, a minute before
        self.assertEqual(len(self.stale()), 1)
        self.page(big_picture("2026-01-19 16:10:29Z", product="acme"), page)  # seconds: as written
        self.assertEqual(len(self.stale()), 1)
        orders = self.content / "orders" / "D-20260118-new-tabs" / "12"
        orders.mkdir(parents=True)
        (orders / "ceo-questions.md").write_text("DEPLOY DONE /12 2026-01-19T20:00:00Z: an order's file\n")
        self.page(big_picture("2026-01-19, 23:59 Dhaka", product="acme"), page)  # 17:59Z
        self.assertEqual(self.stale()[0][2], [
            "acme's production deploy of 2026-01-19T20:00:00Z (DEPLOY DONE, "
            "orders/D-20260118-new-tabs/12/ceo-questions.md:1) came after it"])
        self.page(big_picture("2026-01-20, 03:00 Dhaka", product="acme"), page)  # 21:00Z
        self.assertEqual(self.stale(), [])
        (self.content / "ceo-questions-archive.md").write_text("DEPLOY DONE /2 2026-01-19T22:00:00Z: an archive\n")
        self.assertTrue(self.stale()[0][2][0].endswith("(DEPLOY DONE, ceo-questions-archive.md:1) came after it"))

    def test_a_page_refreshed_in_the_minute_of_its_deploy_is_current(self):
        """The page names the deploy a minute before its own "Last checked", and the DEPLOY DONE line's seconds fall in
        the check's minute."""
        page = "engineering/architecture/acme-how-it-works.md"
        self.page(big_picture("2026-01-19, 23:50 Dhaka, against `main` at `6f708192`, the code production runs "
                              "(deploy PR 3, 23:49).", product="acme"), page)
        (self.content / "ceo-questions.md").write_text(
            "DEPLOY DONE /12.CTO 2026-01-19T17:50:30Z (duty CTO; LANES DEPLOY START 17:45Z). X 6f70819 (PR 1)\n")
        self.assertEqual(self.stale(), [])
        self.page(big_picture("2026-01-19, 23:49 Dhaka (deploy PR 3).", product="acme"), page)
        self.assertEqual(len(self.stale()), 1)  # the minute before the deploy: behind

    def test_the_company_page_older_than_the_newest_system_change(self):
        (self.repo / "knowledge" / "company" / "note.md").write_text("a KB page\n")
        checked = commit(self.repo, "2026-01-16T10:00:00Z")
        (self.repo / "scripts").mkdir()
        (self.repo / "scripts" / "x.py").write_text("print(1)\n")
        landed = commit(self.repo, "2026-01-19T08:30:30Z")
        self.page(big_picture(f"2026-01-16, against `main` at `{checked[:8]}` (x)."))
        self.assertEqual(self.stale(), [("knowledge/company/how-it-works.md", "2026-01-16", [
            f"system change {landed[:8]} (2026-01-19T08:30:30Z) landed after it since `main` at {checked[:8]}"])])
        (self.repo / "knowledge" / "company" / "note.md").write_text("a KB page, changed\n")
        head = commit(self.repo, "2026-01-19T09:00:00Z")  # a KB commit: not a system change
        self.page(big_picture(f"2026-01-19, against `main` at `{head[:8]}`."))
        self.assertEqual(self.stale(), [])
        self.page(big_picture(f"2026-01-19, 14:00 Dhaka, against `main` at `{landed[:8]}`."))  # exact: by the commit
        self.assertEqual(self.stale(), [])
        self.page(big_picture("2026-01-18, against `main` at `abcdef12`."))  # a commit git doesn't know: by the date
        self.assertEqual(len(self.stale()), 1)
        self.page(big_picture("2026-01-19, 14:29 Dhaka."))  # 08:29Z, a minute before the change
        self.assertEqual(len(self.stale()), 1)
        self.page(big_picture("2026-01-19."))  # a date alone: a change that day isn't after it
        self.assertEqual(self.stale(), [])

    def test_a_last_checked_line_that_can_t_be_read_is_stale(self):
        why = ['its "Last checked" line can\'t be read: write "**Last checked:** <YYYY-MM-DD>, <HH:MM>, against ..."']
        for checked in (None, "soon", "2026-02-31, against `main`", "19 January"):
            with self.subTest(checked=checked):
                self.page(big_picture(checked, product="acme"))
                self.assertEqual(self.stale(), [("knowledge/company/how-it-works.md", None, why)])

    def test_a_page_with_no_product_other_than_the_company_s_is_stale(self):
        """Only knowledge/company/how-it-works.md is the system's."""
        page = "engineering/architecture/acme-how-it-works.md"
        self.page(big_picture("2026-01-19, 22:30 Dhaka, against `main` at `4d5e6f70`"), page)
        with mock.patch.object(scan, "git", side_effect=AssertionError("git ran")):  # no system change is read
            self.assertEqual(self.stale(), [(f"knowledge/{page}", "2026-01-19 22:30 Dhaka", [
                "it names no `product: <id>` (a workspaces/ folder), so the scan can't tell which deploys it "
                "describes: its owner adds one"])])

    def test_quiet(self):
        self.page(big_picture("2026-01-01", product="acme", flag="false"))
        self.page(big_picture("2026-01-01", product="acme", status="superseded"), "company/old.md")
        self.page(big_picture("2026-01-01", product="acme"), "research/note.md")
        self.page(big_picture("2026-01-18, 10:00 Dhaka", product="acme"), "company/fresh.md")
        self.assertEqual(self.stale(), [])

    def test_the_full_scan_lists_it_under_start_now(self):
        directives = self.repo / "directives"
        directives.mkdir()
        (directives / "README.md").write_text("| Id | Title | Status | Received |\n|---|---|---|---|\n")
        self.page(big_picture("2026-01-01, against production", product="acme"))
        out = io.StringIO()
        now = datetime(2026, 1, 19, 12, tzinfo=timezone.utc).timestamp()
        with mock.patch.object(scan, "DIRECTIVES", directives), mock.patch.object(scan, "KNOWLEDGE", self.knowledge), \
                mock.patch.object(scan, "WORKSPACES", self.workspaces), \
                mock.patch.object(scan, "projects_root", return_value=self.repo / "projects"), \
                mock.patch.object(scan, "mac_room", return_value=(True, "Mac: room: yes")), \
                mock.patch.object(scan.time, "time", return_value=now), contextlib.redirect_stdout(out):
            self.assertEqual(scan.main([]), 1)
        lines = out.getvalue().splitlines()
        self.assertIn("STALE PAGE knowledge/company/how-it-works.md: last checked 2026-01-01; more than 7 days old",
                      lines)
        self.assertEqual(lines[-1], "Start now (ceo.md, \"Capacity\"): STALE PAGE knowledge/company/how-it-works.md")


QA = "---\ntitle: Q&A\nowner: ceo\nstatus: active\nupdated: 2026-01-19\nrelated: []\n---\n\n## 2026-01-19\n\n{}"
ASKS = "---\ntitle: Asks\nowner: ceo\nstatus: active\nupdated: 2026-01-19\nrelated: []\n---\n\n## Open\n\n{}"


def directive(status="active"):
    return f"---\ntitle: A directive\nowner: ceo\nstatus: {status}\nupdated: 2026-01-19\nrelated: []\n---\n\n# D\n"


def table(*rows):
    """The directives table (README.md) with a row (id, status) each."""
    return "# Directives\n\n| Id | Title | Status | Received |\n|---|---|---|---|\n" + "".join(
        f"| [{d}]({d}.md) | A title | {status} | 2026-01-19 |\n" for d, status in rows)


class EmailsDue(unittest.TestCase):
    """EMAIL DUE: each answer, new or closed ask and new or done
    directive from EMAIL_FROM (2026-01-19T17:00Z here) on, until a logged email names its id in the subject."""

    NOW = datetime(2026, 1, 19, 18, tzinfo=timezone.utc).timestamp()

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.repo = Path(os.path.realpath(tmp.name))
        self.knowledge = self.repo / "knowledge"
        self.desk = self.knowledge / "company" / "board-desk"
        self.directives = self.knowledge / "board" / "directives"
        self.desk.mkdir(parents=True)
        self.directives.mkdir(parents=True)
        self.log = self.repo / "notify-log.jsonl"
        self.write("qa.md", QA.format("### Q-1 · current · a question · asked about 21:0x on 01-19\n"))
        self.write("asks.md", ASKS.format("### A-1 · open · b1 · D-20260101-old · asked 2026-01-19 10:00\n\n"
                                          "### B-7 D · open · two-way · D-20260101-old · asked 2026-01-18 06:35\n"))
        (self.directives / "D-20260101-old.md").write_text(directive())
        (self.directives / "D-20260102-shut.md").write_text(directive())
        (self.directives / "README.md").write_text(table(("D-20260101-old", "in-progress"),
                                                         ("D-20260102-shut", "done (2026-01-18)")))
        commit(self.repo, "2026-01-19T15:00:00Z")

    def write(self, name, text):
        (self.desk / name).write_text(text)

    def due(self, now=None):
        return scan.email_due(self.knowledge, now or self.NOW, self.log)

    def test_each_kind(self):
        self.write("qa.md", QA.format("### Q-1 · current · a question\n\n### Q-2 · current · another\n"))
        self.write("asks.md", ASKS.format("### A-1 · answered 2026-01-19 (in chat) · b1 · D-20260101-old\n\n"
                                          "### B-7 D · withdrawn 2026-01-19 · two-way\n\n### A-2 · open · b9\n"))
        (self.directives / "D-20260119-new.md").write_text(directive())
        (self.directives / "D-20260119-new-archive-1.md").write_text(directive("archived"))  # an archive: no event
        (self.directives / "README.md").write_text(table(
            ("D-20260101-old", "done (2026-01-19)"), ("D-20260102-shut", "done (2026-01-18)"),
            ("D-20260119-new", "open")))
        commit(self.repo, "2026-01-19T17:30:00Z")
        (self.directives / "D-20260119-gone.md").write_text(directive())  # not committed yet: counts
        (self.directives / "README.md").write_text(table(
            ("D-20260101-old", "done (2026-01-19)"), ("D-20260102-shut", "done (2026-01-18)"),
            ("D-20260119-new", "open"), ("D-20260119-gone", "cancelled (2026-01-19)")))
        self.assertEqual(self.due(), [("Q-2", "Answered"), ("A-1", "Ask closed"), ("B-7 D", "Ask closed"),
                                      ("A-2", "New ask"), ("D-20260101-old", "Directive done"),
                                      ("D-20260119-gone", "New directive"), ("D-20260119-gone", "Directive done"),
                                      ("D-20260119-new", "New directive")])

    def test_an_archived_directive_page_is_no_new_directive(self):
        """A page of a directive's old log rows, status archived; a real new directive beside it still counts."""
        (self.directives / "D-20260118-new-tabs-log-2026-01-18.md").write_text(directive("archived"))
        (self.directives / "D-20260119-new.md").write_text(directive())
        self.assertEqual(self.due(), [("D-20260119-new", "New directive")])

    def test_a_page_s_own_status_is_no_directive_done(self):
        """A directive is done by its row in the directives table, not by its page's front matter (kb_lint allows
        no done there)."""
        (self.directives / "D-20260101-old.md").write_text(directive("archived"))
        self.assertEqual(self.due(), [])

    def test_off_until_company_json_names_when_it_starts(self):
        (self.directives / "D-20260119-new.md").write_text(directive())
        with mock.patch.object(scan, "EMAIL_FROM", None):
            self.assertEqual(self.due(), [])
        self.assertEqual(self.due(), [("D-20260119-new", "New directive")])

    def test_events_before_17z_are_quiet(self):
        self.write("qa.md", QA.format("### Q-1 · current\n\n### Q-2 · current\n"))
        commit(self.repo, "2026-01-19T16:59:00Z")
        self.assertEqual(self.due(), [])
        self.write("qa.md", QA.format("### Q-1 · current\n\n### Q-2 · current\n\n### Q-3 · current\n"))
        self.assertEqual(self.due(datetime(2026, 1, 19, 16, 59, tzinfo=timezone.utc).timestamp()), [])  # not yet 17Z
        self.assertEqual(self.due(), [("Q-3", "Answered")])

    def test_an_answer_moved_to_an_archive_is_no_event(self):
        self.write("qa.md", QA.format(""))
        self.write("qa-archive-2026-01.md", QA.format("### Q-1 · current · a question\n"))
        self.assertEqual(self.due(), [])

    def test_an_id_named_in_a_subject_is_quiet(self):
        self.write("qa.md", QA.format("### Q-1 · current\n\n### Q-2 · current\n\n### Q-31 · current\n"))
        self.write("asks.md", ASKS.format("### A-1 · answered · b1\n\n### B-7 D · open · two-way\n\n### A-3 · open\n"))
        self.log.write_text("\n".join(json.dumps(line) for line in (
            {"time": "2026-01-19T14:50:00Z", "subject": "[CEO] New ask: before the base (A-3)"},  # too early to count
            {"time": "2026-01-19T17:10:00Z", "subject": "[CEO] Answered: two questions (Q-2, Q-3)"},
            {"time": "2026-01-19T17:11:00Z", "subject": "[CEO] Ask closed: the first ask (A-1)"})) + "\nnot json\n")
        self.assertEqual(self.due(), [("Q-31", "Answered"), ("A-3", "New ask")])  # Q-3 doesn't name Q-31
        with self.log.open("a") as log:
            log.write(json.dumps({"time": "2026-01-19T17:20:00Z", "subject": "[CEO] Answered (Q-31); New ask (A-3)"})
                      + "\n")
        self.assertEqual(self.due(), [])

    def test_an_email_between_the_base_and_17z_counts(self):
        """The base is the newest commit before 17:00Z (here 15:00Z), so an email sent at
        16:50Z about an entry committed at 17:10Z was sent and counts."""
        self.write("qa.md", QA.format("### Q-1 · current\n\n### Q-32 · current\n"))
        commit(self.repo, "2026-01-19T17:10:00Z")
        self.log.write_text(json.dumps({"time": "2026-01-19T16:50:30Z", "subject": "[CEO] Answered: x (Q-32)"}) + "\n")
        self.assertEqual(self.due(), [])

    def test_one_email_quiets_every_event_of_its_id_before_it(self):
        """Asked 23:3x Dhaka (17:3xZ), closed the same day, and one email at 17:35:30Z: no EMAIL DUE for A-7."""
        self.write("asks.md", ASKS.format(
            "### A-7 · answered 2026-01-19 (in chat) · b1 · D-20260101-old · asked 2026-01-19 23:3x\n\n"
            "### A-1 · open · b1 · D-20260101-old · asked 2026-01-19 10:00\n\n"
            "### B-7 D · open · two-way · D-20260101-old · asked 2026-01-18 06:35\n"))
        self.log.write_text(json.dumps({"time": "2026-01-19T17:35:30Z",
                                        "subject": "Ask closed: the old page (A-7)"}) + "\n")
        self.assertEqual(self.due(), [])
        self.log.write_text(json.dumps({"time": "2026-01-19T17:29:00Z", "subject": "x (A-7)"}) + "\n")
        self.assertEqual(self.due(), [("A-7", "New ask"), ("A-7", "Ask closed")])  # before 23:30 Dhaka: names none

    def test_an_event_after_the_email_needs_another(self):
        self.write("asks.md", ASKS.format("### A-1 · open\n\n### B-7 D · open\n\n"
                                          "### A-4 · answered 2026-01-19 23:45 · b1 · asked 2026-01-19 23:05\n"))
        self.log.write_text(json.dumps({"time": "2026-01-19T17:10:00Z", "subject": "[CEO] New ask: x (A-4)"}) + "\n")
        self.assertEqual(self.due(), [("A-4", "Ask closed")])  # closed 17:45Z, after the 17:10Z email
        with self.log.open("a") as log:
            log.write(json.dumps({"time": "2026-01-19T17:46:00Z", "subject": "[CEO] Ask closed: x (A-4)"}) + "\n")
        self.assertEqual(self.due(), [])
        self.write("asks.md", ASKS.format("### A-1 · open\n\n### B-7 D · open\n\n"
                                          "### A-4 · withdrawn 2026-01-20 · b1 · asked 2026-01-19 23:05\n"))
        self.assertEqual(self.due(), [("A-4", "Ask closed")])  # a date alone: its day's start, after both emails
        (self.directives / "D-20260119-new.md").write_text(directive())
        (self.directives / "README.md").write_text(table(
            ("D-20260101-old", "in-progress"), ("D-20260102-shut", "done (2026-01-18)"),
            ("D-20260119-new", "done (2026-01-20)")))
        self.log.write_text(json.dumps({"time": "2026-01-19T17:30:00Z", "subject": "New directive (D-20260119-new)"})
                            + "\n")
        self.assertEqual(self.due(), [("A-4", "New ask"), ("A-4", "Ask closed"),
                                      ("D-20260119-new", "Directive done")])  # received 01-19: quiet; done 01-20: due

    def test_an_order_or_a_shorter_id_doesn_t_name_it(self):
        """`D-…/15` is an order, not its directive; `B-7 D` is the
        ask's whole id, so `(B-7)` doesn't name it."""
        self.write("asks.md", ASKS.format("### A-1 · open\n\n### B-7 D · answered 2026-01-19 · two-way\n"))
        (self.directives / "README.md").write_text(table(("D-20260101-old", "done (2026-01-19)"),
                                                         ("D-20260102-shut", "done (2026-01-18)")))
        self.log.write_text(json.dumps({"time": "2026-01-19T17:30:00Z",
                                        "subject": "Order done (D-20260101-old/15); Ask closed (B-7)"}) + "\n")
        self.assertEqual(self.due(), [("B-7 D", "Ask closed"), ("D-20260101-old", "Directive done")])
        with self.log.open("a") as log:
            log.write(json.dumps({"time": "2026-01-19T17:31:00Z",
                                  "subject": "Directive done (D-20260101-old); Ask closed (B-7 D)"}) + "\n")
        self.assertEqual(self.due(), [])

    def test_an_ask_moved_to_its_archive_counts(self):
        """An ask closed and moved to asks-archive-*.md in one edit is closed;
        one written there at once is new too; one only moved is no event."""
        self.write("asks.md", ASKS.format("### A-5 · open\n"))
        self.write("asks-archive-2026-01.md", ASKS.format(
            "### A-1 · answered 2026-01-19 · b1\n\n### B-7 D · open · two-way\n\n### A-6 · withdrawn 2026-01-19\n"))
        self.assertEqual(self.due(), [("A-5", "New ask"), ("A-1", "Ask closed"), ("A-6", "New ask"),
                                      ("A-6", "Ask closed")])

    def test_no_desk_or_directives_reads_no_git(self):
        empty = self.repo / "elsewhere" / "knowledge"
        empty.mkdir(parents=True)
        with mock.patch.object(scan, "git", side_effect=AssertionError("git ran")):
            self.assertEqual(scan.email_due(empty, self.NOW, self.log), [])

    def test_the_full_scan_lists_it_under_start_now(self):
        self.write("qa.md", QA.format("### Q-1 · current\n\n### Q-2 · current\n"))
        directives = self.repo / "other-directives"
        directives.mkdir()
        (directives / "README.md").write_text("| Id | Title | Status | Received |\n|---|---|---|---|\n")
        out = io.StringIO()
        with mock.patch.object(scan, "DIRECTIVES", directives), mock.patch.object(scan, "KNOWLEDGE", self.knowledge), \
                mock.patch.object(scan, "main_checkout", return_value=self.repo / "main"), \
                mock.patch.object(scan, "projects_root", return_value=self.repo / "projects"), \
                mock.patch.object(scan, "mac_room", return_value=(True, "Mac: room: yes")), \
                mock.patch.object(scan.time, "time", return_value=self.NOW), contextlib.redirect_stdout(out):
            self.assertEqual(scan.main([]), 1)
        lines = out.getvalue().splitlines()
        self.assertIn("EMAIL DUE Q-2: Answered", lines)
        self.assertEqual(lines[-1], "Start now (ceo.md, \"Capacity\"): EMAIL DUE Q-2: Answered")


if __name__ == "__main__":
    unittest.main()
