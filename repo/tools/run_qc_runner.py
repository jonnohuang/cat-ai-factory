#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import sys
from typing import Any, Dict, List, Optional


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


def _save_json(path: pathlib.Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _safe_rel(path: pathlib.Path, root: pathlib.Path) -> Optional[str]:
    try:
        return str(path.resolve().relative_to(root.resolve())).replace("\\", "/")
    except Exception:
        return None


def _job_path(root: pathlib.Path, job_id: str) -> pathlib.Path:
    return root / "sandbox" / "jobs" / f"{job_id}.job.json"


def _load_quality_targets_from_job(root: pathlib.Path, job_id: str) -> Dict[str, float]:
    defaults: Dict[str, float] = {
        "identity_consistency": 0.70,
        "mask_edge_bleed": 0.60,
        "temporal_stability": 0.70,
        "loop_seam": 0.70,
        "audio_video": 0.95,
        "costume_fidelity": 1.0,
        "background_stability": 0.80,
        "identity_drift": 0.80,
    }
    job = _load_json(_job_path(root, job_id))
    if not isinstance(job, dict):
        return defaults
    quality_target = job.get("quality_target")
    if not isinstance(quality_target, dict):
        return defaults
    rel = quality_target.get("relpath")
    if not isinstance(rel, str) or not rel.startswith("repo/"):
        return defaults
    contract = _load_json(root / rel)
    if not isinstance(contract, dict) or contract.get("version") != "quality_target.v1":
        return defaults
    thresholds = contract.get("thresholds")
    if not isinstance(thresholds, dict):
        return defaults
    merged = dict(defaults)
    for key in (
        "identity_consistency",
        "mask_edge_bleed",
        "temporal_stability",
        "loop_seam",
        "audio_video",
        "background_stability",
        "identity_drift",
    ):
        v = thresholds.get(key)
        if isinstance(v, (int, float)):
            merged[key] = max(0.0, min(1.0, float(v)))
    return merged


def _load_continuity_require_costume(root: pathlib.Path, job_id: str) -> bool:
    job = _load_json(_job_path(root, job_id))
    if not isinstance(job, dict):
        return False
    continuity = job.get("continuity_pack")
    if not isinstance(continuity, dict):
        return False
    rel = continuity.get("relpath")
    if not isinstance(rel, str) or not rel.startswith("repo/"):
        return False
    pack = _load_json(root / rel)
    if (
        not isinstance(pack, dict)
        or pack.get("version") != "episode_continuity_pack.v1"
    ):
        return False
    rules = pack.get("rules")
    return bool(
        isinstance(rules, dict) and rules.get("require_costume_fidelity") is True
    )


def _metric_gate_status(
    metric_payload: Any, threshold: float
) -> tuple[str, Optional[float], str]:
    if not isinstance(metric_payload, dict):
        return "unknown", None, "metric_missing"
    score = metric_payload.get("score")
    if not isinstance(score, (int, float)):
        return "unknown", None, "score_missing"
    fscore = float(score)
    if fscore >= threshold:
        return "pass", fscore, ""
    return "fail", fscore, "score_below_threshold"


def _choose_recommended_action(
    failed_actions: List[str],
    priorities: List[str],
    fallback_action: str,
) -> str:
    if not failed_actions:
        return "proceed_finalize"
    for action in priorities:
        if action in failed_actions:
            return action
    return fallback_action


def _normalize_missing_report_action(
    policy: Dict[str, Any], fallback_action: str
) -> str:
    raw = policy.get("default_action_on_missing_report")
    if isinstance(raw, str) and raw in {
        "retry_motion",
        "retry_recast",
        "block_for_costume",
        "escalate_hitl",
    }:
        return raw
    return fallback_action


def _build_failure_class_map(policy: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    cfg = policy.get("failure_classification")
    if not isinstance(cfg, dict):
        return out
    classes = cfg.get("classes")
    if not isinstance(classes, list):
        return out
    for row in classes:
        if not isinstance(row, dict):
            continue
        class_id = row.get("class_id")
        action = row.get("action")
        metrics = row.get("metrics")
        if not isinstance(class_id, str) or not class_id:
            continue
        if not isinstance(action, str) or not action:
            continue
        if not isinstance(metrics, list) or not metrics:
            continue
        metric_set = {str(m) for m in metrics if isinstance(m, str) and m}
        if not metric_set:
            continue
        out[class_id] = {"action": action, "metrics": metric_set}
    return out


def _classify_failure(
    metric: str, class_map: Dict[str, Dict[str, Any]]
) -> Optional[str]:
    for class_id, row in class_map.items():
        metrics = row.get("metrics")
        if isinstance(metrics, set) and metric in metrics:
            return class_id
    return None


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Build deterministic qc_report.v1 from policy + measured artifacts"
    )
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--qc-policy-relpath", default="repo/shared/qc_policy.v1.json")
    args = parser.parse_args(argv[1:])

    root = _repo_root()
    qc_dir = root / "sandbox" / "logs" / args.job_id / "qc"
    policy_path = root / args.qc_policy_relpath
    quality_path = qc_dir / "recast_quality_report.v1.json"
    costume_path = qc_dir / "costume_fidelity.v1.json"
    two_pass_path = qc_dir / "two_pass_orchestration.v1.json"
    out_path = qc_dir / "qc_report.v1.json"

    policy = _load_json(policy_path)
    if not isinstance(policy, dict) or policy.get("version") != "qc_policy.v1":
        print("ERROR: qc policy missing or invalid", file=sys.stderr)
        return 1

    quality_targets = _load_quality_targets_from_job(root, args.job_id)
    require_costume = _load_continuity_require_costume(root, args.job_id)
    quality = _load_json(quality_path)
    costume = _load_json(costume_path)

    policy_gates = policy.get("gates", [])
    priorities = [
        str(x)
        for x in policy.get("routing", {}).get("failure_action_priority", [])
        if isinstance(x, str)
    ]
    fallback_action = str(
        policy.get("routing", {}).get("fallback_action", "escalate_hitl")
    )
    missing_report_action = _normalize_missing_report_action(policy, fallback_action)

    gates: List[Dict[str, Any]] = []
    failed_gate_ids: List[str] = []
    failed_actions: List[str] = []
    failed_failure_classes: List[str] = []
    failure_class_map = _build_failure_class_map(policy)

    metrics = quality.get("metrics", {}) if isinstance(quality, dict) else {}

    for gate in policy_gates if isinstance(policy_gates, list) else []:
        if not isinstance(gate, dict):
            continue
        gate_id = str(gate.get("gate_id", "unknown_gate"))
        metric = str(gate.get("metric", "unknown_metric"))
        dimension = str(gate.get("dimension", "technical"))
        failure_action = str(gate.get("failure_action", "escalate_hitl"))
        threshold = float(gate.get("threshold", 1.0))
        threshold = float(quality_targets.get(metric, threshold))
        status = "unknown"
        score: Optional[float] = None
        reason = ""

        if metric == "costume_fidelity":
            if not require_costume:
                status = "pass"
                score = 1.0
                reason = "not_required_by_continuity"
            elif isinstance(costume, dict):
                passed = costume.get("pass")
                status = "pass" if passed is True else "fail"
                score = 1.0 if status == "pass" else 0.0
                reason = "" if status == "pass" else "costume_fidelity_failed"
            else:
                status = "fail"
                score = 0.0
                reason = "costume_report_missing"
        else:
            status, score, reason = _metric_gate_status(metrics.get(metric), threshold)

        gate_entry: Dict[str, Any] = {
            "gate_id": gate_id,
            "metric": metric,
            "dimension": dimension,
            "status": status,
            "score": score,
            "threshold": threshold,
            "failure_action": failure_action,
            "failure_class": None,
        }
        if reason:
            gate_entry["reason"] = reason
        gates.append(gate_entry)

        if status == "fail":
            failed_gate_ids.append(gate_id)
            failure_class = _classify_failure(metric, failure_class_map)
            if failure_class:
                gate_entry["failure_class"] = failure_class
                failed_failure_classes.append(failure_class)
                mapped = failure_class_map.get(failure_class, {}).get("action")
                if isinstance(mapped, str) and mapped:
                    failed_actions.append(mapped)
                    continue
            failed_actions.append(failure_action)
        elif status == "unknown":
            failed_gate_ids.append(gate_id)
            failed_actions.append(missing_report_action)

    recommended_action = _choose_recommended_action(
        failed_actions, priorities, fallback_action
    )
    payload: Dict[str, Any] = {
        "version": "qc_report.v1",
        "job_id": args.job_id,
        "generated_at": _utc_now(),
        "inputs": {
            "qc_policy_relpath": _safe_rel(policy_path, root),
            "quality_report_relpath": (
                _safe_rel(quality_path, root) if quality_path.exists() else None
            ),
            "costume_report_relpath": (
                _safe_rel(costume_path, root) if costume_path.exists() else None
            ),
            "two_pass_orchestration_relpath": (
                _safe_rel(two_pass_path, root) if two_pass_path.exists() else None
            ),
        },
        "gates": gates,
        "overall": {
            "pass": len(failed_gate_ids) == 0,
            "failed_gate_ids": failed_gate_ids,
            "failed_failure_classes": sorted(set(failed_failure_classes)),
            "recommended_action": recommended_action,
        },
    }
    _save_json(out_path, payload)
    print(str(out_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
