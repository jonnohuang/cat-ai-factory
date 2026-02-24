#!/usr/bin/env python3
import json
import os
import pathlib
import sys
from unittest.mock import MagicMock

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT))

# Import ralph_loop logic (we need to be careful as it's a script)
import repo.services.orchestrator.ralph_loop as ralph


def test_supervisor_decisions():
    print("\n--- Verifying Supervisor Reasoning Loop ---")

    # Mocking logs_dir and other dependencies
    job_id = "smoke-supervisor-test"
    logs_dir = REPO_ROOT / "sandbox" / "logs" / job_id
    qc_dir = logs_dir / "qc"
    qc_dir.mkdir(parents=True, exist_ok=True)

    # Scenario: RETRY_STAGE recommended by QC
    print("Testing Scenario: QC recommends RETRY_STAGE (motion)")
    qc_report = {
        "version": "qc_report.v1",
        "overall": {
            "recommended_action": "RETRY_STAGE"
        },
        "gates": [
            {
                "gate_id": "temporal_stability_gate",
                "status": "SOFT_FAIL",
                "target_stage": "motion"
            }
        ]
    }
    (qc_dir / "qc_report.v1.json").write_text(json.dumps(qc_report, indent=2))

    # Create mock job
    job_path = REPO_ROOT / "sandbox" / "jobs" / f"{job_id}.job.json"
    job_path.write_text(json.dumps({"job_id": job_id}, indent=2))

    # Call the method
    ralph.production_supervisor_decide(
        attempt_id="run-0001",
        current_job_path=job_path,
        logs_dir=logs_dir,
        canonical_job_id=job_id,
        events_path=logs_dir / "events.ndjson",
        current_state="RUNNING"
    )

    # Verify decision artifact
    decision_path = logs_dir / "supervisor" / "run-0001" / "production_decision.v1.json"
    decision = json.loads(decision_path.read_text())
    print(f"Supervisor Decision: {decision['decision']['action']}")
    print(f"Target Stage: {decision['decision'].get('target_stage')}")
    assert decision["decision"]["action"] == "RETRY_STAGE"
    assert decision["decision"]["target_stage"] == "motion"

    # Scenario: ESCALATE_USER recommended by QC
    print("\nTesting Scenario: QC recommends ESCALATE_USER")
    qc_report["overall"]["recommended_action"] = "ESCALATE_USER"
    (qc_dir / "qc_report.v1.json").write_text(json.dumps(qc_report, indent=2))

    ralph.production_supervisor_decide(
        attempt_id="run-0002",
        current_job_path=job_path,
        logs_dir=logs_dir,
        canonical_job_id=job_id,
        events_path=logs_dir / "events.ndjson",
        current_state="RUNNING"
    )

    decision_path2 = logs_dir / "supervisor" / "run-0002" / "production_decision.v1.json"
    decision2 = json.loads(decision_path2.read_text())
    print(f"Supervisor Decision: {decision2['decision']['action']}")

    escalation_path = qc_dir / "user_action_required.json"
    assert escalation_path.exists()
    escalation = json.loads(escalation_path.read_text())
    print(f"Escalation Reason: {escalation['reason']}")
    assert escalation["version"] == "user_action_required.v1"

    print("\n[SUPERVISOR TEST PASSED] Decision logic and escalation artifacts verified.")

if __name__ == "__main__":
    test_supervisor_decisions()
