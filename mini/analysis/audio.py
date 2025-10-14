"""Audio analysis helpers."""

from __future__ import annotations

import logging
import math
import subprocess
from pathlib import Path
from typing import List

import numpy as np

from .types import DetectionEvent

LOGGER = logging.getLogger(__name__)


def analyze_audio_peaks(
    path: Path,
    sample_rate: int = 48_000,
    window: int = 1024,
    hop: int = 512,
    threshold_factor: float = 1.25,
    max_events: int = 200,
) -> List[DetectionEvent]:
    """Return significant audio peaks for the supplied media path."""
    path = Path(path)
    audio = _read_mono_pcm(path, sample_rate)
    if audio.size == 0:
        return []

    rms = _frame_rms(audio, window, hop)
    times = np.arange(len(rms)) * (hop / sample_rate)
    mean = float(np.mean(rms))
    std = float(np.std(rms))
    threshold = mean + threshold_factor * std
    LOGGER.debug("Audio RMS mean=%.4f std=%.4f threshold=%.4f", mean, std, threshold)

    peaks = _local_peaks(rms, threshold)
    events = [DetectionEvent(time=float(times[idx]), score=float(rms[idx]), tag="audio_peak") for idx in peaks]
    events.sort(key=lambda ev: ev.score, reverse=True)
    return events[:max_events]


def _read_mono_pcm(path: Path, sample_rate: int) -> np.ndarray:
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        str(sample_rate),
        "-f",
        "f32le",
        "pipe:1",
    ]
    LOGGER.debug("Running ffmpeg for audio decode: %s", " ".join(cmd))
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if proc.returncode != 0:
        LOGGER.warning("ffmpeg failed to decode audio for %s: %s", path, proc.stderr.decode("utf-8", "ignore"))
        return np.array([], dtype=np.float32)
    audio = np.frombuffer(proc.stdout, dtype=np.float32)
    return audio


def _frame_rms(samples: np.ndarray, window: int, hop: int) -> np.ndarray:
    if samples.size < window:
        return np.sqrt(np.mean(np.square(samples))) * np.ones(1, dtype=np.float32)
    num_frames = 1 + (samples.size - window) // hop
    frames = np.lib.stride_tricks.as_strided(
        samples,
        shape=(num_frames, window),
        strides=(samples.strides[0] * hop, samples.strides[0]),
        writeable=False,
    )
    rms = np.sqrt(np.mean(np.square(frames), axis=1))
    return rms


def _local_peaks(values: np.ndarray, threshold: float) -> List[int]:
    peaks: List[int] = []
    for i in range(1, len(values) - 1):
        if values[i] < threshold:
            continue
        if values[i] >= values[i - 1] and values[i] >= values[i + 1]:
            peaks.append(i)
    if len(peaks) > 1:
        # enforce descending order by score, keep top unique indices
        peaks.sort(key=lambda idx: values[idx], reverse=True)
    return peaks
