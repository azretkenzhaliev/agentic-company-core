---
title: Definition of done
owner: cto
status: active
updated: 2026-11-25
related: [README.md, review-checklist.md, ../README.md]
---

# Definition of done

## A task (Senior)

- Every acceptance criterion is met, with a test for each behavior change.
- The task suite passes (the runbook's "Task suite", or the tests the diff touches where the runbook has none), with the exact commands and results in the report.
- Linters and formatters pass on the change.
- Committed on the workstream branch with ids in the message.
- Code review finished: APPROVED, in the round or at the re-check of its fixes (every blocker and major fixed). Minors and nits are logged, not fixed.

## A workstream (Staff)

- The design was signed off before implementation started: by the CEO (two-way) or the Board (one-way), unless the Board waived sign-off (engineering README, section 3).
- Every task is done, and logged minors and follow-ups are carried into a later task or listed.
- Typecheck, lint, the task suite and the runbook's essential tier (where it has one) are green on the landing branch after merging `origin/main`; zero tests selected for a code change fails the gate (README §5). A production deploy needs the affected tests, the essential tier and the PR's CI checks green; never a full suite (SA-001 condition 2).
- The design doc's review and implementation logs are complete, and its status is updated.
- One PR, with the required checks green if the repo has them.
- Merged and deployed per the runbook with the smoke check passing, or reported as blocked on a named gate.

## A directive (CEO)

- Every order has a REPORT, and every acceptance criterion is met or explained.
- KB pages are updated and pass `python3 scripts/kb_lint.py`.
- The directive file holds the plan, orders, status log and final report.
- The Board has the final report, including every deploy.
