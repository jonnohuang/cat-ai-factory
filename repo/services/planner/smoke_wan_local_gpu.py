#!/usr/bin/env python3
"""Smoke test for Wan 2.2 Motion Engine (PR-111)."""

import json
import os
import pathlib
import subprocess
import sys

# repo_root
repo_root = pathlib.Path(__file__).resolve().parents[3]
sys.path.append(str(repo_root))

from repo.services.planner.providers.wan_2_2 import Wan22Provider


def test_wan_integration():
    print("--- WAN 2.2 SMOKE TEST ---")

    # 1. Generate Job
    planner = Wan22Provider()
    prd = {
        "prompt": "Kitten dancing disco 24s",
        "niche": "cats",
        "date": "2026-02-22"
    }
    job = planner.generate_job(prd)

    job_id = job["job_id"]
    job_path = repo_root / "sandbox" / "jobs" / f"{job_id}.smoke.json"
    job_path.parent.mkdir(parents=True, exist_ok=True)

    with open(job_path, "w") as f:
        json.dump(job, f, indent=2)
    print(f"Generated smoke job: {job_path}")

    # 2. Run Worker (Scaffold)
    worker_script = repo_root / "repo" / "worker" / "render_wan.py"
    out_dir = repo_root / "sandbox" / "output" / "smoke-wan"

    cmd = [
        sys.executable,
        str(worker_script),
        "--job", str(job_path),
        "--out-dir", str(out_dir)
    ]

    print(f"Running worker: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)

    print("STDOUT:", result.stdout)
    if result.stderr:
        print("STDERR:", result.stderr)

    if result.returncode == 0:
        print("SUCCESS: Wan 2.2 integration smoke test passed (scaffold mode).")
    else:
        print(f"FAILED: Worker exited with {result.returncode}")
        sys.exit(1)

if __name__ == "__main__":
    test_wan_integration()
