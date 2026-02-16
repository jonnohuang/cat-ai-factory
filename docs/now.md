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

PR: **PR-25 — Vertex AI providers (mandatory portfolio requirement)**
Last Updated: 2026-02-16

### Status by Role
- ARCH: Completed
- CODEX: Completed
- CLOUD-REVIEW: Completed (Approved)

### Decisions / ADRs Touched
- ADR-0006 (Planner LLM provider strategy)
- ADR-0018 (Optional provider posture)
- ADR-0039 (Planner-side AI template generation allowed)
- ADR-0038 (Infra provisioning deferred to PR-30)

### What Changed (Diff Summary)
- `docs/PR_PROJECT_PLAN.md`: PR-24 marked COMPLETED; PR-25 marked ACTIVE.
- `docs/now.md`: switched ledger from PR-24 closeout to PR-25 kickoff.
- `repo/services/planner/providers/vertex_ai.py`: added planner-side Vertex adapters with deterministic validation/repair flow and safe fallback behavior.
- `repo/services/planner/providers/__init__.py`: registered `vertex_veo` and `vertex_imagen` providers for planner CLI selection.
- `repo/services/planner/providers/vertex_ai.py`: added ADC-capable token resolution (when `google-auth` is available) and explicit fallback/lane-visibility logging.
- `repo/requirements-dev.txt`: added `google-auth` for local ADC support during live Vertex validation.
- `repo/services/planner/providers/vertex_ai.py`: added generated-seed handoff wiring (Vertex Imagen predict -> `sandbox/assets/generated/<job_id>/seed-0001.png`) and automatic `image_motion` routing for deterministic Worker rendering.
- `repo/services/planner/providers/vertex_ai.py`: added deterministic auto-audio attachment (`audio.audio_asset`) from audio manifest (or safe local beds fallback) when job audio is missing.
- `repo/services/planner/providers/vertex_ai.py`: improved dance quality heuristics (multi-seed generation for dance prompts, motion preset selection, mood-aware audio bed scoring with upbeat preference).
- `repo/services/planner/providers/vertex_ai.py`: added Lane A true video handoff attempt for `vertex_veo` (Veo video asset -> `render.background_asset`) with deterministic fallback to `image_motion` seeds.
- `repo/worker/render_ffmpeg.py`: added basic audio mastering chain (`loudnorm` + `alimiter`) in both standard and image-motion render paths.
- `repo/services/planner/providers/vertex_ai.py`: audio scoring now prefers extracted `caf_bed_dance_loop_01.wav` for dance-loop contexts.
- `repo/services/planner/providers/vertex_ai.py`: added hero-registry enforcement path (hero selection, persisted hero bundle under `sandbox/assets/generated/heroes/<hero_id>/`, hero trait prompt injection, and hero-seed-priority dance routing for Mochi consistency).

### Open Findings / Conditions
- Verification: End-to-end `vertex_veo` provider call succeeded (path=vertex).
- Cloud Risk addressed in PR-25: adapter no longer depends on token-only auth; it supports either `VERTEX_ACCESS_TOKEN` or ADC.
- Non-blocking improvement addressed: planner now logs provider fallback reasons and lane-hint application visibility.
- Runtime note: if Imagen predict is unavailable for the configured model/region, planner falls back to non-generated background behavior.
- Cloud Risk: default `VERTEX_LOCATION=us-central1` must match enabled Vertex region during PR-30 provisioning.
- Runtime note: `audio_manifest.v1.json` currently has empty `beds`; planner uses safe local-bed fallback if files exist under `sandbox/assets/audio/beds/`.
- Quality note: dance prompts now prefer multi-frame `image_motion` (`cut_3frame` when seeds available) and upbeat beds (e.g., `caf_bed_upbeat_01.wav`).
- Runtime note: true Lane A video handoff depends on Veo response format/model availability; if unavailable, adapter safely falls back to multi-seed `image_motion`.
- Runtime note: hero consistency mode intentionally prioritizes deterministic `image_motion` for hero dance prompts to preserve schema identity.

### Next Action (Owner + Task)
- ARCH: Open PR-26 and begin budget guardrails implementation.

------------------------------------------------------------
