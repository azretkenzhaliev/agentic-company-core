"""A subagent's Bash call with run_in_background is refused.

cto.md, Working rules, "Wait in the foreground": "Never use `run_in_background`." Every engineering agent points there.
A command an agent leaves in the background keeps its result open, so its report is lost.

A subagent is a hook input with agent_id. The main session has none, the CEO included, and keeps its background
watchers by design. No agent's file allows run_in_background, so there is no exception: a script that needs a server
starts it detached (nohup) in a foreground call.

guard_marketing_tools.py calls background_reason for every Bash call, whatever is configured: its settings entry runs
in every session and fails closed.
"""

MESSAGE = (
    "Blocked: subagents never use run_in_background (cto.md, Working rules, \"Wait in the foreground\"; "
    "scripts/hooks/background_bash.py): a command left in the background keeps your result open, and your report is "
    "lost. Run it in the foreground, its exit code written last: `<command> > <log> 2>&1; echo $? > <rc>`. If Claude "
    "Code moves it to the background after 180 s, don't end your turn: repeat this one Bash call, with "
    "timeout: 175000, until it prints the exit code, then read <log>: "
    "`until [ -e <rc> ] || [ $SECONDS -ge 170 ]; do sleep 5; done; cat <rc> 2>/dev/null || echo running`."
)


def background_reason(event: dict) -> "str | None":
    """Why this Bash call may not run, or None. Only a subagent's call with run_in_background set is refused."""
    if event.get("tool_name") != "Bash" or not event.get("agent_id"):
        return None
    tool_input = event.get("tool_input") or {}
    if tool_input.get("run_in_background") in (None, False):
        return None
    return MESSAGE
