#!/usr/bin/env python3
from __future__ import annotations

import json
import pathlib
import sys
from typing import Any

try:
    from jsonschema import ValidationError, validate
except Exception:
    ValidationError = Exception
    validate = None


def eprint(*args: Any) -> None:
    print(*args, file=sys.stderr)


def _repo_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parents[2]


def _load(path: pathlib.Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        eprint(
            "Usage: python -m repo.tools.validate_retry_plan path/to/retry_plan.v1.json"
        )
        return 1
    target = pathlib.Path(argv[1]).resolve()
    if not target.exists():
        eprint(f"ERROR: file not found: {target}")
        return 1

    root = _repo_root()
    schema = _load(root / "repo" / "shared" / "retry_plan.v1.schema.json")
    data = _load(target)
    if validate is not None:
        try:
            validate(instance=data, schema=schema)
        except ValidationError as ex:
            eprint(f"SCHEMA_ERROR: {ex.message}")
            return 1
    elif not isinstance(data, dict):
        eprint("SEMANTIC_ERROR: payload must be object")
        return 1

    retry = data.get("retry", {}) if isinstance(data, dict) else {}
    state = data.get("state", {}) if isinstance(data, dict) else {}
    src = data.get("source", {}) if isinstance(data, dict) else {}
    enabled = bool(retry.get("enabled"))
    retry_type = str(retry.get("retry_type", "none"))
    next_attempt = int(retry.get("next_attempt", 0))
    max_retries = int(retry.get("max_retries", 0))
    pass_target = str(retry.get("pass_target", "unknown"))
    terminal_state = str(state.get("terminal_state", "none"))
    action = str(src.get("action", ""))
    seg_retry = retry.get("segment_retry", {}) if isinstance(retry, dict) else {}
    seg_mode = (
        str(seg_retry.get("mode", "none")) if isinstance(seg_retry, dict) else "none"
    )
    seg_targets = (
        seg_retry.get("target_segments", []) if isinstance(seg_retry, dict) else []
    )
    provider_switch = (
        retry.get("provider_switch", {}) if isinstance(retry, dict) else {}
    )
    ps_mode = (
        str(provider_switch.get("mode", "none"))
        if isinstance(provider_switch, dict)
        else "none"
    )
    ps_current = (
        provider_switch.get("current_provider")
        if isinstance(provider_switch, dict)
        else None
    )
    ps_next = (
        provider_switch.get("next_provider")
        if isinstance(provider_switch, dict)
        else None
    )
    ps_idx = (
        provider_switch.get("provider_order_index")
        if isinstance(provider_switch, dict)
        else None
    )
    workflow_preset = (
        retry.get("workflow_preset", {}) if isinstance(retry, dict) else {}
    )
    wp_mode = (
        str(workflow_preset.get("mode", "none"))
        if isinstance(workflow_preset, dict)
        else "none"
    )
    wp_preset_id = (
        workflow_preset.get("preset_id") if isinstance(workflow_preset, dict) else None
    )
    wp_workflow_id = (
        workflow_preset.get("workflow_id")
        if isinstance(workflow_preset, dict)
        else None
    )
    wp_failure_class = (
        workflow_preset.get("failure_class")
        if isinstance(workflow_preset, dict)
        else None
    )

    if enabled and retry_type == "none":
        eprint("SEMANTIC_ERROR: enabled retry requires retry_type != none")
        return 1
    if not enabled and retry_type != "none":
        eprint("SEMANTIC_ERROR: disabled retry requires retry_type == none")
        return 1
    if next_attempt > max_retries and enabled:
        eprint("SEMANTIC_ERROR: enabled retry requires next_attempt <= max_retries")
        return 1
    if retry_type == "motion" and pass_target != "motion":
        eprint("SEMANTIC_ERROR: motion retry requires pass_target=motion")
        return 1
    if retry_type == "recast" and pass_target != "identity":
        eprint("SEMANTIC_ERROR: recast retry requires pass_target=identity")
        return 1
    if retry_type == "none" and pass_target != "unknown":
        eprint("SEMANTIC_ERROR: no retry requires pass_target=unknown")
        return 1
    if retry_type == "motion" and seg_mode == "none":
        eprint("SEMANTIC_ERROR: motion retry requires segment_retry mode != none")
        return 1
    if seg_mode == "retry_selected" and (
        not isinstance(seg_targets, list) or len(seg_targets) == 0
    ):
        eprint("SEMANTIC_ERROR: retry_selected requires target_segments")
        return 1
    if retry_type != "none" and terminal_state != "none":
        eprint(
            "SEMANTIC_ERROR: retry plan cannot be enabled when terminal_state is set"
        )
        return 1
    if terminal_state != "none" and action not in {
        "block_for_costume",
        "escalate_hitl",
    }:
        eprint("SEMANTIC_ERROR: terminal_state requires terminal source action")
        return 1
    if ps_mode not in {"none", "video_provider", "frame_provider"}:
        eprint("SEMANTIC_ERROR: provider_switch.mode invalid")
        return 1
    if ps_mode == "none":
        if ps_next is not None or ps_idx is not None:
            eprint(
                "SEMANTIC_ERROR: provider_switch mode=none requires next_provider/provider_order_index null"
            )
            return 1
    else:
        if not isinstance(ps_current, str) or not ps_current:
            eprint(
                "SEMANTIC_ERROR: provider_switch requires non-empty current_provider"
            )
            return 1
        if not isinstance(ps_next, str) or not ps_next:
            eprint("SEMANTIC_ERROR: provider_switch requires non-empty next_provider")
            return 1
        if ps_current == ps_next:
            eprint(
                "SEMANTIC_ERROR: provider_switch current_provider must differ from next_provider"
            )
            return 1
        if not isinstance(ps_idx, int) or ps_idx < 0:
            eprint(
                "SEMANTIC_ERROR: provider_switch requires non-negative provider_order_index"
            )
            return 1
    if retry_type == "motion" and ps_mode == "frame_provider":
        eprint("SEMANTIC_ERROR: motion retry cannot switch frame provider")
        return 1
    if wp_mode not in {"none", "comfyui_preset"}:
        eprint("SEMANTIC_ERROR: workflow_preset.mode invalid")
        return 1
    if wp_mode == "none":
        if (
            wp_preset_id is not None
            or wp_workflow_id is not None
            or wp_failure_class is not None
        ):
            eprint(
                "SEMANTIC_ERROR: workflow_preset mode=none requires preset/workflow/failure_class null"
            )
            return 1
    else:
        if not isinstance(wp_preset_id, str) or not wp_preset_id:
            eprint(
                "SEMANTIC_ERROR: workflow_preset mode=comfyui_preset requires preset_id"
            )
            return 1
        if not isinstance(wp_workflow_id, str) or not wp_workflow_id:
            eprint(
                "SEMANTIC_ERROR: workflow_preset mode=comfyui_preset requires workflow_id"
            )
            return 1
        if not isinstance(wp_failure_class, str) or not wp_failure_class:
            eprint(
                "SEMANTIC_ERROR: workflow_preset mode=comfyui_preset requires failure_class"
            )
            return 1

    print(f"OK: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
