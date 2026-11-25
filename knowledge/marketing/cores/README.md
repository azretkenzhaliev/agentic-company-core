---
title: "Marketing cores: what each role loads at spawn"
owner: cmo
status: active
updated: 2026-01-01
related: [shared.md, cmo.md, content-producer.md, content-reviewer.md, performance-analyst.md, reel-analyst.md, trend-researcher.md, ../README.md]
---

# Marketing cores

Each marketing role loads `shared.md` and its own core at spawn, as the "## Core" section `scripts/build_cores.py` writes into its agent file. This page isn't loaded.

**How they're built:** each line is a rule's operative words or a pointer, with its source. The rules stay in the agent files and skills; a core repeats or points, and never loosens. Precedence, written at the top of `shared.md`: the rest of the agent file and every source the core names win over the Core section. No research note and no copied brand fact goes in a core: facts stay in their owners' pages.

**Budget:** at most 10,000 characters a role as loaded: the agent file's Core section, from `## Core` to the blank line ending it, shared part included (`scripts/build_cores.py`'s cap).

## For the platform engineer

Regenerate with `python3 scripts/build_cores.py` after a core page changes, through the gate; `--check` says what differs. A core replaces nothing in an agent file but the reel-analyst's reading of `swipe-teardown`'s Hard rules at each run: their operative words load with its core.

## Upkeep

When a rule a core quotes changes, its owner updates the core the same day (`CLAUDE.md`, "Fix the rule, not only the case").
