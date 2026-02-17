#!/usr/bin/env python3
"""
smoke_viggle_handoff.py

Smoke test for PR-34.1/34.2/34.3 external HITL recast flow artifacts.
"""
from __future__ import annotations

import pathlib
import subprocess
import sys


def _repo_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parents[2]


def _latest_pointer(inbox: pathlib.Path, job_id: str) -> pathlib.Path:
    files = sorted(inbox.glob(f"viggle-reingest-{job_id}-*.json"))
    if not files:
        raise SystemExit("No viggle re-ingest pointer produced")
    return files[-1]


def main(argv: list[str]) -> int:
    _ = argv
    root = _repo_root()
    job_path = root / "sandbox/jobs/mochi-dino-replace-smoke-20240515.job.json"
    job_id = "mochi-dino-replace-smoke-20240515"
    result_rel = f"sandbox/inbox/viggle_results/{job_id}/viggle.mp4"
    result_abs = root / result_rel
    result_abs.parent.mkdir(parents=True, exist_ok=True)

    # Reuse existing demo video as mock external output.
    src = root / "sandbox/assets/demo/mochi_dance_loop_swap.mp4"
    result_abs.write_bytes(src.read_bytes())

    commands = [
        [
            sys.executable,
            "repo/tools/export_viggle_pack.py",
            "--job",
            str(job_path),
            "--hero-id",
            "mochi-grey-tabby",
            "--motion-video",
            "assets/demo/dance_loop.mp4",
            "--costume-profile-id",
            "dance_loop_dino_onesie",
            "--prompt",
            "Replace dancer with Mochi while preserving choreography and camera timing.",
        ],
        [
            sys.executable,
            "repo/tools/create_viggle_reingest_pointer.py",
            "--job-id",
            job_id,
            "--result-video-relpath",
            result_rel,
            "--notes",
            "smoke test pointer",
        ],
    ]
    for cmd in commands:
        print("RUN:", " ".join(cmd))
        subprocess.check_call(cmd, cwd=str(root))

    pointer = _latest_pointer(root / "sandbox/inbox", job_id)
    process_cmd = [sys.executable, "repo/tools/process_viggle_reingest.py", "--pointer", str(pointer)]
    print("RUN:", " ".join(process_cmd))
    subprocess.check_call(process_cmd, cwd=str(root))

    validate_cmd = [
        sys.executable,
        "-m",
        "repo.tools.validate_viggle_handoff",
        "--pack",
        str(root / f"sandbox/dist_artifacts/{job_id}/viggle_pack/viggle_pack.v1.json"),
        "--lifecycle",
        str(root / f"sandbox/dist_artifacts/{job_id}/viggle_pack/external_recast_lifecycle.v1.json"),
        "--pointer",
        str(pointer),
    ]
    print("RUN:", " ".join(validate_cmd))
    subprocess.check_call(validate_cmd, cwd=str(root))
    print("OK: Viggle handoff smoke")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
