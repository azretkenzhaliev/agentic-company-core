#!/usr/bin/env python3
"""Write each agent's "## Core" section from its owner's KB pages.

The core pages are the one copy: the CTO writes knowledge/engineering/cores/, the CMO knowledge/marketing/cores/. The
agent body carries a generated copy, so it loads at every spawn: `skills:` preload is reported broken under `--agent`,
and a SubagentStart hook would be one more step in .claude/settings.json (cores/README.md, both folders).

A section is "## Core", then each page's body (front matter stripped, headings two levels down, so the section ends at
the agent file's next "## " heading), shared part first. It sits before the body's first "## " heading, after the
opening paragraphs. Each stays within its owner's cap, 10,000 characters from the heading to the blank line ending it.

A regenerate rewrites agent files, so it is a system change: the owner changes the page, then the platform engineer
runs this on a sys/ branch and the CEO lands it through the gate (ceo.md, "System changes"). Never run it on main,
and never edit a section by hand.

Usage: python3 scripts/build_cores.py           rewrite the sections from the pages
       python3 scripts/build_cores.py --check   exit 1, naming each agent file whose section differs
scripts/tests/test_build_cores.py fails the same way until a gated regenerate lands.
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CAP = 10_000
HEADING = "## Core"
ENG = "knowledge/engineering/cores"
MKT = "knowledge/marketing/cores"
CORES = {  # agent file: its core pages, in load order (cores/README.md, "Load plan" and "For the platform engineer")
    ".claude/agents/engineering/staff-engineer.md": [f"{ENG}/shared.md", f"{ENG}/staff-engineer.md"],
    ".claude/agents/engineering/senior-engineer.md": [f"{ENG}/shared.md", f"{ENG}/senior-engineer.md"],
    ".claude/agents/engineering/code-reviewer.md": [f"{ENG}/shared.md", f"{ENG}/code-reviewer.md"],
    ".claude/agents/engineering/design-reviewer.md": [f"{ENG}/shared.md", f"{ENG}/design-reviewer.md"],
    ".claude/agents/engineering/cto.md": [f"{ENG}/cto.md"],
    ".claude/agents/marketing/cmo.md": [f"{MKT}/shared.md", f"{MKT}/cmo.md"],
    ".claude/agents/marketing/content-producer.md": [f"{MKT}/shared.md", f"{MKT}/content-producer.md"],
    ".claude/agents/marketing/content-reviewer.md": [f"{MKT}/shared.md", f"{MKT}/content-reviewer.md"],
    ".claude/agents/marketing/performance-analyst.md": [f"{MKT}/shared.md", f"{MKT}/performance-analyst.md"],
    ".claude/agents/marketing/reel-analyst.md": [f"{MKT}/shared.md", f"{MKT}/reel-analyst.md"],
    ".claude/agents/marketing/trend-researcher.md": [f"{MKT}/shared.md", f"{MKT}/trend-researcher.md"],
}
FRONT_MATTER = re.compile(r"---\n.*?\n---\n", re.S)


def page_body(text):
    """A core page without its front matter, headings two levels down: "# X" becomes "### X"."""
    found = FRONT_MATTER.match(text)
    body = text[found.end():] if found else text
    if "```" in body or "~~~" in body:
        raise ValueError("a code block in a core page: headings inside it would be changed")
    return re.sub(r"^(#{1,4}) ", r"##\1 ", body.strip(), flags=re.M)


def section(pages):
    """The "## Core" section for these page texts, with the blank line that ends it: the span the cap counts."""
    text = f"{HEADING}\n\n" + "\n\n".join(page_body(page) for page in pages) + "\n\n"
    if len(text) > CAP:
        raise ValueError(f"{len(text)} characters, over the {CAP:,} cap: the owner shortens the page")
    return text


def with_core(agent, core):
    """The agent file's text with its Core section set to `core`; front matter and the rest unchanged."""
    found = FRONT_MATTER.match(agent)
    if not found:
        raise ValueError("no front matter")
    head, body = agent[:found.end()], agent[found.end():]
    start = re.search(rf"^{re.escape(HEADING)}\n", body, re.M)
    if start:
        end = re.compile(r"^## ", re.M).search(body, start.end())
        if not end:
            raise ValueError("no heading after the Core section")
        return head + body[:start.start()] + core + body[end.start():]
    first = re.search(r"^## ", body, re.M)
    if not first:
        raise ValueError("no '## ' heading to put the Core section before")
    return head + body[:first.start()] + core + body[first.start():]


def build(root=ROOT):
    """{agent file path: (current text, text with its Core section from the pages)}."""
    out = {}
    for agent, pages in CORES.items():
        path = root / agent
        current = path.read_text(encoding="utf-8")
        try:
            out[path] = (current, with_core(current, section([(root / p).read_text(encoding="utf-8") for p in pages])))
        except ValueError as e:
            raise ValueError(f"{agent}: {e}") from None
    return out


def main(argv, root=ROOT):
    check = argv[1:] == ["--check"]
    if argv[1:] not in ([], ["--check"]):
        print(__doc__.split("\n\n")[-1], file=sys.stderr)
        return 2
    stale = []
    for path, (current, expected) in build(root).items():
        if current != expected:
            stale.append(path.relative_to(root).as_posix())
            if not check:
                path.write_text(expected, encoding="utf-8")
    for name in stale:
        print(f"{'differs' if check else 'written'}: {name}")
    return 1 if check and stale else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
