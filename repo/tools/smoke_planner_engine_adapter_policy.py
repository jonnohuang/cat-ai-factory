#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys

from repo.services.planner.planner_cli import (
    _apply_engine_adapter_hints,
    _load_quality_context,
)


def _repo_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parents[2]


def main(argv: list[str]) -> int:
    _ = argv
    root = _repo_root()
    ctx = _load_quality_context(str(root), None)
    policy = ctx.get("engine_adapter_policy")
    if not isinstance(policy, dict):
        print(
            "ERROR: missing engine_adapter_policy in planner quality context",
            file=sys.stderr,
        )
        return 1

    job = {
        "job_id": "smoke-engine-adapter-policy",
        "date": "2026-02-18",
        "niche": "cats",
        "video": {
            "length_seconds": 12,
            "aspect_ratio": "9:16",
            "fps": 30,
            "resolution": "1080x1920",
        },
        "script": {
            "hook": "Mochi dance test",
            "voiceover": "Deterministic adapter policy smoke for planner generation routing hints.",
            "ending": "Loop it again.",
        },
        "shots": [
            {"t": 0, "visual": "shot1", "action": "a", "caption": "c1"},
            {"t": 2, "visual": "shot2", "action": "a", "caption": "c2"},
            {"t": 4, "visual": "shot3", "action": "a", "caption": "c3"},
            {"t": 6, "visual": "shot4", "action": "a", "caption": "c4"},
            {"t": 8, "visual": "shot5", "action": "a", "caption": "c5"},
            {"t": 10, "visual": "shot6", "action": "a", "caption": "c6"},
        ],
        "captions": ["one", "two", "three", "four"],
        "hashtags": ["#cat", "#shorts", "#pets"],
        "render": {
            "background_asset": "assets/demo/fight_composite.mp4",
            "subtitle_style": "big_bottom",
            "output_basename": "smoke-engine-adapter-policy",
        },
    }
    job = _apply_engine_adapter_hints(job, ctx)
    gen = job.get("generation_policy")
    if not isinstance(gen, dict):
        print("ERROR: generation_policy hint missing from job", file=sys.stderr)
        return 1
    if not isinstance(gen.get("video_provider_order"), list) or not gen.get(
        "video_provider_order"
    ):
        print("ERROR: generation_policy.video_provider_order missing", file=sys.stderr)
        return 1
    if not isinstance(gen.get("frame_provider_order"), list) or not gen.get(
        "frame_provider_order"
    ):
        print("ERROR: generation_policy.frame_provider_order missing", file=sys.stderr)
        return 1
    if gen.get("route_mode") != "production":
        print("ERROR: expected production route_mode by default", file=sys.stderr)
        return 1

    prior_mode = os.environ.get("CAF_ENGINE_ROUTE_MODE")
    try:
        os.environ["CAF_ENGINE_ROUTE_MODE"] = "lab"
        lab_job = dict(job)
        lab_job.pop("generation_policy", None)
        lab_job = _apply_engine_adapter_hints(lab_job, ctx)
        lab_gen = lab_job.get("generation_policy")
        if not isinstance(lab_gen, dict):
            print("ERROR: missing generation_policy in lab mode", file=sys.stderr)
            return 1
        if lab_gen.get("route_mode") != "lab":
            print(
                "ERROR: expected lab route_mode when CAF_ENGINE_ROUTE_MODE=lab",
                file=sys.stderr,
            )
            return 1
    finally:
        if prior_mode is None:
            os.environ.pop("CAF_ENGINE_ROUTE_MODE", None)
        else:
            os.environ["CAF_ENGINE_ROUTE_MODE"] = prior_mode

    temp_job = root / "sandbox" / "jobs" / "smoke-engine-adapter-policy.job.json"
    temp_job.parent.mkdir(parents=True, exist_ok=True)
    temp_job.write_text(json.dumps(job, indent=2) + "\n", encoding="utf-8")
    cmd = [sys.executable, "-m", "repo.tools.validate_job", str(temp_job)]
    print("RUN:", " ".join(cmd))
    subprocess.check_call(cmd, cwd=str(root))
    print("OK: planner engine adapter policy smoke")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
