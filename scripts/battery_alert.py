#!/usr/bin/env python3
"""Battery alerts to the Board by email while the Mac runs unplugged. macOS only (pmset, launchd). The job can
reach your Gmail only if it starts with your Claude account's own settings, so it does nothing until company.json has a
board_email and "integrations": {"battery_alert": {}}. To switch it on: connect Gmail to the Claude account, set the two
in company.json, run `test`, then `install`.

    python3 scripts/battery_alert.py run        what launchd starts every 60 seconds: one read of `pmset -g batt`, and
                                                at most one email
    python3 scripts/battery_alert.py test       one test email by the same path, subject
                                                "[CEO] Test: battery alert"; it changes no state
    python3 scripts/battery_alert.py install    install and start the launchd job (from the main checkout only), only
                                                once `test` has delivered its email
    python3 scripts/battery_alert.py uninstall  stop and remove it

- The rule: on battery ("Now drawing from 'Battery Power'"), when the level first reaches or passes below 50, 25, 10, 5
  or 2 since the Mac last ran on AC power, one email for that threshold. Several crossed at once (the Mac asleep, or
  unplugged below 50): one email, for the lowest, and the higher ones count as sent. On AC power the thresholds reset.
  Any other reading (pmset failing, no battery line, another source) changes nothing and is logged once.
- The email names the level, the time in the company's time zone (company.json) and the estimated time left as pmset
  prints it ("2:00 remaining", "(no estimate)").
- How it sends: one headless `claude -p` from this checkout as the CEO main session (`--agent ceo`), so
  scripts/hooks/board_email.py's caller check, the Board's own address, the form and the secrets check bind it as they
  bind the CEO, on the Claude account it was installed from ($CLAUDE_CONFIG_DIR at install, else the default), without
  ANTHROPIC_API_KEY or ANTHROPIC_AUTH_TOKEN (SA-002). --setting-sources user,project: the claude.ai connectors load only
  with the account's settings; the checkout's local settings stay out. So each run loads the account's allow rules,
  plugins, hooks and MCP servers. The tool list and the deny list keep them out (claude_argv): --tools leaves only
  ToolSearch, which loads a tool's definition and does nothing else, so no Bash, files, agents or WebFetch; of the MCP
  tools, the ceo agent's own tools list leaves only the Gmail send and Claude in Chrome's; --disallowedTools
  (DISALLOWED) takes out Chrome's and each MCP server the project's settings allow (Neon), and tests check it against
  both lists; --allowedTools names the Gmail send alone. The run doesn't start while the account's settings name an
  apiKeyHelper or an API key in env (api_key_reason; SA-002), which would reach it past the environment it strips. Its
  environment sets AGENTIC_COMPANY_JOB, so ceo.md's Stop hook (scripts/hooks/capacity_heartbeat.py) neither nudges the
  run to start work nor takes the live CEO's nudge. Install after `test` delivers from the checkout the job runs in.
- Sent or not is read from the run itself, never from the model's words: a send_message call in its stream whose
  result is no error is sent, one whose result is an error is not. With neither (the run cut off, its stream
  unreadable), a line the guard logged with this subject since the try began counts as sent, so a doubt never sends
  twice.
- State: workspaces/system/battery-alert.json (gitignored), the thresholds sent since AC power and the failed tries.
  Log: ~/Library/Logs/agentic-company/battery-alert.log, a line for each change, email and failure, none on a quiet run.

What it can't do: an asleep Mac runs nothing (launchd runs a missed interval once at wake, and that run emails the
lowest threshold crossed), and a Mac with no network sends nothing. A try that fails (no network, the account's usage
limit, Gmail, the guard) is logged and tried again at the next run; after each further failure in a row the next try
waits longer (2, 4, 8, then 15 minutes at most), so a broken path doesn't spend a model run every minute. The Gmail
connector may still be connecting when the run starts: the run searches for it a second time, and a run that still
doesn't find it fails, so that alert comes at the next run, or 2 to 15 minutes later after failures in a row.
"""

import argparse
import contextlib
import fcntl
import json
import os
import plistlib
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent / "hooks"))

import board_email  # noqa: E402  (the guard's own rules: its tool and log)
import company_config  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
STATE = Path("workspaces/system/battery-alert.json")  # gitignored, like all of workspaces/
LOCK = Path("workspaces/system/battery-alert.lock")
LABEL = "com.agentic-company.battery-alert"
PLIST = Path.home() / f"Library/LaunchAgents/{LABEL}.plist"
LOG = Path.home() / "Library/Logs/agentic-company/battery-alert.log"
EVERY = 60  # seconds between runs: a 2% step at a fast drain takes minutes
PYTHON = "/usr/bin/python3"  # Apple's, as the desk's jobs: keep this file and what it imports Python 3.9
ACCOUNT = os.environ.get("CLAUDE_CONFIG_DIR")  # the Claude account's folder, when it isn't the default one
JOB_ENV = {"PATH": f"{Path.home()}/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin",
           **({"CLAUDE_CONFIG_DIR": ACCOUNT} if ACCOUNT else {})}
API_KEYS = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")  # never passed to claude -p: it would bill the key (SA-002)
ACCOUNT_SETTINGS = Path(ACCOUNT or Path.home() / ".claude") / "settings.json"  # what --setting-sources user loads
MARKER = {"AGENTIC_COMPANY_JOB": "battery-alert"}  # capacity_heartbeat.JOB: no Stop-hook nudge in the run
THRESHOLDS = (50, 25, 10, 5, 2)
AC, BATTERY = "AC Power", "Battery Power"
SEND = board_email.SEND
DISALLOWED = ("mcp__claude_ai_Neon", "mcp__claude-in-chrome")  # each MCP server .claude/settings.json allows, and
#   Claude in Chrome, the one MCP server but Gmail the ceo agent's tools name (a test checks each list)
MODEL = "sonnet"
TIMEOUT = 180  # seconds for one claude run
FIRST_WAIT, MAX_WAIT = 120, 900  # after 2 failures in a row, 4 min after 3, 8 after 4, then 15 (the 1st: the next run)
TEST_SUBJECT = "[CEO] Test: battery alert"

SOURCE = re.compile(r"Now drawing from '([^']*)'")
LEVEL = re.compile(r"^\s*-InternalBattery-\d+\b[^\t\n]*\t\s*(\d{1,3})%;([^;\n]*);([^\n]*?)(?:\s+present: \w+)?\s*$", re.M)
LEFT = re.compile(r"[^\w:() .-]")  # what the time-left text may hold; anything else is dropped


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def say(line: str) -> None:
    print(f"{utc_now().strftime('%Y-%m-%dT%H:%M:%SZ')} {line}", flush=True)


def off() -> "str | None":
    """Why this does nothing here, or None: not macOS, not switched on in company.json (module docstring), or a
    company.json that can't be read."""
    if sys.platform != "darwin":
        return "macOS only"
    try:
        company_config.timezone()
        settings, board = company_config.integration("battery_alert"), company_config.load()["board_email"]
    except Exception as error:  # noqa: BLE001 - whatever is wrong with the file, nothing is sent
        return f"company.json can't be read ({type(error).__name__})"
    if settings is None:
        return "off: company.json has no battery_alert integration"
    return None if board else "off: company.json has no board_email"


# ---- the reading and the rule ---------------------------------------------------------------------------------------

def parse(text: str) -> "tuple[dict | None, str | None]":
    """({"source", "percent", "left"}, None) from `pmset -g batt`'s text, or (None, why it can't be read)."""
    source = SOURCE.search(text)
    if not source:
        return None, "no \"Now drawing from\" line"
    if source.group(1) not in (AC, BATTERY):
        return None, f"source {source.group(1)[:40]!r}"
    level = LEVEL.search(text)
    if not level:
        return None, "no internal battery line"
    percent = int(level.group(1))
    if percent > 100:
        return None, f"level {percent}%"
    left = LEFT.sub("", level.group(3)).strip()[:40] or "(none printed)"
    return {"source": source.group(1), "percent": percent, "left": left}, None


def read_pmset() -> "tuple[dict | None, str | None]":
    try:
        done = subprocess.run(["pmset", "-g", "batt"], capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.SubprocessError) as error:
        return None, f"pmset didn't run ({type(error).__name__})"
    if done.returncode:
        return None, f"pmset exited {done.returncode}"
    return parse(done.stdout)


def fresh() -> dict:
    return {"source": None, "sent": [], "failures": 0, "next_try": None, "unreadable": None}


def due(state: dict, reading: dict) -> "int | None":
    """The threshold to email now: the lowest crossed on battery and not yet sent since AC power, or None."""
    if reading["source"] != BATTERY:
        return None
    crossed = [t for t in THRESHOLDS if reading["percent"] <= t and t not in state["sent"]]
    return min(crossed) if crossed else None


def step(state: dict, reading: "dict | None", why: "str | None") -> "tuple[dict, int | None, list]":
    """(the new state, the threshold to email now or None, lines to log) for one reading. Pure: no clock, no I/O."""
    state, lines = dict(state), []
    if reading is None:
        if state["unreadable"] != why:
            lines.append(f"pmset unreadable: {why}; nothing changes")
        state["unreadable"] = why
        return state, None, lines
    if state["unreadable"]:
        lines.append("pmset readable again")
    state["unreadable"] = None
    if reading["source"] != state["source"]:
        lines.append(f"now on {reading['source']} at {reading['percent']}%"
                     + ("; thresholds reset" if reading["source"] == AC else ""))
    state["source"] = reading["source"]
    if reading["source"] == AC:
        state.update(sent=[], failures=0, next_try=None)
        return state, None, lines
    return state, due(state, reading), lines


def mark_sent(state: dict, percent: int) -> dict:
    """Every threshold at or above this level counts as sent, so the higher ones crossed with it never go out."""
    return {**state, "sent": sorted({*state["sent"], *(t for t in THRESHOLDS if percent <= t)}, reverse=True),
            "failures": 0, "next_try": None}


def mark_failed(state: dict, now: datetime) -> dict:
    """The next try: at the next run after one failure, then later after each one more in a row (FIRST_WAIT)."""
    failures = state["failures"] + 1
    if failures == 1:
        return {**state, "failures": 1, "next_try": None}
    wait = min(FIRST_WAIT * 2 ** (failures - 2), MAX_WAIT)
    return {**state, "failures": failures, "next_try": (now + timedelta(seconds=wait)).strftime("%Y-%m-%dT%H:%M:%SZ")}


def waiting(state: dict, now: datetime) -> bool:
    return bool(state["next_try"]) and now.strftime("%Y-%m-%dT%H:%M:%SZ") < state["next_try"]


# ---- the email ------------------------------------------------------------------------------------------------------

def board_time(now: datetime) -> str:
    return now.astimezone(company_config.timezone()).strftime("%H:%M %Z, %A %Y-%m-%d")


def alert(reading: dict, threshold: int, now: datetime) -> "tuple[str, str]":
    """(subject, body) of the email for this threshold."""
    lower = [t for t in THRESHOLDS if t < threshold]
    subject = f"[CEO] Battery: {reading['percent']}%, the Mac is not plugged in"
    body = (f"The Mac is running on battery: {reading['percent']}% at {board_time(now)} (the {threshold}% alert).\n"
            f"Estimated time left, as pmset prints it: {reading['left']}.\n"
            + (f"Next alert at {max(lower)}%. " if lower else "This is the last alert of this discharge. ")
            + "Plug it in, or the Mac sleeps and the company's agents stop.\n\n"
            "Sent by scripts/battery_alert.py: one email per level (50, 25, 10, 5 and 2%) while on battery, reset on "
            "AC power.")
    return subject, body


def test_email(reading: "dict | None", why: "str | None", now: datetime) -> "tuple[str, str]":
    seen = (f"{reading['source']}, {reading['percent']}%, {reading['left']}" if reading
            else f"pmset unreadable: {why}")
    return TEST_SUBJECT, (f"A test of the battery alert's path (scripts/battery_alert.py test), "
                          f"at {board_time(now)}.\nNow: {seen}.\n"
                          "Real alerts come at 50, 25, 10, 5 and 2% while the Mac runs on battery, one per level, "
                          "reset on AC power. Nothing to do.")


# ---- the send -------------------------------------------------------------------------------------------------------

def claude_argv(tool_input: dict) -> list:
    """The headless run: the CEO main session with only the Gmail send tool allowed (module docstring)."""
    prompt = (f"Battery alert job (scripts/battery_alert.py). Do only this: load {SEND} with ToolSearch (query "
              f"\"select:{SEND}\"); if it isn't found (Gmail may still be connecting), search once more the same way. "
              f"Then call it once with exactly this input and nothing else: "
              f"{json.dumps(tool_input, ensure_ascii=False)}. Call no other tool. Then reply in one line: SENT, or "
              "NOT SENT and the error.")
    return ["claude", "-p", prompt, "--agent", "ceo", "--model", MODEL, "--permission-mode", "default",
            "--setting-sources", "user,project", "--tools", "ToolSearch", "--allowedTools", SEND,
            "--disallowedTools", ",".join(DISALLOWED), "--disable-slash-commands", "--no-session-persistence",
            "--max-turns", "5", "--output-format", "stream-json", "--verbose"]  # 2 searches, send, reply, 1 spare


def one_line(text: object, limit: int = 300) -> str:
    return " ".join(str(text).split())[:limit]


def read_stream(stdout: str) -> "tuple[bool | None, str]":
    """(True, "sent") if the run's stream holds a send_message call whose result is no error, (False, why) if each such
    call's result is an error, else (None, why): nothing in the stream says whether it went."""
    calls, results, final = [], {}, None
    for line in stdout.splitlines():
        try:
            message = json.loads(line)
        except ValueError:
            continue
        if not isinstance(message, dict):
            continue
        if message.get("type") == "result":
            final = message
        content = message.get("message", {}).get("content") if isinstance(message.get("message"), dict) else None
        for block in content if isinstance(content, list) else []:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_use" and block.get("name") == SEND:
                calls.append(block.get("id"))
            elif block.get("type") == "tool_result":
                results[block.get("tool_use_id")] = block
    for call in calls:
        if call in results and not results[call].get("is_error"):
            return True, "sent"
    if calls and all(call in results for call in calls):
        return False, f"send_message failed or was refused: {one_line(results[calls[-1]].get('content'))}"
    if calls:
        return None, "send_message gave no result"
    if final is None:
        return None, "claude gave no result"
    denied = final.get("permission_denials") or []
    if denied:
        return None, f"refused: {one_line([d.get('tool_name') for d in denied if isinstance(d, dict)])}"
    return None, f"no send_message call ({final.get('subtype')}; {one_line(final.get('result') or '', 200)})"


def guard_logged(root: Path, subject: str, since: str) -> bool:
    """Whether the guard logged an email with this subject at or after `since` (it logs what it lets through)."""
    try:
        log = board_email.main_checkout(root) / board_email.LOG
        lines = log.read_text(encoding="utf-8").splitlines()
    except (OSError, ValueError):
        return False
    for line in lines:
        with contextlib.suppress(ValueError, TypeError, AttributeError):
            entry = json.loads(line)
            if entry.get("subject") == subject and str(entry.get("time")) >= since:
                return True
    return False


def api_key_reason(path: Path) -> "str | None":
    """Why the account's settings would bill an API key in the run (SA-002), or None: an apiKeyHelper, or an API_KEYS
    name in their env. Names only, never a value; settings that can't be read count as a reason."""
    try:
        settings = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError):
        return f"{path} unreadable"
    if not isinstance(settings, dict):
        return f"{path} is not a settings object"
    if "apiKeyHelper" in settings:
        return f"{path} names an apiKeyHelper"
    env = settings.get("env")
    named = sorted(set(env) & set(API_KEYS)) if isinstance(env, dict) else []
    return f"{path} sets {', '.join(named)} in env" if named else None


def run_claude(argv: list, root: Path) -> "tuple[int | None, str]":
    env = {key: value for key, value in os.environ.items() if key not in API_KEYS}  # SA-002: the subscription only
    env.update(JOB_ENV, **MARKER, CLAUDE_CODE_DISABLE_CLAUDE_MDS="1", CLAUDE_CODE_DISABLE_AUTO_MEMORY="1")
    try:
        done = subprocess.run(argv, cwd=root, env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                              timeout=TIMEOUT)
    except subprocess.TimeoutExpired as error:
        out = error.stdout
        return None, out.decode(errors="replace") if isinstance(out, bytes) else (out or "")
    except OSError:
        return None, ""
    return done.returncode, done.stdout


def send(root: Path, subject: str, body: str, runner=run_claude) -> "tuple[bool, str]":
    """(True, "sent") once the email went out by the headless run, or (False, why not)."""
    reason = off()
    if reason:
        return False, reason
    tool_input = {"to": [company_config.load()["board_email"]], "subject": subject, "body": body}
    reason = board_email.form_reason({"tool_name": SEND, "agent_type": "ceo", "tool_input": tool_input}, root)
    if reason:
        return False, f"the guard would refuse it: {reason}"
    reason = api_key_reason(ACCOUNT_SETTINGS)
    if reason:
        return False, f"refused, SA-002: {reason}"
    since = utc_now().strftime("%Y-%m-%dT%H:%M:%SZ")
    code, stdout = runner(claude_argv(tool_input), root)
    sent, why = read_stream(stdout)
    if sent is None and guard_logged(root, subject, since):
        return True, f"sent (the guard logged it; the run: {why})"
    if code is None:
        why = f"claude didn't start or ran out of time ({TIMEOUT} s); {why}"
    return bool(sent), why


# ---- the runs -------------------------------------------------------------------------------------------------------

def load_state(root: Path) -> dict:
    try:
        state = json.loads((root / STATE).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return fresh()
    except ValueError:
        say("state unreadable; starting over")
        return fresh()
    return {**fresh(), **state} if isinstance(state, dict) else fresh()


def save_state(root: Path, state: dict) -> None:
    path = root / STATE
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, indent=1) + "\n", encoding="utf-8")
    os.replace(temporary, path)


@contextlib.contextmanager
def locked(root: Path, wait: bool):
    """The job's lock, so a run and a test never send at once; yields False if another holds it and wait is False."""
    (root / LOCK).parent.mkdir(parents=True, exist_ok=True)
    with open(root / LOCK, "a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | (0 if wait else fcntl.LOCK_NB))
        except BlockingIOError:
            yield False
            return
        yield True


def run_once(root: Path, reader=read_pmset, sender=send, now=None) -> int:
    with locked(root, wait=False) as mine:
        if not mine:
            return 0  # the other run is sending
        now = now or utc_now()
        reading, why = reader()
        old = load_state(root)
        state, threshold, lines = step(old, reading, why)
        for line in lines:
            say(line)
        if threshold is not None and not waiting(state, now):
            subject, body = alert(reading, threshold, now)
            sent, how = sender(root, subject, body)
            if sent:
                state = mark_sent(state, reading["percent"])
                say(f"{how}: {subject}")
            else:
                state = mark_failed(state, now)
                say(f"not sent (try {state['failures']}): {how}; next try after {state['next_try']}")
        if state != old:
            save_state(root, state)
        return 1 if reading is None else 0


def test(root: Path, reader=read_pmset, sender=send) -> int:
    with locked(root, wait=True):
        reading, why = reader()
        subject, body = test_email(reading, why, utc_now())
        sent, how = sender(root, subject, body)
    say(f"test: {how}: {subject}")
    return 0 if sent else 1


# ---- launchd --------------------------------------------------------------------------------------------------------

def job() -> dict:
    return {
        "Label": LABEL,
        "ProgramArguments": [PYTHON, str(Path(__file__).resolve()), "run"],
        "StartInterval": EVERY,
        "EnvironmentVariables": dict(JOB_ENV),
        "StandardOutPath": str(LOG),
        "StandardErrorPath": str(LOG),
    }


def install() -> int:
    if not (REPO / ".git").is_dir():
        print(f"refused: {REPO} is a worktree; install from the main checkout")
        return 2
    PLIST.parent.mkdir(parents=True, exist_ok=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(PLIST, "wb") as file:
        plistlib.dump(job(), file)
    domain = f"gui/{os.getuid()}"
    subprocess.run(["launchctl", "bootout", f"{domain}/{LABEL}"], stderr=subprocess.DEVNULL)
    subprocess.run(["launchctl", "bootstrap", domain, str(PLIST)], check=True)
    print(f"installed {LABEL}: every {EVERY} s, from {REPO}, on {ACCOUNT_SETTINGS.parent}; log {LOG}")
    return 0


def uninstall() -> int:
    service = f"gui/{os.getuid()}/{LABEL}"
    stopped = subprocess.run(["launchctl", "bootout", service], stderr=subprocess.DEVNULL)
    if stopped.returncode and subprocess.run(["launchctl", "print", service], stdout=subprocess.DEVNULL,
                                             stderr=subprocess.DEVNULL).returncode == 0:  # still loaded
        print(f"bootout failed (exit {stopped.returncode}), {LABEL} is still loaded; the plist stays, run uninstall again")
        return 1
    with contextlib.suppress(FileNotFoundError):
        PLIST.unlink()
    print(f"removed {LABEL}; its state stays in {STATE}")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", nargs="?", default="run", choices=["run", "test", "install", "uninstall"])
    command = parser.parse_args(argv).command
    if sys.platform == "darwin" and command == "uninstall":
        return uninstall()
    reason = off()
    if reason:
        print(f"battery alert: nothing done; {reason}")
        return 0 if command == "run" else 2
    if command == "install":
        return install()
    return test(REPO) if command == "test" else run_once(REPO)


if __name__ == "__main__":
    sys.exit(main())
