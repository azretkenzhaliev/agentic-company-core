"""Per page and format: each number's median, P10 and P90 over the pieces, and each embedding model's centroid.

Standard library only, so the summary of saved feature files runs anywhere.
"""

from __future__ import annotations

import math

SKIP_TOP = {"schema", "piece", "embedding"}


def quantile(values: list, q: float) -> float:
    """Linear interpolation between the closest ranks (numpy's default)."""
    ordered = sorted(values)
    position = (len(ordered) - 1) * q
    low = math.floor(position)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def flatten(features: dict) -> dict:
    """Dotted keys for every finite number. Flags, words, lists and missing values aren't distributions."""
    found = {}

    def walk(prefix: str, value) -> None:
        if isinstance(value, dict):
            for key, inner in value.items():
                walk(f"{prefix}.{key}" if prefix else key, inner)
        elif isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
            found[prefix] = value

    for key, value in features.items():
        if key not in SKIP_TOP:
            walk(key, value)
    return found


def group_key(features: dict) -> tuple:
    piece = features.get("piece", {})
    return piece.get("page") or "", piece.get("format") or ""


def summarize(pieces: list) -> list:
    groups: dict = {}
    for features in pieces:
        groups.setdefault(group_key(features), []).append(flatten(features))
    out = []
    for (page, format_), rows in sorted(groups.items()):
        keys = sorted({key for row in rows for key in row})
        numbers = {}
        for key in keys:
            values = [row[key] for row in rows if key in row]
            numbers[key] = {"n": len(values), "median": round(quantile(values, 0.5), 4),
                            "p10": round(quantile(values, 0.1), 4), "p90": round(quantile(values, 0.9), 4)}
        out.append({"page": page, "format": format_, "pieces": len(rows), "numbers": numbers})
    return out


def normalized(vector: list) -> list | None:
    norm = math.sqrt(sum(x * x for x in vector))
    return [x / norm for x in vector] if norm > 0 else None


def centroids(pieces: list) -> list:
    """The normalized mean of each piece's normalized vector, per page, format and model, with the mean cosine to it."""
    groups: dict = {}
    for features in pieces:
        embedding = features.get("embedding") or {}
        vector = embedding.get("vector")
        if embedding.get("status") != "ok" or not vector:
            continue
        unit = normalized(vector)
        if unit:
            groups.setdefault((*group_key(features), embedding.get("model") or ""), []).append(unit)
    out = []
    for (page, format_, model), vectors in sorted(groups.items()):
        if len({len(vector) for vector in vectors}) != 1:
            continue
        mean = normalized([sum(column) / len(vectors) for column in zip(*vectors)])
        if not mean:
            continue
        cosines = [sum(a * b for a, b in zip(vector, mean)) for vector in vectors]
        out.append({"page": page, "format": format_, "model": model, "pieces": len(vectors),
                    "mean_cosine": round(sum(cosines) / len(cosines), 4), "vector": [round(x, 6) for x in mean]})
    return out
