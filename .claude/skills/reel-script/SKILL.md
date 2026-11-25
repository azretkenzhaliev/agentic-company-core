---
name: reel-script
description: Use when the content-producer writes a reel. It covers the hook, timed beats, on-screen text, subtitles in the brand's languages and the CTA. For a founder-filmed reel it adds a phone-friendly shot list with direction notes; for a reel with no filming, TextReel props and AI b-roll shots.
---

# Reel script

This skill writes the `## Hook` and `## Script` sections of one reel's page (`knowledge/_templates/content-piece.md`).

Related:
- **Facts:** `knowledge/marketing/platform-facts.md`.
- **Format choice:** the `instagram-formats` skill.
- **Copy in a second language:** the `second-language-copy` skill.
- **The AI record:** the `content-qa` skill (F).

## 0. Before writing

1. **Read:**
   - the calendar row;
   - `knowledge/marketing/<brand>/brand-book.md`: voice, languages, and whether comedy is allowed;
   - the founder's raw material (the page's `raw_material:`), and on his pages `voice.md` (his corrections);
   - `knowledge/marketing/<brand>/learnings.md`, if it exists;
   - from `knowledge/marketing/language/`: `hooks.md`, `language-rules.md`, `captions-and-ctas.md` and `red-lines.md`.
2. **His words first.** A take, opinion or reflection comes from his raw material, quoted or closely cut, where there is some; `## Raw material` quotes it or links it. Where there is none, draft it in his voice from `voice.md` and the brand book, for the Board to correct:
   - write "drafted by us" beside each drafted line; with no raw material at all, set `raw_material: drafted`;
   - a dry run, or a brand whose `voice.md` records that the Board wants only its own words, sets `raw_material: placeholder` and writes "placeholder: the founder's take" wherever his words would go, and keeps the piece `draft`. `content_lint` blocks `ready-for-board` for placeholders.
3. **Pick the path.** The calendar says which, and `filmed_by:` records it:
   - **A. Founder-filmed** (`filmed_by: founder`): §4.
   - **B. No filming** (`filmed_by: none`): a TextReel, his voice note over our renders, or AI b-roll: §5.

## 1. Hook (0–2 s)

Meta's ranking predicts whether a viewer skips within 2 s and whether they watch at least 3 s (platform-facts, "Ranking signals"). So:
- **Land it by 2 s, on all three channels:** picture, spoken line and on-screen text.
- **Open a loop** that the reel closes later: context, then conflict.
- **Show something in the first frame:** a visual pattern interrupt, not a logo or a title card.
- **Fit the awareness stage:** a non-follower needs the problem or the surprise, not who he is.
- **News hooks:** lead with what the news means to the viewer, in his words.
- **Patterns:** the hook patterns are in `knowledge/marketing/language/hooks.md`.
- **Variants:** write two or three hook variants in `## Hook`. The cmo picks one.

## 2. Beats with timings

`## Script` holds one table:

| t (s) | Beat | Spoken (per the brand book's languages) | On-screen text | Picture |
|---|---|---|---|---|
| 0–2 | Hook | | | |
| 2–… | Context and conflict | | | |
| … | Payoff | | | |
| last 2–3 | CTA | | | |

- **Length:** the shortest that carries the idea. Meta compares watch-through with reels of the same length, so padding costs and length alone doesn't (an inference from the system card). The app allows up to 3 minutes. "15–30 s" is a practitioner hypothesis, not a rule. State the total length under the table.
- **Pace:** every beat earns the next, with no dead air. In a longer reel, add a re-hook partway through.
- **Payoff:** it beats what the hook promised.

## 3. On-screen text and subtitles

- **Rendered in code, never by an AI model:** image and video models garble letters. Vetted fonts only.
- **Keep text out of the top 250 px and the bottom 340 px** of the 1080×1920 frame (our template convention; TextReel and `subtitles.mjs` already respect it).
- **One short line on screen at a time.** Where both languages show, the first comes first (`second-language-copy`).
- **Subtitles:** one SRT per language the brand book asks for, burned with Golos Text:
  ```
  node tools/marketing/video/subtitles.mjs --in <clip> --srt <subs.srt> --out <reel.mp4>
  ```
  Which language is spoken and which is subtitled: the brand book decides.
- **Subtitles for his footage:** take them from the script, corrected against what he actually said.
- **Captions on a cut reel:** the `Captions` component (`tools/marketing/remotion/Captions.jsx`): 3-5 words a card, a vetted font, stroke, one active-word colour, default 144 px (7.5% of the height), resting on the 340 px line. `size` and `bottom` are props: five long words wrap to three lines at 144 px. One overlay for the whole reel, never one per card or word: dozens of overlays cost far more than one.
  1. Compile the reel without captions and run `voice/scribe.py` on it: `<name>.words.json` holds each word in the reel's own time. Correct a word's `text` against the script; keep its times.
  2. Render, with only the style in `style.json` (`font`, `activeColor` from the brand book; `size`, `bottom`, `color`, `strokeWidth`, `strokeColor` where they change):
     ```
     node tools/marketing/render/reel.mjs --composition Captions --props <style.json> --words <name>.words.json --out <media/…/captions.mov>
     ```
  3. Add `{ "file": "<media/…/captions.mov>", "start": 0 }` to the edit list's `overlays` and compile again.
- **Check the second language:** every spoken line, on-screen text and subtitle in it goes through `python3 scripts/language_check.py <page>`, unless that's off (SA-004), after `content_lint`.

## 4. Founder-filmed: shot list and direction notes

He films on his phone, the week's reels in one session. His minutes count against his weekly cap. Under `## Script`, add this phone-friendly block:

```
### Shot list: <day> reel, <short name> (about <n> min)
Set up once: <location>, <light>, phone vertical (9:16) at <height>, <props>, <clothes>.
| # | Shot | Framing | Line (his words) | Delivery | Takes |
|---|---|---|---|---|---|
| 1 | Hook | chest up, eyes in the top third | "<…>" | fast, surprised | 2 |
| 2 | … | … | "<…>" | calm | 1 |
After filming: put the clips where the week's packet says, and note how long it took: __ min.
```

**Direction rules** (keep his filming fast):
- **Setups:** group the week's shots by location and setup, so he sets up once.
- **Lines:** short enough to say in one breath. He may reword a line; a drafted line is his to change.
- **Framing:** plain words ("chest up, phone at eye level"). Keep his face and the key action out of the top 250 px and bottom 340 px, where on-screen text and Instagram's interface go.
- **Delivery:** a word or two per line (calm, fast, deadpan).
- **Props:** only what he has to hand.
- **Other people:** someone identifiable on camera needs their consent, and a child a parent's (`content-qa` B). On his pages that's a `Board note:` in review, never a block.
- **Takes:** 2 of the hook and 1 of everything else, unless a line is hard. This is a default; his measured minutes will tune it.
- **Sound:** his own voice and original audio. Music: the cmo pre-selects it for every piece (`instagram-formats` §5), and the Board adds it from Instagram's library at publishing (`knowledge/marketing/platform-facts.md`, "Music and audio"); the page names the track and where it starts.
- **His minutes:** every shot list ends with "how long it took: __ min". The cmo logs it.

## 5. No filming

### 5a. TextReel (Remotion, no AI)

1. Write the props to `workspaces/marketing/media/<brand>/<week>/<slug>/reel.json` (`tools/marketing/README.md`):
   ```
   { "lines": [{ "text": "<hook>", "seconds": 2 }, …], "background": "#…", "foreground": "#…", "accent": "#…" }
   ```
   The colours come from the brand book's visual rules. The first line is the hook and lasts at most 2 s.
2. Render it:
   ```
   node tools/marketing/render/reel.mjs --props <…>/reel.json --out <…>/reel.mp4
   ```
3. Look at it. Save frames with `node tools/marketing/video/frames.mjs --in <…>/reel.mp4 --out <…>/frames --every 1`, and Read each PNG. Check that the text fits, every letter renders, and nothing is clipped.
4. Sound: the TextReel has none. Use his voice note (§5b, §5d) or the cmo's pre-selected music, added at publishing (platform-facts, "Music and audio").

Provenance: `own-render`; `ai_generated: false` unless AI assets are added.

### 5b. His voice note over our visuals

Lay his voice note under a TextReel or our renders, and take the subtitles from his words.

Provenance:
- clips he films: `own-footage`;
- files he hands over (voice notes, photos): `board-supplied`.

### 5c. AI b-roll (SA-005)

- **Prerequisites:** only once the Board has created and topped up the capped Gemini key. Until then, plan the shots and mark each one "pending: no key".
- **What the shots may show:**
  - Text-free only: any words are rendered in code on top.
  - AI-made people may appear, unless the brand's `ai_people` is false (`content-qa` F).
  - Police or officials: on the founder's pages, the reviewer notes red-lines.md's "Authorities and politics" row to the Board; on other brands, none: a blocker (`content-qa` F).
  - What the brand book says about imagery.
- **Models:** the ones in `tools/marketing/gen/` (`gen/video.py` clips of up to 10 s, `gen/image.py` text-free stills); prices change, so read them before a batch.
- **Spend:** report it per batch; it stops at the key's cap.
- **Write each shot in this table:**

| # | Seconds | Prompt (text-free) | Why AI rather than his footage |
|---|---|---|---|

- **Assets:** each clip goes into `## Assets` as `ai-generated`, with its prompt. Set `ai_generated: true` and an `ai_reason` such as "AI b-roll in shots 3–4".
- **Label:** Instagram's AI label is the Board's choice on the post; with it off, the uploaded reel goes without its C2PA (SA-005; `publish/strip_ai.py`).
- **Voice:** voice-over in an ElevenLabs stock voice, only a brand whose `voice_over` is true (SA-005; `voice/tts.py`, on its own capped key).

### 5d. A cut from clips: his footage, outside clips and our layer

For a reel cut from his clips, outside clips or both, with our text, subtitles, voice and music over them (`tools/marketing/video/compile.mjs`).
1. **Gather.** His clips stay in `workspaces/marketing/inbox/`. Outside clips: find them with `python3 tools/marketing/footage/fetch.py search --library youtube|pexels|pixabay --query "<words>"`, then download each with `fetch.py get --url '<address>' --brand <b> --week <w> --slug <name>` (any public video, unless the Board turned `public_downloads` off) or `get --library pexels|pixabay --id <n> ...` (stock). Each lands in `workspaces/marketing/sources/<brand>/<week>/<slug>/` with its MANIFEST.json entry. What you may do with them: `content-qa` I.
2. **Plan the cut** as an edit list, `workspaces/marketing/media/<brand>/<week>/<slug>/edit.json` (written with Write). The beats table (§2) sets the order; each clip's in and out points cover only its beat. The fields are in the header of `compile.mjs`.
3. **Pauses:** `node tools/marketing/video/compile.mjs --list <…>/edit.json --propose-cuts` prints cuts for the silences in his clips. Copy into `cuts` the ones that don't clip a word.
4. **Our layer over the clips:**
   - text: render each overlay from `tools/marketing/templates/overlay.html` with `node tools/marketing/render/png.mjs --html <…>.html --out <…>.png --size 1080x1920 --transparent`, and give it a start and an end;
   - subtitles: per clip, the SRT `voice/scribe.py` made from it (`srt`, in the clip's own time; the tool moves it onto the reel's time, past the cuts), or one SRT in the reel's time for a voice track (`subtitles`);
   - voice: his voice note, or a TTS track (`"ai": true`), as `voice` with its start;
   - music: none in the file by default; the cmo's pre-selected track is added at publishing. A bed baked in (`music`, ducked under speech) only from our own files, or from an outside file whose manifest entry says `"music_ok": true` because its licence allows it;
   - sound effects: `sfx`, each with its start in the reel's time. Ours, or outside on the same rule as a music bed: its manifest entry says `"music_ok": true`. A licence `fetch.py` recorded from a sound's page is a record to check, not that word. Never pass an outside sound as `voice`. On the founder's pages, an outside bed or sound without `music_ok` is a point of law, so never a reason to drop the idea: compile without it, and put one `Board note:` on the piece naming the file and its recorded licence. The flag still moves only on the Board's word (`compile.mjs` refuses without it): the Board's yes on that note is the word, the CEO sets the flag, and the reel recompiles with the sound. On another brand, name the file and its licence under Open questions;
   - the footage's look: `zooms` (a slight push on a beat), a clip's `crossfade` (a dissolve from the clip before; it shortens the reel, so later starts move up) and `grade` (one look for the whole reel). None of them touch our overlays or subtitles.
5. **Compile:** `node tools/marketing/video/compile.mjs --list <…>/edit.json --out <…>/reel.mp4`. It also writes `reel.mp4.json`: every input's provenance, the parts used and `ai_generated`, and adds the parts to each outside clip's manifest entry.
6. **Look:** frames every second (`video/frames.mjs`), and Read each. Check the text fits, the subtitles match the words, and nothing of ours sits in the bottom 340 px.
7. **The page:** in `## Assets`, the reel, each outside clip (`outside`) and each overlay; `ai_generated` as the record says; each outside source credited on screen or in the caption.

## 6. CTA per funnel stage

| `funnel_stage` | CTA on the founder's accounts |
|---|---|
| awareness | Follow, or send it to someone it's for |
| consideration | Save it |
| loyalty | Answer a question in the comments |
| conversion | The offer's CTA, once an order has an offer (`funnel-design`); until then, a follow |

Wording patterns are in `knowledge/marketing/language/captions-and-ctas.md`. Never ask for phone numbers or contacts in comments: collecting contacts needs consent (`content-qa` B).

## 7. Comedy (only where the brand book allows it)

- **Structure:** find the one unusual thing in the scene, then heighten and explore it. Or pick a topic, list its associations and build the punchline from two that clash.
- **Limits:** on the founder's pages no topic is off limits; a joke that touches the law gets a one-line `Board note:` from the reviewer, never a block (`content-qa` B). Other brands keep `red-lines.md`.

## 8. News reels (a brand with `news` set)

- **His take is the content:** in his words, from his raw material or drafted in his voice and marked "drafted by us" (`voice.md`; `content-qa` A). The news is only the context.
- **Sources:** a news claim's source, when we have it, goes in `## Sources` with its https link and date (YYYY-MM-DD); `content_lint` checks the line's format. On the founder's pages a news claim with no source is a `Board note:` on false news, never a block; on a product brand it's a blocker (`content-qa` C).
- **Dates on screen:** the batch posts days after the news, so say when it happened ("on 2026-01-27, …") on screen or in the caption.
- **Visuals:** `news-card.html` renders, a TextReel, his footage, text-free AI b-roll, or clips of the news itself fetched as outside footage (§5d) under his take, credited, only as long as the point needs (`content-qa` I).
- **No same-day lane:** news goes into the weekly batch, unless the Board adds one.

## 9. Done when

- [ ] The hook lands by 2 s on picture, voice and text, with 2–3 variants.
- [ ] Every beat is timed, and the total length is stated.
- [ ] Every opinion traces to his raw material, or is marked "drafted by us" (a dry run: `placeholder`).
- [ ] Path A has a full shot list with a minutes line; path B has the props or shot table.
- [ ] On-screen text is in the vetted fonts and inside the safe area.
- [ ] Each source we have is in `## Sources` with its link and date (a product brand: one for each claim).
- [ ] A compiled reel: its edit list, `reel.mp4.json` and frames exist, and every outside clip is listed as `outside` and credited.
- [ ] `## Assets` and `ai_generated` / `ai_reason` are true to the media.
- [ ] `python3 tools/marketing/content_lint.py <page>` is clean, then, unless it's off, `python3 scripts/language_check.py <page>`.
