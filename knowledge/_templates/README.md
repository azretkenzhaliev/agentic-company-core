---
title: Page templates
owner: ceo
status: active
updated: 2026-11-16
related: [../README.md]
---

# Page templates

Copy a template, rename it per the ID rules in [../README.md](../README.md), and replace every `<placeholder>`. The KB linter skips this folder, so these files don't have to pass lint themselves.

| Template | For | Written by |
|---|---|---|
| [page.md](page.md) | Any page without a more specific template | anyone, in their own folder |
| [directive.md](directive.md) | `board/directives/D-YYYYMMDD-<slug>.md` | ceo |
| [decision.md](decision.md) | `company/decisions/DEC-NNN-<slug>.md` | ceo |
| [product.md](product.md) | `products/<product>/README.md` | ceo |
| [research-note.md](research-note.md) | `research/<YYYY-MM-DD>-<slug>.md` | analyst |
| [roadmap.md](roadmap.md) | `engineering/roadmaps/RM-NNN-<slug>.md` | cto |
| [design-doc.md](design-doc.md) | `engineering/designs/DD-NNN-<slug>.md` | staff-engineer |
| [adr.md](adr.md) | `engineering/adr/ADR-NNN-<slug>.md` | cto |
| [architecture.md](architecture.md) | `engineering/architecture/<product>.md` | cto |
| [runbook.md](runbook.md) | `engineering/runbooks/<product>.md` | cto |
| [content-piece.md](content-piece.md) | `marketing/<brand>/content/<week>/` | content-producer |
| [ask.md](ask.md) | one ask (`A-n`) or Board step (`B-n`) in `company/board-desk/asks.md` | ceo |
| [qa.md](qa.md) | one Board question and its answer (`Q-n`) in `company/board-desk/qa.md` | ceo |
