---
title: Engineering core, Senior engineer
owner: cto
status: active
updated: 2026-11-25
related: [README.md, shared.md, ../standards/coding.md, ../standards/testing.md, ../standards/review-checklist.md]
---

# Senior engineer: your part

What `senior-engineer.md` points to but doesn't hold: your "What to read" standards and the code points reviewers hold you to. C = `standards/coding.md`; T = `testing.md`; S = `security.md`; RC = `review-checklist.md` "Code review". Inside a repo, its own `CLAUDE.md`, README or tooling wins over the standards (`standards/README.md`).

## Code (C)
- Match the repo: its `CLAUDE.md`, README, linter and formatter configs, the code next to yours. Every changed line traces to the acceptance criteria: no refactoring, reformatting or "improving" neighbours; an unrelated problem goes in your report. (C 1-2)
- Simple first: no single-use abstractions, unasked configurability or impossible cases. Remove what your change makes unused; leave older dead code and mention it. (C 3, 5)
- Handle errors at the boundaries (input, network, files, outside services); fail loudly with a useful message; never swallow an exception. (C 4)
- A new runtime dependency needs a design line; S-size adds none. Config and secrets from the environment, never code. Run the repo's linters and formatters; fix what they report in your change. Small commits citing ids. (C 6-9)
- Database times stay in the database: compare `timestamptz` in SQL, never through a JS `Date`. (C 10)
- A step with a deadline checks the time left before each statement and runs it under `set local statement_timeout` set to that. A read that grows with a customer's history gets an `EXPLAIN (ANALYZE)`, or a count of its rows and width, on production, named in the design or PR before it lands, and a test where that read alone costs more than the budget. (C 11)
- Change a file's text with Edit or Write, never a heredoc, `sed -i` or an interpreter writing it (outside: a `<log>` and `<rc>`, a lock's `owner` line, the `>>` lines your agent file names, git, the repo's formatter or generator, scratch). (WR "Change a file's text")

## Tests (T)
- Each behaviour change has a test that fails without it and passes with it: write it first and watch it fail. A bug fix starts with a test that reproduces it. (T 1-2)
- Report each command run and its result; a failure you didn't cause goes in by name. (T 3)
- Test real behaviour: mock only paid services, production systems and the network; assert results, not mock calls. A module mock keeps the real module's other exports. No network or production data, no real credentials. (T 4-5, 13)
- Deterministic: no sleeps for timing, no dependence on test order, the clock or unseeded randomness; a "lacks `f01`" check matches a whole word. (T 6)
- Cover the edges the criteria imply: empty, too long, invalid, unauthorized, duplicate, concurrent. Code that reads hostile input stays linear, and every fix proves it. (T 7, 17)
- A test with its own registry, fixtures or config overrides every part it depends on; slow tests set an explicit timeout. Each file builds or seeds what it needs in its `beforeAll` and leaves shared rows as it found them. (T 9, 18)
- A failing test is a failure, on a loaded machine too. Change only the existing tests your ORDER names; another one: say which and why. (T 15)
- A test of a tunable reads it from the settings' defaults, never a literal. No `RegExp` built from a variable, in tests too, where the repo's scan blocks it. (T 20, 23)

## Security (S 1-8)
- Secrets by name only. Validate input at the boundary (type, length, format, allowed values); parameterized queries; output encoded for its context. Authorization on every request, on the server. Personal data: only what's needed, never logged. Never disable a security control to make something work: escalate. A vulnerability goes to your manager as a risk.

## What reviewers hold you to (RC)
- Every acceptance criterion met; a deviation from the design is a finding. (RC 1)
- A tunable (size, budget, timeout, threshold, rate, floor, retry, model, cadence) is a runtime setting: the old value as default, a safe range, a fallback test, a runbook row. (RC 11)
- Row locks in one order by every writer; a test races the two paths and asserts no `40P01`. A locked pick with a `limit` that feeds an `update` or `delete` is a CTE or `any(array(...))`, never `in (select … limit … for …)`; its test empties the table's statistics (`delete`, `analyze`) and asserts the limit. (RC 9)
- No production control calls a stub. A sentence telling customers what a feature does names its path from a production entry point, file:line (a test isn't a caller), or says "not in use yet". A new or changed gate has a test where the change does nothing, and passes. (RC 8, 12, 13)
- A new fail-closed rule over existing data: report a count of the fixture rows it catches. A down file fails whole; its test asserts the catalog unchanged. (RC 10)
