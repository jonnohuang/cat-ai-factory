# Agent Operating Guide

This document defines the responsibilities, permissions, and operational boundaries
of each agent in the Cat AI Factory system.

The design mirrors production ML and data platforms: planning, orchestration,
and execution are strictly separated and enforced by infrastructure—not prompts.

------------------------------------------------------------

## Core Rule

> **Agents communicate ONLY via deterministic file-based contracts.**

There is:
- no implicit shared state
- no UI-driven coordination
- no direct agent-to-agent RPC

All coordination occurs through explicit artifacts written to disk. This enforces
reproducibility, debuggability, and clear failure modes.

------------------------------------------------------------

## Non-Negotiable Architecture (Three Planes)

- **Planner (Clawdbot)**
  - LLM-driven but constrained
  - Produces versioned, validated `job.json`
  - **No side effects, no artifact writes** (except job contracts)

- **Control Plane (Ralph Loop)**
  - Deterministic reconciler/state machine
  - Coordinates execution, retries, audit logging, artifact lineage

- **Worker (Renderer)**
  - Deterministic, CPU-bound execution (FFmpeg)
  - No LLM usage
  - Idempotent and retry-safe

Frameworks (LangGraph, etc.), RAG, and auxiliary agents must be treated as **adapters**
that preserve these plane boundaries. RAG is **planner-only**.

------------------------------------------------------------

## Agents

### 🦞 Clawdbot — Planner Agent

**Purpose**  
Translate high-level intent into structured, machine-readable work contracts.

**Responsibilities**
- Interpret product intent (`/sandbox/PRD.json`) and external instructions
- Generate versioned `job.json` contracts
- Validate structure and required fields

**Inputs**
- `/sandbox/PRD.json`
- `/sandbox/inbox/*.json` (optional external instructions)
- Optional planner-only context (e.g., RAG)

**Outputs**
- `/sandbox/jobs/*.job.json`

**Permissions**
- Read-only access to repository source code
- Write access limited to `/sandbox/jobs`

**Explicitly Disallowed**
- File writes outside `/sandbox/jobs` (planner produces contracts only)
- Modifying assets, outputs, or logs
- Network access beyond configured LLM/RAG endpoints (if enabled)
- Financial, purchasing, or account-level actions

------------------------------------------------------------

### 🧠 Ralph Loop — Orchestrator Agent (Control Plane)

**Purpose**  
Act as the control plane, reconciling desired state with observed state and coordinating execution.

**Responsibilities**
- Interpret `job.json` contracts
- Decide which deterministic execution steps should run and in what order
- Enforce sequencing, retries, and (future) approval gates
- Produce audit-friendly status/log outputs (as artifacts, not implicit state)

**Inputs**
- `/sandbox/jobs/*.job.json`
- Observed artifacts (e.g., `/sandbox/output/`, `/sandbox/logs/`)

**Outputs**
- Execution decisions
- Status summaries and transitions (as artifacts/logs, as implemented)

**Design Note**  
Ralph Loop implements a **control-loop / reconciler pattern**. It compares desired
state (job contracts) with observed state and coordinates execution accordingly.
It does not embed CPU-bound rendering or LLM planning inside the control plane.

------------------------------------------------------------

### 🛠 Worker — Renderer (Data Plane)

**Purpose**  
Execute deterministic, CPU-bound transformations to produce final artifacts.

**Responsibilities**
- Render videos and captions from job contracts
- Perform no planning or decision-making

**Inputs**
- `/sandbox/jobs/*.job.json`
- `/sandbox/assets/*`

**Outputs**
- `/sandbox/output/*.mp4` (or per-job output directory as defined)
- `/sandbox/output/*.srt`
- `/sandbox/logs/*` (run logs)

**Characteristics**
- No LLM access
- Fully deterministic and idempotent
- CPU-bound execution
- Safe to retry without side effects

------------------------------------------------------------

### ✅ Verification / QC Agent — Deterministic Evaluator (Optional)

**Purpose**  
Provide deterministic, read-only quality control over contracts and outputs.

**Responsibilities**
- Validate `job.json` against schema and required fields
- Verify output conformance (e.g., presence, structure, checksums/tolerances if defined)
- Emit results as logs/summary artifacts

**Inputs**
- `/sandbox/jobs/*.job.json`
- `/sandbox/output/*`
- `/sandbox/logs/*`

**Outputs**
- QC results as logs or summary files under `/sandbox/logs/` (or equivalent)

**Constraints**
- Deterministic only (no LLM usage required)
- **Read-only evaluation:** must not modify existing job/assets/output artifacts

------------------------------------------------------------

### 🛡 Safety / Social Advisors — Advisory Only (Optional)

**Purpose**  
Provide advisory signals (risk flags, posting suggestions) without execution authority.

**Responsibilities**
- Flag risky actions for explicit human review (safety)
- Suggest captions/metadata/posting plans (social)

**Constraints**
- **No artifact mutation authority**
- No bypass of orchestrator approvals
- No direct invocation of worker or side effects

These advisors exist to support safe operation and portfolio demonstration—not to extend autonomy.

------------------------------------------------------------

### 📬 Telegram Bridge — Message Ingress (Optional)

**Purpose**  
Provide a controlled external input channel for human instructions.

**Responsibilities**
- Receive external text messages
- Translate messages into file-based instruction artifacts

**Inputs**
- Telegram messages

**Outputs**
- `/sandbox/inbox/*.json`

**Security Constraints**
- No write access outside `/sandbox`
- No direct agent invocation
- No execution authority

------------------------------------------------------------

## Safety & Guardrails

- All write access confined to `/sandbox`
- No agent can modify source code at runtime
- No autonomous financial transactions
- Explicit human confirmation required for sensitive or destructive actions

These constraints are enforced by container boundaries and filesystem permissions,
not by agent prompts.

------------------------------------------------------------

## Failure Philosophy

- Fail fast
- Fail loud
- Never partially mutate state

If required inputs are missing or invalid, the pipeline exits immediately without
producing side effects or partial artifacts.

------------------------------------------------------------

## Design Rationale

This agent model reflects production ML and data platforms where:
- planning ≠ orchestration ≠ execution
- LLMs are advisory components, not authorities
- infrastructure enforces correctness, safety, and boundaries

The goal is predictability and operability, not autonomous behavior.

