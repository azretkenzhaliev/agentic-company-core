#!/usr/bin/env python3
"""Measure a folder of pieces, ours or a reference page's, so a taste profile can be checked against real ones.

    workspaces/system/venvs/measure/bin/python tools/marketing/measure/run.py run --in <folder> --page <page> --out <new folder>
        [--format <format>] [--models <folder>] [--ocr tesseract|vision] [--speech auto|<language code>]
    ... run.py summary  --runs <run folder> [<run folder> ...] --out <new file>.json
    ... run.py check    [--models <folder>]

- **Pieces** are the folder's direct children (media.discover): a reel folder (video.mp4, as reels/ downloads it), a
  post folder (MANIFEST.json), a folder of images (a carousel), a video file or an image file, each with its caption.
- **Out:** a new folder: pieces/<piece>.json, one feature file a piece (rewritten after each stage, so a stopped run
  keeps what it measured), and summary.json: per page and format each number's median, P10 and P90, and each embedding
  model's centroid. `summary` pools several runs. The format is the piece's kind unless --format names it.
- **Only numbers and vectors are kept:** no transcript, no on-screen text, no frame. OCR frames sit in a folder of the
  run while they're read, then go.
- **No network:** before anything loads, the Hugging Face libraries are set offline and this process's internet sockets
  and name lookups are refused. Models load only from the models folder (default workspaces/system/models/measure),
  each file matching its sha256 pinned in models.json (models.py); a missing model skips its stage ("not installed") and
  nothing downloads. ffmpeg opens only local files; Tesseract and Apple Vision read local images.
- **One heavy model at a time:** each stage runs over every piece, then its model is closed before the next one loads
  (a small machine swaps otherwise).
- **A stage that fails on a piece** is in the piece's errors, and the other stages still run.
- **Its own environment:** Python 3.10 or later with numpy and Pillow (requirements.txt says how).
  Everything it reads is untrusted data, so it runs Python isolated (-I).
- --out is a new folder or file whose parent exists; inside the repo, only under workspaces/ (gitignored).
"""

from __future__ import annotations

import os
import sys

if __name__ == "__main__" and not sys.flags.isolated:
    os.execv(sys.executable, [sys.executable, "-I", *sys.argv])

import argparse
import gc
import importlib.util
import json
import math
import re
import socket
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / "tools/marketing")]

from measure import audio, caption, cuts, embed, media, models, ocr, speech, stats  # noqa: E402

SCHEMA = 1
OFFLINE = ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "HF_DATASETS_OFFLINE", "HF_HUB_DISABLE_TELEMETRY")
NETWORK_FAMILIES = (socket.AF_INET, socket.AF_INET6)
ENVIRONMENT = "workspaces/system/venvs/measure"
PAGE = re.compile(r"[\w@.:+-]{1,100}")
ERROR_CHARS = 300
IMPORTS = ("numpy", "PIL", "onnxruntime", "mlx_whisper", "torch")


class Refused(Exception):
    pass


def refuse_network() -> None:
    """Hugging Face offline, and no internet socket or name lookup from this process."""
    for key in OFFLINE:
        os.environ[key] = "1"

    def blocked(*_, **__):
        raise OSError("measure: no network")

    def guard(method):
        def guarded(self, *args, **kwargs):
            if self.family in NETWORK_FAMILIES:
                raise OSError("measure: no network")
            return method(self, *args, **kwargs)
        return guarded

    for name in ("connect", "connect_ex", "sendto", "sendmsg"):
        setattr(socket.socket, name, guard(getattr(socket.socket, name)))
    socket.getaddrinfo = socket.gethostbyname = socket.gethostbyname_ex = blocked


def needs_environment(numpy: bool = True) -> None:
    if sys.version_info < (3, 10):
        raise Refused(f"needs Python 3.10 or later (this is {sys.version.split()[0]}): use {ENVIRONMENT}/bin/python")
    if numpy and importlib.util.find_spec("numpy") is None:
        raise Refused(f"needs numpy: use {ENVIRONMENT}/bin/python (requirements.txt says how to make it)")


def new_path(text: str, root: Path) -> Path:
    """A path that doesn't exist yet, in a folder that does; inside the repo, only under workspaces/."""
    path = Path(text).expanduser()
    if not path.name or path.name in (".", ".."):
        raise Refused(f"--out {text}: name a new folder or file")
    path = path.parent.resolve() / path.name
    if path.exists() or path.is_symlink():
        raise Refused(f"--out {path} exists: name a new one")
    if not path.parent.is_dir():
        raise Refused(f"--out {path}: {path.parent} isn't a folder")
    root = Path(root).resolve()
    if path.is_relative_to(root) and not path.is_relative_to((root / "workspaces").resolve()):
        raise Refused(f"--out {path}: inside the repo, only under workspaces/")
    return path


def message(error: Exception) -> str:
    return f"{type(error).__name__}: {' '.join(str(error).split())}"[:ERROR_CHARS]


def clean(value):
    """JSON without NaN or infinity: such a number is None."""
    if isinstance(value, dict):
        return {key: clean(inner) for key, inner in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(inner) for inner in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def write_json(path: Path, data: dict) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(clean(data), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def file_names(items: list) -> list:
    """A safe, unique file name for each piece."""
    names, seen = [], set()
    for item in items:
        stem = re.sub(r"[^\w.-]", "_", item["name"]).strip(".")[:100] or "piece"
        name, count = stem, 1
        while name.lower() in seen:
            count += 1
            name = f"{stem}-{count}"
        seen.add(name.lower())
        names.append(f"{name}.json")
    return names


def load(name: str, directory: Path, make):
    """(the model, its status): a model whose files aren't all there and pinned never loads."""
    try:
        folder = models.locate(name, directory)
    except models.ModelError as error:
        return None, f"refused: {error}"
    if folder is None:
        return None, f"not installed: {name}"
    try:
        return make(folder), "ok"
    except Exception as error:  # a missing library or a file it can't read: the stage is skipped, the run goes on
        return None, f"error: {name} didn't load: {message(error)}"


def close(model) -> None:
    if model is not None:
        model.close()
    gc.collect()


# ---- the stages ----------------------------------------------------------------------------------------------------

def media_of(row: dict, format_: str | None) -> dict:
    item = row["item"]
    if item["video"]:
        info = media.probe(item["video"])
    else:
        width, height = media.image_size(item["images"][0])
        info = {"seconds": None, "width": width, "height": height, "fps": None, "has_audio": False}
    info["aspect"] = round(info["width"] / info["height"], 4) if info["width"] and info["height"] else None
    kind = media.kind_for(item["kind"], info["width"], info["height"])
    row["features"]["piece"].update(kind=kind, format=format_ or kind)
    row["info"] = info
    return info


def visual_of(row: dict) -> dict:
    from measure import visual

    item, info = row["item"], row["info"]
    if item["video"]:
        frames = media.video_frames(item["video"], media.scaled_size(info["width"], info["height"], visual.WIDTH),
                                    fps=visual.FPS, max_frames=visual.MAX_FRAMES)
        return visual.features(list(frames), motion=True)
    return visual.features([media.image_rgb(path, visual.WIDTH)[0] for path in item["images"]])


def audio_of(row: dict, silero, silero_status: str) -> dict:
    item, info = row["item"], row["info"]
    if not info["has_audio"]:
        row["segments"] = []
        return {"status": "none"}
    samples = media.audio_samples(item["video"])
    seconds = len(samples) / audio.SR
    out = {"status": "ok", "seconds": round(seconds, 2), "loudness": audio.loudness(item["video"]),
           "tempo": audio.tempo(samples)}
    if silero is None:
        out["speech"] = out["pitch"] = {"status": f"not run: {silero_status}"}
        return out
    segments = silero.segments(samples)
    row["segments"] = segments
    out["speech"] = {"status": "ok", "model": "silero-vad", **audio.speech_features(segments, seconds)}
    out["pitch"] = {"status": "ok", **audio.pitch(samples, segments)} if segments else {"status": "none"}
    return out


def cuts_of(row: dict, transnet) -> dict:
    item, info = row["item"], row["info"]
    if transnet is not None:
        return cuts.cut_stats(transnet.cuts(item["video"], info), info["seconds"], "transnetv2")
    return cuts.cut_stats(cuts.ffmpeg_cuts(item["video"], info["seconds"]), info["seconds"], "ffmpeg-scene")


def has_speech(row: dict) -> bool:
    segments = row.get("segments") or []
    return sum(end - start for start, end in segments) >= speech.MIN_SPEECH_SECONDS


def speech_of(row: dict, forced: str, whisper=None) -> dict:
    if not row["info"]["has_audio"]:
        return {"status": "none"}
    if "segments" not in row:
        return {"status": "not run: needs voice activity (silero-vad)"}
    samples = media.audio_samples(row["item"]["video"]) if whisper is not None and has_speech(row) else None
    return speech.measure(samples, row["segments"], row["features"]["caption"].get("language"), forced, whisper)


def embedding_of(row: dict, clip) -> dict:
    units = clip.frame_units(embed.frames_of(row["item"], row["info"]))
    row["units"] = units
    return embed.piece_embedding(units, clip.MODEL)


def run_stage(rows: list, name: str, work, applies=None, otherwise=None) -> None:
    """work(row) for each row it applies to; a failure is the row's, never the run's. Each file is saved after."""
    for row in rows:
        features = row["features"]
        if row.get("info") is None and name != "media":
            features[name] = {"status": "not run: the file couldn't be read"}
        elif applies is not None and not applies(row):
            features[name] = otherwise
        else:
            try:
                features[name] = work(row)
            except Exception as error:  # a damaged or odd file: recorded, and the next piece goes on
                features[name] = {"status": "error"}
                features["errors"][name] = message(error)
        write_json(row["path"], features)


def is_video(row: dict) -> bool:
    return bool(row["item"]["video"])


def speech_pass(rows: list, directory: Path, forced: str, statuses: dict) -> None:
    """Whisper over every piece with speech; a row it didn't load for says why, as the other stages do."""
    model, name = None, speech.Whisper.MODEL
    if any(row.get("info") and is_video(row) and has_speech(row) for row in rows):
        model, statuses[name] = load(name, directory, speech.Whisper)
    else:
        statuses[name] = "not needed: no speech to read"

    def work(row):
        found = speech_of(row, forced, model)
        return {"status": f"not run: {statuses[name]}"} if found["status"].startswith("not installed") else found

    run_stage(rows, "speech", work, is_video, {"status": "n/a"})
    close(model)


def measure_all(rows: list, directory: Path, format_: str | None, engine: str, forced: str, scratch: Path) -> dict:
    """Every stage over every row, one model at a time; the models' statuses."""
    statuses = {}
    run_stage(rows, "media", lambda row: media_of(row, format_))
    run_stage(rows, "visual", visual_of)

    silero, statuses["silero-vad"] = load("silero-vad", directory, audio.Silero)
    run_stage(rows, "audio", lambda row: audio_of(row, silero, statuses["silero-vad"]), is_video, {"status": "n/a"})
    close(silero)

    transnet, statuses["transnetv2"] = load("transnetv2", directory, cuts.TransNet)
    run_stage(rows, "cuts", lambda row: cuts_of(row, transnet), is_video, {"status": "n/a"})
    close(transnet)

    speech_pass(rows, directory, forced, statuses)

    if engine == "vision":
        tessdata, statuses[ocr.TESSERACT_MODEL] = None, "not needed: --ocr vision"
    else:
        tessdata, statuses[ocr.TESSERACT_MODEL] = load(ocr.TESSERACT_MODEL, directory, lambda folder: folder)
    run_stage(rows, "text", lambda row: ocr.measure(row["item"], row["info"], engine, scratch, tessdata),
              lambda row: engine == "vision" or tessdata is not None,
              {"status": f"not run: {statuses[ocr.TESSERACT_MODEL]}"})

    clip, statuses[embed.Clip.MODEL] = load(embed.Clip.MODEL, directory, embed.Clip)
    run_stage(rows, "embedding", lambda row: embedding_of(row, clip), lambda row: clip is not None,
              {"status": f"not run: {statuses[embed.Clip.MODEL]}"})
    close(clip)

    aesthetic, needs = None, f"needs {embed.Clip.MODEL}'s embeddings"
    if any("units" in row for row in rows):
        aesthetic, statuses[embed.Aesthetic.MODEL] = load(embed.Aesthetic.MODEL, directory, embed.Aesthetic)
    else:
        statuses[embed.Aesthetic.MODEL] = f"not run: {needs}"

    def quality(row: dict) -> dict:
        if aesthetic is not None and "units" in row:
            return {"aesthetic": aesthetic.measure(row.pop("units")), "dover": embed.DOVER}
        why = statuses[embed.Aesthetic.MODEL] if aesthetic is None and "units" in row else needs
        return {"aesthetic": {"status": f"not run: {why}"}, "dover": embed.DOVER}

    run_stage(rows, "quality", quality)
    close(aesthetic)
    statuses["dover"] = embed.DOVER["status"]
    return statuses


def summary(features: list, skipped: list, statuses: dict | None = None) -> dict:
    return {"schema": SCHEMA, "pieces": len(features), "groups": stats.summarize(features),
            "centroids": stats.centroids(features), "skipped": skipped, "models": statuses,
            "errors": {f["piece"]["name"]: sorted(f.get("errors") or {}) for f in features if f.get("errors")}}


# ---- the commands --------------------------------------------------------------------------------------------------

def run(args, root: Path) -> int:
    needs_environment()
    source = Path(args.input).expanduser()
    if not source.is_dir():
        raise Refused(f"--in {source} isn't a folder")
    if not PAGE.fullmatch(args.page):
        raise Refused("--page: up to 100 letters, digits and @ . : + - _")
    if not speech.ROUTE.fullmatch(args.speech):
        raise Refused("--speech: auto, or a language's two or three letters")
    if args.format is not None and not PAGE.fullmatch(args.format):
        raise Refused("--format: up to 100 letters, digits and @ . : + - _")
    out = new_path(args.out, root)
    directory = Path(args.models).expanduser() if args.models else models.DEFAULT_DIR
    items, skipped = media.discover(source)
    out.mkdir()
    (out / "pieces").mkdir()
    rows = []
    for item, name in zip(items, file_names(items)):
        features = {"schema": SCHEMA,
                    "piece": {"name": item["name"], "page": args.page, "format": args.format, "kind": item["kind"],
                              "slides": len(item["images"]), "video_slides": item["video_slides"]},
                    "caption": caption.features(item["caption"]), "errors": {}}
        rows.append({"item": item, "features": features, "path": out / "pieces" / name})
    statuses = measure_all(rows, directory, args.format, args.ocr, args.speech, out)
    found = [row["features"] for row in rows]
    write_json(out / "summary.json", {"page": args.page, **summary(found, skipped, statuses)})
    print(json.dumps({"out": str(out), "pieces": len(found), "skipped": len(skipped),
                      "with_errors": sum(1 for f in found if f["errors"]), "models": statuses}, indent=1))
    return 0


def summary_command(args, root: Path) -> int:
    needs_environment(numpy=False)
    out = new_path(args.out, root)
    found = []
    for folder in args.runs:
        pieces = Path(folder).expanduser() / "pieces"
        if not pieces.is_dir():
            raise Refused(f"--runs {folder}: no pieces/ folder (not a run of this tool)")
        for path in sorted(pieces.glob("*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("schema") == SCHEMA and isinstance(data.get("piece"), dict):
                found.append(data)
    write_json(out, summary(found, []))
    print(json.dumps({"out": str(out), "pieces": len(found)}))
    return 0


def tesseract_languages() -> set:
    """The languages in Tesseract's own tessdata; none when it's missing or fails."""
    if not ocr.TESSERACT:
        return set()
    try:
        listed = subprocess.run([ocr.TESSERACT, "--list-langs"], capture_output=True, encoding="utf-8",
                                errors="replace", timeout=ocr.READ_SECONDS)
    except (OSError, subprocess.SubprocessError):
        return set()
    if listed.returncode != 0:
        return set()
    return {line.strip() for line in listed.stdout.splitlines()[1:] if line.strip()}


def check(args, root: Path) -> int:
    needs_environment(numpy=False)
    directory = Path(args.models).expanduser() if args.models else models.DEFAULT_DIR
    report = {
        "python": sys.version.split()[0],
        "imports": {name: importlib.util.find_spec(name) is not None for name in IMPORTS},
        "ffmpeg": media.FFMPEG.is_file(),
        "tesseract": bool(ocr.TESSERACT),
        "tesseract_languages": sorted(tesseract_languages()) if ocr.TESSERACT else [],
        "vision": Path(ocr.OSASCRIPT).is_file(),
        "models_dir": str(directory),
        "models": {name: models.status(name, directory) for name in models.catalogue()},
    }
    print(json.dumps(report, indent=1))
    return 0


def main(argv=None, root: Path = ROOT) -> int:
    parser = argparse.ArgumentParser(description="Measure pieces into feature files, distributions and centroids.")
    commands = parser.add_subparsers(dest="command", required=True)
    command = commands.add_parser("run", help="measure a folder of pieces")
    command.add_argument("--in", dest="input", required=True, help="the folder of pieces")
    command.add_argument("--page", required=True, help="whose pieces: our account or the reference page")
    command.add_argument("--out", required=True, help="a new folder")
    command.add_argument("--format", help="one format for every piece (default: each piece's kind)")
    command.add_argument("--models", help=f"the models folder (default {models.DEFAULT_DIR})")
    command.add_argument("--ocr", choices=ocr.ENGINES, default="tesseract", help="the on-screen text reader")
    command.add_argument("--speech", default="auto", help="the speech's language: auto (the caption's) or its code")
    command = commands.add_parser("summary", help="pool runs into one summary")
    command.add_argument("--runs", nargs="+", required=True, help="run folders")
    command.add_argument("--out", required=True, help="a new .json file")
    commands.add_parser("check", help="what's installed").add_argument("--models", help="the models folder")
    args = parser.parse_args(argv)
    refuse_network()
    commands_ = {"run": run, "summary": summary_command, "check": check}
    try:
        return commands_[args.command](args, root)
    except Refused as error:
        raise SystemExit(f"refused: {error}") from None


if __name__ == "__main__":
    raise SystemExit(main())
