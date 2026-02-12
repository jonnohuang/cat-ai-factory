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

## Diagram 1 — Planes & Authority Boundaries (Local Canon)

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

### Planner reference inputs (optional; read-only)

The Planner may also read additional **canon/continuity** and **audio selection** reference artifacts.

These are inputs only. The Planner MUST NOT modify them.

- Canon / continuity:
  - `repo/shared/series_bible.v1.json`
  - `repo/shared/episode_ledger.v1.json`

- Audio selection (license-safe manifest):
  - `sandbox/assets/audio/audio_manifest.v1.json`

------------------------------------------------------------

## Diagram 2 — Artifact Lineage & Filesystem Bus (Local Canon)

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

  %% Cloud mapping (Phase 7; mandatory)
  subgraph CLOUD[Cloud Mapping (Phase 7; mandatory)]
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

  %% Cloud mapping (mandatory Phase 7)
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

## Diagram 4 — Phase 7 Cloud Runtime Lifecycle (Sequence Diagram)

Phase 7 migrates the local architecture to GCP while preserving:
- the three-plane invariant
- deterministic Worker behavior
- contract-first job planning
- file-bus semantics (mapped to GCS + Firestore)

Important:
- Telegram webhooks MUST NOT block (Telegram timeouts are short).
- The Receiver is an async ingress that enqueues work to Cloud Tasks.

sequenceDiagram
  participant TG as Telegram
  participant RX as Webhook Receiver (Cloud Run)
  participant TQ as Cloud Tasks Queue
  participant PL as Planner (LangGraph on Cloud Run)
  participant FS as Firestore
  participant RL as Ralph Loop (Cloud Run)
  participant WK as Worker (FFmpeg on Cloud Run)
  participant GCS as GCS (Artifacts)
  participant OPS as Ops/Distribution (outside factory)

  TG->>RX: POST update (webhook)
  RX->>TQ: enqueue task(plan request)
  RX-->>TG: 200 OK (fast)

  TQ->>PL: invoke planner task
  PL->>FS: read PRD + series canon + ledger
  PL->>PL: Analyze Brief (LLM)
  PL->>PL: Draft Job Contract (LLM)
  PL->>PL: Validate Schema (deterministic)
  PL->>FS: write jobs/{job_id} (contract + metadata)
  PL->>GCS: write job.json artifact (optional mirror)

  PL->>TQ: enqueue task(orchestrate job_id)

  TQ->>RL: invoke orchestrator task
  RL->>FS: read jobs/{job_id}
  RL->>RL: reconcile state deterministically
  RL->>TQ: enqueue task(run worker job_id)

  TQ->>WK: invoke worker task
  WK->>FS: read jobs/{job_id} (recipe)
  WK->>GCS: read assets referenced by contract
  WK->>WK: render deterministically (FFmpeg)
  WK->>GCS: write output artifacts (final.mp4, final.srt, result.json)
  WK->>FS: update jobs/{job_id}.status = COMPLETED

  RL->>FS: read completion state
  RL->>FS: write audit logs / state transitions

  OPS->>FS: read jobs/{job_id} status + outputs
  OPS->>GCS: generate signed URL(s) for manual posting
  OPS->>FS: write dist state (publish plan / handoff artifacts)

Notes:
- Cloud Tasks is the deterministic retry boundary between all steps.
- Firestore is the durable state authority for job contracts + orchestration state.
- GCS is the immutable artifact store (cloud mapping of local /sandbox paths).
- Ops/Distribution remains outside the factory, even in cloud.
- “Signed URL generation” is a handoff artifact, not publishing.

------------------------------------------------------------

## Diagram 5 — Phase 7 Cloud Mapping (Local Paths → GCS + Firestore)

Phase 7 preserves the *shape* of the local file-bus by mapping it to:
- Firestore (state + contracts)
- GCS (immutable artifacts)

### Local → Cloud mapping (conceptual)

| Local artifact | Cloud equivalent | Authority |
|---|---|---|
| `sandbox/jobs/<job_id>.job.json` | Firestore `jobs/{job_id}` + optional GCS mirror | Firestore |
| `sandbox/logs/<job_id>/**` | Firestore state history + GCS log blobs | Firestore (state), GCS (raw logs) |
| `sandbox/output/<job_id>/final.mp4` | `gs://<bucket>/output/<job_id>/final.mp4` | GCS |
| `sandbox/output/<job_id>/final.srt` | `gs://<bucket>/output/<job_id>/final.srt` | GCS |
| `sandbox/output/<job_id>/result.json` | `gs://<bucket>/output/<job_id>/result.json` | GCS |
| `sandbox/dist_artifacts/<job_id>/**` | `gs://<bucket>/dist_artifacts/<job_id>/**` + Firestore publish docs | Firestore (state), GCS (bundles) |

### Cloud path conventions (recommended)

- Job contracts:
  - `gs://<bucket>/jobs/<job_id>/job.json` (optional mirror)

- Logs/state:
  - `gs://<bucket>/logs/<job_id>/events.ndjson`
  - `gs://<bucket>/logs/<job_id>/state.json`
  - `gs://<bucket>/logs/<job_id>/attempts/run-000N/**`

- Worker outputs:
  - `gs://<bucket>/output/<job_id>/final.mp4`
  - `gs://<bucket>/output/<job_id>/final.srt`
  - `gs://<bucket>/output/<job_id>/result.json`

- Dist artifacts:
  - `gs://<bucket>/dist_artifacts/<job_id>/bundles/<platform>/v1/**`

Notes:
- GCS objects are treated as immutable artifacts (append-only where possible).
- Firestore is the authority for current job status + contract.
- “files-as-bus” becomes “artifacts-as-bus” with explicit mapping.

------------------------------------------------------------

## Phase 7 Firestore Schema (Proposed; Minimal + Lane-Friendly)

Phase 7 needs a durable state model that supports:
- the three lanes (ai_video, image_motion, template_remix)
- deterministic orchestration
- publish state + signed URL handoff
- idempotent retries

### Collection: `jobs/{job_id}`

Recommended fields:

- `job_id` (string; primary key)
- `job_version` (string; e.g., `job.v1`)
- `lane` (optional string; hint only)
- `status` (string; e.g., PLANNED | RUNNING | COMPLETED | FAILED)
- `created_at` (timestamp)
- `updated_at` (timestamp)

- `job_contract` (object)
  - full JSON of the job contract (schema-valid)
  - stored as canonical contract state

- `artifact_paths` (object)
  - `output_final_mp4` (string; GCS path)
  - `output_final_srt` (string; GCS path; optional)
  - `output_result_json` (string; GCS path)
  - `logs_root` (string; GCS path)

- `attempts` (object)
  - `orchestrator_attempt` (int)
  - `worker_attempt` (int)
  - `last_error` (string; optional)

Notes:
- `job_contract` is the authoritative contract state in cloud.
- The job contract may also be mirrored into GCS for portability.
- Lanes remain non-binding hints; the contract content drives the deterministic recipe.

### Subcollection: `jobs/{job_id}/publishes/{platform}`

Fields:
- `platform` (string; doc id)
- `status` (string; e.g., PENDING | APPROVED | BUNDLED | PUBLISHED | FAILED)
- `approved_at` (timestamp; optional)
- `approved_by` (string; optional)
- `bundle_root` (string; GCS path)
- `signed_urls` (object; optional)
  - `final_mp4_url` (string)
  - `final_srt_url` (string; optional)
  - `bundle_zip_url` (string; optional)
- `platform_post_id` (string; optional)
- `post_url` (string; optional)
- `updated_at` (timestamp)

Notes:
- This is the cloud-native mapping of:
  - `sandbox/dist_artifacts/<job_id>/<platform>.state.json`
- Idempotency remains keyed by `{job_id, platform}`.

------------------------------------------------------------

## Signed URL Handoff (Important Boundary)

In Phase 7, the system MUST produce a **Signed URL** for the final clip
to support manual posting.

Important:
- Generating a signed URL is NOT “publishing”.
- It is a derived Ops/Distribution artifact and must remain outside the core factory.

Recommended:
- Signed URL generation is triggered only after:
  - job status = COMPLETED
  - export bundle exists (or direct final.mp4 is ready)

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

Notes:
- The table above describes the local canonical mapping.
- Phase 7 adds a cloud runtime mapping that preserves the same semantics.

------------------------------------------------------------

## References

- Invariants & rationale: docs/master.md
- Binding decisions (ADRs): docs/decisions.md
- Agent roles & permissions: AGENTS.md
- Chat governance: docs/chat-bootstrap.md
- Historical context: docs/memory.md
- Video creation direction: docs/video-creation.md
