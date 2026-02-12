# Cat AI Factory — PR Project Plan (Current Canon + Status Labels)

This document defines the expected Pull Request (PR) plan for the Cat AI Factory project.

The goal is to keep the project:
- finite
- reviewable
- deterministic
- portfolio-ready

Each PR is intentionally scoped and independently defensible.

------------------------------------------------------------

## Guiding Rules

- One PR = one clearly defined deliverable
- PRs must preserve the three-plane invariant:
  Planner / Control Plane / Worker
- Architectural changes require ADRs (`docs/decisions.md`)
- LOCAL determinism must always be preserved
- Earlier phases must not be invalidated by later ones
- Demo assets must be license-safe (or excluded from Git)
- **PR numbers must never be reused once shipped**

------------------------------------------------------------

## Scope Reminder: Ops/Distribution is Outside the Factory

Cat AI Factory’s core invariant is the three-plane factory:

Planner (Clawdbot) → Control Plane (Ralph Loop) → Worker (FFmpeg)

Ops/Distribution (e.g., Telegram, approval gates, publisher adapters, bundle generation)
is an **external automation layer**. It may consume events and artifacts, but it must:

- NOT replace Clawdbot or Ralph Loop
- NOT mutate `job.json`
- NOT modify worker outputs under `/sandbox/output/<job_id>/...`
- Emit derived artifacts instead (e.g., `sandbox/dist_artifacts/<job_id>/...`)
- Enforce idempotency for publishing keyed by `{job_id, platform}`

Important:
- Ops/Distribution remains outside the factory invariant.
- Ops/Distribution is REQUIRED before Cloud migration, because it defines
  the “posting modules” and daily operational workflow.

------------------------------------------------------------

## PR Status Legend

- **COMPLETED** — merged/shipped
- **ACTIVE** — currently being implemented
- **NEXT** — next up after ACTIVE
- **PLANNED** — queued for later

------------------------------------------------------------

## Phase 0 — Governance & Documentation (COMPLETED)

Purpose: establish authority, invariants, and navigability.

### PR-0 — Docs normalization + architecture
Status: **COMPLETED**

Scope:
- Normalize master / decisions / chat bootstrap
- Add diagram-first architecture
- Add SYSTEM, GUARDRAILS, and milestone briefs

Outcome:
- Clear architectural authority
- Safe collaboration with Codex and IMPL
- Recruiter-readable docs

------------------------------------------------------------

## Phase 1 — LOCAL v0.1 Deterministic Pipeline (COMPLETED)

Purpose: prove reproducibility, idempotency, and artifact lineage locally.

### PR-1 — Job contract v1
Status: **COMPLETED**

Scope:
- job.schema.json v1
- Deterministic validator
- Golden job example

Outcome:
- Explicit, versioned contract
- Fail-loud validation
- Planner → Worker interface locked

---

### PR-2 — Worker idempotency + stable outputs
Status: **COMPLETED**

Scope:
- Per-job output directories
- Atomic overwrite / safe reruns
- result.json run metadata
- Determinism check (harness-only)

Outcome:
- Re-runnable worker
- Stable paths
- Deterministic artifacts

---

### PR-3 — Artifact lineage + determinism harness
Status: **COMPLETED**

Scope:
- Lineage verifier (job → outputs → logs)
- Unified local harness command
- One-command LOCAL v0.1 verification

Outcome:
- Auditable artifact graph
- Determinism proven end-to-end
- LOCAL v0.1 complete

---

### PR-3.5 — Demo Sample Pack (cat activities + assets)
Status: **COMPLETED** (recommended demo pack)

Scope:
- Add a small demo pack under:
  - assets: `sandbox/assets/demo/`
  - jobs: `sandbox/jobs/demo-*.job.json`
  - docs: minimal “how to run demo” notes
- Include canonical “cat activity” examples aligned with Shorts/Reels style.
- No schema changes.
- No pipeline logic changes.
- Demo pack must not be required for LOCAL v0.1 correctness.

Licensing rules:
- Prefer AI-generated or CC0/public-domain assets that are safe to redistribute.
- If using privately sourced reference videos for style analysis, keep them OUT of Git
  and provide placeholder filenames/instructions instead.

Outcome:
- A recruiter-friendly, reproducible demo scenario
- Clear separation: pipeline correctness vs content aesthetics

------------------------------------------------------------

## Phase 2 — AGENTS v0.2 Control Plane + Planner Autonomy (COMPLETED)

Purpose: demonstrate real agent orchestration + autonomous planning without sacrificing safety.

### PR-4 — Ralph Loop state machine (single-job orchestrator)
Status: **COMPLETED**

Scope:
- Explicit job lifecycle states
- Deterministic reconciliation loop
- Logs-only state artifacts under `/sandbox/logs/<job_id>/**`
- Fast-path completion when outputs already exist + lineage passes
- Locking via atomic mkdir (`/sandbox/logs/<job_id>/.lock`)

Outcome:
- Control-plane semantics are explicit and testable
- Retry-safe orchestration without mutating outputs

---

### PR-4.1 — Requirements + roadmap tightening (docs-only)
Status: **COMPLETED**

Scope:
- Add `docs/system-requirements.md` as a reviewer-readable requirements contract
- Capture phased provider strategy (AI Studio now, Vertex later)
- Capture budget guardrails + secret handling requirements
- No schema changes

Outcome:
- Reviewers can understand constraints and roadmap in 1 file
- PR5+ scope stays clean and PR-sized

---

### PR-5 — Planner Adapter Layer + Gemini AI Studio (LOCAL autonomy)
Status: **COMPLETED**

Scope:
- Introduce a planner adapter interface (frameworks are adapters, not foundations)
- Add a Gemini adapter using Google AI Studio API key (LOCAL, no OAuth)
- Planner target is autonomous planning (no long-term human-in-loop planner)
- Adapters must produce the same `job.json` schema (contract remains stable)

Hard constraints:
- Planner writes `job.json` only
- RAG is planner-only
- No framework becomes mandatory
- No orchestration semantics move into frameworks
- No worker LLM usage

Security constraints:
- API keys are runtime-only via `.env` (never committed)
- Logs must not print secrets

Outcome:
- Autonomous planning with a real Gemini integration
- Framework alignment without lock-in
- Strong portfolio signal: “adapters, not foundations”

---

### PR-5.1 — Planner prompt-injection hardening + debug redaction
Status: **COMPLETED**

Scope:
- Add planner prompt guardrails (PRD/inbox treated as untrusted; JSON-only)
- Ensure debug surfaces never print model raw text (len-only) and never print secrets

Outcome:
- Reduced leakage risk
- Stronger production safety posture

---

### PR-6 — Verification / QC agent
Status: **COMPLETED**

Scope:
- Deterministic, read-only evaluator
- Contract + output conformance checks
- Emits QC results as logs/summary artifacts (no mutation of existing artifacts)

Outcome:
- Production-grade quality gates without autonomy creep

---

### PR-6.1 — Harness-only QC integration (reporting-only)
Status: **COMPLETED**

Scope:
- Integrate QC into the local harness.
- QC is additive reporting only; does not change harness PASS/FAIL gating.
- QC results are recorded in harness summary artifacts.

Outcome:
- QC is a first-class reporting surface in the local development harness.
- Clear separation: harness gating vs QC reporting.

------------------------------------------------------------

## Phase 3 — Ops/Distribution v0.2 (COMPLETED)

Purpose: demonstrate real-world “agent → human approval → publish artifacts” workflows without contaminating core determinism.

### PR-7 — Telegram/mobile control adapter (inbox/status bridge)
Status: **COMPLETED**

Scope:
- Telegram writes requests into `/sandbox/inbox/*.json`
- Telegram reads status from:
  - `/sandbox/logs/<job_id>/state.json` (factory status)
  - `/sandbox/dist_artifacts/<job_id>/<platform>.state.json` (publish status)
- Commands are implemented as inbox artifacts (file-bus), e.g.:
  - `/plan <prompt>` → `plan-<nonce>.json`
  - `/approve <job_id>` → `approve-<job_id>-<platform>-<nonce>.json`
  - `/reject <job_id> [reason]` → `reject-<job_id>-<platform>-<nonce>.json`
- Authorization enforced via `TELEGRAM_ALLOWED_USER_ID`
- No bypass of file-bus semantics
- No mutation of job.json or worker outputs

Outcome:
- Mobile-friendly supervisor surface
- Clean adapter boundary (no orchestration contamination)

---

### PR-8 — Publish contracts + idempotency model (docs-only)
Status: **COMPLETED**

Scope:
- Define publish contracts, approval artifacts, and idempotency conventions.
- Lock derived artifact conventions under `sandbox/dist_artifacts/`.
- No changes to worker outputs or job.json schema.

Outcome:
- Stable publish/idempotency conventions
- Prevents drift in Ops/Distribution artifact semantics

---

### PR-9 — Publish pipeline MVP (YouTube first) + approval gate
Status: **COMPLETED**

Scope:
- YouTube publish adapter
- Approval gate via inbox artifacts
- Idempotency via dist_artifacts state file
- Must not modify worker outputs

Outcome:
- End-to-end “COMPLETED → approved → published” workflow for YouTube

---

### PR-10 — Roadmap + ADR locks (docs-only)
Status: **COMPLETED**

Scope:
- Rewrite PR plan sequencing (daily lanes + promotion toolkit + publisher adapters before cloud)
- Append ADRs locking roadmap decisions:
  - lanes
  - hero cats (metadata)
  - multilingual support (en + zh-Hans)
  - audio plan
  - LangGraph planner-only
  - Seedance optional
- Align docs (system requirements + architecture notes) with required posture

Outcome:
- A stable “constitution” for the next implementation era

------------------------------------------------------------

## Phase 4 — Promotion Toolkit + Publisher Modules v0.3 (COMPLETED)

Purpose: make posting fast, safe, and repeatable without requiring platform automation.

Note:
PR11–PR14 were executed early to lock publish_plan + bundle layout + platform copy formatting
before lane expansion work. This sequencing is intentional and does not violate invariants.

### PR-11 — Publish plan v1 (multilingual + audio plan included)
Status: **COMPLETED**

Scope:
- publish_plan.json v1 + schema + validator
- language-map structures (en + zh-Hans enabled)
- audio plan per clip (strategy + notes + optional assets list)
- Generates platform copy artifacts and posting metadata

Outcome:
- Deterministic promotion contract via artifacts (no posting required)

---

### PR-12 — Export Bundle Layout v1 (ADR-0021; normative spec)
Status: **COMPLETED**

Scope:
- Lock bundle layout under:
  `sandbox/dist_artifacts/<job_id>/bundles/<platform>/v1/`
- Require audio + bilingual copy artifacts in bundle
- No schema changes

Outcome:
- Bundle layout drift prevented; platform modules can rely on fixed structure

---

### PR-13 — Publisher adapter interface + bundle builder (bundle-first)
Status: **COMPLETED**

Scope:
- Publisher adapter interface
- Bundle builder generates ADR-0021-compliant bundles for:
  - YouTube / Instagram / TikTok / X
- Bundle-only behavior (no upload automation required)

Outcome:
- Platform modules exist pre-cloud; bundles are deterministic artifacts

---

### PR-14 — Per-platform copy formatting (derived from publish_plan.v1)
Status: **COMPLETED**

Scope:
- Deterministic, per-platform copy formatting:
  - YouTube / Instagram / TikTok / X
- Writes only:
  `copy/copy.en.txt`, `copy/copy.zh-Hans.txt`
- No schema changes; no new artifact paths

Outcome:
- Bundles become immediately usable for manual posting (<2 min/clip)

------------------------------------------------------------

## Phase 5 — Repo Posture + Branding (COMPLETED)

Purpose: lock public-repo guardrails and improve brand survival against repost theft.

### PR-15 — Public repo posture + roadmap alignment (docs-only)
Status: **COMPLETED**

Scope:
- Update canon docs to reflect:
  - CAF core repo is PUBLIC (portfolio posture)
  - No secrets in repo (non-negotiable)
  - Credentialed publishing integrations must be external/private
- Update PR plan sequencing to match shipped PR11–PR14
- Add PR16 watermark PR entry to roadmap
- Optional: add LICENSE + SECURITY.md

Outcome:
- Repo is safe to keep public; roadmap is coherent and non-contradictory

---

### PR-16 — Deterministic watermark overlay (Worker)
Status: **COMPLETED**

Scope:
- Worker applies deterministic FFmpeg watermark overlay:
  - repo-owned watermark asset (versioned)
  - fixed placement + opacity + scale
  - output path unchanged:
    `/sandbox/output/<job_id>/final.mp4`
- No schema changes
- No bundle layout changes (bundles inherit watermarked media automatically)

Outcome:
- Brand attribution survives reposts; reduces lazy theft without autonomy creep

---

### PR-16.1 — Brand Asset Pack v1 (static repo-owned assets + channel setup)
Status: **COMPLETED**

Scope:
- Add repo-owned, static brand assets for deterministic reuse:
  - `repo/assets/watermarks/caf-watermark.png` (already exists; ensure it remains canonical)
  - `repo/assets/brand/profile_1x1.png`
  - optional banners (non-runtime):
    - `repo/assets/brand/banner_youtube.png`
    - `repo/assets/brand/banner_facebook.png`
    - `repo/assets/brand/banner_x.png`
- Add `docs/brand.md` containing:
  - canonical brand name: Cat AI Factory
  - canonical handle: @cataifactory
  - links to platform accounts:
    - YouTube / Instagram / TikTok / X / Facebook / Snapchat / Threads
  - asset usage rules (watermark sizing guidance; profile/banner usage)
- No schema changes.
- No Worker logic changes.
- No “branding layer” in Worker; assets are static inputs only.

Notes:
- For Facebook/Snapchat/Threads: CAF outputs one universal `final.mp4`.
- No platform-specific video adapters are required until a future “auto-publish” phase.

Outcome:
- Deterministic brand identity pack lives in-repo
- Channel setup becomes documented and reproducible
- Watermark asset remains stable and versioned

------------------------------------------------------------

## Phase 6 — Daily Output System v0.4 (PLANNED)

Purpose: achieve 3 clips/day under strict budget constraints using lane-based production.

### PR-17 — Lane contracts + expected outputs (no cloud yet)
Status: **COMPLETED**

Scope:
- Define lane identifiers (contract-level):
  - ai_video | image_motion | template_remix
- Define expected artifacts per lane (local paths)
- No change to core 3-plane invariant

Outcome:
- Lane-aware planning becomes explicit and reviewable

---

### PR-18 — Lane C: Template registry + deterministic template_remix recipes
Status: **COMPLETED**

Scope:
- Add template registry (deterministic metadata)
- Worker supports template_remix lane via FFmpeg-only recipes

Outcome:
- Near-free daily clips at scale (Lane C)

---

### PR-19 — Lane B: image_motion (seed frames + deterministic motion presets)
Status: **COMPLETED**

Scope:
- Seed image request/selection interface (planner-side or pre-worker; not in worker)
- Worker adds deterministic motion presets (Ken Burns/zoom/shake/cuts)

Outcome:
- Cheap “video-like” clips at scale (Lane B)

---

### PR-20 — Deterministic audio support (Worker; blocker fix)
Status: **COMPLETED**

Scope:
- Ensure Worker always emits `final.mp4` with an audio stream (Shorts/Reels/TikTok requirement).
- Deterministic priority order:
  1) If job provides `audio.audio_asset` (sandbox-relative), use it.
  2) Else if background video has audio, preserve/passthrough it.
  3) Else inject deterministic silence so output ALWAYS contains audio.
- Deterministic encoding settings (e.g., AAC, 48kHz, stereo, fixed bitrate).
- Safe path validation for audio assets (sandbox-only).
- Must NOT call network/LLM APIs; pure deterministic FFmpeg mux/encode only.

Outcome:
- No silent/broken MP4s; publish-ready media across all lanes.

---

### PR-21 — Hero cats registry (metadata only) + planner bindings
Status: **COMPLETED**

Scope:
- Add character registry + schema + validator
- Planner uses hero-cat metadata for series continuity
- Characters are metadata, NOT agents

Outcome:
- Series continuity without story-memory/autonomy creep

---

### PR-21.1 — Job creativity controls (contract-only; provider-agnostic)
Status: **COMPLETED**

Scope:
- Extend `repo/shared/job.schema.json` with an optional top-level `creativity` object:
  - `mode`: canon | balanced | experimental
  - (optional) `canon_fidelity`: high | medium
- No provider-specific knobs (Gemini/Vertex remain adapters).
- No Worker changes; Planner/control-plane only.
- Backward compatible; schema remains permissive (no lane-based conditional enforcement).

Outcome:
- Stable “creative intent” surface for Planner without temperature hacks.

---

### PR-21.2 — Series Bible + Episode Ledger v1 (contracts + docs only)
Status: **COMPLETED**

Scope:
- Add minimal continuity artifacts as versioned contracts:
  - `repo/shared/series_bible.v1.schema.json`
  - `repo/shared/series_bible.v1.json` (example)
  - `repo/shared/episode_ledger.v1.schema.json`
  - `repo/shared/episode_ledger.v1.json` (example)
- The series bible includes:
  - tone rules
  - forbidden topics
  - running gags
  - canon setting rules
  - references to hero registry ids
- The episode ledger records per-episode:
  - what happened
  - new facts introduced
  - next hook / continuity seed
- Docs update: define these as the canonical continuity layer above job contracts.
- No Worker changes.

Outcome:
- Canon continuity becomes explicit, file-based, reviewable, and reproducible.

---

### PR-21.3 — Audio Strategy v1 (assets + manifest + usage rules; license-safe)
Status: **COMPLETED**

Scope:
- Add repo-owned, license-safe loopable audio beds:
  - `sandbox/assets/audio/beds/*.wav`
- Add an audio manifest contract:
  - `sandbox/assets/audio/audio_manifest.v1.json`
  - includes filename, mood tags, license/source notes, safe-to-commit flag
- Add documentation:
  - `sandbox/assets/audio/README.md`
  - rules: Planner may only select from approved beds; no trending/copyright music
- No Worker changes required (PR20 already supports deterministic audio selection order).

Outcome:
- Higher-quality shorts audio posture with reduced copyright / Content-ID risk.

---

### PR-21.4 — Telegram daily_plan: optional creativity hints (adapter-only)
Status: **COMPLETED**

Scope:
- Extend the Telegram daily_plan ingress artifact to optionally include:
  - `creativity.mode`: canon | balanced | experimental
  - `creativity.canon_fidelity`: high | medium
- Backward compatible:
  - if absent, behavior is unchanged
- Update Telegram command documentation with example syntax for setting creativity.
- No schema changes required.
- No Worker changes.
- No Planner changes required (Planner may ignore until it is wired in later).

Outcome:
- Daily planning can steer “canon vs experimental” tone from mobile without breaking contracts.
- Keeps creativity control as planner-only intent, consistent with ADR-0025.

---

### PR-22 — LangGraph demo workflow (planner-only)
Status: **ACTIVE**

Scope:
- LangGraph workflow adapter in Planner plane only
- Must NOT replace Ralph or Worker
- Demonstrate recruiter-facing workflow orchestration story

Outcome:
- Mandatory Google demo signal without architecture compromise

---

### PR-22.1 — Planner RAG v1 (deterministic retrieval; docs + manifest; planner-only)
Status: **PLANNED**

Scope:
- Add a minimal, license-safe RAG “pack” that is **planner-only** and **deterministic**:
  - `repo/shared/rag_manifest.v1.schema.json`
  - `repo/shared/rag_manifest.v1.json` (example)
  - `repo/shared/rag/` (small set of repo-owned guidance docs, e.g. tone, safety, lane guidance, caption rules)
- Retrieval MUST be deterministic and reproducible (no embeddings required):
  - tag + priority selection from `rag_manifest`
  - stable tie-break rules (e.g., `priority` then `doc_id` lexical)
- Planner integration is read-only:
  - Planner MAY read RAG docs to improve contract quality
  - Planner MUST NOT write or modify any RAG artifacts at runtime
- No changes to:
  - Worker logic
  - Ralph Loop logic
  - job schema (unless explicitly required later via ADR)

Outcome:
- A portfolio-credible RAG story that preserves CAF invariants:
  deterministic “reference context” for the Planner, file-based and reviewable,
  without embeddings, vector DBs, or hidden memory.

------------------------------------------------------------

## Phase 7 — Cloud v0.5 Migration (PLANNED)

Purpose: demonstrate cloud literacy while preserving LOCAL guarantees.

### PR-23 — Cloud artifact layout (GCS + Firestore mapping)
Status: **PLANNED**

Scope:
- GCS path conventions (immutable artifacts)
- Firestore job + publish state mapping consistent with local lineage

Outcome:
- Cloud storage/state explicitly modeled

---

### PR-24 — Cloud Run execution stubs (orchestrator + worker)
Status: **PLANNED**

Scope:
- Minimal Cloud Run deployment
- Preserve contracts and states; no redesign

Outcome:
- Clean cloud execution path without semantics drift

---

### PR-25 — Vertex AI providers (mandatory portfolio requirement)
Status: **PLANNED**

Scope:
- Vertex AI provider adapters (planner-side)
- Lane A: Veo (ai_video), Lane B: Imagen (seed frames) as applicable
- Maintain adapter boundaries and deterministic worker behavior

Outcome:
- Enterprise/production path demonstrated

---

### PR-26 — Budget guardrails + enforcement (local + cloud)
Status: **PLANNED**

Scope:
- Cost estimation and caps (hard stop) before spending
- Idempotent accounting keys; retry-safe enforcement

Outcome:
- Safe autonomy and cost control

---

### PR-27 — CI/CD skeleton
Status: **PLANNED**

Scope:
- Lint + harness execution
- No auto-deploy required

Outcome:
- Portfolio-grade hygiene

------------------------------------------------------------

## Completion Criteria

The project is considered **portfolio-complete** when:
- Phase 1 is complete (PR-3 merged)
- PR-5 is complete (Gemini autonomy via AI Studio)
- PR-25 is complete (Vertex AI presence demonstrated)
- All invariants remain intact
- LOCAL v0.1 can be verified with a single command

Phases 4+ must not compromise Phase 1 guarantees.
