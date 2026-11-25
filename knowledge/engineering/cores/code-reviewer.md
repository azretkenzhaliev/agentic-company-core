---
title: Engineering core, code reviewer
owner: cto
status: active
updated: 2026-11-25
related: [README.md, shared.md, ../standards/review-checklist.md, ../standards/testing.md]
---

# Code reviewer: your part

What `code-reviewer.md` points to but doesn't hold: the checklist you grade by, and the standards' lines reviews cite most. RC = `standards/review-checklist.md` "Code review", each point in its operative words; open one for its case. T = `testing.md`; S = `security.md`. Inside a repo, its own `CLAUDE.md`, README or tooling wins over the standards (`standards/README.md`).

## Grades (`review-checklist.md`, top)
- blocker: wrong, unsafe or breaks something; must be fixed. major: misses an acceptance criterion, a standard or a needed test; must be fixed. minor: works, but should be better; the author decides. nit: style or wording. APPROVED means no blocker or major. Every finding cites a file and line and says what must change.

## The checklist (RC 1-13)
1. Matches the design and the task's acceptance criteria; a deviation is a finding unless the design was updated.
2. Each behaviour change has a test that would fail without it. Run the test commands you were given and report the result.
3. Correctness: edge cases, error paths, concurrency, time zones and encodings where relevant.
4. Security (`security.md`): input validation, authorization, secrets, personal data.
5. Scope: no unrelated changes, refactors or reformatting.
6. Conventions: the repo's style, linters and formatter output.
7. Commits cite ids; no secrets, `.env` files or large generated files.
8. No production control calls a stub: a visible button whose member answers "not available" is a major.
9. Row locks are taken in one order by every writer: the change lists every other path that locks or writes those rows, and a test races two paths and asserts no `40P01`. A locked pick with a `limit` that feeds an `update` or `delete` runs once (a CTE, `any(array(...))`, a scalar subquery), never as `in (select … limit … for …)` or a `from (select …)` subquery; its test empties the table's statistics and asserts the limit.
10. A new fail-closed rule over existing data: the author reports a query counting the fixture rows it now catches, where only its own tests may appear. A down file changes a constraint in one statement, or puts the one that can fail first, and its test asserts the catalog unchanged after a refused down.
11. A new tunable literal in code (size, budget, timeout, threshold, rate, floor, retry count, model, cadence; not build-fixed values, secrets, sign-in or permission values) is a major: it's a runtime setting read through the registry, default equal to the old value, a safe range, a fallback test, a runbook row with its door.
12. Each sentence or value telling customers what a feature does has its path from a production entry point named, file:line; a test isn't a caller. None: a major.
13. A new or changed gate has a test where the change under test does nothing, built from real or recorded data where there is any, and it passes; a baseline that makes it pass vacuously doesn't count. None: a major.

## Standards lines reviews cite most
- A test of a tunable reads it from the settings' defaults, never a literal in the code or its name. (T 20)
- Each test file stands alone: builds or seeds what it needs in `beforeAll`, leaves shared rows as it found them. A module mock keeps the real module's other exports. (T 18, 13)
- Deterministic: no sleeps for timing, no dependence on order, clock or unseeded randomness. Mock only paid services, production and the network; assert results, not mock calls. (T 6, 4)
- Code that reads hostile input stays linear, and every fix proves it. (T 17)
- Flag any `new RegExp(` with a non-literal argument in the diff, where the repo's scan blocks it. (T 23)
- A step with a deadline bounds each statement with `set local statement_timeout`; a read that grows with a customer's history has a production `EXPLAIN (ANALYZE)` or row count named before it lands. Compare `timestamptz` in SQL, never through a JS `Date`. (`coding.md` 10-11)
- Authorization on every request, on the server; parameterized queries; personal data never logged; no security control disabled. (S 3-5, 7)
- An edit written by an interpreter (not Edit or Write) is a finding. (LL "Landings")
- A change that lands in production is never reviewed single-family while the second-opinion keys are set. Summary statuses claim no more than their inputs. (LL "Reviews")

## Done means (`definition-of-done.md` "A task")
- Every acceptance criterion met, a test for each behaviour change; the task suite passes with exact commands and results reported; linters and formatters pass; commits on the branch cite ids.
