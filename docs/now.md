# CAF — Now (Status + Handoff Ledger)

Single source of truth for current PR state and cross-role handoff context.
All coordination happens via explicit artifacts; this file is the ledger.

Update rules:
- Keep edits minimal and factual.
- Do NOT rewrite history; update the current PR block only.
- Use placeholders (no project IDs, buckets, secrets).
- Update at every role handoff and at PR closeout.
- Prefer brief diff summaries, not raw patch text.

------------------------------------------------------------

### 4. Current PR Status (PR-58: Golden Baseline Architecture)
Status: **COMPLETED**

#### Phase 14: Golden Baseline Pipeline
- **Status**: **COMPLETE**
- **Action**: Refactored the factory default execution path to a monolithic VLM sequence rooted in a storyboard contact sheet.
- **Outcome**: Deterministic narrative and identity coherence, isolating complex multi-engine routing to Tier-2 recovery pathways.

### 5. Current PR Status (PR-59: LTX-2 Draft Engine)
Status: **COMPLETED**

#### Phase 15: Iteration Speed — Draft Engines
- **Status**: **COMPLETE**
- **Action**: Integrated LTX-2 as a budget-first draft/iteration layer with automated Promotion Gate logic and "Fast-Track" bypass.
- **Outcome**: Faster iteration on motion and style experiments with budget isolation. High-quality drafts can now bypass Tier-1 rendering entirely.

### 6. Current PR Status (PR-60: Multi-Act Golden Baseline)
Status: **COMPLETED / HAND-OFF**

#### Phase 16: Multi-Act — Long Mode
- **Status**: **COMPLETE**
- **Action**: Implemented structural narrative partitioning (Acts) and continuity contracts for 16-32s video generation.
- **Outcome**: Stable, cohesive long-form content with identity-lock and temporal consistency through segment-based rendering and stitching.

### Decisions / ADRs Touched
- ADR-0074: Golden Baseline Architecture (Tier-1 Monolithic VLM vs Tier-2 Modular Fallback)
- ADR-0075: LTX-2 Draft/Iteration Engine (Tier-0 Selection Path)
- ADR-0076: Multi-Act Narrative Partitioning (Long Mode)
- ADR-0077: Tier-0 Fast-Track Promotion

### What Changed (Diff Summary)
- Core architectural documentation updated (ADR-0076, ADR-0077).
- `act_planner.py` service implemented for long-mode segmentation.
- `ralph_loop.py` updated with act-based iteration, lossless stitching, and fast-track promotion logic.
- Storyboard and video workers updated to be act-aware and support continuity contracts.

### Open Findings / Conditions
- None. Verification complete with mock workers.

### ARCH Invariant Status
1) **Three-plane separation**: **LOCKED**
2) **Files-as-bus**: **LOCKED** (Act-specific folders and contracts)
3) **Narrative Intent**: **ENFORCED** (Acts + Continuity Contracts)
4) **Budget Safety**: **ENFORCED** (Fast-Track promotion for early successes)
