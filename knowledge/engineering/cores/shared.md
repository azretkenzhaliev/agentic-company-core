---
title: Engineering core, shared part
owner: cto
status: active
updated: 2026-11-25
related: [README.md, ../README.md, ../standards/lessons-learned.md]
---

# Engineering core: shared (Staff, Senior, code and design reviewers)

The rules your agent file points to but doesn't hold, each with its source. **The rest of your agent file and every source this Core names win over this Core section.** A stricter choice the Board recorded wins over both. WR = `.claude/agents/engineering/cto.md` "Working rules"; LL = `standards/lessons-learned.md` "Digest: the rules". `<repo root>` is the main checkout's absolute path.

## Reading and reporting
- Read sections, not pages: `grep -n` a page, then read a range. Never a whole folder; never re-read what you have. Archives (`*-archive.md`, `archive-*.md`, `*-history.md`) are only searched. A page over its size limit (`knowledge/oversize-pages.txt`, `wc -c`) is never read whole. (WR "Read sections, not pages")
- Test runs show failures and totals only: output to a log, then `tail` or `grep` it. (WR "Short output")
- Your report is your final message (SubagentHandback), about 2k tokens at most, with its decisions (a verdict's findings) in it: cut anything else first; detail goes to a file it names. Never write `report*.md`, `summary*.md`, `findings*.md` or `analysis*.md`. (WR "Short reports", "No report files")
- Scratch: one fresh folder named for your order under your scratchpad, plain `mkdir` (no `-p`). Never overwrite a file you didn't write. Never `rm` a path built from a variable or a glob. (LL "Stops"; `senior-engineer.md` Boundaries)

## Waiting and handing back
- Never `run_in_background`. A long command runs as `<command> > <log> 2>&1; echo $? > <rc>`, a new `<rc>` each run. Moved to the background: don't end your turn; repeat `until [ -e <rc> ] || [ $SECONDS -ge 170 ]; do sleep 5; done; cat <rc> 2>/dev/null || echo running` with `timeout: 175000`. Every loop that sleeps has `$SECONDS` in its test; use the templates word for word. (WR "Wait in the foreground")
- Never hand back while a command or agent of yours runs. A refused hand-back didn't arrive: end your turn once nothing of yours runs. Woken after your hand-back: do nothing. (WR "Never hand back", S11)
- Deadlines are UTC: compare with `date -u`. (WR)

## Tests and the machine
- On the founder's machine, only the tests your change touches (the runbook's task suite), never a full suite, before a deploy too (SA-001 condition 2). Nothing runs twice on one tree (`git rev-parse <sha>^{tree}`) but a landing's essential tier and zero-test check. A heavy run (over about 30 test files) takes a slot where the runbook has them. (WR "Tests: what the change touches")
- S11, one suite per database, one writer per worktree: the test database your ORDER names (Staff: the worktree's; Senior `-sr`; reviewer `-cr`). Before a run, `mkdir workspaces/<product>/.test-locks/<name>` with an `owner` line; remove both after, failure too; `mkdir` fails: don't run. A test script that takes the lock itself: don't take it first. At hand-back, stop your database as the runbook says, unless another agent's lock is on it. A guard refuses your release of a slot or lock: at once, one `REFUSED` line in the product's `ceo-questions.md` (slot or lock, time, the guard's words); it stays held. (WR S11)
- The load hold gates on the exit code, in one Bash call: `python3 scripts/capacity_scan.py --mac > <log>; echo $? > <rc>`, and start only on 0 (`room: yes`), never on reading its text. Never kill running work for load. At least 15 GB free disk before large pulls; never reset Docker. (WR "The load hold", "Disk and machine")

## Refusals, customer data, secrets
- A permission refusal is final: stop that line of work; the exact command under Open questions, the refusal under Risks. No retry, no variant: the same effect by another tool, form, agent or cwd (an Edit, a clause cut, dynamic SQL). Three retries only, once each, final if refused: a refused `origin/main` merge, exactly as in `staff-engineer.md` §5 step 4; a refused push of your branch, as `git -C <full worktree path> push origin <branch>` alone; exactly the form a block message names. Only these hook lines aren't refusals: `bounded_wait.py`'s (run the form it names) and a full-suite guard's no-slot, load, no-test-database and battery lines, where there is one (a wait: do as it says, then the same command, no variant). Every other hook's stop, a permission prompt's and the classifier's stay final. (WR "A permission refusal is final", "Tests")
- Customer data goes to no outside model unless a standing authorization names that provider, and none of it into git, the KB or any file. No secret in git, the KB, a report, a log, a test or a packet; never print one. A fake secret or canary in a test is built at run time from harmless parts, never a literal. (WR; `CLAUDE.md`, "Git, code and safety")

## Where the rest is
- Your reads: `knowledge/engineering/README.md` "What to read", your row. A product: its runbook (`runbooks/<product>.md`). Standards: `standards/README.md`; a lesson: grep `lessons-learned.md`, then its archive; what the Board prefers: grep `knowledge/company/board-preferences.md`; b1-b9: `CLAUDE.md` "The Board's attention".
