---
title: Standing authorizations
owner: board
status: active
updated: 2026-11-25
related: [charter.md, ../engineering/README.md]
---

# Standing authorizations

A standing authorization (SA) pre-approves a class of actions, so agents can take them without asking the Board each time. Only the Board grants, changes or revokes one. Agents quote the SA id when they rely on it.

**In force by default:** SA-001, SA-002, SA-003, SA-004 and SA-008. They ship with the system; the Board narrows or ends each in `/onboard-company`, which reads them out (but SA-002, a limit), or at any time. One that needs a key or an account does nothing until the founder sets it. **Templates:** SA-005, SA-006 and SA-007 rest on facts only the founder has (accounts, keys, caps, ids, customers' consent), and each stays off until the Board grants it in its own words. A key, an account or an entry in `company.json` is never a grant, and is never recorded as the Board's words. What the Board says is added as a dated `Granted`, `Amended` or `Ended` line in its own words, never by rewriting what it said; until there is one, nothing here is the Board's words.

## SA-001: autonomous production deploys

- **In force by default;** the Board narrows or ends it in `/onboard-company` or at any time.
- **Allows:** agents may deploy any product to production without asking the Board.
- **Conditions.** Every gate must pass, in order:
  1. every task in the change has a code-review verdict of APPROVED;
  2. the affected and essential tests are green, and so are the PR's CI checks, if the repo has CI; no full test suite runs on a schedule or before a deploy. The Board may choose the full suite before a deploy instead (slower; it catches a break outside the tests chosen), product by product, in its words here;
  3. the product has a deploy and rollback runbook at `knowledge/engineering/runbooks/<product>.md` with `status: active`;
  4. the deploy follows the runbook, and the runbook's smoke check passes afterwards;
  5. if anything fails after deploy, the agent rolls back immediately per the runbook.
- **Reporting:** every production deploy, successful or rolled back, is reported to the Board afterwards in the CEO's report.
- **Doesn't cover:** anything else the charter reserves. For example, a deploy that needs a new paid service, or that changes legal terms or public statements, still needs the Board.
- **If the Board ends it:** the CEO asks the Board before each production deploy.

## SA-002: subscription first

- **In force by default;** the Board narrows or ends it at any time.
- **Allows:** agents run on the Board's Claude subscription: interactive sessions, or `claude -p` without `--bare`.
- **Requires Board approval:** any pay-per-token API key path (Agent SDK, Managed Agents, `claude --bare`), and any new paid service. SA-003 approves one such path: reviews by other model families.
- **Usage discipline** (the defaults in the agents' frontmatter; a smaller plan lowers them, `docs/guide.md` "Plan sizes"): Opus for design review, the critic, the platform engineer, the CEO, the CTO, Staff engineers, the CMO, the content reviewer, the UX expert, the analyst and reviews of sensitive code; Sonnet for everything else. Every agent thinks at `xhigh`. The effort-scaling rules in `CLAUDE.md`, and no large fan-outs.

## SA-003: reviews by other model families

- **In force by default once the founder sets a provider's key and `company.json` names that provider** (`"second_opinion": {"providers": ["openai", "google"]}` under `"integrations"`, with only the providers it wants; `"google"` is Google Gemini, key `GEMINI_API_KEY`; `/onboard-company` proposes the entry as the default when a key is given; no key or no entry, no call); the Board narrows or ends it in `/onboard-company` or at any time.
- **Allows:** agents send review packets (code, diffs, design docs, KB pages) to the Google Gemini and OpenAI APIs to get second opinions on designs and code (`scripts/second_opinion.py`); the `critic` also sends the CEO's analyses, plans and design gists. Models tend to favour their own output, so a second family catches what Claude misses. Code and design reviews go to OpenAI alone, the critic's checks to both.
- **Training:** the providers may train on what they receive. Whether they do depends on each account's settings (OpenAI's organisation data sharing; whether the Gemini key's project is on the paid tier), and no agent checks them. The stricter choice: set each account so it doesn't train, or don't set its key.
- **Doesn't allow:** customer data, secrets, or any other provider.
- **Default models** (edit the `choose_*` functions in the script to change them). The script confirms each model is on the key's model list; it never guesses IDs. When one provider fails, the other is the only second opinion; with none, reviews are single-family and say so.
- **Keys:** the Board sets `GEMINI_API_KEY` and `OPENAI_API_KEY` in its environment. Agents never see or print the values.
- **Spending:** review costs count against the budget of the directive the review serves; every call is logged. Outside a budgeted directive, the limit is the money in each provider's account, until the Board sets a monthly cap here.
- **Kept anyway:** the script screens credential values out of every packet. Reviews never need them.

## SA-004: a second-language check of marketing copy

- **In force by default once marketing is on and the founder sets the language and the key** (`docs/marketing.md`; no key, no call); the Board narrows or ends it in `/onboard-company` or at any time.
- **Allows:** marketing agents send post copy in the second language (captions, on-screen text, scripts) to Google's Gemini API for a language check (`scripts/language_check.py`) before the Board reads it.
- **Doesn't allow:** sending anything but post copy (no customer data, no product material); publishing anything. The Board still reads the copy in every weekly packet.

## SA-005: AI images, b-roll and voice-over for marketing (template)

- **Granted:** not granted.
- **Allows:** the content producer generates and edits text-free images and short b-roll with Gemini image and video models (on-image text is rendered in code), and, only if the Board names it, voice-over with a text-to-speech service in its stock voices, on separate API keys with a spending cap the Board sets.
- **Doesn't allow:** any cloned, professional or "famous" voice: a clone of the founder's own voice needs its own grant. Nothing generates until the Board has created and topped up the key, and set the cap.
- **Conditions:** whether a post carries the platform's AI label is the Board's choice on each post, off unless ticked.
- **Asked with it:** the models, the keys and the cap.

## SA-006: agents' access to production accounts and data (template)

- **Granted:** not granted.
- **Allows:** agents use the connectors and command-line tools the Board names (a hosting provider, a database, a cloud account), signed in as the Board names, on the products it names, with the access it names (reading customer data is named on its own, or isn't allowed).
- **Not part of it:** `gh`, signed in by the founder at install. Opening, updating and merging the products' reviewed pull requests with it is on by default (`docs/guards.md`).
- **Ready for it, by default:** the permission rules in `.claude/settings.json` and the database guard's settings (`docs/guards.md`). None of them connects an account: the Board does, and names it here. Until it has, agents don't use a connected account.
- **Unchanged:** production changes go only through the runbooks; the hooks stay (`docs/guards.md`), and so does the deny list: no deletes of database projects or branches, no force-push; customer data never goes to an outside party (b2).

## SA-007: the merge queue's numbers (template)

- **Granted:** not granted.
- **Allows:** for a product repo with a GitHub merge queue, the CTO (or the Staff or Senior it names) changes the numbers of the `merge_queue` rule in the ruleset the Board names, without asking: `check_response_timeout_minutes`, `max_entries_to_build`, `max_entries_to_merge`, `min_entries_to_merge` and `min_entries_to_merge_wait_minutes`, each read back after the change and reported to the CEO with its undo (the old value).
- **Unchanged** (still the Board's, b9): the required status checks, bypass actors, enforcement, the ruleset's other rules, the queue's grouping strategy and merge method, and every other ruleset or branch protection.
- **If the permission system refuses an agent's ruleset write,** the refusal is final: the change comes to the Board as a step.

## SA-008: agents read and manage the company's own secrets

- **In force by default;** the Board narrows or ends it in `/onboard-company` or at any time.
- **Allows:** agents read and manage the company's own `.env` files, keys and passwords when a task needs them.
- **Doesn't allow:** customers' credentials; printing a value; a secret in git, the KB, a report, a log, a test, a second-opinion packet or any outside service other than the one the key belongs to.
- **If the Board ends it:** agents read none. Deny rules for the files it names can go into `.claude/settings.json` (only the main session edits that file, on the founder's own message).
