"""Tests for scripts/board_desk/adapter_notion.py.

Notion is faked at send(): each answer is shaped as Notion's API reference shows it (a page object with
last_edited_by and properties, a paginated list with has_more and next_cursor, an error object with code). Nothing
here reads the Keychain or calls the network: Redirect's servers listen on 127.0.0.1 alone."""

import http.server
import json
import shutil
import sys
import tempfile
import threading
import unittest
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "board_desk"))

import adapter_notion as notion  # noqa: E402

BLOB = "https://github.com/example/company/blob/main/"


def setUpModule():
    """The answers' seal in a temporary folder (no test writes the live one), and settings that are the tests' own,
    whatever company.json says."""
    seals = tempfile.TemporaryDirectory()
    unittest.addModuleCleanup(seals.cleanup)
    for patch in (mock.patch.object(notion.answers_seal, "SEAL_DIR", Path(seals.name) / "seal"),
                  mock.patch.object(notion, "ZONE", ZoneInfo("Asia/Dhaka")),
                  mock.patch.object(notion, "ZONE_NAME", "Dhaka"), mock.patch.object(notion, "GITHUB", BLOB)):
        patch.start()
        unittest.addModuleCleanup(patch.stop)


BOT, BOARD = "b0700000-0000-4000-8000-000000000001", "b0a7d000-0000-4000-8000-000000000002"
OTHER = "0c0c0000-0000-4000-8000-000000000003"
ASKS, NOTES = "da7a0000-0000-4000-8000-0000000000a5", "da7a0000-0000-4000-8000-0000000000b6"
PAGE = "9a9e0000-0000-4000-8000-000000000010"
ROW = "a0a00000-0000-4000-8000-000000000012"
STEPS = "9a9e0000-0000-4000-8000-000000000020"  # a page of long commands
QA_SOURCE = "da7a0000-0000-4000-8000-0000000000c7"
QA_PAGE = "knowledge/company/board-desk/qa.md"


def user(identity, kind="person", name="Someone"):
    return {"object": "user", "id": identity, "type": kind, "name": name, "avatar_url": None,
            **({"person": {"email": "someone@example.com"}} if kind == "person" else {"bot": {}})}


def rich_text(text):
    return [{"type": "text", "text": {"content": text, "link": None}, "annotations": {"bold": False}, "plain_text": text,
             "href": None}]


def page(identity, editor, edited="2026-01-16T15:04:00.000Z", answer=None, words=None, trash=False):
    properties = {"Id": {"id": "title", "type": "title", "title": rich_text("A-1")}}
    if answer is not None:
        properties["Your answer"] = {"id": "%3Fa", "type": "select",
                                     "select": {"id": "1", "name": answer, "color": "green"} if answer else None}
    if words is not None:
        properties["Your words"] = {"id": "%3Fw", "type": "rich_text", "rich_text": rich_text(words)}
    return {"object": "page", "id": identity, "created_time": "2026-01-16T14:00:00.000Z", "last_edited_time": edited,
            "created_by": {"object": "user", "id": BOT}, "last_edited_by": {"object": "user", "id": editor},
            "in_trash": trash, "archived": trash, "parent": {"type": "data_source_id", "data_source_id": ASKS},
            "properties": properties, "url": f"https://www.notion.so/{identity.replace('-', '')}"}


B_ROW, CEO_ROW = "a0a00000-0000-4000-8000-0000000000b1", "a0a00000-0000-4000-8000-0000000000c1"


def board_row(identity, title="Can we ship on Friday?", edited="2026-01-19T06:01:00.000Z", editor=BOARD, trash=False):
    """A row the Board added to the Q&A database: made by the Board, its title its question, the CEO's columns
    empty."""
    return {"object": "page", "id": identity, "created_time": edited, "last_edited_time": edited,
            "created_by": {"object": "user", "id": BOARD}, "last_edited_by": {"object": "user", "id": editor},
            "in_trash": trash, "archived": trash, "parent": {"type": "data_source_id", "data_source_id": QA_SOURCE},
            "properties": {"Question": {"id": "title", "type": "title", "title": rich_text(title)},
                           "Answer": {"id": "%3Fn", "type": "rich_text", "rich_text": []}},
            "url": f"https://www.notion.so/{identity.replace('-', '')}"}


D_SOURCE = "da7a0000-0000-4000-8000-0000000000d8"
D_ROW = "a0a00000-0000-4000-8000-0000000000d1"


def directive_row(identity, creator=BOARD, editor=BOARD):
    """A row of the Directives database: one the Board added (creator), or one the connection made."""
    return {"object": "page", "id": identity, "created_time": "2026-01-19T08:00:00.000Z",
            "last_edited_time": "2026-01-19T08:00:00.000Z", "created_by": {"object": "user", "id": creator},
            "last_edited_by": {"object": "user", "id": editor}, "in_trash": False, "archived": False,
            "parent": {"type": "data_source_id", "data_source_id": D_SOURCE},
            "properties": {"Directive": {"id": "title", "type": "title", "title": rich_text("Make the logo")},
                           "Status": {"id": "%3Fs", "type": "select", "select": None},
                           "Id": {"id": "%3Fi", "type": "rich_text", "rich_text": []}},
            "url": f"https://www.notion.so/{identity.replace('-', '')}"}


def paragraph(identity, text, children=False):
    return {"object": "block", "id": identity, "type": "paragraph", "has_children": children,
            "paragraph": {"rich_text": rich_text(text) if text else []}}


def units(text):
    """A text's length as Notion counts it: UTF-16 units."""
    return len(text.encode("utf-16-le")) // 2


def listing(results, cursor=None):
    return {"object": "list", "results": results, "next_cursor": cursor, "has_more": cursor is not None,
            "type": "page_or_data_source", "page_or_data_source": {}}


class FakeSend:
    """send(method, url, headers, data): the next answer queued for (method, path), as (status, Retry-After, JSON)."""

    def __init__(self):
        self.answers, self.calls = {}, []

    def queue(self, method, path, *answers):
        self.answers.setdefault((method, path), []).extend(
            answer if isinstance(answer, tuple) else (200, None, answer) for answer in answers)

    def __call__(self, method, url, headers, data):
        path = url[len(notion.API):].split("?")[0]
        self.calls.append((method, path, headers, json.loads(data) if data else None, url))
        queued = self.answers.get((method, path))
        if not queued:
            raise AssertionError(f"no answer queued for {method} {path}")
        return queued.pop(0)


class Client(unittest.TestCase):
    def setUp(self):
        self.send, self.slept, self.reads = FakeSend(), [], []

        def token():
            self.reads.append(1)
            return "test-token"

        self.notion = notion.Notion(token=token, send=self.send, sleep=self.slept.append)

    def test_each_call_names_the_version_and_reads_the_token_once(self):
        self.send.queue("GET", "/users/me", user(BOT, "bot"), user(BOT, "bot"))
        self.notion.call("GET", "/users/me")
        self.notion.call("GET", "/users/me")
        _, _, headers, _, _ = self.send.calls[0]
        self.assertEqual(headers["Notion-Version"], "2026-03-11")
        self.assertEqual(headers["Authorization"], "Bearer test-token")
        self.assertEqual(self.reads, [1])

    def test_a_board_only_property_in_a_page_write_is_never_sent(self):
        for field in notion.BOARD_FIELDS:
            with self.subTest(field=field):
                with self.assertRaises(notion.NotionError):
                    self.notion.call("PATCH", f"/pages/{ROW}", {"properties": {field: {"rich_text": rich_text("Yes")}}})
        self.assertEqual(self.send.calls, [])
        self.assertEqual(self.reads, [])

    def test_429_and_5xx_wait_as_told_capped_then_give_up(self):
        self.send.queue("GET", "/users/me", (429, "2", {"code": "rate_limited"}), (503, "999", {}), user(BOT, "bot"))
        self.assertEqual(self.notion.call("GET", "/users/me")["id"], BOT)
        self.assertEqual(self.slept, [2.0, 60])
        self.send.queue("GET", "/users", *[(503, None, {"code": "service_unavailable"})] * 4)
        with self.assertRaises(notion.NotionError) as raised:
            self.notion.call("GET", "/users")
        self.assertEqual(raised.exception.status, 503)

    def test_an_error_names_its_status_and_code_never_its_body(self):
        self.send.queue("POST", "/pages", (400, None, {"object": "error", "status": 400, "code": "validation_error",
                                                       "message": "body.properties.Words: a private word"}))
        with self.assertRaises(notion.NotionError) as raised:
            self.notion.call("POST", "/pages", {"parent": {"page_id": PAGE}})
        self.assertEqual(str(raised.exception), "Notion 400: validation_error")

    def test_a_refusal_names_notion_s_message_never_the_page_s_text_or_the_token(self):
        """An error keeps Notion's own message for a log line (named()): on one line, each value it quotes but a number
        as "…", any 20 characters in a row of the request's page text as "…", never the token, at most 200 characters;
        str() stays the status and code."""
        words = "Σχεδιάστε ένα σύντομο βίντεο 🤖 για τον νέο φούρνο, παρακαλώ"
        limit = ("body failed validation: body.properties.Your words (verbatim).rich_text[0].text.content.length "
                 "should be ≤ `2000`, instead was `2004`.")
        cases = [(limit, limit),
                 ("body.properties.Status.select.name should be a string, instead was `\"open, two-way\"`.",
                  "body.properties.Status.select.name should be a string, instead was `…`."),
                 (f"Could not parse the markdown:\n  {words} near line 3", "Could not parse the markdown: … near line 3"),
                 ("The token test-token can't edit this page.", "The token … can't edit this page."),
                 ("`" + "v" * 992 + "` test-token is not ours.", "`…` … is "),  # the token across character 1,000
                 # removed before the message is cut there
                 ("Notion says no. " * 20, "Notion says no. " * 12 + "Notion …")]
        body = {"properties": {"Your words (verbatim)": {"rich_text": notion.rich(words)}},
                "markdown": {"new_str": "A page's line, whole.\n"}}
        for message, logged in cases:
            with self.subTest(message=message[:30]):
                self.send.queue("POST", "/pages", (400, None, {"object": "error", "status": 400,
                                                               "code": "validation_error", "message": message}))
                with self.assertRaises(notion.NotionError) as raised:
                    self.notion.call("POST", "/pages", body)
                self.assertEqual((str(raised.exception), raised.exception.message), ("Notion 400: validation_error", logged))
                self.assertEqual(raised.exception.named(), f"Notion 400: validation_error: {logged}")
                self.assertLessEqual(len(raised.exception.named()) - len("Notion 400: validation_error: "),
                                     notion.MESSAGE_CUT)
        self.send.queue("GET", f"/pages/{ROW}", (404, None, {"object": "error", "code": "object_not_found"}))
        with self.assertRaises(notion.NotionError) as raised:  # no message: named() is str() alone
            self.notion.call("GET", f"/pages/{ROW}")
        self.assertEqual(raised.exception.named(), "Notion 404: object_not_found")

    def test_a_value_open_across_the_cut_and_a_wrapped_token_are_never_shown(self):
        """A quoted value the 1,000-character cut leaves open (900 v quoted, then 218 characters quoted across the cut)
        is "…" to the end, as one Notion's message leaves open; the token is removed wherever white space splits it."""
        cases = [("`" + "v" * 900 + "` instead was `Q value here 12345" + "x" * 200 + "`", "`…` instead was `…"),
                 ('instead was "He said, and now and then', 'instead was "…'),
                 ("The token test-\ntoken can't edit this page.", "The token … can't edit this page."),
                 ("The token test- \r\n  tok\u00a0en, then `2004`.", "The token …, then `2004`.")]
        for message, logged in cases:
            with self.subTest(message=message[-30:]):
                self.send.queue("POST", "/pages", (400, None, {"code": "validation_error", "message": message}))
                with self.assertRaises(notion.NotionError) as raised:
                    self.notion.call("POST", "/pages", {"parent": {"page_id": PAGE}})
                self.assertEqual(raised.exception.message, logged)
                self.assertNotIn("Q value", raised.exception.named())
                self.assertNotIn("tok", raised.exception.message.replace("The token", ""))

    def test_a_list_is_read_to_its_end(self):
        self.send.queue("GET", "/users", listing([user(BOARD, name="The Board"), user(BOT, "bot")], cursor="c2"),
                        listing([user(OTHER, name="A partner")]))
        people = self.notion.people()
        self.assertEqual(people, [(BOARD, "The Board"), (OTHER, "A partner")])
        self.assertNotIn("example.com", repr(people))
        self.assertIn("start_cursor=c2", self.send.calls[1][4])

    def test_a_database_s_views_and_their_sorts_a_listed_view_without_them_read_whole(self):
        """Views are listed by database_id (a GET's query, every page); each one's sorts as (property, direction)
        pairs, in Notion's order."""
        self.send.queue("GET", "/views", listing([{"object": "view", "id": "v1"}], cursor="c2"),
                        listing([{"object": "view", "id": "v2", "sorts": []}]))
        self.send.queue("GET", "/views/v1", {"object": "view", "id": "v1", "sorts": [
            {"property": "No.", "direction": "descending"}]})
        self.assertEqual(notion.views(self.notion, "db-1"), [("v1", (("No.", "descending"),)), ("v2", ())])
        listed = [url for method, path, _, _, url in self.send.calls if path == "/views"]
        self.assertEqual([urllib.parse.parse_qs(urllib.parse.urlsplit(url).query) for url in listed],
                         [{"database_id": ["db-1"], "page_size": ["100"]},
                          {"database_id": ["db-1"], "page_size": ["100"], "start_cursor": ["c2"]}])
        self.assertEqual(notion.sort_words(()), "nothing")


class Redirect(unittest.TestCase):
    """urllib's own redirect handler would send the token's header to the host a redirect names; https() refuses every
    redirect, so nothing reaches that host."""

    def serve(self, handler):
        server = http.server.HTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return server

    def test_a_redirect_to_another_host_sends_no_second_request_and_no_token(self):
        reached = []

        class Quiet(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

        class Elsewhere(Quiet):
            def do_GET(self):
                reached.append((self.command, dict(self.headers)))
                self.send_response(200)
                self.send_header("Content-Length", "2")
                self.end_headers()
                self.wfile.write(b"{}")

            do_POST = do_GET

        elsewhere = self.serve(Elsewhere)

        class Moved(Quiet):
            def do_GET(self):
                self.send_response(302 if self.command == "GET" else 303)
                self.send_header("Location", f"http://localhost:{elsewhere.server_port}/v1/users/me")
                self.send_header("Content-Length", "0")
                self.end_headers()

            do_POST = do_GET

        moved = self.serve(Moved)
        for method, data, status in (("GET", None, 302), ("POST", b"{}", 303)):
            with self.subTest(method=method):
                with self.assertRaises(notion.NotionError) as raised:
                    notion.https(method, f"http://127.0.0.1:{moved.server_port}/v1/users/me",
                                 {"Authorization": "Bearer test-token", "Content-Type": "application/json"}, data)
                self.assertEqual((raised.exception.status, raised.exception.code), (status, "redirect"))
                self.assertNotIn("test-token", str(raised.exception))
        self.assertEqual(reached, [])


class Texts(unittest.TestCase):
    def test_a_kb_page_as_notion_shows_it(self):
        page_text = ("---\ntitle: x\nowner: ceo\n---\n\n# Progress\n<!-- for the writer -->\nSee [the gist](../gist.md) "
                     "and [Notion](https://www.notion.so/help).\n")
        self.assertEqual(notion.notion_text(page_text),
                         "# Progress\nSee the gist and [Notion](https://www.notion.so/help).\n")

    def test_a_page_s_text_keeps_each_link_s_target_and_each_card_s_url(self):
        """A link's target follows its text, a bookmark's or an image's url its caption; a file uploaded to Notion goes
        by its name, never its signed url."""
        link = {"type": "text", "text": {"content": "the doc"}, "plain_text": "the doc",
                "href": "https://example.org/d"}
        blocks = [{"type": "paragraph", "paragraph": {"rich_text": [link] + rich_text(", please.")}},
                  {"type": "bookmark", "bookmark": {"url": "https://example.org/a", "caption": []}},
                  {"type": "image", "image": {"type": "external", "external": {"url": "https://example.org/i.png"},
                                              "caption": rich_text("A chart")}},
                  {"type": "file", "file": {"type": "file", "name": "plan.pdf", "caption": [],
                                            "file": {"url": "https://files.example/plan.pdf?X-Amz-Signature=abc"}}}]
        text = notion.page_text(blocks)
        self.assertEqual(text, "the doc (https://example.org/d), please.\nhttps://example.org/a\n"
                               "A chart (https://example.org/i.png)\nplan.pdf")
        self.assertNotIn("Signature", text)

    def test_a_column_the_board_adds_is_read_by_its_type_never_a_person_or_a_computed_one(self):
        """A column the Board may add to Q&A, of a type it fills in, is its words."""
        cases = [({"type": "multi_select", "multi_select": [{"name": "a"}, {"name": "b"}]}, "a, b"),
                 ({"type": "number", "number": 3}, "3"), ({"type": "checkbox", "checkbox": True}, "yes"),
                 ({"type": "date", "date": {"start": "2026-01-20", "end": None}}, "2026-01-20"),
                 ({"type": "url", "url": "https://example.org"}, "https://example.org"),
                 ({"type": "people", "people": [{"object": "user", "id": "u1"}]}, ""),
                 ({"type": "last_edited_time", "last_edited_time": "2026-01-19T06:01:00.000Z"}, ""),
                 ({"type": "select", "select": {"name": "urgent"}}, "urgent")]
        self.assertEqual([notion.column_text(prop) for prop, _ in cases], [text for _, text in cases])

    def test_rich_text_is_cut_at_notion_s_limit(self):
        parts = notion.rich("x" * 4001)
        self.assertEqual([len(part["text"]["content"]) for part in parts], [2000, 2000, 1])

    def test_notion_counts_an_emoji_as_two_so_no_part_or_block_is_over_its_limit(self):
        """Notion counts a text's length in UTF-16 units, a character past U+FFFF (most emoji) 2. A text of 2,000
        characters with 4 emoji is 2,004, which Notion refuses; each part rich() and rich_parts() make, and each block
        within_limit() leaves, is within 2,000 that way, the text whole and in order."""
        text = "🤖📸" * 2 + "Σχεδιάστε " * 199 + "x" * 6
        self.assertEqual((len(text), units(text)), (2000, 2004))
        for parts in (notion.rich(text), notion.rich_parts([(text, "https://example.org/r")])):
            contents = [part["text"]["content"] for part in parts]
            self.assertEqual(([units(content) for content in contents], "".join(contents)), ([2000, 4], text))
        self.assertEqual([part["text"]["content"] for part in notion.rich("x" * 1999 + "🤖y")], ["x" * 1999, "🤖y"])
        self.assertEqual(notion.rich("🤖" * 1000), [{"type": "text", "text": {"content": "🤖" * 1000}}])
        prose = ("ab 🤖 " * 400).strip()  # 1,999 characters, 2,399 units
        code = ["echo 🤖" * 45] * 7  # 7 lines of 270 characters: 1,896 with their line breaks, 2,211 units
        page = "\n".join([prose, "", "```", *code, "```"])
        cut = notion.within_limit(page)
        self.assert_within_limit(cut)
        self.assertEqual(" ".join(line for line in cut.split("\n") if line and "echo" not in line and "`" not in line),
                         prose)
        self.assertEqual(([line for line in cut.split("\n") if "echo" in line], cut.count("```")), (code, 4))

    def test_a_cut_at_notion_s_limit_keeps_an_emoji_family_and_a_letter_s_accent_whole(self):
        """A part or block boundary never falls before a combining mark or beside a zero-width joiner, so it moves back
        to the cluster's start; the text stays whole and in order, each part within 2,000 units; a cluster longer than
        the limit is still cut, never into an empty part."""
        family = "👨\u200d👩\u200d👧"
        for text, first in (("x" * 1998 + family + "y", "x" * 1998), ("x" * 1999 + "e\u0301y", "x" * 1999),
                            ("x" * 1999 + "\u200dy", "x" * 1998), ("x" * 1999 + "🤖y", "x" * 1999)):
            with self.subTest(text=text[-6:]):
                contents = [part["text"]["content"] for part in notion.rich(text)]
                self.assertEqual((contents[0], "".join(contents)), (first, text))
                self.assertTrue(all(units(part) <= notion.TEXT_LIMIT for part in contents))
                self.assertEqual(notion.cut(text, prose=False), contents)
        marks = "e" + "\u0301" * 2500
        self.assertEqual([len(part["text"]["content"]) for part in notion.rich(marks)], [2000, 501])

    def test_a_rich_text_of_over_100_parts_keeps_its_text_within_notion_s_100(self):
        """Notion takes at most 100 parts in one rich text; past them the links go and the text stays whole, as
        markdown, in parts of 2,000; past 100 of those it is cut (the row's body has it)."""
        parts = [("Q-2", "https://www.notion.so/a0"), (" and ", None)] * 60
        self.assertEqual(len(notion.rich_parts(parts[:100])), 100)
        self.assertEqual(notion.rich_parts(parts[:100])[0]["text"]["link"], {"url": "https://www.notion.so/a0"})
        rich = notion.rich_parts(parts)
        self.assertEqual(("".join(part["text"]["content"] for part in rich), [part["text"].get("link") for part in rich]),
                         ("[Q-2](https://www.notion.so/a0) and " * 60, [None, None]))  # 2,160 characters: 2 parts
        self.assertEqual([len(part["text"]["content"]) for part in notion.rich_parts([("x" * 300000, None)])],
                         [notion.TEXT_LIMIT] * notion.PARTS_LIMIT)

    def test_property_values_as_plain_text(self):
        self.assertEqual(notion.text_of({"type": "select", "select": {"name": "Yes"}}), "Yes")
        self.assertEqual(notion.text_of({"type": "select", "select": None}), "")
        self.assertEqual(notion.text_of({"type": "rich_text", "rich_text": rich_text("a") + rich_text("b")}), "ab")
        self.assertEqual(notion.text_of(None), "")

    def test_a_q_and_a_row_s_links(self):
        """A KB path, relative to the page, becomes the file on GitHub's main (its anchor kept); a web link stays as
        given; a path out of the repo stays text; a Q-id links to its row only once that row exists."""
        for link, url in [("../../board/directives/D-1.md", BLOB + "knowledge/board/directives/D-1.md"),
                          ("asks.md#open", BLOB + "knowledge/company/board-desk/asks.md#open"),
                          ("../../../scripts/board_desk.py", BLOB + "scripts/board_desk.py"),
                          ("https://github.com/example/acme/pull/89", "https://github.com/example/acme/pull/89"),
                          ("../../../../outside.md", ""), ("/etc/hosts", "")]:
            with self.subTest(link=link):
                self.assertEqual(notion.target(link, QA_PAGE), url)
        rows = {"Q-2": "a0a00000-0000-4000-8000-0000000000c2"}
        self.assertEqual(notion.linked("Asked before: Q-2 and Q-3; [Q-2](asks.md).", QA_PAGE, rows), [
            ("Asked before: ", None), ("Q-2", "https://www.notion.so/a0a000000000400080000000000000c2"),
            (" and Q-3; ", None), ("Q-2", BLOB + "knowledge/company/board-desk/asks.md"), (".", None)])
        self.assertEqual(notion.linked("[out](../../../../x.md)", QA_PAGE, {}), [("out", None)])

    def assert_within_limit(self, markdown):
        """Each block Notion would make of markdown: a fenced code block's text, or another line (one paragraph,
        item or heading), a table's rows aside; none over the limit as Notion counts (units()), every fence closed."""
        fence = None
        for line in markdown.split("\n"):
            if fence is None and notion.FENCE.match(line):
                fence, code = notion.FENCE.match(line).group(1), []
            elif fence is not None and line.strip() == fence:
                self.assertLessEqual(units("\n".join(code)), notion.TEXT_LIMIT)
                fence = None
            elif fence is not None:
                code.append(line)
            elif not line.startswith("|"):
                self.assertLessEqual(units(line), notion.TEXT_LIMIT)
        self.assertIsNone(fence)

    def test_within_limit_cuts_only_a_block_over_notion_s_limit(self):
        """A code block over 2,000 characters becomes several, cut between lines (a line over it, inside), with its
        language; a paragraph over it, several, at spaces; nothing is lost, and everything else is as it was."""
        short = "# Steps\n\n```bash\nnpm test\n```\n\n| a | b |\n"
        self.assertEqual(notion.within_limit(short), short)
        commands = [f"acme env add KEY_{n:03d} production --value-from-file ./k/{n:03d}.txt" for n in range(90)]
        prose = " ".join(["Open the page and press the button."] * 130)
        row = "| " + "x" * 2500 + " |"
        page = "\n".join(["## B-2", "```bash", *commands, "```", "", prose, "", row, "", "````", "z" * 4500, "````"])
        cut = notion.within_limit(page)
        self.assert_within_limit(cut)
        self.assertEqual(cut.count("```bash"), 3)
        self.assertEqual([line for line in cut.split("\n") if line.startswith("acme")], commands)
        words = set(prose.split())
        self.assertEqual(" ".join(line for line in cut.split("\n") if line and set(line.split()) <= words), prose)
        self.assertIn("\n" + row + "\n", cut)
        self.assertEqual("".join(line for line in cut.split("\n") if line.startswith("z")), "z" * 4500)
        self.assertEqual(cut.count("````"), 6)

    def test_markdown_as_the_blocks_added_to_a_board_row_s_page(self):
        """What replace_blocks() adds: a heading, list items with their bold and links, a fenced code block whole, other
        lines as paragraphs, blank lines left out; a long line within the limit."""
        body = ("### 13:00-14:00 Dhaka\n\n- **Answer:** see [asks](asks.md) and [PR](https://x.test/1)\n"
                "1. first\n```bash\nnpm test\n\nnpm run lint\n```\nplain " + "y" * 2500)
        blocks = notion.blocks_of(body)
        self.assertEqual([block["type"] for block in blocks],
                         ["heading_3", "bulleted_list_item", "numbered_list_item", "code", "paragraph"])
        self.assertEqual(blocks[0]["heading_3"]["rich_text"], [{"type": "text", "text": {"content": "13:00-14:00 Dhaka"}}])
        self.assertEqual(blocks[1]["bulleted_list_item"]["rich_text"], [
            {"type": "text", "text": {"content": "Answer:"}, "annotations": {"bold": True}},
            {"type": "text", "text": {"content": " see "}}, {"type": "text", "text": {"content": "asks"}},
            {"type": "text", "text": {"content": " and "}},
            {"type": "text", "text": {"content": "PR", "link": {"url": "https://x.test/1"}}}])
        self.assertEqual(blocks[3]["code"], {"rich_text": [{"type": "text", "text": {"content": "npm test\n\nnpm run lint"}}],
                                             "language": "plain text"})
        self.assertEqual([len(part["text"]["content"]) for part in blocks[4]["paragraph"]["rich_text"]], [2000, 506])


class Desk(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        notion.save_ids(self.root, {"bot": BOT, "root": PAGE, "pages": {"progress": PAGE},
                                    "databases": {"asks": {"database": "d1", "data_source": ASKS},
                                                  "notes": {"database": "d2", "data_source": NOTES}},
                                    "rows": {ROW: "A-1", "a0a00000-0000-4000-8000-0000000000ff": notion.TEST_ROW}})
        self.send, self.logs = FakeSend(), []
        client = notion.Notion(token=lambda: "test-token", send=self.send, sleep=lambda seconds: None)
        self.desk = notion.Desk(self.root, lambda why, data: self.logs.append((why, data)), client)
        self.now = datetime(2026, 1, 16, 15, 7, 30, tzinfo=timezone.utc)

    def bodies(self, method, path):
        return [body for m, p, _, body, _ in self.send.calls if (m, p) == (method, path)]

    def test_in_trash_reads_one_page(self):
        """For board_desk.audit(): in the trash, live, or no such row."""
        self.send.queue("GET", f"/pages/{ROW}", page(ROW, BOARD, answer="Yes", trash=True), page(ROW, BOARD),
                        (404, None, {"object": "error", "status": 404, "code": "object_not_found"}))
        self.assertEqual([self.desk.in_trash(ROW, "A-1", "Your answer", "Yes") for _ in range(3)], [True, False, None])
        self.assertEqual([(m, p) for m, p, *_ in self.send.calls], [("GET", f"/pages/{ROW}")] * 3)

    def test_in_trash_counts_only_the_row_s_own_page_never_one_the_desk_trashed(self):
        """The trash counts only for the answers row's own page (its Id the row's ask id, its field the row's words, in
        one of the desk's databases), and never for one the daily cleanup trashed (notion.json's "trashed", trash()) or
        the connection last edited: a forged row reusing such an id is no answer."""
        def asked(*pages, ids=None):
            if ids:
                self.desk.ids.update(ids)
            for each in pages:
                self.send.queue("GET", f"/pages/{ROW}", each)
            return [self.desk.in_trash(ROW, "A-1", "Your words", "Go\r\n") for _ in pages]

        own = page(ROW, BOARD, words="Go", trash=True)
        self.assertEqual(asked(own, page(ROW, BOARD, words="Not this", trash=True), page(ROW, BOARD, trash=True),
                               page(ROW, BOT, words="Go", trash=True),
                               own | {"parent": {"type": "data_source_id", "data_source_id": "elsewhere"}}),
                         [True, False, False, False, False])
        other = page(ROW, BOARD, words="Go", trash=True)
        other["properties"]["Id"] = {"id": "title", "type": "title", "title": rich_text("A-2")}
        self.assertEqual(asked(other), [False])
        self.assertEqual(asked(own, ids={"trashed": {ROW: "A-1, answered"}}), [False])

    def test_poll_reads_both_data_sources_from_the_minute_once_each(self):
        twice = page(ROW, BOARD, answer="Yes", words="Go")
        self.send.queue("POST", f"/data_sources/{ASKS}/query",
                        listing([twice, page("a0a00000-0000-4000-8000-000000000099", OTHER, answer="Yes")], cursor="n"),
                        listing([twice, page("a0a00000-0000-4000-8000-0000000000ff", BOARD, words="phone"),
                                 page("a0a00000-0000-4000-8000-000000000098", BOARD, answer="Yes", trash=True)]))
        self.send.queue("POST", f"/data_sources/{NOTES}/query", listing([page("n0", BOARD, words="A note")]))
        changes = self.desk.poll(datetime(2026, 1, 16, 15, 3, 45, tzinfo=timezone.utc))
        query = self.bodies("POST", f"/data_sources/{ASKS}/query")
        self.assertEqual(query[0]["filter"], {"timestamp": "last_edited_time",
                                              "last_edited_time": {"on_or_after": "2026-01-16T15:03:00.000Z"}})
        self.assertEqual(query[1]["start_cursor"], "n")
        self.assertEqual([(c["medium_id"], c["ask"], c["field"], c["value"], c["editor"]) for c in changes],
                         [(ROW, "A-1", "Your answer", "Yes", BOARD), (ROW, "A-1", "Your words", "Go", BOARD),
                          ("a0a00000-0000-4000-8000-000000000099", "", "Your answer", "Yes", OTHER),
                          ("n0", "Note", "Your words", "A note", BOARD)])
        self.assertEqual(changes[0]["edited_at"], "2026-01-16T15:04:00.000Z")
        self.assertEqual(notion.load_ids(self.root)["rows"]["n0"], "Note")

    def test_poll_reads_the_ids_again(self):
        """A row the attribution test added after this Desk was made is known at the next poll (it runs under the
        reader's lock, which the attribution test holds while it writes the ids)."""
        ids = notion.load_ids(self.root)
        ids["rows"]["a0a00000-0000-4000-8000-0000000000ee"] = notion.TEST_ROW
        notion.save_ids(self.root, ids)
        self.send.queue("POST", f"/data_sources/{ASKS}/query",
                        listing([page("a0a00000-0000-4000-8000-0000000000ee", BOARD, words="phone")]))
        self.send.queue("POST", f"/data_sources/{NOTES}/query", listing([]))
        self.assertEqual(self.desk.poll(None), [])

    def test_ready_needs_both_databases_poll_reads_not_a_page_added_since(self):
        """A page added to PAGES after setup ran doesn't stop the reads of the Board's answers until setup runs again;
        setup makes the databases after the pages."""
        ids = notion.load_ids(self.root)
        self.assertNotIn("qa", ids["pages"])
        self.assertTrue(notion.ready(ids))
        del ids["databases"]["notes"]
        self.assertFalse(notion.ready(ids))
        self.assertFalse(notion.ready(None))

    def test_a_page_or_database_setup_hasn_t_made_yet_isn_t_pushed(self):
        self.assertEqual(self.desk.push("company", "# How the company works\n", {}, self.now), "not set up")
        self.assertEqual(self.desk.push_qa("Q-1", {"page": QA_PAGE, "lines": ["Q-1"], "fields": {}}, {}),
                         "not set up")
        self.assertEqual(self.send.calls, [])
        self.assertNotIn("qa", notion.PAGES)  # a database, not a page
        self.assertEqual(notion.DATABASES["qa"][0], "Q&A")

    def test_poll_reads_a_row_the_board_added_to_q_and_a_never_a_question_of_the_ceo_s(self):
        """A row the Board added (made by the Board, no Q-id of the CEO's) is "Q&A" in notion.json from its first read,
        and its title and its page's text, whole, nested blocks too, are its Board-only fields; a row of the CEO's (its
        Q-id, or one the connection made whose id a push lost) is never read, so an edit there is never an answer."""
        ids = notion.load_ids(self.root)
        ids["rows"][CEO_ROW] = "Q-1"
        notion.save_ids(self.root, ids)
        self.with_qa()
        self.send.queue("POST", f"/data_sources/{ASKS}/query", listing([]))
        self.send.queue("POST", f"/data_sources/{NOTES}/query", listing([]))
        lost = page("a0a00000-0000-4000-8000-0000000000c9", BOARD, words="typed in a lost row")
        self.send.queue("POST", f"/data_sources/{QA_SOURCE}/query",
                        listing([page(CEO_ROW, BOARD, words="typed in the CEO's row"), board_row(B_ROW), lost,
                                 board_row("a0a00000-0000-4000-8000-0000000000b9", trash=True)]))
        self.send.queue("GET", f"/blocks/{B_ROW}/children",
                        listing([paragraph("k1", "Why is the deploy late?", children=True), paragraph("k3", ""),
                                 paragraph("k4", "Answer me here | please.")]))
        self.send.queue("GET", "/blocks/k1/children", listing([paragraph("k2", "And who decided it?")]))
        changes = self.desk.poll(None)
        self.assertEqual([(c["medium_id"], c["page"], c["ask"], c["field"], c["value"], c["editor"], c["edited_at"])
                          for c in changes],
                         [(B_ROW, "Q&A", "Q&A", "Question", "Can we ship on Friday?", BOARD, "2026-01-19T06:01:00.000Z"),
                          (B_ROW, "Q&A", "Q&A", "Page",
                           "Why is the deploy late?\n  And who decided it?\n\nAnswer me here | please.", BOARD,
                           "2026-01-19T06:01:00.000Z"),
                          (B_ROW, "Q&A", "Q&A", "Answer", "", BOARD, "2026-01-19T06:01:00.000Z")])  # each column too
        rows = notion.load_ids(self.root)["rows"]
        self.assertEqual((rows[B_ROW], rows[CEO_ROW], "a0a00000-0000-4000-8000-0000000000c9" in rows),
                         ("Q&A", "Q-1", False))
        read = [path for _, path, *_ in self.send.calls if path.startswith("/blocks")]
        self.assertEqual(read, [f"/blocks/{B_ROW}/children", "/blocks/k1/children"])  # the CEO's rows never
        self.assertIn("Q&A", [notion.DATABASES[key][0] for key in notion.READ_FROM])
        self.assertFalse(set(notion.DATABASES["qa"][1]) & set(notion.BOARD_FIELDS))

    def test_the_q_and_a_database_is_read_whole_once_then_from_the_minute(self):
        """A reader that has read before reads the Q&A database whole at its first read after setup made it (a row the
        Board added before is read), then as the others; a read with no since reads all."""
        self.with_qa()
        since = datetime(2026, 1, 19, 6, 3, 45, tzinfo=timezone.utc)
        for _ in range(2):
            for source in (ASKS, NOTES, QA_SOURCE):
                self.send.queue("POST", f"/data_sources/{source}/query", listing([]))
            self.assertEqual(self.desk.poll(since), [])
        first, second = self.bodies("POST", f"/data_sources/{QA_SOURCE}/query")
        self.assertEqual(("filter" in first, "filter" in second), (False, True))
        self.assertIn("filter", self.bodies("POST", f"/data_sources/{ASKS}/query")[0])
        self.assertEqual(notion.load_ids(self.root)["polled"], ["asks", "notes", "qa"])

    def board_answer(self, settled, *gets):
        """push_qa() of Q-3, which answers the Board's row B_ROW (its Row line: entry["row"]), with GET answers."""
        ids = notion.load_ids(self.root)
        ids["rows"][B_ROW] = notion.QA_ROW
        notion.save_ids(self.root, ids)
        self.with_qa()
        self.send.queue("GET", f"/pages/{B_ROW}", *gets)
        self.send.queue("GET", f"/blocks/{B_ROW}/children",
                        *[listing([paragraph("k1", "Why is the deploy late?")]) for _ in gets])
        self.send.queue("PATCH", f"/pages/{B_ROW}", board_row(B_ROW, editor=BOT))
        entry = self.entry("Q-3", "- **Answer:** Friday; see Q-1.") | {"row": B_ROW, "answered": {"Q-3": B_ROW}}
        state = {}
        return [self.desk.push_qa("Q-3", entry, state, settled) for _ in range(2)]

    def test_an_answer_goes_into_the_board_s_row_its_columns_only(self):
        """The CEO's answer is written into the row the Board added, its columns (QA_FIELDS) only: never the row's
        title or page, no row made, no markdown route, nothing trashed."""
        seen = []
        outcomes = self.board_answer(lambda row, values, edited: seen.append((row, values, edited)) or True,
                                     board_row(B_ROW))
        self.assertEqual(outcomes, ["answered", "same"])
        self.assertEqual(seen, [(B_ROW, {"Question": "Can we ship on Friday?", "Page": "Why is the deploy late?",
                                         "Answer": ""}, "2026-01-19T06:01:00.000Z")])
        sent = self.bodies("PATCH", f"/pages/{B_ROW}")
        self.assertEqual([sorted(body) for body in sent], [["properties"]])
        self.assertEqual(sorted(sent[0]["properties"]), sorted(notion.QA_FIELDS))
        self.assertEqual(notion.text_of(sent[0]["properties"]["Answer"] | {"type": "rich_text"}), "Friday; see Q-1.")
        self.assertEqual([(m, p) for m, p, *_ in self.send.calls if m != "GET"], [("PATCH", f"/pages/{B_ROW}")])
        self.assertEqual(notion.load_ids(self.root)["rows"][B_ROW], "Q&A")

    def test_an_answer_waits_while_the_board_s_words_in_the_row_are_unread(self):
        """A row the Board is editing while the read runs is left until the reader has its words (push_desk's settled,
        as push_ask's); no settled given, it is never written."""
        self.assertEqual(self.board_answer(lambda row, values, edited: False, board_row(B_ROW), board_row(B_ROW)),
                         ["skipped: words of yours the reader hasn't read yet"] * 2)
        self.assertEqual(self.bodies("PATCH", f"/pages/{B_ROW}"), [])
        self.assertEqual(self.board_answer(None, board_row(B_ROW), board_row(B_ROW)),
                         ["skipped: words of yours the reader hasn't read yet"] * 2)
        self.assertEqual(self.bodies("PATCH", f"/pages/{B_ROW}"), [])

    def test_the_board_s_words_in_a_ceo_column_of_its_row_are_never_replaced(self):
        """Text in a CEO column the desk didn't write (the Board typed in Answer when it added the row) is the Board's:
        settled() is asked about it, and the answer is written to the other columns only, the outcome naming the column
        kept."""
        typed = board_row(B_ROW)
        typed["properties"]["Answer"]["rich_text"] = rich_text("my own note here")
        seen = []
        outcomes = self.board_answer(lambda row, values, edited: seen.append(values) or True, typed, typed)
        self.assertEqual(outcomes, ["kept: Answer", "same"])
        self.assertEqual(seen[0]["Answer"], "my own note here")
        sent = self.bodies("PATCH", f"/pages/{B_ROW}")
        self.assertEqual(len(sent), 1)
        self.assertEqual(sorted(sent[0]["properties"]), sorted(set(notion.QA_FIELDS) - {"Answer"}))
        self.assertEqual(self.logs, [])

    def test_a_board_row_gone_from_notion_is_never_made_again(self):
        """A row the Board trashed or deleted stays as the Board left it: no row made, no write; it stays the Board's in
        notion.json."""
        for gone in (board_row(B_ROW, trash=True), (404, None, {"object": "error", "status": 404,
                                                                "code": "object_not_found"})):
            with self.subTest(gone=gone):
                self.send = FakeSend()
                self.desk.notion = notion.Notion(token=lambda: "test-token", send=self.send, sleep=lambda s: None)
                self.assertEqual(self.board_answer(lambda *args: True, gone, gone),
                                 ["not pushed: the row you added is gone from Notion (in its trash, or deleted)"] * 2)
                self.assertEqual([(m, p) for m, p, *_ in self.send.calls], [("GET", f"/pages/{B_ROW}")] * 2)
                self.assertEqual(notion.load_ids(self.root)["rows"][B_ROW], "Q&A")

    def test_retired_notes_are_skipped_until_restored(self):
        """Once setup retired Notes to the CEO (notion.json's "retired"), a query Notion refuses there (in its trash) is
        skipped and the read goes on; restored, it is read again. Before, a refusal there stops the read, as any
        other."""
        refusal = (404, None, {"object": "error", "status": 404, "code": "object_not_found"})
        self.send.queue("POST", f"/data_sources/{ASKS}/query", listing([]))
        self.send.queue("POST", f"/data_sources/{NOTES}/query", refusal)
        with self.assertRaises(notion.NotionError):
            self.desk.poll(None)
        ids = notion.load_ids(self.root)
        ids["retired"] = ["notes"]
        notion.save_ids(self.root, ids)
        for answer in ((400, None, {"object": "error", "status": 400, "code": "validation_error"}), refusal):
            self.send.queue("POST", f"/data_sources/{ASKS}/query", listing([page(ROW, BOARD, words="Go")]))
            self.send.queue("POST", f"/data_sources/{NOTES}/query", answer)
            self.assertEqual([c["value"] for c in self.desk.poll(None)], ["Go"])
        self.send.queue("POST", f"/data_sources/{ASKS}/query", listing([]))
        self.send.queue("POST", f"/data_sources/{NOTES}/query", listing([page("n1", BOARD, words="Restored")]))
        self.assertEqual([(c["ask"], c["value"]) for c in self.desk.poll(None)], [("Note", "Restored")])

    def with_qa(self):
        ids = notion.load_ids(self.root)
        ids["databases"]["qa"] = {"database": "d3", "data_source": QA_SOURCE}
        notion.save_ids(self.root, ids)
        self.desk = notion.Desk(self.root, lambda why, data: self.logs.append((why, data)), self.desk.notion)

    def entry(self, qid, *lines, status="current"):
        return {"page": QA_PAGE, "lines": [f"{qid} · {status} · delivery · asked 2026-01-17 09:4x", *lines],
                "fields": {"Id": qid, "Asked": "2026-01-17 09:4x", "Status": status, "Topic": "delivery",
                           "Question": "\"Why?\"", "Answer": "\n".join(line.split(":** ", 1)[-1] for line in lines),
                           "Sources": "[B-2](asks.md), [PR 89](https://github.com/example/acme/pull/89)",
                           "Asked before": "Q-1"}}

    def test_a_question_is_one_row_made_then_updated_in_place_with_its_links(self):
        """One row a Q-id, its properties and then its body through the markdown route; a KB path links to GitHub's
        main, a web link as given, a Q-id to its row once that row exists."""
        self.with_qa()
        q1, q2 = "a0a00000-0000-4000-8000-0000000000c1", "a0a00000-0000-4000-8000-0000000000c2"
        self.send.queue("POST", "/pages", page(q1, BOT), page(q2, BOT))
        for row in (q1, q2):
            self.send.queue("PATCH", f"/pages/{row}/markdown", {"object": "page_markdown", "id": row})
        state = {}
        self.assertEqual(self.desk.push_qa("Q-1", self.entry("Q-1", "- **Answer:** Yes, see Q-2."), state), "created")
        self.assertEqual(self.desk.push_qa("Q-2", self.entry("Q-2", "- **Answer:** Fixed."), state), "created")
        made = self.bodies("POST", "/pages")
        self.assertEqual(made[0]["parent"], {"type": "data_source_id", "data_source_id": QA_SOURCE})
        self.assertEqual(sorted(made[0]["properties"]), sorted(("Question",) + notion.QA_FIELDS))
        self.assertEqual(made[0]["properties"]["Answer"]["rich_text"], [{"type": "text", "text": {"content": "Yes, see Q-2."}}])
        self.assertEqual(made[1]["properties"]["Sources"]["rich_text"], [
            {"type": "text", "text": {"content": "B-2", "link": {"url": BLOB + "knowledge/company/board-desk/asks.md"}}},
            {"type": "text", "text": {"content": ", "}},
            {"type": "text", "text": {"content": "PR 89", "link": {"url": "https://github.com/example/acme/pull/89"}}}])
        self.assertEqual(made[1]["properties"]["Asked before"]["rich_text"], [
            {"type": "text", "text": {"content": "Q-1", "link": {"url": "https://www.notion.so/" + q1.replace("-", "")}}}])
        self.assertEqual(self.bodies("PATCH", f"/pages/{q1}/markdown")[0]["replace_content"]["new_str"],
                         "Q-1 · current · delivery · asked 2026-01-17 09:4x\n- **Answer:** Yes, see Q-2.\n")
        rows = notion.load_ids(self.root)["rows"]
        self.assertEqual((rows[q1], rows[q2], rows[ROW]), ("Q-1", "Q-2", "A-1"))
        # Q-2's row exists now: Q-1 is pushed again, in place, its Q-2 a link
        self.send.queue("GET", f"/pages/{q1}", page(q1, BOT))
        self.send.queue("PATCH", f"/pages/{q1}", page(q1, BOT))
        self.send.queue("PATCH", f"/pages/{q1}/markdown", {"object": "page_markdown", "id": q1})
        self.assertEqual(self.desk.push_qa("Q-1", self.entry("Q-1", "- **Answer:** Yes, see Q-2."), state), "updated")
        link = "https://www.notion.so/" + q2.replace("-", "")
        self.assertEqual(self.bodies("PATCH", f"/pages/{q1}")[0]["properties"]["Answer"]["rich_text"], [
            {"type": "text", "text": {"content": "Yes, see "}}, {"type": "text", "text": {"content": "Q-2", "link": {"url": link}}},
            {"type": "text", "text": {"content": "."}}])
        self.assertIn(f"see [Q-2]({link}).", self.bodies("PATCH", f"/pages/{q1}/markdown")[-1]["replace_content"]["new_str"])
        self.assertEqual(self.desk.push_qa("Q-1", self.entry("Q-1", "- **Answer:** Yes, see Q-2."), state), "same")
        self.assertEqual(len(self.bodies("POST", "/pages")), 2)

    def test_a_question_s_long_line_keeps_each_block_within_the_limit(self):
        self.with_qa()
        row = "a0a00000-0000-4000-8000-0000000000c1"
        self.send.queue("POST", "/pages", page(row, BOT))
        self.send.queue("PATCH", f"/pages/{row}/markdown", {"object": "page_markdown", "id": row})
        long = " ".join(["The answer goes on."] * 150)  # one line of about 3,000 characters
        self.assertEqual(self.desk.push_qa("Q-1", self.entry("Q-1", f"- **Answer:** {long}"), {}), "created")
        sent = self.bodies("PATCH", f"/pages/{row}/markdown")[0]["replace_content"]["new_str"]
        Texts.assert_within_limit(self, sent)
        self.assertEqual(sent.split(), f"Q-1 · current · delivery · asked 2026-01-17 09:4x - **Answer:** {long}".split())

    def test_someone_else_s_edit_of_a_question_s_row_is_saved_and_waits_one_read(self):
        self.with_qa()
        ids = notion.load_ids(self.root)
        ids["rows"]["a0a00000-0000-4000-8000-0000000000c1"] = "Q-1"
        notion.save_ids(self.root, ids)
        self.with_qa()
        row = "a0a00000-0000-4000-8000-0000000000c1"
        edited = page(row, BOARD, edited="2026-01-17T09:05:00.000Z", words="a note in the row")
        self.send.queue("GET", f"/pages/{row}", edited, edited)
        self.send.queue("GET", f"/blocks/{row}/children", listing([]))
        self.send.queue("PATCH", f"/pages/{row}", page(row, BOT))
        self.send.queue("PATCH", f"/pages/{row}/markdown", {"object": "page_markdown", "id": row})
        state = {}
        self.assertEqual(self.desk.push_qa("Q-1", self.entry("Q-1", "- **Answer:** x"), state),
                         "waits one read: edited in Notion")
        self.assertEqual(self.logs[0][0], "a Q&A row edit not the connection's, saved before it is replaced")
        self.assertEqual(self.logs[0][1]["properties"]["Your words"], "a note in the row")
        self.assertEqual(self.bodies("PATCH", f"/pages/{row}"), [])
        self.assertEqual(self.desk.push_qa("Q-1", self.entry("Q-1", "- **Answer:** x"), state), "updated")

    def test_a_question_s_row_in_the_trash_or_deleted_is_made_again(self):
        """Notion refuses an edit to a trashed row and answers 404 for a deleted one; the row is dropped from
        notion.json and made again, so the questions after it still go out."""
        for gone in ((200, None, page("a0a00000-0000-4000-8000-0000000000c1", BOT) | {"in_trash": True}),
                     (404, None, {"object": "error", "status": 404, "code": "object_not_found"})):
            with self.subTest(status=gone[0]):
                self.send, self.logs = FakeSend(), []
                self.desk.notion = notion.Notion(token=lambda: "test-token", send=self.send, sleep=lambda s: None)
                self.with_qa()
                ids = notion.load_ids(self.root)
                ids["rows"] = {"a0a00000-0000-4000-8000-0000000000c1": "Q-1"}
                notion.save_ids(self.root, ids)
                self.with_qa()
                self.send.queue("GET", "/pages/a0a00000-0000-4000-8000-0000000000c1", gone)
                self.send.queue("POST", "/pages", {"object": "page", "id": "a0a00000-0000-4000-8000-0000000000c2"})
                self.send.queue("PATCH", "/pages/a0a00000-0000-4000-8000-0000000000c2/markdown",
                                {"object": "page_markdown", "warnings": ["a block was changed"]})
                self.assertEqual(self.desk.push_qa("Q-1", self.entry("Q-1", "- **Answer:** x"), {}), "created")
                rows = notion.load_ids(self.root)["rows"]
                self.assertEqual((rows.get("a0a00000-0000-4000-8000-0000000000c2"),
                                  "a0a00000-0000-4000-8000-0000000000c1" in rows), ("Q-1", False))
                self.assertEqual([why for why, _ in self.logs],
                                 ["a Q&A row gone from Notion (in the trash or deleted), made again",
                                  "Notion's warnings on a push"])  # the warnings, as push() logs them
                self.assertEqual(self.logs[1][1], {"page": "Q-1", "warnings": ["a block was changed"]})

    def test_the_first_poll_reads_everything(self):
        self.send.queue("POST", f"/data_sources/{ASKS}/query", listing([]))
        self.send.queue("POST", f"/data_sources/{NOTES}/query", listing([]))
        self.assertEqual(self.desk.poll(None), [])
        self.assertNotIn("filter", self.bodies("POST", f"/data_sources/{ASKS}/query")[0])

    def test_push_replaces_the_page_through_the_markdown_route_with_its_time(self):
        self.send.queue("GET", f"/pages/{PAGE}", page(PAGE, BOT))
        self.send.queue("PATCH", f"/pages/{PAGE}/markdown", {"object": "page_markdown", "id": PAGE, "markdown": "x",
                                                             "truncated": False, "unknown_block_ids": []})
        state = {}
        self.assertEqual(self.desk.push("progress", "---\ntitle: x\n---\n# Progress\n", state, self.now), "pushed")
        self.assertEqual(self.bodies("PATCH", f"/pages/{PAGE}/markdown"),
                         [{"type": "replace_content", "markdown_version": "v2",
                           "replace_content": {"new_str": "Updated 21:07 Dhaka, 2026-01-16\n\n# Progress\n"}}])
        self.assertEqual(self.desk.push("progress", "---\ntitle: y\n---\n# Progress\n", state, self.now), "same")
        self.assertEqual(len(self.send.calls), 2)

    def test_a_page_goes_out_whole(self):  # no check holds it back
        self.send.queue("GET", f"/pages/{PAGE}", {"id": PAGE, "last_edited_by": {"id": BOT}})
        self.send.queue("PATCH", f"/pages/{PAGE}/markdown", {"object": "page_markdown"})
        text = "# Zed\n\nZed of Acme Bakery, ops@acme.example, https://acme.test/x and acme.test.\n"
        self.assertEqual(self.desk.push("progress", text, {}, self.now), "pushed")
        self.assertIn(text.strip("\n"), self.bodies("PATCH", f"/pages/{PAGE}/markdown")[0]["replace_content"]["new_str"])
        self.assertEqual(self.logs, [])

    def test_a_page_of_about_60_kb_goes_in_one_push_each_block_within_the_limit(self):
        """A page is sent whole, commands included, in one push with every block at most 2,000 characters."""
        self.assertNotIn("steps", notion.PAGES)
        self.assertNotIn("steps-two", notion.PAGES)
        self.desk.ids["pages"]["steps"] = STEPS
        script = [f"curl -sS https://api.example.test/v1/item/{n:04d} -o out/{n:04d}.json" for n in range(60)]
        step = "\n".join(["### B-2 · the labels", "", " ".join(["Copy each line, as it is."] * 90), "",
                          "```sh", *script, "```", ""])
        markdown = "---\ntitle: Board steps\n---\n# Board steps\n\n" + step * 14
        self.assertGreater(len(markdown.encode()), 60_000)
        self.send.queue("GET", f"/pages/{STEPS}", page(STEPS, BOT))
        self.send.queue("PATCH", f"/pages/{STEPS}/markdown", {"object": "page_markdown", "id": STEPS})
        self.assertEqual(self.desk.push("steps", markdown, {}, self.now), "pushed")
        sent = self.bodies("PATCH", f"/pages/{STEPS}/markdown")
        self.assertEqual(len(sent), 1)
        Texts.assert_within_limit(self, sent[0]["replace_content"]["new_str"])
        self.assertEqual(sent[0]["replace_content"]["new_str"].count("```sh"), 28)

    def test_someone_else_s_edit_is_saved_and_the_push_waits_one_read(self):
        """Nested blocks too: text typed in a toggle is in the log before the page is replaced; a child page's own
        content isn't read."""
        toggle = {"object": "block", "id": "k2", "type": "toggle", "has_children": True,
                  "toggle": {"rich_text": rich_text("More")}}
        inner = {"object": "block", "id": "k3", "type": "paragraph", "has_children": False,
                 "paragraph": {"rich_text": rich_text("the Board's words in the toggle")}}
        child = {"object": "block", "id": "k4", "type": "child_page", "has_children": True,
                 "child_page": {"title": "A page"}}
        blocks = listing([{"object": "block", "id": "k1", "type": "paragraph", "has_children": False,
                           "paragraph": {"rich_text": rich_text("the Board's note")}}, toggle, child])
        self.send.queue("GET", f"/pages/{PAGE}", page(PAGE, BOARD, edited="2026-01-16T15:05:00.000Z"),
                        page(PAGE, BOARD, edited="2026-01-16T15:05:00.000Z"))
        self.send.queue("GET", f"/blocks/{PAGE}/children", blocks)
        self.send.queue("GET", "/blocks/k2/children", listing([inner]))
        self.send.queue("PATCH", f"/pages/{PAGE}/markdown", {"object": "page_markdown", "id": PAGE})
        state = {}
        self.assertEqual(self.desk.push("progress", "# Progress\n", state, self.now), "waits one read: edited in Notion")
        self.assertEqual(self.logs[0][0], "a page edit not the connection's, saved before it is replaced")
        self.assertEqual(self.logs[0][1]["blocks"], [
            {"type": "paragraph", "text": "the Board's note"},
            {"type": "toggle", "text": "More", "children": [{"type": "paragraph",
                                                             "text": "the Board's words in the toggle"}]},
            {"type": "child_page", "text": "A page"}])
        self.assertNotIn(("GET", "/blocks/k4/children"), [(m, p) for m, p, *_ in self.send.calls])
        self.assertEqual(self.bodies("PATCH", f"/pages/{PAGE}/markdown"), [])
        self.assertEqual(self.desk.push("progress", "# Progress\n", state, self.now), "pushed")

    def test_a_mention_s_email_never_reaches_the_log(self):
        """A user mention carries Notion's user object, and with the capability to read user information its
        person.email; the log keeps each block's type and plain text alone."""
        mention = {"type": "mention", "mention": {"type": "user", "user": user(OTHER, name="A partner")},
                   "annotations": {"bold": False}, "plain_text": "@A partner", "href": None}
        blocks = listing([{"object": "block", "id": "k1", "type": "paragraph", "has_children": False,
                           "created_by": {"object": "user", "id": OTHER}, "last_edited_by": user(OTHER),
                           "paragraph": {"rich_text": rich_text("ask ") + [mention]}},
                          {"object": "block", "id": "k2", "type": "table_row", "has_children": False,
                           "table_row": {"cells": [rich_text("a"), [mention]]}}])
        self.send.queue("GET", f"/pages/{PAGE}", page(PAGE, BOARD, edited="2026-01-16T15:05:00.000Z"))
        self.send.queue("GET", f"/blocks/{PAGE}/children", blocks)
        self.assertEqual(self.desk.push("progress", "# Progress\n", {}, self.now), "waits one read: edited in Notion")
        self.assertEqual(self.logs[0][1]["blocks"], [{"type": "paragraph", "text": "ask @A partner"},
                                                     {"type": "table_row", "text": "a@A partner"}])
        logged = json.dumps(self.logs)
        for word in ("example.com", "email", "person", OTHER):
            self.assertNotIn(word, logged)

    def test_a_new_ask_is_made_with_the_agent_s_fields_only(self):
        self.send.queue("POST", "/pages", page("a0a00000-0000-4000-8000-000000000013", BOT))
        fields = {"Question": "Ship it?", "Recommended": "Yes", "Status": "open"}
        self.assertEqual(self.desk.push_ask("A-2", fields, {}, lambda row, values, edited: True), "created")
        body = self.bodies("POST", "/pages")[0]
        self.assertEqual(body["parent"], {"type": "data_source_id", "data_source_id": ASKS})
        self.assertEqual(sorted(body["properties"]), sorted(("Id",) + notion.ASK_FIELDS))
        self.assertEqual(notion.load_ids(self.root)["rows"]["a0a00000-0000-4000-8000-000000000013"], "A-2")

    def test_once_migrated_an_ask_s_text_goes_in_its_row_s_page_and_the_table_keeps_the_short_columns(self):
        """The Question column cut to QUESTION_CUT, the long columns gone, the ask's text whole and formatted in the
        row's page (the markdown route, as push_qa's); then "same"."""
        ids = notion.load_ids(self.root)
        notion.save_ids(self.root, {**ids, "migrated": [notion.MIGRATION]})
        self.desk = notion.Desk(self.root, lambda why, data: self.logs.append((why, data)), self.desk.notion)
        made = "a0a00000-0000-4000-8000-000000000013"
        self.send.queue("POST", "/pages", page(made, BOT))
        self.send.queue("PATCH", f"/pages/{made}/markdown", {"object": "page_markdown", "id": made})
        question = "Should " + "the launch party move " * 10 + "to Friday?"
        text = f"- **Question:** {question}\n- **Recommended (yes takes it):** Yes\n\n- **Why:** the party"
        fields = {"Question": question, "Recommended": "Yes", "Details": "- Why: the party", "Status": "open",
                  "State": "1 open", "Body": text}
        state = {}
        self.assertEqual(self.desk.push_ask("A-2", fields, state, lambda row, values, edited: True), "created")
        properties = self.bodies("POST", "/pages")[0]["properties"]
        self.assertEqual(sorted(properties), sorted(("Id", "Question", "Status", "State", "Priority", "No.")))
        cut = properties["Question"]["rich_text"][0]["text"]["content"]
        self.assertEqual((len(cut), cut[-1]), (notion.QUESTION_CUT, "…"))
        written = self.bodies("PATCH", f"/pages/{made}/markdown")
        self.assertEqual(len(written), 1)
        self.assertEqual(written[0]["type"], "replace_content")
        self.assertIn(question, written[0]["replace_content"]["new_str"])
        self.assertIn("**Recommended (yes takes it):** Yes", written[0]["replace_content"]["new_str"])
        self.assertEqual(self.desk.push_ask("A-2", fields, state, lambda row, values, edited: True), "same")

    def test_an_ask_row_is_read_again_and_left_while_an_answer_is_unread(self):
        self.send.queue("GET", f"/pages/{ROW}", page(ROW, BOARD, answer="Yes", words=""),
                        page(ROW, BOARD, answer="Yes", words=""))
        self.send.queue("PATCH", f"/pages/{ROW}", page(ROW, BOT))
        seen = []

        def settled(row, values, edited):
            seen.append((row, values, edited))
            return len(seen) > 1

        state = {}
        self.assertEqual(self.desk.push_ask("A-1", {"Question": "Ship it?"}, state, settled),
                         "skipped: an answer the reader hasn't read yet")
        self.assertEqual(seen, [(ROW, {"Your answer": "Yes", "Your words": ""}, "2026-01-16T15:04:00.000Z")])
        self.assertEqual(self.bodies("PATCH", f"/pages/{ROW}"), [])
        self.assertEqual(self.desk.push_ask("A-1", {"Question": "Ship it?"}, state, settled), "updated")
        self.assertNotIn("Your answer", self.bodies("PATCH", f"/pages/{ROW}")[0]["properties"])

    def migrated_desk(self, **databases):
        ids = notion.load_ids(self.root)
        notion.save_ids(self.root, {**ids, "migrated": [notion.MIGRATION],
                                    "databases": {**ids["databases"], **databases}})
        self.desk = notion.Desk(self.root, lambda why, data: self.logs.append((why, data)), self.desk.notion)

    def writes(self):
        return [(m, p) for m, p, *_ in self.send.calls if m != "GET"]

    ASK = {"Question": "Ship it?", "Status": "open", "State": "1 open", "Body": "- **Question:** Ship it?"}

    def test_once_migrated_an_ask_row_someone_edited_is_saved_before_its_page_is_replaced(self):
        """An ask's page is replaced whole, so a row the Board (or anyone but the connection) edited since is logged
        with its page's text first and waits one read; then written."""
        self.migrated_desk()
        edited = page(ROW, BOARD, edited="2026-01-16T15:05:00.000Z", answer="", words="")
        self.send.queue("GET", f"/pages/{ROW}", edited, edited)
        self.send.queue("GET", f"/blocks/{ROW}/children", listing([paragraph("k1", "my note under the ask")]))
        self.send.queue("PATCH", f"/pages/{ROW}", page(ROW, BOT))
        self.send.queue("PATCH", f"/pages/{ROW}/markdown", {"object": "page_markdown", "id": ROW})
        state = {}
        self.assertEqual(self.desk.push_ask("A-1", self.ASK, state, lambda *args: True),
                         "waits one read: edited in Notion")
        self.assertEqual(self.logs, [("an ask row edit not the connection's, saved before its page is replaced",
                                      {"page": "A-1", "editor": BOARD, "edited_at": "2026-01-16T15:05:00.000Z",
                                       "blocks": [{"type": "paragraph", "text": "my note under the ask"}]})])
        self.assertEqual(self.writes(), [])
        self.assertEqual(self.desk.push_ask("A-1", self.ASK, state, lambda *args: True), "updated")
        self.assertEqual(self.writes(), [("PATCH", f"/pages/{ROW}"), ("PATCH", f"/pages/{ROW}/markdown")])
        self.assertEqual(state["edited"], {})

    def test_once_migrated_an_ask_row_with_an_unread_answer_gets_no_page_write_until_it_is_read(self):
        """While settled() says no, neither the row nor its page is written; once read, the Board's edit is saved and
        the next push writes both."""
        self.migrated_desk()
        unread = page(ROW, BOARD, answer="Yes", words="")
        self.send.queue("GET", f"/pages/{ROW}", unread, unread, unread)
        self.send.queue("GET", f"/blocks/{ROW}/children", listing([]))
        self.send.queue("PATCH", f"/pages/{ROW}", page(ROW, BOT))
        self.send.queue("PATCH", f"/pages/{ROW}/markdown", {"object": "page_markdown", "id": ROW})
        seen, state = [], {}

        def settled(row, values, edited):
            seen.append(values)
            return len(seen) > 1

        self.assertEqual([self.desk.push_ask("A-1", self.ASK, state, settled) for _ in range(3)],
                         ["skipped: an answer the reader hasn't read yet", "waits one read: edited in Notion",
                          "updated"])
        self.assertEqual(self.writes(), [("PATCH", f"/pages/{ROW}"), ("PATCH", f"/pages/{ROW}/markdown")])
        self.assertNotIn("Your answer", self.bodies("PATCH", f"/pages/{ROW}")[0]["properties"])

    def test_once_migrated_a_question_s_row_has_no_answer_column_its_number_and_is_pushed_once_more(self):
        """A question's own row loses its Answer column (the answer is in its page) and gains its number (Q-7's 7, for
        the newest-first sort); every row is pushed once more after the migration."""
        self.with_qa()
        row = "a0a00000-0000-4000-8000-0000000000c1"
        self.send.queue("POST", "/pages", page(row, BOT))
        self.send.queue("PATCH", f"/pages/{row}/markdown", *[{"object": "page_markdown", "id": row}] * 2)
        state, entry = {}, self.entry("Q-7", "- **Answer:** Yes.")
        self.assertEqual(self.desk.push_qa("Q-7", entry, state), "created")
        self.assertIn("Answer", self.bodies("POST", "/pages")[0]["properties"])
        self.migrated_desk()
        self.send.queue("GET", f"/pages/{row}", page(row, BOT))
        self.send.queue("PATCH", f"/pages/{row}", page(row, BOT))
        self.assertEqual(self.desk.push_qa("Q-7", entry, state), "updated")
        sent = self.bodies("PATCH", f"/pages/{row}")[0]["properties"]
        self.assertEqual(sorted(sent), sorted(("Question",) + notion.QA_COLUMNS + ("No.",)))
        self.assertEqual(sent["No."], {"number": 7})
        self.assertIn("- **Answer:** Yes.", self.bodies("PATCH", f"/pages/{row}/markdown")[-1]["replace_content"]["new_str"])
        self.assertEqual(self.desk.push_qa("Q-7", entry, state), "same")

    def test_once_migrated_an_answer_goes_into_the_board_s_row_s_page_under_its_words(self):
        """The CEO's answer in a row the Board added goes in the row's page as blocks added at its end, never replacing
        the Board's; the next answer removes only the desk's blocks the connection was the last to edit (one the Board
        edited is the Board's: kept, and read as its words, as the Board's own block)."""
        ids = notion.load_ids(self.root)
        ids["rows"][B_ROW] = notion.QA_ROW
        notion.save_ids(self.root, ids)
        self.migrated_desk(qa={"database": "d3", "data_source": QA_SOURCE})
        theirs = paragraph("k1", "Why is the deploy late?") | {"last_edited_by": {"object": "user", "id": BOARD}}
        made = [{"object": "block", "id": f"m{n}", "type": "paragraph", "last_edited_by": {"object": "user", "id": BOT},
                 "paragraph": {"rich_text": rich_text(f"desk line {n}")}} for n in (1, 2, 3, 4)]
        made[1]["last_edited_by"] = {"object": "user", "id": BOARD}  # the Board typed into the desk's second block
        row = board_row(B_ROW)
        del row["properties"]["Answer"]
        self.send.queue("GET", f"/pages/{B_ROW}", row, board_row(B_ROW, editor=BOT) | {"properties": row["properties"]})
        self.send.queue("GET", f"/blocks/{B_ROW}/children", listing([theirs]), listing([theirs, *made[:2]]))
        self.send.queue("PATCH", f"/pages/{B_ROW}", *[board_row(B_ROW, editor=BOT)] * 2)
        self.send.queue("PATCH", f"/blocks/{B_ROW}/children", {"object": "list", "results": made[:2]},
                        {"object": "list", "results": made[2:]})
        self.send.queue("DELETE", "/blocks/m1", {"object": "block", "id": "m1", "in_trash": True})
        seen, state = [], {}

        def push(answer):
            entry = self.entry("Q-3", f"- **Answer:** {answer}") | {"row": B_ROW, "answered": {"Q-3": B_ROW}}
            return self.desk.push_qa("Q-3", entry, state, lambda row, values, edited: seen.append(values) or True)

        self.assertEqual(push("Friday."), "answered")
        self.assertEqual(push("Friday."), "same")
        self.assertEqual(push("Monday."), "answered")
        sent = self.bodies("PATCH", f"/pages/{B_ROW}")
        self.assertEqual(sorted(sent[0]["properties"]), sorted(notion.QA_COLUMNS + ("No.",)))
        self.assertEqual(sent[0]["properties"]["No."], {"number": 3})
        self.assertNotIn("Question", sent[0]["properties"])
        appended = self.bodies("PATCH", f"/blocks/{B_ROW}/children")
        self.assertEqual(appended[0]["children"][1], {"type": "bulleted_list_item", "bulleted_list_item": {"rich_text": [
            {"type": "text", "text": {"content": "Answer:"}, "annotations": {"bold": True}},
            {"type": "text", "text": {"content": " Friday."}}]}})
        self.assertIn(" Monday.", json.dumps(appended[1]))
        self.assertEqual([p for m, p in self.writes() if m == "DELETE"], ["/blocks/m1"])  # never k1, never m2
        self.assertEqual(notion.load_ids(self.root)["blocks"], {B_ROW: ["m3", "m4"]})
        self.assertEqual([values["Page"] for values in seen],
                         ["Why is the deploy late?", "Why is the deploy late?\ndesk line 2"])

    def with_directives(self):
        self.migrated_desk(directives={"database": "d4", "data_source": D_SOURCE})

    ITEM = {"title": "Hire a designer", "Status": "In progress", "updated": "2026-01-19 14:00",
            "words": "Find me a designer.", "lines": ["### 13:00-14:00 Dhaka", "The brief went out."], "row": None}

    def test_a_directive_is_one_row_with_its_status_time_words_and_id_its_reports_in_its_page(self):
        """A directive's row of the desk's own, by own_row(): its title, Status, Last updated, the Board's words and its
        id; its progress entries in its page; then 'same' until one changes."""
        self.with_directives()
        row = "a0a00000-0000-4000-8000-0000000000d2"
        self.send.queue("POST", "/pages", page(row, BOT))
        self.send.queue("PATCH", f"/pages/{row}/markdown", *[{"object": "page_markdown", "id": row}] * 2)
        state = {}
        self.assertEqual(self.desk.push_directive("D-20260119-design", self.ITEM, state), "created")
        made = self.bodies("POST", "/pages")[0]
        self.assertEqual(made["parent"], {"type": "data_source_id", "data_source_id": D_SOURCE})
        self.assertEqual(made["properties"], {
            "Directive": {"title": [{"type": "text", "text": {"content": "Hire a designer"}}]},
            "Status": {"select": {"name": "In progress"}},
            "Last updated": {"rich_text": [{"type": "text", "text": {"content": "2026-01-19 14:00"}}]},
            "Your words (verbatim)": {"rich_text": [{"type": "text", "text": {"content": "Find me a designer."}}]},
            "Id": {"rich_text": [{"type": "text", "text": {"content": "D-20260119-design"}}]}})
        self.assertEqual(self.bodies("PATCH", f"/pages/{row}/markdown")[0]["replace_content"]["new_str"],
                         "### 13:00-14:00 Dhaka\nThe brief went out.\n")
        self.assertEqual(self.desk.push_directive("D-20260119-design", self.ITEM, state), "same")
        self.send.queue("GET", f"/pages/{row}", page(row, BOT))
        self.send.queue("PATCH", f"/pages/{row}", page(row, BOT))
        self.assertEqual(self.desk.push_directive("D-20260119-design", self.ITEM | {"Status": "Done"}, state), "updated")
        self.assertEqual(self.bodies("PATCH", f"/pages/{row}")[0]["properties"]["Status"], {"select": {"name": "Done"}})
        self.assertEqual(notion.load_ids(self.root)["rows"][row], "D-20260119-design")

    def test_a_directive_s_words_with_emoji_go_whole_each_part_within_notion_s_count(self):
        """The Board's words cut at 2,000 characters (board_desk.verbatim()) with 4 emoji in them, 2,004 as Notion
        counts: the row is made with them whole, in two parts, none over 2,000."""
        self.with_directives()
        row = "a0a00000-0000-4000-8000-0000000000d3"
        words = ("ΝΕΟΣ ΦΟΥΡΝΟΣ 🤖 ΠΙΤΑ 📸 " * 2 + "Σχεδιάστε " * 196)[:2000]
        self.assertEqual(units(words), 2004)
        self.send.queue("POST", "/pages", page(row, BOT))
        self.send.queue("PATCH", f"/pages/{row}/markdown", {"object": "page_markdown", "id": row})
        self.assertEqual(self.desk.push_directive("D-20260104-video", self.ITEM | {"words": words}, {}), "created")
        sent = self.bodies("POST", "/pages")[0]["properties"][notion.WORDS]["rich_text"]
        self.assertEqual(([units(part["text"]["content"]) for part in sent], "".join(part["text"]["content"]
                                                                                    for part in sent)), ([2000, 4], words))

    def test_a_directive_the_board_added_and_the_ceo_filed_gets_the_desk_s_columns_never_its_title(self):
        """Once filed, the Board's row gets the id, Status and the rest, and the reports in its page under the Board's
        words (fill_row()): no row made, its title and its blocks never touched."""
        ids = notion.load_ids(self.root)
        ids["rows"][D_ROW] = notion.DIRECTIVE_ROW
        notion.save_ids(self.root, ids)
        self.with_directives()
        self.send.queue("GET", f"/pages/{D_ROW}", directive_row(D_ROW))
        self.send.queue("GET", f"/blocks/{D_ROW}/children", listing([paragraph("k1", "By Friday, please.")]))
        self.send.queue("PATCH", f"/pages/{D_ROW}", directive_row(D_ROW, editor=BOT))
        self.send.queue("PATCH", f"/blocks/{D_ROW}/children", {"object": "list", "results": [{"id": "m1"}, {"id": "m2"}]})
        seen, state = [], {}
        settled = lambda row, values, edited: seen.append(values) or True  # noqa: E731
        self.assertEqual(self.desk.push_directive("D-20260119-design", self.ITEM | {"row": D_ROW}, state, settled),
                         "updated")
        self.assertEqual(seen, [{"Directive": "Make the logo", "Page": "By Friday, please.", "Status": "", "Id": ""}])
        sent = self.bodies("PATCH", f"/pages/{D_ROW}")[0]["properties"]
        self.assertEqual(sorted(sent), sorted(notion.DIRECTIVE_FIELDS))
        self.assertEqual(sent["Id"]["rich_text"][0]["text"]["content"], "D-20260119-design")
        self.assertEqual([m for m, p in self.writes()], ["PATCH", "PATCH"])  # no row made, nothing removed
        self.assertEqual(notion.load_ids(self.root)["blocks"], {D_ROW: ["m1", "m2"]})
        self.assertEqual(state["wrote"][D_ROW]["Status"], "In progress")

    def test_poll_reads_a_directive_row_the_board_added_never_one_the_desk_made(self):
        """A row the Board made in the Directives table is "New directive" in notion.json, its title, page and columns
        its words; a directive row the desk made, or one the connection made whose id a push lost, is never read."""
        ids = notion.load_ids(self.root)
        ids["rows"]["a0a00000-0000-4000-8000-0000000000d2"] = "D-20260116-the-desk"
        notion.save_ids(self.root, ids)
        self.with_directives()
        self.send.queue("POST", f"/data_sources/{ASKS}/query", listing([]))
        self.send.queue("POST", f"/data_sources/{NOTES}/query", listing([]))
        self.send.queue("POST", f"/data_sources/{D_SOURCE}/query", listing([
            directive_row("a0a00000-0000-4000-8000-0000000000d2", creator=BOT), directive_row(D_ROW),
            directive_row("a0a00000-0000-4000-8000-0000000000d3", creator=BOT)]))
        self.send.queue("GET", f"/blocks/{D_ROW}/children", listing([paragraph("k1", "By Friday, please.")]))
        changes = self.desk.poll(None)
        self.assertEqual([(c["medium_id"], c["page"], c["ask"], c["field"], c["value"]) for c in changes],
                         [(D_ROW, "Directives", "New directive", "Directive", "Make the logo"),
                          (D_ROW, "Directives", "New directive", "Page", "By Friday, please."),
                          (D_ROW, "Directives", "New directive", "Status", ""),
                          (D_ROW, "Directives", "New directive", "Id", "")])
        rows = notion.load_ids(self.root)["rows"]
        self.assertEqual((rows[D_ROW], "a0a00000-0000-4000-8000-0000000000d3" in rows), ("New directive", False))
        self.assertEqual([p for _, p, *_ in self.send.calls if p.startswith("/blocks")], [f"/blocks/{D_ROW}/children"])

    def test_a_done_row_goes_to_notion_s_trash_once(self):
        """in_trash, where the Board can restore it; never again (a restored row stays), and a row already deleted
        counts as done."""
        self.send.queue("PATCH", f"/pages/{ROW}", page(ROW, BOT, trash=True))
        self.send.queue("PATCH", "/pages/gone", (404, None, {"object": "error", "status": 404,
                                                             "code": "object_not_found"}))
        self.assertEqual([self.desk.trash(ROW, "A-1"), self.desk.trash(ROW, "A-1"), self.desk.trash("gone", "Q-1")],
                         [True, False, True])
        self.assertEqual(self.bodies("PATCH", f"/pages/{ROW}"), [{"in_trash": True}])
        self.assertEqual(notion.load_ids(self.root)["trashed"], {ROW: "A-1", "gone": "Q-1"})

    def test_a_link_to_a_question_whose_row_is_in_the_trash_stays_text(self):
        ids = notion.load_ids(self.root)
        ids["rows"]["a0a00000-0000-4000-8000-0000000000c1"] = "Q-1"
        ids["trashed"] = {"a0a00000-0000-4000-8000-0000000000c1": "Q-1"}
        notion.save_ids(self.root, ids)
        self.with_qa()
        row = "a0a00000-0000-4000-8000-0000000000c2"
        self.send.queue("POST", "/pages", page(row, BOT))
        self.send.queue("PATCH", f"/pages/{row}/markdown", {"object": "page_markdown", "id": row})
        self.assertEqual(self.desk.push_qa("Q-2", self.entry("Q-2", "- **Answer:** see Q-1."), {}), "created")
        self.assertEqual(self.bodies("POST", "/pages")[0]["properties"]["Answer"]["rich_text"],
                         [{"type": "text", "text": {"content": "see Q-1."}}])

    def test_readback_gives_property_names_and_a_block_count_never_text(self):
        self.send.queue("GET", f"/pages/{ROW}", page(ROW, BOARD, answer="Yes", words="secret words"))
        self.send.queue("GET", f"/blocks/{ROW}/children", listing([paragraph("k1", "secret page"),
                                                                   paragraph("k2", "more")]))
        self.assertEqual(self.desk.readback(ROW), (["Id", "Your answer", "Your words"], 2))

    def test_the_desk_s_text_in_a_board_row_goes_in_calls_of_at_most_100_blocks(self):
        self.send.queue("PATCH", f"/blocks/{ROW}/children", {"object": "list", "results": [{"id": "m1"}]},
                        {"object": "list", "results": [{"id": "m2"}]})
        self.desk.replace_blocks(ROW, [], "\n".join(f"line {n}" for n in range(150)))
        self.assertEqual([len(body["children"]) for body in self.bodies("PATCH", f"/blocks/{ROW}/children")], [100, 50])
        self.assertEqual(notion.load_ids(self.root)["blocks"], {ROW: ["m1", "m2"]})

    def test_not_set_up_is_an_error(self):
        (self.root / notion.IDS).unlink()
        notion.answers_seal.path_of(self.root).unlink()  # no ids sealed either: never set up
        with self.assertRaises(notion.NotionError):
            notion.Desk(self.root, lambda why, data: None, object())

    def test_ids_changed_or_deleted_outside_the_desk_are_read_from_the_seal(self):
        """notion.json not as the desk wrote it, the seal's copy of its ids in its place; the desk's next write keeps
        them, and the alarm stands."""
        path = self.root / notion.IDS
        path.write_text(path.read_text().replace(ROW, "a0a00000-0000-4000-8000-0000000000aa"))
        self.assertEqual(notion.load_ids(self.root)["rows"][ROW], "A-1")
        path.unlink()
        self.assertEqual(notion.Desk(self.root, lambda why, data: None, object()).ids["bot"], BOT)
        self.send.queue("POST", "/pages", {"id": "c1"})
        self.assertEqual(self.desk.push_clear(), "created")
        self.assertEqual(json.loads(path.read_text())["rows"],
                         {ROW: "A-1", "c1": notion.CLEAR_ROW, "a0a00000-0000-4000-8000-0000000000ff": notion.TEST_ROW})
        self.assertEqual(notion.load_ids(self.root)["rows"]["c1"], notion.CLEAR_ROW)
        self.assertEqual(notion.answers_seal.check(self.root), [("notion.json", "changed outside the desk")])

    def test_the_clear_row_is_made_once_in_asks(self):
        """The Board's row to clear the alarms, in Asks, its id in notion.json's rows (the hook's list), made once."""
        self.send.queue("POST", "/pages", {"id": "c1"})
        self.assertEqual([self.desk.push_clear(), self.desk.push_clear()], ["created", "same"])
        body = self.bodies("POST", "/pages")[0]
        self.assertEqual(body["parent"], {"type": "data_source_id", "data_source_id": ASKS})
        self.assertEqual(body["properties"]["Id"], {"title": notion.rich(notion.CLEAR_ROW)})
        self.assertFalse(set(notion.BOARD_FIELDS) & set(body["properties"]))  # the Board's fields, the Board's
        self.assertEqual(notion.load_ids(self.root)["rows"]["c1"], notion.CLEAR_ROW)


if __name__ == "__main__":
    unittest.main()
