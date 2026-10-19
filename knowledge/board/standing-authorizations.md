---
title: Standing authorizations
owner: board
status: draft
updated: 2026-10-19
related: [charter.md, ../engineering/README.md]
---

# Standing authorizations

A standing authorization (SA) pre-approves a class of actions, so agents can take them without asking the Board each time. Only the Board grants, changes or revokes one. Agents quote the SA id when they rely on it.

These three are the defaults this setup ships with. The CEO confirms each one with the Board during `/onboard-company` and records the Board's words and the date under it. TODO(board): confirm, change or revoke SA-001, SA-002 and SA-003.

## SA-001: autonomous production deploys

- **Allows:** agents may deploy any product to production without asking the Board.
- **Conditions.** Every gate must pass, in order:
  1. every task in the change has a code-review verdict of APPROVED;
  2. the full test suite is green, and so are the PR's CI checks, if the repo has CI;
  3. the product has a deploy and rollback runbook at `knowledge/engineering/runbooks/<product>.md` with `status: active`;
  4. the deploy follows the runbook, and the runbook's smoke check passes afterwards;
  5. if anything fails after deploy, the agent rolls back immediately per the runbook.
- **Reporting:** every production deploy, successful or rolled back, is reported to the Board afterwards in the CEO's report.
- **Doesn't cover:** anything else the charter reserves. For example, a deploy that needs a new paid service, or that changes legal terms or public statements, still needs the Board.

## SA-002: subscription first

- **Allows:** agents run on the Board's Claude subscription: interactive sessions, or `claude -p` without `--bare`.
- **Requires Board approval:** any pay-per-token API key path (Agent SDK, Managed Agents, `claude --bare`), and any new paid service. SA-003 approves one such path: reviews by other model families.
- **Usage discipline:** Sonnet for implementation and research, Opus for judgment roles, the effort-scaling rules in `CLAUDE.md`, and no large fan-outs.

## SA-003: reviews by other model families (optional)

- **Allows:** when the Board has set the keys, agents send review packets (code, diffs, design docs, KB pages) to the Google Gemini, OpenAI and DeepSeek APIs to get second opinions on designs and code (`scripts/second_opinion.py`). Models tend to favour their own output, so a second family catches what Claude misses. The Board accepts that the providers may use this material for training.
- **Default models** (edit the `choose_*` functions in the script to change them):
  - Google slot: Gemini 4 Argon when the key lists it, otherwise `gemini-3.8-flash` with thinking level high. When Gemini is off or fails (e.g. quota exhausted), `deepseek-flash` takes the slot;
  - OpenAI slot: `gpt-6.1-sol`.

  The script confirms each model is on the key's model list; it never guesses IDs.
- **Keys:** the Board sets `GEMINI_API_KEY`, `OPENAI_API_KEY` and `DEEPSEEK_API_KEY` in its environment. Agents never see or print the values. Without keys, reviews are single-family and say so.
- **Spending:** review costs count against the budget of the directive the review serves; every call is logged to `workspaces/second-opinions/calls.jsonl`. TODO(board): a monthly cap for reviews outside a budgeted directive.
- **Kept anyway:** the script screens credential values out of every packet. Reviews never need them.
