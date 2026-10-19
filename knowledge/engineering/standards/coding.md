---
title: Coding standards
owner: cto
status: active
updated: 2026-10-12
related: [README.md, testing.md, security.md]
---

# Coding standards

1. **Match the repo.** Read its `CLAUDE.md`, README, linter and formatter configs, and the code around your change. New code should look like the code next to it: naming, structure, comment density, error handling.
2. **Change only what the task needs.** Every changed line traces to the task's acceptance criteria. Don't refactor, reformat or "improve" neighbouring code. If you spot an unrelated problem, mention it in your report.
3. **Simple first.** No abstractions for a single use, no configurability nobody asked for, no handling of impossible cases. If 50 lines do it, don't write 200.
4. **Handle errors at the boundaries:** user input, network, files, outside services. Fail loudly with a useful message. Don't swallow exceptions.
5. **No dead code.** Remove what your change makes unused. Leave older dead code alone and mention it.
6. **Dependencies.** A new runtime dependency needs a line in the design doc (what, why, licence, maintenance status). S-size work adds none. Nothing paid without the Board (SA-002).
7. **Configuration and secrets** come from the environment or the platform's secret store, never from code. See [security.md](security.md).
8. **Run the linters and formatters** the repo uses, and fix what they report in your change.
9. **Commits** are small and focused, with messages that cite ids, e.g. `RM-003 WS-1 T-2: add mock-exam timer`.
