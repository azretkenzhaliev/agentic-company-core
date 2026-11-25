#!/usr/bin/env python3
"""The question files' measure. It only reads.

For each product it prints, at the time it runs:
- MISFILED: the lines in its orders' own files (content/orders/ and orders-closed/) whose word is followed by another
  order's ref, as the scan warns (COORD and ANSWER lines go elsewhere on purpose), of the lines with an order's ref;
  then every kind and file's count (COORD and ANSWER too, and the product file's lines against the `## ORDER`
  heading they sit under). The aim: 0 in order files.
- the boundary read: the bytes an agent's first read of its order prints, the whole of its open order's file
  (`sed -n '1,$p'`) plus the product file's `grep -n '^CEO'` lines, as the median and the largest over the open
  orders' files (content/orders/ only). Later reads print only new lines, so this is the most a read prints. Aim:
  a median under 20 KB.
- the product file's size, against kb_lint's 30 KB.

    python3 scripts/cq_measure.py
"""
import argparse
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import capacity_scan as scan  # noqa: E402

WORKSPACES = Path(__file__).resolve().parents[1] / "workspaces"
LIMIT = 30 * 1024  # kb_lint's size limit for a page


def measure(workspaces):
    """[(product, misfiled in order files, lines checked there, misfiled of every kind and file, checked of those, the
    boundary reads in bytes, the product file's bytes or None)], by product."""
    found = {}
    for product, page in scan.question_pages(workspaces):
        found.setdefault(product, []).append(page)
    rows = []
    for product, pages in found.items():
        own = [(product, page) for page in pages if scan.page_order(page)]
        tied, every = [], []
        wrong = scan.misfiled(own, tied=tied)
        old = scan.misfiled([(product, page) for page in pages], every=True, tied=every)
        main = [page for page in pages if not scan.page_order(page)]
        size = main[0].stat().st_size if main else None
        broadcast = 0
        if main:
            broadcast = sum(len(line.encode()) + 1 for line in main[0].read_text(errors="replace").split("\n")
                            if line.startswith("CEO"))
        reads = [page.stat().st_size + broadcast for page in pages
                 if scan.page_order(page) and page.parts[-4] == "orders"]
        rows.append((product, len(wrong), len(tied), len(old), len(every), reads, size))
    return rows


def format_row(product, wrong, tied, old, every, reads, size):
    kb = lambda n: f"{n / 1024:.1f} KB"  # noqa: E731
    read = (f"median {kb(statistics.median(reads))}, largest {kb(max(reads))}, over {len(reads)} open order file(s)"
            if reads else "no open order file")
    whole = f"{kb(size)} (limit {kb(LIMIT)})" if size is not None else "none"
    return (f"{product}: MISFILED in order files {wrong} of {tied}; every kind and file {old} of {every}; "
            f"boundary read {read}; product file {whole}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--workspaces", type=Path, default=WORKSPACES)
    args = parser.parse_args(argv)
    for row in measure(args.workspaces):
        print(format_row(*row))
    return 0


if __name__ == "__main__":
    sys.exit(main())
