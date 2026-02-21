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
    job_id = "smoke-segment-stitch-runtime"
    lineage_path = (
        root / "sandbox" / "logs" / job_id / "qc" / "retry_attempt_lineage.v1.json"
    )

    pre_cmd = [sys.executable, "-m", "repo.tools.smoke_controller_retry_execution"]
    print("RUN:", " ".join(pre_cmd))
    subprocess.check_call(pre_cmd, cwd=str(root))

    if not lineage_path.exists():
        print(f"ERROR: missing lineage contract: {lineage_path}", file=sys.stderr)
        return 1

    val_cmd = [
        sys.executable,
        "-m",
        "repo.tools.validate_retry_attempt_lineage",
        str(lineage_path),
    ]
    print("RUN:", " ".join(val_cmd))
    subprocess.check_call(val_cmd, cwd=str(root))

    payload = _load(lineage_path)
    attempts = payload.get("attempts", [])
    if not isinstance(attempts, list) or len(attempts) == 0:
        print("ERROR: expected non-empty attempt lineage list", file=sys.stderr)
        return 1
    if not any(
        isinstance(a, dict) and a.get("resolution") == "retry" for a in attempts
    ):
        print(
            "ERROR: expected at least one retry resolution in lineage", file=sys.stderr
        )
        return 1

    print("OK:", lineage_path)
    print("lineage_attempt_count:", len(attempts))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
