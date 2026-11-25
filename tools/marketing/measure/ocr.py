"""On-screen text: how much of the frame text covers, where it sits, and what survives the grid.

Frames: a reel's every 2 s (at most 20), a carousel's slides, at 720 px wide, as PNGs in a folder of the run that is
deleted afterwards. The reader is Tesseract, its traineddata only from the models folder, named and pinned by hash in
models.json ("tesseract-script"), or Apple Vision on a Mac (vision_ocr.js). Boxes go on a 100 x 100 grid of the frame,
so overlapping words count once.
- text area: the share of the frame under text, per frame (median, max) and on the cover (the first frame or slide);
- grid crop: the share of the cover's text outside Instagram's 3:4 centre crop of the profile grid;
- safe zone (tall frames, 9:16): the share of frames with text that put some in the top 250 or bottom 340 px of 1920,
  where Instagram's interface sits (our template convention: the reel-script and story-sequence skills);
- language: of all the text read, by caption.language_of. The text itself is never kept.
Measure the reader on your own letters before you trust it: some readers fold special letters into plain ones.
"""

from __future__ import annotations

import csv
import io
import json
import shutil
import statistics
import subprocess
import tempfile
from pathlib import Path

from . import caption, media, models

TESSERACT = shutil.which("tesseract") or shutil.which("tesseract", path="/opt/homebrew/bin")
OSASCRIPT = "/usr/bin/osascript"
VISION_JS = Path(__file__).resolve().with_name("vision_ocr.js")
TESSERACT_MODEL = "tesseract-script"  # models.json: <models dir>/tesseract-script/<its one file>
VISION_LANGUAGES = "en-US"
ENGINES = ("tesseract", "vision")
FRAMES_PER_SECOND = 0.5
MAX_FRAMES = 20
WIDTH = 720
CONFIDENCE = 70  # Tesseract's, as reels/watch.py
MIN_WORD = 4  # a line needs one real word this long (reels/watch.py)
GRID = 100
GRID_ASPECT = 3 / 4
TALL_ASPECT = 0.6
SAFE_TOP = 250 / 1920
SAFE_BOTTOM = 340 / 1920
READ_SECONDS = 60


class OcrError(Exception):
    pass


def real_line(text: str) -> bool:
    return any(len(word) >= MIN_WORD and word.isalpha() for word in text.split())


def number(text) -> float:
    try:
        return float(text)
    except (TypeError, ValueError):
        return -1.0


def tesseract_boxes(tsv: str) -> list:
    """[(text, (x, y, w, h))] per kept line from Tesseract's tsv: words at CONFIDENCE or more, lines with a real word;
    each box a share of the page."""
    rows = list(csv.DictReader(io.StringIO(tsv), delimiter="\t", quoting=csv.QUOTE_NONE))
    page = next((row for row in rows if row.get("level") == "1"), None)
    width, height = (number(page.get("width")), number(page.get("height"))) if page else (0, 0)
    if width <= 0 or height <= 0:
        return []
    lines: dict = {}
    for row in rows:
        word = (row.get("text") or "").strip()
        if row.get("level") == "5" and word and number(row.get("conf")) >= CONFIDENCE:
            lines.setdefault((row.get("block_num"), row.get("par_num"), row.get("line_num")), []).append(row)
    found = []
    for words in lines.values():
        text = " ".join(row["text"].strip() for row in words)
        if not real_line(text):
            continue
        for row in words:
            box = (number(row["left"]) / width, number(row["top"]) / height, number(row["width"]) / width,
                   number(row["height"]) / height)
            found.append((row["text"].strip(), box))
    return found


def tesseract_language() -> str:
    """The traineddata models.json names, e.g. script/Latin."""
    [file] = models.catalogue()[TESSERACT_MODEL]["files"]
    return file.removesuffix(".traineddata")


def vision_languages() -> str:
    """Vision's language codes (company.json: each language's "vision"), comma-separated."""
    found = (caption.integration("marketing", caption.ROOT) or {}).get("languages") or {}
    return ",".join(language["vision"] for language in found.values() if language.get("vision")) or VISION_LANGUAGES


def read_tesseract(images: list, tessdata: Path, psm: str = "11") -> list:
    """Per image, [(text, box)], with the traineddata in `tessdata` only (models.locate checked it); OcrError when
    Tesseract is missing or fails (never the same as no text). TSV by -c: the `tsv` config file isn't in that folder."""
    if not TESSERACT:
        raise OcrError("tesseract isn't installed")
    out, language = [], tesseract_language()
    for image in images:
        try:
            read = subprocess.run([TESSERACT, str(image), "-", "--tessdata-dir", str(tessdata), "-l", language,
                                   "--psm", psm, "-c", "tessedit_create_tsv=1"], capture_output=True,
                                  encoding="utf-8", errors="replace", timeout=READ_SECONDS)
        except (OSError, subprocess.SubprocessError) as error:
            raise OcrError(f"tesseract: {error}") from None
        if read.returncode != 0:
            raise OcrError(f"tesseract failed: {' '.join(read.stderr.split())[-200:]}")
        out.append(tesseract_boxes(read.stdout))
    return out


def vision_items(images: list, correct: bool = True) -> list:
    """Per image, Vision's [{text, conf, box}]; OcrError when osascript fails or an image can't be read."""
    if not images:
        return []
    try:
        read = subprocess.run([OSASCRIPT, "-l", "JavaScript", str(VISION_JS), vision_languages(),
                               "correct" if correct else "plain", *map(str, images)],
                              capture_output=True, encoding="utf-8", errors="replace",
                              timeout=READ_SECONDS + 5 * len(images))
    except (OSError, subprocess.SubprocessError) as error:
        raise OcrError(f"vision: {error}") from None
    if read.returncode != 0:
        raise OcrError(f"vision failed: {' '.join(read.stderr.split())[-200:]}")
    try:
        results = [json.loads(line) for line in read.stdout.splitlines() if line.strip()]
    except ValueError:
        raise OcrError("vision's output isn't JSON lines") from None
    if len(results) != len(images) or not all(result.get("ok") for result in results):
        raise OcrError("vision didn't read every image")
    return [result["items"] for result in results]


def read_vision(images: list) -> list:
    return [[(item["text"], tuple(item["box"])) for item in items if real_line(item["text"])]
            for items in vision_items(images)]


def cells(boxes: list) -> set:
    """The grid cells a frame's boxes cover."""
    covered = set()
    for x, y, w, h in boxes:
        left, top = max(0, int(x * GRID)), max(0, int(y * GRID))
        right, bottom = min(GRID, -int(-(x + w) * GRID // 1)), min(GRID, -int(-(y + h) * GRID // 1))
        covered.update((column, row) for column in range(left, right) for row in range(top, bottom))
    return covered


def grid_keep(aspect: float) -> tuple:
    """(left, top, right, bottom) of the 3:4 centre crop, as shares of a frame of this width / height."""
    if aspect > GRID_ASPECT:
        side = (1 - GRID_ASPECT / aspect) / 2
        return side, 0.0, 1 - side, 1.0
    side = (1 - aspect / GRID_ASPECT) / 2
    return 0.0, side, 1.0, 1 - side


def outside_share(covered: set, keep: tuple) -> float | None:
    """The share of the covered cells whose centre is outside `keep`."""
    if not covered:
        return None
    left, top, right, bottom = keep
    out = sum(1 for column, row in covered
              if not (left <= (column + 0.5) / GRID <= right and top <= (row + 0.5) / GRID <= bottom))
    return out / len(covered)


def in_unsafe(covered: set) -> bool:
    return any((row + 0.5) / GRID < SAFE_TOP or (row + 0.5) / GRID > 1 - SAFE_BOTTOM for _, row in covered)


def features(frames: list, aspect: float | None, engine: str) -> dict:
    """frames: per frame, [(text, box)], the cover first."""
    if not frames:
        return {"status": "none"}
    covered = [cells([box for _, box in found]) for found in frames]
    areas = [len(frame) / GRID ** 2 for frame in covered]
    chars = [sum(len(text) for text, _ in found) for found in frames]
    with_text = [frame for frame in covered if frame]
    out = {
        "status": "ok",
        "engine": engine,
        "frames": len(frames),
        "frames_with_text_share": round(len(with_text) / len(frames), 4),
        "text_area_median": round(statistics.median(areas), 4),
        "text_area_max": round(max(areas), 4),
        "chars_median": statistics.median(chars),
        "cover_text_area": round(areas[0], 4),
        "cover_chars": chars[0],
        "cover_grid_cut_share": None,
        "safe_zone_hit_share": None,
        "language": caption.language_of(" ".join(text for found in frames for text, _ in found)),
    }
    if aspect:
        cut = outside_share(covered[0], grid_keep(aspect))
        out["cover_grid_cut_share"] = round(cut, 4) if cut is not None else None
        if aspect <= TALL_ASPECT and with_text:
            out["safe_zone_hit_share"] = round(sum(1 for frame in with_text if in_unsafe(frame)) / len(with_text), 4)
    return out


def frames_of(item: dict, info: dict, folder: Path) -> list:
    """PNGs in `folder`: a reel's frames every 2 s (at most MAX_FRAMES), else the slides, 720 px wide at most."""
    if item["video"]:
        rate = min(FRAMES_PER_SECOND, MAX_FRAMES / max(info["seconds"], 1))
        media.ffmpeg_ok(item["video"], "-map", "0:v:0", "-an", "-t", str(media.MAX_SECONDS), "-vf",
                        f"fps={rate:.5f},scale='min({WIDTH},iw)':-2", "-frames:v", str(MAX_FRAMES),
                        "-f", "image2", "-y", str(folder / "f-%04d.png"))
        return sorted(folder.glob("f-*.png"))
    from PIL import Image

    out = []
    for index, path in enumerate(item["images"][:MAX_FRAMES]):
        rgb, _ = media.image_rgb(path, WIDTH)
        target = folder / f"s-{index:04d}.png"
        Image.fromarray(rgb).save(target)
        out.append(target)
    return out


def measure(item: dict, info: dict, engine: str, scratch: Path, tessdata: Path | None = None) -> dict:
    """One piece's text numbers; its frames live in a fresh folder under `scratch` only while they're read. Tesseract
    needs `tessdata`, the checked tesseract-script folder."""
    if engine != "vision" and tessdata is None:
        raise OcrError(f"{TESSERACT_MODEL} isn't located")
    folder = Path(tempfile.mkdtemp(prefix=".ocr-", dir=scratch))
    try:
        images = frames_of(item, info, folder)
        found = read_vision(images) if engine == "vision" else read_tesseract(images, tessdata)
    finally:
        shutil.rmtree(folder, ignore_errors=True)
    aspect = info["width"] / info["height"] if info.get("width") and info.get("height") else None
    return features(found, aspect, engine)
