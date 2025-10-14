"""Scene novelty and brightness flash detection."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Tuple

from .types import DetectionEvent

LOGGER = logging.getLogger(__name__)

try:  # pragma: no cover - optional dependency
    import cv2
    import numpy as np
except ImportError as exc:  # pragma: no cover
    cv2 = None  # type: ignore
    np = None  # type: ignore
    LOGGER.warning("OpenCV/NumPy unavailable, scene analysis disabled (%s)", exc)


def analyze_scene_novelty(
    path: Path,
    stride: int = 3,
    novelty_threshold: float = 0.3,
    flash_threshold: float = 0.25,
    max_events: int = 200,
) -> Tuple[List[DetectionEvent], List[DetectionEvent]]:
    if cv2 is None or np is None:
        return [], []

    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        LOGGER.warning("Unable to open video for scene analysis: %s", path)
        return [], []

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    prev_hist = None
    prev_luma = None
    frame_index = 0
    novelty_events: List[DetectionEvent] = []
    flash_events: List[DetectionEvent] = []

    while True:
        ret, frame = cap.read()
        if not ret:
            break
        if frame_index % stride != 0:
            frame_index += 1
            continue
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        hist = cv2.calcHist([hsv], [0, 1], None, [32, 32], [0, 180, 0, 256])
        hist = cv2.normalize(hist, hist).flatten()
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        luma = float(gray.mean()) / 255.0

        if prev_hist is not None:
            diff = cv2.compareHist(prev_hist, hist, cv2.HISTCMP_BHATTACHARYYA)
            score = 1.0 - diff  # convert to similarity score
            if score >= novelty_threshold:
                novelty_events.append(DetectionEvent(time=frame_index / fps, score=score, tag="scene_novelty"))
        prev_hist = hist

        if prev_luma is not None:
            flash_score = abs(luma - prev_luma)
            if flash_score >= flash_threshold:
                flash_events.append(DetectionEvent(time=frame_index / fps, score=flash_score, tag="brightness_flash"))
        prev_luma = luma

        frame_index += 1

    cap.release()
    novelty_events.sort(key=lambda ev: ev.score, reverse=True)
    flash_events.sort(key=lambda ev: ev.score, reverse=True)
    return novelty_events[:max_events], flash_events[:max_events]
