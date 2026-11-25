---
title: Lessons learned
owner: cto
status: active
updated: 2026-11-25
related: [README.md, ../README.md, testing.md]
---

# Lessons learned

The CTO appends a row whenever a directive went wrong or needed manual rescue, and fixes the prompt, skill or standard that caused it. Newest first.

**Read the digest; open a row only when you need its detail.** Keep this page under 30 KB: when it passes, the CTO moves the oldest rows to [lessons-learned-archive.md](lessons-learned-archive.md) and puts any new rule in the digest.

## Digest: the rules

The digest starts with general lessons from running this setup on real products, with the product details removed. A lesson of your own goes in with the date of its row.

**Writing specs and ORDERs**
- A CI change's spec names the image its tests run in (it may lack git or jq), and its first live run is read before it's reported done; a GitHub API list is whole when shorter than `per_page`, never by `total_count`. A sparse or no-install job has a test that walks its script's imports against the job's own paths. Where a runner is slow or capped, a spec that triggers it plans the fewest runs; a red control is a run.
- Work sized from a measured estimate says what the whole run ends with at 2x and 5x the estimate. A timing estimate that sets a date names its measurement. A spec that calls a slow public service sets its in-flight limit and writes the number of calls times the measured time, at 2x and 5x, before the run.
- Work per row on live customers' data: every claim expires, state is marked per unit right before its write, and every terminal state is listed. Narrowing which rows reach a path lists that path's guarantees.
- A rule that reads an engine's verdict lists every cap and filter between the rule and the verdict. A rule keyed on the parsed shape gets one end-to-end test from a raw input.
- Parsers of hostile formats judge what the OS or the real parser does; a named constructor comes with its options spelled out; a check that must agree with another parser is tested against that parser. Parser-heavy tasks name the hostile inputs up front (long or non-ASCII labels, nesting, padding).
- An ORDER that can stop on a question says what the agent does if no answer comes. A question whose default reads a rule that guards production data or deploys doesn't proceed on the default.
- A deploy that needs a Board step: the step is written in the CTO's first 15 minutes and named in the ORDER. Format examples use invented values; canary secrets are built at run time.
- Two parallel designs on one new table: the ORDER names one owner. A DD number cited anywhere is taken: grep first. A roadmap with several migration lanes gives each lane its migration number in its ORDER, in landing order.
- Open a task's PR as ready, not draft, unless something must stop it landing.
- Before ordering work whose result is a measured verdict (an A/B, a gate, a backtest), read its free preconditions (sample counts against the bar) and put the numbers in the order. A PAUSE never takes a queued PR out of a merge queue; its owner tells the CTO.
- A shared-cause fix starts only after `git log <base>..origin/main -- <file>` shows no fix already on `main`.
- A land order's spec carries the runbook's test selection rule by reference, never a file count or an older order's gate words. A landing word cites the runbook's rerun rule and names none of its own.
- Before building a change that loosens a product's check (a b3 door), split its live effect into what users dismissed and what they kept, beside its test-set effect. Build it only if it removes more dismissed than kept and loses no case labelled true.
- A spec that ships, moves or turns on a shared runtime file (traced files, a binary, a sandbox) lists every feature that loads it, from a grep, with what each does live once it ships; "nothing else changes" is a claim with that grep behind it.
- A rollout that sets a setting with several fields names the whole row.
- A count sent up names its definition beside the number (which rows, which window, what "failed" means) and its query is kept; a count read once from a quick query is re-read before it goes to the Board.
- A spec that adds or changes a production smoke check asks for one live control run before it lands: the check's script, read-only GETs against production, its old form failing or absent and its new form passing, logs named in the report; mocked-fetch tests don't stand in.
- When a task can move a size or performance gate, estimate the effect before the last review round, and run the gate's check then.
- A cut the Board or users would notice goes into the roadmap's "Decisions for the Board" with a recommendation, not into non-goals. When recommending, show the Board's own setup effort next to the risk, and design so the low-effort option is also safe by default.

**Facts**
- Facts about access come from the Board or a check, not a repo's docs: database access, connected tools (`claude mcp list`), plan limits, environment variable names and targets are read with the CLI or API. Access the Board granted isn't a gap: check `standing-authorizations.md` first. When an authorization changes, grep the old phrase everywhere.
- Check a credential's target by its identity (project id, account id, host), read through the credential itself. Default names are the same in every project, so the string's shape proves nothing.
- One look doesn't establish how a platform behaves. A rule that depends on a plan limit (branches, storage, retention, rate limits) is written after reading the limit.
- A ruling that turns a state into a promise (a word an owner reads) takes the state from what the code sets, not the design. Absence in logs proves nothing without a control query; an absence read from a batch-filled source counts only for rows before its last pass. Read a run's output with the script left out. Say whether a check acts in production from its setting's value and the runbook's meaning of that value, read where the code reads it (per customer, not only the cron's switch), never from a design's title. A flow change re-reads every part the new path skips.
- Resume points can be wrong: check what they say about paid calls against the files.
- A ruling or ask that changes a mechanism a hook enforces (slots, locks, test runs) quotes the hook's lines, not only the runbook: a change the hook refuses is a hook change, b9.
- A long run's progress is its rate, read from its results twice, 10 minutes apart; "running" and an estimate from an earlier phase aren't progress. If a deadline is at risk, the line to your manager goes up before the deadline, not after.
- Fakes aren't the real client. Before the first real run of anything that calls an external tool, make one live call through the exact code path, or test against a recorded real response beside the fakes.
- A clean local `git merge-tree` isn't the host's verdict: a landing plan reads the PR's mergeable state too, and `git merge-base --all` for more than one base.

**Tests**
- Each test file builds what it needs; module mocks spread the real module; a test of module-level state resets it (testing standards 13 and 18).
- A green CI run doesn't prove a race, and code that spawns processes or uses OS paths can pass on one machine and fail in CI's image. Repeats and CI-image runs happen only where the design or task spec asks (README §4), so whoever writes the spec asks for them where code races, spawns processes or uses OS paths.
- A platform check's `pass` needs the mechanism's own evidence and a control run. A negative proof prints its targets next to the control's address: a target that equals it proves nothing.
- One suite per database, one writer per worktree. A heavy run takes a slot where the runbook has them; one tree, one full run. A rerun names files that exist.
- A data migration that reads seed data states how it behaves on a used test database, and is run on one.
- Stop reasons carry the cause chain (the underlying error code and message, never parameters or URLs), or "fix the cause and resume" can't be followed.

**Reviews**
- One review round, and each blocker or major fix gets a re-check by the same reviewer (README §4): a second look finds real defects in live code, and a fix that adds a new mechanism is one of those re-checks. Risky code gets a stronger reviewer, not a second round.
- Long designs don't converge: keep an M design under about 30 KB, and put Senior-level detail into task specs.
- A change that lands in production is never reviewed single-family while the second-opinion keys are set. An exhausted paid provider is a Board question, raised at once; spend is counted from the call log, not from worst-case prices.
- Summary statuses claim no more than their inputs. A change that waits on a person's look is looked at on a local production build before it lands.

**Landings, CI and deploys**
- The merge runs alone, in the exact form; a permission refusal stops the landing, and a refused merge in a production deploy keeps the lock. Push right after the landing's local step. A PR's cleanup is one command per action: close the PR first, delete the branch last and alone.
- Read the staging run before a production deploy, not at a landing; a green run proves only the steps it ran, and a staging step that runs app code first checks which commit staging serves. Step 0, the host can gate it (`staff-engineer.md` §5 step 5). A PR pushed during an outage of the git host gets CI only at its next push.
- "Rides the next deploy" only while a deploy is under way; with none, the landing's owner deploys at once.
- A landing or deploy that followed a default re-reads its question file for the answer first.
- No deploys by hand: a "test" CLI deploy can reach production, and "deployment protection on" may not cover the production domain. Products deploy through Git.
- A guard committed in a repo guards only commits that contain it: merge the default branch before pushing an older branch, and prefer a project-level setting where the platform has one.
- A ruling that waits for a merge first checks that the merge can pass. Senior ORDERs say "Edit tool only, even for repeated replacements".
- Fake secrets in tests are built at run time: a secret scanner reads the branch's whole history, so a later commit can't clear one. Rebuild the final tree on a fresh branch instead of allowlisting.

**Stops, refusals and the machine**
- Persist as you go: the doc before its review, each verdict before any revision. After a stop, recover before redoing, and nothing is paid twice: stopped agents' transcripts survive under `~/.claude/projects/`, and `scripts/second_opinion.py` saves every answer by call id.
- Never hand back while a child runs; wait in bounded foreground steps. An agent forced to hand back names each running child and where its result will land.
- Hand over while the context is fresh: each Staff spawn owns one landing or about 4 tasks, then reports "continue from the log".
- An unattended run never waits on a person. A refusal is final, with no retry and no variant, except the named retries (engineering README); the refused call reshaped (minus a clause, split, dynamic SQL) is a variant, and a walk names each table it reads. No removal of any file to clear an old result: a new log and rc name per run.
- A hook reads a command's text. A question-file line goes in its own Bash call, by its absolute path, with no `cd` and nothing chained; scripts are files written with Write and run by path, never `-c`, `-e` or a heredoc to an interpreter. Never put a hook's block message or a held folder's name in a command's text (a PR body, a `>>` line, a commit message). A GraphQL read writes its query literally in single quotes, one call per PR.
- An edit that narrows or reads a data-handling rule can look to the permission system like weakening oversight, even when a ruling orders it: it goes to the CEO at once with its exact old and new text, and is never retried or reworded.
- A new gate runs once on data where the change does nothing before it reaches the Board; a Board step names a form field's default when it differs.
- A CEO hold or ruling goes from each Staff to every running Senior of its own by SendMessage at once. A "fixed" claim about a guard in an ORDER is read from the CEO's latest broadcast the same turn.
- A shared slot's order comes from every order's waiting lines for it; a holder who releases after a failed gate has used its turn. Before clearing a lock whose owner looks gone, grep the product's file and the owner's order file for a `REFUSED` line: a refused release stays held.
- At every wake and before every turn end, read the question file's new lines, not only at task boundaries; a line up by message is at most 1,000 characters, and the same line goes in the file.
- Scratch goes in one fresh folder named for the order, made with plain `mkdir`; never overwrite a file you didn't write, never copy another agent's file into the repo unread.
- The shared content files (`ceo-questions*.md`, `board-steps*.md`) change only by Edit or by an append (`>>`), never by a script that opens one with 'w'.
- Keep at least 15 GB free. A power loss empties the temporary folder, so verdicts go to `content/` at once. The founder's Esc stops every agent under it.
- `Agent(a, b)` in a main-session agent's definition binds every subagent of that session. Agent definitions list plain `Agent`, and `scripts/hooks/guard_agent_spawn.py` enforces the org chart per caller; never work around it with `claude -p --agent` from Bash.

## Recent lessons

| Date | Directive | What went wrong | Root cause | Fix (and where) |
|---|---|---|---|---|
