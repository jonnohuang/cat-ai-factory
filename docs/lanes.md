# Lane Contracts & Invariants

Cat AI Factory uses **lanes** to define different production strategies for daily content.
Lanes are a contract-level concept that informs the Planner and Ops/Distribution layers,
but they **do not change the core Worker invariant**.

## Lane Identifiers

PR17 represents lane intent via an optional `lane` field in `job.json`. If present, it must be one of:

| Lane ID | Intent | Worker Behavior |
|---|---|---|
| `ai_video` | Premium / High Cost. Uses external generation APIs (Planner-side). | Standard deterministic render. |
| `image_motion` | Low Cost / Scalable. Uses seed images + motion presets. | Standard deterministic render. |
| `template_remix` | Near-Free / Scalable. Uses existing assets/templates. | Standard deterministic render. |

If `lane` is omitted, the job is treated as a generic/legacy job (fully supported).

> **Planning Note**: PR17 establishes these identifiers as planning intent only. Future PRs (PR18/PR19) will add lane-specific recipes and logic.

## Invariants

- **Worker Determinism**: The Worker does not know or care about "lanes". It simply renders `job.json` + assets.
- **Output Stability**: Regardless of lane, the canonical worker outputs are ALWAYS:
  - `/sandbox/output/<job_id>/final.mp4`
  - `/sandbox/output/<job_id>/final.srt` (if captions are present)
  - `/sandbox/output/<job_id>/result.json`
- **No LLM in Worker**: "AI Video" generation happens in the Planner plane (or pre-worker), delivering video assets to the Worker. The Worker never calls generation APIs.
