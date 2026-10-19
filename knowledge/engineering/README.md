---
title: How engineering works
owner: cto
status: active
updated: 2026-10-19
related: [standards/README.md, ../board/standing-authorizations.md, ../../CLAUDE.md]
---

# How engineering works

The CTO owns this folder and this process. Every engineering agent follows it. The message formats (ORDER, REPORT, VERDICT) are in [`CLAUDE.md`](../../CLAUDE.md).

## Folder map

| Path | What | Writer |
|---|---|---|
| [standards/](standards/README.md) | Coding, testing, security, review checklists, definition of done, lessons learned | cto |
| [architecture/](architecture/overview.md) | `overview.md`, plus `<product>.md` per product from `/onboard-codebase` | cto |
| [roadmaps/](roadmaps/README.md) | `RM-NNN-<slug>.md` for M- and L-size work | cto |
| [designs/](designs/README.md) | `DD-NNN-<slug>.md`, one per workstream | staff-engineer |
| [adr/](adr/README.md) | `ADR-NNN-<slug>.md` architecture decisions | cto |
| [runbooks/](runbooks/README.md) | `<product>.md`: build, test, deploy, smoke check, rollback | cto |

## 1. Intake and sizing (CTO)

The CEO sends the CTO an ORDER. The CTO reads the order's context, the product page, the product's architecture page and its runbook, then sizes the work:

| Size | Meaning | Path |
|---|---|---|
| **S** | One contained change, about one task, in one repo. No data-model change, no new dependency on outside services | No roadmap or design doc. The CTO writes the task spec as the Senior's ORDER, runs step 4 directly with a Senior and the code reviewer, and puts the spec in its report |
| **M** | One workstream | CTO writes a short roadmap (`RM-NNN`) with one workstream, then assigns one Staff engineer |
| **L** | Several workstreams | CTO writes a roadmap with several workstreams. Staff engineers work in parallel **only** on workstreams the roadmap marks independent |

Escalate to the CEO before starting if the work needs new paid infrastructure, a data-model change that risks user data, or a cross-product rewrite.

**Roadmap contents** (`roadmaps/RM-NNN-<slug>.md`, from the template): goals, non-goals, milestones, workstreams (`WS-1`, …) each with checkable acceptance criteria and a branch name, dependencies and sequencing, risks.

Two rules for roadmaps ([lessons learned](standards/lessons-learned.md)):
- If a roadmap drops something users or the Board would notice, that cut goes under "Decisions for the Board" with a recommendation, not under non-goals.
- Facts about access and capabilities (databases, accounts, connected tools) come from the Board or a check, not from a product repo's own docs.

## 2. Design (Staff)

The Staff engineer reads the roadmap workstream and **the actual code** in `workspaces/<product>/`, then writes `designs/DD-NNN-<slug>.md`: context with real file paths, the proposed design, data and API changes, migration, testing strategy, rollout and rollback, security and privacy, a task list (`T-1`, …) with acceptance criteria, and a review log.

## 3. Design-review loop (Staff ↔ design reviewer)

1. Staff spawns the design reviewer with the design doc path, the roadmap path and the repo path.
2. The reviewer checks the design against the codebase (do these modules, functions and integration points really exist and work as described?), the roadmap's acceptance criteria, the standards, security, migrations and rollback. It returns a VERDICT.
3. On CHANGES_REQUESTED, Staff revises the doc and appends the round to the review log.
4. **At most 3 rounds.** If round 3 isn't APPROVED, Staff escalates to the CTO with the disagreement summarized. The CTO rules, or takes it to the CEO.
   - **Fixes after the cap.** Staff may apply the round-3 fixes it agrees with, marked "after round 3, not re-reviewed", and draft the gist; the design status says "review cap reached; CTO ruling pending".
   - **The CTO may accept them by ruling, with no fourth round,** when the reviewer named the fix for every finding, the CTO has read the changed text, every change narrows a rule or fails closed, and no roadmap criterion moves. The ruling goes in the review log as a "CTO ruling" row, and the design moves to `awaiting-board`. The CTO's report tells the Board which designs passed this way.
   - **Otherwise** (a disputed finding, a change of scope, or a fix the CTO can't check from the text), the CTO decides the dispute or takes it to the CEO.
5. **Keep designs short enough to converge.** An M design is a "short design doc" (section 1). Long designs don't converge: each round finds new problems in new text. Put the detail a Senior needs into task specs, not the design; the reviewer checks the contracts, data, safety and criteria.

### Board design sign-off (M and L)

The Board approves a gist of every design doc before anything is built ([charter](../board/charter.md)), unless the directive waives it.

1. When the design reviewer has APPROVED, Staff fills in the doc's **"Gist for the Board"** section. At most 10 plain-language lines:
   - what users will notice;
   - what gets built;
   - data or API changes;
   - risks;
   - cost (paid services, heavy usage);
   - any decision the Board must make.
2. Staff sets the design status to `awaiting-board` and stops. It reports PARTIAL ("design approved by review; awaiting Board sign-off") with the gist in the report.
3. The CTO passes the gists up, batching parallel workstreams. The CEO shows them to the Board and records the answer in the directive file.
4. **Approved:** the CEO's next order says so. The CTO starts the Staff engineer again, which logs "Board: APPROVED <date>" in the review log and moves on to section 4. **Changes requested:** Staff revises, the design-review loop runs again (the round count continues), and the gist goes back to the Board.
5. **Calibration.** The review log keeps the Board's verdict next to the reviewer's. When the Board rejects or changes a design the reviewer approved, the CTO adds a row to `standards/lessons-learned.md` and tightens the review checklist where it can. The disagreement rate shows how much the reviewer can be trusted.

### Second opinions from other model families (SA-003)

Both reviewers also get second opinions from Google Gemini and OpenAI GPT through `scripts/second_opinion.py`, with DeepSeek taking Gemini's place when Gemini is exhausted, because models tend to favour their own output.
- **What's sent:** only a packet the script builds: the brief, the given files and diff, and our review checklist. Credential values are screened out.
- **Models:** the defaults in [SA-003](../board/standing-authorizations.md): Gemini 4 Argon when available, otherwise Gemini 3.8 Flash on high thinking; `deepseek-flash` when Gemini is exhausted; `gpt-6.1-sol`. The output names the model used.
- **How it counts:** a blocker or major from either one counts, unless the Claude reviewer refutes it with `file:line` evidence.
- **Keys:** each provider runs when its key (`GEMINI_API_KEY`, `OPENAI_API_KEY`, `DEEPSEEK_API_KEY`) is set. Without keys, reviews are single-family and say so.
- **Spend** is counted from the script's call log (`workspaces/second-opinions/calls.jsonl`) against the SA-003 reserve. If the CTO narrows second opinions to save the reserve, the reason and the rule go into the roadmap and the next report. **A change that lands in production is never reviewed single-family while the keys are set** ([lessons learned](standards/lessons-learned.md)).

### How the loops run

Both loops are agent conversations with hard caps of 3 rounds. They move into saved Claude Code workflows, so code drives the loop and agents only draft and judge, after three directives have run cleanly through the current prompts.

**Persist as you go** ([lessons learned](standards/lessons-learned.md)). A usage limit can end any agent mid-loop, and whatever is only in its context is lost.
- The design doc is saved before its first review.
- Each verdict goes into the review log (design) or implementation log (code) as soon as it arrives, before any revision starts. A round in progress says so in its Resolution cell.
- The doc's header always shows the loop's state (`in review (round n)`, `awaiting-board`, `review cap reached; CTO ruling pending`).
- The CTO keeps `designs/README.md` and the roadmap's workstream statuses current as reports arrive, not only at the end.
- **After a stop, recover before redoing** ([lessons learned](standards/lessons-learned.md)). The stopped agents' transcripts survive on disk (`~/.claude/projects/<project>/<session>/subagents/agent-*.jsonl`, with a `.meta.json` naming each agent's type and task). Before restaffing, the CTO checks that every old agent ended, then reads them for finished reports that didn't reach a log and for answered SA-003 calls. Recovered material goes outside git (`workspaces/<product>/content/recovered-<order>/`), the Staff order names it, and a review of an unchanged range reuses the paid answers instead of paying again.

**An unattended run never waits on a person** ([lessons learned](standards/lessons-learned.md)). Background agents can't answer a permission prompt, and one that waits stalls the whole order silently, for hours if nobody is watching.
- A refused action is final for the whole order: nobody retries it or tries a variant. It goes under Open questions with the exact command, for the Board.
- After a refusal, run only commands of the shapes already used in the order, and keep going on the rest of the work.

**Pace** (defaults sized for a large Claude plan; the Board can lower them):
- **At most 5 Staff engineers at once,** on workstreams the roadmap marks independent, or fewer if the order says so. A Staff engineer that has stopped, or waits for the Board, isn't running.
- **A fresh Staff engineer per landing or about 4 tasks.** Each Staff spawn owns at most one landing or about 4 tasks, whichever comes first. It stops between tasks with its implementation log, its design's header and any landing lock current, and reports PARTIAL "continue from the log". The CTO then starts a fresh Staff engineer on the same workstream, worktree and test container, with the workstream's order and the log as its starting state. (A long-running Staff engineer fills its context, which makes it slower and costlier and loses more at a stop.)

**Check before staffing.** Before a design wave or an S task, the CTO checks that the Agent tool offers the agent types it needs (`staff-engineer`, `senior-engineer`, `code-reviewer`). If it doesn't, the CTO reports BLOCKED with the exact error. It never works around the restriction, for example by starting `claude -p --agent …` from Bash ([lessons learned](standards/lessons-learned.md)).

## 4. Implement-review loop (Senior ↔ code reviewer), per task

Tasks within one workstream run **one at a time**, in the design's order.

1. Staff (or the CTO, for S-size) spawns a Senior with the task spec: design doc path and task id, worktree path, branch, and the task-suite commands from the runbook.
2. The Senior implements on the workstream branch, writes tests, runs the task suite, and commits.
3. Staff spawns the code reviewer with the commit range, the design doc, the roadmap, the task id, the task-suite commands and **the round number**.
4. On CHANGES_REQUESTED, the Senior fixes the findings in new commits. **At most 3 rounds.**
   - **Round 3 closes the loop.** The reviewer checks that every earlier finding is fixed, raises only new blockers and majors, lists new minors and nits as follow-ups, and approves when no blocker or major remains.
   - Staff carries the follow-ups into the next task's spec, or into a short follow-up task before the landing, and says which in the implementation log. For S-size work the CTO carries them into a follow-up task before the deploy, or lists them in its report.
   - A blocker or major still open after round 3 goes to the CTO with both positions.
   - **An agreed fix after the cap** ([lessons learned](standards/lessons-learned.md)): when the reviewer named the fix for the open major and Staff agrees, Staff may carry it as the next task's first item (§0), reviewed in that task's loop, so an unattended run doesn't stall. The earlier task isn't marked APPROVED: the CTO rules, and it counts as APPROVED for the landing gate only once the next review confirms the fix. A disputed major isn't carried this way.
5. Staff records each round in the design doc's implementation log.

**Tests: the task suite while a task iterates, the full suite before every landing.**
- The Senior and the code reviewer run the **task suite**: the suites the task's diff can affect, chosen by the runbook's "Task suite" table, with the exact commands and results in their messages.
- The **full suite** (unit tests of every package on the branch, e2e, `tsc`, lint) runs before every landing, on the landing database (§5 gate 2). Staff also runs it once per spawn, on the workstream's container, before it reports, so a break in a suite the tasks didn't run shows up within about 4 tasks. Such a break is fixed as a follow-up task and reviewed like any other.

## 5. Merge and deploy (SA-001)

Staff (or the CTO, for S-size) opens **one PR per workstream** with `gh`, unless the product's runbook says otherwise. Then, **all** of these gates must pass, in order:

1. every task in the workstream has an APPROVED verdict;
2. the full test suite is green on the branch, and the PR's CI checks are green if the repo has CI;
3. `runbooks/<product>.md` exists and has `status: active`. A draft runbook means **no autonomous deploy**: merge if the runbook allows it, then report "ready to deploy, blocked on runbook";
4. merge the PR as the runbook says, then deploy exactly as the runbook says. **The merge command runs alone,** with nothing chained before or after it; checks are separate commands. **If the permission system refuses the merge,** the landing stops there: keep any landing lock with the reason, report PARTIAL with the exact command and PR, and the CEO takes it to the Board. Nobody retries it or tries another route to the default branch ([lessons learned](standards/lessons-learned.md));
5. run the runbook's smoke check;
6. **if the deploy or the smoke check fails, roll back immediately per the runbook,** then report.

Every production deploy, including a rollback, goes into the report, which the CEO passes to the Board.

**First deploy of each product:** there's no active runbook until `/onboard-codebase` has drafted it, its steps are verified, and the Board has confirmed how deploys work. Until then, nothing deploys autonomously.

## 6. Reports

Senior → Staff → CTO → CEO, each in REPORT format. Reports cite branches, PR links, commit ranges, deploy ids and KB paths. The CEO updates the directive file and reports to the Board.

## Git and workspaces

- Product repos: `workspaces/<product>/<repo>/`, cloned by `/onboard-codebase`. The `workspaces/` folder is gitignored in the company repo.
- **One git worktree per workstream:** `git -C workspaces/<product>/<repo> worktree add ../.worktrees/<RM-id>-<WS-id> -b ws/<RM-id>-<WS-id>-<slug> origin/<default-branch>`. S-size work uses worktree `../.worktrees/<directive-id>` and branch `task/<directive-id>-<slug>`. Parallel workstreams never share a working tree.
- Remove the worktree after the PR merges: `git -C workspaces/<product>/<repo> worktree remove ../.worktrees/<id>`.
- Commit messages cite ids, e.g. `RM-003 WS-1 T-2: add mock-exam timer`.
- **Never force-push. Never rewrite history on shared branches.** Fix review findings with new commits.
- Respect each product repo's `CLAUDE.md`, README, linters and formatters. If they conflict with our standards, the repo's rules win inside that repo.
- In the company repo, only the main session commits. Engineering subagents write KB files and list them in their reports.
