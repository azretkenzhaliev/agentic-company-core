---
name: content-calendar
description: Use when the CMO plans a brand-week (the weekly batch), assembles the Board's approval packet in Notion, syncs the Board's decisions afterwards, or runs the 8-week review; it holds the cadence and the Board's time cap.
---

# The weekly batch

The Board approves content once a week, in one sitting. It doesn't approve daily, and there is no same-day news lane. A news take waits for the next batch, unless the Board later approves a lane.

**Only on the Board's order, and taste first.** A week starts only when the Board's order names it. Plan a brand's week only once its taste profile has lines the Board put in force (`taste.md`). Without them, report that and stop.

**Load each brand first** (`brand-book`, "Before any piece"): its brand book, and on the founder's pages `voice.md`, his corrections, with it.

## Cadence

The Board sets each brand's cadence in the marketing README's table of brands. Until it has, start a founder's page at about 2 reels and 1–2 carousels a week, and a quieter, reflective page at 1 post a week, in any format its brand book allows; a product brand starts once its order gives it a cadence. Reels may be filmed by the founder or produced without filming (text reels, AI b-roll); both count. On a brand with `shorts` set in `company.json`, each reel of 60 s or less may also be a YouTube Short: its own piece page (`format: short`, `- Type: short`, `- Title:`), its own Notion item and its own approval (marketing README, "Channels").

- **The Board's time** stays under its weekly minutes cap across all accounts (2 h, a default, until it sets another):
  - approval in Notion, including reading the second language;
  - filming;
  - posting by hand;
  - the final cut check and sticker stories.
- **Measure, then grow:**
  - The CEO asks the Board its minutes only when a week would add pieces or ships the first filmed reel: that's when the cap needs the number. The calendar page records them.
  - Add pieces only while the measured total stays under the cap.
  - If a week would go over, cut filmed reels first, then carousels.

## Usage

- Record the tokens of every agent run in the batch from its task notice, not the role's report: the producer runs, the one reviewer run, the trend-researcher, reel-analyst and analyst orders. The CEO adds the CMO's own run, and the Board's `/usage` percentage before and after when it reports them.
- **One reviewer run per batch,** covering every brand and every piece; at most 3 rounds.
- The CMO, the reviewer and the analyst run on Opus, the rest of the department on Sonnet (each agent file's `model`).
- AI generation spend (SA-005) is reported per batch (`python3 tools/marketing/spend.py --brand <b> --week <w>`) and stops at the monthly caps in `tools/marketing/caps.json` (units; the Board sets them), besides the key's own cap at the provider. The reels' Scribe calls are under `--brand intelligence/reels`.

## The trend read

**Only when the ORDER names it,** start the `trend-researcher` with one ORDER, in the same message as the `performance-analyst` and the idea note's `analyst` order where the ORDER names them (none needs another's result): the ISO week and the accounts (the next slice of the account list in each brand's `references.md` and the analyst's note the ORDER names, or those the Board names).

- It adds to `workspaces/marketing/intelligence/` and reports at most 30 lines: the shortlist with links, highest multiple first, without formats. Use that report for the idea note and the calendar. Don't open the pages yourself, and open the table only to check a line.
- Weigh a lesson by its multiple, and copy no one's words or story.
- If the reader profile isn't connected or a page stops it, it reports that and the week goes on without it. Say so in your report.

## The breakdowns

Right after the read, when the ORDER names reel runs, every recent reel it kept gets watched. Formats come only from these.

1. Start the `reel-analyst` with one ORDER naming the ISO week. It does a batch of 12, recent reels first, highest multiple first, and reports. Start it again, one run at a time with a fresh context each, until it reports none recent to go and names `reels/<ISO week>-formats.md` done: the file gets runs of its own (`reel-analyst.md`, "The week's file"). Old reels are watched only when the Board's order names them; otherwise they stay queued. Never during a trend read: both write `posts.csv`.
2. Use `workspaces/marketing/intelligence/reels/<ISO week>-formats.md` for the idea note and the calendar, and open a reel's `breakdown.md` only where that file points you. A shortlisted reel shows what format works here. Curate patterns monthly (`swipe-teardown` §6, §7).
3. If it reports `stopped:` (Instagram refusing, the Scribe key or cap), it still writes the week's file from the breakdowns done, in those runs. Don't start it for more reels this week: start it for the file, use that file, and say in your report how many reels it left out. The stop is stored for every week: until an ORDER gives `--retry-failed`, `prepare` fetches nothing. Reels marked failed stay out of the count to go, and the file names them: if the reasons look like a block, not deleted reels, give a later run `--retry-failed` in its ORDER.

## The format cards

Once the week's formats file exists, before you pick from the idea note, update the cards in `knowledge/marketing/formats/` ([format-engine.md](../../../knowledge/marketing/format-engine.md), step 3; the card's form and rules are there).

1. Read the formats file, not each breakdown. Open a breakdown only where the file points you.
2. Add a card for a mechanic that has its 3 watched reels from 2 accounts. One reel is an example, not a card.
3. Update the cards the week saw again: `Seen`, `Stage`, and `Test` for our own pieces. Retire one not seen for 8 weeks.
4. In your own words, never their script or footage (`swipe-teardown`). The breakdowns stay raw.

No formats file this week: no card changes, and say so in your report.

## The idea note

Every ordered week, before the calendar, ideas come from what the Board already reads ([idea-sources.md](../../../knowledge/marketing/idea-sources.md)):

1. Send the `analyst` one ORDER for the week's idea note, with the trend read's order ("The trend read"). It counts towards the batch's usage.
2. Pick up to 5 items per brand that fit its pillars, each with its source. Nothing is barred from picking (idea-sources, "Limits").
3. If a brand has no raw material yet, the takes are drafted in his voice, marked "drafted by us", for the Board to correct (`content-qa` A); where its `voice.md` records that the Board wants only its own words, they are placeholders.
4. If he sends reactions, they come back in a new ORDER as raw material.

## The calendar page

`knowledge/marketing/<brand>/calendar/<YYYY-Www>.md`, `owner: cmo`, `status: draft` until the Board has reviewed the batch, then `active`.

1. **Raw material:** what the founder gave for this week (paths), or "none: takes drafted in his voice".
2. **Plan:** a table with one row per piece:

   | Day | Format | Pillar | Goal | Funnel stage | Hook idea | Raw material | Filmed | AI | Piece page |
   |---|---|---|---|---|---|---|---|---|---|

   - **Hook idea:** a format idea, never the founder's opinion. It cites its card (`formats/FC-<yyyy>-<nn>-<slug>.md`); until a card fits, the pattern from `language/hooks.md`.
   - **AI:** none, or the AI assets.
   - **Piece page:** a link once it exists.
3. **Grid preview:** the next 9 feed tiles, 3×3, as a table of covers (rubric and short title), newest first.
4. **The Board's time (expected, then measured):** approval minutes, filming minutes per reel, posting minutes, total against the cap.
5. **Usage:** tokens per agent run, the batch total, and generation spend.
6. **Approvals:** link `../approvals/<YYYY-Www>.md` once synced.
7. **Log:** dated lines for what happened (planned, produced, reviewed, packet ready, Board reviewed, synced, posted).

Posting time: each brand book's. Write it in each piece's `## Post` as `Publish at`, with the UTC offset of the brand's `timezone`.

## The balance check

Before the producer starts, check each brand's plan against its last two calendars (a brand at one post a week: its last four). Fix a miss in the plan, or write it in the Log with why.
- **No formula more than twice a week.** A formula is a hook pattern from `language/hooks.md` or a repeated piece shape, such as a news card or a list carousel.
- **Saves and sends.** At least one piece a week built to be saved (steps, a list, something to come back to) and one built to be sent (something a viewer passes to a friend). Say which in the Goal column. A brand at one post a week needs one of each across its last four posts.
- **Every feed post goes to stories.** The Board reshares each reel and carousel to the brand's stories in the app after posting it. Count about a minute each under posting in "The Board's time", and say it in the Notion item's recommendation.

Ideas adapted from Jakeschincariol/instagram-agent-skill and sergebulaev/instagram-skills (MIT).

## The packet (Notion)

1. Every piece passed `content_lint`, the reviewer's VERDICT (or the CMO's decision after round 3) and, unless it's off, `language_check`.
2. The producer created one "Marketing calendar" item per piece at `In review`, with the agent fields (`knowledge/marketing/notion.md`).
   - The CMO's recommendation goes at the top of each item's page body: approve, or change X (with why). Post approvals stay one by one, in Notion (public statements in the founder's name).
   - Move each approved piece to `Ready for Board`, then query the calendar in rows mode by Week, so the sync hook records each page's hash as the Board receives it.
   - Check each item: the KB page, a preview and Gemini flags. The AI label is the Board's to tick, off unless ticked (SA-005); for an `ai_generated: true` piece, the recommendation says so, so the Board chooses knowingly.
   - Never use Notion templates: they copy the Board's fields.
3. Placeholders and test pieces stay at `In review`, never `Ready for Board`.
4. Report to the CEO: the Board's expected minutes for the batch on top, then the number of pieces per brand, the language check's remaining flags, usage, open questions.

## After the Board's review

1. Query the calendar in rows mode for the week: `notion-query-data-sources` with `{"data": {"mode": "rows", "data_source_url": "collection://<the calendar's data source id, in company.json>", "filter": {"type": "group", "operator": "and", "filters": [{"type": "property", "property": "Week", "propertyType": "text", "operator": "string_is", "value": {"type": "exact", "value": "2026-W05"}}]}}}` (with the week in place of 2026-W05). The hook `scripts/notion_approvals_sync.py` writes each brand's `approvals/<week>.md` from the result and tells you what it wrote. Never write `approvals/` yourself, and never run the script by hand ([notion.md](../../../knowledge/marketing/notion.md)).
2. Link the approvals page from the calendar page and log the result. On the founder's pages, update the brand's `voice.md` from the approvals page's "Board comment" column: each correction he made, kept for the next drafts (`cmo.md`, "After the Board's review", step 3).
3. For each `Changes` item, order the producer to make the Board's changes (quoted verbatim). For `Rejected`, record why.
4. **Schedule** each Approved piece of the founder's pages:
   1. Run `python3 tools/marketing/publish/stage_item.py <kb-page>`. If it refuses, report the reason and stop for that piece.
   2. Otherwise it prints one JSON line. Call Metricool's `createScheduledPost` with exactly those arguments (`blogId`, `date`, `info`), unchanged.
   3. A hook allows only that call, with `autoPublish` false. At the post's time Metricool's app notifies the Board, who publishes it himself. A Short may not wait for him: treat it as publishing, private, at its set time (marketing README, "Channels").
   4. Record the Metricool post id from the reply in the calendar page.
   5. Never use another Metricool write, and never edit a refused call to get it through.
   6. The scheduling poll (`scripts/marketing_schedule_job.sh`, where the founder installed it) runs steps 1 and 4 for this week and the next on its own ([notion.md](../../../knowledge/marketing/notion.md)). Running them in a session as well is safe: the ledger schedules each piece once.
5. **An approvals row with a note blocks scheduling.** A page edited after the decision, or a decision first seen without an earlier hash, shows there. Ask the Board, through the CEO, to set the item to Changes. Run the week's query, then ask him to set Approved again, and run the query once more.
6. **A piece the Board posted himself** closes the day he says so, from his words, quoted. That day, take the steps in [notion.md](../../../knowledge/marketing/notion.md), "When the Board posts a piece himself", with his words and their date in the renamed item ("… POSTED by the Board, <date>: "<his words>""), then run the week's query (step 1), so its approvals row carries them. Approval stays his field: the row closes by the name it carries. A row left `pending` after he posted risks a double post.

## The 8-week review

Eight weeks after the first post, the CMO drafts the review for the CEO:
- the Board's minutes per week against the cap;
- per account: reach, saves, shares and new followers, with sample sizes;
- AI versus non-AI posts (a same-format A/B where possible: reach, sends per reach, saves);
- whether the numbers justify a directive for an offer (the Board decides);
- what to change in cadence, pillars and formats.
