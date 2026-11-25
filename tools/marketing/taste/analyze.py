#!/usr/bin/env python3
"""Analyse one taste-defining sitting: from the trial page's export, the Board's
taste profile and its consistency numbers; and a check that the sitting's design recovers a known profile.

    python3 tools/marketing/taste/analyze.py --page <page> --session <folder>/session.json --answers <folder>/<export>.json
    python3 tools/marketing/taste/analyze.py --page <page> --session <folder>/session.json --recover

- **Where:** session.json and the export (`answers-<page>-<session>.json`) sit directly in
  workspaces/marketing/media/taste/<page>/session-<YYYY-MM-DD>[-<word>]/, as for build.py. The tool writes only
  `profile-<page>-<session>.json` there, beside them, whole or not at all. --recover writes nothing: it prints.
- **Refusals:** the design is rebuilt from session.json with build.py's own checks (a ref/ item still needs its
  style.md; media may be gone). The export is refused if its format isn't taste-trial-answers-1, its page or session
  differ, its design_id isn't the rebuilt design's (session.json changed after the page was made), or an answer names a
  trial the design hasn't or doesn't fit its trial. The analysis reads the rebuilt design, never the export's copy.
  Unanswered trials are counted, not refused. A refusal names the reason, exits 1 and writes nothing.
- **The estimator:** one ridge-penalized multinomial logit for all the choice data, fitted to its maximum a posteriori
  by Newton's method, standard errors from the inverse of the penalized information (Laplace). One model, so every
  part's weights are on the same logit scale: pairwise is Bradley-Terry, one weight an item;
  maxdiff is sequential best-worst, the best of four and then the worst of the other three; cbc is one weight a level,
  holdouts kept out; a sequence is a 7-way logit for each dimension's best step. The ridge (0.25: a prior SD of 2
  logits, about the spread of a respondent whose judgments have reliability 0.7) keeps thin parts finite: few answers
  pull a weight to zero, not to an extreme, and the standard errors say so. Weights are relative within their group (a
  part's items, an attribute's levels, a dimension's steps): the fit centres each group, as effects coding does, without
  favouring a level, and the standard errors are the centred weights'. Unscored pairwise (practice) is counted only.
- **Consistency:** the restart check (at least 80%, and the Board confirms the summary; nothing restarts by
  itself) is the hidden repeats' agreement: a pairwise or cbc repeat agrees when the same item, or the same option by its
  levels, is picked; a maxdiff repeat counts its best and its worst. It is split: near ties, where the two
  closest options shown are under 0.5 logit apart (62% against 38% in a pair) in a fit without the repeat pairs, against
  clear ones. Sequences are their own repeat, up against down: reported beside the check, not in it. Also per part: fit
  (the geometric mean probability of each pick against chance, and the hit rate), split-half reliability for pairwise
  and maxdiff (Spearman-Brown; null when the halves don't correlate), early against late trials (hit rate and median time; Li et al. 2022), and the holdout hit
  rate (chance 1 in 3).
- **Uncertain:** a cbc attribute with no level 2 standard errors clear of zero; a missed holdout; a sequence whose up
  and down bests are over a step apart, or whose fine runs don't meet. They mark dimensions and don't hold the restart.
- **Red lines** come only from a redlines part. A checklist's lines are passed on as ticked, never as red lines.
- **Recovery (--recover):** a synthetic respondent with a known profile answers the exact design, repeats and holdouts
  included, 100 times from a fixed seed, and its answers go through the same analysis. It is Thurstone: each option's
  utility plus normal noise of SD 0.655 a trial, so one judgment's reliability is 1/(1 + 0.655²) = 0.70. Items and levels have true utilities of SD 1 (an option's, in cbc); a sequence dimension has an ideal
  step. Bounds: a pairwise or maxdiff part's weights correlate with the truth at 0.8 or more on average, a cbc part's at
  0.7 or more, and each cbc attribute's best level is found in 70% of runs (chance 1 in 3); a sequence's fitted best is
  within a step of the ideal in 80% of dimensions. A part or attribute under its bound is named to cut. It also says
  whether this respondent passes the 80% repeat check.
- Local only: no network, nothing sent. Python's standard library, run isolated (-I).
"""
import os
import sys

if __name__ == "__main__" and not sys.flags.isolated:
    os.execv(sys.executable, [sys.executable, "-I", *sys.argv])

import argparse  # noqa: E402
import json  # noqa: E402
import math  # noqa: E402
import random  # noqa: E402
import statistics  # noqa: E402
import tempfile  # noqa: E402
from pathlib import Path  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))  # -I leaves the script's own folder off the path
sys.dont_write_bytecode = True  # importing build leaves no __pycache__/ beside the code
import build  # noqa: E402
from build import STEPS, Refused, need  # noqa: E402

FORMAT = "taste-trial-answers-1"
RIDGE = 0.25
NEAR = 0.5  # logits between the two closest options shown: under it, a near tie
BAR = 0.8  # a default
CLEAR = 2.0  # standard errors
SIGMA = 0.655
SCALE = 1.702 / (SIGMA * math.sqrt(2))  # the synthetic respondent's utilities on the logit scale
REPLICATES = 100
BOUNDS = {"items": 0.8, "cbc": 0.7, "best level": 0.7, "sequence": 0.8}
CHOICE = ("pairwise", "maxdiff", "cbc")
ESTIMATOR = ("one ridge-penalized multinomial logit (prior SD 2 logits), MAP by Newton's method, Laplace standard errors; "
             "pairwise Bradley-Terry, maxdiff sequential best-worst, cbc one weight a level with holdouts out, sequence a "
             "7-way logit for the best step; weights centred within each part, attribute or dimension")


def rounded(value):
    return None if value is None else round(value, 3)


# The estimator. A choice is (rows, pick): one sparse row {weight: coefficient} an option shown, and the place picked.

def utilities(rows: list, weights: list) -> list:
    return [sum(c * weights[i] for i, c in row.items()) for row in rows]


def probabilities(values: list) -> list:
    top = max(values)
    powers = [math.exp(x - top) for x in values]
    total = sum(powers)
    return [x / total for x in powers]


def posterior(choices: list, weights: list) -> float:
    total = -RIDGE / 2 * sum(x * x for x in weights)
    for rows, pick in choices:
        values = utilities(rows, weights)
        top = max(values)
        total += values[pick] - top - math.log(sum(math.exp(x - top) for x in values))
    return total


def derivatives(choices: list, weights: list) -> tuple:
    """The log posterior's gradient, and the penalized information (its negative Hessian)."""
    size = len(weights)
    gradient = [-RIDGE * x for x in weights]
    information = [[RIDGE if i == j else 0.0 for j in range(size)] for i in range(size)]
    for rows, pick in choices:
        mean = {}
        for row, chance in zip(rows, probabilities(utilities(rows, weights))):
            for i, a in row.items():
                mean[i] = mean.get(i, 0.0) + chance * a
                for j, b in row.items():
                    information[i][j] += chance * a * b
        for i, c in rows[pick].items():
            gradient[i] += c
        for i, a in mean.items():
            gradient[i] -= a
            for j, b in mean.items():
                information[i][j] -= a * b
    return gradient, information


def cholesky(matrix: list) -> list:
    size = len(matrix)
    lower = [[0.0] * size for _ in range(size)]
    for i in range(size):
        for j in range(i + 1):
            rest = matrix[i][j] - sum(lower[i][k] * lower[j][k] for k in range(j))
            lower[i][j] = math.sqrt(max(rest, 1e-12)) if i == j else rest / lower[j][j]
    return lower


def solve(lower: list, vector: list) -> list:
    size = len(vector)
    middle = [0.0] * size
    for i in range(size):
        middle[i] = (vector[i] - sum(lower[i][k] * middle[k] for k in range(i))) / lower[i][i]
    result = [0.0] * size
    for i in reversed(range(size)):
        result[i] = (middle[i] - sum(lower[k][i] * result[k] for k in range(i + 1, size))) / lower[i][i]
    return result


def fit(choices: list, size: int, groups: list) -> tuple:
    """The MAP weights, centred within each group, and their standard errors. The ridge makes the log posterior strictly
    concave, so Newton's method, halving a step that doesn't climb, finds its one maximum."""
    weights = [0.0] * size
    value = posterior(choices, weights)
    for _ in range(100):
        gradient, information = derivatives(choices, weights)
        step = solve(cholesky(information), gradient)
        share = 1.0
        while share > 1e-6:
            moved = [w + share * s for w, s in zip(weights, step)]
            new = posterior(choices, moved)
            if new >= value:
                weights, value = moved, new
                break
            share /= 2
        if share <= 1e-6 or max(map(abs, step), default=0.0) * share < 1e-9:
            break
    lower = cholesky(derivatives(choices, weights)[1])
    covariance = [solve(lower, [1.0 if i == k else 0.0 for i in range(size)]) for k in range(size)]
    errors = [0.0] * size
    for group in groups:  # the likelihood can't see a shift of a whole group: report the centred weights and their errors
        count = len(group)
        centre = sum(weights[i] for i in group) / count
        spread = sum(covariance[i][j] for i in group for j in group) / count ** 2
        for i in group:
            weights[i] -= centre
            errors[i] = math.sqrt(max(covariance[i][i] - 2 * sum(covariance[i][j] for j in group) / count + spread, 0.0))
    return weights, errors


def hit(rows: list, pick: int, weights: list) -> float:
    """1 if the pick is the fitted favourite, a share of 1 if it ties for it, else 0."""
    values = utilities(rows, weights)
    top = max(values)
    best = [k for k, x in enumerate(values) if x >= top - 1e-9]
    return (pick in best) / len(best)


def fit_numbers(choices: list, weights: list) -> "dict | None":
    if not choices:
        return None
    logs = [math.log(probabilities(utilities(rows, weights))[pick]) for rows, pick in choices]
    return {"choices": len(choices), "rlh": rounded(math.exp(statistics.fmean(logs))),
            "chance": rounded(math.exp(statistics.fmean([-math.log(len(rows)) for rows, _ in choices]))),
            "hit_rate": rounded(statistics.fmean([hit(rows, pick, weights) for rows, pick in choices]))}


def pearson(xs: list, ys: list) -> "float | None":
    if len(xs) < 3:
        return None
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx < 1e-12 or syy < 1e-12:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / math.sqrt(sxx * syy)


def median_ms(answers: list) -> "float | None":
    times = [answer["ms"] for answer in answers if "ms" in answer]
    return statistics.median(times) if times else None


# The choice parts.

def layout(part: dict) -> tuple:
    """Each weight's place by its key (an item id, or an attribute and level), and the groups the fit centres."""
    if part["type"] == "cbc":
        keys, groups = [], []
        for attribute in part["attributes"]:
            groups.append(list(range(len(keys), len(keys) + len(attribute["levels"]))))
            keys += [(attribute["id"], level["id"]) for level in attribute["levels"]]
    else:
        keys = [item["id"] for item in part["items"]]
        groups = [list(range(len(keys)))]
    return {key: k for k, key in enumerate(keys)}, groups


def shown_rows(part: dict, trial: dict, index: dict) -> list:
    if part["type"] == "cbc":
        return [{index[(attribute["id"], option["levels"][attribute["id"]])]: 1.0 for attribute in part["attributes"]}
                for option in trial["options"]]
    return [{index[key]: 1.0} for key in trial["items"]]


def choices_of(part: dict, trial: dict, answer: dict, index: dict) -> list:
    rows = shown_rows(part, trial, index)
    if part["type"] == "pairwise":
        return [(rows, trial["items"].index(answer["pick"]))]
    if part["type"] == "cbc":
        return [(rows, answer["pick"] - 1)]
    best = trial["items"].index(answer["best"])
    rest = [k for k in range(len(rows)) if k != best]
    worst = rest.index(trial["items"].index(answer["worst"]))
    return [(rows, best), ([{i: -c for i, c in rows[k].items()} for k in rest], worst)]


def picked(part: dict, trial: dict, answer: dict) -> list:
    """What a repeat has to match: the cbc option by its levels, the item picked, or maxdiff's best and worst."""
    if part["type"] == "cbc":
        return [trial["options"][answer["pick"] - 1]["levels"]]
    if part["type"] == "maxdiff":
        return [answer["best"], answer["worst"]]
    return [answer["pick"]]


def gaps(part: dict, trial: dict, index: dict, weights: list) -> list:
    """How close the trial was: the two top options shown, and for maxdiff's worst the two bottom ones."""
    values = sorted(utilities(shown_rows(part, trial, index), weights), reverse=True)
    return [values[0] - values[1], values[-2] - values[-1]] if part["type"] == "maxdiff" else [values[0] - values[1]]


def choice_part(part: dict, answers: dict) -> tuple:
    index, groups = layout(part)
    answered = [trial for trial in part["trials"] if trial["id"] in answers]
    fitted = [trial for trial in answered if not trial.get("holdout")]
    tagged = [(trial["id"], choice) for trial in fitted for choice in choices_of(part, trial, answers[trial["id"]], index)]
    choices = [choice for _, choice in tagged]
    weights, errors = fit(choices, len(index), groups)
    entry = {"answered": len(answered), "of": len(part["trials"]), "fit": fit_numbers(choices, weights)}
    uncertain = []

    by_id = {trial["id"]: trial for trial in part["trials"]}
    paired = {key for trial in part["trials"] if "repeat_of" in trial for key in (trial["id"], trial["repeat_of"])}
    close = fit([choice for key, choice in tagged if key not in paired], len(index), groups)[0]
    comparisons = []
    for trial in answered:
        original = by_id.get(trial.get("repeat_of"))
        if original is None or original["id"] not in answers:
            continue
        for first, again, gap in zip(picked(part, original, answers[original["id"]]), picked(part, trial, answers[trial["id"]]),
                                     gaps(part, original, index, close)):
            comparisons.append({"part": part["id"], "trial": trial["id"], "of": original["id"], "agree": first == again, "gap": gap})
    entry["repeats"] = {"repeats": len(comparisons), "agree": sum(c["agree"] for c in comparisons)}

    if part["type"] == "cbc":
        attributes = []
        for attribute, group in zip(part["attributes"], groups):
            levels = [{"id": level["id"], "label": level["label"], "weight": rounded(weights[i]), "se": rounded(errors[i])}
                      for level, i in zip(attribute["levels"], group)]
            best = max(range(len(group)), key=lambda k: weights[group[k]])
            clear = any(abs(weights[i]) > CLEAR * errors[i] for i in group)
            attributes.append({"id": attribute["id"], "name": attribute["name"], "best": attribute["levels"][best]["id"],
                               "importance": rounded(max(weights[i] for i in group) - min(weights[i] for i in group)),
                               "clear": clear, "levels": levels})
            if not clear:
                uncertain.append({"part": part["id"], "attribute": attribute["id"], "why": "no level 2 standard errors clear of zero"})
        entry["attributes"] = attributes
        held = [trial for trial in answered if trial.get("holdout")]
        hits = sum(hit(shown_rows(part, trial, index), answers[trial["id"]]["pick"] - 1, weights) for trial in held)
        entry["holdouts"] = {"tasks": len(held), "hits": rounded(hits), "rate": rounded(hits / len(held)) if held else None,
                             "chance": rounded(1 / 3)}
        if hits < len(held):
            uncertain.append({"part": part["id"], "why": f"{rounded(len(held) - hits)} of {len(held)} holdouts missed"})
    else:
        items = [{key: item[key] for key in ("id", "label", "src") if key in item} for item in part["items"]]
        for item in items:
            item.update(weight=rounded(weights[index[item["id"]]]), se=rounded(errors[index[item["id"]]]))
        entry["items"] = sorted(items, key=lambda item: -item["weight"])
        halves = [fit([choice for trial in fitted[k::2] for choice in choices_of(part, trial, answers[trial["id"]], index)],
                      len(index), groups)[0] for k in (0, 1)]
        r = pearson(*halves)
        entry["split_half"] = rounded(2 * r / (1 + r)) if r is not None and r > 0 else None  # Spearman-Brown; none at r <= 0

    middle = len(answered) // 2
    entry["early_late"] = {}
    for name, trials in (("early", answered[:middle]), ("late", answered[middle:])):
        own = [choice for trial in trials if not trial.get("holdout") for choice in choices_of(part, trial, answers[trial["id"]], index)]
        entry["early_late"][name] = {"trials": len(trials), "hit_rate": rounded(statistics.fmean([hit(rows, pick, weights) for rows, pick in own])) if own else None,
                                     "median_ms": median_ms([answers[trial["id"]] for trial in trials])}
    return entry, comparisons, uncertain


def sequence_part(part: dict, answers: dict) -> tuple:
    shown = {(trial["dimension"], trial["order"]): answers.get(trial["id"]) for trial in part["trials"]}
    dimensions, pairs, uncertain = [], [], []
    for dimension in part["dimensions"]:
        up, down = shown.get((dimension["id"], "up")), shown.get((dimension["id"], "down"))
        given = [answer for answer in (up, down) if answer]
        rows = [{k: 1.0} for k in range(STEPS)]
        weights, errors = fit([(rows, answer["best"] - 1) for answer in given], STEPS, [list(range(STEPS))])
        top = max(weights)
        tied = [k + 1 for k in range(STEPS) if weights[k] >= top - 1e-9]
        entry = {"id": dimension["id"], "name": dimension["name"],
                 "steps": [{"step": k + 1, **({"label": dimension["labels"][k]} if "labels" in dimension else {}),
                            "weight": rounded(weights[k]), "se": rounded(errors[k])} for k in range(STEPS)],
                 "best": statistics.fmean(tied) if given else None,
                 "up": {key: up[key] for key in ("best", "from", "to")} if up else None,
                 "down": {key: down[key] for key in ("best", "from", "to")} if down else None, "fine": None}
        if up and down:
            low, high = max(up["from"], down["from"]), min(up["to"], down["to"])
            entry["fine"] = [low, high] if low <= high else None
            apart = abs(up["best"] - down["best"])
            pairs.append(apart)
            if apart > 1:
                uncertain.append({"part": part["id"], "dimension": dimension["id"], "why": f"the bests up and down are {apart} steps apart"})
            if entry["fine"] is None:
                uncertain.append({"part": part["id"], "dimension": dimension["id"], "why": "the fine runs up and down don't meet"})
        dimensions.append(entry)
    entry = {"answered": sum(trial["id"] in answers for trial in part["trials"]), "of": len(part["trials"]),
             "dimensions": dimensions}
    return entry, pairs, uncertain


def tally(comparisons: list) -> dict:
    agree = sum(c["agree"] for c in comparisons)
    return {"repeats": len(comparisons), "agree": agree, "share": rounded(agree / len(comparisons)) if comparisons else None}


def profile_of(design: dict, answers: dict) -> dict:
    """The profile of checked answers to a checked design."""
    parts, comparisons, apart, uncertain, red, ticked, notes = [], [], [], [], [], [], []
    for part in design["parts"]:
        kind = part["type"]
        entry = {"id": part["id"], "type": kind, "title": part["title"]}
        mine = [answers[trial["id"]] for trial in part["trials"] if trial["id"] in answers]
        if kind in CHOICE and part.get("scored", True):
            more, found, unsure = choice_part(part, answers)
            comparisons += found
        elif kind == "pairwise":
            more, unsure = {"scored": False, "answered": len(mine), "of": len(part["trials"])}, []
        elif kind == "sequence":
            more, found, unsure = sequence_part(part, answers)
            apart += found
        else:
            more, unsure = {"answered": len(mine), "of": len(part["trials"])}, []
            if kind == "range":
                given = {trial["dimension"]: answers[trial["id"]] for trial in part["trials"] if trial["id"] in answers}
                more["dimensions"] = [{"id": dimension["id"], "name": dimension["name"], "ordered": dimension["ordered"],
                                       "answer": {key: value for key, value in given[dimension["id"]].items()
                                                  if key in ("from", "to", "fine", "best")} if dimension["id"] in given else None}
                                      for dimension in part["dimensions"]]
            elif kind == "notes":
                items = {item["id"]: item for item in part["items"]}
                notes += [{"part": part["id"], "item": trial["item"], **{key: items[trial["item"]][key] for key in ("label", "src")
                                                                        if key in items[trial["item"]]}, "note": answers[trial["id"]]["note"]}
                          for trial in part["trials"] if trial["id"] in answers and answers[trial["id"]]["note"]]
            elif kind == "redlines":
                red += [line for answer in mine for line in answer["checked"] + answer["own"] if line not in red]
            elif kind == "checklist":
                ticked += [{"part": part["id"], "mark": part["mark"], "lines": answer["checked"] + answer["own"]} for answer in mine]
        entry.update(more)
        parts.append(entry)
        uncertain += unsure
    met = None if not comparisons else sum(c["agree"] for c in comparisons) / len(comparisons) >= BAR
    restart = {**tally(comparisons), "bar": BAR, "met": met,
               "near_tie": tally([c for c in comparisons if c["gap"] < NEAR]),
               "clear": tally([c for c in comparisons if c["gap"] >= NEAR]), "near_tie_gap": NEAR,
               "missed": [{key: rounded(c[key]) if key == "gap" else c[key] for key in ("part", "trial", "of", "gap")}
                          for c in comparisons if not c["agree"]],
               "sequences": {"dimensions": len(apart), "same_best": sum(gap == 0 for gap in apart),
                             "within_one": sum(gap <= 1 for gap in apart)},
               "rule": "the hidden repeats of pairwise, maxdiff and cbc parts; sequences (up against down) beside it, not in it. "
                       "A page restarts at 80% or more and when the Board confirms its summary; nothing restarts by itself"}
    trials = [trial["id"] for part in design["parts"] for trial in part["trials"]]
    return {"format": "taste-profile-1", "page": design["page"], "session": design["session"], "seed": design["seed"],
            "design_id": design["design_id"], "estimator": ESTIMATOR,
            "answered": {"trials": sum(key in answers for key in trials), "of": len(trials),
                         "unanswered": [key for key in trials if key not in answers]},
            "restart_check": restart, "parts": parts, "red_lines": red, "ticked": ticked, "notes": notes, "uncertain": uncertain}


# The export.

def design_of(page: str, session_file: str, root: Path) -> tuple:
    here, path = build.session_folder(page, session_file, root)
    raw = build.read_json(path)
    need(isinstance(raw, dict) and raw.get("mode") == "trial", 'analyze.py reads a trial session, one with "mode": "trial"')
    return here, build.checked_trial(raw, page, here, root, set())


def whole_number(value, low: int, high: int) -> bool:
    return type(value) is int and low <= value <= high


def checked_answer(part: dict, trial: dict, answer) -> dict:
    what = f"the answer to {trial['id']}"
    need(isinstance(answer, dict), f"{what} isn't an object")
    kind = part["type"]
    if kind == "pairwise":
        need(isinstance(answer.get("pick"), str) and answer["pick"] in trial["items"], f"{what}: the pick isn't an item shown")
    elif kind == "maxdiff":
        best, worst = answer.get("best"), answer.get("worst")
        need(isinstance(best, str) and isinstance(worst, str) and best in trial["items"] and worst in trial["items"] and best != worst,
             f"{what}: best and worst must be two different items shown")
    elif kind == "cbc":
        need(whole_number(answer.get("pick"), 1, len(trial["options"])), f"{what}: the pick is an option's place, 1 to {len(trial['options'])}")
    elif kind == "sequence":
        best, low, high = answer.get("best"), answer.get("from"), answer.get("to")
        need(all(whole_number(value, 1, STEPS) for value in (best, low, high)) and low <= best <= high,
             f"{what}: best, from and to are steps 1 to {STEPS}, from <= best <= to")
    elif kind == "range":
        dimension = next(entry for entry in part["dimensions"] if entry["id"] == trial["dimension"])
        values = dimension["values"]
        fine = (lambda value: isinstance(value, str) and value in values)
        best = answer.get("best")
        need(best is None or fine(best), f"{what}: the best isn't one of the values")
        if dimension["ordered"]:
            low, high = answer.get("from"), answer.get("to")
            need((low is None and high is None) or (fine(low) and fine(high) and values.index(low) <= values.index(high)),
                 f"{what}: from and to are two values, lowest first, or both null")
            need(best is None or (low is not None and values.index(low) <= values.index(best) <= values.index(high)),
                 f"{what}: the best is a fine value, from <= best <= to")
        else:
            need(isinstance(answer.get("fine"), list) and all(fine(value) for value in answer["fine"]), f"{what}: fine lists values")
            need(best is None or best in answer["fine"], f"{what}: the best is one of the fine values")
    elif kind == "notes":
        need(isinstance(answer.get("note"), str), f"{what}: the note is text")
    else:
        need(isinstance(answer.get("checked"), list) and all(isinstance(line, str) and line in trial["candidates"] for line in answer["checked"])
             and isinstance(answer.get("own"), list) and all(isinstance(line, str) for line in answer["own"]),
             f"{what}: checked lists the lines shown, own lists text")
    ms = answer.get("ms")
    need(ms is None or (isinstance(ms, (int, float)) and not isinstance(ms, bool) and 0 <= ms < math.inf), f"{what}: ms is a time")
    return answer if ms is not None else {key: value for key, value in answer.items() if key != "ms"}


def export_of(design: dict, here: Path, page: str, answers_file: str) -> tuple:
    path = build.directly_in(here, answers_file)
    need(path.suffix == ".json", f"{path.name}: the export is a .json file")
    raw = build.read_json(path)
    need(isinstance(raw, dict) and raw.get("format") == FORMAT, f"{path.name} isn't a trial page's export ({FORMAT})")
    need(raw.get("page") == page, f"{path.name} is for page {str(raw.get('page'))[:40]!r}, not {page}")
    need(raw.get("session") == here.name, f"{path.name} is for session {str(raw.get('session'))[:40]!r}, not {here.name}")
    need(raw.get("design_id") == design["design_id"],
         f"{path.name} answers design {str(raw.get('design_id'))[:20]!r}, and session.json now makes {design['design_id']}: "
         "the session changed after the page was made")
    answers = raw.get("answers")
    need(isinstance(answers, dict), f"{path.name}: answers isn't an object")
    trials = {trial["id"]: (part, trial) for part in design["parts"] for trial in part["trials"]}
    checked = {}
    for key, answer in answers.items():
        need(key in trials, f"{path.name} answers trial {key[:40]!r}, which the design hasn't")
        checked[key] = checked_answer(*trials[key], answer)
    return path, raw, checked


def write_profile(here: Path, data: bytes) -> Path:
    target = here / f"profile-{here.parent.name}-{here.name}.json"
    try:
        descriptor, temporary = tempfile.mkstemp(dir=here, prefix=".profile-", suffix=".tmp")
        try:
            with os.fdopen(descriptor, "wb") as file:
                file.write(data)
            os.chmod(temporary, 0o644)
            os.replace(temporary, target)
        except OSError:
            Path(temporary).unlink(missing_ok=True)
            raise
    except OSError as error:
        raise Refused(f"can't write {target.name}: {error}") from error
    return target


def analyze(page: str, session_file: str, answers_file: str, root: Path = build.ROOT) -> str:
    """Write the sitting's profile beside its export and return the result line. Raises Refused, having written nothing."""
    here, design = design_of(page, session_file, root)
    path, raw, answers = export_of(design, here, page, answers_file)
    profile = profile_of(design, answers)
    profile.update(answers_file=path.name, exported_at=str(raw.get("exported_at"))[:40] if isinstance(raw.get("exported_at"), str) else None)
    target = write_profile(here, (json.dumps(profile, indent=1, ensure_ascii=False) + "\n").encode("utf-8"))
    check, apart = profile["restart_check"], profile["restart_check"]["sequences"]
    share = "no hidden repeats answered" if check["met"] is None else \
        f"hidden repeats agree {check['agree']} of {check['repeats']} ({check['share']:.0%}), the 80% bar {'met' if check['met'] else 'not met'}"
    return (f"wrote {target}: {profile['answered']['trials']} of {profile['answered']['of']} trials answered; {share}; "
            f"near ties {check['near_tie']['agree']} of {check['near_tie']['repeats']}, clear {check['clear']['agree']} of "
            f"{check['clear']['repeats']}; sequences up and down: {apart['same_best']} of {apart['dimensions']} the same best, "
            f"{apart['within_one']} within a step; {len(profile['uncertain'])} uncertain")


# The recovery.

def respondent(design: dict, rng) -> tuple:
    """A known profile, and its answers to every trial of the design."""
    truth, answers = {}, {}

    def noisy(values):
        return [x + rng.gauss(0, SIGMA) for x in values]

    def place(values, pick=max):
        return values.index(pick(values))

    for part in design["parts"]:
        kind = part["type"]
        true = {}
        if kind in ("pairwise", "maxdiff"):
            true = {item["id"]: rng.gauss(0, 1) for item in part["items"]}
        elif kind == "cbc":
            for attribute in part["attributes"]:
                draws = [rng.gauss(0, 1) for _ in attribute["levels"]]
                centre = statistics.fmean(draws)
                true.update({(attribute["id"], level["id"]): x - centre for level, x in zip(attribute["levels"], draws)})
            spread = math.sqrt(sum(statistics.fmean([true[(attribute["id"], level["id"])] ** 2 for level in attribute["levels"]])
                                   for attribute in part["attributes"]))
            true = {key: x / spread for key, x in true.items()}  # an option's utility has SD 1
        elif kind == "sequence":
            for dimension in part["dimensions"]:
                ideal = rng.uniform(1, STEPS)
                curve = [-(k - ideal) ** 2 for k in range(1, STEPS + 1)]
                centre, spread = statistics.fmean(curve), statistics.pstdev(curve)
                true[dimension["id"]] = (ideal, [(x - centre) / spread for x in curve])
        truth[part["id"]] = true
        for trial in part["trials"]:
            if kind in ("pairwise", "maxdiff"):
                seen = noisy([true[key] for key in trial["items"]])
                answer = {"pick": trial["items"][place(seen)]} if kind == "pairwise" else \
                    {"best": trial["items"][place(seen)], "worst": trial["items"][place(seen, min)]}
            elif kind == "cbc":
                seen = noisy([sum(true[(attribute["id"], option["levels"][attribute["id"]])] for attribute in part["attributes"])
                              for option in trial["options"]])
                answer = {"pick": place(seen) + 1}
            elif kind == "sequence":
                seen = noisy(true[trial["dimension"]][1])
                best = low = high = place(seen)
                while low > 0 and seen[low - 1] >= seen[best] - 1:
                    low -= 1
                while high < STEPS - 1 and seen[high + 1] >= seen[best] - 1:
                    high += 1
                answer = {"best": best + 1, "from": low + 1, "to": high + 1}
            elif kind == "range":
                values = next(d for d in part["dimensions"] if d["id"] == trial["dimension"])["values"]
                answer = {"from": values[0], "to": values[-1], "best": None}
                if not next(d for d in part["dimensions"] if d["id"] == trial["dimension"])["ordered"]:
                    answer = {"fine": values, "best": None}
            elif kind == "notes":
                answer = {"note": ""}
            else:
                answer = {"checked": [], "own": []}
            answers[trial["id"]] = {**answer, "ms": 1000}
    return truth, answers


def percentile(values: list, share: float):
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(share * len(ordered)))] if ordered else None


def recovery(design: dict, replicates: int = REPLICATES, seed: int = 1) -> dict:
    """How well the design recovers a known profile, over `replicates` synthetic respondents."""
    rng = random.Random(f"{seed}/{design['design_id']}")
    runs = {part["id"]: {"r": [], "slope": [], "covered": [], "best": {}, "steps": []} for part in design["parts"]}
    checks = []
    for _ in range(replicates):
        truth, answers = respondent(design, rng)
        profile = profile_of(design, answers)
        checks.append(profile["restart_check"])
        for part, entry in zip(design["parts"], profile["parts"]):
            run, true = runs[part["id"]], truth[part["id"]]
            if part["type"] in ("pairwise", "maxdiff") and part.get("scored", True):
                centre = statistics.fmean(true.values())
                pairs = [(true[item["id"]] - centre, item["weight"], item["se"]) for item in entry["items"]]
            elif part["type"] == "cbc":
                pairs = [(true[(attribute["id"], level["id"])], level["weight"], level["se"])
                         for attribute in entry["attributes"] for level in attribute["levels"]]
                for attribute in part["attributes"]:
                    found = next(a for a in entry["attributes"] if a["id"] == attribute["id"])["best"]
                    wanted = max(attribute["levels"], key=lambda level: true[(attribute["id"], level["id"])])["id"]
                    run["best"].setdefault(attribute["id"], []).append(found == wanted)
            elif part["type"] == "sequence":
                for dimension in entry["dimensions"]:
                    ideal = round(true[dimension["id"]][0])
                    run["steps"].append(None if dimension["best"] is None else abs(dimension["best"] - ideal))
                continue
            else:
                continue
            r = pearson([t for t, _, _ in pairs], [w for _, w, _ in pairs])
            if r is not None:
                run["r"].append(r)
            run["slope"].append(sum(t * w for t, w, _ in pairs) / sum(t * t for t, _, _ in pairs))
            run["covered"].append(statistics.fmean([abs(w - SCALE * t) <= CLEAR * se for t, w, se in pairs]))
    parts, cut = [], []
    for part in design["parts"]:
        run, kind = runs[part["id"]], part["type"]
        entry = {"id": part["id"], "type": kind}
        if kind in ("pairwise", "maxdiff", "cbc") and part.get("scored", True):
            bound = BOUNDS["cbc" if kind == "cbc" else "items"]
            r = statistics.fmean(run["r"]) if run["r"] else 0.0
            entry.update(r=rounded(r), r_p5=rounded(percentile(run["r"], 0.05)), slope=rounded(statistics.fmean(run["slope"])),
                         slope_expected=rounded(SCALE), coverage_2se=rounded(statistics.fmean(run["covered"])), bound=bound,
                         within=r >= bound)
            if not entry["within"]:
                cut.append({"part": part["id"], "why": f"its weights correlate {r:.2f} with the truth, under {bound}"})
            if kind == "cbc":
                entry["attributes"] = []
                for attribute in part["attributes"]:
                    rate = statistics.fmean(run["best"][attribute["id"]])
                    entry["attributes"].append({"id": attribute["id"], "best_level_found": rounded(rate), "within": rate >= BOUNDS["best level"]})
                    if rate < BOUNDS["best level"]:
                        cut.append({"part": part["id"], "attribute": attribute["id"],
                                    "why": f"its best level found in {rate:.0%} of runs, under {BOUNDS['best level']:.0%}"})
        elif kind == "sequence":
            apart = [gap for gap in run["steps"] if gap is not None]
            within = statistics.fmean([gap <= 1 for gap in apart])
            entry.update(exact=rounded(statistics.fmean([gap == 0 for gap in apart])), within_one=rounded(within),
                         bound=BOUNDS["sequence"], within=within >= BOUNDS["sequence"])
            if not entry["within"]:
                cut.append({"part": part["id"], "why": f"its best step within one of the ideal in {within:.0%} of dimensions, under {BOUNDS['sequence']:.0%}"})
        else:
            continue
        parts.append(entry)
    shares = [check["share"] for check in checks if check["share"] is not None]
    near = [check["near_tie"]["share"] for check in checks if check["near_tie"]["share"] is not None]
    clear = [check["clear"]["share"] for check in checks if check["clear"]["share"] is not None]
    return {"format": "taste-recovery-1", "page": design["page"], "session": design["session"], "design_id": design["design_id"],
            "replicates": replicates, "seed": seed, "sigma": SIGMA, "reliability": rounded(1 / (1 + SIGMA ** 2)),
            "bounds": BOUNDS, "parts": parts,
            "repeat_check": {"repeats": checks[0]["repeats"] if checks else 0,
                             "share": rounded(statistics.fmean(shares)) if shares else None,
                             "share_p5": rounded(percentile(shares, 0.05)),
                             "met": rounded(statistics.fmean([check["met"] for check in checks if check["met"] is not None]))
                             if shares else None,
                             "near_tie": rounded(statistics.fmean(near)) if near else None,
                             "clear": rounded(statistics.fmean(clear)) if clear else None, "bar": BAR},
            "cut": cut, "within_bounds": not cut}


def recover(page: str, session_file: str, root: Path = build.ROOT, replicates: int = REPLICATES) -> str:
    """The recovery check of the sitting's design, as JSON. Writes nothing."""
    _, design = design_of(page, session_file, root)
    return json.dumps(recovery(design, replicates), indent=1, ensure_ascii=False)


def main(argv: "list | None" = None) -> int:
    parser = argparse.ArgumentParser(description="Analyse a taste sitting's answers, or check its design recovers a known profile.")
    parser.add_argument("--page", required=True)
    parser.add_argument("--session", required=True, help="the sitting's session.json")
    what = parser.add_mutually_exclusive_group(required=True)
    what.add_argument("--answers", help="the trial page's export, beside session.json")
    what.add_argument("--recover", action="store_true", help="run the synthetic respondent on the design; write nothing")
    args = parser.parse_args(argv)
    try:
        print(recover(args.page, args.session) if args.recover else analyze(args.page, args.session, args.answers))
    except Refused as error:
        print(f"refused: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
