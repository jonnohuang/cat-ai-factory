# Cat AI Factory — Master Design Document (v1)

This document is the living design brain of the Cat AI Factory project.
It captures **why** the system is structured the way it is, and the invariants that must remain true.

It is intentionally principle-driven. Binding architectural changes must be recorded in `docs/decisions.md`.

------------------------------------------------------------

## Docs Index

- Architecture (diagram-first): `docs/architecture.md`
- Decisions (binding ADRs): `docs/decisions.md`
- Historical context (non-authoritative): `docs/memory.md`

------------------------------------------------------------

## Project Intent

Cat AI Factory is not a demo chatbot or prompt experiment.

It is a **production-minded agent system** designed to demonstrate how AI agents
can be safely operationalized using real infrastructure patterns suitable for
ML Infrastructure and Platform Engineering roles.

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
  - Approval logic (future)
  - State reconciliation

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

## Future Work (Non-Binding)

- CI/CD pipeline integration.
- Formal schema validation for job contracts.
- Approval workflow agent (control-plane gatekeeper).
- Cost-aware scheduling and throttling.
- Multi-niche routing.

Future work must preserve the three-plane invariant. Binding commitments belong in ADRs.


------------------------------------------------------------

## Ops/Distribution Layer (Outside the Factory)

Publishing and distribution workflows are inherently nondeterministic (external APIs).
They must remain **outside** the core factory invariant (Planner / Control Plane / Worker).

Ops/Distribution may be implemented using tools like:
- n8n (triggers, notifications, approval gates)
- Slack/Discord/email integrations
- Cloud Run publisher adapters
- Pub/Sub event routing
- Firestore status tracking

Hard constraints:
- Ops/Distribution is NOT a replacement for Clawdbot (Planner) or Ralph Loop (Control Plane).
- Ops/Distribution must NOT mutate `job.json`.
- Ops/Distribution must NOT modify worker outputs under:
  - `/sandbox/output/<job_id>/final.mp4`
  - `/sandbox/output/<job_id>/final.srt`
  - `/sandbox/output/<job_id>/result.json`
- If platform-specific formatting is needed, write derived **dist artifacts**:
  - `sandbox/dist_artifacts/<job_id>/<platform>.json`
  - (cloud equivalent: `gs://.../dist_artifacts/<job_id>/<platform>.json`)
- Publishing should be gated by human approval by default.
- Publishing must be idempotent: store `platform_post_id` / `post_url` keyed by `{job_id, platform}` to prevent double-posting.

