#!/usr/bin/env python3
"""
gen_hero.py

Generates Hero Assets (seed images) using Imagen 3 via google-genai SDK.
Updates hero_registry.v1.json with the new asset paths.

Usage:
  python3 repo/tools/gen_hero.py --hero tiger-black --costume chef-uniform --prompt-override "..."
"""

import argparse
import json
import os
import pathlib
import sys
import time
from typing import Any, Dict, Optional

from google import genai
from google.genai import types


def _repo_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parents[2]


def _load_json(path: pathlib.Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _save_json(path: pathlib.Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def _init_client() -> genai.Client:
    project = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("GCP_PROJECT_ID")
    location = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")

    import google.auth
    from google.auth.transport.requests import Request

    # Explicitly look for ADC
    creds, adc_project = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )

    if not project and adc_project:
        project = adc_project

    if not project:
        raise ValueError("GOOGLE_CLOUD_PROJECT or GCP_PROJECT_ID must be set")

    # Refresh if needed
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())

    print(
        f"DEBUG: Initializing client project={project} location={location} creds={bool(creds)}"
    )
    return genai.Client(vertexai=True, project=project, location=location)


def _generate_image(
    client: genai.Client, prompt: str, output_path: pathlib.Path
) -> None:
    print("Generating image with Imagen 3...")
    print(f"Prompt: {prompt}")

    try:
        response = client.models.generate_images(
            model="imagen-3.0-generate-001",
            prompt=prompt,
            config=types.GenerateImagesConfig(
                number_of_images=1,
                aspect_ratio="9:16",
                safety_filter_level="block_medium_and_above",
                person_generation="allow_adult",
            ),
        )
        if not response.generated_images:
            raise RuntimeError("No images generated")

        image = response.generated_images[0].image
        output_path.parent.mkdir(parents=True, exist_ok=True)
        image.save(output_path)
        print(f"Saved to {output_path}")

    except Exception as e:
        print(f"Generation failed: {e}")
        raise


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--hero", required=True, help="Hero ID from registry")
    parser.add_argument(
        "--costume",
        required=True,
        help="Costume ID from registry (or match hero default)",
    )
    parser.add_argument("--prompt-override", help="Override constructed prompt")
    parser.add_argument("--registry-path", default="repo/shared/hero_registry.v1.json")
    parser.add_argument(
        "--costume-path", default="repo/shared/costume_profiles.v1.json"
    )
    parser.add_argument(
        "--style", help="Style prompt override (e.g. 'Pixar-style 3D, fluffy fur')"
    )
    parser.add_argument(
        "--offset-y",
        type=int,
        default=0,
        help="Vertical offset hint (no-op for Imagen)",
    )
    args = parser.parse_args()

    root = _repo_root()
    hero_registry_path = root / args.registry_path
    costume_registry_path = root / args.costume_path

    hero_data = _load_json(hero_registry_path) or {}
    costume_data = _load_json(costume_registry_path) or {}

    # Resolve Hero
    hero = next(
        (h for h in hero_data.get("heroes", []) if h["hero_id"] == args.hero), None
    )
    if not hero:
        print(f"Error: Hero {args.hero} not found")
        return 1

    # Resolve Costume
    costume_entry = next(
        (c for c in costume_data.get("profiles", []) if c["id"] == args.costume), None
    )
    if not costume_entry:
        print(f"Error: Costume {args.costume} not found")
        return 1

    # Construct Prompt
    traits = hero.get("traits", {})
    costume_cues = costume_entry.get("cues", [])

    # Style Prompt Construction
    style_prompt = "Pixar-style 3D, fluffy fur texture, soft lighting, rim light."
    if args.style:
        style_prompt = args.style

    prompt_parts = [
        "High quality 3D render, cute stylized character design, unreal engine 5, octane render, 8k.",
        f"Character: {hero['name']['en']}, a {traits.get('primary_color', '')} {traits.get('coat_type', 'cat')}.",
        f"Eyes: {traits.get('eye_color', 'dark')} eyes, bright and expressive.",
        f"Costume: {', '.join(costume_cues)}.",
        "Pose: Standing confidently, facing forward, full body shot.",
        "Background: Simple clean studio lighting, soft gradient background.",
        f"Style: {style_prompt}",
    ]

    if args.prompt_override:
        final_prompt = args.prompt_override
    else:
        final_prompt = " ".join(prompt_parts)

    # Output Path
    out_filename = f"{args.hero}_{args.costume}.png"
    out_relpath = f"assets/generated/heroes/{out_filename}"
    out_fullpath = root / out_relpath

    client = _init_client()
    _generate_image(client, final_prompt, out_fullpath)

    # Update Registry
    # Find hero index
    for idx, h in enumerate(hero_data["heroes"]):
        if h["hero_id"] == args.hero:
            if "asset_hints" not in h:
                h["asset_hints"] = {}
            if "seed_frames" not in h["asset_hints"]:
                h["asset_hints"]["seed_frames"] = []

            # Prepend new asset
            # Convert to repo-relative string
            if out_relpath not in h["asset_hints"]["seed_frames"]:
                h["asset_hints"]["seed_frames"].insert(0, out_relpath)

            # Limit to 3
            h["asset_hints"]["seed_frames"] = h["asset_hints"]["seed_frames"][:3]
            break

    _save_json(hero_registry_path, hero_data)
    print(f"Updated registry {args.registry_path}")


if __name__ == "__main__":
    main()
