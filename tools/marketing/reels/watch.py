#!/usr/bin/env python3
"""Watch a week's reels, so a format label comes from the reel and not its cover.

    python3 tools/marketing/reels/watch.py prepare --week 2026-W05 [--count 7] [--recent-only] [--retry-failed]
    python3 tools/marketing/reels/watch.py next    --week 2026-W05 [--count 7]
    python3 tools/marketing/reels/watch.py label   --week 2026-W05
    python3 tools/marketing/reels/watch.py status  --week 2026-W05
    python3 tools/marketing/reels/watch.py table   --week 2026-W05
    python3 tools/marketing/reels/watch.py measure --file workspaces/marketing/media/<brand>/<week>/<slug>/<reel>.mp4

- **Reels come only from posts.csv:** this takes a week, never a URL or a path. Each address is rebuilt from a checked
  post code; the csv's link column is never fetched. Highest views against the account's median go first.
- **measure --file** is the one exception, and never a reel: the cmo's and the producer's, for our own render under
  workspaces/marketing/media/ (a link out of it is refused). It prints the same numbers as a reel's metrics.json, and the
  longest shot. Local: no Scribe, no download, nothing written.
- **prepare** refuses where the Board turned downloading from public pages off (fetch.py, "Any public URL"). It gets
  `--count` reels ready for a breakdown (measured, not yet broken down), and does nothing if that many
  are: the count is the total ready, not how many to add. `--recent-only` counts and prepares recent reels only, so old
  ones are never pulled in. It downloads through footage/fetch.py (no cookies, no login, one video), waits about 20 s
  after each download (10-30 s at random), starts no reel after 6 minutes, stops after 3 failures in a row, and picks up
  from the files on disk. metrics.json is written last, so a reel without one is simply done again; each call fits Bash's
  10-minute limit.
- **One prepare at a time:** prepare holds an flock on reels/.prepare.lock while it runs, and a second one, any week and
  any flags, refuses at once (exit 1) and reads and fetches nothing, so it can't download over the first one's reels. The lock is the
  running process's, not the file: the system drops it when prepare ends, however it ends (a kill included), so a lock
  left by a dead process never blocks, and the file left behind is no lock. When unsure (a link there, a lock that can't
  be taken), it refuses.
- **A reel's steps share 200 s:** its download, ffmpeg runs, Scribe call and tesseract. A slower reel fails with a record,
  so Bash can't kill it with none and leave it first in the queue.
- **A failed reel** gets failed.txt with the reason and is skipped until --retry-failed. After 3 failures in a row,
  which may mean Instagram is refusing us, wait before the next run; don't push on. The spend cap, the key and
  ElevenLabs being down stop the run at once, since every later reel would hit them too.
- **A `stopped:` line is stored** in reels/stopped.txt, for every week: until --retry-failed clears it, prepare prints it
  and fetches nothing, unless the count is already ready. status prints it too.
- **status** prints the week's reels and its total to go, then recent and old reels apart, each line with its reels,
  downloaded, measured, broken down, labelled, failed and to go (neither broken down nor failed).
- **Files,** under workspaces/marketing/intelligence/reels/<code>/, never a synced folder (a link there is refused): video.mp4,
  video.info.json and MANIFEST.json (kept), caption.txt (mentions, emails and phone numbers masked,
  as in trend_reader.py's REEL_JS), scribe.seconds.txt, scribe.raw.json, scribe.json, transcript.srt, onscreen.txt,
  sheet-first3s.jpg, sheet-whole.jpg, metrics.json, then the reel-analyst's breakdown.md.
  Frames and audio are deleted as soon as they're used. Everything here is untrusted data: nothing executes it, ffmpeg
  opens only the file itself as MP4, and this script runs Python isolated (-I).
- **Measures:** length; cuts per minute and the first cut (a spike in ffmpeg's scene score against the frames around it:
  ffmpeg's usual fixed 0.3 misses cuts in a dark or boxed reel. A
  flash or a phone screen's animation can count; a dissolve doesn't); integrated loudness, range and true peak (EBU R128); words per minute over
  the spoken span and the first word; sound: no_audio, silent (under -50 LUFS), speech (at least 3 words and 30 a minute
  of reel; sung lyrics count, so the analyst checks) or music_or_other.
- **On-screen text** is a hint: tesseract every 2 s, words at 70% confidence or more, in the language company.json names
  ("ocr_language", tesseract's code, eng by default). Caption boxes read well; plain white text on a busy frame reads in
  part; small text hardly at all.
- **Paid:** one ElevenLabs Scribe call for each reel with a sound track, through
  the monthly cap in spend.py, counted from the audio sent, under the brand intelligence/reels. Its reply is saved byte
  for byte as scribe.raw.json before anything parses it, so no reel is paid for twice: one that can't be parsed stays
  failed, at no further cost. Language: Scribe always detects it; metrics.json records what it heard.
- **A breakdown counts** in prepare, next, status, label and table only with a `## ` heading for each section of the
  reel-analyst's template (SECTIONS). A label over a style-only note isn't one: its
  reel is still to go, and its label isn't copied.
- **label** copies the `format: <Carrier>: <mechanic>` first line of each breakdown into the week's rows of posts.csv,
  replacing any cover label. A carrier outside the ten in format-engine.md is refused, named and not copied; status and
  table still read an older week's labels. Don't run it while the trend-researcher is writing that file.
"""

import argparse
import csv
import fcntl
import io
import json
import math
import os
import random
import re
import shutil
import signal
import statistics
import subprocess
import sys
import time
import urllib.error
from pathlib import Path

if __name__ == "__main__" and not sys.flags.isolated:
    os.execv(sys.executable, [sys.executable, "-I", *sys.argv])

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / "tools/marketing"), str(ROOT / "tools/marketing/footage"), str(ROOT / "tools/marketing/voice")]

import fetch  # noqa: E402
import scribe  # noqa: E402
import spend  # noqa: E402

POSTS = "workspaces/marketing/intelligence/posts.csv"
REELS = "workspaces/marketing/intelligence/reels"
MEDIA = "workspaces/marketing/media"
REEL_URL = "https://www.instagram.com/reel/"
CODE = re.compile(r"[A-Za-z0-9_-]{5,40}")
PAUSE_SECONDS = 20
MAX_FAILURES = 3  # in a row
REEL_SECONDS = 200  # all of one reel's steps share this
BUDGET_SECONDS = 360  # no reel starts after this: with a reel's time and the longest pause, a call fits Bash's 600 s limit
FFMPEG_SECONDS = 180
OCR_FRAME_SECONDS = 60
SCENE_FLOOR = 0.05
SCENE_SPIKE = 5  # a cut scores this many times the frames around it; steady motion doesn't
SCENE_WINDOW = 15  # frames either side
SCENE_QUIET = 0.0005  # the least those frames count for: a still shot's are near 0
CUT_GAP_SECONDS = 0.25  # closer spikes are one cut
EDGE_SECONDS = 0.1  # a scene change this close to the start or end isn't a cut
SILENT_LUFS = -50
MIN_WORDS_FOR_RATE = 5
SPEECH_WORDS = 3
SPEECH_WORDS_PER_MINUTE = 30
OCR_FRAMES_PER_SECOND = 0.5
OCR_MAX_FRAMES = 60
OCR_CONFIDENCE = 70
OCR_MIN_WORD = 4  # a line needs one real word of this many letters; shorter is mostly noise or a phone's clock
TESSERACT = shutil.which("tesseract") or shutil.which("tesseract", path="/opt/homebrew/bin")
LABEL_LINE = re.compile(r"format:\s*([^\s|=+\-@][^|]*)")  # a table cell, never a spreadsheet formula
MAX_LABEL = 60
CARRIERS = ("Talking head", "Skit", "Series episode", "Text reel", "Voice-over on b-roll", "Trend", "Vlog or montage",
            "Live performance", "Explainer", "Other")  # word for word, knowledge/marketing/format-engine.md
SECTIONS = ("Answer", "Hook", "Beats", "Format", "Pacing", "Caption and on-screen text", "Sound", "Call to action",
            "Why it holds attention", "What to adapt", "What NOT to copy", "Caveats")  # reel-analyst.md's template
MENTION = re.compile(r"[\w.+-]*@[\w.]+")  # this and PHONE as in trend_reader.py's REEL_JS: no one's handle or contact
PHONE = re.compile(r"\+?\d(?:[ ()-]*\d){8,}")  # 9 digits or more, so dates and prices stay
STOPPED = "stopped.txt"  # under reels/: Instagram refusing us, the key or the cap, none of them one week's
PREPARE_LOCK = ".prepare.lock"  # under reels/, for every week
BUSY = ("refused: another watch.py prepare is running; start no second one: wait for its report, or for its reel folders "
        "to stop changing")
LOUD_KEYS = ("integrated_lufs", "range_lu", "true_peak_dbfs")
# ffmpeg prints the real lines at exactly two spaces, after the file's metadata. Metadata is deeper, but a key can hold a
# newline and print at two spaces as well: so the last match, and Scribe's seconds come from the wav, not here.
DURATION_LINE = re.compile(r"^  Duration: (\d+):(\d\d):(\d\d(?:\.\d+)?)", re.M)
AUDIO_LINE = re.compile(r"^  Stream #.*: Audio: ", re.M)
WAV_BYTES_PER_SECOND = 32000  # the wav transcribe makes: 16 kHz, mono, 16-bit
REEL_BRAND = "intelligence/reels"  # for the spend log: spend.py --brand intelligence/reels --week <w>
OUT_OF_TIME = f"out of time: a reel gets {REEL_SECONDS} s"
reel_time = None  # while prepare works on a reel: a function giving the seconds left of its REEL_SECONDS


class ReelError(Exception):
    """This reel can't be watched; it counts toward the failures in a row."""


class Stop(Exception):
    """Something every later reel would hit too: end the run."""


def write_atomic(path: Path, data: "str | bytes") -> None:
    temp = path.with_name(path.name + ".tmp")
    temp.write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))
    os.replace(temp, path)


def left(limit: float) -> float:
    """A step's timeout: its own limit, or what's left of the reel's time if that's less. None left fails the reel."""
    if reel_time is None:
        return limit
    seconds = reel_time()
    if seconds <= 0:
        raise ReelError(OUT_OF_TIME)
    return min(limit, seconds)


# ---- the week's reels -----------------------------------------------------------------------------------------

def number(text) -> float:
    try:
        value = float(text)
    except (TypeError, ValueError):
        return 0.0
    return value if math.isfinite(value) else 0.0


def read_posts(root: Path) -> list:
    with (root / POSTS).open(newline="", encoding="utf-8") as f:
        return list(csv.reader(f))


def week_reels(root: Path, week: str) -> list:
    """The week's Instagram reels, one per post code: recent ones first, then old ones, which stay queued, each highest
    multiple first. An old reel's multiple has had years to grow, so it never goes ahead."""
    rows = read_posts(root)
    reels = {}
    for row in rows[1:]:
        post = dict(zip(rows[0], row))
        if post.get("week") != week or post.get("platform") != "instagram":
            continue
        code = post.get("post_code") or ""
        if not CODE.fullmatch(code):
            print(f"skipped a row with a bad post code: {code[:40]!r}")
            continue
        multiple = number(post.get("multiple"))
        if code not in reels or multiple > reels[code]["multiple"]:
            reels[code] = {"code": code, "account": post.get("account") or "", "views": number(post.get("views")),
                           "multiple": multiple, "format": post.get("format") or "", "recent_or_old": post.get("recent_or_old") or ""}
    return sorted(reels.values(), key=lambda reel: (reel["recent_or_old"] != "recent", -reel["multiple"], reel["code"]))


def reels_root(root: Path) -> Path:
    base = root / REELS
    for path in (base.parent, base):
        if path.is_symlink():
            raise SystemExit(f"refused: {path} is a link; reels stay on this disk, not in a synced folder")
    base.mkdir(parents=True, exist_ok=True)
    return base


def is_measured(folder: Path) -> bool:
    return (folder / "metrics.json").is_file()


def is_broken_down(folder: Path) -> bool:
    """breakdown.md with a `## ` heading for each of SECTIONS. A label line over a style note ("Style-only run, ...: no
    breakdown; see style.md.") isn't one: that reel wasn't watched, so it stays to go."""
    try:
        lines = (folder / "breakdown.md").read_text(encoding="utf-8").splitlines()
    except (OSError, ValueError):
        return False
    headings = [line[3:] for line in lines if line.startswith("## ")]
    return all(any(heading.startswith(name) for heading in headings) for name in SECTIONS)


def is_ready(folder: Path) -> bool:
    return is_measured(folder) and not is_broken_down(folder)


# ---- download -------------------------------------------------------------------------------------------------

def download(code: str, folder: Path, root: Path = ROOT) -> None:
    """One reel, through fetch.py's rules, into a clean folder first: its manifest appends, and a half-done
    download must not look like a reel."""
    temp = folder.with_name(f".tmp-{code}")
    shutil.rmtree(temp, ignore_errors=True)
    temp.mkdir()
    try:
        fetch._get_url(fetch.public_url(f"{REEL_URL}{code}/"), temp, fetch.caps(root), timeout=left(REEL_SECONDS))
        video = temp / "video.mp4"
        if not video.is_file():
            raise ReelError("the download isn't an MP4")
        folder.mkdir(exist_ok=True)
        for part in sorted(temp.iterdir(), key=lambda path: path == video):  # the video last: it means the rest is there
            os.replace(part, folder / part.name)
    except subprocess.TimeoutExpired:  # prepare words this one: its text is the whole command line
        raise
    except (SystemExit, OSError, ValueError, subprocess.SubprocessError) as error:
        raise ReelError(str(error)) from None
    finally:
        shutil.rmtree(temp, ignore_errors=True)


# ---- measures -------------------------------------------------------------------------------------------------

def ffmpeg(video: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([str(fetch.FFMPEG), "-hide_banner", "-nostdin", "-protocol_whitelist", "file", "-f", "mov",
                           "-i", str(video), *args], capture_output=True, encoding="utf-8", errors="replace",
                          timeout=left(FFMPEG_SECONDS))


def ffmpeg_ok(video: Path, *args: str) -> subprocess.CompletedProcess:
    result = ffmpeg(video, *args)
    if result.returncode != 0:
        raise ReelError(f"ffmpeg failed: {result.stderr.strip()[-200:]}")
    return result


def probe(video: Path) -> tuple:
    """(length in seconds, whether there's a sound track), from what ffmpeg prints for `-i` alone."""
    stderr = ffmpeg(video).stderr
    matches = DURATION_LINE.findall(stderr)
    if not matches:
        raise ReelError("ffmpeg can't read its length")
    hours, minutes, seconds = matches[-1]
    length = int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    if length <= 0:
        raise ReelError("the video has no length")
    return length, bool(AUDIO_LINE.search(stderr))


def pick_cuts(scores: list) -> list:
    """The times of the spikes in [(time, scene score)], one per frame. No fixed threshold: a black box scales every score down."""
    cuts = []
    for index, (time_, score) in enumerate(scores):
        if score < SCENE_FLOOR:
            continue
        around = [other for _, other in scores[max(0, index - SCENE_WINDOW):index] + scores[index + 1:index + SCENE_WINDOW + 1]]
        if score < SCENE_SPIKE * max(statistics.median(around or [0]), SCENE_QUIET):
            continue
        if not cuts or time_ - cuts[-1][0] >= CUT_GAP_SECONDS:
            cuts.append((time_, score))
        elif score > cuts[-1][1]:
            cuts[-1] = (time_, score)
    return [time_ for time_, _ in cuts]


def scene_cuts(video: Path, length: float) -> list:
    stdout = ffmpeg_ok(video, "-map", "0:v:0", "-an", "-vf", "select='gte(scene,0)',metadata=print:file=-",
                       "-f", "null", "-").stdout
    scores = [(float(time_), float(score)) for time_, score
              in re.findall(r"pts_time:([\d.]+)\s+lavfi\.scene_score=([\d.]+)", stdout)]
    return [round(time_, 2) for time_ in pick_cuts(scores) if EDGE_SECONDS < time_ < length - EDGE_SECONDS]


def parse_loudness(stderr: str) -> dict:
    """The Summary block of ffmpeg's ebur128 filter. A silent track prints I: -70.0 and Peak: -inf, which JSON can't hold: None."""
    summary = stderr[stderr.rfind("Summary:"):]
    found = {}
    for key, pattern in zip(LOUD_KEYS, (r"\bI:\s+(-?[\d.]+|-?inf|nan) LUFS", r"\bLRA:\s+(-?[\d.]+|-?inf|nan) LU\b",
                                        r"\bPeak:\s+(-?[\d.]+|-?inf|nan) dBFS")):
        match = re.search(pattern, summary)
        value = float(match.group(1)) if match else math.nan
        found[key] = value if math.isfinite(value) else None
    return found


def video_numbers(video: Path) -> tuple:
    """(length, whether there's a sound track, cut times, loudness)."""
    length, has_audio = probe(video)
    cuts = scene_cuts(video, length)
    loudness = dict.fromkeys(LOUD_KEYS)
    if has_audio:
        loudness = parse_loudness(ffmpeg_ok(video, "-vn", "-af", "ebur128=peak=true", "-f", "null", "-").stderr)
    return length, has_audio, cuts, loudness


def contact_sheets(video: Path, folder: Path, length: float) -> dict:
    """sheet-first3s.jpg: 6 frames, 0.5 s apart. sheet-whole.jpg: up to 24 frames across the reel, in rows of 6."""
    single_image = ("-frames:v", "1", "-q:v", "4", "-f", "image2", "-update", "1", "-y")
    ffmpeg_ok(video, "-t", "3", "-vf", "fps=2,scale=320:-2,tile=6x1", *single_image, str(folder / "sheet-first3s.jpg"))
    tiles = min(24, max(6, math.ceil(length * 2)))
    rows = math.ceil(tiles / 6)
    ffmpeg_ok(video, "-vf", f"fps={tiles / length:.5f},scale=240:-2,tile=6x{rows}", *single_image, str(folder / "sheet-whole.jpg"))
    return {"columns": 6, "rows": rows, "seconds_per_tile": round(length / tiles, 2)}


def tsv_lines(tsv: str) -> list:
    """Lines from tesseract's tsv output: words at OCR_CONFIDENCE or more, lines with one real word."""
    lines = {}
    for row in csv.DictReader(io.StringIO(tsv), delimiter="\t", quoting=csv.QUOTE_NONE):
        word = (row.get("text") or "").strip()
        if word and number(row.get("conf")) >= OCR_CONFIDENCE:
            lines.setdefault((row.get("block_num"), row.get("par_num"), row.get("line_num")), []).append(word)
    return [" ".join(words) for words in lines.values() if any(len(word) >= OCR_MIN_WORD and word.isalpha() for word in words)]


def ocr_language(root: Path = ROOT) -> str:
    return (fetch.integration("marketing", root) or {}).get("ocr_language") or "eng"


def on_screen(video: Path, folder: Path, length: float) -> list:
    """`mm:ss text` for each distinct line, at its first sight. The frames are always deleted."""
    if not TESSERACT:
        return ["(not read: tesseract isn't installed)"]
    frames = folder / "frames"
    shutil.rmtree(frames, ignore_errors=True)
    frames.mkdir()
    rate = min(OCR_FRAMES_PER_SECOND, OCR_MAX_FRAMES / length)
    found, seen = [], set()
    try:
        ffmpeg_ok(video, "-vf", f"fps={rate:.5f},scale=720:-2", "-f", "image2", "-y", str(frames / "f-%04d.png"))
        for index, frame in enumerate(sorted(frames.glob("f-*.png"))):
            read = subprocess.run([TESSERACT, str(frame), "-", "-l", ocr_language(), "--psm", "11", "tsv"], capture_output=True,
                                  encoding="utf-8", errors="replace", timeout=left(OCR_FRAME_SECONDS))
            if read.returncode != 0:  # no model, or a crash: never the same as no text
                return found + [f"(not read: tesseract failed: {' '.join(read.stderr.split())[-200:]})"]
            for line in tsv_lines(read.stdout):
                if line.casefold() not in seen:
                    seen.add(line.casefold())
                    found.append(f"{int(index / rate) // 60:02}:{int(index / rate) % 60:02} {line}")
    finally:
        shutil.rmtree(frames, ignore_errors=True)
    return found


def scribe_reply(video: Path, folder: Path, reel: dict, week: str, root: Path, send, token) -> tuple:
    """The paid step: the reply's bytes and the seconds sent, on disk before anything parses them, so no reel is paid for
    twice. The seconds go first: a scribe.raw.json means both are there."""
    raw, sent = folder / "scribe.raw.json", folder / "scribe.seconds.txt"
    if raw.is_file():
        return raw.read_bytes(), float(sent.read_text(encoding="utf-8"))
    wav = folder / "audio.wav"
    try:
        ffmpeg_ok(video, "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", "-f", "wav", "-y", str(wav))
        seconds = wav.stat().st_size / WAV_BYTES_PER_SECOND  # what's sent, whatever the file says of itself
        try:
            key = token()
        except SystemExit as error:  # the key is missing: every later reel would hit it too
            raise Stop(str(error)) from None
        try:
            call = spend.reserve(scribe.TOOL, scribe.MODEL, REEL_BRAND, week, reel["code"], seconds, root)
        except spend.CapError as error:
            raise Stop(str(error)) from None
        try:
            body = send(wav, None, key)  # Scribe detects it: the table's language comes from covers and captions
        except Exception as error:  # bad key, network, quota: logged, since some failures are billed
            spend.done(call, seconds, False, root)
            if isinstance(error, ReelError):  # the reel's time ran out: this reel, not the service
                raise
            if isinstance(error, urllib.error.HTTPError) and error.code in (400, 422):  # this audio, not the service
                raise ReelError(f"ElevenLabs refused its audio: {scribe.why_failed(error)}") from None
            raise Stop(f"ElevenLabs failed: {scribe.why_failed(error)}") from None
        spend.done(call, seconds, True, root)
    finally:
        wav.unlink(missing_ok=True)
    write_atomic(sent, f"{seconds}\n")
    write_atomic(raw, body)
    return body, seconds


def transcribe(video: Path, folder: Path, reel: dict, week: str, root: Path, send, token) -> dict:
    """scribe.json, parsed from the reply scribe_reply saved. A reply it can't parse fails this reel and costs nothing again."""
    saved = folder / "scribe.json"
    if saved.is_file():
        return json.loads(saved.read_text(encoding="utf-8"))
    body, seconds = scribe_reply(video, folder, reel, week, root, send, token)
    try:
        reply = json.loads(body)
        kept = {"text": reply.get("text") or "", "seconds": round(seconds, 2), "language_code": reply.get("language_code"),
                "language_probability": reply.get("language_probability"),
                "words": [{"text": word["text"], "type": "word", "start": word["start"], "end": word["end"]}
                          for word in reply.get("words") or []
                          if word.get("type") == "word" and (word.get("text") or "").strip()
                          and word.get("start") is not None and word.get("end") is not None]}
    except (ValueError, AttributeError, KeyError, TypeError) as error:
        raise ReelError(f"Scribe's reply can't be read (kept in scribe.raw.json): {error!r}") from None
    write_atomic(saved, json.dumps(kept, ensure_ascii=False, indent=1) + "\n")
    return kept


def speech_numbers(words: list) -> dict:
    if not words:
        return {"words": 0, "words_per_minute": None, "first_word_seconds": None}
    span = words[-1]["end"] - words[0]["start"]
    rate = round(len(words) / span * 60, 1) if len(words) >= MIN_WORDS_FOR_RATE and span > 0 else None
    return {"words": len(words), "words_per_minute": rate, "first_word_seconds": round(words[0]["start"], 2)}


def sound_kind(has_audio: bool, lufs, words: int, length: float) -> str:
    if not has_audio:
        return "no_audio"
    if lufs is not None and lufs < SILENT_LUFS:
        return "silent"
    if words >= SPEECH_WORDS and words / length * 60 >= SPEECH_WORDS_PER_MINUTE:
        return "speech"
    return "music_or_other"


def caption_of(folder: Path) -> str:
    try:
        info = json.loads((folder / "video.info.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    description = info.get("description") if isinstance(info, dict) else None
    return description if isinstance(description, str) else ""


def masked(text: str) -> str:
    return PHONE.sub("...", MENTION.sub("@...", text))


def out_of_time(signum, frame):
    raise ReelError(OUT_OF_TIME)


def send_audio(audio: Path, language_code: "str | None", api_key: str) -> bytes:
    """Scribe's reply, by the reel's deadline. The alarm holds it: a socket's timeout counts one read at a time, so a reply
    trickling in would outlast one. signal needs the main thread, which prepare is. A name lookup isn't cut until it returns."""
    seconds = left(REEL_SECONDS)
    before = signal.signal(signal.SIGALRM, out_of_time)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        return scribe.scribe_post(audio, language_code, api_key)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, before)


def measure(folder: Path, reel: dict, week: str, root: Path = ROOT, send=send_audio, token=scribe.read_token) -> dict:
    video = folder / "video.mp4"
    length, has_audio, cuts, loudness = video_numbers(video)
    sheet = contact_sheets(video, folder, length)
    lufs = loudness["integrated_lufs"]
    heard = has_audio and not (lufs is not None and lufs < SILENT_LUFS)  # None: not read, so a cent rather than no transcript
    transcript = transcribe(video, folder, reel, week, root, send, token) if heard else {}
    words = transcript.get("words") or []
    write_atomic(folder / "transcript.srt", scribe.to_srt(scribe.caption_lines(words)))
    write_atomic(folder / "onscreen.txt", "".join(f"{line}\n" for line in on_screen(video, folder, length)))
    write_atomic(folder / "caption.txt", masked(caption_of(folder)) + "\n")
    metrics = {"code": reel["code"], "account": reel["account"], "views": reel["views"], "multiple": reel["multiple"],
               "length_seconds": round(length, 2), "cuts": len(cuts), "cuts_per_minute": round(len(cuts) / length * 60, 1),
               "first_cut_seconds": cuts[0] if cuts else None, "cut_times": cuts, **speech_numbers(words),
               "sound": sound_kind(has_audio, lufs, len(words), length), "language": transcript.get("language_code"),
               "language_probability": transcript.get("language_probability"), **loudness, "sheet_whole": sheet,
               "scribe_seconds": transcript.get("seconds", 0)}
    write_atomic(folder / "metrics.json", json.dumps(metrics, ensure_ascii=False, indent=1) + "\n")
    return metrics


# ---- commands -------------------------------------------------------------------------------------------------

def stop_run(base: Path, reason: str) -> int:
    """Stored, so a rerun is stopped by more than the words of the role's file."""
    line = f"stopped: {reason}"
    write_atomic(base / STOPPED, line + "\n")
    print(line)
    return 2


def hold(base: Path) -> int:
    """PREPARE_LOCK, held until the run ends, or a refusal. The system drops an flock when its process ends, however it
    ends, so only a live run can hold it. Any other fault refuses too: when unsure, two downloads are the worse case."""
    lock = None
    try:
        lock = os.open(base / PREPARE_LOCK, os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return lock
    except OSError as error:
        if lock is not None:
            os.close(lock)
        if isinstance(error, BlockingIOError):
            raise SystemExit(BUSY) from None
        raise SystemExit(f"refused: reels/{PREPARE_LOCK} can't be locked ({error.strerror or error}), so another prepare "
                         "may be running; report it") from None


def prepare(root: Path, week: str, count: int, retry_failed: bool = False, get=download, watch=measure,
            sleep=time.sleep, clock=time.monotonic, recent_only: bool = False) -> int:
    """One run at a time: the lock comes before anything else is read or fetched."""
    lock = hold(reels_root(root))
    try:
        return prepare_held(root, week, count, retry_failed, get, watch, sleep, clock, recent_only)
    finally:
        os.close(lock)


def prepare_held(root: Path, week: str, count: int, retry_failed: bool, get, watch, sleep, clock, recent_only: bool) -> int:
    global reel_time
    reels = week_reels(root, week)
    if recent_only:
        reels = [reel for reel in reels if reel["recent_or_old"] == "recent"]
    base = reels_root(root)
    stored = base / STOPPED
    if retry_failed:
        stored.unlink(missing_ok=True)
    missing = count - sum(is_ready(base / reel["code"]) for reel in reels)
    if missing <= 0:
        print(f"{count} or more reels are ready for a breakdown: nothing to prepare.")
        return 0
    if stored.is_file():
        print(f"{stored.read_text(encoding='utf-8').strip()}\nThat's stored from an earlier run, so nothing was fetched. "
              "Only --retry-failed, on your ORDER, clears it.")
        return 2
    started, failures, made = clock(), [], 0
    for reel in reels:
        folder = base / reel["code"]
        if made >= missing:
            break
        if is_measured(folder) or ((folder / "failed.txt").is_file() and not retry_failed):
            continue
        if clock() - started >= BUDGET_SECONDS:
            print(f"out of time for one call: run prepare again after these {made} reels.")
            break
        fetched = not (folder / "video.mp4").is_file()
        began = clock()
        reel_time = lambda: began + REEL_SECONDS - clock()
        try:
            if fetched:
                get(reel["code"], folder, root)
            metrics = watch(folder, reel, week, root)
        except Stop as error:
            return stop_run(base, str(error))
        except Exception as error:  # whatever a reel's files can do fails that reel, and counts toward the run of failures
            reason = (str(error) or type(error).__name__)[:300]
            if isinstance(error, subprocess.TimeoutExpired):  # never its text, which is the whole command line
                reason = OUT_OF_TIME if reel_time() <= 0 else f"a step ran past its own limit of {error.timeout:.0f} s"
            failures.append(reason)
            folder.mkdir(exist_ok=True)
            write_atomic(folder / "failed.txt", reason + "\n")
            print(f"{reel['code']}: failed: {reason}")
            if len(failures) >= MAX_FAILURES:
                return stop_run(base, f"{MAX_FAILURES} failures in a row, which may mean Instagram is refusing us. Don't run "
                                      f"prepare again now; report it. --retry-failed retries these later. Last reason: {reason}")
        else:
            failures = []
            (folder / "failed.txt").unlink(missing_ok=True)
            made += 1
            print(f"{reel['code']}: {metrics['length_seconds']} s, {metrics['cuts_per_minute']} cuts/min, "
                  f"{metrics['sound']}, {clock() - began:.0f} s to prepare")
        finally:
            reel_time = None
        if fetched and made < missing:
            sleep(random.uniform(PAUSE_SECONDS * 0.5, PAUSE_SECONDS * 1.5))
    print(f"prepared {made} this run.")
    return 0


def format_label(path: Path) -> str:
    """The label on a breakdown's first line. Raises ValueError if the line is wrong."""
    first = path.read_text(encoding="utf-8").split("\n", 1)[0].strip()
    match = LABEL_LINE.fullmatch(first)
    if not match or len(match.group(1)) > MAX_LABEL:
        raise ValueError(f"{path.parent.name}: the first line must be 'format: <label of at most {MAX_LABEL} characters>', "
                         "with no | and not starting with = + - @")
    return match.group(1)


def carrier_label(path: Path) -> str:
    """A label posts.csv may take. Only here, so status and table still read an older week's labels."""
    text = format_label(path)
    carrier, _, mechanic = text.partition(": ")
    if carrier not in CARRIERS or not mechanic:
        raise ValueError(f"{path.parent.name}: '{text}' isn't '<Carrier>: <mechanic>' with one of the ten: {', '.join(CARRIERS)}")
    return text


def label(root: Path, week: str) -> int:
    base = reels_root(root)
    labels, wrong = {}, []
    for reel in week_reels(root, week):
        path = base / reel["code"] / "breakdown.md"
        if is_broken_down(path.parent):
            try:
                labels[reel["code"]] = carrier_label(path)
            except ValueError as error:
                wrong.append(str(error))
    rows = read_posts(root)
    header = rows[0]
    week_at, code_at, format_at = header.index("week"), header.index("post_code"), header.index("format")
    changed = 0
    for row in rows[1:]:
        if len(row) > max(week_at, code_at) and row[week_at] == week and row[code_at] in labels:
            row.extend([""] * (len(header) - len(row)))
            if row[format_at] != labels[row[code_at]]:
                row[format_at] = labels[row[code_at]]
                changed += 1
    if changed:
        out = io.StringIO()
        csv.writer(out, lineterminator="\n").writerows(rows)
        write_atomic(root / POSTS, out.getvalue())
    print(f"labelled {changed} rows from {len(labels)} breakdowns.")
    for line in wrong:
        print(line)
    return 1 if wrong else 0


def label_of(folder: Path) -> "str | None":
    if not is_broken_down(folder):
        return None
    try:
        return format_label(folder / "breakdown.md")
    except (OSError, ValueError):
        return None


def read_metrics(folder: Path) -> dict:
    return json.loads((folder / "metrics.json").read_text(encoding="utf-8"))


def next_up(root: Path, week: str, count: int) -> int:
    base = reels_root(root)
    ready = [reel for reel in week_reels(root, week) if is_ready(base / reel["code"])]
    print(f"{len(ready)} ready for a breakdown; the next {min(count, len(ready))}, in {REELS}/<code>/:")
    for reel in ready[:count]:
        metrics = read_metrics(base / reel["code"])
        age = "recent" if reel["recent_or_old"] == "recent" else "old"
        print(f"{reel['code']}  {reel['account']}  {age}  x{reel['multiple']:g}  {metrics['length_seconds']} s  {metrics['sound']}  "
              f"{metrics['language'] or '-'}")
    return 0


def status(root: Path, week: str) -> int:
    base = reels_root(root)
    reels = week_reels(root, week)
    folders = [base / reel["code"] for reel in reels]
    to_go = len(reels) - sum(map(is_broken_down, folders)) - sum((folder / "failed.txt").is_file() for folder in folders)
    print(f"{week}: {len(reels)} reels, {to_go} to go (neither broken down nor failed). Each line counts only its own:")
    for name, recent in (("recent", True), ("old", False)):
        group = [reel for reel in reels if (reel["recent_or_old"] == "recent") == recent]
        folders = [base / reel["code"] for reel in group]
        done, failed = sum(map(is_broken_down, folders)), sum((folder / "failed.txt").is_file() for folder in folders)
        labelled = sum(1 for reel, folder in zip(group, folders) if reel["format"] and reel["format"] == label_of(folder))
        print(f"{name}: {len(group)} reels, {sum((folder / 'video.mp4').is_file() for folder in folders)} downloaded, "
              f"{sum(map(is_measured, folders))} measured, {done} broken down, {labelled} labelled, {failed} failed, "
              f"{len(group) - done - failed} to go.")
    if (base / STOPPED).is_file():
        print((base / STOPPED).read_text(encoding="utf-8").strip())
    return 0


def median(values: list) -> "float | None":
    values = [value for value in values if value is not None]
    return round(statistics.median(values), 1) if values else None


def format_rows(groups: dict) -> None:
    print("| format | reels | accounts | median multiple | top multiple | median length s | median cuts/min | median words/min | speech | top reels |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for name, group in sorted(groups.items(), key=lambda item: (-median([g["multiple"] for g in item[1]]), item[0])):
        top = sorted(group, key=lambda g: -g["multiple"])
        print(f"| {name} | {len(group)} | {len({g['account'] for g in group})} | {median([g['multiple'] for g in group])} | "
              f"{top[0]['multiple']:g} | {median([g['length_seconds'] for g in group])} | {median([g['cuts_per_minute'] for g in group])} | "
              f"{median([g['words_per_minute'] for g in group])} | {sum(g['sound'] == 'speech' for g in group)}/{len(group)} | "
              f"{' '.join(g['code'] for g in top[:3])} |")


def table(root: Path, week: str) -> int:
    """Per format label, for reels/<week>-formats.md. `multiple` is views against the median of the account's 9 newest
    reels: the weight of every pattern. So only recent reels make the patterns; old ones print apart."""
    base = reels_root(root)
    reels = week_reels(root, week)
    recent, old = {}, {}
    for reel in reels:
        folder = base / reel["code"]
        name = label_of(folder)
        if name and is_measured(folder):
            groups = recent if reel["recent_or_old"] == "recent" else old
            groups.setdefault(name, []).append({**read_metrics(folder), **reel})
    recent_count, old_count = sum(map(len, recent.values())), sum(map(len, old.values()))
    print(f"{recent_count + old_count} of {len(reels)} reels have a labelled breakdown.")
    print(f"\nRecent, {recent_count}: the patterns.\n")
    format_rows(recent)
    print(f"\nOld, {old_count}: apart, never in the patterns.\n")
    format_rows(old)
    return 0


def longest_shot(cuts: list, length: float) -> float:
    edges = [0, *cuts, length]
    return round(max(after - before for before, after in zip(edges, edges[1:])), 2)


def measure_file(root: Path, file: str) -> int:
    """Our own render's numbers, for content-qa's warnings: local, nothing paid, nothing written."""
    video = Path(file).resolve()
    if not video.is_relative_to((root / MEDIA).resolve()) or not video.is_file():
        raise SystemExit(f"refused: --file takes a render under {MEDIA}/")
    try:
        length, _, cuts, loudness = video_numbers(video)
    except (ReelError, subprocess.TimeoutExpired) as error:
        raise SystemExit(f"can't measure it: {error}") from None
    print(json.dumps({"length_seconds": round(length, 2), "cuts": len(cuts), "cuts_per_minute": round(len(cuts) / length * 60, 1),
                      "first_cut_seconds": cuts[0] if cuts else None, "longest_shot_seconds": longest_shot(cuts, length),
                      "cut_times": cuts, **loudness}))
    return 0


def main(argv=None, root: Path = ROOT) -> int:
    parser = argparse.ArgumentParser(description="Watch a week's reels from posts.csv for the reel-analyst's breakdowns.")
    commands = parser.add_subparsers(dest="command", required=True)
    for name, about in (("prepare", "download, measure and transcribe reels until --count are ready"),
                        ("next", "list the reels ready for a breakdown"), ("label", "copy breakdowns' format labels into posts.csv"),
                        ("status", "count the week's progress"), ("table", "the week's numbers per format")):
        command = commands.add_parser(name, help=about)
        command.add_argument("--week", required=True, help="an ISO week, e.g. 2026-W05")
        if name in ("prepare", "next"):
            command.add_argument("--count", type=int, default=7, help="how many reels; for prepare, the total ready, not how many to add")
        if name == "prepare":
            command.add_argument("--retry-failed", action="store_true", help="try reels with a failed.txt again, and clear a stored stop")
            command.add_argument("--recent-only", action="store_true", help="count and prepare recent reels only")
    commands.add_parser("measure", help="our own render's numbers: local, nothing written").add_argument(
        "--file", required=True, help=f"a render under {MEDIA}/")
    args = parser.parse_args(argv)
    if args.command == "measure":
        return measure_file(root, args.file)
    if not fetch.WEEK.fullmatch(args.week):
        raise SystemExit("refused: --week like 2026-W05")
    if getattr(args, "count", 1) < 1:
        raise SystemExit("refused: --count at least 1")
    if args.command == "prepare":
        fetch.public_ok(root)
        return prepare(root, args.week, args.count, args.retry_failed, recent_only=args.recent_only)
    if args.command == "next":
        return next_up(root, args.week, args.count)
    return {"label": label, "status": status, "table": table}[args.command](root, args.week)


if __name__ == "__main__":
    raise SystemExit(main())
