"""Sound numbers: loudness, voice activity, pauses, tempo and pitch.

- loudness: ffmpeg's ebur128 filter (integrated LUFS, loudness range, true peak), parsed as reels/watch.py does; it
  stands in for pyloudnorm, with the same EBU R128 measure.
- voice activity: Silero VAD (ONNX, ungated, MIT), run and segmented exactly as faster-whisper 1.2.1 does
  (faster_whisper/vad.py); its segments also say where speech recognition should listen.
- tempo: the autocorrelation of a spectral-flux onset envelope, 60-200 BPM with a prior around 120 (librosa's idea).
- pitch: windowed autocorrelation (Boersma's normalisation, Praat's method) on 64 ms frames inside speech.
Audio is mono float32 at 16 kHz.
"""

from __future__ import annotations

import math
import re

try:
    import numpy as np
except ImportError:  # loudness parsing and segmenting are plain Python; the rest needs the measure environment
    np = None

SR = 16000
WINDOW = 512
CONTEXT = 64
VAD_BATCH = 10000
PAUSE_SECONDS = 0.3
HOOK_SECONDS = 3.0
TEMPO_MIN_SECONDS = 5.0
FLUX_FRAME, FLUX_HOP = 1024, 256
PITCH_FRAME, PITCH_HOP = 1024, 512
PITCH_LAGS = (40, 213)  # 400 Hz to 75 Hz at 16 kHz
VOICING = 0.4
MIN_VOICED_FRAMES = 50
LOUD_KEYS = ("integrated_lufs", "range_lu", "true_peak_dbfs")


# ---- loudness: the Summary block, copied from reels/watch.py (parse_loudness); a test keeps them the same ----------

def parse_loudness(stderr: str) -> dict:
    """The Summary block of ffmpeg's ebur128 filter. A silent track prints I: -70.0 and Peak: -inf, which JSON can't hold: None."""
    summary = stderr[stderr.rfind("Summary:"):]
    found = {}
    for key, pattern in zip(LOUD_KEYS, (r"\bI:\s+(-?[\d.]+|-?inf|nan) LUFS", r"\bLRA:\s+(-?[\d.]+|-?inf|nan) LU\b",
                                        r"\bPeak:\s+(-?[\d.]+|-?inf|nan) dBFS")):
        match = re.search(pattern, summary)
        value = float(match.group(1)) if match else math.nan
        found[key] = value if math.isfinite(value) else None
    return found


def loudness(video) -> dict:
    from . import media

    stderr = media.ffmpeg_ok(video, "-vn", "-map", "0:a:0", "-t", str(media.MAX_SECONDS), "-af", "ebur128=peak=true",
                             "-f", "null", "-").stderr.decode("utf-8", "replace")
    return parse_loudness(stderr)


# ---- voice activity: Silero ----------------------------------------------------------------------------------------

class Silero:
    FILE = "silero_vad_v6.onnx"

    def __init__(self, folder, session=None):
        if session is None:
            import onnxruntime

            options = onnxruntime.SessionOptions()
            options.inter_op_num_threads = 1
            options.intra_op_num_threads = 1
            options.enable_cpu_mem_arena = False
            options.log_severity_level = 4
            session = onnxruntime.InferenceSession(str(folder / self.FILE), providers=["CPUExecutionProvider"],
                                                   sess_options=options)
        self.session = session

    def probabilities(self, audio: np.ndarray) -> np.ndarray:
        """One speech probability per 512 samples, padded as faster-whisper pads."""
        padded = np.pad(audio.astype(np.float32), (0, WINDOW - audio.shape[0] % WINDOW))
        batched = padded.reshape(-1, WINDOW)
        context = batched[..., -CONTEXT:]
        context[-1] = 0
        context = np.roll(context, 1, 0)
        batched = np.concatenate([context, batched], 1).reshape(-1, WINDOW + CONTEXT)
        h = np.zeros((1, 1, 128), dtype=np.float32)
        c = np.zeros((1, 1, 128), dtype=np.float32)
        outputs = []
        for i in range(0, batched.shape[0], VAD_BATCH):
            output, h, c = self.session.run(None, {"input": batched[i:i + VAD_BATCH], "h": h, "c": c})
            outputs.append(output)
        return np.concatenate(outputs, axis=0).reshape(-1)

    def segments(self, audio: np.ndarray) -> list:
        return speech_segments(self.probabilities(audio), len(audio))

    def close(self) -> None:
        self.session = None


def speech_segments(probs, n_samples: int, sr: int = SR, threshold: float = 0.5, min_speech_ms: int = 250,
                    min_silence_ms: int = 100, pad_ms: int = 30, max_speech_s: float = math.inf) -> list:
    """faster-whisper 1.2.1's get_speech_timestamps, line for line, over the probabilities; [(start, end)] seconds."""
    min_speech_samples = sr * min_speech_ms / 1000
    speech_pad_samples = sr * pad_ms / 1000
    max_speech_samples = sr * max_speech_s - WINDOW - 2 * speech_pad_samples
    min_silence_samples = sr * min_silence_ms / 1000
    min_silence_samples_at_max_speech = sr * 98 / 1000
    neg_threshold = max(threshold - 0.15, 0.01)
    triggered = False
    speeches = []
    current_speech: dict = {}
    temp_end = 0
    prev_end = next_start = 0
    for i, speech_prob in enumerate(probs):
        if speech_prob >= threshold and temp_end:
            temp_end = 0
            if next_start < prev_end:
                next_start = WINDOW * i
        if speech_prob >= threshold and not triggered:
            triggered = True
            current_speech["start"] = WINDOW * i
            continue
        if triggered and WINDOW * i - current_speech["start"] > max_speech_samples:
            if prev_end:
                current_speech["end"] = prev_end
                speeches.append(current_speech)
                current_speech = {}
                if next_start < prev_end:
                    triggered = False
                else:
                    current_speech["start"] = next_start
                prev_end = next_start = temp_end = 0
            else:
                current_speech["end"] = WINDOW * i
                speeches.append(current_speech)
                current_speech = {}
                prev_end = next_start = temp_end = 0
                triggered = False
                continue
        if speech_prob < neg_threshold and triggered:
            if not temp_end:
                temp_end = WINDOW * i
            if WINDOW * i - temp_end > min_silence_samples_at_max_speech:
                prev_end = temp_end
            if WINDOW * i - temp_end < min_silence_samples:
                continue
            current_speech["end"] = temp_end
            if current_speech["end"] - current_speech["start"] > min_speech_samples:
                speeches.append(current_speech)
            current_speech = {}
            prev_end = next_start = temp_end = 0
            triggered = False
            continue
    if current_speech and (n_samples - current_speech["start"]) > min_speech_samples:
        current_speech["end"] = n_samples
        speeches.append(current_speech)
    for i, speech in enumerate(speeches):
        if i == 0:
            speech["start"] = int(max(0, speech["start"] - speech_pad_samples))
        if i != len(speeches) - 1:
            silence_duration = speeches[i + 1]["start"] - speech["end"]
            if silence_duration < 2 * speech_pad_samples:
                speech["end"] += int(silence_duration // 2)
                speeches[i + 1]["start"] = int(max(0, speeches[i + 1]["start"] - silence_duration // 2))
            else:
                speech["end"] = int(min(n_samples, speech["end"] + speech_pad_samples))
                speeches[i + 1]["start"] = int(max(0, speeches[i + 1]["start"] - speech_pad_samples))
        else:
            speech["end"] = int(min(n_samples, speech["end"] + speech_pad_samples))
    return [(speech["start"] / sr, speech["end"] / sr) for speech in speeches]


def speech_features(segments: list, seconds: float) -> dict:
    spoken = sum(end - start for start, end in segments)
    gaps = [after[0] - before[1] for before, after in zip(segments, segments[1:])]
    pauses = [gap for gap in gaps if gap >= PAUSE_SECONDS]
    return {
        "speech_seconds": round(spoken, 2),
        "speech_share": round(spoken / seconds, 4) if seconds else None,
        "segments": len(segments),
        "pauses": len(pauses),
        "pauses_per_minute": round(len(pauses) / seconds * 60, 2) if seconds else None,
        "longest_pause_seconds": round(max(pauses), 2) if pauses else 0.0,
        "first_speech_seconds": round(segments[0][0], 2) if segments else None,
        "speech_in_first_3s": round(sum(max(0.0, min(end, HOOK_SECONDS) - start) for start, end in segments
                                        if start < HOOK_SECONDS), 2),
    }


# ---- tempo ---------------------------------------------------------------------------------------------------------

def onset_envelope(audio: np.ndarray) -> np.ndarray:
    """Positive spectral flux of log magnitudes, 1024-sample frames every 256 (62.5 a second), in blocks."""
    window = np.hanning(FLUX_FRAME)
    count = 1 + (len(audio) - FLUX_FRAME) // FLUX_HOP
    flux, previous = [], None
    for first in range(0, count, 2048):
        index = (np.arange(first, min(count, first + 2048))[:, None] * FLUX_HOP + np.arange(FLUX_FRAME)[None])
        magnitude = np.log1p(np.abs(np.fft.rfft(audio[index] * window, axis=1)) * 10)
        stacked = magnitude if previous is None else np.vstack([previous[None], magnitude])
        flux.append(np.maximum(0, np.diff(stacked, axis=0)).sum(axis=1))
        previous = magnitude[-1]
    return np.concatenate(flux) if flux else np.zeros(0)


def parabola(values: np.ndarray, index: int) -> float:
    if 0 < index < len(values) - 1:
        a, b, c = values[index - 1], values[index], values[index + 1]
        denominator = a - 2 * b + c
        if denominator:
            return index + 0.5 * (a - c) / denominator
    return float(index)


def tempo(audio: np.ndarray, sr: int = SR) -> dict:
    if len(audio) < TEMPO_MIN_SECONDS * sr:
        return {"bpm": None, "strength": None}
    envelope = onset_envelope(audio)
    rate = sr / FLUX_HOP
    smooth = int(rate)
    envelope = envelope - np.convolve(envelope, np.ones(smooth) / smooth, mode="same")
    envelope = np.maximum(envelope, 0)
    size = 1 << int(np.ceil(np.log2(2 * len(envelope))))
    spectrum = np.fft.rfft(envelope, size)
    correlation = np.fft.irfft(spectrum * np.conj(spectrum), size)[:len(envelope)]
    if correlation[0] <= 0:
        return {"bpm": None, "strength": None}
    low, high = int(np.floor(60 * rate / 200)), int(np.ceil(60 * rate / 60))
    lags = np.arange(low, high + 1)
    prior = np.exp(-0.5 * np.log2(60 * rate / lags / 120) ** 2)
    best = int(lags[np.argmax(correlation[lags] * prior)])
    lag = parabola(correlation, best)
    return {"bpm": round(60 * rate / lag, 1), "strength": round(float(correlation[best] / correlation[0]), 4)}


# ---- pitch ---------------------------------------------------------------------------------------------------------

def frame_starts(n_samples: int, segments: list, sr: int = SR) -> np.ndarray:
    starts = np.arange(0, max(0, n_samples - PITCH_FRAME) + 1, PITCH_HOP)
    if not segments:
        return starts
    centres = (starts + PITCH_FRAME / 2) / sr
    inside = np.zeros(len(starts), dtype=bool)
    for start, end in segments:
        inside |= (centres >= start) & (centres < end)
    return starts[inside]


def pitch(audio: np.ndarray, segments: list, sr: int = SR) -> dict:
    """Median, P10 and P90 of the voiced frames' f0 in Hz, and the P10-P90 range in semitones."""
    starts = frame_starts(len(audio), segments, sr)
    window = np.hanning(PITCH_FRAME)
    size = 2 * PITCH_FRAME
    window_spectrum = np.fft.rfft(window, size)
    window_ac = np.fft.irfft(np.abs(window_spectrum) ** 2, size)[:PITCH_FRAME]
    window_ac = window_ac / window_ac[0]
    low, high = PITCH_LAGS
    f0 = []
    for first in range(0, len(starts), 1000):
        index = starts[first:first + 1000, None] + np.arange(PITCH_FRAME)[None]
        frames = audio[index].astype(np.float64)
        frames = (frames - frames.mean(axis=1, keepdims=True)) * window
        ac = np.fft.irfft(np.abs(np.fft.rfft(frames, size, axis=1)) ** 2, size, axis=1)[:, :PITCH_FRAME]
        for row in ac:
            if row[0] <= 1e-6:
                continue
            normal = row[:high + 2] / row[0] / window_ac[:high + 2]
            peaks = [lag for lag in range(low, high + 1) if normal[lag] >= normal[lag - 1] and normal[lag] > normal[lag + 1]]
            if not peaks:
                continue
            top = max(normal[lag] for lag in peaks)
            if top < VOICING:
                continue
            lag = parabola(normal, next(lag for lag in peaks if normal[lag] >= 0.9 * top))
            f0.append(sr / lag)
    if len(f0) < MIN_VOICED_FRAMES:
        return {"voiced_frames": len(f0), "median_hz": None, "p10_hz": None, "p90_hz": None, "range_semitones": None}
    p10, median, p90 = np.percentile(f0, [10, 50, 90])
    return {"voiced_frames": len(f0), "median_hz": round(float(median), 1), "p10_hz": round(float(p10), 1),
            "p90_hz": round(float(p90), 1), "range_semitones": round(float(12 * np.log2(p90 / p10)), 2)}
