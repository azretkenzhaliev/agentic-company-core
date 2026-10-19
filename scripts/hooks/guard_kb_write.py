#!/usr/bin/env python3
"""PreToolUse hook for Write, Edit and MultiEdit.

Blocks (exit 2, reason on stderr) when:
- the new text for a file under knowledge/ contains a secret;
- the analyst writes anywhere outside knowledge/research/.

Everything else is allowed (exit 0). The project root is $CLAUDE_PROJECT_DIR,
falling back to this script's location.
"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from kb_secrets import find_secrets  # noqa: E402

WRITE_TOOLS = {"Write", "Edit", "MultiEdit"}


def new_text(tool_name: str, tool_input: dict) -> str:
    if tool_name == "Write":
        return tool_input.get("content", "")
    if tool_name == "Edit":
        return tool_input.get("new_string", "")
    return "\n".join(edit.get("new_string", "") for edit in tool_input.get("edits", []))


def is_under(path: Path, folder: Path) -> bool:
    return path == folder or folder in path.parents


def block(reason: str) -> None:
    print(reason, file=sys.stderr)
    sys.exit(2)


def main() -> None:
    try:
        event = json.load(sys.stdin)
    except json.JSONDecodeError:
        return
    tool_name = event.get("tool_name")
    if tool_name not in WRITE_TOOLS:
        return
    tool_input = event.get("tool_input") or {}

    root = Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path(__file__).resolve().parents[2]).resolve()
    path = Path(tool_input.get("file_path", ""))
    if not path.is_absolute():
        path = Path(event.get("cwd") or root) / path
    path = path.resolve()
    knowledge = root / "knowledge"

    if event.get("agent_type") == "analyst" and not is_under(path, knowledge / "research"):
        block("Blocked: the analyst may write only under knowledge/research/. Report the finding to the CEO instead.")

    if is_under(path, knowledge):
        hits = find_secrets(new_text(tool_name, tool_input))
        if hits:
            found = ", ".join(f"{kind} (line {line} of the new text)" for line, kind in hits)
            block(
                f"Blocked: possible secret in a knowledge-base write: {found}. "
                "Never write secrets into the KB; write where the secret lives instead "
                "(e.g. 'env var X in the hosting dashboard')."
            )


if __name__ == "__main__":
    main()
