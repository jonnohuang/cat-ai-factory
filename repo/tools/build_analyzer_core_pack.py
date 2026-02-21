#!/usr/bin/env python3
"""
build_analyzer_core_pack.py

Deterministic analyzer-core pack builder for PR-34.7e.
Generates planner-side artifacts:
- beat_grid.v1
- pose_checkpoints.v1
- keyframe_checkpoints.v1
- caf.video_reverse_prompt.v1
- frame_labels.v1
- segment_stitch_plan.v1
"""

from __future__ import annotations

import argparse
import datetime as dt
import importlib.metadata as importlib_metadata
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
from typing import Any, Dict, List, Optional, Tuple


def eprint(*args: Any) -> None:
    print(*args, file=sys.stderr)


def _repo_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parents[2]


def _utc_now() -> str:
    return (
        dt.datetime.now(dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _kebab(value: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return s or "analysis"


def _run(cmd: List[str]) -> str:
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if p.returncode != 0:
        raise RuntimeError(
            f"command failed ({p.returncode}): {' '.join(cmd)}\n{p.stderr.strip()}"
        )
    return p.stdout


def _load_json(path: pathlib.Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _save_json(path: pathlib.Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def _safe_rel(path: pathlib.Path, root: pathlib.Path) -> str:
    return str(path.resolve().relative_to(root.resolve())).replace("\\", "/")


def _pkg_version(pkg: str) -> str:
    try:
        return str(importlib_metadata.version(pkg))
    except Exception:
        return "unknown"


def _collect_tool_versions() -> Dict[str, str]:
    return {
        "python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "opencv": _pkg_version("opencv-python-headless"),
        "mediapipe": _pkg_version("mediapipe"),
        "movenet": _pkg_version("tensorflow"),
        "librosa": _pkg_version("librosa"),
        "scenedetect": _pkg_version("scenedetect"),
    }


def _load_movenet_interpreter() -> tuple[Any, Any, Any] | tuple[None, None, None]:
    """Best-effort MoveNet loader (optional)."""
    model_path = os.environ.get("CAF_MOVENET_MODEL_PATH", "").strip()
    if not model_path:
        return None, None, None
    p = pathlib.Path(model_path)
    if not p.exists():
        return None, None, None
    try:
        import tensorflow as tf  # type: ignore

        interp = tf.lite.Interpreter(model_path=str(p))
        interp.allocate_tensors()
        in_details = interp.get_input_details()
        out_details = interp.get_output_details()
        return interp, in_details, out_details
    except Exception:
        return None, None, None


def _infer_movenet_signature(
    frame_bgr: Any,
    interp: Any,
    in_details: Any,
    out_details: Any,
) -> tuple[list[float], float]:
    import cv2  # type: ignore
    import numpy as np  # type: ignore

    # MoveNet single-pose expects 192x192 RGB tensor.
    rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
    inp = cv2.resize(rgb, (192, 192), interpolation=cv2.INTER_AREA)
    inp = np.expand_dims(inp, axis=0)
    in_dtype = in_details[0]["dtype"]
    if in_dtype == np.float32:
        inp = inp.astype(np.float32)
    else:
        inp = inp.astype(in_dtype)
    interp.set_tensor(in_details[0]["index"], inp)
    interp.invoke()
    out = interp.get_tensor(out_details[0]["index"])
    # Shape usually [1,1,17,3] => (y, x, score)
    kp = out[0, 0]
    idxs = [0, 5, 6, 11, 12, 9, 10]  # nose, shoulders, hips, wrists
    sig: list[float] = []
    vis: list[float] = []
    for i in idxs:
        y, x, score = kp[i]
        sig.extend([round(float(x), 4), round(float(y), 4)])
        vis.append(float(score))
    conf = round(sum(vis) / max(1, len(vis)), 3)
    return sig, conf


def _probe(path: pathlib.Path) -> Dict[str, Any]:
    out = _run(
        [
            "ffprobe",
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_streams",
            "-show_format",
            str(path),
        ]
    )
    data = json.loads(out)
    vstream = None
    for s in data.get("streams", []):
        if s.get("codec_type") == "video":
            vstream = s
            break
    if not isinstance(vstream, dict):
        raise RuntimeError("no video stream")

    duration = float(
        vstream.get("duration") or data.get("format", {}).get("duration") or 0
    )
    fr = vstream.get("avg_frame_rate") or vstream.get("r_frame_rate") or "30/1"
    fps = 30.0
    if isinstance(fr, str) and "/" in fr:
        n, d = fr.split("/", 1)
        try:
            n_f = float(n)
            d_f = float(d)
            if d_f > 0:
                fps = n_f / d_f
        except Exception:
            pass
    codec = str(vstream.get("codec_name") or "unknown")
    return {
        "duration": max(0.001, duration),
        "fps": max(1.0, fps),
        "width": int(vstream.get("width") or 0),
        "height": int(vstream.get("height") or 0),
        "codec": codec,
    }


def _extract_audio_beats(
    path: pathlib.Path,
) -> Tuple[Optional[float], List[float], str]:
    try:
        import librosa  # type: ignore
    except Exception:
        return None, [], "librosa_unavailable"

    tmp_wav = pathlib.Path(tempfile.mkstemp(prefix="caf-audio-", suffix=".wav")[1])
    try:
        _run(
            [
                "ffmpeg",
                "-y",
                "-v",
                "error",
                "-i",
                str(path),
                "-ac",
                "1",
                "-ar",
                "22050",
                str(tmp_wav),
            ]
        )
        y, sr = librosa.load(str(tmp_wav), sr=22050, mono=True)
        tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
        beat_times = librosa.frames_to_time(beat_frames, sr=sr)
        beats = [round(float(t), 3) for t in beat_times if float(t) >= 0]
        bpm = float(tempo) if tempo is not None else None
        return bpm, beats, "librosa"
    except Exception:
        return None, [], "librosa_failed"
    finally:
        try:
            tmp_wav.unlink(missing_ok=True)
        except Exception:
            pass


def _hex_from_rgb_triplet(rgb: Tuple[int, int, int]) -> str:
    return f"#{rgb[0]:02X}{rgb[1]:02X}{rgb[2]:02X}"


def _classify_camera_mode(flow_rows: List[Dict[str, float]]) -> Tuple[str, float]:
    if not flow_rows:
        return "unknown", 0.0
    avg_mag = sum(r["mag"] for r in flow_rows) / len(flow_rows)
    avg_dx = sum(r["dx"] for r in flow_rows) / len(flow_rows)
    avg_dy = sum(r["dy"] for r in flow_rows) / len(flow_rows)

    if avg_mag < 0.08:
        return "locked", 0.92
    ax = abs(avg_dx)
    ay = abs(avg_dy)
    if ax > ay * 1.25:
        conf = max(0.5, min(0.95, ax / max(ax + ay, 1e-6)))
        return "pan", round(conf, 3)
    if ay > ax * 1.25:
        conf = max(0.5, min(0.95, ay / max(ax + ay, 1e-6)))
        return "tilt", round(conf, 3)
    return "mixed", 0.58


def _extract_video_signals(
    path: pathlib.Path,
    fps: float,
) -> Tuple[
    List[Dict[str, float]], List[Tuple[float, List[float], float]], str, Dict[str, Any]
]:
    try:
        import cv2  # type: ignore
        import numpy as np  # type: ignore
    except Exception:
        return (
            [],
            [],
            "opencv_unavailable",
            {
                "brightness_bucket": "unknown",
                "luma_mean": None,
                "palette_top_hex": ["#808080"],
                "camera_movement_mode": "unknown",
                "camera_movement_confidence": 0.0,
            },
        )

    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        return (
            [],
            [],
            "opencv_open_failed",
            {
                "brightness_bucket": "unknown",
                "luma_mean": None,
                "palette_top_hex": ["#808080"],
                "camera_movement_mode": "unknown",
                "camera_movement_confidence": 0.0,
            },
        )

    # Sample at 6Hz deterministically.
    frame_step = max(1, int(round(max(fps, 1.0) / 6.0)))
    frame_idx = 0
    prev_gray = None
    motion: List[Dict[str, float]] = []
    pose_rows: List[Tuple[float, List[float], float]] = []
    luma_values: List[float] = []
    palette_bins: Dict[Tuple[int, int, int], int] = {}

    mp_pose = None
    pose_engine = None
    pose_mode = "cv_fallback"
    try:
        import mediapipe as mp  # type: ignore

        mp_pose = mp.solutions.pose
        pose_engine = mp_pose.Pose(static_image_mode=False, model_complexity=1)
        pose_mode = "mediapipe_pose"
    except Exception:
        pose_engine = None
    movenet_interp = None
    movenet_in = None
    movenet_out = None
    if pose_engine is None:
        movenet_interp, movenet_in, movenet_out = _load_movenet_interpreter()
        if movenet_interp is not None:
            pose_mode = "movenet"

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            if frame_idx % frame_step != 0:
                frame_idx += 1
                continue

            t = frame_idx / max(fps, 1.0)
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            gray_small = cv2.resize(gray, (256, 256), interpolation=cv2.INTER_AREA)
            luma_values.append(float(gray_small.mean()))

            # Deterministic coarse palette histogram (16-level RGB bins).
            rgb_small = cv2.cvtColor(
                cv2.resize(frame, (64, 64), interpolation=cv2.INTER_AREA),
                cv2.COLOR_BGR2RGB,
            )
            flat = rgb_small.reshape(-1, 3)
            for px in flat[::8]:
                r = int((int(px[0]) // 16) * 16 + 8)
                g = int((int(px[1]) // 16) * 16 + 8)
                b = int((int(px[2]) // 16) * 16 + 8)
                key = (max(0, min(255, r)), max(0, min(255, g)), max(0, min(255, b)))
                palette_bins[key] = palette_bins.get(key, 0) + 1

            if prev_gray is not None:
                flow = cv2.calcOpticalFlowFarneback(
                    prev_gray,
                    gray_small,
                    None,
                    0.5,
                    3,
                    15,
                    3,
                    5,
                    1.2,
                    0,
                )
                mag, _ang = cv2.cartToPolar(flow[..., 0], flow[..., 1])
                motion_val = float(mag.mean())
                dx = float(flow[..., 0].mean())
                dy = float(flow[..., 1].mean())
                motion.append({"t": t, "mag": motion_val, "dx": dx, "dy": dy})
            prev_gray = gray_small

            if pose_engine is not None:
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                result = pose_engine.process(rgb)
                if result.pose_landmarks and mp_pose is not None:
                    idxs = [0, 11, 12, 23, 24, 15, 16]
                    sig: List[float] = []
                    vis: List[float] = []
                    for i in idxs:
                        lm = result.pose_landmarks.landmark[i]
                        sig.extend([round(float(lm.x), 4), round(float(lm.y), 4)])
                        vis.append(float(getattr(lm, "visibility", 1.0)))
                    conf = round(sum(vis) / max(1, len(vis)), 3)
                    pose_rows.append((t, sig, conf))
                else:
                    pose_rows.append((t, [0.0] * 14, 0.0))
            elif movenet_interp is not None:
                try:
                    sig, conf = _infer_movenet_signature(
                        frame, movenet_interp, movenet_in, movenet_out
                    )
                    pose_rows.append((t, sig, conf))
                except Exception:
                    pose_rows.append((t, [0.0] * 14, 0.0))
            else:
                vec = (
                    cv2.resize(gray, (8, 8), interpolation=cv2.INTER_AREA)
                    .flatten()
                    .astype("float32")
                )
                vec = (vec / 255.0).tolist()
                sig = [round(float(x), 4) for x in vec[:16]]
                pose_rows.append((t, sig, 0.5))

            frame_idx += 1
    finally:
        cap.release()
        if pose_engine is not None:
            try:
                pose_engine.close()
            except Exception:
                pass

    camera_mode, camera_conf = _classify_camera_mode(motion)
    luma_mean = (
        round(sum(luma_values) / max(1, len(luma_values)), 3) if luma_values else None
    )
    if luma_mean is None:
        brightness = "unknown"
    elif luma_mean < 85:
        brightness = "dark"
    elif luma_mean > 170:
        brightness = "bright"
    else:
        brightness = "mid"
    top_palette = sorted(palette_bins.items(), key=lambda row: (-row[1], row[0]))[:3]
    palette_top_hex = [_hex_from_rgb_triplet(rgb) for rgb, _count in top_palette] or [
        "#808080"
    ]

    visual_facts = {
        "brightness_bucket": brightness,
        "luma_mean": luma_mean,
        "palette_top_hex": palette_top_hex,
        "camera_movement_mode": camera_mode,
        "camera_movement_confidence": float(camera_conf),
    }
    return motion, pose_rows, pose_mode, visual_facts


def _pick_motion_peaks(
    series: List[Dict[str, float]], duration: float, limit: int = 6
) -> List[float]:
    if not series:
        return [0.0, round(duration, 3)]
    vals = [row["mag"] for row in series]
    mean_v = sum(vals) / max(1, len(vals))
    peaks: List[Tuple[float, float]] = []
    for i in range(1, len(series) - 1):
        t = series[i]["t"]
        v = series[i]["mag"]
        if v >= series[i - 1]["mag"] and v >= series[i + 1]["mag"] and v >= mean_v:
            peaks.append((v, t))
    peaks.sort(key=lambda x: (-x[0], x[1]))
    picked = sorted({round(t, 3) for _, t in peaks[:limit]})
    if 0.0 not in picked:
        picked.insert(0, 0.0)
    if round(duration, 3) not in picked:
        picked.append(round(duration, 3))
    return picked


def _scene_segments(
    path: pathlib.Path, duration: float
) -> Tuple[List[Tuple[float, float]], str]:
    try:
        from scenedetect import ContentDetector, SceneManager, open_video  # type: ignore
    except Exception:
        return [(0.0, round(duration, 3))], "scenedetect_unavailable"

    try:
        video = open_video(str(path))
        manager = SceneManager()
        manager.add_detector(ContentDetector())
        manager.detect_scenes(video, show_progress=False)
        scenes = manager.get_scene_list()
        out: List[Tuple[float, float]] = []
        for start, end in scenes:
            s = round(float(start.get_seconds()), 3)
            e = round(float(end.get_seconds()), 3)
            if e > s:
                out.append((s, e))
        if not out:
            out = [(0.0, round(duration, 3))]
        return out, "scenedetect"
    except Exception:
        return [(0.0, round(duration, 3))], "scenedetect_failed"


def _build_segments_from_shots(
    shots: List[Tuple[float, float]], max_len: float = 3.0
) -> List[Tuple[float, float]]:
    segs: List[Tuple[float, float]] = []
    for s, e in shots:
        cur = s
        while (e - cur) > max_len:
            segs.append((round(cur, 3), round(cur + max_len, 3)))
            cur += max_len
        if e > cur:
            segs.append((round(cur, 3), round(e, 3)))
    if not segs and shots:
        segs = [(round(shots[0][0], 3), round(shots[0][1], 3))]
    return segs


def _motion_phase(motion_intensity: float) -> str:
    if motion_intensity >= 0.67:
        return "high"
    if motion_intensity >= 0.34:
        return "medium"
    return "low"


def _composition_from_camera(camera_mode: str) -> str:
    if camera_mode in {"push", "pull"}:
        return "close"
    if camera_mode in {"pan", "tilt", "mixed"}:
        return "wide"
    if camera_mode == "locked":
        return "mid"
    return "unknown"


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Build deterministic analyzer core pack"
    )
    parser.add_argument("--input", required=True, help="Input video path")
    parser.add_argument("--analysis-id", help="Analysis id (kebab-case)")
    parser.add_argument(
        "--out-dir", default="repo/canon/demo_analyses", help="Output directory"
    )
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv[1:])

    root = _repo_root()
    in_path = pathlib.Path(args.input).resolve()
    if not in_path.exists():
        eprint(f"ERROR: input not found: {in_path}")
        return 1

    analysis_id = _kebab(args.analysis_id or in_path.stem)
    out_dir = (root / args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    beat_path = out_dir / f"{analysis_id}.beat_grid.v1.json"
    pose_path = out_dir / f"{analysis_id}.pose_checkpoints.v1.json"
    keyframe_path = out_dir / f"{analysis_id}.keyframe_checkpoints.v1.json"
    reverse_path = out_dir / f"{analysis_id}.caf.video_reverse_prompt.v1.json"
    frame_labels_path = out_dir / f"{analysis_id}.frame_labels.v1.json"
    segment_plan_path = out_dir / f"{analysis_id}.segment_stitch_plan.v1.json"

    if (not args.overwrite) and any(
        p.exists()
        for p in [
            beat_path,
            pose_path,
            keyframe_path,
            reverse_path,
            frame_labels_path,
            segment_plan_path,
        ]
    ):
        eprint("ERROR: output files exist; use --overwrite")
        return 1

    meta = _probe(in_path)
    duration = float(meta["duration"])
    fps = float(meta["fps"])

    bpm, beat_times, beat_source = _extract_audio_beats(in_path)
    motion_series, pose_rows, pose_source, visual_facts = _extract_video_signals(
        in_path, fps
    )
    scene_shots, scene_source = _scene_segments(in_path, duration)
    tool_versions = _collect_tool_versions()

    if not beat_times:
        beat_times = _pick_motion_peaks(motion_series, duration, limit=12)

    beat_doc = {
        "version": "beat_grid.v1",
        "analysis_id": analysis_id,
        "source_video_relpath": _safe_rel(in_path, root),
        "bpm_estimate": round(float(bpm or 120.0), 3),
        "beats": [
            {"t_sec": round(float(t), 3), "strength": 0.8}
            for t in beat_times
            if 0 <= float(t) <= duration
        ],
    }

    # Select up to 8 checkpoints by motion peaks, fallback to evenly sampled rows.
    checkpoint_times = _pick_motion_peaks(motion_series, duration, limit=8)
    pose_lookup = pose_rows if pose_rows else [(0.0, [0.0] * 16, 0.0)]
    pose_doc_rows = []
    for t in checkpoint_times:
        nearest = min(pose_lookup, key=lambda row: abs(row[0] - t))
        pose_doc_rows.append(
            {
                "t_sec": round(float(t), 3),
                "pose_signature": nearest[1],
                "confidence": round(float(nearest[2]), 3),
            }
        )
    pose_doc = {
        "version": "pose_checkpoints.v1",
        "analysis_id": analysis_id,
        "source_video_relpath": _safe_rel(in_path, root),
        "model": pose_source,
        "tool_versions": tool_versions,
        "checkpoints": pose_doc_rows,
    }

    keyframes = []
    for i, (s, _e) in enumerate(scene_shots, start=1):
        keyframes.append(
            {
                "t_sec": round(float(s), 3),
                "label": f"scene-{i:03d}-start",
                "tags": ["scene", "segment", "dance"],
            }
        )
    keyframe_doc = {
        "version": "keyframe_checkpoints.v1",
        "analysis_id": analysis_id,
        "source_video_relpath": _safe_rel(in_path, root),
        "keyframes": keyframes,
    }

    rel_beat = _safe_rel(beat_path, root)
    rel_pose = _safe_rel(pose_path, root)
    rel_key = _safe_rel(keyframe_path, root)

    motion_default = 0.6
    if motion_series:
        vals = [row["mag"] for row in motion_series]
        vmin = min(vals)
        vmax = max(vals)
        rng = max(1e-6, vmax - vmin)

        def norm(v: float) -> float:
            return max(0.0, min(1.0, (v - vmin) / rng))

    else:

        def norm(_v: float) -> float:
            return motion_default

    shot_docs = []
    for i, (s, e) in enumerate(scene_shots, start=1):
        near = 0.0
        if motion_series:
            near = min(motion_series, key=lambda row: abs(row["t"] - s))["mag"]
        shot_camera = str(visual_facts.get("camera_movement_mode") or "unknown")
        if shot_camera not in {
            "locked",
            "pan",
            "tilt",
            "push",
            "pull",
            "mixed",
            "unknown",
        }:
            shot_camera = "unknown"
        palette = visual_facts.get("palette_top_hex", [])
        palette_hint = "#808080"
        if isinstance(palette, list) and palette:
            p0 = palette[min(i - 1, len(palette) - 1)]
            if isinstance(p0, str) and p0.startswith("#") and len(p0) == 7:
                palette_hint = p0
        shot_docs.append(
            {
                "shot_id": f"shot_{i:03d}",
                "start_sec": round(float(s), 3),
                "end_sec": round(float(max(s + 0.001, e)), 3),
                "camera": shot_camera,
                "camera_confidence": round(
                    float(visual_facts.get("camera_movement_confidence") or 0.0), 3
                ),
                "motion_intensity": round(float(norm(near)), 3),
                "brightness_luma_mean": round(
                    float(visual_facts.get("luma_mean") or 0.0), 3
                ),
                "palette_hint": palette_hint,
            }
        )

    reverse_doc = {
        "version": "caf.video_reverse_prompt.v1",
        "analysis_id": analysis_id,
        "source_video_relpath": _safe_rel(in_path, root),
        "tool_versions": tool_versions,
        "truth": {
            "beat_grid_ref": rel_beat,
            "pose_checkpoints_ref": rel_pose,
            "keyframe_checkpoints_ref": rel_key,
            "visual_facts": {
                "camera_movement_mode": visual_facts.get(
                    "camera_movement_mode", "unknown"
                ),
                "camera_movement_confidence": round(
                    float(visual_facts.get("camera_movement_confidence") or 0.0), 3
                ),
                "brightness_bucket": visual_facts.get("brightness_bucket", "unknown"),
                "luma_mean": (
                    round(float(visual_facts.get("luma_mean")), 3)
                    if isinstance(visual_facts.get("luma_mean"), (int, float))
                    else None
                ),
                "palette_top_hex": visual_facts.get("palette_top_hex", ["#808080"]),
            },
            "shots": shot_docs,
        },
        "prompt_packages": {
            "text2video": {
                "prompt": "Locked-camera dance sequence with beat-aligned movement and stable temporal consistency.",
                "negative": ["flicker", "identity drift", "camera shake"],
            },
            "image2video": {
                "prompt": "Preserve key poses at checkpoint timestamps and return to a loop-safe end pose.",
                "negative": ["hard jump cuts", "background drift", "costume mismatch"],
            },
        },
        "confidence": {
            "measured_truth": 0.85,
            "inferred_semantics": 0.6,
            "notes": f"beat={beat_source}; scene={scene_source}; pose={pose_source}",
        },
    }

    frame_rows: List[Dict[str, Any]] = []
    for i, shot in enumerate(shot_docs, start=1):
        motion_intensity = float(shot.get("motion_intensity", 0.0))
        camera_mode = str(shot.get("camera") or "unknown")
        brightness_bucket = str(visual_facts.get("brightness_bucket") or "unknown")
        palette_hint = str(shot.get("palette_hint") or "#808080")
        action_summary = (
            f"{_motion_phase(motion_intensity)} motion dance beat; "
            f"camera {camera_mode if camera_mode in {'locked', 'pan', 'tilt', 'push', 'pull', 'mixed'} else 'unknown'}."
        )
        frame_rows.append(
            {
                "frame_id": f"frame_{i:03d}",
                "shot_id": shot.get("shot_id"),
                "t_sec": shot.get("start_sec"),
                "facts": {
                    "camera_mode": camera_mode,
                    "brightness_bucket": brightness_bucket,
                    "palette_hint": palette_hint,
                    "motion_intensity": motion_intensity,
                },
                "labels": {
                    "subject_focus": "group" if motion_intensity >= 0.6 else "hero",
                    "motion_phase": _motion_phase(motion_intensity),
                    "composition": _composition_from_camera(camera_mode),
                    "action_summary": action_summary[:160],
                },
                "confidence": {
                    "facts": 0.92,
                    "enrichment": 0.58,
                },
                "uncertainty": [],
            }
        )

    frame_labels_doc = {
        "version": "frame_labels.v1",
        "analysis_id": analysis_id,
        "source_video_relpath": _safe_rel(in_path, root),
        "tool_versions": tool_versions,
        "authority": {
            "reverse_prompt_ref": _safe_rel(reverse_path, root),
            "keyframe_checkpoints_ref": rel_key,
        },
        "policy": {
            "facts_only_or_unknown": True,
            "enrichment_provider": "rule_based",
        },
        "frames": frame_rows,
    }

    segment_ranges = _build_segments_from_shots(scene_shots, max_len=3.0)
    segments = []
    stitch_order = []
    for i, (s, e) in enumerate(segment_ranges, start=1):
        seg_id = f"seg_{i:03d}"
        stitch_order.append(seg_id)
        seg: Dict[str, Any] = {
            "segment_id": seg_id,
            "order": i,
            "start_sec": round(float(s), 3),
            "end_sec": round(float(max(s + 0.001, e)), 3),
            "retry_budget": 2,
        }
        if i > 1:
            seg["seam"] = {
                "prev_segment_id": f"seg_{i-1:03d}",
                "blend_frames": 6,
                "method": "crossfade",
            }
        segments.append(seg)

    seg_plan = {
        "version": "segment_stitch_plan.v1",
        "plan_id": f"{analysis_id}-segplan",
        "analysis_id": analysis_id,
        "source_video_relpath": _safe_rel(in_path, root),
        "constraints": {
            "camera_lock": True,
            "background_lock": True,
            "max_shot_length_sec": 3.0,
        },
        "segments": segments,
        "stitch_order": stitch_order,
    }

    _save_json(beat_path, beat_doc)
    _save_json(pose_path, pose_doc)
    _save_json(keyframe_path, keyframe_doc)
    _save_json(reverse_path, reverse_doc)
    _save_json(frame_labels_path, frame_labels_doc)
    _save_json(segment_plan_path, seg_plan)

    print(f"OK beat_grid: {beat_path}")
    print(f"OK pose_checkpoints: {pose_path}")
    print(f"OK keyframe_checkpoints: {keyframe_path}")
    print(f"OK reverse_prompt: {reverse_path}")
    print(f"OK frame_labels: {frame_labels_path}")
    print(f"OK segment_plan: {segment_plan_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
