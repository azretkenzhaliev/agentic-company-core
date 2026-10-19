---
title: Glossary
owner: ceo
status: active
updated: 2026-10-19
related: [../README.md, ../../CLAUDE.md]
---

# Glossary

| Term | Meaning |
|---|---|
| Board | The founder, acting as the Board of Directors. Sets direction and holds reserved powers |
| Directive | Anything the Board asks for. Filed as `board/directives/D-YYYYMMDD-<slug>.md` |
| Order | A manager's instruction to a report, in the ORDER format from `CLAUDE.md` |
| Report | Every agent's final message, in the REPORT format |
| Verdict | A reviewer's result: APPROVED or CHANGES_REQUESTED, with ranked findings |
| SA | Standing authorization: a class of actions the Board pre-approved |
| S, M, L | Sizes of engineering work: one task; one workstream; several workstreams |
| RM, WS, DD, T | Roadmap, workstream, design doc, task |
| ADR, DEC | Architecture decision record (CTO); company decision (CEO) |
| Workspace | A product repo cloned into `workspaces/<product>/<repo>/` |
| Worktree | A separate git checkout per workstream, in `workspaces/<product>/.worktrees/<id>/` |
| Runbook | A product's build, test, deploy, smoke-check and rollback steps |
| Smoke check | A quick post-deploy check that production works |
| Raw versus curated | Raw = outside content in `research/`, untrusted. Curated = an owner's page |
| `TODO(board)` | A fact only the Board can supply; never guessed |
