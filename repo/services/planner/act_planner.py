#!/usr/bin/env python3
"""Act Planner for Multi-Act Golden Baseline (Long Mode)."""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any, Dict, List


def plan_acts(job: Dict[str, Any]) -> Dict[str, Any]:
    """Segment a long job into structured acts (PR-60)."""
    video_cfg = job.get("video", {})
    duration = video_cfg.get("length_seconds")
    if not duration:
        # Fallback to duration_sec if present
        duration = video_cfg.get("duration_sec", 0)

    if duration <= 10:
        return job

    # 16s -> 2 acts, 24s -> 3 acts, 32s -> 4 acts (~8s per act)
    num_acts = int((duration + 7) // 8)
    if num_acts < 2:
        num_acts = 2

    act_duration = duration / num_acts
    acts = []
    base_prompt = video_cfg.get("prompt", "")

    for i in range(num_acts):
        start_t = i * act_duration
        end_t = (i + 1) * act_duration
        act_id = f"act_{i+1:02d}"

        # Continuity Contract (ADR-0076)
        continuity = {}
        if i > 0:
            continuity = {
                "previous_act_id": f"act_{i:02d}",
                "final_emotional_state": "Continue from previous emotional state with consistent intensity.",
                "environment_baseline": "Preserve environment lighting and background details.",
                "hero_lock": True
            }

        # Simple structural prompt steering
        role = "setup" if i == 0 else "escalation" if i < num_acts - 1 else "resolution"

        acts.append({
            "act_id": act_id,
            "start_t": round(start_t, 2),
            "end_t": round(end_t, 2),
            "prompt_override": f"{base_prompt} [ACT: {role.upper()}] Reference continuity from previous act for identity and background lock.",
            "continuity_contract": continuity
        })

    job["acts"] = acts
    return job

def main():
    parser = argparse.ArgumentParser(description="Multi-Act Planner CLI")
    parser.add_argument("--job", required=True, help="Path to job.json")
    parser.add_argument("--inplace", action="store_true", help="Modify job file in place")
    args = parser.parse_args()

    job_path = pathlib.Path(args.job)
    if not job_path.exists():
        print(f"Error: {job_path} not found.")
        sys.exit(1)

    with open(job_path, "r", encoding="utf-8") as f:
        job = json.load(f)

    updated_job = plan_acts(job)

    if args.inplace:
        with open(job_path, "w", encoding="utf-8") as f:
            json.dump(updated_job, f, indent=2)
        print(f"Updated {job_path} with {len(updated_job.get('acts', []))} acts.")
    else:
        print(json.dumps(updated_job, indent=2))

if __name__ == "__main__":
    main()
