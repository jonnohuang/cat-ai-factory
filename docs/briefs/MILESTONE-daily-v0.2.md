# CAF Milestone Brief — DAILY v0.2 (3 Clips/Day)

This brief is a **prompt-ready entrypoint** for the “daily output era” of Cat AI Factory (CAF).

Authority:
- Binding decisions: `docs/decisions.md`
- Invariants & rationale: `docs/master.md`
- Requirements: `docs/system-requirements.md`
- Architecture diagrams: `docs/architecture.md`
- PR sequencing: `docs/PR_PROJECT_PLAN.md`

This file is NOT a contract and does NOT override ADRs.

------------------------------------------------------------

## Goal

Enable a sustainable, deterministic, reviewer-friendly workflow that supports:

- **3 clips/day**
- **10–15 seconds**
- **1080p Shorts/Reels format**
- **strict budget constraints**
- **multi-platform posting readiness**
- strong portfolio signal for Google:
  - LangGraph demo (planner-only)
  - Vertex AI integration (later)
  - clean file-bus + control-plane patterns

The key point: **we do not generate 3 expensive AI videos/day.**

We generate **3 daily clips** using a multi-lane strategy while preserving the
core architecture invariants.

------------------------------------------------------------

## The Required Strategy: Multi-Lane Daily Output

CAF becomes a deterministic renderer with multiple production lanes.

### Lane A — ai_video (premium, expensive)
- Provider: Vertex Veo (later; cloud)
- Optional: manual Sora lane (not factory default)
- Requires strict budget gates

### Lane B — image_motion (cheap, scalable)
- Provider: Imagen seed frames (later; cloud)
- Worker: deterministic FFmpeg motion presets (Ken Burns, shake, cuts)
- Produces MP4 outputs that feel like video

### Lane C — template_remix (near-free, most scalable)
- Inputs: existing clips/templates + captions
- Worker: deterministic FFmpeg recipes
- No LLM in Worker

Default daily mix:
- A=0, B=1, C=2

Premium day:
- A=1, B=1, C=1

Zero-spend day:
- A=0, B=0, C=3

------------------------------------------------------------

## What “Daily v0.2” Means (Behavior)

Daily v0.2 is defined as:

1) Human sends a **Daily Plan Brief** (Telegram preferred)
2) Planner may produce an EpisodePlan v1 (planner-only intermediate) before committing job.json
3) Planner generates **exactly N jobs**
4) Ralph/Worker deterministically produce outputs
5) System produces **publish-ready export bundles**
6) Human posts manually using bundles (fast)
7) Optional automation is allowed only where safe (YouTube later)

------------------------------------------------------------

## Inputs (Human Interface)

### Telegram is the canonical input channel
Telegram is the human-facing control surface.

Hard constraints:
- Telegram = inbox write + status read only
- No direct execution authority
- No bypass of file-bus semantics

### Daily Plan Brief
The daily plan brief is the canonical interface.

It should allow the human to specify:
- desired lane mix (A/B/C)
- theme/topic
- optional hero cats
- optional templates to remix
- optional “auto style” behavior (best-effort)
- structured inputs are expected to map into PlanRequest v1 (adapter-neutral)

------------------------------------------------------------

## Style Control (Manifest + Optional Auto Style)

CAF supports two modes:

### Mode 1 — Human-set style (default)
- Human edits `sandbox/assets/manifest.json`
- Planner reads it as reference (read-only)
- The manifest MUST NOT be overwritten by any agent

### Mode 2 — Auto style (optional)
- Human passes an option like `/plan --auto-style ...`
- Planner selects a style deterministically (best-effort)
- This must not require schema changes

------------------------------------------------------------

## Hero Cats (Metadata, Not Agents)

Daily v0.2 requires a small recurring cast:

- 5–7 hero cats
- corporate-role archetypes
- consistent recognition + series continuity

Hard constraints:
- hero cats are metadata only
- no “story memory engine”
- no lore agent
- no narrative autonomy creep

------------------------------------------------------------

## Multilingual Support (Enabled: en + zh-Hans)

Daily v0.2 includes multilingual readiness.

Locked:
- Enabled languages:
  - English: `en`
  - Simplified Chinese: `zh-Hans`
- Spanish deferred

Contracts must support N languages via language-map structures.

Primary surface:
- captions (and optionally platform copy)

------------------------------------------------------------

## Promotion Toolkit (Artifact-Only)

Daily v0.2 requires a “promotion toolkit” that is safe.

Allowed:
- schedule suggestion windows
- caption variants
- hashtags
- pinned comment suggestions
- posting checklist

Not allowed:
- engagement automation
- scraping analytics
- credential handling inside repo
- cross-platform auto-posting by default

------------------------------------------------------------

## Publisher Modules (Bundle-First)

Before cloud migration, CAF must support bundle-first publisher modules for:

- YouTube
- Instagram
- TikTok
- X

Definition:
- A Publisher Adapter interface + platform adapters
- v1 adapters produce export bundles + copy artifacts + checklists
- Upload automation is optional per platform (YouTube first), opt-in, and credentials out-of-repo

------------------------------------------------------------

## Audio (Plan + Optional Assets)

Daily v0.2 requires audio support in the export bundles.

Audio is represented as:
1) Audio plan metadata (what to use / how to add audio)
2) Optional bundled audio assets (SFX stingers, optional VO)

Non-goals:
- no music generation
- no trending-audio scraping
- no automatic in-app music selection

------------------------------------------------------------

## Budget Guardrails (Hard Requirement)

Daily v0.2 assumes autonomous planning, so budget guardrails are mandatory.

Required concepts:
- per-job cost estimate (planner/provider)
- per-day/per-month caps
- deterministic refusal when over budget
- idempotent accounting (no double counting)

------------------------------------------------------------

## What Must NOT Change

Daily v0.2 is a policy milestone — NOT a rewrite of core architecture.

Non-negotiable invariants remain:

- 3-plane separation (Planner / Control Plane / Worker)
- Files-as-bus coordination
- Worker deterministic, no LLM
- Planner emits contracts only
- Ops/Distribution writes derived dist artifacts only
- No manifest overwrite
- No autonomy creep

------------------------------------------------------------

## Success Criteria (Definition of Done)

Daily v0.2 is considered “real” when:

- A human can request a daily run from Telegram
- The planner generates 3 jobs (lane mix respected)
- Ralph/Worker produce outputs deterministically
- The system produces export bundles for YT/IG/TikTok/X
- Each bundle includes:
  - final.mp4
  - captions (en + zh-Hans)
  - platform copy artifacts
  - posting checklist
  - audio_plan.json + audio_notes.txt (+ optional audio assets)
- The human can manually post each clip in < 2 minutes using the bundle
