# Cat AI Factory — Design Memory

This document captures durable architectural, security, and infrastructure
decisions for the Cat AI Factory project.

It is intentionally concise and updated only when decisions materially change.
This file exists to preserve design intent across chats, contributors, and time.

------------------------------------------------------------

## Architecture

- The system is **headless-first** and operates without any required UI.
- All agent coordination is **file-based and deterministic**.
- Agents communicate only via explicit artifacts (e.g. `PRD.json`, `job.json`).
- No shared memory, no implicit state, no agent-to-agent RPC.

### Agent Separation of Concerns

- **Clawdbot (Planner Agent)**
  - Translates intent into structured job contracts.
  - Advisory only (LLM-powered).
  - No execution authority.

- **Ralph Loop (Orchestrator Agent)**
  - Control-plane reconciler.
  - Interprets job contracts and coordinates execution steps.
  - Does not perform work directly.

- **Worker (Renderer)**
  - Deterministic, CPU-bound execution (FFmpeg).
  - Idempotent and retry-safe.
  - No LLM access.

- **Telegram Bridge (optional ingress)**
  - External instructions converted into file-based inputs.
  - No direct agent invocation.

------------------------------------------------------------

## Security Model

- Development occurs on a personal macOS machine using Docker sandboxing.
- No additional macOS users are created.
- Containers can write **only** to `/sandbox`.
- Source code is mounted read-only.
- No access to host `$HOME`, browser data, or credentials.

### Gateway Hardening

- Agent gateway bound to loopback only (`127.0.0.1`).
- Token-based authentication required.
- Gateway verified to be unreachable from LAN or internet.

### Secrets

- Secrets stored in `.env` locally.
- `.env` excluded from Git.
- `.env.example` committed.
- Future cloud secrets managed via GCP Secret Manager.

------------------------------------------------------------

## Infrastructure (Target: GCP)

- Orchestration: Cloud Run (Ralph Loop).
- Eventing: Pub/Sub.
- Artifacts: Google Cloud Storage.
- State tracking: Firestore.
- Secrets: Secret Manager.
- IAM: least-privilege service accounts.

Rendering is intentionally decoupled from orchestration due to CPU cost and
determinism requirements.

------------------------------------------------------------

## Naming & Semantics

- Orchestrator is named **Ralph Loop** to signal a control-loop / reconciler role.
- Meme or anthropomorphic naming is intentionally avoided.
- Public naming favors behavior and responsibility over personality.

------------------------------------------------------------

## Non-Goals

- Autonomous financial transactions.
- UI-first workflows.
- Implicit or hidden agent state.
- Prompt-enforced safety without infrastructure backing.

------------------------------------------------------------

## Open Questions

- Best long-term rendering target:
  - Cloud Run Jobs vs GCE VM vs hybrid local worker.
- CI/CD choice:
  - GitHub Actions vs Cloud Build.
- External ingress authentication model for chat-based control.
- Cost controls and scaling limits for daily generation.

## 2026-02-03 — Job Contract v1 + validation tooling

- Added explicit Job Contract v1 versioning: `schema_version: "v1"` and required `job_id`.
- Added `repo/tools/validate_job.py`:
  - Uses full JSON Schema validation when `jsonschema` is available.
  - Falls back to deterministic minimal v1 checks when `jsonschema` is not installed (offline-friendly).
- Updated golden example job(s) under `sandbox/jobs/` to include `schema_version: "v1"`.

## 2026-02-03 — Pre-commit secret scan refinement

- Pre-commit secret scanning now inspects **only added lines** in staged diffs (ignores removed lines).
  - Rationale: avoid false positives when deleting legacy wording (e.g., “token”, “secret”) from non-doc files.
  - Coverage remains focused on preventing *new* sensitive-looking strings from entering the repo outside `docs/` and `.env.example`.

