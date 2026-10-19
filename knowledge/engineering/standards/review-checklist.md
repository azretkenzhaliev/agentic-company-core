---
title: Review checklists
owner: cto
status: active
updated: 2026-10-14
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

## Code review (code reviewer)

1. **Matches the design** and the task's acceptance criteria. Deviations are findings unless the design was updated.
2. **Tests:** each behavior change has a test that would fail without it. Run the test commands you were given yourself (the task suite while a task iterates) and report the result.
3. **Correctness:** edge cases, error paths, concurrency, time zones and encodings where relevant.
4. **Security** per [security.md](security.md): input validation, authorization, secrets, personal data.
5. **Scope:** no unrelated changes, refactors or reformatting.
6. **Conventions:** matches the repo's style, linters and formatter output.
7. **Commits** cite ids. No secrets, `.env` files or large generated files.
