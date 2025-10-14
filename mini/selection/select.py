"""Selection of highlight segments based on scoring and diversity rules."""

from __future__ import annotations

import logging
import random
from collections import defaultdict
from typing import Dict, Iterable, List, Tuple

from ..analysis.types import CandidateClip
from ..edl import Config, EDL, Segment

LOGGER = logging.getLogger(__name__)


def select_segments(
    candidates_by_src: Dict[str, List[CandidateClip]],
    config: Config,
) -> Tuple[EDL, Dict[str, float]]:
    """Select highlight segments and return an EDL with selection metadata."""
    max_duration = config.max_duration
    rng = random.Random(config.seed)

    all_candidates: List[CandidateClip] = []
    for clips in candidates_by_src.values():
        all_candidates.extend(clips)

    if not all_candidates:
        return _empty_edl(config), {"total_candidates": 0, "selected_segments": 0, "selected_duration": 0.0}

    ordered = _order_candidates(all_candidates, rng)

    selected: List[Segment] = []
    total_duration = 0.0
    camera_usage = defaultdict(float)
    last_camera_time: Dict[str, float] = {}

    for cand in ordered:
        duration = cand.duration
        if duration < config.clip_min or duration > config.clip_max:
            continue
        camera = cand.camera or "unknown"

        if not _passes_overlap_check(cand, selected):
            continue

        max_camera_share = config.diversity.max_per_cam_ratio * max_duration
        if camera_usage[camera] + duration > max_camera_share + 1e-6:
            continue

        last_time = last_camera_time.get(camera)
        if last_time is not None and abs(cand.start - last_time) < config.diversity.min_gap_same_cam:
            continue

        if total_duration + duration > max_duration:
            remaining = max_duration - total_duration
            if remaining < config.clip_min:
                break
            duration = min(duration, remaining, config.clip_max)
            cand_end = cand.start + duration
        else:
            cand_end = cand.end

        segment = Segment(
            src=cand.src,
            start=float(round(cand.start, 3)),
            end=float(round(cand_end, 3)),
            score=float(cand.score),
            tags=tuple(sorted(cand.tags)),
            camera=camera,
        )

        selected.append(segment)
        total_duration += segment.duration
        camera_usage[camera] += segment.duration
        last_camera_time[camera] = segment.start

        if total_duration >= max_duration - 0.01:
            break

    edl = EDL(
        project=config.project,
        variant=config.variant,
        seed=config.seed,
        max_duration=config.max_duration,
        clip_min=config.clip_min,
        clip_max=config.clip_max,
        segments=selected,
        metadata={
            "target_range": list(config.target_range),
            "deliverables": list(config.deliverables),
        },
    )

    metrics = {
        "total_candidates": len(all_candidates),
        "selected_segments": len(selected),
        "selected_duration": round(total_duration, 3),
    }
    return edl, metrics


def _order_candidates(candidates: Iterable[CandidateClip], rng: random.Random) -> List[CandidateClip]:
    ordered = list(candidates)
    ordered.sort(key=lambda c: (-c.score, c.src, c.start, c.end))
    # apply deterministic shuffle on score ties by sampling a tiny jitter
    jittered = []
    for cand in ordered:
        jitter = rng.random() * 1e-6
        jittered.append((cand.score + jitter, cand))
    jittered.sort(key=lambda item: (-item[0], item[1].src, item[1].start))
    return [item[1] for item in jittered]


def _passes_overlap_check(cand: CandidateClip, selected: Iterable[Segment], tolerance: float = 0.25) -> bool:
    for seg in selected:
        if seg.src != cand.src:
            continue
        overlap = min(seg.end, cand.end) - max(seg.start, cand.start)
        if overlap > tolerance:
            return False
    return True


def _empty_edl(config: Config) -> EDL:
    return EDL(
        project=config.project,
        variant=config.variant,
        seed=config.seed,
        max_duration=config.max_duration,
        clip_min=config.clip_min,
        clip_max=config.clip_max,
        segments=[],
        metadata={
            "target_range": list(config.target_range),
            "deliverables": list(config.deliverables),
        },
    )
