---
title: Review checklists
owner: cto
status: active
updated: 2026-11-25
related: [README.md, definition-of-done.md, security.md]
---

# Review checklists

Reviewers return a VERDICT (format in `CLAUDE.md`). Rank every finding:

- **blocker:** wrong, unsafe or breaks something; must be fixed;
- **major:** misses an acceptance criterion, a standard or a needed test; must be fixed;
- **minor:** works, but should be better; the author decides;
- **nit:** style or wording.

APPROVED means no blocker or major findings. Every finding cites a file and line, or a doc section, and says what must change.

## Design review (design reviewer)

1. **Grounded in the code:** every file, module, function, table and endpoint the design names exists and works as described. Check with Read and `grep`, not from memory.
2. **Meets the roadmap:** every acceptance criterion of the workstream is covered by a task, and nothing outside the workstream is added.
3. **Integration points:** callers, consumers and data flows that the change affects are all accounted for.
4. **Data:** schema and API changes are explicit; migrations are safe on real data, ordered, and reversible or have a stated rollback.
5. **Testing strategy** proves each acceptance criterion and names the command that runs it.
6. **Rollout and rollback** follow the product runbook.
7. **Security and privacy** per [security.md](security.md).
8. **Tasks** are small, ordered, each with checkable acceptance criteria.
9. **Simplicity:** no speculative features or abstractions.
10. **Evaluations and labelling.** A design that measures models or rules against labels says (a) who makes the labels, and no candidate is scored only against labels from its own model family (two labellers from different vendors, or people); (b) how the negatives are checked: a random and a targeted sample of what every labeller and candidate calls negative, so a miss they share can be found; (c) which steps need a person per item, and how the production version runs without one (which test numbers set its thresholds); (d) what the labellers were shown: when the variants differ in an input, labels made with that input favour the variant that has it, so the key is made without it, or the design names that bias and adds a check that is independent of it. A gap in (a), (b) or (d) is a major finding.
11. **Summary statuses claim no more than their inputs.** A headline, badge or overall word that tells users all is well names its scope in the words they read, and a product or input it doesn't cover reads "Not set up" or "Status unavailable", never a better word. Check what a reader takes away from the largest word on the screen, not only the rule behind it. A word that overstates its scope is a major finding.
12. **Entries read from an outside directory or list are typed.** A design that selects people, accounts or data from an outside source (a directory, an API list, a customer's export) names every entry type that source can return (members, guests, other or secondary domains, groups, service or suspended accounts) and the rule for each; types already seen in the KB are cited. An entry type with no rule is a major.
13. **Board steps are few and light** ([board-steps.md](board-steps.md)). Every step the design needs from the Board is one only the Board can do under [board-steps.md](board-steps.md) §1, has its minutes, and is listed for one batch per landing. When the Board would read numbers off a page (counts, costs, a run's table), the design also logs them as one count-only code line the CTO can read from the logs, so the step asks only for "done". A step an agent could do, or a read-back with no log line, is a major.
14. **The Door is checked against the Board's words and the ADRs' "never" lists.** (a) For each Board sentence the design quotes, the design does what the sentence says, or names the part it doesn't as a narrowing (b8). A quote it serves only in part, unnamed, is a major. (b) A design that adds input to an AI request, or gives data to a new reader, quotes the matching "never" clause of the product's data-handling ADR and says how it stands against it. A "b2: no" that doesn't is a major.
15. **Every new gate passes on data where the change under test does nothing.** Applies to any pass/fail check that holds back a switch, a landing or a Board step: a run's gate, a measured bar, a tripwire. The design says what the gate measures against (the rules, a baseline answer, the old code) and shows one run of it, on real or recorded data, where the tested change is a no-op (the new input is empty, the knob is at its old value). That run must pass. If it fails, the gate measures the base and not the change. A gate with no such run is a major.

## Code review (code reviewer)

1. **Matches the design** and the task's acceptance criteria. Deviations are findings unless the design was updated.
2. **Tests:** each behavior change has a test that would fail without it. Run the test commands you were given yourself (the task suite while a task iterates) and report the result.
3. **Correctness:** edge cases, error paths, concurrency, time zones and encodings where relevant.
4. **Security** per [security.md](security.md): input validation, authorization, secrets, personal data.
5. **Scope:** no unrelated changes, refactors or reformatting.
6. **Conventions:** matches the repo's style, linters and formatter output.
7. **Commits** cite ids. No secrets, `.env` files or large generated files.
8. **No production control calls a stub.** Every button, form or route a production page offers calls a real implementation, or the page hides it or says "not available yet". A wired member that still answers "not available" behind a visible button is a major finding.
9. **Row locks are taken in one order by every writer.** (a) A change that takes a row lock (`for update`, `for key share`, or a key-share lock an insert takes through a foreign key) lists every other code path that locks or writes those rows and checks that all take them in the same order; a test races the two paths and asserts no `40P01`. (b) A pick with a `limit` and a lock clause (`for update`, `for no key update`, `for share`, with or without `skip locked`) that feeds an `update` or `delete` runs once: a CTE joined once, `= any(array(...))`, a scalar `= (select … limit 1)`, or its own statement. Never `in (select … limit … for …)` or a `from (select … limit … for …)` subquery: a nested-loop plan can take more rows than the limit. Its test empties the table's statistics (`delete`, then `analyze`) and asserts the limit.
10. **A new fail-closed rule over existing data is checked against the fixtures too, and down files fail whole.** (a) When a change narrows what existing rows or inputs may be, the author reports a query over the test database after the suite that counts the fixture rows the new rule now catches, and only the new rule's own tests may appear in it. (b) A down file changes a constraint in one statement (`ALTER TABLE … DROP CONSTRAINT …, ADD CONSTRAINT …`) or puts the statement that can fail first, and its test asserts the catalog is unchanged after a refused down.
11. **Values someone may tune are runtime settings** ([runtime-settings.md](runtime-settings.md)). A new or changed size, budget, timeout, threshold, rate, floor, retry count, model choice or tick cadence is read from the product's settings table through its registry, with a default equal to the old value, a safe range, a fallback test, and a runbook row with its door and one-line change. A new tunable literal in code (outside what the platform fixes at build, secrets, and sign-in or permission values) is a major.
12. **A sentence that tells customers what a feature does has a production caller.** For each such sentence or value the diff adds or changes, the notes name the path from a production entry point (a page, route, cron or push handler) to the code that does it, with file:line; a test is not a caller. A claim with no such path is a major finding: the sentence says "not in use yet" or goes.
13. **A new or changed gate has a no-op test** (design review point 15). A diff that adds or changes a pass/fail gate has a test where the change under test does nothing (the new answer equals the baseline, the input is empty, the setting is at its old value), built from the pattern of real or recorded data where there is any. The gate passes in that test. A test with a different baseline that makes the gate pass vacuously doesn't count. A gate with no such test is a major.
