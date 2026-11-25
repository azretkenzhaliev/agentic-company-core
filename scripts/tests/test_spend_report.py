"""Tests for scripts/spend_report.py.

gh and vercel are always faked: nothing here reads the network. The Vercel guard is the real hook, run locally."""

import contextlib
import io
import json
import subprocess
import sys
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

import company_config  # noqa: E402
import spend_report  # noqa: E402

UTC = timezone.utc
NOON = datetime(2026, 11, 11, 12, 0, tzinfo=UTC)  # 18:00 in Dhaka
NOVEMBER = datetime(2026, 11, 1, tzinfo=UTC)
DECEMBER = datetime(2026, 12, 1, tzinfo=UTC)
CANARY = "CANARY-a-tool-said-this"


def setUpModule():
    """A company that names both vendors, six hours ahead of UTC, whatever this machine's company.json says."""
    for name, value in (("GITHUB_ORG", "acme"), ("GITHUB_POOL", 500.0), ("VERCEL_SCOPE", "acme"),
                        ("VERCEL_CREDIT", 20.0), ("BOARD_TZ", ZoneInfo("Asia/Dhaka")), ("FAULT", None),
                        ("VERCEL_USAGE", ["vercel", "usage", "--scope", "acme", "--breakdown", "daily", "--json"]),
                        ("MANUAL", [("OpenAI API pool", "the Board's balance"),
                                    ("Claude subscription (SA-002)", "a flat fee: no money beyond the plan")])):
        patcher = mock.patch.object(spend_report, name, value)
        patcher.start()
        unittest.addModuleCleanup(patcher.stop)


def answer(payload, returncode=0):
    return subprocess.CompletedProcess([], returncode, stdout=json.dumps(payload), stderr=f"tool says {CANARY}")


def github_answer(days: dict, other=0.0):
    items = [{"date": f"{day}T00:00:00Z", "product": "Actions", "sku": "Actions Linux", "grossAmount": amount,
              "netAmount": 0, "repositoryName": CANARY} for day, amount in days.items()]
    items.append({"date": "2026-11-02T00:00:00Z", "product": "Packages", "grossAmount": other})
    return {"usageItems": items}


def vercel_answer(days: dict, start="2026-10-20T08:00:00.000Z", end="2026-11-20T08:00:00.000Z", unit="USD"):
    return {
        "period": {"from": start, "to": end}, "context": CANARY, "costUnit": unit,
        "breakdown": {"period": "daily", "data": [
            {"periodKey": day, "services": [
                {"name": "Build CPU Minutes", "cost": amount, "category": "usage"},
                {"name": "Pro seats", "cost": 20.0, "category": "subscription"},
            ], "totals": {"cost": amount + 20.0}} for day, amount in days.items()]},
    }


class Paces(unittest.TestCase):
    def test_today_scaled_to_a_day_and_yesterday_prorated_into_the_last_24_hours(self):
        daily = {date(2026, 11, 10): 24.0, date(2026, 11, 11): 6.0}
        last_24, today = spend_report.paces(daily, UTC, NOVEMBER, NOON)
        self.assertAlmostEqual(today, 12.0)  # $6 in 12 hours
        self.assertAlmostEqual(last_24, 18.0)  # $6 today + half of yesterday's $24

    def test_a_day_with_no_figure_counts_as_nothing_spent(self):
        last_24, today = spend_report.paces({date(2026, 11, 10): 24.0}, UTC, NOVEMBER, NOON)
        self.assertEqual(today, 0.0)
        self.assertAlmostEqual(last_24, 12.0)

    def test_no_pace_for_today_in_its_first_hour(self):
        _, today = spend_report.paces({date(2026, 11, 11): 1.0}, UTC, NOVEMBER, NOON.replace(hour=0, minute=30))
        self.assertIsNone(today)

    def test_no_last_24_hours_on_the_cycles_first_day(self):
        last_24, today = spend_report.paces({date(2026, 11, 1): 6.0}, UTC, NOVEMBER, NOVEMBER.replace(hour=12))
        self.assertIsNone(last_24)
        self.assertAlmostEqual(today, 12.0)

    def test_the_vendors_own_day(self):
        # 12:00Z is 04:00 in Los Angeles: its day is 11-11, four hours old.
        last_24, today = spend_report.paces({date(2026, 11, 11): 1.0, date(2026, 11, 10): 6.0},
                                            spend_report.LOS_ANGELES, NOVEMBER, NOON)
        self.assertAlmostEqual(today, 6.0)
        self.assertAlmostEqual(last_24, 1.0 + 6.0 * 20 / 24)


class Projection(unittest.TestCase):
    def test_spend_plus_pace_times_the_time_left(self):
        self.assertAlmostEqual(spend_report.projection(420.0, 10.0, NOON, DECEMBER), 420.0 + 10.0 * 19.5)

    def test_the_day_the_cap_is_passed(self):
        self.assertEqual(spend_report.passes(500.0, 420.0, 10.0, NOON, DECEMBER), NOON + timedelta(days=8))
        self.assertIsNone(spend_report.passes(500.0, 420.0, 1.0, NOON, DECEMBER))  # 80 days: not this cycle
        self.assertIsNone(spend_report.passes(500.0, 420.0, 0.0, NOON, DECEMBER))

    def test_a_tiny_pace_never_overflows(self):
        for cap, spent, pace in ((500.0, 420.0, 1e-05), (500.0, 0.0, 1e-04), (20.0, 19.0, 1e-07), (500.0, 0.0, 5e-324)):
            self.assertIsNone(spend_report.passes(cap, spent, pace, NOON, DECEMBER), pace)

    def test_the_day_spend_reached_the_cap(self):
        daily = {date(2026, 11, 3): 15.0, date(2026, 11, 1): 10.0, date(2026, 11, 5): 1.0}
        self.assertEqual(spend_report.passed_on(20.0, daily), date(2026, 11, 3))
        self.assertIsNone(spend_report.passed_on(100.0, daily))


class VendorLine(unittest.TestCase):
    def line(self, daily, cap=500.0, now=NOON):
        return spend_report.vendor_line("GitHub Actions", "pool", cap, "the billing API", daily, UTC,
                                        NOVEMBER, DECEMBER, now)

    def test_projected_over_names_both_paces_and_their_dates_in_the_companys_zone(self):
        over, line = self.line({date(2026, 11, 1): 400.0, date(2026, 11, 10): 24.0, date(2026, 11, 11): 6.0})
        self.assertTrue(over)
        self.assertTrue(line.startswith("PROJECTED OVER GitHub Actions: pool $500.00, cycle 11-01 06:00 to "
                                        "12-01 06:00 | spent $430.00, read 11-11 18:00 (the billing API)"))
        # $70 left: at $18 a day 3.89 days (11-15 09:20Z), at $12 a day 5.83 days (11-17 08:00Z), both in Dhaka
        self.assertIn("$781.00 at the last 24 hours' pace ($18.00 a day), $664.00 at today's pace ($12.00 a day)", line)
        self.assertIn("passes $500.00: 11-15 at the last 24 hours' pace, 11-17 at today's pace", line)

    def test_under_says_not_this_cycle(self):
        over, line = self.line({date(2026, 11, 10): 2.4, date(2026, 11, 11): 0.6})
        self.assertFalse(over)
        self.assertTrue(line.startswith("GitHub Actions:"))
        self.assertIn("passes $500.00: not this cycle at the last 24 hours' pace, not this cycle at today's pace", line)

    def test_over_names_the_day_it_passed(self):
        over, line = self.line({date(2026, 11, 8): 490.0, date(2026, 11, 9): 20.0}, now=NOON)
        self.assertTrue(over)
        self.assertTrue(line.startswith("OVER GitHub Actions"))
        self.assertIn("passed $500.00 in its billing day 11-09 06:00 to 11-10 06:00", line)  # the UTC day, in Dhaka

    def test_a_fraction_of_a_cent_a_day_is_not_this_cycle(self):
        over, line = self.line({date(2026, 11, 10): 1e-07, date(2026, 11, 11): 1e-07})
        self.assertFalse(over)
        self.assertIn("passes $500.00: not this cycle at the last 24 hours' pace, not this cycle at today's pace", line)

    def test_no_pace_is_said_not_guessed(self):
        over, line = spend_report.vendor_line("V", "credit", 20.0, "s", {date(2026, 11, 1): 1.0}, UTC, NOVEMBER,
                                              DECEMBER, NOVEMBER.replace(minute=30))
        self.assertFalse(over)
        self.assertIn("no pace for the last 24 hours' (the cycle began today), no pace for today's (under an hour "
                      "into today)", line)
        self.assertIn("passes $20.00: no pace to project", line)


class Readers(unittest.TestCase):
    def test_github_counts_actions_gross_by_day_only(self):
        daily = spend_report.github_daily(github_answer({"2026-11-10": 2.5, "2026-11-11": 1.0}, other=99.0))
        self.assertEqual(daily, {date(2026, 11, 10): 2.5, date(2026, 11, 11): 1.0})

    def test_github_answer_it_cant_read(self):
        for bad in (None, [], {"message": "Not Found"}, {"usageItems": [{"product": "Actions", "grossAmount": 1}]},
                    {"usageItems": [{"product": "Actions", "date": "2026-11-01", "grossAmount": "1"}]},
                    {"usageItems": ["Actions"]}, {"usageItems": [{"date": "2026-11-01", "grossAmount": 1}]}):
            self.assertIsNone(spend_report.github_daily(bad), bad)

    def test_github_nan_or_infinity_isnt_a_number(self):
        for amount in (float("nan"), float("inf"), float("-inf")):
            bad = json.loads(json.dumps(github_answer({"2026-11-10": amount})))  # json.loads gives NaN and Infinity
            self.assertIsNone(spend_report.github_daily(bad), amount)

    def test_github_net_is_shown_only_when_every_actions_item_has_one(self):
        good = github_answer({"2026-11-10": 2.5, "2026-11-11": 1.0})
        self.assertEqual(spend_report.github_net(good), 0.0)
        del good["usageItems"][0]["netAmount"]
        self.assertIsNone(spend_report.github_net(good))

    def test_vercel_counts_usage_by_los_angeles_day_and_leaves_out_seats(self):
        daily, start, end = spend_report.vercel_reading(vercel_answer({"2026-11-10": 0.5, "2026-11-11": 0.25}))
        self.assertEqual(daily, {date(2026, 11, 10): 0.5, date(2026, 11, 11): 0.25})
        self.assertEqual((start.day, end.day, end.hour), (20, 20, 8))

    def test_vercel_answer_it_cant_read(self):
        for bad in (None, {}, vercel_answer({"2026-11-10": 1.0}, unit="managed_infrastructure_units"),
                    {**vercel_answer({}), "breakdown": None}):
            self.assertIsNone(spend_report.vercel_reading(bad))

    def test_vercel_nan_or_infinity_isnt_a_number(self):
        for amount in (float("nan"), float("inf")):
            self.assertIsNone(spend_report.vercel_reading(vercel_answer({"2026-11-10": amount})), amount)


class TheVercelGuard(unittest.TestCase):
    """The real hook, as Claude Code runs it: no network."""

    def test_lets_the_usage_read_through(self):
        self.assertFalse(spend_report.refused_by_guard(spend_report.VERCEL_USAGE))

    def test_a_refusal_counts(self):
        self.assertTrue(spend_report.refused_by_guard(["vercel", "deploy", "--scope", "acme"]))

    def assert_refused_and_vercel_never_runs(self, *patches):
        with contextlib.ExitStack() as stack:
            for patch in patches:
                stack.enter_context(patch)
            run_json = stack.enter_context(mock.patch.object(spend_report, "run_json"))
            self.assertTrue(spend_report.refused_by_guard(spend_report.VERCEL_USAGE))
            _, line = spend_report.vercel_line()
        run_json.assert_not_called()
        self.assertIn("not read here (scripts/hooks/guard_vercel_cli.py refuses", line)

    def test_a_missing_guard_counts_as_a_refusal(self):
        self.assert_refused_and_vercel_never_runs(
            mock.patch.object(spend_report, "VERCEL_GUARD", SCRIPTS / "hooks" / "no_such_guard.py"))

    def test_a_guard_that_times_out_counts_as_a_refusal(self):
        self.assert_refused_and_vercel_never_runs(
            mock.patch.object(spend_report.subprocess, "run", side_effect=subprocess.TimeoutExpired("guard", 30)))

    def test_a_guard_that_cant_start_counts_as_a_refusal(self):
        self.assert_refused_and_vercel_never_runs(
            mock.patch.object(spend_report.subprocess, "run", side_effect=OSError("no python")))


class Report(unittest.TestCase):
    """The whole output, with gh and vercel faked."""

    def run_report(self, gh=None, vercel=None, guard_refuses=False):
        calls = []

        def fake_run(argv, **_):
            calls.append(argv[0])
            reply = {"gh": gh, "vercel": vercel}[argv[0]]
            if isinstance(reply, Exception):
                raise reply
            return reply

        out = io.StringIO()
        with mock.patch.object(spend_report, "utc_now", return_value=NOON), \
                mock.patch.object(spend_report, "refused_by_guard", return_value=guard_refuses), \
                mock.patch.object(spend_report.subprocess, "run", side_effect=fake_run), \
                contextlib.redirect_stdout(out):
            self.assertEqual(spend_report.main(), 0)
        return out.getvalue(), calls

    def test_one_line_per_vendor_in_the_ledgers_order_over_first(self):
        text, _ = self.run_report(gh=answer(github_answer({"2026-11-10": 1.0, "2026-11-11": 0.5})),
                                  vercel=answer(vercel_answer({"2026-11-09": 23.0, "2026-11-11": 0.3})))
        lines = text.splitlines()
        self.assertEqual(lines[0], "Spend as of 11-11 18:00 Asia/Dhaka (all times Asia/Dhaka; over or projected "
                                   "over first; projections are arithmetic at the pace named)")
        names = [line.split(":")[0] for line in lines[1:]]
        self.assertEqual(names, ["- OVER Vercel", "- GitHub Actions", "- OpenAI API pool",
                                 "- Claude subscription (SA-002)"])
        self.assertIn("(GitHub's billing API, Actions gross; $0.00 of it billed (net))", lines[2])
        self.assertIn("passed $20.00 in its billing day 11-09 14:00 to 11-10 14:00", lines[1])  # Los Angeles' day
        self.assertIn("cycle 10-20 14:00 to 11-20 14:00", lines[1])
        self.assertIn("OpenAI API pool: manual, from knowledge/finance/spend.md (the Board's balance)", text)
        self.assertNotIn(CANARY, text)

    def test_cant_read_names_who_reads_it_and_never_prints_the_tools_text(self):
        text, _ = self.run_report(gh=answer({"message": CANARY}, returncode=1), vercel=FileNotFoundError(CANARY))
        self.assertIn("- GitHub Actions: not read here (the billing API gave no answer this script can "
                      "read); read by the CTO (GitHub's billing page)", text)
        self.assertIn("- Vercel: not read here (`vercel usage` gave no answer this script can "
                      "read); read by the CTO (Vercel's usage page)", text)
        self.assertNotIn(CANARY, text)

    def test_an_error_while_reading_one_vendor_turns_only_its_line(self):
        with mock.patch.object(spend_report, "github_line", side_effect=OverflowError(CANARY)):
            text, _ = self.run_report(vercel=answer(vercel_answer({"2026-11-11": 0.3})))
        self.assertIn("- GitHub Actions: not read here (this script failed on its answer); read by the CTO "
                      "(GitHub's billing page)", text)
        self.assertIn("Vercel: credit $20.00, cycle 10-20 14:00 to 11-20 14:00 | spent $0.30", text)
        self.assertEqual(len(text.splitlines()), 5)
        self.assertNotIn(CANARY, text)

    def test_a_guard_refusal_means_vercel_never_runs(self):
        text, calls = self.run_report(gh=answer(github_answer({})), vercel=AssertionError("vercel ran"),
                                      guard_refuses=True)
        self.assertNotIn("vercel", calls)
        self.assertIn("- Vercel: not read here (scripts/hooks/guard_vercel_cli.py refuses "
                      "`vercel usage --scope acme --breakdown daily --json`); read by the CTO", text)

    def test_a_vercel_answer_with_no_billing_cycle_isnt_projected(self):
        text, _ = self.run_report(gh=answer(github_answer({})),
                                  vercel=answer(vercel_answer({"2026-11-11": 1.0}, start="2026-11-01T07:00:00Z",
                                                              end="2026-11-11T11:59:00Z")))
        self.assertIn("- Vercel: not read here (`vercel usage` named no billing cycle)", text)

    def test_december_asks_for_december_and_its_cycle_ends_in_january(self):
        asked = []

        def fake_run(argv, **_):
            asked.append(argv)
            return answer(github_answer({"2026-12-15": 1.0}))

        with mock.patch.object(spend_report, "utc_now", return_value=datetime(2026, 12, 15, 12, tzinfo=UTC)), \
                mock.patch.object(spend_report.subprocess, "run", side_effect=fake_run):
            _, line = spend_report.github_line()
        self.assertEqual(asked[0][-1], "/organizations/acme/settings/billing/usage?year=2026&month=12")
        self.assertIn("cycle 12-01 06:00 to 01-01 06:00", line)

    def test_the_commands_are_read_only(self):
        _, calls = self.run_report(gh=answer(github_answer({})), vercel=answer(vercel_answer({})))
        self.assertEqual(calls, ["gh", "vercel"])
        self.assertEqual(spend_report.VERCEL_USAGE[:2], ["vercel", "usage"])
        self.assertTrue(spend_report.GITHUB_USAGE.startswith("/organizations/{org}/settings/billing/usage?"))

    def test_a_vendor_company_json_doesnt_name_is_never_read(self):
        with mock.patch.object(spend_report, "GITHUB_ORG", None), mock.patch.object(spend_report, "VERCEL_SCOPE", None):
            text, calls = self.run_report()
        self.assertEqual(calls, [])
        self.assertEqual([line.split(":")[0] for line in text.splitlines()[1:]],
                         ["- OpenAI API pool", "- Claude subscription (SA-002)"])


class Settings(unittest.TestCase):
    def read(self, **own):
        with mock.patch.object(company_config, "load", return_value={**company_config.DEFAULTS, **own}):
            return spend_report.settings()

    def test_off_by_default(self):
        own, zone, fault = self.read()
        self.assertEqual((own, str(zone), fault), ({"manual": {}}, "UTC", None))

    def test_what_company_json_names(self):
        own, zone, fault = self.read(timezone="Asia/Dhaka", integrations={"spend": {"github_org": "acme"}})
        self.assertEqual((own["github_org"], str(zone), fault), ("acme", "Asia/Dhaka", None))

    def test_a_company_json_it_cant_read_is_said_and_names_no_vendor(self):
        for own in ({"integrations": {"spend": "acme"}}, {"integrations": {"spend": {"manual": 5}}},
                    {"timezone": "No/Where"}, {"integrations": None}):
            settings, zone, fault = self.read(**own)
            self.assertEqual((settings, zone), ({"manual": {}}, UTC), own)
            self.assertIn("company.json can't be read", fault)
        with mock.patch.object(company_config, "load", side_effect=ValueError(CANARY)):
            self.assertEqual(spend_report.settings()[2], "company.json can't be read (ValueError)")
        out = io.StringIO()
        with mock.patch.object(spend_report, "FAULT", "company.json can't be read (ValueError)"), \
                mock.patch.object(spend_report, "GITHUB_ORG", None), \
                mock.patch.object(spend_report, "VERCEL_SCOPE", None), contextlib.redirect_stdout(out):
            self.assertEqual(spend_report.main(), 0)
        self.assertIn("- company.json can't be read (ValueError): no vendor is read", out.getvalue())


class Flags(unittest.TestCase):
    """--help, or a flag it doesn't take, prints the usage and exits before any call."""

    def exits_without_a_call(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(spend_report.subprocess, "run", side_effect=AssertionError("a call")) as run, \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as done:
            spend_report.main(argv)
        run.assert_not_called()
        return done.exception.code, out.getvalue() + err.getvalue()

    def test_help_prints_the_usage(self):
        code, text = self.exits_without_a_call(["--help"])
        self.assertEqual(code, 0)
        self.assertIn("usage:", text)

    def test_an_unknown_flag_prints_the_usage(self):
        for argv in (["--json"], ["now"], ["-x", "--help"]):
            code, text = self.exits_without_a_call(argv)
            self.assertIn("usage:", text, argv)
            self.assertNotEqual(code, None, argv)

    def test_the_command_line_reaches_main(self):
        done = subprocess.run([sys.executable, str(Path(spend_report.__file__)), "--bogus"], capture_output=True,
                              text=True, timeout=30, env={"PATH": "/nonexistent"})  # no gh or vercel to find
        self.assertEqual(done.returncode, 2)
        self.assertIn("usage:", done.stderr)
        self.assertEqual(done.stdout, "")


if __name__ == "__main__":
    unittest.main()
