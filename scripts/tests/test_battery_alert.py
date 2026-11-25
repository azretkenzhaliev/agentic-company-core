"""Tests for scripts/battery_alert.py: battery alerts to the Board."""

import fcntl
import json
import re
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import battery_alert as ba  # noqa: E402
import board_email  # noqa: E402  (battery_alert put scripts/hooks on the path)
import company_config  # noqa: E402

SEND = "mcp__claude_ai_Gmail__send_message"
NOW = datetime(2026, 1, 15, 17, 40, tzinfo=timezone.utc)  # 23:40 six hours ahead
BOARD = "board@example.com"


def setUpModule():
    """A company that switched the alerts on, on a Mac, whatever this machine and its company.json are."""
    own = {**company_config.DEFAULTS, "board_email": BOARD, "timezone": "Asia/Dhaka",
           "integrations": {"battery_alert": {}}}
    for patcher in (mock.patch.object(company_config, "load", lambda root=None: own),
                    mock.patch.object(ba.sys, "platform", "darwin")):
        patcher.start()
        unittest.addModuleCleanup(patcher.stop)


def pmset(source="Battery Power", percent=22, rest="discharging; 2:00 remaining"):
    return f"Now drawing from '{source}'\n -InternalBattery-0 (id=1234567)\t{percent}%; {rest} present: true\n"


def on_battery(percent, left="2:00 remaining"):
    return {"source": ba.BATTERY, "percent": percent, "left": left}


AC_READING = {"source": ba.AC, "percent": 100, "left": "0:00 remaining"}


def stream(*messages):
    return "\n".join(json.dumps(message) for message in messages) + "\n"


def tool_use(name=SEND, id_="toolu_1"):
    return {"type": "assistant", "message": {"content": [{"type": "tool_use", "id": id_, "name": name, "input": {}}]}}


def tool_result(is_error=False, content="Message sent: id 18f", id_="toolu_1"):
    return {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": id_, "is_error": is_error,
                                                     "content": content}]}}


def result(denials=(), text="SENT"):
    return {"type": "result", "subtype": "success", "result": text, "permission_denials": list(denials)}


class Reading(unittest.TestCase):
    def test_on_battery_with_an_estimate(self):
        self.assertEqual(ba.parse(pmset()), ({"source": "Battery Power", "percent": 22, "left": "2:00 remaining"}, None))

    def test_on_battery_with_no_estimate(self):
        reading, _ = ba.parse(pmset(percent=50, rest="discharging; (no estimate)"))
        self.assertEqual((reading["percent"], reading["left"]), (50, "(no estimate)"))

    def test_on_ac_power_as_this_mac_prints_it(self):
        text = "Now drawing from 'AC Power'\n -InternalBattery-0 (id=1234567)\t100%; charged; 0:00 remaining present: true\n"
        self.assertEqual(ba.parse(text), ({"source": "AC Power", "percent": 100, "left": "0:00 remaining"}, None))

    def test_an_unreadable_pmset_gives_a_reason_and_no_reading(self):
        for text in ("", "garbage", pmset(source="UPS Power"), "Now drawing from 'Battery Power'\n",
                     pmset(percent=101), pmset(percent="x")):
            with self.subTest(text=text):
                reading, why = ba.parse(text)
                self.assertIsNone(reading)
                self.assertTrue(why)

    def test_the_time_left_keeps_only_plain_characters(self):
        reading, _ = ba.parse(pmset(rest="discharging; 2:00 remaining\x1b[31m<b>`x`"))
        self.assertEqual(reading["left"], "2:00 remaining31mbx")

    def test_pmset_failing_to_run_is_unreadable(self):
        with mock.patch.object(ba.subprocess, "run", side_effect=FileNotFoundError):
            self.assertEqual(ba.read_pmset(), (None, "pmset didn't run (FileNotFoundError)"))
        with mock.patch.object(ba.subprocess, "run", return_value=mock.Mock(returncode=1, stdout="")):
            self.assertEqual(ba.read_pmset(), (None, "pmset exited 1"))


class Rule(unittest.TestCase):
    def due_after(self, percents, state=None):
        """The thresholds emailed as the level falls through percents on battery, each send succeeding."""
        state, sent = state or ba.fresh(), []
        for percent in percents:
            state, threshold, _ = ba.step(state, on_battery(percent), None)
            if threshold is not None:
                sent.append(threshold)
                state = ba.mark_sent(state, percent)
        return state, sent

    def test_each_level_sends_once_as_it_is_reached(self):
        _, sent = self.due_after(range(100, -1, -1))
        self.assertEqual(sent, [50, 25, 10, 5, 2])

    def test_each_level_is_reached_at_or_below_it(self):
        for threshold in ba.THRESHOLDS:
            with self.subTest(threshold=threshold):
                state, sent = self.due_after(range(100, threshold, -1))
                self.assertNotIn(threshold, sent)
                self.assertEqual(self.due_after([threshold], state)[1], [threshold])

    def test_several_crossed_at_once_send_the_lowest_and_the_rest_count_as_sent(self):
        state, threshold, _ = ba.step(ba.fresh(), on_battery(9), None)
        self.assertEqual(threshold, 10)
        state = ba.mark_sent(state, 9)
        self.assertEqual(state["sent"], [50, 25, 10])
        self.assertEqual(self.due_after([8, 7, 6, 5, 4, 3, 2, 1], state)[1], [5, 2])

    def test_unplugged_below_50_sends_the_50_alert_at_once(self):
        self.assertEqual(self.due_after([45, 44, 43])[1], [50])

    def test_ac_power_resets_the_levels(self):
        state, _ = self.due_after([50, 25])
        state, threshold, lines = ba.step(state, AC_READING, None)
        self.assertIsNone(threshold)
        self.assertEqual(state["sent"], [])
        self.assertIn("thresholds reset", lines[0])
        self.assertEqual(self.due_after([40, 30, 25], state)[1], [50, 25])

    def test_on_ac_power_nothing_is_sent_at_any_level(self):
        for percent in (50, 10, 2, 0):
            with self.subTest(percent=percent):
                self.assertIsNone(ba.step(ba.fresh(), {**AC_READING, "percent": percent}, None)[1])

    def test_an_unreadable_pmset_changes_nothing_and_logs_once(self):
        state, _ = self.due_after([50])
        unread, threshold, lines = ba.step(state, None, "pmset exited 1")
        self.assertIsNone(threshold)
        self.assertEqual(unread["sent"], [50])
        self.assertEqual(len(lines), 1)
        again, _, lines = ba.step(unread, None, "pmset exited 1")
        self.assertEqual(lines, [])
        back, threshold, lines = ba.step(again, on_battery(25), None)
        self.assertEqual((threshold, lines), (25, ["pmset readable again"]))

    def test_failures_retry_at_the_next_run_then_wait_longer(self):
        state, waits = ba.fresh(), []
        for _ in range(6):
            state = ba.mark_failed(state, NOW)
            waits.append(None if state["next_try"] is None else
                         (datetime.strptime(state["next_try"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                          - NOW).seconds)
        self.assertEqual(waits, [None, 120, 240, 480, 900, 900])
        self.assertTrue(ba.waiting(state, NOW + timedelta(seconds=899)))
        self.assertFalse(ba.waiting(state, NOW + timedelta(seconds=900)))
        self.assertEqual(ba.mark_sent(state, 22)["failures"], 0)


class Email(unittest.TestCase):
    def assertPassesTheGuard(self, subject, body):
        event = {"tool_name": SEND, "agent_type": "ceo",
                 "tool_input": {"to": [BOARD], "subject": subject, "body": body}}
        self.assertIsNone(board_email.form_reason(event, ROOT))

    def test_an_alert_names_the_level_the_board_s_time_and_the_time_left(self):
        subject, body = ba.alert(on_battery(22), 25, NOW)
        self.assertEqual(subject, "[CEO] Battery: 22%, the Mac is not plugged in")
        self.assertIn("22% at 23:40 +06, Thursday 2026-01-15", body)
        self.assertIn("as pmset prints it: 2:00 remaining", body)
        self.assertIn("Next alert at 10%", body)
        self.assertPassesTheGuard(subject, body)

    def test_the_2_percent_alert_is_the_last(self):
        subject, body = ba.alert(on_battery(2, "(no estimate)"), 2, NOW)
        self.assertIn("last alert", body)
        self.assertPassesTheGuard(subject, body)

    def test_the_test_email_has_its_subject_and_passes_the_guard(self):
        for reading, why in ((AC_READING, None), (None, "pmset exited 1")):
            with self.subTest(reading=reading):
                subject, body = ba.test_email(reading, why, NOW)
                self.assertEqual(subject, "[CEO] Test: battery alert")
                self.assertPassesTheGuard(subject, body)


class HeadlessRun(unittest.TestCase):
    def argv(self):
        return ba.claude_argv({"to": [BOARD], "subject": "[CEO] Battery: 22%", "body": "x"})

    def flag(self, name):
        argv = self.argv()
        self.assertEqual(argv.count(name), 1, name)
        return argv[argv.index(name) + 1]

    def test_only_the_gmail_send_tool_is_allowed(self):
        self.assertEqual(self.flag("--allowedTools"), SEND)
        self.assertEqual(self.flag("--tools"), "ToolSearch")  # no Bash, files, agents, skills or WebFetch
        # The account's settings (user) load because the claude.ai connectors, Gmail among them, start only with them
        # (battery_alert's docstring); the checkout's local settings stay out.
        self.assertEqual(self.flag("--setting-sources"), "user,project")
        self.assertNotIn("local", self.flag("--setting-sources").split(","))
        self.assertEqual(self.flag("--permission-mode"), "default")
        self.assertEqual(self.flag("--agent"), "ceo")
        joined = " ".join(self.argv()[3:])
        for loosener in ("--dangerously-skip-permissions", "bypassPermissions", "acceptEdits", "--add-dir",
                         "--mcp-config", "--settings ", "--plugin-dir", "--allow-dangerously"):
            with self.subTest(flag=loosener):
                self.assertNotIn(loosener, joined)
        self.assertNotIn(SEND, self.flag("--disallowedTools"))

    def test_every_mcp_server_the_project_allows_is_disallowed(self):
        settings = json.loads((ROOT / ".claude" / "settings.json").read_text())
        rules = [rule for rule in settings["permissions"]["allow"] if rule.startswith("mcp__")]
        denied = self.flag("--disallowedTools").split(",")
        for rule in rules:
            with self.subTest(rule=rule):
                self.assertTrue(any(rule == server or rule.startswith(server + "__") for server in denied))
        # The other rules are built-ins' (Bash(...)), and --tools leaves no built-in but ToolSearch.

    def test_every_mcp_tool_the_ceo_agent_names_but_the_gmail_send_is_disallowed(self):
        # The account's allow rules load, so a tool the ceo agent's tools line names would enter the run allowed:
        # only DISALLOWED keeps it out. A tool added to that line must be added there too.
        text = (ROOT / ".claude" / "agents" / "executive" / "ceo.md").read_text(encoding="utf-8")
        line = re.search(r"^tools:(.*)$", text.split("\n---", 1)[0], re.M).group(1)
        entries = [entry.strip() for entry in line.split(",") if entry.strip().startswith("mcp__")]
        self.assertIn(SEND, entries)
        denied = self.flag("--disallowedTools").split(",")
        for entry in entries:
            if entry == SEND:
                continue
            with self.subTest(entry=entry):
                server = entry[:-3] if entry.endswith("__*") else entry
                self.assertTrue(any(server == rule or server.startswith(rule + "__") for rule in denied))

    def test_the_run_searches_twice_for_gmail_and_has_the_turns_for_it(self):
        self.assertIn("search once more", self.argv()[2])
        self.assertEqual(self.flag("--max-turns"), "5")

    def test_settings_that_would_bill_an_api_key_are_a_reason(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "settings.json"
            self.assertIsNone(ba.api_key_reason(path))  # no account settings: nothing loads
            cases = [({"env": {"ENABLE_TOOL_SEARCH": "1"}, "permissions": {}}, None),
                     ({"apiKeyHelper": "/bin/echo never-shown"}, "apiKeyHelper"),
                     ({"env": {"ANTHROPIC_API_KEY": "never-shown"}}, "ANTHROPIC_API_KEY"),
                     ({"env": {"ANTHROPIC_AUTH_TOKEN": "never-shown", "X": "1"}}, "ANTHROPIC_AUTH_TOKEN"),
                     ([], "not a settings object")]
            for settings, expected in cases:
                with self.subTest(settings=settings):
                    path.write_text(json.dumps(settings))
                    reason = ba.api_key_reason(path)
                    if expected is None:
                        self.assertIsNone(reason)
                    else:
                        self.assertIn(expected, reason)
                        self.assertNotIn("never-shown", reason)  # names only, never a value
            path.write_text("{not json")
            self.assertIn("unreadable", ba.api_key_reason(path))

    def test_the_run_drops_api_keys_and_uses_the_jobs_account(self):
        environ = {"ANTHROPIC_API_KEY": "k", "ANTHROPIC_AUTH_TOKEN": "t", "HOME": "/h", "CLAUDE_CONFIG_DIR": "/other"}
        with mock.patch.dict(ba.os.environ, environ, clear=True), \
                mock.patch.dict(ba.JOB_ENV, {"CLAUDE_CONFIG_DIR": "/job"}), \
                mock.patch.object(ba.subprocess, "run", return_value=mock.Mock(returncode=0, stdout="")) as run:
            ba.run_claude(["claude"], Path("/repo"))
        env = run.call_args.kwargs["env"]
        self.assertNotIn("ANTHROPIC_API_KEY", env)
        self.assertNotIn("ANTHROPIC_AUTH_TOKEN", env)
        self.assertEqual(env["CLAUDE_CONFIG_DIR"], "/job")
        self.assertEqual(run.call_args.kwargs["cwd"], Path("/repo"))

    def test_the_run_sets_the_marker_that_keeps_the_ceos_stop_hook_out(self):
        sys.path.insert(0, str(ROOT / "scripts" / "hooks"))
        import capacity_heartbeat
        with mock.patch.dict(ba.os.environ, {}, clear=True), \
                mock.patch.object(ba.subprocess, "run", return_value=mock.Mock(returncode=0, stdout="")) as run:
            ba.run_claude(["claude"], Path("/repo"))
        self.assertTrue(run.call_args.kwargs["env"].get(capacity_heartbeat.JOB))

    def test_the_stream_says_sent_failed_or_unknown(self):
        cases = [
            (stream(tool_use(), tool_result(), result()), True),
            (stream(tool_use(), tool_result(True, "Blocked: the subject must be one line"), result()), False),
            (stream(tool_use(), result()), None),  # cut off before the result
            (stream(result(text="SENT")), None),  # the model's words alone prove nothing
            (stream(result([{"tool_name": SEND}], "NOT SENT")), None),
            (stream(tool_use("mcp__claude_ai_Gmail__create_draft"), tool_result(), result()), None),
            ("not json\n", None),
            ("", None),
        ]
        for output, expected in cases:
            with self.subTest(output=output[:80]):
                self.assertIs(ba.read_stream(output)[0], expected)


class Send(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / ".git").mkdir()  # a main checkout, where the guard's log lives
        self.log = self.root / "workspaces" / "system" / "notify-log.jsonl"
        self.settings = self.root / "account-settings.json"  # not the real account's: none, unless a test writes it
        patcher = mock.patch.object(ba, "ACCOUNT_SETTINGS", self.settings)
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        self.tmp.cleanup()

    def runner(self, output, guard_logs=None, code=0):
        def run(argv, root):
            self.argv = argv
            if guard_logs:
                board_email.count_reason(root, guard_logs)
            return code, output
        return run

    def test_a_clean_stream_is_sent(self):
        self.assertEqual(ba.send(self.root, "[CEO] Battery: 22%", "b", self.runner(stream(tool_use(), tool_result()))),
                         (True, "sent"))

    def test_an_unclear_run_the_guard_logged_counts_as_sent(self):
        sent, why = ba.send(self.root, "[CEO] Battery: 22%", "b", self.runner("", "[CEO] Battery: 22%", None))
        self.assertTrue(sent)
        self.assertIn("the guard logged it", why)

    def test_an_unclear_run_the_guard_didnt_log_is_not_sent(self):
        board_email.count_reason(self.root, "[CEO] Battery: 22%")  # it logs an earlier one; the time check
        with mock.patch.object(ba, "utc_now", return_value=datetime.now(timezone.utc) + timedelta(seconds=5)):
            sent, why = ba.send(self.root, "[CEO] Battery: 22%", "b", self.runner("", None, None))
        self.assertFalse(sent)
        self.assertIn("ran out of time", why)

    def test_an_explicit_error_is_not_sent_even_if_the_guard_logged_it(self):
        output = stream(tool_use(), tool_result(True, "Gmail: 503"), result())
        sent, why = ba.send(self.root, "[CEO] Battery: 22%", "b", self.runner(output, "[CEO] Battery: 22%"))
        self.assertFalse(sent)
        self.assertIn("Gmail: 503", why)

    def test_an_email_the_guard_would_refuse_never_starts_claude(self):
        def never(argv, root):
            raise AssertionError("claude started")
        sent, why = ba.send(self.root, "[CEO] " + "x" * 300, "b", never)
        self.assertFalse(sent)
        self.assertIn("the guard would refuse it", why)

    def test_account_settings_with_an_api_key_never_start_claude(self):
        def never(argv, root):
            raise AssertionError("claude started")
        self.settings.write_text(json.dumps({"apiKeyHelper": "/bin/echo never-shown"}))
        sent, why = ba.send(self.root, "[CEO] Battery: 22%", "b", never)
        self.assertFalse(sent)
        self.assertIn("refused, SA-002", why)


class Off(unittest.TestCase):
    """Nothing is read, sent or installed off macOS, until company.json switches it on, or while it can't be read."""

    def company(self, **own):
        return mock.patch.object(company_config, "load", lambda root=None: {**company_config.DEFAULTS, **own})

    def broken(self):
        return mock.patch.object(company_config, "load", side_effect=ValueError("not JSON"))

    def cases(self):
        on = {"battery_alert": {}}
        return [(mock.patch.object(ba.sys, "platform", "linux"), "macOS only"),
                (self.company(board_email=BOARD), "no battery_alert integration"),
                (self.company(integrations=on), "no board_email"),
                (self.company(board_email=BOARD, integrations=on, timezone="No/Where"), "can't be read"),
                (self.broken(), "can't be read")]

    def test_no_email_leaves_and_no_claude_starts(self):
        def never(argv, root):
            raise AssertionError("claude started")
        for patcher, why in self.cases():
            with self.subTest(why=why), patcher:
                sent, said = ba.send(Path("/nowhere"), "[CEO] Battery: 22%", "b", never)
                self.assertFalse(sent)
                self.assertIn(why, said)

    def test_no_command_does_anything(self):
        for patcher, why in self.cases():
            for command, code in (("run", 0), ("test", 2), ("install", 2)):
                with self.subTest(why=why, command=command), patcher, mock.patch("builtins.print") as said, \
                        mock.patch.object(ba.subprocess, "run") as run, mock.patch.object(ba, "locked") as locked:
                    self.assertEqual(ba.main([command]), code)
                    self.assertIn(why, said.call_args.args[0])
                run.assert_not_called()
                locked.assert_not_called()


class Runs(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.sent, self.ok = [], True

    def tearDown(self):
        self.tmp.cleanup()

    def sender(self, root, subject, body):
        self.sent.append(subject)
        return (True, "sent") if self.ok else (False, "no network")

    def run_at(self, reading, now=NOW):
        reader = (lambda: (reading, None)) if reading else (lambda: (None, "pmset exited 1"))
        with mock.patch("sys.stdout"):
            return ba.run_once(self.root, reader, self.sender, now)

    def state(self):
        return json.loads((self.root / ba.STATE).read_text())

    def test_a_discharge_sends_one_email_per_level_and_ac_resets(self):
        for percent in (80, 50, 49, 30, 25, 9, 5, 4, 2, 1):
            self.run_at(on_battery(percent))
        self.assertEqual(self.sent, [f"[CEO] Battery: {p}%, the Mac is not plugged in" for p in (50, 25, 9, 5, 2)])
        self.run_at(AC_READING)
        self.assertEqual(self.state()["sent"], [])
        self.run_at(on_battery(48))
        self.assertEqual(len(self.sent), 6)

    def test_a_failed_send_is_retried_at_the_next_run_then_later(self):
        self.ok = False
        self.run_at(on_battery(49), NOW)
        self.assertEqual(self.state()["failures"], 1)
        self.run_at(on_battery(49), NOW + timedelta(seconds=60))  # the next run
        self.assertEqual(len(self.sent), 2)
        self.run_at(on_battery(49), NOW + timedelta(seconds=120))  # waits 2 minutes after the second failure
        self.assertEqual(len(self.sent), 2)
        self.ok = True
        self.run_at(on_battery(48), NOW + timedelta(seconds=180))
        self.assertEqual(len(self.sent), 3)
        self.assertEqual((self.state()["sent"], self.state()["failures"]), ([50], 0))

    def test_an_unreadable_pmset_sends_nothing_and_exits_1(self):
        self.assertEqual(self.run_at(None), 1)
        self.assertEqual(self.sent, [])
        self.assertEqual(self.state()["unreadable"], "pmset exited 1")

    def test_the_state_lives_in_workspaces_system(self):
        self.run_at(on_battery(50))
        self.assertEqual(ba.STATE, Path("workspaces/system/battery-alert.json"))
        self.assertEqual(self.state()["sent"], [50])

    def test_a_run_while_another_holds_the_lock_sends_nothing(self):
        (self.root / ba.LOCK).parent.mkdir(parents=True)
        with open(self.root / ba.LOCK, "a") as held:
            fcntl.flock(held, fcntl.LOCK_EX)
            self.assertEqual(self.run_at(on_battery(10)), 0)
        self.assertEqual(self.sent, [])

    def test_the_test_command_sends_the_test_email_and_changes_no_state(self):
        with mock.patch("sys.stdout"):
            self.assertEqual(ba.test(self.root, lambda: (on_battery(22), None), self.sender), 0)
        self.assertEqual(self.sent, ["[CEO] Test: battery alert"])
        self.assertFalse((self.root / ba.STATE).exists())


class Launchd(unittest.TestCase):
    def test_the_job_runs_every_60_seconds_on_apples_python(self):
        job = ba.job()
        self.assertEqual(job["StartInterval"], 60)
        self.assertEqual(job["ProgramArguments"][0], "/usr/bin/python3")
        self.assertEqual(job["ProgramArguments"][2], "run")
        self.assertEqual(job["EnvironmentVariables"], ba.JOB_ENV)

    def test_install_refuses_a_worktree(self):
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / ".git").write_text("gitdir: /elsewhere\n")
            with mock.patch.object(ba, "REPO", Path(folder)), mock.patch("builtins.print"), \
                    mock.patch.object(ba.subprocess, "run") as run:
                self.assertEqual(ba.install(), 2)
            run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
