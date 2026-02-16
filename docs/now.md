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

PR: **PR-33.1 — Dance Swap implementation (deterministic recipe wiring)**
Last Updated: 2026-02-16

### Status by Role
- ARCH: In Progress
- CODEX: Pending
- CLOUD-REVIEW: Not Required (PR-33.1 is non-cloud scope)

### Decisions / ADRs Touched
- ADR-0041 (Video Analyzer planner-side canon contracts)
- ADR-0042 (Dance Swap v1 deterministic lane)

### What Changed (Diff Summary)
- `docs/PR_PROJECT_PLAN.md`:
  - PR-31 status updated to COMPLETED
  - PR-32 status updated to COMPLETED
  - PR-32.1 status updated to COMPLETED
  - PR-32.2 status updated to COMPLETED
  - PR-33 status updated to COMPLETED
  - PR-33.1 status updated to ACTIVE
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
- Docs alignment updates for new sub-PR scope:
  - `docs/system-requirements.md`:
    - FR-26.2 (voice/style registries)
    - FR-27.1 (optional Mode B planning contracts)
    - FR-28.1 (HITL lifecycle + pack/pointer validation contracts)
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

### Open Findings / Conditions
- Roadmap policy:
  - Cloud migration PRs are postponed until quality-video track (PR-31..PR-34) is complete and accepted.
  - Execution order override: Phase 8 runs first; Phase 7 resumes after Phase 8 closeout.
- Analyzer lock:
  - metadata/patterns only in canon; no copyrighted media in repo.
  - Worker must not depend on analyzer artifacts.
- PR-33.1 scope lock:
  - implementation wiring only from explicit Dance Swap artifacts
  - preserve non-binding lane policy (ADR-0024)
  - no LLM/network side effects in Worker

### Next Action (Owner + Task)
- ARCH: review PR-33 contract closeout and confirm PR-33.1 implementation boundaries.
- CODEX: implement PR-33.1 deterministic Dance Swap recipe wiring + smoke validation.

### ARCH Decision Queue Snapshot (PR-33.1 Focus)
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
4) Dance Swap v1 implementation:
- Must consume explicit loop/tracks/mask/beatflow artifacts only.
- Preserve Worker determinism and output boundary constraints.

------------------------------------------------------------
