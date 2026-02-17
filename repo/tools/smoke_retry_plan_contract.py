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
    qc_dir = root / "sandbox" / "logs" / job_id / "qc"
    decision_path = qc_dir / "quality_decision.v1.json"
    retry_plan_path = qc_dir / "retry_plan.v1.json"

    pre_cmd = [sys.executable, "-m", "repo.tools.smoke_quality_segment_retry"]
    print("RUN:", " ".join(pre_cmd))
    subprocess.check_call(pre_cmd, cwd=str(root))

    if not retry_plan_path.exists():
        print(f"ERROR: missing retry plan: {retry_plan_path}", file=sys.stderr)
        return 1

    val_cmd = [sys.executable, "-m", "repo.tools.validate_retry_plan", str(retry_plan_path)]
    print("RUN:", " ".join(val_cmd))
    subprocess.check_call(val_cmd, cwd=str(root))

    decision = _load(decision_path)
    retry_plan = _load(retry_plan_path)
    action = decision.get("decision", {}).get("action")
    retry_type = retry_plan.get("retry", {}).get("retry_type")
    if action == "retry_motion" and retry_type != "motion":
        print(
            f"ERROR: expected retry_type motion for action retry_motion, got {retry_type!r}",
            file=sys.stderr,
        )
        return 1

    print("OK:", retry_plan_path)
    print("decision_action:", action)
    print("retry_type:", retry_type)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
