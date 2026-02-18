#!/usr/bin/env python3
from __future__ import annotations

import json
import pathlib
import tempfile
import sys

from repo.worker.render_ffmpeg import prepare_subtitles_file


def _load_json(path: pathlib.Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"expected object JSON: {path}")
    return data


def main() -> int:
    root = pathlib.Path(__file__).resolve().parents[2]
    sandbox_root = root / "sandbox"
    out_dir = pathlib.Path(tempfile.mkdtemp(prefix="caf-captions-smoke-", dir=str(root / "sandbox" / "output")))
    srt_out = out_dir / "final.srt"

    # Validate example artifact using schema validator command.
    import subprocess
    proc = subprocess.run(
        [sys.executable, "-m", "repo.tools.validate_captions_artifact", str(root / "repo" / "examples" / "captions_artifact.v1.example.json")],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    print(proc.stdout, end="")
    if proc.returncode != 0:
        return proc.returncode

    # Case A: valid external artifact path -> ready_to_burn + non-empty srt.
    job_a = {
        "captions_artifact": {
            "relpath": "repo/examples/captions_artifact.v1.example.json"
        },
        "captions": []
    }
    status_a = prepare_subtitles_file(job_a, srt_out, sandbox_root)
    if status_a != "ready_to_burn":
        print(f"ERROR: expected ready_to_burn, got {status_a}", file=sys.stderr)
        return 1
    if not srt_out.exists() or srt_out.stat().st_size == 0:
        print("ERROR: expected non-empty final.srt from captions artifact", file=sys.stderr)
        return 1

    # Case B: missing external artifact path -> non-blocking skip + empty srt.
    job_b = {
        "captions_artifact": {
            "relpath": "repo/examples/does-not-exist.captions_artifact.v1.json"
        },
        "captions": []
    }
    status_b = prepare_subtitles_file(job_b, srt_out, sandbox_root)
    if status_b != "skipped_external_missing":
        print(f"ERROR: expected skipped_external_missing, got {status_b}", file=sys.stderr)
        return 1
    if not srt_out.exists():
        print("ERROR: expected final.srt to exist for empty fallback", file=sys.stderr)
        return 1

    print("captions_artifact_status_valid: ready_to_burn")
    print("captions_artifact_status_missing: skipped_external_missing")
    print("OK: optional captions artifact smoke")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
