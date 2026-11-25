#!/usr/bin/env python3
"""Score a ux-expert findings table against the calibration answer key.

Usage: python3 tools/ux/calibration/score.py <findings.md> [--key answer-key.json]

Reads the first markdown table whose header has the columns page, where, criterion and
level (the ux-checklist skill's findings table). A row finds a planted defect when its page
cell contains the defect's page name, its criterion ids overlap the defect's, and one of the
defect's locators appears in its where or evidence cell (case-insensitive). A row that finds
none is "invented": it may still be a real defect nobody planted, so the CEO judges each one.
Prints, by evidence level, the defects found, the invented rows and the defects missed (at the
level their kind calls for: EXPECTED); then the missed defects by kind, and duplicates.
"""
import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

KEY = Path(__file__).resolve().parent / "answer-key.json"
CRITERION = re.compile(r"\b\d\.\d{1,2}\.\d{1,2}\b|\bH(?:10|[1-9])\b|\b(?:CLS|LCP|INP)\b|\bi18n\b", re.I)
LEVELS = ["L0", "L1", "L2", "L3", "L?"]
REQUIRED = {"page", "where", "criterion", "level"}
# The level a defect's kind calls for (agent file, "Evidence"): a check makes it L2, a judgement L3.
EXPECTED = {"axe": "L2", "measured": "L2", "playwright": "L2", "judgement": "L3"}


def cells(line):
    return [c.strip() for c in line.strip().strip("|").split("|")]


def parse_table(text):
    """Rows of the first findings table, as dicts keyed by the lower-cased header; None if there's none."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if not line.lstrip().startswith("|"):
            continue
        header = [h.lower() for h in cells(line)]
        if not REQUIRED <= set(header):
            continue
        rows = []
        for row in lines[i + 2:]:
            if not row.lstrip().startswith("|"):
                break
            values = cells(row)
            rows.append(dict(zip(header, values + [""] * (len(header) - len(values)))))
        return rows
    return None


def norm(criterion):
    return "i18n" if criterion.lower() == "i18n" else criterion.upper()


def criteria(cell):
    return {norm(c) for c in CRITERION.findall(cell)}


def level(cell):
    m = re.search(r"\bL[0-3]\b", cell, re.I)
    return m.group(0).upper() if m else "L?"


def confirmed(row):
    return row.get("confirmed-by", "").strip(" `") not in ("", "-", "—", "–")


def match(row, defects):
    """The defect this row finds (most locator hits, then key order), or None."""
    page = row.get("page", "").lower()
    found = criteria(row.get("criterion", ""))
    text = f"{row.get('where', '')} {row.get('evidence', '')}".lower()
    best, best_hits = None, 0
    for d in defects:
        if d["page"] not in page or not found & {norm(c) for c in d["criteria"]}:
            continue
        hits = sum(loc.lower() in text for loc in d["locators"])
        if hits > best_hits:
            best, best_hits = d, hits
    return best


def score(rows, key):
    defects = key["defects"]
    found = {lv: 0 for lv in LEVELS}
    found_confirmed = {lv: 0 for lv in LEVELS}
    invented = {lv: 0 for lv in LEVELS}
    invented_rows = []
    hits = Counter()
    for n, row in enumerate(rows, 1):
        lv = level(row.get("level", ""))
        d = match(row, defects)
        if d is None:
            invented[lv] += 1
            invented_rows.append((n, row))
            continue
        hits[d["id"]] += 1
        if hits[d["id"]] == 1:
            found[lv] += 1
            found_confirmed[lv] += confirmed(row)
    missed = [d for d in defects if d["id"] not in hits]
    missed_by_level = {lv: 0 for lv in LEVELS}
    for d in missed:
        missed_by_level[EXPECTED[d["kind"]]] += 1
    return {
        "rows": len(rows),
        "found": found,
        "found_confirmed": found_confirmed,
        "invented": invented,
        "invented_rows": invented_rows,
        "missed": missed,
        "missed_by_level": missed_by_level,
        "duplicates": {i: c - 1 for i, c in hits.items() if c > 1},
        "defects": len(defects),
    }


def report(result):
    out = [f"{result['rows']} findings; {result['defects'] - len(result['missed'])} of {result['defects']} planted defects found."]
    out.append("level  found  of which confirmed  invented  missed (expected level)")
    for lv in LEVELS:
        if result["found"][lv] or result["invented"][lv] or result["missed_by_level"][lv]:
            out.append(f"{lv:<6} {result['found'][lv]:>5}  {result['found_confirmed'][lv]:>18}  {result['invented'][lv]:>8}"
                       f"  {result['missed_by_level'][lv]:>23}")
    by_kind = Counter(d["kind"] for d in result["missed"])
    out.append("missed: " + (", ".join(f"{d['id']} ({d['kind']})" for d in result["missed"]) or "none"))
    if by_kind:
        out.append("missed by kind: " + ", ".join(f"{k} {v}" for k, v in sorted(by_kind.items())))
    if result["duplicates"]:
        out.append("duplicates: " + ", ".join(f"{i} +{c}" for i, c in sorted(result["duplicates"].items())))
    for n, row in result["invented_rows"]:
        out.append(f"invented, row {n}: {row.get('page', '')} | {row.get('where', '')} | {row.get('criterion', '')} | {row.get('level', '')}")
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("findings")
    ap.add_argument("--key", default=str(KEY))
    args = ap.parse_args(argv)
    rows = parse_table(Path(args.findings).read_text(encoding="utf-8"))
    if rows is None:
        print("no findings table (columns page, where, criterion, level) in " + args.findings, file=sys.stderr)
        return 1
    key = json.loads(Path(args.key).read_text(encoding="utf-8"))
    print(report(score(rows, key)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
