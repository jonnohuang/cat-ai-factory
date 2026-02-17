#!/usr/bin/env python3
"""
score_recast_quality.py

Deterministic quality-gate scoring for recast videos.
Writes recast_quality_report.v1 JSON (default under sandbox/logs/<job_id>/qc/).
"""
from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import time
from dataclasses import dataclass
from typing import Any

import numpy as np

try:
    import cv2  # type: ignore
except Exception:
    cv2 = None


THRESH_IDENTITY = 0.55
THRESH_MASK_BLEED = 0.45
THRESH_TEMPORAL = 0.55
THRESH_LOOP_SEAM = 0.60
THRESH_AV = 0.95


@dataclass
class Metric:
    available: bool
    score: float | None
    threshold: float
    passed: bool
    reason: str = ""

    def as_dict(self) -> dict[str, Any]:
        out = {
            "available": self.available,
            "score": self.score,
            "threshold": self.threshold,
            "pass": self.passed,
        }
        if self.reason:
            out["reason"] = self.reason
        return out


def _repo_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parents[2]


def _load(path: pathlib.Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: pathlib.Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _ffprobe_streams(video_path: pathlib.Path) -> dict[str, Any]:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "stream=codec_type,start_time,duration,avg_frame_rate:format=duration",
        "-of",
        "json",
        str(video_path),
    ]
    out = subprocess.check_output(cmd, text=True)
    return json.loads(out)


def _video_fps_from_cv2(cap: Any) -> float:
    fps = float(cap.get(cv2.CAP_PROP_FPS)) if cv2 else 0.0
    if fps <= 0:
        return 30.0
    return fps


def _read_frame_at(cap: Any, frame_idx: int) -> np.ndarray | None:
    cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, frame_idx))
    ok, frame = cap.read()
    if not ok:
        return None
    return frame


def _hist_similarity(a_bgr: np.ndarray, b_bgr: np.ndarray) -> float:
    a = cv2.cvtColor(a_bgr, cv2.COLOR_BGR2HSV)
    b = cv2.cvtColor(b_bgr, cv2.COLOR_BGR2HSV)
    h1 = cv2.calcHist([a], [0, 1], None, [48, 32], [0, 180, 0, 256])
    h2 = cv2.calcHist([b], [0, 1], None, [48, 32], [0, 180, 0, 256])
    cv2.normalize(h1, h1, alpha=1, beta=0, norm_type=cv2.NORM_L1)
    cv2.normalize(h2, h2, alpha=1, beta=0, norm_type=cv2.NORM_L1)
    corr = float(cv2.compareHist(h1, h2, cv2.HISTCMP_CORREL))
    return max(0.0, min(1.0, (corr + 1.0) / 2.0))


def _score_identity(video_path: pathlib.Path, hero_image: pathlib.Path | None, tracks_path: pathlib.Path | None, subject_id: str | None) -> Metric:
    if cv2 is None:
        return Metric(False, None, THRESH_IDENTITY, False, "opencv_not_available")
    if hero_image is None or not hero_image.exists():
        return Metric(False, None, THRESH_IDENTITY, False, "missing_hero_image")
    if tracks_path is None or not tracks_path.exists():
        return Metric(False, None, THRESH_IDENTITY, False, "missing_tracks")

    hero = cv2.imread(str(hero_image))
    if hero is None:
        return Metric(False, None, THRESH_IDENTITY, False, "hero_image_unreadable")

    tracks = _load(tracks_path)
    subjects = tracks.get("subjects", [])
    target = None
    if subject_id:
        target = next((s for s in subjects if s.get("subject_id") == subject_id), None)
    if target is None and subjects:
        target = subjects[0]
    if target is None:
        return Metric(False, None, THRESH_IDENTITY, False, "no_subject_rows")

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return Metric(False, None, THRESH_IDENTITY, False, "video_open_failed")

    sims: list[float] = []
    for row in target.get("frames", [])[:12]:
        frame = _read_frame_at(cap, int(row["frame"]))
        if frame is None:
            continue
        b = row.get("bbox", {})
        x = max(0, int(b.get("x", 0)))
        y = max(0, int(b.get("y", 0)))
        w = max(1, int(b.get("w", 1)))
        h = max(1, int(b.get("h", 1)))
        crop = frame[y : y + h, x : x + w]
        if crop.size == 0:
            continue
        sims.append(_hist_similarity(crop, hero))
    cap.release()

    if not sims:
        return Metric(False, None, THRESH_IDENTITY, False, "no_valid_subject_crops")
    score = float(np.mean(sims))
    return Metric(True, score, THRESH_IDENTITY, score >= THRESH_IDENTITY)


def _score_temporal(video_path: pathlib.Path) -> Metric:
    if cv2 is None:
        return Metric(False, None, THRESH_TEMPORAL, False, "opencv_not_available")
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return Metric(False, None, THRESH_TEMPORAL, False, "video_open_failed")

    diffs: list[float] = []
    ok, prev = cap.read()
    if not ok:
        cap.release()
        return Metric(False, None, THRESH_TEMPORAL, False, "no_frames")
    prev_g = cv2.cvtColor(cv2.resize(prev, (160, 90)), cv2.COLOR_BGR2GRAY)

    sample_step = 2
    idx = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        idx += 1
        if idx % sample_step != 0:
            continue
        g = cv2.cvtColor(cv2.resize(frame, (160, 90)), cv2.COLOR_BGR2GRAY)
        diffs.append(float(np.mean(np.abs(g.astype(np.float32) - prev_g.astype(np.float32)))))
        prev_g = g
    cap.release()

    if len(diffs) < 4:
        return Metric(False, None, THRESH_TEMPORAL, False, "insufficient_frame_diffs")
    jitter = float(np.std(np.array(diffs, dtype=np.float32)))
    score = float(max(0.0, min(1.0, 1.0 - (jitter / 25.0))))
    return Metric(True, score, THRESH_TEMPORAL, score >= THRESH_TEMPORAL)


def _score_loop_seam(video_path: pathlib.Path, loop_start: int | None, loop_end: int | None) -> Metric:
    if cv2 is None:
        return Metric(False, None, THRESH_LOOP_SEAM, False, "opencv_not_available")
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return Metric(False, None, THRESH_LOOP_SEAM, False, "video_open_failed")

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    start = loop_start if loop_start is not None else 0
    end = loop_end if loop_end is not None else max(0, total_frames - 1)
    end = min(end, max(0, total_frames - 1))
    if end <= start:
        cap.release()
        return Metric(False, None, THRESH_LOOP_SEAM, False, "invalid_loop_bounds")

    a = _read_frame_at(cap, start)
    b = _read_frame_at(cap, end)
    cap.release()
    if a is None or b is None:
        return Metric(False, None, THRESH_LOOP_SEAM, False, "failed_read_loop_frames")

    a = cv2.cvtColor(cv2.resize(a, (240, 426)), cv2.COLOR_BGR2GRAY)
    b = cv2.cvtColor(cv2.resize(b, (240, 426)), cv2.COLOR_BGR2GRAY)
    mae = float(np.mean(np.abs(a.astype(np.float32) - b.astype(np.float32))))
    score = float(max(0.0, min(1.0, 1.0 - (mae / 40.0))))
    return Metric(True, score, THRESH_LOOP_SEAM, score >= THRESH_LOOP_SEAM)


def _score_mask_bleed(video_path: pathlib.Path, tracks_path: pathlib.Path | None, subject_id: str | None) -> Metric:
    if cv2 is None:
        return Metric(False, None, THRESH_MASK_BLEED, False, "opencv_not_available")
    if tracks_path is None or not tracks_path.exists():
        return Metric(False, None, THRESH_MASK_BLEED, False, "missing_tracks")

    tracks = _load(tracks_path)
    subjects = tracks.get("subjects", [])
    target = None
    if subject_id:
        target = next((s for s in subjects if s.get("subject_id") == subject_id), None)
    if target is None and subjects:
        target = subjects[0]
    if target is None:
        return Metric(False, None, THRESH_MASK_BLEED, False, "no_subject_rows")

    root = _repo_root()
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return Metric(False, None, THRESH_MASK_BLEED, False, "video_open_failed")

    edge_energies: list[float] = []
    for row in target.get("frames", [])[:10]:
        mask_rel = row.get("mask_relpath")
        if not isinstance(mask_rel, str):
            continue
        mask_path = root / mask_rel
        if not mask_path.exists():
            continue
        frame = _read_frame_at(cap, int(row["frame"]))
        if frame is None:
            continue
        mask = cv2.imread(str(mask_path), cv2.IMREAD_GRAYSCALE)
        if mask is None:
            continue
        if mask.shape[:2] != frame.shape[:2]:
            mask = cv2.resize(mask, (frame.shape[1], frame.shape[0]), interpolation=cv2.INTER_NEAREST)
        _, bin_mask = cv2.threshold(mask, 127, 255, cv2.THRESH_BINARY)
        boundary = cv2.morphologyEx(bin_mask, cv2.MORPH_GRADIENT, np.ones((3, 3), np.uint8))
        if int(np.count_nonzero(boundary)) == 0:
            continue
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
        gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
        grad = cv2.magnitude(gx, gy)
        edge_vals = grad[boundary > 0]
        if edge_vals.size > 0:
            edge_energies.append(float(np.mean(edge_vals)))
    cap.release()

    if not edge_energies:
        return Metric(False, None, THRESH_MASK_BLEED, False, "no_valid_masks_for_scoring")
    bleed = float(np.mean(np.array(edge_energies, dtype=np.float32)))
    score = float(max(0.0, min(1.0, 1.0 - (bleed / 120.0))))
    return Metric(True, score, THRESH_MASK_BLEED, score >= THRESH_MASK_BLEED)


def _score_audio_video(video_path: pathlib.Path) -> dict[str, Any]:
    probe = _ffprobe_streams(video_path)
    streams = probe.get("streams", [])
    a = next((s for s in streams if s.get("codec_type") == "audio"), None)
    v = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio_present = a is not None
    a_start = float(a.get("start_time", 0.0)) if a else 0.0
    v_start = float(v.get("start_time", 0.0)) if v else 0.0
    sync = abs(a_start - v_start)
    score = 0.0 if not audio_present else max(0.0, min(1.0, 1.0 - (sync / 0.12)))
    passed = bool(audio_present and score >= THRESH_AV)
    out = {
        "audio_stream_present": audio_present,
        "av_sync_sec": round(sync, 6),
        "score": round(score, 6),
        "threshold": THRESH_AV,
        "pass": passed,
    }
    if not audio_present:
        out["reason"] = "missing_audio_stream"
    return out


def _resolve(path_str: str) -> pathlib.Path:
    p = pathlib.Path(path_str)
    if p.is_absolute():
        return p
    return _repo_root() / path_str


def main() -> int:
    parser = argparse.ArgumentParser(description="Score deterministic recast quality gates")
    parser.add_argument("--job-id", required=True, help="Job ID")
    parser.add_argument("--video-relpath", required=True, help="Video path under sandbox, e.g. sandbox/output/<job_id>/final.mp4")
    parser.add_argument("--hero-image-relpath", help="Optional hero image path under sandbox/assets")
    parser.add_argument("--tracks-relpath", help="Optional dance_swap_tracks JSON path")
    parser.add_argument("--subject-id", help="Optional subject_id for tracks lookup")
    parser.add_argument("--loop-start-frame", type=int, help="Optional loop start frame")
    parser.add_argument("--loop-end-frame", type=int, help="Optional loop end frame")
    parser.add_argument("--out", help="Output report path; default sandbox/logs/<job_id>/qc/recast_quality_report.v1.json")
    args = parser.parse_args()

    video = _resolve(args.video_relpath)
    if not video.exists():
        raise SystemExit(f"Video not found: {video}")

    hero = _resolve(args.hero_image_relpath) if args.hero_image_relpath else None
    tracks = _resolve(args.tracks_relpath) if args.tracks_relpath else None

    identity = _score_identity(video, hero, tracks, args.subject_id)
    mask_bleed = _score_mask_bleed(video, tracks, args.subject_id)
    temporal = _score_temporal(video)
    loop = _score_loop_seam(video, args.loop_start_frame, args.loop_end_frame)
    av = _score_audio_video(video)

    metric_rows = {
        "identity_consistency": identity.as_dict(),
        "mask_edge_bleed": mask_bleed.as_dict(),
        "temporal_stability": temporal.as_dict(),
        "loop_seam": loop.as_dict(),
        "audio_video": av,
    }

    scores = []
    failed: list[str] = []
    for name in ("identity_consistency", "mask_edge_bleed", "temporal_stability", "loop_seam"):
        m = metric_rows[name]
        if m["available"] and m["score"] is not None:
            scores.append(float(m["score"]))
        if not m["pass"]:
            failed.append(name)
    scores.append(float(av["score"]))
    if not av["pass"]:
        failed.append("audio_video")

    overall_score = float(np.mean(np.array(scores, dtype=np.float32))) if scores else 0.0
    report = {
        "version": "recast_quality_report.v1",
        "job_id": args.job_id,
        "video_relpath": args.video_relpath,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "metrics": metric_rows,
        "overall": {
            "score": round(overall_score, 6),
            "pass": len(failed) == 0,
            "failed_metrics": failed,
        },
    }

    out_path = (
        _resolve(args.out)
        if args.out
        else _repo_root() / "sandbox" / "logs" / args.job_id / "qc" / "recast_quality_report.v1.json"
    )
    _write_json(out_path, report)
    print("Wrote", out_path)
    print("overall.score", report["overall"]["score"])
    print("overall.pass", report["overall"]["pass"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

