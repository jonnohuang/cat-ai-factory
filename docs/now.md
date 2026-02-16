# CAF — Now (Status + Handoff Ledger)

Single source of truth for current PR state and cross-role handoff context.
All coordination happens via explicit artifacts; this file is the live ledger.

Update rules:
- Keep edits minimal and factual.
- Do NOT rewrite history; update the current PR block only.
- Use placeholders (no project IDs, buckets, secrets).
- Update at every role handoff and at PR closeout.
- Prefer brief diff summaries, not raw patch text.

------------------------------------------------------------

## Current PR

PR: **PR-31 — Media contracts + analyzer + dance-swap architecture lock (docs/ADRs)**
Last Updated: 2026-02-16

### Status by Role
- ARCH: In Progress
- CODEX: Pending
- CLOUD-REVIEW: Not Required (PR-31 is non-cloud scope)

### Decisions / ADRs Touched
- ADR-0040 (Media Stack v1 contracts)
- ADR-0041 (Video Analyzer planner-side canon contracts)
- ADR-0042 (Dance Swap v1 deterministic lane)
- ADR-0043 (Mode B default stack strategy)
- ADR-0044 (External HITL recast boundary)

### What Changed (Diff Summary)
- `docs/decisions.md`: appended ADR-0040..ADR-0044 to lock media-quality architecture decisions (PR-31 track).
- `docs/PR_PROJECT_PLAN.md`: Phase 7 cloud PRs (PR-26..PR-30) explicitly deferred; Phase 8 media-quality track (PR-31..PR-34) set active.
- `docs/now.md`: switched active ledger to PR-31 for media/contracts architecture lock.

### Open Findings / Conditions
- Roadmap policy:
  - Cloud migration PRs are postponed until quality-video track (PR-31..PR-34) is complete and accepted.
  - Execution order override: Phase 8 runs first; Phase 7 resumes after Phase 8 closeout.
- Boundary lock:
  - Planner authority remains `job.json`; stage manifests cannot bypass contract authority.
  - Worker stays deterministic and output-bound.
- Analyzer lock:
  - metadata/patterns only in canon; no copyrighted media in repo.
  - Worker must not depend on analyzer artifacts.
- External-tool lock:
  - Viggle-class steps are explicit Ops/Distribution HITL flow, not internal Worker logic.
  - Re-ingest is via inbox metadata contract, not ad-hoc hidden manual file drops.

### Next Action (Owner + Task)
- CODEX: open PR-31 implementation branch for docs/contracts-only changes (schemas + canon placement + lifecycle wording).
- ARCH: prepare PR-32 CODEX handoff prompt (analyzer contract implementation scope only).

### ARCH Decision Queue Snapshot (PR-31 Baseline)
1) Media Stack v1:
- Approved with modification: planner authority (`job.json`) is preserved.
- ADR required and now locked (ADR-0040).

2) Video Analyzer contracts:
- Approved as planner enrichment layer.
- Metadata-only canon and index/query contracts.
- ADR required and now locked (ADR-0041).

3) Dance Swap v1 lane:
- Approved as deterministic choreography-preserving replacement lane.
- Explicit tracks/masks/loop artifacts.
- ADR required and now locked (ADR-0042).

4) External stack strategy (Mode B):
- Approved as default: deterministic daily path + optional premium hosted generation.
- ADR required and now locked (ADR-0043).

5) 3-plane wording clarification:
- Approved wording: "3-plane orchestration with a multi-stage deterministic Worker production pipeline."
- Reflected in architecture narrative updates for PR-31 docs scope.

6) Viggle-class integration:
- Approved with boundary correction:
  - external Ops/Distribution HITL only
  - explicit pack export and re-ingest contracts
  - no hidden manual authority.
- ADR required and now locked (ADR-0044).

------------------------------------------------------------
