#!/usr/bin/env python3
"""The Board desk's writer and reader: hourly Progress, the daily summary and the Board's answers (docs/board-desk.md).
A chat moves too fast to read and track; the desk is where the Board reads and answers at its own pace. Off until
company.json has "integrations"."board_desk" (its settings: docs/board-desk.md).

    python3 scripts/board_desk.py run        what launchd starts at every HH:00: `hour`, then `day`
    python3 scripts/board_desk.py hour       the hours since the last run, as one entry in progress.md
    python3 scripts/board_desk.py day        each past day not yet summarised whose summary is due (at 10:00 the
                                             next morning; normally yesterday) into summaries.md, then the roll-up
    python3 scripts/board_desk.py wait       the CEO's watcher: exits with "R-1: the Board answered A-1" once an
                                             answer no status-log row names is there (ceo.md, "Keep a watcher")
    python3 scripts/board_desk.py read       what launchd starts every 2 minutes once Notion is set up: one poll of
                                             the Board's answers, then each ask and page that changed pushed
    python3 scripts/board_desk.py setup      Notion's desk pages under the "Board desk" page the Board shared, their
                                             ids in workspaces/board-desk/notion.json, and the people, for the
                                             Board to pick its own id; run again, only what was added since, and a
                                             page dropped since goes to the trash;
                                             once a CEO row of a status log starts "Q&A rows proven live", Notes
                                             to the CEO goes to the trash too, once; each
                                             table's first view sorted, once
    python3 scripts/board_desk.py readback [<id> ...]
                                             each table's views and their sorts; each id's row (a
                                             Q-id, a D-id or an ask id): its property names and its page's block
                                             count, never its text
    python3 scripts/board_desk.py attribution --board <id>
                                             the attribution test: a test row the Board edits on the phone;
                                             only its edit, shown with that id, records the Board's id
    python3 scripts/board_desk.py install    install and start the launchd jobs for this checkout (the main one only;
                                             the 2-minute reader only once setup has run)
    python3 scripts/board_desk.py uninstall  stop and remove them
    python3 scripts/board_desk.py seal       the Board's, after an ANSWERS TAMPERED line: the answers pages and the
                                             reader's files as they are now become the seal; the
                                             Board's other route, in Notion: Yes on the Asks row
                                             "Answers checked"

- Pages (knowledge/company/board-desk/): progress.md and summaries.md are this job's alone; asks.md and qa.md are the
  CEO's, which it reads, and whose closed asks and old days of questions only the roll-up moves. Times shown are
  in company.json's timezone ("local" below); its state and log stay in UTC.
- The roll-up, at each run after the summaries due: kb_sweep.plan_desk's moves, word for word to each page's
  <page>-archive-YYYY-MM.md: progress.md's summarised days but the latest, summaries.md's older than 5 days, asks.md's
  asks closed more than 3 days ago, qa.md's days asked more than 3 days ago. The
  same moves show in `kb_sweep.py`'s dry run; `--apply --owner ceo` makes them too.
- Lines in each hour's entry outside the 600 bytes and with no model run: "Q&A: new answers to …; answers changed on
  …" for qa.md's questions (and its archives') new or changed since the last entry, and "Stalled orders: …", the first
  order id of each line `capacity_scan.py --stalled` prints, nothing while the
  scan has no such flag.
- The hour and the day read, and change none of: the status-log rows of knowledge/board/directives/D-*.md that weren't
  there at its last run (its own copy is in its state file, so no commit is needed), asks.md, knowledge/board/answers/,
  `git log` subjects new on main, through `gh` each product repo's PRs merged and, where the settings name one, its
  production workflow's runs in the hour, and the session folder's agent records, only to count agents at work. Never
  ceo-questions.md, a transcript's text, research notes, mail or customer data.
- The packet: one line per item, with its source id; UTC clock times in it become local ones, and a markdown link's
  "](" becomes "] (" (its text and target kept). The CEO's To the Board rows are marked "the CEO's words for you",
  and a last part gives the plain name of each id in it (a directive's title, an ask's question, a design's or a
  roadmap's title, a question's words), so the writers write for a bird's-eye reader. Nothing in it is replaced or
  dropped (docs/board-desk.md, "What it sends out"). An empty packet is "Nothing happened." with no model run.
- The writer: one turn of `claude -p` with no tools, no MCP, no settings files (so no hooks, plugins or CLAUDE.md) and
  no saved session, from a fresh temporary folder outside the repo, with board_desk/scribe.md (an hour, Sonnet) or
  board_desk/daily.md (a day, Opus) as its whole system prompt, on the account CLAUDE_CONFIG_DIR names (the
  setting "claude_config_dir" puts it in the job's plist), with ANTHROPIC_API_KEY and ANTHROPIC_AUTH_TOKEN left out of
  its environment, so a hand run never bills a key (SA-002).
- Checks on its text: an hour's at most 600 bytes and 5 lines, a summary's 4,000 bytes and no heading above ###; every
  id, date, clock time and other number in it is in the packet as the same kind (a number's meaning, count or amount,
  isn't checked). One retry. Nothing in it is screened for what it says; a markdown link's "](" becomes "] (", as in the
  packet. A text whose only failure is that last check is never held back: after the last try, or a usage stop on the
  retry, the latest such text goes out with "(unchecked)" after each id, date, time or number the packet doesn't hold,
  the marks outside the 600 or 4,000 bytes. Any other failure, and a usage stop with no such text, get the raw fallback,
  marked "(raw; the writer failed: <reason>)". A span that began the day before gets "Since MM-DD HH:MM: " in front,
  outside the 600 bytes.
- A gh source that fails is named in the hour's entry ("Nothing found; not read: …" when nothing else came in, never
  "Nothing happened.") and read again from the start of the window it missed, each hour until it answers. A read
  that reaches its limit (PR_LIMIT, RUN_LIMIT, COMMIT_LIMIT) is marked "maybe incomplete" in the entry and the
  summary's counts; production runs are filtered by their start in gh, so the limit counts only the window's.
- progress.md is parsed before any model run, and must render back to itself word for word: a line the job didn't
  write, or a hand edit that breaks its shape, stops the hour with one "**Stopped:**" line in the page's head (at
  the top of the body if the Spend heading is gone), where the Board reads it, and nothing else changed. The hours wait
  in the state, and come in as one entry once the page is put back. An edit the shape takes (an entry's words
  changed) renders back to itself and is kept as it is: keeping agents off the page is the guards'.
- Completeness: each Decided and ASK row of the hour must be named in its
  entry, by its ask id (A-1) if the row has one, else its directive's id, in its lines, or in the "Covered:" line
  scribe.md ends with (which never reaches the page) with half its plain name's longer words in the lines (unnamed()).
  Those that aren't go on one more line, outside the 600 bytes: "+N more decided: <plain name> (<id>)" (and "+N more
  asks: …").
- Spend: at 00:00, 06:00, 12:00 and 18:00 (and when progress.md has none) scripts/spend_report.py's block replaces the
  one at the head of progress.md whole, with no model run and nothing in it screened; if
  spend_report.py fails, "Spend: not read at HH:MM (<reason>)" heads the old one. Every summary ends with the block
  as printed at its run, under the same rule.
- Writes are atomic and compare-before-replace (kb_sweep.write), under a lock the hour and the day share; state.json
  is synced to disk, and one that can't be read is kept aside as state-unreadable-<time>.json and the run starts over.
  The log, ~/Library/Logs/agentic-company/board-desk.log, holds counts, tokens and exit codes, Notion's own message for
  a refused request (adapter_notion.message_of()), and for each row the hourly check names, its subject, Notion's edit
  time of its row and one of three editor labels (edit_lines()), never a packet
  or a page: of a page's text at most 19 characters in a row (adapter_notion.ECHO).
- The reader (the medium's adapter calls read_board): a change of a Board-only field's value (Your answer,
  Your words) against its copy, the last R-row for that medium row and field, becomes the next R-row of
  knowledge/board/answers/<YYYY-Www>.md (the local week), word for word, only when the medium names the Board as its
  last editor (the Board's id, picked at install, in workspaces/board-desk/reader.json). Anything else goes once to
  the gitignored workspaces/board-desk/reader-log.jsonl, and the next hour's entry says "A change on A-1 I couldn't
  tie to you: please re-enter it, or answer in the chat.", outside the 600 bytes. Each read reaches back
  READ_OVERLAP before the last one began; a value equal to the copy is no change. It has its own lock and state, so an
  hour's model run never holds an answer back. A row of Notion's "Notes to the CEO" has the ask id "Note"; a row the
  Board added to the Q&A table has "Q&A", and its fields are Question (its title), Page (its page's text) and each
  other column by its name, but for what the push wrote there, whole. A field is
  kept whole at each change, so a page the Board edits over several reads (one each 2 minutes) is a new R-row each
  time, and a week's answers page grows by each copy (kb_lint's 100 KB limit).
- The answers' seal: board_desk/answers_seal.py, its own docstring. A row or answers
  page changed outside the reader, or reader.json, notion.json or reader-log.jsonl changed outside the desk, whatever
  made the change, is an `ANSWERS TAMPERED <R-id or file>: <what>` line at the next read, in capacity_scan's output
  and "Start now", the next hour's entry and wait's output, and its row is never shown as the Board's answer; a read
  stops, nothing read or pushed, while reader.json or notion.json is changed. Once an hour a read reads Notion whole
  and names each row not as Notion holds it, each with one line in the desk's log: Notion's edit time of its row and
  its last editor, the Board, the desk or another editor, never an id (edit_lines()); a Notion read that
  fails is an `ANSWERS NOT CHECKED at <time>` line.
  `seal`, the Board's alone, makes the files as they are the seal again.
- The CEO answers such a row in qa.md, in an entry whose "- **Row:**" line names it by an R-id of it or its Notion
  id; the push writes that entry's fields into the Board's row, its title, page and any column holding the Board's
  words left as the Board wrote them, and makes no row for it. A Row line that names no such row pushes nothing and
  gets one line in the next hour's entry; two entries naming one row, the higher Q-id's is written.
- Notes to the CEO is read as before until a CEO row of a directive's status log starts "Q&A rows proven live" (after
  the first real row of the Board's went through end to end); then `setup`, run again, moves it to Notion's trash,
  once. Undo: restore it from Notion's trash; the next read reads it again.
- The medium: board_desk/adapter_notion.py, its own docstring. Each `read` polls, keeps answers first, then
  pushes each ask of asks.md, each page of adapter_notion.PAGES and each question of qa.md and its archives (a row
  of the Q&A database) whose text changed, whole: no word, name, address or domain is held back or
  replaced. An edit in Notion saved and replaced gets one line in the next hour's entry, outside the
  600 bytes. The Board's id is recorded only by `attribution`, from Notion's own answer for the Board's edit; until
  then no answer counts.
- Missed hours (the Mac asleep or off: launchd coalesces them) become one entry for the whole span; a span that crosses
  midnight sits on its last day, from 00:00, saying when it began.
- The Directives table, once setup has made it: a row for
  each directive open or done within KEEP_DAYS (directive_items()), its progress entries in its page. After each
  hour's entry, one more turn of the hour's model, with board_desk/directives.md, writes 1 to 3 plain lines for each
  directive with new status-log rows in the hour (directive_hour(); its packet is those rows alone), kept KEEP_DAYS
  in the gitignored workspaces/board-desk/directive-progress.json. A row the Board adds there, made and last edited
  by the Board, is recorded as R-rows of ask "New directive", and `wait` says so; one another member made or edited is
  logged by its ids alone, its words in no file. Nothing here acts on a row's text: the CEO files it with /directive
  and writes "R-n New directive" in its status log; the push then fills that row in (its title and the Board's words
  never touched), and until then gives it Status "Not started".
- The cleanup: at the first read at or after 10:00 each day, every row done more than KEEP_DAYS
  ago (a question asked, an ask answered or withdrawn, a directive done) goes to Notion's trash, once, with a count
  per table in the log (clean()); nothing open or not started.
"""

import argparse
import contextlib
import fcntl
import hashlib
import json
import os
import plistlib
import re
import subprocess
import sys
import tempfile
import time
from collections import namedtuple
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import capacity_scan  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent / "board_desk"))

import adapter_notion  # noqa: E402
import answers_seal  # noqa: E402
import company_config  # noqa: E402
from kb_sweep import apply_move, plan_desk, read, sync, touch_updated, write  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
SETTINGS, OPTIONS = adapter_notion.SETTINGS, adapter_notion.OPTIONS  # None and {}: off, no job or Notion command runs
RULES = Path(__file__).resolve().parent / "board_desk"  # the writers' rules
SPEND_REPORT = Path(__file__).resolve().parent / "spend_report.py"
CAPACITY_SCAN = Path(__file__).resolve().parent / "capacity_scan.py"
DESK = Path("knowledge/company/board-desk")
PROGRESS, SUMMARIES, ASKS = DESK / "progress.md", DESK / "summaries.md", DESK / "asks.md"
QA = DESK / "qa.md"  # the CEO's, with its archives qa-archive-YYYY-MM.md
ANSWERS = Path("knowledge/board/answers")
DIRECTIVES = Path("knowledge/board/directives")
STATE = Path("workspaces/board-desk/state.json")  # gitignored, like all of workspaces/
LOCK = Path("workspaces/board-desk/lock")
READER = Path("workspaces/board-desk/reader.json")  # the reader's state: its last read, changes refused, asks untied
READER_LOCK = Path("workspaces/board-desk/reader.lock")
READER_LOG = Path("workspaces/board-desk/reader-log.jsonl")  # the changes it didn't keep, word for word
ANSWERS_HEAD = ("| R-id | Ask | Field | Edited | Recorded | Medium id | The Board's words |\n"
                "|---|---|---|---|---|---|---|")  # knowledge/board/answers/README.md's table
BOARD_FIELDS = ("Your answer", "Your words")  # the medium's Board-only fields
NOTE = "Note"  # the ask id of a row in Notion's "Notes to the CEO"
QA_ROW = adapter_notion.QA_ROW  # the ask id of a row the Board added to the Q&A table
NEW_DIRECTIVE = adapter_notion.DIRECTIVE_ROW  # the ask id of a row the Board added to the Directives table: "New directive"
BOARD_ROW_ASKS = (QA_ROW, NEW_DIRECTIVE)  # rows the Board added: every field of theirs is the Board's but the desk's
QA_LIVE = "Q&A rows proven live"  # how the CEO's status-log row starts that retires Notes to the CEO
ASK_ID_TEXT = r"[AB]-\d+(?: [^·|\n]*[^·|\s])?"  # A-1, or with its part, B-2 B+C;
# never a `|`, which would split the answers table's row (record())
ASKED = re.compile(rf"{ASK_ID_TEXT}|{NOTE}|{QA_ROW}|{NEW_DIRECTIVE}")  # what an answer row's ask may be
R_ID = re.compile(r"\bR-\d+\b")  # an answer's id, as a question's Row line names the row
FILED = re.compile(rf"(?<![\w-])R-(\d+)[\s|:,]*{NEW_DIRECTIVE}\b")  # how a directive's file names the row the Board
# added that it files: `R-1 New directive`, as capacity_scan's NEW_DIRECTIVE_ID
DIRECTIVE_PROGRESS = Path("workspaces/board-desk/directive-progress.json")  # {D-id: {an hour's end, UTC: {"start",
# "lines"}}}: each directive's hourly entries, its Directives row's page, kept KEEP_DAYS
KEEP_DAYS = 7  # a done row, or a progress entry, older than this leaves Notion
DIRECTIVE_LINES, DIRECTIVE_BYTES = 3, 400  # one directive's hourly entry, at most (board_desk/directives.md)
DIRECTIVE_HEAD = re.compile(r"^(D-\d{8}-[a-z0-9-]*[a-z0-9]):$")  # directives.md's line before each directive's entry
DIRECTIVE_STATUS = re.compile(r"^\*\*Directive status:\*\*[ \t]*([A-Za-z-]*)", re.M)  # _templates/directive.md's
ATTRIBUTION_LOG = Path("workspaces/board-desk/attribution.jsonl")  # the attribution test's editors, ids only
ATTRIBUTION_EVERY, ATTRIBUTION_MINUTES = 10, 15  # seconds between its reads, minutes it waits for the Board
LABEL = OPTIONS.get("launchd_label", "com.agentic-company.board-desk")
PLIST = Path.home() / f"Library/LaunchAgents/{LABEL}.plist"
READ_LABEL = f"{LABEL}-read"
READ_PLIST = Path.home() / f"Library/LaunchAgents/{READ_LABEL}.plist"
READ_EVERY = 120  # seconds: the reader's poll
LOG = Path.home() / "Library/Logs/agentic-company/board-desk.log"
PYTHON = "/usr/bin/python3"  # Apple's: keep this file and what it imports Python 3.9
JOB_ENV = {"PATH": f"{Path.home()}/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin",
           **({"CLAUDE_CONFIG_DIR": str(Path(OPTIONS["claude_config_dir"]).expanduser())}
              if OPTIONS.get("claude_config_dir") else {})}  # the account the writers run on; unset: claude's own
ZONE, ZONE_NAME = answers_seal.ZONE, answers_seal.ZONE_NAME  # company.json's timezone, and how the pages name it
SPEND_HOURS = (0, 6, 12, 18)
SUMMARY_HOUR = 10
HOUR_MODEL, DAY_MODEL = "sonnet", "opus"
ENTRY_BYTES, ENTRY_LINES, SPEND_BYTES, SUMMARY_BYTES = 600, 5, 2048, 4000
HOUR_PACKET, DAY_PACKET = 14_000, 40_000  # bytes; the most important lines go in first
ROW_CUT = (600, 300, 200)  # bytes of a status row, by rank: To the Board / Decided / ASK, the rest, NEXT rows
NAME_CUT = 200  # bytes of an id's plain name (plain_names())
# (a product's repo, its production workflow's file or None)
REPOS = tuple((product["repo"], OPTIONS.get("workflows", {}).get(name))
              for name, product in company_config.load()["products"].items() if product.get("repo"))
MAX_DAYS = 3  # summaries one run writes, oldest first; the rest wait for the next hour
LOCK_WAIT = 600  # seconds a run waits for the other to finish
WRITE_TRIES = 3
PR_LIMIT, RUN_LIMIT, COMMIT_LIMIT = 200, 100, 50  # a read at its limit is marked "maybe incomplete"
READ_OVERLAP = timedelta(minutes=1)  # each read reaches back this far before the last one began; repeats are dropped
WAIT_EVERY = 20  # seconds between the watcher's reads
TAMPERED_SHOWN = 5  # ANSWERS TAMPERED lines in an hour's entry, then a count
TRASH_READS = 10  # GETs a check makes for open rows Notion's read lacks (audit()): each holds the
# reader's lock, up to 4 tries and 60 s waits; ten covers the Board deleting a few unanswered rows in an hour, and
# rows added outside the reader past it are named without one
UNTIED_DAYS = 7  # days the reader's state keeps an untied change for the hour's entry

Item = namedtuple("Item", "start end lines agents")  # hours within a local day; lines None means nothing happened

ROW = re.compile(r"^\|\s*(\d{4}-\d{2}-\d{2})\s*\|\s*([^|]*?)\s*\|\s*(.*?)\s*\|\s*$")
STATUS_HEADING = re.compile(r"^#{1,2} Status log\b")
TO_BOARD = re.compile(r"^To the Board\b[^:\n]{0,40}:")  # "To the Board:", or with its time: "To the Board (09:0xZ):"
PRIORITY = re.compile(rf"^(?:{TO_BOARD.pattern[1:]}|Decided:|ASK\b)")
ASK_HEADING = re.compile(rf"^### ({ASK_ID_TEXT}) · ([^·\n]+)(.*)$")
ASK_QUESTION = re.compile(r"^(?:- )?(?:\*\*)?(?:Question|Step):(?:\*\*)?\s*(.*)$")  # a Board step's is its Step
# line
ASK_LINE = re.compile(r"^- \*\*([^*:]+):\*\*\s*(.*)$")  # the ask template's labelled lines
QA_HEADING = re.compile(r"^### (Q-\d+)\b(.*)$")  # _templates/qa.md's: status · topic · asked HH:MM, under its day's
QA_DAY = re.compile(r"^## (\d{4}-\d{2}-\d{2})$")
ENTRY_END = re.compile(r"^#{1,3} ")  # what ends a question's entry; #### and deeper are its own
ORDER_ID = re.compile(r"\bD-\d{8}-[a-z0-9-]*[a-z0-9](?:/\d+)+")  # an order, D-20260101-<slug>/1
CELL = re.compile(r"(?<!\\)\|")
DAY_HEADING = re.compile(r"^## (\d{4}-\d{2}-\d{2}), [A-Z][a-z]+day$")
BLOCK = re.compile(r"^### (\d{2}):00-(\d{2}):00(: Nothing happened\.)?$")
LINE = re.compile(r"^- (\d{2}):00-(\d{2}):00(?: (.*))?$")
SUB = re.compile(r"^  - (.*)$")
EMPTY = re.compile(r"^Nothing happened\.(?: \((\d+) agents? at work\))?$")
SPEND_HEADING = "## Spend"
SPEND_LINE = re.compile(r"Spend as of .+|- .+|Spend: not read at \d{2}:\d{2} \(.+\); below is the last read\.|"
                        r"\(not read yet: the job's first run writes it\)")  # spend_report.py's, spend_lines()', the page's
MD_LINK = re.compile(r"\]\(")
API_KEYS = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")  # never passed to claude -p: it would bill the key (SA-002)
UTC_MARK = r"(?:Z\b| UTC\b)"  # how the logs write UTC: `12:47Z`, `12:47 UTC`
ISO_Z = re.compile(rf"\b(\d{{4}}-\d{{2}}-\d{{2}})[T ](\d{{2}}):(\d{{2}})(?::\d{{2}}(?:\.\d+)?)?{UTC_MARK}")
RANGE_Z = re.compile(rf"\b([01]\d|2[0-3]):([0-5]\d)[-–]([01]\d|2[0-4]):([0-5]\d){UTC_MARK}")  # `13:00-16:00Z`
CLOCK_Z = re.compile(rf"\b([01]\d|2[0-3]):([0-5]\d)(?::[0-5]\d)?{UTC_MARK}")
ASK_ID = re.compile(r"\bA-\d+\b")
ID = re.compile(r"\bD-\d{8}-[a-z0-9-]*[a-z0-9]|\b[A-Z]{1,4}-\d+(?:\.\d+)*\b|#\d+\b")
NUMBER = re.compile(r"\d+(?:,\d{3})*(?:\.\d+)?")
DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
CLOCK = re.compile(r"(?<![\d:])([01]?\d|2[0-4]):([0-5]\d)(?![\d:])")
MONTH_DAY = re.compile(r"(?<![\d-])(\d{2})-(\d{2})(?![\d-])")
STOPPED = "**Stopped:** "  # the head line a refused page gets (hour(), module docstring)
NAMED = re.compile(r"\bD-\d{8}-[a-z0-9-]*[a-z0-9]|\b(?:[AB]|DD|RM|Q)-\d+\b")  # ids with a plain name
CEO_WORDS = "the CEO's words for you"  # how the packet marks the CEO's To the Board rows
COVERED = re.compile(r"^Covered:\s*(.*)$")  # the hour writer's last line: the rows its entry covers (scribe.md)
NAME_WORDS = re.compile(r"[^\W_]{5,}")  # a plain name's words that show the entry speaks of it (unnamed())


def say(text: str) -> None:
    print(f"{datetime.now(timezone.utc):%Y-%m-%dT%H:%MZ} board desk: {text}", flush=True)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def local(moment: datetime) -> datetime:
    return moment.astimezone(ZONE)


def floor_hour(moment: datetime) -> datetime:
    """The local hour's start, in UTC."""
    return local(moment).replace(minute=0, second=0, microsecond=0).astimezone(timezone.utc)


def parse_time(text: str) -> datetime:
    moment = datetime.fromisoformat(str(text).replace("Z", "+00:00"))  # 3.9 reads no Z
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def clip(text: str, limit: int) -> str:
    """At most limit bytes of UTF-8, cut on a character, with an ellipsis when cut."""
    data = text.encode("utf-8")
    return text if len(data) <= limit else data[:limit - 3].decode("utf-8", "ignore") + "…"


def run(argv: list, **kwargs):
    """The finished process, or None if it couldn't start or ran out of time. Its text is never logged."""
    kwargs.setdefault("timeout", 60)
    try:
        return subprocess.run(argv, capture_output=True, text=True, stdin=None if "input" in kwargs else subprocess.DEVNULL,
                              **kwargs)
    except (OSError, subprocess.SubprocessError):
        return None


# ---- the packet's text --------------------------------------------------------------------------------------------

def local_times(text: str) -> str:
    """UTC times the logs write (`2026-01-05T12:47Z`, `12:47:03Z`) as local ones, so the writer copies, never converts;
    one without a date by the zone's offset now."""
    offset = int(local(utc_now()).utcoffset().total_seconds()) // 60

    def iso(found):
        moment = datetime.fromisoformat(f"{found.group(1)}T{found.group(2)}:{found.group(3)}+00:00")
        return f"{local(moment):%Y-%m-%d %H:%M} {ZONE_NAME}"

    def shift(hour: str, minute: str) -> str:
        at = (60 * int(hour) + int(minute) + offset) % (24 * 60)
        return f"{at // 60:02d}:{at % 60:02d}"

    text = ISO_Z.sub(iso, text)
    text = RANGE_Z.sub(lambda found: f"{shift(found.group(1), found.group(2))}-{shift(found.group(3), found.group(4))} "
                                     f"{ZONE_NAME}", text)
    return CLOCK_Z.sub(lambda found: f"{shift(found.group(1), found.group(2))} {ZONE_NAME}", text)


def scrub(text: str) -> str:
    """A packet line as a model sees it: local times, and a markdown link's text and target no longer a link kb_lint
    would check. Nothing replaced or dropped."""
    return local_times(MD_LINK.sub("] (", text))


def facts(text: str) -> tuple:
    """(ids, dates, clock times, month-days, other numbers): each kind taken out before the next is read, so the 12 of
    12:00 or of 2026-01-12 never stands for a count."""
    ids = set(ID.findall(text))
    text = ID.sub(" ", text)
    dates = set(DATE.findall(text))
    text = DATE.sub(" ", text)
    clocks = {f"{int(hour):02d}:{minute}" for hour, minute in CLOCK.findall(text)}
    text = CLOCK.sub(" ", text)
    month_days = {f"{month}-{day_}" for month, day_ in MONTH_DAY.findall(text)}
    text = MONTH_DAY.sub(" ", text)
    return ids, dates, clocks, month_days, {found.replace(",", "").lstrip("0") or "0" for found in NUMBER.findall(text)}


NOT_IN_PACKET = " not in the packet"  # unsourced()'s reasons end so
UNCHECKED = " (unchecked)"  # after each of them in a text that goes out anyway


def unsourced(text: str, packet: str):
    """The first kind of id, date, time or number in the text that the packet doesn't hold, as a reason, or None.
    A number is checked against the packet's numbers of its own kind; its meaning (a count, an amount) isn't."""
    ids, dates, clocks, month_days, numbers = facts(text)
    has = facts(packet)
    month_days_ok = has[3] | {found[5:] for found in has[1]}
    for kind, mine, theirs in (("an id", ids, has[0]), ("a date", dates, has[1]), ("a time", clocks, has[2]),
                               ("a date", month_days, month_days_ok), ("a number", numbers, has[4])):
        if mine - theirs:
            return f"{kind}{NOT_IN_PACKET}"
    return None


def mark_unsourced(text: str, packet: str) -> str:
    """The text with UNCHECKED after each id, date, clock time, month-day and number of it the packet doesn't hold,
    read as unsourced() reads them, each kind taken out before the next."""
    has = facts(packet)
    month_days = has[3] | {found[5:] for found in has[1]}
    kinds = ((ID, lambda found: found.group(0) in has[0]), (DATE, lambda found: found.group(0) in has[1]),
             (CLOCK, lambda found: f"{int(found.group(1)):02d}:{found.group(2)}" in has[2]),
             (MONTH_DAY, lambda found: f"{found.group(1)}-{found.group(2)}" in month_days),
             (NUMBER, lambda found: (found.group(0).replace(",", "").lstrip("0") or "0") in has[4]))
    masked, ends = text, set()
    for pattern, sourced in kinds:
        ends |= {found.end() for found in pattern.finditer(masked) if not sourced(found)}
        masked = pattern.sub(lambda found: " " * len(found.group(0)), masked)
    for end in sorted(ends, reverse=True):
        text = text[:end] + UNCHECKED + text[end:]
    return text


# ---- what it reads --------------------------------------------------------------------------------------------------

def status_rows(root: Path) -> dict:
    """{key: (directive id, date, who, entry)} for each row of each directive's status log, archives left out."""
    rows = {}
    for page in sorted((root / DIRECTIVES).glob("D-*.md")):
        if "-archive" in page.stem:
            continue
        inside = False
        for line in read(page).split("\n"):
            if re.match(r"#{1,6} ", line):
                inside = bool(STATUS_HEADING.match(line))
                continue
            row = ROW.match(line) if inside else None
            if row:
                key = hashlib.sha256(f"{page.stem}\n{line}".encode("utf-8", "surrogateescape")).hexdigest()[:20]
                rows[key] = (page.stem, row.group(1), row.group(2), row.group(3))
    return rows


def proven_live(root: Path) -> bool:
    """Whether a CEO row of a directive's status log starts "Q&A rows proven live" (QA_LIVE), the line after which
    setup retires Notes to the CEO. A row that only quotes it doesn't, and neither does one moved to a directive's
    archive (status_rows() leaves archives out): run setup before the row is archived."""
    return any(who.strip().lower() == "ceo" and entry.lstrip("*_ ").startswith(QA_LIVE)
               for _, _, who, entry in status_rows(root).values())


def asks(root: Path) -> dict:
    """{ask id: (status word, the heading's fields after it, its Question line)} from asks.md."""
    path, found, current = root / ASKS, {}, None
    if not path.exists():
        return {}
    for line in read(path).split("\n"):
        heading = ASK_HEADING.match(line)
        if heading:
            current = heading.group(1)
            found[current] = [(heading.group(2).split() or ["?"])[0].lower(), heading.group(2) + heading.group(3), ""]
        elif line.startswith("#"):
            current = None
        elif current and ASK_QUESTION.match(line):
            found[current][2] = ASK_QUESTION.match(line).group(1)
    return {key: tuple(value) for key, value in found.items()}


def front_title(path: Path) -> str:
    """A KB page's front-matter title, or "" for a page missing or without one."""
    try:
        lines = read(path).split("\n")
    except OSError:
        return ""
    for line in lines[1:] if lines[0].strip() == "---" else []:
        if line.strip() == "---":
            break
        if line.startswith("title:"):
            return line[len("title:"):].strip().strip("\"'")
    return ""


def plain_names(root: Path, text: str) -> dict:
    """{id: its plain name} for each id in text that has one, so the Board never reads a code without its name: a
    directive's title, an ask's or Board step's question, a design's or roadmap's title, a question's words (or its
    topic). An id with none found (an ask archived, a design elsewhere) has none here; the text keeps it as it is."""
    names, asked, questions = {}, None, None
    for found in dict.fromkeys(NAMED.findall(text)):
        if found.startswith("D-"):
            name = front_title(root / DIRECTIVES / f"{found}.md")
        elif found.startswith(("A-", "B-")):
            asked = asked if asked is not None else {key.split()[0]: question for key, (_, _, question)
                                                     in asks(root).items()}
            name = asked.get(found, "")
        elif found.startswith("Q-"):
            questions = questions if questions is not None else {
                qid: entry["fields"].get("Question") or entry["fields"]["Topic"] for qid, entry in qa_entries(root).items()}
            name = questions.get(found, "")
        else:
            folder = root / "knowledge" / "engineering" / ("designs" if found.startswith("DD-") else "roadmaps")
            pages = sorted(folder.glob(f"{found}-*.md"))
            name = re.sub(rf"^{found}:\s*", "", front_title(pages[0])) if pages else ""
        if name.strip():
            names[found] = clip(name.replace("**", "").strip(), NAME_CUT)
    return names


def named(found: str, names: dict) -> str:
    """An id after its plain name, "<name> (<id>)", or the id alone when it has none."""
    return f"{names[found]} ({found})" if names.get(found) else found


def answers(root: Path) -> dict:
    """{R-id: (ask id, recorded)} from knowledge/board/answers/<YYYY-Www>.md's rows (the reader's)."""
    found = {}
    for page in sorted((root / ANSWERS).glob("*-W*.md")):
        for line in read(page).split("\n"):
            cells = [cell.strip() for cell in CELL.split(line)[1:-1]]
            if len(cells) >= 5 and re.fullmatch(r"R-\d+", cells[0]):
                found[cells[0]] = (cells[1], cells[4])
    return found


def gh(root: Path, args: list):
    done = run(["gh", *args], cwd=root, timeout=60)
    try:
        return json.loads(done.stdout) if done and done.returncode == 0 else None
    except ValueError:
        return None


def merged_prs(root: Path, repo: str, start: datetime, end: datetime):
    """([(number, merged at, title)] merged in [start, end), whether gh's answer reached its limit, so more may be
    missing), or None when gh gives no answer it can read."""
    found = gh(root, ["pr", "list", "--repo", repo, "--state", "merged", "--search",
                      f"merged:>={start:%Y-%m-%dT%H:%M:%S}+00:00", "--json", "number,title,mergedAt", "--limit",
                      str(PR_LIMIT)])
    try:
        return sorted((pr["number"], parse_time(pr["mergedAt"]), str(pr["title"])) for pr in found
                      if start <= parse_time(pr["mergedAt"]) < end), len(found) >= PR_LIMIT
    except (TypeError, KeyError, ValueError):
        return None


def deploys(root: Path, repo: str, workflow: str, start: datetime, end: datetime):
    """([(run id, started, conclusion or status, title)] of the workflow's runs started in [start, end), whether gh's
    answer reached its limit), or None. gh filters by the start, so the limit counts only runs from then on."""
    found = gh(root, ["run", "list", "--repo", repo, "--workflow", workflow, "--created",
                      f">={start.astimezone(timezone.utc):%Y-%m-%dT%H:%M:%SZ}", "--json",
                      "databaseId,status,conclusion,createdAt,displayTitle", "--limit", str(RUN_LIMIT)])
    try:
        return sorted((job["databaseId"], parse_time(job["createdAt"]), job.get("conclusion") or job["status"],
                       str(job.get("displayTitle", ""))) for job in found
                      if start <= parse_time(job["createdAt"]) < end), len(found) >= RUN_LIMIT
    except (TypeError, KeyError, ValueError):
        return None


def commits(root: Path, since: "str | None", start: datetime) -> tuple:
    """(main's head, [(short sha, time, subject)] new on main since that head, or since start without one, or None;
    whether git log reached its limit)."""
    head = run(["git", "-C", str(root), "rev-parse", "--verify", "-q", "main"])
    if not head or head.returncode:
        return since, None, False
    head = head.stdout.strip()
    known = since and run(["git", "-C", str(root), "merge-base", "--is-ancestor", since, head])
    span = [f"{since}..{head}"] if known and known.returncode == 0 else [head, f"--since={start.isoformat()}"]
    done = run(["git", "-C", str(root), "log", "-n", str(COMMIT_LIMIT), "--format=%h%x09%cI%x09%s", *span])
    if not done or done.returncode:
        return since, None, False
    found = [line.split("\t", 2) for line in done.stdout.splitlines() if line.count("\t") >= 2]
    return head, [(sha, parse_time(when), subject) for sha, when, subject in found], len(found) >= COMMIT_LIMIT


def agents_at_work(now: float):
    """How many subagents run now, as the capacity scan counts one (its transcript recent and not finished), or None."""
    try:
        count = 0
        for meta in capacity_scan.projects_root().glob("*/subagents/agent-*.meta.json"):
            log = meta.with_name(meta.name[:-len(".meta.json")] + ".jsonl")
            try:
                if now - log.stat().st_mtime > capacity_scan.RUNNING_FOR:
                    continue
                info = json.loads(meta.read_text())
            except (OSError, ValueError):
                continue
            if info.get("finished") and (info.get("stoppedByUser") or not capacity_scan.waiting_on_background(log)):
                continue
            count += 1
        return count
    except Exception:  # noqa: BLE001 - a count only decorates "Nothing happened."
        return None


# ---- the hour's packet ----------------------------------------------------------------------------------------------

def gather(root: Path, state: dict, start: datetime, end: datetime) -> tuple:
    """(packet, [(rank, line, what the entry must name)], the state the run leaves once its entry is written, the gh
    sources it couldn't read); no items for an empty hour. Rank 0 goes in first. A gh source that fails is read again
    from the start of the window it missed, at each run until it answers."""
    items, failed, counts = [], [], {"rows": 0, "decided": 0, "board": 0, "ask rows": 0, "prs": 0, "deploys": 0,
                                     "asks": 0, "ask changes": 0, "answers": 0, "commits": 0}
    rows, seen = status_rows(root), set(state.get("rows", []))
    for key, (directive, day, who, entry) in rows.items():
        if key in seen:
            continue
        rank = 0 if PRIORITY.match(entry) else 2 if entry.startswith("NEXT:") else 1
        counts["rows"] += 1
        counts["decided"] += entry.startswith("Decided:")
        counts["board"] += bool(TO_BOARD.match(entry))
        counts["ask rows"] += entry.startswith("ASK")
        need = ("decided", directive) if entry.startswith("Decided:") else None
        if entry.startswith("ASK"):
            need = ("ask", (ASK_ID.findall(entry) or [directive])[0])
        mark = f", {CEO_WORDS}" if TO_BOARD.match(entry) and who.strip().lower() == "ceo" else ""
        items.append((rank, f"[{directive}, {who}, row dated {day}{mark}] {clip(entry, ROW_CUT[rank])}", need))
    now_asks, old_asks = asks(root), state.get("asks", {})
    for key, (status, fields, question) in now_asks.items():
        if key not in old_asks:
            counts["asks"] += 1
            items.append((0, f"[{key}, asks.md] New ask ({fields.strip()}): {clip(question, 300)}", None))
        elif old_asks[key] != status:
            counts["ask changes"] += 1
            items.append((0, f"[{key}, asks.md] Now {status} (was {old_asks[key]}): {clip(question, 200)}", None))
    now_answers, old_answers = answers(root), set(state.get("answers", []))
    for key, (ask, recorded) in sorted(now_answers.items()):
        if key not in old_answers:
            counts["answers"] += 1
            what = ("note" if ask == NOTE else "row in the Q&A table" if ask == QA_ROW else
                    "new directive, in a row it added to the Directives table" if ask == NEW_DIRECTIVE else
                    f"answer to {ask}")
            items.append((0, f"[{key}, {ask}] The Board's {what} reached the CEO at {recorded} {ZONE_NAME}", None))
    head, found, full = commits(root, state.get("main"), start)
    capped = ["git log of main"] if full else []
    if found is None:
        failed.append("git log")
    for sha, when, subject in found or []:
        counts["commits"] += 1
        items.append((1, f"[commit {sha}, {local(when):%H:%M} {ZONE_NAME}] {clip(subject, 200)}", None))
    unread, failed_gh = dict(state.get("unread", {})), []  # {source: the start of the window it hasn't read}
    for repo, workflow in REPOS:
        key = f"{repo} PRs"
        prs = merged_prs(root, repo, min(start, parse_time(unread.get(key, start.isoformat()))), end)
        prs, full = prs if prs is not None else (None, False)
        capped += [f"gh ({key})"] if full else []
        if prs is None:
            failed_gh.append(key)
            unread[key] = unread.get(key, start.isoformat())
        else:
            unread.pop(key, None)
        for number, when, title in prs or []:
            counts["prs"] += 1
            items.append((1, f"[{repo} PR #{number}, merged {local(when):%H:%M} {ZONE_NAME}] {clip(title, 200)}", None))
        key = f"{repo} production runs"
        since = min(start, parse_time(unread.get(key, start.isoformat())))
        runs = deploys(root, repo, workflow, since, end) if workflow else ([], False)
        runs, full = runs if runs is not None else (None, False)
        capped += [f"gh ({key})"] if full else []
        if runs is None:
            failed_gh.append(key)
            unread[key] = unread.get(key, start.isoformat())
        elif workflow:
            unread.pop(key, None)
        for number, when, outcome, title in runs or []:
            counts["deploys"] += 1
            items.append((0, f"[{repo} production run {number}, started {local(when):%H:%M} {ZONE_NAME}, {outcome}] "
                             f"{clip(title, 150)}", None))
    kept = []
    for rank, line, need in items:
        kept.append((rank, scrub(line), need))
    kept.sort(key=lambda item: item[0])
    head_lines = [f"The hour: {local(start):%Y-%m-%d %H:%M}-{local(end):%H:%M} {ZONE_NAME}.",
                  f"Counts in it: {counts['rows']} new status-log rows ({counts['decided']} Decided, {counts['board']} "
                  f"To the Board, {counts['ask rows']} ASK), {counts['prs']} PRs merged, {counts['deploys']} production "
                  f"deploy runs, {counts['asks']} new asks, {counts['answers']} answers from the Board, "
                  f"{counts['commits']} commits on main."]
    failed += [f"gh ({key})" for key in failed_gh]
    if failed:
        head_lines.append("Not read this hour: " + ", ".join(failed) + ".")
    if capped:
        head_lines.append("At their limit, so maybe incomplete: " + ", ".join(capped) + ".")
    packet, left = fit(head_lines + ["Items, most important first:"], kept, HOUR_PACKET)
    packet += names_section(root, packet)
    fresh = dict(state, rows=sorted(rows), asks={key: value[0] for key, value in now_asks.items()},
                 answers=sorted(set(now_answers) | old_answers), main=head, last_end=end.isoformat(), unread=unread)
    happened = any(n for what, n in counts.items() if what not in ("commits", "decided", "board", "ask rows"))
    return packet, kept if happened else [], fresh, failed_gh, capped  # commits alone: an empty hour


def names_section(root: Path, packet: str) -> str:
    """The packet's last part: the plain name of each id in it,
    one line each, outside its byte limit, so no item goes for it; "" when none has one."""
    names = plain_names(root, packet)
    return ("\n\nPlain names of the ids above (name each thing so; its id only after the name, in brackets, and only "
            "when the Board may need to find it):\n" + "\n".join(scrub(f"- {key}: {name}") for key, name in names.items())
            if names else "")


def fit(head: list, items: list, limit: int) -> tuple:
    """The packet: the head, then items in order while they fit in limit bytes, then how many were left out."""
    lines, size, left = list(head), sum(len(line.encode()) + 1 for line in head), 0
    for _, line, _ in items:
        if not line:
            continue
        size += len(line.encode()) + 3
        if size > limit:
            left += 1
            continue
        lines.append(f"- {line}")
    if left:
        lines.append(f"({left} more items left out for length.)")
    return "\n".join(lines), left


# ---- the writer -----------------------------------------------------------------------------------------------------

def ask_model(prompt: str, rules: Path, model: str, timeout: int) -> tuple:
    """(text, None, usage) or (None, reason, usage) from one no-tools turn of claude -p (module docstring)."""
    argv = ["claude", "-p", "--model", model, "--tools", "", "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}',
            "--setting-sources", "", "--system-prompt-file", str(rules), "--no-session-persistence",
            "--disable-slash-commands", "--max-turns", "1", "--output-format", "json"]
    env = {key: value for key, value in os.environ.items() if key not in API_KEYS}  # SA-002: the subscription only
    env.update(CLAUDE_CODE_DISABLE_CLAUDE_MDS="1", CLAUDE_CODE_DISABLE_AUTO_MEMORY="1")
    with tempfile.TemporaryDirectory(prefix="board-desk-") as folder:
        done = run(argv, input=prompt, cwd=folder, env=env, timeout=timeout)
    if done is None:
        return None, "claude didn't start or ran out of time", {}
    try:
        answer = json.loads(done.stdout)
    except ValueError:
        answer = {}
    if not isinstance(answer, dict):
        return None, "claude's answer wasn't a JSON object", {}
    models, counts = answer.get("modelUsage"), answer.get("usage")
    counts = counts if isinstance(counts, dict) else {}
    usage = {"models": sorted(map(str, models)) if isinstance(models, dict) else [],
             **{key: counts[key] if isinstance(counts.get(key), int) else 0 for key in (
                 "input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens")}}
    text = answer.get("result")
    if done.returncode or answer.get("is_error") or answer.get("subtype") != "success" or not isinstance(text, str):
        said = f"{text or ''} {done.stderr}".lower()
        return None, ("the account's usage limit" if "limit" in said else f"claude exited {done.returncode}"), usage
    return text, None, usage


def log_usage(what: str, usage: dict, outcome: str) -> None:
    if usage:
        say(f"{what}: {'+'.join(usage['models']) or 'no model'}, input {usage['input_tokens']:,}, cache write "
            f"{usage['cache_creation_input_tokens']:,}, cache read {usage['cache_read_input_tokens']:,}, output "
            f"{usage['output_tokens']:,}; {outcome}")


def written(packet: str, rules: Path, model: str, check, what: str, timeout: int) -> tuple:
    """(text, None) once the model's text passes check, or (None, the last reason): one retry, never more. Its markdown
    links' "](" become "] (", text and target kept, so kb_lint never reads one as a link. A text that failed only
    unsourced() (its reason ends NOT_IN_PACKET, as check reads the size first) is never held back: after the last try,
    or a usage stop on the retry, the latest such text goes out, mark_unsourced()'s "(unchecked)" on each such id, date,
    time or number."""
    prompt, reason, unchecked = packet, None, None
    for attempt in (1, 2):
        text, reason, usage = ask_model(prompt, rules, model, timeout)
        if text is not None:
            text = MD_LINK.sub("] (", text.strip())
            reason = check(text)
            unchecked = text if reason and reason.endswith(NOT_IN_PACKET) else unchecked
        log_usage(f"{what}, try {attempt}", usage, reason or "passed")
        if reason is None:
            return text, None
        if text is None and "limit" in reason:
            break  # a usage stop doesn't clear in a minute
        prompt = (f"{packet}\n\nYour last answer failed a check ({reason}). Write it again, following your rules: every "
                  "id and number exactly as the packet has it, no others.")
    if unchecked is not None:
        say(f"{what}: posted with each id or number the packet doesn't hold marked{UNCHECKED}")
        return mark_unsourced(unchecked, packet), None
    return None, reason


def entry_lines(text: str) -> list:
    """The model's text as entry lines: no blank ones, no bullet of its own."""
    return [re.sub(r"^(?:[-*•]\s+|\d+\.\s+)", "", line.strip()) for line in text.split("\n") if line.strip()]


def covered(text: str) -> tuple:
    """(the entry's lines, the text of its "Covered:" lists, or ""): scribe.md's last line names the ids of the Decided
    and ASK rows the entry speaks of, for unnamed(), and never reaches the page. A Covered line anywhere, in bold
    or not, comes off."""
    lines, listed = [], []
    for line in entry_lines(text):
        found = COVERED.match(line.replace("*", "").strip())
        if found:
            listed.append(found.group(1))
        else:
            lines.append(line)
    return lines, ", ".join(listed)


def check_entry(packet: str):
    def check(text: str):
        lines = covered(text)[0]
        if not lines:
            return "no text"
        if len("\n".join(lines).encode("utf-8")) > ENTRY_BYTES:
            return f"over {ENTRY_BYTES} bytes"
        if len(lines) > ENTRY_LINES:
            return f"over {ENTRY_LINES} lines"
        return unsourced(text, packet)
    return check


def raw_entry(items: list, reason: str) -> list:
    """The hour's To the Board, Decided and ASK rows (or its first items), raw, cut to the entry's size, and marked."""
    picked = [line for rank, line, _ in items if rank == 0 and line] or [line for _, line, _ in items if line]
    lines = clip("\n".join(picked), ENTRY_BYTES).split("\n")[:ENTRY_LINES]
    return lines + [f"(raw; the writer failed: {reason})"]


def unnamed(lines: list, items: list, names: "dict | None" = None, listed: str = "") -> list:
    """The completeness line(s) (module docstring): the hour's Decided and ASK rows its entry doesn't name, each by its
    plain name, then its id (names: plain_names()'s). A row is named when its
    lines hold its id, or when its Covered list (listed: covered()'s) holds the id and its lines hold at least half
    of its plain name's words of 5 letters or more: the writer's list alone never drops a row."""
    text, missing = "\n".join(lines), {"decided": [], "ask": []}
    words = set(NAME_WORDS.findall(text.lower()))

    def said(found: str) -> bool:
        pattern = rf"(?<![\w-]){re.escape(found)}(?![\w-])"
        wanted = set(NAME_WORDS.findall((names or {}).get(found, "").lower()))
        return bool(re.search(pattern, text)) or (bool(wanted) and bool(re.search(pattern, listed))
                                                  and 2 * len(wanted & words) >= len(wanted))

    for _, _, need in items:
        if need and not said(need[1]):
            missing[need[0]].append(need[1])
    parts = [f"+{len(ids)} more {'decided' if kind == 'decided' else 'asks'}: "
             f"{', '.join(named(found, names or {}) for found in dict.fromkeys(ids))}"
             for kind, ids in missing.items() if ids]
    return ["; ".join(parts)] if parts else []


# ---- progress.md ----------------------------------------------------------------------------------------------------

def parse_progress(text: str, strict: bool = False) -> tuple:
    """(head lines, Spend lines, {day: [Item]}). Raises ValueError on a line this job didn't write, so nothing is lost;
    strict, also on a page that doesn't render back to itself word for word (a hand edit the grammar would take)."""
    lines = text.split("\n")
    if SPEND_HEADING not in lines:
        raise ValueError(f"no `{SPEND_HEADING}` line")
    at = lines.index(SPEND_HEADING)
    head, spend, days, day, last = lines[:at], [], {}, None, None
    for number, line in enumerate(lines[at + 1:], at + 2):
        heading = DAY_HEADING.match(line)
        if heading:
            day, last = date.fromisoformat(heading.group(1)), None
            days.setdefault(day, [])
            continue
        if day is None:
            if line.strip() and not SPEND_LINE.fullmatch(line):
                raise ValueError(f"line {number} isn't one this job writes")
            spend.append(line)
            continue
        if not line.strip():
            continue
        block, entry, sub = BLOCK.match(line), LINE.match(line), SUB.match(line)
        if block and block.group(3):
            days[day].append(Item(int(block.group(1)), int(block.group(2)), None, None))
        elif block:
            last = None
        elif entry:
            text_ = entry.group(3)
            empty = EMPTY.match(text_ or "")
            if empty:
                last = None
                days[day].append(Item(int(entry.group(1)), int(entry.group(2)), None,
                                      int(empty.group(1)) if empty.group(1) else None))
            else:
                last = Item(int(entry.group(1)), int(entry.group(2)), [text_] if text_ else [], None)
                days[day].append(last)
        elif sub and last is not None:
            last.lines.append(sub.group(1))
        else:
            raise ValueError(f"line {number} isn't one this job writes")
    while spend and not spend[-1].strip():
        spend.pop()
    while spend and not spend[0].strip():
        spend.pop(0)
    while head and not head[-1].strip():
        head.pop()
    if strict:
        again = render_progress(head, spend, days).split("\n")
        differ = next((n for n, (a, b) in enumerate(zip(lines, again), 1) if a != b), min(len(lines), len(again)) + 1)
        if again != lines:
            raise ValueError(f"line {differ} isn't as the job wrote it")
    return head, spend, days


def render_item(item: Item) -> list:
    label = f"- {item.start:02d}:00-{item.end:02d}:00"
    if len(item.lines) == 1:
        return [f"{label} {item.lines[0]}"]
    return [label] + [f"  - {line}" for line in item.lines]


def render_empty(start: int, end: int, agents) -> list:
    at_work = "" if agents is None else f" ({agents} agent{'' if agents == 1 else 's'} at work)"
    return [f"- {start:02d}:00-{end:02d}:00 Nothing happened.{at_work}"]


def render_day(day: date, items: list) -> list:
    """The day's section, newest first: consecutive empty hours share a line, consecutive empty blocks a heading."""
    out, empty, entries = [f"## {day.isoformat()}, {day:%A}"], {}, []
    for item in sorted(items, key=lambda item: item.start):
        if item.lines is None:
            empty.update({hour: item.agents for hour in range(item.start, item.end)})
        else:
            entries.append(item)
    full = [all(hour in empty for hour in range(6 * block, 6 * block + 6))
            and not any((item.end - 1) // 6 == block for item in entries) for block in range(4)]
    block = 3
    while block >= 0:
        if full[block]:
            low = block
            while low > 0 and full[low - 1]:
                low -= 1
            out.append(f"### {6 * low:02d}:00-{6 * block + 6:02d}:00: Nothing happened.")
            block = low - 1
            continue
        lines = [(item.start, render_item(item)) for item in entries if (item.end - 1) // 6 == block]
        hour = 6 * block + 5
        while hour >= 6 * block:
            if hour in empty:
                top = hour
                while hour > 6 * block and hour - 1 in empty:
                    hour -= 1
                lines.append((hour, render_empty(hour, top + 1, empty[top])))
            hour -= 1
        if lines:
            out.append(f"### {6 * block:02d}:00-{6 * block + 6:02d}:00")
            out.extend(line for _, rendered in sorted(lines, key=lambda pair: -pair[0]) for line in rendered)
        block -= 1
    return out


def render_progress(head: list, spend: list, days: dict) -> str:
    out = [*head, "", SPEND_HEADING, "", *spend]
    for day in sorted(days, reverse=True):
        out += ["", *render_day(day, days[day])]
    return "\n".join(out) + "\n"


def place(days: dict, start: datetime, end: datetime, lines, agents) -> None:
    """Puts the span [start, end) on the local day of its last hour. An empty span is split at midnight; an entry
    that began on an earlier day starts at 00:00 and says when it began."""
    first, last = local(start), local(end - timedelta(minutes=1))
    day = last.date()
    if lines is None and first.date() != day:
        place(days, start, datetime.combine(day, datetime.min.time(), ZONE), None, agents)
        first = datetime.combine(day, datetime.min.time(), ZONE)
    if lines is not None and first.date() != day:
        lines = [f"Since {first:%m-%d %H:%M}: {lines[0]}", *lines[1:]]
        first = datetime.combine(day, datetime.min.time(), ZONE)
    days.setdefault(day, []).append(Item(first.hour, last.hour + 1, lines, agents))


def spend_lines(now: datetime, old: list) -> tuple:
    """(the Spend block's lines, None) from scripts/spend_report.py, or (the old lines headed by why not, reason)."""
    done = run([sys.executable, str(SPEND_REPORT)], cwd=REPO, timeout=180)
    lines = done.stdout.rstrip("\n").split("\n") if done and done.returncode == 0 and done.stdout.strip() else None
    reason = None
    if lines is None:
        reason = "spend_report.py didn't finish" if done is None else f"spend_report.py exited {done.returncode}"
        kept = [line for line in old if not line.startswith("Spend: not read at ")]
        lines = [f"Spend: not read at {local(now):%H:%M} ({reason}); below is the last read.", *kept]
    while len("\n".join(lines).encode()) > SPEND_BYTES and len(lines) > 1:  # the failure line counts too
        lines.pop()
    return lines, reason


def spend_due(spend: list, start: datetime, end: datetime) -> bool:
    if not any(line.startswith("Spend as of ") for line in spend):
        return True
    hour = start + timedelta(hours=1)
    while hour <= end:
        if local(hour).hour in SPEND_HOURS:
            return True
        hour += timedelta(hours=1)
    return False


# ---- state, lock, writes --------------------------------------------------------------------------------------------

def load_state(root: Path, rel: Path = STATE):
    """The state, or None for none. One that can't be read is set aside, and the run starts again as a first run.
    reader.json changed outside the desk, with ids the seal keeps of it (answers_seal.sealed()): the seal's Board id
    and last read time in place of its own, the rest as it is, nothing set aside (the alarm stands)."""
    path = root / rel
    sealed = answers_seal.sealed(root, rel) if rel == READER else None
    if sealed is not None:
        try:
            state = json.loads(path.read_text())
        except (OSError, ValueError):
            state = {}
        return {**(state if isinstance(state, dict) else {}), **sealed}
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        return None
    except ValueError:
        kept = path.with_name(f"{path.stem}-unreadable-{int(time.time())}.json")
        os.replace(path, kept)
        say(f"{path.name} couldn't be read (kept as {kept.name}): starting again"
            + ("; the hours since its last run aren't written" if rel == STATE else ""))
        return None


def save_state(root: Path, state: dict, rel: Path = STATE) -> None:
    """Atomic and synced; reader.json sealed (answers_seal.writing())."""
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.stem}-{os.getpid()}")
    text = json.dumps(state, indent=0, sort_keys=True)
    with answers_seal.writing(root, rel, text.encode()):
        with open(temp, "w") as file:
            file.write(text)
            file.flush()
            sync(file)
        os.replace(temp, path)


def baseline(root: Path, end: datetime) -> dict:
    """The state of a first run: every row, ask and answer there now counts as seen; entries start at end."""
    return {"rows": sorted(status_rows(root)), "asks": {key: value[0] for key, value in asks(root).items()},
            "answers": sorted(answers(root)), "main": commits(root, None, end)[0], "last_end": end.isoformat(),
            "summarised": (local(end).date() - timedelta(days=1)).isoformat(), "qa": qa_digests(root)}


@contextlib.contextmanager
def locked(root: Path, rel: Path = LOCK):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as handle:
        waited = 0
        while True:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if waited >= LOCK_WAIT:
                    raise TimeoutError("another run holds the lock")
                time.sleep(1)
                waited += 1
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def rewrite(path: Path, change, now: datetime) -> None:
    """Applies change(text) -> new text and writes it atomically, again on a fresh read if the page changed
    meanwhile."""
    for _ in range(WRITE_TRIES):
        before = read(path)
        after = touch_updated(change(before), local(now).date())  # the run's date, the Board's, not UTC's
        if after == before or write(path, after, before):
            return
    raise RuntimeError(f"{path.name} kept changing while it was written")


# ---- hour -----------------------------------------------------------------------------------------------------------

def refuse(path: Path, now: datetime, reason: str) -> None:
    """Puts one Stopped line in the page's head, where the Board reads it, unless one is there (with no Spend heading,
    at the top of the body); the rest stays as is."""
    say(f"progress.md refused ({reason}): nothing written; the hour waits for the page")
    line = (f"{STOPPED}the hourly job stopped at {local(now):%Y-%m-%d %H:%M} {ZONE_NAME}: {reason}. Entries resume, "
            "with the hours missed, once the CEO has the page put back as the job wrote it.")

    def change(text: str) -> str:
        lines = text.split("\n")
        if any(old.startswith(STOPPED) for old in lines):
            return text
        if SPEND_HEADING not in lines:
            at = lines.index("---", 1) + 1 if lines[0] == "---" and "---" in lines[1:] else 0
            return "\n".join([*lines[:at], "", line, *lines[at:]] if at else [line, "", *lines])
        at = lines.index(SPEND_HEADING)
        head = lines[:at]
        while head and not head[-1].strip():
            head.pop()
        return "\n".join([*head, "", line, "", *lines[at:]])

    rewrite(path, change, now)


def hour(root: Path, now: datetime) -> int:
    end, state = floor_hour(now), load_state(root)
    if not (root / PROGRESS).exists():
        say(f"no {PROGRESS}: nothing written")
        return 1
    if state is None:
        save_state(root, baseline(root, end))
        say(f"started: what's there now counts as seen; entries begin with the hour after {local(end):%H:%M} "
            f"{ZONE_NAME}")
        return 0
    start = parse_time(state["last_end"])
    if end <= start:
        say("up to date: this hour's entry is written")
        return 0
    try:  # before any model run: a page it would refuse costs nothing
        parse_progress(read(root / PROGRESS), strict=True)
    except ValueError as error:
        refuse(root / PROGRESS, now, str(error))
        return 1
    packet, items, fresh, failed_gh, capped = gather(root, state, start, end)
    not_read = f"not read: {', '.join(failed_gh)} (gh); the next hour reads them again." if failed_gh else ""
    limits = [f"Maybe incomplete: {', '.join(capped)} answered at their limit."] if capped else []
    untied, said = untied_lines(root, set(state.get("untied_named", [])))  # outside the writer's 600 bytes
    questions = qa_digests(root)
    # outside them too
    untied = qa_line(state.get("qa"), questions, root) + stalled_line(root) + tampered_lines(root, now) + untied
    if items:
        text, reason = written(packet, RULES / "scribe.md", HOUR_MODEL, check_entry(packet),
                               f"hour {local(start):%H:%M}-{local(end):%H:%M}", 300)
        lines, listed = covered(text) if text is not None else (raw_entry(items, reason), "")
        missing = unnamed(lines, items, plain_names(root, " ".join(need[1] for *_, need in items if need)), listed)
        lines = [line for line in lines if line] + missing + ([not_read[0].upper() + not_read[1:]]
                                                              if not_read else []) + limits + untied
        agents = None
    elif failed_gh or untied:  # never "Nothing happened." on a source it couldn't read
        lines, agents = ([f"Nothing found; {not_read}"] if failed_gh else []) + untied, None
    else:
        lines, agents = None, agents_at_work(now.timestamp())
    spent = {}

    def change(text: str) -> str:
        head, spend, days = parse_progress(text, strict=True)
        head = [line for line in head if not line.startswith(STOPPED)]
        while head and not head[-1].strip():
            head.pop()
        if spend_due(spend, start, end):
            if "lines" not in spent:
                spent["lines"], spent["reason"] = spend_lines(now, spend)
            spend = spent["lines"]
        place(days, start, end, lines, agents)
        return render_progress(head, spend, days)

    rewrite(root / PROGRESS, change, now)
    fresh["untied_named"], fresh["qa"] = said, questions
    save_state(root, fresh)
    say(f"hour {local(start):%H:%M}-{local(end):%H:%M} {ZONE_NAME} written: {len(items)} items"
        + (f"; spend {'read' if not spent.get('reason') else 'not read: ' + spent['reason']}" if spent else ""))
    if "directives" in ((adapter_notion.load_ids(root) or {}).get("databases") or {}):
        rows, seen = status_rows(root), set(state.get("rows", []))
        try:  # after the hour's entry and state are saved: a failure here costs only the directives' entries
            directive_hour(root, [rows[key] for key in fresh["rows"] if key not in seen and key in rows], start, end,
                           now)
        except Exception as error:  # noqa: BLE001 - logged by type only, as main() logs a step's
            say(f"directives {local(start):%H:%M}-{local(end):%H:%M} failed: {type(error).__name__}")
    return 0


# ---- day ------------------------------------------------------------------------------------------------------------

def day_window(day: date) -> tuple:
    start = datetime.combine(day, datetime.min.time(), ZONE).astimezone(timezone.utc)
    end = datetime.combine(day + timedelta(days=1), datetime.min.time(), ZONE).astimezone(timezone.utc)
    return start, end


def summary_sections(text: str) -> tuple:
    """(head lines, [(day, section lines)]) of summaries.md, newest first as written."""
    head, sections = [], []
    for line in text.split("\n"):
        heading = DAY_HEADING.match(line)
        if heading:
            sections.append((date.fromisoformat(heading.group(1)), [line]))
        elif sections:
            sections[-1][1].append(line)
        else:
            head.append(line)
    while head and not head[-1].strip():
        head.pop()
    return head, sections


def ask_events(root: Path, day: date) -> list:
    """Lines on the asks opened, answered and withdrawn on that day, and those open now."""
    opened, closed, still = [], [], []
    for key, (status, fields, question) in asks(root).items():
        if f"asked {day.isoformat()}" in fields:
            opened.append(key)
        if status in ("answered", "withdrawn") and day.isoformat() in fields.split("·")[0]:
            closed.append(f"{key} {status}")
        if status == "open":
            still.append(key)
    return [f"Asks opened that day: {', '.join(opened) or 'none'}; answered or withdrawn: {', '.join(closed) or 'none'};"
            f" open now: {', '.join(still) or 'none'} (asks.md)."]


def backlog_counts(root: Path, now: datetime) -> list:
    """Per backlog page: its rows, how many are done or cancelled, and that share (capacity_scan's reading)."""
    out = []
    for page in sorted((root / "knowledge").rglob("*.md")):
        rel = page.relative_to(root / "knowledge")
        if rel.parts[0] in capacity_scan.BACKLOG_SKIP or not capacity_scan.backlog_page(page):
            continue
        rows = capacity_scan.backlog_rows(read(page))
        done = sum(row[3].strip("*_ ").lower().startswith(capacity_scan.CLOSED) for row in rows)
        if rows:
            out.append(f"{rel.as_posix()}: {len(rows)} rows, {done} done or cancelled ({100 * done // len(rows)}% of the "
                       f"rows), {len(rows) - done} not (read {local(now):%Y-%m-%d %H:%M} {ZONE_NAME})")
    return out


def capacity_lines(root: Path, now: float) -> list:
    running = capacity_scan.agents(capacity_scan.projects_root(), now)
    today = capacity_scan.utc_today(now)
    rows = capacity_scan.scan(root / DIRECTIVES, running, today, now)
    stack = capacity_scan.backlog(root / "knowledge", running, today, [row[0] for row in rows], now)
    return [capacity_scan.format_row(*row) for row in rows] + [capacity_scan.format_backlog(*row) for row in stack]


def day_packet(root: Path, day: date, now: datetime, previous: list, spend: list) -> tuple:
    """(packet, counts lines for the raw fallback)."""
    start, end = day_window(day)
    counts = []
    for repo, workflow in REPOS:
        prs, pr_full = merged_prs(root, repo, start, end) or (None, False)
        runs, run_full = deploys(root, repo, workflow, start, end) or (None, False) if workflow else ([], False)
        line = f"{repo}: " + ("PRs merged not read" if prs is None else f"{len(prs)} PRs merged"
                              + (" (gh's limit: maybe more)" if pr_full else ""))
        if workflow:
            outcomes = {}
            for *_, outcome, _title in runs or []:
                outcomes[outcome] = outcomes.get(outcome, 0) + 1
            line += ("; production runs not read" if runs is None else f"; {len(runs)} production runs ("
                     + (", ".join(f"{n} {what}" for what, n in sorted(outcomes.items())) or "none") + ")"
                     + (" (gh's limit: maybe more)" if run_full else ""))
        counts.append(line)
    try:
        _, _, days = parse_progress(read(root / PROGRESS))
        progress = render_day(day, days[day]) if day in days else ["(no entries: the job didn't run that day)"]
    except (OSError, ValueError):
        progress = ["(progress.md couldn't be read)"]
    try:
        capacity = capacity_lines(root, now.timestamp())
    except Exception:  # noqa: BLE001 - the summary says so instead
        capacity = ["(the capacity scan failed)"]
    parts = [f"The day: {day.isoformat()}, {day:%A}, 00:00-24:00 {ZONE_NAME}. Written at "
             f"{local(now):%Y-%m-%d %H:%M} {ZONE_NAME}.",
             "", f"Counts for 00:00-24:00 {ZONE_NAME} on {day.isoformat()} (gh):", *[f"- {line}" for line in counts],
             "", *ask_events(root, day), "", "Backlog pages now (rule 5; sizes are letters, so no size-weighted %):",
             *[f"- {line}" for line in backlog_counts(root, now)], "",
             "Open directives and backlog rows now (capacity_scan.py; NEXT is the CEO's next step, waits its hard wait):",
             *[f"- {line}" for line in capacity], "", "The day's progress (progress.md):", *progress, "",
             "The previous summary (summaries.md), for Since last:", *(previous or ["(none: this is the first)"]), "",
             "Spend (scripts/spend_report.py, read now; the script appends it after your text):", *spend]
    packet = clip("\n".join(scrub(line) for line in parts), DAY_PACKET)
    return packet + names_section(root, packet), counts, progress  # the ids' plain names


def check_summary(packet: str):
    def check(text: str):
        if not text:
            return "no text"
        if len(text.encode("utf-8")) > SUMMARY_BYTES:
            return f"over {SUMMARY_BYTES} bytes"
        if re.search(r"(?m)^#{1,2} ", text):
            return "a heading above ###"
        return unsourced(text, packet)
    return check


def raw_summary(counts: list, progress: list, root: Path, day: date, reason: str) -> list:
    blocks = [line[4:] for line in progress if line.startswith("### ")]
    return [f"(raw; the summary writer failed: {reason})", "",
            f"Counts, 00:00-24:00 {ZONE_NAME} (gh): {'; '.join(counts)}.", "", *ask_events(root, day), "",
            "The day's blocks: " + ("; ".join(blocks) or "none") + " (progress.md, its archive after the roll-up)."]


def summarise(root: Path, day: date, now: datetime) -> None:
    path = root / SUMMARIES
    head, sections = summary_sections(read(path))
    previous = next((lines for when, lines in sections if when < day), [])
    try:
        last = parse_progress(read(root / PROGRESS))[1]
    except (OSError, ValueError):
        last = []
    spend, reason = spend_lines(now, last)
    packet, counts, progress = day_packet(root, day, now, [clip("\n".join(previous), 5000)] if previous else [],
                                          spend)
    text, failed = written(packet, RULES / "daily.md", DAY_MODEL, check_summary(packet),
                           f"summary {day.isoformat()}", 600)
    body = text.split("\n") if text is not None else raw_summary(counts, progress, root, day, failed)
    section = [f"## {day.isoformat()}, {day:%A}",
               f"Written {local(now):%Y-%m-%d %H:%M} {ZONE_NAME}, for 00:00-24:00 {ZONE_NAME}.",
               "", *body, "", f"### Spend (read {local(now):%H:%M} {ZONE_NAME})", "", *spend, ""]

    def change(text: str) -> str:
        head, sections = summary_sections(text)
        kept = [(when, lines) for when, lines in sections if when != day]
        kept.append((day, section))
        kept.sort(key=lambda pair: pair[0], reverse=True)
        out = [*head]
        for _, lines in kept:
            while lines and not lines[-1].strip():
                lines = lines[:-1]
            out += ["", *lines]
        return "\n".join(out) + "\n"

    rewrite(path, change, now)
    say(f"summary of {day.isoformat()} written" + (f" raw ({failed})" if text is None else "")
        + ("" if reason is None else f"; spend not read: {reason}"))


def due(day: date) -> datetime:
    """When a day's summary is due: SUMMARY_HOUR the next morning, local."""
    return datetime.combine(day + timedelta(days=1), datetime.min.time(), ZONE) + timedelta(hours=SUMMARY_HOUR)


def day(root: Path, now: datetime) -> int:
    state = load_state(root)
    if state is None or not (root / SUMMARIES).exists():
        say("no state or no summaries.md: no summary")
        return 0 if state is None else 1
    today = local(now).date()
    done = date.fromisoformat(state.get("summarised") or (today - timedelta(days=1)).isoformat())
    for _ in range(MAX_DAYS):
        nxt = done + timedelta(days=1)
        if local(now) < due(nxt):
            break
        summarise(root, nxt, now)
        state = dict(load_state(root) or state, summarised=nxt.isoformat())
        save_state(root, state)
        done = nxt
    return roll_up(root, now)


def roll_up(root: Path, now: datetime) -> int:
    """kb_sweep's roll-up of the three desk pages, word for word, after the summary; a pass moves one
    month a page, so a few passes catch up after a long sleep. Ages count from the local date."""
    for _ in range(3):
        moves = plan_desk(root / "knowledge", local(now).date())
        if not moves:
            break
        for move in moves:
            if not apply_move(move):
                say(f"roll-up stopped: {move.page.name} or {move.cold.name} changed while it ran; the next hour tries again")
                return 1
            say(f"rolled up {move.page.name} -> {move.cold.name}: {move.what}")
    return 0


# ---- the reader and the watcher -------------------------------------------------------------------------------------

def cell(text: str) -> str:
    """A table cell answer_rows reads back as the same text (uncell): a backslash, `|` and `<` escaped with a
    backslash, a line break as <br> (\\r\\n and a lone \\r are line breaks, as normal() has them)."""
    return re.sub(r"[\\|<]", lambda found: "\\" + found.group(0), normal(text, strip=False)).replace("\n", "<br>")


def uncell(text: str) -> str:
    return re.sub(r"\\([\\|<])|<br>", lambda found: found.group(1) or "\n", text)


def normal(text: str, strip: bool = True) -> str:
    """The Board's words as the reader compares them: line breaks as \\n, and (by default) no space at either end,
    which a table cell doesn't keep."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text.strip() if strip else text


def answer_rows(root: Path) -> list:
    """[(R number, ask id, field, medium id, the Board's words)] of every answers page's rows, in R order."""
    rows = []
    for page in sorted((root / ANSWERS).glob("*-W*.md")):
        for line in read(page).split("\n"):
            cells = [part.strip() for part in CELL.split(line)[1:-1]]
            if len(cells) == 7 and re.fullmatch(r"R-\d+", cells[0]):
                rows.append((int(cells[0][2:]), cells[1], uncell(cells[2]), uncell(cells[5]), uncell(cells[6])))
    return sorted(rows)


def week_head(now: datetime) -> tuple:
    """(the name of this week's answers page, the head week_page() makes it with)."""
    year, week, _ = local(now).isocalendar()
    return f"{year}-W{week:02d}.md", (
        f"---\ntitle: The Board's answers, {year}-W{week:02d}\nowner: board\nstatus: active\n"
        f"updated: {local(now).date()}\nrelated: [README.md, ../../company/board-desk/asks.md]\n---\n\n"
        f"# The Board's answers, {year}-W{week:02d}\n\nWord for word, from the medium's own response, "
        f"written only by the desk's reader ([README](README.md)).\n\n{ANSWERS_HEAD}\n")


def week_page(root: Path, now: datetime) -> Path:
    """This week's answers page, made with its head if it isn't there."""
    name, head = week_head(now)
    path = root / ANSWERS / name
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        write(path, head, None)
    return path


def reader_log(root: Path, now: datetime, change, why: str) -> None:
    """A change not kept, word for word, in the reader's gitignored log: data, never the Board's word.
    Sealed (answers_seal.writing())."""
    path = root / READER_LOG
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps({"at": now.isoformat(), "why": why, "change": change}, default=str) + "\n"
    with answers_seal.writing(root, READER_LOG, line.encode(), append=True):
        with open(path, "a") as file:
            file.write(line)


def once(root: Path, now: datetime, refused: dict, change, why: str) -> bool:
    """Log a change the reader can't use, the first time its text comes (each read reaches back over the last);
    whether this was the first."""
    key = "?" + hashlib.sha256(repr(change).encode("utf-8")).hexdigest()[:16]
    if key in refused:
        return False
    refused[key] = [now.isoformat()]
    reader_log(root, now, change, why)
    return True


def record(root: Path, state: dict, changes: list, now: datetime, fields: tuple = ()) -> tuple:
    """([R-ids kept], [ask ids not tied to the Board]): each change of a Board-only field's value against the reader's
    copy (the last R-row for its medium id and field) is kept as a new R-row, word for word, only when the medium names
    the Board (state["board"], picked at install from people()) as its last editor; else it goes to the reader's log,
    once, and the next hour's entry names its ask. A change it can't read, or of a field that isn't the Board's (any
    but BOARD_FIELDS and fields, the columns setup removes, keep_removed(); on a row the Board added to Q&A, every
    field is its own but what the push wrote there, the state's "wrote"), goes to the log once too (by its text); the
    first is named by its ask if it has one. R numbers count on from the seal's highest too, so a row deleted outside
    the reader never has its R-id given again; the rows are sealed as they are written (answers_seal.written()). A row a
    clear or seal set aside is no copy: the Board's words there, entered again, are kept anew."""
    rows, board, kept_out = answer_rows(root), str(state.get("board") or ""), answers_seal.aside(root)
    copy = {(medium, field): words for number, _, field, medium, words in rows if f"R-{number}" not in kept_out}
    number = max(rows[-1][0] if rows else 0, answers_seal.top(root))
    refused, kept, untied, lines = state.setdefault("refused", {}), [], [], []
    for change in changes:
        try:
            medium, ask, field, value = (str(change[key]) for key in ("medium_id", "ask", "field", "value"))
            editor, edited = str(change.get("editor") or ""), parse_time(change["edited_at"])
        except (KeyError, TypeError, ValueError, AttributeError):
            if once(root, now, refused, change, "unreadable"):
                ask = str(change.get("ask") or "") if isinstance(change, dict) else ""
                untied.append(ask if ASKED.fullmatch(ask) else "a row with no ask id")
            continue
        if ask not in BOARD_ROW_ASKS and field not in BOARD_FIELDS + tuple(fields):
            once(root, now, refused, change, "not a Board-only field")
            continue
        if normal(value) == normal(copy.get((medium, field), "")):
            continue  # no change: the window's overlap, or another field of the row
        if ask in BOARD_ROW_ASKS and adapter_notion.desk_wrote(state.get("wrote") or {}, medium, field, value):
            continue  # the CEO's answer, as the push wrote it in the Board's row (a directive's too)
        why = ("no Board id recorded" if not board else "no editor" if not editor else
               "another editor" if editor != board else
               "made by another member" if ask == NEW_DIRECTIVE and str(change.get("creator") or "") != board else
               "" if ASKED.fullmatch(ask) else "no ask id")
        if not why:
            number += 1
            copy[(medium, field)] = value
            refused.pop(f"{medium}|{field}", None)
            kept.append(f"R-{number}")
            lines.append(f"| R-{number} | {ask} | {cell(field)} | {local(edited):%Y-%m-%d %H:%M} "
                         f"| {local(now):%Y-%m-%d %H:%M} "
                         f"| {cell(medium)} | {cell(value)} |")
        elif ask == NEW_DIRECTIVE:  # a row someone else made or edited is no directive of
            # the Board's: logged by its ids alone, its words kept nowhere (the state holds their digest)
            if refused.get(f"{medium}|{field}") != [adapter_notion.digest(value), edited.isoformat()]:
                refused[f"{medium}|{field}"] = [adapter_notion.digest(value), edited.isoformat()]
                reader_log(root, now, {key: change[key] for key in change if key != "value"}, why)
                untied.append(ask)
        elif refused.get(f"{medium}|{field}") != [value, edited.isoformat()]:
            refused[f"{medium}|{field}"] = [value, edited.isoformat()]
            reader_log(root, now, change, why)
            untied.append(ask if ASKED.fullmatch(ask) else "a row with no ask id")
    if lines:
        name, head = week_head(now)
        with answers_seal.written(root, name, [answers_seal.row(line) for line in lines], head):
            rewrite(week_page(root, now), lambda text: text.rstrip("\n") + "\n" + "\n".join(lines) + "\n", now)
    cutoff = now - timedelta(days=UNTIED_DAYS)
    for key in [key for key, value in refused.items() if key.startswith("?") and parse_time(value[0]) < cutoff]:
        del refused[key]
    state["untied"] = [entry for entry in state.get("untied", []) if parse_time(entry[1]) >= cutoff]
    state["untied"] += [[ask, now.isoformat()] for ask in untied]
    return kept, untied


def fresh(change, floor) -> bool:
    """Whether a change is one adapter.poll(since) returns too: edited in or after floor, since's minute (or no time
    to tell: record() logs it)."""
    try:
        return floor is None or parse_time(change["edited_at"]) >= floor
    except (KeyError, TypeError, ValueError, AttributeError):
        return True


def audit(root: Path, state: dict, changes: list, floor, in_trash=None) -> list:
    """The hourly check against Notion: [(subject, what, change)] for each
    Board-only field whose value in Notion's full read (changes) differs from the last answers row for it, when the
    reader has read it already (edited before floor, this read's window; none before the first read) and neither set
    it aside (the state's "refused": another editor's) nor wrote it there (the push's "wrote"). A last row that differs
    is named by its R-id; a value no row has, by its ask and field. Notion's value counts, whatever the pages say. Then
    each row the CEO hasn't acted on yet (capacity_scan.unhandled_answers(); clean() keeps its row in Notion) whose
    field Notion's full read lacks is named by its R-id, with no change: a row Notion doesn't hold is no answer. One
    that in_trash(medium id, ask, field, words) (the adapter's: one GET, at most TRASH_READS a check, the rest named
    without one) finds in Notion's trash as its own page, not trashed by the desk, is not: deleted there, by the Board
    or a member (agents can't, guard_marketing_tools.py), it is one plain line and stays an answer. Rows a clear or
    seal set aside (answers_seal.aside(): never an answer) are left out; where a field's last row is
    one, Notion's value whose last editor is the Board comes back as a new R-row with no alarm (subject None), and
    one another editor edited last raises nothing."""
    if floor is None:
        return []  # the first read: nothing read before it to check
    kept_out, board = answers_seal.aside(root), str(state.get("board") or "")
    everything = answer_rows(root)
    ledger = [row for row in everything if f"R-{row[0]}" not in kept_out]
    latest = {(medium, field): (number, words) for number, _, field, medium, words in ledger}
    newest = {(medium, field): number for number, _, field, medium, _ in everything}
    set_aside = {key for key, number in newest.items() if f"R-{number}" in kept_out}  # its last row set aside
    refused, wrote, found = state.get("refused") or {}, state.get("wrote") or {}, []
    held = {(str(change.get("medium_id") or ""), str(change.get("field") or "")) for change in changes
            if isinstance(change, dict)}
    for change in changes:
        if fresh(change, floor):
            continue  # this read's own, record() keeps it or sets it aside now
        medium, ask, field, value = (str(change.get(key) or "") for key in ("medium_id", "ask", "field", "value"))
        last = latest.get((medium, field))
        if normal(value) == normal(last[1] if last else ""):
            continue
        aside = refused.get(f"{medium}|{field}") or []
        if (adapter_notion.desk_wrote(wrote, medium, field, value)
                or aside[:1] in ([value], [adapter_notion.digest(value)])):
            continue
        if (medium, field) in set_aside:  # its last row set aside: the Board's words in Notion read anew; another
            if board and str(change.get("editor") or "") == board:  # editor's (the desk's push of the row's other
                found.append((None, None, change))  # columns) raise nothing, the row staying set aside
            continue
        found.append((f"R-{last[0]}", f"its words aren't what Notion holds in {field} on {ask or medium}", change)
                     if last else (f"{ask or medium} {field}", "Notion holds words of the Board's no answers row has",
                                   change))
    open_ids = {r_id for r_id, _ in capacity_scan.unhandled_answers(root / ANSWERS, root / DIRECTIVES,
                                                                     keep_flagged=True)} - kept_out
    reads = 0
    for number, ask, field, medium, words in ledger:
        if f"R-{number}" not in open_ids or (medium, field) in held:
            continue
        deleted = False
        if in_trash and reads < TRASH_READS:
            reads += 1
            deleted = in_trash(medium, ask, field, words)
        if deleted:
            say(f"checked against Notion: R-{number}'s row is in Notion's trash, deleted there: no alarm")
        else:
            found.append((f"R-{number}", f"Notion holds no {field} on {ask or medium}", None))
    return found


def edit_lines(root: Path, found: list, changes: list, board: str, bot: str) -> list:
    """The desk's log line for each row audit() names, so an alarm's cause can
    be read later: its subject, as the alarm names it, with Notion's edit time of its row in UTC ISO form, or "?" where
    parse_time() can't read it, so nothing but a time goes in, and its last
    editor, "the Board" (the reader's id of it), "the desk" (the connection's bot) or "another editor". Notion gives a
    row one edit time and one last editor, so a field Notion's read lacks takes its row's, from any other field of it
    there. The ids are compared, never written: no name, email or user id goes in the log. It runs after the check's
    outcome is sealed and before record(), and reads only what the read has read already or reads next, under the
    same lock: the answers pages (audit(), which on a read with no since returns before it reads them; record() reads
    them next) and the desk's ids (poll(); the seal's, if notion.json was changed outside the desk, and with none
    sealed the read stopped first), so it has nothing new to fail on."""
    rows, media = {}, {f"R-{number}": medium for number, _, _, medium, _ in answer_rows(root)}
    for change in changes:
        if isinstance(change, dict):
            rows.setdefault(str(change.get("medium_id") or ""), change)
    lines = []
    for subject, _, change in found:
        if not subject:
            continue
        row = change or rows.get(media.get(subject))
        if not row:
            lines.append(f"checked against Notion: {subject}: no field of its row in Notion's read: no edit time or "
                         "editor")
            continue
        editor = str(row.get("editor") or "")
        who = "the Board" if board and editor == board else "the desk" if bot and editor == bot else "another editor"
        try:
            edited = parse_time(row.get("edited_at")).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        except (ValueError, OverflowError):
            edited = "?"
        lines.append(f"checked against Notion: {subject}: its row in Notion last edited at {edited} by {who}")
    return lines


def apart(changes: list) -> tuple:
    """(the poll's changes but the CLEAR_ROW row's, that row's): never an answer, never in the hourly check."""
    def mine(change) -> bool:
        return isinstance(change, dict) and change.get("ask") == adapter_notion.CLEAR_ROW
    return [change for change in changes if not mine(change)], [change for change in changes if mine(change)]


def board_cleared(root: Path, state: dict, changes: list) -> None:
    """The Board clears the ANSWERS TAMPERED alarms in Notion, by Yes in
    Your answer on the Asks row adapter_notion.CLEAR_ROW (push_desk() makes it once an alarm stands). Acted on only
    where Notion names the Board (the state's id; the seal's, if reader.json was changed) as the row's last editor, as
    record() takes an answer, and only when the row's (Your answer, Your words) differ from the last pair acted on, so
    it rests on the hook's refusal of those two fields by name to every caller in every checkout
    (scripts/hooks/guard_marketing_tools.py; an edit of the row's other columns or page acts on nothing): the alarms
    raised before it end, the R-rows they name are set aside, never an answer, and the files are sealed as they are
    (answers_seal.clear()); one plain line."""
    board, edits = str(state.get("board") or ""), {}
    for change in changes:
        try:
            field = change.get("field")
            if board and str(change.get("editor") or "") == board and field in adapter_notion.BOARD_FIELDS:
                edits.setdefault(parse_time(change["edited_at"]), {})[field] = str(change.get("value") or "")
        except (KeyError, TypeError, ValueError, AttributeError):
            continue
    if not edits:
        return
    edited = max(edits)
    pair = tuple(normal(edits[edited].get(field, "")) for field in adapter_notion.BOARD_FIELDS)
    done = answers_seal.clear(root, edited, pair) if pair[0] == "Yes" else None
    if done:
        at = f"{local(edited):%Y-%m-%d %H:%M}"
        say(f"cleared in Notion: the Board picked Yes on \"{adapter_notion.CLEAR_ROW}\" at {at} {ZONE_NAME}: {done[0]} "
            f"ANSWERS TAMPERED lines raised before it ended, their rows set aside, never an answer; {done[1]} raised "
            "since stand; the answers and the reader's files sealed as they are")


def read_board(root: Path, adapter, now: datetime, push=None) -> int:
    """One read of the medium: adapter.poll(since) returns each Board-only field's value on the rows edited since the
    last read began, less READ_OVERLAP, as {medium_id, page, ask, field, value, editor, edited_at}; record() keeps
    what the Board wrote. Then push(state), if given, under the same lock, once the answers are saved. Its own lock,
    so a long hour never holds an answer back. First the seal (answers_seal):
    a write cut short settled, each alarm's first sighting noted, and, while reader.json or notion.json isn't as the
    desk wrote it (they decide what counts as the Board's), a read with the ids the seal keeps of them, the alarm
    standing (with none kept yet, the read stops, nothing read or pushed); then, once an hour, the
    poll reads every row whole
    (adapter.poll(None), in place of this read's own) and audit() compares it with the answers pages, its outcome kept
    in the seal: its alarms, or the failure, re-raised as any read's; each row it names, with Notion's edit time and
    last editor, in the log (edit_lines()). record() gets what poll(since) would have given,
    and the Board's own words where a row differs (the CEO then reads Notion's words as a new R-row; another editor's
    stay out, and the alarm stands). The Asks row CLEAR_ROW's changes go to board_cleared(), never to record()."""
    began = time.monotonic()
    with locked(root, READER_LOCK):
        made = answers_seal.start(root)
        if made:
            say(f"seal: {made}; made from the answers pages and the reader's files as they are")
        answers_seal.settle(root)
        tampered = answers_seal.check(root)  # each first sighting at the time of this check
        answers_seal.note_seen(root, now + timedelta(seconds=time.monotonic() - began), tampered)
        changed = [(subject, what) for subject, what in tampered if subject in answers_seal.STOPS]
        stop = [f"{subject}: {what}" for subject, what in changed
                if answers_seal.sealed(root, READER if subject == READER.name else adapter_notion.IDS) is None]
        if stop:
            say(f"read stopped, nothing read or pushed: {'; '.join(stop)} (the desk's state, changed outside it, and "
                "no ids of it sealed yet); until it is put back as the desk wrote it, or the Board clears the alarms")
            return 1
        if changed:  # read on, with the seal's ids; the alarm stands
            say(f"read with the sealed ids: {'; '.join(f'{subject}: {what}' for subject, what in changed)}")
        state = load_state(root, READER) or {}
        since = parse_time(state["since"]) - READ_OVERLAP if state.get("since") else None
        if answers_seal.due(root, now):
            floor = since.astimezone(timezone.utc).replace(second=0, microsecond=0) if since else None
            try:
                everything, clears = apart(adapter.poll(None))
                found = audit(root, state, everything, floor, getattr(adapter, "in_trash", None))
            # any failure: the answers unchecked, never a pass (its name only, no text but Notion's own)
            except Exception as error:
                answers_seal.audited(root, now, error=str(error) if isinstance(error, adapter_notion.NotionError)
                                     else type(error).__name__)
                raise
            answers_seal.audited(root, now, [(subject, what) for subject, what, _ in found if subject])
            board = str(state.get("board") or "")
            changes = [change for change in everything if fresh(change, floor)] + [
                change for *_, change in found if change and board and str(change.get("editor") or "") == board]
            say(f"checked against Notion: {sum(1 for subject, *_ in found if subject)} not as Notion holds them"
                + (f"; {len(found) - sum(1 for subject, *_ in found if subject)} of the Board's read again where "
                   "the last row was set aside" if any(subject is None for subject, *_ in found) else ""))
            for line in edit_lines(root, found, everything, board,
                                   str((adapter_notion.load_ids(root) or {}).get("bot") or "")):
                say(line)
        else:
            changes, clears = apart(adapter.poll(since))
        board_cleared(root, state, clears)
        kept, untied = record(root, state, changes, now)
        state["since"] = now.isoformat()
        save_state(root, state, READER)
        if push:
            try:
                push(state)
            finally:
                save_state(root, state, READER)
    say(f"read: {len(kept)} answers kept ({', '.join(kept) or 'none'}), {len(untied)} changes not tied to the Board")
    return 0


def ask_fields(root: Path, path: Path = None) -> dict:
    """{ask id: {field: text}} of asks.md's asks, open and closed, as the medium's agent properties
    (adapter_notion.ASK_FIELDS): its labelled lines, every other line in Details, the heading's words after the id
    as Status. With no Question line (a Board step's), Question is its Step or Steps line's text, else its first
    labelled line's. The
    "Your answer" line is left out: that is the Board's, in the medium. Also the two the Asks table's
    view sorts by (adapter_notion.ASK_SORTS): State, from the status word, and
    Priority, from the Priority line's first digit (_templates/ask.md), which stays in Details with its why. And Body,
    the ask's lines but the "Your answer" one, as asks.md formats them, for its row's page. Given a
    path, that page's asks instead (an archive's: keep_removed())."""
    path, found, current = path or root / ASKS, {}, None
    if not path.exists():
        return {}
    states = dict(zip(("open", "answered", "withdrawn"), adapter_notion.STATES))
    for line in read(path).split("\n"):
        heading = ASK_HEADING.match(line)
        if heading:
            current = heading.group(1)
            found[current] = {"Status": (heading.group(2) + heading.group(3)).strip(" ·"), "Details": [],
                              "State": states.get((heading.group(2).split() or [""])[0].lower(), ""), "Body": []}
            continue
        if line.startswith("#"):
            current = None
        if current is None or not line.strip():
            if current is not None:
                found[current]["Body"].append("")
            continue
        labelled = ASK_LINE.match(line)
        label = labelled.group(1).strip().lower() if labelled else ""
        if label.startswith("your answer"):
            continue
        found[current]["Body"].append(line)  # its row's page, formatted as asks.md has it
        name = {"question": "Question", "alternative": "Alternative", "allows and costs": "Cost and undo"}.get(
            label, "Recommended" if label.startswith("recommended") else None)
        if name:
            found[current][name] = labelled.group(2).replace("**", "")
        else:
            found[current]["Details"].append(line.replace("**", ""))
        rank = re.match(r"\s*([123])\b", labelled.group(2)) if label == "priority" else None
        if rank:
            found[current]["Priority"] = adapter_notion.PRIORITIES[int(rank.group(1)) - 1]
        if label.startswith("step") and labelled.group(2).strip():  # a Board step's title, when it has no Question
            found[current].setdefault("step", labelled.group(2).replace("**", ""))  # line
        elif labelled and labelled.group(2).strip():
            found[current].setdefault("first", labelled.group(2).replace("**", ""))
    for fields in found.values():
        step, first = fields.pop("step", ""), fields.pop("first", "")
        if not fields.get("Question") and (step or first):
            fields["Question"] = step or first  # else the first labelled line's text
    return {ask: {**fields, "Details": "\n".join(fields["Details"]), "Body": "\n".join(fields["Body"]).strip("\n")}
            for ask, fields in found.items()}


def qa_entries(root: Path) -> dict:
    """{Q-id: {"page", "lines", "fields"}} of qa.md's questions and its archives',
    lowest id first, the page's over an archive's: the row's body (a first line with the day added to the time asked,
    then the entry's lines) and its fields (adapter_notion.QA_FIELDS, the Board's words as Question). Answer holds the
    Answer line, then every other line but Your words, Sources and Asked before, labelled ("Still true from Q-1: …",
    "Updated: …"), in the page's order. An entry runs to the next heading of level 1 to 3 outside a fenced code block:
    its #### and deeper headings, code and blank lines are its own, whole.
    A Row line, the row the Board added that the entry answers, is "row_ref"."""
    found = {}
    for path in [*sorted((root / DESK).glob("qa-archive-*.md")), root / QA]:
        if not path.exists():
            continue
        day, current, fence = "", None, None
        for line in read(path).split("\n"):
            code = fence is not None  # a fenced code block's line, "# a shell comment" too, is the entry's
            if code:
                fence = None if line.strip().startswith(fence) and not line.strip().strip(fence[0]) else fence
            elif current is not None and adapter_notion.FENCE.match(line):
                fence = adapter_notion.FENCE.match(line).group(1)
            dated, heading = (None, None) if code else (QA_DAY.match(line), QA_HEADING.match(line))
            if dated:
                day = dated.group(1)
            if heading:
                current, parts = heading.group(1), [part.strip() for part in heading.group(2).strip(" ·").split(" · ")]
                if current in found:  # an id is never reused, so say it, once a read
                    say(f"qa: {current} is written twice ({found[current]['page']} and "
                        f"{path.relative_to(root).as_posix()}); only the later one goes to Notion")
                asked = " ".join([day] + [part[len("asked "):] for part in parts if part.startswith("asked ")]).strip()
                status, *topic = [part for part in parts if not part.startswith("asked ")] or [""]
                fields = {"Id": current, "Asked": asked, "Status": status, "Topic": " · ".join(topic), "Answer": []}
                found[current] = {"page": path.relative_to(root).as_posix(), "fields": fields,
                                  "lines": [f"{current} · {status} · {fields['Topic']} · asked {asked}"]}
                continue
            if not code and ENTRY_END.match(line):  # a new day or question, or another heading of level 1 to 3
                current = None
            if current is None:
                continue
            entry, labelled = found[current], ASK_LINE.match(line)
            if not line.strip():
                entry["lines"].append("")  # kept, so the row's body reads as the page does: a "---" stays a rule
                continue
            entry["lines"].append(line)
            label = labelled.group(1).strip() if labelled else ""
            name = {"your words": "Question", "sources": "Sources", "asked before": "Asked before"}.get(label.lower())
            if label.lower() == "row":
                entry["row_ref"] = labelled.group(2).strip()
            elif name:
                entry["fields"][name] = labelled.group(2)
            else:
                entry["fields"]["Answer"].append(labelled.group(2) if label.lower() == "answer" else
                                                 f"{label}: {labelled.group(2)}" if labelled else line.strip())
    for entry in found.values():
        entry["fields"]["Answer"] = "\n".join(entry["fields"]["Answer"])
        while entry["lines"][-1] == "":
            entry["lines"].pop()
    return dict(sorted(found.items(), key=lambda item: int(item[0][2:])))


def directive_status(text: str) -> str:
    """A directive's Status in the Directives table: Done for one
    done or cancelled (its "Directive status:" line's first word) or archived (its front matter's status); In
    progress for any other: open, in-progress, blocked, on hold, or none given."""
    found = DIRECTIVE_STATUS.search(text)
    head = text.split("\n---", 1)[0] if text.startswith("---") else ""
    done = (found.group(1) if found else "").lower() in ("done", "cancelled", "canceled", "closed")
    return "Done" if done or re.search(r"^status:[ \t]*archived\b", head, re.M) else "In progress"


def verbatim(text: str) -> str:
    """The Board's own words: a directive's "## Directive (verbatim)" section, its quote marks off, its first 2,000
    characters."""
    lines, inside = [], False
    for line in text.split("\n"):
        if line.startswith("## "):
            if inside:
                break
            inside = line.strip().lower().startswith("## directive (verbatim)")
        elif inside:
            lines.append(re.sub(r"^> ?", "", line))
    return "\n".join(lines).strip()[:adapter_notion.TEXT_LIMIT]


def directive_items(root: Path, now: datetime, ledger: list) -> tuple:
    """({D-id: item}, {D-id: the Board's row it files, or None}). An item for each directive of
    knowledge/board/directives/ (archives aside) that is open, or done within KEEP_DAYS: its front-matter title, Status
    (directive_status()), "updated" (Last updated: the newest of its status-log rows' dates and its hourly entries'
    times, local), its "words" (verbatim()), the "lines" of its row's page (its hourly entries of the last KEEP_DAYS,
    newest first, each under its hours, then a link to its file) and its "row": the row the Board added that it files
    (`R-1 New directive` in its file, R-1 an R-row of that kind), if any. The second holds those done longer ago, which
    leave Notion (clean())."""
    try:  # read only: the hour writes it
        kept = json.loads((root / DIRECTIVE_PROGRESS).read_text())
    except (OSError, ValueError):
        kept = {}
    newest, board = {}, {number: medium for number, ask, _, medium, _ in ledger if ask == NEW_DIRECTIVE}
    for directive, day, _, _ in status_rows(root).values():
        newest[directive] = max(newest.get(directive, ""), day)
    cutoff, items, old = now - timedelta(days=KEEP_DAYS), {}, {}
    for page in sorted((root / DIRECTIVES).glob("D-*.md")):
        if "-archive" in page.stem:
            continue
        did, text = page.stem, read(page)
        hours = {end: entry for end, entry in (kept.get(did) or {}).items() if parse_time(end) >= cutoff}
        updated = max([newest.get(did, "")] + [f"{local(parse_time(end)):%Y-%m-%d %H:%M}" for end in hours])
        row, status = next((board[int(n)] for n in FILED.findall(text) if int(n) in board), None), directive_status(text)
        if status == "Done" and updated[:10] < f"{local(cutoff):%Y-%m-%d}":
            old[did] = row
            continue
        lines = []
        for end in sorted(hours, reverse=True):
            lines += [f"### {local(parse_time(hours[end]['start'])):%Y-%m-%d %H:%M}-{local(parse_time(end)):%H:%M} "
                      f"{ZONE_NAME}", "", *hours[end]["lines"], ""]
        lines += ([] if hours else [f"No hourly report in the last {KEEP_DAYS} days.", ""]) + [
            f"The whole directive: [{did}.md]({adapter_notion.GITHUB}{DIRECTIVES.as_posix()}/{did}.md)"
            if adapter_notion.GITHUB else f"The whole directive: {DIRECTIVES.as_posix()}/{did}.md"]
        items[did] = {"title": front_title(page) or did, "Status": status, "updated": updated, "words": verbatim(text),
                      "lines": lines, "row": row}
    return items, old


def directive_entries(text: str) -> dict:
    """{D-id: lines} of directives.md's answer: each "D-…:" line, then that directive's lines."""
    found, current = {}, None
    for line in entry_lines(text):
        head = DIRECTIVE_HEAD.match(line.strip("*#` "))
        if head:
            current = head.group(1)
            found.setdefault(current, [])
        elif current:
            found[current].append(line)
    return found


def check_directives(packet: str, wanted: list):
    def check(text: str):
        found = directive_entries(text)
        missing = [directive for directive in wanted if not found.get(directive)]
        if missing:
            return f"no entry for {', '.join(missing)}"
        for directive, lines in found.items():
            if len(lines) > DIRECTIVE_LINES:
                return f"over {DIRECTIVE_LINES} lines for {directive}"
            if len("\n".join(lines).encode("utf-8")) > DIRECTIVE_BYTES:
                return f"over {DIRECTIVE_BYTES} bytes for {directive}"
        return unsourced(text, packet)
    return check


def directive_hour(root: Path, rows: list, start: datetime, end: datetime, now: datetime) -> None:
    """The hour's new status-log rows, by directive, as one plain
    entry of 1 to 3 lines for each (board_desk/directives.md: the hour writer's rules, for each directive alone; one
    more turn of the hour's model, as hour() runs it), kept in DIRECTIVE_PROGRESS, KEEP_DAYS, for the directive's
    row's page in the Directives table. A writer that fails leaves each directive its first rows, raw and marked,
    as raw_entry() does. Only once setup has made that table: until then nothing runs."""
    by = {}
    for directive, day, who, entry in rows:
        rank = 0 if PRIORITY.match(entry) else 2 if entry.startswith("NEXT:") else 1
        by.setdefault(directive, []).append((rank, scrub(f"[{directive}, {who}, row dated {day}] "
                                                         f"{clip(entry, ROW_CUT[rank])}"), None))
    if not by:
        return
    items = [item for directive in by for item in sorted(by[directive], key=lambda item: item[0])]
    packet = fit([f"The hour: {local(start):%Y-%m-%d %H:%M}-{local(end):%H:%M} {ZONE_NAME}.",
                  "Its new status-log rows, each with its directive's id first:"], items, HOUR_PACKET)[0]
    packet += names_section(root, packet)
    wanted = [directive for directive in by if f"[{directive}," in packet]
    text, reason = written(packet, RULES / "directives.md", HOUR_MODEL, check_directives(packet, wanted),
                           f"directives {local(start):%H:%M}-{local(end):%H:%M}", 300)
    found = directive_entries(text) if text is not None else {}
    try:
        kept = json.loads((root / DIRECTIVE_PROGRESS).read_text())
    except (OSError, ValueError):
        kept = {}
    for directive, lines in by.items():
        kept.setdefault(directive, {})[end.isoformat()] = {"start": start.isoformat(), "lines": found.get(directive) or [
            clip(line.split("] ", 1)[-1], 300) for _, line, _ in lines[:DIRECTIVE_LINES - 1]] + [
            f"(raw; the writer failed: {reason or 'no entry for it'})"]}
    cutoff = now - timedelta(days=KEEP_DAYS)
    kept = {directive: {end: entry for end, entry in hours.items() if parse_time(end) >= cutoff}
            for directive, hours in kept.items()}
    save_state(root, {directive: hours for directive, hours in kept.items() if hours}, DIRECTIVE_PROGRESS)


def closed_asks(root: Path) -> dict:
    """{ask id: the day it was answered or withdrawn} from asks.md and its archives."""
    found = {}
    for path in [*sorted((root / DESK).glob("asks-archive-*.md")), root / ASKS]:
        for line in read(path).split("\n") if path.exists() else []:
            heading = ASK_HEADING.match(line)
            day = DATE.search(heading.group(2)) if heading else None
            if day and heading.group(2).split()[0].lower() in ("answered", "withdrawn"):
                found[heading.group(1)] = day.group()
    return found


def done_before(root: Path, now: datetime, entries: dict, state: dict) -> tuple:
    """(Q-ids, ask ids) done more than KEEP_DAYS ago, local days: a question asked and last
    changed before then (its entry is its answer, written in the turn it was asked; one answered again in place, or
    marked changed, counts from that day), an ask answered or withdrawn
    before then. The reader's state keeps {Q-id: [its entry's digest, the day a read first saw it changed]};
    an entry first seen counts from its Asked date."""
    day, today = (local(now).date() - timedelta(days=KEEP_DAYS)).isoformat(), local(now).date().isoformat()
    changed = state.setdefault("changed", {})
    for qid, entry in entries.items():
        mark = adapter_notion.digest("\n".join(entry["lines"]))
        if (changed.get(qid) or [mark])[0] != mark:
            changed[qid] = [mark, today]
        changed.setdefault(qid, [mark, ""])
    return ({qid for qid, entry in entries.items()
             if "" < entry["fields"]["Asked"][:10] and max(entry["fields"]["Asked"][:10], changed[qid][1]) < day},
            {ask for ask, closed in closed_asks(root).items() if closed < day})


def clean(root: Path, adapter, state: dict, now: datetime) -> dict:
    """At the first read at or after 10:00 each day,
    every done row older than KEEP_DAYS goes to Notion's trash, once (adapter.trash(); undo: restore it there): a
    question's asked before then (the desk's row, or the row the Board added that it answers), an ask's answered or
    withdrawn before then, a directive's done before then (its row, or the row the Board added that it files).
    Nothing open, unanswered or not started: a row the Board added stays while it has an R-row recorded within
    KEEP_DAYS, or one no status-log row names yet (capacity_scan's unhandled answers). push_desk() pushes none of
    the old ones again, so none is made again. The
    pages: progress.md keeps its days up to the latest summarised one, and summaries.md 5 days (the roll-up), so
    neither shows anything older; a directive's page keeps its last KEEP_DAYS of entries (directive_items()). A count
    for each table in the log; {table: count}."""
    today = f"{local(now):%Y-%m-%d}"
    if local(now).hour < SUMMARY_HOUR or state.get("cleaned") == today:
        return {}
    ledger = answer_rows(root)
    entries = board_rows(qa_entries(root), ledger)[0]
    questions, asks_done = done_before(root, now, entries, state)
    old = directive_items(root, now, ledger)[1] if "directives" in (adapter.ids.get("databases") or {}) else {}
    day, recorded = (local(now).date() - timedelta(days=KEEP_DAYS)).isoformat(), answers(root)
    unhandled = {r_id for r_id, _ in capacity_scan.unhandled_answers(root / ANSWERS, root / DIRECTIVES,
                                                                      keep_flagged=True)}
    open_rows = {medium for number, _, _, medium, _ in ledger  # a row the Board
                 if f"R-{number}" in unhandled or (recorded.get(f"R-{number}") or ("", ""))[1][:10] >= day}  # wrote
    # in within KEEP_DAYS, or whose words no status-log row has handled yet, is open: it stays
    by_what = {}
    for row, what in (adapter.ids.get("rows") or {}).items():
        by_what.setdefault(what, []).append(row)
    plan = {"Q&A": [(qid, row) for qid in sorted(questions)
                    for row in by_what.get(qid, []) + [entries[qid].get("row")] if row and row not in open_rows],
            "Asks": [(ask, row) for ask in sorted(asks_done) for row in by_what.get(ask, [])
                     if row not in open_rows],  # as the Q&A and Directives rows
            "Directives": [(did, row) for did, filed in sorted(old.items()) for row in by_what.get(did, []) + [filed]
                           if row and row not in open_rows]}

    def trashed(what: str, row: str) -> bool:
        try:
            return adapter.trash(row, what)
        except adapter_notion.NotionError as error:
            if error.status != 400:
                raise
            say(f"cleanup: Notion refused to move {what}'s row to its trash ({error.named()}); tried again tomorrow")
            return False

    counts = {table: sum(trashed(what, row) for what, row in pairs) for table, pairs in plan.items()}
    state["cleaned"] = today
    say(f"cleanup: rows done more than {KEEP_DAYS} days ago, moved to Notion's trash: "
        + ", ".join(f"{table} {count}" for table, count in counts.items()))
    return counts


def push_desk(root: Path, adapter, state: dict, now: datetime) -> list:
    """`read`'s pushes, after the answers: each ask of asks.md, then each page of adapter_notion.PAGES, then each
    question of qa.md and its archives, whole, through the adapter; [(what, outcome)]. An edit in the medium saved
    before it is replaced gets one line in the next hour's entry, once for each new outcome. An item Notion refuses
    (a 400) is "refused: Notion 400: <code>", on its own log line with Notion's message (adapter_notion.message_of()),
    and tried again at the next read; the rest go. A
    refusal still there an hour after it was first read gets one line in the next hour's entry, once for each new one.
    A question whose Row line names a row the Board added is written into that
    row; one whose Row line names none is "not pushed: …", and gets one line in the next hour's entry too."""
    ledger = answer_rows(root)
    copy = {(medium, field): words for _, _, field, medium, words in ledger}
    refused = state.get("refused", {})

    def refused_then(row: str, field: str, value: str, edited) -> bool:
        entry = refused.get(f"{row}|{field}") or []
        try:  # a directive row's words are refused by their digest (record())
            return (len(entry) == 2 and entry[0] in (value, adapter_notion.digest(value))
                    and parse_time(entry[1]) == parse_time(edited))
        except (TypeError, ValueError):
            return False

    def settled(row: str, values: dict, edited) -> bool:  # every Board-only value read: kept as it is, or refused as
        # it is at the row's last edit time, so the Board's same words typed again since are read first
        return all(normal(value) == normal(copy.get((row, field), "")) or refused_then(row, field, value, edited)
                   for field, value in values.items())

    refusals = {}  # what: its refusal with Notion's message, for the log line alone

    def one(what: str, push, *args) -> str:  # Notion's 400 refuses that item alone (a block or page it won't take): its
        # outcome, and the rest still go; any other failure stops the read
        try:
            return push(*args)
        except adapter_notion.NotionError as error:
            if error.status != 400:
                raise
            refusals[what] = error.named()
            return f"refused: {error}"

    entries, unnamed = board_rows(qa_entries(root), ledger)
    old_questions, old_asks = done_before(root, now, entries, state)  # done, out of Notion
    outcomes = [(ask, one(ask, adapter.push_ask, ask, fields, state, settled))
                for ask, fields in ask_fields(root).items() if ask not in old_asks]
    if (hasattr(adapter, "push_clear") and adapter_notion.CLEAR_ROW not in (adapter.ids.get("rows") or {}).values()
            and answers_seal.report(root)[0]):  # once an alarm stands
        outcomes.append((adapter_notion.CLEAR_ROW, one(adapter_notion.CLEAR_ROW, adapter.push_clear)))
    for key, (title, rel) in adapter_notion.PAGES.items():
        if (root / rel).exists():
            outcomes.append((title, one(title, adapter.push, key, read(root / rel), state, now)))
    outcomes += [(qid, unnamed.get(qid) or one(qid, adapter.push_qa, qid, entry, state, settled))
                 for qid, entry in entries.items() if qid not in old_questions]
    if "directives" in (adapter.ids.get("databases") or {}):  # once setup made it
        items, old = directive_items(root, now, ledger)
        for did, item in items.items():
            outcome = one(did, adapter.push_directive, did, item, state, settled)
            if outcome.startswith("not pushed"):  # the row the Board added is gone from Notion: the desk's own
                outcome = one(did, adapter.push_directive, did, {**item, "row": None}, state, settled)
            outcomes.append((did, outcome))
        filed = {item["row"] for item in items.values()} | set(old.values())
        recorded = {medium for _, ask, _, medium, _ in ledger if ask == NEW_DIRECTIVE}  # the Board's: an R-row
        for row in [row for row, ask in (adapter.ids.get("rows") or {}).items()
                    if ask == NEW_DIRECTIVE and row in recorded and row not in filed]:  # not filed yet: Not started
            what = f"the row you added to Directives ({row})"
            outcome = one(what, adapter.fill_row, "directives", row, row,
                          {"Status": {"select": {"name": "Not started"}}}, None, "", {}, state, settled)
            outcomes.append((what, "same" if outcome.startswith("not pushed") else outcome))  # gone: nothing to say
    said, lines = state.setdefault("said", {}), state.setdefault("desk", [])
    for what, outcome in outcomes:
        if not outcome.startswith(("waits", "not pushed", "kept")):
            said.pop(what, None)
        elif said.get(what) != outcome:
            said[what] = outcome
            lines.append([what, outcome, now.isoformat()])
    stuck, state["stuck"] = state.get("stuck", {}), {}  # what: [its refusal, first read, said]
    for what, outcome in outcomes:  # a refusal an hour on gets one line, once for each new outcome
        if outcome.startswith("refused"):
            then = stuck[what] if stuck.get(what, [None])[0] == outcome else [outcome, now.isoformat(), False]
            if not then[2] and now - parse_time(then[1]) >= timedelta(hours=1):
                then[2] = True
                lines.append([what, outcome, now.isoformat()])
            state["stuck"][what] = then
    state["desk"] = [line for line in lines if parse_time(line[2]) >= now - timedelta(days=UNTIED_DAYS)]
    moved = [f"{what}: {outcome}" for what, outcome in outcomes
             if outcome not in ("same", "not set up")
             and not outcome.startswith(("refused", "not pushed", "superseded"))]
    if moved:
        say(f"pushed: {'; '.join(moved)}")
    unpushed = [f"{what} ({outcome[len('not pushed: '):]})" for what, outcome in outcomes
                if outcome.startswith("not pushed")]
    if unpushed:  # a Row line that names no row of the Board's, or a row gone from Notion
        say(f"not pushed: {'; '.join(unpushed)}")
    waiting = [what for what, outcome in outcomes if outcome == "not set up"]
    if waiting:  # never under "pushed:"
        say(f"not in Notion until setup runs again: {', '.join(waiting)}")
    refused_now = [f"{what} ({refusals.get(what) or outcome[9:]})" for what, outcome in outcomes
                   if outcome.startswith("refused")]
    if refused_now:  # tried again at each read: what it holds may change, or Notion's limits
        say(f"Notion refused, not pushed: {'; '.join(refused_now)}")
    return outcomes


def board_rows(entries: dict, ledger: list) -> tuple:
    """(entries, {Q-id: 'not pushed: …'}): each entry whose Row line names a row the Board added to Q&A, by an R-id of
    it or its Notion id (an R-row of ask QA_ROW), with entry["row"], that row's id; of two naming one row, the higher
    Q-id's, the other superseded, which the hour doesn't name. Every entry has entry["answered"], {Q-id: row} of those,
    so a Q-id links to the row that holds its answer."""
    rows = {number: medium for number, ask, _, medium, _ in ledger if ask == QA_ROW}
    plain = {medium.replace("-", "").lower(): medium for medium in rows.values()}
    answered, unnamed = {}, {}
    for qid, entry in entries.items():  # in Q order: a higher Q-id comes later
        ref = entry.get("row_ref")
        if ref is None:
            continue
        flat = ref.replace("-", "").lower()
        named = [rows.get(int(r_id[2:])) for r_id in R_ID.findall(ref)] + [medium for key, medium in plain.items()
                                                                           if key in flat]
        row = next((medium for medium in named if medium), None)
        if row is None:
            unnamed[qid] = f"not pushed: its Row line ({ref}) names no row you added to the Q&A table"
            continue
        for other, held in list(answered.items()):
            if held == row:
                unnamed[other] = f"superseded: {qid} answers the same row"  # nothing to say
                del answered[other]
        answered[qid] = row
    for qid, entry in entries.items():
        entry["answered"] = answered
        if qid in answered:
            entry["row"] = answered[qid]
    return entries, unnamed


def desk_line(what: str, outcome: str) -> str:
    if outcome.startswith("refused"):
        return (f"Notion has refused {what} for an hour or more ({outcome[len('refused: '):]}), so Notion doesn't "
                "have it as the KB does; it is tried again at each read, and the reader's log has each refusal.")
    if outcome.startswith("not pushed"):
        return (f"{what} isn't in Notion ({outcome[len('not pushed: '):]}): the CEO fixes it in qa.md, and it is "
                "tried again at each read.")
    if outcome.startswith("kept"):
        columns = outcome[len("kept: "):]
        return (f"Your words in the {columns} of the row {what} answers stay as you wrote them, and reached the CEO; "
                f"the CEO's answer for {'those columns' if ', ' in columns else 'that column'} is {what} in qa.md, "
                "not in the row.")
    return (f"Someone edited {what} in Notion: the CEO has the text in the reader's log, and the page is rewritten "
            "at the next read. Write to the CEO in a new row of the Q&A table instead.")


def untied_lines(root: Path, named) -> tuple:
    """(the hour's line for each ask the reader couldn't tie to the Board, then each of push_desk's lines, that no
    entry has named yet; the keys of the entries now named). Marked by key, not by time, so an entry a read
    saves while the hour runs is named in the next one."""
    try:  # read only: a state the reader can't read is the reader's to set aside
        state = json.loads((root / READER).read_text())
    except (OSError, ValueError):
        return [], list(named)
    entries = [(ask, f"{ask}|{when}") for ask, when in state.get("untied", [])]
    asks_seen = []
    for ask, key in entries:
        if key not in named and ask not in asks_seen:
            asks_seen.append(ask)
    desk = [(what, outcome, f"desk|{what}|{outcome}|{when}") for what, outcome, when in state.get("desk", [])
            if not outcome.startswith("held")]  # not named
    names = plain_names(root, " ".join(asks_seen))  # an ask by its question, then its id
    named_as = {NOTE: "a note to the CEO", QA_ROW: "a row you added to the Q&A table",
                NEW_DIRECTIVE: "a row added to the Directives table",
                **{ask: f"your answer to {names[ask]} ({ask})" for ask in asks_seen if names.get(ask)}}  # not
    # named(): the parameter of that name shadows it here
    return ([f"A change on {named_as.get(ask, ask)} I couldn't tie to you: please re-enter it, or "
             "answer in the chat." for ask in asks_seen]
            + [desk_line(what, outcome) for what, outcome, key in desk if key not in named],
            [key for _, key in entries] + [key for _, _, key in desk])


def qa_digests(root: Path) -> dict:
    return {qid: adapter_notion.digest("\n".join(entry["lines"])) for qid, entry in qa_entries(root).items()}


def qa_line(old, now: dict, root: "Path | None" = None) -> list:
    """The hour's line on the Q&A list: its questions new or changed since the last entry, each by its words, then
    its Q-id (plain_names()); none on a state with no copy to compare."""
    if old is None:
        return []
    new, changed = [qid for qid in now if qid not in old], [qid for qid in now if qid in old and old[qid] != now[qid]]
    names = plain_names(root, " ".join(new + changed)) if root is not None and (new or changed) else {}
    said = ([f"new answers to {'; '.join(named(qid, names) for qid in new)}"] if new else []) + (
        [f"answers changed on {'; '.join(named(qid, names) for qid in changed)}"] if changed else [])
    return [f"Q&A: {' | '.join(said)}."] if said else []


def stalled_line(root: Path) -> list:
    """The hour's line on stalled orders: the first order id of each line `capacity_scan.py --stalled` prints; nothing
    while the scan has no such flag, or doesn't run."""
    done = run([sys.executable, str(CAPACITY_SCAN), "--stalled"], cwd=root, timeout=120)
    if done is None or "unrecognized arguments" in (done.stderr or ""):
        return []
    found = []
    for line in (done.stdout or "").split("\n"):
        order = ORDER_ID.search(line)
        if order and order.group() not in found:
            found.append(order.group())
    names = plain_names(root, " ".join(found))  # each by its directive's title first
    return [f"Stalled orders: {'; '.join(named(order, {order: names.get(order.split('/')[0], '')}) for order in found)}."
            ] if found else []


def tampered_lines(root: Path, now: datetime) -> list:
    """The hour's ANSWERS TAMPERED lines, at most TAMPERED_SHOWN and a count of the rest, and what ends them, then its
    NOT CHECKED line (answers_seal.report()): read again each hour, nothing kept
    in the state."""
    alarms, _, unchecked = answers_seal.report(root, now)
    more = len(alarms) - TAMPERED_SHOWN
    return (alarms[:TAMPERED_SHOWN] + ([f"{answers_seal.MARK}: {more} more (python3 scripts/capacity_scan.py)"]
                                       if more > 0 else [])
            + ([f"{answers_seal.MARK}: each stands until you, having looked, pick Yes in Your answer on the Asks row "
                f"\"{adapter_notion.CLEAR_ROW}\" in Notion; to end later ones, type something new in Your words "
                "there (or run python3 scripts/board_desk.py seal in a terminal). Rows I couldn't tie to your Notion "
                "edits are set aside, never taken as your answer, then too; if one was yours, enter it again"]
               if alarms else [])
            + ([unchecked] if unchecked else []))


def wait(root: Path, sleep=time.sleep) -> int:
    """The CEO's watcher: every WAIT_EVERY seconds, the answers no status-log row names yet; it prints one line for
    each and exits 0 once there are any (ceo.md, "Keep a watcher"). It only reads.
    Each ANSWERS TAMPERED and NOT CHECKED line prints once; one whose subject is new
    since it started exits 0 too (those there at its start don't, or a watcher started again would never wait). A row
    an alarm names never prints as the Board's answer (capacity_scan.unhandled_answers() leaves it out)."""
    shown, subjects, first = set(), set(), True
    while True:
        alarms, _, unchecked = answers_seal.report(root)
        for line in [line for line in alarms + [unchecked] if line and line not in shown]:
            print(line, flush=True)
            shown.add(line)
        new = {line.split(":")[0] for line in alarms} - subjects
        subjects |= new
        found = capacity_scan.unhandled_answers(root / ANSWERS, root / DIRECTIVES)
        if found:
            for r_id, ask in found:
                print(f"{r_id}: the Board gave a new directive in a row of Notion's Directives table: file it with "
                      f"/directive and write \"{r_id} {NEW_DIRECTIVE}\" in a row of its status log" if ask == NEW_DIRECTIVE else
                      f"{r_id}: the Board answered {ask}", flush=True)
            return 0
        if new and not first:
            return 0
        first = False
        sleep(WAIT_EVERY)


# ---- the medium: Notion ----------------------------------------------------------------------------------------

def notion_desk(root: Path, notion=None):
    return adapter_notion.Desk(root, lambda why, data: reader_log(root, utc_now(), data, why), notion)


def read_notion(root: Path, now: datetime, notion=None) -> int:
    """`read`: one poll, the answers kept, then the pushes. Before setup: one line, nothing read."""
    if not adapter_notion.ready(adapter_notion.load_ids(root)):
        say("read: Notion isn't set up, or its setup stopped part way (python3 scripts/board_desk.py setup)")
        return 0
    medium = notion_desk(root, notion)
    return read_board(root, medium, now, push=lambda state: (push_desk(root, medium, state, now),
                                                             clean(root, medium, state, now)))


def readback(root: Path, whats: list, notion=None) -> int:
    """`readback`: for each id given (a Q-id, a D-id or an ask id), its row's id, its property names and the count of
    its page's blocks, never their text: the CEO's check after
    the migration. A question that answers a row the Board added, or a directive that files one, shows that row. It
    only reads. First, each table's views and their sorts, with the sort setup gives the first."""
    if not adapter_notion.ready(adapter_notion.load_ids(root)):
        print("Notion isn't set up here (python3 scripts/board_desk.py setup, in the main checkout)")
        return 1
    medium, ledger = notion_desk(root, notion), answer_rows(root)
    for key, sorts in adapter_notion.VIEW_SORTS.items():
        if key not in medium.ids["databases"]:
            continue
        title = adapter_notion.DATABASES[key][0]
        try:
            found = adapter_notion.views(medium.notion, medium.ids["databases"][key]["database"])
        except adapter_notion.NotionError as error:
            if not 400 <= error.status < 500:
                raise
            print(f"The {title} table's views: Notion answered {error.status} ({error.code})")
            continue
        print(f"The {title} table's views: " + ("; ".join(f"{view} sorted by {adapter_notion.sort_words(its)}"
                                                         for view, its in found) or "none")
              + f" (setup's for the first: {adapter_notion.sort_words(sorts)})")
    entries = board_rows(qa_entries(root), ledger)[0]
    items, old = directive_items(root, utc_now(), ledger)
    rows = {}
    for row, what in (medium.ids.get("rows") or {}).items():
        rows.setdefault(what, row)
    for what in whats:
        row = (entries.get(what) or {}).get("row") or (items.get(what) or {}).get("row") or old.get(what) or rows.get(what)
        if not row:
            print(f"{what}: no row of it in {adapter_notion.IDS}")
            continue
        names, count = medium.readback(row)
        print(f"{what}: row {row}; properties: {', '.join(names)}; blocks in its page: {count}")
    return 0


def title_of(page: dict) -> str:
    return next((adapter_notion.text_of(prop) for prop in (page.get("properties") or {}).values()
                 if (prop or {}).get("type") == "title"), "")


def worktree(root: Path, command: str) -> bool:
    """Whether root is a worktree, said once: setup and attribution write the ids and the Board's id the main
    checkout's read job uses."""
    if capacity_scan.main_checkout(root) == root:
        return False
    print(f"refused: {root} is a worktree; {command} runs in the main checkout, whose read job uses what it records")
    return True


def setup(root: Path, notion=None) -> int:
    """`setup`: under the one page titled "Board desk" the Board shared with the connection, the desk's pages and its
    databases, each made once, their ids in notion.json and the fixed ones in board_desk/desk_ids.json; then the
    workspace's people, names and ids only. Run again, it makes only what PAGES or DATABASES gained since, adds once the
    columns of adapter_notion.MIGRATIONS to a database made before them (the Q&A table's No.) and removes REMOVALS',
    sorts each table's first view once (sort_views()), and moves to Notion's trash a page PAGES no longer has, under the
    reader's lock, as the read job writes notion.json too."""
    if worktree(root, "setup"):
        return 2
    with locked(root, READER_LOCK):
        return make_desk(root, notion or adapter_notion.Notion())


def unread_rows(root: Path, notion, source: str) -> list:
    """A table's rows, out of Notion's trash, changed at or after the minute the reader's last read reached back to,
    which that read may not have kept; every row before its first read (retire_notes(), the migration)."""
    state = load_state(root, READER) or {}
    since = parse_time(state["since"]) - READ_OVERLAP if state.get("since") else None
    minute = since.astimezone(timezone.utc).replace(second=0, microsecond=0) if since else None
    query = ({"filter": {"timestamp": "last_edited_time", "last_edited_time": {
        "on_or_after": minute.strftime("%Y-%m-%dT%H:%M:%S.000Z")}}} if minute else {})
    return [row for row in notion.listed("POST", f"/data_sources/{source}/query", query)
            if not (row.get("in_trash") or row.get("archived"))]


def keep_removed(root: Path, notion, ids: dict, key: str) -> str:
    """Before setup removes a table's REMOVALS columns, each one's text in
    a row the connection didn't edit last goes to record() as a change of that row, read now, as a read's: the Board's
    words become R-rows of the answers ledger, word for word, another editor's go to the reader's log. Not the desk's
    own text: an ask's column as asks.md or its archives have it now, the CEO's answer the push wrote in a row the Board
    added (record() sets it aside). A row of the desk's own Q&A entries holds no answer (own_row(): an edit there is
    never one), so its Answer goes to the reader's log, whole. A line for setup's output."""
    now, title, state = datetime.now(timezone.utc), adapter_notion.DATABASES[key][0], load_state(root, READER) or {}
    gone, rows, bot = adapter_notion.REMOVALS.get(key, ()), ids.get("rows") or {}, ids.get("bot")
    desk_text, changes, logged = {}, [], 0
    for path in [*sorted((root / DESK).glob("asks-archive-*.md")), root / ASKS] if key == "asks" else []:
        desk_text.update(ask_fields(root, path))  # the page's over an archive's, as closed_asks() reads them
    for row in notion.listed("POST", f"/data_sources/{ids['databases'][key]['data_source']}/query", {}):
        identity = str(row.get("id") or "")
        editor = str((row.get("last_edited_by") or {}).get("id") or "")
        creator = str((row.get("created_by") or {}).get("id") or "")
        if not identity or row.get("in_trash") or row.get("archived") or editor == bot:
            continue
        ask = rows.get(identity) or ("" if key == "asks" or creator == bot else QA_ROW)  # one poll() hasn't seen
        if ask == adapter_notion.TEST_ROW:
            continue  # the attribution test's row, never an answer
        for name in gone:
            value = adapter_notion.column_text((row.get("properties") or {}).get(name))
            if not value.strip() or normal(value) == normal((desk_text.get(ask) or {}).get(name, "")):
                continue
            change = {"medium_id": identity, "page": title, "ask": ask, "field": name, "value": value,
                      "editor": editor, "creator": creator, "edited_at": row.get("last_edited_time")}
            if key == "qa" and ask != QA_ROW:  # once, by its text, as record() logs a change it can't use
                logged += once(root, now, state.setdefault("refused", {}), change,
                               "a removed column's text in a row of the desk's own Q&A entries")
            else:
                changes.append(change)
    kept, untied = record(root, state, changes, now, gone)
    save_state(root, state, READER)
    return (f"their text kept first: your words as {', '.join(kept) or 'no new answer row'}; other texts to the "
            f"reader's log: {len(untied) + logged}")


def retire_notes(root: Path, notion, ids: dict) -> None:
    """Notes to the CEO's database to Notion's trash, once (ids'
    "retired"), under the reader's lock (setup's); not while a row there changed at or after the minute the reader's
    last read reached back to, which that read may not have kept. Undo: restore it from
    Notion's trash, and the next read reads it again."""
    notes = ids["databases"]["notes"]
    try:
        unread = unread_rows(root, notion, notes["data_source"])
    except adapter_notion.NotionError as error:
        if error.status != 404:
            raise
        unread = []  # gone from Notion already: nothing there to read
    if unread:
        print(f"Notes to the CEO is not retired: {len(unread)} of its rows changed since the reader's last read, or "
              "the reader hasn't read yet; run setup again after the next read (2 minutes).")
        return
    where = "moved to Notion's trash"
    try:
        notion.call("PATCH", f"/databases/{notes['database']}", {"in_trash": True})
    except adapter_notion.NotionError as error:
        if error.status != 404:
            raise
        where = "already gone from Notion"
    ids["retired"] = [*ids.get("retired", []), "notes"]
    adapter_notion.save_ids(root, ids)
    print(f"Notes to the CEO is retired ({where}); the Board writes in a new row of the Q&A table. Undo: restore it "
          "from Notion's trash, and the next read reads it again.")


def sort_views(root: Path, notion, ids: dict) -> None:
    """Each table's first view, as
    Notion lists them, gets adapter_notion.VIEW_SORTS' sort, once (ids' "sorted"), so a sort the Board sets there later
    stays. Each view of the table is printed first with the sorts it has, for the undo; after the
    PATCH the view is read back (GET /views/{id}), its sorts printed, and the table recorded sorted only when they are
    VIEW_SORTS', each sort's property by its
    name or its id (the data source's properties map ids to names), so a read-back by id
    never makes setup send a sort again over one the Board set. A refusal from Notion (a 4xx: the views API is
    unchecked live), an answer without the view's id, or other sorts read back, is printed and left for setup run
    again; the rest of setup goes on. Undo: sort the view by hand in Notion, as printed before."""

    def sorts_of(view) -> tuple:  # ((property, direction), ...) as Notion answers a view
        return tuple((str(sort.get("property")), str(sort.get("direction")))
                     for sort in (view if isinstance(view, dict) else {}).get("sorts") or [] if isinstance(sort, dict))

    for key, sorts in adapter_notion.VIEW_SORTS.items():
        if key not in ids["databases"] or key in ids.get("sorted", []):
            continue
        title, first, read = adapter_notion.DATABASES[key][0], None, ()
        try:
            found = [view if isinstance(view, dict) else {} for view in
                     notion.listed("GET", "/views", {"database_id": ids["databases"][key]["database"]})]
            had = [(str(view.get("id") or "(no id)"), sorts_of(view if "sorts" in view or not view.get("id") else
                                                               notion.call("GET", f"/views/{view['id']}")))
                   for view in found]
            print(f"The {title} table's views before setup sorts the first: "
                  + ("; ".join(f"{view} sorted by {adapter_notion.sort_words(was)}" for view, was in had) or "none")
                  + ".")
            first = found[0].get("id") if found else None
            if first:
                notion.call("PATCH", f"/views/{first}", {"sorts": [{"property": name, "direction": direction}
                                                                   for name, direction in sorts]})
                read = sorts_of(notion.call("GET", f"/views/{first}"))
                if read != tuple(sorts):  # by id, perhaps: each id read back as its column's name
                    source = notion.call("GET", f"/data_sources/{ids['databases'][key]['data_source']}")
                    named = {str(prop.get("id")): name for name, prop in (source.get("properties") or {}).items()
                             if isinstance(prop, dict) and prop.get("id")}
                    read = tuple((named.get(name, name), direction) for name, direction in read)
        except adapter_notion.NotionError as error:
            if not 400 <= error.status < 500:
                raise
            print(f"The {title} table's view is not sorted: Notion answered {error.status} ({error.code}); setup run "
                  "again tries again.")
            continue
        if not first:
            print(f"The {title} table has no view to sort in Notion's answer; setup run again tries again.")
            continue
        if read != tuple(sorts):
            print(f"The {title} table's view {first} reads back sorted by {adapter_notion.sort_words(read)}, not "
                  f"{adapter_notion.sort_words(sorts)}; setup run again sorts it again.")
            continue
        ids["sorted"] = [*ids.get("sorted", []), key]
        adapter_notion.save_ids(root, ids)
        print(f"The {title} table's view {first} is sorted by {adapter_notion.sort_words(sorts)}, as read back.")


def migrate(root: Path, notion, ids: dict) -> None:
    """Each table made before MIGRATIONS' columns gets them and loses REMOVALS', recorded as each completes (ids'
    "made_with"), then ids' "migrated" once all have. No text the Board typed in a removed column is lost: nothing moves
    while a row of a table losing columns changed at or after the minute the reader's last read reached back to
    (unread_rows(), as retire_notes()), so every edit of the Board's to then is read; and first each removed column's
    text goes to the reader (keep_removed())."""
    todo = [key for key in adapter_notion.MIGRATIONS
            if key in ids["databases"] and (ids.get("made_with") or {}).get(key) != adapter_notion.MIGRATION]
    for key in [key for key in todo if adapter_notion.REMOVALS.get(key)]:
        changed = unread_rows(root, notion, ids["databases"][key]["data_source"])
        if changed:
            print(f"The {adapter_notion.DATABASES[key][0]} table isn't changed yet, nor any other: {len(changed)} of "
                  "its rows changed since the reader's last read, or the reader hasn't read yet; run setup again "
                  "after the next read (2 minutes).")
            return
    for key in todo:
        names, gone = adapter_notion.MIGRATIONS[key], adapter_notion.REMOVALS.get(key, ())
        kept = keep_removed(root, notion, ids, key) if gone else ""
        notion.call("PATCH", f"/data_sources/{ids['databases'][key]['data_source']}",
                    {"properties": {**{name: adapter_notion.DATABASES[key][1][name] for name in names},
                                    **{name: None for name in gone}}})
        ids.setdefault("made_with", {})[key] = adapter_notion.MIGRATION  # each as it completes
        adapter_notion.save_ids(root, ids)
        print(f"The {adapter_notion.DATABASES[key][0]} table has its new columns: {', '.join(names)}"
              + (f"; the columns {', '.join(gone)} are removed, their text now in each row's page ({kept})" if gone
                 else "") + "; the next read fills them in.")
    ids["migrated"] = [*ids.get("migrated", []), adapter_notion.MIGRATION]
    adapter_notion.save_ids(root, ids)


def make_desk(root: Path, notion) -> int:
    me = notion.call("GET", "/users/me")
    if me.get("type") != "bot":
        print("refused: this token acts as a person (a personal access token?); the desk needs the Board's internal "
              "connection, whose own edits show as its bot")
        return 2
    ids = adapter_notion.load_ids(root) or {}
    ids.update({"bot": me["id"], "pages": ids.get("pages", {}), "databases": ids.get("databases", {}),
                "rows": ids.get("rows", {})})
    if not ids.get("root"):
        found = [page for page in notion.listed("POST", "/search", {"query": adapter_notion.ROOT_TITLE,
                                                                     "filter": {"property": "object", "value": "page"}})
                 if title_of(page).strip().casefold() == adapter_notion.ROOT_TITLE.casefold()
                 and not page.get("in_trash")]
        if len(found) != 1:
            print(f"refused: {len(found)} pages titled \"{adapter_notion.ROOT_TITLE}\" are shared with the connection, "
                  "and it needs exactly one (docs/board-desk.md, \"Set it up\")")
            return 2
        ids["root"] = found[0]["id"]
    parent = {"type": "page_id", "page_id": ids["root"]}
    for key, (title, _) in adapter_notion.PAGES.items():
        if key not in ids["pages"]:
            made = notion.call("POST", "/pages", {"parent": parent,
                                                  "properties": {"title": {"title": adapter_notion.rich(title)}}})
            ids["pages"][key] = made["id"]
            adapter_notion.save_ids(root, ids)
    for key, (title, properties) in adapter_notion.DATABASES.items():
        if key not in ids["databases"]:
            made = notion.call("POST", "/databases", {"parent": parent, "title": adapter_notion.rich(title),
                                                      "initial_data_source": {"properties": properties}})
            ids["databases"][key] = {"database": made["id"], "data_source": made["data_sources"][0]["id"]}
            if key in adapter_notion.MIGRATIONS:  # made with the columns, in the same save: never migrated, even by a
                ids.setdefault("made_with", {})[key] = adapter_notion.MIGRATION  # setup cut short
            adapter_notion.save_ids(root, ids)
    if not adapter_notion.migrated(ids):  # columns a database made before lacks
        migrate(root, notion, ids)
    sort_views(root, notion, ids)  # after the migration: the sorts name its columns
    for key in [key for key in ids["pages"] if key not in adapter_notion.PAGES]:
        where = "moved to Notion's trash, where it can be restored"
        try:
            notion.call("PATCH", f"/pages/{ids['pages'][key]}", {"in_trash": True})
        except adapter_notion.NotionError as error:
            if error.status != 404:
                raise
            where = "already gone from Notion"
        print(f"The page \"{key}\" is no longer pushed: {where}.")
        del ids["pages"][key]
        adapter_notion.save_ids(root, ids)
    if proven_live(root) and "notes" in ids["databases"] and "notes" not in ids.get("retired", []):
        retire_notes(root, notion, ids)
    adapter_notion.save_ids(root, ids)
    adapter_notion.save_fixed_ids(root, ids)
    print(f"Notion is set up: {len(ids['pages'])} pages and {len(ids['databases'])} databases under "
          f"\"{adapter_notion.ROOT_TITLE}\"; ids in {adapter_notion.IDS}, and the fixed ones in "
          f"{adapter_notion.FIXED_IDS} for the CEO to commit (the hook's list in every checkout). The workspace's "
          "people (pick the Board's):")
    for identity, name in notion.people():
        print(f"  {identity}  {name}")
    try:  # read only: a state the reader can't read is the reader's to set aside
        recorded = json.loads((root / READER).read_text()).get("board")
    except (OSError, ValueError, AttributeError):
        recorded = None
    if recorded:
        print("The Board's id is recorded already (attribution ran): nothing more to do.")
    else:
        print("Next: python3 scripts/board_desk.py attribution --board <the Board's id>")
    return 0


TEST_QUESTION = ("Attribution test. 1. On your phone, open this row and type phone in Your words. 2. Then, in your own "
                 "Claude app with Notion connected, ask Claude to change Your words on this row to connector.")


def attribution(root: Path, board: str, notion=None, sleep=time.sleep, clock=utc_now) -> int:
    """`attribution --board <id>`: a test row the script writes; the Board types
    "phone" in it on the phone, then has its own Claude app's Notion connector write "connector". Each edit's last
    editor, as Notion gives it, goes to the output and attribution.jsonl (ids, never names or emails); the words are
    compared without case, spaces or punctuation ("Phone." is phone). Only the edit "phone" shown with the picked id
    records the Board's id in reader.json; until then no answer counts. No connector edit by the end is said and
    logged too. The row goes to the trash at the end. notion.json is written under the
    reader's lock, as the read job writes it."""
    if worktree(root, "attribution"):
        return 2
    notion = notion or adapter_notion.Notion()
    ids = adapter_notion.load_ids(root)
    if not ids:
        print("refused: Notion isn't set up (python3 scripts/board_desk.py setup)")
        return 2
    if board == ids["bot"] or board not in {identity for identity, _ in notion.people()}:
        print("refused: that id isn't one of the workspace's people")
        return 2
    source = ids["databases"]["asks"]["data_source"]
    properties = {"Id": {"title": adapter_notion.rich(adapter_notion.TEST_ROW)},
                  "Question": {"rich_text": adapter_notion.rich(TEST_QUESTION)}}
    with locked(root, READER_LOCK):  # a read in between would see the row with no ask id
        row = notion.call("POST", "/pages", {"parent": {"type": "data_source_id", "data_source_id": source},
                                             "properties": properties})["id"]
        ids = adapter_notion.load_ids(root)
        ids["rows"][row] = adapter_notion.TEST_ROW
        adapter_notion.save_ids(root, ids)
    log = root / ATTRIBUTION_LOG

    def note(step: str, page: dict) -> str:
        editor = str((page.get("last_edited_by") or {}).get("id") or "")
        who = "the id you picked" if editor == board else "the connection" if editor == ids["bot"] else "another id"
        with open(log, "a") as file:
            file.write(json.dumps({"at": clock().isoformat(), "step": step, "editor": who, "editor_id": editor,
                                   "edited_at": page.get("last_edited_time")}) + "\n")
        print(f"{local(clock()):%H:%M} {ZONE_NAME}: {step}: Notion shows the last editor as {who} ({editor or 'none'})",
              flush=True)
        return editor

    recorded = connector = False
    try:
        note("the script's own write", notion.call("GET", f"/pages/{row}"))
        print("Waiting for the Board's edits (up to 15 minutes).", flush=True)
        last, deadline = None, clock() + timedelta(minutes=ATTRIBUTION_MINUTES)
        while clock() < deadline and not (recorded and connector):
            sleep(ATTRIBUTION_EVERY)
            page = notion.call("GET", f"/pages/{row}")
            words = re.sub(r"\W+", "", adapter_notion.text_of((page.get("properties") or {}).get("Your words"))
                           .casefold())
            seen = (words, (page.get("last_edited_by") or {}).get("id"), page.get("last_edited_time"))
            if not words or seen == last:
                continue
            last = seen
            step = words if words in ("phone", "connector") else "other text"
            editor = note(f"the edit \"{step}\"" if step != "other text" else step, page)
            connector = connector or step == "connector"
            if step == "phone" and editor == board and not recorded:
                with locked(root, READER_LOCK):
                    state = load_state(root, READER) or {}
                    state["board"] = board
                    save_state(root, state, READER)
                recorded = True
                print("Recorded: Notion shows your edit as yours, so your answers count from now.", flush=True)
    finally:
        try:
            notion.call("PATCH", f"/pages/{row}", {"in_trash": True})
        except adapter_notion.NotionError as error:
            print(f"The test row is still there ({error}): delete it in Notion.")
        with locked(root, READER_LOCK):
            ids = adapter_notion.load_ids(root)
            ids["rows"].pop(row, None)
            adapter_notion.save_ids(root, ids)
    if not connector:
        with open(log, "a") as file:
            file.write(json.dumps({"at": clock().isoformat(), "step": "no connector edit seen"}) + "\n")
        print("No connector edit seen: the Claude app's step wasn't logged. Tell the CEO.")
    if not recorded:
        print("Not recorded: no edit \"phone\" shown with the id you picked, so no answer counts yet. Tell the CEO.")
        return 1
    return 0


# ---- launchd --------------------------------------------------------------------------------------------------------

def job(read: bool = False) -> dict:
    return {
        "Label": READ_LABEL if read else LABEL,
        "ProgramArguments": [PYTHON, str(Path(__file__).resolve()), "read" if read else "run"],
        **({"StartInterval": READ_EVERY} if read else {"StartCalendarInterval": {"Minute": 0}}),
        "EnvironmentVariables": dict(JOB_ENV),
        "StandardOutPath": str(LOG),
        "StandardErrorPath": str(LOG),
    }


def macos(command: str) -> bool:
    """Whether this machine has launchd, said when it hasn't."""
    if sys.platform == "darwin":
        return True
    print(f"{command}: launchd is macOS only; elsewhere cron can start `run` hourly, and the Notion side, whose token is "
          "in the macOS Keychain, doesn't run (docs/board-desk.md)")
    return False


def install() -> int:
    if not macos("install"):
        return 2
    if capacity_scan.main_checkout(REPO) != REPO:
        print(f"refused: {REPO} is a worktree; install from the main checkout, whose pages the CEO commits")
        return 2
    PLIST.parent.mkdir(parents=True, exist_ok=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with locked(REPO):
        if load_state(REPO) is None:
            save_state(REPO, baseline(REPO, floor_hour(utc_now())))
    domain = f"gui/{os.getuid()}"
    for read, label, plist in ((False, LABEL, PLIST), (True, READ_LABEL, READ_PLIST)):
        if read and not adapter_notion.ready(adapter_notion.load_ids(REPO)):
            print(f"{READ_LABEL} not installed: Notion isn't set up, or its setup stopped part way (setup, then "
                  "install again)")
            break
        with open(plist, "wb") as file:
            plistlib.dump(job(read), file)
        subprocess.run(["launchctl", "bootout", f"{domain}/{label}"], stderr=subprocess.DEVNULL)
        subprocess.run(["launchctl", "bootstrap", domain, str(plist)], check=True)
        print(f"installed {label}: {f'every {READ_EVERY} s' if read else 'every hour at :00'}, from {REPO}, on "
              f"{JOB_ENV.get('CLAUDE_CONFIG_DIR', 'the default Claude account')}; log {LOG}")
    return 0


def uninstall() -> int:
    if not macos("uninstall"):
        return 2
    code = 0
    for label, plist in ((READ_LABEL, READ_PLIST), (LABEL, PLIST)):
        service = f"gui/{os.getuid()}/{label}"
        stopped = subprocess.run(["launchctl", "bootout", service], stderr=subprocess.DEVNULL)
        if stopped.returncode and subprocess.run(["launchctl", "print", service], stdout=subprocess.DEVNULL,
                                                 stderr=subprocess.DEVNULL).returncode == 0:  # still loaded
            print(f"bootout failed (exit {stopped.returncode}), {label} is still loaded; the plist stays, run uninstall "
                  "again")
            code = 1
            continue
        with contextlib.suppress(FileNotFoundError):
            plist.unlink()
        print(f"removed {label}; the pages and the state stay")
    return code


def seal(root: Path) -> int:
    """The Board's step once it has looked at an ANSWERS TAMPERED line: the
    answers pages and the reader's files as they are now become the seal, and the next read checks Notion again. The
    Bash guard lets no agent run it, the CEO included (scripts/hooks/board_desk_bash.py: only wait, install, uninstall
    and --help, and the CEO's setup and attribution)."""
    with locked(root, READER_LOCK):
        ended = answers_seal.reseal(root)
    for line in ended:
        print(f"sealed over: {line}")
    say(f"seal: the answers pages and the reader's files as they are now; {len(ended)} alarm lines ended")
    return 0


def off(command: str) -> int:
    """With no desk in company.json: one line, nothing read or written. A job's command ends well, as nothing is due; a
    command someone typed doesn't."""
    print(f"{command}: the Board desk is off (company.json has no \"integrations\".\"board_desk\"; docs/board-desk.md)")
    return 0 if command in ("run", "hour", "day", "read") else 2


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=["run", "hour", "day", "wait", "read", "setup", "attribution", "readback",
                                            "install", "uninstall", "seal"])
    parser.add_argument("ids", nargs="*", help="readback: the Q-ids, D-ids or ask ids whose rows it reads")
    parser.add_argument("--root", type=Path, default=REPO,
                        help="every command but install and uninstall: the checkout whose pages it writes or reads")
    parser.add_argument("--board", help="attribution: the Board's own id, from setup's list of people")
    args = parser.parse_args(argv)
    if args.command == "uninstall":
        return uninstall()
    if adapter_notion.FAULT is not None:
        raise adapter_notion.FAULT
    if SETTINGS is None and args.command != "seal":  # uninstall and seal work with the desk off too
        return off(args.command)
    if args.command == "install":
        return install()
    if args.command == "wait":
        return wait(args.root.resolve())
    if args.command in ("read", "setup", "attribution", "readback", "seal"):
        try:
            if args.command == "read":
                return read_notion(args.root.resolve(), utc_now())
            if args.command == "seal":
                return seal(args.root.resolve())
            if args.command == "readback":
                return readback(args.root.resolve(), args.ids)
            if args.command == "setup":
                return setup(args.root.resolve())
            if not args.board:
                parser.error("attribution needs --board <id>")
            return attribution(args.root.resolve(), args.board)
        except adapter_notion.NotionError as error:  # a status and a code, never a body or the token
            say(f"{args.command} failed: {error}")
            return 1
        except TimeoutError:
            say(f"{args.command}: the reader's lock is held; nothing written")
            return 1
    root, now, code = args.root.resolve(), utc_now(), 0
    try:
        with locked(root):
            for name, step in (("hour", hour), ("day", day)):
                if args.command in (name, "run"):
                    try:
                        code = max(code, step(root, now))
                    except Exception as error:  # noqa: BLE001 - logged by type only; the next hour tries again
                        say(f"{name} failed: {type(error).__name__}")
                        code = 1
    except TimeoutError:
        say("another run holds the lock; nothing written")
        return 1
    return code


if __name__ == "__main__":
    sys.exit(main())
