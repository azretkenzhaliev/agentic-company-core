---
title: How engineering works
owner: cto
status: active
updated: 2026-11-25
related: [standards/README.md, ../board/standing-authorizations.md, ../../CLAUDE.md]
---

# How engineering works

The CTO owns this folder and this process. Every engineering agent follows it. The message formats (ORDER, REPORT, VERDICT) are in [`CLAUDE.md`](../../CLAUDE.md). `<repo root>` in a command is the main checkout's absolute path.

**These rules are defaults.** A stricter choice the Board recorded (a standing authorization, the charter, [board-preferences.md](../company/board-preferences.md), or a runbook on its word) wins over this page, the standards and the engineering agents' files.

**Contents:** What to read; Folder map; 1. Intake and sizing; 2. Design; 3. Design-review loop; 4. Implement-review loop; 5. Landing and deploy; 6. Reports; Git and workspaces.

## What to read

**Read sections, not whole files.** Everything you read stays in your context and slows every later turn. Your row below is about 15k tokens at most (4 bytes a token).

- **Find it, then read that part.** `grep -rn '<id or phrase>' knowledge/`, then `grep -n '^##' <file>`, then read that section with an offset and a limit. Never re-read a section you have.
- **Archives aren't required reading,** even inside a folder you were told to read: `*-archive.md`, `archive-*.md` and `*-history.md` are only searched, by date, order or id. Their text is moved verbatim, so a fact isn't lost by being there.
- **Question files:** an order with a `Question file:` line: at each task boundary read only its new lines, `sed -n '<N+1>,$p' <Question file>` (N the last line you read), and the CEO's broadcasts, `grep -n '^CEO' workspaces/<product>/content/ceo-questions.md`. An order without that line reads the product's `ceo-questions.md`: `grep -n -E '^## ORDER|^(\*\*)?CEO|^RULING|NEEDS-CEO-NOW' <file> | cut -c1-160` (order headings, lines starting `CEO` or `**CEO`, `RULING` lines, `NEEDS-CEO-NOW`), then those of your order in full by line number.

| Role | Always | When the task needs it |
|---|---|---|
| Senior | Its ORDER; `definition-of-done` "A task (Senior)"; the digest's groups "Tests", "Landings, CI and deploys" and "Stops, refusals and the machine" (a refusal is final, b9); the runbook's "Find your section", "Task suite". Your Core (in your agent file) carries `coding` 1-11, `testing` 1-7, 9, 13, 15, 17, 18, 20 and 23, and `security` 1-8: open a rule for its case; the rule binds | The design's task section; the architecture section it names; a `testing` rule whose title the task meets (8 a repo with no tests, 10 a platform check or spike, 11 a check against another parser, 12 mutation checks, 14 timing tests, 16 a rule on parsed shape, 17 hostile input, 19 a test selection); `security` rule 9 for a production statement; "Test (the full suite)" for its test table, run lock and long runs only; to land, `staff-engineer.md` §5 and the runbook's CI and landing sections |
| Code reviewer | Its packet; standards `testing`, `security`; the digest; the runbook's "Find your section", "Task suite". Your Core carries `review-checklist` "Code review" and `definition-of-done` "A task": open a point for its case; it binds | The design lines in the packet |
| Design reviewer | The design; the digest; the runbook's "Find your section". Your Core carries `review-checklist` "Design review" and `security` 1-9: open a point for its case; it binds | The architecture, deploy or rollback section the design touches |
| Staff | Its ORDER and workstream section; of this page, "What to read", §3's "How the loops run", §6 and "Git and workspaces"; standards `coding`, `testing`, `security`, `review-checklist` "Design review", `definition-of-done` "A task (Senior)"; the digest; the runbook's "Find your section". Your Core carries `cto.md`'s "Thin managers", Working rules and "Board steps and questions", and `definition-of-done` "A workstream": open them for a case; they bind | By step, each binding when you're in it: **the design** §2, §3's opening, "Design sign-off" and "Second opinions", §1's "When the ux-expert is called" for a design that changes UI, and the architecture sections it needs; **its tasks** §4 and `review-checklist` "Code review" for the task specs; **a landing** §5, and for a deploy the runbook's "Deploy to production". The rest of this page (Folder map, §1) for a case |
| CTO | The ORDER; of this page, "What to read", "Folder map", §1, §3's "How the loops run", §6 and "Git and workspaces"; `standards/README.md`; the runbook's "Find your section"; the contents of the product and architecture pages. Your Core carries the lessons digest: open a row in `standards/lessons-learned.md` for its case; the row binds | Those pages' sections, and roadmap sections, as the order touches them. By step, each binding when you're in it: **an S task** §4; **M or L sign-off** §2, §3's opening and "Design sign-off"; **a review's second opinion** §3's "Second opinions"; **a landing or deploy** §5 and the digest's "Landings, CI and deploys" |

**Pages stay small.** A roadmap, runbook or questions file holds current state; history goes to its sibling archive, verbatim, with a link. Whoever closes an order or answers a line moves that text in the same step; nobody summarises it away. Links go one level deep: a page to its archive, not an archive to another. A page over about 100 lines has a contents list.

## Folder map

| Path | What | Writer |
|---|---|---|
| [standards/](standards/README.md) | Coding, testing, security, review checklists, definition of done, lessons learned | cto |
| [cores/](cores/README.md) | Each engineering role's core, loaded in its agent body as "## Core" (the platform engineer regenerates it through the gate) | cto |
| [architecture/](architecture/overview.md) | `overview.md`, plus `<product>.md` per product from `/onboard-codebase` | cto |
| [roadmaps/](roadmaps/README.md) | `RM-NNN-<slug>.md` for M- and L-size work | cto |
| [designs/](designs/README.md) | `DD-NNN-<slug>.md`, one per workstream | staff-engineer |
| [adr/](adr/README.md) | `ADR-NNN-<slug>.md` architecture decisions | cto |
| [runbooks/](runbooks/README.md) | `<product>.md`: build, test, deploy, smoke check, rollback | cto |
| [ux/](ux/README.md) | UX audits, specs, and the ux-expert's curriculum and sources | ux-expert |

## 1. Intake and sizing (CTO)

The CEO sends the CTO an ORDER. The CTO reads the order's context, the product page, the product's architecture page and its runbook, then sizes the work:

| Size | Meaning | Path |
|---|---|---|
| **S** | One contained change, about one task, in one repo. No data-model change, no new dependency on outside services | No roadmap or design doc. The CTO writes the task spec as the Senior's ORDER, runs step 4 directly with a Senior and the code reviewer, and puts the spec in its report |
| **M** | One workstream | CTO writes a short roadmap (`RM-NNN`) with one workstream. One Staff engineer writes the design; its tasks follow "Who runs a task" below |
| **L** | Several workstreams | CTO writes a roadmap with several workstreams. Staff engineers work in parallel **only** on workstreams the roadmap marks independent |

**Who runs a task.** A task from an approved design, and any S task, is CTO to Senior plus reviewer, with no Staff. Add a Staff only when there's no approved design, the work spans workstreams or about 3 or more Senior tasks, it touches an item on the one-way list (b1–b9), or a review failed (a blocker or major still open after its re-check). One CTO per order; several may run at once, and in a product with several, one of them, the duty CTO, owns what they share (`cto.md`, "Parallel work"). Seniors merge their own work and report one line, so the CTO doesn't become a queue.

**When the ux-expert is called** (`.claude/agents/engineering/ux-expert.md`): a Staff engineer has it check a design that changes UI, before the design review; whoever starts a UI task's code review (the CTO or the Staff) starts it too, for acceptance in a local browser; a new page gets its UX spec before it is built, and a page that has no full UX/UI spec or audit gets one when it is touched: the touch starts the full audit alongside, and a fix doesn't wait for it; other audits on the CEO's or the CTO's order. Every Senior on a UI task meets the `ux-checklist` skill's component acceptance checklist.

Escalate to the CEO before starting if the work needs new paid infrastructure, a data-model change that risks user data, or a cross-product rewrite.

**Roadmap contents** (`roadmaps/RM-NNN-<slug>.md`, from the template): goals, non-goals, milestones, workstreams (`WS-1`, …) each with checkable acceptance criteria and a branch name, dependencies and sequencing, risks.

Two rules for roadmaps:
- If a roadmap drops something users or the Board would notice, say so with a recommendation, not under non-goals: under "Decisions for the Board" if it drops something the Board asked for or is another one-way door (`CLAUDE.md`, "The Board's attention"), otherwise as a decision for the CEO, which goes in its next report's "Decided".
- Facts about access and capabilities (databases, accounts, connected tools) come from the Board or a check, not from a product repo's own docs.

## 2. Design (Staff)

The Staff engineer reads the roadmap workstream and **the actual code** in `workspaces/<product>/`, then writes `designs/DD-NNN-<slug>.md`: context with real file paths, the proposed design, data and API changes, migration, testing strategy, rollout and rollback, security and privacy, a task list (`T-1`, …) with acceptance criteria, and a review log.

## 3. Design-review loop (Staff ↔ design reviewer)

1. Staff spawns the design reviewer with the design doc path, the roadmap path and the repo path.
2. The reviewer checks the design against the codebase (do these modules, functions and integration points really exist and work as described?), the roadmap's acceptance criteria, the standards, security, migrations and rollback. It returns a VERDICT.
3. On CHANGES_REQUESTED, Staff revises the doc and appends the round to the review log.
4. **One round.** On CHANGES_REQUESTED, Staff fixes every blocker and major and logs each fix against its finding; minors and nits go in the report, not into a fix. There is no second design round: a blocker or major Staff can't fix, or disputes, goes to the CTO with both positions.
   - **The CTO rules, with no further round,** when the reviewer named the fix for every finding, the CTO has read the changed text, every change narrows a rule or fails closed, and no roadmap criterion moves. The ruling goes in the review log as a "CTO ruling" row, and the design moves to sign-off (`awaiting-ceo` or `awaiting-board`). The CTO's report tells the Board which designs passed this way.
   - **Otherwise** (a disputed finding, a change of scope, or a fix the CTO can't check from the text), the CTO decides the dispute or takes it to the CEO.
5. **Keep designs short enough to converge.** An M design is a "short design doc" (section 1). Long designs don't converge: each round finds new problems in new text. Put the detail a Senior needs into task specs, not the design; the reviewer checks the contracts, data, safety and criteria.

### Design sign-off (M and L)

Designs that touch the one-way list (sign-in, customer data, look, money) wait for the Board ([charter](../board/charter.md), "Design sign-off"). The rest start after design review and the CEO's check; the Board sees a 3-line gist afterwards and can stop it. Only the Board waives sign-off, in its own words in the directive, and a waiver doesn't cover a one-way door it didn't name.

1. **Door and the Board's words.** Staff fills in the doc's **Door** (one-way with its number, b1–b9 in `CLAUDE.md`'s "The Board's attention", or two-way) and **"The Board's words this design relies on"** while writing it. The design reviewer checks both: a wrong door is a major finding.
2. When the design reviewer has APPROVED, Staff fills in the doc's **"Gist for the Board"** section. At most 10 plain-language lines, the first three standing alone:
   - what users will notice;
   - what gets built;
   - data or API changes;
   - risks;
   - cost (paid services, heavy usage);
   - any decision the Board must make.
3. Staff sets the design status to `awaiting-ceo` (two-way) or `awaiting-board` (one-way) and stops. It reports PARTIAL ("design approved by review; awaiting sign-off") with the door and the gist in the report.
4. The CTO passes the gists up, batching parallel workstreams.
   - **Two-way:** the CEO checks the gist against `knowledge/company/board-preferences.md` and the Board's quoted words, approves it, and reports its first three lines to the Board afterwards; the Board may stop it. No critic: design review already had SA-003 second opinions, where a key is set. If the CEO thinks it's one-way, it is.
   - **One-way:** the critic, then the Board. The CEO records the answer in the directive file.
5. **Approved:** the CEO's next order says so. The CTO starts the Staff engineer again, which logs "CEO: APPROVED <date> (two-way)" or "Board: APPROVED <date>" in the review log and moves on to section 4. **Changes requested** (by the CEO, or by the Board, also after a two-way design has started): Staff revises, one design-review round runs on the revision, and the gist goes back the same way.
6. **Calibration.** The review log keeps the CEO's or the Board's verdict next to the reviewer's. When either rejects or changes a design the reviewer approved, the CTO adds a row to `standards/lessons-learned.md` and tightens the review checklist where it can. The disagreement rate shows how much the reviewer can be trusted.

### Second opinions from other model families (SA-003)

**In force once the founder sets a provider's key and names it in `company.json`** ([SA-003](../board/standing-authorizations.md)); without both, a review is single-family, says so, and waits for nothing. Reviews also get a second opinion from another model family through `scripts/second_opinion.py`, because models tend to favour their own output. The script picks the family by `--kind`:
- **Code and design reviews** (`--kind code` or `design`; the ux-expert's checks use `design`): OpenAI GPT alone. **The critic's checks** (`--kind plan`): GPT and Google Gemini.
- **What's sent:** only a packet the script builds: the brief, the given files and diff, and our review checklist (a code packet leaves out its design section). Secrets files are skipped and a packet with a secret pattern is refused. Customers' data never goes into one.
- **Models, reasoning effort and service tier** are the script's defaults or its environment variables (`SECOND_OPINION_*`, its docstring). The output names the model used.
- **How it counts:** a blocker or major from the second opinion counts, unless the Claude reviewer refutes it with `file:line` evidence.
- **Problems** print as OFF, NOT SENT or UNAVAILABLE and never fail a review. With no key for the kind, the review is single-family and says so.
- **Spend** is counted from the script's call logs, every product's (`workspaces/*/content/sa003-calls.jsonl`), against the budget of the directive the review serves (SA-003, Spending). One call per review, the plain form, never `--only gemini`; a re-check makes no call. **A change that lands in production is never reviewed by Claude alone while the keys are set.** An exhausted provider is a Board question, raised at once.

### How the loops run

Both loops are agent conversations with hard caps: one design round; one code round, with a short re-check of each blocker and major fix (section 4). A review takes about 20 minutes at most. They move into saved Claude Code workflows, so code drives the loop and agents only draft and judge, after three directives have run cleanly through the current prompts.

**Persist as you go.** A usage limit can end any agent mid-loop, and whatever is only in its context is lost.
- The design doc is saved before its first review.
- A design verdict goes into the review log as soon as it arrives, before any revision starts. A round in progress says so in its Resolution cell. A code verdict is in the reviewer's findings file.
- The doc's header always shows the loop's state (`in review`, `awaiting-board`, `CTO ruling pending`), overwritten.
- **No per-step rows.** A design's implementation log gets one row per landing, and a roadmap one row per workstream change. `ceo-questions.md` holds only questions with their rulings, `NEEDS-CEO-NOW` lines and one RESUME POINT. In an order's own question file nothing moves: its RESUME POINT is edited in place, no cq_archive runs on it, and the CEO closes the file when the order is CLOSED (ceo.md, "Close an order's question file"). In the product's `ceo-questions.md`: **whoever writes a RESUME POINT also moves its order's handled lines** (answered questions, REPORT lines it has acted on, and rulings and coordination lines older than that RESUME POINT, except a ruling that still binds), word for word, to `ceo-questions-archive.md` beside it, under the same heading: first append the lines to the archive by its absolute path with one `>>` heredoc of the whole block, in order, then remove them from the file by Edits, from a CEO line's last line up, or the CEO line with its numbered or indented lines in one Edit; a relative path, a `cd` or a `>` is refused (the hook's own words: `ARCHIVE_MESSAGE`, `scripts/hooks/cq_write.py`). Never by rewriting the file. The tool does this move: after writing the RESUME POINT, run `python3 <repo root>/scripts/cq_archive.py <repo root>/workspaces/<product>/content/ceo-questions.md --order <order id>` (`--dry-run` first; the absolute path, from any dir: the hook refuses the relative form from a cwd with its own copy, such as a repo worktree); it moves handled lines, superseded RESUME POINTs and REPORT lines that a later line marks `ACTED: /<n>.<task>, …` (a RESUME POINT can carry the mark), word for word, and never CEO lines, open `NEEDS-CEO-NOW` lines or PAUSE lines. A RESUME POINT stays under about 1.5 KB; its detail goes to the design's header or the order's notes file.
- The CTO keeps `designs/README.md` and the roadmap's workstream statuses current as reports arrive, not only at the end.
- **After a stop, recover before redoing.** The stopped agents' transcripts survive on disk (`~/.claude/projects/<project>/<session>/subagents/agent-*.jsonl`, with a `.meta.json` naming each agent's type and task). Before restaffing, the CTO checks that every old agent ended, then reads them for finished reports that didn't reach a log and for answered SA-003 calls. Recovered material goes outside git (`workspaces/<product>/content/recovered-<order>/`), the Staff order names it, and a review of an unchanged range reuses the paid answers instead of paying again.

**An unattended run never waits on a person.** Background agents can't answer a permission prompt, and one that waits stalls the whole order silently, for hours if nobody is watching.
- A refused action is final for the whole order: nobody retries it or tries a variant. It goes under Open questions with the exact command, for the Board.
- **Two exceptions:** a merge of `origin/main` refused in any other form is retried once in the exact form of `staff-engineer.md` §5 step 4; a push refused while chained with other commands is retried once as the plain push alone, `git -C <full worktree path> push origin <branch>`. A refusal of either retry is final. (The third named retry, the form a block message spells out: `cto.md`, "A permission refusal is final".)
- After a refusal, run only commands of the shapes already used in the order, and keep going on the rest of the work.

**Parallel work (hard rule; in `cto.md`, "Parallel work").**
- **Every independent task runs now, without being told;** only real conflicts serialize work. Before each spawn the CTO checks that the new task is in a different workstream from every task in flight; that no two in-flight tasks edit the same files or shared contracts (APIs, schemas, types other code depends on); that at most one in-flight task adds a database migration; and that a task needing another's result waits until that result is on `main`.
- **How many Staff engineers:** one per independent workstream with work ready, with no fixed number and no usage throttle; the limit is the machine: `python3 scripts/capacity_scan.py --mac` must print `room: yes`. It prints `room: no` only for under 15 GB of disk free; macOS memory pressure critical, under 5% of memory free, or either reading unreadable; or a 5-minute load of 2.5 or more per CPU (the script's defaults, which the Board may change; anywhere but macOS the memory isn't checked; disk and load hold the same). It holds each spawn, new local test container and full-suite or whole-tree run (exit 1 = hold), as `cto.md`, "The load hold", says: re-check every 5 minutes, a `HOLD` line past 30 minutes, running work finishes and is never killed for load, and production fixes, deploys under `.landing-lock` and reads aren't held. Load holds work only through this check. Fewer Staff if the order says so. A Staff engineer that has stopped, or waits for the Board, isn't running.
- **A waiting PR doesn't hold its lane:** a lane whose PR waits on main's CI, a review or a Board step starts its next independent task. Nobody stops or pauses for usage: a RESUME POINT after each step, and work runs until the account stops it.
- **One production deploy at a time,** under the lock (`.landing-lock`). A landing on `main` takes no lock and doesn't queue (§5).
- **Never idle a place waiting for the CEO:** questions go to the order's question file (or the product's `ceo-questions.md`), Board steps to the product's `board-steps.md`, and the work goes on.
- **Board steps, relays and stops** ([standards/board-steps.md](standards/board-steps.md)): before adding a Board step, check its §1 (can an agent do it; minutes; one batch per landing; read-backs as log codes). Rulings reach running agents, and agents reach the CEO, through the channels in its §3, never through the Board.

**Token economy (in the agent files).**
- Fixes go to a Senior with the blockers and majors verbatim; minors and nits go in the report, not into a fix (`staff-engineer.md` §4).
- Reviewers work from a compact packet: the diff, the design lines and the acceptance criteria; they open other files only to check a specific doubt (`code-reviewer.md`, `design-reviewer.md`).
- Short output, foreground waits under 3 minutes (the bounded wait on an exit-code file), no hand-back while a child agent runs, no report files, S11, disk rules, refusals: `cto.md`, "Working rules", which bind every engineering agent.
- **A task spec that changes when rows of a shared table are released, settled or deleted lists every writer of those rows** (file and line) and what each one expects of them, and the Senior checks the change against each before building.
- **Task specs and ORDERs never ask a subagent for a file named `report*.md`, `summary*.md`, `findings*.md` or `analysis*.md`:** Claude Code refuses such a Write in any folder. Reports are the SubagentHandback message; reviewers' findings files are `content/reviews/<DD id>-<task id>-r1.md`.
- **Models** (SA-002): the agent files' frontmatter. A task touching sign-in, tenancy, what the product does to customers' data, migrations or code that runs on customers' machines gets its code reviewer with the Agent tool's `model: opus` override.

**Pace:**
- **A Staff spawn owns one design, or the tasks of one landing (about 4 at most) through the merge.** A landing is never left for a fresh Staff. If work remains, it stops with its implementation log and its design's header current, and reports PARTIAL "continue from the log". The CTO then starts a fresh Staff engineer on the same workstream, worktree and test container, with the workstream's order and the log as its starting state. (A long-running agent fills its context, which makes it slower and loses more at a stop.)

**Check before staffing.** Before a design wave or an S task, the CTO checks that the Agent tool offers the agent types it needs (`staff-engineer`, `senior-engineer`, `code-reviewer`). If it doesn't, the CTO reports BLOCKED with the exact error. It never works around the restriction, for example by starting `claude -p --agent …` from Bash.

## 4. Implement-review loop (Senior ↔ code reviewer), per task

Tasks within one workstream run **one at a time**, in the design's order.

1. The CTO (or a Staff, where one is needed) spawns a Senior with the task spec: design doc path and task id, worktree path, branch, and the task-suite commands from the runbook.
2. The Senior implements on the workstream branch, writes tests, runs the task suite, and commits.
3. Its manager spawns the code reviewer with the commit range, the design doc, the roadmap, the task id and the task-suite commands.
4. **One round for every task, about 20 minutes at most** (in `staff-engineer.md` §4). The quality aim: good enough passes; anything broken, or any bug, doesn't.
   - The author fixes every blocker and major in new commits. **Each such fix gets a short re-check of its fix diff by the same reviewer,** not a new round: no second opinions, no new minors.
   - **Minors and nits go in the report, not into a fix.**
   - **No mutant runs, no repeat runs, no size or timing measurements and no run in a CI image,** unless the design or the task spec asks. A test that looks flaky may be repeated, only that test.
   - **A blocker or major still open after the re-check goes to the CTO** with both positions. The CTO rules (a "CTO ruling" row in the log); there is never a further round. A new blocker or major that the re-check finds in the fix diff counts as still open, and goes to the CTO the same way. The CTO may rule one more fix plus re-check.
5. The design's implementation log gets one row per landing.

**Tests: what the change touches, never a full suite on the founder's machine.**
- The Senior and the code reviewer run the **task suite**: the suites the task's diff can affect, chosen by the runbook's "Task suite" table, with the exact commands and results in their messages.
- The Senior landing a task runs typecheck, lint, the task suite and the essential tier after merging `origin/main` (§5). The **essential tier** is a small always-on set, which the CTO names in each runbook.
- **Seniors write:** one test per flow; no mock-only tests; tests of removed features deleted; a flaky test fixed or deleted within 30 minutes (`senior-engineer.md`).
- **One tree, one full run.** No full suite runs before a production deploy or on a schedule (SA-001 condition 2). A production deploy runs the affected tests, the essential tier and the PR's CI checks (§5). Apart from the essential tier and the zero-test check, nothing runs twice on one tree: a suite already green on the same code doesn't run again.

## 5. Landing and deploy (SA-001)

**The Senior that finished the task merges it,** on its manager's word that the review passed, and reports one line. No fresh Staff, no wait-only agent and no lock. Where the repo has a merge queue, the tests run once, in the queue, on the merge result. Where a runbook, roadmap or standard still says otherwise about a landing on `main`, a review or a test run, sections 3 to 5 here win until the CTO changes it, unless it is a stricter choice the Board recorded. The production gates and the runbook's deploy steps stay. Steps: `staff-engineer.md` §5.

**A landing on `main`** (where `main` doesn't deploy production). All of these, in order:

1. every task has an APPROVED verdict, or every blocker and major fixed and re-checked. The manager's word to land names that reviewed head. Any commit after it, other than a clean merge of `origin/main`, gets a re-check of that diff before the merge, with no second opinions. Scanner config stays a CTO order;
2. on the machine that lands it: current `origin/main` merged into the branch; typecheck, lint, the task suite and the essential tier green. **Test selection that returns zero tests for a code change fails this gate.** Only what already ran green on this exact tree is skipped; the essential tier and the zero-test check always run;
3. a PR, with `gh` (`gh pr create` as one plain command: `--repo` and `--head`, no `cd`, never chained, text in `--body` or a `--body-file` inside the task's worktree; a refused PR stops and goes up to your manager; open PRs only as the order says, with no `--reviewer` or `--assignee`), not a draft, and the required checks the runbook names (its scanners, at least) green on it, within the runbook's time, otherwise BLOCKED. Nothing else is waited for. A draft already open is marked ready by the manager, after the review;
4. `runbooks/<product>.md` exists and has `status: active`. A draft runbook means **no autonomous deploy**: stop after the PR and report "ready to merge and deploy; blocked on runbook";
5. `gh pr merge`, as the runbook says. **The merge command runs alone,** with nothing chained before or after it; checks are separate commands. **If GitHub refuses it because `main` moved,** go back to 2. **If the permission system refuses the merge,** the landing stops there: report PARTIAL with the exact command and PR, and the CEO takes it to the Board. Nobody retries it or tries another route to the default branch.

The landing ends at the merge. **A red staging run is fixed forward,** in a new task, with no rollback.

**A production deploy** (SA-001), by the CTO or a Staff, never a Senior: one at a time, under the lock (`.landing-lock`), which stays for this alone. Where a push to `main` is the deploy, every landing is one. All of these, in order:

1. every task in the change has a code-review verdict of APPROVED (a re-check ends in a verdict);
2. **the affected and essential tests are green, and so are the PR's CI checks if the repo has CI** (SA-001: no full suite before a deploy or on a schedule; a full run is a manual `workflow_dispatch`). Anything a landing's log row says this deploy must show is read first. This run blocks that deploy, not the landings. **On red, on a deploy from a tree already on `main`, revert the last merge in the deploy's head `X` first** (`git revert -m 1 <merge>`, landed like any task), then find the cause. Where the landing is the deploy, nothing has reached `main`: don't push it; fix the branch;
3. `runbooks/<product>.md` exists and has `status: active`. A draft runbook means **no autonomous deploy**;
4. deploy exactly as the runbook says. **The merge command runs alone,** with nothing chained before or after it; checks are separate commands. **If the permission system refuses the merge,** the deploy stops there: keep the lock with the reason, report PARTIAL with the exact command and PR, and the CEO takes it to the Board. Nobody retries it or tries another route to the default branch;
5. run the runbook's smoke check;
6. **if the deploy or the smoke check fails, roll back immediately per the runbook,** then report.

Every production deploy, including a rollback, goes into the report, which the CEO passes to the Board.

**When these rules tighten.** They hold while a break costs little. They tighten at the first of these (for a product that meets one when it is onboarded, at once):
- the first paying customer;
- a second customer's data;
- any change to what the product does to live customers (b3);
- two selection misses in a month: a break that a test would have caught, in a test the selection didn't run. Each one gets a row in [lessons learned](standards/lessons-learned.md), which is how they're counted.

The CTO writes a `NEEDS-CEO-NOW` line as soon as one happens. The CEO sets the tighter gates.

**First deploy of each product:** there's no active runbook until `/onboard-codebase` has drafted it, its steps are verified, and the Board has confirmed how deploys work. Until then, nothing deploys autonomously.

## 6. Reports

Senior → Staff → CTO → CEO, each in REPORT format. Reports cite branches, PR links, commit ranges, deploy ids and KB paths. The CEO updates the directive file and reports to the Board.

## Git and workspaces

- Product repos: `workspaces/<product>/<repo>/`, cloned by `/onboard-codebase`. The `workspaces/` folder is gitignored in the company repo.
- **One git worktree per workstream:** `git -C workspaces/<product>/<repo> worktree add ../.worktrees/<RM-id>-<WS-id> -b ws/<RM-id>-<WS-id>-<slug> origin/<default-branch>`. S-size work uses worktree `../.worktrees/<directive-id>` and branch `task/<directive-id>-<slug>`. Parallel workstreams never share a working tree.
- Remove the worktree after the PR merges: `git -C workspaces/<product>/<repo> worktree remove ../.worktrees/<id>`.
- Commit messages cite ids, e.g. `RM-NNN WS-1 T-2: add the export button`.
- **Never force-push. Never rewrite history on shared branches.** Fix review findings with new commits.
- Respect each product repo's `CLAUDE.md`, README, linters and formatters. If they conflict with our standards, the repo's rules win inside that repo.
- In the company repo, only the main session commits. Engineering subagents write KB files and list them in their reports.
