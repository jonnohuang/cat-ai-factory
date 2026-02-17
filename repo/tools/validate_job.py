#!/usr/bin/env python3
"""
validate_job.py

Validates a Cat AI Factory job.json against repo/shared/job.schema.json.

- If `jsonschema` is available, performs full JSON Schema validation.
- If `jsonschema` is NOT available (offline/no-deps), performs minimal Contract v1 checks
  sufficient for deterministic rendering with the current worker.

Usage:
  python3 repo/tools/validate_job.py path/to/job.json

Exit codes:
  0 = valid
  1 = invalid / error
"""
from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict, List, Tuple


SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "..", "shared", "job.schema.json")
SCHEMA_PATH = os.path.normpath(SCHEMA_PATH)


def eprint(*args: Any) -> None:
    print(*args, file=sys.stderr)


def load_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _is_number(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def minimal_v1_checks(job: Dict[str, Any]) -> List[str]:
    """Dependency-free minimal checks for Contract v1."""
    errors: List[str] = []

    # schema_version (optional, but if present must be 'v1')
    sv = job.get("schema_version")
    if sv is not None and sv != "v1":
        errors.append(f"schema_version must be 'v1' (got {sv!r})")

    # job_id
    jid = job.get("job_id")
    if not isinstance(jid, str) or len(jid.strip()) < 6:
        errors.append("job_id must be a non-empty string with length >= 6")

    # video
    video = job.get("video")
    if not isinstance(video, dict):
        errors.append("video must be an object")
    else:
        ls = video.get("length_seconds")
        if not _is_number(ls) or ls <= 0:
            errors.append("video.length_seconds must be a number > 0")
        fps = video.get("fps")
        if not _is_number(fps) or fps <= 0:
            errors.append("video.fps must be a number > 0")

    # render
    render = job.get("render")
    if not isinstance(render, dict):
        errors.append("render must be an object")
    else:
        bg = render.get("background_asset")
        if not isinstance(bg, str) or not bg.strip():
            errors.append("render.background_asset must be a non-empty string")
        ob = render.get("output_basename")
        if not isinstance(ob, str) or not ob.strip():
            errors.append("render.output_basename must be a non-empty string")

    # captions
    caps = job.get("captions")
    if not isinstance(caps, list):
        errors.append("captions must be an array of strings")
    else:
        for i, c in enumerate(caps):
            if not isinstance(c, str):
                errors.append(f"captions[{i}] must be a string")

    # creativity (optional)
    creativity = job.get("creativity")
    if creativity is not None:
        if not isinstance(creativity, dict):
            errors.append("creativity must be an object")
        else:
            # Check for unknown keys
            known_keys = {"mode", "canon_fidelity"}
            unknown = set(creativity.keys()) - known_keys
            if unknown:
                errors.append(f"creativity has unknown keys: {sorted(list(unknown))}")

            # mode
            mode = creativity.get("mode")
            if mode is not None:
                if mode not in ("canon", "balanced", "experimental"):
                    errors.append(f"creativity.mode must be one of ['canon', 'balanced', 'experimental'] (got {mode!r})")

            # canon_fidelity
            fidelity = creativity.get("canon_fidelity")
            if fidelity is not None:
                if fidelity not in ("high", "medium"):
                    errors.append(f"creativity.canon_fidelity must be one of ['high', 'medium'] (got {fidelity!r})")

    lane = job.get("lane")
    if lane == "dance_swap":
        ds = job.get("dance_swap")
        if not isinstance(ds, dict):
            errors.append("lane='dance_swap' requires dance_swap object")
        else:
            for key in ("loop_artifact", "tracks_artifact", "foreground_asset"):
                val = ds.get(key)
                if not isinstance(val, str) or not val.strip():
                    errors.append(f"dance_swap.{key} must be a non-empty string")
            beatflow = ds.get("beatflow_artifact")
            if beatflow is not None and (not isinstance(beatflow, str) or not beatflow.strip()):
                errors.append("dance_swap.beatflow_artifact must be a non-empty string when present")
            subject_id = ds.get("subject_id")
            if subject_id is not None and (not isinstance(subject_id, str) or not subject_id.strip()):
                errors.append("dance_swap.subject_id must be a non-empty string when present")

    segment_stitch = job.get("segment_stitch")
    if segment_stitch is not None:
        if not isinstance(segment_stitch, dict):
            errors.append("segment_stitch must be an object when present")
        else:
            plan_relpath = segment_stitch.get("plan_relpath")
            if not isinstance(plan_relpath, str) or not plan_relpath.strip():
                errors.append("segment_stitch.plan_relpath must be a non-empty string")
            elif not plan_relpath.startswith("repo/"):
                errors.append("segment_stitch.plan_relpath must be repo-relative (repo/...)")
            enabled = segment_stitch.get("enabled")
            if enabled is not None and not isinstance(enabled, bool):
                errors.append("segment_stitch.enabled must be boolean when present")

    quality_target = job.get("quality_target")
    if quality_target is not None:
        if not isinstance(quality_target, dict):
            errors.append("quality_target must be an object when present")
        else:
            relpath = quality_target.get("relpath")
            if not isinstance(relpath, str) or not relpath.strip():
                errors.append("quality_target.relpath must be a non-empty string")
            elif not relpath.startswith("repo/"):
                errors.append("quality_target.relpath must be repo-relative (repo/...)")

    continuity_pack = job.get("continuity_pack")
    if continuity_pack is not None:
        if not isinstance(continuity_pack, dict):
            errors.append("continuity_pack must be an object when present")
        else:
            relpath = continuity_pack.get("relpath")
            if not isinstance(relpath, str) or not relpath.strip():
                errors.append("continuity_pack.relpath must be a non-empty string")
            elif not relpath.startswith("repo/"):
                errors.append("continuity_pack.relpath must be repo-relative (repo/...)")

    return errors


def validate_with_jsonschema(job: Dict[str, Any], schema: Dict[str, Any]) -> Tuple[bool, str]:
    """Full validation using jsonschema if available."""
    try:
        import jsonschema  # type: ignore
    except Exception as ex:
        return False, f"jsonschema import failed: {ex}"

    try:
        jsonschema.validate(instance=job, schema=schema)
        return True, "ok"
    except Exception as ex:
        # jsonschema exceptions are already descriptive (path, message)
        return False, str(ex)


def main(argv: List[str]) -> int:
    if len(argv) != 2:
        eprint("Usage: python3 repo/tools/validate_job.py path/to/job.json")
        return 1

    job_path = argv[1]
    if not os.path.exists(job_path):
        eprint(f"ERROR: job file not found: {job_path}")
        return 1

    try:
        job = load_json(job_path)
    except Exception as ex:
        eprint(f"ERROR: failed to parse JSON: {job_path}")
        eprint(f"  {ex}")
        return 1

    # Try full schema validation if jsonschema exists; otherwise fallback.
    schema = None
    if os.path.exists(SCHEMA_PATH):
        try:
            schema = load_json(SCHEMA_PATH)
        except Exception as ex:
            eprint(f"ERROR: failed to parse schema JSON: {SCHEMA_PATH}")
            eprint(f"  {ex}")
            return 1

    # If schema + jsonschema available, do full validation.
    if schema is not None:
        ok, msg = validate_with_jsonschema(job, schema)
        if ok:
            print(f"OK: {job_path}")
            return 0
        # If jsonschema not available, fall through to minimal checks.
        if "jsonschema import failed" not in msg:
            eprint(f"INVALID (schema): {job_path}")
            eprint(msg)
            return 1
        eprint("NOTE: jsonschema not installed; running minimal v1 checks instead.")

    # Minimal checks (offline-safe)
    errors = minimal_v1_checks(job)
    if errors:
        eprint(f"INVALID (minimal v1): {job_path}")
        for err in errors:
            eprint(f"- {err}")
        return 1

    print(f"OK (minimal v1): {job_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
