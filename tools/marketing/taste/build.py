#!/usr/bin/env python3
"""Build one page's taste picker: one self-contained HTML file, for any mix of reels, carousels, posts and stories.
Each page (account) has its own picker, and each aspect (description, number of slides, length, cover and so on) is judged
in it.

    python3 tools/marketing/taste/build.py --page <page> --rubric <file> --picks <file>
    python3 tools/marketing/taste/build.py --page <page> --session <folder>/session.json [--design]

- **Where:** <page> is an existing folder, workspaces/marketing/media/taste/<page>/ (the media folder may be a link to a
  synced folder). The rubric and the picks sit directly in it. The tool writes only picker.html there, whole or not at all, and nothing else.
  A session's picker.html goes beside its session.json, in <page>/session-<YYYY-MM-DD>[-<word>]/, the one other place it
  writes.
- **Limits:** at most 30 items, 4 aspects an item shown, 5 page questions, 15 MB (JPEG quality drops, then it
  refuses). It refuses rather than trims: a refusal names the item, exits 1 and writes nothing.
- **Children:** nothing is refused for a child on screen. Every item, and the reel or post each session reference image
  names, still needs its style.md.
- **Text is data:** reel folders and manifests come from other people's pages. Everything is escaped. Every value read
  from an item's folder gets watch.py's masks, the account included; the rubric, the CMO's own file, is escaped only.
  Descriptions, style values and the format line are also cut to 230 characters, after the mask, as trend_reader.py's
  REEL_JS cuts captions. Links are rebuilt from the kind and a checked code, never read from a file. ffmpeg opens only
  the one file, and this runs Python isolated (-I).

**The rubric** (JSON). The aspects are data: a new `style:` aspect needs no code.
    {"title": "...", "intro": "...", "assumed": ["what I guessed", ...],
     "page_questions": [{"key": "length", "question": "How long?", "options": ["Under 30 s", "30-60 s"], "default": "30-60 s"}],
     "aspects": [{"key": "subs", "label": "Subtitles", "kinds": ["reel", "story"], "from": "style:Subtitles"}]}
`from` is `style:<a line of the item's style.md>`, or `description`, `slides`, `seconds` or `cover`.

**The picks** (JSON). L liked, D disliked; an aspect with no pick isn't shown.
    {"round": 1, "items": [{"code": "<post code>", "kind": "reel|carousel|post|story", "picks": {"subs": "L", "length": "D"}}]}
A pick the item has no data for is dropped, and named in the result line.

**An item:** a reel reads workspaces/marketing/intelligence/reels/<code>/: metrics.json, style.md, video.mp4, and
breakdown.md (its first line), caption.txt and cover.jpg if they're there. A carousel, post or story reads
workspaces/marketing/intelligence/posts/<code>/: style.md and this MANIFEST.json, with its files beside it:
    {"kind": "carousel", "code": "<code>", "account": "<handle>", "date": "2026-01-06", "description": "...",
     "cover": "cover.jpg", "slides": [{"file": "1.jpg", "type": "image"}, {"file": "2.mp4", "type": "video", "seconds": 12.5}]}

**A session** (the weekly improvement session, answered visually)
is session.json, with its images beside it in ref/ (what we saw) and ours/ (our options), file names only:
    {"page": "demo", "title": "...", "intro": "...", "items": [{"id": "t1", "part": "overview|trend|taste|brand",
     "title": "...", "why": "...", "links": ["https://www.instagram.com/reel/<code>/"],
     "reference": [{"src": "ref/t1-1.jpg", "caption": "...", "reel": "<code>"}],
     "options": [{"key": "A", "label": "...", "src": "ours/t1-a.png"}], "old": "the line now", "new": "the line proposed",
     "choices": ["Adopt A", "Try", "Skip"], "default": "Adopt A"}]}
At most 8 items plus one overview, 3 reference images and 3 options an item, 2 to 4 choices, 300 characters a text
(refused, not cut). Every text is masked. Links must be Instagram reel or post addresses, rebuilt from their code. A
reference names the saved item it shows: `"reel": "<code>"` (reels/<code>/) or `"post": "<code>"` (posts/<code>/).

**A trial session** (the Board's taste-defining sittings) is a session.json with
`"mode": "trial"`: its schema is trial-schema.md, its worked example example-trial.json. Its media stay files beside the
page (ref/ and ours/, checked by their first bytes); every ref/ file names a saved item with its style.md. --design checks a
trial session and prints its design and the media it still lacks, writing nothing; it warns on stderr, and still passes,
on an intro line with a merit word (MERIT).
"""
import os
import sys

if __name__ == "__main__" and not sys.flags.isolated:
    os.execv(sys.executable, [sys.executable, "-I", *sys.argv])

import argparse  # noqa: E402
import base64  # noqa: E402
import difflib  # noqa: E402
import hashlib  # noqa: E402
import html  # noqa: E402
import json  # noqa: E402
import math  # noqa: E402
import random  # noqa: E402
import re  # noqa: E402
import subprocess  # noqa: E402
import tempfile  # noqa: E402
from itertools import combinations  # noqa: E402
from pathlib import Path  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
TASTE = Path("workspaces/marketing/media/taste")
REELS = Path("workspaces/marketing/intelligence/reels")
POSTS = Path("workspaces/marketing/intelligence/posts")
FFMPEG = Path("tools/marketing/node_modules/ffmpeg-static/ffmpeg")
FONTS = Path("tools/marketing/node_modules/@fontsource/golos-text/files")
FONT_RANGES = (  # @fontsource's own
    ("cyrillic-ext", "U+0460-052F,U+1C80-1C8A,U+20B4,U+2DE0-2DFF,U+A640-A69F,U+FE2E-FE2F"),
    ("cyrillic", "U+0301,U+0400-045F,U+0490-0491,U+04B0-04B1,U+2116"),
    ("latin-ext", "U+0100-02BA,U+02BD-02C5,U+02C7-02CC,U+02CE-02D7,U+02DD-02FF,U+0304,U+0308,U+0329,U+1D00-1DBF,U+1E00-1E9F,"
                  "U+1EF2-1EFF,U+2020,U+20A0-20AB,U+20AD-20C0,U+2113,U+2C60-2C7F,U+A720-A7FF"),
    ("latin", "U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,U+0304,U+0308,U+0329,U+2000-206F,U+20AC,"
              "U+2122,U+2191,U+2193,U+2212,U+2215,U+FEFF,U+FFFD"),
)
MAX_ITEMS = 30
MAX_ASPECTS = 4
MAX_QUESTIONS = 5
FRAMES = 6
LIMIT = 15_000_000
DESCRIPTION_CHARS = 230
WIDTH = 340
QUALITIES = (5, 7, 9, 12)
KINDS = ("reel", "carousel", "post", "story")
FIELDS = ("description", "slides", "seconds", "cover")
PAGE = re.compile(r"[a-z0-9][a-z0-9._-]{0,40}")
CODE = re.compile(r"[A-Za-z0-9_-]{5,40}")
KEY = re.compile(r"[a-z0-9_-]{1,30}")
HANDLE = re.compile(r"[A-Za-z0-9._]{1,40}")
FILE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}")
# reels/watch.py's masks, copied: importing it would bring its paid and networked modules here. test_taste.py checks they match.
MENTION = re.compile(r"[\w.+-]*@[\w.]+")
PHONE = re.compile(r"\+?\d(?:[ ()-]*\d){8,}")
SESSION = re.compile(r"session-\d{4}-\d{2}-\d{2}(?:-[a-z0-9]{1,12})?")
PARTS = ("overview", "trend", "taste", "brand")
MAX_SESSION_ITEMS = 9  # 8, plus one overview
MAX_EACH = 3  # reference images an item, and options an item
MAX_CHOICES = 4
TEXT_CHARS = 300
SESSION_WIDTH = 720  # our options carry text, which has to stay readable enlarged
OPTION_KEY = re.compile(r"[A-Za-z0-9]{1,8}")
LINK = re.compile(r"https://(?:www\.)?instagram\.com/(reel|p)/([A-Za-z0-9_-]{5,40})/?(?:\?[A-Za-z0-9=&_.-]*)?")
READ_ERRORS = (OSError, ValueError, KeyError, TypeError, AttributeError, IndexError, RecursionError)
# Trial sessions (trial-schema.md).
TRIALS = ("pairwise", "maxdiff", "cbc", "sequence", "range", "notes", "redlines", "checklist")
QUESTIONS = {"pairwise": "Which one do you prefer?", "maxdiff": "Which is the best of these four, and which the worst?",
             "cbc": "Which one would you post?", "sequence": "Which step is best, and which would you accept?",
             "range": "What's fine, and what's best?", "notes": "What do you notice? Type it as it comes.",
             "redlines": "Tick every hard no, and add your own.", "checklist": "Tick every line that applies."}
TRIAL_FIELDS = ("mode", "page", "title", "intro", "seed", "break_minutes", "parts")
PART_FIELDS = ("id", "type", "title", "minutes", "question", "intro")
FIELDS_OF = {"pairwise": ("items", "rounds", "scored"), "maxdiff": ("items", "appearances"),
             "cbc": ("attributes", "tasks", "holdouts", "media", "show_levels"), "sequence": ("dimensions",),
             "range": ("dimensions",), "notes": ("items",), "redlines": ("candidates",),
             "checklist": ("candidates", "mark")}
MEDIA = {".jpg": "image", ".jpeg": "image", ".png": "image", ".webp": "image", ".mp4": "video", ".webm": "video"}
MAX_PARTS = 16
MAX_TRIALS = 700  # with repeats; the worked example is 329 trials and 314 media files
MAX_MEDIA = 900
MEDIA_BYTES = 50_000_000
MAX_DIMENSIONS = 16
MAX_INTRO = 16
STEPS = 7
SEED_MAX = 2_147_483_647
REPEAT_GAP = 5  # a hidden repeat comes at least this many trials after its original
DRAWS = 200  # designs drawn from the seed; the best is kept
TEMPLATE_MARK = re.compile(r"\{([a-z0-9_-]{1,30})\}")
# Words that say which option is better: an intro line says what varies, never that (trial-schema.md, "A part").
MERIT = re.compile(r"\b(better|suits?|avoids?|signals?|calm\w*|helps?|hurts?|stud(?:y|ies))\b", re.IGNORECASE)
# Display text and settings, and the folder's name, left out of the design id: changing them keeps the renders and
# the saved answers.
WORDS = ("title", "minutes", "question", "intro", "name", "label", "labels", "mark", "show_levels", "break_minutes", "session")


class Refused(Exception):
    """One plain reason; nothing has been written."""


def need(condition, reason: str) -> None:
    if not condition:
        raise Refused(reason)


def masked(text) -> str:
    return PHONE.sub("...", MENTION.sub("@...", " ".join(str(text).split())))


def cut(text) -> str:
    return masked(text)[:DESCRIPTION_CHARS].strip()


def esc(text) -> str:
    return html.escape(str(text), quote=True)


def number(value):
    """A positive, finite number, or None."""
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) and 0 < value < math.inf else None


def read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, RecursionError) as error:
        raise Refused(f"{path.name}: {error}") from error


def page_folder(page: str, root: Path) -> Path:
    need(PAGE.fullmatch(page), f"page name {page!r}: lower-case letters, digits, dots, dashes, underscores")
    base = root / TASTE
    folder = base / page
    need(not base.is_symlink() and not folder.is_symlink() and folder.is_dir(), f"{TASTE / page}/ must be an existing folder, not a link")
    return folder


def directly_in(folder: Path, value: str) -> Path:
    path = Path(value).resolve()
    need(path.parent == folder.resolve() and path.is_file(), f"{value} must be a file directly in {folder.name}/")
    return path


def strings(value) -> bool:
    return isinstance(value, list) and all(isinstance(text, str) and text.strip() for text in value)


def checked_keys(entries: list, what: str) -> None:
    keys = [entry.get("key") if isinstance(entry, dict) else None for entry in entries]
    for key in keys:
        need(isinstance(key, str) and KEY.fullmatch(key), f"{what} key {key!r}: lower-case letters, digits, dashes, underscores")
    need(len(set(keys)) == len(keys), f"two {what}s share a key")


def checked_rubric(rubric) -> dict:
    need(isinstance(rubric, dict), "the rubric must be one JSON object")
    for field in ("title", "intro"):
        need(isinstance(rubric.get(field), str) and rubric[field].strip(), f"the rubric needs a {field}")
    need(strings(rubric.setdefault("assumed", [])), "the rubric's assumed must be a list of text")
    questions = rubric.setdefault("page_questions", [])
    aspects = rubric.get("aspects")
    need(isinstance(questions, list), "the rubric's page_questions must be a list")
    need(len(questions) <= MAX_QUESTIONS, f"{len(questions)} page questions: a picker asks at most {MAX_QUESTIONS}")
    need(isinstance(aspects, list) and aspects, "the rubric needs aspects")
    checked_keys(questions, "question")
    checked_keys(aspects, "aspect")
    for question in questions:
        key, options = question["key"], question.get("options")
        need(isinstance(question.get("question"), str) and question["question"].strip(), f"question {key} has no text")
        need(strings(options) and len(options) >= 2 and len(set(options)) == len(options), f"question {key}: two or more different options")
        need(question.get("default") in options, f"question {key}: its default must be one of its options")
    for aspect in aspects:
        key, source, kinds = aspect["key"], aspect.get("from"), aspect.get("kinds")
        need(isinstance(aspect.get("label"), str) and aspect["label"].strip(), f"aspect {key} has no label")
        need(strings(kinds) and kinds and set(kinds) <= set(KINDS), f"aspect {key}: kinds are {', '.join(KINDS)}")
        need(isinstance(source, str) and (source in FIELDS or (source.startswith("style:") and source[6:].strip())),
             f"aspect {key}: from is style:<line>, or one of {', '.join(FIELDS)}")
    return rubric


def checked_picks(picks, rubric: dict) -> dict:
    need(isinstance(picks, dict), "the picks must be one JSON object")
    need(type(picks.get("round")) is int and picks["round"] >= 1, "the picks need a round: a whole number from 1")
    items = picks.get("items")
    need(isinstance(items, list) and items, "the picks list no items")
    need(len(items) <= MAX_ITEMS, f"{len(items)} items: a picker holds at most {MAX_ITEMS}")
    keys = {aspect["key"] for aspect in rubric["aspects"]}
    seen = set()
    for entry in items:
        code = entry.get("code") if isinstance(entry, dict) else None
        need(isinstance(code, str) and CODE.fullmatch(code), f"item code {code!r} isn't a post code")
        need(code not in seen, f"{code}: listed twice")
        seen.add(code)
        need(entry.get("kind") in KINDS, f"{code}: kind must be one of {', '.join(KINDS)}")
        choices = entry.get("picks")
        need(isinstance(choices, dict) and choices, f"{code}: no picks")
        for key, value in choices.items():
            need(key in keys, f"{code}: {key} isn't in the rubric")
            need(value in ("L", "D"), f"{code}: the pick for {key} must be L or D")
    return picks


def plain_file(folder: Path, name: str) -> Path:
    path = folder / name
    need(not path.is_symlink() and path.is_file(), f"{folder.name}: {name} is missing or a link")
    return path


def optional_text(folder: Path, name: str) -> str:
    if not (folder / name).exists() and not (folder / name).is_symlink():
        return ""
    return plain_file(folder, name).read_text(encoding="utf-8")


def item_folder(base: Path, code: str) -> Path:
    folder = base / code
    need(not folder.is_symlink() and folder.is_dir(), f"{code}: no folder of its own in {base.name}/")
    return folder


def style_of(folder: Path) -> dict:
    """The style note's lines, by label."""
    lines = [line.partition(":") for line in plain_file(folder, "style.md").read_text(encoding="utf-8").splitlines()]
    return {label.strip(): value.strip() for label, _, value in lines}


def read_reel(root: Path, code: str) -> dict:
    folder = item_folder(root / REELS, code)
    style = style_of(folder)
    metrics = json.loads(plain_file(folder, "metrics.json").read_text(encoding="utf-8"))
    sheet = metrics["sheet_whole"]
    tiles = sheet["columns"] * sheet["rows"]
    tile_numbers = [int(part) for part in style["Frames"].replace(",", " ").split()]
    need(len(tile_numbers) == FRAMES and all(1 <= tile <= tiles for tile in tile_numbers),
         f"{code}: Frames must be {FRAMES} tiles from 1 to {tiles}")
    video = plain_file(folder, "video.mp4")
    frames = []
    for tile in tile_numbers:
        seconds = (tile - 1) * sheet["seconds_per_tile"]
        frames.append((video, seconds, False, f"Frame at {seconds:.0f} seconds"))
    saved = (folder / "cover.jpg").exists() or (folder / "cover.jpg").is_symlink()  # reels/save.py's, when it saved one
    return {"account": metrics["account"], "link": f"https://www.instagram.com/reel/{code}/", "frames": frames, "style": style,
            "label": (optional_text(folder, "breakdown.md").splitlines() or [""])[0].removeprefix("format: "),
            "multiple": number(metrics.get("multiple")), "description": optional_text(folder, "caption.txt"),
            "slides": None, "seconds": number(metrics.get("length_seconds")),
            "cover": plain_file(folder, "cover.jpg") if saved else None}


def read_post(root: Path, code: str, kind: str) -> dict:
    folder = item_folder(root / POSTS, code)
    style = style_of(folder)
    manifest = json.loads(plain_file(folder, "MANIFEST.json").read_text(encoding="utf-8"))
    need(manifest["kind"] == kind and manifest["code"] == code, f"{code}: its manifest says something else")
    slides = manifest["slides"]
    need(isinstance(slides, list) and slides, f"{code}: its manifest has no slides")
    frames = []
    seconds = 0
    for place, slide in enumerate(slides, 1):
        need(isinstance(slide["file"], str) and FILE_NAME.fullmatch(slide["file"]), f"{code}: slide {place} has a bad file name")
        path = plain_file(folder, slide["file"])
        need(slide["type"] in ("image", "video"), f"{code}: slide {place} is neither an image nor a video")
        length = number(slide.get("seconds"))
        need(slide["type"] == "image" or length, f"{code}: video slide {place} has no length")
        seconds += length if slide["type"] == "video" else 0
        if place <= FRAMES:
            frames.append((path, (length or 0) / 2, slide["type"] == "image", f"Slide {place}"))
    cover = manifest.get("cover")
    if cover is not None:
        need(isinstance(cover, str) and FILE_NAME.fullmatch(cover), f"{code}: bad cover file name")
        cover = plain_file(folder, cover)
    return {"account": manifest["account"], "frames": frames, "style": style, "cover": cover, "multiple": None,
            "link": None if kind == "story" else f"https://www.instagram.com/p/{code}/",
            "label": " ".join(part for part in (kind, str(manifest.get("date", ""))) if part),
            "description": manifest.get("description") or "", "slides": len(slides), "seconds": seconds or None}


def read_item(root: Path, entry: dict) -> dict:
    code, kind = entry["code"], entry["kind"]
    try:
        item = read_reel(root, code) if kind == "reel" else read_post(root, code, kind)
    except READ_ERRORS as error:
        raise Refused(f"{code}: can't read it: {error!r}") from error
    need(isinstance(item["account"], str) and HANDLE.fullmatch(item["account"]), f"{code}: its account isn't a handle")
    return {**item, "account": masked(item["account"]), "code": code, "kind": kind}


def value_of(aspect: dict, item: dict):
    source = aspect["from"]
    return item["style"].get(source[6:].strip()) if source.startswith("style:") else item[source]


def rows_of(item: dict, aspects: list, choices: dict) -> tuple:
    """The rows this item shows, and the picks it has nothing to show for."""
    rows, dropped = [], []
    for aspect in aspects:
        if aspect["key"] not in choices:
            continue
        value = value_of(aspect, item)
        if item["kind"] in aspect["kinds"] and value not in (None, ""):
            rows.append((aspect, value, choices[aspect["key"]]))
        else:
            dropped.append(f"{item['code']}/{aspect['key']}")
    need(rows, f"{item['code']}: none of its picks has anything to show")
    need(len(rows) <= MAX_ASPECTS, f"{item['code']}: {len(rows)} aspects, and an item shows at most {MAX_ASPECTS}")
    return rows, dropped


def frame(path: Path, seconds: float, quality: int, root: Path, image: bool = False, width: int = WIDTH) -> str:
    source = ["-f", "image2", "-pattern_type", "none"] if image else ["-ss", f"{seconds:.2f}", "-f", "mov"]
    run = subprocess.run(
        [str(root / FFMPEG), "-hide_banner", "-loglevel", "error", "-nostdin", "-protocol_whitelist", "file", *source,
         "-i", str(path), "-frames:v", "1", "-vf", f"scale={width}:-2", "-q:v", str(quality), "-f", "mjpeg", "pipe:1"],
        capture_output=True, check=True, timeout=60)
    need(run.stdout, f"no frame at {seconds} s in {path.parent.name}/{path.name}")
    return "data:image/jpeg;base64," + base64.b64encode(run.stdout).decode()


def seen_html(aspect: dict, value, quality: int, root: Path, grab) -> str:
    source = aspect["from"]
    if source == "cover":
        return f'<img src="{grab(value, 0, quality, root, True)}" alt="Cover" decoding="async">'
    if source == "description":
        return esc(cut(value))
    if source == "slides":
        return f"{value} slide{'' if value == 1 else 's'}"
    if source == "seconds":
        return f"{value:.0f} seconds"
    return esc(cut(value))


def aspect_row(field: str, aspect: dict, seen: str, chosen: str) -> str:
    def option(value: str, word: str) -> str:
        checked = " checked" if chosen == value else ""
        return (f'<input type="radio" name="{field}" id="{field}-{value}" value="{value}"{checked}>'
                f'<label for="{field}-{value}">{word}</label>')

    name = esc(aspect["label"])
    return (f'<div class="aspect" role="radiogroup" aria-label="{name}" data-aspect="{aspect["key"]}" data-pre="{chosen}">'
            f'<p class="name">{name}</p><p class="seen">{seen}</p>'
            f'<div class="toggle">{option("L", "Liked")}{option("D", "Disliked")}</div></div>')


def card(place: int, total: int, item: dict, rows: list, quality: int, root: Path, grab) -> str:
    code, account = esc(item["code"]), esc(item["account"])
    who = f'<a href="{esc(item["link"])}" target="_blank" rel="noopener">@{account}</a>' if item["link"] else f"@{account}"
    multiple = f'<p class="mult">×{item["multiple"]}</p>' if item["multiple"] else ""
    try:
        images = "".join(f'<img src="{grab(path, seconds, quality, root, image)}" alt="{esc(alt)}" decoding="async">'
                         for path, seconds, image, alt in item["frames"])
        shown = "".join(aspect_row(f'i{place}-{aspect["key"]}', aspect, seen_html(aspect, value, quality, root, grab), chosen)
                        for aspect, value, chosen in rows)
    except (OSError, subprocess.SubprocessError) as error:
        raise Refused(f"{item['code']}: ffmpeg couldn't read it: {error}") from error
    return (f'<article class="item" data-code="{code}" data-account="{account}" data-kind="{esc(item["kind"])}">'
            f'<div class="head"><p class="who">{who}</p>{multiple}<p class="format">{esc(cut(item["label"]))}</p>'
            f'<p class="place">{place} of {total}</p></div>'
            f'<div class="frames" tabindex="0" aria-label="Images from this item. Tap one to enlarge it.">{images}</div>'
            f'<div class="aspects">{shown}'
            f'<input class="note" type="text" placeholder="Note, if you want one" aria-label="Note on this item"></div></article>')


def question_block(question: dict) -> str:
    key = esc(question["key"])
    options = []
    for place, option in enumerate(question["options"]):
        checked = " checked" if option == question["default"] else ""
        options.append(f'<input type="radio" name="q-{key}" id="q-{key}-{place}" value="{esc(option)}"{checked}>'
                       f'<label for="q-{key}-{place}">{esc(option)}</label>')
    return (f'<fieldset class="question" data-key="{key}" data-pre="{esc(question["default"])}">'
            f'<legend>{esc(question["question"])}</legend><div class="options">{"".join(options)}</div></fieldset>')


def font_css(root: Path) -> str:
    faces = []
    for weight in (400, 600):
        for subset, ranges in FONT_RANGES:
            path = root / FONTS / f"golos-text-{subset}-{weight}-normal.woff2"
            need(path.is_file(), f"{path.name} is missing: run npm install in tools/marketing")
            data = base64.b64encode(path.read_bytes()).decode()
            faces.append(f'@font-face{{font-family:"Golos Text";font-weight:{weight};font-display:swap;'
                         f'src:url(data:font/woff2;base64,{data}) format("woff2");unicode-range:{ranges}}}')
    return "\n".join(faces)


def whole_page(page: str, rubric: dict, picks: dict, cards: str, css: str) -> str:
    questions = "".join(question_block(question) for question in rubric["page_questions"])
    marks = {
        "/*CSS*/": css + "\n" + (HERE / "picker.css").read_text(encoding="utf-8"),
        "/*JS*/": (HERE / "picker.js").read_text(encoding="utf-8"),
        "__PAGE__": esc(page), "__ROUND__": str(picks["round"]), "__COUNT__": str(len(picks["items"])),
        "__TITLE__": esc(rubric["title"]), "__INTRO__": esc(rubric["intro"]),
        "<!--ASSUMED-->": "".join(f"<li>{esc(line)}</li>" for line in rubric["assumed"]),
        "<!--QUESTIONS-->": f'<section class="questions"><h2>Once for this page</h2>{questions}</section>' if questions else "",
        "<!--ITEMS-->": cards,
    }
    # One pass, so a mark inside a description or the page's own script is never replaced.
    template = (HERE / "template.html").read_text(encoding="utf-8")
    return re.sub("|".join(re.escape(mark) for mark in marks), lambda match: marks[match.group()], template)


def write_whole(folder: Path, data: bytes) -> Path:
    target = folder / "picker.html"
    try:
        descriptor, temporary = tempfile.mkstemp(dir=folder, prefix=".picker-", suffix=".tmp")
        try:
            with os.fdopen(descriptor, "wb") as file:
                file.write(data)
            os.chmod(temporary, 0o644)  # mkstemp's 0600 would make it the one unreadable file in the folder
            os.replace(temporary, target)
        except OSError:
            Path(temporary).unlink(missing_ok=True)
            raise
    except OSError as error:
        raise Refused(f"can't write {target.name}: {error}") from error
    return target


def build(page: str, rubric_file: str, picks_file: str, root: Path = ROOT, grab=frame, fonts=font_css) -> str:
    """Write one page's picker and return the result line. Raises Refused, having written nothing."""
    folder = page_folder(page, root)
    rubric = checked_rubric(read_json(directly_in(folder, rubric_file)))
    picks = checked_picks(read_json(directly_in(folder, picks_file)), rubric)
    items, dropped = [], []
    for entry in picks["items"]:
        item = read_item(root, entry)
        rows, lost = rows_of(item, rubric["aspects"], entry["picks"])
        items.append((item, rows))
        dropped += lost
    css = fonts(root)
    for quality in QUALITIES:
        cards = "\n".join(card(place, len(items), item, rows, quality, root, grab) for place, (item, rows) in enumerate(items, 1))
        data = whole_page(page, rubric, picks, cards, css).encode("utf-8")
        if len(data) <= LIMIT:
            break
    need(len(data) <= LIMIT, f"{len(data) / 1_000_000:.1f} MB at the lowest quality, over the {LIMIT / 1_000_000:.0f} MB limit: use fewer items")
    target = write_whole(folder, data)
    return (f"wrote {target}: {len(items)} items, {len(data) / 1_000_000:.1f} MB at JPEG quality {quality}"
            f"; dropped, no data: {', '.join(dropped) or 'none'}")


def session_folder(page: str, session_file: str, root: Path) -> tuple:
    """The session's folder and its session.json, which sits directly in media/taste/<page>/session-<YYYY-MM-DD>[-<word>]/."""
    folder = page_folder(page, root)
    path = Path(session_file).resolve()
    need(path.name == "session.json" and SESSION.fullmatch(path.parent.name) and path.parent.parent == folder.resolve(),
         f"{session_file} must be {TASTE / page}/session-<YYYY-MM-DD>[-<word>]/session.json")
    here = folder / path.parent.name  # the resolved parent: never a link itself
    return here, directly_in(here, str(path))


def session_text(value, what: str, required: bool = False) -> str:
    """The CMO's text, which may quote other people's: one line, masked, and refused over TEXT_CHARS rather than cut."""
    need(isinstance(value, str), f"{what} must be text")
    text = " ".join(value.split())
    need(text or not required, f"{what} is empty")
    need(len(text) <= TEXT_CHARS, f"{what}: {len(text)} characters, and text holds at most {TEXT_CHARS}")
    return masked(text)


def session_image(here: Path, src, sub: str, what: str) -> Path:
    first, _, name = src.partition("/") if isinstance(src, str) else ("", "", "")
    need(first == sub and FILE_NAME.fullmatch(name), f"{what}: src must be {sub}/<file name>")
    need(not (here / sub).is_symlink() and (here / sub).is_dir(), f"{what}: {sub}/ must be a folder, not a link")
    path = here / sub / name
    need(not path.is_symlink() and path.is_file(), f"{what}: {src} is missing or a link")
    return path


def reference_code(reference: dict, what: str, root: Path) -> tuple:
    """The saved item a reference image came from, `"reel"` (reels/<code>/) or `"post"` (posts/<code>/), once its style.md
    reads: no style note, no reference image."""
    kinds = [kind for kind in ("reel", "post") if kind in reference]
    need(kinds, f"{what} names no reel or post code")
    need(len(kinds) == 1, f"{what} names both a reel and a post")
    kind, code = kinds[0], reference[kinds[0]]
    need(isinstance(code, str) and CODE.fullmatch(code), f"{what} names no {kind} code")
    try:
        style_of(item_folder(root / (REELS if kind == "reel" else POSTS), code))
    except Refused as error:
        raise Refused(f"{what}: {error}") from error
    except READ_ERRORS as error:
        raise Refused(f"{what}: can't read {code}'s style.md: {error!r}") from error
    return kind, code


def session_item(entry, here: Path, root: Path) -> dict:
    need(isinstance(entry, dict), "every session item must be one JSON object")
    key = entry.get("id")
    need(isinstance(key, str) and KEY.fullmatch(key), f"item id {key!r}: lower-case letters, digits, dashes, underscores")
    need(entry.get("part") in PARTS, f"{key}: part must be one of {', '.join(PARTS)}")
    item = {"id": key, "part": entry["part"], "title": session_text(entry.get("title"), f"{key}'s title", required=True),
            **{field: session_text(entry.get(field, ""), f"{key}'s {field}") for field in ("why", "old", "new")}}
    links = entry.get("links", [])
    need(isinstance(links, list), f"{key}: links must be a list")
    item["links"] = []
    for link in links:
        match = LINK.fullmatch(link.strip()) if isinstance(link, str) else None
        need(match, f"{key}: a link that isn't an Instagram reel or post address")
        item["links"].append((match[1], match[2]))  # rebuilt from these, never shown as written
    references, options = entry.get("reference", []), entry.get("options", [])
    for name, value in (("reference images", references), ("options", options)):
        need(isinstance(value, list) and all(isinstance(one, dict) for one in value), f"{key}: {name} must be a list of objects")
        need(len(value) <= MAX_EACH, f"{key}: {len(value)} {name}, and an item shows at most {MAX_EACH}")
    item["reference"] = []
    for place, reference in enumerate(references, 1):
        what = f"{key}'s reference {place}"
        reference_code(reference, what, root)
        item["reference"].append((session_image(here, reference.get("src"), "ref", what),
                                  session_text(reference.get("caption", ""), f"{what}'s caption")))
    item["options"] = []
    for place, option in enumerate(options, 1):
        what = f"{key}'s option {place}"
        need(isinstance(option.get("key"), str) and OPTION_KEY.fullmatch(option["key"]), f"{what}: its key is letters or digits")
        item["options"].append((option["key"], session_text(option.get("label"), f"{what}'s label", required=True),
                                session_image(here, option.get("src"), "ours", what)))
    need(len({letter for letter, _, _ in item["options"]}) == len(options), f"{key}: two options share a key")
    choices = entry.get("choices")
    need(isinstance(choices, list) and 2 <= len(choices) <= MAX_CHOICES, f"{key}: two to {MAX_CHOICES} choices")
    item["choices"] = [session_text(choice, f"{key}'s choice", required=True) for choice in choices]
    need(len(set(item["choices"])) == len(choices), f"{key}: two choices are the same")
    item["default"] = session_text(entry.get("default"), f"{key}'s default", required=True)
    need(item["default"] in item["choices"], f"{key}: its default must be one of its choices")
    return item


def checked_session(session, page: str, here: Path, root: Path) -> dict:
    need(isinstance(session, dict), "the session must be one JSON object")
    need(session.get("page") == page, f"the session is for page {session.get('page')!r}, not {page}")
    items = session.get("items")
    need(isinstance(items, list) and items, "the session lists no items")
    overviews = sum(isinstance(entry, dict) and entry.get("part") == "overview" for entry in items)
    need(overviews <= 1 and len(items) - overviews <= MAX_SESSION_ITEMS - 1,
         f"{len(items)} items, {overviews} of them overviews: a session holds at most {MAX_SESSION_ITEMS - 1}, plus one overview")
    checked = [session_item(entry, here, root) for entry in items]
    need(len({item["id"] for item in checked}) == len(checked), "two items share an id")
    return {"title": session_text(session.get("title"), "the session's title", required=True),
            "intro": session_text(session.get("intro", ""), "the session's intro"), "items": checked}


def change_html(old: str, new: str) -> str:
    """The line now and the line proposed, word by word: what goes is struck through, what comes is marked."""
    if not old and not new:
        return ""
    before, after = old.split(), new.split()
    gone, came = [], []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(a=before, b=after, autojunk=False).get_opcodes():
        lost, added = esc(" ".join(before[i1:i2])), esc(" ".join(after[j1:j2]))
        if tag == "equal":
            gone.append(lost)
            came.append(added)
            continue
        gone += [f"<del>{lost}</del>"] if lost else []
        came += [f"<ins>{added}</ins>"] if added else []
    return (f'<div class="change"><p class="old"><span class="tag">Now</span>{" ".join(gone) if old else "Nothing yet: a new line."}</p>'
            f'<p class="new"><span class="tag">Proposed</span>{" ".join(came) if new else "Nothing: the line goes."}</p></div>')


def session_card(place: int, total: int, item: dict, quality: int, root: Path, grab) -> str:
    def figure(path: Path, caption: str, alt: str) -> str:
        return (f'<figure><img src="{grab(path, 0, quality, root, True, SESSION_WIDTH)}" alt="{esc(alt)}" decoding="async">'
                f'<figcaption>{caption}</figcaption></figure>')

    try:
        theirs = "".join(figure(path, esc(caption), caption or "What we saw") for path, caption in item["reference"])
        ours = "".join(figure(path, f"<b>{esc(key)}</b> {esc(label)}", f"Option {key}: {label}") for key, label, path in item["options"])
    except (OSError, subprocess.SubprocessError) as error:
        raise Refused(f"{item['id']}: ffmpeg couldn't read an image: {error}") from error
    sides = [f'<div class="side"><h3>{name}</h3><div class="figs">{figures}</div></div>'
             for name, figures in (("What we saw", theirs), ("Ours", ours)) if figures]
    compare = f'<div class="compare{" both" if len(sides) == 2 else ""}">{"".join(sides)}</div>' if sides else ""
    links = "".join(f'<a href="https://www.instagram.com/{kind}/{code}/" target="_blank" rel="noopener">{kind} {code}</a>'
                    for kind, code in item["links"])
    lede = "".join((f'<p class="why">{esc(item["why"])}</p>' if item["why"] else "",
                    f'<p class="links">{links}</p>' if links else ""))
    lede = f'<div class="lede">{lede}</div>' if lede else ""
    group = f'c-{item["id"]}'
    buttons = "".join(f'<input type="radio" name="{group}" id="{group}-{n}" value="{esc(choice)}"'
                      f'{" checked" if choice == item["default"] else ""}><label for="{group}-{n}">{esc(choice)}</label>'
                      for n, choice in enumerate(item["choices"]))
    return (f'<article class="item" data-id="{item["id"]}" data-part="{item["part"]}">'
            f'<div class="head"><p class="who">{esc(item["title"])}</p><p class="format">{item["id"]}, {item["part"]}</p>'
            f'<p class="place">{place} of {total}</p></div>'
            f'{lede}{compare}'
            f'<div class="answer{"" if compare else " wide"}">{change_html(item["old"], item["new"])}'
            f'<fieldset class="choice" data-pre="{esc(item["default"])}"><legend>Your answer</legend>'
            f'<div class="options">{buttons}</div></fieldset>'
            f'<input class="note" type="text" placeholder="Note, if you want one" aria-label="Note on {item["id"]}"></div></article>')


def session_page(page: str, name: str, session: dict, cards: str, css: str) -> str:
    marks = {
        "/*CSS*/": "\n".join((css, (HERE / "picker.css").read_text(encoding="utf-8"), (HERE / "session.css").read_text(encoding="utf-8"))),
        "/*JS*/": (HERE / "session.js").read_text(encoding="utf-8"),
        "__PAGE__": esc(page), "__SESSION__": esc(name), "__COUNT__": str(len(session["items"])),
        "__TITLE__": esc(session["title"]), "__INTRO__": esc(session["intro"]), "<!--ITEMS-->": cards,
    }
    # One pass, as whole_page does, so a mark inside the session's text is never replaced.
    template = (HERE / "session.html").read_text(encoding="utf-8")
    return re.sub("|".join(re.escape(mark) for mark in marks), lambda match: marks[match.group()], template)


def whole(value, low: int, high: int, what: str) -> int:
    need(type(value) is int and low <= value <= high, f"{what} must be a whole number from {low} to {high}")
    return value


def only(entry, fields: tuple, what: str) -> dict:
    """One JSON object holding only the named fields: a misspelt field is refused, not silently left out."""
    need(isinstance(entry, dict), f"{what} must be one JSON object")
    for field in entry:
        need(field in fields, f"{what}: unknown field {str(field)[:40]!r}")
    return entry


def key_of(value, what: str) -> str:
    need(isinstance(value, str) and KEY.fullmatch(value), f"{what} {str(value)[:40]!r}: lower-case letters, digits, dashes, underscores")
    return value


def pair(a: str, b: str) -> tuple:
    return (a, b) if a < b else (b, a)


def magic(head: bytes, suffix: str) -> bool:
    """Whether a file's first bytes are what its suffix says."""
    if suffix in (".jpg", ".jpeg"):
        return head[:3] == b"\xff\xd8\xff"
    if suffix == ".png":
        return head[:8] == b"\x89PNG\r\n\x1a\n"
    if suffix == ".webp":
        return head[:4] == b"RIFF" and head[8:12] == b"WEBP"
    if suffix == ".mp4":
        return head[4:8] == b"ftyp"
    return head[:4] == b"\x1a\x45\xdf\xa3"  # .webm


def trial_media(here: Path, src, what: str, missing, subs: tuple = ("ref", "ours")) -> dict:
    """One file beside the session, by name only: a plain file in ref/ or ours/, at most MEDIA_BYTES, whose first bytes
    match its suffix. With --design, `missing` is a set and an absent file goes in it instead of being refused."""
    first, _, name = src.partition("/") if isinstance(src, str) else ("", "", "")
    suffix = Path(name).suffix.lower()
    need(first in subs and FILE_NAME.fullmatch(name) and suffix in MEDIA,
         f"{what}: src must be {' or '.join(subs)}/<file name> ending {', '.join(MEDIA)}")
    folder = here / first
    need(not folder.is_symlink() and (folder.is_dir() or not folder.exists()), f"{what}: {first}/ must be a folder, not a link")
    path = folder / name
    if missing is not None and not path.is_symlink() and not path.exists():
        missing.add(src)
        return {"src": src, "media": MEDIA[suffix]}
    need(not path.is_symlink() and path.is_file(), f"{what}: {src} is missing or a link")
    try:
        size = path.stat().st_size
        with path.open("rb") as file:
            head = file.read(12)
    except OSError as error:  # an unreadable file, or a cloud drive's placeholder that won't download
        raise Refused(f"{what}: can't read {src}: {error.strerror or error}") from error
    need(size <= MEDIA_BYTES, f"{what}: {src} is {size / 1_000_000:.0f} MB, and a file holds at most {MEDIA_BYTES / 1_000_000:.0f} MB")
    need(magic(head, suffix), f"{what}: {src} isn't a {suffix[1:]} file")
    return {"src": src, "media": MEDIA[suffix]}


def trial_item(entry, what: str, here: Path, root: Path, missing) -> dict:
    """An item to judge. A ref/ file names its saved reel or post, whose style.md must read, and is
    named for it (<code>.<suffix>); an ours/ file names neither."""
    entry = only(entry, ("id", "src", "label", "reel", "post"), what)
    key = key_of(entry.get("id"), f"{what}'s id")
    what = f"{what} {key}"
    item = {"id": key}
    src = entry.get("src")
    if isinstance(src, str) and src.startswith("ref/"):
        kind, code = reference_code(entry, what, root)  # first, design or not, media rendered or not
        need(Path(src).stem == code, f"{what}: a ref/ file is named for its {kind}: ref/{code}.<suffix>")
        item[kind] = code
    else:
        need("reel" not in entry and "post" not in entry, f"{what}: only a ref/ file names a reel or post code")
    item.update(trial_media(here, src, what, missing))
    if "label" in entry:
        item["label"] = session_text(entry["label"], f"{what}'s label", required=True)
    return item


def trial_items(part: dict, what: str, low: int, high: int, here: Path, root: Path, missing) -> list:
    entries = part.get("items")
    need(isinstance(entries, list) and low <= len(entries) <= high, f"{what}: {low} to {high} items")
    items = [trial_item(entry, f"{what}'s item", here, root, missing) for entry in entries]
    need(len({item["id"] for item in items}) == len(items), f"{what}: two items share an id")
    return items


def trial_intro(value, what: str) -> list:
    need(isinstance(value, list) and len(value) <= MAX_INTRO, f"{what}: intro is a list of at most {MAX_INTRO} lines")
    lines = []
    for place, entry in enumerate(value, 1):
        entry = only(entry, ("name", "line"), f"{what}'s intro line {place}")
        lines.append({"name": session_text(entry.get("name"), f"{what}'s intro line {place} name", required=True),
                      "line": session_text(entry.get("line"), f"{what}'s intro line {place}", required=True)})
    return lines


def round_robin(ids: list, rounds: int, rng) -> list:
    """`rounds` rounds of a circle-method round robin over an even number of items, each round showing every item once.
    Past len(ids) - 1 rounds the schedule comes again."""
    order = list(ids)
    rng.shuffle(order)
    fixed, rest = order[0], order[1:]
    schedule = []
    for turn in range(len(rest)):
        circle = [fixed] + rest[turn:] + rest[:turn]
        schedule.append([(circle[k], circle[-1 - k]) for k in range(len(circle) // 2)])
    rng.shuffle(schedule)
    return (schedule + schedule)[:rounds]


def pairwise_trials(ids: list, rounds: int, rng) -> list:
    """The round robin in shuffled order, no item twice in a row where a round allows it. A pair seen before comes with
    its sides swapped; a new one puts on the left the item that has been there less."""
    trials, lefts, seen = [], dict.fromkeys(ids, 0), {}
    for pairs in round_robin(ids, rounds, rng):
        pairs = list(pairs)
        rng.shuffle(pairs)
        if trials:
            last = set(trials[-1]["items"])
            for place, (a, b) in enumerate(pairs):
                if a not in last and b not in last:
                    pairs.insert(0, pairs.pop(place))
                    break
        for a, b in pairs:
            if pair(a, b) in seen:
                right, left = seen[pair(a, b)]
            elif lefts[a] != lefts[b]:
                left, right = (a, b) if lefts[a] < lefts[b] else (b, a)
            else:
                left, right = (a, b) if rng.random() < 0.5 else (b, a)
            seen[pair(a, b)] = (left, right)
            lefts[left] += 1
            trials.append({"items": [left, right]})
    return trials


def maxdiff_sets(ids: list, appearances: int, rng, what: str) -> list:
    """Sets of 4 showing every item `appearances` times: of DRAWS greedy draws, the one whose pairs meet most evenly."""
    count = len(ids) * appearances // 4
    best, best_score = None, None
    for _ in range(DRAWS):
        left, together, sets = dict.fromkeys(ids, appearances), {}, []
        for done in range(count):
            chosen = [key for key in ids if left[key] == count - done]  # in every set still to come
            pool = [key for key in ids if left[key] and key not in chosen]
            rng.shuffle(pool)
            while len(chosen) < 4 and pool:
                pick = min(pool, key=lambda key: (sum(together.get(pair(key, other), 0) for other in chosen), -left[key]))
                pool.remove(pick)
                chosen.append(pick)
            if len(chosen) != 4:
                break
            for a, b in combinations(chosen, 2):
                together[pair(a, b)] = together.get(pair(a, b), 0) + 1
            for key in chosen:
                left[key] -= 1
            sets.append(chosen)
        else:
            score = sum(n * n for n in together.values())
            if best_score is None or score < best_score:
                best, best_score = sets, score
    need(best is not None, f"{what}: no balanced sets of 4 found: change the items or appearances")
    rng.shuffle(best)
    ordered = [best.pop(0)]
    while best:  # each set shares as little as it can with the one before
        last = set(ordered[-1])
        ordered.append(best.pop(min(range(len(best)), key=lambda k: len(last & set(best[k])))))
    for chosen in ordered:
        rng.shuffle(chosen)
    return [{"items": chosen} for chosen in ordered]


def effects(levels_of: list, option: dict) -> list:
    """An option's effects-coded row: one column per level but the last, which is minus one in all of them."""
    row = []
    for attribute, levels in levels_of:
        place = levels.index(option[attribute])
        row += [1.0 if place == k else (-1.0 if place == len(levels) - 1 else 0.0) for k in range(len(levels) - 1)]
    return row


def log_det(matrix: list) -> "float | None":
    """The log determinant of a symmetric positive semi-definite matrix, or None if it's singular."""
    rows = [row[:] for row in matrix]
    total = 0.0
    for col in range(len(rows)):
        pivot = max(range(col, len(rows)), key=lambda r: abs(rows[r][col]))
        if abs(rows[pivot][col]) < 1e-9:
            return None
        rows[col], rows[pivot] = rows[pivot], rows[col]
        total += math.log(abs(rows[col][col]))
        for r in range(col + 1, len(rows)):
            factor = rows[r][col] / rows[col][col]
            if factor:
                for c in range(col, len(rows)):
                    rows[r][c] -= factor * rows[col][c]
    return total


def information(tasks: list, levels_of: list) -> list:
    """The logit's information matrix at zero utilities, where each of 3 options is picked one time in 3."""
    size = sum(len(levels) - 1 for _, levels in levels_of)
    matrix = [[0.0] * size for _ in range(size)]
    for task in tasks:
        rows = [effects(levels_of, option) for option in task]
        mean = [sum(column) / len(rows) for column in zip(*rows)]
        for row in rows:
            centred = [x - m for x, m in zip(row, mean)]
            for i, x in enumerate(centred):
                if x:
                    for j, y in enumerate(centred):
                        matrix[i][j] += x * y / len(rows)
    return matrix


def cbc_task(levels_of: list, used: dict, rng) -> "list | None":
    """Three different options, each attribute showing its least-used levels (three different ones where it has three)."""
    for _ in range(100):
        columns = {}
        for attribute, levels in levels_of:
            order = list(levels)
            rng.shuffle(order)
            order.sort(key=lambda level: used[attribute][level])
            column = order[:3] if len(order) >= 3 else [order[0], order[1], order[0]]
            rng.shuffle(column)
            columns[attribute] = column
        options = [{attribute: columns[attribute][k] for attribute, _ in levels_of} for k in range(3)]
        if len({tuple(option.values()) for option in options}) == 3:
            for option in options:
                for attribute, level in option.items():
                    used[attribute][level] += 1
            return options
    return None


def cbc_design(levels_of: list, tasks: int, holdouts: int, rng, what: str) -> list:
    """Of DRAWS level-balanced designs, the one that tells the level effects apart best (D-efficiency), then the holdouts,
    which the analysis keeps out of the fit, at places drawn from the seed."""
    best, best_score, best_used = None, None, None
    for _ in range(DRAWS):
        used = {attribute: dict.fromkeys(levels, 0) for attribute, levels in levels_of}
        design = [cbc_task(levels_of, used, rng) for _ in range(tasks)]
        if None in design:
            continue
        score = log_det(information(design, levels_of))
        if score is not None and (best_score is None or score > best_score):
            best, best_score, best_used = design, score, used
    effects_count = sum(len(levels) - 1 for _, levels in levels_of)
    need(best is not None, f"{what}: {tasks} tasks can't tell {effects_count} level effects apart: add tasks or cut levels")
    trials = [{"options": task} for task in best]
    for _ in range(holdouts):
        task = cbc_task(levels_of, best_used, rng)
        need(task is not None, f"{what}: no holdout task differs in all three options")
        trials.insert(rng.randrange(1, len(trials) + 1), {"options": task, "holdout": True})
    return trials


def sequence_trials(ids: list, rng) -> list:
    """Every dimension once ascending, then every one once descending, each pass in its own shuffled order."""
    up, down = list(ids), list(ids)
    rng.shuffle(up)
    rng.shuffle(down)
    if len(down) > 1 and down[0] == up[-1]:
        down = down[1:] + down[:1]
    return [{"dimension": key, "order": "up"} for key in up] + [{"dimension": key, "order": "down"} for key in down]


def numbered(part: str, trials: list, rng, swap=None, members=lambda trial: ()) -> list:
    """Trial ids in their final order. With `swap`, about one trial in 10 (at least one; never a holdout) comes again,
    hidden, at least REPEAT_GAP trials later, swapped, beside trials that share none of its members where it can."""
    order, placed = list(trials), []
    if swap:
        regular = [k for k, trial in enumerate(order) if not trial.get("holdout")]
        eligible = [k for k in regular if k + REPEAT_GAP < len(order)] or regular[:1]
        inserts = []
        for source in sorted(rng.sample(eligible, min(max(1, int(len(regular) / 10 + 0.5)), len(eligible)))):
            mine = set(members(order[source]))
            slots = range(min(source + REPEAT_GAP + 1, len(order)), len(order) + 1)
            clear = [t for t in slots if not mine & set(members(order[t - 1])) and not (t < len(order) and mine & set(members(order[t])))]
            inserts.append((rng.choice(clear or list(slots)), source))
        inserts.sort()
        for at in range(len(order) + 1):
            placed += [(swap(order[source]), order[source]) for slot, source in inserts if slot == at]
            if at < len(order):
                placed.append((order[at], None))
    else:
        placed = [(trial, None) for trial in order]
    for place, (trial, original) in enumerate(placed, 1):
        trial["id"] = f"{part}.{place}"
        if original is not None:
            trial["repeat_of"] = original["id"]  # always earlier, so already numbered
    return [trial for trial, _ in placed]


def cbc_part(part: dict, what: str, here: Path, missing, rng) -> dict:
    attributes = part.get("attributes")
    need(isinstance(attributes, list) and 1 <= len(attributes) <= 8, f"{what}: 1 to 8 attributes")
    checked = []
    for place, attribute in enumerate(attributes, 1):
        attribute = only(attribute, ("id", "name", "levels"), f"{what}'s attribute {place}")
        name = key_of(attribute.get("id"), f"{what}'s attribute {place} id")
        levels = attribute.get("levels")
        need(isinstance(levels, list) and 2 <= len(levels) <= 5, f"{what}'s attribute {name}: 2 to 5 levels")
        shown = []
        for level in levels:
            level = only(level, ("id", "label"), f"{what}'s attribute {name}: a level")
            shown.append({"id": key_of(level.get("id"), f"{what}'s attribute {name}: level id"),
                          "label": session_text(level.get("label"), f"{what}'s attribute {name}: a level's label", required=True)})
        need(len({level["id"] for level in shown}) == len(shown), f"{what}'s attribute {name}: two levels share an id")
        checked.append({"id": name, "name": session_text(attribute.get("name"), f"{what}'s attribute {name} name", required=True),
                        "levels": shown})
    ids = [attribute["id"] for attribute in checked]
    need(len(set(ids)) == len(ids), f"{what}: two attributes share an id")
    need(math.prod(len(attribute["levels"]) for attribute in checked) >= 3, f"{what}: the levels make fewer than 3 different options")
    template = part.get("media")
    need(isinstance(template, str) and template.startswith("ours/") and sorted(TEMPLATE_MARK.findall(template)) == sorted(ids)
         and not set("{}") & set(TEMPLATE_MARK.sub("", template)),
         f"{what}: media must be ours/<file name> holding each {{attribute id}} once")
    tasks = whole(part.get("tasks"), 2, 30, f"{what}'s tasks")
    holdouts = whole(part.get("holdouts", 0), 0, 4, f"{what}'s holdouts")
    show_levels = part.get("show_levels", False)
    need(isinstance(show_levels, bool), f"{what}: show_levels is true or false")
    levels_of = [(attribute["id"], [level["id"] for level in attribute["levels"]]) for attribute in checked]
    trials = cbc_design(levels_of, tasks, holdouts, rng, what)
    files = {}
    for trial in trials:
        options = []
        for levels in trial["options"]:
            src = TEMPLATE_MARK.sub(lambda match: levels[match.group(1)], template)
            if src not in files:
                files[src] = trial_media(here, src, f"{what}'s option", missing, ("ours",))
            options.append({"levels": levels, **files[src]})
        trial["options"] = options
    trials = numbered(part["id"], trials, rng, lambda trial: {"options": trial["options"][1:] + trial["options"][:1]})
    return {"attributes": checked, "tasks": tasks, "holdouts": holdouts, "show_levels": show_levels, "trials": trials}


def dimensions_of(part: dict, what: str, fields: tuple) -> list:
    dimensions = part.get("dimensions")
    need(isinstance(dimensions, list) and 1 <= len(dimensions) <= MAX_DIMENSIONS, f"{what}: 1 to {MAX_DIMENSIONS} dimensions")
    checked = []
    for place, dimension in enumerate(dimensions, 1):
        dimension = only(dimension, fields, f"{what}'s dimension {place}")
        key = key_of(dimension.get("id"), f"{what}'s dimension {place} id")
        checked.append((key, dimension, f"{what}'s dimension {key}"))
    need(len({key for key, _, _ in checked}) == len(checked), f"{what}: two dimensions share an id")
    return checked


def texts(value, what: str, low: int, high: int) -> list:
    need(isinstance(value, list) and low <= len(value) <= high, f"{what}: {low} to {high} lines")
    lines = [session_text(line, what, required=True) for line in value]
    need(len(set(lines)) == len(lines), f"{what}: two lines are the same")
    return lines


def trial_part(part, here: Path, root: Path, missing, seed: int) -> dict:
    """One part, checked, with its fixed design drawn from the seed and the part's id, so changing one part leaves the
    others' designs as they were."""
    need(isinstance(part, dict), "every part must be one JSON object")
    key = key_of(part.get("id"), "a part's id")
    what = f"part {key}"
    kind = part.get("type")
    need(kind in TRIALS, f"{what}: type must be one of {', '.join(TRIALS)}")
    only(part, PART_FIELDS + FIELDS_OF[kind], what)
    rng = random.Random(f"{seed}/{key}")
    shown = {"id": key, "type": kind, "title": session_text(part.get("title"), f"{what}'s title", required=True),
             "minutes": whole(part.get("minutes"), 1, 60, f"{what}'s minutes"),
             "question": session_text(part.get("question", QUESTIONS[kind]), f"{what}'s question", required=True),
             "intro": trial_intro(part.get("intro", []), what)}
    if kind == "pairwise":
        items = trial_items(part, what, 4, 40, here, root, missing)
        need(len(items) % 2 == 0, f"{what}: an even number of items")
        rounds = whole(part.get("rounds"), 1, 2 * (len(items) - 1), f"{what}'s rounds")
        scored = part.get("scored", True)
        need(isinstance(scored, bool), f"{what}: scored is true or false")
        trials = pairwise_trials([item["id"] for item in items], rounds, rng)
        swap = (lambda trial: {"items": trial["items"][::-1]}) if scored else None
        shown.update(items=items, rounds=rounds, scored=scored,
                     trials=numbered(key, trials, rng, swap, lambda trial: trial["items"]))
    elif kind == "maxdiff":
        items = trial_items(part, what, 4, 30, here, root, missing)
        appearances = whole(part.get("appearances"), 2, 6, f"{what}'s appearances")
        need(len(items) * appearances % 4 == 0, f"{what}: items × appearances must divide by 4")
        trials = maxdiff_sets([item["id"] for item in items], appearances, rng, what)
        shown.update(items=items, appearances=appearances,
                     trials=numbered(key, trials, rng, lambda trial: {"items": trial["items"][2:] + trial["items"][:2]},
                                     lambda trial: trial["items"]))
    elif kind == "cbc":
        shown.update(cbc_part(part, what, here, missing, rng))
    elif kind == "sequence":
        dimensions = []
        for name, dimension, where in dimensions_of(part, what, ("id", "name", "steps", "labels")):
            steps = dimension.get("steps")
            need(isinstance(steps, list) and len(steps) == STEPS, f"{where}: {STEPS} steps")
            entry = {"id": name, "name": session_text(dimension.get("name"), f"{where}'s name", required=True),
                     "steps": [trial_media(here, step, f"{where}'s step {k}", missing, ("ours",)) for k, step in enumerate(steps, 1)]}
            if "labels" in dimension:
                entry["labels"] = [session_text(label, f"{where}'s label", required=True) for label in dimension["labels"]] \
                    if isinstance(dimension["labels"], list) and len(dimension["labels"]) == STEPS else need(False, f"{where}: {STEPS} labels")
            dimensions.append(entry)
        shown.update(dimensions=dimensions, trials=numbered(key, sequence_trials([d["id"] for d in dimensions], rng), rng))
    elif kind == "range":
        dimensions = []
        for name, dimension, where in dimensions_of(part, what, ("id", "name", "values", "ordered")):
            ordered = dimension.get("ordered", True)
            need(isinstance(ordered, bool), f"{where}: ordered is true or false")
            dimensions.append({"id": name, "name": session_text(dimension.get("name"), f"{where}'s name", required=True),
                               "values": texts(dimension.get("values"), f"{where}'s values", 2, 12), "ordered": ordered})
        trials = [{"dimension": dimension["id"]} for dimension in dimensions]
        rng.shuffle(trials)
        shown.update(dimensions=dimensions, trials=numbered(key, trials, rng))
    elif kind == "notes":
        items = trial_items(part, what, 1, 12, here, root, missing)
        trials = [{"item": item["id"]} for item in items]
        rng.shuffle(trials)
        shown.update(items=items, trials=numbered(key, trials, rng))
    elif kind == "redlines":
        candidates = texts(part.get("candidates", []), f"{what}'s candidates", 0, 30)
        shown.update(candidates=candidates, trials=numbered(key, [{"candidates": rng.sample(candidates, len(candidates))}], rng))
    else:  # a list the analysis passes on as ticked, never as red lines; its lines keep their order
        candidates = texts(part.get("candidates"), f"{what}'s candidates", 1, 30)
        mark = session_text(part.get("mark", "Tick"), f"{what}'s mark", required=True)
        need(len(mark) <= 40, f"{what}: the mark is a button, at most 40 characters")
        shown.update(candidates=candidates, mark=mark, trials=numbered(key, [{"candidates": candidates}], rng))
    return shown


def structure(value):
    """The design without its display text, for the design id."""
    if isinstance(value, dict):
        return {key: structure(inner) for key, inner in value.items() if key not in WORDS}
    if isinstance(value, list):
        return [structure(inner) for inner in value]
    return value


def sources(value) -> set:
    if isinstance(value, dict):
        found = {value["src"]} if "src" in value and "media" in value else set()
        return found.union(*(sources(inner) for inner in value.values()))
    if isinstance(value, list):
        return set().union(*(sources(inner) for inner in value))
    return set()


def checked_trial(session: dict, page: str, here: Path, root: Path, missing) -> dict:
    """The whole sitting's design, every check passed. Raises Refused, naming the part."""
    only(session, TRIAL_FIELDS, "the session")
    need(session.get("page") == page, f"the session is for page {str(session.get('page'))[:40]!r}, not {page}")
    seed = whole(session.get("seed"), 1, SEED_MAX, "the seed")
    break_minutes = whole(session.get("break_minutes"), 20, 25, "break_minutes")
    parts = session.get("parts")
    need(isinstance(parts, list) and 1 <= len(parts) <= MAX_PARTS, f"the session holds 1 to {MAX_PARTS} parts")
    checked = [trial_part(part, here, root, missing, seed) for part in parts]
    need(len({part["id"] for part in checked}) == len(checked), "two parts share an id")
    trials = sum(len(part["trials"]) for part in checked)
    need(trials <= MAX_TRIALS, f"{trials} trials with repeats, and a sitting holds at most {MAX_TRIALS}")
    design = {"format": "taste-trial-1", "page": page, "session": here.name, "seed": seed,
              "title": session_text(session.get("title"), "the session's title", required=True),
              "intro": session_text(session.get("intro", ""), "the session's intro"), "break_minutes": break_minutes,
              "parts": checked}
    files = sources(design)
    need(len(files) <= MAX_MEDIA, f"{len(files)} media files, and a sitting shows at most {MAX_MEDIA}")
    design["design_id"] = hashlib.sha256(json.dumps(structure(design), sort_keys=True).encode()).hexdigest()[:12]
    return design


def trial_page(design: dict, css: str) -> str:
    # The design goes in as JSON the HTML parser can't end early: no <, > or & in it.
    data = json.dumps(design, ensure_ascii=False, separators=(",", ":"))
    data = data.replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")
    marks = {
        "/*CSS*/": "\n".join((css, (HERE / "picker.css").read_text(encoding="utf-8"), (HERE / "trial.css").read_text(encoding="utf-8"))),
        "/*JS*/": (HERE / "trial.js").read_text(encoding="utf-8"),
        "__PAGE__": esc(design["page"]), "__SESSION__": esc(design["session"]), "__TITLE__": esc(design["title"]),
        "__DESIGN__": data,
    }
    # One pass, as whole_page does, so a mark inside the design is never replaced.
    template = (HERE / "trial.html").read_text(encoding="utf-8")
    return re.sub("|".join(re.escape(mark) for mark in marks), lambda match: marks[match.group()], template)


def build_trial(page: str, here: Path, session: dict, root: Path, fonts, design_only: bool) -> str:
    """Write a trial session's picker beside its session.json, or with design_only print its design and write nothing."""
    missing = set() if design_only else None
    design = checked_trial(session, page, here, root, missing)
    parts = design["parts"]
    trials = sum(len(part["trials"]) for part in parts)
    if design_only:
        for part in parts:
            for place, entry in enumerate(part["intro"], 1):
                word = MERIT.search(entry["line"])
                if word:
                    print(f"warning: {part['id']}'s intro line {place} says {word[0]!r}: an intro line says what varies,"
                          " never which is better (trial-schema.md)", file=sys.stderr)
        return json.dumps({
            "page": page, "session": here.name, "seed": design["seed"], "design_id": design["design_id"], "trials": trials,
            "minutes": sum(part["minutes"] for part in parts),
            "parts": [{"id": part["id"], "type": part["type"], "trials": len(part["trials"]),
                       "repeats": sum("repeat_of" in trial for trial in part["trials"]),
                       "holdouts": sum(bool(trial.get("holdout")) for trial in part["trials"]), "minutes": part["minutes"]}
                      for part in parts],
            "files": sorted(sources(design)), "missing": sorted(missing)}, indent=1, ensure_ascii=False)
    data = trial_page(design, fonts(root)).encode("utf-8")
    need(len(data) <= LIMIT, f"{len(data) / 1_000_000:.1f} MB of page, over the {LIMIT / 1_000_000:.0f} MB limit")
    target = write_whole(here, data)
    return f"wrote {target}: {len(parts)} parts, {trials} trials, {len(sources(design))} media files, seed {design['seed']}"


def build_session(page: str, session_file: str, root: Path = ROOT, grab=frame, fonts=font_css, design_only: bool = False) -> str:
    """Write one session's picker beside its session.json and return the result line. Raises Refused, having written nothing."""
    here, path = session_folder(page, session_file, root)
    raw = read_json(path)
    if isinstance(raw, dict) and "mode" in raw:
        need(raw["mode"] == "trial", 'a session\'s mode is "trial", or it has none')
        return build_trial(page, here, raw, root, fonts, design_only)
    need(not design_only, '--design is for a trial session, one with "mode": "trial"')
    session = checked_session(raw, page, here, root)
    css = fonts(root)
    total = len(session["items"])
    for quality in QUALITIES:
        cards = "\n".join(session_card(place, total, item, quality, root, grab) for place, item in enumerate(session["items"], 1))
        data = session_page(page, here.name, session, cards, css).encode("utf-8")
        if len(data) <= LIMIT:
            break
    need(len(data) <= LIMIT, f"{len(data) / 1_000_000:.1f} MB at the lowest quality, over the {LIMIT / 1_000_000:.0f} MB limit: use fewer images")
    target = write_whole(here, data)
    return f"wrote {target}: {total} items, {len(data) / 1_000_000:.1f} MB at JPEG quality {quality}"


def main(argv: "list | None" = None) -> int:
    parser = argparse.ArgumentParser(description="Build one page's taste picker, or one session's picker.")
    parser.add_argument("--page", required=True)
    parser.add_argument("--rubric")
    parser.add_argument("--picks")
    parser.add_argument("--session", help="a session.json, instead of --rubric and --picks")
    parser.add_argument("--design", action="store_true", help="with a trial --session: print its design and missing media, write nothing")
    args = parser.parse_args(argv)
    given = [name for name in ("rubric", "picks", "session") if getattr(args, name) is not None]
    if given not in (["rubric", "picks"], ["session"]):
        parser.error("give --rubric and --picks, or --session alone")
    if args.design and args.session is None:
        parser.error("--design goes with --session")
    try:
        print(build_session(args.page, args.session, design_only=args.design) if args.session is not None
              else build(args.page, args.rubric, args.picks))
    except Refused as error:
        print(f"refused: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
