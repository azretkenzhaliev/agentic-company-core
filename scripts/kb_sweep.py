#!/usr/bin/env python3
"""Keep hot pages hot: move old log text, word for word, to its cold page.

With no flags it changes nothing: it prints what would move, what stays, and which pages agents opened in the last 14
days. --apply --owner ceo|cto moves that owner's text and records the sweep in knowledge/last-sweep.txt. It never
summarises, rewords or commits. What's due comes from kb_lint's "sweep due" lines: /report and the CTO's report act on them.

What moves, past its age (AGE_DAYS; --age-days for a page still near its limit):
- a `# ` section of workspaces/<product>/content/ceo-questions.md, to ceo-questions-archive.md, only on its owner's word:
  `CLOSED YYYY-MM-DD` as the first line under the heading. A status row saying DONE only names a candidate. A NEEDS-CEO-NOW
  or PAUSE line or a line dated after CLOSED keeps it, and it's named. Any code fence on the page holds the whole page: a
  `# ` in a fence can't be told from a heading, so nothing moves from that page and its first fence is named, once.
- status-log rows of a directive near or over its limit, or that already has an archive; a row with one of those two
  words stays and is counted, and so does the latest `NEXT:` row, the one capacity_scan.py reads, whatever its age.
  Rows go to the highest-numbered archive, -archive-<n>.md; with several, the header names each with the dates of its
  log's rows;
- rows of lessons-learned.md's "Recent lessons". A row there tells a past story, so those words don't hold it.
- the Board desk's pages (knowledge/company/board-desk/), each to
  <page>-archive-YYYY-MM.md by the month of what moves, one month a run, newest first: a day of progress.md once
  summaries.md (or its archive) holds that day's summary and a later day is on the page; a day of summaries.md past
  AGE_DAYS["summaries"]; an ask of asks.md answered or withdrawn longer ago than AGE_DAYS["closed"], by the date in its
  heading; a day of qa.md asked longer ago than AGE_DAYS["closed"], its questions whatever their status (never
  deleted, and still in the desk's Q&A, which board_desk.py fills from the page and its archives). qa.md and asks.md past their limit (FIT_PAGES) also move their oldest whole entries, questions and
  closed asks, whatever their age, until the page fits, below kb_lint's sweep band so the next entry doesn't put it
  over again; an open ask never moves. qa's
  archive keeps the CEO's order, oldest first: a question goes to the end of its day there, under that day's one
  heading. Headings inside a code fence are text, as board_desk.qa_entries reads them. scripts/board_desk.py runs this
  part itself after the 10:00 summary.
"Never moves an open order's line" is a rule for ceo-questions.md only: rows move by age, whatever order they name.

Owners: --apply touches only pages owned by --owner (front matter; ceo-questions.md is WORK_LOG_OWNER's) whose cold page
has the same owner. That's a stated rule, not a lock: nothing can check who runs it. Transcripts: only the paths of pages
opened are taken, on this machine; the output is paths and counts. Exits 1 if a page changed under an --apply: run it again.
Today is the UTC date, as the logs write it. --today moves only the date ages count from: last-sweep.txt and `updated:`
get the run's own date.
"""

import argparse
import fcntl
import json
import os
import re
import sys
import time
from collections import Counter, namedtuple
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from capacity_scan import NEXT  # noqa: E402
from kb_lint import (  # noqa: E402
    FIT_PAGES, ISO_DATE, KB, SWEEP_BAND, SWEEP_DAYS, SWEEP_OWNERS, SWEEP_STAMPS, SUMMARY_HEADING, WORK_LOG_OWNER, WORK_LOGS,
    fence_hold, is_cold, linked_pages, parse_front_matter, read_oversize_list, size_limit, utc_date,
)

AGE_DAYS = {"closed": 3, "status": 14, "lessons": 7, "summaries": 5}  # days past a text's date before it moves: defaults
HOT_OPENS = 10  # a cold page opened this often in the window is a candidate for hot
STAYS = ("NEEDS-CEO-NOW", "PAUSE")  # the CEO's watcher and running agents look for these in the hot page
STATUS = re.compile(r"^#{1,2} Status log\b")
STATUS_LOG = (STATUS, STATUS, False, STAYS, NEXT)  # hot heading, cold heading, newest first, words that hold a row, and
LESSONS_LOG = (re.compile(r"^## Recent lessons\b"), re.compile(r"^# Lessons learned, archive\b"), True, (), None)  # the scan's row
ROW = re.compile(r"^\| (\d{4}-\d{2}-\d{2}) \|")
POINTER = re.compile(r"^Rows before (\d{4}-\d{2}-\d{2})\b")
ARCHIVE = re.compile(r"-archive-(\d+)\.md$")
CLOSED_LINE = re.compile(r"^CLOSED (\d{4}-\d{2}-\d{2})\b")
ORDER = re.compile(r"/\d+(?:\.\d+)*")
PAGE = r"knowledge/[^\s\"'`|;()<>]+?\.md|workspaces/[^/\s]+/content/[^\s\"'`|;()<>]+?\.md"
READ_PATH = re.compile(rf"(?:^|[^\w.-])({PAGE})")
SHELL_READ = re.compile(rf"\b(?:sed -n|cat|head|tail)\b[^|;&>\n]*?[\s\"'=/]({PAGE})")  # a grep isn't an open: cold pages are for searching
Move = namedtuple("Move", "page cold owner before cold_before hot cold_text chunks what")  # before: as read, so --apply can see a change
DESK = ("company", "board-desk")
DESK_DAY = re.compile(r"^## (\d{4}-\d{2}-\d{2}), [A-Z][a-z]+day$")  # board_desk.py's DAY_HEADING
# _templates/ask.md's heading; its id may carry a part, "B-7 B+C" (board_desk.py's ASK_ID_TEXT)
DESK_ASK = re.compile(r"^### [AB]-\d+(?: [^·|\n]*[^·|\s])? · (?:answered|withdrawn) (\d{4}-\d{2}-\d{2})\b")
QA_DAY = re.compile(r"^## (\d{4}-\d{2}-\d{2})$")  # _templates/qa.md's day heading
DAY_END = re.compile(r"^#{1,2} ")
ENTRY_END = re.compile(r"^#{1,3} ")  # board_desk.py's: a question's entry runs to the next heading of level 1 to 3
CODE_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")  # adapter_notion.FENCE, so the sweep cuts entries where the push does
DESK_PAGES = {  # page: (what starts a section, what ends one, what moved sections are called)
    "progress": (DESK_DAY, DAY_END, "days"),
    "summaries": (DESK_DAY, DAY_END, "summaries"),
    "asks": (DESK_ASK, ENTRY_END, "closed asks"),
    "qa": (QA_DAY, DAY_END, "days of questions"),
}


def read(path: Path) -> str:
    """Lossless, whatever the bytes: text that moves must not change."""
    return path.read_bytes().decode("utf-8", "surrogateescape")


def sync(f) -> None:
    """To the disk itself: on macOS fsync stops at the drive's cache. Linux, or a disk that can't, gets fsync."""
    try:
        fcntl.fcntl(f, fcntl.F_FULLFSYNC)
    except (AttributeError, OSError):
        os.fsync(f)


def write(path: Path, text: str, before: "str | None") -> bool:
    """All or nothing, on disk before the replace. False, nothing changed, if the file no longer reads `before`.

    The temporary file comes first, the slow part, so the compare sits right before the replace. A line written in
    the moment between them is lost: no lock can bind Edit or a >>.
    """
    target = path.resolve()
    tmp = target.with_name(f".kb_sweep-{os.getpid()}")
    try:
        with open(tmp, "wb") as f:
            f.write(text.encode("utf-8", "surrogateescape"))
            f.flush()
            sync(f)
        if (read(path) if path.exists() else None) != before:
            return False
        os.replace(tmp, target)
        return True
    finally:
        tmp.unlink(missing_ok=True)


def owner_of(page: Path) -> str:
    parsed = parse_front_matter(read(page).split("\n"))
    return parsed[0].get("owner", "?") if parsed else WORK_LOG_OWNER if "workspaces" in page.parts else "?"


def touch_updated(text: str, today: date) -> str:
    lines = text.split("\n")
    parsed = parse_front_matter(lines)  # the front matter's own line only: nothing in the body changes
    if parsed and "updated" in parsed[1]:
        lines[parsed[1]["updated"] - 1] = f"updated: {today}"
    return "\n".join(lines)


def log_span(lines: list, heading: re.Pattern):
    """The heading and what's right under it, up to the next heading of any level."""
    start = next((i for i, line in enumerate(lines) if heading.match(line)), None)
    if start is None:
        return None
    return start, next((i for i in range(start + 1, len(lines)) if re.match(r"#{1,6} ", lines[i])), len(lines))


def new_cold_page(page: Path, lines: list, span: tuple, today: date) -> str:
    fields = (parse_front_matter(lines) or ({},))[0]
    title = str(fields.get("title", page.stem)).replace('"', "'")
    table_head = [line for line in lines[span[0]:span[1]] if line.startswith("|") and not ROW.match(line)][:2]
    return "\n".join(["---", f'title: "{title}: archive of its log"', f"owner: {fields.get('owner')}", "status: archived",
                      f"updated: {today}", f"related: [{page.name}]", "---", "", f"# {page.stem}: archive", "",
                      f"Moved word for word from [{page.name}]({page.name}) by scripts/kb_sweep.py. Search it; don't load it whole.",
                      "", lines[span[0]], "", *table_head, ""])


def archives_of(page: Path) -> list:
    """A directive's archives, <stem>-archive-<n>.md, lowest number first."""
    found = [(int(m.group(1)), p) for p in page.parent.glob(f"{page.stem}-archive-*.md")
             if (m := ARCHIVE.search(p.name)) and p.name == page.stem + m.group()]
    return [p for _, p in sorted(found)]


def log_dates(lines: list, heading: re.Pattern) -> list:
    """The dates of the rows under every heading the log's matches: an archive can hold its log in several sections."""
    dates, inside = [], False
    for line in lines:
        if re.match(r"#{1,6} ", line):
            inside = bool(heading.match(line))
        elif inside and (row := ROW.match(line)):
            dates.append(row.group(1))
    return dates


def pointer(since: str, archives: list, cold_lines: list, heading: re.Pattern) -> str:
    """The log's header: its one archive, or each of several with its rows' dates (the last one's from cold_lines)."""
    if len(archives) == 1:
        return f"Rows before {since} are in [the archive]({archives[0].name})."
    parts = []
    for archive in archives:
        dates = sorted(log_dates(cold_lines if archive == archives[-1] else read(archive).split("\n"), heading))
        parts.append(f"[archive {ARCHIVE.search(archive.name).group(1)}]({archive.name})"
                     + (f", rows of {dates[0]} to {dates[-1]}" if dates else ""))
    return f"Rows before {since} are in {len(archives)} archives: {'; '.join(parts)}."


def plan_rows(page: Path, archives: list, log: tuple, age: int, today: date, left: list):
    heading, cold_heading, newest_first, stays, scanned = log
    cold = archives[-1]
    before = read(page)
    lines = before.split("\n")
    span = log_span(lines, heading)
    cutoff = (today - timedelta(days=age)).isoformat()
    old = {i for i in range(*span) if (row := ROW.match(lines[i])) and row.group(1) < cutoff} if span else set()
    held = {i for i in old if any(word in lines[i] for word in stays)}
    latest = max((i for i, line in enumerate(lines) if scanned and scanned.match(line)), default=None)
    owner, cold_before = owner_of(page), read(cold) if cold.exists() else None
    if held:
        left.append((owner, page, f"{len(held)} old rows hold a {' or '.join(stays)}: they stay"))
    if latest in old:
        left.append((owner, page, f"the latest NEXT row ({ROW.match(lines[latest]).group(1)}) stays: capacity_scan.py reads it"))
        held.add(latest)
    old -= held
    if not old:
        return None
    ran = utc_date(time.time())  # what `updated:` says: the run's own date, never --today's
    cold_lines = (new_cold_page(page, lines, span, ran) if cold_before is None else cold_before).split("\n")
    cold_span = log_span(cold_lines, cold_heading)
    table = [i for i in range(*cold_span) if cold_lines[i].startswith("|")] if cold_span else []
    rules = [i for i in table if cold_lines[i].startswith("|---")]
    if not rules or (cold_before is not None and owner_of(cold) != owner):
        left.append((owner, page, f"{cold.name} has no table for this log, or another owner: move by hand"))
        return None
    rows = [lines[i] for i in sorted(old)]
    at = rules[0] + 1 if newest_first else table[-1] + 1
    cold_lines[at:at] = list((Counter(rows) - Counter(cold_lines)).elements())  # a rerun after a stop adds nothing twice
    kept = [line for i, line in enumerate(lines) if i not in old]
    for i, line in enumerate(kept):  # a header moves forward, never back; with several archives it names them all
        if line.startswith("Rows before ") and any(f"({archive.name})" in line for archive in archives):
            kept[i] = (max(line, pointer(cutoff, archives, cold_lines, cold_heading)) if len(archives) == 1 else
                       pointer(max([cutoff, *POINTER.findall(line)]), archives, cold_lines, cold_heading))
    if cold.name not in "\n".join(kept):  # a page that links its cold page already needs no pointer
        kept[span[0] + 1:span[0] + 1] = ["", pointer(cutoff, archives, cold_lines, cold_heading)]
    dates = sorted(ROW.match(row).group(1) for row in rows)
    return Move(page, cold, owner, before, cold_before, touch_updated("\n".join(kept), ran),
                touch_updated("\n".join(cold_lines), ran), rows, f"{len(rows)} rows, {dates[0]} to {dates[-1]}")


def why_it_stays(section: list, first: str, closed: str, cutoff: str):
    """Why a section its owner closed stays on the hot page, or None."""
    held = [word for word in STAYS if any(word in line for line in section)]
    newer = [found for line in section if line != first for found in ISO_DATE.findall(line) if found > closed]
    return (f"holds a {held[0]} line" if held else f"has a line dated {max(newer)}, after its CLOSED line" if newer
            else f"closed {closed}, within its age" if closed >= cutoff else None)


def plan_questions(page: Path, root: Path, age: int, today: date, left: list):
    before = read(page)
    held = fence_hold(before)
    if held:
        left.append((WORK_LOG_OWNER, page, held))
        return None
    lines = before.split("\n")
    cutoff = (today - timedelta(days=age)).isoformat()
    done_rows = [(p.stem, line) for p in sorted((root / "board" / "directives").glob("D-*.md"))
                 for line in read(p).split("\n") if line.startswith("|") and "REPORT" in line and "DONE" in line]
    starts = [i for i, line in enumerate(lines) if line.startswith("# ")]
    gone, chunks = set(), []
    for start, end in zip(starts, starts[1:] + [len(lines)]):
        section, heading = lines[start:end], lines[start][:60]
        first = next((line for line in section[1:] if line.strip()), "")
        mark = CLOSED_LINE.match(first)
        order = ORDER.search(heading)
        said = order and sorted({stem for stem, row in done_rows if re.search(rf"REPORT {re.escape(order.group())}\D.*DONE", row)})
        why = why_it_stays(section, first, mark.group(1), cutoff) if mark else said and (
            f"candidate: a row in {', '.join(said)} says DONE; if nothing here is open, add `CLOSED YYYY-MM-DD` under the heading")
        if why:
            left.append((WORK_LOG_OWNER, page, f"{heading}: {why}"))
        elif mark:
            gone.update(range(start, end))
            chunks.append("\n".join(section).rstrip("\n"))
    if not chunks:
        return None
    cold = page.with_name(f"{page.stem}-archive.md")
    cold_before = read(cold) if cold.exists() else None
    if cold_before is not None and owner_of(cold) != WORK_LOG_OWNER:
        left.append((WORK_LOG_OWNER, page, f"{cold.name} has another owner: move by hand"))
        return None
    cold_text = "# ceo-questions, archive: search it, don't load it\n" if cold_before is None else cold_before
    for chunk in chunks:
        if chunk not in cold_text:  # a rerun after a stop adds nothing twice
            cold_text = cold_text.rstrip("\n") + "\n\n" + chunk + "\n"
    kept = [line for i, line in enumerate(lines) if i not in gone]
    if cold.name not in "\n".join(kept):
        at = next((i for i, line in enumerate(kept) if line.startswith("# ")), len(kept))
        kept[at:at] = [f"Closed orders' lines are in [{cold.name}]({cold.name}): search it, don't load it.", ""]
    hot = "\n".join(kept)
    hot += "\n" if before.endswith("\n") and not hot.endswith("\n") else ""  # a line added with >> must start its own line
    rulings = sum(line.startswith("**CEO") for chunk in chunks for line in chunk.split("\n"))
    return Move(page, cold, WORK_LOG_OWNER, before, cold_before, hot, cold_text, chunks, f"{len(chunks)} closed sections, {rulings} **CEO lines")


def in_code(lines: list, starts: re.Pattern) -> set:
    """The lines inside a fenced code block, as board_desk.qa_entries reads them: a heading there is text. A fence opens
    only from the first line `starts` matches on: one in the page's intro is text."""
    inside, fence, began = set(), None, False
    for i, line in enumerate(lines):
        if fence is not None:
            inside.add(i)
            if line.strip().startswith(fence) and not line.strip().strip(fence[0]):
                fence = None
            continue
        began = began or bool(starts.match(line))
        if began and (opened := CODE_FENCE.match(line)):
            fence = opened.group(1)
    return inside


def desk_sections(lines: list, starts: re.Pattern, ends: re.Pattern) -> list:
    """[(first line, end, its date)]: each section from a line `starts` matches up to the next line `ends` matches,
    neither inside a code fence."""
    code, found = in_code(lines, starts), []
    for i, line in enumerate(lines):
        if i not in code and (head := starts.match(line)):
            end = next((j for j in range(i + 1, len(lines)) if j not in code and ends.match(lines[j])), len(lines))
            found.append((i, end, head.group(1)))
    return found


def qa_units(lines: list, days: list) -> list:
    """qa.md's questions, [(first line, end, day)]: each `### ` entry of a day up to the next heading of level 1 to 3
    outside a code fence, as board_desk.qa_entries reads it. A day with no entry is one unit, whole."""
    code, units = in_code(lines, QA_DAY), []
    for start, end, day in days:
        heads = [i for i in range(start + 1, end) if i not in code and ENTRY_END.match(lines[i])]
        units += [(i, j, day) for i, j in zip(heads, heads[1:] + [end])] or [(start, end, day)]
    return units


def nbytes(text: str) -> int:
    return len(text.encode("utf-8", "surrogateescape"))


def summarised_days(folder: Path) -> set:
    return {found.group(1) for page in [folder / "summaries.md", *sorted(folder.glob("summaries-archive-*.md"))]
            if page.exists() for line in read(page).split("\n") if (found := DESK_DAY.match(line))}


def desk_archive(page: Path, lines: list, owner: str, month: str, ran: date, order: str = "newest first") -> str:
    title = str((parse_front_matter(lines) or ({},))[0].get("title", page.stem)).replace('"', "'")
    return "\n".join(["---", f'title: "{title}: archive, {month}"', f"owner: {owner}", "status: archived", f"updated: {ran}",
                      f"related: [{page.name}]", "---", "", f"# {title}: archive, {month}", "",
                      f"Moved word for word from [{page.name}]({page.name}) by scripts/kb_sweep.py, {order}. Search "
                      "it; don't load it whole.", ""])


def desk_hot(page: Path, lines: list, days: list, units: list, chosen: list, called: str, ran: date) -> tuple:
    """(the page without the chosen units, the lines gone): a day whose every unit goes takes its heading with it, and
    the page links the month's archive above its first `## `."""
    gone = {j for i, end, _ in chosen for j in range(i, end)}
    for start, end, _ in days:
        if {unit for unit in units if start <= unit[0] < end} <= set(chosen):
            gone.update(range(start, end))
    kept = [line for j, line in enumerate(lines) if j not in gone]
    month = min(when for *_, when in chosen)[:7]
    cold = page.with_name(f"{page.stem}-archive-{month}.md")
    if cold.name not in "\n".join(kept):
        at = next((j for j, line in enumerate(kept) if line.startswith("## ")), len(kept))
        kept[at:at] = [f"{called.capitalize()} of {month}, moved word for word: [{cold.name}]({cold.name}). Search it; "
                       "don't load it whole.", ""]
    return touch_updated("\n".join(kept), ran), gone


def file_questions(cold_text: str, lines: list, days: list, chosen: list, gone: set) -> tuple:
    """(qa's archive with the chosen questions in, the texts that must be there). Oldest first, as the CEO keeps it: a
    day the page loses whole goes in as it was, before the first later day; questions of a day already there go to the
    end of that day, under its one heading."""
    must = []
    for start, end, day in sorted(days, key=lambda found: (found[2], found[0])):
        mine = [unit for unit in chosen if start <= unit[0] < end]
        if not mine:
            continue
        cold_lines = cold_text.split("\n")
        filed = desk_sections(cold_lines, QA_DAY, DAY_END)
        there = [end_there for _, end_there, when in filed if when == day]
        if start in gone and not there:  # the whole day, as it was
            new, at = ["\n".join(lines[start:end]).rstrip("\n")], None
        else:
            head = "\n".join(lines[start + 1:end if mine[0][0] == start else mine[0][0]]).strip("\n") if start in gone else ""
            pieces = [head] * bool(head) + ["\n".join(lines[i:j]).rstrip("\n") for i, j, _ in mine if i != start]
            must += pieces
            new = [piece for piece in pieces if piece not in cold_text]  # a rerun after a stop adds nothing twice
            if not new:
                continue
            if not there:  # some questions of a day the archive hasn't got yet: under its heading, as on the page
                new = [lines[start], *new]
            at = there[-1] if there else None
        if at is None:  # a new day, before the first later one
            must.append(new[0])
            at = next((i for i, _, when in filed if when > day), len(cold_lines))
        cold_text = ("\n".join(cold_lines[:at]).rstrip("\n") + "\n\n" + "\n\n".join(new)
                     + ("\n\n" + "\n".join(cold_lines[at:]) if at < len(cold_lines) else "\n"))
    return cold_text, must


def plan_desk_page(page: Path, kind: str, today: date, age_days, left: list):
    """One page's Move: its due sections of the oldest month among them, word for word to that month's archive. A
    FIT_PAGES page past its limit also moves its oldest whole entries of that month, at any age, until it fits, below
    the sweep band."""
    starts, ends, called = DESK_PAGES[kind]
    before = read(page)
    lines = before.split("\n")
    found = desk_sections(lines, starts, ends)
    units = qa_units(lines, found) if kind == "qa" else found
    if kind == "progress":  # the latest day stays: an hour can still land on it
        done, newest = summarised_days(page.parent), max((when for *_, when in found), default="")
        due = [(i, end, when) for i, end, when in found if when in done and when < newest]
    else:
        cutoff = (today - timedelta(days=age_days or AGE_DAYS["summaries" if kind == "summaries" else "closed"])).isoformat()
        due = [unit for unit in units if unit[2] < cutoff]
    if due:
        month = min(when for *_, when in due)[:7]
        due = [unit for unit in due if unit[2].startswith(month)]
    owner, ran = owner_of(page), utc_date(time.time())  # `updated:` says the run's own date
    in_kb, fitted = "/".join([*DESK, page.name]), 0
    limit = size_limit(in_kb)[1] * KB
    if in_kb in FIT_PAGES and nbytes(before) > limit:  # oldest first, one month a run, until the page is out of
        rest = sorted(set(units) - set(due), key=lambda unit: (unit[2], unit[0]))  # kb_lint's sweep band, not due again
        while rest and (not due or rest[0][2][:7] == due[0][2][:7]) and (
                not due or nbytes(desk_hot(page, lines, found, units, due, called, ran)[0]) >= SWEEP_BAND * limit):
            due.append(rest.pop(0))
            fitted += 1
        if not due or nbytes(desk_hot(page, lines, found, units, due, called, ran)[0]) > limit:
            left.append((owner, page, f"over its {limit // KB} KB limit after what moves: " +
                         ("the next run moves the next month's" if rest else
                          "nothing else moves (an open ask stays)" if kind == "asks" else "nothing else moves")))
    if not due:
        return None
    due.sort()
    month = min(when for *_, when in due)[:7]
    cold = page.with_name(f"{page.stem}-archive-{month}.md")
    cold_before = read(cold) if cold.exists() else None
    if cold_before is not None and owner_of(cold) != owner:
        left.append((owner, page, f"{cold.name} has another owner: move by hand"))
        return None
    hot, gone = desk_hot(page, lines, found, units, due, called, ran)
    if kind == "qa":
        cold_text = desk_archive(page, lines, owner, month, ran, "oldest first") if cold_before is None else cold_before
        cold_text, chunks = file_questions(cold_text, lines, found, due, gone)
    else:
        chunks = ["\n".join(lines[i:end]).rstrip("\n") for i, end, _ in due]
        cold_text = desk_archive(page, lines, owner, month, ran) if cold_before is None else cold_before
        new = [chunk for chunk in chunks if chunk not in cold_text]  # a rerun after a stop adds nothing twice
        if new:
            cold_lines = cold_text.split("\n")
            at = next((i for i, line in enumerate(cold_lines) if starts.match(line)), None)
            cold_text = (cold_text.rstrip("\n") + "\n\n" + "\n\n".join(new) + "\n" if at is None else
                         "\n".join(cold_lines[:at]).rstrip("\n") + "\n\n" + "\n\n".join(new) + "\n\n" + "\n".join(cold_lines[at:]))
    dates = sorted(when for *_, when in due)
    noun = f"{len(due)} {called}"
    if kind == "qa":  # a day with no entry moves whole and counts as a day
        empty = sum(bool(starts.match(lines[i])) for i, *_ in due)
        noun = " and ".join(f"{n} {word}{'s' * (n != 1)}" for n, word in ((len(due) - empty, "question"),
                                                                           (empty, "empty day")) if n)
    what = f"{noun}, {dates[0]} to {dates[-1]}"
    if fitted:
        what += f"; {fitted} of them younger: over its {limit // KB} KB limit, it goes under {SWEEP_BAND * limit / KB:.1f} KB"
    return Move(page, cold, owner, before, cold_before, hot, touch_updated(cold_text, ran), chunks, what)


def plan_desk(root: Path, today: date, age_days=None, left=None) -> list:
    """The Board desk's Moves, at most one a page. `today` is the date ages count from."""
    folder, left = root.joinpath(*DESK), [] if left is None else left
    moves = [plan_desk_page(folder / f"{kind}.md", kind, today, age_days, left) for kind in DESK_PAGES
             if (folder / f"{kind}.md").exists()]
    return [move for move in moves if move]


def plan(root: Path, today: date, age_days=None) -> tuple:
    """(moves, what stays and why). Reads only."""
    moves, left = [], []
    oversize = read_oversize_list(root)
    for page in sorted((root / "board" / "directives").glob("D-*.md")):
        archives, in_kb = archives_of(page), page.relative_to(root).as_posix()
        if not is_cold(page) and (archives or in_kb in oversize or page.stat().st_size >= SWEEP_BAND * size_limit(in_kb)[1] * KB):
            cold = archives or [page.with_name(f"{page.stem}-archive-1.md")]
            moves.append(plan_rows(page, cold, STATUS_LOG, age_days or AGE_DAYS["status"], today, left))
    lessons = root / "engineering" / "standards" / "lessons-learned.md"
    if lessons.exists():
        moves.append(plan_rows(lessons, [lessons.with_name("lessons-learned-archive.md")], LESSONS_LOG, age_days or AGE_DAYS["lessons"], today, left))
    for page in sorted(root.parent.glob("workspaces/*/content/ceo-questions.md")):
        moves.append(plan_questions(page, root, age_days or AGE_DAYS["closed"], today, left))
    moves += plan_desk(root, today, age_days, left)
    return [move for move in moves if move], left


def apply_move(move: Move) -> bool:
    """Cold page first, so a stop can leave text in both places but never in neither. False if a page changed."""
    if not write(move.cold, move.cold_text, move.cold_before):
        return False
    if not all(chunk in read(move.cold) for chunk in move.chunks):
        raise RuntimeError(f"{move.cold}: moved text isn't on the cold page; {move.page} left as it was")
    return write(move.page, move.hot, move.before)


def line_opens(raw: bytes, since: date) -> list:
    """The paths one transcript line opened: Read calls and shell reads. A line of any other shape gives none."""
    try:
        entry = json.loads(raw)
        calls = [b for b in entry["message"]["content"] if b["type"] == "tool_use" and entry["timestamp"][:10] >= since.isoformat()]
        found = [path for b in calls for path in (READ_PATH.findall(b["input"]["file_path"]) if b["name"] == "Read" else
                                                  SHELL_READ.findall(b["input"]["command"]) if b["name"] == "Bash" else [])]
    except (ValueError, KeyError, TypeError, AttributeError):
        return []
    return [path for path in found if ".." not in path]


def page_opens(folders: list, since: date) -> tuple:
    """(how often each path was opened, transcripts read). Only tool calls' paths are read out, never text."""
    opens, count = Counter(), 0
    start = datetime(since.year, since.month, since.day, tzinfo=timezone.utc).timestamp()
    for file in (f for folder in folders for f in Path(folder).rglob("*.jsonl")):
        try:
            if file.stat().st_mtime >= start:
                count += 1
                with open(file, "rb") as lines:
                    for raw in lines:
                        opens.update(line_opens(raw, since) if b'"tool_use"' in raw else [])
        except OSError:
            continue  # a session log can go while we walk
    return opens, count


def transcript_folders(base: Path) -> list:
    """This repo's sessions: its own folder and its worktrees'. Subagents' logs sit inside them."""
    config = os.environ.get("CLAUDE_CONFIG_DIR")
    projects = (Path(config).expanduser() if config else Path.home() / ".claude") / "projects"
    return sorted(projects.glob(re.sub(r"[^A-Za-z0-9]", "-", str(base).split("/.claude/worktrees/")[0]) + "*"))


def hot_pages(root: Path) -> list:
    """Pages already split: they link a cold page or carry a summary of one, and the work logs. Paths from the repo."""
    hot = [p for name in WORK_LOGS for p in root.parent.glob(f"workspaces/*/content/{name}")]
    for page in sorted(root.rglob("*.md")):
        if "_templates" not in page.parts and not is_cold(page):
            text = read(page)
            if any(map(SUMMARY_HEADING.match, text.split("\n"))) or any(map(is_cold, linked_pages(page, root.parent, text))):
                hot.append(page)
    return [page.relative_to(root.parent).as_posix() for page in hot]


def use_report(root: Path, today: date, transcripts: list) -> list:
    since, base = today - timedelta(days=SWEEP_DAYS), root.parent
    opens, count = page_opens(transcripts or transcript_folders(base), since)
    if not count:
        return ["Use: no transcripts found, so no candidates; nothing is inferred from that."]
    seen = {path: n for path, n in opens.items() if (base / path).is_file()}
    top = sorted(seen.items(), key=lambda item: (-item[1], item[0]))
    return ([f"Use, {since} to {today}: {sum(seen.values())} opens of {len(seen)} pages, from {count} transcripts (paths and counts only)."]
            + [f"  {n:5d}  {path}" for path, n in top[:15]]
            + [f"  candidate for hot: {path}: {n} opens (owner: {owner_of(base / path)})" for path, n in top if n >= HOT_OPENS and is_cold(base / path)]
            + [f"  candidate for cold: {path}: no opens (owner: {owner_of(base / path)})" for path in hot_pages(root) if path not in seen])


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Move old log text to its cold page; show what's due.")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1] / "knowledge")
    parser.add_argument("--today", type=date.fromisoformat, default=utc_date(time.time()),
                        help="the date ages count from (default: today in UTC); the sweep is recorded with the real date")
    parser.add_argument("--age-days", type=int, help="this age for every log, for a page still near its limit")
    parser.add_argument("--apply", action="store_true", help="move the text; without it nothing changes")
    parser.add_argument("--owner", choices=SWEEP_OWNERS, help="with --apply: the role running it; only its pages move")
    parser.add_argument("--transcripts", type=Path, action="append", help="folders of session logs (default: this repo's)")
    args = parser.parse_args(argv)
    if (args.apply and not args.owner) or (args.age_days is not None and args.age_days < 1):
        parser.error("--apply needs --owner: only a page's owner moves its text; --age-days needs at least 1")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="backslashreplace")  # a heading can hold any bytes; a print mustn't stop a sweep
    root = args.root.resolve()
    moves, left = plan(root, args.today, args.age_days)
    show = lambda page: page.relative_to(root.parent).as_posix()  # noqa: E731
    size = lambda text: len(text.encode("utf-8", "surrogateescape")) / KB  # noqa: E731
    if args.apply:
        stopped = False
        for move in moves:
            if move.owner != args.owner:
                print(f"Not yours, {move.owner}: {show(move.page)}: {move.what}")
            elif apply_move(move):
                print(f"Moved, {move.owner}: {show(move.page)} -> {move.cold.name}: {move.what}")
            else:
                stopped = True
                print(f"Stopped, {move.owner}: {show(move.page)} or its cold page changed while running. Run again.")
        if stopped:
            return 1
        stamps, ran = root / SWEEP_STAMPS, utc_date(time.time())  # the run's own date, never --today's
        before = read(stamps) if stamps.exists() else None
        kept = [line for line in (before or "").splitlines() if line.split(" ")[0] != args.owner]
        if not write(stamps, "\n".join([*kept, f"{args.owner} {ran}", ""]), before):
            print(f"Stopped, {args.owner}: {root.name}/{SWEEP_STAMPS} changed while running. Run again.")
            return 1
        print(f"Recorded the sweep: {args.owner} {ran} in {root.name}/{SWEEP_STAMPS}. Nothing is committed.")
        return 0
    for move in moves:
        print(f"Would move, {move.owner}: {show(move.page)} -> {move.cold.name}: {move.what} ({size(move.before):.1f} KB -> {size(move.hot):.1f} KB)")
    for owner, page, why in left:
        print(f"Stays, {owner}: {show(page)}: {why}")
    if not moves:
        print("Nothing to move at these ages. A page still near its limit: --age-days N, or slim it by hand.")
    print("\n".join(use_report(root, args.today, args.transcripts or [])))
    print("Dry run: nothing changed. An owner moves its pages with --apply --owner <role>.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
