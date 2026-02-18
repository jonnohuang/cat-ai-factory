# Video Workflow End-to-End

This is the single runbook for CAF’s full multi-stage pipeline:
- user brief input
- planner contract generation
- controller orchestration
- worker multi-stage rendering
- QC gates and routing
- optional external HITL recast
- distribution artifacts

## 0) Pipeline Summary

Canonical flow:
1. User brief/intent input
2. Planner writes `job.json`
3. Controller runs deterministic worker
4. Worker emits output artifacts
5. QC runner + decision artifacts
6. Controller routes (finalize/retry/fallback/escalate)
7. Optional external HITL recast path
8. Ops/distribution artifacts for publishing

## 0.1) Stage Artifact Producer/Consumer Map

| Artifact | Producer | Primary Consumer(s) | Purpose |
|---|---|---|---|
| `sandbox/PRD.json` | User/operator | Planner | High-level brief and constraints |
| `sandbox/inbox/*.json` | Adapters/user/operator | Planner | Structured ingress inputs (optional) |
| `sandbox/jobs/<job_id>.job.json` | Planner | Controller, Worker | Execution authority contract |
| `sandbox/output/<job_id>/frames/**` | Worker (or analyzer tools when enabled) | QC tools, diagnostics, optional frame lanes | Frame snapshots / keyframe inspection |
| `sandbox/output/<job_id>/segments/**` | Worker | QC decision engine, seam analysis | Segment and stitch evaluation inputs |
| `sandbox/output/<job_id>/audio/**` | Worker | QC/audio checks | Audio extraction/mix diagnostics |
| `sandbox/output/<job_id>/final.mp4` | Worker | QC tools, Ops/Distribution, HITL export | Main video output |
| `sandbox/output/<job_id>/final.srt` | Worker | Ops/Distribution, posting bundles | Subtitle artifact |
| `sandbox/output/<job_id>/result.json` | Worker | Controller/QC/ops tools | Render result metadata |
| `sandbox/logs/<job_id>/qc/qc_report.v1.json` | `run_qc_runner` | Decision engine, controller | Normalized gate report |
| `sandbox/logs/<job_id>/qc/quality_decision.v1.json` | `decide_quality_action` | Controller | Deterministic next action |
| `sandbox/dist_artifacts/<job_id>/viggle_pack/**` | HITL export tools | External recast operator | External recast package |
| `sandbox/inbox/viggle-reingest-*.json` | Re-ingest pointer tool | Re-ingest processor | External result handoff |

## 0.2) Engine Feed Wiring

### Current wired pipeline (implemented now)

- Frame engine feed:
  - reads: `job.json`, source media/assets
  - writes: frame/keyframe artifacts under `sandbox/output/<job_id>/frames/**` (when enabled by worker/debug flow)
  - consumed by: QC/debug inspection and downstream tools

- Motion engine feed:
  - reads: analyzer/reference assets and generated outputs
  - writes: analyzer contracts + motion metrics artifacts
  - consumed by: planner hints and QC scoring tools (not direct worker authority)

- Audio engine feed:
  - reads: source audio/media
  - writes: beat/onset metadata and normalized audio outputs
  - consumed by: planner timing hints, worker assembly, QC A/V checks (where configured)

- Editor engine feed (Worker deterministic assembly):
  - reads: `job.json`, assets, staged clips/segments/audio
  - writes: `final.mp4`, `final.srt`, `result.json`, optional debug/stage outputs
  - consumed by: QC and distribution (this is the main production path today)

- QC engine feed:
  - reads: `qc_policy.v1`, worker outputs, stage reports, quality artifacts
  - writes: `qc_report.v1`, `quality_decision.v1`
  - consumed by: controller retry/fallback/escalation routing (production authority)

### Planned target wiring (PR35 direction)

- Motion-conditioned generation path:
  - sample dance trace -> pose-conditioned keyframes -> animation
  - tighter frame/motion coupling before final assembly
- Pose/motion similarity gates become first-class production thresholds.
- ComfyUI workflow registry-driven keyframe generation becomes a stronger upstream feed for video generation.

## 0.3) Active Environment Requirements (Wired Engines)

These are required to run the currently wired deterministic stack in practice:

```bash
# Core deps
pip install -r repo/requirements-dev.txt
pip install jsonschema librosa scenedetect soundfile

# Optional analyzer fallback (MoveNet)
pip install tensorflow

# Optional worker captions stage (Whisper)
pip install openai-whisper torch
```

System tools required on PATH:

```bash
ffmpeg -version
ffprobe -version
```

Required/optional env vars:

```bash
# MoveNet fallback for analyzer (when MediaPipe unavailable)
CAF_MOVENET_MODEL_PATH=sandbox/models/movenet_singlepose_lightning_4.tflite

# Optional Whisper subtitle generation in worker
CAF_ENABLE_WHISPER_CAPTIONS=1
CAF_WHISPER_MODEL=tiny
```

Python caveat:
- `mediapipe` in this repo is currently installed only for Python `<3.12`.
- On Python `3.12+`, analyzer will report `mediapipe=unknown` unless you provide an alternative install path.
- MoveNet fallback is available through `CAF_MOVENET_MODEL_PATH`.

Quick verification:

```bash
python3 -m repo.tools.smoke_worker_engine_policy_runtime
python3 -m repo.tools.smoke_dance_swap
python3 -m repo.tools.smoke_analyzer_core_pack
```

## 1) Stage: User Brief / Input

### Inputs
- `sandbox/PRD.json`
- optional ingress artifacts:
  - `sandbox/inbox/*.json`

### Outputs
- none directly; planner consumes these inputs

## 2) Stage: Planner (Contract Generation)

### Inputs
- `sandbox/PRD.json`
- `sandbox/inbox/*.json` (optional)
- planner reference/canon inputs (read-only), e.g.:
  - `repo/shared/*.json`
  - `repo/canon/demo_analyses/**`

### Command
```bash
python3 -m repo.services.planner.planner_cli \
  --prompt "Mochi dance loop continuity test" \
  --provider vertex_veo \
  --inbox sandbox/inbox \
  --out sandbox/jobs
```

### Outputs
- `sandbox/jobs/<job_id>.job.json`

## 3) Stage: Controller (Ralph Loop)

### Inputs
- `sandbox/jobs/<job_id>.job.json`
- existing `sandbox/output/<job_id>/**` (for idempotent fast-path checks)
- `sandbox/logs/<job_id>/**` (state/history)

### Command
```bash
python3 -m repo.services.orchestrator.ralph_loop \
  --job sandbox/jobs/<job_id>.job.json \
  --max-retries 2
```

### Outputs
- controller state/log artifacts only:
  - `sandbox/logs/<job_id>/**`

## 4) Stage: Worker (Deterministic Multi-Stage Render)

Worker is deterministic and output-bound.

### Inputs
- `sandbox/jobs/<job_id>.job.json`
- `sandbox/assets/**`
- static runtime assets under repo (e.g., watermark)

### Command (direct worker run)
```bash
python3 -m repo.worker.render_ffmpeg \
  --job sandbox/jobs/<job_id>.job.json
```

### Outputs
- required:
  - `sandbox/output/<job_id>/final.mp4`
  - `sandbox/output/<job_id>/result.json`
- optional:
  - `sandbox/output/<job_id>/final.srt`
- stage artifacts when enabled by flow:
  - `sandbox/output/<job_id>/segments/**`
  - `sandbox/output/<job_id>/frames/**`
  - `sandbox/output/<job_id>/audio/**`
  - `sandbox/output/<job_id>/debug/**`

## 5) Stage: QC Runner + Decision

### Inputs
- policy:
  - `repo/shared/qc_policy.v1.json`
- measured/runtime artifacts (job-dependent), typically:
  - `sandbox/logs/<job_id>/qc/recast_quality_report.v1.json`
  - `sandbox/output/<job_id>/segments/segment_stitch_report.v1.json`
  - other QC inputs referenced by contract

### Commands
```bash
python3 -m repo.tools.run_qc_runner --job-id <job_id>
python3 -m repo.tools.decide_quality_action --job-id <job_id> --max-retries 2
python3 -m repo.tools.validate_quality_decision sandbox/logs/<job_id>/qc/quality_decision.v1.json
```

### Outputs
- `sandbox/logs/<job_id>/qc/qc_report.v1.json`
- `sandbox/logs/<job_id>/qc/quality_decision.v1.json`

## 6) Stage: Deterministic Routing (Controller)

### Inputs
- `qc_report.v1.json`
- `quality_decision.v1.json`
- retry budget and controller state

### Outcomes
- finalize
- retry_motion / retry_recast
- fallback provider path
- escalate to HITL/review

### Output paths
- controller logs/state:
  - `sandbox/logs/<job_id>/**`
- output artifacts remain in:
  - `sandbox/output/<job_id>/**`

## 7) Optional Stage: External HITL Recast

Use this only when quality route requires external recast.

### Export
```bash
python3 -m repo.tools.export_viggle_pack --job-id <job_id>
python3 -m repo.tools.validate_viggle_handoff --job-id <job_id>
```

### Re-ingest
```bash
python3 -m repo.tools.create_viggle_reingest_pointer \
  --job-id <job_id> \
  --recast-video-relpath sandbox/assets/<recast_video>.mp4

python3 -m repo.tools.process_viggle_reingest --job-id <job_id>
python3 -m repo.tools.finalize_viggle_reingest --job-id <job_id>
```

### HITL paths
- `sandbox/dist_artifacts/<job_id>/viggle_pack/**`
- `sandbox/inbox/viggle-reingest-<job_id>-*.json`
- updated QC under:
  - `sandbox/logs/<job_id>/qc/**`

## 8) Stage: Ops / Distribution

### Inputs
- immutable worker outputs under `sandbox/output/<job_id>/`
- approval/publish artifacts

### Outputs
- derived distribution artifacts only:
  - `sandbox/dist_artifacts/<job_id>/**`

See:
- `docs/publish-contracts.md`

## 9) Lab Mode Variant (Provider Matrix)

Use for experiment loops:

```bash
python3 -m repo.tools.run_lab_qc_loop \
  --prompt "Mochi dance loop continuity lab" \
  --providers "vertex_veo,wan_dashscope,comfyui_video,sora_lab,meta_ai_lab" \
  --route-mode lab \
  --max-attempts 2 \
  --max-retries 1
```

Outputs:
- per-run QC artifacts under `sandbox/logs/<job_id>/qc/**`
- matrix summary:
  - `sandbox/logs/<best_job_id>/qc/lab_qc_loop_summary.v1.json`

## 9.1) QC Improvement Loop (How To Operate)

Use this repeatable loop to improve quality deterministically:

1. Run baseline job and collect outputs.
2. Build QC report and decision:
```bash
python3 -m repo.tools.run_qc_runner --job-id <job_id>
python3 -m repo.tools.decide_quality_action --job-id <job_id> --max-retries 2
```
3. Inspect failed gates in:
   - `sandbox/logs/<job_id>/qc/qc_report.v1.json`
4. Apply targeted change based on failure type:
   - identity gate failures: tighten identity anchors / frame workflow constraints
   - motion gate failures: improve pose/motion conditioning and segment strategy
   - seam/audio/technical failures: adjust worker/editor parameters
5. Re-run controller (or lab matrix) and compare new QC report.
6. Promote only when repeated runs show measurable lift.

Lab matrix command for rapid iteration:
```bash
python3 -m repo.tools.run_lab_qc_loop \
  --prompt "Mochi dance loop continuity lab" \
  --providers "vertex_veo,wan_dashscope,comfyui_video,sora_lab,meta_ai_lab" \
  --route-mode lab \
  --max-attempts 2 \
  --max-retries 1
```

## 10) Single-Job Example (Quick Path)

```bash
# 1) Plan
python3 -m repo.services.planner.planner_cli \
  --prompt "Mochi dance loop continuity test" \
  --provider vertex_veo \
  --inbox sandbox/inbox \
  --out sandbox/jobs

# 2) Run controller/worker with retries
python3 -m repo.services.orchestrator.ralph_loop \
  --job sandbox/jobs/<job_id>.job.json \
  --max-retries 2

# 3) Build QC report + decision (if needed explicitly)
python3 -m repo.tools.run_qc_runner --job-id <job_id>
python3 -m repo.tools.decide_quality_action --job-id <job_id> --max-retries 2
```

Final outputs to inspect:
- `sandbox/output/<job_id>/final.mp4`
- `sandbox/output/<job_id>/result.json`
- `sandbox/logs/<job_id>/qc/qc_report.v1.json`
- `sandbox/logs/<job_id>/qc/quality_decision.v1.json`

## 11) Asset Onboarding Checklist (New Sample Videos)

Use this flow whenever you introduce a new demo/sample video.

1. Store source sample in runtime assets:
   - `sandbox/assets/demo/<sample_video>.mp4`
2. Run LAB mode first (required for onboarding/tuning):
   - analyze sample behavior
   - generate staged artifacts/reports
   - evaluate QC gates and retry behavior
3. Keep artifacts from lab runs:
   - videos/stage outputs: `sandbox/output/<job_id>/**`
   - QC/reports: `sandbox/logs/<job_id>/qc/**`
4. Promote only validated contracts/workflows to production:
   - update committed policy/workflow/contract files by PR
   - avoid direct runtime-only assumptions in production
5. Run production mode with explicit contract pointers:
   - planner writes `job.json` with asset/contract relpaths
   - controller/worker consume only those explicit pointers

LAB mode matrix command:
```bash
python3 -m repo.tools.run_lab_qc_loop \
  --prompt "Analyze new sample dance video for production onboarding" \
  --providers "vertex_veo,wan_dashscope,comfyui_video,sora_lab,meta_ai_lab" \
  --route-mode lab \
  --max-attempts 2 \
  --max-retries 1
```

Production mode reminder:
```bash
CAF_ENGINE_ROUTE_MODE=production
```

## 11.1) Manual Today vs Autonomous Bridge

Current (manual-heavy):
- run lab mode via CLI
- inspect QC artifacts
- update pointers/policy/workflow by PR
- run production with explicit contract pointers

Bridge now available (PR-35g MVP):
- place new samples in `sandbox/assets/demo/incoming/`
- run `python3 -m repo.tools.ingest_demo_samples` for deterministic lab-first artifact extraction
- planner pointer resolver reads:
  - `repo/canon/demo_analyses/*.sample_ingest_manifest.v1.json`
  - `repo/shared/promotion_registry.v1.json`
- approve/reject promotions using `promotion_action.v1` inbox artifacts
- run `python3 -m repo.tools.process_promotion_queue` to promote approved candidates into registry

## Related Guides

- `docs/lab-mode-runbook.md`
- `docs/engine-adapters.md`
- `docs/comfyui-workflows.md`
- `docs/qc-pipeline-guide.md`
- `docs/external-hitl-workflow.md`
