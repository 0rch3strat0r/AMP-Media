import argparse
import hashlib
import json
import os
import subprocess
import sys

CHUNK_SIZE = 1 << 20  # 1 MiB

def sha256(path: str) -> str:
    """Return SHA-256 hex digest for a file."""
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()

def ffprobe_duration(path: str) -> float:
    """Query media duration (seconds) via ffprobe."""
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", path]
    output = subprocess.check_output(cmd, text=True).strip()
    return float(output)

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate deterministic pipeline outputs")
    parser.add_argument("--config", required=True, help="Config JSON path")
    parser.add_argument("--edl1", required=True, help="First run EDL JSON")
    parser.add_argument("--edl2", required=True, help="Second run EDL JSON")
    parser.add_argument("--vid1", required=True, help="First run video output")
    parser.add_argument("--vid2", required=True, help="Second run video output")
    parser.add_argument("--max_duration", type=float, default=60.2, help="Maximum allowed reel duration")
    parser.add_argument("--duration_tol", type=float, default=0.25, help="Allowed duration delta between runs")
    args = parser.parse_args(argv)

    cfg = json.load(open(args.config, "r", encoding="utf-8-sig"))
    deliverables = cfg.get("deliverables", ["9:16", "1:1", "16:9"])

    edl1 = json.load(open(args.edl1, "r", encoding="utf-8"))
    edl2 = json.load(open(args.edl2, "r", encoding="utf-8"))
    if not edl1.get("segments") or not edl2.get("segments"):
        print("EDL missing segments", file=sys.stderr)
        return 2
    if edl1["segments"] != edl2["segments"]:
        print("EDLs differ; determinism failed", file=sys.stderr)
        return 3

    if not os.path.exists(args.vid1) or not os.path.exists(args.vid2):
        print("Rendered files not found", file=sys.stderr)
        return 4

    dur1 = ffprobe_duration(args.vid1)
    dur2 = ffprobe_duration(args.vid2)
    if dur1 > args.max_duration or dur2 > args.max_duration:
        print(f"Duration exceeds cap: run1={dur1:.3f}s run2={dur2:.3f}s", file=sys.stderr)
        return 5
    if abs(dur1 - dur2) > args.duration_tol:
        print(f"Duration mismatch between runs: {dur1:.3f}s vs {dur2:.3f}s", file=sys.stderr)
        return 6

    hash1 = sha256(args.vid1)
    hash2 = sha256(args.vid2)

    print(json.dumps({
        "deterministic_edl": True,
        "durations": {"run1": dur1, "run2": dur2},
        "hashes": {"run1": hash1, "run2": hash2},
        "deliverables": deliverables
    }, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
