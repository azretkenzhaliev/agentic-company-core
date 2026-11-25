"""Tests for scripts/notion_approvals_sync.py (a PostToolUse hook). No network: the query result is a fixture."""

import copy
import hashlib
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from kb_lint import parse_front_matter  # noqa: E402
from notion_approvals_sync import calendar_query, main, read_rows, render  # noqa: E402

EVENT = json.loads((Path(__file__).parent / "fixtures" / "notion_rows_event.json").read_text())
CALENDAR = EVENT["tool_input"]["data"]["data_source_url"].removeprefix("collection://")
ROWS = json.loads(EVENT["tool_response"][0]["text"])["results"]
WEEK_FILTER = {"type": "group", "operator": "and", "filters": [
    {"type": "property", "property": "Week", "propertyType": "text", "operator": "string_is",
     "value": {"type": "exact", "value": "2026-W05"}}]}


def query(rows, has_more=False, **data):
    event = copy.deepcopy(EVENT)
    event["tool_input"]["data"].update(data)
    event["tool_response"] = [{"type": "text", "text": json.dumps({"results": rows, "has_more": has_more})}]
    return event


class Hook(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.marketing = self.root / "knowledge" / "marketing"
        self.page = self.marketing / "founder/demo/approvals/2026-W05.md"
        (self.root / "company.json").write_text(json.dumps({"integrations": {"marketing": {
            "notion": {"calendar": CALENDAR}, "brands": {"founder/demo": {}, "acme": {}}}}}))
        content = self.marketing / "founder/demo/content/2026-W05"
        content.mkdir(parents=True)
        for name in ("mon-reel.md", "wed-carousel.md", "other.md"):
            (content / name).write_text(f"# {name}\n")

    def tearDown(self):
        self.tmp.cleanup()

    def run_hook(self, event):
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()):
            code = main(io.StringIO(json.dumps(event)), self.marketing)
        return code, out.getvalue()

    def rows(self):
        return read_rows(self.page)

    def test_two_brands_with_one_last_name_sync_nothing(self):
        (self.root / "company.json").write_text(json.dumps({"integrations": {"marketing": {
            "notion": {"calendar": CALENDAR}, "brands": {"founder/demo": {}, "demo": {}}}}}))
        code, out = self.run_hook(query(ROWS, filter=WEEK_FILTER))
        self.assertEqual((code, out), (0, ""))
        self.assertFalse(self.page.exists())

    def test_writes_the_boards_fields_verbatim_and_lints(self):
        code, out = self.run_hook(query(ROWS, filter=WEEK_FILTER))
        self.assertEqual(code, 0)
        text = self.page.read_text()
        fields, _, _ = parse_front_matter(text.splitlines())
        self.assertEqual(fields["owner"], "board")
        self.assertIn("Slide 3: use \\| my own words<br>not this", text)
        self.assertEqual([r["approval"] for r in self.rows()], ["Approved", "Changes", "pending"])
        self.assertIn("approvals/2026-W05.md: 3 items", json.loads(out)["hookSpecificOutput"]["additionalContext"])

    def test_a_decision_keeps_the_page_and_hash_it_was_made_on(self):
        self.run_hook(query(ROWS))
        approved = self.rows()[0]
        page = self.root / approved["kb_page"]
        self.assertEqual(approved["kb_sha256"], hashlib.sha256(page.read_bytes()).hexdigest())
        moved = dict(ROWS[0], **{"KB page": "knowledge/marketing/founder/demo/content/2026-W05/other.md"})
        self.run_hook(query([moved, *ROWS[1:3]]))
        row = self.rows()[0]
        self.assertEqual(row["kb_page"], approved["kb_page"])
        self.assertEqual(row["kb_sha256"], approved["kb_sha256"])
        self.assertIn("KB page is now", row["note"])
        page.write_text("# edited after approval\n")
        self.run_hook(query(ROWS[:3]))
        self.assertIn("changed after the decision", self.rows()[0]["note"])

    def test_a_new_decision_records_the_page_again(self):
        self.run_hook(query(ROWS))
        self.assertEqual(self.rows()[2]["kb_sha256"], "")
        decided = dict(ROWS[2], Approval="Approved",
                       **{"KB page": "knowledge/marketing/founder/demo/content/2026-W05/other.md"})
        self.run_hook(query([*ROWS[:2], decided]))
        self.assertEqual(len(self.rows()[2]["kb_sha256"]), 64)

    def test_a_decision_seen_first_without_a_pending_sync_is_noted(self):
        self.run_hook(query(ROWS[:1]))
        self.assertIn("no earlier hash to compare", self.rows()[0]["note"])

    def test_moving_an_approved_item_to_another_week_keeps_it_where_it_was_decided(self):
        self.run_hook(query(ROWS[:3]))
        decided = self.rows()[0]
        moved = dict(ROWS[0], Week="2026-W06", **{"KB page": "knowledge/marketing/founder/demo/content/2026-W05/other.md"})
        w06 = dict(WEEK_FILTER, filters=[dict(WEEK_FILTER["filters"][0], value={"type": "exact", "value": "2026-W06"})])
        self.run_hook(query([moved], filter=w06))
        self.assertFalse((self.marketing / "founder/demo/approvals/2026-W06.md").exists())
        row = self.rows()[0]
        self.assertEqual((row["kb_page"], row["kb_sha256"], row["approval"]),
                         (decided["kb_page"], decided["kb_sha256"], "Approved"))
        self.assertIn("Notion now files it under demo 2026-W06", row["note"])
        self.assertIn("KB page is now", row["note"])
        _, out = self.run_hook(query(ROWS[1:3], filter=WEEK_FILTER))
        self.assertIn("not in a complete Notion query", self.rows()[0]["note"])

    def test_an_edit_between_the_packet_and_the_decision_is_noted(self):
        pending = dict(ROWS[0])
        pending.pop("Approval")
        self.run_hook(query([pending]))
        self.assertEqual(len(self.rows()[0]["kb_sha256"]), 64)
        (self.root / ROWS[0]["KB page"]).write_text("# changed while the Board was reviewing\n")
        self.run_hook(query([ROWS[0]]))
        self.assertIn("changed after the last sync before the decision", self.rows()[0]["note"])

    def test_rows_not_approved_refresh_their_hash_and_approval_compares_with_the_last(self):
        changes = dict(ROWS[0], Approval="Changes")
        self.run_hook(query([changes]))
        page = self.root / ROWS[0]["KB page"]
        page.write_text("# fixed after Changes\n")
        self.run_hook(query([changes]))
        self.assertEqual(self.rows()[0]["kb_sha256"], hashlib.sha256(page.read_bytes()).hexdigest())
        self.run_hook(query([ROWS[0]]))
        self.assertEqual((self.rows()[0]["approval"], self.rows()[0]["note"]), ("Approved", ""))

    def test_an_edit_between_the_decision_and_its_sync_is_noted(self):
        changes = dict(ROWS[0], Approval="Changes")
        self.run_hook(query([changes]))
        (self.root / ROWS[0]["KB page"]).write_text("# edited after the Board's tap, before the sync\n")
        self.run_hook(query([ROWS[0]]))
        self.assertIn("changed after the last sync before the decision", self.rows()[0]["note"])
        self.run_hook(query([ROWS[0]]))
        self.assertIn("changed after the last sync before the decision", self.rows()[0]["note"])  # sticky

    def test_a_kb_page_set_only_at_the_decision_is_noted(self):
        empty = dict(ROWS[0], **{"KB page": ""})
        empty.pop("Approval")
        self.run_hook(query([empty]))
        self.run_hook(query([ROWS[0]]))
        self.assertIn("KB page changed after the last sync before the decision", self.rows()[0]["note"])

    def test_a_decision_with_no_earlier_hash_is_noted(self):
        empty = dict(ROWS[0], **{"KB page": ""})
        pending = dict(empty)
        pending.pop("Approval")
        self.run_hook(query([pending]))
        self.run_hook(query([empty]))
        self.assertIn("no earlier hash to compare", self.rows()[0]["note"])

    def test_filtered_or_partial_queries_never_change_a_decision(self):
        self.run_hook(query(ROWS))
        before = self.page.read_text()
        revoked = dict(ROWS[0], Approval="Rejected")
        approval_filter = {"type": "group", "operator": "and", "filters": [
            {"type": "property", "property": "Approval", "propertyType": "select", "operator": "is_empty"}]}
        for event in (query([revoked], filter=approval_filter), query([revoked], has_more=True)):
            _, out = self.run_hook(event)
            self.assertIn("not synced", out)
        self.assertEqual(self.page.read_text(), before)

    def test_an_item_gone_from_a_complete_week_is_noted_not_removed(self):
        self.run_hook(query(ROWS))
        self.run_hook(query(ROWS[1:3], filter=WEEK_FILTER))
        rows = self.rows()
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["approval"], "Approved")
        self.assertIn("not in a complete Notion query", rows[0]["note"])

    def test_unchanged_rows_leave_the_page_alone(self):
        self.run_hook(query(ROWS))
        before = self.page.read_text()
        _, out = self.run_hook(query(ROWS))
        self.assertEqual(self.page.read_text(), before)
        self.assertIn("unchanged", out)

    def test_the_ai_label_is_the_boards_tick_refreshed_after_the_decision(self):
        self.run_hook(query(ROWS))
        before = self.rows()
        self.assertEqual([r["ai_label"] for r in before], ["off", "off", "off"])
        self.run_hook(query([dict(ROWS[0], **{"AI label": "__YES__"}), dict(ROWS[1], **{"AI label": "__NO__"}), ROWS[2]]))
        rows = self.rows()
        self.assertEqual([r["ai_label"] for r in rows], ["on", "off", "off"])
        self.assertEqual(rows[0]["approval"], "Approved")
        # the Board's own field: a change keeps the decision, its page, hash and note
        self.assertEqual(dict(rows[0], ai_label="off"), before[0])
        self.run_hook(query(ROWS))
        self.assertEqual(self.rows()[0]["ai_label"], "off")

    def test_a_bad_week_and_an_unknown_brand_are_skipped(self):
        bad = [ROWS[3], dict(ROWS[0], Brand="another"), dict(ROWS[0], Week="2026-W06\nx")]
        _, out = self.run_hook(query(bad))
        self.assertFalse((self.marketing / "founder/demo/approvals").exists())
        self.assertEqual(out.count("skipped"), 3)

    def test_a_brand_outside_founder_syncs_to_its_folder(self):
        content = self.marketing / "acme/content/2026-W06"
        content.mkdir(parents=True)
        (content / "a-reel.md").write_text("# a reel\n")
        item = dict(ROWS[0], Brand="acme", Week="2026-W06", url="https://app.notion.com/p/a-reel",
                    **{"KB page": "knowledge/marketing/acme/content/2026-W06/a-reel.md"})
        brand = {"type": "property", "property": "Brand", "operator": "enum_is", "value": {"type": "exact", "value": "acme"}}
        w06 = dict(WEEK_FILTER["filters"][0], value={"type": "exact", "value": "2026-W06"})
        _, out = self.run_hook(query([item], filter=dict(WEEK_FILTER, filters=[w06, brand])))
        self.assertIn("acme/approvals/2026-W06.md: 1 items", out)
        [row] = read_rows(self.marketing / "acme/approvals/2026-W06.md")
        self.assertEqual((row["approval"], row["note"]), ("Approved", "first synced after the decision: no earlier "
                                                                       "hash to compare"))

    def test_it_does_nothing_until_the_calendar_is_set(self):
        for settings in ({}, {"integrations": {"marketing": {"brands": {"founder/demo": {}}}}}):
            (self.root / "company.json").write_text(json.dumps(settings))
            self.assertEqual(self.run_hook(query(ROWS, data_source_url="collection://")), (0, ""))
            self.assertEqual(self.run_hook(query(ROWS)), (0, ""))
        self.assertFalse(self.page.exists())

    def test_a_broken_company_json_never_blocks_or_writes(self):
        (self.root / "company.json").write_text("{not json")
        self.assertEqual(self.run_hook(query(ROWS)), (0, ""))
        self.assertFalse(self.page.exists())

    def test_other_queries_are_ignored(self):
        for event in (query([], mode="sql"), query([], data_source_url="collection://other"),
                      dict(EVENT, tool_name="mcp__claude_ai_Notion__notion-fetch")):
            with self.subTest(event=event["tool_name"]):
                self.assertIsNone(calendar_query(event, self.root))
                self.assertEqual(self.run_hook(event), (0, ""))

    def test_unreadable_responses_never_block_or_write(self):
        for text in ("Notion error: rate limited", json.dumps({"results": {"a": 1}}), json.dumps({"results": [1]})):
            with self.subTest(text=text):
                event = dict(EVENT, tool_response=[{"type": "text", "text": text}])
                self.assertEqual(self.run_hook(event), (0, ""))
        self.assertFalse(self.page.exists())

    def test_kb_page_outside_marketing_is_never_read(self):
        sneaky = dict(ROWS[0], **{"KB page": "../../../etc/passwd"})
        self.run_hook(query([sneaky]))
        self.assertEqual(self.rows()[0]["kb_sha256"], "not a marketing KB page")


class Render(unittest.TestCase):
    def test_says_who_writes_it(self):
        page = render("founder/demo", "2026-W05", [], "2026-01-01T10:00:00Z")
        self.assertIn("scripts/notion_approvals_sync.py", page)
        self.assertIn('title: "Board approvals: demo, 2026-W05"', page)


if __name__ == "__main__":
    unittest.main()
