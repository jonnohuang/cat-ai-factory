# MILESTONE — local v0.1 (Prompt Brief)

This is a **non-authoritative** implementation brief for local v0.1.
Authoritative sources: `docs/decisions.md` (ADRs), `docs/master.md` (invariants), `docs/architecture.md` (flows).

Goal: one command produces reproducible artifacts from `PRD.json → job.json → outputs`, fully sandboxed.

------------------------------------------------------------

## Deliverables

### 1) Job contract v1 is explicit and validated
- `job.json` is versioned and validates against `repo/shared/job.schema.json`.
- At least one golden example exists under `/sandbox/jobs/`.
- Contract includes a stable job identifier and schema version.

### 2) Worker is deterministic + idempotent
- Same `job.json` + same assets → same outputs (within documented tolerance).
- Re-running does not produce conflicting artifacts.
- Outputs include:
  - video (`.mp4`)
  - captions (`.srt`)
  - logs (per job run)

### 3) Artifact lineage is auditable
For each job-id, artifacts are organized so lineage is obvious:
- job contract: `/sandbox/jobs/<job-id>.job.json`
- outputs: `/sandbox/output/<job-id>/final.mp4` and `final.srt` (or equivalent stable layout)
- logs: `/sandbox/logs/<job-id>.*`
- optional run metadata: checksums/tool versions/timings (as a file, not implicit state)

### 4) Sandbox boundaries are enforceable
- Containers write only under `/sandbox`.
- No writes to repo paths.
- No secrets in Git.

------------------------------------------------------------

### Demo sample pack (optional)
- Demo jobs: `demo-dialogue-reaction.job.json`, `demo-meme-narrative.job.json`, `demo-dance-loop.job.json`, `demo-flight-composite.job.json`.
- Assets live under `/sandbox/assets/demo/` with provenance in `LICENSE.txt`.
- Example run: `python3 repo/tools/local_v0_1_harness.py sandbox/jobs/demo-dialogue-reaction.job.json`.

------------------------------------------------------------

## Non-goals (explicit)

- Cloud deployment (Cloud Run / Pub/Sub / GCS / Firestore).
- New architecture or plane changes.
- Any LLM usage outside the Planner.
- Any agent authority that modifies artifacts outside its allowed plane.

## Optional: Demo sample pack (PR3.5)

Demo jobs (bring your own `sandbox/assets/demo/bg.mp4`):
- sandbox/jobs/demo-dialogue-reaction.job.json
- sandbox/jobs/demo-meme-narrative.job.json
- sandbox/jobs/demo-dance-loop.job.json
- sandbox/jobs/demo-flight-composite.job.json

Run one:
- python3 repo/tools/local_v0_1_harness.py sandbox/jobs/demo-dialogue-reaction.job.json
