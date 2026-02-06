# Cat AI Factory — System Requirements (Human-Readable)

This document summarizes **what the system must do** (requirements) and **what it must never do**
(non-goals / guardrails). It is reviewer-facing and intended to stay short.

Authority:
- Binding invariants and rationale: `docs/master.md`
- Binding decisions (ADRs): `docs/decisions.md`
- Diagram-first architecture: `docs/architecture.md`
- PR sequencing / scope: `docs/PR_PROJECT_PLAN.md`

------------------------------------------------------------

## 1) System Summary

Cat AI Factory is a **headless, file-contract, deterministic** pipeline for generating short-form videos.

Core invariant:
Planner (Clawdbot) → Control Plane (Ralph Loop) → Worker (FFmpeg)

- Planner is the only nondeterministic component (LLM-driven).
- Control Plane + Worker must remain deterministic and retry-safe.
- Files are the bus: no shared memory, no agent-to-agent RPC.

------------------------------------------------------------

## 2) Functional Requirements (FR)

### FR-01 — Contract-first planning
- Planner MUST output a versioned, validated job contract (`job.json`) under `/sandbox/jobs/`.
- Planner MUST NOT write any other artifacts (no outputs, logs, assets).

### FR-02 — Deterministic orchestration
- Ralph Loop MUST reconcile a single job deterministically.
- Ralph Loop MUST write only state/log artifacts under `/sandbox/logs/<job_id>/**`.
- Ralph Loop MUST NOT mutate `job.json`.
- Ralph Loop MUST support retries without changing outputs.

### FR-03 — Deterministic rendering
- Worker MUST render deterministically from `job.json` + `/sandbox/assets/**`.
- Worker MUST write outputs only under `/sandbox/output/<job_id>/**`:
  - `final.mp4`, `final.srt`, `result.json`
- Worker MUST NOT call any LLMs or image-generation APIs.

### FR-04 — Artifact lineage verification
- The system MUST support deterministic verification that required artifacts exist and are consistent:
  - job → outputs → logs/state (lineage)
- Determinism checking across environments is OPTIONAL (strict-mode / harness-only).

### FR-05 — Planner autonomy target
- The long-term target is **fully autonomous planning** (no human-in-loop planner).
- Human approval gates may exist for nondeterministic external actions (e.g., publishing), not for core planning.

### FR-06 — LLM provider strategy (phased)
- LOCAL (PR5): Planner calls Gemini via **Google AI Studio API key**.
  - API key injected at runtime; never committed.
  - No OAuth required for PR5 model calls.
- CLOUD (later): The final portfolio state MUST include **Vertex AI** as a first-class provider option.

### FR-07 — Seed image generation capability (phased)
- Planner SHOULD be able to generate or request seed images for the pipeline.
- In PR5: this may be a stub/interface (or AI Studio implementation), but MUST remain outside the Worker.
- In cloud phase: Vertex AI image generation may be added as a provider option.
- Any image generation is nondeterministic and MUST NOT be implemented inside the Worker.

### FR-08 — Remote instruction + status viewing (adapter)
- A mobile/remote adapter (Telegram recommended) MAY be added later.
- Telegram adapter MUST:
  - write requests/instructions into `/sandbox/inbox/`
  - read status from `/sandbox/logs/<job_id>/state.json`
  - NOT bypass the file-bus
  - NOT mutate outputs

### FR-09 — Ops/Distribution (outside factory)
- Ops/Distribution automation (e.g., n8n, publishing adapters) MUST remain outside core planes.
- It may consume events/artifacts and write derived dist artifacts, but MUST NOT modify worker outputs.

------------------------------------------------------------

## 3) Non-Functional Requirements (NFR)

### NFR-01 — Reproducibility and debuggability
- Runs MUST be debuggable via artifacts and logs on disk.
- State transitions MUST be auditable.

### NFR-02 — Idempotency and retry-safety
- Control Plane retries MUST NOT introduce duplicate side effects.
- Worker reruns MUST be safe and overwrite outputs atomically (as designed in v0.1).

### NFR-03 — Portability
- Local execution MUST work on a personal Mac via Docker sandboxing.
- Avoid OS-specific locking dependencies (prefer atomic mkdir locks).

------------------------------------------------------------

## 4) Security Requirements (SEC)

### SEC-01 — Secrets handling
- Secrets (API keys/tokens) MUST be runtime-injected only:
  - LOCAL: `.env` / secret mount
  - CLOUD: Secret Manager
- Secrets MUST NOT be committed to Git.
- Secrets MUST NOT be written to artifacts:
  - `job.json`, `state.json`, `events.ndjson`, outputs, or logs
- Logs MUST redact any secret-derived values.

### SEC-02 — Network exposure
- Any local gateway MUST bind loopback-only and require token auth (defense in depth).

### SEC-03 — Least privilege (cloud)
- Cloud IAM MUST be least-privilege for Vertex + storage + events.
- Cloud integration must not break local-only workflows.

------------------------------------------------------------

## 5) Budget Guardrails (BUDGET)

Budget guardrails are required to prevent runaway autonomous costs.

### BUDGET-01 — Budget model
- The system MUST support:
  - per-job cost estimate (planner-provided or adapter-provided)
  - per-day and/or per-month caps
  - hard-stop behavior when budget is exceeded

### BUDGET-02 — Enforcement point
- Budget enforcement MUST occur before spending (control plane or planner adapter gate).
- Worker MUST remain cost-neutral (no LLM calls, no external paid APIs).

### BUDGET-03 — Accounting + idempotency
- Budget usage tracking MUST be idempotent (no double counting on retries).
- Accounting keys SHOULD include `{job_id, provider, model, attempt}` or equivalent.

(Implementation may be local-first, then integrated with Cloud Billing budgets later.)

------------------------------------------------------------

## 6) Explicit Non-Goals

- No agent-to-agent RPC or shared memory coordination.
- No LLM usage in the Worker.
- No nondeterministic rendering.
- No autonomous financial transactions.
- No secrets in Git; no secrets printed in logs.
- No schema changes unless explicitly required (ADR required if semantics change).

