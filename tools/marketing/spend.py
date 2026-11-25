#!/usr/bin/env python3
"""The usage log and monthly caps for paid media calls (SA-005).

    python3 tools/marketing/spend.py --brand founder/demo --week 2026-W05

prints one batch's totals per tool, for the CMO to paste into the week's report.

Every paid call appends two JSON lines to workspaces/marketing/spend.jsonl (gitignored),
each {"ts", "kind", "id", "tool", "model", "brand", "week", "piece", "units", "unit"}:
- before it is sent, a reservation ("kind": "reserve", the units asked for), written
  under an exclusive lock on the log right after checking the cap under the same lock,
  so two calls at once can't both slip under it;
- after the reply, the outcome ("kind": "done", the units actually used, and "ok").
A month's total counts each call id once, as the larger of its reserved and actual units,
in the month it was reserved. So a call whose process was killed before the reply still
counts; the report shows it as failed. `tool` names the cap in tools/marketing/caps.json.
Caps count units per calendar month (UTC), not money, because prices change. The Board
sets them, and the platform engineer writes them in caps.json; a null cap refuses, so nothing
runs before the Board sets a number. Failed calls count toward the cap too: some are
billed, and a cap should err on the safe side.

It also holds what every paid media script shares: the batch folder outputs go to
(media_dir) and how seconds are measured (media_seconds, with the bundled ffmpeg).
"""

import argparse
import fcntl
import json
import re
import subprocess
import sys
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOG = Path("workspaces/marketing/spend.jsonl")
CAPS = Path("tools/marketing/caps.json")
FFMPEG = ROOT / "tools/marketing/node_modules/ffmpeg-static/ffmpeg"
UNITS = {
    "gemini_images": "images",
    "gemini_video_seconds": "seconds",
    "elevenlabs_stt_seconds": "seconds",
    "elevenlabs_tts_characters": "characters",
}
# ffmpeg prints the real line at exactly two spaces, after the file's metadata, which can say anything: as in reels/watch.py
DURATION = re.compile(r"^  Duration: (\d+):(\d\d):(\d\d(?:\.\d+)?)", re.M)
MEDIA = Path("workspaces/marketing/media")
BATCH = {"brand": (re.compile(r"[a-z0-9][a-z0-9_.-]*(/[a-z0-9][a-z0-9_.-]*)?"), "founder/demo"),
         "week": (re.compile(r"\d{4}-W\d{2}"), "2026-W05"),
         "piece": (re.compile(r"[a-z0-9][a-z0-9-]*"), "a lower-case slug like mountain-dawn")}


class CapError(Exception):
    """A paid call refused before it is sent."""


def _now(now=None) -> datetime:
    return now or datetime.now(timezone.utc)


def _entries(root: Path) -> list:
    path = root / LOG
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


@contextmanager
def _locked_log(root: Path):
    """The log, open for appending under an exclusive lock that is released when it closes."""
    path = root / LOG
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as log:
        fcntl.flock(log, fcntl.LOCK_EX)
        yield log


def _append(log, kind: str, call: dict, units: float, now: datetime, **extra) -> None:
    line = {"ts": now.isoformat(timespec="seconds"), "kind": kind, **call, "units": units,
            "unit": UNITS[call["tool"]], **extra}
    log.write(json.dumps(line, ensure_ascii=False) + "\n")


def _calls(root: Path) -> list:
    """One dict per call id: its reservation's ts, tool and batch; units, the larger of reserved and actual;
    ok only when an outcome line says so."""
    calls = {}
    for e in _entries(root):
        call = calls.setdefault(e["id"], {**e, "units": 0, "ok": False})
        call["units"] = max(call["units"], e["units"])
        if e["kind"] == "done":
            call["ok"] = e["ok"]
    return list(calls.values())


def month_total(tool: str, month: str, root: Path = ROOT) -> float:
    """Units used by `tool` in `month` (YYYY-MM, UTC), each call once, reservations without an outcome included."""
    return sum(c["units"] for c in _calls(root) if c["tool"] == tool and c["ts"][:7] == month)


def reserve(tool: str, model: str, brand, week, piece, units: float, root: Path = ROOT, now=None) -> dict:
    """Before a paid call: under an exclusive lock on the log, check that this month's total plus `units` stays
    within the cap, then append the reservation. Returns the call, for done(). Raises CapError, logging
    nothing, when the cap is null or would be passed."""
    cap = json.loads((root / CAPS).read_text(encoding="utf-8"))[tool]
    if cap is None:
        raise CapError(f"{tool}: no cap set, so nothing runs. TODO(board): set the monthly cap in {CAPS.as_posix()}.")
    now = _now(now)
    month = now.strftime("%Y-%m")
    call = {"id": uuid.uuid4().hex, "tool": tool, "model": model, "brand": brand, "week": week, "piece": piece}
    with _locked_log(root) as log:
        used = month_total(tool, month, root)
        if used + units > cap:
            raise CapError(f"{tool}: {used:g} of {cap:g} {UNITS[tool]} used in {month}; {units:g} more would pass "
                           "the cap. Generation stops here until next month or until the Board raises the cap.")
        _append(log, "reserve", call, units, now)
    return call


def done(call: dict, units: float, ok: bool, root: Path = ROOT, now=None) -> None:
    """After a paid call: append its outcome, with the units actually used."""
    with _locked_log(root) as log:
        _append(log, "done", call, units, _now(now), ok=ok)


def report(brand: str, week: str, root: Path = ROOT) -> None:
    """Print the batch's calls and units per tool, as a table for the week's report."""
    totals = {}
    for c in _calls(root):
        if c["brand"] == brand and c["week"] == week:
            calls, failed, units = totals.get(c["tool"], (0, 0, 0))
            totals[c["tool"]] = (calls + 1, failed + (not c["ok"]), units + c["units"])
    if not totals:
        print(f"Generation spend, {brand} {week}: no paid calls logged.")
        return
    print(f"Generation spend, {brand} {week} (units; Failed includes calls with no outcome logged; every call counts "
          "toward the cap):\n")
    print("| Tool | Calls | Failed | Units |\n|---|---|---|---|")
    for tool, (calls, failed, units) in sorted(totals.items()):
        print(f"| {tool} | {calls} | {failed} | {units:g} {UNITS[tool]} |")


def media_dir(brand: str, week: str, piece: str, root: Path = ROOT) -> Path:
    """workspaces/marketing/media/<brand>/<week>/<piece>/: the only place paid media is written.
    Each part must match its pattern, so no part can climb out of the folder."""
    for name, value in (("brand", brand), ("week", week), ("piece", piece)):
        pattern, example = BATCH[name]
        if not pattern.fullmatch(value):
            raise ValueError(f"--{name} {value!r} should look like {example}")
    return root / MEDIA / brand / week / piece


def media_seconds(path: Path, run=subprocess.run) -> float:
    """Length of an audio or video file, from the `Duration:` line ffmpeg prints for `-i` alone."""
    result = run([str(FFMPEG), "-hide_banner", "-i", str(path)], capture_output=True, text=True)
    found = DURATION.findall(result.stderr)
    if not found:
        raise ValueError(f"ffmpeg shows no duration for {path}")
    hours, minutes, seconds = found[-1]
    return round(int(hours) * 3600 + int(minutes) * 60 + float(seconds), 2)


def main(argv=None, root: Path = ROOT) -> int:
    parser = argparse.ArgumentParser(description="Print a batch's paid generation calls, for the week's report.")
    parser.add_argument("--brand", required=True, help="e.g. founder/demo")
    parser.add_argument("--week", required=True, help="e.g. 2026-W05")
    args = parser.parse_args(argv)
    report(args.brand, args.week, root)
    return 0


if __name__ == "__main__":
    sys.exit(main())
