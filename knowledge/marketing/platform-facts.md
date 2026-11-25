---
title: Instagram and Meta platform facts
owner: cmo
status: draft
updated: 2026-10-28
related: [README.md, notion.md, craft-standard.md]
last_verified: 2026-10-28
ttl_days: 30
---

# Instagram and Meta platform facts

The Instagram and Meta facts the marketing agents rely on: ranking signals, format specs, what the publishing API can and can't do, originality, AI labels and cadence. The skills `instagram-formats`, `reel-script`, `carousel-design`, `story-sequence` and `content-qa` link here instead of copying these facts. The cmo curates this page from the analyst's notes.

**This page shipped with the core, read on `last_verified`.** Past its TTL every row is stale: before your first batch, order the analyst to re-check the rows you'll rely on against the sources named, and write your own notes' names in the Source column.

## How a fact gets here, and when it goes stale

- **Only official sources change a "fact":** Meta, Instagram and Instagram's head, Adam Mosseri. Practitioner claims stay hypotheses (the last sections) until your own data confirms them.
- **Re-check after the TTL.** From `last_verified` plus `ttl_days`, treat every row as stale: re-check it against its source before relying on it. The analyst re-checks the official sources; the cmo updates this page.
- **Kind** of each row:
  - *official*: Meta's or Instagram's own page, or Mosseri's own post;
  - *official, via press*: an official statement known only from press or blog reports;
  - *practitioner*: blogs, vendors, consultants;
  - *study*: a research paper;
  - *inference*: a reading, not anyone's statement;
  - *ours*: a rule of this department. It binds us, but it isn't a platform fact.
- **Sources** (official pages; every row is a paraphrase):
  - **RC** = Meta's ranking system cards, transparency.meta.com, "Explaining ranking" (Reels, Explore, Feed, Stories, Search);
  - **CP** = Instagram Platform docs, "Content Publishing" and the media reference, developers.facebook.com/docs/instagram-platform;
  - **CL** = the Instagram Platform changelog, same site;
  - **IN** = the Instagram Platform docs on insights, same site;
  - **PR** = the Instagram Platform docs on private replies and messaging, same site;
  - **AA** = the Instagram Platform docs on the Audio API, same site;
  - **OB** = Instagram's creators blog on original content (2026-04-30), creators.instagram.com/blog;
  - **AB** = Instagram's creators blog on AI-generated profiles (2026-08-31), same site;
  - **AI** = Meta's posts and help pages on labelling AI content (2024, updated to April 2025), about.fb.com and transparency.meta.com;
  - **EN** = Engineering at Meta on Andromeda, engineering.fb.com;
  - **MO** = Mosseri's posts, via press (Social Media Today and others);
  - **MC** = Metricool's help pages and its connector's own tool text;
  - **HC** = Instagram's Help Centre, via search summaries.

## Ranking signals

| Fact | Kind | Source |
|---|---|---|
| Reels ranking predicts specific viewer actions. The Reels card lists: watching less than 3 seconds; watching more of a reel than 95% of viewers of reels of the same length; commenting; resharing; sharing off Instagram; following the author; using the audio in one's own reel; tapping "Interested" where it's offered; opening a tall reel in Explore full screen. Signals under them include: skips within 2 seconds of opening; sound-on views; 3-second views; time spent; followers gained through the reel; likes; the viewer's own saved videos. No weights | official | RC |
| Feed, Stories, Explore, Reels and Search each have their own ranking system | official | RC |
| Explore recommends photos and reels from accounts the viewer doesn't follow. It predicts: following the author; viewing more than 5 seconds; watching more than 95% of a video; clicking "Not Interested"; commenting; liking; resharing; saving. No weights | official | RC |
| The Feed card orders posts by predicting what the viewer will find most valuable; models and signals change often. Predictions: swiping through a whole carousel; enjoying or skipping the post; time on the author's profile afterwards; sending it in a DM (signals include informative content such as news, reviews, tutorials and how-tos, and recency); time on the post (signals: whether it's a photo, and how much text is overlaid); skipping the first post in Feed; turning the sound on. No weights, and no direction given for any signal | official | RC |
| Top signals: watch time, likes per reach and sends per reach. Likes count more for reach among followers; sends count more for reach among non-followers (January 2025) | official, via press | MO |
| Originality, recency and showing small creators' public posts to non-followers to test them are named as principles (September 2026). Use trial reels to experiment; watch engagement *rate*, not raw views; post as much as you sustainably can | official, via press | MO |
| Viewers can curate their topics ("Not interested", "Tune Your Algorithm", Favorites, a recommendations reset), so a clear topic per account matters more | official (features); the consequence is inference | RC |
| Instagram doesn't throttle AI content's reach for being AI content, says Mosseri (October 2026); ranking probably doesn't yet rank it as well as other content | official, via press | MO |
| "Sends" in the app are `shares` in the API | inference | IN |

## Formats and specs

| Fact | Kind | Source |
|---|---|---|
| Reels can be up to 3 minutes in the app. The profile grid shows vertical rectangles (4:5; some sources say 3:4), so a cover must work in that crop. Keep text and marks 80 px in from each side, which survives either | official, via press; ours | HC |
| API reels: MOV or MP4, H.264 or HEVC with AAC, 23–60 fps, ≤ 25 Mbps, 3 s to 15 min, ≤ 300 MB, 9:16 recommended. Cover from `cover_url` (JPEG ≤ 8 MB) or `thumb_offset`; `share_to_feed` | official | CP |
| API single image: JPEG only, ≤ 8 MB, aspect 4:5 to 1.91:1, width 320–1,440 px | official | CP |
| API carousel: up to 20 items, images and videos mixed. Every item is cropped to the first item's ratio; a reel can't be a carousel item; caption and location go on the carousel, not on items | official | CP |
| API stories: an image (JPEG ≤ 8 MB) or a video (3–60 s, ≤ 100 MB) | official | CP |
| Caption: at most 2,200 characters | official | CP |
| The caption fold: how much of a caption shows before "more" has **no Meta figure**. The common "about 125 characters" comes from third-party guides, which say it varies by device. So the first line carries the hook on its own (`content-qa` H), and nobody cites 125 as Meta's number | official (absence); practitioner (125) | HC |
| **Hashtags:** Instagram said in December 2025 that it is moving to at most 5 per caption, gradually; older API docs said 30. **Ours: at most 5**, caption and hashtag section together (`content_lint`) | official, via press; ours | MO |
| Mentions: up to 20 per caption. Alt text: up to 1,000 characters, images only. Collab posts: up to 3 collaborators, on feed images, reels and carousels, not stories | official | CP |
| Profile limits, none from a Meta page we could read: bio 150 characters; name 30; highlight title about 15; 3 pinned posts; 5 bio links. **Ours:** draft to the low figures (bio ≤ 150 counting each line break, highlight titles ≤ 9) | practitioner; ours | HC |
| Story and reel safe zones are published for **ads**, not organic posts. Our `story.html` keeps text out of the top 250 px and bottom 340 px, close to what third parties report of the ads guidance | practitioner; ours | – |

## The publishing API: what it can and can't do

| Fact | Kind | Source |
|---|---|---|
| Publishes reels, carousels, single images, stories and trial reels (trial reels since 2025-12-03, shown to non-followers first) | official | CP, CL |
| No native scheduling found: a scheduler has to call `media_publish` at the time (the absence is unverified). Meta Business Suite's planner schedules by hand in its interface, for free | official (absence unverified) | CP |
| Link, poll and location stickers can't be published through the API. User mentions can. Quiz stickers aren't named in the docs read. TODO(verify): quiz. Until then, every interactive sticker is a phone task | official; quiz unknown | CP |
| Music through the API: **reels only** ("Music and audio", below). Carousels, photos and stories have no documented way to attach audio; it's added in the app | official | AA |
| Media must sit at a publicly reachable URL when the API fetches it; resumable upload needs Facebook Login | official | CP |
| Containers expire after 24 h; 400 containers per rolling 24 h | official | CP |
| Publishing limit: 100 API posts per rolling 24 h; the same page's carousel section says 50. Check `GET /<IG_ID>/content_publishing_limit` | official (the page conflicts with itself) | CP |
| AI self-disclosure: `is_ai_generated=true` (since 2026-06-22); on a carousel it's set on the container only | official | CP, CL |
| Posts can be deleted through the API (since 2025-12-03) | official | CL |
| A professional account (Business or Creator) is needed. Instagram Login needs no Facebook Page | official | CP |
| Tokens: short-lived 1 h; long-lived 60 days, refreshable. A token never goes in the KB | official; ours | CP |
| Comment-to-DM: one private reply per comment, within 7 days of the comment; more only after the person replies (then a 24 h window) | official | PR |
| Insights: `views` replaced `impressions` and `plays` (from 2025-04-21). Per post: `saved`, `shares`, `follows`, `profile_visits`. Reels add `ig_reels_avg_watch_time`, `ig_reels_video_view_total_time` and `reels_skip_rate`. Story insights exist for 24 h only. Values under 5 return an error. Demographics need ≥ 100 followers. Up to 48 h lag | official | IN |
| No official organic Instagram MCP server found (the absence is unverified). Instagram's terms prohibit collecting information by automated means, so agents never drive instagram.com in a browser (the one exception, the trend-researcher's public read in the reader profile, is the Board's to switch on, knowing this: `docs/marketing.md`) | official (terms); ours | HC |

## Outside footage and stock libraries

| Fact | Kind | Source |
|---|---|---|
| **Ours:** footage from any public source (films, series, TV news, other people's videos, stock), cut and compiled with our own text, graphics, voice and music, through `tools/marketing/footage/fetch.py` with a `MANIFEST.json` entry per clip, unless the Board bars it (the brand book's "Visual rules"). What we may do with it: `content-qa` I | ours | – |
| YouTube's and Instagram's terms don't allow downloading unless the platform offers a download function. Public videos are downloaded anyway (no login, no cookies), by default, until the Board turns `public_downloads` off; agents still never drive instagram.com in a browser | official (terms); ours | HC |
| Stock libraries (Pexels, Pixabay) have their own licences: free use and editing, no standalone resale, limits on recognisable people and trademarks. Their keys are the founder's, in the macOS keychain. Read the licence page at the time of use | official (licence) | pexels.com/license, pixabay.com/service/license-summary |
| Instagram's originality rule asks for meaningful creative input and says nothing about stock or outside clips. That our commentary and edits over clips count as original is inference | official (silent); inference | OB |

## Music and audio

| Fact | Kind | Source |
|---|---|---|
| **The Audio API** (June 2026) searches audio and attaches it to a **reel** at creation: `GET /ig_audio`, then `POST /{ig-user-id}/media` with `media_type=REELS` and `audio_configuration`. Nothing is documented for carousels, photos or stories | official | AA |
| It returns only audio authorized for third-party use, which may differ from the app's picker. It needs a Business or Creator account with a connected Facebook Page, and Facebook Login | official | AA |
| A reel with attached audio can't be previewed: nobody hears the mix before it's live. So the Board approves the track and the video separately | official; the consequence is ours | AA |
| Since 2026-07-30 the API gives no file for our own reels that carry licensed music | official | CL |
| **Metricool** adds audio to Reels in its web planner: the account must be connected through Facebook Login; only third-party-authorized audio; the track starts at 0:00; reels only; no preview. If a song is missing, its advice is to publish by notification and add the audio in the app | official for Metricool | MC |
| **Ours:** our publisher (`tools/marketing/publish/post.py`) sends no audio, and always schedules with `autoPublish` false, so the Board finishes each post in the app. Every music choice is therefore a phone step at publishing | ours | `post.py` |
| **Business versus Creator:** vendor blogs say a Business account's picker serves Meta's royalty-free Sound Collection, while personal and Creator accounts get the licensed popular catalogue where Meta holds the rights. No Meta page read says so | practitioner; unverified | – |
| **Ours:** default to Sound Collection or original audio (his voice), until each account's type and its picker are known | ours | – |
| Meta's Reels card lists using the audio in one's own reel and sound-on views among predictions and signals; no Meta text says trending or original audio lifts reach | official (no direction given) | RC |

## Originality

| Fact | Kind | Source |
|---|---|---|
| The originality rules cover reels (since 2024) and, since 2026-04-30, photos and carousels. Accounts that mostly repost others' content aren't recommended to non-followers | official | OB |
| Instagram judges about a month of an account's output. Eligibility returns once most recently posted content is original over 30 days. Account Status shows where an account stands | official | OB |
| Original means work you wholly created, or that reflects your unique perspective. Original on-image text, new graphics, remixes, and memes with added humour or commentary count. Borders, watermarks, subtitles, speed changes, a credit line, minor crops and screenshots of others' posts don't | official; the lists partly via press | OB |
| The rules don't mention AI. Whether an AI asset a human edited counts as original isn't stated | official (silent) | OB |
| **Ours:** the platform's originality rules are never a block (`content-qa` F); what Instagram rewards stays here as craft information. Near-identical posts in a row are avoided | ours | – |

## AI labels and disclosure

| Fact | Kind | Source |
|---|---|---|
| Meta labels from two signals: the poster's self-disclosure, and industry-standard AI indicators, which it names as C2PA and IPTC metadata | official | AI |
| Disclosure is required for organic photorealistic video or realistic-sounding audio that was digitally created or altered. Meta says it may apply penalties; none are listed. Images aren't in that required sentence | official | AI |
| Generated content shows "AI info" on the post. Content only edited with AI tools has the label in the post's menu instead (since September 2024) | official | AI |
| Per carousel item or per post, and how it shows on reels and stories: not found. Treat it as one label for the whole post | inference | AI |
| Google's image and video models' files carry SynthID, and C2PA by default. An unedited file will probably be labelled automatically | official (Google); inference | AI |
| HTML/CSS renders and ffmpeg edits of our own footage carry no AI metadata. False positives on real photos are documented (2024) | inference | AI |
| A realistic AI voice falls under the audio rule. Whether a clearly synthetic narrator does isn't stated | official; unverified | AI |
| No source says the label, or AI content as such, cuts reach. One experiment (Copenhagen Business School, about 700 people, no platform measured) found lower engagement on content labelled AI | official, via press (MO); study | MO |
| **Ours:** a piece with any AI asset says `ai_generated: true`. Whether its post carries Instagram's AI label is the Board's choice on each post, the AI label box in Notion, off unless the Board ticks it (SA-005). **On:** our self-disclosure flag goes with the post and the files go up as made. **Off:** no flag, and the uploaded copy goes without its C2PA, XMP and IPTC (`publish/strip_ai.py`), so neither of the two signals Meta names is sent; SynthID stays in the pixels. The facts above, the disclosure Meta requires among them, are information for that choice ([notion.md](notion.md), "AI label") | ours | – |

## AI-generated profiles (since 2026-08-31)

| Fact | Kind | Source |
|---|---|---|
| A profile that features an AI-generated person and lacks Instagram's "AI-generated profile" label loses recommendation eligibility. With the label, reach doesn't change. Creators who only use AI tools in their process don't need it | official | AB |
| **Ours:** an AI-made person may appear, unless the brand's `ai_people` is false; the reach fact above goes to the Board as information on that piece | ours | – |

## Andromeda (ads)

| Fact | Kind | Source |
|---|---|---|
| Andromeda is Meta's machine-learning system for ads retrieval, the first step of its ads recommendation. No Meta text found ties it to organic ranking, so it changes nothing in organic planning | official (silent); the consequence is ours | EN |

## Cadence

| Fact | Kind | Source |
|---|---|---|
| "As much as you sustainably can" is Mosseri's advice (September 2026) | official, via press | MO |
| **Ours:** weekly batch approval only; the README's cadence and the founder's weekly minutes | ours | [README.md](README.md) |

## Hypotheses to test (practitioner, not facts)

Promote one to a fact only with your own data (the performance-analyst):
- A send is worth several likes; originals get far more distribution; a reposts-in-30-days threshold. Meta's cards list predictions and give no weights.
- A hook in the first ~1.5 s (the system card's own figure is 2 s).
- 9:16 reels of 15–30 s.
- Carousels earn saves and shares; reels earn sends.
- The idea-scoring rubric (stop power, watch-through, sends, saves, follows and comments, stage fit, minutes): weights start equal and are refitted from results.
- Labelled versus unlabelled AI posts: at the 8-week review (`ig-insights-review`).
- Music: "original audio ranks higher"; "trending audio gives more organic reach".
- Ads: that Andromeda groups similar creatives.

## Unknowns

- TODO(verify): whether the 5-hashtag limit is live on your accounts; the caption fold on the founder's own phone.
- TODO(verify): whether quiz stickers can be published through the API.
- TODO(verify): the AI label per carousel item or per post; whether Meta reads C2PA in video, or SynthID.
- TODO(verify): Instagram's own safe-zone figures for organic stories and reels.
- TODO(verify): reel length: 3 minutes in the app against 15 minutes in the API docs.
- TODO(verify): native scheduling in the API; the publishing limit (100 or 50).
- TODO(verify): each account's type (Business or Creator), how Instagram is connected in Metricool, and which music library its picker shows in your country.
- TODO(verify): the trial-reel follower minimum.

## Official sources to re-check

The ranking cards (transparency.meta.com/features/explaining-ranking), creators.instagram.com/blog, about.instagram.com/blog, the Instagram Platform docs and changelog (developers.facebook.com/docs/instagram-platform), facebook.com/business/news, the Meta Business Help Center, engineering.fb.com, and Mosseri's own posts. Press (Social Media Today and the like) is for discovery only: confirm each item against the primary source.
