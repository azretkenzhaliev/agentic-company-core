# The guide

What the system is, how it is laid out and how to change it. Installing it, starting it and the everyday steps are in the [README](../README.md), in five languages.

A startup run by Claude Code agents. You, the founder, are the **Board of Directors**: you set direction and talk only to a **CEO** agent. The CEO turns what you ask for into orders for an **engineering department** (a CTO who plans, Staff engineers who design and land one workstream each, Senior engineers who implement one task each, independent design and code reviewers, a UX expert), an **analyst** (research), a **critic** that checks the CEO's plans before you see them, a **platform engineer** that changes the company's own system, and, if you switch it on, a **marketing department**. A markdown **knowledge base** in git is the company's shared memory.

Everything is plain Claude Code: agent definitions, skills, hooks and permission rules. No extra framework, and it runs on your Claude subscription.

```
Board (you)
└── ceo                        also acting head of sales and product
    ├── analyst                research; writes raw, sourced notes
    ├── critic                 read-only; checks the CEO's plans and big decisions before you see them
    ├── platform-engineer      changes this system itself, in an isolated worktree
    │   └── code-reviewer
    ├── cto                    architecture, roadmaps, standards, runbooks
    │   └── staff-engineer     one workstream: design → review → tasks → landing
    │       ├── design-reviewer    read-only, checks designs against the real code
    │       ├── senior-engineer    implements one task, with tests
    │       ├── code-reviewer      read-only, checks each diff
    │       └── ux-expert          UX audits, specs, acceptance of built screens
    └── cmo                    optional: plans each week of content
        ├── content-producer       makes it
        ├── content-reviewer       read-only, a verdict per piece
        ├── performance-analyst    the weekly numbers
        ├── trend-researcher       reads public pages, read only
        └── reel-analyst           breaks down the reels it found
```

Who may start whom, with the models: [`knowledge/company/org-chart.md`](../knowledge/company/org-chart.md).

## What makes it work

- **A constitution** ([`CLAUDE.md`](../CLAUDE.md)) every agent loads: who decides what, the one list of decisions that need you (b1–b9), the chain of command, message formats (ORDER, REPORT, VERDICT) and safety rules. Nothing leaves the company (emails, posts, purchases, sign-ups) without you.
- **Directives.** Anything you ask for is filed as `knowledge/board/directives/D-YYYYMMDD-<slug>.md`, with your words verbatim, the CEO's plan, every order sent, a status log and the final report.
- **Little asked of you.** Agents decide everything that isn't on the list, tell you afterwards with how to undo it, and ask in one screen with one pre-selected answer. What you said once is kept in [`board-preferences.md`](../knowledge/company/board-preferences.md) and read before anything is asked again.
- **Every lane busy.** The CEO keeps independent work running in parallel and a backlog behind it; a scan says what is idle and why.
- **Effort scaling.** Questions are answered directly; a small change goes CTO → Senior with a code review; a workstream gets a short reviewed design; bigger work gets a roadmap with parallel workstreams.
- **Bounded review loops.** One round of design review and one of code review with a short re-check of fixes, then escalation with both positions.
- **Gated deploys.** Autonomous production deploys only through a verified runbook, behind every gate, with an immediate rollback when a smoke check fails ([SA-001](../knowledge/board/standing-authorizations.md)).
- **Persistence through stops.** Verdicts and state go into the knowledge base as they happen, so a usage limit or an outage costs minutes, not the work.
- **Hooks** that hold the line: who may start whom, no secrets in the knowledge base, your answers never written by an agent, dangerous SQL and CLI deploys blocked, and plain git reads, merges into a product worktree and pushes of its own branch pre-approved so background agents don't stall ([docs/guards.md](guards.md)). A limit that holds every agent stays on whatever you configure, and a missing setting refuses what would leave the company or write a database. They stop mistakes; they aren't a sandbox.
- **The company improves its own rules.** When you correct it, the rule's owner changes the rule the same day, through a reviewed change; loosening a guardrail always comes to you.

A plain-words tour: [`knowledge/company/how-it-works.md`](../knowledge/company/how-it-works.md). The lessons from running it: [`lessons-learned.md`](../knowledge/engineering/standards/lessons-learned.md).

## What is on by default

From the first start (items that begin after something you do say so), the agents do the following without asking you each time. Beside each is how to switch it off; where it says "tell the CEO", ordinary words are enough: the CEO writes them down and follows them. The command `/onboard-company` shows the same list and offers a stricter choice for each.

Everything you type, and everything the agents read, is sent to Anthropic, the company that makes Claude; that is how it works. On Pro, Max and Ultra plans it is used to train Anthropic's models when that setting is on in your account: check it at [claude.ai/settings/data-privacy-controls](https://claude.ai/settings/data-privacy-controls). On Team and Enterprise plans and Console accounts it isn't, unless you or your organization chose to give it.

1. **Work until the plan's limit runs out,** without slowing down to save it. With usage credits off in your Claude account, the work stops at the limit; with them on, it goes on past the limit and costs you money, up to the monthly limit you set (`Unlimited` when you set none); with a Console account, every use costs money. On Pro, Max and Ultra you switch the credits off and set that limit at [claude.ai/settings/usage](https://claude.ai/settings/usage) or with `/usage-credits`; a Console account's spend limit is set in the Console. To switch off: tell the CEO how far into the limit to go.
2. **Release new versions to users** once you have confirmed how the product is released and every check passes; they run only the essential tests and those the change touches. If something is wrong after a release, they bring back the previous version, and they tell you afterwards. To switch off: tell the CEO to ask you before each release, or to run all the tests.
3. **Start medium and large work** once its plan has passed review; you get a short summary. Plans that touch the list "What needs your yes" still wait for you. To switch off: tell the CEO that you want to see every plan.
4. **Read and manage the company's own passwords and keys** (`.env` files, where programs keep their keys; if you set up Vercel, a hosting service, also the values kept there, except those of the site your users use (production)) when a task needs them. Customers' passwords are off limits, and so is showing a value or sending it to anyone but Anthropic (whatever an agent reads passes through it) and the service the key belongs to. This is a rule the agents follow, not a technical barrier: nothing stops them from opening other key files on the computer either, your personal ones included (`~/.ssh`, `~/.aws`). To switch off: tell the CEO. To block those files, the guide has lines to add to the settings, after its copy of this list; ask the CEO to add them.
5. **Add reviewed code to a product's main version, and upload working copies of it (branches) to GitHub,** without a question in the terminal. If a product's repository is public, everyone sees them. To switch off: tell the CEO; it changes the settings (`.claude/settings.json`, `company.json`) once you confirm.
6. **Work in your Neon database** (a service that keeps a product's data on the internet), if you connect it and tell the CEO in your own words what they may do there (customers' data must be named separately): they run commands there without a question, and these can change and delete data. In the database your users use (production), changing or deleting all the rows of a table without a condition, emptying it, or removing a table or a column needs a fresh backup first, but then it is allowed; changing or deleting rows chosen by a condition needs no backup, even when that is nearly all of them, or all. To switch off: don't connect it, or tell the CEO, as in item 5.
7. **Repeat a stopped command once.** Guards are small programs that check the agents' commands and stop dangerous ones. When a guard stops a command and its message names the allowed form, the agent may run it once in exactly that form. To switch off: tell the CEO.
8. **Write you emails** with no daily limit, once you give your address, and only to it. To switch off: don't give the address, or name a limit.
9. **Send code, plans and pages to OpenAI and Google for a second opinion, and the texts of posts to Google for a language check** (the language check only with marketing on and with a key of its own). Second opinions start once you put the keys (`OPENAI_API_KEY`, `GEMINI_API_KEY`) where the guide says, never in the conversation, and agree to the entry in `company.json` that `/onboard-company` then proposes; a key by itself starts nothing. These companies charge for it, with no limit but the money in your account there, and may train their AI on what they receive. Customers' data and passwords must not be sent. To switch off: don't agree to the entry, remove the key, or tell the CEO to stop; forbidding training in your account switches off only the training.
10. **Not wait for legal texts:** wording on law, privacy and consent goes on a list for a lawyer, and the work doesn't wait for it, even if you already have customers; until then the risk is yours. Prices, terms and a new kind of message to customers still need your yes. To switch off: tell the CEO to settle the legal texts first.
11. **Draft your opinions for posts in your voice,** if you switch marketing on: you correct them, and nothing is posted without your yes. To switch off: tell the CEO to use only what you said yourself.
12. **Leave Instagram's AI label off posts with AI-made pictures or video,** if you switch marketing on, unless you tick it for that post; the hidden marks that say "made by AI" are removed from the uploaded copy. Instagram's terms and the law where you live may require the label: that is your responsibility. To switch off: tick the label on each post.
13. **Make the computer slow:** new heavy work waits only when about 2.5 tasks run or wait for each processor core, or, on a Mac, when less than 5% of memory is free. To switch off: name a stricter limit to the CEO.
14. **Improve the company itself:** they change its own agents, their instructions (skills) and its programs (scripts) without asking you; each change is first tested and reviewed by another agent, and the CEO tells you in its report. A change that loosens a guard, gives wider access, sends more data out or weakens something you said needs your yes, unless you already asked for it yourself; the settings (`.claude/settings.json`, `company.json`) change only on your word. To switch off: tell the CEO to ask you before every change to the company itself.

The list "What needs your yes" is in the [README](../README.md). The rules behind it: [standing authorizations](../knowledge/board/standing-authorizations.md) (items 1, 2, 4 and 9), [the charter](../knowledge/board/charter.md) (item 3), the CEO's "System changes" in [ceo.md](../.claude/agents/executive/ceo.md) (item 14), and [docs/guards.md](guards.md), with the setting to change for items 4 to 6, 8, 9 and 13. What stays off until you give it, because only you have it: accounts, addresses, keys, brands, languages, money and customers' consent. Second opinions, once on, spend until you name a limit, remove the key or stop them (item 9). Where to put item 9's keys: [optional integrations](optional-integrations.md), section 1.

To block key files (item 4), add these lines to `"deny"` under `"permissions"` in `.claude/settings.json`, by your own hand, or tell the CEO to. They stop the tools that read files, not a script that opens one itself:

```json
"Read(.env)",
"Read(.env.*)",
"Read(!.env.example)",
"Read(!.env.sample)",
"Read(!.env.template)",
"Read(*.pem)",
"Read(*.key)",
"Read(*.p12)",
"Read(*.pfx)",
"Read(id_rsa*)",
"Read(id_ecdsa*)",
"Read(id_ed25519*)",
"Read(~/.ssh/**)",
"Read(~/.aws/**)",
"Read(~/.config/gh/**)"
```

To keep the company's own `.env` files readable, leave out the first five.

Five smaller ones, each with its setting in [docs/guards.md](guards.md):

- **Tests, linters, and plain git and GitHub reads** run without a question (the allow list in `.claude/settings.json`).
- **Pull requests:** agents open them without a question, as they merge them (item 5).
- **Neon's reads and new branches** run without a question, once you connect it (item 6).
- **GPT's second opinions** run on OpenAI's cheaper, slower `flex` tier, and once more on the standard one when it is busy or too slow (item 9).
- **Up to 30 agents at once** (item 13; "Plan sizes", below).

## What it runs on

The steps are in the [README](../README.md); this is the why.

| Need | Why | Check |
|---|---|---|
| [Claude Code](https://code.claude.com/docs/en/setup) 2.1.295 or later, logged in with your Claude subscription | Every agent runs on it ([SA-002](../knowledge/board/standing-authorizations.md)). The guards are set to refuse when they fail (`"onFailure": "block"`); an older version may ignore that setting and let the action through ([docs/guards.md](guards.md)). Don't set `ANTHROPIC_API_KEY`: it would bill an API account instead | `claude --version` |
| git, and the GitHub CLI logged in with access to your product repos | Cloning, PRs, CI status | `gh auth status` |
| Python 3.10+ | The linter, the hooks and the scripts use only the standard library. On Linux, the hooks need `python3` on the `PATH` of the shell Claude Code starts | `python3 --version` |
| poppler (optional) | Lets agents read PDFs | `pdftotext -v` |
| Node.js 20 or later (optional) | Only for the marketing department's rendering tools ([docs/marketing.md](marketing.md)) and the ux-expert's browser check ([tools/ux/README.md](../tools/ux/README.md)) | `node --version` |

It runs on macOS and Linux, and on Windows inside WSL 2, with the folder on Ubuntu's own disk, not under `/mnt/c`. Don't run it directly in Windows yet: judging by its code and Claude Code's documentation, its guards can't start there, and commands run through PowerShell can pass without them. What to change is in [windows.md](windows.md); tell the CEO, from WSL 2 or a Mac: "Make the company run on native Windows, by docs/windows.md."

A few upkeep pieces (scheduled jobs through launchd, battery alerts) are macOS-only; they say so and do nothing elsewhere. So is the memory part of item 13 above; the disk and load limits hold on Linux and WSL 2 too. No scheduled job starts by itself: each needs its entry in `company.json`, which Claude Code asks you about, and its install command (the README's "Every day" lists them). The Board desk's Notion side doesn't work on Linux or in WSL 2, not even by hand: its key is kept in the Mac's Keychain, so don't set it up there; answer the CEO in the terminal.

**Always start Claude in this folder:** Claude Code loads the company's settings, hooks, agents and skills only from the folder a session starts in, once you accept its trust prompt.

## The first steps, in more detail

1. `/onboard-company`: the CEO interviews you for about 45 minutes: the company, each product, how deploys work today, which accounts agents may use, how you want reports, and which departments and integrations to switch on. It reads out what is on by default (above) in one message and offers the stricter choice of each; what you don't answer stays as it is. The CEO writes your answers into `knowledge/company/` and `knowledge/products/` and, with your approval in the prompt that appears, sets `company.json`.
2. `/onboard-codebase <product-id>` for each product. It runs as the CTO: it clones the repo into `workspaces/` (gitignored) and writes the product's architecture page and a draft deploy runbook. The runbook becomes `active`, and deploys autonomous, only after its steps are verified and you've confirmed how deploys work (SA-001).
3. Your first directive. The CEO proposes one in its onboarding report. Just write what you want; `/directive` is optional.

## Sessions

```bash
claude
claude --agent cto
cd .. && claude
```

- `claude` operates the company: you talk to the CEO (`"agent": "ceo"` in `.claude/settings.json`). Every session started in this repo is the CEO, including cloud sessions at claude.ai/code, which read the committed `.claude/settings.json`. In it: `/onboard-company`, `/directive <what you want>`, `/report`, `/kb-check`, `/onboard-codebase <product>`, `/system-check`.
- `claude --agent cto` is an escape hatch: you talk to the CTO directly.
- `cd .. && claude` maintains the system yourself (agents, skills, hooks, KB tooling). It starts from the parent folder, so none of the repo's `.claude/` loads: no `"agent"`, and also none of its hooks, permission rules, agents or skills. You seldom need it: the CEO orders the platform engineer to change the system and lands the reviewed commit.

## Plan sizes, models and parallelism

The defaults assume a large Claude plan: planners and judges run on `opus[1m]` at `xhigh` thinking, builders on Sonnet, and up to 30 agents at once. On a smaller plan, or when you hit limits often:

| What to lower | Where |
|---|---|
| **Models.** Set `model: opus` (no `[1m]`) or `model: sonnet`. Start with the CTO, Staff and CMO; keep the critic, the design-reviewer and the platform engineer on Opus longest, because they catch the others' mistakes | `model:` in `.claude/agents/**/*.md`; SA-002 lists who runs on Opus, and `scripts/tests/test_agent_models.py` checks the files against it, so change the three together |
| **Compaction.** An agent without a 1M window needs a smaller `autoCompactWindow` (for example `150000`) | the same front matter and test |
| **Thinking.** `effort: high` or `medium` | `effort:` in the same files; the same test checks it |
| **Parallelism.** Fewer agents at once | `CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS` in `.claude/settings.json`; and tell the CEO how many workstreams to run, which it records in `board-preferences.md` |
| **How far into the limit.** By default, until the account stops the agents; with a line of yours, managers start nothing new past it | `/onboard-company` offers it; kept in `board-preferences.md` |
| **Second opinions.** Nothing is sent until you set API keys (pay-per-token) and agree to their entry in `company.json` | [docs/optional-integrations.md](optional-integrations.md) |
| **Marketing.** Off until you switch it on | [docs/marketing.md](marketing.md) |

Nothing breaks when the account reaches its limit: agents stop, and their resume points are in the knowledge base. `python3 scripts/token_report.py` shows where the tokens go.

## Keep your copy private

Your copy's knowledge base records internal decisions and, in time, unfixed security findings about your products. Keep the repo private, and never push it to a public remote; that is why the README clones instead of forking (a fork of a public repo stays public) and sets `core`'s push address to `no-push`. Secrets still don't belong in it: name where a secret lives, never its value (a hook and the linter enforce this). `workspaces/` (product repos, local state, logs) stays out of git.

## Pull later core updates

Your company's own facts live in `company.json`, `knowledge/` and `workspaces/`; the system lives in `CLAUDE.md`, `.claude/`, `scripts/`, `tools/`, `docs/` and `knowledge/_templates/`. An update is an ordinary merge, and the README has its commands. What to know before you run them:

- `git log --oneline HEAD..core/main`, after `git fetch core`, shows what is new.
- On a conflict, keep your side in `company.json` and in the `knowledge/` pages you filled in, and in `.claude/settings.json` the hooks and deny rules of both sides, but no allow rule you took out. For those two files, do it in a maintenance session of your own ([`CLAUDE.md`](../CLAUDE.md), "Operating modes"), not through the CEO.
- Read the diff of `.claude/settings.json`, `company.json`, `scripts/hooks/`, `CLAUDE.md` and `knowledge/board/` (`git diff main core-update -- .claude/settings.json company.json scripts/hooks CLAUDE.md knowledge/board`) before you merge the branch into `main`: those are the guardrails, and what is on by default.
- If the update was published as one squashed commit, git still merges it normally, because your copy started from the core's history.

Or give the CEO a directive to do it ("Update us to the latest core"): it fetches, and the platform engineer makes the merge in its worktree, with tests and a review. When the update changes `.claude/settings.json` or `company.json`, no agent may make it: the CEO shows you what comes in for that file, and you run the README's steps yourself. Afterwards tell the CEO you did, or its next system check reverts the commits as changes nobody landed.

## Layout

| Path | What |
|---|---|
| [`CLAUDE.md`](../CLAUDE.md) | The constitution. Every agent loads it |
| `company.json` | The company's own settings: name, the Board's email, time zone, products, integrations. Scripts and hooks read it through `scripts/company_config.py`. A guardrail file: no subagent writes it, and a hook asks you before the CEO's session does |
| [`knowledge/`](../knowledge/INDEX.md) | The knowledge base: board, company, products, engineering, marketing, sales, research. Conventions in [`knowledge/README.md`](../knowledge/README.md); templates in `knowledge/_templates/` |
| `.claude/agents/` | `executive/` (ceo, analyst, critic, platform-engineer), `engineering/` (cto, staff-engineer, design-reviewer, senior-engineer, code-reviewer, ux-expert), `marketing/` (cmo, content-producer, content-reviewer, performance-analyst, trend-researcher, reel-analyst) |
| `.claude/skills/` | The company: onboard-company, directive, report, kb-check, system-check, sales-playbook. Engineering: onboard-codebase, ux-checklist. Marketing: the rest |
| `.claude/settings.json` | Permission rules (no force-push, no admin merges) and the hooks |
| `scripts/` | The linter, the hooks in `hooks/`, the scans and reports, `second_opinion.py`, the Board desk, and their tests |
| `tools/` | Rendering and measuring tools for marketing and UX |
| `docs/` | This guide, [optional integrations](optional-integrations.md), [guards](guards.md), [the Board desk](board-desk.md), [marketing](marketing.md), [native Windows](windows.md) |
| `workspaces/` | Your product repos, cloned on demand, and local state (gitignored) |

## Make it yours

- **Decision rights and standing authorizations** are defaults. Change them in `CLAUDE.md` and [`knowledge/board/standing-authorizations.md`](../knowledge/board/standing-authorizations.md).
- **Who may start whom** is `MAY_SPAWN` in `scripts/hooks/guard_agent_spawn.py`. Don't use `Agent(a, b)` lists in agent definitions: one on a main-session agent binds every subagent too.
- **Your way of working** goes into [`board-preferences.md`](../knowledge/company/board-preferences.md): tell the CEO, in your words, and it records them.

## License

MIT. See [LICENSE](../LICENSE).
