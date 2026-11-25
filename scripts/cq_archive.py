#!/usr/bin/env python3
"""Move a ceo-questions.md's handled lines, word for word, to ceo-questions-archive.md beside it.
Whoever writes a RESUME POINT runs it for their own order (cto.md, Working rules, "Logs"):

    python3 <main checkout>/scripts/cq_archive.py <main checkout>/workspaces/<product>/content/ceo-questions.md --order <order id> [--dry-run]

Both paths absolute, no `cd`: scripts/hooks/cq_write.py refuses a relative `scripts/` from a worktree of this repo,
its own copy.

With `--add '<line>' --order <order id>` it moves nothing: it puts that one line under the order's last heading,
after its last line, by the same swap as a move, so a REPORT, HANDOVER, NEEDS, QUESTION or BLOCKED line lands under
its own order. A `>>` lands under the file's last heading, another order's once one is added after it.
With no section headed so, it adds nothing and exits 2. The line is one line: text
str.splitlines() would split (\r too) is refused. After the grace period the file is read back; a line a writer's
whole-file write dropped is added once more, and if it's dropped again it exits 1; one the archive beside it gained
meanwhile was moved there on purpose, and isn't. An order's own file (content/orders/<directive id>/<n>/
ceo-questions.md) has one heading, its line 1, so the line lands at its end.

A section is a `# ` or `## ` heading and its lines; its order is the id after ORDER in the heading, and --order and
--closed name only such ids (a heading without one is no order's). What moves, under a copy of its section's heading
appended to the archive:
- HANDLED lines, but one whose first named order is another with a heading in the file, outside this run's: it stays
  until that order's own run;
- with --order, also a HANDLED line under another order's heading whose first named order is this one: by its id
  (D-20260111-x/1) or by the id's end from the slash (/1, as in /1.WS1), its own heading's directive's order when the
  file has that heading, else the order whose heading is the last one before the line ending so. It goes under this
  order's heading. A `>>` lands a line under the file's last heading;
- a REPORT line that a later line of the same order marks `ACTED: <id>, <id>`, an id being the REPORT's own
  (D-20260111-x/1.WS1.T4) or its end from a slash (/1.WS1.T4);
- a RESUME POINT that a later one of the same order and lane supersedes, by its first date and time (2026-01-12T00:05Z
  or 2026-01-12 00:05:30Z, so its own time comes first; a line whose first time has no date can't be ordered, so it
  stays). Its lane is a /34.WS1 right after the words, or else the order itself;
- with --closed <order id>, that order's whole sections (their blank lines leave the file; the archive has its own);
  with --all too, every line of them but CEO and PAUSE lines, which keep their heading (the CEO
  moves its own), but only when the order's status log has its CLOSED row (a DONE report alone isn't
  enough), none is an
  ask the scan reads as unanswered (capacity_scan.unanswered, whatever its age), none is another order's
  (capacity_scan.misfiled: it goes under that order's heading first), and no line elsewhere points into them (`full
  text under "## ORDER <id>"`); else it moves nothing, names each such line and exits 1;
- with --trim alone, in a product's content/ceo-questions.md, each LANES or DEPLOY DONE line whose first date and
  time is over 48 h old, but the latest LANES DUTY line and each TOKEN claim no later line releases.
What never moves: a line starting with CEO (the CEO moves its own), a line naming NEEDS-CEO-NOW that isn't HANDLED, a
PAUSE line, a lane's latest RESUME POINT outside a closed section, and any other line (ANSWER, COORDINATION, FYI, ...):
move those by hand, while they stand in the file: `>>` the CEO line with its lines, in their order, as one heredoc, to
the archive by its absolute path, then Edit them out of the file from the last line up, or the CEO line with its
numbered or indented lines in one Edit. A line under no heading never
moves. A line scripts/hooks/cq_write.py's ceo_line counts as the CEO's (a HANDLED line with `(CEO` as its writer field
too) and the indented, numbered or `(` lines right under it, or under one of them, are one reply to the capacity scan
(together): they move together or stay together, so one that stays keeps the rest, and a CEO line never loses its
lines to the archive, nor they their CEO line. Nor does any run put such a line
into the reply of a CEO line (a heading ceo_line counts too) it wasn't in before the run. In the file, a line whose move would put one there
stays: an agent's `>>` of a HANDLED line with an indented line under it, after a CEO line, keeps its HANDLED line
until the CEO line or the indented line leaves (keep_apart). In the archive, a blank line goes above a moved one that
would land in a reply, under a CEO line or the heading's copy, it wasn't in in the file: with --closed, one under a
NEEDS-CEO-NOW line the run keeps, below a moved HANDLED line with `(CEO` as its writer field (to_archive). One whose
line above in its own reply the archive already held (as after a stopped run) lands in that reply still.

Other agents write the file while this runs. So it reads the file, appends to the archive first (`a` mode only, less
the copies the archive already holds under the same heading, as after a stopped run), writes the new file to a temporary file,
reads the file again and, only if it's byte-identical to the first read, swaps the two in one atomic step (macOS
renamex_np, Linux renameat2), retrying up to TRIES times. It opens neither file with 'w'. If the swapped-out
file isn't the one it compared, a writer got in between: it swaps that file back and tries again. An append that
opened the file before the swap and wrote after it lands in the old file: after GRACE seconds the old file is read
once more and any new line is appended to the new one. Last, every moved line must be in the archive; one that isn't
(the archive was rewritten meanwhile) is appended to it again. Exits 0 when done or when nothing moves, 1 when nothing
was removed (a code fence, or the file kept changing), 2 on a usage error.
"""

import argparse
import ctypes
import os
import re
import stat
import sys
import tempfile
import time
from collections import Counter, namedtuple
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import capacity_scan as scan  # noqa: E402
from kb_lint import KB, fence_hold  # noqa: E402
from kb_sweep import read, sync  # noqa: E402

sys.path.append(str(Path(__file__).resolve().parent / "hooks"))  # last: no hook module shadows the ones above
from cq_write import CONTINUES, ceo_line  # noqa: E402

TRIES = 5
GRACE = 0.2  # seconds: a shell `>>` opens and writes within this
RESUME_LIMIT = 1.5  # KB, the RESUME POINT's size (engineering README, "No per-step rows")
ARCHIVE_TITLE = "# ceo-questions, archive: search it, don't load it\n"  # kb_sweep.py's title for a new archive
HEADING = re.compile(r"#{1,2} ")
ORDER = re.compile(r"\bORDER\s+([^\s,;:()]+)", re.IGNORECASE)
LEAD = r"(?:- )?(?:\*\*)?"  # a list item or bold, as hand-written lines have it
HANDLED = re.compile(LEAD + r"HANDLED\b")
CEO = re.compile(LEAD + r"CEO\b")
PAUSE = re.compile(LEAD + r"PAUSE\b")
REPORT = re.compile(LEAD + r"REPORT\s+(\S+)")
RESUME = re.compile(LEAD + r"RESUME POINT\b(?:\s+(/[^\s,;:()]+))?")
ID = r"(?:D-\d{8}-[\w-]+)?/\d+(?:\.[\w-]+)*"
ACTED = re.compile(rf"\bACTED:\s*({ID}(?:\s*,\s*(?:and\s+)?{ID})*)")
NAMED = re.compile(r"(?<![\w/-])(?:D-\d{8}-[\w-]+)?/\d+")  # an order a line names: D-20260111-x/1, or /1 of /1.WS1
STAMP = re.compile(r"(?:(20\d\d-\d\d-\d\d)[T ])?(\d\d):(\d\d)(?::(\d\d))?(?:\.\d+)?Z")
HOLD = ("needs", "ceo", "pause")  # kinds that stay even in a closed section
KEPT = {"needs": "naming NEEDS-CEO-NOW", "ceo": "the CEO's", "pause": "PAUSE",
        "report": "REPORT not marked ACTED", "resume": "latest RESUME POINT (or one it can't date)",
        "other": "of other kinds (ANSWER, COORDINATION, FYI, ...)",
        "another": "HANDLED naming another order first (they move with that order's run)",
        "together": "of a CEO line's reply, kept whole (the line and the indented or numbered lines under it move together)",
        "apart": "that would put an indented, numbered or ( line into a CEO line's reply it wasn't in",
        "trim": "LANES or DEPLOY DONE kept (the latest DUTY line, an open TOKEN claim, or one it can't date)"}
LANES = re.compile(LEAD + r"(?:LANES\s+(\w+)|DEPLOY DONE)\b")  # the product file's lines the trim moves
TOKEN = re.compile(r"LANES\s+TOKEN\s+\S+\s+(\S+)\s+(CLAIMED|RELEASED)\s+by\s+(\S+)")  # its claim, kind and claimer
TRIM_AFTER = 48 * 3600  # seconds: older LANES and DEPLOY DONE lines leave the product file
POINTER = r'under\s+["`]?(?:#+\s*)?ORDER\s+{}(?![\w/-])'  # `full text under "## ORDER D-20260110-x/3"`
Plan = namedtuple("Plan", "lines moves blocks kept big orders")  # moves: {index: why}; blocks: [(heading index, [index])]


def kind(line: str) -> str:
    if HANDLED.match(line):
        return "handled"
    if CEO.match(line):
        return "ceo"
    if "NEEDS-CEO-NOW" in line:
        return "needs"
    for name, pattern in (("pause", PAUSE), ("report", REPORT), ("resume", RESUME)):
        if pattern.match(line):
            return name
    return "other" if line.strip() else "blank"


def order_of(heading: str) -> str:
    found = ORDER.search(heading)
    return found.group(1).rstrip(".") if found else heading


def stamp(line: str):
    """The line's first date and time, sortable, or None: a first time without a date can't be ordered."""
    found = STAMP.search(line)
    return found and found.group(1) and (found.group(1), found.group(2), found.group(3), found.group(4) or "00")


def lane(line: str, own: str):
    """A RESUME POINT's lane: the /34.WS1 right after its words, or None for the order's own."""
    found = RESUME.match(line).group(1)
    return None if found == own else found


def acted(report: str, line: str) -> bool:
    """Whether `line` marks the REPORT with this id ACTED."""
    ids = [i for found in ACTED.finditer(line) for i in re.findall(ID, found.group(1))]
    return any(i == report or (i.startswith("/") and report.endswith(i)) for i in ids)


def first_named(lines: list, sections: list, h: int, i: int):
    """The first order line i, under heading h, names, or None. A line names an order by its id (D-20260111-x/1), or by
    the id's end from the slash (/1, as in /1.WS1): its own heading's directive's order when the file has that
    heading, else the order whose heading is the last one before the line ending so."""
    keys = {key for start, _, key in sections if ORDER.search(lines[start])}
    own = order_of(lines[h])
    mine = own.rsplit("/", 1)[0] if ORDER.search(lines[h]) and not own.startswith("/") else None  # its directive
    for token in NAMED.findall(lines[i]):
        return (token if not token.startswith("/") else mine + token if mine and mine + token in keys else
                next((key for start, _, key in reversed(sections) if start < i and key.endswith(token)
                      and ORDER.search(lines[start])), None))
    return None


def strays(lines: list, sections: list, scope: list) -> dict:
    """HANDLED lines under a heading out of scope whose first named order (first_named) is in scope, by the heading of
    that order's section they go under: {heading index: [line index]}. That section is the order's last before the
    line, or else its first. The first named order decides, even when the line names its own heading's order later:
    that order's own run keeps it."""
    wanted, out = {key for _, _, key in scope}, {}
    for h, stop, own in sections:
        if own in wanted:
            continue  # it moves with its own heading
        for i in range(h + 1, stop):
            if kind(lines[i]) != "handled":
                continue
            order = first_named(lines, sections, h, i)
            order = order if order in wanted and order != own else None  # the first decides
            if order:
                starts = [start for start, _, key in sections if key == order]
                out.setdefault(max((s for s in starts if s < i), default=starts[0]), []).append(i)
    return out


def together(lines: list, end: int) -> list:
    """[[index, ...]] for each line ceo_line counts as the CEO's with the indented, numbered or `(` lines right under
    it, or under one of them (CONTINUES, as cq_write.under_ceo reads them), where there is one: the capacity scan
    reads them as one reply."""
    units, unit = [], None
    for i in range(end):
        if unit is not None and lines[i].strip() and CONTINUES.match(lines[i]):
            unit.append(i)
        else:
            unit = [i] if ceo_line(lines[i]) else None
            units += [unit] if unit else []
    return [unit for unit in units if len(unit) > 1]


def keep_together(lines: list, end: int, moves: dict, kept: Counter) -> None:
    """Take out of moves each reply together finds that moves only in part: it all stays."""
    for unit in together(lines, end):
        if any(i in moves for i in unit) and not all(i in moves for i in unit):
            for i in unit:
                if moves.pop(i, None):
                    kept[KEPT["together"]] += 1


def heads(lines: list, end: int) -> dict:
    """{index: the index of its CEO line} for each line together finds in a reply, but the CEO line itself."""
    return {i: unit[0] for unit in together(lines, end) for i in unit[1:]}


def strangers(lines: list, order: list, under: dict) -> list:
    """The lines of order (indices, read one under another, as the scan reads a file) that would join a reply together's
    way under a CEO line other than the one they stood under in the file (under, from heads), or under none: [index], in
    order. The walk goes on below each as if a blank line stood above it."""
    found, head = [], None
    for i in order:
        if head is not None and lines[i].strip() and CONTINUES.match(lines[i]):
            if under.get(i) == head:
                continue
            found.append(i)
        head = i if ceo_line(lines[i]) else None
    return found


def keep_apart(lines: list, end: int, moves: dict, kept: Counter, under: dict) -> bool:
    """Keep the moved line right above the first line the file left by the moves has in a CEO line's reply it wasn't in
    (strangers): True if one was kept. That line moves: keep_together has run, so a reply moves whole
    or stays whole, and a line right under one that stays joins what it joined before."""
    found = strangers(lines, [i for i in range(end) if i not in moves], under)
    if not found or moves.pop(found[0] - 1, None) is None:
        return False
    kept[KEPT["apart"]] += 1
    return True


def settle(lines: list, end: int, moves: dict, kept: Counter) -> None:
    """keep_together, then keep_apart and keep_together again until neither keeps a line. Both only take lines out of
    moves, so it ends, and no line moves that didn't before."""
    under = heads(lines, end)
    keep_together(lines, end, moves, kept)
    while keep_apart(lines, end, moves, kept, under):
        keep_together(lines, end, moves, kept)


def plan(text: str, orders=(), closed=(), whole=False) -> Plan:
    """What would move and why; whole (--all): a closed order's sections move with every line. Reads only."""
    lines = text.split("\n")
    end = len(lines) - 1 if text.endswith("\n") else len(lines)  # the "" after the last newline isn't a line
    starts = [i for i in range(end) if HEADING.match(lines[i])]
    sections = [(h, stop, order_of(lines[h])) for h, stop in zip(starts, starts[1:] + [end])]
    scope = [s for s in sections if not orders or s[2] in orders or s[2] in closed]
    body = {}  # each order's lines in scope, in file order
    for h, stop, key in scope:
        body.setdefault(key, []).extend(range(h + 1, stop))
    moves, kept, big = {}, Counter(), []
    keys, wanted = {k for start, _, k in sections if ORDER.search(lines[start])}, {k for _, _, k in scope}

    def another(i, h, key):
        first = kind(lines[i]) == "handled" and first_named(lines, sections, h, i)
        return first in keys and first != key and first not in wanted

    for h, stop, key in scope:
        own = "/" + key.rsplit("/", 1)[-1]
        if key in closed:  # a HANDLED line naming first another order outside the run waits for it;
            # with --all, CEO and PAUSE lines still stay: the CEO moves its own
            held = [i for i in range(h + 1, stop) if kind(lines[i]) in ("ceo", "pause")
                    or (not whole and (kind(lines[i]) in HOLD or another(i, h, key)))]
            moves.update({i: "closed" for i in range(h if not held else h + 1, stop) if i not in held})
            kept.update(KEPT["another" if another(i, h, key) else kind(lines[i])] for i in held)
            continue
        for i in range(h + 1, stop):
            line, what, later = lines[i], kind(lines[i]), [j for j in body[key] if j > i]
            if another(i, h, key):
                kept[KEPT["another"]] += 1  # it moves with that order's own run (strays)
            elif what == "handled":
                moves[i] = "HANDLED"
            elif what == "report" and any(acted(REPORT.match(line).group(1).rstrip(".,;:)"), lines[j]) for j in later):
                moves[i] = "REPORT marked ACTED"
            elif what == "resume" and stamp(line) and any(
                    RESUME.match(lines[j]) and lane(lines[j], own) == lane(line, own) and (stamp(lines[j]) or ()) > stamp(line)
                    for j in later):
                moves[i] = "superseded RESUME POINT"
            elif what != "blank":
                kept[KEPT[what]] += 1
                if RESUME.match(line) and len(line.encode("utf-8", "surrogateescape")) > RESUME_LIMIT * KB:
                    big.append(i)
    found = strays(lines, sections, scope)
    moves.update({i: "HANDLED, under another heading" for stray in found.values() for i in stray})
    settle(lines, end, moves, kept)
    blocks = [(h, sorted([i for i in range(h + 1, stop) if i in moves and lines[i].strip()]
                         + [i for i in found.get(h, []) if i in moves]))
              for h, stop, _ in scope]
    return Plan(lines, moves, [b for b in blocks if b[1]], kept, big,
                {key for h, _, key in sections if ORDER.search(lines[h])})  # --order and --closed name only these


def trim_plan(text: str, now: float) -> Plan:
    """The product file's trim (--trim): each LANES or DEPLOY DONE line under a heading whose first date
    and time is over TRIM_AFTER old moves, but the latest LANES DUTY line and each TOKEN claim no later TOKEN line of
    the same token and claimer releases. A line whose first time has no date stays. Reads only."""
    lines = text.split("\n")
    end = len(lines) - 1 if text.endswith("\n") else len(lines)
    starts = [i for i in range(end) if HEADING.match(lines[i])]
    sections = [(h, stop) for h, stop in zip(starts, starts[1:] + [end])]
    cutoff = tuple(time.strftime("%Y-%m-%d %H %M %S", time.gmtime(now - TRIM_AFTER)).split(" "))
    duty = [i for i in range(end) if LANES.match(lines[i]) and LANES.match(lines[i]).group(1) == "DUTY"]
    latest = max(duty, key=lambda i: (stamp(lines[i]) or ("",), i), default=None)
    claims, unreleased = {}, set()
    for i in range(end):
        token = LANES.match(lines[i]) and TOKEN.search(lines[i])
        if token and token.group(2) == "CLAIMED":
            claims.setdefault((token.group(1), token.group(3)), []).append(i)
            unreleased.add(i)
        elif token:
            unreleased -= set(claims.pop((token.group(1), token.group(3)), []))
    moves, kept = {}, Counter()
    for h, stop in sections:
        for i in range(h + 1, stop):
            if not LANES.match(lines[i]) or (stamp(lines[i]) and stamp(lines[i]) >= cutoff):
                continue
            if i == latest or i in unreleased or not stamp(lines[i]):
                kept[KEPT["trim"]] += 1
            else:
                moves[i] = "LANES or DEPLOY DONE over 48 h old"
    settle(lines, end, moves, kept)
    blocks = [(h, sorted(i for i in range(h + 1, stop) if i in moves)) for h, stop in sections]
    return Plan(lines, moves, [b for b in blocks if b[1]], kept, [], set())


def drain_holds(path: Path, text: str, closed) -> list:
    """Why --closed <id> --all may not drain the order's sections: each line in them that the scan reads
    as an ask nobody answered (capacity_scan.unanswered, whatever its age), each whose word is followed by another
    order's ref (capacity_scan.misfiled: it goes under that order's heading first; a COORD or ANSWER sits in the
    recipient's or asker's section on purpose), and each line
    elsewhere that points into them (`full text under "## ORDER <id>"`): ["line N: why"]; and an order whose directive's
    status log has no CLOSED row for it (capacity_scan.order_log's closed set, read from the repo the file's
    workspaces/ is in): ["why"]. Reads only."""
    lines = text.split("\n")
    end = len(lines) - 1 if text.endswith("\n") else len(lines)
    starts = [i for i in range(end) if HEADING.match(lines[i])]
    inside = {i + 1 for h, stop in zip(starts, starts[1:] + [end]) if order_of(lines[h]) in closed
              for i in range(h, stop)}
    layout = path.parent.name == "content" and len(path.parents) > 2  # workspaces/<product>/content/: its other files
    product = path.parents[1].name if layout else ""
    pages = [(product, path)] + ([page for page in scan.question_pages(path.parents[2])
                                  if page[0] == product and page[1] != path] if layout else [])
    why = [(ask[4], f"an unanswered {ask[1]}{' ' + ask[2] if ask[2] else ''} of {ask[3]}")
           for ask in scan.unanswered(pages, float("inf")) if ask[6] == scan.page_place(path) and ask[4] in inside]
    why += [(line[2], f"a {line[3]} line of {line[4]}, another order's: put it under that order's heading first")
            for line in scan.misfiled([(product, path)]) if line[2] in inside]
    sections = [(h, stop, order_of(lines[h])) for h, stop in zip(starts, starts[1:] + [end])]
    keys = {key for h, _, key in sections if ORDER.search(lines[h])}
    for h, stop, key in sections:
        for i in range(h + 1, stop) if key in closed else ():
            first = kind(lines[i]) == "handled" and first_named(lines, sections, h, i)
            if first in keys and first != key:  # it moves with that order's own run
                why.append((i + 1, f"a HANDLED line naming ORDER {first} first: it moves with that order's own run"))
    for key in closed:  # the CEO closed it: a CLOSED row in its status log, a DONE report alone isn't
        directive, n, rows = *key.rsplit("/", 1), set()
        if layout:
            scan.order_log(path.parents[3] / "knowledge" / "board" / "directives", directive, rows)
        if n not in rows:
            why.append((0, f"ORDER {key} has no CLOSED row in knowledge/board/directives/{directive}.md's status log"
                           f"{'' if layout else ' (not found)'}"))
        pointer = re.compile(POINTER.format(re.escape(key)))
        why += [(i + 1, f"it points to the text of ORDER {key} (`under ... ORDER {key}`)")
                for i in range(end) if i + 1 not in inside and pointer.search(lines[i])]
    return [f"line {n}: {reason}" if n else reason for n, reason in sorted(why)]


def to_archive(p: Plan, archive: str) -> str:
    """What to append: each block under a copy of its heading, less the copies the archive holds under it already, with a
    blank line above each moved line that would join there, right under a CEO line or the heading's copy, a reply it
    wasn't in in the file (strangers).

    Counted, not a set: two identical lines moved need two copies, and a rerun after a stop adds none."""
    have, heading = {}, None
    for line in archive.split("\n"):
        heading = line if HEADING.match(line) else heading
        have.setdefault(heading, Counter())[line] += 1
    under, out = heads(p.lines, len(p.lines)), []
    for h, moved in p.blocks:
        held, new = have.setdefault(p.lines[h], Counter()), []
        for i in moved:
            if held[p.lines[i]]:
                held[p.lines[i]] -= 1
            else:
                new.append(i)
        apart = set(strangers(p.lines, [h, *new], under))
        out += ["", p.lines[h]] if new else []
        for i in new:
            out += ["", p.lines[i]] if i in apart else [p.lines[i]]
    text = "\n".join(out) + "\n" if out else ""  # its first "\n" ends a last line written without one
    return ARCHIVE_TITLE + text if text and not archive else text


def append(path: Path, text: str) -> None:
    with open(path, "ab") as f:
        f.write(text.encode("utf-8", "surrogateescape"))
        f.flush()
        sync(f)


def exchange(a: Path, b: Path) -> None:
    """Swap two paths in one atomic step: each name then holds the other's file."""
    libc = ctypes.CDLL(None, use_errno=True)
    swap = getattr(libc, "renamex_np", None)
    done = (swap(os.fsencode(a), os.fsencode(b), 2) if swap  # RENAME_SWAP
            else libc.renameat2(-100, os.fsencode(a), -100, os.fsencode(b), 2))  # AT_FDCWD, RENAME_EXCHANGE
    if done != 0:
        err = ctypes.get_errno()
        raise OSError(err, os.strerror(err), str(b))


def rescue(path: Path, archive: Path, text: str, base: str) -> list:
    """Append to `path` each line of `text` that `base` didn't have and that neither file has now: a writer's."""
    old, have = set(base.split("\n")), set(read(path).split("\n")) | set(read(archive).split("\n"))
    gone = list(dict.fromkeys(line for line in text.split("\n") if line.strip() and line not in old | have))
    if gone:
        append(path, "\n" + "\n".join(gone) + "\n")
        print(f"Kept {len(gone)} lines a writer added during the swap: appended at the end of {path.name}, under its last "
              "heading; move any that belong to another order under that order's heading.")
    return gone


def swap_in(path: Path, archive: Path, before: str, after: str) -> bool:
    """Put `after` where `before` is, never over anything else. False, the file as a writer left it, if it changed."""
    fd, name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.cq_archive-")
    tmp = Path(name)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(after.encode("utf-8", "surrogateescape"))
            f.flush()
            sync(f)
        os.chmod(tmp, stat.S_IMODE(path.stat().st_mode))
        if read(path) != before:
            return False
        exchange(tmp, path)
        if read(tmp) != before:  # a writer got in between the read and the swap: give it its file back
            exchange(tmp, path)
            rescue(path, archive, read(tmp), after)  # and one that wrote to ours in that moment keeps its lines
            return False
        time.sleep(GRACE)
        rescue(path, archive, read(tmp), before)  # an append that opened the old file before the swap
        return True
    finally:
        tmp.unlink(missing_ok=True)


def place(text: str, order: str, line: str):
    """The text with `line` after the last line of the last section headed ORDER `order`, before its blank lines and
    the next heading, and that heading's index. A heading's order is `order`, or else the one heading id that is its
    end from the slash or whose end it is (`/5` and D-20260111-x/5); else the list of such ids, empty or more than one."""
    lines = text.split("\n")
    end = len(lines) - 1 if text.endswith("\n") else len(lines)
    starts = [i for i in range(end) if HEADING.match(lines[i])]
    ordered = [h for h in starts if ORDER.search(lines[h])]  # a heading with no ORDER id is no order's
    keys = {order_of(lines[h]) for h in ordered}
    named = [order] if order in keys else sorted(
        k for k in keys if order.startswith("/") and k.endswith(order) or k.startswith("/") and order.endswith(k))
    if len(named) != 1:
        return named
    own = [h for h in ordered if order_of(lines[h]) == named[0]]
    at = next((s for s in starts if s > own[-1]), end)
    while at > own[-1] + 1 and not lines[at - 1].strip():
        at -= 1
    return "\n".join(lines[:at] + [line] + lines[at:]), own[-1]


def add(path: Path, order: str, line: str, dry_run=False) -> int:
    """Put one line under its order's heading (--add), never over another writer's lines: swap_in, as run's move.
    After the grace period it reads the file back: a line a whole-file write dropped (an Edit from a read taken before
    the swap) is added once more, and if that one is dropped too it exits 1. A line that left the file
    because the archive beside it gained a copy meanwhile was moved there on purpose (another cq_archive run): it isn't
    added again."""
    lost = False
    archive = path.with_name(f"{path.stem}-archive.md")
    for _ in range(TRIES):
        kept = read(archive).split("\n").count(line) if archive.exists() else 0
        before = read(path)
        held = fence_hold(before)
        if held:
            print(f"Nothing added: {held.split(',')[0]}. Add the line by Edit.")
            return 1
        found = place(before, order, line)
        if isinstance(found, list) and found:
            print(f"ORDER {order} may be any of {', '.join(found)} in {path.name}: nothing added. Give one with --order.")
            return 2
        if not found:
            print(f"No section of {path.name} is headed ORDER {order}, or by an id ending so: nothing added. Add the "
                  "heading with the line under it: one `>>` of both at the end, the heading first, or Edit.")
            return 2
        after, h = found
        heading = before.split("\n")[h][:100]
        if dry_run:
            print(f"Would add the line under {heading}. Dry run: nothing changed.")
            return 0
        try:
            if not swap_in(path, path, before, after):
                time.sleep(GRACE)
                continue
        except OSError as e:
            print(f"Couldn't swap the files ({e}): nothing added.")
            return 1
        if read(path).split("\n").count(line) > before.split("\n").count(line):
            print(f"Added the line under {heading}.")
            return 0
        if archive.exists() and read(archive).split("\n").count(line) > kept:
            print(f"Added the line under {heading}; another run then moved it to {archive.name} on purpose: not added "
                  "again.")
            return 0
        if lost:
            print(f"The line went under {heading} twice, and twice a writer's whole-file write dropped it: it isn't in "
                  f"{path.name}. Add it by Edit.")
            return 1
        lost = True
        print(f"A writer's whole-file write dropped the line just after it was added under {heading}: adding it again.")
    print(f"{path.name} changed while this ran, {TRIES} times: nothing added. Run it again.")
    return 1


def size(text: str) -> str:
    return f"{len(text.encode('utf-8', 'surrogateescape')) / KB:.1f} KB"


def count(text: str) -> int:
    return text.count("\n") + (not text.endswith("\n") and bool(text))


def describe(p: Plan, path: Path, archive: Path, before: str, after: str, archived: str, add: str) -> list:
    out = []
    for h, moved in p.blocks:
        out.append(f"  {p.lines[h][:100]}")
        out += [f"    line {i + 1}, {p.moves[i]}, {size(p.lines[i])}: {p.lines[i][:90]}" for i in moved if p.moves[i] != "closed"]
        closed = sum(p.moves[i] == "closed" for i in moved)
        out += [f"    {closed} lines of a closed section"] if closed else []
    if p.kept:
        apart = p.kept.get(KEPT["apart"], 0)  # a move by hand would put that line into the CEO's reply too
        out.append("Kept: " + ", ".join(f"{n} {why}" for why, n in p.kept.items()) + "." + (
            f" The {apart} kept so no line joins a CEO line's reply stay where they are, also by hand, until the CEO "
            "line above them, or the line under them, leaves." if apart else "") + (
            " Move the rest by hand, while they stand in the file: >> the CEO line with its lines, in their order, as "
            "one heredoc, to the archive by its absolute path, then Edit them out of the file from the last line up, "
            "or the CEO line with its numbered or indented lines in one Edit." if sum(p.kept.values()) > apart else ""))
    out += [f"Over about {RESUME_LIMIT} KB: the RESUME POINT at line {i + 1} ({size(p.lines[i])}); its detail goes to the "
            "design's header or the order's notes file." for i in p.big]
    out.append(f"{path.name}: {size(before)}, {count(before)} lines -> {size(after)}, {count(after)} lines; "
               f"{archive.name}: {size(archived)}, {count(archived)} lines -> {size(archived + add)}, {count(archived + add)} lines.")
    return out


def run(path: Path, orders=(), closed=(), dry_run=False, whole=False, trim=False) -> int:
    archive = path.with_name(f"{path.stem}-archive.md")
    for _ in range(TRIES):
        before = read(path)
        held = fence_hold(before)
        if held:
            print(f"Nothing moved: {held}.")
            return 1
        p = trim_plan(before, time.time()) if trim else plan(before, orders, closed, whole)
        unknown = [o for o in (*orders, *closed) if o not in p.orders]
        if unknown:
            print(f"No section of {path.name} is headed ORDER {', '.join(unknown)}: nothing moved.")
            return 2
        holds = drain_holds(path, before, closed) if whole else []
        if holds:
            print("\n".join([f"Nothing moved: ORDER {', '.join(closed)} holds lines that can't leave yet; its sections "
                             "stay until each is answered, moved under its own order's heading, or no longer pointed "
                             "to:", *(f"  {why}" for why in holds)]))
            return 1
        archived = read(archive) if archive.exists() else ""
        add = to_archive(p, archived)
        after = "\n".join(line for i, line in enumerate(p.lines) if i not in p.moves)
        report = describe(p, path, archive, before, after, archived, add)
        moving = sum(len(moved) for _, moved in p.blocks)
        if not p.moves:
            print("\n".join([f"Nothing to move in {path.name}.", *report]))
            return 0
        if dry_run:
            print("\n".join([f"Would move {moving} lines of {path.name} to {archive.name}:", *report, "Dry run: nothing changed."]))
            return 0
        if add:
            append(archive, add)
        if to_archive(p, read(archive)):
            print(f"{archive.name} doesn't hold the lines to move (rewritten meanwhile?): nothing removed. Run again.")
            return 1
        try:
            if not swap_in(path, archive, before, after):
                time.sleep(GRACE)
                continue
        except OSError as e:
            print(f"Couldn't swap the files ({e}): nothing removed; a rerun doesn't add the archive's copies twice.")
            return 1
        again = to_archive(p, read(archive))
        if again:
            append(archive, again)
            print(f"{archive.name} lost moved lines while this ran (rewritten?): appended them again.")
        print("\n".join([f"Moved {moving} lines of {path.name} to {archive.name}, word for word:", *report]))
        return 0
    print(f"{path.name} changed while this ran, {TRIES} times: nothing removed. The archive may hold copies of lines "
          "still in the file; a rerun doesn't add them twice.")
    return 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Move a ceo-questions.md's handled lines, word for word, to its archive.")
    parser.add_argument("file", type=Path, help="<main checkout>/workspaces/<product>/content/ceo-questions.md by "
                                                "absolute path, and the main checkout's script too, no cd")
    parser.add_argument("--order", action="append", default=[],
                        help="only this order's sections, the id after ORDER in the heading; repeat for more (default: all)")
    parser.add_argument("--closed", action="append", default=[],
                        help="this order is done: move its whole sections but their CEO, NEEDS-CEO-NOW and PAUSE lines")
    parser.add_argument("--dry-run", action="store_true", help="print what would move and the sizes before and after")
    parser.add_argument("--add", metavar="LINE", help="instead, put this one line under the heading of the one --order, "
                                                       "after its last line")
    parser.add_argument("--all", action="store_true", help="with --closed: every line of its sections but CEO and "
                                                           "PAUSE lines, once the order has its CLOSED row and none "
                                                           "is unanswered, another order's or pointed to")
    parser.add_argument("--trim", action="store_true", help="instead, the product file's LANES and DEPLOY DONE lines "
                                                            "over 48 h old, but the latest DUTY and open TOKEN claims")
    args = parser.parse_args(argv)
    if args.file.name != "ceo-questions.md" or not args.file.is_file():
        parser.error(f"{args.file}: not a ceo-questions.md file")
    if args.add is not None and (len(args.order) != 1 or args.closed or args.add.splitlines() != [args.add]
                                 or not args.add.strip()):  # no break str.splitlines() reads (\r, \v, \f, \x85, ...)
        parser.error("--add takes one line, with exactly one --order and no --closed")
    if args.all and (not args.closed or args.add is not None or args.trim):
        parser.error("--all goes with --closed only")
    if args.trim and (args.order or args.closed or args.add is not None or args.file.parent.name != "content"):
        parser.error("--trim takes a product's content/ceo-questions.md, with no --order, --closed or --add")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="backslashreplace")  # a line can hold any bytes; a print mustn't stop a move
    if args.add is not None:
        return add(args.file.resolve(), args.order[0], args.add, args.dry_run)
    return run(args.file.resolve(), args.order, args.closed, args.dry_run, args.all, args.trim)


if __name__ == "__main__":
    sys.exit(main())
