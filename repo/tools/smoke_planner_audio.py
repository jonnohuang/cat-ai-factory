#!/usr/bin/env python3
import json
import os
import pathlib
import shutil
import subprocess
import sys

# Add repo to path
root = pathlib.Path(__file__).parent.parent.parent
sys.path.append(str(root))

def run_smoke_test():
    print("--- Running Planner Audio Intelligence Smoke Test ---")

    # 0. Clean old output
    out_dir = root / "sandbox/output/smoke-planner-audio"
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. Mock PRD with explicit audio intent
    inbox_dir = root / "sandbox/inbox/smoke-planner-audio"
    inbox_dir.mkdir(parents=True, exist_ok=True)

    prd_path = inbox_dir / "prd.json"
    prd = {
        "project_id": "smoke-planner-audio",
        "brief": "A high-energy cat dance video with trending tiktok audio vibes.",
        "intent": "trending, energetic, cat dance",
        "constraints": {
            "length_seconds": 12,
            "fps": 30
        }
    }
    with open(prd_path, "w") as f:
        json.dump(prd, f, indent=2)

    # 2. Run Planner CLI
    # Use CAF_VEO_MOCK=1 to avoid real LLM/VEO calls
    env = os.environ.copy()
    env["CAF_VEO_MOCK"] = "1"
    env["VERTEX_PROJECT_ID"] = "mock-project"
    env["VERTEX_ACCESS_TOKEN"] = "mock-token"

    cmd = [
        "python3", "-m", "repo.services.planner.planner_cli",
        "--prd", str(prd_path),
        "--inbox", str(inbox_dir),
        "--out", "sandbox/output/smoke-planner-audio",
        "--provider", "vertex_veo"
    ]

    print(f"Running Planner CLI: {' '.join(cmd)}")
    result = subprocess.run(cmd, env=env, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"FAIL: Planner CLI failed with exit code {result.returncode}")
        print(result.stderr)
        return False

    print("Planner CLI finished successfully.")
    print(result.stdout)

    # 3. Verify job.json
    out_dir = root / "sandbox/output/smoke-planner-audio"
    job_paths = list(out_dir.glob("*.job.json"))
    if not job_paths:
        print("FAIL: No job.json produced.")
        return False

    job_path = job_paths[0]
    with open(job_path, "r") as f:
        job = json.load(f)

    audio = job.get("audio", {})
    mode = audio.get("mode")
    beat_grid = audio.get("beat_alignment")

    print(f"Detected mode: {mode}")

    if mode != "platform_trending":
        print(f"FAIL: Expected 'platform_trending' mode based on 'trending' intent, got '{mode}'")
        return False

    if not beat_grid:
        print("FAIL: No beat_alignment grid found in job.json")
        return False

    print("SUCCESS: Audio strategy and beat grid verified in job.json.")

    # 4. Test 2: Licensed Pack intent
    print("\n[Test 2] Licensed Pack Intent")
    prd["brief"] = "A chill lofi cat nap video."
    prd["intent"] = "chill, lofi, brand-safe"
    with open(prd_path, "w") as f:
        json.dump(prd, f, indent=2)

    subprocess.run(cmd, env=env, capture_output=True, text=True, check=True)

    # Check updated job.json (or find latest)
    job_paths = sorted(out_dir.glob("*.job.json"), key=os.path.getmtime)
    job_path = job_paths[-1]
    with open(job_path, "r") as f:
        job = json.load(f)

    audio = job.get("audio", {})
    mode = audio.get("mode")

    print(f"Detected mode: {mode}")
    if mode != "licensed_pack":
        print(f"FAIL: Expected 'licensed_pack' mode for lofi intent, got '{mode}'")
        return False

    # Verify shot alignment
    shots = job.get("shots", [])
    if shots:
        print(f"Shot 1 time: {shots[0].get('t')}")
        # In our GridResolver, shots are snapped to cuts. Cut 1 is at 0.0.
        if shots[0].get("t") != 0.0:
            print(f"FAIL: Shot 1 not snapped to grid (t={shots[0].get('t')})")
            return False

    print("SUCCESS: Licensed pack selection and shot snapping verified.")

    print("\n--- Planner Audio Intelligence Smoke Test Passed! ---")
    return True

if __name__ == "__main__":
    if run_smoke_test():
        sys.exit(0)
    else:
        sys.exit(1)
