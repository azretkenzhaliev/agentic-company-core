# The Board desk

A chat moves too fast to read and track. The Board desk is where the founder (the Board) reads what happened and answers what the company asks, at their own pace, on a phone if they like: one "Board desk" page in Notion with the asks, the questions and answers, the hourly progress and the daily summaries. The company's own copy stays in the knowledge base.

It is optional and **off by default**. With it off, nothing runs and nothing is sent; "Run without it" says how the company works then.

## What it is

| Part | What it does |
|---|---|
| `knowledge/company/board-desk/asks.md` | What the CEO asks the Board (`A-n`) and the steps only the Board can take (`B-n`). Written by the CEO. |
| `knowledge/company/board-desk/qa.md` | The Board's questions and the CEO's answers (`Q-n`). Written by the CEO. |
| `knowledge/company/board-desk/progress.md`, `summaries.md` | An entry an hour, and a summary of each day. Written by the job alone. |
| `knowledge/board/answers/<YYYY-Www>.md` | The Board's own words on each ask, word for word (`R-n`). Written by the reader alone. |
| `scripts/board_desk.py` | The job: the hour, the day, the read and the set-up. Its docstring is the full description. |
| `scripts/board_desk/adapter_notion.py` | The Notion side. |
| `scripts/board_desk/answers_seal.py` | The seal that shows a change to the answers made outside the reader. |
| `scripts/board_desk/scribe.md`, `daily.md`, `directives.md` | The writers' rules: the hour's entry, the day's summary, each directive's lines. |
| `scripts/board_desk/desk_ids.json` | The desk's Notion ids (ids only), empty until `setup` fills it. |
| `scripts/hooks/board_desk_bash.py` | The guard on agents' Bash; always on, whether the desk is or not. |

Two jobs run it:

- **`run`, every hour at :00.** It gathers the hour's status-log rows, asks, answers, commits on `main`, merged pull requests and production runs, and has a model write one entry of at most 600 bytes. An empty hour costs no model run. At the first run after 10:00 it writes yesterday's summary and moves old entries to the archive pages.
- **`read`, every 2 minutes.** It reads the Board's answers from Notion, keeps each one as an `R-n` row, then pushes each ask, page and question that changed. Only an edit Notion shows as made by the Board's own account counts as an answer.

The writer is one turn of `claude -p` with no tools, no MCP, no settings and no session, on the founder's Claude subscription (`ANTHROPIC_API_KEY` is taken out of its environment). Every id, date, time and number it writes must be in its packet; one that isn't is marked "(unchecked)".

## What it sends out

Read this before you turn it on. With the desk on:

- **To Notion:** the asks and the questions and answers, whole; every page of `pages` (by default the progress and summary pages and "How the company works"), whole; and for each directive that is open, or done in the last 7 days, its title, its status, the Board's own words in it (the first 2,000 characters of "Directive (verbatim)") and its hourly entries. Nothing is screened, held back or replaced: a customer's name, an address or a link in one of those pages goes to your Notion workspace as it is. Keep what must not leave the company out of those pages.
- **To Claude** (the writer's model), as it is in the same way: the hour's status-log rows, new and changed asks, when each answer came (not its words), and the titles of commits, merged pull requests and production runs; each directive's own lines of that; and for the day's summary the progress page's day, the previous summary, the backlog and open-directive lines, the spend lines, and the counts of pull requests and production runs. Each packet also has the plain names of the ids in it.
- **Never:** `ceo-questions.md` files, transcripts, research notes, customer data the pages don't hold, and the Notion token.

That choice is the founder's, so the desk ships off, and `/onboard-company` asks.

## Set it up

You need macOS for the Notion side (the token is in the Keychain and the jobs are launchd's), a Notion workspace you own, and `claude` signed in on this machine. `gh` is optional: without it, or for a repo it can't read, the entry says what wasn't read.

1. **In Notion:** make a page titled `Board desk`. Create an internal connection (integration) for the workspace: it must read, insert and update content, and read user information (the attribution test lists the workspace's people). Share the `Board desk` page with the connection, and nothing else.
2. **The token, in your own terminal,** so no agent sees it: `security add-generic-password -s board-desk-notion -a notion -w`, then paste the connection's token at the prompt. Only `adapter_notion.py` reads it, into memory, per run.
3. **`company.json`:** add the block below ("Settings"). `{}` is enough to turn the desk on. No subagent writes this file; a hook asks you first.
4. **Set up the pages:** `python3 scripts/board_desk.py setup`, from the main checkout. It makes the pages and tables under `Board desk`, sorts each table's view, writes their ids, and lists the workspace's people. Commit `scripts/board_desk/desk_ids.json`: it is how a fresh clone's guards know which Notion pages are the desk's.
5. **The attribution test:** `python3 scripts/board_desk.py attribution --board <your id from that list>`, and do the two steps of the row it makes in Asks. Until Notion shows your phone edit as yours, no answer counts. The second step shows whom Notion names when your own Claude app edits for you; a guard refuses agents' Notion writes on the desk's pages either way.
6. **The jobs:** `python3 scripts/board_desk.py install`, from the main checkout. Run it again after `setup` if the read job wasn't installed, and after you change `claude_config_dir`. To change `launchd_label`, run `uninstall` first, then change it, then `install`: the jobs under the old label keep running otherwise.
7. **Check it:** within 2 minutes the log shows a read; at the next :00, `progress.md` has an entry.

## Settings

In `company.json`:

```json
{
  "timezone": "America/New_York",
  "integrations": {
    "board_desk": {
      "github": "https://github.com/example/acme-company/blob/main/"
    }
  }
}
```

| Key | What it is | Left out |
|---|---|---|
| `timezone` (top level) | The time zone of every time the Board reads, an IANA name | UTC |
| `products` (top level) | Each product's `repo`: whose merged pull requests the entries read | none read |
| `root_title` | The Notion page shared with the connection | `Board desk` |
| `github` | Where a KB path in a Notion row links: this company repo's `blob/main/` address | the path stays text |
| `pages` | The KB pages pushed whole, `{"key": ["Notion title", "KB path"]}`, each under `knowledge/`. It replaces the default list whole, and the next `setup` makes the pages it adds and moves those it drops to Notion's trash | `progress`, `summaries` and `company` (`knowledge/company/how-it-works.md`) |
| `workflows` | Each product's production workflow file, `{"<product id>": "production.yml"}` | no production runs read |
| `launchd_label` | The hourly job's launchd label; the read job's is this with `-read` | `com.agentic-company.board-desk` |
| `claude_config_dir` | The Claude account the launchd jobs' writers run on, as `CLAUDE_CONFIG_DIR` | `claude`'s own |

The desk is off when `integrations` has no `board_desk`, or when its value isn't an object (`false`, `null`). A `company.json` that can't be parsed stops every command; a `timezone` or `pages` that can't be used stops every one but `uninstall`. The Board's Notion id isn't a setting: only the attribution test records it, in the desk's own state.

One desk per Mac user, whatever the label: the Keychain item, the seal's folder and the log are the user's.

## The jobs and the log

- launchd: `com.agentic-company.board-desk` (hourly) and `com.agentic-company.board-desk-read` (every 2 minutes), in `~/Library/LaunchAgents/`. `launchctl list | grep board-desk` shows both and their last exit codes.
- The log: `~/Library/Logs/agentic-company/board-desk.log`. It holds counts, tokens, exit codes and Notion's refusals, never a page's text. When the capacity scan prints `DESK STALE`, look here first, then at `launchctl list`.
- State: `workspaces/board-desk/`, gitignored.
- The Mac asleep or off: the missed hours become one entry. A read that fails is tried again at the next one.
- **Elsewhere (Linux, WSL 2):** don't set up the Notion side. `install` and `uninstall` say they can't and do nothing. Cron can start the hour: `0 * * * * cd <repo> && PATH="$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin" CLAUDE_CONFIG_DIR="$HOME/.claude" python3 scripts/board_desk.py run`. Cron has neither of its own: `PATH` must hold the folders of `claude`, `git`, `gh` and a Python 3.10 or later (without `claude` an entry is the raw list), and `CLAUDE_CONFIG_DIR` names the account (leave it out for `claude`'s own). The pages in the knowledge base are written as on a Mac; the Notion side doesn't run, so the Board reads them there, and the CEO quotes each ask in the chat, where the Board answers (`ceo.md`, "The desk").

## Protection

The CEO acts on each answer as the Board's word, so an agent must not be able to write one by mistake.

- **The folders:** agents never write `knowledge/board/answers/` or `workspaces/board-desk/`: `guard_kb_write.py` holds Write and Edit, `board_desk_bash.py` holds Bash, and `guard_marketing_tools.py` holds Notion writes to the desk's pages through Claude's connector. They hold whether the desk is on or off. The CEO's main session commits the answers.
- **The commands:** an agent may run `wait`, `install`, `uninstall` and `--help`; the CEO's main session also `setup` and `attribution`, on the Board's steps. `run`, `hour`, `day` and `read` are the jobs' (or the founder's own). `readback` is the founder's own. `seal` is the Board's alone.
- **The token:** no agent reads the desk's Keychain item.
- **The seal:** the reader keeps a digest of every answer row and of its own state outside the repo. A change made any other way shows as `ANSWERS TAMPERED <R-id or file>` in the capacity scan, the next hour's entry and `wait`, and that row is never shown as the Board's answer. Once an hour the reader also compares its rows with Notion itself.
- **After an alarm:** look at what changed. Then pick Yes in "Your answer" on the Asks row "Answers checked", or run `python3 scripts/board_desk.py seal` in your own terminal. Rows the alarm named are set aside; enter an answer of yours again.

It stops mistakes; it isn't a sandbox.

## Run without it

With the desk off, the CEO works with the knowledge-base pages alone:

- Asks and Board steps still go in `asks.md`, whole, in the shape of `knowledge/_templates/ask.md`, and are also quoted whole in the chat as plain text, where the Board answers (an email, if `board_email` is set, quotes it too, without secrets or customer data). The CEO records the answer on the page and in the directive.
- Questions and answers still go in `qa.md`.
- `progress.md`, `summaries.md` and `knowledge/board/answers/` stay empty; `/report` gives the status.
- `python3 scripts/board_desk.py run` and the other jobs' commands print one line and end; `wait`, `setup`, `attribution`, `readback` and `install` refuse.
- The guards stay on.

## Turn it off

1. `python3 scripts/board_desk.py uninstall` (it works with the desk off too).
2. Take `board_desk` out of `company.json`'s `integrations`.
3. In Notion, remove the connection from the `Board desk` page; delete the page if you want its copies gone.
4. `security delete-generic-password -s board-desk-notion -a notion`.

The knowledge-base pages, the answers and the state stay.
