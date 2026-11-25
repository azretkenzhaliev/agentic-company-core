---
title: Engineering cores
owner: cto
status: active
updated: 2026-11-25
related: [shared.md, senior-engineer.md, code-reviewer.md, design-reviewer.md, staff-engineer.md, cto.md, ../README.md]
---

# Engineering cores

A core is what an engineering role has in front of it on every task, loaded at spawn: the rules its agent file points to but doesn't hold, each in its operative words or as a pointer, with its source. **Status: loaded** as each agent body's "## Core". A page change reaches the bodies only when they are regenerated through the system-change gate (`scripts/build_cores.py`; "Load plan" below). Why it exists: agents told to read a page at the start often skip it.

## What loads

`scripts/build_cores.py` writes each role's "## Core" section from these page bodies (front matter left out, headings two levels down), and counts it with its own `section()`. The cap is 10,000 characters per role, shared part included.

| Role | Loads (page bodies) |
|---|---|
| senior-engineer | [shared.md](shared.md) + [senior-engineer.md](senior-engineer.md) |
| code-reviewer | shared + [code-reviewer.md](code-reviewer.md) |
| design-reviewer | shared + [design-reviewer.md](design-reviewer.md) |
| staff-engineer | shared + [staff-engineer.md](staff-engineer.md) |
| cto | [cto.md](cto.md) only |

## Design choices

Two-way; undo by reverting these pages and regenerating.
- **A core holds only what the agent file points to but doesn't hold.** The agent file is already loaded whole at every spawn, so restating it costs tokens and adds nothing.
- **The source binds.** Each core says the rest of the agent file and every source the Core names win over the Core section, and the Senior's that inside a product repo its own rules win over the standards (`standards/README.md`). A Core line never narrows its source: the refusal line lists the only hook lines that aren't refusals and closes with "Every other hook's stop, a permission prompt's and the classifier's stay final."
- **The CTO loads no shared part:** its body, `cto.md`, holds the Working rules word for word. Its core is the digest and the pointers `cto.md` doesn't hold.
- **No copied facts.** Product facts (test databases, ports, suites, deploy steps) stay in the runbooks; a core points to them.
- **Chosen by use.** A line earns its place by what agents skip reading and what reviews send back most. Change the selection on your own numbers, when you have them: the share of spawns that open a source page, and the share of first verdicts that are CHANGES_REQUESTED, by topic.

## Load plan

Where: the agent body, as a `## Core` section after the opening paragraph, its text these pages' bodies (shared first), not a preload. Why: `skills:` preload is reported broken when an agent runs as the main session (`claude --agent cto` is one), and a `SubagentStart` hook would be one more entry in `.claude/settings.json`. `scripts/tests/test_build_cores.py` fails when a body's Core section differs from these pages, so the page stays the one text and the CTO stays its one writer.

The platform engineer regenerates the bodies (never by hand, never on `main`): `python3 scripts/build_cores.py`, then `--check`.

The "What to read" rows in [../README.md](../README.md) list only what the core doesn't carry as "Always", and name what it carries as "open for a case".

## Left out, and where it still lives

Nothing below is dropped: it binds from its source.

| Source | In a core | Left out, and where it lives |
|---|---|---|
| `cto.md` Working rules | Shared: reading, short output and reports, no report files, waits, hand-back, UTC, S11, tests, load-hold gate, disk, refusals, customer data, secrets. Senior and Staff: Edit or Write ("Change a file's text"). Staff: child agents, one report per result, and of "Logs" only what `ceo-questions.md` holds and how it's written | The why of each rule; size limits (`scripts/kb_lint.py`); of "Logs": one design-log row per landing, the roadmap's row per workstream change (the CTO's), `cq_archive.py`'s run, moves and `ACTED:` marks; slot detail; the CTO clearing dead locks (S11); Edit-or-Write for reviewers, who have no Edit or Write |
| `cto.md` other sections | Staff: Thin managers, Board steps and questions, the measured criterion of "On every order" | Of "Board steps and questions": `PAUSE`, and `TaskStop` only agents you spawned and theirs, leaves first; taking over a finished Staff's agents; "Capacity, every time"; "Switched off in production"; "Usage"; the load hold's re-check and `HOLD` lines |
| Lessons digest | CTO: all of "Writing specs", "Facts", "Reviews"; most of "Landings" and "Stops". Staff, design reviewer: most spec lines. Shared: most of "Stops" | Every role but the CTO still reads the digest or these groups as "Always" in its row (`../README.md`, "What to read") |
| `review-checklist.md` | Code 1-13 and Design 1-15, operative words, in the reviewers' cores; Senior: code 1, 8-13 | Each point's detail |
| `coding.md` 1-11, `security.md` 1-9 | Senior: all of coding, security 1-5, 7-8; reviewers: security short | Security 2's detail, 6's package choice, 9's detail |
| `testing.md` 1-23 | Senior: 1-7, 9, 13, 15, 17, 18, 20, 23; code reviewer: 4, 6, 13, 17, 18, 20, 23 | 8 (repo without tests), 10-12 and 16, 14 and 22 (timing bounds), 19 (selection size), 21 (failure output), 3's tiers (shared and the Senior file) |
| `definition-of-done.md` | Task: code reviewer; workstream: Staff, design reviewer | Directive: the CEO's |
| `runtime-settings.md`, `board-steps.md` | §1 of each, as pointers or lines | All other sections |
| Agent files | None restated | All their own text, which loads whole |

## Upkeep

- When the CTO changes a rule a core restates, the core changes in the same step, re-measured (the cap stays 10,000 per role).
- A rule that fails (`CLAUDE.md`, "Fix the rule, not only the case") is fixed at its source first, then here.
