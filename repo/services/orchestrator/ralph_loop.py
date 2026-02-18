#!/usr/bin/env python3
"""Ralph Loop orchestrator: single-job CLI (PR-4)."""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone, timezone
from typing import Any, Dict, List, Optional, Tuple


def repo_root_from_here() -> pathlib.Path:
    # repo/services/orchestrator/ralph_loop.py -> <repo_root>
    return pathlib.Path(__file__).resolve().parents[3]


def now_ts() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

def atomic_write_json(path: pathlib.Path, payload: Dict[str, Any]) -> None:
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    tmp_path.replace(path)


def append_event(
    events_path: pathlib.Path,
    event: str,
    from_state: Optional[str],
    to_state: Optional[str],
    attempt_id: Optional[str],
    details: Optional[Dict[str, Any]] = None,
) -> None:
    record = {
        "ts": now_ts(),
        "event": event,
        "from_state": from_state,
        "to_state": to_state,
        "attempt_id": attempt_id,
        "details": details or {},
    }
    with events_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def write_state(
    state_path: pathlib.Path,
    job_id: str,
    state: str,
    attempt_id: Optional[str],
    reason: Optional[str],
    error: Optional[str],
    pointers: Dict[str, Optional[str]],
) -> None:
    payload = {
        "job_id": job_id,
        "state": state,
        "attempt_id": attempt_id,
        "updated_at": now_ts(),
        "reason": reason,
        "error": error,
        "pointers": pointers,
    }
    atomic_write_json(state_path, payload)


def run_cmd(cmd: List[str], log_path: pathlib.Path, env_overrides: Optional[Dict[str, str]] = None) -> int:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    if env_overrides:
        env.update(env_overrides)
    with log_path.open("wb") as f:
        proc = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT, env=env)
    return proc.returncode


def load_json_if_exists(path: pathlib.Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def safe_rel(path: pathlib.Path, root: pathlib.Path) -> Optional[str]:
    try:
        return str(path.resolve().relative_to(root.resolve())).replace("\\", "/")
    except Exception:
        return None


def classify_action(action: str) -> str:
    if action in ("retry_recast", "retry_motion"):
        return "retry"
    if action in ("block_for_costume", "escalate_hitl"):
        return "escalate"
    return "finalize"


def append_retry_attempt_lineage(
    *,
    lineage_path: pathlib.Path,
    job_id: str,
    entry: Dict[str, Any],
) -> None:
    payload = load_json_if_exists(lineage_path)
    attempts: List[Dict[str, Any]] = []
    generated_at = now_ts()
    if isinstance(payload, dict) and payload.get("version") == "retry_attempt_lineage.v1":
        existing_attempts = payload.get("attempts", [])
        if isinstance(existing_attempts, list):
            attempts = [x for x in existing_attempts if isinstance(x, dict)]
        generated_at = str(payload.get("generated_at", generated_at))

    attempts.append(entry)
    out = {
        "version": "retry_attempt_lineage.v1",
        "job_id": job_id,
        "generated_at": generated_at,
        "updated_at": now_ts(),
        "attempts": attempts,
    }
    lineage_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(lineage_path, out)


def job_id_from_filename(job_path: pathlib.Path) -> str:
    name = job_path.name
    if name.endswith(".job.json"):
        return name[: -len(".job.json")]
    if name.endswith(".json"):
        return name[: -len(".json")]
    return job_path.stem


def outputs_status(output_dir: pathlib.Path) -> Tuple[bool, bool, List[str], List[str]]:
    required = ["final.mp4", "final.srt", "result.json"]
    present = [name for name in required if (output_dir / name).exists()]
    missing = [name for name in required if name not in present]
    all_present = len(missing) == 0
    any_present = len(present) > 0
    return all_present, any_present, present, missing


def is_under(path: pathlib.Path, root: pathlib.Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except Exception:
        return False


def load_job(job_path: pathlib.Path) -> Dict[str, Any]:
    return json.loads(job_path.read_text(encoding="utf-8"))


def verify_inputs(job: Dict[str, Any], sandbox_root: pathlib.Path) -> Tuple[bool, str]:
    try:
        bg_rel = job["render"]["background_asset"]
    except Exception:
        return False, "render.background_asset missing"

    bg_path = (sandbox_root / bg_rel).resolve()
    assets_root = (sandbox_root / "assets").resolve()

    if not bg_path.exists():
        return False, f"missing background asset: {bg_path}"
    if not is_under(bg_path, assets_root):
        return False, f"background asset outside /sandbox/assets: {bg_path}"
    return True, ""


def next_attempt_id(attempts_root: pathlib.Path) -> str:
    attempts_root.mkdir(parents=True, exist_ok=True)
    existing = []
    pattern = re.compile(r"run-(\d{4})$")
    for path in attempts_root.iterdir():
        if not path.is_dir():
            continue
        match = pattern.search(path.name)
        if match:
            existing.append(int(match.group(1)))
    next_num = max(existing) + 1 if existing else 1
    return f"run-{next_num:04d}"


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(description="Ralph Loop single-job orchestrator.")
    parser.add_argument("--job", required=True, help="Path to a job.json file")
    parser.add_argument("--max-retries", type=int, default=2, help="Max retries (default: 2)")
    args = parser.parse_args(argv)

    repo_root = repo_root_from_here()
    sandbox_root = repo_root / "sandbox"

    job_path = pathlib.Path(args.job)
    filename_job_id = job_id_from_filename(job_path)

    staging_log = pathlib.Path("/tmp") / f"ralph-validate-{os.getpid()}.log"
    validate_cmd = [
        "python3",
        "repo/tools/validate_job.py",
        str(job_path),
    ]
    rc = run_cmd(validate_cmd, staging_log)
    if rc != 0:
        return 1

    try:
        job = load_job(job_path)
    except Exception:
        return 1

    canonical_job_id = job.get("job_id")
    if not canonical_job_id:
        return 1

    logs_root = sandbox_root / "logs"
    logs_dir = logs_root / canonical_job_id
    events_path = logs_dir / "events.ndjson"
    state_path = logs_dir / "state.json"
    lock_dir = logs_dir / ".lock"
    attempts_root = logs_dir / "attempts"

    logs_dir.mkdir(parents=True, exist_ok=True)

    try:
        os.mkdir(lock_dir)
    except FileExistsError:
        print(f"Lock exists for job_id={canonical_job_id}; exiting.")
        return 0

    current_state: Optional[str] = None
    pointers: Dict[str, Optional[str]] = {
        "result_json": None,
        "attempt_dir": None,
        "validate_log": None,
        "worker_log": None,
        "lineage_log": None,
    }

    def transition(
        to_state: str,
        event: str,
        attempt_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        reason: Optional[str] = None,
        error: Optional[str] = None,
    ) -> None:
        nonlocal current_state
        append_event(events_path, event, current_state, to_state, attempt_id, details)
        current_state = to_state
        write_state(state_path, canonical_job_id, to_state, attempt_id, reason, error, pointers)

    def warn(event: str, details: Dict[str, Any]) -> None:
        append_event(events_path, event, current_state, current_state, None, details)

    def quality_decision(attempt_id: Optional[str] = None) -> Tuple[str, str, Dict[str, Any]]:
        qc_dir = logs_dir / "qc"
        qc_dir.mkdir(parents=True, exist_ok=True)
        decision_log = qc_dir / "quality_decision.log"
        pass_log = qc_dir / "two_pass_orchestration.log"
        pass_cmd = [
            "python3",
            "repo/tools/derive_two_pass_orchestration.py",
            "--job-id",
            canonical_job_id,
        ]
        pass_rc = run_cmd(pass_cmd, pass_log)
        if pass_rc != 0:
            warn("TWO_PASS_ORCHESTRATION_FAILED", {"exit_code": pass_rc})
        decision_cmd = [
            "python3",
            "repo/tools/decide_quality_action.py",
            "--job-id",
            canonical_job_id,
            "--max-retries",
            str(max(0, args.max_retries)),
        ]
        rc = run_cmd(decision_cmd, decision_log)
        if rc != 0:
            warn("QUALITY_DECISION_FAILED", {"exit_code": rc})
            return "escalate_hitl", "quality decision tool failed; finalize gate is fail-closed", {}

        decision_path = qc_dir / "quality_decision.v1.json"
        retry_plan_path = qc_dir / "retry_plan.v1.json"
        finalize_gate_path = qc_dir / "finalize_gate.v1.json"
        advice_path = qc_dir / "qc_route_advice.v1.json"
        payload = load_json_if_exists(decision_path) or {}
        decision = payload.get("decision", {}) if isinstance(payload, dict) else {}
        action = decision.get("action") if isinstance(decision, dict) else None
        reason = decision.get("reason") if isinstance(decision, dict) else None
        action_s = str(action) if isinstance(action, str) and action else "proceed_finalize"
        reason_s = str(reason) if isinstance(reason, str) and reason else "quality decision unavailable"
        append_event(
            events_path,
            "QUALITY_DECISION",
            current_state,
            current_state,
            attempt_id,
            {"action": action_s, "reason": reason_s, "artifact": str(decision_path)},
        )
        advice_payload = load_json_if_exists(advice_path)
        if isinstance(advice_payload, dict) and advice_payload.get("version") == "qc_route_advice.v1":
            advice_action = advice_payload.get("advice", {}).get("recommended_action")
            advice_reason = advice_payload.get("advice", {}).get("reason")
            append_event(
                events_path,
                "QUALITY_ADVISORY",
                current_state,
                current_state,
                attempt_id,
                {
                    "advice_action": advice_action,
                    "advice_reason": advice_reason,
                    "authoritative_action": action_s,
                    "authority_mode": "policy_authoritative",
                    "artifact": str(advice_path),
                },
            )
        retry_plan_payload = load_json_if_exists(retry_plan_path)
        if isinstance(retry_plan_payload, dict):
            retry = retry_plan_payload.get("retry", {})
            source = retry_plan_payload.get("source", {})
            if isinstance(retry, dict) and isinstance(source, dict):
                enabled = bool(retry.get("enabled"))
                retry_type = str(retry.get("retry_type", "none"))
                source_action = str(source.get("action", action_s))
                source_reason = str(source.get("reason", reason_s))
                max_retries = retry.get("max_retries")
                next_attempt = retry.get("next_attempt")
                if (
                    enabled
                    and retry_type in {"motion", "recast"}
                    and isinstance(max_retries, int)
                    and isinstance(next_attempt, int)
                    and next_attempt <= max_retries
                ):
                    mapped_action = "retry_motion" if retry_type == "motion" else "retry_recast"
                    append_event(
                        events_path,
                        "QUALITY_RETRY_PLAN",
                        current_state,
                        current_state,
                        attempt_id,
                        {
                            "mapped_action": mapped_action,
                            "source_action": source_action,
                            "next_attempt": next_attempt,
                            "max_retries": max_retries,
                            "artifact": str(retry_plan_path),
                        },
                    )
                    return mapped_action, source_reason, {
                        "quality_decision_relpath": safe_rel(decision_path, repo_root),
                        "retry_plan_relpath": safe_rel(retry_plan_path, repo_root),
                        "finalize_gate_relpath": safe_rel(finalize_gate_path, repo_root) if finalize_gate_path.exists() else None,
                        "qc_route_advice_relpath": safe_rel(advice_path, repo_root) if advice_path.exists() else None,
                        "retry_type": retry_type,
                        "segment_retry": retry.get("segment_retry"),
                    }
                terminal_state = str(retry_plan_payload.get("state", {}).get("terminal_state", "none"))
                if terminal_state == "block_for_costume":
                    return "block_for_costume", source_reason, {
                        "quality_decision_relpath": safe_rel(decision_path, repo_root),
                        "retry_plan_relpath": safe_rel(retry_plan_path, repo_root),
                        "finalize_gate_relpath": safe_rel(finalize_gate_path, repo_root) if finalize_gate_path.exists() else None,
                        "qc_route_advice_relpath": safe_rel(advice_path, repo_root) if advice_path.exists() else None,
                        "retry_type": "none",
                        "segment_retry": retry.get("segment_retry") if isinstance(retry, dict) else None,
                    }
                if terminal_state == "escalate_hitl":
                    return "escalate_hitl", source_reason, {
                        "quality_decision_relpath": safe_rel(decision_path, repo_root),
                        "retry_plan_relpath": safe_rel(retry_plan_path, repo_root),
                        "finalize_gate_relpath": safe_rel(finalize_gate_path, repo_root) if finalize_gate_path.exists() else None,
                        "qc_route_advice_relpath": safe_rel(advice_path, repo_root) if advice_path.exists() else None,
                        "retry_type": "none",
                        "segment_retry": retry.get("segment_retry") if isinstance(retry, dict) else None,
                    }
        decision_ctx = {
            "quality_decision_relpath": safe_rel(decision_path, repo_root),
            "retry_plan_relpath": safe_rel(retry_plan_path, repo_root) if retry_plan_path.exists() else None,
            "finalize_gate_relpath": safe_rel(finalize_gate_path, repo_root) if finalize_gate_path.exists() else None,
            "qc_route_advice_relpath": safe_rel(advice_path, repo_root) if advice_path.exists() else None,
            "retry_type": None,
            "segment_retry": None,
        }
        gate_payload = load_json_if_exists(finalize_gate_path)
        if isinstance(gate_payload, dict):
            gate = gate_payload.get("gate", {})
            allow_finalize = bool(isinstance(gate, dict) and gate.get("allow_finalize") is True)
            if action_s == "proceed_finalize" and not allow_finalize:
                return "escalate_hitl", "Finalize gate blocked completion.", decision_ctx
        elif action_s == "proceed_finalize":
            return "escalate_hitl", "Finalize gate artifact missing; blocking completion.", decision_ctx
        return action_s, reason_s, decision_ctx

    try:
        validate_log = logs_dir / "validate_job.log"
        pointers["validate_log"] = str(validate_log)
        try:
            shutil.copyfile(staging_log, validate_log)
        except Exception:
            pass

        transition("DISCOVERED", "DISCOVERED")
        transition("VALIDATED", "VALIDATED")

        if canonical_job_id != filename_job_id:
            warn(
                "JOB_ID_MISMATCH",
                {
                    "filename_job_id": filename_job_id,
                    "job_json_job_id": canonical_job_id,
                },
            )

        output_dir = sandbox_root / "output" / canonical_job_id
        result_json = output_dir / "result.json"
        pointers["result_json"] = str(result_json)
        force_retry_from_existing = False
        lineage_contract_path = logs_dir / "qc" / "retry_attempt_lineage.v1.json"

        all_present, any_present, present, missing = outputs_status(output_dir)
        if any_present and not all_present:
            transition(
                "FAIL_OUTPUTS",
                "OUTPUTS_PARTIAL",
                reason="partial outputs present",
                details={"present": present, "missing": missing},
            )

        if all_present:
            transition("OUTPUTS_PRESENT", "OUTPUTS_PRESENT")
            transition("LINEAGE_READY", "LINEAGE_READY")
            lineage_log = logs_dir / "lineage_verify.log"
            pointers["lineage_log"] = str(lineage_log)
            lineage_cmd = [
                "python3",
                "repo/tools/lineage_verify.py",
                str(job_path),
            ]
            rc = run_cmd(lineage_cmd, lineage_log)
            if rc == 0:
                transition("VERIFIED", "LINEAGE_OK")
                action, reason, decision_ctx = quality_decision()
                action_class = classify_action(action)
                append_retry_attempt_lineage(
                    lineage_path=lineage_contract_path,
                    job_id=canonical_job_id,
                    entry={
                        "ts": now_ts(),
                        "attempt_id": "preexisting-output",
                        "source_attempt_id": None,
                        "decision_action": action,
                        "decision_reason": reason,
                        "resolution": action_class,
                        "retry_type": decision_ctx.get("retry_type"),
                        "segment_retry": decision_ctx.get("segment_retry"),
                        "artifacts": {
                            "quality_decision_relpath": decision_ctx.get("quality_decision_relpath"),
                            "retry_plan_relpath": decision_ctx.get("retry_plan_relpath"),
                            "result_relpath": safe_rel(result_json, repo_root) if result_json.exists() else None,
                            "output_final_relpath": safe_rel(output_dir / "final.mp4", repo_root)
                            if (output_dir / "final.mp4").exists()
                            else None,
                        },
                    },
                )
                if action_class == "retry":
                    transition(
                        "FAIL_QUALITY",
                        "QUALITY_RETRY",
                        reason=reason,
                    )
                    if max(0, args.max_retries) == 0:
                        return 1
                    force_retry_from_existing = True
                    append_event(
                        events_path,
                        "QUALITY_RETRY_EXECUTION",
                        current_state,
                        current_state,
                        None,
                        {"reason": "retry requested on existing outputs; entering bounded retry loop"},
                    )
                if action_class == "escalate":
                    transition(
                        "FAIL_QUALITY",
                        "QUALITY_ESCALATED",
                        reason=reason,
                    )
                    return 1
                if action_class == "finalize" and not force_retry_from_existing:
                    transition("COMPLETED", "COMPLETED")
                    return 0
            transition(
                "FAIL_VERIFY",
                "LINEAGE_FAILED",
                reason="lineage verification failed on existing outputs",
                details={"exit_code": rc},
            )

        ok_inputs, msg_inputs = verify_inputs(job, sandbox_root)
        if not ok_inputs:
            transition(
                "FAIL_MISSING_INPUTS",
                "MISSING_INPUTS",
                reason=msg_inputs,
            )
            return 1

        max_retries = max(0, args.max_retries)
        total_attempts = max_retries + 1

        for attempt_index in range(total_attempts):
            attempt_id = next_attempt_id(attempts_root)
            attempt_dir = attempts_root / attempt_id
            attempt_dir.mkdir(parents=True, exist_ok=True)
            pointers["attempt_dir"] = str(attempt_dir)

            transition("RUNNING", "ATTEMPT_START", attempt_id=attempt_id)

            worker_log = attempt_dir / "worker.log"
            pointers["worker_log"] = str(worker_log)
            worker_cmd = ["python3", "repo/worker/render_ffmpeg.py", "--job", str(job_path)]
            retry_plan_path = logs_dir / "qc" / "retry_plan.v1.json"
            worker_env: Dict[str, str] = {}
            if retry_plan_path.exists():
                worker_env["CAF_RETRY_PLAN_PATH"] = str(retry_plan_path.resolve())
            worker_env["CAF_RETRY_ATTEMPT_ID"] = attempt_id
            rc = run_cmd(worker_cmd, worker_log, env_overrides=worker_env)
            if rc != 0:
                transition(
                    "FAIL_WORKER",
                    "WORKER_FAILED",
                    attempt_id=attempt_id,
                    reason="worker failed",
                    details={"exit_code": rc},
                )
                if attempt_index < total_attempts - 1:
                    continue
                return 1

            all_present, any_present, present, missing = outputs_status(output_dir)
            if not all_present:
                transition(
                    "FAIL_OUTPUTS",
                    "OUTPUTS_MISSING",
                    attempt_id=attempt_id,
                    reason="outputs missing after worker",
                    details={"present": present, "missing": missing},
                )
                if attempt_index < total_attempts - 1:
                    continue
                return 1

            transition("OUTPUTS_PRESENT", "OUTPUTS_PRESENT", attempt_id=attempt_id)
            transition("LINEAGE_READY", "LINEAGE_READY", attempt_id=attempt_id)

            lineage_log = attempt_dir / "lineage_verify.log"
            pointers["lineage_log"] = str(lineage_log)
            lineage_cmd = [
                "python3",
                "repo/tools/lineage_verify.py",
                str(job_path),
            ]
            rc = run_cmd(lineage_cmd, lineage_log)
            if rc == 0:
                transition("VERIFIED", "LINEAGE_OK", attempt_id=attempt_id)
                action, reason, decision_ctx = quality_decision(attempt_id=attempt_id)
                action_class = classify_action(action)
                append_retry_attempt_lineage(
                    lineage_path=lineage_contract_path,
                    job_id=canonical_job_id,
                    entry={
                        "ts": now_ts(),
                        "attempt_id": attempt_id,
                        "source_attempt_id": "preexisting-output" if force_retry_from_existing else None,
                        "decision_action": action,
                        "decision_reason": reason,
                        "resolution": action_class,
                        "retry_type": decision_ctx.get("retry_type"),
                        "segment_retry": decision_ctx.get("segment_retry"),
                        "artifacts": {
                            "quality_decision_relpath": decision_ctx.get("quality_decision_relpath"),
                            "retry_plan_relpath": decision_ctx.get("retry_plan_relpath"),
                            "result_relpath": safe_rel(result_json, repo_root) if result_json.exists() else None,
                            "output_final_relpath": safe_rel(output_dir / "final.mp4", repo_root)
                            if (output_dir / "final.mp4").exists()
                            else None,
                        },
                    },
                )
                if action_class == "retry":
                    transition(
                        "FAIL_QUALITY",
                        "QUALITY_RETRY",
                        attempt_id=attempt_id,
                        reason=reason,
                    )
                    if attempt_index < total_attempts - 1:
                        continue
                    return 1
                if action_class == "escalate":
                    transition(
                        "FAIL_QUALITY",
                        "QUALITY_ESCALATED",
                        attempt_id=attempt_id,
                        reason=reason,
                    )
                    return 1
                transition("COMPLETED", "COMPLETED", attempt_id=attempt_id)
                return 0

            transition(
                "FAIL_VERIFY",
                "LINEAGE_FAILED",
                attempt_id=attempt_id,
                reason="lineage verification failed",
                details={"exit_code": rc},
            )
            if attempt_index < total_attempts - 1:
                continue
            return 1

        return 1
    finally:
        try:
            os.rmdir(lock_dir)
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
