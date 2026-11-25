---
title: Executive summaries for the Board (format and snapshots)
owner: ceo
status: active
updated: 2026-11-25
related: [board-preferences.md, ../finance/spend.md]
---

# Executive summaries for the Board

## The rules for every executive summary

Defaults; the Board changes them as it likes.

1. **Tables per workstream:** task, what it does, status, done date (the Board's time zone), and whether it is live. Keys:
   - Status: ✅ merged · ☑️ approved, not merged · 🔄 in progress · ⏳ not started.
   - Live: 🟢 on staging · ⚪ merged but unused · ❌ not merged.
2. **Show the change since the last summary:**
   - each table has a **"Since last"** column: the previous status → today's, or "–" when unchanged;
   - a short count at the top: merged, approved, design updates, started, and new tasks;
   - how much working time the period really had (pauses excluded).
3. **Name every limit** on agents, money or usage that affects speed, with the reason.
4. **After each summary,** append its snapshot below. The next summary's delta is computed from it.
5. **Include the work not done yet, and a percentage of progress:**
   - every task on the current master list, including ⏳ ones, with what each waits on;
   - overall progress in %, weighted by each task's size (the size column of the master list; a range counts its midpoint; an unsized item counts 1; an in-progress task counts the share of its sub-tasks done), plus the share of items done, and the same for the path to the current milestone.
6. **Live key once production exists:** 🟢 in production · ⚪ merged or in production but switched off or unused · ❌ not merged.
7. **Every number states its period and source** (from and to; the Board's time zone for the Board): a count without dates is not reported.
8. **A budget or limit warning says when it runs out, and what stops then.** At the current pace and with the fix applied, each with its source; never only the next warning line.
9. **Every summary and status report has a Spend block.** One line per paid vendor or pool: spent this cycle to date, what the plan includes, the projection to the cycle's end at the current pace, and the date it passes what's included or a cap. Each number is read from its source in that turn, with the time; the ones nobody can read yet say so. Lead with the line that is over, or will be. The ledger: [finance/spend.md](../finance/spend.md). `python3 scripts/spend_report.py` prints the block: what it can read live, the rest named with who reads them.
10. **A test's numbers name what they ran on:** the prompt, and whether it is the one the Board asked for; where the answer key comes from (a person, or which models agree); and how many cases stand behind each rate.
11. **For a bird's-eye reader.** Plain words that need no earlier context. A row or line says what a product or the company can now do, or what changed for customers, money or the Board; never which pull request merged. A codename (an ask, directive or design id) appears only after a short plain name of the thing, and only when the Board may need to find it. Where rule 1's task tables differ, this rule decides: rows are outcomes, not tasks.

## Snapshots

Statuses use the keys above. A row covers a group of tasks when they share a status.

None yet.
