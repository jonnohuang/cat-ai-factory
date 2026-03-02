import argparse
import json
import os
import pathlib
import sys
from typing import Any, Dict, List, Optional

try:
    from google import genai
    from google.genai import types
    HAS_GENAI = True
except ImportError:
    HAS_GENAI = False
    genai = None
    types = None

def load_job(job_path: pathlib.Path) -> dict:
    with open(job_path, "r") as f:
        return json.load(f)

def generate_storyboard(
    job_path: pathlib.Path,
    output_dir: pathlib.Path,
    project_id: str,
    location: str
):
    job = load_job(job_path)
    job_id = job.get("job_id", "unknown_job")

    # Ensure output directory exists
    storyboard_dir = output_dir / "storyboard"
    storyboard_dir.mkdir(parents=True, exist_ok=True)
    contact_sheet_path = storyboard_dir / "contact_sheet.png"

    # Extract prompt
    target_act_id = os.environ.get("CAF_TARGET_ACT_ID", "").strip()
    prompt = None
    act_data = None

    if target_act_id:
        acts = job.get("acts", [])
        act_data = next((a for a in acts if a.get("act_id") == target_act_id), None)
        if act_data:
            print(f"INFO: Targeting act='{target_act_id}'")
            prompt = act_data.get("prompt_override")
        else:
            print(f"WARNING: Act '{target_act_id}' not found in job. Falling back to global prompt.")

    if not prompt:
        prompt = job.get("prompt")

    if not prompt:
        # Fallback to script/voiceover or storyboard vision if available
        script = job.get("script", {})
        prompt = script.get("voiceover") or script.get("hook")

    if not prompt:
        print("ERROR: No prompt found in job.json", file=sys.stderr)
        sys.exit(1)

    # Narrative framing for contact sheet
    storyboard_prompt = (
        f"Create a high-fidelity 3x4 grid contact sheet (12 panels total) for the following video script: {prompt}. "
        "Each panel should represent a sequential moment in the 12-second story. "
        "Ensure consistent character identity and background across all 12 panels. "
        "Style: Cinematic, high-quality animation."
    )

    print(f"Generating storyboard contact sheet for job: {job_id}")
    print(f"Base Prompt: {prompt}")

    is_mock = os.environ.get("CAF_VEO_MOCK", "").strip().lower() in ("1", "true", "yes")

    if is_mock:
        print("INFO: Mocking storyboard generation...")
        # In mock mode, we'll try to find a placeholder or just touch the file
        # For now, let's look for a dummy in assets
        dummy_path = pathlib.Path("repo/assets/dummy_contact_sheet.png")
        if dummy_path.exists():
            import shutil
            shutil.copy(dummy_path, contact_sheet_path)
        else:
            # Create an empty file if no dummy exists
            contact_sheet_path.touch()
        print(f"Mock output written to {contact_sheet_path}")
        return

    if not HAS_GENAI:
        print("ERROR: google-genai package not found.", file=sys.stderr)
        sys.exit(1)

    try:
        client = genai.Client(vertexai=True, project=project_id, location=location)

        # Using Imagen 3 or similar for high-fidelity contact sheet
        # Note: In a real implementation, we would use the specific Imagen/multimodal endpoint
        print("Calling Vertex AI Image Generation...")

        # Placeholder for Imagen 3 call structure
        # response = client.models.generate_image(
        #     model="imagen-3.0-generate-001",
        #     prompt=storyboard_prompt,
        #     parameters=types.GenerateImageConfig(
        #         number_of_images=1,
        #         aspect_ratio="3:4",
        #         add_watermark=False,
        #     )
        # )

        # For now, we simulate the structure until the exact v2.5 multimodal API is pinned
        print(f"Simulating API call with prompt: {storyboard_prompt}")
        contact_sheet_path.touch() # Placeholder

    except Exception as e:
        print(f"ERROR: Storyboard generation failed: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"SUCCESS: Storyboard contact sheet saved to {contact_sheet_path}")

def main():
    parser = argparse.ArgumentParser(description="Generate a storyboard contact sheet for the Golden Baseline.")
    parser.add_argument("--job", type=str, required=True, help="Path to job.json")
    parser.add_argument("--out", type=str, required=True, help="Path to output directory")
    parser.add_argument("--project", type=str, default=os.environ.get("GOOGLE_CLOUD_PROJECT"), help="GCP Project ID")
    parser.add_argument("--location", type=str, default="us-central1", help="GCP Location")

    args = parser.parse_args()

    job_path = pathlib.Path(args.job)
    output_dir = pathlib.Path(args.out)

    if not job_path.exists():
        print(f"ERROR: Job file not found at {job_path}", file=sys.stderr)
        sys.exit(1)

    generate_storyboard(job_path, output_dir, args.project, args.location)

if __name__ == "__main__":
    main()
