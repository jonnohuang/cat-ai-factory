# Telegram Commands

This document lists the available commands for the CAF Telegram Bridge.

**Note:** The bridge is an adapter only. The bridge MAY include optional creativity hints in planning artifacts; these are Planner-only and do not affect the Worker. It writes instruction artifacts to the `/sandbox/inbox/` directory but does not publish or orchestrate jobs. All commands require the user to be authorized via `TELEGRAM_ALLOWED_USER_ID`.

## Commands

### `/start`
- **Action:** Displays a welcome message and basic guidance.
- **Artifact:** None.

### `/help`
- **Action:** Displays the command menu.
- **Artifact:** None.

### `/plan <prompt>`
- **Action:** Creates a new plan request.
- **Artifact:** `sandbox/inbox/plan-<nonce>.json`

Optional modifiers (Planner-only intent):
- `creativity=canon|balanced|experimental`
- `canon_fidelity=high|medium`

Example:
- `/plan A=0 B=1 C=2 theme: office cats | creativity=canon`
- `/plan theme: cafe drama | creativity=experimental canon_fidelity=medium`

### `/approve <job_id>`
- **Action:** Approves a job for publishing.
- **Artifact:** `sandbox/inbox/approve-<job_id>-youtube-<nonce>.json`

### `/reject <job_id> [reason]`
- **Action:** Rejects a job for publishing.
- **Artifact:** `sandbox/inbox/reject-<job_id>-youtube-<nonce>.json`

### `/style list`
- **Action:** Lists available style keys from the manifest.
- **Artifact:** None.

### `/style set <key>`
- **Action:** Writes a style selection request.
- **Artifact:** `sandbox/inbox/style-set-<nonce>.json`

### `/status <job_id> [platform]`
- **Action:** Queries the status of a job.
- **Artifact:** None.
