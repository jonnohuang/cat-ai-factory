# Cat AI Factory 🐱🎬
A headless, agent-driven AI content factory for short-form video generation

------------------------------------------------------------

## Overview

Cat AI Factory is a local-first, headless AI agent system that generates short-form vertical videos (Reels / Shorts) through a fully automated, reproducible pipeline.

The project demonstrates:

- Agent orchestration (planning → execution → rendering)
- Secure, sandboxed local development with Docker
- Deterministic file-based workflows (no fragile UIs)
- Production-ready patterns suitable for Cloud Run / GCP migration

The current niche is “cute lifelike cats doing funny activities”, but the architecture is content-agnostic.

------------------------------------------------------------

## Why This Matters (ML Infra / MLOps Portfolio)

This project is designed to showcase practical ML-infrastructure skills beyond model training:

- Event-driven orchestration patterns (Scheduler/queue → stateless compute → artifacts)
- Deterministic, testable contracts (job.json schema) and reproducible outputs
- Separation of concerns: planning (LLM) vs execution (renderer)
- Secure-by-default agent operation (sandboxed writes, loopback-only gateway, token auth)
- Artifact lineage and state tracking (jobs, outputs, status progression)
- Clear migration path to GCP (Cloud Run + Pub/Sub + GCS + Secret Manager + IAM)

In short: it demonstrates how to operationalize an “AI agent workflow” with real infra hygiene,
guardrails, and deployability—similar to production ML systems.

------------------------------------------------------------

## High-Level Architecture

PRD / Instructions  
→ Planner Agent (Clawdbot)  
→ job.json (structured contract)  
→ Worker (FFmpeg Renderer)  
→ MP4 + captions  

Optional ingress:

Telegram Message  
→ Message Bridge  
→ /sandbox/inbox  

All agent interaction happens through files, not shared memory or browser UIs.

------------------------------------------------------------

## Design Principles

- Headless-first: no required UI or dashboard
- Deterministic: outputs reproducible from inputs
- Sandboxed: containers write only to /sandbox
- Secure by default:
  - loopback-only gateway
  - token-based authentication
  - secrets never committed
- Cloud-ready: clean mapping to GCP (Cloud Run + GCS + Secret Manager)

------------------------------------------------------------

## Folder Structure

cat-ai-factory/
├── README.md
├── AGENTS.md
├── docker-compose.yml
├── .env.example
├── .gitignore
│
├── repo/                    (source code, read-only to containers)
│   ├── shared/              (schemas & contracts)
│   ├── tools/               (generators & bridges)
│   ├── worker/              (render logic using FFmpeg)
│
├── sandbox/                 (ONLY writable runtime area)
│   ├── PRD.json             (high-level product definition)
│   ├── jobs/                (generated job.json files)
│   ├── assets/              (input media: backgrounds, clips)
│   ├── output/              (final MP4 + SRT outputs)
│   ├── inbox/               (external instructions, e.g. Telegram)
│   ├── outbox/              (agent responses)
│   └── logs/                (runtime logs)

------------------------------------------------------------

## Architecture Diagram

LOCAL (today)

  /sandbox/PRD.json
        |
        v
  Planner Agent (Clawdbot)
        |
        v
  /sandbox/jobs/*.job.json  ----->  Worker (FFmpeg render)
        |                              |
        |                              v
        |                         /sandbox/output/*.mp4
        |
        v
  Ralph (orchestrator; reads job contract and coordinates steps)

Optional ingress:
  Telegram Bot -> /sandbox/inbox/*.json

------------------------------------------------------------

CLOUD (target GCP)

  Cloud Scheduler
        |
        v
      Pub/Sub  (daily-jobs)
        |
        v
     Cloud Run (orchestrator)
        |
        +--> GCS: jobs/YYYY-MM-DD/job.json
        |
        +--> Firestore: jobs/{YYYY-MM-DD} status=PLANNED
        |
        +--> Pub/Sub (render-jobs)
               |
               v
     Worker (Cloud Run Job or VM or Local Worker)
        |
        +--> GCS: output/YYYY-MM-DD/final.mp4
        |
        +--> Firestore: status=RENDERED

------------------------------------------------------------

## Local Development

Prerequisites:
- macOS (Apple Silicon supported)
- Docker Desktop
- Docker Compose v2

Setup:
1. Copy environment template
   cp .env.example .env

2. Fill in API tokens in .env (DO NOT COMMIT)

3. Start services
   docker compose up -d

Run the full pipeline:
   docker compose run --rm worker

Outputs are written to:
   sandbox/output/

------------------------------------------------------------

## Security Model

- Agent gateway bound to loopback only
- Token-based authentication required
- No LAN or public exposure
- Containers have no access to the host home directory
- Secrets loaded via .env only
- .env is excluded from Git

This mirrors real-world production agent security practices.

------------------------------------------------------------

## Why This Project Exists

This project serves two purposes:

1. A personal automation system for AI-generated content
2. A portfolio demonstration of agent orchestration, infrastructure hygiene, and ML-adjacent systems engineering

The design intentionally avoids “magic demos” and instead emphasizes:

- clarity
- safety
- reproducibility
- real-world deployability

------------------------------------------------------------

## Roadmap

- Replace stub generator with Gemini (Vertex AI)
- Upload pack generation per platform
- Event-driven orchestration (new inbox message → render)
- GCP deployment (Cloud Run + GCS + Scheduler)
- Approval gates for high-risk actions (e.g. purchasing)

------------------------------------------------------------

## Disclaimer

This project does NOT perform autonomous financial transactions.
All potentially destructive actions require explicit human confirmation.

------------------------------------------------------------

## GCP Deployment (ML Infra Portfolio Version)

This section outlines a clean migration path from local-first development to a cloud-operated pipeline on Google Cloud Platform. The goal is to demonstrate ML-infrastructure fundamentals: event-driven orchestration, artifact storage, secure secret handling, and reproducible deployments.

### Target Cloud Architecture

Cloud Scheduler (daily trigger)
→ Pub/Sub topic (job queue)
→ Cloud Run (orchestrator API)
→ GCS (jobs + artifacts)
→ Firestore (job status + metadata)
→ (Optional) Cloud Run Job / GCE worker (rendering)
→ (Optional) Telegram bot service (instructions + notifications)

Key ML-Infra concepts demonstrated:
- Event-driven workflows (Scheduler + Pub/Sub)
- Stateless compute (Cloud Run)
- Artifact versioning (GCS)
- Secure secrets (Secret Manager + IAM)
- Observability (Cloud Logging / Error Reporting)
- Reproducible deployments (CI/CD + IaC)

### What Runs Where

Recommended split for reliability and cost control:

1) Cloud Run: Orchestrator (LLM planning / job generation)
- Generates structured job.json
- Writes job.json to GCS
- Updates Firestore status
- Publishes a “render requested” message

2) Worker (Rendering)
- Short-term: keep local worker (your Mac) pulling jobs from GCS (fast iteration)
- Later options:
  - Cloud Run Jobs (if rendering is headless and CPU-only)
  - GCE VM (if you need heavier video tooling or persistent GPU/CPU tuning)

Rendering is intentionally separated from orchestration because video rendering is CPU-heavy and benefits from controlled, deterministic execution.

### Artifact & State Layout (GCS + Firestore)

GCS bucket layout suggestion:

gs://<PROJECT>-cat-ai-factory/
  jobs/YYYY-MM-DD/job.json
  output/YYYY-MM-DD/final.mp4
  output/YYYY-MM-DD/captions.srt
  packs/YYYY-MM-DD/<platform>/{title.txt,description.txt,hashtags.txt}

Firestore collection suggestion:

jobs/{YYYY-MM-DD}
  status: "PLANNED" | "RENDERED" | "PACKAGED" | "PUBLISHED"
  job_gcs_uri: ...
  output_gcs_uri: ...
  created_at: ...
  errors: ...

This mirrors common ML pipeline patterns:
- immutable artifacts in object storage
- lightweight state in a document DB

### Security & IAM (Portfolio-Grade)

Use dedicated service accounts with least privilege:

- sa-orchestrator (Cloud Run)
  - read Secret Manager (LLM keys)
  - write to GCS bucket (jobs + metadata)
  - publish to Pub/Sub (render requests)
  - write Firestore job status

- sa-worker (Cloud Run Job / VM / local ADC)
  - read from GCS (job + assets)
  - write to GCS (render output)
  - update Firestore status (optional)

Secrets:
- Store LLM API keys in Secret Manager
- Do not store secrets in images or code
- Do not commit .env

Network boundaries:
- Keep internal services private where possible
- Use authenticated Pub/Sub push or signed URLs for artifact access

### CI/CD (Recruiter-Friendly)

Recommended pipeline:
- GitHub Actions or Cloud Build:
  - run unit tests
  - build container image
  - push to Artifact Registry
  - deploy Cloud Run on merge to main

Include:
- schema validation tests for job.json
- linting + formatting
- a “dry-run generate job” test that ensures deterministic structure

This demonstrates production discipline and reduces regressions.

### Cost Controls

To keep costs stable:
- Use smaller/cheaper models for ideation, and a stronger model only for final script polish
- Cap retries (e.g., max 1–2 regeneration attempts)
- Store artifacts in GCS with lifecycle rules (auto-delete after N days)
- Prefer template-based rendering (FFmpeg) over expensive generative video for daily runs

### Suggested Terraform Resources (High-Level)

Infrastructure-as-Code components:
- google_cloud_run_v2_service (orchestrator)
- google_pubsub_topic (daily-jobs, render-jobs)
- google_cloud_scheduler_job (daily trigger)
- google_storage_bucket (artifacts)
- google_firestore_database (Native mode)
- google_secret_manager_secret + secret versions
- IAM bindings for least privilege service accounts

This provides a clear story for ML Infra / MLOps interviews:
- reproducible provisioning
- secure secret handling
- event-driven processing
- artifact lineage and job state tracking




