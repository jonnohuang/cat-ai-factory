#!/usr/bin/env python3
from __future__ import annotations

import sys
from typing import Any, Callable

from repo.worker import render_ffmpeg as rf


def _expect_system_exit(fn: Callable[[], Any], needle: str) -> None:
    try:
        fn()
    except SystemExit as exc:
        msg = str(exc)
        if needle not in msg:
            raise AssertionError(f"expected error containing {needle!r}, got {msg!r}") from exc
        return
    raise AssertionError("expected SystemExit, but call succeeded")


def main(argv: list[str]) -> int:
    _ = argv
    workflow_doc = {
        "caf_capabilities": {
            "required_node_ids": ["10", "20"],
            "required_node_classes": ["CheckpointLoaderSimple", "KSampler"],
        }
    }
    prompt_graph = {"10": {"class_type": "CheckpointLoaderSimple"}}

    original_object_info = rf._comfy_object_info
    original_resolve_checkpoint = rf._comfy_resolve_checkpoint
    try:
        rf._comfy_object_info = lambda _base_url: {"CheckpointLoaderSimple": {}, "KSampler": {}}
        rf._comfy_resolve_checkpoint = lambda _base_url: "smoke.safetensors"
        _expect_system_exit(
            lambda: rf._comfy_preflight_capabilities(
                base_url="http://127.0.0.1:8188",
                workflow_doc=workflow_doc,
                prompt_graph=prompt_graph,
            ),
            "missing required node ids",
        )

        prompt_graph["20"] = {"class_type": "KSampler"}
        rf._comfy_object_info = lambda _base_url: {"CheckpointLoaderSimple": {}}
        _expect_system_exit(
            lambda: rf._comfy_preflight_capabilities(
                base_url="http://127.0.0.1:8188",
                workflow_doc=workflow_doc,
                prompt_graph=prompt_graph,
            ),
            "required node classes unavailable",
        )

        rf._comfy_object_info = lambda _base_url: {"CheckpointLoaderSimple": {}, "KSampler": {}}
        out = rf._comfy_preflight_capabilities(
            base_url="http://127.0.0.1:8188",
            workflow_doc=workflow_doc,
            prompt_graph=prompt_graph,
        )
    finally:
        rf._comfy_object_info = original_object_info
        rf._comfy_resolve_checkpoint = original_resolve_checkpoint

    if out.get("required_node_count") != 2:
        print("ERROR: expected required_node_count=2", file=sys.stderr)
        return 1
    if out.get("required_class_count") != 2:
        print("ERROR: expected required_class_count=2", file=sys.stderr)
        return 1
    if out.get("checkpoint_name") != "smoke.safetensors":
        print("ERROR: expected checkpoint_name from resolver", file=sys.stderr)
        return 1

    print("OK: comfy capability preflight smoke")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
