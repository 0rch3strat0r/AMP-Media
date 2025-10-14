"""Face detection scoring."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import List

from .types import DetectionEvent

LOGGER = logging.getLogger(__name__)

try:  # pragma: no cover - optional dependency
    import cv2
    import numpy as np
except ImportError as exc:  # pragma: no cover
    cv2 = None  # type: ignore
    np = None  # type: ignore
    LOGGER.warning("OpenCV/NumPy unavailable, face detection disabled (%s)", exc)


def analyze_faces(
    path: Path,
    stride: int = 4,
    max_events: int = 150,
) -> List[DetectionEvent]:
    if cv2 is None or np is None:
        return []

    cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    face_cascade = cv2.CascadeClassifier(cascade_path)
    if face_cascade.empty():
        LOGGER.warning("Failed to load Haar cascade: %s", cascade_path)
        return []

    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        LOGGER.warning("Unable to open video for face analysis: %s", path)
        return []

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    frame_index = 0
    events: List[DetectionEvent] = []

    while True:
        ret, frame = cap.read()
        if not ret:
            break
        if frame_index % stride != 0:
            frame_index += 1
            continue
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=4)
        if len(faces) > 0:
            coverage = _face_coverage(faces, frame.shape)
            timestamp = frame_index / fps
            events.append(DetectionEvent(time=float(timestamp), score=coverage, tag="faces"))
        frame_index += 1

    cap.release()
    events.sort(key=lambda ev: ev.score, reverse=True)
    return events[:max_events]


def _face_coverage(faces, shape) -> float:
    h, w = shape[:2]
    frame_area = float(h * w)
    if frame_area <= 0:
        return 0.0
    coverage = sum((fw * fh) for (_, _, fw, fh) in faces) / frame_area
    return float(min(1.0, coverage))
