"""EDL and configuration schemas for AMP Mini highlight pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence
import json

DEFAULT_WEIGHTS = {
    "audio_peak": 0.40,
    "motion": 0.30,
    "faces": 0.20,
    "scene_novelty": 0.08,
    "brightness_flash": 0.02,
}

DEFAULT_CONFIG = {
    "project": "Event_Recap",
    "variant": "deterministic",
    "seed": 42,
    "max_duration": 60.0,
    "clip_min": 1.2,
    "clip_max": 4.0,
    "target_range": [2.0, 3.5],
    "weights": DEFAULT_WEIGHTS,
    "diversity": {"min_gap_same_cam": 3.0, "max_per_cam_ratio": 0.5},
    "branding": {
        "logo_path": "logo.png",
        "logo_corner": "bottom_right",
        "logo_size_px": 64,
        "safe_area": 0.8,
    },
    "deliverables": ["9:16", "1:1", "16:9"],
}

VALID_DELIVERABLES = {"9:16", "1:1", "16:9"}


@dataclass
class DiversitySettings:
    min_gap_same_cam: float = 3.0
    max_per_cam_ratio: float = 0.5


@dataclass
class BrandingSettings:
    logo_path: Optional[str] = None
    logo_corner: str = "bottom_right"
    logo_size_px: int = 64
    safe_area: float = 0.8
    intro_path: Optional[str] = None
    outro_path: Optional[str] = None
    lut_path: Optional[str] = None
    fonts: Sequence[str] = field(default_factory=list)


@dataclass
class Config:
    project: str = "Event_Recap"
    variant: str = "deterministic"
    seed: int = 42
    max_duration: float = 60.0
    clip_min: float = 1.2
    clip_max: float = 4.0
    target_range: Sequence[float] = field(default_factory=lambda: (2.0, 3.5))
    weights: Dict[str, float] = field(default_factory=lambda: dict(DEFAULT_WEIGHTS))
    diversity: DiversitySettings = field(default_factory=DiversitySettings)
    branding: BrandingSettings = field(default_factory=BrandingSettings)
    deliverables: Sequence[str] = field(default_factory=lambda: ("9:16",))

    def validate(self) -> None:
        _validate_weights(self.weights)
        if self.clip_min <= 0 or self.clip_max <= 0:
            raise ValueError("clip_min and clip_max must be positive")
        if self.clip_min > self.clip_max:
            raise ValueError("clip_min cannot exceed clip_max")
        if len(self.target_range) != 2 or self.target_range[0] > self.target_range[1]:
            raise ValueError("target_range must be a [min, max] pair with min<=max")
        if not 0 < self.diversity.max_per_cam_ratio <= 1:
            raise ValueError("max_per_cam_ratio must be within (0,1]")
        if self.branding.safe_area <= 0 or self.branding.safe_area > 1:
            raise ValueError("branding.safe_area must be in (0,1]")
        invalid = [d for d in self.deliverables if d not in VALID_DELIVERABLES]
        if invalid:
            raise ValueError(f"Unsupported deliverable ratios: {invalid}")


@dataclass
class Segment:
    src: str
    start: float
    end: float
    score: float
    tags: Sequence[str]
    camera: Optional[str] = None

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


@dataclass
class EDL:
    project: str
    variant: str
    seed: int
    max_duration: float
    clip_min: float
    clip_max: float
    segments: List[Segment] = field(default_factory=list)
    metadata: Dict[str, object] = field(default_factory=dict)

    def total_duration(self) -> float:
        return sum(seg.duration for seg in self.segments)

    def to_dict(self) -> Dict[str, object]:
        data = {
            "project": self.project,
            "variant": self.variant,
            "seed": self.seed,
            "max_duration": self.max_duration,
            "clip_min": self.clip_min,
            "clip_max": self.clip_max,
            "segments": [
                {
                    "src": seg.src,
                    "in": round(seg.start, 3),
                    "out": round(seg.end, 3),
                    "score": round(seg.score, 4),
                    "tags": list(seg.tags),
                    "cam": seg.camera,
                }
                for seg in self.segments
            ],
        }
        if self.metadata:
            data["metadata"] = self.metadata
        return data

    def to_json(self, path: Path) -> None:
        path = Path(path)
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")


def load_config(path: Optional[Path]) -> Config:
    if path is None:
        cfg = Config()
        cfg.validate()
        return cfg
    data = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    cfg = _config_from_dict(data)
    cfg.validate()
    return cfg


def _config_from_dict(data: Dict[str, object]) -> Config:
    weights = data.get("weights", dict(DEFAULT_WEIGHTS))
    diversity_data = data.get("diversity", {})
    branding_data = data.get("branding", {})
    cfg = Config(
        project=data.get("project", "Event_Recap"),
        variant=data.get("variant", "deterministic"),
        seed=int(data.get("seed", 42)),
        max_duration=float(data.get("max_duration", 60.0)),
        clip_min=float(data.get("clip_min", 1.2)),
        clip_max=float(data.get("clip_max", 4.0)),
        target_range=tuple(data.get("target_range", (2.0, 3.5))),
        weights=dict(weights),
        diversity=DiversitySettings(
            min_gap_same_cam=float(diversity_data.get("min_gap_same_cam", 3.0)),
            max_per_cam_ratio=float(diversity_data.get("max_per_cam_ratio", 0.5)),
        ),
        branding=BrandingSettings(
            logo_path=branding_data.get("logo_path"),
            logo_corner=str(branding_data.get("logo_corner", "bottom_right")),
            logo_size_px=int(branding_data.get("logo_size_px", 64)),
            safe_area=float(branding_data.get("safe_area", 0.8)),
            intro_path=branding_data.get("intro_path"),
            outro_path=branding_data.get("outro_path"),
            lut_path=branding_data.get("lut_path"),
            fonts=tuple(branding_data.get("fonts", [])),
        ),
        deliverables=tuple(data.get("deliverables", ("9:16", "1:1", "16:9"))),
    )
    return cfg


def edl_from_dict(data: Dict[str, object]) -> EDL:
    segments = []
    for seg in data.get("segments", []):
        segments.append(
            Segment(
                src=seg["src"],
                start=float(seg.get("in", seg.get("start", 0.0))),
                end=float(seg.get("out", seg.get("end", 0.0))),
                score=float(seg.get("score", 0.0)),
                tags=tuple(seg.get("tags", [])),
                camera=seg.get("cam"),
            )
        )
    return EDL(
        project=data.get("project", "Event_Recap"),
        variant=data.get("variant", "deterministic"),
        seed=int(data.get("seed", 42)),
        max_duration=float(data.get("max_duration", 60.0)),
        clip_min=float(data.get("clip_min", 1.2)),
        clip_max=float(data.get("clip_max", 4.0)),
        segments=segments,
        metadata=data.get("metadata", {}),
    )


def edl_from_file(path: Path) -> EDL:
    return edl_from_dict(json.loads(Path(path).read_text(encoding='utf-8-sig')))


def _validate_weights(weights: Dict[str, float]) -> None:
    total = sum(weights.values())
    if not weights:
        raise ValueError("weights cannot be empty")
    if not abs(total - 1.0) < 1e-6:
        raise ValueError(f"weights must sum to 1.0 (got {total:.3f})")

    invalid_keys = set(weights) - set(DEFAULT_WEIGHTS)
    if invalid_keys:
        raise ValueError(f"Unsupported weight keys: {sorted(invalid_keys)}")
