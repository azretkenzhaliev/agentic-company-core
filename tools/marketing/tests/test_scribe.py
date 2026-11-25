"""Tests for tools/marketing/voice/scribe.py. No network: ElevenLabs, the keychain and ffmpeg are fakes."""

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "voice"))

import scribe  # noqa: E402
import spend  # noqa: E402


def word(text, start, end):
    return {"text": text, "type": "word", "start": start, "end": end, "logprob": -0.1}


def gap(start):
    return {"text": " ", "type": "spacing", "start": start, "end": start, "logprob": 0.0}


# Shaped like Scribe's reply: words[] with spacing between them and an audio event.
REPLY = {
    "language_code": "deu", "language_probability": 0.97, "text": "Was ist heute? Ein Überblick folgt.",
    "words": [
        word("Was", 0.10, 0.50), gap(0.50), word("ist", 0.55, 0.80), gap(0.80), word("heute?", 0.85, 1.30),
        {"text": "(laughter)", "type": "audio_event", "start": 1.3, "end": 1.9, "logprob": 0.0},
        word("Ein", 2.00, 2.30), gap(2.30), word("Überblick", 2.35, 2.90), gap(2.90), word("folgt.", 2.95, 3.40),
    ],
}


class ScribeCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.marketing = self.root / "workspaces/marketing"
        self.audio = self.marketing / "swipe/reel/audio.wav"
        self.audio.parent.mkdir(parents=True)
        self.audio.write_bytes(b"RIFF")
        self.caps(60)
        (self.root / "company.json").write_text(json.dumps({"integrations": {"marketing": {"languages": {
            "en": {"name": "English", "scribe": "eng"}, "de": {"name": "German", "scribe": "deu"}}}}}))
        self.sent, self.keys = [], []
        self.elsewhere = tempfile.TemporaryDirectory()  # outside the repo, like a synced folder

    def tearDown(self):
        self.tmp.cleanup()
        self.elsewhere.cleanup()

    def caps(self, seconds):
        path = self.root / spend.CAPS
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({**{tool: None for tool in spend.UNITS}, "elevenlabs_stt_seconds": seconds}))

    def send(self, audio, language_code, api_key):
        self.sent.append((audio, language_code, api_key))
        return REPLY

    def token(self):
        self.keys.append(1)
        return "fake-key"

    def run_main(self, argv, send=None):
        err = io.StringIO()
        with redirect_stderr(err), redirect_stdout(io.StringIO()):
            code = scribe.main(argv, send=send or self.send, token=self.token, seconds=lambda p: 3.4, root=self.root)
        return code, err.getvalue()

    def log(self):
        path = self.root / spend.LOG
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


class Paths(ScribeCase):
    def test_refuses_files_outside_workspaces_marketing(self):
        outside = self.root / "knowledge/private.wav"
        outside.parent.mkdir(parents=True)
        outside.write_bytes(b"RIFF")
        linked = self.marketing / "inbox/note.wav"  # a link inside that points elsewhere
        linked.parent.mkdir(parents=True)
        linked.symlink_to(outside)
        for audio in [outside, self.marketing / "../../knowledge/private.wav", linked]:
            with self.subTest(audio=audio):
                code, err = self.run_main([str(audio), "--lang", "de", "--out", str(self.marketing / "media/t")])
                self.assertEqual(code, 1)
                self.assertIn("outside workspaces/marketing/", err)
        self.assertEqual((self.sent, self.keys), ([], []))

    def test_writes_only_under_media_or_swipe(self):
        (self.marketing / "media/link").parent.mkdir(parents=True)
        (self.marketing / "media/link").symlink_to(self.elsewhere.name)
        for out in [self.root / "knowledge", self.marketing / "../elsewhere", self.marketing / "inbox",
                    self.marketing / "corpus/a", self.marketing / "books", self.marketing,
                    self.marketing / "media/../inbox", self.marketing / "media/link/t"]:
            with self.subTest(out=out):
                code, err = self.run_main([str(self.audio), "--lang", "de", "--out", str(out)])
                self.assertEqual(code, 1)
                self.assertIn("transcripts go only to workspaces/marketing/media/ or workspaces/marketing/swipe/", err)
        self.assertEqual((self.sent, self.keys), ([], []))
        self.assertEqual(list(Path(self.elsewhere.name).iterdir()), [])

    def test_folders_linked_out_of_the_repo_count(self):
        synced = Path(self.elsewhere.name)
        (synced / "Inbox").mkdir()
        (synced / "Inbox/note.wav").write_bytes(b"RIFF")
        (synced / "media").mkdir()
        (self.marketing / "inbox").symlink_to(synced / "Inbox")
        (self.marketing / "media").symlink_to(synced / "media")
        code, err = self.run_main([str(self.marketing / "inbox/note.wav"), "--lang", "en",
                                   "--out", str(self.marketing / "media/founder/demo/2026-W05/a")])
        self.assertEqual(code, 0, err)
        self.assertTrue((synced / "media/founder/demo/2026-W05/a/note.srt").is_file())

    def test_a_language_company_json_doesnt_name_is_refused(self):
        for settings in (None, {"languages": {"de": {"name": "German"}}}):
            if settings is None:
                (self.root / "company.json").unlink()
            else:
                (self.root / "company.json").write_text(json.dumps({"integrations": {"marketing": settings}}))
            with self.assertRaises(SystemExit):
                self.run_main([str(self.audio), "--lang", "de", "--out", str(self.marketing / "media/t")])
        self.assertEqual((self.sent, self.keys), ([], []))

    def test_never_overwrites_a_transcript(self):
        out = self.marketing / "swipe/reel"
        self.assertEqual(self.run_main([str(self.audio), "--lang", "de", "--out", str(out)])[0], 0)
        (out / "audio.txt").unlink()  # the .srt alone still blocks
        code, err = self.run_main([str(self.audio), "--lang", "de", "--out", str(out)])
        self.assertEqual(code, 1)
        self.assertIn("audio.srt exists", err)
        (out / "audio.srt").unlink()  # so do the word timings alone
        code, err = self.run_main([str(self.audio), "--lang", "de", "--out", str(out)])
        self.assertEqual(code, 1)
        self.assertIn("audio.words.json exists", err)
        self.assertEqual(len(self.sent), 1)
        self.assertEqual(len(self.log()), 2, "the refused runs reserved nothing")


class Transcribe(ScribeCase):
    def test_writes_transcript_and_srt_and_logs_seconds(self):
        out = self.marketing / "swipe/reel"
        code, err = self.run_main([str(self.audio), "--lang", "de", "--out", str(out)])
        self.assertEqual(code, 0, err)
        self.assertEqual(self.sent, [(self.audio, "deu", "fake-key")])
        self.assertEqual((out / "audio.txt").read_text(), REPLY["text"] + "\n")
        self.assertEqual((out / "audio.srt").read_text(),
                         "1\n00:00:00,100 --> 00:00:01,300\nWas ist heute?\n\n"
                         "2\n00:00:02,000 --> 00:00:03,400\nEin Überblick folgt.\n\n")
        timings = json.loads((out / "audio.words.json").read_text(encoding="utf-8"))
        self.assertEqual(timings[:2], [{"text": "Was", "start": 0.10, "end": 0.50}, {"text": "ist", "start": 0.55, "end": 0.80}])
        self.assertEqual(len(timings), 6, "words only: no spacing, no audio event")
        reserved, outcome = self.log()
        self.assertEqual({k: outcome[k] for k in ("kind", "tool", "model", "units", "unit", "ok", "brand")},
                         {"kind": "done", "tool": "elevenlabs_stt_seconds", "model": "scribe_v2", "units": 3.4,
                          "unit": "seconds", "ok": True, "brand": None})
        self.assertEqual((reserved["kind"], reserved["id"], reserved["units"]), ("reserve", outcome["id"], 3.4))

    def test_another_language_is_sent_as_its_code(self):
        self.run_main([str(self.audio), "--lang", "en", "--out", str(self.marketing / "media/t")])
        self.assertEqual(self.sent[0][1], "eng")

    def test_cap_refuses_before_any_send(self):
        self.caps(3)
        code, err = self.run_main([str(self.audio), "--lang", "de", "--out", str(self.marketing / "media/t")])
        self.assertEqual(code, 1)
        self.assertIn("would pass the cap", err)
        self.assertEqual((self.sent, self.keys, self.log()), ([], [], []))

    def test_a_failed_call_is_logged_not_ok(self):
        def broken(*args):
            raise OSError("network down")
        code, err = self.run_main([str(self.audio), "--lang", "de", "--out", str(self.marketing / "media/t"),
                                   "--brand", "founder/demo", "--week", "2026-W05", "--piece", "p"], send=broken)
        self.assertEqual(code, 1)
        self.assertIn("network down", err)
        self.assertEqual([(e["kind"], e.get("ok"), e["units"], e["brand"]) for e in self.log()],
                         [("reserve", None, 3.4, "founder/demo"), ("done", False, 3.4, "founder/demo")])


class CaptionLines(unittest.TestCase):
    def test_lines_stay_within_42_characters_and_2_5_seconds(self):
        words = [word(w, i * 0.3, i * 0.3 + 0.25) for i, w in enumerate(("für " * 40).split())]
        words += [word("ü" * 12, 20 + i * 0.1, 20.05 + i * 0.1) for i in range(6)]  # the 42 characters bind
        lines = scribe.caption_lines(words)
        self.assertEqual(sum(len(line["text"].split()) for line in lines), len(words))
        for line in lines:
            self.assertLessEqual(len(line["text"]), scribe.MAX_CHARS)
            self.assertLessEqual(line["end"] - line["start"], scribe.MAX_SECONDS)

    def test_skips_spacing_audio_events_and_untimed_words(self):
        lines = scribe.caption_lines([gap(0), {"text": "(music)", "type": "audio_event", "start": 0, "end": 1},
                                      {"text": "x", "type": "word", "start": None, "end": None}, word("ok", 1, 1.2)])
        self.assertEqual([line["text"] for line in lines], ["ok"])

    def test_word_timings_are_stripped_and_keep_only_timed_words(self):
        self.assertEqual(scribe.spoken_words([gap(0), word(" ok ", 1, 1.2), {"text": "x", "type": "word", "start": None, "end": 1}]),
                         [{"text": "ok", "start": 1, "end": 1.2}])

    def test_srt_stamps(self):
        self.assertEqual(scribe.to_srt([{"start": 3725.5, "end": 3726.04, "text": "a"}]),
                         "1\n01:02:05,500 --> 01:02:06,040\na\n\n")


if __name__ == "__main__":
    unittest.main()
