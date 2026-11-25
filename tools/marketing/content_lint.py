#!/usr/bin/env python3
"""Lint marketing content pages (one piece each) before review.

    python3 tools/marketing/content_lint.py <page.md | folder> ...
    python3 tools/marketing/content_lint.py --clean <page.md> ...   # AI-tell score beside the cleaned caption

Checks the format in knowledge/_templates/content-piece.md and the content rules that text can
show: required fields, caption length (characters, not bytes; a Short's in
bytes, with its title's bounds), hashtags,
placeholders, where each asset came from, vetted fonts, sources and dates,
and words that need a source or a person's judgment.
Outside footage must come from sources/ with its MANIFEST.json entry, and a
compiled reel's record must list it. It also scores the caption for AI tells that don't depend on the language;
those are warnings only.
Errors fail (exit 1); warnings are for the content-reviewer to judge.
A folder's `status: archived` pages are skipped, each named on its own line; a page named directly is always checked.
A page with any required field or a `## Post` is a live piece, never skipped, and `status: archived` on it is an error.
The standard library only; front matter is parsed by scripts/kb_lint.py.
"""

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))

from company_config import integration  # noqa: E402
from kb_lint import Finding, parse_front_matter  # noqa: E402

REQUIRED = ("brand", "week", "format", "pillar", "ai_generated", "ai_reason", "raw_material", "piece_status", "languages")
FORMATS = {"reel", "carousel", "post", "story", "short"}
STATUSES = {"draft", "in-review", "ready-for-board"}
PROVENANCE = {"own-render", "own-footage", "ai-generated", "board-supplied", "outside"}
SOURCES = "workspaces/marketing/sources/"  # outside footage, each file with a MANIFEST.json entry (footage/fetch.py)
FACTS_ONLY = "facts-only"  # a piece of facts with no take of the founder's
DRAFTED = "drafted"  # the founder's take drafted by an agent in his voice, for the Board to correct
FOUNDER_PAGES = "founder/"  # his own pages (content-qa B)
VETTED_FONTS = {"montserrat", "golos text"}
ARABIC_FONT = "scheherazade new"  # Arabic script only
GENERIC_FONTS = {"sans-serif", "serif", "monospace", "system-ui", "inherit", "initial", "unset"}
CAPTION_MAX = 2200  # Instagram's
HASHTAGS_MAX = 5
TITLE_MAX, DESCRIPTION_MAX = 100, 5000  # YouTube's, as in publish/post.py, which refuses them when hashing and staging
TITLE_LINE = "- Title: "

WEEK = re.compile(r"^\d{4}-W\d{2}$")
DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
HASHTAG = re.compile(r"#\w+")
FONT_FAMILY = re.compile(r"font-family\s*:\s*([^;}]+)", re.I)
FONT_SHORTHAND = re.compile(r"(?<![-\w])font\s*:\s*([^;}]+)", re.I)
FONT_SIZE = re.compile(r"(?:\d+(?:\.\d+)?(?:px|pt|em|rem|%|vh|vw)|(?:xx?-)?(?:small|large)|medium)(?:/\S+)?\s+(.+)$", re.I)
INBOX = "workspaces/marketing/inbox/"
CLAIMS = [r"№\s?1", r"#1\b", r"\bbest\b", r"guarantee"]  # and company.json's "lint"."claims", in the brand's languages

# AI tells. Ideas adapted from Jakeschincariol/instagram-agent-skill and sergebulaev/instagram-skills (MIT).
# The cut-offs are ours, not a platform's. The em-dash count runs on Latin-script lines only: other languages may
# use the dash as ordinary punctuation.
EMOJI = ("[\U0001F300-\U0001F3FA\U0001F400-\U0001FAFF\u2194-\u2199\u2300-\u23FF\u25AA-\u25FE\u2600-\u27BF"
         "\u2934\u2935\u2B05-\u2B55]")
# A flag is two regional indicators; a joiner followed by any visible symbol stays inside the emoji.
EMOJI_SEQ = re.compile(f"(?:[\U0001F1E6-\U0001F1FF]{{2}}|{EMOJI})(?:[\uFE0F\U0001F3FB-\U0001F3FF]|\u200D[^\\s\\w])*")
INVISIBLE = re.compile("[\u00AD\u180E\u200B-\u200F\u202A-\u202E\u2060-\u2064\u2066-\u2069\uFEFF]")
MARKDOWN = (("'**' or '__'", re.compile(r"(?<!\w)(\*\*|__)(?=\S)(.+?)(?<=\S)\1(?!\w)"), r"\2"),
            ("a '#' heading", re.compile(r"^#{1,6}[ \t]+", re.M), ""),
            ("a [text](link)", re.compile(r"\[([^\]\n]+)\]\((https?://[^)\s]+)\)"), r"\1 (\2)"),
            ("backticks", re.compile(r"`+"), ""))
URL = re.compile(r"https?://\S+")
LATIN = re.compile(r"[A-Za-z]")
LATIN_WORD = re.compile(r"[A-Za-z]+")
WORD = re.compile(r"[^\W\d_]+")
HASHTAG_RUN = re.compile(r"#\w+(?:\s+#\w+){2,}")
QUOTE_OPEN, QUOTE_CLOSE = "[\"'\u201C\u201E\u00AB]", "[\"'\u201D\u00BB]"
BAIT = [  # and company.json's "lint"."bait", in the brand's languages
    r"\blike\s+if\b", r"\b(?:hit|smash|drop|leave|give)\s+(?:a|the|that)?\s*like\b",
    r"\btag\s+(?:a|your|\d+)\s+(?:friend|buddy|person)",
    rf"\b(?:comment|type|write|drop)\s+{QUOTE_OPEN}[^\n]{{1,15}}?{QUOTE_CLOSE}",
    r"\b(?:share|send)\s+(?:this\s+)?(?:with|to)\s+\d+\s+(?:friends|people)",
]
TELL_WEIGHTS = {"invisible": 30, "markdown": 20, "em dash": 15, "emoji": 15, "hashtag wall": 10, "bait": 20}


def lint_words(root: Path) -> tuple:
    """(claims, bait): the patterns above and company.json's own, as regular expressions."""
    own = ((integration("marketing", root) or {}).get("lint")) or {}
    return tuple(re.compile("|".join([*words, *(own.get(name) or [])]), re.I)
                 for name, words in (("claims", CLAIMS), ("bait", BAIT)))


def sections(lines: list, start: int) -> dict:
    """{name: (line number of the heading, [body lines])} for each '## ' section."""
    out, name = {}, None
    for i in range(start, len(lines)):
        if lines[i].startswith("## "):
            name = lines[i][3:].strip()
            out[name] = (i + 1, [])
        elif name:
            out[name][1].append(lines[i])
    return out


def fenced_block(body: list) -> "str | None":
    fences = [i for i, line in enumerate(body) if line.strip().startswith("```")]
    if len(fences) < 2:
        return None
    return "\n".join(body[fences[0] + 1:fences[1]])


def font_stacks(css: str) -> list:
    """Each font-family list in the CSS, from `font-family:` and the `font:` shorthand."""
    stacks = list(FONT_FAMILY.findall(css))
    for value in FONT_SHORTHAND.findall(css):
        size = FONT_SIZE.search(value.strip())
        if size:
            stacks.append(size.group(1))
    return [[f.strip().strip("'\"") for f in stack.split(",") if f.strip()] for stack in stacks]


def font_problem(stack: list) -> "str | None":
    """A stack must start with a vetted font; generic families may only follow one.
    The Arabic font may lead only when a vetted font follows it, for any other script."""
    if stack and stack[0].lower() == ARABIC_FONT:
        if len(stack) < 2 or stack[1].lower() not in VETTED_FONTS:
            return "the Arabic font needs Montserrat or Golos Text right after it"
        stack = stack[1:]
    if not stack or stack[0].lower() not in VETTED_FONTS:
        return f"'{stack[0] if stack else ''}' comes first"
    others = [f for f in stack[1:] if f.lower() not in VETTED_FONTS | GENERIC_FONTS | {ARABIC_FONT}]
    return f"'{others[0]}' is in the stack" if others else None


def table_rows(body: list) -> list:
    rows = []
    for line in body:
        if not line.strip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if cells[0].lower() == "file" or set(cells[0]) <= set("-: "):
            continue
        rows.append(cells + [""] * (4 - len(cells)))
    return rows


def without_invisible(text: str) -> str:
    """Drop invisible characters, but keep the joiners inside emoji (👨‍💻)."""
    out, last = [], 0
    for m in EMOJI_SEQ.finditer(text):
        out += [INVISIBLE.sub("", text[last:m.start()]), m.group(0)]
        last = m.end()
    return "".join(out) + INVISIBLE.sub("", text[last:])


def ai_tells(text: str, root: Path = REPO) -> tuple:
    """(score 0-100, what was found, the cleaned text). Cleaning fixes only what is mechanical
    (invisible characters, Markdown); emoji, dashes, hashtags and bait need the producer's judgment."""
    found = []
    invisible = INVISIBLE.findall(EMOJI_SEQ.sub("", text))
    if invisible:
        codes = ", ".join(sorted({f"U+{ord(c):04X}" for c in invisible}))
        found.append(("invisible", f"{len(invisible)} invisible characters ({codes})"))
    marks = [name for name, rx, _ in MARKDOWN if rx.search(text)]
    if marks:
        found.append(("markdown", f"Markdown marks ({', '.join(marks)}) show as typed on Instagram"))
    english = []
    for line in (URL.sub("", line) for line in text.splitlines()):
        if LATIN.search(line) and not any(c.isalpha() and ord(c) >= 0x370 for c in line):  # no other script's letters
            english.append(line)
    dashes, words = sum(line.count("—") for line in english), sum(len(LATIN_WORD.findall(line)) for line in english)
    if dashes >= 2 and dashes * 50 > words:
        found.append(("em dash", f"{dashes} em dashes in {words} words (counted in Latin-script lines only)"))
    emoji = EMOJI_SEQ.findall(text)
    led = sum(bool(EMOJI_SEQ.match(line.strip())) for line in text.splitlines())
    if len(emoji) >= 5 and len(emoji) * 10 > len(WORD.findall(text)):
        found.append(("emoji", f"{len(emoji)} emoji in {len(WORD.findall(text))} words"))
    elif led >= 3:
        found.append(("emoji", f"{led} lines start with an emoji"))
    lines = [line for line in text.splitlines() if line.strip()]
    if any(HASHTAG_RUN.search(line) for line in lines[:-1]):
        found.append(("hashtag wall", "a hashtag wall before the last line; keep hashtags to one closing line"))
    bait = lint_words(root)[1].search(text)
    if bait:
        found.append(("bait", f"engagement bait ('{bait.group(0)}'): ask for a comment, save, send or follow, "
                              "not a vote, a like or a tag"))
    cleaned = without_invisible(text)
    for _, rx, repl in MARKDOWN:
        cleaned = rx.sub(repl, cleaned)
    return min(100, sum(TELL_WEIGHTS[k] for k, _ in found)), [m for _, m in found], cleaned


def outside_problem(file: str, repo_root: Path, expected_sha: "str | None" = None) -> "str | None":
    """Why an outside file isn't properly recorded, or None: it must sit in sources/ beside a MANIFEST.json
    entry with its SHA-256 (and match the compile record's, if given)."""
    clean = file.replace("\\", "/")
    if not clean.startswith(SOURCES) or ".." in clean.split("/"):
        return f"outside footage comes only from {SOURCES} (footage/fetch.py), with its MANIFEST.json entry"
    path = repo_root / file
    if not path.is_file():
        return None  # not on this machine: lint warns "not found" for pieces past draft
    sources = (repo_root / SOURCES).resolve()
    if sources not in path.resolve().parents:
        return f"{file} resolves outside {SOURCES} (a link)"
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    try:
        entries = json.loads((path.parent / "MANIFEST.json").read_text(encoding="utf-8")).get("files", [])
    except (OSError, json.JSONDecodeError, AttributeError):
        entries = []
    if not any(isinstance(e, dict) and e.get("sha256") == digest and e.get("file") == path.name for e in entries):
        return "no MANIFEST.json entry with this file's name and SHA-256 (changed or never fetched with footage/fetch.py)"
    if expected_sha and expected_sha != digest:
        return "the file changed after the reel was compiled"
    return None


def is_piece(fields: dict, parts: dict) -> bool:
    """A piece keeps its shape even with piece_status deleted; only a record with none of it can be archived."""
    return any(key in fields for key in REQUIRED) or "Post" in parts


def lint(path: Path, repo_root: Path = REPO) -> list:
    rel = str(path)
    lines = path.read_text(encoding="utf-8").splitlines()
    out = []

    def add(line, level, message):
        out.append(Finding(rel, line, level, message))

    parsed = parse_front_matter(lines)
    if parsed is None:
        add(1, "error", "no front matter (see knowledge/_templates/content-piece.md)")
        return out
    fields, key_lines, end = parsed
    at = lambda key: key_lines.get(key, 1)  # noqa: E731
    for key in REQUIRED:
        if not fields.get(key):
            add(1, "error", f"missing front matter field '{key}'")
    if fields.get("owner") != "content-producer":
        add(at("owner"), "error", "owner must be content-producer (one writer per piece)")
    if fields.get("format") and fields["format"] not in FORMATS:
        add(at("format"), "error", f"format must be one of {', '.join(sorted(FORMATS))}")
    if fields.get("piece_status") and fields["piece_status"] not in STATUSES:
        add(at("piece_status"), "error", f"piece_status must be one of {', '.join(sorted(STATUSES))}")
    if fields.get("ai_generated") and fields["ai_generated"] not in ("true", "false"):
        add(at("ai_generated"), "error", "ai_generated must be true or false")
    if fields.get("week") and not WEEK.match(str(fields["week"])):
        add(at("week"), "error", "week must look like 2026-W05")

    brand = str(fields.get("brand", ""))
    body_text = "\n".join(lines[end + 1:])
    parts = sections(lines, end + 1)
    if fields.get("status") == "archived" and is_piece(fields, parts):
        add(at("status"), "error", "a live piece can't be archived: set status back, or, for a dead piece, "
                                   "drop its piece fields and ## Post")

    # Caption and hashtags.
    caption = ""
    if "Caption" in parts:
        block = fenced_block(parts["Caption"][1])
        if block is None:
            add(parts["Caption"][0], "error", "## Caption needs one fenced block holding the caption exactly as posted")
        else:
            caption = block
            if fields.get("format") == "short":
                if len(caption.encode("utf-8")) > DESCRIPTION_MAX or "<" in caption or ">" in caption:
                    add(parts["Caption"][0], "error", f"a short's caption is its YouTube description: "
                                                      f"{DESCRIPTION_MAX} bytes of UTF-8 or fewer, with no < or >")
            elif len(caption) > CAPTION_MAX:
                add(parts["Caption"][0], "error", f"caption is {len(caption):,} characters; Instagram allows 2,200")
            score, tells, _ = ai_tells(caption, repo_root)
            if tells:
                add(parts["Caption"][0], "warning", f"AI tells, score {score}/100: {'; '.join(tells)}. The cleaned "
                                                    f"caption: python3 tools/marketing/content_lint.py --clean {rel}")
    elif fields.get("format") != "story":
        add(end + 1, "error", "## Caption is required (only stories have none)")
    tag_text = caption + "\n" + "\n".join(parts.get("Hashtags", (0, []))[1])
    tags = {t.lower() for t in HASHTAG.findall(tag_text)}
    if len(tags) > HASHTAGS_MAX:
        add(parts.get("Hashtags", (end + 1,))[0], "error",
            f"{len(tags)} hashtags; at most {HASHTAGS_MAX}, caption and ## Hashtags together")

    # A Short's title: publish/post.py's rules, so an edit after post_hashes fails here too.
    if "Post" in parts:
        titles = [line[len(TITLE_LINE):].strip() for line in parts["Post"][1] if line.startswith(TITLE_LINE)]
        title = titles[0] if titles else ""
        if len(titles) > 1:
            add(parts["Post"][0], "error", "the page needs at most one '- Title:' line")
        elif bool(title) != (fields.get("format") == "short"):
            add(parts["Post"][0], "error", "a short needs '- Title:', its YouTube title, and only a short has one")
        elif len(title) > TITLE_MAX or "<" in title or ">" in title or not title.isprintable():
            add(parts["Post"][0], "error", f"'- Title:' must be {TITLE_MAX} characters or fewer, "
                                           "with no < or > and no control characters")

    # The founder's voice: his own file, or a take drafted in his voice for the Board to correct.
    raw = str(fields.get("raw_material", ""))
    if raw.lower() == FACTS_ONLY and not brand.startswith(FOUNDER_PAGES) and not [
            s for s in parts.get("Sources", (0, []))[1] if s.strip().startswith("-")]:
        # Product brands: claims trace to a source. On the founder's pages sources are never a finding.
        add(at("raw_material"), "error", "raw_material is facts-only, so it needs at least one line in ## Sources")
    if raw.lower() == DRAFTED and not brand.startswith(FOUNDER_PAGES):
        add(at("raw_material"), "error", f"raw_material {DRAFTED} is only for the founder's pages; on a product brand "
                                         f"use {FACTS_ONLY} with ## Sources, his own file in {INBOX}, or placeholder")
    if raw and raw.lower() not in (FACTS_ONLY, DRAFTED, "placeholder"):
        if not raw.startswith(INBOX):
            add(at("raw_material"), "error", f"raw_material must be the founder's own file in {INBOX} (only he puts "
                                             f"files there), {DRAFTED} (his take drafted in his voice, for the Board "
                                             f"to correct), {FACTS_ONLY} (facts, no take of his), or placeholder")
        elif fields.get("piece_status") != "draft" and not (repo_root / raw).exists():
            add(at("raw_material"), "warning", f"raw_material {raw} not found")
    if raw.lower() == "placeholder":
        if "placeholder" not in body_text.lower():
            add(at("raw_material"), "error", "raw_material is placeholder, so the piece must say 'placeholder' where the take goes")
        if fields.get("piece_status") == "ready-for-board":
            add(at("piece_status"), "error", "a placeholder piece never goes to the Board for approval")

    # Assets: ours only, vetted fonts, AI flag.
    asset_rows = [row[:4] for row in table_rows(parts.get("Assets", (0, []))[1])]
    listed_outside = {f for f, prov, _a, _n in asset_rows if prov.lower() == "outside"}
    for file, provenance, _ai, _notes in asset_rows:
        line = parts["Assets"][0]
        if provenance.lower() not in PROVENANCE:
            add(line, "error", f"asset {file}: provenance '{provenance}' must be one of {', '.join(sorted(PROVENANCE))}; "
                               f"other people's media is outside, from {SOURCES} with its manifest (footage/fetch.py)")
        if provenance.lower() == "outside":
            problem = outside_problem(file, repo_root)
            if problem:
                add(line, "error", f"asset {file}: {problem}")
        record = (Path(file) if Path(file).is_absolute() else repo_root / file).with_name(Path(file).name + ".json")
        if file.lower().endswith(".mp4") and record.is_file():
            try:
                made = json.loads(record.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                made = None
            generator = isinstance(made, dict) and "prompt" in made and "inputs" not in made  # gen/video.py's sidecar
            compiled = isinstance(made, dict) and isinstance(made.get("inputs"), list)       # video/compile.mjs's record
            if not (generator or compiled):
                add(line, "error", f"asset {file}: {record.name} is neither a compile record nor a generator sidecar "
                                   "(unreadable or changed by hand)")
            if not compiled:
                made = {"inputs": [], "ai_generated": isinstance(made, dict) and made.get("ai_generated") is True}
            for used in made["inputs"]:
                if isinstance(used, dict) and used.get("provenance") == "outside":
                    if used.get("file") not in listed_outside:
                        add(line, "error", f"asset {file} uses outside footage {used.get('file')}: list it in ## Assets as outside")
                    elif outside_problem(used["file"], repo_root, used.get("sha256")):
                        add(line, "error", f"asset {file}: {outside_problem(used['file'], repo_root, used.get('sha256'))}")
            if made.get("ai_generated") is True and fields.get("ai_generated") == "false":
                add(line, "warning", f"asset {file} was compiled from AI inputs ({record.name}) but ai_generated is false: "
                                     "set ai_generated: true or say why not in ai_reason")
        if provenance.lower() == "ai-generated":
            if fields.get("ai_generated") == "false":
                add(line, "warning", f"asset {file} is AI-generated but ai_generated is false: set ai_generated: true "
                                     "or say why not in ai_reason (our own record; Instagram's AI label is the Board's "
                                     "choice in Notion, SA-005)")
        media = Path(file) if Path(file).is_absolute() else repo_root / file
        if file.lower().endswith((".html", ".htm")) and media.is_file():
            for stack in font_stacks(media.read_text(encoding="utf-8", errors="replace")):
                problem = font_problem(stack)
                if problem:
                    add(line, "error", f"asset {file} font stack {', '.join(stack)}: {problem}; on-image text only in "
                                       "Montserrat or Golos Text, Arabic script in Scheherazade New, "
                                       "a generic family only after one")
        elif fields.get("piece_status") != "draft" and not media.exists():
            add(line, "warning", f"asset {file} not found")

    # Sources: a news brand's claims link a source and its date (company.json: "brands", "news"). A warning: on the
    # founder's pages sources are never a finding, only the reviewer's false-news note (content-qa B, C).
    source_lines = [s for s in parts.get("Sources", (0, []))[1] if s.strip().startswith("-")]
    settings = integration("marketing", repo_root) or {}
    if ((settings.get("brands") or {}).get(brand) or {}).get("news") is True:
        for s in source_lines:
            if "https://" not in s:
                add(parts["Sources"][0], "warning", f"source needs an https:// link: {s.strip()}")
            if not DATE.search(s):
                add(parts["Sources"][0], "warning", f"source needs its date (YYYY-MM-DD): {s.strip()}")
    found = lint_words(repo_root)[0].search(body_text)
    if found and not source_lines:
        add(end + 1, "warning", f"claim word '{found.group(0)}' needs a source (advertising law)")

    if fields.get("test") == "true" and "not for posting" not in body_text.lower():
        add(at("test"), "error", "a test piece must say 'not for posting'")
    return out


def archived(page: Path) -> bool:
    lines = page.read_text(encoding="utf-8").splitlines()
    parsed = parse_front_matter(lines)
    return (parsed is not None and parsed[0].get("status") == "archived"
            and not is_piece(parsed[0], sections(lines, parsed[2] + 1)))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Lint marketing content pages.")
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument("--clean", action="store_true", help="print each caption's AI-tell score and the cleaned caption")
    args = parser.parse_args(argv)
    pages, skipped = [], []
    for p in args.paths:
        if p.is_dir():
            for page in sorted(p.rglob("*.md")):
                (skipped if archived(page) else pages).append(page)
        else:
            pages.append(p)
    for page in skipped:
        print(f"{page}: skipped: status archived")
    if args.clean:
        for page in pages:
            lines = page.read_text(encoding="utf-8").splitlines()
            parsed = parse_front_matter(lines)
            block = fenced_block(sections(lines, parsed[2] + 1).get("Caption", (0, []))[1]) if parsed else None
            if block is None:
                print(f"{page}: no caption block")
                continue
            score, tells, cleaned = ai_tells(block)
            print(f"{page}: AI tells, score {score}/100: {'; '.join(tells) or 'none'}\n{cleaned}\n")
        return 0
    findings = [f for page in pages for f in lint(page)]
    for f in findings:
        print(f"{f.path}:{f.line}: {f.level}: {f.message}")
    errors = sum(f.level == "error" for f in findings)
    print(f"content_lint: {len(pages)} pages, {errors} errors, {len(findings) - errors} warnings, {len(skipped)} archived skipped")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
