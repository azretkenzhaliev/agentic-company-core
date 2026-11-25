"""Tests for tools/marketing/voice/tts.py. No network: ElevenLabs and the keychain are fakes."""

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "voice"))

import spend  # noqa: E402
import tts  # noqa: E402


SHIPPED = tts.GRANTED


class TtsCase(unittest.TestCase):
    def setUp(self):
        granted = mock.patch.object(tts, "GRANTED", True)
        granted.start()
        self.addCleanup(granted.stop)
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.folder = self.root / "workspaces/marketing/media/founder/demo/2026-W05/lake-dawn"
        self.text = self.folder / "voiceover.txt"
        self.text.parent.mkdir(parents=True)
        self.text.write_text("What is new today?\n", encoding="utf-8")
        caps = self.root / spend.CAPS
        caps.parent.mkdir(parents=True)
        caps.write_text(json.dumps({**{tool: None for tool in spend.UNITS}, "elevenlabs_tts_characters": 1000}))
        (self.root / "company.json").write_text(json.dumps({"integrations": {"marketing": {"brands": {
            "founder/demo": {"voice_over": True}, "founder/acme": {}}}}}))
        self.sent = []

    def tearDown(self):
        self.tmp.cleanup()

    def send(self, text, voice, model, api_key):
        self.sent.append((text, voice, model, api_key))
        return b"ID3fake-mp3"

    def run_main(self, text=None, brand="founder/demo", category="premade"):
        argv = [str(text or self.text), "--voice", "v1", "--model", "eleven_v4", "--brand", brand,
                "--week", "2026-W05", "--piece", "lake-dawn"]
        err = io.StringIO()
        with redirect_stderr(err), redirect_stdout(io.StringIO()):
            code = tts.main(argv, send=self.send, token=lambda: "fake-key", root=self.root,
                            lookup=lambda voice, key: category)
        return code, err.getvalue()

    def assertRefusedUnpaid(self, code, err, words):
        self.assertEqual(code, 1)
        self.assertIn(words, err)
        self.assertEqual(self.sent, [])
        self.assertFalse((self.root / spend.LOG).exists())


class Grant(TtsCase):
    def test_ships_ungranted(self):
        with mock.patch.object(tts, "GRANTED", SHIPPED):
            self.assertIs(tts.GRANTED, False)
            self.assertRefusedUnpaid(*self.run_main(), "hasn't granted")

    def test_refuses_a_brand_the_board_didnt_grant(self):
        self.assertRefusedUnpaid(*self.run_main(brand="founder/acme"), "founder/demo only")
        (self.root / "company.json").unlink()
        self.assertRefusedUnpaid(*self.run_main(), "no brand only")

    def test_refuses_any_voice_but_a_stock_one(self):
        for category in ["cloned", "professional", "famous", "generated", "None"]:
            with self.subTest(category=category):
                self.assertRefusedUnpaid(*self.run_main(category=category), "premade")


class Granted(TtsCase):
    def test_writes_mp3_and_logs_characters(self):
        code, err = self.run_main()
        self.assertEqual(code, 0, err)
        self.assertEqual(self.sent, [("What is new today?", "v1", "eleven_v4", "fake-key")])
        self.assertEqual((self.folder / "voiceover.mp3").read_bytes(), b"ID3fake-mp3")
        reserved, outcome = [json.loads(x) for x in (self.root / spend.LOG).read_text().splitlines()]
        self.assertEqual((reserved["kind"], reserved["units"]), ("reserve", 18))
        self.assertEqual((outcome["kind"], outcome["tool"], outcome["units"], outcome["unit"], outcome["ok"]),
                         ("done", "elevenlabs_tts_characters", 18, "characters", True))

    def test_reads_the_text_only_from_workspaces_marketing_media(self):
        with tempfile.TemporaryDirectory() as elsewhere:
            secret = Path(elsewhere) / "notes.txt"
            secret.write_text("private\n", encoding="utf-8")
            linked = self.folder / "linked.txt"  # a link inside media that points elsewhere
            linked.symlink_to(secret)
            scripts = self.root / "workspaces/marketing/scripts/voiceover.txt"
            scripts.parent.mkdir(parents=True)
            scripts.write_text("Today\n", encoding="utf-8")
            for text in [secret, linked, scripts, self.folder / "../../../../../scripts/voiceover.txt"]:
                with self.subTest(text=text):
                    code, err = self.run_main(text)
                    self.assertEqual(code, 1)
                    self.assertIn("outside workspaces/marketing/media/", err)
        self.assertEqual(self.sent, [])
        self.assertFalse((self.root / spend.LOG).exists())

    def test_never_overwrites_a_paid_file(self):
        self.run_main()
        code, err = self.run_main()
        self.assertEqual(code, 1)
        self.assertIn("exists", err)
        self.assertEqual(len(self.sent), 1)


if __name__ == "__main__":
    unittest.main()
