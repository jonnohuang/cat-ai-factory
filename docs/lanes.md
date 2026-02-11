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

If `lane="template_remix"`, the job contract must include:
```json
"template": {
  "template_id": "simple_remix",
  "params": { ... }
}
```
The Worker will enforce that:
1. `template.template_id` exists in the registry.
2. All `required_inputs` are present in the job contract.
