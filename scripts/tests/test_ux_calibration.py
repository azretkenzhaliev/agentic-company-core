"""Tests for tools/ux/: the calibration answer key matches its pages; score.py counts found, missed,
invented and duplicate findings; check.mjs, run on the calibration pages in a real browser, still reports
the values the calibration README records, and refuses a bad out-dir or steps module."""

import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools" / "ux"
CAL = TOOLS / "calibration"
spec = importlib.util.spec_from_file_location("ux_score", CAL / "score.py")
score = importlib.util.module_from_spec(spec)
spec.loader.exec_module(score)

KEY = json.loads((CAL / "answer-key.json").read_text(encoding="utf-8"))

FINDINGS = """# Calibration audit

Some text before the table, and a table that isn't the findings table:

| a | b |
|---|---|
| 1 | 2 |

| # | page | where | criterion | level | confirmed-by | evidence | severity |
|---|---|---|---|---|---|---|---|
| 1 | dashboard.html | `p#last-updated` | 1.4.3 | L2 | axe:color-contrast | 2.85:1 | major (proposed) |
| 2 | dashboard.html | pager buttons | 2.5.8 | L2 | axe:target-size | 16x16 | major (proposed) |
| 3 | dashboard.html | `p#last-updated` | 1.4.3 | L2 | axe:color-contrast | again, at 375 | major (proposed) |
| 4 | dashboard.html | status column | 1.4.1, 1.1.1 | L3 | - | coloured dot only | major (proposed) |
| 5 | dashboard.html | `button#export` | 2.4.4 | L3 | - | vague label | minor (proposed) |
| 6 | booking.html | `#booking-title` | i18n | L2 | measured:mixedScriptWords=Tеатър | Latin T | major (proposed) |
| 7 | booking.html | `div.opt` in `#seats` | 2.1.1, 4.1.2 | L2 | measured:notReachable=3 | no tabindex, no name | blocker (proposed) |
| 8 | booking.html | `#guest-name` | 1.4.3 | L3 | — | right place, wrong criterion | minor (proposed) |
| 9 | booking.html | page | 3.1.1 | maybe | - | lang is en | major (proposed) |

After the table.
"""


class AnswerKeyTest(unittest.TestCase):
    def test_pages_exist_and_hold_each_defect(self):
        pages = {name: (CAL / path).read_text(encoding="utf-8").lower() for name, path in KEY["pages"].items()}
        self.assertGreaterEqual(len(KEY["defects"]), 10)
        for d in KEY["defects"]:
            with self.subTest(defect=d["id"]):
                self.assertIn(d["page"], pages)
                self.assertTrue(d["criteria"])
                self.assertIn(d["kind"], {"axe", "measured", "playwright", "judgement"})
                self.assertTrue(any(loc.lower() in pages[d["page"]] for loc in d["locators"]), d["locators"])

    def test_ids_are_unique(self):
        ids = [d["id"] for d in KEY["defects"]]
        self.assertEqual(len(ids), len(set(ids)))

    def test_pages_name_no_defect(self):
        for name, path in KEY["pages"].items():
            html = (CAL / path).read_text(encoding="utf-8")
            with self.subTest(page=name):
                self.assertNotIn("<!--", html)
                self.assertIsNone(re.search(r"defect|planted|answer.key|wcag", html, re.I))


class ScoreTest(unittest.TestCase):
    def setUp(self):
        self.result = score.score(score.parse_table(FINDINGS), KEY)

    def test_parses_only_the_findings_table(self):
        rows = score.parse_table(FINDINGS)
        self.assertEqual(len(rows), 9)
        self.assertEqual(rows[0]["where"], "`p#last-updated`")

    def test_found_by_level(self):
        self.assertEqual(self.result["found"]["L2"], 4)  # D1, D3, E2, E4
        self.assertEqual(self.result["found"]["L3"], 1)  # D5
        self.assertEqual(self.result["found"]["L?"], 1)  # E1: the level cell has no L0-L3
        self.assertEqual(self.result["found_confirmed"]["L2"], 4)
        self.assertEqual(self.result["found_confirmed"]["L3"], 0)

    def test_invented(self):
        self.assertEqual(self.result["invented"]["L3"], 2)  # the Export label, and E3's field under a wrong criterion
        self.assertEqual([n for n, _ in self.result["invented_rows"]], [5, 8])

    def test_missed_and_duplicates(self):
        self.assertEqual(
            sorted(d["id"] for d in self.result["missed"]),
            ["D2", "D4", "D6", "D7", "D8", "E3", "E5", "E6", "E7", "E8"],
        )
        self.assertEqual(self.result["duplicates"], {"D1": 1})

    def test_missed_by_expected_level(self):
        # axe, measured and playwright defects are expected at L2, judgement ones at L3
        self.assertEqual(self.result["missed_by_level"]["L2"], 8)  # D2 D4 D6 D7 D8 E3 E7 E8
        self.assertEqual(self.result["missed_by_level"]["L3"], 2)  # E5 E6
        self.assertEqual(sum(self.result["missed_by_level"].values()), len(self.result["missed"]))
        self.assertTrue(all(d["kind"] in score.EXPECTED for d in KEY["defects"]))

    def test_empty_table_scores_zero(self):
        rows = score.parse_table("| page | where | criterion | level |\n|---|---|---|---|\n")
        self.assertEqual(rows, [])
        result = score.score(rows, KEY)
        self.assertEqual(sum(result["found"].values()), 0)
        self.assertEqual(len(result["missed"]), len(KEY["defects"]))
        self.assertIsNone(score.parse_table("no table\n"))

    def test_best_match_wins(self):
        defects = [
            {"id": "A", "page": "p", "criteria": ["4.1.2"], "locators": ["name"]},
            {"id": "B", "page": "p", "criteria": ["4.1.2"], "locators": ["name", "opt"]},
        ]
        row = {"page": "p.html", "where": "div.opt", "criterion": "4.1.2", "evidence": "no name"}
        self.assertEqual(score.match(row, defects)["id"], "B")

    def test_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "findings.md"
            path.write_text(FINDINGS, encoding="utf-8")
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(score.main([str(path)]), 0)
            text = out.getvalue()
            self.assertIn("9 findings; 6 of 16 planted defects found.", text)
            self.assertIn("missed (expected level)", text)
            self.assertRegex(text, r"\nL3 +1 +0 +2 +2\n")
            self.assertIn("duplicates: D1 +1", text)
            self.assertIn("invented, row 5:", text)
            (Path(tmp) / "none.md").write_text("no table\n", encoding="utf-8")
            with redirect_stderr(io.StringIO()):
                self.assertEqual(score.main([str(Path(tmp) / "none.md")]), 1)
            (Path(tmp) / "empty.md").write_text("| page | where | criterion | level |\n|---|---|---|---|\n", encoding="utf-8")
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(score.main([str(Path(tmp) / "empty.md")]), 0)
            self.assertIn("0 findings; 0 of 16 planted defects found.", out.getvalue())


def check_tree(test_class):
    """A copy of check.mjs in a temp tree (tools/ux/ and workspaces/ux/), so its output stays out of the repo."""
    if not shutil.which("node"):
        raise unittest.SkipTest("check.mjs not run: node isn't installed")
    if not all((TOOLS / "node_modules" / m).is_dir() for m in ("playwright", "axe-core")):
        raise unittest.SkipTest("check.mjs not run: tools/ux/node_modules is missing (npm ci --prefix tools/ux)")
    tmp = Path(os.path.realpath(tempfile.mkdtemp()))
    test_class.addClassCleanup(shutil.rmtree, tmp)
    tools = tmp / "tools" / "ux"
    tools.mkdir(parents=True)
    shutil.copy(TOOLS / "check.mjs", tools)
    (tools / "node_modules").symlink_to(TOOLS / "node_modules")
    test_class.tmp, test_class.out = tmp, tmp / "workspaces" / "ux"
    test_class.check = staticmethod(lambda *args: subprocess.run(
        ["node", str(tools / "check.mjs"), *map(str, args)], capture_output=True, text=True, timeout=180))


def page_url(page):
    return (CAL / "site" / page).as_uri()


class CheckBrowserTest(unittest.TestCase):
    """check.mjs at 375 px on both pages: the values tools/ux/calibration/README.md records."""

    @classmethod
    def setUpClass(cls):
        check_tree(cls)
        cls.runs = {}
        for page in ("dashboard.html", "booking.html"):
            run = cls.check(page_url(page), cls.out / page, "--widths", "375")
            if run.returncode and "Executable doesn't exist" in run.stderr:
                raise unittest.SkipTest("check.mjs not run: Playwright's Chromium isn't installed (its own cache folder: tools/ux/README.md)")
            if run.returncode:
                raise AssertionError(f"check.mjs failed on {page}:\n{run.stderr}")
            report = json.loads((cls.out / page / "report.json").read_text(encoding="utf-8"))
            cls.runs[page] = report["runs"][0]

    def test_wcag22_rules_run(self):
        axe = self.runs["dashboard.html"]["axe"]
        self.assertIn("target-size", axe["wcag22RanWhenOn"])
        self.assertIn("target-size", [v["id"] for v in axe["violations"]])  # D3

    def test_tab_walk(self):
        stops = self.runs["dashboard.html"]["tabStops"]
        self.assertTrue(stops[0]["el"].startswith("button#refresh"), stops[0])  # D8: tabindex=1 goes first
        chips = [s for s in stops if s["el"].startswith("button.chip")]
        self.assertEqual([s["indicator"] for s in chips], ["none"] * 4)  # D4
        others = [s for s in stops if s not in chips]
        self.assertTrue(others)
        self.assertTrue(all("outline" in s["indicator"] for s in others), others)

    def test_measured(self):
        dashboard, booking = self.runs["dashboard.html"], self.runs["booking.html"]
        self.assertGreater(dashboard["clsLab"], 0.1)  # D7
        self.assertEqual(booking["mixedScriptWords"], ["Tеатър"])  # E2
        self.assertEqual(len([e for e in booking["notReachable"] if e.startswith("div.opt")]), 3)  # E4
        self.assertGreater(booking["overflowX"], 0)  # E8, at 375


class CheckRefusesTest(unittest.TestCase):
    """check.mjs refuses before it opens a browser or makes a folder."""

    @classmethod
    def setUpClass(cls):
        check_tree(cls)

    def assert_refused(self, run, message, out):
        self.assertEqual(run.returncode, 1, run.stderr)
        self.assertIn(message, run.stderr)
        self.assertFalse(out.exists())

    def test_out_dir_outside_workspaces_ux(self):
        self.out.mkdir(parents=True, exist_ok=True)
        (self.out / "link").symlink_to(self.tmp)
        for out in (self.tmp / "elsewhere", self.out / ".." / "ux-sibling", self.out / "link" / "escaped"):
            with self.subTest(out=out):
                self.assert_refused(self.check(page_url("booking.html"), out), "<out-dir> must be under", out)

    def test_steps_without_default_function(self):
        steps = self.tmp / "steps.mjs"
        steps.write_text("export const steps = async () => {};\n", encoding="utf-8")
        out = self.out / "steps"
        self.assert_refused(self.check(page_url("booking.html"), out, "--steps", steps), "has no default function", out)


if __name__ == "__main__":
    unittest.main()
