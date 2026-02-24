# QC Pipeline Guide

This guide explains CAF quality-control gates, contracts, and execution flow.

## QC Authority Contracts

Production routing authority is contract-based:

- policy:
  - `repo/shared/qc_policy.v1.json`
- measured report (per attempt):
  - `sandbox/logs/<job_id>/qc/qc_report.v1.json`
- deterministic supervisor decision:
  - `sandbox/logs/<job_id>/qc/production_decision.v1.json`

### Responsibility Model
| Component | Responsibility |
|---|---|
| **QC Gate** | Deterministic measurement + `qc_report.v1.json` |
| **Production Supervisor** | Interpret metrics + select repair policy |
| **Director QC Gate** | Verify storyboard/hook/loop compliance |
| **Controller** | Execute `production_decision.v1.json` |
| **Engine** | Deterministic transformation (No self-healing) |

## Pre-Inference QC Gate (Fail-Loud)

Before expensive GPU/Inference execution, the system MUST pass a "Pre-flight" gate. Failure at this stage terminates the job immediately to prevent resource waste.

- **Check 1: Asset Existence**: Verify `background_asset`, `identity_anchor`, and `pose_guide` exist at their resolved locations.
- **Check 2: Duration Alignment**: Verify that `shot_duration` matches the requested script timing (vs. global video length).
- **Check 3: Contract Validity**: Verify the `motion_contract` is reachable and parsed.
- **Action on Failure**: Exit with error code > 0 and log explicitly as `FAIL_PREFLIGHT_QC`.

1. **Artifact Stage**: `artifact_analyzer` validates inputs -> **Artifact QC**.
2. **Frame Stage**: `frame_engine` (ComfyUI) renders seed -> **Frame QC**.
3. **Motion Stage**: `motion_engine` (Wan) synthesizes motion -> **Motion QC**.
4. **Video Stage**: `video_engine` (Veo3/Stitch) generates video -> **Video QC**.
5. **Final Stage**: `editor_engine` (FFmpeg) assembles output -> **Final QC**.

At each stage:
- **Production Supervisor** (Gemini 2.5) evaluates metrics.
- **Controller** (Ralph Loop) executes repair or proceeds.

## Typical QC Inputs

Depending on lane and enabled features, QC runner/decision engine may consume:
- `sandbox/logs/<job_id>/qc/recast_quality_report.v1.json`
- `sandbox/logs/<job_id>/qc/costume_fidelity.v1.json`
- `repo/canon/viral_patterns/<id>/scorecard.json` (VPL thresholds)
- `sandbox/output/<job_id>/segments/segment_stitch_report.v1.json`
- continuity/quality target contracts referenced by `job.json`

## Key Output Artifacts

- `qc_report.v1.json`:
  - gate-level statuses (`pass/fail/unknown`)
  - gate-level `failure_class` tags (for class-driven routing)
  - score + threshold per gate
  - `overall.failed_failure_classes`
  - `overall.recommended_action`

- `production_decision.v1.json`:
  - `decision.action`: pass/retry/fallback/escalate
  - `decision.workflow_profile`: (e.g., `identity_strong`, `hero_safe`)
  - `decision.parameter_adjustments`: Dynamic overrides (e.g., `max_frames`, `denoise`)
  - `decision.policy_overrides`: (e.g., `pose_coverage_threshold`)

- `production_metrics.v1.json` (Experience Database):
  - `visual_metrics.pose_detection_ratio`
  - `visual_metrics.feline_confidence`
  - `engine_metrics.stage_durations`

- optional lab artifacts:
  - `qc_route_advice.v1.json` (advisory)
  - `lab_qc_loop_summary.v1.json` (matrix/run summary)

## Gate Categories

Common gate dimensions:
- **Technical/Production Lock**: Resolution must be exactly `1080x1080` and frame rate `24 fps`.
- **Infrastructure Check**: High-performance lanes MUST verify MIG GPU availability (L4+).
- **Director / Storyboard Compliance**: Every shot must align with the vision prompts in `storyboard.json`.
- **Viral Engineering (Hook/Loop)**: Verify rhythmic onsets (0-3s) and seamless loop seams as defined in `hook_plan.json` and `loop_plan.json`.
- identity consistency (Hero Anchor similarity)
- motion/temporal stability (Wan 2.2 / Veo3 consistency)
- pose/motion similarity (vs. MediaPipe dance-trace)
- seam/loop quality
- audio-video alignment (Beat-sync check)
- costume/continuity constraints (when required)

For dance/identity-critical jobs, policy should include both:
- identity gates (repo/canon/identities)
- pose/motion similarity gates against deterministic dance-trace contracts (extracted via MediaPipe or Wan 2.2 tokens).

## Validation Commands

```bash
python3 -m repo.tools.validate_qc_policy repo/shared/qc_policy.v1.json
python3 -m repo.tools.validate_qc_report sandbox/logs/<job_id>/qc/qc_report.v1.json
python3 -m repo.tools.validate_quality_decision sandbox/logs/<job_id>/qc/quality_decision.v1.json
```

## Runtime Prereqs For QC-Meaningful Signals

If these are missing, QC can still run but artifacts may degrade to `unknown`/fallback signals.

Install:

```bash
pip install -r repo/requirements-dev.txt
pip install jsonschema librosa scenedetect soundfile tensorflow
```

Configure:

```bash
# MoveNet fallback for analyzer pose extraction
CAF_MOVENET_MODEL_PATH=sandbox/models/movenet_singlepose_lightning_4.tflite
```

Notes:
- MediaPipe is currently Python-version constrained in this repo (`<3.12` marker).
- On Python `3.12+`, expect MoveNet fallback or `mediapipe=unknown` in analyzer tool versions.

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
