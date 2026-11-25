"""Tests for how the Board desk reads company.json (docs/board-desk.md, "Settings"): off unless it has settings, nothing
run on a file that can't be read, the founder's time zone, and what doesn't run elsewhere than macOS. The scripts run
from a copy with a company.json of its own and an empty home: nothing here reads the checkout's settings, calls a model
or the network, or touches a job."""

import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(SCRIPTS), str(SCRIPTS / "board_desk")]

JOBS = ("run", "hour", "day", "read")
TYPED = (["wait"], ["setup"], ["attribution", "--board", "someone"], ["readback"], ["install"])
BROKEN = ("{", "[]", '{"integrations": null}', '{"timezone": "No/Such_Zone"}', '{"integrations": {"board_desk": {"pages": 3}}}')


class Copy(unittest.TestCase):
    """A copy of scripts/, without the tests, with a company.json of its own."""

    def copy(self, company=None) -> Path:
        root = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        shutil.copytree(SCRIPTS, root / "scripts", ignore=shutil.ignore_patterns("tests", "__pycache__"))
        if company is not None:
            (root / "company.json").write_text(company if isinstance(company, str) else json.dumps(company))
        (root / "home").mkdir()
        return root

    def python(self, root, *argv):
        return subprocess.run([sys.executable, *argv], cwd=root, capture_output=True, text=True, timeout=60,
                              env={"HOME": str(root / "home"), "PATH": os.defpath, "PYTHONDONTWRITEBYTECODE": "1"})

    def desk(self, root, *argv):
        return self.python(root, "scripts/board_desk.py", *argv)

    @staticmethod
    def files(root):
        return {path: path.read_bytes() for path in root.rglob("*") if path.is_file()}


class Off(Copy):
    def test_the_desk_is_off_until_company_json_has_its_settings(self):
        """No file, no such integration, or `false` or `null` for it: a job's command says so and ends well, one
        someone typed refuses, and nothing is written."""
        for company in (None, {}, {"integrations": {}}, {"integrations": {"board_desk": False}},
                        {"integrations": {"board_desk": None}}):
            root = self.copy(company)
            before = self.files(root)
            for argv, code in [([job], 0) for job in JOBS] + [(argv, 2) for argv in TYPED]:
                with self.subTest(company=company, argv=argv):
                    done = self.desk(root, *argv)
                    self.assertEqual((done.returncode, done.stderr), (code, ""))
                    self.assertIn(f"{argv[0]}: the Board desk is off", done.stdout)
            self.assertEqual(self.files(root), before)

    def test_a_company_json_that_can_t_be_read_runs_nothing(self):
        for company in BROKEN:
            root = self.copy(company)
            before = self.files(root)
            for argv in [[job] for job in JOBS] + list(TYPED):
                with self.subTest(company=company, argv=argv):
                    done = self.desk(root, *argv)
                    self.assertNotEqual(done.returncode, 0)
                    self.assertEqual(done.stdout, "")
                    self.assertRegex(done.stderr, r"company_config\.py|adapter_notion\.py")  # the file, not an import
            self.assertEqual(self.files(root), before)

    def test_a_wrong_zone_or_pages_value_doesn_t_stop_uninstall(self):
        ask = ("import sys; sys.path.insert(0, 'scripts'); import board_desk as d; d.uninstall = lambda: 7; "
               "print(d.main(['uninstall']))")
        for company in BROKEN[3:]:
            with self.subTest(company=company):
                done = self.python(self.copy(company), "-c", ask)
                self.assertEqual((done.stdout, done.stderr), ("7\n", ""))

    def test_the_scan_goes_on_with_a_company_json_that_can_t_be_read_and_names_it(self):
        ask = ("import sys; sys.path.insert(0, 'scripts'); import capacity_scan as s; print(s.BOARD_TZ, s.BOARD_DESK, "
               "s.answers_seal.ZONE_NAME, bool(s.CONFIG_FAULT))")
        for company in BROKEN[:4]:
            with self.subTest(company=company):
                done = self.python(self.copy(company), "-c", ask)
                self.assertEqual((done.stdout, done.stderr), ("UTC None UTC True\n", ""))


class Guard(Copy):
    ASK = ("import json, sys; sys.path.insert(0, 'scripts/hooks'); from board_desk_bash import desk_reason; "
           "print(json.dumps([bool(desk_reason(command, '/repo', ceo)) for command, ceo in json.loads(sys.argv[1])]))")

    def test_the_bash_guard_holds_whatever_company_json_says(self):
        commands = [("echo x >> knowledge/board/answers/2026-W02.md", False),
                    ("echo x >> knowledge/board/answers/2026-W02.md", True),
                    ("rm workspaces/board-desk/reader.json", False), ("python3 scripts/board_desk.py read", False),
                    ("python3 scripts/board_desk.py seal", True), ("python3 scripts/board_desk.py setup", False),
                    ("security find-generic-password -s board-desk-notion -w", False),
                    ("cat knowledge/board/answers/2026-W02.md", False), ("python3 scripts/board_desk.py wait", False),
                    ("python3 scripts/board_desk.py setup", True)]
        for company in (None, {}, {"integrations": {"board_desk": {}}}, {"integrations": {"board_desk": False}}, *BROKEN):
            with self.subTest(company=company):
                done = self.python(self.copy(company), "-c", self.ASK, json.dumps(commands))
                self.assertEqual(done.stderr, "")
                self.assertEqual(json.loads(done.stdout), [True] * 7 + [False] * 3)


class Settings(Copy):
    SHOW = ("import json, sys; sys.path.insert(0, 'scripts'); import board_desk as d; a = d.adapter_notion; "
            "print(json.dumps([d.SETTINGS, d.LABEL, d.READ_LABEL, d.job(True)['Label'], d.JOB_ENV.get('CLAUDE_CONFIG_DIR'), "
            "d.ZONE_NAME, d.REPOS, a.ROOT_TITLE, a.GITHUB, sorted(a.PAGES), d.capacity_scan.DESK_JOB]))")

    def shown(self, company):
        root = self.copy(company)
        done = self.python(root, "-c", self.SHOW)
        self.assertEqual(done.stderr, "")
        return root, json.loads(done.stdout)

    def test_an_empty_object_turns_the_desk_on_with_the_defaults(self):
        self.assertEqual(self.shown({"integrations": {"board_desk": {}}})[1], [
            {}, "com.agentic-company.board-desk", "com.agentic-company.board-desk-read",
            "com.agentic-company.board-desk-read", None, "UTC", [], "Board desk", "", ["company", "progress", "summaries"],
            "com.agentic-company.board-desk-read"])

    def test_each_setting_is_read(self):
        settings = {"launchd_label": "com.example.desk", "claude_config_dir": "~/.claude-desk", "root_title": "Acme desk",
                    "github": "https://github.com/example/company/blob/main/", "workflows": {"acme": "release.yml"},
                    "pages": {"progress": ["Progress", "knowledge/company/board-desk/progress.md"]}}
        root, shown = self.shown({"timezone": "America/New_York", "integrations": {"board_desk": settings},
                                  "products": {"acme": {"repo": "example/acme"}, "demo": {"repo": "example/demo"},
                                               "plain": {}}})
        self.assertEqual(shown, [
            settings, "com.example.desk", "com.example.desk-read", "com.example.desk-read",
            str(root / "home" / ".claude-desk"), "New York", [["example/acme", "release.yml"], ["example/demo", None]],
            "Acme desk", "https://github.com/example/company/blob/main/", ["progress"], "com.example.desk-read"])

    def test_a_github_address_with_no_last_slash_gets_one(self):
        settings = {"github": "https://github.com/example/company/blob/main"}
        self.assertEqual(self.shown({"integrations": {"board_desk": settings}})[1][8],
                         "https://github.com/example/company/blob/main/")

    def test_only_the_knowledge_base_s_pages_are_pushed(self):
        for page in ("company.json", "workspaces/x.md", "/etc/hosts", "knowledge/../company.json", "knowledge"):
            with self.subTest(page=page):
                done = self.desk(self.copy({"integrations": {"board_desk": {"pages": {"x": ["X", page]}}}}), "read")
                self.assertNotEqual(done.returncode, 0)
                self.assertEqual(done.stdout, "")
                self.assertIn(f"{page}, which isn't under knowledge/", done.stderr)


class Adapter(unittest.TestCase):
    """The Notion side, without Notion."""

    def setUp(self):
        import adapter_notion
        self.notion = adapter_notion

    def test_a_kb_link_stays_text_until_the_repo_s_address_is_set(self):
        page = "knowledge/company/board-desk/qa.md"
        with mock.patch.object(self.notion, "GITHUB", ""):
            self.assertEqual(self.notion.linked("See [asks](asks.md) and [it](https://example.com/x).", page, {}), [
                ("See ", None), ("asks", None), (" and ", None), ("it", "https://example.com/x"), (".", None)])
        with mock.patch.object(self.notion, "GITHUB", "https://github.com/example/company/blob/main/"):
            self.assertEqual(self.notion.target("../../board/charter.md#scope", page),
                             "https://github.com/example/company/blob/main/knowledge/board/charter.md#scope")

    def test_without_a_keychain_the_token_s_read_is_a_notion_error(self):
        with mock.patch.object(self.notion.subprocess, "run", side_effect=FileNotFoundError):
            with self.assertRaises(self.notion.NotionError) as raised:
                self.notion.keychain_token()
        self.assertIn("no Keychain here", str(raised.exception))

    def test_the_shipped_ids_file_is_no_desk(self):
        self.assertFalse(self.notion.ready({"databases": {}, "pages": {}, "root": ""}))
        self.assertFalse(self.notion.ready(None))


class Elsewhere(unittest.TestCase):
    def test_the_jobs_are_launchd_s_so_install_and_uninstall_do_nothing_elsewhere(self):
        import board_desk as desk
        for command in (desk.install, desk.uninstall):
            out = io.StringIO()
            with mock.patch.object(desk.sys, "platform", "linux"), redirect_stdout(out), \
                    mock.patch.object(desk.subprocess, "run", side_effect=AssertionError("ran a command")):
                self.assertEqual(command(), 2)
            self.assertIn("launchd is macOS only", out.getvalue())


class Zones(unittest.TestCase):
    """A day of the founder's zone, whatever its offset and its length."""

    DAYS = (("America/New_York", date(2026, 11, 1), 25), ("America/New_York", date(2026, 3, 8), 23),
            ("Europe/London", date(2026, 10, 25), 25), ("Asia/Kolkata", date(2026, 1, 5), 24), ("UTC", date(2026, 1, 5), 24))

    def test_each_hour_of_a_day_gets_its_line_and_the_page_reads_back(self):
        import board_desk as desk
        for zone, day, hours in self.DAYS:
            with self.subTest(zone=zone, day=day), mock.patch.object(desk, "ZONE", ZoneInfo(zone)):
                start, end = desk.day_window(day)
                self.assertEqual(end - start, timedelta(hours=hours))
                for entry in (None, "Done: hour {}."):
                    text = "# Progress\n\n## Spend\n\nSpend as of x\n"
                    for hour in range(hours):
                        head, spend, days = desk.parse_progress(text, strict=True)
                        at = start + timedelta(hours=hour)
                        desk.place(days, at, at + timedelta(hours=1), entry and [entry.format(hour)], 1)
                        text = desk.render_progress(head, spend, days)
                    days = desk.parse_progress(text, strict=True)[2]
                    self.assertEqual(list(days), [day])
                    if entry:
                        self.assertEqual(text.count("Done: hour "), hours)

    def test_a_utc_time_in_a_log_reads_in_the_founder_s_zone(self):
        import board_desk as desk
        with mock.patch.object(desk, "ZONE", ZoneInfo("America/New_York")), mock.patch.object(desk, "ZONE_NAME", "New York"):
            self.assertEqual(desk.local_times("landed 2026-01-05T02:30:00Z, again 2026-07-05T02:30Z"),
                             "landed 2026-01-04 21:30 New York, again 2026-07-04 22:30 New York")
            self.assertEqual(desk.due(date(2026, 1, 5)), datetime(2026, 1, 6, 10, tzinfo=ZoneInfo("America/New_York")))


if __name__ == "__main__":
    unittest.main()
