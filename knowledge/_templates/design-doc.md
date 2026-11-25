---
title: <Design title>
owner: staff-engineer
status: draft
updated: <YYYY-MM-DD>
related: []
---

# DD-<NNN>: <title>

**Roadmap:** <RM-NNN / WS-n, linked>   **Product/repo:** <id, repo>
**Branch:** `ws/RM-<NNN>-WS-<n>-<slug>`   **Worktree:** `workspaces/<product>/.worktrees/RM-<NNN>-WS-<n>/`
**Design status:** in review | approved | awaiting-ceo | awaiting-board | implementing | merged | deployed
**Door:** one-way (<b1–b9, `CLAUDE.md` "The Board's attention">) | two-way

## Gist for the Board

<At most 10 plain-language lines, filled in once the design review passes: what users will notice, what gets built, data or API changes, risks, cost, and any decision the Board must make. The first three lines stand alone: for a two-way design they are what the Board sees.>

## The Board's words this design relies on

<Quoted, dated and linked, from `knowledge/company/board-preferences.md` and the directives, each with one line on how the design complies. Every preference item the design touches is here. "None found" if none.>

## Context

<What exists today, citing real files and modules (path:line).>

## Goals and acceptance criteria

<Copied from the roadmap workstream, unchanged.>

## Proposed design

<The change, citing the real files, modules and functions it touches.>

## Data and API changes

<Schemas, migrations, endpoints, contracts. "None" if none.>

## Migration

<Steps, and whether they're reversible.>

## Testing strategy

<Which tests, where, and the command that runs them.>

## Rollout and rollback

<How it ships per the product runbook, and how to undo it.>

## Security and privacy

<Inputs, auth, secrets, personal data. "No impact" with a reason if none.>

## Tasks

### T-1: <name>

- **Files:** <paths>
- **Acceptance criteria:** <checkable>
- **Tests:** <what proves it>

## Review log

One row for the design review, plus one row per sign-off (`CEO: APPROVED (two-way)`, `CEO: CHANGES_REQUESTED`, `Board: APPROVED` or `Board: CHANGES_REQUESTED`).

| Round | Date | Verdict | Findings (summary) | Resolution |
|---|---|---|---|---|

## Implementation log

One row per landing, no per-step rows. The reviewer's verdicts are in its findings files; where the work stands is in the header.

| Landing | Tasks | PR and merge commit | Verdicts | For the next production deploy |
|---|---|---|---|---|
