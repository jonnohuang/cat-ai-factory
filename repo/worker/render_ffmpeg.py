import argparse
import copy
import hashlib
import json
import math
import os
import pathlib
import shutil
import statistics
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from typing import Any

from repo.shared.demo_asset_resolver import (
    DANCE_LOOP_CANDIDATES,
    resolve_alias_for_existing,
    resolve_first_existing,
)

try:
    import cv2  # type: ignore
    import numpy as np  # type: ignore
except Exception:
    cv2 = None
    np = None


_HAS_SUBTITLES_FILTER: bool | None = None
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


def atomic_write_json(path: pathlib.Path, payload: dict[str, Any]) -> None:
    atomic_write_text(path, json.dumps(payload, indent=2, sort_keys=True))


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


def prepare_subtitles_file(job: dict, srt_path: pathlib.Path, sandbox_root: pathlib.Path) -> str:
    """
    Resolve subtitles deterministically from:
    1) optional job.captions_artifact.relpath (captions_artifact.v1)
    2) inline job.captions[]
    3) empty fallback

    Returns initial subtitles_status.
    """
    captions_artifact = job.get("captions_artifact")
    if isinstance(captions_artifact, dict):
        relpath = captions_artifact.get("relpath")
        if isinstance(relpath, str) and relpath.strip():
            try:
                artifact_path = resolve_project_relpath(relpath.strip(), repo_root_from_here(), sandbox_root)
            except Exception:
                atomic_write_text(srt_path, "")
                return "skipped_external_invalid_pointer"
            if not artifact_path.exists():
                atomic_write_text(srt_path, "")
                return "skipped_external_missing"
            try:
                artifact = load_json_file(artifact_path)
            except Exception:
                atomic_write_text(srt_path, "")
                return "skipped_external_invalid_json"
            if artifact.get("version") != "captions_artifact.v1":
                atomic_write_text(srt_path, "")
                return "skipped_external_invalid_contract"
            srt_relpath = artifact.get("srt_relpath")
            if not isinstance(srt_relpath, str) or not srt_relpath.strip():
                atomic_write_text(srt_path, "")
                return "skipped_external_missing_srt_relpath"
            try:
                source_srt = resolve_project_relpath(srt_relpath.strip(), repo_root_from_here(), sandbox_root)
            except Exception:
                atomic_write_text(srt_path, "")
                return "skipped_external_invalid_srt_pointer"
            if (not source_srt.exists()) or (not source_srt.is_file()):
                atomic_write_text(srt_path, "")
                return "skipped_external_srt_missing"
            content = source_srt.read_text(encoding="utf-8")
            atomic_write_text(srt_path, content)
            if srt_path.stat().st_size == 0:
                return "skipped_empty"
            return "ready_to_burn"

    if "captions" in job and job["captions"]:
        make_srt(job["captions"], srt_path)
        if srt_path.stat().st_size == 0:
            return "skipped_empty"
        return "ready_to_burn"

    whisper_status = maybe_generate_whisper_captions(job=job, srt_path=srt_path, sandbox_root=sandbox_root)
    if whisper_status is not None:
        return whisper_status
    atomic_write_text(srt_path, "")
    return "skipped_no_captions"


def maybe_generate_whisper_captions(
    *,
    job: dict,
    srt_path: pathlib.Path,
    sandbox_root: pathlib.Path,
) -> str | None:
    enabled = os.environ.get("CAF_ENABLE_WHISPER_CAPTIONS", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    if not enabled:
        return None
    render = job.get("render")
    if not isinstance(render, dict):
        return "skipped_whisper_no_render"
    bg_rel = render.get("background_asset")
    if not isinstance(bg_rel, str) or not bg_rel.strip():
        return "skipped_whisper_no_background"
    try:
        media_path = normalize_sandbox_path(bg_rel.strip(), sandbox_root)
        validate_safe_path(media_path, sandbox_root)
    except Exception:
        return "skipped_whisper_invalid_source"
    if (not media_path.exists()) or (not media_path.is_file()):
        return "skipped_whisper_missing_source"

    work_dir = srt_path.parent / "_whisper"
    work_dir.mkdir(parents=True, exist_ok=True)
    wav_path = work_dir / "whisper_input.wav"
    base_name = "whisper_input"
    out_srt = work_dir / f"{base_name}.srt"
    try:
        run_subprocess(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(media_path),
                "-vn",
                "-ac",
                "1",
                "-ar",
                "16000",
                str(wav_path),
            ]
        )
        run_subprocess(
            [
                sys.executable,
                "-m",
                "whisper",
                str(wav_path),
                "--model",
                os.environ.get("CAF_WHISPER_MODEL", "tiny"),
                "--task",
                "transcribe",
                "--output_format",
                "srt",
                "--output_dir",
                str(work_dir),
            ]
        )
        if out_srt.exists() and out_srt.stat().st_size > 0:
            atomic_write_text(srt_path, out_srt.read_text(encoding="utf-8"))
            return "ready_to_burn"
        return "skipped_whisper_empty"
    except Exception:
        return "skipped_whisper_failed"


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


def run_subprocess(cmd: list[str]) -> list[str]:
    print("Running:", " ".join(cmd))
    subprocess.check_call(cmd)
    return cmd


def _http_json(
    *,
    url: str,
    method: str,
    payload: dict[str, Any] | None = None,
    timeout_s: int = 60,
) -> dict[str, Any]:
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url=url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as ex:
        body = ""
        try:
            body = ex.read().decode("utf-8", errors="replace")
        except Exception:
            body = ""
        detail = f"HTTP {ex.code}"
        if body:
            detail = f"{detail} body={body}"
        raise RuntimeError(detail) from ex
    obj = json.loads(raw)
    if not isinstance(obj, dict):
        raise RuntimeError("non-object JSON response")
    return obj


def _http_download(url: str, dst: pathlib.Path, timeout_s: int = 300) -> None:
    req = urllib.request.Request(url=url, method="GET")
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        data = resp.read()
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(data)


def _comfy_object_info(base_url: str) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}/object_info"
    return _http_json(url=url, method="GET", payload=None, timeout_s=60)


def _comfy_resolve_checkpoint(base_url: str) -> str:
    ckpt = os.environ.get("COMFYUI_CHECKPOINT_NAME", "").strip()
    info = _comfy_object_info(base_url)
    node = info.get("CheckpointLoaderSimple")
    names: list[str] = []
    if isinstance(node, dict):
        req = ((node.get("input") or {}).get("required") or {}).get("ckpt_name")
        if isinstance(req, list) and req:
            first = req[0]
            if isinstance(first, list):
                names = [str(x) for x in first if isinstance(x, str)]
    if ckpt:
        if names and ckpt not in names:
            raise SystemExit(
                f"COMFYUI_CHECKPOINT_NAME='{ckpt}' not found in Comfy checkpoints: {names}"
            )
        return ckpt
    if not names:
        raise SystemExit(
            "Comfy motion synthesis requires at least one checkpoint model under "
            "ComfyUI/models/checkpoints (or set COMFYUI_CHECKPOINT_NAME)."
        )
    return names[0]


def _comfy_pick_media_item(history_obj: dict[str, Any]) -> dict[str, str] | None:
    # Comfy history schema has outputs by node; each node may include videos/images/gifs arrays.
    outputs = history_obj.get("outputs")
    if not isinstance(outputs, dict):
        return None
    for node_out in outputs.values():
        if not isinstance(node_out, dict):
            continue
        for key in ("videos", "images", "gifs"):
            items = node_out.get(key)
            if not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, dict):
                    continue
                filename = item.get("filename")
                subfolder = item.get("subfolder", "")
                media_type = item.get("type", "output")
                if isinstance(filename, str) and filename.strip():
                    return {
                        "filename": filename.strip(),
                        "subfolder": str(subfolder),
                        "type": str(media_type),
                    }
    return None


def _apply_comfy_bindings(prompt_graph: dict[str, Any], bindings: dict[str, Any]) -> None:
    # Applies basic deterministic bindings to named nodes in exported workflow JSON.
    positive = str(bindings.get("positive_prompt", "")).strip()
    negative = str(bindings.get("negative_prompt", "")).strip()
    seed = bindings.get("seed")
    positive_nodes = [str(x) for x in bindings.get("positive_nodes", []) if isinstance(x, str)]
    negative_nodes = [str(x) for x in bindings.get("negative_nodes", []) if isinstance(x, str)]
    seed_nodes = [str(x) for x in bindings.get("seed_nodes", []) if isinstance(x, str)]

    for node_id in positive_nodes:
        node = prompt_graph.get(node_id)
        if isinstance(node, dict) and isinstance(node.get("inputs"), dict):
            if positive and "text" in node["inputs"]:
                node["inputs"]["text"] = positive
    for node_id in negative_nodes:
        node = prompt_graph.get(node_id)
        if isinstance(node, dict) and isinstance(node.get("inputs"), dict):
            if negative and "text" in node["inputs"]:
                node["inputs"]["text"] = negative
    for node_id in seed_nodes:
        node = prompt_graph.get(node_id)
        if isinstance(node, dict) and isinstance(node.get("inputs"), dict):
            if isinstance(seed, int) and "seed" in node["inputs"]:
                node["inputs"]["seed"] = seed


def _prepare_comfy_seed_image(
    *,
    job: dict[str, Any],
    repo_root: pathlib.Path,
    sandbox_root: pathlib.Path,
) -> str:
    comfy_home_s = os.environ.get("COMFYUI_HOME", "").strip()
    comfy_home = pathlib.Path(comfy_home_s) if comfy_home_s else (repo_root / "sandbox" / "third_party" / "ComfyUI")
    input_dir = comfy_home / "input"
    input_dir.mkdir(parents=True, exist_ok=True)
    seed_png = input_dir / "caf_seed_input.png"

    # Prefer current render background as seed when present.
    bg_rel = str((job.get("render") or {}).get("background_asset") or "").strip()
    bg_path: pathlib.Path | None = None
    if bg_rel:
        try:
            bg_path = normalize_sandbox_path(bg_rel, sandbox_root)
            validate_safe_path(bg_path, sandbox_root)
        except Exception:
            bg_path = None
    if bg_path is None or (not bg_path.exists()):
        fallback_rel = resolve_first_existing(
            sandbox_root=sandbox_root,
            candidates=DANCE_LOOP_CANDIDATES,
        )
        if fallback_rel:
            bg_path = sandbox_root / fallback_rel
        else:
            raise SystemExit("Comfy seed image source is missing; set render.background_asset or provide demo source.")

    ext = bg_path.suffix.lower()
    if ext in {".png", ".jpg", ".jpeg", ".webp"}:
        shutil.copy2(bg_path, seed_png)
        return seed_png.name

    # Treat everything else as video and extract the first frame.
    cmd = [
        "ffmpeg",
        "-y",
        "-ss",
        "0.0",
        "-i",
        str(bg_path),
        "-frames:v",
        "1",
        str(seed_png),
    ]
    run_subprocess(cmd)
    if not seed_png.exists() or seed_png.stat().st_size == 0:
        raise SystemExit(f"failed to prepare Comfy seed image: {seed_png}")
    return seed_png.name


def _inject_comfy_seed_image(prompt_graph: dict[str, Any], seed_filename: str) -> None:
    for node in prompt_graph.values():
        if not isinstance(node, dict):
            continue
        if str(node.get("class_type", "")).strip() != "LoadImage":
            continue
        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            continue
        image_name = str(inputs.get("image", "")).strip()
        if image_name == "__CAF_SEED_IMAGE__":
            inputs["image"] = seed_filename
            inputs["upload"] = "image"


def _inject_motion_frame_inputs(
    prompt_graph: dict[str, Any],
    *,
    frame_filename: str,
    anchor_filename: str | None,
    checkpoint_name: str | None,
) -> None:
    for node in prompt_graph.values():
        if not isinstance(node, dict):
            continue
        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            continue
        cls = str(node.get("class_type", "")).strip()
        if cls == "LoadImage" and str(inputs.get("image", "")).strip() == "__CAF_FRAME_IMAGE__":
            inputs["image"] = frame_filename
            inputs["upload"] = "image"
        if (
            anchor_filename
            and cls == "LoadImage"
            and str(inputs.get("image", "")).strip() == "__CAF_ANCHOR_IMAGE__"
        ):
            inputs["image"] = anchor_filename
            inputs["upload"] = "image"
        if (
            checkpoint_name
            and cls == "CheckpointLoaderSimple"
            and str(inputs.get("ckpt_name", "")).strip() == "__CAF_CHECKPOINT__"
        ):
            inputs["ckpt_name"] = checkpoint_name


def _prepare_comfy_anchor_image(
    *,
    job: dict[str, Any],
    sandbox_root: pathlib.Path,
    comfy_input_dir: pathlib.Path,
) -> str | None:
    render = job.get("render") if isinstance(job.get("render"), dict) else {}
    bg_rel = str(render.get("background_asset") or "").strip()
    candidates = [
        os.environ.get("COMFYUI_ANCHOR_IMAGE", "").strip(),
        "assets/demo/mochi_dino_frame_for_key.png",
        "assets/demo/mochi_front.png",
        "assets/demo/mochi_profile.png",
        bg_rel if bg_rel.lower().endswith((".png", ".jpg", ".jpeg", ".webp")) else "",
    ]
    for rel in candidates:
        if not rel:
            continue
        try:
            src = normalize_sandbox_path(rel, sandbox_root)
            validate_safe_path(src, sandbox_root)
        except Exception:
            continue
        if not src.exists() or not src.is_file():
            continue
        ext = src.suffix.lower()
        if ext not in {".png", ".jpg", ".jpeg", ".webp"}:
            continue
        dst = comfy_input_dir / "caf_anchor_input.png"
        shutil.copy2(src, dst)
        return dst.name
    return None


def _prepare_motion_frames(
    *,
    job: dict[str, Any],
    sandbox_root: pathlib.Path,
    out_dir: pathlib.Path,
    comfy_input_dir: pathlib.Path,
    motion_fps: int,
    max_frames: int,
) -> list[str]:
    bg_rel = str((job.get("render") or {}).get("background_asset") or "").strip()
    if not bg_rel:
        raise SystemExit("motion workflow requires render.background_asset source video")
    bg_path = normalize_sandbox_path(bg_rel, sandbox_root)
    validate_safe_path(bg_path, sandbox_root)
    if not bg_path.exists():
        raise SystemExit(f"motion workflow source video not found: {bg_path}")

    tmp_dir = out_dir / "generated" / "motion_source_frames"
    if tmp_dir.exists():
        for p in tmp_dir.glob("*.png"):
            p.unlink()
    tmp_dir.mkdir(parents=True, exist_ok=True)

    motion_preprocess = os.environ.get("CAF_COMFY_MOTION_PREPROCESS", "pose").strip().lower()
    ffmpeg_preprocess = motion_preprocess
    if motion_preprocess in {"pose", "mediapipe_pose"}:
        # Extract clean RGB frames first; pose hints are derived in Python below.
        ffmpeg_preprocess = "none"

    vf = f"fps={motion_fps}"
    if ffmpeg_preprocess in {"edge", "edges", "edgedetect"}:
        # Use structure-heavy hints to reduce direct identity leakage from source footage.
        vf = f"{vf},edgedetect=low=0.08:high=0.22,format=rgb24"
    elif ffmpeg_preprocess in {"gray", "grayscale"}:
        vf = f"{vf},format=gray,format=rgb24"

    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(bg_path),
        "-vf",
        vf,
        str(tmp_dir / "frame_%04d.png"),
    ]
    run_subprocess(cmd)
    src_frames = sorted(tmp_dir.glob("frame_*.png"))
    if not src_frames:
        raise SystemExit("motion workflow could not extract source frames")
    if max_frames > 0 and len(src_frames) > max_frames:
        # Keep temporal coverage across the full source clip rather than
        # truncating to the opening seconds.
        if max_frames == 1:
            src_frames = [src_frames[0]]
        else:
            last = len(src_frames) - 1
            picked: list[pathlib.Path] = []
            used: set[int] = set()
            for i in range(max_frames):
                idx = round(i * last / (max_frames - 1))
                if idx in used:
                    continue
                used.add(idx)
                picked.append(src_frames[idx])
            src_frames = picked

    processed_frames = src_frames
    preprocess_report: dict[str, Any] = {
        "requested_mode": motion_preprocess,
        "status": "raw",
        "frames_in": len(src_frames),
    }
    if motion_preprocess in {"pose", "mediapipe_pose"}:
        pose_dir = out_dir / "generated" / "motion_pose_frames"
        if pose_dir.exists():
            for p in pose_dir.glob("*.png"):
                p.unlink()
        pose_dir.mkdir(parents=True, exist_ok=True)
        try:
            import cv2  # type: ignore
            import numpy as np  # type: ignore
            import mediapipe as mp  # type: ignore
            built: list[pathlib.Path] = []
            detected_count = 0
            coverage_threshold = float(os.environ.get("CAF_COMFY_POSE_MIN_DETECTION_RATIO", "0.35") or 0.35)

            if hasattr(mp, "solutions"):
                # Legacy MediaPipe Solutions API.
                mp_solutions = mp.solutions  # type: ignore[attr-defined]
                pose = mp_solutions.pose.Pose(
                    static_image_mode=True,
                    model_complexity=int(os.environ.get("CAF_MEDIAPIPE_MODEL_COMPLEXITY", "1") or 1),
                    min_detection_confidence=float(os.environ.get("CAF_MEDIAPIPE_MIN_DETECTION", "0.5") or 0.5),
                )
                drawing = mp_solutions.drawing_utils
                drawing_styles = mp_solutions.drawing_styles
                connections = mp_solutions.pose.POSE_CONNECTIONS

                last_pose_canvas: Optional[Any] = None
                for i, src in enumerate(src_frames, start=1):
                    img = cv2.imread(str(src))
                    if img is None:
                        continue
                    rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                    result = pose.process(rgb)
                    canvas = np.zeros_like(img)
                    if result.pose_landmarks:
                        detected_count += 1
                        drawing.draw_landmarks(
                            canvas,
                            result.pose_landmarks,
                            connections,
                            landmark_drawing_spec=drawing_styles.get_default_pose_landmarks_style(),
                        )
                        last_pose_canvas = canvas.copy()
                    elif last_pose_canvas is not None:
                        canvas = last_pose_canvas.copy()
                    dst = pose_dir / f"frame_{i:04d}.png"
                    cv2.imwrite(str(dst), canvas)
                    built.append(dst)
            else:
                # MediaPipe Tasks API path (newer wheels, no mp.solutions).
                from mediapipe.tasks.python import vision  # type: ignore
                from mediapipe.tasks.python.core.base_options import BaseOptions  # type: ignore
                from mediapipe.tasks.python.vision import drawing_utils, drawing_styles  # type: ignore

                model_path_s = os.environ.get("CAF_MEDIAPIPE_POSE_MODEL", "").strip()
                model_path = (
                    pathlib.Path(model_path_s)
                    if model_path_s
                    else (sandbox_root / "assets" / "models" / "mediapipe" / "pose_landmarker_lite.task")
                )
                if not model_path.exists():
                    raise FileNotFoundError(
                        "pose landmarker model not found: "
                        f"{model_path} (set CAF_MEDIAPIPE_POSE_MODEL)"
                    )

                options = vision.PoseLandmarkerOptions(
                    base_options=BaseOptions(model_asset_path=str(model_path)),
                    running_mode=vision.RunningMode.IMAGE,
                    num_poses=1,
                    min_pose_detection_confidence=float(
                        os.environ.get("CAF_MEDIAPIPE_MIN_DETECTION", "0.5") or 0.5
                    ),
                )
                detector = vision.PoseLandmarker.create_from_options(options)
                connections = vision.PoseLandmarksConnections.POSE_LANDMARKS

                last_pose_canvas: Optional[Any] = None
                for i, src in enumerate(src_frames, start=1):
                    img = cv2.imread(str(src))
                    if img is None:
                        continue
                    rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                    mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                    result = detector.detect(mp_img)
                    canvas = np.zeros_like(img)
                    if result.pose_landmarks:
                        detected_count += 1
                        drawing_utils.draw_landmarks(
                            canvas,
                            result.pose_landmarks[0],
                            connections,
                            landmark_drawing_spec=drawing_styles.get_default_pose_landmarks_style(),
                        )
                        last_pose_canvas = canvas.copy()
                    elif last_pose_canvas is not None:
                        canvas = last_pose_canvas.copy()
                    dst = pose_dir / f"frame_{i:04d}.png"
                    cv2.imwrite(str(dst), canvas)
                    built.append(dst)

            if built:
                detection_ratio = float(detected_count) / float(len(built))
                preprocess_report["frames_out"] = len(built)
                preprocess_report["frames_detected"] = detected_count
                preprocess_report["detection_ratio"] = round(detection_ratio, 4)
                preprocess_report["min_detection_ratio"] = coverage_threshold
                if detection_ratio >= coverage_threshold:
                    processed_frames = built
                    preprocess_report["status"] = "mediapipe_pose"
                    print(
                        "INFO worker comfy motion_preprocess=pose "
                        f"frames={len(built)} detected={detected_count} ratio={detection_ratio:.3f}"
                    )
                else:
                    preprocess_report["status"] = "pose_low_detection_fallback_raw"
                    print(
                        "WARNING worker comfy motion_preprocess=pose low detection ratio; "
                        f"using raw frames ratio={detection_ratio:.3f} min={coverage_threshold:.3f}"
                    )
            else:
                preprocess_report["status"] = "pose_empty_fallback_raw"
                print("WARNING worker comfy motion_preprocess=pose produced no frames; using raw frames")
        except Exception as ex:
            preprocess_report["status"] = "mediapipe_unavailable_fallback_raw"
            preprocess_report["error"] = f"{type(ex).__name__}: {ex}"
            print(
                "WARNING worker comfy motion_preprocess=pose unavailable; "
                f"using raw frames ({type(ex).__name__}: {ex})"
            )

    try:
        report_path = out_dir / "generated" / "motion_preprocess_report.v1.json"
        report_path.write_text(json.dumps(preprocess_report, indent=2), encoding="utf-8")
    except Exception:
        pass

    frame_filenames: list[str] = []
    for idx, src in enumerate(processed_frames, start=1):
        dst_name = f"caf_motion_frame_{idx:04d}.png"
        dst = comfy_input_dir / dst_name
        shutil.copy2(src, dst)
        frame_filenames.append(dst_name)
    return frame_filenames


def _render_motion_sequence_via_comfy(
    *,
    job: dict[str, Any],
    prompt_graph_template: dict[str, Any],
    base_url: str,
    sandbox_root: pathlib.Path,
    comfy_home: pathlib.Path,
    out_dir: pathlib.Path,
    bindings: dict[str, Any] | None,
    timeout_seconds: int,
    interval_seconds: int,
) -> dict[str, Any]:
    requires_checkpoint = "__CAF_CHECKPOINT__" in json.dumps(prompt_graph_template, sort_keys=True)
    checkpoint_name: str | None = None
    if requires_checkpoint:
        checkpoint_name = _comfy_resolve_checkpoint(base_url)
    motion_fps = int(os.environ.get("CAF_COMFY_MOTION_FPS", "2") or 2)
    motion_fps = max(1, min(8, motion_fps))
    max_frames = int(os.environ.get("CAF_COMFY_MOTION_MAX_FRAMES", "12") or 12)
    max_frames = max(1, min(120, max_frames))
    comfy_input_dir = comfy_home / "input"
    comfy_input_dir.mkdir(parents=True, exist_ok=True)
    anchor_filename = _prepare_comfy_anchor_image(
        job=job,
        sandbox_root=sandbox_root,
        comfy_input_dir=comfy_input_dir,
    )
    frame_names = _prepare_motion_frames(
        job=job,
        sandbox_root=sandbox_root,
        out_dir=out_dir,
        comfy_input_dir=comfy_input_dir,
        motion_fps=motion_fps,
        max_frames=max_frames,
    )

    gen_frames_dir = out_dir / "generated" / "motion_frames"
    gen_frames_dir.mkdir(parents=True, exist_ok=True)
    for old in gen_frames_dir.glob("frame_*.png"):
        old.unlink()

    for i, frame_name in enumerate(frame_names, start=1):
        print(f"INFO worker comfy motion_frame_start index={i}/{len(frame_names)} src={frame_name}")
        prompt_graph = copy.deepcopy(prompt_graph_template)
        if isinstance(bindings, dict):
            _apply_comfy_bindings(prompt_graph, bindings)
        _inject_motion_frame_inputs(
            prompt_graph,
            frame_filename=frame_name,
            anchor_filename=anchor_filename,
            checkpoint_name=checkpoint_name,
        )
        client_id = str(uuid.uuid4())
        submit_url = f"{base_url}/prompt"
        submit_payload = {"client_id": client_id, "prompt": prompt_graph}
        try:
            submit_resp = _http_json(url=submit_url, method="POST", payload=submit_payload, timeout_s=120)
        except Exception as ex:
            raise SystemExit(f"comfy motion submit failed at frame {i}: {type(ex).__name__}: {ex}")
        prompt_id = submit_resp.get("prompt_id")
        if not isinstance(prompt_id, str) or not prompt_id.strip():
            raise SystemExit(f"comfy motion submit missing prompt_id at frame {i}")
        prompt_id = prompt_id.strip()
        print(f"INFO worker comfy motion_prompt_submitted index={i}/{len(frame_names)} prompt_id={prompt_id}")
        deadline = time.time() + timeout_seconds
        history_obj: dict[str, Any] | None = None
        while time.time() < deadline:
            history_url = f"{base_url}/history/{prompt_id}"
            try:
                history_resp = _http_json(url=history_url, method="GET", payload=None, timeout_s=60)
            except Exception:
                time.sleep(interval_seconds)
                continue
            raw = history_resp.get(prompt_id)
            if isinstance(raw, dict) and raw:
                status = raw.get("status")
                if isinstance(status, dict):
                    status_str = str(status.get("status_str", "")).lower()
                    if status_str in {"error", "failed"}:
                        raise SystemExit(
                            f"comfy motion generation failed at frame {i} prompt_id={prompt_id}"
                        )
                media = _comfy_pick_media_item(raw)
                if media is not None:
                    history_obj = raw
                    break
            time.sleep(interval_seconds)
        if history_obj is None:
            raise SystemExit(f"comfy motion timeout at frame {i} prompt_id={prompt_id}")
        media = _comfy_pick_media_item(history_obj)
        if media is None:
            raise SystemExit(f"comfy motion missing media at frame {i}")
        query = urllib.parse.urlencode(
            {
                "filename": media["filename"],
                "subfolder": media["subfolder"],
                "type": media["type"],
            }
        )
        view_url = f"{base_url}/view?{query}"
        out_img = gen_frames_dir / f"frame_{i:04d}.png"
        _http_download(view_url, out_img, timeout_s=120)
        print(f"INFO worker comfy motion_frame_done index={i}/{len(frame_names)} output={out_img.name}")

    video_cfg = job.get("video") if isinstance(job.get("video"), dict) else {}
    resolution = str(video_cfg.get("resolution", "1080x1920"))
    if "x" in resolution:
        w_s, h_s = resolution.lower().split("x", 1)
        try:
            w = int(w_s)
            h = int(h_s)
        except Exception:
            w, h = 1080, 1920
    else:
        w, h = 1080, 1920
    out_video = out_dir / "generated" / "comfy_motion_source.mp4"
    tmp_video = out_dir / "generated" / "comfy_motion_source.short.mp4"
    target_fps = int(video_cfg.get("fps", 30) or 30)
    target_fps = max(12, min(60, target_fps))
    target_duration = int(video_cfg.get("length_seconds", 12) or 12)
    target_duration = max(1, min(60, target_duration))
    use_minterp = os.environ.get("CAF_COMFY_ENABLE_MINTERPOLATE", "1").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    vf_core = f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}"
    if use_minterp:
        vf = f"{vf_core},minterpolate=fps={target_fps}:mi_mode=mci:mc_mode=aobmc:vsbmc=1"
    else:
        vf = f"{vf_core},fps={target_fps}"
    cmd = [
        "ffmpeg",
        "-y",
        "-framerate",
        str(motion_fps),
        "-i",
        str(gen_frames_dir / "frame_%04d.png"),
        "-vf",
        vf,
        "-c:v",
        "libx264",
        "-preset",
        "slow",
        "-crf",
        "18",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(tmp_video),
    ]
    run_ffmpeg(cmd, tmp_video)
    loop_cmd = [
        "ffmpeg",
        "-y",
        "-stream_loop",
        "-1",
        "-i",
        str(tmp_video),
        "-t",
        str(target_duration),
        "-r",
        str(target_fps),
        "-c:v",
        "libx264",
        "-preset",
        "slow",
        "-crf",
        "18",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(out_video),
    ]
    run_ffmpeg(loop_cmd, out_video)
    if tmp_video.exists():
        tmp_video.unlink()
    rel_video = str(out_video.resolve().relative_to(sandbox_root.resolve())).replace("\\", "/")
    return {
        "provider": "comfyui_video",
        "mode": "motion_frame_sequence",
        "checkpoint_name": checkpoint_name,
        "frame_count": len(frame_names),
        "anchor_image": anchor_filename,
        "motion_fps": motion_fps,
        "target_fps": target_fps,
        "target_duration": target_duration,
        "minterpolate_enabled": use_minterp,
        "output_relpath": rel_video,
    }


def _ensure_video_from_comfy_media(
    *,
    media_path: pathlib.Path,
    out_dir: pathlib.Path,
    job: dict[str, Any],
) -> pathlib.Path:
    ext = media_path.suffix.lower()
    if ext in {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}:
        return media_path

    # Convert image output to deterministic short video so render pipeline can consume it.
    video_cfg = job.get("video") if isinstance(job.get("video"), dict) else {}
    duration = int(video_cfg.get("length_seconds", 12) or 12)
    fps = int(video_cfg.get("fps", 30) or 30)
    resolution = str(video_cfg.get("resolution", "1080x1920"))
    if "x" in resolution:
        w_s, h_s = resolution.lower().split("x", 1)
        try:
            w = int(w_s)
            h = int(h_s)
        except Exception:
            w, h = 1080, 1920
    else:
        w, h = 1080, 1920

    video_path = out_dir / "generated" / "comfy_source.mp4"
    video_path.parent.mkdir(parents=True, exist_ok=True)
    vf = f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:black"
    cmd = [
        "ffmpeg",
        "-y",
        "-loop",
        "1",
        "-i",
        str(media_path),
        "-t",
        str(duration),
        "-r",
        str(fps),
        "-vf",
        vf,
        "-c:v",
        "libx264",
        "-preset",
        "slow",
        "-crf",
        "18",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(video_path),
    ]
    run_ffmpeg(cmd, video_path)
    return video_path


def generate_comfyui_video_asset(
    *,
    job: dict[str, Any],
    repo_root: pathlib.Path,
    sandbox_root: pathlib.Path,
    out_dir: pathlib.Path,
) -> dict[str, Any]:
    comfy = job.get("comfyui")
    if not isinstance(comfy, dict):
        raise SystemExit("selected_video_provider=comfyui_video requires job.comfyui block")

    base_url = str(comfy.get("base_url") or os.environ.get("COMFYUI_BASE_URL", "")).strip().rstrip("/")
    if not base_url:
        raise SystemExit("comfyui generation requires COMFYUI_BASE_URL or job.comfyui.base_url")

    workflow_rel = comfy.get("workflow_relpath")
    if not isinstance(workflow_rel, str) or not workflow_rel.strip():
        raise SystemExit("job.comfyui.workflow_relpath is required")
    workflow_path = resolve_project_relpath(workflow_rel.strip(), repo_root, sandbox_root)
    if not workflow_path.exists():
        raise SystemExit(f"comfy workflow not found: {workflow_path}")

    workflow_doc = load_json_file(workflow_path)
    prompt_graph: dict[str, Any] | None = None
    if isinstance(workflow_doc.get("prompt_api"), dict):
        prompt_graph = workflow_doc["prompt_api"]
    elif isinstance(workflow_doc.get("nodes"), dict):
        prompt_graph = workflow_doc["nodes"]
    if not isinstance(prompt_graph, dict) or not prompt_graph:
        raise SystemExit("comfy workflow must provide non-empty 'prompt_api' or 'nodes' map")

    bindings = comfy.get("bindings")
    workflow_mode = str(workflow_doc.get("caf_mode", "")).strip().lower()
    if workflow_mode == "motion_frame_sequence":
        comfy_home_s = os.environ.get("COMFYUI_HOME", "").strip()
        comfy_home = pathlib.Path(comfy_home_s) if comfy_home_s else (repo_root / "sandbox" / "third_party" / "ComfyUI")
        return _render_motion_sequence_via_comfy(
            job=job,
            prompt_graph_template=prompt_graph,
            base_url=base_url,
            sandbox_root=sandbox_root,
            comfy_home=comfy_home,
            out_dir=out_dir,
            bindings=bindings if isinstance(bindings, dict) else None,
            timeout_seconds=int((comfy.get("poll") or {}).get("timeout_seconds", 900) or 900),
            interval_seconds=int((comfy.get("poll") or {}).get("interval_seconds", 2) or 2),
        )
    if isinstance(bindings, dict):
        _apply_comfy_bindings(prompt_graph, bindings)
    seed_filename = _prepare_comfy_seed_image(job=job, repo_root=repo_root, sandbox_root=sandbox_root)
    _inject_comfy_seed_image(prompt_graph, seed_filename)

    poll = comfy.get("poll") if isinstance(comfy.get("poll"), dict) else {}
    timeout_seconds = int(poll.get("timeout_seconds", 900) or 900)
    interval_seconds = int(poll.get("interval_seconds", 2) or 2)
    timeout_seconds = max(30, min(3600, timeout_seconds))
    interval_seconds = max(1, min(10, interval_seconds))

    client_id = str(comfy.get("client_id") or uuid.uuid4())
    submit_url = f"{base_url}/prompt"
    submit_payload = {
        "client_id": client_id,
        "prompt": prompt_graph,
    }
    try:
        submit_resp = _http_json(url=submit_url, method="POST", payload=submit_payload, timeout_s=120)
    except Exception as ex:
        msg = f"{type(ex).__name__}: {ex}"
        # Allow placeholder workflow fallback so end-to-end pipeline remains testable.
        # Real Comfy generation requires a workflow graph with output nodes.
        if "prompt_no_outputs" in str(ex):
            print(
                "WARNING worker comfy placeholder workflow has no outputs; "
                "falling back to existing render.background_asset"
            )
            return {
                "provider": "comfyui_video",
                "fallback_used": True,
                "fallback_reason": "prompt_no_outputs",
                "base_url": base_url,
                "workflow_relpath": str(workflow_rel),
            }
        raise SystemExit(f"comfy submit failed at {submit_url}: {msg}")
    prompt_id = submit_resp.get("prompt_id")
    if not isinstance(prompt_id, str) or not prompt_id.strip():
        raise SystemExit("comfy submit did not return prompt_id")
    prompt_id = prompt_id.strip()
    print(f"INFO worker comfy prompt_submitted prompt_id={prompt_id}")

    deadline = time.time() + timeout_seconds
    history_obj: dict[str, Any] | None = None
    while time.time() < deadline:
        history_url = f"{base_url}/history/{prompt_id}"
        try:
            history_resp = _http_json(url=history_url, method="GET", payload=None, timeout_s=60)
        except Exception:
            time.sleep(interval_seconds)
            continue
        raw = history_resp.get(prompt_id)
        if isinstance(raw, dict) and raw:
            status = raw.get("status")
            if isinstance(status, dict):
                status_str = str(status.get("status_str", "")).lower()
                if status_str in {"error", "failed"}:
                    raise SystemExit(f"comfy generation failed for prompt_id={prompt_id}")
            media = _comfy_pick_media_item(raw)
            if media is not None:
                history_obj = raw
                break
        time.sleep(interval_seconds)

    if history_obj is None:
        raise SystemExit(f"comfy generation timeout after {timeout_seconds}s for prompt_id={prompt_id}")

    media = _comfy_pick_media_item(history_obj)
    if media is None:
        raise SystemExit("comfy completed but no media item found in history outputs")
    filename = media["filename"]
    subfolder = media["subfolder"]
    media_type = media["type"]
    query = urllib.parse.urlencode(
        {
            "filename": filename,
            "subfolder": subfolder,
            "type": media_type,
        }
    )
    view_url = f"{base_url}/view?{query}"
    generated_dir = out_dir / "generated"
    ext = pathlib.Path(filename).suffix or ".mp4"
    local_path = generated_dir / f"comfy_source{ext}"
    try:
        _http_download(view_url, local_path, timeout_s=300)
    except Exception as ex:
        raise SystemExit(f"comfy media download failed: {type(ex).__name__}: {ex}")
    if (not local_path.exists()) or local_path.stat().st_size == 0:
        raise SystemExit("comfy download produced empty file")

    final_media_path = _ensure_video_from_comfy_media(media_path=local_path, out_dir=out_dir, job=job)
    relpath = str(final_media_path.resolve().relative_to(sandbox_root.resolve())).replace("\\", "/")
    print(f"INFO worker comfy media_downloaded={relpath}")
    return {
        "provider": "comfyui_video",
        "prompt_id": prompt_id,
        "media_filename": filename,
        "media_subfolder": subfolder,
        "media_type": media_type,
        "downloaded_relpath": str(local_path.resolve().relative_to(sandbox_root.resolve())).replace("\\", "/"),
        "output_relpath": relpath,
        "workflow_relpath": str(workflow_rel),
        "base_url": base_url,
    }


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


def build_audio_filter(duration: str) -> str:
    """
    Build deterministic audio filter chain.
    Default mode is fast (no loudnorm) to avoid multi-minute stalls on short renders.
    Enable loudnorm explicitly with CAF_ENABLE_LOUDNORM=1.
    """
    enable_loudnorm = os.environ.get("CAF_ENABLE_LOUDNORM", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    if enable_loudnorm:
        return (
            f"apad=pad_dur={duration},"
            f"atrim=0:{duration},"
            "loudnorm=I=-16:TP=-1.5:LRA=11,"
            "alimiter=limit=0.95"
        )
    return (
        f"apad=pad_dur={duration},"
        f"atrim=0:{duration},"
        "alimiter=limit=0.95"
    )


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
        "-preset",
        "slow",
        "-crf",
        "18",
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

    # Resolve demo asset aliases (for example flight_composite <-> fight_composite).
    alias_rel = resolve_alias_for_existing(sandbox_root=sandbox_root, relpath=str(p))
    if isinstance(alias_rel, str) and alias_rel:
        p = pathlib.Path(alias_rel)

    full_path = sandbox_root / p
    return full_path


def validate_safe_path(path: pathlib.Path, root: pathlib.Path) -> None:
    # Ensure path is within root
    # Py3.9+ has is_relative_to, but we can fallback for safety
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        raise ValueError(f"Path is strictly forbidden outside sandbox root: {path}")


def validate_safe_path_under(path: pathlib.Path, root: pathlib.Path, label: str) -> None:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        raise ValueError(f"{label} path forbidden outside {root}: {path}")


def resolve_project_relpath(rel_path_str: str, repo_root: pathlib.Path, sandbox_root: pathlib.Path) -> pathlib.Path:
    p = pathlib.Path(rel_path_str)
    if p.is_absolute():
        raise ValueError(f"Path must be relative: {rel_path_str}")
    if rel_path_str.startswith("sandbox/"):
        out = normalize_sandbox_path(rel_path_str, sandbox_root)
        validate_safe_path(out, sandbox_root)
        return out
    if rel_path_str.startswith("repo/"):
        out = (repo_root / rel_path_str).resolve()
        validate_safe_path_under(out, repo_root / "repo", "repo")
        return out
    raise ValueError(f"Unsupported relpath prefix (expected repo/ or sandbox/): {rel_path_str}")


def load_json_file(path: pathlib.Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as ex:
        raise SystemExit(f"Invalid JSON artifact: {path} ({ex})")


def load_retry_hook(
    *,
    job: dict,
    sandbox_root: pathlib.Path,
) -> dict[str, Any] | None:
    retry_plan_path_s = os.environ.get("CAF_RETRY_PLAN_PATH", "").strip()
    if not retry_plan_path_s:
        return None
    retry_plan_path = pathlib.Path(retry_plan_path_s)
    try:
        validate_safe_path(retry_plan_path, sandbox_root)
    except Exception:
        raise SystemExit(f"Unsafe retry plan path: {retry_plan_path}")
    if not retry_plan_path.exists():
        return None
    payload = load_json_file(retry_plan_path)
    if payload.get("version") != "retry_plan.v1":
        raise SystemExit("CAF_RETRY_PLAN_PATH must point to retry_plan.v1")
    if str(payload.get("job_id", "")) != str(job.get("job_id", "")):
        raise SystemExit("retry_plan job_id mismatch with current job")
    retry = payload.get("retry", {})
    if not isinstance(retry, dict):
        return None
    if retry.get("enabled") is not True:
        return None
    retry_type = str(retry.get("retry_type", "none"))
    if retry_type not in {"motion", "recast"}:
        return None
    seg_retry = retry.get("segment_retry", {})
    if not isinstance(seg_retry, dict):
        seg_retry = {"mode": "none", "target_segments": [], "trigger_metrics": []}
    mode = str(seg_retry.get("mode", "none"))
    targets = seg_retry.get("target_segments", [])
    if not isinstance(targets, list):
        targets = []
    triggers = seg_retry.get("trigger_metrics", [])
    if not isinstance(triggers, list):
        triggers = []
    provider_switch = retry.get("provider_switch", {})
    if not isinstance(provider_switch, dict):
        provider_switch = {}
    workflow_preset = retry.get("workflow_preset", {})
    if not isinstance(workflow_preset, dict):
        workflow_preset = {}
    switch_mode = str(provider_switch.get("mode", "none"))
    switch_current = provider_switch.get("current_provider")
    switch_next = provider_switch.get("next_provider")
    switch_index = provider_switch.get("provider_order_index")
    preset_mode = str(workflow_preset.get("mode", "none"))
    preset_id = workflow_preset.get("preset_id")
    workflow_id = workflow_preset.get("workflow_id")
    failure_class = workflow_preset.get("failure_class")
    parameter_overrides = workflow_preset.get("parameter_overrides")
    return {
        "retry_type": retry_type,
        "mode": mode,
        "target_segments": [str(x) for x in targets if isinstance(x, str)],
        "trigger_metrics": [str(x) for x in triggers if isinstance(x, str)],
        "provider_switch": {
            "mode": switch_mode,
            "current_provider": str(switch_current) if isinstance(switch_current, str) and switch_current else None,
            "next_provider": str(switch_next) if isinstance(switch_next, str) and switch_next else None,
            "provider_order_index": int(switch_index) if isinstance(switch_index, int) and switch_index >= 0 else None,
        },
        "workflow_preset": {
            "mode": preset_mode,
            "preset_id": str(preset_id) if isinstance(preset_id, str) and preset_id else None,
            "workflow_id": str(workflow_id) if isinstance(workflow_id, str) and workflow_id else None,
            "failure_class": str(failure_class) if isinstance(failure_class, str) and failure_class else None,
            "parameter_overrides": parameter_overrides if isinstance(parameter_overrides, dict) else {},
        },
        "provider_switch_env": {
            "mode": os.environ.get("CAF_RETRY_PROVIDER_SWITCH_MODE"),
            "current_provider": os.environ.get("CAF_RETRY_CURRENT_PROVIDER"),
            "next_provider": os.environ.get("CAF_RETRY_NEXT_PROVIDER"),
        },
        "retry_plan_relpath": str(retry_plan_path.resolve().relative_to(repo_root_from_here().resolve())).replace("\\", "/"),
        "attempt_id": os.environ.get("CAF_RETRY_ATTEMPT_ID"),
    }


def build_engine_policy_runtime(
    *,
    job: dict,
    retry_hook: dict[str, Any] | None,
    motion_constraints_runtime: list[dict[str, Any]] | None = None,
    post_process_runtime: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    gen = job.get("generation_policy")
    if not isinstance(gen, dict):
        return None
    motion = gen.get("motion_constraints")
    post = gen.get("post_process_order")
    motion_list = [str(x) for x in motion if isinstance(x, str)] if isinstance(motion, list) else []
    post_list = [str(x) for x in post if isinstance(x, str)] if isinstance(post, list) else []
    if not motion_list and not post_list:
        return None

    policy_runtime: dict[str, Any] = {
        "route_mode": gen.get("route_mode"),
        "selected_video_provider": gen.get("selected_video_provider"),
        "selected_frame_provider": gen.get("selected_frame_provider"),
        "motion_constraints": motion_constraints_runtime
        if isinstance(motion_constraints_runtime, list)
        else [{"constraint_id": cid, "status": "not_applied_worker_policy_only"} for cid in motion_list],
        "post_process_order": post_process_runtime
        if isinstance(post_process_runtime, list)
        else [{"step_id": sid, "status": "not_applied_worker_policy_only"} for sid in post_list],
    }
    if isinstance(retry_hook, dict):
        policy_runtime["retry_provider_switch"] = retry_hook.get("provider_switch")
        policy_runtime["retry_workflow_preset"] = retry_hook.get("workflow_preset")
    return policy_runtime


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


def emit_media_stack_artifacts(
    job: dict,
    out_dir: pathlib.Path,
    sandbox_root: pathlib.Path,
    render_result: dict[str, Any],
    result_path: pathlib.Path,
) -> dict[str, Any]:
    job_id = str(job["job_id"])
    final_mp4 = pathlib.Path(render_result["outputs"]["final_mp4"])
    final_srt = pathlib.Path(render_result["outputs"]["final_srt"])

    frames_dir = out_dir / "frames"
    audio_dir = out_dir / "audio"
    edit_dir = out_dir / "edit"
    render_dir = out_dir / "render"
    for d in [frames_dir, audio_dir, edit_dir, render_dir]:
        d.mkdir(parents=True, exist_ok=True)

    duration = int(job["video"]["length_seconds"])
    fps = int(job["video"]["fps"])
    video_duration = get_video_duration(final_mp4)
    sample_duration = video_duration if video_duration > 0.0 else float(duration)
    frame_times = sorted(
        set([0.0, max(0.0, sample_duration / 2.0), max(0.0, sample_duration - 0.2)])
    )
    frame_files: list[str] = []
    for idx, t in enumerate(frame_times, start=1):
        out_png = frames_dir / f"frame_{idx:04d}.png"
        cmd = [
            "ffmpeg",
            "-y",
            "-ss",
            f"{t:.3f}",
            "-i",
            str(final_mp4),
            "-frames:v",
            "1",
            "-update",
            "1",
            "-vf",
            "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black",
            str(out_png),
        ]
        run_subprocess(cmd)
        frame_files.append(str(out_png))

    frame_manifest = {
        "version": "frame_manifest.v1",
        "job_id": job_id,
        "stage": "frame",
        "source_video": str(final_mp4),
        "fps": fps,
        "sample_times_sec": [round(x, 3) for x in frame_times],
        "frames": frame_files,
        "frame_count": len(frame_files),
        "hashes": {pathlib.Path(p).name: sha256_file(pathlib.Path(p)) for p in frame_files},
    }
    frame_manifest_path = frames_dir / "frame_manifest.v1.json"
    atomic_write_json(frame_manifest_path, frame_manifest)

    mix_wav = audio_dir / "mix.wav"
    audio_extract_cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(final_mp4),
        "-vn",
        "-acodec",
        "pcm_s16le",
        "-ar",
        "48000",
        "-ac",
        "2",
        str(mix_wav),
    ]
    run_subprocess(audio_extract_cmd)

    audio_manifest = {
        "version": "audio_manifest.v1",
        "job_id": job_id,
        "stage": "audio",
        "audio_source": render_result.get("audio_source"),
        "audio_asset_path": render_result.get("audio_asset_path"),
        "mix_wav": str(mix_wav),
        "mix_wav_sha256": sha256_file(mix_wav),
        "sample_rate_hz": 48000,
        "channels": 2,
    }
    audio_manifest_path = audio_dir / "audio_manifest.v1.json"
    atomic_write_json(audio_manifest_path, audio_manifest)

    shots = job.get("shots", [])
    timeline_segments = []
    for idx, shot in enumerate(shots):
        start_sec = float(shot.get("t", 0))
        if idx + 1 < len(shots):
            end_sec = float(shots[idx + 1].get("t", duration))
        else:
            end_sec = float(duration)
        if end_sec < start_sec:
            end_sec = start_sec
        timeline_segments.append(
            {
                "index": idx,
                "start_sec": round(start_sec, 3),
                "end_sec": round(end_sec, 3),
                "visual": str(shot.get("visual", "")),
                "action": str(shot.get("action", "")),
                "caption": str(shot.get("caption", "")),
            }
        )
    timeline = {
        "version": "timeline.v1",
        "job_id": job_id,
        "stage": "edit",
        "duration_sec": duration,
        "segments": timeline_segments,
        "captions_count": len(job.get("captions", [])),
    }
    timeline_path = edit_dir / "timeline.v1.json"
    atomic_write_json(timeline_path, timeline)

    render_manifest = {
        "version": "render_manifest.v1",
        "job_id": job_id,
        "stage": "render",
        "final_mp4": str(final_mp4),
        "final_srt": str(final_srt),
        "result_json": str(result_path),
        "hashes": {
            "final_mp4_sha256": sha256_file(final_mp4),
            "final_srt_sha256": sha256_file(final_srt),
        },
        "ffmpeg_cmd": render_result.get("ffmpeg_cmd"),
        "ffmpeg_cmd_executed": render_result.get("ffmpeg_cmd_executed"),
    }
    render_manifest_path = render_dir / "render_manifest.v1.json"
    atomic_write_json(render_manifest_path, render_manifest)

    return {
        "frame_manifest": str(frame_manifest_path),
        "audio_manifest": str(audio_manifest_path),
        "timeline": str(timeline_path),
        "render_manifest": str(render_manifest_path),
    }


def execute_segment_stitch_runtime(
    *,
    job: dict,
    repo_root: pathlib.Path,
    sandbox_root: pathlib.Path,
    out_dir: pathlib.Path,
    source_mp4: pathlib.Path,
    retry_hook: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    segment_cfg = job.get("segment_stitch")
    if not isinstance(segment_cfg, dict):
        return None
    if segment_cfg.get("enabled") is False:
        return None

    plan_relpath = segment_cfg.get("plan_relpath")
    if not isinstance(plan_relpath, str) or not plan_relpath.strip():
        raise SystemExit("segment_stitch.plan_relpath must be a non-empty string")
    plan_path = resolve_project_relpath(plan_relpath, repo_root, sandbox_root)
    if not plan_path.exists():
        raise SystemExit(f"segment_stitch plan not found: {plan_path}")

    plan = load_json_file(plan_path)
    if plan.get("version") != "segment_stitch_plan.v1":
        raise SystemExit("segment_stitch.plan_relpath must point to segment_stitch_plan.v1")
    segments = plan.get("segments", [])
    if not isinstance(segments, list) or not segments:
        raise SystemExit("segment_stitch plan requires non-empty segments array")

    fps = int(job.get("video", {}).get("fps", 30) or 30)
    seg_dir = out_dir / "segments"
    seg_dir.mkdir(parents=True, exist_ok=True)
    # Remove stale runtime artifacts from prior attempts to avoid false consumers.
    for stale in seg_dir.glob("seg_*.mp4"):
        try:
            stale.unlink()
        except OSError:
            pass
    for stale in (seg_dir / "stitched_preview.mp4", seg_dir / "stitched_preview.mp4.tmp.mp4"):
        if stale.exists():
            try:
                stale.unlink()
            except OSError:
                pass

    ordered = sorted(
        [s for s in segments if isinstance(s, dict)],
        key=lambda s: int(s.get("order", 0)),
    )
    if not ordered:
        raise SystemExit("segment_stitch plan has no valid segment entries")

    retry_hook_applied: dict[str, Any] | None = None
    if isinstance(retry_hook, dict) and retry_hook.get("retry_type") in {"motion", "recast"}:
        mode = str(retry_hook.get("mode", "none"))
        targets = set(retry_hook.get("target_segments", []) or [])
        if mode == "retry_selected" and targets:
            ordered = [s for s in ordered if str(s.get("segment_id", "")) in targets]
            if not ordered:
                raise SystemExit("retry_hook selected zero segments after filtering")
        retry_hook_applied = {
            "retry_type": str(retry_hook.get("retry_type")),
            "mode": mode,
            "target_segments": sorted(list(targets)),
            "trigger_metrics": sorted([str(x) for x in (retry_hook.get("trigger_metrics", []) or [])]),
            "retry_plan_relpath": retry_hook.get("retry_plan_relpath"),
            "attempt_id": retry_hook.get("attempt_id"),
        }

    seg_outputs: list[dict[str, Any]] = []
    skipped_segments: list[dict[str, Any]] = []
    seg_paths: list[pathlib.Path] = []
    seg_durations: list[float] = []
    effective_order: list[dict[str, Any]] = []
    source_duration = max(0.0, get_video_duration(source_mp4))
    for seg in ordered:
        seg_id = str(seg.get("segment_id", "")).strip()
        if not seg_id:
            raise SystemExit("segment_stitch segment_id is required")
        start = float(seg.get("start_sec", 0.0))
        end = float(seg.get("end_sec", 0.0))
        if end <= start:
            raise SystemExit(f"segment_stitch {seg_id} has end_sec <= start_sec")
        if source_duration > 0.0:
            if start >= source_duration:
                skipped_segments.append(
                    {
                        "segment_id": seg_id,
                        "reason": "out_of_source_range",
                        "start_sec": round(start, 3),
                        "end_sec": round(end, 3),
                    }
                )
                continue
            end = min(end, source_duration)
        if (end - start) < 0.05:
            skipped_segments.append(
                {
                    "segment_id": seg_id,
                    "reason": "too_short_after_clamp",
                    "start_sec": round(start, 3),
                    "end_sec": round(end, 3),
                }
            )
            continue
        out_mp4 = seg_dir / f"{seg_id}.mp4"
        cmd = [
            "ffmpeg",
            "-y",
            "-ss",
            f"{start:.3f}",
            "-to",
            f"{end:.3f}",
            "-i",
            str(source_mp4),
            "-r",
            str(fps),
            "-c:v",
            "libx264",
            "-preset",
            "slow",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-an",
            "-movflags",
            "+faststart",
            str(out_mp4),
        ]
        run_ffmpeg(cmd, out_mp4)
        if (not out_mp4.exists()) or out_mp4.stat().st_size < 1024:
            skipped_segments.append(
                {
                    "segment_id": seg_id,
                    "reason": "empty_output",
                    "start_sec": round(start, 3),
                    "end_sec": round(end, 3),
                }
            )
            continue
        seg_paths.append(out_mp4)
        seg_durations.append(max(0.001, end - start))
        effective_order.append(seg)
        seg_outputs.append(
            {
                "segment_id": seg_id,
                "start_sec": round(start, 3),
                "end_sec": round(end, 3),
                "output_relpath": str(out_mp4.resolve().relative_to(repo_root.resolve())).replace("\\", "/"),
                "duration_sec": round(end - start, 3),
            }
        )

    if not seg_paths:
        raise SystemExit("segment_stitch produced zero valid segments after clamping")

    seams: list[dict[str, Any]] = []
    for idx in range(1, len(effective_order)):
        cur = effective_order[idx]
        prev = effective_order[idx - 1]
        seam = cur.get("seam") if isinstance(cur.get("seam"), dict) else {}
        method = str(seam.get("method") or "hard_cut")
        blend_frames = int(seam.get("blend_frames", 0) or 0)
        transition = "none"
        if method == "crossfade":
            transition = "fade"
        elif method == "motion_blend":
            transition = "smoothleft"
        seams.append(
            {
                "from_segment": str(prev.get("segment_id")),
                "to_segment": str(cur.get("segment_id")),
                "method": method if method in ("hard_cut", "crossfade", "motion_blend") else "hard_cut",
                "blend_frames": max(0, min(60, blend_frames)),
                "transition": transition,
            }
        )

    if retry_hook_applied is not None and retry_hook_applied.get("retry_type") == "motion":
        for seam in seams:
            if seam["method"] == "hard_cut":
                seam["method"] = "crossfade"
                seam["transition"] = "fade"
            seam["blend_frames"] = max(int(seam["blend_frames"]), 6)

    stitched_preview = seg_dir / "stitched_preview.mp4"
    has_non_hard = any(s["method"] != "hard_cut" for s in seams)
    if not has_non_hard or len(seg_paths) == 1:
        concat_file = seg_dir / "concat_inputs.txt"
        concat_lines = [f"file '{p.name}'" for p in seg_paths]
        atomic_write_text(concat_file, "\n".join(concat_lines) + "\n")
        concat_cmd = [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_file),
            "-c:v",
            "libx264",
            "-preset",
            "slow",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-an",
            "-movflags",
            "+faststart",
            str(stitched_preview),
        ]
        run_ffmpeg(concat_cmd, stitched_preview)
    else:
        # Deterministic xfade chain when seam methods request blending.
        inputs: list[str] = []
        for p in seg_paths:
            inputs += ["-i", str(p)]
        chains: list[str] = []
        acc = seg_durations[0]
        prev_label = "[0:v]"
        for idx in range(1, len(seg_paths)):
            seam = seams[idx - 1]
            method = seam["method"]
            transition = "fade" if method == "crossfade" else ("smoothleft" if method == "motion_blend" else "fade")
            blend_frames = int(seam["blend_frames"])
            dur = max(0.03, min(0.7, blend_frames / max(1, fps)))
            offset = max(0.0, acc - dur)
            out_label = f"[x{idx}]"
            chains.append(
                f"{prev_label}[{idx}:v]xfade=transition={transition}:duration={dur:.3f}:offset={offset:.3f}{out_label}"
            )
            prev_label = out_label
            acc = acc + seg_durations[idx] - dur
        filter_complex = ";".join(chains)
        xfade_cmd = [
            "ffmpeg",
            "-y",
            *inputs,
            "-filter_complex",
            filter_complex,
            "-map",
            prev_label,
            "-c:v",
            "libx264",
            "-preset",
            "slow",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-an",
            "-movflags",
            "+faststart",
            str(stitched_preview),
        ]
        run_ffmpeg(xfade_cmd, stitched_preview)

    report = {
        "version": "segment_stitch_report.v1",
        "job_id": str(job.get("job_id")),
        "plan_relpath": plan_relpath,
        "segments_dir": str(seg_dir.resolve().relative_to(repo_root.resolve())).replace("\\", "/"),
        "stitched_preview": str(stitched_preview.resolve().relative_to(repo_root.resolve())).replace("\\", "/"),
        "segments": seg_outputs,
        "skipped_segments": skipped_segments,
        "seams": seams,
        "retry_hook_applied": retry_hook_applied,
    }
    report_path = seg_dir / "segment_stitch_report.v1.json"
    atomic_write_json(report_path, report)
    return {
        "segments_dir": str(seg_dir),
        "stitched_preview": str(stitched_preview),
        "report": str(report_path),
    }


def emit_segment_debug_exports(
    *,
    job: dict,
    repo_root: pathlib.Path,
    out_dir: pathlib.Path,
    final_mp4: pathlib.Path,
    segment_runtime: dict[str, Any] | None,
    media_stack_paths: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not isinstance(segment_runtime, dict):
        return None
    report_path_s = segment_runtime.get("report")
    if not isinstance(report_path_s, str):
        return None
    report_path = pathlib.Path(report_path_s)
    if not report_path.exists():
        return None
    report = load_json_file(report_path)
    if report.get("version") != "segment_stitch_report.v1":
        return None

    debug_dir = out_dir / "debug"
    seams_dir = debug_dir / "seams"
    debug_dir.mkdir(parents=True, exist_ok=True)
    seams_dir.mkdir(parents=True, exist_ok=True)

    segments = report.get("segments", [])
    seams = report.get("seams", [])
    seg_by_id: dict[str, dict[str, Any]] = {}
    if isinstance(segments, list):
        for seg in segments:
            if isinstance(seg, dict):
                sid = seg.get("segment_id")
                if isinstance(sid, str):
                    seg_by_id[sid] = seg

    seam_previews: list[dict[str, Any]] = []
    if isinstance(seams, list):
        for idx, seam in enumerate(seams, start=1):
            if not isinstance(seam, dict):
                continue
            from_id = str(seam.get("from_segment", ""))
            to_id = str(seam.get("to_segment", ""))
            to_seg = seg_by_id.get(to_id)
            if not to_seg:
                continue
            seam_center = float(to_seg.get("start_sec", 0.0))
            clip_start = max(0.0, seam_center - 0.4)
            clip_end = max(clip_start + 0.2, seam_center + 0.4)
            preview = seams_dir / f"seam_{idx:03d}.mp4"
            cmd = [
                "ffmpeg",
                "-y",
                "-ss",
                f"{clip_start:.3f}",
                "-to",
                f"{clip_end:.3f}",
                "-i",
                str(final_mp4),
                "-c:v",
                "libx264",
                "-preset",
                "slow",
                "-crf",
                "18",
                "-pix_fmt",
                "yuv420p",
                "-an",
                "-movflags",
                "+faststart",
                str(preview),
            ]
            run_ffmpeg(cmd, preview)
            seam_previews.append(
                {
                    "seam_index": idx,
                    "from_segment": from_id,
                    "to_segment": to_id,
                    "preview_relpath": str(preview.resolve().relative_to(repo_root.resolve())).replace("\\", "/"),
                    "start_sec": round(clip_start, 3),
                    "end_sec": round(clip_end, 3),
                }
            )

    motion_curve_path = debug_dir / "motion_curve_snapshot.v1.json"
    motion_curve_payload: dict[str, Any] = {
        "version": "motion_curve_snapshot.v1",
        "job_id": str(job.get("job_id")),
        "available": False,
        "reason": "opencv_not_available",
        "points": [],
    }
    if cv2 is not None and np is not None:
        cap = cv2.VideoCapture(str(final_mp4))
        if cap.isOpened():
            fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
            step = 2
            ok, prev = cap.read()
            points: list[dict[str, float]] = []
            i = 0
            if ok:
                prev_g = cv2.cvtColor(cv2.resize(prev, (160, 90)), cv2.COLOR_BGR2GRAY)
                while True:
                    ok, frame = cap.read()
                    if not ok:
                        break
                    i += 1
                    if i % step != 0:
                        continue
                    g = cv2.cvtColor(cv2.resize(frame, (160, 90)), cv2.COLOR_BGR2GRAY)
                    score = float(np.mean(np.abs(g.astype("float32") - prev_g.astype("float32"))))
                    t = float((i + 1) / max(1.0, fps))
                    points.append({"t_sec": round(t, 3), "score": round(score, 6)})
                    prev_g = g
            cap.release()
            motion_curve_payload = {
                "version": "motion_curve_snapshot.v1",
                "job_id": str(job.get("job_id")),
                "available": True,
                "reason": "",
                "sample_step_frames": step,
                "points": points,
            }
        else:
            motion_curve_payload["reason"] = "video_open_failed"
    atomic_write_json(motion_curve_path, motion_curve_payload)

    checkpoint_strip_relpath = None
    frame_manifest_path = None
    if isinstance(media_stack_paths, dict):
        fm = media_stack_paths.get("frame_manifest")
        if isinstance(fm, str):
            frame_manifest_path = pathlib.Path(fm)
    if frame_manifest_path is not None and frame_manifest_path.exists() and cv2 is not None and np is not None:
        frame_manifest = load_json_file(frame_manifest_path)
        frames = frame_manifest.get("frames", [])
        imgs = []
        if isinstance(frames, list):
            for p in frames[:3]:
                if not isinstance(p, str):
                    continue
                im = cv2.imread(p)
                if im is None:
                    continue
                im = cv2.resize(im, (360, 640))
                imgs.append(im)
        if imgs:
            strip = imgs[0]
            for im in imgs[1:]:
                sep = np.zeros((strip.shape[0], 8, 3), dtype=strip.dtype)
                strip = np.hstack([strip, sep, im])
            strip_path = debug_dir / "checkpoint_strip.png"
            cv2.imwrite(str(strip_path), strip)
            checkpoint_strip_relpath = str(strip_path.resolve().relative_to(repo_root.resolve())).replace("\\", "/")

    manifest_path = debug_dir / "segment_debug_manifest.v1.json"
    manifest = {
        "version": "segment_debug_manifest.v1",
        "job_id": str(job.get("job_id")),
        "source_final_mp4": str(final_mp4.resolve().relative_to(repo_root.resolve())).replace("\\", "/"),
        "debug_dir": str(debug_dir.resolve().relative_to(repo_root.resolve())).replace("\\", "/"),
        "inputs": {
            "segment_stitch_report_relpath": str(report_path.resolve().relative_to(repo_root.resolve())).replace("\\", "/"),
            "frame_manifest_relpath": str(frame_manifest_path.resolve().relative_to(repo_root.resolve())).replace("\\", "/")
            if frame_manifest_path is not None and frame_manifest_path.exists()
            else None,
        },
        "seam_previews": seam_previews,
        "motion_curve_snapshot_relpath": str(motion_curve_path.resolve().relative_to(repo_root.resolve())).replace("\\", "/"),
        "checkpoint_strip_relpath": checkpoint_strip_relpath,
    }
    atomic_write_json(manifest_path, manifest)
    return {
        "manifest": str(manifest_path),
        "debug_dir": str(debug_dir),
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

    wm_width = max(MIN_WM_WIDTH, min(math.floor(VIDEO_W * SCALE_FACTOR), MAX_WM_WIDTH))
    wm_input_idx = next_input_idx
    inputs.extend(["-i", str(wm_path)])
    next_input_idx += 1
    filter_chain.append(f"[{wm_input_idx}:v]format=rgba,colorchannelmixer=aa={OPACITY},scale={wm_width}:-1[wm]")

    # Now we have [bg] at 1080x1920
    out_mp4 = out_dir / "final.mp4"
    srt_path = out_dir / "final.srt"
    
    subtitles_status = prepare_subtitles_file(job, srt_path, sandbox_root)
    
    current_bg_ref = "[bg]"
    
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
    
    audio_filter = build_audio_filter(duration)

    output_args = [
        "-map", "[out]",
        "-map", f"{audio_input_idx}:a:0",
        "-t", str(duration),
        "-r", str(fps),
        "-c:v", "libx264",
        "-preset", "slow", "-crf", "18",
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
    
    subtitles_status = prepare_subtitles_file(job, srt_path, sandbox_root)

    # Get video dimensions (height unused but returned for completeness/logging if needed)
    video_w, _ = get_video_dims(bg)
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

    wm_input_idx = next_input_idx
    inputs.extend(["-i", str(wm_path)])
    next_input_idx += 1

    # Helper to build filter string
    def build_filter(include_subtitles: bool):
        f = []
        f.append(f"[{wm_input_idx}:v]format=rgba,colorchannelmixer=aa={OPACITY},scale={wm_width}:-1[wm]")
        current_bg_ref = f"[{current_bg_idx}:v]"

        # Apply subtitles (optional).
        # Only use subtitles if the file is non-empty/valid
        if include_subtitles and srt_path.exists() and srt_path.stat().st_size > 0:
            # Strict validation
            validate_safe_path(srt_path, sandbox_root)
            
            safe_srt_path = escape_ffmpeg_path(srt_path)
            
            f.append(f"{current_bg_ref}subtitles=filename='{safe_srt_path}'[v_sub]")
            current_bg_ref = "[v_sub]"

        f.append(f"{current_bg_ref}[wm]overlay=W-w-{PADDING_PX}:H-h-{PADDING_PX}[out]")
        return ";".join(f)

    # Strategy: Try with subtitles first (if they exist). If that fails (e.g. no libass),
    # fallback to clean render without subtitles.
    
    final_cmd_logical = []
    final_cmd_executed = []
    failed_cmd = None
    
    audio_filter = build_audio_filter(duration)
    
    output_args = [
        "-map", "[out]",
        "-map", f"{audio_input_idx}:a:0",
        "-t", duration,
        "-r", fps,
        "-c:v", "libx264",
        "-preset", "slow", "-crf", "18",
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
            print("Attempting render with subtitles...")
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
    
    # Attempt 2: clean render (if Attempt 1 failed or no subtitles)
    if not out_mp4.exists():
        full_filter = build_filter(include_subtitles=False)
        cmd = ["ffmpeg", "-y"] + inputs + ["-filter_complex", full_filter] + output_args
        print("Rendering clean video...")
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


def render_dance_swap(job: dict, sandbox_root: pathlib.Path, out_dir: pathlib.Path, wm_path: pathlib.Path) -> dict:
    """Deterministic dance-swap render path using validated slot contracts."""
    job_id = job["job_id"]
    ds = resolve_dance_swap_contracts(job, sandbox_root)
    source_video = normalize_sandbox_path(ds["source_video_relpath"], sandbox_root)
    fg_asset = normalize_sandbox_path(ds["foreground_asset_relpath"], sandbox_root)
    validate_safe_path(source_video, sandbox_root)
    validate_safe_path(fg_asset, sandbox_root)
    if not source_video.exists():
        raise SystemExit(f"Dance Swap source not found: {source_video}")
    if not fg_asset.exists():
        raise SystemExit(f"Dance Swap foreground not found: {fg_asset}")

    out_mp4 = out_dir / "final.mp4"
    srt_path = out_dir / "final.srt"
    subtitles_status = prepare_subtitles_file(job, srt_path, sandbox_root)

    fps_i = int(job["video"].get("fps", 30) or 30)
    duration_i = int(job["video"]["length_seconds"])
    duration = str(duration_i)
    fps = str(fps_i)

    slot = ds["slot"]
    slot_x = int(slot["x"])
    slot_y = int(slot["y"])
    slot_w = max(1, int(slot["w"]))
    slot_h = max(1, int(slot["h"]))
    slot_dx = float(slot.get("dx", 0.0) or 0.0)
    slot_dy = float(slot.get("dy", 0.0) or 0.0)
    slot_hz = max(0.1, float(slot.get("hz", 1.6) or 1.6))

    inputs = ["-i", str(source_video), "-i", str(fg_asset), "-i", str(wm_path)]
    source_idx, fg_idx, wm_idx = 0, 1, 2
    audio_source = "bg_audio" if has_audio_stream(source_video) else "silence"
    audio_input_idx = source_idx
    if audio_source == "silence":
        inputs.extend(["-f", "lavfi", "-t", duration, "-i", "anullsrc=channel_layout=stereo:sample_rate=48000"])
        audio_input_idx = 3

    video_w, _ = get_video_dims(source_video)
    wm_width = max(MIN_WM_WIDTH, min(math.floor(video_w * SCALE_FACTOR), MAX_WM_WIDTH))
    fg_core = (
        f"[{fg_idx}:v]scale={slot_w}:{slot_h}:force_original_aspect_ratio=decrease,"
        f"pad={slot_w}:{slot_h}:(ow-iw)/2:(oh-ih)/2:color=black@0[fgfit]"
    )
    overlay_x = f"{slot_x}+{slot_dx:.3f}*sin(2*PI*{slot_hz:.6f}*t)"
    overlay_y = f"{slot_y}+{slot_dy:.3f}*cos(2*PI*{slot_hz:.6f}*t)"
    wm_core = f"[{wm_idx}:v]format=rgba,colorchannelmixer=aa={OPACITY},scale={wm_width}:-1[wm]"

    attempt_burn = (subtitles_status == "ready_to_burn" and ffmpeg_has_subtitles_filter())
    if subtitles_status == "ready_to_burn" and not ffmpeg_has_subtitles_filter():
        subtitles_status = "skipped_missing_subtitles_filter"

    def _build_filter(with_subs: bool) -> str:
        parts = [fg_core]
        base_ref = f"[{source_idx}:v]"
        if with_subs:
            safe_srt = escape_ffmpeg_path(srt_path)
            parts.append(f"{base_ref}subtitles=filename='{safe_srt}'[v_sub]")
            base_ref = "[v_sub]"
        parts.append(f"{base_ref}[fgfit]overlay=x='{overlay_x}':y='{overlay_y}':format=auto[v_swap]")
        parts.append(wm_core)
        parts.append(f"[v_swap][wm]overlay=W-w-{PADDING_PX}:H-h-{PADDING_PX}[out]")
        return ";".join(parts)

    audio_filter = build_audio_filter(duration)
    output_args = [
        "-map", "[out]",
        "-map", f"{audio_input_idx}:a:0",
        "-t", duration,
        "-r", fps,
        "-c:v", "libx264",
        "-preset", "slow", "-crf", "18",
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

    final_cmd_logical: list[str] = []
    final_cmd_executed: list[str] = []
    failed_cmd: list[str] | None = None
    if attempt_burn:
        try:
            cmd = ["ffmpeg", "-y"] + inputs + ["-filter_complex", _build_filter(True)] + output_args
            final_cmd_executed = run_ffmpeg(cmd, out_mp4)
            final_cmd_logical = cmd
            subtitles_status = "burned"
        except subprocess.CalledProcessError:
            subtitles_status = "failed_ffmpeg_subtitles"
            failed_cmd = cmd
            if out_mp4.exists():
                out_mp4.unlink()

    if not out_mp4.exists():
        cmd = ["ffmpeg", "-y"] + inputs + ["-filter_complex", _build_filter(False)] + output_args
        final_cmd_executed = run_ffmpeg(cmd, out_mp4)
        final_cmd_logical = cmd

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
            "bg_path": str(source_video),
            "wm_path": str(wm_path),
            "video_width": video_w,
            "wm_width": wm_width,
            "padding": PADDING_PX,
            "opacity": OPACITY,
        },
        "audio_source": audio_source,
        "audio_asset_path": None,
        "has_bg_audio": audio_source == "bg_audio",
        "subtitles_status": subtitles_status,
        "ffmpeg_cmd": final_cmd_logical,
        "ffmpeg_cmd_executed": final_cmd_executed,
        "failed_ffmpeg_cmd": failed_cmd,
        "dance_swap_runtime": ds,
    }


def enforce_motion_constraints(job: dict, repo_root: pathlib.Path) -> list[dict[str, Any]]:
    gen = job.get("generation_policy")
    if not isinstance(gen, dict):
        return []
    motion = gen.get("motion_constraints")
    motion_list = [str(x) for x in motion if isinstance(x, str)] if isinstance(motion, list) else []
    out: list[dict[str, Any]] = []
    for cid in motion_list:
        if cid != "openpose_constraint":
            out.append({"constraint_id": cid, "status": "skipped_unknown_constraint"})
            continue
        mc = job.get("motion_contract")
        if not isinstance(mc, dict):
            raise SystemExit("motion_constraints=openpose_constraint requires motion_contract block")
        relpath = mc.get("relpath")
        if not isinstance(relpath, str) or not relpath.startswith("repo/"):
            raise SystemExit("motion_contract.relpath must be repo-relative for openpose_constraint")
        contract_path = repo_root / relpath
        if not contract_path.exists():
            raise SystemExit(f"motion_contract missing for openpose_constraint: {contract_path}")
        data = load_json_file(contract_path)
        version = str(data.get("version", ""))
        if version != "pose_checkpoints.v1":
            raise SystemExit("openpose_constraint requires pose_checkpoints.v1 motion contract")
        out.append({"constraint_id": cid, "status": "applied", "contract_relpath": relpath})
    return out


def apply_post_process_order(
    *,
    job: dict,
    final_mp4: pathlib.Path,
    fps: int,
) -> list[dict[str, Any]]:
    gen = job.get("generation_policy")
    if not isinstance(gen, dict):
        return []
    post = gen.get("post_process_order")
    post_list = [str(x) for x in post if isinstance(x, str)] if isinstance(post, list) else []
    out: list[dict[str, Any]] = []
    for step_id in post_list:
        if step_id == "rife_film_post":
            # Deterministic temporal smoothing fallback using ffmpeg minterpolate.
            tmp = final_mp4.with_suffix(".rife.tmp.mp4")
            cmd = [
                "ffmpeg",
                "-y",
                "-i",
                str(final_mp4),
                "-filter:v",
                f"minterpolate=fps={fps}:mi_mode=mci:mc_mode=aobmc:vsbmc=1",
                "-map",
                "0:v:0",
                "-map",
                "0:a:0?",
                "-c:v",
                "libx264",
                "-preset",
                "slow",
                "-crf",
                "18",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "copy",
                "-movflags",
                "+faststart",
                str(tmp),
            ]
            run_ffmpeg(cmd, tmp)
            tmp.replace(final_mp4)
            out.append({"step_id": step_id, "status": "applied", "impl": "ffmpeg_minterpolate"})
            continue
        if step_id == "esrgan_selective_post":
            # Deterministic lightweight sharpening/denoise approximation in absence of ESRGAN runtime.
            tmp = final_mp4.with_suffix(".esrgan.tmp.mp4")
            cmd = [
                "ffmpeg",
                "-y",
                "-i",
                str(final_mp4),
                "-filter:v",
                "hqdn3d=1.2:1.2:2.0:2.0,unsharp=5:5:0.7:5:5:0.0",
                "-map",
                "0:v:0",
                "-map",
                "0:a:0?",
                "-c:v",
                "libx264",
                "-preset",
                "slow",
                "-crf",
                "18",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "copy",
                "-movflags",
                "+faststart",
                str(tmp),
            ]
            run_ffmpeg(cmd, tmp)
            tmp.replace(final_mp4)
            out.append({"step_id": step_id, "status": "applied", "impl": "ffmpeg_sharpen_denoise"})
            continue
        out.append({"step_id": step_id, "status": "skipped_unknown_step"})
    return out


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
    comfy_generation: dict[str, Any] | None = None
    motion_constraints_runtime: list[dict[str, Any]] = []
    post_process_runtime: list[dict[str, Any]] = []

    gen_policy = job.get("generation_policy") if isinstance(job.get("generation_policy"), dict) else {}
    selected_video_provider = str(gen_policy.get("selected_video_provider", "")).strip()
    comfy_required = selected_video_provider == "comfyui_video" or isinstance(job.get("comfyui"), dict)
    if comfy_required:
        comfy_generation = generate_comfyui_video_asset(
            job=job,
            repo_root=root,
            sandbox_root=sandbox_root,
            out_dir=out_dir,
        )
        comfy_rel = comfy_generation.get("output_relpath") if isinstance(comfy_generation, dict) else None
        if isinstance(comfy_rel, str) and comfy_rel.strip():
            job.setdefault("render", {})
            job["render"]["background_asset"] = comfy_rel.strip()

    # Enforce declared motion constraints before lane execution.
    motion_constraints_runtime = enforce_motion_constraints(job, root)

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
        else:
            raise SystemExit(f"Unsupported template recipe_id: {recipe_id}")

    elif lane == "image_motion":
        # PR19 Lane B Logic
        render_result = render_image_motion(job, sandbox_root, out_dir, wm_path)
    elif lane == "dance_swap":
        render_result = render_dance_swap(job, sandbox_root, out_dir, wm_path)

    else:
        # Legacy / Default behavior (Lane A, Lane B, or no lane)
        # Use simple standard render directly
        render_result = render_standard(job, sandbox_root, out_dir, wm_path)

    # Execute deterministic post-processing policy on rendered output.
    post_process_runtime = apply_post_process_order(
        job=job,
        final_mp4=pathlib.Path(render_result["outputs"]["final_mp4"]),
        fps=int(job["video"].get("fps", 30) or 30),
    )
    # Refresh final hash after post-processing mutations.
    render_result["hashes"]["final_mp4_sha256"] = sha256_file(pathlib.Path(render_result["outputs"]["final_mp4"]))

    retry_hook = load_retry_hook(job=job, sandbox_root=sandbox_root)
    segment_runtime = execute_segment_stitch_runtime(
        job=job,
        repo_root=root,
        sandbox_root=sandbox_root,
        out_dir=out_dir,
        source_mp4=pathlib.Path(render_result["outputs"]["final_mp4"]),
        retry_hook=retry_hook,
    )

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
    if comfy_generation is not None:
        final_result["comfy_generation"] = comfy_generation
    
    if lane == "template_remix":
        final_result["template_id"] = template_id
        final_result["recipe_id"] = recipe_id
    elif lane == "image_motion":
        final_result["motion_preset"] = render_result["motion_preset"]
        final_result["seed_frames_count"] = render_result["seed_frames_count"]
    elif lane == "dance_swap":
        final_result["dance_swap_runtime"] = render_result.get("dance_swap_runtime")
    
    if render_result.get("failed_ffmpeg_cmd"):
        final_result["failed_ffmpeg_cmd"] = render_result["failed_ffmpeg_cmd"]

    media_stack_paths = emit_media_stack_artifacts(
        job=job,
        out_dir=out_dir,
        sandbox_root=sandbox_root,
        render_result=render_result,
        result_path=result_path,
    )
    final_result["media_stack"] = media_stack_paths
    if segment_runtime is not None:
        final_result["segment_stitch_runtime"] = segment_runtime
    if retry_hook is not None:
        final_result["worker_retry_hook"] = retry_hook
    engine_policy_runtime = build_engine_policy_runtime(
        job=job,
        retry_hook=retry_hook,
        motion_constraints_runtime=motion_constraints_runtime,
        post_process_runtime=post_process_runtime,
    )
    if engine_policy_runtime is not None:
        final_result["engine_policy_runtime"] = engine_policy_runtime
    debug_exports = emit_segment_debug_exports(
        job=job,
        repo_root=root,
        out_dir=out_dir,
        final_mp4=pathlib.Path(render_result["outputs"]["final_mp4"]),
        segment_runtime=segment_runtime,
        media_stack_paths=media_stack_paths,
    )
    if debug_exports is not None:
        final_result["segment_debug_exports"] = debug_exports

    atomic_write_text(result_path, json.dumps(final_result, indent=2, sort_keys=True))

    print("Wrote", render_result["outputs"]["final_mp4"])
    print("Wrote", render_result["outputs"]["final_srt"])
    print("Wrote", result_path)


if __name__ == "__main__":
    main()
