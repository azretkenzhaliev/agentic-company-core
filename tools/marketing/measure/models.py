"""Where measure/'s models live and whether each one may load: every file present and matching its pinned sha256.

A model is <models dir>/<name>/<file> for each file in models.json. Nothing here downloads anything: a missing model is
"not installed", and its stage is skipped. A hash that isn't pinned yet (null), a partial set of files or a mismatch is an
error, so a model can't load from a file nobody checked.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DIR = ROOT / "workspaces" / "system" / "models" / "measure"
CATALOGUE = Path(__file__).resolve().parent / "models.json"

_hashes: dict = {}


class ModelError(Exception):
    pass


def catalogue() -> dict:
    return {model["name"]: model for model in json.loads(CATALOGUE.read_text(encoding="utf-8"))["models"]}


def sha256(path: Path) -> str:
    """Hashed once a run per file (a model's weights are gigabytes)."""
    key = str(path.resolve())
    if key not in _hashes:
        digest = hashlib.sha256()
        with open(path, "rb") as handle:
            for block in iter(lambda: handle.read(1 << 20), b""):
                digest.update(block)
        _hashes[key] = digest.hexdigest()
    return _hashes[key]


def locate(name: str, directory: Path) -> Path | None:
    """The model's folder when every file is there and matches; None when none is there; ModelError otherwise."""
    model = catalogue()[name]
    files = model["files"]
    folder = Path(directory) / name
    present = {file: (folder / file).is_file() for file in files}
    if not files or not any(present.values()):
        return None
    missing = [file for file, here in present.items() if not here]
    if missing:
        raise ModelError(f"{name}: missing {', '.join(missing)} in {folder}")
    for file, expected in files.items():
        if not expected:
            raise ModelError(f"{name}: {file} has no pinned sha256 in models.json; pin it before it can load")
        actual = sha256(folder / file)
        if actual != expected:
            raise ModelError(f"{name}: {file} sha256 {actual} isn't the pinned {expected}")
    return folder


def status(name: str, directory: Path) -> str:
    try:
        return "ok" if locate(name, directory) else "not installed"
    except ModelError as error:
        return f"refused: {error}"
