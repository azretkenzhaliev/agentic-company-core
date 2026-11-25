"""Edit structure: where the cuts are, then the cut rate, shot lengths and the first cut.

TransNetV2 (ONNX, converted once from the authors' SavedModel) when it's installed; otherwise ffmpeg's scene score with
reels/watch.py's spike rule (pick_cuts, copied here; a test keeps them the same), in place of PySceneDetect, which
measures the same frame difference. The method used is in the output.
"""

from __future__ import annotations

import re
import statistics

try:
    import numpy as np
except ImportError:  # the ffmpeg fallback and the numbers are plain Python
    np = None

from . import media, stats

SCENE_FLOOR = 0.05
SCENE_SPIKE = 5
SCENE_WINDOW = 15
SCENE_QUIET = 0.0005
CUT_GAP_SECONDS = 0.25
EDGE_SECONDS = 0.1
TRANSNET_SIZE = (48, 27)
TRANSNET_THRESHOLD = 0.5


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


def ffmpeg_cuts(video, length: float) -> list:
    stdout = media.ffmpeg_ok(video, "-map", "0:v:0", "-an", "-t", str(media.MAX_SECONDS), "-vf",
                             "select='gte(scene,0)',metadata=print:file=-", "-f", "null", "-").stdout
    scores = [(float(time_), float(score)) for time_, score
              in re.findall(r"pts_time:([\d.]+)\s+lavfi\.scene_score=([\d.]+)", stdout.decode("utf-8", "replace"))]
    return [round(time_, 2) for time_ in pick_cuts(scores) if EDGE_SECONDS < time_ < length - EDGE_SECONDS]


def frame_rate(fps: float | None) -> int:
    """TransNetV2's frames come at a constant rate, so frame i is at i / rate; the source's own rate when it's sane."""
    return round(fps) if fps and 15 <= fps <= 60 else 25


class TransNet:
    FILE = "transnetv2.onnx"

    def __init__(self, folder, session=None):
        if session is None:
            import onnxruntime

            options = onnxruntime.SessionOptions()
            options.intra_op_num_threads = 2
            options.log_severity_level = 4
            session = onnxruntime.InferenceSession(str(folder / self.FILE), providers=["CPUExecutionProvider"],
                                                   sess_options=options)
        self.session = session
        spec = session.get_inputs()[0]
        self.input, self.dtype = spec.name, np.uint8 if "uint8" in spec.type else np.float32
        names = [output.name for output in session.get_outputs()]
        self.output = next((name for name in names if "many_hot" not in name), names[0])

    def predictions(self, frames: np.ndarray) -> np.ndarray:
        """One cut probability per frame, from (n, 27, 48, 3) RGB: windows of 100 frames, 50 apart, the middle 50 kept,
        padded with copies of the first and last frames (the authors' inference code)."""
        count = len(frames)
        if not count:
            return np.zeros(0)
        end = 25 + 50 - (count % 50 if count % 50 else 50)
        padded = np.concatenate([frames[:1]] * 25 + [frames] + [frames[-1:]] * end, 0)
        out = []
        for start in range(0, len(padded) - 100 + 1, 50):
            batch = padded[start:start + 100][None].astype(self.dtype)
            logits = self.session.run([self.output], {self.input: batch})[0]
            out.append(1 / (1 + np.exp(-np.asarray(logits, dtype=np.float64).reshape(-1)[25:75])))
        return np.concatenate(out)[:count]

    def cuts(self, video, info: dict) -> list:
        rate = frame_rate(info.get("fps"))
        frames = media.video_frames(video, TRANSNET_SIZE, fps=rate, flags=None)
        return cuts_from_predictions(self.predictions(frames), rate, info["seconds"])

    def close(self) -> None:
        self.session = None


def cuts_from_predictions(predictions, fps: float, seconds: float, threshold: float = TRANSNET_THRESHOLD) -> list:
    """A new shot starts at the first frame below the threshold after frames above it (predictions_to_scenes)."""
    above = [p > threshold for p in predictions]
    times = [i / fps for i in range(1, len(above)) if above[i - 1] and not above[i]]
    return [round(time_, 2) for time_ in times if EDGE_SECONDS < time_ < seconds - EDGE_SECONDS]


def cut_stats(cuts: list, seconds: float, method: str) -> dict:
    edges = [0.0, *cuts, seconds]
    shots = [after - before for before, after in zip(edges, edges[1:])]
    return {
        "status": "ok",
        "method": method,
        "cuts": len(cuts),
        "cuts_per_minute": round(len(cuts) / seconds * 60, 2) if seconds else None,
        "first_cut_seconds": cuts[0] if cuts else None,
        "shots": len(shots),
        "shot_median_seconds": round(stats.quantile(shots, 0.5), 2),
        "shot_p10_seconds": round(stats.quantile(shots, 0.1), 2),
        "shot_p90_seconds": round(stats.quantile(shots, 0.9), 2),
        "longest_shot_seconds": round(max(shots), 2),
        "times": cuts,
    }
