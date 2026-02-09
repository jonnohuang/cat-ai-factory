# GUARDRAILS — Cat AI Factory (Prompt Brief)

This is a **non-authoritative** guardrail brief for onboarding and prompting.

Authoritative sources:
- Invariants & rationale: `docs/master.md`
- Binding decisions (ADRs): `docs/decisions.md`
- Agent permissions: `AGENTS.md`
- Diagrams + repo mapping: `docs/architecture.md`

------------------------------------------------------------

## Hard invariants (do not violate)

### 1) Three-plane separation (absolute)
- Planner produces contracts only.
- Control Plane orchestrates deterministically.
- Worker executes deterministically (no LLM usage).

No plane may “borrow” responsibilities from another plane.

### 2) Files are the bus
- No shared memory.
- No agent-to-agent RPC.
- Coordination happens through explicit artifacts on disk.

### 3) Determinism is enforced by boundaries
- Only the Planner is nondeterministic.
- Control Plane + Worker must be retry-safe and deterministic.

------------------------------------------------------------

## Strict write boundaries (absolute)

### Planner (Clawdbot)
- Allowed writes: `/sandbox/jobs/*.job.json`
- Forbidden writes: everything else

### Control Plane (Ralph Loop)
- Allowed writes: `/sandbox/logs/<job_id>/**`
- Forbidden writes: `/sandbox/jobs/**`, `/sandbox/output/**`, `/sandbox/assets/**`

### Worker (FFmpeg renderer)
- Allowed writes: `/sandbox/output/<job_id>/**`
- Forbidden writes: `/sandbox/jobs/**`, `/sandbox/assets/**`
- (Worker logs may be captured under `/sandbox/logs/<job_id>/**` via redirected stdout/stderr,
  but the Worker itself must not treat logs as a coordination channel.)

### Ops/Distribution (post-factory)
- Allowed writes: `/sandbox/dist_artifacts/<job_id>/**` (derived artifacts only)
- Forbidden writes: `/sandbox/output/<job_id>/**`, `/sandbox/jobs/**`

------------------------------------------------------------

## Strict prohibitions

### Planner autonomy limits
- Planner MUST NOT write outputs, logs, assets, dist artifacts, or state.
- Planner MUST NOT “self-execute” worker actions.
- Planner MUST NOT embed credentials or secrets into contracts.

### RAG (planner-only)
- RAG is planner-only.
- RAG MUST NOT move into the Control Plane or Worker.

### Worker
- Worker MUST NOT call any LLMs or external generation APIs.
- Worker MUST remain deterministic and idempotent.

### Verification / QC
- QC MUST be deterministic and read-only.
- QC MAY emit logs/results, but MUST NOT modify jobs/assets/outputs.
- QC MUST NOT “fix” artifacts.

### Safety / social advisors
- Advisory only.
- Cannot modify artifacts.
- Cannot bypass approval gates or orchestrator authority.

------------------------------------------------------------

## Security constraints (non-negotiable)

- Containers write only to `/sandbox`.
- Repo/source is mounted read-only.
- Loopback-only gateway + token auth (defense-in-depth).
- Secrets must be runtime-injected only:
  - local: `.env` / secret mount
  - cloud: Secret Manager
- No secrets committed to Git.
- No secrets printed in logs (redact aggressively).

------------------------------------------------------------

## PUBLIC REPO: Secrets & Credentials Policy

This repository is PUBLIC by design (portfolio posture).

Non-negotiable:
- NO secrets may ever be committed to this repo.
- NO credential material may ever be stored in tracked files, including docs, examples, logs, or sandbox artifacts.

Examples (non-exhaustive) of prohibited material:
- API keys
- OAuth client secrets
- OAuth refresh tokens
- Session cookies
- Authorization headers / Bearer tokens
- Webhook URLs with embedded secrets
- Service account JSON files
- Private keys (SSH keys, RSA keys, etc.)

.env policy:
- Never commit a real `.env`.
- `.env.example` is allowed and must contain placeholders only.

Logs policy:
- Never log Authorization headers, tokens, cookies, or full request payloads containing secrets.
- If debugging is needed, redact or omit sensitive fields entirely.

Credentialed integrations boundary:
- Any credentialed publishing integrations (OAuth/token flows, account bindings, automated posting requiring credentials)
  MUST live outside this public repo (private ops repo / separate deployment artifact).
- This repo may only implement credential-free, bundle-first publisher adapters by default.

------------------------------------------------------------

## Ops/Distribution (Outside the Factory)

Ops/Distribution is required pre-cloud, but it is still outside the factory.

Hard constraints:
- Ops/Distribution MUST NOT replace Clawdbot (Planner) or Ralph Loop (Control Plane).
- Ops/Distribution MUST NOT mutate `job.json`.
- Ops/Distribution MUST NOT modify worker outputs under:
  - `/sandbox/output/<job_id>/final.mp4`
  - `/sandbox/output/<job_id>/final.srt`
  - `/sandbox/output/<job_id>/result.json`

Platform-specific formatting MUST emit derived dist artifacts only:
- `/sandbox/dist_artifacts/<job_id>/<platform>.json`
- `/sandbox/dist_artifacts/<job_id>/<platform>.state.json`

Publishing must be:
- human-approved by default
- idempotent via `{job_id, platform}` keys

------------------------------------------------------------

## If a task conflicts with these rules

Stop immediately and escalate to ARCH for an ADR decision.

