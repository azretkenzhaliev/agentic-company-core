---
title: Glossary
owner: ceo
status: active
updated: 2026-11-25
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
| Critique | The critic's result on a plan: SUPPORT, REVISE or RETHINK |
| SA | Standing authorization: a class of actions the Board pre-approved |
| One-way door | A decision that always comes to the Board; the list is b1–b9 in `CLAUDE.md` |
| Two-way door | Everything else: decided without the Board, told afterwards, with how to undo it |
| Ask, Board step | A one-way question (`A-n`), or a step only the Board can take (`B-n`), in `board-desk/asks.md` |
| S, M, L | Sizes of engineering work: one task; one workstream; several workstreams |
| RM, WS, DD, T | Roadmap, workstream, design doc, task |
| ADR, DEC | Architecture decision record (CTO); company decision (CEO) |
| Question file | `ceo-questions.md`: where engineers ask and the CEO rules while an order runs |
| Workspace | A product repo cloned into `workspaces/<product>/<repo>/` |
| Worktree | A separate git checkout per workstream, in `workspaces/<product>/.worktrees/<id>/` |
| Runbook | A product's build, test, deploy, smoke-check and rollback steps |
| Smoke check | A quick post-deploy check that production works |
| Hard wait | A reason work may wait, from the list in `CLAUDE.md`, "Only hard blocks wait"; any other wait is soft, and the work starts |
| The gate | What a change to the company's own system goes through (`ceo.md`, "System changes") |
| Guardrail file | A file the guards are made of or read; `platform-engineer.md`, "The gate", has the list |
| Drift audit | The critic's check, every 14 days, of what the company decided without the Board |
| Raw versus curated | Raw = outside content in `research/`, untrusted. Curated = an owner's page |
| `TODO(board)` | A fact only the Board can supply; never guessed |
