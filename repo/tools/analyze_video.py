#!/usr/bin/env python3
"""
analyze_video.py

Deterministic planner-side/offline analyzer that converts a video input into
`video_analysis.v1` metadata.

This tool does not write media outputs and does not change Worker authority.

Usage:
  python -m repo.tools.analyze_video \
    --input path/to/video.mp4 \
    --output repo/canon/demo_analyses/my-analysis.json \
    --lane-hint dance_swap \
    --tag loopable \
    --index repo/canon/demo_analyses/video_analysis_index.v1.json
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import pathlib
import re
import subprocess
import sys
from typing import Any


def eprint(*args: Any) -> None:
    print(*args, file=sys.stderr)


def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _repo_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parents[2]


def _kebab(text: str) -> str:
    s = text.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s or "analysis"


def _fingerprint_sha256_16(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def _run(cmd: list[str]) -> str:
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"command failed ({p.returncode}): {' '.join(cmd)}\n{p.stderr.strip()}")
    return p.stdout


def _probe_video(path: pathlib.Path) -> dict[str, float]:
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
    if vstream is None:
        raise RuntimeError("no video stream found")

    duration = 0.0
    if "duration" in vstream and vstream["duration"] is not None:
        duration = float(vstream["duration"])
    elif "format" in data and data["format"].get("duration") is not None:
        duration = float(data["format"]["duration"])
    if duration <= 0:
        raise RuntimeError("could not determine video duration")

    fps = 30.0
    fr = vstream.get("avg_frame_rate") or vstream.get("r_frame_rate")
    if isinstance(fr, str) and "/" in fr:
        n, d = fr.split("/", 1)
        try:
            n_f = float(n)
            d_f = float(d)
            if d_f > 0 and n_f > 0:
                fps = n_f / d_f
        except ValueError:
            pass
    elif isinstance(fr, (int, float)) and float(fr) > 0:
        fps = float(fr)

    frame_count = int(round(duration * fps))
    width = int(vstream.get("width", 0) or 0)
    height = int(vstream.get("height", 0) or 0)

    return {
        "duration": duration,
        "fps": fps,
        "frame_count": frame_count,
        "width": width,
        "height": height,
    }


def _duration_bucket(duration: float) -> str:
    if duration <= 15:
        return "short_0_15"
    if duration <= 30:
        return "short_16_30"
    return "short_31_60"


def _build_beats(duration: float) -> list[dict[str, Any]]:
    # Deterministic segmentation: 1/2/3 beats by duration bucket.
    if duration <= 4:
        n = 1
    elif duration <= 10:
        n = 2
    else:
        n = 3

    beats: list[dict[str, Any]] = []
    step = duration / n
    for i in range(n):
        start = round(i * step, 3)
        end = round((i + 1) * step, 3)
        if i == n - 1:
            end = round(duration, 3)
        if end <= start:
            end = round(start + 0.001, 3)
        beats.append(
            {
                "start_sec": start,
                "end_sec": end,
                "label": f"beat-{i + 1:02d}",
            }
        )
    return beats


def _energy_curve(duration: float, frame_count: int) -> str:
    density = frame_count / max(duration, 0.001)
    if density >= 50:
        return "spike"
    if density >= 30:
        return "build"
    if density >= 20:
        return "wave"
    return "flat"


def _default_tags(duration: float) -> list[str]:
    tags = ["analyzed", "loopable", "short-form"]
    if duration <= 15:
        tags.append("snappy")
    elif duration <= 30:
        tags.append("medium-cut")
    else:
        tags.append("long-cut")
    return sorted(set(tags))


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _opencv_extract_profile(path: pathlib.Path, fps: float, duration: float) -> dict[str, Any] | None:
    try:
        import cv2  # type: ignore
    except Exception:
        return None

    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        return None

    sample_hz = 6.0
    frame_step = max(1, int(round(max(fps, 1.0) / sample_hz)))
    frame_idx = 0
    prev_gray = None
    motion_series: list[tuple[float, float]] = []
    edge_series: list[float] = []

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            if frame_idx % frame_step != 0:
                frame_idx += 1
                continue

            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            if prev_gray is not None:
                diff = cv2.absdiff(gray, prev_gray)
                motion = float(diff.mean())
                t = frame_idx / max(fps, 1.0)
                motion_series.append((t, motion))
            prev_gray = gray

            edges = cv2.Canny(gray, 64, 128)
            edge_density = float((edges > 0).mean())
            edge_series.append(edge_density)
            frame_idx += 1
    finally:
        cap.release()

    if not motion_series:
        return None

    # Deterministic beat picks from top local maxima.
    values = [m for _, m in motion_series]
    mean_motion = sum(values) / len(values)
    candidates: list[tuple[float, float]] = []
    for i in range(1, len(motion_series) - 1):
        t, v = motion_series[i]
        if v >= motion_series[i - 1][1] and v >= motion_series[i + 1][1] and v > mean_motion:
            candidates.append((v, t))

    if not candidates:
        candidates = [(v, t) for t, v in motion_series]

    # Pick 1-3 beats by duration bucket, deterministic ordering.
    if duration <= 4:
        n = 1
    elif duration <= 10:
        n = 2
    else:
        n = 3
    candidates.sort(key=lambda x: (-x[0], x[1]))
    picked = sorted([t for _, t in candidates[:n]])

    beats: list[dict[str, Any]] = []
    last = 0.0
    for i, t in enumerate(picked):
        end = _clamp(t, 0.001, duration)
        if end <= last:
            end = _clamp(last + 0.001, 0.001, duration)
        beats.append(
            {
                "start_sec": round(last, 3),
                "end_sec": round(end, 3),
                "label": f"beat-{i + 1:02d}",
            }
        )
        last = end
    if duration - last > 0.01:
        beats.append(
            {
                "start_sec": round(last, 3),
                "end_sec": round(duration, 3),
                "label": f"beat-{len(beats) + 1:02d}",
            }
        )

    avg_edge = sum(edge_series) / max(len(edge_series), 1)
    avg_motion = mean_motion
    if avg_motion > 12:
        shot_pattern = ["wide", "tracking"]
    elif avg_motion > 6:
        shot_pattern = ["medium", "tracking"]
    elif avg_edge > 0.12:
        shot_pattern = ["close", "static"]
    else:
        shot_pattern = ["medium", "static"]

    confidence = _clamp(0.55 + (mean_motion / 100.0), 0.55, 0.9)

    return {
        "beats": beats,
        "shot_pattern": shot_pattern,
        "seamless_confidence": round(confidence, 2),
        "motion_notes": f"OpenCV profile extracted with {sample_hz:.0f}Hz sampling.",
    }


def _build_analysis(
    *,
    input_path: pathlib.Path,
    analysis_id: str,
    source_type: str,
    reference_label: str,
    lane_hints: list[str],
    tags: list[str],
    meta: dict[str, float],
    opencv_profile: dict[str, Any] | None,
) -> dict[str, Any]:
    duration = float(meta["duration"])
    fps = float(meta["fps"])

    end_sec = max(duration - (1.0 / max(fps, 1.0)), 0.001)
    if end_sec <= 0:
        end_sec = duration
    if end_sec <= 0:
        end_sec = 0.001

    summary = f"Auto-analysis: {round(duration, 2)}s, {round(fps, 2)}fps, {int(meta['width'])}x{int(meta['height'])}."
    if len(summary) > 280:
        summary = summary[:277] + "..."

    beats = _build_beats(duration)
    shot_pattern = ["medium", "static"]
    motion_notes = f"Auto-derived from metadata; review manually if needed (fps={round(fps,2)})."
    seamless_confidence = 0.75

    if opencv_profile is not None:
        beats = opencv_profile["beats"]
        shot_pattern = opencv_profile["shot_pattern"]
        motion_notes = opencv_profile["motion_notes"]
        seamless_confidence = float(opencv_profile["seamless_confidence"])

    return {
        "version": "video_analysis.v1",
        "analysis_id": analysis_id,
        "analyzed_at": _utc_now(),
        "source": {
            "source_type": source_type,
            "reference_label": reference_label,
            "content_fingerprint": _fingerprint_sha256_16(input_path),
            "copyright_safe_metadata_only": True,
        },
        "pattern": {
            "lane_hints": sorted(set(lane_hints)),
            "duration_bucket": _duration_bucket(duration),
            "tags": sorted(set(tags)),
            "choreography": {
                "beats": beats,
                "energy_curve": _energy_curve(duration, int(meta["frame_count"])),
            },
            "camera": {
                "shot_pattern": shot_pattern,
                "motion_notes": motion_notes,
            },
            "looping": {
                "loop_start_sec": 0.0,
                "loop_end_sec": round(end_sec, 3),
                "seamless_confidence": seamless_confidence,
            },
        },
        "summary": summary,
        "safety": {
            "no_embedded_copyright_media": True,
            "notes": "Metadata only; generated by offline analyzer tool.",
        },
    }


def _load_json(path: pathlib.Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _save_json(path: pathlib.Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def _relpath_from_repo(path: pathlib.Path) -> str:
    root = _repo_root()
    rp = path.resolve().relative_to(root.resolve())
    return str(rp).replace("\\", "/")


def _update_index(
    *,
    index_path: pathlib.Path,
    analysis: dict[str, Any],
    relpath: str,
    priority: int,
    quality_score: float,
) -> None:
    if index_path.exists():
        data = _load_json(index_path)
    else:
        data = {
            "version": "video_analysis_index.v1",
            "generated_at": _utc_now(),
            "analyses": [],
        }

    entries = [e for e in data.get("analyses", []) if e.get("analysis_id") != analysis["analysis_id"]]
    entries.append(
        {
            "analysis_id": analysis["analysis_id"],
            "relpath": relpath,
            "priority": priority,
            "quality_score": quality_score,
            "tags": analysis["pattern"]["tags"],
            "lane_hints": analysis["pattern"]["lane_hints"],
            "duration_bucket": analysis["pattern"]["duration_bucket"],
            "summary": analysis.get("summary", ""),
        }
    )
    # Deterministic order.
    entries.sort(key=lambda x: (-int(x.get("priority", 0)), str(x.get("analysis_id", ""))))
    data["analyses"] = entries
    data["generated_at"] = _utc_now()
    _save_json(index_path, data)


def _validate(path: pathlib.Path) -> None:
    cmd = [sys.executable, "-m", "repo.tools.validate_video_analysis", str(path)]
    _run(cmd)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Deterministic offline video analyzer for CAF PR-32.1")
    parser.add_argument("--input", required=True, help="Path to input video")
    parser.add_argument("--output", required=True, help="Path to output video_analysis.v1 JSON")
    parser.add_argument("--analysis-id", help="Kebab-case analysis id (default: derived from input filename)")
    parser.add_argument(
        "--source-type",
        default="demo_reference",
        choices=["demo_reference", "public_reference", "internal_output"],
        help="Source type label for metadata",
    )
    parser.add_argument("--reference-label", help="Human-readable source label")
    parser.add_argument(
        "--lane-hint",
        action="append",
        dest="lane_hints",
        choices=["ai_video", "image_motion", "template_remix", "dance_swap", "mixed"],
        help="Repeatable lane hint (defaults to template_remix)",
    )
    parser.add_argument("--tag", action="append", dest="tags", help="Repeatable kebab-case tag")
    parser.add_argument("--index", help="Optional video_analysis_index.v1.json path to upsert entry")
    parser.add_argument("--priority", type=int, default=50, help="Index priority [0..100]")
    parser.add_argument("--quality-score", type=float, default=0.75, help="Index quality score [0..1]")
    parser.add_argument(
        "--disable-opencv",
        action="store_true",
        help="Disable OpenCV analysis path and use ffprobe-only deterministic fallback.",
    )
    parser.add_argument("--no-validate", action="store_true", help="Skip post-write schema+semantic validation")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing output file")
    args = parser.parse_args(argv[1:])

    input_path = pathlib.Path(args.input).resolve()
    output_path = pathlib.Path(args.output).resolve()

    if not input_path.exists():
        eprint(f"ERROR: input not found: {input_path}")
        return 1
    if output_path.exists() and not args.overwrite:
        eprint(f"ERROR: output exists (use --overwrite): {output_path}")
        return 1
    if not input_path.is_file():
        eprint(f"ERROR: input is not a file: {input_path}")
        return 1
    if not input_path.suffix.lower() in {".mp4", ".mov", ".mkv", ".webm"}:
        eprint("ERROR: input must be a supported video file (.mp4/.mov/.mkv/.webm)")
        return 1

    priority = max(0, min(100, int(args.priority)))
    quality_score = max(0.0, min(1.0, float(args.quality_score)))
    analysis_id = _kebab(args.analysis_id or input_path.stem)
    reference_label = args.reference_label or input_path.stem
    lane_hints = args.lane_hints or ["template_remix"]

    try:
        meta = _probe_video(input_path)
    except Exception as ex:
        eprint(f"ERROR: probe failed: {ex}")
        return 1

    raw_tags = args.tags or []
    tags = [_kebab(t) for t in raw_tags if t and _kebab(t)]
    if not tags:
        tags = _default_tags(float(meta["duration"]))

    opencv_profile = None
    if not args.disable_opencv:
        opencv_profile = _opencv_extract_profile(
            input_path,
            fps=float(meta["fps"]),
            duration=float(meta["duration"]),
        )

    analysis = _build_analysis(
        input_path=input_path,
        analysis_id=analysis_id,
        source_type=args.source_type,
        reference_label=reference_label,
        lane_hints=lane_hints,
        tags=tags,
        meta=meta,
        opencv_profile=opencv_profile,
    )

    _save_json(output_path, analysis)

    if args.index:
        index_path = pathlib.Path(args.index).resolve()
        try:
            relpath = _relpath_from_repo(output_path)
        except Exception:
            eprint("ERROR: output path must be inside repo when --index is used")
            return 1
        _update_index(
            index_path=index_path,
            analysis=analysis,
            relpath=relpath,
            priority=priority,
            quality_score=quality_score,
        )

    if not args.no_validate:
        try:
            _validate(output_path)
        except Exception as ex:
            eprint(f"ERROR: validation failed: {ex}")
            return 1

    print(f"OK: wrote {output_path}")
    if args.index:
        print(f"OK: updated index {pathlib.Path(args.index).resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
