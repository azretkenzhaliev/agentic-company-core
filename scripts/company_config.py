"""The company's own settings, from company.json at the repo root. Scripts and hooks read them here, so someone who
copies the company edits one file. A missing file or key gives the default below; a file that can't be parsed raises."""

import json
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
DEFAULTS = {
    "company_name": "Example Co",
    "board_email": "",  # the only address the CEO may email; empty: it emails nobody
    "timezone": "UTC",  # IANA name; times shown to the Board
    "products": {},  # id -> {"repo": "owner/name", "workspace": "workspaces/<id>/<name>"}
    "integrations": {},  # name -> settings; an integration that isn't here is off
}


def load(root: Path = ROOT) -> dict:
    path = Path(root) / "company.json"
    own = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    return {**DEFAULTS, **own}


def timezone(root: Path = ROOT) -> ZoneInfo:
    return ZoneInfo(load(root)["timezone"])


def integration(name: str, root: Path = ROOT) -> "dict | None":
    """The integration's settings, or None when it is off."""
    return load(root)["integrations"].get(name)
