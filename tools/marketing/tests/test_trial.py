"""taste/build.py's trial mode (trial-schema.md): the fixed designs, the hidden repeats, --design, the page, and the
refusals, which write nothing. Fake media files with the right first bytes; the page in a real browser, with a video,
is trial.test.mjs."""
import collections
import contextlib
import io
import json
import re
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_taste import PAGE, Taste, fake_fonts, taste  # noqa: E402

EXAMPLE = Path(taste.__file__).resolve().parent / "example-trial.json"
DAY = "session-2026-01-07"
REF = "DemoCode00M"
JPG = b"\xff\xd8\xff\xe0" + bytes(12)
PNG = b"\x89PNG\r\n\x1a\n" + bytes(8)
MP4 = b"\x00\x00\x00\x18ftypisom" + bytes(4)
SWAPPED = ("pairwise", "maxdiff", "cbc")  # the types that get hidden repeats


def levels(*ids):
    return [{"id": key, "label": key.title()} for key in ids]


def sitting():
    return {
        "mode": "trial", "page": PAGE, "title": "Day 1: demo", "intro": "A short sitting.", "seed": 7, "break_minutes": 22,
        "parts": [
            {"id": "pw", "type": "pairwise", "title": "Pairs", "minutes": 5, "rounds": 3,
             "intro": [{"name": "Pace", "line": "Fast against slow."}],
             "items": [{"id": "r1", "src": f"ref/{REF}.mp4", "reel": REF}, {"id": "a", "src": "ours/a.jpg", "label": "Ours A"},
                       {"id": "b", "src": "ours/b.jpg"}, {"id": "c", "src": "ours/c.mp4"}]},
            {"id": "md", "type": "maxdiff", "title": "Boards", "minutes": 5, "appearances": 3,
             "items": [{"id": f"m{k}", "src": f"ours/m{k}.jpg"} for k in range(8)]},
            {"id": "cb", "type": "cbc", "title": "Reels", "minutes": 5, "tasks": 9, "holdouts": 1, "media": "ours/r-{pace}-{grade}.mp4",
             "attributes": [{"id": "pace", "name": "Pace", "levels": levels("slow", "mid", "fast")},
                            {"id": "grade", "name": "Grade", "levels": levels("warm", "cool")}]},
            {"id": "sq", "type": "sequence", "title": "Steps", "minutes": 3,
             "dimensions": [{"id": "cut", "name": "Cut length", "steps": [f"ours/s{k}.jpg" for k in range(1, 8)]}]},
            {"id": "rg", "type": "range", "title": "Ranges", "minutes": 2,
             "dimensions": [{"id": "len", "name": "Length", "values": ["15 s", "30 s", "45 s"]}]},
            {"id": "nt", "type": "notes", "title": "Notes", "minutes": 2, "items": [{"id": "n1", "src": "ours/a.jpg", "label": "A frame"}]},
            {"id": "rl", "type": "redlines", "title": "Hard nos", "minutes": 2, "candidates": ["Shouting", "Clickbait", "Stock music"]},
            {"id": "ck", "type": "checklist", "title": "Carry over", "minutes": 2, "mark": "Not for him",
             "candidates": ["Pace", "Grade", "Cover", "Hook"]},
        ]}


def files_of():
    return {f"ref/{REF}.mp4", "ours/a.jpg", "ours/b.jpg", "ours/c.mp4", *(f"ours/m{k}.jpg" for k in range(8)),
            *(f"ours/r-{pace}-{grade}.mp4" for pace in ("slow", "mid", "fast") for grade in ("warm", "cool")),
            *(f"ours/s{k}.jpg" for k in range(1, 8))}


def part_of(session, key):
    return next(part for part in session["parts"] if part["id"] == key)


class Trial(Taste):
    def setUp(self):
        super().setUp()
        self.here = self.folder / DAY
        for sub in ("ref", "ours"):
            (self.here / sub).mkdir(parents=True)
        self.reel(REF, caption=None, breakdown=None)
        self.session = sitting()
        for src in files_of():
            (self.here / src).write_bytes(MP4 if src.endswith(".mp4") else JPG)

    def write(self, session=None):
        (self.here / "session.json").write_text(json.dumps(self.session if session is None else session), encoding="utf-8")

    def run_trial(self, session=None, design_only=False):
        self.write(session)
        return taste.build_session(PAGE, str(self.here / "session.json"), root=self.root, fonts=fake_fonts, design_only=design_only)

    def design(self, session=None):
        """The whole checked design, as the page carries it."""
        return taste.checked_trial(self.session if session is None else session, PAGE, self.here, self.root, None)

    def trial_refused(self, reason, session=None, design_only=False):
        self.write(session)
        before = {path: path.read_bytes() if path.is_file() else None for path in self.root.rglob("*")}
        with self.assertRaisesRegex(taste.Refused, reason):
            taste.build_session(PAGE, str(self.here / "session.json"), root=self.root, fonts=fake_fonts, design_only=design_only)
        after = {path: path.read_bytes() if path.is_file() else None for path in self.root.rglob("*")}
        self.assertEqual(after, before, "a refusal must write nothing")

    def example(self):
        """example-trial.json, with a clean saved folder for each reel and post it names."""
        example = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        items = [item for part in example["parts"] for item in part.get("items", [])]
        for code in sorted({item["reel"] for item in items if "reel" in item}):
            self.reel(code, caption=None, breakdown=None)
        for code in sorted({item["post"] for item in items if "post" in item}):
            self.post(code)
        return example

    def with_part(self, key, **changes):
        session = json.loads(json.dumps(self.session))
        part_of(session, key).update(changes)
        return session

    def with_item(self, key, **changes):
        session = json.loads(json.dumps(self.session))
        part_of(session, key)["items"][0].update(changes)
        return session


class TrialPage(Trial):
    def test_writes_the_page_with_the_whole_design_and_no_answer_chosen(self):
        result = self.run_trial()
        self.assertRegex(result, rf"^wrote .*/picker\.html: 8 parts, \d+ trials, {len(files_of())} media files, seed 7$")
        page = (self.here / "picker.html").read_text(encoding="utf-8")
        data = json.loads(re.search(r'<script type="application/json" id="design">(.*?)</script>', page, re.S)[1])
        self.assertEqual(data, self.design())
        self.assertEqual(data["format"], "taste-trial-1")
        markup = re.sub(r"<script.*?</script>|<style.*?</style>", "", page, flags=re.S)
        self.assertIsNone(re.search(r"\b(checked|selected)\b", markup), "nothing on the page is chosen before he chooses")
        self.assertNotIn('"default"', json.dumps(data))
        self.assertIn("default-src 'none'", page)
        self.assertNotRegex(page, r"https?://", "the page loads nothing from outside")

    def test_media_are_named_not_embedded_and_videos_are_videos(self):
        self.run_trial()
        page = (self.here / "picker.html").read_text(encoding="utf-8")
        self.assertNotIn("base64", page)
        items = {item["id"]: item for item in part_of(self.design(), "pw")["items"]}
        self.assertEqual((items["r1"], items["a"]["media"], items["c"]["media"]),
                         ({"id": "r1", "reel": REF, "src": f"ref/{REF}.mp4", "media": "video"}, "image", "video"))

    def test_text_cannot_end_the_script_or_the_title(self):
        hostile = "</script><script>alert(1)</script> & <b>"
        self.session["title"] = hostile
        part_of(self.session, "ck")["candidates"][0] = hostile
        self.run_trial()
        page = (self.here / "picker.html").read_text(encoding="utf-8")
        self.assertNotIn("<script>alert", page)
        self.assertEqual(page.count("</script>"), page.count("<script"))
        self.assertEqual(part_of(self.design(), "ck")["candidates"][0], hostile, "the text itself survives, escaped")

    def test_handles_and_phone_numbers_are_masked(self):
        text = "Call +49 555 123 4567 or ask @qzx.handle"
        self.session["intro"] = text
        part_of(self.session, "pw")["items"][1]["label"] = text
        part_of(self.session, "ck")["mark"] = "No, @qzx"
        self.run_trial()
        page = (self.here / "picker.html").read_text(encoding="utf-8")
        self.assertNotIn("555 123", page)
        self.assertNotIn("qzx", page)
        design = self.design()
        self.assertEqual(design["intro"], "Call ... or ask @...")
        self.assertEqual(part_of(design, "ck")["mark"], "No, @...")

    def test_the_example_builds_its_design(self):
        example = self.example()
        with contextlib.redirect_stderr(io.StringIO()) as err:
            out = json.loads(self.run_trial(example, design_only=True))
        self.assertEqual(err.getvalue(), "", "the example's intro lines are neutral")
        self.assertEqual([part["id"] for part in out["parts"]], [part["id"] for part in example["parts"]])
        self.assertEqual(out["missing"], out["files"], "none of the example's media is here, and none is needed for --design")
        self.assertEqual((out["seed"], out["minutes"]), (12345, sum(part["minutes"] for part in example["parts"])))
        regular = sum(part["trials"] - part["repeats"] - part["holdouts"] for part in out["parts"] if part["repeats"])
        self.assertAlmostEqual(sum(part["repeats"] for part in out["parts"]) / regular, 0.10, delta=0.02)
        self.assertEqual(json.dumps(example, indent=1, ensure_ascii=False) + "\n", EXAMPLE.read_text(encoding="utf-8"))


class TrialDesign(Trial):
    def test_the_same_seed_gives_the_same_design_and_another_seed_another(self):
        self.assertEqual(self.design(), self.design())
        other = {**self.session, "seed": 8}
        self.assertNotEqual([part["trials"] for part in self.design()["parts"]], [part["trials"] for part in self.design(other)["parts"]])

    def test_changing_one_part_leaves_the_others_as_they_were(self):
        changed = self.with_part("md", appearances=4)
        before, after = self.design(), self.design(changed)
        for one, two in zip(before["parts"], after["parts"]):
            if one["id"] != "md":
                self.assertEqual(one, two)
        self.assertNotEqual(part_of(before, "md")["trials"], part_of(after, "md")["trials"])

    def test_the_design_id_ignores_display_text_and_follows_the_design(self):
        same = json.loads(json.dumps(self.session))
        same["title"], same["intro"] = "Another title", "Another intro"
        for part in same["parts"]:
            part.update(title="Renamed", question="Asked otherwise?", minutes=9, intro=[{"name": "New", "line": "New line."}])
        part_of(same, "pw")["items"][1]["label"] = "Relabelled"
        part_of(same, "cb")["attributes"][0]["name"] = "Speed"
        part_of(same, "cb")["attributes"][0]["levels"][0]["label"] = "Slowest"
        part_of(same, "sq")["dimensions"][0].update(name="Renamed", labels=[str(k) for k in range(7)])
        part_of(same, "ck")["mark"] = "Drop"
        part_of(same, "cb")["show_levels"] = not part_of(same, "cb").get("show_levels", False)
        same["break_minutes"] = 25
        design_id = self.design()["design_id"]
        self.assertRegex(design_id, r"^[0-9a-f]{12}$")
        self.assertEqual(self.design(same)["design_id"], design_id)
        for label, changed in (("seed", {**self.session, "seed": 8}), ("rounds", self.with_part("pw", rounds=2)),
                               ("a file", self.with_item("md", src="ours/b.jpg")),
                               ("a candidate", self.with_part("ck", candidates=["Pace", "Grade", "Cover", "Tone"]))):
            with self.subTest(label):
                self.assertNotEqual(self.design(changed)["design_id"], design_id)

    def test_pairwise_is_a_round_robin_with_the_sides_balanced(self):
        for items, rounds in ((4, 3), (8, 10), (24, 12)):
            with self.subTest(items=items, rounds=rounds):
                ids = [f"i{k}" for k in range(items)]
                session = self.with_part("pw", rounds=rounds, items=[{"id": key, "src": "ours/a.jpg"} for key in ids])
                trials = [trial for trial in part_of(self.design(session), "pw")["trials"] if "repeat_of" not in trial]
                shown = collections.Counter(key for trial in trials for key in trial["items"])
                self.assertEqual(set(shown.values()), {rounds})
                pairs = collections.Counter(taste.pair(*trial["items"]) for trial in trials)
                self.assertLessEqual(max(pairs.values()) - min(pairs.values()), 1)
                if rounds <= items - 1:
                    self.assertEqual(max(pairs.values()), 1, "no pair twice in one round robin")
                lefts = collections.Counter(trial["items"][0] for trial in trials)
                self.assertLessEqual(max(lefts[key] for key in ids) - min(lefts[key] for key in ids), 2)
                if items > 4:
                    for one, two in zip(trials, trials[1:]):
                        self.assertFalse(set(one["items"]) & set(two["items"]), "no item twice in a row")

    def test_a_pair_seen_again_comes_with_its_sides_swapped(self):
        trials = [trial for trial in part_of(self.design(self.with_part("pw", rounds=6)), "pw")["trials"] if "repeat_of" not in trial]
        first = {}
        for trial in trials:
            left, right = trial["items"]
            if taste.pair(left, right) in first:
                self.assertEqual(first[taste.pair(left, right)], (right, left))
            else:
                first[taste.pair(left, right)] = (left, right)

    def test_maxdiff_sets_of_four_show_every_item_as_often(self):
        trials = [trial for trial in part_of(self.design(), "md")["trials"] if "repeat_of" not in trial]
        self.assertEqual(len(trials), 8 * 3 // 4)
        self.assertTrue(all(len(set(trial["items"])) == 4 for trial in trials))
        self.assertEqual(set(collections.Counter(key for trial in trials for key in trial["items"]).values()), {3})

    def test_cbc_tasks_are_level_balanced_with_their_holdouts(self):
        part = part_of(self.design(), "cb")
        regular = [trial for trial in part["trials"] if "repeat_of" not in trial and not trial.get("holdout")]
        self.assertEqual(len(regular), 9)
        self.assertEqual(sum(bool(trial.get("holdout")) for trial in part["trials"]), 1)
        for trial in part["trials"]:
            self.assertEqual(len({json.dumps(option["levels"], sort_keys=True) for option in trial["options"]}), 3)
            for option in trial["options"]:
                self.assertEqual(option["src"], f"ours/r-{option['levels']['pace']}-{option['levels']['grade']}.mp4")
        for attribute in part["attributes"]:
            used = collections.Counter(option["levels"][attribute["id"]] for trial in regular for option in trial["options"])
            counts = [used[level["id"]] for level in attribute["levels"]]
            self.assertLessEqual(max(counts) - min(counts), 1, attribute["id"])

    def test_cbc_that_cant_tell_its_levels_apart_refuses(self):
        many = [{"id": f"a{k}", "name": f"A{k}", "levels": levels("x", "y", "z", "w", "v")} for k in range(4)]
        media = "ours/" + "-".join(f"{{a{k}}}" for k in range(4)) + ".mp4"
        self.trial_refused("2 tasks can't tell 16 level effects apart", self.with_part("cb", attributes=many, media=media, tasks=2, holdouts=0),
                           design_only=True)

    def test_about_one_trial_in_ten_comes_again_later_swapped_and_never_a_holdout(self):
        example = self.example()
        design = taste.checked_trial(example, PAGE, self.here, self.root, set())
        for part in design["parts"]:
            with self.subTest(part=part["id"]):
                trials = part["trials"]
                place = {trial["id"]: k for k, trial in enumerate(trials)}
                repeats = [trial for trial in trials if "repeat_of" in trial]
                if part["type"] not in SWAPPED or part.get("scored") is False:
                    self.assertEqual(repeats, [])
                    continue
                regular = [trial for trial in trials if "repeat_of" not in trial and not trial.get("holdout")]
                self.assertEqual(len(repeats), max(1, int(len(regular) / 10 + 0.5)))
                self.assertEqual([trial["id"] for trial in trials], [f"{part['id']}.{k}" for k in range(1, len(trials) + 1)])
                for repeat in repeats:
                    original = trials[place[repeat["repeat_of"]]]
                    self.assertNotIn("holdout", original)
                    self.assertNotIn("holdout", repeat)
                    self.assertNotIn("repeat_of", original)
                    if len(trials) - len(repeats) > taste.REPEAT_GAP + 1:
                        self.assertGreater(place[repeat["id"]] - place[original["id"]], taste.REPEAT_GAP)
                    else:  # a part too short for the gap: the repeat comes last
                        self.assertEqual(place[repeat["id"]], len(trials) - 1)
                    shown = "items" if "items" in repeat else "options"
                    self.assertNotEqual(repeat[shown], original[shown], "a repeat shows its sides swapped")
                    self.assertEqual(sorted(map(json.dumps, repeat[shown])), sorted(map(json.dumps, original[shown])))
                    if part["type"] == "pairwise":
                        self.assertEqual(repeat["items"], original["items"][::-1])

    def test_a_sequence_runs_every_dimension_up_then_down(self):
        session = self.with_part("sq", dimensions=[{"id": f"d{n}", "name": f"D{n}", "steps": [f"ours/s{k}.jpg" for k in range(1, 8)]}
                                                   for n in range(5)])
        trials = part_of(self.design(session), "sq")["trials"]
        self.assertEqual([trial["order"] for trial in trials], ["up"] * 5 + ["down"] * 5)
        self.assertEqual(sorted(trial["dimension"] for trial in trials[:5]), sorted(trial["dimension"] for trial in trials[5:]))
        self.assertNotEqual(trials[4]["dimension"], trials[5]["dimension"])

    def test_a_checklist_keeps_its_order_and_a_red_lines_list_is_shuffled_from_the_seed(self):
        design = self.design()
        self.assertEqual(part_of(design, "ck")["trials"], [{"candidates": ["Pace", "Grade", "Cover", "Hook"], "id": "ck.1"}])
        self.assertEqual(part_of(design, "ck")["mark"], "Not for him")
        shown = part_of(design, "rl")["trials"][0]["candidates"]
        self.assertEqual(sorted(shown), sorted(part_of(self.session, "rl")["candidates"]))
        without = self.with_part("ck")
        del part_of(without, "ck")["mark"]
        self.assertEqual(part_of(self.design(without), "ck")["mark"], "Tick")
        self.assertEqual(part_of(self.design(without), "ck")["question"], "Tick every line that applies.")


class TrialDesignOnly(Trial):
    def test_design_lists_the_missing_media_and_writes_nothing(self):
        for src in ("ours/b.jpg", "ours/r-mid-cool.mp4", "ours/s7.jpg"):
            (self.here / src).unlink()
        self.write()
        before = set(self.root.rglob("*"))
        out = json.loads(taste.build_session(PAGE, str(self.here / "session.json"), root=self.root, fonts=fake_fonts, design_only=True))
        self.assertEqual(set(self.root.rglob("*")), before)
        self.assertEqual(out["missing"], ["ours/b.jpg", "ours/r-mid-cool.mp4", "ours/s7.jpg"])
        self.assertEqual(set(out["files"]), files_of())
        self.assertEqual(out["design_id"], taste.checked_trial(self.session, PAGE, self.here, self.root, set())["design_id"])
        self.assertEqual([(part["id"], part["holdouts"]) for part in out["parts"] if part["holdouts"]], [("cb", 1)])
        self.assertEqual(out["trials"], sum(part["trials"] for part in out["parts"]))
        self.trial_refused("ours/b.jpg is missing or a link")

    def test_design_and_the_page_agree_on_the_design_id(self):
        out = json.loads(self.run_trial(design_only=True))
        self.assertEqual(out["missing"], [])
        self.assertEqual(out["design_id"], self.design()["design_id"])

    def test_design_still_refuses_what_the_page_refuses(self):
        (self.here / "ours" / "link.jpg").symlink_to(self.root / "nowhere.jpg")
        self.trial_refused("ours/link.jpg is missing or a link", self.with_item("md", src="ours/link.jpg"), design_only=True)
        self.trial_refused("unknown field", {**self.session, "seeds": 7}, design_only=True)

    def test_a_word_tells_two_sittings_of_one_day_apart(self):
        pilot = self.folder / (DAY + "-pilot")
        self.here.rename(pilot)
        (pilot / "session.json").write_text(json.dumps(self.session), encoding="utf-8")
        out = json.loads(taste.build_session(PAGE, str(pilot / "session.json"), root=self.root, fonts=fake_fonts, design_only=True))
        self.assertEqual(out["missing"], [])
        for word in ("Pilot", "pilot-2", "a-very-long-word"):
            bad = self.folder / f"{DAY}-{word}"
            pilot.rename(bad)
            with self.subTest(word=word), self.assertRaisesRegex(taste.Refused, re.escape("session-<YYYY-MM-DD>[-<word>]/")):
                taste.build_session(PAGE, str(bad / "session.json"), root=self.root, fonts=fake_fonts, design_only=True)
            bad.rename(pilot)

    def test_an_intro_line_with_a_merit_word_warns_and_still_passes(self):
        leaning = self.with_part("pw", intro=[{"name": "Pace", "line": "A studio or a street."},
                                              {"name": "Grade", "line": "Cool is calmer; warm suits a talk."}])
        self.write(leaning)
        before = set(self.root.rglob("*"))
        with contextlib.redirect_stderr(io.StringIO()) as err:
            out = json.loads(self.run_trial(leaning, design_only=True))
        self.assertEqual(out["design_id"], self.design()["design_id"])
        self.assertEqual(set(self.root.rglob("*")), before)
        self.assertEqual(err.getvalue().splitlines(), ["warning: pw's intro line 2 says 'calmer': an intro line says what varies,"
                                                       " never which is better (trial-schema.md)"])
        with contextlib.redirect_stderr(io.StringIO()) as err:
            self.run_trial(design_only=True)
            self.run_trial(leaning)
        self.assertEqual(err.getvalue(), "", "a neutral intro, or the page itself, gives no warning")

    def test_design_is_for_trial_sessions_only(self):
        weekly = {"page": PAGE, "title": "Session 1", "intro": "Three changes.", "items": []}
        self.trial_refused('--design is for a trial session, one with "mode": "trial"', weekly, design_only=True)

    def test_the_command_line(self):
        for argv, reason in ((["--page", PAGE, "--design"], "give --rubric and --picks, or --session alone"),
                             (["--page", PAGE, "--rubric", "r.json", "--picks", "p.json", "--design"], "--design goes with --session")):
            with self.subTest(argv=argv), contextlib.redirect_stderr(io.StringIO()) as err, self.assertRaises(SystemExit) as stop:
                taste.main(argv)
            self.assertEqual(stop.exception.code, 2)
            self.assertIn(reason, err.getvalue())
        self.write()
        real = taste.build_session
        here = lambda page, session, design_only=False: real(page, session, root=self.root, fonts=fake_fonts, design_only=design_only)
        with mock.patch.object(taste, "build_session", here), contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(taste.main(["--page", PAGE, "--session", str(self.here / "session.json"), "--design"]), 0)
        self.assertEqual(json.loads(out.getvalue())["design_id"], self.design()["design_id"])
        self.assertFalse((self.here / "picker.html").exists())


class TrialChildren(Trial):
    def with_post(self):
        session = json.loads(json.dumps(self.session))
        part_of(session, "pw")["items"][0] = {"id": "r1", "src": "ref/CzAbCdEfGhI.jpg", "post": "CzAbCdEfGhI"}
        return session

    def test_a_child_flagged_or_unflagged_item_passes(self):
        self.reel("DemoCode00N", flag="child on screen", caption=None, breakdown=None)
        self.reel("NoFlagLine1", style="Frames: 1\n", caption=None, breakdown=None)
        for code in ("DemoCode00N", "NoFlagLine1"):
            with self.subTest(code=code):
                session = self.with_item("pw", src=f"ref/{code}.mp4", reel=code)
                design = taste.checked_trial(session, PAGE, self.here, self.root, set())  # the media may be missing
                self.assertEqual(part_of(design, "pw")["items"][0]["reel"], code)
        self.post("CzAbCdEfGhI", flag="a child, briefly")
        (self.here / "ref" / "CzAbCdEfGhI.jpg").write_bytes(JPG)
        self.run_trial(self.with_post())

    def test_a_clean_post_passes(self):
        self.post("CzAbCdEfGhI")
        (self.here / "ref" / "CzAbCdEfGhI.jpg").write_bytes(JPG)
        self.run_trial(self.with_post())
        self.assertEqual(part_of(self.design(self.with_post()), "pw")["items"][0]["post"], "CzAbCdEfGhI")

    def test_a_reference_with_no_saved_item_refuses(self):
        self.trial_refused("DemoCode00Z: no folder of its own in reels/", self.with_item("pw", src="ref/DemoCode00Z.mp4", reel="DemoCode00Z"),
                           design_only=True)

    def test_a_ref_file_is_named_for_its_item_and_only_it_names_one(self):
        self.trial_refused("a ref/ file is named for its reel: ref/DemoCode00M.<suffix>", self.with_item("pw", src="ref/other.mp4"))
        self.trial_refused("only a ref/ file names a reel or post code", self.with_item("md", reel=REF))
        self.trial_refused("names no reel or post code", self.with_item("md", src=f"ref/{REF}.mp4"))
        self.trial_refused("names both a reel and a post", self.with_item("pw", post="CzAbCdEfGhI"))


class TrialRefusals(Trial):
    def test_media_stay_in_the_session_folder(self):
        for src in ("../a.jpg", "ours/../a.jpg", "ours/../../x.jpg", "/etc/hosts.jpg", "ours/sub/a.jpg", "a.jpg", "ours/.a.jpg",
                    "work/a.jpg", "ours/a.gif", "ours/a", "ours/" + "a" * 80 + ".jpg", 7, None):
            with self.subTest(src=src):
                self.trial_refused("src must be ref or ours/<file name> ending", self.with_item("md", src=src), design_only=True)
        self.trial_refused("step 1: src must be ours/<file name>", self.with_part("sq", dimensions=[
            {"id": "cut", "name": "Cut", "steps": [f"ref/{REF}.mp4"] + [f"ours/s{k}.jpg" for k in range(2, 8)]}]))

    def test_a_link_is_refused_file_or_folder(self):
        (self.here / "ours" / "link.jpg").symlink_to(self.here / "ours" / "a.jpg")
        self.trial_refused("ours/link.jpg is missing or a link", self.with_item("md", src="ours/link.jpg"))
        elsewhere = self.root / "elsewhere"
        (self.here / "ours").rename(elsewhere)
        (self.here / "ours").symlink_to(elsewhere)
        self.trial_refused("ours/ must be a folder, not a link", design_only=True)

    def test_a_file_must_be_what_its_name_says(self):
        (self.here / "ours" / "m0.jpg").write_bytes(PNG)
        self.trial_refused("ours/m0.jpg isn't a jpg file")
        (self.here / "ours" / "m0.jpg").write_bytes(JPG)
        (self.here / "ours" / "c.mp4").write_bytes(JPG)
        self.trial_refused("ours/c.mp4 isn't a mp4 file")

    def test_a_file_that_cant_be_read_refuses(self):
        self.write(None)
        before = sorted(self.root.rglob("*"))
        unreadable = self.here / "ours" / "m0.jpg"
        unreadable.chmod(0)
        self.addCleanup(unreadable.chmod, 0o644)
        with self.assertRaisesRegex(taste.Refused, "can't read ours/m0.jpg: Permission denied"):
            taste.build_session(PAGE, str(self.here / "session.json"), root=self.root, fonts=fake_fonts)
        self.assertEqual(sorted(self.root.rglob("*")), before, "a refusal must write nothing")

    def test_a_file_over_the_size_limit_refuses(self):
        with mock.patch.object(taste, "MEDIA_BYTES", len(JPG) - 1):
            self.trial_refused("and a file holds at most")

    def test_the_caps(self):
        self.assertEqual((taste.MAX_PARTS, taste.MAX_TRIALS, taste.MAX_MEDIA, taste.MEDIA_BYTES), (16, 700, 900, 50_000_000),
                         "raising a cap is a reviewed change")
        trials = sum(len(part["trials"]) for part in self.design()["parts"])
        with mock.patch.object(taste, "MAX_TRIALS", trials):
            self.run_trial()
        with mock.patch.object(taste, "MAX_TRIALS", trials - 1):
            self.trial_refused(f"{trials} trials with repeats, and a sitting holds at most {trials - 1}")
        files = len(files_of())
        with mock.patch.object(taste, "MAX_MEDIA", files - 1):
            self.trial_refused(f"{files} media files, and a sitting shows at most {files - 1}")
        many = [{**part_of(self.session, "ck"), "id": f"ck{n}"} for n in range(17)]
        self.trial_refused("the session holds 1 to 16 parts", {**self.session, "parts": many})
        self.trial_refused("the session holds 1 to 16 parts", {**self.session, "parts": []})

    def test_the_cbc_media_template(self):
        for media in ("ours/r-{pace}.mp4", "ours/r-{pace}-{grade}-{pace}.mp4", "ref/r-{pace}-{grade}.mp4", "ours/r-{pace}-{grade}-{x}.mp4",
                      "ours/r-{pace}-{grade}}.mp4", "ours/r-{Pace}-{grade}.mp4", None):
            with self.subTest(media=media):
                self.trial_refused(r"media must be ours/<file name> holding each \{attribute id\} once", self.with_part("cb", media=media))
        self.trial_refused("src must be ours/<file name>", self.with_part("cb", media="ours/../{pace}-{grade}.mp4"), design_only=True)

    def test_unknown_fields_are_refused_everywhere(self):
        session = json.loads(json.dumps(self.session))
        cases = {"the session": {**session, "seeds": 7}, "part pw": self.with_part("pw", item=[]),
                 "part md's item": self.with_item("md", source="ours/a.jpg")}
        attribute = self.with_part("cb")
        part_of(attribute, "cb")["attributes"][0]["level"] = "slow"
        cases["part cb's attribute 1"] = attribute
        level = self.with_part("cb")
        part_of(level, "cb")["attributes"][0]["levels"][0]["name"] = "Slow"
        cases["part cb's attribute pace: a level"] = level
        cases["part sq's dimension 1"] = self.with_part("sq", dimensions=[{**part_of(session, "sq")["dimensions"][0], "values": []}])
        cases["part pw's intro line 1"] = self.with_part("pw", intro=[{"name": "Pace", "text": "x"}])
        cases["part ck"] = self.with_part("ck", items=[])
        cases["part rl"] = self.with_part("rl", mark="No")
        for where, case in cases.items():
            with self.subTest(where):
                self.trial_refused(re.escape(where) + ": unknown field", case)

    def test_the_seed_and_the_break(self):
        for seed in (0, -5, 2 ** 31, "7", 7.0, True, None):
            with self.subTest(seed=seed):
                self.trial_refused("the seed must be a whole number from 1 to 2147483647", {**self.session, "seed": seed})
        self.run_trial({**self.session, "seed": 2 ** 31 - 1})
        for minutes in (19, 26, 22.5, "22"):
            with self.subTest(minutes=minutes):
                self.trial_refused("break_minutes must be a whole number from 20 to 25", {**self.session, "break_minutes": minutes})

    def test_the_mode_page_and_part_ids(self):
        self.trial_refused('a session\'s mode is "trial", or it has none', {**self.session, "mode": "weekly"})
        self.trial_refused("the session is for page 'acme', not demo", {**self.session, "page": "acme"})
        twice = json.loads(json.dumps(self.session))
        twice["parts"][1]["id"] = "pw"
        self.trial_refused("two parts share an id", twice)
        self.trial_refused("part pw: two items share an id", self.with_item("pw", id="a"))
        self.trial_refused("part xx: type must be one of", {**self.session, "parts": [{"id": "xx", "type": "rating"}]})

    def test_the_sizes_of_each_type(self):
        for reason, session in (
            ("part pw: an even number of items", self.with_part("pw", items=part_of(self.session, "pw")["items"] + [{"id": "d", "src": "ours/b.jpg"}])),
            ("part pw's rounds must be a whole number from 1 to 6", self.with_part("pw", rounds=7)),
            ("part pw: scored is true or false", self.with_part("pw", scored="no")),
            ("part md: items × appearances must divide by 4", self.with_part("md", appearances=5,
                                                                            items=part_of(self.session, "md")["items"][:7])),
            ("part md's appearances must be a whole number from 2 to 6", self.with_part("md", appearances=1)),
            ("part cb's holdouts must be a whole number from 0 to 4", self.with_part("cb", holdouts=5)),
            ("part cb's tasks must be a whole number from 2 to 30", self.with_part("cb", tasks=31)),
            ("part sq's dimension cut: 7 steps", self.with_part("sq", dimensions=[{"id": "cut", "name": "Cut", "steps": ["ours/s1.jpg"] * 6}])),
            ("part sq's dimension cut: 7 labels", self.with_part("sq", dimensions=[{**part_of(self.session, "sq")["dimensions"][0], "labels": ["a"]}])),
            ("part rg's dimension len's values: 2 to 12 lines", self.with_part("rg", dimensions=[{"id": "len", "name": "Length", "values": ["15 s"]}])),
            ("part ck's candidates: 1 to 30 lines", self.with_part("ck", candidates=[])),
            ("part ck's candidates: 1 to 30 lines", self.with_part("ck", candidates=[f"Line {n}" for n in range(31)])),
            ("part ck's candidates: two lines are the same", self.with_part("ck", candidates=["Pace", "Pace"])),
            ("part ck: the mark is a button, at most 40 characters", self.with_part("ck", mark="x" * 41)),
            ("part ck's mark is empty", self.with_part("ck", mark="  ")),
            ("part rl's candidates: 0 to 30 lines", self.with_part("rl", candidates=[f"Line {n}" for n in range(31)])),
            ("part pw: intro is a list of at most 16 lines", self.with_part("pw", intro=[{"name": "x", "line": "y"}] * 17)),
            ("part pw's title: 301 characters", self.with_part("pw", title="x" * 301)),
        ):
            with self.subTest(reason):
                self.trial_refused(re.escape(reason), session)
        self.run_trial(self.with_part("ck", mark="x" * 40))
        self.run_trial(self.with_part("rl", candidates=[]))


if __name__ == "__main__":
    unittest.main()
