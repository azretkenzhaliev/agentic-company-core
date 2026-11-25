---
title: The Notion calendar (the Board's approval screen)
owner: cmo
status: draft
updated: 2026-01-01
related: [README.md, platform-facts.md]
---

# The Notion calendar

Notion is where the Board reviews each weekly batch on its phone. The KB stays the record: every piece's page is in `<brand>/content/`, and the Board's decisions are copied into `<brand>/approvals/<week>.md` by a script.

- **Database:** "Marketing calendar", a private page in the Board's own Notion workspace. The Board creates it with the fields below (`docs/marketing.md`).
  - Its data source id goes in `company.json` (`integrations.marketing.notion.calendar`), for the Notion tools, `scripts/notion_approvals_sync.py` and the guard.
- **Who writes what:** agents create the week's items and set the agent fields below. Only the Board sets the Board fields, in Notion itself. `scripts/hooks/guard_marketing_tools.py` blocks any agent that tries, and lets agents set only the agent fields.

| Property | Type | Set by | What |
|---|---|---|---|
| Name | title | agents | Day, format and a short name, e.g. "Mon reel: placeholder take" |
| Brand | select (one option per brand) | agents | The account: the last part of the brand's path (`founder/demo` → `demo`) |
| Week | text, `2026-W05` | agents | ISO week of the batch |
| Date | date | agents | The planned posting day and time (the connector writes it as `date:Date:start`) |
| Format | select (`reel`, `carousel`, `post`, `story`, `short`) | agents | Options are added by the Board only, in Notion (the hook blocks structural writes for every agent) |
| Pillar | text | agents | From the brand's `pillars.md` |
| Status | select (`Draft`, `In review`, `Ready for Board`) | agents | The piece's progress, not the Board's decision |
| KB page | url | agents | The piece's KB path |
| Gemini flags | text | agents | `language_check`'s remaining flags (SA-004); empty where the check is off |
| Preview | files | (unused) | Uploading files needs Notion's API with a write token, which no agent holds. Previews are in the shared media folder instead (below) |
| **Approval** | select (`Approved`, `Rejected`, `Changes`) | **the Board** | The decision on the piece |
| **Board comment** | text | **the Board** | What to change, in the Board's words |
| **AI label** | checkbox | **the Board** | Whether the Instagram post carries Instagram's AI label: the Board's choice on each post, **off unless the Board ticks it** (SA-005). **On:** Metricool sends Instagram's AI flag (`isAiGenerated` true) and the files go up as made. **Off:** no label, and `stage_item.py` uploads a copy with the C2PA, XMP and IPTC metadata removed (`publish/strip_ai.py`; a watermark in the pixels, such as SynthID, stays), refusing any file it can't clean. The sync copies it into `approvals/` at every query, decided or not; it counts when the piece is staged. The page's `ai_generated` stays our record of what is AI-made, and for an `ai_generated: true` piece the CMO's recommendation says so, so the Board chooses knowingly. A Short's YouTube flag is still the page's `ai_generated` ([README.md](README.md), "Channels") |

## Seeing the media on the phone

`workspaces/marketing/media/` can be a link into a folder the founder's phone syncs, so the Board opens each piece's PNGs, frames and cuts there: `<that folder>/media/<brand>/<week>/<piece>/`. The producer writes that path in each Notion item's page body. The hooks resolve the link, so writes into it still count as media.

**The Board's one-time step** (in a terminal, in this repo's folder; what is in a synced folder leaves this computer, which is the Board's choice):
```
SYNCED="<the full path of a folder your phone syncs>"
mkdir -p "$SYNCED/media" "$SYNCED/Inbox" "$SYNCED/Swipe" workspaces/marketing
ln -s "$SYNCED/media" workspaces/marketing/media
ln -s "$SYNCED/Inbox" workspaces/marketing/inbox
ln -s "$SYNCED/Swipe" workspaces/marketing/swipe
```
If any of the three exists already, move its files into the synced folder and remove the empty folder first.
Without this step the three are plain folders on this computer. On macOS, agents that write through a link out of the repo also need that folder in `.claude/settings.local.json`'s `additionalDirectories`.
The Inbox is where the founder drops his voice notes, notes and clips for the week (`workspaces/marketing/inbox/<brand>/<week>/`). Only he writes there; agents read it.

## Syncing the Board's decisions

No one runs a sync. Whenever any session queries the calendar in rows mode (`notion-query-data-sources` with `"mode": "rows"` and the data source), filtered by Week (and Brand) only and with every row returned, the PostToolUse hook `scripts/notion_approvals_sync.py` copies each returned item's Board fields into `knowledge/marketing/<brand>/approvals/<week>.md` (`owner: board`), one row per item, keyed by its Notion URL.
- The rows come from the connector's own response, not from an agent's retelling, and are only added or updated, never removed. Any other filter is ignored, so a decision can't be kept stale by never querying it.
- Items not yet Approved get the page's current SHA-256 at every sync. When Approved first appears, the row keeps the page and hash, and the Note column says if the page changed since the last sync before the decision, or if there was no earlier hash. Later, if the item points elsewhere, the page changes, or Notion moves it, the Note says so.
- Scheduling needs an Approved row with no note on the page as it is now (`tools/marketing/publish/post.py`).
- The cmo's weekly step is simply that query (the `content-calendar` skill). Agents read these pages and never edit them; no agent may run the script by hand.

No token or integration is needed: the hook reads what the Board's own Notion connection returned.

**The scheduling poll** (optional, macOS only). Every 30 minutes from 08:00 to midnight (Mac time), a launchd job on the founder's Mac runs the cmo (`scripts/marketing_schedule_job.sh`). It starts that session only while some founder piece is due: not yet scheduled, with its Publish at still ahead, or, for a page post.py's `read_piece` can't read as a post, in this week or the next; or whose path matches only when letter case is ignored (`scripts/marketing_schedule_gate.py`). If the gate itself fails, the session starts as before. When nothing is due it logs one line and syncs nothing: a decision made after that gets no "Not scheduled" line unless another piece keeps the poll running, and the cmo's own query of the week records it.
- It queries this ISO week and the next, which syncs the Board's decisions. Each piece at `Ready for Board` that the Board set to Approved, and that isn't scheduled yet, is then scheduled in Metricool. The Metricool post id goes into the item's page body, or "Not scheduled: <reason>" if staging refuses.
- So the Board's steps for an Instagram post are Approved here and Publish in Metricool's app. A Short may not wait for that tap: Approved here may be its only gate, and it stays private until the Board makes it public ([README.md](README.md), "Channels").
- Log: `~/Library/Logs/agentic-company/cmo-schedule.log`. Install it with `scripts/marketing_schedule_job.sh install`, from the checkout it should run in; remove it with `uninstall`.

**When the Board posts a piece himself:** the producer sets its page's `- Publish at:` to the posted time, or the latest it can be when the exact time is unknown, with a line under it saying so. Staging then refuses it ("2 hours to 6 days ahead") and the gate stops counting it. The cmo renames the Notion item "… POSTED by the Board …", moves it off `Ready for Board`, clears its Date, puts a line saying it was posted at the top of its page body, and queries the Week so the approvals row carries the name. Approval stays the Board's; nobody writes the ledger by hand.

## The Swipe database (the reel library)

"Swipe", next to the calendar, created by the Board. Its data source id goes in `company.json` (`integrations.marketing.notion.swipe`).

| Property | Type | Set by | What |
|---|---|---|---|
| Name | title | the founder | Account and a short topic |
| Reel URL | url | the founder | The reel's link |
| Brand | select (one option per brand, and `any`) | the founder | Which account it's a lesson for |
| Type | select (`reel`, `carousel`, `story`) | the founder | |
| File | text | the founder | The file name in the Swipe folder (`workspaces/marketing/swipe/`), when the reel wasn't downloaded |
| Status | select (`Saved`, `Ingested`, `Teardown done`) | founder, then the cmo | The hook lets the cmo and producer set any of these fields; only the cmo should, and only Status and Teardown, plus the row itself for a link given in the chat to learn from (a link to try gets no row) |
| Teardown | text | the cmo | The teardown note's KB path |
| Saved | created time | Notion | |

**The founder's step per reel:** give the link: add a row here with the Reel URL, Brand and Type, or send the link in the chat. The cmo downloads it with `fetch.py` (public videos only, no login) and keeps the video with its manifest. Where `public_downloads` is off, or if a site refuses without a login, the cmo asks for the file: save the reel's video to the Swipe folder (or screen-record it there) and put the file name in the row. A link sent only to try is a download test: no row. The `swipe-teardown` skill does the rest.
