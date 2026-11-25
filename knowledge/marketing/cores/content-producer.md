---
title: "Marketing core: content-producer"
owner: cmo
status: active
updated: 2026-01-01
related: [shared.md, README.md, ../craft-standard.md]
---

# Core: content-producer

With `shared.md`: the craft of five skills, short; `content-qa` you read in full. Open a skill for its detail and commands.

## Before a piece
- Read the brand's `brand-book.md`, `voice.md` (his corrections first), `pillars.md`, `grid.md`, `taste.md`'s in-force lines and the last two `approvals/`. A brand-book rule beats a skill; a `TODO(board)` there is undecided: don't decide it in a piece (`brand-book`).
- Open the brand's last three pieces: no near-identical templated post in a row; change the layout, structure or format (`instagram-formats` §4).
- The calendar sets the format; if the material doesn't fit, say so and propose another; never edit the calendar (`instagram-formats`).

## Every format
- Reel and story 1080×1920; carousel and single post 1080×1350, every slide the same size; at most 10 items (`instagram-formats` §3).
- No text in the top 250 px or bottom 340 px; a reel cover keeps text and face in its centre 4:5 (`reel-script` §3; `instagram-formats` §3).
- Read every PNG and frame before calling it done; check each screen, document or label in the background at 1080 wide (`carousel-design` §3; `content-qa` F).
- CTA by funnel stage: awareness, follow or send it to someone; consideration, save it; loyalty, answer a question in the comments; conversion, the offer's CTA once an order has one, else a follow. Never ask for phone numbers or contacts in comments (`reel-script` §6).

## Reels (`reel-script`)
- The hook lands by 2 s on picture, spoken line and on-screen text; the first frame shows something, not a logo or title card; open a loop the reel closes; 2–3 variants in `## Hook` (§1).
- News: lead with what it means to the viewer, in his words; say when it happened, on screen or in the caption (§1, §8).
- `## Script`: one beats table (t, beat, spoken, on-screen text, picture) and the total length; the shortest that carries the idea; every beat earns the next; a re-hook in a long reel; the payoff beats the hook's promise (§2).
- Subtitle size and colour, cuts a minute, loudness: the brand's `taste.md`, then `craft-standard.md`, whose Board rows replace §3's defaults. At most 20 characters a second and 42 a line, contrast 4.5:1 or more, one text layer at a time, each card a whole thought: never end on a preposition or before its number (`craft-standard.md`).
- Word captions: one `Captions` overlay for the whole reel, never one per card or word (§3).
- Filmed: §4's shot list, setups grouped, one-breath lines, ending "how long it took: __ min".
- Music: none baked in by default; the CMO's pick is added at publishing. An outside bed or sound only with `"music_ok": true`; on the founder's pages, compile without it and write one `Board note:` naming the file and its licence (§5d).
- Outside clips only through `footage/fetch.py`: our layer over them, each source credited on screen or in the caption, each clip only as long as its point, no cut that changes what was said (§5d; `content-qa` I).
- AI b-roll: text-free shots, each with its prompt and why AI rather than his footage, which is used wherever it exists (§5c).

## Carousels, single posts, stories
- Slide 1 is the hook in big type; one idea per slide, its last line worth a swipe; the CTA last; no filler. `## Script`: `NN | headline | body | image` (`carousel-design` §1).
- One template copy per slide, named in order; edit only the text and the `:root` colours from the brand book; a right-to-left script sets `dir` and `lang`. Images: our renders, his photos, text-free AI images, stills fetched by `fetch.py`; never a screenshot (`carousel-design` §3, §5).
- Stories only when the calendar has one: 3–5 frames, the arc named, honest arcs only (no fake scarcity, cases or deadlines). Each sticker frame is a founder phone task with the exact text; empty the `.sticker-slot`, keep its height (`story-sequence`).

## The second language (`second-language-copy`)
- From his raw material or the drafted take, its meaning only; never machine-translate blindly or invent a word: a form not in `language/language-rules.md`'s glossary is listed in `## Language check` as "not in the glossary".
- A source line in the first language for every block in the second: the caption's other block, else pairs per beat or slide.
- Apply the `language_check` fixes you agree with, re-render, run it again if anything changed; the remaining flags and the model name go in `## Language check` and Notion's Gemini flags. Never run `security` or print a key.
