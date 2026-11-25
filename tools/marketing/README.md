# Marketing tools

The marketing department's renderer, linter and media scripts. They live here, with their own dependencies, because `scripts/` uses only Python's standard library. How to switch the department on, and every setting in `company.json`, with what happens without it: `docs/marketing.md`.

## Setup (once per machine)

```
cd tools/marketing
npm install
npx playwright install chromium
```

The first reel render also downloads Remotion's headless Chrome (about 170 MB).

The measurement pipeline (`measure/`, optional) has its own Python in `workspaces/system/venvs/measure/` and its models in `workspaces/system/models/measure/`, installed once: `measure/requirements.txt` and `measure/models.json` (sources, revisions, sha256) say how, and `run.py check` says what's there. It never downloads at run time.

`reels/save.py` (optional; off where `public_downloads` is) runs only in its own environment, at exactly this path and version, which you make once from the repo root: `python3 -m venv workspaces/system/venvs/instaloader-4.16`, then `workspaces/system/venvs/instaloader-4.16/bin/pip install instaloader==4.16`. Without it, it refuses.

## Commands

Run them from `tools/marketing/`, or give the path from the repo root. Media goes to `workspaces/marketing/media/<brand>/<week>/` (gitignored); content pages link to it by path.

| What | Command |
|---|---|
| Lint content pages | `python3 tools/marketing/content_lint.py <page.md or folder>` (standard library; exit 1 on errors; a folder's `status: archived` pages are skipped and named). `--clean <page.md>` prints the caption's AI-tell score beside the cleaned caption |
| HTML/CSS → PNG | `node render/png.mjs --html slide.html --out slide.png --size 1080x1350` (or `1080x1920`, `1080x1080`) |
| A folder of slides | `node render/png.mjs --dir <folder> --size 1080x1350` (every `*.html` → `.png`, in name order) |
| One template, many renders | `node render/png.mjs --html <template> --list <list.json> --dir <folder> --size 1080x1350`, with the list `[{ "out": "<name>.png", "values": { … } }]`: each entry renders the template alone, its scripts reading `window.VALUES`, into `<folder>/<out>` (a plain file name). The template's relative paths count from where it is. A bad entry fails alone and is named; the rest render, then exit 1. A list of hundreds can pass Bash's 2-minute default, so split it or give Bash a longer timeout |
| Text reel (no filming) | `node render/reel.mjs --props reel.json --out reel.mp4`, with props `{ "lines": [{ "text", "seconds" }], "background", "foreground", "accent" }` |
| Burn subtitles | `node video/subtitles.mjs --in clip.mov --srt subs.srt --out reel.mp4` |
| A reel cut from clips | `node video/compile.mjs --list <media/…/edit.json> --out <media/…/reel.mp4>` (writes `reel.mp4.json`: provenance, parts used, `ai_generated`); `--propose-cuts` prints pause cuts first. Sound effects, zoom, crossfade and a colour grade: `sfx`, `zooms`, a clip's `crossfade` and `grade` (the fields are in the script's header). A zoom's `"ease": "linear"` pushes in at an even speed and is at its scale at `end`, then snaps back, so end it on a cut; the default, `"sine"`, goes in and back out. `grade`'s `warmth`, -1 to 1, warms (above 0) or cools the footage, e.g. 0.3 for cool stock next to warmer shots; 0 or none changes nothing. A clip's `"crop": { "corner": "bottom-left", "size": 0.8 }` shows that corner (`top-left`, `top-right`, `bottom-left`, `bottom-right`), size 0.5 to 1 of the largest 9:16 window. The sound is mastered to -14 LUFS with true peaks at most -1 dBTP (`knowledge/marketing/craft-standard.md`, "Loudness"), and the line printed and `reel.mp4.json`'s `loudness` give what was measured in the reel (a reel turned up more than 20 dB says so: listen for its noise); `"loudness": false` leaves the sound as mixed, and a silent reel stays silent. Text overlays: `templates/overlay.html` with `render/png.mjs --size 1080x1920 --transparent` |
| A folder of edit lists, one call | `node video/compile.mjs --batch <folder> --dir <media/… folder> [--vars <vars.json>]`: every `<name>.edit.json` → `<dir>/<name>.mp4` and its `.mp4.json`, in name order, with the checks above. A reel that fails is named and the rest are built, then exit 1. `--vars` changes every list first (a new voice, clips swapped for his footage, times moved along a map to his word timings: the fields are in the script's header); a list it can't change stops the batch before anything is built. A batch of dozens of reels outlasts Bash's 2-minute default: run it in the background |
| Captions for a cut reel | `node render/reel.mjs --composition Captions --props style.json --words <name>.words.json --out <media/…/captions.mov>`: one transparent overlay for the edit list's `overlays` (`reel-script` §3). `style.json`: `font`, `activeColor`, and where they change `size`, `bottom`, `color`, `strokeWidth`, `strokeColor` |
| Outside footage | `python3 tools/marketing/footage/fetch.py search --library youtube\|pexels\|pixabay --query "…"`; `get --url '<public video>' --brand <b> --week <w> --slug <name>` or `get --library pexels\|pixabay --id <n> …`. Any public video and a YouTube search, unless the Board turned them off (`public_downloads`). Into `workspaces/marketing/sources/<brand>/<week>/<slug>/` with a `MANIFEST.json` entry (a Freesound sound's licence comes from its page, a record to check, not a grant); caps in `caps.json`. Needs yt-dlp once: `python3 -m venv footage/.venv && footage/.venv/bin/pip install --require-hashes -r footage/requirements.txt`. Stock keys (optional): keychain items `agentic-company-pexels`, `agentic-company-pixabay` |
| Frames for review | `node video/frames.mjs --in reel.mp4 --out <folder>/frames [--every 1] [--width 1080]` (the reviewer reads frames, not video, at `--width 1080`: `content-qa`; 540 px wide unless `--width` says otherwise) |
| Transcript, SRT and word timings (ElevenLabs Scribe) | `python3 tools/marketing/voice/scribe.py <audio under workspaces/marketing/> --lang <code> --out <folder under workspaces/marketing/media/ or swipe/>` (writes `.txt`, `.srt` and `.words.json`; never overwrites a transcript) |
| A week's reels, watched | `python3 tools/marketing/reels/watch.py prepare\|next\|label\|status\|table --week <w>` (the `reel-analyst`'s, from `posts.csv`; `prepare` is off where `public_downloads` is; into `workspaces/marketing/intelligence/reels/<code>/`; a reel gets 200 s, then fails with a record; Scribe is paid, the rest local) |
| Public posts and reel covers, saved | `python3 tools/marketing/reels/save.py post --code <code> [<code> ...]` or `covers --week <w> [--count 10]` (the `cmo`'s, and the `reel-analyst`'s both), or `latest --account <username> [--count 6]` (the `cmo`'s only: the account's latest posts that aren't reels, 1-12, from its profile page alone, about 12 with pinned ones first, no next page; a reel the page didn't mark is recorded and the next run takes the next post). Off where `public_downloads` is. Logged out, on instaloader 4.16 pinned in `workspaces/system/venvs/instaloader-4.16`; a post into `workspaces/marketing/intelligence/posts/<code>/` with a `MANIFEST.json` for `taste/build.py`, a cover as `reels/<code>/cover.jpg`; an image served as PNG, WebP, HEIC or AVIF is made a JPEG by macOS's own `sips`, locally, and an HTML, empty or unknown body fails its post, its `failed.txt` naming the kind and size; one run at a time, 10-15 s before each request, at most 24 a run; a 401, 403, 429, `feedback_required`, checkpoint, a redirect of the profile page or 3 failures in a row stop it, stored in `posts/stopped.txt`; free, nothing written to Instagram |
| Our own reel, measured | `python3 tools/marketing/reels/watch.py measure --file <render under workspaces/marketing/media/>` (the `cmo`'s and the `content-producer`'s; one line of JSON: length, cuts, cut times, longest shot, loudness; local, nothing written; `content-qa` J reads it as warnings) |
| A page's pieces, measured | `workspaces/system/venvs/measure/bin/python tools/marketing/measure/run.py run --in <folder of pieces> --page <page> --out <new folder>` (a feature file a piece in `pieces/`, and `summary.json` with each number's median, P10 and P90 and the embedding centroids, per page and format; `summary --runs <run> … --out <file>.json` pools runs. Only numbers and vectors are kept, no text or frames; local, no network; a missing model skips its stage. On-screen text: Tesseract with the traineddata `measure/models.json` names, read only from the models folder, whose sha256 you pin there first (`shasum -a 256 <file>`); until then the stage is refused; speech: Whisper, which detects the language unless `--speech <code>` names it; cuts: ffmpeg's scene score until TransNetV2 is installed) |
| A page's taste picker | `python3 tools/marketing/taste/build.py --page <page> --rubric <file> --picks <file>` (the `cmo`'s; both files directly in `workspaces/marketing/media/taste/<page>/`, where it writes `picker.html`; at most 30 items, 4 aspects an item, 5 page questions, 15 MB; refuses an item with no style note; the two formats are in the script's header; local, nothing sent). A weekly session's picker: `--page <page> --session <folder>/session.json`, the file in `<page>/session-<YYYY-MM-DD>/` with its images in `ref/` and `ours/`, and `picker.html` beside it; at most 8 items plus an overview, 3 images and 3 options an item, 2 to 4 choices, 300 characters a text; refuses a reference image whose reel or post has no style note. A taste-defining sitting: the same command on a `"mode": "trial"` file in `<page>/session-<YYYY-MM-DD>[-<word>]/` (schema and worked example: `taste/trial-schema.md`, `taste/example-trial.json`); add `--design` to check the file and list the media its seed needs, writing nothing |
| A sitting's taste profile | `python3 tools/marketing/taste/analyze.py --page <page> --session <folder>/session.json --answers <folder>/<export>.json` (the `cmo`'s; the trial page's export, beside its `session.json`; writes `profile-<page>-<session>.json` there: weights with standard errors, red lines, uncertain dimensions and the hidden-repeat check; refuses an export of another design). `--recover` instead of `--answers` checks the design recovers a known profile, writing nothing (`taste/trial-schema.md`, "The analysis"; local, nothing sent) |
| Voice-over (ElevenLabs) | `python3 tools/marketing/voice/tts.py <text file under workspaces/marketing/media/> --voice <id> --model <id> --brand <b> --week <w> --piece <slug>`; in ElevenLabs' stock voices only, for the brands whose `voice_over` is true; refuses until the Board grants it (`GRANTED` in the script) |
| Text-free image (Gemini) | `python3 tools/marketing/gen/image.py --brand <b> --week <w> --piece <slug> --prompt "<what to show>" [--aspect 4:5\|9:16\|1:1]` |
| Text-free b-roll (Gemini Omni Flash) | `python3 tools/marketing/gen/video.py --brand <b> --week <w> --piece <slug> --prompt "<what to show>" --seconds <1-10>` |
| A batch's generation spend | `python3 tools/marketing/spend.py --brand <b> --week <w>` (paste into the week's report; `--brand intelligence/reels` for the reels' Scribe calls) |
| Tests | `npm test` (the renderer, the taste picker, the session picker and the trial picker, needs Chromium) and `python3 -m unittest discover -s tools/marketing/tests` (content_lint and the media scripts, also in CI; `test_measure` skips what needs numpy, Pillow, ffmpeg or Tesseract where they're missing) |

**Paid media scripts**: each reads its key from the macOS keychain at run time (`agentic-company-elevenlabs`, `agentic-company-gemini-marketing`), checks the month's cap in `caps.json` before the call and logs the units to `workspaces/marketing/spend.jsonl` after. A cap of `null` refuses, and every cap ships `null` until the Board sets it. The Gemini scripts refuse a brand that isn't in `company.json`, and prompts asking for text in the picture, or for people where the brand's `ai_people` is false, and write a `<file>.json` sidecar with `ai_generated: true`.

## Nightly copy of the intelligence folder (macOS only)

Off until `company.json` names a `backup_folder`, a folder on this computer (one a cloud drive syncs, say; then what is copied leaves this computer, which the Board decides).
- **What it does:** `scripts/marketing_intelligence_backup.py` copies `workspaces/marketing/intelligence/` into `<backup_folder>/intelligence-backup/`.
- **When:** every night at 03:00, by launchd. If the Mac was asleep it runs on waking; if the Mac was off it skips the night.
- **Why a copy and not a move:** the tools work on the local folder (`reels/watch.py` refuses a link there), and a cloud drive may keep only placeholders on the computer.
- **What it never does:** delete anything, in the folder or in the copy, or follow a link. Each file lands whole or not at all.
- **Log:** one line a run, counts and error codes only, in `~/Library/Logs/agentic-company/intelligence-backup.log`.

**Install** (the CEO, from the main checkout):

```
python3 scripts/marketing_intelligence_backup.py install
launchctl kickstart gui/$(id -u)/com.agentic-company.intelligence-backup
tail -1 ~/Library/Logs/agentic-company/intelligence-backup.log
```

- The line should end `0 failed; exit 0`.
- A macOS prompt to let `python3` into the folder is the Board's to answer.
- A line with `EPERM` or `refused` means macOS kept the job out: report it, and don't give Python Full Disk Access to get round it.
- A power cut or a forced quit mid-file can leave one hidden `.<name>.<random>.part` in the copy, up to that file's size, and no run removes it. `find <backup_folder>/intelligence-backup -name '.*.part'` lists them; delete them by hand.

**Uninstall:** `python3 scripts/marketing_intelligence_backup.py uninstall`. The copy stays.

**Restore:** make sure the cloud drive has downloaded the copy, then copy it back as a real folder, not a link, without the hidden `*.part` files a power cut can leave: `rsync -a --exclude '.*.part' <backup_folder>/intelligence-backup/ workspaces/marketing/intelligence/`.

Files deleted here since the copy come back too. A stale `reels/stopped.txt` or `reels/<code>/failed.txt` holds its reel back until `watch.py prepare --retry-failed`; a stale `posts/stopped.txt`, `posts/<code>/failed.txt` or `reels/<code>/cover-failed.txt` holds `save.py` back until its `--retry-failed`.

## Rules built in

- **Fonts:** on-image text only in Montserrat or Golos Text (Latin and Cyrillic), Arabic script in Scheherazade New. Check that a vetted font holds every letter of your languages before you use it; another font needs a line in `render/fonts.mjs` and `content_lint.py`. `render/fonts.mjs` loads them from `@fontsource` (SIL Open Font License). `npm test` fails if one falls back to another font, and `content_lint` fails a slide that names another family.
- **Templates** (`templates/`): `carousel.html` (4:5), `story.html` (9:16, with Instagram's top 250 px and bottom 340 px kept clear), `news-card.html` (its source line is required), `quote-card.html` (plain background) and `overlay.html` (a transparent text overlay for a reel). Copy one per slide into the week's media folder and edit its text and `:root` colours. `templates/base.css` and the fonts are injected at render time.
- **Our own media:** templates and renders are ours (`own-render`). Other people's video and stills only as outside footage through `footage/fetch.py`, each file with its manifest entry (`outside`). Never screenshots or files that came any other way.
- **Remotion props:** check a composition's props in its `calculateMetadata` (`remotion/index.jsx`), not only in the component body: Remotion hears a page's errors only while it renders a frame, so one thrown at mount can pass as empty frames.
- **Remotion's licence** is free for companies of up to 3 people when this was written: check it (https://www.remotion.dev/license) before the first render, and again if the company hires.
