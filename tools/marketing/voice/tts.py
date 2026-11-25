#!/usr/bin/env python3
"""Voice-over with ElevenLabs text-to-speech, for the brands the Board grants it, in stock voices only.

    python3 tools/marketing/voice/tts.py <text file under workspaces/marketing/media/> --voice <voice id> \
        --model <model id> --brand founder/demo --week 2026-W05 --piece <slug>

Reads the text only from workspaces/marketing/media/ (links resolved, so nothing else on
the machine can be sent). Writes workspaces/marketing/media/<brand>/<week>/<piece>/<text
file name>.mp3, and never overwrites one (each call is paid). Units are the text's
characters; the call is checked against the monthly cap first and logged after
(tools/marketing/spend.py).

The key is read at run time from the macOS keychain item `agentic-company-elevenlabs`
(see voice/scribe.py).

The grant: off until the Board says yes (GRANTED), then only for the brands company.json names. Only ElevenLabs'
stock voices, whose voice record says category "premade": no cloned, professional or "famous" voice, so no one's voice
is imitated. Each piece still needs the Board's approval in Notion and his own tap in Metricool, and is marked
ai_generated (content-qa).

API, from https://elevenlabs.io/docs/api-reference/text-to-speech/convert :
POST /v1/text-to-speech/{voice_id}?output_format=mp3_44100_128, header xi-api-key, JSON
{text, model_id}; the reply is the audio. Eleven v4 is `eleven_v4` and lists its languages
(https://elevenlabs.io/docs/overview/capabilities/text-to-speech/eleven-v4).
https://elevenlabs.io/docs/api-reference/voices/get : GET /v1/voices/{voice_id}; its `category` is one
of generated, cloned, premade, professional, famous, high_quality.
"""

import argparse
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools/marketing"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import spend  # noqa: E402
from scribe import inside, read_token, why_failed  # noqa: E402

from company_config import integration  # noqa: E402  (scribe put scripts/ on the path)

GRANTED = False  # the Board's yes to voice-over; then the platform engineer sets it
VOICES = "https://api.elevenlabs.io/v1/voices"

API = "https://api.elevenlabs.io/v1/text-to-speech"
TOOL = "elevenlabs_tts_characters"


def brands(root: Path) -> set:
    """The brands the Board granted voice-over (company.json: "brands", "voice_over": true)."""
    named = (integration("marketing", root) or {}).get("brands") or {}
    return {brand for brand, settings in named.items() if settings.get("voice_over") is True}


def tts_send(text: str, voice: str, model: str, api_key: str) -> bytes:
    url = f"{API}/{urllib.parse.quote(voice, safe='')}?output_format=mp3_44100_128"
    request = urllib.request.Request(url, data=json.dumps({"text": text, "model_id": model}).encode(), headers={
        "xi-api-key": api_key, "Content-Type": "application/json", "Accept": "audio/mpeg"})  # the key only in a header
    with urllib.request.urlopen(request, timeout=600) as response:
        return response.read()


def voice_category(voice: str, api_key: str) -> str:
    request = urllib.request.Request(f"{VOICES}/{urllib.parse.quote(voice, safe='')}", headers={"xi-api-key": api_key})
    with urllib.request.urlopen(request, timeout=60) as response:
        return str(json.load(response).get("category"))


def main(argv=None, send=tts_send, token=read_token, root: Path = ROOT, lookup=voice_category) -> int:
    parser = argparse.ArgumentParser(description="Voice-over with ElevenLabs text-to-speech (needs the Board's grant).")
    parser.add_argument("text", type=Path,
                        help="a UTF-8 text file under workspaces/marketing/media/: exactly what is spoken")
    parser.add_argument("--voice", required=True, help="the ElevenLabs voice id")
    parser.add_argument("--model", required=True, help="the ElevenLabs model id, e.g. eleven_v4")
    parser.add_argument("--brand", required=True, help="e.g. founder/demo")
    parser.add_argument("--week", required=True, help="e.g. 2026-W05")
    parser.add_argument("--piece", required=True, help="the piece's slug")
    args = parser.parse_args(argv)

    if not GRANTED:
        print("tts: refused: the Board hasn't granted ElevenLabs voice-over yet. Only scribe.py runs until then.",
              file=sys.stderr)
        return 1
    if args.brand not in brands(root):
        print(f"tts: refused: voice-over is for {', '.join(sorted(brands(root))) or 'no brand'} only; another brand needs "
              "the Board's grant.", file=sys.stderr)
        return 1
    try:
        if not inside(args.text, root / spend.MEDIA):
            raise ValueError(f"refused: {args.text} is outside {spend.MEDIA.as_posix()}/; the text is read only "
                             "from there, so nothing else can be sent")
        folder = spend.media_dir(args.brand, args.week, args.piece, root)
        text = args.text.read_text(encoding="utf-8").strip()
        if not text:
            raise ValueError(f"{args.text} is empty")
        out = folder / f"{args.text.stem}.mp3"
        if out.exists():
            raise ValueError(f"{out} exists; each call is paid, so delete it first if you mean to replace it")
        key = token()
        try:
            category = lookup(args.voice, key)
        except Exception as error:  # an unknown voice id, the network: nothing paid yet
            raise ValueError(f"couldn't read voice {args.voice}: {why_failed(error)}")
        if category != "premade":
            raise ValueError(f"refused: voice {args.voice} is '{category}'; only ElevenLabs' stock (premade) voices "
                             "are used, so no one's voice is imitated")
        call = spend.reserve(TOOL, args.model, args.brand, args.week, args.piece, len(text), root)
    except (ValueError, OSError, spend.CapError) as error:
        print(f"tts: {error}", file=sys.stderr)
        return 1
    try:
        audio = send(text, args.voice, args.model, key)
    except Exception as error:  # bad key, network, quota: logged, since some failures are billed
        spend.done(call, len(text), False, root)
        print(f"tts: ElevenLabs failed: {why_failed(error)}", file=sys.stderr)
        return 1
    spend.done(call, len(text), True, root)
    folder.mkdir(parents=True, exist_ok=True)
    out.write_bytes(audio)
    print(f"tts: wrote {out} ({len(text)} characters)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
