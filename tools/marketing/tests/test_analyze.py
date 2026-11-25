"""taste/analyze.py: a sitting's export to its profile, the consistency numbers, the
refusals, which write nothing, and the recovery check. The sitting is test_trial.py's, with fake media."""
import contextlib
import io
import json
import math
import random
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "taste"))

from test_trial import DAY, PAGE, Trial, part_of  # noqa: E402

import analyze  # noqa: E402

EXPORT = f"answers-{PAGE}-{DAY}.json"


def root_of(f, low, high):
    """f's one root in [low, high], f falling, by bisection: independent of the fit's Newton steps."""
    for _ in range(200):
        middle = (low + high) / 2
        low, high = (middle, high) if f(middle) > 0 else (low, middle)
    return (low + high) / 2


class Estimator(unittest.TestCase):
    """The MAP and its Laplace standard errors against answers worked out by hand, under the ridge's 0.25."""

    def test_a_pair_with_7_wins_in_10(self):
        rows, ridge, n = [{0: 1.0}, {1: 1.0}], analyze.RIDGE, 10
        weights, errors = analyze.fit([(rows, 0)] * 7 + [(rows, 1)] * 3, 2, [[0, 1]])
        # By symmetry the weights are d/2 and -d/2; the gradient is 7 - n sigma(d) - ridge d/2.
        d = root_of(lambda d: 7 - n / (1 + math.exp(-d)) - ridge * d / 2, 0, 20)
        p = 1 / (1 + math.exp(-d))
        self.assertAlmostEqual(weights[0], d / 2, places=7)
        self.assertAlmostEqual(weights[1], -d / 2, places=7)
        # The information is ridge I + n p(1-p) [[1,-1],[-1,1]]; the centred weight is (w0 - w1)/2.
        for error in errors:
            self.assertAlmostEqual(error, math.sqrt(1 / (2 * ridge + 4 * n * p * (1 - p))), places=7)

    def test_three_levels_shown_together_picked_6_2_2(self):
        rows, ridge, counts = [{0: 1.0}, {1: 1.0}, {2: 1.0}], analyze.RIDGE, (6, 2, 2)
        n = sum(counts)
        weights, errors = analyze.fit([(rows, k) for k, count in enumerate(counts) for _ in range(count)], 3, [[0, 1, 2]])
        # By symmetry the weights are 2t, -t, -t; the first's gradient is 6 - n p1 - ridge 2t.
        t = root_of(lambda t: counts[0] - n / (1 + 2 * math.exp(-3 * t)) - ridge * 2 * t, 0, 10)
        for weight, expected in zip(weights, (2 * t, -t, -t)):
            self.assertAlmostEqual(weight, expected, places=7)
        top = math.exp(2 * t) + 2 * math.exp(-t)
        p = [math.exp(2 * t) / top, math.exp(-t) / top, math.exp(-t) / top]
        h = [[n * ((p[i] if i == j else 0) - p[i] * p[j]) + (ridge if i == j else 0) for j in range(3)] for i in range(3)]
        cofactor = lambda i, j: (h[(i + 1) % 3][(j + 1) % 3] * h[(i + 2) % 3][(j + 2) % 3]
                                 - h[(i + 1) % 3][(j + 2) % 3] * h[(i + 2) % 3][(j + 1) % 3])
        det = sum(h[0][j] * cofactor(0, j) for j in range(3))
        inverse = [[cofactor(j, i) / det for j in range(3)] for i in range(3)]
        for k in range(3):  # the centred weight w_k - mean(w) is a'w with a = e_k - 1/3
            a = [(1 if i == k else 0) - 1 / 3 for i in range(3)]
            variance = sum(a[i] * inverse[i][j] * a[j] for i in range(3) for j in range(3))
            self.assertAlmostEqual(errors[k], math.sqrt(variance), places=7)

    def test_the_information_is_the_negative_hessian_for_any_rows(self):
        rng = random.Random(3)
        choices = []
        for _ in range(12):  # cbc rows with two weights each, and maxdiff's negated worst rows
            rows = [{i: 1.0, 3 + j: 1.0} for i, j in rng.sample([(0, 0), (1, 1), (2, 0), (0, 1), (1, 0)], 3)]
            choices.append((rows, rng.randrange(3)))
            choices.append(([{i: -c for i, c in row.items()} for row in rows[1:]], rng.randrange(2)))
        weights = [rng.uniform(-1, 1) for _ in range(5)]
        gradient, information = analyze.derivatives(choices, weights)
        step = 1e-5
        for i in range(5):
            up, down = list(weights), list(weights)
            up[i] += step
            down[i] -= step
            self.assertAlmostEqual(gradient[i], (analyze.posterior(choices, up) - analyze.posterior(choices, down)) / (2 * step), places=6)
            rise = [(a - b) / (2 * step) for a, b in zip(analyze.derivatives(choices, up)[0], analyze.derivatives(choices, down)[0])]
            for j in range(5):
                self.assertAlmostEqual(information[i][j], -rise[j], places=6)


class Sitting(Trial):
    def setUp(self):
        super().setUp()
        self.write()
        self.built = self.design()

    def answers(self, seed=1):
        return analyze.respondent(self.built, random.Random(seed))[1]

    def export(self, answers=None, name=EXPORT, folder=None, **changes):
        data = {"format": "taste-trial-answers-1", "page": PAGE, "session": DAY, "seed": self.built["seed"],
                "design_id": self.built["design_id"], "design": self.built,
                "answers": self.answers() if answers is None else answers, "exported_at": "2026-01-07T10:00:00.000Z", **changes}
        path = (self.here if folder is None else folder) / name
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def run_analysis(self, path=None):
        return analyze.analyze(PAGE, str(self.here / "session.json"), str(path or self.here / EXPORT), root=self.root)

    def profile(self, answers=None):
        self.export(answers)
        self.run_analysis()
        return json.loads((self.here / f"profile-{PAGE}-{DAY}.json").read_text(encoding="utf-8"))

    def refused(self, reason, path=None):
        before = {path: path.read_bytes() if path.is_file() else None for path in self.root.rglob("*")}
        with self.assertRaisesRegex(analyze.Refused, reason):
            self.run_analysis(path)
        after = {path: path.read_bytes() if path.is_file() else None for path in self.root.rglob("*")}
        self.assertEqual(after, before, "a refusal must write nothing")

    def trial(self, part, test=lambda trial: True):
        return next(trial for trial in part_of(self.built, part)["trials"] if test(trial))


class Profile(Sitting):
    def test_writes_only_the_profile_beside_the_export(self):
        self.export()
        before = set(self.root.rglob("*"))
        result = self.run_analysis()
        self.assertEqual(set(self.root.rglob("*")) - before, {self.here / f"profile-{PAGE}-{DAY}.json"})
        self.assertRegex(result, r"^wrote .*/profile-demo-session-2026-01-07\.json: (\d+) of \1 trials answered; hidden "
                                 r"repeats agree \d+ of \d+ \(\d+%\), the 80% bar (met|not met); near ties \d+ of \d+, clear")

    def test_the_profile_holds_estimates_with_errors_for_every_choice_part(self):
        profile = self.profile()
        self.assertEqual((profile["format"], profile["page"], profile["session"], profile["design_id"], profile["answers_file"]),
                         ("taste-profile-1", PAGE, DAY, self.built["design_id"], EXPORT))
        parts = {part["id"]: part for part in profile["parts"]}
        self.assertEqual({item["id"] for item in parts["pw"]["items"]}, {"r1", "a", "b", "c"})
        for key in ("pw", "md"):
            items = parts[key]["items"]
            self.assertTrue(all(item["se"] > 0 for item in items))
            self.assertAlmostEqual(sum(item["weight"] for item in items), 0, places=2)
            self.assertEqual([item["weight"] for item in items], sorted((item["weight"] for item in items), reverse=True))
        self.assertEqual(parts["pw"]["items"][[item["id"] for item in parts["pw"]["items"]].index("a")]["label"], "Ours A")
        for attribute in parts["cb"]["attributes"]:
            self.assertAlmostEqual(sum(level["weight"] for level in attribute["levels"]), 0, places=2)
            self.assertTrue(all(level["se"] > 0 for level in attribute["levels"]))
        steps = parts["sq"]["dimensions"][0]["steps"]
        self.assertEqual([step["step"] for step in steps], list(range(1, 8)))
        self.assertIsNotNone(parts["sq"]["dimensions"][0]["best"])
        self.assertEqual(parts["rg"]["dimensions"][0]["answer"], {"from": "15 s", "to": "45 s", "best": None})
        for key in ("pw", "md", "cb"):
            self.assertEqual(set(parts[key]["early_late"]), {"early", "late"})
            self.assertGreater(parts[key]["fit"]["rlh"], 0)
        self.assertIn("split_half", parts["md"])

    def test_the_same_answers_make_the_same_profile(self):
        self.assertEqual(self.profile(), self.profile())

    def test_a_consistent_respondent_is_fitted_in_its_order(self):
        rank = {"r1": 3, "a": 2, "b": 1, "c": 0}
        answers = self.answers()
        for trial in part_of(self.built, "pw")["trials"]:
            answers[trial["id"]] = {"pick": max(trial["items"], key=rank.get)}
        items = next(part for part in self.profile(answers)["parts"] if part["id"] == "pw")["items"]
        self.assertEqual([item["id"] for item in items], ["r1", "a", "b", "c"])
        check = next(part for part in self.profile(answers)["parts"] if part["id"] == "pw")["repeats"]
        self.assertEqual(check["agree"], check["repeats"])

    def test_unanswered_trials_are_counted_not_refused(self):
        answers = self.answers()
        gone = self.trial("md")["id"]
        del answers[gone]
        profile = self.profile(answers)
        self.assertEqual(profile["answered"]["trials"], profile["answered"]["of"] - 1)
        self.assertEqual(profile["answered"]["unanswered"], [gone])


class Repeats(Sitting):
    def test_a_cbc_repeat_agrees_by_the_option_s_levels_not_its_place(self):
        repeat = self.trial("cb", lambda trial: "repeat_of" in trial)
        original = self.trial("cb", lambda trial: trial["id"] == repeat["repeat_of"])
        place = {json.dumps(option["levels"], sort_keys=True): k + 1 for k, option in enumerate(repeat["options"])}
        answers = self.answers()
        answers[original["id"]] = {"pick": 1}
        same = place[json.dumps(original["options"][0]["levels"], sort_keys=True)]
        self.assertNotEqual(same, 1, "the repeat shows the options in another order")
        for pick, agree in ((same, True), (next(k for k in (1, 2, 3) if k != same), False)):
            answers[repeat["id"]] = {"pick": pick}
            comparisons = analyze.choice_part(part_of(self.built, "cb"), answers)[1]
            self.assertEqual(next(c["agree"] for c in comparisons if c["trial"] == repeat["id"]), agree)

    def test_a_maxdiff_repeat_counts_its_best_and_its_worst(self):
        answers = self.answers()
        repeats = [trial for trial in part_of(self.built, "md")["trials"] if "repeat_of" in trial]
        comparisons = analyze.choice_part(part_of(self.built, "md"), answers)[1]
        self.assertEqual(len(comparisons), 2 * len(repeats))

    def test_the_restart_check_counts_choice_repeats_and_splits_them_by_closeness(self):
        profile = self.profile()
        check = profile["restart_check"]
        by_part = sum(part["repeats"]["repeats"] for part in profile["parts"] if "repeats" in part)
        self.assertEqual(check["repeats"], by_part)
        self.assertGreater(check["repeats"], 0)
        self.assertEqual(check["near_tie"]["repeats"] + check["clear"]["repeats"], check["repeats"])
        self.assertEqual(check["near_tie"]["agree"] + check["clear"]["agree"], check["agree"])
        self.assertEqual(len(check["missed"]), check["repeats"] - check["agree"])
        self.assertEqual((check["bar"], check["met"]), (0.8, check["share"] >= 0.8))
        self.assertEqual(check["sequences"]["dimensions"], 1)
        for gap, near in ((1e9, "near_tie"), (0.0, "clear")):
            with mock.patch.object(analyze, "NEAR", gap):
                split = analyze.profile_of(self.built, self.answers())["restart_check"]
            self.assertEqual(split[near]["repeats"], split["repeats"])

    def test_the_closeness_comes_from_a_fit_without_the_repeat_pairs(self):
        answers = self.answers()
        part = part_of(self.built, "pw")
        paired = {key for trial in part["trials"] if "repeat_of" in trial for key in (trial["id"], trial["repeat_of"])}
        first = analyze.choice_part(part, answers)[1]
        flipped = dict(answers)
        for trial in part["trials"]:
            if trial["id"] in paired:
                flipped[trial["id"]] = {"pick": next(item for item in trial["items"] if item != answers[trial["id"]]["pick"])}
        self.assertEqual([c["gap"] for c in first], [c["gap"] for c in analyze.choice_part(part, flipped)[1]])

    def test_without_repeats_the_check_is_not_met_or_missed(self):
        answers = {key: value for key, value in self.answers().items()
                   if not any(trial["id"] == key and "repeat_of" in trial for part in self.built["parts"] for trial in part["trials"])}
        check = self.profile(answers)["restart_check"]
        self.assertEqual((check["repeats"], check["met"], check["share"]), (0, None, None))


class Parts(Sitting):
    def test_holdouts_stay_out_of_the_fit_and_get_a_hit_rate(self):
        answers = self.answers()
        part = part_of(self.built, "cb")
        held = [trial for trial in part["trials"] if trial.get("holdout")]
        self.assertEqual(len(held), 1)
        entry = analyze.choice_part(part, answers)[0]
        self.assertEqual(entry["fit"]["choices"], len(part["trials"]) - 1)
        self.assertEqual((entry["holdouts"]["tasks"], entry["holdouts"]["chance"]), (1, 0.333))
        rates = set()
        for pick in (1, 2, 3):
            answers[held[0]["id"]] = {"pick": pick}
            other = analyze.choice_part(part, answers)[0]
            self.assertEqual(other["attributes"], entry["attributes"])
            rates.add(other["holdouts"]["rate"])
        self.assertIn(1, rates)
        self.assertIn(0, rates)

    def test_split_half_is_null_when_the_halves_don_t_correlate(self):
        part = part_of(self.built, "md")
        for r, expected in ((0.5, 0.667), (0.0, None), (-0.5, None)):
            with self.subTest(r=r), mock.patch.object(analyze, "pearson", return_value=r):
                self.assertEqual(analyze.choice_part(part, self.answers())[0]["split_half"], expected)

    def test_unscored_pairwise_is_counted_only(self):
        session = self.with_part("pw", scored=False)
        self.write(session)
        self.built = self.design(session)
        profile = self.profile()
        entry = next(part for part in profile["parts"] if part["id"] == "pw")
        self.assertEqual(entry, {"id": "pw", "type": "pairwise", "title": "Pairs", "scored": False,
                                 "answered": len(part_of(self.built, "pw")["trials"]), "of": len(part_of(self.built, "pw")["trials"])})
        self.assertFalse(any(c["part"] == "pw" for c in profile["restart_check"]["missed"]))

    def test_checklist_lines_are_ticked_never_red_lines(self):
        answers = self.answers()
        answers[self.trial("rl")["id"]] = {"checked": ["Shouting"], "own": ["Fake urgency"], "ms": 900}
        answers[self.trial("ck")["id"]] = {"checked": ["Pace", "Hook"], "own": ["Logo"], "ms": 900}
        answers[self.trial("nt")["id"]] = {"note": "Too dark", "ms": 900}
        profile = self.profile(answers)
        self.assertEqual(profile["red_lines"], ["Shouting", "Fake urgency"])
        self.assertEqual(profile["ticked"], [{"part": "ck", "mark": "Not for him", "lines": ["Pace", "Hook", "Logo"]}])
        self.assertEqual(profile["notes"], [{"part": "nt", "item": "n1", "label": "A frame", "src": "ours/a.jpg", "note": "Too dark"}])

    def test_a_sequence_marks_its_dimension_uncertain_when_up_and_down_disagree(self):
        answers = self.answers()
        for trial in part_of(self.built, "sq")["trials"]:
            answers[trial["id"]] = {"best": 2, "from": 1, "to": 3} if trial["order"] == "up" else {"best": 6, "from": 5, "to": 7}
        profile = self.profile(answers)
        dimension = next(part for part in profile["parts"] if part["id"] == "sq")["dimensions"][0]
        self.assertEqual((dimension["fine"], dimension["best"]), (None, 4))
        self.assertEqual([entry["why"] for entry in profile["uncertain"] if entry.get("dimension") == "cut"],
                         ["the bests up and down are 4 steps apart", "the fine runs up and down don't meet"])
        self.assertEqual(profile["restart_check"]["sequences"], {"dimensions": 1, "same_best": 0, "within_one": 0})


class Refusals(Sitting):
    def test_an_export_of_another_design_is_refused(self):
        self.export(design_id="0123456789ab")
        self.refused("answers design '0123456789ab', and session.json now makes .*: the session changed after the page was made")

    def test_a_session_changed_after_the_page_was_made_is_refused(self):
        self.export()
        self.session["seed"] = 8
        self.write()
        self.refused("the session changed after the page was made")

    def test_an_export_for_another_page_session_or_format_is_refused(self):
        for changes, reason in (({"format": "taste-trial-1"}, "isn't a trial page's export"),
                                ({"page": "acme"}, "is for page 'acme', not demo"),
                                ({"session": "session-2026-01-06"}, "is for session 'session-2026-01-06', not session-2026-01-07")):
            with self.subTest(changes=changes):
                self.export(**changes)
                self.refused(reason)

    def test_an_export_outside_the_session_folder_is_refused(self):
        self.export(folder=self.here / "ours")
        self.refused("must be a file directly in session-2026-01-07/", self.here / "ours" / EXPORT)
        self.export(name="answers.txt")
        self.refused("the export is a .json file", self.here / "answers.txt")

    def test_answers_the_design_hasn_t_or_that_don_t_fit_are_refused(self):
        pw, md, cb, sq = (self.trial(key)["id"] for key in ("pw", "md", "cb", "sq"))
        for key, value, reason in (("zz.1", {"note": ""}, "answers trial 'zz.1', which the design hasn't"),
                                   (pw, {"pick": "nope"}, f"the answer to {pw}: the pick isn't an item shown"),
                                   (pw, ["a"], f"the answer to {pw} isn't an object"),
                                   (md, {"best": "m0", "worst": "m0"}, "best and worst must be two different items shown"),
                                   (cb, {"pick": 4}, "the pick is an option's place, 1 to 3"),
                                   (cb, {"pick": True}, "the pick is an option's place"),
                                   (sq, {"best": 5, "from": 1, "to": 4}, "from <= best <= to"),
                                   (pw, {"pick": "a", "ms": "slow"}, "ms is a time")):
            with self.subTest(key=key, value=value):
                answers = self.answers()
                answers[key] = value
                self.export(answers)
                self.refused(reason)

    def test_a_range_s_best_must_be_a_fine_value(self):
        rg = self.trial("rg")["id"]
        for value, reason in (({"from": "15 s", "to": "30 s", "best": "45 s"}, "the best is a fine value, from <= best <= to"),
                              ({"from": None, "to": None, "best": "30 s"}, "the best is a fine value")):
            with self.subTest(value=value):
                answers = self.answers()
                answers[rg] = value
                self.export(answers)
                self.refused(reason)
        answers = self.answers()
        answers[rg] = {"from": "30 s", "to": "30 s", "best": "30 s"}
        self.assertEqual(part_of(self.profile(answers), "rg")["dimensions"][0]["answer"], answers[rg])
        session = self.with_part("rg", dimensions=[{"id": "len", "name": "Length", "values": ["15 s", "30 s", "45 s"], "ordered": False}])
        self.write(session)
        self.built = self.design(session)
        answers = self.answers()
        answers[rg] = {"fine": ["15 s"], "best": "30 s"}
        self.export(answers)
        self.refused("the best is one of the fine values")

    def test_a_weekly_session_is_refused(self):
        self.export()
        self.write({"page": PAGE, "title": "Session 1", "intro": "Three changes.", "items": []})
        self.refused('analyze.py reads a trial session, one with "mode": "trial"')


class Recovery(Sitting):
    def test_a_low_noise_respondent_is_recovered_within_the_bounds(self):
        with mock.patch.object(analyze, "SIGMA", 0.05):
            result = analyze.recovery(self.built, replicates=5)
        self.assertEqual({part["id"] for part in result["parts"]}, {"pw", "md", "cb", "sq"})
        self.assertTrue(result["within_bounds"], result["cut"])
        self.assertGreaterEqual(result["repeat_check"]["share"], 0.9)

    def test_a_noisy_respondent_names_what_to_cut(self):
        with mock.patch.object(analyze, "SIGMA", 50.0):
            result = analyze.recovery(self.built, replicates=5)
        self.assertFalse(result["within_bounds"])
        self.assertTrue(any(entry.get("attribute") for entry in result["cut"]))

    def test_the_recovery_is_reproducible_and_writes_nothing(self):
        before = {path: path.read_bytes() if path.is_file() else None for path in self.root.rglob("*")}
        first = analyze.recover(PAGE, str(self.here / "session.json"), root=self.root, replicates=3)
        self.assertEqual(first, analyze.recover(PAGE, str(self.here / "session.json"), root=self.root, replicates=3))
        self.assertEqual({path: path.read_bytes() if path.is_file() else None for path in self.root.rglob("*")}, before)
        result = json.loads(first)
        self.assertEqual((result["format"], result["replicates"], result["sigma"], result["reliability"]),
                         ("taste-recovery-1", 3, 0.655, 0.7))

    def test_the_synthetic_answers_pass_the_export_checks(self):
        self.export()
        self.run_analysis()


class Command(Sitting):
    def test_the_command_takes_answers_or_recover(self):
        for argv in ([], ["--answers", "a.json", "--recover"], ["--session", "s/session.json"]):
            with self.subTest(argv=argv), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as stop:
                analyze.main(["--page", PAGE, *argv])
            self.assertEqual(stop.exception.code, 2)
        with mock.patch.object(analyze, "recover", return_value="{}") as recovered, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(analyze.main(["--page", PAGE, "--session", "s/session.json", "--recover"]), 0)
        recovered.assert_called_once_with(PAGE, "s/session.json")

    def test_a_refusal_exits_1_with_its_reason(self):
        self.export(design_id="0123456789ab")
        real = analyze.analyze
        here = lambda page, session, answers: real(page, session, answers, root=self.root)
        err = io.StringIO()
        with mock.patch.object(analyze, "analyze", here), contextlib.redirect_stderr(err):
            code = analyze.main(["--page", PAGE, "--session", str(self.here / "session.json"), "--answers", str(self.here / EXPORT)])
        self.assertEqual(code, 1)
        self.assertIn("refused: ", err.getvalue())
        self.assertFalse((self.here / f"profile-{PAGE}-{DAY}.json").exists())


if __name__ == "__main__":
    unittest.main()
