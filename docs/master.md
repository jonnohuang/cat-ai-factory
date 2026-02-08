# Cat AI Factory — Master Design Document (v1)

This document is the living design brain of the Cat AI Factory project.
It captures **why** the system is structured the way it is, and the invariants that must remain true.

It is intentionally principle-driven. Binding architectural changes must be recorded in `docs/decisions.md`.

------------------------------------------------------------

## Docs Index

- Architecture (diagram-first): `docs/architecture.md`
- Decisions (binding ADRs): `docs/decisions.md`
- System requirements (reviewer-readable): `docs/system-requirements.md`
- PR roadmap (sequencing + scope): `docs/PR_PROJECT_PLAN.md`
- Historical context (non-authoritative): `docs/memory.md`

------------------------------------------------------------

## Project Intent

Cat AI Factory is not a demo chatbot or prompt experiment.

It is a **production-minded agent system** designed to demonstrate how AI agents
can be safely operationalized using real infrastructure patterns suitable for
ML Infrastructure and Platform Engineering roles.

The goal is not “one perfect AI video”.
The goal is a **repeatable daily pipeline** with clear contracts, safety boundaries,
and a clean cloud migration path.

------------------------------------------------------------

## Core Philosophy

### Determinism over Autonomy

- Outputs should be reproducible from inputs.
- Agents advise and coordinate; infrastructure enforces safety.
- Side effects occur only in controlled execution stages.

### Files as the Source of Truth

- Files provide explicit contracts, durability, and debuggability.
- Artifact-based workflows mirror real ML pipelines (data → transform → artifact).
- Failure modes are observable and recoverable.

------------------------------------------------------------

## Three-Plane Architecture (Invariant)

Cat AI Factory separates responsibilities into three planes:

- **Planner**
  - LLM-driven (non-deterministic) but constrained
  - Produces versioned, validated `job.json` contracts
  - **No side effects, no artifact writes**

- **Control Plane (Orchestrator)**
  - Deterministic state machine
  - Idempotency, retries, audit logging, artifact lineage
  - Coordinates execution; does not embed CPU-bound work

- **Worker**
  - Deterministic rendering/execution (no LLM usage)
  - Same inputs → same outputs (within documented tolerance)
  - Safe to retry without side effects

Frameworks (e.g., orchestration libraries), RAG, and auxiliary agents must be treated as **adapters**
that preserve this invariant. Decisions that alter plane responsibilities require an ADR.

------------------------------------------------------------

## Control Plane vs Data Plane

The system deliberately separates:

- **Control Plane**
  - Planning
  - Orchestration
  - Approval logic (file-bus mediated; outside the Worker)
  - State reconciliation
  - Budget enforcement (pre-spend gates; future)

- **Data Plane**
  - CPU-bound rendering
  - Deterministic transformations
  - Artifact generation

Ralph Loop operates exclusively in the control plane.

------------------------------------------------------------

## Local-First, Cloud-Ready

Local development:
- Docker Compose
- Sandboxed filesystem
- Loopback-only networking

Cloud target:
- Cloud Run for orchestration
- Pub/Sub for decoupling
- GCS for artifacts
- Firestore for state

This allows fast iteration locally while preserving a clean cloud migration path.

------------------------------------------------------------

## Failure & Safety Model

- Fail fast.
- Fail loud.
- Never partially mutate state.
- No destructive actions without explicit human confirmation.

These guarantees are enforced by infrastructure, not by prompts.

------------------------------------------------------------

## Portfolio Framing

This project is intentionally designed to answer:
- “How would you run agents in production?”
- “How do you prevent unsafe autonomy?”
- “How do you debug and reason about agent behavior?”

The answer is: **clear contracts, separation of concerns, and infra-enforced guardrails**.

------------------------------------------------------------

## Ops/Distribution Layer (Outside the Factory)

Publishing and distribution workflows are inherently nondeterministic (external APIs).
They must remain **outside** the core factory invariant (Planner / Control Plane / Worker).

Ops/Distribution is a separate layer that:
- consumes immutable worker outputs
- consumes planner-produced publish metadata
- enforces human approval gates by default
- emits **derived distribution artifacts** (dist artifacts)
- may optionally perform platform uploads (opt-in, platform-specific, credentials out-of-repo)

Hard constraints:
- Ops/Distribution is NOT a replacement for Clawdbot (Planner) or Ralph Loop (Control Plane).
- Ops/Distribution must NOT mutate `job.json`.
- Ops/Distribution must NOT modify worker outputs under:
  - `/sandbox/output/<job_id>/final.mp4`
  - `/sandbox/output/<job_id>/final.srt`
  - `/sandbox/output/<job_id>/result.json`

If platform-specific formatting is needed, write derived **dist artifacts**:
- `sandbox/dist_artifacts/<job_id>/<platform>.json`
- `sandbox/dist_artifacts/<job_id>/<platform>.state.json`

Publishing should be gated by human approval by default.
Publishing must be idempotent: store `platform_post_id` / `post_url` keyed by `{job_id, platform}`
to prevent double-posting.

------------------------------------------------------------

## Daily Output Strategy (Policy; not an invariant)

The system is designed to support a sustainable “daily output” workflow under strict budgets.

This is intentionally achieved via multiple content lanes (policies), while preserving
the deterministic Worker and the 3-plane invariant.

The lane strategy itself is a binding roadmap decision (see ADRs), but the *existence*
of lanes does not change the core architecture invariant.

------------------------------------------------------------

## Future Work (Non-Binding)

This section is intentionally non-binding.
All binding commitments belong in ADRs + `docs/PR_PROJECT_PLAN.md`.

- Multi-platform publisher adapters (bundle-first, upload optional).
- Local distribution runner (approval-gated automation).
- Publish plan contract + export bundle spec.
- Hero cat cast registry (metadata; not agents).
- Multilingual support (en + zh-Hans first).
- Lane-based content generation (template remix, image motion, premium AI video).
- Budget enforcement (local + cloud).
- Cloud migration (GCS/Firestore/Cloud Run) preserving file-bus semantics.
- CI/CD skeleton and reproducible checks.

