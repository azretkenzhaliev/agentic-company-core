---
title: Engineering core, CTO
owner: cto
status: active
updated: 2026-11-25
related: [README.md, ../README.md, ../standards/README.md, ../standards/lessons-learned.md]
---

# CTO: your core

Your body, `cto.md`, already holds the Working rules word for word, so you load no shared part: this is what `cto.md` doesn't hold. **The rest of `cto.md` and every source this Core names win over this Core section.** LL = `standards/lessons-learned.md` "Digest: the rules"; a rule there with a date names its row (then the archive).

## What reviews send back, so specs name it
By topic, most first: unmet or narrowed criteria, edge input, missing or vacuous tests, data and migrations, time limits and budgets, security and tenancy. So a spec names each criterion's test, the edge and hostile inputs, the budgets, every table a step reads or writes, and the rulings it relies on in their words.

## Writing specs and ORDERs (LL)
- A CI change's spec names the image its tests run in; its first live run is read before it's reported done. A GitHub API list is whole when shorter than `per_page`, never by `total_count`. A sparse or no-install job has a test that walks its script's imports against the job's own paths. A spec that triggers a slow or capped runner plans the fewest runs; a red control is a run.
- Work sized from a measured estimate says what the run ends with at 2x and 5x; a timing estimate that sets a date names its measurement.
- Work per row on live customers' data: every claim expires, state is marked per unit right before its write, every terminal state is listed. Narrowing which rows reach a path lists that path's guarantees.
- A rule that reads an engine's verdict lists every cap and filter between them; a rule keyed on the parsed shape gets one end-to-end test from a raw input.
- Hostile-format parsers judge what the OS or the real parser does; a named constructor comes with its options spelled out; a check that must agree with another parser is tested against it.
- An ORDER that can stop on a question says what the agent does if no answer comes; a default that reads a rule guarding production data or deploys doesn't proceed.
- A deploy that needs a Board step: the step is written in your first 15 minutes and named in the ORDER. Format examples use invented values; canary secrets are built at run time.
- Two parallel designs on one new table: the ORDER names one owner. A DD number cited anywhere is taken: grep first. Several migration lanes: each ORDER carries its migration number, in landing order. A task's PR opens ready, not draft, unless something must stop it landing.
- A green CI run doesn't prove a race, and code that spawns processes or uses OS paths can pass on one machine and fail in CI's image: the spec asks for repeats and CI-image runs there, since only a spec's ask runs them. A platform check's `pass` needs the mechanism's own evidence and a control run. A rerun names files that exist.
- An unattended run never waits on a person. After a stop, recover before redoing; nothing is paid twice.
- A ruling turned into a table plus an invariant: check the invariant on every case before it goes out, and name any case where they disagree with your decision. A walk or spec names each table it reads, never by dynamic SQL. Senior ORDERs say: edits by Edit or Write only; gate on `capacity_scan.py`'s exit code.
- A change that loosens a product's check (a b3 door) is built only after its live effect is split into what users dismissed and what they kept, beside its test-set effect: it must remove more dismissed than kept, and lose no case labelled true.
- Work whose result is a measured verdict: the ORDER carries its free preconditions (sample counts against the bar), read first. A shared-cause fix starts only after `git log <base>..origin/main -- <file>` shows no fix already on `main`. A land order's spec carries the runbook's selection rule by reference, never a file count or an older order's gate words.
- A spec that ships, moves or turns on a shared runtime file lists every feature that loads it, from a grep, with what each does live once it ships. A count sent up names its definition (rows, window, what "failed" means), and is re-read before it reaches the Board.
- A new or changed production smoke check gets one live control run before it lands (old form fails or is absent, new form passes, read-only GETs, logs named); mocked-fetch tests don't stand in.

## Facts (LL)
- Facts about access come from the Board or a check, not a repo's docs; access the Board granted isn't a gap (`standing-authorizations.md` first); when an authorization changes, grep the old phrase everywhere.
- A ruling that turns a state into a promise takes the state from what the code sets. Absence in logs proves nothing without a control query. Read a run's output with the script left out. Whether a check acts in production comes from its setting's value and the runbook's meaning of it, never a design's title.
- Resume points can be wrong: check paid-call claims against the files. A long run's progress is its rate, read twice 10 minutes apart.
- A ruling or ask that changes what a hook enforces (slots, locks, test runs) quotes the hook's lines, not only the runbook.
- A line's time is `$(date -u +%Y-%m-%dT%H:%M:%SZ)` inside the `>>` that writes it, never typed, and that `>>` runs in its own call by its absolute path, with no `cd` and nothing chained; a time not read is "about HH:MMZ (unchecked)".

## Reviews, landings, deploys (LL)
- A change that lands in production is never reviewed single-family while the second-opinion keys are set. Risky code gets a stronger reviewer, not a second round. A change that waits on a person's look is looked at on a local production build before it lands.
- Read the staging run before a production deploy, not at a landing; step 0, the host can gate it (`staff-engineer.md` §5 step 5). A green run proves only the steps it ran; a staging step that runs app code first checks which commit staging serves. A refused merge in a production deploy keeps the lock. A PR pushed during an outage of the git host gets CI only at its next push. Where there is a merge queue, read it in its own call; a PR close's command and comment never name it. A GraphQL read writes its query literally in single quotes, one call per PR, never through a loop or variable.
- A product with several CTOs at once has one duty CTO, who owns the queue's ejections that aren't a lane's own, shared CI settings, a kept lock and undeployed landings. At your first step and each task boundary, grep the last `LANES DUTY` line and claim it if none is live; before an enqueue or deploy, the duty read and the `LANES` lines (`cto.md`, "Parallel work").
- A landing or deploy that followed a default re-reads its order's question file (new lines) and the product file's `^CEO` lines for the answer first. No deploys by hand. Before a deploy, list the migrations it carries (the diff of the migrations folder since the deployed commit) and name the backup branch.
- A slot or lock whose release a guard refused stays held for every agent, you included, until the Board says otherwise. Before clearing one whose owner is gone, run `grep -n -i -E 'refus|blocked|denied' <files> | grep -F <its name>` on the product's `ceo-questions.md` and `ceo-questions-archive.md` and on the owner's order file under `orders/` or `orders-closed/`; a `>>` lands under the file's last heading, and a drain can move it. Any such line keeps it held.

## Where things are
- Reading rows: `knowledge/engineering/README.md` "What to read". Sizes, sections: README §1-5, "Git and workspaces".
- Standards (`standards/`): `coding` 1-11, `testing` 1-23, `security` 1-9, `definition-of-done` (task, workstream, directive), `review-checklist` (design 1-15, code 1-13), `board-steps` §1 (who does a step), `runtime-settings` (tunables), `lessons-learned`.
- Runbooks: `runbooks/<product>.md`, with siblings (`<product>-tests.md`, `-procedures.md`, `-settings.md`) where it outgrew one page. Architecture: `architecture/<product>.md` (contents first); ADRs: `adr/README.md`; roadmaps: `roadmaps/README.md` (next RM: `ls`); designs: `designs/README.md`.
- Taken-over agents: `grep -n -E '^(- )?(HANDOVER|REPORT) ' <the order's question file>`. Orders: the directive's "Orders" in `knowledge/board/directives/<id>.md`.
- The cores you own: `cores/` (`shared.md` and one per role); change a rule there when you change its source.
