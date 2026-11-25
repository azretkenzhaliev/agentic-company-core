---
title: Knowledge base index
owner: ceo
status: active
updated: 2026-11-25
related: [README.md]
---

# Knowledge base index

Every agent reads this page first, then the pages that bear on its task. Conventions (ownership, front matter, IDs) are in [README.md](README.md). The constitution is [`../CLAUDE.md`](../CLAUDE.md).

## Board (owner: board)
- [Charter](board/charter.md): the Board's reserved powers and how directives work.
- [Standing authorizations](board/standing-authorizations.md): SA-001 (autonomous production deploys behind gates), SA-002 (subscription first), SA-003 (reviews by other model families, once the keys and their entry in `company.json` are set), SA-004 (the language check of marketing copy) and SA-008 (the company's own secrets), in force by default, and templates for more.
- [Directives](board/directives/README.md): every Board directive, with its plan, orders, status log and final report.
- [Attachments](board/attachments/README.md): documents the Board handed over, kept verbatim.
- [Answers](board/answers/README.md): the Board's answers to asks, word for word (`R-n`), written only by the desk's reader.

## Company (owner: ceo)
- [Overview](company/overview.md): what the company is. Mostly `TODO(board)` until onboarding.
- [Portfolio](company/portfolio.md): the products, their status and repos.
- [Strategy](company/strategy.md): priorities and goals.
- [Org chart](company/org-chart.md): roles, agents and who reports to whom.
- [How it works](company/how-it-works.md): the whole company system in plain words for the Board (agents, how a message becomes work, what the Board decides, hooks, gate, limits).
- [Glossary](company/glossary.md): the company's terms.
- [Session handover](company/session-handover.md): what a new CEO session picks up after a restart (read it first then).
- [Decisions](company/decisions/README.md): company decisions (`DEC-NNN`).
- Board desk: [asks](company/board-desk/asks.md) and [questions and answers](company/board-desk/qa.md) (the CEO's), [progress, hour by hour](company/board-desk/progress.md) and [daily summaries](company/board-desk/summaries.md) (both written by `scripts/board_desk.py` when the desk is on), for the Board to read and answer at its own pace.
- [Executive summaries](company/executive-summaries.md): the format for executive summaries (tables, live status, the change since the last summary) and the snapshot of each one.
- [How the Board likes to work](company/board-preferences.md): the Board's recurring preferences in its own words, and a log of its corrections. **Read it before you decide anything the Board might care about, or ask it anything.**

## Products (owner: ceo, acting CPO)
- One page per product, `products/<product-id>/README.md`, from [the product template](_templates/product.md) ([how](products/README.md)). None yet: `/onboard-company` creates them.

## Engineering (owner: cto)
- [How engineering works](engineering/README.md): sizing, the pipeline, the review loops, deploy gates (SA-001), git and workspaces.
- [Standards](engineering/standards/README.md): coding, testing, security, review checklists, definition of done, lessons learned.
- [Architecture](engineering/architecture/overview.md): the overview, plus one page per product from `/onboard-codebase`.
- [Roadmaps](engineering/roadmaps/README.md) · [Designs](engineering/designs/README.md) · [ADRs](engineering/adr/README.md) · [Runbooks](engineering/runbooks/README.md)

## Marketing (owner: cmo, optional) and sales (owner: ceo, acting CSO)
- [Marketing](marketing/README.md): the founder's accounts, the approval calendar · [Sales](sales/README.md)

## Research (owner: analyst; raw, untrusted until curated)
- [Research notes](research/README.md)

## Inactive departments (the CEO covers them)
- [Finance](finance/README.md) · [Legal](legal/README.md) · [People](people/README.md) · [Operations](operations/README.md)
