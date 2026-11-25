---
name: story-sequence
description: Use when the content-producer makes an Instagram story sequence. It covers picking an arc (including the arcs without an offer), rendering frames to PNG inside the safe zones, and writing each link, poll or quiz sticker as a founder phone task with its exact text.
---

# Story sequence

This skill makes one story sequence.

The page:
- `format: story`, using `knowledge/_templates/content-piece.md`;
- no `## Caption` needed (`content_lint` allows it for stories);
- `## Script` holds one line per frame, then the phone tasks.

Related:
- **Facts:** `knowledge/marketing/platform-facts.md`.
- **Copy in a second language:** the `second-language-copy` skill.
- **The AI record:** the `content-qa` skill (F).

**Only when the calendar has one.** The cadence counts reels and carousels; stories aren't in it. Every sticker frame costs the founder phone minutes under his weekly cap, about 2 minutes each.

## 1. Pick the arc

**The classic warm-up** runs: context → problem → behind the scenes → proof → offer. A longer version runs: introduction → problem → insight or cases → answering objections → offer → deadline → the final push. Use the honest version only: no fake scarcity, no invented cases, no fake deadlines.

**Without an offer, these arcs fit the founder's accounts;** once an order has one, the warm-up above runs to it (`funnel-design`):

| Arc | Frames | Fits |
|---|---|---|
| Warm-up without the offer | context → problem → behind the scenes → proof → a question, or a pointer to the week's post | any page |
| News, take, poll | the news (sourced and dated) → his take → a poll or quiz sticker → next day, the result and what he thinks now | a news page |
| Behind the scenes | what he's building or trying → what happened → what he learned → a question sticker | any page |
| Reflection | his reflection → the quoted text's card (`content-qa` E) → a question to reflect on | a reflective page |
| Pointer | a teaser of the week's reel or carousel → the post shared to his story (a phone task) | any page |

- **His voice:** every take, reflection or "what he learned" comes from his raw material, or is drafted in his voice and marked "drafted by us" (`voice.md`; `content-qa` A); a dry run's is `placeholder`.
- **Length:** 3–5 frames.
- **Record the arc** in `## Script`, above the frame list.

## 2. Frames

1. **Copy the template:** one copy of `tools/marketing/templates/story.html` per frame into `workspaces/marketing/media/<brand>/<week>/<slug>/`, named in order (`01-<name>.html`, `02-…`).
2. **Edit the text, and the `:root` colours** from the brand book (`knowledge/marketing/<brand>/brand-book.md`). Fonts: only the vetted ones; `content_lint` fails any other.
3. **Safe zones:** keep all text out of the top 250 px and the bottom 340 px, where Instagram's interface sits. The template's padding does this. The figures are our convention, not yet checked against an official source (platform-facts).
4. **One idea per frame,** in big type. Where both languages show, the first comes first (`second-language-copy`).
5. **Sticker frames:** keep the `.sticker-slot` space, but empty it before the final render: delete its text and its dashed border, and keep its height. The posted frame then shows no placeholder, and the phone task says where the sticker goes.
6. **Render:**
   ```
   node tools/marketing/render/png.mjs --dir workspaces/marketing/media/<brand>/<week>/<slug> --size 1080x1920
   ```
   Read every PNG and check it: nothing clipped, every letter right, text inside the safe zones, the sticker space clear. Fix, render again and look again.
7. **List every HTML file and PNG in `## Assets`.** The AI rules are the same as for carousels (`carousel-design` §3, step 5).

## 3. Sticker frames are founder phone tasks

The publishing API can't add link, poll or location stickers, and quiz stickers aren't documented either way (platform-facts, "The publishing API"). So the founder posts every sticker frame from his phone, from ready assets. Write one block per sticker frame in `## Script`, after the frame list:

```
Phone task: <brand>, <day>, frame <n> of <m> (about <x> min)
1. Post the image: workspaces/marketing/media/<brand>/<week>/<slug>/<nn>-<name>.png
2. Add a <Poll | Quiz | Question | Link> sticker in the empty space <where on the frame>.
3. Type exactly:
   Question: "<first language>" / "<second language>"
   Options:  "<…>" / "<…>"                          (poll, quiz)
   Correct:  "<…>"                                   (quiz)
   Link:     https://<…>   Sticker text: "<…>"       (link)
4. Then post frames <n+1> to <m>.
```

**Rules:**
- **The exact text,** ready to type. Sticker text in the second language is post copy, so it goes through `python3 scripts/language_check.py <page>`, unless that's off (SA-004).
- A quiz's answer or a poll's facts get a line in `## Sources`, with the https link and date, when we have one (a product brand: always; `content-qa` C).
- **Links:** our own posts or pages, the source of a claim, or the offer an order names. A page that collects contacts follows `funnel-design` §3.
- **Contacts:** only with a consent line and a privacy notice, and never a phone number asked for in public comments (`funnel-design` §3).
- **Sticker text limits:** keep the text short. TODO(verify): Instagram's character limits and option counts.
- **His minutes:** the cmo logs them against his weekly cap.
- **Results frames:** story insights last only 24 h (platform-facts). A next-day results frame needs the result from the founder, which is another phone task. Say so in the task.

## 4. Done when

- [ ] The arc is named and fits the brand.
- [ ] Every take or reflection traces to his raw material, or is marked "drafted by us" (a dry run: `placeholder`).
- [ ] 3–5 frames at 1080×1920, text inside the safe zones, every PNG read.
- [ ] Every sticker frame has a phone task with its exact text, and its sticker space is empty.
- [ ] Links point to our own pages, a claim's source or the order's offer; anything that collects contacts has its consent line (`funnel-design` §3).
- [ ] `## Assets` and `ai_generated` / `ai_reason` are true to the media.
- [ ] `python3 tools/marketing/content_lint.py <page>` is clean, then, unless it's off, `python3 scripts/language_check.py <page>`.
