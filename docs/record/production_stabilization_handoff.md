# Walkthrough — Production Stabilization & Handoff (PR-PROD / PR-47)

This PR formalizes the **Production Supervisor** layer, transitioning feline video stabilization from ad-hoc tuning to a bounded reasoning system.

## Changes Made

### 1. Specification & Schemas (Architecture)
- **ADR-0068**: Formalized the Supervisor as a Control Plane layer that audits runs and selects repair policies.
- **[production_metrics.v1.schema.json](file:///Users/jonathanhuang/Developer/cat-ai-factory/repo/shared/production_metrics.v1.schema.json)**: Standardized visual and engine diagnostics (pose coverage, stage timing).
- **[production_decision.v1.schema.json](file:///Users/jonathanhuang/Developer/cat-ai-factory/repo/shared/production_decision.v1.schema.json)**: Standardized repair policies (profiles, adjustments, queue management).
- **[workflow_registry.v1.json](file:///Users/jonathanhuang/Developer/cat-ai-factory/repo/shared/workflow_registry.v1.json)**: Created a registry of approved workflows with capability tags (e.g., `hero_safe`).

### 2. Worker Instrumentation (Experience Database)
- **`render_ffmpeg.py`**:
    - Added `_emit_production_metrics` to capture technical diagnostics.
    - Instrumentated the MediaPipe preprocessing loop to track `pose_detection_ratio`.
    - Captured `stage_durations` to identify bottlenecks (MediaPipe stalls vs. ComfyUI render time).
    - Enabled `production_decision` awareness to apply overrides for `max_frames`, `coverage_threshold`, and node-level `parameter_adjustments`.

### 4. Stage-Level QC & Responsibility (Stabilization)
- **`run_qc_runner.py`**: Refactored to support multi-stage gating (Frame, Motion, Video) and map failure classes to `RETRY_STAGE` or `ESCALATE_USER` based on `severity` and `repairable` metadata.
- **`qc_policy.v1.json`**: Enriched with detailed thresholds, target stages, and repairability hints for all key metrics.
- **[user_action_required.v1.schema.json](file:///Users/jonathanhuang/Developer/cat-ai-factory/repo/shared/user_action_required.v1.schema.json)**: Implemented the structured escalation contract for unrecoverable failures.
### 3. Orchestration (Repair Loop)
- **`ralph_loop.py`**: 
    - Updated `classify_action` to support enriched retry and escalation enums.
    - **POSTED State**: Implemented detection of platform-specific distribution artifacts (`ADR-0012`) to transition jobs to the `POSTED` terminal state (PR-47).
    - Integrated with the Supervisor to call for audit on every run and execute stage-level repairs.

### 5. Distribution (Handoff Registry & Cleanup)
- **`handoff_registry.v1.json`**: Established a central ledger for all live/posted content clips (PR-47).
- **`register_handoff.py`**: Created a utility to register successful platform posts and update the global registry.
- **Infrastructure Cleanup**: Purged legacy provider references (`grok`, `meta_ai`, `sora_lab`) from the policy engine and smoke tests.

### 4. Documentation & Planning (Alignment)
- **PR_PROJECT_PLAN.md**: Reconciled PR sequencing to fix the jump from 49 to 110. Renumbered PRs 110-112 to 50-52 and updated the finale to PR-53.
- **Architecture & Requirements**: Formally integrated the **Production Supervisor** and **Experience Database** into:
    - `architecture.md` (Stage-level QC gates added to Production Plane)
    - `system-requirements.md` (FR-33: Stage-Level QC; FR-34: Structured Escalation)
    - `decisions.md` (ADR-0069: Stage-Level QC; ADR-0070: QC Ownership)
    - `AGENTS.md` (Supervisor as sole reasoning authority; Engines as non-self-healing)
    - `qc-pipeline-guide.md` (Responsibility model matrix and stage artifacts)
    - `video-workflow-end-to-end.md` (12-step canonical flow with structured escalation)
    - `master.md` (Core design philosophy)

## Verification Results

### Automated Validation
- **QC Runner Smoke Test**: Verified via `repo/tools/smoke_test_stabilization.py`. Validated Healthy, Motion-Repairable, and Costume-Fatal scenarios.
- **Supervisor Reasoning Test**: Verified via `repo/tools/test_supervisor_reasoning.py`. Validated that the orchestrator correctly generates `production_decision.v1` and `user_action_required.v1` artifacts.
- **Modularization**: Refactored `ralph_loop.py` to move Supervisor and QC logic to module level, enabling these automated tests.
- **Verification**: Verified the `run_qc_runner.py` generates `qc_report.v1.json` with correct severity and target stages.
- **Escalation**: Validated that `ESCALATE_USER` action correctly triggers the creation of `user_action_required.json`.
- **Handoff**: Verified that `ralph_loop.py` detects `.state.json` artifacts and transitions to `POSTED`.
- **Infrastructure Cleanup**: Audited the codebase and removed legacy provider references (`grok`, `meta_ai`, `sora_lab`) from active logic and smoke tests.
- **Orchestration**: Verified `ralph_loop.py` successfully transitions through the supervised repair lifecycle using the new enums.

### Manual Verification
- **Run-0015**: Monitored for MediaPipe stalls; verified that `flush=True` on logs and metrics emission provides clear visibility into stage-by-stage progress.
- **Refactoring**: Verified that `CAF_COMFY_MOTION_MAX_FRAMES` can now be overridden by the Supervisor without environment variable modification.

> [!NOTE]
> The Supervisor currently uses a logic bridge (simulated reasoning) which will be fully automated via Gemini 2.5 in the next phase of the Control Plane expansion.
