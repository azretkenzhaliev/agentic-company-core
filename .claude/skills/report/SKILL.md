---
name: report
description: Use when the Board asks for status, a report, an update or "what's going on", or opens a CEO session with a greeting.
argument-hint: "[period, e.g. 'this week' or 'since 2026-10-01']"
---

# Status report for the Board

You are the CEO. Give the Board a short, true picture of the company. This is read-only: don't spawn agents, and don't change anything except to fix a status you find wrong in your own pages. Period: $ARGUMENTS (default: the last 7 days, plus everything still open).

## Gather

1. `knowledge/board/directives/README.md`, then every directive file that isn't `done` or `cancelled`, plus those closed within the period.
2. Engineering evidence for in-flight and recent work, per product repo:
   `gh pr list --repo <owner>/<repo> --state all --limit 15 --json number,title,state,url,mergedAt,updatedAt`
3. Every "Open questions for the Board" entry that's still unanswered.
4. KB health: run `python3 scripts/kb_lint.py`, and count open facts with `grep -rc "TODO(board)" knowledge --include=*.md` (sum per top-level folder).

## Write

Keep it under about 25 lines, facts first, with links:

```
Status as of <YYYY-MM-DD>

In progress
- <D-id>: <one line: where it stands, next step>

Blocked on you
1. <question or approval> (recommendation: <…>)

Shipped (production deploys)
- <product>: <change> (PR <link>, smoke check <pass/fail, rolled back?>)

Done since <date>
- <D-id>: <outcome>

KB: <lint errors/warnings>; <N> TODO(board) open (most in <folders>)
```

Write "none" under any empty heading. **Never report work as done without evidence** (a merged PR, an existing page). If evidence contradicts a directive file, say so and fix the file.
