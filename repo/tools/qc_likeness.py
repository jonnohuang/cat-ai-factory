#!/usr/bin/env python3
import argparse
import base64
import json
import os
import pathlib
import sys
import urllib.error
import urllib.parse
import urllib.request


def _repo_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parents[2]

def _get_api_key() -> str:
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        # Try to load from .env if running locally
        env_path = _repo_root() / ".env"
        if env_path.exists():
            with open(env_path, "r") as f:
                for line in f:
                    if line.startswith("GEMINI_API_KEY="):
                        return line.split("=", 1)[1].strip().strip('"').strip("'")
    return key

def check_likeness(image_path: pathlib.Path, target: str) -> dict:
    api_key = _get_api_key()
    if not api_key:
        return {"status": "ERROR", "message": "Missing GEMINI_API_KEY"}

    model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"

    with open(image_path, "rb") as f:
        img_data = base64.b64encode(f.read()).decode("utf-8")

    prompt = (
        f"Analyze this image. Does it contain a {target}? "
        "Return a JSON object with: "
        "\"likeness_score\": 0.0 to 1.0, "
        "\"detected_entities\": [list], "
        "\"is_hallucination\": true/false (true if it looks like a human when it should be a cat), "
        "\"reason\": \"brief explanation\"."
    )

    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt},
                    {"inline_data": {"mime_type": "image/png", "data": img_data}}
                ]
            }
        ],
        "generationConfig": {"temperature": 0.0, "response_mime_type": "application/json"}
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            text = data["candidates"][0]["content"]["parts"][0]["text"]
            return json.loads(text)
    except Exception as ex:
        return {"status": "ERROR", "message": str(ex)}

def main():
    parser = argparse.ArgumentParser(description="Likeness QC Gate")
    parser.add_argument("image_path", type=pathlib.Path)
    parser.add_argument("--target", default="cat", help="Target character (e.g. cat)")
    parser.add_argument("--threshold", type=float, default=0.7)
    args = parser.parse_args()

    if not args.image_path.exists():
        print(f"Error: Image not found at {args.image_path}")
        sys.exit(1)

    result = check_likeness(args.image_path, args.target)
    print(json.dumps(result, indent=2))

    if result.get("status") == "ERROR":
        sys.exit(1)

    score = result.get("likeness_score", 0.0)
    is_hallucination = result.get("is_hallucination", False)

    if is_hallucination:
        print(f"FAIL: Hallucination detected! Reason: {result.get('reason')}")
        sys.exit(2)

    if score < args.threshold:
        print(f"FAIL: Likeness score {score} below threshold {args.threshold}")
        sys.exit(2)

    print(f"PASS: Likeness score {score}")
    sys.exit(0)

if __name__ == "__main__":
    main()
