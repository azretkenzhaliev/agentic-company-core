# The guards

The hooks in `scripts/hooks/` check what agents do before it happens. `.claude/settings.json` says which hook runs on which tool, and denies some commands and reads outright. `scripts/tests/test_settings.py` checks that file: run it after every change to it.

**They stop mistakes. They aren't a sandbox.** They read the text of a command or a tool call; they can't see everything a program does. What must never happen is held by the service itself: a branch ruleset, a database role without the right, a token without the scope, a spending cap. Set those too.

## How they behave

- **Whom they hold.** Claude Code names the caller: `agent_type` is the role, a subagent's or the main session's (here `ceo`, as `.claude/settings.json` starts every session, or the one `claude --agent <role>` names); `agent_id` is there only for a subagent. Some limits hold every caller, some only subagents, one role or any role.
- **Off means refuse, not open.** A limit on every caller (email, posting, Telegram, Notion, the database, background runs, question files, the Board's answers) is on whatever `company.json` says. A tool that isn't set up there (no `board_email`, no `neon`) refuses what would leave the company or write a database. Only a role's own limits cost nothing to a company without that role.
- **They fail closed.** An input a guard can't read, an error in it or a `company.json` it can't parse is a refusal, with the reason. Each guard's entry in `.claude/settings.json` also has `"onFailure": "block"`, so a hook that crashes, can't start or times out refuses the call. That needs Claude Code 2.1.295 or later; an older version doesn't know the key, so a hook that can't start lets the call through there. Check with `claude --version`. One exception: `guard_full_suite.py` holds the machine's load, not data, so an input it can't read lets the call go, and so does an error of its own once it has read its settings (it logs that one in the product's folder, `.suite-guard-errors.log`).
- **A refusal is final** for the agent it stops: no variant, no other tool, no other agent. It reports the exact command to its manager. Where the message names the one form that is allowed, it may run the command once in exactly that form.
- **Loosening one is the founder's decision.** A hook, its settings entry and `company.json` are guardrails. No subagent writes `company.json`; when the main session writes it, Claude Code asks you first.
- **Where they run.** macOS and Linux, with Python 3.10 or later as `python3`, and bash or zsh as the agents' shell; nothing else to install. On Windows, use WSL 2: [windows.md](windows.md). The battery check in `guard_full_suite.py` and the Board desk's launchd check in `capacity_heartbeat.py` are macOS only and do nothing elsewhere.

## The hooks

| Hook | Runs on | Holds | Stops | Settings in `company.json` |
|---|---|---|---|---|
| `guard_kb_write.py` | Write, Edit, MultiEdit, NotebookEdit; Bash for `company.json` alone | everyone; role limits for the analyst, the ux-expert and marketing | a secret in `knowledge/`; one agent writing in another's worktree; a role writing outside its own pages; any agent writing the Board's approvals, answers or desk state, or the founder's raw inbox; a subagent writing `company.json` (the main session is asked), or overwriting a question file | none |
| `cq_write.py` (called by `guard_kb_write.py` and `guard_marketing_tools.py`) | Write, Edit, Bash | subagents | anything but an Edit, an append or `cq_archive.py` on a `ceo-questions.md` (several agents write it at once), removing a folder that holds one, and a line that passes for the CEO's | `question_files` |
| `guard_agent_spawn.py` | Agent | the roles in its `MAY_SPAWN` and `HELD_CALLERS` | a spawn the org chart doesn't allow; a spawn of a role that runs tests or builds while this machine's 5-minute load is 2.5 per CPU or more, until `python3 scripts/capacity_scan.py --mac` prints `room: yes` (a production fix says so in its prompt and is logged) | none |
| `guard_agent_control.py` | SendMessage, TaskStop | agents | a message to anyone but the agent's own children or launcher; stopping an agent outside its own tree | none |
| `guard_critic_bash.py` | Bash | the critic, the content-reviewer | everything but reads and their two checks | none |
| `background_bash.py` (called by `guard_marketing_tools.py`) | Bash | subagents | `run_in_background`: the agent's report is lost while it runs | none |
| `bounded_wait.py` (the same) | Bash | engineering agents | a wait loop with no time bound | none |
| `guard_merge_queue.py` (the same) | Bash | everyone | taking a pull request out of a GitHub merge queue, cancelling a workflow run | none |
| `board_email.py` (the same) | Gmail's `send_message` | everyone | every email but the CEO main session's plain one to `board_email`; all of them while that is empty; any other Gmail write is `guard_marketing_tools.py`'s | `board_email`, `email` |
| `neon_branch.py` (the same) | Neon's `update_branch` | everyone | all but the CTO's or a Staff engineer's expiry on a `backup-` or `gate-` branch, and never on a default branch | `neon` |
| `guard_neon_sql.py` | Neon's `run_sql`, `run_sql_transaction` | everyone | every call until `neon` is there; then a dropped database, schema or role, role and password changes, the protected tables, and a bulk change (`DELETE` or `UPDATE` without `WHERE`, `TRUNCATE`, a dropped table or column) with no backup branch from the last 60 minutes. Each statement is logged to `workspaces/neon-sql-audit.log` | `neon` |
| `guard_vercel_cli.py` | Bash | agents | deploys, `redeploy`, `link` and `promote` with the Vercel CLI, `rollback`, alias writes and `rolling-release` with no `--scope` or a Git-only team's (all of them until `vercel` is there), and calls that could show production's environment values (every environment's until `vercel` is there) | `vercel` |
| `guard_full_suite.py` | Bash | everyone, for one product | full test suites on this machine, and heavy runs without a slot; **off until configured** | `full_suite` |
| `guard_marketing_tools.py` | every MCP tool, and Bash | everyone; role limits for marketing | sending, posting and writing through the connectors (Gmail, Metricool, Notion, Telegram, FastDL, Neon's `update_branch`), and the marketing roles' other tools; it calls the modules above | its docstring |
| `board_desk_bash.py`, `fastdl.py`, `trend_reader.py`, `marketing_bash.py` (called by it) | Bash, MCP | agents; the marketing roles | writes to the Board's answers and the desk's state; FastDL's and the browser's tools beyond reads; the marketing roles' Bash | their docstrings |
| `approve_git_reads.py`, `approve_worktree_merge.py`, `approve_pr_ready.py` | Bash | – | nothing: each approves one exact form (a plain git read; one merge of `origin/main` and one push of the agent's own branch in a product worktree; marking a reviewed pull request ready), so the agent isn't stopped by a permission prompt it can't answer. The merge, the push and the pull request hold for the products in `products` | `auto_approve`, `products` |
| `capacity_heartbeat.py` | the CEO's Stop event, from `ceo.md` | the CEO | a turn that ends while work is idle, once; it blocks no tool | none |

Each hook's docstring has the exact rule, and its tests are in `scripts/tests/test_<hook>.py`. Run them all with `python3 -m unittest discover -s scripts/tests`.

The approve hooks and the Notion sync after a read (`scripts/notion_approvals_sync.py`) aren't guards: when one fails, the normal permission rules decide, so their entries have no `onFailure`.

## Settings

All of them are in `company.json`, which starts with none: no address, no product, no entry under `integrations`. Below, `acme` and the `full_suite` and `question_files` values are examples; the other values are the defaults. `neon` and `vercel` need an entry (`{}` is enough); `auto_approve` and `email` need none.

```json
{
  "board_email": "",
  "products": {"acme": {"repo": "example-co/acme-app", "workspace": "workspaces/acme/acme-app"}},
  "integrations": {
    "auto_approve": {"merge": true, "push": true, "pr_ready": true},
    "email": {"per_day": null},
    "neon": {
      "protected_tables": [],
      "bulk_after_backup": true,
      "production_projects": [],
      "default_branches": []
    },
    "vercel": {"promote_scopes": [], "git_only_scopes": []},
    "full_suite": {"product": "acme", "database_env": "ACME_TEST_DATABASE_URL", "database_name": "acme_test", "container_prefix": "acme-pg", "workflow": "ci"},
    "question_files": {"deploy_script": "deploy.ts"}
  }
}
```

- **`board_email`**: the only address the CEO may email. Empty: it emails nobody.
- **`auto_approve`**: what runs without a prompt, for the products in **`products`**: `merge` in the worktrees beside a product's `workspace`, `push` and `pr_ready` for its `repo`. `merge`: any session merges `origin/main` into a product worktree. `push`: a Senior, a Staff engineer or the CTO pushes that worktree's own task or workstream branch. `pr_ready`: a Staff engineer or the CTO marks a pull request ready. All are on; `false` turns one off, and then the normal rules ask, or refuse an agent that can't ask.
- **`email.per_day`**: the CEO's emails to you a UTC day. No cap unless you set a whole number.
- **`neon`**: without the entry, every `run_sql` call is refused; `{}` gives the defaults above.
  - `protected_tables`: bare names, no schema (a `public.users` entry matches only that text). No statement may name one. It adds to `account`, `session` and `verification`, which common sign-in libraries use: name your tables of credentials, sessions and personal data.
  - `bulk_after_backup`: on. A `DELETE` or `UPDATE` without `WHERE`, `TRUNCATE`, `DROP TABLE` or `DROP COLUMN` on a production project passes only within 60 minutes of a backup branch made in the same session. `false` refuses them, and every other `DROP`, backup or not. Roles, passwords, protected tables and whole-database drops are refused either way.
  - `production_projects`: the projects that backup rule holds. Empty: all of them.
  - `default_branches`: the `br-…` id of each project's default branch. Without it, no agent sets an expiry on a branch.
- **`vercel`**: `promote_scopes` are the teams whose runbook rolls back with Instant Rollback and then promotes; `git_only_scopes` are those whose production and aliases change only through Git. Without the entry, `rollback`, alias writes and `rolling-release` are refused; with it, they need a `--scope` that isn't in `git_only_scopes`, and go to the permission check. With the entry there, agents read non-production environment values; `value_scopes` limits that to the teams it lists (`[]`: none). Production's stay out of reach.
- **`full_suite`**: turn it on when one product's full suite keeps the machine busy. Only named test files then run locally, and a full run is CI's own, started by hand (engineering README, section 5); its runbook (`knowledge/engineering/runbooks/<product>.md`) needs the sections "Machine load: a heavy run takes a slot" and "Essential tier". Don't set it for a product whose full suite the Board chose before a deploy (SA-001, condition 2): this guard refuses that run on this machine.
- **`question_files.deploy_script`**: the one product deploy script, by file name, that a subagent may run with `--ceo-questions <path>`.

## On by default, and how to tighten it

The defaults let agents work without stopping to ask. Each of these is on from the start, or from the day you set its tool up; tighten any of them in the file named, by your own hand or by telling the CEO, which makes the edit once you confirm.

| On | From | Tighten it |
|---|---|---|
| Tests, linters, and plain git and GitHub reads run without a prompt | the start | take their rules out of `permissions.allow` |
| Merges, pushes and ready pull requests in your products run without a prompt | a product in `products` | `company.json`, `auto_approve`: `"merge": false`, `"push": false`, `"pr_ready": false` |
| Agents read and write your databases, bulk changes only after a backup branch | `neon` in `company.json` | `"bulk_after_backup": false`; name more `protected_tables`; or take `mcp__claude_ai_Neon__run_sql` and `…run_sql_transaction` out of `permissions.allow`, so each statement asks |
| Neon's reads and new branches run without a prompt | the Neon connector | take its other rules out of `permissions.allow` |
| Agents read non-production environment values with the Vercel CLI | `vercel` in `company.json`, and SA-006 granted | `"value_scopes": ["<team>"]`, or `[]` for none |
| With a `--scope`, the Vercel CLI's `rollback`, alias writes and `rolling-release` go to the permission check | `vercel` in `company.json` | list the team in `git_only_scopes`: they are then refused there |
| The Vercel CLI's writes of environment variables go to the permission check | the start | add `permissions.deny` rules, such as `Bash(vercel env add *)` |
| The CEO emails you, with no daily cap | `board_email` | `"email": {"per_day": 6}` |
| `gh pr create` and `gh pr merge` run without a prompt (`--admin` and `--auto` are denied) | the start | take the rule out of `permissions.allow`; a branch ruleset is what holds a merge |
| Review packets go to the second-opinion providers you name | a provider's entry in `company.json` (its form: `scripts/second_opinion.py`) and its key; a key alone starts nothing | leave the entry out; or don't set the key; or take `Bash(python3 scripts/second_opinion.py *)` out of `permissions.allow` |
| GPT answers at OpenAI's slower, cheaper `flex` tier | OpenAI's entry and key | take `SECOND_OPINION_OPENAI_TIER` out of `env` for the standard tier |
| Agents read the company's own `.env` files and keys when a task needs them, and never print or send a value (`CLAUDE.md`, "Secrets") | the start | add `permissions.deny` rules: `Read(.env)`, `Read(.env.*)`, `Read(*.pem)`, `Read(*.key)`, `Read(~/.ssh/**)` |
| Up to 30 subagents run at once; no heavy one starts at a load of 2.5 per CPU or more | the start | lower `CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS` in `env`; lower `LOAD_PER_CPU` in `guard_agent_spawn.py` and `scripts/capacity_scan.py`, together |

`permissions` and `env` are in `.claude/settings.json`. Taking an allow rule out, or adding a deny rule, keeps the settings test green; a new allow rule goes into its list too.

A tool with no rule goes to Claude Code's own permission check: it asks you, or refuses an agent that can't ask. Neon's other writes are such tools; deleting a project, branch, database, endpoint, role or snapshot, the snapshot schedule, a reset and a restore are denied. To deny more, add for example `mcp__claude_ai_Neon__get_connection_string`, `mcp__claude_ai_Neon__reset_postgres_role_password` or `mcp__claude_ai_Neon__create_credential`.

Connect the Neon connector under the name the rules use (`claude.ai Neon` gives `mcp__claude_ai_Neon__…`): the allow and deny rules and the branch rule hold that name, while the SQL guard holds any connector with "neon" in its name.

## Left out

A guard for an agent that reads the founder's mailbox isn't part of this repo: it would bind to one mailbox and one person's rules. Give an agent a mailbox only with a guard of your own.
