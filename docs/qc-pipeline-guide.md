# QC Pipeline Guide

This guide explains CAF quality-control gates, contracts, and execution flow.

## QC Authority Contracts

Production routing authority is contract-based:

- policy:
  - `repo/shared/qc_policy.v1.json`
- measured report (per attempt):
  - `sandbox/logs/<job_id>/qc/qc_report.v1.json`
- deterministic controller decision:
  - `sandbox/logs/<job_id>/qc/quality_decision.v1.json`

Controller routing (`pass/retry/fallback/escalate`) must derive from these artifacts plus retry budget.

## Main QC Flow

1. Worker/render produces runtime artifacts.
2. QC runner builds normalized report:
   - `python3 -m repo.tools.run_qc_runner --job-id <job_id>`
3. Decision engine chooses next action:
   - `python3 -m repo.tools.decide_quality_action --job-id <job_id> --max-retries 2`
4. Controller consumes decision and executes deterministic route.

## Typical QC Inputs

Depending on lane and enabled features, QC runner/decision engine may consume:
- `sandbox/logs/<job_id>/qc/recast_quality_report.v1.json`
- `sandbox/logs/<job_id>/qc/costume_fidelity.v1.json`
- `sandbox/output/<job_id>/segments/segment_stitch_report.v1.json`
- continuity/quality target contracts referenced by `job.json`

## Key Output Artifacts

- `qc_report.v1.json`:
  - gate-level statuses (`pass/fail/unknown`)
  - score + threshold per gate
  - `overall.recommended_action`

- `quality_decision.v1.json`:
  - normalized action used by controller
  - input contract pointers/errors
  - retry/fallback metadata

- optional lab artifacts:
  - `qc_route_advice.v1.json` (advisory)
  - `lab_qc_loop_summary.v1.json` (matrix/run summary)

## Gate Categories

Common gate dimensions:
- identity consistency
- motion/temporal stability
- seam/loop quality
- audio-video alignment
- costume/continuity constraints (when required)

For dance/identity-critical jobs, policy should include both:
- identity gates
- pose/motion similarity gates against deterministic dance-trace contracts

## Validation Commands

```bash
python3 -m repo.tools.validate_qc_policy repo/shared/qc_policy.v1.json
python3 -m repo.tools.validate_qc_report sandbox/logs/<job_id>/qc/qc_report.v1.json
python3 -m repo.tools.validate_quality_decision sandbox/logs/<job_id>/qc/quality_decision.v1.json
```

## Smoke Commands

```bash
python3 -m repo.tools.smoke_qc_policy_report_contract
python3 -m repo.tools.smoke_quality_controller_loop
```

## Lab Mode vs Production

- Production:
  - `CAF_ENGINE_ROUTE_MODE=production`
  - deterministic policy/report routing authority

- Lab:
  - `CAF_ENGINE_ROUTE_MODE=lab`
  - advisory experiments allowed
  - authority trial must remain guarded (`CAF_QC_AUTHORITY_TRIAL=0` by default)

## Troubleshooting

- Missing `qc_report.v1.json`:
  - run `run_qc_runner` manually
  - validate `qc_policy.v1.json`
- Decision is always escalate:
  - inspect failed gates and threshold mismatches
  - verify quality target contract pointers in `job.json`
- Unexpected retry loops:
  - check `max-retries`
  - inspect `quality_decision.v1.json` action and reason fields

See also:
- `docs/external-hitl-workflow.md`
