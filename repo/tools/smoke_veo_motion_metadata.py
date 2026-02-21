import json
import os
import pathlib
import sys

# Add repo root to path
repo_root = pathlib.Path(__file__).resolve().parents[2]
sys.path.append(str(repo_root))

from repo.services.planner.providers.vertex_ai import _seed_prompt_from_job


def test_motion_translation():
    print("Testing Motion Metadata Translation...")

    # 1. Mock Data
    job = {"niche": "cat video", "script": {}}
    prd = {"prompt": "A cute cat"}
    hero_desc = "Grey tabby"

    # Context with Motion Metadata
    quality_context = {
        "video_analysis": {
            "version": "video_analysis.v1",
            "pattern": {
                "choreography": {"energy_curve": "build"},
                "camera": {"shot_pattern": ["tracking", "medium"]},
            },
        },
        "reverse_prompt": {
            "suggestions": {"vendor_style_tokens": ["cinematic lighting"]},
            "truth": {
                "visual_facts": {"camera_movement_mode": "handheld"},
                "shots": [{"motion_intensity": 0.8}],
            },
        },
    }

    # 2. Call Function
    prompt = _seed_prompt_from_job(job, prd, hero_desc, quality_context)

    print(f"\nGenerated Prompt:\n{prompt}\n")

    # 3. Assertions
    expected_phrases = [
        "building energy, intensifying motion",  # From energy_curve=build
        "dynamic tracking shot",  # From shot_pattern=tracking
        "handheld camera motion",  # From camera_movement_mode=handheld
        "high energy, fast paced",  # From motion_intensity=0.8
        "cinematic lighting",  # From vendor_style_tokens
    ]

    missing = []
    for phrase in expected_phrases:
        if phrase.lower() not in prompt.lower():
            missing.append(phrase)

    if missing:
        print(f"FAILED: Missing phrases in prompt: {missing}")
        sys.exit(1)

    print("SUCCESS: All motion metadata phrases found in prompt.")


if __name__ == "__main__":
    test_motion_translation()
