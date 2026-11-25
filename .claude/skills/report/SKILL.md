---
name: report
description: Use when the Board asks for status, a report, an update or "what's going on", or opens a CEO session with a greeting.
argument-hint: "[period, e.g. 'this week' or 'since 2026-01-01']"
---

# Status report for the Board

You are the CEO. Give the Board a short, true picture of the company. Writing the report changes nothing except a status you find wrong in your own pages. What's due comes after it (below): the idle work, which you start in the same turn; the sweep, which you run and commit unasked; and the drift audit. Period: $ARGUMENTS (default: the last 7 days, plus everything still open).

## Gather

1. `knowledge/board/directives/README.md`, then every directive file that isn't `done` or `cancelled`, plus those closed within the period.
2. Engineering evidence for in-flight and recent work, per product repo:
   `gh pr list --repo <owner>/<repo> --state all --limit 15 --json number,title,state,url,mergedAt,updatedAt`
3. Every "Open questions for the Board" entry that's still unanswered, and the open asks and Board steps in `knowledge/company/board-desk/asks.md` (`ceo.md`, "The desk"). An `ANSWER` line in the capacity scan (step 8) is an answer not yet acted on: act on it first. Never read the desk's `progress.md` or `summaries.md`: they retell the rows you read here.
4. KB health: run `python3 scripts/kb_lint.py` (its `sweep due` lines are the hot and cold check, below), and count open facts with `grep -rc "TODO(board)" knowledge --include="*.md"` (sum per top-level folder).
5. What was decided without the Board since the last report: the status logs' decisions, and new or changed lines in `knowledge/company/board-preferences.md` (`git log -p --since=<date> -- knowledge/company/board-preferences.md`).
6. The Board's load (`ceo.md`, "Asking the Board"): the last drift audit (`grep -rn "DRIFT AUDIT" knowledge/board/directives/`), the last one-word answer (`grep -rn "LOAD:" knowledge/board/directives/`), and the period's `ASK` rows and Board-active days (dates with a `board` row in any status log).
7. Cost and landings: `python3 scripts/token_report.py --since <period start>`, for each role's turns, mean context and weighted share, each product's deploy failures and PRs that needed a follow-up fix, and the machine's load. It prints numbers only, and reads the session that last started an agent (`--session <id>` for another).
8. Capacity: `python3 scripts/capacity_scan.py` (each open directive's running orders, its `NEXT:` row and a state, then the machine's room; ids and roles only).
9. Switched off in production: in each product's runbook (`knowledge/engineering/runbooks/<product>.md`), `grep -n` the "Switched off in production" heading and read that table. A finding is a row whose reason isn't one of `CLAUDE.md`'s hard waits ("Only hard blocks wait"; a design's own "after X" gate isn't one), a row whose reason is a date or event that has passed, and a product with live users and no such table.
10. Spend (`executive-summaries.md`, rule 9): `python3 scripts/spend_report.py`. One line per paid vendor or pool, in `knowledge/finance/spend.md`'s order, over or projected over first, every time in the Board's time zone: what's included or the cap, this cycle's spend with its read time and source, the cycle's end at the last 24 hours' pace and at today's, and the date it passes what's included. A `not read here` line names who reads it. A `manual` line takes `spend.md`'s number with the date and source it names there, or says it isn't read; a vendor on `spend.md` the script doesn't print is manual too. A bill or balance last read 7 or more days ago or never, or whose named reader can't read it, goes under "Blocked on you" as a Board step, one of the 5: a one-minute read, what to open and which number to send back. With `spend.md` empty, write "no paid vendors recorded".

## Write

Keep it under about 30 lines plus the Spend block, facts first, with links. Every date and time in the Board's time zone (`timezone` in `company.json`; logs stay in UTC with a Z, and you convert):

```
Status as of <YYYY-MM-DD HH:MM> <time zone>

In progress
- <D-id>: <one line: where it stands, next step>

Decided since <date> (undo any: say "undo N")
1. <what> (<why>; undo: <how>)

Blocked on you (at most 5, tier-1 or tier-2 form; each one an open ask or Board step in asks.md, written there first)
1. A-<n>: <the recommended answer "yes" takes> | or: <at most one alternative> | allows and costs: <…> | undo: <…> | meanwhile: <…>

Shipped (production deploys)
- <product>: <change> (PR <link>, smoke check <pass/fail, rolled back?>)

Done since <date>
- <D-id>: <outcome>

KB: <lint errors/warnings>; <N> TODO(board) open (most in <folders>); sweep: <what's due, or none>

Spend (as of <HH:MM> <time zone>; over or projected over first)
- <each line spend_report.py prints, as printed; a manual line with its number, date and source>

Cost: <top roles by share, with mean context>; deploy failures <n>; follow-up fixes <n>; load <1-min> on <CPUs> CPUs

Capacity: <n> directives with agents on them; idle: <ids, or none> (starting now); waiting on you: <ids, or none>; switched off: <n> rows, <n> findings (acting now); room: <yes | no, and why>
```

Write "none" under any empty heading. **Never report work as done without evidence** (a merged PR, an existing page). If evidence contradicts a directive file, say so and fix the file.

**The idle work:** right after the report, in the same turn, start every IDLE and NO NEXT line of the capacity scan (`ceo.md`, "Capacity"), and act on every switched-off finding (Gather, step 9): a two-way switch-on is an order or a `SendMessage` ruling to the CTO, a one-way one (b1–b9) goes under "Blocked on you", and a missing table is an order to the CTO.

**The sweep** (hot and cold pages): `kb_lint` prints `sweep due` for a page within 10% of its limit, for an owner whose last sweep is 14 days old or more, and for a "Past, in short" older than its cold text. Say what's due, by owner, on the "KB:" line. After the report, unasked: run `python3 scripts/kb_sweep.py` (a dry run: what would move, what stays and why, and which pages agents really opened). If it prints `Would move, ceo` or `kb_lint` prints `sweep due: ceo`, run `python3 scripts/kb_sweep.py --apply --owner ceo` and commit the moved pages with `knowledge/last-sweep.txt`. Refresh any summary `kb_lint` names as yours. A `cto` line needs no order: the CTO sweeps and refreshes its summaries at the end of its next order (`cto.md`, "Afterwards, every time"), and you commit what it lists. A near-limit page the tool can't move stays on the "KB:" line and orders nobody. A `ceo-questions.md`'s handled lines move by `python3 <repo>/scripts/cq_archive.py <repo>/workspaces/<product>/content/ceo-questions.md` (both paths absolute, no `cd`: `cto.md`, "Logs"; `--dry-run` first, `--closed <order id>` for a finished order), as its lint line says; `kb_sweep.py` moves only its `# ` sections with a CLOSED line. The tool moves text word for word and never commits; a page's owner decides on its summary and on what a use candidate means. Pages of other owners go to them, as with lint errors.

**Every 14 days** (the drift audit and the Board's load):
- **"Drift audit due"** goes on the last line when the last `DRIFT AUDIT` row is more than 14 days old, or none exists and the first directive is more than 14 days old. After the report, send the critic the audit order (`critic.md`, "Drift audit"), and log its outcome as a status-log row starting `DRIFT AUDIT <from>..<to>:`.
- With it, the numbers: asks per Board-active day, the share marked `taken`, and the last audit's findings. Then end with one question: "Lighter, same or heavier than two weeks ago?" Log the answer as a status-log row `LOAD: <word>`.
