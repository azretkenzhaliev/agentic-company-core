---
title: Definition of done
owner: cto
status: active
updated: 2026-10-14
related: [README.md, review-checklist.md, ../README.md]
---

# Definition of done

## A task (Senior)

- Every acceptance criterion is met, with a test for each behavior change.
- The task suite passes (the runbook's "Task suite", or the full suite where the runbook has none), with the exact commands and results in the report.
- Linters and formatters pass on the change.
- Committed on the workstream branch with ids in the message.
- Code review verdict: APPROVED.

## A workstream (Staff)

- The Board approved the design gist before implementation started (unless the directive waived sign-off).
- Every task is done and APPROVED, and round-3 follow-ups are carried into a later task or listed.
- The full suite is green on the landing branch before the landing.
- The design doc's review and implementation logs are complete, and its status is updated.
- One PR, with green CI checks if the repo has CI.
- Merged and deployed per the runbook with the smoke check passing, or reported as blocked on a named gate.

## A directive (CEO)

- Every order has a REPORT, and every acceptance criterion is met or explained.
- KB pages are updated and pass `python3 scripts/kb_lint.py`.
- The directive file holds the plan, orders, status log and final report.
- The Board has the final report, including every deploy.
