# GUARDRAILS — Cat AI Factory (Prompt Brief)

This is a **non-authoritative** guardrail brief for onboarding and prompting.
Authoritative sources: `docs/master.md`, `docs/decisions.md`, `AGENTS.md`.

------------------------------------------------------------

## Hard invariants (do not violate)

### Three-plane separation
- Planner produces contracts only.
- Control Plane orchestrates deterministically.
- Worker executes deterministically (no LLM usage).

### Files are the bus
- No shared memory.
- No agent-to-agent RPC.
- Coordination happens through explicit artifacts on disk.

------------------------------------------------------------

## Strict prohibitions

### Planner (Clawdbot)
- **No side effects.**
- **No artifact writes** except `job.json` contracts in `/sandbox/jobs/`.
- Must not modify outputs, logs, or assets.

### RAG
- **Planner-only.**
- RAG must not move into orchestrator or worker.

### Worker
- **No LLM usage.**
- Deterministic and idempotent rendering only.

### Verification / QC agents
- **Deterministic, read-only evaluation only.**
- May emit logs/results, but must not modify existing artifacts (jobs/assets/outputs).

### Safety / social agents
- **Advisory only.**
- Cannot modify artifacts.
- Cannot bypass orchestrator authority.

------------------------------------------------------------

## Security constraints (non-negotiable)

- Containers write only to `/sandbox`.
- Repo/source mounted read-only.
- Loopback-only gateway + token auth.
- No secrets committed (use `.env`, not Git).

