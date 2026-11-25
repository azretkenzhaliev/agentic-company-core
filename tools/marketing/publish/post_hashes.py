#!/usr/bin/env python3
"""Fill the SHA-256 column of a piece page's `## Post` table from its media files (the producer's last step).

    python3 tools/marketing/publish/post_hashes.py <knowledge/marketing/founder/<account>/content/<week>/<slug>.md>

Each row's file is looked up in the piece's media folder, workspaces/marketing/media/<brand>/<week>/<slug>/
(links resolved). Because the hashes are on the page, the Board's
decision in Notion covers the exact bytes: the sync hook records the page's hash at the decision, and
stage_item.py and the hook refuse a file that changed since.
"""

import hashlib
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools/marketing/publish"))

import post  # noqa: E402


def main(argv=None, root: Path = ROOT) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print(__doc__, file=sys.stderr)
        return 2
    page = Path(os.path.relpath(Path(argv[0]).resolve(), root.resolve())).as_posix()
    try:
        piece = post.read_piece(page, root)
        names = [name for _, name, _ in piece.files]
        bad = [n for n in names if not post.FILE_NAME.fullmatch(n)]
        if bad:
            raise post.Refused(f"not a plain .png, .jpg, .jpeg or .mp4 file name: {', '.join(bad)}")
        hashes = {name: hashlib.sha256(post.file_path(piece, name, root).read_bytes()).hexdigest() for name in names}
    except post.Refused as refused:
        print(f"post_hashes: {refused}", file=sys.stderr)
        return 1
    lines = (root / page).read_text(encoding="utf-8").split("\n")
    start = lines.index("## Post")
    for i in range(start + 1, len(lines)):
        if lines[i].startswith("## "):
            break
        cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
        if lines[i].startswith("| ") and len(cells) == 3 and cells[1] in hashes:
            lines[i] = f"| {cells[0]} | {cells[1]} | {hashes[cells[1]]} |"
    (root / page).write_text("\n".join(lines), encoding="utf-8")
    print(f"post_hashes: {len(hashes)} files hashed in {page}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
