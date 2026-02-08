# Ops/Distribution: Cloud Mapping (Firestore)

**Status: Proposed (non-binding)**

This document proposes a non-binding schema for mapping the local file-bus artifacts to a cloud-native state and artifact store, using Google Firestore and Cloud Storage (GCS).

This mapping is critical for enabling cloud-based orchestration (Phase 4) and scalable Ops/Distribution workflows (Phase 3).

References:
- `docs/architecture.md` (Diagram 3 - Cloud Surfaces)
- `docs/publish-contracts.md` (Local Artifacts)

---

## 1. Collections and Documents

The proposed structure uses a top-level `jobs` collection, with each job having a `publishes` subcollection. This allows for clean separation of core job data from platform-specific publish attempts.

- **Recommended Default (ARCH):**
  - `jobs/{job_id}`
  - `jobs/{job_id}/publishes/{platform}`

This structure is query-friendly and scales well. The `{job_id}` and `{platform}` are the natural keys.

---

## 2. `jobs/{job_id}` Document

This document acts as the central record for a job, mirroring the state managed by the Ralph Loop orchestrator.

**Minimal Fields:**
```
{
  // Core Job Info
  "job_id": "string",
  "status": "string (e.g., COMPLETED, FAILED)",
  "created_at": "timestamp",
  "completed_at": "timestamp",

  // Artifact Pointers (immutable)
  "artifacts": {
    "job_file_gcs": "gs://<bucket>/jobs/archive/<job_id>.job.json",
    "final_mp4_gcs": "gs://<bucket>/output/<job_id>/final.mp4",
    "final_srt_gcs": "gs://<bucket>/output/<job_id>/final.srt",
    "result_json_gcs": "gs://<bucket>/output/<job_id>/result.json"
  },

  // QC & Lineage Pointers
  "verification": {
    "qc_summary_gcs": "gs://<bucket>/logs/<job_id>/qc/qc_summary.json",
    "lineage_ok": "bool",
    "qc_passed": "bool"
  },

  // Timestamps
  "timestamps": {
    "created": "timestamp",
    "orchestrator_start": "timestamp",
    "worker_start": "timestamp",
    "worker_end": "timestamp",
    "orchestrator_end": "timestamp"
  }
}
```

---

## 3. `jobs/{job_id}/publishes/{platform}` Document

This document records the state of a publish action for a single platform, serving as the cloud-native idempotency lock.

**Minimal Fields:**
```
{
  // Publish State
  "platform": "string (e.g., youtube, tiktok)",
  "status": "string (e.g., PENDING_APPROVAL, APPROVED, PUBLISHED, FAILED)",
  "idempotency_key": "string (e.g., <job_id>_<platform>)",

  // Outcome
  "platform_post_id": "string",
  "post_url": "string",
  "error_message": "string (if FAILED)",

  // Approval Info
  "approval": {
    "approved_by": "string",
    "approved_at": "timestamp",
    "source": "string (e.g., slack, n8n_webhook)"
  },

  // Timestamps
  "timestamps": {
    "created_at": "timestamp",
    "updated_at": "timestamp",
    "published_at": "timestamp"
  }
}
```

This schema provides a robust, retry-safe mechanism for managing publishing workflows in a distributed, event-driven cloud environment. An external system (like a Cloud Function triggered by Pub/Sub) can safely attempt to publish, checking and then setting the document in this subcollection within a transaction to guarantee idempotency.
