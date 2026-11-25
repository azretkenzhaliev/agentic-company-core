"""Tests for scripts/token_report.py.

Every transcript is made up in a temporary folder and gh is always faked: nothing here reads a real session log or the network."""

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

import company_config  # noqa: E402
import token_report  # noqa: E402

ACME = {"acme": {"repo": "acme/app"}}
SINCE = "2026-01-05T12:00:00Z"
AFTER = "2026-01-05T13:00:00.000Z"
BEFORE = "2026-01-05T11:00:00.000Z"
CANARY = "CANARY-the-text-of-a-transcript"


def assistant(message_id, *, when=AFTER, model="claude-sonnet-5-5", read=0, written=0, written_1h=0, fresh=0, out=0):
    return {
        "type": "assistant",
        "timestamp": when,
        "message": {
            "id": message_id,
            "model": model,
            "content": [{"type": "text", "text": CANARY}],
            "usage": {
                "input_tokens": fresh,
                "cache_read_input_tokens": read,
                "cache_creation_input_tokens": written,
                "cache_creation": {"ephemeral_1h_input_tokens": written_1h, "ephemeral_5m_input_tokens": written - written_1h},
                "output_tokens": out,
            },
        },
    }


def gh_answer(payload, returncode=0):
    return subprocess.CompletedProcess([], returncode, stdout=json.dumps(payload), stderr=f"gh says {CANARY}")


def gh_quiet(arguments, **_):
    return gh_answer([])


class Base(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.session = Path(folder.name) / "session-1"
        (self.session / "subagents").mkdir(parents=True)

    def agent(self, name, role, records, raw_lines=()):
        path = self.session / "subagents" / f"agent-{name}.jsonl"
        lines = [json.dumps(record, separators=(",", ":")) for record in records] + list(raw_lines)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        meta = {"description": CANARY}
        if role is not None:
            meta["agentType"] = role
        path.with_suffix(".meta.json").write_text(json.dumps(meta), encoding="utf-8")
        return path

    def run_report(self, gh=gh_quiet, since=SINCE, products=ACME):
        out = io.StringIO()
        load = {"side_effect": products} if isinstance(products, Exception) else {"return_value": {"products": products}}
        with mock.patch.object(token_report.subprocess, "run", side_effect=gh), \
                mock.patch.object(company_config, "load", **load), \
                mock.patch.object(token_report.os, "getloadavg", return_value=(3.1, 4.2, 5.0)), \
                contextlib.redirect_stdout(out):
            code = token_report.main(["--since", since, "--session", str(self.session)])
        self.assertEqual(code, 0)
        return out.getvalue()

    def rows(self, since=SINCE):
        return token_report.role_rows(self.session, token_report.parse_time(since))


class Tokens(Base):
    def test_turns_mean_context_and_share(self):
        self.agent("a", "senior-engineer", [assistant("m1", read=100, written=20, fresh=5), assistant("m2", read=200, fresh=5)])
        self.agent("b", "code-reviewer", [assistant("m3", model="claude-opus-5-5", read=1000)])
        senior = 1.25 * (10 + 25 + 10 + 20 + 0 + 0)  # reads at 0.1, 5-minute writes at 1.25, input at 1
        reviewer = 2.5 * 100
        rows = {row[0]: row for row in self.rows()}
        self.assertEqual(rows["senior-engineer"][1:3], (2, 165))  # (125 + 205) / 2
        self.assertEqual(rows["code-reviewer"][1:3], (1, 1000))
        self.assertAlmostEqual(rows["code-reviewer"][3], 100 * reviewer / (senior + reviewer))
        self.assertEqual(self.rows()[0][0], "code-reviewer")

    def test_a_message_on_many_lines_is_one_turn_with_its_last_count(self):
        self.agent("a", "cto", [assistant("m1", read=100, out=1), assistant("m1", read=100, out=9), assistant("m1", read=100, out=9)])
        turns = {}
        path = self.session / "subagents" / "agent-a.jsonl"
        token_report.read_turns(path, "cto", token_report.parse_time(SINCE), turns)
        self.assertEqual(len(turns), 1)
        self.assertEqual(turns["m1"][2]["output_tokens"], 9)

    def test_the_same_message_in_two_transcripts_counts_once(self):
        self.agent("a", "cto", [assistant("m1", read=100)])
        self.agent("b", "cto", [assistant("m1", read=100)])
        self.assertEqual(self.rows()[0][1], 1)

    def test_turns_before_since_do_not_count(self):
        self.agent("a", "cto", [assistant("m1", when=BEFORE, read=999), assistant("m2", read=100)])
        self.assertEqual(self.rows()[0][1:3], (1, 100))

    def test_a_transcript_untouched_since_is_not_opened(self):
        path = self.agent("a", "cto", [assistant("m1", read=100)])
        old = token_report.parse_time(SINCE).timestamp() - 60
        os.utime(path, (old, old))
        self.assertEqual(self.rows(), [])

    def test_one_hour_cache_writes_weigh_more_than_five_minute_ones(self):
        five = token_report.weight("claude-sonnet-5-5", assistant("m", written=100)["message"]["usage"])
        hour = token_report.weight("claude-sonnet-5-5", assistant("m", written=100, written_1h=100)["message"]["usage"])
        self.assertAlmostEqual(five, 1.25 * 125)
        self.assertAlmostEqual(hour, 1.25 * 200)

    def test_output_weighs_five_times_input(self):
        usage = assistant("m", fresh=10, out=10)["message"]["usage"]
        self.assertAlmostEqual(token_report.weight("claude-haiku-5-5", usage), 0.16 * 60)

    def test_a_model_with_no_price_counts_at_the_dearest(self):
        usage = assistant("m", fresh=10)["message"]["usage"]
        self.assertEqual(token_report.weight("something-new", usage), token_report.weight("claude-opus-5-5", usage))

    def test_a_turn_with_no_tokens_is_not_a_turn(self):
        self.agent("a", "cto", [assistant("m1"), assistant("m2", read=10)])
        self.assertEqual(self.rows()[0][1], 1)

    def test_an_odd_line_is_skipped_unprinted(self):
        odd = [f'{{"usage": "{CANARY}"', f'["usage", "{CANARY}"]', f'{{"type":"assistant","usage":"{CANARY}"}}',
               json.dumps({"type": "assistant", "message": {"id": "x", "usage": CANARY}, "timestamp": AFTER}),
               json.dumps({"type": "assistant", "message": {"id": "y", "usage": {}}, "timestamp": CANARY})]
        self.agent("a", "cto", [assistant("m1", read=10)], raw_lines=odd)
        self.assertEqual(self.rows()[0][1], 1)
        self.assertNotIn(CANARY, self.run_report())

    def test_no_text_of_a_transcript_or_its_meta_in_the_output(self):
        self.agent("a", "senior-engineer", [assistant("m1", read=10, out=1)])
        output = self.run_report()
        self.assertIn("senior-engineer", output)
        self.assertNotIn(CANARY, output)

    def test_a_role_that_is_not_shaped_like_a_role_is_other(self):
        self.agent("a", f"senior engineer {CANARY}", [assistant("m1", read=10)])
        self.agent("b", {"text": CANARY}, [assistant("m2", read=10)])
        output = self.run_report()
        self.assertNotIn(CANARY, output)
        self.assertEqual({row[0] for row in self.rows()}, {"other"})

    def test_no_meta_file_is_unknown(self):
        path = self.agent("a", "cto", [assistant("m1", read=10)])
        path.with_suffix(".meta.json").unlink()
        self.assertEqual(self.rows()[0][0], "unknown")

    def test_no_turns_says_so(self):
        self.assertIn("No subagent turns", self.run_report())


class Sessions(Base):
    def test_the_default_session_is_the_one_that_last_started_an_agent(self):
        root = self.session.parent
        newer = root / "session-2" / "subagents"
        newer.mkdir(parents=True)
        os.utime(self.session / "subagents", (1000, 1000))
        with mock.patch.object(token_report, "projects_root", return_value=root):
            self.assertEqual(token_report.find_session(None), newer.parent)

    def test_a_session_id_is_looked_up_under_the_project(self):
        with mock.patch.object(token_report, "projects_root", return_value=self.session.parent):
            self.assertEqual(token_report.find_session("session-1"), self.session)

    def test_a_session_with_no_subagents_folder_is_an_error_not_no_spend(self):
        wrong = self.session.parent / "a-typo"
        err, out = io.StringIO(), io.StringIO()
        with mock.patch.object(token_report, "projects_root", return_value=self.session.parent), \
                contextlib.redirect_stderr(err), contextlib.redirect_stdout(out):
            self.assertEqual(token_report.main(["--since", SINCE, "--session", "a-typo"]), 1)
        self.assertIn(str(wrong), err.getvalue())
        self.assertEqual(out.getvalue(), "")

    def test_a_folder_with_no_subagents_folder_is_an_error_too(self):
        folder = self.session.parent / "plain-folder"
        folder.mkdir()
        with self.assertRaises(FileNotFoundError):
            token_report.find_session(str(folder))

    def test_the_project_folder_follows_claude_code_s_naming(self):
        with mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": "/config"}), \
                mock.patch.object(token_report, "REPO_ROOT", Path("/home/a/agentic-company")):
            self.assertEqual(token_report.projects_root(), Path("/config/projects/-home-a-agentic-company"))

    def test_no_transcripts_is_an_error_not_a_crash(self):
        err = io.StringIO()
        with mock.patch.object(token_report, "projects_root", return_value=self.session.parent / "none"), \
                contextlib.redirect_stderr(err):
            self.assertEqual(token_report.main(["--since", SINCE]), 1)
        self.assertIn("--session", err.getvalue())

    def test_since_takes_a_date_or_a_time_and_defaults_to_utc(self):
        self.assertEqual(token_report.parse_time("2026-01-05"), datetime(2026, 1, 5, tzinfo=timezone.utc))
        self.assertEqual(token_report.parse_time("2026-01-05T17:00:00+05:00"),
                         datetime(2026, 1, 5, 12, tzinfo=timezone.utc))


class FromGh(Base):
    def run_gh(self, runs=(), prs=()):
        def gh(arguments, **_):
            if arguments[:3] == ["gh", "run", "list"]:
                return gh_answer(list(runs.get(arguments[arguments.index("--workflow") + 1], []) if runs else []))
            return gh_answer(list(prs))
        return self.run_report(gh)

    def test_failed_deploys_by_workflow_with_run_ids(self):
        runs = {
            "staging": [
                {"databaseId": 11, "conclusion": "failure", "createdAt": AFTER},
                {"databaseId": 12, "conclusion": "success", "createdAt": AFTER},
                {"databaseId": 13, "conclusion": "timed_out", "createdAt": AFTER},
                {"databaseId": 14, "conclusion": "failure", "createdAt": BEFORE},
            ],
            "production": [{"databaseId": 21, "conclusion": "cancelled", "createdAt": AFTER}],
        }
        output = self.run_gh(runs=runs)
        self.assertIn("- staging: 2 failed: runs 11, 13", output)
        self.assertIn("- production: 0 failed", output)

    def test_gh_is_asked_from_the_day_of_since_and_only_read_commands_run(self):
        calls = []

        def gh(arguments, **_):
            calls.append(arguments)
            return gh_answer([])

        self.run_report(gh)
        self.assertEqual(len(calls), 3)
        for call in calls:
            self.assertEqual(call[0], "gh")
            self.assertEqual(call[2], "list")
            self.assertIn("acme/app", call)
        self.assertIn(">=2026-01-05", calls[0])
        self.assertIn("merged:>=2026-01-05", calls[2])

    def test_gh_is_asked_from_the_utc_day_so_a_zone_ahead_of_utc_loses_nothing(self):
        calls = []

        def gh(arguments, **_):
            calls.append(arguments)
            return gh_answer([])

        self.run_report(gh, since="2026-01-05T01:00:00+05:00")  # 20:00Z on the 4th
        self.assertIn(">=2026-01-04", calls[0])
        self.assertIn("merged:>=2026-01-04", calls[2])

    def test_each_product_repo_is_read(self):
        repos = []

        def gh(arguments, **_):
            repos.append(arguments[arguments.index("--repo") + 1])
            return gh_answer([])

        output = self.run_report(gh, products={**ACME, "demo": {"repo": "acme/demo"}, "bare": {}})
        self.assertEqual(repos, ["acme/app"] * 3 + ["acme/demo"] * 3)
        self.assertIn("Deploy failures, acme/demo:", output)

    def test_no_repo_or_a_company_json_it_cant_read_is_said_and_gh_never_runs(self):
        self.agent("a", "cto", [assistant("m1", read=10)])
        never = mock.Mock(side_effect=AssertionError("gh ran"))
        for products, why in (({}, "company.json names no product repo"),
                              (ValueError(CANARY), "company.json can't be read (ValueError)"),
                              ([], "company.json can't be read (AttributeError)")):
            output = self.run_report(never, products=products)
            self.assertIn(f"Deploy failures and follow-up fixes: not read ({why})", output)
            self.assertIn("cto", output)
            self.assertIn("Machine load:", output)
            self.assertNotIn(CANARY, output)

    def pr(self, number, title, branch="ws/x", body="", merged=AFTER):
        return {"number": number, "title": title, "headRefName": branch, "body": body, "mergedAt": merged}

    def test_follow_up_prs_show_numbers_only(self):
        prs = [
            self.pr(30, f"Fix forward #28 {CANARY}", body=f"{CANARY} also #27 and #30"),
            self.pr(31, "T-4 add the screen", branch="task/D-1-hotfix-login"),
            self.pr(32, 'Revert "something"'),
            self.pr(33, "fixes #29: label"),
        ]
        output = self.run_gh(prs=prs)
        self.assertIn("by their words: 4: #30 after #27, #28; #31; #32; #33 after #29", output)
        self.assertNotIn(CANARY, output)

    def test_an_ordinary_pr_is_not_a_follow_up(self):
        prs = [
            self.pr(40, "T-2 add filter", body="a fix for #12 was in the design"),
            self.pr(41, "Fix the label's colour"),
            self.pr(42, "prefix the table names #9"),
            self.pr(43, "Follow-up to #1", merged=BEFORE),
        ]
        self.assertIn("by their words: 0", self.run_gh(prs=prs))

    def test_a_list_at_the_limit_says_so(self):
        prs = [self.pr(n, "T-1 x") for n in range(1, token_report.GH_LIMIT + 1)]
        self.assertIn(f"only the newest {token_report.GH_LIMIT} read", self.run_gh(prs=prs))

    def test_gh_failing_loses_only_its_lines(self):
        cases = [
            lambda *a, **k: gh_answer([], returncode=1),
            mock.Mock(side_effect=FileNotFoundError("gh")),
            mock.Mock(side_effect=subprocess.TimeoutExpired("gh", 60)),
            lambda *a, **k: subprocess.CompletedProcess([], 0, stdout=f"not json {CANARY}", stderr=""),
            lambda *a, **k: gh_answer({"not": "a list"}),
        ]
        self.agent("a", "cto", [assistant("m1", read=10)])
        for gh in cases:
            output = self.run_report(gh)
            self.assertIn("- staging: not read (gh failed)", output)
            self.assertIn("by their words: not read (gh failed)", output)
            self.assertIn("cto", output)
            self.assertIn("Machine load:", output)
            self.assertNotIn(CANARY, output)


class Load(Base):
    def test_the_machine_s_load(self):
        with mock.patch.object(token_report.os, "cpu_count", return_value=10):
            self.assertIn("Machine load: 3.10, 4.20, 5.00 (1, 5, 15 min) on 10 CPUs", self.run_report())


if __name__ == "__main__":
    unittest.main()
