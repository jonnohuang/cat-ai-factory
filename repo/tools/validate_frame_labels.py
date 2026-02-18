#!/usr/bin/env python3
"""
validate_frame_labels.py

Validate frame_labels.v1 with schema + deterministic grounding checks:
- authority refs match reverse/keyframe docs
- facts remain aligned with reverse truth shots
- enrichment stays facts-only-or-unknown
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
from typing import Any, Dict, List

try:
    from jsonschema import ValidationError, validate
except Exception:
    print("ERROR: jsonschema not installed in active environment.", file=sys.stderr)
    raise SystemExit(1)


def eprint(*args: Any) -> None:
    print(*args, file=sys.stderr)


def _repo_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parents[2]


def _load(path: pathlib.Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Expected object JSON at {path}")
    return data


def _camera_token_set(text: str) -> set[str]:
    m = re.findall(r"\b(pan|tilt|zoom|dolly|push|pull|tracking|handheld|static|locked)\b", text, flags=re.IGNORECASE)
    return {x.lower() for x in m}


def _brightness_claims(text: str) -> bool:
    return bool(re.search(r"\b(bright|dark|dim|neon|high-key|low-key)\b", text, flags=re.IGNORECASE))


def _validate_semantics(
    frame_doc: Dict[str, Any],
    reverse_doc: Dict[str, Any],
    keyframe_doc: Dict[str, Any],
) -> List[str]:
    errs: List[str] = []

    if frame_doc.get("analysis_id") != reverse_doc.get("analysis_id"):
        errs.append("analysis_id mismatch between frame_labels and reverse_prompt")
    if frame_doc.get("analysis_id") != keyframe_doc.get("analysis_id"):
        errs.append("analysis_id mismatch between frame_labels and keyframe_checkpoints")

    if frame_doc.get("source_video_relpath") != reverse_doc.get("source_video_relpath"):
        errs.append("source_video_relpath mismatch between frame_labels and reverse_prompt")
    if frame_doc.get("source_video_relpath") != keyframe_doc.get("source_video_relpath"):
        errs.append("source_video_relpath mismatch between frame_labels and keyframe_checkpoints")

    frame_tools = frame_doc.get("tool_versions")
    reverse_tools = reverse_doc.get("tool_versions")
    if isinstance(frame_tools, dict) and isinstance(reverse_tools, dict):
        if frame_tools != reverse_tools:
            errs.append("tool_versions mismatch between frame_labels and reverse_prompt")
    else:
        errs.append("tool_versions missing in frame_labels and/or reverse_prompt")

    truth = reverse_doc.get("truth", {})
    shots = truth.get("shots", []) if isinstance(truth, dict) else []
    shot_map: Dict[str, Dict[str, Any]] = {}
    for shot in shots:
        if isinstance(shot, dict):
            sid = shot.get("shot_id")
            if isinstance(sid, str):
                shot_map[sid] = shot

    authority = frame_doc.get("authority", {})
    if isinstance(authority, dict):
        if authority.get("reverse_prompt_ref") == authority.get("keyframe_checkpoints_ref"):
            errs.append("authority refs must point to distinct contracts")

    policy = frame_doc.get("policy", {})
    if isinstance(policy, dict):
        if policy.get("facts_only_or_unknown") is not True:
            errs.append("policy.facts_only_or_unknown must be true")

    seen_frame_ids: set[str] = set()
    last_t = -1.0
    for i, row in enumerate(frame_doc.get("frames", [])):
        if not isinstance(row, dict):
            errs.append(f"frames[{i}] must be object")
            continue
        frame_id = str(row.get("frame_id", ""))
        if frame_id in seen_frame_ids:
            errs.append(f"duplicate frame_id: {frame_id}")
        seen_frame_ids.add(frame_id)

        t_sec = float(row.get("t_sec", 0.0))
        if t_sec < last_t:
            errs.append(f"frames[{i}].t_sec must be monotonic non-decreasing")
        last_t = t_sec

        shot_id = row.get("shot_id")
        if shot_id not in shot_map:
            errs.append(f"frames[{i}].shot_id '{shot_id}' not found in reverse truth.shots")
            continue
        shot_truth = shot_map[str(shot_id)]
        facts = row.get("facts", {})
        if not isinstance(facts, dict):
            errs.append(f"frames[{i}].facts missing")
            continue

        # Facts must align with reverse truth shot values.
        cam = facts.get("camera_mode")
        if isinstance(shot_truth.get("camera"), str) and cam != shot_truth.get("camera"):
            errs.append(f"frames[{i}].facts.camera_mode must match truth.shots[{shot_id}].camera")
        palette = facts.get("palette_hint")
        if isinstance(shot_truth.get("palette_hint"), str) and palette != shot_truth.get("palette_hint"):
            errs.append(f"frames[{i}].facts.palette_hint must match truth.shots[{shot_id}].palette_hint")
        mi = facts.get("motion_intensity")
        if isinstance(mi, (int, float)):
            tv = float(shot_truth.get("motion_intensity", 0.0))
            if abs(float(mi) - tv) > 0.001:
                errs.append(f"frames[{i}].facts.motion_intensity must match truth.shots[{shot_id}].motion_intensity")

        labels = row.get("labels", {})
        if not isinstance(labels, dict):
            errs.append(f"frames[{i}].labels missing")
            continue
        action_summary = str(labels.get("action_summary", ""))
        camera_tokens = _camera_token_set(action_summary)
        brightness_tokens = _brightness_claims(action_summary)
        cam_truth = str(facts.get("camera_mode") or "unknown")
        bright_truth = str(facts.get("brightness_bucket") or "unknown")
        allowed_camera = {
            "unknown": set(),
            "locked": {"locked", "static"},
            "pan": {"pan", "tracking"},
            "tilt": {"tilt"},
            "push": {"push"},
            "pull": {"pull"},
            "mixed": {"pan", "tilt", "zoom", "dolly", "push", "pull", "tracking", "handheld", "static", "locked"},
        }.get(cam_truth, set())
        if camera_tokens and not camera_tokens.issubset(allowed_camera):
            errs.append(f"frames[{i}].labels.action_summary camera claims violate facts-only-or-unknown policy")
        if bright_truth == "unknown" and brightness_tokens:
            errs.append(f"frames[{i}].labels.action_summary brightness claims violate unknown policy")

    return errs


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(description="Validate frame_labels.v1 contract")
    parser.add_argument("--frame-labels", required=True, help="Path to frame_labels.v1 JSON")
    parser.add_argument("--reverse", required=True, help="Path to caf.video_reverse_prompt.v1 JSON")
    parser.add_argument("--keyframes", required=True, help="Path to keyframe_checkpoints.v1 JSON")
    args = parser.parse_args(argv[1:])

    root = _repo_root()
    schemas = {
        "frame_labels": _load(root / "repo" / "shared" / "frame_labels.v1.schema.json"),
        "reverse": _load(root / "repo" / "shared" / "caf.video_reverse_prompt.v1.schema.json"),
        "keyframes": _load(root / "repo" / "shared" / "keyframe_checkpoints.v1.schema.json"),
    }
    docs = {
        "frame_labels": _load(pathlib.Path(args.frame_labels).resolve()),
        "reverse": _load(pathlib.Path(args.reverse).resolve()),
        "keyframes": _load(pathlib.Path(args.keyframes).resolve()),
    }

    errors: List[str] = []
    for key in ("frame_labels", "reverse", "keyframes"):
        try:
            validate(instance=docs[key], schema=schemas[key])
        except ValidationError as ex:
            errors.append(f"SCHEMA {key}: {ex.message}")

    if not errors:
        errors.extend(_validate_semantics(docs["frame_labels"], docs["reverse"], docs["keyframes"]))

    if errors:
        eprint("INVALID: frame_labels contracts")
        for err in errors:
            eprint(f"- {err}")
        return 1

    print("OK: frame_labels contracts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
