---
title: Lessons learned
owner: cto
status: active
updated: 2026-10-19
related: [README.md, ../README.md, testing.md]
---

# Lessons learned

The CTO appends a row to the log below whenever a directive went wrong or needed manual rescue, and fixes the prompt, skill or standard that caused it. Newest first.

## Seed lessons

These come from the first weeks of running this setup on real products, with the product details removed. Most are already rules in the prompts, the [engineering README](../README.md) or the [testing standard](testing.md); each says where.

### Keeping work alive through stops

- **Persist as you go.** A usage limit or a network outage can end any agent mid-loop, and whatever lives only in its context is lost: a review verdict, a Senior's report, a paid second opinion. Save the design before its first review, write each verdict into the log before revising, and keep the doc's header on the loop's state. *Engineering README §3; `staff-engineer`.*
- **After a stop, recover before redoing.** Stopped agents' transcripts survive under `~/.claude/projects/<project>/<session>/subagents/`. Read them for finished reports and paid answers before restaffing; `scripts/second_opinion.py` also saves every answer by call id, so a review of an unchanged range reuses it instead of paying again. Write the stop state (worktree heads, uncommitted files, open reviews) into the roadmap, and give each new order its exact resume point. *Engineering README §3.*
- **An unattended run never waits on a person.** A background agent that hits a permission prompt waits silently, and the whole order stalls for hours. A refused action is final for the order: nobody retries it or tries a variant, and it goes to the Board with the exact command. *Engineering README §3.*
- **Hand over while the context is fresh.** A Staff engineer that runs many tasks fills its context, slows down, and loses more at a stop. Each spawn owns one landing or about 4 tasks, then reports "continue from the log". *`staff-engineer`, `cto`.*
- **Parallel loops spend the window faster, not less in total.** Size the number of parallel Staff engineers to the Board's Claude plan, and read the usage window at the start of each order.
- **A manager can be ended while its children still run.** When an agent is forced to hand back, it names each running child and where that child's result will land, so the next manager can collect it.

### Reviews that converge

- **Long designs don't converge.** Each revision adds text the next round finds new problems in, so the cap stops a loop that is converging, not one in dispute. Keep an M design under about 30 KB, put Senior-level detail into task specs, and make round 3 a closing round. *`staff-engineer`, `design-reviewer`, `code-reviewer`.*
- **The CTO may accept named, narrowing fixes after the cap by a recorded ruling,** and an agreed code fix after the cap rides as the next task's first item. A disputed finding still goes up. *Engineering README §3–4.*
- **Parser-heavy tasks name the hostile inputs up front** (long or non-ASCII labels, nesting, padding), so round 1 sees them instead of round 3. *`staff-engineer`.*
- **Second opinions: count real spend, don't ration by worst case.** Pricing every call at the model's maximum output made the budget look spent and led to skipping reviews on a production change. Spend is counted from the call log, and a change that reaches production is never reviewed single-family while the keys are set. *Engineering README §3.*
- **An exhausted paid provider is a Board question, raised at once,** not something the next report mentions in passing.
- **If several products share one set of review keys,** add a product or directive field to the call log, or spend can only be split by guesswork.

### Facts about platforms and access

- **Read capability facts, don't assume them.** Database access, connected tools (`claude mcp list`), plan limits, environment variable names and targets: read them with the CLI or API, or ask the Board. A product repo's own docs may be out of date.
- **Check a credential's target by its identity** (project id, account id, host), read through the credential itself. Default names such as a database owner role are the same in every project, so the string's shape proves nothing.
- **One look doesn't establish how a platform behaves.** A "test" CLI deploy to a new project went straight to production, and "deployment protection on" didn't cover the production domain. Products deploy through Git; see the optional Vercel guard in `docs/optional-integrations.md`.
- **Fakes aren't the real client.** Before the first real run of anything that calls an external tool, make one live call through the exact code path, or test against a recorded real response beside the fakes.
- **A rule that depends on a plan limit** (branches, storage, retention, rate limits) is written after reading the limit, or carries a `TODO` until it is read.
- **`Agent(a, b)` in a main-session agent's definition binds every subagent of that session,** so the CTO couldn't spawn its team under the CEO. Agent definitions list plain `Agent`, and `scripts/hooks/guard_agent_spawn.py` enforces the org chart per caller. Before staffing, check that the Agent tool offers the needed types; never work around it with `claude -p --agent` from Bash.

### Git, CI and permissions

- **Fake secrets in tests are built at run time.** A canary that looks like a credential is a credential to a secret scanner, and scanners read the branch's whole history, so a later commit can't clear it. Rebuild the final tree on a fresh branch instead of allowlisting. *`staff-engineer`, `code-reviewer`.*
- **The merge runs alone, and a refused merge is final.** The permission system may refuse a merge it allowed an hour earlier, more readily inside a chained command. Stop the landing, keep the lock, and let the Board merge or decide. *Engineering README §5; `staff-engineer`, `cto`.*
- **Cleanup is one command per action,** only when the order names it: close the PR first, delete the branch last and alone.
- **A proof that needs a commit is the Senior's commit;** the CTO only reads the PR's state.
- **A guard committed in a repo guards only commits that contain it.** Branches cut before it aren't protected: merge the default branch before pushing them, and prefer a project-level setting where the platform has one.
- **Each agent writes only in its own scratchpad subfolder,** and never copies another agent's file into the repo unread.

### Tests

- Tests hold up when other workstreams land; platform checks must be able to fail; a check that must agree with another parser is tested against that parser; mutation checks run in a copy; module mocks keep the real module's other exports. *Testing standards 9–13.*
- **A data migration that reads seed data** states how it behaves on a used test database, and is run on one.
- **When a task can move a size or performance gate,** estimate the effect before the last review round, and run the gate's check then.
- **Stop reasons carry the cause chain** (the underlying error code and message, never parameters or URLs), or "fix the cause and resume" can't be followed.

### Working with the Board

- **A cut the Board or users would notice** goes into the roadmap's "Decisions for the Board" with a recommendation, not into non-goals.
- **When recommending, show the Board's own setup effort next to the risk,** and design so the low-effort option is also safe by default.

## Log

| Date | Directive | What went wrong | Root cause | Fix (and where) |
|---|---|---|---|---|
| – | – | none yet | – | – |
