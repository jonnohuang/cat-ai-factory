#!/usr/bin/env python3
"""Smoke test for the new Director loop in PR-39."""

import json
import os
import pathlib
import shutil
import subprocess
import sys

# repo/tools/smoke_director_loop.py -> <repo_root>
repo_root = pathlib.Path(__file__).resolve().parents[2]
sys.path.append(str(repo_root))

def setup_job(job_id: str):
    root = repo_root
    jobs_dir = root / "sandbox" / "jobs"
    jobs_dir.mkdir(parents=True, exist_ok=True)

    job_path = jobs_dir / f"{job_id}.job.json"
    job_data = {
        "job_id": job_id,
        "lane": "ai_video",
        "video": {"length_seconds": 4, "fps": 24},
        "shots": [
            {"shot_id": "shot_1", "visual": "scene 1", "t": [0, 2]},
            {"shot_id": "shot_2", "visual": "scene 2", "t": [2, 4]},
        ],
        "render": {
            "segment_generation_contract": "shot_by_shot",
            "background_asset": "sandbox/assets/demo/dance_loop.mp4",
        }
    }
    job_path.write_text(json.dumps(job_data, indent=2))
    return job_path

def main():
    job_id = "smoke-director-loop"
    root = repo_root
    
    # Clean up
    shutil.rmtree(root / "sandbox" / "output" / job_id, ignore_errors=True)
    shutil.rmtree(root / "sandbox" / "logs" / job_id, ignore_errors=True)
    
    job_path = setup_job(job_id)
    
    print(f"--- Running Orchestrator for {job_id} ---")
    
    cmd = [
        sys.executable,
        "-m", "repo.services.orchestrator.ralph_loop",
        "--job", str(job_path),
        "--max-retries", "1"
    ]
    
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root)
    env["CAF_VEO_MOCK"] = "1" # Use mock mode for faster testing
    
    try:
        subprocess.check_call(cmd, env=env)
        print("Orchestrator finished successfully.")
    except subprocess.CalledProcessError as e:
        print(f"Orchestrator failed with code {e.returncode}")
        sys.exit(1)

    # Verify outputs
    out_dir = root / "sandbox" / "output" / job_id
    shots_dir = out_dir / "shots"
    
    assert (shots_dir / "shot_1" / "final.mp4").exists(), "shot_1/final.mp4 missing"
    assert (shots_dir / "shot_2" / "final.mp4").exists(), "shot_2/final.mp4 missing"
    assert (out_dir / "final.mp4").exists(), "final assembled video missing"
    
    # Verify director state
    state_file = root / "sandbox" / "logs" / job_id / "director" / "state.v1.json"
    assert state_file.exists(), "Director state file missing"
    state_data = json.loads(state_file.read_text())
    assert state_data["shots"]["shot_1"]["status"] == "ready"
    assert state_data["shots"]["shot_2"]["status"] == "ready"
    assert state_data["assembly"]["status"] == "completed"

    print("SUCCESS: Director loop verified!")

if __name__ == "__main__":
    main()
