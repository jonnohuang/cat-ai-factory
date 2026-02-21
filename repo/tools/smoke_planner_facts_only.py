#!/usr/bin/env python3
from __future__ import annotations

import json
import pathlib
import subprocess
import sys


def _run(cmd: list[str]) -> int:
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    print(p.stdout, end="")
    return p.returncode


def main() -> int:
    root = pathlib.Path(__file__).resolve().parents[2]
    job = {
        "job_id": "facts-smoke-0001",
        "date": "2026-02-17",
        "niche": "cats",
        "video": {
            "length_seconds": 15,
            "aspect_ratio": "9:16",
            "fps": 30,
            "resolution": "1080x1920",
        },
        "script": {
            "hook": "Mochi starts with a locked pose.",
            "voiceover": "Camera stays locked while dance beats progress.",
            "ending": "Loop returns to start.",
        },
        "shots": [
            {
                "t": 0,
                "visual": "locked camera cat dance",
                "action": "pose hit",
                "caption": "start",
            },
            {
                "t": 5,
                "visual": "static frame dance",
                "action": "paw pop",
                "caption": "middle",
            },
            {
                "t": 10,
                "visual": "locked final pose",
                "action": "reset",
                "caption": "end",
            },
            {
                "t": 11,
                "visual": "locked final pose",
                "action": "reset",
                "caption": "end",
            },
            {
                "t": 12,
                "visual": "locked final pose",
                "action": "reset",
                "caption": "end",
            },
            {
                "t": 13,
                "visual": "locked final pose",
                "action": "reset",
                "caption": "end",
            },
        ],
        "captions": ["a", "b", "c", "d"],
        "hashtags": ["#cat", "#loop", "#dance"],
        "render": {
            "background_asset": "sandbox/assets/demo/mochi_dance_loop_swap.mp4",
            "subtitle_style": "big_bottom",
            "output_basename": "facts-smoke",
        },
    }

    tmp_job = pathlib.Path("/tmp/facts_only_smoke.job.json")
    tmp_job.write_text(json.dumps(job, indent=2), encoding="utf-8")
    reverse = root / "repo" / "examples" / "caf.video_reverse_prompt.v1.example.json"

    rc = _run(
        [
            sys.executable,
            "-m",
            "repo.tools.validate_planner_facts_only",
            "--job",
            str(tmp_job),
            "--reverse",
            str(reverse),
        ]
    )
    tmp_job.unlink(missing_ok=True)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
