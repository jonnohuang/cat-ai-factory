#!/usr/bin/env python3
from __future__ import annotations

import pathlib
import sys

from repo.services.planner.planner_cli import _build_pointer_resolution_artifact


def _repo_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parents[2]


def main() -> int:
    root = _repo_root()
    prd = {"prompt": "Use dance loop choreography with same continuity and hero identity"}
    inbox = []
    job = {
        "job_id": "smoke-pointer-fail-loud",
        "date": "2026-02-19",
        "niche": "cats",
        "video": {"length_seconds": 15, "aspect_ratio": "9:16", "fps": 30, "resolution": "1080x1920"},
        "script": {"hook": "hook", "voiceover": "voiceover text long enough for validation contract path.", "ending": "end"},
        "shots": [{"t": 0, "visual": "v", "action": "a", "caption": "c"} for _ in range(6)],
        "captions": ["c1", "c2", "c3", "c4"],
        "hashtags": ["#cat", "#dance", "#loop"],
        "render": {"background_asset": "sandbox/assets/demo/placeholder.mp4", "subtitle_style": "big_bottom", "output_basename": "x"},
    }
    quality_context = {
        "reverse_analysis": {"analysis_id": "smoke-missing", "pose_checkpoints_relpath": None},
        "pointer_resolver": {"contracts": {}, "promoted_contract_pointers": {}},
    }

    _artifact, unresolved = _build_pointer_resolution_artifact(
        job=job,
        prd=prd,
        inbox_list=inbox,
        quality_context=quality_context,
        project_root=str(root),
    )
    if not unresolved:
        print("ERROR: expected unresolved required pointers for fail-loud smoke", file=sys.stderr)
        return 1
    required = {"motion_contract", "quality_target", "segment_stitch", "continuity_pack"}
    seen = {item.split(":", 1)[0] for item in unresolved}
    if not required.issubset(seen):
        print(f"ERROR: unresolved pointers incomplete, got={sorted(seen)}", file=sys.stderr)
        return 1

    print("OK: planner pointer resolution fail-loud smoke")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
