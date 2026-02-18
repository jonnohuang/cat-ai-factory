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
import subprocess
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


def _load_qc_policy_from_job(
    project_root: pathlib.Path,
    job_id: str,
) -> Tuple[str, Optional[pathlib.Path], Optional[str], str]:
    default_relpath = "repo/shared/qc_policy.v1.json"
    default_action = "escalate_hitl"
    job_path = _job_path_from_job_id(project_root, job_id)
    if job_path is None:
        policy_path = project_root / default_relpath
        return default_relpath, policy_path if policy_path.exists() else None, None, default_action
    job = _load_json(job_path)
    if not isinstance(job, dict):
        policy_path = project_root / default_relpath
        return default_relpath, policy_path if policy_path.exists() else None, "job contract unreadable", default_action
    quality_policy = job.get("quality_policy")
    relpath = default_relpath
    if isinstance(quality_policy, dict):
        rel = quality_policy.get("relpath")
        if isinstance(rel, str) and rel.startswith("repo/"):
            relpath = rel
    policy_path = project_root / relpath
    if not policy_path.exists():
        return relpath, None, "qc policy contract missing", default_action
    policy = _load_json(policy_path)
    if not isinstance(policy, dict):
        return relpath, policy_path, "qc policy contract unreadable", default_action
    if policy.get("version") != "qc_policy.v1":
        return relpath, policy_path, "qc policy contract version mismatch", default_action
    default_action_value = policy.get("default_action_on_missing_report")
    if isinstance(default_action_value, str):
        default_action = default_action_value
    return relpath, policy_path, None, default_action


def _ensure_qc_report(
    project_root: pathlib.Path,
    job_id: str,
    qc_policy_relpath: str,
) -> Tuple[Optional[pathlib.Path], Optional[str]]:
    cmd = [
        sys.executable,
        "-m",
        "repo.tools.run_qc_runner",
        "--job-id",
        job_id,
        "--qc-policy-relpath",
        qc_policy_relpath,
    ]
    proc = subprocess.run(cmd, cwd=str(project_root), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    report_path = project_root / "sandbox" / "logs" / job_id / "qc" / "qc_report.v1.json"
    if proc.returncode != 0:
        return None, "qc runner execution failed"
    if not report_path.exists():
        return None, "qc report missing after runner execution"
    payload = _load_json(report_path)
    if not isinstance(payload, dict) or payload.get("version") != "qc_report.v1":
        return None, "qc report unreadable or version mismatch"
    return report_path, None


def _emit_qc_route_advice(project_root: pathlib.Path, job_id: str) -> None:
    cmd = [
        sys.executable,
        "-m",
        "repo.tools.generate_qc_route_advice",
        "--job-id",
        job_id,
    ]
    _ = subprocess.run(cmd, cwd=str(project_root), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _load_qc_route_advice(
    project_root: pathlib.Path,
    job_id: str,
) -> Tuple[Optional[pathlib.Path], Optional[Dict[str, Any]]]:
    advice_path = project_root / "sandbox" / "logs" / job_id / "qc" / "qc_route_advice.v1.json"
    payload = _load_json(advice_path)
    if not isinstance(payload, dict):
        return None, None
    if payload.get("version") != "qc_route_advice.v1":
        return None, None
    return advice_path, payload


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


def _as_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        if isinstance(item, str):
            token = item.strip()
            if token:
                out.append(token)
    return out


def _next_provider(order: list[str], current: Optional[str]) -> tuple[Optional[str], Optional[str], Optional[int]]:
    if not order:
        return None, None, None
    if current in order:
        idx = order.index(str(current))
        if idx + 1 < len(order):
            return order[idx], order[idx + 1], idx + 1
        return order[idx], None, None
    if len(order) >= 2:
        return order[0], order[1], 1
    return order[0], None, None


def _build_workflow_preset(
    *,
    project_root: pathlib.Path,
    job_id: str,
    failed_failure_classes: list[str],
) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "mode": "none",
        "preset_id": None,
        "workflow_id": None,
        "failure_class": None,
        "parameter_overrides": {},
    }
    if not failed_failure_classes:
        return out
    job_path = _job_path_from_job_id(project_root, job_id)
    if job_path is None:
        return out
    job = _load_json(job_path)
    if not isinstance(job, dict):
        return out
    quality_policy = job.get("quality_policy")
    relpath = "repo/shared/qc_policy.v1.json"
    if isinstance(quality_policy, dict):
        rel = quality_policy.get("relpath")
        if isinstance(rel, str) and rel.startswith("repo/"):
            relpath = rel
    policy = _load_json(project_root / relpath)
    if not isinstance(policy, dict):
        return out
    presets_cfg = policy.get("workflow_presets")
    if not isinstance(presets_cfg, dict):
        return out
    mappings = presets_cfg.get("class_to_preset")
    if not isinstance(mappings, list):
        return out
    classes = [x for x in failed_failure_classes if isinstance(x, str) and x]
    for cls in classes:
        for row in mappings:
            if not isinstance(row, dict):
                continue
            if row.get("class_id") != cls:
                continue
            preset_id = row.get("preset_id")
            workflow_id = row.get("workflow_id")
            if not isinstance(preset_id, str) or not preset_id:
                continue
            if not isinstance(workflow_id, str) or not workflow_id:
                continue
            overrides = row.get("parameter_overrides")
            out.update(
                {
                    "mode": "comfyui_preset",
                    "preset_id": preset_id,
                    "workflow_id": workflow_id,
                    "failure_class": cls,
                    "parameter_overrides": overrides if isinstance(overrides, dict) else {},
                }
            )
            return out
    return out


def _build_provider_switch(
    *,
    project_root: pathlib.Path,
    job_id: str,
    action: str,
) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "mode": "none",
        "current_provider": None,
        "next_provider": None,
        "provider_order_index": None,
    }
    if action not in {"retry_motion", "retry_recast"}:
        return out
    job_path = _job_path_from_job_id(project_root, job_id)
    if job_path is None:
        return out
    job = _load_json(job_path)
    if not isinstance(job, dict):
        return out
    generation_policy = job.get("generation_policy")
    if not isinstance(generation_policy, dict):
        return out

    video_order = _as_str_list(generation_policy.get("video_provider_order"))
    frame_order = _as_str_list(generation_policy.get("frame_provider_order"))
    selected_video = generation_policy.get("selected_video_provider")
    selected_frame = generation_policy.get("selected_frame_provider")
    selected_video_s = selected_video if isinstance(selected_video, str) and selected_video else None
    selected_frame_s = selected_frame if isinstance(selected_frame, str) and selected_frame else None

    if action == "retry_motion":
        cur, nxt, idx = _next_provider(video_order, selected_video_s)
        if nxt:
            out.update(
                {
                    "mode": "video_provider",
                    "current_provider": cur,
                    "next_provider": nxt,
                    "provider_order_index": idx,
                }
            )
        return out

    cur_f, nxt_f, idx_f = _next_provider(frame_order, selected_frame_s)
    if nxt_f:
        out.update(
            {
                "mode": "frame_provider",
                "current_provider": cur_f,
                "next_provider": nxt_f,
                "provider_order_index": idx_f,
            }
        )
        return out

    cur_v, nxt_v, idx_v = _next_provider(video_order, selected_video_s)
    if nxt_v:
        out.update(
            {
                "mode": "video_provider",
                "current_provider": cur_v,
                "next_provider": nxt_v,
                "provider_order_index": idx_v,
            }
        )
    return out


def _build_retry_plan(
    *,
    job_id: str,
    quality_decision_relpath: str,
    max_retries: int,
    retry_attempt: int,
    action: str,
    reason: str,
    segment_retry: Dict[str, Any],
    provider_switch: Dict[str, Any],
    workflow_preset: Dict[str, Any],
    motion_status: Optional[str],
    identity_status: Optional[str],
) -> Dict[str, Any]:
    retry_type = "none"
    enabled = False
    terminal_state = "none"
    pass_target = "unknown"
    if action == "retry_motion":
        retry_type = "motion"
        enabled = True
        pass_target = "motion"
    elif action == "retry_recast":
        retry_type = "recast"
        enabled = True
        pass_target = "identity"
    elif action in {"block_for_costume", "escalate_hitl"}:
        terminal_state = action

    motion = motion_status if motion_status in {"pass", "fail"} else "unknown"
    identity = identity_status if identity_status in {"pass", "fail"} else "unknown"

    return {
        "version": "retry_plan.v1",
        "job_id": job_id,
        "generated_at": _utc_now(),
        "source": {
            "quality_decision_relpath": quality_decision_relpath,
            "action": action,
            "reason": reason,
        },
        "retry": {
            "enabled": enabled,
            "retry_type": retry_type,
            "next_attempt": retry_attempt,
            "max_retries": max_retries,
            "segment_retry": segment_retry,
            "provider_switch": provider_switch,
            "workflow_preset": workflow_preset,
            "pass_target": pass_target,
        },
        "state": {
            "motion_status": motion,
            "identity_status": identity,
            "terminal_state": terminal_state,
        },
    }


def _build_finalize_gate(
    *,
    job_id: str,
    quality_decision_relpath: str,
    action: str,
    reason: str,
) -> Dict[str, Any]:
    allow_finalize = action == "proceed_finalize"
    gate_status = "pass" if allow_finalize else "block"
    return {
        "version": "finalize_gate.v1",
        "job_id": job_id,
        "generated_at": _utc_now(),
        "source": {
            "quality_decision_relpath": quality_decision_relpath,
            "decision_action": action,
            "decision_reason": reason,
        },
        "gate": {
            "allow_finalize": allow_finalize,
            "status": gate_status,
        },
    }


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
    retry_plan_path = qc_dir / "retry_plan.v1.json"
    finalize_gate_path = qc_dir / "finalize_gate.v1.json"

    quality = _load_json(quality_path)
    costume = _load_json(costume_path)
    two_pass = _load_json(two_pass_path)
    segment_report = _load_segment_report(project_root, args.job_id)
    qc_policy_relpath, qc_policy_path, qc_policy_error, qc_missing_report_action = _load_qc_policy_from_job(
        project_root, args.job_id
    )
    qc_report_path, qc_report_error = _ensure_qc_report(project_root, args.job_id, qc_policy_relpath)
    qc_report = _load_json(qc_report_path) if qc_report_path is not None else None
    if qc_report_path is not None:
        _emit_qc_route_advice(project_root, args.job_id)
    advice_path, advice = _load_qc_route_advice(project_root, args.job_id)
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
    if isinstance(qc_report, dict):
        gates = qc_report.get("gates", [])
        if isinstance(gates, list):
            for gate in gates:
                if isinstance(gate, dict) and gate.get("status") == "fail":
                    metric = gate.get("metric")
                    if isinstance(metric, str):
                        failed_metrics.append(metric)
    failed_metrics = sorted(set(failed_metrics))
    failed_failure_classes: list[str] = []
    if isinstance(qc_report, dict):
        overall = qc_report.get("overall")
        if isinstance(overall, dict):
            failed_failure_classes = [
                str(x)
                for x in overall.get("failed_failure_classes", [])
                if isinstance(x, str) and x
            ]
    failed_failure_classes = sorted(set(failed_failure_classes))
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
    elif qc_policy_error is not None:
        action = "escalate_hitl"
        reason = f"QC policy invalid: {qc_policy_error}"
    elif qc_report_error is not None:
        action = qc_missing_report_action
        reason = f"QC report unavailable: {qc_report_error}"
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
    elif action == "proceed_finalize" and isinstance(qc_report, dict):
        overall = qc_report.get("overall", {})
        overall_pass = bool(isinstance(overall, dict) and overall.get("pass") is True)
        recommended_action = (
            str(overall.get("recommended_action"))
            if isinstance(overall, dict) and isinstance(overall.get("recommended_action"), str)
            else "retry_recast"
        )
        if not overall_pass:
            next_retry = retry_attempt + 1
            if next_retry <= max(0, args.max_retries):
                if recommended_action in {"retry_motion", "retry_recast"}:
                    action = recommended_action
                    reason = f"QC policy route selected {recommended_action} within retry budget."
                elif recommended_action == "block_for_costume":
                    action = "block_for_costume"
                    reason = "QC policy route blocked for costume fidelity."
                else:
                    action = "escalate_hitl"
                    reason = "QC policy route escalated due to failed gates."
                retry_attempt = next_retry
            else:
                action = "escalate_hitl"
                retry_attempt = next_retry
                reason = "QC policy route exceeded retry budget; escalate to explicit HITL."

    advisory_mode_cfg = {}
    authority_cfg = {}
    if qc_policy_path is not None:
        qc_policy = _load_json(qc_policy_path)
        if isinstance(qc_policy, dict):
            if isinstance(qc_policy.get("advisory_mode"), dict):
                advisory_mode_cfg = qc_policy.get("advisory_mode", {})
            if isinstance(qc_policy.get("authority_trial"), dict):
                authority_cfg = qc_policy.get("authority_trial", {})
    authority_trial_env = os.getenv("CAF_QC_AUTHORITY_TRIAL", "0").strip().lower() in {"1", "true", "yes", "on"}
    advisory_enabled = bool(isinstance(advisory_mode_cfg, dict) and advisory_mode_cfg.get("enabled") is True)
    authority_enabled = (
        bool(isinstance(authority_cfg, dict) and authority_cfg.get("enabled") is True) and authority_trial_env
    )
    authority_used = False
    authority_rollback = False
    advice_action = None
    if advisory_enabled and isinstance(advice, dict):
        raw = advice.get("advice")
        if isinstance(raw, dict) and isinstance(raw.get("recommended_action"), str):
            advice_action = str(raw.get("recommended_action"))
    if authority_enabled and isinstance(advice_action, str):
        allowed = authority_cfg.get("allowed_actions", [])
        allowed_actions = {str(x) for x in allowed} if isinstance(allowed, list) else set()
        rollback_action = str(authority_cfg.get("rollback_action", "escalate_hitl"))
        if advice_action in allowed_actions:
            if action != "proceed_finalize" and retry_attempt <= max(0, args.max_retries):
                action = advice_action
                reason = f"Authority-trial override accepted from advisory: {advice_action}."
                authority_used = True
            else:
                action = rollback_action
                reason = "Authority-trial advisory rejected by bounds; rolled back to deterministic policy action."
                authority_rollback = True
        else:
            authority_rollback = True

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
            "qc_policy_relpath": _safe_rel(qc_policy_path, project_root)
            if qc_policy_path is not None and qc_policy_path.exists()
            else qc_policy_relpath,
            "qc_policy_error": qc_policy_error,
            "qc_report_relpath": _safe_rel(qc_report_path, project_root) if qc_report_path is not None else None,
            "qc_report_error": qc_report_error,
            "qc_route_advice_relpath": _safe_rel(advice_path, project_root) if advice_path is not None else None,
            "continuity_pack_relpath": _safe_rel(continuity_pack_path, project_root)
            if continuity_pack_path is not None and continuity_pack_path.exists()
            else None,
            "continuity_pack_error": continuity_pack_error,
            "segment_stitch_plan_relpath": _safe_rel(segment_plan_path, project_root) if segment_plan_path else None,
            "failed_metrics": failed_metrics,
            "failed_failure_classes": failed_failure_classes,
        },
        "policy": {
            "max_retries": max(0, args.max_retries),
            "retry_attempt": retry_attempt,
            "quality_targets": quality_targets,
            "advisory_mode_enabled": advisory_enabled,
            "authority_trial_enabled": authority_enabled,
            "authority_trial_used": authority_used,
            "authority_trial_rollback": authority_rollback,
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
    decision_relpath = _safe_rel(decision_path, project_root) or str(decision_path)
    retry_plan = _build_retry_plan(
        job_id=args.job_id,
        quality_decision_relpath=decision_relpath,
        max_retries=max(0, args.max_retries),
        retry_attempt=retry_attempt,
        action=action,
        reason=reason,
        segment_retry=segment_retry,
        provider_switch=_build_provider_switch(project_root=project_root, job_id=args.job_id, action=action),
        workflow_preset=_build_workflow_preset(
            project_root=project_root,
            job_id=args.job_id,
            failed_failure_classes=failed_failure_classes,
        ),
        motion_status=motion_status,
        identity_status=identity_status,
    )
    _save_json(retry_plan_path, retry_plan)
    finalize_gate = _build_finalize_gate(
        job_id=args.job_id,
        quality_decision_relpath=decision_relpath,
        action=action,
        reason=reason,
    )
    _save_json(finalize_gate_path, finalize_gate)
    print(str(decision_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
