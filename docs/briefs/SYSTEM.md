# SYSTEM — Cat AI Factory (Prompt Brief)

This is a **non-authoritative** quick brief for onboarding and prompting.
Authoritative sources: `docs/master.md` (invariants), `docs/decisions.md` (ADRs), `docs/architecture.md` (diagrams).

------------------------------------------------------------

## What this system is

Cat AI Factory is a **headless, file-contract, deterministic** agent pipeline that generates short-form videos.

It demonstrates production-grade agent operationalization:
- explicit contracts (`job.json`)
- strict separation of concerns
- infra-enforced safety and debuggability

------------------------------------------------------------

## Canonical architecture (invariant)

Three-plane separation is non-negotiable:

- **Planner (Clawdbot)**
  - LLM-driven, constrained
  - Inputs: PRD + optional instructions (+ optional RAG)
  - Output: versioned, validated `job.json`
  - **No side effects, no artifact writes**

- **Control Plane (Ralph Loop)**
  - Deterministic state machine / reconciler
  - Idempotency, retries, audit logging, artifact lineage

- **Worker (FFmpeg)**
  - Fully deterministic rendering
  - No LLM usage
  - Safe to retry

------------------------------------------------------------

## Contracts & coordination

- Agents coordinate **only via files** (no shared memory, no RPC).
- `PRD.json → job.json → outputs` is the canonical lineage.

See: `docs/architecture.md`


------------------------------------------------------------

## Ops/Distribution (Outside the Factory)

Publishing and distribution automation (e.g., n8n workflows + platform adapters) is **outside** the core factory.
It may consume events and immutable artifacts for notifications, approval, and posting.

Hard constraints:
- Must not mutate `job.json`.
- Must not modify worker outputs under `/sandbox/output/<job_id>/...`.
- If platform-specific formatting is needed, emit derived dist artifacts:
  - `sandbox/dist_artifacts/<job_id>/<platform>.json`
- Publishing should be gated by human approval and must be idempotent via `{job_id, platform}` keys.

