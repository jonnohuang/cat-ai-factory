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


def load_template_registry(repo_root: pathlib.Path) -> dict:
    registry_path = repo_root / "repo/assets/templates/template_registry.json"
    if not registry_path.exists():
        raise SystemExit(f"Template registry not found at {registry_path}")
    
    try:
        data = json.loads(registry_path.read_text(encoding="utf-8"))
        if "version" not in data or "templates" not in data:
            raise SystemExit(f"Invalid template registry schema at {registry_path}: missing 'version' or 'templates'")
        if not isinstance(data["templates"], dict):
            raise SystemExit(f"Invalid template registry schema at {registry_path}: 'templates' must be a dictionary")
        return data
    except json.JSONDecodeError as e:
        raise SystemExit(f"Failed to parse template registry: {e}")


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


def normalize_sandbox_path(rel_path_str: str, sandbox_root: pathlib.Path) -> pathlib.Path:
    # Deterministic normalization:
    # If path starts with "sandbox/", strip it.
    # Then join with sandbox_root.
    # This supports both "assets/..." and "sandbox/assets/..." conventions
    # while ensuring they map to the same physical location under sandbox_root.
    
    p = pathlib.Path(rel_path_str)
    if p.is_absolute():
        raise ValueError(f"Asset path must be relative: {rel_path_str}")
    
    parts = p.parts
    if parts and parts[0] == "sandbox":
        p = pathlib.Path(*parts[1:])
        
    full_path = sandbox_root / p
    return full_path


def validate_safe_path(path: pathlib.Path, root: pathlib.Path) -> None:
    # Ensure path is within root
    # Py3.9+ has is_relative_to, but we can fallback for safety
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        raise ValueError(f"Path is strictly forbidden outside sandbox root: {path}")


def render_standard(job: dict, sandbox_root: pathlib.Path, out_dir: pathlib.Path, wm_path: pathlib.Path) -> dict:
    # Standard render logic refactored from main
    job_id = job["job_id"]
    
    # background_asset is stored as a sandbox-relative path in the contract
    bg_rel = job["render"]["background_asset"]
    
    try:
        bg = normalize_sandbox_path(bg_rel, sandbox_root)
        validate_safe_path(bg, sandbox_root)
    except ValueError as e:
        raise SystemExit(str(e))
    
    if not bg.exists():
        raise SystemExit(f"Missing background asset: {bg}")

    out_mp4 = out_dir / "final.mp4"
    srt_path = out_dir / "final.srt"
    
    # Create captions if present
    if "captions" in job and job["captions"]:
        make_srt(job["captions"], srt_path)
    else:
        # Create empty srt file to preserve invariant
        atomic_write_text(srt_path, "")

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
        # Only use subtitles if the file is non-empty/valid
        if include_subtitles and srt_path.exists() and srt_path.stat().st_size > 0:
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
    
    # Default status if we declare we aren't burning (e.g. empty file)
    # Default status logic
    if "captions" not in job or not job["captions"]:
        subtitles_status = "skipped_no_captions"
    elif srt_path.exists() and srt_path.stat().st_size == 0:
        subtitles_status = "skipped_empty"
    else:
        # If we have a file with content, we assume we might try to burn it.
        # If we fail, we'll update this.
        subtitles_status = "ready_to_burn"

    final_cmd_logical = []
    final_cmd_executed = []
    failed_cmd = None
    
    # Duration and FPS
    duration = str(job["video"]["length_seconds"])
    fps = str(job["video"]["fps"])

    # Attempt 1: With Subtitles (if available and non-empty)
    if srt_path.exists() and srt_path.stat().st_size > 0:
        try:
            full_filter = build_filter(include_subtitles=True)
            cmd = [
                "ffmpeg", "-y",
                "-i", str(bg),
                "-i", str(wm_path),
                "-filter_complex", full_filter,
                "-map", "[out]",
                "-t", duration,
                "-r", fps,
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
            "-t", duration,
            "-r", fps,
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            str(out_mp4),
        ]
        print("Rendering with watermark only...")
        executed = run_ffmpeg(cmd, out_mp4)
        final_cmd_logical = cmd
        final_cmd_executed = executed

    return {
        "job_id": job_id,
        "outputs": {
            "final_mp4": str(out_mp4),
            "final_srt": str(srt_path),
        },
        "hashes": {
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
        "failed_ffmpeg_cmd": failed_cmd
    }


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

    # Validate watermark asset
    # Standardized path: repo/assets/watermarks/caf-watermark.png
    wm_path = root / "repo/assets/watermarks/caf-watermark.png"
    if not wm_path.exists():
        raise SystemExit(f"Missing watermark asset: {wm_path}")

    out_dir = output_root / job_id
    out_dir.mkdir(parents=True, exist_ok=True)
    result_path = out_dir / "result.json"

    # -- Lane Routing --
    lane = job.get("lane", "")
    template_id = None
    recipe_id = None
    
    if lane == "template_remix":
        # PR18: Lane C Logic
        # 1. Require registry
        registry = load_template_registry(root)
        
        # 2. Require job.template and valid template_id
        if "template" not in job:
            raise SystemExit("Lane 'template_remix' requires 'template' field in job.json")
        
        template_id = job["template"]["template_id"]
        if template_id not in registry.get("templates", {}):
            raise SystemExit(f"Unknown template_id: {template_id}")
             
        template_config = registry["templates"][template_id]
        
        # 3. Validate required inputs
        for req_input in template_config.get("required_inputs", []):
            if req_input == "render.background_asset":
                if "background_asset" not in job.get("render", {}):
                    raise SystemExit(f"Template '{template_id}' requires 'render.background_asset' in job")
            else:
                # Strict enforcement: no aliases, no other inputs supported yet
                raise SystemExit(f"Template '{template_id}' requires unknown input '{req_input}'. Only 'render.background_asset' is supported.")


        # 4. Validate Params (Worker-side enforcement)
        params = job["template"].get("params", {})
        clip_start = params.get("clip_start_seconds")
        clip_end = params.get("clip_end_seconds")
        
        # Note: These params are validated here but not yet used in the standard_render recipe.
        # They are reserved for future recipe implementations.
        if clip_start is not None and clip_end is not None:
            if clip_end < clip_start:
                raise SystemExit(f"Invalid params: clip_end_seconds ({clip_end}) must be >= clip_start_seconds ({clip_start})")

        # 5. Dispatch recipe
        recipe_id = template_config.get("recipe_id")
        if recipe_id == "standard_render":
            # Use refactored standard logic
            render_result = render_standard(job, sandbox_root, out_dir, wm_path)
        else:
            raise SystemExit(f"Unsupported recipe_id: {recipe_id}")

    else:
        # Legacy / Default behavior (Lane A, Lane B, or no lane)
        # Use simple standard render directly
        render_result = render_standard(job, sandbox_root, out_dir, wm_path)

    # Final result assembly
    final_result = {
        "job_id": job_id,
        "lane": lane,
        "job_path": str(job_path),
        "sandbox_root": str(sandbox_root),
        "output_dir": str(out_dir),
        "outputs": render_result["outputs"],
        "hashes": {
            "job_json_sha256": sha256_file(pathlib.Path(job_path)),
            **render_result["hashes"]
        },
        "watermark": render_result["watermark"],
        "subtitles_status": render_result["subtitles_status"],
        "ffmpeg_cmd": render_result["ffmpeg_cmd"],
        "ffmpeg_cmd_executed": render_result["ffmpeg_cmd_executed"],
    }
    
    if lane == "template_remix":
        final_result["template_id"] = template_id
        final_result["recipe_id"] = recipe_id
    
    if render_result.get("failed_ffmpeg_cmd"):
        final_result["failed_ffmpeg_cmd"] = render_result["failed_ffmpeg_cmd"]

    atomic_write_text(result_path, json.dumps(final_result, indent=2, sort_keys=True))

    print("Wrote", render_result["outputs"]["final_mp4"])
    print("Wrote", render_result["outputs"]["final_srt"])
    print("Wrote", result_path)


if __name__ == "__main__":
    main()
