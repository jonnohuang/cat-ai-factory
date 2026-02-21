#!/usr/bin/env python3
"""Smoke test for DirectorService."""

import json
import os
import pathlib
import shutil
import sys

# repo/tools/smoke_director_service.py -> <repo_root>
repo_root = pathlib.Path(__file__).resolve().parents[2]
sys.path.append(str(repo_root))

from repo.services.orchestrator.director_service import DirectorService

def main():
    sandbox_root = repo_root / "sandbox"
    job_id = "smoke-director-v1"
    
    # Cleanup previous run
    job_out_dir = sandbox_root / "output" / job_id
    job_log_dir = sandbox_root / "logs" / job_id
    if job_out_dir.exists(): shutil.rmtree(job_out_dir)
    if job_log_dir.exists(): shutil.rmtree(job_log_dir)
    
    director = DirectorService(job_id, sandbox_root, repo_root)
    
    job_payload = {
        "job_id": job_id,
        "shots": [
            {"shot_id": "shot-001", "prompt": "cat dancing"},
            {"shot_id": "shot-002", "prompt": "cat sleeping"}
        ]
    }
    
    # 1. Sync shots (should both be pending)
    needed = director.sync_shots(job_payload)
    print(f"Needed shots: {needed}")
    assert len(needed) == 2
    
    # 2. Mock rendering shot-001
    shot_001_dir = director.get_shot_output_dir("shot-001")
    shot_001_dir.mkdir(parents=True, exist_ok=True)
    (shot_001_dir / "final.mp4").write_text("mock mp4 1")
    (shot_001_dir / "result.json").write_text(json.dumps({"status": "success"}))
    
    # 3. Sync shots again (should only need shot-002)
    needed = director.sync_shots(job_payload)
    print(f"Needed shots after mock 1: {needed}")
    assert needed == ["shot-002"]
    
    # 4. Mock rendering shot-002
    shot_002_dir = director.get_shot_output_dir("shot-002")
    shot_002_dir.mkdir(parents=True, exist_ok=True)
    # We'll use a real blank video for assembly to actually work if ffmpeg is called
    # For smoke, we'll just mock it and see if assembly fails as expected or we skip actual ffmpeg call
    (shot_002_dir / "final.mp4").write_text("mock mp4 2")
    (shot_002_dir / "result.json").write_text(json.dumps({"status": "success"}))
    
    needed = director.sync_shots(job_payload)
    print(f"Needed shots after mock 2: {needed}")
    assert len(needed) == 0
    
    # 5. Assemble (will likely fail because files aren't real videos, but we want to check the call)
    print("Attempting assembly...")
    success, err = director.assemble(job_payload)
    if not success:
        print(f"Assembly failed (expected if non-video files): {err}")
    else:
        print("Assembly succeeded!")

    print("DirectorService smoke passed (logic check only).")

if __name__ == "__main__":
    main()
