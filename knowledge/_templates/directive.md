---
title: <Short directive title>
owner: ceo
status: active
updated: <YYYY-MM-DD>
related: []
---

# D-<YYYYMMDD>-<slug>: <title>

**Directive status:** open | in-progress | blocked | done | cancelled
**Received:** <YYYY-MM-DD>

## Directive (verbatim)

> <The Board's exact words. Never edit this section.>

## CEO analysis

<Scaled to the stakes (`ceo.md`, "Challenge before you plan"): none for facts, questions and small edits; a few lines for S-size; every heading for M, L, legal, money, security and customer data.>

### Goal

<The goal behind the request, in one line.>

### What we know and what we don't

<What the KB, the CTO's pages and outside facts say, with links. What was checked, and what wasn't. No guess stated as a fact.>

### Alternatives

| Option | Pros | Cons | Cost (Board time, usage, money) | Risk |
|---|---|---|---|---|
| <the Board's proposal> | | | | |
| <a smaller one> | | | | |
| Not now | | | | |

### Gaps and risks in the proposal

<"I disagree because …", or one line on why the analysis supports it.>

### Recommendation

<The option, and why.>

### Critic's verdict and what changed

<SUPPORT | REVISE | RETHINK, and what the CEO changed because of it, or why not. "Not needed" below the full analysis.>

## CEO plan

- **Classification:** question | KB edit | research | engineering (S, M or L) | marketing | sales | other
- **Delegation and why:** <who does what; which orders run at once, and what each waiting one waits on>
- **Board decisions needed:** <one-way doors, each with its item (b1–b9, `CLAUDE.md` "The Board's attention"), or "none">
- **Done when:** <checkable outcome>

## Orders

<One subsection per order, the full ORDER block as sent.>

### ORDER D-<YYYYMMDD>-<slug>/1   from: ceo   to: <role>

```
<ORDER block>
```

## Status log

| Date | Who | Event |
|---|---|---|
| <YYYY-MM-DD> | ceo | Directive received and filed |
| <YYYY-MM-DD> | ceo | NEXT: <the next step no agent is on>; waits: <none, b<N> and what, board-order and what, an order id, a YYYY-MM-DD, or why> |

<The latest `NEXT:` row is what `scripts/capacity_scan.py` reads (`ceo.md`, "Capacity").>
<`waits:` names a hard reason (`CLAUDE.md`, "Every lane busy": only hard blocks wait), or reads `none`: re-check it at every report.>
<A step held by a usage line the Board set: `waits: <the reset, YYYY-MM-DD HH:MMZ>, the Board's usage line`.>
<The scan counts `none`, `b<N>`, a `YYYY-MM-DD` or a directive id only first, an order as `D-…/n` anywhere or as `/n` first, and a door after an order only after `, `, `; ` or `then ` (`/2, then b2`); under an IDLE row with any other b<N> it prints a warning.>

## Open questions for the Board

- <question> (asked <date>; answer: <answer and date>)

## Final report

<The REPORT the Board received: summary, artifacts with links, deploys, decisions, open questions, risks.>
