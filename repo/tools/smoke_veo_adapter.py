import json
import os
import pathlib
import subprocess
import sys


def main():
    repo_root = pathlib.Path(__file__).parents[2]
    worker_script = repo_root / "repo/worker/render_veo.py"
    if not worker_script.exists():
        print(f"ERROR: Worker script not found: {worker_script}")
        sys.exit(1)

    # Output paths
    job_file = repo_root / "job_veo_smoke.json"
    output_video = repo_root / "veo_smoke_output.mp4"
    seed_image = repo_root / "param_test_seed.png"

    # 1. create dummy seed image
    try:
        from PIL import Image, ImageDraw

        img = Image.new("RGB", (512, 512), color=(73, 109, 137))
        d = ImageDraw.Draw(img)
        d.text((10, 10), "Veo Smoke Test Seed", fill=(255, 255, 0))
        img.save(seed_image)
        print(f"Created dummy seed image: {seed_image}")
    except ImportError:
        print(
            "PIL not installed, skipping image creation. Adapter will rely on fallback behavior if mocked correctly."
        )
        pass

    # 2. create dummy job
    job_data = {
        "job_id": "smoke-test-veo-001",
        "prompt": "A cinematic shot of a cute grey tabby kitten in a green dinosaur costume, dancing joyfully in a studio setting, high quality, 4k. The dancing motion matches the rhythm of the provided seed frame context.",
        "image_motion": {"seed_frames": [str(seed_image)], "motion_preset": "pan_lr"},
    }

    with open(job_file, "w") as f:
        json.dump(job_data, f, indent=2)

    print(f"Created job file: {job_file}")

    # 3. run worker
    cmd = [
        sys.executable,
        str(worker_script),
        str(job_file),
        str(output_video),
        "--location",
        "us-central1",
        "--project",
        "gen-lang-client-0381423928",
    ]

    print(f"Running command: {' '.join(cmd)}")

    result = subprocess.run(cmd, capture_output=True, text=True)

    print("--- STDOUT ---")
    print(result.stdout)
    print("--- STDERR ---")
    print(result.stderr)

    # Check for specific "Loaded reference image" log to verify I2V logic was triggered
    if "Loaded reference image" in result.stdout:
        print("SUCCESS: I2V logic triggered (image loaded).")
    else:
        print("WARNING: I2V logic NOT triggered (image not loaded or skipped).")

    if result.returncode != 0:
        print(f"Worker failed with return code {result.returncode}")
        sys.exit(result.returncode)

    if output_video.exists() and output_video.stat().st_size > 0:
        print(
            f"Success! Output video created at {output_video} ({output_video.stat().st_size} bytes)"
        )
    else:
        print("Failure! Output video not found or empty.")
        sys.exit(1)


if __name__ == "__main__":
    main()
