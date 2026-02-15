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

PR: **PR-23 — Cloud artifact layout (GCS + Firestore mapping)**
Last Updated: 2026-02-15

### Status by Role
- ARCH: Completed
- CODEX: Completed
- CLOUD-REVIEW: Completed (Approved)

### Decisions / ADRs Touched
- ADR-0013 (Cloud State Mapping)
- ADR-0029 (Cloud storage/state mapping)
- ADR-0030 (Signed URL delivery)

### What Changed (Diff Summary)
- `docs/cloud-mapping-firestore.md`: aligned Firestore/GCS mapping content and schema examples.
- `docs/PR_PROJECT_PLAN.md`: PR-23 status set to COMPLETED.
- `docs/now.md`: normalized to status + handoff format.

### Open Findings / Conditions
- None

### Next Action (Owner + Task)
- ARCH: Merge PR-23.

------------------------------------------------------------
