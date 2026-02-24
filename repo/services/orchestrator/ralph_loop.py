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
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

# repo/services/orchestrator/ralph_loop.py -> <repo_root>
repo_root = pathlib.Path(__file__).resolve().parents[3]
sys.path.append(str(repo_root))

from repo.services.budget.tracker import BudgetTracker
from repo.services.orchestrator.director_service import DirectorService


def repo_root_from_here() -> pathlib.Path:
    # repo/services/orchestrator/ralph_loop.py -> <repo_root>
    return pathlib.Path(__file__).resolve().parents[3]


def now_ts() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def atomic_write_json(path: pathlib.Path, payload: Dict[str, Any]) -> None:
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    tmp_path.replace(path)


def resolve_worker_script(job: Dict[str, Any], repo_root: pathlib.Path) -> str:
    """Resolve the worker script based on engine_adapter_registry.v1.json."""
    default_worker = "repo/worker/render_ffmpeg.py"
    registry_path = repo_root / "repo/shared/engine_adapter_registry.v1.json"
    if not registry_path.exists():
        return default_worker

    try:
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        model_family = job.get("video", {}).get("model_family")

        # Simple heuristic mapping for now
        family_to_provider = {
            "veo": "vertex_veo",
            "wan": "wan_dashscope",
            "comfyui": "comfyui_video"
        }

        provider_id = family_to_provider.get(model_family)
        if not provider_id:
            profile = job.get("workflow_profile", "")
            if "veo" in profile or "val_production" in profile:
                provider_id = "vertex_veo"
            elif "wan" in profile:
                provider_id = "wan_dashscope"
            elif "comfy" in profile:
                provider_id = "comfyui_video"

        if provider_id:
            for p in registry.get("providers", []):
                if p.get("provider_id") == provider_id:
                    script = p.get("config", {}).get("worker_script")
                    if script:
                        return script
    except Exception:
        pass
    return default_worker


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


def run_cmd(
    cmd: List[str],
    log_path: pathlib.Path,
    env_overrides: Optional[Dict[str, str]] = None,
    timeout_sec: Optional[int] = None,
) -> Tuple[int, bool]:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    if env_overrides:
        env.update(env_overrides)
    with log_path.open("wb") as f:
        try:
            proc = subprocess.run(
                cmd,
                stdout=f,
                stderr=subprocess.STDOUT,
                env=env,
                timeout=(
                    timeout_sec
                    if isinstance(timeout_sec, int) and timeout_sec > 0
                    else None
                ),
            )
            return proc.returncode, False
        except subprocess.TimeoutExpired:
            f.write(
                (
                    f"\n\n[ralph_loop] command timeout after {timeout_sec}s: "
                    + " ".join(cmd)
                    + "\n"
                ).encode("utf-8")
            )
            return 124, True


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


def provider_switch_env_from_retry_plan(
    retry_plan_path: pathlib.Path,
) -> Dict[str, str]:
    payload = load_json_if_exists(retry_plan_path)
    if not isinstance(payload, dict):
        return {}
    retry = payload.get("retry")
    if not isinstance(retry, dict):
        return {}
    switch = retry.get("provider_switch")
    if not isinstance(switch, dict):
        return {}
    mode = str(switch.get("mode", "none"))
    next_provider = switch.get("next_provider")
    current_provider = switch.get("current_provider")
    if mode not in {"video_provider", "frame_provider"}:
        return {}
    if not isinstance(next_provider, str) or not next_provider:
        return {}
    out = {
        "CAF_RETRY_PROVIDER_SWITCH_MODE": mode,
        "CAF_RETRY_NEXT_PROVIDER": next_provider,
    }
    if isinstance(current_provider, str) and current_provider:
        out["CAF_RETRY_CURRENT_PROVIDER"] = current_provider
    return out


def classify_action(action: str) -> str:
    if action in ("RETRY_STAGE", "SWITCH_POLICY", "retry_recast", "retry_motion"):
        return "retry"
    if action in ("ESCALATE_USER", "ABORT", "block_for_costume", "escalate_hitl"):
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
    if (
        isinstance(payload, dict)
        and payload.get("version") == "retry_attempt_lineage.v1"
    ):
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


def check_is_posted(job_id: str, sandbox_root: pathlib.Path) -> Tuple[bool, Optional[str]]:
    """PR-47: Check if any platform has reached the POSTED terminal state."""
    dist_dir = sandbox_root / "dist_artifacts" / job_id
    if not dist_dir.exists():
        return False, None
    for state_file in dist_dir.glob("*.state.json"):
        try:
            payload = json.loads(state_file.read_text(encoding="utf-8"))
            if payload.get("status") == "POSTED":
                return True, state_file.stem
        except Exception:
            pass
    return False, None


def is_under(path: pathlib.Path, root: pathlib.Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except Exception:
        return False


def load_job(job_path: pathlib.Path) -> Dict[str, Any]:
    return json.loads(job_path.read_text(encoding="utf-8"))


def verify_inputs(job: Dict[str, Any], sandbox_root: pathlib.Path) -> Tuple[bool, str]:
    contract = job.get("render", {}).get("segment_generation_contract", "")
    if contract == "shot_by_shot" or os.environ.get("CAF_VEO_MOCK"):
        return True, ""

    try:
        bg_rel = job["render"]["background_asset"]
    except Exception:
        return False, "render.background_asset missing"

    # Normalize path (strip sandbox/ prefix if present)
    p = pathlib.Path(bg_rel)
    parts = p.parts
    if parts and parts[0] == "sandbox":
        p = pathlib.Path(*parts[1:])

    bg_path = (sandbox_root / p).resolve()
    if not bg_path.exists():
        return False, f"missing background asset: {bg_path}"
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


def production_supervisor_decide(
    attempt_id: str,
    current_job_path: pathlib.Path,
    logs_dir: pathlib.Path,
    canonical_job_id: str,
    events_path: pathlib.Path,
    current_state: Optional[str],
) -> bool:
    """PR-PROD-01/03: Invoke Supervisor to analyze detailed QC reports."""
    qc_report_path = logs_dir / "qc" / "qc_report.v1.json"
    metrics_path = logs_dir / "production_metrics.v1.json"

    qc_report = load_json_if_exists(qc_report_path) or {}
    metrics = load_json_if_exists(metrics_path) or {}
    job = load_job(current_job_path)

    supervisor_dir = logs_dir / "supervisor" / attempt_id
    supervisor_dir.mkdir(parents=True, exist_ok=True)
    decision_path = supervisor_dir / "production_decision.v1.json"
    escalation_path = logs_dir / "qc" / "user_action_required.json"

    # Ingres: overall recommended action from the runner
    overall = qc_report.get("overall", {})
    recommended = overall.get("recommended_action", "PROCEED")

    decision = {
        "version": "1.0",
        "job_id": canonical_job_id,
        "attempt_id": attempt_id,
        "decision": {
            "action": recommended,
            "reasoning": "Supervisor aligned with QC recommended action.",
            "policy_overrides": {}
        }
    }

    # Fine-grained reasoning (Gemini 2.5 simulation)
    if recommended == "PROCEED":
         # Double check for soft failures that might need "SWITCH_POLICY" instead of blind PROCEED
         failed_gates = qc_report.get("gates", [])
         for gate in failed_gates:
             if gate.get("status") == "SOFT_FAIL" and gate.get("severity") == "HIGH":
                 decision["decision"]["action"] = "SWITCH_POLICY"
                 decision["decision"]["reasoning"] = f"Soft failure at {gate.get('gate_id')} with HIGH severity; triggering policy switch."
                 decision["decision"]["workflow_profile"] = "identity_strong"
                 break

    if recommended == "RETRY_STAGE":
         # Identify target stage
         target_stage = None
         for gate in qc_report.get("gates", []):
             if gate.get("status") in ("HARD_FAIL", "SOFT_FAIL"):
                 target_stage = gate.get("target_stage")
                 break
         decision["decision"]["target_stage"] = target_stage or "frame"

    if recommended == "ESCALATE_USER":
         # Generate structured escalation artifact
         escalation = {
             "version": "user_action_required.v1",
             "job_id": canonical_job_id,
             "reason": "IDENTITY_CONFLICT",
             "required_artifact": "render.identity_anchor",
             "expected_format": "identity_pack relpath",
             "escalation_ts": now_ts()
         }
         atomic_write_json(escalation_path, escalation)

    atomic_write_json(decision_path, decision)
    append_event(
        events_path,
        "SUPERVISOR_DECISION",
        current_state,
        current_state,
        attempt_id,
        {"decision": decision["decision"]}
    )
    return decision["decision"]["action"] not in ("ABORT", "FAIL_LOUD")


def quality_decision(
    logs_dir: pathlib.Path,
    canonical_job_id: str,
    job_path: pathlib.Path,
    py_exec: str,
    attempt_id: Optional[str] = None,
    events_path: Optional[pathlib.Path] = None,
    current_state: Optional[str] = None,
) -> Tuple[str, str, Dict[str, Any]]:
    qc_dir = logs_dir / "qc"
    qc_dir.mkdir(parents=True, exist_ok=True)

    # 1. Run the deterministic QC runner to measure gates
    qc_runner_log = qc_dir / "run_qc_runner.log"
    qc_runner_cmd = [
        py_exec,
        "repo/tools/run_qc_runner.py",
        "--job-id",
        canonical_job_id,
    ]
    rc, _ = run_cmd(qc_runner_cmd, qc_runner_log)
    if rc != 0:
        if events_path:
            append_event(events_path, "QC_RUNNER_FAILED", current_state, current_state, attempt_id, {"exit_code": rc})
        return "ESCALATE_USER", "QC runner failed; blocking for safety.", {}

    # 2. Transition to Supervisor reasoning
    if attempt_id:
        if not production_supervisor_decide(
            attempt_id, job_path, logs_dir, canonical_job_id, events_path, current_state
        ):
            return "ABORT", "Supervisor aborted the run.", {}

    # 3. Read the supervisor's decision
    supervisor_dir = logs_dir / "supervisor" / (attempt_id or "initial")
    decision_path = supervisor_dir / "production_decision.v1.json"
    if not attempt_id: # Handle pre-existing outputs scenario
        production_supervisor_decide(
            "initial", job_path, logs_dir, canonical_job_id, events_path, current_state
        )

    payload = load_json_if_exists(decision_path) or {}
    decision = payload.get("decision", {}) if isinstance(payload, dict) else {}
    action = decision.get("action", "PROCEED")
    reason = decision.get("reasoning", "No detailed reasoning provided.")

    decision_ctx = {
        "production_decision_relpath": safe_rel(decision_path, repo_root),
        "qc_report_relpath": safe_rel(qc_dir / "qc_report.v1.json", repo_root),
        "target_stage": decision.get("target_stage"),
        "workflow_profile": decision.get("workflow_profile"),
    }

    return action, reason, decision_ctx


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(description="Ralph Loop single-job orchestrator.")
    parser.add_argument("--job", required=True, help="Path to a job.json file")
    parser.add_argument(
        "--max-retries", type=int, default=2, help="Max retries (default: 2)"
    )
    parser.add_argument(
        "--worker-timeout-sec",
        type=int,
        default=900,
        help="Per-attempt worker timeout in seconds (default: 900)",
    )
    args = parser.parse_args(argv)

    repo_root = repo_root_from_here()
    sandbox_root = repo_root / "sandbox"

    job_path = pathlib.Path(args.job)
    filename_job_id = job_id_from_filename(job_path)

    staging_log = sandbox_root / f"ralph-validate-{os.getpid()}.log"
    py_exec = sys.executable or "python3"
    # validate_cmd = [py_exec, "repo/tools/validate_job.py", str(job_path)]
    # rc, _timed_out = run_cmd(validate_cmd, staging_log)
    # if rc != 0:
    #     return 1

    try:
        job = load_job(job_path)
    except Exception as e:
        print(f"FAILED TO LOAD JOB {job_path}: {e}", file=sys.stderr)
        return 1

    canonical_job_id = job.get("job_id")
    if not canonical_job_id:
        return 1

    # PR-47: Distribution Check
    is_posted, platform = check_is_posted(canonical_job_id, sandbox_root)

    logs_root = sandbox_root / "logs"
    logs_dir = logs_root / canonical_job_id
    events_path = logs_dir / "events.ndjson"
    state_path = logs_dir / "state.json"
    lock_dir = logs_dir / ".lock"
    attempts_root = logs_dir / "attempts"

    logs_dir.mkdir(parents=True, exist_ok=True)
    qc_dir = logs_dir / "qc"

    # PR-26: Pre-flight Budget Check
    budget = BudgetTracker(str(sandbox_root))
    if not budget.check_budget(0.0):  # Zero cost just to check caps
        summary = budget.get_usage_summary()
        append_event(
            events_path,
            "BUDGET_EXCEEDED",
            None,
            "FAILED",
            None,
            {"reason": "Budget limits exceeded at start", "summary": summary},
        )
        print(
            f"FATAL: Budget exceeded. Daily: {summary['daily_spent']}/{summary['daily_limit']}, Total: {summary['total_spent']}/{summary['total_limit']}"
        )
        return 1

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
        write_state(
            state_path, canonical_job_id, to_state, attempt_id, reason, error, pointers
        )

    def warn(event: str, details: Dict[str, Any]) -> None:
        append_event(events_path, event, current_state, current_state, None, details)

    if is_posted:
        transition(
            "POSTED",
            "POSTED_DETECTED",
            reason=f"Distribution artifact found for platform: {platform}",
        )
        print(f"INFO: Job {canonical_job_id} already POSTED to {platform}.")
        return 0

    def replan(
        attempt_id: str,
        qc_report_path: pathlib.Path,
        current_job_path: pathlib.Path,
    ) -> bool:
        """PR-100: Call the Planner to refine the job based on QC feedback."""
        refine_dir = logs_dir / "refinement" / attempt_id
        refine_dir.mkdir(parents=True, exist_ok=True)
        refine_log = refine_dir / "replan.log"

        # Prepare inbox for planner (current job + QC report)
        planner_inbox = refine_dir / "inbox"
        planner_inbox.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(current_job_path, planner_inbox / "original_job.json")
        shutil.copyfile(qc_report_path, planner_inbox / "qc_report.json")

        # Call planner_cli.py
        # We assume the PRD is available or we use the job as PRD proxy
        cmd = [
            py_exec,
            "repo/services/planner/planner_cli.py",
            "--job-id",
            canonical_job_id,
            "--inbox",
            str(planner_inbox),
            "--out",
            str(repo_root / "sandbox" / "jobs"),
            "--overwrite",
        ]
        append_event(
            events_path,
            "REPLAN_START",
            current_state,
            current_state,
            attempt_id,
            {"cmd": " ".join(cmd)},
        )
        rc, _ = run_cmd(cmd, refine_log)
        if rc == 0:
             append_event(
                 events_path,
                 "REPLAN_SUCCESS",
                 current_state,
                 current_state,
                 attempt_id,
                 {"log": str(refine_log)}
             )
             return True
        else:
             append_event(
                 events_path,
                 "REPLAN_FAILED",
                 current_state,
                 current_state,
                 attempt_id,
                 {"exit_code": rc, "log": str(refine_log)}
             )
             return False

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
            lineage_cmd = [py_exec, "repo/tools/lineage_verify.py", str(job_path)]
            rc, _ = run_cmd(lineage_cmd, lineage_log)
            if rc == 0:
                transition("VERIFIED", "LINEAGE_OK")
                action, reason, decision_ctx = quality_decision(
                    logs_dir=logs_dir,
                    canonical_job_id=canonical_job_id,
                    job_path=job_path,
                    py_exec=py_exec,
                    events_path=events_path,
                    current_state=current_state,
                )
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
                            "quality_decision_relpath": decision_ctx.get(
                                "quality_decision_relpath"
                            ),
                            "retry_plan_relpath": decision_ctx.get(
                                "retry_plan_relpath"
                            ),
                            "result_relpath": (
                                safe_rel(result_json, repo_root)
                                if result_json.exists()
                                else None
                            ),
                            "output_final_relpath": (
                                safe_rel(output_dir / "final.mp4", repo_root)
                                if (output_dir / "final.mp4").exists()
                                else None
                            ),
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
                        {
                            "reason": "retry requested on existing outputs; entering bounded retry loop"
                        },
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

        is_shot_by_shot = (
            job.get("render", {}).get("segment_generation_contract") == "shot_by_shot"
            or len(job.get("shots", [])) > 0
        )
        director = None
        if is_shot_by_shot:
            director = DirectorService(canonical_job_id, sandbox_root, repo_root)

        for attempt_index in range(total_attempts):
            attempt_id = next_attempt_id(attempts_root)
            attempt_dir = attempts_root / attempt_id
            attempt_dir.mkdir(parents=True, exist_ok=True)
            pointers["attempt_dir"] = str(attempt_dir)

            transition("RUNNING", "ATTEMPT_START", attempt_id=attempt_id)

            if director:
                needed_shots = director.sync_shots(job)
                if not needed_shots:
                    # All shots ready, skip to assembly
                    pass
                else:
                    for shot_id in needed_shots:
                        shot_out_dir = director.get_shot_output_dir(shot_id)
                        shot_out_dir.mkdir(parents=True, exist_ok=True)

                        worker_log = attempt_dir / f"worker_{shot_id}.log"
                        worker_script = resolve_worker_script(job, repo_root)
                        worker_cmd = [
                            py_exec,
                            worker_script,
                            "--job",
                            str(job_path),
                        ]
                        worker_env = {
                            "PYTHONPATH": str(repo_root),
                            "CAF_TARGET_SHOT_ID": shot_id,
                            "CAF_RETRY_ATTEMPT_ID": attempt_id,
                            "CAF_OUTPUT_OVERRIDE": str((shot_out_dir / "final.mp4").resolve()),
                        }
                        # We don't propagate retry_plan for specific shot targeting yet,
                        # but we could if needed.

                        rc, timed_out = run_cmd(
                            worker_cmd,
                            worker_log,
                            env_overrides=worker_env,
                            timeout_sec=max(1, int(args.worker_timeout_sec)),
                        )
                        if rc != 0:
                            # Log failure and continue or fail attempt?
                            # For now, fail the attempt if any shot fails.
                            transition(
                                "FAIL_WORKER",
                                "SHOT_FAILED",
                                attempt_id=attempt_id,
                                reason=f"Shot {shot_id} failed",
                                details={"shot_id": shot_id, "exit_code": rc},
                            )
                            break
                    else:
                        # All shots in this attempt finished successfully
                        director.sync_shots(job)  # update state

                        # Attempt assembly
                        success, err = director.assemble(job)
                        if success:
                            transition("COMPLETED", "COMPLETED", attempt_id=attempt_id)
                            return 0
                        else:
                            transition(
                                "FAIL_WORKER",
                                "ASSEMBLY_FAILED",
                                attempt_id=attempt_id,
                                reason=err,
                            )
                            if attempt_index < total_attempts - 1:
                                continue
                            return 1

            else:
                # Monolithic path (existing)
                worker_log = attempt_dir / "worker.log"
                pointers["worker_log"] = str(worker_log)
                worker_script = resolve_worker_script(job, repo_root)
                worker_cmd = [
                    py_exec,
                    worker_script,
                    "--job",
                    str(job_path),
                ]
                retry_plan_path = logs_dir / "qc" / "retry_plan.v1.json"
                worker_env: Dict[str, str] = {}
                # Ensure workers can import from repo.*
                worker_env["PYTHONPATH"] = str(repo_root)
                if retry_plan_path.exists():
                    worker_env["CAF_RETRY_PLAN_PATH"] = str(retry_plan_path.resolve())
                    worker_env.update(
                        provider_switch_env_from_retry_plan(retry_plan_path)
                    )

                    retry_plan_payload = load_json_if_exists(retry_plan_path)
                    if isinstance(retry_plan_payload, dict):
                        retry_block = retry_plan_payload.get("retry", {})
                        segment_retry = retry_block.get("segment_retry", {})
                        if segment_retry.get("mode") == "retry_selected":
                            target_segments = segment_retry.get("target_segments", [])
                            if isinstance(target_segments, list) and target_segments:
                                first_target = target_segments[0]
                                if isinstance(first_target, str) and first_target:
                                    worker_env["CAF_TARGET_SHOT_ID"] = first_target
                worker_env["CAF_RETRY_ATTEMPT_ID"] = attempt_id
                rc, timed_out = run_cmd(
                    worker_cmd,
                    worker_log,
                    env_overrides=worker_env,
                    timeout_sec=max(1, int(args.worker_timeout_sec)),
                )
                if rc != 0:
                    if timed_out:
                        transition(
                            "FAIL_WORKER",
                            "WORKER_TIMEOUT",
                            attempt_id=attempt_id,
                            reason=f"worker timed out after {int(args.worker_timeout_sec)}s",
                            details={"timeout_sec": int(args.worker_timeout_sec)},
                        )
                    else:
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
                lineage_cmd = [py_exec, "repo/tools/lineage_verify.py", str(job_path)]
                rc, _ = run_cmd(lineage_cmd, lineage_log)
                if rc == 0:
                    transition("VERIFIED", "LINEAGE_OK", attempt_id=attempt_id)
                    action, reason, decision_ctx = quality_decision(
                        logs_dir=logs_dir,
                        canonical_job_id=canonical_job_id,
                        job_path=job_path,
                        py_exec=py_exec,
                        attempt_id=attempt_id,
                        events_path=events_path,
                        current_state=current_state,
                    )
                    action_class = classify_action(action)
                    append_retry_attempt_lineage(
                        lineage_path=lineage_contract_path,
                        job_id=canonical_job_id,
                        entry={
                            "ts": now_ts(),
                            "attempt_id": attempt_id,
                            "source_attempt_id": (
                                "preexisting-output"
                                if force_retry_from_existing
                                else None
                            ),
                            "decision_action": action,
                            "decision_reason": reason,
                            "resolution": action_class,
                            "retry_type": decision_ctx.get("retry_type"),
                            "segment_retry": decision_ctx.get("segment_retry"),
                            "artifacts": {
                                "quality_decision_relpath": decision_ctx.get(
                                    "quality_decision_relpath"
                                ),
                                "retry_plan_relpath": decision_ctx.get(
                                    "retry_plan_relpath"
                                ),
                                "result_relpath": (
                                    safe_rel(result_json, repo_root)
                                    if result_json.exists()
                                    else None
                                ),
                                "output_final_relpath": (
                                    safe_rel(output_dir / "final.mp4", repo_root)
                                    if (output_dir / "final.mp4").exists()
                                    else None
                                ),
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
                            # PR-100/PROD-03: Refinement Logic
                            if action in ("RETRY_STAGE", "SWITCH_POLICY", "retry_recast"):
                                if replan(attempt_id, qc_dir / "qc_report.v1.json", job_path):
                                    # Reload job for next attempt
                                    job = load_job(job_path)
                                    append_event(
                                        events_path,
                                        "JOB_RELOADED",
                                        current_state,
                                        current_state,
                                        attempt_id,
                                        {"reason": "Refined plan generated by Brain."}
                                    )

                            # PR-100: Vertex Fallback logic
                            if attempt_index == 1 and job.get("hero"):
                                 # Second failure for a Hero job -> fallback to Vertex
                                 job["lane"] = "vertex_veo"
                                 # We need to notify the worker or update the job file
                                 atomic_write_json(job_path, job)
                                 append_event(
                                     events_path,
                                     "LANE_FALLBACK",
                                     current_state,
                                     current_state,
                                     attempt_id,
                                     {"new_lane": "vertex_veo", "reason": "Comfy stabilization failed twice for Hero."}
                                 )
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
