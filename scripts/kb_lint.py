#!/usr/bin/env python3
"""Lint the knowledge base (Python standard library only).

Errors: missing or invalid front matter, broken relative links and
`related:` paths, duplicate IDs, and secrets. Warnings: pages whose
`updated` date is 90 or more days old, and orphan pages that no other
page links to (checked when the root has an INDEX.md). `_templates/` is
skipped.

Usage: python3 scripts/kb_lint.py [--root knowledge] [--today YYYY-MM-DD]
Exits 1 if there are errors, else 0.
"""

import argparse
import re
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from urllib.parse import unquote

sys.path.insert(0, str(Path(__file__).resolve().parent))

from kb_secrets import find_secrets  # noqa: E402

REQUIRED_KEYS = ("title", "owner", "status", "updated", "related")
OWNERS = {"board", "ceo", "cto", "analyst", "staff-engineer"}
STATUSES = {"draft", "active", "superseded", "archived"}
STALE_DAYS = 90
SKIP_DIRS = {"_templates"}

FILE_ID = re.compile(r"^(RM|DD|ADR|DEC)-\d{3,}")
SA_HEADING = re.compile(r"^#+\s+(SA-\d{3,})\b")
LINK = re.compile(r"!?\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
INLINE_CODE = re.compile(r"`[^`]*`")
SCHEME = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")


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


def link_target_exists(page: Path, target: str) -> bool:
    target = unquote(target.split("#", 1)[0].split("?", 1)[0])
    if not target:
        return True
    return (page.parent / target).exists()


def is_checkable(target: str) -> bool:
    return not (SCHEME.match(target) or target.startswith("#") or target.startswith("/") or target.startswith("<"))


def lint_page(page: Path, rel: str, today: date, linked: set[Path]) -> list[Finding]:
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
                if link_target_exists(page, target):
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
            if link_target_exists(page, target):
                linked.add(resolve_target(page, target))
            else:
                err(i + 1, f"broken link -> {target}")

    for line_no, kind in find_secrets(text):
        err(line_no, f"possible {kind}; remove it and write where the secret lives instead")
    return out


def lint(root: Path, today: date) -> list[Finding]:
    root = root.resolve()
    base = root.parent
    findings: list[Finding] = []
    file_ids: dict[str, str] = {}
    sa_ids: dict[str, str] = {}
    inbound: dict[Path, set[Path]] = {}
    pages = [p for p in sorted(root.rglob("*.md")) if not SKIP_DIRS.intersection(p.relative_to(root).parts)]
    for page in pages:
        rel = page.relative_to(base).as_posix()
        linked: set[Path] = set()
        findings.extend(lint_page(page, rel, today, linked))
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

    index = root / "INDEX.md"
    if index.exists():
        for page in pages:
            if page != index and not inbound.get(page.resolve()):
                rel = page.relative_to(base).as_posix()
                findings.append(Finding(rel, 1, "warning", "orphan: no other page links here; link it from its folder README or INDEX.md"))
    return findings


def main(argv=None) -> int:
    default_root = Path(__file__).resolve().parents[1] / "knowledge"
    parser = argparse.ArgumentParser(description="Lint the knowledge base.")
    parser.add_argument("--root", type=Path, default=default_root, help="knowledge base folder (default: ./knowledge)")
    parser.add_argument("--today", type=date.fromisoformat, default=date.today(), help="date for staleness checks")
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
