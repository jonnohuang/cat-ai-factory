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

## Phase 1 — LOCAL v0.1 Deterministic Pipeline

Purpose: prove reproducibility, idempotency, and artifact lineage locally.

### PR-1 — Job contract v1
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
Scope:
- Per-job output directories
- Atomic overwrite / safe reruns
- result.json run metadata
- Determinism check

Outcome:
- Re-runnable worker
- Stable paths
- Deterministic artifacts

---

### PR-3 — Artifact lineage + determinism harness
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
Status: Optional but recommended (portfolio demo)

Scope:
- Add a small demo pack under:
  docs: minimal “how to run demo” notes
  assets: `sandbox/assets/demo/`
  jobs: `sandbox/jobs/demo-*.job.json`
- Include 2–4 canonical “cat activity” examples aligned with Shorts/Reels style.
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

## Phase 2 — AGENTS v0.2 Control Plane Semantics (Optional but Recommended)

Purpose: demonstrate real agent orchestration without sacrificing safety.

### PR-4 — Ralph Loop state machine
Scope:
- Explicit job lifecycle states
- Deterministic reconciliation loop

Outcome:
- Control-plane semantics are explicit and testable

---

### PR-5 — Planner Adapter Layer (LangGraph / CrewAI + RAG provider)
Scope:
- Introduce a planner adapter interface (frameworks are adapters, not foundations)
- Provide:
  - default planner mode (existing)
  - LangGraph-backed planner adapter (optional)
  - CrewAI-style planner adapter (optional)
- Add a planner-only RAG provider abstraction:
  - optional, pluggable context retrieval
  - must not move into orchestrator or worker
- Adapters must produce the same `job.json` schema (contract remains stable)

Hard constraints:
- RAG is planner-only
- No framework becomes mandatory
- No orchestration semantics move into frameworks
- No worker LLM usage

Outcome:
- Framework alignment without lock-in
- Clear portfolio signal: “adapters, not foundations”

---

### PR-6 — Verification / QC agent
Scope:
- Deterministic, read-only evaluator
- Contract + output conformance checks
- Emits QC results as logs/summary artifacts (no mutation of existing artifacts)

Outcome:
- Production-grade quality gates without autonomy creep

------------------------------------------------------------

## Phase 3 — CLOUD v0.3 Migration (Optional / Stretch)

Purpose: show cloud literacy and clean mapping; do not compromise LOCAL guarantees.

### PR-7 — Cloud artifact layout
Scope:
- GCS path conventions
- Firestore job state schema
- Mapping remains consistent with local lineage

---

### PR-8 — Cloud Run orchestration stub
Scope:
- Minimal Cloud Run deployment for orchestrator
- No new semantics; same contracts and states

---

### PR-9 — CI/CD skeleton
Scope:
- Lint + harness execution
- No auto-deploy required
- Preserve determinism checks

------------------------------------------------------------

## Completion Criteria

The project is considered **portfolio-complete** when:
- Phase 1 is complete (PR-3 merged)
- All invariants remain intact
- LOCAL v0.1 can be verified with a single command

Phases 2 and 3 are optional enhancements and should not compromise Phase 1 guarantees.

