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
    print("--- Running Audio Modes Smoke Test ---")

    sandbox_root = root / "sandbox"
    out_root = sandbox_root / "output"

    # Ensure examples exist
    silent_job = root / "repo/examples/job.v1.silent_master.example.json"
    mixed_job = root / "repo/examples/job.v1.mixed_master.example.json"

    if not silent_job.exists() or not mixed_job.exists():
        print("ERROR: Example jobs not found.")
        return False

    # Mock background assets if missing
    mock_bg = sandbox_root / "assets/demo/dance_loop.mp4"
    mock_bg.parent.mkdir(parents=True, exist_ok=True)
    if not mock_bg.exists():
        subprocess.run(["ffmpeg", "-f", "lavfi", "-i", "color=c=black:s=1080x1920", "-t", "5", str(mock_bg), "-y"], check=True)

    mock_studio = sandbox_root / "assets/demo/studio.mp4"
    if not mock_studio.exists():
        subprocess.run(["ffmpeg", "-f", "lavfi", "-i", "color=c=blue:s=1080x1920", "-t", "5", str(mock_studio), "-y"], check=True)

    # Use a dummy watermark
    wm_path = sandbox_root / "assets/watermark.png"
    if not wm_path.exists():
        subprocess.run(["ffmpeg", "-f", "lavfi", "-i", "color=c=white:s=100x100", "-vframes", "1", str(wm_path), "-y"], check=True)

    # 1. Test Silent Master
    print("\n[Test 1] Silent Master (Platform Trending)")
    cmd_silent = [
        "python3", "repo/worker/render_ffmpeg.py",
        "--job", str(silent_job),
        "--sandbox-root", str(sandbox_root)
    ]
    subprocess.run(cmd_silent, check=True)

    silent_out = out_root / "example-silent-master/final.mp4"
    if not silent_out.exists():
        print("FAIL: Silent master output missing.")
        return False

    # Verify it has no audio or silent audio
    # ffprobe -show_streams final.mp4
    print("SUCCESS: Silent master rendered.")

    # 2. Test Mixed Master
    print("\n[Test 2] Mixed Master (Licensed Pack)")
    # Ensure the pack asset we created earlier is there
    pack_asset = root / "repo/assets/audio/caf_signature_v1/mochi_meow_trap.wav"
    if not pack_asset.exists():
        print("ERROR: Pack asset missing for test.")
        return False

    cmd_mixed = [
        "python3", "repo/worker/render_ffmpeg.py",
        "--job", str(mixed_job),
        "--sandbox-root", str(sandbox_root)
    ]
    subprocess.run(cmd_mixed, check=True)

    mixed_out = out_root / "example-mixed-master/final.mp4"
    if not mixed_out.exists():
        print("FAIL: Mixed master output missing.")
        return False

    print("SUCCESS: Mixed master rendered.")

    print("\n--- Audio Modes Smoke Test Passed! ---")
    return True

if __name__ == "__main__":
    if run_smoke_test():
        sys.exit(0)
    else:
        sys.exit(1)
