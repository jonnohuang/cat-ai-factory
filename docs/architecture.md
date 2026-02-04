# Cat AI Factory — Architecture (Diagram-First)

Cat AI Factory is a **headless, deterministic, file-contract** agent system for generating short-form videos.
It is designed to demonstrate production-grade agent operationalization: clear contracts, strict boundaries, and infra-enforced guardrails.

This page is explanatory. Binding architectural changes must be recorded in `docs/decisions.md`.

------------------------------------------------------------

## Architecture Invariants

- **Three-plane separation (non-negotiable):**
  - Planner → produces `job.json` only (no side effects)
  - Control Plane → deterministic orchestrator (reconciler/state machine)
  - Worker → deterministic renderer (no LLM usage)

- **Files are the bus:**
  - No shared memory
  - No agent-to-agent RPC
  - Coordination happens through explicit artifacts on disk

- **Frameworks are adapters, not foundations:**
  - Orchestration frameworks (e.g., LangGraph) may wrap planner logic, but must not change plane responsibilities.

- **RAG is planner-only.**

- **Verification agents are deterministic QC only:**
  - Read-only evaluation of contracts and outputs
  - May emit logs/results, but do not modify artifacts

- **Safety / social agents are advisory only:**
  - Cannot modify artifacts or bypass orchestration authority

------------------------------------------------------------

## Diagram 1 — Planes & Authority Boundaries

flowchart TB
  subgraph P[Planner Plane — Clawdbot (LLM; constrained)]
    PRD[/sandbox/PRD.json/]
    INBOX[/sandbox/inbox/*.json (optional)/]
    RAG[(RAG Provider)\nplanner-only]
    ADAPT[Framework Adapter\n(e.g., LangGraph)\noptional]
    PLAN[Planner\n(no side effects)]
    JOB[/sandbox/jobs/*.job.json\n(versioned + validated)/]

    PRD --> PLAN
    INBOX --> PLAN
    RAG --> PLAN
    ADAPT --> PLAN
    PLAN --> JOB
  end

  subgraph C[Control Plane — Ralph Loop (deterministic reconciler)]
    ORCH[Ralph Loop\nstate machine + retries\n+ audit logging]
  end

  subgraph W[Worker Plane — Renderer (deterministic; no LLM)]
    WORK[FFmpeg Worker\n(idempotent execution)]
    ASSETS[/sandbox/assets/*/]
    OUTMP4[/sandbox/output/<job-id>/final.mp4/]
    OUTSRT[/sandbox/output/<job-id>/final.srt/]
    LOGS[/sandbox/logs/*/]

    ASSETS --> WORK
    WORK --> OUTMP4
    WORK --> OUTSRT
    WORK --> LOGS


  JOB --> ORCH
  ORCH --> WORK

  subgraph Q[Verification / QC (deterministic; read-only)]
    VERIFY[Verifier\n(schema + hashes + output conformance)]
  end

  JOB --> VERIFY
  OUTMP4 --> VERIFY
  OUTSRT --> VERIFY
  VERIFY --> LOGS

  subgraph S[Safety / Social (advisory-only; no writes)]
    SAFETY[Safety Advisor]
    SOCIAL[Social/Post Advisor]
  end

  ORCH --> SAFETY
  ORCH --> SOCIAL


## Diagram 2 — Artifact Lineage & Filesystem Bus

flowchart LR
  PRD[/sandbox/PRD.json/]
  INBOX[/sandbox/inbox/<msg>.json (optional)/]
  JOBS[/sandbox/jobs/<job-id>.job.json/]

  subgraph RUN[Run artifacts (per job-id)]
    LOGS[/sandbox/logs/<job-id>.* /]
    OUTDIR[/sandbox/output/<job-id>/]
    MP4[final.mp4]
    SRT[final.srt]
    META[result.json\n(checksums, versions, timings)]
  end

  PRD -->|planner reads| JOBS
  INBOX -->|planner reads| JOBS

  JOBS -->|orchestrator reconciles| LOGS
  JOBS -->|orchestrator triggers| OUTDIR

  OUTDIR --> MP4
  OUTDIR --> SRT
  OUTDIR --> META
  LOGS --> META

  JOBS -. same inputs .-> MP4
  JOBS -. same inputs .-> SRT

## Repo → Architecture Mapping

Plane              | Component                         | Repo path                          | Runtime writable paths                           | Contract / Interface               | Notes
-------------------|-----------------------------------|------------------------------------|--------------------------------------------------|------------------------------------|-----------------------------------------------
Planner            | Clawdbot container                | repo/docker/clawdbot/              | /sandbox/jobs/                                   | job.json (schema validated)        | Produces contracts only; no artifact writes
Planner            | Planner runtime state (sandboxed) | (runtime)                          | /sandbox/home/clawd/                             | N/A                                | Internal persona/state; not pipeline output
Control Plane      | Orchestrator service              | repo/services/orchestrator/        | /sandbox/logs/                                   | Reads job.json; observes outputs   | Deterministic reconciler / state machine
Control Plane      | Ralph container                   | repo/docker/ralph/                 | /sandbox/logs/                                   | N/A                                | Packaging/runtime wrapper for orchestrator
Worker             | Worker code                       | repo/worker/render_ffmpeg.py       | /sandbox/output/, /sandbox/logs/                 | Consumes job.json + assets         | Deterministic, idempotent, CPU-bound; no LLM
Worker             | Input assets                      | (runtime)                          | /sandbox/assets/                                 | N/A                                | Worker reads assets from sandbox only
Ingress (optional) | Telegram bridge                   | repo/tools/telegram_bridge.py      | /sandbox/inbox/                                  | Instruction artifacts              | Ingress only; no execution authority
Contracts          | Job schema                        | repo/shared/job.schema.json        | N/A                                              | JSON Schema                        | Central contract definition for job.json


## References
- Invariants & rationale: docs/master.md
- Binding decisions (ADRs): docs/decisions.md
- Agent roles & permissions: AGENTS.md
- Chat governance: docs/chat-bootstrap.md
- Historical context: docs/memory.md
