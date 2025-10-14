"""FFmpeg command assembly for highlight rendering."""

import json
import logging
import os
import shutil
import subprocess
from collections import Counter
from functools import lru_cache
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from ..edl import BrandingSettings, Config, EDL, Segment

LOGGER = logging.getLogger(__name__)

ASPECT_DIMENSIONS = {

    "9:16": (1080, 1920),

    "1:1": (1080, 1080),

    "16:9": (1920, 1080),

}

def build_commands(edl: EDL, config: Config, output_stub: Path) -> Dict[str, List[str]]:

    """Return ffmpeg command lines for each requested deliverable ratio."""

    if not edl.segments:

        raise ValueError("EDL contains no segments to render")

    commands: Dict[str, List[str]] = {}

    for ratio in config.deliverables:

        dims = ASPECT_DIMENSIONS.get(ratio)

        if dims is None:

            LOGGER.warning("Unsupported deliverable ratio %s, skipping", ratio)

            continue

        output_path = _derive_output_path(output_stub, ratio)

        cmd = _build_single_command(edl, config.branding, edl.segments, dims[0], dims[1], output_path)

        commands[ratio] = cmd

    return commands

def _derive_output_path(stub: Path, ratio: str) -> Path:

    stub = Path(stub)

    suffix = stub.suffix or ".mp4"

    base = stub.with_suffix("")

    return Path(f"{base}_{ratio.replace(':', 'x')}{suffix}")

def _build_single_command(

    edl: EDL,

    branding: BrandingSettings,

    segments: Iterable[Segment],

    width: int,

    height: int,

    output_path: Path,

) -> List[str]:

    ordered_sources = list(dict.fromkeys(seg.src for seg in segments))

    input_map = {src: idx for idx, src in enumerate(ordered_sources)}

    input_args: List[str] = []

    for src in ordered_sources:

        input_args.extend(["-i", src])

    logo_index: Optional[int] = None

    if branding.logo_path:

        logo_path = Path(branding.logo_path)

        if logo_path.exists():

            logo_index = len(ordered_sources)

            input_args.extend(["-i", str(logo_path)])

        else:

            LOGGER.warning("Logo asset %s not found; skipping overlay", branding.logo_path)

    audio_presence = {input_map[src]: _has_audio_stream(src) for src in ordered_sources}

    segment_payload: List[Dict[str, float]] = []

    for seg in segments:

        idx = input_map[seg.src]

        segment_payload.append(

            {

                "src_index": idx,

                "in": float(seg.start),

                "out": float(seg.end),

            }

        )

    filter_complex, video_label, audio_label = build_filter_complex(

        segment_payload,

        inputs_count=len(ordered_sources),

        logo_idx=logo_index,

        width=width,

        height=height,

        source_audio=audio_presence,

        logo_corner=branding.logo_corner,

        logo_safe_area=branding.safe_area,

    )

    cmd = [

        _ffmpeg_executable(),

        "-y",

        *input_args,

        "-filter_complex",

        filter_complex,

        "-map",

        video_label,

        "-map",

        audio_label,

        "-c:v",

        "libx264",

        "-preset",

        "veryfast",

        "-crf",

        "18",

        "-c:a",

        "aac",

        "-b:a",

        "192k",

        "-movflags",

        "+faststart",

        "-r",

        "30",

        str(output_path),

    ]

    return cmd

def build_filter_complex(

    segments: List[Dict[str, float]],

    inputs_count: int,

    logo_idx: Optional[int],

    width: int,

    height: int,

    *,

    source_audio: Optional[Dict[int, bool]] = None,

    logo_corner: str = "bottom_right",

    logo_safe_area: float = 0.8,

    loudnorm: bool = True,

    synth_silence_for_missing_audio: bool = True,

) -> Tuple[str, str, str]:

    """Construct the filter_complex graph and return (graph, video_label, audio_label)."""

    lines: List[str] = []

    audio_flags = source_audio or {i: True for i in range(inputs_count)}

    usage_counts = Counter(int(seg["src_index"]) for seg in segments)

    video_branches: Dict[int, List[str]] = {}

    audio_branches: Dict[int, List[str]] = {}

    for idx in range(inputs_count):

        count = usage_counts.get(idx, 0)

        if count == 0:

            continue

        base_v = f"v{idx}base"

        lines.append(f"[{idx}:v]setsar=1[{base_v}]")

        if count > 1:

            v_labels = [f"v{idx}b{n}" for n in range(count)]

            split_expr = ''.join(f"[{label}]" for label in v_labels)

            lines.append(f"[{base_v}]split={count}{split_expr}")

        else:

            v_labels = [base_v]

        video_branches[idx] = v_labels

        if audio_flags.get(idx, True):

            base_a = f"a{idx}base"

            lines.append(f"[{idx}:a]aresample=48000,aformat=channel_layouts=stereo[{base_a}]")

            if count > 1:

                a_labels = [f"a{idx}b{n}" for n in range(count)]

                split_expr = ''.join(f"[{label}]" for label in a_labels)

                lines.append(f"[{base_a}]asplit={count}{split_expr}")

            else:

                a_labels = [base_a]

            audio_branches[idx] = a_labels

        else:

            audio_branches[idx] = []

    video_cursor = {idx: 0 for idx in video_branches}

    audio_cursor = {idx: 0 for idx in audio_branches}

    concat_inputs: List[str] = []

    scale_expr = (

        f"scale=iw*min({width}/iw\\,{height}/ih):"

        f"ih*min({width}/iw\\,{height}/ih):flags=lanczos," \

        f"pad={width}:{height}:(max({width}-iw\\,0))/2:(max({height}-ih\\,0))/2:black"

    )

    for idx, seg in enumerate(segments):

        src_idx = int(seg["src_index"])

        start = float(seg["in"])

        end = float(seg["out"])

        if end < start:

            end = start

        duration = max(0.0, end - start)

        v_branch_list = video_branches.get(src_idx)

        if not v_branch_list:

            raise ValueError(f"No video branches for input {src_idx}")

        v_branch = v_branch_list[video_cursor[src_idx]]

        video_cursor[src_idx] += 1

        trim_label = f"vtrim{idx}"

        lines.append(

            f"[{v_branch}]trim=start={start:.3f}:end={end:.3f},setpts=PTS-STARTPTS[{trim_label}]"

        )

        lines.append(f"[{trim_label}]{scale_expr},setsar=1[v{idx}]")

        if audio_flags.get(src_idx, True):

            a_branch_list = audio_branches.get(src_idx)

            if not a_branch_list:

                raise ValueError(f"No audio branches for input {src_idx}")

            a_branch = a_branch_list[audio_cursor[src_idx]]

            audio_cursor[src_idx] += 1

            lines.append(

                f"[{a_branch}]atrim=start={start:.3f}:end={end:.3f},asetpts=PTS-STARTPTS[a{idx}]"

            )

        else:

            if synth_silence_for_missing_audio:

                lines.append(

                    f"anullsrc=r=48000:cl=stereo,atrim=duration={duration:.3f},asetpts=PTS-STARTPTS[a{idx}]"

                )

            else:

                raise ValueError(f"Input {src_idx} has no audio and silence synthesis disabled")

        concat_inputs.append(f"[v{idx}][a{idx}]")

    lines.append(

        f"{''.join(concat_inputs)}concat=n={len(segments)}:v=1:a=1[vcat][acat]"

    )

    if logo_idx is not None:

        pos_x, pos_y = _logo_coordinates(logo_safe_area, logo_corner)

        lines.append(f"[vcat][{logo_idx}]overlay=x={pos_x}:y={pos_y}:format=auto[vo]")

        video_out = "[vo]"

    else:

        video_out = "[vcat]"

    lines.append(f"{video_out}format=yuv420p[vout]")

    if loudnorm:

        lines.append("[acat]loudnorm=I=-14:TP=-1.0:LRA=11[aout]")

    else:

        lines.append("[acat]anorm=2[aout]")

    return ";".join(lines), "[vout]", "[aout]"

def _logo_coordinates(safe_area: float, corner: str) -> Tuple[str, str]:

    safe = max(0.0, min(1.0, safe_area or 0.8))

    margin = (1.0 - safe) / 2.0

    left = f"(main_w*{margin:.3f})"

    right = f"(main_w*(1-{margin:.3f}) - overlay_w)"

    top = f"(main_h*{margin:.3f})"

    bottom = f"(main_h*(1-{margin:.3f}) - overlay_h)"

    corner = (corner or "bottom_right").lower()

    if corner == "bottom_left":

        return left, bottom

    if corner == "top_right":

        return right, top

    if corner == "top_left":

        return left, top

    return right, bottom

def _ffmpeg_executable() -> str:

    custom = os.environ.get("FFMPEG_EXE")

    if custom:

        return custom

    found = shutil.which("ffmpeg")

    if found:

        return found

    return "ffmpeg"

def _ffprobe_executable() -> str:

    custom = os.environ.get("FFPROBE_EXE")

    if custom:

        return custom

    found = shutil.which("ffprobe")

    if found:

        return found

    ffmpeg_path = Path(_ffmpeg_executable())

    candidate = ffmpeg_path.with_name(ffmpeg_path.name.replace("ffmpeg", "ffprobe"))

    if candidate.exists():

        return str(candidate)

    return "ffprobe"

@lru_cache(maxsize=None)

def _has_audio_stream(src: str) -> bool:

    cmd = [

        _ffprobe_executable(),

        "-v",

        "error",

        "-select_streams",

        "a",

        "-show_entries",

        "stream=index",

        "-of",

        "json",

        src,

    ]

    try:

        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)

    except FileNotFoundError:

        LOGGER.warning("ffprobe executable not found; assuming %s has no audio", src)

        return False

    if proc.returncode != 0:

        LOGGER.warning("ffprobe failed for %s: %s", src, proc.stderr.strip())

        return False

    try:

        data = json.loads(proc.stdout or "{}")

    except json.JSONDecodeError:

        LOGGER.warning("ffprobe returned invalid JSON for %s", src)

        return False

    return bool(data.get("streams"))
