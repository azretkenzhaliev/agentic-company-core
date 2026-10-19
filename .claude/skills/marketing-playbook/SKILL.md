---
name: marketing-playbook
description: Use when the CEO, acting as CMO, works on marketing for a product, such as positioning, the ideal customer profile, messaging, channel plans, campaigns, launch plans, content calendars, landing-page or social-post copy, or marketing metrics.
---

# Marketing playbook (the CEO as acting CMO)

Marketing work produces **reviewed drafts and plans in `knowledge/marketing/<product>/`**. Nothing is published, posted, sent, boosted or paid for without the Board's explicit approval (charter: external messages, public statements, spending). This playbook is the seed of the future CMO agent's prompt.

## Before any task

1. Read `knowledge/products/<product>/README.md`, everything in `knowledge/marketing/<product>/` and `knowledge/sales/<product>/`, and the related research notes in `knowledge/research/`.
2. **Find the blocking unknowns.** If a fact the work depends on is `TODO(board)` (target users, languages, pricing, brand voice), ask the Board first, or ask for research. Don't draft on guesses.
3. Need market facts (competitors, channel benchmarks, audience size)? Send the `analyst` one order per question, through the directive.

## Procedures

| Task | Write to | Must contain |
|---|---|---|
| **Positioning** | `marketing/<product>/positioning.md` | Target segment; their problem in their words; alternatives, including "do nothing"; what's uniquely better, with proof; a one-sentence positioning statement; three messaging pillars; top objections and answers |
| **ICP and personas** | `marketing/<product>/icp.md` | Who buys and who uses; jobs to be done; trigger events; where they spend time online and offline; decision process; who's *not* a fit |
| **Channel plan** | `marketing/<product>/channels.md` | Candidate channels with effort, cost, expected reach and how to measure each; the one or two to test first and why; the budget needed (the Board approves) |
| **Campaign** | `marketing/<product>/campaigns/C-NNN-<slug>.md` | Goal and metric; audience; message and offer; channel; assets list; timeline; budget (the Board approves); success criteria; a results section filled in afterwards |
| **Copy** | `marketing/<product>/content/<slug>.md`, `status: draft` | The draft in each needed language, two or three variants of headlines and CTAs, where it would appear, and a source for every factual claim |
| **Metrics** | `marketing/<product>/metrics.md` | What's measured and where (`TODO(board)` if there's no analytics yet); a weekly snapshot table |

Use the page front matter from `knowledge/_templates/page.md`, with `owner: ceo`.

## Rules

- **Every claim traces** to the product page, the Board, or a cited research note. Never invent numbers, customers, testimonials, awards or features.
- **Write for the market's languages.** Until the Board confirms them, mark language choices `TODO(board)`.
- **Engineering needs** (landing-page changes, analytics, tracking, SEO fixes) go to the CTO as an order, inside the directive.
- **No personal data** about individuals in marketing pages.

## Asking the Board to approve

When a draft is ready to leave the company, ask with AskUserQuestion, or in plain text for long drafts:

```
Approve to publish?  <what>, on <channel/where>, <when>
Draft:   <KB path>
Cost:    <amount, or none>
Expected result: <metric and target>
Recommendation: <approve / change X / don't>
```

Record the Board's answer in the campaign or content page. On approval, the **Board** publishes, unless the Board explicitly grants a standing authorization for that channel.
