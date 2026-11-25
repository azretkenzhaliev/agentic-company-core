#!/usr/bin/env python3
"""What each agent loads at spawn, in characters, against a cap.

Per agent in .claude/agents/: its file's body (its system prompt), the repo's CLAUDE.md (every custom subagent loads
it), and the body of each skill its `skills:` field preloads. Characters, not bytes: text in many
alphabets has more bytes than characters. Tokens are an estimate at 2.65 bytes a token. It changes
nothing. Exits 1 if any agent's total is over --cap.

Not counted: the harness's own prompt and tool listings, user-level CLAUDE.md files and auto memory (each machine has
its own; --also adds a file to every agent), hook context and `memory:`. A skill in `skills:` counts even for an agent
run as the main session (the CEO), where Claude Code skips the preload, so the check errs high.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from kb_lint import parse_front_matter  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
BYTES_PER_TOKEN = 2.65


def split_file(path: Path) -> tuple:
    """(front matter fields, body as Claude Code loads it: after the front matter, stripped)."""
    lines = path.read_text(encoding="utf-8").splitlines()
    parsed = parse_front_matter(lines)
    if parsed is None:
        return {}, "\n".join(lines).strip()
    fields, _, end = parsed
    return fields, "\n".join(lines[end + 1:]).strip()


def skill_names(fields: dict) -> list:
    value = fields.get("skills") or []
    return [value] if isinstance(value, str) else list(value)


def measure(root: Path, also=()) -> tuple:
    """([(agent, body, CLAUDE.md, skills, total characters, est. tokens)], [notes])."""
    claude_md = root / "CLAUDE.md"
    shared = claude_md.read_text(encoding="utf-8") if claude_md.exists() else ""
    shared += "".join(Path(p).read_text(encoding="utf-8") for p in also)
    rows, notes = [], []
    for path in sorted((root / ".claude" / "agents").rglob("*.md")):
        fields, body = split_file(path)
        name = str(fields.get("name") or path.stem)
        skills = ""
        for skill in skill_names(fields):
            skill_file = root / ".claude" / "skills" / skill / "SKILL.md"
            if skill_file.exists():
                skills += split_file(skill_file)[1]
            else:
                notes.append(f"{name}: skill {skill} not found, not counted")
        text = body + shared + skills
        rows.append((name, len(body), len(shared), len(skills), len(text),
                     round(len(text.encode("utf-8")) / BYTES_PER_TOKEN)))
    return rows, notes


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--cap", type=int, required=True, help="most characters an agent may load at spawn")
    parser.add_argument("--agent", action="append", help="only this agent (repeatable)")
    parser.add_argument("--also", action="append", default=[], help="another file every agent loads (repeatable)")
    parser.add_argument("--root", type=Path, default=ROOT, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    rows, notes = measure(args.root, args.also)
    if args.agent:
        missing = set(args.agent) - {r[0] for r in rows}
        if missing:
            print(f"no such agent: {', '.join(sorted(missing))}", file=sys.stderr)
            return 2
        rows = [r for r in rows if r[0] in args.agent]
    over = [r for r in rows if r[4] > args.cap]
    print(f"{'agent':20} {'body':>7} {'CLAUDE.md':>9} {'skills':>7} {'total':>7} {'~tokens':>8}")
    for name, body, shared, skills, total, tokens in sorted(rows, key=lambda r: -r[4]):
        print(f"{name:20} {body:7} {shared:9} {skills:7} {total:7} {tokens:8}")
    for note in notes:
        print(note)
    for name, *_, total, _tokens in over:
        print(f"OVER {name}: {total} characters, cap {args.cap}")
    return 1 if over else 0


if __name__ == "__main__":
    sys.exit(main())
