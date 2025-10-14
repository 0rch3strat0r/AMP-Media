"""Common dataclasses used by analysis modules."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Set


@dataclass
class DetectionEvent:
    time: float
    score: float
    tag: str


@dataclass
class CandidateClip:
    src: str
    start: float
    end: float
    score: float
    tags: Set[str] = field(default_factory=set)
    camera: str | None = None

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)

    def add_tags(self, *extra: Iterable[str]) -> None:
        for collection in extra:
            if isinstance(collection, str):
                self.tags.add(collection)
            else:
                self.tags.update(collection)
