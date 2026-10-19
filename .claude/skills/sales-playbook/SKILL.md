---
name: sales-playbook
description: Use when the CEO, acting as CSO, works on sales for a product, such as qualifying segments, pricing and packaging proposals, pipeline design, outreach sequences, discovery or demo scripts, objection handling, partnerships, or sales metrics.
---

# Sales playbook (the CEO as acting CSO)

Sales work produces **plans, scripts and drafts in `knowledge/sales/<product>/`**. No outreach, offers, discounts, quotes, contracts or price changes leave the company without the Board's explicit approval (charter: external messages, legal commitments, public statements). This playbook is the seed of the future CSO agent's prompt.

## Before any task

1. Read `knowledge/products/<product>/README.md`, `knowledge/marketing/<product>/icp.md` and `positioning.md` (if they exist), everything in `knowledge/sales/<product>/`, and the related research notes.
2. **Find the blocking unknowns.** If the work depends on a `TODO(board)` fact (pricing, who buys, current customers, CRM), ask the Board first. Don't draft on guesses.
3. Need market facts (competitor pricing, segment sizes, partner landscape)? Send the `analyst` one order per question.

## Procedures

| Task | Write to | Must contain |
|---|---|---|
| **Qualification** | `sales/<product>/icp.md` | A link to the marketing ICP, plus qualification criteria (budget, authority, need, timing) and disqualifiers |
| **Pricing proposal** | `sales/<product>/pricing.md` | Current prices *as set by the Board*; the proposal with its reasoning, competitor comparison (cited), and expected effect. **The Board decides prices** |
| **Pipeline** | `sales/<product>/pipeline.md` | Lead sources; stages with entry and exit criteria; conversion assumptions, marked as assumptions until there's data; the weekly metrics |
| **Playbook** | `sales/<product>/playbook.md` | Discovery questions, a demo flow, objections and answers, next-step asks |
| **Outreach** | `sales/<product>/outreach/<slug>.md`, `status: draft` | The sequence (channel, timing, each message in the needed language), the audience definition (segments, not named people), and success metrics |
| **Partnerships** | `sales/<product>/partners.md` | Partner types, value for both sides, the approach, and what the Board must approve |

Use the page front matter from `knowledge/_templates/page.md`, with `owner: ceo`.

## Rules

- **No personal data about individual leads** (names, phones, emails) in the KB, unless the Board approves a lawful basis and a home for it. Describe segments instead. `TODO(board)`: the CRM of record.
- **Every claim to a prospect traces** to the product page or a cited source. Never promise features, timelines or terms that aren't confirmed.
- **Product gaps** customers would pay for go to the product page's open questions, and to the CTO via a directive if the Board wants them built.

## Asking the Board to approve

```
Approve to send?  <what>, to <segment/how many>, via <channel>, <when>
Draft:   <KB path>
Commitments in it: <prices, discounts, terms, or none>
Recommendation: <approve / change X / don't>
```

Record the Board's answer in the page. On approval, the **Board** sends, unless the Board explicitly grants a standing authorization for that channel.
