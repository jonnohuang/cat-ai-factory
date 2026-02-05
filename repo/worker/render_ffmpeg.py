import argparse
import hashlib
import json
import pathlib
import subprocess


def repo_root_from_here() -> pathlib.Path:
    # repo/worker/render_ffmpeg.py -> <repo_root>
    return pathlib.Path(__file__).resolve().parents[2]


def sha256_file(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def atomic_write_text(path: pathlib.Path, content: str) -> None:
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(content, encoding="utf-8")
    tmp_path.replace(path)


def make_srt(captions, out_path: pathlib.Path) -> None:
    # naive 3s per caption
    def ts(sec: int) -> str:
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
    atomic_write_text(out_path, "\n".join(lines))


def load_job(jobs_dir: pathlib.Path, job_path: str | None = None):
    if job_path:
        job_file = pathlib.Path(job_path)
        if not job_file.exists():
            raise SystemExit(f"Job file not found: {job_file}")
        return job_file, json.loads(job_file.read_text(encoding="utf-8"))

    job_files = sorted(jobs_dir.glob("*.job.json"))
    if not job_files:
        raise SystemExit(f"No job files found in {jobs_dir}")
    job_file = job_files[-1]
    return job_file, json.loads(job_file.read_text(encoding="utf-8"))


def run_ffmpeg(cmd, out_path: pathlib.Path) -> None:
    # Write to a temp file then atomically replace.
    tmp_out = out_path.with_name(out_path.name + ".tmp" + out_path.suffix)
    if tmp_out.exists():
        tmp_out.unlink()
    cmd = cmd[:-1] + [str(tmp_out)]
    print("Running:", " ".join(cmd))
    subprocess.check_call(cmd)
    tmp_out.replace(out_path)


def main():
    parser = argparse.ArgumentParser(description="Deterministic FFmpeg renderer.")
    parser.add_argument("--job", dest="job_path", help="Path to a job.json file")
    parser.add_argument(
        "--sandbox-root",
        default=None,
        help="Path to sandbox root. Default: <repo_root>/sandbox (host). Use /sandbox in containers if mounted.",
    )
    args = parser.parse_args()

    root = repo_root_from_here()
    sandbox_root = pathlib.Path(args.sandbox_root) if args.sandbox_root else (root / "sandbox")

    jobs_dir = sandbox_root / "jobs"
    assets_dir = sandbox_root / "assets"
    output_root = sandbox_root / "output"

    job_path, job = load_job(jobs_dir, args.job_path)

    job_id = job.get("job_id")
    if not job_id:
        raise SystemExit("Missing job_id in job.json")

    # background_asset is stored as a sandbox-relative path in the contract
    bg_rel = job["render"]["background_asset"]
    bg = sandbox_root / bg_rel
    if not bg.exists():
        raise SystemExit(f"Missing background asset: {bg}")

    out_dir = output_root / job_id
    out_dir.mkdir(parents=True, exist_ok=True)

    out_mp4 = out_dir / "final.mp4"
    srt_path = out_dir / "final.srt"
    result_path = out_dir / "result.json"

    make_srt(job["captions"], srt_path)

    base_cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(bg),
        "-vf",
        "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920",
        "-t",
        str(job["video"]["length_seconds"]),
        "-r",
        str(job["video"]["fps"]),
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        str(out_mp4),
    ]

    subtitles_cmd = base_cmd.copy()
    # Replace the -vf argument with "...,subtitles=<srt_path>"
    subtitles_cmd[5] = f"{subtitles_cmd[5]},subtitles={srt_path}"

    subtitles_burned = True
    try:
        run_ffmpeg(subtitles_cmd, out_mp4)
    except subprocess.CalledProcessError:
        subtitles_burned = False
        if out_mp4.exists():
            out_mp4.unlink()
        run_ffmpeg(base_cmd, out_mp4)

    result = {
        "job_id": job_id,
        "job_path": str(job_path),
        "sandbox_root": str(sandbox_root),
        "output_dir": str(out_dir),
        "outputs": {
            "final_mp4": str(out_mp4),
            "final_srt": str(srt_path),
        },
        "hashes": {
            "job_json_sha256": sha256_file(pathlib.Path(job_path)),
            "final_mp4_sha256": sha256_file(out_mp4),
            "final_srt_sha256": sha256_file(srt_path),
        },
        "subtitles_burned": subtitles_burned,
        "ffmpeg_cmd": subtitles_cmd if subtitles_burned else base_cmd,
    }
    atomic_write_text(result_path, json.dumps(result, indent=2, sort_keys=True))

    print("Wrote", out_mp4)
    print("Wrote", srt_path)
    print("Wrote", result_path)


if __name__ == "__main__":
    main()
