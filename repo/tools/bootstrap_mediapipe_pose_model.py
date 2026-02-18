#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import pathlib
import sys
import urllib.request


DEFAULT_URL = (
    "https://storage.googleapis.com/mediapipe-models/pose_landmarker/"
    "pose_landmarker_lite/float16/latest/pose_landmarker_lite.task"
)


def _repo_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parents[2]


def _download(url: str, dst: pathlib.Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_suffix(dst.suffix + ".part")
    req = urllib.request.Request(url=url, method="GET")
    with urllib.request.urlopen(req, timeout=120) as resp, tmp.open("wb") as f:
        while True:
            chunk = resp.read(1024 * 1024)
            if not chunk:
                break
            f.write(chunk)
    tmp.replace(dst)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Download MediaPipe PoseLandmarker model for CAF pose preprocessing."
    )
    parser.add_argument(
        "--url",
        default=os.environ.get("CAF_MEDIAPIPE_POSE_MODEL_URL", "").strip() or DEFAULT_URL,
    )
    parser.add_argument(
        "--out",
        default=os.environ.get("CAF_MEDIAPIPE_POSE_MODEL", "").strip(),
        help="Target .task path. Defaults to sandbox/assets/models/mediapipe/pose_landmarker_lite.task",
    )
    args = parser.parse_args(argv)

    root = _repo_root()
    out = pathlib.Path(args.out) if args.out else (
        root / "sandbox" / "assets" / "models" / "mediapipe" / "pose_landmarker_lite.task"
    )
    if not out.is_absolute():
        out = (root / out).resolve()

    print(f"Downloading MediaPipe pose model to: {out}")
    try:
        _download(args.url, out)
    except Exception as ex:
        print(f"ERROR: download failed: {ex}", file=sys.stderr)
        return 1
    print(f"OK: downloaded {out}")
    print("Set CAF_MEDIAPIPE_POSE_MODEL to this path (or leave default path in place).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

