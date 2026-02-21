#!/usr/bin/env python3
from __future__ import annotations

import json
import pathlib
import subprocess
import sys


def _repo_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parents[2]


def _load(path: pathlib.Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def main(argv: list[str]) -> int:
    root = _repo_root()
    pre_cmd = [sys.executable, "-m", "repo.tools.smoke_segment_stitch_runtime"]
    print("RUN:", " ".join(pre_cmd))
    subprocess.check_call(pre_cmd, cwd=str(root))

    manifest = (
        root
        / "sandbox"
        / "output"
        / "smoke-segment-stitch-runtime"
        / "debug"
        / "segment_debug_manifest.v1.json"
    )
    result = (
        root / "sandbox" / "output" / "smoke-segment-stitch-runtime" / "result.json"
    )
    validate_cmd = [
        sys.executable,
        "-m",
        "repo.tools.validate_segment_debug_manifest",
        str(manifest),
    ]
    print("RUN:", " ".join(validate_cmd))
    subprocess.check_call(validate_cmd, cwd=str(root))

    payload = _load(manifest)
    if not isinstance(payload.get("seam_previews"), list):
        print("ERROR: seam_previews missing", file=sys.stderr)
        return 1
    for seam in payload.get("seam_previews", []):
        p = seam.get("preview_relpath")
        if isinstance(p, str) and not (root / p).exists():
            print(f"ERROR: seam preview missing: {p}", file=sys.stderr)
            return 1
    mpath = payload.get("motion_curve_snapshot_relpath")
    if not isinstance(mpath, str) or not (root / mpath).exists():
        print("ERROR: motion curve snapshot missing", file=sys.stderr)
        return 1

    result_data = _load(result)
    dbg = result_data.get("segment_debug_exports")
    if not isinstance(dbg, dict):
        print("ERROR: result.json missing segment_debug_exports", file=sys.stderr)
        return 1
    print("OK:", manifest)
    print("OK:", result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
