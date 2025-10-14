"""Shotstack timeline export helper."""

from __future__ import annotations

from typing import Dict, List

from ..edl import BrandingSettings, Config, EDL, Segment


def build_shotstack_timeline(edl: EDL, config: Config) -> Dict[str, object]:
    """Return a Shotstack timeline JSON payload representing the EDL."""
    clips: List[Dict[str, object]] = []
    cursor = 0.0
    for segment in edl.segments:
        duration = segment.duration
        clips.append(
            {
                "asset": {
                    "type": "video",
                    "src": segment.src,
                    "trim": round(segment.start, 3),
                },
                "length": round(duration, 3),
                "start": round(cursor, 3),
            }
        )
        cursor += duration

    timeline: Dict[str, object] = {
        "timeline": {
            "background": "#000000",
            "soundtrack": {
                "src": edl.segments[0].src if edl.segments else "",
                "effect": "fade",
            },
            "tracks": [
                {"clips": clips},
            ],
        },
        "output": {
            "format": "mp4",
            "resolution": _primary_resolution(config),
        },
    }

    overlay = _build_logo_overlay(config.branding, cursor)
    if overlay is not None:
        timeline["timeline"]["tracks"].append({"clips": [overlay]})

    return timeline


def _primary_resolution(config: Config) -> str:
    deliverable = config.deliverables[0] if config.deliverables else "9:16"
    mapping = {
        "9:16": "vertical",
        "1:1": "square",
        "16:9": "hd",
    }
    return mapping.get(deliverable, "vertical")


def _build_logo_overlay(branding: BrandingSettings, total_length: float) -> Dict[str, object] | None:
    if not branding.logo_path:
        return None
    return {
        "asset": {"type": "image", "src": branding.logo_path, "fit": "contain"},
        "length": round(total_length, 3),
        "start": 0.0,
        "position": branding.logo_corner or "bottom_right",
    }
