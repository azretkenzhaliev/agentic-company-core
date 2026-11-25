---
title: Marketing
owner: cmo
status: draft
updated: 2026-01-01
related: [../sales/README.md, notion.md, craft-standard.md, format-engine.md, platform-facts.md]
---

# Marketing

**Owner: the CMO** (`.claude/agents/marketing/cmo.md`), under the CEO. The department is **optional**: until the Board switches it on (`docs/marketing.md`), nobody starts the CMO, and the CEO writes what marketing it needs itself, as drafts, by the table and checks in the CMO's file ("Other marketing work").

The department makes Instagram content in weekly batches:
- the CMO plans;
- the content-producer makes the content from the founder's raw material;
- the content-reviewer checks it;
- the Board approves each piece in the Notion calendar.

Nothing leaves the company without the Board.

## Brands, in order

A brand is a folder here: `founder/<account>/` for one of the founder's own accounts, `<brand>/` for anything else. Its settings are in `company.json` (`integrations.marketing.brands`). Copy [_brand/](_brand/README.md) to start one.

| Account | Folder | What | Status | Gate | Cadence |
|---|---|---|---|---|---|
| TODO(board): your first account | `founder/<account>/` | TODO(board): what it's about, in one line | not started | TODO(board): what must be true before it posts or sells | about 2 reels and 1–2 carousels a week until the Board sets it (a quieter, reflective page: 1 post a week) |

- **Status:** not started, live or paused, in the Board's words. A brand starts on the Board's word.
- **Gate:** "none", or what lifts it. A gated brand gets no post, funnel, lead form or ad until the Board lifts the gate.
- TODO(board): the languages, the market and the goals (followers, reach, sales), per brand.

## Layout

| Path | Owner | What |
|---|---|---|
| `<brand>/brand-book.md`, `pillars.md`, `grid.md` | cmo (drafts; the Board approves) | Audience, voice, languages, pillars and rubrics, visual rules, the Board's own never-post list, the 3×3 grid plan |
| `<brand>/voice.md` | cmo | The founder's voice: his corrections to our drafted takes, and whether he wants only his own words |
| `<brand>/references.md`, `taste.md` | cmo (`taste.md` is a draft until the Board's picks) | The Board's reference accounts with its remarks, and what it has said on the page's look |
| `<brand>/calendar/<YYYY-Www>.md` | cmo | The week's plan, cadence, the Board's expected minutes and the batch's usage |
| `<brand>/content/<YYYY-Www>/<slug>.md` | content-producer | One page per piece, from [the template](../_templates/content-piece.md); media in `workspaces/marketing/media/` (gitignored) |
| `<brand>/approvals/<YYYY-Www>.md` | board, written by `scripts/notion_approvals_sync.py` | The Board's decisions from Notion. No agent writes these |
| `<brand>/positioning.md`, `icp.md`, `channels.md`, `campaigns/C-NNN-<slug>.md` | cmo | As in the CMO's prompt; `icp.md` is shared with sales |
| `<brand>/metrics.md`, `learnings.md` | performance-analyst | Weekly stats and dated learnings |
| [_brand/](_brand/README.md) | cmo | The templates of a brand's pages |
| [language/](language/README.md) | cmo | The language layer: rules and glossary, hooks, captions, red lines, calendar |
| [platform-facts.md](platform-facts.md) | cmo | Instagram and Meta facts with sources; 30-day TTL |
| `playbooks/` | cmo | Created with the first card: summary cards, one per framework, from official sources (later from books), with `verified_against_text`; official cards have a 30-day TTL (`book-to-cards` skill) |
| [format-engine.md](format-engine.md), `formats/` | cmo | The weekly format engine: the read, the watched reels, the format cards made from them, and each page's weekly improvement session |
| [craft-standard.md](craft-standard.md) | cmo | What our pieces are checked against: subtitles, pacing, hook, colour, writing, story, each number marked measured or "to test" |
| [notion.md](notion.md) | cmo | The Notion "Marketing calendar": fields, who sets each, the sync |
| [cores/](cores/README.md) | cmo | Each marketing role's core, loaded at spawn with the shared one: rules' operative words and pointers, at most 10,000 characters a role |
| [idea-sources.md](idea-sources.md) | cmo | The channels and newsletters behind the weekly idea note, and the Telegram server |
| `workspaces/marketing/intelligence/` (gitignored) | trend-researcher; `reels/` the reel-analyst | The weekly intelligence table `<ISO week>.md` and the growing `posts.csv`, read from public Instagram, YouTube and Telegram pages in the reader profile. `reels/` holds each watched reel's folder (`<code>/`, with its `breakdown.md`) and the week's `<ISO week>-formats.md`; format labels in `posts.csv` come only from these. Where `backup_folder` is set, a nightly copy goes there (`tools/marketing/README.md`, "Nightly copy") |

## Rules

- **Nothing is published, posted, sent or paid for without the Board.** The cmo schedules only approved pieces in Metricool, with `autoPublish` false, and the Board publishes each one himself in Metricool's app. No agent holds a DM or ad tool, and only the trend-researcher a browser (`scripts/hooks/guard_marketing_tools.py`).
- **The trend-researcher only reads.** It is the one role with a browser: public pages on instagram.com, youtube.com and t.me, in the reader profile the founder set up (`docs/marketing.md`, "The reader profile"). It never likes, follows, comments, messages, posts, signs up or logs in, and it stops at any login, verification or block page. What it keeps about a person is the public account and post numbers, and two things more: a shortlisted reel's public caption, up to 230 characters, with `@` handles, emails and phone numbers masked, and one other public handle per collab (`.claude/agents/marketing/trend-researcher.md`).
- **The founder's pages:** agents write in his voice, in the first person, from his material when there is some, and learn from his corrections (each account's `voice.md`). His Approved on each post is the one gate there; a point of law is a one-line note to him ([language/red-lines.md](language/red-lines.md)), except one that page's brand book records as a blocker.
- **Product brands:** claims trace to a source: the product pages, the Board or a cited research note. A breach of the law or the red lines is a blocker in review. Never invent numbers, testimonials or features.
- **A second language:** checked by Gemini (SA-004, `scripts/language_check.py`), unless the Board turned that off, then read by the Board; on-image text only in the vetted fonts.
- **Metricool, Notion and Canva** are the founder's own claude.ai connectors. Only the cmo and the performance-analyst read Metricool, through its five `get…` reads. The one write allowed is the cmo's `createScheduledPost` of a staged, approved piece with `autoPublish` false. The hook blocks the rest (`createScheduledPostForReview`, `updateScheduledPost`, `sendScheduledPostForReview`) for everyone.
- **Gmail:** the analyst reads the mail an order names, through `search_threads`, `get_thread`, `get_message` and `list_labels`. The hook blocks every other Gmail tool for every other agent, so no marketing agent sends, drafts or changes mail.
- **Telegram** (a local read-only server): the analyst reads only the channels on [idea-sources.md](idea-sources.md), never a private chat. No other agent reads it, and the server has no write tool.
- **Cadence and usage:**
  - weekly batches only;
  - each account's cadence in the table above;
  - the Board's time at most 2 h a week across all accounts (a default; the Board's to change);
  - no usage cap on marketing. A batch still reports its tokens: the sum of its agent runs from the Agent results.

## Channels

- **Instagram** is the department's channel. Everything else is a plan in the brand's `channels.md` until the Board opens it.
- **YouTube Shorts** (a brand with `shorts` true, through the same Metricool brand). A Short is its own piece: its own page, its own Notion item (Format `short`) and its own approval, even when it reuses a reel's cut. Its title and description never carry the Instagram handle. It is always sent **private** with `madeForKids` false, may go up at its set time without a tap in Metricool's app, and becomes public only when the Board makes it so in YouTube Studio. Its AI flag follows `ai_generated`.
- **Telegram, WhatsApp, paid ads:** not built here. Each needs the Board first.
