# Cat AI Factory 🐱🎬
A headless, agent-driven content factory for short-form vertical video (Shorts/Reels/TikTok)

**Start here:** `docs/architecture.md` (diagram-first)

Key docs:
- `docs/system-requirements.md` (what must be true)
- `docs/PR_PROJECT_PLAN.md` (roadmap / PR sizing)
- `docs/decisions.md` (binding ADRs)
- `docs/lab-mode-runbook.md` (OpenClaw lab mode usage)
- `docs/engine-adapters.md` (adapter/env matrix)
- `docs/comfyui-workflows.md` (workflow_id registry pattern)
- `docs/qc-pipeline-guide.md` (QC gates + artifacts + routing flow)
- `docs/external-hitl-workflow.md` (default flow vs external HITL recast flow)
- `docs/video-workflow-end-to-end.md` (single end-to-end multi-stage runbook)
- `docs/briefs/MILESTONE-daily-v0.2.md` (daily output workflow)
- `docs/now.md` (live PR status ledger; role sync)

------------------------------------------------------------

## Overview

Cat AI Factory (CAF) is a local-first, headless agent system that generates short-form vertical videos through a reproducible, contract-driven pipeline.

This is not a prompt demo or a UI chatbot.

CAF is intentionally designed as an **infrastructure-focused system** that demonstrates how AI agents can be operationalized safely and deterministically, using production-style patterns:

- strict separation of responsibilities
- explicit file contracts
- idempotent execution
- artifact lineage + audit logs
- safe boundaries for nondeterministic work (LLMs, publishing)

The current niche is “cute lifelike cats doing funny activities”, but the architecture is content-agnostic.

------------------------------------------------------------

## Why This Matters (ML Infra / Platform / MLOps Portfolio)

This project showcases ML-infrastructure skills beyond model training:

- Contract-first pipelines (`job.json`) with schema validation
- Deterministic orchestration (control-loop reconciler pattern)
- Deterministic rendering (FFmpeg worker; retry-safe)
- Artifact lineage, state tracking, and auditability
- Secure-by-default agent operation:
  - sandboxed writes
  - loopback-only gateway
  - token auth
  - secrets never committed
- A clean migration path to GCP (Cloud Run, Pub/Sub, GCS, Firestore, Secret Manager, IAM)
- Realistic “Ops/Distribution” layer:
  - approval-gated publishing
  - bundle-first export modules per platform
  - idempotent publish state keyed by `{job_id, platform}`

------------------------------------------------------------

## High-Level Architecture (3-plane invariant)

**Diagram-first details:** `docs/architecture.md`

PRD / Instructions  
→ Planner Agent (Clawdbot)  
→ EpisodePlan v1 (planner-only intermediate)  
→ `job.json` (structured contract)  
→ Control Plane (Ralph Loop orchestrator)  
→ Worker (FFmpeg renderer)  
→ MP4 + captions  

Optional ingress (adapter-only):

Telegram / Coze / future UI  
→ Adapter  
→ PlanRequest v1 (`/sandbox/inbox/*.json`)
→ Planner (source of truth)

All coordination happens through **files**, not shared memory, RPC, or browser UIs.

Frameworks (LangGraph, etc.) are treated as **adapters**, not foundations.
RAG is **planner-only**.
CrewAI (when used) is planner-only and contained inside a single LangGraph node.

------------------------------------------------------------

## Design Principles

- Headless-first: no required UI or dashboard
- Deterministic execution: outputs reproducible from inputs
- Contract-driven: files are the source of truth
- Sandboxed: containers write only to `/sandbox`
- Secure by default:
  - loopback-only gateway
  - token-based authentication
  - secrets never committed
- Cloud-ready: clean mapping to GCP services
- Ops/Distribution is outside the factory:
  - derived artifacts only
  - no mutation of worker outputs
  - approval gates by default

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
│   ├── system-requirements.md
│   ├── PR_PROJECT_PLAN.md
│   ├── memory.md
│   ├── chat-bootstrap.md
│   └── briefs/
│       ├── BOOTSTRAP-BASE.md
│       ├── BOOTSTRAP-ARCH.md
│       ├── BOOTSTRAP-IMPL.md
│       ├── BOOTSTRAP-CODEX.md
│       └── MILESTONE-daily-v0.2.md
│
├── repo/                    (source code, read-only to containers)
│   ├── shared/              (schemas & contracts)
│   ├── services/            (orchestrator + planner)
│   ├── tools/               (validators, bridges, publishers)
│   └── worker/              (render logic using FFmpeg)
│
├── sandbox/                 (ONLY writable runtime area)
│   ├── PRD.json             (high-level product definition)
│   ├── jobs/                (generated job contracts)
│   ├── assets/              (input media: clips, backgrounds, templates)
│   ├── output/              (immutable worker outputs per job)
│   ├── logs/                (orchestrator logs/state per job)
│   ├── inbox/               (external instructions, approvals, plan briefs)
│   ├── outbox/              (agent responses)
│   └── dist_artifacts/      (derived distribution artifacts; bundles, state)

------------------------------------------------------------

## Ops/Distribution (required before cloud)

CAF includes a required “Ops/Distribution” layer which remains OUTSIDE the factory invariant.

It is responsible for:
- approvals (human-in-the-loop)
- publisher adapters (bundle-first, platform-specific)
- idempotent publish state tracking
 - optional ops workflow automation (e.g., n8n) for notifications/approvals only

Hard constraints:
- MUST NOT mutate `job.json`
- MUST NOT modify worker outputs under `sandbox/output/<job_id>/...`
- MUST emit derived artifacts only under:
  - `sandbox/dist_artifacts/<job_id>/...`

n8n MUST remain outside the factory and MUST NOT replace Cloud Tasks for internal execution retries/backoff.

This is intentionally designed so cloud migration is a mapping exercise, not a redesign.

------------------------------------------------------------

## How to Bootstrap a New Chat (ARCH / IMPL / CODEX)

This repo is designed to be worked on using **role-separated chats**:

- ARCH = decisions + contracts + doc structure
- IMPL = debugging + edge cases + implementation review
- CODEX = file-writing implementation (PR-sized diffs only)

### Always send 2 messages at the start of a new chat

1) Base bootstrap (project constitution)
- `docs/chat-bootstrap.md`

2) Role bootstrap (pick exactly one)
- `docs/briefs/BOOTSTRAP-ARCH.md`
- `docs/briefs/BOOTSTRAP-IMPL.md`
- `docs/briefs/BOOTSTRAP-CODEX.md`

------------------------------------------------------------

## Local Development

Prerequisites:
- macOS (Apple Silicon supported)
- Docker Desktop
- Docker Compose v2

Setup:
1) Copy environment template  
   cp .env.example .env

2) Fill in API tokens in `.env` (DO NOT COMMIT)

3) Start services  
   docker compose up -d

Outputs are written to:
- `sandbox/output/<job_id>/` (worker outputs)
- `sandbox/logs/<job_id>/` (orchestrator state/logs)
- `sandbox/dist_artifacts/<job_id>/` (publisher/bundle artifacts)

------------------------------------------------------------

## Security Model

- Agent gateway bound to loopback only
- Token-based authentication required
- No LAN or public exposure
- Containers have no access to the host home directory
- Secrets loaded via `.env` only
- `.env` excluded from Git

------------------------------------------------------------

## Why This Project Exists

This project serves two purposes:

1) A personal automation system for daily short-form content output
2) A portfolio demonstration of agent orchestration, infrastructure hygiene,
   and production-grade boundary enforcement

The design intentionally avoids “magic demos” and instead emphasizes clarity,
safety, reproducibility, and deployability.
