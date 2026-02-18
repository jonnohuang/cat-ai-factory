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

Engine/runtime extras for analyzer + worker stages:

```bash
# Analyzer fallback pose model (recommended on Python 3.12+)
CAF_MOVENET_MODEL_PATH=sandbox/models/movenet_singlepose_lightning_4.tflite

# Optional worker caption synthesis from source media
CAF_ENABLE_WHISPER_CAPTIONS=1
CAF_WHISPER_MODEL=tiny
```

Install baseline packages in active env:

```bash
pip install -r repo/requirements-dev.txt
pip install jsonschema librosa scenedetect soundfile tensorflow openai-whisper torch
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

## Sample Ingest + Promotion Queue (PR-35g MVP)

### 1) Ingest new sample videos (lab-first)

Put source videos under:
- `sandbox/assets/demo/incoming/`

Run deterministic ingest:

```bash
python3 -m repo.tools.ingest_demo_samples
```

Outputs:
- `repo/canon/demo_analyses/<analysis_id>.video_analysis.v1.json`
- `repo/canon/demo_analyses/<analysis_id>.beat_grid.v1.json`
- `repo/canon/demo_analyses/<analysis_id>.pose_checkpoints.v1.json`
- `repo/canon/demo_analyses/<analysis_id>.keyframe_checkpoints.v1.json`
- `repo/canon/demo_analyses/<analysis_id>.caf.video_reverse_prompt.v1.json`
- `repo/canon/demo_analyses/<analysis_id>.segment_stitch_plan.v1.json`
- `repo/canon/demo_analyses/<analysis_id>.sample_ingest_manifest.v1.json`
- `sandbox/logs/lab/sample_ingest_summary.v1.json`

### 2) Create a promotion candidate

```bash
python3 -m repo.tools.create_promotion_candidate \
  --job-id <lab_job_id> \
  --sample-manifest-relpath repo/canon/demo_analyses/<analysis_id>.sample_ingest_manifest.v1.json \
  --pass-rate-delta 0.10 \
  --retry-count-delta -1
```

Output:
- `sandbox/logs/lab/promotions/<candidate_id>.promotion_candidate.v1.json`

### 3) Approve/Reject through inbox contract

Write an inbox action artifact:
- `sandbox/inbox/<action>.json` (version `promotion_action.v1`)

Then process queue:

```bash
python3 -m repo.tools.process_promotion_queue
```

Outputs:
- `repo/shared/promotion_registry.v1.json` (approved promotions)
- `sandbox/logs/lab/promotion_queue_result.v1.json`

Design rule:
- non-CLI promotion remains file-contract driven and auditable.
