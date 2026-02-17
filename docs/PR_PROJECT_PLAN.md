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

### PR-21.5 — PlanRequest v1 (guided input contract; cloud-agnostic)
Status: **COMPLETED**

Scope:
- Add a deterministic, versioned request contract for guided inputs (UI/front-end neutral):
  - `repo/shared/plan_request.v1.schema.json`
  - `repo/examples/plan_request.v1.example.json`
- Add docs describing:
  - how Telegram/free-text can map into PlanRequest fields
  - normalization rules (planner-side deterministic defaults)
- Optional: add a minimal local validator/normalizer tool (does not change runtime authority):
  - produces a canonical inbox artifact (still file-bus)
- No changes to Worker or Ralph Loop.
- No secrets; public repo safe.

Outcome:
- A stable, schema-valid request interface that supports future guided UIs (Coze) without coupling,
  while keeping CAF planner as the source of truth.

---

### PR-21.6 — EpisodePlan v1 (planner-only intermediate artifact)
Status: **COMPLETED**

Scope:
- Add a schema-validated planner-only intermediate artifact:
  - `repo/shared/episode_plan.v1.schema.json`
  - `repo/examples/episode_plan.v1.example.json`
- Update docs to describe EpisodePlan v1:
  - planner-only
  - deterministic normalization + validation
  - does not replace `job.json`
- No changes to Worker or Ralph Loop.

Outcome:
- A reviewable, deterministic planning artifact that improves continuity without changing execution boundaries.

---

### PR-22 — LangGraph demo workflow (planner-only)
Status: **COMPLETED**

Scope:
- LangGraph workflow adapter in Planner plane only
- Must NOT replace Ralph or Worker
- Demonstrate recruiter-facing workflow orchestration story

Outcome:
- Mandatory Google demo signal without architecture compromise

---

### PR-22.1 — Planner RAG v1 (deterministic retrieval; docs + manifest; planner-only)
Status: **COMPLETED**

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

---

### PR-22.2 — CrewAI inside Planner node (contained; deterministic gates preserved)
Status: **COMPLETED**

Scope:
- Add CrewAI as a planning quality layer contained inside exactly one LangGraph node (or subgraph).
- CrewAI must NOT become the control plane and must NOT bypass deterministic gates.
- Determinism posture:
  - CrewAI output must be strict JSON (EpisodePlan / draft job inputs) only.
  - Schema validation, normalization, and artifact commits remain deterministic and outside CrewAI.
- No changes to:
  - Worker logic
  - Ralph Loop logic
  - file-bus write boundaries

Outcome:
- Portfolio-required multi-agent planning demo (CrewAI) without breaking CAF invariants:
  CrewAI improves planning quality, while deterministic validation + commit remain authoritative.

------------------------------------------------------------

## Phase 7 — Cloud v0.5 Migration (DEFERRED)

Purpose: demonstrate cloud literacy while preserving LOCAL guarantees.
Phase 7 is staged: early PRs define mappings and local stubs; live GCP provisioning
is deferred to a dedicated infra PR.
Execution policy:
- Phase 7 implementation PRs (PR-26..PR-30) are explicitly postponed until quality-video track
  PR-31..PR-34.6 reaches accepted output quality and deterministic handoff readiness.
- Execution order override: Phase 8 is intentionally executed before returning to Phase 7.

### PR-23 — Cloud artifact layout (GCS + Firestore mapping)
Status: **COMPLETED**

Scope:
- GCS path conventions (immutable artifacts)
- Firestore job + publish state mapping consistent with local lineage

Outcome:
- Cloud storage/state explicitly modeled

---

### PR-24 — Cloud Run execution stubs (orchestrator + worker)
Status: **COMPLETED**

Scope:
- Minimal Cloud Run stubs (no live deploy required)
- Preserve contracts and states; no redesign

Outcome:
- Clean cloud execution path without semantics drift

---

### PR-25 — Vertex AI providers (mandatory portfolio requirement)
Status: **COMPLETED**

Scope:
- Vertex AI provider adapters (planner-side)
- Lane A: Veo (ai_video), Lane B: Imagen (seed frames) as applicable
- Optional: AI-generated template assets (planner-side only)
- Maintain adapter boundaries and deterministic worker behavior

Outcome:
- Enterprise/production path demonstrated

---

### PR-26 — Budget guardrails + enforcement (local + cloud)
Status: **DEFERRED**

Scope:
- Cost estimation and caps (hard stop) before spending
- Idempotent accounting keys; retry-safe enforcement

Outcome:
- Safe autonomy and cost control

---

### PR-27 — CI/CD skeleton
Status: **DEFERRED**

Scope:
- Lint + harness execution
- No auto-deploy required

Outcome:
- Portfolio-grade hygiene

---

### PR-28 — Coze wiring (Cloud Run ingress client; PlanRequest.v1 → Firestore/GCS)
Status: **DEFERRED**

Scope:
- Wire Coze to call CAF Cloud Run ingress endpoint (e.g., `/ingress/plan`).
- Receiver validates PlanRequest.v1 deterministically and persists request/state per Phase 7 mapping.
- Cloud Tasks remains the async bridge for downstream work (Receiver must ACK fast).
- No changes to Worker rendering logic.

Outcome:
- Guided-input UI becomes functional in cloud without coupling Coze into core CAF logic.

---

### PR-29 — n8n workflows (post-cloud ops layer; human approval + manual publish)
Status: **DEFERRED**

Scope:
- Introduce n8n as an ops/workflow client layer after cloud state exists (Firestore/GCS).
- Cloud Tasks remains CAF’s internal queue for “do work” steps.
- Provide:
  - n8n workflow exports + setup docs
  - minimal idempotent CAF endpoints if needed (approve/publish triggers)
- No changes to Worker rendering logic.

Outcome:
- Smoother human approval + manual publish loop, with a clear separation:
  n8n = ops UX/integrations; Cloud Tasks = backend reliability.

---

### PR-30 — Terraform infra (live GCP provisioning; required, Phase 7 infra track)
Status: **DEFERRED**

Scope:
- Terraform for Cloud Run + Cloud Tasks + Firestore + GCS (placeholders only in repo)
- No real project IDs or bucket names committed
- Live provisioning is explicit and opt-in

Outcome:
- Reproducible, reviewable infra provisioning without polluting core docs or contracts

---

## Phase 8 — Media Quality & Recast Contracts (ACTIVE)

Purpose: lock deterministic media contracts and quality/recast pathways without breaking
three-plane authority or cloud sequencing.
Execution order:
- Active now; complete PR-31..PR-34.6 before resuming deferred Phase 7 PRs.

Planning directive (effective 2026-02-16):
- New PR planning is restricted to the quality-path track only.
- Fallback-only or scaffolding work is deferred unless it directly improves output quality, identity fidelity, or choreography fidelity.
- Cloud-phase PR planning remains paused until quality-path acceptance criteria are met.

### PR-31 — Media contracts + analyzer + lane docs/ADRs (no runtime code)
Status: **COMPLETED**

Scope:
- Lock ADR-backed contract posture for:
  - Media Stack v1 stage artifacts
  - Video Analyzer planner-side metadata canon
  - Dance Swap v1 deterministic lane
  - External HITL recast boundary
- Docs/contracts only; no runtime code changes required.

Outcome:
- Canonical boundaries are explicit before deeper implementation PRs.

---

### PR-32 — Analyzer contracts + query path (planner enrichment only)
Status: **COMPLETED**

Scope:
- Add versioned analyzer schemas and metadata index artifacts.
- Add deterministic planner-side lookup contract(s) for pattern retrieval.
- No Worker dependency on analyzer artifacts.

Outcome:
- Planner can reuse structured pacing/choreography/camera patterns safely.

---

### PR-32.1 — Analyzer implementation (planner-side runtime; metadata-only output)
Status: **COMPLETED**

Scope:
- Implement planner-side analyzer runtime that ingests video input and emits `video_analysis.v1` artifacts.
- Add deterministic extraction/normalization path for:
  - beat boundaries
  - loop window candidates
  - camera/choreography metadata fields required by `video_analysis.v1`
- OpenCV (or equivalent deterministic CV library) MAY be used for deterministic analysis utilities.
- Persist analyzer outputs as planner-side/canon metadata artifacts only.
- Provide deterministic validation + smoke command path for generated artifacts.
- No Worker dependency on analyzer artifacts.
- No copyrighted source media committed to repo canon.
- CV tooling usage MUST NOT change plane boundaries or Worker determinism constraints.

Outcome:
- CAF can generate analyzer metadata artifacts from real video inputs while preserving planner-only authority and Worker determinism.

---

### PR-32.2 — Voice/Style registries (contracts + validation)
Status: **COMPLETED**

Scope:
- Add versioned registry contracts and examples:
  - `voice_registry.v1` (hero_id -> voice adapter id/placeholder)
  - `style_registry.v1` (style_id -> workflow/prompt fragments)
- Add deterministic validators and smoke checks for both registries.
- Keep registries provider-agnostic and repo-safe (no secrets/PII).

Outcome:
- Media stack and planning lanes can reference stable voice/style metadata without provider lock-in.

---

### PR-33 — Dance Swap v1 deterministic lane (tracks/masks/loop artifacts)
Status: **COMPLETED**

Scope:
- Introduce lane-specific contracts for:
  - loop bounds
  - subject tracks
  - mask references
  - optional beat/flow metadata
- Deterministic Worker recipe consumes explicit artifacts only.
- Preserve non-binding lane semantics (ADR-0024).

Outcome:
- Recast-quality path for choreography-preserving hero replacement is available.

---

### PR-33.1 — Dance Swap implementation (deterministic recipe wiring)
Status: **COMPLETED**

Scope:
- Implement deterministic Dance Swap recipe wiring from explicit artifacts:
  - loop bounds
  - subject tracks
  - mask references
  - optional beat/flow metadata
- OpenCV (or equivalent deterministic CV library) MAY be used for deterministic compositing/flow/loop utilities.
- Add validation/smoke tooling for Dance Swap artifact integrity and required-field checks.
- Preserve lane non-binding policy (ADR-0024) and fail-loud behavior for unsafe/missing required artifacts.
- No LLM usage in Worker and no cross-plane authority changes.
- CV tooling usage MUST NOT introduce nondeterministic or network side effects in Worker.

Outcome:
- Dance Swap lane is executable with deterministic, artifact-driven behavior and reviewable validation surfaces.
- Current implementation is a deterministic baseline/fallback path; production-quality recast remains on the external HITL quality path (PR-34.x) and future dedicated motion-swap engine work.

---

### PR-33.2 — Media Stack v1 staged implementation (frame/audio/edit/render)
Status: **COMPLETED**

Scope:
- Implement deterministic staged pipeline wiring for:
  - frame outputs + frame manifest
  - audio outputs + audio manifest
  - edit/timeline outputs
  - render manifest + final assembly
- OpenCV (or equivalent deterministic CV library) MAY be used for deterministic preprocessing and quality utilities.
- Keep stage artifacts under `sandbox/output/<job_id>/**`.
- Preserve `job.json` as execution authority and Worker determinism constraints.
- CV tooling usage MUST NOT change authority boundaries or runtime write boundaries.

Outcome:
- Multi-stage Worker production pipeline is executable with inspectable stage artifacts.

---

### PR-33.3 — Optional Mode B contract expansion (script/identity/storyboard)
Status: **COMPLETED**

Scope:
- Introduce optional, versioned planner-side contracts:
  - `script_plan.v1`
  - `identity_anchor.v1`
  - `storyboard.v1`
- Keep these contracts planner/control-plane facing; they must not replace `job.json` execution authority.
- Add minimal examples and deterministic validators.

Outcome:
- Mode B planning surfaces become explicit and reusable without changing core authority boundaries.

---

### PR-34 — External HITL recast flow (Viggle pack export + re-ingest contract)
Status: **COMPLETED**

Scope:
- Model external recast as Ops/Distribution flow with explicit states/artifacts.
- Export deterministic recast packs to `sandbox/dist_artifacts/<job_id>/viggle_pack/**`.
- Define ingress metadata contract for re-ingested external result.
- Worker performs deterministic finishing only.

Outcome:
- Fast quality iteration with explicit manual boundary and auditability.

---

### PR-34.1 — External HITL recast implementation (ops flow + re-ingest path)
Status: **COMPLETED**

Scope:
- Implement deterministic export-pack builder for:
  - `sandbox/dist_artifacts/<job_id>/viggle_pack/**`
- Implement explicit re-ingest adapter path via `sandbox/inbox/*.json` metadata pointer contract.
- Add idempotent ops-state handling for recast export/re-ingest lifecycle.
- Keep external tool execution outside factory authority boundaries.
- Worker remains deterministic finishing only; no direct external recast service calls.

Outcome:
- External HITL recast loop is operational, auditable, and boundary-safe end-to-end.

---

### PR-34.2 — HITL lifecycle + inbox pointer contracts
Status: **COMPLETED**

Scope:
- Define lifecycle/state contracts for external recast steps (e.g., ready/exported/re-ingested/finished).
- Define deterministic inbox pointer schema for re-ingest metadata under `sandbox/inbox/*.json`.
- Preserve canonical dist artifact path:
  - `sandbox/dist_artifacts/<job_id>/viggle_pack/**`

Outcome:
- External manual steps become explicit, auditable, and idempotent in contract/state form.

---

### PR-34.3 — `viggle_pack.v1` schema + export/re-ingest validation
Status: **COMPLETED**

Scope:
- Add `viggle_pack.v1` schema for pack completeness/consistency checks.
- Add deterministic validators for:
  - pack export contents
  - re-ingest metadata pointer integrity
- No direct external-tool invocation inside factory components.

Outcome:
- Viggle-class HITL handoff is standardized and validation-backed for future automation.

---

### PR-34.4 — Recast quality gates + deterministic scoring
Status: **COMPLETED**

Scope:
- Define deterministic quality metrics and report artifacts for recast outputs:
  - identity consistency
  - mask bleed/edge artifacts
  - temporal jitter/flicker
  - loop seam quality
  - audio/video sync + audio-stream presence
- Add deterministic pass/fail thresholds and a QC report schema under logs/output validation flow.
- Keep scoring artifact-only; no model-side autonomy or external API dependence inside Worker.

Outcome:
- Recast quality is measurable and gateable with deterministic, reviewable signals.

---

### PR-34.5 — Recast benchmark harness (quality regression set)
Status: **COMPLETED**

Scope:
- Add deterministic benchmark harness for a fixed set of demo loops + hero targets.
- Produce comparable quality reports across runs (baseline vs HITL outputs).
- Add smoke command path for repeatable quality regression checks.
- Keep benchmark inputs/outputs contract-bound and repo-safe (no copyrighted media committed).

Outcome:
- Quality improvements and regressions are visible, testable, and auditable before release decisions.

---

### PR-34.6 — Internal Baseline V2 motion-preserve pipeline (deterministic, non-overlay)
Status: **PLANNED**

Scope:
- Add a deterministic internal baseline path that improves quality without overlay recast and without external HITL dependency:
  - motion-preserve 9:16 reframing
  - stabilization/denoise/color normalization
  - deterministic loop seam refinement
  - deterministic audio normalization + stream guarantee
  - subtitle/watermark finishing
- Add optional contract block/settings for internal baseline tuning while preserving permissive lane policy.
- Emit deterministic stage artifacts/manifests under `sandbox/output/<job_id>/**`.
- Keep `job.json` as execution authority and preserve Worker determinism/no-network rules.
- ADR requirement:
  - requires an ARCH-approved ADR before implementation because it introduces new Worker contract semantics for baseline-v2 tuning.

Outcome:
- Internal baseline output quality is materially better than legacy overlay path and benchmark-comparable as a non-HITL fallback.

---

### PR-34.7 — Deterministic quality-controller loop (artifact-driven retries + escalation)
Status: **ACTIVE**

Scope:
- Add deterministic quality decision contract artifact under:
  - `sandbox/logs/<job_id>/qc/quality_decision.v1.json`
- Add deterministic policy engine that maps failed quality metrics to bounded next actions:
  - recast quality failure -> retry recommendation (within capped attempts)
  - costume fidelity failure -> block finalize and require corrected recast input
  - repeated failures -> explicit HITL escalation state
- Add deterministic loop runner orchestration for:
  - evaluate reports
  - compute next action
  - emit auditable decision artifact
- Keep all loop state file-based; no hidden autonomy/background agents.
- Preserve existing authority boundaries:
  - Planner writes job contracts only
  - Control Plane writes logs/state only
  - Worker writes output only
  - external recast remains explicit HITL.
- ADR requirement:
  - requires an ARCH-approved ADR before implementation because it introduces a new deterministic quality-decision policy contract.

Outcome:
- Quality iteration becomes deterministic, auditable, and repeatable with explicit retry budgets and fail-loud escalation.

Sub-PR plan:

### PR-34.7a — Reverse-analysis contracts (truth vs suggestions split)
Status: **COMPLETED**

Scope:
- Add CAF-owned canonical reverse-analysis schema:
  - `repo/shared/caf.video_reverse_prompt.v1.schema.json`
- Add deterministic analyzer checkpoint schemas:
  - beat grid (timestamps/BPM)
  - pose checkpoints (key timestamps + compact pose features)
  - keyframe checkpoints
- Add optional vendor suggestion artifact envelope (non-authoritative):
  - `repo/analysis/vendor/indiegtm/**`
  - `repo/analysis/vendor/nanophoto/**`
  - `repo/analysis/vendor/bigspy/**`
- Enforce contract rule:
  - deterministic analyzer fields = authoritative facts
  - vendor fields = optional suggestions only

Outcome:
- Reverse-analysis data model is stable, planner-readable, and authority-safe.

---

### PR-34.7b — Planner enrichment adapter (optional vendor plugins)
Status: **COMPLETED**

Scope:
- Add planner-side optional plugin adapter for vendor suggestion ingestion.
- Merge vendor suggestions into planner context as optional hints only.
- Wire deterministic reverse-analysis artifacts into planner quality constraints:
  - `beat_grid.v1`
  - `pose_checkpoints.v1`
  - `keyframe_checkpoints.v1`
  - `caf.video_reverse_prompt.v1`
- Keep all vendor integrations non-blocking and optional for daily pipeline.
- No Worker dependency on vendor artifacts.

Outcome:
- Planner consumes measured quality constraints plus optional suggestions without introducing hard vendor dependencies.

---

### PR-34.7c — Deterministic segment-generate-stitch planning contracts
Status: **COMPLETED**

Scope:
- Add planner/control contracts for short segment generation plans:
  - bounded segment duration defaults (<=3s)
  - deterministic stitch order + seam metadata
  - explicit retry slots per segment
- Encode locked defaults for dance-quality scenarios:
  - `constraints.camera_lock = true`
  - `constraints.background_lock = true`
  - `constraints.max_shot_length_sec = 3`
- Drive per-segment retry slot assignment from beat/pose/keyframe checkpoints.

Outcome:
- Motion/identity drift risk is reduced via deterministic short-segment orchestration.

---

### PR-34.7d — Quality-loop policy engine + escalation states
Status: **COMPLETED**

Scope:
- Add deterministic quality decision artifact:
  - `sandbox/logs/<job_id>/qc/quality_decision.v1.json`
- Add bounded action policy map from failed metrics to next actions.
- Add explicit capped retry + escalation states (fail-loud HITL handoff).
- Require policy decisions to consume:
  - deterministic quality report artifacts
  - segment checkpoint coverage signals
- Keep loop artifact-driven and auditable; no hidden autonomous agent execution.

Outcome:
- Quality optimization loop is deterministic, reproducible, and operationally safe.

---

### PR-34.7e — Analyzer Core Pack implementation (deterministic signals for quality loop)
Status: **COMPLETED**

Scope:
- Implement deterministic analyzer signal extraction and emit canonical artifacts:
  - FFprobe metadata truth fields (fps, resolution, duration, codec)
  - PySceneDetect shot boundaries -> shot timestamps
  - pose checkpoints (MoveNet/MediaPipe class implementation)
  - OpenCV optical-flow motion curves
  - librosa BPM/beat/onset grid
- Ensure generated outputs map directly into PR-34.7a schemas.
- Keep analyzer outputs planner-side metadata only; no Worker runtime authority dependency.

Outcome:
- Quality-controller inputs are generated deterministically from analyzer core signals and are actually usable by planner/control retries.

---

### PR-34.7f — Facts-only planner guard + analyzer facts completeness
Status: **COMPLETED**

Scope:
- Extend analyzer-core outputs with deterministic visual facts needed for planner grounding:
  - brightness stats
  - palette stats
  - basic camera movement classification confidence
- Add planner-side facts-only guard policy:
  - planner may use analyzer facts only
  - when a fact is unavailable, planner must emit `unknown` instead of inferring unsupported details
- Add deterministic validation/smoke checks to fail when planner outputs claims that are not analyzer-backed.

Outcome:
- Reverse planning becomes consistent, versionable, repo-safe, and automatable with explicit unknown handling.

---

### PR-34.7g — Segment generate+stitch runtime execution path
Status: **PLANNED**

Scope:
- Implement deterministic segment render execution from `segment_stitch_plan.v1` (not contracts-only).
- Emit per-segment runtime artifacts and stitch report under canonical output paths.
- Enforce seam strategy execution (hard cut/crossfade/motion blend) from segment plan contract.

Outcome:
- Segment-first quality path is executable end-to-end and auditable.

---

### PR-34.7h — Two-pass motion→identity orchestration
Status: **PLANNED**

Scope:
- Add explicit pass-level orchestration artifacts for:
  - motion pass (dance fidelity first)
  - identity pass (hero consistency second)
- Enable pass-level retry decisions in controller policy artifacts.
- Preserve explicit external HITL boundary for identity recast where required.

Outcome:
- Motion-vs-identity tradeoff becomes explicit, controllable, and measurable.

---

### PR-34.7i — Quality target tuning + segment-level auto-retry policy
Status: **PLANNED**

Scope:
- Extend quality decision mapping to segment-level retry actions.
- Tune and codify quality thresholds for dance fidelity dimensions.
- Keep retries bounded and deterministic with fail-loud escalation.

Outcome:
- Quality loop improves outputs with targeted retries instead of coarse reruns.

---

### PR-34.7k — Quality target contract artifact
Status: **PLANNED**

Scope:
- Add a versioned quality-target contract artifact for per-job acceptance thresholds.
- Wire controller decisions to explicit target contract values instead of implicit defaults.
- Add deterministic validation and smoke checks for quality-target contract parsing/enforcement.

Outcome:
- Quality acceptance criteria become explicit, auditable, and portable across jobs.

---

### PR-34.7l — Segment/shot debug exports for quality tuning
Status: **PLANNED**

Scope:
- Emit deterministic debug artifacts per segment/shot:
  - seam preview assets
  - motion curve snapshots
  - selected checkpoint overlays/strips
- Keep exports output-bound and non-authoritative.

Outcome:
- Quality failures become diagnosable quickly with concrete artifact evidence.

---

### PR-34.7m — Episode continuity pack (planner + quality shared input)
Status: **PLANNED**

Scope:
- Introduce a versioned episode continuity pack contract (hero/style/costume refs + drift rules).
- Make planner and quality checks consume the same continuity pack inputs.
- Add deterministic validation and smoke coverage.

Outcome:
- Cross-episode consistency improves with shared continuity authority inputs.


------------------------------------------------------------

## Completion Criteria

The project is considered **portfolio-complete** when:
- Phase 1 is complete (PR-3 merged)
- PR-5 is complete (Gemini autonomy via AI Studio)
- PR-25 is complete (Vertex AI presence demonstrated)
- All invariants remain intact
- LOCAL v0.1 can be verified with a single command

Phases 4+ must not compromise Phase 1 guarantees.
