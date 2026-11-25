#!/usr/bin/env python3
"""Text-free images from Gemini (Nano Banana 2) for posts, carousels and stories (SA-005).

    python3 tools/marketing/gen/image.py --brand founder/demo --week 2026-W05 --piece <slug> \
        --prompt "<what to show>" [--aspect 4:5|9:16|1:1]

Writes workspaces/marketing/media/<brand>/<week>/<piece>/image-NN.<ext> and its sidecar
.json. One image per call; the call is checked against the monthly `gemini_images` cap
first and logged after (tools/marketing/spend.py). Refusals, key and API: gen/gemini.py.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from gemini import ROOT, batch_args, generate, interactions_send, read_token  # noqa: E402

# Nano Banana 2 (https://ai.google.dev/gemini-api/docs/image-generation); its images carry SynthID and C2PA.
MODEL = "gemini-3.1-flash-image"
IMAGE_SIZE = "2K"  # 1K is 928, 768 or 1024 px wide at 4:5, 9:16 or 1:1 (the image page's table): under Instagram's 1080
TOOL = "gemini_images"


def main(argv=None, send=interactions_send, token=read_token, root: Path = ROOT) -> int:
    parser = argparse.ArgumentParser(description="A text-free image from Gemini (SA-005).")
    batch_args(parser)
    parser.add_argument("--aspect", choices=["4:5", "9:16", "1:1"], default="4:5",
                        help="4:5 posts and carousels (default), 9:16 stories, 1:1 square")
    args = parser.parse_args(argv)
    response_format = {"type": "image", "aspect_ratio": args.aspect, "image_size": IMAGE_SIZE}
    return generate(args, "image", MODEL, TOOL, 1, response_format, send, token, root)


if __name__ == "__main__":
    sys.exit(main())
