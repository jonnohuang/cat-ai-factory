# Cat AI Factory — Architecture (Diagram-First)

Cat AI Factory is a headless, deterministic, file-contract agent system for generating short-form videos.
It is designed to demonstrate production-grade agent operationalization: clear contracts, strict boundaries, and infra-enforced guardrails.

This page is explanatory. Binding architectural changes must be recorded in docs/decisions.md.

------------------------------------------------------------

## Architecture Invariants

- Three-plane separation (non-negotiable):
  - Planner → produces job.json only (no side effects)
  - Control Plane → deterministic orchestrator (reconciler/state machine)
  - Worker → deterministic renderer (no LLM usage)

- Files are the bus:
  - No shared memory
  - No agent-to-agent RPC
  - Coordination happens through explicit artifacts on disk

- Frameworks are adapters, not foundations:
  - Orchestration frameworks (e.g., LangGraph) may wrap planner logic, but must not change plane responsibilities.

- RAG is planner-only.

- Verification agents are deterministic QC only:
  - Read-only evaluation of contracts and outputs
  - May emit logs/results, but do not modify artifacts

- Safety / social agents are advisory-only:
  - Cannot modify artifacts or bypass orchestration authority

------------------------------------------------------------

## Diagram 1 — Planes & Authority Boundaries

flowchart TB
  subgraph P[Planner Plane — Clawdbot (LLM; constrained)]
    PRD[/sandbox/PRD.json/]
    INBOX[/sandbox/inbox/*.json (optional)/]
    RAG[(RAG Provider\nplanner-only)]
    ADAPT[Framework Adapter\n(e.g., LangGraph)\noptional]
    PLAN[Planner\n(no side effects)]
    JOB[/sandbox/jobs/<job-file>.job.json\n(versioned + validated)/]

    PRD --> PLAN
    INBOX --> PLAN
    RAG --> PLAN
    ADAPT --> PLAN
    PLAN --> JOB
  end

  subgraph C[Control Plane — Ralph Loop (deterministic reconciler)]
    ORCH[Ralph Loop\nstate machine + retries\n+ audit logging]
    LOGS[/sandbox/logs/<job_id>/**/]
  end

  subgraph W[Worker Plane — Renderer (deterministic; no LLM)]
    ASSETS[/sandbox/assets/**/]
    WORK[FFmpeg Worker\n(idempotent execution)]
    OUTDIR[/sandbox/output/<job_id>/**/]
    OUTMP4[final.mp4]
    OUTSRT[final.srt]
    RESULT[result.json]

    ASSETS --> WORK
    WORK --> OUTDIR
    OUTDIR --> OUTMP4
    OUTDIR --> OUTSRT
    OUTDIR --> RESULT
  end

  JOB --> ORCH
  ORCH -->|invokes| WORK
  ORCH -->|writes logs only| LOGS

  subgraph Q[Verification / QC (deterministic; read-only)]
    VERIFY[Verifier\n(lineage + output conformance)]
  end

  JOB --> VERIFY
  OUTDIR --> VERIFY
  VERIFY -->|writes logs only| LOGS

  subgraph S[Safety / Social (advisory-only; no writes)]
    SAFETY[Safety Advisor]
    SOCIAL[Social/Post Advisor]
  end

  ORCH --> SAFETY
  ORCH --> SOCIAL

Notes:
- Canonical output/log directories are keyed by job_id derived from the job filename stem (<job-file>). This is the filesystem bus identity.
- If job.json also contains job_id and it differs, Ralph Loop emits a warning event and proceeds using the filename-derived job_id.

------------------------------------------------------------

## Diagram 2 — Artifact Lineage & Filesystem Bus

flowchart LR
  PRD[/sandbox/PRD.json/]
  INBOX[/sandbox/inbox/<msg>.json (optional)/]
  JOBFILE[/sandbox/jobs/<job-file>.job.json/]

  subgraph JOB[Job contract]
    JOBID[job_id (derived from job filename stem)\nsource-of-truth for canonical paths]
  end

  subgraph RUN[Per-job artifacts (keyed by job_id)]
    OUTDIR[/sandbox/output/<job_id>/]
    MP4[final.mp4]
    SRT[final.srt]
    RESULT[result.json]
    LOGS[/sandbox/logs/<job_id>/**/]
    STATE[state.json]
    EVENTS[events.ndjson]
    ATTEMPTS[/attempts/run-000N/**/]
  end

  PRD -->|planner reads| JOBFILE
  INBOX -->|planner reads| JOBFILE
  JOBFILE --> JOBID

  JOBFILE -->|orchestrator reads| LOGS
  JOBFILE -->|worker reads| OUTDIR

  OUTDIR --> MP4
  OUTDIR --> SRT
  OUTDIR --> RESULT

  LOGS --> STATE
  LOGS --> EVENTS
  LOGS --> ATTEMPTS

Notes:
- Orchestrator writes ONLY under /sandbox/logs/<job_id>/**.
- Worker writes ONLY under /sandbox/output/<job_id>/** (and may also write worker logs under /sandbox/logs/<job_id>/** if configured by orchestrator via redirected stdout/stderr).
- Orchestrator must not mutate job.json.
- If outputs exist, orchestrator may fast-path by running lineage verification and marking COMPLETED without invoking the worker.

------------------------------------------------------------

## Diagram 3 — Ops/Distribution (Outside the Factory)

Ops/Distribution is outside the core factory (Planner / Control Plane / Worker).
It consumes events + immutable artifacts and performs nondeterministic external work
(approvals, notifications, publishing) without mutating worker outputs.

flowchart TB
  %% Core factory (unchanged)
  subgraph FACTORY[Core Factory (Invariant): Planner / Control / Worker]
    JOB[/sandbox/jobs/<job-file>.job.json/]
    ORCH[Ralph Loop\n(reconciler)]
    OUTDIR[/sandbox/output/<job_id>/**/]
    LOGS[/sandbox/logs/<job_id>/**/]

    JOB --> ORCH
    ORCH --> OUTDIR
    ORCH --> LOGS
  end

  %% Event + status surfaces (cloud mapping)
  subgraph CLOUD[Cloud Surfaces (v0.2+ mapping)]
    GCS[(GCS\nimmutable artifacts)]
    FS[(Firestore\njobs/{job_id}\n+ publishes/{job_id})]
    PS[(Pub/Sub\njob.completed, job.failed)]
  end

  OUTDIR -->|sync/upload| GCS
  LOGS -->|sync/upload| GCS
  ORCH -->|update status| FS
  ORCH -->|emit event| PS

  %% Ops/Distribution (outside factory)
  subgraph OPS[Ops/Distribution (Outside the Factory)]
    N8N[n8n\n(triggers + notify + approval)]
    APPROVE[Human Approval Gate\n(Slack/Discord/Email)]
    PUBLISH[Publisher Adapter\n(Cloud Run)\n(platform API calls)]
    DIST[sandbox/dist_artifacts/<job_id>/<platform>.json\n(dist artifacts; derived only)/]
  end

  PS --> N8N
  FS --> N8N
  N8N --> APPROVE
  APPROVE -->|approved| PUBLISH

  GCS -->|read-only artifacts| PUBLISH
  PUBLISH -->|write dist artifacts| DIST
  PUBLISH -->|store outcomes + idempotency| FS

  %% Guardrails (explicit)
  N8N -. MUST NOT edit .-> OUTDIR
  PUBLISH -. MUST NOT edit .-> OUTDIR

Notes:
- Ops/Distribution may be nondeterministic (external APIs). It must remain outside core planes.
- n8n is not a replacement for Clawdbot or Ralph Loop.
- Platform formatting must produce new dist artifacts under sandbox/dist_artifacts/<job_id>/...; worker outputs are immutable.

------------------------------------------------------------

## Repo → Architecture Mapping

| Plane | Component | Repo path | Runtime writable paths | Contract / Interface | Notes |
|---|---|---|---|---|---|
| Planner | Clawdbot container | repo/docker/clawdbot/ | /sandbox/jobs/ | job.json (schema validated) | Produces contracts only; no artifact writes beyond job.json |
| Planner | Planner runtime state (sandboxed) | (runtime) | /sandbox/home/clawd/ | N/A | Internal persona/state; not treated as pipeline output |
| Control Plane | Orchestrator service (Ralph Loop) | repo/services/orchestrator/ | /sandbox/logs/<job_id>/** | Reads job.json; observes outputs | Deterministic reconciler/state machine; retries + audit logging |
| Control Plane | Ralph container | repo/docker/ralph/ | /sandbox/logs/<job_id>/** | N/A | Packaging/runtime wrapper for orchestrator |
| Worker | Worker code | repo/worker/render_ffmpeg.py | /sandbox/output/<job_id>/** | Consumes job.json + /sandbox/assets/** | Deterministic, idempotent, CPU-bound; no LLM |
| Worker | Input assets | (runtime) | /sandbox/assets/** | N/A | Worker reads assets from sandbox only |
| Verification | Lineage verifier (QC) | repo/tools/lineage_verify.py | (writes logs only when invoked) | CLI tool | Deterministic read-only verification of required artifacts |
| Verification | Job validator (QC) | repo/tools/validate_job.py | (writes logs only when invoked) | CLI tool | Deterministic validation of job.json against schema |
| Verification | QC verifier (QC tool) | repo/tools/qc_verify.py | /sandbox/logs/<job_id>/qc/ | CLI tool | Deterministic, read-only QC summary: composes schema validation + lineage + output conformance |
| Ingress (optional) | Telegram bridge | repo/tools/telegram_bridge.py | /sandbox/inbox/ | Instruction artifacts | Ingress only; no execution authority. Reads /sandbox/logs/<job_id>/state.json for status checks. |
| Contracts | Job schema | repo/shared/job.schema.json | N/A | JSON Schema | Central contract definition for job.json |

------------------------------------------------------------

## References

- Invariants & rationale: docs/master.md
- Binding decisions (ADRs): docs/decisions.md
- Agent roles & permissions: AGENTS.md
- Chat governance: docs/chat-bootstrap.md
- Historical context: docs/memory.md
- Video creation direction: docs/video-creation.md
