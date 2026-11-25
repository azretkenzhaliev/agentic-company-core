---
title: Org chart
owner: ceo
status: active
updated: 2026-11-25
related: [../../CLAUDE.md, ../engineering/README.md]
---

# Org chart (v1)

| Role | Agent file | Model | Reports to | Owns in the KB | Job |
|---|---|---|---|---|---|
| Board | (the founder) | – | – | `board/` | Direction, reserved powers, standing authorizations |
| CEO | `.claude/agents/executive/ceo.md` | inherit (the session's model) | Board | `company/`, `products/`, `sales/`, directive files, inactive departments | Turns directives into orders, resolves cross-department questions, acts as CSO and CPO, reports to the Board |
| Analyst | `.claude/agents/executive/analyst.md` | opus | CEO | `research/` | Market, competitor, pricing, regulatory and legal-landscape research; raw, sourced notes |
| Critic | `.claude/agents/executive/critic.md` | opus | CEO | nothing (read-only) | Checks the CEO's analyses, plans and design gists before the Board sees them, with second opinions from other model families (SA-003); every 14 days, the drift audit of what the company decided without the Board |
| Platform engineer | `.claude/agents/executive/platform-engineer.md` | opus | CEO | nothing: it edits the system (agents, skills, hooks, scripts, tools, `CLAUDE.md`, templates) in a worktree; the CEO lands it | Changes the company's own system: change, test, probe, code review, then a reviewed commit for the CEO |
| CMO (optional) | `.claude/agents/marketing/cmo.md` | opus | CEO | `marketing/` (except the rows below) | Plans each brand-week, starts the producer and the reviewer, puts the Board's packet in the marketing calendar, curates the marketing KB |
| Content producer | `.claude/agents/marketing/content-producer.md` | sonnet | CMO | `marketing/<brand>/content/` | Makes one brand-week from the founder's raw material: pages, renders, captions |
| Content reviewer | `.claude/agents/marketing/content-reviewer.md` | opus | CMO | nothing (read-only) | A VERDICT per piece, once per batch: law, red lines, sources, the founder's voice, citations, AI disclosure |
| Performance analyst | `.claude/agents/marketing/performance-analyst.md` | sonnet | CMO | `marketing/<brand>/metrics.md`, `learnings.md` | Weekly numbers from the analytics tool (reads only) into metrics and dated learnings; the AI vs non-AI comparison at the 8-week review |
| Trend researcher | `.claude/agents/marketing/trend-researcher.md` | sonnet | CMO; the CEO also starts it | nothing in the KB; `workspaces/marketing/intelligence/` | Reads public social pages in a separate browser profile, read only, and keeps the weekly intelligence table |
| Reel analyst | `.claude/agents/marketing/reel-analyst.md` | sonnet | CMO; the CEO also starts it | nothing in the KB; `workspaces/marketing/intelligence/reels/` | Watches a week's reels, a batch a run: downloads them logged out, measures and transcribes them, writes a breakdown of each. No browser |
| CTO | `.claude/agents/engineering/cto.md` | opus | CEO | `engineering/` | Architecture, standards, roadmaps, ADRs, runbooks; sizes and staffs engineering work; runs production deploys |
| Staff engineer | `.claude/agents/engineering/staff-engineer.md` | opus | CTO | `engineering/designs/` | Designs and work with no approved design; Seniors merge after review; see the engineering README, "Who runs a task" |
| Design reviewer | `.claude/agents/engineering/design-reviewer.md` | opus | Staff | nothing (read-only) | Checks design docs against the codebase and the roadmap |
| Senior engineer | `.claude/agents/engineering/senior-engineer.md` | sonnet | Staff (or CTO for S-size) | nothing in the KB; code on its branch | Implements one task with tests |
| Code reviewer | `.claude/agents/engineering/code-reviewer.md` | sonnet; opus for sensitive code (customer data, sign-in, migrations) and system diffs | Staff (or CTO) | nothing (read-only) | Checks diffs against the design, roadmap and standards |
| UX expert | `.claude/agents/engineering/ux-expert.md` | opus | CTO, Staff (a UI design's UX check); the CEO and the CMO also start it | `engineering/ux/` | UX audits, specs with rendered options, acceptance of built screens; every finding labelled by evidence level; owns the `ux-checklist` skill Seniors load on UI tasks |

**Inactive departments:** sales (CSO), finance (CFO), legal, people and operations (COO) exist as KB folders. The CEO covers them. The CEO's `sales-playbook` skill is the seed of the future CSO. Marketing is optional: the Board switches it on ([docs/marketing.md](../../docs/marketing.md)).

**Model choices** follow SA-002: Opus for the planners and judges above, Sonnet for the rest. The Opus agents' files say `opus[1m]` and compact at 300k tokens (a default). Every agent thinks at `xhigh`. Changing a role's model is the Board's call (SA-002); [docs/guide.md](../../docs/guide.md), "Plan sizes", says how.

## The tree

`CLAUDE.md` links this tree and keeps the operating modes and the nesting depth; `scripts/hooks/guard_agent_spawn.py` enforces who may start whom.

```
Board (human)
└── ceo            .claude/agents/executive/ceo.md         main session; also CSO and CPO
    ├── analyst    .claude/agents/executive/analyst.md     research; writes raw notes only
    ├── critic     .claude/agents/executive/critic.md      read-only; checks the CEO's analyses, plans and design gists
    ├── platform-engineer  .claude/agents/executive/platform-engineer.md  changes the company's own system in a worktree
    │   └── code-reviewer                               read-only; checks its diffs (the CEO also starts one for the gate)
    ├── cmo        .claude/agents/marketing/cmo.md         marketing (optional): plans each brand-week, puts the Board's packet in the calendar
    │   ├── content-producer                            one brand-week, from the founder's raw material
    │   ├── content-reviewer                            read-only; a VERDICT per piece, once per batch
    │   ├── performance-analyst                         weekly numbers (reads only) → metrics and learnings
    │   ├── trend-researcher  .claude/agents/marketing/trend-researcher.md  read-only browser on public pages; `ceo` also starts it
    │   ├── reel-analyst  .claude/agents/marketing/reel-analyst.md  watches the reels the read kept: breakdowns, the week's formats file; `ceo` also starts it
    │   └── analyst                                     research for marketing (the same agent)
    └── cto        .claude/agents/engineering/cto.md
        └── staff-engineer                              one workstream, end to end
            ├── design-reviewer                         read-only; checks designs against the code
            ├── senior-engineer                         implements one task with tests
            ├── code-reviewer                           read-only; checks diffs against design and roadmap
            └── ux-expert  .claude/agents/engineering/ux-expert.md  UX audits, specs, UX checks and acceptance; `cto`, `ceo` and `cmo` also start it
```
