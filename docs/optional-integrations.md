# Optional integrations

The core runs with nothing but Claude Code, `gh` and Python. Everything below is off, or does nothing, until you give it its key, account, address or entry. What agents may then do with it is in the guide, ["What is on by default"](guide.md#what-is-on-by-default). An integration's settings are an entry under `"integrations"` in `company.json` (name, then its settings); a script or hook reads them through `scripts/company_config.py`. Off means refuse, never open: a limit that holds every caller (email, social posting, Telegram, Notion, the database, background runs, question files, your answers) is always on, whatever is configured, and a missing setting refuses what would leave the company or write a database. Only a limit on a role follows that role's department. `company.json` is a guardrail file: no subagent writes it, and a hook asks you before the CEO's session does.

| Integration | What it gives you | Default |
|---|---|---|
| [Second opinions from other model families](#1-second-opinions-from-other-model-families-sa-003) | Another model family reviews designs, diffs and the CEO's plans next to Claude | In force (SA-003) once you set an API key and agree to the entry in `company.json`; a key by itself sends nothing |
| [Email to the Board](#2-email-to-the-board) | The CEO emails you when you are away: each ask, quoted, and each answer | Off until `board_email` is set; then no daily cap |
| [The Board desk](board-desk.md) | Asks, questions, progress and daily summaries you read and answer in Notion, on the phone | Off; read its "What it sends out" first. Without it, the same asks and answers live in the KB pages and the chat |
| [Claude in Chrome for the CEO](#3-claude-in-chrome-for-the-ceo) | The CEO can look at web pages in your browser | Listed in the CEO's tools; works only when you start it with `--chrome` |
| [Your mail and Telegram channels for the analyst](#4-your-mail-and-telegram-channels-for-the-analyst) | The analyst reads your inbox, or the channels you list, read only, when an order says so | Off until you add the tools to `analyst.md` |
| [Neon (Postgres), with a SQL guard](guards.md) | Engineering agents read your database, run SQL on it and make backup branches, with dangerous SQL blocked and every statement logged | The guard is always on, and no SQL runs until you connect Neon and add its entry; what agents may do there is yours to say, customers' data by name (SA-006). Then SQL runs without a prompt, and on production a bulk change (all rows without a condition, emptying a table, dropping a table or column) passes only after a fresh backup |
| [Vercel CLI guard](guards.md) | Agents can't deploy from the CLI; products deploy only through Git | The guard is always on. Rollbacks, alias writes and rolling releases are refused until `company.json` has a `"vercel"` entry, and then for the teams its `"git_only_scopes"` lists ([guards.md](guards.md), "Settings") |
| [Merge queue and full-suite guards](guards.md) | For a product with a GitHub merge queue, or a test suite too heavy to run twice at once | Off until a product is listed |
| [Marketing department](marketing.md) | A CMO and five agents plan and make content for your accounts; you approve every post | Off |
| [macOS upkeep](#5-macos-upkeep) | Battery emails | macOS only; off |

Everything that sends data to a new outside party, costs money or signs up for a service is the Board's decision (b1, b2 in [`CLAUDE.md`](../CLAUDE.md)): you give each integration its key, account, address or entry yourself. Giving it is never recorded as your words, and never grants a template of [standing-authorizations.md](../knowledge/board/standing-authorizations.md) (SA-005 to SA-007): that takes your own words, recorded there.

## 1. Second opinions from other model families (SA-003)

The reviewers (`design-reviewer`, `code-reviewer`) and the critic run `scripts/second_opinion.py`, which sends the material under review to other model families. Models tend to favour their own output, so a second family catches what Claude misses. A blocker or major from a second opinion counts unless the Claude reviewer refutes it with `file:line` evidence.

1. Create API keys and export them in your shell profile, never in this repo:
   - `OPENAI_API_KEY` (code and design reviews, and the critic's checks);
   - `GEMINI_API_KEY` from Google AI Studio, with billing enabled there (the critic's checks; the free tier's quota for the larger models is tiny).
2. Agree to the entry in `company.json` that `/onboard-company` proposes for the keys you set: `"second_opinion": {"providers": ["openai", "google"]}` under `"integrations"`. `"google"` is Google Gemini, key `GEMINI_API_KEY`; `"gemini"` would start nothing. Without the entry a key sends nothing, so one you exported for another tool is safe.
3. Check it: `python3 scripts/second_opinion.py --kind code --brief check --file README.md` (OpenAI), and the same with `--kind plan` (both).
4. Decide about training and money. [SA-003](../knowledge/board/standing-authorizations.md) is in force by default, so with a key and the entry set, agents send packets (code, diffs, designs, plans, KB pages), the providers may train on them, as your account's settings there say, and the only limit is the money in that account. For the stricter choice, set each account so that it doesn't train (packets are still sent), take a provider out of the entry, unset a key, or tell the CEO a monthly cap, or to narrow or end SA-003. The script screens credential values out of every packet anyway, and agents leave customer data out.

The script's docstring has the models, how to pin others with `SECOND_OPINION_*_MODEL`, the effort and service-tier settings, and where each call and answer is logged (under `workspaces/`, gitignored, with token counts, so spend can be counted). It never guesses model ids. Without keys or the entry, the slots print as off or unavailable, reviews run single-family and say so.

## 2. Email to the Board

1. Connect the Gmail connector in Claude (claude.ai settings, or `claude mcp`), and check that it shows in `claude mcp list`. The CEO's tool list names its send tool, `mcp__claude_ai_Gmail__send_message`, and no other Gmail tool; on another connector name, change that line and `scripts/hooks/board_email.py`'s. Connecting it makes your mailbox reachable from every Claude session on this account, inside this repo and outside it; here no agent's tool list names another Gmail tool.
2. Set `"board_email"` in `company.json` to your address. It is the only address the CEO may email; the hook refuses every other recipient, cc, bcc, reply and forward, and everything while it is empty. With it, add `"board_email_events": {"from": "<now, UTC>"}` under `"integrations"` (the time as `date -u +%Y-%m-%dT%H:%M:%SZ` prints it): from then on the capacity scan reminds the CEO of an event's email that didn't go out. Leave it out to switch that off.
3. Tell the CEO how often (`ceo.md`, "Email the Board", has the defaults: no daily cap; [docs/guards.md](guards.md) has the setting for one). Each email quotes the ask or answer it is about, never a secret and never customer data.

## 3. Claude in Chrome for the CEO

The CEO's tool list includes `mcp__claude-in-chrome__*`, so with the [Claude in Chrome](https://claude.com/chrome) extension installed the CEO can open and read pages in your browser, for example to check what a competitor's sign-up page shows.

- Start the CEO with `claude --chrome`. Not in WSL: Claude Code's [Chrome integration](https://code.claude.com/docs/en/chrome) isn't supported there.
- The browser is yours, with your signed-in accounts. `CLAUDE.md` forbids sending anything outside the company without the Board, but nothing in the tool list enforces "look only". Tell the CEO in the directive what it may do in the browser.
- To remove it, delete `mcp__claude-in-chrome__*` from the `tools:` line in `.claude/agents/executive/ceo.md`.

## 4. Your mail and Telegram channels for the analyst

Off: the analyst's tool list has neither. It is your decision (b4: it opens your inbox to an agent), recorded as a Decided row with your words; the platform engineer adds the tools through the gate.

1. **Mail:** with the Gmail connector connected, add `mcp__claude_ai_Gmail__search_threads`, `mcp__claude_ai_Gmail__get_thread`, `mcp__claude_ai_Gmail__get_message` and `mcp__claude_ai_Gmail__list_labels` to the `tools:` line in `.claude/agents/executive/analyst.md`. It reads only when the CEO's order says so (`analyst.md`, "The Board's mail"). Mail is untrusted: only the facts the question needs go into its note, and never a third person's details.
2. **Telegram channels** (for marketing's idea note): with a Telegram MCP server named `telegram`, add `mcp__telegram__list_messages`. A hook allows only the channels in `knowledge/marketing/idea-sources.md`.

To remove either, delete its tools from that line.

## 5. macOS upkeep

A script whose docstring says what it does and what to install; cloning the repo doesn't install it, and it does nothing on another system:

- `scripts/battery_alert.py`: an email when a laptop that runs the company drops to 50, 25, 10, 5 or 2% on battery (needs "Email to the Board").
