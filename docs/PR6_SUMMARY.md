# PR6 — Verification / QC Agent

PR6 adds a deterministic, read-only QC gate for a single job contract and its artifacts.

## What QC checks

- **Job schema validation**
  - Validates `job.json` against `repo/shared/job.schema.json` via `repo/tools/validate_job.py`.

- **Artifact lineage verification**
  - Verifies required lineage (job → outputs → logs/state) via `repo/tools/lineage_verify.py`.

- **Output presence / conformance**
  - Required:
    - `/sandbox/output/<job_id>/final.mp4` exists and is non-empty
    - `/sandbox/output/<job_id>/result.json` exists and is non-empty
  - Optional (non-strict mode):
    - `/sandbox/output/<job_id>/final.srt`

- **result.json integrity**
  - If `result.json` is missing: FAIL
  - If present: must be parseable JSON
  - If `job_id` exists inside `result.json`, it must match filename-derived `<job_id>`

## Outputs (QC artifacts)

QC writes logs/results only under:

- `/sandbox/logs/<job_id>/qc/qc.log`
- `/sandbox/logs/<job_id>/qc/qc_summary.json`

No mutation of `job.json` or worker outputs.

## Exit codes

- `0` — PASS (all checks passed)
- `2` — FAIL (one or more QC checks failed)
- `1` — ERROR (usage/runtime error)
