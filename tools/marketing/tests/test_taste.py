"""taste/build.py: the refusals, the masks and the page. Fake frames and fonts, so no ffmpeg or node_modules is needed;
the pages in a real browser are taste.test.mjs and session.test.mjs."""
import base64
import contextlib
import io
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "taste"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "reels"))

import build as taste  # noqa: E402
import watch  # noqa: E402

PAGE = "demo"
STYLE = """style: {code}
Frames: 1, 5, 8, 15, 19, 23
Subtitles: White words, one to five
Fonts and colours: One clean font
Inserts: A phone held on camera
Overall: Clean
Newline: Added later
Flag: {flag}
"""
RUBRIC = {
    "title": "Your taste: demo",
    "intro": "I chose for you.",
    "assumed": ["Short cards liked"],
    "page_questions": [{"key": "length", "question": "How long?", "options": ["Under 30 s", "30-60 s"], "default": "30-60 s"}],
    "aspects": [
        {"key": "subs", "label": "Subtitles", "kinds": ["reel", "story"], "from": "style:Subtitles"},
        {"key": "desc", "label": "Description", "kinds": ["reel", "carousel", "post", "story"], "from": "description"},
        {"key": "count", "label": "Slides", "kinds": ["carousel"], "from": "slides"},
        {"key": "long", "label": "Length", "kinds": ["reel", "story", "post"], "from": "seconds"},
        {"key": "cover", "label": "Cover", "kinds": ["reel", "carousel"], "from": "cover"},
        {"key": "over", "label": "Overall", "kinds": ["reel"], "from": "style:Overall"},
    ],
}


def fake_frame(path, seconds, quality, root, image=False):
    fake_frame.calls.append((path, seconds, quality, image))
    return "data:image/jpeg;base64,AAAA"


def fake_fonts(root):
    return "/* fonts */"


class Taste(unittest.TestCase):
    def setUp(self):
        fake_frame.calls = []
        self.scratch = tempfile.TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)
        self.root = Path(self.scratch.name).resolve()
        self.folder = self.root / taste.TASTE / PAGE
        self.folder.mkdir(parents=True)
        (self.root / taste.REELS).mkdir(parents=True)
        (self.root / taste.POSTS).mkdir(parents=True)
        self.rubric = json.loads(json.dumps(RUBRIC))

    def reel(self, code="DemoCode00M", flag="none", caption="A caption", breakdown="format: talking head\n", style=None):
        folder = self.root / taste.REELS / code
        folder.mkdir()
        (folder / "style.md").write_text(style if style is not None else STYLE.format(code=code, flag=flag), encoding="utf-8")
        (folder / "metrics.json").write_text(json.dumps({
            "account": "someone.real", "multiple": 12.5, "length_seconds": 37.2,
            "sheet_whole": {"columns": 6, "rows": 4, "seconds_per_tile": 2.0}}), encoding="utf-8")
        (folder / "video.mp4").write_bytes(b"not a video")
        if caption is not None:
            (folder / "caption.txt").write_text(caption, encoding="utf-8")
        if breakdown is not None:
            (folder / "breakdown.md").write_text(breakdown, encoding="utf-8")
        return code

    def post(self, code="CzAbCdEfGhI", kind="carousel", flag="none", manifest=None, style=None):
        folder = self.root / taste.POSTS / code
        folder.mkdir()
        (folder / "style.md").write_text(style if style is not None else STYLE.format(code=code, flag=flag), encoding="utf-8")
        for name in ("1.jpg", "2.mp4", "cover.jpg"):
            (folder / name).write_bytes(b"x")
        whole = {"kind": kind, "code": code, "account": "someone.real", "date": "2026-01-06", "description": "A post",
                 "cover": "cover.jpg",
                 "slides": [{"file": "1.jpg", "type": "image"}, {"file": "2.mp4", "type": "video", "seconds": 12.5}]}
        (folder / "MANIFEST.json").write_text(json.dumps({**whole, **(manifest or {})}), encoding="utf-8")
        return code

    def write_inputs(self, items, round_number=1):
        (self.folder / "rubric.json").write_text(json.dumps(self.rubric), encoding="utf-8")
        (self.folder / "picks.json").write_text(json.dumps({"round": round_number, "items": items}), encoding="utf-8")

    def run_build(self, items=None, page=PAGE, **kwargs):
        if items is not None:
            self.write_inputs(items)
        return taste.build(page, str(self.folder / "rubric.json"), str(self.folder / "picks.json"),
                           root=self.root, grab=fake_frame, fonts=fake_fonts, **kwargs)

    def page(self):
        return (self.folder / "picker.html").read_text(encoding="utf-8")

    def refused(self, reason, items=None, page=PAGE):
        with self.assertRaisesRegex(taste.Refused, reason):
            self.run_build(items, page=page)
        self.assertFalse((self.folder / "picker.html").exists(), "a refusal must write nothing")
        self.assertEqual(sorted(path.name for path in self.folder.iterdir()), ["picks.json", "rubric.json"])

    @staticmethod
    def item(code, kind="reel", **picks):
        return {"code": code, "kind": kind, "picks": picks or {"subs": "L"}}


class Page(Taste):
    def test_a_mix_of_kinds_shows_each_item_only_its_aspects(self):
        reel = self.reel()
        carousel = self.post()
        story = self.post("StOrYcOdE12", kind="story", manifest={"cover": None, "slides": [{"file": "2.mp4", "type": "video", "seconds": 9}]})
        result = self.run_build([
            self.item(reel, subs="L", desc="D", long="L", over="D"),
            self.item(carousel, "carousel", desc="L", count="L", cover="D"),
            self.item(story, "story", desc="L", long="D", cover="L", count="L"),
        ])
        text = self.page()
        cards = re.findall(r'<article class="item".*?</article>', text, re.S)
        self.assertEqual(len(cards), 3)
        keys = [re.findall(r'data-aspect="([^"]+)"', card) for card in cards]
        self.assertEqual(keys, [["subs", "desc", "long", "over"], ["desc", "count", "cover"], ["desc", "long"]])
        self.assertIn("37 seconds", cards[0])
        self.assertIn("2 slides", cards[1])
        self.assertIn('alt="Cover"', cards[1])
        self.assertIn("9 seconds", cards[2])
        self.assertIn(f'href="https://www.instagram.com/reel/{reel}/"', cards[0])
        self.assertIn(f'href="https://www.instagram.com/p/{carousel}/"', cards[1])
        self.assertNotIn("href", cards[2])
        self.assertIn(f"{story}/cover", result)
        self.assertIn(f"{story}/count", result)
        self.assertIn('data-pre="D"', cards[0])
        self.assertIn('id="i1-subs-L" value="L" checked', cards[0])

    def test_the_page_answers_come_once_at_the_top_each_pre_selected(self):
        self.run_build([self.item(self.reel()), self.item(self.reel("DemoCode00N"))])
        text = self.page()
        self.assertEqual(text.count('<fieldset class="question"'), 1)
        self.assertLess(text.index('class="questions"'), text.index('class="item"'))
        self.assertIn('value="30-60 s" checked', text)
        self.assertNotIn('value="Under 30 s" checked', text)

    def test_a_new_style_aspect_needs_no_code(self):
        self.rubric["aspects"].append({"key": "inserts", "label": "Inserts", "kinds": ["reel"], "from": "style:Inserts"})
        self.run_build([self.item(self.reel(), inserts="L")])
        self.assertIn("A phone held on camera", self.page())

    def test_the_breakdown_and_caption_are_optional(self):
        self.run_build([self.item(self.reel(caption=None, breakdown=None), subs="L", desc="L")])
        self.assertEqual(re.findall(r'data-aspect="([^"]+)"', self.page()), ["subs"])

    def test_a_reel_shows_its_saved_cover_and_none_without_one(self):
        with_cover = self.reel()
        (self.root / taste.REELS / with_cover / "cover.jpg").write_bytes(b"x")
        without = self.reel("DemoCode00N")
        result = self.run_build([self.item(with_cover, cover="L"), self.item(without, cover="L", subs="L")])
        cards = re.findall(r'<article class="item".*?</article>', self.page(), re.S)
        self.assertIn('alt="Cover"', cards[0])
        self.assertNotIn('alt="Cover"', cards[1])
        self.assertIn(f"{without}/cover", result)
        self.assertIn(self.root / taste.REELS / with_cover / "cover.jpg", [path for path, *_ in fake_frame.calls])

    def test_a_linked_reel_cover_refuses(self):
        code = self.reel()
        outside = self.root / "outside.jpg"
        outside.write_bytes(b"x")
        (self.root / taste.REELS / code / "cover.jpg").symlink_to(outside)
        self.refused(f"{code}: cover.jpg is missing or a link", [self.item(code, cover="L")])

    def test_a_breakdown_gives_the_format_line(self):
        self.run_build([self.item(self.reel())])
        self.assertIn('<p class="format">talking head</p>', self.page())

    def test_pages_are_separate(self):
        (self.root / taste.TASTE / "acme").mkdir()
        self.run_build([self.item(self.reel())])
        self.assertIn('data-page="demo"', self.page())
        self.assertFalse((self.root / taste.TASTE / "acme" / "picker.html").exists())

    def test_the_round_is_in_the_page(self):
        self.write_inputs([self.item(self.reel())], round_number=3)
        self.run_build()
        self.assertIn('data-round="3"', self.page())

    def test_nothing_is_written_but_the_picker(self):
        self.write_inputs([self.item(self.reel())])
        before = set(self.root.rglob("*"))
        self.run_build()
        self.assertEqual(set(self.root.rglob("*")) - before, {self.folder / "picker.html"})
        self.run_build()
        self.assertEqual(set(self.root.rglob("*")) - before, {self.folder / "picker.html"})

    def test_the_picker_is_readable_like_any_file(self):
        self.run_build([self.item(self.reel())])
        self.assertEqual(stat.S_IMODE((self.folder / "picker.html").stat().st_mode), 0o644)

    def test_a_link_at_picker_html_is_replaced_and_not_followed(self):
        outside = self.root / "outside.html"
        outside.write_text("mine", encoding="utf-8")
        (self.folder / "picker.html").symlink_to(outside)
        self.run_build([self.item(self.reel())])
        self.assertEqual(outside.read_text(encoding="utf-8"), "mine")
        self.assertFalse((self.folder / "picker.html").is_symlink())

    def test_nothing_on_the_page_can_load_from_outside(self):
        self.run_build([self.item(self.reel())])
        self.assertIn("default-src 'none'", self.page())
        self.assertEqual(re.findall(r'(?:src|href)="(?!data:|https://www\.instagram\.com/reel/)', self.page()), [])

    def test_a_linked_media_folder_counts(self):
        marketing = self.root / "workspaces/marketing"
        cloud = self.root / "cloud"
        (marketing / "media").rename(cloud)
        (marketing / "media").symlink_to(cloud)
        self.folder = marketing / "media/taste" / PAGE
        self.run_build([self.item(self.reel())])
        self.assertTrue((cloud / "taste" / PAGE / "picker.html").is_file())

    def test_the_font_ranges_cover_accented_letters(self):
        for subset, letters in (("latin", "äöüßñ"), ("latin-ext", "čšžłı")):
            low, high = re.match(r"U\+(\w+)-(\w+)", dict(taste.FONT_RANGES)[subset]).groups()
            for letter in letters:
                self.assertTrue(int(low, 16) <= ord(letter) <= int(high, 16))

    def test_a_refusal_exits_1_with_its_reason(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code = taste.main(["--page", "../outside", "--rubric", "r", "--picks", "p"])
        self.assertEqual(code, 1)
        self.assertIn("refused:", err.getvalue())


class Text(Taste):
    def test_the_masks_are_watch_pys(self):
        self.assertEqual(taste.MENTION.pattern, watch.MENTION.pattern)
        self.assertEqual(taste.PHONE.pattern, watch.PHONE.pattern)

    def test_the_cut_is_trend_readers(self):
        reader = (Path(__file__).resolve().parents[3] / "scripts/hooks/trend_reader.py").read_text(encoding="utf-8")
        self.assertIn(f".slice(0,{taste.DESCRIPTION_CHARS})", reader)

    def test_descriptions_are_masked_then_cut(self):
        self.run_build([self.item(self.reel(caption="Call +49 555 123 4567 or @someone, mail a.b@c.de now\nnext line"), desc="L")])
        text = self.page()
        self.assertNotIn("555", text)
        self.assertNotIn("someone,", text)
        self.assertNotIn("a.b@", text)
        self.assertIn("Call ... or @..., mail @... now next line", text)

    def test_a_cut_cannot_leave_part_of_a_number(self):
        lead = "x" * (taste.DESCRIPTION_CHARS - 5)
        self.run_build([self.item(self.reel(caption=f"{lead} +49 555 123 4567"), desc="L")])
        self.assertNotRegex(self.page(), "x +\\+?4")

    def test_a_long_description_is_cut(self):
        self.run_build([self.item(self.reel(caption="ä" * 500), desc="L")])
        self.assertEqual(self.page().count("ä"), taste.DESCRIPTION_CHARS)

    def test_style_values_format_lines_and_dates_are_cut_too(self):
        style = STYLE.format(code="x", flag="none").replace("White words, one to five", "ä" * 500)
        self.run_build([self.item(self.reel(style=style, breakdown="format: " + "ö" * 500 + "\n"), subs="L")])
        self.assertEqual(self.page().count("ä"), taste.DESCRIPTION_CHARS)
        self.assertEqual(self.page().count("ö"), taste.DESCRIPTION_CHARS)
        self.run_build([self.item(self.post(manifest={"date": "ü" * 500}), "carousel", desc="L")])
        self.assertEqual(self.page().count("ü"), taste.DESCRIPTION_CHARS - len("carousel "))

    def test_an_all_digit_handle_is_masked(self):
        reel = self.reel()
        metrics = self.root / taste.REELS / reel / "metrics.json"
        metrics.write_text(metrics.read_text(encoding="utf-8").replace("someone.real", "495551234567"), encoding="utf-8")
        self.run_build([self.item(reel), self.item(self.post(manifest={"account": "de.495551234577"}), "carousel", desc="L")])
        text = self.page()
        self.assertEqual((text.count("555123456"), text.count("555123457")), (0, 0))
        self.assertEqual(text.count("@de....<"), 1)

    def test_a_number_split_over_lines_is_masked_too(self):
        self.run_build([self.item(self.reel(caption="+49\n555\n123\n4567"), desc="L")])
        self.assertNotIn("555", self.page())

    def test_page_text_is_escaped_everywhere(self):
        attack = '<script>alert(1)</script>" onload="x'
        style = STYLE.format(code="x", flag="none").replace("White words, one to five", attack)
        self.run_build([self.item(self.reel(style=style, caption=attack, breakdown=f"format: {attack}\n"), subs="L", desc="L")])
        self.assertNotIn("<script>alert", self.page())
        self.assertNotIn('" onload="', self.page())

    def test_the_rubric_is_escaped_too(self):
        self.rubric["title"] = "<b>t</b>"
        self.rubric["assumed"] = ["<i>a</i>"]
        self.rubric["page_questions"][0]["question"] = '<u>q</u>"'
        self.rubric["page_questions"][0]["options"] = ['a"b', "c"]
        self.rubric["page_questions"][0]["default"] = 'a"b'
        self.rubric["aspects"][0]["label"] = '"><img src=x>'
        self.run_build([self.item(self.reel())])
        text = self.page()
        for raw in ("<b>t</b>", "<i>a</i>", "<u>q</u>", 'a"b', "<img src=x>"):
            self.assertNotIn(raw, text)

    def test_a_template_mark_in_a_description_stays_text(self):
        self.run_build([self.item(self.reel(caption="/*JS*/ __TITLE__ <!--ITEMS-->"), desc="L")])
        text = self.page()
        self.assertIn("/*JS*/ __TITLE__ &lt;!--ITEMS--&gt;", text)
        self.assertEqual(text.count("window.pickerText = "), 1)

    def test_a_manifest_cannot_set_a_link(self):
        self.run_build([self.item(self.post(manifest={"link": "https://evil.example/"}), "carousel", desc="L")])
        self.assertNotIn("evil.example", self.page())

    def test_the_handle_must_be_a_handle(self):
        code = self.post(manifest={"account": "a b\nnew line"})
        self.refused("isn't a handle", [self.item(code, "carousel", desc="L")])


class Caps(Taste):
    def test_thirty_items_pass_and_thirty_one_do_not(self):
        codes = [self.reel(f"reel-{n:03}") for n in range(31)]
        self.run_build([self.item(code) for code in codes[:30]])
        self.assertEqual(self.page().count('<article class="item"'), 30)
        (self.folder / "picker.html").unlink()
        self.refused("31 items", [self.item(code) for code in codes])

    def test_four_aspects_pass_and_five_do_not(self):
        self.rubric["aspects"].append({"key": "fonts", "label": "Fonts", "kinds": ["reel"], "from": "style:Fonts and colours"})
        code = self.reel()
        self.run_build([self.item(code, subs="L", desc="L", long="L", over="L")])
        (self.folder / "picker.html").unlink()
        self.refused("5 aspects", [self.item(code, subs="L", desc="L", long="L", over="L", fonts="L")])

    def test_five_page_questions_pass_and_six_do_not(self):
        questions = [{"key": f"q{n}", "question": "How long?", "options": ["a", "b"], "default": "a"} for n in range(6)]
        code = self.reel()
        self.rubric["page_questions"] = questions[:5]
        self.run_build([self.item(code)])
        self.assertEqual(self.page().count('<fieldset class="question"'), 5)
        (self.folder / "picker.html").unlink()
        self.rubric["page_questions"] = questions
        self.refused("6 page questions", [self.item(code)])

    def test_quality_drops_to_fit_the_limit(self):
        def by_quality(path, seconds, quality, root, image=False):
            return "data:image/jpeg;base64," + "A" * (taste.LIMIT if quality < 9 else 1000)

        self.write_inputs([self.item(self.reel())])
        result = taste.build(PAGE, str(self.folder / "rubric.json"), str(self.folder / "picks.json"),
                             root=self.root, grab=by_quality, fonts=fake_fonts)
        self.assertIn("quality 9", result)

    def test_over_the_limit_at_the_lowest_quality_refuses(self):
        def huge(path, seconds, quality, root, image=False):
            return "data:image/jpeg;base64," + "A" * taste.LIMIT

        self.write_inputs([self.item(self.reel())])
        with self.assertRaisesRegex(taste.Refused, "over the 15 MB limit"):
            taste.build(PAGE, str(self.folder / "rubric.json"), str(self.folder / "picks.json"),
                        root=self.root, grab=huge, fonts=fake_fonts)
        self.assertFalse((self.folder / "picker.html").exists())


class Children(Taste):
    """Nothing is refused for a child on screen: a style note's flags refuse nothing."""

    def test_a_child_flagged_or_unflagged_item_builds(self):
        unflagged = STYLE.format(code="x", flag="none").replace("Flag: none\n", "")
        codes = [self.reel(flag="child on screen"), self.reel("DemoCode00N", style=unflagged),
                 self.reel("DemoCode00O", style=STYLE.format(code="x", flag="none") + "Child: yes\n")]
        posts = [self.post(flag="child on screen"), self.post("CzAbCdEfGhJ", style=unflagged)]
        self.run_build([self.item(code) for code in codes] + [self.item(post, "carousel", desc="L") for post in posts])
        for code in codes + posts:
            self.assertIn(code, self.page())

    def test_no_style_note_refuses(self):
        code = self.reel()
        (self.root / taste.REELS / code / "style.md").unlink()
        self.refused("style.md is missing", [self.item(code)])


class Refusals(Taste):
    def test_bad_page_names(self):
        self.write_inputs([self.item(self.reel())])
        for page in ("../outside", "a/b", "", ".hidden", "UPPER", "a\n"):
            with self.subTest(page=page), self.assertRaisesRegex(taste.Refused, "page name"):
                self.run_build(page=page)

    def test_the_page_folder_must_exist(self):
        self.write_inputs([self.item(self.reel())])
        with self.assertRaisesRegex(taste.Refused, "existing folder"):
            self.run_build(page="missing")
        self.assertFalse((self.root / taste.TASTE / "missing").exists())

    def test_a_linked_page_folder_refuses(self):
        self.write_inputs([self.item(self.reel())])
        (self.root / taste.TASTE / "linked").symlink_to(self.folder)
        with self.assertRaisesRegex(taste.Refused, "not a link"):
            self.run_build(page="linked")

    def test_a_linked_taste_folder_refuses(self):
        self.write_inputs([self.item(self.reel())])
        taste_folder = self.root / taste.TASTE
        moved = self.root / "elsewhere"
        taste_folder.rename(moved)
        taste_folder.symlink_to(moved)
        with self.assertRaisesRegex(taste.Refused, "not a link"):
            self.run_build()

    def test_inputs_outside_the_folder_refuse(self):
        self.write_inputs([self.item(self.reel())])
        outside = self.root / "rubric.json"
        outside.write_text(json.dumps(self.rubric), encoding="utf-8")
        link = self.folder / "linked.json"
        link.symlink_to(outside)
        for rubric in (str(outside), str(link), str(self.folder / "missing.json")):
            with self.subTest(rubric=rubric), self.assertRaisesRegex(taste.Refused, "directly in"):
                taste.build(PAGE, rubric, str(self.folder / "picks.json"), root=self.root, grab=fake_frame, fonts=fake_fonts)

    def test_a_linked_item_refuses(self):
        real = self.reel()
        os.symlink(self.root / taste.REELS / real, self.root / taste.REELS / "linked-reel")
        self.refused("no folder of its own", [self.item("linked-reel")])

    def test_a_linked_file_in_an_item_refuses(self):
        code = self.reel()
        folder = self.root / taste.REELS / code
        (folder / "video.mp4").unlink()
        (folder / "video.mp4").symlink_to(self.root / "outside.mp4")
        (self.root / "outside.mp4").write_bytes(b"x")
        self.refused("video.mp4 is missing or a link", [self.item(code)])

    def test_a_linked_optional_file_refuses(self):
        code = self.reel(caption=None)
        (self.root / "outside.txt").write_text("private", encoding="utf-8")
        (self.root / taste.REELS / code / "caption.txt").symlink_to(self.root / "outside.txt")
        self.refused("caption.txt is missing or a link", [self.item(code)])

    def test_unsafe_manifest_file_names_refuse(self):
        for number, name in enumerate(("../../secret.jpg", "/etc/passwd", ".hidden.jpg", "a b.jpg")):
            code = self.post(f"badfile-{number}", manifest={"slides": [{"file": name, "type": "image"}]})
            self.refused("bad file name", [self.item(code, "carousel", desc="L")])

    def test_an_unsafe_cover_name_refuses(self):
        self.refused("bad cover", [self.item(self.post(manifest={"cover": "../x.jpg"}), "carousel", desc="L")])

    def test_a_linked_slide_refuses(self):
        code = self.post()
        folder = self.root / taste.POSTS / code
        (folder / "1.jpg").unlink()
        (self.root / "outside.jpg").write_bytes(b"x")
        (folder / "1.jpg").symlink_to(self.root / "outside.jpg")
        self.refused("1.jpg is missing or a link", [self.item(code, "carousel", desc="L")])

    def test_the_manifest_must_agree_with_the_pick(self):
        self.refused("says something else", [self.item(self.post(kind="story"), "carousel", desc="L")])

    def test_a_video_slide_needs_a_length(self):
        code = self.post(manifest={"slides": [{"file": "2.mp4", "type": "video"}]})
        self.refused("no length", [self.item(code, "carousel", desc="L")])

    def test_an_infinite_length_is_no_length(self):
        code = self.post(manifest={"slides": [{"file": "2.mp4", "type": "video", "seconds": float("inf")}]})
        self.refused("no length", [self.item(code, "carousel", desc="L")])
        reel = self.reel()
        metrics = self.root / taste.REELS / reel / "metrics.json"
        metrics.write_text(metrics.read_text(encoding="utf-8").replace("37.2", "Infinity").replace("12.5", "Infinity"), encoding="utf-8")
        result = self.run_build([self.item(reel, subs="L", long="L")])
        self.assertIn(f"{reel}/long", result)
        self.assertNotIn("inf", self.page())

    def test_deep_nesting_refuses_and_writes_nothing(self):
        deep = "[" * 1_000_000 + "]" * 1_000_000
        code = self.reel()
        self.write_inputs([self.item(code)])
        (self.folder / "rubric.json").write_text(deep, encoding="utf-8")
        self.refused("rubric.json")
        self.write_inputs([self.item(code)])
        (self.root / taste.REELS / code / "metrics.json").write_text(deep, encoding="utf-8")
        self.refused(f"{code}: can't read it")

    def test_bad_picks(self):
        reel = self.reel()
        for items, reason in (
            ([], "no items"),
            ([self.item(reel), self.item(reel)], "listed twice"),
            ([self.item("../../x")], "isn't a post code"),
            ([{**self.item(reel), "kind": "tweet"}], "kind must be"),
            ([self.item(reel, subs="X")], "must be L or D"),
            ([self.item(reel, nosuch="L")], "isn't in the rubric"),
            ([{"code": reel, "kind": "reel", "picks": {}}], "no picks"),
        ):
            with self.subTest(reason=reason):
                self.refused(reason, items)

    def test_a_bad_round_refuses(self):
        for value in (0, -1, "1", True, None):
            (self.folder / "rubric.json").write_text(json.dumps(self.rubric), encoding="utf-8")
            (self.folder / "picks.json").write_text(json.dumps({"round": value, "items": [self.item(self.reel(f"round{value}x"))]}), encoding="utf-8")
            with self.subTest(round=value), self.assertRaisesRegex(taste.Refused, "need a round"):
                self.run_build()

    def test_an_item_with_nothing_to_show_refuses(self):
        self.refused("nothing to show|none of its picks", [self.item(self.reel(), cover="L")])

    def test_bad_rubrics(self):
        reel = self.reel()
        for change, reason in (
            (lambda r: r.pop("title"), "needs a title"),
            (lambda r: r.pop("aspects"), "needs aspects"),
            (lambda r: r["aspects"][0].update({"from": "shell:ls"}), "from is style"),
            (lambda r: r["aspects"][0].update({"from": "style:"}), "from is style"),
            (lambda r: r["aspects"][0].update({"kinds": ["tweet"]}), "kinds are"),
            (lambda r: r["aspects"][0].update({"key": "A b"}), "aspect key"),
            (lambda r: r["aspects"].append(dict(r["aspects"][0])), "share a key"),
            (lambda r: r["page_questions"][0].update({"default": "Never"}), "default must be"),
            (lambda r: r["page_questions"][0].update({"options": ["one"]}), "two or more"),
            (lambda r: r["page_questions"][0].update({"options": ["a", "a"], "default": "a"}), "two or more"),
        ):
            with self.subTest(reason=reason):
                self.rubric = json.loads(json.dumps(RUBRIC))
                change(self.rubric)
                self.refused(reason, [self.item(reel)])

    def test_a_broken_metrics_file_refuses_and_names_the_item(self):
        code = self.reel()
        (self.root / taste.REELS / code / "metrics.json").write_text("{", encoding="utf-8")
        self.refused(code, [self.item(code)])

    def test_bad_frames_refuse(self):
        style = STYLE.format(code="x", flag="none").replace("1, 5, 8, 15, 19, 23", "1, 5, 99")
        self.refused("Frames must be", [self.item(self.reel(style=style))])

    def test_ffmpeg_failing_refuses_and_names_the_item(self):
        def broken(path, seconds, quality, root, image=False):
            raise OSError("no ffmpeg")

        self.write_inputs([self.item(self.reel())])
        with self.assertRaisesRegex(taste.Refused, "DemoCode00M: ffmpeg"):
            taste.build(PAGE, str(self.folder / "rubric.json"), str(self.folder / "picks.json"),
                        root=self.root, grab=broken, fonts=fake_fonts)

    def test_missing_fonts_refuse(self):
        self.write_inputs([self.item(self.reel())])
        with self.assertRaisesRegex(taste.Refused, "npm install"):
            taste.build(PAGE, str(self.folder / "rubric.json"), str(self.folder / "picks.json"), root=self.root, grab=fake_frame)


class Frame(Taste):
    """frame() itself, with subprocess.run faked: its flags are all that limits what ffmpeg opens in a downloaded file."""

    def ffmpeg(self, image, stdout=b"jpeg"):
        calls = []

        def run(argv, **options):
            calls.append((argv, options))
            return subprocess.CompletedProcess(argv, 0, stdout=stdout, stderr=b"")

        path = self.root / taste.REELS / "DemoCode00M" / ("1.jpg" if image else "video.mp4")
        with mock.patch.object(taste.subprocess, "run", run):
            uri = taste.frame(path, 2.5, 7, self.root, image=image)
        self.assertEqual(len(calls), 1)
        argv, options = calls[0]
        self.assertEqual(argv[0], str(self.root / taste.FFMPEG))
        self.assertEqual(argv.count("-i"), 1)
        self.assertEqual(argv[argv.index("-i") + 1], str(path))
        self.assertEqual((options.get("capture_output"), options.get("check"), options.get("timeout")), (True, True, 60))
        self.assertEqual(uri, "data:image/jpeg;base64," + base64.b64encode(stdout).decode())
        before = argv[:argv.index("-i")]
        return before, set(zip(before, before[1:]))

    def test_a_video_is_read_as_mov_from_a_file_only(self):
        before, pairs = self.ffmpeg(image=False)
        self.assertIn("-nostdin", before)
        self.assertLessEqual({("-protocol_whitelist", "file"), ("-f", "mov"), ("-ss", "2.50")}, pairs)
        self.assertNotIn("image2", before)

    def test_an_image_is_read_as_one_image_from_a_file_only(self):
        before, pairs = self.ffmpeg(image=True)
        self.assertIn("-nostdin", before)
        self.assertLessEqual({("-protocol_whitelist", "file"), ("-f", "image2"), ("-pattern_type", "none")}, pairs)
        self.assertNotIn("-ss", before)

    def test_no_frame_refuses(self):
        with self.assertRaisesRegex(taste.Refused, "no frame"):
            self.ffmpeg(image=False, stdout=b"")

    def test_frames_are_340_wide_and_session_images_720(self):
        for width, scale in ((None, "scale=340:-2"), (taste.SESSION_WIDTH, "scale=720:-2")):
            calls = []
            run = lambda argv, **options: calls.append(argv) or subprocess.CompletedProcess(argv, 0, stdout=b"jpeg", stderr=b"")
            with mock.patch.object(taste.subprocess, "run", run):
                taste.frame(self.root / "a.jpg", 0, 7, self.root, True, **({"width": width} if width else {}))
            self.assertEqual(calls[0][calls[0].index("-vf") + 1], scale)


DAY = "session-2026-01-06"
REEL = "DemoCode00M"


def fake_image(path, seconds, quality, root, image=False, width=taste.WIDTH):
    fake_image.calls.append((path, quality, image, width))
    return "data:image/jpeg;base64,AAAA"


class Session(Taste):
    """A session: session.json and its images in media/taste/<page>/session-<date>/."""

    def setUp(self):
        super().setUp()
        fake_image.calls = []
        self.here = self.folder / DAY
        for sub in ("ref", "ours"):
            (self.here / sub).mkdir(parents=True)
        for name in ("ref/t1-1.jpg", "ref/t1-2.jpg", "ref/t1-3.jpg", "ref/t1-4.jpg",
                     "ours/t1-a.png", "ours/t1-b.png", "ours/t1-c.png", "ours/t1-d.png"):
            (self.here / name).write_bytes(b"x")
        self.reel(REEL, caption=None, breakdown=None)
        self.session = {"page": PAGE, "title": "Session 1: demo", "intro": "Three changes.", "items": [self.entry()]}

    @staticmethod
    def entry(key="t1", part="taste", **changes):
        whole = {"id": key, "part": part, "title": "Labels on the screen", "why": "Cooking reels ran x2 with labels.",
                 "links": [f"https://www.instagram.com/reel/{REEL}/"],
                 "reference": [{"src": "ref/t1-1.jpg", "caption": "cooking, x2", "reel": REEL}],
                 "options": [{"key": "A", "label": "Ours: German labels", "src": "ours/t1-a.png"},
                             {"key": "B", "label": "Ours: English labels", "src": "ours/t1-b.png"}],
                 "old": "Labels in French only.", "new": "Labels in French and German.",
                 "choices": ["Adopt A", "Adopt B", "Try", "Skip"], "default": "Adopt A"}
        return {**whole, **changes}

    def write(self, session=None):
        (self.here / "session.json").write_text(json.dumps(self.session if session is None else session), encoding="utf-8")

    def run_session(self, session=None, page=PAGE, grab=fake_image, **kwargs):
        self.write(session)
        return taste.build_session(page, str(self.here / "session.json"), root=self.root, grab=grab, fonts=fake_fonts, **kwargs)

    def page(self):
        return (self.here / "picker.html").read_text(encoding="utf-8")

    def card(self, key):
        return re.search(rf'<article class="item" data-id="{key}".*?</article>', self.page(), re.S)[0]

    def session_refused(self, reason, session=None, page=PAGE, file=None):
        self.write(session)
        before = set(self.root.rglob("*"))
        fake_image.calls = []
        with self.assertRaisesRegex(taste.Refused, reason):
            taste.build_session(page, str(file or self.here / "session.json"), root=self.root, grab=fake_image, fonts=fake_fonts)
        self.assertEqual(set(self.root.rglob("*")), before, "a refusal must write nothing")
        self.assertEqual(fake_image.calls, [], "no image is read before the whole session has passed")

    def with_item(self, **changes):
        return {**self.session, "items": [self.entry(**changes)]}


class SessionPage(Session):
    def test_one_card_per_item_with_the_images_side_by_side_and_the_answer(self):
        self.session["items"] = [self.entry("o1", "overview", reference=[], options=[], old="", new="", links=[],
                                            choices=["Agree", "Discuss"], default="Agree"),
                                 self.entry(), self.entry("b1", "brand", reference=[], why="")]
        result = self.run_session()
        self.assertIn("3 items", result)
        self.assertEqual(self.page().count('<article class="item"'), 3)
        self.assertIn('data-page="demo" data-session="session-2026-01-06"', self.page())
        t1, o1, b1 = self.card("t1"), self.card("o1"), self.card("b1")
        self.assertIn('<div class="compare both"><div class="side"><h3>What we saw</h3>', t1)
        self.assertIn("<h3>Ours</h3>", t1)
        self.assertEqual(t1.count("<img"), 3)
        self.assertIn('<div class="compare"><div class="side"><h3>Ours</h3>', b1)
        self.assertNotIn("compare", o1)
        self.assertIn('<div class="answer wide">', o1)
        self.assertIn('<fieldset class="choice" data-pre="Adopt A">', t1)
        self.assertIn('value="Adopt A" checked>', t1)
        self.assertEqual(t1.count(" checked"), 1)
        self.assertIn('value="Agree" checked>', o1)
        self.assertIn('aria-label="Note on t1"', t1)
        self.assertIn("<b>A</b> Ours: German labels", t1)
        self.assertIn("cooking, x2", t1)
        self.assertEqual({(quality, image, width) for _, quality, image, width in fake_image.calls}, {(5, True, 720)})
        self.assertEqual([path.name for path, *_ in fake_image.calls], ["t1-1.jpg", "t1-a.png", "t1-b.png", "t1-a.png", "t1-b.png"])

    def test_the_change_shows_what_goes_and_what_comes(self):
        self.session["items"] = [self.entry(), self.entry("n1", old=""), self.entry("g1", new=""), self.entry("e1", old="", new="")]
        self.run_session()
        self.assertIn('<p class="old"><span class="tag">Now</span>Labels in French <del>only.</del></p>', self.card("t1"))
        self.assertIn('<p class="new"><span class="tag">Proposed</span>Labels in French <ins>and German.</ins></p>', self.card("t1"))
        self.assertIn("Nothing yet: a new line.", self.card("n1"))
        self.assertIn("<ins>Labels in French and German.</ins>", self.card("n1"))
        self.assertIn("<del>Labels in French only.</del>", self.card("g1"))
        self.assertIn("Nothing: the line goes.", self.card("g1"))
        self.assertNotIn('class="change"', self.card("e1"))

    def test_links_are_rebuilt_from_their_code(self):
        self.run_session(self.with_item(links=["https://instagram.com/p/CzAbCdEfGhI/?igsh=abc", f" https://www.instagram.com/reel/{REEL} "]))
        self.assertIn('<a href="https://www.instagram.com/p/CzAbCdEfGhI/" target="_blank" rel="noopener">', self.page())
        self.assertIn(f'<a href="https://www.instagram.com/reel/{REEL}/" target="_blank" rel="noopener">', self.page())
        self.assertNotIn("igsh", self.page())

    def test_text_is_masked_and_escaped_everywhere(self):
        self.session["title"] = "<b>Session</b>"
        self.session["intro"] = "Ask @someone.real"
        self.run_session(self.with_item(
            title="<script>x</script>", why="From @someone.real, call +49 555 123 4567",
            reference=[{"src": "ref/t1-1.jpg", "caption": 'cap "<i>" by @someone.real', "reel": REEL}],
            options=[{"key": "A", "label": "A & <u>B</u>", "src": "ours/t1-a.png"}],
            old="<s>old</s>", new="<s>new</s>", choices=['Adopt "A"', "Skip <now>"], default='Adopt "A"'))
        page = self.page()
        for raw in ("someone.real", "555 123", "<script>x", "<b>Session", "<i>", "<u>B", "<s>", "<now>"):
            self.assertNotIn(raw, page)
        for shown in ("&lt;script&gt;x&lt;/script&gt;", "&lt;b&gt;Session&lt;/b&gt;", "Ask @...", "From @..., call ...",
                      "A &amp; &lt;u&gt;B&lt;/u&gt;", 'value="Adopt &quot;A&quot;" checked', 'data-pre="Adopt &quot;A&quot;"'):
            self.assertIn(shown, page)

    def test_a_template_mark_in_text_stays_text(self):
        self.session["title"] = "Week __INTRO__"
        self.run_session(self.with_item(why="__TITLE__ <!--ITEMS--> /*JS*/ __PAGE__"))
        self.assertIn('<p class="why">__TITLE__ &lt;!--ITEMS--&gt; /*JS*/ __PAGE__</p>', self.page())
        self.assertIn("<h1>Week __INTRO__</h1>", self.page())

    def test_nothing_on_the_page_can_load_from_outside(self):
        self.run_session()
        self.assertIn("default-src 'none'", self.page())
        self.assertEqual(re.findall(r'(?:src|href)="(?!data:|https://www\.instagram\.com/(?:reel|p)/)', self.page()), [])

    def test_nothing_is_written_but_the_session_picker(self):
        self.write()
        before = set(self.root.rglob("*"))
        self.run_session()
        self.assertEqual(set(self.root.rglob("*")) - before, {self.here / "picker.html"})
        self.run_session()
        self.assertEqual(set(self.root.rglob("*")) - before, {self.here / "picker.html"})

    def test_the_session_picker_is_readable_like_any_file(self):
        self.run_session()
        self.assertEqual(stat.S_IMODE((self.here / "picker.html").stat().st_mode), 0o644)

    def test_a_link_at_picker_html_is_replaced_and_not_followed(self):
        outside = self.root / "outside.html"
        outside.write_text("mine", encoding="utf-8")
        (self.here / "picker.html").symlink_to(outside)
        self.run_session()
        self.assertEqual(outside.read_text(encoding="utf-8"), "mine")
        self.assertFalse((self.here / "picker.html").is_symlink())

    def test_a_linked_media_folder_counts(self):
        marketing = self.root / "workspaces/marketing"
        cloud = self.root / "cloud"
        (marketing / "media").rename(cloud)
        (marketing / "media").symlink_to(cloud)
        self.folder = marketing / "media/taste" / PAGE
        self.here = self.folder / DAY
        self.run_session()
        self.assertTrue((cloud / "taste" / PAGE / DAY / "picker.html").is_file())

    def test_the_command_takes_a_session_alone(self):
        with mock.patch.object(taste, "build_session", return_value="wrote it") as built, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(taste.main(["--page", PAGE, "--session", "s/session.json"]), 0)
        built.assert_called_once_with(PAGE, "s/session.json", design_only=False)
        for argv in (["--session", "s", "--rubric", "r"], ["--session", "s", "--picks", "p"], ["--rubric", "r"], ["--picks", "p"], []):
            with self.subTest(argv=argv), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as stop:
                taste.main(["--page", PAGE, *argv])
            self.assertEqual(stop.exception.code, 2)

    def test_a_refusal_exits_1_with_its_reason(self):
        self.write()
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code = taste.main(["--page", PAGE, "--session", str(self.folder / "session.json")])
        self.assertEqual(code, 1)
        self.assertIn("refused:", err.getvalue())
        self.assertFalse((self.here / "picker.html").exists())


class SessionCaps(Session):
    def test_eight_items_and_one_overview_pass(self):
        self.session["items"] = [self.entry("o1", "overview")] + [self.entry(f"t{n}") for n in range(1, 9)]
        self.assertIn("9 items", self.run_session())

    def test_more_refuse(self):
        for label, items in (
            ("nine items", [self.entry(f"t{n}") for n in range(1, 10)]),
            ("two overviews", [self.entry("o1", "overview"), self.entry("o2", "overview")]),
            ("ten with an overview", [self.entry("o1", "overview")] + [self.entry(f"t{n}") for n in range(1, 10)]),
        ):
            with self.subTest(label):
                self.session_refused("a session holds at most 8, plus one overview", {**self.session, "items": items})

    def test_three_images_a_side_pass_and_four_do_not(self):
        refs = [{"src": f"ref/t1-{n}.jpg", "reel": REEL} for n in range(1, 5)]
        ours = [{"key": key, "label": f"Ours {key}", "src": f"ours/t1-{key.lower()}.png"} for key in "ABCD"]
        self.run_session(self.with_item(reference=refs[:3], options=ours[:3]))
        self.assertEqual(self.card("t1").count("<img"), 6)
        self.session_refused("4 reference images, and an item shows at most 3", self.with_item(reference=refs))
        self.session_refused("4 options, and an item shows at most 3", self.with_item(options=ours))

    def test_two_to_four_choices(self):
        for choices in (["Adopt A", "Skip"], ["Adopt A", "Adopt B", "Try", "Skip"]):
            with self.subTest(choices=choices):
                self.run_session(self.with_item(choices=choices))
        for choices in (["Adopt A"], ["Adopt A", "Adopt B", "Try", "Skip", "Later"], "Adopt A", None):
            with self.subTest(choices=choices):
                self.session_refused("two to 4 choices", self.with_item(choices=choices))

    def test_three_hundred_characters_pass_and_more_refuse(self):
        def placed(field, text):
            if field in ("title_", "intro"):
                return {**self.session, field.rstrip("_"): text}
            if field == "caption":
                return self.with_item(reference=[{"src": "ref/t1-1.jpg", "reel": REEL, "caption": text}])
            if field == "label":
                return self.with_item(options=[{"key": "A", "label": text, "src": "ours/t1-a.png"}])
            if field == "choice":
                return self.with_item(choices=[text, "Skip"], default="Skip")
            return self.with_item(**{field: text})

        for field in ("title_", "intro", "title", "why", "old", "new", "caption", "label", "choice"):
            with self.subTest(field=field):
                self.run_session(placed(field, "x" * 300))
                self.session_refused("301 characters, and text holds at most 300", placed(field, "x" * 301))

    def test_quality_drops_to_fit_the_limit(self):
        def by_quality(path, seconds, quality, root, image=False, width=taste.WIDTH):
            return "data:image/jpeg;base64," + "A" * (taste.LIMIT if quality < 9 else 1000)

        self.assertIn("quality 9", self.run_session(grab=by_quality))

    def test_over_the_limit_at_the_lowest_quality_refuses(self):
        def huge(path, seconds, quality, root, image=False, width=taste.WIDTH):
            return "data:image/jpeg;base64," + "A" * taste.LIMIT

        with self.assertRaisesRegex(taste.Refused, "over the 15 MB limit: use fewer images"):
            self.run_session(grab=huge)
        self.assertFalse((self.here / "picker.html").exists())


class SessionChildren(Session):
    def flagged(self, code, **kwargs):
        self.reel(code, caption=None, breakdown=None, **kwargs)
        refs = [{"src": "ref/t1-1.jpg", "reel": REEL}, {"src": "ref/t1-2.jpg", "reel": code}]
        return self.with_item(reference=refs)

    def test_a_child_flagged_reference_passes(self):
        self.run_session(self.flagged("DemoCode00N", flag="child on screen"))
        self.assertEqual(self.card("t1").count("<img"), 4)

    def test_a_reference_with_no_flag_line_passes(self):
        self.run_session(self.flagged("NoFlagLine", style="Frames: 1\n"))
        self.assertEqual(self.card("t1").count("<img"), 4)

    def test_a_reference_needs_a_reel_with_a_style_note(self):
        code = "NoStyleNote"
        session = self.flagged(code)
        (self.root / taste.REELS / code / "style.md").unlink()
        self.session_refused("t1's reference 2: NoStyleNote: style.md is missing", session)
        (self.root / taste.REELS / code / "style.md").write_bytes(b"\xff\xfe Flag: none")
        self.session_refused("t1's reference 2: can't read NoStyleNote's style.md", session)
        for reel in (None, "", "../x", "a/b", "NoSuchReel"):
            with self.subTest(reel=reel):
                refs = [{"src": "ref/t1-1.jpg"} | ({"reel": reel} if reel is not None else {})]
                self.session_refused("names no reel (or post )?code|no folder of its own", self.with_item(reference=refs))

    def test_a_linked_reel_folder_refuses(self):
        (self.root / taste.REELS / "LinkedReel").symlink_to(self.root / taste.REELS / REEL)
        self.session_refused("LinkedReel: no folder of its own", self.with_item(
            reference=[{"src": "ref/t1-1.jpg", "reel": "LinkedReel"}]))

    def post_reference(self, code="CzAbCdEfGhI", **kwargs):
        self.post(code, **kwargs)
        return self.with_item(reference=[{"src": "ref/t1-1.jpg", "reel": REEL}, {"src": "ref/t1-2.jpg", "post": code}])

    def test_a_saved_post_with_a_clean_style_note_passes(self):
        self.run_session(self.post_reference())
        self.assertEqual(self.card("t1").count("<img"), 4)

    def test_a_child_flagged_post_passes(self):
        self.run_session(self.post_reference(flag="child on screen"))
        self.assertEqual(self.card("t1").count("<img"), 4)

    def test_a_post_with_no_flag_line_passes(self):
        self.run_session(self.post_reference(style="Frames: 1\n"))
        self.assertEqual(self.card("t1").count("<img"), 4)

    def test_a_post_needs_a_folder_and_a_style_note_of_its_own(self):
        session = self.post_reference()
        (self.root / taste.POSTS / "CzAbCdEfGhI" / "style.md").unlink()
        self.session_refused("t1's reference 2: CzAbCdEfGhI: style.md is missing", session)
        (self.root / taste.POSTS / "LinkedPost").symlink_to(self.root / taste.POSTS / "CzAbCdEfGhI")
        for post, reason in (("LinkedPost", "LinkedPost: no folder of its own in posts/"),
                             ("NoSuchPost", "NoSuchPost: no folder of its own in posts/"),
                             (REEL, f"{REEL}: no folder of its own in posts/"),
                             ("../x", "names no post code"), (None, "names no post code")):
            with self.subTest(post=post):
                self.session_refused(reason, self.with_item(reference=[{"src": "ref/t1-1.jpg", "post": post}]))

    def test_a_reference_names_one_saved_item(self):
        self.post()
        self.session_refused("t1's reference 1 names both a reel and a post", self.with_item(
            reference=[{"src": "ref/t1-1.jpg", "reel": REEL, "post": "CzAbCdEfGhI"}]))
        self.session_refused("t1's reference 1 names no reel or post code", self.with_item(reference=[{"src": "ref/t1-1.jpg"}]))


class SessionRefusals(Session):
    def test_the_session_file_must_sit_in_a_session_folder_of_its_page(self):
        other = self.root / taste.TASTE / "acme" / DAY
        outside = self.root / DAY
        deeper = self.here / "ref"
        for folder in (other, outside, self.folder / "session-x"):
            folder.mkdir(parents=True)
        for file in (self.folder / "session.json", self.folder / "session-x" / "session.json", self.here / "other.json",
                     other / "session.json", outside / "session.json", deeper / "session.json"):
            with self.subTest(file=file):
                file.write_text(json.dumps(self.session), encoding="utf-8")
                self.session_refused(re.escape("must be workspaces/marketing/media/taste/demo/session-<YYYY-MM-DD>[-<word>]/session.json"),
                                     file=file)
        self.session_refused("must be a file directly in session-2026-01-07/", file=self.folder / "session-2026-01-07" / "session.json")

    def test_a_linked_session_folder_in_the_same_page_builds_the_session_it_points_to(self):
        self.write()
        (self.folder / "session-2026-01-08").symlink_to(self.here)
        result = taste.build_session(PAGE, str(self.folder / "session-2026-01-08" / "session.json"), root=self.root,
                                     grab=fake_image, fonts=fake_fonts)
        self.assertIn(f"wrote {self.here / 'picker.html'}", result)
        self.assertIn('data-session="session-2026-01-06"', self.page())

    def test_a_linked_session_folder_or_file_outside_refuses(self):
        outside = self.root / DAY
        outside.mkdir()
        (outside / "session.json").write_text(json.dumps(self.session), encoding="utf-8")
        (self.folder / "session-2026-01-07").symlink_to(outside)
        self.session_refused("must be", file=self.folder / "session-2026-01-07" / "session.json")
        linked = self.folder / "session-2026-01-08"
        linked.mkdir()
        (linked / "session.json").symlink_to(outside / "session.json")
        self.session_refused("must be", file=linked / "session.json")

    def test_the_session_must_be_for_its_page(self):
        self.session_refused("the session is for page 'acme', not demo", {**self.session, "page": "acme"})

    def test_bad_page_names_refuse(self):
        for page in ("../outside", "a/b", "UPPER"):
            with self.subTest(page=page):
                self.session_refused("page name", page=page)

    def test_an_image_outside_its_folder_refuses(self):
        for src in ("ref/../ours/t1-a.png", "../t1-1.jpg", "/etc/hosts", "ref", "ref/", "ours/t1-a.png", "ref/.hidden",
                    "ref/a/b.jpg", "ref\\t1-1.jpg", 5, None):
            with self.subTest(src=src):
                self.session_refused("src must be ref/<file name>", self.with_item(reference=[{"src": src, "reel": REEL}]))
        self.session_refused("src must be ours/<file name>", self.with_item(
            options=[{"key": "A", "label": "x", "src": "ref/t1-1.jpg"}]))

    def test_a_linked_or_missing_image_refuses(self):
        outside = self.root / "outside.jpg"
        outside.write_bytes(b"x")
        (self.here / "ref" / "linked.jpg").symlink_to(outside)
        for name in ("linked.jpg", "missing.jpg"):
            with self.subTest(name=name):
                self.session_refused(f"ref/{name} is missing or a link",
                                     self.with_item(reference=[{"src": f"ref/{name}", "reel": REEL}]))

    def test_a_linked_image_folder_refuses(self):
        cloud = self.root / "elsewhere"
        (self.here / "ours").rename(cloud)
        (self.here / "ours").symlink_to(cloud)
        self.session_refused("ours/ must be a folder, not a link")

    def test_bad_items_refuse(self):
        for change, reason in (
            ({"id": "T 1"}, "item id"), ({"id": None}, "item id"), ({"part": "other"}, "part must be"),
            ({"title": ""}, "title is empty"), ({"title": None}, "title must be text"), ({"why": 5}, "why must be text"),
            ({"old": None}, "old must be text"),
            ({"links": "https://www.instagram.com/reel/DemoCode00M/"}, "links must be a list"),
            ({"links": ["https://evil.example/reel/DemoCode00M/"]}, "isn't an Instagram"),
            ({"links": ["javascript:alert(1)"]}, "isn't an Instagram"),
            ({"links": ["http://www.instagram.com/reel/DemoCode00M/"]}, "isn't an Instagram"),
            ({"links": ['https://www.instagram.com/reel/DemoCode00M/" onclick="x']}, "isn't an Instagram"),
            ({"links": ["https://www.instagram.com/stories/someone/123/"]}, "isn't an Instagram"),
            ({"links": [5]}, "isn't an Instagram"),
            ({"reference": {"src": "ref/t1-1.jpg"}}, "reference images must be a list of objects"),
            ({"options": ["ours/t1-a.png"]}, "options must be a list of objects"),
            ({"options": [{"key": "A b", "label": "x", "src": "ours/t1-a.png"}]}, "key is letters or digits"),
            ({"options": [{"label": "x", "src": "ours/t1-a.png"}]}, "key is letters or digits"),
            ({"options": [{"key": "A", "src": "ours/t1-a.png"}]}, "label must be text"),
            ({"options": [{"key": "A", "label": "x", "src": "ours/t1-a.png"}, {"key": "A", "label": "y", "src": "ours/t1-b.png"}]},
             "two options share a key"),
            ({"choices": ["Adopt A", " Adopt  A "]}, "two choices are the same"),
            ({"choices": ["Adopt A", ""]}, "choice is empty"),
            ({"default": None}, "default must be text"),
            ({"default": "Later"}, "its default must be one of its choices"),
        ):
            with self.subTest(change=change):
                self.session_refused(reason, self.with_item(**change))

    def test_bad_sessions_refuse(self):
        for session, reason in (
            ([], "one JSON object"), ({**self.session, "items": []}, "lists no items"),
            ({**self.session, "items": None}, "lists no items"), ({**self.session, "items": ["t1"]}, "one JSON object"),
            ({**self.session, "items": [self.entry(), self.entry()]}, "two items share an id"),
            ({**self.session, "title": ""}, "the session's title is empty"),
            ({**self.session, "intro": None}, "the session's intro must be text"),
        ):
            with self.subTest(reason=reason):
                self.session_refused(reason, session)

    def test_deep_nesting_refuses_and_writes_nothing(self):
        self.write()
        (self.here / "session.json").write_text("[" * 1_000_000 + "]" * 1_000_000, encoding="utf-8")
        before = set(self.root.rglob("*"))
        with self.assertRaisesRegex(taste.Refused, "session.json"):
            taste.build_session(PAGE, str(self.here / "session.json"), root=self.root, grab=fake_image, fonts=fake_fonts)
        self.assertEqual(set(self.root.rglob("*")), before)

    def test_ffmpeg_failing_refuses_and_names_the_item(self):
        def broken(path, seconds, quality, root, image=False, width=taste.WIDTH):
            raise subprocess.CalledProcessError(1, "ffmpeg")

        with self.assertRaisesRegex(taste.Refused, "t1: ffmpeg couldn't read an image"):
            self.run_session(grab=broken)
        self.assertFalse((self.here / "picker.html").exists())

    def test_missing_fonts_refuse(self):
        self.write()
        with self.assertRaisesRegex(taste.Refused, "npm install"):
            taste.build_session(PAGE, str(self.here / "session.json"), root=self.root, grab=fake_image)


if __name__ == "__main__":
    unittest.main()
