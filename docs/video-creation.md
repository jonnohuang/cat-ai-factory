# Cat AI Factory — Video Creation Architecture (v0.1 Direction)

This document defines the canonical v0.1 direction for how Cat AI Factory produces
high-performing short-form videos.

This is not a redesign. It is a content-production framing that is fully consistent
with the system’s existing architectural invariants:

- Three-plane separation (Planner / Control Plane / Worker)
- Files-as-bus coordination
- Deterministic worker (no LLM, no randomness)
- Frameworks treated as adapters, not foundations
- RAG is planner-only
- Verification agents are deterministic QC only
- Safety/social agents are advisory-only and cannot modify artifacts

For the authoritative system invariants, see:
- `docs/master.md`
- `docs/decisions.md`
- `docs/architecture.md`

------------------------------------------------------------

## Strategic Conclusion

Cat AI Factory is a deterministic short-form meme assembly engine.

High-performing cat Shorts/Reels are built from a balance of deterministic compositing and high-performance generative motion.

While v0.1 focused on "deterministic editing illusions," v0.2 (Phase 12) introduces the **Guided Seed Pattern**:
- **Draft Pass**: Wan 2.2 (High-Performance Motion) generates the pose/identity-stable latent.
- **Refine Pass**: Veo3/Comfy (High-Photo Quality) refines the draft into final cinema-quality frames.

The worker remains deterministic and infrastructure-enforced, consuming these generative lanes as structured service providers.


------------------------------------------------------------

## Series Connectivity (Continuity Layer)

Cat AI Factory implements a **deterministic continuity layer** to support consistent character voices, recurring gags, and story progression without autonomous memory creep.

The Planner reads these artifacts as **canon inputs** but cannot modify them directly.

### 1) Series Bible (Canon Rules)
- **Contract**: `repo/shared/series_bible.v1.schema.json`
- **Canonical Instance**: `repo/shared/series_bible.v1.json`
- **Scope**: Tone, forbidden topics, running gags, setting descriptions, and character cross-references.
- **Validation**:
  
  # Basic validation
  python3 repo/tools/validate_series_bible.py repo/shared/series_bible.v1.json
  
  # With explicit hero registry path (optional)
  python3 repo/tools/validate_series_bible.py repo/shared/series_bible.v1.json repo/shared/hero_registry.v1.json


### 2) Episode Ledger (History)
- **Contract**: `repo/shared/episode_ledger.v1.schema.json`
- **Canonical Instance**: `repo/shared/episode_ledger.v1.json`
- **Scope**: Ordered list of published episodes, summary of events, new facts introduced, and continuity hooks for future episodes.
- **Validation**:

  # Basic validation
  python3 repo/tools/validate_episode_ledger.py repo/shared/episode_ledger.v1.json
  
  # With explicit cross-references (optional)
  python3 repo/tools/validate_episode_ledger.py repo/shared/episode_ledger.v1.json repo/shared/hero_registry.v1.json repo/shared/series_bible.v1.json

------------------------------------------------------------


## Production Archetypes (v0.1 Registry)

Cat AI Factory supports a small registry of deterministic production archetypes.

### 1) dialogue_reaction
- Source: short real clips (user-supplied licensed footage)
- Core: caption timing + anthropomorphic dialogue
- Worker: trim + captions + optional audio normalization

### 2) meme_narrative
- Source: static images, cutouts, or short clips
- Core: jump cuts + punch-in + shake + SFX cues + captions
- Worker: deterministic scene assembly from a beat sheet

### 3) dance_loop
- Source: cat PNG cutouts
- Core: BPM-locked sinusoidal transforms (sway/bounce/rotate), loopable output
- Worker: math-based motion presets

### 4) flight_composite
- Source: cat PNG + moving background
- Core: scale + translation + slight rotation + motion blur; “fake camera” sells depth
- Worker: deterministic compositing presets

### 5) hybrid_motion (Phase 12)
- Source: identity anchor + dance trace
- Core: Guided Seed pattern (Wan 2.2 draft -> Veo3 refine)
- Worker: generative lane orchestration + artifact handoff

### Non-core (not a factory primitive)
cozy_real_life:
- Source: real footage
- Core: authenticity + minimal edits
- Note: low scalability; only viable via user submissions/licensed footage

------------------------------------------------------------

## Diagram — Planes and Authority Boundaries

Diagram-first section
Diagram 1 — Planes and authority boundaries (v0.1 creation mechanics)
flowchart TB
  subgraph P[Planner Plane — Clawdbot (LLM; constrained)]
    PRD[/sandbox/PRD.json/]
    INBOX[/sandbox/inbox/*.json (optional)/]
    STYLE[(Private style refs\nNOT in git)]
    REG[Archetype Registry\n(preset catalog)]
    PLAN[Planner:\nselect archetype + emit beat sheet + job.json]
    JOB[/sandbox/jobs/<job_id>.job.json/]

    PRD --> PLAN
    INBOX --> PLAN
    STYLE -. guides writing only .-> PLAN
    REG --> PLAN
    PLAN --> JOB
  end

  subgraph C[Control Plane — Ralph Loop (deterministic)]
    ORCH[Orchestrator:\nvalidate job\nensure lineage\ntrigger worker\nretry safely]
  end

  subgraph W[Worker Plane — Production (deterministic)]
    WORK[FFmpeg-first renderer:\ncompositing + captions + audio]
    ASSETS[/sandbox/assets/.../]
    MASTER[/sandbox/output/<job_id>/\nfinal.mp4 (1080x1080) + result.json/]
    LOGS[/sandbox/logs/<job_id>.../]
    ASSETS --> WORK
    WORK --> MASTER
    WORK --> LOGS
  end

  subgraph D[Distribution Plane — Export (automated)]
    RUNNER[Distribution Runner:\npolls inbox for approvals]
    REFR[Dist Reframer:\nreframes 1:1 to 9:16 / 4:5 / 16:9]
    BUNDLE[/sandbox/dist_artifacts/<job_id>/bundles/\ntiktok/ instagram/ youtube/]
    
    MASTER --> RUNNER
    RUNNER --> REFR
    REFR --> BUNDLE
  end

  JOB --> ORCH
  ORCH --> WORK

## Diagram — Archetype → Deterministic Render Graph
Diagram 2 — Archetype selection to deterministic render graph
flowchart LR
  JOB[job.json\n(archetype + inputs + preset refs)] --> PIPE[Render pipeline\n(archetype-specific)]
  PIPE --> MP4[final.mp4]
  PIPE --> SRT[final.srt]
  PIPE --> META[result.json\nchecksums + versions]

    A1[dialogue_reaction:\ntrim + captions + audio normalize]
    A2[meme_narrative:\nscene list + punch-in + shake + sfx cues + captions]
    A3[dance_loop:\nBPM loop + sine motion preset + captions]
    A4[flight_composite:\nfg png + bg + fake camera preset + captions]
  end

  PIPE --> OUT[Production Master\n1080x1080 @ 24fps]

------------------------------------------------------------

## Minimal Job Contract Shapes (Conceptual)

This section describes the minimal job contract shape per archetype.
It does not supersede the canonical schema (`repo/shared/job.schema.json`).

Common fields:
- `schema_version`
- `job_id`
- `archetype` (enum)
- `inputs` (asset references)
- `preset` (named preset selection)
- `beats` / `timeline` (structured, deterministic)
- `outputs` (optional; defaults to canonical layout)

### dialogue_reaction

Required inputs:
- `inputs.video_primary` (mp4)

Optional inputs:
- `inputs.video_secondary` (mp4)

Deterministic parameters:
- `preset.caption_style` (name)
- `preset.edit_style` (name)
- `beats[]` (caption segments with `start_ms`, `end_ms`, `text`)

Expected outputs:
- `final.mp4`, `final.srt`, `result.json`

### meme_narrative

Required inputs:
- `inputs.scenes[]` (each scene references an image/video + `duration_ms`)

Optional inputs:
- `inputs.sfx[]` (named cues or file references, if supported)

Deterministic parameters:
- `preset.camera` (name; e.g., punch-in)
- `preset.shake` (name)
- `preset.caption_style` (name)
- `timeline[]` (scene order + per-scene caption segments)

Expected outputs:
- `final.mp4`, `final.srt`, `result.json`

### dance_loop

Required inputs:
- `inputs.foreground_pngs[]` (one or more dancer cutouts)

Optional inputs:
- `inputs.background` (image/video)

Deterministic parameters:
- `bpm` (int)
- `loop_seconds` (int)
- `preset.motion` (name; e.g., sine sway/bounce)
- `preset.caption_style` (name)
- `timeline[]` (optional; captions/events)

Expected outputs:
- `final.mp4` (loopable), `final.srt`, `result.json`

### flight_composite

Required inputs:
- `inputs.foreground_png`
- `inputs.background` (image/video)

Deterministic parameters:
- `preset.camera` (name; parallax / fake camera preset)
- `preset.blur` (name, optional)
- `preset.caption_style` (name)
- `timeline[]` (optional; captions/events)

Expected outputs:
- `final.mp4`, `final.srt`, `result.json`

------------------------------------------------------------

## Worker Rendering Strategy (v0.1)

- FFmpeg-first pipeline.
- **Resolution Lock**: Production masters are locked to `1080x1080` (Square) at `24 fps`.
- **Smart Scaling**: Vertical assets used in the square 1:1 master are center-cropped for safety.
- Deterministic filtergraphs per archetype.
- Motion presets are math-based and parameterized by fixed integers where possible.
- Captions:
  - `final.srt` is always required output.
  - burn-in is optional and environment-dependent.
- Audio:
  - optional deterministic transforms only (if enabled),
  - no beat detection or analysis in the worker.

------------------------------------------------------------

## Control Plane Strategy (v0.1 → v0.2)

v0.1:
- A local harness can validate, render, rerun, verify determinism, and verify lineage.

v0.2:
- Ralph Loop becomes the canonical control-plane reconciler:
  - validates job.json
  - enforces lineage
  - triggers worker
  - supports retries without changing outputs

------------------------------------------------------------

## Explicit Non-Goals

- No prompt→video generation model pipeline.
- No nondeterministic rendering.
- No LLM usage in the worker.
- No “creative” worker decisions.
- No hidden state or shared-memory coordination.

