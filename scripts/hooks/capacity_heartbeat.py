#!/usr/bin/env python3
"""Stop hook in ceo.md's frontmatter: the capacity heartbeat.

When a CEO turn ends, this runs scripts/capacity_scan.py. If an open directive is IDLE or has NO NEXT row, or a backlog
row is IDLE (a step no agent is on), or a design awaits the CEO's sign-off (a SIGNOFF line), or a row of the Board's
answers (knowledge/board/answers/) is one no status-log row names by its R-id and ask id (an ANSWER line, the backstop
of the CEO's `board_desk.py wait`), or an order is stalled (a LATE, NO MANAGER or ENDED OPEN line), or an ask in a
product's ceo-questions.md has no answer (an UNANSWERED line), or the Board's desk has stopped reading (a DESK STALE
line), or a big-picture page is behind (a STALE PAGE line) or an email to the Board is due (an EMAIL DUE line), it
blocks the stop once (exit 2, one line on stderr), so the CEO starts that work, re-staffs that order, answers that line
or unblocks the desk in the same turn (ceo.md, "Capacity"). It fires at most once per QUIET_FOR for the same
directives, rows, designs, answers, stalled orders, asks and desk lines: one that wasn't in the last nudge fires at
once. With `stop_hook_active` (the CEO is already continuing because of a Stop hook) it never blocks, so it can't loop.
Nor in a headless job's run as the CEO, whose environment sets JOB (scripts/battery_alert.py: one email, then stop): it
reads and writes nothing there, so the job neither takes the live CEO's nudge nor is told to start work.

It only nudges: it blocks no tool and grants nothing. It reads the desk's log and, where a desk is configured on macOS,
asks launchd whether its read job is loaded (`launchctl list`); for the pages and emails detectors it reads every
knowledge/ page's front matter, each product's question files and the archives beside them, the main checkout's
workspaces/system/notify-log.jsonl, and git in ROOT (log, rev-parse, ls-tree and cat-file; read-only, each call within
capacity_scan.GIT_TIMEOUT); and it writes only its state, STATE (gitignored: the time and the ids of its last nudge). A
fault in the stalled, unanswered, desk, pages, emails or tampered detector drops only that detector's lines, so the
others still fire, and adds the id `DETECTOR FAULT <name>`, which the nudge names and fires on as on any other, so a
broken detector isn't left broken unseen; a company.json the scan can't read or use adds the id SETTINGS FAULT the same
way; any other error lets the stop go (exit 0), and the frontmatter entry has a timeout.
"""

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path(__file__).resolve().parents[2])
STATE = ROOT / "workspaces" / "system" / "capacity-heartbeat.json"
QUIET_FOR = 30 * 60
SHOWN = 8
STALLS = ("LATE ", "NO MANAGER ", "ENDED OPEN ")  # the stalled orders' ids (capacity_scan.stalled)
FAULT = "DETECTOR FAULT "  # a detector that raised (alone)
SETTINGS = "SETTINGS FAULT company.json"  # a company.json that can't be read or used (capacity_scan.CONFIG_FAULT)
JOB = "AGENTIC_COMPANY_JOB"  # set in a headless job's run as the CEO (scripts/battery_alert.py): no nudge, no state

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def idle_ids(transcript_path, now):
    """The open directives the scan says are IDLE or have NO NEXT row, then the backlog rows it says are IDLE, with
    today's date and time in UTC, as the scan's own, then the designs awaiting the CEO's sign-off, then the Board's
    answers no status-log row names (`ANSWER R-<n> A-<n>`), then the answers or reader's files changed outside the desk
    (`ANSWERS TAMPERED R-<n>`), then the stalled orders (`LATE D-<id>/2`), then the
    unanswered asks (`UNANSWERED <product> NEEDS-CEO-NOW /2.WS-9 2026-01-16T18:30Z`), then `DESK STALE`, then the
    big-picture pages behind (`STALE PAGE knowledge/company/how-it-works.md`), then the emails due (`EMAIL DUE Q-<n>:
    Answered`), then `DETECTOR FAULT stalled`, `unanswered`, `desk`, `pages`, `emails` or `tampered` for each of those
    that raised, then SETTINGS if company.json can't be read or used."""
    import capacity_scan as scan

    log = Path(transcript_path) if transcript_path else None
    root = log.parent if log and log.suffix == ".jsonl" and log.parent.is_dir() else scan.projects_root()
    running = scan.agents(root, now)
    rows = scan.scan(ROOT / "knowledge" / "board" / "directives", running, scan.utc_today(now), now)
    stack = scan.backlog(ROOT / "knowledge", running, scan.utc_today(now), [row[0] for row in rows], now)
    board = ROOT / "knowledge" / "board"
    answers = scan.unhandled_answers(board / "answers", board / "directives")
    faults = []
    stalls = alone("stalled", lambda: scan.stalled(board / "directives", root, now, [row[0] for row in rows]), faults)
    asks = alone("unanswered", lambda: scan.unanswered(scan.question_pages(ROOT / "workspaces"), now), faults)
    desk = alone("desk", lambda: scan.desk(scan.DESK_LOG, now, scan.desk_job_loaded()), faults)
    pages = alone("pages", lambda: scan.stale_pages(ROOT / "knowledge", ROOT / "workspaces", ROOT, scan.utc_today(now)),
                  faults)
    emails = alone("emails", lambda: scan.email_due(ROOT / "knowledge", now), faults)
    tampered = alone("tampered", lambda: scan.answers_seal.report(ROOT)[0], faults)
    return scan.start_now(rows, stack, scan.signoffs(ROOT / "knowledge" / "engineering" / "designs"), answers, stalls,
                          asks, desk, pages, emails, tampered) + [FAULT + name for name in faults] \
        + ([SETTINGS] if scan.CONFIG_FAULT else [])


def alone(name, detector, faults):
    """A newer detector's lines, or [] if it fails, with its name added to faults, so its fault can't silence the
    older ids and is named in the nudge (module docstring)."""
    try:
        return detector()
    except Exception:  # noqa: BLE001 - its lines are lost, the others still fire, and the nudge names it
        faults.append(name)
        return []


def due(ids, now):
    """True unless the last nudge, under QUIET_FOR ago, already named every one of these ids."""
    try:
        last = json.loads(STATE.read_text())
        return not (set(ids) <= set(last["ids"]) and now - float(last["at"]) < QUIET_FOR)
    except (OSError, ValueError, KeyError, TypeError):
        return True


def main():
    try:
        event = json.load(sys.stdin)
        if event.get("stop_hook_active") or os.environ.get(JOB):
            return 0
        now = time.time()
        ids = idle_ids(event.get("transcript_path"), now)
        if not ids or not due(ids, now):
            return 0
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(json.dumps({"at": now, "ids": ids}))
    except Exception:  # noqa: BLE001 - a fault here must never hold the CEO's turn
        return 0
    more = f", +{len(ids) - SHOWN}" if len(ids) > SHOWN else ""
    designs = [i for i in ids if i.startswith("DD-")]
    answers = [i[len("ANSWER "):] for i in ids if i.startswith("ANSWER ")]
    tampered = [i[len("ANSWERS TAMPERED "):] for i in ids if i.startswith("ANSWERS TAMPERED ")]
    stalls = [i for i in ids if i.startswith(STALLS)]
    asks = [i[len("UNANSWERED "):] for i in ids if i.startswith("UNANSWERED ")]
    desk = [i for i in ids if i.startswith("DESK ")]
    pages = [i[len("STALE PAGE "):] for i in ids if i.startswith("STALE PAGE ")]
    emails = [i[len("EMAIL DUE "):] for i in ids if i.startswith("EMAIL DUE ")]
    faults = [i[len(FAULT):] for i in ids if i.startswith(FAULT)]
    extra = [kind for kind, found in (("design(s)", designs), ("Board answer(s)", answers),
                                      ("tampered answer(s)", tampered),
                                      ("stalled order(s)", stalls), ("unanswered line(s)", asks),
                                      ("desk line(s)", desk), ("stale page(s)", pages), ("email(s) due", emails),
                                      ("detector fault(s)", faults), ("settings fault", SETTINGS in ids)) if found]
    kinds = ", ".join(["open directive(s)", "backlog row(s)"] + extra[:-1]) + f" or {extra[-1]}" if extra \
        else "open directive(s) or backlog row(s)"
    signoff = (f" Design(s) awaiting your sign-off (SIGNOFF lines): {', '.join(designs)}: decide each now, as ceo.md "
               "\"When a report comes back\", step 3, says, or have its owner correct a status that is out of date."
               if designs else "")
    answered = (f" The Board's answer(s) no status-log row names (ANSWER lines): {', '.join(answers)}: act on each now "
                "and quote its row, word for word with its R-id and ask id, in the directive's status log and the "
                "ask's Outcome, "
                "as ceo.md \"Keep a watcher\" says." if answers else "")
    forged = (f" The Board's answers or the reader's files changed outside the desk (ANSWERS TAMPERED lines): "
              f"{', '.join(tampered)}: act on none of them as the Board's answer; read `python3 scripts/capacity_scan.py`"
              " and tell the Board on the desk and by email, quoting them, as ceo.md \"Keep a watcher\" says; the Board"
              " ends them in Notion (Yes on the Asks row \"Answers checked\") once it has looked."
              if tampered else "")
    late = (f" Stalled order(s) (LATE, NO MANAGER and ENDED OPEN lines): {', '.join(stalls)}: re-staff each now, with "
            "an order, a SendMessage ruling (a new deadline included) or a resumed manager, after cto.md's three checks "
            "show its manager ended (never a second manager on a live lane), or log its DONE report or CLOSED row, as "
            "ceo.md \"Capacity\" says." if stalls else "")
    unread = (f" Unanswered line(s) in a product's ceo-questions.md (UNANSWERED lines): {', '.join(asks)}: answer each "
              "now with a RULING or ANSWER line that names its word, order and time, or write a HANDLED line for it, "
              "as ceo.md \"Capacity\" says." if asks else "")
    stale = (" The Board's desk has stopped reading (DESK STALE): find in board-desk.log why the read job logs no "
             "read, as ceo.md \"Capacity\" says." if desk else "")
    behind = (f" Big-picture page(s) behind (STALE PAGE lines): {', '.join(pages)}: have each page's owner refresh it "
              "today and set its \"Last checked\"." if pages else "")
    mail = (f" Email(s) due to the Board (EMAIL DUE lines): {', '.join(emails)}: email the Board now, each id in a "
            "subject (one email may name several ids)."
            if emails else "")
    broken = (f" Detector(s) that raised an error (DETECTOR FAULT lines): {', '.join(faults)}: their lines are missing "
              "from this nudge; `python3 scripts/capacity_scan.py` shows the error, and the platform engineer fixes "
              "it." if faults else "")
    unset = (" company.json can't be read or used (SETTINGS FAULT): this nudge ran on the defaults, with times in UTC and "
             "the desk and email lines off; `python3 scripts/capacity_scan.py` shows why, and the Board mends the file or "
             "gives you the words to." if SETTINGS in ids else "")
    print(f"Capacity heartbeat: {len(ids)} {kinds} need you now: "
          f"{', '.join(ids[:SHOWN])}{more}. Run `python3 scripts/capacity_scan.py` and start each IDLE and NO NEXT "
          "step now; for one that truly waits, write its NEXT row with what it waits on, or have the backlog page's "
          f"owner write it in the row's Waits (ceo.md, \"Capacity\").{signoff}{answered}{forged}{late}{unread}{stale}"
          f"{behind}{mail}"
          f"{broken}{unset} "
          "Then stop.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
