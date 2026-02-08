# Cat AI Factory — PR Project Plan

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
- However, Ops/Distribution is REQUIRED before Cloud migration, because it defines
  the “posting modules” and daily operational workflow.

------------------------------------------------------------

## Phase 0 — Governance & Documentation (Completed)

Purpose: establish authority, invariants, and navigability.

### PR-0 — Docs normalization + architecture
Status: Completed

Scope:
- Normalize master / decisions / chat bootstrap
- Add diagram-first architecture
- Add SYSTEM, GUARDRAILS, and milestone briefs

Outcome:
- Clear architectural authority
- Safe collaboration with Codex and IMPL
- Recruiter-readable docs

------------------------------------------------------------

## Phase 1 — LOCAL v0.1 Deterministic Pipeline (Completed)

Purpose: prove reproducibility, idempotency, and artifact lineage locally.

### PR-1 — Job contract v1
Status: Completed

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
Status: Completed

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
Status: Completed

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
Status: Completed (recommended demo pack)

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

## Phase 2 — AGENTS v0.2 Control Plane + Planner Autonomy (Completed)

Purpose: demonstrate real agent orchestration + autonomous planning without sacrificing safety.

### PR-4 — Ralph Loop state machine (single-job orchestrator)
Status: Completed

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
Status: Completed

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
Status: Completed

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
Status: Completed

Scope:
- Add planner prompt guardrails (PRD/inbox treated as untrusted; JSON-only)
- Ensure debug surfaces never print model raw text (len-only) and never print secrets

Outcome:
- Reduced leakage risk
- Stronger production safety posture

---

### PR-6 — Verification / QC agent
Status: Completed

Scope:
- Deterministic, read-only evaluator
- Contract + output conformance checks
- Emits QC results as logs/summary artifacts (no mutation of existing artifacts)

Outcome:
- Production-grade quality gates without autonomy creep

---

### PR-6.1 — Harness-only QC integration (reporting-only)
Status: Completed

Scope:
- Integrate QC into the local harness.
- QC is additive reporting only; does not change harness PASS/FAIL gating.
- QC results are recorded in harness summary artifacts.

Outcome:
- QC is a first-class reporting surface in the local development harness.
- Clear separation: harness gating vs QC reporting.

------------------------------------------------------------

## Phase 3 — Ops/Distribution v0.2 (Completed)

Purpose: demonstrate real-world “agent → human approval → publish artifacts” workflows without contaminating core determinism.

### PR-7 — Telegram/mobile control adapter (inbox/status bridge)
Status: Completed

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
Status: Completed

Scope:
- Define publish contracts, approval artifacts, and idempotency conventions.
- Lock derived artifact conventions under `sandbox/dist_artifacts/`.
- No changes to worker outputs or job.json schema.

Outcome:
- Stable publish/idempotency conventions
- Prevents drift in Ops/Distribution artifact semantics

---

### PR-9 — Publish pipeline MVP (YouTube first) + approval gate
Status: Completed

Scope:
- YouTube publish adapter
- Approval gate via inbox artifacts
- Idempotency via dist_artifacts state file
- Must not modify worker outputs

Outcome:
- End-to-end “COMPLETED → approved → published” workflow for YouTube

------------------------------------------------------------

## Phase 4 — Daily Output System v0.3 (Required before Cloud)

Purpose: achieve 3 clips/day under strict budget constraints without violating determinism.

Key idea:
- CAF is a deterministic renderer with multiple production lanes.
- Telegram daily plan brief is the canonical human input.
- Promotion outputs are artifacts and bundles (bundle-first).

### PR-10 — Roadmap + ADR locks (docs-only)
Status: ACTIVE (this PR)

Scope:
- Rewrite PR plan sequencing (daily lanes + promotion toolkit + publisher adapters before cloud)
- Append ADRs locking the new roadmap decisions:
  - lanes
  - hero cats (metadata)
  - multilingual support (en + zh-Hans)
  - audio plan
  - LangGraph planner-only
  - Seedance optional
- Align docs (system requirements + architecture notes) with required posture

Outcome:
- A stable “constitution” for the next implementation era

---

### PR-11 — Lane contracts + expected outputs (no cloud yet)
Scope:
- Define lane identifiers: ai_video | image_motion | template_remix (contract-level)
- Define expected artifacts per lane (local paths)
- No change to core 3-plane invariant

Outcome:
- Lane-aware planning and publish planning becomes explicit and reviewable

---

### PR-12 — Lane C: Template registry + deterministic template_remix recipes
Scope:
- Add a template registry (deterministic metadata)
- Worker supports template_remix lane via FFmpeg-only recipes

Outcome:
- Near-free daily clips at scale (C lane)

---

### PR-13 — Lane B: image_motion (seed frames + deterministic motion presets)
Scope:
- Seed image request/selection interface (planner-side or pre-worker; not in worker)
- Worker adds deterministic motion presets (Ken Burns/zoom/shake/cuts)

Outcome:
- Cheap “video-like” clips (B lane)

---

### PR-14 — Hero cats registry (metadata only) + planner bindings
Scope:
- Add character registry + schema + validator
- Planner uses hero-cat metadata for series consistency (no agent behavior)

Outcome:
- Series continuity and retention improvement

------------------------------------------------------------

## Phase 5 — Promotion Toolkit + Publisher Modules v0.3 (Required before Cloud)

Purpose: make posting fast, safe, and repeatable without requiring platform automation.

### PR-15 — Publish plan v1 (multilingual + audio plan included)
Scope:
- publish_plan.json v1 + schema + validator
- language-map structures (en + zh-Hans enabled)
- audio plan per clip (strategy + notes + optional assets list)
- Generates platform copy artifacts and posting metadata

Outcome:
- Deterministic “algorithm farming” toolkit via artifacts (no posting required)

---

### PR-16 — Publisher Adapter Interface + Platform Modules (bundle-first)
Scope:
- Define Publisher Adapter interface (platform-agnostic)
- Implement v1 adapters that generate export bundles + checklists:
  - YouTube / Instagram / TikTok / X
- Bundles contain:
  - final.mp4 (+ captions/srt if present)
  - per-language copy files
  - audio_notes.txt + audio_plan.json (+ optional audio assets)
  - posting_checklist_{platform}.txt
- Upload automation:
  - optional per platform
  - opt-in
  - official APIs only
  - credentials out-of-repo only

Outcome:
- Required “posting modules” exist before cloud; manual posting <2 minutes/clip

------------------------------------------------------------

## Phase 6 — Cloud v0.4 Migration (After local daily workflow is proven)

Purpose: demonstrate cloud literacy while preserving LOCAL guarantees.

### PR-17 — Cloud artifact layout (GCS + Firestore mapping)
Scope:
- GCS path conventions (immutable artifacts)
- Firestore job + publish state mapping consistent with local lineage

Outcome:
- Cloud storage/state explicitly modeled

---

### PR-18 — Cloud Run execution stubs (orchestrator + worker)
Scope:
- Minimal Cloud Run deployment
- Preserve contracts and states; no redesign

Outcome:
- Clean cloud execution path without semantics drift

---

### PR-19 — Vertex AI providers (mandatory portfolio requirement)
Scope:
- Vertex AI provider adapters (planner-side)
- Lane A: Veo (ai_video), Lane B: Imagen (seed frames) as applicable
- Maintain adapter boundaries and deterministic worker behavior

Outcome:
- Enterprise/production path demonstrated

---

### PR-20 — Budget guardrails + enforcement (local + cloud)
Scope:
- Cost estimation and caps (hard stop) before spending
- Idempotent accounting keys; retry-safe enforcement

Outcome:
- Safe autonomy and cost control

---

### PR-21 — CI/CD skeleton
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
- PR-19 is complete (Vertex AI presence demonstrated)
- All invariants remain intact
- LOCAL v0.1 can be verified with a single command

Phases 4+ must not compromise Phase 1 guarantees.
