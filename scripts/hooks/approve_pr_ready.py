#!/usr/bin/env python3
"""PreToolUse hook for Bash: approves marking one reviewed pull request ready.
It is on for company.json's products; the founder turns it off with
"pr_ready": false in its integrations "auto_approve".

A Staff engineer or the CTO marks a draft ready once its review has passed.
Claude Code's auto-mode check may refuse that, and a refusal is final for the
order, so the landing would wait on the Board. A rule like
`Bash(gh pr ready * --repo <repo>)` can't express this safely: its `*` also
spans spaces, so it would approve `gh pr ready --undo 12 --repo <repo>`, and
a rule can't name a role. This hook approves only:

    gh pr ready <number> --repo <owner>/<name>

- the caller is a role that lands: the hook input's `agent_type` is
  `staff-engineer` or `cto` (Claude Code sets it, for a subagent or a
  `--agent` session; a plain session has none, so it gets no approval);
- <number> is a bare PR number: ASCII digits, no leading zero;
- <owner>/<name> is the `repo` of one of company.json's products, as written
  there; with no products, nothing is approved;
- single spaces, and nothing before or after the command (no other flag,
  chained command, redirection or variable, not even a trailing space).

The hook sees the command, not the review. `staff-engineer.md` says when it
may run: only after the APPROVED verdict, since a draft is GitHub's only stop
on an unreviewed green PR.

Anything else gets no output, no decision, so the normal permission rules and
the auto-mode check apply.
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

LANDING_ROLES = {"staff-engineer", "cto"}
READY = re.compile(r"gh pr ready [1-9][0-9]* --repo ([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)")


def product_repos() -> set:
    """The `owner/name` of each product in company.json; none where its integrations "auto_approve" sets "pr_ready" to
    anything but true, or it can't be read."""
    try:
        import company_config
        settings = company_config.load()
        if settings["integrations"].get("auto_approve", {}).get("pr_ready", True) is not True:
            return set()
        return {product["repo"] for product in settings["products"].values()}
    except (OSError, ValueError, AttributeError, KeyError, TypeError, ImportError):
        return set()


def main() -> None:
    try:
        event = json.load(sys.stdin)
    except json.JSONDecodeError:
        return
    if event.get("tool_name") != "Bash" or event.get("agent_type") not in LANDING_ROLES:
        return
    command = (event.get("tool_input") or {}).get("command")
    match = READY.fullmatch(command) if isinstance(command, str) else None
    if match and match[1] in product_repos():
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
            "permissionDecisionReason": "the exact gh pr ready form, by a role that lands (scripts/hooks/approve_pr_ready.py)",
        }}))


if __name__ == "__main__":
    main()
