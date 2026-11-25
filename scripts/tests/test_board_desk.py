"""Tests for scripts/board_desk.py.

Every page is made up in a temporary checkout. claude, gh, git and spend_report.py are faked through board_desk.run,
and launchctl through subprocess.run: nothing here calls a model or the network, or installs a job."""

import contextlib
import importlib.util
import io
import json
import os
import plistlib
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo

SCRIPTS = Path(__file__).resolve().parents[1]
REPO = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

import board_desk as desk  # noqa: E402

UTC = timezone.utc
DIRECTIVE = "D-20260216-desk-test"
SPEND = ("Spend as of 02-16 18:00 Dhaka (all times Dhaka)\n- GitHub Actions, Acme: $1.00 of $30.00\n"
         "- Hosting: $2.00 of $20.00\n")
BLOB = "https://github.com/example/company/blob/main/"
SKELETONS = {  # the desk's pages before their first use
    "progress.md": """---
title: Progress, hour by hour
owner: ceo
status: active
updated: 2026-02-16
related: [summaries.md, asks.md]
---

# Progress, hour by hour

What happened in the company each hour, in plain words, newest first. Written only by `scripts/board_desk.py`.

## Spend

(not read yet: the job's first run writes it)
""",
    "summaries.md": """---
title: Daily executive summaries
owner: ceo
status: active
updated: 2026-02-16
related: [progress.md, asks.md]
---

# Daily executive summaries

Each day's executive summary, newest first. Written only by `scripts/board_desk.py`.
""",
    "asks.md": """---
title: Asks for the Board
owner: ceo
status: active
updated: 2026-02-16
related: [progress.md, summaries.md]
---

# Asks for the Board

Each thing the Board must decide or do, one entry each. Only the CEO writes it.

## Open

(none yet)

## Closed

(none yet)
""",
}
QA_PAGE = """---
title: The Board's questions and the CEO's answers
owner: ceo
status: active
updated: 2026-02-17
related: [asks.md, progress.md]
---

# The Board's questions and the CEO's answers

Every question the Board asks the CEO, with the answer and its sources.

## 2026-02-17

### Q-1 · current · the order form · asked 09:1x

- **Your words:** "Is the order form ready?"
- **Answer:** Yes, since noon. The test order went through, from a phone too.
- **Sources:** [D-20260216-the-desk](../../board/directives/D-20260216-the-desk.md), status log 2026-02-17.

### Q-2 · current · the menu · asked about 09:4x

- **Your words:** "Can http://acme.test/menu open without http://acme.test/welcome first? Some people know us."
- **Answer:** Yes, from the next release on: the welcome page becomes a link.
- **Sources:** [D-20251229-menu](../../board/directives/D-20251229-menu.md), its status log; [asks.md](asks.md) B-3.
- **Asked before:** on 2026-02-16 you asked for a longer welcome page.

### Q-3 · current · delivery · asked about 10:0x

- **Your words:** "How far do we deliver?"
- **Answer:** Up to 10 km from the shop.
- **Sources:** [DD-001](../../engineering/designs/DD-001-old-orders.md).

### Q-4 · current · Sundays · asked about 10:0x

- **Your words:** "When do we open on Sundays?"
- **Answer:** From March on. The page says so once PR 89, open, is in.
- **Sources:** [D-20251229-menu](../../board/directives/D-20251229-menu.md); [PR 89](https://github.com/example/acme/pull/89).

### Q-5 · current · how we work · asked about 10:1x

- **Your words:** "How do we keep the orders on time?"
- **Answer:** The kitchen gets each one 40 minutes before its pickup.
- **Sources:** [D-20251212-platform](../../board/directives/D-20251212-platform.md).

### Q-6 · current · the desk · asked about 10:1x

- **Your words:** "Can I find my old questions here?"
- **Answer:** Yes: this page is that list, and the desk shows it as a table.
- **Sources:** [D-20260216-the-desk](../../board/directives/D-20260216-the-desk.md).
"""


def setUpModule():
    """The answers' seal in a temporary folder (no test writes the live one), and settings that are the tests' own,
    whatever company.json says."""
    seals = tempfile.TemporaryDirectory()
    unittest.addModuleCleanup(seals.cleanup)
    repos = (("example/acme", "production.yml"), ("example/demo", None), ("example/third", None))
    pages = {"progress": ("Progress", desk.PROGRESS.as_posix()), "summaries": ("Daily summaries", desk.SUMMARIES.as_posix()),
             "company": ("How the company works", "knowledge/company/how-it-works.md"),
             "product": ("The product", "knowledge/products/acme/plan.md")}
    patches = [mock.patch.object(desk.answers_seal, "SEAL_DIR", Path(seals.name) / "seal"),
               mock.patch.object(desk, "SETTINGS", {}), mock.patch.object(desk, "REPOS", repos),
               mock.patch.object(desk.adapter_notion, "PAGES", pages),
               mock.patch.object(desk.adapter_notion, "ROOT_TITLE", "Board desk"),
               mock.patch.object(desk.adapter_notion, "GITHUB", BLOB)]
    for module in (desk, desk.adapter_notion, desk.answers_seal):
        patches += [mock.patch.object(module, "ZONE", ZoneInfo("Asia/Dhaka")),
                    mock.patch.object(module, "ZONE_NAME", "Dhaka")]
    for patch in patches:
        patch.start()
        unittest.addModuleCleanup(patch.stop)


def at(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=UTC)


def reply(text, subtype="success", is_error=False, code=0, stderr=""):
    answer = {"type": "result", "subtype": subtype, "is_error": is_error, "result": text,
              "usage": {"input_tokens": 3, "cache_creation_input_tokens": 1200, "cache_read_input_tokens": 0,
                        "output_tokens": 80}, "modelUsage": {"claude-sonnet-5-5": {}}}
    return subprocess.CompletedProcess(["claude"], code, json.dumps(answer), stderr)


class Checkout(unittest.TestCase):
    """A made-up checkout with the desk's pages before their first use (SKELETONS), one directive, and the fakes."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        for page in ("progress.md", "summaries.md", "asks.md"):
            self.put(desk.DESK / page, SKELETONS[page])
        self.put(desk.DIRECTIVES / "README.md", "# Directives\n")
        self.rows = []
        self.write_directive()
        self.replies, self.calls, self.gh, self.spend = [], [], {}, subprocess.CompletedProcess([], 0, SPEND, "")
        self.stalled = subprocess.CompletedProcess([], 2, "", "capacity_scan.py: error: unrecognized arguments: --stalled\n")
        for patcher in (mock.patch.object(desk, "run", self.fake_run), mock.patch.object(desk, "say", lambda text: None),
                        mock.patch.object(desk, "agents_at_work", lambda now: 3)):
            patcher.start()
            self.addCleanup(patcher.stop)

    def put(self, rel, text):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def page(self, rel=desk.PROGRESS):
        return (self.root / rel).read_text()

    def write_directive(self):
        table = "".join(f"| 2026-02-16 | ceo | {row} |\n" for row in self.rows)
        self.put(desk.DIRECTIVES / f"{DIRECTIVE}.md", f"---\ntitle: test\n---\n\n# {DIRECTIVE}\n\n## Plan\n\n"
                 f"| 2026-02-16 | ceo | Decided: a plan row, not a status row |\n\n## Status log\n\n"
                 f"| Date | Who | Entry |\n|---|---|---|\n{table}")

    def add_rows(self, *rows):
        self.rows += rows
        self.write_directive()

    def fake_run(self, argv, **kwargs):
        self.calls.append((argv, kwargs))
        if argv[0] == "claude":
            return self.replies.pop(0) if self.replies else reply("Done: nothing to say.")
        if argv[0] == "gh":
            return subprocess.CompletedProcess(argv, 0, json.dumps(self.gh.get(argv[1], [])), "")
        if argv[0] == "git":
            return subprocess.CompletedProcess(argv, 1, "", "")
        if str(argv[-1]).endswith("spend_report.py"):
            return self.spend
        if str(argv[1]).endswith("capacity_scan.py") and argv[2:] == ["--stalled"]:
            return self.stalled  # by default as a scan with no such flag answers
        raise AssertionError(f"unexpected command {argv[0]}")

    def claude_calls(self):
        return [kwargs for argv, kwargs in self.calls if argv[0] == "claude"]

    def hour(self, now):
        return desk.hour(self.root, at(now))

    def started(self, when="2026-02-16T14:00"):
        """The state of a run that wrote the hour ending at `when`, with the fixture's rows already seen."""
        desk.save_state(self.root, desk.baseline(self.root, at(when)))


class Formats(unittest.TestCase):
    def test_the_page_s_example_round_trips(self):
        text = ("---\ntitle: Progress\nupdated: 2026-02-16\n---\n\n# Progress\n\nAbout.\n\n## Spend\n\nSpend as of x\n- a\n\n"
                "## 2026-02-16, Monday\n### 18:00-24:00\n- 20:00-21:00 Decided: keep it (undo: revert; D-1).\n"
                "- 18:00-20:00 Nothing happened. (3 agents at work)\n### 06:00-18:00: Nothing happened.\n")
        self.assertEqual(desk.render_progress(*desk.parse_progress(text)), text)

    def test_a_multi_line_entry_round_trips(self):
        text = ("# P\n\n## Spend\n\nSpend as of x\n\n## 2026-02-16, Monday\n### 12:00-18:00\n- 13:00-16:00\n  - Decided: a.\n"
                "  - Done: b.\n- 12:00-13:00 Nothing happened.\n")
        self.assertEqual(desk.render_progress(*desk.parse_progress(text)), text)

    def test_empty_hours_merge_within_a_block_and_empty_blocks_share_a_heading(self):
        days = {}
        for hour in range(0, 20):
            desk.place(days, at("2026-02-15T18:00") + timedelta(hours=hour), at("2026-02-15T19:00") + timedelta(hours=hour),
                       None, 2)
        desk.place(days, at("2026-02-16T14:00"), at("2026-02-16T15:00"), ["Done: x."], None)
        self.assertEqual(desk.render_day(date(2026, 2, 16), days[date(2026, 2, 16)]), [
            "## 2026-02-16, Monday", "### 18:00-24:00", "- 20:00-21:00 Done: x.", "- 18:00-20:00 Nothing happened. "
            "(2 agents at work)", "### 00:00-18:00: Nothing happened."])

    def test_an_empty_span_across_midnight_splits_and_an_entry_sits_on_its_last_day(self):
        days = {}
        desk.place(days, at("2026-02-15T16:00"), at("2026-02-15T20:00"), None, 1)  # 22:00-02:00 Dhaka
        self.assertEqual(sorted(days), [date(2026, 2, 15), date(2026, 2, 16)])
        self.assertEqual(desk.render_day(date(2026, 2, 15), days[date(2026, 2, 15)])[-1],
                         "- 22:00-24:00 Nothing happened. (1 agent at work)")
        days = {}
        desk.place(days, at("2026-02-15T16:00"), at("2026-02-15T20:00"), ["Done: x."], None)
        self.assertEqual(list(days), [date(2026, 2, 16)])
        self.assertEqual(desk.render_day(date(2026, 2, 16), days[date(2026, 2, 16)])[-1],
                         "- 00:00-02:00 Since 02-15 22:00: Done: x.")

    def test_a_line_the_job_didnt_write_stops_the_parse(self):
        with self.assertRaises(ValueError):
            desk.parse_progress("# P\n\n## Spend\n\n## 2026-02-16, Monday\nsomeone's note\n")
        with self.assertRaises(ValueError):
            desk.parse_progress("# P\n\nno spend heading\n")

    def test_strict_refuses_a_hand_edit_the_grammar_would_take(self):
        good = "# P\n\n## Spend\n\nSpend as of x\n\n## 2026-02-16, Monday\n### 18:00-24:00\n- 20:00-21:00 Done: x.\n"
        desk.parse_progress(good, strict=True)
        for edit in (good.replace("Monday", "Tuesday"), good.replace("### 18:00-24:00", "### 12:00-24:00"),
                     good.replace("Spend as of x", "Spend as of x\na note of mine"), good + "\n"):
            with self.assertRaises(ValueError, msg=edit):
                desk.parse_progress(edit, strict=True)

    def test_a_block_with_an_entry_is_never_collapsed(self):
        days = {}
        desk.place(days, at("2026-02-15T18:00"), at("2026-02-16T00:00"), None, None)  # 00:00-06:00 Dhaka, empty
        desk.place(days, at("2026-02-15T20:00"), at("2026-02-15T21:00"), ["Done: x."], None)  # 02:00-03:00
        self.assertIn("- 02:00-03:00 Done: x.", desk.render_day(date(2026, 2, 16), days[date(2026, 2, 16)]))

    def test_utc_times_become_the_board_s(self):
        self.assertEqual(desk.local_times("at 21:47Z, landed 2026-02-16T19:05:03Z"),
                         "at 03:47 Dhaka, landed 2026-02-17 01:05 Dhaka")
        self.assertEqual(desk.local_times("09:05 UTC, 2026-02-13 10:30 UTC, 13:00-16:00Z, 22:00–24:00 UTC"),
                         "15:05 Dhaka, 2026-02-13 16:30 Dhaka, 19:00-22:00 Dhaka, 04:00-06:00 Dhaka")


class Checks(unittest.TestCase):
    PACKET = ("The hour: 2026-02-16 20:00-21:00 Dhaka. At 12:00.\n"
              "- [D-20260216-desk-test, ceo] Decided: 3 retries (PR #41; A-2)")

    def check(self, text):
        return desk.check_entry(self.PACKET)(text)

    def test_a_clean_entry_passes(self):
        self.assertIsNone(self.check("Decided: 3 retries (D-20260216-desk-test). Shipped: it (PR #41). Ask A-2."))
        self.assertIsNone(self.check("Done at 12:00 on 02-16, 20:00-21:00 (2026-02-16): see board_desk.py and asks.md."))

    def test_each_failure_names_its_reason_never_the_text(self):
        cases = {"x" * 601: "over 600 bytes", "a\nb\nc\nd\ne\nf": "over 5 lines", "Done: 4 retries.": "a number not in the packet",
                 "Done (D-20260216-other).": "an id not in the packet", "Shipped (PR #42).": "an id not in the packet",
                 "Shipped 12 PRs.": "a number not in the packet", "Done at 21:30.": "a time not in the packet",
                 "Done on 2026-02-15.": "a date not in the packet", "Done on 02-15.": "a date not in the packet",
                 "": "no text"}
        for text, reason in cases.items():
            self.assertEqual(self.check(text), reason, text)

    def test_names_links_addresses_and_domains_pass_whole(self):
        for text in ("Done: see https://example.com/x", "Done: [it](x)", "Mail ops@example.org", "Done for acme.test",
                     "Done for shop.example.", "Acme Bakery liked it.", "Live on acme.test and demo.test."):
            self.assertIsNone(self.check(text), text)

    def test_scrub_keeps_a_packet_line_whole_but_its_times_and_link_marks(self):
        line = "Acme Bakery (ACME) wrote ops@shop.example.com via https://x.test/a, see shop.test and acme.test, in notes.md"
        self.assertEqual(desk.scrub(line), line)
        self.assertEqual(desk.scrub("see [the PR](https://x.test/1) at 14:30Z"),
                         "see [the PR] (https://x.test/1) at 20:30 Dhaka")

    def test_mark_unsourced_marks_each_fact_the_packet_doesn_t_hold_and_nothing_else(self):
        cases = {"Decided: 3 retries, then 4 (PR #41; PR #42).": "Decided: 3 retries, then 4 (unchecked) (PR #41; PR #42 "
                                                                    "(unchecked)).",
                 "Done at 12:00 and 21:30 on 2026-02-16 and 2026-02-15, 02-16 and 02-14.":
                     "Done at 12:00 and 21:30 (unchecked) on 2026-02-16 and 2026-02-15 (unchecked), 02-16 and 02-14 "
                     "(unchecked).",
                 "Done (D-20260216-desk-test; D-20260216-other).": "Done (D-20260216-desk-test; D-20260216-other "
                                                                   "(unchecked)).",
                 "Done: 1,000 rows.": "Done: 1,000 (unchecked) rows."}
        for text, marked in cases.items():
            self.assertEqual(desk.mark_unsourced(text, self.PACKET), marked, text)


class Hour(Checkout):
    def test_the_first_run_writes_nothing_and_counts_whats_there_as_seen(self):
        self.add_rows("Decided: an old row")
        before = self.page()
        self.assertEqual(self.hour("2026-02-16T14:05"), 0)
        self.assertEqual(self.page(), before)
        self.assertEqual(desk.load_state(self.root)["last_end"], "2026-02-16T14:00:00+00:00")
        self.assertEqual(self.claude_calls(), [])

    def test_an_hour_with_rows_gets_the_writers_entry_and_the_state_moves(self):
        self.started()
        self.add_rows("Decided: keep the old label (undo: revert the commit)", "NEXT: the next step; waits: none")
        self.replies = [reply(f"Decided: keep the old label; undo by reverting it ({DIRECTIVE}).")]
        self.assertEqual(self.hour("2026-02-16T15:02"), 0)
        page = self.page()
        self.assertIn(f"## 2026-02-16, Monday\n### 18:00-24:00\n- 20:00-21:00 Decided: keep the old label; undo by "
                      f"reverting it ({DIRECTIVE}).\n", page)
        self.assertIn("updated: 2026-02-16", page)
        self.assertEqual(desk.load_state(self.root)["last_end"], "2026-02-16T15:00:00+00:00")
        packet = self.claude_calls()[0]["input"]
        self.assertTrue(packet.startswith("The hour: 2026-02-16 20:00-21:00 Dhaka."))
        self.assertLess(packet.index("Decided: keep"), packet.index("NEXT: the next"))  # priority rows first
        self.assertEqual(self.hour("2026-02-16T15:40"), 0)  # the same hour again: nothing more
        self.assertEqual(len(self.claude_calls()), 1)

    def test_the_writer_runs_with_no_tools_settings_or_claude_md_outside_the_repo(self):
        self.started()
        self.add_rows("Done: a thing")
        self.hour("2026-02-16T15:02")
        (argv, kwargs), = [(argv, kwargs) for argv, kwargs in self.calls if argv[0] == "claude"]
        flags = dict(zip(argv, argv[1:]))
        self.assertEqual((flags["--model"], flags["--tools"], flags["--setting-sources"], flags["--mcp-config"]),
                         ("sonnet", "", "", '{"mcpServers":{}}'))
        self.assertEqual(flags["--system-prompt-file"], str(SCRIPTS / "board_desk" / "scribe.md"))
        for flag in ("--strict-mcp-config", "--no-session-persistence", "--disable-slash-commands"):
            self.assertIn(flag, argv)
        self.assertEqual(kwargs["env"]["CLAUDE_CODE_DISABLE_CLAUDE_MDS"], "1")
        self.assertNotIn(str(REPO), kwargs["cwd"])
        self.assertFalse(Path(kwargs["cwd"]).exists())  # a fresh folder, gone after the run

    def test_names_links_and_addresses_reach_the_writer_and_the_page_whole(self):
        self.started()
        self.add_rows("Decided: Acme Bakery get the new label first (undo: drop it)",
                      "Done: told ops@acme.example at 14:30Z, see https://x.test/a and acme.test")
        self.replies = [reply(f"Decided: Acme Bakery get the label first; told ops@acme.example ({DIRECTIVE}).")]
        self.hour("2026-02-16T15:02")
        calls = self.claude_calls()
        self.assertEqual(len(calls), 1)
        for whole in ("Acme Bakery", "ops@acme.example", "https://x.test/a", "acme.test", "at 20:30 Dhaka"):
            self.assertIn(whole, calls[0]["input"])
        self.assertIn(f"Decided: Acme Bakery get the label first; told ops@acme.example ({DIRECTIVE}).", self.page())

    def test_two_unsourced_answers_post_the_last_with_each_fact_marked_unchecked(self):
        self.started()
        self.add_rows("Decided: Acme Bakery first (undo: drop it)", "Done: routine")
        self.replies = [reply("Decided: 7 things."), reply(f"Decided: 8 things for Acme Bakery ({DIRECTIVE}).")]
        self.hour("2026-02-16T15:02")
        calls, page = self.claude_calls(), self.page()
        self.assertEqual(len(calls), 2)
        self.assertIn("failed a check (a number not in the packet)", calls[1]["input"])
        self.assertIn(f"- 20:00-21:00 Decided: 8 (unchecked) things for Acme Bakery ({DIRECTIVE}).\n", page)
        self.assertNotIn("(raw;", page)

    def test_an_unsourced_answer_then_one_over_the_cap_posts_the_first_marked(self):
        self.started()
        self.add_rows("Decided: one (undo: a)")
        self.replies = [reply("Decided: 7 things."), reply("x" * 601)]
        self.hour("2026-02-16T15:02")
        self.assertIn("Decided: 7 (unchecked) things.\n", self.page())
        self.assertNotIn("(raw;", self.page())

    def test_an_unsourced_answer_then_a_usage_stop_posts_the_first_marked(self):
        self.started()
        self.add_rows("Decided: one (undo: a)")
        self.replies = [reply("Decided: 7 things."),
                        reply("Claude AI usage limit reached", subtype="error", is_error=True, code=1)]
        self.hour("2026-02-16T15:02")
        self.assertEqual(len(self.claude_calls()), 2)
        self.assertIn("Decided: 7 (unchecked) things.\n", self.page())
        self.assertNotIn("(raw;", self.page())

    def test_a_markdown_link_in_the_writer_s_text_lands_as_text_and_target(self):
        self.started()
        self.add_rows("Decided: one (undo: a)")
        self.replies = [reply(f"Decided: one, see [the page](knowledge/x.md) ({DIRECTIVE}).")]
        self.hour("2026-02-16T15:02")
        self.assertIn(f"Decided: one, see [the page] (knowledge/x.md) ({DIRECTIVE}).\n", self.page())
        self.assertNotIn("](", self.page().split("## 2026-02-16")[1])

    def test_two_failed_format_checks_give_the_raw_rows_whole(self):
        self.started()
        self.add_rows("Decided: Acme Bakery first (undo: drop it)", "Done: routine")
        self.replies = [reply("x" * 601), reply("a\nb\nc\nd\ne\nf")]
        self.hour("2026-02-16T15:02")
        page = self.page()
        self.assertIn("(raw; the writer failed: over 5 lines)", page)
        self.assertIn("Decided: Acme Bakery first (undo: drop it)", page)
        self.assertNotIn("Done: routine", page)  # the raw entry is the priority rows

    def test_a_usage_stop_gives_the_raw_fallback_with_no_retry(self):
        self.started()
        self.add_rows("Decided: x (undo: y)")
        self.replies = [reply("Claude AI usage limit reached", subtype="error", is_error=True, code=1)]
        self.hour("2026-02-16T15:02")
        self.assertEqual(len(self.claude_calls()), 1)
        self.assertIn("(raw; the writer failed: the account's usage limit)", self.page())

    def test_a_decided_row_the_entry_doesnt_name_is_added_outside_the_cap(self):
        self.started()
        self.add_rows("Decided: one (undo: a)", "ASK 1 b9 A-12: sent", "Done: routine")
        self.replies = [reply("Done: routine work.")]
        self.hour("2026-02-16T15:02")
        self.assertIn(f"- 20:00-21:00\n  - Done: routine work.\n  - +1 more decided: test ({DIRECTIVE}); +1 more asks: "
                      "A-12\n", self.page())  # by the directive's title first; A-12 isn't in asks.md

    def test_the_covered_line_counts_for_completeness_and_never_reaches_the_page(self):
        """The entry names things by their plain names, so scribe.md's last line lists the ids of the rows it speaks of;
        the script takes it off, and names the rest by plain name."""
        self.started()
        self.put(desk.ASKS, self.page(desk.ASKS).replace(
            "## Open\n\n(none yet)", "## Open\n\n### A-12 · open · b9 · D-20260216-x · asked 2026-02-16 21:00\n\n"
            "- **Question:** Should the launch party move to Friday?\n"))
        self.add_rows("Decided: one (undo: a)", "ASK 1 b9 A-12: sent", "Done: routine")
        self.replies = [reply("You decided nothing new; the CEO asks whether the launch party moves.\nCovered: A-12")]
        self.hour("2026-02-16T15:02")
        page = self.page()
        self.assertNotIn("Covered", page)
        self.assertIn("  - You decided nothing new; the CEO asks whether the launch party moves.\n"
                      f"  - +1 more decided: test ({DIRECTIVE})\n", page)
        self.replies = [reply("Should the launch party move to Friday? (A-12)\nCovered: A-9")]  # an id not in the packet
        self.add_rows("ASK 2 b9 A-12: sent again")
        self.hour("2026-02-16T16:02")
        self.assertEqual(len(self.claude_calls()), 3, "the Covered line's ids are checked as any: one retry")

    def test_a_covered_id_the_lines_never_speak_of_still_gets_its_more_line(self):
        """The writer's Covered list alone never drops a row: a row counts as covered only with half its plain name's
        longer words in the lines; a Covered line that isn't last, or is in bold, comes off the page too."""
        self.started()
        self.put(desk.ASKS, self.page(desk.ASKS).replace(
            "## Open\n\n(none yet)", "## Open\n\n### A-12 · open · b9 · D-20260216-x · asked 2026-02-16 21:00\n\n"
            "- **Question:** Should the launch party move to Friday?\n"))
        self.add_rows("Decided: one (undo: a)", "ASK 1 b9 A-12: sent", "Done: routine")
        self.replies = [reply(f"**Covered: A-12, {DIRECTIVE}**\nRoutine work only.")]
        self.hour("2026-02-16T15:02")
        page = self.page()
        self.assertNotIn("Covered", page)
        self.assertIn(f"  - Routine work only.\n  - +1 more decided: test ({DIRECTIVE}); +1 more asks: Should the launch "
                      "party move to Friday? (A-12)\n", page)

    def test_the_packet_marks_the_ceo_s_words_and_gives_each_id_s_plain_name(self):
        """The CEO's To the Board rows are marked as the plain source, and a last part names each id: a directive's
        title, an ask's question, a design's and a roadmap's title; nothing of the packet is dropped."""
        self.put(desk.ASKS, self.page(desk.ASKS).replace(
            "## Open\n\n(none yet)", "## Open\n\n### A-12 · open · b9 · D-20260216-x · asked 2026-02-16 21:00\n\n"
            "- **Question:** Should the launch party move to Friday?\n\n"
            "### B-5 · open · two-way · D-20260216-x · asked 2026-02-16 21:00\n\n"  # a Board step: its Step line
            "- **Step:** The labels on the top shelf\n"))
        self.put(Path("knowledge/engineering/designs/DD-001-old-orders.md"),
                 "---\ntitle: \"DD-001: The nightly check of old orders\"\nowner: cto\n---\n")
        self.put(Path("knowledge/engineering/roadmaps/RM-001-simpler-start.md"), "---\ntitle: A simpler start\n---\n")
        state = desk.baseline(self.root, at("2026-02-16T14:00"))
        self.add_rows("To the Board: old orders are checked again each night (DD-001)",
                      "ASK 1 b9 A-12: sent; RM-001 waits on it", "Done: PR #106 merged",
                      "To the Board (09:0xZ): the menu is late", "Done: B-5 is on the Asks page")
        self.put(desk.DIRECTIVES / f"{DIRECTIVE}.md", self.page(desk.DIRECTIVES / f"{DIRECTIVE}.md")
                 + "| 2026-02-16 | cto | To the Board: a line the CTO wrote |\n")  # not the CEO's: unmarked
        packet = desk.gather(self.root, state, at("2026-02-16T14:00"), at("2026-02-16T15:00"))[0]
        self.assertIn(f"[{DIRECTIVE}, cto, row dated 2026-02-16] To the Board: a line the CTO wrote", packet)
        self.assertIn(f"[{DIRECTIVE}, ceo, row dated 2026-02-16, the CEO's words for you] To the Board: old orders",
                      packet)
        self.assertIn("3 To the Board", packet)  # with its time too, ranked first; the CTO's counted, unmarked
        self.assertIn(f"[{DIRECTIVE}, ceo, row dated 2026-02-16, the CEO's words for you] To the Board (09:0xZ): the",
                      packet.split("Done: PR #106")[0])
        self.assertIn("ASK 1 b9 A-12: sent; RM-001 waits on it", packet)
        self.assertIn("Done: PR #106 merged", packet)  # nothing dropped: the writer leaves it out (scribe.md)
        names = packet.split("Plain names of the ids above")[1]
        for line in (f"- {DIRECTIVE}: test", "- DD-001: The nightly check of old orders",
                     "- A-12: Should the launch party move to Friday?", "- RM-001: A simpler start",
                     "- B-5: The labels on the top shelf"):
            self.assertIn(line, names)

    def test_an_empty_hour_says_nothing_happened_without_a_model(self):
        self.started()
        self.hour("2026-02-16T15:02")
        self.hour("2026-02-16T16:02")
        self.assertEqual(self.claude_calls(), [])
        self.assertIn("### 18:00-24:00\n- 20:00-22:00 Nothing happened. (3 agents at work)\n", self.page())

    def test_hours_the_mac_slept_through_become_one_entry(self):
        self.started()
        self.add_rows("Done: a thing")
        self.replies = [reply(f"Done: a thing ({DIRECTIVE}).")]
        self.hour("2026-02-16T17:10")
        self.assertIn(f"- 20:00-23:00 Done: a thing ({DIRECTIVE}).\n", self.page())
        self.assertIn("The hour: 2026-02-16 20:00-23:00 Dhaka.", self.claude_calls()[0]["input"])

    def test_spend_is_read_at_its_hours_and_says_so_when_it_fails(self):
        self.started("2026-02-16T11:00")  # 17:00 Dhaka
        self.hour("2026-02-16T12:01")  # the hour ending 18:00: due
        self.assertIn("## Spend\n\n" + SPEND, self.page())
        self.spend = subprocess.CompletedProcess([], 1, "", "boom")
        self.hour("2026-02-16T13:01")  # 19:00: not due
        self.assertIn("## Spend\n\n" + SPEND, self.page())
        self.started("2026-02-16T23:00")  # 05:00 Dhaka, the next day
        self.hour("2026-02-17T00:01")  # 06:00: due, and it fails
        self.assertIn("## Spend\n\nSpend: not read at 06:01 (spend_report.py exited 1); below is the last read.\n"
                      + SPEND, self.page())

    def test_a_page_with_a_line_it_didnt_write_stops_the_hour_visibly_and_costs_no_model_run(self):
        self.started()
        self.put(desk.PROGRESS, self.page() + "\n## 2026-02-16, Monday\nan edit by hand\n")
        self.add_rows("Done: a thing")
        self.assertEqual(self.hour("2026-02-16T15:02"), 1)
        page = self.page()
        self.assertTrue(page.endswith("\n## 2026-02-16, Monday\nan edit by hand\n"))  # the body as it was
        self.assertEqual(page.count(desk.STOPPED), 1)
        self.assertIn("isn't one this job writes", page)
        self.assertEqual(self.claude_calls(), [])
        self.assertEqual(desk.load_state(self.root)["last_end"], "2026-02-16T14:00:00+00:00")
        self.assertEqual(self.hour("2026-02-16T16:02"), 1)
        self.assertEqual(self.page().count(desk.STOPPED), 1)  # once, not every hour
        self.put(desk.PROGRESS, self.page().replace("\n## 2026-02-16, Monday\nan edit by hand\n", ""))  # the CEO's fix
        self.replies = [reply(f"Done: a thing ({DIRECTIVE}).")]
        self.assertEqual(self.hour("2026-02-16T16:02"), 0)
        self.assertNotIn(desk.STOPPED, self.page())
        self.assertIn(f"- 20:00-22:00 Done: a thing ({DIRECTIVE}).", self.page())

    def test_an_hour_where_gh_failed_never_says_nothing_happened_and_is_read_again(self):
        self.started()
        later = {"pr": [{"number": 41, "title": "Fix it", "mergedAt": "2026-02-16T14:30:00Z"}]}
        self.gh = None
        real = self.fake_run

        def failing(argv, **kwargs):
            if argv[0] == "gh" and self.gh is None:
                self.calls.append((argv, kwargs))
                return subprocess.CompletedProcess(argv, 4, "", "auth")
            return real(argv, **kwargs)
        with mock.patch.object(desk, "run", failing):
            self.hour("2026-02-16T15:02")
            page = self.page()
            self.assertNotIn("Nothing happened", page)
            self.assertIn("- 20:00-21:00 Nothing found; not read: example/acme PRs, example/acme production runs, "
                          "example/demo PRs, example/third PRs (gh); the next hour reads them again.",
                          page)
            self.assertEqual(self.claude_calls(), [])
            self.gh = later
            self.hour("2026-02-16T16:02")
        searches = [argv[argv.index("--search") + 1] for argv, _ in self.calls if argv[:2] == ["gh", "pr"]]
        self.assertEqual(searches[-1], "merged:>=2026-02-16T14:00:00+00:00")  # from the hour it missed
        self.assertIn("PR #41, merged 20:30 Dhaka] Fix it", self.claude_calls()[0]["input"])
        self.assertEqual(desk.load_state(self.root)["unread"], {})

    def test_new_asks_and_answers_go_in_first(self):
        self.started()
        self.put(desk.ASKS, self.page(desk.ASKS).replace(
            "## Open\n\n(none yet)", "## Open\n\n### A-12 · open · b9 · D-20260216-desk-test · asked 2026-02-16 20:10\n\n"
            "- **Question:** Keep the job?\n"))
        self.put(desk.ANSWERS / "2026-W08.md", "| R-id | Ask | Field | Edited | Recorded | Medium id | Words |\n"
                 "|---|---|---|---|---|---|---|\n| R-3 | A-9 | Your answer | 2026-02-16 20:30 | 2026-02-16 20:31 | x | Yes |\n")
        self.add_rows("Done: routine")
        self.hour("2026-02-16T15:02")
        packet = self.claude_calls()[0]["input"]
        self.assertIn("[A-12, asks.md] New ask (open · b9 · D-20260216-desk-test · asked 2026-02-16 20:10): Keep the job?",
                      packet)
        self.assertIn("[R-3, A-9] The Board's answer to A-9 reached the CEO at 2026-02-16 20:31 Dhaka", packet)
        self.assertLess(packet.index("R-3"), packet.index("Done: routine"))

    def test_merged_prs_and_production_runs_in_the_hour_are_read(self):
        self.started()
        self.gh = {"pr": [{"number": 41, "title": "Fix it", "mergedAt": "2026-02-16T14:30:00Z"},
                          {"number": 40, "title": "Old", "mergedAt": "2026-02-16T13:59:00Z"}],
                   "run": [{"databaseId": 9, "status": "completed", "conclusion": "success",
                            "createdAt": "2026-02-16T14:40:00Z", "displayTitle": "Deploy"}]}
        self.hour("2026-02-16T15:02")
        packet = self.claude_calls()[0]["input"]
        self.assertIn("PR #41, merged 20:30 Dhaka] Fix it", packet)
        self.assertNotIn("#40", packet)
        self.assertIn("[example/acme production run 9, started 20:40 Dhaka, success] Deploy", packet)
        self.assertIn("3 PRs merged", packet)  # the fake answers every repo with the same PR


class Day(Checkout):
    SUMMARY = "The day: one decision.\n\n### Since last\n\n- 0 PRs merged, 00:00-24:00 (gh)."

    def setUp(self):
        super().setUp()
        self.capacity = ["D-20260216-desk-test  IDLE | NEXT (2026-02-16): ask Acme Bakery at acme.test; waits: none"]
        patcher = mock.patch.object(desk, "capacity_lines", lambda root, now: list(self.capacity))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_a_name_and_a_domain_reach_the_summary_writer_and_the_page_whole(self):
        self.started("2026-02-16T03:00")
        self.replies = [reply("We asked Acme Bakery at acme.test.")]
        desk.day(self.root, at("2026-02-17T04:01"))
        calls = self.claude_calls()
        self.assertEqual(len(calls), 1)
        self.assertIn("ask Acme Bakery at acme.test", calls[0]["input"])
        self.assertIn("We asked Acme Bakery at acme.test.", self.page(desk.SUMMARIES))

    def test_two_unsourced_summaries_post_the_last_marked_unchecked(self):
        self.started("2026-02-16T03:00")
        self.replies = [reply("We merged 77 PRs."), reply("We merged 78 PRs.")]
        desk.day(self.root, at("2026-02-17T04:01"))
        page = self.page(desk.SUMMARIES)
        self.assertIn("We merged 78 (unchecked) PRs.", page)
        self.assertNotIn("(raw;", page)

    def test_the_10_00_run_raises_no_answers_alarm(self):
        """The day's run at 10:00, its moves to the archives included, after a read that sealed an answer."""
        desk.save_state(self.root, {"board": "board-user"}, desk.READER)
        self.assertEqual(desk.read_board(self.root, FakeAdapter([change("Yes")]), at("2026-02-17T03:55")), 0)
        self.started("2026-02-16T03:00")
        self.replies = [reply(self.SUMMARY)]
        self.assertEqual(desk.day(self.root, at("2026-02-17T04:01")), 0)
        self.assertEqual(desk.answers_seal.report(self.root), ([], set(), ""))

    def test_the_day_packet_gives_each_id_s_plain_name(self):
        self.put(desk.ASKS, self.page(desk.ASKS).replace(
            "## Open\n\n(none yet)", "## Open\n\n### A-12 · open · b9 · D-20260216-x · asked 2026-02-16 21:00\n\n"
            "- **Question:** Should the launch party move to Friday?\n"))
        packet = desk.day_packet(self.root, date(2026, 2, 16), at("2026-02-17T04:01"), [], [])[0]
        body, names = packet.split("Plain names of the ids above")
        self.assertIn("open now: A-12 (asks.md)", body)
        self.assertIn("- A-12: Should the launch party move to Friday?", names)

    def test_the_summary_waits_for_10_in_the_board_s_zone_and_covers_yesterday(self):
        self.started("2026-02-16T03:00")  # 09:00 Dhaka on the 16th: summarised up to the 15th
        self.assertEqual(desk.day(self.root, at("2026-02-17T03:30")), 0)  # 09:30 on the 17th
        self.assertNotIn("## 2026-02-16", self.page(desk.SUMMARIES))
        self.replies = [reply(self.SUMMARY)]
        self.assertEqual(desk.day(self.root, at("2026-02-17T04:01")), 0)  # 10:01
        page = self.page(desk.SUMMARIES)
        self.assertIn("## 2026-02-16, Monday\nWritten 2026-02-17 10:01 Dhaka, for 00:00-24:00 Dhaka.\n\n"
                      + self.SUMMARY + "\n\n### Spend (read 10:01 Dhaka)\n\n" + SPEND, page)
        argv, kwargs = next((argv, kwargs) for argv, kwargs in self.calls if argv[0] == "claude")
        self.assertEqual(dict(zip(argv, argv[1:]))["--model"], "opus")
        self.assertIn("The day: 2026-02-16, Monday, 00:00-24:00 Dhaka.", kwargs["input"])
        self.assertEqual(desk.load_state(self.root)["summarised"], "2026-02-16")
        desk.day(self.root, at("2026-02-17T05:01"))
        self.assertEqual(len(self.claude_calls()), 1)

    def test_after_the_summary_the_summarised_day_rolls_up_word_for_word(self):
        self.started("2026-02-16T03:00")
        yesterday = "## 2026-02-16, Monday\n### 18:00-24:00\n- 20:00-21:00 Done: a thing (D-20260216-desk-test).\n"
        self.put(desk.PROGRESS, self.page() + "\n## 2026-02-17, Tuesday\n### 06:00-12:00\n- 09:00-10:00 Done: b.\n\n"
                 + yesterday)
        self.replies = [reply(self.SUMMARY)]
        self.assertEqual(desk.day(self.root, at("2026-02-17T04:01")), 0)
        page = self.page()
        self.assertNotIn("## 2026-02-16, Monday", page)
        self.assertIn("## 2026-02-17, Tuesday", page)
        self.assertIn("[progress-archive-2026-02.md](progress-archive-2026-02.md)", page)
        self.assertIn(yesterday.rstrip("\n"), self.page(desk.DESK / "progress-archive-2026-02.md"))
        desk.parse_progress(page, strict=True)
        self.replies = [reply(f"Done: c ({DIRECTIVE}).")]
        self.add_rows("Done: c")
        self.assertEqual(self.hour("2026-02-17T05:02"), 0)  # the hour still takes the page after a roll-up

    def test_a_summary_failing_its_checks_twice_is_the_raw_fallback(self):
        self.started("2026-02-16T03:00")
        self.replies = [reply("We merged 999 PRs.\n## Big heading"), reply("# Bigger")]  # only an unsourced fact goes out
        desk.day(self.root, at("2026-02-17T04:01"))
        page = self.page(desk.SUMMARIES)
        self.assertIn("(raw; the summary writer failed: a heading above ###)", page)
        self.assertIn("Counts, 00:00-24:00 Dhaka (gh): example/acme: 0 PRs merged; 0 production runs (none)", page)
        self.assertIn("### Spend (read 10:01 Dhaka)", page)
        self.assertNotIn("999", page)

    def test_days_missed_are_summarised_oldest_first_newest_on_top(self):
        self.started("2026-02-14T03:00")
        self.replies = [reply("First."), reply("Second.")]
        desk.day(self.root, at("2026-02-16T04:01"))
        page = self.page(desk.SUMMARIES)
        self.assertLess(page.index("## 2026-02-15, Sunday"), page.index("## 2026-02-14, Saturday"))
        self.assertIn("## 2026-02-14, Saturday\nWritten 2026-02-16 10:01 Dhaka, for 00:00-24:00 Dhaka.\n\nFirst.", page)


class Edges(Checkout):
    """Failed runs, limits and shapes the hour and the day must take."""

    def test_a_markdown_link_in_a_packet_line_is_no_longer_a_link(self):
        self.assertEqual(desk.scrub("see [the PR](https://x.test/1) and [notes](../n.md)"),
                         "see [the PR] (https://x.test/1) and [notes] (../n.md)")

    def test_a_spend_block_with_a_domain_goes_on_both_pages_whole(self):
        self.spend = subprocess.CompletedProcess([], 0, "Spend as of 02-16 18:00 Dhaka\n- Hosting: see host.test\n", "")
        self.started()
        self.add_rows("Done: a thing")
        self.hour("2026-02-16T15:02")
        self.assertIn("## Spend\n\nSpend as of 02-16 18:00 Dhaka\n- Hosting: see host.test\n", self.page())
        desk.save_state(self.root, dict(desk.load_state(self.root), summarised="2026-02-15"))
        desk.day(self.root, at("2026-02-17T04:01"))
        summaries = self.page(desk.SUMMARIES)
        self.assertIn("- Hosting: see host.test", summaries)
        self.assertNotIn("not read at", summaries)

    def test_an_answer_that_isn_t_a_json_object_is_a_failed_run(self):
        for stdout in ("[]", "null", '"text"'):
            with mock.patch.object(desk, "run", lambda argv, **kwargs: subprocess.CompletedProcess(argv, 0, stdout, "")):
                self.assertEqual(desk.ask_model("p", desk.RULES / "scribe.md", "sonnet", 5),
                                 (None, "claude's answer wasn't a JSON object", {}), stdout)
        odd = json.dumps({"type": "result", "subtype": "success", "is_error": False, "result": "Done: x.",
                          "usage": ["not", "a", "dict"], "modelUsage": None})
        with mock.patch.object(desk, "run", lambda argv, **kwargs: subprocess.CompletedProcess(argv, 0, odd, "")):
            text, reason, usage = desk.ask_model("p", desk.RULES / "scribe.md", "sonnet", 5)
        self.assertEqual((text, reason, usage["input_tokens"], usage["models"]), ("Done: x.", None, 0, []))
        self.started()
        self.add_rows("Done: a thing")
        self.replies = [subprocess.CompletedProcess(["claude"], 0, "[]", "")] * 2
        self.assertEqual(self.hour("2026-02-16T15:02"), 0)
        self.assertIn("(raw; the writer failed: claude's answer wasn't a JSON object)", self.page())

    def test_overdue_days_are_written_before_10_and_yesterday_waits_for_it(self):
        self.started("2026-02-13T03:00")  # summarised up to the 12th
        self.assertEqual(desk.day(self.root, at("2026-02-17T01:00")), 0)  # 07:00 Dhaka on the 17th
        page = self.page(desk.SUMMARIES)
        for day in ("2026-02-13", "2026-02-14", "2026-02-15"):
            self.assertIn(f"## {day}, ", page)
        self.assertNotIn("## 2026-02-16", page)
        self.assertEqual(desk.load_state(self.root)["summarised"], "2026-02-15")
        self.assertEqual(desk.due(date(2026, 2, 16)), datetime(2026, 2, 17, 4, 0, tzinfo=UTC))

    def test_runs_are_filtered_by_their_start_and_a_read_at_its_limit_is_marked(self):
        self.started()
        self.gh = {"pr": [{"number": n, "title": f"PR {n}", "mergedAt": "2026-02-16T14:30:00Z"}
                          for n in range(desk.PR_LIMIT)]}
        self.replies = [reply(f"Shipped {desk.PR_LIMIT * 3} PRs.")] * 2
        self.hour("2026-02-16T15:02")
        runs = [argv for argv, _ in self.calls if argv[:3] == ["gh", "run", "list"]]
        self.assertEqual(runs[0][runs[0].index("--created") + 1], ">=2026-02-16T14:00:00Z")
        self.assertIn("At their limit, so maybe incomplete: gh (example/acme PRs), gh (example/demo PRs), gh "
                      "(example/third PRs).", self.claude_calls()[0]["input"])
        self.assertIn("  - Maybe incomplete: gh (example/acme PRs), gh (example/demo PRs), gh (example/third PRs) "
                      "answered at their limit.\n", self.page())
        packet, counts, _ = desk.day_packet(self.root, date(2026, 2, 16), at("2026-02-17T04:01"), [], [])
        self.assertIn(f"example/acme: {desk.PR_LIMIT} PRs merged (gh's limit: maybe more); 0 production runs (none)",
                      counts[0])

    def test_the_writer_never_gets_an_api_key(self):
        self.started()
        self.add_rows("Done: a thing")
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "not-a-key", "ANTHROPIC_AUTH_TOKEN": "not-a-token"}):
            self.hour("2026-02-16T15:02")
        env = self.claude_calls()[0]["env"]
        self.assertNotIn("ANTHROPIC_API_KEY", env)
        self.assertNotIn("ANTHROPIC_AUTH_TOKEN", env)
        self.assertEqual(env["PATH"], os.environ["PATH"])

    def test_with_the_spend_heading_gone_the_stopped_line_heads_the_body(self):
        self.started()
        self.put(desk.PROGRESS, self.page().replace("## Spend\n", "## Spent\n"))
        self.add_rows("Done: a thing")
        self.assertEqual(self.hour("2026-02-16T15:02"), 1)
        page = self.page()
        self.assertEqual(page.count(desk.STOPPED), 1)
        self.assertTrue(page.split("\n---\n", 1)[1].startswith("\n" + desk.STOPPED), page[:400])
        self.hour("2026-02-16T16:02")
        self.assertEqual(self.page().count(desk.STOPPED), 1)


class Writes(Checkout):
    def test_a_page_changed_between_read_and_write_is_read_again(self):
        real, tries = desk.write, []

        def racing(path, text, before):
            tries.append(before)
            return False if len(tries) == 1 else real(path, text, before)
        with mock.patch.object(desk, "write", racing):
            desk.rewrite(self.root / desk.PROGRESS, lambda text: text + "x\n", at("2026-02-16T15:02"))
        self.assertEqual(len(tries), 2)
        self.assertTrue(self.page().endswith("x\n"))

    def test_a_page_that_keeps_changing_stops_the_write(self):
        with mock.patch.object(desk, "write", lambda path, text, before: False), self.assertRaises(RuntimeError):
            desk.rewrite(self.root / desk.PROGRESS, lambda text: text + "x\n", at("2026-02-16T15:02"))

    def test_an_unreadable_state_is_set_aside_and_the_run_starts_again(self):
        self.started()
        (self.root / desk.STATE).write_text('{"rows": [')
        self.assertEqual(self.hour("2026-02-16T15:02"), 0)
        self.assertEqual(desk.load_state(self.root)["last_end"], "2026-02-16T15:00:00+00:00")
        self.assertEqual(len(list((self.root / desk.STATE).parent.glob("state-unreadable-*.json"))), 1)


class Lock(Checkout):
    def test_a_second_run_waits_then_gives_up_without_writing(self):
        with desk.locked(self.root), mock.patch.object(desk, "LOCK_WAIT", 0):
            self.assertEqual(desk.main(["hour", "--root", str(self.root)]), 1)
        self.assertIsNone(desk.load_state(self.root))


class FakeAdapter:
    """A medium, in the tests only: poll(since) returns the next list of changes it was given, and keeps each since it
    was asked for."""

    def __init__(self, *polls):
        self.polls, self.since = list(polls), []

    def poll(self, since):
        self.since.append(since)
        return self.polls.pop(0) if self.polls else []


def change(value, editor="board-user", ask="A-12", field="Your answer", medium="page-12", edited="2026-02-16T21:03"):
    return {"medium_id": medium, "page": "Asks", "ask": ask, "field": field, "value": value, "editor": editor,
            "edited_at": edited + ":00Z"}


class Reader(Checkout):
    """The reader's KB side. Only a change the medium names the Board as the last editor of becomes the Board's
    word."""

    WEEK = desk.ANSWERS / "2026-W08.md"

    def setUp(self):
        super().setUp()
        desk.save_state(self.root, {"board": "board-user"}, desk.READER)

    def read(self, *polls, now="2026-02-16T21:05"):
        adapter = FakeAdapter(*polls)
        self.assertEqual(desk.read_board(self.root, adapter, at(now)), 0)
        return adapter

    def logged(self):
        path = self.root / desk.READER_LOG
        return [json.loads(line)["why"] for line in path.read_text().splitlines()] if path.exists() else []

    def test_the_board_s_change_becomes_an_r_row_word_for_word(self):
        words = "Not that one | the other.\nAnd a second line, with a \\| too, a <br> and a <b>."
        self.read([change("Yes"), change(words, field="Your words")])
        page = self.page(self.WEEK)
        self.assertTrue(page.startswith("---\ntitle: The Board's answers, 2026-W08\nowner: board\nstatus: active\n"
                                        "updated: 2026-02-17\n"))
        self.assertIn(desk.ANSWERS_HEAD + "\n| R-1 | A-12 | Your answer | 2026-02-17 03:03 | 2026-02-17 03:05 | page-12 | "
                      "Yes |\n| R-2 | A-12 | Your words | 2026-02-17 03:03 | 2026-02-17 03:05 | page-12 | Not that one "
                      "\\| the other.<br>And a second line, with a \\\\\\| too, a \\<br> and a \\<b>. |\n", page)
        self.assertEqual(desk.answer_rows(self.root), [(1, "A-12", "Your answer", "page-12", "Yes"),
                                                       (2, "A-12", "Your words", "page-12", words)])
        self.assertEqual(desk.answers(self.root), {"R-1": ("A-12", "2026-02-17 03:05"),
                                                   "R-2": ("A-12", "2026-02-17 03:05")})
        self.assertEqual(self.logged(), [])

    def test_another_editor_no_editor_or_no_board_id_isn_t_kept_and_is_logged_once(self):
        self.read([change("Yes", editor="the-integration"), change("Later", editor="", ask="A-13", medium="page-13")])
        self.read([change("Yes", editor="the-integration")], now="2026-02-16T21:07")  # the window's overlap
        self.assertFalse((self.root / self.WEEK).exists())
        self.assertEqual(self.logged(), ["another editor", "no editor"])
        self.assertEqual([ask for ask, _ in desk.load_state(self.root, desk.READER)["untied"]], ["A-12", "A-13"])
        self.read([change("Yes", edited="2026-02-16T21:08")], now="2026-02-16T21:09")  # the Board enters it again
        self.assertEqual(desk.answer_rows(self.root), [(1, "A-12", "Your answer", "page-12", "Yes")])
        desk.save_state(self.root, {}, desk.READER)
        self.read([change("No", edited="2026-02-16T21:10")], now="2026-02-16T21:11")
        self.assertEqual(self.logged()[-1], "no Board id recorded")
        self.assertEqual(len(desk.answer_rows(self.root)), 1)

    def test_a_value_equal_to_the_copy_is_no_change_whoever_edited_the_row(self):
        self.read([change("Yes")])
        self.read([change("Yes"), change(" Yes ", editor="the-integration", edited="2026-02-16T21:06")],
                  now="2026-02-16T21:07")
        self.assertEqual(len(desk.answer_rows(self.root)), 1)
        self.assertEqual(self.logged(), [])
        self.read([change("", editor="the-integration", field="Your words")], now="2026-02-16T21:09")  # empty as before
        self.assertEqual(self.logged(), [])

    def test_the_copy_is_the_answers_pages_so_a_lost_state_records_nothing_twice(self):
        """A state written outside the desk is read with the ids the seal keeps, nothing set aside, the alarm standing;
        and a state the desk lost (its since) still records nothing twice: the copy is the answers pages."""
        self.read([change("Yes")])
        (self.root / desk.READER).write_text('{"board": ')
        self.assertEqual(desk.load_state(self.root, desk.READER),
                         {"board": "board-user", "since": at("2026-02-16T21:05").isoformat()})
        self.assertEqual(desk.read_board(self.root, FakeAdapter([change("Yes")]), at("2026-02-16T21:20")), 0)
        self.assertEqual(desk.answers_seal.report(self.root)[0],
                         ["ANSWERS TAMPERED reader.json: changed outside the desk"])
        desk.answers_seal.reseal(self.root)
        desk.save_state(self.root, {"board": "board-user"}, desk.READER)  # lost: no since
        self.read([change("Yes")], now="2026-02-16T21:22")
        self.assertEqual(len(desk.answer_rows(self.root)), 1)

    def test_a_field_that_isn_t_the_board_s_an_unreadable_change_or_no_ask_id_is_logged(self):
        self.read([change("Ship it", field="Recommended"), {"ask": "A-12"}, change("Yes", ask="see A-12")])
        self.assertFalse((self.root / self.WEEK).exists())
        self.assertEqual(self.logged(), ["not a Board-only field", "unreadable", "no ask id"])
        self.assertEqual([ask for ask, _ in desk.load_state(self.root, desk.READER)["untied"]],
                         ["A-12", "a row with no ask id"])

    def test_each_change_it_can_t_use_is_logged_once_over_the_overlapping_reads(self):
        """Each read reaches back over the last, so the same unreadable or non-Board change comes again; it is logged
        and named once."""
        polls = [[change("Ship it", field="Recommended"), {"ask": "A-12"}, {"ask": "A-13", "edited_at": "x"}]] * 3
        for minute, poll in zip(("05", "07", "09"), polls):
            self.read(poll, now=f"2026-02-16T21:{minute}")
        self.assertEqual(self.logged(), ["not a Board-only field", "unreadable", "unreadable"])
        self.assertEqual([ask for ask, _ in desk.load_state(self.root, desk.READER)["untied"]], ["A-12", "A-13"])

    def test_the_words_read_back_word_for_word_and_a_repeat_adds_no_row(self):
        """A literal <br>, a backslash before a bar, and a line break as \\r\\n read back the same, so the overlapping
        reads find no change."""
        for words in ("a <br> b", "c \\| d \\\\ e", "f\r\ng", "h\ri", "<br>", "\\", "j\\<br>k"):
            self.read([change(words, field="Your words", medium=f"page-{len(words)}-{words[:1]}")])
        rows = desk.answer_rows(self.root)
        self.assertEqual([row[4] for row in rows],
                         ["a <br> b", "c \\| d \\\\ e", "f\ng", "h\ni", "<br>", "\\", "j\\<br>k"])
        for words in ("a <br> b", "c \\| d \\\\ e", "f\r\ng", "h\ri", "<br>", "\\", "j\\<br>k"):
            self.read([change(words, field="Your words", medium=f"page-{len(words)}-{words[:1]}")],
                      now="2026-02-16T21:07")
        self.assertEqual(len(desk.answer_rows(self.root)), 7)

    def test_each_read_reaches_back_a_minute_before_the_last_began(self):
        self.assertEqual(self.read([]).since, [None])
        self.assertEqual(self.read([], now="2026-02-16T21:07").since, [at("2026-02-16T21:04")])

    def test_r_ids_count_on_across_weeks_and_a_new_week_gets_its_page(self):
        self.read([change("Yes")])
        self.read([change("No", ask="A-14", medium="page-14", edited="2026-02-23T05:00")], now="2026-02-23T05:01")
        self.assertIn("| R-2 | A-14 | Your answer | 2026-02-23 11:00 | 2026-02-23 11:01 | page-14 | No |",
                      self.page(desk.ANSWERS / "2026-W09.md"))
        self.assertEqual([row[0] for row in desk.answer_rows(self.root)], [1, 2])

    def test_an_untied_change_is_named_once_in_the_next_hour_s_entry_with_no_model_run(self):
        self.started()
        self.read([change("Yes", editor="the-integration")], now="2026-02-16T14:30")
        self.assertEqual(self.hour("2026-02-16T15:02"), 0)
        self.assertIn("- 20:00-21:00 A change on A-12 I couldn't tie to you: please re-enter it, or answer in the "
                      "chat.\n", self.page())
        self.assertEqual(self.claude_calls(), [])
        self.assertEqual(self.hour("2026-02-16T16:02"), 0)
        self.assertEqual(self.page().count("I couldn't tie to you"), 1)

    def test_an_untied_change_on_an_ask_of_asks_md_is_named_by_its_question_first(self):
        self.put(desk.ASKS, self.page(desk.ASKS).replace(
            "## Open\n\n(none yet)", "## Open\n\n### A-12 · open · b9 · D-20260216-x · asked 2026-02-16 21:00\n\n"
            "- **Question:** Should the launch party move to Friday?\n"))
        self.started()
        self.read([change("Yes", editor="the-integration")], now="2026-02-16T14:30")
        self.assertEqual(self.hour("2026-02-16T15:02"), 0)
        self.assertIn("- 20:00-21:00 A change on your answer to Should the launch party move to Friday? (A-12) I couldn't "
                      "tie to you: please re-enter it, or answer in the chat.\n", self.page())

    def test_the_hour_names_new_and_changed_questions_and_the_stalled_orders(self):
        """Outside the 600 bytes, with no model run: the Q-ids new or changed since the last entry, and the first order
        id of each line `capacity_scan.py --stalled` prints; nothing on a state with no copy of the questions, or while
        the scan has no such flag. Both lines pass the real check."""
        self.put(desk.QA, QA_PAGE)
        desk.save_state(self.root, {k: v for k, v in desk.baseline(self.root, at("2026-02-16T14:00")).items()
                                    if k != "qa"})  # a state with no copy, so no line
        self.assertEqual(self.hour("2026-02-16T15:02"), 0)
        self.assertNotIn("Q&A", self.page())
        self.put(desk.QA, QA_PAGE.replace("### Q-5 · current", "### Q-5 · changed 2026-02-16, see Q-7")
                 + "\n### Q-7 · current · how we work · asked 21:10\n\n- **Your words:** \"And now?\"\n")
        self.put(desk.DIRECTIVES / "D-20260216-the-desk.md", "---\ntitle: The Board's desk\n---\n")
        self.stalled = subprocess.CompletedProcess([], 1, "D-20251212-platform/78: past its deadline (2026-02-16 "
                                                   "18:00Z); D-20260216-the-desk/9 waits on it\n"
                                                   "D-20260216-the-desk/9: no manager alive\n\n", "")
        self.assertEqual(self.hour("2026-02-16T16:02"), 0)
        entry = self.page().split("- 21:00-22:00")[1].split("\n- ")[0]
        self.assertIn("  - Q&A: new answers to \"And now?\" (Q-7) | answers changed on \"How do we keep the orders on "
                      "time?\" (Q-5).\n", entry)  # by the Board's words first
        self.assertIn("  - Stalled orders: D-20251212-platform/78; The Board's desk (D-20260216-the-desk/9)."
                      , entry)  # a directive's title first; the first has no page here, so its id alone
        self.assertEqual(self.claude_calls(), [])
        self.stalled = subprocess.CompletedProcess([], 2, "", "error: unrecognized arguments: --stalled\n")
        self.assertEqual(self.hour("2026-02-16T17:02"), 0)
        self.assertIn("- 22:00-23:00 Nothing happened.", self.page())

    def test_a_change_saved_while_the_hour_runs_is_named_in_the_next(self):
        """A read that saves its state after the hour's run has read it, with a time in the hour just written, is named
        by the next run, not lost to a window."""
        self.started()
        real = desk.untied_lines

        def late(root, named):  # the hour reads the reader's state, then a read lands in that same hour
            found = real(root, named)
            self.read([change("Yes", editor="the-integration")], now="2026-02-16T14:59")
            return found

        with mock.patch.object(desk, "untied_lines", late):
            self.assertEqual(self.hour("2026-02-16T15:00"), 0)
        self.assertNotIn("I couldn't tie to you", self.page())
        self.assertEqual(self.hour("2026-02-16T16:02"), 0)
        self.assertEqual(self.page().count("A change on A-12 I couldn't tie to you"), 1)


class Wait(Checkout):
    """The CEO's watcher (ceo.md, "Keep a watcher"): it exits once an answer no status-log row names is there, and only
    reads."""

    def answer(self, number, ask):
        path = self.root / Reader.WEEK
        if not path.exists():
            self.put(Reader.WEEK, f"---\ntitle: t\nowner: board\n---\n\n{desk.ANSWERS_HEAD}\n")
        with open(path, "a") as file:
            file.write(f"| R-{number} | {ask} | Your answer | 2026-02-17 03:03 | 2026-02-17 03:05 | page-12 | Yes |\n")

    def test_it_waits_then_names_each_answer_and_exits(self):
        sleeps, out = [], io.StringIO()

        def sleep(seconds):
            sleeps.append(seconds)
            self.answer(1, "A-12")
            self.answer(2, "A-13")
        with contextlib.redirect_stdout(out):
            self.assertEqual(desk.wait(self.root, sleep), 0)
        self.assertEqual(sleeps, [20])
        self.assertEqual(out.getvalue(), "R-1: the Board answered A-12\nR-2: the Board answered A-13\n")

    def test_an_answer_a_status_log_row_names_is_handled(self):
        self.answer(31, "A-12")
        self.add_rows("ASK 1 b9 A-12 R-31: taken")

        def sleep(seconds):
            raise StopIteration
        with self.assertRaises(StopIteration):
            desk.wait(self.root, sleep)

    def test_as_a_command(self):
        self.answer(31, "A-12")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(desk.main(["wait", "--root", str(self.root)]), 0)
        self.assertEqual(out.getvalue(), "R-31: the Board answered A-12\n")


class Seal(Checkout):
    """Each change to the Board's answers or the reader's files made outside the desk is an ANSWERS TAMPERED line at the
    next read and in the hour's entry and wait's output; the hourly check against Notion names a row Notion doesn't hold
    even with the seal made to agree; the desk's own writes, the 10:00 run (Day, Directives), a week's rollover, the
    Board's later edit and a failed Notion read raise none. The seal is in a temporary folder (setUpModule)."""

    WEEK = Reader.WEEK
    R1 = "| R-1 | A-12 | Your answer | 2026-02-17 03:03 | 2026-02-17 03:05 | page-12 | Yes |"
    R2 = "| R-2 | A-13 | Your answer | 2026-02-17 03:03 | 2026-02-17 03:05 | page-13 | Later |"
    ADDED = "| R-3 | A-99 | Your answer | 2026-02-17 03:04 | 2026-02-17 03:05 | page-99 | Spend it |"
    NOTION = [change("Yes"), change("Later", ask="A-13", medium="page-13"),
              change("Maybe", editor="the-integration", ask="A-15", medium="page-15")]  # Notion's rows, read at 21:05

    def setUp(self):
        super().setUp()
        desk.save_state(self.root, {"board": "board-user"}, desk.READER)
        desk.adapter_notion.save_ids(self.root, {"bot": "bot-1", "rows": {}, "databases": {}})
        self.read(list(self.NOTION))  # R-1 and R-2; A-15's change logged, another editor's

    def read(self, *polls, now="2026-02-16T21:05", code=0):
        adapter = FakeAdapter(*polls)
        self.assertEqual(desk.read_board(self.root, adapter, at(now)), code)
        return adapter

    def alarms(self):
        return desk.answers_seal.report(self.root)[0]

    def edit(self, rel, old, new):
        path = self.root / rel
        text = path.read_text()
        self.assertIn(old, text)
        path.write_text(text.replace(old, new))

    def forge_seal(self):
        """The seal made to agree with the files as they are: no alarm ended, no row set aside, as the Board's seal or
        clear would."""
        desk.answers_seal.save(self.root, desk.answers_seal.snapshot(self.root))

    def test_each_plain_write_is_caught_at_the_next_read(self):
        """A row added, its words, R-id or ask id changed, a row deleted, a file deleted or replaced, and the reader's
        state, its copy of the desk's ids or its log edited or deleted. A changed state or copy of the ids is read with
        the ids the seal keeps: the Board's answer at 21:06 is kept all the same."""
        cases = [("a row added", lambda: self.edit(self.WEEK, self.R2, self.R2 + "\n" + self.ADDED),
                  ["R-3: added outside the reader (2026-W08.md, ask A-99)"], 0),
                 ("its words changed", lambda: self.edit(self.WEEK, "| page-12 | Yes |", "| page-12 | No |"),
                  ["R-1: its words or other cells changed"], 0),
                 ("its R-id changed", lambda: self.edit(self.WEEK, "| R-1 |", "| R-7 |"),
                  ["R-7: its R-id changed: the reader wrote it as R-1"], 0),
                 ("its ask id changed", lambda: self.edit(self.WEEK, "| R-1 | A-12 |", "| R-1 | A-14 |"),
                  ["R-1: its ask id changed from A-12 to A-14"], 0),
                 ("a row deleted", lambda: self.edit(self.WEEK, self.R1 + "\n", ""), ["R-1: deleted"], 0),
                 ("a file deleted", lambda: (self.root / self.WEEK).unlink(), ["R-1: deleted", "R-2: deleted"], 0),
                 ("a file replaced", lambda: self.put(self.WEEK, f"---\ntitle: t\n---\n\n{desk.ANSWERS_HEAD}\n{self.R1}\n"),
                  ["2026-W08.md: its text outside the rows changed", "R-2: deleted"], 0),
                 ("a row's line with text before it", lambda: self.edit(self.WEEK, self.R1, " " + self.R1),
                  ["R-1: its words or other cells changed"], 0),
                 ("the reader's state edited", lambda: self.edit(desk.READER, '"board-user"', '"someone-else"'),
                  ["reader.json: changed outside the desk"], 0),
                 ("the reader's state deleted", lambda: (self.root / desk.READER).unlink(),
                  ["reader.json: changed outside the desk"], 0),  # the desk's write since, from the seal's ids
                 ("its copy of the desk's ids edited", lambda: self.edit(desk.adapter_notion.IDS, '"bot-1"', '"bot-2"'),
                  ["notion.json: changed outside the desk"], 0),
                 ("its log edited", lambda: self.edit(desk.READER_LOG, "another editor", "the Board"),
                  ["reader-log.jsonl: changed outside the desk"], 0),
                 ("its log deleted", lambda: (self.root / desk.READER_LOG).unlink(), ["reader-log.jsonl: deleted"], 0),
                 ("a row hidden after a lone CR", lambda: self.edit(self.WEEK, self.R1, self.R1 + "\r" + self.ADDED),
                  ["R-3: added outside the reader (2026-W08.md, ask A-99)"], 0),  # its readers split there too
                 ("a row there twice", lambda: self.edit(self.WEEK, self.R1, self.R1 + "\n" + self.R1),
                  ["R-1: there 2 times (2026-W08.md, 2026-W08.md)"], 0),
                 ("a row moved to a page made outside the reader", self.move_r1,
                  ["R-1: moved from 2026-W08.md to 2026-W07.md", "2026-W07.md: made outside the reader"], 0),
                 ("its copy of the desk's ids deleted", lambda: (self.root / desk.adapter_notion.IDS).unlink(),
                  ["notion.json: deleted"], 0),
                 ("its log made outside the desk", self.make_log, ["reader-log.jsonl: made outside the desk"], 0)]
        for name, tamper, lines, code in cases:
            with self.subTest(name):
                self.setUp()
                self.assertEqual(self.alarms(), [])
                tamper()
                self.read([change("Yes", ask="A-20", medium="page-20", edited="2026-02-16T21:06")], now="2026-02-16T21:07",
                          code=code)
                self.assertEqual(self.alarms(), [f"ANSWERS TAMPERED {line}" for line in lines])
                self.assertEqual(any(row[1] == "A-20" for row in desk.answer_rows(self.root)), not code)  # stopped: no read

    def move_r1(self):
        self.edit(self.WEEK, self.R1 + "\n", "")
        self.put(desk.ANSWERS / "2026-W07.md", f"---\ntitle: t\n---\n\n{desk.ANSWERS_HEAD}\n{self.R1}\n")

    def make_log(self):
        (self.root / desk.READER_LOG).unlink()
        desk.answers_seal.reseal(self.root)
        self.read(list(self.NOTION), now="2026-02-16T21:06")  # the check against Notion a seal calls for, done
        self.put(desk.READER_LOG, '{"why": "made up"}\n')

    def test_a_page_deleted_with_nothing_to_write_is_named_with_its_rows(self):
        (self.root / self.WEEK).unlink()
        self.read([], now="2026-02-16T21:07")
        self.assertEqual(self.alarms(), ["ANSWERS TAMPERED 2026-W08.md: deleted, with 2 rows (R-1 to R-2)"])

    def test_the_hourly_check_names_a_row_notion_lacks_and_words_no_row_has(self):
        """With the seal made to agree: a row the CEO hasn't acted on whose field Notion doesn't hold, and the Board's
        words in Notion that no row has (kept now as a new R-row, the alarm standing)."""
        self.edit(self.WEEK, self.R2, self.R2 + "\n" + self.ADDED)
        self.forge_seal()
        self.read(list(self.NOTION) + [change("Go", ask="A-30", medium="page-30", edited="2026-02-16T20:00")],
                  now="2026-02-16T21:07")
        self.assertEqual(self.alarms(), [
            "ANSWERS TAMPERED A-30 Your answer: Notion holds words of the Board's no answers row has (Notion read "
            "2026-02-17 03:07 Dhaka)",
            "ANSWERS TAMPERED R-3: Notion holds no Your answer on A-99 (Notion read 2026-02-17 03:07 Dhaka)"])
        self.assertEqual(desk.capacity_scan.unhandled_answers(self.root / desk.ANSWERS, self.root / desk.DIRECTIVES),
                         [("R-1", "A-12"), ("R-2", "A-13"), ("R-4", "A-30")])

    def test_a_row_deleted_in_notion_raises_none_and_one_notion_lacks_does(self):
        """A row whose Notion row the Board deleted (in Notion's trash, read by its page) is one plain line and stays an
        answer; one Notion holds no row for is named."""
        self.edit(self.WEEK, self.R2, self.R2 + "\n" + self.ADDED)
        self.forge_seal()
        for where, alarms in ((True, []), (None, [
                "ANSWERS TAMPERED R-3: Notion holds no Your answer on A-99 (Notion read 2026-02-17 03:07 Dhaka)"])):
            with self.subTest(where):
                adapter, asked = FakeAdapter(list(self.NOTION)), []
                adapter.in_trash = lambda row, *row_s: asked.append((row, *row_s)) or where
                with mock.patch.object(desk, "say") as said:
                    self.assertEqual(desk.read_board(self.root, adapter, at("2026-02-16T21:07")), 0)
                self.assertEqual((asked, self.alarms()), ([("page-99", "A-99", "Your answer", "Spend it")], alarms))
                self.assertEqual(any("R-3's row is in Notion's trash" in str(call) for call in said.call_args_list),
                                 bool(where))
                self.assertEqual(("R-3", "A-99") in desk.capacity_scan.unhandled_answers(
                    self.root / desk.ANSWERS, self.root / desk.DIRECTIVES), bool(where))  # an answer, or flagged
                desk.answers_seal.reseal(self.root)

    def test_a_check_reads_at_most_trash_reads_pages_the_rest_named(self):
        """The GETs for open rows Notion's read lacks are capped a check (each holds the reader's lock); a row past the
        cap is named without one."""
        other = "| R-4 | A-98 | Your answer | 2026-02-17 03:04 | 2026-02-17 03:05 | page-98 | Spend more |"
        self.edit(self.WEEK, self.R2, self.R2 + "\n" + self.ADDED + "\n" + other)
        self.forge_seal()
        adapter, asked = FakeAdapter(list(self.NOTION)), []
        adapter.in_trash = lambda row, *row_s: asked.append(row) or True
        with mock.patch.object(desk, "TRASH_READS", 1):
            self.assertEqual(desk.read_board(self.root, adapter, at("2026-02-16T21:07")), 0)
        self.assertEqual((asked, self.alarms()), (["page-99"], [
            "ANSWERS TAMPERED R-4: Notion holds no Your answer on A-98 (Notion read 2026-02-17 03:07 Dhaka)"]))
        self.assertEqual(desk.TRASH_READS, 10)

    def test_an_alarm_is_first_seen_when_its_check_runs(self):
        """The first sighting a clear compares with is the time check() ran, not the read's start."""
        self.edit(self.WEEK, "| page-12 | Yes |", "| page-12 | No |")
        ticks = iter([0.0])  # the read's start, then 90 s on
        with mock.patch.object(desk.time, "monotonic", side_effect=lambda: next(ticks, 90.0)):
            self.read([], now="2026-02-16T21:07")
        self.assertEqual(desk.answers_seal.load(self.root)["seen"],
                         {"R-1|its words or other cells changed": "2026-02-16T21:08:30+00:00"})

    def test_a_check_that_fails_any_way_or_is_late_is_not_checked(self):
        """A full read that fails another way than Notion's (its error's name only), and no check against Notion within
        two hours (the reader stopped), are NOT CHECKED lines too."""
        class Broken:
            def poll(self, since):
                raise KeyError("databases")
        desk.answers_seal.reseal(self.root)
        with self.assertRaises(KeyError):
            desk.read_board(self.root, Broken(), at("2026-02-16T21:07"))
        self.assertEqual(desk.answers_seal.report(self.root), ([], set(), (
            "ANSWERS NOT CHECKED at 2026-02-17 03:07 Dhaka: Notion's read failed (KeyError); last checked "
            "2026-02-17 03:05 Dhaka")))
        self.setUp()
        self.assertEqual(desk.answers_seal.report(self.root, at("2026-02-16T23:04"))[2], "")
        self.assertEqual(desk.answers_seal.report(self.root, at("2026-02-16T23:06"))[2],
                         "ANSWERS NOT CHECKED at 2026-02-17 05:06 Dhaka: no check against Notion since 2026-02-17 "
                         "03:05 Dhaka")

    def test_the_alarm_is_in_the_hour_s_entry_and_wait_s_output_and_never_an_answer(self):
        self.add_rows("ASK 1 b9 A-12 R-1: taken", "ASK 1 b9 A-13 R-2: taken")
        self.edit(self.WEEK, self.R2, self.R2 + "\n" + self.ADDED)
        self.started()
        self.assertEqual(self.hour("2026-02-16T15:02"), 0)
        self.assertIn("ANSWERS TAMPERED R-3: added outside the reader (2026-W08.md, ask A-99)\n", self.page())
        out, sleeps = io.StringIO(), []

        def sleep(seconds):  # a second change while it waits: one there at its start doesn't end it, a new one does
            sleeps.append(seconds)
            self.edit(self.WEEK, self.R2 + "\n", "")
        with contextlib.redirect_stdout(out):
            self.assertEqual(desk.wait(self.root, sleep), 0)
        self.assertEqual(sleeps, [20])
        self.assertEqual(out.getvalue(), "ANSWERS TAMPERED R-3: added outside the reader (2026-W08.md, ask A-99)\n"
                                         "ANSWERS TAMPERED R-2: deleted\n")  # never "R-3: the Board answered A-99"
        self.assertEqual(desk.capacity_scan.unhandled_answers(self.root / desk.ANSWERS, self.root / desk.DIRECTIVES),
                         [])
        self.assertEqual(desk.capacity_scan.unhandled_answers(self.root / desk.ANSWERS, self.root / desk.DIRECTIVES,
                                                              keep_flagged=True), [("R-3", "A-99")])

    def test_the_hourly_check_names_rows_notion_doesn_t_hold_with_the_seal_made_to_agree(self):
        """The rows and the seal both changed: the next read reads Notion whole and names each row not as Notion holds
        it; the Board's own words come back as a new R-row, and what another editor holds in Notion stays out,
        unsaid."""
        self.edit(self.WEEK, "| page-12 | Yes |", "| page-12 | No |")
        unseen = "| R-3 | A-16 | Your answer | 2026-02-17 03:04 | 2026-02-17 03:05 | page-16 | Spend it |"
        self.edit(self.WEEK, self.R2, self.R2 + "\n" + unseen)
        self.forge_seal()
        self.assertEqual(self.alarms(), [])
        notion = self.NOTION + [change("", editor="bot-1", ask="A-16", medium="page-16", edited="2026-02-16T20:00")]
        self.assertEqual(self.read(list(notion), now="2026-02-16T21:07").since, [None])
        self.assertEqual(self.alarms(), [
            "ANSWERS TAMPERED R-1: its words aren't what Notion holds in Your answer on A-12 (Notion read 2026-02-17 "
            "03:07 Dhaka)",
            "ANSWERS TAMPERED R-3: its words aren't what Notion holds in Your answer on A-16 (Notion read 2026-02-17 "
            "03:07 Dhaka)"])
        self.assertEqual(desk.answers_seal.report(self.root)[1], {"R-1", "R-3"})
        rows = desk.answer_rows(self.root)
        self.assertEqual((len(rows), rows[-1]), (4, (4, "A-12", "Your answer", "page-12", "Yes")))
        self.assertEqual([ask for ask, _ in desk.load_state(self.root, desk.READER)["untied"]], ["A-15"])
        self.assertEqual(self.read([], now="2026-02-16T21:09").since, [at("2026-02-16T21:06")])  # once an hour
        alarms = self.alarms()
        self.assertEqual(self.read(list(notion), now="2026-02-16T22:08").since, [None])  # R-4 now agrees with Notion
        self.assertEqual(self.alarms(), alarms)  # standing, with the read that found each, until the Board seals
        self.assertEqual(desk.answers_seal.report(self.root)[1], {"R-1", "R-3"})

    def test_each_row_the_hourly_check_names_gets_notion_s_edit_time_and_editor_in_the_log(self):
        """Each row named, one log line with Notion's edit time of its row, as Notion gives it, and its last editor as
        the Board, the desk or another editor (Notion's row for a field it lacks, from another field of it; none for a
        row it lacks); the alarms as before. No id, name or email in the log: the extra keys are what a user object
        could carry, were an adapter ever to pass them on."""
        member = "0c0c0000-0000-4000-8000-000000000003"
        self.edit(self.WEEK, "| page-12 | Yes |", "| page-12 | No |")
        added = ["| R-3 | A-16 | Your answer | 2026-02-17 03:04 | 2026-02-17 03:05 | page-16 | Spend it |",
                 "| R-4 | A-18 | Your answer | 2026-02-17 03:04 | 2026-02-17 03:05 | page-18 | Wait |",
                 "| R-5 | A-13 | Your words | 2026-02-17 03:04 | 2026-02-17 03:05 | page-13 | Soon |",
                 "| R-6 | A-99 | Your answer | 2026-02-17 03:04 | 2026-02-17 03:05 | page-99 | Spend |"]
        self.edit(self.WEEK, self.R2, "\n".join([self.R2] + added))
        self.forge_seal()
        other = {**change("Go on", editor=member, ask="A-18", medium="page-18", edited="2026-02-16T20:01"),
                 "editor_name": "Jane Roe", "editor_email": "jane@example.com"}
        notion = self.NOTION + [change("", editor="bot-1", ask="A-16", medium="page-16", edited="2026-02-16T20:00"),
                                other, change("Go", ask="A-30", medium="page-30", edited="2026-02-16T20:02")]
        said = []
        with mock.patch.object(desk, "say", said.append):
            self.assertEqual(self.read(list(notion), now="2026-02-16T21:07").since, [None])
        head = "checked against Notion: "
        self.assertEqual([line for line in said if line.startswith(head) and "not as Notion holds" not in line], [
            head + "R-1: its row in Notion last edited at 2026-02-16T21:03:00Z by the Board",
            head + "R-3: its row in Notion last edited at 2026-02-16T20:00:00Z by the desk",
            head + "R-4: its row in Notion last edited at 2026-02-16T20:01:00Z by another editor",
            head + "A-30 Your answer: its row in Notion last edited at 2026-02-16T20:02:00Z by the Board",
            head + "R-5: its row in Notion last edited at 2026-02-16T21:03:00Z by the Board",
            head + "R-6: no field of its row in Notion's read: no edit time or editor"])
        self.assertIn(head + "6 not as Notion holds them", said)
        read = " (Notion read 2026-02-17 03:07 Dhaka)"
        self.assertEqual(self.alarms(), [f"ANSWERS TAMPERED {line}{read}" for line in (
            "R-1: its words aren't what Notion holds in Your answer on A-12",
            "R-3: its words aren't what Notion holds in Your answer on A-16",
            "R-4: its words aren't what Notion holds in Your answer on A-18",
            "A-30 Your answer: Notion holds words of the Board's no answers row has",
            "R-5: Notion holds no Your words on A-13", "R-6: Notion holds no Your answer on A-99")])
        log = "\n".join(said)
        for kept_out in ("board-user", "bot-1", member, "Jane", "Roe", "@"):
            self.assertNotIn(kept_out, log)

    def test_only_a_time_parse_time_reads_goes_in_the_log_as_its_utc_iso_form(self):
        """An edit time is written only as parse_time() reads it, in UTC; any other value, whatever it holds, as "?".
        Both routes: a row named with Notion's change, and a field Notion lacks, whose row's time comes from another
        field of it (one audit() never parsed)."""
        head = "checked against Notion: R-2: its row in Notion last edited at "
        cases = [({"name": "Jane Roe", "email": "jane@example.com"}, "?"), ("jane@example.com", "?"),
                 (["2026-02-16T21:03:00Z", "jane@example.com"], "?"), ("not a time", "?"), (None, "?"),
                 ("2026-02-18T09:40:00.000Z", "2026-02-18T09:40:00Z"),
                 ("2026-02-17T03:03:00+06:00", "2026-02-16T21:03:00Z")]
        for edited, shown in cases:
            with self.subTest(edited):
                notion = {**change("Later", ask="A-13", medium="page-13"), "edited_at": edited}
                for found, changes in (([("R-2", "its words aren't what Notion holds", notion)], []),
                                       ([("R-2", "Notion holds no Your words on A-13", None)], [notion])):
                    lines = desk.edit_lines(self.root, found, changes, "board-user", "bot-1")
                    self.assertEqual(lines, [f"{head}{shown} by the Board"])
                    for kept_out in ("Jane", "Roe", "@", "board-user", "bot-1"):
                        self.assertNotIn(kept_out, lines[0])

    def test_notion_is_read_whole_at_most_once_an_hour(self):
        sinces = [self.read([], now=now).since for now in ("2026-02-16T21:07", "2026-02-16T22:04", "2026-02-16T22:05",
                                                           "2026-02-16T22:07")]
        self.assertEqual(sinces, [[at("2026-02-16T21:04")], [at("2026-02-16T21:06")], [None], [at("2026-02-16T22:04")]])

    def test_the_desk_s_own_writes_raise_none(self):
        """Its rows, its log, its state and its ids, then the hour's check."""
        self.read([change("No", edited="2026-02-16T21:05"),
                   change("Hm", editor="the-integration", ask="A-17", medium="page-17", edited="2026-02-16T21:05")],
                  now="2026-02-16T21:07")
        ids = desk.adapter_notion.load_ids(self.root)
        desk.adapter_notion.save_ids(self.root, {**ids, "rows": {"page-12": "A-12"}})
        self.read([change("No", edited="2026-02-16T21:05")] + self.NOTION[1:]
                  + [change("Hm", editor="the-integration", ask="A-17", medium="page-17", edited="2026-02-16T21:05")],
                  now="2026-02-16T22:06")
        self.assertEqual(len(desk.answer_rows(self.root)), 3)
        self.assertEqual(desk.answers_seal.report(self.root), ([], set(), ""))

    def test_a_week_s_rollover_raises_none(self):
        self.read(list(self.NOTION) + [change("No", ask="A-14", medium="page-14", edited="2026-02-23T05:00")],
                  now="2026-02-23T05:01")  # the hour's check, Notion read whole
        self.assertIn("| R-3 | A-14 |", self.page(desk.ANSWERS / "2026-W09.md"))
        self.assertEqual(desk.answers_seal.report(self.root), ([], set(), ""))

    def test_the_board_editing_an_old_answer_raises_none(self):
        later = [change("No", edited="2026-02-16T22:09")] + self.NOTION[1:]
        self.read(list(later), now="2026-02-16T22:10")  # the hour's check, as the Board edits: a new R-row
        self.read(list(later), now="2026-02-16T22:30")
        self.read(list(later), now="2026-02-16T23:15")  # the next hour's, with the edit before its window
        self.assertEqual(desk.answer_rows(self.root)[-1], (3, "A-12", "Your answer", "page-12", "No"))
        self.assertEqual(desk.answers_seal.report(self.root), ([], set(), ""))

    def test_the_hourly_read_names_words_changed_without_a_new_edit_time_and_keeps_notion_s(self):
        """Notion holds new words in a row whose edit time is still the old one, the Board its last editor. The reads
        between, which ask Notion only for rows edited since the last read's minute, get nothing of it; the hourly read
        names the R-row and, the same read, keeps Notion's words as a new one with the same edit time."""
        question = change("The spring menu: soups or salads", ask="Q&A", field="Question", medium="qa-7",
                          edited="2026-02-16T21:06")
        self.read([question], now="2026-02-16T21:07")  # R-3: Edited 03:06, kept 03:07
        self.read(list(self.NOTION) + [question], now="2026-02-16T22:06")  # the hourly check: as Notion holds it
        self.assertEqual(self.alarms(), [])
        self.read([], now="2026-02-16T22:30")  # Notion's words change, its row's edit time not: no row in the window
        late = {**question, "value": question["value"] + "?"}
        self.read(list(self.NOTION) + [late], now="2026-02-16T23:08")
        self.assertEqual(self.alarms(), ["ANSWERS TAMPERED R-3: its words aren't what Notion holds in Question on Q&A "
                                         "(Notion read 2026-02-17 05:08 Dhaka)"])
        self.assertIn("| R-4 | Q&A | Question | 2026-02-17 03:06 | 2026-02-17 05:08 | qa-7 | The spring menu: "
                      "soups or salads? |", self.page(self.WEEK))

    def test_what_the_hourly_check_is_for_still_alarms(self):
        """What the check exists for is named at the hourly read: with the seal made to agree, a row changed outside the
        desk with no Notion edit since (R-1: Notion's edit time its row's own), a row deleted (A-14's: Notion's words no
        row has), a field another editor wrote in Notion since (A-16's), and a row the CEO hasn't acted on whose field
        Notion no longer holds (A-17's); with the seal as the desk wrote it, a row moved."""
        read = " (Notion read 2026-02-17 04:06 Dhaka)"
        other = ["R-4: its words aren't what Notion holds in Your answer on A-16" + read,
                 "R-5: Notion holds no Your answer on A-17" + read]
        cases = [("the seal made to agree", self.change_r1_delete_r3_and_forge_the_seal,
                  ["R-1: its words aren't what Notion holds in Your answer on A-12" + read,
                   "A-14 Your answer: Notion holds words of the Board's no answers row has" + read] + other),
                 ("the seal as the desk wrote it", self.move_r1,
                  ["R-1: moved from 2026-W08.md to 2026-W07.md", "2026-W07.md: made outside the reader"] + other)]
        for name, tamper, alarms in cases:
            with self.subTest(name):
                self.setUp()
                self.read([change("Go", ask=ask, medium=f"page-{ask[2:]}", edited="2026-02-16T21:06")
                           for ask in ("A-14", "A-16", "A-17")], now="2026-02-16T21:07")  # R-3 to R-5
                self.read([], now="2026-02-16T22:04")
                tamper()
                self.read([change("Yes"), self.NOTION[1],
                           change("Go", ask="A-14", medium="page-14", edited="2026-02-16T21:06"),
                           change("Stop", editor="someone-else", ask="A-16", medium="page-16", edited="2026-02-16T21:40"),
                           self.NOTION[2]], now="2026-02-16T22:06")
                self.assertEqual(self.alarms(), [f"ANSWERS TAMPERED {line}" for line in alarms])

    def change_r1_delete_r3_and_forge_the_seal(self):
        self.edit(self.WEEK, "| page-12 | Yes |", "| page-12 | No |")
        self.edit(self.WEEK, "| R-3 | A-14 | Your answer | 2026-02-17 03:06 | 2026-02-17 03:07 | page-14 | Go |\n", "")
        self.forge_seal()

    def test_the_board_s_edit_of_another_field_of_the_row_never_hides_a_changed_row(self):
        """Notion gives a row one edit time, so the Board's answer to A-12 (R-1, 21:03) and its words there (R-3, 21:06)
        both read as edited at 21:06; R-1 changed outside the desk, with the seal made to agree, is still named, whether
        Notion's edit time has seconds or not."""
        for edited_at in ("2026-02-16T21:06:00Z", "2026-02-16T21:06:40Z"):
            with self.subTest(edited_at):
                self.setUp()
                self.read([change("Yes", edited="2026-02-16T21:06"),
                           change("Soon", field="Your words", edited="2026-02-16T21:06")], now="2026-02-16T21:07")
                self.assertEqual(desk.answer_rows(self.root)[-1], (3, "A-12", "Your words", "page-12", "Soon"))
                self.read([], now="2026-02-16T22:04")
                self.edit(self.WEEK, "| page-12 | Yes |", "| page-12 | No |")
                self.forge_seal()
                notion = [{**change("Yes"), "edited_at": edited_at},
                          {**change("Soon", field="Your words"), "edited_at": edited_at}] + self.NOTION[1:]
                self.read(notion, now="2026-02-16T22:06")
                self.assertEqual(self.alarms(), ["ANSWERS TAMPERED R-1: its words aren't what Notion holds in Your "
                                                 "answer on A-12 (Notion read 2026-02-17 04:06 Dhaka)"])

    def test_a_failed_notion_read_is_not_checked_never_a_pass_or_an_alarm(self):
        self.edit(self.WEEK, "| page-12 | Yes |", "| page-12 | No |")
        self.forge_seal()
        self.read(list(self.NOTION), now="2026-02-16T21:07")  # an alarm from Notion, which a failure leaves standing

        class Down:
            def poll(self, since):
                raise desk.adapter_notion.NotionError(503, "service_unavailable")
        with self.assertRaises(desk.adapter_notion.NotionError):
            desk.read_board(self.root, Down(), at("2026-02-16T22:10"))
        unchecked = ("ANSWERS NOT CHECKED at 2026-02-17 04:10 Dhaka: Notion's read failed (Notion 503: "
                     "service_unavailable); last checked 2026-02-17 03:07 Dhaka")
        self.assertEqual(desk.answers_seal.report(self.root), (
            ["ANSWERS TAMPERED R-1: its words aren't what Notion holds in Your answer on A-12 (Notion read 2026-02-17 "
             "03:07 Dhaka)"], {"R-1"}, unchecked))
        self.started()
        self.assertEqual(self.hour("2026-02-16T15:02"), 0)
        self.assertIn(unchecked, self.page())
        self.read([], now="2026-02-16T22:12")  # within the hour of the try: no read of Notion whole again
        self.assertEqual(desk.answers_seal.report(self.root)[2], unchecked)

    def test_a_row_write_cut_short_raises_none(self):
        """A read cut short after it registered its rows, before or after writing them: the next read settles it."""
        real = desk.rewrite

        def after(path, change, now):
            real(path, change, now)
            raise OSError("cut short")
        for cut in (after, mock.Mock(side_effect=OSError("cut short"))):
            with self.subTest(cut):
                self.setUp()
                with mock.patch.object(desk, "rewrite", cut), self.assertRaises(OSError):
                    desk.read_board(self.root, FakeAdapter([change("No", edited="2026-02-16T21:06")]),
                                    at("2026-02-16T21:07"))
                self.assertEqual(self.alarms(), [])
                self.read([change("No", edited="2026-02-16T21:06")], now="2026-02-16T21:09")
                self.assertEqual([row[0] for row in desk.answer_rows(self.root)], [1, 2, 3])
                self.assertEqual(self.alarms(), [])

    def test_only_the_board_seals_and_sealing_ends_the_alarms(self):
        spec = importlib.util.spec_from_file_location("board_desk_bash", SCRIPTS / "hooks" / "board_desk_bash.py")
        guard = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(guard)
        for ceo in (False, True):
            self.assertIsNotNone(guard.desk_reason("python3 scripts/board_desk.py seal", str(REPO), ceo))
        self.edit(self.WEEK, "| page-12 | Yes |", "| page-12 | No |")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(desk.main(["seal", "--root", str(self.root)]), 0)
        self.assertEqual(out.getvalue(), "sealed over: ANSWERS TAMPERED R-1: its words or other cells changed\n")
        self.assertEqual(desk.answers_seal.report(self.root), ([], {"R-1"}, ""))  # set aside
        self.assertEqual(self.read(list(self.NOTION), now="2026-02-16T21:07").since, [None])  # Notion read whole
        self.assertEqual(self.alarms(), [])
        self.assertEqual(desk.answer_rows(self.root)[-1], (3, "A-12", "Your answer", "page-12", "Yes"))  # the Board's

    def test_a_row_whose_alarm_the_board_ended_is_set_aside_never_an_answer(self):
        """A clear ends the alarm, but the R-row it named stays out of the answers: no ANSWER line in the scan, no "the
        Board answered" from wait, not checked against Notion again; the hour's line and the clear row say so; the
        Board's own words in Notion for that field come back as a new R-row, with no alarm."""
        self.edit(self.WEEK, self.R2, self.R2 + "\n" + self.ADDED)  # a forged row: A-99, never asked of the Board
        self.read([], now="2026-02-16T21:07")
        self.assertEqual(self.alarms(), ["ANSWERS TAMPERED R-3: added outside the reader (2026-W08.md, ask A-99)"])
        for text in (desk.tampered_lines(self.root, at("2026-02-16T21:08"))[-1], desk.adapter_notion.CLEAR_QUESTION):
            self.assertIn("couldn't tie to your Notion edits are set aside", text)
            self.assertIn("if one was yours, enter it again", text)
        self.read(self.clear("2026-02-16T21:08"), now="2026-02-16T21:09")
        self.assertEqual(self.alarms(), [])
        self.assertEqual(desk.capacity_scan.unhandled_answers(self.root / desk.ANSWERS, self.root / desk.DIRECTIVES),
                         [("R-1", "A-12"), ("R-2", "A-13")])
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(desk.main(["wait", "--root", str(self.root)]), 0)
        self.assertNotIn("R-3", out.getvalue())
        with mock.patch.object(desk, "say") as said:
            self.read(list(self.NOTION) + [change("Spend less", ask="A-99", medium="page-99",
                                                  edited="2026-02-16T21:00")],
                      now="2026-02-16T22:10")  # the check against Notion: page-99 not open, not named
        self.assertEqual(self.alarms(), [])
        self.assertIn("1 of the Board's read again where the last row was set aside", str(said.call_args_list))
        self.assertEqual(desk.answer_rows(self.root)[-1], (4, "A-99", "Your answer", "page-99", "Spend less"))

    def test_a_field_whose_last_row_was_set_aside_raises_nothing_another_editor_left(self):
        """A row changed in the file, its alarm, the Board's clear; then each full read with another editor (the desk's
        push of the row's other columns) last on that Notion row raises nothing, the row staying set aside; the Board's
        own later edit is a new R-row."""
        self.edit(self.WEEK, "| page-12 | Yes |", "| page-12 | No |")
        self.read([], now="2026-02-16T21:07")
        self.assertEqual(self.alarms(), ["ANSWERS TAMPERED R-1: its words or other cells changed"])
        self.read(self.clear("2026-02-16T21:08"), now="2026-02-16T21:09")
        self.assertEqual(desk.answers_seal.report(self.root), ([], {"R-1"}, ""))
        notion = [change("Yes", editor="bot-1")] + self.NOTION[1:]
        for now in ("2026-02-16T21:11", "2026-02-16T22:12"):
            self.assertEqual(self.read(list(notion), now=now).since, [None])  # read whole each hour
            self.assertEqual(desk.answers_seal.report(self.root), ([], {"R-1"}, ""))
        self.read([change("Yes", edited="2026-02-16T22:13")], now="2026-02-16T22:14")
        self.assertEqual(desk.answer_rows(self.root)[-1], (3, "A-12", "Your answer", "page-12", "Yes"))
        self.assertIn(("R-3", "A-12"), desk.capacity_scan.unhandled_answers(self.root / desk.ANSWERS,
                                                                            self.root / desk.DIRECTIVES))
        self.assertEqual(self.alarms(), [])

    def test_an_unreadable_seal_is_set_aside_and_made_again_holding_no_answer(self):
        """Nothing may hold the Board's answers back: a seal that isn't JSON, or isn't a seal's shape, is set aside
        beside it, made again from the files as they are, and named by an alarm; the read goes on and keeps the Board's
        answer."""
        path, notion = desk.answers_seal.path_of(self.root), list(self.NOTION)
        for n, bad in enumerate(("not json {", "[]", '{"files": {}}', '{"files": {}, "rows": {"x": 1}, "pages": {}}',
                                 '{"files": {}, "rows": {}, "pages": {}, "audit": {"tried": "noon"}}')):
            with self.subTest(bad):
                path.write_text(bad)
                rows = len(desk.answer_rows(self.root))
                notion.append(change("Go", ask=f"A-4{n}", medium=f"page-4{n}", edited=f"2026-02-16T21:1{n}"))
                with mock.patch.object(desk, "say") as said:
                    self.read(list(notion), now=f"2026-02-16T21:1{n}")  # each read after a new seal: Notion whole
                self.assertEqual(len(desk.answer_rows(self.root)), rows + 1)
                set_aside = sorted(path.parent.glob(f"{path.stem}-unreadable-*.json"))
                self.assertEqual((len(set_aside), set_aside[-1].read_text()), (n + 1, bad))
                why = "JSONDecodeError" if n == 0 else "not a seal's shape"
                self.assertIn(f"seal: couldn't be read ({why}); set aside as {set_aside[-1].name}",
                              str(said.call_args_list))
                [alarm] = self.alarms()
                self.assertRegex(alarm, re.escape(f"ANSWERS TAMPERED seal: couldn't be read ({why}): set aside as "
                                                  f"{set_aside[-1].name}, made again from the files as they are (")
                                 + r"\d{4}-\d\d-\d\d \d\d:\d\d Dhaka\)$")
                self.assertIn((f"R-{rows + 1}", f"A-4{n}"), desk.capacity_scan.unhandled_answers(
                    self.root / desk.ANSWERS, self.root / desk.DIRECTIVES))
                desk.answers_seal.reseal(self.root)
                self.assertEqual(self.alarms(), [])

    def test_a_forged_row_reusing_an_id_the_cleanup_trashed_is_named(self):
        """A forged row with the Notion id of a row the 10:00 cleanup moved to Notion's trash, the seal made again, is
        named at the hourly check: the trash counts only for a page the desk didn't trash (notion.json's "trashed",
        sealed with its ids) and the connection didn't last edit."""
        forged = "| R-3 | A-77 | Your answer | 2026-02-17 03:04 | 2026-02-17 03:05 | page-77 | Yes |"

        def trashed_page(editor):
            return {"object": "page", "id": "page-77", "in_trash": True, "archived": True,
                    "last_edited_by": {"object": "user", "id": editor},
                    "parent": {"type": "data_source_id", "data_source_id": "ds-asks"},
                    "properties": {"Id": {"type": "title", "title": [{"plain_text": "A-77"}]},
                                   "Your answer": {"type": "select", "select": {"name": "Yes"}}}}
        for trashed, editor in (({"page-77": "A-77"}, "board-user"), ({}, "bot-1")):
            with self.subTest(editor):
                self.setUp()
                desk.adapter_notion.save_ids(self.root, {
                    "bot": "bot-1", "rows": {"page-77": "A-77"}, "trashed": trashed,
                    "databases": {"asks": {"database": "d1", "data_source": "ds-asks"}}})
                self.edit(self.WEEK, self.R2, self.R2 + "\n" + forged)
                desk.answers_seal.path_of(self.root).unlink()
                fake = FakeNotion()
                fake.queue("GET", "/pages/page-77", trashed_page(editor))
                adapter = FakeAdapter(list(self.NOTION))
                adapter.in_trash = desk.adapter_notion.Desk(self.root, lambda why, data: None, fake).in_trash
                self.assertEqual(desk.read_board(self.root, adapter, at("2026-02-16T22:10")), 0)
                self.assertEqual(self.alarms(), [
                    "ANSWERS TAMPERED R-3: Notion holds no Your answer on A-77 (Notion read 2026-02-17 04:10 Dhaka)"])
                self.assertEqual(fake.calls, [("GET", "/pages/page-77", None)])

    def clear(self, edited, editor="board-user", value="Yes", words=None):
        """The clear row as poll() gives it: Your answer, and Your words if given."""
        row = {"editor": editor, "ask": desk.adapter_notion.CLEAR_ROW, "medium": "clear-row", "edited": edited}
        return [change(value, **row)] + ([] if words is None else [change(words, field="Your words", **row)])

    def test_the_board_clears_the_alarms_in_notion_those_raised_before_its_edit(self):
        """Yes in Your answer on the clear row, Notion naming the Board as its last editor, ends the alarms a read saw
        before that edit, and seals the files as they are; one raised since stands. The same edit again, another
        editor's Yes or the Board's other answer end none; the row is never an answer, and the next read checks Notion
        whole. A later clear needs new words in Your words (the pair acted on is kept), and the R-row an ended alarm
        names is set aside: never an answer, not flagged again, its line the same in the scan and wait."""
        self.add_rows("ASK 1 b9 A-99 R-3: taken")
        self.edit(desk.READER_LOG, "another editor", "the Board")
        self.read([], now="2026-02-16T21:07")
        self.edit(self.WEEK, self.R2, self.R2 + "\n" + self.ADDED)
        with mock.patch.object(desk, "say") as said:
            self.read(self.clear("2026-02-16T21:09"), now="2026-02-16T21:11")  # R-3 first seen after the edit
        added = "ANSWERS TAMPERED R-3: added outside the reader (2026-W08.md, ask A-99)"
        self.assertEqual(self.alarms(), [added])
        self.assertIn("cleared in Notion: the Board picked Yes on \"Answers checked\" at 2026-02-17 03:09 Dhaka: 1 "
                      "ANSWERS TAMPERED lines raised before it ended, their rows set aside, never an answer; 1 raised "
                      "since stand", str(said.call_args_list))
        self.assertEqual(self.read(list(self.NOTION) + self.clear("2026-02-16T21:09"), now="2026-02-16T21:13").since,
                         [None])  # the check against Notion a clear calls for: no alarm from the clear row
        self.read(self.clear("2026-02-16T21:14", editor="someone-else") + self.clear("2026-02-16T21:15",
                                                                                     value="Alternative"),
                  now="2026-02-16T21:16")
        self.read(self.clear("2026-02-16T21:17"), now="2026-02-16T21:18")  # Yes again, no new words: the pair acted on
        self.assertEqual(self.alarms(), [added])
        self.read(self.clear("2026-02-16T21:19", words="looked again"), now="2026-02-16T21:20")
        self.assertEqual(desk.answers_seal.report(self.root), ([], {"R-3"}, ""))
        self.assertEqual([row[1] for row in desk.answer_rows(self.root)], ["A-12", "A-13", "A-99"])
        self.assertNotIn(("R-3", "A-99"), desk.capacity_scan.unhandled_answers(self.root / desk.ANSWERS,
                                                                               self.root / desk.DIRECTIVES))
        self.assertEqual(desk.load_state(self.root, desk.READER).get("untied"), [["A-15", "2026-02-16T21:05:00+00:00"]])

    def test_the_same_words_edited_again_end_nothing(self):
        """A later edit of the clear row (its other columns, or Yes kept) with the same (Your answer, Your words) acts
        on nothing; only new words do, and the row and the hour's line say so."""
        self.read(self.clear("2026-02-16T21:06", words="seen"), now="2026-02-16T21:07")
        self.read(list(self.NOTION), now="2026-02-16T21:08")  # the check against Notion a clear calls for
        self.edit(self.WEEK, "| page-12 | Yes |", "| page-12 | No |")
        self.read([], now="2026-02-16T21:09")
        for later in ("2026-02-16T21:10", "2026-02-16T21:40"):
            self.read(self.clear(later, words="seen"), now="2026-02-16T21:41")
            self.assertEqual(self.alarms(), ["ANSWERS TAMPERED R-1: its words or other cells changed"])
        self.assertIn("type something new in Your words", desk.adapter_notion.CLEAR_QUESTION)
        self.assertIn("type something new in Your words", desk.tampered_lines(self.root, at("2026-02-16T21:42"))[-1])
        self.read(self.clear("2026-02-16T21:43", words="seen twice"), now="2026-02-16T21:44")
        self.assertEqual(self.alarms(), [])

    def test_a_clear_ends_the_hourly_check_s_alarms_raised_before_it(self):
        desk.answers_seal.audited(self.root, at("2026-02-16T21:30"), [("R-1", "its words aren't what Notion holds")])
        desk.answers_seal.audited(self.root, at("2026-02-16T21:40"), [("R-2", "its words aren't what Notion holds")])
        self.assertEqual(desk.answers_seal.clear(self.root, at("2026-02-16T21:35")), (1, 1))
        self.assertEqual(self.alarms(), ["ANSWERS TAMPERED R-2: its words aren't what Notion holds (Notion read "
                                         "2026-02-17 03:40 Dhaka)"])
        self.assertIsNone(desk.answers_seal.clear(self.root, at("2026-02-16T21:35")))  # acted on once
        self.assertEqual(desk.answers_seal.top(self.root), 2)

    def test_a_page_changed_after_the_board_s_edit_stands_through_its_clear(self):
        self.edit(self.WEEK, self.R2, self.R2 + "\nnot a row")
        self.read(self.clear("2026-02-16T21:06"), now="2026-02-16T21:09")  # first seen after the Board's edit
        self.assertEqual(self.alarms(), ["ANSWERS TAMPERED 2026-W08.md: its text outside the rows changed"])
        self.edit(self.WEEK, "\nnot a row", "")
        self.assertEqual(self.alarms(), [])  # put back: the page and its rows as the desk wrote them

    def test_the_clear_row_is_made_once_an_alarm_stands(self):
        """push_desk() makes the Asks row once, after an alarm, with the hook's ids (notion.json)."""
        desk.adapter_notion.save_ids(self.root, {"bot": "bot-1", "rows": {}, "databases": {
            "asks": {"database": "d1", "data_source": "ds-asks"}}})
        fake = FakeNotion()
        fake.queue("POST", "/pages", {"id": "clear-row"})
        notion = desk.adapter_notion.Desk(self.root, lambda why, data: None, fake)
        with mock.patch.dict(desk.adapter_notion.PAGES, clear=True):
            self.assertNotIn("Answers checked", dict(desk.push_desk(self.root, notion, {}, at("2026-02-16T21:06"))))
            self.edit(self.WEEK, "| page-12 | Yes |", "| page-12 | No |")
            outcomes = [dict(desk.push_desk(self.root, notion, {}, at(now))).get("Answers checked")
                        for now in ("2026-02-16T21:07", "2026-02-16T21:09")]
        self.assertEqual(outcomes, ["created", None])
        self.assertEqual(desk.adapter_notion.load_ids(self.root)["rows"], {"clear-row": "Answers checked"})
        self.assertEqual([(method, path) for method, path, _ in fake.calls], [("POST", "/pages")])

    def test_a_changed_state_is_read_with_the_sealed_ids_and_with_none_sealed_stops(self):
        """reader.json changed outside the desk is read with the Board's id the seal keeps, the alarm standing; a seal
        with no ids takes them from the files the desk last wrote; with none, the read stops."""
        self.edit(desk.READER, '"board-user"', '"someone-else"')
        self.read([change("Go", editor="someone-else", ask="A-20", medium="page-20", edited="2026-02-16T21:06"),
                   change("Go", ask="A-21", medium="page-21", edited="2026-02-16T21:06")], now="2026-02-16T21:07")
        self.assertEqual([row[1] for row in desk.answer_rows(self.root)], ["A-12", "A-13", "A-21"])
        self.assertEqual(json.loads((self.root / desk.READER).read_text())["board"], "board-user")
        self.assertEqual(self.alarms(), ["ANSWERS TAMPERED reader.json: changed outside the desk"])
        seal = desk.answers_seal.load(self.root)
        del seal["ids"]
        desk.answers_seal.save(self.root, seal)
        self.read([change("Go", ask="A-22", medium="page-22", edited="2026-02-16T21:08")], now="2026-02-16T21:09",
                  code=1)
        self.assertEqual(len(desk.answer_rows(self.root)), 3)
        desk.answers_seal.reseal(self.root)
        seal = desk.answers_seal.load(self.root)
        del seal["ids"]
        desk.answers_seal.save(self.root, seal)
        self.read([], now="2026-02-16T21:11")
        self.assertEqual(desk.answers_seal.load(self.root)["ids"]["workspaces/board-desk/reader.json"]["board"],
                         "board-user")
        self.assertEqual(desk.answers_seal.load(self.root)["ids"]["workspaces/board-desk/notion.json"]["bot"], "bot-1")


class Install(Checkout):
    """launchctl is mocked and the plist and log go to the temporary checkout: nothing is installed."""

    ENV = {"PATH": "/usr/bin:/bin", "CLAUDE_CONFIG_DIR": "/home/demo/.claude-second"}

    def setUp(self):
        super().setUp()
        for name, value in (("PLIST", self.root / "LaunchAgents" / f"{desk.LABEL}.plist"), ("LOG", self.root / "Logs" / "x.log"),
                            ("READ_PLIST", self.root / "LaunchAgents" / f"{desk.READ_LABEL}.plist"), ("REPO", self.root),
                            ("JOB_ENV", self.ENV), ("macos", lambda command: True)):
            patcher = mock.patch.object(desk, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.launchctl = []

    def call(self, function, main=None):
        def fake(args, **_):
            self.launchctl.append(args)
            return subprocess.CompletedProcess(args, 0)
        out = io.StringIO()
        with mock.patch.object(desk.subprocess, "run", fake), contextlib.redirect_stdout(out), \
                mock.patch.object(desk.capacity_scan, "main_checkout", lambda repo=None: main or self.root):
            return function(), out.getvalue()

    def test_install_writes_an_hourly_job_with_its_environment_and_baselines(self):
        code, _ = self.call(desk.install)
        self.assertEqual(code, 0)
        with open(desk.PLIST, "rb") as file:
            job = plistlib.load(file)
        self.assertEqual(job["StartCalendarInterval"], {"Minute": 0})
        self.assertEqual(job["ProgramArguments"][0], "/usr/bin/python3")
        self.assertEqual(job["ProgramArguments"][2], "run")
        self.assertEqual(job["EnvironmentVariables"], self.ENV)
        self.assertEqual([args[1] for args in self.launchctl], ["bootout", "bootstrap"])
        self.assertIsNotNone(desk.load_state(self.root))

    def test_install_refuses_a_worktree(self):
        code, out = self.call(desk.install, main=self.root / "elsewhere")
        self.assertEqual(code, 2)
        self.assertIn("refused", out)
        self.assertFalse(desk.PLIST.exists())
        self.assertEqual(self.launchctl, [])

    def test_the_reader_s_job_comes_only_once_notion_is_set_up(self):
        _, out = self.call(desk.install)
        self.assertFalse(desk.READ_PLIST.exists())
        self.assertIn("not installed: Notion isn't set up", out)
        ids = {"bot": "b", "pages": {"progress": "p"}, "databases": {}, "rows": {}}  # a setup that stopped part way
        desk.adapter_notion.save_ids(self.root, ids)
        _, out = self.call(desk.install)
        self.assertFalse(desk.READ_PLIST.exists())
        self.assertIn("or its setup stopped part way", out)
        ids.update(pages={key: f"p-{key}" for key in desk.adapter_notion.PAGES},
                   databases={key: {"database": "d", "data_source": "s"} for key in desk.adapter_notion.DATABASES})
        desk.adapter_notion.save_ids(self.root, ids)
        self.launchctl.clear()
        self.call(desk.install)
        with open(desk.READ_PLIST, "rb") as file:
            job = plistlib.load(file)
        self.assertEqual((job["StartInterval"], job["ProgramArguments"][2]), (120, "read"))
        self.assertEqual([args[1] for args in self.launchctl], ["bootout", "bootstrap"] * 2)
        self.call(desk.uninstall)
        self.assertFalse(desk.READ_PLIST.exists() or desk.PLIST.exists())

    def test_uninstall_removes_the_plist(self):
        self.call(desk.install)
        code, out = self.call(desk.uninstall)
        self.assertEqual(code, 0)
        self.assertFalse(desk.PLIST.exists())


class FakeNotion:
    """adapter_notion.Notion's surface, in the tests only: call() answers by (method, path) from queued answers or a
    function, and keeps each call."""

    def __init__(self, people=(("board-user", "The Board"),)):
        self.answers, self.calls, self.persons = {}, [], list(people)

    def queue(self, method, path, *answers):
        self.answers.setdefault((method, path), []).extend(answers)

    def call(self, method, path, body=None, query=None):
        self.calls.append((method, path, body))
        queued = self.answers.get((method, path)) or self.answers.get((method, path.split("/")[1]))
        if not queued:
            raise AssertionError(f"no answer for {method} {path}")
        answer = queued.pop(0) if len(queued) > 1 else queued[0]
        return answer(body) if callable(answer) else answer

    def listed(self, method, path, body=None):
        return self.call(method, path, body)["results"]

    def people(self):
        return self.persons


class Medium(Checkout):
    """board_desk.py's side of the Notion desk (adapter_notion.py has its own tests): every ask heading, everything
    going out whole, the asks as Notion's rows, the pushes' lines in the hour, setup and the attribution test. Nothing
    here calls Notion."""

    ASKS = ("## Open\n\n### A-12 · open · b9 · D-20260216-x · asked 2026-02-16 21:00\n\n- **Question:** Ship it?\n\n"
            "## Closed\n\n### B-9 B+C · answered 2026-02-17 (in chat) · b1 · D-20260216-x · asked 2026-02-17 09:00\n\n"
            "- **Question:** Run the two steps?\n\n"
            "### A-3 · answered 2026-02-17 (in chat) · two-way · D-20260216-x · asked 2026-02-16 09:00\n\n"
            "- **Question:** Three?\n\n"
            "### A-2 · withdrawn 2026-02-17 · b7 · D-20260216-x · asked 2026-02-15 09:00\n\n- **Question:** Two?\n")

    def test_every_ask_heading_form_parses(self):
        self.put(desk.ASKS, self.page(desk.ASKS).replace("## Open\n\n(none yet)\n\n## Closed\n\n(none yet)", self.ASKS))
        self.assertEqual({ask: status for ask, (status, _, _) in desk.asks(self.root).items()},
                         {"A-12": "open", "B-9 B+C": "answered", "A-3": "answered", "A-2": "withdrawn"})
        fields = desk.ask_fields(self.root)
        self.assertEqual(list(fields), ["A-12", "B-9 B+C", "A-3", "A-2"])
        self.assertEqual(fields["B-9 B+C"]["Status"],
                         "answered 2026-02-17 (in chat) · b1 · D-20260216-x · asked 2026-02-17 09:00")
        self.assertEqual(fields["B-9 B+C"]["Question"], "Run the two steps?")
        for ask in ("A-12", "B-9 B+C", "B-7 a", "Note"):
            self.assertTrue(desk.ASKED.fullmatch(ask), ask)
        for ask in ("C-1", "A-", "B-9 ", "A-1 · x", "B-7 a|b", "B-7 a|"):  # a `|` would split the answers row
            self.assertFalse(desk.ASKED.fullmatch(ask), ask)
        self.assertIsNone(desk.ASK_HEADING.match("### B-7 a|b · open · b9 · D-20260216-x · asked 2026-02-16 21:00"))

    def test_every_ask_and_page_goes_out_whole(self):  # names, addresses and domains included
        self.put(desk.ASKS, self.page(desk.ASKS).replace(
            "## Open\n\n(none yet)", "## Open\n\n### A-12 · open · b9 · D-20260216-x · asked 2026-02-16 21:00\n\n"
            "- **Question:** Write to Acme Bakery at ops@acme.example, from acme.test?\n"))
        desk.adapter_notion.save_ids(self.root, {"bot": "bot-1", "root": "root-0", "pages": {"progress": "p-1"},
                                                 "rows": {}, "databases": {"asks": {"database": "d1",
                                                                                    "data_source": "ds-asks"}}})
        self.put(desk.PROGRESS, self.page(desk.PROGRESS) + "\nZed of Acme Bakery, at help@acme.example.\n")
        fake, sent = FakeNotion(), []
        fake.queue("GET", "/pages/p-1", {"last_edited_by": {"id": "bot-1"}, "last_edited_time": "2026-02-16T14:00:00Z"})
        fake.queue("PATCH", "/pages/p-1/markdown", lambda body: sent.append(body) or {})
        fake.queue("POST", "/pages", lambda body: sent.append(body) or {"id": "row-new"})
        notion = desk.adapter_notion.Desk(self.root, lambda why, data: None, fake)
        outcomes = dict(desk.push_desk(self.root, notion, {}, at("2026-02-16T14:05")))
        self.assertEqual((outcomes["A-12"], outcomes["Progress"]), ("created", "pushed"))
        text = json.dumps(sent, ensure_ascii=False)
        for whole in ("Write to Acme Bakery at ops@acme.example, from acme.test?", "Zed of Acme Bakery, at help@acme.example."):
            self.assertIn(whole, text)

    def test_an_ask_s_lines_become_its_row_s_fields_the_board_s_left_out(self):
        self.put(desk.ASKS, self.page(desk.ASKS).replace(
            "## Open\n\n(none yet)", "## Open\n\n### A-12 · open · b9 · D-20260216-x · asked 2026-02-16 21:00\n\n"
            "- **Question:** Ship it?\n- **Recommended (yes takes it):** Yes\n- **Alternative:** Wait a week\n"
            "- **Allows and costs:** a deploy. **Undo:** roll back. **Meanwhile:** tests\n"
            "- **Your earlier words it relies on:** \"Go\" (2026-02-02)\n"
            "- **Priority:** 2 this week: the release waits for it\n"
            "- **Your answer:** (in Notion)\n- **Outcome:** \n"))
        self.assertEqual(desk.ask_fields(self.root), {"A-12": {
            "Status": "open · b9 · D-20260216-x · asked 2026-02-16 21:00", "Question": "Ship it?",
            "Recommended": "Yes", "Alternative": "Wait a week",
            "Cost and undo": "a deploy. Undo: roll back. Meanwhile: tests",
            "Details": "- Your earlier words it relies on: \"Go\" (2026-02-02)\n"
                       "- Priority: 2 this week: the release waits for it\n- Outcome: ",
            "State": "1 open", "Priority": "2 this week",  # what the view sorts by
            "Body": "- **Question:** Ship it?\n- **Recommended (yes takes it):** Yes\n- **Alternative:** Wait a week\n"
                    "- **Allows and costs:** a deploy. **Undo:** roll back. **Meanwhile:** tests\n"
                    "- **Your earlier words it relies on:** \"Go\" (2026-02-02)\n"
                    "- **Priority:** 2 this week: the release waits for it\n- **Outcome:** "}})  # the row's page, as
        # asks.md formats it, but the Board's own line

    def test_a_board_step_with_no_question_line_shows_its_step_as_its_question(self):
        """Once migrated the Asks table shows only Question and Status, so a Board step (no Question line) shows its
        Step or Steps line, else its first labelled line with text."""
        self.put(desk.ASKS, self.page(desk.ASKS).replace(
            "## Open\n\n(none yet)", "## Open\n\n### B-1 · open · two-way · D-20260216-x · asked 2026-02-19 09:00\n\n"
            "- **Why:** \n- **Steps:** **Open** the hosting page and press Redeploy.\n- **Done when:** it is green\n\n"
            "### B-2 · open · two-way · D-20260216-x · asked 2026-02-19 09:00\n\n- **Why:** the party moved\n"
            "- **Done when:** it is green\n"))
        fields = desk.ask_fields(self.root)
        self.assertEqual((fields["B-1"]["Question"], fields["B-2"]["Question"]),
                         ("Open the hosting page and press Redeploy.", "the party moved"))

    def test_an_ask_s_state_and_priority_go_to_notion_once_setup_added_their_columns(self):
        """State (open first), Priority and No. are the columns the Asks view sorts by; before setup adds them (ids'
        "migrated"), the push leaves them out, as Notion would refuse them; once it has, every ask is pushed again with
        them. An ask with no Priority line sends none. The table keeps the short columns, and each ask's text goes,
        formatted, in its row's page."""
        self.put(desk.ASKS, self.page(desk.ASKS).replace("## Open\n\n(none yet)\n\n## Closed\n\n(none yet)", self.ASKS
                                                         + "- **Priority:** 1 today, the party is tomorrow\n"))
        ids = {"bot": "bot-1", "root": "root-0", "rows": {}, "pages": {},
               "databases": {"asks": {"database": "d1", "data_source": "ds-asks"}}}
        sent, pages = [], {}
        desk.adapter_notion.save_ids(self.root, ids)
        for migrated in (False, True):
            if migrated:  # setup has run: the rows made stay, the columns are there
                ids = desk.adapter_notion.load_ids(self.root)
                desk.adapter_notion.save_ids(self.root, {**ids, "migrated": [desk.adapter_notion.MIGRATION]})
            fake = FakeNotion()
            fake.queue("POST", "/pages", lambda body: sent.append(body) or {"object": "page", "id": f"row-{len(sent)}"})
            fake.queue("GET", "pages", {"last_edited_by": {"id": "bot-1"}, "last_edited_time": "2026-02-19T09:00:00.000Z",
                                        "properties": {}})
            fake.queue("PATCH", "pages", lambda body: ("properties" in body and sent.append(body)) or {"object": "page"})
            notion = desk.adapter_notion.Desk(self.root, lambda why, data: None, fake)
            state = {} if not migrated else state
            sent.clear()
            outcomes = dict(desk.push_desk(self.root, notion, state, at("2026-02-19T14:05")))
            columns = {body["properties"]["Id"]["title"][0]["text"]["content"]: body["properties"] for body in sent}
            self.assertEqual(set(columns), {"A-12", "B-9 B+C", "A-3", "A-2"}, "every ask pushed, again once migrated")
            rows = desk.adapter_notion.load_ids(self.root)["rows"]
            pages = {rows[path.split("/")[2]]: body for method, path, body in fake.calls if path.endswith("/markdown")}
            if not migrated:
                self.assertEqual(outcomes["A-12"], "created")
                self.assertFalse({"State", "Priority", "No."} & set(columns["A-12"]))
                self.assertEqual(pages, {}, "no page text before setup removed the long columns")
                continue
            self.assertEqual(outcomes["A-12"], "updated")
            self.assertEqual(set(columns["A-2"]), {"Id", "Question", "Status", "State", "Priority", "No."})
            self.assertEqual(set(pages), set(columns))
            self.assertEqual(pages["A-2"]["type"], "replace_content")
            self.assertIn("**Priority:** 1 today, the party is tomorrow", pages["A-2"]["replace_content"]["new_str"])
            sorts = {ask: (props["State"], props["Priority"], props["No."]) for ask, props in columns.items()}
            none = {"select": None}
            self.assertEqual(sorts, {
                "A-12": ({"select": {"name": "1 open"}}, none, {"number": 12}),
                "B-9 B+C": ({"select": {"name": "2 answered"}}, none, {"number": 9}),
                "A-3": ({"select": {"name": "2 answered"}}, none, {"number": 3}),
                "A-2": ({"select": {"name": "3 withdrawn"}}, {"select": {"name": "1 today"}}, {"number": 2})})
        notion = desk.adapter_notion.Desk(self.root, lambda why, data: None, FakeNotion())  # no call queued: none made
        outcomes = dict(desk.push_desk(self.root, notion, state, at("2026-02-19T14:10")))
        self.assertEqual({outcomes[ask] for ask in columns}, {"same"}, "pushed again once, then no more")

    @unittest.skipUnless(os.environ.get("BOARD_DESK_TODAY"), "BOARD_DESK_TODAY names a copy of the live pages")
    def test_today_s_pages_go_out_every_ask_and_page_none_held(self):
        """push_desk with the real adapter, on a fake Notion, over a copy of the live pages (BOARD_DESK_TODAY: a folder
        holding the PAGES', asks.md's and qa.md's paths); every ask is created, every page pushed, every question a
        row."""
        today = Path(os.environ["BOARD_DESK_TODAY"])
        for rel in [desk.ASKS.as_posix(), *(rel for _, rel in desk.adapter_notion.PAGES.values()), desk.QA.as_posix()]:
            self.put(Path(rel), (today / rel).read_text())
        desk.adapter_notion.save_ids(self.root, {
            "bot": "bot-1", "root": "root-0", "rows": {},
            "pages": {key: f"page-{key}" for key in desk.adapter_notion.PAGES},
            "databases": {"asks": {"database": "d1", "data_source": "ds-asks"},
                          "qa": {"database": "d3", "data_source": "ds-qa"}}})
        fake, made = FakeNotion(), []
        for key in desk.adapter_notion.PAGES:
            fake.queue("GET", f"/pages/page-{key}", {"id": f"page-{key}", "last_edited_by": {"id": "bot-1"}})
            fake.queue("PATCH", f"/pages/page-{key}/markdown", {"object": "page_markdown"})
        fake.queue("POST", "/pages", lambda body: made.append(body) or {"id": f"row-{len(made)}"})
        fake.queue("PATCH", "pages", {"object": "page_markdown"})  # a question's body
        notion = desk.adapter_notion.Desk(self.root, lambda why, data: None, fake)
        outcomes = desk.push_desk(self.root, notion, {}, desk.utc_now())
        asks, questions = list(desk.ask_fields(self.root)), list(desk.qa_entries(self.root))
        self.assertTrue(questions)
        self.assertEqual(outcomes, [(ask, "created") for ask in asks]
                         + [(title, "pushed") for title, _ in desk.adapter_notion.PAGES.values()]
                         + [(qid, "created") for qid in questions])
        print(f"\nBOARD_DESK_TODAY: {len(asks)} asks created ({', '.join(asks)}), "
              f"{len(desk.adapter_notion.PAGES)} pages pushed, {len(questions)} questions created "
              f"({', '.join(questions)}), 0 held", file=sys.stderr)

    def test_a_hold_in_an_old_state_is_never_named(self):
        state = {"desk": [["Progress", "held: a word not on the list (line 3)", "2026-02-16T14:05:00+00:00"]]}
        desk.save_state(self.root, state, desk.READER)
        self.assertEqual(desk.untied_lines(self.root, set())[0], [])

    ROW = "row-12"

    def race(self, polls, fresh):
        """read_notion, once per poll, with the real adapter on a fake Notion (the pages aside): A-12's
        row as each poll gives it, then as `fresh` gives it when push_ask reads it again just before its write.
        [the answers rows at each PATCH of the row]."""
        desk.adapter_notion.save_ids(self.root, {
            "bot": "bot-1", "root": "root-0", "pages": {}, "rows": {self.ROW: "A-12"},
            "databases": {"asks": {"database": "d1", "data_source": "ds-asks"},
                          "notes": {"database": "d2", "data_source": "ds-notes"}}})
        desk.save_state(self.root, {"board": "board-user"}, desk.READER)
        self.put(desk.ASKS, self.page(desk.ASKS).replace(
            "## Open\n\n(none yet)", "## Open\n\n### A-12 · open · b9 · D-20260216-x · asked 2026-02-16 21:00\n\n"
            "- **Question:** Ship it?\n"))
        fake, patched = FakeNotion(), []
        fake.queue("POST", "/data_sources/ds-asks/query", *[{"results": rows} for rows in polls])
        fake.queue("POST", "/data_sources/ds-notes/query", {"results": []})
        fake.queue("GET", f"/pages/{self.ROW}", fresh)
        fake.queue("PATCH", f"/pages/{self.ROW}", lambda body: patched.append(desk.answer_rows(self.root)) or fresh)
        with mock.patch.dict(desk.adapter_notion.PAGES, clear=True):
            for minute in range(len(polls)):
                self.assertEqual(desk.read_notion(self.root, at(f"2026-02-16T14:0{5 + 2 * minute}"), fake), 0)
        return patched

    def row(self, editor, answer="", words="", edited="2026-02-16T14:04:00.000Z"):
        return {"object": "page", "id": self.ROW, "last_edited_by": {"object": "user", "id": editor},
                "last_edited_time": edited, "in_trash": False,
                "properties": {"Your answer": {"type": "select", "select": {"name": answer} if answer else None},
                               "Your words": {"type": "rich_text",
                                              "rich_text": [{"plain_text": words}] if words else []}}}

    def test_the_board_s_answer_is_kept_before_its_row_is_written(self):
        """The poll's answer is an R-row before push_ask writes the row, and a value kept as it is counts as settled."""
        answered = self.row("board-user", answer="Yes")
        patched = self.race([[answered]], answered)
        self.assertEqual(patched, [[(1, "A-12", "Your answer", self.ROW, "Yes")]])

    def test_an_answer_written_after_the_poll_holds_the_row_until_it_is_kept(self):
        """Words the Board typed between the poll and the write, in neither the answers nor the refused, leave the row
        unwritten; the next read keeps them, then writes it."""
        late = self.row("board-user", words="One more thing")
        patched = self.race([[], [late]], late)
        self.assertEqual(patched, [[(1, "A-12", "Your words", self.ROW, "One more thing")]], "written once, after")

    def test_a_refused_value_counts_as_settled(self):
        """Words someone else typed are refused (the log, the hour), not an answer; the row is written over them."""
        other = self.row("someone-else", words="Not the Board")
        patched = self.race([[other]], other)
        self.assertEqual(patched, [[]])
        self.assertEqual(desk.load_state(self.root, desk.READER)["refused"][f"{self.ROW}|Your words"][0],
                         "Not the Board")

    def test_a_refused_value_typed_again_after_the_poll_is_read_before_the_row_is_written(self):
        """The Board's same words, typed again between the poll that refused them and the write, carry a later edit
        time; the row waits for the next read, which keeps them."""
        other = self.row("someone-else", words="Not the Board")
        again = self.row("board-user", words="Not the Board", edited="2026-02-16T14:06:00.000Z")
        patched = self.race([[other], [again]], again)
        self.assertEqual(patched, [[(1, "A-12", "Your words", self.ROW, "Not the Board")]], "written once, after")

    def test_read_before_setup_reads_nothing(self):
        self.assertEqual(desk.read_notion(self.root, at("2026-02-16T14:05"), FakeNotion()), 0)
        self.assertFalse((self.root / desk.READER).exists())

    def setup_notion(self, me=None, roots=1):
        fake, made = FakeNotion(), []

        def page(body):
            made.append(("page", desk.adapter_notion.text_of(body["properties"]["title"] | {"type": "title"})))
            return {"id": f"page-{len(made)}"}

        def database(body):
            made.append(("database", body["title"][0]["text"]["content"]))
            return {"id": f"db-{len(made)}", "data_sources": [{"id": f"ds-{len(made)}"}]}

        fake.queue("GET", "/users/me", me or {"object": "user", "id": "bot-1", "type": "bot", "bot": {}})
        fake.queue("POST", "/search", {"results": [{"object": "page", "id": f"root-{n}", "in_trash": False,
                                                    "properties": {"title": {"type": "title", "title": [
                                                        {"plain_text": "Board desk"}]}}} for n in range(roots)]
                                       + [{"object": "page", "id": "other", "properties": {}}]})
        fake.queue("POST", "/pages", page)
        fake.queue("POST", "/databases", database)
        fake.queue("GET", "/views", lambda body: {"results": [  # each database's views, unsorted
            {"object": "view", "id": f"view-{body['database_id']}", "sorts": []},
            {"object": "view", "id": f"other-{body['database_id']}", "sorts": []}]})
        sorted_now = {}  # the view read back after its PATCH holds what the PATCH sent
        fake.queue("PATCH", "views", lambda body: sorted_now.update(body) or {"object": "view"})
        fake.queue("GET", "views", lambda body: {"object": "view", "sorts": sorted_now.get("sorts", [])})
        fake.queue("POST", "data_sources", {"results": []})  # the migration's reads of a table's rows
        fake.queue("GET", "data_sources", {"object": "data_source", "properties": {}})  # ids to names
        return fake, made

    def run_quiet(self, function, *args, main=None, **kwargs):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), \
                mock.patch.object(desk.capacity_scan, "main_checkout", lambda repo=None: main or self.root):
            return function(*args, **kwargs), out.getvalue()

    def test_setup_makes_each_page_and_database_once_under_the_one_shared_page(self):
        fake, made = self.setup_notion()
        code, out = self.run_quiet(desk.setup, self.root, fake)
        self.assertEqual(code, 0)
        self.assertEqual(made, [("page", title) for title, _ in desk.adapter_notion.PAGES.values()]
                         + [("database", "Asks"), ("database", "Notes to the CEO"), ("database", "Q&A"),
                            ("database", "Directives")])
        ids = desk.adapter_notion.load_ids(self.root)
        self.assertEqual(ids["made_with"], {"asks": desk.adapter_notion.MIGRATION, "qa": desk.adapter_notion.MIGRATION})
        self.assertEqual((ids["bot"], ids["root"]), ("bot-1", "root-0"))
        self.assertEqual(ids["databases"]["asks"], {"database": "db-5", "data_source": "ds-5"})
        self.assertEqual(ids["migrated"], [desk.adapter_notion.MIGRATION])  # made with the columns: nothing to add
        self.assertEqual([(path, body) for method, path, body in fake.calls if method == "PATCH"], [
            ("/views/view-db-7", {"sorts": [{"property": "No.", "direction": "descending"}]}),
            ("/views/view-db-5", {"sorts": [{"property": name, "direction": "ascending"}
                                            for name in ("State", "Priority", "No.")]}),
            ("/views/view-db-8", {"sorts": [{"property": "Last updated", "direction": "descending"}]})])
        self.assertEqual(ids["sorted"], ["qa", "asks", "directives"])
        self.assertIn("The Q&A table's views before setup sorts the first: view-db-7 sorted by nothing; other-db-7 "
                      "sorted by nothing.\nThe Q&A table's view view-db-7 is sorted by No. descending, as read back.",
                      out)  # each view's sorts before, for the undo; the view read back after
        self.assertEqual([path for method, path, _ in fake.calls if method == "GET" and path.startswith("/views/")],
                         ["/views/view-db-7", "/views/view-db-5", "/views/view-db-8"])
        asks_columns = next(body for method, path, body in fake.calls if path == "/databases"
                            and body["title"][0]["text"]["content"] == "Asks")["initial_data_source"]["properties"]
        self.assertEqual(set(asks_columns), {"Id", "Question", "Status", "Your answer", "Your words", "State", "Priority",
                                             "No."})  # the short columns; the ask's text in its page
        self.assertEqual({name: asks_columns[name] for name in ("State", "Priority", "No.")},
                         {"State": {"select": {"options": [{"name": "1 open"}, {"name": "2 answered"},
                                                           {"name": "3 withdrawn"}]}},
                          "Priority": {"select": {"options": [{"name": "1 today"}, {"name": "2 this week"},
                                                              {"name": "3 when convenient"}]}},
                          "No.": {"number": {}}})
        parents = {json.dumps(body["parent"]) for method, _, body in fake.calls if method == "POST" and "parent" in body}
        self.assertEqual(parents, {json.dumps({"type": "page_id", "page_id": "root-0"})})
        self.assertIn("board-user  The Board", out)
        self.assertIn("Next: python3 scripts/board_desk.py attribution", out)
        fixed = json.loads((self.root / desk.adapter_notion.FIXED_IDS).read_text())
        self.assertEqual(fixed, {"root": "root-0", "pages": ids["pages"],
                                 "databases": {"asks": {"database": "db-5", "data_source": "ds-5"},
                                               "notes": {"database": "db-6", "data_source": "ds-6"},
                                               "qa": {"database": "db-7", "data_source": "ds-7"},
                                               "directives": {"database": "db-8", "data_source": "ds-8"}}})
        directives = next(body for method, path, body in fake.calls if path == "/databases"
                          and body["title"][0]["text"]["content"] == "Directives")["initial_data_source"]["properties"]
        self.assertEqual(set(directives), {"Directive", "Status", "Last updated", "Your words (verbatim)", "Id"})
        self.assertEqual(directives["Status"], {"select": {"options": [{"name": "Not started"}, {"name": "In progress"},
                                                                       {"name": "Done"}]}})
        qa_columns = next(body for method, path, body in fake.calls if path == "/databases"
                          and body["title"][0]["text"]["content"] == "Q&A")["initial_data_source"]["properties"]
        self.assertNotIn("Answer", qa_columns)  # the answer is in the row's page
        self.assertEqual(qa_columns["No."], {"number": {}})
        self.assertIn(str(desk.adapter_notion.FIXED_IDS), out)  # the CEO commits it
        again, made = self.setup_notion()
        self.assertEqual(self.run_quiet(desk.setup, self.root, again)[0], 0)
        self.assertEqual(made, [])
        self.assertFalse([path for _, path, _ in again.calls if path.startswith("/views")])  # sorted once

    def test_setup_run_again_makes_the_q_and_a_database_once_and_trashes_the_q_and_a_page(self):
        """A desk set up earlier (five pages, a Q&A page among them, two databases, the Board's id recorded) gains the
        Q&A database from setup run again, once, under the reader's lock; the Q&A page, which the database replaces,
        goes to Notion's trash (gone already counts as done); the Asks table, made before, gets its State, Priority and
        No. columns, once."""
        old = {"bot": "bot-1", "root": "root-0", "rows": {"row-1": "A-1"},
               "pages": {key: f"old-{key}" for key in ("progress", "summaries", "company", "product", "qa")},
               "databases": {"asks": {"database": "d1", "data_source": "s1"},
                             "notes": {"database": "d2", "data_source": "s2"}}}
        for gone in (False, True):
            with self.subTest(gone=gone):
                desk.adapter_notion.save_ids(self.root, old)
                desk.save_state(self.root, {"board": "board-user", "since": "2026-02-17T09:00:00+00:00"}, desk.READER)
                fake, made = self.setup_notion()

                def trash(body):
                    if gone:
                        raise desk.adapter_notion.NotionError(404, "object_not_found")
                    return {"id": "old-qa", "in_trash": True}

                fake.queue("PATCH", "/pages/old-qa", trash)
                fake.queue("PATCH", "/data_sources/s1", {"object": "data_source", "id": "s1"})
                locks = []
                real = desk.locked

                @contextlib.contextmanager
                def watched(root, rel=desk.LOCK):
                    with real(root, rel):
                        locks.append(rel)
                        yield

                with mock.patch.object(desk, "locked", watched):
                    code, out = self.run_quiet(desk.setup, self.root, fake)
                self.assertEqual((code, made, locks), (0, [("database", "Q&A"), ("database", "Directives")],
                                                       [desk.READER_LOCK]))
                self.assertIn(("PATCH", "/pages/old-qa", {"in_trash": True}), fake.calls)
                added = [body for method, path, body in fake.calls if path == "/data_sources/s1"]
                self.assertEqual(added, [{"properties": {
                    **{name: desk.adapter_notion.DATABASES["asks"][1][name] for name in ("State", "Priority", "No.")},
                    "Recommended": None, "Alternative": None, "Cost and undo": None, "Details": None}}])
                self.assertIn("The Asks table has its new columns: State, Priority, No.; the columns Recommended, "
                              "Alternative, Cost and undo, Details are removed, their text now in each row's page", out)
                ids = desk.adapter_notion.load_ids(self.root)
                pages = {key: value for key, value in old["pages"].items() if key != "qa"}
                self.assertEqual(ids, {**old, "pages": pages, "migrated": [desk.adapter_notion.MIGRATION],
                                       "made_with": {"qa": desk.adapter_notion.MIGRATION,  # made now: nothing to add
                                                     "asks": desk.adapter_notion.MIGRATION},  # migrated
                                       "sorted": ["qa", "asks", "directives"],
                                       "databases": {**old["databases"],
                                                     "qa": {"database": "db-1", "data_source": "ds-1"},
                                                     "directives": {"database": "db-2", "data_source": "ds-2"}}})
                self.assertNotIn(("POST", "/search"), [(method, path) for method, path, _ in fake.calls])
                fixed = json.loads((self.root / desk.adapter_notion.FIXED_IDS).read_text())
                self.assertEqual((fixed["pages"], fixed["databases"]["qa"]), (pages, ids["databases"]["qa"]))
                self.assertIn("The page \"qa\" is no longer pushed: " + ("already gone from Notion." if gone else
                                                                          "moved to Notion's trash"), out)
                self.assertEqual("trash" in out, not gone)
                self.assertIn("The Board's id is recorded already", out)
                again, made = self.setup_notion()
                self.assertEqual(self.run_quiet(desk.setup, self.root, again)[0], 0)
                self.assertEqual(made, [])
                self.assertNotIn("PATCH", [method for method, *_ in again.calls])

    def test_setup_cut_short_after_making_a_database_adds_no_columns_to_it_when_run_again(self):
        """A database setup made with MIGRATIONS' columns is recorded so in the same save ("made_with"), so a setup
        stopped before it recorded the migration adds no column to it when run again; one made before them still gets
        its own."""
        desk.adapter_notion.save_ids(self.root, {
            "bot": "bot-1", "root": "root-0", "rows": {}, "pages": {key: f"p-{key}" for key in desk.adapter_notion.PAGES},
            "made_with": {"qa": desk.adapter_notion.MIGRATION},
            "databases": {key: {"database": f"d-{key}", "data_source": f"s-{key}"}
                          for key in ("asks", "notes", "qa", "directives")}})
        desk.save_state(self.root, {"board": "board-user", "since": "2026-02-19T09:00:00+00:00"}, desk.READER)
        fake, made = self.setup_notion()
        fake.queue("PATCH", "/data_sources/s-asks", {"object": "data_source", "id": "s-asks"})
        code, out = self.run_quiet(desk.setup, self.root, fake)
        self.assertEqual((code, made), (0, []))
        self.assertEqual([path for method, path, _ in fake.calls if method == "PATCH"],
                         ["/data_sources/s-asks", "/views/view-d-qa", "/views/view-d-asks", "/views/view-d-directives"])
        self.assertNotIn("The Q&A table has its new columns", out)
        self.assertEqual(desk.adapter_notion.load_ids(self.root)["migrated"], [desk.adapter_notion.MIGRATION])

    def migration_fixture(self):
        desk.adapter_notion.save_ids(self.root, {
            "bot": "bot-1", "root": "root-0", "pages": {key: f"p-{key}" for key in desk.adapter_notion.PAGES},
            "rows": {"r-a12": "A-12", "r-a13": "A-13", "r-a14": "A-14", "r-a5": "A-5", "b-row": "Q&A", "r-q3": "Q-3"},
            "databases": {key: {"database": f"d-{key}", "data_source": f"s-{key}"}
                          for key in ("asks", "notes", "qa", "directives")}})
        desk.save_state(self.root, {"board": "board-user", "since": "2026-02-20T09:00:30+00:00"}, desk.READER)
        self.put(desk.ASKS, self.page(desk.ASKS).replace(
            "## Open\n\n(none yet)", "## Open\n\n### A-12 · open · b9 · D-x · asked 2026-02-16 21:00\n\n"
            "- **Question:** Ship it?\n- **Recommended (yes takes it):** Ship it today.\n- **Alternative:** Wait.\n"))
        self.put(desk.DESK / "asks-archive-2026-02.md", "---\ntitle: Asks archive\nowner: ceo\n---\n\n"
                 "# Asks archive\n\n### A-5 · answered 2026-02-10 13:00 · b9 · D-x · asked 2026-02-09 09:00\n\n"
                 "- **Question:** Five?\n- **Recommended (yes takes it):** Do five.\n"
                 "- **Alternative:** Do four.\n")  # an ask moved out of asks.md

        def row(identity, editor, **columns):
            return {"id": identity, "last_edited_by": {"id": editor}, "created_by": {"id": "bot-1"},
                    "last_edited_time": "2026-02-20T08:00:00.000Z",
                    "properties": {name: {"type": "rich_text", "rich_text": [{"plain_text": text}]}
                                   for name, text in columns.items()}}

        return {"asks": [row("r-a12", "board-user", Recommended="Ship it, but on Friday.", Alternative="Wait."),
                         row("r-a13", "bot-1", Recommended="The desk's, last written by it"),
                         row("r-a14", "someone-else", Recommended="Not the Board's"),
                         row("r-a5", "board-user", Recommended="Do five.", Alternative="Do four.")],  # the desk's
                # text of an ask in the archive, the Board its row's last editor: no R-row
                "qa": [{**row("b-row", "board-user", Answer="My note, typed in the Answer column"),
                        "created_by": {"id": "board-user"}},
                       row("r-q3", "board-user", Answer="The CEO's answer, edited")]}

    def test_setup_s_migration_keeps_the_text_of_the_columns_it_removes_and_waits_for_the_reader(self):
        """No table changes while a row of one losing columns changed at or after the minute the reader's last read
        reached back to (printed; setup run again goes on); then each removed column's text in a row the connection
        didn't edit last is kept before the removal: the Board's words as R-rows, word for word (an ask's column as
        asks.md or an archive has it is the desk's, left out), another editor's and a desk's own Q&A row's in the
        reader's log; each table recorded as it completes, so a stop after the first leaves only the second for setup
        run again."""
        rows = self.migration_fixture()
        fake, _ = self.setup_notion()
        recent = {"asks": [], "qa": [rows["qa"][1]]}
        for key in ("asks", "qa"):
            fake.queue("POST", f"/data_sources/s-{key}/query",
                       lambda body, key=key: {"results": recent[key] if body else rows[key]})
        code, out = self.run_quiet(desk.setup, self.root, fake)
        self.assertEqual(code, 0)
        self.assertFalse([path for method, path, _ in fake.calls if method == "PATCH" and "data_sources" in path])
        self.assertIn("The Q&A table isn't changed yet, nor any other: 1 of its rows changed since the reader's last "
                      "read, or the reader hasn't read yet; run setup again after the next read (2 minutes).", out)
        self.assertEqual([body for method, path, body in fake.calls if path == "/data_sources/s-asks/query"], [
            {"filter": {"timestamp": "last_edited_time",
                        "last_edited_time": {"on_or_after": "2026-02-20T08:59:00.000Z"}}}])
        ids = desk.adapter_notion.load_ids(self.root)
        self.assertNotIn("migrated", ids)
        self.assertNotIn("made_with", ids)
        self.assertEqual(desk.answer_rows(self.root), [])
        recent["qa"] = []
        fake, _ = self.setup_notion()
        for key in ("asks", "qa"):
            fake.queue("POST", f"/data_sources/s-{key}/query",
                       lambda body, key=key: {"results": recent[key] if body else rows[key]})
        fake.queue("PATCH", "/data_sources/s-asks", {"object": "data_source"})

        def down(body):
            raise desk.adapter_notion.NotionError(503, "service_unavailable")

        fake.queue("PATCH", "/data_sources/s-qa", down)
        with self.assertRaises(desk.adapter_notion.NotionError):
            self.run_quiet(desk.setup, self.root, fake)
        self.assertEqual([row[1:] for row in desk.answer_rows(self.root)], [
            ("A-12", "Recommended", "r-a12", "Ship it, but on Friday."),
            ("Q&A", "Answer", "b-row", "My note, typed in the Answer column")])
        logged = [json.loads(line) for line in (self.root / desk.READER_LOG).read_text().splitlines()]
        self.assertEqual([(entry["why"], entry["change"]["medium_id"], entry["change"]["value"]) for entry in logged], [
            ("another editor", "r-a14", "Not the Board's"),
            ("a removed column's text in a row of the desk's own Q&A entries", "r-q3", "The CEO's answer, edited")])
        ids = desk.adapter_notion.load_ids(self.root)
        self.assertEqual((ids["made_with"], ids.get("migrated")), ({"asks": desk.adapter_notion.MIGRATION}, None))
        fake, _ = self.setup_notion()
        for key in ("asks", "qa"):
            fake.queue("POST", f"/data_sources/s-{key}/query",
                       lambda body, key=key: {"results": recent[key] if body else rows[key]})
        fake.queue("PATCH", "/data_sources/s-qa", {"object": "data_source"})
        code, out = self.run_quiet(desk.setup, self.root, fake)
        self.assertEqual(code, 0)
        self.assertEqual([path for method, path, _ in fake.calls if method == "PATCH" and "data_sources" in path],
                         ["/data_sources/s-qa"])  # the Asks table's removal isn't sent again
        self.assertIn("the columns Answer are removed, their text now in each row's page (their text kept first: your "
                      "words as no new answer row; other texts to the reader's log: 0)", out)
        self.assertEqual(len(desk.answer_rows(self.root)), 2)  # read again, kept once
        self.assertEqual(len((self.root / desk.READER_LOG).read_text().splitlines()), 2)  # logged once
        ids = desk.adapter_notion.load_ids(self.root)
        self.assertEqual((ids["made_with"], ids["migrated"]), ({"asks": desk.adapter_notion.MIGRATION,
                                                                "qa": desk.adapter_notion.MIGRATION},
                                                               [desk.adapter_notion.MIGRATION]))

    def test_setup_records_a_view_sorted_only_when_it_reads_back_so(self):
        """A view Notion answers the PATCH for but reads back with other sorts is printed, not recorded, and setup run
        again sorts it again."""
        desk.adapter_notion.save_ids(self.root, {
            "bot": "bot-1", "root": "root-0", "rows": {}, "migrated": [desk.adapter_notion.MIGRATION],
            "pages": {key: f"p-{key}" for key in desk.adapter_notion.PAGES},
            "databases": {key: {"database": f"d-{key}", "data_source": f"s-{key}"}
                          for key in ("asks", "notes", "qa", "directives")}})
        desk.save_state(self.root, {"board": "board-user", "since": "2026-02-20T09:00:00+00:00"}, desk.READER)
        fake, _ = self.setup_notion()
        fake.queue("GET", "/views/view-d-qa", {"object": "view", "sorts": [{"property": "%3Aab",
                                                                            "direction": "descending"}]})
        code, out = self.run_quiet(desk.setup, self.root, fake)
        self.assertEqual(code, 0)
        self.assertIn("The Q&A table's view view-d-qa reads back sorted by %3Aab descending, not No. descending; setup "
                      "run again sorts it again.", out)
        self.assertEqual(desk.adapter_notion.load_ids(self.root)["sorted"], ["asks", "directives"])
        again, _ = self.setup_notion()
        self.assertEqual(self.run_quiet(desk.setup, self.root, again)[0], 0)
        self.assertEqual([path for method, path, _ in again.calls if method == "PATCH"], ["/views/view-d-qa"])
        self.assertEqual(desk.adapter_notion.load_ids(self.root)["sorted"], ["asks", "directives", "qa"])

    def test_setup_reads_a_view_s_sorts_back_by_property_id_as_the_column_s_name(self):
        """Notion may read a view's sorts back by property id; the data source's properties map each id to its column's
        name, so the table is recorded sorted and setup never sends the sort again."""
        desk.adapter_notion.save_ids(self.root, {
            "bot": "bot-1", "root": "root-0", "rows": {}, "migrated": [desk.adapter_notion.MIGRATION],
            "pages": {key: f"p-{key}" for key in desk.adapter_notion.PAGES},
            "databases": {key: {"database": f"d-{key}", "data_source": f"s-{key}"}
                          for key in ("asks", "notes", "qa", "directives")}})
        desk.save_state(self.root, {"board": "board-user", "since": "2026-02-20T09:00:00+00:00"}, desk.READER)
        fake, _ = self.setup_notion()
        fake.queue("GET", "/views/view-d-qa", {"object": "view", "sorts": [{"property": "%3Aab",
                                                                            "direction": "descending"}]})
        fake.queue("GET", "/data_sources/s-qa", {"object": "data_source", "properties": {
            "No.": {"id": "%3Aab", "name": "No.", "type": "number"}, "Question": {"id": "title", "type": "title"}}})
        code, out = self.run_quiet(desk.setup, self.root, fake)
        self.assertEqual(code, 0)
        self.assertIn("The Q&A table's view view-d-qa is sorted by No. descending, as read back.", out)
        self.assertEqual(desk.adapter_notion.load_ids(self.root)["sorted"], ["qa", "asks", "directives"])
        self.assertEqual([path for method, path, _ in fake.calls if method == "GET" and "data_sources" in path],
                         ["/data_sources/s-qa"])  # only for a read-back that isn't by name
        again, _ = self.setup_notion()
        self.assertEqual(self.run_quiet(desk.setup, self.root, again)[0], 0)
        self.assertFalse([path for _, path, _ in again.calls if path.startswith("/views")])  # never sent again

    def test_setup_sorts_each_table_s_first_view_once_and_a_refusal_waits_for_setup_run_again(self):
        """Setup sorts the first view of the Q&A, Asks and Directives tables (Notes has none to sort), never another
        view, once, so a sort the Board sets later stays; a 4xx from Notion is printed, setup goes on, and setup run
        again sorts that one alone."""
        desk.adapter_notion.save_ids(self.root, {
            "bot": "bot-1", "root": "root-0", "rows": {}, "migrated": [desk.adapter_notion.MIGRATION],
            "pages": {key: f"p-{key}" for key in desk.adapter_notion.PAGES},
            "databases": {key: {"database": f"d-{key}", "data_source": f"s-{key}"}
                          for key in ("asks", "notes", "qa", "directives")}})
        desk.save_state(self.root, {"board": "board-user", "since": "2026-02-20T09:00:00+00:00"}, desk.READER)
        fake, _ = self.setup_notion()

        def refused(body):
            raise desk.adapter_notion.NotionError(400, "validation_error")

        fake.queue("PATCH", "/views/view-d-asks", refused)
        code, out = self.run_quiet(desk.setup, self.root, fake)
        self.assertEqual(code, 0)
        self.assertEqual([path for method, path, _ in fake.calls if method == "PATCH"],
                         ["/views/view-d-qa", "/views/view-d-asks", "/views/view-d-directives"])
        self.assertEqual([body for _, path, body in fake.calls if path == "/views"],
                         [{"database_id": "d-qa"}, {"database_id": "d-asks"}, {"database_id": "d-directives"}])
        self.assertIn("The Asks table's view is not sorted: Notion answered 400 (validation_error); setup run again "
                      "tries again.", out)
        self.assertIn("The Directives table's view view-d-directives is sorted by Last updated descending, as read "
                      "back.", out)
        self.assertIn("Notion is set up", out)  # the rest of setup went on
        self.assertEqual(desk.adapter_notion.load_ids(self.root)["sorted"], ["qa", "directives"])
        again, _ = self.setup_notion()
        self.assertEqual(self.run_quiet(desk.setup, self.root, again)[0], 0)
        self.assertEqual([(path, body) for method, path, body in again.calls if path.startswith("/views")], [
            ("/views", {"database_id": "d-asks"}),
            ("/views/view-d-asks", {"sorts": [{"property": "State", "direction": "ascending"},
                                              {"property": "Priority", "direction": "ascending"},
                                              {"property": "No.", "direction": "ascending"}]}),
            ("/views/view-d-asks", None)])  # read back
        self.assertEqual(desk.adapter_notion.load_ids(self.root)["sorted"], ["qa", "directives", "asks"])
        once, _ = self.setup_notion()
        self.assertEqual(self.run_quiet(desk.setup, self.root, once)[0], 0)
        self.assertFalse([path for _, path, _ in once.calls if path.startswith("/views")])

    def test_setup_leaves_a_table_without_a_view_in_notion_s_answer_unsorted_and_a_5xx_stops_it(self):
        """No view listed, or one listed without its id, is printed and left for setup run again, the rest of setup
        going on; a 5xx stops setup, as the migration's does."""
        desk.adapter_notion.save_ids(self.root, {
            "bot": "bot-1", "root": "root-0", "rows": {}, "migrated": [desk.adapter_notion.MIGRATION],
            "pages": {key: f"p-{key}" for key in desk.adapter_notion.PAGES},
            "databases": {key: {"database": f"d-{key}", "data_source": f"s-{key}"}
                          for key in ("asks", "notes", "qa", "directives")}})
        desk.save_state(self.root, {"board": "board-user", "since": "2026-02-20T09:00:00+00:00"}, desk.READER)
        fake, _ = self.setup_notion()
        fake.answers[("GET", "/views")] = [lambda body: {"results": {
            "d-qa": [], "d-asks": [{"object": "view", "name": "no id"}]}.get(
            body["database_id"], [{"object": "view", "id": f"view-{body['database_id']}"}])}]
        code, out = self.run_quiet(desk.setup, self.root, fake)
        self.assertEqual(code, 0)
        self.assertEqual([path for method, path, _ in fake.calls if method == "PATCH"], ["/views/view-d-directives"])
        for title in ("Q&A", "Asks"):
            self.assertIn(f"The {title} table has no view to sort in Notion's answer; setup run again tries again.",
                          out)
        self.assertIn("Notion is set up", out)
        self.assertEqual(desk.adapter_notion.load_ids(self.root)["sorted"], ["directives"])
        failing, _ = self.setup_notion()

        def down(body):
            raise desk.adapter_notion.NotionError(503, "service_unavailable")

        failing.queue("PATCH", "/views/view-d-qa", down)
        with self.assertRaises(desk.adapter_notion.NotionError):
            self.run_quiet(desk.setup, self.root, failing)
        self.assertEqual(desk.adapter_notion.load_ids(self.root)["sorted"], ["directives"])

    def test_setup_trashes_the_pages_no_longer_shown_and_the_read_pushes_nothing_for_them(self):
        """Two pages PAGES no longer has: setup moves both to Notion's trash, once, and the read pushes nothing for
        them, though their KB pages stay."""
        old = {"bot": "bot-1", "root": "root-0", "rows": {}, "migrated": [desk.adapter_notion.MIGRATION],
               "pages": {"progress": "p1", "summaries": "p2", "company": "p3", "product": "p4", "steps": "p5",
                         "steps-two": "p6"},
               "databases": {key: {"database": f"d-{key}", "data_source": f"s-{key}"} for key in ("asks", "notes", "qa")}}
        desk.adapter_notion.save_ids(self.root, old)
        desk.save_state(self.root, {"board": "board-user", "since": "2026-02-19T09:00:00+00:00"}, desk.READER)
        fake, made = self.setup_notion()
        fake.queue("PATCH", "/pages/p5", {"id": "p5", "in_trash": True})
        fake.queue("PATCH", "/pages/p6", {"id": "p6", "in_trash": True})
        code, out = self.run_quiet(desk.setup, self.root, fake)
        self.assertEqual((code, made), (0, [("database", "Directives")]))  # made once
        self.assertEqual([(path, body) for method, path, body in fake.calls if method == "PATCH"
                          and not path.startswith("/views/")],  # the views' sorts have their own test
                         [("/pages/p5", {"in_trash": True}), ("/pages/p6", {"in_trash": True})])
        self.assertIn("The page \"steps\" is no longer pushed: moved to Notion's trash", out)
        self.assertIn("The page \"steps-two\" is no longer pushed: moved to Notion's trash", out)
        ids = desk.adapter_notion.load_ids(self.root)
        self.assertEqual(ids["pages"], {"progress": "p1", "summaries": "p2", "company": "p3", "product": "p4"})
        again, made = self.setup_notion()
        self.assertEqual((self.run_quiet(desk.setup, self.root, again)[0], made), (0, []))
        self.assertNotIn("PATCH", [method for method, *_ in again.calls])
        for name in ("steps.md", "steps-two.md"):
            self.put(desk.DESK / name, "---\ntitle: Steps\n---\n# Steps\n\n### B-9 · a step\n")

        class Pushes:  # the adapter's surface push_desk uses, each push kept
            pushed, ids = [], {}

            def push(self, key, markdown, state, now):
                self.pushed.append(key)
                return "same"

            def push_ask(self, ask, fields, state, settled):
                return "same"

            def push_qa(self, qid, entry, state, settled=None):
                return "same"

        medium = Pushes()
        outcomes = desk.push_desk(self.root, medium, {}, at("2026-02-19T17:00"))
        self.assertNotIn("steps", medium.pushed)
        self.assertNotIn("steps-two", medium.pushed)
        self.assertIn("progress", medium.pushed)
        self.assertFalse([what for what, _ in outcomes if "steps" in what.lower()])

    def qa_desk(self, page_text):
        """A desk set up with the Q&A database and qa.md as given; a FakeNotion whose rows are made as row-<n>."""
        self.put(desk.QA, page_text)
        desk.adapter_notion.save_ids(self.root, {
            "bot": "bot-1", "root": "root-0", "rows": {}, "pages": {},
            "databases": {"asks": {"database": "d1", "data_source": "ds-asks"},
                          "notes": {"database": "d2", "data_source": "ds-notes"},
                          "qa": {"database": "d3", "data_source": "ds-qa"}}})
        fake, rows = FakeNotion(), []

        def row(body):
            rows.append(body)
            return {"id": f"a0a00000-0000-4000-8000-{len(rows):012d}"}

        fake.queue("POST", "/data_sources/ds-asks/query", {"results": []})
        fake.queue("POST", "/data_sources/ds-notes/query", {"results": []})
        fake.queue("POST", "/data_sources/ds-qa/query", {"results": []})  # read for rows the Board adds
        fake.queue("POST", "/pages", row)
        fake.queue("GET", "pages", {"last_edited_by": {"id": "bot-1"}, "last_edited_time": "2026-02-17T09:00:00.000Z"})
        fake.queue("PATCH", "pages", {"object": "page_markdown"})
        return fake, rows

    def test_until_setup_runs_again_the_read_says_what_waits_for_it_never_as_pushed(self):
        """A page or question setup hasn't made yet is named on its own line, never under "pushed:"; the read goes
        on."""
        fake, rows = self.qa_desk(QA_PAGE)
        ids = desk.adapter_notion.load_ids(self.root)
        del ids["databases"]["qa"]
        desk.adapter_notion.save_ids(self.root, ids)
        said = []
        with mock.patch.object(desk, "say", said.append):
            self.assertEqual(desk.read_notion(self.root, at("2026-02-17T09:30"), fake), 0)
        self.assertEqual(rows, [])
        self.assertIn("not in Notion until setup runs again: Progress, Daily summaries, Q-1, Q-2, Q-3, Q-4, Q-5, Q-6",
                      said)
        self.assertNotIn("not set up", "\n".join(said))

    def test_qa_md_s_questions_are_rows_of_the_q_and_a_database_whole(self):
        """Each question of qa.md as the CEO wrote it (Q-1 to Q-6, QA_PAGE) becomes one row, whole, a name included;
        nothing is made twice."""
        fake, rows = self.qa_desk(QA_PAGE.replace("The test order went", "The Acme Bakery order went"))
        pushes = []
        real = desk.push_desk

        def kept(root, adapter, state, now):
            pushes.append(real(root, adapter, state, now))
            return pushes[-1]

        with mock.patch.object(desk, "push_desk", kept):
            self.assertEqual(desk.read_notion(self.root, at("2026-02-17T09:30"), fake), 0)
        questions = [(what, outcome) for what, outcome in pushes[-1] if what.startswith("Q-")]
        self.assertEqual(questions, [(f"Q-{n}", "created") for n in range(1, 7)])
        self.assertEqual([body["properties"]["Id"]["rich_text"][0]["text"]["content"] for body in rows],
                         [f"Q-{n}" for n in range(1, 7)])
        self.assertIn("The Acme Bakery order went", json.dumps(fake.calls))
        q2 = rows[1]["properties"]
        self.assertEqual(desk.adapter_notion.text_of(q2["Question"] | {"type": "title"}),
                         "\"Can http://acme.test/menu open without http://acme.test/welcome first? Some people know us.\"")
        self.assertEqual(q2["Asked"]["rich_text"][0]["text"]["content"], "2026-02-17 about 09:4x")
        self.assertEqual(q2["Sources"]["rich_text"][0]["text"]["link"]["url"],
                         BLOB + "knowledge/board/directives/D-20251229-menu.md")
        with mock.patch.object(desk, "push_desk", kept):
            self.assertEqual(desk.read_notion(self.root, at("2026-02-17T09:32"), fake), 0)
        self.assertEqual([(what, outcome) for what, outcome in pushes[-1] if what.startswith("Q-")],
                         [(f"Q-{n}", "same") for n in range(1, 7)])
        self.assertEqual(len(rows), 6)

    def bodies(self, fake):
        """{row or page id: the markdown each replace_content call sent}, the last call's."""
        return {path.split("/")[2]: body["replace_content"]["new_str"] for method, path, body in fake.calls
                if method == "PATCH" and path.endswith("/markdown")}

    def test_an_entry_runs_to_the_next_heading_of_level_1_to_3_its_sub_headings_and_code_whole(self):
        """#### and deeper headings, a fenced code block (its "# a comment" too), a rule and the lines after them are
        the entry's, in its row's body as the page has them and in Answer."""
        page = ("# The Board's questions and the CEO's answers\n\n## 2026-02-17\n\n"
                "### Q-1 · current · the launch party · asked about 18:2x\n\n"
                "- **Your words:** \"All the steps?\"\n- **Answer:** Below, in full.\n\n"
                "#### 5. The hall\n\n**Minutes:** about 5.\n1. Copy the plan.\n\n---\n\n"
                "#### 6. The menu\n\n4. Paste this block:\n```\n# a shell comment, not a heading\n## nor this\n"
                "P=<id>\n```\n   The two names are deliberate.\n**Doors:** b1.\n\n"
                "### Q-2 · current · delivery · asked about 18:3x\n\n- **Your words:** \"And the cake?\"\n")
        fake, rows = self.qa_desk(page)
        desk.push_desk(self.root, desk.notion_desk(self.root, fake), {}, at("2026-02-17T13:30"))
        bodies = self.bodies(fake)
        entry = page.split("asked about 18:2x\n")[1].split("\n### Q-2")[0]
        self.assertEqual(bodies["a0a00000-0000-4000-8000-000000000001"],
                         "Q-1 · current · the launch party · asked 2026-02-17 about 18:2x\n" + entry)
        answer = desk.adapter_notion.text_of(rows[0]["properties"]["Answer"] | {"type": "rich_text"})
        self.assertEqual(answer, "Below, in full.\n#### 5. The hall\nMinutes: about 5.\n1. Copy the plan.\n---\n"
                                 "#### 6. The menu\n4. Paste this block:\n```\n# a shell comment, not a heading\n"
                                 "## nor this\nP=<id>\n```\nThe two names are deliberate.\nDoors: b1.")
        self.assertEqual(bodies["a0a00000-0000-4000-8000-000000000002"],
                         "Q-2 · current · delivery · asked 2026-02-17 about 18:3x\n\n- **Your words:** \"And the cake?\"\n")

    @staticmethod
    def party_page():
        """qa.md with 11 questions, the last the launch party's: over 100 lines under #### headings, with code blocks,
        rules and more links than one rich text's parts."""
        lines = ["- **Your words:** \"All the steps, please?\"", "- **Answer:** Below, in full.", ""]
        for number, title in ((5, "The hall"), (6, "The menu"), (7, "The guests: who brings what")):
            lines += [f"#### {number}. {title}", "", "**Minutes:** about 5.", ""]
            lines += [f"{step}. Check [the list](list-{number}.md), then [the plan](plan.md), and note step {step}."
                      for step in range(1, 26)]
            lines += ["", "```", "# a comment, not a heading", f"part={number}", "```", "", "---", ""]
        lines.append("**Doors:** none; say nothing about the cake.")
        earlier = "".join(f"\n### Q-{n} · current · the desk · asked about 12:0x\n\n- **Your words:** \"Question {n}?\"\n"
                          f"- **Answer:** Answer {n}.\n" for n in range(1, 11))
        return ("# The Board's questions and the CEO's answers\n\n## 2026-02-17\n" + earlier
                + "\n### Q-11 · current · the launch party · asked about 18:2x\n\n" + "\n".join(lines) + "\n")

    def test_q_11_of_the_launch_party_reaches_its_row_whole_within_notion_s_limits(self):
        """Q-11, the launch party's steps under #### 5. to #### 7., reaches its row whole, links aside, with no block
        over Notion's 2,000 characters and no rich text over its 100 parts."""
        page = self.party_page()
        fake, rows = self.qa_desk(page)
        outcomes = desk.push_desk(self.root, desk.notion_desk(self.root, fake), {}, at("2026-02-17T13:30"))
        self.assertEqual([(what, outcome) for what, outcome in outcomes if what.startswith("Q-")],
                         [(f"Q-{n}", "created") for n in range(1, 12)])
        body = self.bodies(fake)["a0a00000-0000-4000-8000-000000000011"]
        plain = lambda text: desk.adapter_notion.LINK.sub(r"\1", text)  # noqa: E731, a link's url aside
        entry = page.split("\n### Q-11 ")[1].split("\n", 1)[1].rstrip().split("\n")
        self.assertGreater(len(entry), 100)
        self.assertEqual(plain(body).split("\n")[1:], [plain(line) if line.strip() else "" for line in entry] + [""])
        fence = None
        for line in body.split("\n"):
            if fence is None and desk.adapter_notion.FENCE.match(line):
                fence, code = line.strip(), []
            elif fence is not None and line.strip() == fence:
                self.assertLessEqual(len("\n".join(code)), desk.adapter_notion.TEXT_LIMIT)
                fence = None
            elif fence is not None:
                code.append(line)
            else:
                self.assertLessEqual(len(line), desk.adapter_notion.TEXT_LIMIT)
        self.assertIsNone(fence)
        properties = rows[10]["properties"]
        for name, value in properties.items():
            parts = value.get("title") or value.get("rich_text")
            self.assertLessEqual(len(parts), desk.adapter_notion.PARTS_LIMIT, name)
            self.assertLessEqual(max([len(part["text"]["content"]) for part in parts], default=0),
                                 desk.adapter_notion.TEXT_LIMIT)
        answer = desk.adapter_notion.text_of(properties["Answer"] | {"type": "rich_text"})
        self.assertIn("#### 7. The guests: who brings what", answer)
        self.assertTrue(answer.endswith("say nothing about the cake."))

    def test_a_page_notion_refuses_is_said_and_the_q_and_a_rows_still_go(self):
        fake, rows = self.qa_desk(QA_PAGE)
        ids = desk.adapter_notion.load_ids(self.root)
        ids["pages"] = {"progress": "p-progress", "summaries": "p-summaries"}
        desk.adapter_notion.save_ids(self.root, ids)

        def refuse(status):
            def answer(body):
                raise desk.adapter_notion.NotionError(status, "validation_error" if status == 400 else "unauthorized")
            return answer

        fake.queue("PATCH", "/pages/p-progress/markdown", refuse(400))
        said, state = [], {}
        with mock.patch.object(desk, "say", said.append):
            outcomes = desk.push_desk(self.root, desk.notion_desk(self.root, fake), state, at("2026-02-17T09:30"))
        self.assertIn(("Progress", "refused: Notion 400: validation_error"), outcomes)
        self.assertIn(("Daily summaries", "pushed"), outcomes)
        self.assertEqual([what for what, outcome in outcomes if outcome == "created"], [f"Q-{n}" for n in range(1, 7)])
        self.assertEqual(len(rows), 6)
        self.assertIn("Notion refused, not pushed: Progress (Notion 400: validation_error)", said)
        self.assertNotIn("Progress: refused", "\n".join(said))  # never under "pushed:"
        self.assertEqual(("progress" in state["pushed"], "summaries" in state["pushed"]), (False, True))
        tries = lambda: [call[:2] for call in fake.calls].count(("PATCH", "/pages/p-progress/markdown"))  # noqa: E731
        self.assertEqual(tries(), 1)  # never marked pushed, so the next read tries again
        with mock.patch.object(desk, "say", said.append):
            again = desk.push_desk(self.root, desk.notion_desk(self.root, fake), state, at("2026-02-17T09:32"))
        self.assertTrue({("Progress", "refused: Notion 400: validation_error"), ("Daily summaries", "same")} <= set(again))
        self.assertEqual((tries(), "progress" in state["pushed"]), (2, False))
        fake.queue("PATCH", "/pages/p-summaries/markdown", refuse(401))
        with self.assertRaises(desk.adapter_notion.NotionError):  # anything else stops the read
            desk.push_desk(self.root, desk.notion_desk(self.root, fake), {}, at("2026-02-17T09:32"))

    def test_each_notion_refused_line_names_notion_s_message_the_outcome_as_before(self):
        """The read's "Notion refused" line names Notion's message (adapter_notion.message_of()'s, through
        NotionError.named()) for each item it names; the outcome, which the hour's line and the state keep, is the
        status and code alone."""
        fake, _ = self.qa_desk(QA_PAGE)
        ids = desk.adapter_notion.load_ids(self.root)
        ids["pages"] = {"progress": "p-progress", "summaries": "p-summaries"}
        desk.adapter_notion.save_ids(self.root, ids)
        too_long = ("body failed validation: body.properties.Your words (verbatim).rich_text[0].text.content.length "
                    "should be ≤ `2000`, instead was `2004`.")

        def refuse(message):
            def answer(body):
                raise desk.adapter_notion.NotionError(400, "validation_error", message)
            return answer

        fake.queue("PATCH", "/pages/p-progress/markdown", refuse(too_long))
        fake.queue("PATCH", "/pages/p-summaries/markdown", refuse(""))  # Notion gave no message: the code alone
        said, state = [], {}
        with mock.patch.object(desk, "say", said.append):
            outcomes = desk.push_desk(self.root, desk.notion_desk(self.root, fake), state, at("2026-02-17T09:30"))
        self.assertTrue({("Progress", "refused: Notion 400: validation_error"),
                         ("Daily summaries", "refused: Notion 400: validation_error")} <= set(outcomes))
        self.assertIn(f"Notion refused, not pushed: Progress (Notion 400: validation_error: {too_long}); "
                      "Daily summaries (Notion 400: validation_error)", said)
        self.assertEqual(state["stuck"]["Progress"][0], "refused: Notion 400: validation_error")

    def test_a_refusal_an_hour_on_gets_one_line_in_the_hour_s_entry_once_for_each_new_one(self):
        """A page Notion still refuses an hour after the first read that refused it is named once in the next hour's
        entry; a new refusal starts its own hour; a push that goes ends it."""
        fake, _ = self.qa_desk(QA_PAGE)
        ids = desk.adapter_notion.load_ids(self.root)
        ids["pages"] = {"progress": "p-progress"}
        desk.adapter_notion.save_ids(self.root, ids)
        code = ["validation_error"]

        def answer(body):
            if code[0]:
                raise desk.adapter_notion.NotionError(400, code[0])
            return {"object": "page_markdown"}

        fake.queue("PATCH", "/pages/p-progress/markdown", answer)
        state = {}

        def lines(when):
            with mock.patch.object(desk, "say", lambda line: None):
                desk.push_desk(self.root, desk.notion_desk(self.root, fake), state, at(when))
            return [(what, outcome) for what, outcome, _ in state["desk"]]

        first = ("Progress", "refused: Notion 400: validation_error")
        self.assertEqual([lines(when) for when in ("2026-02-17T09:30", "2026-02-17T10:28")], [[], []])
        self.assertEqual([lines(when) for when in ("2026-02-17T10:30", "2026-02-17T11:30")], [[first], [first]])
        desk.save_state(self.root, state, desk.READER)
        self.assertEqual(desk.untied_lines(self.root, set())[0], [
            "Notion has refused Progress for an hour or more (Notion 400: validation_error), so Notion doesn't have it "
            "as the KB does; it is tried again at each read, and the reader's log has each refusal."])
        code[0] = "invalid_request"  # a new refusal: its own hour
        second = ("Progress", "refused: Notion 400: invalid_request")
        self.assertEqual([lines(when) for when in ("2026-02-17T11:32", "2026-02-17T12:32")], [[first], [first, second]])
        code[0] = None  # pushed: the refusal ends, and one later starts its hour again
        self.assertEqual((lines("2026-02-17T12:34"), state["stuck"]), ([first, second], {}))
        code[0], state["pushed"] = "validation_error", {}
        self.assertEqual([lines(when) for when in ("2026-02-17T12:36", "2026-02-17T13:36")],
                         [[first, second], [first, second, first]])

    def test_a_q_id_written_twice_is_said_and_the_later_one_kept(self):
        self.put(desk.DESK / "qa-archive-2026-02.md", "## 2026-02-15\n\n### Q-2 · current · old · asked 09:00\n\n"
                                                       "- **Your words:** \"Old?\"\n")
        self.put(desk.QA, QA_PAGE)
        said = []
        with mock.patch.object(desk, "say", said.append):
            entries = desk.qa_entries(self.root)
        self.assertEqual(entries["Q-2"]["page"], "knowledge/company/board-desk/qa.md")
        self.assertEqual(said, ["qa: Q-2 is written twice (knowledge/company/board-desk/qa-archive-2026-02.md and "
                                "knowledge/company/board-desk/qa.md); only the later one goes to Notion"])

    def test_a_repeat_question_s_row_shows_what_still_holds_then_what_changed(self):
        """"Still true from Q-m" and "Updated" are both in the row's answer, in that order; the old entry's "changed …,
        see Q-n" and the new one's "Asked before" link the two rows, the first once the newer row exists (the read
        after)."""
        later = ("\n## 2026-02-18\n\n### Q-7 · current · the menu · asked 09:10\n\n- **Your words:** \"And today?\"\n"
                 "- **Still true from Q-2:** The welcome page is a link.\n- **Updated:** Done on 02-18; see "
                 "[asks.md](asks.md) B-3.\n- **Asked before:** Q-2\n")
        fake, rows = self.qa_desk(QA_PAGE.replace("### Q-2 · current", "### Q-2 · changed 2026-02-18, see Q-7") + later)
        entries = desk.qa_entries(self.root)
        self.assertEqual(entries["Q-7"]["fields"]["Answer"],
                         "Still true from Q-2: The welcome page is a link.\nUpdated: Done on 02-18; see "
                         "[asks.md](asks.md) B-3.")
        self.assertEqual((entries["Q-2"]["fields"]["Status"], entries["Q-7"]["fields"]["Asked"]),
                         ("changed 2026-02-18, see Q-7", "2026-02-18 09:10"))
        desk.read_notion(self.root, at("2026-02-18T03:30"), fake)
        q7 = rows[-1]["properties"]
        self.assertEqual([part["text"]["content"] for part in q7["Answer"]["rich_text"]],
                         ["Still true from ", "Q-2", ": The welcome page is a link.\nUpdated: Done on 02-18; "
                          "see ", "asks.md", " B-3."])
        self.assertEqual(q7["Asked before"]["rich_text"][0]["text"]["link"]["url"], self.row_url(2))
        desk.read_notion(self.root, at("2026-02-18T03:32"), fake)
        q2_again = [body for method, path, body in fake.calls
                    if method == "PATCH" and path == "/pages/a0a00000-0000-4000-8000-000000000002"]
        self.assertEqual(len(q2_again), 1)
        self.assertEqual(q2_again[0]["properties"]["Status"]["rich_text"][1]["text"]["link"]["url"], self.row_url(7))
        q7_body = [body for method, path, body in fake.calls
                   if (method, path) == ("PATCH", "/pages/a0a00000-0000-4000-8000-000000000007/markdown")]
        self.assertIn(f"[Q-2]({self.row_url(2)})", q7_body[0]["replace_content"]["new_str"])

    @staticmethod
    def row_url(n):
        return "https://www.notion.so/" + f"a0a00000-0000-4000-8000-{n:012d}".replace("-", "")

    def test_a_q_and_a_row_s_edit_is_never_an_answer(self):
        """A change on a Q&A row (no ask id: its Q-id) is never kept as the Board's answer, even in a Board-only field's
        name; only an ask's or a note's is."""
        state = {"board": "board-user"}
        change = {"medium_id": "a0a00000-0000-4000-8000-000000000002", "page": "Q&A", "ask": "Q-2",
                  "field": "Your words", "value": "yes", "editor": "board-user", "edited_at": "2026-02-17T09:31:00Z"}
        kept, untied = desk.record(self.root, state, [change], at("2026-02-17T09:32"))
        self.assertEqual((kept, untied), ([], ["a row with no ask id"]))
        self.assertFalse((self.root / desk.ANSWERS).exists())

    def test_setup_refuses_a_person_s_token_two_roots_and_a_worktree(self):
        for fake, why in [(self.setup_notion(me={"id": "u", "type": "person"})[0], "acts as a person"),
                          (self.setup_notion(roots=2)[0], "2 pages titled"),
                          (self.setup_notion(roots=0)[0], "0 pages titled")]:
            with self.subTest(why=why):
                code, out = self.run_quiet(desk.setup, self.root, fake)
                self.assertEqual(code, 2)
                self.assertIn(why, out)
        code, out = self.run_quiet(desk.setup, self.root, FakeNotion(), main=self.root / "elsewhere")
        self.assertEqual(code, 2)
        self.assertIn("is a worktree", out)
        self.assertIsNone(desk.adapter_notion.load_ids(self.root))

    def attribution(self, edits, board="board-user"):
        desk.adapter_notion.save_ids(self.root, {"bot": "bot-1", "root": "root-0", "pages": {}, "rows": {},
                                                 "databases": {"asks": {"database": "d", "data_source": "ds"}}})
        fake, clock = FakeNotion(), [at("2026-02-16T14:00")]

        def row(words, editor, minute):
            return {"object": "page", "id": "test-row", "last_edited_by": {"object": "user", "id": editor},
                    "last_edited_time": f"2026-02-16T14:{minute:02d}:00.000Z",
                    "properties": {"Your words": {"type": "rich_text", "rich_text": [{"plain_text": words}]}}}

        fake.queue("POST", "/pages", {"id": "test-row"})
        fake.queue("GET", "/pages/test-row", row("", "bot-1", 0),
                   *[row(words, editor, n + 1) for n, (words, editor) in enumerate(edits)])
        fake.queue("PATCH", "/pages/test-row", {"id": "test-row", "in_trash": True})

        def tick():
            return clock[-1]

        def sleep(seconds):
            clock.append(clock[-1] + timedelta(seconds=seconds))

        code, out = self.run_quiet(desk.attribution, self.root, board, fake, sleep=sleep, clock=tick)
        return code, out, fake

    def test_the_board_s_phone_edit_records_its_id_and_each_edit_is_logged(self):
        code, out, fake = self.attribution([("phone", "board-user"), ("connector", "board-user")])
        self.assertEqual(code, 0)
        self.assertIn("Recorded: Notion shows your edit as yours", out)
        self.assertEqual(desk.load_state(self.root, desk.READER)["board"], "board-user")
        logged = [json.loads(line) for line in (self.root / desk.ATTRIBUTION_LOG).read_text().splitlines()]
        self.assertEqual([(entry["step"], entry["editor"]) for entry in logged],
                         [("the script's own write", "the connection"), ('the edit "phone"', "the id you picked"),
                          ('the edit "connector"', "the id you picked")])
        self.assertNotIn("The Board", json.dumps(logged))
        self.assertIn(("PATCH", "/pages/test-row", {"in_trash": True}), fake.calls)
        self.assertEqual(desk.adapter_notion.load_ids(self.root)["rows"], {})
        test_row = next(body for method, path, body in fake.calls if (method, path) == ("POST", "/pages"))
        self.assertNotIn("Your words", test_row["properties"])

    def test_a_phone_s_period_and_case_still_count(self):
        code, out, _ = self.attribution([("Phone.", "board-user"), (" Connector! ", "board-user")])
        self.assertEqual(code, 0)
        self.assertIn('the edit "phone"', out)
        self.assertNotIn("No connector edit seen", out)

    def test_no_connector_edit_is_said_and_logged(self):
        """The connector check not made shows in the output and the log, though the phone edit records the Board's
        id."""
        code, out, _ = self.attribution([("phone", "board-user")])
        self.assertEqual(code, 0)
        self.assertIn("No connector edit seen", out)
        logged = [json.loads(line) for line in (self.root / desk.ATTRIBUTION_LOG).read_text().splitlines()]
        self.assertEqual(logged[-1]["step"], "no connector edit seen")

    def test_no_phone_edit_shown_as_the_board_s_records_nothing(self):
        code, out, _ = self.attribution([("phone", "someone-else"), ("connector", "board-user")])
        self.assertEqual(code, 1)
        self.assertIn("Not recorded", out)
        self.assertNotIn("board", desk.load_state(self.root, desk.READER) or {})

    def test_attribution_refuses_an_id_that_isn_t_a_person_s(self):
        for board in ("bot-1", "nobody"):
            with self.subTest(board=board):
                code, out, fake = self.attribution([], board=board)
                self.assertEqual(code, 2)
                self.assertEqual([call for call in fake.calls if call[0] != "GET"], [])


class BoardRows(Checkout):
    """The Board writes to the CEO in a new row of Notion's Q&A table, and the CEO's answer goes into that row. The real
    adapter on a FakeNotion that holds one row the Board added (ROW); nothing here calls Notion or reads the live
    answers ledger."""

    ROW = "b0a10000-0000-4000-8000-000000000001"
    QA = ("---\ntitle: The Board's questions and the CEO's answers\nowner: ceo\n---\n\n# Q&A\n\n## 2026-02-19\n\n"
          "### Q-7 · current · deploys · asked 12:01\n\n- **Row:** {row}\n- **Answer:** Friday, if the checks pass.\n"
          "- **Sources:** [asks.md](asks.md)\n")

    def setUp(self):
        super().setUp()
        desk.adapter_notion.save_ids(self.root, {
            "bot": "bot-1", "root": "root-0", "rows": {}, "pages": {}, "migrated": [desk.adapter_notion.MIGRATION],
            "databases": {"asks": {"database": "d1", "data_source": "ds-asks"},
                          "notes": {"database": "d2", "data_source": "ds-notes"},
                          "qa": {"database": "d3", "data_source": "ds-qa"}}})  # a desk setup has migrated
        desk.save_state(self.root, {"board": "board-user"}, desk.READER)
        self.title, self.text, self.editor, self.edited = "Can we ship on Friday?", "Answer me here.", "board-user", 1
        self.typing, self.patched, self.made, self.columns = [], [], [], {}  # no Answer column
        self.ours, self.appended = [], []  # the desk's blocks in the row's page; each append's children
        fake = self.fake = FakeNotion()

        def append(body):  # as Notion: the blocks go at the end of the page, the connection their last editor
            self.appended.append(body["children"])
            made = []
            for child in body["children"]:
                block = {"id": f"d{len(self.ours) + len(made) + 1}-{len(self.appended)}", "type": child["type"],
                         "has_children": False, "last_edited_by": {"object": "user", "id": "bot-1"},
                         child["type"]: {"rich_text": [{**part, "plain_text": part["text"]["content"]}
                                                       for part in child[child["type"]]["rich_text"]]}}
                made.append(block)
                fake.queue("DELETE", f"/blocks/{block['id']}",
                           lambda body, gone=block["id"]: self.ours.remove(
                               next(block for block in self.ours if block["id"] == gone)) or {"in_trash": True})
            self.ours += made
            self.editor, self.edited = "bot-1", self.edited + 1
            return {"results": made}

        def query(body):  # the row as the poll reads it; then the Board's typing during the read, if any
            listed = {"results": [self.row()]}
            if self.typing:
                self.title, self.editor, self.edited = self.typing.pop(0), "board-user", self.edited + 1
            return listed

        def patch(body):
            self.patched.append(body)
            self.columns = {**self.columns,  # as Notion: only the properties sent change
                            **{name: {"type": "rich_text", **prop} for name, prop in body["properties"].items()}}
            self.editor, self.edited = "bot-1", self.edited + 1
            return self.row()

        fake.queue("POST", "/data_sources/ds-asks/query", {"results": []})
        fake.queue("POST", "/data_sources/ds-notes/query", {"results": []})
        fake.queue("POST", "/data_sources/ds-qa/query", query)
        fake.queue("GET", f"/pages/{self.ROW}", lambda body: self.row())
        fake.queue("GET", f"/blocks/{self.ROW}/children", lambda body: {"results": [
            {"id": "k1", "type": "paragraph", "has_children": False, "last_edited_by": {"id": "board-user"},
             "paragraph": {"rich_text": [{"plain_text": self.text}]}}, *self.ours, *self.later]})
        self.later = []  # blocks the Board types under the desk's
        fake.queue("PATCH", f"/pages/{self.ROW}", patch)
        fake.queue("PATCH", f"/blocks/{self.ROW}/children", append)
        fake.queue("POST", "/pages", lambda body: self.made.append(body) or {"id": f"row-{len(self.made)}"})

    def row(self):
        return {"object": "page", "id": self.ROW, "created_by": {"object": "user", "id": "board-user"},
                "last_edited_by": {"object": "user", "id": self.editor}, "in_trash": False,
                "last_edited_time": f"2026-02-19T06:{self.edited:02d}:00.000Z",
                "properties": {"Question": {"type": "title", "title": [{"plain_text": self.title}]}, **self.columns}}

    def read(self, when):
        with mock.patch.dict(desk.adapter_notion.PAGES, clear=True):
            self.assertEqual(desk.read_notion(self.root, at(when), self.fake), 0)
        return desk.answer_rows(self.root)

    def ours_text(self):
        """The text of the desk's blocks in the row's page."""
        return "\n".join("".join(part["plain_text"] for part in block[block["type"]]["rich_text"]) for block in self.ours)

    def test_a_new_row_is_read_word_for_word_and_the_watcher_and_scan_name_it(self):
        """A row the Board added is two R-rows of ask "Q&A" (its title and its page), word for word, named by the row's
        id; `wait` exits naming them, and the scan's ANSWER lines show them until a status-log row names them as
        `R-n Q&A`."""
        self.text = "Line one | with a bar.\nAnd <b>two</b>."
        self.fake.queue("GET", f"/blocks/{self.ROW}/children", lambda body: {"results": [
            {"id": "k1", "type": "paragraph", "has_children": False, "paragraph": {"rich_text": [
                {"plain_text": "Line one | with a bar."}]}},
            {"id": "k2", "type": "paragraph", "has_children": False, "paragraph": {"rich_text": [
                {"plain_text": "And <b>two</b>."}]}}]})
        self.assertEqual(self.read("2026-02-19T06:03"),
                         [(1, "Q&A", "Question", self.ROW, "Can we ship on Friday?"),
                          (2, "Q&A", "Page", self.ROW, "Line one | with a bar.\nAnd <b>two</b>.")])
        self.assertEqual(desk.adapter_notion.load_ids(self.root)["rows"][self.ROW], "Q&A")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(desk.wait(self.root, lambda seconds: None), 0)
        self.assertEqual(out.getvalue(), "R-1: the Board answered Q&A\nR-2: the Board answered Q&A\n")
        scan = desk.capacity_scan.unhandled_answers
        self.assertEqual(scan(self.root / desk.ANSWERS, self.root / desk.DIRECTIVES), [("R-1", "Q&A"), ("R-2", "Q&A")])
        self.add_rows("R-1 Q&A, R-2 Q&A: the Board asks when we ship; answered in Q-7")
        self.assertEqual(scan(self.root / desk.ANSWERS, self.root / desk.DIRECTIVES), [])
        self.assertEqual(self.patched, [])  # qa.md doesn't answer it yet: the row is left as the Board wrote it
        self.assertEqual(self.made, [])

    def test_an_edited_row_is_read_again(self):
        """The Board's change to its row's title is a new R-row; a read with no change adds none."""
        self.read("2026-02-19T06:03")
        self.read("2026-02-19T06:05")
        self.title, self.edited = "Can we ship on Friday, or Monday?", 9
        self.assertEqual(self.read("2026-02-19T06:11")[-1], (3, "Q&A", "Question", self.ROW,
                                                             "Can we ship on Friday, or Monday?"))
        self.assertEqual(len(desk.answer_rows(self.root)), 3)

    def test_the_answer_goes_into_the_board_s_row_its_words_left_as_written(self):
        """A Q-entry whose Row line names the row (its R-id, or its Notion id) is written into that row, the CEO's
        columns only, with no second row and no markdown route; the row's title and the Board's blocks stay the Board's.
        The entry goes in the row's page as blocks added under the Board's, which the reader leaves out of its Page. A
        question of the CEO's own (no Row line) is still its own row."""
        for ref in ("R-1", f"https://www.notion.so/Can-we-ship-{self.ROW.replace('-', '')}"):
            with self.subTest(ref=ref):
                self.setUp()
                self.read("2026-02-19T06:03")
                self.put(desk.QA, self.QA.format(row=ref) + "\n### Q-8 · current · own · asked 12:09\n\n"
                                                            "- **Your words:** \"And Monday?\"\n- **Answer:** Also.\n")
                self.fake.queue("PATCH", "pages", {"object": "page_markdown"})  # Q-8's own row's body
                self.read("2026-02-19T06:05")
                self.assertEqual(len(self.patched), 1)
                self.assertEqual(sorted(self.patched[0]), ["properties"])
                properties = self.patched[0]["properties"]
                self.assertEqual(sorted(properties), sorted(desk.adapter_notion.QA_COLUMNS + ("No.",)))
                self.assertEqual(properties["No."], {"number": 7})
                self.assertIn("Answer: Friday, if the checks pass.", self.ours_text())
                bold = self.appended[0][1]["bulleted_list_item"]["rich_text"][0]
                self.assertEqual((bold["text"]["content"], bold["annotations"]), ("Row:", {"bold": True}))
                self.assertEqual([body["properties"]["Id"]["rich_text"][0]["text"]["content"] for body in self.made],
                                 ["Q-8"])  # Q-8 alone made a row
                writes = [(method, path) for method, path, _ in self.fake.calls if method in ("PATCH", "POST", "DELETE")
                          and self.ROW in path]
                self.assertEqual(writes, [("PATCH", f"/pages/{self.ROW}"), ("PATCH", f"/blocks/{self.ROW}/children")])
                self.read("2026-02-19T06:07")  # the push's own edit is no answer, and nothing is written again
                self.assertEqual((len(self.patched), len(self.appended), len(desk.answer_rows(self.root))), (1, 1, 2))
                self.assertNotIn("DELETE", [method for method, *_ in self.fake.calls])

    def test_a_row_edited_during_a_read_waits_for_its_words_then_gets_the_answer(self):
        """The Board retitles its row after the poll and before the push: the push leaves the row, the next read keeps
        the new words, then the answer goes in, once."""
        self.put(desk.QA, self.QA.format(row="R-1"))
        self.assertEqual(self.read("2026-02-19T06:03"), [(1, "Q&A", "Question", self.ROW, "Can we ship on Friday?"),
                                                         (2, "Q&A", "Page", self.ROW, "Answer me here.")])
        self.assertEqual(len(self.patched), 1)
        self.typing = ["Can we ship on Friday? Or is Monday safer?"]
        self.put(desk.QA, self.QA.format(row="R-1").replace("if the checks pass", "if the checks pass today"))
        self.read("2026-02-19T06:05")
        self.assertEqual(len(self.patched), 1, "left while the Board's new words are unread")
        rows = self.read("2026-02-19T06:07")
        self.assertEqual(rows[-1], (3, "Q&A", "Question", self.ROW, "Can we ship on Friday? Or is Monday safer?"))
        self.assertEqual(len(self.patched), 2, "written once, after")
        self.assertEqual(self.title, "Can we ship on Friday? Or is Monday safer?")

    def test_a_row_line_that_names_no_board_row_pushes_nothing_and_is_said_once(self):
        """No second row: a Row line naming no row the Board added (an R-id of an ask, a typo) pushes nothing; the
        hour's entry names it once. Of two entries naming one row, the later Q-id's is written."""
        self.read("2026-02-19T06:03")
        self.put(desk.QA, self.QA.format(row="R-9") + "\n### Q-8 · current · deploys · asked 12:09\n\n"
                                                      "- **Row:** R-2\n- **Answer:** Monday.\n"
                                                      "\n### Q-9 · current · deploys · asked 12:10\n\n"
                                                      "- **Row:** R-1\n- **Answer:** Tuesday.\n")
        said = []
        with mock.patch.object(desk, "say", said.append):
            self.read("2026-02-19T06:05")
            self.read("2026-02-19T06:07")
        self.assertEqual(self.made, [])
        self.assertEqual(len(self.patched), 1)
        self.assertIn("Answer: Tuesday.", self.ours_text())
        self.assertNotIn("Monday", self.ours_text())
        self.assertIn("not pushed: Q-7 (its Row line (R-9) names no row you added to the Q&A table)", said)
        self.assertNotIn("Q-8", "\n".join(said))  # a later entry took its place: nothing to say
        lines = desk.untied_lines(self.root, set())[0]
        self.assertEqual(lines, [
            "Q-7 isn't in Notion (its Row line (R-9) names no row you added to the Q&A table): the CEO fixes it in "
            "qa.md, and it is tried again at each read."])

    def test_the_hour_names_a_row_it_couldn_t_tie_to_the_board_and_points_to_q_and_a(self):
        """The hourly lines name the Q&A table, never Notes to the CEO."""
        self.editor = "someone-else"
        self.read("2026-02-19T06:03")
        state = desk.load_state(self.root, desk.READER)
        state["desk"] = [["Progress", "waits one read: edited in Notion", "2026-02-19T06:03:00+00:00"]]
        desk.save_state(self.root, state, desk.READER)
        lines = desk.untied_lines(self.root, set())[0]
        self.assertEqual(lines, [
            "A change on a row you added to the Q&A table I couldn't tie to you: please re-enter it, or answer in the "
            "chat.",
            "Someone edited Progress in Notion: the CEO has the text in the reader's log, and the page is rewritten at "
            "the next read. Write to the CEO in a new row of the Q&A table instead."])
        self.assertNotIn("Notes to the CEO", "\n".join(lines))

    def test_every_column_of_a_q_and_a_row_is_the_board_s_but_what_the_push_wrote(self):
        """On a row the Board added, any column's text is the Board's (a column name with a bar kept whole), but for
        what the push wrote there (state["wrote"]); on an ask's row, only BOARD_FIELDS."""
        state = {"board": "board-user", "wrote": {self.ROW: {"Answer": "Friday."}}}

        def change(field, value, ask="Q&A"):
            return {"medium_id": self.ROW, "page": "Q&A", "ask": ask, "field": field, "value": value,
                    "editor": "board-user", "edited_at": "2026-02-19T06:01:00Z"}

        kept, untied = desk.record(self.root, state, [change("Answer", "Friday."), change("Topic", "release"),
                                                      change("A | B", "x"), change("Topic", "y", ask="A-12")],
                                   at("2026-02-19T06:03"))
        self.assertEqual((kept, untied), (["R-1", "R-2"], []))
        self.assertEqual(desk.answer_rows(self.root), [(1, "Q&A", "Topic", self.ROW, "release"),
                                                       (2, "Q&A", "A | B", self.ROW, "x")])
        self.assertTrue(desk.ASKED.fullmatch("Q&A"))

    def test_the_board_s_words_in_a_column_are_read_and_never_replaced(self):
        """A column the Board filled when it added the row reaches the ledger word for word and stays as written; the
        CEO's answer goes to the other columns, and the hour says so once. A reply the Board types in the page under the
        CEO's answer, and the Board's edit of one of the desk's blocks, are its words: read, and never removed; the
        CEO's next answer replaces only the desk's own blocks."""
        self.columns["Topic"] = {"type": "rich_text", "rich_text": [{"plain_text": "release"}]}
        self.put(desk.QA, self.QA.format(row="R-1"))
        self.assertEqual(self.read("2026-02-19T06:03")[-1], (3, "Q&A", "Topic", self.ROW, "release"))
        self.assertNotIn("Topic", self.patched[-1]["properties"])
        self.assertIn("Answer: Friday, if the checks pass.", self.ours_text())
        self.read("2026-02-19T06:05")  # the push's own words: no answer of the Board's
        self.assertEqual(len(desk.answer_rows(self.root)), 3)
        self.later = [{"id": "k2", "type": "paragraph", "has_children": False, "last_edited_by": {"id": "board-user"},
                       "paragraph": {"rich_text": [{"plain_text": "Which checks?"}]}}]
        edited = self.ours[0]  # the Board also types into the desk's first block: it is the Board's now
        edited["last_edited_by"], edited["paragraph"] = {"id": "board-user"}, {"rich_text": [{"plain_text": "Not R-1."}]}
        edited["type"] = "paragraph"
        self.editor, self.edited = "board-user", self.edited + 1
        self.assertEqual(self.read("2026-02-19T06:07")[-1],
                         (4, "Q&A", "Page", self.ROW, "Answer me here.\nNot R-1.\nWhich checks?"))
        self.put(desk.QA, self.QA.format(row="R-1").replace("if the checks pass.", "after the release's checks."))
        self.read("2026-02-19T06:09")
        self.assertEqual(sorted(self.patched[-1]["properties"]),
                         sorted(set(desk.adapter_notion.QA_COLUMNS + ("No.",)) - {"Topic"}))
        deleted = [path for method, path, _ in self.fake.calls if method == "DELETE"]
        self.assertEqual(len(deleted), len(self.appended[0]) - 1)  # the desk's own, not the one the Board edited
        self.assertNotIn(f"/blocks/{edited['id']}", deleted)
        self.assertIn("after the release's checks.", self.ours_text())
        self.assertIn(edited, self.ours)
        self.assertEqual(len(desk.answer_rows(self.root)), 4)  # the desk's new blocks are no words of the Board's
        self.assertEqual(desk.untied_lines(self.root, set())[0], 2 * [  # once for each answer of the CEO's
            "Your words in the Topic of the row Q-7 answers stay as you wrote them, and reached the CEO; the CEO's "
            "answer for that column is Q-7 in qa.md, not in the row."])

    def setup_retires(self, *rows):
        """setup run again, the CEO's status-log rows as given: (the calls to Notes' database, printed)."""
        self.rows = []
        self.add_rows(*rows)
        fake, _ = Medium.setup_notion(self)
        fake.queue("PATCH", "/databases/d2", {"object": "database", "id": "d2", "in_trash": True})
        fake.queue("POST", "/data_sources/ds-notes/query", {"results": self.unread})
        code, out = Medium.run_quiet(self, desk.setup, self.root, fake)
        self.assertEqual(code, 0)
        self.fake_calls = fake.calls
        return [call for call in fake.calls if call[1] == "/databases/d2"], out

    unread = []  # the Notes rows changed since the reader's last read, as setup's query finds them

    def test_notes_with_a_row_the_reader_hasn_t_read_are_not_retired(self):
        """A note written after the reader's last read is never trashed unread; the query reaches back to the minute
        that read reached back to."""
        state = desk.load_state(self.root, desk.READER)
        desk.save_state(self.root, {**state, "since": "2026-02-19T06:03:20+00:00"}, desk.READER)
        self.unread = [{"object": "page", "id": "n9", "in_trash": False}]
        calls, out = self.setup_retires("Q&A rows proven live: R-1")
        self.assertEqual(calls, [])
        self.assertIn("Notes to the CEO is not retired: 1 of its rows changed since the reader's last read", out)
        self.assertNotIn("retired", desk.adapter_notion.load_ids(self.root))
        query = [body for method, path, body in self.fake_calls if path == "/data_sources/ds-notes/query"]
        self.assertEqual(query, [{"filter": {"timestamp": "last_edited_time",
                                             "last_edited_time": {"on_or_after": "2026-02-19T06:02:00.000Z"}}}])
        self.unread = []
        self.assertEqual(self.setup_retires("Q&A rows proven live: R-1")[0], [("PATCH", "/databases/d2",
                                                                                 {"in_trash": True})])

    def test_notes_to_the_ceo_is_retired_only_after_the_ceo_s_line_once(self):
        """Setup trashes Notes to the CEO's database only once a CEO row of a status log starts "Q&A rows proven live"
        (a row quoting it doesn't), once; undo: restore it from Notion's trash, and the next read reads it again."""
        quoted = 'ORDER: Notes retired after a "Q&A rows proven live" line'
        self.assertEqual(self.setup_retires(quoted)[0], [])
        self.assertNotIn("retired", desk.adapter_notion.load_ids(self.root))
        calls, out = self.setup_retires(quoted, "Q&A rows proven live: R-1 and R-2 went through end to end (Q-7)")
        self.assertEqual(calls, [("PATCH", "/databases/d2", {"in_trash": True})])
        self.assertIn("Notes to the CEO is retired (moved to Notion's trash)", out)
        self.assertIn("Undo: restore it from Notion's trash", out)
        ids = desk.adapter_notion.load_ids(self.root)
        self.assertEqual((ids["retired"], ids["databases"]["notes"]["database"]), (["notes"], "d2"))
        self.assertEqual(self.setup_retires("Q&A rows proven live: again")[0], [])  # once

    def test_retiring_notes_already_gone_counts_as_done(self):
        self.add_rows("Q&A rows proven live: R-1")
        fake, _ = Medium.setup_notion(self)

        def gone(body):
            raise desk.adapter_notion.NotionError(404, "object_not_found")

        fake.queue("PATCH", "/databases/d2", gone)
        fake.queue("POST", "/data_sources/ds-notes/query", gone)
        code, out = Medium.run_quiet(self, desk.setup, self.root, fake)
        self.assertEqual(code, 0)
        self.assertIn("Notes to the CEO is retired (already gone from Notion)", out)
        self.assertEqual(desk.adapter_notion.load_ids(self.root)["retired"], ["notes"])


class Directives(Checkout):
    """The Directives table, a directive the Board adds there, and the daily cleanup of done rows. The real adapter on
    a FakeNotion that holds one row someone added (ROW); nothing here calls Notion or a model, or reads the live
    ledger."""

    ROW = "d0a10000-0000-4000-8000-000000000001"
    LOGO = "D-20260219-logo"

    def setUp(self):
        super().setUp()
        desk.adapter_notion.save_ids(self.root, {
            "bot": "bot-1", "root": "root-0", "rows": {}, "pages": {}, "migrated": [desk.adapter_notion.MIGRATION],
            "databases": {key: {"database": f"d-{key}", "data_source": f"ds-{key}"}
                          for key in ("asks", "notes", "qa", "directives")}})
        desk.save_state(self.root, {"board": "board-user"}, desk.READER)
        self.creator = self.editor = "board-user"
        self.edited, self.listed, self.columns, self.ours, self.patched, self.made = 1, True, {}, [], [], []
        fake = self.fake = FakeNotion()

        def patch(body):
            self.patched.append(body)
            self.columns = {**self.columns, **{name: {"type": next(iter(prop)), **prop}
                                               for name, prop in body["properties"].items()}}
            self.editor, self.edited = "bot-1", self.edited + 1
            return self.row()

        def append(body):
            made = [{"id": f"m{len(self.ours) + n}", "type": child["type"], "has_children": False,
                     "last_edited_by": {"id": "bot-1"}, child["type"]: {"rich_text": [
                         {"plain_text": part["text"]["content"]} for part in child[child["type"]]["rich_text"]]}}
                    for n, child in enumerate(body["children"])]
            self.ours += made
            self.editor, self.edited = "bot-1", self.edited + 1
            return {"results": made}

        for key in ("asks", "notes", "qa"):
            fake.queue("POST", f"/data_sources/ds-{key}/query", {"results": []})
        fake.queue("POST", "/data_sources/ds-directives/query",
                   lambda body: {"results": [self.row()] if self.listed else []})
        fake.queue("GET", f"/pages/{self.ROW}", lambda body: self.row())
        fake.queue("GET", f"/blocks/{self.ROW}/children", lambda body: {"results": [
            {"id": "k1", "type": "paragraph", "has_children": False, "last_edited_by": {"id": self.creator},
             "paragraph": {"rich_text": [{"plain_text": "By Friday, please."}]}}, *self.ours]})
        fake.queue("PATCH", f"/pages/{self.ROW}", patch)
        fake.queue("PATCH", f"/blocks/{self.ROW}/children", append)
        fake.queue("POST", "/pages", lambda body: self.made.append(body) or {"id": f"row-{len(self.made)}"})
        fake.queue("PATCH", "pages", {"object": "page_markdown"})  # the desk's own rows' pages

    def row(self):
        return {"object": "page", "id": self.ROW, "created_by": {"object": "user", "id": self.creator},
                "last_edited_by": {"object": "user", "id": self.editor}, "in_trash": False,
                "last_edited_time": f"2026-02-19T06:{self.edited:02d}:00.000Z",
                "properties": {"Directive": {"type": "title", "title": [{"plain_text": "Make the logo"}]},
                               "Status": {"type": "select", "select": None}, **self.columns}}

    def read(self, when):
        with mock.patch.dict(desk.adapter_notion.PAGES, clear=True):
            self.assertEqual(desk.read_notion(self.root, at(when), self.fake), 0)
        return desk.answer_rows(self.root)

    def directive(self, did, title, rows, status="open", words=""):
        self.put(desk.DIRECTIVES / f"{did}.md", f"---\ntitle: {title}\nowner: ceo\nstatus: active\n---\n\n# {did}\n\n"
                 f"**Directive status:** {status}\n\n## Directive (verbatim)\n\n{words}\n\n## Status log\n\n"
                 "| Date | Who | Entry |\n|---|---|---|\n" + "".join(f"| {day} | ceo | {entry} |\n" for day, entry in rows))

    def test_a_row_the_board_adds_is_a_new_directive_the_watcher_names_and_the_ceo_files(self):
        """A row the Board adds with no id is recorded as R-rows of kind "New directive", word for word; `wait` wakes
        the CEO saying so, and the scan names them until a status-log row does. Recorded and not yet filed, the row gets
        Status "Not started" (the desk's own write, no answer); once the CEO files it, the next push links the row: its
        id, Status "In progress", the directive's reports in its page under the Board's words, its title and the Board's
        block untouched. Nothing acts on the row's text."""
        self.assertEqual(self.read("2026-02-19T06:03"),
                         [(1, "New directive", "Directive", self.ROW, "Make the logo"),
                          (2, "New directive", "Page", self.ROW, "By Friday, please.")])
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(desk.wait(self.root, lambda seconds: None), 0)
        self.assertEqual(out.getvalue(), "".join(
            f"R-{n}: the Board gave a new directive in a row of Notion's Directives table: file it with /directive "
            f"and write \"R-{n} New directive\" in a row of its status log\n" for n in (1, 2)))
        scan = desk.capacity_scan.unhandled_answers
        self.assertEqual(scan(self.root / desk.ANSWERS, self.root / desk.DIRECTIVES),
                         [("R-1", "New directive"), ("R-2", "New directive")])
        self.assertEqual(self.patched, [{"properties": {"Status": {"select": {"name": "Not started"}}}}])
        self.assertEqual(len(self.read("2026-02-19T06:05")), 2)  # the desk's Status is no word of the Board's
        self.directive(self.LOGO, "Make the logo", [("2026-02-19", "Filed from R-1 New directive, R-2 New directive")],
                       words="> Make the logo. By Friday, please.")
        self.assertEqual(scan(self.root / desk.ANSWERS, self.root / desk.DIRECTIVES), [])
        made = len(self.made)
        self.read("2026-02-19T06:07")
        self.assertEqual(len(self.made), made)  # no row made for it: the Board's is its row
        sent = self.patched[-1]["properties"]
        self.assertEqual(sorted(sent), sorted(desk.adapter_notion.DIRECTIVE_FIELDS))
        self.assertEqual((sent["Id"]["rich_text"][0]["text"]["content"], sent["Status"]),
                         (self.LOGO, {"select": {"name": "In progress"}}))
        self.assertEqual(sent["Your words (verbatim)"]["rich_text"][0]["text"]["content"],
                         "Make the logo. By Friday, please.")
        self.assertNotIn("Directive", sent)
        text = "\n".join("".join(part["plain_text"] for part in block[block["type"]]["rich_text"]) for block in self.ours)
        self.assertIn(f"No hourly report in the last 7 days.\nThe whole directive: {self.LOGO}.md", text)
        self.assertNotIn("DELETE", [method for method, *_ in self.fake.calls])
        self.assertEqual(len(self.read("2026-02-19T06:09")), 2)  # the link is no answer either
        self.assertEqual([call for call in self.claude_calls()], [])  # nothing ran on the row's text

    def test_a_row_another_member_adds_is_ignored_and_logged_by_its_ids_alone(self):
        """A row someone else made is no directive: no R-row, no write; the reader's log names it by its ids, never its
        words, once, and the hour says a change on the Directives table couldn't be tied to the Board."""
        self.creator = self.editor = "member-2"
        self.assertEqual(self.read("2026-02-19T06:03"), [])
        self.read("2026-02-19T06:05")
        log = (self.root / desk.READER_LOG).read_text()
        self.assertEqual([json.loads(line)["why"] for line in log.splitlines()], ["another editor", "another editor"])
        self.assertIn(self.ROW, log)
        for words in ("Make the logo", "By Friday"):
            self.assertNotIn(words, log)
            self.assertNotIn(words, (self.root / desk.READER).read_text())
        self.assertEqual(self.patched, [])
        self.assertEqual(desk.untied_lines(self.root, set())[0], [
            "A change on a row added to the Directives table I couldn't tie to you: please re-enter it, or answer in "
            "the chat."])
        self.editor, self.edited = "board-user", self.edited + 1  # the Board edits it: still not the Board's row
        self.assertEqual(self.read("2026-02-19T06:09"), [])
        self.assertEqual([json.loads(line)["why"] for line in (self.root / desk.READER_LOG).read_text().splitlines()],
                         ["another editor"] * 2 + ["made by another member"] * 2)
        self.assertEqual(self.patched, [])
        for words in ("Make the logo", "By Friday"):
            self.assertNotIn(words, (self.root / desk.READER_LOG).read_text())

    def test_a_directive_s_row_holds_its_title_status_time_words_and_its_reports_newest_first(self):
        """One row a directive open or done within 7 days: its front-matter title, Status (Done for done or cancelled),
        Last updated (the newest of its rows' dates and its entries' times, in the Board's zone), the verbatim section's
        first 2,000 characters, and its page: its hourly entries of the last 7 days, newest first."""
        self.directive(self.LOGO, "Make the logo", [("2026-02-18", "Done: the brief")],
                       words="> " + "w" * 2100)
        self.directive("D-20260201-old", "Old work", [("2026-02-11", "Done: all of it")], status="done")
        self.directive("D-20260205-recent", "Recent work", [("2026-02-13", "Done: all of it")], status="cancelled")
        self.put(desk.DIRECTIVE_PROGRESS, json.dumps({self.LOGO: {
            "2026-02-19T05:00:00+00:00": {"start": "2026-02-19T04:00:00+00:00", "lines": ["The designer started."]},
            "2026-02-19T03:00:00+00:00": {"start": "2026-02-19T02:00:00+00:00", "lines": ["The brief went out."]},
            "2026-02-11T03:00:00+00:00": {"start": "2026-02-11T02:00:00+00:00", "lines": ["Too old to show."]}}}))
        items, old = desk.directive_items(self.root, at("2026-02-19T06:00"), [])
        self.assertEqual(set(items), {DIRECTIVE, self.LOGO, "D-20260205-recent"})
        self.assertEqual(old, {"D-20260201-old": None})
        logo = items[self.LOGO]
        self.assertEqual((logo["title"], logo["Status"], logo["updated"], len(logo["words"]), logo["row"]),
                         ("Make the logo", "In progress", "2026-02-19 11:00", 2000, None))
        self.assertEqual(logo["lines"][:7], ["### 2026-02-19 10:00-11:00 Dhaka", "", "The designer started.", "",
                                             "### 2026-02-19 08:00-09:00 Dhaka", "", "The brief went out."])
        self.assertNotIn("Too old to show.", logo["lines"])
        self.assertEqual((items["D-20260205-recent"]["Status"], items["D-20260205-recent"]["updated"]),
                         ("Done", "2026-02-13"))
        self.assertIn("No hourly report in the last 7 days.", items["D-20260205-recent"]["lines"])

    def test_the_hour_writes_each_directive_s_entry_once_the_table_exists(self):
        """After the hour's own entry, the hour's new rows go to directives.md's writer, by directive; its lines are
        kept for the directive's page, 7 days. A writer that fails twice leaves the first rows, raw and marked."""
        self.started()
        self.add_rows("Decided: keep the old label (undo: revert the commit)")
        self.replies = [reply(f"Decided: keep the old label; undo by reverting it ({DIRECTIVE})."),
                        reply(f"{DIRECTIVE}:\nThe team kept the old label, and can undo it.")]
        self.assertEqual(self.hour("2026-02-16T15:02"), 0)
        calls = self.claude_calls()
        self.assertEqual(len(calls), 2)
        self.assertIn(f"[{DIRECTIVE}, ceo, row dated 2026-02-16] Decided: keep the old label", calls[1]["input"])
        argv = [argv for argv, _ in self.calls if argv[0] == "claude"][1]
        flags = dict(zip(argv, argv[1:]))
        self.assertEqual((flags["--model"], flags["--tools"], flags["--system-prompt-file"]),
                         ("sonnet", "", str(SCRIPTS / "board_desk" / "directives.md")))  # no tools: the packet is data
        kept = json.loads(self.page(desk.DIRECTIVE_PROGRESS))
        self.assertEqual(kept, {DIRECTIVE: {"2026-02-16T15:00:00+00:00": {
            "start": "2026-02-16T14:00:00+00:00", "lines": ["The team kept the old label, and can undo it."]}}})
        self.add_rows("Done: the label shipped")
        self.replies = [reply(f"Done: the label shipped ({DIRECTIVE})."), reply("nothing useful"),
                        reply("still nothing")]
        self.assertEqual(self.hour("2026-02-16T16:02"), 0)
        kept = json.loads(self.page(desk.DIRECTIVE_PROGRESS))[DIRECTIVE]["2026-02-16T16:00:00+00:00"]["lines"]
        self.assertEqual(kept, ["Done: the label shipped", f"(raw; the writer failed: no entry for {DIRECTIVE})"])

    def test_no_directive_entry_is_written_before_setup_makes_the_table(self):
        ids = desk.adapter_notion.load_ids(self.root)
        del ids["databases"]["directives"]
        desk.adapter_notion.save_ids(self.root, ids)
        self.started()
        self.add_rows("Done: a thing")
        self.hour("2026-02-16T15:02")
        self.assertEqual(len(self.claude_calls()), 1)
        self.assertFalse((self.root / desk.DIRECTIVE_PROGRESS).exists())

    def cleanup_fixture(self):
        self.put(desk.QA, "---\ntitle: Q&A\nowner: ceo\n---\n\n# Q&A\n\n## 2026-02-13\n\n### Q-2 · current · deploys · "
                          "asked 12:01\n\n- **Answer:** Six days old.\n\n## 2026-02-11\n\n### Q-1 · current · deploys · "
                          "asked 12:01\n\n- **Answer:** Eight days old.\n")
        self.put(desk.ASKS, self.page(desk.ASKS).replace(
            "## Open\n\n(none yet)", "## Open\n\n### A-3 · open · b9 · D-x · asked 2026-02-01 09:00\n\n"
            "- **Question:** Still open?\n").replace(
            "## Closed\n\n(none yet)", "## Closed\n\n### A-2 · answered 2026-02-13 · b9\n\n- **Question:** Six?\n\n"
            "### A-1 · withdrawn 2026-02-11 · b9\n\n- **Question:** Eight?\n"))
        self.directive("D-20260201-old", "Old work", [("2026-02-11", "Done: all of it")], status="done")
        self.directive("D-20260205-recent", "Recent work", [("2026-02-13", "Done: all of it")], status="done")
        self.directive("D-20260201-open", "Open work", [("2026-02-01", "Started")])
        ids = desk.adapter_notion.load_ids(self.root)
        ids["rows"] = {"r-q1": "Q-1", "r-q2": "Q-2", "r-a1": "A-1", "r-a2": "A-2", "r-a3": "A-3",
                       "r-old": "D-20260201-old", "r-recent": "D-20260205-recent", "r-open": "D-20260201-open"}
        desk.adapter_notion.save_ids(self.root, ids)

    class Stub:
        """The adapter's surface push_desk and clean use: each push and trash kept."""

        def __init__(self, ids):
            self.ids, self.pushed, self.trashed = ids, [], []

        def push(self, key, markdown, state, now):
            return "same"

        def push_ask(self, ask, *args):
            self.pushed.append(ask)
            return "same"

        def push_qa(self, qid, *args):
            self.pushed.append(qid)
            return "same"

        def push_directive(self, did, *args):
            self.pushed.append(did)
            return "same"

        def trash(self, row, what):
            self.trashed.append((what, row))
            return True

    def test_each_day_at_10_done_rows_older_than_7_days_go_to_the_trash_and_are_pushed_no_more(self):
        """At the first read at or after 10:00 in the Board's zone, once a day, every row done more than 7 days ago goes
        to Notion's trash (a question asked, an ask answered or withdrawn, a directive done), a count per table in the
        log; 6 days old, open or not started, stays; the push leaves the ones gone."""
        self.cleanup_fixture()
        stub, state = self.Stub(desk.adapter_notion.load_ids(self.root)), {}
        with mock.patch.object(desk, "say") as said:
            self.assertEqual(desk.clean(self.root, stub, state, at("2026-02-19T03:59")), {})  # 09:59 Dhaka
            self.assertEqual(stub.trashed, [])
            self.assertEqual(desk.clean(self.root, stub, state, at("2026-02-19T04:01")),
                             {"Q&A": 1, "Asks": 1, "Directives": 1})
            self.assertEqual(sorted(stub.trashed), [("A-1", "r-a1"), ("D-20260201-old", "r-old"), ("Q-1", "r-q1")])
            said.assert_called_with("cleanup: rows done more than 7 days ago, moved to Notion's trash: Q&A 1, Asks 1, "
                                    "Directives 1")
            self.assertEqual(desk.clean(self.root, stub, state, at("2026-02-19T09:00")), {})  # once a day
        self.assertEqual(len(stub.trashed), 3)
        desk.push_desk(self.root, stub, state, at("2026-02-19T04:03"))
        self.assertEqual(sorted(set(stub.pushed) & {"Q-1", "Q-2", "A-1", "A-2", "A-3", "D-20260201-old",
                                                    "D-20260205-recent", "D-20260201-open"}),
                         ["A-2", "A-3", "D-20260201-open", "D-20260205-recent", "Q-2"])

    def test_the_cleanup_s_notion_refused_line_names_notion_s_message(self):
        """A move to the trash Notion refuses is said with Notion's message (NotionError.named())."""
        self.cleanup_fixture()
        stub = self.Stub(desk.adapter_notion.load_ids(self.root))

        def trash(row, what):
            raise desk.adapter_notion.NotionError(400, "validation_error", "Can't edit block that is archived.")

        stub.trash, said = trash, []
        with mock.patch.object(desk, "say", said.append):
            desk.clean(self.root, stub, {}, at("2026-02-19T04:01"))
        self.assertIn("cleanup: Notion refused to move A-1's row to its trash (Notion 400: validation_error: Can't "
                      "edit block that is archived.); tried again tomorrow", said)

    def test_the_10_00_cleanup_raises_no_answers_alarm(self):
        """The cleanup's moves to Notion's trash, through the adapter, rewrite the desk's ids (notion.json): no ANSWERS
        TAMPERED line."""
        self.cleanup_fixture()
        self.fake.queue("PATCH", "pages", {})
        notion = desk.adapter_notion.Desk(self.root, lambda why, data: None, self.fake)
        with mock.patch.object(desk, "say"):
            self.assertEqual(desk.clean(self.root, notion, {}, at("2026-02-19T04:01")),
                             {"Q&A": 1, "Asks": 1, "Directives": 1})
        self.assertIn("r-a1", desk.adapter_notion.load_ids(self.root)["trashed"])
        self.assertEqual(desk.answers_seal.report(self.root), ([], set(), ""))

    def test_a_row_the_board_added_stays_while_its_words_are_recent_or_unhandled(self):
        """An answer asked 8 days ago doesn't take the Board's row to the trash while the Board wrote there within 7
        days (an R-row of it recorded 1 day ago), or while an R-row of it is one no status-log row names yet; once both
        are old and handled, it goes. The same for a directive's filed row."""
        self.cleanup_fixture()
        self.put(desk.QA, self.page(desk.QA) + "\n### Q-3 · current · deploys · asked 12:05\n\n- **Row:** R-1\n"
                                               "- **Answer:** Eight days old too.\n")  # under 2026-02-11
        ledger = desk.ANSWERS / "2026-W07.md"

        def answers(*rows):
            self.put(ledger, f"---\ntitle: t\nowner: board\n---\n\n{desk.ANSWERS_HEAD}\n" + "".join(
                f"| R-{n} | {ask} | Page | {day} 12:01 | {day} 12:03 | {row} | words |\n" for n, ask, day, row in rows))

        cases = [((2, "Q&A", "2026-02-18", "b-qa"), "R-1 Q&A, R-2 Q&A, R-3 New directive, R-4 New directive", False),
                 ((2, "Q&A", "2026-02-11", "b-qa"), "R-1 Q&A, R-3 New directive", False),
                 ((2, "Q&A", "2026-02-11", "b-qa"), "R-1 Q&A, R-2 Q&A, R-3 New directive, R-4 New directive", True)]
        for follow_up, handled, gone in cases:
            with self.subTest(follow_up=follow_up, handled=handled):
                answers((1, "Q&A", "2026-02-11", "b-qa"), follow_up, (3, "New directive", "2026-02-11", "b-dir"),
                        (4, "New directive", follow_up[2], "b-dir"))
                self.rows = []
                self.add_rows(handled)
                text = self.page(desk.DIRECTIVES / "D-20260201-old.md")
                self.put(desk.DIRECTIVES / "D-20260201-old.md", text.replace("| Done: all of it |",
                                                                             "| Done: all of it, from R-3 New directive |"))
                stub = self.Stub(desk.adapter_notion.load_ids(self.root))
                with mock.patch.object(desk, "say"):
                    desk.clean(self.root, stub, {}, at("2026-02-19T04:01"))
                trashed = {row for _, row in stub.trashed}
                self.assertEqual({"b-qa", "b-dir"} & trashed, {"b-qa", "b-dir"} if gone else set())
                self.assertIn("r-q1", trashed)  # the desk's own old row goes either way

    def test_an_old_ask_row_with_recent_board_words_stays_and_a_question_counts_from_its_last_change(self):
        """An ask withdrawn 8 days ago whose row got the Board's words 1 day ago stays, as a question's and a
        directive's rows do; a question asked 8 days ago and answered again in place since counts from the day a read
        saw it changed, one first seen from its Asked date."""
        self.cleanup_fixture()
        self.put(desk.ANSWERS / "2026-W08.md", f"---\ntitle: t\nowner: board\n---\n\n{desk.ANSWERS_HEAD}\n"
                 "| R-1 | A-1 | Your words | 2026-02-18 12:01 | 2026-02-18 12:03 | r-a1 | One more thing |\n")
        stub, state = self.Stub(desk.adapter_notion.load_ids(self.root)), {}
        with mock.patch.object(desk, "say"):
            desk.push_desk(self.root, stub, state, at("2026-02-12T04:00"))
            self.put(desk.QA, self.page(desk.QA).replace("Eight days old.", "Eight days old, answered again."))
            desk.push_desk(self.root, stub, state, at("2026-02-15T04:00"))
            self.assertEqual(desk.clean(self.root, stub, state, at("2026-02-19T04:01")),
                             {"Q&A": 0, "Asks": 0, "Directives": 1})
        self.assertEqual(stub.trashed, [("D-20260201-old", "r-old")])
        self.assertEqual((state["changed"]["Q-1"][1], state["changed"]["Q-2"][1]), ("2026-02-15", ""))

    def test_readback_prints_property_names_and_block_counts_never_text(self):
        """For each id, its row, its property names and its page's block count; no text."""
        ids = desk.adapter_notion.load_ids(self.root)
        ids["rows"] = {"row-31": "Q-31"}
        desk.adapter_notion.save_ids(self.root, ids)
        self.fake.queue("GET", "/pages/row-31", {"properties": {"Question": {"type": "title", "title": [
            {"plain_text": "secret question"}]}, "No.": {"type": "number", "number": 31}}})
        self.fake.queue("GET", "/blocks/row-31/children", {"results": [
            {"id": "k1", "type": "paragraph", "paragraph": {"rich_text": [{"plain_text": "secret answer"}]}}] * 3})

        def views(body):  # each table's views; the Directives table's list refused
            if body["database_id"] == "d-directives":
                raise desk.adapter_notion.NotionError(404, "object_not_found")
            return {"results": {"d-qa": [{"object": "view", "id": "v-qa", "sorts": [
                {"property": "No.", "direction": "descending"}]}],
                                "d-asks": [{"object": "view", "id": "v-asks"},
                                           {"object": "view", "id": "v-mine", "sorts": []}]}[body["database_id"]]}

        self.fake.queue("GET", "/views", views)
        self.fake.queue("GET", "/views/v-asks", {"object": "view", "id": "v-asks", "sorts": [  # listed without sorts
            {"property": "State", "direction": "ascending"}]})
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(desk.readback(self.root, ["Q-31", "Q-29"], self.fake), 0)
        self.assertEqual(out.getvalue(),
                         "The Q&A table's views: v-qa sorted by No. descending (setup's for the first: No. "
                         "descending)\nThe Asks table's views: v-asks sorted by State ascending; v-mine sorted by "
                         "nothing (setup's for the first: State ascending, Priority ascending, No. ascending)\n"
                         "The Directives table's views: Notion answered 404 (object_not_found)\n"
                         "Q-31: row row-31; properties: No., Question; blocks in its page: 3\n"
                         f"Q-29: no row of it in {desk.adapter_notion.IDS}\n")
        self.assertFalse([call for call in self.fake.calls if call[0] != "GET"])  # it only reads


class Python39(unittest.TestCase):
    def test_the_job_runs_under_apples_python(self):
        if not Path(desk.PYTHON).exists():
            self.skipTest("no /usr/bin/python3")
        done = subprocess.run([desk.PYTHON, "-c", "import sys; sys.path.insert(0, sys.argv[1]); import board_desk; "
                               "board_desk.main(['--help'])", str(SCRIPTS)], capture_output=True, text=True, timeout=60)
        self.assertEqual(done.returncode, 0, done.stderr[-500:])
        self.assertIn("usage:", done.stdout)


if __name__ == "__main__":
    unittest.main()
