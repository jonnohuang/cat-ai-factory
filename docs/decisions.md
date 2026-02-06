# Architecture Decision Records (ADR)

This file logs key architectural decisions for Cat AI Factory.

**Authority & hierarchy**
- `docs/decisions.md` is the binding record of architectural decisions (append-only).
- `docs/master.md` captures invariants and rationale.
- `docs/architecture.md` is diagram-first and explanatory; it must align with ADRs (it does not override them).
- `docs/memory.md` is historical context only.

Format: short, dated ADR entries. Append new ADRs as decisions are made.

Guidelines:
- One decision per ADR
- Include context, decision, consequences
- Link to relevant docs (README.md, AGENTS.md, docs/master.md, docs/memory.md, docs/architecture.md)

# Example on adding new ADR:

cat >> docs/decisions.md <<'EOF'

------------------------------------------------------------

## ADR-000X — <Title>
Date: YYYY-MM-DD
Status: Proposed | Accepted | Deprecated

Context:
Decision:
Consequences:
References:

EOF

=======================================
# ADR Records
=======================================

------------------------------------------------------------

## ADR-0001 — File-based agent coordination (contracts over RPC)
Date: 2026-01-27
Status: Accepted

Context:
- Agent systems become brittle when coordination relies on UI clicks, implicit memory, or agent-to-agent RPC.
- We want reproducibility, debuggability, and clean failure modes aligned with production ML systems.

Decision:
- All agent coordination will happen via deterministic file-based contracts:
  - PRD.json → job.json → rendered artifacts
- No shared memory, no implicit state, no direct agent-to-agent RPC.

Consequences:
- Pros: reproducible runs, easier debugging, clearer auditing.
- Cons: requires explicit schema/versioning discipline and artifact organization.

References:
- docs/master.md
- docs/memory.md
- AGENTS.md

------------------------------------------------------------

## ADR-0002 — Separation of concerns: Planner vs Orchestrator vs Worker
Date: 2026-01-27
Status: Accepted

Context:
- Mixing planning (LLM), orchestration (control loop), and execution (rendering) increases risk and reduces determinism.

Decision:
- Define distinct roles:
  - Clawdbot = Planner Agent (creates job contracts)
  - Ralph Loop = Orchestrator Agent (control-plane reconciler)
  - Worker = Renderer (deterministic FFmpeg execution)

Consequences:
- Pros: strong safety boundaries, easier retries, clearer ownership.
- Cons: more components to wire, requires well-defined interfaces.

References:
- AGENTS.md
- README.md

------------------------------------------------------------

## ADR-0003 — Docker sandbox on personal Mac (no additional macOS users)
Date: 2026-01-27
Status: Accepted

Context:
- The development machine is a personal daily-use Mac.
- Strong isolation is needed without adding friction (no extra macOS user accounts).

Decision:
- Use Docker sandboxing as the primary isolation layer:
  - Mount only ./sandbox into containers (writeable)
  - Mount repo read-only when needed
  - Keep secrets out of Git

Consequences:
- Pros: good isolation, low friction, reproducible dev environment.
- Cons: must be disciplined with mounts and secrets; some UI tools may be awkward.

References:
- docs/memory.md
- README.md

------------------------------------------------------------

## ADR-0004 — Gateway security: loopback bind + token auth
Date: 2026-01-27
Status: Accepted

Context:
- Local agent gateway must not be reachable from LAN/internet.
- Token-based auth reduces risk from local processes.

Decision:
- Enforce:
  - gateway.bind = loopback
  - gateway.auth.mode = token
  - Host port mapping binds to 127.0.0.1 only
- Verified LAN unreachable.

Consequences:
- Pros: prevents accidental exposure; defense-in-depth.
- Cons: makes “UI access from host” trickier in containerized setups.

References:
- docs/memory.md

------------------------------------------------------------

## ADR-0005 — Naming: “Ralph Loop” for orchestrator
Date: 2026-01-27
Status: Accepted

Context:
- Public repo naming should sound professional and convey function.
- Avoid meme/joke naming for recruiter-facing artifacts.

Decision:
- Name the orchestrator “Ralph Loop” (control-loop / reconciler pattern).
- Use “ralph-loop” as a GitHub topic; internal shorthand “ralph” is acceptable.

Consequences:
- Pros: communicates control-plane intent; recruiter-friendly.
- Cons: minor renaming overhead in docs/code.

References:
- README.md
- AGENTS.md

------------------------------------------------------------

## ADR-0006 — Planner LLM provider strategy (AI Studio local-first; Vertex mandatory later)
Date: 2026-02-05
Status: Accepted

Context:
- PR5 needs fast LOCAL autonomy without cloud IAM/OAuth plumbing.
- The final portfolio state must demonstrate production/enterprise readiness using Vertex AI.
- Planner is the only nondeterministic component; Control Plane + Worker must remain deterministic.

Decision:
- PR5 (LOCAL): Clawdbot planning uses Gemini via Google AI Studio API key.
  - Auth via runtime-injected API key (.env / secret mount); never committed.
  - No OAuth required for PR5 model calls.
- Cloud phase (later): Vertex AI is a first-class planner provider option and is mandatory in the final portfolio state.
  - Secrets via Secret Manager; least-privilege IAM.

Consequences:
- Pros: PR5 can move quickly while preserving deterministic boundaries; portfolio includes Vertex AI later.
- Cons: two provider paths must be maintained behind an adapter interface; parity must be tested.

References:
- docs/master.md
- docs/system-requirements.md
- docs/PR_PROJECT_PLAN.md
- docs/architecture.md

------------------------------------------------------------

## ADR-0007 — Seed image generation is a planner-side nondeterministic step (never in Worker)
Date: 2026-02-05
Status: Accepted

Context:
- Seed images are needed for certain content archetypes and future pipeline quality.
- Image generation is nondeterministic and may incur cost and policy constraints.
- The Worker must remain deterministic and must not call LLM or generation APIs.

Decision:
- Seed image generation (or seed image requests) is allowed only as a Planner-side or pre-worker nondeterministic step.
- In PR5 this may exist as a stub/interface or be implemented via AI Studio, but it must NOT be implemented inside the Worker.
- Cloud phase may add Vertex AI image generation as a provider option, still outside the Worker.

Consequences:
- Pros: preserves determinism and retry-safety of the Worker; isolates nondeterminism and cost.
- Cons: requires an explicit boundary and artifact flow for generated assets (handled as inputs, not worker decisions).

References:
- docs/system-requirements.md
- docs/master.md
- docs/architecture.md
- docs/video-creation.md

------------------------------------------------------------

## ADR-0008 — Budget guardrails are required for autonomous operation (hard stop)
Date: 2026-02-05
Status: Accepted

Context:
- Planner autonomy is the target; autonomous operation must not create runaway costs.
- LLM and generation providers are paid external services; retries can multiply spend if not controlled.

Decision:
- The system must support a budget guardrail concept:
  - per-job cost estimate
  - per-day/per-month caps
  - hard-stop behavior when budget is exceeded
- Enforcement must occur before spending (planner adapter and/or control plane gate).
- Budget tracking must be idempotent and retry-safe (no double counting).

Consequences:
- Pros: prevents uncontrolled spend; makes autonomy safe to run continuously.
- Cons: requires accounting model + enforcement surface (implemented in later PRs).

References:
- docs/system-requirements.md
- docs/master.md
- docs/PR_PROJECT_PLAN.md

------------------------------------------------------------

## ADR-0009 — Telegram/mobile adapter is ingress/status-only (adapter; no authority bypass)
Date: 2026-02-05
Status: Accepted

Context:
- Mobile remote instruction and approval is desired for real-world operation.
- Remote channels are inherently untrusted and must not bypass core invariants.

Decision:
- Telegram (or any mobile UI adapter) is an adapter only:
  - writes requests into `/sandbox/inbox/`
  - reads status from `/sandbox/logs/<job_id>/state.json`
  - does not bypass the file-bus
  - does not mutate outputs or job contracts
- Any approval gates remain control-plane enforced and artifact-mediated.

Consequences:
- Pros: safe remote control path; preserves debuggability and auditability through artifacts.
- Cons: requires careful mapping of messages → inbox artifacts and state visibility (implemented in later PRs).

References:
- docs/system-requirements.md
- docs/architecture.md
- repo/tools/telegram_bridge.py
