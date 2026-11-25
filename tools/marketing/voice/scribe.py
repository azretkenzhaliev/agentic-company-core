#!/usr/bin/env python3
"""Transcribe speech with ElevenLabs Scribe, for captions and swipe teardowns.

    python3 tools/marketing/voice/scribe.py <audio or video under workspaces/marketing/> --lang <code> \
        --out <folder under workspaces/marketing/media/ or swipe/> [--brand B --week W --piece P]

Writes <out>/<input name>.txt (the transcript), <out>/<input name>.srt (captions from
Scribe's word timestamps: lines of at most 42 characters and 2.5 s, a new line after each
sentence) and <out>/<input name>.words.json (each spoken word with its seconds, for
remotion/Captions.jsx), and refuses if any exists: each call is paid. Only files under
workspaces/marketing/ go out, so nothing else on the machine can be sent, and transcripts
go only under its media/ or swipe/ folder. Paths are compared with links resolved: the
inbox/, media/ and swipe/ folders may be links (into a synced folder, say), so their real folders count,
and any other link that points out of these folders doesn't. Units are audio seconds, read
with the bundled ffmpeg; the call is checked against the monthly cap first and logged after
(tools/marketing/spend.py).
--brand, --week and --piece only label the log line; swipe teardowns have none. The languages are company.json's
("integrations"."marketing"."languages"), each with Scribe's code for it ("scribe"); without one it refuses.

The key is read at run time from the macOS keychain item `agentic-company-elevenlabs`,
which the Board creates with `security add-generic-password -s agentic-company-elevenlabs -a elevenlabs -w`.

API, from ElevenLabs' docs:
https://elevenlabs.io/docs/api-reference/speech-to-text/convert : POST /v1/speech-to-text,
multipart form, header xi-api-key, model_id "scribe_v2", language_code (ISO-639-1 or
-3), timestamps_granularity "word"; the reply has text and words[] of {text, type:
word|spacing|audio_event, start, end} in seconds.
https://elevenlabs.io/docs/overview/capabilities/speech-to-text : each language's code and accuracy tier. A language
below the top tier needs a native speaker's check of the captions.
"""

import argparse
import http.client
import json
import mimetypes
import os
import subprocess
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools/marketing"))

import spend  # noqa: E402

sys.path.insert(0, str(ROOT / "scripts"))

from company_config import integration  # noqa: E402

KEYCHAIN_ITEM = "agentic-company-elevenlabs"
API = "https://api.elevenlabs.io/v1/speech-to-text"
MODEL = "scribe_v2"  # the model id in the API reference's examples
MARKETING = Path("workspaces/marketing")
LINKED = ("inbox", "media", "swipe")  # may be links: their real folders count as inside
OUT_FOLDERS = ("media", "swipe")
TOOL = "elevenlabs_stt_seconds"
MAX_CHARS = 42
MAX_SECONDS = 2.5
SENTENCE_END = ".?!…"


def langs(root: Path) -> dict:
    """{code: Scribe's code} for company.json's languages, e.g. {"de": "deu"}."""
    languages = (integration("marketing", root) or {}).get("languages") or {}
    return {code: language["scribe"] for code, language in languages.items() if language.get("scribe")}


def read_token() -> str:
    try:
        result = subprocess.run(["security", "find-generic-password", "-s", KEYCHAIN_ITEM, "-w"], capture_output=True, text=True)
    except FileNotFoundError:
        raise SystemExit("The ElevenLabs key is in the macOS keychain, and this system has none.") from None
    if result.returncode != 0:
        raise SystemExit(f"No ElevenLabs key in the keychain item '{KEYCHAIN_ITEM}'. See this script's docstring.")
    return result.stdout.strip()


def scribe_post(audio: Path, language_code: "str | None", api_key: str) -> bytes:
    """The reply as it came, for reels/watch.py to keep before reading it. None as the language lets Scribe detect it
    (for a reel whose language nobody noted)."""
    boundary = uuid.uuid4().hex
    fields = {"model_id": MODEL, "language_code": language_code, "timestamps_granularity": "word",
              "tag_audio_events": "false"}
    body = b"".join(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
                    for k, v in fields.items() if v is not None)
    mime = mimetypes.guess_type(audio.name)[0] or "application/octet-stream"
    body += (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="audio{audio.suffix}"\r\n'
             f"Content-Type: {mime}\r\n\r\n").encode() + audio.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
    request = urllib.request.Request(API, data=body, headers={
        "xi-api-key": api_key, "Content-Type": f"multipart/form-data; boundary={boundary}"})  # the key only in a header
    with urllib.request.urlopen(request, timeout=600) as response:
        try:
            return response.read()
        except http.client.IncompleteRead as cut:  # paid for all the same: the caller keeps what came, and can't parse it
            return cut.partial


def scribe_send(audio: Path, language_code: "str | None", api_key: str) -> dict:
    return json.loads(scribe_post(audio, language_code, api_key))


def inside(path: Path, *bases: Path) -> bool:
    """True when `path` is in one of `bases`, comparing real paths: a base that is a link still counts, and a link
    that points out of every base doesn't."""
    real = Path(os.path.realpath(path))
    return any(real.is_relative_to(os.path.realpath(base)) for base in bases)


def spoken_words(words: list) -> list:
    """Scribe's words as {text, start, end}, without spacing, audio events or words it gave no time."""
    return [{"text": word["text"].strip(), "start": word["start"], "end": word["end"]} for word in words
            if word.get("type") == "word" and (word.get("text") or "").strip()
            and word.get("start") is not None and word.get("end") is not None]


def caption_lines(words: list) -> list:
    """Group spoken words into caption lines of at most MAX_CHARS characters and MAX_SECONDS,
    starting a new line after a sentence ends."""
    lines, line = [], None
    for word in spoken_words(words):
        text = word["text"]
        if line and (line["text"][-1] in SENTENCE_END or len(line["text"]) + 1 + len(text) > MAX_CHARS
                     or word["end"] - line["start"] > MAX_SECONDS):
            lines.append(line)
            line = None
        if line is None:
            line = {"start": word["start"], "end": word["end"], "text": text}
        else:
            line["text"] += " " + text
            line["end"] = word["end"]
    return lines + [line] if line else lines


def _stamp(seconds: float) -> str:
    ms = round(seconds * 1000)
    hours, ms = divmod(ms, 3_600_000)
    minutes, ms = divmod(ms, 60_000)
    secs, ms = divmod(ms, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{ms:03}"


def to_srt(lines: list) -> str:
    return "".join(f"{i}\n{_stamp(line['start'])} --> {_stamp(line['end'])}\n{line['text']}\n\n"
                   for i, line in enumerate(lines, 1))


def why_failed(error: Exception) -> str:
    if isinstance(error, urllib.error.HTTPError):
        try:
            detail = json.load(error).get("detail", "")
        except (ValueError, OSError, AttributeError):
            detail = ""
        return f"HTTP {error.code} {detail}".strip()
    return f"{type(error).__name__}: {error}"


def main(argv=None, send=scribe_send, token=read_token, seconds=spend.media_seconds, root: Path = ROOT) -> int:
    known = langs(root)
    parser = argparse.ArgumentParser(description="Transcribe speech with ElevenLabs Scribe into .txt, .srt and .words.json.")
    parser.add_argument("audio", type=Path, help="an audio or video file under workspaces/marketing/")
    parser.add_argument("--lang", choices=sorted(known), required=True,
                        help="the main spoken language, one of company.json's")
    parser.add_argument("--out", type=Path, required=True,
                        help="a folder under workspaces/marketing/media/ or workspaces/marketing/swipe/")
    parser.add_argument("--brand", help="for the spend log, e.g. founder/demo")
    parser.add_argument("--week", help="for the spend log, e.g. 2026-W05")
    parser.add_argument("--piece", help="for the spend log, the piece's slug")
    args = parser.parse_args(argv)

    marketing = root / MARKETING
    if not inside(args.audio, marketing, *(marketing / folder for folder in LINKED)):
        print(f"scribe: refused: {args.audio} is outside {MARKETING.as_posix()}/; only files there are sent.",
              file=sys.stderr)
        return 1
    if not inside(args.out, *(marketing / folder for folder in OUT_FOLDERS)):
        print(f"scribe: refused: --out {args.out}: transcripts go only to {MARKETING.as_posix()}/media/ or "
              f"{MARKETING.as_posix()}/swipe/.", file=sys.stderr)
        return 1
    if not args.audio.is_file():
        print(f"scribe: {args.audio} not found.", file=sys.stderr)
        return 1
    txt, srt = args.out / f"{args.audio.stem}.txt", args.out / f"{args.audio.stem}.srt"
    timings = args.out / f"{args.audio.stem}.words.json"
    for path in (txt, srt, timings):
        if os.path.lexists(path):
            print(f"scribe: {path} exists; each call is paid, so delete it first if you mean to replace it.",
                  file=sys.stderr)
            return 1
    try:
        units = seconds(args.audio)
        call = spend.reserve(TOOL, MODEL, args.brand, args.week, args.piece, units, root)
    except (ValueError, OSError, spend.CapError) as error:
        print(f"scribe: {error}", file=sys.stderr)
        return 1
    try:
        reply = send(args.audio, known[args.lang], token())
    except Exception as error:  # bad key, network, quota: logged, since some failures are billed
        spend.done(call, units, False, root)
        print(f"scribe: ElevenLabs failed: {why_failed(error)}", file=sys.stderr)
        return 1
    spend.done(call, units, True, root)
    args.out.mkdir(parents=True, exist_ok=True)
    txt.write_text(reply.get("text", "").strip() + "\n", encoding="utf-8")
    srt.write_text(to_srt(caption_lines(reply.get("words") or [])), encoding="utf-8")
    timings.write_text(json.dumps(spoken_words(reply.get("words") or []), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"scribe: wrote {txt}, {srt} and {timings} ({units:g} seconds, language {reply.get('language_code', '?')})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
