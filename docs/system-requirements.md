# Cat AI Factory — System Requirements (Human-Readable)

This document summarizes **what the system must do** (requirements) and **what it must never do**
(non-goals / guardrails). It is reviewer-facing and intentionally short.

Authority:
- Binding invariants and rationale: `docs/master.md`
- Binding decisions (ADRs): `docs/decisions.md`
- Diagram-first architecture: `docs/architecture.md`
- PR sequencing / scope: `docs/PR_PROJECT_PLAN.md`

------------------------------------------------------------

## 1) System Summary

Cat AI Factory is a **headless, file-contract, deterministic** content factory for producing short-form videos.

Core invariant:
Planner (Clawdbot) → Control Plane (Ralph Loop) → Worker (FFmpeg)

- Planner is the only nondeterministic component (LLM-driven).
- Control Plane + Worker must remain deterministic and retry-safe.
- Files are the bus: no shared memory, no agent-to-agent RPC.

------------------------------------------------------------

## 2) Functional Requirements (FR)

### FR-01 — Contract-first planning
- Planner MUST output a versioned, validated job contract (`job.json`) under `/sandbox/jobs/`.
- Planner MUST NOT write any other artifacts (no outputs, logs, assets).

### FR-02 — Deterministic orchestration
- Ralph Loop MUST reconcile a job deterministically.
- Ralph Loop MUST write only state/log artifacts under `/sandbox/logs/<job_id>/**`.
- Ralph Loop MUST NOT mutate `job.json`.
- Ralph Loop MUST support retries without changing outputs.

### FR-03 — Deterministic rendering
- Worker MUST render deterministically from `job.json` + `/sandbox/assets/**`.
- Worker MUST write outputs only under `/sandbox/output/<job_id>/**`:
  - `final.mp4`, `final.srt`, `result.json`
- Worker MUST NOT call any LLMs or image-generation APIs.

### FR-04 — Artifact lineage verification
- The system MUST support deterministic verification that required artifacts exist and are consistent:
  - job → outputs → logs/state (lineage)
- Determinism checking across environments is OPTIONAL (harness-only).

### FR-05 — Planner autonomy target
- The long-term target is **autonomous planning** (no human-in-loop planner).
- Human approval gates may exist for nondeterministic external actions (e.g., publishing), not for core planning.

### FR-06 — LLM provider strategy (phased)
- LOCAL: Planner calls Gemini via **Google AI Studio API key**.
  - API key injected at runtime; never committed.
  - No OAuth required for local model calls.
- CLOUD (later): The final portfolio state MUST include **Vertex AI** as a first-class provider option.

### FR-07 — Style selection (manifest + deterministic best-effort)
- The system MUST support a style reference mechanism that allows a human to provide preferred style examples.
- The canonical local mechanism is a **style manifest** under `/sandbox/assets/manifest.json`.
- Planner MAY read the manifest to select a style deterministically (best-effort), without requiring schema changes.
- The system MUST NOT overwrite an existing manifest file.
- Remote adapters (e.g., Telegram) MAY update the manifest only via explicit user intent (never implicitly).

### FR-08 — Multi-lane daily output strategy (required)
The system MUST support multiple production lanes for daily output.

- Lane A: `ai_video` (premium / expensive)
  - Video generation via cloud providers (Vertex AI) is allowed in this lane only.
- Lane B: `image_motion` (cheap / scalable)
  - 1–3 seed frames + deterministic FFmpeg motion presets.
- Lane C: `template_remix` (near-free / scalable)
  - Uses existing templates/clips + deterministic FFmpeg recipes.

Constraints:
- Worker MUST remain deterministic in all lanes.
- Planner MAY choose lane mix based on a daily plan brief and budget guardrails.

### FR-09 — Telegram = daily plan brief ingress (required)
Telegram is the human-facing ingress for daily planning and approvals.

- Telegram MUST remain an adapter:
  - writes requests into `/sandbox/inbox/`
  - reads status from `/sandbox/logs/<job_id>/state.json`
  - reads publish status from `/sandbox/dist_artifacts/<job_id>/<platform>.state.json`
- Telegram MUST NOT bypass the file-bus.
- Telegram MUST NOT mutate worker outputs or `job.json`.

### FR-10 — Ops/Distribution is outside the factory (required)
Ops/Distribution automation (e.g., runners, publisher adapters, bundles) MUST remain outside the three-plane factory.

It MAY:
- read factory outputs under `/sandbox/output/<job_id>/`
- write derived artifacts under `/sandbox/dist_artifacts/<job_id>/`

It MUST NOT:
- modify worker outputs
- modify `job.json`

### FR-11 — Approval-gated distribution (required)
- Distribution MUST be approval-gated by default via inbox artifacts:
  - `sandbox/inbox/approve-<job_id>-<platform>-<nonce>.json`
- A deterministic local distribution runner MUST be able to:
  - poll file-bus artifacts
  - detect approvals
  - invoke publisher adapters
  - remain idempotent

### FR-12 — Publisher adapter interface (bundle-first; required pre-cloud)
Before cloud migration, the system MUST support a publisher adapter interface and platform modules for:

- YouTube
- Instagram
- TikTok
- X

Constraints:
- v1 publisher adapters MUST be **bundle-first**:
  - produce export bundles + copy artifacts + posting checklists
  - allow manual posting in <2 minutes per clip
- Upload automation is OPTIONAL per platform.
- No credentials committed to repo.
- No browser automation.

### FR-13 — Promotion toolkit is artifacts-only (required)
The system MUST support “promotion automation” as artifact generation only:

- schedule windows
- platform caption variants
- hashtag variants
- pinned comment suggestions (where applicable)
- export bundles per platform

Non-goals:
- no posting automation required
- no engagement automation
- no scraping analytics

### FR-14 — Hero cats are metadata (required)
The system MUST support a small “hero cat cast” registry.

- Hero cats are metadata, NOT agents.
- Planner uses character metadata for copy/series continuity.
- No story-memory engine is required.

### FR-15 — LangGraph demo requirement (planner-only; required)
The project MUST include a LangGraph workflow demo for recruiter signaling.

Constraints:
- LangGraph MUST be planner-plane only (workflow adapter).
- LangGraph MUST NOT replace Ralph Loop or the Worker.

### FR-16 — Multilingual support (EN + zh-Hans now; extensible)
The system MUST support multilingual copy for captions and platform text.

- Exactly two languages enabled initially:
  - English: `en`
  - Simplified Chinese: `zh-Hans`
- Contracts MUST support N languages via language-map structures.
- Spanish (`es`) is explicitly deferred.

### FR-17 — Audio included in export bundles (required)
Audio is part of the posting workflow.

- Every clip export bundle MUST include:
  - `audio_plan.json`
  - `audio_notes.txt`
- Audio is represented as:
  1) audio strategy metadata, and
  2) optional bundled audio assets (SFX stingers, optional voiceover track)

Non-goals (v1):
- no music generation
- no automated trending-music selection
- no scraping platform trends

------------------------------------------------------------

## 3) Non-Functional Requirements (NFR)

### NFR-01 — Reproducibility and debuggability
- Runs MUST be debuggable via artifacts and logs on disk.
- State transitions MUST be auditable.

### NFR-02 — Idempotency and retry-safety
- Control Plane retries MUST NOT introduce duplicate side effects.
- Worker reruns MUST be safe and overwrite outputs atomically (as designed in v0.1).
- Distribution publishing MUST be idempotent per `{job_id, platform}`.

### NFR-03 — Portability
- Local execution MUST work on a personal Mac via Docker sandboxing.
- Avoid OS-specific locking dependencies (prefer atomic mkdir locks).

------------------------------------------------------------

## 4) Security Requirements (SEC)

### SEC-01 — Secrets handling
- Secrets (API keys/tokens) MUST be runtime-injected only:
  - LOCAL: `.env` / secret mount
  - CLOUD: Secret Manager
- Secrets MUST NOT be committed to Git.
- Secrets MUST NOT be written to artifacts:
  - `job.json`, `state.json`, `events.ndjson`, outputs, or logs
- Logs MUST redact any secret-derived values.

### SEC-02 — Network exposure
- Any local gateway MUST bind loopback-only and require token auth (defense in depth).

### SEC-03 — Least privilege (cloud)
- Cloud IAM MUST be least-privilege for Vertex + storage + events.
- Cloud integration must not break local-only workflows.

------------------------------------------------------------

## 5) Budget Guardrails (BUDGET)

Budget guardrails are required to prevent runaway autonomous costs.

### BUDGET-01 — Budget model
- The system MUST support:
  - per-job cost estimate (planner-provided or adapter-provided)
  - per-day and/or per-month caps
  - hard-stop behavior when budget is exceeded

### BUDGET-02 — Enforcement point
- Budget enforcement MUST occur before spending (control plane or planner adapter gate).
- Worker MUST remain cost-neutral (no LLM calls, no external paid APIs).

### BUDGET-03 — Accounting + idempotency
- Budget usage tracking MUST be idempotent (no double counting on retries).
- Accounting keys SHOULD include `{job_id, provider, model, attempt}` or equivalent.

(Implementation may be local-first, then integrated with Cloud Billing budgets later.)

------------------------------------------------------------

## 6) Explicit Non-Goals

- No agent-to-agent RPC or shared memory coordination.
- No LLM usage in the Worker.
- No nondeterministic rendering.
- No autonomous financial transactions.
- No secrets in Git; no secrets printed in logs.
- No schema changes unless explicitly required (ADR required if semantics change).
- No engagement automation (likes/comments/follows).
- No scraping analytics.
