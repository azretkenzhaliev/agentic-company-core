#!/usr/bin/env python3
"""Text-free b-roll clips from Gemini Omni Flash for reels (SA-005).

    python3 tools/marketing/gen/video.py --brand founder/demo --week 2026-W05 --piece <slug> \
        --prompt "<what to show>" --seconds 8 [--aspect 9:16|16:9]

Writes workspaces/marketing/media/<brand>/<week>/<piece>/video-NN.mp4 and its sidecar
.json, at 720p (Google's default; larger files need its URI delivery). Units are seconds:
--seconds is checked against the monthly `gemini_video_seconds` cap first, and the larger
of it and the clip's real length (bundled ffmpeg) is logged after (tools/marketing/spend.py).
Refusals, key and API: gen/gemini.py.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from gemini import ROOT, batch_args, generate, interactions_send, read_token  # noqa: E402
import spend  # noqa: E402  (gemini put tools/marketing on the path)

# Gemini Omni Flash (https://ai.google.dev/gemini-api/docs/omni).
MODEL = "gemini-omni-1.1-flash"
MAX_SECONDS = 10  # a clip is about 10 s; longer needs Omni's extension turns
TOOL = "gemini_video_seconds"


def main(argv=None, send=interactions_send, token=read_token, root: Path = ROOT, measure=spend.media_seconds) -> int:
    parser = argparse.ArgumentParser(description="A text-free b-roll clip from Gemini Omni Flash (SA-005).")
    batch_args(parser)
    parser.add_argument("--seconds", type=int, choices=range(1, MAX_SECONDS + 1), metavar=f"1-{MAX_SECONDS}",
                        required=True, help="the clip's length")
    parser.add_argument("--aspect", choices=["9:16", "16:9"], default="9:16", help="9:16 reels (default) or 16:9")
    args = parser.parse_args(argv)
    # `duration` is in the OpenAPI spec's VideoResponseFormat (a google-duration string such as "8s"),
    # not in the Omni guide; the allowed values aren't documented.
    response_format = {"type": "video", "aspect_ratio": args.aspect, "duration": f"{args.seconds}s",
                       "delivery": "inline"}
    return generate(args, "video", MODEL, TOOL, args.seconds, response_format, send, token, root, measure)


if __name__ == "__main__":
    sys.exit(main())
