---
title: Engineering core, design reviewer
owner: cto
status: active
updated: 2026-11-25
related: [README.md, shared.md, ../standards/review-checklist.md, ../standards/security.md, ../standards/runtime-settings.md]
---

# Design reviewer: your part

What `design-reviewer.md` points to but doesn't hold: the checklist you grade by and the standards and lessons a design must meet. DR = `standards/review-checklist.md` "Design review", each point in its operative words; open one for its case. Inside a repo, its own `CLAUDE.md`, README or tooling wins over the standards (`standards/README.md`).

## Grades (`review-checklist.md`, top)
- blocker: wrong, unsafe or breaks something. major: misses an acceptance criterion, a standard or a needed test. minor: works, could be better; the author decides. nit: style or wording. APPROVED means no blocker or major. Every finding cites a doc section or file and line, and says what must change.

## The checklist (DR 1-15)
1. Grounded in the code: every file, module, function, table and endpoint named exists and works as described, checked with Read and grep, not memory.
2. Every workstream acceptance criterion is covered by a task; nothing outside the workstream is added.
3. Every affected caller, consumer and data flow is accounted for.
4. Schema and API changes explicit; migrations safe on real data, ordered, reversible or with a stated rollback.
5. The testing strategy proves each criterion and names the command that runs it.
6. Rollout and rollback follow the product runbook.
7. Security and privacy per `security.md` (below).
8. Tasks small, ordered, each with checkable criteria.
9. Simple: no speculative features or abstractions.
10. Measuring against labels: (a) who labels, and no candidate scored only on its own model family's labels; (b) a random and a targeted sample of what every labeller and candidate calls negative; (c) which steps need a person per item, and how production runs without one; (d) what labellers were shown: the key made without an input the variants differ in, or that bias named with a check independent of it. A gap in (a), (b) or (d) is a major.
11. A headline, badge or overall word telling users all is well names its scope in their words; an uncovered product or input reads "Not set up" or "Status unavailable". Overstating is a major.
12. People, accounts or data from an outside directory or list: every entry type it can return (members, guests, other domains, groups, service or suspended accounts), each with a rule. A type with no rule is a major.
13. Board steps: only ones the Board alone can do (`board-steps.md` §1), with minutes, one batch per landing; numbers the Board would read are also logged as one count-only line. A step an agent could do, or a read-back with no log line, is a major.
14. (a) Each quoted Board sentence is served, or the part it isn't is named as a narrowing (b8); (b) new input to an AI request, or data to a new reader, quotes the product's data-handling ADR's matching "never" clause and how it stands. Either missing is a major.
15. Every new gate (a run's gate, a measured bar, a tripwire) says what it measures against and shows one run, on real or recorded data, where the change under test is a no-op; that run passes. None is a major.

## Standards and lessons a design meets
- Tunables are runtime settings: sizes, lane counts, budgets, floors, rates, timeouts, retries, thresholds, model choices, tick cadence and time budget. Stay in code: build-fixed platform values, secrets, sign-in and permission values (b4), constants of meaning. (`runtime-settings.md` §1)
- A step with a deadline bounds each statement; a read that grows with a customer's history is measured on production first. (`coding.md` 11)
- Work per row on live customers' data: every claim expires, state is marked per unit right before its write, every terminal state listed. Narrowing which rows reach a path lists its guarantees. A rule reading an engine's verdict lists every cap and filter between them. Work sized from a measured estimate says the end at 2x and 5x. Two parallel designs on one new table name one owner. (LL "Writing specs and ORDERs")
- A table a step reads is named; never tables by dynamic SQL over `information_schema`. (LL "Stops")
- Security (`security.md` 1-9): secrets by name only; input validated at the boundary, parameterized queries, output encoded; authorization on every request, on the server; personal data only as needed, never logged, the design says where it's stored, who reads it and how long it's kept; never disable a security control; a vulnerability goes to your manager as a risk; a backup branch before any production statement that can change many rows at once.
- Done for a workstream: the design signed off by the CEO (two-way) or the Board (one-way) before implementation. (`definition-of-done.md`)
