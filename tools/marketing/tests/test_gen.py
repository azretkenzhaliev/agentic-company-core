"""Tests for tools/marketing/gen/ (image.py, video.py, gemini.py). No network: Gemini and the keychain are fakes."""

import base64
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "gen"))

import gemini  # noqa: E402
import image  # noqa: E402
import spend  # noqa: E402
import video  # noqa: E402

PNG = b"\x89PNG\r\n\x1a\nC2PA-and-SynthID-stay"
MP4 = b"\x00\x00\x00\x20ftypisom-C2PA"


def reply(kind, data, mime):
    """Shaped like the Interactions API's REST reply (ai.google.dev/gemini-api/docs/omni, 'Raw REST JSON structure')."""
    return {"id": "v1_x", "status": "completed", "object": "interaction", "steps": [
        {"type": "user_input", "content": [{"type": "text", "text": "..."}]},
        {"type": "thought", "content": [{"type": "thought", "text": "..."}]},
        {"type": "model_output", "content": [{"type": kind, "mime_type": mime,
                                              "data": base64.b64encode(data).decode()}]}]}


class GenCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.caps(gemini_images=10, gemini_video_seconds=60)
        self.brands({"founder/demo": {}})
        self.sent, self.keys = [], []
        self.answer = reply("image", PNG, "image/png")

    def tearDown(self):
        self.tmp.cleanup()

    def caps(self, **values):
        path = self.root / spend.CAPS
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({**{tool: None for tool in spend.UNITS}, **values}))

    def brands(self, brands):
        (self.root / "company.json").write_text(json.dumps({"integrations": {"marketing": {"brands": brands}}}))

    def send(self, body, api_key):
        self.sent.append((body, api_key))
        return self.answer

    def token(self):
        self.keys.append(1)
        return "fake-key"

    def image(self, prompt, brand="founder/demo", piece="lake-dawn", extra=()):
        argv = ["--brand", brand, "--week", "2026-W05", "--piece", piece, "--prompt", prompt, *extra]
        err = io.StringIO()
        with redirect_stderr(err), redirect_stdout(io.StringIO()):
            code = image.main(argv, send=self.send, token=self.token, root=self.root)
        return code, err.getvalue()

    def video(self, prompt, seconds="8", measure=lambda path: 8.0):
        argv = ["--brand", "founder/demo", "--week", "2026-W05", "--piece", "lake-dawn", "--prompt", prompt,
                "--seconds", seconds]
        err = io.StringIO()
        with redirect_stderr(err), redirect_stdout(io.StringIO()):
            code = video.main(argv, send=self.send, token=self.token, root=self.root, measure=measure)
        return code, err.getvalue()

    def log(self):
        path = self.root / spend.LOG
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def assertRefused(self, prompt, fragment, brand="founder/demo"):
        code, err = self.image(prompt, brand)
        self.assertEqual(code, 1, prompt)
        self.assertIn(fragment, err)
        self.assertEqual((self.sent, self.keys, self.log()), ([], [], []), "refused before any call")

    @property
    def folder(self):
        return self.root / "workspaces/marketing/media/founder/demo/2026-W05/lake-dawn"


class Refusals(GenCase):
    def test_text_in_the_picture(self):
        for prompt in ["a shop sign that says OPEN", "a logo on a mug", "neon letters", "a poster with a caption",
                       "a mountain lake, no text", "a line of script on paper", "calligraphic strokes in ink",
                       "an open page", "verses on a wall", "a banner over the gate"]:
            with self.subTest(prompt=prompt):
                self.assertRefused(prompt, "rendered in code")

    def test_people_may_appear_unless_the_board_turned_them_off_for_the_brand(self):
        prompts = ["a man walking on a bridge", "two women at a cafe", "a portrait in soft light", "a crowd at a concert",
                   "a child's hands", "a smiling face", "a quiet street, no people", "a silhouette at dawn"]
        self.brands({"founder/demo": {"ai_people": False}, "founder/acme": {"ai_people": "yes"}})
        for prompt in prompts:
            with self.subTest(prompt=prompt):
                self.assertRefused(prompt, "asks for a person")
        self.assertRefused(prompts[0], "asks for a person", "founder/acme")
        for settings in ({}, {"ai_people": True}):
            self.caps(gemini_images=100)
            self.brands({"founder/demo": settings})
            for n, prompt in enumerate(prompts):
                with self.subTest(prompt=prompt, settings=settings):
                    code, err = self.image(prompt, piece=f"p{n}")
                    self.assertEqual(code, 0, err)
                    self.assertNotIn("No people", self.sent[-1][0]["input"][0]["text"])

    def test_a_brand_that_isnt_set_up_sends_nothing(self):
        self.assertRefused("a mountain lake at dawn", "company.json has no brand founder/acme", "founder/acme")
        (self.root / "company.json").write_text("{}")
        self.assertRefused("a mountain lake at dawn", "company.json has no brand founder/demo")
        (self.root / "company.json").unlink()
        self.assertRefused("a mountain lake at dawn", "company.json has no brand founder/demo")

    def test_a_setting_of_the_wrong_kind_sends_nothing(self):
        for marketing in (True, "on", ["brands"], {"brands": True}, {"brands": ["founder/demo"]},
                          {"brands": {"founder/demo": None}}, {"brands": {"founder/demo": True}}):
            (self.root / "company.json").write_text(json.dumps({"integrations": {"marketing": marketing}}))
            with self.subTest(marketing=marketing):
                self.assertRefused("a mountain lake at dawn", "company.json has no brand founder/demo")

    def test_a_broken_company_json_sends_nothing(self):
        (self.root / "company.json").write_text("{not json")
        self.assertRefused("a mountain lake at dawn", "Expecting")

    def test_plain_scenes_pass(self):
        self.caps(gemini_images=100)
        for n, prompt in enumerate(["misty mountain lake at dawn", "texture of linen in warm colours", "a signal tower on a hill",
                                    "abstract green gradient", "a glass cube on a desk", "a white tent in a meadow"]):
            with self.subTest(prompt=prompt):
                code, err = self.image(prompt, piece=f"p{n}")
                self.assertEqual(code, 0, err)


class Image(GenCase):
    def test_request_has_the_model_format_and_no_text_instruction(self):
        self.image("misty mountain lake at dawn", extra=["--aspect", "9:16"])
        [(body, key)] = self.sent
        self.assertEqual(key, "fake-key")
        self.assertEqual(body["model"], image.MODEL)
        self.assertEqual(body["response_format"], {"type": "image", "aspect_ratio": "9:16", "image_size": "2K"})
        text = body["input"][0]["text"]
        self.assertTrue(text.startswith("misty mountain lake at dawn\n\nNo text, letters"), text)
        self.assertNotIn("No people", text)
        self.brands({"founder/demo": {"ai_people": False}})
        self.image("misty mountain lake at dawn")
        text = self.sent[-1][0]["input"][0]["text"]
        self.assertTrue(text.endswith("No people, faces, hands or human figures."), text)

    def test_writes_bytes_as_sent_with_a_sidecar(self):
        code, err = self.image("misty mountain lake at dawn")
        self.assertEqual(code, 0, err)
        self.assertEqual((self.folder / "image-01.png").read_bytes(), PNG)
        sidecar = json.loads((self.folder / "image-01.png.json").read_text())
        self.assertIs(sidecar["ai_generated"], True)
        self.assertEqual(sidecar["model"], image.MODEL)
        self.assertTrue(sidecar["prompt"].startswith("misty mountain lake at dawn"))
        self.assertRegex(sidecar["date"], r"^\d{4}-\d\d-\d\dT")

    def test_numbers_files_without_overwriting(self):
        self.image("misty mountain lake at dawn")
        self.answer = reply("image", b"\xff\xd8jpeg", "image/jpeg")
        self.image("misty mountain lake at dawn")
        self.assertEqual(sorted(p.name for p in self.folder.iterdir()),
                         ["image-01.png", "image-01.png.json", "image-02.jpg", "image-02.jpg.json"])

    def test_output_only_in_the_batch_folder(self):
        for brand, piece in [("../../..", "p"), ("founder/demo", "../../x"), ("founder/demo", "a/b")]:
            with self.subTest(brand=brand, piece=piece):
                code, err = self.image("misty mountain lake at dawn", brand=brand, piece=piece)
                self.assertEqual(code, 1)
                self.assertIn("should look like", err)
        self.assertEqual(self.sent, [])

    def test_spend_is_reserved_then_logged(self):
        self.image("misty mountain lake at dawn")
        reserved, outcome = self.log()
        batch = {"tool": "gemini_images", "model": image.MODEL, "brand": "founder/demo", "week": "2026-W05",
                 "piece": "lake-dawn", "units": 1, "unit": "images"}
        self.assertEqual({k: reserved[k] for k in ("kind", *batch)}, {"kind": "reserve", **batch})
        self.assertEqual({k: outcome[k] for k in ("kind", *batch, "ok")}, {"kind": "done", **batch, "ok": True})
        self.assertEqual(reserved["id"], outcome["id"])

    def test_the_units_are_reserved_before_the_call_is_sent(self):
        seen = []

        def send(body, api_key):
            seen.extend(self.log())
            return self.answer
        argv = ["--brand", "founder/demo", "--week", "2026-W05", "--piece", "lake-dawn", "--prompt", "a lake"]
        with redirect_stderr(io.StringIO()), redirect_stdout(io.StringIO()):
            image.main(argv, send=send, token=self.token, root=self.root)
        self.assertEqual([(e["kind"], e["units"]) for e in seen], [("reserve", 1)])

    def test_null_cap_refuses_before_any_send(self):
        self.caps(gemini_images=None)
        code, err = self.image("misty mountain lake at dawn")
        self.assertEqual(code, 1)
        self.assertIn("TODO(board)", err)
        self.assertEqual((self.sent, self.keys), ([], []))

    def test_reached_cap_refuses_before_any_send(self):
        self.caps(gemini_images=2)
        self.image("misty mountain lake at dawn")
        self.image("misty mountain lake at dawn")
        code, err = self.image("misty mountain lake at dawn")
        self.assertEqual(code, 1)
        self.assertIn("would pass the cap", err)
        self.assertEqual((len(self.sent), len(self.keys)), (2, 2))

    def test_a_reply_without_an_image_is_logged_as_failed(self):
        self.answer = {"status": "completed", "steps": [
            {"type": "model_output", "content": [{"type": "text", "text": "I can't make that."}]}]}
        code, err = self.image("misty mountain lake at dawn")
        self.assertEqual(code, 1)
        self.assertIn("I can't make that.", err)
        self.assertEqual([(e["kind"], e.get("ok"), e["units"]) for e in self.log()],
                         [("reserve", None, 1), ("done", False, 1)])
        self.assertFalse(self.folder.exists())


class Video(GenCase):
    def setUp(self):
        super().setUp()
        self.answer = reply("video", MP4, "video/mp4")

    def test_asks_for_the_seconds_and_logs_them(self):
        code, err = self.video("waves on a pebble shore", seconds="8")
        self.assertEqual(code, 0, err)
        [(body, _)] = self.sent
        self.assertEqual(body["model"], video.MODEL)
        self.assertEqual(body["response_format"],
                         {"type": "video", "aspect_ratio": "9:16", "duration": "8s", "delivery": "inline"})
        self.assertEqual((self.folder / "video-01.mp4").read_bytes(), MP4)
        self.assertIs(json.loads((self.folder / "video-01.mp4.json").read_text())["ai_generated"], True)
        self.assertEqual([(e["kind"], e["tool"], e["units"], e["unit"]) for e in self.log()],
                         [("reserve", "gemini_video_seconds", 8, "seconds"), ("done", "gemini_video_seconds", 8, "seconds")])

    def test_logs_the_real_length_when_longer(self):
        self.video("waves on a pebble shore", seconds="8", measure=lambda path: 10.04)
        self.assertEqual([e["units"] for e in self.log()], [8, 10.04])
        self.assertEqual(spend.month_total("gemini_video_seconds", self.log()[0]["ts"][:7], self.root), 10.04)

    def test_cap_counts_seconds_before_any_send(self):
        self.caps(gemini_video_seconds=12)
        self.video("waves on a pebble shore", seconds="8")
        code, err = self.video("waves on a pebble shore", seconds="8")
        self.assertEqual(code, 1)
        self.assertIn("8 of 12 seconds", err)
        self.assertEqual(len(self.sent), 1)

    def test_text_refused_for_video_too(self):
        code, err = self.video("waves under a banner")
        self.assertEqual(code, 1)
        self.assertIn("rendered in code", err)
        self.assertEqual(self.sent, [])

    def test_seconds_stay_within_one_clip(self):
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            self.video("waves on a pebble shore", seconds="11")


if __name__ == "__main__":
    unittest.main()
