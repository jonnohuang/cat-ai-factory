import argparse
import io
import json
import os
import pathlib
import shutil
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

try:
    from google import genai
    from google.genai import types
    HAS_GENAI = True
except ImportError:
    HAS_GENAI = False
    genai = None
    types = None

try:
    from PIL import Image
except ImportError:
    print("WARNING: PIL not found, I2V features will be disabled.", file=sys.stderr)
    Image = None


def load_env(env_path: pathlib.Path = pathlib.Path(".env")):
    """Load environment variables from a .env file."""
    if not env_path.exists():
        return

    print(f"Loading environment from {env_path}")
    with open(env_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, value = line.split("=", 1)
                if not os.environ.get(key):
                    os.environ[key] = value


def atomic_write_json(path: pathlib.Path, payload: Dict[str, Any]) -> None:
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    tmp_path.replace(path)


def load_job(job_path: pathlib.Path) -> dict:
    with open(job_path, "r") as f:
        return json.load(f)


def render(
    job_path: pathlib.Path, output_path: pathlib.Path, project_id: str, location: str
):
    job = load_job(job_path)

    target_shot_id = os.environ.get("CAF_TARGET_SHOT_ID", "").strip()

    # Extract prompt from job
    prompt = None

    if target_shot_id:
        shots = job.get("shots", [])
        target_shot = next(
            (s for s in shots if s.get("shot_id") == target_shot_id), None
        )
        if target_shot:
            print(f"INFO: Targeting granular shot_id='{target_shot_id}'")
            prompt = target_shot.get("visual")
            # In Director mode, we may want to append action tokens
            action = target_shot.get("action")
            if action:
                prompt = f"{prompt} | {action}"
        else:
            print(
                f"ERROR: shot_id '{target_shot_id}' specified via CAF_TARGET_SHOT_ID but not found in job.",
                file=sys.stderr,
            )
            sys.exit(1)

    if not prompt:
        prompt = job.get("prompt")

    if not prompt:
        bindings = job.get("comfyui", {}).get("bindings", {})
        prompt = bindings.get("prompt_text") or bindings.get("prompt")

    # Fallback for legacy jobs or simple briefs
    if not prompt:
        script = job.get("script", {})
        prompt = script.get("voiceover") or script.get("hook")

    if not prompt:
        print(
            "ERROR: No prompt found in job JSON (or target shot missing visual)",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"Authenticating (project={project_id}, location={location})")

    is_mock = os.environ.get("CAF_VEO_MOCK", "").strip().lower() in ("1", "true", "yes")
    client = None

    if not is_mock:
        if not HAS_GENAI:
            print(
                "ERROR: google-genai package not found. Install with: pip install google-genai",
                file=sys.stderr,
            )
            sys.exit(1)
        try:
            client = genai.Client(vertexai=True, project=project_id, location=location)
        except Exception as e:
            print(f"ERROR: Failed to initialize google-genai client: {e}", file=sys.stderr)
            sys.exit(1)

    # --- I2V Logic ---
    veo_image = None
    if Image:
        # 1. Check image_motion (deterministic planner path)
        image_motion = job.get("image_motion", {})
        seed_frames = image_motion.get("seed_frames", [])

        # 2. Check storyboard logic (fallback/direct pointer)
        if not seed_frames:
            pass

        # 3. Check fallback simple render.background_asset
        if not seed_frames:
            bg = job.get("render", {}).get("background_asset")
            if bg and (bg.endswith(".png") or bg.endswith(".jpg")):
                seed_frames = [bg]

        # Load ONLY the first seed frame if available for Veo 2.0 I2V
        if seed_frames:
            rel_path = seed_frames[0]
            if os.path.isabs(rel_path):
                p = pathlib.Path(rel_path)
            else:
                p = pathlib.Path(rel_path).resolve()

            if not p.exists():
                sandbox_p = pathlib.Path("sandbox") / rel_path
                if sandbox_p.exists():
                    p = sandbox_p

            if p.exists():
                try:
                    print(f"Loading reference image: {p}")
                    # Serialize to bytes explicitly
                    with open(p, "rb") as f:
                        img_bytes = f.read()

                    mime = (
                        "image/png" if str(p).lower().endswith(".png") else "image/jpeg"
                    )
                    veo_image = types.Image(image_bytes=img_bytes, mime_type=mime)

                except Exception as e:
                    print(f"WARNING: Failed to load image {p}: {e}", file=sys.stderr)
            else:
                print(f"WARNING: Seed frame not found at {p}", file=sys.stderr)

    print("Generating video with veo-2.0-generate-001...")
    print(f"Prompt: {prompt}")
    if veo_image:
        print("Reference Image: Loaded (I2V mode)")

    try:

        kwargs = {
            "model": "veo-2.0-generate-001",
            "prompt": prompt,
            "config": {
                "fps": 24,  # Cinematic 24fps default
                "aspect_ratio": "9:16",
            },
        }

        # Add negative prompt if present
        negative_prompt = job.get("negative_prompt")
        if not negative_prompt:
            bindings = job.get("comfyui", {}).get("bindings", {})
            negative_prompt = bindings.get("negative_prompt") or bindings.get(
                "negative_prompt_text"
            )

        if negative_prompt:
            print(f"Negative Prompt: {negative_prompt}")
            kwargs["config"]["negative_prompt"] = negative_prompt

        if veo_image:
            kwargs["image"] = veo_image

        if os.environ.get("CAF_VEO_MOCK", "").strip().lower() in ("1", "true", "yes"):
            print(
                "INFO: CAF_VEO_MOCK enabled. Skipping Vertex AI API call and copying demo video."
            )
            source_demo = pathlib.Path("sandbox/assets/demo/dance_loop.mp4")
            if not source_demo.exists():
                # Try higher up if running from worker dir
                source_demo = pathlib.Path("../../sandbox/assets/demo/dance_loop.mp4")

            if source_demo.exists():
                print(f"Mocking output by copying {source_demo} to {output_path}")
                output_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source_demo, output_path)

                result_json = output_path.parent / "result.json"
                atomic_write_json(result_json, {
                    "version": "1.0",
                    "status": "success",
                    "output_relpath": str(output_path.name)
                })
                return
            else:
                print(f"ERROR: Mock source {source_demo} not found.", file=sys.stderr)
                sys.exit(1)

        response = client.models.generate_videos(**kwargs)

        print(f"Operation started: {response.name}")

        while True:
            current_op = client.operations.get(operation=response)

            if current_op.done:
                if current_op.error:
                    print(
                        f"ERROR: Video generation failed: {current_op.error}",
                        file=sys.stderr,
                    )
                    sys.exit(1)

                print("Generation complete.")
                result = current_op.result

                if result and result.generated_videos:
                    video_obj = result.generated_videos[0]
                    inner_video = video_obj.video

                    if inner_video and inner_video.uri:
                        print(f"Video URI: {inner_video.uri}")

                    if inner_video and inner_video.video_bytes:
                        print(
                            f"Writing {len(inner_video.video_bytes)} bytes to {output_path}"
                        )
                        with open(output_path, "wb") as f:
                            f.write(inner_video.video_bytes)
                    elif inner_video and inner_video.uri:
                        print(
                            f"WARNING: No bytes returned, but URI is {inner_video.uri}. Downloading not yet implemented.",
                            file=sys.stderr,
                        )
                        sys.exit(1)
                    else:
                        print(
                            "ERROR: No video content (bytes or URI) found in response.",
                            file=sys.stderr,
                        )
                        sys.exit(1)

                else:
                    print("ERROR: No generated_videos in result.", file=sys.stderr)
                    sys.exit(1)
                break

            print(".", end="", flush=True)
            time.sleep(5)

    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("job_json", type=pathlib.Path, nargs="?")
    parser.add_argument("output_video", type=pathlib.Path, nargs="?")
    parser.add_argument("--job", type=pathlib.Path, help="Path to job.json")
    parser.add_argument("--output", type=pathlib.Path, help="Path to output video")
    parser.add_argument(
        "--project",
        default=os.environ.get("GOOGLE_CLOUD_PROJECT")
        or os.environ.get("GCP_PROJECT_ID"),
        help="GCP Project ID",
    )
    parser.add_argument(
        "--location",
        default=os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1"),
        help="Vertex AI Location",
    )

    args = parser.parse_args()

    job_json = args.job or args.job_json
    output_video = args.output or args.output_video or os.environ.get("CAF_OUTPUT_OVERRIDE")

    if not job_json:
        parser.error("job_json is required (via positional or --job)")
    if not output_video:
        parser.error("output_video is required (via positional, --output, or CAF_OUTPUT_OVERRIDE)")

    output_video = pathlib.Path(output_video)

    load_env()

    gac = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if gac and not os.path.exists(gac):
        if gac:
            print(
                f"WARNING: GOOGLE_APPLICATION_CREDENTIALS file not found: {gac}. Unsetting to use ADC."
            )
        del os.environ["GOOGLE_APPLICATION_CREDENTIALS"]

    project_id = args.project
    if not project_id:
        if os.environ.get("GEN_LANG_CLIENT_PROJECT"):
            project_id = os.environ.get("GEN_LANG_CLIENT_PROJECT")
        else:
            project_id = "gen-lang-client-0381423928"

    if not project_id:
        print(
            "ERROR: Could not determine Google Cloud Project ID. Set GOOGLE_CLOUD_PROJECT or pass --project.",
            file=sys.stderr,
        )
        sys.exit(1)

    render(job_json, output_video, project_id, args.location)
