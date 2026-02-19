#!/bin/bash
set -e

echo "Running PR-36 Smoke Tests..."

echo "--------------------------------------------------------"
echo "1. Smoke: Pointer Resolution (Fail Loud)"
python3 repo/tools/smoke_planner_pointer_resolution_fail_loud.py

echo "--------------------------------------------------------"
echo "2. Smoke: QC Policy Routing (Contract Check)"
python3 repo/tools/smoke_qc_policy_report_contract.py

echo "--------------------------------------------------------"
echo "3. Smoke: Promotion Queue Processing"
python3 repo/tools/smoke_promotion_queue.py

echo "--------------------------------------------------------"
echo "4. Smoke: QC Unknown Metrics (Fail Closed)"
python3 repo/tools/smoke_qc_unknown_metrics_block.py

echo "--------------------------------------------------------"
echo "5. Validate Key Registries"
python3 repo/shared/hero_registry_validate.py
python3 repo/tools/validate_promotion_registry.py sandbox/logs/lab/smoke_promotion_queue/promotion_registry.v1.json

echo "--------------------------------------------------------"
echo "All PR-36 Smoke Tests Passed!"
