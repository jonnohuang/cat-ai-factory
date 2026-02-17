#!/usr/bin/env python3
from __future__ import annotations

import json
import pathlib
import subprocess
import sys

from repo.services.planner.planner_cli import _apply_continuity_pack_hints, _load_quality_context


def _repo_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parents[2]


def _load(path: pathlib.Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def main(argv: list[str]) -> int:
    root = _repo_root()
    quality_context = _load_quality_context(str(root), None)
    job = {"job_id": "smoke-segment-stitch-runtime"}
    job = _apply_continuity_pack_hints(job, quality_context)
    relpath = job.get("continuity_pack", {}).get("relpath") if isinstance(job.get("continuity_pack"), dict) else None
    if relpath != "repo/examples/episode_continuity_pack.v1.example.json":
        print(f"ERROR: planner did not apply continuity pack relpath, got {relpath!r}", file=sys.stderr)
        return 1

    job_id = "smoke-segment-stitch-runtime"
    job_path = root / "sandbox" / "jobs" / f"{job_id}.job.json"
    original_job_text = job_path.read_text(encoding="utf-8")
    patched = json.loads(original_job_text)
    patched["continuity_pack"] = {"relpath": relpath}
    job_path.write_text(json.dumps(patched, indent=2) + "\n", encoding="utf-8")

    decide_cmd = [sys.executable, "-m", "repo.tools.decide_quality_action", "--job-id", job_id, "--max-retries", "0"]
    print("RUN:", " ".join(decide_cmd))
    try:
        subprocess.check_call(decide_cmd, cwd=str(root))

        decision_path = root / "sandbox" / "logs" / job_id / "qc" / "quality_decision.v1.json"
        validate_cmd = [sys.executable, "-m", "repo.tools.validate_quality_decision", str(decision_path)]
        print("RUN:", " ".join(validate_cmd))
        subprocess.check_call(validate_cmd, cwd=str(root))

        decision = _load(decision_path)
        d_relpath = decision.get("inputs", {}).get("continuity_pack_relpath")
        action = decision.get("decision", {}).get("action")
        if d_relpath != "repo/examples/episode_continuity_pack.v1.example.json":
            print(f"ERROR: quality decision did not consume continuity pack relpath, got {d_relpath!r}", file=sys.stderr)
            return 1
        if action != "block_for_costume":
            print(f"ERROR: expected block_for_costume due to continuity rule, got {action!r}", file=sys.stderr)
            return 1

        print("OK:", job_path)
        print("OK:", decision_path)
        print("decision_action:", action)
        return 0
    finally:
        job_path.write_text(original_job_text, encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
