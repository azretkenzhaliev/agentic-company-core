"""The Board desk's Notion adapter (docs/board-desk.md). scripts/board_desk.py uses it; nothing else does. Its settings
(the root page's title, the pages, where a KB link goes) are company.json's "integrations"."board_desk".

- Access: Notion's REST API (API, Notion-Version VERSION) with the token of the Board's internal connection, read from
  the login Keychain (service board-desk-notion, account notion) by this script alone, into memory, per run: never
  printed, logged, written to a file or put on a command line. A redirect is refused, never followed: urllib would
  send the token's header to the host it names. The connection reaches the
  "Board desk" page the Board shared and its children, and lists the workspace's people: their email addresses are
  never read into a file, a log or the output.
- Ids: workspaces/board-desk/notion.json (gitignored): the connection's bot, the root page, each desk page, the Asks,
  Notes and Q&A databases with their data sources, and every row seen, with its ask id (a Q&A row's: its Q-id). setup
  also writes the fixed ones (the root, the pages, the databases and their data sources; ids only) to
  scripts/board_desk/desk_ids.json, which the CEO commits, so a checkout without notion.json (a cloud session, a fresh
  clone) has them too.
  guard_marketing_tools.py refuses any Notion write through Claude's connector that names one of them.
- poll(since): the rows of the Asks, Notes and Q&A databases edited on or after since's minute (Notion rounds edit
  times down to the minute), each row once, rows in the trash left out; each Board-only field's value with the row's
  last editor and edit time. A database it hasn't read before is read whole once. An Asks row's ask id is the one the script gave it
  (notion.json), never its title, so a row anyone else made has none and record() never keeps it; a Notes row's is
  "Note". A Q&A row the script didn't make (the Board adds one to write to the CEO) is "Q&A" in notion.json
  from its first read, so the hook's list holds it too; its Board's fields are its title, as "Question", its page's
  text, as "Page", and each other column by its name, whole (the reader sets aside what the push wrote there). A Q&A
  row the script made (a Q-id) is never read: an edit there is never an answer.
  Once setup has retired Notes to the CEO (board_desk.py, `setup`), a read Notion refuses there (400 or 404: in its
  trash) is skipped; restored from the trash, it is read again.
- push(key, markdown): the page whole, nothing held back or replaced (docs/board-desk.md, "What it sends out"). If the
  page's last editor isn't the connection, its blocks, nested ones included, are first saved to the reader's log as each
  one's type and plain text (never Notion's user objects: a mention's may carry an email) and the push waits one read;
  then one replace_content call, "Updated HH:MM" and the zone on top.
- push_ask(ask, fields): the ask whole too, its agent properties only: call() refuses any page write that
  sets a Board-only property. An existing row is read again just before, and skipped while its Board-only values
  hold anything the reader hasn't settled (a refused value only at the edit time it was refused at), so the
  script's write can't become the last editor of an unread answer. Once setup has added them (MIGRATIONS), also State (1
  open, 2 answered, 3 withdrawn), Priority (its template line's 1 today, 2 this week or 3 when convenient) and No.
  (A-1's 1), the columns setup sorts the table's view by (VIEW_SORTS), each ascending: open first, then the most urgent,
  then by number. From then on too, the table keeps only the short columns (ASK_COLUMNS, the Question cut to
  QUESTION_CUT; setup removes ASK_GONE), and the ask's text as asks.md has it, formatted, goes in its row's page by the
  markdown route, as push_qa() writes a row's page; a row last edited by anyone else has its blocks saved to the log
  first and waits one read, as a page does. Two writes follow the one read (properties, then the page), so an answer
  typed between them makes the connection its last editor: the reader calls it untied and asks the Board to re-enter it
  (fail-safe). Unchecked live: removing a column by PATCH /data_sources/{id} with the property set to null.
- push_qa(qid, entry): one row of the Q&A database for each question of
  qa.md and its archives, updated in place, whole too; KB paths link to the file on GitHub's main, other
  links as given, and a Q-id to its row. A question whose Row line names a row the Board added is written into that row,
  its fields only (QA_FIELDS): never the row's title or page, which are the Board's, no row made, nothing moved or
  trashed, and, as push_ask, not while the reader hasn't read the Board's words there. Once setup has migrated the
  table, the Q&A database has no Answer column and a No. column (Q-1's 1, for a view sorted newest first): a question's
  own row has its entry in its page alone, and a row the Board added gets the entry as blocks appended to its page
  (replace_blocks()), under the Board's words, which are never removed; poll() leaves the desk's blocks out of the row's
  "Page" by their ids, while the connection is still their last editor.
- push_directive(did, item): one row of the Directives database for each open
  directive, or one done within KEEP_DAYS: title, Status, Last updated, the Board's verbatim words and the id, its
  progress entries in its page; or, once the CEO filed a row the Board added there (a "New directive" row: the
  Board's, by its creator and its last editor, board_desk.record()), that row, as a Q&A row the Board added.
- trash(row): a done row to Notion's trash, once. readback(row): a row's property names and block
  count, never its text.
- views(notion, database): a database's views and each one's sorts, for
  `readback`; setup (board_desk.sort_views()) sorts each table's first view by VIEW_SORTS once (PATCH /views/{id}).

Unchecked against a live answer (no call before the Board's setup): the bodies of replace_content and of a database's
creation, and the search filter's value. The setup's first push and the attribution test are their first live use.
Unchecked too: replace_content on a database row, a rich text part's link, a row's link as
ROW_URL plus its id, and the trash call setup makes for a page PAGES no longer has (in_trash). A page goes in one
replace_content:
within_limit() keeps each block at most TEXT_LIMIT characters, but whether the markdown route caps a page's size or
its count of blocks is unchecked; Notion's warnings are logged. Unchecked too: how the markdown route
shows a #### heading of a Q&A row's body, and whether it caps a block's parts at 100 as the API's rich text.
Unchecked too: a row's created_by in a query's answer, the trash call for a database
(PATCH /databases/{id}, in_trash) and what a query of a database in the trash answers.
Unchecked too: the columns setup adds to the Asks database (PATCH /data_sources/{id} with
"properties"); the numbers in State's and Priority's names make a view's sort right either way it sorts a select.
Unchecked too: appending blocks to a row's page (PATCH /blocks/{id}/children, at
most CHILDREN_LIMIT a call, its answer's "results" taken as the new blocks), removing one (DELETE /blocks/{id}), and
a block's last_edited_by.
Unchecked too: the views API: that PATCH /views/{id} takes a "sorts" array and that views are listed by database_id;
each sort as a data source query's ({"property": name, "direction": ...}); whether VERSION has it; which view Notion
lists first.
"""

import hashlib
import json
import posixpath
import re
import subprocess
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import timezone
from pathlib import Path

import answers_seal  # this folder's: the seal on the desk's ids; it puts scripts/ on the path
import company_config

SETTINGS = company_config.integration("board_desk")
SETTINGS = SETTINGS if isinstance(SETTINGS, dict) else None  # None (`false` in the file too): the desk is off
OPTIONS = SETTINGS or {}

API = "https://api.notion.com/v1"
VERSION = "2026-03-11"  # the markdown route takes only this one
KEYCHAIN = ("board-desk-notion", "notion")  # service, account
IDS = Path("workspaces/board-desk/notion.json")
FIXED_IDS = Path("scripts/board_desk/desk_ids.json")  # tracked: the hook's list in every checkout
ROOT_TITLE = OPTIONS.get("root_title", "Board desk")  # the page the Board shared with the connection
BOARD_FIELDS = ("Your answer", "Your words")  # board_desk.BOARD_FIELDS: the Board's alone
ASK_FIELDS = ("Question", "Recommended", "Alternative", "Cost and undo", "Details", "Status")
STATES = ("1 open", "2 answered", "3 withdrawn")  # an ask's State; numbered,
# so a view's sort puts open first whether it sorts a select by its options' order or by name
PRIORITIES = ("1 today", "2 this week", "3 when convenient")  # its Priority, _templates/ask.md's
ASK_SORTS = ("State", "Priority")  # the columns a view sorts the asks by, with NUMBER
NUMBER = "No."  # an ask's number, for that sort: A-1 is 1
ASK_COLUMNS = ("Question", "Status")  # the short text columns the Asks table keeps: an ask's text is easier to read,
# formatted, in its row's page
ASK_GONE = tuple(name for name in ASK_FIELDS if name not in ASK_COLUMNS)  # the columns setup removes
QUESTION_CUT = 120  # characters of the Question column; the page holds it whole
FAULT = None  # why the zone or `pages` can't be used: board_desk.main() raises it for every command but uninstall
try:
    company_config.timezone()
    PAGES = {key: (title, page) for key, (title, page) in OPTIONS.get("pages", {
        "progress": ("Progress", "knowledge/company/board-desk/progress.md"),
        "summaries": ("Daily summaries", "knowledge/company/board-desk/summaries.md"),
        "company": ("How the company works", "knowledge/company/how-it-works.md"),
    }).items()}  # key: (the Notion page's title, the KB page it shows); one added later is made by setup run again, one
    # removed goes to Notion's trash
    for _, shown in PAGES.values():  # a page is pushed whole
        if not posixpath.normpath(shown).startswith("knowledge/"):
            raise ValueError(f"company.json: the board_desk setting `pages` has {shown}, which isn't under knowledge/")
except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
    PAGES, FAULT = {}, error
READ_FROM = ("asks", "notes", "qa", "directives")  # the databases poll() reads: the only rows whose edits can be the
# Board's answers
READ_BEFORE = ("asks", "notes")  # read from the first setup on; the others once setup has made them
QA_FIELDS = ("Id", "Asked", "Answer", "Sources", "Status", "Topic", "Asked before")  # _templates/qa.md's, the title aside
QA_COLUMNS = tuple(name for name in QA_FIELDS if name != "Answer")  # once migrated: the answer
# is in the row's page
QA_ROW = "Q&A"  # the ask id of a row the Board added to the Q&A database
QA_BOARD_FIELDS = ("Question", "Page")  # its Board-only fields: its title, and its page's text
DIRECTIVE_ROW = "New directive"  # the ask id of a row the Board added to the Directives database
STATUSES = ("Not started", "In progress", "Done")  # a directive row's Status
WORDS = "Your words (verbatim)"  # a directive's: its verbatim section, cut; never BOARD_FIELDS' "Your words"
DIRECTIVE_FIELDS = ("Status", "Last updated", WORDS, "Id")  # its desk columns, the title aside; Last updated is text,
# "YYYY-MM-DD HH:MM" in the Board's zone, which a view sorts as time and reads back exactly as written
CHILDREN_LIMIT = 100  # blocks one append call takes (Notion's limit for a request's children)
BOARD_ROWS = {"qa": (QA_ROW, QA_BOARD_FIELDS), "directives": (DIRECTIVE_ROW, ("Directive", "Page"))}  # database: (the
# ask id of a row the Board added there, its Board-only fields: its title, then its page's text)
DATABASES = {  # key: (title, properties); the Board-only ones are named here, never given a value
    "asks": ("Asks", {"Id": {"title": {}}, **{name: {"rich_text": {}} for name in ASK_COLUMNS},
                      "Your answer": {"select": {"options": [{"name": "Yes"}, {"name": "Alternative"},
                                                             {"name": "Other"}]}},
                      "Your words": {"rich_text": {}},
                      "State": {"select": {"options": [{"name": name} for name in STATES]}},
                      "Priority": {"select": {"options": [{"name": name} for name in PRIORITIES]}},
                      NUMBER: {"number": {}}}),
    "notes": ("Notes to the CEO", {"Your words": {"title": {}}}),
    "qa": ("Q&A", {"Question": {"title": {}}, **{name: {"rich_text": {}} for name in QA_COLUMNS},
                   NUMBER: {"number": {}}}),  # Q-1's 1, which a view sorts by, newest first
    "directives": ("Directives", {"Directive": {"title": {}},
                                  "Status": {"select": {"options": [{"name": name} for name in STATUSES]}},
                                  **{name: {"rich_text": {}} for name in DIRECTIVE_FIELDS[1:]}}),
}
MIGRATIONS = {"asks": ("State", "Priority", NUMBER), "qa": (NUMBER,)}  # the columns setup adds, once, to a database
# made before; ids["migrated"] holds MIGRATION once it has, or once setup made the database with them
REMOVALS = {"asks": ASK_GONE, "qa": ("Answer",)}  # the columns that same step removes
MIGRATION = "13"
VIEW_SORTS = {  # the sort setup gives each table's first view, once
    "qa": ((NUMBER, "descending"),),  # the questions newest first
    "asks": tuple((name, "ascending") for name in (*ASK_SORTS, NUMBER)),  # open first, then priority, then id
    "directives": (("Last updated", "descending"),),  # the latest progress first
}
GITHUB = OPTIONS.get("github", "")  # where a KB path in a Q&A row links: https://github.com/<owner>/<repo>/blob/main/;
# empty: the path stays text
GITHUB += "/" if GITHUB and not GITHUB.endswith("/") else ""
ROW_URL = "https://www.notion.so/"  # a row's link: this, then its id without hyphens
TEST_ROW = "Test"  # the attribution test's row, never an answer
CLEAR_ROW = "Answers checked"  # the Asks row whose Yes, the Board's, ends the ANSWERS TAMPERED alarms; no answer
CLEAR_QUESTION = ("To end the ANSWERS TAMPERED alarms in the progress page's hourly entries, once you have looked at "
                  "them: pick Yes in Your answer. Those raised before your edit end; later ones stand. To end later "
                  "ones, type something new in Your words, with Yes still picked. Rows I couldn't tie to your Notion "
                  "edits are set aside, never taken as your answer; if one was yours, enter it again.")
TRIES, WAIT_CAP, TIMEOUT, TEXT_LIMIT = 4, 60, 30, 2000  # TEXT_LIMIT as Notion counts it: fit()
PARTS_LIMIT = 100  # Notion's limit for the parts of one rich text
MESSAGE_CUT, ECHO = 200, 20  # characters of Notion's message a log line names; of a page's text in a row it never does
SENT_TEXT = ("content", "url", "new_str")  # where a request's body holds a page's text (sent_text())
QUOTED = re.compile(r"`[^`]*(?:`|\Z)|\"[^\"]*(?:\"|\Z)")  # a value Notion's message quotes: "instead was `2004`";
# one still open at the message's end (its 1,000-character cut) runs to it
ZWJ = "\u200d"  # a zero-width joiner: fit() never cuts beside one
NUMBER_TEXT = re.compile(r"-?\d+(?:\.\d+)?")
ZONE, ZONE_NAME = answers_seal.ZONE, answers_seal.ZONE_NAME
FRONT_MATTER = re.compile(r"\A---\n.*?\n---\n+", re.S)
COMMENT = re.compile(r"<!--.*?-->\n?", re.S)
KB_LINK = re.compile(r"\[([^\]\n]*)\]\((?![a-z][a-z0-9+.-]*:)[^)\s]*\)", re.I)  # a link into the KB, not the web
LINK = re.compile(r"\[([^\]\n]*)\]\(([^)\s]*)\)")
SCHEME = re.compile(r"[a-z][a-z0-9+.-]*:", re.I)
QA_ID = re.compile(r"\bQ-\d+\b")
FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")  # a fenced code block's first line
BOLD = re.compile(r"\*\*(.+?)\*\*")
BLOCK_KINDS = (("heading_3", re.compile(r"^#{1,6} (.*)$")), ("bulleted_list_item", re.compile(r"^\s*[-*] (.*)$")),
               ("numbered_list_item", re.compile(r"^\s*\d+[.)] (.*)$")))  # blocks_of()'s, else a paragraph


class NotionError(Exception):
    """A request that failed: Notion's status and error code, or the local failure's type; never a body or the token.
    Notion's own message, as message_of() leaves it, is apart, for a log line (named())."""

    def __init__(self, status, code, message=""):
        super().__init__(f"Notion {status}: {code}")
        self.status, self.code, self.message = status, code, message

    def named(self) -> str:
        """The status and code, then Notion's message when it gave one."""
        return f"{self}: {self.message}" if self.message else str(self)


def sent_text(value) -> list:
    """The page text a request's body holds (each rich text's content, a link's url, a markdown's new_str), each on
    one line, as message_of() reads a message."""
    if isinstance(value, dict):
        return [found for key, item in value.items() for found in
                ([" ".join(item.split())] if key in SENT_TEXT and isinstance(item, str) else sent_text(item))]
    return [found for item in value for found in sent_text(item)] if isinstance(value, list) else []


def blank(quoted) -> str:
    """A value Notion's message quotes (QUOTED) as "…", but a closed one that is a number; one still open at the end,
    "…" to the end."""
    text, mark = quoted.group(), quoted.group()[0]
    if len(text) > 1 and text[-1] == mark:
        return text if NUMBER_TEXT.fullmatch(text[1:-1]) else mark + "…" + mark
    return mark + "…"


def message_of(answer, body, key) -> str:
    """Notion's own message for a refused request, as a log line may name it:
    on one line; each value it quotes, but a number, as "…", one the 1,000-character cut leaves open to the end; any
    ECHO or more characters in a row that the request's page text holds (sent_text()) as "…"; never the token, wherever
    white space splits it (a line Notion wrapped); at most MESSAGE_CUT characters."""
    message = str((answer or {}).get("message") or "")
    if key:  # the token out before any cut
        message = re.sub(r"\s*".join(map(re.escape, key)), "…", message)
    message = QUOTED.sub(blank, " ".join(message.split())[:1000])
    sent, out, at = "\n".join(sent_text(body)), "", 0
    while at < len(message):
        end = at + ECHO
        if end > len(message) or message[at:end] not in sent:
            out, at = out + message[at], at + 1
            continue
        while end < len(message) and message[at:end + 1] in sent:
            end += 1
        out, at = out + "…", end
    return out if len(out) <= MESSAGE_CUT else out[:MESSAGE_CUT - 1] + "…"


def keychain_token() -> str:
    try:
        done = subprocess.run(["security", "find-generic-password", "-s", KEYCHAIN[0], "-a", KEYCHAIN[1], "-w"],
                              capture_output=True, text=True, timeout=30)
    except FileNotFoundError:
        raise NotionError(0, "no Keychain here: the desk's jobs are macOS only") from None
    if done.returncode or not done.stdout.strip():
        raise NotionError(0, f"no token in the Keychain (service {KEYCHAIN[0]}, account {KEYCHAIN[1]})")
    return done.stdout.strip()


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """Every redirect refused: urllib's own handler sends the request's headers, the token's included, to the host
    it names."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise NotionError(code, "redirect")


OPENER = urllib.request.build_opener(NoRedirect)  # in place of urllib's redirect handler


def https(method: str, url: str, headers: dict, data):
    """(status, Retry-After, the answer's JSON) of one request; a redirect raises NotionError, unfollowed."""
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with OPENER.open(request, timeout=TIMEOUT) as response:
            return response.status, None, json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as error:
        try:
            answer = json.loads(error.read() or b"{}")
        except ValueError:
            answer = {}
        return error.code, error.headers.get("Retry-After"), answer


class Notion:
    """Notion's REST API with the connection's token; `send` is https in use and a fake in the tests."""

    def __init__(self, token=keychain_token, send=https, sleep=time.sleep):
        self.token, self.send, self.sleep, self._key = token, send, sleep, None

    def call(self, method: str, path: str, body=None, query=None) -> dict:
        if body and path.startswith("/pages") and set(body.get("properties") or {}) & set(BOARD_FIELDS):
            raise NotionError(0, "a Board-only property in a write")  # never sent
        if self._key is None:
            self._key = self.token()
        url = API + path + ("?" + urllib.parse.urlencode(query) if query else "")
        headers = {"Authorization": f"Bearer {self._key}", "Notion-Version": VERSION,
                   "Content-Type": "application/json"}
        data = None if body is None else json.dumps(body).encode()
        for attempt in range(TRIES):
            try:
                status, retry, answer = self.send(method, url, headers, data)
            except (OSError, ValueError) as error:  # no answer, or one that isn't JSON
                raise NotionError(0, type(error).__name__) from None
            if status in (429, 502, 503, 504, 529) and attempt + 1 < TRIES:
                try:
                    pause = float(retry)
                except (TypeError, ValueError):
                    pause = 2.0 ** attempt
                self.sleep(min(max(pause, 0.0), WAIT_CAP))
                continue
            if status >= 400:
                raise NotionError(status, str((answer or {}).get("code") or "error"),
                                  message_of(answer, body, self._key))
            return answer
        raise NotionError(0, "no tries left")  # not reached: the last try returns or raises

    def listed(self, method: str, path: str, body=None) -> list:
        """Every result of a paginated list (GET with body as its query, POST with body as its body)."""
        results, cursor = [], None
        while True:
            more = {"page_size": 100, **({"start_cursor": cursor} if cursor else {})}
            answer = (self.call("GET", path, query={**(body or {}), **more}) if method == "GET"
                      else self.call(method, path, {**(body or {}), **more}))
            results += answer.get("results") or []
            cursor = answer.get("next_cursor")
            if not answer.get("has_more") or not cursor:
                return results

    def people(self) -> list:
        """[(id, name)] of the workspace's people (no bots, no guests: the API lists none), for the Board to pick its
        own id. Each user's email is left where Notion put it, unread."""
        return [(user["id"], str(user.get("name") or "")) for user in self.listed("GET", "/users")
                if user.get("type") == "person" and user.get("id")]


def text_of(prop) -> str:
    """A title, rich text or select property's value as plain text ("" for none or another type)."""
    kind = (prop or {}).get("type")
    value = (prop or {}).get(kind)
    if kind in ("title", "rich_text"):
        return "".join(str(part.get("plain_text") or (part.get("text") or {}).get("content") or "")
                       for part in value or [])
    if kind in ("select", "status"):
        return str((value or {}).get("name") or "")
    return ""


def column_text(prop) -> str:
    """A column of a row the Board added, as text: text_of's types, and a column the Board may add of
    another type the Board fills in (multi-select, number, checkbox, url, email, phone, date). Not people (a user
    object may carry an email) and not what Notion fills in (created or edited by or at, formula, rollup,
    relation, unique id): those change at each edit, and aren't the Board's words."""
    kind = (prop or {}).get("type")
    value = (prop or {}).get(kind)
    if kind == "multi_select":
        return ", ".join(str((option or {}).get("name") or "") for option in value or [])
    if kind in ("number", "url", "email", "phone_number"):
        return "" if value is None else str(value)
    if kind == "checkbox":
        return "yes" if value else ""
    if kind == "date":
        return " to ".join(str(value[end]) for end in ("start", "end") if (value or {}).get(end))
    return text_of(prop)


def fit(text: str) -> int:
    """How many of text's first characters are within TEXT_LIMIT as Notion counts: in UTF-16 units, so a character
    past U+FFFF (most emoji) is 2. A cut there moves back off a combining mark and off each side
    of a zero-width joiner, so a letter and its accent, or an emoji family, stay whole, unless that would
    leave nothing before it. It counts characters, so it never cuts a character past U+FFFF in two. A flag's two
    letters can still be cut apart, and a skin tone from its emoji: each part then shows
    on its own."""
    size = 0
    for at, char in enumerate(text):
        size += 2 if ord(char) > 0xFFFF else 1
        if size > TEXT_LIMIT:
            back = at
            while back and (ZWJ in text[back - 1:back + 1] or unicodedata.category(text[back]).startswith("M")):
                back -= 1
            return back or at
    return len(text)


def chunks(text: str) -> list:
    """text in pieces, each within TEXT_LIMIT as Notion counts (fit()), none cut inside a letter and its marks or an
    emoji family."""
    found = []
    while text:
        found.append(text[:fit(text)])
        text = text[len(found[-1]):]
    return found


def rich(text: str) -> list:
    """Rich text in parts within TEXT_LIMIT (Notion's limit for one, fit())."""
    return [{"type": "text", "text": {"content": piece}} for piece in chunks(text)]


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def notion_text(markdown: str) -> str:
    """A KB page as the medium shows it: no front matter or HTML comments, and links into the KB as their text."""
    return KB_LINK.sub(r"\1", COMMENT.sub("", FRONT_MATTER.sub("", markdown))).strip() + "\n"


def cut(line: str, prose: bool) -> list:
    """A line in pieces within TEXT_LIMIT (fit()): prose at the last space before it, code anywhere."""
    pieces, room = [], fit(line)
    while room < len(line):
        at = line.rfind(" ", 1, room + 1) if prose else -1
        at = at if at > 0 else room
        pieces.append(line[:at])
        line = line[at:].lstrip(" ") if prose else line[at:]
        room = fit(line)
    return pieces + [line]


def within_limit(markdown: str) -> str:
    """The page with no block Notion makes of it over TEXT_LIMIT characters, its limit for one rich text: a fenced code
    block over it becomes several, cut between lines; any other line over it (a paragraph: the KB writes one to a line)
    becomes several paragraphs, cut at spaces; a table's row stays as it is (each cell has the limit). Markdown's own
    length counts, as Notion counts it (fit()), so a block cut is never over it in Notion. A page with no such block
    comes back as it was."""
    out, lines, at = [], markdown.split("\n"), 0
    while at < len(lines):
        fence = FENCE.match(lines[at])
        if not fence:
            pieces = [lines[at]] if lines[at].lstrip().startswith("|") else cut(lines[at], prose=True)
            out += [line for piece in pieces for line in (piece, "")][:-1]
            at += 1
            continue
        mark = fence.group(1)
        end = next((i for i in range(at + 1, len(lines))
                    if lines[i].strip().startswith(mark) and not lines[i].strip().strip(mark[0])), len(lines))
        code, groups = lines[at + 1:end], [[]]
        for piece in [piece for line in code for piece in cut(line, prose=False)]:
            joined = "\n".join(groups[-1] + [piece])
            if groups[-1] and fit(joined) < len(joined):
                groups.append([])
            groups[-1].append(piece)
        if len(groups) == 1:
            out += lines[at:end + 1]
        else:
            out += [line for group in groups for line in (lines[at], *group, mark)]
        at = end + 1
    return "\n".join(out)


def target(link: str, page: str) -> str:
    """Where a link of a KB page goes from a Q&A row: a web link as given; a path, relative to the page (its path in the
    repo), to that file on GitHub (GITHUB); "" for one that leaves the repo, or with no GITHUB (it stays text)."""
    if SCHEME.match(link):
        return link
    path, _, anchor = link.partition("#")
    found = posixpath.normpath(posixpath.join(posixpath.dirname(page), path)) if path else page
    if not GITHUB or found == ".." or found.startswith(("../", "/")):
        return ""
    return GITHUB + found + (f"#{anchor}" if anchor else "")


def linked(text: str, page: str, rows: dict) -> list:
    """[(text, url or None)]: the text's markdown links to target(), and each Q-id outside them to its row when rows
    ({Q-id: row id}) has one."""
    def ids(part: str) -> list:
        found, at = [], 0
        for match in QA_ID.finditer(part):
            if match.group() in rows:
                found += [(part[at:match.start()], None), (match.group(), ROW_URL + rows[match.group()].replace("-", ""))]
                at = match.end()
        return found + [(part[at:], None)]

    parts, at = [], 0
    for match in LINK.finditer(text):
        parts += ids(text[at:match.start()]) + [(match.group(1), target(match.group(2), page) or None)]
        at = match.end()
    return [part for part in parts + ids(text[at:]) if part[0]]


def markdown_of(parts: list) -> str:
    return "".join(f"[{text}]({url})" if url else text for text, url in parts)


def rich_parts(parts: list) -> list:
    """linked()'s parts as rich text, each link kept, each part cut within TEXT_LIMIT (chunks()); over PARTS_LIMIT
    parts (Notion's limit for one rich text), the text whole as plain parts, each link as markdown's [text](url), cut at
    PARTS_LIMIT parts (up to 200,000 UTF-16 units as Notion counts them, fit(); the row's body has it all)."""
    out = [{"type": "text", "text": {"content": piece, **({"link": {"url": url}} if url else {})}}
           for text, url in parts for piece in chunks(text)]
    return out if len(out) <= PARTS_LIMIT else rich(markdown_of(parts))[:PARTS_LIMIT]


def inline(text: str) -> list:
    """A line's rich text for a block: its **bold** kept, each markdown link to a web address as a link (rich_parts());
    a KB path's link was made one by fill_row() already (linked()), and any other stays text."""
    parts = []
    for at, piece in enumerate(BOLD.split(text)):  # split by a group: the odd pieces were in bold
        found, start = [], 0
        for match in LINK.finditer(piece):
            found += [(piece[start:match.start()], None),
                      (match.group(1), match.group(2) if SCHEME.match(match.group(2)) else None)]
            start = match.end()
        for part in rich_parts([part for part in found + [(piece[start:], None)] if part[0]]):
            parts.append({**part, "annotations": {"bold": True}} if at % 2 else part)
    return parts if len(parts) <= PARTS_LIMIT else rich(text)[:PARTS_LIMIT]


def blocks_of(body: str) -> list:
    """Markdown as Notion blocks, for replace_blocks(): a heading as a
    heading_3, a "- " or "1. " line as a list item, a fenced code block as one code block, any other line as a
    paragraph; blank lines left out."""
    out, lines, at = [], body.split("\n"), 0
    while at < len(lines):
        line, at = lines[at], at + 1
        fence = FENCE.match(line)
        if fence:
            mark, code = fence.group(1), []
            while at < len(lines) and not (lines[at].strip().startswith(mark) and not lines[at].strip().strip(mark[0])):
                code.append(lines[at])
                at += 1
            at += 1
            out.append({"type": "code", "code": {"rich_text": rich("\n".join(code))[:PARTS_LIMIT],
                                                 "language": "plain text"}})
            continue
        if not line.strip():
            continue
        kind, found = next(((kind, pattern.match(line)) for kind, pattern in BLOCK_KINDS if pattern.match(line)),
                           ("paragraph", None))
        out.append({"type": kind, kind: {"rich_text": inline(found.group(1) if found else line.strip())}})
    return out


def editor_of(thing: dict) -> str:
    """The id of a page's or block's last editor."""
    return str((thing.get("last_edited_by") or {}).get("id") or "")


def value_text(prop: dict) -> str:
    """What a property the desk writes holds, as the reader reads it back (column_text()): a rich text's or title's
    text, a select's name, a number."""
    kind = next(iter(prop))
    value = prop[kind]
    if kind in ("rich_text", "title"):
        return "".join(part["text"]["content"] for part in value)
    if kind == "select":
        return str((value or {}).get("name") or "")
    return "" if value is None else str(value)


def load_ids(root: Path):
    """notion.json's ids; changed outside the desk, the seal's copy of them in their place (answers_seal.sealed())."""
    sealed = answers_seal.sealed(root, IDS)
    if sealed is not None:
        return json.loads(json.dumps(sealed))
    path = root / IDS
    return json.loads(path.read_text()) if path.exists() else None


def block_texts(blocks: list) -> list:
    """Blocks as the reader's log keeps them: each one's type and plain text, nested ones under "children"; no id and
    no user object (a mention's person may carry an email). A link's target follows its text in brackets, and a
    bookmark's, embed's or link preview's url, or a file's (an uploaded one by its name: Notion's own url for it is
    signed and short-lived), follows its caption."""
    def text_of_part(part: dict) -> str:
        text, href = str(part.get("plain_text") or ""), str(part.get("href") or "")
        return f"{text} ({href})" if href and href != text else text

    kept = []
    for block in blocks:
        kind = str(block.get("type") or "")
        value = block.get(kind) if isinstance(block.get(kind), dict) else {}
        parts = [*(value.get("rich_text") or []), *(value.get("caption") or []),
                 *(part for cell in value.get("cells") or [] for part in cell)]
        text = "".join(text_of_part(part) for part in parts if isinstance(part, dict))
        target = str(value.get("url") or (value.get("external") or {}).get("url") or
                     (value.get("name") or "a file uploaded to Notion" if value.get("type") == "file" else ""))
        text = f"{text} ({target})" if text and target else text or target
        entry = {"type": kind, "text": text or str(value.get("title") or value.get("expression") or "")}
        if block.get("children"):
            entry["children"] = block_texts(block["children"])
        kept.append(entry)
    return kept


def page_text(blocks: list) -> str:
    """A page's text as the reader keeps it (a row the Board added): each
    block's plain text on a line of its own, a nested one two spaces in for each level; nothing cut or held back."""
    def lines(entries: list, depth: int) -> list:
        return [line for entry in entries
                for line in ["  " * depth + entry["text"], *lines(entry.get("children") or [], depth + 1)]]

    return "\n".join(lines(block_texts(blocks), 0))


def normal_text(text: str) -> str:
    """Text as the reader compares it (board_desk.normal): line breaks as \\n, no space at either end."""
    return str(text).replace("\r\n", "\n").replace("\r", "\n").strip()


def desk_wrote(wrote: dict, row: str, field: str, value: str) -> bool:
    """Whether a Board row's column holds what the desk last wrote there (the reader state's "wrote", {row: {column:
    text}}): the CEO's words, never an answer of the Board's."""
    written = (wrote.get(row) or {}).get(field)
    return written is not None and normal_text(value) == normal_text(written)


def migrated(ids) -> bool:
    """Whether setup has added MIGRATIONS' columns: until then Notion would refuse a write naming them."""
    return MIGRATION in ((ids or {}).get("migrated") or [])


def views(notion, database: str) -> list:
    """[(view id, ((property, direction), ...))] of a database's views, in the order Notion lists them; a listed view
    without "sorts" is read whole. Unchecked live: the list's path and query, its order (the first taken as the default
    view), and where a view keeps its sorts."""
    found = []
    for view in notion.listed("GET", "/views", {"database_id": database}):
        whole = view if "sorts" in view else notion.call("GET", f"/views/{view['id']}")
        found.append((str(view["id"]), tuple((str(sort.get("property")), str(sort.get("direction")))
                                             for sort in whole.get("sorts") or [])))
    return found


def sort_words(sorts) -> str:
    return ", ".join(f"{name} {direction}" for name, direction in sorts) or "nothing"


def ready(ids) -> bool:
    """Whether setup finished: an id for the Asks and Notes databases (setup makes them after the pages). A page or
    database added since (the Q&A database) waits for setup to run again (push() and push_qa() say "not set up", poll()
    leaves it); the reads and the other pushes go on meanwhile."""
    return bool(ids) and set(READ_BEFORE) <= set(ids.get("databases") or {})


def save_ids(root: Path, ids: dict) -> None:
    """notion.json, sealed (answers_seal.writing(): a change made outside the
    desk is an alarm, and the reader reads with the ids the seal keeps, load_ids())."""
    path = root / IDS
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(ids, indent=1, sort_keys=True) + "\n"
    with answers_seal.writing(root, IDS, text.encode()):
        temporary = path.with_suffix(".tmp")
        temporary.write_text(text)
        temporary.replace(path)


def save_fixed_ids(root: Path, ids: dict) -> None:
    """FIXED_IDS: notion.json's ids that setup made (root, pages, databases and data sources), ids only: no bot, no
    row, no name."""
    fixed = {"root": ids["root"], "pages": dict(ids["pages"]),
             "databases": {key: {"database": value["database"], "data_source": value["data_source"]}
                           for key, value in ids["databases"].items()}}
    path = root / FIXED_IDS
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(fixed, indent=1, sort_keys=True) + "\n")
    temporary.replace(path)


class Desk:
    """The Board desk in Notion, by notion.json's ids: poll() for board_desk.read_board, push() and push_ask() for
    board_desk.push_desk. `log(why, data)` writes the reader's log."""

    def __init__(self, root: Path, log, notion=None):
        self.root, self.log = root, log
        self.notion = notion or Notion()
        self.ids = load_ids(root)
        if not self.ids:
            raise NotionError(0, "not set up (python3 scripts/board_desk.py setup)")

    def blocks(self, parent: str) -> list:
        """Every block of a page, each nested one under its parent's "children" (a child page's or database's own
        content aside: it isn't this page's text)."""
        found = self.notion.listed("GET", f"/blocks/{parent}/children")
        for block in found:
            if block.get("has_children") and block.get("type") not in ("child_page", "child_database"):
                block["children"] = self.blocks(str(block.get("id")))
        return found

    def poll(self, since) -> list:
        """Called under the reader's lock (board_desk.read_board), which every writer of notion.json holds: the ids
        are read again here, so a row the attribution test added since this Desk was made is known."""
        self.ids = load_ids(self.root) or self.ids
        recent = {}
        if since is not None:
            minute = since.astimezone(timezone.utc).replace(second=0, microsecond=0)
            recent["filter"] = {"timestamp": "last_edited_time",
                                "last_edited_time": {"on_or_after": minute.strftime("%Y-%m-%dT%H:%M:%S.000Z")}}
        polled = self.ids.setdefault("polled", list(READ_BEFORE) if since is not None else [])
        rows, changes, seen, new = self.ids.setdefault("rows", {}), [], set(), False
        for key in [key for key in READ_FROM if key in self.ids["databases"]]:  # the Q&A database once setup made it
            source = self.ids["databases"][key]["data_source"]
            try:
                found = self.notion.listed("POST", f"/data_sources/{source}/query", recent if key in polled else {})
            except NotionError as error:  # Notes to the CEO, retired to Notion's trash: until restored
                if key not in (self.ids.get("retired") or {}) or error.status not in (400, 404):
                    raise
                continue
            if key not in polled:
                polled.append(key)
                new = True
            for row in found:
                identity = str(row.get("id") or "")
                if not identity or identity in seen or row.get("in_trash") or row.get("archived"):
                    continue
                seen.add(identity)
                if key == "notes" and identity not in rows:
                    rows[identity], new = "Note", True  # its id goes on the hook's list too
                if key in BOARD_ROWS and identity not in rows:
                    if str((row.get("created_by") or {}).get("id") or "") == self.ids.get("bot"):
                        continue  # the script's own row, its id lost to a push cut short: never the Board's
                    rows[identity], new = BOARD_ROWS[key][0], True  # a row the Board added; on the hook's list too
                ask = rows.get(identity, "")
                if ask == TEST_ROW or (key in BOARD_ROWS and ask != BOARD_ROWS[key][0]):
                    continue  # the attribution test's row; a question or directive of the CEO's (its id), never an answer
                properties = row.get("properties") or {}
                if key in BOARD_ROWS:
                    values = self.board_words(identity, row, key)
                else:
                    values = {field: text_of(properties[field]) for field in BOARD_FIELDS
                              if properties.get(field) is not None}
                editor = str((row.get("last_edited_by") or {}).get("id") or "")
                creator = str((row.get("created_by") or {}).get("id") or "")  # a directive's must be the Board's too
                for field, value in values.items():
                    changes.append({"medium_id": identity, "page": DATABASES[key][0], "ask": ask, "field": field,
                                    "value": value, "editor": editor, "creator": creator,
                                    "edited_at": row.get("last_edited_time")})
        if new:
            save_ids(self.root, self.ids)
        return changes

    def push_clear(self) -> str:
        """The CLEAR_ROW row in Asks, made once: 'same' or 'created'. Its
        id goes in notion.json's rows, so the hook refuses any caller's Notion write naming it; poll() reads it as
        any ask row, and board_desk.read_board() takes it out of the answers (board_cleared())."""
        rows = self.ids.setdefault("rows", {})
        if CLEAR_ROW in rows.values():
            return "same"
        source = self.ids["databases"]["asks"]["data_source"]
        made = self.notion.call("POST", "/pages", {"parent": {"type": "data_source_id", "data_source_id": source},
                                                  "properties": {"Id": {"title": rich(CLEAR_ROW)},
                                                                 "Question": {"rich_text": rich(CLEAR_QUESTION)}}})
        rows[str(made["id"])] = CLEAR_ROW
        save_ids(self.root, self.ids)
        return "created"

    def in_trash(self, row: str, ask: str, field: str, words: str):
        """One GET, for an answers row whose field the full read lacks (board_desk.audit()): True only if Notion holds
        the page in its trash as that row's own, and not one the desk trashed: in one of the desk's databases; an ask's
        Id its ask id (a note's, a Q&A or a directive row's: "Note", that table's own); field, read as poll() reads it
        (a page's body aside: not read, so never its own), holding words; not in notion.json's "trashed" (the 10:00
        cleanup's, trash()), and its last editor not the connection. False if it's live or not the row's own; None if
        Notion holds no such page."""
        try:
            page = self.notion.call("GET", f"/pages/{row}")
        except NotionError as error:
            if error.status in (400, 404):
                return None
            raise
        if not (page.get("in_trash") or page.get("archived")):
            return False
        if row in (self.ids.get("trashed") or {}) or editor_of(page) == self.ids.get("bot"):
            return False
        parent = page.get("parent") or {}
        parents = {str(parent.get("data_source_id")), str(parent.get("database_id"))} - {"None"}
        key = next((key for key, made in (self.ids.get("databases") or {}).items()
                    if parents & {str(made.get("data_source")), str(made.get("database"))}), None)
        properties = page.get("properties") or {}
        if key in BOARD_ROWS:
            own, values = BOARD_ROWS[key][0], self.board_words(row, page, key, blocks=[])
        elif key in ("asks", "notes"):
            own = text_of(properties.get("Id")) if key == "asks" else "Note"
            values = {name: text_of(properties[name]) for name in BOARD_FIELDS if properties.get(name) is not None}
        else:
            return False

        def plain(text: str) -> str:
            return text.replace("\r\n", "\n").replace("\r", "\n").strip()
        return own == ask and field in values and plain(values[field]) == plain(words)

    def board_words(self, row: str, page: dict, key: str = "qa", blocks=None) -> dict:
        """{field: text} of a row the Board added to the Q&A database, or to
        the Directives one: its title, whatever the column is called now, as "Question" (a
        directive's: "Directive"), its page's text as "Page" (BOARD_ROWS), less the blocks the desk added there and
        was the last to edit (replace_blocks()), and each other column's text by the column's name (the CEO's columns
        too: what the desk wrote there is set aside by the reader, record(), and by fill_row())."""
        fields = BOARD_ROWS[key][1]
        properties = page.get("properties") or {}
        title = next((prop for prop in properties.values() if (prop or {}).get("type") == "title"), None)
        mine = set((self.ids.get("blocks") or {}).get(row) or [])
        theirs = [block for block in (self.blocks(row) if blocks is None else blocks)
                  if not (str(block.get("id")) in mine and editor_of(block) == self.ids.get("bot"))]
        words = dict(zip(fields, (text_of(title), page_text(theirs))))
        for name, prop in properties.items():
            if (prop or {}).get("type") != "title":
                words[f"{name} (column)" if name in fields else name] = column_text(prop)
        return words

    def push(self, key: str, markdown: str, state: dict, now) -> str:
        """'same', 'pushed', 'waits one read: …', or 'not set up' for a page setup hasn't made yet (one added to
        PAGES since it ran). state is the reader's (its "pushed" hashes)."""
        if key not in self.ids.get("pages", {}):
            return "not set up"
        body = notion_text(markdown)
        pushed = state.setdefault("pushed", {})
        if pushed.get(key) == digest(body):
            return "same"
        page = self.ids["pages"][key]
        current = self.notion.call("GET", f"/pages/{page}")
        editor, edited = str((current.get("last_edited_by") or {}).get("id") or ""), current.get("last_edited_time")
        edits = state.setdefault("edited", {})
        if editor != self.ids["bot"] and edits.get(key) != edited:
            blocks = self.blocks(page)
            self.log("a page edit not the connection's, saved before it is replaced",
                     {"page": key, "editor": editor, "edited_at": edited, "blocks": block_texts(blocks)})
            edits[key] = edited
            return "waits one read: edited in Notion"
        stamp = f"Updated {now.astimezone(ZONE):%H:%M} {ZONE_NAME}, {now.astimezone(ZONE):%Y-%m-%d}\n\n"
        answer = self.notion.call("PATCH", f"/pages/{page}/markdown",
                                  {"type": "replace_content", "replace_content": {"new_str": stamp + within_limit(body)},
                                   "markdown_version": "v2"})
        if answer.get("warnings"):
            self.log("Notion's warnings on a push", {"page": key, "warnings": answer["warnings"]})
        pushed[key] = digest(body)
        edits.pop(key, None)
        return "pushed"

    def push_ask(self, ask: str, fields: dict, state: dict, settled) -> str:
        """'same', 'created', 'updated' or 'skipped: …'. settled(row id, {field: value}, the row's last edit time) says
        whether the reader has read every Board-only value there (kept as it is, or refused as it is at that time)."""
        sorts = migrated(self.ids)  # State, Priority and NUMBER, once setup has added them
        columns, body = (ASK_COLUMNS, fields.get("Body", "")) if sorts else (ASK_FIELDS, None)
        text = "\n".join([ask] + [f"{name}: {fields.get(name, '')}" for name in columns
                                  + (ASK_SORTS + (MIGRATION,) if sorts else ())]
                         + ([body] if sorts else []))  # pushed again once they are added
        pushed = state.setdefault("pushed", {})
        if pushed.get(ask) == digest(text):
            return "same"
        short = {name: fields.get(name, "") for name in columns}
        if sorts and len(short["Question"]) > QUESTION_CUT:
            short["Question"] = short["Question"][:QUESTION_CUT - 1].rstrip() + "…"
        properties = {"Id": {"title": rich(ask)}, **{name: {"rich_text": rich(value)} for name, value in short.items()}}
        if sorts:
            number = re.search(r"\d+", ask)
            properties.update({name: {"select": {"name": fields[name]} if fields.get(name) else None}
                               for name in ASK_SORTS})
            properties[NUMBER] = {"number": int(number.group()) if number else None}
        rows = self.ids.setdefault("rows", {})
        row = next((identity for identity, named in rows.items() if named == ask), None)
        if row is None:
            source = self.ids["databases"]["asks"]["data_source"]
            made = self.notion.call("POST", "/pages", {"parent": {"type": "data_source_id", "data_source_id": source},
                                                      "properties": properties})
            rows[str(made["id"])] = ask
            save_ids(self.root, self.ids)
            outcome = "created"
        else:
            fresh = self.notion.call("GET", f"/pages/{row}")  # just before the write: the race
            values = {field: text_of(prop) for field, prop in (fresh.get("properties") or {}).items()
                      if field in BOARD_FIELDS}
            if not settled(row, values, fresh.get("last_edited_time")):
                return "skipped: an answer the reader hasn't read yet"
            editor, edited = str((fresh.get("last_edited_by") or {}).get("id") or ""), fresh.get("last_edited_time")
            edits = state.setdefault("edited", {})
            if body is not None and editor != self.ids["bot"] and edits.get(ask) != edited:  # the
                # page is replaced whole, so words typed there are saved first, as push() and push_qa() save them
                self.log("an ask row edit not the connection's, saved before its page is replaced",
                         {"page": ask, "editor": editor, "edited_at": edited, "blocks": block_texts(self.blocks(row))})
                edits[ask] = edited
                return "waits one read: edited in Notion"
            self.notion.call("PATCH", f"/pages/{row}", {"properties": properties})
            edits.pop(ask, None)
            outcome = "updated"
        if body is not None:  # the ask's own text, formatted, in its row's page, as push_qa() writes a row's
            row = row or next(identity for identity, named in rows.items() if named == ask)
            answer = self.notion.call("PATCH", f"/pages/{row}/markdown", {
                "type": "replace_content", "replace_content": {"new_str": within_limit(notion_text(body))},
                "markdown_version": "v2"})
            if answer.get("warnings"):
                self.log("Notion's warnings on a push", {"page": ask, "warnings": answer["warnings"]})
        pushed[ask] = digest(text)
        return outcome

    def push_qa(self, qid: str, entry: dict, state: dict, settled=None) -> str:
        """'same', 'created', 'updated', 'waits one read: …', or 'not set up' before setup made the Q&A
        database. entry is board_desk.qa_entries()'s: the row's title and properties (QA_FIELDS), its body's lines, and
        the page they're on. One row a Q-id, by own_row(). Another Q-id becomes a link once its row exists (or the row
        the Board added that it answers, entry["answered"]), and the digest holds the links, so a row is pushed again
        then. Once setup has migrated the table, the columns are
        QA_COLUMNS and NUMBER (Q-1's 1): the answer is in the row's page alone, and each row is pushed once more. An
        entry whose Row line names a row the Board added (entry["row"]) goes to answer()."""
        if "qa" not in self.ids.get("databases", {}):
            return "not set up"
        rows = self.ids.setdefault("rows", {})
        made = {named: identity for identity, named in rows.items() if QA_ID.fullmatch(named)
                and identity not in (self.ids.get("trashed") or {})}  # no link into the trash
        others = {key: value for key, value in {**made, **(entry.get("answered") or {})}.items() if key != qid}
        page = entry["page"]
        if entry.get("row"):
            return self.answer(qid, entry, state, settled, others)
        body = "\n".join(markdown_of(linked(line, page, others)) for line in entry["lines"]).strip() + "\n"
        moved = migrated(self.ids)
        fields = {name: str(value).replace("**", "") for name, value in entry["fields"].items()}
        properties = {"Question": {"title": rich(fields.get("Question") or qid)},
                      **{name: {"rich_text": rich_parts(linked(fields.get(name, ""), page, others))}
                         for name in (QA_COLUMNS if moved else QA_FIELDS)}}
        if moved:
            properties[NUMBER] = {"number": int(qid[2:])}
        return self.own_row("qa", qid, properties, body, (MIGRATION + "\n" if moved else "") + body, state)

    def push_directive(self, did: str, item: dict, state: dict, settled=None) -> str:
        """A directive's row of the Directives database. item is
        board_desk.directive_items()'s: its title, Status, Last updated ("updated"), the Board's words (the verbatim
        section, cut) and the lines of its page (its progress entries, newest first). A row the desk made, by
        own_row(), or, once the CEO filed a row the Board added, that row, by fill_row():
        its title and the Board's blocks never touched. 'not set up' before setup made the database."""
        if "directives" not in self.ids.get("databases", {}):
            return "not set up"
        columns = {"Status": {"select": {"name": item["Status"]}}, "Last updated": {"rich_text": rich(item["updated"])},
                   WORDS: {"rich_text": rich(item["words"])[:PARTS_LIMIT]}, "Id": {"rich_text": rich(did)}}
        if item.get("row"):
            return self.fill_row("directives", did, item["row"], columns, item["lines"], "", {}, state, settled)
        body = "\n".join(item["lines"]).strip() + "\n"
        properties = {"Directive": {"title": rich(item["title"] or did)}, **columns}
        return self.own_row("directives", did, properties, body, json.dumps(properties, sort_keys=True) + "\n" + body,
                            state)

    def own_row(self, key: str, what: str, properties: dict, body: str, text: str, state: dict) -> str:
        """A row the desk made and alone writes, in the database key (a question's, push_qa(); a directive's,
        push_directive()): 'same' while text (all the row shows) is as last pushed; else found by notion.json's rows,
        never by its title, and made (again, when gone from Notion) or updated in place, whole: its properties, then
        its page through the markdown route, so the Board's search finds its words. A row someone else edited is saved
        to the log first and waits one read, as a page does; poll() never reads these rows, so an edit there is never
        an answer."""
        pushed, edits = state.setdefault("pushed", {}), state.setdefault("edited", {})
        if pushed.get(what) == digest(text):
            return "same"
        title, rows = DATABASES[key][0], self.ids.setdefault("rows", {})
        row, current = next((identity for identity, named in rows.items() if named == what), None), None
        if row is not None:
            try:
                current = self.notion.call("GET", f"/pages/{row}")
            except NotionError as error:
                if error.status != 404:
                    raise
                current = {"in_trash": True}  # deleted: gone as a trashed one is
            if current.get("in_trash") or current.get("archived"):
                self.log(f"a {title} row gone from Notion (in the trash or deleted), made again",
                         {"page": what, "row": row})
                del rows[row]
                save_ids(self.root, self.ids)
                row = None
        if row is None:
            source = self.ids["databases"][key]["data_source"]
            created = self.notion.call("POST", "/pages", {"parent": {"type": "data_source_id", "data_source_id": source},
                                                         "properties": properties})
            row = str(created["id"])
            rows[row] = what
            save_ids(self.root, self.ids)
            outcome = "created"
        else:
            editor, edited = str((current.get("last_edited_by") or {}).get("id") or ""), current.get("last_edited_time")
            if editor != self.ids["bot"] and edits.get(what) != edited:
                self.log(f"a {title} row edit not the connection's, saved before it is replaced",
                         {"page": what, "editor": editor, "edited_at": edited,
                          "properties": {name: text_of(prop) for name, prop in (current.get("properties") or {}).items()},
                          "blocks": block_texts(self.blocks(row))})
                edits[what] = edited
                return "waits one read: edited in Notion"
            self.notion.call("PATCH", f"/pages/{row}", {"properties": properties})
            outcome = "updated"
        answer = self.notion.call("PATCH", f"/pages/{row}/markdown", {"type": "replace_content",
                                                                      "replace_content": {"new_str": within_limit(body)},
                                                                      "markdown_version": "v2"})
        if answer.get("warnings"):  # as push() logs them
            self.log("Notion's warnings on a push", {"page": what, "warnings": answer["warnings"]})
        pushed[what] = digest(text)
        edits.pop(what, None)
        return outcome

    def answer(self, qid: str, entry: dict, state: dict, settled, others: dict) -> str:
        """push_qa() for a question that answers a row the Board added, by
        fill_row(): its fields (QA_FIELDS; once migrated, QA_COLUMNS and NUMBER, and the entry's lines in the row's
        page)."""
        row, page, moved = entry["row"], entry["page"], migrated(self.ids)
        fields = {name: str(value).replace("**", "") for name, value in entry["fields"].items()}
        properties = {name: {"rich_text": rich_parts(linked(fields.get(name, ""), page, others))}
                      for name in (QA_COLUMNS if moved else QA_FIELDS)}
        if moved:
            properties[NUMBER] = {"number": int(qid[2:])}
        return self.fill_row("qa", qid, row, properties, entry["lines"] if moved else None, page, others, state,
                             settled)

    def fill_row(self, key: str, what: str, row: str, properties: dict, lines, page: str, others: dict, state: dict,
                 settled) -> str:
        """The desk's columns (properties) written into a row the Board added (to Q&A or to Directives), and, given
        lines, the desk's text in its page, added under what the page holds (replace_blocks()): never the row's title or
        a block the Board wrote, no row made, nothing moved. A column holding text the desk didn't write there
        (state["wrote"]) holds the Board's words: the reader keeps them, and the column is left as it is. 'same',
        'answered' (a directive's row: 'updated'), 'kept: …' when the CEO's answer differs in such a Q&A column,
        'skipped: …' while settled() (push_desk's, as push_ask's) says the reader hasn't read the Board's words there
        yet (none given: never written), or 'not pushed: …' for a row gone from Notion, which stays gone."""
        body = None if lines is None else "\n".join(markdown_of(linked(line, page, others)) for line in lines).strip()
        text = digest(row + "\n" + json.dumps(properties, sort_keys=True) + ("" if body is None else
                                                                            f"\n{MIGRATION}\n{body}"))
        pushed = state.setdefault("pushed", {})
        if pushed.get(what) == text:
            return "same"
        try:
            current = self.notion.call("GET", f"/pages/{row}")
        except NotionError as error:
            if error.status != 404:
                raise
            current = {"in_trash": True}
        if current.get("in_trash") or current.get("archived"):
            return "not pushed: the row you added is gone from Notion (in its trash, or deleted)"
        wrote, blocks = state.setdefault("wrote", {}), self.blocks(row)
        words = {name: value for name, value in self.board_words(row, current, key, blocks).items()
                 if not desk_wrote(wrote, row, name, value)}
        if settled is None or not settled(row, words, current.get("last_edited_time")):
            return "skipped: words of yours the reader hasn't read yet"
        held = [name for name in properties if words.get(name, "").strip()]  # the Board's words in a desk column: kept
        sending = {name: prop for name, prop in properties.items() if name not in held}
        if sending:
            self.notion.call("PATCH", f"/pages/{row}", {"properties": sending})
        wrote[row] = {**(wrote.get(row) or {}), **{name: value_text(prop) for name, prop in sending.items()}}
        if body is not None:
            self.replace_blocks(row, blocks, body)
        pushed[what] = text
        if key != "qa":
            return "updated"  # the Board's own Status or words in a directive's column stay, unsaid
        kept = [name for name in held if normal_text(words[name]) != normal_text(value_text(properties[name]))]
        return f"kept: {', '.join(kept)}" if kept else "answered"

    def replace_blocks(self, row: str, blocks: list, body: str) -> None:
        """The desk's text in a row the Board added, whose page may hold the Board's words: the desk's blocks from
        before (notion.json's "blocks") removed, only those the connection was the last to edit (one the Board edited
        since is the Board's now: kept, and read as its words), then the new ones added at the end of the page, their
        ids kept, so board_words() reads the page without them. Unchecked live: appending blocks to a database row's
        page, and removing one."""
        ours = self.ids.setdefault("blocks", {})
        mine = set(ours.get(row) or [])
        for block in blocks:
            if str(block.get("id")) in mine and editor_of(block) == self.ids["bot"]:
                try:
                    self.notion.call("DELETE", f"/blocks/{block['id']}")
                except NotionError as error:
                    if error.status != 404:
                        raise
        made, new = [], blocks_of(body)
        for at in range(0, len(new), CHILDREN_LIMIT):
            answer = self.notion.call("PATCH", f"/blocks/{row}/children", {"children": new[at:at + CHILDREN_LIMIT]})
            made += [str(block["id"]) for block in answer.get("results") or [] if block.get("id")]
            ours[row] = made  # kept at each call: a call cut short leaves no block of the desk's read as the Board's
            save_ids(self.root, self.ids)
        if not new:
            ours[row] = []
            save_ids(self.root, self.ids)

    def trash(self, row: str, what: str) -> bool:
        """A done row to Notion's trash, where it can be restored,
        once (notion.json's "trashed"), so a row the Board restores stays. Whether it moved now."""
        trashed = self.ids.setdefault("trashed", {})
        if row in trashed:
            return False
        try:
            self.notion.call("PATCH", f"/pages/{row}", {"in_trash": True})
        except NotionError as error:
            if error.status != 404:
                raise
        trashed[row] = what
        save_ids(self.root, self.ids)
        return True

    def readback(self, row: str) -> tuple:
        """(property names, count of the page's top-level blocks) of a row: never its text."""
        page = self.notion.call("GET", f"/pages/{row}")
        return sorted(page.get("properties") or {}), len(self.notion.listed("GET", f"/blocks/{row}/children"))
