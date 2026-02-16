# Cat AI Factory — Master Design Document (v2)

This document is the living design brain of the Cat AI Factory (CAF) project.
It captures **why** the system is structured the way it is, and the invariants that must remain true.

This document is principle-driven.
Binding architectural changes must be recorded in `docs/decisions.md` as ADRs.

------------------------------------------------------------

## Docs Index (Authority Map)

Binding:
- Architecture (diagram-first): `docs/architecture.md`
- Decisions (binding ADRs; append-only): `docs/decisions.md`
- System requirements (reviewer-readable): `docs/system-requirements.md`
- PR roadmap (sequencing + scope): `docs/PR_PROJECT_PLAN.md`

Non-binding:
- Historical context: `docs/memory.md`

------------------------------------------------------------

## Project Intent

Cat AI Factory is not a prompt demo, chatbot, or “one-off AI video generator”.

CAF is a **production-minded, contract-first agent system** designed to demonstrate:
- safe operationalization of LLM planning
- deterministic execution boundaries
- reproducible artifact pipelines
- portfolio-grade architecture discipline
- a clean migration from local → cloud without rewriting semantics

The goal is not “one perfect AI video”.
The goal is a **repeatable daily pipeline** with strong contracts, safety boundaries,
and an event-driven cloud runtime.

------------------------------------------------------------

## Core Philosophy

### Determinism over Autonomy
- Outputs must be reproducible from explicit inputs.
- The Planner may be nondeterministic; execution must not be.
- Side effects occur only in controlled execution stages.

### Files as the Source of Truth
- Files provide explicit contracts, durability, and debuggability.
- Artifact-based workflows mirror real ML pipelines:
  input → transform → artifact → verification.
- Failure modes are observable and recoverable.

### Portfolio-Ready Engineering Discipline
CAF is intentionally designed to answer:
- “How would you run agents in production?”
- “How do you prevent unsafe autonomy?”
- “How do you debug and reason about agent behavior?”
- “How do you migrate local pipelines to serverless without breaking correctness?”

The answer is:
**contracts, separation of concerns, idempotency, and infra-enforced guardrails.**

------------------------------------------------------------

## Three-Plane Architecture (Non-Negotiable Invariant)

CAF separates responsibilities into three planes:

### 1) Planner Plane (Clawdbot / OpenClaw)
- LLM-driven (nondeterministic) but constrained.
- Produces versioned, validated `job.json` contracts.
- Writes **ONLY**:
  - `sandbox/jobs/*.job.json`
- No side effects.
- No output/log/asset writes.

Planned (ADR-0034):
- Introduce a planner-only intermediate artifact (EpisodePlan v1) that is schema-validated and committed before job.json.
- EpisodePlan MUST remain planner-only and must not be required by Control Plane or Worker.

### 2) Control Plane (Ralph Loop)
- Deterministic reconciler / state machine.
- Enforces retries, idempotency, and audit logging.
- Writes **ONLY**:
  - `sandbox/logs/<job_id>/**`
- Must NOT mutate `job.json`.
- Must NOT write worker outputs.

### 3) Worker Plane (Renderer / FFmpeg)
- Deterministic rendering/execution.
- No LLM usage.
- Idempotent and retry-safe.
- Writes **ONLY**:
  - `sandbox/output/<job_id>/**`
- Must NOT call external APIs.

Clarification (ADR-0040/ADR-0042):
- CAF uses **3-plane orchestration with a multi-stage deterministic Worker production pipeline**.
- Worker staging artifacts (e.g., frame/audio/timeline/render manifests) are execution artifacts, not planning authority.
- `job.json` remains the execution authority contract.

Frameworks (LangGraph, CrewAI, etc.), RAG, and auxiliary “agents” must be treated as
**adapters**, not foundations, and must not violate these plane boundaries.
CrewAI (when used) MUST be contained inside the Planner workflow (LangGraph) and must not become a control plane.
Planner-side asset generation (e.g., AI-generated templates or seed frames) is permitted,
but any generated assets must be treated as explicit inputs and must not change Worker determinism.


------------------------------------------------------------

## Filesystem Bus Identity (Job ID Discipline)

CAF uses **files-as-bus** coordination.

- The canonical job identity is the job filename stem:
  `sandbox/jobs/<job_id>.job.json`
- All canonical output/log paths are keyed by that job_id.

This prevents hidden coupling and keeps every run debuggable by inspecting artifacts.

------------------------------------------------------------

## Canonical Output Naming (Worker)

Inside:
- `sandbox/output/<job_id>/`

The Worker MUST emit canonical names:

- `final.mp4` (required)
- `final.srt` (optional)
- `result.json` (required)

Rationale:
- The Worker is deterministic and toolable when downstream consumers can rely on stable names.
- Uniqueness is provided by the **job_id directory**, not the filename.

If a platform-friendly filename is needed, it is created by Ops/Distribution as a derived artifact.

------------------------------------------------------------

## Repo Visibility Posture (PUBLIC by Design)

The CAF core repository is intended to be PUBLIC (portfolio posture).

Non-negotiables:
- No secrets in repo (code, docs, examples, sandbox).
- No credentials, OAuth tokens, refresh tokens, cookies, or browser automation.
- Avoid PII and identity-tied cloud resource names in repo text/configs:
  - no real project IDs
  - no bucket names
  - no personal emails
  - no personal identifiers

Credentialed publishing integrations MUST live outside this repo:
- private ops repo
- separate deployment artifact
- or runtime-only injection in cloud environments

------------------------------------------------------------

## Ops/Distribution Layer (Outside the Factory)

Publishing and distribution workflows are inherently nondeterministic (external APIs).
They must remain **outside** the core factory invariant.

Ops/Distribution:
- consumes immutable worker outputs
- consumes publish metadata / publish_plan
- enforces human approval gates by default
- emits **derived distribution artifacts** only:
  - `sandbox/dist_artifacts/<job_id>/**`

Hard constraints:
- MUST NOT mutate `job.json`
- MUST NOT modify worker outputs under:
  - `/sandbox/output/<job_id>/final.mp4`
  - `/sandbox/output/<job_id>/final.srt`
  - `/sandbox/output/<job_id>/result.json`

Publishing must be idempotent:
- keyed by `{job_id, platform}`
- state authority:
  - `sandbox/dist_artifacts/<job_id>/<platform>.state.json`

Operational rule:
- Manual posting should always use export bundles, not `/sandbox/output/` directly.

Ops workflow automation (e.g., n8n) is allowed only in this layer:
- n8n is ops UX/integrations only (notifications, approvals, manual publish triggers)
- n8n MUST NOT replace Cloud Tasks for internal execution retries/backoff

------------------------------------------------------------

## Daily Output Strategy (Policy; Not an Invariant)

CAF is designed for a sustainable “daily output” workflow under strict budgets.

This is achieved via multiple production lanes (policy), while preserving:
- deterministic Worker behavior
- 3-plane separation

Lane policy stance:
- Lanes are planning/cost/routing hints, not creativity gates.
- `job.lane` may be omitted.
- Schema must remain permissive.
- Runtime recipes decide what inputs are required.

Quality-oriented extensions (ADR-0041/ADR-0042/ADR-0044):
- Video Analyzer artifacts are planner-only metadata canon (no Worker runtime authority).
- Dance Swap v1 is a deterministic choreography-preserving recast lane.
- External recast tools (Viggle-class) are explicit Ops/Distribution HITL steps, never internal Worker engines.

Creativity controls:
- `job.creativity` is an OPTIONAL planner-only input that influences tone/canon strictness.
- It MUST NOT change Worker behavior and MUST NOT introduce schema gating.
- Recommended values:
  - `creativity.mode`: canon | balanced | experimental
  - `creativity.canon_fidelity`: high | medium (optional)

------------------------------------------------------------

## Series Continuity (Planner-Only, Deterministic Canon)

CAF aims for:
- higher quality comedy
- consistent character voices
- ongoing storyline continuity

…but without introducing autonomy creep or a “memory engine”.

The solution is a minimal, deterministic **series layer** above `job.json`.

Planner may read **canon artifacts** (file-based, reviewable, reproducible):
- `repo/shared/hero_registry.v1.json`
- `repo/shared/series_bible.v1.json`
- `repo/shared/episode_ledger.v1.json`

Key principle:
- The LLM may propose new facts, jokes, characters, or continuity hooks,
  but **only committed artifacts become canon**.

This keeps continuity stable and prevents silent drift.

------------------------------------------------------------

## Audio Strategy (License-Safe, Deterministic Workflow)

Audio is both a quality lever and a major copyright risk.

CAF’s audio posture:
- No music generation (v1).
- No trending-music scraping.
- Audio plans exist as artifacts for manual posting workflows.

Worker-level requirement:
- `final.mp4` must always contain an audio stream (no silent MP4).

Continuity-safe audio workflow:
- a repo-owned allowlist of license-safe audio beds
- a deterministic manifest for selection
- planner may select only from the allowlist

This enables higher quality without copyright risk or nondeterministic scraping.

------------------------------------------------------------

## Phase 7 (Mandatory Next Milestone): Event-Driven Cloud Runtime on GCP

Phase 7 is the next required milestone.

Goal:
- migrate from local docker-compose execution to a serverless, event-driven GCP architecture
- preserve determinism, lane separation, and the file-bus mental model
- keep Ops/Distribution outside the factory
- produce a signed URL for manual posting workflows

Phase 7 is NOT a redesign.
It is a **mapping of the same contracts and invariants** onto cloud primitives.
Phase 7 is staged: early PRs define mappings and local stubs; live GCP provisioning
(e.g., Terraform + real deployments) is deferred to a dedicated infra PR.

### Phase 7 Cloud Principles (Binding for the milestone)

1) Telegram webhook receiver MUST NOT block
- Telegram has timeouts; the receiver must ACK quickly.
- The receiver is an ingress adapter, not an execution engine.

2) Async bridge between receiver and planner is mandatory
- Cloud Tasks is the preferred mechanism:
  - retry-safe
  - durable
  - explicit backoff
  - clean auditability

3) Planner becomes a hosted workflow (LangGraph on Cloud Run)
Planner steps (conceptual):
- Analyze Brief (LLM)
- Draft Contract (LLM)
- Validate Schema (deterministic)
- Persist Job Contract state (deterministic)
- (optional sub-step) CrewAI inside a single LangGraph node (LLM; planner-only)
  - used to improve creative quality + continuity editing
  - MUST NOT write artifacts directly; commit happens in deterministic nodes

Note:
- CrewAI is a planner-only implementation detail (contained); it must not replace Ralph Loop or the Worker.

Planner remains the only nondeterministic component.

4) Job contract state MUST be durable (Firestore preferred)
Firestore becomes the durable state store for:
- job contract snapshots
- planner attempts
- job lifecycle state

5) Worker remains deterministic and stateless (Cloud Run FFmpeg)
- Worker pulls its recipe from the persisted job contract state.
- Worker does not call any LLM or external model APIs.
- Worker writes immutable outputs only.

6) Artifacts stored in GCS
- Assets and outputs live in GCS.
- The local file-bus maps to GCS prefixes.
- Deterministic naming remains job_id keyed.

7) Signed URL is the “handoff artifact”
- Phase 7 must produce a signed URL for `final.mp4`
- This is for manual posting and Ops/Distribution workflows.
- Signed URLs do NOT imply automated posting.

8) CI/CD is mandatory
- GitHub main merges trigger Cloud Build:
  build → Artifact Registry → deploy Cloud Run services

### What must remain true in Phase 7

- Planner / Control Plane / Worker boundaries do not change.
- Worker remains deterministic and LLM-free.
- Lanes remain hints, not schema gates.
- Ops/Distribution remains outside the factory.
- No secrets in repo; no identity-tied resource names in repo.

------------------------------------------------------------

## Failure & Safety Model

CAF follows a strict failure philosophy:
- Fail fast.
- Fail loud.
- Never partially mutate state.
- Never introduce hidden side effects.

These guarantees are enforced by:
- container boundaries
- filesystem or object-store write restrictions
- deterministic contracts
- idempotent state models
- durable queues (Cloud Tasks)

Not by prompts.

------------------------------------------------------------

## What CAF Must Never Become (Explicit Anti-Goals)

CAF must NOT become:
- a “self-running autonomous agent” with hidden actions
- a system with agent-to-agent RPC coupling across planes
- a worker that calls LLMs or network APIs
- a repo that contains credentials or identity-tied cloud resources
- a platform automation bot (engagement scraping, like/follow automation)

CAF is a deterministic factory with clear contracts and safe boundaries.
