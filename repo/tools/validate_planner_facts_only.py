#!/usr/bin/env python3
"""
validate_planner_facts_only.py

Deterministically validates that planner job text claims are grounded in reverse analyzer facts.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
from typing import Any, Dict, List, Tuple


def eprint(*args: Any) -> None:
    print(*args, file=sys.stderr)


def _load(path: pathlib.Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Expected object JSON at {path}")
    return data


def _collect_texts(job: Dict[str, Any]) -> List[Tuple[str, str]]:
    out: List[Tuple[str, str]] = []
    script = job.get("script", {})
    if isinstance(script, dict):
        for k in ("hook", "voiceover", "ending"):
            v = script.get(k)
            if isinstance(v, str):
                out.append((f"script.{k}", v))
    shots = job.get("shots", [])
    if isinstance(shots, list):
        for i, shot in enumerate(shots):
            if not isinstance(shot, dict):
                continue
            for k in ("visual", "action", "caption"):
                v = shot.get(k)
                if isinstance(v, str):
                    out.append((f"shots[{i}].{k}", v))
    return out


def _validate(job: Dict[str, Any], reverse_doc: Dict[str, Any]) -> List[str]:
    errs: List[str] = []
    visual = reverse_doc.get("truth", {}).get("visual_facts", {})
    if not isinstance(visual, dict):
        return ["reverse_doc.truth.visual_facts missing"]

    camera_mode = str(visual.get("camera_movement_mode") or "unknown").lower()
    brightness_bucket = str(visual.get("brightness_bucket") or "unknown").lower()

    camera_terms = re.compile(r"\\b(pan|tilt|zoom|dolly|push|pull|tracking|handheld|static|locked)\\b", re.IGNORECASE)
    brightness_terms = re.compile(r"\\b(bright|dark|dim|neon|high-key|low-key)\\b", re.IGNORECASE)
    allowed_camera: Dict[str, set[str]] = {
        "unknown": set(),
        "locked": {"locked", "static"},
        "pan": {"pan", "tracking"},
        "tilt": {"tilt"},
        "push": {"push"},
        "pull": {"pull"},
        "mixed": {"pan", "tilt", "zoom", "dolly", "push", "pull", "tracking", "handheld", "static", "locked"},
    }

    for label, text in _collect_texts(job):
        cam_match = camera_terms.search(text)
        if cam_match:
            token = cam_match.group(1).lower()
            if token not in allowed_camera.get(camera_mode, set()):
                errs.append(f"{label}: camera claim '{token}' not grounded by camera_movement_mode={camera_mode}")
        if brightness_bucket == "unknown" and brightness_terms.search(text):
            errs.append(f"{label}: brightness claim not allowed when brightness_bucket=unknown")
    return errs


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(description="Validate planner output against facts-only reverse-analysis rules")
    parser.add_argument("--job", required=True)
    parser.add_argument("--reverse", required=True)
    args = parser.parse_args(argv[1:])

    job = _load(pathlib.Path(args.job).resolve())
    reverse_doc = _load(pathlib.Path(args.reverse).resolve())
    errs = _validate(job, reverse_doc)
    if errs:
        eprint("INVALID: planner facts-only")
        for err in errs:
            eprint(f"- {err}")
        return 1
    print("OK: planner facts-only")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
