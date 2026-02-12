# Telegram Commands

This document lists the available commands for the CAF Telegram Bridge.

**Note:** The bridge is an adapter only. It writes instruction artifacts to `/sandbox/inbox/` but does not publish or orchestrate jobs. The bridge MAY include optional *Planner-only* hints (e.g., creativity/continuity) in planning artifacts; these do not affect the Worker. All commands require the user to be authorized via `TELEGRAM_ALLOWED_USER_ID`.

## When to use `/daily` vs `/plan`

- **Use `/daily`** for the **canonical daily production brief**: quotas (A/B/C) + today’s theme/brief.  
  Think: “What are we producing today?”

- **Use `/plan`** for **optional planning notes** and **Planner-only hints** (creativity + continuity).  
  Think: “How should we interpret canon / series / hooks?”

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
/approve <job_id>
/reject <job_id> [reason]
/status <job_id> [platform]
/help

Recommended workflow:
1) /style set <key>        (sets default visual style)
2) /plan <prompt...>       (story + continuity + creativity hints)
3) /daily A=.. B=.. C=..    (today’s production targets + theme)

Daily plan notes:
- Defaults: auto_style=true
- A/B/C lane numbers are volume targets (jobs/videos), NOT time slots.

Example:
/style set cinematic_lofi
/plan Lane A is a canon series about Tiger’s corporate failures creativity=canon canon_fidelity=high
/daily --human-style A=2 B=1 C=0 theme: office cats, broken deploys, latte disasters

Note: This bridge only writes inbox artifacts. It does not run the factory.


### `/plan <prompt>`
- **Action:** Creates an optional plan request / planning note.
- **Artifact:** `sandbox/inbox/plan-<nonce>.json`

#### Optional modifiers (Planner-only intent)

**Creativity tokens**
- `creativity=canon|balanced|experimental`
- `canon_fidelity=high|medium` (optional; meaningful when `creativity=canon`)

**Continuity tokens**
- `series=<kebab-id>`  
  Selects an arc/series identifier (e.g., `office-ops`, `construction-crew`).
- `continuity=on|off`  
  `on` = strongly enforce canon; `off` = canon violations allowed.
- `hook="<text>"`  
  A next-episode hook to carry forward (quotes recommended).
- `must_include=<hero_id,hero_id>`  
  Comma-separated hero IDs that must appear (best-effort).
- `avoid=<tag,tag>`  
  Comma-separated tags/topics to avoid (best-effort).

Token parsing rules:
- Tokens may appear anywhere in the prompt.
- The bridge may remove recognized tokens from `brief_text` and write parsed fields into optional objects.
- Unknown/invalid token values are ignored (best-effort; bridge should not crash).

Examples:
- `/plan A=0 B=1 C=2 theme: office cats creativity=canon canon_fidelity=high continuity=on series=office-ops hook="glowing bug returns"`
- `/plan theme: cafe drama creativity=experimental continuity=off`
- `/plan must_include=tiger-black,mochi-grey-tabby avoid=politics,violence theme: “server room mystery”`


### `/daily [--auto-style|--human-style] <brief text...>`
- **Action:** Creates the canonical daily plan (quotas + brief).
- **Artifact:** `sandbox/inbox/daily-plan-<YYYY-MM-DD>-<nonce>.json`

Notes:
- Defaults: `--auto-style` if omitted.
- A/B/C lanes are **volume targets** (how many videos/jobs), **not** time slots.

Examples:
- `/daily A=1 B=0 C=2 theme: office cats, barista mishaps`
- `/daily --human-style A=0 B=1 C=1 theme: construction cats, safety goggles`


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

---

## Artifact Shape Contracts (Reference)

This section documents the expected JSON shapes written by the bridge.
These are **not** schemas; they are human-readable contracts.

### Daily Plan Artifact
Path:
- `sandbox/inbox/daily-plan-<YYYY-MM-DD>-<nonce>.json`

Example:
{
  "source": "telegram",
  "received_at": "2026-02-11T18:30:00Z",
  "command": "daily_plan",
  "date": "2026-02-11",
  "brief_text": "A=1 B=0 C=2 theme: office cats, barista mishaps",
  "auto_style": true,
  "approved_by": "telegram:123456789",
  "nonce": "987654321"
}

Invariants:
- `command` MUST be `"daily_plan"`.
- `brief_text` MUST be a single string.
- The bridge MUST NOT overwrite an existing daily-plan artifact.

### Plan Artifact
Path:
- `sandbox/inbox/plan-<nonce>.json`

Example (no tokens):
{
  "source": "telegram",
  "received_at": "2026-02-11T18:31:00Z",
  "command": "plan",
  "brief_text": "theme: cafe drama",
  "nonce": "987654322"
}

Example (with tokens parsed):
{
  "source": "telegram",
  "received_at": "2026-02-11T18:32:00Z",
  "command": "plan",
  "brief_text": "theme: office cats",
  "creativity": {
    "mode": "canon",
    "canon_fidelity": "high"
  },
  "continuity": {
    "series": "office-ops",
    "continuity": "on",
    "hook": "glowing bug returns",
    "must_include": [
      "tiger-black",
      "mochi-grey-tabby"
    ],
    "avoid": [
      "politics",
      "violence"
    ]
  },
  "nonce": "987654323"
}

Invariants:
- `command` MUST be `"plan"`.
- `creativity` MUST be omitted if no valid creativity tokens exist.
- `continuity` MUST be omitted if no valid continuity tokens exist.
- The bridge MUST NOT overwrite an existing plan artifact.
- Unknown tokens MUST NOT crash the bridge.

## Recommended Workflow (Style + Plan + Daily)

CAF separates three different kinds of human input:

- **Style selection** (`/style set`) = default visual style key
- **Planning** (`/plan`) = creative intent + continuity hints (Planner-only)
- **Daily production** (`/daily`) = lane volumes + daily theme

### Example (Typical Day)

1) Set a default style (rarely changes):
- `/style set cinematic_lofi`

This writes:
- `sandbox/inbox/style-set-<nonce>.json`

2) Send a planning instruction (story + continuity):
- `/plan Lane A is a continuity series: “Tiger’s Corporate Disaster Week”.
  Keep canon fidelity high. creativity=canon canon_fidelity=high`

This writes:
- `sandbox/inbox/plan-<nonce>.json`

3) Send today’s production targets:
- `/daily A=2 B=1 C=0 theme: office cats, broken deploys, latte disasters`

This writes:
- `sandbox/inbox/daily-plan-<date>-<nonce>.json`

### Notes

- `/style set` defines a **default style** for future planning and daily output.
- `/plan` may define continuity, series direction, and optional creativity hints.
- `/daily` defines how many jobs should be generated today in each lane.
- If `/daily` is not sent, no production volume is defined for the day (Planner may still record the plan).
