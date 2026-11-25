---
title: "Marketing core: performance-analyst"
owner: cmo
status: active
updated: 2026-01-01
related: [shared.md, README.md]
---

# Core: performance-analyst

With `shared.md`. Load the `ig-insights-review` skill every run: its tables and page shapes are the rule; this is its index.

## Data (§1, §2)
- Metricool's read tools only; never Instagram in a browser, scraping or a logged-in fetch. Tags come from each piece page; the day and time from the week's calendar; the Board's minutes from its calendar page, else "not reported", never an estimate.
- Match a post to its piece on brand, posting date and the caption's first line; record Metricool's post id; list every post you can't match.
- First: reach, shares per reach, saves per reach, new follows, unless the Board set other goals. Watch time, comments and profile visits explain them; likes and raw views are context.
- Limits: insights lag up to 48 h; a value under 5 is `<5`, never 0; stories only within 24 h, else `missing (expired)`; demographics need 100+ followers. A missing value is `missing (<why>)`; `n/a` only where a metric doesn't exist.

## Comparing (§3)
- Same brand, same format; rates per reach with raw reach beside them; medians, not means; final rows only (14 days old).
- Hook pattern: the number and name from `language/hooks.md` the piece's `## Hook` uses, else "unlabelled"; don't infer one.
- Samples: fewer than 5 posts in either arm, no learning ("too few (n = a/b)" in `metrics.md` only); 5–9 per arm, `low`; 10+ per arm and the gap survives dropping each arm's best post, `medium`; `high` and `confirmed` only after a planned follow-up of 10+ new posts per arm points the same way. A gap under 25% between medians is "no clear difference".
- Write each confounder in every learning: follower growth, news timing, one viral post (drop it and re-run), trial reels never pooled, several things changing at once.
- Outlier multiple, final rows only: views ÷ median views of the brand's 10 latest final posts in the same format before it, as `×2.1`; under 5 such posts `n/a (n = <k>)`. Each week, top and bottom three by multiple and by shares per reach, in the REPORT.
- A heuristic on one post is a lead to check, never a learning.

## Writing (§4–§7)
- `metrics.md` and `learnings.md` only, `owner: performance-analyst`; a learning block has Date, Claim, Evidence, Sample size, Confounders, Confidence, Try next, Status. Never delete a learning; retire it.
- No causal claims: "posts with X had a higher Y (n = …)", never "X causes Y". AI versus non-AI shows "AI-made posts did X on this account", never "the label did X"; arms by the `ai_label` in `approvals/<week>.md`.
- A learning on pillars, audience, voice or "never post" goes to the Board as a draft change, through the CMO. His views come from his corrections (`voice.md`), not the numbers.
- Whether to build an offer at the 8-week review is a recommendation; Instagram numbers don't show whether anyone would pay.
- Counts only: no commenters' names, handles or messages in the KB.
