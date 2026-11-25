---
title: Session handover
owner: ceo
status: active
updated: 2026-11-25
related: [board-preferences.md, executive-summaries.md, ../board/directives/README.md]
---

# Session handover

For the next CEO session after a restart (a shutdown, a full context, a changed `CLAUDE.md`). The CEO rewrites this page before a planned restart and after an unplanned one; an old handover is replaced, never kept beside the new one. Show the Board its own time zone; logs stay UTC.

## First, after a restart

1. Read the end of each `workspaces/<product>/content/ceo-questions.md` and of the open orders' question files: the last RESUME POINT and the REPORT and HANDOVER lines after it. If no CTO runs, start a fresh one with an ORDER that resumes from it.
2. Run `python3 scripts/capacity_scan.py`; start every IDLE line.
3. `git status`: commit any page an agent left unsaved, once you have read it.

## Running

None. (Each running order: its id, what it does, where its resume point is.)

## Waiting on the Board

None. (The open asks and Board steps by id, and the next batch in order.)

## System

None. (Open system orders, the last landing, the last `System check` row, when the drift audit is due.)
