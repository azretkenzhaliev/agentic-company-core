#!/usr/bin/env python3
"""Print a subagent's last report from its transcript.

Claude Code delivers one report per result: an agent that hands back (SubagentHandback) again in the same result is
refused, and that report never reaches its manager. The notice about an agent names its `<output-file>`, which is the
agent's transcript. This prints one line saying whether the last SubagentHandback call in it was delivered, refused or
has no answer yet, then that call's message. Nothing else from the transcript is printed: it can hold anything the
agent read.

Usage: python3 scripts/last_handback.py <output-file>
Exit code: 0 when a call was found, 1 when there is none.
"""

import json
import sys


def _text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(x.get("text", "") for x in content if isinstance(x, dict))
    return ""


def last_handback(lines):
    """(status, message) of the last SubagentHandback call in transcript lines, or None."""
    calls, last = {}, None
    for line in lines:
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if not isinstance(record, dict) or record.get("type") not in ("assistant", "user"):
            continue  # api-request-blob records repeat earlier calls after their answers
        message = record.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_use" and block.get("name") == "SubagentHandback":
                last = block.get("id")
                calls.setdefault(last, ["no answer yet", str((block.get("input") or {}).get("message", ""))])
            elif block.get("type") == "tool_result" and block.get("tool_use_id") in calls:
                try:
                    ok = json.loads(_text(block.get("content"))).get("success")
                except (ValueError, AttributeError):
                    ok = None
                calls[block["tool_use_id"]][0] = "delivered" if ok is True else "refused"
    return tuple(calls[last]) if last else None


def main(argv):
    if len(argv) != 2:
        print("usage: python3 scripts/last_handback.py <output-file>", file=sys.stderr)
        return 2
    with open(argv[1], errors="replace") as transcript:
        found = last_handback(transcript)
    if not found:
        print("no SubagentHandback call in this transcript")
        return 1
    status, message = found
    print("last hand-back: " + status)
    print(message)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
