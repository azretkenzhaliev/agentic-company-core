#!/usr/bin/env python3
"""How long the orders to each role are, over a date range.

An agent that knows its craft (its own knowledge base) needs less Context and fewer Constraints in its orders. Run it
over a range before and after a change to the agents' knowledge bases, and compare.

Reads knowledge/board/directives/ (archives included), so it counts the orders the CEO files, not the CTO's own
orders to its team. An order's text is
a fenced block whose first line is `ORDER <id>   from: <role>   to: <role>`, or a status-log row that holds one (line
breaks written `<br>`). Its date is the earliest of that row's and of every status-log row of its directive that logs or
sends it: the row names ORDER or Orders, says logged, sent, sending or "in full", and holds `/<n>` or a range
`/<a>-/<b>`; a NEXT row isn't one. A row that only mentions an order in passing can date it too, never earlier than its
real row. Its length is the characters of its Context plus its Constraints, whitespace collapsed (an order with neither
counts 0). Orders a row dates in the range whose text the KB doesn't hold (sent from a scratch file) are counted as "no
text", an upper bound: a sent row's other numbers (another directive's order, a ruling) count there too, never in the
means. Orders with text and no dated row are counted as "undated". It changes nothing and prints counts and lengths
only.
"""

import argparse
import re
import statistics
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIRECTIVES = Path("knowledge") / "board" / "directives"
DIRECTIVE_OF = re.compile(r"^(D-\d{8}-[a-z0-9-]+?)(?:-archive(?:-\d+)?)?\.md$")
HEAD = re.compile(r"ORDER (D-\d{8}-[a-z0-9-]+)/(\d+)\s+from:\s*(\S+)\s+to:\s*([a-z-]+)", re.IGNORECASE)
LABEL = re.compile(r"(?:^|(?<=\s))(Objective|Why|Context|Product\(s\)/repos|Acceptance criteria[^:]{0,160}|Constraints|"
                   r"Report back with|Question|Decision it feeds|Tasks):(?=\s|$)")
ROW = re.compile(r"^\| (\d{4}-\d{2}-\d{2}) \| [^|]+ \| (.*)\|\s*$")
SENT = re.compile(r"\b(?:logged|sent|sending|in full)\b")
NAMES_ORDERS = re.compile(r"\bORDERS?\b|\bOrders?\b")
NUMBER = re.compile(r"(?:(D-\d{8}-[a-z0-9-]+)|(?<![\w-]))/(\d+)(?:\s*-\s*/?(\d+))?(?![\d.])")
FIELDS = ("Context", "Constraints")


def length_of(order_text: str) -> int:
    """Characters of an order's Context plus Constraints, whitespace collapsed."""
    flat = " ".join(order_text.split())
    marks = list(LABEL.finditer(flat))
    total = 0
    for i, mark in enumerate(marks):
        if mark.group(1) in FIELDS:
            stop = marks[i + 1].start() if i + 1 < len(marks) else len(flat)
            total += len(flat[mark.end():stop].strip())
    return total


def orders_in(text: str) -> dict:
    """{(directive, n): (to, length, date or None)} for every order whose text is in this file; a row gives its date."""
    found, lines, i = {}, text.splitlines(), 0
    while i < len(lines):
        line, day = lines[i], None
        head = HEAD.match(line.strip())
        if head and i > 0 and lines[i - 1].strip().startswith("```"):
            end = i + 1
            while end < len(lines) and not lines[end].strip().startswith("```"):
                end += 1
            body, i = "\n".join(lines[i:end]), end
        elif ROW.match(line) and HEAD.search(ROW.match(line).group(2)):
            row = ROW.match(line)
            head = HEAD.search(row.group(2))
            body, day = row.group(2)[head.start():].replace("<br>", " "), date.fromisoformat(row.group(1))
            if not LABEL.search(body):
                head = None  # a row that names an order without holding it
        else:
            head = None
        if head:
            found.setdefault((head.group(1), int(head.group(2))), (head.group(4).lower(), length_of(body), day))
        i += 1
    return found


def sent_dates(text: str, directive: str) -> dict:
    """{(directive, n): first date} from status-log rows that log or send orders."""
    dates = {}
    for line in text.splitlines():
        row = ROW.match(line)
        event = row.group(2).strip() if row else ""
        if not row or event.startswith("NEXT") or not NAMES_ORDERS.search(event) or not SENT.search(event):
            continue
        day = date.fromisoformat(row.group(1))
        for number in NUMBER.finditer(event):
            first = int(number.group(2))
            last = int(number.group(3) or first)
            for n in range(first, (last if first <= last <= first + 50 else first) + 1):
                key = (number.group(1) or directive, n)
                dates[key] = min(day, dates.get(key, day))
    return dates


def measure(folder: Path, since: date, until: date) -> tuple:
    """({role: [lengths]}, no-text count in the range, undated count)."""
    texts, dates = {}, {}
    for path in sorted(folder.glob("D-*.md")):
        directive = DIRECTIVE_OF.match(path.name)
        if not directive:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for key, (role, length, day) in orders_in(text).items():
            texts.setdefault(key, (role, length))
            if day:
                dates[key] = min(day, dates.get(key, day))
        for key, day in sent_dates(text, directive.group(1)).items():
            dates[key] = min(day, dates.get(key, day))
    per_role, undated = {}, 0
    for key, (role, length) in texts.items():
        day = dates.get(key)
        if day is None:
            undated += 1
        elif since <= day <= until:
            per_role.setdefault(role, []).append(length)
    no_text = sum(1 for key, day in dates.items() if key not in texts and since <= day <= until)
    return per_role, no_text, undated


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--since", type=date.fromisoformat, required=True, help="first day, YYYY-MM-DD (UTC)")
    parser.add_argument("--until", type=date.fromisoformat, required=True, help="last day, YYYY-MM-DD (UTC)")
    parser.add_argument("--root", type=Path, default=ROOT, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    per_role, no_text, undated = measure(args.root / DIRECTIVES, args.since, args.until)
    print(f"Orders in {DIRECTIVES.as_posix()}/ dated {args.since} to {args.until}; Context plus Constraints, characters")
    print(f"{'to':20} {'orders':>6} {'mean':>6} {'median':>6}")
    rows = sorted(per_role.items(), key=lambda kv: -len(kv[1]))
    rows.append(("all", [n for _, lengths in rows for n in lengths]))
    for role, lengths in rows:
        if lengths:
            print(f"{role:20} {len(lengths):6} {round(statistics.mean(lengths)):6} {round(statistics.median(lengths)):6}")
    print(f"no text in the KB, dated in the range: at most {no_text}; text but no dated row, any date: {undated}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
