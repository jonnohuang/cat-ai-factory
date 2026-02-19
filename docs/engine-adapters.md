# Engine Matrix And Adapters

This guide covers the full CAF media stack:
- core deterministic engines already used in pipeline
- provider adapters used for generation lanes
- authority level for each engine

## Authority Model

- Contract authority:
  - `job.json`, `qc_policy.v1.json`, `qc_report.v1.json`
- Deterministic runtime authority:
  - Controller + Worker decisions from policy/report contracts
- Advisory-only:
  - OpenClaw lab suggestions
  - multimodal diagnostics

## Core Engines (Deterministic Stack)

### Frame Engine
- Tools:
  - `FFmpeg` (keyframes, extraction, transcode)
  - `OpenCV` (frame stats, brightness/palette/flicker metrics)
  - optional vision labeling (advisory enrichment only)
- Plane:
  - planner-side analysis + worker-side deterministic processing
- Main artifacts:
  - frame/keyframe assets under `sandbox/output/<job_id>/frames/**`
  - analysis contracts under `repo/canon/demo_analyses/**` (planner-side canon)

### Motion Engine
- Tools:
  - `MediaPipe Pose` (primary)
  - `MoveNet` (optional/when enabled)
  - `OpenCV optical flow` (motion curves)
- Plane:
  - planner-side analysis contracts (worker reads deterministic outputs only when wired)
- Main artifacts:
  - pose/motion contracts (example families in analyzer outputs)
  - `repo/canon/demo_analyses/*.pose_checkpoints.v1.json`
  - `repo/canon/demo_analyses/*.segment_stitch_plan.v1.json`

### Audio Engine
- Tools:
  - `librosa` (BPM/beat grid/onsets)
  - `FFmpeg loudnorm` (deterministic normalization/mux)
  - optional `Whisper` (captions/subtitle extraction lane)
- Plane:
  - planner/control preprocessing + worker deterministic assembly
- Main artifacts:
  - beat/cue contracts
  - `final.srt` and audio artifacts under `sandbox/output/<job_id>/`

### Editor Engine
- Tools:
  - `FFmpeg` deterministic assembly
  - deterministic segment split/stitch, transitions, watermark, mux
- Plane:
  - Worker only
- Main artifacts:
  - `sandbox/output/<job_id>/final.mp4`
  - `sandbox/output/<job_id>/final.srt`
  - `sandbox/output/<job_id>/result.json`
  - segment artifacts under `sandbox/output/<job_id>/segments/**`

### QC Engine
- Tools:
  - deterministic QC runner + decision engine
  - schema validators + smoke suites
  - optional multimodal diagnostics (advisory)
- Plane:
  - control/QC tools
- Main artifacts:
  - `repo/shared/qc_policy.v1.json`
  - `sandbox/logs/<job_id>/qc/qc_report.v1.json`
  - `sandbox/logs/<job_id>/qc/quality_decision.v1.json`
  - optional:
    - `sandbox/logs/<job_id>/qc/qc_route_advice.v1.json`
    - `sandbox/logs/<job_id>/qc/lab_qc_loop_summary.v1.json`

## Generation/Provider Adapters

### `vertex_veo`
- Type: baseline video generation adapter
- Typical mode: production baseline
- Required env:
  - `VERTEX_PROJECT_ID`
  - `VERTEX_LOCATION`
  - `VERTEX_ACCESS_TOKEN` (or ADC-compatible auth)

### `comfyui_video`
- Type: workflow-driven generation lane
- Typical mode: production or lab (policy-gated)
- Required env:
  - `COMFYUI_BASE_URL`
  - `COMFYUI_WORKFLOW_ID`
- Workflow authority:
  - `workflow_id -> repo/workflows/comfy/<workflow_id>.json`

## Route Mode

Set in `.env`:

```bash
CAF_ENGINE_ROUTE_MODE=production
```

Options:
- `production`: deterministic policy route
- `lab`: experiment/challenger route collection

Guarded trial flag:

```bash
CAF_QC_AUTHORITY_TRIAL=0
```

Keep `0` unless running explicit controlled trials.

## Quick Checks

```bash
python3 -m repo.tools.smoke_planner_comfyui_provider
python3 -m repo.tools.smoke_qc_policy_report_contract
```

See also:
- `docs/lab-mode-runbook.md`
- `docs/comfyui-workflows.md`
- `docs/qc-pipeline-guide.md`
