"""What gen/image.py and gen/video.py share: the refusals, the Gemini call and the output files (SA-005).

Refused before any call:
- a brand that isn't in company.json ("brands");
- text in the picture, for every brand: text, letters, words, captions, logos, signs, banners, posters, pages, script,
  calligraphy or verses. On-image text is rendered in code (SA-005);
- a person, face, portrait, figure, silhouette or crowd, only for a brand whose "ai_people" in company.json isn't true.
  Without that key an AI-made person may appear.
The words are matched in English. This list is a backstop, not the check: the
content-reviewer also reads every AI asset's prompt in its sidecar and looks at the image.
Every prompt then gets an instruction for no text (and, for such a brand, no people), so prompts never need to
say it (saying "no text" is refused like any other mention).

Outputs go only to workspaces/marketing/media/<brand>/<week>/<piece>/, written byte for
byte as Gemini sent them: nothing here re-encodes them or strips C2PA, SynthID or other
metadata. Each gets a sidecar <file>.json with the prompt, model, date and
`ai_generated: true`. Only the copy that goes to Instagram loses its C2PA, XMP and IPTC, when
the Board's AI label for the post is off (publish/strip_ai.py; SA-005).

The key is read at run time from the macOS keychain item `agentic-company-gemini-marketing`
(the Board creates it with `security add-generic-password -s agentic-company-gemini-marketing -a gemini -w`,
on a Google Cloud project with a budget alert).

API: the Interactions API, POST https://generativelanguage.googleapis.com/v1beta/interactions,
header x-goog-api-key, JSON {model, input, response_format, store, background}; the media is
in steps[] of type model_output, content[] of type image or video, base64 `data` plus
`mime_type`. Sources: https://ai.google.dev/gemini-api/docs/image-generation, https://ai.google.dev/gemini-api/docs/omni and the
OpenAPI spec https://ai.google.dev/static/api/interactions.openapi.json (ImageResponseFormat,
VideoResponseFormat, ModelOutputStep).
"""

import argparse
import base64
import json
import re
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools/marketing"))

import spend  # noqa: E402

sys.path.insert(0, str(ROOT / "scripts"))

from company_config import integration  # noqa: E402

KEYCHAIN_ITEM = "agentic-company-gemini-marketing"
API = "https://generativelanguage.googleapis.com/v1beta/interactions"
EXTENSIONS = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp", "video/mp4": ".mp4"}
INSTRUCTION = "\n\nNo text, letters, numbers, logos or signs anywhere in the {kind}."
NO_PEOPLE = " No people, faces, hands or human figures."

TEXT = re.compile(
    r"\b(texts?|letters?|lettering|words?|captions?|logos?|signs?|signage|typography|fonts?|titles?|headlines?"
    r"|slogans?|labels?|inscriptions?|calligraph\w*|scripts?|scriptures?|verses?|alphabets?"
    r"|banners?|posters?|billboards?|graffiti|pages?)\b", re.I)
PEOPLE = re.compile(
    r"\b(persons?|peoples?|man|men|woman|women|boys?|girls?|child|children|kids?|baby|babies|faces?|portraits?"
    r"|crowds?|human(s|oids?)?|selfies?|family|families|teens?|teenagers?|guys?|lady|ladies|someone|somebody"
    r"|figures?|silhouettes?)\b", re.I)


def read_token() -> str:
    try:
        result = subprocess.run(["security", "find-generic-password", "-s", KEYCHAIN_ITEM, "-w"], capture_output=True, text=True)
    except FileNotFoundError:
        raise SystemExit("The Gemini key is in the macOS keychain, and this system has none.") from None
    if result.returncode != 0:
        raise SystemExit(f"No Gemini key in the keychain item '{KEYCHAIN_ITEM}'. See tools/marketing/gen/gemini.py.")
    return result.stdout.strip()


def people_allowed(brand: str, root: Path) -> bool:
    marketing = integration("marketing", root)
    brands = marketing.get("brands") if isinstance(marketing, dict) else None
    settings = brands.get(brand) if isinstance(brands, dict) else None
    if not isinstance(settings, dict):
        raise ValueError(f"refused: company.json has no brand {brand} (integrations, marketing, brands)")
    return settings.get("ai_people", True) is True


def refusal(prompt: str, people: bool) -> "str | None":
    """Why the prompt can't be sent, or None. `people`: they may appear for this brand."""
    found = TEXT.search(prompt)
    if found:
        return (f"'{found.group(0)}' asks for text in the picture: on-image text is rendered in code (SA-005). "
                "Leave it out; the script already asks for no text.")
    found = not people and PEOPLE.search(prompt)
    if found:
        return (f"'{found.group(0)}' asks for a person: the Board turned AI-made people off for this brand. "
                "Leave people out; the script already asks for none.")
    return None


def interactions_send(body: dict, api_key: str) -> dict:
    request = urllib.request.Request(API, data=json.dumps(body).encode(), headers={
        "Content-Type": "application/json", "x-goog-api-key": api_key})  # the key in a header, never the URL
    with urllib.request.urlopen(request, timeout=900) as response:  # video can take minutes
        return json.load(response)


def output_media(reply: dict, kind: str) -> tuple:
    """(bytes, mime type) of the first generated image or video in a reply."""
    texts = []
    for step in reply.get("steps") or []:
        if step.get("type") != "model_output":
            continue
        for item in step.get("content") or []:
            if item.get("type") == kind and item.get("data"):
                return base64.b64decode(item["data"]), item.get("mime_type", "")
            if item.get("type") == "text":
                texts.append(item.get("text", ""))
    said = " ".join(texts + [str(e) for e in reply.get("errors") or []]).strip()
    raise RuntimeError(f"no {kind} in the reply (status {reply.get('status')}){': ' + said[:300] if said else ''}")


def why_failed(error: Exception) -> str:
    if isinstance(error, urllib.error.HTTPError):
        try:
            message = json.load(error).get("error", {}).get("message", "")
        except (ValueError, OSError, AttributeError):
            message = ""
        return f"HTTP {error.code} {message}".strip()
    return f"{type(error).__name__}: {error}"


def batch_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--brand", required=True, help="e.g. founder/demo")
    parser.add_argument("--week", required=True, help="e.g. 2026-W05")
    parser.add_argument("--piece", required=True, help="the piece's slug")
    parser.add_argument("--prompt", required=True,
                        help="what to show; no text (the script asks for none, and mentioning it is refused)")


def generate(args, kind: str, model: str, tool: str, units: float, response_format: dict, send, token, root: Path,
             measure=None) -> int:
    """Refuse, reserve the units under the cap, call Gemini, save the media and its sidecar, log the outcome.
    Returns the exit code. `measure`, for video, reads the saved file's real length; the larger of it and `units`
    is logged."""
    name = f"gen/{kind}.py"
    try:
        folder = spend.media_dir(args.brand, args.week, args.piece, root)
        people = people_allowed(args.brand, root)
        problem = refusal(args.prompt, people)
        if problem:
            raise ValueError(f"refused: {problem}")
        call = spend.reserve(tool, model, args.brand, args.week, args.piece, units, root)
    except (ValueError, OSError, spend.CapError) as error:
        print(f"{name}: {error}", file=sys.stderr)
        return 1
    prompt = args.prompt.strip() + INSTRUCTION.format(kind=kind) + ("" if people else NO_PEOPLE)
    body = {"model": model, "input": [{"type": "text", "text": prompt}], "response_format": response_format,
            "store": False, "background": False}
    try:
        data, mime = output_media(send(body, token()), kind)
    except Exception as error:  # bad key, network, quota, a blocked prompt: logged, since some failures are billed
        spend.done(call, units, False, root)
        print(f"{name}: Gemini failed: {why_failed(error)}", file=sys.stderr)
        return 1
    try:  # the call is paid for, so it's logged even if saving fails
        folder.mkdir(parents=True, exist_ok=True)
        n = 1
        while list(folder.glob(f"{kind}-{n:02}.*")):
            n += 1
        path = folder / f"{kind}-{n:02}{EXTENSIONS.get(mime, '.png' if kind == 'image' else '.mp4')}"
        path.write_bytes(data)  # as sent: no re-encoding, so C2PA and SynthID stay
        sidecar = path.with_name(path.name + ".json")
        sidecar.write_text(json.dumps({"prompt": prompt, "model": model,
                                       "date": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                       "ai_generated": True}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if measure:
            try:
                units = max(units, measure(path))
            except (ValueError, OSError):
                pass  # keep the seconds asked for
    finally:
        spend.done(call, units, True, root)
    print(f"{name}: wrote {path} and {sidecar.name} ({units:g} {spend.UNITS[tool]})")
    return 0
