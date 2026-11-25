"""Tests for tools/marketing/measure/. No network and no model: every model is a fake session on small synthetic
fixtures. Tests that need numpy, Pillow, the bundled ffmpeg or Tesseract are skipped where they aren't installed (the
standard library parts run everywhere)."""

import importlib.util
import inspect
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
import wave
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "reels"))

import watch  # noqa: E402
from measure import audio, caption, cuts, embed, media, models, ocr, run, speech, stats  # noqa: E402

try:
    import numpy as np
except ImportError:
    np = None

TOOLS = Path(__file__).resolve().parents[1]
HAS_NUMPY = np is not None
HAS_PIL = importlib.util.find_spec("PIL") is not None
HAS_FFMPEG = media.FFMPEG.exists()
HAS_TESSERACT = bool(ocr.TESSERACT)
NEEDS_NUMPY = unittest.skipUnless(HAS_NUMPY, "numpy isn't installed here")
NEEDS_PICTURES = unittest.skipUnless(HAS_NUMPY and HAS_PIL, "numpy and Pillow aren't installed here")
NEEDS_FFMPEG = unittest.skipUnless(HAS_FFMPEG and HAS_NUMPY and HAS_PIL,
                                   "the bundled ffmpeg, numpy and Pillow aren't installed here")

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
PROBE = """  Duration: 00:00:12.48, start: 0.000000, bitrate: 1000 kb/s
  Stream #0:0[0x1](und): Video: h264 (High) (avc1 / 0x31637661), yuv420p(tv, bt709), 1080x1920 [SAR 1:1 DAR 9:16], 2000 kb/s, 29.97 fps, 29.97 tbr
  Stream #0:1[0x2](und): Audio: aac (LC), 44100 Hz, stereo
"""
AUDIO_LINE = "  Stream #0:1[0x2](und): Audio: aac (LC), 44100 Hz, stereo\n"
TSV = ("level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n"
       "1\t1\t0\t0\t0\t0\t0\t0\t720\t1280\t-1\t\n"
       "5\t1\t1\t1\t1\t1\t10\t10\t50\t20\t96.1\tGuten\n"
       "5\t1\t1\t1\t1\t2\t60\t10\t50\t20\t91.0\tMorgen\n"
       "5\t1\t1\t1\t1\t3\t120\t10\t50\t20\t30.0\tMMMM\n"
       "5\t1\t2\t1\t1\t1\t10\t90\t50\t20\t90.0\t10:30\n"
       "5\t1\t3\t1\t1\t1\t10\t190\t50\t20\t50.0\tSeite\n")


def quiet_main(argv, root):
    """run.main in this process, its stdout parsed; the real refuse_network would patch this process's sockets."""
    out = io.StringIO()
    with mock.patch.object(run, "refuse_network") as refuse, redirect_stdout(out):
        code = run.main(argv, root=root)
    refuse.assert_called_once()
    return code, json.loads(out.getvalue())


def write_wav(path: Path, samples) -> None:
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16000)
        handle.writeframes((np.clip(samples, -1, 1) * 32767).astype("<i2").tobytes())


class SameAsWatch(unittest.TestCase):
    """measure/ copies reels/watch.py's cut and loudness rules; they must not drift apart."""

    def test_copied_functions_are_the_same(self):
        self.assertEqual(inspect.getsource(cuts.pick_cuts), inspect.getsource(watch.pick_cuts))
        self.assertEqual(inspect.getsource(audio.parse_loudness), inspect.getsource(watch.parse_loudness))

    def test_copied_constants_are_the_same(self):
        for name in ("SCENE_FLOOR", "SCENE_SPIKE", "SCENE_WINDOW", "SCENE_QUIET", "CUT_GAP_SECONDS", "EDGE_SECONDS"):
            self.assertEqual(getattr(cuts, name), getattr(watch, name), name)
        self.assertEqual(audio.LOUD_KEYS, watch.LOUD_KEYS)
        self.assertEqual(speech.MIN_WORDS_FOR_RATE, watch.MIN_WORDS_FOR_RATE)
        self.assertEqual(ocr.CONFIDENCE, watch.OCR_CONFIDENCE)
        self.assertEqual(ocr.MIN_WORD, watch.OCR_MIN_WORD)


class Cuts(unittest.TestCase):
    def test_pick_cuts_finds_the_spike(self):
        scores = [(round(i * 0.1, 1), 0.001) for i in range(60)]
        scores[20], scores[21] = (2.0, 0.3), (2.1, 0.6)
        self.assertEqual(cuts.pick_cuts(scores), [2.1])

    def test_cuts_from_predictions(self):
        predictions = [0, 0.9, 0.9, 0, 0, 0.9, 0]
        self.assertEqual(cuts.cuts_from_predictions(predictions, 2, 10), [1.5, 3.0])
        self.assertEqual(cuts.cuts_from_predictions(predictions, 2, 3.05), [1.5])

    def test_cut_stats(self):
        found = cuts.cut_stats([1.5, 3.0], 6.0, "x")
        self.assertEqual((found["cuts"], found["cuts_per_minute"], found["first_cut_seconds"], found["shots"]),
                         (2, 20.0, 1.5, 3))
        self.assertEqual((found["shot_median_seconds"], found["shot_p10_seconds"], found["shot_p90_seconds"],
                          found["longest_shot_seconds"]), (1.5, 1.5, 2.7, 3.0))
        self.assertEqual(found["method"], "x")
        self.assertIsNone(cuts.cut_stats([], 6.0, "x")["first_cut_seconds"])

    def test_frame_rate(self):
        self.assertEqual([cuts.frame_rate(fps) for fps in (None, 29.97, 120, 10)], [25, 30, 25, 25])

    @NEEDS_NUMPY
    def test_transnet_windows(self):
        calls = []

        class Session:
            def get_inputs(self):
                return [SimpleNamespace(name="frames", type="tensor(uint8)")]

            def get_outputs(self):
                return [SimpleNamespace(name="many_hot"), SimpleNamespace(name="single_frame_pred")]

            def run(self, names, feeds):
                calls.append(names)
                batch = feeds["frames"]
                assert batch.shape == (1, 100, 27, 48, 3) and batch.dtype == np.uint8
                return [np.where(batch[0].mean(axis=(1, 2, 3)) > 100, 10.0, -10.0).reshape(1, 100, 1)]

        model = cuts.TransNet(None, session=Session())
        self.assertEqual(model.output, "single_frame_pred")
        frames = np.zeros((130, 27, 48, 3), dtype=np.uint8)
        frames[[0, 64, 129]] = 255
        predictions = model.predictions(frames)
        self.assertEqual(len(predictions), 130)
        self.assertEqual(list(np.nonzero(predictions > 0.5)[0]), [0, 64, 129])
        self.assertEqual(len(calls), 3)
        self.assertEqual(calls[0], ["single_frame_pred"])
        calls.clear()
        self.assertEqual(len(model.predictions(np.zeros((100, 27, 48, 3), dtype=np.uint8))), 100)
        self.assertEqual(len(calls), 2)
        self.assertEqual(len(model.predictions(np.zeros((0, 27, 48, 3), dtype=np.uint8))), 0)


class Audio(unittest.TestCase):
    def test_parse_loudness(self):
        self.assertEqual(audio.parse_loudness(EBUR128),
                         {"integrated_lufs": -15.0, "range_lu": 5.0, "true_peak_dbfs": -1.5})
        silent = EBUR128.replace("Peak:       -1.5 dBFS", "Peak:       -inf dBFS")
        self.assertIsNone(audio.parse_loudness(silent)["true_peak_dbfs"])

    def test_speech_features(self):
        found = audio.speech_features([(0.5, 1.5), (2.0, 3.5), (3.6, 4.0)], 10)
        self.assertAlmostEqual(found["speech_seconds"], 2.9)
        self.assertAlmostEqual(found["speech_share"], 0.29)
        self.assertEqual((found["segments"], found["pauses"]), (3, 1))
        self.assertAlmostEqual(found["pauses_per_minute"], 6.0)
        self.assertAlmostEqual(found["longest_pause_seconds"], 0.5)
        self.assertAlmostEqual(found["first_speech_seconds"], 0.5)
        self.assertAlmostEqual(found["speech_in_first_3s"], 2.0)
        empty = audio.speech_features([], 10)
        self.assertIsNone(empty["first_speech_seconds"])
        self.assertEqual((empty["longest_pause_seconds"], empty["pauses"]), (0.0, 0))

    @NEEDS_NUMPY
    def test_silero_segments(self):
        class Session:
            def run(self, names, feeds):
                x = feeds["input"]
                assert x.shape[1] == audio.WINDOW + audio.CONTEXT
                assert feeds["h"].shape == feeds["c"].shape == (1, 1, 128)
                return (np.abs(x).mean(axis=1) > 0.1).astype(np.float32).reshape(-1, 1), feeds["h"], feeds["c"]

        samples = np.zeros(64000, dtype=np.float32)
        samples[16000:32000] = np.random.default_rng(0).uniform(-0.5, 0.5, 16000)
        model = audio.Silero(None, session=Session())
        segments = model.segments(samples)
        self.assertEqual(len(segments), 1)
        start, end = segments[0]
        self.assertTrue(0.9 <= start <= 1.0, start)
        self.assertTrue(2.0 <= end <= 2.1, end)

    @NEEDS_NUMPY
    def test_tempo(self):
        samples = np.zeros(16000 * 10, dtype=np.float32)
        for start in range(0, len(samples), 8000):
            samples[start:start + 160] = 0.8
        found = audio.tempo(samples)
        self.assertTrue(115 <= found["bpm"] <= 125, found)
        self.assertEqual(audio.tempo(np.zeros(16000 * 4, dtype=np.float32)), {"bpm": None, "strength": None})

    @NEEDS_NUMPY
    def test_pitch(self):
        t = np.arange(16000 * 3) / 16000
        found = audio.pitch((0.5 * np.sin(2 * np.pi * 200 * t)).astype(np.float32), [])
        self.assertAlmostEqual(found["median_hz"], 200, delta=3)
        self.assertIsNone(audio.pitch(np.zeros(16000 * 3, dtype=np.float32), [])["median_hz"])


@NEEDS_NUMPY
class Visual(unittest.TestCase):
    def setUp(self):
        from measure import visual

        self.visual = visual

    def test_red_frame(self):
        found = self.visual.features([np.full((10, 10, 3), (255, 0, 0), dtype=np.uint8)])
        self.assertEqual((found["status"], found["frames"]), ("ok", 1))
        self.assertAlmostEqual(found["saturation"], 1.0)
        self.assertAlmostEqual(found["warmth"], 1.0)
        self.assertAlmostEqual(found["colourfulness"], 85.53, places=1)
        self.assertEqual((found["contrast"], found["sharpness"]), (0, 0))
        self.assertEqual(found["palette"], [{"hex": "#ff0000", "share": 1.0}])
        self.assertNotIn("motion", found)

    def test_motion(self):
        frames = [np.zeros((10, 10, 3), dtype=np.uint8), np.full((10, 10, 3), 255, dtype=np.uint8)]
        self.assertAlmostEqual(self.visual.features(frames, motion=True)["motion"], 1.0)
        self.assertNotIn("motion", self.visual.features(frames))
        self.assertEqual(self.visual.features([]), {"status": "none"})


@NEEDS_PICTURES
class Embeddings(unittest.TestCase):
    def test_clip_batches_and_units(self):
        calls = []

        class Session:
            def get_inputs(self):
                return [SimpleNamespace(name="pixel_values")]

            def get_outputs(self):
                return [SimpleNamespace(name="last_hidden_state"), SimpleNamespace(name="image_embeds")]

            def run(self, names, feeds):
                calls.append(names)
                batch = feeds["pixel_values"]
                assert batch.shape[1:] == (3, embed.CLIP_SIZE, embed.CLIP_SIZE) and batch.dtype == np.float32
                return [batch.mean(axis=(2, 3))]

        rng = np.random.default_rng(1)
        frames = [rng.integers(0, 256, (200, 300, 3), dtype=np.uint8) for _ in range(6)]
        model = embed.Clip(None, session=Session())
        found = model.frame_units(frames)
        self.assertEqual(model.output, "image_embeds")
        self.assertEqual(found.shape, (6, 3))
        self.assertEqual(len(calls), 2)
        np.testing.assert_allclose(np.linalg.norm(found, axis=1), 1.0)

    def test_piece_embedding(self):
        found = embed.piece_embedding(np.array([[1.0, 0.0], [0.0, 1.0]]), "m")
        self.assertEqual((found["status"], found["model"], found["frames"]), ("ok", "m", 2))
        self.assertEqual(found["vector"], [0.707107, 0.707107])
        self.assertEqual(embed.piece_embedding(np.array([[1.0, 0.0], [-1.0, 0.0]]), "m"), {"status": "none"})
        self.assertEqual(embed.piece_embedding(np.zeros((0, 2)), "m"), {"status": "none"})

    def test_aesthetic_is_weak(self):
        found = embed.Aesthetic(None, layers=[([[1, 0, 0]], [5])]).measure(np.array([[1, 0, 0], [0, 1, 0]]))
        self.assertEqual(found, {"status": "ok", "model": "laion-aesthetic", "weak": True, "median": 5.5,
                                 "p10": 5.1, "p90": 5.9})

    def test_short_side_size(self):
        self.assertEqual(embed.short_side_size(1080, 1920), (256, 456))
        self.assertEqual(embed.short_side_size(100, 200), (100, 200))


class Speech(unittest.TestCase):
    def test_the_language_for_whisper(self):
        self.assertEqual([speech.whisper_language(language) for language in ("de", "mixed", "unknown", None)],
                         ["de", None, None, None])
        self.assertEqual(speech.whisper_language("de", "fr"), "fr")

    def test_inside(self):
        self.assertFalse(speech.inside({"start": 4.0, "end": 4.4}, [(0, 3.5)]))
        self.assertTrue(speech.inside({"start": 3.6, "end": 4.2}, [(0, 3.5)]))

    def test_numbers(self):
        words = [{"start": float(i), "end": i + 0.5} for i in range(5)]
        found = speech.numbers(words, 6)
        self.assertEqual((found["words"], found["words_per_minute"], found["words_per_voiced_minute"]), (5, 66.7, 50.0))
        self.assertEqual((found["first_word_seconds"], found["words_first_3s"]), (0.0, 3))
        self.assertIsNone(speech.numbers(words[:4], 6)["words_per_minute"])
        self.assertEqual(speech.numbers([], 6)["words"], 0)

    def test_measure_gates(self):
        self.assertEqual(speech.measure(None, [(0, 0.5)], "de", "auto", None), {"status": "none", "speech_seconds": 0.5})
        self.assertEqual(speech.measure(None, [(0, 3)], "de", "auto", None),
                         {"status": "not installed: whisper-large-v3-mlx"})

    def test_whisper_keeps_timings_inside_speech(self):
        seen = {}

        def transcribe(audio_, **kwargs):
            seen.update(kwargs)
            words = [{"word": "x", "start": 0.5 * i + 0.5, "end": 0.5 * i + 0.9} for i in range(5)]
            words.append({"word": "music", "start": 9.0, "end": 9.4})
            return {"text": "never kept", "segments": [{"words": words}]}

        whisper = speech.Whisper(Path("/models/whisper"), transcribe=transcribe)
        found = speech.measure("samples", [(0.4, 3.5)], "de", "auto", whisper)
        self.assertEqual((found["status"], found["words"], found["model"]), ("ok", 5, "whisper-large-v3-mlx"))
        self.assertNotIn("never kept", json.dumps(found))
        self.assertEqual(seen, {"path_or_hf_repo": "/models/whisper", "language": "de", "word_timestamps": True,
                                "condition_on_previous_text": False, "verbose": None})

    def test_whisper_close_drops_the_cached_model(self):
        holder = SimpleNamespace(model="loaded", model_path="/models/whisper")
        cleared = []
        fakes = {"mlx_whisper.transcribe": SimpleNamespace(ModelHolder=holder),
                 "mlx.core": SimpleNamespace(clear_cache=lambda: cleared.append(1))}
        with mock.patch.dict(sys.modules, fakes):
            whisper = speech.Whisper(None, transcribe=lambda *_, **__: {})
            whisper.close()
        self.assertEqual((holder.model, holder.model_path, whisper.transcribe, cleared), (None, None, None, [1]))


LANGUAGES = {"en": (set(), {"the", "and", "is", "this", "are", "you"}), "de": (set("äöüß"), {"und", "ist", "wir", "das"})}


class Caption(unittest.TestCase):
    def test_language(self):
        cases = {"Heute üben wir das, und morgen ist Pause": "de",
                 "This is a short English caption": "en",
                 "Wir are here and das ist the end": "mixed",
                 "Bonjour tout le monde": "unknown",
                 "Hallo": None}
        with mock.patch.object(caption, "known_languages", return_value=LANGUAGES):
            for text, language in cases.items():
                self.assertEqual(caption.language_of(text), language, text)
        with mock.patch.object(caption, "known_languages", return_value={}):
            self.assertIsNone(caption.language_of("This is a short English caption"))

    def test_the_languages_are_company_jsons(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(caption.known_languages(Path(tmp)), {})
            (Path(tmp) / "company.json").write_text(json.dumps({"integrations": {"marketing": {"languages": {
                "en": {"name": "English"}, "de": {"name": "German", "letters": "äß", "words": ["und"]}}}}}))
            self.assertEqual(caption.known_languages(Path(tmp)), {"de": (set("äß"), {"und"})})

    def test_counts(self):
        self.assertEqual(caption.features("Hallo 👋🏽 🇩🇪 1️⃣")["emoji"], 3)
        self.assertEqual(caption.features("#demo #übung a#b")["hashtags"], 2)
        self.assertEqual(caption.features("@demo")["mentions"], 1)
        self.assertEqual(caption.features("https://x.test")["links"], 1)
        found = caption.features("Erste Zeile\n\nzweite")
        self.assertEqual((found["lines"], found["first_line_chars"], found["words"]), (3, 11, 3))
        self.assertEqual(caption.features(None), {"status": "none"})


class Media(unittest.TestCase):
    def test_parse_probe(self):
        found = media.parse_probe(PROBE)
        self.assertEqual((found["width"], found["height"], found["seconds"], found["fps"], found["has_audio"]),
                         (1080, 1920, 12.48, 29.97, True))
        self.assertFalse(media.parse_probe(PROBE.replace(AUDIO_LINE, ""))["has_audio"])
        rotated = media.parse_probe(PROBE + "    displaymatrix: rotation of -90.00 degrees\n")
        self.assertEqual((rotated["width"], rotated["height"]), (1920, 1080))

    def test_sizes_and_kinds(self):
        self.assertEqual(media.scaled_size(1080, 1920, 540), (540, 960))
        self.assertEqual(media.scaled_size(300, 401, 540), (300, 400))
        self.assertEqual(media.kind_for("reel", 1, 1), "reel")
        self.assertIsNone(media.kind_for(None, None, None))
        self.assertEqual(media.kind_for(None, 1080, 1920), "story")
        self.assertEqual(media.kind_for(None, 1080, 1350), "post")

    def test_discover(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "reel1").mkdir()
            (root / "reel1" / "video.mp4").write_bytes(b"not decoded here")
            (root / "reel1" / "video.info.json").write_text(json.dumps({"description": "Hallo"}), encoding="utf-8")
            (root / "post1").mkdir()
            (root / "post1" / "1.png").write_bytes(b"png")
            (root / "post1" / "2.mp4").write_bytes(b"mp4")
            (root / "post1" / "MANIFEST.json").write_text(json.dumps(
                {"kind": "carousel", "description": "x", "slides": [{"type": "image", "file": "1.png"},
                                                                    {"type": "video", "file": "2.mp4"},
                                                                    {"type": "image", "file": "../x.png"}]}),
                encoding="utf-8")
            (root / "carousel").mkdir()
            (root / "carousel" / "a.png").write_bytes(b"png")
            (root / "carousel" / "b.png").write_bytes(b"png")
            (root / "lone.jpg").write_bytes(b"jpg")
            (root / "lone.txt").write_text("Von Hand\n", encoding="utf-8")
            (root / "link.jpg").symlink_to(root / "lone.jpg")
            (root / "empty").mkdir()
            (root / "junk.bin").write_bytes(b"?")
            (root / ".hidden").write_bytes(b"?")
            pieces, skipped = media.discover(root)
        self.assertEqual([(p["name"], p["kind"]) for p in pieces],
                         [("carousel", "carousel"), ("lone.jpg", None), ("post1", "carousel"), ("reel1", "reel")])
        carousel, lone, post, reel = pieces
        self.assertEqual([p.name for p in carousel["images"]], ["a.png", "b.png"])
        self.assertEqual(lone["caption"], "Von Hand")
        self.assertEqual(([p.name for p in post["images"]], post["video"], post["video_slides"], post["caption"]),
                         (["1.png"], None, 1, "x"))
        self.assertEqual((reel["video"].name, reel["caption"]), ("video.mp4", "Hallo"))
        self.assertEqual(skipped, [{"name": "empty", "reason": "nothing to measure"},
                                   {"name": "junk.bin", "reason": "not a video, an image or a piece folder"},
                                   {"name": "link.jpg", "reason": "a link"}])

    def test_discover_skips_an_odd_manifest_and_measures_the_rest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name, manifest in (("a-slides-number", {"kind": "carousel", "slides": 1}),
                                   ("b-kind-list", {"kind": ["reel"], "slides": []})):
                (root / name).mkdir()
                (root / name / "1.png").write_bytes(b"png")
                (root / name / "MANIFEST.json").write_text(json.dumps(manifest), encoding="utf-8")
            (root / "c-good.jpg").write_bytes(b"jpg")
            pieces, skipped = media.discover(root)
        self.assertEqual([p["name"] for p in pieces], ["c-good.jpg"])
        self.assertEqual(skipped[0], {"name": "a-slides-number", "reason": "nothing to measure"})
        self.assertEqual(skipped[1]["name"], "b-kind-list")
        self.assertTrue(skipped[1]["reason"].startswith("couldn't be read: TypeError"), skipped[1])

    def test_probe_caps_the_length_and_every_rate_uses_it(self):
        long = SimpleNamespace(stderr=PROBE.replace("00:00:12.48", "00:20:00.00").encode())
        with mock.patch.object(media, "run_ffmpeg", return_value=long):
            info = media.probe(Path("long.mp4"))
        self.assertEqual((info["seconds"], info["full_seconds"], info["truncated"]), (600.0, 1200.0, True))
        with mock.patch.object(media, "run_ffmpeg", return_value=SimpleNamespace(stderr=PROBE.encode())):
            self.assertNotIn("truncated", media.probe(Path("short.mp4")))
        row = {"item": media.piece("long.mp4", "reel", video=Path("long.mp4")), "info": info}
        with mock.patch.object(cuts, "ffmpeg_cuts", return_value=[300.0]) as found:
            stats_ = run.cuts_of(row, None)
        found.assert_called_once_with(Path("long.mp4"), 600.0)
        self.assertEqual((stats_["cuts_per_minute"], stats_["longest_shot_seconds"]), (0.1, 300.0))


class Models(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.directory = self.root / "models"
        (self.directory / "m").mkdir(parents=True)
        self.a, self.b = self.directory / "m" / "a.bin", self.directory / "m" / "b.bin"
        self.a.write_bytes(b"a")
        self.b.write_bytes(b"b")
        hashes = {path.name: models.sha256(path) for path in (self.a, self.b)}
        self.b.unlink()
        catalogue = self.root / "models.json"
        catalogue.write_text(json.dumps({"models": [{"name": "m", "files": hashes}, {"name": "open", "files": {}},
                                                    {"name": "unpinned", "files": {"w.bin": None}}]}), encoding="utf-8")
        for patch in (mock.patch.object(models, "CATALOGUE", catalogue), mock.patch.dict(models._hashes, clear=True)):
            patch.start()
            self.addCleanup(patch.stop)

    def test_pinned_files_only(self):
        with self.assertRaisesRegex(models.ModelError, "missing b.bin"):
            models.locate("m", self.directory)
        self.b.write_bytes(b"b")
        self.assertEqual(models.locate("m", self.directory), self.directory / "m")
        self.assertEqual(models.status("m", self.directory), "ok")
        models._hashes.clear()
        self.b.write_bytes(b"changed")
        with self.assertRaisesRegex(models.ModelError, "isn't the pinned"):
            models.locate("m", self.directory)

    def test_absent_open_and_unpinned(self):
        self.a.unlink()
        self.assertIsNone(models.locate("m", self.directory))
        self.assertEqual(models.status("m", self.directory), "not installed")
        self.assertIsNone(models.locate("open", self.directory))
        (self.directory / "unpinned").mkdir()
        (self.directory / "unpinned" / "w.bin").write_bytes(b"w")
        with self.assertRaisesRegex(models.ModelError, "has no pinned sha256"):
            models.locate("unpinned", self.directory)
        self.assertTrue(models.status("unpinned", self.directory).startswith("refused:"))

    def test_the_catalogue_pins_every_file_it_names_or_says_why_not(self):
        with mock.patch.object(models, "CATALOGUE", TOOLS / "measure" / "models.json"):
            for name, model in models.catalogue().items():
                for file, sha in model["files"].items():
                    self.assertTrue(sha is None or len(sha) == 64, f"{name}/{file}")


class Ocr(unittest.TestCase):
    def test_tesseract_boxes(self):
        found = ocr.tesseract_boxes(TSV)
        self.assertEqual([text for text, _ in found], ["Guten", "Morgen"])
        for (_, box), expected in zip(found, [(10 / 720, 10 / 1280, 50 / 720, 20 / 1280),
                                              (60 / 720, 10 / 1280, 50 / 720, 20 / 1280)]):
            for got, want in zip(box, expected):
                self.assertAlmostEqual(got, want)
        self.assertEqual(ocr.tesseract_boxes("level\ttext\n"), [])

    def test_grid_and_safe_zone(self):
        for got, want in zip(ocr.grid_keep(9 / 16), (0, 0.125, 1, 0.875)):
            self.assertAlmostEqual(got, want)
        for got, want in zip(ocr.grid_keep(1.0), (0.125, 0, 0.875, 1)):
            self.assertAlmostEqual(got, want)
        self.assertIsNone(ocr.outside_share(set(), (0, 0, 1, 1)))
        self.assertTrue(ocr.in_unsafe({(0, 0)}))
        self.assertFalse(ocr.in_unsafe({(50, 50)}))

    def test_features(self):
        empty = ocr.features([[]], None, "tesseract")
        self.assertEqual((empty["frames_with_text_share"], empty["language"]), (0.0, None))
        self.assertEqual(ocr.features([], None, "tesseract"), {"status": "none"})
        found = ocr.features([[("Hallo", (0.1, 0.0, 0.3, 0.05))], []], 9 / 16, "tesseract")
        self.assertEqual((found["cover_grid_cut_share"], found["safe_zone_hit_share"]), (1.0, 1.0))
        self.assertEqual((found["frames"], found["frames_with_text_share"], found["cover_chars"]), (2, 0.5, 5))
        self.assertAlmostEqual(found["cover_text_area"], 0.015)
        square = ocr.features([[("Hallo", (0.4, 0.4, 0.2, 0.1))]], 1.0, "tesseract")
        self.assertEqual((square["cover_grid_cut_share"], square["safe_zone_hit_share"]), (0.0, None))

    def test_tesseract_reads_only_the_checked_folder(self):
        done = subprocess.CompletedProcess([], 0, stdout=TSV, stderr="")
        with mock.patch.object(ocr, "TESSERACT", "tesseract"), \
                mock.patch.object(ocr.subprocess, "run", return_value=done) as called:
            found = ocr.read_tesseract([Path("f.png")], Path("/models/tesseract-script"))
        self.assertEqual(found, [ocr.tesseract_boxes(TSV)])
        self.assertEqual(called.call_args.args[0],
                         ["tesseract", "f.png", "-", "--tessdata-dir", "/models/tesseract-script", "-l",
                          "script/Latin", "--psm", "11", "-c", "tessedit_create_tsv=1"])
        with self.assertRaisesRegex(ocr.OcrError, "tesseract-script isn't located"):
            ocr.measure(media.piece("p", "post", images=[Path("p.png")]), {}, "tesseract", Path("/nowhere"))

    def test_the_traineddata_loads_only_when_pinned(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(models._hashes, clear=True):
            directory = Path(tmp)
            self.assertEqual(run.load(ocr.TESSERACT_MODEL, directory, lambda folder: folder),
                             (None, "not installed: tesseract-script"))
            (directory / "tesseract-script" / "script").mkdir(parents=True)
            (directory / "tesseract-script" / "script" / "Latin.traineddata").write_bytes(b"not the file")
            folder, status = run.load(ocr.TESSERACT_MODEL, directory, lambda folder: folder)
        self.assertIsNone(folder)
        self.assertRegex(status, r"^refused: tesseract-script: script/Latin.traineddata has no pinned sha256")

    @unittest.skipUnless(HAS_TESSERACT and HAS_NUMPY and HAS_PIL, "Tesseract, numpy and Pillow aren't installed here")
    def test_reads_a_rendered_slide(self):
        listed = subprocess.run([ocr.TESSERACT, "--list-langs"], capture_output=True, text=True, timeout=60).stdout
        prefix = listed.split('"')[1] if listed.count('"') >= 2 else ""
        installed = Path(prefix) / "eng.traineddata"
        if not prefix or not installed.is_file():
            self.skipTest("Tesseract's eng isn't installed here")
        from PIL import Image, ImageDraw, ImageFont

        pinned = {ocr.TESSERACT_MODEL: {"files": {"eng.traineddata": models.sha256(installed)}}}
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as directory, \
                mock.patch.object(models, "catalogue", return_value=pinned):
            (Path(directory) / ocr.TESSERACT_MODEL).mkdir()
            (Path(directory) / ocr.TESSERACT_MODEL / "eng.traineddata").symlink_to(installed)
            tessdata, status = run.load(ocr.TESSERACT_MODEL, Path(directory), lambda folder: folder)
            self.assertEqual(status, "ok")
            slide = Path(tmp) / "slide.png"
            image = Image.new("RGB", (720, 1280), (255, 255, 255))
            ImageDraw.Draw(image).text((60, 600), "Good morning all", font=ImageFont.load_default(72), fill=(0, 0, 0))
            image.save(slide)
            item = media.piece("slide", "post", images=[slide])
            found = ocr.measure(item, {"width": 720, "height": 1280}, "tesseract", Path(tmp), tessdata)
            self.assertEqual(sorted(path.name for path in Path(tmp).iterdir()), ["slide.png"])
        self.assertEqual((found["status"], found["frames"], found["frames_with_text_share"]), ("ok", 1, 1.0))
        self.assertGreater(found["cover_text_area"], 0)
        self.assertEqual(found["safe_zone_hit_share"], 0.0)


class Stats(unittest.TestCase):
    def test_quantiles_and_groups(self):
        self.assertEqual([stats.quantile([1, 2, 3, 4, 5], q) for q in (0.1, 0.5, 0.9)], [1.4, 3, 4.6])
        pieces = [{"schema": 1, "piece": {"page": "p", "format": "reel", "slides": 0}, "visual": {"lightness": v},
                   "flag": True, "caption": {"language": "de"}} for v in (10.0, 20.0, 30.0)]
        pieces.append({"piece": {"page": "p", "format": "post"}, "visual": {"lightness": 50.0}})
        groups = stats.summarize(pieces)
        self.assertEqual([(g["page"], g["format"], g["pieces"]) for g in groups], [("p", "post", 1), ("p", "reel", 3)])
        self.assertEqual(groups[1]["numbers"], {"visual.lightness": {"n": 3, "median": 20.0, "p10": 12.0, "p90": 28.0}})

    def test_centroids(self):
        def piece(vector, model="clip"):
            return {"piece": {"page": "p", "format": "reel"},
                    "embedding": {"status": "ok", "model": model, "vector": vector}}

        found = stats.centroids([piece([1, 0]), piece([0, 2]), piece([0, 0]), piece([1, 0, 0], "other"),
                                 {"piece": {"page": "p", "format": "reel"}, "embedding": {"status": "none"}}])
        self.assertEqual([(c["model"], c["pieces"]) for c in found], [("clip", 2), ("other", 1)])
        self.assertEqual(found[0]["vector"], [0.707107, 0.707107])
        self.assertAlmostEqual(found[0]["mean_cosine"], 0.7071)


class Run(unittest.TestCase):
    def test_new_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp).resolve()
            repo = base / "repo"
            (repo / "workspaces").mkdir(parents=True)
            (base / "taken").mkdir()
            (base / "dangling").symlink_to(base / "nowhere")
            self.assertEqual(run.new_path(str(base / "out"), repo), base / "out")
            self.assertEqual(run.new_path(str(repo / "workspaces" / "out"), repo), repo / "workspaces" / "out")
            for text, why in ((str(base / "taken"), "exists"), (str(base / "dangling"), "exists"),
                              (str(base / "no" / "out"), "isn't a folder"), (str(repo / "out"), "inside the repo"),
                              (str(repo / "workspaces" / ".." / "out"), "inside the repo"), (".", "name a new")):
                with self.assertRaisesRegex(run.Refused, why):
                    run.new_path(text, repo)

    def test_file_names_clean_and_message(self):
        self.assertEqual(run.file_names([{"name": "a b"}, {"name": "A_B"}, {"name": "..."}]),
                         ["a_b.json", "A_B-2.json", "piece.json"])
        self.assertEqual(run.clean({"a": float("nan"), "b": (1.0, float("inf")), "c": [{"d": 2}]}),
                         {"a": None, "b": [1.0, None], "c": [{"d": 2}]})
        self.assertEqual(run.message(ValueError("bad\n  thing")), "ValueError: bad thing")
        self.assertEqual(len(run.message(ValueError("x" * 1000))), run.ERROR_CHARS)

    def test_load(self):
        folder = Path("/models/m")
        with mock.patch.object(run.models, "locate", return_value=None):
            self.assertEqual(run.load("m", folder, object), (None, "not installed: m"))
        with mock.patch.object(run.models, "locate", side_effect=models.ModelError("m: missing a.bin")):
            self.assertEqual(run.load("m", folder, object), (None, "refused: m: missing a.bin"))
        with mock.patch.object(run.models, "locate", return_value=folder):
            self.assertEqual(run.load("m", folder, lambda path: path.name), ("m", "ok"))

            def broken(path):
                raise ImportError("no onnxruntime")

            self.assertEqual(run.load("m", folder, broken),
                             (None, "error: m didn't load: ImportError: no onnxruntime"))

    def test_the_speech_pass_reads_each_piece_once(self):
        closed, loaded = [], []

        class Whisper:
            MODEL = "whisper-large-v3-mlx"

            def words(self, audio_, language):
                return [{"start": 0.5 * i, "end": 0.5 * i + 0.3} for i in range(5)]

            def close(self):
                closed.append(self.MODEL)

        def load(name, directory, make):
            loaded.append(name)
            return Whisper(), "ok"

        with tempfile.TemporaryDirectory() as tmp:
            def rows():
                return [{"item": {"video": f"{name}.mp4"}, "info": {"has_audio": True}, "segments": [(0.0, seconds)],
                         "features": {"caption": {"language": language}, "errors": {}},
                         "path": Path(tmp) / f"{name}.json"}
                        for name, language, seconds in (("a", "de", 3.0), ("b", "mixed", 0.5), ("c", None, 3.0))]

            with mock.patch.object(run, "load", side_effect=load), \
                    mock.patch.object(run.media, "audio_samples", return_value="samples"):
                found, statuses = rows(), {}
                run.speech_pass(found, Path(tmp), "auto", statuses)
                self.assertEqual([row["features"]["speech"].get("model") for row in found],
                                 ["whisper-large-v3-mlx", None, "whisper-large-v3-mlx"])
                self.assertEqual(found[1]["features"]["speech"], {"status": "none", "speech_seconds": 0.5})
                self.assertEqual((loaded, closed), ([Whisper.MODEL], [Whisper.MODEL]))
                self.assertEqual(statuses, {Whisper.MODEL: "ok"})
                statuses = {}
                run.speech_pass(rows()[1:2], Path(tmp), "auto", statuses)
                self.assertTrue(statuses[Whisper.MODEL].startswith("not needed"))
            failed = "error: whisper-large-v3-mlx didn't load: no memory"
            with mock.patch.object(run, "load", return_value=(None, failed)), \
                    mock.patch.object(run.media, "audio_samples", return_value="samples"):
                found, statuses = rows(), {}
                run.speech_pass(found, Path(tmp), "de", statuses)
                self.assertEqual(found[0]["features"]["speech"], {"status": f"not run: {failed}"})
                self.assertEqual(found[1]["features"]["speech"], {"status": "none", "speech_seconds": 0.5})
                self.assertEqual(statuses[Whisper.MODEL], failed)

    def test_needs_environment(self):
        with mock.patch.object(run.sys, "version_info", (3, 9, 0)):
            with self.assertRaisesRegex(run.Refused, "3.10 or later"):
                run.needs_environment(numpy=False)
        with mock.patch.object(run.importlib.util, "find_spec", return_value=None):
            with self.assertRaisesRegex(run.Refused, "needs numpy"):
                run.needs_environment()
            run.needs_environment(numpy=False)

    def test_summary_errors(self):
        found = run.summary([{"piece": {"name": "a", "page": "p", "format": "reel"}, "errors": {"text": "x", "cuts": "y"}},
                             {"piece": {"name": "b", "page": "p", "format": "reel"}, "errors": {}}], [])
        self.assertEqual(found["errors"], {"a": ["cuts", "text"]})
        self.assertEqual((found["schema"], found["pieces"]), (1, 2))

    def test_summary_and_check_commands(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "run1" / "pieces").mkdir(parents=True)
            (base / "run1" / "pieces" / "a.json").write_text(json.dumps(
                {"schema": 1, "piece": {"name": "a", "page": "p", "format": "reel"}, "visual": {"lightness": 50.0}}),
                encoding="utf-8")
            (base / "run1" / "pieces" / "old.json").write_text(json.dumps({"schema": 0, "piece": {}}), encoding="utf-8")
            code, printed = quiet_main(["summary", "--runs", str(base / "run1"), "--out", str(base / "all.json")],
                                       base / "repo")
            self.assertEqual((code, printed["pieces"]), (0, 1))
            pooled = json.loads((base / "all.json").read_text(encoding="utf-8"))
            self.assertEqual(pooled["groups"][0]["numbers"]["visual.lightness"]["median"], 50.0)
            (base / "empty").mkdir()
            code, printed = quiet_main(["check", "--models", str(base / "empty")], base / "repo")
            self.assertEqual(code, 0)
            self.assertEqual(set(printed["models"].values()), {"not installed"})
            self.assertEqual(set(printed["models"]), set(models.catalogue()))
            with mock.patch.object(run, "refuse_network"), self.assertRaises(SystemExit) as refused:
                run.main(["summary", "--runs", str(base / "empty"), "--out", str(base / "x.json")], root=base / "repo")
            self.assertEqual(str(refused.exception), f"refused: --runs {base / 'empty'}: no pieces/ folder (not a run "
                                                     "of this tool)")

    def test_run_refuses_an_out_inside_the_repo(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp).resolve()
            (repo / "in").mkdir()
            with mock.patch.object(run, "refuse_network"), mock.patch.object(run, "needs_environment"), \
                    self.assertRaises(SystemExit) as refused:
                run.main(["run", "--in", str(repo / "in"), "--page", "p", "--out", str(repo / "out")], root=repo)
            self.assertIn("inside the repo, only under workspaces/", str(refused.exception))
            with mock.patch.object(run, "refuse_network"), mock.patch.object(run, "needs_environment"), \
                    self.assertRaises(SystemExit) as refused:
                run.main(["run", "--in", str(repo / "in"), "--page", "a/b", "--out", str(repo / "out")], root=repo)
            self.assertTrue(str(refused.exception).startswith("refused: --page"))
            self.assertFalse((repo / "out").exists())

    def test_refuse_network_in_a_process_of_its_own(self):
        code = ("import os, socket, sys\n"
                f"sys.path.insert(0, {str(TOOLS)!r})\n"
                "from measure import run\n"
                "run.refuse_network()\n"
                "try:\n"
                "    socket.getaddrinfo('localhost', 80)\n"
                "    print('looked up')\n"
                "except OSError:\n"
                "    pass\n"
                "s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)\n"
                "try:\n"
                "    s.connect(('127.0.0.1', 9))\n"
                "    print('connected')\n"
                "except OSError as error:\n"
                "    assert 'measure: no network' in str(error), error\n"
                "s.close()\n"
                "a, b = socket.socketpair()\n"
                "a.sendall(b'x')\n"
                "assert b.recv(1) == b'x'\n"
                "assert os.environ['HF_HUB_OFFLINE'] == '1'\n"
                "print('ok')\n")
        done = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True, timeout=60)
        self.assertEqual((done.returncode, done.stdout.strip()), (0, "ok"), done.stderr)


@NEEDS_FFMPEG
class EndToEnd(unittest.TestCase):
    """A reel, a post and a story through `run` with no model installed, then `summary` over the run."""

    def test_a_folder(self):
        from PIL import Image

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source, repo, empty = base / "in", base / "repo", base / "models"
            for folder in (source, repo, empty):
                folder.mkdir()
            subprocess.run([str(media.FFMPEG), "-hide_banner", "-nostdin", "-y", "-f", "lavfi", "-i",
                            "testsrc=size=270x480:rate=10:duration=3", "-f", "lavfi", "-i",
                            "sine=frequency=440:duration=3", "-c:v", "mpeg4", "-c:a", "aac", str(source / "reel.mp4")],
                           check=True, capture_output=True, timeout=120)
            Image.new("RGB", (300, 400), (200, 30, 30)).save(source / "post.png")
            (source / "post.txt").write_text("Heute lernen wir und ihr eine neue Lektion #demo", encoding="utf-8")
            Image.new("RGB", (270, 480), (30, 30, 200)).save(source / "story.png")
            with mock.patch.object(caption, "known_languages", return_value=LANGUAGES):
                code, printed = quiet_main(["run", "--in", str(source), "--page", "demo", "--out", str(base / "out"),
                                            "--models", str(empty)], repo)
            self.assertEqual((code, printed["pieces"], printed["skipped"]), (0, 3, 0))
            pieces = {path.stem: json.loads(path.read_text(encoding="utf-8"))
                      for path in sorted((base / "out" / "pieces").glob("*.json"))}
            self.assertEqual({name: f["piece"]["kind"] for name, f in pieces.items()},
                             {"reel.mp4": "reel", "post.png": "post", "story.png": "story"})
            reel = pieces["reel.mp4"]
            self.assertEqual(reel["visual"]["status"], "ok")
            self.assertIn("motion", reel["visual"])
            self.assertEqual(reel["audio"]["status"], "ok")
            self.assertEqual(reel["audio"]["speech"], {"status": "not run: not installed: silero-vad"})
            self.assertEqual(reel["cuts"]["method"], "ffmpeg-scene")
            self.assertEqual(reel["speech"], {"status": "not run: needs voice activity (silero-vad)"})
            for name in ("post.png", "story.png"):
                self.assertEqual([pieces[name][stage] for stage in ("audio", "cuts", "speech")], [{"status": "n/a"}] * 3)
            self.assertEqual(pieces["post.png"]["caption"]["language"], "de")
            for features in pieces.values():
                self.assertEqual(features["text"], {"status": "not run: not installed: tesseract-script"})
                self.assertEqual(features["embedding"], {"status": "not run: not installed: clip-vit-l14"})
                self.assertEqual(features["quality"]["aesthetic"],
                                 {"status": "not run: needs clip-vit-l14's embeddings"})
                self.assertEqual(features["errors"], {})
                self.assertEqual(features["piece"]["page"], "demo")
            self.assertTrue(printed["models"]["whisper-large-v3-mlx"].startswith("not needed"))
            summary = json.loads((base / "out" / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["page"], "demo")
            self.assertEqual(sorted(g["format"] for g in summary["groups"]), ["post", "reel", "story"])
            self.assertEqual(summary["centroids"], [])
            self.assertEqual(sorted(os.listdir(base / "out")), ["pieces", "summary.json"])
            code, pooled = quiet_main(["summary", "--runs", str(base / "out"), "--out", str(base / "all.json")], repo)
            self.assertEqual(pooled["pieces"], 3)


if __name__ == "__main__":
    unittest.main()
