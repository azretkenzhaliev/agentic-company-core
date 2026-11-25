"""Speech with word timestamps: how much is said, how fast, and how soon.

A piece's language is its caption's (caption.language_of) unless --speech names one for the run; Whisper large-v3 on MLX
(Apple Silicon) reads it, and detects the language itself where neither says. Silero's segments gate it: under a second of
speech isn't transcribed. Whisper reads the whole audio, and a word outside the segments (a hallucination over music or
silence) isn't counted. Only numbers are kept, never the words. Whisper doesn't know every language: check yours before
you trust a number.
"""

from __future__ import annotations

import gc
import re
import sys

SR = 16000
MIN_SPEECH_SECONDS = 1.0
SEGMENT_SLACK = 0.5
MIN_WORDS_FOR_RATE = 5  # reels/watch.py's rule for a words-per-minute figure
HOOK_SECONDS = 3.0
ROUTE = re.compile(r"auto|[a-z]{2,3}")


def whisper_language(language: str | None, forced: str = "auto") -> str | None:
    """The language's code for Whisper (the run's --speech, or the caption's); None: Whisper detects it."""
    if forced != "auto":
        return forced
    return None if language in (None, "mixed", "unknown") else language


def inside(word: dict, segments: list, slack: float = SEGMENT_SLACK) -> bool:
    middle = (word["start"] + word["end"]) / 2
    return any(start - slack <= middle <= end + slack for start, end in segments)


def numbers(words: list, speech_seconds: float) -> dict:
    if not words:
        return {"status": "ok", "words": 0, "words_per_minute": None, "first_word_seconds": None,
                "words_first_3s": 0, "words_per_voiced_minute": None}
    span = words[-1]["end"] - words[0]["start"]
    rate = round(len(words) / span * 60, 1) if len(words) >= MIN_WORDS_FOR_RATE and span > 0 else None
    voiced = round(len(words) / speech_seconds * 60, 1) if len(words) >= MIN_WORDS_FOR_RATE and speech_seconds else None
    return {"status": "ok", "words": len(words), "words_per_minute": rate,
            "first_word_seconds": round(words[0]["start"], 2),
            "words_first_3s": sum(1 for word in words if word["start"] < HOOK_SECONDS),
            "words_per_voiced_minute": voiced}


def clear_mlx() -> None:
    gc.collect()
    mx = sys.modules.get("mlx.core")
    clear = getattr(mx, "clear_cache", None) or getattr(getattr(mx, "metal", None), "clear_cache", None)
    if clear is not None:
        clear()


class Whisper:
    MODEL = "whisper-large-v3-mlx"

    def __init__(self, folder, transcribe=None):
        if transcribe is None:
            import mlx_whisper

            transcribe = mlx_whisper.transcribe
        self.folder, self.transcribe = folder, transcribe

    def result(self, audio, language: str | None) -> dict:
        """mlx_whisper's result; a local folder, so it never looks the model up online."""
        return self.transcribe(audio, path_or_hf_repo=str(self.folder), language=language, word_timestamps=True,
                               condition_on_previous_text=False, verbose=None)

    def words(self, audio, language: str | None) -> list:
        """[{start, end}] of every word: the timings only."""
        return [{"start": float(word["start"]), "end": float(word["end"])}
                for segment in self.result(audio, language).get("segments", []) for word in segment.get("words", [])]

    def close(self) -> None:
        """Drops mlx_whisper's cached model (its package's `transcribe` is the function, so the module is looked up)."""
        self.transcribe = None
        holder = getattr(sys.modules.get("mlx_whisper.transcribe"), "ModelHolder", None)
        if holder is not None:
            holder.model = holder.model_path = None
        clear_mlx()


def measure(audio, segments: list, language: str | None, forced: str, whisper: Whisper | None) -> dict:
    """The speech numbers of one piece's 16 kHz audio, given Silero's segments."""
    speech_seconds = sum(end - start for start, end in segments)
    if speech_seconds < MIN_SPEECH_SECONDS:
        return {"status": "none", "speech_seconds": round(speech_seconds, 2)}
    if whisper is None:
        return {"status": "not installed: whisper-large-v3-mlx"}
    words = [word for word in whisper.words(audio, whisper_language(language, forced)) if inside(word, segments)]
    return {**numbers(words, speech_seconds), "model": whisper.MODEL}
