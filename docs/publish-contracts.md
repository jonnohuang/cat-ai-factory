# Ops/Distribution: Publish Contracts & Idempotency

**Status: Proposed (non-binding)**

This document outlines the proposed (non-binding) file contracts for the Ops/Distribution layer. This layer sits outside the core Planner/Control/Worker planes and is responsible for publishing content to external platforms.

References:
- `docs/master.md` (Ops/Distribution Layer)
- `docs/system-requirements.md` (FR-09, SEC-01)
- `docs/architecture.md` (Diagram 3)
- `docs/decisions.md` (ADR-0009)

---

## 1. Core Principle: Derived, Immutable Artifacts

The Ops/Distribution layer **MUST NOT** modify worker outputs. Instead, it creates **derived artifacts** in a dedicated location.

- **Recommended Default (ARCH):** `sandbox/dist_artifacts/`

- **Option B:** `sandbox/outbox/dist_artifacts/`. This might offer clearer semantic separation but adds path depth.

---

## 2. Publish Payload (`<platform>.json`)

This is the derived payload containing all information needed for a publisher adapter to post to a specific platform.

- **Path:** `sandbox/dist_artifacts/<job_id>/<platform>.json`
- **Purpose:** A self-contained, platform-specific input for a publishing tool or Cloud Function.

**Minimal Fields:**
```json
{
  "job_id": "demo-dance-loop-v1",
  "platform": "youtube",
  "publish_config": {
    "title": "Cat Vibing to Lo-fi Beats",
    "description": "Just a cat enjoying some music. #cat #lofi #vibes",
    "tags": ["cat", "lofi", "chill"],
    "privacy": "public"
  },
  "artifact_pointers": {
    "video": "../../output/demo-dance-loop-v1/final.mp4",
    "subtitles": "../../output/demo-dance-loop-v1/final.srt",
    "thumbnail": null
  },
  "lineage": {
    "job_file": "../../jobs/demo-dance-loop-v1.job.json",
    "qc_summary": "../../logs/demo-dance-loop-v1/qc/qc_summary.json"
  }
}
```

---

## 3. Local Idempotency (`<platform>.state.json`)

This file is the local source-of-truth for the publish state of a specific `{job_id, platform}` pair. It prevents duplicate posts. A publisher adapter would check for this file's existence and content before acting.

- **Path:** `sandbox/dist_artifacts/<job_id>/<platform>.state.json`
- **Purpose:** Record the outcome of a publish attempt. The presence of this file for a given idempotency key signifies a completed operation.

**Minimal Fields:**
```json
{
  "job_id": "demo-dance-loop-v1",
  "platform": "youtube",
  "idempotency_key": "demo-dance-loop-v1_youtube",
  "status": "PUBLISHED",
  "published_at": "2026-02-08T12:30:00Z",
  "platform_post_id": "dQw4w9WgXcQ",
  "post_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
}
```
- **Idempotency Key:** The canonical key for preventing duplicate work is the tuple `{job_id, platform}`.

---

## 4. Approval Artifacts (`approve-*.json`)

Following the ingress model of `ADR-0009`, human or automated approvals are delivered via the file-bus into the `inbox`.

- **Recommended Default (ARCH):** `sandbox/inbox/approve-<job_id>-<platform>-<nonce>.json`
  - The `nonce` (e.g., a timestamp or message ID from the source system like Telegram) prevents replay conflicts.

- **Option B:** A new top-level directory like `sandbox/approvals/`. This could simplify inbox processing but introduces a new monitored path.

**Minimal Fields:**
```json
{
  "job_id": "demo-dance-loop-v1",
  "platform": "youtube",
  "approved": true,
  "approved_at": "2026-02-08T12:25:00Z",
  "approved_by": "telegram:user:12345",
  "source": "telegram_bridge",
  "nonce": "msg_aBcDeF12345"
}
```
This structure allows an orchestration tool (like n8n or a simple file watcher) to deterministically gate the creation of the publish payload and the invocation of the publisher itself.
