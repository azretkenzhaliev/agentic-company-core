#!/usr/bin/env python3
"""Whether the scheduling poll has anything to do. scripts/marketing_schedule_job.sh runs it before it starts Claude.

    python3 scripts/marketing_schedule_gate.py

Exit 0, naming the pieces, when the poll has a piece to act on; exit 3, with one line, when it has none, and the job
then starts no session. On any other exit (a crash, an unreadable page) the job runs as before. It reads only this
checkout (the founder's piece pages, the approvals pages and the ledger) and calls nothing outside.

A piece to act on is a founder piece page (knowledge/marketing/founder/<account>/content/<week>/<slug>.md) whose item
id isn't in the ledger, and either
- post.read_piece takes it and its Publish at is still ahead: stage_item.py may stage it, or, under 2 hours ahead,
  the poll writes "Not scheduled: <reason>" in Notion if the Board approves it; or
- read_piece refuses it and its week is this ISO week or the next, the weeks the poll queries: the poll writes that
  line if the Board approves it; or
- its path matches post.PAGE only when letter case is ignored (a 2026-w05 folder, First.md): a disk may ignore
  case, so stage_item.py and the hook open it by the item id's path, and the gate can't tell what they'll find.

Why it can't miss an approved piece: the poll schedules only through
stage_item.py, which refuses a piece unless read_piece takes its page, its Publish at is at least post.MIN_AHEAD
(2 hours) ahead, and its item id isn't in the ledger. Every such piece is due here, by the same code, before
stage_item.py would check it: time only moves on. While any piece is due, the poll runs as before and syncs the
Board's decisions every 30 minutes, so a piece the Board hasn't decided keeps it running until its Publish at.
"""

import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools/marketing/publish"))

import post  # noqa: E402
import stage_item  # noqa: E402

NOTHING = 3  # the job's code for "no session"
NAME_CASE = re.compile(post.PAGE.pattern, re.IGNORECASE)  # a page post.PAGE matches only when case is ignored


def listing(folder: Path) -> list:
    """The folder's entries, or none when there is no such folder. A folder it can't list raises: Path.glob would
    skip it silently, while stage_item.py could still read a page in it by its path."""
    try:
        return sorted(folder.iterdir())
    except (FileNotFoundError, NotADirectoryError):
        return []


def due(root: Path, now: datetime) -> list:
    """The pieces the poll may act on now (the docstring), as '<item id> at <Publish at>', '<item id> (refused)' or
    '<item id> (name case)'."""
    # The weeks the job queries: `date +%G-W%V` and `date -v+7d +%G-W%V`, in this computer's time zone
    queried = {(now + timedelta(days=d)).astimezone().isocalendar()[:2] for d in (0, 7)}
    found = []
    pages = [page for account in listing(root / "knowledge/marketing/founder")
             for week in listing(account / "content") for page in listing(week) if page.suffix.lower() == ".md"]
    for path in pages:
        page = path.relative_to(root).as_posix()
        match = post.PAGE.fullmatch(page)
        if not match:
            loose = NAME_CASE.fullmatch(page)
            if loose:  # e.g. a 2026-w05 folder: a disk may ignore case, so stage_item.py and the hook open it
                _, account, year, week, slug = (part.lower() for part in loose.groups())
                item_id = f"{year}-w{week}-{account}-{slug}"
                if not stage_item.already_scheduled(item_id, root):
                    found.append(f"{item_id} (name case)")
            continue
        _, account, year, week, slug = match.groups()
        item_id = f"{year}-w{week}-{account}-{slug}"  # post.Piece.item_id
        try:
            piece = post.read_piece(page, root)
        except post.Refused:  # anything else (an unreadable page) ends the gate, and the poll runs
            if (int(year), int(week)) in queried and not stage_item.already_scheduled(item_id, root):
                found.append(f"{item_id} (refused)")
            continue
        if piece.publish_at > now and not stage_item.already_scheduled(item_id, root):
            found.append(f"{item_id} at {piece.publish_at.isoformat()}")
    return found


def main(root: Path = ROOT, now: "datetime | None" = None) -> int:
    found = due(root, now or datetime.now(timezone.utc))
    if not found:
        print("nothing to schedule: no founder piece page with its Publish at ahead, or refused in a week the poll "
              "queries, that isn't in the ledger")
        return NOTHING
    print("due: " + ", ".join(found))
    return 0


if __name__ == "__main__":
    sys.exit(main())
