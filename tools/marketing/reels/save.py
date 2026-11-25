#!/usr/bin/env python3
"""Save public Instagram posts and reel covers, so a taste session shows real references in every format,
unless the Board turned downloading from public pages off (fetch.py, "Any public URL").

    python3 tools/marketing/reels/save.py post   --code AbCdEfGhI01 [AbCdEfGhI02 ...] [--retry-failed]
    python3 tools/marketing/reels/save.py latest --account someaccount [--count 6] [--retry-failed]
    python3 tools/marketing/reels/save.py covers --week 2026-W05 [--count 10] [--retry-failed]

- **instaloader 4.16 (MIT), pinned,** in workspaces/system/venvs/instaloader-4.16 (gitignored): this re-runs itself with
  that interpreter, isolated (-I), and refuses any other version. Logged out only: no login, no account, no session file.
  Signed-in reads (Highlights, stories) wait for an upstream fix (instaloader issue 2792).
- **post** saves an image post or a carousel: every slide, video slides as MP4. A reel is refused: watch.py saves reels.
  A code already saved is skipped.
- **latest** reads an account's profile page as a logged-out visitor sees it and
  saves its latest --count posts that aren't reels or videos (1-12, 6 by default), each as post does, printing each
  code and its type. Only what the page itself lists, about 12 (unverified), pinned posts first: no next page is asked
  for. A reel the page didn't mark is recorded as post records one once its read shows it, and the next run takes the
  next post in its place. A private account, or none by that name, saves nothing and doesn't stop the run.
- **covers** saves cover.jpg in reels/<code>/ for each of the week's measured reels that has none, up to --count.
- **Gentle:** one run at a time (posts/.lock), 10-15 s before every request, at most 24 a run, nothing started after 8
  minutes, one attempt each. A 401, 403 or 429, a 400 feedback_required, a checkpoint or challenge, a login redirect,
  or any other redirect of the profile page stops the run, stored in posts/stopped.txt; so do 3 failures in a row.
  Until --retry-failed clears it, a run prints it and fetches nothing. A failed post gets posts/<code>/failed.txt, a
  failed cover reels/<code>/cover-failed.txt, skipped until --retry-failed.
- **Requests,** all reads: for latest, the profile page once (a GET in instaloader's anonymous session, with no
  cookies of ours); the start page once for the web app's tokens (and once more if it set no csrf cookie);
  each post one GraphQL read (an HTTP POST, as the logged-out web app makes); each file one GET from Instagram's CDN
  (cdninstagram.com or fbcdn.net, https only), in instaloader's anonymous session: logged out, no account. A redirect
  is followed by hand, at most 3, each hop checked to be on the CDN before it's requested and paced like any request.
  No likes, follows, comments or any other write.
- **Files,** under workspaces/marketing/intelligence/posts/<code>/ (beside reels/), never a synced folder (a link anywhere below
  the checkout is refused): 1.jpg, 2.mp4, ..., cover.jpg when slide 1 is a video, caption.txt (masked as watch.py does),
  and MANIFEST.json in taste/build.py's format, moved in last from this run's temporary folder under posts/. Untrusted
  data: each file is checked by its first bytes and fetch.py's size cap, and only ffmpeg opens a video, for its length.
  An image slot takes a JPEG as it is, and a PNG, WebP, HEIC or AVIF made a JPEG by macOS's own sips (elsewhere
  such a file fails its post), so every image is still a .jpg; anything else (an HTML page, an empty or unknown body) fails its post,
  its failed.txt naming the kind found and the size.
  A post shows in a taste picker only once it has a style.md, as a reel does; this never writes style.md.
"""

import argparse
import fcntl
import json
import os
import random
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import urljoin, urlsplit

ROOT = Path(__file__).resolve().parents[3]
VENV = ROOT / "workspaces/system/venvs/instaloader-4.16"
PINNED = VENV / "bin/python"
VERSION = "4.16"


def pinned(argv: list, isolated: bool, prefix: str, executable: str, execv=os.execv) -> None:
    """Go on in the pinned environment, isolated (-I); from anywhere else, re-run with its interpreter."""
    if isolated and Path(prefix).resolve() == VENV.resolve():
        return
    if isolated and executable == str(PINNED):  # re-run already, and still not the environment: no loop
        raise SystemExit(f"refused: {PINNED} doesn't run in {VENV}")
    if not PINNED.is_file():
        raise SystemExit(f"refused: no pinned environment at {VENV}; it holds instaloader {VERSION}")
    execv(PINNED, [str(PINNED), "-I", str(Path(__file__).resolve()), *argv])


if __name__ == "__main__":
    pinned(sys.argv[1:], bool(sys.flags.isolated), sys.prefix, sys.executable)

sys.path[:0] = [str(ROOT / "tools/marketing/reels")]

import watch  # noqa: E402  (it adds tools/marketing and footage/ to the path)
import fetch  # noqa: E402

POSTS_DIR = "workspaces/marketing/intelligence/posts"
HANDLE = re.compile(r"[A-Za-z0-9._]{1,40}")
HOSTS = (".cdninstagram.com", ".fbcdn.net")
PAUSE = (10, 15)  # seconds before every request
MAX_FETCHES = 24  # a run's requests: a 20-slide carousel opening on a video, with the start page twice, fits a fresh run
RUN_SECONDS = 480  # no request starts after this, so a run fits Bash's 10 minutes
DOWNLOAD_SECONDS = 60
MAX_SLIDES = 20
REDIRECTS = 3  # a file's, each one paced
CHUNK = 65536
SIPS = "/usr/bin/sips"  # macOS's own image converter: local, no network
SIPS_SECONDS = 30
BRANDS = {b"heic": "HEIC", b"heix": "HEIC", b"mif1": "HEIC", b"avif": "AVIF"}  # an ISO file's brand that's an image
CONVERTED = ("PNG", "WebP", "HEIC", "AVIF")  # the images sips makes a JPEG
REDIRECTED = re.compile(r"3\d\d\b")  # how 4.16's words for a 3xx it didn't follow begin: "302 Found when accessing ..."
KINDS = {"GraphImage": "post", "GraphSidecar": "carousel"}
STOP_ERRORS = ("AbortDownloadException", "TooManyRequestsException", "LoginRequiredException",
               "QueryReturnedForbiddenException")
# Instagram's refusals, in one place: a 401, 403 or 429; a 400 that says feedback_required (as 4.16 words it:
# '400 Bad Request - "fail" status, message "feedback_required"'); and these words anywhere, a 200 "fail" with
# feedback_required included. A 400 without them fails only its post.
REFUSED = re.compile(r"\b(401|403|429) [A-Z]|\b(400) [A-Z].*?(feedback_required)"
                     r"|(?i:(checkpoint|challenge|feedback_required|login|wait a few minutes))")
USERNAME = re.compile(r"(?!\.)(?!.*\.\.)[A-Za-z0-9._]{1,30}(?<!\.)")  # no dot first or last, nor two in a row
NOT_ACCOUNTS = {"about", "accounts", "api", "challenge", "developer", "direct", "explore", "graphql", "legal", "p",
                "reel", "reels", "stories", "tv", "web"}  # Instagram's own pages, whose login redirect would stop us
LATEST = (1, 12)  # latest --count: the profile page lists about 12
REEL = "a reel or a video: watch.py saves reels, and covers saves its cover"  # its failed.txt, which latest skips
FAILED_POST = "failed.txt"
FAILED_COVER = "cover-failed.txt"


class Failed(Exception):
    """This post or cover can't be saved; it counts toward the failures in a row."""


class Reel(Failed):
    """A reel or a video, which post refuses and latest skips."""


class Full(Exception):
    """The run's requests or time are used up: the rest waits for the next run."""


USED_UP = f"this run's {MAX_FETCHES} requests or {RUN_SECONDS // 60} minutes are used up: run it again for the rest."


class Pace:
    """10-15 s before every request, and no request past the run's caps."""

    def __init__(self, sleep, clock, rand):
        self.sleep, self.clock, self.rand = sleep, clock, rand
        self.started, self.count = clock(), 0

    def room(self, requests: int) -> bool:
        return (self.count + requests <= MAX_FETCHES
                and self.clock() - self.started + requests * PAUSE[1] <= RUN_SECONDS)

    def wait(self) -> None:
        pause = self.rand(*PAUSE)
        if self.count >= MAX_FETCHES or self.clock() - self.started + pause > RUN_SECONDS:
            raise Full()
        self.sleep(pause)
        self.count += 1


def load_instaloader():
    import instaloader
    if instaloader.__version__ != VERSION:
        raise SystemExit(f"refused: instaloader {instaloader.__version__}, not the pinned {VERSION}")
    return instaloader


def make_loader(instaloader, pace: Pace):
    """Logged out, one attempt per request, and every request Instagram counts paced, the csrf one included."""
    class Gentle(instaloader.RateController):
        def wait_before_query(self, query_type):
            pace.wait()

    loader = instaloader.Instaloader(sleep=False, quiet=True, max_connection_attempts=1, request_timeout=30,
                                     fatal_status_codes=[401, 403, 429], iphone_support=False,
                                     rate_controller=lambda context: Gentle(context))
    context = loader.context
    csrf = getattr(context, "_csrf_token", None)
    if (instaloader.__version__ != VERSION or not callable(csrf)
            or not hasattr(getattr(context, "_session", None), "cookies")):
        loader.close()
        raise SystemExit(f"refused: the csrf fetch is paced as instaloader {VERSION} makes it; check this wrapper "
                         "before moving the pin")

    def paced_csrf():  # it fetches the start page itself when there's no csrf cookie, past the rate controller
        if not any(cookie.name == "csrftoken" and cookie.value for cookie in context._session.cookies):
            pace.wait()
        return csrf()

    context._csrf_token = paced_csrf
    return loader


def refusal(error: BaseException, instaloader, quiet: str = "") -> "str | None":
    """Why this error means Instagram is refusing us, or None. Names and signals only: its text holds signed URLs.
    quiet is left out of the text first: a profile's address, whose name may hold such a word."""
    classes = tuple(getattr(instaloader, name) for name in STOP_ERRORS)
    names, signals, link = [], set(), error
    while link is not None and len(names) < 10:
        names.append(type(link).__name__)
        if isinstance(link, classes):
            signals.add(type(link).__name__)
        text = str(link).replace(quiet, "") if quiet else str(link)
        signals.update(" ".join(group for group in match.groups() if group).lower()
                       for match in REFUSED.finditer(text))
        link = link.__cause__ or link.__context__
    if not signals:
        return None
    return (f"Instagram refused us ({', '.join(sorted(signals))}; {' from '.join(names)}). Don't run save.py again now; "
            "report it.")


def on_cdn(url) -> bool:
    parts = urlsplit(url) if isinstance(url, str) else None
    host = (parts.hostname or "") if parts else ""
    return bool(parts and parts.scheme == "https" and parts.netloc.lower() == host and host.endswith(HOSTS))


def kind_of(head: bytes) -> str:
    """What a file's first bytes say it is: JPEG, PNG, WebP, HEIC, AVIF, MP4 (any other ISO file), HTML, empty or
    unknown."""
    if not head:
        return "empty"
    if head[:3] == b"\xff\xd8\xff":
        return "JPEG"
    if head[:8] == b"\x89PNG\r\n\x1a\n":
        return "PNG"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "WebP"
    if head[4:8] == b"ftyp":
        return BRANDS.get(head[8:12], "MP4")
    if head.lstrip()[:1] == b"<":
        return "HTML"
    return "unknown"


def to_jpeg(source: Path, target: Path, limit: int, what: str) -> None:
    """source, an image that isn't a JPEG, made a JPEG at target by macOS's sips, on this Mac; what names it. A failure
    is raised outside the except, so neither it nor refusal(), which reads an error's context, holds sips's command
    line and the folder's path in it."""
    try:
        done = subprocess.run([SIPS, "-s", "format", "jpeg", str(source), "--out", str(target)],
                              stdin=subprocess.DEVNULL, capture_output=True, timeout=SIPS_SECONDS)
        problem = None if done.returncode == 0 and target.is_file() else "sips failed"
    except subprocess.TimeoutExpired:
        problem = f"sips ran over {SIPS_SECONDS} s"
    except OSError as error:
        problem = f"sips can't run here ({type(error).__name__})"
    if problem is None:
        with target.open("rb") as file:
            if kind_of(file.read(64)) != "JPEG":
                problem = "sips wrote something else"
    if problem:
        raise Failed(f"{what} wasn't made a JPEG: {problem}")
    if target.stat().st_size > limit:
        raise Failed(f"{what} made a JPEG over the cap of {limit // 2**20} MB")


def download(context, url, path: Path, pace: Pace, root: Path) -> None:
    """One file from Instagram's CDN into a new file, under fetch.py's size cap, checked by its first bytes; an image
    slot's PNG, WebP, HEIC or AVIF is made a JPEG. As 4.16's get_raw, but redirects are followed by hand: each hop
    checked to be on the CDN before it's requested, and paced."""
    for hop in range(REDIRECTS + 1):
        if not on_cdn(url):
            raise Failed("a file was redirected off Instagram's CDN" if hop
                         else "a file's address isn't on Instagram's CDN")
        pace.wait()
        with context.get_anonymous_session() as session:
            resp = session.get(url, stream=True, allow_redirects=False)
        if not resp.is_redirect:
            break
        resp.close()
        url = urljoin(url, resp.headers["location"])
    else:
        raise Failed(f"a file was redirected more than {REDIRECTS} times")
    try:
        context._raise_for_download_status(resp)  # 4.16's: a 403 raises what stops the run, a 401 or 429 says it
        resp.raw.decode_content = True
        limit = fetch.caps(root)["max_bytes"]
        deadline, size = pace.clock() + DOWNLOAD_SECONDS, 0
        with path.open("xb") as out:
            while chunk := resp.raw.read(CHUNK):
                size += len(chunk)
                if size > limit:
                    raise Failed(f"a file is over the cap of {limit // 2**20} MB")
                if pace.clock() > deadline:
                    raise Failed(f"a file took over {DOWNLOAD_SECONDS} s")
                out.write(chunk)
    finally:
        resp.close()
    with path.open("rb") as file:
        found = kind_of(file.read(64))
    if path.suffix == ".mp4":
        if found != "MP4":
            raise Failed(f"{path.name} isn't an MP4: {found}, {size} bytes")
    elif found in CONVERTED:
        source = path.with_name(f"{path.stem}.{found.lower()}")  # 1.webp beside 1.jpg's place, gone once read
        os.replace(path, source)
        try:
            to_jpeg(source, path, limit, f"{path.name}, a {found} of {size} bytes,")
        finally:
            source.unlink(missing_ok=True)
    elif found != "JPEG":
        raise Failed(f"{path.name} isn't an image we take: {found}, {size} bytes")


def save_post(instaloader, loader, code: str, folder: Path, pace: Pace, root: Path) -> str:
    post = instaloader.Post.from_shortcode(loader.context, code)
    if post.typename == "GraphVideo":
        raise Reel(REEL)
    kind = KINDS.get(post.typename)
    if kind is None:
        raise Failed("an unknown kind of post")
    account = post.owner_username
    if not (isinstance(account, str) and HANDLE.fullmatch(account)):
        raise Failed("its account isn't a handle")
    if kind == "post":
        nodes = [(False, post.url, None)]
    else:
        nodes = [(node.is_video, node.display_url, node.video_url) for node in post.get_sidecar_nodes()]
        if not 1 <= len(nodes) <= MAX_SLIDES:
            raise Failed(f"a carousel of {len(nodes)} slides; at most {MAX_SLIDES}")
    slides = [(f"{place}.{'mp4' if video else 'jpg'}", video_url if video else display_url)
              for place, (video, display_url, video_url) in enumerate(nodes, 1)]
    downloads = list(slides)
    first_video, first_display, _ = nodes[0]
    cover = "1.jpg" if not first_video else "cover.jpg" if first_display else None
    if cover == "cover.jpg":
        downloads.append((cover, first_display))
    if not pace.room(len(downloads)):
        raise Full()
    temp = Path(tempfile.mkdtemp(prefix=f".tmp-{code}-", dir=folder.parent))
    try:
        for name, url in downloads:
            download(loader.context, url, temp / name, pace, root)
        entries = []
        for name, _ in slides:
            if name.endswith(".mp4"):
                entries.append({"file": name, "type": "video", "seconds": round(watch.probe(temp / name)[0], 2)})
            else:
                entries.append({"file": name, "type": "image"})
        caption = watch.masked(post.caption or "")
        (temp / "caption.txt").write_text(caption + "\n", encoding="utf-8")
        manifest = {"kind": kind, "code": code, "account": account, "date": post.date_utc.strftime("%Y-%m-%d"),
                    "description": " ".join(caption.split())[:230], "slides": entries}
        if cover:
            manifest["cover"] = cover
        (temp / "MANIFEST.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        folder.mkdir(exist_ok=True)
        for part in sorted(temp.iterdir(), key=lambda path: path.name == "MANIFEST.json"):  # the manifest last
            os.replace(part, folder / part.name)
    finally:
        shutil.rmtree(temp, ignore_errors=True)
    return kind


def save_cover(instaloader, loader, code: str, folder: Path, pace: Pace, root: Path) -> str:
    post = instaloader.Post.from_shortcode(loader.context, code)
    if not pace.room(1):
        raise Full()
    temp = Path(tempfile.mkdtemp(prefix=f".tmp-cover-{code}-", dir=root / POSTS_DIR))  # posts/, which this run holds
    try:
        download(loader.context, post.url, temp / "cover.jpg", pace, root)
        os.replace(temp / "cover.jpg", folder / "cover.jpg")
    finally:
        shutil.rmtree(temp, ignore_errors=True)
    return "cover"


def recorded_reel(folder: Path) -> bool:
    """Whether an earlier run found this code a reel (its failed.txt says so), so latest leaves it out."""
    record = folder / FAILED_POST
    if folder.is_symlink() or record.is_symlink() or not record.is_file():
        return False
    try:
        with record.open(encoding="utf-8", errors="replace") as file:
            return file.read(len(REEL) + 2).strip() == REEL
    except OSError:
        return False


def latest_codes(context, base: Path, account: str, count: int) -> list:
    """The codes of the account's latest count posts that aren't reels or videos, newest first, from its profile page
    as a logged-out visitor gets it (4.16's get_page_data: one GET, paced as "other"). No next page."""
    users = [data["xig_user_by_username"] for data in context.get_page_data(f"{account}/")
             if isinstance(data, dict) and isinstance(data.get("xig_user_by_username"), dict)]
    if any(user.get("is_private") for user in users):  # none of the account's words here: refusal() reads this text
        raise Failed("a private account, whose posts a logged-out visitor doesn't see")
    timeline = next((user["polaris_ordered_timeline_connection"] for user in users
                     if isinstance(user.get("polaris_ordered_timeline_connection"), dict)), None)
    if timeline is None:
        raise Failed("its page lists no posts: no account by that name, or Instagram changed the page")
    nodes = [edge.get("node") for edge in timeline.get("edges") or [] if isinstance(edge, dict)]
    nodes = [node for node in nodes if isinstance(node, dict) and isinstance(node.get("code"), str)
             and watch.CODE.fullmatch(node["code"])]
    codes = [node["code"] for node in nodes if node.get("media_type") != 2 and node.get("product_type") != "clips"
             and not recorded_reel(base / node["code"])]
    print(f"{account}: its page lists {len(nodes)} posts; {len(nodes) - len(codes)} left out, as reels or videos "
          "the page marked or an earlier run found.")
    return codes[:count]


def each(items: list, base: Path, record: str, save, pace: Pace, instaloader, skip: tuple = ()) -> int:
    """Save each (code, folder) in turn; stop on a refusal or a run of failures, and end when the caps are reached.
    An error in skip is recorded as a failure is, but doesn't count toward the failures in a row."""
    failures, saved = 0, 0
    for code, folder in items:
        try:
            if not pace.room(2):
                raise Full()
            kind = save(code, folder)
        except Full:
            print(USED_UP)
            break
        except Exception as error:  # whatever Instagram or a file does fails that item, unless it's a refusal
            reason = refusal(error, instaloader)
            if reason:
                return stop(base, reason)
            if isinstance(error, subprocess.TimeoutExpired):  # never its text, which is the whole command line
                reason = "ffmpeg ran past its limit"
            else:
                reason = str(error)[:300] if isinstance(error, (Failed, watch.ReelError)) else type(error).__name__
            skipped = isinstance(error, skip)
            if not skipped:
                failures += 1
            try:
                folder.mkdir(exist_ok=True)
                watch.write_atomic(folder / record, reason + "\n")
            except OSError as problem:
                return stop(base, f"{code} failed ({reason}), and its {record} couldn't be written "
                                  f"({type(problem).__name__}). Don't run save.py again now; report it.")
            print(f"{code}: skipped: {reason}; a rerun takes the next post" if skipped else f"{code}: failed: {reason}")
            if failures >= watch.MAX_FAILURES:
                return stop(base, f"{watch.MAX_FAILURES} failures in a row, which may mean Instagram is refusing us. "
                                  f"Don't run save.py again now; report it. --retry-failed retries these later. "
                                  f"Last reason: {reason}")
        else:
            failures = 0
            (folder / record).unlink(missing_ok=True)
            saved += 1
            print(f"{code}: saved ({kind})")
    print(f"saved {saved} this run.")
    return 0


def stop(base: Path, reason: str) -> int:
    """watch.py's stored stop; if it can't be stored, still a printed stop, not a traceback."""
    try:
        return watch.stop_run(base, reason)
    except OSError as problem:
        print(f"stopped: {reason}\nThat couldn't be stored in {watch.STOPPED} ({type(problem).__name__}): report it.")
        return 2


def unlinked(root: Path, path: Path) -> Path:
    """path, refused if it or any folder between it and the checkout is a link: posts and covers stay on this disk."""
    for part in (path, *path.parents):
        if part == root:
            return path
        if part.is_symlink():
            raise SystemExit(f"refused: {part} is a link; posts and covers stay on this disk, not in a synced folder")
    raise SystemExit(f"refused: {path} isn't in the checkout")


def posts_root(root: Path) -> Path:
    base = unlinked(root, root / POSTS_DIR)
    base.mkdir(parents=True, exist_ok=True)
    return base


def hold(base: Path) -> int:
    """One run at a time, so two never share a folder or double the rate. The system drops the lock when a run ends,
    however it ends."""
    lock = os.open(base / ".lock", os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(lock)
        raise SystemExit("refused: another save.py run is going; report it rather than wait for it") from None
    return lock


def stored_stop(stored: Path) -> "str | None":
    """The stored stop's text, or None if there's none. Opened without following a link: a planted link would print
    whatever it points to."""
    try:
        fd = os.open(stored, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return None
    except OSError as problem:
        return f"stopped: posts/{watch.STOPPED} can't be read ({type(problem).__name__}: a link?). Report it."
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            return f"stopped: posts/{watch.STOPPED} isn't a plain file. Report it."
        with os.fdopen(fd, encoding="utf-8", errors="replace", closefd=False) as file:
            return file.read(4000).strip()
    finally:
        os.close(fd)


def post_items(base: Path, codes: list, retry_failed: bool) -> list:
    items = []
    for code in dict.fromkeys(codes):
        folder = base / code
        if folder.is_symlink():
            print(f"{code}: skipped: its folder is a link")
        elif (folder / "MANIFEST.json").is_file():
            print(f"{code}: saved already")
        elif (folder / FAILED_POST).is_file() and not retry_failed:
            print(f"{code}: failed before; --retry-failed tries it again")
        else:
            items.append((code, folder))
    return items


def cover_items(root: Path, week: str, count: int, retry_failed: bool) -> list:
    unlinked(root, root / watch.REELS)
    base, items = watch.reels_root(root), []
    for reel in watch.week_reels(root, week):
        folder = base / reel["code"]
        if len(items) >= count:
            break
        if (folder.is_symlink() or not watch.is_measured(folder) or (folder / "cover.jpg").exists()
                or ((folder / FAILED_COVER).is_file() and not retry_failed)):
            continue
        items.append((reel["code"], folder))
    return items


def main(argv=None, root: Path = ROOT, sleep=time.sleep, clock=time.monotonic, rand=random.uniform,
         library=load_instaloader) -> int:
    parser = argparse.ArgumentParser(description="Save public Instagram posts and reel covers, logged out, for taste sessions.")
    commands = parser.add_subparsers(dest="command", required=True)
    post = commands.add_parser("post", help="an image post or a carousel, every slide")
    post.add_argument("--code", nargs="+", required=True, help="post codes, e.g. AbCdEfGhI01")
    latest = commands.add_parser("latest", help="an account's latest posts that aren't reels, as post saves them")
    latest.add_argument("--account", required=True, help="an Instagram username, e.g. someaccount")
    latest.add_argument("--count", type=int, default=6, help=f"at most this many, {LATEST[0]} to {LATEST[1]}")
    covers = commands.add_parser("covers", help="cover.jpg for the week's measured reels that have none")
    covers.add_argument("--week", required=True, help="an ISO week, e.g. 2026-W05")
    covers.add_argument("--count", type=int, default=10, help="at most this many covers")
    for command in (post, latest, covers):
        command.add_argument("--retry-failed", action="store_true", help="try failed ones again, and clear a stored stop")
    args = parser.parse_args(argv)
    if args.command == "post" and not all(watch.CODE.fullmatch(code) for code in args.code):
        raise SystemExit("refused: --code takes post codes like AbCdEfGhI01")
    if args.command == "latest" and not USERNAME.fullmatch(args.account):
        raise SystemExit("refused: --account takes an Instagram username like someaccount, not a link")
    if args.command == "latest" and args.account.lower() in NOT_ACCOUNTS:
        raise SystemExit(f"refused: {args.account} is one of Instagram's own pages, not an account")
    if args.command == "latest" and not LATEST[0] <= args.count <= LATEST[1]:
        raise SystemExit(f"refused: --count from {LATEST[0]} to {LATEST[1]} for latest: its page lists about 12")
    if args.command == "covers" and not fetch.WEEK.fullmatch(args.week):
        raise SystemExit("refused: --week like 2026-W05")
    if args.command == "covers" and args.count < 1:
        raise SystemExit("refused: --count at least 1")
    fetch.public_ok(root)
    base = posts_root(root)
    lock = hold(base)
    try:
        for stale in base.glob(".tmp-*"):  # a killed run's: no other run holds the lock
            shutil.rmtree(stale, ignore_errors=True)
        stored = base / watch.STOPPED
        if args.retry_failed:
            stored.unlink(missing_ok=True)
        held = stored_stop(stored)
        if held is not None:
            print(f"{held}\nThat's stored from an earlier run, so nothing was fetched. Only --retry-failed, on your "
                  "ORDER, clears it.")
            return 2
        if args.command == "post":
            items, record, saver = post_items(base, args.code, args.retry_failed), FAILED_POST, save_post
        elif args.command == "covers":
            items, record, saver = cover_items(root, args.week, args.count, args.retry_failed), FAILED_COVER, save_cover
        else:
            items, record, saver = None, FAILED_POST, save_post
        if items == []:
            print("nothing to save.")
            return 0
        instaloader = library()
        pace = Pace(sleep, clock, rand)
        loader = make_loader(instaloader, pace)
        try:
            if items is None:  # latest: the list comes from the account's page
                account = args.account.lower()
                try:
                    codes = latest_codes(loader.context, base, account, args.count)
                except Full:
                    print(USED_UP)
                    return 0
                except Exception as error:  # a refusal stops; anything else fails the listing alone
                    reason = refusal(error, instaloader, quiet=f"/{account}/")
                    if not reason and REDIRECTED.match(str(error)):  # not to the login page, which 4.16 names itself
                        reason = (f"Instagram redirected the profile page ({str(error)[:3]}), maybe to a challenge. "
                                  "Don't run save.py again now; report it.")
                    if reason:
                        return stop(base, reason)
                    if isinstance(error, Failed):
                        why = str(error)[:300]
                    elif isinstance(error, instaloader.QueryReturnedNotFoundException):
                        why = "no account by that name (404)"
                    else:
                        why = type(error).__name__  # never its text, which holds the address
                    print(f"{account}: not listed: {why}")
                    return 1
                items = post_items(base, codes, args.retry_failed)
                if not items:
                    print("nothing to save.")
                    return 0
            return each(items, base, record, lambda code, folder: saver(instaloader, loader, code, folder, pace, root),
                        pace, instaloader, skip=(Reel,) if args.command == "latest" else ())
        finally:
            loader.close()
    finally:
        os.close(lock)


if __name__ == "__main__":
    raise SystemExit(main())
