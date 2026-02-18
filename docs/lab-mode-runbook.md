# CAF Lab Mode Runbook

This runbook explains how to use OpenClaw lab mode for quality experiments while keeping production routing deterministic.

## Purpose

Lab mode is for controlled experiments:
- compare providers/adapters
- evaluate quality gates
- collect evidence for policy promotion

Lab mode is not production authority by default.

## Environment Setup

Set in `.env`:

```bash
CAF_ENGINE_ROUTE_MODE=lab
CAF_QC_AUTHORITY_TRIAL=0
```

Common adapter keys:

```bash
VERTEX_PROJECT_ID=...
VERTEX_LOCATION=...
DASHSCOPE_API_KEY=...
COMFYUI_BASE_URL=http://127.0.0.1:8188
COMFYUI_WORKFLOW_ID=caf_dance_loop_v1
GROK_API_KEY=...
SORA_LAB_API_KEY=...
META_AI_LAB_API_KEY=...
META_AI_LAB_BASE_URL=...
```

Production mode:

```bash
CAF_ENGINE_ROUTE_MODE=production
```

## Single Provider Lab Run

```bash
python3 -m repo.tools.run_lab_qc_loop \
  --prompt "Mochi dance loop continuity lab" \
  --provider vertex_veo \
  --route-mode lab \
  --max-attempts 2 \
  --max-retries 1
```

## Provider Matrix Lab Run

```bash
python3 -m repo.tools.run_lab_qc_loop \
  --prompt "Mochi dance loop continuity lab" \
  --providers "vertex_veo,wan_dashscope,comfyui_video,sora_lab,meta_ai_lab" \
  --route-mode lab \
  --max-attempts 2 \
  --max-retries 1
```

## Compare With Production Mode

```bash
python3 -m repo.tools.run_lab_qc_loop \
  --prompt "Mochi dance loop continuity production check" \
  --provider vertex_veo \
  --route-mode production \
  --max-attempts 1 \
  --max-retries 1
```

## Output Artifacts

Key per-job artifacts:
- `sandbox/logs/<job_id>/qc/qc_report.v1.json`
- `sandbox/logs/<job_id>/qc/quality_decision.v1.json`
- `sandbox/logs/<job_id>/qc/lab_qc_loop_summary.v1.json`
- `sandbox/output/<job_id>/final.mp4`

Matrix summary fields to inspect:
- `best_provider`
- `best_job_id`
- `runs[].status`
- `runs[].attempts[].quality_action`

## Promotion Discipline

Use lab mode outputs as evidence only:
- update policy/advisory contracts by PR
- validate with replay/smoke coverage
- promote into production mode explicitly

Do not bypass production policy authority:
- `repo/shared/qc_policy.v1.json`
- `sandbox/logs/<job_id>/qc/qc_report.v1.json`

## Promotion Queue (Planned PR-35g)

Goal:
- reduce manual CLI/path handling for lab-to-production promotions

Planned flow:
1. Lab runs emit promotion candidate artifacts.
2. User approves/rejects candidate through adapter/UI (writes inbox artifact).
3. Promotion processor validates benchmark/policy gates.
4. Promoted contracts/workflows become production-consumable repo-truth.

Planned artifact families:
- `promotion_candidate.v1`
- `promotion_request.v1`
- `promotion_decision.v1`

Design rule:
- even in non-CLI flows, promotion remains file-contract driven and auditable.
