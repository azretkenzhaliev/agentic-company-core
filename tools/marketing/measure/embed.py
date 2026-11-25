"""Embeddings and weak quality scores.

- embedding: CLIP ViT-L/14's image embedding (ONNX), per frame (a reel's up to 16, evenly spaced; a carousel's slides),
  each made unit length; the piece's vector is their normalized mean, and stats.centroids averages those per page and
  format. SigLIP would do as well; CLIP L/14 is picked because the aesthetic head reads its embeddings.
- aesthetic: LAION's improved aesthetic predictor (a linear head on the same unit embeddings, about 1-10), per frame,
  then the median. A weak feature only: it says how much a frame looks like what LAION's raters liked, not our taste.
- DOVER: dropped for now: a weak feature, and its code and weights licences are unchecked.
"""

from __future__ import annotations

try:
    import numpy as np
except ImportError:
    np = None

from . import media

MAX_FRAMES = 16
SHORT_SIDE = 256
CLIP_SIZE = 224
CLIP_MEAN = (0.48145466, 0.4578275, 0.40821073)
CLIP_STD = (0.26862954, 0.26130258, 0.27577711)
BATCH = 4
AESTHETIC_LAYERS = (0, 2, 4, 6, 7)  # Linear 768-1024-128-64-16-1; the dropouts between them hold no weights


def short_side_size(width: int, height: int, short: int = SHORT_SIDE) -> tuple:
    """Even sides with the shorter one `short` (never upscaled past the source)."""
    scale = min(1.0, short / min(width, height))
    return max(2, round(width * scale / 2) * 2), max(2, round(height * scale / 2) * 2)


def frames_of(item: dict, info: dict) -> list:
    """RGB frames: a reel's up to MAX_FRAMES, evenly spaced; else the slides."""
    if item["video"]:
        rate = min(1.0, MAX_FRAMES / max(info["seconds"], 1))
        size = short_side_size(info["width"], info["height"])
        return list(media.video_frames(item["video"], size, fps=round(rate, 5), max_frames=MAX_FRAMES))
    return [media.image_rgb(path, None)[0] for path in item["images"][:MAX_FRAMES]]


def clip_input(rgb) -> np.ndarray:
    """(3, 224, 224) float32: the short side resized to 224 (bicubic), centre-cropped, CLIP's mean and std."""
    from PIL import Image

    image = Image.fromarray(rgb)
    width, height = image.size
    scale = CLIP_SIZE / min(width, height)
    image = image.resize((max(CLIP_SIZE, round(width * scale)), max(CLIP_SIZE, round(height * scale))),
                         Image.Resampling.BICUBIC)
    left, top = (image.width - CLIP_SIZE) // 2, (image.height - CLIP_SIZE) // 2
    pixels = np.asarray(image.crop((left, top, left + CLIP_SIZE, top + CLIP_SIZE)), dtype=np.float32) / 255
    pixels = (pixels - np.array(CLIP_MEAN, dtype=np.float32)) / np.array(CLIP_STD, dtype=np.float32)
    return pixels.transpose(2, 0, 1)


def units(vectors: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    return vectors / np.where(norms > 0, norms, 1)


class Clip:
    MODEL = "clip-vit-l14"
    FILE = "vision_model.onnx"

    def __init__(self, folder, session=None):
        if session is None:
            import onnxruntime

            options = onnxruntime.SessionOptions()
            options.intra_op_num_threads = 2
            options.log_severity_level = 4
            session = onnxruntime.InferenceSession(str(folder / self.FILE), providers=["CPUExecutionProvider"],
                                                   sess_options=options)
        self.session = session
        self.input = session.get_inputs()[0].name
        names = [output.name for output in session.get_outputs()]
        self.output = "image_embeds" if "image_embeds" in names else names[0]

    def frame_units(self, frames: list) -> np.ndarray:
        """(n, d) unit embeddings, BATCH frames at a time."""
        out = []
        for start in range(0, len(frames), BATCH):
            batch = np.stack([clip_input(frame) for frame in frames[start:start + BATCH]])
            embeds = np.asarray(self.session.run([self.output], {self.input: batch})[0], dtype=np.float64)
            out.append(embeds.reshape(len(batch), -1))
        return units(np.concatenate(out))

    def close(self) -> None:
        self.session = None


def piece_embedding(frame_units: np.ndarray, model: str) -> dict:
    if not len(frame_units):
        return {"status": "none"}
    mean = frame_units.mean(axis=0)
    norm = float(np.linalg.norm(mean))
    if norm <= 0:
        return {"status": "none"}
    return {"status": "ok", "model": model, "frames": len(frame_units),
            "vector": [round(float(x), 6) for x in mean / norm]}


class Aesthetic:
    MODEL = "laion-aesthetic"
    FILE = "sac+logos+ava1-l14-linearMSE.pth"

    def __init__(self, folder, layers=None):
        """layers: [(weight (out, in), bias (out,))] in order; read from the checkpoint as plain tensors, no code."""
        if layers is None:
            import torch

            state = torch.load(str(folder / self.FILE), map_location="cpu", weights_only=True)
            layers = [(state[f"layers.{i}.weight"].float().numpy(), state[f"layers.{i}.bias"].float().numpy())
                      for i in AESTHETIC_LAYERS]
        self.layers = [(np.asarray(w, dtype=np.float64), np.asarray(b, dtype=np.float64)) for w, b in layers]

    def scores(self, frame_units: np.ndarray) -> np.ndarray:
        x = np.asarray(frame_units, dtype=np.float64)
        for weight, bias in self.layers:
            x = x @ weight.T + bias
        return x.reshape(-1)

    def measure(self, frame_units: np.ndarray) -> dict:
        if not len(frame_units):
            return {"status": "none"}
        scores = self.scores(frame_units)
        return {"status": "ok", "model": self.MODEL, "weak": True, "median": round(float(np.median(scores)), 3),
                "p10": round(float(np.percentile(scores, 10)), 3), "p90": round(float(np.percentile(scores, 90)), 3)}

    def close(self) -> None:
        self.layers = None


DOVER = {"status": "dropped for now: a weak feature, and its licences are unchecked"}
