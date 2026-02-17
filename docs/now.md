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

PR: **PR-34.1 — External HITL recast implementation (ops flow + re-ingest path)**
Last Updated: 2026-02-16

### Status by Role
- ARCH: In Progress (review/closeout)
- CODEX: Completed
- CLOUD-REVIEW: Not Required (PR-34.x is non-cloud scope)

### Decisions / ADRs Touched
- ADR-0041 (Video Analyzer planner-side canon contracts)
- ADR-0042 (Dance Swap v1 deterministic lane)
- ADR-0040 (Media Stack v1 stage contracts)
- ADR-0043 (Mode B default strategy)
- ADR-0044 (External HITL recast boundary)

### What Changed (Diff Summary)
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

### Open Findings / Conditions
- Roadmap policy:
  - Cloud migration PRs are postponed until quality-video track (PR-31..PR-34.5) is complete and accepted.
  - Execution order override: Phase 8 runs first; Phase 7 resumes after Phase 8 closeout.
  - Planning directive (2026-02-16): only quality-path PRs will be planned from this point forward.
  - Fallback-only/scaffolding PRs are deferred unless they directly raise output quality or recast fidelity.
- Analyzer lock:
  - metadata/patterns only in canon; no copyrighted media in repo.
  - Worker must not depend on analyzer artifacts.
- PR-34.x scope lock:
  - external recast remains explicit Ops/Distribution HITL flow
  - Worker does not call external recast services
  - no cross-plane authority changes
- PR-34.x completion notes:
  - export/re-ingest lifecycle is now explicit, auditable, and validation-backed
  - Worker remains deterministic and output-bound

### Next Action (Owner + Task)
- ARCH: review PR-34.x implementation closeout against ADR-0044 boundaries.
- CODEX: proceed to quality gating track (PR-34.4 / PR-34.5).

### ARCH Decision Queue Snapshot (PR-34.x Focus)
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
4) External HITL recast contracts:
- Must remain explicit Ops/Distribution flow (`viggle_pack.v1`, lifecycle, re-ingest pointer).
- Must preserve `job.json` as execution authority and keep Worker external-call free.

------------------------------------------------------------
