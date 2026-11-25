#!/usr/bin/env python3
"""PreToolUse hook for Bash: approves two exact git forms in a product
worktree: one merge of origin/main into it, and one push of its task or
workstream branch. Both are on for company.json's products; the founder turns
one off with "merge": false or "push": false in its integrations
"auto_approve". With no products, nothing is approved.

A Staff engineer brings a branch up to date with `main` before its landing.
The auto-mode check may refuse that merge, and a refusal is final for the
order. A rule like `Bash(git -C * merge --no-edit -m * origin/main)`
can't express this safely: its `*` also spans spaces, so it would approve
`-m "x" -s ours origin/main`. This hook approves only:

    git -C <repo>/workspaces/<product>/.worktrees/<id> merge --no-edit -m "<message>" origin/main

- <repo> is this repo's absolute path (the folder above scripts/hooks/);
  <product> and <id> are single path parts of letters, digits and _ . -
  that don't start with a dot;
- the path is a linked worktree (its .git is a file, not a folder), and
  doesn't lead out of workspaces/<product>/.worktrees/ through a symlink;
- workspaces/<product>/ is the folder of the `workspace` of one of
  company.json's products;
- the message sits in double quotes, is non-empty, and uses only letters,
  digits, spaces and _ . / @ : = + , % ^ ~ # - (no quotes, $, `, \\, ;, &,
  |, <, >, parentheses or newlines, so the shell can't expand or end it);
- single spaces between the words, and nothing before or after the command
  (no other flag, ref, chained command or redirection).

The same check may refuse the push of a reviewed task branch, and each
refused push would wait on the Board. A rule like
`Bash(git -C * push origin task/*)` would also approve
`push origin task/x main` or `task/x:main`. This hook approves only:

    git -C <worktree> push [-u] origin <branch>

- the caller is an engineering role that pushes: the hook input's
  `agent_type` is `senior-engineer`, `staff-engineer` or `cto`;
- <worktree> passes the first two path checks above, and git says it is a linked
  worktree of its repo: its git dir differs from the repo's common dir,
  whose `git worktree list` names that path (so not a repo made with
  `git init --separate-git-dir`);
- the remote is `origin`, and <branch> is `task/<name>`, `ws/<name>`,
  `HEAD:task/<name>` or `HEAD:ws/<name>`, the name made of parts of
  letters, digits and _ . - that don't start with a dot, joined by /
  (no `+`, `:` elsewhere, `*`, `^`, `~` or `@`);
- single spaces, nothing before or after (so no --force, --delete,
  --mirror, --all, --tags, other refs, chained command or redirection);
- git, asked in that worktree, says: its HEAD is that branch (the
  worktree's own branch); for the bare form, the name resolves to
  refs/heads/<branch> and nothing else (not a tag or another ref of that
  name);
- the push goes to origin alone: git's config holds one remote.origin.url,
  the ssh form of a product's `repo` in company.json, and
  `git remote get-url --push --all origin` prints that same URL alone; the
  repo has no legacy <common dir>/remotes/origin or branches/origin file
  (git reads origin, with its own Push lines, from those when config has
  no URL); and git's config, every scope, sets none of these, at any value:
  remote.origin.push, .pushurl, .mirror, .vcs and .receivepack;
  push.default (`upstream` sends a bare <branch> to its upstream, main for
  a branch made from origin/main), push.followTags, push.pushOption and
  push.recurseSubmodules; submodule.recurse; core.sshCommand;
  url.<base>.insteadOf and .pushInsteadOf. Each can send the push to
  another ref, URL, repo or program, add tags or submodule pushes to it, or
  hand the server options. Keys that pick a remote only when none is named
  (remote.pushDefault, branch.<name>.pushRemote and .remote), and
  branch.<name>.merge, which acts only through push.default, aren't checked.

Each git call gets 1 s, and at most 7 run, so the hook ends within its 10 s
timeout. Any git error, timeout or missing git gives no decision. With
`HEAD:<branch>`, git matches the name against origin's refs: if origin has
only a tag of that name, git refuses the push (the tag already exists). A
new product's merges and pushes go to the normal check until company.json
names it.

Anything else gets no decision (exit 0, no output), so the normal permission
rules and the auto-mode check apply.
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
PART = r"[A-Za-z0-9_-][A-Za-z0-9_.-]*"
MESSAGE = r"[A-Za-z0-9 _./@:=+,%^~#-]+"
WORKTREE = r"(?P<path>" + re.escape(str(REPO)) + r"/workspaces/" + PART + r"/\.worktrees/" + PART + r")"
MERGE = re.compile(r"git -C " + WORKTREE + r' merge --no-edit -m "' + MESSAGE + r'" origin/main')
PUSHERS = {"senior-engineer", "staff-engineer", "cto"}
PUSH = re.compile(
    r"git -C " + WORKTREE + r" push (?:-u )?origin (?P<head>HEAD:)?(?P<branch>(?:task|ws)/" + PART + r"(?:/" + PART + r")*)"
)
REDIRECTS = (
    r"^(remote\.origin\.(push|pushurl|mirror|vcs|receivepack)|push\.(default|followtags|pushoption|recursesubmodules)"
    r"|submodule\.recurse"
    r"|core\.sshcommand|url\..*\.(insteadof|pushinsteadof))$"
)


def worktree(path: str) -> bool:
    real = Path(os.path.realpath(path))
    return real.parent.name == ".worktrees" and real.parent.parent.parent == REPO / "workspaces" and (Path(path) / ".git").is_file()


def approvable(command: str) -> bool:
    match = MERGE.fullmatch(command)
    return bool(match) and worktree(match["path"]) and listed(match["path"])


def git(path: str, *args: str) -> "subprocess.CompletedProcess[str] | None":
    try:
        return subprocess.run(["git", "-C", path, *args], capture_output=True, text=True, timeout=1)
    except (OSError, subprocess.SubprocessError):
        return None


def lines(path: str, *args: str) -> "list[str] | None":
    result = git(path, *args)
    return result.stdout.splitlines() if result and result.returncode == 0 else None


def common_dir(path: str) -> "str | None":
    """The repo's common dir, if <path> is a linked worktree that the repo lists."""
    dirs = lines(path, "rev-parse", "--path-format=absolute", "--git-dir", "--git-common-dir")
    if not dirs or len(dirs) != 2 or os.path.realpath(dirs[0]) == os.path.realpath(dirs[1]):
        return None
    listed = lines(dirs[1], "worktree", "list", "--porcelain") or []
    if os.path.realpath(path) not in {os.path.realpath(line[9:]) for line in listed if line.startswith("worktree ")}:
        return None
    return dirs[1]


def own_branch(path: str, branch: str, bare: bool) -> bool:
    if lines(path, "symbolic-ref", "-q", "HEAD") != [f"refs/heads/{branch}"]:
        return False
    return not bare or lines(path, "rev-parse", "--symbolic-full-name", branch) == [f"refs/heads/{branch}"]


def products(form: str, key: str) -> set:
    """Each product's key in company.json; none where its integrations "auto_approve" sets form to anything but true, or
    it can't be read."""
    try:
        import company_config
        settings = company_config.load()
        if settings["integrations"].get("auto_approve", {}).get(form, True) is not True:
            return set()
        return {str(product[key]) for product in settings["products"].values()}
    except (OSError, ValueError, AttributeError, KeyError, TypeError, ImportError):
        return set()


def listed(path: str) -> bool:
    """Whether the worktree is in the folder of a product's workspace."""
    folder = Path(os.path.realpath(path)).parent.parent
    return any((REPO / workspace).parent == folder for workspace in products("merge", "workspace"))


def origins() -> set:
    """Each product's origin. Ssh only: an https origin could go through http.proxy."""
    return {f"git@github.com:{repo}.git" for repo in products("push", "repo")}


def goes_to_origin(path: str, common: str) -> bool:
    if any(os.path.lexists(os.path.join(common, legacy, "origin")) for legacy in ("remotes", "branches")):
        return False
    redirects = git(path, "config", "--get-regexp", REDIRECTS)
    if not redirects or redirects.returncode != 1 or redirects.stdout.strip():
        return False
    urls = lines(path, "config", "--get-all", "remote.origin.url")
    return bool(urls) and len(urls) == 1 and urls[0] in origins() and lines(path, "remote", "get-url", "--push", "--all", "origin") == urls


def push_approvable(command: str) -> bool:
    match = PUSH.fullmatch(command)
    if not match or not worktree(match["path"]):
        return False
    path = match["path"]
    common = common_dir(path)
    return bool(common) and own_branch(path, match["branch"], bare=not match["head"]) and goes_to_origin(path, common)


def main() -> None:
    try:
        event = json.load(sys.stdin)
    except json.JSONDecodeError:
        return
    if event.get("tool_name") != "Bash":
        return
    command = (event.get("tool_input") or {}).get("command")
    if not isinstance(command, str):
        return
    command = command.strip()
    if approvable(command):
        reason = "merge of origin/main into a worktree (scripts/hooks/approve_worktree_merge.py)"
    elif event.get("agent_type") in PUSHERS and push_approvable(command):
        reason = "push of a task or ws branch from a worktree (scripts/hooks/approve_worktree_merge.py)"
    else:
        return
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "allow",
        "permissionDecisionReason": reason,
    }}))


if __name__ == "__main__":
    main()
