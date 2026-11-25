"""Tests for scripts/language_check.py. No network: Gemini is a fake."""

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from language_check import extract_copy, main, parse_flags  # noqa: E402
from second_opinion import Reply  # noqa: E402

PAGE = """---
title: "Mon reel: x"
owner: content-producer
status: draft
updated: 2026-01-02
related: []
---

# Mon reel

## Raw material

Not post copy: the founder's voice note transcript stays here.

## Hook

Ein neues Modell für alle.

## Script

1. (0–2 s) Was können wir heute?

## Caption

```text
Das neue Modell ist verfügbar.

A new model is out.
```

## Assets

| File | Provenance | AI | Notes |
|---|---|---|---|
| slide.html | own-render | no | |

## Sources

- https://example.com (2026-01-28)
"""
POST = """
## Post

- Type: short
- Title: Wofür ein neues Modell?
- Publish at: 2026-01-13T18:00+00:00

| # | File | SHA-256 |
|---|---|---|
| 1 | short-take-1.mp4 | 0123456789abcdef |
"""


SETTINGS = {"second_language": "de", "languages": {
    "en": {"name": "English"}, "de": {"name": "German", "letters": "äöüß", "words": ["nicht"]}}}


class LanguageCheck(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.page = self.root / "page.md"
        self.page.write_text(PAGE, encoding="utf-8")
        (self.root / "slide.html").write_text("<style>h1{color:red}</style><h1>Drei Gründe</h1><p>Three reasons</p>",
                                              encoding="utf-8")
        self.settings(SETTINGS)

    def settings(self, marketing):
        (self.root / "company.json").write_text(json.dumps({"integrations": {"marketing": marketing}}), encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_extracts_only_post_copy(self):
        copy = extract_copy(self.page, self.root)
        for text in ["Ein neues Modell für alle.", "Was können wir heute?", "Das neue Modell ist verfügbar.", "Drei Gründe"]:
            self.assertIn(text, copy)
        self.assertNotIn("voice note transcript", copy)
        self.assertNotIn("example.com", copy)
        self.assertNotIn("color:red", copy)

    def test_a_shorts_title_is_post_copy_and_the_rest_of_post_is_not(self):
        self.page.write_text(PAGE + POST, encoding="utf-8")
        copy = extract_copy(self.page, self.root)
        self.assertIn("## Title\nWofür ein neues Modell?", copy)
        for other in ("Publish at", "2026-01-13", "short-take-1.mp4", "0123456789abcdef", "Type"):
            self.assertNotIn(other, copy)

    def test_a_page_with_no_title_has_no_title_section(self):
        self.assertNotIn("## Title", extract_copy(self.page, self.root))

    def test_parse_flags_reads_fenced_json(self):
        flags = parse_flags('```json\n{"flags": [{"where": "Caption", "text": "a", "problem": "b", "suggestion": "c", "severity": "error"}]}\n```')
        self.assertEqual(flags[0]["where"], "Caption")
        self.assertEqual(parse_flags('{"flags": []}'), [])

    def test_unreadable_answer_is_one_flag_not_a_crash(self):
        self.assertEqual(parse_flags("sorry")[0]["severity"], "unreadable")

    def run_main(self, page, send):
        out = io.StringIO()
        with redirect_stdout(out), mock.patch("language_check.choose_gemini", return_value="a-gemini-model"):
            code = main([str(page)], send=send, models=lambda key: ["a-gemini-model"], token=lambda: "k", repo_root=self.root)
        return code, out.getvalue()

    def test_sends_copy_and_prints_flags_with_the_model(self):
        sent = {}

        def send(packet, instruction, model, key):
            sent.update(packet=packet, instruction=instruction, model=model)
            return Reply('{"flags": [{"where": "Hook", "text": "für", "problem": "ok?", "suggestion": "-", "severity": "style"}]}',
                         1, 1, 0, False)

        code, out = self.run_main(self.page, send)
        self.assertEqual(code, 0)
        self.assertEqual(sent["model"], "a-gemini-model")
        self.assertIn("Das neue Modell ist verfügbar.", sent["packet"])
        self.assertIn("You check the German in one", sent["instruction"])
        self.assertNotIn("LANGUAGE", sent["instruction"])
        self.assertIn("a-gemini-model", out)
        self.assertIn("| Hook | für |", out)

    def test_a_title_that_is_the_pages_only_second_language_is_sent(self):
        sent = {}

        def send(packet, instruction, model, key):
            sent.update(packet=packet, instruction=instruction)
            return Reply('{"flags": []}', 1, 1, 0, False)

        page = self.root / "short.md"
        page.write_text("## Caption\n\n```text\nA model is out.\n```\n" + POST, encoding="utf-8")
        code, _ = self.run_main(page, send)
        self.assertEqual(code, 0)
        self.assertIn("Wofür ein neues Modell?", sent["packet"])
        self.assertNotIn("Instagram", sent["instruction"])

    def test_no_second_language_means_nothing_is_sent(self):
        page = self.root / "en.md"
        page.write_text(PAGE.replace("Ein neues Modell für alle.", "A model is out.").replace("Was können wir heute?", "What now?")
                        .replace("Das neue Modell ist verfügbar.", "News."), encoding="utf-8")
        (self.root / "slide.html").write_text("<h1>Three reasons</h1>")
        code, out = self.run_main(page, lambda *a: self.fail("must not send"))
        self.assertEqual(code, 0)
        self.assertIn("no German text", out)

    def test_a_word_marks_the_language_too(self):
        page = self.root / "word.md"
        page.write_text("## Hook\n\nDas geht nicht.\n", encoding="utf-8")
        sent = []
        self.run_main(page, lambda *a: sent.append(a) or Reply('{"flags": []}', 1, 1, 0, False))
        self.assertEqual(len(sent), 1)

    def test_true_in_the_settings_is_the_default(self):
        self.settings({**SETTINGS, "language_check": True})
        sent = []
        self.run_main(self.page, lambda *a: sent.append(a) or Reply('{"flags": []}', 1, 1, 0, False))
        self.assertEqual(len(sent), 1)

    def test_nothing_is_sent_until_the_language_is_set_or_when_the_board_turned_it_off(self):
        for settings in [{}, {**SETTINGS, "language_check": False}, {**SETTINGS, "language_check": "yes"},
                         {**SETTINGS, "language_check": None}, {**SETTINGS, "second_language": ""}, {**SETTINGS, "languages": {"de": {"name": "German"}}},
                         {**SETTINGS, "languages": {}}]:
            self.settings(settings)
            with self.subTest(settings=settings):
                code, out = self.run_main(self.page, lambda *a: self.fail("must not send"))
                self.assertEqual(code, 0)
                self.assertIn("off; nothing sent", out)

    def test_a_broken_company_json_sends_nothing(self):
        (self.root / "company.json").write_text("{not json", encoding="utf-8")
        with self.assertRaises(ValueError):
            self.run_main(self.page, lambda *a: self.fail("must not send"))


if __name__ == "__main__":
    unittest.main()
