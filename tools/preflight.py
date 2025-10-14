import json
import importlib.util
import shutil
import sys

REQUIRED = [
    "numpy",
    "cv2",
    "librosa",
    "soundfile",
    "tqdm",
    "pydantic",
    "typing_extensions",
]


def has_mod(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def main() -> None:
    ffmpeg_path = shutil.which("ffmpeg")
    ffprobe_path = shutil.which("ffprobe")
    missing = [mod for mod in REQUIRED if not has_mod(mod)]

    report = {
        "ffmpeg": bool(ffmpeg_path),
        "ffprobe": bool(ffprobe_path),
        "ffmpeg_path": ffmpeg_path,
        "ffprobe_path": ffprobe_path,
        "missing_modules": missing,
    }
    print(json.dumps(report, indent=2))

    ok = report["ffmpeg"] and report["ffprobe"] and not report["missing_modules"]
    if not ok:
        print(
            "\n[PRE-FLIGHT] ❌ Missing dependencies. Install with:\n"
            "  pip install -r requirements.txt\n",
            file=sys.stderr,
        )
        sys.exit(1)

    print("\n[PRE-FLIGHT] ✅ Environment looks good.")
    sys.exit(0)


if __name__ == "__main__":
    main()
