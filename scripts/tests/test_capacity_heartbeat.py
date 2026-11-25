"""Tests for scripts/hooks/capacity_heartbeat.py.

The scan is faked or pointed at made-up directives in a temporary folder; the state file is always a temporary one,
so no test reads a live session log or writes the live heartbeat state."""

import io
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stderr
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "hooks"))

import capacity_heartbeat as hook  # noqa: E402
import capacity_scan  # noqa: E402  (on the path the hook set)

NOW = 1_800_000_000.0
BOARD_ORDER = "board-order"  # what capacity_scan reads as a wait on the Board's order to start marketing work
IDLE = ["D-20260101-first", "D-20260101-new"]


class Heartbeat(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = Path(self.tmp.name) / "workspaces" / "system" / "capacity-heartbeat.json"
        self.desk_log = Path(self.tmp.name) / "board-desk.log"  # missing, and the read job unloaded, unless a test says
        patches = [mock.patch.object(hook, "STATE", self.state), mock.patch.object(hook.time, "time", return_value=NOW),
                   mock.patch.object(capacity_scan, "DESK_LOG", self.desk_log),
                   mock.patch.object(capacity_scan, "desk_job_loaded", return_value=False),
                   mock.patch.object(capacity_scan, "email_due", return_value=[])]  # its own tests: git in a temp repo
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)

    def tearDown(self):
        self.tmp.cleanup()

    def run_hook(self, event=None, ids=IDLE, now=NOW):
        err = io.StringIO()
        stdin = io.StringIO(json.dumps(event if event is not None else {"transcript_path": ""}))
        with mock.patch.object(hook, "idle_ids", return_value=ids) as scan, mock.patch.object(hook.sys, "stdin", stdin), \
                mock.patch.object(hook.time, "time", return_value=now), redirect_stderr(err):
            code = hook.main()
        return code, err.getvalue(), scan

    def test_idle_work_blocks_the_stop_once(self):
        code, err, _ = self.run_hook()
        self.assertEqual(code, 2)
        self.assertIn("2 open directive(s) or backlog row(s) need you now: D-20260101-first, "
                      "D-20260101-new.", err)
        self.assertIn("python3 scripts/capacity_scan.py", err)
        self.assertEqual(json.loads(self.state.read_text()), {"at": NOW, "ids": IDLE})

    def test_never_while_a_stop_hook_already_continued_the_turn(self):
        code, err, scan = self.run_hook({"stop_hook_active": True})
        self.assertEqual((code, err), (0, ""))
        scan.assert_not_called()
        self.assertFalse(self.state.exists())

    def test_never_in_a_headless_jobs_run_as_the_ceo(self):
        # scripts/battery_alert.py's run sets the marker.
        with mock.patch.dict(os.environ, {"AGENTIC_COMPANY_JOB": "battery-alert"}):
            code, err, scan = self.run_hook()
        self.assertEqual((code, err), (0, ""))
        scan.assert_not_called()
        self.assertFalse(self.state.exists())
        self.assertEqual(self.run_hook()[0], 2)  # without it, the same ids nudge

    def test_nothing_idle(self):
        self.assertEqual(self.run_hook(ids=[])[:2], (0, ""))
        self.assertFalse(self.state.exists())

    def test_quiet_for_the_same_directives_then_again(self):
        self.assertEqual(self.run_hook()[0], 2)
        self.assertEqual(self.run_hook(now=NOW + 60)[:2], (0, ""))
        self.assertEqual(self.run_hook(ids=IDLE[:1], now=NOW + 120)[0], 0)  # fewer: still quiet
        self.assertEqual(self.run_hook(ids=IDLE + ["D-20260101-new-one"], now=NOW + 180)[0], 2)  # a new one: at once
        self.assertEqual(self.run_hook(ids=IDLE, now=NOW + 180 + hook.QUIET_FOR)[0], 2)

    def test_long_lists_are_cut(self):
        ids = [f"D-202601{n:02d}-x" for n in range(1, 13)]
        err = self.run_hook(ids=ids)[1]
        self.assertIn("12 open directive(s) or backlog row(s)", err)
        self.assertIn("D-20260108-x, +4.", err)
        self.assertNotIn("D-20260109-x", err)

    def test_a_broken_state_file_fires(self):
        self.state.parent.mkdir(parents=True)
        self.state.write_text("{not json")
        self.assertEqual(self.run_hook()[0], 2)

    def test_faults_let_the_stop_go(self):
        err = io.StringIO()
        with mock.patch.object(hook, "idle_ids", side_effect=RuntimeError("boom")), \
                mock.patch.object(hook.sys, "stdin", io.StringIO("{}")), redirect_stderr(err):
            self.assertEqual(hook.main(), 0)
        with mock.patch.object(hook.sys, "stdin", io.StringIO("not json")), redirect_stderr(err):
            self.assertEqual(hook.main(), 0)
        self.assertEqual(err.getvalue(), "")

    def test_a_fault_in_a_new_detector_drops_only_its_lines(self):
        """stalled() raising, or unanswered() or desk(), must not silence an IDLE directive."""
        root = Path(self.tmp.name)
        directives = root / "knowledge" / "board" / "directives"
        directives.mkdir(parents=True)
        (directives / "README.md").write_text(
            "| Id | Title | Status | Received |\n|---|---|---|---|\n"
            "| [D-20260101-a](D-20260101-a.md) | A | in-progress | 2026-01-12 |\n")
        (root / "projects").mkdir()
        event = json.dumps({"transcript_path": str(root / "projects" / "session.jsonl")})
        for broken in ("stalled", "unanswered", "desk"):
            with self.subTest(broken=broken):
                self.state.unlink(missing_ok=True)
                err = io.StringIO()
                with mock.patch.object(hook, "ROOT", root), mock.patch.object(hook.sys, "stdin", io.StringIO(event)), \
                        mock.patch.object(capacity_scan, broken, side_effect=RuntimeError("boom")), redirect_stderr(err):
                    code = hook.main()
                self.assertEqual(code, 2)
                self.assertIn("2 open directive(s), backlog row(s) or detector fault(s) need you now: D-20260101-a, "
                              f"DETECTOR FAULT {broken}.", err.getvalue())

    def test_a_detector_that_raises_is_named_and_fires_alone(self):
        """A broken detector isn't left broken unseen: its lines fall back to [], and its name goes into the nudge,
        alone too."""
        root = Path(self.tmp.name)
        (root / "knowledge" / "board" / "directives").mkdir(parents=True)
        (root / "knowledge" / "board" / "directives" / "README.md").write_text(
            "| Id | Title | Status | Received |\n|---|---|---|---|\n")
        (root / "projects").mkdir()
        log = str(root / "projects" / "session.jsonl")
        with mock.patch.object(hook, "ROOT", root), \
                mock.patch.object(capacity_scan, "unanswered", side_effect=RuntimeError("boom")), \
                mock.patch.object(capacity_scan, "desk", side_effect=OSError("boom")):
            self.assertEqual(hook.idle_ids(log, NOW), ["DETECTOR FAULT unanswered", "DETECTOR FAULT desk"])
        with mock.patch.object(hook, "ROOT", root):
            self.assertEqual(hook.idle_ids(log, NOW), [])  # nothing raised: nothing to name
        code, err, _ = self.run_hook(ids=["DETECTOR FAULT stalled"])
        self.assertEqual(code, 2)
        self.assertIn("1 open directive(s), backlog row(s) or detector fault(s) need you now: DETECTOR FAULT stalled.",
                      err)
        self.assertIn(" Detector(s) that raised an error (DETECTOR FAULT lines): stalled: their lines are missing "
                      "from this nudge; `python3 scripts/capacity_scan.py` shows the error", err)
        many = [f"D-202601{n:02d}-x" for n in range(1, 10)] + ["DETECTOR FAULT desk"]
        self.state.unlink()
        self.assertIn("(DETECTOR FAULT lines): desk:", self.run_hook(ids=many)[1])  # named past the 8 ids shown

    def test_a_company_json_that_cant_be_read_is_named_and_fires_alone(self):
        root = Path(self.tmp.name)
        (root / "knowledge" / "board" / "directives").mkdir(parents=True)
        (root / "knowledge" / "board" / "directives" / "README.md").write_text(
            "| Id | Title | Status | Received |\n|---|---|---|---|\n")
        (root / "projects").mkdir()
        log = str(root / "projects" / "session.jsonl")
        with mock.patch.object(hook, "ROOT", root), mock.patch.object(capacity_scan, "CONFIG_FAULT", "KeyError: 'x'"):
            self.assertEqual(hook.idle_ids(log, NOW), ["SETTINGS FAULT company.json"])
        with mock.patch.object(hook, "ROOT", root), mock.patch.object(capacity_scan, "CONFIG_FAULT", ""):
            self.assertEqual(hook.idle_ids(log, NOW), [])
        code, err, _ = self.run_hook(ids=["SETTINGS FAULT company.json"])
        self.assertEqual(code, 2)
        self.assertIn("1 open directive(s), backlog row(s) or settings fault need you now: SETTINGS FAULT company.json.",
                      err)
        self.assertIn(" company.json can't be read or used (SETTINGS FAULT): this nudge ran on the defaults", err)
        self.assertNotIn("can't be read or used", self.run_hook(ids=IDLE)[1])

    def test_real_scan_on_made_up_directives(self):
        root = Path(self.tmp.name)
        directives = root / "knowledge" / "board" / "directives"
        directives.mkdir(parents=True)
        (directives / "README.md").write_text(
            "| Id | Title | Status | Received |\n|---|---|---|---|\n"
            "| [D-20260101-a](D-20260101-a.md) | A | in-progress | 2026-01-12 |\n"
            "| [D-20260101-b](D-20260101-b.md) | B | open | 2026-01-13 |\n")
        (directives / "D-20260101-b.md").write_text("| 2026-01-07 | ceo | NEXT: wait for the reel; waits: 2099-01-01 |\n")
        projects = root / "projects"
        projects.mkdir()
        with mock.patch.object(hook, "ROOT", root):
            self.assertEqual(hook.idle_ids(str(projects / "session.jsonl"), NOW), ["D-20260101-a"])

    def test_a_wait_later_today_is_not_idle(self):
        """The heartbeat passes the scan the time, so `waits: <today> <a later time>Z` doesn't fire it."""
        root = Path(self.tmp.name)
        directives = root / "knowledge" / "board" / "directives"
        directives.mkdir(parents=True)
        (directives / "README.md").write_text(
            "| Id | Title | Status | Received |\n|---|---|---|---|\n"
            "| [D-20260101-b](D-20260101-b.md) | B | open | 2026-01-13 |\n")
        (directives / "D-20260101-b.md").write_text("| 2026-01-13 | ceo | NEXT: read it; waits: 2026-01-13 01:40Z |\n")
        (root / "projects").mkdir()
        at = datetime(2026, 1, 13, 0, 5, tzinfo=timezone.utc).timestamp()
        with mock.patch.object(hook, "ROOT", root):
            self.assertEqual(hook.idle_ids(str(root / "projects" / "session.jsonl"), at), [])
            self.assertEqual(hook.idle_ids(str(root / "projects" / "session.jsonl"), at + 100 * 60), ["D-20260101-b"])

    def test_marketing_waiting_on_the_board_s_order_is_not_idle(self):
        """Marketing starts work only on the Board's order; a row with `waits: none` still fires."""
        root = Path(self.tmp.name)
        directives = root / "knowledge" / "board" / "directives"
        directives.mkdir(parents=True)
        (directives / "README.md").write_text(
            "| Id | Title | Status | Received |\n|---|---|---|---|\n"
            "| [D-20260101-m](D-20260101-m.md) | M | in-progress | 2026-01-28 |\n"
            "| [D-20260101-n](D-20260101-n.md) | N | in-progress | 2026-01-29 |\n"
            "| [D-20260101-o](D-20260101-o.md) | O | in-progress | 2026-01-30 |\n")
        (directives / "D-20260101-m.md").write_text(f"| 2026-01-09 | ceo | NEXT: W04's plan; waits: {BOARD_ORDER} |\n")
        (directives / "D-20260101-n.md").write_text(f"| 2026-01-09 | ceo | NEXT: the next reel run; waits: /3, then {BOARD_ORDER} |\n")
        (directives / "D-20260101-o.md").write_text("| 2026-01-09 | ceo | NEXT: W04's plan; waits: none |\n")
        projects = root / "projects"
        projects.mkdir()
        with mock.patch.object(hook, "ROOT", root):
            self.assertEqual(hook.idle_ids(str(projects / "session.jsonl"), NOW), ["D-20260101-o"])

    def test_a_week_boundary_with_no_board_order_starts_nothing(self):
        """The day 2026-01-16 comes: marketing rows that wait on the Board's order stay quiet, a plain date
        fires."""
        root = Path(self.tmp.name)
        directives = root / "knowledge" / "board" / "directives"
        directives.mkdir(parents=True)
        (directives / "README.md").write_text(
            "| Id | Title | Status | Received |\n|---|---|---|---|\n"
            "| [D-20260101-m](D-20260101-m.md) | M | in-progress | 2026-01-28 |\n"
            "| [D-20260101-n](D-20260101-n.md) | N | in-progress | 2026-01-29 |\n"
            "| [D-20260101-o](D-20260101-o.md) | O | in-progress | 2026-01-30 |\n")
        (directives / "D-20260101-m.md").write_text(f"| 2026-01-09 | ceo | NEXT: W03's plan; waits: 2026-01-16, then {BOARD_ORDER} |\n")
        (directives / "D-20260101-n.md").write_text(f"| 2026-01-09 | ceo | NEXT: W03's read; waits: {BOARD_ORDER} for W03 |\n")
        (directives / "D-20260101-o.md").write_text("| 2026-01-09 | ceo | NEXT: the runbook check; waits: 2026-01-16 |\n")
        projects = root / "projects"
        projects.mkdir()
        with mock.patch.object(hook, "ROOT", root):
            for day, ids in ((15, []), (16, ["D-20260101-o"])):
                now = datetime(2026, 1, day, 0, 5, tzinfo=timezone.utc).timestamp()
                self.assertEqual(hook.idle_ids(str(projects / "session.jsonl"), now), ids, day)

    def test_a_waits_date_is_read_in_utc(self):
        """In Tokyo (UTC+9) the local date turns at 15:00Z; the logs' UTC one doesn't."""
        root = Path(self.tmp.name)
        directives = root / "knowledge" / "board" / "directives"
        directives.mkdir(parents=True)
        (directives / "README.md").write_text(
            "| Id | Title | Status | Received |\n|---|---|---|---|\n| [D-20260101-b](D-20260101-b.md) | B | open | 2026-01-13 |\n")
        (directives / "D-20260101-b.md").write_text("| 2026-01-08 | ceo | NEXT: read the reel; waits: 2026-01-09 |\n")
        projects = root / "projects"
        projects.mkdir()
        old = os.environ.get("TZ")
        os.environ["TZ"] = "Asia/Tokyo"
        time.tzset()
        try:
            with mock.patch.object(hook, "ROOT", root):
                for hour, minute, day, ids in ((18, 30, 8, []), (0, 5, 9, ["D-20260101-b"])):
                    now = datetime(2026, 1, day, hour, minute, tzinfo=timezone.utc).timestamp()
                    self.assertEqual(hook.idle_ids(str(projects / "session.jsonl"), now), ids, (day, hour))
        finally:
            if old is None:
                del os.environ["TZ"]
            else:
                os.environ["TZ"] = old
            time.tzset()

    def test_a_ceo_gate_review_running_is_not_idle(self):
        """The CEO's gate reviewer of an order is running work, where its prompt names the order only in its body."""
        root = Path(self.tmp.name)
        directives = root / "knowledge" / "board" / "directives"
        directives.mkdir(parents=True)
        (directives / "README.md").write_text(
            "| Id | Title | Status | Received |\n|---|---|---|---|\n"
            "| [D-20260101-a](D-20260101-a.md) | A | in-progress | 2026-01-12 |\n")
        (directives / "D-20260101-a.md").write_text("| 2026-01-13 | ceo | NEXT: land /46; waits: /46 (gate review) |\n")
        session = root / "projects" / "session-1"
        (session / "subagents").mkdir(parents=True)
        log = session / "subagents" / "agent-g1.jsonl"
        (session / "subagents" / "agent-g1.meta.json").write_text(json.dumps({"agentType": "code-reviewer"}))
        with mock.patch.object(hook, "ROOT", root):
            for prompt, ids in (('CEO gate review (ceo.md "System changes", step 4). The order (ORDER D-20260101-a/46, '
                                 'in the status log).', []),
                                ('CEO gate review. The row starts "ORDER D-20260101-a/46".', ["D-20260101-a"])):
                log.write_text(json.dumps({"type": "user", "message": {"role": "user", "content": prompt}}) + "\n")
                os.utime(log, (NOW - 60, NOW - 60))
                self.assertEqual(hook.idle_ids(str(session.with_suffix(".jsonl")), NOW), ids, prompt)

    def test_an_idle_backlog_row_stops_the_turn_as_an_idle_directive_does(self):
        """A backlog with a step no agent is on fires too. The same 30 minutes for the same set; a new idle row fires at once; a hard wait never."""
        root = Path(self.tmp.name)
        directives = root / "knowledge" / "board" / "directives"
        directives.mkdir(parents=True)
        (directives / "README.md").write_text(
            "| Id | Title | Status | Received |\n|---|---|---|---|\n"
            "| [D-20260101-b](D-20260101-b.md) | B | open | 2026-01-13 |\n")
        (directives / "D-20260101-b.md").write_text("| 2026-01-13 | ceo | NEXT: ship it; waits: b1 the post |\n")
        page = root / "knowledge" / "engineering" / "roadmaps" / "RM-901-acme-backlog.md"
        page.parent.mkdir(parents=True)
        front = "---\ntitle: x\nowner: cto\nstatus: active\nupdated: 2026-01-14\nrelated: []\nbacklog: true\n---\n\n"
        table = ("| # | Item | Status | Size | Door | Waits | Order |\n|---|---|---|---|---|---|---|\n"
                 "| 17 | The import | done | M | two-way | none | – |\n"
                 "| 18 | The export | not started | M | two-way | none | – |\n"
                 "| 19 | The price | not started | S | b3 | b3, the Board's yes | – |\n"
                 "| 20 | The report | in progress | S | two-way | 2099-01-01 | – |\n")
        page.write_text(front + table)
        (root / "projects").mkdir()
        event = json.dumps({"transcript_path": str(root / "projects" / "session.jsonl")})
        ref = "knowledge/engineering/roadmaps/RM-901-acme-backlog.md#"

        def stop(now):
            err = io.StringIO()
            with mock.patch.object(hook, "ROOT", root), mock.patch.object(hook.sys, "stdin", io.StringIO(event)), \
                    mock.patch.object(hook.time, "time", return_value=now), redirect_stderr(err):
                return hook.main(), err.getvalue()

        code, err = stop(NOW)
        self.assertEqual(code, 2)
        self.assertIn(f"1 open directive(s) or backlog row(s) need you now: {ref}18.", err)
        self.assertEqual(json.loads(self.state.read_text())["ids"], [f"{ref}18"])
        self.assertEqual(stop(NOW + 60), (0, ""))  # the same set, within 30 minutes
        page.write_text(front + table + "| 21 | The footer | not started | S | two-way | – | – |\n")
        code, err = stop(NOW + 120)  # a new idle row: at once
        self.assertEqual(code, 2)
        self.assertIn(f"{ref}18, {ref}21.", err)
        self.assertEqual(stop(NOW + 180), (0, ""))
        self.assertEqual(stop(NOW + 120 + hook.QUIET_FOR)[0], 2)  # the same set, 30 minutes on
        page.write_text(front + table.replace("| 18 | The export | not started", "| 18 | The export | done"))
        self.state.unlink()
        self.assertEqual(stop(NOW + 240 + hook.QUIET_FOR), (0, ""))  # only a hard wait and a date to come are left

    def test_designs_awaiting_sign_off_are_named_and_the_old_message_is_kept(self):
        """SIGNOFF lines count as IDLE ones and the message names them; with none, the message is the plain one."""
        err = self.run_hook()[1]
        self.assertEqual(err, "Capacity heartbeat: 2 open directive(s) or backlog row(s) need you now: "
                              "D-20260101-first, D-20260101-new. Run `python3 scripts/capacity_scan.py` and "
                              "start each IDLE and NO NEXT step now; for one that truly waits, write its NEXT row with "
                              "what it waits on, or have the backlog page's owner write it in the row's Waits (ceo.md, "
                              "\"Capacity\"). Then stop.\n")
        ids = [f"D-202601{n:02d}-x" for n in range(1, 9)] + ["DD-902", "DD-906"]
        self.state.unlink()
        code, err, _ = self.run_hook(ids=ids)
        self.assertEqual(code, 2)
        self.assertIn("10 open directive(s), backlog row(s) or design(s) need you now: ", err)
        self.assertIn("D-20260108-x, +2.", err)  # cut at 8, as before
        self.assertIn(" Design(s) awaiting your sign-off (SIGNOFF lines): DD-902, DD-906: decide each now, as ceo.md "
                      "\"When a report comes back\", step 3, says, or have its owner correct a status that is out of "
                      "date. Then stop.\n", err)
        self.assertEqual(json.loads(self.state.read_text())["ids"], ids)

    def test_a_design_awaiting_sign_off_alone_stops_the_turn(self):
        """On SIGNOFF lines alone it fires, at most once per 30
        minutes for the same set; a new one fires at once; another status, or none, never."""
        root = Path(self.tmp.name)
        directives = root / "knowledge" / "board" / "directives"
        directives.mkdir(parents=True)
        (directives / "README.md").write_text(
            "| Id | Title | Status | Received |\n|---|---|---|---|\n"
            "| [D-20260101-b](D-20260101-b.md) | B | open | 2026-01-13 |\n")
        (directives / "D-20260101-b.md").write_text("| 2026-01-15 | ceo | NEXT: ship it; waits: b1 the post |\n")
        designs = root / "knowledge" / "engineering" / "designs"
        designs.mkdir(parents=True)
        front = "---\ntitle: {}\nowner: staff-engineer\nstatus: draft\nupdated: 2026-01-15\nrelated: []\n---\n\n"
        (designs / "DD-902-landing.md").write_text(front.format("DD-902 Landing") + "**Design status:** awaiting-ceo (round 1)\n")
        (designs / "DD-903-seats.md").write_text(front.format("Seats") + "**Design status:** implementing (CEO approved)\n")
        (designs / "DD-904-none.md").write_text(front.format("No status") + "Text.\n")
        (designs / "DD-905-folder.md").mkdir()
        (root / "projects").mkdir()
        event = json.dumps({"transcript_path": str(root / "projects" / "session.jsonl")})

        def stop(now):
            err = io.StringIO()
            with mock.patch.object(hook, "ROOT", root), mock.patch.object(hook.sys, "stdin", io.StringIO(event)), \
                    mock.patch.object(hook.time, "time", return_value=now), redirect_stderr(err):
                return hook.main(), err.getvalue()

        code, err = stop(NOW)
        self.assertEqual(code, 2)
        self.assertIn("1 open directive(s), backlog row(s) or design(s) need you now: DD-902.", err)
        self.assertIn("(SIGNOFF lines): DD-902: decide each now", err)
        self.assertEqual(json.loads(self.state.read_text())["ids"], ["DD-902"])
        self.assertEqual(stop(NOW + 60), (0, ""))  # the same set, within 30 minutes
        (designs / "DD-906-staff.md").write_text(front.format("Staff") + "**Design status:** Awaiting-CEO (gist)\n")
        code, err = stop(NOW + 120)  # a new one: at once
        self.assertEqual(code, 2)
        self.assertIn("DD-902, DD-906.", err)
        self.assertEqual(stop(NOW + 180), (0, ""))
        self.assertEqual(stop(NOW + 120 + hook.QUIET_FOR)[0], 2)  # the same set, 30 minutes on
        for name in ("DD-902-landing.md", "DD-906-staff.md"):
            page = designs / name
            page.write_text(page.read_text().replace("awaiting-ceo", "implementing").replace("Awaiting-CEO", "merged"))
        self.state.unlink()
        self.assertEqual(stop(NOW + 240 + hook.QUIET_FOR), (0, ""))  # signed off: only the door's wait is left

    def test_the_board_s_answers_are_named_with_what_to_do(self):
        """ANSWER lines count as IDLE ones, after the designs."""
        code, err, _ = self.run_hook(ids=IDLE[:1] + ["DD-902", "ANSWER R-1 A-2"])
        self.assertEqual(code, 2)
        self.assertIn("Capacity heartbeat: 3 open directive(s), backlog row(s), design(s) or Board answer(s) need you now: "
                      "D-20260101-first, DD-902, ANSWER R-1 A-2.", err)
        self.assertIn("(SIGNOFF lines): DD-902: decide each now", err)
        self.assertTrue(err.endswith(" The Board's answer(s) no status-log row names (ANSWER lines): R-1 A-2: act on "
                                     "each now and quote its row, word for word with its R-id and ask id, in the directive's "
                                     "status log and the ask's Outcome, as ceo.md \"Keep a watcher\" says. Then stop.\n"),
                        err)
        self.state.unlink()
        err = self.run_hook(ids=["ANSWER R-2 A-3"])[1]
        self.assertIn("1 open directive(s), backlog row(s) or Board answer(s) need you now: ANSWER R-2 "
                      "A-3.", err)
        self.assertNotIn("SIGNOFF", err)

    def test_an_answer_no_status_log_row_names_alone_stops_the_turn(self):
        """The real scan of a made-up answers page fires on it alone, at most
        once per 30 minutes for the same set; once a status-log row names its R-id, never."""
        root = Path(self.tmp.name)
        board = root / "knowledge" / "board"
        (board / "directives").mkdir(parents=True)
        (board / "answers").mkdir()
        (board / "directives" / "README.md").write_text(
            "| Id | Title | Status | Received |\n|---|---|---|---|\n"
            "| [D-20260101-desk](D-20260101-desk.md) | Desk | open | 2026-01-16 |\n")
        log = board / "directives" / "D-20260101-desk.md"
        log.write_text("## Status log\n\n| Date | Who | Event |\n|---|---|---|\n"
                       "| 2026-01-15 | ceo | NEXT: ship it; waits: b1 the post |\n")
        (board / "answers" / "2026-W03.md").write_text(
            "---\ntitle: The Board's answers, 2026-W03\nowner: board\n---\n\n"
            "| R-id | Ask | Field | Edited (UTC) | Recorded (UTC) | Medium id | The Board's words |\n"
            "|---|---|---|---|---|---|---|\n| R-1 | A-2 | Your answer | 2026-01-16 20:00 | 2026-01-16 20:05 | p | Yes |\n")
        (root / "projects").mkdir()
        event = json.dumps({"transcript_path": str(root / "projects" / "session.jsonl")})

        def stop(now):
            err = io.StringIO()
            with mock.patch.object(hook, "ROOT", root), mock.patch.object(hook.sys, "stdin", io.StringIO(event)), \
                    mock.patch.object(hook.time, "time", return_value=now), redirect_stderr(err):
                return hook.main(), err.getvalue()

        code, err = stop(NOW)
        self.assertEqual(code, 2)
        self.assertIn("1 open directive(s), backlog row(s) or Board answer(s) need you now: ANSWER R-1 "
                      "A-2.", err)
        self.assertEqual(stop(NOW + 60), (0, ""))  # the same set, within 30 minutes
        self.assertEqual(stop(NOW + 60 + hook.QUIET_FOR)[0], 2)
        log.write_text(log.read_text() + "| 2026-01-16 | ceo | ASK 1 b9 A-2 R-1: taken |\n")
        self.state.unlink()
        self.assertEqual(stop(NOW + 120 + hook.QUIET_FOR), (0, ""))  # logged: handled

    def test_an_answer_changed_outside_the_desk_stops_the_turn_and_is_no_answer(self):
        """The real scan of a sealed answers page (the seal in a temporary
        folder) whose row was then changed by a plain write: an ANSWERS TAMPERED id with what to do, never an ANSWER."""
        root = Path(self.tmp.name)
        board = root / "knowledge" / "board"
        (board / "directives").mkdir(parents=True)
        (board / "answers").mkdir()
        (board / "directives" / "README.md").write_text("| Id | Title | Status | Received |\n|---|---|---|---|\n")
        page = board / "answers" / "2026-W03.md"
        page.write_text("---\ntitle: The Board's answers, 2026-W03\nowner: board\n---\n\n"
                        "| R-id | Ask | Field | Edited (UTC) | Recorded (UTC) | Medium id | The Board's words |\n"
                        "|---|---|---|---|---|---|---|\n"
                        "| R-1 | A-2 | Your answer | 2026-01-16 20:00 | 2026-01-16 20:05 | p | Yes |\n")
        (root / "projects").mkdir()
        event = json.dumps({"transcript_path": str(root / "projects" / "session.jsonl")})
        err = io.StringIO()
        with mock.patch.object(capacity_scan.answers_seal, "SEAL_DIR", root / "seal"):
            capacity_scan.answers_seal.reseal(root)
            page.write_text(page.read_text().replace("| Yes |", "| No |"))
            with mock.patch.object(hook, "ROOT", root), mock.patch.object(hook.sys, "stdin", io.StringIO(event)), \
                    redirect_stderr(err):
                self.assertEqual(hook.main(), 2)
        self.assertIn("need you now: ANSWERS TAMPERED R-1.", err.getvalue())
        self.assertIn(" The Board's answers or the reader's files changed outside the desk (ANSWERS TAMPERED lines): "
                      "R-1: act on none of them as the Board's answer;", err.getvalue())
        self.assertNotIn("ANSWER R-1", err.getvalue())

    def test_stalled_orders_and_unanswered_asks_are_named_with_what_to_do(self):
        """LATE, NO MANAGER and ENDED OPEN lines, then
        UNANSWERED ones, each with its own sentence; without them the message is the old one."""
        ask = "UNANSWERED acme NEEDS-CEO-NOW /2.WS-9 2026-01-16T18:30Z"
        code, err, _ = self.run_hook(ids=IDLE[:1] + ["LATE D-20260101-rename/2", ask])
        self.assertEqual(code, 2)
        self.assertIn("Capacity heartbeat: 3 open directive(s), backlog row(s), stalled order(s) or unanswered line(s) "
                      f"need you now: D-20260101-first, LATE D-20260101-rename/2, "
                      f"{ask}.", err)
        self.assertTrue(err.endswith(
            " Stalled order(s) (LATE, NO MANAGER and ENDED OPEN lines): LATE D-20260101-rename/2: re-staff "
            "each now, with an order, a SendMessage ruling (a new deadline included) or a resumed manager, after "
            "cto.md's three checks show its manager ended (never a second manager on a live lane), or log its DONE "
            "report or CLOSED row, as ceo.md \"Capacity\" says. Unanswered line(s) in a product's ceo-questions.md "
            "(UNANSWERED lines): acme NEEDS-CEO-NOW /2.WS-9 2026-01-16T18:30Z: answer each now with a RULING or "
            "ANSWER line that names its word, order and time, or write a HANDLED line for it, as ceo.md \"Capacity\" "
            "says. Then stop.\n"), err)
        self.state.unlink()
        err = self.run_hook(ids=IDLE)[1]
        self.assertNotIn("Stalled", err)
        self.assertNotIn("Unanswered", err)
        self.assertTrue(err.endswith("(ceo.md, \"Capacity\"). Then stop.\n"), err)

    def test_a_late_order_or_an_unanswered_ask_alone_stops_the_turn(self):
        """The real scan of a made-up directive whose ORDER's deadline passed, and of a made-up product's questions:
        it fires, stays quiet for 30 minutes on the same set, and stops firing once the REPORT DONE row and the
        RULING are logged."""
        root = Path(self.tmp.name)
        directives = root / "knowledge" / "board" / "directives"
        directives.mkdir(parents=True)
        (directives / "README.md").write_text(
            "| Id | Title | Status | Received |\n|---|---|---|---|\n"
            "| [D-20260101-x](D-20260101-x.md) | X | open | 2026-01-16 |\n")
        log = directives / "D-20260101-x.md"
        late = datetime.fromtimestamp(NOW - 3600, timezone.utc)
        log.write_text("## Status log\n\n| Date | Who | Event |\n|---|---|---|\n"
                       f"| {late:%Y-%m-%d} | ceo | ORDER /2 to a CTO; deadline {late:%Y-%m-%d %H:%M}Z. |\n"
                       "| 2026-01-15 | ceo | NEXT: the CTO's report; waits: 2099-01-01 |\n")
        content = root / "workspaces" / "acme" / "content"
        content.mkdir(parents=True)
        questions = content / "ceo-questions.md"
        asked = datetime.fromtimestamp(NOW - 1200, timezone.utc)
        questions.write_text(f"NEEDS-CEO-NOW /2.CTO {asked:%Y-%m-%dT%H:%M}Z (CTO). x\n")
        (root / "projects").mkdir()
        event = json.dumps({"transcript_path": str(root / "projects" / "session.jsonl")})

        def stop(now):
            err = io.StringIO()
            with mock.patch.object(hook, "ROOT", root), mock.patch.object(hook.sys, "stdin", io.StringIO(event)), \
                    mock.patch.object(hook.time, "time", return_value=now), redirect_stderr(err):
                return hook.main(), err.getvalue()

        code, err = stop(NOW)
        self.assertEqual(code, 2)
        self.assertIn("need you now: LATE D-20260101-x/2, UNANSWERED acme NEEDS-CEO-NOW /2.CTO "
                      f"{asked:%Y-%m-%dT%H:%M}Z.", err)
        self.assertEqual(stop(NOW + 60), (0, ""))  # the same set, within 30 minutes
        self.assertEqual(stop(NOW + 60 + hook.QUIET_FOR)[0], 2)
        log.write_text(log.read_text() + f"| {late:%Y-%m-%d} | cto | REPORT /2 DONE |\n")
        questions.write_text(questions.read_text() + f"RULING /2/1 (CEO), on NEEDS-CEO-NOW /2.CTO {asked:%H:%M}Z: x\n")
        self.state.unlink()
        # a writer's name after the ruling answers nothing: the line starts with the CEO's word
        code, err = stop(NOW + 120 + hook.QUIET_FOR)
        self.assertEqual(code, 2)
        self.assertIn("UNANSWERED acme NEEDS-CEO-NOW /2.CTO", err)
        self.assertNotIn("LATE", err)
        questions.write_text(questions.read_text() + f"CEO RULING /2/1, on NEEDS-CEO-NOW /2.CTO {asked:%H:%M}Z: x\n")
        self.state.unlink()
        self.assertEqual(stop(NOW + 180 + hook.QUIET_FOR), (0, ""))  # logged and answered

    def test_an_order_file_s_ask_alone_stops_the_turn(self):
        """The real scan sees an ask in an order's own file,
        content/orders/<directive id>/<n>/ceo-questions.md, with no product file beside it, and a CEO's ruling in the
        product file, dated, answers it."""
        root = Path(self.tmp.name)
        directives = root / "knowledge" / "board" / "directives"
        directives.mkdir(parents=True)
        (directives / "README.md").write_text("| Id | Title | Status | Received |\n|---|---|---|---|\n")
        content = root / "workspaces" / "acme" / "content"
        folder = content / "orders" / "D-20260101-x" / "2"
        folder.mkdir(parents=True)
        asked = datetime.fromtimestamp(NOW - 1200, timezone.utc)
        (folder / "ceo-questions.md").write_text(
            f"# ORDER D-20260101-x/2 (cto, {asked:%Y-%m-%d})\nNEEDS-CEO-NOW /2.CTO {asked:%Y-%m-%dT%H:%M}Z (CTO). x\n")
        (root / "projects").mkdir()
        event = json.dumps({"transcript_path": str(root / "projects" / "session.jsonl")})

        def stop(now):
            err = io.StringIO()
            with mock.patch.object(hook, "ROOT", root), mock.patch.object(hook.sys, "stdin", io.StringIO(event)), \
                    mock.patch.object(hook.time, "time", return_value=now), redirect_stderr(err):
                return hook.main(), err.getvalue()

        code, err = stop(NOW)
        self.assertEqual(code, 2)
        self.assertIn(f"need you now: UNANSWERED acme NEEDS-CEO-NOW /2.CTO {asked:%Y-%m-%dT%H:%M}Z.", err)
        (content / "ceo-questions.md").write_text(
            f"CEO RULING D-20260101-x/2/1 {asked:%Y-%m-%dT%H:%M}Z, on NEEDS-CEO-NOW /2.CTO {asked:%H:%M}Z: x\n")
        self.state.unlink()
        self.assertEqual(stop(NOW + 60), (0, ""))

    def test_the_desk_s_line_is_named_with_what_to_do(self):
        """DESK STALE gets its own sentence, last."""
        code, err, _ = self.run_hook(ids=["DESK STALE"])
        self.assertEqual(code, 2)
        self.assertIn("Capacity heartbeat: 1 open directive(s), backlog row(s) or desk line(s) need you now: "
                      "DESK STALE.", err)
        self.assertTrue(err.endswith(
            "(ceo.md, \"Capacity\"). The Board's desk has stopped reading (DESK STALE): find in board-desk.log why the "
            "read job logs no read, as ceo.md \"Capacity\" says. Then stop.\n"), err)

    def test_a_stale_desk_alone_stops_the_turn(self):
        """The real scan, with the desk's read job loaded and its log's last line of 2026-01-17 10:30Z: quiet while the
        desk reads, it fires 10 minutes on, stays quiet for 30 minutes on the same set, and stops once a read logs."""
        root = Path(self.tmp.name)
        directives = root / "knowledge" / "board" / "directives"
        directives.mkdir(parents=True)
        (directives / "README.md").write_text("# Directives\n")
        (root / "projects").mkdir()
        at = datetime(2026, 1, 17, 10, 30, tzinfo=timezone.utc).timestamp()
        self.desk_log.write_text("2026-01-17T10:30Z board desk: pushed: A-1: updated; Progress: waits one read: edited "
                                 "in Notion\n")
        event = json.dumps({"transcript_path": str(root / "projects" / "session.jsonl")})

        def stop(now):
            err = io.StringIO()
            with mock.patch.object(hook, "ROOT", root), mock.patch.object(hook.sys, "stdin", io.StringIO(event)), \
                    mock.patch.object(capacity_scan, "desk_job_loaded", return_value=True), \
                    mock.patch.object(hook.time, "time", return_value=now), redirect_stderr(err):
                return hook.main(), err.getvalue()

        self.assertEqual(stop(at + 60), (0, ""))  # reading; a page that waits one read isn't held
        code, err = stop(at + 660)
        self.assertEqual(code, 2)
        self.assertIn("need you now: DESK STALE.", err)
        self.assertEqual(stop(at + 720), (0, ""))  # the same set, within 30 minutes
        self.desk_log.write_text(self.desk_log.read_text() + "2026-01-17T10:43Z board desk: read: 0 answers kept "
                                 "(none), 0 changes not tied to the Board\n")
        self.state.unlink()
        self.assertEqual(stop(at + 780), (0, ""))  # read again

    def test_stale_pages_and_emails_due_are_named_with_what_to_do(self):
        """Each kind gets its own sentence."""
        ids = ["STALE PAGE knowledge/company/how-it-works.md", "EMAIL DUE Q-1: Answered"]
        code, err, _ = self.run_hook(ids=ids)
        self.assertEqual(code, 2)
        self.assertIn("2 open directive(s), backlog row(s), stale page(s) or email(s) due need you now: " + ", ".join(ids),
                      err)
        self.assertTrue(err.endswith(
            "(ceo.md, \"Capacity\"). Big-picture page(s) behind (STALE PAGE lines): knowledge/company/how-it-works.md: "
            "have each page's owner refresh it today and set its \"Last checked\". "
            "Email(s) due to the Board (EMAIL DUE lines): Q-1: Answered: email the Board now, each id in a subject "
            "(one email may name several ids). Then stop.\n"), err)

    def test_a_stale_page_or_an_email_due_alone_stops_the_turn_and_a_fault_is_named(self):
        root = Path(self.tmp.name)
        (root / "knowledge" / "board" / "directives").mkdir(parents=True)
        (root / "knowledge" / "board" / "directives" / "README.md").write_text("# Directives\n")
        (root / "knowledge" / "company").mkdir(parents=True)
        (root / "knowledge" / "company" / "how-it-works.md").write_text(
            "---\ntitle: x\nowner: ceo\nstatus: active\nupdated: 2026-01-01\nrelated: []\nbig_picture: true\n"
            "product: x\n---\n\n**Last checked:** 2026-01-01, 10:00 UTC.\n")
        (root / "projects").mkdir()
        log = str(root / "projects" / "session.jsonl")
        with mock.patch.object(hook, "ROOT", root):
            self.assertEqual(hook.idle_ids(log, NOW), ["STALE PAGE knowledge/company/how-it-works.md"])
            with mock.patch.object(capacity_scan, "email_due", return_value=[("Q-1", "Answered")]):
                self.assertEqual(hook.idle_ids(log, NOW), ["STALE PAGE knowledge/company/how-it-works.md",
                                                           "EMAIL DUE Q-1: Answered"])
            with mock.patch.object(capacity_scan, "stale_pages", side_effect=RuntimeError("git log failed")), \
                    mock.patch.object(capacity_scan, "email_due", side_effect=RuntimeError("git rev-list failed")):
                self.assertEqual(hook.idle_ids(log, NOW), ["DETECTOR FAULT pages", "DETECTOR FAULT emails"])

    def test_runs_as_a_command(self):
        result = subprocess.run([sys.executable, str(Path(hook.__file__))], input='{"stop_hook_active": true}',
                                capture_output=True, text=True, timeout=30)
        self.assertEqual((result.returncode, result.stderr), (0, ""))

    def test_the_ceo_s_stop_hook_runs_from_a_path_with_a_space(self):
        """ceo.md's command line, through a shell with CLAUDE_PROJECT_DIR set, as Claude Code runs it."""
        repo = Path(hook.__file__).resolve().parents[2]
        front = (repo / ".claude" / "agents" / "executive" / "ceo.md").read_text().split("\n---\n", 1)[0]
        command = re.search(r"^ +command: '(.*capacity_heartbeat\.py.*)'$", front, re.M).group(1).replace("''", "'")
        spaced = Path(self.tmp.name) / "a folder with a space"
        spaced.symlink_to(repo)
        result = subprocess.run(["sh", "-c", command], input='{"stop_hook_active": true}', capture_output=True,
                                text=True, timeout=30, env={**os.environ, "CLAUDE_PROJECT_DIR": str(spaced)})
        self.assertEqual((result.returncode, result.stderr), (0, ""))


if __name__ == "__main__":
    unittest.main()
