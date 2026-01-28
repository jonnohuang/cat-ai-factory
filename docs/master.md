# Cat AI Factory — Master Design Document (v1)

This document represents the living design brain of the Cat AI Factory project.
It explains *why* the system is structured the way it is and records architectural
tradeoffs and guiding principles.

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
- Artifact-based workflows mirror real ML pipelines (data → model → artifact).
- Failure modes are observable and recoverable.

------------------------------------------------------------

## Control Plane vs Data Plane

The system deliberately separates:

- **Control Plane**
  - Planning
  - Orchestration
  - Approval logic
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

## Future Work

- CI/CD pipeline integration.
- Formal schema validation for job contracts.
- Approval workflow agent.
- Cost-aware scheduling and throttling.
- Multi-niche routing.
