#!/usr/bin/env python3
"""
Debug script to list Vertex AI operations for Veo.
"""

import json
import os
import sys

import google.auth
import google.auth.transport.requests
import requests


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


def get_access_token():
    load_env()
    # Sanitize environment: if GOOGLE_APPLICATION_CREDENTIALS points to a missing file, unset it
    gac = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if gac and not os.path.exists(gac):
        del os.environ["GOOGLE_APPLICATION_CREDENTIALS"]

    scopes = [
        "https://www.googleapis.com/auth/cloud-platform",
        "https://www.googleapis.com/auth/generative-language.retriever",  # Try broad
        "https://www.googleapis.com/auth/generative-language",
    ]
    creds, project = google.auth.default(scopes=scopes)
    auth_req = google.auth.transport.requests.Request()
    creds.refresh(auth_req)
    return creds.token, project


def main():
    token, project = get_access_token()
    project = os.environ.get("GOOGLE_CLOUD_PROJECT") or project
    location = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
    print(f"Listing operations for {project} in {location}...")

    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    # Try standard operations endpoint (regional)
    url = f"https://{location}-aiplatform.googleapis.com/v1/projects/{project}/locations/{location}/operations"
    _check_ops(url, headers, "Regional")

    # Try global operations endpoint (sometimes used for certain resources)
    url_global = f"https://aiplatform.googleapis.com/v1/projects/{project}/locations/global/operations"
    _check_ops(url_global, headers, "Global")

    # Try direct access to a known LRO (from previous error log)
    # 74957c71-5d84-44ee-a0a3-7613adc13b5e
    op_id = "74957c71-5d84-44ee-a0a3-7613adc13b5e"
    # url_direct = f"https://{location}-aiplatform.googleapis.com/v1/projects/{project}/locations/{location}/operations/{op_id}"
    # _check_ops(url_direct, headers, "Direct LRO")

    # v1beta1 Regional Standard
    url_beta = f"https://{location}-aiplatform.googleapis.com/v1beta1/projects/{project}/locations/{location}/operations"
    _check_ops(url_beta, headers, "v1beta1 Regional")

    # v1beta1 Publisher Operations (likely candidate for Veo)
    # projects/{project}/locations/{location}/publishers/google/operations/{op_id}
    # But list first?
    # No list endpoint for publishers/google/operations usually.
    # Try direct access on v1beta1 publisher path for known ID
    op_id = "74957c71-5d84-44ee-a0a3-7613adc13b5e"

    # 1. v1beta1 Publisher Operations Collection (Direct)
    url_beta_pub = f"https://{location}-aiplatform.googleapis.com/v1beta1/projects/{project}/locations/{location}/publishers/google/operations/{op_id}"
    _check_ops(url_beta_pub, headers, "v1beta1 Publisher Direct")

    # 2. v1beta1 Publisher Model Operations (Direct)
    # projects/{project}/locations/{location}/publishers/google/models/veo-2.0-generate-001/operations/{op_id}
    url_beta_model_ops = f"https://{location}-aiplatform.googleapis.com/v1beta1/projects/{project}/locations/{location}/publishers/google/models/veo-2.0-generate-001/operations/{op_id}"
    _check_ops(url_beta_model_ops, headers, "v1beta1 Publisher Model Direct")

    # v1beta1 Standard Operations (Direct) - Attempting because v1 returned "Must be Long"
    # projects/{project}/locations/{location}/operations/{op_id}
    url_beta_std_direct = f"https://{location}-aiplatform.googleapis.com/v1beta1/projects/{project}/locations/{location}/operations/{op_id}"
    _check_ops(url_beta_std_direct, headers, "v1beta1 Standard Direct")

    # Generative Language API Endpoint
    # models/veo-2.0-generate-001/operations/{op_id}
    # Note: no project/location in URL usually, or implied by API key. But we have token.
    url_genlang = f"https://generativelanguage.googleapis.com/v1beta/models/veo-2.0-generate-001/operations/{op_id}"
    _check_ops(url_genlang, headers, "Generative Language API")

    # Generative Language API Endpoint with API Key
    # Load API Key from env (simulated here)
    api_key = os.environ.get("GEMINI_API_KEY")
    if api_key:
        url_genlang_key = f"https://generativelanguage.googleapis.com/v1beta/models/veo-2.0-generate-001/operations/{op_id}?key={api_key}"
        # No headers for key-based auth (or minimal)
        _check_ops(url_genlang_key, {}, "Generative Language API (API Key)")
    else:
        print("Skipping API Key check (GEMINI_API_KEY not set)")


def _check_ops(url, headers, label):
    print(f"Checking {label} operations at {url}...")
    resp = requests.get(url, headers=headers)
    if resp.status_code != 200:
        print(f"ERROR: {resp.status_code}")
        print(resp.text)
        return

    ops = resp.json().get("operations", [])
    print(f"Found {len(ops)} operations.")
    for op in ops[:5]:
        print(f"Name: {op.get('name')}")
        print("-" * 20)


if __name__ == "__main__":
    main()
