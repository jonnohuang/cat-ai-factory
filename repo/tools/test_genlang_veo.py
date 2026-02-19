#!/usr/bin/env python3
"""
Test script for Generating Video via Generative Language API (Veo)
Requires: GEMINI_API_KEY env var
"""
import os
import json
import time
import requests
import sys

def load_env():
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), ".env")
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
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("ERROR: GEMINI_API_KEY not found in .env")
        return

    # Using veo-2.0-generate-001 (or update to veo-3.0 if available)
    model = "veo-2.0-generate-001"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:predictLongRunning?key={api_key}"
    
    prompt = "A cinematic shot of a cute grey tabby kitten in a green dinosaur costume, dancing joyfully in a studio setting, high quality, 4k."
    
    payload = {
        "instances": [
            { "prompt": prompt }
        ],
        "parameters": {
            "sampleCount": 1
        }
    }
    
    print(f"POST {url}")
    print(json.dumps(payload, indent=2))
    
    resp = requests.post(url, json=payload)
    if resp.status_code != 200:
        print(f"ERROR: {resp.status_code}")
        print(resp.text)
        return

    lro = resp.json()
    op_name = lro.get("name")
    if not op_name:
        print("ERROR: No operation name returned")
        print(json.dumps(lro, indent=2))
        return
        
    print(f"Operation started: {op_name}. Polling...")
    
    # Poll
    while True:
        poll_url = f"https://generativelanguage.googleapis.com/v1beta/{op_name}?key={api_key}"
        poll_resp = requests.get(poll_url)
        if poll_resp.status_code != 200:
            print(f"ERROR: Poll failed {poll_resp.status_code}")
            print(poll_resp.text)
            return
            
        poll_json = poll_resp.json()
        if poll_json.get("done"):
            if "error" in poll_json:
                print("ERROR: Operation failed")
                print(json.dumps(poll_json["error"], indent=2))
                return
            
            print("Success! Operation done.")
            # print(json.dumps(poll_json.get("response", {}), indent=2))
            break
            
        print(".", end="", flush=True)
        time.sleep(5)

if __name__ == "__main__":
    main()
