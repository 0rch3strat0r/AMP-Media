"""Motion intensity detection."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import List

from .types import DetectionEvent

LOGGER = logging.getLogger(__name__)

try:  # pragma: no cover - optional dependency validation
    import cv2
    import numpy as np
except ImportError as exc:  # pragma: no cover
    cv2 = None  # type: ignore
    np = None  # type: ignore
    LOGGER.warning("OpenCV or NumPy not available: motion analysis disabled (%s)", exc)


def analyze_motion(
    path: Path,
    downscale_width: int = 320,
    stride: int = 2,
    max_events: int = 200,
    threshold_factor: float = 1.0,
) -> List[DetectionEvent]:
    """Return motion events detected via frame differencing."""
    if cv2 is None or np is None:
        return []

    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        LOGGER.warning("Unable to open video for motion analysis: %s", path)
        return []

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    width = cap.get(cv2.CAP_PROP_FRAME_WIDTH) or downscale_width
    height = cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or (downscale_width * 9 / 16)
    scale = downscale_width / width
    target_size = (downscale_width, max(1, int(height * scale)))

    prev_gray = None
    responses = []
    frame_index = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break
        if frame_index % stride != 0:
            frame_index += 1
            continue
        resized = cv2.resize(frame, target_size)
        gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
        if prev_gray is not None:
            diff = cv2.absdiff(gray, prev_gray)
            score = float(diff.mean()) / 255.0
            timecode = frame_index / fps
            responses.append((timecode, score))
        prev_gray = gray
        frame_index += 1

    cap.release()

    if not responses:
        return []

    times, values = zip(*responses)
    values_arr = np.array(values)
    mean = float(values_arr.mean())
    std = float(values_arr.std())
    threshold = mean + threshold_factor * std
    events = [DetectionEvent(time=t, score=v, tag="motion") for t, v in responses if v >= threshold]
    events.sort(key=lambda ev: ev.score, reverse=True)
    return events[:max_events]
