#!/usr/bin/env python3
from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import tempfile


def _run(cmd: list[str], expect_ok: bool = True) -> None:
    proc = subprocess.run(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
    )
    print(proc.stdout, end="")
    if expect_ok and proc.returncode != 0:
        raise SystemExit(proc.returncode)
    if (not expect_ok) and proc.returncode == 0:
        print("ERROR: expected command to fail but it passed", file=sys.stderr)
        raise SystemExit(1)


def main() -> int:
    root = pathlib.Path(__file__).resolve().parents[2]
    frame_labels = root / "repo" / "examples" / "frame_labels.v1.example.json"
    reverse = root / "repo" / "examples" / "caf.video_reverse_prompt.v1.example.json"
    keyframes = root / "repo" / "examples" / "keyframe_checkpoints.v1.example.json"

    _run(
        [
            sys.executable,
            "-m",
            "repo.tools.validate_frame_labels",
            "--frame-labels",
            str(frame_labels),
            "--reverse",
            str(reverse),
            "--keyframes",
            str(keyframes),
        ]
    )

    # Deterministic negative case: violate facts authority by mutating camera_mode.
    with frame_labels.open("r", encoding="utf-8") as f:
        doc = json.load(f)
    if not isinstance(doc, dict):
        print("ERROR: invalid example doc", file=sys.stderr)
        return 1
    frames = doc.get("frames", [])
    if isinstance(frames, list) and frames and isinstance(frames[0], dict):
        facts = frames[0].get("facts")
        if isinstance(facts, dict):
            facts["camera_mode"] = "pan"

    with tempfile.NamedTemporaryFile(
        prefix="caf-frame-labels-bad-",
        suffix=".json",
        mode="w",
        encoding="utf-8",
        delete=False,
    ) as tmp:
        json.dump(doc, tmp, indent=2, ensure_ascii=False)
        tmp.write("\n")
        bad_path = pathlib.Path(tmp.name)

    _run(
        [
            sys.executable,
            "-m",
            "repo.tools.validate_frame_labels",
            "--frame-labels",
            str(bad_path),
            "--reverse",
            str(reverse),
            "--keyframes",
            str(keyframes),
        ],
        expect_ok=False,
    )

    print("OK: frame-labels contract smoke")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
