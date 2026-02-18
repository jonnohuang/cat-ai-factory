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

Optional CAF-managed runtime env:

```bash
COMFYUI_HOME=sandbox/third_party/ComfyUI
COMFYUI_HOST=127.0.0.1
COMFYUI_PORT=8188
COMFYUI_PYTHON_BIN=python3
# Leave empty for default GPU/MPS runtime; use --cpu only as fallback.
COMFYUI_EXTRA_ARGS=
COMFYUI_CHECKPOINT_NAME=
COMFYUI_CHECKPOINT_URL=
CAF_COMFY_MOTION_FPS=2
CAF_COMFY_MOTION_MAX_FRAMES=24
```

## CAF-Managed Runtime

You can manage ComfyUI from CAF directly:

```bash
# one-time clone into sandbox/third_party/ComfyUI
python3 -m repo.tools.manage_comfy_runtime install

# one-time dependency setup inside ComfyUI checkout
python3 -m repo.tools.manage_comfy_runtime setup

# start runtime (detached)
python3 -m repo.tools.manage_comfy_runtime start

# check status
python3 -m repo.tools.manage_comfy_runtime status

# stop runtime
python3 -m repo.tools.manage_comfy_runtime stop
```

Runtime logs:
- `sandbox/logs/comfyui/comfyui.runtime.log`

`setup` creates and uses:
- `sandbox/third_party/ComfyUI/.venv`

`start` automatically prefers that venv Python if present.

Default runtime is GPU/MPS when available. If your torch build crashes on startup,
set extra args for CPU fallback:

```bash
COMFYUI_EXTRA_ARGS=--cpu
```

Dependency source order for `setup`:
1. `requirements-comfy-runtime.txt` (CAF-managed baseline)
2. `sandbox/third_party/ComfyUI/requirements.txt`
3. `sandbox/third_party/ComfyUI/manager_requirements.txt`

If API is reachable:

```bash
curl http://127.0.0.1:8188/system_stats
```

For checkpoint bootstrap (optional, enables style/identity synthesis workflows):

```bash
python3 -m repo.tools.bootstrap_comfy_checkpoint \
  --url "<checkpoint_download_url>" \
  --filename "<model_name>.safetensors"
```

## Default Example

Default workflow file:
- `repo/workflows/comfy/caf_dance_loop_v1.json`

Current default behavior of `caf_dance_loop_v1`:
- motion frame sequence (dance continuity preserved from source clip)
- Comfy processes source frames and CAF stitches the result into video
- no checkpoint required for baseline pass-through motion mode

If your workflow includes `__CAF_CHECKPOINT__` placeholder:
- at least one checkpoint must exist in `ComfyUI/models/checkpoints`
- set `COMFYUI_CHECKPOINT_NAME` to pin a specific model

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

## One-Command End-to-End (Pinned To Demo Dance Loop)

```bash
python3 -m repo.tools.run_comfy_video_job \
  --prompt "Use demo dance loop choreography, hero Mochi in dinosaur costume, same dance continuity" \
  --auto-start-comfy
```

Defaults:
- `--analysis-id dance-loop`
- `--ignore-inbox` (deterministic pointer pinning)

## Failure Modes

If workflow is missing/invalid:
- planner warns and falls back to scaffold behavior
- fix by adding valid JSON at:
  - `repo/workflows/comfy/<workflow_id>.json`
