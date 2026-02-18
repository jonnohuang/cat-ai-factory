# External HITL Recast Workflow

This runbook explains both:
- the default CAF workflow (no external HITL recast)
- the external HITL media-pack/re-ingest path (Viggle-class tools)

## 1) Default Workflow (No External HITL)

This is the normal production path.

Flow:
1. Planner writes `sandbox/jobs/<job_id>.job.json`.
2. Controller runs Worker deterministically.
3. Worker writes:
   - `sandbox/output/<job_id>/final.mp4`
   - `sandbox/output/<job_id>/final.srt` (if present)
   - `sandbox/output/<job_id>/result.json`
4. QC pipeline runs:
   - `qc_report.v1.json`
   - `quality_decision.v1.json`
5. Controller routes deterministically (finalize/retry/fallback/escalate).
6. Ops/Distribution uses bundle/publish artifacts under:
   - `sandbox/dist_artifacts/<job_id>/**`

Notes:
- No external recast service is invoked.
- Worker outputs remain immutable authority artifacts.

## 2) External HITL Recast Workflow

This path is used when quality gates indicate recast/HITL is needed.

Binding boundary:
- External recast is outside factory authority (ADR-0044).
- Worker never calls external recast services directly.

### Step A: Export HITL Media Pack

```bash
python3 -m repo.tools.export_viggle_pack --job-id <job_id>
python3 -m repo.tools.validate_viggle_handoff --job-id <job_id>
```

Expected artifacts:
- `sandbox/dist_artifacts/<job_id>/viggle_pack/viggle_pack.v1.json`
- `sandbox/dist_artifacts/<job_id>/viggle_pack/external_recast_lifecycle.v1.json`

### Step B: Perform External Recast Manually

Operator uses exported pack with external recast tool and obtains recast output media.

### Step C: Create Re-ingest Pointer Artifact

```bash
python3 -m repo.tools.create_viggle_reingest_pointer \
  --job-id <job_id> \
  --recast-video-relpath sandbox/assets/<your_recast_file>.mp4
```

Expected inbox artifact:
- `sandbox/inbox/viggle-reingest-<job_id>-*.json`

### Step D: Process Re-ingest Deterministically

```bash
python3 -m repo.tools.process_viggle_reingest --job-id <job_id>
python3 -m repo.tools.finalize_viggle_reingest --job-id <job_id>
```

### Step E: Re-score Quality + Decide Route

```bash
python3 -m repo.tools.score_recast_quality --job-id <job_id> \
  --video-relpath sandbox/output/<job_id>/final.mp4 \
  --hero-image-relpath sandbox/assets/<hero_ref>.png \
  --tracks-relpath repo/examples/dance_swap_tracks.v1.example.json \
  --subject-id cat-1

python3 -m repo.tools.decide_quality_action --job-id <job_id> --max-retries 2
python3 -m repo.tools.validate_quality_decision sandbox/logs/<job_id>/qc/quality_decision.v1.json
```

### Step F: Continue Controller Routing

Controller reads updated decision artifacts and continues deterministic route.

## 3) Artifact Summary

Default no-HITL core:
- `sandbox/output/<job_id>/final.mp4`
- `sandbox/logs/<job_id>/qc/qc_report.v1.json`
- `sandbox/logs/<job_id>/qc/quality_decision.v1.json`

External HITL additions:
- `sandbox/dist_artifacts/<job_id>/viggle_pack/viggle_pack.v1.json`
- `sandbox/dist_artifacts/<job_id>/viggle_pack/external_recast_lifecycle.v1.json`
- `sandbox/inbox/viggle-reingest-<job_id>-*.json`
- `sandbox/logs/<job_id>/qc/recast_quality_report.v1.json`

## 4) Guardrails

- Factory planes must not write outside their boundaries.
- External HITL artifacts are explicit and auditable via files-as-bus.
- No hidden manual file drops become authority state.
- Production routing authority still comes from QC policy/report contracts.

See also:
- `docs/publish-contracts.md`
- `docs/qc-pipeline-guide.md`
- `docs/lab-mode-runbook.md`
- `docs/decisions.md` (ADR-0044, ADR-0045, ADR-0046)
