"""Tests for tools/marketing/spend.py: the usage log, the monthly caps and the batch report."""

import io
import json
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import spend  # noqa: E402

JAN = datetime(2026, 1, 31, 23, 59, tzinfo=timezone.utc)
FEB = datetime(2026, 2, 1, 0, 1, tzinfo=timezone.utc)


class SpendCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.caps({})

    def tearDown(self):
        self.tmp.cleanup()

    def caps(self, values):
        path = self.root / spend.CAPS
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({**{tool: None for tool in spend.UNITS}, **values}))

    def reserve(self, tool, units, brand="founder/demo", week="2026-W04", now=JAN):
        return spend.reserve(tool, "m", brand, week, "p", units, self.root, now)

    def log(self, tool, units, brand="founder/demo", week="2026-W04", ok=True, now=JAN):
        """A whole call: its reservation, then its outcome."""
        spend.done(self.reserve(tool, units, brand, week, now), units, ok, self.root, now)


class Caps(SpendCase):
    def test_the_shipped_caps_refuse_until_the_board_sets_them(self):
        shipped = json.loads((spend.ROOT / spend.CAPS).read_text())
        footage = {k for k in shipped if k.startswith(("footage_", "_note_footage"))}  # per-download limits, not money
        self.assertEqual(footage, {"_note_footage", "footage_max_mb", "footage_max_minutes", "footage_retries"})
        self.assertEqual(set(shipped) - {"_note"} - footage, set(spend.UNITS))
        self.assertTrue(all(shipped[tool] is None for tool in spend.UNITS))

    def test_a_null_cap_refuses(self):
        with self.assertRaisesRegex(spend.CapError, r"TODO\(board\): set the monthly cap in tools/marketing/caps.json"):
            self.reserve("gemini_images", 1)
        self.assertFalse((self.root / spend.LOG).exists())

    def test_within_the_cap_passes(self):
        self.caps({"gemini_images": 3})
        self.log("gemini_images", 2)
        self.reserve("gemini_images", 1)  # exactly reaches the cap: allowed

    def test_passing_the_cap_refuses(self):
        self.caps({"gemini_video_seconds": 20})
        self.log("gemini_video_seconds", 16)
        with self.assertRaisesRegex(spend.CapError, "16 of 20 seconds used in 2026-01; 8 more would pass"):
            self.reserve("gemini_video_seconds", 8)
        self.assertEqual(spend.month_total("gemini_video_seconds", "2026-01", self.root), 16, "a refusal logs nothing")

    def test_failed_calls_count_toward_the_cap(self):
        self.caps({"gemini_images": 1})
        self.log("gemini_images", 1, ok=False)
        with self.assertRaises(spend.CapError):
            self.reserve("gemini_images", 1)

    def test_a_reservation_without_an_outcome_still_counts(self):
        self.caps({"elevenlabs_stt_seconds": 60})
        self.reserve("elevenlabs_stt_seconds", 45)  # the process was killed before the reply
        self.assertEqual(spend.month_total("elevenlabs_stt_seconds", "2026-01", self.root), 45)
        with self.assertRaisesRegex(spend.CapError, "45 of 60 seconds"):
            self.reserve("elevenlabs_stt_seconds", 20)

    def test_two_reservations_that_together_pass_the_cap_the_second_is_refused(self):
        self.caps({"gemini_video_seconds": 12})
        self.reserve("gemini_video_seconds", 8)
        with self.assertRaisesRegex(spend.CapError, "8 of 12 seconds used in 2026-01; 8 more would pass"):
            self.reserve("gemini_video_seconds", 8)

    def test_reservations_at_the_same_time_never_pass_the_cap(self):
        self.caps({"gemini_images": 5})

        def attempt(_):
            try:
                self.reserve("gemini_images", 1)
                return True
            except spend.CapError:
                return False

        with ThreadPoolExecutor(max_workers=20) as pool:
            passed = list(pool.map(attempt, range(20)))
        self.assertEqual(passed.count(True), 5)
        self.assertEqual(spend.month_total("gemini_images", "2026-01", self.root), 5)

    def test_a_call_counts_once_as_the_larger_of_reserved_and_actual(self):
        self.caps({"gemini_video_seconds": 60})
        spend.done(self.reserve("gemini_video_seconds", 8), 10.04, True, self.root, JAN)  # the clip came out longer
        spend.done(self.reserve("gemini_video_seconds", 6), 4, True, self.root, JAN)  # and shorter
        self.assertEqual(spend.month_total("gemini_video_seconds", "2026-01", self.root), 16.04)

    def test_other_tools_dont_count(self):
        self.caps({"elevenlabs_stt_seconds": 60, "gemini_video_seconds": 500})
        self.log("gemini_video_seconds", 500)
        self.reserve("elevenlabs_stt_seconds", 60)

    def test_a_new_month_starts_from_zero(self):
        self.caps({"elevenlabs_tts_characters": 1000})
        self.log("elevenlabs_tts_characters", 1000, now=JAN)
        with self.assertRaises(spend.CapError):
            self.reserve("elevenlabs_tts_characters", 1, now=JAN)
        self.reserve("elevenlabs_tts_characters", 1000, now=FEB)

    def test_a_call_counts_in_the_month_it_was_reserved(self):
        self.caps({"gemini_images": 1})
        spend.done(self.reserve("gemini_images", 1, now=JAN), 1, True, self.root, FEB)  # the reply came after midnight
        self.assertEqual(spend.month_total("gemini_images", "2026-01", self.root), 1)
        self.assertEqual(spend.month_total("gemini_images", "2026-02", self.root), 0)
        self.reserve("gemini_images", 1, now=FEB)


class Log(SpendCase):
    def test_a_reservation_line_then_an_outcome_line(self):
        self.caps({"gemini_images": 10})
        self.log("gemini_images", 1, now=JAN)
        reserved, outcome = [json.loads(line) for line in (self.root / spend.LOG).read_text().splitlines()]
        self.assertRegex(reserved["id"], r"^[0-9a-f]{32}$")
        batch = {"id": reserved["id"], "tool": "gemini_images", "model": "m", "brand": "founder/demo",
                 "week": "2026-W04", "piece": "p", "units": 1, "unit": "images"}
        self.assertEqual(reserved, {"ts": "2026-01-31T23:59:00+00:00", "kind": "reserve", **batch})
        self.assertEqual(outcome, {"ts": "2026-01-31T23:59:00+00:00", "kind": "done", **batch, "ok": True})


class Report(SpendCase):
    def setUp(self):
        super().setUp()
        self.caps({tool: 1000 for tool in spend.UNITS})

    def report(self, brand, week):
        out = io.StringIO()
        with redirect_stdout(out):
            spend.report(brand, week, self.root)
        return out.getvalue()

    def test_totals_per_tool_for_one_batch(self):
        self.log("gemini_images", 1)
        self.log("gemini_images", 1, ok=False)
        self.reserve("gemini_images", 1)  # no outcome: counted, and shown as failed
        self.log("gemini_video_seconds", 8)
        spend.done(self.reserve("gemini_video_seconds", 6), 6.5, True, self.root, JAN)
        self.log("gemini_images", 1, week="2026-W05")
        self.log("gemini_images", 1, brand="founder/acme")
        text = self.report("founder/demo", "2026-W04")
        self.assertIn("| gemini_images | 3 | 2 | 3 images |", text)
        self.assertIn("| gemini_video_seconds | 2 | 0 | 14.5 seconds |", text)
        self.assertIn("no outcome", text)
        self.assertNotIn("elevenlabs", text)

    def test_an_empty_batch_says_so(self):
        self.assertIn("no paid calls logged", self.report("founder/demo", "2026-W04"))


class Helpers(SpendCase):
    def test_media_dir_keeps_to_the_batch_folder(self):
        self.assertEqual(spend.media_dir("founder/demo", "2026-W05", "lake-dawn", self.root),
                         self.root / "workspaces/marketing/media/founder/demo/2026-W05/lake-dawn")
        for brand, week, piece in [("../x", "2026-W05", "p"), ("founder/demo", "05", "p"),
                                   ("founder/demo", "2026-W05", "../p"), ("founder/demo", "2026-W05", "a/b"),
                                   ("/abs", "2026-W05", "p")]:
            with self.subTest(brand=brand, week=week, piece=piece), self.assertRaises(ValueError):
                spend.media_dir(brand, week, piece, self.root)

    def test_media_seconds_reads_ffmpegs_banner(self):
        banner = "Input #0, mov,mp4 from 'a.m4a':\n  Duration: 00:01:02.35, start: 0.000000, bitrate: 73 kb/s\n"
        fake = lambda cmd, **kw: subprocess.CompletedProcess(cmd, 1, "", banner)  # noqa: E731
        self.assertEqual(spend.media_seconds(Path("a.m4a"), run=fake), 62.35)
        none = lambda cmd, **kw: subprocess.CompletedProcess(cmd, 1, "", "a.txt: Invalid data")  # noqa: E731
        with self.assertRaises(ValueError):
            spend.media_seconds(Path("a.txt"), run=none)

    def test_media_seconds_isnt_fooled_by_a_files_metadata(self):
        for tag in ("    title           : Duration: 00:00:01.00, start", "  Duration: 00:00:01.00 from a key with a newline"):
            banner = f"Input #0, mov,mp4 from 'a.mp4':\n  Metadata:\n{tag}\n  Duration: 00:10:00.00, start: 0.000000\n"
            fake = lambda cmd, **kw: subprocess.CompletedProcess(cmd, 1, "", banner)  # noqa: E731
            with self.subTest(tag=tag):
                self.assertEqual(spend.media_seconds(Path("a.mp4"), run=fake), 600.0)


if __name__ == "__main__":
    unittest.main()
