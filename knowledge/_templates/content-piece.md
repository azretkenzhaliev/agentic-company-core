---
title: "<Day> <format>: <short name>"
owner: content-producer
status: draft
updated: YYYY-MM-DD
related: [../../calendar/YYYY-Www.md]
brand: founder/<brand>
week: YYYY-Www
format: reel | carousel | post | story | short
pillar: <a pillar from the brand's pillars.md>
funnel_stage: awareness | consideration | conversion | loyalty
filmed_by: founder | none
ai_generated: true | false
ai_reason: "<why: e.g. 'AI b-roll in shots 3-4' or 'HTML/CSS renders and the founder's own footage only'>"
raw_material: <path to the founder's voice note or notes, or: drafted | placeholder>
piece_status: draft | in-review | ready-for-board
languages: [en]
---

# <Day> <format>: <short name>

One piece of one brand-week. Written by the content-producer (`content_lint` checks it: `python3 tools/marketing/content_lint.py <this page>`). The Board's decision is in `../../approvals/YYYY-Www.md`, written by the sync script.

## Raw material

What the founder said or wrote, quoted or linked. Without the founder's material, `raw_material: drafted`: the take is drafted in the founder's voice from what we know, and the Board corrects it. A dry run writes "placeholder" here and on every take.

## Hook

The first 1–2 seconds (reel) or the cover (carousel): on-screen text and spoken line.

## Script

Reels: beats with timings, spoken lines (in the languages the brand book names), on-screen text, and for founder-filmed reels the shot list and direction notes (framing, delivery, props, location, takes). Carousels: one line per slide. Stories: one line per frame, with sticker tasks for the founder.

## Caption

```text
The caption exactly as posted: the first language whole, then each other language's full block. At most 2,200 characters on Instagram (a Short: see `## Post`).
```

## Hashtags

#tag1 #tag2 (at most 5, counted together with any in the caption)

## Post

What goes to Instagram (`tools/marketing/publish/`). Type is image, carousel or reel. A YouTube Short is `format: short` with `- Type: short` and one `- Title:` line, its YouTube title (100 characters at most, no `<` or `>`): one .mp4, no cover. Its caption is the video's description (5,000 bytes of UTF-8 at most, no `<` or `>`). Publish at is the calendar's time with its UTC offset. List the files from the piece's media folder in posting order; a reel may add a `cover` row last. Then run `python3 tools/marketing/publish/post_hashes.py <this page>`, and again after any file changes.

- Type: carousel
- Publish at: 2026-01-05T18:00+00:00

| # | File | SHA-256 |
|---|---|---|
| 1 | 01-cover.png | – |
| 2 | 02-slide.png | – |

## Assets

| File | Provenance | AI | Notes or prompt |
|---|---|---|---|
| workspaces/marketing/media/<brand>/<week>/<file> | own-render \| own-footage \| ai-generated \| board-supplied | yes \| no | the generation prompt, for AI assets |

## Sources

- <each factual or news claim> — https://<source> (YYYY-MM-DD)
- <text the Board provided> — provided by the Board

## Language check

Only for a piece in a second language, once the founder has set the key (SA-004, `docs/marketing.md`): the model that ran, and the flags left after the fixes. The Board reads the second language itself during approval.

## Review

The content-reviewer's findings for this piece, copied in by the producer with the round number, and what changed.
