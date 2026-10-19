---
title: Org chart
owner: ceo
status: active
updated: 2026-10-12
related: [../../CLAUDE.md, ../engineering/README.md]
---

# Org chart (v1)

| Role | Agent file | Model | Reports to | Owns in the KB | Job |
|---|---|---|---|---|---|
| Board | (the founder) | – | – | `board/` | Direction, reserved powers, standing authorizations |
| CEO | `.claude/agents/executive/ceo.md` | inherit (the session's model) | Board | `company/`, `products/`, `marketing/`, `sales/`, directive files, inactive departments | Turns directives into orders, resolves cross-department questions, acts as CMO, CSO and CPO, reports to the Board |
| Analyst | `.claude/agents/executive/analyst.md` | sonnet | CEO | `research/` | Market, competitor, pricing, regulatory and legal-landscape research; raw, sourced notes |
| CTO | `.claude/agents/engineering/cto.md` | opus | CEO | `engineering/` | Architecture, standards, roadmaps, ADRs, runbooks; sizes and staffs engineering work |
| Staff engineer | `.claude/agents/engineering/staff-engineer.md` | opus | CTO | `engineering/designs/` | One workstream end to end: design, both review loops, merge and deploy |
| Design reviewer | `.claude/agents/engineering/design-reviewer.md` | opus | Staff | nothing (read-only) | Checks design docs against the codebase and the roadmap |
| Senior engineer | `.claude/agents/engineering/senior-engineer.md` | sonnet | Staff (or CTO for S-size) | nothing in the KB; code on its branch | Implements one task with tests |
| Code reviewer | `.claude/agents/engineering/code-reviewer.md` | opus | Staff (or CTO for S-size) | nothing (read-only) | Checks diffs against the design, roadmap and standards |

**Inactive departments:** marketing (CMO), sales (CSO), finance (CFO), legal, people and operations (COO) exist as KB folders. The CEO covers them. The CEO's `marketing-playbook` and `sales-playbook` skills are the seeds of the future CMO and CSO.

**Model choices** save subscription usage (SA-002). If limits bite, move judgment roles to sonnet before cutting reviews.
