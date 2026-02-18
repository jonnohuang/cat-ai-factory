# ComfyUI Workflows In CAF

CAF uses a repo-owned workflow registry pattern:

- `COMFYUI_WORKFLOW_ID=<workflow_id>`
- resolves to `repo/workflows/comfy/<workflow_id>.json`

This keeps workflow authority deterministic and versioned in Git.

## Required Env

In `.env`:

```bash
COMFYUI_BASE_URL=http://127.0.0.1:8188
COMFYUI_WORKFLOW_ID=caf_dance_loop_v1
```

## Default Example

Default workflow file:
- `repo/workflows/comfy/caf_dance_loop_v1.json`

You can create additional workflow files, for example:
- `repo/workflows/comfy/caf_dance_loop_v2.json`
- `repo/workflows/comfy/caf_identity_strict_v1.json`

Then switch by env only:

```bash
COMFYUI_WORKFLOW_ID=caf_identity_strict_v1
```

## Authoring Rules

- Keep workflow JSON in `repo/workflows/comfy/`
- Use stable, descriptive IDs
- Treat workflow file changes like code changes (PR + review)
- Do not depend on external UI state as authority

## Planner Usage Example

```bash
python3 -m repo.services.planner.planner_cli \
  --prompt "Mochi dance loop continuity test" \
  --provider comfyui_video \
  --inbox sandbox/inbox \
  --out sandbox/jobs
```

Expected planner log includes:
- `workflow_id=<your_id>`
- `workflow_path=.../repo/workflows/comfy/<your_id>.json`

## Smoke Test

```bash
python3 -m repo.tools.smoke_planner_comfyui_provider
```

## Failure Modes

If workflow is missing/invalid:
- planner warns and falls back to scaffold behavior
- fix by adding valid JSON at:
  - `repo/workflows/comfy/<workflow_id>.json`
