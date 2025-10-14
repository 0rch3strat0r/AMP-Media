"""Command line interface for AMP Mini highlight builder."""

from __future__ import annotations
import argparse
import glob
import json
import logging
import os
import subprocess
from pathlib import Path
from typing import Iterable, List, Optional
from . import analysis
from .analysis.types import CandidateClip
from .edl import Config, EDL, edl_from_file, load_config
from .render.ffmpeg_cmd import build_commands
from .render.shotstack import build_shotstack_timeline
from .selection.select import select_segments

def _load_config(path: Optional[Path]) -> Config:

    return load_config(Path(path)) if path else load_config(None)

def _override_seed_in_config(cfg: Config, seed: Optional[int]) -> Config:
    if seed is None:
        return cfg
    cfg.seed = int(seed)
    return cfg


def _resolve_inputs(inputs: Iterable[str]) -> List[Path]:
    files: List[Path] = []
    for raw in inputs:
        if raw is None:
            continue
        tokens = [token.strip() for token in str(raw).split(',') if token.strip()]
        for token in tokens:
            expanded = _expand_token(token)
            files.extend(expanded)
    if not files:
        joined = ', '.join(str(s) for s in inputs)
        raise ValueError(f"--inputs resolved to no files. Provided: {joined}")
    unique: dict[str, Path] = {}
    for item in files:
        unique.setdefault(str(item), item)
    return sorted(unique.values(), key=lambda p: str(p).lower())


def _expand_token(token: str) -> List[Path]:
    token = token.strip().strip("'").strip('"')
    if not token:
        return []
    if os.path.isdir(token):
        directory = Path(token)
        patterns = ('*.mp4', '*.mov', '*.mkv')
        matches: List[Path] = []
        for pattern in patterns:
            matches.extend(sorted(directory.glob(pattern)))
        return matches
    if any(ch in token for ch in ('*', '?', '[')):
        return [Path(p) for p in sorted(glob.glob(token)) if Path(p).is_file()]
    candidate = Path(token)
    return [candidate] if candidate.is_file() else []

LOGGER = logging.getLogger("mini")

def main(argv: Iterable[str] | None = None) -> int:

    parser = _build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
    if args.command == "analyze":
        return _cmd_analyze(args)
    if args.command == "render":
        return _cmd_render(args)
    if args.command == "shotstack":
        return _cmd_shotstack(args)
    if args.command == "pipeline":
        return _cmd_pipeline(args)
    parser.print_help()
    return 1

def _build_parser() -> argparse.ArgumentParser:

    parser = argparse.ArgumentParser(prog="mini", description="AMP Mini highlight builder")
    sub = parser.add_subparsers(dest="command")
    analyze = sub.add_parser("analyze", help="Analyze inputs and produce an EDL JSON")
    analyze.add_argument("--inputs", nargs="+", required=True, help="Input video files")
    analyze.add_argument("--config", help="Config JSON path", default=None)
    analyze.add_argument("--output", help="Output EDL path", default=None)
    analyze.add_argument("--seed", type=int, help="Override seed for this run")
    render = sub.add_parser("render", help="Render MP4s from an EDL")
    render.add_argument("--edl", required=True, help="EDL JSON path")
    render.add_argument("--config", help="Config JSON path", default=None)
    render.add_argument("--output", required=True, help="Output file stub (e.g., out.mp4)")
    render.add_argument("--run", action="store_true", help="Execute ffmpeg commands")
    shotstack = sub.add_parser("shotstack", help="Emit Shotstack timeline JSON from an EDL")
    shotstack.add_argument("--edl", required=True, help="EDL JSON path")
    shotstack.add_argument("--config", help="Config JSON path", default=None)
    shotstack.add_argument("--out", required=True, help="Timeline JSON output path")
    pipeline = sub.add_parser("pipeline", help="Run analyze+render in one step")
    pipeline.add_argument("--inputs", nargs="+", required=True, help="Input video files")
    pipeline.add_argument("--config", help="Config JSON path", default=None)
    pipeline.add_argument("--output", required=True, help="Output file stub (e.g., recap.mp4)")
    pipeline.add_argument("--seed", type=int, help="Override seed for deterministic run")
    pipeline.add_argument("--run", action="store_true", help="Execute ffmpeg commands")
    pipeline.add_argument("--edl", help="Optional EDL output path", default=None)
    return parser

def _cmd_analyze(args) -> int:

    config = _override_seed_in_config(_load_config(args.config), getattr(args, "seed", None))
    sources = _resolve_inputs(args.inputs)
    candidate_map = analysis.analyze_sources(sources, config)
    edl, metrics = select_segments(candidate_map, config)
    edl.metadata.setdefault("metrics", metrics)
    if args.output:
        Path(args.output).write_text(json.dumps(edl.to_dict(), indent=2), encoding="utf-8")
        LOGGER.info("Wrote EDL to %s", args.output)
    else:
        print(json.dumps(edl.to_dict(), indent=2))
    return 0

def _cmd_render(args) -> int:

    config = _override_seed_in_config(_load_config(args.config), getattr(args, "seed", None))
    edl = edl_from_file(Path(args.edl))
    commands = build_commands(edl, config, Path(args.output))
    for ratio, cmd in commands.items():
        LOGGER.info("FFmpeg command for %s: %s", ratio, " ".join(cmd))
        if args.run:
            _run_command(cmd)
    return 0

def _cmd_shotstack(args) -> int:

    config = _override_seed_in_config(_load_config(args.config), getattr(args, "seed", None))
    edl = edl_from_file(Path(args.edl))
    timeline = build_shotstack_timeline(edl, config)
    Path(args.out).write_text(json.dumps(timeline, indent=2), encoding="utf-8")
    LOGGER.info("Wrote Shotstack JSON to %s", args.out)
    return 0

def _cmd_pipeline(args) -> int:

    config = _override_seed_in_config(_load_config(args.config), getattr(args, "seed", None))
    sources = _resolve_inputs(args.inputs)
    candidate_map = analysis.analyze_sources(sources, config)
    edl, metrics = select_segments(candidate_map, config)
    edl.metadata.setdefault("metrics", metrics)
    if args.edl:
        Path(args.edl).write_text(json.dumps(edl.to_dict(), indent=2), encoding="utf-8")
        LOGGER.info("Wrote EDL to %s", args.edl)
    commands = build_commands(edl, config, Path(args.output))
    for ratio, cmd in commands.items():
        LOGGER.info("FFmpeg command for %s: %s", ratio, " ".join(cmd))
        if args.run:
            _run_command(cmd)
    return 0

def _run_command(cmd: List[str]) -> None:

    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    process = subprocess.run(cmd, env=env)
    if process.returncode != 0:
        raise RuntimeError(f"Command failed with exit code {process.returncode}: {' '.join(cmd)}")

if __name__ == "__main__":  # pragma: no cover

    raise SystemExit(main())
