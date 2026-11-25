"""The one builder of a Metricool post, shared by stage_item.py and the PreToolUse hook (docs/marketing.md, "Publishing").

A piece page's `## Post` section, `## Caption` block and front matter, its Board decision (the approvals page the
sync hook writes) and company.json's marketing settings are the only inputs. stage_item.py builds
the `createScheduledPost` arguments from them; the hook (scripts/hooks/guard_marketing_tools.py)
rebuilds them from the same inputs and allows the cmo's call only if it equals the rebuild, with
`autoPublish` false: the Board publishes each Instagram post himself in Metricool's app. A Short
(`- Type: short`, only on a brand whose settings say `shorts`) goes to YouTube through the same call and the same
checks, always private, and may publish at its set time; every other type goes to Instagram. Instagram's AI flag is
the Board's AI label from Notion, off unless ticked (SA-005); a Short's YouTube flag stays the page's `ai_generated`.
"""

import fcntl
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

from company_config import integration  # noqa: E402
from kb_lint import parse_front_matter  # noqa: E402
from notion_approvals_sync import read_rows  # noqa: E402

CONFIG = Path("company.json")
MEDIA = Path("workspaces/marketing/media")
LEDGER = Path("workspaces/marketing/staged/scheduled.jsonl")
PAGE = re.compile(r"knowledge/marketing/(founder/([a-z0-9][a-z0-9_.]*))/content/(\d{4})-W(\d{2})/([a-z0-9][a-z0-9-]*)\.md")
ITEM_ID = re.compile(r"(\d{4})-w(\d{2})-([a-z0-9][a-z0-9_.]*)-([a-z0-9][a-z0-9-]*)")
FILE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}\.(png|jpg|jpeg|mp4)")
TOKEN = re.compile(r"[A-Za-z0-9_.~-]+")
SHA256 = re.compile(r"[0-9a-f]{64}")
IMAGES, VIDEOS = (".png", ".jpg", ".jpeg"), (".mp4",)
TYPES = {"image": "POST", "carousel": "POST", "reel": "REEL"}  # Instagram's
SHORT = "short"  # YouTube's
SHORT_PRIVACY = "private"  # Metricool may ignore autoPublish false for a Short
MIN_AHEAD, MAX_AHEAD = timedelta(hours=2), timedelta(days=6)
CAPTION_MAX, HASHTAGS_MAX = 2200, 30  # Instagram's limits
# YouTube's: 100 characters, 5,000 UTF-8 bytes, no < or > in either. A refusal burns the ledger line, a cut changes approved text
TITLE_MAX, DESCRIPTION_MAX = 100, 5000
SF_DATALESS = 0x40000000  # macOS: a cloud drive's file whose bytes aren't on this computer


class Refused(Exception):
    pass


@dataclass
class Piece:
    page: str  # repo-relative
    brand: str  # founder/demo
    account: str  # demo
    week: str  # 2026-W05
    slug: str
    ai_generated: bool
    caption: str
    type: str  # image | carousel | reel | short
    publish_at: datetime
    files: list  # [(label, name, sha256)]: labels "1".."n", then an optional "cover"
    title: "str | None" = None  # a short's YouTube title
    ai_label: bool = False  # Instagram's AI label: the Board's choice in Notion (SA-005), off unless ticked

    @property
    def item_id(self) -> str:
        return f"{self.week.lower()}-{self.account}-{self.slug}"

    @property
    def folder(self) -> Path:
        return MEDIA / self.brand / self.week / self.slug


def _section(lines: list, heading: str) -> list:
    """The lines under `## heading`, up to the next `## `."""
    try:
        start = lines.index(f"## {heading}") + 1
    except ValueError:
        raise Refused(f"no '## {heading}' section")
    end = next((i for i in range(start, len(lines)) if lines[i].startswith("## ")), len(lines))
    return lines[start:end]


def read_piece(page: str, root: Path = ROOT) -> Piece:
    """Parse a piece page; raises Refused when it isn't a well-formed post."""
    match = PAGE.fullmatch(page)
    if not match:
        raise Refused(f"{page} isn't a founder piece page (knowledge/marketing/founder/<account>/content/<week>/<slug>.md)")
    brand, account, year, week, slug = match.groups()
    lines = (root / page).read_text(encoding="utf-8").split("\n")  # not splitlines(): U+2028 isn't a line here
    for heading in ("## Caption", "## Post"):
        if lines.count(heading) != 1:
            raise Refused(f"the page needs exactly one '{heading}' heading")
    fields, _, _ = parse_front_matter(lines) or ({}, None, None)
    if fields.get("brand") != brand or fields.get("week") != f"{year}-W{week}":
        raise Refused("the front matter's brand and week don't match the page's folder")
    if fields.get("ai_generated") not in ("true", "false"):
        raise Refused("ai_generated must be true or false")
    caption = _section(lines, "Caption")
    fences = [i for i, line in enumerate(caption) if line.startswith("```")]
    if len(fences) != 2:
        raise Refused("'## Caption' must hold exactly one fenced block")
    if any("<!--" in line for line in caption + _section(lines, "Post")):
        raise Refused("no HTML comments in '## Caption' or '## Post': the Board must see what is posted")
    post_type = publish_at = title = None
    files = []
    for line in _section(lines, "Post"):
        if line.startswith("- Type: "):
            post_type = line[len("- Type: "):].strip()
        elif line.startswith("- Publish at: "):
            publish_at = line[len("- Publish at: "):].strip()
        elif line.startswith("- Title: "):
            if title is not None:
                raise Refused("the page needs at most one '- Title:' line")
            title = line[len("- Title: "):].strip()
        elif line.startswith("| ") and not line.startswith(("| #", "|---")):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) != 3:
                raise Refused(f"a '## Post' table row needs #, File and SHA-256: {line}")
            files.append(tuple(cells))
    if post_type not in (*TYPES, SHORT):
        raise Refused(f"'- Type:' must be one of {', '.join((*TYPES, SHORT))}")
    if (fields.get("format") == SHORT) != (post_type == SHORT):
        raise Refused("'format: short' and '- Type: short' go together: a short never goes to Instagram, a reel never to YouTube")
    if post_type == SHORT and (load_config(root)["brands"].get(brand) or {}).get("shorts") is not True:
        raise Refused(f"{brand} has no Shorts (company.json: \"shorts\")")
    if bool(title) != (post_type == SHORT):
        raise Refused("a short needs '- Title:', its YouTube title, and only a short has one")
    if title and (len(title) > TITLE_MAX or "<" in title or ">" in title or not title.isprintable()):
        raise Refused(f"'- Title:' must be {TITLE_MAX} characters or fewer, with no < or > and no control characters")
    text = "\n".join(caption[fences[0] + 1:fences[1]])
    if post_type == SHORT and (len(text.encode("utf-8")) > DESCRIPTION_MAX or "<" in text or ">" in text):
        raise Refused(f"a short's caption is its YouTube description: {DESCRIPTION_MAX} bytes of UTF-8 or fewer, with no < or >")
    try:
        when = datetime.fromisoformat(publish_at or "")
    except ValueError:
        raise Refused("'- Publish at:' must be an ISO 8601 time with its UTC offset, e.g. 2026-01-08T19:00+01:00")
    if when.tzinfo is None:
        raise Refused("'- Publish at:' needs its UTC offset")
    return Piece(page, brand, account, f"{year}-W{week}", slug, fields["ai_generated"] == "true",
                 text, post_type, when, files, title, [row["ai_label"] for row in approval_rows(page, root)] == ["on"])


def shape_reasons(piece: Piece) -> list:
    """What's wrong with the piece's shape, from the page alone."""
    reasons = []
    media = [f for f in piece.files if f[0] != "cover"]
    cover = [f for f in piece.files if f[0] == "cover"]
    if [f[0] for f in media] != [str(i) for i in range(1, len(media) + 1)] or piece.files[len(media):] != cover:
        reasons.append("the '## Post' rows must be numbered 1, 2, … in order, with an optional 'cover' row last")
    for label, name, sha in piece.files:
        if not FILE_NAME.fullmatch(name):
            reasons.append(f"row {label}: '{name}' must be a plain file name ending .png, .jpg, .jpeg or .mp4")
        if not SHA256.fullmatch(sha):
            reasons.append(f"row {label}: no SHA-256; run tools/marketing/publish/post_hashes.py on the page")
    kinds = [Path(name).suffix.lower() for _, name, _ in media]
    if piece.type == "image" and (len(media) != 1 or kinds[0] not in IMAGES):
        reasons.append("an image post has exactly one .png or .jpg")
    if piece.type == "carousel" and not 2 <= len(media) <= 10:
        reasons.append("a carousel has 2 to 10 files")
    if piece.type in ("reel", SHORT) and (len(media) != 1 or kinds[0] not in VIDEOS):
        reasons.append(f"a {piece.type} has exactly one .mp4")
    if cover and (piece.type != "reel" or Path(cover[0][1]).suffix.lower() not in IMAGES):
        reasons.append("only a reel has a cover, a .png or .jpg")
    if piece.type != SHORT and len(piece.caption) > CAPTION_MAX:
        reasons.append(f"the caption is {len(piece.caption)} characters; Instagram's limit is {CAPTION_MAX}")
    if len(re.findall(r"#\w", piece.caption)) > HASHTAGS_MAX:
        reasons.append(f"the caption has more than {HASHTAGS_MAX} hashtags")
    return reasons


def time_reason(piece: Piece, now: datetime) -> "str | None":
    ahead = piece.publish_at - now
    if not MIN_AHEAD <= ahead <= MAX_AHEAD:
        return "Publish at must be 2 hours to 6 days ahead"
    return None


def load_config(root: Path = ROOT) -> dict:
    """company.json's "b2" and "brands" ("integrations"."marketing"). A file that can't be parsed raises."""
    settings = integration("marketing", root) or {}
    return {"b2": settings.get("b2") or {}, "brands": settings.get("brands") or {}}


def config_reasons(piece: Piece, config: dict) -> list:
    brand = config["brands"].get(piece.brand) or {}
    missing = [k for k in ("metricool_blog_id", "timezone") if not brand.get(k)]
    missing += [f"b2.{k}" for k in ("bucket", "download_host") if not config["b2"].get(k)]
    return [f"TODO(board): {CONFIG.as_posix()} has no {', '.join(missing)} for {piece.brand}"] if missing else []


def page_sha256(piece: Piece, root: Path) -> str:
    return hashlib.sha256((root / piece.page).read_bytes()).hexdigest()


def approval_rows(page: str, root: Path) -> list:
    """The approvals rows, synced from Notion, that point at this page."""
    return [row for approvals in sorted((root / "knowledge/marketing").glob("**/approvals/*.md"))
            for row in read_rows(approvals) if row["kb_page"] == page]


def approval_reason(piece: Piece, root: Path) -> "str | None":
    """None if exactly one Board decision covers this page: Approved, with no note, on the page as it is now."""
    rows = approval_rows(piece.page, root)
    if len(rows) != 1:
        return f"{len(rows)} approvals rows point at this page; publishing needs exactly one"
    row = rows[0]
    if row["approval"] != "Approved":
        return f"the Board's decision is '{row['approval']}', not Approved"
    if row["note"]:
        return f"the approvals row has a note ({row['note']}): the Board decides again after the cmo's sync"
    if row["kb_sha256"] != page_sha256(piece, root):
        return "the page changed after the Board's decision"
    return None


def file_path(piece: Piece, name: str, root: Path) -> Path:
    """The media file, links resolved, which must stay inside the piece's real folder."""
    folder = (root / piece.folder).resolve()
    path = (folder / name).resolve()
    if path.parent != folder or not path.is_file():
        raise Refused(f"{name} isn't a file in {piece.folder}")
    if getattr(os.stat(path), "st_flags", 0) & SF_DATALESS:
        raise Refused(f"{name} is in a cloud drive but not on this computer; download it first")
    return path


def file_reasons(piece: Piece, root: Path) -> list:
    reasons = []
    for label, name, sha in piece.files:
        try:
            if hashlib.sha256(file_path(piece, name, root).read_bytes()).hexdigest() != sha:
                reasons.append(f"{name} changed after its hash went on the page")
        except Refused as refused:
            reasons.append(str(refused))
    return reasons


def reasons(piece: Piece, root: Path, now: datetime, config: dict) -> list:
    """Every reason not to post this piece, cheapest checks first."""
    found = shape_reasons(piece) + [r for r in [time_reason(piece, now)] if r] + config_reasons(piece, config)
    if found:
        return found
    approval = approval_reason(piece, root)
    return [approval] if approval else file_reasons(piece, root)


def object_name(piece: Piece, name: str, sha: str) -> str:
    return f"posts/{piece.item_id}/{sha}-{name}"


def base_url(piece: Piece, config: dict, name: str, sha: str) -> str:
    return f"{config['b2']['download_host']}/file/{config['b2']['bucket']}/{quote(object_name(piece, name, sha))}"


def build_args(piece: Piece, config: dict, token: "str | None") -> dict:
    """The exact createScheduledPost arguments. token=None gives the URLs without their Authorization."""
    def url(name, sha):
        return base_url(piece, config, name, sha) + (f"?Authorization={token}" if token is not None else "")
    brand = config["brands"][piece.brand]
    local = piece.publish_at.astimezone(ZoneInfo(brand["timezone"]))
    short = piece.type == SHORT
    info = {
        "autoPublish": False,
        "draft": False,
        "text": piece.caption,
        "media": [url(name, sha) for label, name, sha in piece.files if label != "cover"],
        "providers": [{"network": "youtube" if short else "instagram"}],
        "publicationDate": {"dateTime": local.strftime("%Y-%m-%dT%H:%M:%S"), "timezone": brand["timezone"]},
    }
    if short:
        info["youtubeData"] = {"title": piece.title, "type": "short", "privacy": SHORT_PRIVACY, "madeForKids": False,
                               "isAiGeneratedContent": piece.ai_generated}
    else:
        info["instagramData"] = {"type": TYPES[piece.type], "isAiGenerated": piece.ai_label}
    info.update({"videoThumbnailUrl": url(name, sha) for label, name, sha in piece.files if label == "cover"})
    return {"blogId": str(brand["metricool_blog_id"]), "date": local.isoformat(timespec="seconds"),
            "info": json.dumps(info, ensure_ascii=False)}


def _no_duplicates(pairs: list) -> dict:
    keys = [k for k, _ in pairs]
    if len(keys) != len(set(keys)):
        raise ValueError("a key appears twice")
    return dict(pairs)


def schedule_reason(tool_input, root: Path = ROOT, now: "datetime | None" = None) -> "str | None":
    """The hook's check of a createScheduledPost call: None (and the item goes in the ledger) or why it's refused.

    The call must equal, string for string, what build_args makes from the approved page with the call's one
    B2 token: Metricool gets exactly the bytes checked here."""
    now = now or datetime.now(timezone.utc)
    if not isinstance(tool_input, dict) or set(tool_input) != {"blogId", "date", "info"}:
        return "the arguments must be exactly blogId, date and info, as stage_item.py printed them"
    try:
        info = json.loads(tool_input["info"], object_pairs_hook=_no_duplicates) \
            if isinstance(tool_input["info"], str) else None
    except ValueError:
        info = None
    if not isinstance(info, dict):
        return "info must be the JSON string stage_item.py printed, with no key twice"
    if info.get("autoPublish") is not False:
        return "autoPublish must be false: the Board publishes each Instagram post himself in Metricool's app"
    media = info.get("media")
    first = media[0] if isinstance(media, list) and media and isinstance(media[0], str) else ""
    item = re.search(r"/posts/([^/?#]+)/", first)
    match = ITEM_ID.fullmatch(item.group(1)) if item else None
    token = first.partition("?Authorization=")[2]
    if not match or not TOKEN.fullmatch(token):
        return "the media URLs aren't stage_item.py's"
    year, week, account, slug = match.groups()
    try:
        piece = read_piece(f"knowledge/marketing/founder/{account}/content/{year}-W{week}/{slug}.md", root)
        config = load_config(root)
        found = reasons(piece, root, now, config)
        if found:
            return "; ".join(found)
        if tool_input != build_args(piece, config, token):
            return ("the arguments differ from what the approved page builds; pass stage_item.py's output "
                    "unchanged")
    except Refused as refused:
        return str(refused)
    except (OSError, ValueError, KeyError, TypeError) as error:
        return f"couldn't check the post ({type(error).__name__}: {error})"
    ledger = root / LEDGER
    ledger.parent.mkdir(parents=True, exist_ok=True)
    with ledger.open("a+", encoding="utf-8") as log:
        fcntl.flock(log, fcntl.LOCK_EX)  # the check and the append as one step, across sessions
        log.seek(0)
        if any(json.loads(line).get("item_id") == piece.item_id for line in log.read().splitlines() if line.strip()):
            return (f"{piece.item_id} was already scheduled once ({LEDGER.as_posix()}). If that call failed, the "
                    "CEO has its line removed")
        log.write(json.dumps({"item_id": piece.item_id, "kb_page": piece.page, "at": now.isoformat(timespec="seconds")})
                  + "\n")
    return None
