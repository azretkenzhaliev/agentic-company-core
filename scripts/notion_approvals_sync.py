#!/usr/bin/env python3
"""PostToolUse hook: copy the Board's decisions from the Notion calendar into the KB.

Runs after every Notion data-source query (`.claude/settings.json`). It does nothing until company.json names the
calendar and the brands ("integrations"."marketing": "notion"."calendar" and "brands"). When the query
is a complete rows-mode query of the "Marketing calendar" (knowledge/marketing/notion.md):
no filter, or a filter on Week and Brand only, with nothing left unreturned. Then each
item's Board fields are written into knowledge/marketing/<brand>/approvals/<week>.md
(owner: board), one row per Notion item, keyed by the item's Notion URL.

Why this is the Board's record and not an agent's: the rows come from the Notion
connector's own response to the query, not from an agent's retelling. Only the
Board sets Approval, AI label and Board comment in Notion
(scripts/hooks/guard_marketing_tools.py blocks everyone else), and no agent
writes approvals/ pages (scripts/hooks/guard_kb_write.py) or runs this script
(scripts/hooks/marketing_bash.py). It uses the Notion connection the Board's Claude
account already has: no token of its own.

A decision is tied to what was decided on. Every sync records the KB page's SHA-256 of
every item not Approved (the cmo syncs when the packet goes to the Board). When Approved
first appears, the row keeps that page and hash, and notes if the page changed since the
last sync before the decision, or if there was no earlier hash to compare. Publishing
needs an Approved row with no note (tools/marketing/publish/post.py). If agents later point the item at another page,
edit the page, or move the item to another week or brand in Notion, the Note column
says so and the recorded page and hash stay. An item stays on the approvals page
where it first appeared, whatever week Notion files it under later. A filtered query
(say, on Approval) is ignored, so a stale decision can't be kept by never querying
it. Rows are never removed; an item missing from a complete query that covers its
page is noted. The hook never blocks; it tells the agent what it wrote.

AI label is the Board's choice for each post (SA-005): `on` when the
Board ticked it in Notion, else `off`, refreshed at every sync, decided or not. post.py
sends it as Instagram's AI flag.
"""

import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from company_config import integration  # noqa: E402

MARKETING = ROOT / "knowledge" / "marketing"
WEEK = re.compile(r"\d{4}-W(0[1-9]|[1-4]\d|5[0-3])")
SCOPE_FILTERS = {("Week", "string_is"), ("Brand", "enum_is")}
COLUMNS = ("item", "kb_page", "kb_sha256", "approval", "ai_label", "board_comment", "notion", "note")
HEADER = "| Item | KB page | KB page SHA-256 | Approval | AI label | Board comment | Notion | Note |"
LABEL_ON, LABEL_OFF = "on", "off"
CHECKED = "__YES__"  # how the Notion connector returns a ticked checkbox
PENDING = "pending"
APPROVED = "Approved"
STICKY_NOTES = ("first synced after the decision", "no earlier hash to compare", "the page changed after the last sync",
                "the KB page changed after the last sync")  # facts about the decision; kept while it stands


def brand_folders(root: Path) -> dict:
    """Notion's Brand option: its folder under knowledge/marketing/, whose last part is the option's own name (the Note
    column compares them). company.json's "brands" are the folders; two with one last part are refused, since a decision
    could land under the wrong one."""
    brands = list((integration("marketing", root) or {}).get("brands") or {})
    folders = {brand.rsplit("/", 1)[-1]: brand for brand in brands}
    if len(folders) != len(brands):
        raise ValueError("two brands in company.json share a last name, so Notion's Brand can't tell them apart: rename one")
    return folders


def calendar(root: Path) -> str:
    """The Marketing calendar's data source, "collection://<id>", or "" when company.json doesn't name it."""
    identity = ((integration("marketing", root) or {}).get("notion") or {}).get("calendar") or ""
    return "collection://" + identity.removeprefix("collection://") if identity else ""


def calendar_query(event: dict, root: Path = ROOT):
    """(rows, scope) for a rows-mode query of the calendar, or None for any other call. scope is None when the
    query isn't complete, else (weeks, brands): the sets its filter names, None for "all"."""
    data = (event.get("tool_input") or {}).get("data") or {}
    if not str(event.get("tool_name", "")).endswith("notion-query-data-sources"):
        return None
    source = calendar(root)
    if not source or data.get("mode") != "rows" or data.get("data_source_url") != source:
        return None
    response = event.get("tool_response")
    if isinstance(response, dict):
        response = response.get("content", response)
    if isinstance(response, list):
        response = "".join(part.get("text", "") for part in response if isinstance(part, dict))
    result = json.loads(response)
    rows = result.get("results")
    if not isinstance(rows, list) or not all(isinstance(r, dict) for r in rows):
        raise ValueError("results isn't a list of rows")
    return rows, (scope(data.get("filter"), brand_folders(root)) if result.get("has_more") is False else None)


def scope(query_filter, folders: dict):
    """(weeks, brands) for no filter or an AND of Week/Brand equality filters only (the query returns whole
    brand-weeks), None for any other filter."""
    if query_filter is None:
        return None, None
    if query_filter.get("type") != "group" or query_filter.get("operator") != "and":
        return None
    named = {"Week": set(), "Brand": set()}
    for f in query_filter.get("filters") or []:
        if f.get("type") != "property" or (f.get("property"), f.get("operator")) not in SCOPE_FILTERS:
            return None
        named[f["property"]].add(_text((f.get("value") or {}).get("value")))
    return named["Week"] or None, {folders.get(b, b) for b in named["Brand"]} or None


def _text(value) -> str:
    return str(value or "").strip()


def page_sha256(kb_page: str, root: Path) -> str:
    """The SHA-256 of a KB page under knowledge/marketing/, or a reason it has none."""
    if not kb_page:
        return ""
    path = (root / kb_page).resolve()
    if not kb_page.endswith(".md") or not path.is_relative_to((root / "knowledge" / "marketing").resolve()):
        return "not a marketing KB page"
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else "page missing"


def _cell(value) -> str:
    return str(value).replace("|", "\\|").replace("\n", "<br>") or "–"


def _value(cell: str) -> str:
    text = cell.strip().replace("<br>", "\n").replace("\\|", "|")
    return "" if text == "–" else text


def read_rows(page: Path) -> list:
    """The rows of an existing approvals page, in order."""
    if not page.exists():
        return []
    rows, columns = [], None
    for line in page.read_text(encoding="utf-8").splitlines():
        if line == HEADER:
            columns = COLUMNS
        elif columns and line.startswith("| ") and not line.startswith("|---"):
            cells = re.split(r"(?<!\\)\|", line)[1:-1]
            rows.append({column: _value(cell) for column, cell in zip(columns, cells)})
    return rows


def render(brand: str, week: str, rows: list, synced_at: str) -> str:
    """The approvals page for one brand-week."""
    name = brand.rsplit("/", 1)[-1]
    lines = [
        "---",
        f'title: "Board approvals: {name}, {week}"',
        "owner: board",
        "status: active",
        f"updated: {synced_at[:10]}",
        "related: []",
        "---",
        "",
        f"# Board approvals: {name}, {week}",
        "",
        "Written by `scripts/notion_approvals_sync.py` from the Notion calendar's own query results, where only the "
        f"Board sets these fields. Last change {synced_at}. No agent edits this page; a rows-mode query of the "
        "calendar by Week refreshes it. KB page and SHA-256 are what the decision was made on; Note says what "
        "changed since.",
        "",
        HEADER,
        "|---" * len(COLUMNS) + "|",
    ]
    lines += ["| " + " | ".join(_cell(row[c]) for c in COLUMNS) + " |" for row in rows]
    return "\n".join(lines) + "\n"


def merge(old: "dict | None", raw: dict, root: Path, filed: str) -> dict:
    """The row for one Notion item, keeping the KB page and hash its decision was made on. filed: the brand
    and week of the approvals page the row lives on, e.g. 'demo 2026-W05'."""
    approval = _text(raw.get("Approval")) or PENDING
    row = {
        "item": _text(raw.get("Name")),
        "kb_page": _text(raw.get("KB page")),
        "kb_sha256": "",
        "approval": approval,
        "ai_label": LABEL_ON if _text(raw.get("AI label")) == CHECKED else LABEL_OFF,
        "board_comment": _text(raw.get("Board comment")),
        "notion": _text(raw.get("url")),
        "note": "",
    }
    notes = []
    notion_filed = f"{_text(raw.get('Brand'))} {_text(raw.get('Week'))}"
    if notion_filed != filed:
        notes.append(f"Notion now files it under {notion_filed}")
    if approval != APPROVED or not old or old["approval"] != approval:
        row["kb_sha256"] = page_sha256(row["kb_page"], root)
        if old and old["approval"] == approval:  # still not Approved: a fresh hash, the same facts
            notes = [n for n in old["note"].split("; ") if n.startswith(STICKY_NOTES)] + notes
        elif approval != PENDING and not old:
            notes.append("first synced after the decision: no earlier hash to compare")
        elif approval != PENDING:
            if old["kb_page"] != row["kb_page"]:
                notes.append(f"the KB page changed after the last sync before the decision (was {old['kb_page'] or 'empty'})")
            elif not old["kb_sha256"]:
                notes.append("no earlier hash to compare")
            elif old["kb_sha256"] != row["kb_sha256"]:
                notes.append("the page changed after the last sync before the decision")
        return dict(row, note="; ".join(notes))
    notes = [n for n in old["note"].split("; ") if n.startswith(STICKY_NOTES)] + notes
    if row["kb_page"] != old["kb_page"]:
        notes.append(f"Notion's KB page is now {row['kb_page'] or 'empty'}")
    if page_sha256(old["kb_page"], root) != old["kb_sha256"]:
        notes.append("the page changed after the decision")
    return dict(row, kb_page=old["kb_page"], kb_sha256=old["kb_sha256"], note="; ".join(notes))


def approvals_pages(marketing: Path) -> dict:
    """{Notion URL: the approvals page it first appeared on}, across every brand and week."""
    pages = {}
    for page in sorted(marketing.glob("**/approvals/*.md")):
        for row in read_rows(page):
            pages.setdefault(row["notion"], page)
    return pages


def upsert(raw_rows: list, query_scope: tuple, synced_at: str, marketing: Path = MARKETING) -> list:
    """Write each approvals page a complete query touches or covers; return what was written or skipped."""
    root = marketing.parents[1]
    folders = brand_folders(root)
    first_page = approvals_pages(marketing)
    weeks, brands = query_scope
    touched, notes = {}, []
    for raw in raw_rows:
        brand, week, url = folders.get(_text(raw.get("Brand"))), _text(raw.get("Week")), _text(raw.get("url"))
        if not brand or not WEEK.fullmatch(week) or not url:
            notes.append(f"skipped '{_text(raw.get('Name')) or '?'}' (brand '{_text(raw.get('Brand'))}', week '{week}')")
            continue
        page = first_page.get(url) or marketing / brand / "approvals" / f"{week}.md"
        touched.setdefault(page, {})[url] = raw
    for page in set(first_page.values()):
        brand, week = page.parent.parent.relative_to(marketing).as_posix(), page.stem
        if (weeks is None or week in weeks) and (brands is None or brand in brands):
            touched.setdefault(page, {})
    for page, raws in sorted(touched.items()):
        brand, week = page.parent.parent.relative_to(marketing).as_posix(), page.stem
        filed = f"{brand.rsplit('/', 1)[-1]} {week}"
        old = read_rows(page)
        rows, seen = [], set()
        for row in old:
            raw = raws.get(row["notion"])
            if raw is not None:
                rows.append(merge(row, raw, root, filed))
                seen.add(row["notion"])
            elif "not in a complete Notion query" not in row["note"]:
                rows.append(dict(row, note="; ".join(filter(None, [row["note"], "not in a complete Notion query of "
                                                                   "this week (moved or deleted)"]))))
            else:
                rows.append(row)
        rows += [merge(None, raw, root, filed) for url, raw in raws.items() if url not in seen]
        rel = page.relative_to(root)
        if rows == old:
            notes.append(f"{rel}: unchanged")
            continue
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text(render(brand, week, rows, synced_at), encoding="utf-8")
        notes.append(f"{rel}: {len(rows)} items")
    return notes


def main(stdin=sys.stdin, marketing: Path = MARKETING) -> int:
    try:
        query = calendar_query(json.load(stdin), marketing.parents[1])
        if query is None:
            return 0
        rows, query_scope = query
        if query_scope is None:
            notes = ["not synced: query the calendar by Week (and Brand) only, with every row returned "
                     "(knowledge/marketing/notion.md)"]
        else:
            synced_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            notes = upsert(rows, query_scope, synced_at, marketing)
    except (ValueError, AttributeError, TypeError, KeyError, OSError) as error:
        print(f"notion_approvals_sync: couldn't sync the Board's approvals ({type(error).__name__}: {error}).",
              file=sys.stderr)
        return 0
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PostToolUse",
        "additionalContext": "Board approvals from Notion: " + ("; ".join(notes) or "no calendar items"),
    }}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
