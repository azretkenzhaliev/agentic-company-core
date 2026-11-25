---
name: instagram-formats
description: Use when the cmo picks the format for an idea in a brand-week (reel, carousel, single post or story sequence), or when the content-producer checks a piece against Instagram's specs, publishing-API limits, and its originality and AI-label facts before making it.
---

# Instagram formats

Pick the format for each idea, then meet the specs. The facts behind this skill, each with its source and kind (official or practitioner), are in `knowledge/marketing/platform-facts.md`. Check that page's `last_verified` plus `ttl_days` first. If it's past, write "platform facts stale: re-verify" in your report and name the rows you relied on.

**Who decides:**
- The cmo picks each piece's format when it writes `knowledge/marketing/<brand>/calendar/<week>.md` (`CLAUDE.md`, the CMO's decision rights).
- The content-producer follows the calendar. If the raw material doesn't fit the format (for example, a filmed reel with no footage), it says so in its report and proposes another format. It never edits the calendar.

## 1. Pick the format

Inputs: the calendar row (pillar, goal, `funnel_stage`, hook idea), the founder's raw material, the week's mix so far, and the founder's minutes left this week. Rules per brand: `knowledge/marketing/<brand>/brand-book.md`, `pillars.md` and `grid.md` (the `brand-book` skill).

**Step 1. Drop a format if any of these is true:**
- It needs material we don't have: a filmed reel with no footage or filming slot this week. A take with no raw material isn't one: we draft it in his voice, marked "drafted by us", for the Board to correct (`content-qa` A).
- It costs more founder minutes than the week has left under his cap. Filming, sticker phone tasks and adding music in the app all cost his minutes.
- It breaks a brand rule, such as a brand book's bar on screenshots or on someone else's video.

**Step 2. Score each remaining format 0–3 per signal.** The first five signals are what Meta's ranking predicts (platform-facts, "Ranking signals").

| Signal | A 3 looks like | Often strongest in (a hypothesis) |
|---|---|---|
| Stop power: not skipped in the first 2 s, watched at least 3 s | Picture, voice and on-screen text all hook within 2 s | reel; a carousel's cover |
| Watch-through, compared with reels of the same length | Every second earns the next; no padding | reel |
| Sends per reach (counts most for non-followers) | There's a specific person the viewer would send it to | reel |
| Saves | Reference value: steps, a checklist, something to come back to | carousel |
| Follows and comments | Part of a series; a real question to answer | reel or carousel series; stories |
| Fit to the awareness stage | Matches the step 3 table | – |
| Founder minutes | 3 = no extra minutes; 0 = most of what's left this week | – |

The third column is a practitioner hypothesis (platform-facts, "Hypotheses to test"), not a fact. Weights start equal; the performance-analyst re-weights them from our data. Take the highest total. On a tie, take the format the week has fewest of, then the one that costs the founder fewer minutes.

**Step 3. Match the awareness stage** (`funnel_stage` in the piece's front matter):

| `funnel_stage` | The viewer | Default format | CTA on the founder's accounts |
|---|---|---|---|
| awareness | Doesn't know him (non-followers) | reel | follow; send it to someone |
| consideration | Follows; deciding whether he's worth their time | carousel; reel | save it |
| loyalty | Follows and engages | story sequence; carousel | reply; comment |
| conversion | Ready to act | the offer's post or story, once an order has an offer (`funnel-design`) | the offer's CTA; until then, a follow |

This mapping is our default, a hypothesis to test, not a fact.

**Step 4. Record it.** The cmo writes the format and a one-line reason in the calendar row, for example "reel: sends; news hook; his clip exists". The producer sets `format:` in the piece's front matter.

## 2. When each format fits

- **Reel:** reaching non-followers. Small creators' public posts are shown to non-followers to test them, and sends count most for that reach (platform-facts). Three paths, all in `reel-script`: founder-filmed; a text reel (Remotion TextReel); his voice or AI b-roll over our renders (SA-005). Filmed reels are optional: AI-produced reels count toward the cadence.
- **Compilation reel:** his clips and outside clips (films, series, TV news, other people's videos, stock) cut together under his voice, our text and subtitles: news reactions, explainers, "what this looks like". The clips serve his point; see `reel-script` §5d and `content-qa` I.
- **Carousel:** one idea in steps, worth saving. At most 10 items (what `publish/post.py` schedules; the API's limit is 20). See `carousel-design`.
- **Single post:** one image, one idea: a news card or a quote card. See `carousel-design` (a one-slide carousel).
- **Story sequence:** followers; interaction (polls, quizzes, questions) and behind the scenes. Story insights last only 24 h. See `story-sequence`.

## 3. Specs

Details and sources: platform-facts, "Formats and specs" and "The publishing API". Renderer commands: `tools/marketing/README.md`.

| | Reel | Carousel | Single post | Story frame |
|---|---|---|---|---|
| Canvas | 1080×1920 (9:16) | 1080×1350 (4:5), every slide | 1080×1350 (4:5) | 1080×1920 (9:16) |
| Made with | footage plus `video/subtitles.mjs`, `render/reel.mjs`, or `video/compile.mjs` (a cut from clips) | `render/png.mjs --size 1080x1350` | `render/png.mjs --size 1080x1350` | `render/png.mjs --size 1080x1920` |
| Length | Up to 3 min in the app; 3 s to 15 min through the API. The shortest the idea needs | 2 to 10 items | 1 image | Video frames 3–60 s |
| Caption | At most 2,200 characters | same | same | none (`content_lint` allows it) |
| Hashtags | At most 5, caption and `## Hashtags` together | same | same | – |

- **Captions:** the first language, then, on a brand with two, a full block in the second, unless the brand book says otherwise (`knowledge/_templates/content-piece.md`; the `second-language-copy` skill).
- **Same ratio throughout:** every carousel item is cropped to the first item's ratio, so render every slide at the same size.
- **JPEG for the API:** it takes single images as JPEG only (≤ 8 MB). Our renders are PNG, and `publish/` uploads them as they are: TODO(verify) whether Metricool converts them, and whether carousel images must be JPEG too, before the first PNG is scheduled.

**Cover rules:**
- **Reel cover:** a chosen frame, or our own rendered JPEG (`cover_url`, ≤ 8 MB). The profile grid crops to 4:5, so keep the cover's text and face inside the centre 4:5 area of the 9:16 frame.
- **Carousel cover:** slide 1 is the hook. It also sets the crop for every slide.
- **Grid:** covers fit the brand's `grid.md`; the cmo checks the 3×3 preview.
- **Text:** only rendered in code, in the vetted fonts. Never let an AI model write the words: image models garble letters.

## 4. Originality (craft, every format)

Instagram's rules on original content are never a block (`content-qa` F). What they reward is craft: accounts that mostly post unoriginal content aren't recommended to non-followers, judged over about a month (platform-facts, "Originality"). Borders, watermarks, subtitles or a credit line alone don't make a post original.
- Make each post wholly ours or materially edited, with our own commentary, voice or text and real edits over any outside clip. Other people's media only as outside clips, credited, with a manifest (`content-qa` I).
- **No near-identical templated posts in a row** (craft). Before choosing a template, open the brand's last three pieces in `knowledge/marketing/<brand>/content/`. Change the layout, the structure or the format from the last post.

## 5. What the publishing API can't do

Each of these becomes a founder phone task or a Board step. Count his minutes against his weekly cap.

| The API can't | So |
|---|---|
| Publish without the Board | Metricool schedules with `autoPublish` false: its app notifies the Board at the time, who publishes (`content-calendar`, "After the Board's review"). Without Metricool, the Board schedules the week's posting kit in Meta Business Suite |
| Add link, poll or location stickers (quiz isn't documented either way) | A founder phone task with the exact sticker text (`story-sequence`) |
| Attach music (our publisher sends no audio; `knowledge/marketing/platform-facts.md`, "Music and audio") | **The cmo pre-selects music for every piece:** one recommended track and one alternative, or "no music: his voice". The Board adds it in the app at publishing; the page names the track and where it starts |
| Take media from our disk | A private bucket with short-lived signed URLs (`tools/marketing/publish/`) |

## 6. AI-label facts that change a format choice

Sources: platform-facts, "AI labels" and "AI-generated profiles"; SA-005. The AI record is the `content-qa` skill's (F). Whether a post carries Instagram's AI label is the Board's choice on each post, in Notion (SA-005).
- **AI images or video:** the files carry C2PA marks, which Meta reads. With the Board's AI label off, the copy uploaded to Instagram goes without its C2PA, XMP and IPTC (`publish/strip_ai.py`); a watermark in the pixels, such as SynthID, stays. Set `ai_generated: true` with the reason either way. A Short goes to YouTube as made, and its YouTube flag follows `ai_generated`.
- **One label per post:** the Board's AI label is one flag for the whole post, a carousel included; with it off, every file of the post goes up stripped.
- **No AI marker:** HTML/CSS renders and edits of the founder's own footage carry none. Then `ai_generated: false`, with the reason "own renders and own footage only".
- **Pick the format on the signals,** not on the label, and keep same-format AI and non-AI pieces comparable for the 8-week review.
- **Never words rendered by an AI model** (SA-005).

## 7. Before `content_lint`

The producer checks:
- [ ] The format matches the calendar, or the mismatch is in the report.
- [ ] The canvas size matches the table; every carousel slide is the same size.
- [ ] The caption is at most 2,200 characters: every block in full, in the brand book's order.
- [ ] At most 5 hashtags, caption and section together.
- [ ] The cover reads in the 4:5 grid crop.
- [ ] Not a near copy of the brand's previous post (craft, §4).
- [ ] Every phone task (sticker, music) is written out with its exact text.
- [ ] `ai_generated` and `ai_reason` are true to the assets.
