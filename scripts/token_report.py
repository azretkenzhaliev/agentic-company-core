#!/usr/bin/env python3
"""What the work cost and how it landed, for /report.

Since a given time, it prints:
- from a session's subagent transcripts, each role's turns, mean context and weighted share;
- from gh, for each product repo in company.json, its failed `staging` and `production` runs, and its merged PRs that
  read as a follow-up fix (with no repo there, or a company.json that can't be read, it says so and goes on);
- the machine's load.

It changes nothing. It calls GitHub only through `gh`, with read commands, as whoever `gh` is logged in as.

Nothing from a transcript's text reaches the output, and that's the rule the code is built around: from a transcript
line it takes the message id, the model, the usage numbers and the time; from a .meta.json only `agentType`, and only if
it has the shape of a role's name (otherwise it counts as `other`). A line it can't read is skipped unprinted. From gh it
prints numbers only: run ids and PR numbers, never a title, a body or gh's own error text.

The shares are ratios, not bills. Token classes use Anthropic's list ratios (MULTIPLIER). The models use
what Claude Code's own cost records imply (BASE, backed out of `lastModelUsage` in ~/.claude.json): not a published
price. How the subscription counts tokens is unknown.

"Needed a follow-up fix" is read from words, so it's approximate: a merged PR counts as a follow-up if its title or
branch says follow-up, fix-forward, hotfix or revert, or its title says fix and names a `#N`. The `#N`s in its title or
body are the PRs it followed.
"""

import argparse
import json
import os
import re
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import company_config  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
DEPLOY_WORKFLOWS = ("staging", "production")
FAILED = {"failure", "timed_out", "startup_failure"}
GH_LIMIT = 500
GH_TIMEOUT = 60

# Ratios only. See the docstring for where they come from.
BASE = {"opus": 2.5, "sonnet": 1.25, "haiku": 0.16}
UNKNOWN_MODEL = BASE["opus"]  # a model with no price counts at the dearest, so a share is never understated
MULTIPLIER = {"input": 1.0, "cache_read": 0.1, "cache_write_5m": 1.25, "cache_write_1h": 2.0, "output": 5.0}

ROLE = re.compile(r"[a-z0-9][a-z0-9:_-]{0,40}")
FOLLOW_UP = re.compile(r"(?i)\b(follow[- _]?up|fix[- _]?forward|hotfix|revert)")
FIX_NAMING_PR = re.compile(r"(?i)\bfix(es|ed)?\b.*#\d")
PR_NUMBER = re.compile(r"#(\d+)")


def parse_time(text: str) -> datetime:
    """An ISO date or time; with no zone it's UTC."""
    moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def projects_root(repo: "Path | None" = None) -> Path:
    config = os.environ.get("CLAUDE_CONFIG_DIR")
    base = Path(config).expanduser() if config else Path.home() / ".claude"
    return base / "projects" / re.sub(r"[^A-Za-z0-9]", "-", str(repo or REPO_ROOT))


def find_session(name) -> Path:
    """The folder named, the session id named, or the session that last started an agent."""
    if name:
        session = Path(name) if Path(name).is_dir() else projects_root() / name
        if not (session / "subagents").is_dir():  # a typo must not read as no spend
            raise FileNotFoundError(f"no subagent transcripts in {session}")
        return session
    sessions = list(projects_root().glob("*/subagents"))
    if not sessions:
        raise FileNotFoundError(f"no subagent transcripts under {projects_root()}: pass --session")
    return max(sessions, key=lambda folder: folder.stat().st_mtime).parent


def role_of(transcript: Path) -> str:
    try:
        agent_type = json.loads(transcript.with_suffix(".meta.json").read_text(encoding="utf-8")).get("agentType")
    except (OSError, ValueError, AttributeError):
        return "unknown"
    return agent_type if isinstance(agent_type, str) and ROLE.fullmatch(agent_type) else "other"


def tokens(usage: dict, key: str) -> int:
    value = usage.get(key)
    return value if isinstance(value, int) else 0


def context_of(usage: dict) -> int:
    return sum(tokens(usage, key) for key in ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"))


def weight(model, usage: dict) -> float:
    family = next((BASE[name] for name in BASE if name in str(model)), UNKNOWN_MODEL)
    written = tokens(usage, "cache_creation_input_tokens")
    details = usage.get("cache_creation")
    written_1h = tokens(details, "ephemeral_1h_input_tokens") if isinstance(details, dict) else 0
    return family * (tokens(usage, "input_tokens") * MULTIPLIER["input"]
                     + tokens(usage, "cache_read_input_tokens") * MULTIPLIER["cache_read"]
                     + (written - written_1h) * MULTIPLIER["cache_write_5m"]
                     + written_1h * MULTIPLIER["cache_write_1h"]
                     + tokens(usage, "output_tokens") * MULTIPLIER["output"])


def read_turns(transcript: Path, role: str, since: datetime, turns: dict) -> None:
    """Adds this transcript's turns to `turns`, by message id. A message spans several lines; the last count stands."""
    with transcript.open("rb") as lines:
        for line in lines:
            if b'"usage"' not in line:  # most of the bytes are tool output; don't parse what can't count
                continue
            try:
                record = json.loads(line)
                message = record["message"]
                message_id, usage = message["id"], message["usage"]
                if record["type"] != "assistant" or parse_time(record["timestamp"]) < since:
                    continue
            except (ValueError, KeyError, TypeError, AttributeError):
                continue
            if not isinstance(usage, dict) or not (context_of(usage) or tokens(usage, "output_tokens")):
                continue
            earlier = turns.get(message_id)
            if earlier is None or tokens(usage, "output_tokens") >= tokens(earlier[2], "output_tokens"):
                turns[message_id] = (role, message.get("model"), usage)


def role_rows(session: Path, since: datetime) -> list:
    """(role, turns, mean context, share %), the largest share first."""
    turns = {}
    for transcript in sorted((session / "subagents").glob("*.jsonl")):
        if transcript.stat().st_mtime >= since.timestamp():
            read_turns(transcript, role_of(transcript), since, turns)
    counts, contexts, weights = defaultdict(int), defaultdict(int), defaultdict(float)
    for role, model, usage in turns.values():
        counts[role] += 1
        contexts[role] += context_of(usage)
        weights[role] += weight(model, usage)
    total = sum(weights.values()) or 1.0
    rows = [(role, counts[role], contexts[role] // counts[role], 100 * weights[role] / total) for role in counts]
    return sorted(rows, key=lambda row: -row[3])


def gh_json(*arguments):
    """gh's JSON list, or None if gh couldn't give one. gh's own text is never printed."""
    try:
        done = subprocess.run(["gh", *arguments], capture_output=True, text=True, timeout=GH_TIMEOUT)
        answer = json.loads(done.stdout) if done.returncode == 0 else None
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    return answer if isinstance(answer, list) else None


def after(item: dict, key: str, since: datetime) -> bool:
    try:
        return parse_time(item[key]) >= since
    except (KeyError, TypeError, ValueError):
        return False


def hit_limit(items: list) -> str:
    return f" (only the newest {GH_LIMIT} read)" if len(items) >= GH_LIMIT else ""


def utc_day(since: datetime) -> str:
    """The day to ask gh from, in UTC, so a zone ahead of it doesn't lose the hours before its own midnight."""
    return str(since.astimezone(timezone.utc).date())


def product_repos() -> tuple:
    """(the products' repos in company.json, why none is read or None)."""
    try:
        repos = [own["repo"] for own in company_config.load()["products"].values() if own.get("repo")]
    except Exception as error:  # noqa: BLE001 - a report: whatever is wrong with the file, it says so and goes on
        return [], f"company.json can't be read ({type(error).__name__})"
    return repos, None if repos else "company.json names no product repo"


def deploy_lines(repo: str, since: datetime) -> list:
    lines = []
    for workflow in DEPLOY_WORKFLOWS:
        runs = gh_json("run", "list", "--repo", repo, "--workflow", workflow, "--created", f">={utc_day(since)}",
                       "--json", "databaseId,conclusion,createdAt", "--limit", str(GH_LIMIT))
        if runs is None:
            lines.append(f"- {workflow}: not read (gh failed)")
            continue
        failed = [str(run.get("databaseId")) for run in runs if run.get("conclusion") in FAILED and after(run, "createdAt", since)]
        lines.append(f"- {workflow}: {len(failed)} failed{hit_limit(runs)}" + (f": runs {', '.join(failed)}" if failed else ""))
    return lines


def follow_up_line(repo: str, since: datetime) -> str:
    prs = gh_json("pr", "list", "--repo", repo, "--state", "merged", "--search", f"merged:>={utc_day(since)}",
                  "--json", "number,title,headRefName,body,mergedAt", "--limit", str(GH_LIMIT))
    if prs is None:
        return "not read (gh failed)"
    found = []
    for pr in prs:
        title, branch, body = str(pr.get("title")), str(pr.get("headRefName")), str(pr.get("body"))
        if not after(pr, "mergedAt", since):
            continue
        if not (FOLLOW_UP.search(f"{title} {branch}") or FIX_NAMING_PR.search(title)):
            continue
        followed = sorted({int(n) for n in PR_NUMBER.findall(f"{title} {body}")} - {pr.get("number")})
        found.append(f"#{pr.get('number')}" + (" after " + ", ".join(f"#{n}" for n in followed) if followed else ""))
    return f"{len(found)}{hit_limit(prs)}" + (f": {'; '.join(found)}" if found else "")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Tokens by role, deploy failures, follow-up fixes and the machine's load.")
    parser.add_argument("--since", required=True, type=parse_time, help="ISO date or time; with no zone it's UTC")
    parser.add_argument("--session", help="a session id or folder; default: the session that last started an agent")
    args = parser.parse_args(argv)
    try:
        session = find_session(args.session)
        rows = role_rows(session, args.since)
    except OSError as error:
        print(f"token_report: {error}", file=sys.stderr)
        return 1

    print(f"Tokens since {args.since.isoformat()}, session {session.name}")
    if rows:
        print(f"{'role':<26}{'turns':>8}{'mean context':>14}{'share':>8}")
        for role, turns, context, share in rows:
            print(f"{role:<26}{turns:>8,}{context:>14,}{share:>7.1f}%")
        print("Shares are ratios from API prices; how the subscription counts tokens is unknown.")
    else:
        print("No subagent turns in that time.")

    repos, why = product_repos()
    if why:
        print(f"\nDeploy failures and follow-up fixes: not read ({why})")
    for repo in repos:
        print(f"\nDeploy failures, {repo}:")
        print("\n".join(deploy_lines(repo, args.since)))
        print(f"PRs that needed a follow-up fix, {repo}, by their words: {follow_up_line(repo, args.since)}")

    one, five, fifteen = os.getloadavg()
    print(f"\nMachine load: {one:.2f}, {five:.2f}, {fifteen:.2f} (1, 5, 15 min) on {os.cpu_count()} CPUs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
