#!/usr/bin/env python3
import argparse
import os
import sys
import json
import time
import pathlib
import requests

# Try importing google-genai, if not present, exit with error
try:
    from google import genai
    from google.genai import types
except ImportError:
    print("ERROR: 'google-genai' package not found. Install with: pip install google-genai", file=sys.stderr)
    sys.exit(1)

def _sanitize_creds():
    """
    Sanitize environment: if GOOGLE_APPLICATION_CREDENTIALS points 
    to a missing file, unset it to allow fallback to ADC.
    """
    gac = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if gac and not os.path.exists(gac):
        # print(f"WARNING: GOOGLE_APPLICATION_CREDENTIALS set to missing file '{gac}'. Unsetting to use ADC.")
        del os.environ["GOOGLE_APPLICATION_CREDENTIALS"]

def load_job(job_path: pathlib.Path) -> dict:
    with open(job_path, "r") as f:
        return json.load(f)

def render(job_path: pathlib.Path, output_path: pathlib.Path, project_id: str, location: str):
    job = load_job(job_path)
    
    # Extract prompt from job
    # Structure depends on job format. Assuming "prompt" key or similar from args
    # For Veo, we need a text prompt.
    # Check if job has "prompt" directly or in "comfyui.bindings.prompt"
    prompt = job.get("prompt")
    if not prompt:
        bindings = job.get("comfyui", {}).get("bindings", {})
        prompt = bindings.get("prompt_text") or bindings.get("prompt")
        
    if not prompt:
        print("ERROR: No prompt found in job JSON", file=sys.stderr)
        sys.exit(1)
        
    print(f"Authenticating (project={project_id}, location={location})")
    
    # Initialize google-genai client
    try:
        client = genai.Client(vertexai=True, project=project_id, location=location)
    except Exception as e:
        print(f"ERROR: Failed to initialize google-genai client: {e}", file=sys.stderr)
        sys.exit(1)
        
    print(f"Generating video with veo-2.0-generate-001...")
    print(f"Prompt: {prompt}")
    
    try:
        # Start generation
        response = client.models.generate_videos(
            model='veo-2.0-generate-001',
            prompt=prompt,
        )
        
        print(f"Operation started: {response.name}")
        
        # Poll for completion
        while True:
            # Poll operation status
            current_op = client.operations.get(operation=response)
            
            if current_op.done:
                if current_op.error:
                    print(f"ERROR: Video generation failed: {current_op.error}", file=sys.stderr)
                    sys.exit(1)
                
                print("Generation complete.")
                result = current_op.result
                
                if result and result.generated_videos:
                    # Get the first video
                    video_obj = result.generated_videos[0]
                    # Check for bytes or URI
                    # Based on introspection, GeneratedVideo has a .video attribute of type Video
                    # which likely contains the data
                    
                    # Inspect if video_bytes is available directly on video_obj or nested
                    # Based on test script: video_obj is GeneratedVideo
                    # It has a .video attribute
                    inner_video = video_obj.video 
                    
                    if inner_video and inner_video.uri:
                         print(f"Video URI: {inner_video.uri}")
                         # If it's a GCS URI and we want local file, we might need to download
                         # For now, let's just print it. If bytes are missing, we might need to implement download.
                         # But Veo usually returns bytes for small videos?
                         pass
                    
                    if inner_video and inner_video.video_bytes:
                        print(f"Writing {len(inner_video.video_bytes)} bytes to {output_path}")
                        with open(output_path, "wb") as f:
                            f.write(inner_video.video_bytes)
                    elif inner_video and inner_video.uri:
                         print(f"WARNING: No bytes returned, but URI is {inner_video.uri}. Downloading not yet implemented.", file=sys.stderr)
                         # TODO: Implement GCS download if needed
                         sys.exit(1)
                    else:
                        print("ERROR: No video content (bytes or URI) found in response.", file=sys.stderr)
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

def main():
    load_env()
    _sanitize_creds()
    
    # Auto-detect project if not provided
    # internal helper to get default project if possible
    # But genai.Client handles this locally if we don't pass project?
    # Let's rely on args or env
    default_project = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("GCP_PROJECT_ID")
    default_location = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")

    parser = argparse.ArgumentParser(description="Vertex AI Veo3 Worker (google-genai)")
    parser.add_argument("--job", required=True, type=pathlib.Path, help="Path to job JSON")
    parser.add_argument("--out", required=True, type=pathlib.Path, help="Path to output MP4")
    parser.add_argument("--project", default=default_project, help="GCP Project ID")
    parser.add_argument("--location", default=default_location, help="GCP Region")
    
    args = parser.parse_args()
    
    if not args.project:
        # Try to guess from google.auth as fallback
        try:
             import google.auth
             _, project_id = google.auth.default()
             args.project = project_id
        except:
             pass

    if not args.project:
        print("ERROR: --project or GOOGLE_CLOUD_PROJECT env required", file=sys.stderr)
        sys.exit(1)

    render(args.job, args.out, args.project, args.location)

def load_env():
    # Helper to load .env manually if not running in an env with exported vars
    # traverse up until repo root
    current = pathlib.Path(__file__).resolve()
    for _ in range(4): # up to repo root
        current = current.parent
        env_path = current / ".env"
        if env_path.exists():
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        key, _, val = line.partition("=")
                        if key and val:
                            os.environ[key.strip()] = val.strip().strip('"').strip("'")
            break

if __name__ == "__main__":
    main()
