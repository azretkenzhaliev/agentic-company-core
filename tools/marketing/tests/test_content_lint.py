"""Tests for tools/marketing/content_lint.py: one content page in, findings out."""

import hashlib
import io
import json
import re
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "publish"))

import content_lint  # noqa: E402
import post  # noqa: E402
from content_lint import lint, main  # noqa: E402

FRONT = {
    "title": '"Mon reel: a take"',
    "owner": "content-producer",
    "status": "draft",
    "updated": "2026-01-02",
    "related": "[]",
    "brand": "founder/demo",
    "week": "2026-W05",
    "format": "reel",
    "pillar": "News, my take",
    "funnel_stage": "awareness",
    "filmed_by": "founder",
    "ai_generated": "false",
    "ai_reason": '"HTML/CSS renders and my own footage only"',
    "raw_material": "workspaces/marketing/inbox/2026-W05/note-1.m4a",
    "piece_status": "draft",
    "languages": "[de, en]",
}
SECTIONS = {
    "Caption": "```text\nDas neue Modell ist da.\n\nA new model is out.\n```",
    "Hashtags": "#ai #tech",
    "Assets": "| File | Provenance | AI | Notes or prompt |\n|---|---|---|---|\n"
              "| workspaces/marketing/media/a.png | own-render | no | |",
    "Sources": "- Model released — https://example.com/news (2026-01-28)",
}
RECORD = '---\ntitle: "Old log"\nowner: content-producer\nstatus: archived\nupdated: 2026-01-06\nrelated: []\n---\n\n# Old\n\nA record, not a piece.\n'


def piece(front=None, sections=None, drop=()):
    fields = {**FRONT, **(front or {})}
    parts = {**SECTIONS, **(sections or {})}
    head = "".join(f"{k}: {v}\n" for k, v in fields.items() if k not in drop)
    body = "".join(f"## {name}\n\n{text}\n\n" for name, text in parts.items() if text is not None)
    return f"---\n{head}---\n\n# Title\n\n{body}"


class ContentLintCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def findings(self, text, level="error"):
        path = self.root / "page.md"
        path.write_text(text, encoding="utf-8")
        return [f.message for f in lint(path, repo_root=self.root) if f.level == level]

    def assertClean(self, text):
        self.assertEqual(self.findings(text), [])

    def assertError(self, text, fragment):
        errors = self.findings(text)
        self.assertTrue(any(fragment in e for e in errors), errors)


class Basics(ContentLintCase):
    def test_a_good_piece_is_clean(self):
        self.assertClean(piece())
        self.assertEqual(self.findings(piece(), "warning"), [])

    def test_required_fields(self):
        for key in ["brand", "week", "format", "pillar", "ai_generated", "ai_reason", "raw_material", "piece_status", "languages"]:
            with self.subTest(key=key):
                self.assertError(piece(drop=(key,)), key)

    def test_owner_is_the_producer(self):
        self.assertError(piece({"owner": "cmo"}), "owner")

    def test_a_short_is_a_format(self):
        self.assertClean(piece({"format": "short"}))

    def test_enumerations(self):
        self.assertError(piece({"format": "tiktok"}), "format")
        self.assertError(piece({"piece_status": "approved"}), "piece_status")
        self.assertError(piece({"ai_generated": "maybe"}), "ai_generated")
        self.assertError(piece({"week": "2026-45"}), "week")


class Archived(ContentLintCase):
    def setUp(self):
        super().setUp()
        (self.root / "good.md").write_text(piece(), encoding="utf-8")
        self.old = self.root / "sub/old.md"
        self.old.parent.mkdir()
        self.old.write_text(RECORD, encoding="utf-8")  # no piece fields, so a lint would say so

    def run_main(self, path):
        out = io.StringIO()
        with redirect_stdout(out):
            code = main([str(path)])
        return code, out.getvalue()

    def test_a_folder_run_skips_an_archived_page_and_names_it(self):
        code, out = self.run_main(self.root)
        self.assertEqual(code, 0, out)
        self.assertIn(f"{self.old}: skipped: status archived", out)
        self.assertIn("1 pages, 0 errors, 0 warnings, 1 archived skipped", out)

    def test_an_archived_page_named_directly_is_still_checked(self):
        code, out = self.run_main(self.old)
        self.assertEqual(code, 1, out)
        self.assertIn("0 archived skipped", out)

    def test_only_the_front_matter_status_counts(self):
        (self.root / "good.md").write_text(piece(sections={"Hook": "status: archived"}, drop=("brand",)), encoding="utf-8")
        code, out = self.run_main(self.root)
        self.assertEqual(code, 1, out)

    def test_a_live_piece_marked_archived_fails_on_a_folder_run_and_on_its_own(self):
        for status in ("draft", "in-review", "ready-for-board", "", "something-else"):
            with self.subTest(piece_status=status):
                self.old.write_text(piece({"status": "archived", "piece_status": status}), encoding="utf-8")
                for path in (self.root, self.old):
                    code, out = self.run_main(path)
                    self.assertEqual(code, 1, out)
                    self.assertIn("a live piece can't be archived", out)
                    self.assertIn("0 archived skipped", out)

    def test_a_piece_with_piece_status_deleted_is_still_a_piece(self):
        self.old.write_text(piece({"status": "archived"}, drop=("piece_status",)), encoding="utf-8")
        for path in (self.root, self.old):
            code, out = self.run_main(path)
            self.assertEqual(code, 1, out)
            self.assertIn("a live piece can't be archived", out)
            self.assertIn("0 archived skipped", out)

    def test_a_post_section_alone_makes_a_page_a_piece(self):
        self.old.write_text(RECORD + "\n## Post\n\n- Type: reel\n", encoding="utf-8")
        for path in (self.root, self.old):
            code, out = self.run_main(path)
            self.assertEqual(code, 1, out)
            self.assertIn("a live piece can't be archived", out)
            self.assertIn("0 archived skipped", out)


class Shorts(ContentLintCase):
    def caption(self, text):
        return {"Caption": f"```text\n{text}\n```", "Hashtags": ""}

    def test_a_shorts_caption_is_bounded_in_bytes(self):
        self.assertClean(piece({"format": "short"}, sections=self.caption("a" * 5000)))
        self.assertClean(piece({"format": "short"}, sections=self.caption("ü" * 2500)))
        self.assertError(piece({"format": "short"}, sections=self.caption("a" * 5001)), "5000 bytes")
        self.assertError(piece({"format": "short"}, sections=self.caption("ü" * 2501)), "5000 bytes")

    def test_instagrams_limit_binds_every_other_format_only(self):
        self.assertClean(piece({"format": "short"}, sections=self.caption("a" * 3000)))
        self.assertError(piece({"format": "reel"}, sections=self.caption("a" * 3000)), "2,200")

    def test_angle_brackets_are_barred_in_a_shorts_caption_only(self):
        for text in ("a < b", "a > b"):
            self.assertError(piece({"format": "short"}, sections=self.caption(text)), "no < or >")
            self.assertClean(piece({"format": "reel"}, sections=self.caption(text)))

    def test_a_shorts_title_has_youtubes_bounds(self):
        bad = {"a < b": "no < or >", "a > b": "no < or >", "a\x07b": "control characters", "a" * 101: "100 characters"}
        self.assertClean(piece({"format": "short"}, sections={"Post": "- Type: short\n- Title: " + "ü" * 100}))
        for title, fragment in bad.items():
            with self.subTest(title=title):
                self.assertError(piece({"format": "short"}, sections={"Post": f"- Type: short\n- Title: {title}"}), fragment)

    def test_a_title_belongs_on_a_short_once(self):
        two = "- Type: short\n- Title: One\n- Title: Two"
        self.assertError(piece({"format": "short"}, sections={"Post": two}), "at most one")
        self.assertError(piece({"format": "short"}, sections={"Post": "- Type: short"}), "a short needs")
        self.assertError(piece({"format": "reel"}, sections={"Post": "- Type: reel\n- Title: One"}), "only a short")
        self.assertClean(piece({"format": "reel"}, sections={"Post": "- Type: reel"}))

    def test_the_bounds_are_the_ones_post_py_refuses(self):
        self.assertEqual((content_lint.TITLE_MAX, content_lint.DESCRIPTION_MAX), (post.TITLE_MAX, post.DESCRIPTION_MAX))


class CaptionAndHashtags(ContentLintCase):
    def test_caption_counts_characters_not_bytes(self):
        ok = "```text\n" + "ü" * 2200 + "\n```"
        too_long = "```text\n" + "ü" * 2201 + "\n```"
        self.assertClean(piece(sections={"Caption": ok, "Hashtags": ""}))
        self.assertError(piece(sections={"Caption": too_long, "Hashtags": ""}), "2,200")

    def test_caption_is_required_except_for_stories(self):
        self.assertError(piece(sections={"Caption": None}), "Caption")
        self.assertClean(piece({"format": "story"}, sections={"Caption": None, "Hashtags": None}))

    def test_at_most_five_hashtags_without_double_counting(self):
        caption = "```text\nText #ai #tech #tools\n```"
        self.assertClean(piece(sections={"Caption": caption, "Hashtags": "#ai #tech #tools #news #events"}))
        self.assertError(piece(sections={"Caption": caption, "Hashtags": "#ai #news #events #code"}), "hashtags")


class FounderVoice(ContentLintCase):
    def test_placeholder_must_say_so(self):
        self.assertError(piece({"raw_material": "placeholder"}), "placeholder")
        self.assertClean(piece({"raw_material": "placeholder"}, sections={"Hook": "PLACEHOLDER take: to be replaced"}))

    def test_raw_material_is_the_founders_inbox_or_placeholder(self):
        self.assertError(piece({"raw_material": "knowledge/marketing/founder/demo/notes.md"}), "inbox")
        self.assertError(piece({"raw_material": "workspaces/marketing/media/a/take.txt"}), "inbox")

    def test_placeholder_never_goes_to_the_board(self):
        text = piece({"raw_material": "placeholder", "piece_status": "ready-for-board"}, sections={"Hook": "placeholder"})
        self.assertError(text, "placeholder")

    def test_a_drafted_take_may_go_to_the_board_with_or_without_sources(self):
        self.assertClean(piece({"raw_material": "drafted", "piece_status": "ready-for-board"}))
        self.assertClean(piece({"raw_material": "drafted"}, sections={"Sources": None}))

    def test_a_drafted_take_is_only_for_the_founders_pages(self):
        self.assertError(piece({"raw_material": "drafted", "brand": "acme"}), "only for the founder's pages")
        self.assertClean(piece({"raw_material": "drafted", "brand": "founder/acme"}))


class FactsOnly(ContentLintCase):
    def test_facts_only_needs_no_take_and_on_the_founders_pages_no_sources(self):
        self.assertClean(piece({"raw_material": "facts-only", "piece_status": "ready-for-board"}))
        for brand in ["founder/demo", "founder/acme"]:
            with self.subTest(brand=brand):
                self.assertClean(piece({"raw_material": "facts-only", "brand": brand}, sections={"Sources": None}))

    def test_on_a_product_brand_facts_only_needs_sources(self):
        self.assertError(piece({"raw_material": "facts-only", "brand": "acme"}, sections={"Sources": None}), "## Sources")
        self.assertClean(piece({"raw_material": "facts-only", "brand": "acme"}))


class Outside(ContentLintCase):
    """Outside footage: from sources/, with a manifest entry, listed when compiled in."""

    def setUp(self):
        super().setUp()
        self.folder = self.root / "workspaces/marketing/sources/founder/demo/2026-W05/a-talk"
        self.folder.mkdir(parents=True)
        (self.folder / "video.mp4").write_bytes(b"clip")
        self.sha = hashlib.sha256(b"clip").hexdigest()
        (self.folder / "MANIFEST.json").write_text(json.dumps({"files": [{"file": "video.mp4", "sha256": self.sha}]}))
        self.clip = "workspaces/marketing/sources/founder/demo/2026-W05/a-talk/video.mp4"

    def rows(self, *rows):
        return "| File | Provenance | AI | Notes |\n|---|---|---|---|\n" + "\n".join(f"| {f} | {p} | no | |" for f, p in rows)

    def test_an_outside_clip_with_its_manifest_entry_is_clean(self):
        self.assertClean(piece(sections={"Assets": self.rows((self.clip, "outside"))}))

    def test_an_outside_clip_needs_sources_and_a_matching_manifest_entry(self):
        self.assertError(piece(sections={"Assets": self.rows(("workspaces/marketing/media/a.mp4", "outside"))}), "sources/")
        (self.folder / "video.mp4").write_bytes(b"changed")
        self.assertError(piece(sections={"Assets": self.rows((self.clip, "outside"))}), "MANIFEST.json")

    def test_outside_paths_cannot_leave_sources(self):
        media = self.root / "workspaces/marketing/media/x"
        media.mkdir(parents=True)
        (media / "clip.mp4").write_bytes(b"clip")
        (media / "MANIFEST.json").write_text(json.dumps({"files": [{"file": "clip.mp4", "sha256": self.sha}]}))
        sneaky = "workspaces/marketing/sources/../media/x/clip.mp4"
        self.assertError(piece(sections={"Assets": self.rows((sneaky, "outside"))}), "sources/")
        (self.folder / "linked.mp4").symlink_to(media / "clip.mp4")
        linked = self.clip.replace("video.mp4", "linked.mp4")
        self.assertError(piece(sections={"Assets": self.rows((linked, "outside"))}), "outside")

    def test_a_renamed_file_doesnt_match_its_entry(self):
        (self.folder / "video.mp4").rename(self.folder / "other.mp4")
        renamed = self.clip.replace("video.mp4", "other.mp4")
        self.assertError(piece(sections={"Assets": self.rows((renamed, "outside"))}), "MANIFEST.json")

    def test_a_generator_sidecar_is_not_a_compile_record(self):
        clip = self.root / "workspaces/marketing/media/g/video-01.mp4"
        clip.parent.mkdir(parents=True)
        clip.write_bytes(b"ai")
        Path(f"{clip}.json").write_text(json.dumps({"prompt": "calm field", "ai_generated": True}))
        rows = "| File | Provenance | AI | Notes |\n|---|---|---|---|\n| workspaces/marketing/media/g/video-01.mp4 | ai-generated | yes | calm field |"
        self.assertClean(piece({"ai_generated": "true", "ai_reason": "Gemini b-roll"}, sections={"Assets": rows}))
        warnings = self.findings(piece(sections={"Assets": rows.replace("| ai-generated |", "| own-render |")}), "warning")
        self.assertTrue(any("AI inputs" in w for w in warnings), warnings)  # the sidecar's flag still counts

    def test_a_damaged_record_beside_a_video_is_an_error(self):
        clip = self.root / "workspaces/marketing/media/d/reel.mp4"
        clip.parent.mkdir(parents=True)
        clip.write_bytes(b"reel")
        rows = "| File | Provenance | AI | Notes |\n|---|---|---|---|\n| workspaces/marketing/media/d/reel.mp4 | own-render | no | |"
        for broken in ["{not json", "[]", "{}", '{"inputs": "x"}']:
            with self.subTest(broken=broken):
                Path(f"{clip}.json").write_text(broken)
                self.assertError(piece(sections={"Assets": rows}), "reel.mp4.json")

    def test_a_compiled_reel_lists_its_outside_clips_and_its_ai_flag(self):
        reel = self.root / "workspaces/marketing/media/r/reel.mp4"
        reel.parent.mkdir(parents=True)
        reel.write_bytes(b"reel")
        record = {"ai_generated": True, "inputs": [
            {"file": self.clip, "provenance": "outside", "sha256": self.sha,
             "manifest": "workspaces/marketing/sources/founder/demo/2026-W05/a-talk/MANIFEST.json"}]}
        Path(f"{reel}.json").write_text(json.dumps(record))
        only_reel = self.rows(("workspaces/marketing/media/r/reel.mp4", "own-render"))
        self.assertError(piece(sections={"Assets": only_reel}), "list it in ## Assets")
        both = self.rows(("workspaces/marketing/media/r/reel.mp4", "own-render"), (self.clip, "outside"))
        self.assertEqual(self.findings(piece(sections={"Assets": both})), [])
        self.assertIn("ai_generated", " ".join(self.findings(piece(sections={"Assets": both}), "warning")))


class Assets(ContentLintCase):
    def test_provenance_must_be_ours(self):
        for bad in ["screenshot", "repost", "third-party"]:
            with self.subTest(bad=bad):
                rows = SECTIONS["Assets"].replace("own-render", bad)
                self.assertError(piece(sections={"Assets": rows}), "provenance")

    def test_ai_asset_without_ai_flag_warns(self):
        rows = SECTIONS["Assets"].replace("own-render | no", "ai-generated | yes")
        warnings = " ".join(self.findings(piece(sections={"Assets": rows}), "warning"))
        self.assertIn("ai_generated", warnings)
        self.assertClean(piece({"ai_generated": "true", "ai_reason": "Gemini background"}, sections={"Assets": rows}))

    def test_html_fonts_must_be_vetted(self):
        media = self.root / "slide.html"
        rows = "| File | Provenance | AI | Notes |\n|---|---|---|---|\n| slide.html | own-render | no | |"
        media.write_text("<style>h1{font-family:'Golos Text', sans-serif} p{font-family: Montserrat}</style>")
        self.assertClean(piece(sections={"Assets": rows}))
        media.write_text("<style>h1{font-family: 'Unbounded', sans-serif}</style>")
        self.assertError(piece(sections={"Assets": rows}), "Unbounded")
        for css, ok in [("h1{font: 700 30px 'Golos Text', sans-serif}", True),
                        ("h1{font: 800 96px/1.08 Montserrat, sans-serif}", True),
                        ("h1{font: 700 30px serif}", False),
                        ("h1{font-family: system-ui}", False),
                        ("h1{font-family: sans-serif, 'Golos Text'}", False),
                        ("h1{font: 700 30px 'Unbounded', 'Golos Text'}", False),
                        (".ar{font-family:'Scheherazade New', 'Golos Text', sans-serif}", True),
                        ("h1{font-family:'Golos Text', 'Scheherazade New', sans-serif}", True),
                        (".ar{font-family:'Scheherazade New', sans-serif}", False),
                        (".ar{font-family:'Scheherazade New'}", False),
                        (".ar{font-family:'Amiri', 'Golos Text'}", False)]:
            with self.subTest(css=css):
                media.write_text(f"<style>{css}</style>")
                errors = self.findings(piece(sections={"Assets": rows}))
                self.assertEqual(errors == [], ok, errors)


class News(ContentLintCase):
    def test_on_a_news_brand_a_source_without_a_link_or_a_date_is_a_warning(self):
        (self.root / "company.json").write_text(json.dumps({"integrations": {"marketing": {"brands": {
            "founder/demo": {"news": True}, "founder/acme": {}}}}}))
        for line, fragment in [("- Model released — example.com (2026-01-28)", "https://"),
                               ("- Model released — https://example.com/news", "date")]:
            with self.subTest(line=line):
                text = piece(sections={"Sources": line})
                self.assertEqual(self.findings(text), [])
                self.assertTrue(any(fragment in w for w in self.findings(text, "warning")))
                other = self.findings(piece({"brand": "founder/acme"}, sections={"Sources": line}), "warning")
                self.assertFalse(any(fragment in w for w in other), other)


class TestPieces(ContentLintCase):
    def test_test_piece_is_not_for_posting(self):
        self.assertError(piece({"test": "true"}), "not for posting")
        self.assertClean(piece({"test": "true"}, {"Hook": "TEST, not for posting"}))


class Claims(ContentLintCase):
    def warnings(self, caption):
        return " ".join(self.findings(piece(sections={"Caption": f"```text\n{caption}\n```", "Sources": None}), "warning"))

    def test_superlatives_without_a_source_warn(self):
        self.assertIn("source", self.warnings("The best AI tool, with a guarantee"))

    def test_the_companys_own_claim_words_count_too(self):
        self.assertNotIn("source", self.warnings("Das beste Werkzeug"))
        (self.root / "company.json").write_text(json.dumps({"integrations": {"marketing": {"lint": {"claims": [r"\bbeste"]}}}}))
        self.assertIn("source", self.warnings("Das beste Werkzeug"))


class AiTells(ContentLintCase):
    """Language-independent AI tells in the caption: warnings with a score, never errors."""

    def tells(self, caption_text):
        page = piece(sections={"Caption": f"```text\n{caption_text}\n```", "Hashtags": ""})
        self.assertClean(page)  # never an error
        return [w for w in self.findings(page, "warning") if "AI tells" in w]

    def assertTell(self, caption_text, fragment):
        found = self.tells(caption_text)
        self.assertEqual(len(found), 1, found)
        self.assertIn(fragment, found[0])
        self.assertRegex(found[0], r"score \d+/100")

    def assertNoTell(self, caption_text):
        self.assertEqual(self.tells(caption_text), [])

    def test_ordinary_captions_are_clean(self):
        self.assertNoTell("Das neue Modell ist da 🙂👍🏻\n\n—\n\nA new model is out.\n\nFollow for more.\n\n#AI #News")
        self.assertNoTell("Source: Example Co, 2026-01-26 — https://example.com")

    def test_invisible_characters(self):
        self.assertTell("A new\u200b model is out.", "invisible")
        self.assertTell("A new model\ufeff is out.", "invisible")
        self.assertTell("A new\u00ad model.", "invisible")
        self.assertNoTell("The team 👨‍💻 shipped.")  # a joiner inside an emoji is part of the emoji

    def test_markdown_marks(self):
        self.assertTell("**Note:** a model is out.", "Markdown")
        self.assertTell("# In short\nA model is out.", "Markdown")  # a '## ' line already ends the Caption section
        self.assertTell("Read [here](https://example.com).", "Markdown")
        self.assertNoTell("#AI #tech")

    def test_em_dash_density_counts_only_in_latin_script(self):
        english = "This is big — really big — and it is new — again."
        self.assertTell(english, "em dash")
        self.assertNoTell("Αυτό είναι — πολύ μεγάλο — και νέο — πάλι.")
        self.assertNoTell("A new model is out — and it is fast. " + "More words here to make it longer. " * 3)

    def test_emoji_density(self):
        self.assertTell("🔥🔥🔥 New 🚀🚀 video", "emoji")
        self.assertTell("✅ one\n✅ two\n✅ three", "emoji")
        self.assertNoTell("A new AI model is out 🙂👍🏻 and it is faster than the one we had before.")

    def test_hashtag_wall_before_the_last_line(self):
        self.assertTell("#ai #tech #tools\nA model is out.", "hashtag")
        self.assertNoTell("A model is out.\n\n#ai #tech #tools")

    def test_engagement_bait(self):
        for bait in ["Like if you agree", "Tag a friend who needs this", 'Comment "YES" below']:
            with self.subTest(bait=bait):
                self.assertTell(bait, "engagement bait")
        for cta in ["Save this for later.", "Follow for more.", "Send it to someone who needs it.", "What do you think? Comment."]:
            with self.subTest(cta=cta):
                self.assertNoTell(cta)

    def test_the_companys_own_bait_counts_too(self):
        self.assertNoTell("Markiere einen Freund")
        (self.root / "company.json").write_text(json.dumps({"integrations": {"marketing": {"lint": {
            "bait": [r"\bmarkiere\w*\s+(?:einen\s+)?freund"]}}}}))
        self.assertTell("Markiere einen Freund", "engagement bait")

    def test_no_false_alarms_on_ordinary_prose(self):
        # Handles and flags.
        for text in ["@user__1 and @user__2 disagree.", "🇩🇪🇩🇪🇩🇪 Hello",
                     "Source: Example Research, 2026-01-26 — https://example.com"]:
            with self.subTest(text=text):
                self.assertNoTell(text)

    def test_joined_emoji_survive(self):
        for emoji in ["👨‍💻", "🐈‍⬛", "🙂‍↔️"]:
            with self.subTest(emoji=emoji):
                self.assertNoTell(f"The team {emoji} shipped.")
                path = self.root / "page.md"
                path.write_text(piece(sections={"Caption": f"```text\n**Result** {emoji}\n```"}), encoding="utf-8")
                out = io.StringIO()
                with redirect_stdout(out):
                    main(["--clean", str(path)])
                self.assertIn(f"\nResult {emoji}\n", out.getvalue())

    def test_score_adds_up_and_caps_at_100(self):
        one = self.tells("A new\u200b model.")[0]
        many = self.tells("**Note**\u200b 🔥🔥🔥🔥🔥 This is big — really big — new — again. Like if you agree\n#a #b #c\nEnd")[0]
        score = lambda w: int(re.search(r"score (\d+)/100", w).group(1))  # noqa: E731
        self.assertLess(score(one), score(many))
        self.assertLessEqual(score(many), 100)

    def test_clean_prints_the_score_beside_the_cleaned_caption(self):
        path = self.root / "page.md"
        path.write_text(piece(sections={"Caption": "```text\n**Note:**\u200b a model is out.\n```"}), encoding="utf-8")
        out = io.StringIO()
        with redirect_stdout(out):
            main(["--clean", str(path)])
        text = out.getvalue()
        self.assertRegex(text, r"score \d+/100")
        self.assertIn("\nNote: a model is out.\n", text)
        self.assertNotIn("​", text)


if __name__ == "__main__":
    unittest.main()
