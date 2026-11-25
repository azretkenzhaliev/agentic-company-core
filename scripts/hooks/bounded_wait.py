"""An engineering agent's Bash wait with no time bound is refused.

cto.md, Working rules, "Wait in the foreground", gives the one wait form, bounded:
`until [ -e <rc> ] || [ $SECONDS -ge 170 ]; do sleep 5; done`. An unbounded one runs on after its step, keeps the
agent's result open and loses its report, and TaskStop can't end it, since it isn't an agent.

A wait is a `while` or `until` loop that sleeps (`sleep` in its test or its body); it is bounded when its test names
SECONDS (`$SECONDS`, `${SECONDS}`, `(( SECONDS < 170 ))`). Each loop counts, one inside another too, since an inner
loop that never ends holds the outer one. A loop is read from its keyword (a whole word, at the start or after a
space, a separator, a quote or a parenthesis) to its first `; do` or newline `do` and its own `done` (each `do` and
`done` after a separator counted, so a nested loop's `done` doesn't end it; one with no `done` isn't a loop), in
the command's text as typed, quotes included, so one inside `bash -c '...'` counts. A loop that ends by itself isn't a
wait: one that doesn't sleep (`while read line; do ...; done`), a `for` loop, a watch command such as
`gh pr checks --watch`. A bound anywhere but the test (a count, a `break` in the body, `timeout`) is refused too:
write SECONDS into the test.

Engineering agents only (ENGINEERING, by agent_type; the main session and other roles keep theirs). guard_marketing_tools.py
calls wait_reason for every subagent's Bash call: its settings entry runs in every session and fails closed. The
refusal asks for the bounded form; it grants nothing.
"""

import re

ENGINEERING = {"cto", "staff-engineer", "senior-engineer", "code-reviewer", "design-reviewer", "ux-expert"}
KEYWORD = re.compile(r"(?:^|(?<=[\s;&|(){}'\"`!]))(while|until)(?=\s)")
HEAD = re.compile(r"(while|until)\s(?P<test>.*?)[;\n]\s*do(?![\w-])", re.S)
DO_DONE = re.compile(r"[;\n&]\s*(do|done)(?![\w-])")  # where a command starts, as the shell reads them
SLEEP = re.compile(r"(?<![\w-])sleep(?![\w-])")
BOUND = re.compile(r"(?<!\w)SECONDS(?!\w)")

MESSAGE = (
    "Blocked: a wait with no time bound (scripts/hooks/bounded_wait.py; cto.md, Working rules, \"Wait in the "
    "foreground\"): this `{keyword}` loop sleeps, and its test never reads $SECONDS, so it can run on after your step, "
    "keep your result open and lose your report. Put the bound in the test and keep each call under 3 minutes, with "
    "timeout: 175000: `until <your test> || [ $SECONDS -ge 170 ]; do sleep 5; done`, for a long command "
    "`until [ -e <rc> ] || [ $SECONDS -ge 170 ]; do sleep 5; done; cat <rc> 2>/dev/null || echo running`. "
    "Then run that bounded form: this stop asks for it, and isn't a permission refusal."
)


def unbounded(command: str) -> "str | None":
    """The keyword of the first loop in command that sleeps with no SECONDS in its test, or None."""
    for start in KEYWORD.finditer(command):
        head = HEAD.match(command, start.start())
        if not head:
            continue
        depth = 1
        for token in DO_DONE.finditer(command, head.end()):  # its body ends at its own `done`, past nested loops'
            depth += 1 if token[1] == "do" else -1
            if not depth:
                body = command[head.end():token.start()]
                if (SLEEP.search(head["test"]) or SLEEP.search(body)) and not BOUND.search(head["test"]):
                    return head[1]
                break
    return None


def wait_reason(event: dict) -> "str | None":
    """Why this Bash call may not run, or None. Only an engineering subagent's unbounded wait is refused."""
    if event.get("tool_name") != "Bash" or not event.get("agent_id"):
        return None
    if (event.get("agent_type") or "") not in ENGINEERING:
        return None
    keyword = unbounded(str((event.get("tool_input") or {}).get("command") or ""))
    return MESSAGE.format(keyword=keyword) if keyword else None
