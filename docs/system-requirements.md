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
Planner (Clawdbot) → Production Plane (Worker) → Distribution Plane (Publish Pack Engine)

- Planner is the only nondeterministic component (LLM-driven).
- Control Plane + Production Plane (Worker) must remain deterministic and retry-safe.
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
- Human approval gates may exist for nondeterministic external actions (e.g., in the Distribution Plane), not for core planning.

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
  - Seed frames MAY be AI-generated planner-side (never in Worker).
- Lane C: `template_remix` (near-free / scalable)
  - Uses existing templates/clips + deterministic FFmpeg recipes.
  - Templates MAY be AI-generated planner-side (never in Worker).

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

### FR-09.1 — Telegram daily_plan supports optional creativity hints
Telegram daily planning MUST support optional creativity hints for the Planner.

- The daily_plan ingress artifact MAY include:
  - `creativity.mode`: canon | balanced | experimental
  - `creativity.canon_fidelity`: high | medium
- This is planner-only intent (no Worker meaning).
- Backward compatible: if omitted, behavior is unchanged.
- Telegram MUST remain an adapter and MUST NOT bypass the file-bus.

### FR-10 — Distribution Plane (Ops/Distribution)
The Distribution Plane (Publish Pack Engine) MUST remain outside the three-plane factory (Planning/Production) authority but is a first-class media plane.

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

### FR-17 — Hybrid Audio Strategy (Platform-native + Brand-safe)
Audio is a deterministic media-plane asset layer.

- Every clip MUST support one of three audio modes:
  1. `platform_trending`: Export a **Silent Master**; alignment happens in-platform (No licensing risk).
  2. `licensed_pack`: Mix internal license-safe audio tracks for multi-platform reuse.
  3. `original_pack`: Mix signature CAF motifs for brand moat.
- Every clip MUST adhere to a **Beat Grid** metadata contract if choreography is required.
- Audio is part of the posting workflow: export bundles include `audio_plan.json` and `audio_notes.txt`.

Non-goals (v1):
- no real-time music generation
- no scraping platform trends
- no automated rights management

### FR-18 — Series continuity layer (contracts-only; required for “daily era” quality)
To maintain higher-quality comedy and continuity without autonomy creep, CAF MUST support a minimal,
deterministic “series layer” above job contracts.

- The system MUST support a versioned “series bible” artifact that defines:
  - tone rules, forbidden topics, running gags, canon setting rules
  - references to hero cat registry ids (no new identities implied)
- The system MUST support a versioned “episode ledger” artifact that records:
  - what happened, new facts introduced, next hook
- These artifacts MUST be file-based, reviewable, and reproducible.
- The Worker MUST remain unchanged by this layer (planner/control-plane only).
- The system MUST treat continuity as **explicit canon artifacts**:
  - LLM may propose new facts, but only committed artifacts become canon.
- The Planner MAY use optional creativity hints (canon/balanced/experimental) to control canon fidelity.

### FR-19 — Planner RAG (deterministic, file-based, planner-only)
The system MUST support Retrieval-Augmented Generation (RAG) as a **planner-only, deterministic, file-based** reference mechanism to improve job contract quality and continuity.

- Canonical artifacts:
  - `repo/shared/rag_manifest.v1.schema.json`
  - `repo/shared/rag_manifest.v1.json` (references available docs, tags, priority)
  - `repo/shared/rag/` (repo-owned, license-safe reference documents)
- Deterministic retrieval:
  - Planner selects RAG docs using manifest tags/filters with stable tie-break rules
    (e.g., `priority` then `doc_id` lexical).
  - No embeddings/vector DBs are required for v1.
- Read-only inputs:
  - Planner MAY read RAG docs when generating `job.json`.
  - Planner MUST NOT modify any RAG artifacts at runtime.
- Hard constraints:
  - RAG MUST NOT move into the Control Plane or Worker.
  - Worker MUST remain LLM-free and deterministic.
  - No hidden “memory” store becomes an authority source; only committed files count.


### FR-20 — PlanRequest v1 (UI-agnostic daily planning input contract)
The system MUST support a versioned, schema-valid “plan request” contract to capture daily planning intent in a structured, UI-agnostic way.

- Purpose:
  - enable guided UI inputs (Coze later) without making any UI a dependency
  - normalize daily intent before the Planner runs
- Canonical artifacts:
  - `repo/shared/plan_request.v1.schema.json`
  - `repo/examples/plan_request.v1.example.json`
- Invariants:
  - PlanRequest is an input only; it does not replace `job.json`
  - The Planner remains the only component that writes `sandbox/jobs/*.job.json`
  - Any adapter (Telegram, Coze, future UIs) must map into PlanRequest v1 deterministically


### FR-21 — CrewAI planning (planner-only; contract-gated; required portfolio signal)
The system MUST support a CrewAI-based planning step as part of the Planner plane to improve creative quality and continuity consistency.

- Scope constraints:
  - CrewAI MUST run only inside the Planner plane.
  - CrewAI MUST be contained to a single LangGraph node (or subgraph) to prevent framework creep.
- Determinism gates:
  - CrewAI outputs MUST be normalized and validated deterministically before becoming canonical.
  - CrewAI MUST NOT write artifacts directly.
  - Only deterministic commit steps may persist canonical state (job contracts, ledger updates).
- Hard constraints:
  - CrewAI MUST NOT replace Ralph Loop.
  - CrewAI MUST NOT run in the Worker.
  - CrewAI MUST NOT introduce agent-to-agent RPC across planes.


### FR-22 — Optional guided UI front end (Coze; adapter-only; post-cloud wiring)
The system MUST support an optional guided UI front end for daily planning inputs.

- Posture:
  - Coze is treated as an adapter/UI only.
  - Coze MUST NOT become a required runtime dependency.
  - CAF remains the source of truth for contracts and canon.
- Requirements:
  - Coze (or any UI) must emit PlanRequest v1 and submit it to CAF ingress.
  - Continuity reasoning and canon enforcement must remain in the Planner (LangGraph), not in Coze.


### FR-23 — Ops workflow automation layer (n8n; outside factory; post-cloud)
The system MUST support an optional Ops workflow automation layer (e.g., n8n) to improve human approvals, notifications, and manual publish workflows.

- Posture:
  - n8n MUST remain outside the core factory invariant.
  - n8n MUST NOT replace Cloud Tasks for internal execution retries/backoff.
- Allowed responsibilities:
  - notifications (Telegram/Email/Slack)
  - human approval UI/buttons
  - manual publish triggers
  - external logging (Sheets/Notion)
- Hard constraints:
  - n8n MUST NOT mutate worker outputs or job contracts.
  - Cloud Tasks remains the internal queue for all “do work” steps.


### FR-24 — EpisodePlan v1 (planner-only intermediate artifact; schema-validated)
The system MUST support a planner-only intermediate artifact (EpisodePlan v1) to improve continuity and make planning outputs auditable before job.json is written.

- Canonical artifacts:
  - `repo/shared/episode_plan.v1.schema.json`
  - `repo/examples/episode_plan.v1.example.json`
- Posture:
  - EpisodePlan v1 is planner-only and MUST NOT be required by Control Plane or Worker.
  - EpisodePlan v1 is schema-validated and committed as an explicit artifact (no hidden memory).
- Determinism gates:
  - EpisodePlan outputs MUST be normalized and validated deterministically before becoming canonical.
- EpisodePlan MUST NOT bypass job.json validation/commit steps.

### FR-25 — Media Stack v1 stage contracts (deterministic Worker artifacts)
The system MUST support deterministic, versioned media-stage artifacts for inspectability without changing execution authority.

- Canonical stage contract families (v1):
  - frame manifest
  - audio manifest
  - timeline
  - render manifest
- Hard constraints:
  - `job.json` remains execution authority.
  - Stage manifests are execution artifacts only.
  - Worker writes stage artifacts only under `/sandbox/output/<job_id>/**`.

### FR-26 — Video Analyzer contracts (planner-side metadata canon)
The system MUST support planner-side reference analysis artifacts for reusable pacing/choreography/camera patterns.

- Canonical posture:
  - schemas under `repo/shared/*.schema.json`
  - metadata instances/index under `repo/canon/demo_analyses/**`
- Hard constraints:
  - metadata/patterns only; no copyrighted source media in repo canon.
  - Worker MUST NOT depend on analyzer artifacts at runtime.

### FR-26.1 — Video Analyzer implementation path (planner-side/offline tooling)
The system MUST support an implementation path that generates `video_analysis.v1`
artifacts from video inputs for planner enrichment.

- Implementation posture:
  - analyzer execution is planner-side/offline tooling (not Worker runtime authority)
  - outputs are metadata artifacts only and must conform to `video_analysis.v1`
  - generated metadata is validated deterministically before use
  - deterministic CV tooling (e.g., OpenCV) MAY be used for extraction/normalization
- Hard constraints:
  - no change to runtime write boundaries for Planner/Control/Worker
  - no copyrighted source media committed into repo canon
  - Worker MUST remain independent from analyzer artifacts at runtime authority level

### FR-26.2 — Voice/Style registries (planner metadata inputs)
The system MUST support versioned, provider-agnostic metadata registries for voice/style references.

- Canonical posture:
  - `voice_registry.v1` (hero_id -> voice adapter id/placeholder)
  - `style_registry.v1` (style_id -> workflow/prompt fragments/keys)
- Hard constraints:
  - registries are planner/control-plane metadata only (not Worker authority by themselves)
  - no secrets or identity-tied credentials in registry artifacts
  - deterministic validation is required for registry shape and references

### FR-27 — Dance Swap v1 deterministic lane
The system MUST support a choreography-preserving recast lane using explicit deterministic artifacts.

- Expected artifact classes:
  - loop bounds
  - tracked subject IDs
  - per-frame mask references
  - optional beat/flow metadata
- Hard constraints:
  - lane remains non-binding at schema level (consistent with lane policy).
  - Worker performs deterministic compositing/replacement only from explicit artifacts.
  - deterministic CV tooling (e.g., OpenCV) MAY be used if behavior remains contract-bound.

### FR-27.1 — Optional Mode B planning contracts
The system MAY support optional, versioned planner-side contracts for Mode B planning:

- `script_plan.v1`
- `identity_anchor.v1`
- `storyboard.v1`

Hard constraints:
- these contracts MUST NOT replace `job.json` execution authority
- Planner/Control MAY consume them as intermediate planning/state artifacts
- Worker behavior remains deterministic and contract-bound

### FR-28 — External HITL recast boundary (Ops/Distribution only)
The system MUST model external recast tools (Viggle-class) as explicit Ops/Distribution steps.

- Export pack path:
  - `/sandbox/dist_artifacts/<job_id>/viggle_pack/**`
- Re-ingest posture:
  - via explicit inbox metadata artifact under `/sandbox/inbox/*.json`
- Hard constraints:
  - no hidden manual authority
  - Worker MUST NOT call external recast services
  - Worker performs deterministic finishing only

### FR-28.1 — HITL lifecycle + pack/pointer validation contracts
The system MUST support deterministic contract surfaces for external HITL recast lifecycle and handoff integrity.

- Required contract classes:
  - lifecycle/state artifacts for external recast steps
  - inbox metadata pointer contract for re-ingest under `/sandbox/inbox/*.json`
  - `viggle_pack.v1` (or equivalent) completeness/consistency schema
- Hard constraints:
  - canonical pack root remains `/sandbox/dist_artifacts/<job_id>/viggle_pack/**`
  - no direct external-tool invocation inside factory components
  - re-ingest remains explicit, auditable, and idempotent
  - deterministic CV tooling (e.g., OpenCV) MAY be used for offline validation/preflight checks

### FR-28.2 — Recast quality gates and deterministic scoring
The system MUST support deterministic quality-gate scoring artifacts for recast outputs.

- Required quality dimensions:
  - identity consistency
  - mask edge/bleed artifact checks
  - temporal stability (jitter/flicker)
  - loop seam continuity
  - audio/video sync and audio stream presence
- Required behavior:
  - deterministic pass/fail thresholds
  - explicit report artifact(s) for reviewer inspection and control-plane gating
- Hard constraints:
  - no nondeterministic authority from scoring artifacts
  - no external recast invocation inside Worker
  - quality scoring remains artifact-driven and auditable

### FR-28.3 — Recast benchmark regression harness
The system MUST support a deterministic benchmark harness for recast quality regression tracking.

- Required behavior:
  - fixed benchmark set definition (demo loops + hero mappings)
  - repeatable run command path
  - comparable output metrics/reports across runs
- Hard constraints:
  - benchmark artifacts remain contract-bound and deterministic
  - benchmark process MUST NOT bypass runtime write boundaries
  - no copyrighted source media committed into repo canon

### FR-28.4 — Internal Baseline V2 motion-preserve path (non-overlay fallback)
The system MUST support a deterministic internal baseline quality path that is better than legacy overlay outputs and does not require external HITL.

- Required behavior:
  - motion-preserve 9:16 reframing and deterministic preprocess filters
  - loop seam refinement and audio-stream guarantee
  - subtitle/watermark finishing in deterministic Worker flow
  - benchmark-visible comparison against prior internal baseline
- Hard constraints:
  - no overlay-based identity recast fallback in this path
  - no external API/tool invocation inside Worker
  - outputs and stage artifacts remain under `/sandbox/output/<job_id>/**`
  - `job.json` remains execution authority

### FR-28.5 — Deterministic quality-controller loop (bounded retry + explicit escalation)
The system MUST support an artifact-driven quality-controller loop that deterministically maps quality results to bounded next actions.

- Required behavior:
  - emit deterministic decision artifact under `/sandbox/logs/<job_id>/qc/quality_decision.v1.json`
  - map failed quality dimensions to explicit policy actions (retry, block finalize, escalate)
  - enforce bounded retry budgets and fail-loud escalation states
  - keep all decision state auditable and reproducible from artifacts
- Hard constraints:
  - no hidden autonomous/background agent behavior
  - no changes to write boundaries (Planner/Control/Worker remain separated)
  - external recast remains explicit HITL outside Worker runtime
  - quality policy artifacts are deterministic guidance, not authority overrides of `job.json`

### FR-28.6 — Reverse-analysis truth/suggestions contracts (planner-side)
The system MUST support a planner-side reverse-analysis contract that separates deterministic measured truth from optional vendor suggestions.

- Required behavior:
  - canonical reverse-analysis artifact schema (`caf.video_reverse_prompt.v1`)
  - deterministic checkpoint schemas for beat grid, pose checkpoints, and keyframe checkpoints
  - optional vendor suggestion envelopes stored under `repo/analysis/vendor/**`
  - deterministic validation that enforces cross-artifact analysis/source consistency
- Hard constraints:
  - deterministic analyzer fields remain authoritative; vendor fields are suggestions only
  - vendor integrations remain optional and non-blocking for daily pipeline operation
  - Worker MUST NOT depend on reverse-analysis/vendor artifacts as runtime authority

### FR-28.7 — Analyzer core implementation and quality-loop consumption
The system MUST implement deterministic analyzer core signals and ensure planner/control quality flows consume them.

- Required behavior:
  - deterministic extraction for metadata truth, shot boundaries, pose checkpoints, optical-flow motion curves, and beat/onset timing
  - planner quality constraints consume reverse-analysis artifacts as first-class inputs
  - control-plane quality decisions consume report artifacts plus checkpoint/segment coverage signals
- Hard constraints:
  - analyzer outputs remain planner-side metadata artifacts
  - no Worker authority dependency on analyzer artifacts
  - no changes to runtime write boundaries

### FR-28.8 — Facts-only planner guard with explicit unknown semantics
The system MUST enforce planner outputs to be grounded in analyzer facts for reverse-analysis workflows.

- Required behavior:
  - analyzer facts include brightness/palette stats and basic camera movement classification output
  - planner must only emit claims supported by available analyzer facts
  - unsupported fields must be emitted as `unknown`
  - deterministic validation fails when planner output contains non-fact-backed claims
- Hard constraints:
  - no hidden fallback to unconstrained semantic guessing in facts-only mode
  - Worker authority remains unchanged and deterministic

### FR-28.9 — Segment runtime execution and seam enforcement
The system MUST support deterministic segment generation and stitch execution from versioned segment plan contracts.

- Required behavior:
  - execute segment render runtime from `segment_stitch_plan.v1`
  - enforce seam methods from contract
  - emit per-segment and stitch report artifacts for auditability
- Hard constraints:
  - output artifacts remain under `/sandbox/output/<job_id>/**`
  - no nondeterministic runtime behavior introduced in Worker

### FR-28.10 — Two-pass motion/identity orchestration
The system MUST support explicit two-pass orchestration for dance-quality jobs.

- Required behavior:
  - motion pass and identity pass artifacts/log states are explicit and deterministic
  - controller policy can route retries by pass-level failures
- Hard constraints:
  - external identity recast remains explicit HITL when used
  - write boundaries and authority invariants remain unchanged

### FR-28.11 — Quality target contract and segment-level retry tuning
The system MUST support explicit quality-target contracts and segment-level retry policy mapping.

- Required behavior:
  - versioned quality-target artifact with per-dimension thresholds
  - deterministic decision mapping from failed dimensions to segment-level retries
  - bounded retries with fail-loud escalation
- Hard constraints:
  - no hidden automatic loops beyond declared retry budgets
  - policy artifacts remain auditable and deterministic

### FR-28.12 — Continuity pack and debug export posture
The system MUST support continuity-pack inputs and deterministic debug exports for quality tuning.

- Required behavior:
  - versioned continuity pack consumed by planner and quality checks
  - deterministic segment/shot debug export artifacts for diagnostics
- Hard constraints:
- debug exports are non-authoritative artifacts
- continuity inputs remain planner/quality-side references and must not alter Worker determinism rules

### FR-28.13 — Storyboard-first image-to-video default for quality paths
The system MUST support storyboard-first I2V routing as the default generation strategy for quality/dance paths.

- Required behavior:
  - planner emits shot/segment references that map to storyboard/keyframe assets
  - provider routing prefers I2V from storyboard frames over prompt-only T2V for quality paths
  - fallback behavior is explicit and contract-visible when storyboard inputs are unavailable
- Hard constraints:
  - routing remains deterministic from artifacts/contract inputs
  - Worker remains provider-agnostic and deterministic
  - no hidden runtime side-channel state

### FR-28.14 — Frame-labeling contract lane with analyzer-grounded enrichment
The system MUST support a planner-side frame-labeling contract that separates deterministic analyzer facts from optional multimodal semantic enrichment.

- Required behavior:
  - FFmpeg-extracted keyframes and analyzer facts are the authoritative base inputs
  - multimodal labeling (Gemini/ChatGPT Vision class) is constrained to facts-backed claims or explicit `unknown`
  - frame-label artifacts include confidence/uncertainty fields and are versioned/validated
- Hard constraints:
  - analyzer truth MUST NOT be overwritten by enrichment output
  - enrichment remains planner-side only
  - Worker MUST NOT depend on frame-label enrichment as runtime authority

### FR-28.15 — Optional Whisper captions lane (non-blocking)
The system MUST support optional subtitle/caption artifact ingestion from Whisper-class tooling without making it a required dependency.

- Required behavior:
  - when captions artifact exists, deterministic worker subtitle burn path may consume it
  - when captions artifact is absent/unavailable, pipeline proceeds without failure
  - optional captions artifact pointers are validated and auditable
- Hard constraints:
  - captions extraction remains outside Worker runtime determinism requirements
- Worker network/LLM prohibitions remain unchanged
- no failure escalation solely due to optional captions unavailability

### FR-28.16 — Analyzer reproducibility lock + version stamps
The system MUST reduce analyzer model/tool drift by pinning dependency versions and recording runtime tool versions in analyzer artifacts.

- Required behavior:
  - provide a reproducible analyzer constraints/lock file for CV/audio dependencies
  - emit `tool_versions` metadata in analyzer-derived contracts (pose/reverse/frame-label lanes)
  - enforce version stamp presence and cross-artifact consistency in deterministic validators
- Hard constraints:
  - lock metadata is advisory to install/runtime and must not become hidden mutable state
- analyzer artifact version stamps remain planner-side metadata only
- Worker authority and determinism boundaries remain unchanged

### FR-28.17 — Deterministic planner artifact selection + quality target auto-wiring
The planner MUST deterministically select and wire quality artifacts so control-plane quality policy is consistently applied without manual job edits.

- Required behavior:
  - when multiple contracts match a lane/version, prefer `repo/canon/**` over `repo/examples/**`
  - within the same source bucket, prefer the newest artifact deterministically
  - auto-populate `job.quality_target.relpath` when absent using available versioned quality-target contracts
- Hard constraints:
  - planner remains the only writer of `sandbox/jobs/*.job.json`
  - no runtime mutation of `job.json` after planner write
  - Worker determinism/authority boundaries remain unchanged

### FR-28.18 — QC policy contract + normalized QC report + deterministic routing
The system MUST support policy-driven quality routing where controller decisions are derived from explicit quality policy and normalized QC reports.

- Required behavior:
  - production-authoritative policy contract at `repo/shared/qc_policy.v1.json`
  - deterministic QC report artifact at `sandbox/logs/<job_id>/qc/qc_report.v1.json`
  - deterministic QC runner that normalizes existing quality artifacts into gate-level pass/fail results
  - controller routes pass/retry/fallback/escalate from policy + report under bounded retries
- Hard constraints:
  - planner remains nondeterministic contract generator, not runtime routing authority
  - Worker remains deterministic and non-networked/non-LLM
  - no mutation of `job.json` after planner write
  - controller decisions remain auditable and replayable from artifacts

### FR-28.19 — OpenClaw lab advisory mode and promotion governance
The system MUST support OpenClaw as a lab-only quality optimizer that can propose routing/policy improvements without directly becoming production authority by default.

- Required behavior:
  - advisory contract artifact (`qc_route_advice.v1`) with deterministic validation
  - optional controller advisory-consumption mode that logs accept/reject reasoning
  - replay/benchmark harness measuring advisory lift vs baseline deterministic routing
  - promotion gate contract enforcing minimum lift and regression/safety constraints
  - guarded authority trial mode, feature-flagged and disabled by default
- Hard constraints:
  - default production authority remains deterministic policy routing
  - advisory and trial modes must be bounded by explicit retry/cost/time guardrails
  - fail-closed fallback to deterministic policy route is mandatory

### FR-28.20 — Free-first engine adapter path for quality ceiling lift
The system MUST support integrating free/open-source generation/recast adapters behind existing contracts and quality policy routing.

- Required behavior:
  - Veo3 remains baseline production video lane unless promotion policy explicitly changes default ordering
  - adapter lanes for ComfyUI/OpenPose-constrained generation and temporal/post passes (RIFE/FILM, selective ESRGAN)
  - policy-driven provider ordering and deterministic best-of-attempt selection by quality reports
  - end-to-end smoke coverage proving adapter path compliance with controller policy routing
- Hard constraints:
  - no authority boundary changes (Planner/Control/Worker remain separated)
  - Worker determinism and write boundaries remain unchanged
  - paid engines remain optional adapters, not required dependencies

Defer note:
- MoveNet integration is deferred until measured quality gains exceed current MediaPipe-based pose extraction.

### FR-28.21 — Autonomous lab-first sample onboarding and pointer resolver
The system MUST support a low-manual-overhead path where high-level briefs can be executed without per-run manual contract pointer editing.

- Required behavior:
  - lab-first onboarding flow for new samples under a deterministic incoming path (for example `sandbox/assets/demo/incoming/**`)
  - deterministic generation of sample asset manifests and candidate pointer contracts from lab analysis outputs
  - planner-side deterministic pointer resolver:
    - when user brief omits pointers, planner resolves best-available contracts/manifests from policy/canon rules
    - resolved pointers are emitted explicitly in `job.json` (or referenced contracts)
- Hard constraints:
  - planner remains the only writer of `sandbox/jobs/*.job.json`
  - no hidden mutable state outside file contracts
  - production authority remains policy/report driven; no direct lab runtime bypass

### FR-28.22 — Promotion queue contracts for non-CLI lab->production operations
The system MUST support contract-driven promotion actions that can be triggered by adapters/UI without requiring direct CLI path editing by operators.

- Required behavior:
  - promotion candidate artifact(s) emitted from lab benchmarking outputs
  - promotion approve/reject request artifacts accepted through ingress (`sandbox/inbox/*.json`)
  - deterministic promotion processor that validates evidence thresholds before activating production-facing policy/workflow/manifest updates
  - auditable promotion decision artifact recording accepted/rejected result and reasons
- Hard constraints:
  - adapter layer remains ingress/status only (no direct authority bypass)
  - promotion decisions remain reproducible from explicit contracts and benchmark artifacts
- production mode consumes promoted artifacts/contracts only

### FR-28.23 — Planner intelligence graph for deterministic contract pointer resolution
The system MUST support a planner intelligence step that maps high-level briefs to concrete contract pointers with deterministic final selection.

- Required behavior:
  - parse brief intent into structured slots (hero, costume/style, choreography/motion source, setting, tone)
  - retrieve candidate contracts from canon/lab manifests
  - deterministically rank/select pointers according to policy and artifact quality/provenance rules
  - emit a resolution artifact with selected pointers and rejection reasons
- Hard constraints:
  - planner remains contract author only; runtime routing authority remains controller policy + QC report
  - no hidden mutable memory authority outside explicit artifacts

### FR-28.24 — Lab bootstrap extractor completeness for production-consumable assets
The system MUST support extracting and validating a minimum reusable asset/contract pack from sample video onboarding.

- Required behavior:
  - emit versioned artifacts for at least:
    - hero/identity anchors
    - costume/style references
    - background/stage/setting references
    - framing/camera/edit metadata
    - motion trace + segment plan
    - audio/beat metadata
  - include consumer mapping metadata (which lane consumes each artifact, required vs optional)
  - fail-loud when required classes are missing
- Hard constraints:
  - extraction artifacts remain planner/control references only unless promoted
  - worker runtime determinism and authority boundaries remain unchanged

### FR-28.25 — One-command autonomous brief run with lab bootstrap fallback
The system MUST support an end-to-end operator path where a high-level brief can run without manual pointer editing.

- Required behavior:
  - single run path: brief -> planner resolve -> controller execute -> QC decision artifacts
  - if required sample contracts are missing, trigger deterministic lab bootstrap before production execution
  - persist lifecycle/state artifacts for adapter/UI status visibility
- Hard constraints:
  - no bypass of promotion policy for production authority
  ### FR-28.26 — Granular shot-by-shot generation primitives
The system MUST support generating and reworking individual shots/cliplets independently to enable Director-level autonomy.

- Required behavior:
  - Workers MUST support `CAF_TARGET_SHOT_ID` to generate only the specified segment.
  - Assembly engine MUST support partial updates to the final video without re-rendering all segments.
  - Every stage (Shot, Frame, Motion) MUST emit unique, versioned artifacts (e.g., `shot_001_v1.mp4`).
- Hard constraints:
  - `job.json` remains the root execution authority.
  - No nondeterministic behavior in the Worker.
  - Shot-level idempotency must be maintained.

### FR-28.27 — Identity Packs and Costume Stability (optional but recommended)
The system SHOULD support explicit identity-pack references (multi-frame character anchors) to improve character/fur/costume stability over time.

### FR-28.28 — Pose-Gated Quality Control
The system MUST support rejecting generations where the motion/choreography diverges from the extracted pose landmarks (`pose_seq.json`).


### FR-29 — Dev Master Resolution Lock
The system MUST standardize on `1080x1080 @ 24fps` for the Production Plane dev master.
- Rationale: High-quality square "canon" ensures stable motion/identity while shortening debug loops and simplifying 9:16/16:9 reframing in the Distribution Plane.

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
