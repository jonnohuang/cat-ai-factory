# Agent Operating Guide (AGENTS.md)

This document defines the responsibilities, permissions, and operational boundaries of each **plane**, **component**, and **adapter** in Cat AI Factory (CAF).

CAF is designed to mirror production ML/data platforms:

* planning is nondeterministic (LLM)
* orchestration is deterministic (control-plane)
* execution is deterministic (data-plane)

This doc is explanatory.
Binding architectural changes must be recorded in `docs/decisions.md` as ADRs.

---

## Core Rule

> **All coordination happens ONLY via explicit, versioned artifacts (“files-as-bus”).**

There is:

* no implicit shared state
* no UI-driven authority
* no agent-to-agent RPC
* no hidden background services required for correctness

All components communicate through explicit artifacts, which enables:

* reproducibility
* debuggability
* auditability
* clean failure modes

---

## CAF Invariants (Non-Negotiable)

### 1) Three-plane separation

CAF is permanently structured into three planes:

* **Planner Plane** (Clawdbot)

  * LLM-driven (nondeterministic)
  * produces contracts only

* **Control Plane** (Ralph Loop)

  * deterministic reconciler/state machine
  * idempotency, retries, audit logging

* **Worker Plane** (Renderer / FFmpeg)

  * deterministic execution
  * no LLM
  * retry-safe

### 2) Files are the bus

* no shared memory
* no RPC coordination
* no “agent chat memory” as authority

### 3) Worker is always deterministic

The Worker must never:

* call an LLM
* call network APIs
* scrape trends
* make decisions based on nondeterministic inputs

Clarification (ADR-0040 / ADR-0042):
* Worker may execute multiple deterministic stages internally (frame/audio/edit/render).
* Stage manifests are Worker execution artifacts only and MUST NOT replace `job.json` authority.

### 4) Ops/Distribution is outside the factory

Publishing is nondeterministic (external platforms). It must remain outside the factory.

---

## Filesystem Bus Identity (job_id)

CAF uses strict job identity discipline:

* The canonical `job_id` is derived from the job filename stem:

  * `sandbox/jobs/<job_id>.job.json`

* All canonical paths are keyed by `job_id`:

  * outputs: `sandbox/output/<job_id>/**`
  * logs/state: `sandbox/logs/<job_id>/**`
  * dist artifacts: `sandbox/dist_artifacts/<job_id>/**`

If the JSON contract also contains a `job_id` field and it differs:

* Ralph Loop MAY emit a warning
* Ralph Loop MUST proceed using the filename-derived job_id

---

## Canonical Runtime Write Boundaries

### Planner writes only

* `sandbox/jobs/*.job.json`

### Control Plane writes only

* `sandbox/logs/<job_id>/**`

### Worker writes only

* `sandbox/output/<job_id>/**`

### Ingress adapters write only

* `sandbox/inbox/*.json`

### Ops/Distribution writes only

* `sandbox/dist_artifacts/<job_id>/**`

Hard rules:

* No component may modify `job.json` after it is written.
* No component outside the Worker may modify `sandbox/output/<job_id>/**`.
* No component inside the factory may write to `sandbox/dist_artifacts/**`.

Planned (ADR-0034):

* EpisodePlan v1 is a planner-only intermediate artifact.
* It will be stored as a committed file (path TBD) and MUST NOT be required by Control Plane or Worker.

---

## Planner Reference Inputs (Series + Audio + RAG)

CAF supports a minimal continuity + quality layer above `job.json`.

These are **planner-only read-only reference inputs**.
They MUST NOT be modified at runtime.

Canon / continuity:

* `repo/shared/hero_registry.v1.json` (PR21)
* `repo/shared/series_bible.v1.json` (PR21.2)
* `repo/shared/episode_ledger.v1.json` (PR21.2)

Audio allowlist:

* `sandbox/assets/audio/audio_manifest.v1.json` (PR21.3)

RAG (planner-only; deterministic, file-based):

* `repo/shared/rag_manifest.v1.json` (PR22.1)
* `repo/shared/rag/**` (PR22.1)

Video Analyzer (planner-only metadata canon):

* `repo/canon/demo_analyses/**` (metadata only)
* `repo/shared/video_analysis*.schema.json` (when present)

Voice/style registries (planner/control metadata inputs):

* `repo/shared/voice_registry.v1.json` (when present)
* `repo/shared/style_registry.v1.json` (when present)

PlanRequest (UI-agnostic plan input contract):

* `repo/shared/plan_request.v1.schema.json` (PR21.5)
* `repo/examples/plan_request.v1.example.json` (PR21.5)

Creativity controls (planner-only; optional):

* `job.creativity` (PR21.1)

Important:

* The LLM may propose new facts.
* Only committed files become canon.
* RAG must never become an authority source outside committed artifacts.
* CrewAI (PR-22.2) is planner-only and MUST be contained inside a LangGraph node/subgraph.
* Video Analyzer artifacts are planner-only and MUST NOT be runtime authority for Worker.
* **Mock Mode** (`CAF_VEO_MOCK=1`) is supported across the Planner, Worker, and Orchestrator for cost-safe, deterministic E2E verification using demo assets.

---

## Lane Policy (Creativity-Friendly; Deterministic Routing)

CAF uses lanes to streamline planning, cost, and routing.

**Lanes must never restrict creativity.**

Hard rules:

* `job.lane` is OPTIONAL.
* Lanes are non-binding hints.
* Hybrid jobs are allowed.
* JSON Schema must remain permissive.
* Lane-based if/then/else “require/forbid” schema gating is disallowed.

Deterministic routing guidance:

* Prefer explicit lane routing if `job.lane` is present AND the required block exists.
* Otherwise infer route from fields:

  * if `image_motion` exists → render_image_motion
  * else if `template_remix` exists → render_template_remix
  * else → render_standard

The Worker enforces only what is required for the chosen deterministic recipe.

---

## Components (Local / Phase 6)

This section describes the core local-first system.

---

### 🎬 The Director — Orchestrator-Above-Orchestrator (Planner Plane)

**Purpose**
Orchestrates the granular, multi-stage pipeline (Brief -> Shot -> Frame -> Motion -> Assembly).

**Responsibilities**
- **Pipeline Logic**: Maps high-level creative specs to individual shot-level work orders.
- **Granular Retries**: Directs the Control Plane to re-roll specific shots based on QC failures.
- **Feedback Inversion**: Translates QC reports and OpenClaw advice into "Prompt Deltas" for subsequent attempts.
- **Idempotent Assembly**: Ensures final video stitching is consistent across r-rendered clips.

**Authority**
- Acts as the "Thinking" layer of the Planner.
- MUST NOT replace the deterministic Worker or the state-tracking Ralph Loop.
- Operates within LangGraph as a coordinating graph node.

---

### 🦞 Clawdbot — Planner Agent (Planner Plane)


**Purpose**
Translate intent into structured, machine-readable work contracts.

**Responsibilities**

* interpret `sandbox/PRD.json`
* interpret `sandbox/inbox/*.json` (optional)
* optionally consult series/audio reference inputs
* optionally produce EpisodePlan v1 (planner-only; intermediate) before job.json
* generate schema-valid `job.json`
* validate before writing (fail-loud)

**Reads**

* `sandbox/PRD.json`
* `sandbox/inbox/*.json`
* optional read-only references:

  * `repo/shared/hero_registry.v1.json`
  * `repo/shared/series_bible.v1.json`
  * `repo/shared/episode_ledger.v1.json`
  * `sandbox/assets/audio/audio_manifest.v1.json`
  * `sandbox/assets/**`

**Writes (ONLY)**

* `sandbox/jobs/<job_id>.job.json`

**Explicitly disallowed**

* writing anywhere outside `sandbox/jobs/`
* invoking FFmpeg / Worker
* orchestration responsibilities
* mutating canon files
* mutating assets
* writing logs/outputs/dist artifacts

---

### 🧠 Ralph Loop — Orchestrator (Control Plane)

**Purpose**
Deterministic reconciler/state machine.

**Responsibilities**

* interpret `job.json`
* decide which deterministic steps should run
* enforce retries and idempotency
* write audit-friendly state/log artifacts
* optionally fast-path completion when outputs already exist and pass QC

**Reads**

* `sandbox/jobs/*.job.json`
* `sandbox/output/<job_id>/**`
* `sandbox/logs/<job_id>/**`

**Writes (ONLY)**

* `sandbox/logs/<job_id>/**`

**Explicitly disallowed**

* mutating job.json
* writing worker outputs
* calling LLMs
* writing dist artifacts

---

### 🛠 Worker — Renderer (FFmpeg) (Worker Plane)

**Purpose**
Deterministic, CPU-bound execution that produces publish-ready artifacts.

**Responsibilities**

* render deterministic video + captions from job contract + assets
* apply deterministic watermark overlay
* guarantee `final.mp4` always has an audio stream (no silent MP4)
* may emit deterministic stage artifacts/manifests under `sandbox/output/<job_id>/**`

**Reads**

* `sandbox/jobs/<job_id>.job.json`
* `sandbox/assets/**`
* repo-owned static runtime assets:

  * `repo/assets/watermarks/caf-watermark.png`

**Writes (ONLY)**

* `sandbox/output/<job_id>/final.mp4`
* `sandbox/output/<job_id>/final.srt` (if applicable)
* `sandbox/output/<job_id>/result.json`

**Explicitly disallowed**

* any LLM usage
* any network calls
* reading planner continuity artifacts
* writing outside `sandbox/output/<job_id>/**`

---

### ✅ QC Verifier — Deterministic Read-Only Evaluator

**Purpose**
Provide deterministic quality control over contracts and outputs.

**Responsibilities**

* validate job.json schema
* verify artifact lineage
* verify output conformance
* emit a QC summary

**Reads**

* `sandbox/jobs/*.job.json`
* `sandbox/output/<job_id>/**`
* `sandbox/logs/<job_id>/**`

**Writes (ONLY)**

* `sandbox/logs/<job_id>/qc/**`

**Explicitly disallowed**

* modifying any artifacts
* any LLM usage

---

## Adapters (External Interfaces)

Adapters are not authorities.
They translate external systems into file-bus artifacts.

---

### 📬 Telegram Bridge — Ingress + Status (Adapter)

**Purpose**
Mobile supervisor surface (human-in-the-loop).

**Responsibilities**

* write inbox artifacts into `sandbox/inbox/`
* daily_plan artifacts MAY include optional creativity hints for the Planner:
  - `creativity.mode`: canon | balanced | experimental
  - `creativity.canon_fidelity`: high | medium
* read status artifacts and report them back

**Writes (ONLY)**

* `sandbox/inbox/*.json`

**Reads (ONLY)**

* `sandbox/logs/<job_id>/state.json`
* `sandbox/dist_artifacts/<job_id>/<platform>.state.json` (if present)

**Security constraints**

* authorized sender check required (e.g., `TELEGRAM_ALLOWED_USER_ID`)
* MUST NOT invoke orchestrator or worker
* MUST NOT modify outputs/logs/dist artifacts
* MUST NOT overwrite or delete any existing files

---

### 🧭 Guided UI (Coze or equivalent) — PlanRequest Ingress (Adapter)

**Purpose**
Provide a guided UI for structured planning inputs.

**Responsibilities**

* emit PlanRequest v1 artifacts (adapter-neutral)
* submit to CAF ingress without bypassing the file-bus

**Writes (ONLY)**

* `sandbox/inbox/*.json` (PlanRequest v1)

**Reads (ONLY)**

* none (UI-only; no authority)

**Explicitly disallowed**

* emitting `job.json` directly
* storing or mutating canon/continuity artifacts
* bypassing CAF Planner authority

---

## Ops/Distribution (Outside the Factory)

Ops/Distribution performs nondeterministic external work.

**Responsibilities**

* consume immutable worker outputs + publish plans
* produce export bundles + checklists
* optionally upload using official APIs (opt-in)
* enforce human approval gates by default
* maintain idempotency keyed by `{job_id, platform}`
* host explicit external HITL recast steps (Viggle-class), when configured

**Writes (ONLY)**

* `sandbox/dist_artifacts/<job_id>/**`

**Hard constraints**

* MUST NOT mutate `job.json`
* MUST NOT modify `sandbox/output/<job_id>/**`
* MUST NOT bypass file-bus semantics
* MUST NOT commit or write secrets

External recast/HITL rule (ADR-0044):
* export pack path:
  - `sandbox/dist_artifacts/<job_id>/viggle_pack/**`
* re-ingest to factory MUST be explicit inbox metadata under:
  - `sandbox/inbox/*.json`
* no hidden manual file drops become authoritative state
* optional validation schema for pack completeness/consistency:
  - `viggle_pack.v1` (when present)

Ops workflow automation (e.g., n8n) is allowed only in this layer:

* n8n is ops UX/integrations only (notifications, approvals, manual publish triggers)
* n8n MUST NOT replace Cloud Tasks for internal execution retries/backoff
* n8n MUST NOT bypass CAF contract/state authority (files-as-bus locally; Firestore/GCS in cloud)

---

## Phase 7 (Mandatory Milestone): Cloud Mapping Without Breaking Invariants

Phase 7 migrates CAF from local Docker Compose to a serverless, event-driven GCP architecture.

This is a deployment/runtime change.
The core invariants MUST remain identical.

### Phase 7 roles (cloud runtime)

These are runtime components, not new planes.
They preserve the same boundaries.

---

### ☁️ Telegram Webhook Receiver (Cloud Run)

**Purpose**
Receive Telegram webhook events.

**Hard requirement**
Telegram webhooks must not block (avoid Telegram timeouts).

**Responsibilities**

* authenticate Telegram sender
* immediately enqueue an async task
* return HTTP 200 quickly

**Writes**

* does NOT write job/output/log artifacts directly

**Enqueues**

* Cloud Tasks job for planner invocation

---

### ☁️ Cloud Tasks Bridge (Async buffer)

**Purpose**
Async bridge with retries between Receiver and Planner.

**Responsibilities**

* retry delivery
* decouple Telegram latency from planning

---

### ☁️ Planner Service (LangGraph on Cloud Run)

**Purpose**
Planner plane, hosted as a stateful workflow.

**Responsibilities**

* Analyze Brief (LLM)
* Draft Contract (LLM)
* Validate Schema (deterministic)
* Persist Job Contract state (deterministic)

**State store**

* Firestore (preferred)

**Artifact store**

* GCS for immutable artifacts

**Hard constraints**

* must not execute FFmpeg
* must not mutate worker outputs

---

### ☁️ Control Plane (Ralph Loop) on Cloud Run

**Purpose**
Deterministic reconciler, hosted in serverless runtime.

**Responsibilities**

* reconcile desired state (Firestore job contract)
* invoke Worker (Cloud Run)
* write logs/state to Firestore and/or GCS

**Hard constraints**

* deterministic only
* no LLM usage

---

### ☁️ Worker Service (FFmpeg on Cloud Run)

**Purpose**
Deterministic renderer.

**Responsibilities**

* pull job contract state
* read assets from GCS
* render deterministically
* write outputs to GCS

**Hard constraints**

* no LLM
* no network calls except GCS read/write

---

### ☁️ Signed URL Handoff (Manual Posting)

**Purpose**
Phase 7 must produce a Signed URL for the final output so posting remains manual.

**Hard rule**
Ops/Distribution remains outside the factory.

---

## Failure Philosophy

* Fail fast.
* Fail loud.
* Never partially mutate state.

If required inputs are missing or invalid, the system exits immediately without producing partial or ambiguous artifacts.

---

## End-to-End Video Generation Workflow

This section documents the optimal path for high-quality video generation, covering the entire lifecycle from sample analysis to final output.

### 1. Sample Analysis & Ingestion (Lab Plane)

Before generating content, reference assets (like character turnarounds or style references) must be ingested into the deterministic canon.

*   **Analyze Video**:
    *   Command: `python -m repo.tools.analyze_video --input <video_path> --output <json_path>`
    *   Purpose: Extracts deterministic metadata (beats, shot pattern, motion profile) from a video.
    *   Output: `video_analysis.v1` JSON.

*   **Ingest Samples**:
    *   Command: `python -m repo.tools.ingest_demo_samples --incoming-dir <dir>`
    *   Purpose: Bulk analyze and register demo videos into `repo/canon/demo_analyses`.
    *   Artifacts: Creates `sample_ingest_manifest.v1` and moves assets to processed directory.

### 2. Hero Image Creation (Frame Engine)

The **Frame Engine** is responsible for creating the "seed" or "hero" image that anchors the video's identity.

*   **Current State**:
    *   Hero images are typically opaque assets provided to the factory (e.g., `assets/demo/mochi_front.png`).
    *   **Planner Role**: The planner selects these assets via `quality_context` or `render.background_asset` pointers in `job.json`.
    *   **Generation**: Future capability (e.g., `grok_image` or `imagen`) will generate these via a Worker adapter. For now, they are treated as static inputs or external hand-offs.

### 3. User Brief & Planning (Planner Plane)

The workflow begins with a user intent.

*   **Entry Point**:
    *   Command: `python repo/tools/run_autonomous_brief.py --prompt "..." --provider vertex_veo`
    *   Function: Orchestrates the transition from vague brief to strict contract.

*   **Planner Logic (`Clawdbot`)**:
    *   Analyzes brief against `PRD.json` and optional `inbox` context.
    *   Selects **optimal path**:
        *   **Provider**: `vertex_veo` (for high-quality generation) or `comfyui` (for controllable motion).
        *   **Lane**: `ai_video` (generative) or `template_remix` (composite).
    *   Generates `job.json` containing:
        *   `generation_policy`: explicit provider order (e.g., `["vertex_veo", "wan_dashscope"]`).
        *   `image_motion.seed_frames`: pointer to Hero Image.
        *   `render.background_asset`: fallback/primary visual anchor.
        *   **Motion Metadata Translation**:
            *   Extracts `video_analysis.v1` signals (energy, camera patterns).
            *   Translates signals into Veo3 motion vocabulary (e.g., "building energy" -> "intense motion").
            *   Injects translated tokens into `job.prompt` for generative alignment.
            *   Verified by `job.schema.json` (root `prompt` field support).

### 4. Component Execution (Control & Worker Planes)

The **Control Plane (`Ralph Loop`)** executes the deterministic recipe defined in `job.json`.

*   **Motion Engine (Video Generation)**:
    *   **Vertex Veo3**:
        *   Worker: `repo/worker/render_veo.py`
        *   Input: Prompt + Seed Image (I2V).
        *   Action: Calls Vertex AI, polls LRO, writes raw video to `sandbox/output/<job_id>`.
    *   **ComfyUI**:
        *   Worker: `repo/worker/render_ffmpeg.py` (wraps Comfy execution).
        *   Input: Workflow JSON + Assets.
        *   Action: Executes local ComfyUI graph.

*   **Audio Engine**:
    *   Worker: `repo/worker/render_ffmpeg.py`
    *   Action: Mixes `audio.audio_asset` (voiceover/music) with video.

*   **Editor Engine**:
    *   Worker: `repo/worker/render_ffmpeg.py`
    *   Action:
        *   Stitches segments (if `segment_stitch` is enabled).
        *   Applies watermarks (`repo/assets/watermarks/caf-watermark.png`).
        *   Burns captions (if `captions` present).
        *   Produces `final.mp4`.

### 5. Quality Control (QC Engine)

Verification is automated and deterministic.

*   **QC Engine**:
    *   Tool: `repo/tools/decide_quality_action.py` (invoked by Ralph).
    *   Logic:
        *   Checks `quality_target` thresholds (e.g., `identity_consistency > 0.7`).
        *   Validates artifact lineage (ensure `final.mp4` matches `job.json` spec).
        *   Enforces `fail-closed` policy for missing inputs/reports.
    *   Output: `quality_decision.v1.json` (Pass/Fail/Retry).

### 6. Troubleshooting & Gotchas

*   **ModuleNotFoundError: No module named 'repo'**:
    *   **Cause**: Worker environment missing `PYTHONPATH`.
    *   **Fix**: `ralph_loop.py` injects `PYTHONPATH=repo_root` automatically (Fixed in PR-36).

*   **Auth Errors (403/401)**:
    *   **Vertex**: Check `VERTEX_PROJECT_ID` and `VERTEX_LOCATION`. Use `gcloud auth application-default login`.
    *   **Comfy**: Ensure local server is running at `127.0.0.1:8188`.
