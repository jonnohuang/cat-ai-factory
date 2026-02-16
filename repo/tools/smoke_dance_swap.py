#!/usr/bin/env python3
"""
smoke_dance_swap.py

PR-33.1 smoke runner for deterministic Dance Swap wiring.

It creates minimal Dance Swap artifacts under sandbox/output/<job_id>/contracts,
validates contracts/job, and executes worker render.
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys
from typing import Any


def _repo_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parents[2]


def _write(path: pathlib.Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: list[str]) -> int:
    _ = argv
    root = _repo_root()
    sandbox = root / "sandbox"
    job_id = "smoke-dance-swap-v1"
    contracts_dir = sandbox / "output" / job_id / "contracts"
    jobs_dir = sandbox / "jobs"

    source_video = "sandbox/assets/demo/dance_loop.mp4"
    mask_png = "sandbox/assets/demo/dance_loop_ref_01.png"
    fg_asset = "assets/generated/mochi-dino-dance-loop-20240515/veo-0001.mp4"

    loop = {
        "version": "dance_swap_loop.v1",
        "source_video_relpath": source_video,
        "fps": 30.0,
        "loop_start_frame": 12,
        "loop_end_frame": 240,
        "blend_strategy": "crossfade",
    }
    tracks = {
        "version": "dance_swap_tracks.v1",
        "source_video_relpath": source_video,
        "subjects": [
            {
                "subject_id": "cat-1",
                "hero_id": "mochi-grey-tabby",
                "frames": [
                    {"frame": 12, "bbox": {"x": 140, "y": 780, "w": 280, "h": 520}, "mask_relpath": mask_png},
                    {"frame": 36, "bbox": {"x": 150, "y": 776, "w": 286, "h": 522}, "mask_relpath": mask_png},
                    {"frame": 60, "bbox": {"x": 144, "y": 782, "w": 282, "h": 518}, "mask_relpath": mask_png},
                ],
            }
        ],
    }
    beatflow = {
        "version": "dance_swap_beatflow.v1",
        "source_video_relpath": source_video,
        "beats": [{"frame": 24, "strength": 0.8}, {"frame": 48, "strength": 0.76}],
        "flow_windows": [{"start_frame": 12, "end_frame": 60, "mean_magnitude": 4.1}],
    }

    loop_path = contracts_dir / "loop.json"
    tracks_path = contracts_dir / "tracks.json"
    beatflow_path = contracts_dir / "beatflow.json"
    _write(loop_path, loop)
    _write(tracks_path, tracks)
    _write(beatflow_path, beatflow)

    job = {
        "job_id": job_id,
        "date": "2026-02-16",
        "lane": "dance_swap",
        "niche": "cat_dance_comedy",
        "video": {
            "length_seconds": 12,
            "aspect_ratio": "9:16",
            "fps": 30,
            "resolution": "1080x1920",
        },
        "script": {
            "hook": "Dance swap smoke.",
            "voiceover": "Deterministic dance swap lane smoke test.",
            "ending": "Done.",
        },
        "shots": [
            {"t": 0, "visual": "dance", "action": "start", "caption": "start"},
            {"t": 2, "visual": "dance", "action": "swap", "caption": "swap"},
            {"t": 4, "visual": "dance", "action": "beat", "caption": "beat"},
            {"t": 6, "visual": "dance", "action": "loop", "caption": "loop"},
            {"t": 8, "visual": "dance", "action": "pose", "caption": "pose"},
            {"t": 10, "visual": "dance", "action": "end", "caption": "end"},
        ],
        "captions": ["Dance swap", "Artifact-driven", "Deterministic", "Smoke"],
        "hashtags": ["#CatDance", "#DanceSwap", "#CAF"],
        "render": {
            "background_asset": "assets/demo/dance_loop.mp4",
            "subtitle_style": "big_bottom",
            "output_basename": "smoke_dance_swap_v1",
        },
        "audio": {"audio_asset": "assets/audio/beds/caf_bed_dance_loop_01.wav"},
        "dance_swap": {
            "loop_artifact": f"sandbox/output/{job_id}/contracts/loop.json",
            "tracks_artifact": f"sandbox/output/{job_id}/contracts/tracks.json",
            "beatflow_artifact": f"sandbox/output/{job_id}/contracts/beatflow.json",
            "foreground_asset": fg_asset,
            "subject_id": "cat-1",
        },
    }
    job_path = jobs_dir / f"{job_id}.job.json"
    _write(job_path, job)

    cmds = [
        [sys.executable, "-m", "repo.tools.validate_dance_swap_contracts", "--loop", str(loop_path), "--tracks", str(tracks_path), "--beatflow", str(beatflow_path)],
        [sys.executable, "repo/tools/validate_job.py", str(job_path)],
        [sys.executable, "-m", "repo.worker.render_ffmpeg", "--job", str(job_path)],
    ]
    for cmd in cmds:
        print("RUN:", " ".join(cmd))
        subprocess.check_call(cmd, cwd=str(root))

    out_mp4 = sandbox / "output" / job_id / "final.mp4"
    result_json = sandbox / "output" / job_id / "result.json"
    print("OK:", out_mp4)
    print("OK:", result_json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

