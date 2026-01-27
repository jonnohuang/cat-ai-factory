import json, pathlib, subprocess

SANDBOX = pathlib.Path("/sandbox")
JOBS = SANDBOX / "jobs"
ASSETS = SANDBOX / "assets"
OUTPUT = SANDBOX / "output"

def make_srt(captions, out_path):
    # naive 3s per caption
    def ts(sec):
        h = sec // 3600
        m = (sec % 3600) // 60
        s = sec % 60
        return f"{h:02}:{m:02}:{s:02},000"
    lines = []
    t = 0
    for i, cap in enumerate(captions, start=1):
        start = ts(t)
        end = ts(t + 3)
        lines += [str(i), f"{start} --> {end}", cap, ""]
        t += 3
    out_path.write_text("\n".join(lines), encoding="utf-8")

def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)

    # pick the newest job json
    job_files = sorted(JOBS.glob("*.job.json"))
    if not job_files:
        raise SystemExit("No job files found in /sandbox/jobs")

    job_path = job_files[-1]
    job = json.loads(job_path.read_text(encoding="utf-8"))

    bg = SANDBOX / job["render"]["background_asset"]
    if not bg.exists():
        raise SystemExit(f"Missing background asset: {bg}")

    out_base = job["render"]["output_basename"]
    out_mp4 = OUTPUT / f"{out_base}.mp4"
    srt_path = OUTPUT / f"{out_base}.srt"

    make_srt(job["captions"], srt_path)

    # Render: scale/crop to 1080x1920 and burn subtitles
    cmd = [
        "ffmpeg", "-y",
        "-i", str(bg),
        "-vf", f"scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,subtitles={srt_path}",
        "-t", str(job["video"]["length_seconds"]),
        "-r", str(job["video"]["fps"]),
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        str(out_mp4)
    ]
    print("Running:", " ".join(cmd))
    subprocess.check_call(cmd)
    print("Wrote", out_mp4)

if __name__ == "__main__":
    main()
