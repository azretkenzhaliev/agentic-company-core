---
title: Knowledge base index
owner: ceo
status: active
updated: 2026-10-19
related: [README.md]
---

# Knowledge base index

Every agent reads this page first, then the pages that bear on its task. Conventions (ownership, front matter, IDs) are in [README.md](README.md). The constitution is [`../CLAUDE.md`](../CLAUDE.md).

## Board (owner: board)
- [Charter](board/charter.md): the Board's reserved powers and how directives work.
- [Standing authorizations](board/standing-authorizations.md): SA-001 (autonomous production deploys behind gates), SA-002 (subscription first), SA-003 (optional reviews by Google Gemini, DeepSeek and OpenAI GPT).
- [Directives](board/directives/README.md): every Board directive, with its plan, orders, status log and final report.
- [Attachments](board/attachments/README.md): documents the Board handed over, kept verbatim.

## Company (owner: ceo)
- [Overview](company/overview.md): what the company is. Mostly `TODO(board)` until onboarding.
- [Portfolio](company/portfolio.md): the products, their status and repos.
- [Strategy](company/strategy.md): priorities and goals.
- [Org chart](company/org-chart.md): roles, agents and who reports to whom.
- [Glossary](company/glossary.md): the company's terms.
- [Decisions](company/decisions/README.md): company decisions (`DEC-NNN`).

## Products (owner: ceo, acting CPO)
- One page per product, `products/<product-id>/README.md`, from [the product template](_templates/product.md). None yet: `/onboard-company` creates them.

## Engineering (owner: cto)
- [How engineering works](engineering/README.md): sizing, the pipeline, the review loops, deploy gates (SA-001), git and workspaces.
- [Standards](engineering/standards/README.md): coding, testing, security, review checklists, definition of done, lessons learned.
- [Architecture](engineering/architecture/overview.md): the overview, plus one page per product from `/onboard-codebase`.
- [Roadmaps](engineering/roadmaps/README.md) · [Designs](engineering/designs/README.md) · [ADRs](engineering/adr/README.md) · [Runbooks](engineering/runbooks/README.md)

## Marketing and sales (owner: ceo, acting CMO and CSO)
- [Marketing](marketing/README.md) · [Sales](sales/README.md)

## Research (owner: analyst; raw, untrusted until curated)
- [Research notes](research/README.md)

## Inactive departments (the CEO covers them)
- [Finance](finance/README.md) · [Legal](legal/README.md) · [People](people/README.md) · [Operations](operations/README.md)
