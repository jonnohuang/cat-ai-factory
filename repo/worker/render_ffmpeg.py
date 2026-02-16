import argparse
import hashlib
import json
import math
import os
import pathlib
import statistics
import subprocess


PADDING_PX = 24
OPACITY = 0.35
SCALE_FACTOR = 0.12
MIN_WM_WIDTH = 64
MAX_WM_WIDTH = 256
_HAS_SUBTITLES_FILTER: bool | None = None


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


def get_video_duration(path: pathlib.Path) -> float:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=duration",
        "-of",
        "csv=p=0",
        str(path),
    ]
    out = subprocess.check_output(cmd, text=True).strip()
    try:
        return float(out)
    except Exception:
        return 0.0


def build_loop_ready_bg(
    bg_path: pathlib.Path, out_dir: pathlib.Path, target_seconds: int, fps: int
) -> pathlib.Path:
    out_path = out_dir / "bg_loop.mp4"
    first = target_seconds // 2
    if first < 2:
        first = 4
    second = target_seconds - first
    if second < 2:
        second = first
        target_seconds = first + second
    fade_dur = min(0.5, max(0.2, first * 0.08))
    fade_offset = max(0.0, first - fade_dur)

    filter_complex = (
        f"[0:v]trim=0:{first},setpts=PTS-STARTPTS[v1];"
        f"[0:v]trim={first}:{first + second},setpts=PTS-STARTPTS[v2];"
        f"[v1][v2]xfade=transition=fade:duration={fade_dur:.3f}:offset={fade_offset:.3f}[v]"
    )
    cmd = [
        "ffmpeg",
        "-y",
        "-stream_loop",
        "-1",
        "-i",
        str(bg_path),
        "-filter_complex",
        filter_complex,
        "-map",
        "[v]",
        "-t",
        str(target_seconds),
        "-r",
        str(fps),
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        "-map_metadata",
        "-1",
        "-map_chapters",
        "-1",
        str(out_path),
    ]
    run_ffmpeg(cmd, out_path)
    return out_path


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


def load_json_file(path: pathlib.Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as ex:
        raise SystemExit(f"Invalid JSON artifact: {path} ({ex})")


def _with_temp_env(overrides: dict[str, str], fn):
    original: dict[str, str | None] = {k: os.environ.get(k) for k in overrides}
    try:
        for key, value in overrides.items():
            os.environ[key] = value
        return fn()
    finally:
        for key, old in original.items():
            if old is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old


def resolve_dance_swap_contracts(job: dict, sandbox_root: pathlib.Path) -> dict:
    dance_swap = job.get("dance_swap")
    if not isinstance(dance_swap, dict):
        raise SystemExit("Lane 'dance_swap' requires 'dance_swap' object in job.json")

    required_fields = ["loop_artifact", "tracks_artifact", "foreground_asset"]
    missing = [k for k in required_fields if not isinstance(dance_swap.get(k), str) or not dance_swap.get(k, "").strip()]
    if missing:
        raise SystemExit(f"dance_swap missing required string field(s): {', '.join(missing)}")

    loop_path = normalize_sandbox_path(dance_swap["loop_artifact"], sandbox_root)
    tracks_path = normalize_sandbox_path(dance_swap["tracks_artifact"], sandbox_root)
    fg_path = normalize_sandbox_path(dance_swap["foreground_asset"], sandbox_root)
    validate_safe_path(loop_path, sandbox_root)
    validate_safe_path(tracks_path, sandbox_root)
    validate_safe_path(fg_path, sandbox_root)

    beatflow_path = None
    if dance_swap.get("beatflow_artifact"):
        beatflow_path = normalize_sandbox_path(dance_swap["beatflow_artifact"], sandbox_root)
        validate_safe_path(beatflow_path, sandbox_root)

    for p in [loop_path, tracks_path, fg_path, beatflow_path]:
        if p and not p.exists():
            raise SystemExit(f"Dance Swap artifact not found: {p}")

    loop = load_json_file(loop_path)
    tracks = load_json_file(tracks_path)
    beatflow = load_json_file(beatflow_path) if beatflow_path else None

    if loop.get("version") != "dance_swap_loop.v1":
        raise SystemExit("dance_swap.loop_artifact must be a dance_swap_loop.v1 artifact")
    if tracks.get("version") != "dance_swap_tracks.v1":
        raise SystemExit("dance_swap.tracks_artifact must be a dance_swap_tracks.v1 artifact")
    if beatflow is not None and beatflow.get("version") != "dance_swap_beatflow.v1":
        raise SystemExit("dance_swap.beatflow_artifact must be a dance_swap_beatflow.v1 artifact")

    source_rel = loop.get("source_video_relpath")
    if not isinstance(source_rel, str) or not source_rel.startswith("sandbox/"):
        raise SystemExit("dance_swap.loop.source_video_relpath must be a sandbox-relative path")
    if tracks.get("source_video_relpath") != source_rel:
        raise SystemExit("Dance Swap source mismatch: loop and tracks source_video_relpath differ")
    if beatflow is not None and beatflow.get("source_video_relpath") != source_rel:
        raise SystemExit("Dance Swap source mismatch: beatflow source_video_relpath differs")

    source_video = normalize_sandbox_path(source_rel, sandbox_root)
    validate_safe_path(source_video, sandbox_root)
    if not source_video.exists():
        raise SystemExit(f"Dance Swap source video not found: {source_video}")

    render_bg = normalize_sandbox_path(job["render"]["background_asset"], sandbox_root)
    validate_safe_path(render_bg, sandbox_root)
    if render_bg.resolve() != source_video.resolve():
        raise SystemExit(
            "dance_swap source mismatch: render.background_asset must match loop.source_video_relpath"
        )

    loop_start = int(loop["loop_start_frame"])
    loop_end = int(loop["loop_end_frame"])
    if loop_end <= loop_start:
        raise SystemExit("Dance Swap loop_end_frame must be > loop_start_frame")

    subjects = tracks.get("subjects")
    if not isinstance(subjects, list) or not subjects:
        raise SystemExit("dance_swap.tracks.subjects must contain at least one subject")
    subject_id = dance_swap.get("subject_id") or subjects[0].get("subject_id")
    subject = None
    for s in subjects:
        if isinstance(s, dict) and s.get("subject_id") == subject_id:
            subject = s
            break
    if subject is None:
        raise SystemExit(f"Dance Swap subject_id not found in tracks: {subject_id}")

    subject_frames = []
    for row in subject.get("frames", []):
        frame = int(row["frame"])
        if loop_start <= frame <= loop_end:
            mask_rel = row.get("mask_relpath")
            if not isinstance(mask_rel, str) or not mask_rel.startswith("sandbox/"):
                raise SystemExit(f"Dance Swap frame has invalid mask_relpath: frame={frame}")
            mask_path = normalize_sandbox_path(mask_rel, sandbox_root)
            validate_safe_path(mask_path, sandbox_root)
            if not mask_path.exists():
                raise SystemExit(f"Dance Swap mask file missing: {mask_path}")
            bbox = row.get("bbox") or {}
            subject_frames.append(
                {
                    "frame": frame,
                    "x": int(bbox["x"]),
                    "y": int(bbox["y"]),
                    "w": int(bbox["w"]),
                    "h": int(bbox["h"]),
                    "mask_relpath": mask_rel,
                }
            )

    if not subject_frames:
        raise SystemExit(
            f"Dance Swap subject '{subject_id}' has no frame rows within loop bounds [{loop_start}, {loop_end}]"
        )

    xs = [x["x"] for x in subject_frames]
    ys = [x["y"] for x in subject_frames]
    ws = [x["w"] for x in subject_frames]
    hs = [x["h"] for x in subject_frames]

    slot_x = int(statistics.median(xs))
    slot_y = int(statistics.median(ys))
    slot_w = max(1, int(statistics.median(ws)))
    slot_h = max(1, int(statistics.median(hs)))
    slot_dx = max(0.0, (max(xs) - min(xs)) / 2.0)
    slot_dy = max(0.0, (max(ys) - min(ys)) / 2.0)

    fps = float(loop.get("fps", 30.0))
    slot_hz = 1.6
    if beatflow and beatflow.get("beats"):
        beats = sorted(int(b["frame"]) for b in beatflow["beats"])
        if len(beats) >= 2:
            gaps = [b - a for a, b in zip(beats, beats[1:]) if (b - a) > 0]
            if gaps:
                avg_gap = sum(gaps) / len(gaps)
                if avg_gap > 0:
                    slot_hz = max(0.2, min(4.0, fps / avg_gap))

    return {
        "source_video_relpath": source_rel,
        "foreground_asset_relpath": dance_swap["foreground_asset"],
        "subject_id": subject_id,
        "hero_id": subject.get("hero_id"),
        "loop_start_frame": loop_start,
        "loop_end_frame": loop_end,
        "blend_strategy": loop.get("blend_strategy"),
        "frame_rows_in_loop": len(subject_frames),
        "slot": {
            "x": slot_x,
            "y": slot_y,
            "w": slot_w,
            "h": slot_h,
            "dx": round(slot_dx, 3),
            "dy": round(slot_dy, 3),
            "hz": round(slot_hz, 6),
        },
    }




def has_audio_stream(path: pathlib.Path) -> bool:
    try:
        cmd = [
            "ffprobe",
            "-v", "error",
            "-select_streams", "a:0",
            "-show_entries", "stream=codec_type",
            "-of", "csv=p=0",
            str(path)
        ]
        out = subprocess.check_output(cmd, text=True).strip()
        return bool(out)
    except subprocess.CalledProcessError:
        # Fallback for corrupt files or other probe errors
        return False


def resolve_audio_asset(job: dict, sandbox_root: pathlib.Path) -> pathlib.Path | None:
    if "audio" not in job or "audio_asset" not in job["audio"]:
        return None
    
    clean_path = job["audio"]["audio_asset"]
    if not clean_path:
        return None
        
    try:
        p = normalize_sandbox_path(clean_path, sandbox_root)
        
        # Security check: fail loud if unsafe path
        validate_safe_path(p, sandbox_root)
        
        # Existence check: fail soft (warn and fallback)
        if not p.exists():
            print(f"WARNING: Audio asset missing, falling back to silence/bg: {p}")
            return None
            
        # Extension check: fail soft
        # PR20: Allow video containers (mp4, mov, etc) to be used as audio sources
        valid_exts = [".mp3", ".wav", ".m4a", ".aac", ".mp4", ".mov", ".mkv", ".webm"]
        if p.suffix.lower() not in valid_exts:
             print(f"WARNING: Unsupported audio format, falling back: {p.suffix}")
             return None
            
        print(f"Found audio asset: {p}")
        return p
    except ValueError as e:
        # Malformed/unsafe path: fail loud
        raise SystemExit(f"Invalid audio asset path: {e}")


def escape_ffmpeg_path(path: pathlib.Path) -> str:
    # Escape path for FFmpeg filter argument
    # 1. : is separator -> \:
    # 2. \ is escape -> \\
    # 3. ' is quote -> \'
    safe_path = str(path).replace("\\", "/").replace(":", "\\:")
    # We don't expect commas in safe paths, but good practice
    safe_path = safe_path.replace(",", "\\,")
    safe_path = safe_path.replace("'", "\\'")
    return safe_path


def ffmpeg_has_subtitles_filter() -> bool:
    global _HAS_SUBTITLES_FILTER
    if _HAS_SUBTITLES_FILTER is not None:
        return _HAS_SUBTITLES_FILTER
    try:
        out = subprocess.check_output(
            ["ffmpeg", "-hide_banner", "-filters"],
            text=True,
            stderr=subprocess.STDOUT,
        )
        _HAS_SUBTITLES_FILTER = " subtitles " in f" {out} "
    except Exception:
        _HAS_SUBTITLES_FILTER = False
    return _HAS_SUBTITLES_FILTER


def render_image_motion(job: dict, sandbox_root: pathlib.Path, out_dir: pathlib.Path, wm_path: pathlib.Path) -> dict:
    job_id = job["job_id"]
    
    # 1. Validate Lane B inputs
    if "image_motion" not in job:
        raise SystemExit("Lane 'image_motion' requires 'image_motion' field in job.json")
    
    im_config = job["image_motion"]
    seed_frames = im_config.get("seed_frames", [])
    preset = im_config.get("motion_preset")
    
    if not seed_frames or not isinstance(seed_frames, list):
        raise SystemExit("image_motion.seed_frames must be a non-empty list")
    
    if len(seed_frames) > 3:
        raise SystemExit("image_motion.seed_frames max 3 frames supported")
        
    if not preset:
        raise SystemExit("image_motion.motion_preset is required")

    # 2. Resolve safe paths
    safe_seeds = []
    for sf in seed_frames:
        try:
            p = normalize_sandbox_path(sf, sandbox_root)
            validate_safe_path(p, sandbox_root)
            if not p.exists():
                raise SystemExit(f"Missing seed frame: {sf}")
            if p.suffix.lower() not in [".png", ".jpg", ".jpeg", ".webp"]:
                raise SystemExit(f"Unsupported image format: {sf}")
            safe_seeds.append(p)
        except ValueError as e:
            raise SystemExit(str(e))

    # 3. Determine Duration and FPS
    # job.video.length_seconds is authoritative
    duration = job["video"]["length_seconds"]
    fps = job["video"].get("fps", 30)
    total_frames = int(duration * fps)

    # 4. Filter Graph Construction
    inputs: list[str] = []
    filter_chain: list[str] = []
    
    next_input_idx = 0  # Unified input counter
    
    # Constants
    VIDEO_W = 1080
    VIDEO_H = 1920
    
    # Base scale/crop filter
    scale_crop = f"scale={VIDEO_W}:{VIDEO_H}:force_original_aspect_ratio=increase,crop={VIDEO_W}:{VIDEO_H}"
    
    # Preset Expressions
    PRESETS = {
        "kb_zoom_in": f"zoompan=z='min(zoom+0.0015,1.5)':d={{d}}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={VIDEO_W}x{VIDEO_H}",
        "kb_zoom_out": f"zoompan=z='if(eq(on,1),1.5,max(1.0,zoom-0.0015))':d={{d}}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={VIDEO_W}x{VIDEO_H}",
        "pan_lr": f"zoompan=z=1.2:d={{d}}:x='on*(iw-iw/zoom)/{{d}}':y='ih/2-(ih/zoom/2)':s={VIDEO_W}x{VIDEO_H}",
        "pan_ud": f"zoompan=z=1.2:d={{d}}:x='iw/2-(iw/zoom/2)':y='on*(ih-ih/zoom)/{{d}}':s={VIDEO_W}x{VIDEO_H}",
        "shake_soft": f"zoompan=z=1.1:d={{d}}:x='iw/2-(iw/zoom/2)+20*sin(on/20)':y='ih/2-(ih/zoom/2)+20*cos(on/20)':s={VIDEO_W}x{VIDEO_H}",
        "static": f"zoompan=z=1.0:d={{d}}:x=0:y=0:s={VIDEO_W}x{VIDEO_H}" 
    }

    # -- Video Inputs (Images) First --
    # Add image inputs before audio to ensure stable video indexing
    
    if preset == "cut_3frame" and len(safe_seeds) > 1:
        # Multi-frame (2 or 3)
        count = len(safe_seeds)
        seg_frames_base = total_frames // count
        remainder = total_frames % count
        
        concat_inputs = []
        
        for i, p in enumerate(safe_seeds):
            current_seg_frames = seg_frames_base + (1 if i < remainder else 0)
            current_seg_duration = current_seg_frames / fps
            
            # Use next_input_idx for image input
            input_idx = next_input_idx
            inputs.extend(["-loop", "1", "-t", f"{current_seg_duration:.3f}", "-i", str(p)])
            next_input_idx += 1
            
            zp_expr = PRESETS["kb_zoom_in"].format(d=current_seg_frames)
            
            filter_chain.append(f"[{input_idx}:v]{scale_crop},setsar=1[v{i}_base]")
            filter_chain.append(f"[v{i}_base]{zp_expr}[v{i}_zoom]")
            concat_inputs.append(f"[v{i}_zoom]")
            
        concat_str = "".join(concat_inputs)
        filter_chain.append(f"{concat_str}concat=n={count}:v=1:a=0[bg]")
        
    else:
        # Single frame or fallback
        if preset == "cut_3frame":
             preset = "kb_zoom_in"
             
        if preset not in PRESETS:
            raise SystemExit(f"Unknown or unsupported preset: {preset}")
            
        if not safe_seeds:
             raise SystemExit("No seed frames available")
             
        p_path = safe_seeds[0]
        input_idx = next_input_idx
        inputs.extend(["-loop", "1", "-i", str(p_path)])
        next_input_idx += 1
        
        zp_expr = PRESETS[preset].format(d=total_frames)
        filter_chain.append(f"[{input_idx}:v]{scale_crop},setsar=1[base]")
        filter_chain.append(f"[base]{zp_expr}[bg]")

    # -- Audio Inputs --
    # Prio: Job Asset > Silence (Images have no BG audio)
    audio_asset = resolve_audio_asset(job, sandbox_root)
    has_bg_audio = False # Images don't have audio stream
    audio_source = "silence"
    audio_input_idx = -1
    
    if audio_asset:
        audio_source = "job_asset"
        # -stream_loop -1 allows audio to loop if shorter than video duration
        inputs.extend(["-stream_loop", "-1", "-i", str(audio_asset)])
        audio_input_idx = next_input_idx
        next_input_idx += 1
    else:
        audio_source = "silence"
        # Inject deterministic silence
        inputs.extend([
            "-f", "lavfi", 
            "-t", str(duration), 
            "-i", "anullsrc=channel_layout=stereo:sample_rate=48000"
        ])
        audio_input_idx = next_input_idx
        next_input_idx += 1

    # -- Watermark Input --
    wm_width = max(MIN_WM_WIDTH, min(math.floor(VIDEO_W * SCALE_FACTOR), MAX_WM_WIDTH))

    wm_input_idx = next_input_idx
    inputs.extend(["-i", str(wm_path)])
    next_input_idx += 1
    
    filter_chain.append(f"[{wm_input_idx}:v]format=rgba,colorchannelmixer=aa={OPACITY},scale={wm_width}:-1[wm]")
    
    # Now we have [bg] at 1080x1920
    out_mp4 = out_dir / "final.mp4"
    srt_path = out_dir / "final.srt"
    
    if "captions" in job and job["captions"]:
        make_srt(job["captions"], srt_path)
    else:
        atomic_write_text(srt_path, "")
    
    current_bg_ref = "[bg]"
    
    subtitles_status = "ready_to_burn"
    if "captions" not in job or not job["captions"]:
        subtitles_status = "skipped_no_captions"
    elif srt_path.exists() and srt_path.stat().st_size == 0:
        subtitles_status = "skipped_empty"
    
    if subtitles_status == "ready_to_burn":
        try:
            validate_safe_path(srt_path, sandbox_root)
        except ValueError:
            subtitles_status = "skipped_unsafe_path"

    attempt_burn = (subtitles_status == "ready_to_burn")
    if attempt_burn and not ffmpeg_has_subtitles_filter():
        subtitles_status = "skipped_missing_subtitles_filter"
        attempt_burn = False
    
    def build_final_chain(burning: bool):
        c = list(filter_chain)
        ref = current_bg_ref
        if burning:
             safe_srt = escape_ffmpeg_path(srt_path)
             c.append(f"{ref}subtitles=filename='{safe_srt}'[v_sub]")
             ref = "[v_sub]"
        
        c.append(f"{ref}[wm]overlay=W-w-{PADDING_PX}:H-h-{PADDING_PX}[out]")
        return ";".join(c)

    executed_cmd = []
    failed_cmd = None
    
    # Audio filters:
    # 1) guarantee duration (pad/trim),
    # 2) basic loudness normalization,
    # 3) limiter to prevent clipping peaks.
    audio_filter = (
        f"apad=pad_dur={duration},"
        f"atrim=0:{duration},"
        "loudnorm=I=-16:TP=-1.5:LRA=11,"
        "alimiter=limit=0.95"
    )

    output_args = [
        "-map", "[out]",
        "-map", f"{audio_input_idx}:a:0",
        "-t", str(duration),
        "-r", str(fps),
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "192k",
        "-ar", "48000",
        "-ac", "2",
        "-af", audio_filter,
        "-movflags", "+faststart",
        "-map_metadata", "-1",
        "-map_chapters", "-1",
        str(out_mp4)
    ]
    
    if attempt_burn:
        try:
            full_filter = build_final_chain(True)
            cmd = ["ffmpeg", "-y"] + inputs + ["-filter_complex", full_filter] + output_args
            print(f"Rendering Image Motion ({preset}) with subtitles...")
            executed_cmd = run_ffmpeg(cmd, out_mp4)
            subtitles_status = "burned"
        except subprocess.CalledProcessError:
            print("Subtitle burn failed, falling back to clean render")
            subtitles_status = "failed_ffmpeg_subtitles"
            failed_cmd = cmd
            attempt_burn = False
            
    if not attempt_burn:
        full_filter = build_final_chain(False)
        cmd = ["ffmpeg", "-y"] + inputs + ["-filter_complex", full_filter] + output_args
        print(f"Rendering Image Motion ({preset}) clean...")
        executed_cmd = run_ffmpeg(cmd, out_mp4)
        
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
            "bg_path": "n/a (image_motion)",
            "wm_path": str(wm_path),
            "video_width": VIDEO_W,
            "wm_width": wm_width,
            "padding": PADDING_PX,
            "opacity": OPACITY,
        },
        "audio_source": audio_source,
        "audio_asset_path": str(audio_asset) if audio_asset else None,
        "has_bg_audio": has_bg_audio,
        "motion_preset": preset,
        "seed_frames_count": len(safe_seeds),
        "subtitles_status": subtitles_status,
        "ffmpeg_cmd": cmd,
        "ffmpeg_cmd_executed": executed_cmd,
        "failed_ffmpeg_cmd": failed_cmd
    }


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

    # Duration and FPS
    lane = str(job.get("lane", ""))
    job_duration = int(job["video"]["length_seconds"])
    fps_i = int(job["video"]["fps"])
    duration_i = job_duration

    # Quality-first lane-A mode:
    # by default, align output duration to generated source video duration to avoid
    # long padded outputs that feel unsynced.
    if lane == "ai_video":
        match_source = os.environ.get("CAF_AI_VIDEO_MATCH_SOURCE_DURATION", "0").strip().lower()
        if match_source in ("1", "true", "yes"):
            src_dur = get_video_duration(bg)
            if src_dur > 0.0:
                duration_i = max(4, int(round(src_dur)))

        # Optional loop builder for cleaner longer outputs.
        build_loop = os.environ.get("CAF_AI_VIDEO_BUILD_LOOP", "").strip().lower()
        if build_loop in ("1", "true", "yes"):
            loop_target = int(os.environ.get("CAF_AI_VIDEO_LOOP_DURATION", "16"))
            loop_target = max(8, min(60, loop_target))
            bg = build_loop_ready_bg(bg, out_dir, loop_target, fps_i)
            duration_i = loop_target
            video_w, _ = get_video_dims(bg)

    duration = str(duration_i)
    fps = str(fps_i)

    # Inputs Construction
    inputs = []
    next_input_idx = 0
    
    # Input 0: Background
    # Add input first, then increment counter and use it
    current_bg_idx = next_input_idx
    inputs.extend(["-i", str(bg)])
    next_input_idx += 1
    
    # -- Audio Logic (Standard) --
    # Prio: Job Asset > BG Audio > Silence
    audio_asset = resolve_audio_asset(job, sandbox_root)
    has_bg_audio = has_audio_stream(bg)
    audio_source = "silence"
    audio_input_idx = -1
    
    if audio_asset:
        audio_source = "job_asset"
        inputs.extend(["-stream_loop", "-1", "-i", str(audio_asset)])
        audio_input_idx = next_input_idx
        next_input_idx += 1
    elif has_bg_audio:
        audio_source = "bg_audio"
        audio_input_idx = current_bg_idx # Use BG input
    else:
        audio_source = "silence"
        inputs.extend([
            "-f", "lavfi", 
            "-t", duration, 
            "-i", "anullsrc=channel_layout=stereo:sample_rate=48000"
        ])
        audio_input_idx = next_input_idx
        next_input_idx += 1

    # Watermark Input
    wm_input_idx = next_input_idx
    inputs.extend(["-i", str(wm_path)])
    next_input_idx += 1

    # Helper to build filter string
    def build_filter(include_subtitles: bool):
        f = []
        # 1. Prepare watermark: scale and opacity
        f.append(f"[{wm_input_idx}:v]format=rgba,colorchannelmixer=aa={OPACITY},scale={wm_width}:-1[wm]")
        
        current_bg_ref = f"[{current_bg_idx}:v]"
        
        # 2. Apply subtitles (Optional)
        # Only use subtitles if the file is non-empty/valid
        if include_subtitles and srt_path.exists() and srt_path.stat().st_size > 0:
            # Strict validation
            validate_safe_path(srt_path, sandbox_root)
            
            safe_srt_path = escape_ffmpeg_path(srt_path)
            
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
    
    # Audio filters:
    # 1) guarantee duration (pad/trim),
    # 2) basic loudness normalization,
    # 3) limiter to prevent clipping peaks.
    audio_filter = (
        f"apad=pad_dur={duration},"
        f"atrim=0:{duration},"
        "loudnorm=I=-16:TP=-1.5:LRA=11,"
        "alimiter=limit=0.95"
    )
    
    output_args = [
        "-map", "[out]",
        "-map", f"{audio_input_idx}:a:0",
        "-t", duration,
        "-r", fps,
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "192k",
        "-ar", "48000",
        "-ac", "2",
        "-af", audio_filter,
        "-movflags", "+faststart",
        "-map_metadata", "-1",
        "-map_chapters", "-1",
        str(out_mp4),
    ]

    # Attempt 1: With Subtitles (if available and non-empty and ffmpeg supports subtitles filter)
    if srt_path.exists() and srt_path.stat().st_size > 0 and ffmpeg_has_subtitles_filter():
        try:
            full_filter = build_filter(include_subtitles=True)
            cmd = ["ffmpeg", "-y"] + inputs + ["-filter_complex", full_filter] + output_args
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
        cmd = ["ffmpeg", "-y"] + inputs + ["-filter_complex", full_filter] + output_args
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
        "audio_source": audio_source,
        "audio_asset_path": str(audio_asset) if audio_asset else None,
        "has_bg_audio": has_bg_audio,
        "subtitles_status": subtitles_status,
        "ffmpeg_cmd": final_cmd_logical,
        "ffmpeg_cmd_executed": final_cmd_executed,
        "failed_ffmpeg_cmd": failed_cmd
    }
def render_duet_overlay_mochi(job: dict, sandbox_root: pathlib.Path, out_dir: pathlib.Path, wm_path: pathlib.Path) -> dict:
    job_id = job["job_id"]
    fg_rel = job["render"]["background_asset"]
    bg_rel = "assets/demo/dance_loop.mp4"

    try:
        fg = normalize_sandbox_path(fg_rel, sandbox_root)
        bg = normalize_sandbox_path(bg_rel, sandbox_root)
        validate_safe_path(fg, sandbox_root)
        validate_safe_path(bg, sandbox_root)
    except ValueError as e:
        raise SystemExit(str(e))

    if not fg.exists():
        raise SystemExit(f"Missing foreground duet asset: {fg}")
    if not bg.exists():
        raise SystemExit(f"Missing base duet asset: {bg}")

    out_mp4 = out_dir / "final.mp4"
    srt_path = out_dir / "final.srt"
    if "captions" in job and job["captions"]:
        make_srt(job["captions"], srt_path)
    else:
        atomic_write_text(srt_path, "")

    duration = str(job["video"]["length_seconds"])
    fps = str(job["video"]["fps"])
    video_w = 1080

    inputs = [
        "-stream_loop", "-1", "-i", str(bg),
        "-stream_loop", "-1", "-i", str(fg),
    ]
    next_input_idx = 2

    audio_asset = resolve_audio_asset(job, sandbox_root)
    has_bg_audio = has_audio_stream(bg)
    if audio_asset:
        audio_source = "job_asset"
        inputs.extend(["-stream_loop", "-1", "-i", str(audio_asset)])
        audio_input_idx = next_input_idx
        next_input_idx += 1
    elif has_bg_audio:
        audio_source = "bg_audio"
        audio_input_idx = 0
    else:
        audio_source = "silence"
        inputs.extend([
            "-f", "lavfi",
            "-t", duration,
            "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
        ])
        audio_input_idx = next_input_idx
        next_input_idx += 1

    wm_input_idx = next_input_idx
    inputs.extend(["-i", str(wm_path)])

    wm_width = max(MIN_WM_WIDTH, min(math.floor(video_w * SCALE_FACTOR), MAX_WM_WIDTH))
    key_color = os.environ.get("CAF_DUET_KEY_COLOR", "0x66DDEE")
    key_sim = float(os.environ.get("CAF_DUET_KEY_SIMILARITY", "0.26"))
    key_blend = float(os.environ.get("CAF_DUET_KEY_BLEND", "0.08"))
    panel_w = int(os.environ.get("CAF_DUET_PANEL_W", "560"))
    panel_h = int(os.environ.get("CAF_DUET_PANEL_H", "996"))
    panel_x = os.environ.get("CAF_DUET_PANEL_X", "W-w-120")
    panel_y = os.environ.get("CAF_DUET_PANEL_Y", "H-h-220")

    base_chain = (
        f"[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1[v_bg];"
        # Foreground path is expected to be a single-subject clip on cyan background.
        # We key cyan out to blend Mochi into the demo dance scene.
        f"[1:v]scale={panel_w}:{panel_h}:force_original_aspect_ratio=decrease,"
        f"pad={panel_w}:{panel_h}:(ow-iw)/2:(oh-ih)/2:color={key_color},setsar=1,format=rgba,"
        f"colorkey={key_color}:{key_sim}:{key_blend}[v_fg];"
        f"[v_bg][v_fg]overlay=x={panel_x}:y={panel_y}:format=auto[v_duet];"
        f"[{wm_input_idx}:v]format=rgba,colorchannelmixer=aa={OPACITY},scale={wm_width}:-1[wm]"
    )

    if "captions" not in job or not job["captions"]:
        subtitles_status = "skipped_no_captions"
    elif srt_path.exists() and srt_path.stat().st_size == 0:
        subtitles_status = "skipped_empty"
    else:
        subtitles_status = "ready_to_burn"

    if subtitles_status == "ready_to_burn" and not ffmpeg_has_subtitles_filter():
        subtitles_status = "skipped_missing_subtitles_filter"

    if subtitles_status == "ready_to_burn":
        try:
            validate_safe_path(srt_path, sandbox_root)
        except ValueError:
            subtitles_status = "skipped_unsafe_path"

    def build_filter(with_subtitles: bool) -> str:
        parts = [base_chain]
        ref = "[v_duet]"
        if with_subtitles:
            safe_srt = escape_ffmpeg_path(srt_path)
            parts.append(f"{ref}subtitles=filename='{safe_srt}'[v_sub]")
            ref = "[v_sub]"
        parts.append(f"{ref}[wm]overlay=W-w-{PADDING_PX}:H-h-{PADDING_PX}[out]")
        return ";".join(parts)

    audio_filter = (
        f"apad=pad_dur={duration},"
        f"atrim=0:{duration},"
        "loudnorm=I=-16:TP=-1.5:LRA=11,"
        "alimiter=limit=0.95"
    )
    output_args = [
        "-map", "[out]",
        "-map", f"{audio_input_idx}:a:0",
        "-t", duration,
        "-r", fps,
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "192k",
        "-ar", "48000",
        "-ac", "2",
        "-af", audio_filter,
        "-movflags", "+faststart",
        "-map_metadata", "-1",
        "-map_chapters", "-1",
        str(out_mp4),
    ]

    failed_cmd = None
    if subtitles_status == "ready_to_burn":
        try:
            cmd = ["ffmpeg", "-y"] + inputs + ["-filter_complex", build_filter(True)] + output_args
            executed_cmd = run_ffmpeg(cmd, out_mp4)
            subtitles_status = "burned"
        except subprocess.CalledProcessError:
            failed_cmd = cmd
            cmd = ["ffmpeg", "-y"] + inputs + ["-filter_complex", build_filter(False)] + output_args
            executed_cmd = run_ffmpeg(cmd, out_mp4)
            subtitles_status = "failed_ffmpeg_subtitles"
    else:
        cmd = ["ffmpeg", "-y"] + inputs + ["-filter_complex", build_filter(False)] + output_args
        executed_cmd = run_ffmpeg(cmd, out_mp4)

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
        "audio_source": audio_source,
        "audio_asset_path": str(audio_asset) if audio_asset else None,
        "has_bg_audio": has_bg_audio,
        "subtitles_status": subtitles_status,
        "ffmpeg_cmd": cmd,
        "ffmpeg_cmd_executed": executed_cmd,
        "failed_ffmpeg_cmd": failed_cmd,
    }


def render_motion_source_overlay_mochi(
    job: dict, sandbox_root: pathlib.Path, out_dir: pathlib.Path, wm_path: pathlib.Path
) -> dict:
    """Lane C bootstrap recipe:
    - background motion authority from render.background_asset (human/source dance clip)
    - foreground cat clip from template.params.foreground_asset (prefer cyan keyed source)
    """
    job_id = job["job_id"]
    bg_rel = job["render"]["background_asset"]
    params = job.get("template", {}).get("params", {})
    fg_rel = params.get("foreground_asset")
    if not isinstance(fg_rel, str) or not fg_rel.strip():
        raise SystemExit("motion_source_overlay_mochi requires template.params.foreground_asset")

    try:
        bg = normalize_sandbox_path(bg_rel, sandbox_root)
        fg = normalize_sandbox_path(fg_rel, sandbox_root)
        validate_safe_path(bg, sandbox_root)
        validate_safe_path(fg, sandbox_root)
    except ValueError as e:
        raise SystemExit(str(e))

    if not bg.exists():
        raise SystemExit(f"Missing motion source background asset: {bg}")
    if not fg.exists():
        raise SystemExit(f"Missing foreground overlay asset: {fg}")

    out_mp4 = out_dir / "final.mp4"
    srt_path = out_dir / "final.srt"
    if "captions" in job and job["captions"]:
        make_srt(job["captions"], srt_path)
    else:
        atomic_write_text(srt_path, "")

    duration = str(job["video"]["length_seconds"])
    fps = str(job["video"]["fps"])
    video_w = 1080

    inputs = [
        "-stream_loop",
        "-1",
        "-i",
        str(bg),
        "-stream_loop",
        "-1",
        "-i",
        str(fg),
    ]
    next_input_idx = 2

    audio_asset = resolve_audio_asset(job, sandbox_root)
    has_bg_audio = has_audio_stream(bg)
    if audio_asset:
        audio_source = "job_asset"
        inputs.extend(["-stream_loop", "-1", "-i", str(audio_asset)])
        audio_input_idx = next_input_idx
        next_input_idx += 1
    elif has_bg_audio:
        audio_source = "bg_audio"
        audio_input_idx = 0
    else:
        audio_source = "silence"
        inputs.extend(
            [
                "-f",
                "lavfi",
                "-t",
                duration,
                "-i",
                "anullsrc=channel_layout=stereo:sample_rate=48000",
            ]
        )
        audio_input_idx = next_input_idx
        next_input_idx += 1

    wm_input_idx = next_input_idx
    inputs.extend(["-i", str(wm_path)])

    wm_width = max(MIN_WM_WIDTH, min(math.floor(video_w * SCALE_FACTOR), MAX_WM_WIDTH))
    key_color = os.environ.get("CAF_DUET_KEY_COLOR", "0x66DDEE")
    key_sim = float(os.environ.get("CAF_DUET_KEY_SIMILARITY", "0.26"))
    key_blend = float(os.environ.get("CAF_DUET_KEY_BLEND", "0.08"))
    panel_w = int(os.environ.get("CAF_DUET_PANEL_W", "560"))
    panel_h = int(os.environ.get("CAF_DUET_PANEL_H", "996"))
    panel_x = os.environ.get("CAF_DUET_PANEL_X", "W-w-120")
    panel_y = os.environ.get("CAF_DUET_PANEL_Y", "H-h-220")

    base_chain = (
        f"[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1[v_bg];"
        f"[1:v]scale={panel_w}:{panel_h}:force_original_aspect_ratio=decrease,"
        f"pad={panel_w}:{panel_h}:(ow-iw)/2:(oh-ih)/2:color={key_color},setsar=1,format=rgba,"
        f"colorkey={key_color}:{key_sim}:{key_blend}[v_fg];"
        f"[v_bg][v_fg]overlay=x={panel_x}:y={panel_y}:format=auto[v_mix];"
        f"[{wm_input_idx}:v]format=rgba,colorchannelmixer=aa={OPACITY},scale={wm_width}:-1[wm]"
    )

    if "captions" not in job or not job["captions"]:
        subtitles_status = "skipped_no_captions"
    elif srt_path.exists() and srt_path.stat().st_size == 0:
        subtitles_status = "skipped_empty"
    else:
        subtitles_status = "ready_to_burn"

    if subtitles_status == "ready_to_burn" and not ffmpeg_has_subtitles_filter():
        subtitles_status = "skipped_missing_subtitles_filter"

    if subtitles_status == "ready_to_burn":
        try:
            validate_safe_path(srt_path, sandbox_root)
        except ValueError:
            subtitles_status = "skipped_unsafe_path"

    def build_filter(with_subtitles: bool) -> str:
        parts = [base_chain]
        ref = "[v_mix]"
        if with_subtitles:
            safe_srt = escape_ffmpeg_path(srt_path)
            parts.append(f"{ref}subtitles=filename='{safe_srt}'[v_sub]")
            ref = "[v_sub]"
        parts.append(f"{ref}[wm]overlay=W-w-{PADDING_PX}:H-h-{PADDING_PX}[out]")
        return ";".join(parts)

    audio_filter = (
        f"apad=pad_dur={duration},"
        f"atrim=0:{duration},"
        "loudnorm=I=-16:TP=-1.5:LRA=11,"
        "alimiter=limit=0.95"
    )
    output_args = [
        "-map",
        "[out]",
        "-map",
        f"{audio_input_idx}:a:0",
        "-t",
        duration,
        "-r",
        fps,
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-ar",
        "48000",
        "-ac",
        "2",
        "-af",
        audio_filter,
        "-movflags",
        "+faststart",
        "-map_metadata",
        "-1",
        "-map_chapters",
        "-1",
        str(out_mp4),
    ]

    failed_cmd = None
    if subtitles_status == "ready_to_burn":
        try:
            cmd = ["ffmpeg", "-y"] + inputs + ["-filter_complex", build_filter(True)] + output_args
            executed_cmd = run_ffmpeg(cmd, out_mp4)
            subtitles_status = "burned"
        except subprocess.CalledProcessError:
            failed_cmd = cmd
            cmd = ["ffmpeg", "-y"] + inputs + ["-filter_complex", build_filter(False)] + output_args
            executed_cmd = run_ffmpeg(cmd, out_mp4)
            subtitles_status = "failed_ffmpeg_subtitles"
    else:
        cmd = ["ffmpeg", "-y"] + inputs + ["-filter_complex", build_filter(False)] + output_args
        executed_cmd = run_ffmpeg(cmd, out_mp4)

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
        "audio_source": audio_source,
        "audio_asset_path": str(audio_asset) if audio_asset else None,
        "has_bg_audio": has_bg_audio,
        "subtitles_status": subtitles_status,
        "ffmpeg_cmd": cmd,
        "ffmpeg_cmd_executed": executed_cmd,
        "failed_ffmpeg_cmd": failed_cmd,
    }


def render_dance_loop_replace_dino_with_mochi(
    job: dict, sandbox_root: pathlib.Path, out_dir: pathlib.Path, wm_path: pathlib.Path
) -> dict:
    """Lane C slot replacement:
    Replace the dino-cat slot in demo dance-loop style background using a keyed Mochi foreground clip.
    """
    job_id = job["job_id"]
    bg_rel = job["render"]["background_asset"]
    params = job.get("template", {}).get("params", {})
    fg_rel = params.get("foreground_asset")
    if not isinstance(fg_rel, str) or not fg_rel.strip():
        raise SystemExit("dance_loop_replace_dino_with_mochi requires template.params.foreground_asset")

    try:
        bg = normalize_sandbox_path(bg_rel, sandbox_root)
        fg = normalize_sandbox_path(fg_rel, sandbox_root)
        validate_safe_path(bg, sandbox_root)
        validate_safe_path(fg, sandbox_root)
    except ValueError as e:
        raise SystemExit(str(e))

    if not bg.exists():
        raise SystemExit(f"Missing replacement background asset: {bg}")
    if not fg.exists():
        raise SystemExit(f"Missing replacement foreground asset: {fg}")

    out_mp4 = out_dir / "final.mp4"
    srt_path = out_dir / "final.srt"
    if "captions" in job and job["captions"]:
        make_srt(job["captions"], srt_path)
    else:
        atomic_write_text(srt_path, "")

    duration = str(job["video"]["length_seconds"])
    fps = str(job["video"]["fps"])
    video_w = 1080

    inputs = [
        "-stream_loop",
        "-1",
        "-i",
        str(bg),
        "-stream_loop",
        "-1",
        "-i",
        str(fg),
    ]
    next_input_idx = 2

    audio_asset = resolve_audio_asset(job, sandbox_root)
    has_bg_audio = has_audio_stream(bg)
    if audio_asset:
        audio_source = "job_asset"
        inputs.extend(["-stream_loop", "-1", "-i", str(audio_asset)])
        audio_input_idx = next_input_idx
        next_input_idx += 1
    elif has_bg_audio:
        audio_source = "bg_audio"
        audio_input_idx = 0
    else:
        audio_source = "silence"
        inputs.extend(
            [
                "-f",
                "lavfi",
                "-t",
                duration,
                "-i",
                "anullsrc=channel_layout=stereo:sample_rate=48000",
            ]
        )
        audio_input_idx = next_input_idx
        next_input_idx += 1

    wm_input_idx = next_input_idx
    inputs.extend(["-i", str(wm_path)])

    wm_width = max(MIN_WM_WIDTH, min(math.floor(video_w * SCALE_FACTOR), MAX_WM_WIDTH))
    key_color = os.environ.get("CAF_DUET_KEY_COLOR", "0x66DDEE")
    key_sim = float(os.environ.get("CAF_DUET_KEY_SIMILARITY", "0.26"))
    key_blend = float(os.environ.get("CAF_DUET_KEY_BLEND", "0.08"))

    # Tuned defaults for the dino slot position in the demo dance-loop composition.
    # Defaults tuned from iterative fitting (v3 baseline).
    slot_w = int(os.environ.get("CAF_REPLACE_DINO_W", "280"))
    slot_h = int(os.environ.get("CAF_REPLACE_DINO_H", "530"))
    slot_x = int(os.environ.get("CAF_REPLACE_DINO_X", "105"))
    slot_y = int(os.environ.get("CAF_REPLACE_DINO_Y", "800"))
    slot_mask_alpha = float(os.environ.get("CAF_REPLACE_DINO_MASK_ALPHA", "0.30"))

    # Deterministic slot tracking motion to better follow the original dino dancer.
    slot_dx = float(os.environ.get("CAF_REPLACE_SLOT_DX", "16"))
    slot_dy = float(os.environ.get("CAF_REPLACE_SLOT_DY", "10"))
    slot_hz = float(os.environ.get("CAF_REPLACE_SLOT_HZ", "1.6"))
    slot_phase = float(os.environ.get("CAF_REPLACE_SLOT_PHASE", "0.0"))
    slot_x_expr = f"{slot_x}+({slot_dx})*sin(2*PI*t*{slot_hz}+{slot_phase})"
    slot_y_expr = f"{slot_y}+({slot_dy})*cos(2*PI*t*{slot_hz}+{slot_phase})"
    fg_is_image = fg.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp")
    face_only_mode = os.environ.get("CAF_REPLACE_DINO_FACE_ONLY", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    if face_only_mode:
        # Preserve the original dino dancer body/motion from the template video and
        # swap only the head region with a Mochi face crop.
        head_w = int(os.environ.get("CAF_REPLACE_HEAD_W", "132"))
        head_h = int(os.environ.get("CAF_REPLACE_HEAD_H", "132"))
        head_x = int(os.environ.get("CAF_REPLACE_HEAD_X", "152"))
        head_y = int(os.environ.get("CAF_REPLACE_HEAD_Y", "768"))
        head_alpha = float(os.environ.get("CAF_REPLACE_HEAD_ALPHA", "0.95"))
        head_dx = float(os.environ.get("CAF_REPLACE_HEAD_DX", "6"))
        head_dy = float(os.environ.get("CAF_REPLACE_HEAD_DY", "5"))
        head_hz = float(os.environ.get("CAF_REPLACE_HEAD_HZ", "1.6"))
        head_phase = float(os.environ.get("CAF_REPLACE_HEAD_PHASE", "0.0"))
        head_x_expr = f"{head_x}+({head_dx})*sin(2*PI*t*{head_hz}+{head_phase})"
        head_y_expr = f"{head_y}+({head_dy})*cos(2*PI*t*{head_hz}+{head_phase})"
        head_radius = int(min(head_w, head_h) * 0.48)
        head_feather = float(os.environ.get("CAF_REPLACE_HEAD_FEATHER", "4.0"))
        base_chain = (
            f"[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1[v_bg];"
            f"[1:v]scale={head_w}:{head_h}:force_original_aspect_ratio=increase,crop={head_w}:{head_h},"
            f"setsar=1,format=rgba,eq=saturation=0.92:contrast=1.04:brightness=-0.015,colorchannelmixer=aa={head_alpha}[v_face_src];"
            f"color=black:s={head_w}x{head_h},format=gray,"
            f"geq=lum='if(lte((X-{head_w}/2)^2+(Y-{head_h}/2)^2,({head_radius})^2),255,0)',"
            f"gblur=sigma={head_feather}[v_mask];"
            f"[v_face_src][v_mask]alphamerge[v_face];"
            f"[v_bg][v_face]overlay=x='{head_x_expr}':y='{head_y_expr}':format=auto:eval=frame[v_mix];"
            f"[{wm_input_idx}:v]format=rgba,colorchannelmixer=aa={OPACITY},scale={wm_width}:-1[wm]"
        )
    elif fg_is_image:
        # Lightweight puppet motion for still-image replacement (deterministic).
        # Adds rhythmic sway/rotation so static replacements feel dance-like.
        sway_hz = float(os.environ.get("CAF_REPLACE_PUPPET_HZ", "1.8"))
        sway_amp = float(os.environ.get("CAF_REPLACE_PUPPET_AMP_DEG", "2.2"))
        scale_pulse = float(os.environ.get("CAF_REPLACE_PUPPET_SCALE_PULSE", "0.015"))
        image_key_color = os.environ.get("CAF_REPLACE_IMAGE_KEY_COLOR", "0x66DDEE").strip()
        image_key_sim = float(os.environ.get("CAF_REPLACE_IMAGE_KEY_SIMILARITY", "0.24"))
        image_key_blend = float(os.environ.get("CAF_REPLACE_IMAGE_KEY_BLEND", "0.06"))
        if image_key_color:
            fg_src_tail = f",colorkey={image_key_color}:{image_key_sim}:{image_key_blend}[v_fg_src]"
        else:
            fg_src_tail = "[v_fg_src]"
        base_chain = (
            f"[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1[v_bg];"
            f"[v_bg]drawbox=x='{slot_x_expr}':y='{slot_y_expr}':w={slot_w}:h={slot_h}:color=black@{slot_mask_alpha}:t=fill[v_bg_mask];"
            f"[1:v]scale={slot_w}:{slot_h}:force_original_aspect_ratio=increase,"
            f"crop={slot_w}:{slot_h},setsar=1,format=rgba{fg_src_tail};"
            f"[v_fg_src]rotate='({sway_amp}*PI/180)*sin(2*PI*t*{sway_hz})':c=none:ow=rotw(iw):oh=roth(ih),"
            f"scale='trunc({slot_w}*(1+{scale_pulse}*sin(2*PI*t*{sway_hz}))/2)*2':'trunc({slot_h}*(1+{scale_pulse}*sin(2*PI*t*{sway_hz}))/2)*2':eval=frame,"
            f"pad={slot_w}:{slot_h}:(ow-iw)/2:(oh-ih)/2:color=black@0.0[v_fg];"
            f"[v_bg_mask][v_fg]overlay=x='{slot_x_expr}':y='{slot_y_expr}':format=auto:eval=frame[v_mix];"
            f"[{wm_input_idx}:v]format=rgba,colorchannelmixer=aa={OPACITY},scale={wm_width}:-1[wm]"
        )
    else:
        # Foreground is expected to be a cyan-keyed generated clip.
        base_chain = (
            f"[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1[v_bg];"
            f"[v_bg]drawbox=x='{slot_x_expr}':y='{slot_y_expr}':w={slot_w}:h={slot_h}:color=black@{slot_mask_alpha}:t=fill[v_bg_mask];"
            f"[1:v]scale={slot_w}:{slot_h}:force_original_aspect_ratio=increase,"
            f"crop={slot_w}:{slot_h},setsar=1,format=rgba,"
            f"colorkey={key_color}:{key_sim}:{key_blend}[v_fg];"
            f"[v_bg_mask][v_fg]overlay=x='{slot_x_expr}':y='{slot_y_expr}':format=auto:eval=frame[v_mix];"
            f"[{wm_input_idx}:v]format=rgba,colorchannelmixer=aa={OPACITY},scale={wm_width}:-1[wm]"
        )

    if "captions" not in job or not job["captions"]:
        subtitles_status = "skipped_no_captions"
    elif srt_path.exists() and srt_path.stat().st_size == 0:
        subtitles_status = "skipped_empty"
    else:
        subtitles_status = "ready_to_burn"

    if subtitles_status == "ready_to_burn" and not ffmpeg_has_subtitles_filter():
        subtitles_status = "skipped_missing_subtitles_filter"

    if subtitles_status == "ready_to_burn":
        try:
            validate_safe_path(srt_path, sandbox_root)
        except ValueError:
            subtitles_status = "skipped_unsafe_path"

    def build_filter(with_subtitles: bool) -> str:
        parts = [base_chain]
        ref = "[v_mix]"
        if with_subtitles:
            safe_srt = escape_ffmpeg_path(srt_path)
            parts.append(f"{ref}subtitles=filename='{safe_srt}'[v_sub]")
            ref = "[v_sub]"
        parts.append(f"{ref}[wm]overlay=W-w-{PADDING_PX}:H-h-{PADDING_PX}[out]")
        return ";".join(parts)

    audio_filter = (
        f"apad=pad_dur={duration},"
        f"atrim=0:{duration},"
        "loudnorm=I=-16:TP=-1.5:LRA=11,"
        "alimiter=limit=0.95"
    )
    output_args = [
        "-map",
        "[out]",
        "-map",
        f"{audio_input_idx}:a:0",
        "-t",
        duration,
        "-r",
        fps,
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-ar",
        "48000",
        "-ac",
        "2",
        "-af",
        audio_filter,
        "-movflags",
        "+faststart",
        "-map_metadata",
        "-1",
        "-map_chapters",
        "-1",
        str(out_mp4),
    ]

    failed_cmd = None
    if subtitles_status == "ready_to_burn":
        try:
            cmd = ["ffmpeg", "-y"] + inputs + ["-filter_complex", build_filter(True)] + output_args
            executed_cmd = run_ffmpeg(cmd, out_mp4)
            subtitles_status = "burned"
        except subprocess.CalledProcessError:
            failed_cmd = cmd
            cmd = ["ffmpeg", "-y"] + inputs + ["-filter_complex", build_filter(False)] + output_args
            executed_cmd = run_ffmpeg(cmd, out_mp4)
            subtitles_status = "failed_ffmpeg_subtitles"
    else:
        cmd = ["ffmpeg", "-y"] + inputs + ["-filter_complex", build_filter(False)] + output_args
        executed_cmd = run_ffmpeg(cmd, out_mp4)

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
        "audio_source": audio_source,
        "audio_asset_path": str(audio_asset) if audio_asset else None,
        "foreground_mode": (
            "face_only" if face_only_mode else ("image_puppet" if fg_is_image else "video_keyed")
        ),
        "has_bg_audio": has_bg_audio,
        "subtitles_status": subtitles_status,
        "ffmpeg_cmd": cmd,
        "ffmpeg_cmd_executed": executed_cmd,
        "failed_ffmpeg_cmd": failed_cmd,
    }


def render_dance_swap(
    job: dict, sandbox_root: pathlib.Path, out_dir: pathlib.Path, wm_path: pathlib.Path
) -> dict:
    contracts = resolve_dance_swap_contracts(job, sandbox_root)
    slot = contracts["slot"]

    overlay_job = json.loads(json.dumps(job))
    overlay_job.setdefault("template", {})
    overlay_job["template"]["params"] = {
        "foreground_asset": contracts["foreground_asset_relpath"],
        "duration_seconds": int(job["video"]["length_seconds"]),
    }
    overlay_job["render"]["background_asset"] = contracts["source_video_relpath"]

    env_overrides = {
        "CAF_REPLACE_DINO_X": str(slot["x"]),
        "CAF_REPLACE_DINO_Y": str(slot["y"]),
        "CAF_REPLACE_DINO_W": str(slot["w"]),
        "CAF_REPLACE_DINO_H": str(slot["h"]),
        "CAF_REPLACE_SLOT_DX": str(slot["dx"]),
        "CAF_REPLACE_SLOT_DY": str(slot["dy"]),
        "CAF_REPLACE_SLOT_HZ": str(slot["hz"]),
    }

    render_result = _with_temp_env(
        env_overrides,
        lambda: render_dance_loop_replace_dino_with_mochi(overlay_job, sandbox_root, out_dir, wm_path),
    )
    render_result["dance_swap"] = contracts
    return render_result


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
            elif req_input == "template.params.foreground_asset":
                params = job.get("template", {}).get("params", {})
                if not isinstance(params, dict) or "foreground_asset" not in params:
                    raise SystemExit(
                        f"Template '{template_id}' requires 'template.params.foreground_asset' in job"
                    )
            else:
                # Strict enforcement: no aliases, no other inputs supported yet
                raise SystemExit(
                    f"Template '{template_id}' requires unknown input '{req_input}'. "
                    "Only 'render.background_asset' and 'template.params.foreground_asset' are supported."
                )


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
        elif recipe_id == "duet_overlay_mochi":
            render_result = render_duet_overlay_mochi(job, sandbox_root, out_dir, wm_path)
        elif recipe_id == "motion_source_overlay_mochi":
            render_result = render_motion_source_overlay_mochi(job, sandbox_root, out_dir, wm_path)
        elif recipe_id == "dance_loop_replace_dino_with_mochi":
            render_result = render_dance_loop_replace_dino_with_mochi(job, sandbox_root, out_dir, wm_path)
        else:
            raise SystemExit(f"Unsupported recipe_id: {recipe_id}")

    elif lane == "image_motion":
        # PR19 Lane B Logic
        render_result = render_image_motion(job, sandbox_root, out_dir, wm_path)
    elif lane == "dance_swap":
        # PR-33.1 deterministic Dance Swap route
        render_result = render_dance_swap(job, sandbox_root, out_dir, wm_path)

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
        "audio_source": render_result.get("audio_source"),
        "audio_asset_path": render_result.get("audio_asset_path"),
        "foreground_mode": render_result.get("foreground_mode"),
        "has_bg_audio": render_result.get("has_bg_audio"),
        "ffmpeg_cmd": render_result["ffmpeg_cmd"],
        "ffmpeg_cmd_executed": render_result["ffmpeg_cmd_executed"],
    }
    
    if lane == "template_remix":
        final_result["template_id"] = template_id
        final_result["recipe_id"] = recipe_id
    elif lane == "image_motion":
        final_result["motion_preset"] = render_result["motion_preset"]
        final_result["seed_frames_count"] = render_result["seed_frames_count"]
    elif lane == "dance_swap":
        final_result["dance_swap"] = render_result.get("dance_swap")
        final_result["recipe_id"] = "dance_swap_slot_overlay_v1"
    
    if render_result.get("failed_ffmpeg_cmd"):
        final_result["failed_ffmpeg_cmd"] = render_result["failed_ffmpeg_cmd"]

    atomic_write_text(result_path, json.dumps(final_result, indent=2, sort_keys=True))

    print("Wrote", render_result["outputs"]["final_mp4"])
    print("Wrote", render_result["outputs"]["final_srt"])
    print("Wrote", result_path)


if __name__ == "__main__":
    main()
