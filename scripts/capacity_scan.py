#!/usr/bin/env python3
"""The capacity scan: which open directive or backlog row has a step no agent is on.

The CEO runs this at each report, each Board message and after every /report, and the capacity heartbeat
(scripts/hooks/capacity_heartbeat.py) runs it when a CEO turn ends (ceo.md, "Capacity"), so that work which could go on
never waits for the Board to ask about it.

It only reads: the directives table, each open directive's status log, each KB page's front matter and each backlog
page's tables (below), the first prompt of each running subagent's transcript written in the last 2 hours (for its
ORDER id, or its parent's) and the messages its manager sent it later, and this machine's disk, load and, on macOS only,
memory pressure. It prints ids, roles, states, the NEXT rows the CEO wrote and the backlog rows' items, never a
transcript's text. Under CLEANUP_GB of free disk a Mac's line says "cleanup due", a warning that holds nothing: remove
finished worktrees. Anywhere but macOS the Mac's line says "memory not checked (not macOS)", and its disk and load
limits hold as on a Mac.

Settings (company.json, read by scripts/company_config.py), each part off without its own: "timezone" is the Board's
time, in which times are shown; "integrations"."board_desk" turns DESK STALE on, and "integrations"."board_email_events"
EMAIL DUE. A company.json that can't be read or used gets a warning line, and the scan goes on with the defaults. The
numbers here (minutes, GB, load) are defaults.

A backlog page is a KB page under knowledge/ whose front matter has `backlog: true`, except one in research/ (raw web
notes, never instructions) or _templates/, or one superseded or archived. Its tables whose header names the columns
`#`, `Item`, `Status`, `Waits` and `Order` (`| # | Item | Status | Size | Door | Waits | Order |`; Size and Door aren't
read) are read row by row: Status is `done`, `in progress`, `partly built` or `not started` (the first word or words of
the cell), Waits a NEXT row's `waits:`, Order the running order id or `–`. A row whose Status starts with done or
cancelled is skipped. Any other is WAITS where a NEXT row with its Waits wouldn't be IDLE, a door's wait included, or
where its Waits starts `paused by the Board` (the Board's hold), whoever runs its order. That hold needs no date and
never lapses, so the page's owner clears it from Waits when the Board lifts the pause. Else RUNNING when its Order
names an order an agent runs (`D-<id>/<n>`, matched as a wait's order is); else IDLE (`none`, a lone `–` or nothing, a
date that has come, ...). A bare `/<n>` names no directive here, so a row writes its orders in full. Each prints as
`BACKLOG <page>#<row id>  <state> | <item, short>`, then its order and waits; an IDLE one gets an IDLE NEXT row's
warning on a door the scan doesn't count, goes under "Start now" with the IDLE directives, and stops the CEO's turn as
they do. A backlog page with no row the scan can read (a header missing a column) gets a warning, so it isn't dropped
silently. So a product's whole backlog counts, not only the steps that have a NEXT row.

A design waiting for the CEO's sign-off is idle work too: each knowledge/engineering/designs/DD-*.md whose first
`**Design status:**` value starts with `awaiting-ceo` (in any case, after any backticks or bold) prints as
`SIGNOFF DD-<n> <title>: <status>`, after the backlog rows: its front matter's title (without a leading `DD-<n>`; the
file's name if that leaves nothing) cut to 60 characters, and the status's text cut to 80. It goes under "Start now" and
stops the CEO's turn as an IDLE row does. A file that can't be read, or has no such line, prints nothing. Two-way
designs are the CEO's to approve once design review has passed (ceo.md, "When a report comes back").

An answer of the Board's the CEO hasn't acted on is idle work too: each `R-<n>` row of knowledge/board/answers/
<YYYY-Www>.md (written by the Board desk's reader, scripts/board_desk.py) that no status-log row of a directive names
by its R-id and its ask id together (a note's as `R-<n> Note`, a row the Board added to Q&A as `R-<n> Q&A`), its
archives' rows included, prints as `ANSWER R-<n> <ask id>` before the Mac's line, by number, and goes under "Start now"
as it prints. It is the backstop of the CEO's watcher, `board_desk.py wait` (ceo.md, "Keep a watcher"). After the
ANSWER lines, each `ANSWERS TAMPERED <R-id or file>: <what>` line of the reader's seal
(scripts/board_desk/answers_seal.py: a row or file changed outside the reader, or a row not as Notion holds it at the
hourly check) prints and goes under "Start now" by its subject, and a row it names is no ANSWER line; then an
`ANSWERS NOT CHECKED at <time>` line when the hourly check couldn't read Notion, which doesn't. With no desk there are
no answers pages, and none of these prints.

A subagent runs while its transcript isn't finished, or while it ended its turn "waiting on its own background work":
a background task it started (a `backgroundTaskId` in a tool result) that no later task notification in its transcript
names. A critic's prompt is a directive file's path, not an ORDER (ceo.md, "Challenge before you plan"): a running
critic counts as that directive's work, for any of its orders a wait names, and lists as `critic (path)`.

An order reopened after its REPORT DONE row runs too, for a NEXT row's wait and a directive's RUNNING: a later
status-log row that starts `RULING /<n>` (after at most a role word, as LATE reads a row; `RULING /9/2` names /9) and
says "fix round" outside quotes reopens a done order until a later REPORT DONE or CLOSED row names it, and counts for
RUNNING_FOR (2 hours) after the first UTC time the row names (`RULING /9/2 15:10:30Z`, as `date -u` gives it), so a fix
round left stuck or never started reads IDLE again, and a row with no time counts for nothing. And a subagent whose
manager sent it a message after its last hand-back (a SubagentHandback call in an assistant record) runs, whatever its
meta says, while it was written in the last 2 hours. Its header still has to be a form this reads: `ORDER <id>/9
(resume, fix round)   from: ceo   to: platform-engineer` or `RULING <id>/9 fix round ...`, not `ORDER <id>/9 RESUME`.

A directive's state, the first that fits:
- RUNNING: it has no `NEXT:` row, and an agent runs one of its orders (its transcript isn't finished and was
  written in the last 2 hours);
- NO NEXT: it has no `NEXT:` row, and no agent runs one of its orders;
- BOARD: the row waits on a one-way door (`waits: b<N> ...`) or on the Board's order to start work that only it starts
  (`waits: board-order ...`, as marketing's), or names one after an order no agent runs any more or after a date that
  has come;
- IDLE: `waits: none` (or no `waits:`), even while agents run its other orders; a date that has come, whatever else
  its reason says, with no door after it; a directive that isn't open (done, cancelled or not in the table); or an
  order that no agent runs any more, with no door after it;
- WAITS: a date still to come, an open directive, an order an agent runs, or another reason the row gives.
A date is compared with today's date in UTC, as the logs write it, never the machine's own. A date with a time after it
(`2026-01-13 01:40Z`, or `01:40:45Z`) is compared to the minute, in UTC. An ISO `T` between the two
(`2026-01-15T06:30Z`) reads as the space, wherever a wait's date is read.
A door, a date or a directive counts only when the wait starts with it (`waits: b2 ...`, `waits: 2026-01-09`,
`waits: D-20260101-<slug>`): `waits: none (see b2)` is IDLE, and a date in a reason is only a reason. An order counts
as `D-<id>/<n>` anywhere in the wait, and as a bare `/<n>` (this directive's) only at its start. A door after an order
or a date counts only after `, `, `; ` or `then ` (`waits: /2, then b2`), so `waits: /2, see bucket b2` is IDLE once
/2 is done. `board-order` counts as a door does: `waits: 2026-01-16, then board-order` reads BOARD once that day comes,
so no such work starts by itself. The row is judged on its own: the agents that run the directive's other orders are
listed, and hide nothing. An IDLE row whose wait names a b<N> or board-order outside an id, and doesn't start with
`none`, gets a warning line under it: so a door the scan doesn't count (`/2 and b2`, `/2 (b2)`, `/2: b2`) isn't dropped
silently. Two more warnings:
- a dated row below the latest NEXT row that holds `NEXT:` mid-row (outside double-quoted and backticked spans,
  each on one line, and not right beside a straight quote or backtick): the scan reads only a row that starts with
  it, so it reads the older one;
- a WAITS row whose wait names data, results, a run, numbers or a replay with no date, door, directive or order first:
  nothing wakes it. The date the data is due goes first: `waits: 2026-01-10 08:30Z, ...`.

An agent's order is the first header `ORDER <id>/<n>   from: <role>   to: <role>` in its first prompt. A sub-id after
the number (`/151.D2.T3`) counts as order /151, and a short note in parentheses may follow the number or the sender
(`/10 (resumed)   from: ceo`). The roles may be in any case, and are kept in lower case.
A running agent whose first prompt has a line that starts with "ORDER " and isn't a header the scan reads, wherever
it sits (after a preamble, or beside a header it reads), gets a warning line naming it, not only a count.
An agent runs every order its first prompt's first line starting with "ORDER " or "RESUME of ORDER " lists, joined by
`, ` or `and` (`RESUME of ORDER <id>/<n>, ORDER <id>/<n> and ORDER <id>/<n>`, or the list without `RESUME of`, ending
its line or before a header's `from:`), and its children take them all.
An agent the main session started whose first prompt starts "CEO gate review" and holds no header or list the scan
reads runs the one `ORDER <id>/<n>` the prompt names outside double-quoted and backticked spans, each on one line: `The
order (ORDER <id>/46, ...)` counts, `"ORDER <id>/44"` doesn't, one in single quotes or a fenced block does, and a prompt
that names two or more such orders follows the rules above. The CEO starts the reviewer's prompt, and a re-check's, with
`ORDER <id>/<n> (gate review)   from: ceo   to: code-reviewer` (a re-check: `(gate re-check)`), a header as above.
An agent also runs each order its manager (the main session, for the CEO's reports) sent it later with SendMessage,
and its children take these too: a message whose first line is a header or list as above, `ORDER <id>/<n>` alone
(`ORDER X/4 is cancelled` isn't one), `RULING <id>/<n> ...` or `RULING <short id>/<n> ...`, after at most one sender's
role word in any case (CEO, CTO, Staff, CMO: `CEO RULING cfa/6 ...`). Claude Code writes such a message as a
`queued_command` attachment while the agent runs, or as a user record after "The coordinator sent a message ..." when
it wakes a finished one, both with origin kind "coordinator". A short id is the first letter of each word of a
directive's slug (`cfa` is D-20260101-checkout-fewer-alarms) and counts for the one open directive that has it: with
none or several, it counts for nothing, so write the full id.

Agents are read from the main checkout's session folder (the heartbeat takes the same folder from its transcript's
path), so a run from a worktree sees the CEO's agents; without that folder it says so, and counts none.

Stalled orders, so that work nobody is doing any more doesn't look busy. Each open directive's orders print, after the
ANSWER lines:
- LATE: the latest deadline, target or ready estimate with a UTC time (`deadline 2026-01-16T16:30Z`; a bare `16:30Z`
  in a status-log row is the row's day) that the order's own block (a line starting `ORDER <id>/<n>` with no sub-id,
  to the next heading, fence or row; only dated times there) or a status-log row logs for it, has passed, with no
  `REPORT /<n> ... DONE` row and no row starting `CLOSED /<n>` (the CEO's word that it ends without DONE). A row
  names its orders after `ORDER`, `ORDERS` (a list, or a range `/3-/6`), `RULING` or `CLOSED` at the row's start (a
  role word may come first), or `REPORT`, by a bare `/6`, the full id, the short id (`cfa/7`) or the slug's tail
  (`map-view/6` for D-20260101-demo-map-view's /6); a sub-id (`/2/1`, `/8.T2`) and a quoted or backticked mention
  don't count, and archives count first, then the page, a later time replacing an earlier one; any row's time beats the
  block's.
- NO MANAGER: only senior-engineer, code-reviewer, design-reviewer or ux-expert run the order, which has no DONE
  report or CLOSED row, and the manager that started one of them has handed back since it was last woken (a
  SubagentHandback call after the last message from its manager, a child or a background task) or was stopped. A
  worker the main session started has no manager to lose.
- ENDED OPEN: a cto or staff-engineer has ended in the last ENDED_FOR (handed back, stopped, or quiet with every agent
  under it for ALIVE_FOR), its order has no DONE report or CLOSED row, and no live agent runs it.
  A manager that hasn't handed back counts as alive while it, or any agent under it, wrote in the last ALIVE_FOR: a
  manager parks by ending its turn to wait on its children, so its transcript reads finished and goes quiet, and a
  child's end_turn without a hand-back doesn't wake it. Counting only running agents would flag every lane whose
  manager waits on its Seniors.
- UNANSWERED: a line of a product's workspaces/<product>/content/ceo-questions.md that starts (after a list mark,
  bold or a writer's word) NEEDS-CEO-NOW, NEEDS-CTO or QUESTION, or COORD with the CEO among its recipients (`-> CEO`,
  `to the CEO`), dated (`2026-01-16T18:40Z`), that no line starting RULING, HANDLED or ANSWER, or marking ACTED,
  with the numbered or indented lines below it, in the page or the archive beside it (where cq_archive.py moves
  HANDLED lines), cites within ANSWER_IN (10 minutes for NEEDS-CEO-NOW, 15 for the rest): in a reply written after
  it (by the reply's own dated time, else below it on the page), by its ref, a few letters and its time (`on
  NEEDS-CEO-NOW /2.WS-1 18:40Z`; its word for an ask with no ref), by its time to the second (`not 09:30:30Z's`) or
  by its own id when only one ask has it (`/1.CTO.q1`); in any reply, by its ref, date and time (`/2.WS-1
  2026-01-16T18:40Z`); or by place (a RULING right above it "on the line below"). A reply's own time, the first on its
  first line before any ask's word, cites nothing. COORD lines count only to the CEO: most have no such reply.
  A NEEDS-CEO-NOW, and a QUESTION to the CEO (`-> CEO`, `to the CEO`), counts as answered only by a reply the CEO
  wrote: one that starts `CEO`, wherever it is. A line by the asker or any other agent that names the ask never answers
  it (agents never start a line with `CEO` or put `(CEO` first in a parenthesis: cto.md, staff-engineer.md,
  senior-engineer.md). The write side holds it: scripts/hooks/cq_write.py refuses a subagent's write of such a line, and
  of an indented, numbered or `(` line where it may join one, by the hook input's agent_id, in the file and in the
  archive beside it. cq_archive.py's own moves put no indented, numbered or `(` line into a
  CEO line's reply it wasn't in, in the file or the archive. A reply's indented, numbered or `(` lines join it up to the
  first with a writer field of its own (`(CTO, ...)`, `(WS-1 Staff)`, `(Senior engineer, ...)`; a parenthesis holding a
  role word next to a comma or a time anywhere in it, `(by the CTO, 17:25Z)`, `(Staff engineer WS-1, 17:25Z)`,
  `(17:25Z, CTO)`, or one after a dash, `- CTO 17:25Z`) or a role word first (`  CTO: x`, `1. Staff x`, `(CTO x`,
  `  The CTO: x`), a role word in any case or an agent's id (`(cto, ...)`, `(platform-engineer, ...)`): an agent's line
  glued under the CEO's isn't the CEO's. Agents start each `>>` with their own word.
  A QUESTION with no recipient isn't one to the CEO; a STRAY file is warned about, not read.
  The files: each product's content/ceo-questions.md, and each engineering order's own
  content/orders/<directive id>/<n>/ceo-questions.md, or content/orders-closed/... once the CEO has closed it. A
  reply in another of a product's files, or in the archive beside any of them, cites an ask as an archived reply does
  (by a date, or by its own dated time), and the line prints the file's path. One in an order's file, or the archive
  beside it, answers asks only there and in the product's own file; one in the product's own file, or its archive,
  answers asks in any of its files. Two warnings, which don't join "Start now": MISFILED, a line in an order's file
  whose word (RULING, REPORT, NEEDS, QUESTION, RESUME POINT, ...; not COORD, ANSWER or LANES) is followed by another
  order's ref (a full id, or `/<n>` of the file's directive); and STRAY, a ceo-questions.md elsewhere in a product's
  folder or content/ (its first two levels, and its orders folders' wrong depths), or in an orders folder whose names
  aren't `<directive id>/<n>`.
The stalled orders and asks join "Start now". `--stalled` prints only the LATE, NO MANAGER and ENDED OPEN lines, for
the desk's hourly entry, and exits 1 when there's any.

The Board's desk: with "integrations"."board_desk" in company.json, and while launchd has the desk's read job (DESK_JOB)
loaded, the scan reads the last DESK_TAIL bytes of the desk's log (DESK_LOG) and prints DESK STALE, after the UNANSWERED
lines, when it has no `pushed:` line and no `read: <n> answers kept` line (which every read that runs to its end writes)
in the last DESK_QUIET. The desk writes a push line only when an outcome isn't "same", so a healthy desk with nothing
new writes none, and only the read line tells it ran. A `read failed:` line doesn't count. It joins "Start now". Off a
Mac, with no desk configured or with the job unloaded, it doesn't print.

Big-picture pages ("How it works" pages, which help only while they are current). A KB page whose front matter has
`big_picture: true` (not superseded or archived, nor in research/ or _templates/) prints as `STALE PAGE <path>: last
checked <date>; <reasons>`, after DESK STALE, and goes under "Start now", when its `**Last checked:** <YYYY-MM-DD>[,
<HH:MM>[Z| UTC]] ...` line is missing or its date can't be read; or the date is more than PAGE_DAYS old (UTC today); or
a change it describes came after it. A page with `product: <id>` (a workspaces/ folder) describes that product: its
newest production deploy is the latest `DEPLOY DONE <ref> <date>T<time>Z` line, by its first dated time, in the
product's question files (question_pages) and the archives beside them; the deployers write one per deploy (runbook
"Deploy to production"). The company's page (SYSTEM_PAGE) describes the system: the newest commit on HEAD touching the
system check's paths (the system-check skill, step 1) that the line's `main` at `<sha>` doesn't hold, or, with no such
commit git knows, the newest such commit by its committer time. Any other big-picture page with no `product:` line is
STALE until its owner adds one, so its deploys aren't left unread. Each git call has GIT_TIMEOUT. A time with no zone is
the Board's ("timezone"); a time without seconds is the end of its minute, so a page refreshed in the minute of the
deploy it names is current; a date alone is compared by its UTC date, so a change later that day is seen only once a
later day's comes or the 7 days pass: write the time or `main`'s commit. A product with no DEPLOY DONE line is checked
by age alone.

Emails due to the Board, off unless company.json has "integrations"."board_email_events" with "from", a UTC time
(`"2026-01-01T00:00:00Z"`): the Board gets an email whenever a directive is finished, a question is answered, or an ask
is created or closed. From EMAIL_FROM on, each event prints as `EMAIL DUE <id>: <kind>`, after the STALE PAGE lines, and
goes under "Start now", until an email logged in the main checkout's notify-log.jsonl (the email guard's,
scripts/hooks/board_email.py: the time and subject of each email) from the base's time on, at or after the event's time,
names its id in the subject (`[CEO] Answered: ... (Q-<n>)`; one email may name several ids). So one email quiets every
event of its id before it, and an event after it needs another. An id is named when no letter, digit, `-` or `/` touches
it, so an order (`D-20260101-<slug>/15`) doesn't name its directive. The events are read by comparing knowledge/ as it
is now (uncommitted lines too) with the base, the newest commit before EMAIL_FROM: a `### Q-n` heading new to
company/board-desk/qa.md and its qa-archive-*.md pages (Answered; a changed answer is a new Q-n); an `### A-n` or `###
B-n` heading new to company/board-desk/asks.md and its asks-archive-*.md pages (New ask), or one whose status, the word
after its first `·`, is answered or withdrawn and wasn't (Ask closed); a board/directives/D-*.md file that is new and
whose front matter isn't `status: archived` (New directive; an archived page of a directive's old log rows isn't one),
or a directive whose row in the directives table (board/directives/README.md) has a Status that starts with done or
cancelled and didn't (Directive done). An ask's id is its heading's text before the first `·`, so `### B-<n> D · open`
is `B-<n> D`: only a subject naming that quiets it, not `(B-<n>)`, and its EMAIL DUE line prints it whole. Each event's
time is the earliest its own record allows, in the Board's time: a New ask's `asked <date> <HH:MM>` in its heading
(`20:1x` as 20:10), an Ask closed's date (and time, if written) after `answered` or `withdrawn`, a New directive's
Received date and a Directive done's date in its Status, and a close no earlier than its own ask; a date alone is its
day's start, so an email earlier that day (and after the ask) quiets a close written with its date alone (write
`answered 2026-01-19 23:45` to need one after it); an answer, or a record with no date, is quieted by any email naming
it. Ids are never reused, so each event comes once, and the commit before EMAIL_FROM fixes what came before it.

`--mac` prints only the Mac's line and exits 1 when there's no room for new heavy work (a spawn, a local test
container, a full-suite or whole-tree test run): under DISK_GB free, memory pressure critical or under FREE_PCT% of
memory free (or either unreadable), or a 5-minute load of LOAD_PER_CPU or more per CPU, 25 on 10 CPUs, or an
unreadable one (cto.md, "Parallel work"). A "warn" pressure is shown and doesn't block. CPU load counts too, because
work started on a loaded machine makes the tests beside it time out, which delays a deploy more than the wait does.
Anywhere but macOS memory isn't checked and holds nothing, and no cleanup is named; disk and load hold the same, so this
line and scripts/hooks/guard_agent_spawn.py agree on macOS and Linux. A system that gives no load holds, as an
unreadable one does (native Windows: docs/windows.md).

The full scan exits 1 when "Start now" lists anything (an IDLE or NO NEXT directive, an IDLE backlog row, a SIGNOFF
design, an ANSWER, ANSWERS TAMPERED, a stalled order, an UNANSWERED ask, DESK STALE, a STALE PAGE or an EMAIL DUE),
else 0, so a caller can gate on it. The heartbeat calls start_now itself and never reads the exit code.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.append(str(Path(__file__).resolve().parent / "board_desk"))

import answers_seal  # noqa: E402
import company_config  # noqa: E402
import token_report  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
DIRECTIVES = REPO_ROOT / "knowledge" / "board" / "directives"
KNOWLEDGE = REPO_ROOT / "knowledge"
WORKSPACES = REPO_ROOT / "workspaces"  # each product's content/ceo-questions.md (UNANSWERED)


def settings():
    """(the Board's time zone, the board_desk settings or None, the board_email_events' epoch time or None, why
    company.json can't be read or ""): a report goes on with the defaults and says so (module docstring)."""
    try:
        events = company_config.integration("board_email_events")
        start = datetime.fromisoformat(events["from"].replace("Z", "+00:00")).timestamp() if events is not None else None
        desk = company_config.integration("board_desk")
        return company_config.timezone(), desk if isinstance(desk, dict) else None, start, ""  # `false`: off, as the desk's
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        return timezone.utc, None, None, f"{type(error).__name__}: {error}"


BOARD_TZ, BOARD_DESK, EMAIL_FROM, CONFIG_FAULT = settings()  # EMAIL_FROM: emails due for events from then on
CLOSED = ("done", "cancelled")
BACKLOG_SKIP = ("research", "_templates")  # knowledge/'s folders that hold no backlog page (module docstring)
BACKLOG_COLUMNS = ("#", "item", "status", "waits", "order")  # the ones read, in this order
DASH = ("", "-", "–", "—")  # an empty cell
FRONT_KEY = re.compile(r"([A-Za-z_][\w-]*):\s*(.*)$")  # a front-matter line, as scripts/kb_lint.py reads it
# the Order header, with a sub-id after the number and a note after the number or the sender (module docstring)
ORDER = re.compile(r"ORDER (D-\d{8}-[a-z0-9-]+)/(\d+)(?!\d)[\w./-]*(?:\s+\([^()\n]{1,80}\))?"
                   r"\s+from:\s*([A-Za-z-]+)(?:\s+\([^()\n]{1,80}\))?\s+to:\s*([A-Za-z-]+)")  # roles in any case
ORDER_LINE = re.compile(r"^[ \t]*(?=ORDER )", re.M)  # a line that starts like a header, wherever it sits
# a first line naming several orders: a resume of them, or a header (module docstring)
LISTED = r"ORDER D-\d{8}-[a-z0-9-]+/\d+[\w./-]*(?:(?:, (?:and )?| and )ORDER D-\d{8}-[a-z0-9-]+/\d+[\w./-]*)+"
TAIL = r"(?:\s+\([^()\n]{1,80}\))?\s+from:\s*[A-Za-z-]+(?:\s+\([^()\n]{1,80}\))?\s+to:\s*[A-Za-z-]+"  # ORDER's, after n
ORDER_LIST = re.compile(rf"^[ \t]*(?:RESUME of )?{LISTED}(?={TAIL}|(?:[ \t]+\([^()\n]{{1,80}}\))?[ \t]*$)",
                        re.M)  # a list ends its line, after `RESUME of` or not, or a header's tail follows
FIRST_LINE = re.compile(r"^[ \t]*(?:RESUME of )?(?=ORDER )", re.M)
LISTED_ORDER = re.compile(r"ORDER (D-\d{8}-[a-z0-9-]+)/(\d+)")
# a sent message's first line (module docstring): one order, with a header's tail or nothing after it, or a ruling on
# one by its full or short id; after at most one sender's role word
SENT_ORDER = re.compile(rf"[ \t]*(?:RESUME of )?ORDER (D-\d{{8}}-[a-z0-9-]+)/(\d+)(?!\d)[\w./-]*"
                        rf"(?={TAIL}|(?:[ \t]+\([^()\n]{{1,80}}\))?[ \t]*$)")
RULING = re.compile(r"[ \t]*RULING (?:(D-\d{8}-[a-z0-9-]+)|([a-z][a-z0-9]*))/(\d+)(?!\d)")
SENDER = re.compile(r"[ \t]*(?i:ceo|cto|staff|cmo)[ \t]+(?=(?:RESUME of )?ORDER |RULING )")  # `CEO RULING cfa/6 ...`
SENT_BY = b'"coordinator"'  # the origin kind of a message from the agent's manager
WOKEN = "The coordinator sent a message"  # the line above one that woke a finished agent
NEXT = re.compile(r"^\|\s*(\d{4}-\d{2}-\d{2})\s*\|[^|\n]*\|\s*NEXT:\s*(.*?)\s*\|\s*$", re.M)
ORDER_ID = re.compile(r"(?<![\w/-])(D-\d{8}-[a-z0-9-]+)/(\d+)\b")
PAUSED = re.compile(r"[*_ ]*paused by the board\b", re.I)  # a backlog row's Waits: the Board's hold
BOARD_WAIT = r"(?:b[1-9]|board-order)\b"  # a one-way door, or the Board's order to start work only it starts
DOOR = re.compile(rf"(?:, |; |\bthen ){BOARD_WAIT}")  # a door after an order: only after a separator
WAIT_TIME = re.compile(r" ([01]\d|2[0-3]):([0-5]\d)(?::[0-5]\d)?Z\b")  # after a wait's date: `2026-01-13 01:40Z`, or with seconds
ISO_T = re.compile(r"^(\d{4}-\d{2}-\d{2})T(?=\d{2}:\d{2})")  # a wait's `2026-01-15T06:30Z` reads as `2026-01-15 06:30Z`
ANY_DOOR = re.compile(r"(?<![\w/-])(?:b[1-9]|board-order)(?![\w-])")  # anywhere but inside an id or a word
DIRECTIVE_PATH = re.compile(r"knowledge/board/directives/(D-\d{8}-[a-z0-9-]+)\.md")  # a critic's prompt
GATE_REVIEW = re.compile(r"\s*CEO gate review\b")  # the start of a CEO gate reviewer's prompt (module docstring)
NAMED_ORDER = re.compile(r"(?<!\w)ORDER (D-\d{8}-[a-z0-9-]+)/(\d+)")  # an order a gate review names in its body
MID_NEXT = re.compile(r"(?<![`\"'\w])NEXT:(?![`\"'])")  # not a quoted or backticked mention
ROW_DATE = re.compile(r"^\|\s*(\d{4}-\d{2}-\d{2})\s*\|", re.M)
QUOTED = re.compile(r"`[^`\n]*`|\"[^\"\n]*\"|“[^”\n]*”")  # a double-quoted or backticked span on one line
DATA_WAIT = re.compile(r"\b(?:data|results?|runs?|numbers|replay)\b", re.I)
TASK_ID = re.compile(r"<task-id>([\w-]+)</task-id>")
RUNNING_FOR = 2 * 3600    # an unfinished transcript quiet this long counts as stopped
FIX_ROUND = re.compile(r"\bfix round\b", re.I)  # a RULING row that reopens a done order (module docstring)
ROW_TIME = re.compile(r"(?:(\d{4}-\d{2}-\d{2})T|(?<![\w:]))([01]\d|2[0-3]):([0-5]\d)(?::([0-5]\d))?Z\b")  # 15:10Z
QUIET = 30 * 60           # shown as "quiet <n>m" past this
DISK_GB, LOAD_PER_CPU, FREE_PCT = 15, 2.5, 5  # LOAD_PER_CPU: of the 5-minute load (module docstring)
PRESSURE = {1: "normal", 2: "warn", 4: "critical"}
CLEANUP_GB = 60  # under this much free disk, the Mac's line says "cleanup due" (module docstring)
DESIGN_STATUS = re.compile(r"\*\*Design status:\*\*[ \t]*(.*)", re.I)  # a design's status line (module docstring)
SIGNOFF = "awaiting-ceo"  # a design status that waits for the CEO's sign-off
STATUS_LOG = re.compile(r"#{1,2} Status log\b")  # a directive's status log, or an archive's part of one
R_ID = re.compile(r"(?<![\w-])R-\d+")  # an answer's id, as a status-log row names it
ASK_ID = re.compile(r"(?<![\w-])[AB]-\d+")  # its ask's id, which the same row names
NOTE_ID = re.compile(r"(?<![\w-])(R-\d+)[\s|:,]*Note\b")  # a note to the CEO's answer, named as `R-<n> Note`
QA_ROW_ID = re.compile(r"(?<![\w-])(R-\d+)[\s|:,]*Q&A(?![\w&])")  # a row the Board added to Q&A, as `R-<n> Q&A`
NEW_DIRECTIVE_ID = re.compile(r"(?<![\w-])(R-\d+)[\s|:,]*New directive\b")  # a row the Board added to Directives,
# as `R-<n> New directive`
ANSWER_ROW = re.compile(r"^\|\s*(R-\d+)\s*\|\s*([^|]*?)\s*\|")  # an answers page's row: its R-id and ask id
# stalled orders (module docstring)
WORKERS = ("senior-engineer", "code-reviewer", "design-reviewer", "ux-expert")  # NO MANAGER: only these run it
MANAGERS = ("cto", "staff-engineer")  # ENDED OPEN: one of these ended
HANDED_BACK = b'"name":"SubagentHandback","input"'  # the call itself, not the tool's listing in a request
WOKEN_BY = (b'"origin":{"kind":"peer"', b'"origin":{"kind":"coordinator"', b'"origin":{"kind":"task-notification"')
ALIVE_FOR = RUNNING_FOR  # an agent that hasn't handed back is alive while it, or one under it, wrote this recently
ENDED_FOR = 24 * 3600  # an ended manager prints as ENDED OPEN until this long after its lane's last write
REF = re.compile(r"(?:(D-\d{8}-[a-z0-9-]+)|([a-z][a-z0-9-]*))?/(\d+)((?:[.-][A-Za-z0-9]\w*)*)")  # /2, cfa/7, a sub-id
MENTION = re.compile(r"(?<![\w\"'`“])(ORDERS?|RULING|REPORT|CLOSED)[ \t]+"
                     r"(?=(?:D-\d{8}-[a-z0-9-]+|[a-z][a-z0-9-]*)?/\d)")
NOTE = re.compile(r"[ \t]*\([^()\n]{0,80}\)")  # a note after an order in a list: `/23 (Blue, A)`
LIST_SEP = re.compile(r",[ \t]*(?:and[ \t]+)?|[ \t]+and[ \t]+|(-)")  # `-` makes a range: `/3-/6`
DUE = re.compile(r"\b(deadline|target|ready estimate)\b[^.;|\n]{0,40}?(?:(\d{4}-\d{2}-\d{2})[ T])?"
                 r"([01]\d|2[0-3]):([0-5]\d)(?::[0-5]\d)?Z\b", re.I)
REPORT_STATE = re.compile(r"\b(DONE|PARTIAL|BLOCKED)\b")
LOG_ROW = re.compile(r"^\|\s*(\d{4}-\d{2}-\d{2})\s*\|[^|\n]*\|(.*)$")  # a status-log row: its date, then the rest
ROW_LEAD = re.compile(r"[ \t]*(?:(?i:ceo|cto|staff|cmo)[ \t]+)?$")  # all that may stand before a row's RULING or CLOSED
CQ_LEAD = r"(?:- )?(?:\*\*)?(?:(?:CEO|CTO|Staff)[ \t]+)?"  # a list item, bold or a writer before a ceo-questions line's word
ASKED = re.compile(CQ_LEAD + r"(NEEDS-CEO-NOW|NEEDS-CTO|QUESTION|COORD(?:INATION)?)\b[ \t:]*"  # its word, ref, tail
                   r"((?:D-\d{8}-[a-z0-9-]+|[a-z][a-z0-9-]*)?(/\d+(?:[./][\w-]+)*))?")  # /2.WS-1, cfa/7, /4/16
REPLIED = re.compile(CQ_LEAD + r"(?:RULING|HANDLED|ANSWER)\b|.*\bACTED\b")
GOES_ON = re.compile(r"[ \t]|\d+[.)][ \t]|\(")  # an indented or numbered line, which continues the line above
ASK_STAMP = re.compile(r"(\d{4}-\d{2}-\d{2})[T ]([01]\d|2[0-3]):([0-5][\dx])(?::([0-5]\d))?(?:\.\d+)?Z")  # `21:1xZ` too
OWN_STAMP = re.compile(r"(?:(\d{4}-\d{2}-\d{2})[T ])?(\d{2}):([0-5][\dx])(?::([0-5]\d))?(?:\.\d+)?Z")  # a reply's own
ASK_WORD = re.compile(r"\b(?:NEEDS-CEO-NOW|NEEDS-CTO|QUESTION|COORD)")
TO_CEO = re.compile(r"->[^(\n]*?\bCEO\b|\bto (?:the )?CEO\b")  # a COORD line's recipients name the CEO
CEO_LEAD = re.compile(r"(?:- )?(?:\*\*)?CEO\b")  # a reply the CEO wrote starts so (module docstring)
# a role word, in any case, or an agent's id (.claude/agents/: `(cto, ...)`)
ROLE = (r"(?:CEO|CTO|CMO|Staff|Senior|Reviewer|staff-engineer|senior-engineer|code-reviewer|design-reviewer|ux-expert"
        r"|platform-engineer|analyst|critic|content-producer|content-reviewer|performance-analyst|reel-analyst"
        r"|trend-researcher)")
OWN_FIELD = re.compile(rf"\((?:[\w.+-]+[ \t]+)?{ROLE}(?:[ \t]+[a-z]+)?(?:[),;:]|[ \t]+\d)",  # `(CTO, ...)`,
                       re.IGNORECASE)  # `(WS-1 Staff)`, `(Senior engineer, ...)`
ROLE_FIRST = re.compile(rf"[ \t]*(?:[-*][ \t]+|\d+[.)][ \t]+|\(\d+\)[ \t]*)?(?:\*\*)?\(?"  # `  CTO: x`, `(CTO x`,
                        rf"(?:{ROLE}\b|the[ \t]+{ROLE}[ \t]*[:,])", re.IGNORECASE)  # `  The CTO: x`
# a role word, at most two words, then a comma or a time; or a comma or a time, then the role: a writer field in a
# parenthesis, anywhere in it (NEAR_FIELD: `(by the CTO, 17:25Z)`, `(Staff engineer WS-1, 17:25Z)`, `(17:25Z, CTO)`), or
# after a dash (DASH_FIELD: `- CTO 17:25Z`)
SIGNED = rf"\b{ROLE}\b(?:[ \t]+[\w.+-]+){{0,2}}?[ \t]*(?:,|\d)"
NEAR_FIELD = re.compile(rf"\((?=[^()\n]*\))[^()\n]*?(?:{SIGNED}|(?:,|\dZ?)[ \t]*(?:the[ \t]+)?\b{ROLE}\b)",
                        re.IGNORECASE)
DASH_FIELD = re.compile(rf"[ \t][-–—]+[ \t]+(?:by[ \t]+)?(?:the[ \t]+)?{SIGNED}", re.IGNORECASE)
ORDER_FILES = ("orders", "orders-closed")  # content/<one>/<directive id>/<n>/ceo-questions.md
ORDER_PATH = (re.compile(r"D-\d{8}-[a-z0-9-]+"), re.compile(r"\d+"))  # its two folders' names
# a line's word and its own ref
OWN_REF = re.compile(CQ_LEAD + r"(RULING|REPORT|NEEDS-CEO-NOW|NEEDS-CTO|NEEDS|QUESTION|BLOCKED|HANDOVER|"
                     r"COORD(?:INATION)?|RESUME POINT|HOLD|ANSWER|DUTY-NOTE|ACTED:)[ \t]+"
                     r"((?:D-\d{8}-[a-z0-9-]+|[a-z][a-z0-9]*)?/\d+)")
ELSEWHERE = ("COORD", "COORDINATION", "ANSWER")  # filed in the recipient's or the asker's file: never MISFILED
# HANDLED is left out of OWN_REF on purpose: one under another order's heading is cq_archive's stray, moved to its
# order's section by that order's own run.
ANSWER_IN = {"NEEDS-CEO-NOW": 10 * 60}  # seconds until an uncited ask prints as UNANSWERED
ANSWER_WITHIN = 15 * 60  # every other kind's
DESK_LOG = Path.home() / "Library/Logs/agentic-company/board-desk.log"  # board_desk.LOG
# board_desk.READ_LABEL: the job that reads and pushes
DESK_JOB = f"{(BOARD_DESK or {}).get('launchd_label', 'com.agentic-company.board-desk')}-read"
DESK_LINE = re.compile(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2})Z board desk: (?:pushed: |read: \d+ answers kept\b)")
DESK_QUIET = 10 * 60  # a loaded read job with no read or push line this long prints DESK STALE
DESK_TAIL = 256 * 1024  # bytes read from the log's end
# big-picture pages (module docstring)
PAGE_DAYS = 7  # a big-picture page whose "Last checked" date is more than this many days old is STALE
LAST_CHECKED = re.compile(r"^(?:\*\*)?Last checked:(?:\*\*)?[ \t]*(.*)$", re.M)
CHECKED_AT = re.compile(r"(\d{4}-\d{2}-\d{2})(?:,?[ T]([01]?\d|2[0-3]):([0-5]\d)(?::([0-5]\d))?Z?(?:[ \t]+(UTC))?"
                        r"(?![\d:]))?")
CHECKED_SHA = re.compile(r"`?main`? at `?([0-9a-f]{7,40})\b")  # the company page's `main` at `1a2b3c4d`
SYSTEM_PATHS = (".claude", "scripts", "CLAUDE.md", "company.json", "tools", "knowledge/_templates",
                ".gitignore")  # system-check, step 1
SYSTEM_PAGE = "company/how-it-works.md"  # under knowledge/: the big-picture page that describes the system
GIT_TIMEOUT = 5  # seconds a git call may take: well under the heartbeat's 30 (ceo.md's Stop hook)
DEPLOYED = re.compile(r"(?:- )?(?:\*\*)?DEPLOY DONE\b")  # a production deploy's line in a product's question files
# emails due to the Board (module docstring)
NOTIFY_LOG = Path("workspaces") / "system" / "notify-log.jsonl"  # board_email.LOG, in the main checkout
QA_HEAD = re.compile(r"^### (Q-\d+)\b", re.M)
ASK_HEAD = re.compile(r"^### ([AB]-\d+(?:[ \t]+[^·\n]*?)?)[ \t]*·[ \t]*(\w+)(.*)$", re.M)  # `### B-<n> D · open · ...`
ASK_CLOSED = ("answered", "withdrawn")
EVENT_AT = r"(\d{4}-\d{2}-\d{2})(?:[ \t]+([01]\d|2[0-3]):([0-5][\dx]))?"  # a record's date and time, the Board's: `20:1x`
DIRECTIVES_TABLE = "board/directives/README.md"  # a directive's Status (done, cancelled) is its row's, not its page's
DESK_PAGES = re.compile(r"company/board-desk/(?:qa|qa-archive-[\w-]+|asks|asks-archive-[\w-]+)\.md"
                        r"|board/directives/README\.md")  # under knowledge/
DIRECTIVE_PAGE = re.compile(r"board/directives/(D-\d{8}-[a-z0-9-]+)\.md")


def open_directives(readme_text):
    """Ids of the directives table's rows whose status isn't done or cancelled."""
    ids = []
    for line in readme_text.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        found = re.match(r"\[(D-\d{8}-[a-z0-9-]+)\]", cells[0]) if len(cells) >= 4 else None
        if found and not cells[-2].lower().startswith(CLOSED):
            ids.append(found.group(1))
    return ids


def next_row(text):
    """The latest `NEXT:` row as (date, step, waits), or None."""
    rows = NEXT.findall(text)
    if not rows:
        return None
    when, body = rows[-1]
    step, _, waits = body.rpartition("; waits:") if "; waits:" in body else (body, "", "")
    return when, step.strip(), waits.strip()


def wait_text(waits):
    """A wait as the scan reads it: an ISO `T` between its first date and a time reads as the space (module
    docstring), so `waits: 2026-01-15T06:30Z` is a date first, as `2026-01-15 06:30Z` is."""
    return ISO_T.sub(r"\1 ", waits)


def classify(directive, nxt, running_orders, today, open_ids=(), now=None):
    """The directive's state (module docstring); running_orders holds (directive id, n) for every running agent, with
    n None for a critic on a directive's path (any of its orders), open_ids the open directives, now the epoch time
    (for a wait's time of day; without it a wait on today has come, as a bare date's)."""
    if nxt is None:
        return "RUNNING" if any(d == directive for d, _ in running_orders) else "NO NEXT"
    waits = wait_text(nxt[2])
    if re.match(BOARD_WAIT, waits):
        return "BOARD"
    if not waits or waits.lower().startswith("none"):
        return "IDLE"
    day = re.match(r"(\d{4}-\d{2}-\d{2})\b", waits)
    if day:
        try:
            due = date.fromisoformat(day.group(1))
        except ValueError:  # 2026-02-31 is no date, so it's a reason
            return "WAITS"
        at = WAIT_TIME.match(waits, day.end())
        if due > today or (at and now is not None and due == today
                           and (int(at.group(1)), int(at.group(2))) > utc_minute(now)):
            return "WAITS"
        return "BOARD" if DOOR.search(waits, day.end()) else "IDLE"
    other = re.match(r"D-\d{8}-[a-z0-9-]+", waits)
    if other and not waits[other.end():].startswith("/"):
        return "WAITS" if other.group() in open_ids else "IDLE"
    orders = [(m.group(1), m.group(2), m.start()) for m in ORDER_ID.finditer(waits)]
    bare = re.match(r"/(\d+)\b", waits)
    if bare:
        orders.insert(0, (directive, bare.group(1), 0))
    if orders:
        if any((d, n) in running_orders or (d, None) in running_orders for d, n, _ in orders):
            return "WAITS"
        return "BOARD" if DOOR.search(waits, orders[0][2]) else "IDLE"
    return "WAITS"


def ignored_door(state, nxt):
    """The b<N> or board-order an IDLE row's wait names, unless it starts with `none`, or None (module docstring)."""
    if state != "IDLE" or nxt[2].lower().startswith("none"):
        return None
    found = ANY_DOOR.search(nxt[2])
    return found.group() if found else None


def data_wait(state, nxt):
    """The data or results word a WAITS row's wait names with no date, door, directive or order first, or None
    (module docstring): such a wait reaches classify's last fallback, which nothing wakes."""
    if state != "WAITS":
        return None
    waits = wait_text(nxt[2])
    if re.match(r"\d{4}-\d{2}-\d{2}\b|D-\d{8}-|/\d+\b", waits) or ORDER_ID.search(waits):
        return None
    found = DATA_WAIT.search(waits)
    return found.group() if found else None


def stray_next(text):
    """The date of the last dated row below the latest NEXT row that holds `NEXT:` mid-row, outside double-quoted
    and backticked spans on one line and not right beside a straight quote or backtick, or None (module docstring)."""
    rows = list(NEXT.finditer(text))
    plain = QUOTED.sub(lambda span: " " * len(span.group()), text)  # same length, so offsets hold
    found = None
    for row in ROW_DATE.finditer(plain, rows[-1].end() if rows else 0):
        end = plain.find("\n", row.end())
        if MID_NEXT.search(plain, row.end(), end if end >= 0 else len(plain)):
            found = row.group(1)
    return found


def text_of(content):
    """A prompt's text: the string, or its blocks' text joined, or ""."""
    if isinstance(content, list):
        content = " ".join(b.get("text", "") for b in content if isinstance(b, dict))
    return content if isinstance(content, str) else ""


def first_prompt(log):
    """The text of a transcript's first user prompt, or "" (never printed)."""
    try:
        with log.open("rb") as f:
            for _, line in zip(range(5), f):
                record = json.loads(line)
                if record.get("type") != "user":
                    continue
                return text_of(record.get("message", {}).get("content"))
    except (OSError, ValueError, AttributeError):
        pass
    return ""


def sent_texts(log):
    """The text of each message the agent's manager sent it with SendMessage (module docstring), never printed."""
    try:
        data = log.read_bytes()
    except OSError:
        return []
    texts, at = [], data.find(SENT_BY)
    while at >= 0:  # a find, not a parse of every line: a manager's transcript can run to tens of MB
        start, end = data.rfind(b"\n", 0, at) + 1, data.find(b"\n", at)
        end = len(data) if end < 0 else end
        try:
            record = json.loads(data[start:end])
            queued = record.get("attachment") if record.get("type") == "attachment" else None
            if isinstance(queued, dict) and queued.get("type") == "queued_command":
                if (queued.get("origin") or {}).get("kind") == "coordinator":
                    texts.append(text_of(queued.get("prompt")))
            elif record.get("type") == "user" and (record.get("origin") or {}).get("kind") == "coordinator":
                text = text_of(record.get("message", {}).get("content"))
                texts.append(text.partition("\n")[2] if text.startswith(WOKEN) else text)
        except (ValueError, AttributeError):
            pass
        at = data.find(SENT_BY, end)
    return texts


def short_id(directive):
    """The first letter of each word of a directive's slug: cfa for D-20260101-checkout-fewer-alarms."""
    return "".join(word[0] for word in directive.split("-")[2:] if word)


def by_short_id(short):
    """The one open directive whose short id this is, or None for none or several (module docstring)."""
    try:
        found = [d for d in open_directives((DIRECTIVES / "README.md").read_text()) if short_id(d) == short]
    except OSError:
        return None
    return found[0] if len(found) == 1 else None


def sent_orders(log):
    """[(directive id, n, None, None)] for each order the first line of a message from the agent's manager names
    (module docstring), each once."""
    found = []
    for text in sent_texts(log):
        line = text.lstrip().partition("\n")[0]
        sender = SENDER.match(line)
        line = line[sender.end():] if sender else line
        listed, lead, ruling = ORDER_LIST.match(line), SENT_ORDER.match(line), RULING.match(line)
        if listed:
            named = LISTED_ORDER.findall(listed.group())
        elif lead:
            named = [lead.groups()]
        elif ruling:
            named = [(ruling.group(1) or by_short_id(ruling.group(2)), ruling.group(3))]
        else:
            named = []
        for d, n in named:
            if d and (d, n, None, None) not in found:
                found.append((d, n, None, None))
    return found


def order_list(prompt):
    """The list of orders on the prompt's first line that starts with "ORDER " or "RESUME of ORDER ", or None."""
    line = FIRST_LINE.search(prompt)
    return ORDER_LIST.match(prompt, line.start()) if line else None


def first_orders(prompt):
    """[(directive id, n, from, to)]: the first ORDER header in a first user prompt, then each other order its first
    line's list names, with from and to None (module docstring); [] for none."""
    header = ORDER.search(prompt)
    found = [header.groups()[:2] + (header[3].lower(), header[4].lower())] if header else []
    listed = order_list(prompt)
    for d, n in LISTED_ORDER.findall(listed.group()) if listed else ():
        if all((d, n) != order[:2] for order in found):
            found.append((d, n, None, None))
    return found


def gate_order(prompt):
    """[(directive id, n, None, None)] for the one `ORDER <id>/<n>` a CEO gate review's prompt names outside
    double-quoted and backticked spans on one line, or [] for none or several (module docstring)."""
    if not GATE_REVIEW.match(prompt):
        return []
    named = set(NAMED_ORDER.findall(QUOTED.sub(lambda span: " " * len(span.group()), prompt)))
    return [named.pop() + (None, None)] if len(named) == 1 else []


def waiting_on_background(log):
    """True when the transcript started background work (a `backgroundTaskId` in a tool result) that no later task
    notification names: the agent ended its turn "waiting on its own background work" (module docstring)."""
    pending = set()
    try:
        with log.open("rb") as f:
            for line in f:
                if b"backgroundTaskId" not in line and b"<task-notification>" not in line:
                    continue
                record = json.loads(line)
                result = record.get("toolUseResult")
                if isinstance(result, dict) and isinstance(result.get("backgroundTaskId"), str):
                    pending.add(result["backgroundTaskId"])
                elif record.get("type") != "assistant" and b"<task-notification>" in line:
                    # a user prompt or a queued_command attachment carries it
                    pending -= set(TASK_ID.findall(line.decode("utf-8", "replace")))
    except (OSError, ValueError, AttributeError):
        return False
    return bool(pending)


def orders_of(folder, agent_id, cache, depth=0):
    """The orders the agent runs, (directive id, n, from, to) each (agents' docstring), memoized in cache."""
    key = (folder, agent_id)
    if key not in cache:
        log = folder / f"agent-{agent_id}.jsonl"
        prompt = first_prompt(log)
        mine = first_orders(prompt)
        if not mine and depth < 6:
            try:
                parent = json.loads((folder / f"agent-{agent_id}.meta.json").read_text()).get("parentAgentId")
            except (OSError, ValueError):
                parent = None
            if parent:
                mine = orders_of(folder, parent, cache, depth + 1)
            else:  # the main session started it
                mine = gate_order(prompt)
        cache[key] = mine + [o for o in sent_orders(log) if all(o[:2] != m[:2] for m in mine)]
    return cache[key]


def resumed(log):
    """True when the agent's manager sent it a message after its last hand-back, a SubagentHandback call in an
    assistant record (an api-request-blob record repeats earlier calls: scripts/last_handback.py), and it has handed
    back before: its manager woke it again (module docstring)."""
    try:
        data = log.read_bytes()
    except OSError:
        return False
    woken = data.rfind(WOKEN_BY[1])  # its manager's (coordinator) message
    if woken < 0 or data.rfind(HANDED_BACK, 0, woken) < 0:
        return False
    at = data.find(HANDED_BACK, woken)
    while at >= 0:
        start, end = data.rfind(b"\n", 0, at) + 1, data.find(b"\n", at)
        end = len(data) if end < 0 else end
        try:
            if json.loads(data[start:end]).get("type") == "assistant":
                return False  # it handed back again
        except (ValueError, AttributeError):
            pass
        at = data.find(HANDED_BACK, end)
    return True


def runs(info, log):
    """True when a subagent with this meta runs: not finished, or finished while still waiting on its own background
    work, or woken again by its manager after its last hand-back, and not stopped by the user (module docstring). Its
    transcript's age is the caller's to check."""
    return not info.get("finished") or (not info.get("stoppedByUser") and (waiting_on_background(log) or resumed(log)))


def agents(root, now, unread=None):
    """(directive id, n, role, minutes since its last write) for each order each running subagent under the projects
    folder runs, and (None, None, role, minutes) for one that runs none.

    An agent whose own prompt has no ORDER (a Senior's task, a reviewer's range) takes its nearest ancestor's orders,
    and one the main session started takes the order its CEO gate review names; a critic with neither takes the first
    directive path its prompt holds, with n None. Each agent also runs the orders
    its manager's messages name. A finished agent still waiting on its own background work runs (module docstring).
    Each running agent whose prompt has a line starting "ORDER " that isn't a header or list the scan reads goes into
    the list unread, if given, as (agent id, role, the first order it counts under or None)."""
    orders = {}
    found = []
    for meta in sorted(root.glob("*/subagents/agent-*.meta.json")):
        agent_id = meta.name[len("agent-"):-len(".meta.json")]
        log = meta.with_name(f"agent-{agent_id}.jsonl")
        try:
            age = now - log.stat().st_mtime
            if age > RUNNING_FOR:
                continue
            info = json.loads(meta.read_text())
        except (OSError, ValueError):
            continue
        if not runs(info, log):
            continue
        mine = orders_of(meta.parent, agent_id, orders)
        role = info.get("agentType") or "agent"
        if not mine and role == "critic":
            path = DIRECTIVE_PATH.search(first_prompt(log))
            mine = [(path.group(1), None)] if path else []
        if unread is not None:  # the heartbeat passes none, so it reads no prompt twice
            prompt = first_prompt(log)
            listed = order_list(prompt)
            if any(not ORDER.match(prompt, line.end()) and not (listed and line.start() == listed.start())
                   for line in ORDER_LINE.finditer(prompt)):
                unread.append((agent_id, role, mine[0] if mine else None))
        minutes = max(0, int(age // 60))
        found += [(order[0], order[1], role, minutes) for order in mine] or [(None, None, role, minutes)]
    return found


def mac_room():
    """(room, line): the disk, memory (on macOS) and load, and whether another heavy agent fits (module docstring)."""
    free = shutil.disk_usage(REPO_ROOT).free / 1e9
    try:
        load = os.getloadavg()
    except (OSError, AttributeError):  # AttributeError: a system without it (Windows)
        load = None
    cpus = os.cpu_count() or 1
    why = []
    if free < DISK_GB:
        why.append(f"under {DISK_GB} GB free")
    memory, short = mac_memory() if sys.platform == "darwin" else ("memory not checked (not macOS)", [])
    why += short
    if load is None:
        why.append("load unknown")
    elif load[1] >= LOAD_PER_CPU * cpus:
        why.append(f"5-minute load {LOAD_PER_CPU * cpus:g} or more, {LOAD_PER_CPU:g} per CPU")
    due = " (cleanup due: remove finished worktrees)" if free < CLEANUP_GB and sys.platform == "darwin" else ""
    shown = "unknown" if load is None else ", ".join(f"{n:.2f}" for n in load) + " (1, 5, 15 min)"
    line = (f"Mac: {free:.0f} GB free{due}; {memory}; load {shown} on {cpus} CPUs; "
            "room: " + ("yes" if not why else "no (" + "; ".join(why) + ")"))
    return not why, line


def mac_memory():
    """(text, why): macOS's memory as the line shows it, and why it gives no room ([] when it does)."""
    try:
        level = int(subprocess.run(["sysctl", "-n", "kern.memorystatus_vm_pressure_level"], capture_output=True,
                                   text=True, timeout=5).stdout.strip())
    except (OSError, ValueError, subprocess.SubprocessError):
        level = None
    try:
        report = subprocess.run(["memory_pressure", "-Q"], capture_output=True, text=True, timeout=5).stdout
        found = re.search(r"memory free percentage: (\d+)%", report)
        free_pct = int(found.group(1)) if found else None
    except (OSError, subprocess.SubprocessError):
        free_pct = None
    why = []
    if level not in PRESSURE:
        why.append("memory pressure unknown")
    elif level == 4:
        why.append("memory pressure critical")
    if free_pct is None:
        why.append("memory free unknown")
    elif free_pct < FREE_PCT:
        why.append(f"under {FREE_PCT}% of memory free")
    pressure = "unknown" if level is None else PRESSURE.get(level, str(level))
    mem = "unknown" if free_pct is None else f"{free_pct}%"
    return f"memory pressure {pressure}, {mem} free", why


def utc_today(now):
    """Today's date in UTC for the epoch time now: the date the status logs write."""
    return datetime.fromtimestamp(now, timezone.utc).date()


def utc_minute(now):
    """(hour, minute) in UTC for the epoch time now."""
    moment = datetime.fromtimestamp(now, timezone.utc)
    return moment.hour, moment.minute


def scan(directives_dir, running, today, now=None):
    """[(id, state, [(n, role, minutes)], next row)] for each open directive, in the table's order."""
    running_orders = {(d, n) for d, n, _, _ in running if d}
    open_ids = open_directives((directives_dir / "README.md").read_text())
    clock = time.time() if now is None else now
    for directive in open_ids:  # an order reopened after its DONE row runs (module docstring)
        reopened = {}
        order_log(directives_dir, directive, reopened=reopened)
        running_orders |= {(directive, n) for n, at in reopened.items()
                           if at is not None and 0 <= clock - at <= RUNNING_FOR}
    rows = []
    for directive in open_ids:
        try:
            nxt = next_row((directives_dir / f"{directive}.md").read_text())
        except OSError:
            nxt = None
        mine = [(n, role, minutes) for d, n, role, minutes in running if d == directive]
        rows.append((directive, classify(directive, nxt, running_orders, today, open_ids, now), mine, nxt))
    return rows


def front_fields(page):
    """The page's front-matter fields, each value stripped of quotes and in lower case, or {} with no front matter."""
    try:
        with page.open(encoding="utf-8", errors="replace") as f:
            return fields_of(f)
    except OSError:
        return {}


def fields_of(lines):
    """front_fields of these lines: a page's open file, or a text's lines (a page as git holds it)."""
    lines = iter(lines)
    if next(lines, "").strip() != "---":
        return {}
    fields = {}
    for line in lines:
        if line.strip() == "---":
            return fields
        pair = FRONT_KEY.match(line)
        if pair:
            fields[pair.group(1)] = pair.group(2).strip().strip("'\"").lower()
    return {}


def backlog_page(page):
    """True when the page's front matter has `backlog: true` and its status isn't superseded or archived."""
    fields = front_fields(page)
    return fields.get("backlog") == "true" and fields.get("status") not in ("superseded", "archived")


def backlog_rows(text):
    """[(line number, #, item, status, waits, order)] for each row of each table whose header names BACKLOG_COLUMNS."""
    found, columns = [], None
    for number, line in enumerate(text.splitlines(), 1):
        if not line.lstrip().startswith("|"):
            columns = None
            continue
        row = [c.strip() for c in re.split(r"(?<!\\)\|", line.strip()[1:].removesuffix("|"))]
        named = [c.lower() for c in row]
        if all(c in named for c in BACKLOG_COLUMNS):
            columns = [named.index(c) for c in BACKLOG_COLUMNS]
        elif columns and len(row) > max(columns) and not all(re.fullmatch(r":?-+:?", c) for c in row):
            found.append((number, *(row[i] for i in columns)))
    return found


def backlog(knowledge, running, today, open_ids=(), now=None, unread=None):
    """[(ref, state, item, order, waits)] for each row of each backlog page that isn't done or cancelled (module
    docstring), pages by path; ref is `<page>#<row id>`, the page's path from the repo's root. Each backlog page with
    no row the scan can read goes into the list unread, if given, as that path."""
    running_orders = {(d, n) for d, n, _, _ in running if d}
    rows = []
    for page in sorted(knowledge.rglob("*.md")):
        rel = page.relative_to(knowledge)
        if rel.parts[0] in BACKLOG_SKIP or not backlog_page(page):
            continue
        try:
            text = page.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        path = f"{knowledge.name}/{rel.as_posix()}"
        table = backlog_rows(text)
        if not table and unread is not None:
            unread.append(path)
        for number, row_id, item, status, waits, order in table:
            if status.strip("*_ ").lower().startswith(CLOSED):  # as the directives table's
                continue
            waits = "" if waits in DASH else waits
            if PAUSED.match(waits) or classify(None, ("", item, waits), running_orders, today, open_ids, now) != "IDLE":
                state = "WAITS"  # a hard wait first, whoever runs its order
            elif any((d, n) in running_orders or (d, None) in running_orders for d, n in ORDER_ID.findall(order)):
                state = "RUNNING"
            else:
                state = "IDLE"
            rows.append((f"{path}#{row_id.strip('*# ') or f'L{number}'}", state, item, order, waits))
    return rows


def signoffs(designs):
    """[(DD-<n>, title, status)] for each DD-*.md in the designs folder, by name, whose first `**Design status:**`
    value starts with awaiting-ceo (module docstring), the title without a leading DD-<n>."""
    found = []
    for page in sorted(designs.glob("DD-*.md")):
        try:
            text = page.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        status = DESIGN_STATUS.search(text)
        if not status or not status.group(1).lstrip("`*_ ").lower().startswith(SIGNOFF):
            continue
        dd = re.match(r"DD-\d+", page.name)
        dd = dd.group() if dd else page.stem
        head = text.split("\n---", 1)[0] if text.startswith("---\n") else ""
        title = re.search(r"^title:[ \t]*(.*)$", head, re.M)
        lead = re.compile(rf"^{re.escape(dd)}(?!\d)[:\s-]*")
        title = lead.sub("", title.group(1).strip().strip("'\"") if title else "") or lead.sub("", page.stem)
        found.append((dd, title, status.group(1).strip()))
    return found


def unhandled_answers(answers_dir, directives_dir, keep_flagged=False):
    """[(R-id, ask id)], by number, for each row of the answers pages (`<YYYY-Www>.md`) that no row of a directive's
    status log names by its R-id and its ask id together (`ASK 1 b9 A-<n> R-<n>: taken`, or the row quoted; a note to
    the CEO's as `R-<n> Note`, a row the Board added to Q&A as `R-<n> Q&A`, one added to Directives as `R-<n> New
    directive`, the two side by side), its archives'
    included (module docstring). Both, since the logs name other R-ids too (a design's risk, say). A row an ANSWERS TAMPERED
    line names (answers_seal, for the checkout answers_dir is in) is left out, never shown as the Board's answer,
    unless keep_flagged (board_desk.clean(): such a row's Notion row stays)."""
    named = set()
    for page in sorted(directives_dir.glob("D-*.md")):
        inside = False
        for line in page.read_text(encoding="utf-8", errors="replace").split("\n"):
            if re.match(r"#{1,6} ", line):
                inside = bool(STATUS_LOG.match(line))
            elif inside and line.startswith("|"):
                asks = ASK_ID.findall(line)
                named.update((r_id, ask) for r_id in R_ID.findall(line) for ask in asks)
                named.update((r_id, "Note") for r_id in NOTE_ID.findall(line))
                named.update((r_id, "Q&A") for r_id in QA_ROW_ID.findall(line))
                named.update((r_id, "New directive") for r_id in NEW_DIRECTIVE_ID.findall(line))
    found = {}
    for page in sorted(answers_dir.glob("*-W*.md")):
        for line in page.read_text(encoding="utf-8", errors="replace").split("\n"):
            row = ANSWER_ROW.match(line)
            if row and (row.group(1), row.group(2)) not in named:
                found[row.group(1)] = row.group(2)
    if found and not keep_flagged:
        for r_id in answers_seal.report(answers_dir.parent.parent.parent)[1]:
            found.pop(r_id, None)
    return sorted(found.items(), key=lambda item: int(item[0][2:]))


def listed(text, at):
    """([(full id, short id, n, sub-id)], end) for the orders the list at text[at:] names: `/2`, `cfa/7`, `/23 (Blue,
    A), /24 and /25`, `D-<id>/9-/16` (a range: /9 to /16, each with the first one's id)."""
    found, span = [], False
    while True:
        ref = REF.match(text, at)
        if not ref:
            break
        full, short, n = ref.group(1), ref.group(2), int(ref.group(3))
        if span and found:
            first = found[-1]
            full, short = (full, short) if full or short else first[:2]
            found += [(first[0], first[1], m, "") for m in range(first[2] + 1, min(n, first[2] + 50))]
        found.append((full, short, n, ref.group(4)))
        note = NOTE.match(text, ref.end())
        at = note.end() if note else ref.end()
        sep = LIST_SEP.match(text, at)
        if not sep or not REF.match(text, sep.end()):
            break
        span, at = bool(sep.group(1)), sep.end()
    return found, at


def own(directive, full, short):
    """True when an order reference in the directive's own log names one of its orders: its full id, its short id, its
    slug's tail (`map-view/6` in D-20260101-demo-map-view's log) or a bare `/n`."""
    return full == directive if full else short in (None, short_id(directive)) or directive.endswith(f"-{short}")


def due_time(found, day):
    """(epoch time, word) for a DUE match: its own date or else day (a row's), or None with neither."""
    day = found.group(2) or day
    try:
        at = datetime.fromisoformat(f"{day}T{found.group(3)}:{found.group(4)}:00+00:00") if day else None
    except ValueError:  # 2026-02-31
        return None
    return (at.timestamp(), found.group(1).lower()) if at else None


def row_time(text, day):
    """The epoch time of the first UTC time a row's text names (`15:10Z`, `15:10:30Z`, `2026-01-07T15:10:30Z`) on its
    own date or else day (the row's), or None with none."""
    found = ROW_TIME.search(text)
    try:
        return datetime.fromisoformat(f"{found.group(1) or day}T{found.group(2)}:{found.group(3)}:"
                                      f"{found.group(4) or '00'}+00:00").timestamp() if found else None
    except ValueError:  # 2026-02-31
        return None


def log_row(directive, day, event, due, done, closed=None, reopened=None):
    """Reads one status-log row's ORDER, ORDERS, RULING, REPORT and CLOSED mentions into due ({n: (time, word)}) and
    done (order_log); and, when given, a CLOSED row's orders alone into closed (cq_archive's --all), and into reopened
    ({n: the row's time, row_time, or None}) each done order a row starting RULING reopens for a fix round, until a
    DONE or CLOSED row."""
    plain = QUOTED.sub(lambda span: " " * len(span.group()), event)  # same length, so offsets hold
    marks = list(MENTION.finditer(plain))
    for i, mark in enumerate(marks):
        refs, at = listed(plain, mark.end())
        mine = [str(n) for full, short, n, sub in refs if own(directive, full, short) and not sub]
        segment = event[at:marks[i + 1].start() if i + 1 < len(marks) else len(event)]
        first = ROW_LEAD.match(plain[:mark.start()])  # the row starts with it, after at most a role word
        if mark.group(1) == "REPORT":
            state = REPORT_STATE.search(segment)
            if state and state.group(1) == "DONE":
                done.update(mine)
                for n in mine if reopened is not None else ():
                    reopened.pop(n, None)
        elif mark.group(1) == "CLOSED":
            if first:
                done.update(mine)
                if closed is not None:
                    closed.update(mine)
                for n in mine if reopened is not None else ():
                    reopened.pop(n, None)
        elif mark.group(1) != "RULING" or first:
            if reopened is not None and mark.group(1) == "RULING" and FIX_ROUND.search(plain):
                reopened.update((n, row_time(plain, day)) for n in mine if n in done)
            times = [t for t in (due_time(m, day) for m in DUE.finditer(segment)) if t]
            if times:
                due.update((n, max(times)) for n in mine)


def order_log(directives_dir, directive, closed=None, reopened=None):
    """({n: (due time, its word)}, {n with a REPORT DONE or CLOSED row}) for the directive's own orders, read from its
    archives by number, then its file (module docstring): the latest due time a row logs counts, else its order
    block's, so a ruling's new deadline a sweep moved to an archive still beats the block's first one. closed, when
    given, gets each n with a CLOSED row, and reopened each n reopened since its last DONE (log_row)."""
    archives = sorted(directives_dir.glob(f"{directive}-archive-*.md"),
                      key=lambda page: int(re.sub(r"\D", "", page.stem.rpartition("-")[2]) or 0))
    due, done, blocks = {}, set(), {}
    for page in archives + [directives_dir / f"{directive}.md"]:
        try:
            lines = page.read_text(encoding="utf-8", errors="replace").split("\n")
        except OSError:
            continue
        inside = page in archives  # an archive's rows may sit right under its title
        for number, line in enumerate(lines):
            if re.match(r"#{1,6} ", line):
                inside = bool(STATUS_LOG.match(line)) or (page in archives and line.startswith("# "))
            row = LOG_ROW.match(line) if inside else None
            if row:
                log_row(directive, row.group(1), row.group(2), due, done, closed, reopened)
                continue
            head = re.match(r"[#\s]*(?=ORDER )", line)
            ref = REF.match(line, head.end() + len("ORDER ")) if head and ORDER.match(line, head.end()) else None
            if not ref or ref.group(1) != directive or ref.group(4):
                continue
            block = [line]  # a header and its block: to the next heading, fence or table row
            for after in lines[number + 1:]:
                if after.lstrip().startswith(("#", "```", "|")):
                    break
                block.append(after)
            times = [t for t in (due_time(m, None) for m in DUE.finditer("\n".join(block))) if t]
            if times:
                blocks[ref.group(3)] = max(times)
    return {**blocks, **due}, done


def handed_back(log):
    """True when the transcript's last hand-back (a SubagentHandback call) comes after the last message that woke or
    reached the agent (its manager's, a child's or a background task's): it reported, and nothing has woken it since."""
    try:
        data = log.read_bytes()
    except OSError:
        return False
    return data.rfind(HANDED_BACK) > max(data.rfind(mark) for mark in WOKEN_BY)


def stalled(directives_dir, root, now, open_ids):
    """[(kind, directive id, n, since, what)] for each LATE, NO MANAGER and ENDED OPEN order of the open directives
    (module docstring), by directive, order and kind; since is an epoch time."""
    logs = {d: order_log(directives_dir, d) for d in open_ids}
    found = {}
    for d, (due, done) in logs.items():
        for n, (at, word) in due.items():
            if n not in done and at <= now:
                found[("LATE", d, n)] = (at, f"its {word} passed with no REPORT DONE logged")
    metas, cache, recent, alive = {}, {}, [], {}

    def meta(folder, agent_id):
        if (folder, agent_id) not in metas:
            try:
                info = json.loads((folder / f"agent-{agent_id}.meta.json").read_text())
                at = (folder / f"agent-{agent_id}.jsonl").stat().st_mtime
            except (OSError, ValueError):
                info, at = None, None
            metas[(folder, agent_id)] = (info if isinstance(info, dict) else None, at)
        return metas[(folder, agent_id)]

    for path in sorted(root.glob("*/subagents/agent-*.meta.json")):
        agent_id = path.name[len("agent-"):-len(".meta.json")]
        try:
            if now - path.with_name(f"agent-{agent_id}.jsonl").stat().st_mtime > ENDED_FOR:
                continue
        except OSError:
            continue
        info, at = meta(path.parent, agent_id)
        if info:
            log = path.with_name(f"agent-{agent_id}.jsonl")
            recent.append((path.parent, agent_id, info, at, now - at <= RUNNING_FOR and runs(info, log)))
    running = {(folder, agent_id) for folder, agent_id, _, _, on in recent if on}
    lane = {}  # (folder, agent id): the latest write by it or any agent under it, of the recent ones
    for folder, agent_id, _, at, _ in recent:
        key, seen = (folder, agent_id), set()
        while key not in seen and len(seen) < 7:  # it and up to 6 managers above it
            seen.add(key)
            lane[key] = max(lane.get(key, at), at, meta(*key)[1] or at)
            parent = (meta(*key)[0] or {}).get("parentAgentId")
            if not parent:
                break
            key = (folder, parent)

    def is_alive(folder, agent_id):
        """Running, or not stopped by the user, not handed back since last woken, and written in the
        last ALIVE_FOR by it or an agent under it: a manager that ended its turn to wait on its children is parked."""
        key = (folder, agent_id)
        if key not in alive:
            info = meta(*key)[0]
            alive[key] = key in running or (bool(info) and not info.get("stoppedByUser")
                                            and now - lane.get(key, meta(*key)[1] or 0) <= ALIVE_FOR
                                            and not handed_back(folder / f"agent-{agent_id}.jsonl"))
        return alive[key]

    carried = {}  # (directive id, n): the roles of the live agents on it
    for folder, agent_id in lane:
        if is_alive(folder, agent_id):
            role = (meta(folder, agent_id)[0] or {}).get("agentType") or "agent"
            for d, n, *_ in orders_of(folder, agent_id, cache):
                carried.setdefault((d, n), set()).add(role)
    for folder, agent_id, info, at, on in recent:
        role, parent = info.get("agentType"), info.get("parentAgentId")
        if on and role in WORKERS and parent and meta(folder, parent)[0] and not is_alive(folder, parent):
            since = meta(folder, parent)[1]
            for d, n, *_ in orders_of(folder, agent_id, cache):
                roles = carried.get((d, n), set())
                if d in logs and n and n not in logs[d][1] and roles <= set(WORKERS):
                    key = ("NO MANAGER", d, n)
                    found[key] = (min(since, found[key][0]) if key in found else since,
                                  f"only {', '.join(sorted(roles))} run it, and the manager that started them has "
                                  "handed back or was stopped")
        elif role in MANAGERS and not is_alive(folder, agent_id):
            last = lane.get((folder, agent_id), at)
            for d, n, *_ in orders_of(folder, agent_id, cache):
                if d in logs and n and n not in logs[d][1] and (d, n) not in carried:
                    key = ("ENDED OPEN", d, n)
                    found[key] = (max(last, found[key][0]) if key in found else last,
                                  f"its {role} handed back, was stopped or went quiet with its agents for "
                                  f"{ALIVE_FOR // 3600} hours, with no REPORT DONE logged, and no agent runs it")
    order = {d: i for i, d in enumerate(open_ids)}
    return [(kind, d, n, since, what) for (kind, d, n), (since, what) in
            sorted(found.items(), key=lambda item: (order[item[0][1]], int(item[0][2]), item[0][0]))]


def question_pages(workspaces):
    """[(product, page)] for each product's content/ceo-questions.md under workspaces/, then each of its orders' files
    under content/orders/ and content/orders-closed/ (module docstring), by product."""
    pages = []
    for content in sorted(workspaces.glob("*/content")):
        found = [content / "ceo-questions.md"] if (content / "ceo-questions.md").is_file() else []
        for folder in ORDER_FILES:
            found += sorted((content / folder).glob("*/*/ceo-questions.md"))
        pages += [(content.parent.name, page) for page in found]
    return pages


def in_orders(page):
    """Whether a page sits in content/orders/*/* or content/orders-closed/*/*."""
    return len(page.parts) >= 5 and page.parts[-4] in ORDER_FILES and page.parts[-5] == "content"


def page_order(page):
    """The order an order's file is for, `<directive id>/<n>` from its path, or None for a product's own file or one
    whose folders aren't so named (a STRAY)."""
    if in_orders(page) and all(name.fullmatch(part) for name, part in zip(ORDER_PATH, page.parts[-3:-1])):
        return f"{page.parts[-3]}/{page.parts[-2]}"
    return None


def page_group(page):
    """Whose replies a question file, or the archive beside it, holds: None for a product's own file, else its order
    (page_order), or its folder for an order's file whose folders aren't so named. A reply answers an ask in its own
    group or in a product's own file; one in a product's own file answers any."""
    if not in_orders(page):
        return None
    return page_order(page) or str(page.parent)


def page_place(page):
    """The page's path from its product's content/ folder: `ceo-questions.md`, `orders/<id>/<n>/ceo-questions.md`."""
    return "/".join(page.parts[-4:]) if in_orders(page) else page.name


def stray_pages(workspaces):
    """Each ceo-questions.md under workspaces/ outside the layout (module docstring), as its path from workspaces/."""
    found = set(workspaces.glob("*/ceo-questions.md")) | set(workspaces.glob("*/content/*/ceo-questions.md")) \
        | set(workspaces.glob("*/content/*/*/ceo-questions.md"))
    for folder in ORDER_FILES:
        found |= set(workspaces.glob(f"*/content/{folder}/*/*/*/ceo-questions.md"))
        found |= {page for page in workspaces.glob(f"*/content/{folder}/*/*/ceo-questions.md") if not page_order(page)}
    return sorted(str(page.relative_to(workspaces)) for page in found if page.is_file())


def by_ceo(text):
    """Whether a reply's first line is the CEO's own (module docstring): it starts `CEO`. `HANDLED (CEO RULING /1/2 (3);
    COPY-CHECK 07:10:30Z) Q /1.CTO ... (CTO, ...)` is the CTO's; so is `HANDLED (CEO, RULING /1/2 (3)) ...`, which an
    agent may write."""
    return bool(CEO_LEAD.match(text.split("\n", 1)[0]))


def goes_on(line):
    """Whether a line continues the reply above it: an indented, numbered or `(` line (GOES_ON) with no writer field
    of its own (OWN_FIELD, NEAR_FIELD, DASH_FIELD) and no role word first (ROLE_FIRST): an agent's line glued under the
    CEO's isn't the CEO's. Each test only cuts a line GOES_ON joined, so a reply only shortens."""
    return (bool(GOES_ON.match(line)) and not OWN_FIELD.search(line) and not NEAR_FIELD.search(line)
            and not DASH_FIELD.search(line) and not ROLE_FIRST.match(line))


def misfiled(pages, every=False, tied=None):
    """[(product, place, line number, word, ref, the order the file or heading is for)] for each line whose word is
    followed by another order's ref: in an order's file, against its order; in a product's own file, against the
    `## ORDER` heading it sits under (the measure, scripts/cq_measure.py; the scan prints only order files'). COORD and
    ANSWER lines count only with every. tied, a list, gets each line checked."""
    found = []
    for product, page in pages:
        try:
            lines = page.read_text(encoding="utf-8", errors="replace").split("\n")
        except OSError:
            continue
        own, here = page_order(page), None
        for i, line in enumerate(lines):
            if not own and re.match(r"#{1,2} ", line):
                heading = LISTED_ORDER.search(line)
                here = f"{heading.group(1)}/{heading.group(2)}" if heading else None
                continue
            mine, word = own or here, OWN_REF.match(line)
            if not word or not mine or word.group(2)[0] not in "/D" or (word.group(1) in ELSEWHERE and not every):
                continue  # `cfa/7`: a short id the line's own text can't tie to a directive
            ref = word.group(2) if word.group(2).startswith("D-") else mine.rsplit("/", 1)[0] + word.group(2)
            if tied is not None:
                tied.append((product, page_place(page), i + 1))
            if ref != mine:
                found.append((product, page_place(page), i + 1, word.group(1), word.group(2), mine))
    return found


def replies(lines):
    """[(index, text)] for each RULING, HANDLED or ANSWER line, or one marking ACTED, with the indented or numbered
    lines that continue it (a ruling's `(1) QUESTION /1.WS-4.q2: yes.`), up to one with its own writer field or a role
    word first (goes_on)."""
    found, block = [], None
    for i, line in enumerate(lines):
        if REPLIED.match(line):
            block = [i, line]
            found.append(block)
        elif block and line.strip() and goes_on(line):
            block[1] += "\n" + line
        else:
            block = None
    return [tuple(block) for block in found]


def cited(text):
    """(A reply's text less its own time, that time as an epoch time, or None with no date or an `x` minute: `08:0xZ`
    can't be ordered). Its own time is the first on its first line when no ask's word comes before it (`RULING /1/5
    17:50Z (CEO), on NEEDS-CEO-NOW /1.CTO 17:50Z`, `HANDLED /1.CTO 2026-01-16T17:50Z (CTO)`)."""
    first = text.split("\n", 1)[0]
    stamp, word = OWN_STAMP.search(first), ASK_WORD.search(first)
    if not stamp or (word and word.start() < stamp.start()):
        return text, None
    day, hour, minute, second = stamp.groups()
    try:
        at = day and "x" not in minute and datetime.fromisoformat(f"{day}T{hour}:{minute}:{second or '00'}+00:00")
    except ValueError:  # 2026-02-31
        at = None
    blank = text[:stamp.start()] + " " * (stamp.end() - stamp.start()) + text[stamp.end():]
    return blank, at.timestamp() if at else None


def unanswered(pages, now):
    """[(product, kind, ref, stamp, line number, since, place)] for each NEEDS-CEO-NOW, NEEDS-CTO or QUESTION line, and
    each COORD line to the CEO, that no RULING, HANDLED, ANSWER or ACTED line of its product cites ANSWER_IN after its
    time: one of its page, by place or below it, or one of another of the product's files or of an archive beside any
    of them, by a date, an order's file's only for that file and the product's own (page_group; module docstring); a
    NEEDS-CEO-NOW or a QUESTION to the CEO only by the CEO's own (by_ceo). By product, page and line; since is an
    epoch time, place the page's path from content/ (page_place)."""
    # said: product's [(page or archive, index, text less its own time, that time, whether it is the CEO's)]
    read, said, archives = {}, {}, {}
    for product, page in pages:
        try:
            read[page] = page.read_text(encoding="utf-8", errors="replace").split("\n")
        except OSError:
            continue
        said.setdefault(product, []).extend(
            (page, i, *cited(text), by_ceo(text)) for i, text in replies(read[page]))
        archives.setdefault(product, {}).setdefault(page.with_name(f"{page.stem}-archive.md"), None)
    for product, kept in archives.items():  # archived replies cite only by a date, as another file's do
        for archive in kept:
            try:
                text = archive.read_text(encoding="utf-8", errors="replace").split("\n")
            except OSError:
                continue
            said[product] += [(archive, None, *cited(reply), by_ceo(reply)) for _, reply in replies(text)]
    found = []
    for product, page in pages:
        if page not in read:
            continue
        lines = read[page]
        group = page_group(page)  # a reply in an order's file answers only there and in the product's own file
        here = [(i if other == page else None, text, when, ceo) for other, i, text, when, ceo in said[product]
                if group is None or page_group(other) in (None, group)]
        asks = [(i, ASKED.match(line)) for i, line in enumerate(lines) if ASKED.match(line)]
        tails = Counter(ask.group(3) for _, ask in asks if ask.group(3))
        # asks a reply names by place, a ruling right above "on the line below" or below "above"; and those the CEO's
        # own reply names so
        placed, led_place = set(), set()
        for i, text, _, ceo in here:
            for words, step in (("line below", 1), ("line above", -1)):
                if i is not None and words in text.split("\n", 1)[0]:
                    k = i + step
                    while 0 <= k < len(lines) and (not lines[k].strip() or REPLIED.match(lines[k])
                                                   or goes_on(lines[k])):
                        k += step
                    placed.add(k)
                    (led_place if ceo else set()).add(k)
        for i, ask in asks:
            kind = "COORD" if ask.group(1).startswith("COORD") else ask.group(1)
            stamp = ASK_STAMP.search(lines[i])
            to_ceo = kind == "NEEDS-CEO-NOW" or (kind == "QUESTION" and bool(TO_CEO.search(lines[i][:400])))
            if not stamp or (kind == "COORD" and not TO_CEO.search(lines[i][:400])):
                continue
            day, hour, minute, second = stamp.groups()
            try:
                at = datetime.fromisoformat(f"{day}T{hour}:{minute.replace('x', '9')}:{second or '00'}+00:00")
            except ValueError:  # 2026-02-31
                continue
            at, wait = at.timestamp(), ANSWER_IN.get(kind, ANSWER_WITHIN)
            if i in (led_place if to_ceo else placed):
                continue
            if now < at + wait:
                continue
            tail = ask.group(3)
            named = tail and rf"{re.escape(tail)}(?![\w/-]|\.[\w-])"
            # its ref (or, with none, its word), a few letters, then its time, its own date or none before it
            cite = re.compile((named or ("COORD(?:INATION)?" if kind == "COORD" else re.escape(kind)))
                              + rf"[^\n/\d]{{0,24}}?(?P<day>{re.escape(day)}[T ])?{re.escape(f'{hour}:{minute}')}"
                              r"(?::[0-5]\d)?(?:\.\d+)?Z")
            exact = second and re.compile(rf"(?<![\d:]){hour}:{minute}:{second}(?:\.\d+)?Z")  # 09:30:30Z
            one = bool(named) and tails[tail] == 1 and tail.count(".") >= 2  # an ask's own id: /1.CTO.q1
            # after it: by the reply's own dated time, else below it on the page; a cite with its date is after it;
            # never the ask's own line, which counts as a reply when it marks ACTED (`... ACTED: /1.CTO.r25`)
            if any(any(m.group("day") for m in cite.finditer(text))
                   or ((when >= at if when is not None else j is not None and j > i)
                       and (cite.search(text) or (exact and exact.search(text)) or (one and re.search(named, text))))
                   for j, text, when, ceo in here if j != i and (not to_ceo or ceo)):
                continue
            found.append((product, kind, ask.group(2), f"{day}T{hour}:{minute}Z", i + 1, at + wait, page_place(page)))
    return found


def desk_job_loaded():
    """Whether launchd has the desk's read job (`launchctl list <label>` exits 0); False off a Mac, and with no desk
    in company.json."""
    if BOARD_DESK is None:
        return False
    try:
        return subprocess.run(["launchctl", "list", DESK_JOB], capture_output=True, timeout=5).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def desk(log, now, loaded):
    """[("DESK STALE", the last read or push line's time, or None)] when none is under DESK_QUIET old, else []; []
    while the read job isn't loaded (module docstring)."""
    if not loaded:
        return []
    try:
        with open(log, "rb") as file:
            file.seek(max(0, file.seek(0, os.SEEK_END) - DESK_TAIL))
            text = file.read().decode("utf-8", "replace")
    except OSError:
        text = ""
    last = None
    for line in text.splitlines():
        found = DESK_LINE.match(line)
        if found:
            try:
                last = datetime.fromisoformat(found.group(1)).replace(tzinfo=timezone.utc).timestamp()
            except ValueError:  # 2026-02-31T10:00
                continue
    return [("DESK STALE", last)] if last is None or now - last > DESK_QUIET else []


def git(repo, *args, stdin=None):
    """A read-only git command's output in repo, as text, or as bytes when stdin (bytes) is given; raises on a
    failure, so the caller's detector fault names it."""
    run = subprocess.run(["git", "-C", str(repo), *args], input=stdin, capture_output=True, text=stdin is None,
                         timeout=GIT_TIMEOUT)
    if run.returncode != 0:
        raise RuntimeError(f"git {args[0]} failed: {str(run.stderr).strip()[:200]}")
    return run.stdout


def last_checked(text):
    """(date, epoch time or None, `main`'s commit or None) from a page's "Last checked" line (module docstring), or
    None when it has none or its date can't be read. A time with no zone is the Board's (BOARD_TZ); `Z` or `UTC`
    is UTC. A time without seconds is the end of its minute (+59 s), as newest_deploy reads `1x` as its latest minute:
    the page is refreshed right after the deploy it names."""
    line = LAST_CHECKED.search(text)
    found = CHECKED_AT.match(line.group(1).lstrip("*_ \t")) if line else None
    if not found:
        return None
    try:
        day, at = date.fromisoformat(found.group(1)), None
        if found.group(2):
            utc = found.group(5) == "UTC" or found.group(0).rstrip().endswith("Z")
            at = datetime(day.year, day.month, day.day, int(found.group(2)), int(found.group(3)),
                          int(found.group(4) or 59), tzinfo=timezone.utc if utc else BOARD_TZ).timestamp()
    except ValueError:  # 2026-02-31
        return None
    sha = CHECKED_SHA.search(line.group(1))
    return day, at, sha.group(1) if sha else None


def newer(when, day, at):
    """Whether an epoch time is after a "Last checked": its time, or with a date alone, a later date in UTC."""
    return when > at if at is not None else utc_today(when) > day


def system_change(repo, since=None):
    """(commit, epoch time, exact) for the newest commit on HEAD that touches SYSTEM_PATHS: of those after since (a
    commit git knows) when given, exact True; else the newest of all, exact False; or None."""
    if since:
        try:
            out = git(repo, "log", "-1", "--format=%H %ct", f"{since}..HEAD", "--", *SYSTEM_PATHS).split()
            return (out[0], float(out[1]), True) if out else None
        except RuntimeError:  # a commit this clone doesn't have: by the time instead
            pass
    out = git(repo, "log", "-1", "--format=%H %ct", "HEAD", "--", *SYSTEM_PATHS).split()
    return (out[0], float(out[1]), False) if out else None


def newest_deploy(workspaces, product):
    """(stamp, epoch time, place, line number) of the newest DEPLOY DONE line of the product's question files and the
    archives beside them (question_pages), by the line's first dated time, or None."""
    best = None
    for owner, page in question_pages(workspaces):
        if owner != product:
            continue
        for path in (page, page.with_name(f"{page.stem}-archive.md")):
            try:
                lines = path.read_text(encoding="utf-8", errors="replace").split("\n")
            except OSError:
                continue
            for i, line in enumerate(lines):
                stamp = ASK_STAMP.search(line) if DEPLOYED.match(line) else None
                if not stamp:
                    continue
                day, hour, minute, second = stamp.groups()
                try:  # `21:1xZ` as its latest minute
                    at = datetime.fromisoformat(f"{day}T{hour}:{minute.replace('x', '9')}:{second or '00'}+00:00")
                except ValueError:  # 2026-02-31
                    continue
                if best is None or at.timestamp() > best[1]:
                    best = (stamp.group(), at.timestamp(), page_place(path), i + 1)
    return best


def stale_pages(knowledge, workspaces, repo, today):
    """[(path, its "Last checked" as read or None, [reasons])] for each big-picture page (front matter `big_picture:
    true`, not superseded or archived, nor in research/ or _templates/) that is behind (module docstring), by path."""
    found = []
    for page in sorted(knowledge.rglob("*.md")):
        rel = page.relative_to(knowledge)
        fields = front_fields(page) if rel.parts[0] not in BACKLOG_SKIP else {}
        if fields.get("big_picture") != "true" or fields.get("status") in ("superseded", "archived"):
            continue
        path = f"{knowledge.name}/{rel.as_posix()}"
        checked = last_checked(page.read_text(encoding="utf-8", errors="replace"))
        if not checked:
            found.append((path, None, ['its "Last checked" line can\'t be read: write "**Last checked:** <YYYY-MM-DD>, '
                                       '<HH:MM>, against ..."']))
            continue
        day, at, sha = checked
        shown = board_time(at) if at is not None else str(day)
        why = [f"more than {PAGE_DAYS} days old"] if (today - day).days > PAGE_DAYS else []
        product = fields.get("product")
        if product:
            deploy = newest_deploy(workspaces, product)
            if deploy and newer(deploy[1], day, at):
                why.append(f"{product}'s production deploy of {deploy[0]} (DEPLOY DONE, {deploy[2]}:{deploy[3]}) "
                           "came after it")
        elif rel.as_posix() == SYSTEM_PAGE:
            change = system_change(repo, sha)
            if change and (change[2] or newer(change[1], day, at)):
                moment = datetime.fromtimestamp(change[1], timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                since = f" since `main` at {sha}" if change[2] else ""
                why.append(f"system change {change[0][:8]} ({moment}) landed after it{since}")
        else:
            why.append("it names no `product: <id>` (a workspaces/ folder), so the scan can't tell which deploys it "
                       "describes: its owner adds one")
        if why:
            found.append((path, shown, why))
    return found


def event_at(found):
    """The epoch time of an EVENT_AT match, the Board's, at its earliest (`20:1x` as 20:10, a date alone as its day's
    start), or None when there's no match or no such date."""
    if not found:
        return None
    day, hour, minute = found.groups()
    try:
        return datetime.fromisoformat(f"{day}T{hour or '00'}:{(minute or '00').replace('x', '0')}:00").replace(
            tzinfo=BOARD_TZ).timestamp()
    except ValueError:  # 2026-02-31
        return None


def latest(*times):
    """The latest of the epoch times given that aren't None, or None: a close is no earlier than its own ask."""
    return max((t for t in times if t is not None), default=None)


def desk_state(texts):
    """({Q-ids}, {ask id: closed}, {directive ids with a file}, {directive id: done}, {(id, kind): the event's time as
    its record gives it}) from {path under knowledge/: text} (module docstring): done from the directives table's
    Status, as open_directives reads it."""
    answered, asks, files, done, times = set(), {}, set(), {}, {}
    for rel, text in texts.items():
        if rel.startswith("company/board-desk/qa"):
            answered.update(QA_HEAD.findall(text))
        elif rel.startswith("company/board-desk/asks"):  # asks.md and its asks-archive-*.md pages
            for ask, status, rest in ASK_HEAD.findall(text):
                ask, closed = ask.strip(), status.lower() in ASK_CLOSED
                asks[ask] = asks.get(ask, False) or closed
                times[ask, "New ask"] = event_at(re.search(r"·[ \t]*asked[ \t]+" + EVENT_AT, rest))
                if closed:
                    times[ask, "Ask closed"] = latest(event_at(re.match(r"[ \t]+" + EVENT_AT, rest)),
                                                      times[ask, "New ask"])
        elif rel == DIRECTIVES_TABLE:
            for line in text.splitlines():
                cells = [c.strip() for c in line.strip().strip("|").split("|")]
                found = re.match(r"\[(D-\d{8}-[a-z0-9-]+)\]", cells[0]) if len(cells) >= 4 else None
                if found:
                    done[found.group(1)] = cells[-2].lower().startswith(CLOSED)
                    times[found.group(1), "New directive"] = event_at(re.match(EVENT_AT, cells[-1]))
                    times[found.group(1), "Directive done"] = latest(event_at(re.search(EVENT_AT, cells[-2])),
                                                                     times[found.group(1), "New directive"])
        else:
            directive = DIRECTIVE_PAGE.fullmatch(rel)
            if (directive and not re.search(r"-archive-\d+$", directive.group(1))
                    and fields_of(text.splitlines()).get("status") != "archived"):
                files.add(directive.group(1))
    return answered, asks, files, done, times


def desk_events(base, now):
    """[(id, kind)] for each event between two desk_states, in the order the kinds are listed (module docstring)."""
    events = [(q, "Answered") for q in sorted(now[0] - base[0], key=lambda q: int(q[2:]))]
    for ask, closed in now[1].items():
        events += [(ask, "New ask")] if ask not in base[1] else []
        events += [(ask, "Ask closed")] if closed and not base[1].get(ask) else []
    for directive in sorted(now[2] | {d for d, done in now[3].items() if done}):
        events += [(directive, "New directive")] if directive in now[2] - base[2] else []
        events += [(directive, "Directive done")] if now[3].get(directive) and not base[3].get(directive) else []
    return events


def committed_desk(knowledge, before):
    """({path under knowledge/: text} of the desk's pages and the directives in the newest commit before the epoch
    time before, that commit's committer time), read with git (one log, one ls-tree, one cat-file), or ({}, None) when
    there's no such commit."""
    stamp = datetime.fromtimestamp(before, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    found = git(knowledge, "log", "-1", "--format=%H %ct", f"--before={stamp}", "HEAD").split()
    if not found:
        return {}, None
    base = found[0]
    prefix = knowledge.resolve().relative_to(Path(git(knowledge, "rev-parse", "--show-toplevel").strip()).resolve())
    names = git(knowledge, "ls-tree", "-r", "--name-only", "--full-tree", base, "--",
                f"{prefix.as_posix()}/company/board-desk", f"{prefix.as_posix()}/board/directives").split("\n")
    wanted = {name: name[len(prefix.as_posix()) + 1:] for name in names if name}
    wanted = {name: rel for name, rel in wanted.items() if DESK_PAGES.fullmatch(rel) or DIRECTIVE_PAGE.fullmatch(rel)}
    out = git(knowledge, "cat-file", "--batch", stdin="".join(f"{base}:{name}\n" for name in wanted).encode())
    texts, at = {}, 0
    for rel in wanted.values():  # each object: `<sha> blob <size>\n<bytes>\n`
        head = out.index(b"\n", at)
        size = int(out[at:head].split()[2])
        texts[rel] = out[head + 1:head + 1 + size].decode("utf-8", "replace")
        at = head + 1 + size + 1
    return texts, float(found[1])


def email_due(knowledge, now, log=None):
    """[(id, kind)] for each event from EMAIL_FROM on that no email logged in notify-log.jsonl from the base's time on,
    at or after the event's time, names (module docstring): the desk's pages and the directives under knowledge as
    they are now, against the base, the newest commit before EMAIL_FROM. One email quiets every event of its id before
    it. [] before EMAIL_FROM, and while it is off (None)."""
    if EMAIL_FROM is None or now < EMAIL_FROM:
        return []
    current = {}
    for page in sorted([*knowledge.glob("company/board-desk/*.md"), *knowledge.glob("board/directives/*.md")],
                       key=lambda page: page.stem):  # asks.md before its archives
        rel = page.relative_to(knowledge).as_posix()
        if DESK_PAGES.fullmatch(rel) or DIRECTIVE_PAGE.fullmatch(rel):
            current[rel] = page.read_text(encoding="utf-8", errors="replace")
    if not current:
        return []
    before, since = committed_desk(knowledge, EMAIL_FROM)
    log = log or main_checkout(knowledge.parent) / NOTIFY_LOG
    emails = []
    try:
        for line in Path(log).read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                sent = json.loads(line)
                when = datetime.fromisoformat(sent["time"].replace("Z", "+00:00")).timestamp()
            except (ValueError, KeyError, TypeError, AttributeError):
                continue
            if (since is None or when >= since) and isinstance(sent.get("subject"), str):
                emails.append((when, sent["subject"]))
    except OSError:
        pass
    now_state = desk_state(current)
    due = []
    for event, kind in desk_events(desk_state(before), now_state):
        at = now_state[4].get((event, kind))
        name = re.compile(rf"(?<![\w-]){re.escape(event)}(?![\w/-])")
        if not any((at is None or when >= at) and name.search(subject) for when, subject in emails):
            due.append((event, kind))
    return due


def start_now(rows, stack, signs=(), answers=(), stalls=(), asks=(), desk_lines=(), pages=(), emails=(), tampered=()):
    """The directives and backlog rows that have a step no agent is on, then the designs awaiting the CEO's sign-off,
    then the Board's answers the CEO hasn't logged, then the ANSWERS TAMPERED lines (by their subject), then the
    stalled orders, then the unanswered asks, then DESK STALE, then the big-picture pages that are behind, then the
    emails due to the Board: what "Start now" lists and the heartbeat fires on."""
    return ([d for d, state, _, _ in rows if state in ("IDLE", "NO NEXT")]
            + [ref for ref, state, *_ in stack if state == "IDLE"] + [dd for dd, *_ in signs]
            + [f"ANSWER {r_id} {ask}" for r_id, ask in answers] + [line.split(":")[0] for line in tampered]
            + [f"{kind} {d}/{n}" for kind, d, n, *_ in stalls]
            + [unanswered_id(*ask[:4]) for ask in asks] + [kind for kind, _ in desk_lines]
            + [f"STALE PAGE {path}" for path, *_ in pages] + [f"EMAIL DUE {event}: {kind}" for event, kind in emails])


def main_checkout(repo=None):
    """repo (REPO_ROOT by default), or, for a git worktree, the main checkout its .git file points to
    (`gitdir: <main>/.git/worktrees/<name>`, whose commondir is <main>/.git)."""
    repo = repo or REPO_ROOT
    try:
        gitdir = repo / (repo / ".git").read_text().split("gitdir:", 1)[1].strip()
        return (gitdir / (gitdir / "commondir").read_text().strip()).resolve().parent
    except (OSError, IndexError):  # .git is a folder (the main checkout), or isn't there
        return repo


def projects_root():
    """The folder of the main session's transcripts, the one the heartbeat takes from its transcript's path: the main
    checkout's, so a scan run from a worktree sees the CEO's agents too."""
    return token_report.projects_root(main_checkout())


def board_time(at):
    """An epoch time as the Board reads it: in its time zone, named (`2026-01-10 18:00 UTC`)."""
    return f"{datetime.fromtimestamp(at, BOARD_TZ):%Y-%m-%d %H:%M %Z}"


def format_row(directive, state, mine, nxt):
    parts = [f"{directive}  {state}"]
    if mine:
        parts.append("agents: " + ", ".join(
            (f"/{n} {role}" if n else f"{role} (path)") + (f" quiet {m}m" if m * 60 >= QUIET else "")
            for n, role, m in sorted(mine, key=lambda a: (a[0] is None, int(a[0] or 0)))))
    if nxt:
        step = nxt[1] if len(nxt[1]) <= 120 else nxt[1][:117] + "..."
        parts.append(f"NEXT ({nxt[0]}): {step}; waits: {nxt[2] or 'none'}")
    return " | ".join(parts)


def format_backlog(ref, state, item, order, waits):
    item = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", item).replace("**", "")  # a link's text, no bold
    parts = [f"BACKLOG {ref}  {state}", item if len(item) <= 80 else item[:77] + "..."]
    if order not in DASH:
        parts.append(f"order: {order}")
    parts.append(f"waits: {waits or 'none'}")
    return " | ".join(parts)


def format_signoff(dd, title, status):
    title, status = (re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text).replace("**", "") for text in (title, status))
    return (f"SIGNOFF {dd} {title if len(title) <= 60 else title[:57] + '...'}: "
            f"{status if len(status) <= 80 else status[:77] + '...'}")


def format_stall(kind, directive, n, since, what):
    return f"{kind} {directive}/{n} since {board_time(since)}: {what}"


def unanswered_id(product, kind, ref, stamp):
    return f"UNANSWERED {product} {kind}{f' {ref}' if ref else ''} {stamp}"


def format_unanswered(product, kind, ref, stamp, line, since, place="ceo-questions.md"):
    return (f"{unanswered_id(product, kind, ref, stamp)} since {board_time(since)}: no RULING, HANDLED, ANSWER or ACTED "
            f"line cites it ({place}:{line})")


def format_misfiled(product, place, line, word, ref, own):
    return (f"Warning: MISFILED {product} {place}:{line}: a {word} line of {ref}, in {own}'s file: it goes in its own "
            "order's file (ceo.md, \"While work runs\")")


def format_stray(path):
    return (f"Warning: STRAY workspaces/{path}: a ceo-questions.md outside the layout (content/ceo-questions.md and "
            "content/orders/<directive id>/<n>/ceo-questions.md): move its lines to their order's file and tell its "
            "writer")


def format_desk(kind, since):
    moment = f" since {board_time(since)}" if since else ""
    return (f"{kind}{moment}: {DESK_JOB} is loaded, but board-desk.log has no read or push line in the last "
            f"{DESK_QUIET // 60} minutes")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0],
                                     epilog='Exits 1 when "Start now" lists anything, else 0.')
    parser.add_argument("--mac", action="store_true", help="only the Mac's line; exit 1 when there's no room")
    parser.add_argument("--stalled", action="store_true",
                        help="only the LATE, NO MANAGER and ENDED OPEN lines; exit 1 when there's any")
    args = parser.parse_args(argv)
    if args.stalled:
        folder = projects_root()
        if not folder.is_dir():
            print(f"Agents: can't see them, no session folder at {folder}: only LATE lines below", file=sys.stderr)
        if CONFIG_FAULT:
            print(f"Warning: company.json can't be read or used ({CONFIG_FAULT}): times are UTC", file=sys.stderr)
        stalls = stalled(DIRECTIVES, folder, time.time(), open_directives((DIRECTIVES / "README.md").read_text()))
        for stall in stalls:
            print(format_stall(*stall))
        return 1 if stalls else 0
    room, line = mac_room()
    if args.mac:
        print(line)
        return 0 if room else 1
    now = time.time()
    folder = projects_root()
    seen = folder.is_dir()
    unread = []
    if CONFIG_FAULT:
        print(f"Warning: company.json can't be read or used ({CONFIG_FAULT}): times are UTC, and the desk and email "
              "checks are off")
    running = agents(folder, now, unread) if seen else []
    if not seen:
        print(f"Agents: can't see them, no session folder at {folder}: the states below count no running agent")
    rows = scan(DIRECTIVES, running, utc_today(now), now)
    for row in rows:
        print(format_row(*row))
        door = ignored_door(row[1], row[3])
        if door:
            print(f"Warning: {row[0]}'s NEXT row ({row[3][0]}) reads IDLE but names {door}, which the scan doesn't "
                  f"count as a door there: read it, and if it waits on the Board, write {door} first or after \", then\" "
                  f"(\"waits: /2, then {door}\")")
        data = data_wait(row[1], row[3])
        if data:
            print(f"Warning: {row[0]}'s NEXT row ({row[3][0]}) waits on {data} with no date first, so nothing wakes it: "
                  f"write the date it's due first (\"waits: 2026-01-10 08:30Z, ...\"), or the order that brings it "
                  f"(\"waits: /3, ...\")")
        try:
            stray = stray_next((DIRECTIVES / f"{row[0]}.md").read_text())
        except OSError:
            stray = None
        if stray:
            below = f"below its latest NEXT row ({row[3][0]})" if row[3] else "and it has no NEXT row"
            print(f"Warning: {row[0]}'s row of {stray} holds \"NEXT:\" mid-row, {below}: the scan reads only a "
                  f"row that starts with NEXT:, so if that step is current, give it its own row")
    no_rows = []
    stack = backlog(KNOWLEDGE, running, utc_today(now), [row[0] for row in rows], now, no_rows)
    for page in no_rows:
        print(f"Warning: {page} has `backlog: true` but no row the scan can read: its table's header needs the "
              f"columns \"| # | Item | Status | Size | Door | Waits | Order |\" (ceo.md, \"Capacity\")")
    for row in stack:
        print(format_backlog(*row))
        door = ignored_door(row[1], ("", "", row[4]))
        if door:
            print(f"Warning: {row[0]} reads IDLE but its Waits names {door}, which the scan doesn't count as a door "
                  f"there: read it, and if it waits on the Board, have its page's owner write {door} first or after "
                  f"\", then\" (\"D-<id>/<n>, then {door}\")")
    signs = signoffs(KNOWLEDGE / "engineering" / "designs")
    for sign in signs:
        print(format_signoff(*sign))
    for agent_id, role, order in sorted(unread, key=lambda a: (a[1], a[0])):
        where = f"under {order[0]}" + (f"/{order[1]}" if order[1] else " (path)") if order else "with no ORDER id"
        print(f"Warning: agent {agent_id} ({role}) has an ORDER header the scan can't read, so it counts {where}: "
              f"write it \"ORDER <id>/<n> (note)   from: <role>   to: <role>\" (CLAUDE.md, \"Message formats\")")
    loose = [role for d, _, role, _ in running if d is None]
    if loose:
        print(f"Running with no ORDER id: {len(loose)} ({', '.join(sorted(set(loose)))})")
    answers = unhandled_answers(KNOWLEDGE / "board" / "answers", DIRECTIVES)
    for r_id, ask in answers:
        print(f"ANSWER {r_id} {ask}")
    tampered, _, unchecked = answers_seal.report(KNOWLEDGE.parent, datetime.fromtimestamp(now, timezone.utc))
    for alarm in tampered + ([unchecked] if unchecked else []):
        print(alarm)
    stalls = stalled(DIRECTIVES, folder, now, [row[0] for row in rows])
    for stall in stalls:
        print(format_stall(*stall))
    pages = question_pages(WORKSPACES)
    asks = unanswered(pages, now)
    for ask in asks:
        print(format_unanswered(*ask))
    for line in misfiled([(product, page) for product, page in pages if page_order(page)]):
        print(format_misfiled(*line))
    for path in stray_pages(WORKSPACES):
        print(format_stray(path))
    stale = desk(DESK_LOG, now, desk_job_loaded())
    for item in stale:
        print(format_desk(*item))
    pages = stale_pages(KNOWLEDGE, WORKSPACES, REPO_ROOT, utc_today(now))
    for path, checked, why in pages:
        print(f"STALE PAGE {path}: last checked {checked or 'unreadable'}; {'; '.join(why)}")
    emails = email_due(KNOWLEDGE, now)
    for event, kind in emails:
        print(f"EMAIL DUE {event}: {kind}")
    print(line)
    idle = start_now(rows, stack, signs, answers, stalls, asks, stale, pages, emails, tampered)
    print("Start now (ceo.md, \"Capacity\"): " + (", ".join(idle) if idle else "none"))
    return 1 if idle else 0


if __name__ == "__main__":
    sys.exit(main())
