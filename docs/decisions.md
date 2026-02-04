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

