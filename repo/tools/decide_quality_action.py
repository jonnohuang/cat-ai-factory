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
from typing import Any, Dict, Optional, Tuple

DEFAULT_QUALITY_TARGETS: dict[str, float] = {
    "identity_consistency": 0.70,
    "mask_edge_bleed": 0.60,
    "temporal_stability": 0.70,
    "loop_seam": 0.70,
    "audio_video": 0.95,
}
IDENTITY_METRICS = {"identity_consistency", "mask_edge_bleed"}
MOTION_METRICS = {"temporal_stability", "loop_seam"}


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


def _job_path_from_job_id(project_root: pathlib.Path, job_id: str) -> Optional[pathlib.Path]:
    p = project_root / "sandbox" / "jobs" / f"{job_id}.job.json"
    if p.exists():
        return p
    return None


def _load_quality_targets_from_job(
    project_root: pathlib.Path,
    job_id: str,
) -> Tuple[Dict[str, float], Optional[pathlib.Path], Optional[str]]:
    targets = dict(DEFAULT_QUALITY_TARGETS)
    job_path = _job_path_from_job_id(project_root, job_id)
    if job_path is None:
        return targets, None, None
    job = _load_json(job_path)
    if not isinstance(job, dict):
        return targets, None, "job contract unreadable"
    quality_target = job.get("quality_target")
    if quality_target is None:
        return targets, None, None
    if not isinstance(quality_target, dict):
        return targets, None, "quality_target must be object"
    relpath = quality_target.get("relpath")
    if not isinstance(relpath, str) or not relpath.startswith("repo/"):
        return targets, None, "quality_target.relpath must be repo-relative"

    contract_path = project_root / relpath
    if not contract_path.exists():
        return targets, contract_path, "quality target contract missing"

    contract = _load_json(contract_path)
    if not isinstance(contract, dict):
        return targets, contract_path, "quality target contract unreadable"
    if contract.get("version") != "quality_target.v1":
        return targets, contract_path, "quality target contract version mismatch"

    thresholds = contract.get("thresholds")
    if not isinstance(thresholds, dict):
        return targets, contract_path, "quality target thresholds missing"

    parsed: Dict[str, float] = {}
    for key in DEFAULT_QUALITY_TARGETS.keys():
        v = thresholds.get(key)
        if not isinstance(v, (int, float)):
            return targets, contract_path, f"quality target threshold missing: {key}"
        f = float(v)
        if not (0.0 <= f <= 1.0):
            return targets, contract_path, f"quality target threshold out of range: {key}"
        parsed[key] = f
    return parsed, contract_path, None


def _load_continuity_pack_from_job(
    project_root: pathlib.Path,
    job_id: str,
) -> Tuple[Optional[Dict[str, Any]], Optional[pathlib.Path], Optional[str]]:
    job_path = _job_path_from_job_id(project_root, job_id)
    if job_path is None:
        return None, None, None
    job = _load_json(job_path)
    if not isinstance(job, dict):
        return None, None, "job contract unreadable"
    continuity = job.get("continuity_pack")
    if continuity is None:
        return None, None, None
    if not isinstance(continuity, dict):
        return None, None, "continuity_pack must be object"
    relpath = continuity.get("relpath")
    if not isinstance(relpath, str) or not relpath.startswith("repo/"):
        return None, None, "continuity_pack.relpath must be repo-relative"
    pack_path = project_root / relpath
    if not pack_path.exists():
        return None, pack_path, "continuity pack missing"
    pack = _load_json(pack_path)
    if not isinstance(pack, dict):
        return None, pack_path, "continuity pack unreadable"
    if pack.get("version") != "episode_continuity_pack.v1":
        return None, pack_path, "continuity pack version mismatch"
    rules = pack.get("rules")
    if not isinstance(rules, dict):
        return None, pack_path, "continuity rules missing"
    if not isinstance(rules.get("require_costume_fidelity"), bool):
        return None, pack_path, "continuity rules require_costume_fidelity missing"
    if not isinstance(rules.get("require_identity_consistency"), bool):
        return None, pack_path, "continuity rules require_identity_consistency missing"
    return pack, pack_path, None


def _load_segment_report(project_root: pathlib.Path, job_id: str) -> Optional[Dict[str, Any]]:
    path = project_root / "sandbox" / "output" / job_id / "segments" / "segment_stitch_report.v1.json"
    return _load_json(path)


def _collect_tuned_failed_metrics(quality: Optional[Dict[str, Any]], quality_targets: Dict[str, float]) -> list[str]:
    if not isinstance(quality, dict):
        return []
    metrics = quality.get("metrics", {})
    if not isinstance(metrics, dict):
        return []
    out: list[str] = []
    for key, target in quality_targets.items():
        metric = metrics.get(key)
        if not isinstance(metric, dict):
            continue
        score = metric.get("score")
        if isinstance(score, (int, float)) and float(score) < target:
            out.append(key)
    return out


def _segment_retry_plan(
    segment_report: Optional[Dict[str, Any]],
    failed_metrics: list[str],
) -> Dict[str, Any]:
    trigger = sorted({m for m in failed_metrics if m in MOTION_METRICS})
    if not trigger:
        return {"mode": "none", "target_segments": [], "trigger_metrics": []}
    if not isinstance(segment_report, dict):
        return {"mode": "retry_all", "target_segments": [], "trigger_metrics": trigger}

    segment_ids: list[str] = []
    if "loop_seam" in trigger:
        seams = segment_report.get("seams", [])
        if isinstance(seams, list):
            for seam in seams:
                if not isinstance(seam, dict):
                    continue
                a = seam.get("from_segment")
                b = seam.get("to_segment")
                if isinstance(a, str) and a.startswith("seg_"):
                    segment_ids.append(a)
                if isinstance(b, str) and b.startswith("seg_"):
                    segment_ids.append(b)

    if not segment_ids and "temporal_stability" in trigger:
        segments = segment_report.get("segments", [])
        if isinstance(segments, list):
            for seg in segments:
                if isinstance(seg, dict):
                    sid = seg.get("segment_id")
                    if isinstance(sid, str) and sid.startswith("seg_"):
                        segment_ids.append(sid)

    dedup = sorted(set(segment_ids))
    if dedup:
        return {"mode": "retry_selected", "target_segments": dedup, "trigger_metrics": trigger}
    return {"mode": "retry_all", "target_segments": [], "trigger_metrics": trigger}


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Deterministic quality decision engine")
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--max-retries", type=int, default=2)
    args = parser.parse_args(argv[1:])

    project_root = _repo_root()
    qc_dir = project_root / "sandbox" / "logs" / args.job_id / "qc"
    quality_path = qc_dir / "recast_quality_report.v1.json"
    costume_path = qc_dir / "costume_fidelity.v1.json"
    two_pass_path = qc_dir / "two_pass_orchestration.v1.json"
    decision_path = qc_dir / "quality_decision.v1.json"

    quality = _load_json(quality_path)
    costume = _load_json(costume_path)
    two_pass = _load_json(two_pass_path)
    segment_report = _load_segment_report(project_root, args.job_id)
    quality_targets, quality_target_path, quality_target_error = _load_quality_targets_from_job(project_root, args.job_id)
    continuity_pack, continuity_pack_path, continuity_pack_error = _load_continuity_pack_from_job(project_root, args.job_id)
    prior = _load_json(decision_path)

    retry_attempt = 0
    if isinstance(prior, dict):
        prev_retry = prior.get("policy", {}).get("retry_attempt")
        if isinstance(prev_retry, int) and prev_retry >= 0:
            retry_attempt = prev_retry

    failed_metrics: list[str] = []
    if isinstance(quality, dict):
        failed_metrics = quality.get("overall", {}).get("failed_metrics", []) or []
        failed_metrics = [str(x) for x in failed_metrics if isinstance(x, str)]
    tuned_failed = _collect_tuned_failed_metrics(quality, quality_targets)
    failed_metrics = sorted(set(failed_metrics + tuned_failed))
    segment_retry = _segment_retry_plan(segment_report, failed_metrics)

    action = "proceed_finalize"
    reason = "No blocking quality findings."

    costume_fail = False
    if isinstance(costume, dict):
        costume_fail = bool(costume.get("pass") is False)

    motion_status = None
    identity_status = None
    if quality_target_error is not None:
        action = "escalate_hitl"
        reason = f"Quality target contract invalid: {quality_target_error}"
    elif continuity_pack_error is not None:
        action = "escalate_hitl"
        reason = f"Continuity pack invalid: {continuity_pack_error}"
    elif isinstance(two_pass, dict):
        motion_status = two_pass.get("passes", {}).get("motion", {}).get("status")
        identity_status = two_pass.get("passes", {}).get("identity", {}).get("status")
        if identity_status == "fail":
            next_retry = retry_attempt + 1
            if next_retry <= max(0, args.max_retries):
                action = "retry_recast"
                retry_attempt = next_retry
                reason = "Identity pass failed within retry budget; deterministic recast retry requested."
            else:
                action = "escalate_hitl"
                retry_attempt = next_retry
                reason = "Identity pass failed beyond retry budget; escalate to explicit HITL."
        elif motion_status == "fail":
            next_retry = retry_attempt + 1
            if next_retry <= max(0, args.max_retries):
                action = "retry_motion"
                retry_attempt = next_retry
                reason = "Motion pass failed within retry budget; deterministic motion retry requested."
            else:
                action = "escalate_hitl"
                retry_attempt = next_retry
                reason = "Motion pass failed beyond retry budget; escalate to explicit HITL."

    continuity_rules = continuity_pack.get("rules", {}) if isinstance(continuity_pack, dict) else {}
    continuity_requires_costume = bool(
        isinstance(continuity_rules, dict) and continuity_rules.get("require_costume_fidelity") is True
    )
    if continuity_requires_costume and not isinstance(costume, dict):
        action = "block_for_costume"
        reason = "Continuity pack requires costume fidelity report; report is missing."
    elif costume_fail:
        action = "block_for_costume"
        reason = "Costume fidelity gate failed; require corrected recast input."
    elif action == "proceed_finalize" and isinstance(quality, dict):
        overall_pass = bool(quality.get("overall", {}).get("pass"))
        if not overall_pass or failed_metrics:
            next_retry = retry_attempt + 1
            if next_retry <= max(0, args.max_retries):
                if failed_metrics and set(failed_metrics).issubset(MOTION_METRICS):
                    action = "retry_motion"
                    reason = "Motion quality metrics failed within retry budget; deterministic motion retry requested."
                else:
                    action = "retry_recast"
                    reason = "Quality metrics failed within retry budget; deterministic retry requested."
                retry_attempt = next_retry
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
            "two_pass_orchestration_relpath": _safe_rel(two_pass_path, project_root) if two_pass_path.exists() else None,
            "quality_target_relpath": _safe_rel(quality_target_path, project_root)
            if quality_target_path is not None and quality_target_path.exists()
            else None,
            "quality_target_contract_error": quality_target_error,
            "continuity_pack_relpath": _safe_rel(continuity_pack_path, project_root)
            if continuity_pack_path is not None and continuity_pack_path.exists()
            else None,
            "continuity_pack_error": continuity_pack_error,
            "segment_stitch_plan_relpath": _safe_rel(segment_plan_path, project_root) if segment_plan_path else None,
            "failed_metrics": failed_metrics,
        },
        "policy": {
            "max_retries": max(0, args.max_retries),
            "retry_attempt": retry_attempt,
            "quality_targets": quality_targets,
        },
        "segment_retry": segment_retry,
        "passes": {
            "motion_status": str(motion_status) if motion_status in {"pass", "fail"} else "unknown",
            "identity_status": str(identity_status) if identity_status in {"pass", "fail"} else "unknown",
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
