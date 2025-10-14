"""Public analysis API."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, Iterable, List

from ..edl import Config
from .audio import analyze_audio_peaks
from .combine import generate_candidates
from .faces import analyze_faces
from .motion import analyze_motion
from .scenes import analyze_scene_novelty
from .types import CandidateClip, DetectionEvent

LOGGER = logging.getLogger(__name__)


def analyze_sources(paths: Iterable[Path], config: Config) -> Dict[str, List[CandidateClip]]:
    """Run detection across all sources and return candidate clips per source."""
    result: Dict[str, List[CandidateClip]] = {}
    for path in paths:
        try:
            candidates = analyze_source(Path(path), config)
            if candidates:
                result[str(path)] = candidates
        except Exception as exc:  # pragma: no cover - defensive logging
            LOGGER.exception("Analysis failed for %s: %s", path, exc)
    return result


def analyze_source(path: Path, config: Config) -> List[CandidateClip]:
    LOGGER.info("Analyzing %s", path)
    events: Dict[str, List[DetectionEvent]] = {}

    audio_events = analyze_audio_peaks(path)
    if audio_events:
        events["audio_peak"] = audio_events

    motion_events = analyze_motion(path)
    if motion_events:
        events["motion"] = motion_events

    face_events = analyze_faces(path)
    if face_events:
        events["faces"] = face_events

    novelty_events, flash_events = analyze_scene_novelty(path)
    if novelty_events:
        events["scene_novelty"] = novelty_events
    if flash_events:
        events["brightness_flash"] = flash_events

    if not events:
        LOGGER.warning("No detection events for %s", path)
        return []

    candidates = generate_candidates(path, events, config)
    LOGGER.info("Generated %d candidate clips for %s", len(candidates), path)
    return candidates
