# Agent Operating Guide

This document defines the responsibilities, permissions, and boundaries of each agent in the Cat AI Factory system.

---

## Core Rule

> **Agents communicate ONLY via deterministic file contracts files.**  

There is:
- no implicit state
- no UI-driven coordination
- no direct agent-to-agent RPC

This mirrors production ML systems where planning, execution, and rendering
are deliberately separated.

---

## Agents

### 🦞 Clawdbot — Planner Agent

**Role**
- Translates high-level intent (PRD, inbox messages) into structured work
- Produces `job.json` files

**Inputs**
- `/sandbox/PRD.json`
- `/sandbox/inbox/*.json` (optional)

**Outputs**
- `/sandbox/jobs/*.job.json`

**Allowed Actions**
- Read-only access to repo source code
- Write job files to `/sandbox/jobs`

**Disallowed**
- Network calls beyond configured LLM APIs
- File writes outside `/sandbox`
- Financial or account-level actions

---

### 🧠 Ralph Loop — Orchestrator Agent

**Role**
- Interprets job contracts
- Coordinates execution via a control-loop over job contracts
- (Future) approval gates & retries

**Inputs**
- `/sandbox/jobs/*.job.json`

**Outputs**
- Execution decisions
- Status summaries (future)

**Note**
Ralph Loop implements a control-plane pattern: it reconciles desired state
(job contracts) with execution steps, rather than directly performing work.


---

### 🛠 Worker — Renderer

**Role**
- Executes deterministic transforms
- Renders final video artifacts

**Inputs**
- `/sandbox/jobs/*.job.json`
- `/sandbox/assets/*`

**Outputs**
- `/sandbox/output/*.mp4`
- `/sandbox/output/*.srt`

**Characteristics**
- No LLM access
- Fully deterministic
- Idempotent
- CPU-bound execution

---

### 📬 Telegram Bridge — Message Ingress

**Role**
- Receives external text instructions
- Converts them into file-based tasks

**Inputs**
- Telegram messages

**Outputs**
- `/sandbox/inbox/*.json`

**Security**
- No write access outside `/sandbox`
- No direct agent invocation

---

## Safety & Guardrails

- All write access confined to `/sandbox`
- No agent can modify source code at runtime
- No autonomous purchasing or payments
- Explicit human confirmation required for sensitive actions

---

## Failure Philosophy

- Fail fast
- Fail loud
- Never partially mutate state

If a required asset is missing, the pipeline exits without side effects.

---

## Design Rationale

This agent model mirrors production ML systems where:
- planning ≠ execution
- LLMs are advisory, not authoritative
- infra enforces boundaries, not prompts

---

## Future Extensions

- Approval workflow agent
- Cost-aware scheduling
- Multi-niche routing
- Cloud-native agent execution
