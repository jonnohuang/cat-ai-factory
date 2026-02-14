# Telegram Commands

This document lists the available commands for the CAF Telegram Bridge.

**Note:** The bridge is an adapter only. It writes instruction artifacts to `/sandbox/inbox/` but does not publish or orchestrate jobs. The bridge MAY include optional *Planner-only* hints (e.g., creativity) in planning artifacts; these do not affect the Worker. All commands require the user to be authorized via `TELEGRAM_ALLOWED_USER_ID`.

## When to use `/daily` vs `/plan`

- **Use `/daily`** for the **canonical daily production brief**: quotas (A/B/C) + today’s theme/brief.  
  Think: “What are we producing today?”

- **Use `/plan`** for **optional planning notes** and **Planner-only hints** (creativity).  
  Think: “How should we interpret the theme or creative direction?”

Both commands are ingress-only and write JSON artifacts to the inbox.

---

## Commands

### `/start`
- **Action:** Displays a welcome message and basic guidance.
- **Artifact:** None.

### `/help`
- **Action:** Displays the command menu.
- **Artifact:** None.

🐾 CAF Telegram Bridge (authorized users only)

Commands:
/style list
/style set <key>
/plan <prompt...>
/daily [--auto-style|--human-style] <brief text...>
/approve <job_id> <platform>
/reject <job_id> <platform> [reason]
/status <job_id> [platform]
/help

Recommended workflow:
1) /style set <key>        (sets default visual style)
2) /plan <prompt...>       (story + creativity hints)
3) /daily A=.. B=.. C=..    (today’s production targets + theme)

Daily plan notes:
- Defaults: auto_style=true
- A/B/C lane numbers are volume targets (jobs/videos), NOT time slots.

Example:
/style set cinematic_lofi
/plan Lane A is a series about Tiger’s corporate failures creativity=canon canon_fidelity=high
/daily --human-style A=2 B=1 C=0 theme: office cats, broken deploys, latte disasters

Note: This bridge only writes inbox artifacts. It does not run the factory.


### `/plan <prompt>`
- **Action:** Creates an optional plan request / planning note.
- **Artifact:** `sandbox/inbox/plan-<nonce>.json` (PlanRequest v1; see `repo/shared/plan_request.v1.schema.json`)

#### Optional modifiers (Planner-only intent)

**Creativity tokens**
- `creativity=canon|balanced|experimental`
- `canon_fidelity=high|medium` (optional; meaningful when `creativity=canon`)

Examples:
- `/plan A=0 B=1 C=2 theme: office cats creativity=canon canon_fidelity=high`
- `/plan theme: cafe drama creativity=experimental`
- `/plan theme: “server room mystery”`
- `/plan A=1 B=0 C=2 theme: night shift cats creativity=balanced notes: lean into slapstick`


### `/daily [--auto-style|--human-style] <brief text...>`
- **Action:** Creates the canonical daily plan (quotas + brief).
- **Artifact:** `sandbox/inbox/daily-plan-<YYYY-MM-DD>-<nonce>.json` (PlanRequest v1; see `repo/shared/plan_request.v1.schema.json`)

Notes:
- Defaults: `--auto-style` if omitted.
- A/B/C lanes are **volume targets** (how many videos/jobs), **not** time slots.

Examples:
- `/daily A=1 B=0 C=2 theme: office cats, barista mishaps`
- `/daily --human-style A=0 B=1 C=1 theme: construction cats, safety goggles`


### `/approve <job_id> <platform>`
- **Action:** Approves a job for publishing to a specific platform.
- **Artifact:** `sandbox/inbox/approve-<job_id>-<platform>-<nonce>.json`

### `/reject <job_id> <platform> [reason]`
- **Action:** Rejects a job for publishing (non-binding; no ADR yet).
- **Artifact:** `sandbox/inbox/reject-<job_id>-<platform>-<nonce>.json`

### `/style list`
- **Action:** Lists available style keys from the manifest.
- **Artifact:** None.

### `/style set <key>`
- **Action:** Writes a style selection request.
- **Artifact:** `sandbox/inbox/style-set-<nonce>.json`

### `/status <job_id> [platform]`
- **Action:** Queries the status of a job.
- **Artifact:** None.

---

## Recommended Workflow (Style + Plan + Daily)

CAF separates three different kinds of human input:

- **Style selection** (`/style set`) = default visual style key
- **Planning** (`/plan`) = creative intent (Planner-only)
- **Daily production** (`/daily`) = lane volumes + daily theme

### Example (Typical Day)

1) Set a default style (rarely changes):
- `/style set cinematic_lofi`

This writes:
- `sandbox/inbox/style-set-<nonce>.json`

2) Send a planning instruction (story):
- `/plan Lane A is a series: “Tiger’s Corporate Disaster Week”.
  Keep canon fidelity high. creativity=canon canon_fidelity=high`

This writes:
- `sandbox/inbox/plan-<nonce>.json`

3) Send today’s production targets:
- `/daily A=2 B=1 C=0 theme: office cats, broken deploys, latte disasters`

This writes:
- `sandbox/inbox/daily-plan-<date>-<nonce>.json`

### Notes

- `/style set` defines a **default style** for future planning and daily output.
- `/plan` may define series direction and optional creativity hints.
- `/daily` defines how many jobs should be generated today in each lane.
- If `/daily` is not sent, no production volume is defined for the day (Planner may still record the plan).

---

## PlanRequest v1 Mapping (Telegram → PlanRequest)

Telegram commands map to PlanRequest v1 fields deterministically.

`/plan` mapping:
- `type`: `plan`
- `source`: `telegram`
- `received_at`: adapter timestamp
- `brief_text`: raw prompt text
- `creativity.mode` and `creativity.canon_fidelity`: from `creativity=...` tokens if present
- `notes`: optional extracted notes

`/daily` mapping:
- `type`: `daily_plan`
- `source`: `telegram`
- `received_at`: adapter timestamp
- `date`: provided date or inferred “today”
- `brief_text`: raw daily brief
- `lanes.a` / `lanes.b` / `lanes.c`: from `A=.. B=.. C=..`
- `theme`: parsed from `theme:` if present

Normalization rules (planner-side, deterministic):
- Missing lane values default to `0`.
- `lanes.*` must be integers `0..10` (values outside range are clamped or rejected).
- `brief_text` is stored as raw input (no semantic rewriting).

Example (daily):
```json
{
  "version": "plan_request.v1",
  "source": "telegram",
  "received_at": "2026-02-14T10:00:00Z",
  "nonce": "msg_12345",
  "type": "daily_plan",
  "date": "2026-02-14",
  "brief_text": "A=1 B=0 C=2 theme: office cats, barista mishaps",
  "lanes": { "a": 1, "b": 0, "c": 2 },
  "theme": "office cats, barista mishaps"
}
```
