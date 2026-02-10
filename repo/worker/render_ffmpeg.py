import argparse
import hashlib
import json
import math
import pathlib
import subprocess


PADDING_PX = 24
OPACITY = 0.35
SCALE_FACTOR = 0.12
MIN_WM_WIDTH = 64
MAX_WM_WIDTH = 256


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


def run_ffmpeg(cmd, out_path: pathlib.Path) -> list[str]:
    # Write to a temp file then atomically replace.
    tmp_out = out_path.with_name(out_path.name + ".tmp" + out_path.suffix)
    if tmp_out.exists():
        tmp_out.unlink()
    # Find the output path argument and replace with tmp_out
    # The last argument in our constructed commands is typically the output path
    cmd_with_tmp = list(cmd)
    cmd_with_tmp[-1] = str(tmp_out)
    
    print("Running:", " ".join(cmd_with_tmp))
    subprocess.check_call(cmd_with_tmp)
    tmp_out.replace(out_path)
    return cmd_with_tmp


def get_video_dims(path: pathlib.Path) -> tuple[int, int]:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height",
        "-of",
        "csv=p=0",
        str(path),
    ]
    out = subprocess.check_output(cmd, text=True).strip()
    w, h = map(int, out.split(","))
    return w, h


def validate_safe_path(path: pathlib.Path, root: pathlib.Path) -> None:
    # Ensure path is within root
    # Py3.9+ has is_relative_to, but we can fallback for safety
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        raise ValueError(f"Path is strictly forbidden outside sandbox root: {path}")


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
    output_root = sandbox_root / "output"

    job_path, job = load_job(jobs_dir, args.job_path)

    job_id = job.get("job_id")
    if not job_id:
        raise SystemExit("Missing job_id in job.json")

    # background_asset is stored as a sandbox-relative path in the contract
    bg_rel = job["render"]["background_asset"]
    if pathlib.Path(bg_rel).is_absolute():
        raise SystemExit(f"Background asset path matches host absolute path (disallowed): {bg_rel}")
        
    bg = sandbox_root / bg_rel
    # Double check it didn't resolve outside sandbox
    try:
        validate_safe_path(bg, sandbox_root)
    except ValueError as e:
        raise SystemExit(str(e))
    
    if not bg.exists():
        raise SystemExit(f"Missing background asset: {bg}")

    # Validate watermark asset
    # Standardized path: repo/assets/watermarks/caf-watermark.png
    wm_path = root / "repo/assets/watermarks/caf-watermark.png"
    if not wm_path.exists():
        raise SystemExit(f"Missing watermark asset: {wm_path}")

    out_dir = output_root / job_id
    out_dir.mkdir(parents=True, exist_ok=True)

    out_mp4 = out_dir / "final.mp4"
    srt_path = out_dir / "final.srt"
    result_path = out_dir / "result.json"

    make_srt(job["captions"], srt_path)
    
    # Get video dimensions (height unused but returned for completeness/logging if needed)
    video_w, _ = get_video_dims(bg)
    
    # Calculate watermark dimensions
    raw_wm_width = math.floor(video_w * SCALE_FACTOR)
    wm_width = max(MIN_WM_WIDTH, min(raw_wm_width, MAX_WM_WIDTH))

    # Helper to build filter string
    def build_filter(include_subtitles: bool):
        f = []
        # 1. Prepare watermark: scale and opacity
        f.append(f"[1:v]format=rgba,colorchannelmixer=aa={OPACITY},scale={wm_width}:-1[wm]")
        
        current_bg_ref = "[0:v]"
        
        # 2. Apply subtitles (Optional)
        if include_subtitles and srt_path.exists():
            # Strict validation
            validate_safe_path(srt_path, sandbox_root)
            
            # Escape srt path for FFmpeg filter
            # 1. : is separator -> \:
            # 2. \ is escape -> \\
            # 3. ' is quote -> \'
            safe_srt_path = str(srt_path).replace("\\", "/").replace(":", "\\:")
            # We don't expect commas in safe paths, but good practice
            safe_srt_path = safe_srt_path.replace(",", "\\,")
            
            f.append(f"{current_bg_ref}subtitles=filename='{safe_srt_path}'[v_sub]")
            current_bg_ref = "[v_sub]"

        # 3. Apply watermark overlay
        f.append(f"{current_bg_ref}[wm]overlay=W-w-{PADDING_PX}:H-h-{PADDING_PX}[out]")
        return ";".join(f)

    # Strategy: Try with subtitles first (if they exist). If that fails (e.g. no libass), 
    # fallback to just watermark.
    
    subtitles_status = "skipped_no_file"
    final_cmd_logical = []
    final_cmd_executed = []
    failed_cmd = None
    
    # Attempt 1: With Subtitles (if available)
    if srt_path.exists():
        try:
            full_filter = build_filter(include_subtitles=True)
            cmd = [
                "ffmpeg", "-y",
                "-i", str(bg),
                "-i", str(wm_path),
                "-filter_complex", full_filter,
                "-map", "[out]",
                "-t", str(job["video"]["length_seconds"]),
                "-r", str(job["video"]["fps"]),
                "-c:v", "libx264",
                "-pix_fmt", "yuv420p",
                str(out_mp4),
            ]
            print("Attempting render with subtitles and watermark...")
            executed = run_ffmpeg(cmd, out_mp4)
            subtitles_status = "burned"
            final_cmd_logical = cmd
            final_cmd_executed = executed
        except (subprocess.CalledProcessError, ValueError) as e:
            print(f"Render with subtitles failed: {e}")
            if isinstance(e, ValueError):
                subtitles_status = "skipped_unsafe_path"
            else:
                subtitles_status = "failed_ffmpeg_subtitles"
                failed_cmd = cmd
            
            # Clean up potential partial output
            if out_mp4.exists():
                out_mp4.unlink()
    
    # Attempt 2: Watermark Only (if Attempt 1 failed or no subtitles)
    if not out_mp4.exists():
        full_filter = build_filter(include_subtitles=False)
        cmd = [
            "ffmpeg", "-y",
            "-i", str(bg),
            "-i", str(wm_path),
            "-filter_complex", full_filter,
            "-map", "[out]",
            "-t", str(job["video"]["length_seconds"]),
            "-r", str(job["video"]["fps"]),
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            str(out_mp4),
        ]
        print("Rendering with watermark only...")
        executed = run_ffmpeg(cmd, out_mp4)
        final_cmd_logical = cmd
        final_cmd_executed = executed

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
        "watermark": {
            "bg_path": str(bg),
            "wm_path": str(wm_path),
            "video_width": video_w,
            "wm_width": wm_width,
            "padding": PADDING_PX,
            "opacity": OPACITY,
        },
        "subtitles_status": subtitles_status,
        "ffmpeg_cmd": final_cmd_logical,
        "ffmpeg_cmd_executed": final_cmd_executed,
    }
    
    if failed_cmd:
        result["failed_ffmpeg_cmd"] = failed_cmd

    atomic_write_text(result_path, json.dumps(result, indent=2, sort_keys=True))

    print("Wrote", out_mp4)
    print("Wrote", srt_path)
    print("Wrote", result_path)


if __name__ == "__main__":
    main()
