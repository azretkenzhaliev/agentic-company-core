# agentic-company

A startup run by Claude Code agents. You, the founder, are the **Board of Directors**: you set direction and talk only to a **CEO** agent. The CEO turns what you ask for into orders for an **analyst** (research) and an **engineering department**: a CTO who plans the work, Staff engineers who design and land one workstream each, Senior engineers who implement one task each, and independent design and code reviewers. A markdown **knowledge base** in git is the company's shared memory.

Everything is plain Claude Code: agent definitions, skills, hooks and permission rules. No extra framework, and it runs on your Claude subscription.

```
Board (you)
└── ceo                      also acting CMO, CSO and CPO
    ├── analyst              research; writes raw, sourced notes
    └── cto                  architecture, roadmaps, standards, runbooks
        └── staff-engineer   one workstream: design → reviews → tasks → landing
            ├── design-reviewer   read-only, checks designs against the real code
            ├── senior-engineer   implements one task, with tests
            └── code-reviewer     read-only, checks each diff
```

## What makes it work

- **A constitution** ([`CLAUDE.md`](CLAUDE.md)) every agent loads: who decides what, the chain of command, message formats (ORDER, REPORT, VERDICT), and safety rules. Nothing leaves the company (emails, posts, purchases, sign-ups) without the Board.
- **Directives.** Anything you ask for is filed as `knowledge/board/directives/D-YYYYMMDD-<slug>.md`, with your words verbatim, the CEO's plan, every order sent, a status log and the final report.
- **Effort scaling.** Questions are answered directly; a small change goes CTO → Senior with a code review; a workstream gets a short design doc that you approve as a gist before anything is built; bigger work gets a roadmap with parallel workstreams.
- **Bounded review loops.** At most three rounds of design review and three of code review, the third a closing round, then escalation with both positions.
- **Gated deploys.** Autonomous production deploys only through a verified runbook, behind every gate, with an immediate rollback when a smoke check fails ([SA-001](knowledge/board/standing-authorizations.md)).
- **Persistence through stops.** Verdicts and state go into the knowledge base as they happen, so a usage limit or an outage costs minutes, not the work.
- **Hooks** that hold the line: who may spawn whom (`guard_agent_spawn.py`), no secrets in the knowledge base (`guard_kb_write.py`), and pre-approved plain git reads so background agents don't stall on prompts (`approve_git_reads.py`).
- **Lessons learned** from running this on real products, in [`knowledge/engineering/standards/lessons-learned.md`](knowledge/engineering/standards/lessons-learned.md).

## Set up

| Need | Why | Check |
|---|---|---|
| [Claude Code](https://docs.claude.com/en/docs/claude-code), logged in with your Claude subscription | Every agent runs on it ([SA-002](knowledge/board/standing-authorizations.md)). The engineering prompts assume a large plan; on a smaller one, lower the parallelism in `knowledge/engineering/README.md` ("Pace") | `claude --version` |
| GitHub CLI, logged in with access to your product repos | Cloning, PRs, CI status | `gh auth status` |
| Python 3.10+ | The knowledge-base linter, the hooks and the review script use only the standard library | `python3 --version` |
| poppler (optional) | Lets agents read PDFs | `pdftotext -v` |

Then verify:

```bash
python3 -m unittest discover -s scripts/tests   # expect OK
python3 scripts/kb_lint.py                      # expect 0 errors
```

**Always start Claude in this folder.** Claude Code loads the company's settings, hooks, agents and skills only from the folder a session starts in.

## First steps

1. `claude --agent ceo`, then `/onboard-company`. The CEO interviews you for about 30 minutes: the company, each product, how deploys work today, which accounts agents may use, and how you want reports. It writes your answers into `knowledge/company/` and `knowledge/products/`, and confirms the three default standing authorizations with you.
2. In a plain `claude` session, add each product to the table in [`CLAUDE.md`](CLAUDE.md) (the CEO gives you the rows).
3. In the CEO session, run `/onboard-codebase <product-id>` for each product. It runs as the CTO: it clones the repo into `workspaces/` (gitignored) and writes the product's architecture page and a draft deploy runbook. The runbook becomes `active`, and deploys autonomous, only after its steps are verified and you've confirmed how deploys work.
4. Give the CEO your first directive. It proposes one in its onboarding report.

## Use it

```bash
claude --agent ceo     # operate the company: talk to the CEO
claude                 # maintain the system itself: agents, skills, hooks, knowledge-base tooling
claude --agent cto     # escape hatch: talk to the CTO directly
```

In a CEO session: `/directive <what you want>`, `/report`, `/kb-check`, `/onboard-company`.

## Layout

| Path | What |
|---|---|
| [`CLAUDE.md`](CLAUDE.md) | The constitution |
| [`knowledge/`](knowledge/INDEX.md) | The knowledge base: board, company, products, engineering, marketing, sales, research. Conventions in [`knowledge/README.md`](knowledge/README.md); templates in `knowledge/_templates/` |
| `.claude/agents/` | `executive/` (ceo, analyst) and `engineering/` (cto, staff-engineer, design-reviewer, senior-engineer, code-reviewer) |
| `.claude/skills/` | onboard-company, onboard-codebase, directive, report, kb-check, marketing-playbook, sales-playbook |
| `.claude/settings.json` | Permission rules (no force-push, no reading secrets, no admin merges) and the hooks |
| `scripts/` | `kb_lint.py`, the hooks in `hooks/`, `second_opinion.py`, and their tests |
| `docs/` | [Optional integrations](docs/optional-integrations.md) and the [design rationale](docs/research/agentic-company-architecture.md) |
| `workspaces/` | Your product repos, cloned on demand (gitignored) |

## Optional integrations

[`docs/optional-integrations.md`](docs/optional-integrations.md) explains how to switch on:
- second opinions on every review from Gemini, GPT and DeepSeek (API keys required, pay-per-token);
- Claude in Chrome for the CEO;
- the Neon (Postgres) connector for engineering agents, with a SQL guard;
- a guard that stops agents from deploying with the Vercel CLI.

## Make it yours

- **Decision rights and standing authorizations** are defaults. Change them in `CLAUDE.md` and [`knowledge/board/standing-authorizations.md`](knowledge/board/standing-authorizations.md).
- **Models per role** are in each agent's front matter and in the [org chart](knowledge/company/org-chart.md).
- **Who may spawn whom** is `MAY_SPAWN` in `scripts/hooks/guard_agent_spawn.py`. Don't use `Agent(a, b)` lists in agent definitions: one on a main-session agent binds every subagent too.
- **Keep your copy private** once it holds your company's facts: the knowledge base records internal decisions and, in time, unfixed security findings about your products.

## License

MIT. See [LICENSE](LICENSE).
