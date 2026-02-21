#!/usr/bin/env python3
"""
Deterministic two-pass orchestration artifact builder.
Writes sandbox/logs/<job_id>/qc/two_pass_orchestration.v1.json
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import sys
from typing import Any, Dict, Optional


def _repo_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parents[2]


def _utc_now() -> str:
    return (
        dt.datetime.now(dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _load_json(path: pathlib.Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _save_json(path: pathlib.Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def _safe_rel(path: pathlib.Path, root: pathlib.Path) -> Optional[str]:
    try:
        return str(path.resolve().relative_to(root.resolve())).replace("\\", "/")
    except Exception:
        return None


def _find_external_lifecycle(
    project_root: pathlib.Path, job_id: str
) -> Optional[pathlib.Path]:
    path = (
        project_root
        / "sandbox"
        / "dist_artifacts"
        / job_id
        / "viggle_pack"
        / "external_recast_lifecycle.v1.json"
    )
    if path.exists():
        return path
    return None


def _motion_pass(segment_report: Optional[Dict[str, Any]]) -> tuple[str, str]:
    if not isinstance(segment_report, dict):
        return "unknown", "Segment runtime report unavailable."
    segments = segment_report.get("segments", [])
    if isinstance(segments, list) and len(segments) > 0:
        return "pass", "Segment runtime report present with generated clips."
    return "fail", "Segment runtime report present but no generated segments."


def _identity_pass(
    quality: Optional[Dict[str, Any]],
    costume: Optional[Dict[str, Any]],
) -> tuple[str, str]:
    costume_fail = bool(isinstance(costume, dict) and costume.get("pass") is False)
    if costume_fail:
        return "fail", "Costume fidelity gate failed."

    if not isinstance(quality, dict):
        return "unknown", "Recast quality report unavailable."

    overall = quality.get("overall", {})
    overall_pass = bool(isinstance(overall, dict) and overall.get("pass"))
    if overall_pass:
        return "pass", "Identity-related quality gates passed."
    return "fail", "Identity-related quality gates failed."


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Derive deterministic two-pass orchestration artifact"
    )
    parser.add_argument("--job-id", required=True)
    args = parser.parse_args(argv[1:])

    root = _repo_root()
    job_id = args.job_id
    qc_dir = root / "sandbox" / "logs" / job_id / "qc"
    out_path = qc_dir / "two_pass_orchestration.v1.json"

    segment_report_path = (
        root
        / "sandbox"
        / "output"
        / job_id
        / "segments"
        / "segment_stitch_report.v1.json"
    )
    quality_path = qc_dir / "recast_quality_report.v1.json"
    costume_path = qc_dir / "costume_fidelity.v1.json"
    external_lifecycle_path = _find_external_lifecycle(root, job_id)

    segment_report = _load_json(segment_report_path)
    quality = _load_json(quality_path)
    costume = _load_json(costume_path)
    external_lifecycle = (
        _load_json(external_lifecycle_path) if external_lifecycle_path else None
    )

    motion_status, motion_reason = _motion_pass(segment_report)
    identity_status, identity_reason = _identity_pass(quality, costume)

    if external_lifecycle is not None:
        identity_boundary = "external_hitl_required"
    else:
        identity_boundary = "unknown"

    if identity_status == "fail":
        if isinstance(costume, dict) and costume.get("pass") is False:
            next_action = "block_for_costume"
        else:
            next_action = "retry_recast"
    elif motion_status == "fail":
        next_action = "retry_motion"
    else:
        next_action = "proceed_finalize"

    payload: Dict[str, Any] = {
        "version": "two_pass_orchestration.v1",
        "job_id": job_id,
        "generated_at": _utc_now(),
        "inputs": {
            "segment_stitch_report_relpath": (
                _safe_rel(segment_report_path, root)
                if segment_report_path.exists()
                else None
            ),
            "quality_report_relpath": (
                _safe_rel(quality_path, root) if quality_path.exists() else None
            ),
            "costume_report_relpath": (
                _safe_rel(costume_path, root) if costume_path.exists() else None
            ),
            "external_recast_lifecycle_relpath": (
                _safe_rel(external_lifecycle_path, root)
                if external_lifecycle_path and external_lifecycle_path.exists()
                else None
            ),
        },
        "passes": {
            "motion": {"status": motion_status, "reason": motion_reason},
            "identity": {"status": identity_status, "reason": identity_reason},
        },
        "orchestration": {
            "identity_boundary": identity_boundary,
            "next_preferred_action": next_action,
        },
    }

    _save_json(out_path, payload)
    print(str(out_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
