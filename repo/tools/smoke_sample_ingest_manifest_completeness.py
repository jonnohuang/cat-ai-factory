#!/usr/bin/env python3
from __future__ import annotations

import json
import pathlib
import subprocess
import sys


def _repo_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parents[2]


def _write(path: pathlib.Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _run(cmd: list[str], cwd: pathlib.Path) -> int:
    proc = subprocess.run(cmd, cwd=str(cwd), text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    print(proc.stdout, end="")
    return proc.returncode


def main() -> int:
    root = _repo_root()
    tmp = root / "sandbox" / "logs" / "lab" / "smoke-sample-ingest"
    good = tmp / "good.sample_ingest_manifest.v1.json"
    bad = tmp / "bad.sample_ingest_manifest.v1.json"

    base = {
        "version": "sample_ingest_manifest.v1",
        "sample_id": "smoke",
        "analysis_id": "smoke",
        "generated_at": "2026-02-19T00:00:00Z",
        "source": {
            "video_relpath": "sandbox/assets/demo/processed/smoke.mp4",
            "reference_aliases": ["smoke"],
        },
        "contracts": {
            "video_analysis_relpath": "repo/canon/demo_analyses/smoke.video_analysis.v1.json",
            "reverse_prompt_relpath": "repo/canon/demo_analyses/smoke.caf.video_reverse_prompt.v1.json",
            "beat_grid_relpath": "repo/canon/demo_analyses/smoke.beat_grid.v1.json",
            "pose_checkpoints_relpath": "repo/canon/demo_analyses/smoke.pose_checkpoints.v1.json",
            "keyframe_checkpoints_relpath": "repo/canon/demo_analyses/smoke.keyframe_checkpoints.v1.json",
            "segment_stitch_plan_relpath": "repo/canon/demo_analyses/smoke.segment_stitch_plan.v1.json",
            "quality_target_relpath": "repo/examples/quality_target.motion_strict.v1.example.json",
            "continuity_pack_relpath": "repo/examples/episode_continuity_pack.v1.example.json",
            "storyboard_relpath": "repo/examples/storyboard.v1.example.json",
            "frame_labels_relpath": "repo/canon/demo_analyses/smoke.frame_labels.v1.json",
        },
        "assets": {
            "hero_refs": ["mochi"],
            "costume_refs": ["dino"],
            "background_refs": ["stage"],
            "audio_refs": [],
            "style_tone_refs": ["playful"],
        },
        "artifact_classes": {
            "identity_anchor": {"required": True, "present": True, "consumers": ["planner"], "evidence": ["hero_ref:mochi"]},
            "costume_style": {"required": True, "present": True, "consumers": ["planner"], "evidence": ["costume_ref:dino"]},
            "background_setting": {"required": True, "present": True, "consumers": ["planner"], "evidence": ["background_ref:stage"]},
            "framing_edit": {"required": True, "present": True, "consumers": ["planner"], "evidence": ["repo/canon/demo_analyses/smoke.video_analysis.v1.json"]},
            "motion_trace": {"required": True, "present": True, "consumers": ["planner"], "evidence": ["repo/canon/demo_analyses/smoke.pose_checkpoints.v1.json"]},
            "audio_beat": {"required": True, "present": True, "consumers": ["planner"], "evidence": ["repo/canon/demo_analyses/smoke.beat_grid.v1.json"]},
        },
        "provenance": {
            "ingest_tool": "smoke",
            "tool_versions": {"smoke": "v1"},
            "confidence": 1.0,
        },
    }
    _write(good, base)

    bad_payload = dict(base)
    bad_payload["artifact_classes"] = dict(base["artifact_classes"])
    bad_payload["artifact_classes"]["audio_beat"] = {
        "required": True,
        "present": False,
        "consumers": ["planner"],
        "evidence": [],
    }
    _write(bad, bad_payload)

    cmd_good = [sys.executable, "-m", "repo.tools.validate_sample_ingest_manifest", str(good)]
    if _run(cmd_good, root) != 0:
        print("ERROR: expected good sample_ingest manifest to pass", file=sys.stderr)
        return 1

    cmd_bad = [sys.executable, "-m", "repo.tools.validate_sample_ingest_manifest", str(bad)]
    if _run(cmd_bad, root) == 0:
        print("ERROR: expected bad sample_ingest manifest to fail", file=sys.stderr)
        return 1

    print("OK: sample_ingest manifest completeness smoke")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
