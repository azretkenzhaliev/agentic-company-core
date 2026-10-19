#!/usr/bin/env python3
"""PreToolUse hook for Agent (Task is its older name).

Holds the org chart: the ceo, cto and staff-engineer may spawn only their
own reports. Blocks (exit 2, reason on stderr) any other agent type they ask
for. Other callers, including a plain `claude` session, are not limited.

Why a hook and not `Agent(a, b)` in the agent definitions: Claude Code
(checked in 2.1.296) applies the main session's `Agent(a, b)` list to every
subagent of that session too. `Agent(cto, analyst)` on the CEO stopped the
CTO from spawning its team. So every definition lists plain `Agent`, and
this hook limits each caller. The hook input names the caller in
`agent_type`: the subagent's type, or the --agent type on the main thread.
"""

import json
import sys

AGENT_TOOLS = {"Agent", "Task"}

MAY_SPAWN = {
    "ceo": ["cto", "analyst"],
    "cto": ["staff-engineer", "senior-engineer", "code-reviewer"],
    "staff-engineer": ["design-reviewer", "senior-engineer", "code-reviewer"],
}


def main() -> None:
    try:
        event = json.load(sys.stdin)
    except json.JSONDecodeError:
        return
    if event.get("tool_name") not in AGENT_TOOLS:
        return
    allowed = MAY_SPAWN.get(event.get("agent_type") or "")
    if allowed is None:
        return
    requested = str((event.get("tool_input") or {}).get("subagent_type") or "").strip().lower()
    if requested not in allowed:
        print(
            f"Blocked: {event['agent_type']} may spawn only {', '.join(allowed)} "
            f"(the org chart in CLAUDE.md), not '{requested or 'the default agent'}'. "
            "Name one of those, or report the need up the chain.",
            file=sys.stderr,
        )
        sys.exit(2)


if __name__ == "__main__":
    main()
