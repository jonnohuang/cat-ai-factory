# Lane Contracts & Invariants

Cat AI Factory uses **lanes** to define different production strategies for daily content.
Lanes are a contract-level concept that informs the Planner and Ops/Distribution layers,
but they **do not change the core Worker invariant**.

## Lane Identifiers

Lane intent is represented via an optional `lane` field in `job.json`. If present, it must be one of:

| Lane ID | Intent | Worker Behavior |
|---|---|---|
| `ai_video` | Premium / High Cost. Uses external generation APIs (Planner-side). | Standard deterministic render. |
| `high_perf_motion` | High-Perf / High Quality. Uses Wan 2.2 on local GPUs. | **High-Perf GPU Worker** (MIG-enabled). |
| `image_motion` | Low Cost / Scalable. Uses seed images + motion presets. | Standard deterministic render. |
| `template_remix` | Near-Free / Scalable. Uses existing assets/templates. | Standard deterministic render. |

If `lane` is omitted, the job is treated as a generic/legacy job (fully supported).

> **Planning Note**: Lanes are non-binding hints (ADR-0014, ADR-0038). The schema must remain permissive and must not require lane-specific blocks.

## Invariants

- **Worker Determinism**: The Worker MAY route based on explicit blocks (e.g., `image_motion`, `template`) to select a deterministic recipe. Lane is a hint only. Routing must be deterministic and must not change output paths. The Worker remains fully deterministic: it renders only from `job.json` + sandbox assets and never calls LLMs or networks.
- **Output Stability**: Regardless of lane, the canonical worker outputs are ALWAYS:
  - `/sandbox/output/<job_id>/final.mp4` (locked to **1080x1080 @ 24fps**)
  - `/sandbox/output/<job_id>/final.srt` (if captions are present)
  - `/sandbox/output/<job_id>/result.json`
- **No LLM in Worker**: "AI Video" or generative motion synthesis happens in the Planner plane or specialized GPU worker lanes. The standard Worker never calls generation APIs.
- **Hardware Affinity**: Jobs explicitly requesting `high_perf_motion` or the `wan_2_2` engine MUST be routed to **MIG-enabled GPU nodes** (L4 or better). All other lanes remain CPU-compatible.
- **Planner-side generation allowed**: Seed frames or templates MAY be generated planner-side and treated as explicit inputs. Worker remains deterministic.

## Template Registry (Lane C)

For `lane="template_remix"`, the Worker resolves the `template_id` from a local contract:
- **Registry Path**: `repo/assets/templates/template_registry.json`
- **Schema**:
  ```json
  {
    "version": "1.0",
    "templates": {
      "<template_id>": {
        "recipe_id": "standard_render",
        "description": "Human-readable spec",
        "required_inputs": ["render.background_asset"],
        "default_params": {}
      }
    }
  }
  ```
- **Allowed Keys**:
  - `recipe_id`: Identifier for the deterministic rendering logic (e.g., `standard_render`).
  - `description`: Human-readable description of the template.
  - `required_inputs`: List of job contract field paths (e.g., `render.background_asset`) that must be present.
  - `default_params`: Default values for template parameters.

> [!IMPORTANT]
> All input paths defined in `required_inputs` (e.g. background assets) are **sandbox-relative**. The Worker validates them using `validate_safe_path()` to ensure they do not escape the sandbox environment.

If a `template` block is present, the job contract should include:
```json
"template": {
  "template_id": "simple_remix",
  "params": { ... }
}
```
The Worker will enforce that:
1. `template.template_id` exists in the registry.
2. All `required_inputs` are present in the job contract.
