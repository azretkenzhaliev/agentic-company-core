#!/usr/bin/env python3
"""Find and download outside footage for our reels, to cut and compile with our own text, graphics, voice and music.

    python3 tools/marketing/footage/fetch.py search --library pexels|pixabay|youtube --query "<words>" [--max 10]
    python3 tools/marketing/footage/fetch.py get --url "<public video URL>" --brand founder/demo --week 2026-W05 --slug <name>
    python3 tools/marketing/footage/fetch.py get --library pexels|pixabay --id <clip id> --brand ... --week ... --slug ...

- **Any public URL** (YouTube, Instagram, TikTok, news sites), and a YouTube search, unless the Board turned them off
  (company.json: "public_downloads": false; the sites' terms and the copyright are its risk): through yt-dlp, pinned
  in tools/marketing/footage/.venv (requirements.txt; never system-wide). Public videos only: no cookies, no
  login, no config files, no plugins, no --exec; one video, never a playlist.
- **Stock:** Pexels and Pixabay through their APIs, by library and clip id, never by URL. The tool downloads only
  the file URL the API returned for that id, and follows a redirect only to https on the library's own hosts.
  Keys come from the macOS keychain items agentic-company-pexels and agentic-company-pixabay; without one, that
  library is skipped with a message (getting a key is a sign-up, so the Board's step).
- **Each download gets its own new folder,** workspaces/marketing/sources/<brand>/<week>/<slug>/, and a
  MANIFEST.json entry: source URL, owner, title, date, licence if stated, SHA-256, size and length. yt-dlp
  leaves Freesound's licence empty, so it's read from the sound's page, the copy yt-dlp already fetched
  (--write-pages, no request of ours), and recorded only when the page shows exactly one Creative Commons licence.
  That's a record to check, not a grant: the page's format is unverified, and video/compile.mjs doesn't trust it.
  video/compile.mjs refuses an outside file without that entry and appends the parts it used. The downloaded
  files are untrusted data: nothing here executes them, and this script runs Python isolated (-I).
- **Caps** (caps.json): footage_max_mb and footage_max_minutes per download (the length only when the site
  reports one; Instagram doesn't), footage_retries per request.
"""

import argparse
import hashlib
import ipaddress
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

if __name__ == "__main__" and not sys.flags.isolated:
    os.execv(sys.executable, [sys.executable, "-I", *sys.argv])

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

from company_config import integration  # noqa: E402

TOOLS = ROOT / "tools/marketing"
SOURCES = "workspaces/marketing/sources"
YT_PYTHON = TOOLS / "footage/.venv/bin/python"
FFMPEG = TOOLS / "node_modules/ffmpeg-static/ffmpeg"
BRAND = re.compile(r"^[a-z0-9][a-z0-9_.-]*(/[a-z0-9][a-z0-9_.-]*)?$")
WEEK = re.compile(r"^\d{4}-W\d{2}$")
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,60}$")
LIBRARIES = {
    "pexels": {"keychain": "agentic-company-pexels", "hosts": ("pexels.com", "vimeo.com", "vimeocdn.com", "akamaized.net"),
               "licence": "Pexels License", "licence_url": "https://www.pexels.com/license/"},
    "pixabay": {"keychain": "agentic-company-pixabay", "hosts": ("pixabay.com",),
                "licence": "Pixabay Content License", "licence_url": "https://pixabay.com/service/license-summary/"},
}
FREESOUND = ("freesound.org",)
CC_LICENCE = re.compile(r"https?://(?:www\.)?creativecommons\.org/(publicdomain/zero|licenses/[a-z+-]+)/(\d+\.\d+)", re.I)


def caps(root: Path = ROOT) -> dict:
    data = json.loads((root / "tools/marketing/caps.json").read_text(encoding="utf-8"))
    return {"max_bytes": int(data["footage_max_mb"]) * 1024 * 1024, "max_seconds": int(data["footage_max_minutes"]) * 60,
            "retries": int(data["footage_retries"])}


def read_key(library: str) -> "str | None":
    item = LIBRARIES[library]["keychain"]
    try:
        result = subprocess.run(["security", "find-generic-password", "-s", item, "-w"], capture_output=True, text=True)
    except FileNotFoundError:
        return None  # the keychain is macOS's
    return result.stdout.strip() if result.returncode == 0 and result.stdout.strip() else None


def new_folder(brand: str, week: str, slug: str, root: Path = ROOT) -> Path:
    """workspaces/marketing/sources/<brand>/<week>/<slug>/, new, inside sources/ with links resolved."""
    if not (BRAND.match(brand) and WEEK.match(week) and SLUG.match(slug)):
        raise SystemExit("refused: --brand like founder/demo, --week like 2026-W05, --slug lower-case words with hyphens")
    base = root / SOURCES
    base.mkdir(parents=True, exist_ok=True)
    folder = base / brand / week / slug
    if folder.exists():
        raise SystemExit(f"refused: {folder} exists; each download gets a new folder")
    folder.parent.mkdir(parents=True, exist_ok=True)
    if not str(folder.parent.resolve()).startswith(str(base.resolve()) + os.sep):
        raise SystemExit(f"refused: {folder} must be inside {SOURCES}/")
    folder.mkdir()
    return folder


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def write_manifest(folder: Path, entry: dict) -> Path:
    path = folder / "MANIFEST.json"
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"files": []}
    data["files"].append(entry)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


# ---- stock libraries ----------------------------------------------------------------------------------------

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


_OPENER = urllib.request.build_opener(_NoRedirect)


def open_url(url: str, headers: dict, timeout: int = 60):
    """One request, redirects not followed (the caller checks each hop)."""
    return _OPENER.open(urllib.request.Request(url, headers={"User-Agent": "agentic-company-footage/1", **headers}), timeout=timeout)


def allowed(url: str, hosts: tuple) -> bool:
    parts = urllib.parse.urlsplit(url)
    host = (parts.hostname or "").lower()
    return parts.scheme == "https" and any(host == h or host.endswith("." + h) for h in hosts)


def get_json(url: str, headers: dict, retries: int) -> dict:
    for attempt in range(retries + 1):
        try:
            with open_url(url, headers) as reply:
                return json.loads(reply.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code < 500 or attempt == retries:
                raise SystemExit(f"the library answered {e.code} for {urllib.parse.urlsplit(url).path}")
        except urllib.error.URLError as e:
            if attempt == retries:
                raise SystemExit(f"couldn't reach the library: {e.reason}")
    raise SystemExit("unreachable")


def download(url: str, target: Path, hosts: tuple, limits: dict) -> None:
    """Stream url to target, following at most 5 redirects, each to https on the library's hosts, within the size cap."""
    for _ in range(6):
        if not allowed(url, hosts):
            raise SystemExit(f"refused: {urllib.parse.urlsplit(url).hostname} isn't one of the library's hosts (https only)")
        for attempt in range(limits["retries"] + 1):
            try:
                reply = open_url(url, {})
                break
            except urllib.error.HTTPError as e:
                if e.code in (301, 302, 303, 307, 308):
                    reply = e
                    break
                if e.code < 500 or attempt == limits["retries"]:
                    raise SystemExit(f"download failed: {e.code}")
            except urllib.error.URLError as e:
                if attempt == limits["retries"]:
                    raise SystemExit(f"download failed: {e.reason}")
        status = getattr(reply, "status", None) or reply.code
        if status in (301, 302, 303, 307, 308):
            url = urllib.parse.urljoin(url, reply.headers.get("Location", ""))
            reply.close()
            continue
        size = 0
        with reply, target.open("wb") as out:
            for block in iter(lambda: reply.read(1 << 20), b""):
                size += len(block)
                if size > limits["max_bytes"]:
                    out.close()
                    target.unlink()
                    raise SystemExit(f"refused: over the {limits['max_bytes'] // 1048576} MB cap")
                out.write(block)
        return
    raise SystemExit("refused: too many redirects")


def stock_clip(library: str, clip_id: str, key: str, limits: dict) -> dict:
    """The API's record for one clip: its file URL (the largest within 1920 px), owner, page and length."""
    if not clip_id.isdigit():
        raise SystemExit("refused: --id is the library's numeric clip id")
    if library == "pexels":
        data = get_json(f"https://api.pexels.com/videos/videos/{clip_id}", {"Authorization": key}, limits["retries"])
        files = [f for f in data.get("video_files", []) if f.get("file_type") == "video/mp4" and max(f.get("width") or 0, f.get("height") or 0) <= 1920]
        best = max(files, key=lambda f: (f.get("width") or 0) * (f.get("height") or 0), default=None)
        user = data.get("user") or {}
        record = {"file_url": best and best.get("link"), "owner": user.get("name"), "owner_url": user.get("url"),
                  "page": data.get("url"), "duration": data.get("duration"), "title": None}
    else:
        query = urllib.parse.urlencode({"key": key, "id": clip_id})
        hits = get_json(f"https://pixabay.com/api/videos/?{query}", {}, limits["retries"]).get("hits") or []
        if not hits:
            raise SystemExit(f"pixabay has no clip {clip_id}")
        hit = hits[0]
        sizes = [v for v in (hit.get("videos") or {}).values() if v.get("url") and max(v.get("width") or 0, v.get("height") or 0) <= 1920]
        best = max(sizes, key=lambda v: (v.get("width") or 0) * (v.get("height") or 0), default=None)
        record = {"file_url": best and best.get("url"), "owner": hit.get("user"),
                  "owner_url": f"https://pixabay.com/users/{hit.get('user')}-{hit.get('user_id')}/", "page": hit.get("pageURL"),
                  "duration": hit.get("duration"), "title": hit.get("tags")}
    if not record["file_url"]:
        raise SystemExit(f"{library} gave no MP4 file within 1920 px for clip {clip_id}")
    if record["duration"] and record["duration"] > limits["max_seconds"]:
        raise SystemExit(f"refused: the clip is {record['duration']} s; the cap is {limits['max_seconds']} s")
    return record


def get_stock(library: str, clip_id: str, folder_args: tuple, root: Path = ROOT) -> "Path | None":
    key = read_key(library)
    if not key:
        print(f"skipped: no {library} key in the keychain item '{LIBRARIES[library]['keychain']}' (the Board's sign-up step)")
        return None
    limits = caps(root)
    clip = stock_clip(library, clip_id, key, limits)
    folder = new_folder(*folder_args, root=root)
    target = folder / "video.mp4"
    try:
        download(clip["file_url"], target, LIBRARIES[library]["hosts"], limits)
    except BaseException:
        shutil.rmtree(folder, ignore_errors=True)
        raise
    return write_manifest(folder, {
        "file": target.name, "sha256": sha256(target), "bytes": target.stat().st_size, "seconds": clip["duration"],
        "source_url": clip["page"], "library": library, "id": clip_id, "owner": clip["owner"], "owner_url": clip["owner_url"],
        "title": clip["title"], "date": None, "licence": LIBRARIES[library]["licence"],
        "licence_url": LIBRARIES[library]["licence_url"], "music_ok": False,
        "fetched": datetime.now(timezone.utc).isoformat(timespec="seconds"), "used": []})


def search_stock(library: str, query: str, limit: int) -> None:
    key = read_key(library)
    if not key:
        print(f"skipped: no {library} key in the keychain item '{LIBRARIES[library]['keychain']}' (the Board's sign-up step)")
        return
    retries = caps()["retries"]
    if library == "pexels":
        q = urllib.parse.urlencode({"query": query, "per_page": limit})
        for v in get_json(f"https://api.pexels.com/videos/search?{q}", {"Authorization": key}, retries).get("videos", []):
            print(f"pexels {v.get('id')}  {v.get('duration')} s  {v.get('width')}x{v.get('height')}  by {(v.get('user') or {}).get('name')}  {v.get('url')}")
    else:
        q = urllib.parse.urlencode({"key": key, "q": query, "per_page": max(3, limit)})
        for h in get_json(f"https://pixabay.com/api/videos/?{q}", {}, retries).get("hits", []):
            print(f"pixabay {h.get('id')}  {h.get('duration')} s  by {h.get('user')}  {h.get('pageURL')}")


# ---- any public URL, through yt-dlp ---------------------------------------------------------------------------

def yt_base(limits: dict) -> list:
    """yt-dlp, isolated: no config, cookies, plugins, --exec or playlists; capped in size, length and retries."""
    if not YT_PYTHON.exists():
        raise SystemExit("yt-dlp isn't installed: see tools/marketing/footage/requirements.txt")
    r = str(limits["retries"])
    return [str(YT_PYTHON), "-I", "-m", "yt_dlp", "--ignore-config", "--no-plugin-dirs", "--no-cookies", "--no-cookies-from-browser",
            "--no-batch-file", "--no-exec", "--no-playlist", "--retries", r, "--fragment-retries", r, "--extractor-retries", r,
            "--socket-timeout", "30", "--no-progress", "--no-write-comments"]


def public_url(url: str) -> str:
    """A public web address: http(s), no login, a named host (no IP literal in any spelling) that resolves only to
    public addresses. yt-dlp's own redirects aren't checked; downloads are public videos only."""
    parts = urllib.parse.urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname or "@" in parts.netloc:
        raise SystemExit("refused: --url must be a public http(s) address with no login in it")
    host = parts.hostname.lower().rstrip(".")
    last = host.rsplit(".", 1)[-1]
    if (":" in host or "." not in host or re.fullmatch(r"\d+|0x[0-9a-f]+", last)
            or host == "localhost" or host.endswith((".localhost", ".local", ".internal", ".lan", ".home.arpa"))):
        raise SystemExit("refused: --url must name a public site, not a local name or a numeric address")
    try:
        addresses = {info[4][0] for info in socket.getaddrinfo(host, None)}
    except OSError:
        raise SystemExit(f"refused: {host} doesn't resolve")
    if not addresses or not all(ipaddress.ip_address(a.split("%")[0]).is_global for a in addresses):
        raise SystemExit(f"refused: {host} resolves to a private or local address")
    return url


def freesound_licence(pages: list) -> tuple:
    """(short name, licence URL) from a Freesound sound's saved page, or (None, None) unless it shows exactly one
    Creative Commons licence. A description can link a licence of its own, so an unclear page records nothing;
    a description's link on a page whose own licence link this can't read would still be taken."""
    found = {(kind.lower(), version) for page in pages for kind, version in CC_LICENCE.findall(page)}
    if len(found) != 1:
        return None, None
    kind, version = found.pop()
    name = "CC0" if kind == "publicdomain/zero" else "CC " + kind.removeprefix("licenses/").upper()
    return f"{name} {version}", f"https://creativecommons.org/{kind}/{version}/"


def public_ok(root: Path = ROOT) -> None:
    """Refuses where marketing isn't set up, or the Board turned searching and downloading from public pages off:
    any value but true (reels/watch.py and reels/save.py ask too)."""
    settings = integration("marketing", root)
    if not isinstance(settings, dict) or settings.get("public_downloads", True) is not True:
        raise SystemExit("refused: searching or downloading from a public site is off "
                         "(company.json: integrations.marketing isn't set, or its public_downloads isn't true)")


def get_url(url: str, folder_args: tuple, root: Path = ROOT) -> Path:
    public_ok(root)
    url = public_url(url)
    limits = caps(root)
    folder = new_folder(*folder_args, root=root)
    try:
        return _get_url(url, folder, limits)
    except BaseException:
        shutil.rmtree(folder, ignore_errors=True)
        raise


def _get_url(url: str, folder: Path, limits: dict, timeout: float = 3600) -> Path:
    freesound = allowed(url, FREESOUND)
    args = yt_base(limits) + (["--write-pages"] if freesound else []) + [
        "--max-filesize", f"{limits['max_bytes'] // 1048576}M",
        "--match-filters", f"!is_live & duration <=? {limits['max_seconds']}",  # <=?: Instagram reports no duration
        "-f", "bv*[height<=1920][ext=mp4]+ba[ext=m4a]/b[ext=mp4][height<=1920]/bv*[height<=1920]+ba/b",
        "--merge-output-format", "mp4", "--ffmpeg-location", str(FFMPEG), "--restrict-filenames", "--no-mtime",
        "--write-info-json", "-o", str(folder / "video.%(ext)s"), "--", url]
    run = subprocess.run(args, cwd=folder, capture_output=True, text=True, timeout=timeout)
    videos = [p for p in folder.iterdir() if p.name.startswith("video.") and not p.name.endswith((".json", ".part", ".ytdl"))]
    if run.returncode != 0 or len(videos) != 1:
        said = [line for line in run.stdout.splitlines() if line.startswith("[download] ")][-3:]  # a filter's reason is here
        raise SystemExit(f"yt-dlp didn't download one video (exit {run.returncode}): {' '.join(said + [run.stderr.strip()[-600:]]).strip()}")
    video = videos[0]
    if video.stat().st_size > limits["max_bytes"]:
        video.unlink()
        raise SystemExit(f"refused: over the {limits['max_bytes'] // 1048576} MB cap")
    info_files = list(folder.glob("video*.info.json"))
    info = json.loads(info_files[0].read_text(encoding="utf-8")) if info_files else {}
    if isinstance(info.get("duration"), (int, float)) and info["duration"] > limits["max_seconds"]:
        raise SystemExit(f"refused: the video is {info['duration']} s; the cap is {limits['max_seconds']} s")
    date = info.get("upload_date")
    licence, licence_url = info.get("license"), None
    dumps = list(folder.glob("*.dump"))
    if info.get("extractor_key") == "Freesound":  # a sound's own page, not a pack or forum page on the same host
        licence, licence_url = freesound_licence([p.read_text(encoding="utf-8", errors="replace") for p in dumps])
        if not licence:
            print("no single licence on the Freesound page: the manifest's licence stays empty")
    for dump in dumps:
        dump.unlink()
    return write_manifest(folder, {
        "file": video.name, "sha256": sha256(video), "bytes": video.stat().st_size, "seconds": info.get("duration"),
        "source_url": info.get("webpage_url") or url, "library": info.get("extractor_key") or "yt-dlp", "id": info.get("id"),
        "owner": info.get("channel") or info.get("uploader"), "owner_url": info.get("channel_url") or info.get("uploader_url"),
        "title": info.get("title"), "date": f"{date[:4]}-{date[4:6]}-{date[6:]}" if date and len(date) == 8 else None,
        "licence": licence, "licence_url": licence_url, "music_ok": False,
        "fetched": datetime.now(timezone.utc).isoformat(timespec="seconds"), "used": []})


def search_youtube(query: str, limit: int, root: Path = ROOT) -> None:
    public_ok(root)
    limits = caps(root)
    run = subprocess.run(yt_base(limits) + ["--flat-playlist", "--dump-single-json", "--", f"ytsearch{limit}:{query}"],
                         capture_output=True, text=True, timeout=300, cwd=TOOLS)
    if run.returncode != 0:
        raise SystemExit(f"yt-dlp search failed: {run.stderr.strip()[-400:]}")
    for e in json.loads(run.stdout).get("entries", []):
        print(f"youtube {e.get('duration')} s  {e.get('channel') or e.get('uploader')}  {e.get('title')}  {e.get('url')}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Find and download outside footage, with a manifest per clip.", allow_abbrev=False)
    sub = parser.add_subparsers(dest="command", required=True)
    s = sub.add_parser("search", allow_abbrev=False)
    s.add_argument("--library", choices=["pexels", "pixabay", "youtube"], required=True)
    s.add_argument("--query", required=True)
    s.add_argument("--max", type=int, default=10)
    g = sub.add_parser("get", allow_abbrev=False)
    g.add_argument("--url")
    g.add_argument("--library", choices=list(LIBRARIES))
    g.add_argument("--id")
    for name in ("--brand", "--week", "--slug"):
        g.add_argument(name, required=True)
    args = parser.parse_args(argv)
    if args.command == "search":
        limit = max(1, min(args.max, 30))
        search_youtube(args.query, limit) if args.library == "youtube" else search_stock(args.library, args.query, limit)
        return 0
    folder_args = (args.brand, args.week, args.slug)
    if bool(args.url) == bool(args.library and args.id):
        parser.error("give either --url, or --library and --id")
    manifest = get_url(args.url, folder_args) if args.url else get_stock(args.library, args.id, folder_args)
    if manifest:
        entry = json.loads(manifest.read_text(encoding="utf-8"))["files"][-1]
        print(f"wrote {manifest.parent / entry['file']} ({entry['bytes']:,} bytes, {entry['seconds']} s) and {manifest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
