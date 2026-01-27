# Agent Operating Guide

This document defines the responsibilities, permissions, and operational boundaries
of each agent in the Cat AI Factory system.

The design intentionally mirrors production ML and data platforms, where planning,
orchestration, and execution are strictly separated and enforced by infrastructure,
not prompts.

------------------------------------------------------------

## Core Rule

> **Agents communicate ONLY via deterministic file-based contracts.**

There is:
- no implicit shared state
- no UI-driven coordination
- no direct agent-to-agent RPC

All coordination occurs through explicit artifacts written to disk. This enforces
reproducibility, debuggability, and clear failure modes—core requirements in
production ML systems.

------------------------------------------------------------

## Agents

### 🦞 Clawdbot — Planner Agent

**Purpose**  
Translates high-level intent into structured, machine-readable work contracts.

**Responsibilities**
- Interpret product intent (`PRD.json`) and external instructions
- Generate deterministic `job.json` contracts
- Validate structure and required fields

**Inputs**
- `/sandbox/PRD.json`
- `/sandbox/inbox/*.json` (optional external instructions)

**Outputs**
- `/sandbox/jobs/*.job.json`

**Permissions**
- Read-only access to repository source code
- Write access limited to `/sandbox/jobs`

**Explicitly Disallowed**
- File writes outside `/sandbox`
- Network access beyond configured LLM APIs
- Financial, purchasing, or account-level actions

------------------------------------------------------------

### 🧠 Ralph Loop — Orchestrator Agent

**Purpose**  
Acts as the control plane for execution, reconciling desired state with system actions.

**Responsibilities**
- Interpret `job.json` contracts
- Decide which execution steps should run and in what order
- Enforce sequencing, retries, and (future) approval gates
- Track execution intent without performing work directly

**Inputs**
- `/sandbox/jobs/*.job.json`

**Outputs**
- Execution decisions
- Status summaries and transitions (future)

**Design Note**  
Ralph Loop implements a **control-loop / reconciler pattern**. It compares desired
state (job contracts) with observed state and coordinates execution accordingly,
rather than embedding business logic or performing side effects itself.

------------------------------------------------------------

### 🛠 Worker — Renderer

**Purpose**  
Execute deterministic, CPU-bound transformations to produce final artifacts.

**Responsibilities**
- Render videos and captions from job contracts
- Perform no planning or decision-making

**Inputs**
- `/sandbox/jobs/*.job.json`
- `/sandbox/assets/*`

**Outputs**
- `/sandbox/output/*.mp4`
- `/sandbox/output/*.srt`

**Characteristics**
- No LLM access
- Fully deterministic and idempotent
- CPU-bound execution
- Safe to retry without side effects

------------------------------------------------------------

### 📬 Telegram Bridge — Message Ingress

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

------------------------------------------------------------

## Future Extensions

- Explicit approval workflow agent
- Cost-aware scheduling and throttling
- Multi-niche routing and specialization
- Cloud-native agent execution on GCP
