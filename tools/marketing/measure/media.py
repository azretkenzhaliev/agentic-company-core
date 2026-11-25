"""The pieces in a folder, and their pixels and sound: ffmpeg (the repo's ffmpeg-static) for video, Pillow for images.

ffmpeg reads only local files (-protocol_whitelist file) through the mov demuxer, as reels/watch.py does. numpy and
Pillow load only when pixels are needed, so discovery and probing run on the standard library.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
FFMPEG = ROOT / "tools" / "marketing" / "node_modules" / "ffmpeg-static" / "ffmpeg"
FFMPEG_SECONDS = 600
MAX_SECONDS = 600
VIDEO_EXT = {".mp4", ".mov", ".m4v"}
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp"}
KINDS = {"reel", "carousel", "post", "story"}
STORY_ASPECT = 0.6

DURATION_LINE = re.compile(r"^  Duration: (\d+):(\d\d):(\d\d(?:\.\d+)?)", re.M)
AUDIO_LINE = re.compile(r"^  Stream #.*: Audio: ", re.M)
VIDEO_LINE = re.compile(r"^  Stream #.*: Video: (.*)$", re.M)
SIZE = re.compile(r"(?:^|, )(\d{2,5})x(\d{2,5})(?=[ ,\[]|$)")
FPS = re.compile(r"([\d.]+) fps")
ROTATION = re.compile(r"rotation of (-?[\d.]+) degrees")


class MediaError(Exception):
    pass


def run_ffmpeg(source: Path, *args: str) -> subprocess.CompletedProcess:
    """Bytes out (frames, samples); stderr is what ffmpeg says about the file."""
    try:
        return subprocess.run([str(FFMPEG), "-hide_banner", "-nostdin", "-protocol_whitelist", "file", "-f", "mov",
                               "-i", str(source), *args], capture_output=True, timeout=FFMPEG_SECONDS)
    except (OSError, subprocess.SubprocessError) as error:
        raise MediaError(f"ffmpeg: {error}") from None


def ffmpeg_ok(source: Path, *args: str) -> subprocess.CompletedProcess:
    result = run_ffmpeg(source, *args)
    if result.returncode != 0:
        raise MediaError(f"ffmpeg failed: {result.stderr.decode('utf-8', 'replace').strip()[-200:]}")
    return result


def parse_probe(stderr: str) -> dict:
    """Length, display size (rotation applied, as ffmpeg's frames are), frame rate and whether there's sound."""
    found = {"seconds": None, "width": None, "height": None, "fps": None, "has_audio": bool(AUDIO_LINE.search(stderr))}
    duration = DURATION_LINE.search(stderr)
    if duration:
        hours, minutes, seconds = duration.groups()
        found["seconds"] = round(int(hours) * 3600 + int(minutes) * 60 + float(seconds), 3)
    video = VIDEO_LINE.search(stderr)
    if video:
        size = SIZE.search(video.group(1))
        if size:
            found["width"], found["height"] = int(size.group(1)), int(size.group(2))
        fps = FPS.search(video.group(1))
        if fps:
            found["fps"] = float(fps.group(1))
    rotation = ROTATION.search(stderr)
    if rotation and found["width"] and abs(round(float(rotation.group(1)))) % 180 == 90:
        found["width"], found["height"] = found["height"], found["width"]
    return found


def probe(video: Path) -> dict:
    """parse_probe's numbers; past MAX_SECONDS, `seconds` is what's decoded (every rate uses it) and full_seconds the
    file's own length."""
    info = parse_probe(run_ffmpeg(video).stderr.decode("utf-8", "replace"))
    if not info["seconds"] or not info["width"]:
        raise MediaError("ffmpeg found no video stream or no length")
    if info["seconds"] > MAX_SECONDS:
        info.update(full_seconds=info["seconds"], seconds=float(MAX_SECONDS), truncated=True)
    return info


def scaled_size(width: int, height: int, target: int) -> tuple:
    """At most `target` wide, never upscaled, both sides even."""
    if width > target:
        width, height = target, round(height * target / width)
    return max(2, width - width % 2), max(2, height - height % 2)


def video_frames(video: Path, size: tuple, fps: float | None = None, max_frames: int | None = None,
                 flags: str | None = "area"):
    """RGB frames as a uint8 array (n, height, width, 3). fps None keeps every frame; flags None is ffmpeg's default
    scaler (bicubic), which TransNetV2 was trained on."""
    import numpy as np

    width, height = size
    scale = f"scale={width}:{height}" + (f":flags={flags}" if flags else "")
    chain = f"fps={fps},{scale}" if fps else scale
    args = ["-map", "0:v:0", "-an", "-t", str(MAX_SECONDS), "-vf", chain]
    if max_frames:
        args += ["-frames:v", str(max_frames)]
    stdout = ffmpeg_ok(video, *args, "-f", "rawvideo", "-pix_fmt", "rgb24", "-").stdout
    frame = width * height * 3
    count = len(stdout) // frame
    return np.frombuffer(stdout[:count * frame], dtype=np.uint8).reshape(count, height, width, 3)


def audio_samples(video: Path):
    """Mono float32 at 16 kHz, the first MAX_SECONDS."""
    import numpy as np

    stdout = ffmpeg_ok(video, "-vn", "-map", "0:a:0", "-t", str(MAX_SECONDS), "-ac", "1", "-ar", "16000",
                       "-f", "f32le", "-").stdout
    return np.frombuffer(stdout[:len(stdout) // 4 * 4], dtype=np.float32).copy()


def image_rgb(path: Path, width: int | None = 540):
    """(RGB uint8 array, its width at most `width`; (original width, height)) with the EXIF rotation applied."""
    import numpy as np
    from PIL import Image, ImageOps

    with Image.open(path) as opened:
        image = ImageOps.exif_transpose(opened).convert("RGB")
    original = image.size
    if width and image.width > width:
        image = image.resize((width, max(1, round(image.height * width / image.width))), Image.Resampling.BOX)
    return np.asarray(image), original


def image_size(path: Path) -> tuple:
    from PIL import Image, ImageOps

    with Image.open(path) as opened:
        return ImageOps.exif_transpose(opened).size


def kind_for(kind: str | None, width: int | None, height: int | None) -> str | None:
    """A lone image is a story when it's tall (9:16 is 0.5625), a post otherwise."""
    if kind or not width or not height:
        return kind
    return "story" if width / height <= STORY_ASPECT else "post"


def read_text(path: Path) -> str | None:
    return path.read_text(encoding="utf-8", errors="replace").strip() if path.is_file() else None


def plain_file(folder: Path, name) -> Path | None:
    """A file named in a manifest: a bare name, a regular file, no link."""
    if not isinstance(name, str) or not name or Path(name).name != name or name.startswith("."):
        return None
    path = folder / name
    return path if path.is_file() and not path.is_symlink() else None


def piece(name: str, kind: str | None, video: Path | None = None, images: list | None = None,
          caption: str | None = None, video_slides: int = 0) -> dict:
    return {"name": name, "kind": kind, "video": video, "images": images or [], "caption": caption,
            "video_slides": video_slides}


def from_manifest(folder: Path) -> dict | None:
    try:
        manifest = json.loads((folder / "MANIFEST.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(manifest, dict) or manifest.get("kind") not in KINDS:
        return None
    slides = manifest.get("slides") or []
    if not isinstance(slides, list):
        return None
    images, video, video_slides = [], None, 0
    for slide in slides:
        if not isinstance(slide, dict):
            continue
        path = plain_file(folder, slide.get("file"))
        if slide.get("type") == "video":
            video_slides += 1
            if path and video is None and manifest["kind"] == "reel":
                video = path
        elif slide.get("type") == "image" and path and path.suffix.lower() in IMAGE_EXT:
            images.append(path)
    if not images and not video:
        cover = plain_file(folder, manifest.get("cover"))
        images = [cover] if cover and cover.suffix.lower() in IMAGE_EXT else []
    if not images and not video:
        return None
    description = manifest.get("description")
    return piece(folder.name, manifest["kind"], video, images, description if isinstance(description, str) else None,
                 video_slides)


def from_folder(folder: Path) -> dict | None:
    video = folder / "video.mp4"
    if video.is_file() and not video.is_symlink():
        caption = read_text(folder / "caption.txt")
        if caption is None:
            try:
                info = json.loads((folder / "video.info.json").read_text(encoding="utf-8"))
                caption = info.get("description") if isinstance(info, dict) else None
            except (OSError, ValueError):
                caption = None
        return piece(folder.name, "reel", video, caption=caption if isinstance(caption, str) else None)
    if (folder / "MANIFEST.json").is_file():
        return from_manifest(folder)
    images = sorted(path for path in folder.iterdir() if path.suffix.lower() in IMAGE_EXT and path.is_file()
                    and not path.is_symlink() and not path.name.startswith("."))
    if not images:
        return None
    return piece(folder.name, "carousel" if len(images) > 1 else None, images=images,
                 caption=read_text(folder / "caption.txt"))


def discover(folder: Path) -> tuple:
    """(pieces, skipped) among the folder's direct children: a reel folder (video.mp4), a post folder (MANIFEST.json),
    a folder of images (a carousel, or one image), a video file, or an image file. A caption is caption.txt in a
    folder, or <stem>.txt beside a file."""
    pieces, skipped = [], []
    children = sorted(path for path in Path(folder).iterdir() if not path.name.startswith("."))
    captions = {path.stem for path in children if path.suffix.lower() in VIDEO_EXT | IMAGE_EXT}
    for path in children:
        try:
            if path.is_symlink():
                skipped.append({"name": path.name, "reason": "a link"})
            elif path.is_dir():
                found = from_folder(path)
                if found:
                    pieces.append(found)
                else:
                    skipped.append({"name": path.name, "reason": "nothing to measure"})
            elif path.suffix.lower() in VIDEO_EXT:
                pieces.append(piece(path.name, "reel", video=path, caption=read_text(path.with_suffix(".txt"))))
            elif path.suffix.lower() in IMAGE_EXT:
                pieces.append(piece(path.name, None, images=[path], caption=read_text(path.with_suffix(".txt"))))
            elif not (path.suffix.lower() == ".txt" and path.stem in captions):
                skipped.append({"name": path.name, "reason": "not a video, an image or a piece folder"})
        except (OSError, ValueError, TypeError, AttributeError) as error:  # an odd folder or manifest: the rest go on
            skipped.append({"name": path.name,
                            "reason": f"couldn't be read: {type(error).__name__}: {' '.join(str(error).split())}"[:200]})
    return pieces, skipped
