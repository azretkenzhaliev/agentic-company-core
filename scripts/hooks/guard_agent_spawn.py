#!/usr/bin/env python3
"""PreToolUse hook for Agent (Task is its older name).

Holds the org chart: the ceo, cto, staff-engineer, cmo and platform-engineer
may spawn only their own reports (the ceo also its own code-reviewer, for the
gate on system changes); the ceo, cto, staff-engineer and cmo may also start
the ux-expert; the critic, content-producer, content-reviewer,
performance-analyst, trend-researcher, reel-analyst and ux-expert spawn nothing.
Blocks (exit 2, reason on stderr) any other agent type they ask for. Other callers, including a plain `claude` session
(one started without an agent), are not limited, by the org chart or the load. An input
it can't read and an error are refused.

It also holds this machine's load: a caller in HELD_CALLERS, whose agent file carries the load hold, can't start an
agent type in HEAVY, the ones that run tests or builds, while the 5-minute load is LOAD_PER_CPU or more per CPU (25 on
a 10-CPU machine), or can't be read, as `scripts/capacity_scan.py --mac` reads it for its room line. Running work goes
on: this sees only new spawns. The stop is a wait, ended only by a form its message names: the same spawn once the scan
prints `room: yes`, or, for a production fix (which doesn't wait), the same spawn with a line in its prompt starting
`PRODUCTION FIX:` and naming the fault, which starts at any load. Each spawn that line lets through (held but for it)
adds a JSON line to PRODUCTION_FIX_LOG under the project root (CLAUDE_PROJECT_DIR; workspaces/ is gitignored): UTC
time, caller, agent type and the line, for the drift audit. A log it can't write doesn't hold the fix. Disk and memory
stay the scan's alone (cto.md, "The load hold").
Not held, since they run no tests or builds: the cto and the cmo (their children's spawns are held), critic, analyst,
design-reviewer (reads a design against the code), content-reviewer (content_lint only reads), performance-analyst,
trend-researcher and reel-analyst (downloads and measures reels). The default agent and Claude Code's built-in types
(general-purpose, fork and the rest) aren't listed: no caller in MAY_SPAWN may start them.
The cmo's message points to cmo.md's load hold, not cto.md's: its Bash takes no `$`, so it waits by ending its turn.

Why a hook and not `Agent(a, b)` in the agent definitions: Claude Code
applies the main session's `Agent(a, b)` list to every
subagent of that session too. `Agent(cto, analyst)` on the CEO stopped the
CTO from spawning its team. So every definition lists plain `Agent`, and
this hook limits each caller. The hook input names the caller in
`agent_type`: the subagent's type, or the --agent type on the main thread.
"""

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

AGENT_TOOLS = {"Agent", "Task"}

LOAD_PER_CPU = 2.5  # of the 5-minute load: capacity_scan.LOAD_PER_CPU, kept equal by a test
# The agent types that run tests or builds, and why: a new one waits for the load (module docstring).
HEAVY = {
    "senior-engineer": "runs its task's tests in its own test container",
    "code-reviewer": "runs the tests the diff touches",
    "staff-engineer": "runs tests in its worktree's test container",
    "platform-engineer": "runs the system's test suites",
    "ux-expert": "builds and starts a product's local production build",
    "content-producer": "builds Remotion bundles and renders reels and slides in Chromium",
}
# The callers whose agent file carries the load hold: ceo.md "The only limits", cto.md, staff-engineer.md and cmo.md
# "The load hold", platform-engineer.md "How you work" step 3.
HELD_CALLERS = {"ceo", "cto", "staff-engineer", "platform-engineer", "cmo"}
PRODUCTION_FIX = re.compile(r"^PRODUCTION FIX:[ \t]*\S.*", re.M)  # the whole line
PRODUCTION_FIX_LOG = Path("workspaces") / "system" / "production-fix-spawns.jsonl"

MAY_SPAWN = {
    # The CEO starts its own code-reviewer for the gate on guardrail files.
    "ceo": ["cto", "analyst", "critic", "cmo", "platform-engineer", "code-reviewer", "trend-researcher",
            "reel-analyst", "ux-expert"],
    "platform-engineer": ["code-reviewer"],
    "cto": ["staff-engineer", "senior-engineer", "code-reviewer", "ux-expert"],
    # A Staff engineer starts the ux-expert at depth 3, so it has no Agent tool and spawns nothing.
    "staff-engineer": ["design-reviewer", "senior-engineer", "code-reviewer", "ux-expert"],
    "critic": [],
    # The CMO, not the producer, starts the reviewer: a port to a tool with one nesting level less still fits.
    "cmo": ["content-producer", "content-reviewer", "performance-analyst", "analyst", "trend-researcher", "reel-analyst",
            "ux-expert"],
    "content-producer": [],
    "content-reviewer": [],
    "performance-analyst": [],
    "trend-researcher": [],
    "reel-analyst": [],
    "ux-expert": [],
}


def log_production_fix(caller: str, requested: str, line: str) -> None:
    """One JSON line for a spawn the PRODUCTION FIX line let through; a log it can't write doesn't hold the fix."""
    root = Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path(__file__).resolve().parents[2])
    record = {"time": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "caller": caller,
              "agent_type": requested, "line": line[:500]}
    try:
        (root / PRODUCTION_FIX_LOG).parent.mkdir(parents=True, exist_ok=True)
        with (root / PRODUCTION_FIX_LOG).open("a", encoding="utf-8") as log:
            log.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        pass


def load_hold(requested: str, prompt: str, caller: str = ""):
    """The refusal of a new HEAVY spawn while the 5-minute load is LOAD_PER_CPU per CPU or more, or unreadable, as
    capacity_scan.mac_room reads it; None when it may start (a PRODUCTION FIX line it lets through is logged)."""
    if requested not in HEAVY:
        return None
    cpus = os.cpu_count() or 1
    limit = LOAD_PER_CPU * cpus
    try:
        load = os.getloadavg()[1]
    except OSError:
        load = None
    if load is not None and load < limit:
        return None
    fix = PRODUCTION_FIX.search(prompt)
    if fix:
        log_production_fix(caller, requested, fix.group(0))
        return None
    reading = "can't be read" if load is None else f"is {load:.2f}"
    rules = "cmo.md" if caller == "cmo" else "cto.md"  # where the caller's wait is (module docstring)
    return (
        f"Blocked: this machine's 5-minute load {reading}, and no new {requested} starts while it is {limit:g} or more "
        f"({LOAD_PER_CPU:g} per CPU on {cpus} CPUs) or can't be read, as `python3 scripts/capacity_scan.py --mac` "
        f"holds it: a {requested} {HEAVY[requested]}. Running work goes on: nothing is stopped. This stop is a wait, and "
        "only these forms end it: this same spawn, unchanged, once that scan prints `room: yes` (wait and re-check as "
        f"{rules}, \"The load hold\", says); or, for a production fix only (a fault live in production now), this same "
        "spawn with a line in its prompt starting `PRODUCTION FIX:` and naming the fault."
    )


def refusal(event: dict) -> "str | None":
    """Why the spawn is refused, or None."""
    if event.get("tool_name") not in AGENT_TOOLS:
        return None
    tool_input = event.get("tool_input") or {}
    requested = str(tool_input.get("subagent_type") or "").strip().lower()
    allowed = MAY_SPAWN.get(event.get("agent_type") or "")
    if allowed is None:
        return None
    if requested not in allowed:
        return (
            f"Blocked: {event['agent_type']} may spawn only {', '.join(allowed) or 'no agents'} "
            f"(the org chart in knowledge/company/org-chart.md), not '{requested or 'the default agent'}'. "
            "Name one of those, or report the need up the chain."
        )
    caller = event["agent_type"]
    return load_hold(requested, str(tool_input.get("prompt") or ""), caller) if caller in HELD_CALLERS else None


def main() -> None:
    try:
        reason = refusal(json.load(sys.stdin))
    except Exception as error:  # fail closed: a crash would exit 1, which doesn't block by itself
        reason = f"Blocked: this hook couldn't check the spawn ({type(error).__name__}), so it refuses."
    if reason:
        print(reason, file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
