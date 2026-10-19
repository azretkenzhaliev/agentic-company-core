---
title: Board charter
owner: board
status: active
updated: 2026-10-19
related: [standing-authorizations.md, directives/README.md, ../../CLAUDE.md]
---

# Board charter

The founder acts as the **Board of Directors**. The Board sets the company's direction and holds power over the CEO's decisions.

## Reserved powers

Only the Board decides:

1. Mission and vision.
2. Starting or killing products.
3. Spending real money, and any new paid service or subscription.
4. Legal commitments and contracts.
5. Public statements in the founder's name.
6. Sending anything outside the company: emails, posts, messages, outreach, ads.
7. Hiring humans.
8. Granting, changing or revoking standing authorizations.

Everything else is delegated: to the CEO first, and through the CEO to the departments, per the decision rights in [`../../CLAUDE.md`](../../CLAUDE.md). The Board can overrule any decision at any time.

Standing authorizations pre-approve whole classes of actions so they don't need a Board decision each time. They're listed in [standing-authorizations.md](standing-authorizations.md).

## How the Board works with the company

- **The Board talks only to the CEO,** in a session started with `claude --agent ceo`. The CEO turns what the Board says into orders for the departments.
- **Directives.** Anything the Board asks for is a directive. The CEO files it as `directives/D-YYYYMMDD-<slug>.md` with the Board's words verbatim, then adds the plan, the orders, a status log and the final report. Questions and small asks are handled directly and may skip the file. The CEO decides, following the effort-scaling rules.
- **Design sign-off** (a default; the Board may drop it). Before any M- or L-size engineering work is built, the CEO shows the Board a short gist of each design doc, and agents start building only after the Board approves it. A directive may waive this. S-size work has no design doc: the CEO states the plan when filing the directive.
- **Questions to the Board** come only from the CEO, batched where possible. Facts the company doesn't know are written in the KB as `TODO(board): …` until the Board answers.
- **Reports.** The CEO reports when a directive finishes, when it's blocked on the Board, and after every production deploy (SA-001). `/report` gives a status across all directives at any time.
- **Reviewing the company's memory.** Every KB change is a git commit in this repo, so the Board can review them in `git log` or in pull requests.
