---
title: "Marketing core: cmo"
owner: cmo
status: active
updated: 2026-01-01
related: [shared.md, README.md, ../format-engine.md]
---

# Core: cmo

With `shared.md`. Your agent file holds your rights and the weekly batch; this page points to what you open most: taste pages, `format-engine.md`, brand books, `notion.md`, `craft-standard.md`, red lines.

## Taste in force
- Each brand's `taste.md`: the lines under "In force", which the Board put in force himself; his correction on any piece wins. Sessions are specified in its `taste-library.md`.

## Picking a format (`instagram-formats` §1)
- Drop a format that needs material we don't have (a take with no raw material isn't one: we draft it), costs more of his minutes than the week has left, or breaks a brand rule.
- Score the rest 0–3 on stop power, watch-through, sends, saves, follows and comments, fit to the stage, and his minutes; take the highest; on a tie, the format the week has fewest of, then fewer of his minutes. Write the format and a one-line reason in the calendar row.
- Music for every piece: one recommended track and one alternative, or "no music: his voice"; the Board adds it at publishing (`instagram-formats` §5).

## The calendar (`content-calendar`)
- Sections: raw material; plan (Day, Format, Pillar, Goal, Funnel stage, Hook idea, Raw material, Filmed, AI, Piece page); grid preview; the Board's time against his weekly cap; usage; approvals; log. `status: draft` until the Board has reviewed.
- A hook idea is a format idea, never his opinion; it cites its card `formats/FC-…`, else a `language/hooks.md` pattern.
- Balance, against the last two calendars: no formula more than twice a week; one piece built to be saved and one to be sent; each feed post reshared to stories, about a minute of his.
- `Publish at` carries the brand's UTC offset (`timezone` in `company.json`).
- Add pieces only while his measured minutes stay under his cap; over it, cut filmed reels first, then carousels.
- An `ai_generated: true` piece's recommendation says so. An approvals row with a note blocks scheduling (`content-calendar`, "After the Board's review", step 5).

## Formats (`format-engine.md`)
- A format is judged by watching the reel, never its cover. Multiple: views ÷ median views of the account's 9 newest reels; a format's weight is the median multiple of its recent (90 days or less) reels, with how many reels and accounts.
- A card needs 3 or more watched reels from 2 or more accounts, each ×2 or more; structure and mechanics only, in our words; retire one unseen for 8 weeks.

## Pages you curate
- Brand book, pillars, grid: one complete recommended draft, at most one alternative per contested point; a `TODO(board)` there is undecided (`brand-book`).
- `platform-facts.md`: re-check a fact past its `ttl_days` with the analyst before relying on it.
- Notion ids and the sync: `notion.md`. Craft rows and the correction loop: `craft-standard.md`.
