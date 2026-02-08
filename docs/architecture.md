# Cat AI Factory — Architecture (Diagram-First)

Cat AI Factory is a headless, deterministic, file-contract agent system for generating short-form videos.
It is designed to demonstrate production-grade agent operationalization: clear contracts, strict boundaries, and infra-enforced guardrails.

This page is explanatory. Binding architectural changes must be recorded in `docs/decisions.md`.

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

- Ops/Distribution is outside the factory:
  - External, nondeterministic workflows (approval, notifications, publishing)
  - Must not mutate worker outputs
  - Must emit derived distribution artifacts only

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

  %% Local derived artifacts (binding)
  subgraph LOCAL_DIST[Local Derived Dist Artifacts (binding)]
    INBOX[/sandbox/inbox/*.json\n(ingress + approvals)/]
    DISTROOT[/sandbox/dist_artifacts/<job_id>/]
    PAYLOAD[/sandbox/dist_artifacts/<job_id>/<platform>.json/]
    STATE[/sandbox/dist_artifacts/<job_id>/<platform>.state.json/]
  end

  %% Cloud mapping (later)
  subgraph CLOUD[Cloud Mapping (later)]
    GCS[(GCS\nimmutable artifacts)]
    FS[(Firestore\njobs/{job_id}\n+ publishes/{platform})]
    PS[(Pub/Sub\njob.completed, job.failed)]
  end

  %% Core → local dist layer
  OUTDIR -->|read-only| DISTROOT
  LOGS -->|read-only| DISTROOT
  INBOX -->|approval signals| DISTROOT

  %% Local dist layer semantics
  DISTROOT --> PAYLOAD
  DISTROOT --> STATE

  %% Cloud mapping (optional later)
  OUTDIR -->|sync/upload| GCS
  LOGS -->|sync/upload| GCS

  %% Ops/Distribution layer (outside factory)
  subgraph OPS[Ops/Distribution (Outside the Factory)]
    N8N[n8n / cron / scripts\n(triggers + notify + approval)]
    APPROVE[Human Approval Gate\n(Telegram/Slack/Email)]
    RUNNER[Local Distribution Runner\n(polls artifacts; deterministic)]
    PUBLISH[Publisher Adapters\n(bundle-first; platform-specific)]
  end

  %% Local orchestration path (no always-on service required)
  INBOX --> APPROVE
  APPROVE -->|approved| RUNNER
  RUNNER -->|invokes| PUBLISH

  %% Publisher outputs
  OUTDIR -->|read-only| PUBLISH
  PUBLISH -->|writes derived artifacts only| PAYLOAD
  PUBLISH -->|writes idempotency state| STATE

  %% Guardrails (explicit)
  RUNNER -. MUST NOT edit .-> OUTDIR
  PUBLISH -. MUST NOT edit .-> OUTDIR
  RUNNER -. MUST NOT edit .-> JOB
  PUBLISH -. MUST NOT edit .-> JOB

Notes:
- Ops/Distribution is required before cloud migration: it provides real end-to-end workflows while preserving factory determinism.
- Publisher adapters are bundle-first by default:
  - they produce export bundles + checklists + copy artifacts
  - upload automation is optional per platform (YouTube first)
- Idempotency authority for publishing is:
  - `/sandbox/dist_artifacts/<job_id>/<platform>.state.json`
  - keyed by `{job_id, platform}`

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
| Ingress (optional) | Telegram bridge | repo/tools/telegram_bridge.py | /sandbox/inbox/ | Instruction artifacts | Ingress only; no execution authority. Reads /sandbox/logs/<job_id>/state.json and /sandbox/dist_artifacts/<job_id>/<platform>.state.json for status checks. |
| Ops/Distribution | Publisher adapters | repo/tools/publish_*.py | /sandbox/dist_artifacts/<job_id>/ | Derived artifacts only | Bundle-first; upload automation optional and opt-in |
| Ops/Distribution | Local dist runner | repo/tools/dist_runner.py | /sandbox/dist_artifacts/<job_id>/ | CLI tool | Deterministic poller that invokes publisher adapters based on approval artifacts |
| Contracts | Job schema | repo/shared/job.schema.json | N/A | JSON Schema | Central contract definition for job.json |

------------------------------------------------------------

## References

- Invariants & rationale: docs/master.md
- Binding decisions (ADRs): docs/decisions.md
- Agent roles & permissions: AGENTS.md
- Chat governance: docs/chat-bootstrap.md
- Historical context: docs/memory.md
- Video creation direction: docs/video-creation.md
