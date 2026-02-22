# Architecture Decision Records (ADR)

This file logs key architectural decisions for Cat AI Factory.

**Authority & hierarchy**
- `docs/decisions.md` is the binding record of architectural decisions (append-only).
- `docs/master.md` captures invariants and rationale.
- `docs/architecture.md` is diagram-first and explanatory; it must align with ADRs (it does not override them).
- `docs/memory.md` is historical context only.

Format: short, dated ADR entries. Append new ADRs as decisions are made.

Guidelines:
- One decision per ADR
- Include context, decision, consequences
- Link to relevant docs (README.md, AGENTS.md, docs/master.md, docs/memory.md, docs/architecture.md)

# Example on adding new ADR:

cat >> docs/decisions.md <<'EOF'

------------------------------------------------------------

## ADR-000X — <Title>
Date: YYYY-MM-DD
Status: Proposed | Accepted | Deprecated

Context:
Decision:
Consequences:
References:

EOF

=======================================
# ADR Records
=======================================

------------------------------------------------------------

## ADR-0001 — File-based agent coordination (contracts over RPC)
Date: 2026-01-27
Status: Accepted

Context:
- Agent systems become brittle when coordination relies on UI clicks, implicit memory, or agent-to-agent RPC.
- We want reproducibility, debuggability, and clean failure modes aligned with production ML systems.

Decision:
- All agent coordination will happen via deterministic file-based contracts:
  - PRD.json → job.json → rendered artifacts
- No shared memory, no implicit state, no direct agent-to-agent RPC.

Consequences:
- Pros: reproducible runs, easier debugging, clearer auditing.
- Cons: requires explicit schema/versioning discipline and artifact organization.

References:
- docs/master.md
- docs/memory.md
- AGENTS.md

------------------------------------------------------------

## ADR-0002 — Separation of concerns: Planner vs Orchestrator vs Worker
Date: 2026-01-27
Status: Accepted

Context:
- Mixing planning (LLM), orchestration (control loop), and execution (rendering) increases risk and reduces determinism.

Decision:
- Define distinct roles:
  - Clawdbot = Planner Agent (creates job contracts)
  - Ralph Loop = Orchestrator Agent (control-plane reconciler)
  - Worker = Renderer (deterministic FFmpeg execution)

Consequences:
- Pros: strong safety boundaries, easier retries, clearer ownership.
- Cons: more components to wire, requires well-defined interfaces.

References:
- AGENTS.md
- README.md

------------------------------------------------------------

## ADR-0003 — Docker sandbox on personal Mac (no additional macOS users)
Date: 2026-01-27
Status: Accepted

Context:
- The development machine is a personal daily-use Mac.
- Strong isolation is needed without adding friction (no extra macOS user accounts).

Decision:
- Use Docker sandboxing as the primary isolation layer:
  - Mount only ./sandbox into containers (writeable)
  - Mount repo read-only when needed
  - Keep secrets out of Git

Consequences:
- Pros: good isolation, low friction, reproducible dev environment.
- Cons: must be disciplined with mounts and secrets; some UI tools may be awkward.

References:
- docs/memory.md
- README.md

------------------------------------------------------------

## ADR-0004 — Gateway security: loopback bind + token auth
Date: 2026-01-27
Status: Accepted

Context:
- Local agent gateway must not be reachable from LAN/internet.
- Token-based auth reduces risk from local processes.

Decision:
- Enforce:
  - gateway.bind = loopback
  - gateway.auth.mode = token
  - Host port mapping binds to 127.0.0.1 only
- Verified LAN unreachable.

Consequences:
- Pros: prevents accidental exposure; defense-in-depth.
- Cons: makes “UI access from host” trickier in containerized setups.

References:
- docs/memory.md

------------------------------------------------------------

## ADR-0005 — Naming: “Ralph Loop” for orchestrator
Date: 2026-01-27
Status: Accepted

Context:
- Public repo naming should sound professional and convey function.
- Avoid meme/joke naming for recruiter-facing artifacts.

Decision:
- Name the orchestrator “Ralph Loop” (control-loop / reconciler pattern).
- Use “ralph-loop” as a GitHub topic; internal shorthand “ralph” is acceptable.

Consequences:
- Pros: communicates control-plane intent; recruiter-friendly.
- Cons: minor renaming overhead in docs/code.

References:
- README.md
- AGENTS.md

------------------------------------------------------------

## ADR-0006 — Planner LLM provider strategy (AI Studio local-first; Vertex mandatory later)
Date: 2026-02-05
Status: Accepted

Context:
- PR5 needs fast LOCAL autonomy without cloud IAM/OAuth plumbing.
- The final portfolio state must demonstrate production/enterprise readiness using Vertex AI.
- Planner is the only nondeterministic component; Control Plane + Worker must remain deterministic.

Decision:
- PR5 (LOCAL): Clawdbot planning uses Gemini via Google AI Studio API key.
  - Auth via runtime-injected API key (.env / secret mount); never committed.
  - No OAuth required for PR5 model calls.
- Cloud phase (later): Vertex AI is a first-class planner provider option and is mandatory in the final portfolio state.
  - Secrets via Secret Manager; least-privilege IAM.

Consequences:
- Pros: PR5 can move quickly while preserving deterministic boundaries; portfolio includes Vertex AI later.
- Cons: two provider paths must be maintained behind an adapter interface; parity must be tested.

References:
- docs/master.md
- docs/system-requirements.md
- docs/PR_PROJECT_PLAN.md
- docs/architecture.md

------------------------------------------------------------

## ADR-0007 — Seed image generation is a planner-side nondeterministic step (never in Worker)
Date: 2026-02-05
Status: Accepted

Context:
- Seed images are needed for certain content archetypes and future pipeline quality.
- Image generation is nondeterministic and may incur cost and policy constraints.
- The Worker must remain deterministic and must not call LLM or generation APIs.

Decision:
- Seed image generation (or seed image requests) is allowed only as a Planner-side or pre-worker nondeterministic step.
- In PR5 this may exist as a stub/interface or be implemented via AI Studio, but it must NOT be implemented inside the Worker.
- Cloud phase may add Vertex AI image generation as a provider option, still outside the Worker.

Consequences:
- Pros: preserves determinism and retry-safety of the Worker; isolates nondeterminism and cost.
- Cons: requires an explicit boundary and artifact flow for generated assets (handled as inputs, not worker decisions).

References:
- docs/system-requirements.md
- docs/master.md
- docs/architecture.md
- docs/video-creation.md

------------------------------------------------------------

## ADR-0008 — Budget guardrails are required for autonomous operation (hard stop)
Date: 2026-02-05
Status: Accepted

Context:
- Planner autonomy is the target; autonomous operation must not create runaway costs.
- LLM and generation providers are paid external services; retries can multiply spend if not controlled.

Decision:
- The system must support a budget guardrail concept:
  - per-job cost estimate
  - per-day/per-month caps
  - hard-stop behavior when budget is exceeded
- Enforcement must occur before spending (planner adapter and/or control plane gate).
- Budget tracking must be idempotent and retry-safe (no double counting).

Consequences:
- Pros: prevents uncontrolled spend; makes autonomy safe to run continuously.
- Cons: requires accounting model + enforcement surface (implemented in later PRs).

References:
- docs/system-requirements.md
- docs/master.md
- docs/PR_PROJECT_PLAN.md

------------------------------------------------------------

## ADR-0009 — Telegram/mobile adapter is ingress/status-only (adapter; no authority bypass)
Date: 2026-02-05
Status: Accepted

Context:
- Mobile remote instruction and approval is desired for real-world operation.
- Remote channels are inherently untrusted and must not bypass core invariants.

Decision:
- Telegram (or any mobile UI adapter) is an adapter only:
  - writes requests into `/sandbox/inbox/`
  - reads status from `/sandbox/logs/<job_id>/state.json`
  - does not bypass the file-bus
  - does not mutate outputs or job contracts
- Any approval gates remain control-plane enforced and artifact-mediated.

Consequences:
- Pros: safe remote control path; preserves debuggability and auditability through artifacts.
- Cons: requires careful mapping of messages → inbox artifacts and state visibility (implemented in later PRs).

References:
- docs/system-requirements.md
- docs/architecture.md
- repo/tools/telegram_bridge.py

------------------------------------------------------------

## ADR-0010 — Distribution Artifact Path
Date: 2026-02-07
Status: Accepted

Context:
The Ops/Distribution layer needs a standardized, isolated location for derived artifacts (e.g., platform-specific metadata) to avoid modifying the Worker's immutable outputs.

Decision:
- The canonical root for local derived distribution artifacts will be `sandbox/dist_artifacts/<job_id>/`.
- The primary publish payload will be `sandbox/dist_artifacts/<job_id>/<platform>.json`.

Consequences:
This enforces a clean separation between the core factory's immutable outputs and the mutable, ephemeral artifacts used for external publishing. It reinforces the "files-as-bus" principle for external integrations.

References:
- docs/publish-contracts.md
- docs/architecture.md (Diagram 3)

------------------------------------------------------------

## ADR-0011 — Approval Artifact Contract
Date: 2026-02-07
Status: Accepted

Context:
An explicit, deterministic contract is needed to signal approval for publishing a job to a specific platform, enabling automated-but-gated workflows.

Decision:
- Approval artifacts will be delivered via the existing file-bus ingress path: `sandbox/inbox/`.
- The format will be `sandbox/inbox/approve-<job_id>-<platform>-<nonce>.json`.
- Minimal required fields are: `job_id`, `platform`, `approved` (boolean), `approved_at` (timestamp), `approved_by` (string), `source` (string), and `nonce` (string).

Consequences:
This reuses the existing `ADR-0009` ingress model, avoiding a new file path. It provides a clear, auditable artifact that can be used by an external orchestrator (e.g., n8n) to trigger a publish action.

References:
- docs/publish-contracts.md
- docs/decisions.md (ADR-0009)

------------------------------------------------------------

## ADR-0012 — Local Idempotency Contract for Publishing
Date: 2026-02-07
Status: Accepted

Context:
Publishing actions are not transactional and can fail, requiring a retry-safe mechanism to prevent duplicate posts from the local file system.

Decision:
- The authority for local publish state will be a state file: `sandbox/dist_artifacts/<job_id>/<platform>.state.json`.
- The presence and content of this file (recording `platform_post_id`, `post_url`, etc.) indicate a terminal state (e.g., PUBLISHED, FAILED).
- The canonical idempotency key for any publish action is the tuple `{job_id, platform}`.

Consequences:
This provides a simple, robust, and file-based idempotency lock that external publishing tools can check before executing a post.

References:
- docs/publish-contracts.md

------------------------------------------------------------

## ADR-0013 — Cloud State Mapping for Publishing (Firestore)
Date: 2026-02-07
Status: Accepted

Context:
The local file-based idempotency model needs a scalable, cloud-native equivalent for Phase 3/4 cloud workflows.

Decision:
- The canonical Firestore shape for tracking publish state will be a subcollection: `jobs/{job_id}/publishes/{platform}`.
- Each document within this subcollection, keyed by `{platform}`, will store the state (e.g., `status`, `platform_post_id`, `post_url`) for a given publish attempt.

Consequences:
This structure is idiomatic for Firestore, enabling transactional updates to a publish document that serve as a cloud-native idempotency lock. It allows for scalable, event-driven publisher functions.

References:
- docs/cloud-mapping-firestore.md
------------------------------------------------------------

## ADR-0014 — Daily multi-lane output strategy (A/B/C lanes; deterministic worker)
Date: 2026-02-08
Status: Accepted

Context:
- Daily volume (3 clips/day) is a core goal under strict budget constraints.
- Full AI video generation for all clips is too expensive; we need a scalable, deterministic approach.
- The Worker must remain deterministic and LLM-free; nondeterministic generation (if any) must stay outside the Worker.

Decision:
- CAF adopts a multi-lane production strategy for daily output:
  - Lane A: `ai_video` (premium, expensive; video generation via external provider; gated by budget)
  - Lane B: `image_motion` (cheap/scalable; seed frames + deterministic FFmpeg motion presets)
  - Lane C: `template_remix` (near-free/scalable; deterministic FFmpeg recipes using existing clips/templates)
- Default daily recommendation: A=0, B=1, C=2 (policy; adjustable via human plan brief).
- Lanes are a contract-level concept used by Planner + Ops/Distribution; the core 3-plane invariant remains unchanged.

Consequences:
- Enables high output volume without violating determinism constraints.
- Requires lane-aware planning and lane-specific expected artifact definitions.
- Lane A introduces paid-provider integration and therefore must be budget-gated and explicitly opt-in.

References:
- docs/master.md
- docs/system-requirements.md
- docs/PR_PROJECT_PLAN.md
- docs/architecture.md

------------------------------------------------------------

## ADR-0015 — Promotion toolkit is artifact-only (bundle-first; no platform posting required)
Date: 2026-02-08
Status: Accepted

Context:
- “Algorithm farming” requires repeatable promotion artifacts (copy/hashtags/schedule/checklists) while avoiding ToS-risky automation.
- Many platforms (especially IG/TikTok) have unreliable or policy-sensitive automated posting.
- The project must remain safe, deterministic, and portfolio-credible.

Decision:
- Promotion/publishing is implemented as an artifact-only toolkit by default:
  - generate platform-ready export bundles and checklists
  - do not require automated posting to be considered “complete”
- Automated posting is OPTIONAL per platform and must be:
  - explicit opt-in
  - implemented only via official APIs
  - credentials handled out-of-repo (Secret Manager in cloud later)

Consequences:
- Guarantees a usable workflow even when automation is infeasible.
- Makes manual posting fast (<2 minutes/clip) using bundles only.
- Keeps Ops/Distribution outside the factory invariant and avoids autonomy creep.

References:
- docs/PR_PROJECT_PLAN.md
- docs/architecture.md

------------------------------------------------------------

## ADR-0016 — Hero cats are metadata (not agents)
Date: 2026-02-08
Status: Accepted

Context:
- Recurring characters improve hook clarity, recognition, and series continuity.
- We want a structured “cast” without introducing story memory, lore engines, or agent autonomy.

Decision:
- Hero cats are represented as registry metadata only (e.g., `character_registry`), not as agents.
- Planner may use hero cat metadata to generate copy/series tags and maintain continuity.
- No persistent “character memory” system is introduced as a requirement.

Consequences:
- Improves content continuity while keeping the system simple and deterministic.
- Requires schemas/validators for registries, but avoids complex stateful behavior.

References:
- docs/PR_PROJECT_PLAN.md
- docs/master.md

------------------------------------------------------------

## ADR-0017 — LangGraph is planner-only (adapter; must not replace Ralph or Worker)
Date: 2026-02-08
Status: Accepted

Context:
- A LangGraph workflow demo is a desired portfolio signal.
- Introducing frameworks must not undermine the 3-plane separation or turn frameworks into foundations.

Decision:
- LangGraph (and similar orchestration frameworks) may be used only within the Planner plane as an adapter/workflow wrapper.
- LangGraph must NOT:
  - replace Ralph Loop (control-plane reconciler)
  - introduce agent-to-agent RPC across planes
  - create non-file-bus coupling

Consequences:
- Enables a clear “Google demo” story while preserving architecture invariants.
- Requires explicit boundaries and documentation to avoid framework creep.

References:
- docs/master.md
- docs/architecture.md
- docs/decisions.md (ADR-0001, ADR-0002)

------------------------------------------------------------

## ADR-0018 — Seedance (or any additional video provider) is optional and adapter-gated
Date: 2026-02-08
Status: Accepted

Context:
- Additional providers (e.g., Seedance) may be useful for Lane A experimentation.
- The core system must not depend on optional providers.

Decision:
- Any additional video generation provider is:
  - implemented behind the existing provider interface
  - config-gated and optional
  - not required for the core roadmap or local determinism guarantees
- Worker remains deterministic and does not call providers.

Consequences:
- Keeps the roadmap flexible without adding mandatory dependencies.
- Prevents provider choices from becoming architectural foundations.

References:
- docs/decisions.md (ADR-0006)
- docs/PR_PROJECT_PLAN.md

------------------------------------------------------------

## ADR-0019 — Multilingual support via language maps (enable en + zh-Hans; defer es)
Date: 2026-02-08
Status: Accepted

Context:
- Captions carry most humor and meaning; English + Simplified Chinese are required early.
- We want future China-platform readiness without multiplying operational overhead now.
- We need extensibility to N languages without repeated schema redesigns.

Decision:
- Enable exactly two languages by default:
  - English: `en`
  - Simplified Chinese: `zh-Hans`
- Contracts that carry user-facing copy should use language-map structures:
  - e.g., `{ "en": "...", "zh-Hans": "..." }` or `{ "en": [...], "zh-Hans": [...] }`
- Spanish (`es`) is explicitly deferred until there is evidence/need.

Consequences:
- Keeps early operations manageable while ensuring extensibility.
- Requires schema patterns and bundle output conventions to support multiple languages.

References:
- docs/PR_PROJECT_PLAN.md
- docs/master.md

------------------------------------------------------------

## ADR-0020 — Audio is represented as a plan + optional bundled assets (no music generation v1)
Date: 2026-02-08
Status: Accepted

Context:
- Audio strongly impacts Shorts/Reels/TikTok performance.
- Automated trending-music selection and music generation are costly and/or risk policy issues.
- We need a workflow that supports manual platform-native audio while remaining deterministic.

Decision:
- Audio is represented as:
  1) an “audio plan” (strategy + notes), and
  2) optional bundled audio assets (e.g., SFX stingers, optional VO tracks)
- v1 explicitly excludes:
  - music generation
  - automated trending-audio selection
  - scraping platform trends
- If/when TTS is added later, voiceover assets are per-language (e.g., `voiceover.en.wav`, `voiceover.zh-Hans.wav`).

Consequences:
- Preserves determinism and avoids policy-sensitive automation.
- Adds clarity to manual posting via bundle artifacts.
- Encourages platform-native audio usage while keeping the system artifact-driven.

References:
- docs/PR_PROJECT_PLAN.md
- docs/system-requirements.md

------------------------------------------------------------

## ADR-0021 — Export Bundle Layout v1 (bundle-first normative spec)
Date: 2026-02-08
Status: Accepted

Context:
- The system already defines `publish_plan.v1` as the Ops/Distribution intent contract.
- Without a normative export bundle layout, each platform module (YouTube/IG/TikTok/X) will drift in structure, naming, and required artifacts.
- Audio + multilingual requirements must map to concrete, portable file placement rules.

Decision:
- We lock the following bundle layout under:
  `sandbox/dist_artifacts/<job_id>/bundles/<platform>/v1/`

Normative tree:
```text
sandbox/dist_artifacts/<job_id>/bundles/<platform>/v1/
├── clips/<clip_id>/
│   ├── video/final.mp4                 # required (physical copy)
│   ├── captions/final.srt              # include if present
│   ├── copy/copy.en.txt                # required
│   ├── copy/copy.zh-Hans.txt           # required
│   ├── audio/audio_plan.json           # required
│   ├── audio/audio_notes.txt           # required
│   └── audio/assets/                   # optional: referenced assets
└── checklists/posting_checklist_<platform>.txt  # required
```

Normative rules:
1. Bundles are **derived Ops/Distribution artifacts** and MUST NOT modify worker outputs.
2. Bundle artifacts MUST NOT contain credentials, secrets, tokens, cookies, or OAuth material.
3. Bundles are **bundle-first**; posting automation is optional and outside the scope of this spec.
4. `video/final.mp4` MUST be a physical copy (no symlinks). If `captions/final.srt` is included, it MUST also be a physical copy.
5. `clips/<clip_id>/` MUST use a filesystem-safe clip_id (recommendation: `clip-001`, `clip-002`, ...).
6. v1 export bundle copy artifacts MUST include copy/copy.en.txt and copy/copy.zh-Hans.txt

Consequences:
- Publisher adapters can rely on a fixed, versioned bundle layout.
- Manual + future automated workflows operate with consistent artifacts.
- Prevents bundle format drift across platforms.
- Bundles are portable and safe to share with human operators.

References:
- docs/publish-contracts.md
- docs/system-requirements.md
- docs/architecture.md
- docs/decisions.md (ADR-0010..ADR-0013)


------------------------------------------------------------

## ADR-0022 — Deterministic watermark overlay (Worker; repo-owned asset; no schema changes)
Date: 2026-02-09
Status: Accepted

Context:
- CAF is a public, bundle-first content factory; attribution should survive reposts.
- Visual watermarking is a deterministic media transform and therefore belongs in the Worker plane.
- We must reduce repost theft without introducing nondeterminism, schema churn, or autonomy creep.

Decision:
- The Worker applies a deterministic watermark overlay to the rendered video output (`final.mp4`).
- No schema changes are introduced (job schema and publish_plan schema unchanged).
- The watermark asset is a repo-owned static file (e.g., `repo/assets/watermarks/caf_watermark.png`), not generated per job.
- Output paths remain unchanged; only media content changes:
  - `/sandbox/output/<job_id>/final.mp4` remains the canonical output path.
- Watermark placement/appearance is deterministic (fixed padding, opacity, and scaling rule).
- Per-platform placement rules are deferred; v1 uses a single default placement.

Consequences:
- Attribution persists in the pixels, improving survivability across reposts.
- Bundles (ADR-0021) automatically include watermarked media because they copy `final.mp4`.
- Determinism is preserved; no LLM usage is added to Worker; no external APIs involved.
- Future enhancements (e.g., slight periodic drift) require a new ADR if they change determinism semantics.

References:
- docs/master.md
- docs/system-requirements.md
- docs/architecture.md
- docs/publish-contracts.md
- docs/decisions.md (ADR-0001, ADR-0002, ADR-0021)


------------------------------------------------------------

## ADR-0023 — Deterministic audio stream in Worker outputs (no silent MP4)
Date: 2026-02-10
Status: Accepted

Context:
- Worker outputs currently produce `final.mp4` with no audio stream (silent MP4).
- This is a production blocker for Shorts/Reels/TikTok workflows and affects Lane B (image_motion) and Lane C (template_remix), and likely all lanes.
- The Worker must remain deterministic and must not use LLMs or network calls.

Decision:
- The Worker MUST ensure `sandbox/output/<job_id>/final.mp4` always contains an audio stream, deterministically.
- Priority order:
  1) If the job contract provides `audio.audio_asset` (sandbox-relative), use it as the audio source.
  2) Else, if the background video input contains an audio stream, preserve/passthrough it.
  3) Else, inject deterministic silence (e.g., FFmpeg `anullsrc`) so the output always has audio.
- Audio mux/encode settings must be deterministic (fixed codec/sample rate/channel layout/bitrate).
- Any referenced audio assets must be sandbox-relative and validated to be within the sandbox root.

Consequences:
- Eliminates “silent MP4” outputs and produces publish-ready media across all lanes.
- Preserves the Worker invariant: deterministic, retry-safe, no LLM/network.
- Introduces an optional job contract field (`audio.audio_asset`) and associated validation; any schema/contract evolution must remain minimal and reviewable.

References:
- docs/master.md
- docs/system-requirements.md
- docs/PR_PROJECT_PLAN.md
- docs/architecture.md
- AGENTS.md


------------------------------------------------------------

## ADR-0024 — Lanes are non-binding hints; schema must remain permissive
Date: 2026-02-11
Status: Accepted

Context:
- CAF uses multiple production lanes (ai_video, image_motion, template_remix) to manage cost and routing.
- Real clips are often hybrid or “mixed lane” workflows.
- Strict lane-based schema gating (if/then/else forbids) blocks experimentation and forces premature rigidity.

Decision:
- `job.lane` is an OPTIONAL hint, not a gate.
- `job.json` MUST remain valid even if it includes fields from multiple lanes.
- The JSON Schema MUST remain permissive:
  - validate shape/types
  - do NOT add lane-based conditional rules like:
    - "if lane=image_motion then require X else forbid X"
- The Worker enforces only what is required for the chosen deterministic recipe at runtime.
- Worker routing policy:
  - Prefer explicit lane routing if lane is present AND required blocks exist.
  - Otherwise infer route from fields:
    - if `image_motion` exists -> image_motion recipe
    - else -> standard render path
  - If lane claims a recipe but required inputs are missing:
    - prefer graceful fallback when safe
    - fail-loud only when unsafe (e.g., path traversal, missing required asset)

Consequences:
- Preserves creativity and hybrid workflows.
- Keeps schemas stable and avoids brittle conditional validation.
- Maintains deterministic runtime behavior while allowing flexible planning.

References:
- docs/PR_PROJECT_PLAN.md
- docs/system-requirements.md
- docs/architecture.md


------------------------------------------------------------

## ADR-0025 — Series continuity layer v1 (hero registry + bible + ledger + creativity controls + audio allowlist)
Date: 2026-02-11
Status: Accepted

Context:
- CAF needs higher quality comedy, consistent character voice, and ongoing storyline continuity for daily Shorts/Reels/TikTok output.
- LLM planning can drift canon over time without a structured continuity substrate.
- CAF must remain deterministic and portfolio-ready:
  - Worker must remain deterministic and LLM-free.
  - Canon must be reviewable, file-based, and reproducible.
- Audio is both a quality lever and a major copyright/Content-ID risk area.

Decision:
CAF introduces a minimal, deterministic “series layer” above `job.json`, consisting of:
1) Hero Cats Registry (metadata only)
2) Series Bible (tone rules + canon constraints)
3) Episode Ledger (episode-by-episode continuity record)
4) Job Creativity Controls (planner-only contract knobs)
5) Audio allowlist manifest for license-safe background beds

Rules:
- These artifacts are Planner/Control-plane inputs only.
- Worker remains deterministic and unchanged by these concepts.
- Canon stability model:
  - The Planner may propose new facts, new heroes, or new relationships.
  - Only committed file artifacts become canon.
  - No hidden “memory engine” is required or allowed as an authority source.

Contract posture:
- Provider-agnostic:
  - No Gemini-specific or Vertex-specific knobs in contracts.
- Creativity controls are contract-level, optional, and planner-only:
  - `creativity.mode`: canon | balanced | experimental
  - optional `creativity.canon_fidelity`: high | medium
- Audio policy:
  - Planner may only select background audio beds from a repo-owned, license-safe allowlist manifest.
  - No trending/copyright music selection.
  - No scraping platform trends.

Consequences:
- Improves series continuity, character voice consistency, and recurring gags without autonomy creep.
- Keeps continuity explicit, reviewable, and reproducible via file artifacts.
- Reduces copyright risk and supports consistent audio quality across platforms.
- Preserves all core invariants: 3-plane separation, deterministic Worker, files-as-bus.

References:
- docs/PR_PROJECT_PLAN.md
- docs/system-requirements.md
- docs/architecture.md
- docs/master.md
- AGENTS.md


------------------------------------------------------------

## ADR-0026 — Phase 7 cloud migration posture (serverless, event-driven; preserve invariants)
Date: 2026-02-11
Status: Proposed

Context:
- CAF is currently local-first (docker-compose + filesystem bus).
- We want a Phase 7 migration to GCP that is serverless and event-driven, but must preserve:
  - Planner → Control Plane → Worker separation
  - determinism in Control Plane + Worker
  - “files-as-bus” semantics (explicit, durable artifacts) even when artifacts live in cloud storage/state
- External interfaces (Telegram) must remain adapters and must not block.

Decision:
- Phase 7 cloud posture is serverless + event-driven on GCP:
  - Cloud Run for stateless services (Receiver, Orchestrator, Worker)
  - Cloud Tasks for async bridging and retries
  - Firestore for durable job contract/state (control-plane truth)
  - GCS for immutable assets and outputs
- Preserve invariants:
  - Planner is the only nondeterministic component (LLM).
  - Orchestrator + Worker remain deterministic and retry-safe.
  - Ops/Distribution remains outside the factory; it consumes outputs and produces posting artifacts/URLs.

Consequences:
- Clean cloud portfolio story without rewriting core semantics.
- Requires explicit cloud mappings for:
  - “job contract snapshot” storage (Firestore)
  - immutable artifacts (GCS)
  - deterministic reconciliation (Orchestrator service)
- Adds infra surface area (IAM, service-to-service auth) but keeps responsibilities separated.

References:
- docs/PR_PROJECT_PLAN.md
- docs/system-requirements.md
- docs/architecture.md
- docs/master.md

------------------------------------------------------------

## ADR-0027 — Telegram Receiver must ACK fast; async bridge via Cloud Tasks
Date: 2026-02-11
Status: Proposed

Context:
- Telegram webhooks can time out if we do synchronous planning/orchestration in the request path.
- Telegram is untrusted ingress; it must remain an adapter that writes “intent” without executing the factory.
- We need retries and backpressure without losing messages.

Decision:
- Telegram webhook Receiver (Cloud Run) must:
  - validate/auth (allowed user id)
  - translate message → canonical “inbox-like” request record
  - enqueue a Cloud Tasks task for downstream processing
  - return HTTP 200 quickly (ACK fast)
- Cloud Tasks is the required async bridge with retries between:
  Receiver → Planner entrypoint.

Consequences:
- Prevents Telegram timeouts and removes planning from the request thread.
- Adds at-least-once delivery semantics; downstream processing must be idempotent by a deterministic key
  (e.g., `{source=telegram, update_id}`).
- Keeps adapter boundary intact (no authority bypass).

References:
- docs/system-requirements.md (Telegram adapter requirement)
- docs/architecture.md (Ops/Ingress outside factory authority)
- docs/decisions.md (ADR-0009)

------------------------------------------------------------

## ADR-0028 — Planner becomes a LangGraph workflow on Cloud Run (planner-only; durable contract state)
Date: 2026-02-11
Status: Proposed

Context:
- We want a recruiter-facing “workflow orchestration” story (LangGraph) without replacing Ralph Loop or Worker.
- In cloud, the Planner must produce durable, reviewable job contracts and continuity artifacts.
- Planner is nondeterministic; outputs must be validated deterministically before becoming canonical state.

Decision:
- The Planner is hosted as a LangGraph workflow on Cloud Run, planner-plane only.
- Minimum workflow stages:
  1) Analyze brief (LLM)
  2) Draft contract (LLM)
  3) Validate schema (deterministic)
  4) Persist job contract snapshot/state (deterministic) in Firestore
- The Planner must not execute FFmpeg or orchestration; it writes contracts/state only.

Consequences:
- Preserves ADR-0017 (LangGraph planner-only) while making it a first-class cloud component.
- Requires deterministic schema validation in the Planner service before persisting canonical state.
- Enables auditability: Firestore holds the canonical contract snapshot and status history.

References:
- docs/system-requirements.md
- docs/architecture.md
- docs/decisions.md (ADR-0017)
- docs/PR_PROJECT_PLAN.md

------------------------------------------------------------

## ADR-0029 — Cloud storage/state mapping (Firestore as contract authority; GCS as immutable artifact store)
Date: 2026-02-11
Status: Proposed

Context:
- Local CAF uses the filesystem as the bus and source of truth for artifacts.
- In cloud we need durable equivalents:
  - contract/state authority
  - immutable artifacts (assets, outputs)
  - idempotency and retries
- We must preserve lane separation and prevent “hidden mutation” of outputs.

Decision:
- Firestore is the source of truth for job contract snapshots + job state:
  - `jobs/{job_id}` stores:
    - canonical job contract snapshot (schema-valid JSON or a reference to a versioned blob)
    - lane hint (optional) + derived routing metadata
    - status/state machine fields (deterministic)
- GCS stores immutable artifacts:
  - `gs://<bucket>/assets/...` (inputs)
  - `gs://<bucket>/outputs/<job_id>/final.mp4` (and result/captions)
  - optional: `gs://<bucket>/logs/<job_id>/...` for append-only logs
- No service may mutate an existing output artifact in-place; new attempts write a new versioned object key or overwrite only via deterministic “atomic publish” step.

Consequences:
- Clear authority split:
  - Firestore = contract/state truth
  - GCS = immutable artifacts
- Enables deterministic reconciliation + replay.
- Requires explicit object naming/versioning rules and IAM boundaries.

References:
- docs/architecture.md
- docs/system-requirements.md
- docs/PR_PROJECT_PLAN.md
- docs/decisions.md (ADR-0013)

------------------------------------------------------------

## ADR-0030 — Signed URL delivery is Ops/Distribution output (factory produces artifacts only)
Date: 2026-02-11
Status: Proposed

Context:
- We want a “manual posting” workflow in cloud: retrieve media easily without giving broad bucket access.
- Signed URLs are a distribution convenience and an external-facing artifact.
- Ops/Distribution must remain outside the factory invariant.

Decision:
- The core factory (Planner/Orchestrator/Worker) produces artifacts only (job state + GCS objects).
- Generating and exposing GCS Signed URLs is the responsibility of Ops/Distribution (outside factory), which:
  - reads output object references
  - creates signed URLs (time-bounded)
  - writes derived distribution artifacts (and/or returns them to the human operator)
- Signed URL artifacts must never be stored in Firestore job contract snapshots; they live in dist artifacts.

Consequences:
- Keeps the factory clean and deterministic.
- Prevents accidental exposure of long-lived access paths.
- Fits the bundle-first/manual-posting posture in cloud.

References:
- docs/architecture.md (Ops/Distribution outside factory)
- docs/system-requirements.md
- docs/decisions.md (ADR-0010..ADR-0012, ADR-0015)

------------------------------------------------------------

## ADR-0031 — Cloud asset posture: GCS for runtime media, Artifact Registry for containers, Git for contracts
Date: 2026-02-11
Status: Proposed

Context:
- CAF is local-first with /sandbox/assets/** used by the deterministic Worker.
- In Phase 7, Cloud Run needs access to runtime media assets without committing large or sensitive files to the public repo.
- Artifact Registry is intended for container images, not content libraries.

Decision:
- Store runtime media assets (mp4/png/wav/templates/backgrounds/seed frames) in GCS under a stable prefix:
  - gs://<bucket>/assets/** (inputs)
  - gs://<bucket>/output/<job_id>/** (worker outputs)
- Store container images in Artifact Registry only.
- Store code, schemas/contracts, and small license-safe demo fixtures in GitHub.
- Cloud Build is triggered by GitHub merges to build/push images and deploy Cloud Run services.

Consequences:
- Keeps the public repo lightweight and safe while enabling scalable runtime access.
- Preserves the “files-as-bus” mental model via an explicit local→GCS mapping.
- Requires IAM boundaries so Cloud Run services have least-privilege access to the relevant GCS prefixes.

References:
- docs/master.md
- docs/architecture.md (Phase 7 mapping)
- docs/system-requirements.md (SEC-01, SEC-03)
- docs/decisions.md (ADR-0026..ADR-0030)

------------------------------------------------------------

## ADR-0032 — CrewAI is planner-only and contained inside a single LangGraph node
Date: 2026-02-11
Status: Proposed

Context:
- CAF requires a recruiter-facing workflow orchestration story (LangGraph) while preserving strict 3-plane separation.
- We also want to showcase multi-agent planning quality (CrewAI) for portfolio value.
- Uncontained multi-agent frameworks can accidentally become a “control plane” and violate determinism + files-as-bus semantics.
- The Worker and Control Plane must remain deterministic and LLM-free.

Decision:
- CrewAI is REQUIRED for the portfolio, but it MUST remain planner-plane only.
- CrewAI MUST be contained inside exactly one LangGraph node (or subgraph) within the Planner workflow.
- CrewAI MUST NOT:
  - replace Ralph Loop
  - perform orchestration retries
  - invoke the Worker
  - write artifacts directly
- All canonical artifact writes MUST occur only in deterministic LangGraph nodes:
  - schema validation
  - normalization
  - commit/write steps

Consequences:
- Enables a clean “LangGraph + CrewAI” portfolio demo without compromising CAF invariants.
- Prevents framework creep where CrewAI becomes a hidden orchestrator.
- Forces clear deterministic gates:
  - CrewAI output must be schema-valid JSON or fail closed.
- Keeps Control Plane and Worker unchanged and deterministic.

References:
- docs/master.md
- docs/architecture.md
- docs/system-requirements.md (FR-02, FR-03, FR-15, FR-19)
- docs/decisions.md (ADR-0001, ADR-0002, ADR-0017)
- AGENTS.md

------------------------------------------------------------

## ADR-0033 — PlanRequest v1 (Ingress contract; adapter-neutral)
Date: 2026-02-11
Status: Proposed

Context:
- CAF currently accepts planning intent via Telegram inbox artifacts (daily_plan, /plan).
- We want to support additional front ends (Coze web UI, future web forms) without rewriting the Planner.
- CAF must remain contract-first and deterministic at boundaries.
- Ingress adapters must remain replaceable and must not become authorities.
- Telegram is functional but not ideal for guided, structured inputs (heroes/tone/continuity knobs).

Decision:
- Introduce a versioned ingress request contract: PlanRequest v1.
- PlanRequest v1 is adapter-neutral:
  - Telegram, Coze, and future UIs produce the same schema.
- PlanRequest v1 is NOT a job contract and does not replace job.json.
  - Planner consumes PlanRequest and produces job.json.
- PlanRequest is treated as untrusted input:
  - strict schema validation
  - deterministic normalization (defaults, enum clamping, sorting)
  - safe string length limits
- PlanRequest v1 is planner-plane input only:
  - it must not be consumed by Worker
  - it must not become a coordination channel
- The adapter may provide a nonce, but CAF remains the authority for:
  - job_id generation
  - contract commit decisions
  - canonical storage paths (local now; Firestore/GCS in Phase 7)

Consequences:
- Multiple UIs can exist without changing planner semantics.
- Cloud migration is simpler: local inbox and cloud ingress both map to PlanRequest v1.
- Enables guided UX (Coze) while keeping CAF as the authority.
- Requires a small deterministic normalization layer in the Planner.

References:
- docs/master.md
- docs/system-requirements.md (FR-01, FR-09, SEC-01)
- docs/architecture.md (files-as-bus + adapter boundaries)
- AGENTS.md (Ingress adapter write boundaries)

------------------------------------------------------------

## ADR-0034 — EpisodePlan v1 (Planner-only planning artifact; schema-validated)
Date: 2026-02-11
Status: Proposed

Context:
- CAF currently produces job.json directly from planning inputs.
- As continuity (heroes, series bible, episode ledger), lanes, and creativity controls expand,
  the Planner needs an explicit intermediate artifact that is:
  - reviewable
  - schema-valid
  - reproducible
  - independent of any specific framework (LangGraph, CrewAI)
- We also want to showcase agent orchestration quality (CrewAI) without allowing it to directly
  mutate contracts or bypass deterministic gates.

Decision:
- Introduce a versioned planner-only planning artifact: EpisodePlan v1.
- EpisodePlan v1 is a deterministic, schema-validated intermediate plan that sits above job.json.
- EpisodePlan v1 is produced by the Planner and then deterministically transformed into job.json.

Hard constraints:
- EpisodePlan v1 is Planner-plane only:
  - Worker must never read it
  - Control Plane must never require it for execution correctness
- All writes of EpisodePlan v1 must occur only as committed artifacts (not hidden memory).
- CrewAI may be used to draft EpisodePlan v1, but:
  - CrewAI must be contained inside one Planner node (or subgraph)
  - deterministic validation + commit gates must be outside CrewAI
- EpisodePlan v1 must be strict JSON:
  - schema-validated
  - fail-closed on invalid output
  - deterministic normalization applied before commit

Canonical content of EpisodePlan v1 (conceptual):
- selected lane mix (A/B/C)
- selected hero ids (from hero_registry)
- continuity hooks (derived from series bible + ledger)
- beat outline (setup → gag → payoff)
- captions/copy intent (en + zh-Hans)
- asset intent (seed frames needed, template keys, etc.)
- job generation parameters (duration, style key, etc.)

Consequences:
- Improves planner quality and debuggability:
  reviewers can inspect EpisodePlan separately from job.json.
- Allows CrewAI showcase without contaminating deterministic boundaries.
- Makes LangGraph adoption cleaner (graph nodes can pass EpisodePlan between deterministic gates).
- Adds an extra artifact type to maintain (schema + examples).

References:
- docs/master.md (series continuity layer posture)
- docs/system-requirements.md (FR-01, FR-14, FR-15, FR-18)
- docs/architecture.md (Planner reference inputs)
- AGENTS.md (Planner write boundary; files-as-bus)
- docs/decisions.md (ADR-0032 CrewAI containment requirement)

------------------------------------------------------------

## ADR-0035 — Coze is UI-only (PlanRequest in; CAF remains source of truth)
Date: 2026-02-11
Status: Proposed

Context:
- Telegram commands are functional but not ideal for guided inputs (heroes, tone, continuity knobs).
- Coze can provide a better guided UX (web UI / form-filler) for structured planning requests.
- CAF must remain deterministic, contract-first, and vendor-neutral.
- Continuity logic (series bible, episode ledger, hero registry reasoning) must remain inside CAF Planner,
  not inside a third-party UI tool.

Decision:
- Coze is permitted as an optional guided-input front end only.
- Coze must be treated as a replaceable adapter, not an authority.
- Coze produces PlanRequest v1 only (never job.json).
- Coze must not become a required runtime dependency:
  - Telegram remains supported
  - PlanRequest v1 is the stable contract for all UIs
- Coze must not store or own continuity canon:
  - canon remains file-based artifacts in CAF
  - LangGraph Planner is the continuity reasoning engine

Consequences:
- Enables a better UX without breaking CAF invariants.
- Prevents vendor lock-in and continuity drift.
- Keeps cloud migration clean: Coze wiring happens after PR-23 (cloud artifact layout).

References:
- docs/master.md
- docs/system-requirements.md (FR-01, FR-09, SEC-01)
- docs/architecture.md (adapter boundary + planner reference inputs)
- docs/decisions.md (ADR-0033 PlanRequest v1)
- AGENTS.md

------------------------------------------------------------

## ADR-0036 — n8n is Ops Workflow Automation (Cloud Tasks remains internal queue)
Date: 2026-02-11
Status: Proposed

Context:
- Phase 7 migrates CAF to Cloud Run + Cloud Tasks + Firestore/GCS.
- CAF requires:
  - durable retries/backoff for internal work steps
  - a clean human approval + manual publish workflow
- Cloud Tasks is the correct primitive for internal step execution.
- n8n is valuable for human workflow automation and integrations, but it must not become the orchestrator.

Decision:
- Cloud Tasks is the internal CAF queue for all “do work” steps:
  - planner invocation
  - control-plane reconciliation
  - worker rendering
  - (later) publisher steps
- n8n is permitted only as an Ops/Distribution workflow layer:
  - notifications
  - human approval buttons
  - manual publish triggers
  - integrations (Sheets/Notion/etc.)
- n8n must not replace:
  - Ralph Loop semantics
  - Cloud Tasks retry/backoff authority
  - CAF contract/state authority (Firestore/GCS)
- n8n interactions with CAF must be via explicit, idempotent endpoints or artifacts.

Consequences:
- Keeps CAF production semantics correct and portfolio-grade.
- Allows rapid iteration on human workflow without rewriting CAF core.
- Prevents “workflow tool drift” from becoming architecture drift.

References:
- docs/master.md
- docs/system-requirements.md (FR-10, FR-11, NFR-02)
- docs/architecture.md (Phase 7 mapping)
- docs/decisions.md (ADR-0031 Cloud asset posture)
- AGENTS.md

------------------------------------------------------------

## ADR-0037 — Cloud Tasks is the async bridge (Receiver must ACK fast; no Telegram timeouts)
Date: 2026-02-11
Status: Proposed

Context:
- Telegram webhooks have strict timeouts.
- In Phase 7, CAF must run in a serverless, event-driven architecture on GCP.
- The Receiver is an ingress adapter, not an execution engine.
- Planner work (LangGraph + LLM calls) is nondeterministic and can be slow.
- CAF requires durable retries, backoff, and at-least-once delivery semantics for ingress-triggered planning.

Decision:
- The Telegram Webhook Receiver MUST:
  - authenticate the sender
  - enqueue an async work item
  - return HTTP 200 immediately (fast ACK)
- Cloud Tasks is the required async bridge between Receiver and Planner:
  - retries + backoff
  - explicit throttling
  - durable delivery
  - clear auditability
- The Receiver MUST NOT call the Planner synchronously.
- The Receiver MUST NOT write job/output/log artifacts directly.

Consequences:
- Prevents Telegram timeouts and duplicate planning due to client retries.
- Provides production-grade durability for planner invocation.
- Keeps CAF aligned with its “adapter only” posture for ingress.

References:
- docs/master.md (Phase 7 principles)
- docs/system-requirements.md (FR-09, NFR-02)
- docs/architecture.md (Phase 7 lifecycle)
- AGENTS.md (Receiver + Cloud Tasks roles)
- docs/decisions.md (ADR-0031 Cloud asset posture)

------------------------------------------------------------

## ADR-0038 — Phase 7 infra provisioning is deferred to a dedicated Terraform PR
Date: 2026-02-15
Status: Accepted

Context:
- Phase 7 introduces cloud mapping (GCS + Firestore) and Cloud Run stubs.
- The repo is public and must avoid committing real project IDs, buckets, or secrets.
- We want PR-sized, reviewable changes without conflating mapping docs with live infra.

Decision:
- Phase 7 PRs up through PR-29 are docs + local stubs only (no live GCP provisioning).
- Terraform-based live provisioning is deferred to a dedicated infra PR (PR-30).
- Terraform configs must use placeholders only; real values are injected at runtime.

Consequences:
- Keeps Phase 7 PRs reviewable and aligned with public-repo posture.
- Live cloud deployment becomes explicit and PR-scoped (required in PR-30).
- Actual GCP validation is deferred to the infra PR.

References:
- docs/PR_PROJECT_PLAN.md
- docs/master.md
- docs/architecture.md
- docs/system-requirements.md (SEC-01, SEC-03)

------------------------------------------------------------

## ADR-0039 — Planner-side AI template generation is allowed (Worker remains deterministic)
Date: 2026-02-15
Status: Accepted

Context:
- Lane B/C outputs can look too similar when template variety is low.
- We want higher novelty without violating determinism or moving generation into the Worker.
- Vertex AI is already planned as a planner-side provider (ADR-0006, PR-25).

Decision:
- AI-generated template assets are allowed as a Planner-side, nondeterministic step.
- Generated templates are treated as inputs to deterministic rendering (Worker unchanged).
- The Worker MUST NOT call generation APIs and MUST remain deterministic.
- Generated assets must be stored as explicit artifacts (no hidden state).

Consequences:
- Increases visual novelty while preserving the three-plane invariant.
- Requires budget guardrails and provider gating (planner-side).
- Does not change canonical output paths or Worker recipes.

References:
- docs/master.md
- docs/system-requirements.md
- docs/PR_PROJECT_PLAN.md
- docs/decisions.md (ADR-0006, ADR-0007, ADR-0014, ADR-0017, ADR-0024)

------------------------------------------------------------

## ADR-0040 — Media Stack v1 contracts (planner authority preserved; Worker executes stages)
Date: 2026-02-16
Status: Accepted

Context:
- CAF needs clearer media-stage contracts for frame/audio/edit/render while preserving three-plane authority.
- Planner remains the only author of execution intent (`job.json` authority).
- Worker can be multi-stage internally, but must remain deterministic and output-bound.

Decision:
- Adopt Media Stack v1 contract families:
  - `frame_manifest.v1`
  - `audio_manifest.v1`
  - `timeline.v1`
  - `render_manifest.v1`
- These manifests are Worker-stage artifacts and MUST NOT bypass `job.json` as execution authority.
- Planner may define stage intent and options in contract form; Control Plane schedules deterministically; Worker executes deterministically.
- Worker write boundary remains unchanged:
  - `sandbox/output/<job_id>/**` only.

Consequences:
- Improves inspectability and testability of media pipeline stages.
- Preserves deterministic execution and current filesystem boundaries.
- Enables future engine upgrades (Comfy/ElevenLabs/etc.) without authority drift.

References:
- docs/master.md
- docs/architecture.md
- AGENTS.md
- docs/system-requirements.md

------------------------------------------------------------

## ADR-0041 — Video Analyzer v1 is planner-side metadata canon (no media authority)
Date: 2026-02-16
Status: Accepted

Context:
- CAF needs reusable pattern extraction from reference videos (timing, pacing, camera language, loop cues).
- This should enrich planning without introducing nondeterminism into Worker runtime.

Decision:
- Introduce planner-side Video Analyzer v1 contracts:
  - `video_analysis.v1`
  - `video_analysis_index.v1`
  - optional planner query/result contracts for deterministic retrieval.
- Canon storage:
  - schemas under `repo/shared/*.schema.json`
  - metadata instances under `repo/canon/demo_analyses/**`.
- Hard rule:
  - store metadata/patterns only; no copyrighted source media in repo canon.
- Worker MUST NOT read analyzer artifacts for runtime authority.

Consequences:
- Enables repeatable planning patterns and future RAG/index lookup.
- Keeps Worker deterministic and independent from analyzer state.

References:
- docs/master.md
- docs/architecture.md
- AGENTS.md

------------------------------------------------------------

## ADR-0042 — Dance Swap v1 lane for deterministic choreography-preserving recast
Date: 2026-02-16
Status: Accepted

Context:
- Prompt/video-reference generation alone cannot reliably deliver exact choreography plus stable hero identity.
- Recast quality requires explicit deterministic edit artifacts (tracking/masks/loop bounds).

Decision:
- Add Dance Swap v1 as a deterministic lane focused on choreography-preserving replacement.
- Standardize planner/control-visible artifacts (schema names finalised in contracts PR):
  - loop bounds
  - tracked subject IDs
  - per-frame mask references
  - optional flow/beat metadata.
- Worker performs deterministic replacement/compositing only from explicit artifacts.
- Lane policy remains permissive/non-binding per ADR-0024.

Consequences:
- Aligns implementation with real VFX-style constraints instead of prompt-only retries.
- Increases quality ceiling for hero recast while preserving invariants.

References:
- docs/master.md
- docs/decisions.md (ADR-0014, ADR-0024)
- docs/architecture.md

------------------------------------------------------------

## ADR-0043 — External model/tool strategy Mode B default (deterministic daily + optional premium generation)
Date: 2026-02-16
Status: Accepted

Context:
- CAF needs quality output with cost control and reproducibility.
- Fully hosted video generation for all daily output is expensive and less deterministic.

Decision:
- Adopt Mode B as default strategy:
  - daily output path prioritizes deterministic Worker assembly/editing from explicit assets/contracts
  - optional premium hosted generation is adapter-gated and non-mandatory.
- Hosted providers remain optional per ADR-0018.
- Contract surfaces must stay stable; adapters are swappable.

Consequences:
- Preserves production cadence and budget predictability.
- Keeps portfolio architecture reproducible and contract-first.

References:
- docs/decisions.md (ADR-0018, ADR-0026)
- docs/system-requirements.md

------------------------------------------------------------

## ADR-0044 — External HITL recast boundary (Viggle-class tools are Ops/Distribution, not internal Worker)
Date: 2026-02-16
Status: Accepted

Context:
- External recast tools can accelerate quality, but must not blur factory boundaries or hide manual steps.
- CAF requires explicit, auditable HITL state transitions.

Decision:
- Model Viggle-class recast as external Ops/Distribution HITL flow, not as an internal Worker engine.
- Export packs are written only to:
  - `sandbox/dist_artifacts/<job_id>/viggle_pack/**`
- Re-ingest of externally produced media must happen via explicit ingress artifacts under:
  - `sandbox/inbox/*.json` (metadata pointer contract), then deterministic fetch/copy step by approved adapter.
- Worker remains deterministic finishing only and never invokes external recast services.

Consequences:
- Preserves three-plane and files-as-bus invariants.
- Makes manual/external steps visible, auditable, and retry-manageable.

References:
- docs/master.md
- AGENTS.md
- docs/decisions.md (ADR-0015, ADR-0026, ADR-0030)

------------------------------------------------------------

## ADR-0045 — QC policy/report contracts are production routing authority
Date: 2026-02-18
Status: Accepted

Context:
- CAF quality iteration needs explicit, reproducible routing decisions instead of ad-hoc tuning spread across Planner/Controller/Worker.
- Existing quality artifacts are useful but not yet normalized into one deterministic routing contract.

Decision:
- Introduce a controller-consumed policy contract:
  - `repo/shared/qc_policy.v1.json`
- Introduce a normalized deterministic per-attempt report:
  - `sandbox/logs/<job_id>/qc/qc_report.v1.json`
- Controller routing decisions (`pass`, `retry`, `fallback`, `needs_human_review`) MUST be derived deterministically from:
  - `qc_policy.v1`
  - `qc_report.v1`
  - explicit retry budget state
- Planner and OpenClaw MAY propose changes, but MUST NOT bypass policy authority at runtime.

Consequences:
- Quality routing becomes auditable, replayable, and testable.
- Threshold/policy updates become data changes instead of code-path drift.
- Enables objective promotion gates from lab experiments into production policy.

References:
- docs/system-requirements.md (FR-28.18)
- docs/PR_PROJECT_PLAN.md (PR-34.9, PR-34.9d)
- docs/architecture.md

------------------------------------------------------------

## ADR-0046 — OpenClaw lab mode is advisory by default; authority trials are guarded and reversible
Date: 2026-02-18
Status: Accepted

Context:
- Better video quality requires agentic experimentation, but production reliability requires deterministic authority boundaries.
- Allowing direct autonomous authority without safeguards risks policy drift and non-repeatable routing.

Decision:
- Establish two explicit quality operating modes:
  - LAB mode: OpenClaw runs experiment loops and emits advisory artifacts
  - PRODUCTION mode: controller enforces deterministic policy/routing
- OpenClaw default output is advisory only (example contract family: `qc_route_advice.v1`).
- Any advisory-to-authority path MUST be:
  - feature-flagged
  - default OFF
  - bounded to approved experiments/cohorts
  - reversible via one config switch
- OpenClaw MUST NOT directly modify production code or bypass controller routing contracts.

Consequences:
- Preserves deterministic production behavior while enabling rapid quality discovery.
- Creates a safe path to test smarter routing without permanent authority drift.

References:
- docs/system-requirements.md (FR-28.19)
- docs/PR_PROJECT_PLAN.md (PR-34.9a, PR-34.9b, PR-34.9e)
- docs/briefs/GUARDRAILS.md

------------------------------------------------------------

## ADR-0047 — Free-first engine posture with adapter-based escalation to paid engines
Date: 2026-02-18
Status: Accepted

Context:
- CAF needs higher quality ceilings while controlling operational cost and avoiding hard dependency lock-in.
- Quality stacks span multiple engines (frame/motion/video/audio/editor), and providers will evolve.

Decision:
- Adopt a free/open-source-first default stack where practical, with adapter seams for optional paid engines.
- Keep provider-specific logic behind explicit adapter contracts so planner/controller/worker contracts remain stable.
- Paid engines may be enabled per policy/experiment; they are optional capabilities, not architectural authority.

Consequences:
- Improves sustainability and portability.
- Preserves contract stability while allowing quality-focused engine upgrades.

References:
- docs/system-requirements.md (FR-28.20)
- docs/PR_PROJECT_PLAN.md (PR-35)

------------------------------------------------------------

## ADR-0048 — Motion-conditioned, frame-first quality path for dance/identity-critical generation
Date: 2026-02-18
Status: Accepted

Context:
- Prompt-first video generation remains unreliable for two critical goals:
  - hero identity consistency
  - choreography/motion fidelity to a reference dance.
- CAF already has deterministic analyzer and QC foundations that can support a stronger contract-first approach.

Decision:
- Adopt motion-conditioned, frame-first generation as the preferred architecture for dance/identity-critical jobs:
  - sample dance -> deterministic pose/motion contract -> pose-conditioned hero keyframes -> animation -> deterministic FFmpeg assembly.
- Introduce a first-class deterministic motion analyzer contract family (planner-side/offline generation, worker-independent authority).
- Standardize CAF-owned ComfyUI workflow registry semantics:
  - `workflow_id -> repo/workflows/comfy/<workflow_id>.json` as repo-truth.
  - external UI workflow identifiers are not authoritative.
- QC policy/report authority must include both:
  - identity consistency gates
  - pose/motion similarity gates against dance-trace artifacts.
- Multimodal LLM diagnostics remain advisory (classification/diagnosis/suggested adjustments), not production routing authority.

Consequences:
- Increases quality ceiling where prompt-only paths fail (identity + dance fidelity).
- Keeps existing plane invariants intact:
  - planner/analyzer produce contracts
  - controller routes deterministically via policy/report artifacts
  - worker stays deterministic and assembly-focused.
- Cloud migration remains endpoint-swappable without contract redesign.

References:
- docs/PR_PROJECT_PLAN.md (PR-35)
- docs/architecture.md
- docs/briefs/GUARDRAILS.md

------------------------------------------------------------

## ADR-0049 — Autonomous lab->production bridge is contract-driven (auto-ingest + pointer resolver + promotion queue)
Date: 2026-02-18
Status: Accepted

Context:
- Current quality iteration requires too much manual CLI/path handling for sample onboarding and contract pointer selection.
- CAF’s original goal includes autonomous improvement while preserving deterministic, auditable production authority.

Decision:
- Add a contract-driven autonomy bridge (PR-35g direction):
  - lab-first sample onboarding for new demo inputs (incoming sample path -> lab artifacts/manifests)
  - deterministic planner pointer resolver:
    - high-level briefs may omit pointers
    - planner resolves best available pointers from canon/manifests/policy
    - selected pointers are emitted explicitly in `job.json` (or referenced contracts)
  - promotion queue contracts for non-CLI operations:
    - candidate artifacts from lab benchmarking
    - approve/reject request artifacts via ingress (`sandbox/inbox/*.json`)
    - deterministic promotion processor and promotion decision artifact
- Production authority remains unchanged:
  - controller routes from policy/report contracts
  - lab remains non-authoritative at runtime unless guarded trial flags explicitly enable limited experiments.

Consequences:
- Reduces operator burden for sample-to-production iteration.
- Preserves files-as-bus and three-plane invariants while increasing practical autonomy.
- Provides a clear path for Telegram/UI-driven promotion actions without bypassing deterministic authority.

References:
- docs/PR_PROJECT_PLAN.md (PR-35g)
- docs/system-requirements.md (FR-28.21, FR-28.22)
- docs/telegram-commands.md

------------------------------------------------------------

## ADR-0050 — Planner intelligence + lab bootstrap are required for practical brief-first autonomy
Date: 2026-02-18
Status: Accepted

Context:
- Users can provide high-level creative briefs, but current operation still often needs manual analysis/pointer selection.
- Quality iteration remains too manual when sample-derived assets are missing or incomplete.
- CAF must improve practical autonomy without breaking deterministic production authority.

Decision:
- Add a planner intelligence graph for brief->contract resolution:
  - structured brief slot extraction
  - candidate contract retrieval from canon/lab manifests
  - deterministic ranking/selection and explicit resolution artifact output.
- Require lab bootstrap extraction completeness for production-consumable sample packs:
  - identity, costume/style, stage/setting, framing/edit metadata, motion trace, audio/beat metadata.
- Add one-command autonomous run path:
  - brief -> resolve/bootstrap -> `job.json` -> deterministic controller/worker -> QC decision artifacts.

Consequences:
- Reduces manual CLI/path burden for repeated creative workflows (e.g., dance-loop recreation with hero substitution).
- Keeps runtime authority boundaries intact:
  - planner improves contract quality
  - controller remains routing authority
  - promotion contracts govern adoption into production defaults.

References:
- docs/PR_PROJECT_PLAN.md (PR-35h, PR-35i, PR-35j)
- docs/system-requirements.md (FR-28.23, FR-28.24, FR-28.25)
- docs/architecture.md

------------------------------------------------------------

## ADR-0051 — Deterministic brief pointer resolution authority and tie-break rules
Date: 2026-02-19
Status: Accepted

Context:
- Brief-first operation still requires manual pointer selection in too many runs.
- Planner improvements must remain auditable and must not introduce hidden authority.
- Pointer resolution needs deterministic behavior for replayability and debugging.

Decision:
- Define a deterministic pointer-resolution authority contract for planner output:
  - required pointer classes per workflow/lane
  - deterministic candidate ranking/tie-break rules
  - explicit `pointer_resolution.v1` artifact containing selected and rejected candidates with reasons
- **Sole Source of Truth**: Downstream components (Adapters, Workers, Controllers) MUST derive asset and contract paths EXCLUSIVELY from the `pointer_resolution` block in the job contract or its linked resolution artifact. Hardcoded fallbacks within providers are strictly forbidden.
- Fail loud when required pointers cannot be resolved from committed artifacts.
- Keep runtime authority unchanged:
  - planner resolves pointers
  - controller routes from policy/report contracts
  - worker remains deterministic and output-bound.

Consequences:
- Eliminates provider-specific "path drift" and hidden hardcoded dependencies.
- Reduces manual path editing while preserving deterministic authority boundaries.
- Makes brief->contract resolution reproducible and auditable.

References:
- docs/PR_PROJECT_PLAN.md (PR-35h, PR-36)
- docs/system-requirements.md (FR-28.23)
- docs/architecture.md

------------------------------------------------------------

## ADR-0052 — QC gate authority precedence and deterministic retry matrix
Date: 2026-02-19
Status: Accepted

Context:
- Quality routing decisions must be explicit and stable as adapter diversity increases.
- User expectation is quality convergence; production requires deterministic bounded loops.
- Existing QC surfaces need a strict precedence rule and failure-class action matrix.

Decision:
- Define production routing authority precedence as:
  - `qc_policy + qc_report + bounded retry state` only.
- Define deterministic retry/fallback/escalation matrix keyed by failure class.
- Preserve fail-loud terminal states when retry budget is exhausted or policy blocks finalize.
- Keep lab/advisory outputs non-authoritative by default unless guarded trials are explicitly enabled.

Consequences:
- Prevents routing drift and ad-hoc fallback behavior.
- Improves predictability and auditability of quality-convergence loops.

References:
- docs/PR_PROJECT_PLAN.md (PR-35b, PR-35c, PR-35d, PR-36)
- docs/system-requirements.md (FR-28.18, FR-28.19)
- docs/architecture.md

------------------------------------------------------------

## ADR-0053 — Motion-conditioned workflow capability checks are mandatory and fail-loud
Date: 2026-02-19
Status: Accepted

Context:
- Motion/identity quality depends on required workflow nodes/models being present.
- Current failures can degrade output quality without clear upfront capability failure semantics.
- Production must fail loud rather than silently degrade in quality-critical routes.

Decision:
- Introduce explicit required-capability declarations for motion-conditioned workflows:
  - workflow identifiers
  - required node classes
  - required model/checkpoint references
- Add deterministic preflight capability checks before execution.
- If required capabilities are missing, fail loud with explicit artifacts and no silent downgrade path.

Consequences:
- Improves quality predictability for choreography/identity-sensitive jobs.
- Makes capability-related failures diagnosable and policy-manageable.

References:
- docs/PR_PROJECT_PLAN.md (PR-35e, PR-36)
- docs/system-requirements.md (FR-28.20)
- docs/comfyui-workflows.md

------------------------------------------------------------

## ADR-0054 — Lab-to-production promotion governance is contract-only (no direct code mutation)
Date: 2026-02-19
Status: Accepted

Context:
- Lab mode can produce strong candidates but must not become hidden production authority.
- Promotion needs explicit approval and deterministic activation semantics.
- Direct code/path mutation by lab artifacts would violate reproducibility and governance posture.

Decision:
- Promotion lifecycle is contract-driven only:
  - promotion candidate artifact
  - explicit approval artifact
  - deterministic policy/workflow update artifact
- Lab artifacts must never directly mutate production code or runtime behavior.
- Production may consume only promoted, committed contracts/artifacts.

Consequences:
- Preserves deterministic production authority while enabling autonomous quality improvement.
- Keeps promotion decisions auditable and reversible.

References:
- docs/PR_PROJECT_PLAN.md (PR-35f, PR-35g, PR-36)
- docs/system-requirements.md (FR-28.22)
- docs/architecture.md

## ADR-0055: Granular Shot-by-Shot Director Architecture
**Date**: 2024-07-31  
**Status**: Accepted  
**Context**: Monolithic video generation (30s+ clips) leads to high rework costs and poor deterministic control over specific segment defects. Our LangGraph "Director" vision requires the ability to rework individual shots without re-generating the entire video.

**Decision**:
1.  **Granularity First**: The system will prioritize generating individual shots (cliplets) based on the Shot List before assembly.
2.  **Shot IDs**: Every shot in the `job.json` SHOULD have a unique `shot_id`.
3.  **Targeted Redraw**: Workers MUST support targeted generation via `CAF_TARGET_SHOT_ID`.
4.  **Director Responsibility**: The LangGraph Director is responsible for orchestrating these granular calls and validating segment-level QC before final assembly.

**Consequences**:
- **Benefit**: Significantly lower generation costs during retries (re-rolling a 5s shot vs 30s video).
- **Benefit**: Improved identity consistency by allowing the Director to "pin" a good shot and only rework a bad one.
- **Risk**: Increased orchestration complexity.
- **Risk**: Potential for "seams" between shots if motion state is not shared (mitigated by `image_motion.seed_frames`).


## ADR-0056: Identity Packs and Pose-Gated Generation
**Date**: 2024-07-31  
**Status**: Accepted  
**Context**: Text-to-video and single-frame-to-video are insufficient for maintaining identity and choreography over long durations or multi-character scenes. 

**Decision**:
1.  **Identity Packs**: The Hero Registry will evolve into `identity_pack/` collections containing multiple reference frames (front, side, detail) and a strict `identity_contract.json` (canonical descriptors).
2.  **Pose Landmark Extraction**: The Video Analyzer must extract `pose_seq.json` landmarks from reference videos.
3.  **Pose-Gated QC**: The QC Engine will use pose landmarks to reject generations that diverge from the target choreography (motion_smoothness scoring).
4.  **Multi-Subject Pass**: For complex scenes (e.g. 6 cats), the Director should decompose the job into background-plate generation and grouped-character compositing.

**Consequences**:
- **Benefit**: Significantly higher "yield" of usable dance clips.
- **Benefit**: Hard deterministic gate for choreography without needing model-level pose-control support.
- **Risk**: Increased processing time during the "Analysis" phase.

## ADR-0057: n8n Boundary (Ops/Distribution only)
**Date**: 2024-07-31  
**Status**: Accepted  
**Context**: We need to automate the "fan-out" and "retry" loop for high-yield generation while keeping the CAF core clean.

**Decision**:
1.  **Ops Only**: n8n is strictly limited to the Ops/Distribution plane.
2.  **Responsibilities**: n8n handles the fan-out (K-variants), triggers/webhooks, human approval notifications, and publishing integrations.
3.  **No Logic**: Quality scoring, prompt generation, and contract validation MUST remain inside the CAF file-bus (Planner/Control).

**Consequences**:
- **Benefit**: Decouples "Ops Automation" from "Factory Logic".
- **Benefit**: Prevents "logic leak" into low-code tools.
 
 ------------------------------------------------------------
 
 ## ADR-0058 — Hybrid Audio Strategy (Silent Master vs. Licensed Packs)
 Date: 2026-02-21
 Status: Accepted
 
 Context:
 - CAF needs a scalable way to handle audio that supports both platform-native virality (trending audio) and brand-safe commercial usage (licensed packs).
 - Trending audio on TikTok/IG is a distribution-layer asset; CAF should not store or redistribute it.
 - Licensed/original audio must be mixed deterministically inside the factory for multi-platform reuse.
 - Choreography-preserving generation requires deterministic timing (beat grids) across the media pipeline.
 
 Decision:
 - Formalize a Hybrid Audio Strategy with three modes:
   1. **Platform Trending Mode**: Worker exports a silent master; human/ops aligns audio in-platform.
   2. **Licensed Pack Mode**: Worker mixes internal license-safe audio tracks.
   3. **Original CAF Audio Mode**: Worker mixes original signature CAF motifs.
 - Introduce **Beat Grid System** (`beat_grid.v1`): Deterministic metadata specifying BPM and event timing for cuts and moves.
 - Planner Plane: Responsible for declarative selection of audio mode and BPM.
 - Control Plane: Enforces beat grid constraints and cut cadence.
 - Worker Plane: Performs deterministic mixing or silencing based on the mode.
 
 Consequences:
 - Protects the project from copyright liability via "Silent Masters" for trending content.
 - Enables frame-perfect choreography via the Beat Grid metadata.
 - Preserves the three-plane invariant by keeping media logic inside the media layer.
 
 References:
 - docs/master.md
 - AGENTS.md
 - docs/system-requirements.md (FR-17)
 - docs/PR_PROJECT_PLAN.md (PR-40)

------------------------------------------------------------

## ADR-0059: Dev Master Resolution Standardization

**Status**: PROPOSED
**Context**: To shorten the iteration loop while we stabilize motion/identity/temporal consistency, we need a canonical "dev master" resolution that balances debug signal with rendering speed. Square (1:1) is the core "factory canon" resolution.

**Decision**:
1.  **Dev Master**: Standardize on `1080x1080 @ 24fps`.
2.  **Canonical Aspect Ratio**: Production Plane (Factory) will focus on square 1:1 masters.
3.  **Tiering Strategy**:
    - `dev`: 1080x1080 @ 24fps
    - `staging`: 1440x1440 @ 30fps
    - `production`: 2160x2160 @ 30fps

**Consequences**:
- Shortens debug feedback loop.
- Simplifies reframing logic in the Distribution Plane.
- Requires updating `job.json` schema to include square resolution and ratio.

## ADR-0060: Media Architecture v2 (Publish Pack Engine)

**Status**: PROPOSED
**Context**: Decoupling physical rendering from platform-specific productization.

**Decision**: Evolve from a two-stage process to a three-plane media lifecycle:
1.  **Planning Plane**: Strategic directive (Brief -> Directive).
2.  **Production Plane (The Factory)**: Engine execution (Frame/Motion/Video/Audio/Editor). Produces a **Single Canonical Master**.
3.  **Distribution Plane (Publish Pack Engine)**: Downstream consumer for reframing, safe-zones, and platform-specific packaging.

**Consequences**:
- Moves reframing out of the core Worker.
- Directory separation: `/master` (Factory) vs `/dist` (Publish Packs).
- ADR-0021 (Bundles) survives but is relocated to the Distribution Plane.
