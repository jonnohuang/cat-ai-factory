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
    job_id = argv[1] if len(argv) > 1 else "smoke-segment-stitch-runtime"

    derive_cmd = [
        sys.executable,
        "-m",
        "repo.tools.derive_two_pass_orchestration",
        "--job-id",
        job_id,
    ]
    print("RUN:", " ".join(derive_cmd))
    subprocess.check_call(derive_cmd, cwd=str(root))

    two_pass_path = (
        root / "sandbox" / "logs" / job_id / "qc" / "two_pass_orchestration.v1.json"
    )
    val_two_pass_cmd = [
        sys.executable,
        "-m",
        "repo.tools.validate_two_pass_orchestration",
        str(two_pass_path),
    ]
    print("RUN:", " ".join(val_two_pass_cmd))
    subprocess.check_call(val_two_pass_cmd, cwd=str(root))

    decide_cmd = [
        sys.executable,
        "-m",
        "repo.tools.decide_quality_action",
        "--job-id",
        job_id,
        "--max-retries",
        "2",
    ]
    print("RUN:", " ".join(decide_cmd))
    subprocess.check_call(decide_cmd, cwd=str(root))

    quality_decision_path = (
        root / "sandbox" / "logs" / job_id / "qc" / "quality_decision.v1.json"
    )
    val_quality_cmd = [
        sys.executable,
        "-m",
        "repo.tools.validate_quality_decision",
        str(quality_decision_path),
    ]
    print("RUN:", " ".join(val_quality_cmd))
    subprocess.check_call(val_quality_cmd, cwd=str(root))

    two_pass = _load(two_pass_path)
    decision = _load(quality_decision_path)

    two_pass_rel = decision.get("inputs", {}).get("two_pass_orchestration_relpath")
    if not isinstance(two_pass_rel, str) or not two_pass_rel.startswith(
        f"sandbox/logs/{job_id}/qc/"
    ):
        print("ERROR: decision missing two_pass_orchestration_relpath", file=sys.stderr)
        return 1

    action = str(decision.get("decision", {}).get("action", ""))
    if action not in {
        "proceed_finalize",
        "retry_motion",
        "retry_recast",
        "block_for_costume",
        "escalate_hitl",
    }:
        print(f"ERROR: unexpected action {action!r}", file=sys.stderr)
        return 1

    print("OK:", two_pass_path)
    print("OK:", quality_decision_path)
    print(
        "next_preferred_action:",
        two_pass.get("orchestration", {}).get("next_preferred_action"),
    )
    print("decision_action:", action)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
