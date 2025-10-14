import json
from pathlib import Path

import pytest

from mini.analysis.types import CandidateClip
from mini.edl import Config, EDL, Segment
from mini.render.ffmpeg_cmd import build_commands
from mini.selection.select import select_segments


@pytest.fixture()
def base_config() -> Config:
    cfg = Config()
    cfg.max_duration = 12.0
    cfg.clip_min = 1.0
    cfg.clip_max = 4.0
    cfg.target_range = (2.0, 3.5)
    cfg.diversity.min_gap_same_cam = 1.0
    cfg.diversity.max_per_cam_ratio = 0.5
    cfg.deliverables = ("9:16",)
    cfg.validate()
    return cfg


def test_scoring_weights_sum_to_one(base_config: Config) -> None:
    assert pytest.approx(sum(base_config.weights.values()), 1e-6) == 1.0


def test_candidate_merge_prefers_higher_score_overlap(base_config: Config) -> None:
    high = CandidateClip(src="camA.mp4", start=0.0, end=3.0, score=0.9, tags={"audio_peak"}, camera="camA")
    low = CandidateClip(src="camA.mp4", start=0.1, end=3.1, score=0.4, tags={"audio_peak"}, camera="camA")
    edl, _ = select_segments({high.src: [high, low]}, base_config)
    assert len(edl.segments) == 1
    assert edl.segments[0].score == pytest.approx(0.9)


def test_diversity_constraints_enforced(base_config: Config) -> None:
    base_config.max_duration = 10.0
    base_config.diversity.max_per_cam_ratio = 0.4
    cam_a = CandidateClip(src="camA.mp4", start=0.0, end=4.0, score=0.8, tags={"motion"}, camera="camA")
    cam_a_2 = CandidateClip(src="camA.mp4", start=4.5, end=8.5, score=0.7, tags={"motion"}, camera="camA")
    cam_b = CandidateClip(src="camB.mp4", start=0.0, end=3.0, score=0.6, tags={"faces"}, camera="camB")
    edl, _ = select_segments({"camA.mp4": [cam_a, cam_a_2], "camB.mp4": [cam_b]}, base_config)
    durations = {seg.camera: seg.duration for seg in edl.segments}
    assert durations.get("camA", 0) <= base_config.max_duration * base_config.diversity.max_per_cam_ratio + 1e-6


def test_duration_caps_at_max_duration(base_config: Config) -> None:
    base_config.max_duration = 6.0
    clips = [
        CandidateClip(src="camA.mp4", start=0.0, end=3.0, score=0.8, tags={"motion"}, camera="camA"),
        CandidateClip(src="camB.mp4", start=0.0, end=3.0, score=0.7, tags={"audio_peak"}, camera="camB"),
        CandidateClip(src="camC.mp4", start=0.0, end=3.0, score=0.6, tags={"faces"}, camera="camC"),
    ]
    edl, metrics = select_segments({c.src: [c] for c in clips}, base_config)
    assert edl.total_duration() <= pytest.approx(base_config.max_duration, rel=0.01)
    assert metrics["selected_segments"] <= 3


def test_deterministic_seed_reproducibility(base_config: Config) -> None:
    clips = [
        CandidateClip(src="camA.mp4", start=0.0, end=3.0, score=0.9, tags={"motion"}, camera="camA"),
        CandidateClip(src="camB.mp4", start=0.0, end=3.0, score=0.85, tags={"audio_peak"}, camera="camB"),
    ]
    edl1, _ = select_segments({c.src: [c] for c in clips}, base_config)
    edl2, _ = select_segments({c.src: [c] for c in clips}, base_config)
    assert json.dumps(edl1.to_dict(), sort_keys=True) == json.dumps(edl2.to_dict(), sort_keys=True)


def test_ffmpeg_filter_complex_contains_all_trims(base_config: Config) -> None:
    segments = [
        Segment(src="camA.mp4", start=0.0, end=2.5, score=0.8, tags=("motion",), camera="camA"),
        Segment(src="camB.mp4", start=5.0, end=8.0, score=0.7, tags=("faces",), camera="camB"),
    ]
    edl = EDL(
        project="Event_Recap",
        variant="deterministic",
        seed=42,
        max_duration=60.0,
        clip_min=1.0,
        clip_max=4.0,
        segments=segments,
    )
    commands = build_commands(edl, base_config, Path("output.mp4"))
    command = commands[base_config.deliverables[0]]
    filter_complex = command[command.index("-filter_complex") + 1]
    assert "trim=start=0.000:end=2.500" in filter_complex
    assert "trim=start=5.000:end=8.000" in filter_complex
