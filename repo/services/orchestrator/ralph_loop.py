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


def run_cmd(cmd: List[str], log_path: pathlib.Path) -> int:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("wb") as f:
        proc = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT)
    return proc.returncode


def load_json_if_exists(path: pathlib.Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


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

    def quality_decision(attempt_id: Optional[str] = None) -> Tuple[str, str]:
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
            return "proceed_finalize", "quality decision tool failed; defaulting to finalize"

        decision_path = qc_dir / "quality_decision.v1.json"
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
        return action_s, reason_s

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
                action, reason = quality_decision()
                if action in ("retry_recast", "retry_motion"):
                    transition(
                        "FAIL_QUALITY",
                        "QUALITY_RETRY",
                        reason=reason,
                    )
                    return 1
                elif action in ("block_for_costume", "escalate_hitl"):
                    transition(
                        "FAIL_QUALITY",
                        "QUALITY_ESCALATED",
                        reason=reason,
                    )
                    return 1
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
            rc = run_cmd(worker_cmd, worker_log)
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
                action, reason = quality_decision(attempt_id=attempt_id)
                if action in ("retry_recast", "retry_motion"):
                    transition(
                        "FAIL_QUALITY",
                        "QUALITY_RETRY",
                        attempt_id=attempt_id,
                        reason=reason,
                    )
                    if attempt_index < total_attempts - 1:
                        continue
                    return 1
                if action in ("block_for_costume", "escalate_hitl"):
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
