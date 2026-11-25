#!/usr/bin/env python3
"""Stage an approved piece for Metricool: upload its media to B2 and print the createScheduledPost arguments.

    python3 tools/marketing/publish/stage_item.py <knowledge/marketing/founder/<account>/content/<week>/<slug>.md>

The cmo runs it after the Board's decision is synced, then calls Metricool's createScheduledPost
with the printed JSON, unchanged. The hook rebuilds the same arguments from the page and allows only
that call, with autoPublish false: at an Instagram post's time Metricool's app notifies the Board, who
publishes it himself. A Short may publish at its set time, always private.

Refuses unless tools/marketing/publish/post.py finds nothing wrong: exactly one approvals row for the
page, Approved, with no note, on the page as it is now; a well-formed
`## Post` section; every file unchanged since its hash went on the page and present on this computer;
Publish at 2 hours to 6 days ahead; the brand's Metricool id and the B2 bucket configured; not
already scheduled. Each file is read once, and those bytes are checked, hashed and uploaded as
posts/<item_id>/<sha256>-<file> (B2 checks the SHA-1 on upload). When the Board's AI label is off, an Instagram
post's files go up without their C2PA, XMP and IPTC (strip_ai.py; SA-005), still under the approved file's SHA-256,
and a file with any left, or one strip_ai.py can't parse, is refused. One download authorization for
posts/<item_id>/ lasts until 24 hours after Publish at, at most B2's 7 days. A log without the token
goes to workspaces/marketing/staged/<item_id>.json.

The B2 application key, restricted to the one bucket, is read at run time from the macOS keychain item
`agentic-company-b2-media` as <keyID>:<applicationKey> (the Board: `security add-generic-password
-s agentic-company-b2-media -a b2 -w`); on another system there is none, and nothing is staged. It and the token go only in request headers and the printed
arguments.

B2 native API v4, from Backblaze's docs: b2_authorize_account (Basic auth; the reply's
apiInfo.storageApi has apiUrl, downloadUrl and allowed.buckets[] of id and name; v4 moved the bucket there), b2_get_upload_url, b2_upload_file
(X-Bz-File-Name, X-Bz-Content-Sha1), b2_get_download_authorization (fileNamePrefix,
validDurationInSeconds 1 to 604,800); a download by name takes the token as ?Authorization=.
"""

import base64
import hashlib
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools/marketing/publish"))

import post  # noqa: E402
import strip_ai  # noqa: E402

KEYCHAIN_ITEM = "agentic-company-b2-media"
AUTHORIZE = "https://api.backblazeb2.com/b2api/v4/b2_authorize_account"
STAGED = Path("workspaces/marketing/staged")
MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".mp4": "video/mp4"}
MAX_VALID = 604800  # B2's longest download authorization: one week


def read_key() -> str:
    try:
        result = subprocess.run(["security", "find-generic-password", "-s", KEYCHAIN_ITEM, "-w"], capture_output=True, text=True)
    except FileNotFoundError:
        raise post.Refused("the B2 key is in the macOS keychain, and this system has none") from None
    if result.returncode != 0:
        raise post.Refused(f"no B2 key in the keychain item '{KEYCHAIN_ITEM}'; see this script's docstring")
    return result.stdout.strip()


def b2_send(method: str, url: str, headers: dict, body: "bytes | None") -> dict:
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=600) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        try:
            detail = json.load(error).get("code", "")
        except (ValueError, AttributeError):
            detail = ""
        raise post.Refused(f"B2 answered {error.code} {detail} to {url.split('?')[0]}")
    except (urllib.error.URLError, OSError, ValueError) as error:  # ValueError: a reply that isn't JSON
        raise post.Refused(f"couldn't reach B2 at {url.split('?')[0]} ({type(error).__name__})")


def stage(piece: post.Piece, config: dict, key: str, send, root: Path, now: datetime) -> dict:
    """Upload the files and return the arguments, with the download token."""
    auth = send("GET", AUTHORIZE, {"Authorization": "Basic " + base64.b64encode(key.encode()).decode()}, None)
    api = auth["apiInfo"]["storageApi"]
    bucket = next((b for b in api["allowed"]["buckets"] if b["name"] == config["b2"]["bucket"]), None)
    if bucket is None:
        raise post.Refused(f"the B2 key isn't for the bucket '{config['b2']['bucket']}'")
    if api["downloadUrl"] != config["b2"]["download_host"]:
        raise post.Refused(f"company.json's b2.download_host is {config['b2']['download_host']}, "
                           f"but this key's download host is {api['downloadUrl']}")
    bearer = {"Authorization": auth["authorizationToken"]}
    upload = send("POST", f"{api['apiUrl']}/b2api/v4/b2_get_upload_url", bearer,
                  json.dumps({"bucketId": bucket["id"]}).encode())
    for _, name, sha in piece.files:
        data = post.file_path(piece, name, root).read_bytes()
        if hashlib.sha256(data).hexdigest() != sha:
            raise post.Refused(f"{name} changed after its hash went on the page")
        if piece.type != post.SHORT and not piece.ai_label:
            try:
                data = strip_ai.strip(data, Path(name).suffix)
            except strip_ai.Unparsed:
                raise post.Refused(f"strip_ai.py can't parse {name}, and the Board's AI label is off") from None
            marks = strip_ai.ai_marks(data)
            if marks:
                raise post.Refused(f"couldn't remove the AI metadata from {name} ({', '.join(marks)}), "
                                   "and the Board's AI label is off")
        send("POST", upload["uploadUrl"], {
            "Authorization": upload["authorizationToken"],
            "X-Bz-File-Name": quote(post.object_name(piece, name, sha)),
            "Content-Type": MIME[Path(name).suffix.lower()],
            "Content-Length": str(len(data)),
            "X-Bz-Content-Sha1": hashlib.sha1(data).hexdigest(),
        }, data)
    valid = min(MAX_VALID, int((piece.publish_at + timedelta(hours=24) - now).total_seconds()))
    token = send("POST", f"{api['apiUrl']}/b2api/v4/b2_get_download_authorization", bearer, json.dumps({
        "bucketId": bucket["id"], "fileNamePrefix": f"posts/{piece.item_id}/", "validDurationInSeconds": valid,
    }).encode())["authorizationToken"]
    if not post.TOKEN.fullmatch(token):
        raise post.Refused("B2's download token has characters the hook won't accept in a URL")
    return {"arguments": post.build_args(piece, config, token), "valid": valid}


def already_scheduled(item_id: str, root: Path) -> bool:
    ledger = root / post.LEDGER
    return ledger.exists() and any(json.loads(line).get("item_id") == item_id
                                   for line in ledger.read_text(encoding="utf-8").splitlines() if line.strip())


def main(argv=None, send=b2_send, key: "str | None" = None, root: Path = ROOT, now: "datetime | None" = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print(__doc__, file=sys.stderr)
        return 2
    now = now or datetime.now(timezone.utc)
    page = Path(os.path.relpath(Path(argv[0]).resolve(), root.resolve())).as_posix()
    try:
        try:
            piece = post.read_piece(page, root)
            config = post.load_config(root)
            found = post.reasons(piece, root, now, config)
        except (OSError, ValueError, KeyError) as error:
            raise post.Refused(f"couldn't read the page, its decision or company.json ({type(error).__name__}: {error})")
        if found:
            raise post.Refused("; ".join(found))
        if already_scheduled(piece.item_id, root):
            raise post.Refused(f"{piece.item_id} is already scheduled ({post.LEDGER.as_posix()})")
        staged = stage(piece, config, key or read_key(), send, root, now)
    except post.Refused as refused:
        print(f"stage_item: refused: {refused}", file=sys.stderr)
        return 1
    except (KeyError, TypeError) as error:
        print(f"stage_item: B2's reply wasn't as documented ({type(error).__name__}: {error})", file=sys.stderr)
        return 1
    log = root / STAGED / f"{piece.item_id}.json"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(json.dumps({
        "item_id": piece.item_id, "kb_page": piece.page, "kb_sha256": post.page_sha256(piece, root),
        "files": [{"label": label, "name": name, "sha256": sha} for label, name, sha in piece.files],
        "arguments_without_token": post.build_args(piece, config, None),
        "link_valid_seconds": staged["valid"], "staged_at": now.isoformat(timespec="seconds"),
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(staged["arguments"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
