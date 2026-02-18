#!/usr/bin/env python3
from __future__ import annotations

import pathlib
import sys

from repo.services.planner.planner_cli import _load_quality_context


def main() -> int:
    root = pathlib.Path(__file__).resolve().parents[2]
    selected_analysis = {
        "analysis_id": "smoke-analyzer-core-pack",
        "pattern": {},
    }
    ctx = _load_quality_context(str(root), selected_analysis)
    lane = ctx.get("frame_labeling")
    if not isinstance(lane, dict):
        print("ERROR: missing frame_labeling context lane", file=sys.stderr)
        return 1
    if int(lane.get("frame_count") or 0) <= 0:
        print("ERROR: frame_labeling lane has no frames", file=sys.stderr)
        return 1
    if not bool(lane.get("facts_only_or_unknown")):
        print("ERROR: frame_labeling facts_only_or_unknown must be true", file=sys.stderr)
        return 1
    print(f"frame_labels_relpath: {lane.get('relpath')}")
    print(f"frame_count: {lane.get('frame_count')}")
    print(f"enrichment_provider: {lane.get('enrichment_provider')}")
    print("OK: planner frame-labeling quality context")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
