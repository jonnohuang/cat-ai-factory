#!/usr/bin/env python3
"""
Deterministic quality policy engine.
Writes sandbox/logs/<job_id>/qc/quality_decision.v1.json
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import sys
from typing import Any, Dict, Optional


def _repo_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parents[2]


def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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


def _find_segment_plan(project_root: pathlib.Path) -> Optional[pathlib.Path]:
    for p in [
        project_root / "repo" / "canon" / "demo_analyses",
        project_root / "repo" / "examples",
    ]:
        if not p.is_dir():
            continue
        for f in sorted(p.rglob("*.json")):
            data = _load_json(f)
            if isinstance(data, dict) and data.get("version") == "segment_stitch_plan.v1":
                return f
    return None


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Deterministic quality decision engine")
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--max-retries", type=int, default=2)
    args = parser.parse_args(argv[1:])

    project_root = _repo_root()
    qc_dir = project_root / "sandbox" / "logs" / args.job_id / "qc"
    quality_path = qc_dir / "recast_quality_report.v1.json"
    costume_path = qc_dir / "costume_fidelity.v1.json"
    decision_path = qc_dir / "quality_decision.v1.json"

    quality = _load_json(quality_path)
    costume = _load_json(costume_path)
    prior = _load_json(decision_path)

    retry_attempt = 0
    if isinstance(prior, dict):
        prev_retry = prior.get("policy", {}).get("retry_attempt")
        if isinstance(prev_retry, int) and prev_retry >= 0:
            retry_attempt = prev_retry

    failed_metrics = []
    if isinstance(quality, dict):
        failed_metrics = quality.get("overall", {}).get("failed_metrics", []) or []
        failed_metrics = [str(x) for x in failed_metrics if isinstance(x, str)]

    action = "proceed_finalize"
    reason = "No blocking quality findings."

    costume_fail = False
    if isinstance(costume, dict):
        costume_fail = bool(costume.get("pass") is False)

    if costume_fail:
        action = "block_for_costume"
        reason = "Costume fidelity gate failed; require corrected recast input."
    elif isinstance(quality, dict):
        overall_pass = bool(quality.get("overall", {}).get("pass"))
        if not overall_pass:
            next_retry = retry_attempt + 1
            if next_retry <= max(0, args.max_retries):
                action = "retry_recast"
                retry_attempt = next_retry
                reason = "Quality metrics failed within retry budget; deterministic retry requested."
            else:
                action = "escalate_hitl"
                retry_attempt = next_retry
                reason = "Quality metrics failed beyond retry budget; escalate to explicit HITL."

    segment_plan_path = _find_segment_plan(project_root)
    payload: Dict[str, Any] = {
        "version": "quality_decision.v1",
        "job_id": args.job_id,
        "generated_at": _utc_now(),
        "inputs": {
            "quality_report_relpath": _safe_rel(quality_path, project_root) if quality_path.exists() else None,
            "costume_report_relpath": _safe_rel(costume_path, project_root) if costume_path.exists() else None,
            "segment_stitch_plan_relpath": _safe_rel(segment_plan_path, project_root) if segment_plan_path else None,
            "failed_metrics": failed_metrics,
        },
        "policy": {
            "max_retries": max(0, args.max_retries),
            "retry_attempt": retry_attempt,
        },
        "decision": {
            "action": action,
            "reason": reason,
        },
    }

    _save_json(decision_path, payload)
    print(str(decision_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
