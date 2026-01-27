# Cat AI Factory 🐱🎬
A headless, agent-driven AI content factory for short-form video generation

------------------------------------------------------------

## Overview

Cat AI Factory is a local-first, headless AI agent system that generates short-form vertical videos (Reels / Shorts) through a fully automated, reproducible pipeline.

The project is intentionally designed as an **infrastructure-focused system**, demonstrating how AI agents can be operationalized safely and deterministically rather than as UI-driven demos.

The current niche is “cute lifelike cats doing funny activities”, but the architecture is content-agnostic.

------------------------------------------------------------

## Why This Matters (ML Infra / MLOps Portfolio)

This project showcases practical ML-infrastructure skills beyond model training:

- Event-driven orchestration patterns (scheduler/queue → stateless compute → artifacts)
- Deterministic, testable contracts (`job.json`) with reproducible outputs
- Clear separation of concerns: planning (LLM) vs execution (renderer)
- Secure-by-default agent operation (sandboxed writes, loopback-only gateway, token auth)
- Artifact lineage and state tracking (jobs, outputs, status progression)
- A realistic migration path to GCP (Cloud Run, Pub/Sub, GCS, Firestore, Secret Manager, IAM)

In short, it demonstrates how to operationalize an AI agent workflow with real infra hygiene,
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

All agent interaction happens through **files**, not shared memory, RPC, or browser UIs.

------------------------------------------------------------

## Design Principles

- Headless-first: no required UI or dashboard
- Deterministic: outputs reproducible from inputs
- Sandboxed: containers write only to `/sandbox`
- Secure by default:
  - loopback-only gateway
  - token-based authentication
  - secrets never committed
- Cloud-ready: clean mapping to GCP services

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
  /sandbox/jobs/*.job.json  ----->  Worker (FFmpeg renderer)
        |                              |
        |                              v
        |                         /sandbox/output/*.mp4
        |
        v
  Ralph Loop (orchestrator; reconciles job contracts and coordinates execution)

Optional ingress:
  Telegram Bot → /sandbox/inbox/*.json

------------------------------------------------------------

CLOUD (target GCP)

  Cloud Scheduler
        |
        v
      Pub/Sub (daily-jobs)
        |
        v
     Cloud Run (Ralph Loop orchestrator)
        |
        +--> GCS: jobs/YYYY-MM-DD/job.json
        |
        +--> Firestore: jobs/{YYYY-MM-DD} status=PLANNED
        |
        +--> Pub/Sub (render-jobs)
               |
               v
     Worker (Cloud Run Job, VM, or local worker)
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

2. Fill in API tokens in `.env` (DO NOT COMMIT)

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
- Secrets loaded via `.env` only
- `.env` excluded from Git

This mirrors real-world production agent security practices.

------------------------------------------------------------

## Why This Project Exists

This project serves two purposes:

1. A personal automation system for AI-generated content
2. A portfolio demonstration of agent orchestration, infrastructure hygiene,
   and ML-adjacent systems engineering

The design intentionally avoids “magic demos” and instead emphasizes clarity,
safety, reproducibility, and real-world deployability.

------------------------------------------------------------

## Roadmap

- Replace stub generator with Gemini (Vertex AI)
- Upload pack generation per platform
- Event-driven orchestration (new inbox message → render)
- GCP deployment (Cloud Run, GCS, Scheduler)
- Approval gates for high-risk actions (e.g. purchasing)

------------------------------------------------------------

## GCP Deployment (ML Infra Portfolio Version)

This section outlines a clean migration path from local-first development to a
cloud-operated pipeline on Google Cloud Platform.

Key ML-infra concepts demonstrated:
- Event-driven workflows (Scheduler + Pub/Sub)
- Stateless compute (Cloud Run)
- Artifact versioning (GCS)
- Secure secrets (Secret Manager + IAM)
- Observability (Cloud Logging, Error Reporting)
- Reproducible deployments (CI/CD + IaC)

Rendering is intentionally separated from orchestration because video rendering
is CPU-heavy and benefits from controlled, deterministic execution.

------------------------------------------------------------

## Tech Stack

- Python 3.11 – orchestration logic, job generation, message bridges
- Docker & Docker Compose – sandboxed, reproducible local execution
- FFmpeg – deterministic video rendering and caption burn-in
- AI Agents – planner/orchestrator pattern (Clawdbot + Ralph Loop)
- Telegram Bot API – optional external instruction ingress
- Google Cloud Platform (target) – Cloud Run, Pub/Sub, GCS, Firestore, Secret Manager
- Terraform (planned) – infrastructure-as-code

------------------------------------------------------------

## Disclaimer

This project does NOT perform autonomous financial transactions.
All potentially destructive actions require explicit human confirmation.
