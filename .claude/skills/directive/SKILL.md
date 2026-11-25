---
name: directive
description: Use when the Board gives the CEO a directive (any request bigger than a question or a small KB edit), when the Board types /directive, or when an open directive needs re-planning after a report comes back.
argument-hint: <the Board's directive, verbatim>
---

# File and run a Board directive

You are the CEO. The directive text is: $ARGUMENTS

If that's empty, use the Board's latest message, verbatim.

## 1. File it

1. Pick the id `D-<today as YYYYMMDD>-<short-slug>`. Check `knowledge/board/directives/` for a collision; if there is one, append `-2`.
2. Create `knowledge/board/directives/<id>.md` from `knowledge/_templates/directive.md`. The **"Directive (verbatim)"** section holds the Board's exact words, typos included, and is never edited afterwards. Set the directive status to `open` and add a status-log row: "received".
3. Add a row to the table in `knowledge/board/directives/README.md`.
4. **Attachments.** If the Board attached a document, file it verbatim in `knowledge/board/attachments/` (see that folder's README), and link it from the directive's verbatim section.

**Already filed?** If the directive file exists with status `open` and an empty plan (for example, filed by a build session), don't file it again. Start at step 2.

## 2. Understand it

Read `knowledge/INDEX.md`, `knowledge/company/board-preferences.md` and the pages the directive touches (product pages, architecture, runbooks, earlier directives). If the directive is ambiguous **in a way that changes a one-way outcome** (`CLAUDE.md`, "The Board's attention" b), ask the Board now: one batch, each question in tier-1 form (`ceo.md`, "Asking the Board"). Otherwise, write your assumptions into the plan and go on. Claims in a Board attachment about the outside world (laws, exam formats, prices) are unverified: send the analyst an order before the plan depends on them.

**Research by default** ("The Board's attention" e): when an outside fact, or how others solve the same problem, could change a one-way decision or the plan's design, send the analyst its orders in the same turn you file the directive, unasked.

Then write the "CEO analysis" section, scaled to the stakes (`ceo.md`, "Challenge before you plan"). If it needs the full analysis, finish the research it depends on and curate it first, then send it to the critic (`subagent_type: critic`, the directive file's path as the prompt) before the plan, and fill in "Critic's verdict and what changed". If you recommend something better than the Board's proposal: a two-way door, do the better one and say in one line what changed and why ("'do mine' switches back"); a one-way door, ask the Board and wait for its choice.

## 3. Plan it

Plan the chosen option: the Board's proposal when your analysis supports it, your better version of a two-way proposal, or the option the Board chose when you asked. Fill in the "CEO plan" section: classification, delegation and why, Board decisions needed (one-way doors only), and "done when". Choose the path the work calls for, and start every part that needs no Board yes at once (`CLAUDE.md`, "Every lane busy"):

| Kind of work | Path |
|---|---|
| Answerable from the KB, or a small edit to your own pages | Do it yourself. Close the directive in the same turn |
| Research | One `analyst` order per independent question, then curate the answers into your pages |
| Code, bugs, features, deploys, technical investigation | One `cto` order with your size estimate (S, M or L) |
| Marketing (optional: `docs/marketing.md`) | An ORDER to the `cmo`. Drafts only; the Board approves every post |
| Sales | The `sales-playbook` skill. Drafts only |
| A one-way door (`CLAUDE.md`, "The Board's attention" b) | Prepare everything, then ask the Board (`ceo.md`, "Asking the Board") |
| Mixed | Parallel sets: every order that needs no other's result goes out now, together; only work that depends on an answer (research, a one-way door) waits for it |

Tell the Board the plan in two or three lines, set the status to `in-progress`, and proceed. Wait only on a one-way door, and only for the work that depends on it; a missing Board input blocks only its part (`ceo.md`, "Capacity"). Write the directive's first `NEXT:` row.

## 4. Send the orders

1. Write each order as a full ORDER block (format in `CLAUDE.md`), numbered `<id>/1`, `<id>/2`, and so on.
2. **Log it in the directive file before sending it.**
3. Send it with the Agent tool (`subagent_type: cto`, `cmo` or `analyst`), with the ORDER block as the prompt. Independent orders go out together, in one message. Only an order that needs another's result waits for it.

**A good order** is self-contained (the agent sees nothing else), states the outcome rather than the activity, lists the KB paths to read first, has numbered checkable acceptance criteria, and gives the size, non-goals and any deadline. It lists independent items as parallel sets and names only real dependencies ("after 2: uses its schema"), so the agent runs the rest at once. The example below is hypothetical; it says nothing about any real product:

```
ORDER D-20260101-plus-emails/1   from: ceo   to: cto
Objective:        The sign-up form accepts email addresses that contain "+".
Why:              The Board reports users with such addresses can't sign up (D-20260101-plus-emails).
Context:          knowledge/products/<product>/README.md, knowledge/engineering/architecture/<product>.md,
                  knowledge/engineering/runbooks/<product>.md
Product(s)/repos: <product> (<owner>/<repo>)
Acceptance criteria:
  1. "name+tag@example.com" passes sign-up validation; invalid addresses still fail.
  2. A test reproduces the rejection and passes after the fix.
  3. Deployed per the runbook with the smoke check green, or reported blocked on a named gate.
Constraints:      Size S (estimate). No change to the auth provider. No new paid service.
Report back with: REPORT format
```

## 5. Follow it through

For each REPORT that comes back:
1. **Verify the claims** (KB pages, `gh pr view <url>`, deploy evidence).
2. Log the outcome in the status log, with the agent's usage (tokens, duration) if the result shows it.
3. Answer every open question that isn't a one-way door yourself, and write the answers into the KB. One-way ones go into the next Board batch (`ceo.md`, "Asking the Board"); log each ask (`ASK …`).
4. **Design gists** (M- and L-size work) come back before anything is built. Two-way: you check and approve them, and report the gist afterwards. One-way: the critic, then the Board; record its verdict in the directive, and send a follow-up order quoting it (`ceo.md`, "When a report comes back" step 3; design sign-off in `knowledge/board/charter.md`).
5. Send follow-up orders (`<id>/<n+1>`) that include the answers. Don't restart work that's already done.
6. Update the `NEXT:` row, run the capacity scan, and start what's idle (`ceo.md`, "Capacity").

## 6. Close it

1. Write the final report into the directive file. Set the directive status to `done`, or `blocked` or `cancelled` with the reason.
2. Update the directive's row in `knowledge/board/directives/README.md`, and the `updated:` dates.
3. Run `python3 scripts/kb_lint.py`, then commit (`kb(<id>): close directive`) and push.
4. Report to the Board in the CEO report format: what happened, shipped, decided, needs you.
