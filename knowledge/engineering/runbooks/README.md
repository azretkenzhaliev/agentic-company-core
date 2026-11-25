---
title: Runbooks
owner: cto
status: active
updated: 2026-11-25
related: [../README.md, ../../_templates/runbook.md, ../../board/standing-authorizations.md]
---

# Runbooks

One per product: `<product>.md`, from [the template](../../_templates/runbook.md), first drafted by `/onboard-codebase`. **A runbook must have `status: active` before any autonomous production deploy (SA-001).** A runbook becomes active when its steps have been verified and the Board has confirmed how deploys work for that product.

| Product | Runbook | Status |
|---|---|---|
| – | none yet | – |

A runbook that outgrows one page gets siblings by topic, each with a row in its "Find your section": `<product>-tests.md` (machine load, task suite, essential tier), `<product>-procedures.md` (live steps an ordinary task doesn't need), `<product>-settings.md` (runtime settings), `<product>-lanes.md` (who owns what parallel lanes share), `<product>-history.md` (the verification record and what was done).

**Before moving text off a runbook** (a split, a move to a sibling, a rename): grep `scripts/` and `.claude/` for the page's file name and for each heading that moves (`grep -rn -F --exclude-dir=worktrees '<name>' scripts/ .claude/`). Hooks and system tests may read runbook text. Leave a stub heading with a pointer at each moved heading. If code parses the moved text, tell the platform engineer before the move, through the CEO, so the reader moves with the text; the CEO runs the system suite before committing the move.
