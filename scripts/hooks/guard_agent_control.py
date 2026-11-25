#!/usr/bin/env python3
"""PreToolUse hook for SendMessage and TaskStop.

An agent session (the hook input has `agent_type`: a subagent, or a `--agent` main session such
as the CEO) may message only an agent it spawned itself, which keeps orders one level at a time, and
may stop only agents in its own tree (its children, theirs, and so on), because stopping a parent
doesn't stop its background children, so "stop now" goes leaves first. An
injected instruction can't reach another session either way. The check: the target's
`<session>/subagents/agent-<id>.meta.json` names the Agent tool call that started it
(`toolUseId`), and that call must be in the caller's own transcript (the main transcript for the
main session, `subagents/agent-<caller id>.jsonl` for a subagent); for a stop, the same holds for
the target's ancestor (`parentAgentId`) that the caller spawned.

`to: "main"` always reaches the main session, so only a child of the main
session may use it, to message its launcher (a Senior or producer only with the line below). Any agent may
also message its own launcher (its meta's `parentAgentId`, whose own transcript holds the Agent call that
started it) with one line of at most 1,000 characters that starts NEEDS, QUESTION or BLOCKED: it wakes a
launcher parked on other children within seconds.
Names, cross-session addresses, teammates and `notify_when_idle` are refused for agent sessions.
A plain session (no `agent_type`) isn't limited. Anything unreadable blocks (exit 2, reason on stderr).
"""

import json
import re
import sys
from pathlib import Path

TOOLS = {"SendMessage", "TaskStop"}
AGENT_TOOLS = {"Agent", "Task"}
AGENT_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
# A refused TaskStop lists at most SHOWN of the caller's agents, each in LABEL bytes: a long session holds well
# over a thousand, and listing them all would fill the caller's context.
SHOWN, LABEL = 20, 120
UPWARD = re.compile(r"(NEEDS|QUESTION|BLOCKED)\b")
UPWARD_KEYS = {"to", "recipient", "recipient_kind", "type", "message", "summary", "content"}
# The roles that hold SendMessage only for the upward line: started by a main
# session (`claude --agent cto`, a plain session), they message it with that line only, never other text.
UPWARD_ONLY = {"senior-engineer", "content-producer"}


def upward_line(tool_input: dict) -> bool:
    """A plain message (no other `type` or field) of one line, at most 1,000 characters, that starts NEEDS, QUESTION
    or BLOCKED (leading spaces aside). Only `message` reaches the recipient: `summary` doesn't, and `content` is
    Claude Code's own copy of it, cut to about 50 characters and ending in "…"; any other
    `content`, and a `summary` that isn't one line of at most 100 characters, is refused, in case a build shows it."""
    message, content, summary = tool_input.get("message"), tool_input.get("content"), tool_input.get("summary")
    if set(tool_input) - UPWARD_KEYS or tool_input.get("type") not in (None, "message"):
        return False
    if not isinstance(message, str) or len(message) > 1000:
        return False
    if summary is not None and (not isinstance(summary, str) or len(summary) > 100 or len(summary.splitlines()) > 1):
        return False
    if content is not None and content != message and not (
            isinstance(content, str) and content.endswith("…") and message.startswith(content[:-1])):
        return False
    text = message.strip(" ")
    return len(text.splitlines()) == 1 and bool(UPWARD.match(text))


def block(reason: str) -> None:
    print(f"Blocked (guard_agent_control): {reason}", file=sys.stderr)
    sys.exit(2)


def shown(value) -> str:
    """A value the refusal echoes (the target, the caller's type, an error), cut to LABEL bytes, so the whole refusal
    stays under 4,096 bytes for any input."""
    text = str(value)
    cut = text.encode()[:LABEL].decode("utf-8", "ignore")
    return text if cut == text else cut + "…"


_AGENT_CALLS: dict = {}


def agent_calls(transcript: Path) -> set:
    """The ids of the Agent (or Task) tool calls in the transcript's assistant messages, read once per run: a refused
    TaskStop checks every agent of the session against it, and one read per agent of a long transcript would time the
    hook out."""
    key = str(transcript)
    if key not in _AGENT_CALLS:
        ids = set()
        with open(transcript, encoding="utf-8", errors="replace") as lines:
            for line in lines:
                if '"tool_use"' not in line:
                    continue
                try:
                    message = json.loads(line).get("message") or {}
                except json.JSONDecodeError:
                    continue
                if message.get("role") != "assistant":
                    continue
                content = message.get("content")
                for item in content if isinstance(content, list) else []:
                    if isinstance(item, dict) and item.get("type") == "tool_use" and item.get("name") in AGENT_TOOLS:
                        ids.add(item.get("id"))
        _AGENT_CALLS[key] = ids
    return _AGENT_CALLS[key]


def spawned_in(transcript: Path, tool_use_id: str) -> bool:
    """True if the transcript holds an Agent (or Task) tool call with this id."""
    return tool_use_id in agent_calls(transcript)


def meta(session_dir: Path, agent_id: str) -> dict:
    return json.loads((session_dir / "subagents" / f"agent-{agent_id}.meta.json").read_text(encoding="utf-8"))


def own_tree(session_dir: Path, own: Path, caller_id) -> list:
    """The caller's agents (its children, theirs, and so on) whose meta file doesn't say `finished`, most recently
    active first (by their transcript's last write), as (depth, 'id (type: description)'). The hook can't tell which
    of them still run: an agent a restart killed never gets `finished`."""
    metas = {}
    for path in (session_dir / "subagents").glob("agent-*.meta.json"):
        try:
            metas[path.name[len("agent-"):-len(".meta.json")]] = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
    level = [a for a, m in metas.items() if a != caller_id and spawned_in(own, str(m.get("toolUseId") or "-"))]
    tree, seen, depth = [], set(level), 0
    while level:
        tree += [(depth, a) for a in level]
        level = [a for a, m in metas.items() if m.get("parentAgentId") in level and a not in seen]
        seen.update(level)
        depth += 1

    def active(agent: str) -> float:
        for name in (f"agent-{agent}.jsonl", f"agent-{agent}.meta.json"):
            try:
                return (session_dir / "subagents" / name).stat().st_mtime
            except OSError:
                continue
        return 0.0

    tree = sorted((e for e in tree if metas[e[1]].get("finished") is not True), key=lambda e: active(e[1]), reverse=True)
    return [(d, f"{a} ({metas[a].get('agentType')}: {metas[a].get('description')})".encode()[:LABEL]
             .decode("utf-8", "ignore")) for d, a in tree]


def check(event: dict) -> None:
    caller_type, caller_id = event.get("agent_type"), event.get("agent_id")
    if not caller_type:
        return  # a plain session isn't limited
    tool_input = event.get("tool_input") or {}
    if tool_input.get("notify_when_idle"):
        block("notify_when_idle is for plain sessions only; agent sessions message their own children.")
    if caller_id is not None and not AGENT_ID.match(str(caller_id)):
        block("the caller's agent ID is malformed.")
    if event["tool_name"] == "SendMessage":
        names, kind = [tool_input.get("to"), tool_input.get("recipient")], tool_input.get("recipient_kind")
    else:
        names, kind = [tool_input.get("task_id"), tool_input.get("shell_id")], None
    names = {str(n).strip() for n in names if n}
    if len(names) != 1:
        block("give exactly one target (to and recipient, or task_id and shell_id, must agree).")
    target = names.pop()
    transcript = Path(event["transcript_path"])
    session_dir = transcript.with_suffix("")
    if transcript.parent.name == "subagents":  # in case a subagent's own path is ever passed
        session_dir = transcript.parent.parent
    own = session_dir / "subagents" / f"agent-{caller_id}.jsonl" if caller_id else session_dir.parent / f"{session_dir.name}.jsonl"

    if target == "main" and event["tool_name"] == "SendMessage" and kind in (None, "main"):
        if caller_id:
            caller = meta(session_dir, caller_id)
            if not caller.get("parentAgentId") and spawned_in(transcript, str(caller.get("toolUseId") or "-")):
                if caller_type not in UPWARD_ONLY:
                    return  # a child of the main session messages its launcher
                if upward_line(tool_input):
                    return  # one urgent line, the only message these roles send
                block(f"a {shown(caller_type)} messages its launcher only with one line of at most 1,000 characters "
                      "starting NEEDS, QUESTION or BLOCKED (a summary, if any, one line of at most 100). Anything else "
                      "goes in your report or ceo-questions.md.")
        block("'main' is the main session; only an agent the main session started may message it. "
              "Report to your own launcher in your final message, or in ceo-questions.md.")
    def refuse(why: str) -> None:
        if event["tool_name"] == "TaskStop":
            tree = own_tree(session_dir, own, caller_id)
            listed = [label for _, label in sorted(tree[:SHOWN], key=lambda e: -e[0])]  # newest first within a depth
            rest = f"; and {len(tree) - SHOWN} less recently active" if len(tree) > SHOWN else ""
            why += (f" Your agents not marked finished, the {SHOWN} most recently active at most, leaves first (stop "
                    f"them in this order): {'; '.join(listed) if listed else 'none'}{rest}.")
        block(why)

    if kind not in (None, "agent") or not AGENT_ID.match(target):
        refuse(f"'{shown(target)}' isn't an agent ID. Agent sessions address only agents they spawned, by the ID the "
               "Agent result gave: no names, other sessions or teammates.")
    if event["tool_name"] == "SendMessage" and caller_id and upward_line(tool_input):
        try:  # the launcher named by the caller's meta, whose own transcript holds the Agent call that started it
            caller = meta(session_dir, caller_id)
            launcher = caller.get("parentAgentId")
            if target == launcher and spawned_in(session_dir / "subagents" / f"agent-{launcher}.jsonl",
                                                 str(caller.get("toolUseId") or "-")):
                return  # one urgent line to the caller's own launcher
        except FileNotFoundError:
            pass  # no record of the caller or its launcher: the checks below decide, as before
    try:
        agent = meta(session_dir, target)
    except FileNotFoundError:
        refuse(f"'{shown(target)}' isn't an agent of this session. Agent sessions address only agents they spawned.")
    seen = {target}
    while not spawned_in(own, str(agent.get("toolUseId") or "-")):
        parent = agent.get("parentAgentId")
        if event["tool_name"] != "TaskStop" or not parent or parent in seen or not AGENT_ID.match(parent):
            refuse(f"'{shown(target)}' wasn't spawned by you ({shown(caller_type)}). Message only your own children "
                   "(and your own launcher with one line starting NEEDS, QUESTION or BLOCKED, a summary of at most 100 "
                   "characters), and stop only agents in your own tree; anything else goes up the chain in your report "
                   "or ceo-questions.md.")
        seen.add(parent)
        agent = meta(session_dir, parent)


def main() -> None:
    try:
        event = json.load(sys.stdin)
        if event.get("tool_name") not in TOOLS:
            return
        check(event)
    except SystemExit:
        raise
    except Exception as exc:  # fail closed: unreadable input, a missing transcript or meta file
        block(f"couldn't check the target ({type(exc).__name__}: {shown(exc)}).")


if __name__ == "__main__":
    main()
