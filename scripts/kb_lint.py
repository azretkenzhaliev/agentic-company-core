#!/usr/bin/env python3
"""Lint the knowledge base (Python standard library only).

Errors: missing or invalid front matter, broken relative links and
`related:` paths, duplicate IDs, secrets, pages over their size
limit, and a directive's row whose Event starts "System check" but which
the system-check skill's grep misses (SYSTEM_CHECK_GREP).
Warnings: pages whose `updated` date is 90 or more days old,
orphan pages that no other page links to (checked when the root has an
INDEX.md), lines of oversize-pages.txt that no longer apply, a product's
questions or Board-steps file over its limit (WORK_LOGS), and "sweep due".
`_templates/` is skipped.

Size limits (SIZE_LIMITS) keep what an agent loads small: about 25 KB for
a current-state page, more for what isn't one; pages with `status:
archived` have no limit. The sizes are defaults. PAGE_LIMITS gives one
page its own: board-preferences.md, 80 KB. It stays lean by grouping and
summarizing its rules, whose full words move to the archive, never by a
higher limit; what to do, numbers and scope stay on it. FIT_PAGES, the
desk's Q&A and Asks pages, name scripts/kb_sweep.py when over, which moves
their oldest entries until they fit. oversize-pages.txt, in the KB root,
names pages let pass over their limit: the CEO removes each line as its
page is slimmed.

WORK_LOGS are the files agents reload at each task boundary. They sit
outside the KB, in gitignored workspaces/<product>/content/, so a fresh
worktree has none. Over its limit, one
gets a warning that names what to archive, and a ceo-questions.md's names
scripts/cq_archive.py; it can't fail the linter.
Run from a git worktree, a link into workspaces/ that isn't there is
looked up in the main checkout, and is broken only if it's missing there
too.

"sweep due" warnings are the trigger for scripts/kb_sweep.py, a
ceo-questions.md's for scripts/cq_archive.py and
a board-steps.md's for a move by hand, and a
page of any owner but ceo and cto, which kb_sweep.py can't move, for a move by hand
(HAND_MOVE), in its over-limit error too; and
/report reads them: a page within 10% of its limit, an owner whose last sweep
(last-sweep.txt, in the KB root) is 14 days old or more, and a "Past, in short" summary older than the cold text it
stands for. The linter only reads; transcripts stay out of it, since
marketing agents run it too.

Dates are UTC dates, as the logs write them: today, and a file's date where a page has no `updated`.

Usage: python3 scripts/kb_lint.py [--root knowledge] [--today YYYY-MM-DD]
Exits 1 if there are errors, else 0.
"""

import argparse
import re
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import unquote

sys.path.insert(0, str(Path(__file__).resolve().parent))

from kb_secrets import find_secrets  # noqa: E402

REQUIRED_KEYS = ("title", "owner", "status", "updated", "related")
OWNERS = {"board", "ceo", "cto", "analyst", "staff-engineer", "cmo", "content-producer", "performance-analyst", "ux-expert"}
STATUSES = {"draft", "active", "superseded", "archived"}
STALE_DAYS = 90
SKIP_DIRS = {"_templates"}
IGNORED = "workspaces"  # gitignored whole (.gitignore), so a worktree has none of it
KB = 1024
STATE_PAGE = ("a current-state page", 25)
SIZE_LIMITS = {  # folder under the KB root: (what its pages are, limit in KB); a page anywhere else is a STATE_PAGE
    "engineering/designs/": ("a design", 60),  # staff-engineer.md's 30 KB above the review log, then the logs
    "engineering/roadmaps/": ("a roadmap", 60),
    "engineering/runbooks/": ("a runbook", 60),
    "engineering/standards/": ("a standards page", 30),
    "board/directives/": ("a directive", 100),  # a log of orders, not a state page
    "board/attachments/": ("an attachment", 100),  # the Board's raw material
    "board/answers/": ("the Board's answers, a week", 100),  # its words never move
    "research/": ("a research note", 100),  # raw notes
}
PAGE_LIMITS = {  # one page under the KB root: (what it is, limit in KB, what its size findings add); before SIZE_LIMITS
    # never raised for room
    "company/board-preferences.md": ("the Board's preferences", 80,
                                     "group overlapping rules and summarize them, never a higher limit; "
                                     "what to do, numbers and scope stay (ceo.md, \"Keep board-preferences.md\")"),
}
# Past its limit, scripts/kb_sweep.py moves a page's oldest whole entries, at any age, until it fits
FIT_PAGES = ("company/board-desk/qa.md", "company/board-desk/asks.md")
FIT_MOVE = ("python3 scripts/kb_sweep.py --apply --owner ceo moves its oldest entries, word for word, until it fits; "
            "an open ask never moves: past the limit with only open asks, close or shorten them")
OVERSIZE_LIST = "oversize-pages.txt"
WORK_LOGS = {  # file under workspaces/<product>/content/: (limit in KB, what leaves it)
    "ceo-questions.md": (30, "answered lines and closed orders"),
    "board-steps.md": (20, "done, dropped, waived and obsolete steps"),
}
WORK_LOG_OWNER = "cto"  # the CTO holds these (cto.md, "Hold the plan and small state"); they have no front matter
SWEEP_BAND = 0.9  # a page at this share of its limit, or more, is due
SWEEP_DAYS = 14
SWEEP_OWNERS = ("ceo", "cto")  # who owns the logs scripts/kb_sweep.py moves
SWEEP_STAMPS = "last-sweep.txt"
# A page of any other owner (the marketing roles, whose hooks refuse kb_sweep.py): its size lines say this instead
HAND_MOVE = ("move history by hand, word for word, to a sibling page with status: archived (kb_sweep.py moves only "
             f"{' and '.join(SWEEP_OWNERS)} pages)")

FILE_ID = re.compile(r"^(RM|DD|ADR|DEC)-\d{3,}")
SA_HEADING = re.compile(r"^#+\s+(SA-\d{3,})\b")
LINK = re.compile(r"!?\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
INLINE_CODE = re.compile(r"`[^`]*`")
SCHEME = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")
ISO_DATE = re.compile(r"(?<!\d)20\d{2}-\d{2}-\d{2}(?!\d)")  # no \b: a date is also the start of 2026-01-05T08:00Z
SUMMARY_HEADING = re.compile(r"^#{1,6} Past, in short\b", re.IGNORECASE)
COLD_NAME = re.compile(r"(-archive(-\d+)?|-history)\.md$|^archive-.*\.md$")  # cto.md's names for pages only searched
FENCE = re.compile(r" {0,3}(?:`{3,}(?=[^`]*$)|~{3,})")  # at most 3 spaces in; a backtick after the run makes it inline code
SYSTEM_CHECK_GREP = re.compile(r"^[|] [0-9-]{10} [|] ceo [|] System check [0-9]{4}-")  # the skill's grep, as written there
SYSTEM_CHECK_ROW = re.compile(r"^\s*\|[^|]*\|[^|]*\|\s*system check\b", re.IGNORECASE)  # a row's Event starts with it
SYSTEM_CHECK_DIR = "board/directives/"  # the folder the grep reads


@dataclass
class Finding:
    path: str
    line: int
    level: str
    message: str


def parse_front_matter(lines: list[str]):
    """Return (fields, {key: line number}, end index) or None if absent."""
    if not lines or lines[0].strip() != "---":
        return None
    fields: dict[str, object] = {}
    key_lines: dict[str, int] = {}
    current_list = None
    for i in range(1, len(lines)):
        line = lines[i]
        if line.strip() == "---":
            return fields, key_lines, i
        item = re.match(r"^\s+-\s+(.*)$", line)
        if item and current_list is not None:
            current_list.append(item.group(1).strip().strip("'\""))
            continue
        pair = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", line)
        if not pair:
            continue
        key, value = pair.group(1), pair.group(2).strip()
        key_lines[key] = i + 1
        current_list = None
        if value.startswith("[") and value.endswith("]"):
            fields[key] = [v.strip().strip("'\"") for v in value[1:-1].split(",") if v.strip()]
        elif value == "":
            fields[key] = current_list = []
        else:
            fields[key] = value.strip("'\"")
    return None


def resolve_target(page: Path, target: str) -> Path:
    """The file a relative link points at; a directory link means its README.md."""
    target = unquote(target.split("#", 1)[0].split("?", 1)[0])
    if not target:
        return page
    path = (page.parent / target).resolve()
    return path / "README.md" if path.is_dir() else path


def link_target_exists(page: Path, target: str, ignored=None) -> bool:
    """ignored, from a worktree: (its workspaces/, the main checkout's); a link under the first is looked up in the second."""
    target = unquote(target.split("#", 1)[0].split("?", 1)[0])
    if not target:
        return True
    path = page.parent / target
    if path.exists():
        return True
    if ignored is None:
        return False
    here, there = ignored
    try:
        return (there / path.resolve().relative_to(here)).exists()
    except ValueError:  # not under workspaces/
        return False


def main_checkout(base: Path) -> Path:
    """base, or, for a git worktree, the main checkout its .git file points to (as scripts/capacity_scan.py's)."""
    try:
        gitdir = base / (base / ".git").read_text().split("gitdir:", 1)[1].strip()
        return (gitdir / (gitdir / "commondir").read_text().strip()).resolve().parent
    except (OSError, IndexError):  # .git is a folder (the main checkout), or isn't there
        return base


def is_checkable(target: str) -> bool:
    return not (SCHEME.match(target) or target.startswith("#") or target.startswith("/") or target.startswith("<"))


def lint_page(page: Path, rel: str, today: date, linked: set[Path], ignored=None) -> list[Finding]:
    text = page.read_text(encoding="utf-8")
    lines = text.splitlines()
    out: list[Finding] = []

    def err(line, msg):
        out.append(Finding(rel, line, "error", msg))

    parsed = parse_front_matter(lines)
    body_start = 0
    if parsed is None:
        err(1, "missing front matter (a '---' block with title, owner, status, updated, related)")
    else:
        fields, key_lines, end = parsed
        body_start = end + 1
        for key in REQUIRED_KEYS:
            if key not in fields:
                err(1, f"front matter is missing '{key}'")
        owner = fields.get("owner")
        if owner is not None and owner not in OWNERS:
            err(key_lines["owner"], f"invalid owner '{owner}' (expected one of {', '.join(sorted(OWNERS))})")
        status = fields.get("status")
        if status is not None and status not in STATUSES:
            err(key_lines["status"], f"invalid status '{status}' (expected one of {', '.join(sorted(STATUSES))})")
        updated = fields.get("updated")
        if updated is not None:
            try:
                age = (today - date.fromisoformat(str(updated))).days
            except ValueError:
                err(key_lines["updated"], f"invalid updated date '{updated}' (expected YYYY-MM-DD)")
            else:
                if age >= STALE_DAYS:
                    out.append(Finding(rel, key_lines["updated"], "warning", f"not updated for {age} days; re-check or archive"))
        related = fields.get("related")
        if isinstance(related, list):
            for target in related:
                if not is_checkable(target):
                    continue
                if link_target_exists(page, target, ignored):
                    linked.add(resolve_target(page, target))
                else:
                    err(key_lines["related"], f"broken related path -> {target}")
        elif related is not None:
            err(key_lines["related"], "related must be a list, e.g. [a.md, b.md] or []")

    in_fence = False
    for i in range(body_start, len(lines)):
        line = lines[i]
        if line.lstrip().startswith(("```", "~~~")):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        for target in LINK.findall(INLINE_CODE.sub("", line)):
            if not is_checkable(target):
                continue
            if link_target_exists(page, target, ignored):
                linked.add(resolve_target(page, target))
            else:
                err(i + 1, f"broken link -> {target}")

    for line_no, kind in find_secrets(text):
        err(line_no, f"possible {kind}; remove it and write where the secret lives instead")
    return out


def size_limit(path_in_kb: str) -> tuple:
    """What a page is and its limit in KB, from its path under the KB root."""
    if path_in_kb in PAGE_LIMITS:
        return PAGE_LIMITS[path_in_kb][:2]
    for folder, limit in SIZE_LIMITS.items():
        if path_in_kb.startswith(folder):
            return limit
    return STATE_PAGE


def read_oversize_list(root: Path) -> dict:
    """{path under the KB root: line number} from oversize-pages.txt; no file means no pages."""
    path = root / OVERSIZE_LIST
    if not path.exists():
        return {}
    named = {}
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        name = line.split("#", 1)[0].strip()
        if name:
            named[name] = line_no
    return named


def never_raises(trigger, *args) -> list:
    """A sweep trigger can't stop the linter: on bad input it says nothing, and every other check still runs."""
    try:
        return trigger(*args)
    except (OSError, ValueError):
        return []


def near_limit(size: int, limit: int) -> bool:
    """Within 10% of the limit (limit in KB), and not over it."""
    return SWEEP_BAND * limit * KB <= size <= limit * KB


def sweep_due(size: int, limit: int, owner, then: str = "python3 scripts/kb_sweep.py shows what would move") -> str:
    return f"sweep due: {size / KB:.1f} KB, within 10% of its {limit} KB limit (owner: {owner}); {then}"


def cq_archive(page: Path, main: Path) -> str:
    """A ceo-questions.md's tool: kb_sweep.py moves only `# ` sections with a CLOSED line, not `## ORDER` ones. The
    main checkout's script and the page by absolute path, the form scripts/hooks/cq_write.py allows from any cwd."""
    return (f"python3 {main / 'scripts' / 'cq_archive.py'} {page} --dry-run shows what would move; without --dry-run "
            "it moves the handled lines, and with --closed <order id> a finished order's sections")


def fence_hold(text: str):
    """Why no section of a ceo-questions.md page can move, or None: a `# ` in a code fence looks like a heading."""
    fence = next((i for i, line in enumerate(text.split("\n"), 1) if FENCE.match(line)), None)
    return fence and f"line {fence} is a code fence, so no section here moves: move sections by hand or remove the fence"


def fence_note(page: Path) -> list:
    """What a ceo-questions.md page adds to its sweep line; a list, for never_raises."""
    held = fence_hold(page.read_text(encoding="utf-8", errors="replace"))
    return [held] if held else []


def is_cold(page: Path) -> bool:
    """A page that is only searched: archived, or named as an archive. A research note is neither hot nor cold."""
    parsed = parse_front_matter(page.read_text(encoding="utf-8", errors="replace").splitlines())
    if parsed is not None and parsed[0].get("status") == "archived":
        return True
    return COLD_NAME.search(page.name) is not None and "research" not in page.parts


def section_end(lines: list, start: int) -> int:
    """The line after the section whose heading is lines[start]: the next heading of its level or higher."""
    level = len(lines[start]) - len(lines[start].lstrip("#"))
    higher = re.compile(rf"#{{1,{level}}} ")
    return next((i for i in range(start + 1, len(lines)) if higher.match(lines[i])), len(lines))


def utc_date(timestamp) -> date:
    """The UTC date of an epoch time: the date the logs write (capacity_scan.utc_today's rule)."""
    return datetime.fromtimestamp(timestamp, timezone.utc).date()


def cold_since(page: Path) -> date:
    """When text last reached a cold page: its `updated`, or the file's date outside the KB, where there's none."""
    parsed = parse_front_matter(page.read_text(encoding="utf-8", errors="replace").splitlines())
    try:
        return date.fromisoformat(str(parsed[0]["updated"]))
    except (TypeError, KeyError, ValueError):
        return utc_date(page.stat().st_mtime)


def linked_pages(page: Path, base: Path, text: str) -> list:
    """The .md files inside the repo that this text links to. A link to anything else is never opened."""
    targets = [resolve_target(page, t) for t in LINK.findall(INLINE_CODE.sub("", text)) if is_checkable(t)]
    return [t for t in targets if t.suffix == ".md" and t.is_relative_to(base) and t.is_file()]


def lint_summary(page: Path, base: Path, rel: str, owner) -> list:
    """A "Past, in short" older than the cold text it stands for: judgement, so its owner refreshes it.

    Its date is the one on its heading, or else the newest in the section, so the heading should carry the date it was
    written. Its cold pages are those it links to, and <page>-archive*.md beside it.
    """
    lines = page.read_text(encoding="utf-8", errors="replace").split("\n")
    start = next((i for i, line in enumerate(lines) if SUMMARY_HEADING.match(line)), None)
    if start is None:
        return []
    section = "\n".join(lines[start:section_end(lines, start)])
    siblings = [p for p in sorted(page.parent.glob(f"{page.stem}-archive*.md")) if p.resolve().is_relative_to(base)]
    cold = [p for p in [*linked_pages(page, base, section), *siblings] if is_cold(p)]
    if not cold:
        return []
    written = max(ISO_DATE.findall(lines[start]) or ISO_DATE.findall(section), default=None)
    newest, name = max((cold_since(p), p.name) for p in cold)
    if written is not None and written >= newest.isoformat():
        return []
    return [Finding(rel, start + 1, "warning",
                    f'sweep due: "Past, in short" ({written or "undated"}) is older than {name} ({newest}); '
                    f"its owner ({owner}) refreshes it, with the date in its heading")]


def read_sweep_stamps(root: Path):
    """{owner: date of its last sweep} from last-sweep.txt, or None without the file (a bare KB, as in tests)."""
    path = root / SWEEP_STAMPS
    if not path.exists():
        return None
    stamps = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        words = line.split("#", 1)[0].split()
        if len(words) == 2:
            try:
                stamps[words[0]] = date.fromisoformat(words[1])
            except ValueError:
                pass  # not a date: that owner counts as never swept
    return stamps


def lint_sweep_stamps(root: Path, today: date) -> list:
    stamps = read_sweep_stamps(root)
    if stamps is None:
        return []
    out = []
    for owner in SWEEP_OWNERS:
        last = stamps.get(owner)
        if last is None or (today - last).days >= SWEEP_DAYS:
            since = "none recorded" if last is None else f"the last was {last}, {(today - last).days} days ago"
            out.append(Finding(f"{root.name}/{SWEEP_STAMPS}", 1, "warning",
                               f"sweep due: {owner}: {since}; python3 scripts/kb_sweep.py shows what would move"))
    return out


def lint_size(page: Path, path_in_kb: str, rel: str, oversize: dict) -> list:
    parsed = parse_front_matter(page.read_text(encoding="utf-8").splitlines())
    archived = parsed is not None and parsed[0].get("status") == "archived"
    kind, limit = size_limit(path_in_kb)
    stays = [PAGE_LIMITS[path_in_kb][2]] if path_in_kb in PAGE_LIMITS else []
    size = page.stat().st_size
    over = not archived and size > limit * KB
    owner = parsed[0].get("owner") if parsed else None
    by_hand = [HAND_MOVE] if owner and owner not in SWEEP_OWNERS else []  # kb_sweep.py can't move its history
    if over and path_in_kb not in oversize:
        move = (by_hand[0] if by_hand else FIT_MOVE if path_in_kb in FIT_PAGES
                else "move history to a sibling page with status: archived")
        return [Finding(rel, 1, "error", "; ".join([f"{size / KB:.1f} KB, over the {limit} KB limit for {kind}; {move}",
                                                    *stays]))]
    if not over and path_in_kb in oversize:
        return [Finding(rel, 1, "warning", f"within its limit now; remove it from {OVERSIZE_LIST}")]
    if not archived and near_limit(size, limit):
        return [Finding(rel, 1, "warning", "; ".join([sweep_due(size, limit, owner, *by_hand), *stays]))]
    return []


def lint_system_check_rows(text: str, rel: str) -> list:
    """A row whose Event starts "System check" but which the system-check skill's grep misses, so a check would
    compare with an older row."""
    out = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        if SYSTEM_CHECK_ROW.match(line) and not SYSTEM_CHECK_GREP.match(line):
            out.append(Finding(rel, line_no, "error",
                               "the system-check skill's grep misses this System check row; write it "
                               '"| <YYYY-MM-DD> | ceo | System check <YYYY-MM-DDTHH:MM[:SS]Z>: ..." '
                               "(.claude/skills/system-check/SKILL.md, step 1), or, for a note, "
                               'start its Event with something other than "System check"'))
    return out


def largest_sections(text: str, count: int = 3) -> str:
    """The biggest sections of a page, by heading, so a warning says where to start."""
    sections = [s for s in re.split(r"(?m)^(?=#{1,3} )", text) if s.startswith("#")]
    sections.sort(key=lambda s: len(s.encode("utf-8")), reverse=True)
    return "; ".join(f"{s.splitlines()[0][:60]} ({len(s.encode('utf-8')) / KB:.1f} KB)" for s in sections[:count])


def lint_work_logs(base: Path, main: Path) -> list:
    out = []
    for name, (limit, what) in WORK_LOGS.items():
        for page in sorted(base.glob(f"workspaces/*/content/{name}")):
            size = page.stat().st_size
            rel = page.relative_to(base).as_posix()
            move = f"move {what}, verbatim, to {page.stem}-archive.md"
            tool = [cq_archive(page, main)] if name == "ceo-questions.md" else []  # board-steps.md has none: moved by hand
            if size > limit * KB:
                biggest = largest_sections(page.read_text(encoding="utf-8", errors="replace"))
                over = f"{size / KB:.1f} KB, over about {limit} KB; {move} (largest sections: {biggest or 'none'})"
                out.append(Finding(rel, 1, "warning", "; ".join([over, *tool])))
            elif near_limit(size, limit):
                if tool:
                    due = "; ".join([sweep_due(size, limit, WORK_LOG_OWNER, *tool), *never_raises(fence_note, page)])
                else:
                    due = sweep_due(size, limit, WORK_LOG_OWNER, move)
                out.append(Finding(rel, 1, "warning", due))
            out.extend(never_raises(lint_summary, page, base, page.relative_to(base).as_posix(), WORK_LOG_OWNER))
    return out


def lint(root: Path, today: date) -> list[Finding]:
    root = root.resolve()
    base = root.parent
    main = main_checkout(base)
    ignored = (base / IGNORED, main / IGNORED) if main != base else None
    findings: list[Finding] = []
    oversize = read_oversize_list(root)
    file_ids: dict[str, str] = {}
    sa_ids: dict[str, str] = {}
    inbound: dict[Path, set[Path]] = {}
    pages = [p for p in sorted(root.rglob("*.md")) if not SKIP_DIRS.intersection(p.relative_to(root).parts)]
    for page in pages:
        rel = page.relative_to(base).as_posix()
        linked: set[Path] = set()
        findings.extend(lint_page(page, rel, today, linked, ignored))
        findings.extend(lint_size(page, page.relative_to(root).as_posix(), rel, oversize))
        parsed = parse_front_matter(page.read_text(encoding="utf-8").splitlines())
        findings.extend(never_raises(lint_summary, page, base, rel, parsed[0].get("owner") if parsed else None))
        if page.relative_to(root).as_posix().startswith(SYSTEM_CHECK_DIR):
            findings.extend(lint_system_check_rows(page.read_text(encoding="utf-8"), rel))
        for target in linked - {page.resolve()}:
            inbound.setdefault(target, set()).add(page)

        match = FILE_ID.match(page.name)
        if match:
            ident = match.group(0)
            if ident in file_ids:
                findings.append(Finding(rel, 1, "error", f"duplicate id {ident} (also {file_ids[ident]})"))
            else:
                file_ids[ident] = rel
        for line_no, line in enumerate(page.read_text(encoding="utf-8").splitlines(), start=1):
            heading = SA_HEADING.match(line)
            if heading:
                ident = heading.group(1)
                where = f"{rel}:{line_no}"
                if ident in sa_ids:
                    findings.append(Finding(rel, line_no, "error", f"duplicate id {ident} (also {sa_ids[ident]})"))
                else:
                    sa_ids[ident] = where

    for name in oversize.keys() - {page.relative_to(root).as_posix() for page in pages}:
        findings.append(Finding(f"{root.name}/{OVERSIZE_LIST}", oversize[name], "warning", f"no page {name}; remove the line"))

    index = root / "INDEX.md"
    if index.exists():
        for page in pages:
            if page != index and not inbound.get(page.resolve()):
                rel = page.relative_to(base).as_posix()
                findings.append(Finding(rel, 1, "warning", "orphan: no other page links here; link it from its folder README or INDEX.md"))
    findings.extend(lint_work_logs(base, main))
    findings.extend(never_raises(lint_sweep_stamps, root, today))
    return findings


def main(argv=None) -> int:
    default_root = Path(__file__).resolve().parents[1] / "knowledge"
    parser = argparse.ArgumentParser(description="Lint the knowledge base.")
    parser.add_argument("--root", type=Path, default=default_root, help="knowledge base folder (default: ./knowledge)")
    parser.add_argument("--today", type=date.fromisoformat, default=utc_date(time.time()), help="date for staleness checks (default: today in UTC)")
    args = parser.parse_args(argv)

    findings = lint(args.root, args.today)
    for f in findings:
        print(f"{f.path}:{f.line}: {f.level}: {f.message}")
    errors = sum(f.level == "error" for f in findings)
    warnings = len(findings) - errors
    pages = sum(1 for p in args.root.resolve().rglob("*.md") if not SKIP_DIRS.intersection(p.relative_to(args.root.resolve()).parts))
    print(f"kb_lint: {pages} pages, {errors} errors, {warnings} warnings")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
