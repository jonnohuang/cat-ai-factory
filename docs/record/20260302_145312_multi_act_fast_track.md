# Walkthrough: Golden Baseline & Multi-Act Long Mode

## Phase 14: Golden Baseline Architecture (PR-58)
Established a new default monolithic pipeline that prioritizing narrative coherence via a storyboard-first execution model.

### 1. Tiered Execution Path
Implemented a 3-tier recovery model in `ralph_loop.py`:
- **Tier-1 (Monolithic)**: Standard path using storyboards + VLM.
- **Tier-2 (Modular)**: Automatic fallback to individual segment rendering if Tier-1 fails.

### 2. Storyboard Integration
Developed `generate_storyboard.py` and `split_contact_sheet.py` workers. The orchestrator now injects these stages before the main render to ensure visual grounding for VLMs.

---

## Phase 15: LTX-2 Draft Engine (PR-59)
Introduced a high-velocity, budget-friendly iteration lane using LTX-2.

### 1. Tier-0 Iteration Lane
Created `repo/worker/render_ltx2.py` as an adapter for LTX-2. This lane bypasses storyboard stages and produces a `draft_video.mp4` for rapid review.

### 2. Fast-Track Promotion
Updated the **Production Supervisor** (ADR-0077) to support a direct transition from Draft to `COMPLETED`:
- **Golden Threshold**: If LTX-2 quality exceeds a specific threshold (e.g., > 0.92), the supervisor recommends `PROCEED`.
- **Shortcut**: `ralph_loop.py` intercepts `PROCEED` for `ltx2_draft` lane and completes the job immediately, bypassing Tier-1.

---

## Phase 16: Multi-Act Golden Baseline (PR-60)
The Multi-Act architecture segments long-duration videos (16-32s) into self-contained "Acts" (approx 8s each). This mitigates identity drift and temporal decay.

### 1. Act Planner & Continuity Contract
Created `repo/services/planner/act_planner.py` (ADR-0076) to:
- Partition long briefs into cohesive acts.
- Generate **Continuity Contracts** (Identity Lock, Emotional State, Environment Baseline) to ensure consistency across segments.

### 2. Act-Aware Orchestration
Updated `ralph_loop.py` to support act-level iteration:
- **Per-Act Storyboards**: Each act gets its own unique storyboard panels.
- **Per-Act Rendering**: Workers (Veo/LTX-2) target act-specific prompts and visual anchors.
- **FFmpeg Stitching**: Final acts are stitched using a lossless `concat` stage for the final deliverable.

### Verification Results (16s Multi-Act)
Verified end-to-end 16s (2-act) sequence stability with mock workers.

```ndjson
{"event": "ACT_START", "details": {"act_id": "act_01"}}
{"event": "ACT_COMPLETED", "details": {"act_id": "act_01"}}
{"event": "ACT_START", "details": {"act_id": "act_02"}}
{"event": "ACT_COMPLETED", "details": {"act_id": "act_02"}}
{"event": "LINEAGE_OK"}
{"event": "COMPLETED"}
```

#### Final Artifact Structure
```
sandbox/output/golden-baseline-16s-multi-act/
├── act_01/
│   ├── act_01.mp4
│   └── storyboard/
├── act_02/
│   ├── act_02.mp4
│   └── storyboard/
├── final.mp4
├── final.srt
└── result.json
```

## Summary of Changes
- [x] Tier-0 LTX-2 Draft Engine with "Fast-Track" promotion.
- [x] Multi-Act Golden Baseline for long-mode videos (16-32s).
- [x] FFmpeg-based act stitching subsystem.
- [x] Act-aware storyboard and video workers.
- [x] Lineage verification support for `draft_video.mp4` and act-folders.
