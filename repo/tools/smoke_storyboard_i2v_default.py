#!/usr/bin/env python3
from __future__ import annotations

import os
import pathlib
import sys

from repo.services.planner.planner_cli import _load_quality_context
from repo.services.planner.providers.vertex_ai import VertexVeoProvider


def _repo_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parents[2]


def main(argv: list[str]) -> int:
    _ = argv
    root = _repo_root()
    quality_context = _load_quality_context(str(root), None)
    storyboard = quality_context.get("storyboard_i2v", {})
    if not isinstance(storyboard, dict):
        print("ERROR: missing storyboard_i2v in quality context", file=sys.stderr)
        return 1

    seed_assets = storyboard.get("seed_frame_assets", [])
    if not isinstance(seed_assets, list) or not seed_assets:
        print("ERROR: storyboard_i2v has no seed_frame_assets", file=sys.stderr)
        return 1

    # Ensure reference-image collection uses storyboard-first defaults.
    os.environ.pop("VERTEX_VEO_DISABLE_REFERENCES", None)
    provider = VertexVeoProvider()
    provider._quality_context = quality_context  # planner wiring entrypoint
    refs = provider._build_veo_reference_images(
        job={"job_id": "smoke-storyboard-i2v", "video": {"length_seconds": 8}},
        prd={"prompt": "Mochi dance loop continuity quality smoke"},
    )
    if not refs:
        print("ERROR: expected non-empty Veo reference images", file=sys.stderr)
        return 1
    if not provider._last_reference_image_rels:
        print("ERROR: missing Veo reference relpath trace", file=sys.stderr)
        return 1

    first_expected = str(seed_assets[0]).strip()
    first_actual = str(provider._last_reference_image_rels[0]).strip()
    if first_actual != first_expected:
        print(
            f"ERROR: expected storyboard-first reference '{first_expected}', got '{first_actual}'",
            file=sys.stderr,
        )
        return 1

    print("OK: storyboard_i2v quality context")
    print("storyboard_relpath:", storyboard.get("relpath"))
    print("seed_frame_assets:", seed_assets)
    print("selected_reference_preview:", provider._last_reference_image_rels[:3])
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
