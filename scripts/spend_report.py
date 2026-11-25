#!/usr/bin/env python3
"""The Spend block of every /report and executive summary.

One line per paid vendor or pool, with the lines that are over or projected over first. A line it reads says what's
included or the cap, what this cycle has spent (read when, from where), the projection to the cycle's end at the last 24
hours' pace and at today's, and when spend passes what's included. A line it can't read says who reads it instead. Every
time it prints is in the company's time zone (company.json).

It changes nothing. Its vendors are company.json's, each read only when it is named there:

    "integrations": {"spend": {"github_org": "acme", "github_pool": 50, "vercel_scope": "acme", "vercel_credit": 20,
                               "manual": {"OpenAI API pool": "the Board's balance"}}}

- GitHub Actions: GitHub's billing API for github_org through `gh api`, its /usage endpoint, whose Actions items give
  gross dollars by day, against github_pool dollars a month;
- Vercel: `vercel usage --json` for the team vercel_scope, against vercel_credit dollars a cycle, only if
  scripts/hooks/guard_vercel_cli.py, run as Claude Code runs it for an agent's Bash call, lets that exact command
  through. A subprocess is outside the hooks, so the script asks the guard itself and never works around it.
- manual: the pools and balances read by hand: those lines name the reader, and the page.
While company.json can't be read, it says so and reads no vendor.

It prints only numbers it computes and its own words, never a tool's text: no secret or customer data can pass. An
answer it can't read, or any error while reading one vendor, turns that vendor's line into "not read here".

The paces come from daily figures (GitHub bills by UTC day, Vercel by Los Angeles day):
- today's: today's spend so far, scaled to 24 hours (none in the day's first hour, when it's noise);
- the last 24 hours': today's spend, plus yesterday's for the hours of yesterday still in the window, as if yesterday's
  spend was even through the day.
A projection is the spend so far plus the pace times the time left in the cycle: arithmetic, not a measurement.
"""

import argparse
import json
import math
import shlex
import subprocess
import sys
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))

import company_config  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
VERCEL_GUARD = REPO_ROOT / "scripts" / "hooks" / "guard_vercel_cli.py"
SPEND_PAGE = "knowledge/finance/spend.md"
LOS_ANGELES = ZoneInfo("America/Los_Angeles")
TIMEOUT = 30  # each call; gh, the guard and vercel together stay under the Bash tool's 120 s


def settings() -> tuple:
    """(company.json's spend settings, its time zone, why it can't be read or None)."""
    try:
        own = dict(company_config.integration("spend") or {})
        return {**own, "manual": dict(own.get("manual") or {})}, company_config.timezone(), None
    except Exception as error:  # noqa: BLE001 - a report: whatever is wrong with the file, it says so and goes on
        return {"manual": {}}, timezone.utc, f"company.json can't be read ({type(error).__name__})"


SPEND, BOARD_TZ, FAULT = settings()
GITHUB = "GitHub Actions"
GITHUB_ORG, GITHUB_POOL = SPEND.get("github_org"), SPEND.get("github_pool")  # None: not read
GITHUB_USAGE = "/organizations/{org}/settings/billing/usage?year={year}&month={month}"
GITHUB_READER = "GitHub's billing page"
VERCEL = "Vercel"
VERCEL_READER = "Vercel's usage page"
VERCEL_SCOPE, VERCEL_CREDIT = SPEND.get("vercel_scope"), SPEND.get("vercel_credit")  # None: not read
VERCEL_USAGE = ["vercel", "usage", "--scope", str(VERCEL_SCOPE), "--breakdown", "daily", "--json"]
MANUAL = [*SPEND["manual"].items(),  # (name, where the number comes from)
          ("Claude subscription (SA-002)", "a flat fee: no money beyond the plan")]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_time(text: str) -> datetime:
    moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def is_number(value) -> bool:
    """A finite number: json.loads also gives NaN and Infinity."""
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def money(amount: float) -> str:
    return f"${amount:,.2f}"


def shown(moment: datetime) -> str:
    return moment.astimezone(BOARD_TZ).strftime("%m-%d %H:%M")


def run_json(argv: list):
    """The command's JSON answer, or None. Its own text is never printed."""
    try:
        done = subprocess.run(argv, capture_output=True, text=True, timeout=TIMEOUT, stdin=subprocess.DEVNULL,
                              cwd=REPO_ROOT)
        return json.loads(done.stdout) if done.returncode == 0 else None
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def refused_by_guard(argv: list) -> bool:
    """Whether the Vercel guard refuses this command, as it would an agent's Bash call. Any failure counts as a no."""
    event = {"tool_name": "Bash", "agent_type": "ceo", "cwd": str(REPO_ROOT), "tool_input": {"command": shlex.join(argv)}}
    try:
        done = subprocess.run([sys.executable, str(VERCEL_GUARD)], input=json.dumps(event), capture_output=True,
                              text=True, timeout=TIMEOUT)
    except (OSError, subprocess.SubprocessError):
        return True
    return done.returncode != 0


def paces(daily: dict, zone, cycle_start: datetime, now: datetime) -> tuple:
    """(the last 24 hours' pace, today's pace) in dollars a day; None where the days don't give one."""
    local = now.astimezone(zone)
    today = local.date()
    hours = local.hour + local.minute / 60 + local.second / 3600
    spent_today = daily.get(today, 0.0)
    today_pace = spent_today * 24 / hours if hours >= 1 else None
    yesterday = today - timedelta(days=1)
    if yesterday < cycle_start.astimezone(zone).date():  # the cycle began today: no yesterday in it
        return None, today_pace
    return spent_today + daily.get(yesterday, 0.0) * (24 - hours) / 24, today_pace


def projection(spent: float, pace: float, now: datetime, cycle_end: datetime) -> float:
    return spent + pace * max((cycle_end - now).total_seconds(), 0) / 86400


def passes(cap: float, spent: float, pace: float, now: datetime, cycle_end: datetime) -> "datetime | None":
    """When spend reaches the cap at this pace, or None if not before the cycle ends."""
    if pace <= 0:
        return None
    days = (cap - spent) / pace
    if days >= (cycle_end - now).total_seconds() / 86400:  # before any timedelta: a tiny pace would overflow one
        return None
    return now + timedelta(days=days)


def passed_on(cap: float, daily: dict) -> "date | None":
    """The vendor's day on which the spend so far reached the cap."""
    total = 0.0
    for day in sorted(daily):
        total += daily[day]
        if total >= cap:
            return day
    return None


def vendor_line(name, included, cap, source, daily, zone, cycle_start, cycle_end, now) -> tuple:
    """(over or projected over, the line) for a vendor read by day."""
    spent = sum(daily.values())
    last_24, today = paces(daily, zone, cycle_start, now)
    parts = [f"{name}: {included} {money(cap)}, cycle {shown(cycle_start)} to {shown(cycle_end)}",
             f"spent {money(spent)}, read {shown(now)} ({source})"]
    ends, dates, over = [], [], False
    for label, pace, missing in (("the last 24 hours'", last_24, "the cycle began today"),
                                 ("today's", today, "under an hour into today")):
        if pace is None:
            ends.append(f"no pace for {label} ({missing})")
            continue
        ends.append(f"{money(projection(spent, pace, now, cycle_end))} at {label} pace ({money(pace)} a day)")
        when = passes(cap, spent, pace, now, cycle_end) if spent < cap else None
        over = over or when is not None
        dates.append(f"{when.astimezone(BOARD_TZ):%m-%d}" if when else "not this cycle")
        dates[-1] += f" at {label} pace"
    parts.append("at the cycle's end: " + ", ".join(ends))
    if spent >= cap:
        day = passed_on(cap, daily)
        if day:  # the vendor's billing day, shown by its bounds in the company's time zone
            begins = datetime.combine(day, time(), tzinfo=zone)
            parts.append(f"passed {money(cap)} in its billing day {shown(begins)} to {shown(begins + timedelta(days=1))}")
        else:
            parts.append(f"passed {money(cap)}")
        return True, "OVER " + " | ".join(parts)
    parts.append(f"passes {money(cap)}: " + (", ".join(dates) or "no pace to project"))
    return over, ("PROJECTED OVER " if over else "") + " | ".join(parts)


def unread(name: str, why: str, how: str) -> tuple:
    return False, f"{name}: not read here ({why}); read by the CTO ({how})"


def github_daily(answer) -> "dict | None":
    """Actions' gross dollars by UTC day, from the billing API's answer; None if it isn't one."""
    items = answer.get("usageItems") if isinstance(answer, dict) else None
    if not isinstance(items, list):
        return None
    daily = defaultdict(float)
    for item in items:
        if not isinstance(item, dict) or "product" not in item:
            return None
        if str(item["product"]).lower() != "actions":
            continue
        try:
            day, amount = date.fromisoformat(str(item["date"])[:10]), item["grossAmount"]
        except (KeyError, ValueError):
            return None
        if not is_number(amount):
            return None
        daily[day] += amount
    return dict(daily)


def github_net(answer) -> "float | None":
    """Actions' net (billed) dollars this month, from an answer github_daily read; None if an item has no finite one."""
    amounts = [item.get("netAmount") for item in answer["usageItems"] if str(item["product"]).lower() == "actions"]
    return sum(amounts) if all(is_number(amount) for amount in amounts) else None


def github_line() -> tuple:
    now = utc_now()
    start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
    end = datetime(now.year + now.month // 12, now.month % 12 + 1, 1, tzinfo=timezone.utc)
    answer = run_json(["gh", "api", GITHUB_USAGE.format(org=GITHUB_ORG, year=now.year, month=now.month)])
    daily = github_daily(answer)
    if daily is None:
        return unread(GITHUB, "the billing API gave no answer this script can read", GITHUB_READER)
    net = github_net(answer)
    billed = f"{money(net)} of it billed (net)" if net is not None else "net not in the answer"
    return vendor_line(GITHUB, "pool", GITHUB_POOL, f"GitHub's billing API, Actions gross; {billed}", daily,
                       timezone.utc, start, end, now)


def vercel_reading(answer) -> "tuple | None":
    """(usage dollars by Los Angeles day, cycle start, cycle end) from `vercel usage --json`; None if it isn't that.
    Subscription lines (seats) are left out: the credit covers usage."""
    try:
        if answer["costUnit"] != "USD":
            return None
        start, end = parse_time(answer["period"]["from"]), parse_time(answer["period"]["to"])
        daily = defaultdict(float)
        for period in answer["breakdown"]["data"]:
            day = date.fromisoformat(period["periodKey"])
            for service in period["services"]:
                if service.get("category") == "subscription":
                    continue
                if not is_number(service["cost"]):
                    return None
                daily[day] += service["cost"]
    except (KeyError, TypeError, ValueError, AttributeError):
        return None
    return dict(daily), start, end


def vercel_line() -> tuple:
    if refused_by_guard(VERCEL_USAGE):
        return unread(VERCEL, f"scripts/hooks/guard_vercel_cli.py refuses `{shlex.join(VERCEL_USAGE)}`", VERCEL_READER)
    reading = vercel_reading(run_json(VERCEL_USAGE))
    now = utc_now()
    if reading is None:
        return unread(VERCEL, "`vercel usage` gave no answer this script can read", VERCEL_READER)
    daily, start, end = reading
    if end <= now:  # with no billing period, the CLI reads to its own now: no cycle end to project to
        return unread(VERCEL, "`vercel usage` named no billing cycle", VERCEL_READER)
    return vendor_line(VERCEL, "credit", VERCEL_CREDIT, "vercel usage", daily, LOS_ANGELES, start, end, now)


def read_safely(name: str, read, reader: str) -> tuple:
    """The vendor's line, or "not read here" if reading it fails in any way. The error's text is never printed."""
    try:
        return read()
    except Exception:
        return unread(name, "this script failed on its answer", reader)


def main(argv=()) -> int:
    """`--help`, or any argument it doesn't take, prints the usage and exits before anything is read."""
    argparse.ArgumentParser(description=__doc__.splitlines()[0]).parse_args(list(argv))
    started = utc_now()
    lines = [read_safely(GITHUB, github_line, GITHUB_READER)] if GITHUB_ORG else []
    lines += [read_safely(VERCEL, vercel_line, VERCEL_READER)] if VERCEL_SCOPE else []
    lines += [(False, f"{name}: manual, from {SPEND_PAGE} ({source})") for name, source in MANUAL]
    print(f"Spend as of {shown(started)} {BOARD_TZ} (all times {BOARD_TZ}; over or projected over first; projections "
          "are arithmetic at the pace named)")
    if FAULT:
        print(f"- {FAULT}: no vendor is read")
    for _, line in sorted(lines, key=lambda flagged: not flagged[0]):
        print(f"- {line}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
