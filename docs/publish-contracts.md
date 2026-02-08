# Ops/Distribution: Publish Contracts & Idempotency

**Status: Proposed (non-binding)**

**Note:** The recommended defaults in this document have been accepted and are now binding. See `docs/decisions.md` (ADR-0010..ADR-0013).

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
  "assets": {
    "video_path": "/sandbox/output/demo-dance-loop-v1/final.mp4",
    "caption_path": "/sandbox/output/demo-dance-loop-v1/final.srt"
  },
  "metadata": {
    "title": "Video for Job demo-dance-loop-v1",
    "description": "Content generated for job_id: demo-dance-loop-v1",
    "tags": ["cat-ai-factory", "ai-generated"]
  },
  "created_at": "2026-02-08T12:25:00Z"
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
  "status": "POSTED",
  "attempts": 1,
  "last_attempt_at": "2026-02-08T12:30:00Z",
  "platform_post_id": "dQw4w9WgXcQ",
  "post_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
}
```
- **Idempotency Key:** The canonical key for preventing duplicate work is the tuple `{job_id, platform}`. Any string encoding (like "<job_id>_<platform>") is an optional, non-normative implementation detail.

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

---

## 5. Publishing Workflow (MVP Example)

The `repo/tools/publish_youtube.py` script provides a local, dry-run implementation of the publishing workflow, governed by the binding contracts in `ADR-0010` through `ADR-0013`.

### Step 1: Approve the Job for Publishing

Create an approval artifact in the `sandbox/inbox/` directory. The script will deterministically select the lexicographically newest file matching the pattern.

**Command:**
```bash
# Example for job_id 'demo-dance-loop-v1'
TS=$(date +%s)
cat > sandbox/inbox/approve-demo-dance-loop-v1-youtube-${TS}.json <<EOF
{
  "job_id": "demo-dance-loop-v1",
  "platform": "youtube",
  "approved": true,
  "approved_at": "$(date -u +'%Y-%m-%dT%H:%M:%SZ')",
  "approved_by": "user:local",
  "source": "manual_cli",
  "nonce": "${TS}"
}
EOF
```

### Step 2: Run the Publisher

Execute the script, targeting the `job_id`. The script defaults to a safe `--dry-run` mode.

**Command:**
```bash
python3 -m repo.tools.publish_youtube --job-id demo-dance-loop-v1
```

**On success, the script will:**
1. Validate the approval artifact.
2. Verify the required worker outputs exist (e.g., `sandbox/output/demo-dance-loop-v1/final.mp4`).
3. Create the derived distribution artifacts:
   - `sandbox/dist_artifacts/demo-dance-loop-v1/youtube.json` (the payload)
   - `sandbox/dist_artifacts/demo-dance-loop-v1/youtube.state.json` (the idempotency lock)
4. Print a dry-run message and exit `0`.

Running the command a second time will result in a no-op due to the idempotency check against the `.state.json` file.
