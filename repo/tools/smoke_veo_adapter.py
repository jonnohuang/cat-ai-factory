#!/usr/bin/env python3
"""
Smoke test for Local Veo3 Adapter (render_veo.py).
Requires: pip install google-cloud-aiplatform
"""
import json
import os
import pathlib
import subprocess
import sys

def _repo_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parents[2]

def main() -> int:
    root = _repo_root()
    sandbox = root / "sandbox"
    logs = sandbox / "logs" / "smoke_veo_adapter"
    logs.mkdir(parents=True, exist_ok=True)
    
    # Create dummy job
    job_path = logs / "veo_test.job.json"
    job_payload = {
        "job_id": "veo-test-job",
        "video": {
            "length_seconds": 5
        },
        "script": {
            "voiceover": "A cinematic shot of a cute grey tabby kitten in a green dinosaur costume, dancing joyfully in a studio setting, high quality, 4k."
        },
        "comfyui": {
            "bindings": {
                "prompt_text": "A cinematic shot of a cute grey tabby kitten in a green dinosaur costume, dancing joyfully in a studio setting, high quality, 4k.",
                "negative_prompt": "blurry, low quality, deformed"
            }
        }
    }
    job_path.write_text(json.dumps(job_payload, indent=2), encoding="utf-8")
    
    out_path = logs / "veo_test_output.mp4"
    if out_path.exists():
        out_path.unlink()
        
    print(f"Running render_veo.py with job: {job_path}")
    
    cmd = [
        sys.executable,
        "repo/worker/render_veo.py",
        "--job", str(job_path),
        "--out", str(out_path)
    ]
    
    # Check for authentication
    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
            cwd=str(root)
        )
        print(proc.stdout)
        
        if proc.returncode != 0:
            print("ERROR: render_veo.py failed", file=sys.stderr)
            if "DefaultCredentialsError" in proc.stdout:
                print("\n[!] Authentication Error: You need to run `gcloud auth application-default login`", file=sys.stderr)
            return proc.returncode
            
        if not out_path.exists() or out_path.stat().st_size == 0:
            print("ERROR: Output file missing or empty", file=sys.stderr)
            return 1
            
        print(f"SUCCESS: Video generated at {out_path} ({out_path.stat().st_size} bytes)")
        return 0
        
    except FileNotFoundError:
        print("ERROR: render_veo.py or dependencies missing", file=sys.stderr)
        return 1

if __name__ == "__main__":
    sys.exit(main())
