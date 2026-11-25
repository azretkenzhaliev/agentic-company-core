"""Deterministic picture numbers, per frame and then the median over a piece's frames.

- lightness: CIE L* (0-100) mean, with P10 and P90 within the frame; contrast: the standard deviation of luma / 255;
- saturation: HSV saturation (0-1) mean; colourfulness: Hasler and Süsstrunk 2003 (a pure red frame is 85.5);
- warmth: mean (R - B) / 255; sharpness: the variance of the Laplacian of luma at 540 px wide;
- palette: up to 5 colours, k-means in CIE Lab (seeded), each a hex colour and its share;
- motion (reels): the mean absolute luma change between frames a second apart, / 255.
numpy only, not OpenCV: the same formulas without a 100 MB dependency.
"""

from __future__ import annotations

import numpy as np

WIDTH = 540
FPS = 1
MAX_FRAMES = 90
PALETTE_K = 5
PALETTE_SAMPLES = 4000
PALETTE_ITERATIONS = 20
WHITE = np.array([0.95047, 1.0, 1.08883])
RGB_TO_XYZ = np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]])


def linear(rgb: np.ndarray) -> np.ndarray:
    c = rgb.astype(np.float64) / 255
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def lab_f(t: np.ndarray) -> np.ndarray:
    delta = 6 / 29
    return np.where(t > delta ** 3, np.cbrt(t), t / (3 * delta ** 2) + 4 / 29)


def lab(rgb: np.ndarray) -> np.ndarray:
    """(..., 3) sRGB uint8 to CIE Lab, D65."""
    xyz = linear(rgb) @ RGB_TO_XYZ.T / WHITE
    fx, fy, fz = (lab_f(xyz[..., i]) for i in range(3))
    return np.stack([116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)], axis=-1)


def luma(rgb: np.ndarray) -> np.ndarray:
    return rgb[..., :3].astype(np.float64) @ np.array([0.299, 0.587, 0.114])


def colourfulness(rgb: np.ndarray) -> float:
    r, g, b = (rgb[..., i].astype(np.float64) for i in range(3))
    rg, yb = r - g, 0.5 * (r + g) - b
    return float(np.hypot(rg.std(), yb.std()) + 0.3 * np.hypot(rg.mean(), yb.mean()))


def saturation(rgb: np.ndarray) -> float:
    channels = rgb.astype(np.float64)
    high, low = channels.max(axis=-1), channels.min(axis=-1)
    return float(np.where(high > 0, (high - low) / np.maximum(high, 1e-9), 0).mean())


def sharpness(gray: np.ndarray) -> float:
    if gray.shape[0] < 3 or gray.shape[1] < 3:
        return 0.0
    laplacian = gray[1:-1, :-2] + gray[1:-1, 2:] + gray[:-2, 1:-1] + gray[2:, 1:-1] - 4 * gray[1:-1, 1:-1]
    return float(laplacian.var())


def palette(rgb: np.ndarray, k: int = PALETTE_K) -> list:
    """k-means++ in Lab on a seeded sample of pixels; each colour is its members' mean sRGB."""
    pixels = rgb.reshape(-1, 3)
    rng = np.random.default_rng(0)
    if len(pixels) > PALETTE_SAMPLES:
        pixels = pixels[rng.choice(len(pixels), PALETTE_SAMPLES, replace=False)]
    points = lab(pixels)
    k = min(k, len(np.unique(pixels, axis=0)))
    centres = [points[rng.integers(len(points))]]
    for _ in range(1, k):
        distance = np.min([((points - centre) ** 2).sum(axis=1) for centre in centres], axis=0)
        centres.append(points[rng.choice(len(points), p=distance / distance.sum())])
    centres = np.array(centres)
    for _ in range(PALETTE_ITERATIONS):
        labels = ((points[:, None, :] - centres[None]) ** 2).sum(axis=2).argmin(axis=1)
        moved = np.array([points[labels == i].mean(axis=0) if (labels == i).any() else centres[i] for i in range(k)])
        if np.allclose(moved, centres):
            break
        centres = moved
    labels = ((points[:, None, :] - centres[None]) ** 2).sum(axis=2).argmin(axis=1)
    out = []
    for i in range(k):
        members = pixels[labels == i]
        if len(members):
            colour = members.astype(np.float64).mean(axis=0).round().astype(int)
            out.append({"hex": "#{:02x}{:02x}{:02x}".format(*colour), "share": round(len(members) / len(pixels), 4)})
    return sorted(out, key=lambda colour: -colour["share"])


def frame_numbers(rgb: np.ndarray) -> dict:
    lightness = lab(rgb)[..., 0]
    gray = luma(rgb)
    channels = rgb.astype(np.float64)
    return {
        "lightness": float(lightness.mean()),
        "lightness_p10": float(np.percentile(lightness, 10)),
        "lightness_p90": float(np.percentile(lightness, 90)),
        "contrast": float(gray.std() / 255),
        "saturation": saturation(rgb),
        "colourfulness": colourfulness(rgb),
        "warmth": float((channels[..., 0] - channels[..., 2]).mean() / 255),
        "sharpness": sharpness(gray),
    }


def features(frames: list, motion: bool = False) -> dict:
    """The median of each number over the frames (a reel's, or a carousel's slides), the palette of all of them, and,
    for a reel's frames, the motion between neighbours."""
    if not len(frames):
        return {"status": "none"}
    rows = [frame_numbers(frame) for frame in frames]
    out = {"status": "ok", "frames": len(frames)}
    for key in rows[0]:
        out[key] = round(float(np.median([row[key] for row in rows])), 4)
    out["palette"] = palette(np.concatenate([frame.reshape(-1, 3) for frame in frames]))
    if motion and len(frames) > 1:
        grays = [luma(frame) for frame in frames]
        out["motion"] = round(float(np.mean([np.abs(b - a).mean() / 255 for a, b in zip(grays, grays[1:])])), 4)
    return out
