#!/usr/bin/env python3
"""
score_costume_fidelity.py

Deterministic costume fidelity scoring for recast outputs.
Writes costume_fidelity_report.v1 JSON.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time
from typing import Any

import numpy as np

try:
    import cv2  # type: ignore
except Exception:
    cv2 = None


def _repo_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parents[2]


def _load(path: pathlib.Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _write(path: pathlib.Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _resolve(rel_or_abs: str) -> pathlib.Path:
    p = pathlib.Path(rel_or_abs)
    if p.is_absolute():
        return p
    return _repo_root() / rel_or_abs


def _hist_similarity(a_bgr: np.ndarray, b_bgr: np.ndarray) -> float:
    a = cv2.cvtColor(a_bgr, cv2.COLOR_BGR2HSV)
    b = cv2.cvtColor(b_bgr, cv2.COLOR_BGR2HSV)
    h1 = cv2.calcHist([a], [0, 1], None, [64, 48], [0, 180, 0, 256])
    h2 = cv2.calcHist([b], [0, 1], None, [64, 48], [0, 180, 0, 256])
    cv2.normalize(h1, h1, alpha=1, beta=0, norm_type=cv2.NORM_L1)
    cv2.normalize(h2, h2, alpha=1, beta=0, norm_type=cv2.NORM_L1)
    corr = float(cv2.compareHist(h1, h2, cv2.HISTCMP_CORREL))
    return max(0.0, min(1.0, (corr + 1.0) / 2.0))


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Deterministically score costume fidelity from recast output")
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--video-relpath", required=True)
    parser.add_argument("--costume-image-relpath", required=True)
    parser.add_argument("--tracks-relpath", required=True)
    parser.add_argument("--subject-id", default=None)
    parser.add_argument("--threshold", type=float, default=0.52)
    parser.add_argument("--out", default=None)
    args = parser.parse_args(argv[1:])

    out_path = (
        pathlib.Path(args.out).resolve()
        if args.out
        else _repo_root() / "sandbox" / "logs" / args.job_id / "qc" / "costume_fidelity_report.v1.json"
    )

    report: dict[str, Any] = {
        "version": "costume_fidelity_report.v1",
        "job_id": args.job_id,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "video_relpath": args.video_relpath,
        "costume_image_relpath": args.costume_image_relpath,
        "tracks_relpath": args.tracks_relpath,
        "subject_id": args.subject_id,
        "threshold": float(args.threshold),
    }

    if cv2 is None:
        report["available"] = False
        report["pass"] = False
        report["score"] = None
        report["reason"] = "opencv_not_available"
        _write(out_path, report)
        print("Wrote", out_path)
        print("costume.score", None)
        print("costume.pass", False)
        return 0

    video_path = _resolve(args.video_relpath)
    costume_path = _resolve(args.costume_image_relpath)
    tracks_path = _resolve(args.tracks_relpath)
    for p, label in ((video_path, "video"), (costume_path, "costume_image"), (tracks_path, "tracks")):
        if not p.exists():
            report["available"] = False
            report["pass"] = False
            report["score"] = None
            report["reason"] = f"missing_{label}"
            _write(out_path, report)
            print("Wrote", out_path)
            print("costume.score", None)
            print("costume.pass", False)
            return 0

    costume = cv2.imread(str(costume_path))
    if costume is None:
        report["available"] = False
        report["pass"] = False
        report["score"] = None
        report["reason"] = "costume_image_unreadable"
        _write(out_path, report)
        print("Wrote", out_path)
        print("costume.score", None)
        print("costume.pass", False)
        return 0

    tracks = _load(tracks_path)
    subjects = tracks.get("subjects", []) if isinstance(tracks, dict) else []
    target = None
    if args.subject_id:
        target = next((s for s in subjects if s.get("subject_id") == args.subject_id), None)
    if target is None and subjects:
        target = subjects[0]
    if target is None:
        report["available"] = False
        report["pass"] = False
        report["score"] = None
        report["reason"] = "no_subject_rows"
        _write(out_path, report)
        print("Wrote", out_path)
        print("costume.score", None)
        print("costume.pass", False)
        return 0

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        report["available"] = False
        report["pass"] = False
        report["score"] = None
        report["reason"] = "video_open_failed"
        _write(out_path, report)
        print("Wrote", out_path)
        print("costume.score", None)
        print("costume.pass", False)
        return 0

    sims: list[float] = []
    used_frames = 0
    for row in target.get("frames", [])[:12]:
        frame_idx = int(row.get("frame", 0))
        cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, frame_idx))
        ok, frame = cap.read()
        if not ok:
            continue
        b = row.get("bbox", {})
        x = max(0, int(b.get("x", 0)))
        y = max(0, int(b.get("y", 0)))
        w = max(1, int(b.get("w", 1)))
        h = max(1, int(b.get("h", 1)))
        crop = frame[y : y + h, x : x + w]
        if crop.size == 0:
            continue
        sims.append(_hist_similarity(crop, costume))
        used_frames += 1
    cap.release()

    if not sims:
        report["available"] = False
        report["pass"] = False
        report["score"] = None
        report["reason"] = "no_valid_subject_crops"
        _write(out_path, report)
        print("Wrote", out_path)
        print("costume.score", None)
        print("costume.pass", False)
        return 0

    score = float(np.mean(sims))
    passed = score >= float(args.threshold)
    report["available"] = True
    report["score"] = score
    report["pass"] = passed
    report["sampled_frames"] = used_frames
    report["reason"] = "" if passed else "below_threshold"
    _write(out_path, report)
    print("Wrote", out_path)
    print("costume.score", round(score, 6))
    print("costume.pass", passed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
