"""Tests for tools/marketing/reels/watch.py. No network: the download, ElevenLabs and the keychain are fakes, and one test
talks to a server of its own on 127.0.0.1. Tests that run the real bundled ffmpeg are skipped where it isn't installed."""

import fcntl
import http.server
import io
import json
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
from contextlib import redirect_stdout
from email.message import Message
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "reels"))

import watch  # noqa: E402
import fetch  # noqa: E402
import scribe  # noqa: E402
import spend  # noqa: E402

HEADER = ("read_date,week,platform,account,followers,median,post_code,link,views,multiple,age_days,recent_or_old,"
          "language,format,collab,collab_with")
WEEK = "2026-W05"
REPLY = {"text": "Was ist heute neu im Überblick", "language_code": "deu", "language_probability": 0.9,
         "words": [{"text": word, "type": "word", "start": i * 0.5 + 0.4, "end": i * 0.5 + 0.8, "logprob": -0.1}
                   for i, word in enumerate("Was ist heute neu im Überblick".split())]
         + [{"text": " ", "type": "spacing", "start": 1.0, "end": 1.0}, {"text": "(music)", "type": "audio_event", "start": 3, "end": 4}]}
BODY = json.dumps(REPLY, ensure_ascii=False).encode("utf-8")
EBUR128 = """[Parsed_ebur128_0 @ 0x1] t: 30.0 TARGET:-23 LUFS M: -20.1 S: -14.0 I: -15.0 LUFS LRA: 5.0 LU FTPK: -1.5 dBFS
[Parsed_ebur128_0 @ 0x1] Summary:

  Integrated loudness:
    I:         -15.0 LUFS
    Threshold: -25.0 LUFS

  Loudness range:
    LRA:         5.0 LU
    Threshold: -35.0 LUFS
    LRA low:   -18.0 LUFS
    LRA high:  -13.0 LUFS

  True peak:
    Peak:       -1.5 dBFS
"""
TSV = ("level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n"
       "1\t1\t0\t0\t0\t0\t0\t0\t720\t1280\t-1\t\n"
       "5\t1\t1\t1\t1\t1\t10\t10\t50\t20\t96.1\tGuten\n"
       "5\t1\t1\t1\t1\t2\t60\t10\t50\t20\t91.0\tMorgen\n"
       "5\t1\t1\t1\t1\t3\t120\t10\t50\t20\t30.0\tMMMM\n"
       "5\t1\t2\t1\t1\t1\t10\t90\t50\t20\t90.0\t10:30\n"
       "5\t1\t3\t1\t1\t1\t10\t190\t50\t20\t50.0\tSeite\n")
BREAKDOWN = "# Breakdown: @acc, aaaaa\n\n" + "".join(  # what follows the label line, every section as reel-analyst.md writes it
    f"## {heading}\nnot seen\n\n" for heading in ("Answer", "Hook (0–3 s)", "Beats", "Format", "Pacing", "Caption and on-screen text",
                                                   "Sound", "Call to action", "Why it holds attention", "What to adapt, per brand",
                                                   "What NOT to copy", "Caveats"))
STYLE_ONLY = "Style-only run: no breakdown; see style.md."


def local_scribe(test, answer):
    """Points scribe at a server of the test's own on 127.0.0.1, which answers each POST with answer(handler)."""
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers["Content-Length"]))
            answer(self)

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    test.addCleanup(server.server_close)
    test.addCleanup(server.shutdown)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    for patcher in (mock.patch.object(scribe, "API", f"http://127.0.0.1:{server.server_port}/"),
                    mock.patch.dict(os.environ, {"no_proxy": "*"})):
        patcher.start()
        test.addCleanup(patcher.stop)


class Case(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.base = self.root / watch.REELS
        self.base.parent.mkdir(parents=True)
        self.csv = self.root / watch.POSTS
        path = self.root / spend.CAPS
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({**{tool: None for tool in spend.UNITS}, "elevenlabs_stt_seconds": 1000}))
        self.posts([self.row("aaaaa", 1.0), self.row("bbbbb", 5.0), self.row("ccccc", 3.0)])
        (self.root / "company.json").write_text('{"integrations": {"marketing": {"public_downloads": true}}}')
        self.fetched, self.slept, self.watched = [], [], []
        self.now = 0.0

    def tearDown(self):
        self.tmp.cleanup()

    def row(self, code, multiple, week=WEEK, platform="instagram", account="acc", language="", label="", age="recent"):
        return (f"2026-01-05,{week},{platform},{account},100,10,{code},https://evil.example/{code},100,{multiple},3,{age},"
                f"{language},{label},no,")

    def posts(self, rows):
        self.csv.write_text("\n".join([HEADER, *rows]) + "\n", encoding="utf-8")

    def get(self, code, folder, root):
        self.fetched.append(code)
        folder.mkdir(exist_ok=True)
        (folder / "video.mp4").write_bytes(b"x")

    def watch(self, folder, reel, week, root):
        self.watched.append(reel["code"])
        metrics = {"length_seconds": 3.0, "cuts_per_minute": 4.0, "sound": "speech", "language": "deu", "words_per_minute": 150.0}
        (folder / "metrics.json").write_text(json.dumps(metrics))
        return metrics

    def clock(self):
        return self.now

    def prepare(self, count=2, retry=False, get=None, watching=None, week=WEEK, recent_only=False):
        out = io.StringIO()
        with redirect_stdout(out):
            code = watch.prepare(self.root, week, count, retry, get=get or self.get, watch=watching or self.watch,
                                 sleep=self.slept.append, clock=self.clock, recent_only=recent_only)
        return code, out.getvalue()

    def measured(self, code, label=None):
        folder = self.base / code
        folder.mkdir(parents=True, exist_ok=True)
        self.watch(folder, {"code": code}, WEEK, self.root)
        if label:
            (folder / "breakdown.md").write_text(f"format: {label}\n\n{BREAKDOWN}", encoding="utf-8")
        return folder


class WeekReels(Case):
    def test_one_per_code_highest_multiple_first(self):
        self.posts([self.row("aaaaa", 1.0), self.row("bbbbb", 5.0), self.row("aaaaa", 9.0), self.row("ccccc", "")])
        reels = watch.week_reels(self.root, WEEK)
        self.assertEqual([(reel["code"], reel["multiple"]) for reel in reels], [("aaaaa", 9.0), ("bbbbb", 5.0), ("ccccc", 0.0)])

    def test_recent_reels_go_first_and_old_ones_stay_queued(self):
        self.posts([self.row("ooooo", 300.5, age="old"), self.row("aaaaa", 2.0), self.row("bbbbb", 3.0, age=""), self.row("ccccc", 5.0)])
        reels = watch.week_reels(self.root, WEEK)
        self.assertEqual([(reel["code"], reel["recent_or_old"]) for reel in reels],
                         [("ccccc", "recent"), ("aaaaa", "recent"), ("ooooo", "old"), ("bbbbb", "")])

    def test_only_that_week_and_instagram(self):
        self.posts([self.row("aaaaa", 1.0), self.row("bbbbb", 2.0, week="2026-W04"), self.row("ccccc", 3.0, platform="youtube")])
        self.assertEqual([reel["code"] for reel in watch.week_reels(self.root, WEEK)], ["aaaaa"])

    def test_a_bad_code_is_skipped_never_fetched(self):
        self.posts([self.row("../../etc", 9.0), self.row("a/b/c/d", 9.0), self.row("aaaaa\\n", 9.0), self.row("bbbbb", 1.0)])
        with redirect_stdout(io.StringIO()):
            self.assertEqual([reel["code"] for reel in watch.week_reels(self.root, WEEK)], ["bbbbb"])


class Download(Case):
    def test_the_address_is_rebuilt_from_the_code_never_the_link_column(self):
        self.base.mkdir()
        urls = []

        def fake_get(url, folder, limits, timeout=None):
            urls.append(url)
            (folder / "video.mp4").write_bytes(b"x")
            (folder / "video.info.json").write_text("{}")
            (folder / "MANIFEST.json").write_text("{}")

        with mock.patch.object(fetch, "_get_url", fake_get), mock.patch.object(fetch, "public_url", lambda url: url), \
                mock.patch.object(fetch, "caps", lambda root: {}):
            watch.download("aaaaa", self.base / "aaaaa", self.root)
        self.assertEqual(urls, ["https://www.instagram.com/reel/aaaaa/"])
        self.assertEqual(sorted(p.name for p in (self.base / "aaaaa").iterdir()), ["MANIFEST.json", "video.info.json", "video.mp4"])
        self.assertFalse((self.base / ".tmp-aaaaa").exists())

    def test_a_failed_download_leaves_nothing_and_says_why(self):
        self.base.mkdir()

        def fake_get(url, folder, limits, timeout=None):
            (folder / "video.part").write_bytes(b"x")
            raise SystemExit("yt-dlp didn't download one video (exit 1): login required")

        with mock.patch.object(fetch, "_get_url", fake_get), mock.patch.object(fetch, "public_url", lambda url: url), \
                mock.patch.object(fetch, "caps", lambda root: {}):
            with self.assertRaisesRegex(watch.ReelError, "login required"):
                watch.download("aaaaa", self.base / "aaaaa", self.root)
        self.assertEqual(list(self.base.iterdir()), [])

    def test_only_an_mp4_counts(self):
        self.base.mkdir()

        def fake_get(url, folder, limits, timeout=None):
            (folder / "video.webm").write_bytes(b"x")

        with mock.patch.object(fetch, "_get_url", fake_get), mock.patch.object(fetch, "public_url", lambda url: url), \
                mock.patch.object(fetch, "caps", lambda root: {}):
            with self.assertRaisesRegex(watch.ReelError, "MP4"):
                watch.download("aaaaa", self.base / "aaaaa", self.root)

    def test_the_download_gets_what_is_left_of_the_reels_time(self):
        self.base.mkdir()
        seen = []

        def fake_get(url, folder, limits, timeout=None):
            seen.append(timeout)
            (folder / "video.mp4").write_bytes(b"x")

        with mock.patch.object(fetch, "_get_url", fake_get), mock.patch.object(fetch, "public_url", lambda url: url), \
                mock.patch.object(fetch, "caps", lambda root: {}), mock.patch.object(watch, "reel_time", lambda: 50.0):
            watch.download("aaaaa", self.base / "aaaaa", self.root)
        self.assertEqual(seen, [50.0])

    def test_a_download_cut_off_leaves_nothing_and_prepare_words_it(self):
        self.base.mkdir()

        def fake_get(url, folder, limits, timeout=None):
            raise subprocess.TimeoutExpired(["yt-dlp", "--long-command-line"], timeout)

        with mock.patch.object(fetch, "_get_url", fake_get), mock.patch.object(fetch, "public_url", lambda url: url), \
                mock.patch.object(fetch, "caps", lambda root: {}):
            with self.assertRaises(subprocess.TimeoutExpired):
                watch.download("aaaaa", self.base / "aaaaa", self.root)
        self.assertEqual(list(self.base.iterdir()), [])


class ReelTime(Case):
    def test_a_slow_reel_fails_with_a_record_and_the_queue_goes_on(self):
        def slow_first(folder, reel, week, root):
            if reel["code"] == "bbbbb":
                self.now += watch.REEL_SECONDS
                watch.left(watch.FFMPEG_SECONDS)
            return self.watch(folder, reel, week, root)

        code, out = self.prepare(count=1, watching=slow_first)
        self.assertEqual(code, 0)
        self.assertIn("bbbbb: failed: out of time", out)
        self.assertEqual((self.base / "bbbbb/failed.txt").read_text(), watch.OUT_OF_TIME + "\n")
        self.assertEqual(self.watched, ["ccccc"])

    def test_a_reels_steps_share_its_time(self):
        def watching(folder, reel, week, root):
            self.now += watch.REEL_SECONDS - 50
            self.assertEqual(watch.left(watch.FFMPEG_SECONDS), 50)
            self.assertEqual(watch.left(10), 10)
            return self.watch(folder, reel, week, root)

        self.assertEqual(self.prepare(count=1, watching=watching)[0], 0)
        self.assertEqual(self.watched, ["bbbbb"])

    def test_the_time_ends_with_the_reel(self):
        self.prepare(count=1)
        self.assertIsNone(watch.reel_time)

        def stops(folder, reel, week, root):
            raise watch.Stop("spend cap reached")

        self.assertEqual(self.prepare(count=2, watching=stops)[0], 2)
        self.assertIsNone(watch.reel_time)
        self.assertEqual(watch.left(60), 60)

    def test_a_killed_step_records_the_reason_not_its_command_line(self):
        def killed(folder, reel, week, root):
            raise subprocess.TimeoutExpired(["ffmpeg", "--long-command-line"], 5)

        code, out = self.prepare(count=1, watching=killed)
        self.assertNotIn("--long-command-line", out)
        self.assertEqual((self.base / "bbbbb/failed.txt").read_text(), "a step ran past its own limit of 5 s\n")

    def test_a_step_killed_with_the_reels_time_gone_is_out_of_time(self):
        def killed(folder, reel, week, root):
            self.now += watch.REEL_SECONDS
            raise subprocess.TimeoutExpired(["ffmpeg", "--long-command-line"], 5)

        self.prepare(count=1, watching=killed)
        self.assertEqual((self.base / "bbbbb/failed.txt").read_text(), watch.OUT_OF_TIME + "\n")

    def test_a_reply_past_the_reels_time_fails_with_a_record_and_the_queue_goes_on(self):
        def never_answers(audio, language_code, key):
            time.sleep(30)

        def wav(video, *args):
            Path(args[-1]).write_bytes(b"\0" * watch.WAV_BYTES_PER_SECOND)

        def slow_first(folder, reel, week, root):
            if reel["code"] != "bbbbb":
                return self.watch(folder, reel, week, root)
            self.now += watch.REEL_SECONDS - 0.05
            return watch.transcribe(folder / "video.mp4", folder, reel, week, root, watch.send_audio, lambda: "fake-key")

        started = time.monotonic()
        with mock.patch.object(scribe, "scribe_post", never_answers), mock.patch.object(watch, "ffmpeg_ok", wav):
            code, out = self.prepare(count=1, watching=slow_first)
        self.assertLess(time.monotonic() - started, 5)
        self.assertEqual(code, 0)
        self.assertEqual((self.base / "bbbbb/failed.txt").read_text(), watch.OUT_OF_TIME + "\n")
        self.assertEqual(self.watched, ["ccccc"])
        lines = (self.root / "workspaces/marketing/spend.jsonl").read_text().splitlines()
        self.assertFalse(json.loads(lines[-1])["ok"])
        self.assertFalse((self.base / "bbbbb/audio.wav").exists())

    def test_ffmpeg_and_tesseract_get_what_is_left(self):
        seen = []

        def run(args, **options):
            seen.append(options["timeout"])
            return subprocess.CompletedProcess(args, 0, "", "")

        folder = self.base / "aaaaa"
        folder.mkdir(parents=True)

        def frames(video, *args):
            (folder / "frames/f-0001.png").write_bytes(b"x")

        with mock.patch.object(watch.subprocess, "run", run), mock.patch.object(watch, "reel_time", lambda: 40.0):
            watch.ffmpeg(folder / "video.mp4")
            with mock.patch.object(watch, "ffmpeg_ok", frames), mock.patch.object(watch, "TESSERACT", "tesseract"):
                watch.on_screen(folder / "video.mp4", folder, 10.0)
        self.assertEqual(seen, [40.0, 40.0])

    def test_a_steps_own_limit_stands_when_the_reel_has_more_time(self):
        with mock.patch.object(watch, "reel_time", lambda: 190.0):
            self.assertEqual(watch.left(watch.FFMPEG_SECONDS), watch.FFMPEG_SECONDS)

    def test_the_last_reel_and_its_pause_fit_bashs_limit(self):
        self.assertLess(watch.BUDGET_SECONDS + watch.REEL_SECONDS + watch.PAUSE_SECONDS * 1.5, 600)


class Prepare(Case):
    def test_highest_multiple_first_and_paced_after_each_download_but_the_last(self):
        code, _ = self.prepare(count=2)
        self.assertEqual(code, 0)
        self.assertEqual(self.fetched, ["bbbbb", "ccccc"])
        self.assertEqual(len(self.slept), 1)
        self.assertTrue(10 <= self.slept[0] <= 30)

    def test_count_is_a_target_so_a_ready_batch_costs_nothing(self):
        self.measured("bbbbb")
        self.measured("ccccc")
        code, out = self.prepare(count=2)
        self.assertEqual((code, self.fetched), (0, []))
        self.assertIn("nothing to prepare", out)

    def test_picks_up_where_it_left_off(self):
        self.measured("bbbbb", "talking head")
        self.prepare(count=1)
        self.assertEqual(self.fetched, ["ccccc"])
        self.prepare(count=2)
        self.assertEqual(self.fetched, ["ccccc", "aaaaa"])

    def test_a_video_on_disk_isnt_downloaded_or_paced(self):
        for code in ["bbbbb", "ccccc"]:
            (self.base / code).mkdir(parents=True)
            (self.base / code / "video.mp4").write_bytes(b"x")
        self.prepare(count=2)
        self.assertEqual((self.fetched, self.slept, self.watched), ([], [], ["bbbbb", "ccccc"]))

    def test_three_failures_in_a_row_stop_and_say_why(self):
        def fail(code, folder, root):
            self.fetched.append(code)
            raise watch.ReelError("HTTP 429 rate limited")

        self.posts([self.row(f"code{i}", 9 - i) for i in range(6)])
        code, out = self.prepare(count=5, get=fail)
        self.assertEqual(code, 2)
        self.assertEqual(len(self.fetched), 3)
        self.assertIn("3 failures in a row", out)
        self.assertIn("HTTP 429", out)

    def test_a_success_resets_the_run_of_failures(self):
        calls = iter([watch.ReelError("gone"), watch.ReelError("gone"), None, watch.ReelError("gone"), None])

        def sometimes(code, folder, root):
            outcome = next(calls)
            if outcome:
                raise outcome
            self.get(code, folder, root)

        self.posts([self.row(f"code{i}", 9 - i) for i in range(6)])
        code, _ = self.prepare(count=2, get=sometimes)
        self.assertEqual((code, len(self.fetched)), (0, 2))

    def test_a_failed_reel_is_skipped_until_retried_and_cleared_by_success(self):
        def fail(code, folder, root):
            raise watch.ReelError("this reel is gone")

        first = [True]

        def once(code, folder, root):
            if first.pop() if first else False:
                fail(code, folder, root)
            self.get(code, folder, root)

        self.prepare(count=1, get=once)
        self.assertIn("this reel is gone", (self.base / "bbbbb/failed.txt").read_text())
        self.assertEqual(self.fetched, ["ccccc"])
        self.prepare(count=2)
        self.assertEqual(self.fetched, ["ccccc", "aaaaa"])
        self.prepare(count=3, retry=True)
        self.assertEqual(self.fetched, ["ccccc", "aaaaa", "bbbbb"])
        self.assertFalse((self.base / "bbbbb/failed.txt").exists())

    def test_a_measuring_failure_counts_like_a_download_failure(self):
        def broken(folder, reel, week, root):
            raise watch.ReelError("ffmpeg failed")

        code, out = self.prepare(count=3, watching=broken)
        self.assertEqual(code, 2)
        self.assertIn("ffmpeg failed", out)

    def test_a_run_takes_recent_reels_before_an_old_one_with_a_far_higher_multiple(self):
        self.posts([self.row("ooooo", 300.5, age="old"), self.row("aaaaa", 2.0), self.row("bbbbb", 1.0)])
        self.prepare(count=2)
        self.assertEqual(self.fetched, ["aaaaa", "bbbbb"])
        self.prepare(count=3)
        self.assertEqual(self.fetched, ["aaaaa", "bbbbb", "ooooo"])

    def test_a_failed_download_is_paced_too(self):
        def fail(code, folder, root):
            raise watch.ReelError("this reel is gone")

        self.prepare(count=2, get=fail)
        self.assertEqual(len(self.slept), 2)

    def test_anything_a_reels_files_raise_fails_that_reel_and_the_next_goes_on(self):
        def odd_info(code, folder, root):
            if code == "bbbbb":
                raise AttributeError("'list' object has no attribute 'get'")
            self.get(code, folder, root)

        def odd_caption(folder, reel, week, root):
            if reel["code"] == "ccccc":
                raise TypeError("can only concatenate str")
            return self.watch(folder, reel, week, root)

        code, out = self.prepare(count=1, get=odd_info, watching=odd_caption)
        self.assertEqual(code, 0)
        self.assertIn("no attribute", (self.base / "bbbbb/failed.txt").read_text())
        self.assertIn("concatenate", (self.base / "ccccc/failed.txt").read_text())
        self.assertEqual(self.watched, ["aaaaa"])

    def test_a_failure_with_no_message_still_says_what_it_was(self):
        def odd(code, folder, root):
            raise KeyError()

        self.prepare(count=1, get=odd)
        self.assertEqual((self.base / "bbbbb/failed.txt").read_text(), "KeyError\n")

    def test_a_stop_ends_the_run_at_once(self):
        def stop(folder, reel, week, root):
            raise watch.Stop("spend cap reached")

        code, out = self.prepare(count=3, watching=stop)
        self.assertEqual(code, 2)
        self.assertEqual(self.fetched, ["bbbbb"])
        self.assertIn("spend cap reached", out)
        self.assertFalse((self.base / "bbbbb/failed.txt").exists())

    def test_a_stop_is_stored_and_a_rerun_fetches_nothing(self):
        def stop(folder, reel, week, root):
            raise watch.Stop("spend cap reached")

        self.prepare(count=1, watching=stop)
        self.assertEqual((self.base / watch.STOPPED).read_text(), "stopped: spend cap reached\n")
        self.fetched.clear()
        code, out = self.prepare(count=1)
        self.assertEqual((code, self.fetched, self.watched), (2, [], []))
        self.assertIn("stopped: spend cap reached", out)

    def test_three_failures_in_a_row_are_stored_too(self):
        def fail(code, folder, root):
            raise watch.ReelError("HTTP 429 rate limited")

        self.posts([self.row(f"code{i}", 9 - i) for i in range(6)])
        self.prepare(count=5, get=fail)
        self.assertIn("3 failures in a row", (self.base / watch.STOPPED).read_text())
        self.fetched.clear()
        code, out = self.prepare(count=5)
        self.assertEqual((code, self.fetched), (2, []))
        self.assertIn("HTTP 429", out)

    def test_a_stored_stop_holds_every_week(self):
        self.base.mkdir()
        (self.base / watch.STOPPED).write_text("stopped: spend cap reached\n")
        self.posts([self.row("wwwww", 2.0, week="2026-W06")])
        code, _ = self.prepare(count=1, week="2026-W06")
        self.assertEqual((code, self.fetched), (2, []))

    def test_a_ready_batch_costs_nothing_under_a_stored_stop(self):
        self.measured("bbbbb")
        (self.base / watch.STOPPED).write_text("stopped: spend cap reached\n")
        code, out = self.prepare(count=1)
        self.assertEqual((code, self.fetched), (0, []))
        self.assertIn("nothing to prepare", out)

    def test_retry_failed_clears_a_stored_stop_and_fetches(self):
        self.base.mkdir()
        (self.base / watch.STOPPED).write_text("stopped: spend cap reached\n")
        code, _ = self.prepare(count=1, retry=True)
        self.assertEqual((code, self.fetched), (0, ["bbbbb"]))
        self.assertFalse((self.base / watch.STOPPED).exists())

    def test_retry_failed_stores_a_new_stop(self):
        def stop(folder, reel, week, root):
            raise watch.Stop("spend cap reached")

        self.prepare(count=1, retry=True, watching=stop)
        self.assertTrue((self.base / watch.STOPPED).exists())

    def test_recent_only_never_pulls_in_an_old_reel(self):
        self.posts([self.row("ooooo", 300.5, age="old"), self.row("aaaaa", 2.0), self.row("uuuuu", 3.0, age="")])
        code, _ = self.prepare(count=3, recent_only=True)
        self.assertEqual((code, self.fetched), (0, ["aaaaa"]))

    def test_recent_only_doesnt_count_an_old_ready_reel(self):
        self.posts([self.row("ooooo", 300.5, age="old"), self.row("aaaaa", 2.0)])
        self.measured("ooooo")
        self.prepare(count=1, recent_only=True)
        self.assertEqual(self.fetched, ["aaaaa"])

    def test_one_call_fits_bashs_limit(self):
        def slow(folder, reel, week, root):
            self.now += 300
            return self.watch(folder, reel, week, root)

        code, out = self.prepare(count=3, watching=slow)
        self.assertEqual((code, len(self.fetched)), (0, 2))
        self.assertIn("run prepare again", out)

    def test_refuses_a_link_so_reels_stay_out_of_synced_folders(self):
        with tempfile.TemporaryDirectory() as elsewhere:
            self.base.symlink_to(elsewhere)
            with self.assertRaisesRegex(SystemExit, "a synced folder"):
                self.prepare()


class PrepareLock(Case):
    """One prepare at a time: the lock is a live process's flock, not the file."""

    def holder(self):
        """Another process holding the lock, as a second reel-analyst's prepare would."""
        self.base.mkdir(exist_ok=True)
        code = ("import fcntl, os, sys, time; lock = os.open(sys.argv[1], os.O_WRONLY | os.O_CREAT); "
                "fcntl.flock(lock, fcntl.LOCK_EX); print('held', flush=True); time.sleep(60)")
        child = subprocess.Popen([sys.executable, "-I", "-c", code, str(self.base / watch.PREPARE_LOCK)], stdout=subprocess.PIPE,
                                 text=True)
        self.addCleanup(child.stdout.close)
        self.addCleanup(child.wait)
        self.addCleanup(child.kill)
        self.assertEqual(child.stdout.readline().strip(), "held")
        return child

    def assert_free(self):
        lock = os.open(self.base / watch.PREPARE_LOCK, os.O_WRONLY)
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)  # raises BlockingIOError if a run still held it
        finally:
            os.close(lock)

    def test_a_second_prepare_any_week_or_flags_refuses_at_once_and_reads_nothing(self):
        self.holder()
        (self.base / watch.STOPPED).write_text("stopped: earlier\n")
        for flags in ({}, {"week": "2026-W06"}, {"retry": True}, {"recent_only": True}, {"count": 9, "retry": True, "recent_only": True}):
            began = time.monotonic()
            with self.subTest(**flags), mock.patch.object(watch, "week_reels", side_effect=AssertionError("read posts.csv")), \
                    self.assertRaises(SystemExit) as refused:
                self.prepare(**flags)
            self.assertEqual(str(refused.exception), watch.BUSY)
            self.assertLess(time.monotonic() - began, 5)
        self.assertEqual((self.fetched, self.watched, self.slept), ([], [], []))
        self.assertTrue((self.base / watch.STOPPED).is_file())  # --retry-failed cleared nothing

    def test_the_refusal_is_one_line_and_exits_non_zero_from_the_command_line(self):
        self.holder()
        with self.assertRaises(SystemExit) as refused:
            watch.main(["prepare", "--week", WEEK, "--count", "3", "--recent-only"], self.root)
        self.assertEqual(refused.exception.code, watch.BUSY)  # a message, not 0: Python prints it on stderr and exits 1
        self.assertNotIn("\n", watch.BUSY)
        self.assertEqual(self.fetched, [])

    def test_holds_the_lock_while_it_runs_and_drops_it_after(self):
        inner = []

        def get(code, folder, root):
            with self.assertRaises(SystemExit) as refused:
                watch.prepare(self.root, "2026-W06", 1, get=self.get, watch=self.watch, sleep=self.slept.append, clock=self.clock)
            inner.append(str(refused.exception))
            self.get(code, folder, root)

        code, _ = self.prepare(count=1, get=get)
        self.assertEqual((code, inner, self.fetched), (0, [watch.BUSY], ["bbbbb"]))
        self.assert_free()

    def test_drops_the_lock_however_the_run_ends(self):
        def interrupted(code, folder, root):
            raise KeyboardInterrupt

        with self.assertRaises(KeyboardInterrupt):
            self.prepare(get=interrupted)
        self.assert_free()

    def test_a_lock_left_by_a_killed_run_doesnt_block(self):
        child = self.holder()
        child.send_signal(signal.SIGKILL)
        child.wait()
        self.assertTrue((self.base / watch.PREPARE_LOCK).is_file())  # the file stays, and it is no lock
        code, _ = self.prepare(count=1)
        self.assertEqual((code, self.fetched), (0, ["bbbbb"]))

    def test_a_link_at_the_lock_refuses(self):
        self.base.mkdir()
        target = self.root / "elsewhere.txt"
        target.write_text("x")
        (self.base / watch.PREPARE_LOCK).symlink_to(target)
        with self.assertRaisesRegex(SystemExit, "^refused: .*can't be locked"):
            self.prepare()
        self.assertEqual((self.fetched, target.read_text()), ([], "x"))


class Transcribe(Case):
    def setUp(self):
        super().setUp()
        self.folder = self.base / "aaaaa"
        self.folder.mkdir(parents=True)
        self.sent = []
        self.seconds = 10.0
        patcher = mock.patch.object(watch, "ffmpeg_ok", self.fake_wav)
        patcher.start()
        self.addCleanup(patcher.stop)

    def fake_wav(self, video, *args):
        with Path(args[-1]).open("wb") as wav:
            wav.truncate(int(self.seconds * watch.WAV_BYTES_PER_SECOND))

    def send(self, audio, language_code, key):
        self.assertTrue(audio.is_file())
        self.sent.append((audio.name, language_code, key))
        return BODY

    def transcribe(self, send=None):
        return watch.transcribe(self.folder / "video.mp4", self.folder, {"code": "aaaaa"}, WEEK, self.root, send or self.send, lambda: "fake-key")

    def spend_lines(self):
        return [json.loads(line) for line in (self.root / "workspaces/marketing/spend.jsonl").read_text().splitlines()]

    def test_scribe_detects_the_language(self):
        self.transcribe()
        self.assertEqual(self.sent, [("audio.wav", None, "fake-key")])

    def test_keeps_the_words_deletes_the_audio_and_logs_the_spend(self):
        kept = self.transcribe()
        self.assertEqual(len(kept["words"]), 6)
        self.assertEqual(kept["language_code"], "deu")
        self.assertFalse((self.folder / "audio.wav").exists())
        lines = self.spend_lines()
        self.assertEqual(lines[0]["tool"], scribe.TOOL)
        self.assertTrue(lines[-1]["ok"])

    def test_the_spend_log_counts_the_audio_sent(self):
        self.seconds = 42.5
        kept = self.transcribe()
        self.assertEqual([line["units"] for line in self.spend_lines()], [42.5, 42.5])
        self.assertEqual(kept["seconds"], 42.5)

    def test_no_reel_is_paid_for_twice(self):
        self.transcribe()
        self.transcribe()
        self.assertEqual(len(self.sent), 1)

    def test_the_cap_refuses_before_sending(self):
        self.seconds = 5000.0
        with self.assertRaises(watch.Stop):
            self.transcribe()
        self.assertEqual(self.sent, [])
        self.assertFalse((self.folder / "audio.wav").exists())

    def test_a_service_failure_is_logged_and_stops_the_run(self):
        def down(audio, language_code, key):
            raise OSError("no network")

        with self.assertRaisesRegex(watch.Stop, "ElevenLabs failed"):
            self.transcribe(send=down)
        self.assertFalse(self.spend_lines()[-1]["ok"])
        self.assertFalse((self.folder / "scribe.json").exists())

    def test_audio_the_service_refuses_fails_only_that_reel(self):
        def refused(audio, language_code, key):
            raise urllib.error.HTTPError("https://x", 422, "bad audio", Message(), None)

        with self.assertRaisesRegex(watch.ReelError, "refused its audio"):
            self.transcribe(send=refused)

    def test_a_call_the_reels_time_cut_off_fails_only_that_reel(self):
        def cut_off(audio, language_code, key):
            raise watch.ReelError(watch.OUT_OF_TIME)

        with self.assertRaisesRegex(watch.ReelError, "out of time"):
            self.transcribe(send=cut_off)
        self.assertFalse(self.spend_lines()[-1]["ok"])
        self.assertFalse((self.folder / "audio.wav").exists())

    def assert_kept_and_not_paid_again(self, body):
        def unreadable(audio, language_code, key):
            self.sent.append(audio.name)
            return body

        for _ in range(2):
            with self.assertRaisesRegex(watch.ReelError, "scribe.raw.json"):
                self.transcribe(send=unreadable)
        self.assertEqual(self.sent, ["audio.wav"])
        self.assertEqual(len(self.spend_lines()), 2)  # one call: reserved, then done
        self.assertEqual((self.folder / "scribe.raw.json").read_bytes(), body)
        self.assertFalse((self.folder / "scribe.json").exists())

    def test_a_reply_cut_short_is_kept_and_not_paid_for_twice(self):
        self.assert_kept_and_not_paid_again(BODY[:40])

    def test_a_reply_thats_not_text_is_kept_and_not_paid_for_twice(self):
        self.assert_kept_and_not_paid_again(b"\xff\xfe\x00 not utf-8")

    def test_an_empty_reply_is_kept_and_not_paid_for_twice(self):
        self.assert_kept_and_not_paid_again(b"")

    def test_a_reply_with_a_word_it_cant_read_is_kept_and_not_paid_for_twice(self):
        self.assert_kept_and_not_paid_again(b'{"words": ["not a word object"]}')

    def test_a_reply_that_isnt_an_object_fails_only_that_reel(self):
        self.assert_kept_and_not_paid_again(b'["not an object"]')

    def assert_a_cut_body_is_kept(self, cut):
        posts = []

        def answer(handler):
            posts.append(handler.path)
            cut(handler)

        local_scribe(self, answer)
        for _ in range(2):
            with self.assertRaisesRegex(watch.ReelError, "scribe.raw.json"):
                self.transcribe(send=watch.send_audio)
        self.assertEqual(len(posts), 1)
        self.assertEqual(len(self.spend_lines()), 2)  # one call: reserved, then done
        self.assertTrue(self.spend_lines()[-1]["ok"])
        self.assertEqual((self.folder / "scribe.raw.json").read_bytes(), BODY[:20])
        self.assertFalse((self.folder / "scribe.json").exists())

    def test_a_body_cut_on_the_wire_is_kept_and_not_paid_for_twice(self):
        def cut(handler):
            handler.send_response(200)
            handler.send_header("Content-Length", str(len(BODY)))
            handler.end_headers()
            handler.wfile.write(BODY[:20])

        self.assert_a_cut_body_is_kept(cut)

    def test_a_chunked_body_cut_on_the_wire_is_kept_and_not_paid_for_twice(self):
        def cut(handler):
            handler.protocol_version = "HTTP/1.1"
            handler.close_connection = True
            handler.send_response(200)
            handler.send_header("Transfer-Encoding", "chunked")
            handler.end_headers()
            handler.wfile.write(b"14\r\n" + BODY[:20] + b"\r\n")

        self.assert_a_cut_body_is_kept(cut)

    def test_a_saved_raw_reply_is_parsed_again_with_no_call(self):
        self.seconds = 42.5
        self.transcribe()
        (self.folder / "scribe.json").unlink()
        kept = self.transcribe()
        self.assertEqual(len(self.sent), 1)
        self.assertEqual((kept["seconds"], len(kept["words"])), (42.5, 6))

    def test_reel_spend_carries_a_brand_the_report_can_find(self):
        self.transcribe()
        self.assertEqual({line["brand"] for line in self.spend_lines()}, {watch.REEL_BRAND})
        self.assertRegex(watch.REEL_BRAND, spend.BATCH["brand"][0])

    def test_the_audio_goes_even_if_ffmpeg_fails_midway(self):
        def half_a_wav(video, *args):
            Path(args[-1]).write_bytes(b"RIFF")
            raise watch.ReelError("ffmpeg failed")

        with mock.patch.object(watch, "ffmpeg_ok", half_a_wav), self.assertRaises(watch.ReelError):
            self.transcribe()
        self.assertFalse((self.folder / "audio.wav").exists())
        self.assertEqual(self.sent, [])

    def test_a_missing_key_sends_nothing(self):
        def no_key():
            raise SystemExit("No ElevenLabs key")

        def watching(folder, reel, week, root):
            return watch.transcribe(folder / "video.mp4", folder, reel, week, root, self.send, no_key)

        code, out = self.prepare(count=2, watching=watching)
        self.assertEqual(code, 2)
        self.assertIn("stopped: No ElevenLabs key", out)
        self.assertEqual(self.sent, [])
        self.assertEqual(self.fetched, ["bbbbb"])
        self.assertFalse((self.base / "bbbbb/failed.txt").exists())


class OnScreen(Case):
    def read(self, returncode, stdout="", stderr=""):
        folder = self.base / "aaaaa"
        folder.mkdir(parents=True)
        done = subprocess.CompletedProcess([], returncode, stdout, stderr)

        def one_frame(video, *args):
            Path(args[-1].replace("%04d", "0001")).write_bytes(b"x")

        with mock.patch.object(watch, "ffmpeg_ok", one_frame), mock.patch.object(watch, "TESSERACT", "tesseract"), \
                mock.patch.object(watch.subprocess, "run", lambda *args, **kwargs: done):
            lines = watch.on_screen(folder / "video.mp4", folder, 4.0)
        self.assertFalse((folder / "frames").exists())
        return lines

    def test_text_is_read_with_its_time(self):
        self.assertEqual(self.read(0, TSV), ["00:00 Guten Morgen"])

    def test_a_missing_model_or_a_crash_isnt_the_same_as_no_text(self):
        lines = self.read(1, stderr="Error opening data file deu.traineddata\nFailed loading language 'deu'\n")
        self.assertEqual(len(lines), 1)
        self.assertRegex(lines[0], r"^\(not read: tesseract failed: .*Failed loading language 'deu'\)$")


class Probe(Case):
    REAL = ("  Duration: 00:00:32.50, start: 0.000000, bitrate: 300 kb/s\n"
            "  Stream #0:0[0x1](und): Video: h264 (High), yuv420p, 720x1280, 30 fps\n"
            "    Metadata:\n      handler_name    : Duration: 00:00:01.00\n"
            "  Stream #0:1[0x2](und): Audio: aac (LC), 44100 Hz, stereo\n")

    def probe(self, stderr):
        result = subprocess.CompletedProcess([], 1, "", stderr)
        with mock.patch.object(watch, "ffmpeg", lambda *args: result):
            return watch.probe(Path("v.mp4"))

    def test_metadata_never_sets_the_length(self):
        for block in ["    comment         : Duration: 00:00:01.00, start: 0.0, bitrate: 1 kb/s\n",
                      "    comment         : x\n                    :   Duration: 00:00:01.00, start: 0.0\n",
                      "    Duration: 00:00:01.00, start: 0.0: x\n",
                      "    x\n  Duration: 00:00:01.00, start: 0.0, bitrate: 1 kb/s\n  Stream #0:9: Audio: aac: y\n"]:
            with self.subTest(block=block):
                self.assertEqual(self.probe(f"  Metadata:\n{block}{self.REAL}"), (32.5, True))

    def test_only_a_real_line_says_there_is_sound(self):
        silent = "  Metadata:\n    Stream #0:9: Audio: y\n  Duration: 00:00:04.00, start: 0.0\n  Stream #0:0: Video: h264\n"
        self.assertEqual(self.probe(silent), (4.0, False))

    def test_no_length_fails_the_reel(self):
        with self.assertRaisesRegex(watch.ReelError, "length"):
            self.probe("    Duration: 00:00:01.00\n  Duration: N/A, bitrate: N/A\n")


class Caption(Case):
    def test_a_caption_that_isnt_text_is_no_caption(self):
        folder = self.base / "aaaaa"
        folder.mkdir(parents=True)
        for info in ['{"description": ["a"]}', '{"description": 7}', '{"description": null}', '["a"]', "null", "not json"]:
            with self.subTest(info=info):
                (folder / "video.info.json").write_text(info)
                self.assertEqual(watch.caption_of(folder), "")
        (folder / "video.info.json").write_text('{"description": "the caption"}')
        self.assertEqual(watch.caption_of(folder), "the caption")

    def test_masked_takes_out_handles_emails_and_phone_numbers(self):
        for text, kept in [("cc @some.body ok", "cc @... ok"), ("write to a.b+c@example.com now", "write to @... now"),
                           ("call +49 555 123 4567", "call ..."), ("call 0555 12-34-56", "call ...")]:
            with self.subTest(text=text):
                self.assertEqual(watch.masked(text), kept)

    def test_masked_keeps_dates_and_prices(self):
        for text in ["2026-01-05", "05.01.2026", "1 500 EUR", "12:30", "1000000 views"]:
            with self.subTest(text=text):
                self.assertEqual(watch.masked(text), text)

    def test_the_mask_is_the_browsers_mask(self):
        js = (watch.ROOT / "scripts/hooks/trend_reader.py").read_text(encoding="utf-8")
        for pattern in [watch.MENTION.pattern, watch.PHONE.pattern]:
            with self.subTest(pattern=pattern):
                self.assertIn(f"/{pattern}/g", js)


class Parsers(Case):
    def test_loudness_from_the_summary_not_the_running_lines(self):
        self.assertEqual(watch.parse_loudness(EBUR128), {"integrated_lufs": -15.0, "range_lu": 5.0, "true_peak_dbfs": -1.5})

    def test_silence_has_no_peak_to_write(self):
        found = watch.parse_loudness("Summary:\n    I:         -70.0 LUFS\n    LRA:         0.0 LU\n    Peak:       -inf dBFS\n")
        self.assertEqual(found, {"integrated_lufs": -70.0, "range_lu": 0.0, "true_peak_dbfs": None})
        json.dumps(found, allow_nan=False)

    def test_no_summary_is_no_numbers(self):
        self.assertEqual(watch.parse_loudness("nothing"), dict.fromkeys(watch.LOUD_KEYS))

    def quiet(self, *spikes, base=0.0002):
        """10 seconds at 30 frames a second."""
        scores = {round(time_ * 30): score for time_, score in spikes}
        return [(index / 30, scores.get(index, base)) for index in range(300)]

    def test_a_spike_is_a_cut_far_under_ffmpegs_usual_threshold(self):
        self.assertEqual(watch.pick_cuts(self.quiet((2, 0.06), (5, 0.13))), [2, 5])

    def test_steady_motion_isnt_a_cut_but_a_spike_out_of_it_is(self):
        self.assertEqual(watch.pick_cuts(self.quiet(base=0.06)), [])
        self.assertEqual(watch.pick_cuts(self.quiet((4, 0.24), base=0.02)), [4])

    def test_a_small_flicker_under_the_floor_isnt_a_cut(self):
        self.assertEqual(watch.pick_cuts(self.quiet((4, 0.04))), [])

    def test_spikes_a_frame_apart_are_one_cut_at_the_stronger(self):
        for first, second, kept in [(0.36, 0.13, 4), (0.13, 0.36, 4 + 1 / 30)]:
            scores = self.quiet((4, first), (4 + 1 / 30, second))
            self.assertEqual(watch.pick_cuts(scores), [kept])

    def test_scene_changes_at_the_very_start_or_end_arent_cuts(self):
        spikes = {1: 0.9, 80: 0.8, 240: 0.7, 741: 1.0}  # 0.05, 4, 12 and 37.05 s
        stdout = "".join(f"frame:{frame} pts:{frame} pts_time:{frame / 20}\nlavfi.scene_score={spikes.get(frame, 0.0002):.6f}\n"
                         for frame in range(742))
        result = subprocess.CompletedProcess([], 0, stdout, "")
        with mock.patch.object(watch, "ffmpeg", lambda *args: result):
            self.assertEqual(watch.scene_cuts(Path("v.mp4"), 37.07), [4.0, 12.0])

    def test_ocr_keeps_confident_words_and_lines_with_a_real_word(self):
        self.assertEqual(watch.tsv_lines(TSV), ["Guten Morgen"])

    def test_words_per_minute_runs_over_the_spoken_span(self):
        words = [{"start": i + 1.0, "end": i + 1.5} for i in range(6)]
        self.assertEqual(watch.speech_numbers(words), {"words": 6, "words_per_minute": 65.5, "first_word_seconds": 1.0})

    def test_too_few_words_have_no_rate(self):
        self.assertEqual(watch.speech_numbers([{"start": 1.0, "end": 1.2}])["words_per_minute"], None)
        self.assertEqual(watch.speech_numbers([]), {"words": 0, "words_per_minute": None, "first_word_seconds": None})

    def test_sound_kinds(self):
        for args, kind in [((False, None, 0, 10.0), "no_audio"), ((True, -70.0, 0, 10.0), "silent"),
                           ((True, -14.0, 100, 40.0), "speech"), ((True, -14.0, 3, 60.0), "music_or_other"),
                           ((True, -14.0, 0, 10.0), "music_or_other"), ((True, None, 40, 40.0), "speech")]:
            with self.subTest(args=args):
                self.assertEqual(watch.sound_kind(*args), kind)


class BrokenDown(Case):
    """A label over a style note wasn't watched; a full breakdown with one was."""
    def write(self, code, text):
        folder = self.measured(code)
        (folder / "breakdown.md").write_text(text, encoding="utf-8")
        return folder

    def test_a_style_only_placeholder_is_not_done(self):
        folder = self.write("aaaaa", f"format: Talking head: screen demo\n{STYLE_ONLY}\n")
        self.assertFalse(watch.is_broken_down(folder))
        self.assertTrue(watch.is_ready(folder))

    def test_a_full_breakdown_is_done(self):
        folder = self.measured("aaaaa", "Skit: two people")
        self.assertTrue(watch.is_broken_down(folder))
        self.assertFalse(watch.is_ready(folder))

    def test_a_full_breakdown_with_a_style_note_is_done(self):
        folder = self.write("aaaaa", f"format: Skit: two people\n\n{STYLE_ONLY}\n\n{BREAKDOWN}")
        (folder / "style.md").write_text("# Style\n", encoding="utf-8")
        self.assertTrue(watch.is_broken_down(folder))

    def test_a_missing_section_is_not_done_and_either_dash_in_the_hook_counts(self):
        self.assertFalse(watch.is_broken_down(self.write("aaaaa", "format: Skit: x\n\n" + BREAKDOWN.replace("## Caveats\n", ""))))
        self.assertTrue(watch.is_broken_down(self.write("aaaaa", "format: Skit: x\n\n" + BREAKDOWN.replace("0–3", "0-3"))))

    def test_no_file_or_one_that_isnt_text_is_not_done(self):
        folder = self.measured("aaaaa")
        self.assertFalse(watch.is_broken_down(folder))
        (folder / "breakdown.md").write_bytes(b"\xff" + BREAKDOWN.encode())
        self.assertFalse(watch.is_broken_down(folder))

    def test_prepare_counts_a_placeholder_as_ready_and_fetches_nothing_for_it(self):
        self.write("bbbbb", f"format: Skit: two people\n{STYLE_ONLY}\n")
        code, out = self.prepare(count=1)
        self.assertEqual((code, self.fetched), (0, []))
        self.assertIn("nothing to prepare", out)

    def test_the_sections_are_the_reel_analysts_template(self):
        page = (watch.ROOT / ".claude/agents/marketing/reel-analyst.md").read_text(encoding="utf-8")
        template = page.split("## The breakdown", 1)[1].split("```")[1]
        headings = [line[3:] for line in template.splitlines() if line.startswith("## ")]
        self.assertEqual(len(headings), len(watch.SECTIONS))
        self.assertTrue(all(heading.startswith(name) for heading, name in zip(headings, watch.SECTIONS)), headings)


class Labels(Case):
    def text(self):
        return self.csv.read_text(encoding="utf-8")

    def label(self):
        out = io.StringIO()
        with redirect_stdout(out):
            code = watch.label(self.root, WEEK)
        return code, out.getvalue()

    def test_replaces_a_cover_label_in_every_row_of_that_week_only(self):
        self.posts([self.row("aaaaa", 1.0, label="cover guess"), self.row("aaaaa", 2.0), self.row("bbbbb", 3.0, label="cover guess"),
                    self.row("aaaaa", 4.0, week="2026-W04", label="older")])
        self.measured("aaaaa", "Talking head: screen demo")
        self.assertEqual(self.label()[0], 0)
        lines = self.text().splitlines()
        self.assertEqual(lines[1].split(",")[13], "Talking head: screen demo")
        self.assertEqual(lines[2].split(",")[13], "Talking head: screen demo")
        self.assertEqual(lines[3].split(",")[13], "cover guess")
        self.assertEqual(lines[4].split(",")[13], "older")

    def test_other_rows_stay_byte_for_byte_and_only_a_labelled_short_row_is_padded(self):
        short = "2026-01-05,2026-W05,instagram,acc,100,10,ddddd,https://x/ddddd,100,1.0,3,recent,,,no"
        self.posts([self.row("aaaaa", 1.0), short, short.replace("ddddd", "eeeee")])
        self.measured("eeeee", "Skit: two people")
        self.label()
        lines = self.text().splitlines()
        self.assertEqual(lines[1], self.row("aaaaa", 1.0))
        self.assertEqual(lines[2], short)
        self.assertEqual(lines[3].split(",")[13], "Skit: two people")
        self.assertEqual(len(lines[3].split(",")), 16)

    def test_a_comma_in_a_label_stays_one_field(self):
        self.measured("aaaaa", "Skit: two people, one door")
        self.label()
        self.assertEqual(watch.read_posts(self.root)[1][13], "Skit: two people, one door")

    def test_a_carrier_outside_the_ten_is_refused_and_named(self):
        for wrong in ["skit", "Comedy skit", "skit: POV", "Talking to camera: x", "Skit", "Skit:", "Skit:POV", "Skit: "]:
            with self.subTest(wrong=wrong):
                before = self.text()
                self.measured("aaaaa", wrong)
                code, out = self.label()
                self.assertEqual(code, 1)
                self.assertIn("aaaaa", out)
                self.assertIn("Talking head, Skit", out)
                self.assertEqual(self.text(), before)

    def test_each_of_the_ten_is_taken(self):
        for carrier in watch.CARRIERS:
            with self.subTest(carrier=carrier):
                self.measured("aaaaa", f"{carrier}: one device")
                self.assertEqual(self.label()[0], 0)
                self.assertEqual(watch.read_posts(self.root)[1][13], f"{carrier}: one device")

    def test_a_wrong_label_doesnt_hold_up_a_right_one(self):
        self.posts([self.row("aaaaa", 1.0), self.row("bbbbb", 2.0)])
        self.measured("aaaaa", "Skit: two people")
        self.measured("bbbbb", "Comedy skit")
        code, out = self.label()
        self.assertEqual(code, 1)
        self.assertIn("bbbbb", out)
        self.assertEqual([row[13] for row in watch.read_posts(self.root)[1:]], ["Skit: two people", ""])

    def test_the_ten_are_the_format_engines_word_for_word(self):
        page = (watch.ROOT / "knowledge/marketing/format-engine.md").read_text(encoding="utf-8")
        self.assertIn(", ".join(watch.CARRIERS), page)

    def test_a_wrong_first_line_is_reported_and_writes_nothing(self):
        for first in ["# Breakdown", "format:", "format: " + "x" * 61, "format: skit | series", "format: =1+1", "format: -skit", "format: @skit"]:
            with self.subTest(first=first):
                before = self.text()
                folder = self.measured("aaaaa")
                (folder / "breakdown.md").write_text(f"{first}\n\n{BREAKDOWN}", encoding="utf-8")
                code, out = self.label()
                self.assertEqual(code, 1)
                self.assertIn("first line", out)
                self.assertEqual(self.text(), before)

    def test_a_style_only_placeholders_label_isnt_copied(self):
        self.posts([self.row("aaaaa", 1.0, label="cover guess"), self.row("bbbbb", 2.0)])
        folder = self.measured("aaaaa")
        (folder / "breakdown.md").write_text(f"format: Skit: two people\n{STYLE_ONLY}\n", encoding="utf-8")
        self.measured("bbbbb", "Talking head: screen demo")
        code, out = self.label()
        self.assertEqual(code, 0)
        self.assertIn("from 1 breakdowns", out)
        self.assertEqual([row[13] for row in watch.read_posts(self.root)[1:]], ["cover guess", "Talking head: screen demo"])

    def test_a_label_is_one_line(self):
        folder = self.measured("aaaaa")
        (folder / "breakdown.md").write_text("format: skit\ninjected,row\n", encoding="utf-8")
        self.assertEqual(watch.format_label(folder / "breakdown.md"), "skit")


class Listings(Case):
    def output(self, function, *args):
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(function(self.root, WEEK, *args), 0)
        return out.getvalue()

    def test_next_lists_only_reels_measured_without_a_breakdown(self):
        self.measured("aaaaa", "skit")
        self.measured("bbbbb")
        out = self.output(watch.next_up, 10)
        self.assertIn("1 ready for a breakdown", out)
        self.assertIn("bbbbb", out)
        self.assertNotIn("aaaaa", out)

    def test_next_shows_each_reels_age(self):
        self.measured("aaaaa")
        self.measured("bbbbb")
        self.posts([self.row("aaaaa", 5.0, age="recent"), self.row("bbbbb", 3.0, age="old")])
        lines = self.output(watch.next_up, 10).splitlines()
        self.assertIn("  recent  ", next(line for line in lines if line.startswith("aaaaa")))
        self.assertIn("  old  ", next(line for line in lines if line.startswith("bbbbb")))

    def test_status_counts_each_stage(self):
        self.measured("aaaaa", "skit")
        self.posts([self.row("aaaaa", 1.0, label="skit"), self.row("bbbbb", 5.0), self.row("ccccc", 3.0)])
        (self.base / "bbbbb").mkdir()
        (self.base / "bbbbb/failed.txt").write_text("gone\n")
        out = self.output(watch.status)
        self.assertIn(f"{WEEK}: 3 reels, 1 to go (neither broken down nor failed).", out)
        self.assertIn("recent: 3 reels, 0 downloaded, 1 measured, 1 broken down, 1 labelled, 1 failed, 1 to go.", out)
        self.assertIn("old: 0 reels, 0 downloaded, 0 measured, 0 broken down, 0 labelled, 0 failed, 0 to go.", out)

    def test_status_splits_recent_from_old(self):
        self.posts([self.row("aaaaa", 1.0), self.row("bbbbb", 5.0), self.row("ooooo", 300.5, age="old"), self.row("ppppp", 2.0, age=""),
                    self.row("qqqqq", 3.0, age="old")])
        self.measured("aaaaa", "skit")
        (self.base / "ooooo").mkdir()
        (self.base / "ooooo/failed.txt").write_text("gone\n")
        out = self.output(watch.status)
        self.assertIn(f"{WEEK}: 5 reels, 3 to go", out)
        self.assertIn("recent: 2 reels, 0 downloaded, 1 measured, 1 broken down, 0 labelled, 0 failed, 1 to go.", out)
        self.assertIn("old: 3 reels, 0 downloaded, 0 measured, 0 broken down, 0 labelled, 1 failed, 2 to go.", out)

    def test_old_reels_downloaded_count_only_on_the_old_line(self):
        self.posts([self.row("aaaaa", 1.0), self.row("bbbbb", 5.0), self.row("ccccc", 3.0), self.row("ooooo", 9.0, age="old"),
                    self.row("ppppp", 8.0, age="old")])
        for code in ["bbbbb", "ooooo", "ppppp"]:
            (self.measured(code) / "video.mp4").write_bytes(b"x")
        for code in ["ooooo", "ppppp"]:
            (self.base / code / "breakdown.md").write_text(f"format: Skit: two people\n{STYLE_ONLY}\n", encoding="utf-8")
        out = self.output(watch.status)
        self.assertIn(f"{WEEK}: 5 reels, 5 to go", out)
        self.assertIn("recent: 3 reels, 1 downloaded, 1 measured, 0 broken down, 0 labelled, 0 failed, 3 to go.", out)
        self.assertIn("old: 2 reels, 2 downloaded, 2 measured, 0 broken down, 0 labelled, 0 failed, 2 to go.", out)

    def test_a_style_only_placeholder_is_still_to_go_and_out_of_the_table(self):
        self.posts([self.row("aaaaa", 1.0, label="Skit: two people"), self.row("bbbbb", 5.0, label="Talking head: screen demo")])
        folder = self.measured("aaaaa")  # its label was copied before the rule
        (folder / "breakdown.md").write_text(f"format: Skit: two people\n{STYLE_ONLY}\n", encoding="utf-8")
        self.measured("bbbbb", "Talking head: screen demo")
        out = self.output(watch.next_up, 10)
        self.assertIn("1 ready for a breakdown", out)
        self.assertIn("aaaaa", out)
        self.assertNotIn("bbbbb", out)
        out = self.output(watch.status)
        self.assertIn("recent: 2 reels, 0 downloaded, 2 measured, 1 broken down, 1 labelled, 0 failed, 1 to go.", out)
        out = self.output(watch.table)
        self.assertIn("1 of 2 reels", out)
        self.assertNotIn("Skit", out)

    def test_status_prints_a_stored_stop(self):
        self.assertNotIn("stopped:", self.output(watch.status))
        (self.base / watch.STOPPED).write_text("stopped: spend cap reached\n")
        self.assertIn("stopped: spend cap reached", self.output(watch.status))

    def test_status_and_table_still_read_an_older_weeks_labels(self):
        self.measured("aaaaa", "skit")
        self.posts([self.row("aaaaa", 1.0, label="skit")])
        self.assertIn("1 labelled", self.output(watch.status))
        self.assertIn("| skit | 1 |", self.output(watch.table))

    def test_table_weighs_each_format_by_views_against_the_accounts_median(self):
        self.measured("aaaaa", "skit")
        self.measured("ccccc", "skit")
        self.measured("bbbbb", "talking head")
        out = self.output(watch.table)
        self.assertIn("3 of 3 reels", out)
        self.assertIn("| skit | 2 | 1 | 2.0 | 3 | 3.0 | 4.0 | 150.0 | 2/2 | ccccc aaaaa |", out)
        self.assertLess(out.index("talking head"), out.index("| skit"))

    def test_old_reels_print_apart_and_each_format_counts_its_accounts(self):
        self.posts([self.row("aaaaa", 2.0, account="one"), self.row("bbbbb", 4.0, account="two"), self.row("ccccc", 6.0, account="one"),
                    self.row("ooooo", 300.5, account="one", age="old"), self.row("ppppp", 100.0, account="two", age="old"),
                    self.row("qqqqq", 1.0, age="")])
        for code in ["aaaaa", "bbbbb", "ccccc", "ooooo", "ppppp", "qqqqq"]:
            self.measured(code, "skit")
        recent, old = self.output(watch.table).split("Old, ")
        self.assertIn("6 of 6 reels", recent)
        self.assertIn("Recent, 3: the patterns.", recent)
        self.assertIn("| skit | 3 | 2 | 4.0 | 6 |", recent)
        self.assertNotIn("ooooo", recent)
        self.assertTrue(old.startswith("3: apart"))
        self.assertIn("| skit | 3 | 3 | 100.0 | 300.5 |", old)
        self.assertNotIn("ccccc", old)


class Commands(Case):
    def test_takes_a_week_not_a_url_or_a_path(self):
        for argv in [["prepare", "--week", "https://example.com/"], ["status", "--week", "../x"], ["next", "--week", "2026-W05\n"]]:
            with self.subTest(argv=argv), self.assertRaises(SystemExit):
                watch.main(argv, self.root)

    def test_prepare_is_refused_where_public_downloads_are_off(self):
        for settings in ("{}", '{"integrations": {"marketing": {"public_downloads": false}}}', None):
            if settings is None:
                (self.root / "company.json").unlink()
            else:
                (self.root / "company.json").write_text(settings)
            with self.subTest(settings=settings), self.assertRaisesRegex(SystemExit, "public site is off"):
                watch.main(["prepare", "--week", WEEK], self.root)

    def test_there_is_no_url_flag(self):
        with self.assertRaises(SystemExit), mock.patch("sys.stderr", io.StringIO()):
            watch.main(["prepare", "--week", WEEK, "--url", "https://example.com/"], self.root)

    def test_runs_end_to_end_from_the_command_line_parser(self):
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(watch.main(["status", "--week", WEEK], self.root), 0)
        self.assertIn("3 reels", out.getvalue())

    def test_recent_only_comes_through_from_the_command_line(self):
        for argv, expected in [([], False), (["--recent-only"], True)]:
            with self.subTest(argv=argv), mock.patch.object(watch, "prepare", return_value=0) as called:
                watch.main(["prepare", "--week", WEEK, "--count", "3", *argv], self.root)
                self.assertEqual(called.call_args.args, (self.root, WEEK, 3, False))
                self.assertEqual(called.call_args.kwargs, {"recent_only": expected})

    def test_measure_takes_only_a_file_under_media(self):
        media = self.root / watch.MEDIA
        media.mkdir(parents=True)
        outside = self.root / "workspaces/marketing/sources/x.mp4"
        outside.parent.mkdir()
        outside.write_bytes(b"x")
        (media / "linked.mp4").symlink_to(outside)
        for file in [outside, media / "../sources/x.mp4", media / "linked.mp4", media / "missing.mp4", media]:
            with self.subTest(file=file), self.assertRaises(SystemExit) as refused:
                watch.main(["measure", "--file", str(file)], self.root)
            self.assertIn("refused", str(refused.exception))

    def test_measure_needs_a_file_and_takes_no_week(self):
        for argv in [["measure"], ["measure", "--week", WEEK]]:
            with self.subTest(argv=argv), self.assertRaises(SystemExit), mock.patch("sys.stderr", io.StringIO()):
                watch.main(argv, self.root)

    def test_longest_shot_counts_the_first_and_the_last(self):
        self.assertEqual(watch.longest_shot([], 8.0), 8.0)
        self.assertEqual(watch.longest_shot([4.5, 5.0], 6.0), 4.5)
        self.assertEqual(watch.longest_shot([1.0, 2.0], 6.0), 4.0)


class ScribeSend(unittest.TestCase):
    def body(self, language_code):
        with tempfile.TemporaryDirectory() as folder:
            audio = Path(folder) / "audio.wav"
            audio.write_bytes(b"RIFF")
            seen = {}

            class Reply(io.BytesIO):
                def __enter__(self):
                    return self

                def __exit__(self, *args):
                    return False

            def urlopen(request, timeout=None):
                seen["body"] = request.data
                return Reply(b"{}")

            with mock.patch.object(scribe.urllib.request, "urlopen", urlopen):
                scribe.scribe_send(audio, language_code, "fake-key")
            return seen["body"]

    def test_no_language_leaves_the_field_out_so_scribe_detects_it(self):
        self.assertNotIn(b"language_code", self.body(None))

    def test_a_language_is_sent(self):
        self.assertIn(b'name="language_code"\r\n\r\ndeu', self.body("deu"))

    def test_the_alarm_gets_what_is_left_of_the_reels_time_and_is_cleared(self):
        seen = []

        def scribe_post(audio, language_code, key):
            seen.append(signal.getitimer(signal.ITIMER_REAL)[0])
            return BODY

        handler = signal.getsignal(signal.SIGALRM)
        with mock.patch.object(scribe, "scribe_post", scribe_post), mock.patch.object(watch, "reel_time", lambda: 75.0):
            self.assertEqual(watch.send_audio(Path("audio.wav"), None, "fake-key"), BODY)
        self.assertTrue(74 < seen[0] <= 75)
        self.assertEqual(signal.getitimer(signal.ITIMER_REAL), (0.0, 0.0))
        self.assertEqual(signal.getsignal(signal.SIGALRM), handler)

    def test_no_time_left_sends_nothing(self):
        with mock.patch.object(watch, "reel_time", lambda: 0.0), self.assertRaisesRegex(watch.ReelError, "out of time"):
            watch.send_audio(Path("no-such-file.wav"), None, "fake-key")

    def test_the_post_returns_the_bytes_as_they_came(self):
        with tempfile.TemporaryDirectory() as folder:
            audio = Path(folder) / "audio.wav"
            audio.write_bytes(b"RIFF")
            reply = mock.MagicMock()
            reply.__enter__.return_value.read.return_value = b"{not json"
            with mock.patch.object(scribe.urllib.request, "urlopen", lambda request, timeout: reply):
                self.assertEqual(scribe.scribe_post(audio, None, "fake-key"), b"{not json")
                with self.assertRaises(ValueError):
                    scribe.scribe_send(audio, None, "fake-key")

    def test_a_reply_that_keeps_trickling_in_is_cut_at_the_reels_time(self):
        def trickle(handler):
            handler.send_response(200)
            handler.send_header("Content-Length", "1000000")
            handler.end_headers()
            try:
                for _ in range(250):  # each read gets a byte, so a socket's timeout never fires
                    handler.wfile.write(b" ")
                    handler.wfile.flush()
                    time.sleep(0.02)
            except OSError:
                pass

        local_scribe(self, trickle)
        with tempfile.TemporaryDirectory() as folder:
            audio = Path(folder) / "audio.wav"
            audio.write_bytes(b"RIFF")
            started = time.monotonic()
            with mock.patch.object(watch, "reel_time", lambda: 0.3), self.assertRaisesRegex(watch.ReelError, "out of time"):
                watch.send_audio(audio, None, "fake-key")
        self.assertLess(time.monotonic() - started, 3)


@unittest.skipUnless(fetch.FFMPEG.exists(), "the bundled ffmpeg isn't installed here")
class RealFfmpeg(Case):
    def clip(self, code, seconds, audio):
        folder = self.base / code
        folder.mkdir(parents=True)
        inputs = ["-f", "lavfi", "-i", f"testsrc=size=270x480:rate=10:duration={seconds}"]
        if audio:
            inputs += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}"]
        subprocess.run([str(fetch.FFMPEG), "-hide_banner", "-nostdin", "-y", *inputs, "-c:v", "mpeg4", "-c:a", "aac", "-f", "mp4",
                        str(folder / "video.mp4")], capture_output=True, check=True)
        (folder / "video.info.json").write_text(json.dumps({"description": "the caption @someone"}))
        return folder

    def spend_units(self):
        return [json.loads(line) for line in (self.root / "workspaces/marketing/spend.jsonl").read_text().splitlines()][-1]["units"]

    def run_measure(self, folder, send=None):
        reel = {"code": folder.name, "account": "acc", "views": 100.0, "multiple": 2.0}
        return watch.measure(folder, reel, WEEK, self.root, send=send or (lambda *args: BODY), token=lambda: "fake-key")

    def test_a_reel_with_sound_gets_every_file_and_no_frames_or_audio_stay(self):
        folder = self.clip("aaaaa", 5, True)
        metrics = self.run_measure(folder)
        self.assertEqual(metrics["length_seconds"], 5.0)
        self.assertEqual(metrics["words"], 6)
        self.assertEqual(metrics["sound"], "speech")
        self.assertIsNotNone(metrics["integrated_lufs"])
        self.assertEqual(metrics["sheet_whole"], {"columns": 6, "rows": 2, "seconds_per_tile": 0.5})
        self.assertAlmostEqual(metrics["scribe_seconds"], 5.0, delta=0.1)
        self.assertEqual(json.loads((folder / "metrics.json").read_text())["code"], "aaaaa")
        self.assertIn("-->", (folder / "transcript.srt").read_text(encoding="utf-8"))
        self.assertEqual((folder / "caption.txt").read_text(), "the caption @...\n")
        for name in ["sheet-first3s.jpg", "sheet-whole.jpg", "onscreen.txt", "scribe.json"]:
            self.assertTrue((folder / name).is_file(), name)
        self.assertFalse((folder / "frames").exists())
        self.assertFalse((folder / "audio.wav").exists())

    def measure_a_render(self, audio):
        folder = self.clip("aaaaa", 5, audio)
        media = self.root / watch.MEDIA
        media.parent.mkdir(exist_ok=True)
        media.symlink_to(folder, target_is_directory=True)  # the media folder may be a link
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(watch.main(["measure", "--file", str(media / "video.mp4")], self.root), 0)
        self.assertEqual(sorted(path.name for path in folder.iterdir()), ["video.info.json", "video.mp4"])
        return json.loads(out.getvalue())

    def test_measure_prints_a_renders_numbers_and_writes_nothing(self):
        numbers = self.measure_a_render(True)
        self.assertEqual(numbers["length_seconds"], 5.0)
        self.assertEqual(numbers["longest_shot_seconds"], watch.longest_shot(numbers["cut_times"], 5.0))
        self.assertEqual(numbers["cuts"], len(numbers["cut_times"]))
        self.assertIsNotNone(numbers["integrated_lufs"])
        self.assertIsNotNone(numbers["true_peak_dbfs"])

    def test_measure_of_a_silent_render_has_no_loudness(self):
        numbers = self.measure_a_render(False)
        self.assertIsNone(numbers["integrated_lufs"])

    def test_measure_reports_a_file_ffmpeg_cant_read(self):
        media = self.root / watch.MEDIA
        media.mkdir(parents=True)
        (media / "reel.mp4").write_bytes(b"not a video")
        with self.assertRaises(SystemExit) as refused:
            watch.main(["measure", "--file", str(media / "reel.mp4")], self.root)
        self.assertIn("can't measure it", str(refused.exception))

    def test_a_cut_inside_a_dark_box_is_found(self):
        folder = self.base / "ddddd"
        folder.mkdir(parents=True)
        video = folder / "video.mp4"
        box = "drawbox=x=0:y=150:w=270:h=120:c=0x303030:t=fill:enable='gte(t,1)'"
        subprocess.run([str(fetch.FFMPEG), "-hide_banner", "-nostdin", "-y", "-f", "lavfi", "-i", f"color=c=black:s=270x480:r=30:d=2,{box}",
                        "-c:v", "mpeg4", "-f", "mp4", str(video)], capture_output=True, check=True)
        cuts = watch.scene_cuts(video, 2.0)
        self.assertEqual(len(cuts), 1, cuts)
        self.assertAlmostEqual(cuts[0], 1.0, delta=0.1)

    def test_a_short_silent_clip_still_gets_its_sheets_and_costs_nothing(self):
        folder = self.clip("bbbbb", 2, False)

        def never(*args):
            raise AssertionError("no sound track: nothing to send")

        metrics = self.run_measure(folder, send=never)
        self.assertEqual((metrics["sound"], metrics["scribe_seconds"], metrics["words_per_minute"]), ("no_audio", 0, None))
        self.assertIsNone(metrics["integrated_lufs"])
        json.dumps(metrics, allow_nan=False)
        for name in ["sheet-first3s.jpg", "sheet-whole.jpg"]:
            self.assertGreater((folder / name).stat().st_size, 0, name)

    def test_metadata_cant_shorten_a_reel_or_what_scribe_is_paid_for(self):
        folder = self.base / "eeeee"
        folder.mkdir(parents=True)
        fake = "  Duration: 00:00:01.00, start: 0.0, bitrate: 1 kb/s"
        subprocess.run([str(fetch.FFMPEG), "-hide_banner", "-nostdin", "-y", "-f", "lavfi", "-i", "testsrc=size=270x480:rate=10:duration=4",
                        "-f", "lavfi", "-i", "sine=frequency=440:duration=4", "-c:v", "mpeg4", "-c:a", "aac", "-movflags", "use_metadata_tags",
                        "-metadata", f"comment={fake}", "-metadata", f"x\n{fake}=y", "-metadata:s:v", f"handler_name={fake}",
                        "-f", "mp4", str(folder / "video.mp4")], capture_output=True, check=True)
        self.assertEqual(watch.probe(folder / "video.mp4"), (4.0, True))
        (folder / "video.info.json").write_text("{}")
        self.assertAlmostEqual(self.run_measure(folder)["scribe_seconds"], 4.0, delta=0.1)
        self.assertAlmostEqual(self.spend_units(), 4.0, delta=0.1)

    def test_a_broken_file_is_a_failed_reel_not_a_crash(self):
        folder = self.base / "ccccc"
        folder.mkdir(parents=True)
        (folder / "video.mp4").write_bytes(b"not a video")
        with self.assertRaises(watch.ReelError):
            self.run_measure(folder)

    def test_frames_are_deleted_even_when_reading_them_fails(self):
        folder = self.clip("ddddd", 2, False)
        real_run = subprocess.run

        def tesseract_breaks(command, **kwargs):
            if command[0] == "tesseract":
                raise OSError("tesseract broke")
            return real_run(command, **kwargs)

        with mock.patch.object(watch, "TESSERACT", "tesseract"), mock.patch.object(watch.subprocess, "run", tesseract_breaks), \
                self.assertRaises(OSError):
            watch.on_screen(folder / "video.mp4", folder, 2.0)
        self.assertFalse((folder / "frames").exists())


if __name__ == "__main__":
    unittest.main()
