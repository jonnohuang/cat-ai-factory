# Cat AI Factory 🐱🎬
A headless, agent-driven AI content factory for short-form video generation

**Start here:** `docs/architecture.md` (diagram-first architecture)

------------------------------------------------------------

## Overview

Cat AI Factory is a local-first, headless agent system that generates short-form vertical videos (Reels / Shorts) through a reproducible pipeline.

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

**Diagram-first details:** `docs/architecture.md`

PRD / Instructions  
→ Planner Agent (Clawdbot)  
→ `job.json` (structured contract)  
→ Control Plane (Ralph Loop orchestrator)  
→ Worker (FFmpeg Renderer)  
→ MP4 + captions  

Optional ingress:

Telegram Message  
→ Message Bridge  
→ `/sandbox/inbox`

All agent interaction happens through **files**, not shared memory, RPC, or browser UIs.

Frameworks (LangGraph, etc.) are treated as **adapters**, not foundations. RAG is **planner-only**.

------------------------------------------------------------

## Design Principles

- Headless-first: no required UI or dashboard
- Deterministic: outputs reproducible from inputs
- Contract-driven: files are the source of truth
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
├── docs/
│   ├── architecture.md
│   ├── master.md
│   ├── decisions.md
│   ├── memory.md
│   ├── chat-bootstrap.md
│   └── briefs/
│       ├── BOOTSTRAP-BASE.md
│       ├── BOOTSTRAP-ARCH.md
│       ├── BOOTSTRAP-IMPL.md
│       └── BOOTSTRAP-CODEX.md
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

## How to Bootstrap a New Chat (ARCH / IMPL / CODEX)

This repo is designed to be worked on using **role-separated chats**:

- ARCH = decisions + contracts + doc structure
- IMPL = debugging + edge cases + implementation review
- CODEX = file-writing implementation (PR-sized diffs only)

### Always send 2 messages at the start of a new chat

1) Base bootstrap (project constitution)
- docs/chat-bootstrap.md

2) Role bootstrap (pick exactly one)
- docs/briefs/BOOTSTRAP-ARCH.md
- docs/briefs/BOOTSTRAP-IMPL.md
- docs/briefs/BOOTSTRAP-CODEX.md

This keeps invariants consistent, while letting each role stay ultra-focused.

### Standard handoff packet (send after the 2 bootstraps)

Send this in order:

1) PR context
- PR name + goal (1–2 lines)
- In scope / out of scope
- Binding decisions (if any)

2) Repo tree (scoped)
Do NOT paste the full repo tree. Use one of:
- tree -L 2 repo/services/orchestrator repo/tools repo/worker docs
- tree -L 3 repo/services repo/tools repo/worker docs | sed -n '1,200p'

3) Working state
- git status
- git diff (only relevant files)

4) Authoritative docs (only if needed)
- ARCH: docs/master.md, docs/decisions.md, docs/architecture.md
- IMPL: docs/architecture.md + the relevant PR plan section
- CODEX: PR prompt + file touch list + invariants (avoid dumping full docs)

5) For debugging runs
- exact CLI command
- stdout/stderr
- state.json + last 30 lines of events.ndjson

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

## Roadmap (Non-Binding)

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
