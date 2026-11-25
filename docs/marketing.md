# The marketing department (optional)

Six agents that plan, make, check and measure Instagram content (and YouTube Shorts, if you want them) for your own accounts, in your languages. **It's off** until you switch it on: nobody starts the CMO, and the CEO's marketing work stays drafts, by the table in `.claude/agents/marketing/cmo.md`, "Other marketing work". Nothing is ever posted by an agent: you approve each piece in Notion, and you publish each Instagram post yourself.

| Role | Does |
|---|---|
| `cmo` | Plans the week, runs the others, puts the packet in your Notion calendar, schedules what you approved |
| `content-producer` | Writes and renders the pieces |
| `content-reviewer` | Checks every piece against `content-qa`; read-only |
| `performance-analyst` | Reads your numbers in Metricool; read-only there |
| `trend-researcher` | Reads public pages in a separate Chrome profile; optional |
| `reel-analyst` | Watches the reels the read kept; optional |

They work only on your order: no new week, research, trend read or reel run starts by itself. (The department's files call the founder "he"; read it as you.)

**What holds it.** `scripts/hooks/guard_marketing_tools.py` runs before every Bash call and every MCP call. Its limits on email, Metricool, Notion, Telegram, Neon and FastDL hold every agent and every session, whatever is configured; its limits on the marketing roles concern only those roles. Without `integrations.marketing`, or without a setting, key or cap a step needs, what would leave the company refuses, and a `company.json` that can't be parsed blocks the calls that need it. It stops mistakes; it isn't a sandbox.

## Switch it on

Each step is your decision (accounts, services and what leaves the company are yours: `CLAUDE.md`, b1). You can stop after any of them: what isn't set up refuses and says so.

1. **Say so to the CEO,** with the accounts, what each is for, the languages and your weekly minutes. It runs the `brand-book` interview and records the answers. Nothing is sent anywhere.
2. **Add `integrations.marketing` to `company.json`** (below). `company.json` is a guardrail file: you make or approve the edit. From then on the defaults in "What is on by default" apply: read that section first.
3. **Brand pages:** the CMO copies `knowledge/marketing/_brand/` into `knowledge/marketing/founder/<account>/` (or `knowledge/marketing/<brand>/`), drafts them for you, and you approve.
4. **The market's law:** the CMO orders the analyst to fill `knowledge/marketing/language/red-lines.md`. Until a row is filled, its topic binds as written: a one-line note to you on a founder's page, a blocker on any other brand.
5. **The tools:** `tools/marketing/README.md`, "Setup". Node 20 or later and Python 3.12 or later (ffmpeg comes with `npm install`); Tesseract for watched reels, `pdftotext` and `pandoc` for books: on macOS `brew install poppler pandoc tesseract`, on Ubuntu or WSL `sudo apt install poppler-utils pandoc tesseract-ocr`.
6. **Notion** (the approval screen), then **Metricool and Backblaze B2** (publishing), each only when you want that step. Both services may cost money: check their current plans first.

Without Notion you have pieces as KB pages and files, and no approvals, so nothing can be scheduled. Without Metricool you post the files yourself, and there are no numbers to learn from.

## Settings (`company.json`)

Everything goes under `"integrations"`, `"marketing"`. Leave out what you don't use. The values here are examples, not defaults.

```json
{
  "integrations": {
    "marketing": {
      "brands": {
        "founder/demo": {
          "timezone": "Europe/Berlin",
          "metricool_blog_id": "",
          "shorts": false,
          "news": false,
          "voice_over": false,
          "ai_people": true
        }
      },
      "languages": {
        "de": {"name": "German", "scribe": "deu", "letters": "äöüß", "words": [], "vision": "de-DE"},
        "en": {"name": "English", "scribe": "eng", "letters": "", "words": ["the", "and"], "vision": "en-US"}
      },
      "second_language": "en",
      "language_check": true,
      "lint": {"claims": [], "bait": []},
      "notion": {"calendar": "", "swipe": ""},
      "reader": {"browser": "", "accounts": []},
      "no_prompts": [],
      "b2": {"bucket": "", "download_host": ""},
      "backup_folder": "",
      "ocr_language": "eng",
      "public_downloads": true
    }
  }
}
```

| Key | Means | Without it |
|---|---|---|
| `brands` | One entry per brand, named by its folder under `knowledge/marketing/`. Only a `founder/<account>` brand can post through Metricool | No brand, nothing made |
| `brands.*.timezone` | The IANA zone of its posting times | Nothing is scheduled |
| `brands.*.metricool_blog_id` | The brand's id in Metricool | Nothing is scheduled |
| `brands.*.shorts` | Also schedules private YouTube Shorts. Metricool may not wait for your tap on a Short, so your Approved in Notion may be the only gate | Shorts are refused |
| `brands.*.news` | The lint warns on a source line without a link or its date | It doesn't |
| `brands.*.voice_over` | ElevenLabs' stock voices. Also needs `GRANTED` in `tools/marketing/voice/tts.py` | Refused |
| `brands.*.ai_people` | Prompts may ask for AI-made people | **On**. `false` turns it off |
| `languages` | By code, the first is the main one. `scribe`: the transcription service's code; `letters` (only this one has, of yours) or `words`: how to tell the language; `vision`: macOS's text-recognition code | That language isn't recognised |
| `second_language` | The code of the language captions repeat in | One language |
| `language_check` | Sends post copy in the second language to Google Gemini for a check (SA-004, below) | **On**, once `second_language` and that language's `name` and `letters` or `words` are here and the key is set; the key alone starts nothing. `false` turns it off |
| `lint.claims`, `lint.bait` | Your languages' claim words and engagement bait, as regular expressions | English only |
| `notion.calendar`, `notion.swipe` | The data source ids of the two databases | Nothing is synced or scheduled |
| `reader` | The trend-researcher's Chrome profile (below) | It's refused |
| `no_prompts` | A list of calls the guard approves itself, without a permission prompt: `"work"` and `"fastdl"` ("Running without prompts", below) | Claude Code asks, as for any agent |
| `b2` | The bucket your media waits in until Metricool fetches it, and its download host | Nothing is scheduled |
| `backup_folder` | A nightly local copy of the intelligence folder (macOS; `tools/marketing/README.md`) | Off |
| `ocr_language` | Tesseract's language for watched reels | `eng` |
| `public_downloads` | Agents may download public videos, posts and reel covers, logged out (below) | **On**, once `integrations.marketing` exists. `false` turns it off |

**Keys** are in the macOS keychain, never in a file. Each is read at run time by the one script that uses it; on another system those scripts refuse.

| Keychain item | For |
|---|---|
| `agentic-company-gemini-marketing` | The language check, AI images and video |
| `agentic-company-elevenlabs` | Transcripts and voice-over |
| `agentic-company-b2-media` | Uploads to your bucket; a key limited to that bucket |
| `agentic-company-pexels`, `agentic-company-pixabay` | Stock footage |

Add one in Terminal: `security add-generic-password -s <item> -a marketing -w`, then paste the key at the prompt.

**Caps:** `tools/marketing/caps.json` holds the month's caps for each paid call, in units. Every one ships `null`, which refuses; you set the numbers, and a spending limit on the key itself.

## Running without prompts

`no_prompts` is empty unless you fill it. Each name approves calls the guard has already passed, for the marketing roles only, so nobody asks you again before them. **Some of these spend money or send data out;** the caps, `public_downloads`, `language_check` and the other settings still hold each one.

- **`"work"`:**
  - every Bash command the guard passes whose paths stay in the repo and the marketing folders, for the `cmo`, `content-producer`, `content-reviewer`, `performance-analyst` and `reel-analyst`, each in its own list (`scripts/hooks/marketing_bash.py`): file reads, rendering and the checks, and with them
    - **copies, moves and deletes** (`rm -rf` too) inside `workspaces/marketing/media/`, and for the `cmo` inside `workspaces/marketing/swipe/`, wherever those folders link to: a deleted clip is gone unless you have a copy;
    - **paid calls:** AI images and video, voice-over and transcripts, up to `caps.json`;
    - **data sent out:** copy to Gemini (`language_check`), prompts to the image and video services, a voice-over's text to the voice service, a recording (the whole audio or video file it's given) to the transcription service, an approved piece's media to your bucket (`stage_item.py`);
    - **downloads:** public posts, reels and covers (`reels/watch.py`, `reels/save.py`). Never `footage/fetch.py`;
  - the trend-researcher's Chrome steps the guard passes;
  - Notion: its reads, file uploads, and a new page in the two databases `notion` names; Canva: its reads and exports; Metricool: its reads.
- **`"fastdl"`:** the FastDL reads `scripts/hooks/fastdl.py` passes.

Never approved here: a Metricool write, a Notion page's update or comment, Gmail, Telegram, or anything by another role. Files agents write with Write or Edit follow your Claude Code permissions, not this setting.

## What is on by default, and how you tighten it

These defaults bind from the first order. Each is a rule you can narrow at any time, or in `/onboard-company`: say so to the CEO, which records your words where the rule reads them. Nothing here posts anything: you approve every piece one by one, `autoPublish` is always false, and you publish each Instagram post yourself.

"A founder's page" is a brand under `founder/`: your own account, where your approval of each post is the one gate. The last column says where every other brand is stricter.

| What | On by default | To tighten it | Any other brand |
|---|---|---|---|
| Drafted takes | Where your material covers no take, the producer drafts one in your voice, marked "drafted by us", for you to correct | `voice.md`: record that you want only your own words. A take you didn't give is then a placeholder, and a page with one can't be put to you as ready | Facts and approved claims only |
| A law point or a red line | A one-line note to you on that piece, never a block; no subject is off limits | The brand book, "Never post": name each point you want as a blocker | A blocker |
| Sources | A news claim with no source is a note to you, and a lint warning where `news` is true | The brand book, the same list | Every claim has its source |
| The platform's rules on original content and AI people | Never a finding; what the platform rewards is craft | The brand book, the same list | The same |
| Outside footage | Used under your own commentary and edits, credited, with its manifest | The brand book, "Visual rules": bar it | The same, where its brand book doesn't bar it |
| AI-made people | May appear in AI images and video. What Instagram does with a profile that features one is in `knowledge/marketing/platform-facts.md`, "AI-generated profiles", and goes to you as information on that piece | `ai_people: false` | The same |
| Instagram's AI label | Off on each post unless you tick AI label in Notion. Off, the uploaded copy of every file in an Instagram post goes without its C2PA, XMP and IPTC metadata, the marks that say a file is AI-made; your own files keep theirs, and a watermark in the pixels, such as SynthID, stays. A Short's files go up as made, with YouTube's AI flag from the piece's `ai_generated` | Tick it on each AI post: the tick on that post is the only control | The same |
| How much a week | About 2 reels and 1–2 carousels on a page whose cadence you haven't set, 1 post on a quieter page, 2 hours of your time in all | The brand book, "Posting", and the minutes you name | The same |
| Selling | Not gated: funnels, lead magnets and offers are drafted like any piece. Prices and terms are yours (`CLAUDE.md`, b5) | The brand book, "Never post" | Only once you have started the brand, and never while it's gated |
| The idea note | Politics is in, and a crime or court case naming private people is picked like any item, with the law point noted for you | The brand book, "Never post" | A law point is a blocker |
| Taste pickers | Any saved item with a style note can be shown to you, a child on screen too | Ask the CMO to leave items out | – |
| The language check | On once its language is in `company.json` and its key is set | `language_check: false` | The same |
| Public downloads | On, logged out, once `integrations.marketing` exists | `public_downloads: false` | The same |
| Usage | No department cap; work isn't paused for it | Say so to the CEO | The same |
| A blocked command | Final, with one retry: where the block message spells out the form it allows, the agent runs it once in exactly that form | Say so to the CEO: an agent rule, so a system change | The same |

**The label is your responsibility.** Instagram's terms, and your market's law on AI media, may ask you to label AI-made pictures, video and people, and to leave those marks in. Nobody here has checked either for you. With the label off, the code removes the marks Meta says it reads, so they don't label the post either. Until you know, tick it on every AI post.

**What stays off until you give it,** because it's a fact of yours and not a setting:
- brands, accounts, languages, the reader profile, connectors and keys;
- every cap in `caps.json` and every money amount: no cap, no spend;
- `no_prompts`, `backup_folder`, `shorts`;
- voices (`voice_over`, with `GRANTED`).

**Standing authorizations** (`knowledge/board/standing-authorizations.md`). SA-004 is in force by default, and the Board narrows or ends it in `/onboard-company` or at any time. SA-005 is a template: off until the Board grants it in its own words. Neither calls anything until `integrations.marketing` names what it needs (SA-004: the second language; SA-005: the brand) and the founder has set its key; a key alone starts nothing:
- **SA-004 (language check):** marketing agents send post copy in the second language to Google Gemini for a check before the Board reads it. Never the founder's raw material, sources or notes.
- **SA-005 (AI media; template):** once granted, the content producer makes and edits text-free images and video, on a separate key with a spending cap the Board sets: no cap, no spend. Instagram's AI label is the Board's choice on each post.

## Notion

1. Create a private page and, in it, the "Marketing calendar" database with exactly the fields in `knowledge/marketing/notion.md`; "Swipe" too, if you'll save reels to learn from.
2. Connect Notion to Claude, and put each database's data source id in `company.json`. To find an id, ask the CEO to have the `cmo` fetch the database and report the `collection://` id.
3. Set Approval, Board comment and AI label yourself, always in Notion. A hook blocks every agent from them, and copies them into the KB whenever the calendar is queried.

## Publishing

1. Connect Metricool to Claude, connect your Instagram professional account in Metricool, and put the brand's blog id in `company.json`.
2. Create a private Backblaze B2 bucket and an application key limited to it. In Terminal: `security add-generic-password -s agentic-company-b2-media -a b2 -w`, then paste `<keyID>:<applicationKey>`.
3. Approve a piece in Notion. `tools/marketing/publish/stage_item.py` checks that exactly one Approved row covers the page as it is now, that every file is the one on the page and that its time is 2 hours to 6 days ahead, uploads the media, and prints the one Metricool call the hook then allows, with `autoPublish` false.
4. At its time Metricool's app notifies you, and you tap Publish. A Short is always private, and may go up at its set time without the tap; you make it public in YouTube Studio.
5. Optional, macOS: `scripts/marketing_schedule_job.sh install` polls your decisions every 30 minutes and schedules what you approved. It runs `claude` as you, and only while a piece is due. It names claude.ai's own connectors (`mcp__claude_ai_Notion__`, `mcp__claude_ai_Metricool_Social_Media_Management__`): if yours have other names, change its `N` and `M` first.

Instagram allows automated posting only through approved services, for professional accounts. Metricool is one; no agent logs in to Instagram to post.

## The reader profile

For the `trend-researcher` only. A separate Chrome profile, signed in to an Instagram account made for reading, never to your own. Not in WSL: Claude Code's [Chrome integration](https://code.claude.com/docs/en/chrome) isn't supported there.
1. Create the account yourself (a new account is yours to make), and a Chrome profile with only the Claude in Chrome extension.
2. Put the profile's device id in `reader.browser` and the account's handle in `reader.accounts`.
3. Open a read with an order that names it. The hook allows only a few page shapes on instagram.com, youtube.com and t.me, the scripts in `scripts/hooks/trend_reader.py`, and screenshots: no typing, no clicks.

**Before you do:** Instagram's terms restrict automated collection, and it may limit or close the account that reads. Read the terms and decide; the default is no reader.

## Public downloads

Unless `public_downloads` is `false`, `tools/marketing/footage/fetch.py` (its YouTube search too), `reels/watch.py prepare` and `reels/save.py` (its own environment: `tools/marketing/README.md`, "Setup") fetch public videos, posts and covers, logged out and slowly, to learn from or, unless the brand book bars it, as credited outside footage. The same caution applies: the site's terms and copyright are your risk. They stop at the first block, login or rate limit. Other people's media stays in `workspaces/` (gitignored).

## Telegram

The analyst can read channels you name for a weekly idea note.
1. Run a local Telegram MCP server of your choice, named `telegram`, limited to reading. Its session file stays with the server, outside this repo; no agent reads it.
2. Add each channel to `knowledge/marketing/idea-sources.md`. The hook allows only the analyst, only `list_messages`, only those channels.

## Optional connectors

- **Canva:** for your own edits of a design. Agents use it only on request.
- **FastDL** (an outside service that reads public Instagram; unofficial): if you connect it to your Claude account, `scripts/hooks/fastdl.py` lets three roles call its reads of public accounts and posts, and nobody its lists of people. It sees which accounts and posts you look up. Each call asks you, unless `no_prompts` names it.
- **Stock footage:** Pexels and Pixabay keys in the keychain; their licences are yours to check.

## The measurement pipeline

`tools/marketing/measure/` measures pieces locally: cuts, colours, on-screen text, speech, embeddings. It needs its own Python 3.12 on an Apple silicon Mac (`measure/requirements.txt`) and models (`measure/models.json`), sends nothing, and skips what isn't installed. Apple's text recognition works only on macOS.

## Tests

`npm test` in `tools/marketing/`, and `python3 -m unittest discover -s tools/marketing/tests` from the root. CI runs the Python ones (`.github/workflows/marketing-tools.yml`).

## Switch it off

Remove `integrations.marketing` from `company.json`, run `scripts/marketing_schedule_job.sh uninstall` and `python3 scripts/marketing_intelligence_backup.py uninstall`, and disconnect the connectors. The pages stay. The guard keeps refusing.
