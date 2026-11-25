#!/usr/bin/env python3
"""The CEO's NEEDS-CEO-NOW watcher: prints the NEEDS-CEO-NOW lines that weren't in the files when it started, then exits.

Every 60 seconds it re-reads each glob it was given, so a file created after it started (a new order's
content/orders/<directive id>/<n>/ceo-questions.md) is read in full, and each of its NEEDS-CEO-NOW lines is new. A line
counts as the capacity scan reads one: `NEEDS-CEO-NOW` after a list item's `- `, bold or a writer (`CTO NEEDS-CEO-NOW`;
capacity_scan's CQ_LEAD). The CEO starts it in the background with both layouts' globs:

    python3 scripts/needs_watch.py '<repo>/workspaces/*/content/ceo-questions.md' \\
        '<repo>/workspaces/*/content/orders/*/*/ceo-questions.md'

It only reads.
"""
import glob
import re
import sys
import time

from capacity_scan import CQ_LEAD

ASK = re.compile(CQ_LEAD + 'NEEDS-CEO-NOW')


def lines(paths):
    """The set of NEEDS-CEO-NOW lines (each cut to 400 characters) in the files the globs match now."""
    found = set()
    for path in paths:
        for name in glob.glob(path):
            try:
                for line in open(name, encoding='utf-8', errors='replace'):
                    if ASK.match(line):
                        found.add(line.strip()[:400])
            except OSError:
                pass
    return found


def watch(paths, sleep=time.sleep, every=60):
    """Wait until a NEEDS-CEO-NOW line not there at the start appears; return the new ones."""
    base = lines(paths)
    while True:
        sleep(every)
        new = lines(paths) - base
        if new:
            return new


def main(argv=None):
    for line in watch(sys.argv[1:] if argv is None else argv):
        print(line)
    return 0


if __name__ == '__main__':
    sys.exit(main())
