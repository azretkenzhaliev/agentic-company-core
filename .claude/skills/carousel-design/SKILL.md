---
name: carousel-design
description: Use when the content-producer makes a carousel or a single-image post, including news cards and quote cards. It covers slide grammar, the cover, the HTML templates and brand colours, vetted fonts, rendering to PNG, and looking at every slide before calling it done.
---

# Carousel design

This skill makes the slides for one carousel or single post. The page and its sections are in `knowledge/_templates/content-piece.md`.

Related:
- **Facts** (specs, originality, AI labels): `knowledge/marketing/platform-facts.md`.
- **Format choice:** the `instagram-formats` skill.
- **Copy in a second language:** the `second-language-copy` skill.
- **The AI record:** the `content-qa` skill (F).

## 1. Slide grammar

1. **Slide 1 is the cover.** It carries the hook: one claim, question or number, with its source. It has to stop the scroll and read in the 4:5 profile grid.
2. **One idea per slide.** Each slide's last line makes the next one worth a swipe.
3. **The last slide is the CTA for the funnel stage** (the table in `instagram-formats` §1).
4. **As many slides as the idea needs,** at most 10 (what `publish/post.py` schedules; the API's limit is 20). No filler.
5. **In `## Script`,** write one line per slide: `NN | headline | body | image`.

## 2. Cover rules

- **The hook in big type** (the template's `h1`), in few words.
- **Every slide 1080×1350.** The first item sets the crop for all of them (platform-facts).
- **Fits the grid:** it works in the cmo's 3×3 grid preview (`knowledge/marketing/<brand>/grid.md`).
- **Not the last post's cover:** no near-identical templated posts in a row. Before choosing, open the brand's last three pieces in `knowledge/marketing/<brand>/content/`, and change the layout, the colour use or the structure.
- **Never** words rendered by an AI model, and never a screenshot of someone else's media.

## 3. Make it

1. **Folder:** `workspaces/marketing/media/<brand>/<week>/<slug>/` (gitignored).
2. **Copy one template per slide** into it, named in slide order: `01-cover.html`, `02-<name>.html`, and so on. The renderer works in name order.

   | Template (`tools/marketing/templates/`) | For |
   |---|---|
   | `carousel.html` | any 4:5 slide |
   | `news-card.html` | news: the headline, the founder's take box and the required source line (§4) |
   | `quote-card.html` | quotes (§5) |
   | `story.html` | story frames (the `story-sequence` skill) |

3. **Edit only the text and the `:root` colours** (`--bg`, `--fg`, `--accent`, `--muted`), taking the colours from the brand book's visual rules (`knowledge/marketing/<brand>/brand-book.md`). Change the layout CSS only where a slide needs it.
4. **Fonts:** only `'Montserrat'` and `'Golos Text'`, with a generic fallback such as `sans-serif`.
   - Both cover Latin and Cyrillic. Check that they hold every letter of your languages before the first render.
   - `content_lint` fails any other family.
   - The renderer injects the fonts and `templates/base.css`.
5. **Images in a slide:** only these.

   | Image | Provenance | `ai_generated` |
   |---|---|---|
   | Our own renders | `own-render` | – |
   | The founder's photos | `board-supplied` | – |
   | Text-free AI images (SA-005, on the capped key, once it exists) | `ai-generated` | `true`; Instagram's label is the Board's choice on the post |

   Other people's images only as stills from outside footage fetched with `tools/marketing/footage/fetch.py` (provenance `outside`, credited; `content-qa` I); never screenshots or images that came any other way. Reference images by a path relative to the HTML file.
6. **Render:**
   ```
   node tools/marketing/render/png.mjs --dir workspaces/marketing/media/<brand>/<week>/<slug> --size 1080x1350
   ```
   For a single post: `--html <file> --out <file>.png --size 1080x1350`.
7. **Look at every PNG** with the Read tool before calling it done. Check:
   - no text overflows or is clipped;
   - every letter of the language matches the rest of the text, with no fallback font and no boxes;
   - the contrast is readable;
   - the slide numbers are right;
   - the first language comes first where both show;
   - the cover still reads small.

   Fix the HTML, render again and look again. A slide nobody has looked at isn't done.
8. **List every HTML file and PNG in `## Assets`.** Listing the HTML lets `content_lint` check its fonts.

## 4. News card

- **The headline:** the news in one line, as the source states it.
- **The source line:** the publisher and the date, when we have them. The same claim goes in `## Sources` with its https link and date (YYYY-MM-DD); `content_lint` checks the line's format. On the founder's pages a news claim with no source is a `Board note:` on false news, never a block; on a product brand it's a blocker (`content-qa` C).
- **The take box:** the founder's words from his raw material, or drafted in his voice and marked "drafted by us" (`voice.md`); a dry run's says "placeholder: …" (`content-qa` A).
- **Our own visual only:** no screenshot of the article, the product or a video.

## 5. Quote card (and other text posts)

- **The quoted text:** the rule in `content-qa` E.
- **Background:** plain or abstract: the template's colours, or a text-free abstract or nature image. What the brand book says about imagery on a subject it cares about comes first.
- **Arabic script:** only in Scheherazade New, as `font-family: 'Scheherazade New', 'Golos Text', sans-serif` so any other text falls back to a vetted font (`content_lint` checks this). A right-to-left script: give its element `dir="rtl"` and its `lang`.
- **Reflection slides:** the founder's words from his raw material, or drafted in his voice and marked "drafted by us" (`voice.md`; `content-qa` A).

## 6. Done when

- [ ] The cover hooks and reads in the 4:5 grid.
- [ ] One idea per slide, with the CTA last.
- [ ] Every slide is 1080×1350 and uses only the vetted fonts.
- [ ] Every PNG has been read and looks right.
- [ ] Not a near copy of the brand's previous post.
- [ ] Each source we have is in `## Sources` with its link and date (a product brand: one for each claim).
- [ ] `## Assets` lists every HTML file and PNG with its provenance, and `ai_generated` / `ai_reason` are true to them.
- [ ] `python3 tools/marketing/content_lint.py <page>` is clean, then, unless it's off, `python3 scripts/language_check.py <page>`.
