#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
from typing import Any, Dict, Optional


def _repo_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parents[2]


def _write(path: pathlib.Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _load(path: pathlib.Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _run(cmd: list[str], cwd: pathlib.Path) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(cmd, cwd=str(cwd), text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    print(proc.stdout, end="")
    return proc


def _extract_job_path(output: str) -> Optional[pathlib.Path]:
    for line in reversed(output.splitlines()):
        line = line.strip()
        if line.startswith("Wrote ") and line.endswith(".job.json"):
            return pathlib.Path(line[len("Wrote ") :])
    return None


def main() -> int:
    root = _repo_root()
    os.environ.setdefault("COMFYUI_BASE_URL", "http://127.0.0.1:8188")
    os.environ.setdefault("COMFYUI_WORKFLOW_ID", "caf_dance_loop_v1")
    analysis_id = "smoke-auto-pointer"

    pose_rel = "repo/examples/pose_checkpoints.v1.example.json"
    manifest_path = root / "repo" / "canon" / "demo_analyses" / f"{analysis_id}.sample_ingest_manifest.v1.json"
    _write(
        manifest_path,
        {
            "version": "sample_ingest_manifest.v1",
            "sample_id": analysis_id,
            "analysis_id": analysis_id,
            "generated_at": "2026-02-18T00:00:00Z",
            "source": {
                "video_relpath": "sandbox/assets/demo/processed/smoke-auto-pointer.mp4",
                "reference_aliases": ["smoke auto pointer", "mochi dance loop"]
            },
            "contracts": {
                "video_analysis_relpath": "repo/examples/video_analysis.v1.example.json",
                "reverse_prompt_relpath": None,
                "beat_grid_relpath": None,
                "pose_checkpoints_relpath": pose_rel,
                "keyframe_checkpoints_relpath": None,
                "segment_stitch_plan_relpath": "repo/examples/segment_stitch_plan.v1.example.json",
                "quality_target_relpath": "repo/examples/quality_target.motion_strict.v1.example.json",
                "continuity_pack_relpath": "repo/examples/episode_continuity_pack.v1.example.json",
                "storyboard_relpath": "repo/examples/storyboard.v1.example.json",
                "frame_labels_relpath": None
            },
            "assets": {
                "hero_refs": ["mochi"],
                "costume_refs": [],
                "background_refs": [],
                "audio_refs": [],
                "style_tone_refs": []
            },
            "provenance": {
                "ingest_tool": "smoke",
                "tool_versions": {"smoke": "v1"},
                "confidence": 1.0
            }
        },
    )

    cmd = [
        sys.executable,
        "-m",
        "repo.services.planner.planner_cli",
        "--prompt",
        "Mochi dance loop smoke auto pointer",
        "--provider",
        "comfyui_video",
        "--inbox",
        "sandbox/inbox",
        "--out",
        "sandbox/jobs",
    ]
    proc = _run(cmd, root)
    if proc.returncode != 0:
        return proc.returncode
    job_path = _extract_job_path(proc.stdout)
    if job_path is None:
        print("ERROR: planner did not emit job path", file=sys.stderr)
        return 1
    if not job_path.is_absolute():
        job_path = (root / job_path).resolve()

    job = _load(job_path)
    if not isinstance(job, dict):
        print("ERROR: missing job json", file=sys.stderr)
        return 1
    mc = job.get("motion_contract")
    if not isinstance(mc, dict) or not isinstance(mc.get("relpath"), str) or not mc.get("relpath"):
        print("ERROR: pointer resolver did not produce motion_contract pointer", file=sys.stderr)
        return 1

    resolution = job.get("pointer_resolution")
    if not isinstance(resolution, dict) or resolution.get("version") != "pointer_resolution.v1":
        print("ERROR: missing pointer_resolution.v1 artifact in job contract", file=sys.stderr)
        return 1
    selected = resolution.get("selected", {})
    motion_selected = selected.get("motion_contract") if isinstance(selected, dict) else None
    if not isinstance(motion_selected, dict) or motion_selected.get("relpath") != mc.get("relpath"):
        print("ERROR: pointer_resolution selected.motion_contract does not match effective job pointer", file=sys.stderr)
        return 1

    print("OK: planner pointer resolver smoke")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
