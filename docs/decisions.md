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

