"""Combine detection events into candidate highlight clips."""

from __future__ import annotations

import json
import logging
import math
import subprocess
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Sequence

from ..edl import Config
from .types import CandidateClip, DetectionEvent

LOGGER = logging.getLogger(__name__)

ANCHOR_TAGS = ("audio_peak", "motion")


def generate_candidates(
    path: Path,
    events_by_tag: Dict[str, Sequence[DetectionEvent]],
    config: Config,
) -> List[CandidateClip]:
    duration = _probe_duration(path)
    if duration <= 0:
        LOGGER.warning("Could not probe duration for %s, skipping candidates", path)
        return []

    target_min, target_max = config.target_range
    target_len = max(config.clip_min, min(config.clip_max, (target_min + target_max) / 2.0))

    anchor_tags = [tag for tag in ANCHOR_TAGS if tag in events_by_tag and events_by_tag[tag]]
    if not anchor_tags:
        anchor_tags = [tag for tag in events_by_tag.keys()]
    if not anchor_tags:
        return []

    candidates: List[CandidateClip] = []
    weight_lookup = config.weights
    camera_label = _infer_camera_label(path)

    for tag in anchor_tags:
        for event in events_by_tag.get(tag, []):
            start = max(0.0, event.time - target_len / 2.0)
            end = min(duration, start + target_len)
            if end - start < config.clip_min:
                delta = config.clip_min - (end - start)
                start = max(0.0, start - delta / 2.0)
                end = min(duration, end + delta / 2.0)
            if end - start > config.clip_max:
                end = start + config.clip_max

            score = 0.0
            tags = set([tag])
            for other_tag, events in events_by_tag.items():
                w = weight_lookup.get(other_tag, 0.0)
                if w <= 0:
                    continue
                contribution = _window_contribution(event.time, events, end - start)
                score += w * contribution
                if contribution > 0:
                    tags.add(other_tag)

            if score <= 0:
                continue
            candidate = CandidateClip(
                src=str(path),
                start=float(round(start, 3)),
                end=float(round(end, 3)),
                score=float(score),
                tags=tags,
                camera=camera_label,
            )
            candidates.append(candidate)

    merged = _merge_similar_candidates(candidates)
    merged.sort(key=lambda c: c.score, reverse=True)
    return merged


def _window_contribution(center: float, events: Sequence[DetectionEvent], window: float) -> float:
    half = window / 2.0
    total = 0.0
    for ev in events:
        if abs(ev.time - center) <= half:
            total += ev.score
    return total


def _merge_similar_candidates(candidates: Iterable[CandidateClip], tolerance: float = 0.5) -> List[CandidateClip]:
    result: List[CandidateClip] = []
    for cand in sorted(candidates, key=lambda c: c.score, reverse=True):
        if any(_overlaps(cand, existing, tolerance) for existing in result):
            continue
        result.append(cand)
    return result


def _overlaps(a: CandidateClip, b: CandidateClip, tolerance: float) -> bool:
    if a.src != b.src:
        return False
    start_diff = abs(a.start - b.start)
    end_diff = abs(a.end - b.end)
    return start_diff <= tolerance and end_diff <= tolerance


def _probe_duration(path: Path) -> float:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "format=duration",
        "-of",
        "json",
        str(path),
    ]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if proc.returncode != 0:
        LOGGER.warning("ffprobe failed for %s: %s", path, proc.stderr.decode("utf-8", "ignore"))
        return 0.0
    data = json.loads(proc.stdout or b"{}")
    try:
        return float(data["format"]["duration"])
    except (KeyError, TypeError, ValueError):
        return 0.0


def _infer_camera_label(path: Path) -> str:
    stem = Path(path).stem
    for delimiter in ("_", "-", " "):
        if delimiter in stem:
            return stem.split(delimiter)[0]
    return stem
