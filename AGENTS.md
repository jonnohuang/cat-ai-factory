# Agent Operating Guide

This document defines the responsibilities, permissions, and operational boundaries
of each agent and adapter in the Cat AI Factory system.

The design mirrors production ML/data platforms: planning, orchestration, and execution
are strictly separated and enforced by infrastructure—not prompts.

This doc is explanatory. Binding architectural changes must be recorded in `docs/decisions.md`.

------------------------------------------------------------

## Core Rule

> **All coordination happens ONLY via deterministic file-based artifacts (“files-as-bus”).**

There is:
- no implicit shared state
- no UI-driven coordination
- no agent-to-agent RPC
- no hidden background services required for correctness

All components communicate through explicit artifacts written to disk. This enforces
reproducibility, debuggability, and clean failure modes.

------------------------------------------------------------

## Non-Negotiable Architecture (Three Planes)

- **Planner (Clawdbot)**
  - LLM-driven (nondeterministic) but constrained
  - Produces versioned, validated `job.json` contracts
  - **No side effects, no artifact writes** (except job contracts)

- **Control Plane (Ralph Loop)**
  - Deterministic reconciler/state machine
  - Coordinates execution, retries, audit logging, artifact lineage
  - Writes logs/state only

- **Worker (Renderer)**
  - Deterministic, CPU-bound execution (FFmpeg)
  - No LLM usage
  - Idempotent and retry-safe

Frameworks (LangGraph, etc.), RAG, and auxiliary “agents” must be treated as **adapters**
that preserve these plane boundaries. RAG is **planner-only**.

------------------------------------------------------------

## Canonical Runtime Paths (Write Boundaries)

- **Planner writes only**
  - `sandbox/jobs/*.job.json`

- **Control Plane (Orchestrator) writes only**
  - `sandbox/logs/<job_id>/**`

- **Worker writes only**
  - `sandbox/output/<job_id>/**`

- **Ingress adapters write only**
  - `sandbox/inbox/*.json`

- **Ops/Distribution writes only derived artifacts**
  - `sandbox/dist_artifacts/<job_id>/**`

Hard rule:
- No component may modify `job.json` after it is written.
- No component outside the Worker may modify `sandbox/output/<job_id>/**`.

------------------------------------------------------------

## Components

### 🦞 Clawdbot — Planner Agent (Planner Plane)

**Purpose**  
Translate high-level intent into structured, machine-readable work contracts.

**Responsibilities**
- Interpret product intent (`sandbox/PRD.json`) + inbox instruction artifacts
- Generate schema-valid `job.json` contracts
- Validate contracts before writing (fail-loud)

**Inputs**
- `sandbox/PRD.json`
- `sandbox/inbox/*.json` (optional external instructions)
- Optional planner-only context (e.g., RAG, style manifest read-only)

**Outputs**
- `sandbox/jobs/<job_id>.job.json`

**Permissions**
- Read-only access to repository source code
- Write access limited to `sandbox/jobs/`

**Explicitly Disallowed**
- Writing anywhere outside `sandbox/jobs/`
- Mutating existing assets, outputs, logs, or dist artifacts
- Implementing control-plane logic (no orchestration responsibilities)
- Any worker execution or FFmpeg invocation

------------------------------------------------------------

### 🧠 Ralph Loop — Orchestrator (Control Plane)

**Purpose**  
Act as the deterministic control plane: reconcile desired state with observed state.

**Responsibilities**
- Interpret `job.json` contracts
- Determine which deterministic steps should run (and in what order)
- Enforce retries and idempotency
- Produce audit-friendly state/log artifacts

**Inputs**
- `sandbox/jobs/*.job.json`
- Observed artifacts in:
  - `sandbox/output/<job_id>/**`
  - `sandbox/logs/<job_id>/**`

**Outputs**
- Logs/state only under:
  - `sandbox/logs/<job_id>/**`

**Constraints**
- MUST NOT mutate `job.json`
- MUST NOT write worker outputs
- Deterministic behavior only (no LLM calls)

------------------------------------------------------------

### 🛠 Worker — Renderer (FFmpeg) (Worker Plane / Data Plane)

**Purpose**  
Execute deterministic, CPU-bound transformations to produce final artifacts.

**Responsibilities**
- Render videos/captions deterministically from:
  - `job.json` + `sandbox/assets/**`
- Write stable outputs and run metadata

**Inputs**
- `sandbox/jobs/*.job.json`
- `sandbox/assets/**`

**Outputs**
- `sandbox/output/<job_id>/final.mp4`
- `sandbox/output/<job_id>/final.srt` (if applicable)
- `sandbox/output/<job_id>/result.json`

**Characteristics**
- No LLM access
- Fully deterministic and idempotent
- Safe to retry without side effects

------------------------------------------------------------

### ✅ QC Verifier — Deterministic, Read-Only Evaluator (QC / Verification)

**Purpose**  
Provide deterministic quality control over contracts and produced artifacts.

**Responsibilities**
- Validate `job.json` (schema / required fields)
- Verify artifact lineage and output conformance
- Emit a summary + logs for auditing and human review

**Inputs**
- `sandbox/jobs/*.job.json`
- `sandbox/output/<job_id>/**`
- `sandbox/logs/<job_id>/**`

**Outputs**
- Writes logs/summary only under:
  - `sandbox/logs/<job_id>/qc/**` (or equivalent QC subdir)

**Constraints**
- Deterministic only (no LLM usage)
- Read-only evaluation: MUST NOT modify existing artifacts (jobs/assets/outputs)

------------------------------------------------------------

## Adapters (External Interfaces)

Adapters are *not* authorities. They translate between external systems and the file-bus.

### 📬 Telegram Bridge — Ingress + Status (Adapter)

**Purpose**
- Provide a mobile supervisor surface (human-in-the-loop)
- Write instruction artifacts into the file-bus and read status back

**Responsibilities**
- Write inbox artifacts under `sandbox/inbox/`
- Respond to the authorized user with:
  - command acknowledgment
  - status summaries (read-only)

**Typical Commands (implemented as inbox artifacts)**
- `/plan <prompt>` → `sandbox/inbox/plan-<nonce>.json`
- `/approve <job_id> [platform]` → `sandbox/inbox/approve-<job_id>-<platform>-<nonce>.json`
- `/reject <job_id> [platform] [reason]` → `sandbox/inbox/reject-<job_id>-<platform>-<nonce>.json`
- `/status <job_id> [platform]` → reads:
  - `sandbox/logs/<job_id>/state.json`
  - `sandbox/dist_artifacts/<job_id>/<platform>.state.json` (if present)
- `/help` → prints supported commands

**Security Constraints**
- Authorized sender check required (e.g., `TELEGRAM_ALLOWED_USER_ID`)
- MUST NOT invoke worker or orchestrator directly
- MUST NOT modify outputs or dist artifacts
- MUST NOT overwrite or delete any existing files

------------------------------------------------------------

## Ops/Distribution (Outside the Factory)

Ops/Distribution performs nondeterministic external work (platform posting, approvals, notifications).
It must remain **outside** the core factory invariant (Planner / Control Plane / Worker).

**Responsibilities**
- Consume immutable outputs + plans
- Produce derived artifacts for posting and/or publishing
- Maintain idempotency keyed by `{job_id, platform}`

**Writes**
- Derived artifacts only under:
  - `sandbox/dist_artifacts/<job_id>/**`

**Idempotency Authority (Local)**
- Publish state file:
  - `sandbox/dist_artifacts/<job_id>/<platform>.state.json`
- A terminal state (e.g., POSTED/PUBLISHED) prevents duplicate posting.

**Approval Gate (Local)**
- Approval artifacts arrive via inbox:
  - `sandbox/inbox/approve-<job_id>-<platform>-<nonce>.json`
- Default posture: human approval required before posting/publishing.

**Hard Constraints**
- MUST NOT mutate `job.json`
- MUST NOT modify `sandbox/output/<job_id>/**`
- MUST NOT bypass file-bus semantics
- Credentials/secrets must never be committed to Git or written to artifacts

------------------------------------------------------------

## Safety & Guardrails

- All write access confined to `sandbox/**` (plus repo edits during development PRs)
- No agent can modify source code at runtime
- No autonomous financial transactions
- External side effects must be approval-gated by default and idempotent

These constraints are enforced by container boundaries, filesystem permissions, and process discipline,
not by prompts.

------------------------------------------------------------

## Failure Philosophy

- Fail fast
- Fail loud
- Never partially mutate state

If required inputs are missing or invalid, the system exits immediately without producing
partial or ambiguous artifacts.

