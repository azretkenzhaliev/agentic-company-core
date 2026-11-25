---
title: Runtime settings (values we tweak are read at run time)
owner: cto
status: active
updated: 2026-11-25
related: [README.md, security.md, review-checklist.md]
---

# Runtime settings

A value someone is likely to tweak isn't defined in the code: it's read from somewhere that can be changed at any time, so nobody waits on a deploy to tweak it. This binds all new code in every product; existing values move as the inventory in each product's runbook says.

## 1. Which values are runtime settings

A value is a runtime setting when someone is likely to change it to tune behaviour, not to change what the code means:

- sizes (a chunk, a batch, a page, a sample), lane and concurrency counts;
- budgets and floors (money, tokens, calls, a pool's floor), and rates (per minute, per day);
- timeouts and waits, retry counts and back-off;
- thresholds and scores (a cut-off, a confidence, a share);
- model choices (which model of an already approved vendor);
- how often a tick does work (every Nth tick, a minimum interval), and its time budget inside the function's limit.

**Stays in code:**

- what the platform fixes at build: a function's maximum duration, cron schedules, memory and region. Set each once to what the most generous setting needs; the tick's own budget (a setting) is the knob;
- secrets and per-environment config: environment variables;
- values that decide who can reach data (sign-in, sessions, permissions, OAuth scopes, tenancy): a change there is a one-way door (b4) and gets a code review anyway;
- constants that define meaning, not tuning (a protocol's field length, a unit conversion, an enum);
- values in code that can't read a setting: a sandboxed child with no environment or database. A change there gets a code review that checks its worst case against the platform's limit.

## 2. How a setting is read

1. **Where:** the product's own settings store (a key-value table in its database, one row per key, JSON value; or one settings document). A product without one adds it in its own database in the first order that moves a value. No new or paid config service.
2. **When:** on each request or tick, or from a process cache of at most **60 s**. A path that needs several keys reads them in one query.
3. **Default:** each key has a default in code equal to the value the code used before the move, so a deploy with no rows written changes nothing.
4. **Safe range:** each key has a range in code (min and max, or an allowed set). A value outside it, a malformed value or a missing row falls back to the default, and the code logs one line (the key and the reason) at most once a minute per process. A failed read falls back to the default too. Widening a range is a code change, with its review.
5. **One registry per product:** key, type, default, range, what it tunes, and its door (section 3). New keys go into it; nothing reads a setting around it.
6. **Effective values are readable:** a staff view or a script prints each key's effective value and whether it came from a row or the default. A change is checked by reading it there.
7. **Tests:** each key has a test that a missing, malformed and out-of-range row each give the default ([testing.md](testing.md), rule 20).

## 3. A setting removes the deploy, not the doors

Changing a row is quick; whether you may is unchanged (`CLAUDE.md`, "The Board's attention"):

- **Lowers protection of live customers** (b3): a check off, a threshold raised, a trust exception, a rule that flags less, and anything that makes the product check less of what it promised to check (a shorter timeout or wait, fewer retries, a lower sweep rate, a floor that stops the checks sooner). **The Board's yes first**, then the upsert.
- **Spends beyond a pool or a budget the Board set** (b1), or a pool floor lowered so spending can pass it: **the Board's yes first.**
- **A model choice that sends data to a new outside party** (b2) or a new paid service (b1): **the Board's yes first.** A model of a vendor already approved for that data is two-way.
- **Everything else** is two-way under the normal rules: the owner decides, records the old and new value and how to undo it (upsert the old value, or delete the row for the default), and tells under "Decided". Raising protection within a pool is two-way; lowering spend is two-way only when it doesn't lower protection. A change that hits two doors takes both.

The registry marks each key's door (two-way, b1, b2 or b3) and the runbook repeats it beside the key's upsert.

## 4. Changing a setting

The product runbook lists, per key: today's default, the range, the door, the one-line change and the undo. For a key-value table in Postgres, one statement:

```sql
insert into <settings_table> (key, value) values ('<key>', '<json>'::jsonb) on conflict (key) do update set value = excluded.value
```

A setting upsert needs no backup branch ([security](security.md) rule 9). A trigger that records every change is worth having; the report names the key, old and new value, and the time (UTC). The change is checked by reading the effective value (section 2, step 6) within 60 s.
