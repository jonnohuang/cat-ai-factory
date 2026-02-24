#!/usr/bin/env python3
import argparse
import json
import os
import pathlib
import sys
from datetime import datetime, timezone

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
REGISTRY_PATH = REPO_ROOT / "repo/shared/handoff_registry.v1.json"

def now_ts() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )

def main():
    parser = argparse.ArgumentParser(description="Register a posted clip in the handoff registry.")
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--platform", required=True)
    parser.add_argument("--post-url", required=True)
    parser.add_argument("--platform-post-id")
    parser.add_argument("--author")
    parser.add_argument("--niche")
    parser.add_argument("--lane")
    args = parser.parse_args()

    if not REGISTRY_PATH.exists():
        print(f"Error: Registry not found at {REGISTRY_PATH}")
        sys.exit(1)

    with open(REGISTRY_PATH, "r") as f:
        registry = json.load(f)

    # Check for duplicates
    for entry in registry["entries"]:
        if entry["job_id"] == args.job_id and entry["platform"] == args.platform:
            print(f"Info: {args.job_id} on {args.platform} already registered.")
            return

    new_entry = {
        "job_id": args.job_id,
        "platform": args.platform,
        "post_url": args.post_url,
        "platform_post_id": args.platform_post_id,
        "posted_at": now_ts(),
        "author": args.author,
        "niche": args.niche,
        "lane": args.lane
    }

    registry["entries"].append(new_entry)
    registry["updated_at"] = now_ts()

    with open(REGISTRY_PATH, "w") as f:
        json.dump(registry, f, indent=2)

    print(f"Successfully registered {args.job_id} on {args.platform} in handoff registry.")

if __name__ == "__main__":
    main()
