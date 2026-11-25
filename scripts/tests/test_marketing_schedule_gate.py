"""Tests for scripts/marketing_schedule_gate.py and the job's use of it.

Each test builds a small checkout in a temp folder. Nothing calls Notion, Metricool, B2 or launchctl: the job's
claude, python3 (the gate) and date are stubs in a temp HOME."""

import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

import marketing_schedule_gate as gate  # noqa: E402
import post  # noqa: E402  (the gate put tools/marketing/publish on the path)

NOW = datetime(2026, 2, 11, 12, 0, tzinfo=timezone.utc)  # a Wednesday: 2026-W07 in any time zone
FIRST = "2026-w07-acme-first"


def page_text(publish_at: str, week="2026-W07") -> str:
    return ("---\ntitle: \"x\"\nowner: content-producer\nstatus: draft\nupdated: 2026-01-16\nrelated: []\n"
            f"brand: founder/acme\nweek: {week}\nformat: carousel\nai_generated: false\n---\n\n# x\n\n"
            "## Caption\n\n```text\ncaption\n```\n\n## Post\n\n- Type: carousel\n"
            f"- Publish at: {publish_at}\n\n| # | File | SHA-256 |\n|---|---|---|\n| 1 | 01.png | – |\n| 2 | 02.png | – |\n")


class Gate(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

    def piece(self, publish_at=NOW + timedelta(days=4), slug="first", text=None,
              folder="founder/acme/content/2026-W07") -> str:
        rel = f"knowledge/marketing/{folder}/{slug}.md"
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(page_text(publish_at.isoformat()) if text is None else text, encoding="utf-8")
        return rel

    def schedule(self, item_id):
        ledger = self.root / post.LEDGER
        ledger.parent.mkdir(parents=True, exist_ok=True)
        with ledger.open("a", encoding="utf-8") as log:
            log.write(json.dumps({"item_id": item_id, "kb_page": "x", "at": NOW.isoformat()}) + "\n")

    def run_gate(self, now=NOW):
        out = io.StringIO()
        with redirect_stdout(out):
            code = gate.main(self.root, now)
        return code, out.getvalue()

    def test_a_piece_ahead_is_due(self):
        self.piece()
        code, out = self.run_gate()
        self.assertEqual(code, 0)
        self.assertIn(FIRST, out)

    def test_far_ahead_is_due_too(self):
        # stage_item.py takes it only from 6 days ahead, but the poll syncs it every 30 minutes while the Board decides
        self.piece(NOW + timedelta(days=10))
        self.assertEqual(self.run_gate()[0], 0)

    def test_due_until_its_publish_at(self):
        publish_at = NOW + post.MIN_AHEAD
        rel = self.piece(publish_at)
        self.assertIsNone(post.time_reason(post.read_piece(rel, self.root), NOW))  # stage_item.py may stage it
        self.assertEqual(self.run_gate()[0], 0)
        # too late to stage, but an approval still gets the poll's "Not scheduled: <reason>" line
        later = publish_at - timedelta(seconds=1)
        self.assertIsNotNone(post.time_reason(post.read_piece(rel, self.root), later))
        self.assertEqual(self.run_gate(later)[0], 0)
        self.assertEqual(self.run_gate(publish_at)[0], gate.NOTHING)

    def test_a_scheduled_piece_is_not_due(self):
        self.piece()
        self.schedule(FIRST)
        code, out = self.run_gate()
        self.assertEqual(code, gate.NOTHING)
        self.assertEqual(out.count("\n"), 1)
        self.piece(slug="other")
        code, out = self.run_gate()
        self.assertEqual(code, 0)
        self.assertNotIn(FIRST, out)
        self.assertIn("2026-w07-acme-other", out)

    def test_pages_read_piece_refuses_are_due_in_the_weeks_the_poll_queries(self):
        # an approval gets the poll's "Not scheduled: <reason>" line while its week is this one or the next
        for week, expected in (("2026-W06", gate.NOTHING), ("2026-W07", 0), ("2026-W08", 0), ("2026-W09", gate.NOTHING)):
            with self.subTest(week=week):
                folder = f"founder/acme/content/{week}"
                refused = [
                    self.piece(slug="no-post", folder=folder,
                               text=page_text("2026-01-20T14:00+01:00", week).replace("## Post", "## Notes")),
                    self.piece(slug="placeholder", folder=folder, text=page_text("not scheduled", week)),
                    self.piece(slug="no-offset", folder=folder, text=page_text("2026-01-20T14:00", week)),
                    self.piece(slug="wrong-week", folder=folder, text=page_text("2026-01-20T14:00+01:00", "2026-W01")),
                ]
                for rel in refused:
                    with self.assertRaises(post.Refused, msg=rel):
                        post.read_piece(rel, self.root)
                code, out = self.run_gate()
                self.assertEqual(code, expected, out)
                if expected == 0:
                    self.assertEqual(out.count("(refused)"), 4)
                shutil.rmtree(self.root / "knowledge")

    def test_a_refused_page_in_the_ledger_is_not_due(self):
        self.piece(text=page_text("not scheduled"))
        self.assertEqual(self.run_gate()[0], 0)
        self.schedule(FIRST)
        self.assertEqual(self.run_gate()[0], gate.NOTHING)

    def test_a_page_named_in_the_wrong_case_is_due(self):
        # a disk may ignore case: stage_item.py and the hook would open it by the item id's path
        for folder, name in (("founder/acme/content/2026-w07", "first"),
                             ("founder/acme/content/2026-W07", "First"),
                             ("founder/Acme/content/2026-W07", "first")):
            for suffix in (".md", ".MD"):
                with self.subTest(folder=folder, file=name + suffix):
                    path = self.root / f"knowledge/marketing/{folder}/{name}{suffix}"
                    path.parent.mkdir(parents=True)
                    path.write_text(page_text((NOW - timedelta(days=30)).isoformat()), encoding="utf-8")
                    code, out = self.run_gate()
                    self.assertEqual(code, 0, out)
                    self.assertEqual(out, f"due: {FIRST} (name case)\n")
                    self.schedule(FIRST)
                    self.assertEqual(self.run_gate()[0], gate.NOTHING)
                    shutil.rmtree(self.root / "knowledge")
                    (self.root / post.LEDGER).unlink()

    def test_other_brands_pages_are_not_due(self):
        self.piece(folder="acme/content/2026-W07")  # stage_item.py takes only founder pages
        self.assertEqual(self.run_gate()[0], gate.NOTHING)

    def test_no_pieces(self):
        code, out = self.run_gate()
        self.assertEqual(code, gate.NOTHING)
        self.assertTrue(out.startswith("nothing to schedule"))

    def test_a_ledger_it_cant_read_raises(self):
        # stage_item.py can't read it either; the job then runs the poll as before (Job.test_a_failed_gate_runs_the_poll)
        self.piece()
        (self.root / post.LEDGER).parent.mkdir(parents=True)
        (self.root / post.LEDGER).write_text("not json\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            self.run_gate()

    @unittest.skipIf(os.geteuid() == 0, "root lists any folder")
    def test_a_folder_it_cant_list_raises(self):
        # Path.glob would skip it and say "nothing to schedule", while stage_item.py reads the page by its path
        rel = self.piece()
        week = (self.root / rel).parent
        week.chmod(0o300)  # search but no read: the page opens, the folder doesn't list
        self.addCleanup(week.chmod, 0o755)
        post.read_piece(rel, self.root)
        with self.assertRaises(PermissionError):
            self.run_gate()

    def test_an_approvals_page_it_cant_read_raises(self):
        # read_piece reads every approvals page; stage_item.py would refuse each piece and the poll would say why
        self.piece()
        approvals = self.root / "knowledge/marketing/founder/acme/approvals/2026-W07.md"
        approvals.parent.mkdir(parents=True)
        approvals.write_bytes(b"\xff\xfe not UTF-8\n")
        with self.assertRaises(UnicodeDecodeError):
            self.run_gate()


TOOLS = ("ToolSearch,Bash,Read,mcp__claude_ai_Notion__notion-query-data-sources,mcp__claude_ai_Notion__notion-fetch,"
         "mcp__claude_ai_Notion__notion-update-page,mcp__claude_ai_Metricool_Social_Media_Management__createScheduledPost")
STUBS = {
    "claude": '#!/bin/sh\nprintf "%s\\0" "$@" > "$HOME/claude.args"\necho "nothing to schedule"\n',
    "python3": '#!/bin/sh\n[ "$1" = "-c" ] && { echo "$CALENDAR"; exit "$CALENDAR_EXIT"; }\n'
               'printf "%s\\0" "$PWD" "$@" > "$HOME/python3.args"\necho "$GATE_OUT"\nexit "$GATE_EXIT"\n',
    "date": '#!/bin/sh\n[ "$1" = "+%H" ] && { echo 12; exit 0; }\nexec /bin/date "$@"\n',
}
HEADER = r"=== \d{4}-\d\d-\d\d \d\d:\d\d [+-]\d{4} scheduling poll"


@unittest.skipUnless(sys.platform == "darwin", "the job is macOS's")
class Job(unittest.TestCase):
    """scripts/marketing_schedule_job.sh copied into a temp checkout, run with HOME there: the PATH it sets starts at
    $HOME/.local/bin, where the stubs are. The test's PATH starts there too, so the date stub answers the job's hour
    check, which runs before the job sets its PATH."""

    def setUp(self):
        self.home = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, self.home, ignore_errors=True)
        (self.home / "repo/scripts").mkdir(parents=True)
        self.job = Path(shutil.copy(SCRIPTS / "marketing_schedule_job.sh", self.home / "repo/scripts"))
        stubs = self.home / ".local/bin"
        stubs.mkdir(parents=True)
        for name, text in STUBS.items():
            (stubs / name).write_text(text, encoding="utf-8")
            (stubs / name).chmod(0o755)

    def start(self, calendar="collection://calendar-data-source", calendar_exit=0, gate_exit=0, gate_out=""):
        env = {"HOME": str(self.home), "PATH": f"{self.home}/.local/bin:/usr/bin:/bin", "GATE_EXIT": str(gate_exit),
               "GATE_OUT": gate_out, "CALENDAR": calendar, "CALENDAR_EXIT": str(calendar_exit)}
        return subprocess.run(["/bin/bash", str(self.job)], env=env, capture_output=True, text=True, timeout=60)

    def run_job(self, gate_exit, gate_out):
        result = self.start(gate_exit=gate_exit, gate_out=gate_out)
        self.assertEqual(result.returncode, 0, result.stderr)
        # the gate is this checkout's, run from its root
        self.assertEqual((self.home / "python3.args").read_text(encoding="utf-8").split("\0")[:-1],
                         [str(self.home / "repo"), "scripts/marketing_schedule_gate.py"])
        args = self.home / "claude.args"
        return result.stdout, args.read_text(encoding="utf-8").split("\0")[:-1] if args.exists() else None

    def test_nothing_to_do_logs_one_line_and_starts_no_session(self):
        out, args = self.run_job(gate.NOTHING, "x.py:1: DeprecationWarning: a warning\nnothing to schedule: none")
        self.assertIsNone(args)
        self.assertRegex(out, rf"\A{HEADER} skipped: nothing to schedule: none\n\Z")

    def test_something_to_do_starts_the_same_session(self):
        out, args = self.run_job(0, f"due: {FIRST} at 2026-01-20T14:00:00+01:00")
        self.assertRegex(out, rf"\A{HEADER}\ndue: {FIRST} at 2026-01-20T14:00:00\+01:00\nnothing to schedule\n\Z")
        self.assertTrue(args[1].startswith("Scheduling poll (scripts/marketing_schedule_job.sh, every 30 minutes)."))
        self.assertIn('"data_source_url": "collection://calendar-data-source"', args[1])
        self.assertEqual([args[0]] + args[2:], ["-p", "--agent", "cmo", "--model", "sonnet", "--max-turns", "40",
                                                "--allowedTools", TOOLS])

    def test_no_calendar_or_a_broken_company_json_starts_no_session(self):
        result = self.start(calendar="")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("no calendar in company.json", result.stdout)
        self.assertNotEqual(self.start(calendar_exit=1).returncode, 0)
        for name in ("claude.args", "python3.args"):
            self.assertFalse((self.home / name).exists())

    def test_a_failed_gate_runs_the_poll(self):
        out, args = self.run_job(1, "Traceback (most recent call last):\nValueError: Expecting value")
        self.assertIsNotNone(args)
        lines = out.splitlines()
        self.assertTrue(re.fullmatch(HEADER, lines[0]), lines[0])
        self.assertEqual(lines[1], "the gate failed (exit 1), so the poll runs: ValueError: Expecting value")


if __name__ == "__main__":
    unittest.main()
