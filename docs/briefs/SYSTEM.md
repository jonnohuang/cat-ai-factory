# SYSTEM — Cat AI Factory (Prompt Brief)

This is a **non-authoritative** quick brief for onboarding and prompting.

Authoritative sources:
- Invariants & rationale: `docs/master.md`
- Binding decisions (ADRs): `docs/decisions.md`
- Diagram-first architecture: `docs/architecture.md`
- PR roadmap: `docs/PR_PROJECT_PLAN.md`

------------------------------------------------------------

## What this system is

Cat AI Factory (CAF) is a **headless, file-contract, deterministic** agent pipeline
for generating short-form vertical videos (Shorts / Reels / TikTok).

CAF is designed as a production-minded portfolio system:
- explicit contracts (`job.json`, publish artifacts)
- strict separation of concerns (Planner vs Control vs Worker)
- infra-enforced safety and debuggability
- local-first execution with a clean cloud migration path

------------------------------------------------------------

## Canonical architecture (invariant)

Three-plane separation is non-negotiable:

### Planner Plane (Clawdbot)
- LLM-driven, nondeterministic but constrained
- Inputs: `/sandbox/PRD.json` + optional `/sandbox/inbox/*.json` + optional RAG (planner-only)
- Output: versioned, schema-valid `/sandbox/jobs/*.job.json`
- **No side effects, no artifact writes beyond job contracts**

### Control Plane (Ralph Loop)
- Deterministic reconciler / state machine
- Reads job contracts and observed artifacts
- Coordinates deterministic execution (worker)
- Writes logs/state only under `/sandbox/logs/<job_id>/**`
- Must not mutate `job.json`

### Worker Plane (FFmpeg Renderer)
- Fully deterministic rendering / transformation
- Reads only `job.json` + `/sandbox/assets/**`
- Writes outputs only under `/sandbox/output/<job_id>/**`
- No LLM usage, no nondeterministic calls
- Safe to retry (idempotent)

------------------------------------------------------------

## Files-as-bus (coordination model)

Agents coordinate **only via files**:
- no shared memory
- no agent-to-agent RPC
- no hidden state

Canonical lineage:
`/sandbox/PRD.json → /sandbox/jobs/<job>.job.json → /sandbox/output/<job_id>/**`

See: `docs/architecture.md`

------------------------------------------------------------

## Verification / QC (read-only)

Verification agents/tools (QC) are deterministic and read-only:
- validate contracts
- verify output conformance + artifact lineage
- emit QC summaries under `/sandbox/logs/<job_id>/qc/**`
- must not modify job/assets/output artifacts

------------------------------------------------------------

## Ops/Distribution (Outside the Factory)

Publishing and distribution workflows are outside the core factory.
They are inherently nondeterministic (external platforms, approvals, humans).

CAF defines “distribution” as:
- export bundles + platform copy artifacts
- derived dist artifacts (idempotency state)
- optional cloud mirroring (e.g., GCS)

Hard constraints:
- Must not mutate `job.json`.
- Must not modify worker outputs under `/sandbox/output/<job_id>/**`.
- Must write only derived artifacts under:
  - `/sandbox/dist_artifacts/<job_id>/**`
- Publishing is human-approved by default.
- Publishing idempotency is keyed by `{job_id, platform}` via:
  - `/sandbox/dist_artifacts/<job_id>/<platform>.state.json`

------------------------------------------------------------

## Required pre-cloud posture (summary)

Before cloud migration, CAF must support a real daily workflow locally:
- publish_plan.json contract exists
- bundle-first publisher adapters exist (YouTube / IG / TikTok / X)
- audio plan + optional SFX assets are included in export bundles
- multilingual copy supports N languages, with **en + zh-Hans enabled initially**

------------------------------------------------------------

## Reminder: authority boundaries

This document is a prompt brief only.

If there is any conflict:
- `docs/master.md` wins for invariants
- `docs/decisions.md` wins for binding decisions
- `docs/architecture.md` wins for diagrams and repo mapping
- `docs/PR_PROJECT_PLAN.md` wins for sequencing/scope

