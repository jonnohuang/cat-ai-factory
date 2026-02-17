# CAF — Now (Status + Handoff Ledger)

Single source of truth for current PR state and cross-role handoff context.
All coordination happens via explicit artifacts; this file is the live ledger.

Update rules:
- Keep edits minimal and factual.
- Do NOT rewrite history; update the current PR block only.
- Use placeholders (no project IDs, buckets, secrets).
- Update at every role handoff and at PR closeout.
- Prefer brief diff summaries, not raw patch text.

------------------------------------------------------------

## Current PR

PR: **PR-34.7 — Deterministic quality-controller loop (planning + contracts)**
Last Updated: 2026-02-17

### Status by Role
- ARCH: In Progress (scope/contract lock)
- CODEX: Pending (awaiting ARCH handoff)
- CLOUD-REVIEW: Not Required (PR-34.7 is non-cloud scope)

### Decisions / ADRs Touched
- ADR-0041 (Video Analyzer planner-side canon contracts)
- ADR-0042 (Dance Swap v1 deterministic lane)
- ADR-0040 (Media Stack v1 stage contracts)
- ADR-0043 (Mode B default strategy)
- ADR-0044 (External HITL recast boundary)

### What Changed (Diff Summary)
- Added PR-34.7f facts-only planner guard + analyzer fact completeness:
  - `repo/shared/caf.video_reverse_prompt.v1.schema.json` expanded with `truth.visual_facts` plus shot-level camera/brightness/palette fact fields
  - `repo/tools/build_analyzer_core_pack.py` now emits deterministic brightness/palette stats and basic camera movement mode/confidence
  - `repo/services/planner/planner_cli.py` now enforces facts-only guard in reverse-analysis mode and fails loud on unsupported claims
  - `repo/tools/validate_planner_facts_only.py` added for deterministic facts-grounding checks
  - `repo/tools/smoke_planner_facts_only.py` added for repeatable facts-only guard smoke validation
- Added PR-34.7b planner quality wiring:
  - `repo/services/planner/planner_cli.py` now loads reverse-analysis/checkpoint artifacts into `quality_context`
  - deterministic planner shot-timing hints now consume reverse-analysis timestamps
- Added PR-34.7c segment-stitch contracts + planner wiring:
  - `repo/shared/segment_stitch_plan.v1.schema.json`
  - `repo/examples/segment_stitch_plan.v1.example.json`
  - `repo/tools/validate_segment_stitch_plan.py`
  - planner now consumes segment-stitch anchors for deterministic shot timing
- Added PR-34.7d quality-policy decision engine + controller integration:
  - `repo/shared/quality_decision.v1.schema.json`
  - `repo/examples/quality_decision.v1.example.json`
  - `repo/tools/decide_quality_action.py`
  - `repo/tools/validate_quality_decision.py`
  - `repo/services/orchestrator/ralph_loop.py` now emits/consumes deterministic quality decisions for bounded retry/escalation
- Added PR-34.7e analyzer core pack implementation:
  - `repo/tools/build_analyzer_core_pack.py`
  - `repo/tools/smoke_analyzer_core_pack.py`
  - outputs canonical artifacts (`beat_grid.v1`, `pose_checkpoints.v1`, `keyframe_checkpoints.v1`, `caf.video_reverse_prompt.v1`, `segment_stitch_plan.v1`)
- Dependencies updated:
  - `repo/requirements-dev.txt` adds optional `scenedetect`, `librosa`, and `mediapipe` marker for analyzer-core extraction
- PR-34.7b..PR-34.7e smoke validation (Conda `cat-ai-factory`):
  - `python -m py_compile repo/services/planner/planner_cli.py repo/services/orchestrator/ralph_loop.py repo/tools/validate_segment_stitch_plan.py repo/tools/decide_quality_action.py repo/tools/validate_quality_decision.py repo/tools/build_analyzer_core_pack.py repo/tools/smoke_analyzer_core_pack.py` passed
  - `python -m repo.tools.validate_segment_stitch_plan repo/examples/segment_stitch_plan.v1.example.json` passed
  - `python -m repo.tools.validate_quality_decision repo/examples/quality_decision.v1.example.json` passed
  - `python -m repo.tools.decide_quality_action --job-id pr347d-smoke --max-retries 2` passed and produced decision artifact
  - `python -m repo.tools.smoke_analyzer_core_pack` passed
- Added PR-34.7a reverse-analysis contract artifacts:
  - `repo/shared/caf.video_reverse_prompt.v1.schema.json`
  - `repo/shared/beat_grid.v1.schema.json`
  - `repo/shared/pose_checkpoints.v1.schema.json`
  - `repo/shared/keyframe_checkpoints.v1.schema.json`
- Added PR-34.7a examples + deterministic validator:
  - `repo/examples/caf.video_reverse_prompt.v1.example.json`
  - `repo/examples/beat_grid.v1.example.json`
  - `repo/examples/pose_checkpoints.v1.example.json`
  - `repo/examples/keyframe_checkpoints.v1.example.json`
  - `repo/tools/validate_reverse_analysis_contracts.py`
  - `repo/analysis/vendor/README.md`
- PR-34.7a smoke validation (Conda `cat-ai-factory`):
  - `python -m py_compile repo/tools/validate_reverse_analysis_contracts.py` passed
  - `python -m repo.tools.validate_reverse_analysis_contracts --reverse repo/examples/caf.video_reverse_prompt.v1.example.json --beat repo/examples/beat_grid.v1.example.json --pose repo/examples/pose_checkpoints.v1.example.json --keyframes repo/examples/keyframe_checkpoints.v1.example.json` passed
- `docs/PR_PROJECT_PLAN.md`:
  - added explicit ADR-required notes for PR-34.6 and PR-34.7 before implementation kickoff.
- `docs/system-requirements.md`:
  - added FR-28.5 deterministic quality-controller loop requirements (artifact-driven decision, bounded retries, explicit escalation).
- `docs/PR_PROJECT_PLAN.md`:
  - PR-31 status updated to COMPLETED
  - PR-32 status updated to COMPLETED
  - PR-32.1 status updated to COMPLETED
  - PR-32.2 status updated to COMPLETED
  - PR-33 status updated to COMPLETED
  - PR-33.1 status updated to COMPLETED
  - PR-33.2 status updated to COMPLETED
  - PR-33.3 status updated to COMPLETED
  - PR-34 status updated to COMPLETED
  - PR-34.1 status updated to COMPLETED
  - PR-34.2 status updated to COMPLETED
  - PR-34.3 status updated to COMPLETED
  - PR-34.4 status updated to COMPLETED
  - PR-34.5 status updated to COMPLETED
  - added implementation sub-PRs:
    - PR-32.1 (analyzer runtime implementation)
    - PR-33.1 (Dance Swap deterministic recipe implementation)
    - PR-34.1 (external HITL recast flow implementation)
  - added additional sub-PR planning scopes:
    - PR-32.2 (voice/style registries contracts + validation)
    - PR-33.2 (Media Stack v1 staged implementation)
    - PR-33.3 (optional Mode B contract expansion)
    - PR-34.2 (HITL lifecycle + inbox pointer contracts)
    - PR-34.3 (`viggle_pack.v1` schema + validation)
    - PR-34.4 (recast quality gates + deterministic scoring)
    - PR-34.5 (recast benchmark regression harness)
- Docs alignment updates for new sub-PR scope:
  - `docs/system-requirements.md`:
    - FR-26.2 (voice/style registries)
    - FR-27.1 (optional Mode B planning contracts)
    - FR-28.1 (HITL lifecycle + pack/pointer validation contracts)
    - FR-28.2 (recast quality gates + deterministic scoring)
    - FR-28.3 (recast benchmark regression harness)
  - `docs/architecture.md`:
    - added voice/style registry posture + optional Mode B contract note
    - added explicit HITL lifecycle/pointer/pack-schema notes
  - `AGENTS.md`:
    - added planner/control voice/style registry references
    - added optional `viggle_pack.v1` validation schema note
- Added PR-32 planner-only Video Analyzer contracts:
  - `repo/shared/video_analysis.v1.schema.json`
  - `repo/shared/video_analysis_index.v1.schema.json`
  - `repo/shared/video_analysis_query.v1.schema.json`
  - `repo/shared/video_analysis_query_result.v1.schema.json`
- Added PR-32 canon metadata samples and index:
  - `repo/canon/demo_analyses/video-analysis-cat-kick-spin.json`
  - `repo/canon/demo_analyses/video-analysis-cat-duckwalk-loop.json`
  - `repo/canon/demo_analyses/video_analysis_index.v1.json`
  - `repo/canon/demo_analyses/README.md`
- Added PR-32 examples:
  - `repo/examples/video_analysis.v1.example.json`
  - `repo/examples/video_analysis_query.v1.example.json`
  - `repo/examples/video_analysis_query_result.v1.example.json`
- Added PR-32 deterministic validation glue:
  - `repo/tools/validate_video_analysis.py`
  - enforces cross-field timing semantics (`end_sec > start_sec`, `loop_end_sec > loop_start_sec`)
- Smoke validation (Conda `cat-ai-factory`):
  - `jsonschema` available (`4.26.0`)
  - all PR-32 schema/example/canon validations passed
  - `validate_video_analysis.py` passed for canon samples + example
- PR-32 closeout:
  - contracts/examples/canon samples + deterministic validation glue completed and verified
  - roadmap + docs alignment updated for implementation handoff
- Added PR-32.1 analyzer runtime implementation:
  - `repo/tools/analyze_video.py`
  - deterministic offline tool: video input -> `video_analysis.v1` output
  - optional index upsert to `video_analysis_index.v1`
  - OpenCV-aware path implemented with deterministic fallback when `cv2` is unavailable
- `repo/requirements-dev.txt`:
  - added optional deterministic CV dependency:
    - `opencv-python-headless>=4.10.0`
- PR-32.1 smoke validation (Conda `cat-ai-factory`):
  - generated local sample video and produced schema-valid analysis output
  - `validate_video_analysis.py` passed on generated output
  - optional index-update path validated, then cleaned to keep repo diff focused
- PR-32.1 closeout:
  - analyzer runtime implementation completed with OpenCV-aware deterministic fallback
  - requirements/ledger alignment updated for CV dependency visibility
- Added PR-32.2 voice/style registry contracts + examples + validators:
  - `repo/shared/voice_registry.v1.schema.json`
  - `repo/shared/style_registry.v1.schema.json`
  - `repo/shared/voice_registry.v1.json`
  - `repo/shared/style_registry.v1.json`
  - `repo/examples/voice_registry.v1.example.json`
  - `repo/examples/style_registry.v1.example.json`
  - `repo/tools/validate_voice_registry.py`
  - `repo/tools/validate_style_registry.py`
- PR-32.2 smoke validation (Conda `cat-ai-factory`):
  - registry schemas/examples JSON parse checks passed
  - `validate_voice_registry.py` passed
  - `validate_style_registry.py` passed
- Added PR-33 Dance Swap contracts + examples + validator:
  - `repo/shared/dance_swap_loop.v1.schema.json`
  - `repo/shared/dance_swap_tracks.v1.schema.json`
  - `repo/shared/dance_swap_beatflow.v1.schema.json`
  - `repo/examples/dance_swap_loop.v1.example.json`
  - `repo/examples/dance_swap_tracks.v1.example.json`
  - `repo/examples/dance_swap_beatflow.v1.example.json`
  - `repo/tools/validate_dance_swap_contracts.py`
- PR-33 smoke validation (Conda `cat-ai-factory`):
  - dance swap schemas/examples JSON parse checks passed
  - `validate_dance_swap_contracts.py` passed on full example set
  - negative case confirms fail-loud semantics (invalid loop bounds rejected)
- Added PR-33.1 Dance Swap deterministic implementation wiring:
  - `repo/worker/render_ffmpeg.py`:
    - adds `lane == "dance_swap"` routing
    - resolves and validates explicit artifacts:
      - `dance_swap_loop.v1`
      - `dance_swap_tracks.v1`
      - optional `dance_swap_beatflow.v1`
    - enforces fail-loud checks for source-video consistency, loop bounds, subject selection, and mask path existence
    - derives deterministic slot geometry/motion from tracks (and optional beatflow timing)
  - `repo/shared/job.schema.json`:
    - adds `lane: dance_swap`
    - adds `dance_swap` job block:
      - `loop_artifact`
      - `tracks_artifact`
      - optional `beatflow_artifact`
      - `foreground_asset`
      - optional `subject_id`
  - `repo/tools/validate_job.py`:
    - adds minimal-v1 fail-loud checks for `lane=dance_swap` required fields
  - Added smoke runner:
    - `repo/tools/smoke_dance_swap.py`
    - creates deterministic Dance Swap artifacts/job and executes:
      - contract validator
      - job validator
      - worker render
- PR-33.1 smoke validation (Conda `cat-ai-factory`):
  - `python -m py_compile repo/worker/render_ffmpeg.py repo/tools/validate_job.py repo/tools/smoke_dance_swap.py` passed
  - `python -m repo.tools.validate_dance_swap_contracts --loop repo/examples/dance_swap_loop.v1.example.json --tracks repo/examples/dance_swap_tracks.v1.example.json --beatflow repo/examples/dance_swap_beatflow.v1.example.json` passed
  - `python repo/tools/smoke_dance_swap.py` passed and produced:
    - `sandbox/output/smoke-dance-swap-v1/final.mp4`
    - `sandbox/output/smoke-dance-swap-v1/result.json`
- Added PR-33.2 Media Stack v1 staged implementation:
  - `repo/worker/render_ffmpeg.py`:
    - emits deterministic stage outputs under `sandbox/output/<job_id>/**`:
      - `frames/frame_*.png` + `frames/frame_manifest.v1.json`
      - `audio/mix.wav` + `audio/audio_manifest.v1.json`
      - `edit/timeline.v1.json`
      - `render/render_manifest.v1.json`
    - adds `media_stack` pointers in `result.json`
  - Added Media Stack v1 schemas:
    - `repo/shared/frame_manifest.v1.schema.json`
    - `repo/shared/audio_manifest.v1.schema.json`
    - `repo/shared/timeline.v1.schema.json`
    - `repo/shared/render_manifest.v1.schema.json`
  - Added Media Stack v1 examples:
    - `repo/examples/frame_manifest.v1.example.json`
    - `repo/examples/audio_manifest.v1.example.json`
    - `repo/examples/timeline.v1.example.json`
    - `repo/examples/render_manifest.v1.example.json`
  - Added validators/smoke tooling:
    - `repo/tools/validate_media_stack_manifests.py`
    - `repo/tools/smoke_media_stack.py`
- PR-33.2 smoke validation (Conda `cat-ai-factory`):
  - `python -m py_compile repo/worker/render_ffmpeg.py repo/tools/validate_media_stack_manifests.py repo/tools/smoke_media_stack.py` passed
  - `python -m repo.tools.smoke_media_stack` passed
  - generated and validated:
    - `sandbox/output/mochi-dino-replace-smoke-20240515/frames/frame_manifest.v1.json`
    - `sandbox/output/mochi-dino-replace-smoke-20240515/audio/audio_manifest.v1.json`
    - `sandbox/output/mochi-dino-replace-smoke-20240515/edit/timeline.v1.json`
    - `sandbox/output/mochi-dino-replace-smoke-20240515/render/render_manifest.v1.json`
- Added PR-33.3 Mode B optional contracts:
  - `repo/shared/script_plan.v1.schema.json`
  - `repo/shared/identity_anchor.v1.schema.json`
  - `repo/shared/storyboard.v1.schema.json`
  - `repo/examples/script_plan.v1.example.json`
  - `repo/examples/identity_anchor.v1.example.json`
  - `repo/examples/storyboard.v1.example.json`
  - `repo/tools/validate_mode_b_contracts.py`
  - `repo/tools/smoke_mode_b_contracts.py`
- PR-33.3 smoke validation (Conda `cat-ai-factory`):
  - `python -m py_compile repo/tools/validate_mode_b_contracts.py repo/tools/smoke_mode_b_contracts.py` passed
  - `python -m repo.tools.smoke_mode_b_contracts` passed
- Added PR-34.x external HITL recast contracts + implementation:
  - Schemas:
    - `repo/shared/viggle_pack.v1.schema.json`
    - `repo/shared/external_recast_lifecycle.v1.schema.json`
    - `repo/shared/viggle_reingest_pointer.v1.schema.json`
  - Examples:
    - `repo/examples/viggle_pack.v1.example.json`
    - `repo/examples/external_recast_lifecycle.v1.example.json`
    - `repo/examples/viggle_reingest_pointer.v1.example.json`
  - Tools:
    - `repo/tools/export_viggle_pack.py`
    - `repo/tools/create_viggle_reingest_pointer.py`
    - `repo/tools/process_viggle_reingest.py`
    - `repo/tools/validate_viggle_handoff.py`
    - `repo/tools/smoke_viggle_handoff.py`
- PR-34.x smoke validation (Conda `cat-ai-factory`):
  - `python -m py_compile repo/tools/export_viggle_pack.py repo/tools/create_viggle_reingest_pointer.py repo/tools/process_viggle_reingest.py repo/tools/validate_viggle_handoff.py repo/tools/smoke_viggle_handoff.py` passed
  - `python -m repo.tools.smoke_viggle_handoff` passed
  - generated and validated:
    - `sandbox/dist_artifacts/mochi-dino-replace-smoke-20240515/viggle_pack/viggle_pack.v1.json`
    - `sandbox/dist_artifacts/mochi-dino-replace-smoke-20240515/viggle_pack/external_recast_lifecycle.v1.json`
    - `sandbox/inbox/viggle-reingest-mochi-dino-replace-smoke-20240515-*.json`
- Added PR-34.4 deterministic quality-gate scoring:
  - schema:
    - `repo/shared/recast_quality_report.v1.schema.json`
  - example:
    - `repo/examples/recast_quality_report.v1.example.json`
  - tools:
    - `repo/tools/score_recast_quality.py`
    - `repo/tools/validate_recast_quality_report.py`
    - `repo/tools/smoke_recast_quality.py`
- PR-34.4 smoke validation (Conda `cat-ai-factory`):
  - `python -m py_compile repo/tools/score_recast_quality.py repo/tools/validate_recast_quality_report.py repo/tools/smoke_recast_quality.py` passed
  - `python -m repo.tools.smoke_recast_quality` passed
  - `python -m repo.tools.validate_recast_quality_report sandbox/logs/mochi-dino-replace-smoke-20240515/qc/recast_quality_report.v1.json` passed
- Added PR-34.5 deterministic benchmark harness:
  - schemas:
    - `repo/shared/recast_benchmark_suite.v1.schema.json`
    - `repo/shared/recast_benchmark_report.v1.schema.json`
  - examples:
    - `repo/examples/recast_benchmark_suite.v1.example.json`
    - `repo/examples/recast_benchmark_report.v1.example.json`
  - tools:
    - `repo/tools/run_recast_benchmark.py`
    - `repo/tools/validate_recast_benchmark.py`
    - `repo/tools/smoke_recast_benchmark.py`
- PR-34.5 smoke validation (Conda `cat-ai-factory`):
  - `python -m py_compile repo/tools/run_recast_benchmark.py repo/tools/validate_recast_benchmark.py repo/tools/smoke_recast_benchmark.py` passed
  - `python -m repo.tools.smoke_recast_benchmark` passed
  - generated and validated:
    - `sandbox/logs/benchmarks/recast-regression-smoke/baseline-worker-output.recast_quality_report.v1.json`
    - `sandbox/logs/benchmarks/recast-regression-smoke/hitl-viggle-output.recast_quality_report.v1.json`
    - `sandbox/logs/benchmarks/recast-regression-smoke/recast_benchmark_report.v1.json`

### Open Findings / Conditions
- Roadmap policy:
  - Cloud migration PRs are postponed until quality-video track (PR-31..PR-34.6) is complete and accepted.
  - Execution order override: Phase 8 runs first; Phase 7 resumes after Phase 8 closeout.
  - Planning directive (2026-02-16): only quality-path PRs will be planned from this point forward.
  - Fallback-only/scaffolding PRs are deferred unless they directly raise output quality or recast fidelity.
- Scope update (2026-02-17): PR-34.6 remains planned but is not currently in execution; add PR-34.7 deterministic quality-controller loop scope before PR-34.6 implementation work.
  - ARCH scope addendum (2026-02-17): PR-34.7 includes implemented PR-34.7a..PR-34.7f and planned follow-ons PR-34.7g/34.7h/34.7i/34.7k/34.7l/34.7m for runtime segment execution, two-pass orchestration, quality-target tuning, explicit quality target contracts, debug exports, and continuity-pack inputs.
- Analyzer lock:
  - metadata/patterns only in canon; no copyrighted media in repo.
  - Worker must not depend on analyzer artifacts.
- PR-34.5 scope lock:
  - benchmark suite/report remain deterministic contract artifacts
  - no authority-boundary changes and no Worker external recast calls
  - benchmark outputs remain under sandbox logs for auditability
- PR-34.5 completion notes:
  - benchmark regression harness now produces comparable case reports + aggregate summary
  - Worker remains deterministic and output-bound

### Next Action (Owner + Task)
- ARCH: lock sequencing + acceptance criteria for PR-34.7g/34.7h/34.7i/34.7k/34.7l/34.7m against FR-28.9..FR-28.12.
- CODEX: proceed with PR-34.7g implementation kickoff (segment generate+stitch runtime execution path).
- ARCH: keep PR-34.6 in planned state until PR-34.7g..PR-34.7m quality follow-ons are accepted.

### ARCH Decision Queue Snapshot (PR-34.5 Focus)
1) Video Analyzer contracts:
- Approved as planner enrichment layer.
- Metadata-only canon and index/query contracts.
- ADR required and now locked (ADR-0041).
2) Voice/style registry contracts:
- Approved as provider-agnostic planner/control metadata inputs.
- Must include deterministic validation and no secrets/PII in committed artifacts.
3) Dance Swap v1 contracts:
- Approved as deterministic choreography-preserving lane artifact layer.
- Contract set must remain lane-permissive and preserve `job.json` authority.
4) Recast benchmark regression:
- Must remain deterministic suite/report artifacts (`recast_benchmark_suite.v1`, `recast_benchmark_report.v1`).
- Must preserve authority boundaries and provide comparable outputs across runs.
5) Internal Baseline V2 fallback:
- Must provide a deterministic non-overlay internal quality path that is benchmark-comparable and output-bound.
- Must preserve `job.json` authority and avoid external API dependencies in Worker.

### ARCH Decision Queue Snapshot (PR-34.7 Focus)
1) Analyzer core posture:
- Approved: deterministic, open/local-first, schema-driven analyzer core as primary path.
- Core stack: FFprobe/FFmpeg metadata, PySceneDetect, pose checkpoints, optical-flow motion curve, librosa beat/onset grid.

2) Reverse prompt contracts:
- Approved target canonical artifact: `caf.video_reverse_prompt.v1`.
- Contract must explicitly separate:
  - deterministic measured truth fields
  - inferred semantic/prompt fields
  - confidence/uncertainty markers.

3) Vendor enrichment policy:
- Approved as optional planner-side plugins only:
  - IndieGTM
  - NanoPhoto.ai
  - BigSpy AI Prompt Generator
- Vendor outputs are non-authoritative suggestions and must never overwrite analyzer truth fields.
- Vendor dependency must remain non-blocking for daily pipeline operation.

4) Quality strategy for dance loops:
- Approved shift from prompt-only to constraint-driven generation:
  - segment -> generate -> stitch
  - beat grid + pose checkpoints as first-class constraints
  - locked camera/background defaults for stability.

5) Two-pass motion -> identity:
- Approved as planning/orchestration pattern.
- Identity pass must remain either:
  - reference-constrained generator pass, or
  - explicit external HITL recast pass.
- No hidden autonomous recast behavior inside factory.

6) Invariant lock:
- Preserve three-plane separation and files-as-bus.
- Preserve `job.json` execution authority.
- Preserve Worker determinism/no-network.
- Preserve external recast as explicit Ops/Distribution HITL boundary.

------------------------------------------------------------
