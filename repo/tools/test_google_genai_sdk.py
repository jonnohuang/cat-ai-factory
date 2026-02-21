#!/usr/bin/env python3
"""
Test script for Generating Video via google-genai SDK (Veo)
Requires: pip install google-genai
"""

import json
import os
import time

from google import genai
from google.genai import types


def load_env():
    env_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        ".env",
    )
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    key, _, val = line.partition("=")
                    if key and val:
                        os.environ[key.strip()] = val.strip().strip('"').strip("'")


def main():
    load_env()
    # Sanitize environment: if GOOGLE_APPLICATION_CREDENTIALS points to a missing file, unset it
    gac = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if gac and not os.path.exists(gac):
        del os.environ["GOOGLE_APPLICATION_CREDENTIALS"]

    project = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("GCP_PROJECT_ID")
    location = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")

    if not project:
        print("ERROR: GOOGLE_CLOUD_PROJECT not found in .env")
        return

    print(f"Initializing google-genai client for project={project} location={location}")

    # Initialize client
    client = genai.Client(vertexai=True, project=project, location=location)

    prompt = "A cinematic shot of a cute grey tabby kitten in a green dinosaur costume, dancing joyfully in a studio setting, high quality, 4k."

    print("Generating video with veo-2.0-generate-001...")

    try:
        response = client.models.generate_videos(
            model="veo-2.0-generate-001",
            prompt=prompt,
        )

        print("Response received!")
        print(f"Operation Name: {response.name}")

        import inspect

        print(
            f"Signature of client.operations.get: {inspect.signature(client.operations.get)}"
        )

        while True:
            # Try passing the response object itself
            current_op = client.operations.get(operation=response)

            print(f"current_op type: {type(current_op)}")
            # print(current_op)

            if hasattr(current_op, "done") and current_op.done:
                print("Operation done!")
                if current_op.error:
                    print(f"ERROR: {current_op.error}")
                else:
                    # Success! Result is in current_op.result
                    print("Success!")
                    result = current_op.result
                    if result and result.generated_videos:
                        video_output = result.generated_videos[0].video
                        print(f"video.video type: {type(video_output)}")
                        print("Attributes of video.video:")
                        if video_output:
                            for m in dir(video_output):
                                if not m.startswith("_"):
                                    print(f"  - {m}")
                        else:
                            print("video.video is None!")
                        pass
                    else:
                        print("No video in result.")
                break

            print(".", end="", flush=True)
            time.sleep(5)

    except Exception as e:
        print(f"ERROR: {e}")


if __name__ == "__main__":
    main()
