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

PR: **PR-24 — Cloud Run execution stubs (orchestrator + worker)**
Last Updated: 2026-02-15

### Status by Role
- ARCH: Completed (ready to merge)
- CODEX: Completed (stub implementation + smoke checks)
- CLOUD-REVIEW: Completed (Approved)

### Decisions / ADRs Touched
- ADR-0026 (Phase 7 cloud migration posture)
- ADR-0031 (Cloud asset posture)
- ADR-0038 (Infra provisioning deferred to PR-30)

### What Changed (Diff Summary)
- `docs/PR_PROJECT_PLAN.md`: PR-24 status set to ACTIVE.
- `docs/now.md`: switched ledger from PR-23 closeout to PR-24 kickoff.
- `repo/services/orchestrator/cloud_run_stub.py`: added minimal Cloud Run HTTP stub (`/healthz`, `/trigger`) with deterministic JSON responses and input validation.
- `repo/worker/cloud_run_stub.py`: added minimal Cloud Run HTTP stub (`/healthz`, `/trigger`) with deterministic JSON responses and input validation.

### Open Findings / Conditions
- Sandbox limitation: local socket bind is blocked in this environment, so full HTTP bind/curl smoke tests could not run here.
- Cloud Risk: Stubs rely on IAM (infra layer) for auth; ensure PR-30 restricts public access.
- Non-blocking improvement: add minimal request logging (e.g., `job_id`) in stub POST handlers for Cloud Run connectivity debugging.

### Next Action (Owner + Task)
- ARCH: Merge PR-24 and proceed to PR-25 (Vertex AI providers).

------------------------------------------------------------
